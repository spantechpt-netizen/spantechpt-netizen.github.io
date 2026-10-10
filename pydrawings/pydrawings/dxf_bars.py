"""
Bars read back from an edited sheet DXF.

Every entity of a bar on the design sheets (its polyline, call-out, length text, distribution dimension, dot, tags)
carries the bar's tag as extended data under the application `SPANTECH` (see `barTag` in design.mjs):
  1000 "BAR", 1000 <bar id>, 1000 <role>, 1000 <JSON figures>
The figures are the ones the sheet was drawn with: call-out, length text, diameter, spacing, count (0 = a run of
bars whose count follows the distribution width), face, cutting length, the polyline's drawn length, the
distribution width and the level.

When the engineer edits the sheet in AutoCAD - stretches a bar (STRETCH moves the polyline and the dimension
together), re-writes the call-out (`T16-150 (T)`), moves the distribution dimension - the drawing is uploaded back
and the take-off is updated from what is now drawn:
  - the cutting length follows the drawn polyline (the original cutting length plus the change in the drawn length),
  - the diameter and spacing follow the call-out text,
  - the count of a run of bars follows the distribution width (width / spacing + 1); a counted group keeps its count
    unless the call-out now says another count (`7T16`),
and the steel of the level moves by the difference, bar by bar. Bars that were not touched change nothing.
"""
import json
import math
import re

from .geometry import js_round
from .dxf_reader import parse_dxf
from .rebar import bar_weight_per_m

APP = 'SPANTECH'


def r1(v):
    return js_round(v * 10) / 10


def read_bars(dxf_text):
    """The bars of a DXF (model space and every block), each with what is now drawn for it."""
    dxf = parse_dxf(dxf_text) if isinstance(dxf_text, str) else dxf_text
    ents = list(dxf['entities'])
    for b in dxf['blocks'].values():
        ents.extend(b['entities'])
    bars = {}
    for e in ents:
        x = (e.get('xdata') or {}).get(APP)
        if not x:
            continue
        strs = [v for c, v in x if c == 1000]
        if not strs or strs[0] != 'BAR' or len(strs) < 4:
            continue
        _, id_, role, js = strs[0], strs[1], strs[2], strs[3]
        try:
            payload = json.loads(js)
        except Exception:
            continue
        b = bars.get(id_)
        if not b:
            b = {'id': id_, 'payload': payload, 'now': {}}
            bars[id_] = b
        if role == 'BAR' and e.get('type') == 'LWPOLYLINE':
            b['now']['pl'] = _polyline_length(e['pts'], e.get('closed'))
        elif role == 'CALLOUT' and e.get('text') is not None:
            b['now']['l1'] = str(e['text']).strip()
        elif role == 'LENGTH' and e.get('text') is not None:
            b['now']['l2'] = str(e['text']).strip()
        elif role == 'DIST' and e.get('type') == 'DIMENSION':
            b['now']['dw'] = _dimension_measure(e)
    return list(bars.values())


def _polyline_length(pts, closed):
    L = 0
    for i in range(1, len(pts)):
        L += math.hypot(pts[i]['x'] - pts[i - 1]['x'], pts[i]['y'] - pts[i - 1]['y'])
    if closed and len(pts) > 2:
        L += math.hypot(pts[0]['x'] - pts[-1]['x'], pts[0]['y'] - pts[-1]['y'])
    return L


def _dimension_measure(e):
    """What a rotated dimension measures now: its two definition points projected on its direction (code 42 as a fallback)."""
    if e.get('x3') is not None and e.get('x4') is not None:
        ang = ((e.get('rotation') or 0) * math.pi) / 180
        u = {'x': math.cos(ang), 'y': math.sin(ang)}
        dx = e['x4'] - e['x3']
        dy = e['y4'] - e['y3']
        along = abs(dx * u['x'] + dy * u['y'])
        if along > 1e-6:
            return along
        return math.hypot(dx, dy)
    m = e.get('measure')
    try:
        m = float(m) if m is not None else 0  # Number(e.measure) || 0
    except (TypeError, ValueError):
        m = 0
    return m if (m and math.isfinite(m)) else 0


def parse_callout(text):
    """The call-out figures: count (0 = a run), diameter, spacing."""
    s = str(text if text is not None else '')
    # the consultant's per-metre form "7T18/m": a run at 1000 / 7 spacing, not 7 bars
    pm = re.search(r'(\d+)\s*T(\d+)\s*/\s*m', s, re.I)
    if pm:
        return {'n': 0, 'dia': int(pm.group(2)), 's': js_round(1000 / int(pm.group(1)))}
    m = re.search(r'(\d+)?\s*T(\d+)(?:-(\d+))?', s, re.I)
    if not m:
        return None
    return {'n': int(m.group(1)) if m.group(1) else 0, 'dia': int(m.group(2)), 's': int(m.group(3)) if m.group(3) else 0}


def _round10(v):
    return js_round(v / 10) * 10


def _gt0(v):
    return v is not None and v > 0


def bar_figures(bar):
    """One bar's figures before and after the edit, and whether anything moved."""
    P = bar['payload']
    now = bar.get('now') or {}

    def count_of(n, s, dw):
        return n if _gt0(n) else (math.floor(dw / s + 1e-6) + 1) if (_gt0(s) and _gt0(dw)) else 1

    before = {'dia': P.get('dia'), 's': P.get('s'), 'n': P.get('n'), 'L': P.get('L'), 'dw': P.get('dw'), 'count': count_of(P.get('n'), P.get('s'), P.get('dw'))}
    call = parse_callout(now['l1']) if now.get('l1') is not None else None
    # the call-out decides the diameter and spacing; a count written in it (`7T16`) decides the count, otherwise the
    # group keeps its count (a run of bars, n = 0, follows the distribution width)
    dia = (call or {}).get('dia') or P.get('dia')
    s = (call['s'] or (0 if call['n'] else P.get('s'))) if call else P.get('s')
    n = (call or {}).get('n') or P.get('n')
    dL = now['pl'] - P['pl'] if (now.get('pl') is not None and P.get('pl')) else 0
    L = max(0, _round10((P.get('L') or 0) + dL))  # P.L is always written by the tag (NaN in JS if it were missing)
    dw = js_round(now['dw']) if now.get('dw') is not None else P.get('dw')
    after = {'dia': dia, 's': s, 'n': n, 'L': L, 'dw': dw, 'count': count_of(n, s, dw)}

    def kg_of(f):
        return (f['count'] * f['L'] / 1000) * bar_weight_per_m(f['dia'])

    before['kg'] = r1(kg_of(before))
    after['kg'] = r1(kg_of(after))
    changed = before['dia'] != after['dia'] or before['s'] != after['s'] or before['count'] != after['count'] or abs(before['L'] - after['L']) >= 10
    return {'id': bar['id'], 'face': P.get('face'), 'level': P.get('lv') or '', 'l1': now.get('l1') or P.get('l1'), 'l2': now.get('l2') or P.get('l2'),
            'before': before, 'after': after, 'changed': changed}


def takeoff_from_bars(bars):
    """The take-off change of an edited sheet: every changed bar and the steel difference by face and diameter."""
    figures = [bar_figures(b) for b in bars]
    changed = [f for f in figures if f['changed']]
    delta = {'kg': 0, 'top_kg': 0, 'bottom_kg': 0, 'other_kg': 0, 'byDia': {}}
    for f in changed:
        d = f['after']['kg'] - f['before']['kg']
        delta['kg'] += d
        if f['face'] == 'T':
            delta['top_kg'] += d
        elif f['face'] == 'B':
            delta['bottom_kg'] += d
        else:
            delta['other_kg'] += d
        for sign, fig in [[-1, f['before']], [1, f['after']]]:
            key = fig['dia']
            if key not in delta['byDia']:
                delta['byDia'][key] = {'dia': key, 'kg': 0, 'total_m': 0, 'count': 0}
            delta['byDia'][key]['kg'] += sign * fig['kg']
            delta['byDia'][key]['total_m'] += sign * (fig['count'] * fig['L']) / 1000
            delta['byDia'][key]['count'] += sign * fig['count']
    for k in ['kg', 'top_kg', 'bottom_kg', 'other_kg']:
        delta[k] = r1(delta[k])
    delta['byDia'] = sorted([d for d in ({**d, 'kg': r1(d['kg']), 'total_m': r1(d['total_m'])} for d in delta['byDia'].values()) if d['kg'] or d['count']], key=lambda d: d['dia'])
    first = changed[0] if changed else figures[0] if figures else None
    level = (first or {}).get('level') or ''
    return {'bars': len(figures), 'changed': len(changed), 'level': level, 'delta': delta, 'list': changed}


def apply_takeoff(quantities, level_id, change, note=None):
    """
    The run's take-off with an edited sheet's change applied to its level (steel by face and diameter, the project
    totals re-summed); the note says which file, who and when.
    """
    if note is None:
        note = {}
    q = json.loads(json.dumps(quantities or {'levels': [], 'totals': {}}))
    level = next((l for l in q['levels'] if l.get('id') == level_id), None) or (q['levels'][0] if q['levels'] else None)
    if not level:
        return q
    st = level['steel']
    st['kg'] = r1(st['kg'] + change['delta']['kg'])
    st['top_kg'] = r1((st.get('top_kg') or 0) + change['delta']['top_kg'])
    st['bottom_kg'] = r1((st.get('bottom_kg') or 0) + change['delta']['bottom_kg'])
    st['other_kg'] = r1((st.get('other_kg') or 0) + change['delta']['other_kg'])
    for d in change['delta']['byDia']:
        row = next((x for x in st['byDia'] if x['dia'] == d['dia']), None)
        if row:
            row['kg'] = r1(row['kg'] + d['kg'])
            row['total_m'] = r1(row['total_m'] + d['total_m'])
            row['count'] = (row.get('count') or 0) + d['count']
        else:
            st['byDia'].append({'dia': d['dia'], 'kg': r1(d['kg']), 'total_m': r1(d['total_m']), 'count': d['count']})
    st['byDia'] = sorted([x for x in st['byDia'] if x['kg'] > 0 or x['count'] > 0], key=lambda x: x['dia'])
    net = (level.get('concrete') or {}).get('net_area_m2')
    if net:
        st['kg_per_m2'] = js_round((st['kg'] / net) * 100) / 100  # else st.kg_per_m2 stays as it is
    if (level.get('concrete') or {}).get('total_m3'):
        st['kg_per_m3'] = r1(st['kg'] / level['concrete']['total_m3'])  # else st.kg_per_m3 stays as it is
    level['edited'] = list(level.get('edited') or []) + [{**note, 'bars': change['changed'], 'delta_kg': change['delta']['kg']}]

    # the project totals re-summed
    def sum_by(get):
        return r1(sum((get(l) or 0) for l in q['levels']))

    by_dia = {}
    for l in q['levels']:
        for d in l['steel'].get('byDia') or []:
            if d['dia'] not in by_dia:
                by_dia[d['dia']] = {'dia': d['dia'], 'total_m': 0, 'kg': 0, 'count': 0}
            by_dia[d['dia']]['total_m'] += d['total_m']
            by_dia[d['dia']]['kg'] += d['kg']
            by_dia[d['dia']]['count'] += d.get('count') or 0
    q['totals'] = q.get('totals') or {}
    q['totals']['steel'] = {
        **(q['totals'].get('steel') or {}),
        'kg': sum_by(lambda l: l['steel'].get('kg')), 'top_kg': sum_by(lambda l: l['steel'].get('top_kg')), 'bottom_kg': sum_by(lambda l: l['steel'].get('bottom_kg')),
        'other_kg': sum_by(lambda l: l['steel'].get('other_kg')), 'mesh_kg': sum_by(lambda l: l['steel'].get('mesh_kg')),
        'byDia': [{**d, 'total_m': r1(d['total_m']), 'kg': r1(d['kg'])} for d in sorted(by_dia.values(), key=lambda d: d['dia'])],
    }
    net_all = (q['totals'].get('concrete') or {}).get('net_area_m2')
    if net_all:
        q['totals']['steel']['kg_per_m2'] = js_round((q['totals']['steel']['kg'] / net_all) * 100) / 100
    q['edited'] = list(q.get('edited') or []) + [{'level': level.get('id'), **note, 'bars': change['changed'], 'delta_kg': change['delta']['kg']}]
    return q
