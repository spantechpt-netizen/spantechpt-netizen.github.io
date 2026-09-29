"""
Design drawings in the office's own convention.

Input: the office's reinforcement design plan (RFT drawing) as drawn by the
design team, plus the rules of the office's "General Details" sheet for PT /
flat slabs. Output: a coordinated sheet set (framing, bottom, top, punching)
in the same frame as the shop drawings, where
  - everything the designer drew is kept exactly (bars, call-outs, distribution
    dimensions, dots, mesh labels, camber notes, level tags), and
  - the reinforcement the General Details ask for is added on the plan at the
    places the details refer to, drawn with the SAME bar convention:
      one line on REO-TOP / REO-BOT (magenta hidden / green), the call-out
      "T10-200 (T)" over "L=2400" in style BW (isocp) h=150 parallel to the bar,
      the distribution width as a red dimension with arch ticks and a green
      number across the bars, and a yellow dot where the bar meets it.
  Every added bar carries a small "D#" reference to the detail it comes from.

Details applied (numbers as on the General Details sheet):
  D1  slab edge with edge beam        T10-200 L-bar (T) 1200 into the slab (+ distribution T10-250 unless a top mesh exists)
  D2  slab edge at core / retaining wall   T12@200 U-bar (LB 1200, LC = t - cover, LA as plan); 10T12 (T&B) parallel only with spec.walls.parallelBars
  D3  varying slab thickness          500 lap at the step (note)
  D4  column drop / thickened zone    T12@250 (B) extra reinforcement both ways inside the zone, 50 dia beyond it
  D5  core wall and slab corners      3T16-200 diagonals 2 m long T&B (3T12 at re-entrant slab corners)
  D7  MEP voids                       longitudinal T&B each side, transverse U-bars, diagonals, per the void size table
  D12 punching                        PS tags "rows-legs-dia" per column with the schedule (preliminary)
  Anchorage-dependent details (D6 slab edge at live anchors, bursting spirals, pan-box trimmers) need the
  tendon layout and are left out on purpose; site-specific details (D8-D11) apply only where drawn.

(Ported line by line from shopdrawings/lib/design.mjs.)
"""
import json
import math
import re
from datetime import datetime, timezone

from .extract import extract_model, flatten, closed_polys
from .geometry import (
    bbox, dist, polygon_area, point_in_polygon, centroid, rect_polygon, as_axis_rect, clean_polygon, ceil_to,
    dist_to_polygon, clip_segment_to_polygon, js_round, fmt_num, to_fixed, js_hypot, mid, unit, perp, add, dist_to_seg,
)
from . import rebar as R
from . import details as D
from .sheets import (
    build_sheet, draw_base, common_notes, level_assumptions, grid_ref, fmt_mm, pack_sheets, ram_cables_sheet,
    beam_schedule_rows, BEAM_SCHEDULE_COLS, draw_beam_sections, beam_steel_kg, beam_schedule_totals, beam_schedule_notes,
)
from .punching import override_columns
from . import ram_concept as RC
from .canvas import opts as _opts, js_str

# The office's DIM100: 250 text, 150 oblique ticks, green number, text above the line, and no extension lines at all (dimse1/dimse2 on, dimexe 0).
DIM100 = {'txt': 250, 'asz': 150, 'tsz': 150, 'exo': 0, 'exe': 0, 'gap': 70, 'tad': 1, 'clrt': 3, 'clrd': 256, 'clre': 256, 'dec': 0, 'txsty': 'BW', 'se1': True, 'se2': True}

# ------------------------------------------------------------------ office convention
OFFICE_LAYERS = {
    'REO-TOP': {'color': 6, 'ltype': 'HIDDEN', 'lw': 20},  # reinforcement always 0.20 mm: it stands out among the plan lines
    'REO-BOT': {'color': 3, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REO-TXT': {'color': 7, 'ltype': 'CONTINUOUS'},
    'S-TEXT': {'color': 7, 'ltype': 'CONTINUOUS'},
    'diamension': {'color': 1, 'ltype': 'CONTINUOUS'},
    'DOTS': {'color': 2, 'ltype': 'CONTINUOUS'},
    '9_TEXT': {'color': 4, 'ltype': 'CONTINUOUS'},
    'TEXT-4': {'color': 7, 'ltype': 'CONTINUOUS'},
    'LV': {'color': 1, 'ltype': 'CONTINUOUS'},
    'DETAIL-REF': {'color': 5, 'ltype': 'CONTINUOUS'},
    'PS-TAG': {'color': 1, 'ltype': 'CONTINUOUS'},
    'PS-ROW': {'color': 8, 'ltype': 'CONTINUOUS'},
    'REBAR-PUNCH': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 20},
    's-hatch': {'color': 8, 'ltype': 'CONTINUOUS'},  # the office's column fill: solid grey
}
OFFICE_TEXT_STYLE = {'name': 'BW', 'font': 'isocp.shx', 'widthFactor': 0.8}
PERIM_DIM_IN = 350  # the perimeter distribution dimension sits this far inside the slab edge (nothing is drawn outside the slab)
CALL_H, LEN_H, DIM_H, DIM_TICK, DIM_EXO, DIM_EXE, DOT_R = 150, 150, 250, 150, 50, 100, 33
BAR_W = 20  # every reinforcement bar is a polyline of constant width 20 (model mm)


# ------------------------------------------------------------------ JS semantics helpers
def _t(v):
    """JS truthiness of a value (an empty list / dict is truthy in JS, NaN and '' are not)."""
    if v is None or v is False:
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return not (v == 0 or (isinstance(v, float) and math.isnan(v)))
    if isinstance(v, str):
        return v != ''
    return True


def _nn(v, default):
    """JS `v ?? default`."""
    return default if v is None else v


def _join(arr, sep):
    """JS `Array.prototype.join`: null / undefined print as '', numbers as `String(number)`."""
    return sep.join('' if v is None else js_str(v) for v in arr)


def _whole(v):
    """A JS number that is whole prints without a fraction: keep it an int where the JS arithmetic yields a whole value."""
    if isinstance(v, float) and not math.isnan(v) and not math.isinf(v) and v == int(v):
        return int(v)
    return v


def _locale_en(v):
    """JS `Number.prototype.toLocaleString('en-US')` (up to 3 fraction digits, thousands separators)."""
    v = round(float(v), 3)
    if v == int(v):
        return f'{int(v):,}'
    return f'{v:,}'


def _sign(v):
    """JS `Math.sign` (as an int)."""
    return 1 if v > 0 else -1 if v < 0 else 0


def _rx_test(pattern, s, flags=0):
    return re.search(pattern, '' if s is None else js_str(s), flags) is not None


def bar_line(pl, pts, layer):
    """A bar on the plan: a polyline of width BAR_W."""
    return pl.pline(pts, {'layer': layer, 'width': BAR_W})


def leg_side(u, face):
    """
    The side a bar's legs / hooks are drawn on, by the engineering convention read from the bottom edge for a horizontal
    bar and from the RIGHT edge for a vertical one: a bottom bar's legs point up (a horizontal bar) / left (a vertical
    bar), a top bar's legs point down / right. Returns the unit normal.
    """
    n = {'x': -u['y'], 'y': u['x']}
    if n['y'] < -1e-9 or (abs(n['y']) <= 1e-9 and n['x'] > 0):
        n = {'x': -n['x'], 'y': -n['y']}  # "up / left"
    return n if face == 'B' else {'x': -n['x'], 'y': -n['y']}


DETAILS = {
    'D1': 'TYPICAL SLAB EDGE DETAIL WITH EDGE BEAM',
    'D2': 'TYPICAL SLAB EDGE DETAIL AT ANY CORE OR RETAINING WALLS',
    'D3': 'TYPICAL DETAIL AT VARYING SLAB THICKNESS',
    'D4': 'TYPICAL COLUMN DROP DETAIL',
    'D5': 'TYPICAL SLAB DETAIL AT CORE WALL AND SLAB CORNERS',
    'D6': 'TYPICAL SLAB EDGE REINFORCEMENT DETAIL (U.N.O.) - FREE EDGE U-BARS',
    'D7': 'TYPICAL MEP VOID DETAIL',
    'D8': 'TYPICAL POUR STRIP DETAIL (PT DETAILS 3)',
    'D9': 'TYPICAL BLOCKWORK SUPPORT BEAM DETAIL THROUGH VOID',
    'D12': 'TYPICAL PUNCHING DETAIL (PS TYPES: ROWS - LEGS - BAR)',
}

# Void reinforcement table of detail 7 (size of void in metres).
VOID_TABLE = [
    {'max': 0.5, 'long': {'n': 1, 'dia': 12, 's': 150}, 'u': {'dia': 10, 's': 150}, 'diag': 12},
    {'max': 1.0, 'long': {'n': 2, 'dia': 12, 's': 150}, 'u': {'dia': 12, 's': 150}, 'diag': 12},
    {'max': 2.5, 'long': {'n': 3, 'dia': 16, 's': 150}, 'u': {'dia': 12, 's': 150}, 'diag': 16},
    {'max': 4.0, 'long': {'n': 4, 'dia': 20, 's': 150}, 'u': {'dia': 16, 's': 150}, 'diag': 16},
    {'max': 5.5, 'long': {'n': 4, 'dia': 20, 's': 150}, 'u': {'dia': 16, 's': 100}, 'diag': 16},
]


def _text_of(e):
    return (e.get('text') or '').strip()


def _seg_mid(s):
    return mid(s['a'], s['b'])


def _near(p, q, r):
    return dist(p, q) < r


# ------------------------------------------------------------------ extraction
def extract_design(dxf, options=None):
    """
    Read the office design plan. Every slab outline becomes a PART (the office
    splits its plans the same way). Returns the extractModel result with, per
    level, the office-specific data: walls, thickness zones, the designer's own
    reinforcement (kept verbatim), mesh labels, camber notes and level tags.
    """
    options = options or {}
    model = extract_model(dxf, options)
    ospec = options.get('spec') or {}
    if ospec.get('edgeBeams') is False:
        for l in model['levels']:
            l['noEdgeBeams'] = True
    spec0 = model['spec']
    k = {'mm': 1, 'm': 1000, 'cm': 10}.get(model['source']['units']) or 1
    raw = [e if k == 1 else _scale_ent(e, k) for e in flatten(dxf)]
    texts = [e for e in raw if (e.get('type') == 'TEXT' or e.get('type') == 'MTEXT') and _text_of(e)]

    def A(level, text):
        model['assumptions'].append({'level': level['id'], 'text': text})

    # slab thickness from RC tags ("RC230") if the notes did not say
    rc_tags = [{'x': t['x'], 'y': t['y'], 'thickness': int(re.sub(r'\D', '', _text_of(t), flags=re.A))} for t in texts if re.search(r'^RC\s*\d{3}$', _text_of(t), re.I | re.A)]

    for li, level in enumerate(model['levels']):
        outline = level['outline']

        def in_part(p, outline=outline):
            return point_in_polygon(p, outline) or dist_to_polygon(p, outline) < 1500

        base_name = (options.get('levelNames') and options['levelNames'][0]) or re.sub(r'\s*-\s*PART.*$', '', model['levels'][0]['name'], count=1, flags=re.I)
        old_name = level['name']
        level['name'] = f"{base_name} - PART {str(li + 1).rjust(2, '0')}"
        model['findings'] = [f.replace(f"{level['id']} {old_name}:", f"{level['id']} {level['name']}:", 1) for f in model['findings']]
        for a in model['assumptions']:
            if a.get('level') == level['id']:
                a['text'] = a['text'].replace(old_name, level['name'], 1)
        # grid labels: a bubble text can be picked twice when two lines are close; give the second the next unused label
        for axis in ['x', 'y']:
            seen = set()
            for g in level['grid'][axis]:
                if g.get('label') and g['label'] in seen:
                    g['label'] = _next_label(g['label'], seen)
                seen.add(g.get('label'))
        level['partIndex'] = li

        # thickness: RC tag inside the part wins over the vote / assumption
        tag = next((t for t in rc_tags if point_in_polygon(t, outline)), None)
        if tag:
            level['thickness'] = tag['thickness']
            level['thicknessSource'] = 'RC tag on the plan'

        # walls: long or non-rectangular closed shapes on the column layer, and blade-shaped "columns"
        walls = []
        for e in [x for x in raw if re.search('COL', f"{js_str(x.get('layer'))} {x.get('fromBlock') or ''}", re.I) and (x.get('type') == 'LWPOLYLINE' or x.get('type') == 'HATCH')]:
            for p0 in closed_polys(e):
                p = clean_polygon(p0)
                if len(p) < 4:
                    continue
                b = bbox(p)
                rect = as_axis_rect(p, 5)
                long = max(b['w'], b['h']) >= 1500 and min(b['w'], b['h']) <= 600
                big = max(b['w'], b['h']) > 3000 and abs(polygon_area(p)) < 0.5 * b['w'] * b['h'] + 1
                if not (long or big or (not rect and abs(polygon_area(p)) > 0.3e6)):
                    continue
                if not in_part({'x': b['cx'], 'y': b['cy']}):
                    continue
                if any(_near(centroid(w['polygon']), centroid(p), 100) for w in walls):
                    continue
                along = 'x' if b['w'] >= b['h'] else 'y'
                walls.append({'polygon': list(reversed(p)) if polygon_area(p) < 0 else p, 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h'], 't': min(b['w'], b['h']), 'length': max(b['w'], b['h']),
                              'a': {'x': b['minX'], 'y': b['cy']} if along == 'x' else {'x': b['cx'], 'y': b['minY']},
                              'b': {'x': b['maxX'], 'y': b['cy']} if along == 'x' else {'x': b['cx'], 'y': b['maxY']}})

        def keep_column(c, walls=walls):
            blade = c.get('shape') != 'circle' and max(c['w'], c['h']) >= 1500 and max(c['w'], c['h']) / min(c['w'], c['h']) >= 4
            if blade and not any(_near({'x': w['cx'], 'y': w['cy']}, {'x': c['cx'], 'y': c['cy']}, 100) for w in walls):
                walls.append({'polygon': rect_polygon({'x': c['cx'] - c['w'] / 2, 'y': c['cy'] - c['h'] / 2, 'w': c['w'], 'h': c['h']}), 'cx': c['cx'], 'cy': c['cy'], 'w': c['w'], 'h': c['h'], 't': min(c['w'], c['h']), 'length': max(c['w'], c['h']),
                              'a': {'x': c['cx'] - c['w'] / 2, 'y': c['cy']} if c['w'] >= c['h'] else {'x': c['cx'], 'y': c['cy'] - c['h'] / 2},
                              'b': {'x': c['cx'] + c['w'] / 2, 'y': c['cy']} if c['w'] >= c['h'] else {'x': c['cx'], 'y': c['cy'] + c['h'] / 2}})
            return not blade
        level['columns'] = [c for c in level['columns'] if keep_column(c)]
        for i, w in enumerate(walls):
            w['id'] = f'W{i + 1}'
        level['walls'] = walls

        # a wall outline small enough to pass as a column is not a column
        def wall_takes(c):
            for w in walls:
                wb = bbox(w['polygon'])
                ox = max(0, min(c['cx'] + c['w'] / 2, wb['maxX']) - max(c['cx'] - c['w'] / 2, wb['minX']))
                oy = max(0, min(c['cy'] + c['h'] / 2, wb['maxY']) - max(c['cy'] - c['h'] / 2, wb['minY']))
                if _near({'x': w['cx'], 'y': w['cy']}, {'x': c['cx'], 'y': c['cy']}, 200) or (ox * oy > 0.5 * c['w'] * c['h'] and max(c['w'], c['h']) >= 1000):
                    return True
            return False
        level['columns'] = [c for c in level['columns'] if not wall_takes(c)]
        for i, c in enumerate(level['columns']):  # (the JS loop is a no-op: kept for the record)
            if not c.get('id') or re.search(r'^C\d+$', js_str(c['id']), re.A):
                continue

        # thickness zones: a nested outline with a 3-digit thickness written inside it (e.g. "280")
        thick_zones = list(level.get('thickZones') or [])

        def keep_sunken(z):
            if not z.get('fromOutline'):
                return True
            inside = [t for t in texts if re.search(r'^\d{3}$', _text_of(t), re.A) and point_in_polygon(t, z['polygon'])]
            if not inside:
                return True
            thick_zones.append({'polygon': z['polygon'], 'thickness': int(_text_of(inside[0])), 'kind': 'thick'})
            return False
        level['sunken'] = [z for z in (level.get('sunken') or []) if keep_sunken(z)]
        for i, z in enumerate(thick_zones):
            z['id'] = f'D{i + 1}'
        level['thickZones'] = thick_zones
        model['assumptions'] = [a for a in model['assumptions'] if not (a.get('level') == level['id'] and re.search(r'stepped \(sunken / raised\) zone', a['text']) and not level['sunken'])]

        # local RC thickness markers ("RC" + "200" at stairs)
        level['rcTags'] = [{'x': t['x'], 'y': t['y'], 'thickness': int(_text_of(t))}
                           for t in texts
                           if re.search(r'^\d{3}$', _text_of(t), re.A) and point_in_polygon(t, outline) and not any(point_in_polygon(t, z['polygon']) for z in thick_zones)
                           and any(re.search(r'^RC$', _text_of(u), re.I) and _near(u, t, 700) for u in texts)]

        # level tags "T.O.C" + "+12.35"
        level['levelTags'] = level.get('levelTags') or []
        for t in [x for x in texts if re.search(r'^T\.?O\.?[SC]\.?$', _text_of(x), re.I) and in_part(x)]:
            vs = sorted([u for u in texts if re.search(r'^[+-]?\d+(\.\d+)?$', _text_of(u), re.A) and _near(u, t, 1200)], key=lambda p: dist(p, t))
            v = vs[0] if vs else None
            if v:
                level['levelTags'].append({'x': v['x'], 'y': v['y'], 'label': _text_of(t).upper(), 'value': _text_of(v)})
        if level['levelTags'] and not _t(level.get('tos')):
            level['tos'] = level['levelTags'][0]['value']

        # designer's notes: camber, mesh labels
        seen = set()
        camber = []
        for t in [t for t in texts if re.search('CAMBER', _text_of(t), re.I) and in_part(t)]:
            key = f"{js_round(t['x'])}|{js_round(t['y'])}"
            if key in seen:
                continue
            seen.add(key)
            camber.append({'x': t['x'], 'y': t['y'], 'text': _text_of(t).upper()})
        level['camber'] = camber
        mesh_texts = [t for t in texts if re.search(r'MESH|TWO WAY|BOTTOM\s*&\s*TOP', _text_of(t), re.I) and in_part(t)]
        groups = []
        for t in mesh_texts:
            g = next((x for x in groups if _near(x, t, 1500)), None)
            if g:
                g['lines'].append(t)
            else:
                groups.append({'x': t['x'], 'y': t['y'], 'lines': [t]})
        level['meshLabels'] = [{'x': g['x'], 'y': g['y'], 'lines': [_text_of(t) for t in sorted(g['lines'], key=lambda p: -p['y'])]} for g in groups]
        mesh_spec = next((s for s in [' '.join(m['lines']) for m in level['meshLabels']] if re.search(r'T\d+@\d+', s, re.I | re.A)), None)
        level['meshSpec'] = [int(v) for v in re.search(r'T(\d+)@(\d+)', mesh_spec, re.I | re.A).groups()] if mesh_spec else None
        level['topMesh'] = bool(mesh_spec and re.search('TOP', mesh_spec, re.I))
        if ospec.get('mesh') == 'both' or ospec.get('mesh') == 'bottom':
            level['topMesh'] = ospec['mesh'] == 'both'  # the run option decides over the plan label

        # edge beams: a line on a beam layer running along the slab edge
        level['beams'] = [{'a': {'x': e['x'], 'y': e['y']}, 'b': {'x': e['x2'], 'y': e['y2']}} for e in raw
                          if e.get('type') == 'LINE' and re.search('BEAM', js_str(e.get('layer')), re.I) and (in_part({'x': e['x'], 'y': e['y']}) or in_part({'x': e['x2'], 'y': e['y2']}))]
        mark_beams(level, spec0, A)  # band beams (long thickened strips) take the beam rule
        level['edges'] = slab_edges(level)

        # the designer's own reinforcement, kept verbatim
        def in_win(p):
            return in_part(p)

        def bar_layer(l):
            return re.search(r'^REO-(TOP|BOT)$|S-TOP REINF|^REO-|REINF', js_str(l), re.I) is not None
        segs = []
        for e in raw:
            if not bar_layer(e.get('layer')):
                continue
            if e.get('type') == 'LINE':
                segs.append({'a': {'x': e['x'], 'y': e['y']}, 'b': {'x': e['x2'], 'y': e['y2']}, 'layer': e.get('layer')})
            elif e.get('type') == 'LWPOLYLINE':
                pts = e.get('pts') or []
                for i in range(len(pts) - 1):
                    segs.append({'a': pts[i], 'b': pts[i + 1], 'layer': e.get('layer')})
        lines = [s for s in segs if dist(s['a'], s['b']) > 200 and in_win(_seg_mid(s))]
        for l in lines:
            if dist(l['a'], l['b']) <= 350:
                l['tick'] = True  # the designer's short leg symbols at bar ends, not bars
        callouts = []
        for t in texts:
            if re.search('REO|S-TEXT|TXT', js_str(t.get('layer')), re.I) and re.search(r'T\d+|L\s*=|\(T\)|\(B\)|T&B', _text_of(t), re.I | re.A) and in_win(t):
                c = {'x': t['x'], 'y': t['y'], 'text': _text_of(t), 'h': t.get('height') or CALL_H, 'rot': t.get('rotation') or 0, 'halign': t.get('halign') or 0}
                if t.get('sx') and t['sx'] < 2:
                    c['widthFactor'] = t['sx']
                c['style'] = t.get('style')
                callouts.append(c)

        def face_of_text(s):
            return 'B' if re.search(r'\(B\)|BOT', s, re.I) else 'TB' if re.search(r'T\s*&\s*B|T&B', s, re.I) else 'T' if re.search(r'\(T\)|TOP', s, re.I) else None
        for c in callouts:
            c['face'] = face_of_text(c['text'])
        for c in [x for x in callouts if not x['face']]:
            hosts = sorted([x for x in callouts if x['face'] and _near(x, c, 700)], key=lambda p: dist(p, c))
            c['face'] = hosts[0]['face'] if hosts else 'T'
        for l in lines:
            m = _seg_mid(l)
            hosts = sorted([c for c in callouts if c['face'] and (dist_to_seg(c, l['a'], l['b']) < 500 or _near(c, m, 900))], key=lambda p: dist_to_seg(p, l['a'], l['b']))
            l['face'] = hosts[0]['face'] if hosts else 'B' if re.search('BOT', js_str(l.get('layer')), re.I) else 'T'

        # office rule: a top bar ending at the outer slab edge or at an opening ends in a U (500 bottom leg)
        # office rule: a top bar ending at the outer slab edge ends in a U (500 bottom leg), or in an L where the edge carries a beam; at an opening always a U
        def at_boundary(p):
            if any(dist_to_polygon(p, R.region_polygon(o)) < 300 for o in (level.get('openings') or [])):
                return 'U'
            return R.edge_end_at(level, spec0, p)['type'] if dist_to_polygon(p, outline) < spec0['cover'] + 300 else False
        for l in lines:
            if l['face'] != 'B' and not l.get('tick'):
                l['uEnd'] = {'start': at_boundary(l['a']), 'end': at_boundary(l['b'])}
        dims = [dict(e) for e in raw if e.get('type') == 'DIMENSION' and in_win(e)]
        dots = [{'x': e['x'], 'y': e['y']} for e in raw if e.get('type') == 'INSERT' and re.search('^DOT', e.get('name') or '', re.I) and in_win(e)]

        def face_near_line(p, r):
            ls = sorted([s for s in lines if dist_to_seg(p, s['a'], s['b']) < r], key=lambda s: dist_to_seg(p, s['a'], s['b']))
            return ls[0]['face'] if ls else 'T'
        for d in dims:
            d['face'] = face_near_line({'x': d['x'], 'y': d['y']}, 1500)
        for d in dots:
            d['face'] = face_near_line(d, 300)
        level['existing'] = {'lines': lines, 'callouts': callouts, 'dims': dims, 'dots': dots}
        # the designer's wall top bars: "T10-150 (T)" + "L=3000" near a wall face; LA of the U-bars follows them
        level['wallBarLengths'] = [{'x': c['x'], 'y': c['y'], 'L': int(re.sub(r'\D', '', c['text'], flags=re.A))} for c in callouts if re.search(r'^L\s*=\s*\d+', c['text'], re.I | re.A)]

        thk_list = f" ({_join(list(dict.fromkeys(z.get('thickness') for z in thick_zones)), '/')} mm)" if thick_zones else ''
        model['findings'].append(f"{level['id']} {level['name']}: {len(walls)} walls, {len(thick_zones)} thickness zones{thk_list}, {len([e for e in level['edges'] if e.get('beam')])} of {len(level['edges'])} slab edges with an edge beam, designer's reinforcement: {len(lines)} bars, {len(callouts)} call-outs, {len(dims)} distribution dimensions, {len(dots)} dots; mesh {mesh_spec or 'not labelled'}.")
        if not tag:
            A(level, f"Slab thickness of {level['name']} not tagged on the plan: {js_str(level.get('thickness'))} mm used.")
        if not walls:
            A(level, f"No walls read in {level['name']}: details 2 and 5 (core walls) not applied.")
    mark_joints(model, spec0['cover'])
    not_for_design = re.compile(r'Top bars over columns not specified|Edge U-bars not specified|Opening trimmers not specified|Void trimmers not specified|Stock bar length|No plan title found near slab')
    model['assumptions'] = [a for a in model['assumptions'] if not not_for_design.search(a['text']) and not (a['text'].startswith('Slab thickness not stated') and any(l['id'] == a.get('level') and l.get('thicknessSource') for l in model['levels']))]
    model['design'] = {'units': model['source']['units']}
    return model


# A RAM Concept model (from ramToModel) prepared for the design package: the bands designed in
# RAM become the designer's reinforcement, drawn in the office convention (bar line, call-out
# "T16-150 (T)" + "L=...", distribution DIMENSION, dot); walls become polygons; slab thicknesses
# are tagged on the plan; then the General Details rules are added on top exactly as for an RFT plan.
def _clip_poly_band(poly, axis, lo, hi):
    """Polygon clipped to the band lo <= axis <= hi (Sutherland-Hodgman against the two half-planes)."""
    def clip(pts, keep, at):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ia, ib = keep(a), keep(b)
            if ia:
                out.append(a)
            if ia != ib:
                t = (at - a[axis]) / (b[axis] - a[axis])
                out.append({'x': a['x'] + (b['x'] - a['x']) * t, 'y': a['y'] + (b['y'] - a['y']) * t})
        return out
    pts = clip(poly, lambda q: q[axis] >= lo, lo)
    if pts:
        pts = clip(pts, lambda q: q[axis] <= hi, hi)
    return pts if len(pts) >= 3 else None


def split_levels(model, spec):
    """
    A slab body too big for one sheet is split into PARTS along its longer side, as the office splits its plans
    (`spec.partMax`, 60 m, with `spec.partOverlap` 600 mm of overlap so that the cut reads as a drawing joint):
    columns, bands, stud rails and punching checks go to the part that holds their centre, walls / openings / zones /
    tendons are clipped to each part.
    """
    part_max = spec.get('partMax') or 60000
    ov = _nn(spec.get('partOverlap'), 600)
    out = []
    for level in model['levels']:
        b = bbox(level['outline'])
        axis = 'x' if b['w'] >= b['h'] else 'y'
        size = b['w'] if axis == 'x' else b['h']
        n = math.ceil(size / part_max)
        if n < 2:
            out.append(level)
            continue
        lo0 = b['minX'] if axis == 'x' else b['minY']
        step = size / n
        for k in range(n):
            lo, hi = lo0 + k * step, lo0 + (k + 1) * step

            def band(q, lo=lo, hi=hi, k=k):
                return q[axis] >= lo - (0 if k else 1) and q[axis] < hi + (1 if k == n - 1 else 0)
            outline = _clip_poly_band(level['outline'], axis, lo - (ov if k else 0), hi + (ov if k < n - 1 else 0))
            if not outline:
                continue

            def in_part(q, outline=outline):
                return point_in_polygon(q, outline)

            def clip_polys(lst, lo=lo, hi=hi, k=k):
                res = []
                for o in lst:
                    poly = _clip_poly_band(o['polygon'], axis, lo - (ov if k else 0), hi + (ov if k < n - 1 else 0))
                    if poly:
                        res.append({**o, 'polygon': poly})
                return res
            ram = level.get('ram') or {}
            grid = level.get('grid')
            if grid:
                grid = {
                    **grid,
                    'x': [({**g, 'y1': max(g['y1'], lo - ov), 'y2': min(g['y2'], hi + ov)} if axis == 'y' else g) for g in (grid.get('x') or []) if axis == 'y' or (g['x'] >= lo - ov - 1500 and g['x'] <= hi + ov + 1500)],
                    'y': [({**g, 'x1': max(g['x1'], lo - ov), 'x2': min(g['x2'], hi + ov)} if axis == 'x' else g) for g in (grid.get('y') or []) if axis == 'x' or (g['y'] >= lo - ov - 1500 and g['y'] <= hi + ov + 1500)],
                }
            walls = []
            for w in level.get('walls') or []:
                if w.get('polygon'):
                    if band(centroid(w['polygon'])):
                        walls.append(w)
                else:
                    for a, bb in clip_segment_to_polygon(w['a'], w['b'], outline):
                        if dist(a, bb) > 50:
                            walls.append({**w, 'a': a, 'b': bb})
            beams = []
            for bm in level.get('beams') or []:
                for a, bb in clip_segment_to_polygon(bm['a'], bm['b'], outline):
                    if dist(a, bb) <= 500:
                        continue
                    u = unit(a, bb)
                    nn = perp(u)
                    t = bm.get('t') or 300
                    nb = {**bm, 'a': a, 'b': bb, 'interior': None, 'polygon': [add(a, nn, t / 2), add(bb, nn, t / 2), add(bb, nn, -t / 2), add(a, nn, -t / 2)] if bm.get('polygon') else None}
                    beams.append(nb)
            pour_strips = []
            for ps in clip_polys(level.get('pourStrips') or []):
                pb = bbox(ps['polygon'])
                pour_strips.append({**ps, 'width': min(pb['w'], pb['h']), 'length': max(pb['w'], pb['h'])})
            tendons = []
            for t in ram.get('tendons') or []:
                if any(in_part(q) for q in (t.get('pts') or [])):
                    ct = RC.clip_tendon(t, outline, 300)
                    if ct:
                        tendons.append(ct)
            out.append({
                **level,
                'id': f"{level['id']}{'ABCDEFGHIJ'[k] if k < 10 else k + 1}" if level.get('customId') else f"L{str(len(out) + 1).rjust(2, '0')}", 'name': f"{level['name']} - PART {k + 1}", 'partOf': level['id'], 'partCut': {'axis': axis, 'lo': lo, 'hi': hi, 'overlap': ov, 'joints': {'lo': k > 0, 'hi': k < n - 1}},
                'outline': outline, 'bbox': bbox(outline),
                # the grid keeps the body's labels; only the lines that cross this part are drawn, trimmed to the part
                'grid': grid,
                'columns': [c for c in (level.get('columns') or []) if band({'x': c['cx'], 'y': c['cy']})],
                'walls': walls,
                # beams are clipped to the part along their axis (new objects: each part decides for itself whether a beam is interior)
                'beams': beams,
                'openings': clip_polys([{**o, 'kind': 'polygon', 'polygon': R.region_polygon(o)} for o in (level.get('openings') or [])]),
                'thickZones': clip_polys(level.get('thickZones') or []),
                'pourStrips': pour_strips,
                'ram': {
                    **ram,
                    'bands': [bd for bd in (ram.get('bands') or []) if band(mid(bd['p0'], bd['p1']))],
                    # a tendon running through the cut is drawn up to it on each part (cut end: no anchor, 'CONT.' on the sheet)
                    'tendons': tendons,
                    'shear': [sr for sr in (ram.get('shear') or []) if band(mid(sr['a'], sr['b']))],
                    'punching': [pc for pc in (ram.get('punching') or []) if band(pc['p'])],
                    'ssr': [st for st in (ram.get('ssr') or []) if band(st['loc'])],
                },
            })
        model['assumptions'].append({'level': level['id'], 'text': f"{level['name']} ({js_round(b['w'] / 1000)} x {js_round(b['h'] / 1000)} m) is drawn in {n} parts along its {'length' if axis == 'x' else 'height'} (the office splits its plans the same way); the cut between the parts is a drawing joint, not a slab edge."})
    model['levels'] = out


def mark_joints(model, cover):
    """
    Parts of one plan overlap where the office split it: an edge of one part that runs inside another part is a drawing
    joint, not a slab edge (no perimeter bars, no U ends there). Marks `e.joint`, sets `level.jointEdges`.
    """
    for level in model['levels']:
        # (a slab at another top-of-concrete level is a separate slab: its shared boundary is a step, a free edge, not a joint)
        others = [o for o in model['levels'] if o is not level and _nn(o.get('toc'), 0) == _nn(level.get('toc'), 0)]
        joints = 0
        for e in level.get('edges') or []:
            m = mid(e['a'], e['b'])
            q1 = add(m, unit(e['a'], e['b']), min(300, dist(e['a'], e['b']) / 3))
            q2 = add(m, unit(e['b'], e['a']), min(300, dist(e['a'], e['b']) / 3))
            e['joint'] = any(all(point_in_polygon(q, o['outline']) or dist_to_polygon(q, o['outline']) < 60 for q in [m, q1, q2]) for o in others)
            if e['joint']:
                e['beam'] = False
                joints += 1
        if not joints:
            continue
        level['jointEdges'] = [e for e in level['edges'] if e.get('joint')]
        jl = sum(dist(e['a'], e['b']) for e in level['jointEdges'])
        model['findings'].append(f"{level['id']} {level['name']}: {joints} edges ({js_round(jl / 1000)} m) are drawing joints with the neighbouring part, not slab edges: no perimeter bars or U ends there.")

        def at_joint(p, level=level):
            return any(dist_to_seg(p, e['a'], e['b']) < cover + 300 for e in level['jointEdges'])
        ex = level.get('existing') or {}
        for l in list(ex.get('lines') or []) + list(ex.get('items') or []):
            if l.get('uEnd'):
                for k in ['start', 'end']:
                    p = l['a'] if k == 'start' else l['b']
                    if l['uEnd'].get(k) and at_joint(p):
                        l['uEnd'][k] = False


def prepare_ram_design(model, options=None):
    options = options or {}
    wall_t = options.get('wallThickness') or 250
    spec = model['spec']
    ospec = options.get('spec') or {}
    split_levels(model, {**spec, **ospec})
    # the office rules need their full parameter sets (perimeter U / L bars, column bars, mesh at thickness changes)
    # (the office rules, not the RAM file's G.A. assumptions; the user's config overrides them)
    for key in ['uEdge', 'topColumns', 'thicknessMesh', 'openings', 'punching', 'drops']:
        spec[key] = {**R.DEFAULT_SPEC[key], **(ospec.get(key) or {})}
    # the office reinforcement defaults from the settings: bottom mesh, top mesh (both-faces option), column bars, drop bars
    if ospec.get('bottom'):
        spec['bottom'] = {**(spec.get('bottom') or R.DEFAULT_SPEC['bottom']), **ospec['bottom']}
    if ospec.get('topMesh'):
        spec['topMesh'] = {**(spec.get('bottom') or R.DEFAULT_SPEC['bottom']), **ospec['topMesh']}
    # the pour strip detail (internal and at a retaining wall) with the U-bar lengths from the settings
    spec['pourStrip'] = {**R.DEFAULT_SPEC['pourStrip'], **(ospec.get('pourStrip') or {}), 'wall': {**R.DEFAULT_SPEC['pourStrip']['wall'], **((ospec.get('pourStrip') or {}).get('wall') or {})}}

    def A(level, text):
        model['assumptions'].append({'level': level['id'], 'text': text})
    model['assumptions'] = [a for a in model['assumptions'] if not re.search(r'office standard reinforcement .* ADDITIONAL reinforcement', a['text'], re.I)]
    base_name = options.get('levelName') or re.sub(r'\s*-\s*PART.*$', '', (model['levels'][0].get('name') if model['levels'] else None) or 'SLAB', count=1, flags=re.I)
    tocs = list(dict.fromkeys(_nn(l.get('toc'), 0) for l in model['levels']))
    if len(tocs) > 1:
        model['assumptions'].append({'level': model['levels'][0]['id'], 'text': f"{base_name} has {len(tocs)} top-of-concrete levels ({' / '.join(('+' if t >= 0 else '') + fmt_num(js_round(t)) for t in tocs)} mm): each is drawn as a separate slab (office rule); the step between them is a free edge of both slabs (perimeter U-bars, bars stopped with a U, no bar runs across the step)."})
    for li, level in enumerate(model['levels']):
        outline = level['outline']
        level['partIndex'] = li
        if len(model['levels']) > 1:
            toc_txt = f" (T.O.C {'+' if level['toc'] > 0 else ''}{fmt_num(js_round(level['toc']))})" if len(tocs) > 1 and _t(level.get('toc')) else ''
            level['name'] = f"{base_name} - PART {str(li + 1).rjust(2, '0')}{toc_txt}"
        level['thicknessSource'] = 'RAM model'
        # walls: RAM line supports are axes; give them a body so the wall details (D2 / D5) and the lined-opening rule can see them
        walls = []
        for w in _merge_wall_segments([w for w in (level.get('walls') or []) if not w.get('polygon')]) + [w for w in (level.get('walls') or []) if w.get('polygon')]:
            if w.get('polygon'):
                walls.append(w)
                continue
            u = unit(w['a'], w['b'])
            n = perp(u)
            t = w.get('t') or wall_t
            walls.append({**w, 't': t, 'assumedT': not w.get('t'), 'length': dist(w['a'], w['b']), 'polygon': [add(w['a'], n, t / 2), add(w['b'], n, t / 2), add(w['b'], n, -t / 2), add(w['a'], n, -t / 2)]})
        level['walls'] = walls
        # blade "columns" (a core wall modelled as a long rectangular column) are walls for the drawing
        # (a 500 x 1500 or 500 x 2200 is still a column with its top bars; only a real blade, 2.5 m or longer and 4 x its width, is a wall)
        blade_min = options.get('bladeLength') or 2500
        blades = [c for c in (level.get('columns') or []) if c.get('shape') != 'circle' and max(c['w'], c['h']) >= blade_min and max(c['w'], c['h']) / min(c['w'], c['h']) >= 4 and not math.fmod(c.get('angle') or 0, 90)]
        if blades:
            level['columns'] = [c for c in level['columns'] if not any(c is bl for bl in blades)]
            for c in blades:
                level['walls'].append({'id': c.get('id'), 'polygon': rect_polygon({'x': c['cx'] - c['w'] / 2, 'y': c['cy'] - c['h'] / 2, 'w': c['w'], 'h': c['h']}), 't': min(c['w'], c['h']), 'length': max(c['w'], c['h']),
                                       'a': {'x': c['cx'] - c['w'] / 2, 'y': c['cy']} if c['w'] >= c['h'] else {'x': c['cx'], 'y': c['cy'] - c['h'] / 2},
                                       'b': {'x': c['cx'] + c['w'] / 2, 'y': c['cy']} if c['w'] >= c['h'] else {'x': c['cx'], 'y': c['cy'] + c['h'] / 2}, 'blade': True})
            blade_list = ', '.join(f"{js_str(c.get('id'))} {js_round(c['w'])}x{js_round(c['h'])}" for c in blades[:6])
            A(level, f"{len(blades)} long rectangular columns of {level['name']} ({blade_list}{', ...' if len(blades) > 6 else ''}) are drawn as walls: wall U-bars along their faces, no column top bars or punching tags.")
        for w in level['walls']:
            b = bbox(w['polygon'])
            w['cx'] = _nn(w.get('cx'), b['cx'])
            w['cy'] = _nn(w.get('cy'), b['cy'])
            w['w'] = _nn(w.get('w'), b['w'])
            w['h'] = _nn(w.get('h'), b['h'])
        for i, w in enumerate(level['walls']):
            if not w.get('id'):
                w['id'] = f'W{i + 1}'
        level['beams'] = level.get('beams') or []
        mark_beams(level, spec, A)
        level['edges'] = slab_edges(level)
        # thickness tags: the slab thickness once, each thickened zone inside it
        c0 = centroid(outline)
        if point_in_polygon(c0, outline):
            inside = c0
        else:
            b_ = bbox(outline)
            inside = {'x': b_['minX'] + 1500, 'y': b_['maxY'] - 1500}
        # the slab thickness once, away from any column; the thickened zones carry their own THK labels
        # the boxed slab tag (3.6 x 1.2 m at 1:100) goes where the slab is clear: the candidate on a 1 m grid inside the
        # outline with the largest clearance from columns, walls, openings, thickened zones and pour strips, nearest to
        # the middle among the equally clear ones (never over a core, an opening or a column)
        tag_at = _tag_at(level, outline, inside)
        level['rcTags'] = [{'x': tag_at['x'], 'y': tag_at['y'], 'thickness': level['thickness']}]
        level['levelTags'] = [{'x': inside['x'], 'y': inside['y'] - 400, 'label': 'T.O.C', 'value': js_str(level['tos'])}] if level.get('tos') is not None else []
        level['camber'] = level.get('camber') or []
        level['wallBarLengths'] = []
        # mesh: RAM designs the bands, not the mesh; the mesh of the specification is written in the office box
        mesh = spec.get('bottom') or R.DEFAULT_SPEC['bottom']
        level['meshSpec'] = [mesh['dia'], mesh['spacing']]
        # the slab mesh option: a bottom mesh only (default) or a mesh on both faces (spec.mesh = 'both'); the top mesh
        # takes its own diameter / spacing from the settings (spec.topMesh) or the bottom mesh's
        level['meshFaces'] = 'both' if (ospec.get('mesh') or spec.get('mesh')) == 'both' else 'bottom'
        level['topMesh'] = level['meshFaces'] == 'both'
        tmesh = spec.get('topMesh') or mesh
        level['topMeshSpec'] = [tmesh['dia'], tmesh['spacing']]
        same_mesh = tmesh['dia'] == mesh['dia'] and tmesh['spacing'] == mesh['spacing']
        b0 = bbox(outline)
        level['meshLabels'] = [{'x': b0['minX'] + 600, 'y': b0['maxY'] - 700, 'lines': [f"BOTTOM MESH T{fmt_num(mesh['dia'])}@{fmt_num(mesh['spacing'])}", f"TOP MESH T{fmt_num(tmesh['dia'])}@{fmt_num(tmesh['spacing'])}", 'TWO WAY'] if level['topMesh'] and not same_mesh else [f"MESH T{fmt_num(mesh['dia'])}@{fmt_num(mesh['spacing'])}", 'TOP & BOTTOM TWO WAY' if level['topMesh'] else 'BOTTOM TWO WAY']}]

        # designed bands → office items
        def at_boundary(p, level=level, outline=outline):
            if any(dist_to_polygon(p, R.region_polygon(o)) < 300 for o in (level.get('openings') or [])):
                return 'U'
            return R.edge_end_at(level, spec, p)['type'] if dist_to_polygon(p, outline) < (spec.get('cover') or 25) + 300 else False
        items = []
        tiny = 0
        # which RAM bands are drawn: 'all' (default), 'user' (only the engineer's own bars) or 'none' (office rules only)
        take = ospec.get('ramBands') or spec.get('ramBands') or 'all'
        ram_bands = (level.get('ram') or {}).get('bands') or []
        bands_in = [b for b in ram_bands if take == 'all' or (take == 'user' and b.get('designedBy') != 'program')]
        skipped = len(ram_bands) - len(bands_in)
        if skipped:
            A(level, f"{skipped} RAM {'program-generated' if take == 'user' else ''} bands of {level['name']} not drawn (spec.ramBands = \"{take}\").")
        for band in bands_in:
            n = band.get('count') or len(band['bars']) or 1
            centre = band['bars'][len(band['bars']) // 2] if band['bars'] else {'a': band['p0'], 'b': band['p1']}
            a, b = centre['a'], centre['b']
            if dist(a, b) < 1200:
                tiny += 1
                continue  # a "band" shorter than 1.2 m is an artefact of the individual-bar export, not a design
            u = unit(a, b)
            nn = perp(u)
            spacing = band['spacing'] if (band.get('spacing') or 0) > 0 else js_round(band['width'] / (n - 1)) if n > 1 else 0
            L = js_round(dist(a, b) / 10) * 10
            st = add(a, u, dist(a, b) * 0.35)
            half = max(band.get('width') or 0, 0) / 2
            # a close band reads as a spacing ("T16-150"), a few bars spread over a wide band as a count ("6T16")
            it = {'detail': None, 'ram': band.get('id'), 'face': band['face'], 'a': a, 'b': b,
                  'l1': f"T{fmt_num(band['dia'])}-{fmt_num(spacing)} ({band['face']})" if n > 1 and spacing and spacing <= 500 else f"{fmt_num(n)}T{fmt_num(band['dia'])} ({band['face']})",
                  'l2': f"L={fmt_num(L)}", 'side': 1, 'noTag': True}
            if half > 50:
                it['dist'] = {'p': add(st, nn, -half), 'q': add(st, nn, half)}
            if band['face'] == 'T':
                it['uEnd'] = {'start': at_boundary(a), 'end': at_boundary(b)}
            items.append(it)

        # office rule at the columns: one group each way, as long as the drop panel (or 4 m) and distributed over the
        # crossing group, is added by applyColumnRule; the RAM top bands over the columns are replaced by it
        def in_column_zone(it, level=level):
            for c in level.get('columns') or []:
                cc = {'x': c['cx'], 'y': c['cy']}
                drop = next((z for z in (level.get('thickZones') or []) if point_in_polygon(cc, z['polygon'])), None)
                m = mid(it['a'], it['b'])
                if drop and (point_in_polygon(m, drop['polygon']) or dist_to_polygon(m, drop['polygon']) < 300):
                    return True
                reach = max(c['d'] if c.get('shape') == 'circle' else max(c['w'], c['h']), 600) / 2 + 1200
                if dist_to_seg(cc, it['a'], it['b']) < reach and dist(m, cc) < 2500:
                    return True
            return False

        def in_drop(it, level=level):
            for z in level.get('thickZones') or []:
                b = bbox(z['polygon'])
                if max(b['w'], b['h']) <= ((spec.get('topColumns') or {}).get('dropMax') or 6000) and point_in_polygon(mid(it['a'], it['b']), z['polygon']) and dist(it['a'], it['b']) <= 1.2 * max(b['w'], b['h']):
                    return True
            return False
        replaced_b = [it for it in items if it['face'] == 'B' and in_drop(it)]
        for it in replaced_b:
            items.remove(it)
        if replaced_b:
            A(level, f"{len(replaced_b)} RAM bottom bands local to the drop panels of {level['name']} replaced by the detail 4 extra bottom bars.")
        replaced = [it for it in items if it['face'] == 'T' and in_column_zone(it)]
        for it in replaced:
            items.remove(it)
        if tiny:
            A(level, f"{tiny} RAM bands shorter than 1.2 m in {level['name']} ignored as export artefacts.")
        if replaced:
            A(level, f"{len(replaced)} RAM top bands over the columns of {level['name']} replaced by the office column bars (one group each way, the drop panel length / 4 m, distributed over the crossing group).")
        level['existing'] = {'lines': [], 'callouts': [], 'dims': [], 'dots': [], 'items': items}
        model['findings'].append(f"{level['id']} {level['name']}: {len(level['walls'])} walls, {len(level.get('thickZones') or [])} thickness zones, {len([e for e in level['edges'] if e.get('beam')])} of {len(level['edges'])} slab edges with an edge beam, RAM designed reinforcement: {len(items)} bands ({len([i for i in items if i['face'] == 'T'])} top, {len([i for i in items if i['face'] == 'B'])} bottom).")
        n_prog = len([i for i in items if (next((b for b in ram_bands if b.get('id') == i['ram']), None) or {}).get('designedBy') == 'program'])
        top_txt = f" and top mesh T{fmt_num(level['topMeshSpec'][0])}@{fmt_num(level['topMeshSpec'][1])}" if level['topMesh'] else ''
        src_txt = 'assumed' if (spec.get('sources') or {}).get('bottom') == 'assumed' or not spec.get('bottom') else 'from the settings'
        A(level, f"Reinforcement of {level['name']} is the RAM Concept design ({len(items)} bar bands drawn as designed, {n_prog} of them generated by the program for its design strips, {len(items) - n_prog} drawn by the engineer); the General Details additions are placed on top of it. Bottom mesh T{fmt_num(mesh['dia'])}@{fmt_num(mesh['spacing'])}{top_txt} {src_txt}{' (slab mesh option: both faces)' if level['topMesh'] else ' (slab mesh option: bottom only)'}.")
        if not level['walls']:
            A(level, f"No walls in the RAM model of {level['name']}: details 2 and 5 (core walls) not applied.")
        elif any(w.get('assumedT') for w in level['walls']):
            A(level, f"{len([w for w in level['walls'] if w.get('assumedT')])} walls of {level['name']} are line supports in RAM without a thickness: {fmt_num(wall_t)} mm assumed for the plan (set spec.wallThickness).")
    mark_joints(model, spec.get('cover') or 25)
    model['design'] = {'units': 'mm', 'source': 'RAM Concept'}
    return model


def _tag_at(level, outline, inside):
    """The slab tag place of prepareRamDesign (the JS IIFE `tagAt`)."""
    b = bbox(outline)
    obstacles = [poly for poly in (
        [rect_polygon({'x': c['cx'] - (c.get('w') or c.get('d') or 500) / 2, 'y': c['cy'] - (c.get('h') or c.get('d') or 500) / 2, 'w': c.get('w') or c.get('d') or 500, 'h': c.get('h') or c.get('d') or 500}) for c in (level.get('columns') or [])]
        + [w['polygon'] for w in (level.get('walls') or []) if w.get('polygon')]
        + [R.region_polygon(o) for o in (level.get('openings') or [])]
        + [z['polygon'] for z in (level.get('thickZones') or [])]
        + [ps['polygon'] for ps in (level.get('pourStrips') or [])]
    ) if poly and len(poly) >= 3]
    half_w, half_h = 1900, 700

    def clearance(p):
        if not point_in_polygon(p, outline):
            return -1
        m = min(dist_to_polygon(p, outline), 6000)
        for poly in obstacles:
            if point_in_polygon(p, poly):
                return -1
            m = min(m, dist_to_polygon(p, poly))
        return m
    best = None
    x = b['minX'] + half_w
    while x <= b['maxX'] - half_w:
        y = b['minY'] + half_h
        while y <= b['maxY'] - half_h:
            p = {'x': x, 'y': y}
            c = clearance(p)
            if c >= 0:
                score = min(c, 4000) - dist(p, inside) / 40  # clearance first (capped at 4 m), then nearness to the middle
                if not best or score > best['score']:
                    best = {'p': p, 'score': score}
            y += 1000
        x += 1000
    return best['p'] if best else inside


def mark_beams(level, spec, A=None):
    """
    Office rule for beams: any beam crossing the slab with slab on both sides (a normal beam, a wide band beam, a
    reinforced beam) carries a group of top bars across it, as long as 4 m or 1.5 m past each face, whichever is
    larger, distributed along the beam; the bars stop at an adjacent beam, an opening or the slab edge. A beam
    lying along the slab edge is an edge beam (the L-bars of detail 1 instead). A long thickened strip of the slab
    (longer than `topColumns.dropMax`, up to `beams.bandMaxWidth` wide) is a band beam and takes the same rule.
    """
    if A is None:
        def A(level, text):
            return None
    outline = level['outline']
    openings = [R.region_polygon(o) for o in (level.get('openings') or [])]
    walls = level.get('walls') or []

    def in_slab(p):
        return point_in_polygon(p, outline) and not any(point_in_polygon(p, poly) for poly in openings) and not any(w.get('polygon') and point_in_polygon(p, w['polygon']) for w in walls)
    band_max = (spec.get('beams') or {}).get('bandMaxWidth') or 3000
    drop_max = (spec.get('topColumns') or {}).get('dropMax') or 6000
    # long thickened strips are band beams
    for z in level.get('thickZones') or []:
        b = bbox(z['polygon'])
        long, short = max(b['w'], b['h']), min(b['w'], b['h'])
        if long <= drop_max or short > band_max or long < 3 * short:
            continue
        if any(bm.get('polygon') and point_in_polygon({'x': b['cx'], 'y': b['cy']}, bm['polygon']) for bm in level['beams']):
            continue
        along = {'x': 1, 'y': 0} if b['w'] >= b['h'] else {'x': 0, 'y': 1}
        level['beams'].append({'id': f"BB{z.get('id')}", 'a': add({'x': b['cx'], 'y': b['cy']}, along, -long / 2), 'b': add({'x': b['cx'], 'y': b['cy']}, along, long / 2), 't': short, 'depth': z.get('thickness'), 'polygon': z['polygon'], 'band': True})
    interior = 0
    for bm in level['beams']:
        if not bm.get('polygon'):
            continue
        u = unit(bm['a'], bm['b'])
        n = perp(u)
        m = mid(bm['a'], bm['b'])
        off = bm['t'] / 2 + 400
        bm['interior'] = in_slab(add(m, n, off)) and in_slab(add(m, n, -off))
        b = bbox(bm['polygon'])
        bm['cx'] = b['cx']
        bm['cy'] = b['cy']
        bm['w'] = b['w']
        bm['h'] = b['h']
        bm['along'] = 'x' if abs(u['x']) >= abs(u['y']) else 'y'
        if bm['interior']:
            interior += 1
    for i, bm in enumerate(level['beams']):
        if not bm.get('id'):
            bm['id'] = f'BM{i + 1}'
    if interior:
        tc = spec.get('topColumns') or {}
        lst = ', '.join(f"{b['id']} {js_round(b['t'])}{'x' + fmt_num(js_round(b['depth'])) if _t(b.get('depth')) else ''}{' BAND' if b.get('band') else ''}" for b in [b for b in level['beams'] if b.get('interior')][:8])
        A(level, f"{interior} beams cross the slab of {level['name']} with slab on both sides ({lst}{', ...' if interior > 8 else ''}): each carries top bars across it, {fmt_num((tc.get('length') or 4000) / 1000)} m or {fmt_num(_nn(tc.get('minBeyond'), 1500) / 1000)} m past each face whichever is larger, distributed along the beam, stopped at an adjacent beam, an opening or the slab edge.")
    return interior


def slab_edges(level, tol=20):
    """
    The slab edges for the perimeter rule: consecutive short facets of a curved edge (turning less
    than `tol` degrees) are merged into one run so a curve gets one call-out, not one per facet.
    """
    outline = level['outline']
    segs = []
    for i in range(len(outline)):
        a, b = outline[i], outline[(i + 1) % len(outline)]
        if dist(a, b) < 300:
            continue
        segs.append({'a': a, 'b': b, 'pts': [a, b]})
    if not segs:
        return []

    def turn(s1, s2):
        u, v = unit(s1['a'], s1['b']), unit(s2['a'], s2['b'])
        return (math.acos(max(-1, min(1, u['x'] * v['x'] + u['y'] * v['y']))) * 180) / math.pi
    merged = []
    for sg in segs:
        last = merged[-1] if merged else None
        if last and dist(last['b'], sg['a']) < 1 and turn({'a': last['pts'][-2], 'b': last['b']}, sg) < tol and (dist(sg['a'], sg['b']) < 2500 or dist(last['pts'][-2], last['b']) < 2500):
            last['b'] = sg['b']
            last['pts'].append(sg['b'])
            continue
        merged.append({'a': sg['a'], 'b': sg['b'], 'pts': list(sg['pts'])})
    # the last run may continue into the first one
    if len(merged) > 1:
        f, l = merged[0], merged[-1]
        if dist(l['b'], f['a']) < 1 and turn({'a': l['pts'][-2], 'b': l['b']}, f) < tol and (dist(f['a'], f['b']) < 2500 or dist(l['pts'][-2], l['b']) < 2500):
            l['b'] = f['b']
            l['pts'].extend(f['pts'][1:])
            merged.pop(0)
    return [{'a': e['a'], 'b': e['b'], 'pts': e['pts'], 'curved': len(e['pts']) > 2, 'beam': R.edge_has_beam(level, e['a'], e['b'])} for e in merged]


def apply_column_rule(level, spec, assumptions=None):
    """
    Office rule for the top bars over columns, applied to the design plan itself: at every column the
    designer's top bars crossing it take the office length (4 m both ways, or the drop panel + margins;
    at an edge column the U at the edge and 70 % on top), their "L=" call-outs are rewritten, and the
    bars of each direction are distributed over the length of the crossing bars: the designer's
    dimension across them is set to that length, or one is added where none was drawn. A column with
    no designer's bar in a direction gets the office bar added (`topColumns.addMissing: false` to skip).
    """
    if assumptions is None:
        assumptions = []
    ex = level.get('existing')
    if not ex or not (level.get('columns') or []):
        return {'changed': 0, 'added': []}
    s = spec['topColumns']
    if (s.get('rule') or 'office') != 'office':
        return {'changed': 0, 'added': []}
    res = R.top_at_columns(level, spec)

    def is_top(f):
        return f == 'T' or f == 'TB'

    def dim_dir(d):
        ang = math.atan2(d['y4'] - d['y3'], d['x4'] - d['x3']) if d.get('dimType') == 1 else ((d.get('rotation') or 0) * math.pi) / 180
        return {'x': math.cos(ang), 'y': math.sin(ang)}

    def dot(u, v):
        return u['x'] * v['x'] + u['y'] * v['y']
    added = []
    changed = added_dims = missing = rotated = 0
    for rc in res['columns']:
        col, per = rc['col'], rc['per']
        if col.get('isWall') and col.get('core'):
            continue  # a core wall keeps its U-bars; an isolated wall gets the column groups
        cc = {'x': col['cx'], 'y': col['cy']}
        # the two groups are perpendicular, along the column's own axes (a rotated column) or the tendon direction
        theta = _column_axis(level, col)
        if theta:
            rotated += 1
        U = {'x': {'x': math.cos(theta), 'y': math.sin(theta)}}
        U['y'] = perp(U['x'])

        def loc(p, U=U, cc=cc):
            return {'x': dot({'x': p['x'] - cc['x'], 'y': p['y'] - cc['y']}, U['x']), 'y': dot({'x': p['x'] - cc['x'], 'y': p['y'] - cc['y']}, U['y'])}

        def glob(lx, ly, U=U, cc=cc):
            return {'x': cc['x'] + U['x']['x'] * lx + U['y']['x'] * ly, 'y': cc['y'] + U['x']['y'] * lx + U['y']['y'] * ly}
        size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}

        def span(dir_, size=size, per=per):
            return {'lo': -size[dir_] / 2 - per[dir_]['ext'][-1], 'hi': size[dir_] / 2 + per[dir_]['ext'][1]}
        groups = {}
        for dir_ in ['x', 'y']:
            across = 'y' if dir_ == 'x' else 'x'
            # a beam gets its own group across it (the office beam rule) and leaves the designer's bars alone
            if col.get('isBeam'):
                groups[dir_] = []
                continue
            # the bars of this direction are spread over the crossing group's length: every parallel top bar within that
            # half-width of the column centre (and crossing the column along its length) belongs to the group
            half_band = max(size[across] / 2 + 400, 800, per[across]['straight'] / 2)

            def in_group(l, dir_=dir_, across=across, half_band=half_band):
                if not is_top(l.get('face')) or l.get('tick') or abs(dot(unit(l['a'], l['b']), U[dir_])) < 0.98:
                    return False
                A_, B_ = loc(l['a']), loc(l['b'])
                return abs(A_[across]) <= half_band and min(A_[dir_], B_[dir_]) < size[dir_] / 2 + 100 and max(A_[dir_], B_[dir_]) > -size[dir_] / 2 - 100
            groups[dir_] = [l for l in ex['lines'] if in_group(l)]
        for dir_ in ['x', 'y']:
            across = 'y' if dir_ == 'x' else 'x'
            p = per[dir_]
            sp = span(dir_)
            lo, hi = sp['lo'], sp['hi']

            def pt(along, t, dir_=dir_):
                return glob(along, t) if dir_ == 'x' else glob(t, along)
            if groups[dir_]:
                olds = [{'a': dict(l['a']), 'b': dict(l['b'])} for l in groups[dir_]]
                for l in groups[dir_]:
                    old = {'a': dict(l['a']), 'b': dict(l['b'])}
                    t = loc(l['a'])[across]
                    fwd = dot(unit(old['a'], old['b']), U[dir_]) > 0  # keep the bar's own direction so its call-out stays on the same side
                    l['a'] = pt(lo if fwd else hi, t)
                    l['b'] = pt(hi if fwd else lo, t)
                    l['uEnd'] = {'start': p['hookTypes'][-1] or False, 'end': p['hookTypes'][1] or False} if fwd else {'start': p['hookTypes'][1] or False, 'end': p['hookTypes'][-1] or False}
                    l['office'] = True
                    changed += 1
                # every length call-out next to any bar of the group (parallel bars share one call-out) now reads the office length
                for c in ex['callouts']:
                    if not re.search(r'^L\s*=\s*\d+', c['text'], re.I | re.A) or (c.get('rot') is not None and abs(dot({'x': math.cos((c['rot'] * math.pi) / 180), 'y': math.sin((c['rot'] * math.pi) / 180)}, U[dir_])) < 0.9):
                        continue
                    if any(dist_to_seg(c, o['a'], o['b']) < 600 for o in olds):
                        c['text'] = f"L={fmt_num(p['straight'])}"
                        c['office'] = True
            elif s.get('addMissing') is not False and not (col.get('isWall') and col.get('skipAlong') == dir_) and p['straight'] >= 1000:
                # (a long isolated wall gets the group across it only: its own reinforcement runs along it; a beam likewise;
                # a bar clipped to a stub, as at a column buried in an edge wall, is not drawn: the wall bars cover it)
                c_across = span(across)
                # the symbol beside the column stays within the group it stands for (the crossing bars' extent, which is
                # one-sided at an edge column), so the dot on its distribution dimension always lands on the dimension
                sgn = 1 if dir_ == 'x' else -1  # the bar's left normal points +across for an x bar and -across for a y bar

                def clamp_k(k, sgn=sgn, c_across=c_across):
                    return sgn * max(c_across['lo'] + 150, min(c_across['hi'] - 150, sgn * k))
                cands = list(dict.fromkeys(clamp_k(k) for k in _bar_offsets(spec, size[across], c_across['hi'] - c_across['lo'])))
                item = {'detail': None, 'face': 'T', 'a': pt(lo, 0), 'b': pt(hi, 0), 'l1': f"T{fmt_num(s['dia'])}-{fmt_num(s['spacing'])} (T)", 'l2': f"L={fmt_num(p['straight'])}", 'side': 1, 'noTag': True,
                        'uEnd': {'start': p['hookTypes'][-1] or False, 'end': p['hookTypes'][1] or False}, 'column': col.get('id'), 'dir': dir_, 'n': p['n'], 'length': p['length'], 'shape': p['shape'], 'posCands': cands, 'keep': cc}
                if col.get('isBeam'):
                    item['beam'] = col.get('id')
                added.append(item)
                groups[dir_] = [{'a': pt(lo, 0), 'b': pt(hi, 0), 'added': True, 'item': item}]
                missing += 1
        # the distribution of each direction = the crossing bars' extent
        for dir_ in ['x', 'y']:
            if not groups[dir_]:
                continue
            across = 'y' if dir_ == 'x' else 'x'
            c = {'lo': -size[across] / 2, 'hi': size[across] / 2} if col.get('isBeam') else span(across)  # the beam group is distributed along the beam itself
            sp = span(dir_)
            lo, hi = sp['lo'], sp['hi']

            def dim_in(d, across=across):
                if d.get('x3') is None or abs(dot(dim_dir(d), U[across])) < 0.9:
                    return False
                A_, B_ = loc({'x': d['x3'], 'y': d['y3']}), loc({'x': d['x4'], 'y': d['y4']})
                return _near({'x': (d['x3'] + d['x4']) / 2, 'y': (d['y3'] + d['y4']) / 2}, cc, 3000) and min(A_[across], B_[across]) < 300 and max(A_[across], B_[across]) > -300
            dims = [d for d in ex['dims'] if dim_in(d)]
            if dims:
                for d in dims:
                    A_, B_ = loc({'x': d['x3'], 'y': d['y3']}), loc({'x': d['x4'], 'y': d['y4']})
                    swap = A_[across] > B_[across]
                    P3 = glob(A_['x'], c['hi'] if swap else c['lo']) if dir_ == 'x' else glob(c['hi'] if swap else c['lo'], A_['y'])
                    P4 = glob(B_['x'], c['lo'] if swap else c['hi']) if dir_ == 'x' else glob(c['lo'] if swap else c['hi'], B_['y'])
                    d['x3'], d['y3'], d['x4'], d['y4'] = P3['x'], P3['y'], P4['x'], P4['y']
                    if theta:
                        d['dimType'] = 1
                        d['x'] = P3['x']
                        d['y'] = P3['y']
                    d['x2'] = d['y2'] = None
                    d['text'] = None
                    d['office'] = True
            elif groups[dir_][0].get('added'):
                # an added group carries its own distribution (drawn with the bar, the dot where the bar finally sits)
                # clear of the crossing bar beside the column; a beam's dimension goes on its other side, away from the
                # dimensions of the columns that sit on the beam axis
                # (at an edge column the dimension goes on the side where the bar runs into the slab, never off the edge)
                off = _nn(spec.get('barOffset'), 500) + 700
                minus, plus = max(lo + 200, -(size[dir_] / 2 + off)), min(hi - 200, size[dir_] / 2 + off)
                st = plus if col.get('isBeam') or per[dir_]['ext'][-1] < per[dir_]['ext'][1] else minus
                pA = glob(st, c['lo']) if dir_ == 'x' else glob(c['lo'], st)
                pB = glob(st, c['hi']) if dir_ == 'x' else glob(c['hi'], st)
                groups[dir_][0]['item']['dist'] = {'p': pA, 'q': pB}
                added_dims += 1
            else:
                st = lo + (hi - lo) * 0.35
                pA = glob(st, c['lo']) if dir_ == 'x' else glob(c['lo'], st)
                pB = glob(st, c['hi']) if dir_ == 'x' else glob(c['hi'], st)
                ex['dims'].append({'x3': pA['x'], 'y3': pA['y'], 'x4': pB['x'], 'y4': pB['y'], 'x': pA['x'], 'y': pA['y'], 'dimType': 1 if theta else 0, 'rotation': 0 if across == 'x' else 90, 'face': 'T', 'office': True})
                for l in groups[dir_]:
                    t = loc(l['a'])[across]
                    ex['dots'].append({**(glob(st, t) if dir_ == 'x' else glob(t, st)), 'face': 'T'})
                added_dims += 1
    beam_adds = len([it for it in added if it.get('beam')])
    if beam_adds:
        assumptions.append({'level': level['id'], 'text': f"Top bars across {beam_adds} interior beams of {level['name']}: T{fmt_num(s['dia'])}-{fmt_num(s['spacing'])}, {fmt_num(max(s.get('length') or 4000, 0) / 1000)} m or the beam width + 2 x {fmt_num(_nn(s.get('minBeyond'), 1500) / 1000)} m whichever is larger, distributed along the beam, shortened where the bar reaches an adjacent beam (to its far face), an opening or the slab edge (U)."})
    if changed or added:
        margin_txt = f" + {fmt_num(s['dropMargin'])} mm" if _t(s.get('dropMargin')) else ''
        assumptions.append({'level': level['id'], 'text': f"Top bars over columns set to the office rule in {level['name']}: {fmt_num(s.get('length') or 4000)} mm both ways (exactly the drop panel{margin_txt} where there is one), {js_round(_nn(s.get('edgeFactor'), 0.7) * 100)} % on top with the U at an edge, the two groups perpendicular along the column axis / tendon direction ({rotated} rotated columns); {changed} designer's bars re-lengthed, {missing} bars added where none was drawn, each direction distributed over the crossing bars' length ({added_dims} dimensions added)."})
    return {'changed': changed, 'added': added, 'addedDims': added_dims, 'missing': missing}


def _column_axis(level, col):
    """The axis (radians, 0 for an orthogonal column) the column's top bars follow: the column's own angle, else the nearest tendon within 2.5 m."""
    def norm(deg):
        d = math.fmod(math.fmod(deg, 90) + 90, 90)
        if d > 45:
            d -= 90
        return 0 if abs(d) < 2 else (d * math.pi) / 180
    if col.get('angle') is not None and norm(col['angle']):
        return norm(col['angle'])
    tendons = list((level.get('pt') or {}).get('tendons') or []) + list((level.get('ram') or {}).get('tendons') or [])
    best = None
    for t in tendons:
        pts = t.get('pts') or t.get('points') or []
        for i in range(len(pts) - 1):
            d = dist_to_seg({'x': col['cx'], 'y': col['cy']}, pts[i], pts[i + 1])
            if d < 2500 and (not best or d < best['d']):
                best = {'d': d, 'ang': (math.atan2(pts[i + 1]['y'] - pts[i]['y'], pts[i + 1]['x'] - pts[i]['x']) * 180) / math.pi}
    return norm(best['ang']) if best else 0


column_axis = _column_axis


def drop_column(level, spec, z):
    """The column of a drop panel: a thickened zone around one column, no larger than `topColumns.dropMax` (6 m); null for a strip / band."""
    b = bbox(z['polygon'])
    if max(b['w'], b['h']) > ((spec.get('topColumns') or {}).get('dropMax') or 6000):
        return None
    return next((c for c in (level.get('columns') or []) if point_in_polygon({'x': c['cx'], 'y': c['cy']}, z['polygon'])), None)


def _bar_offsets(spec, col_across, band_len):
    """
    Office rule: the bar symbol of a column group is drawn beside the column, not through its centre (a vertical bar
    half a metre to the left, a horizontal bar half a metre above), unless that place is taken by other bars or writing:
    the candidate offsets (along the bar's normal, +n = left of a vertical bar / above a horizontal one) in order.
    """
    off = _nn(spec.get('barOffset'), 500)
    k = min(col_across / 2 + off, max(0, band_len / 2 - 300))
    return [k, -k, js_round(k * 0.6), -js_round(k * 0.6), 0] if k > 0 else [0]


def _outside_openings(level, p, q, keep):
    """The part of the segment p->q that lies outside every opening and contains (or is nearest to) the point `keep`."""
    polys = [R.region_polygon(o) for o in (level.get('openings') or [])]
    if not polys:
        return [p, q]
    L = dist(p, q) or 1
    u = unit(p, q)
    ts = [0, 1]
    for poly in polys:
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            dx, dy, ex, ey = q['x'] - p['x'], q['y'] - p['y'], b['x'] - a['x'], b['y'] - a['y']
            den = dx * ey - dy * ex
            if abs(den) < 1e-9:
                continue
            t = ((a['x'] - p['x']) * ey - (a['y'] - p['y']) * ex) / den
            v = ((a['x'] - p['x']) * dy - (a['y'] - p['y']) * dx) / den
            if t > 0 and t < 1 and v >= 0 and v <= 1:
                ts.append(t)
    ts.sort()
    tk = max(0, min(1, ((keep['x'] - p['x']) * u['x'] + (keep['y'] - p['y']) * u['y']) / L))
    best = None
    for i in range(len(ts) - 1):
        t0, t1 = ts[i], ts[i + 1]
        if t1 - t0 < 1e-6:
            continue
        m = add(p, u, L * (t0 + t1) / 2)
        if any(point_in_polygon(m, poly) for poly in polys):
            continue
        d = t0 - tk if tk < t0 else tk - t1 if tk > t1 else 0
        if not best or d < best['d']:
            best = {'d': d, 't0': t0, 't1': t1}
    return [add(p, u, L * best['t0']), add(p, u, L * best['t1'])] if best else None


outside_openings = _outside_openings


def clip_at_openings(level, it, u_allow):
    """
    A bar never runs into an opening: it stops at the opening edge and ends there in a U (the piece at the column / the
    bar's own reference `keep` is kept); its written length and cutting length follow. Returns null when nothing is left.
    """
    if it.get('hairpin') or it.get('ind'):
        return it
    os_ = _outside_openings(level, it['a'], it['b'], it.get('keep') or mid(it['a'], it['b']))
    if not os_ or dist(os_[0], os_[1]) < 100:
        return None
    oA, oB = dist(os_[0], it['a']) > 1, dist(os_[1], it['b']) > 1
    if not oA and not oB:
        return it
    old_l, new_l = dist(it['a'], it['b']), dist(os_[0], os_[1])
    it['a'] = os_[0]
    it['b'] = os_[1]
    it['uEnd'] = {**(it.get('uEnd') or {})}
    if oA:
        it['uEnd']['start'] = 'U'
    if oB:
        it['uEnd']['end'] = 'U'
    if re.search(r'^L=\d+', it.get('l2') or '', re.A):
        it['l2'] = f"L={js_round(new_l + (it.get('extra') or 0))}"
    if _t(it.get('length')):
        it['length'] = js_round(it['length'] - (old_l - new_l) + ((1 if oA else 0) + (1 if oB else 0)) * u_allow)
    it['clippedOpening'] = True
    return it


def _clip_bend(level, it, longest):
    """
    A drop bar (D4) beside the slab edge or an opening: its rise and continuation past the drop are never drawn outside
    the slab or into the opening. The continuation is shortened to what lies in the slab; where nothing is left (the
    drop face is the slab edge / the opening edge) the bar simply ends at its run, with no leg, and the written length
    and the cutting length drop that rise and continuation.
    """
    u = unit(it['a'], it['b'])
    step = max(it['bend'].get('rise') or 50, 0)
    extra = _nn(it.get('extra'), 0)
    changed = False
    for end in ['A', 'B']:
        key = f'beyond{end}'
        beyond = _nn(it['bend'].get(key), _nn(it['bend'].get('beyond'), 500))
        if not (beyond > 0):
            continue
        e = it['a'] if end == 'A' else it['b']
        d = {'x': -u['x'], 'y': -u['y']} if end == 'A' else u
        far = add(e, d, beyond)
        # what the continuation keeps: inside the slab outline and outside every opening, measured from the bar's end
        in_slab = longest(e, far)
        kept = dist(in_slab[0], in_slab[1]) if in_slab and dist(in_slab[0], e) < 1 else 0
        if kept > 0:
            os_ = _outside_openings(level, e, add(e, d, kept), e)
            kept = dist(os_[0], os_[1]) if os_ and dist(os_[0], e) < 1 else 0
        if kept >= beyond - 1:
            continue
        if kept < 300:
            it['bend'][f'no{end}'] = True
            it['bend'][key] = 0
            extra -= step + beyond
            if it.get('uEnd'):
                it['uEnd']['start' if end == 'A' else 'end'] = False
        else:
            it['bend'][key] = math.floor(kept - 50)
            extra -= beyond - it['bend'][key]
        changed = True
    if not changed:
        return it
    delta = _nn(it.get('extra'), 0) - extra
    it['extra'] = max(0, extra)
    if re.search(r'^L=\d+', it.get('l2') or '', re.A):
        it['l2'] = f"L={js_round(dist(it['a'], it['b']) + it['extra'])}"
    if _t(it.get('length')):
        it['length'] = js_round(it['length'] - delta)
    it['bendClipped'] = True
    return it


clip_bend = _clip_bend


def clip_to_slab(level, items, spec=None):
    """Nothing is drawn outside the slab: bars and distribution lines are clipped to the outline (an item fully outside is dropped)."""
    spec = spec or {}
    outline = level['outline']
    u_allow = R.U_BOTTOM_LEG + (level['thickness'] - 2 * (spec.get('cover') or 25))  # what a U end adds to the cutting length

    def longest(a, b):
        parts = [s for s in clip_segment_to_polygon(a, b, outline) if dist(s[0], s[1]) > 50]
        parts = sorted(parts, key=lambda s: -dist(s[0], s[1]))
        return parts[0] if parts else None
    out = []
    # a cut that falls on a drawing joint with the neighbouring part is no cut: the slab (and the bar) continue there
    joints = level.get('jointEdges') or []

    def at_joint(p):
        return any(dist_to_seg(p, e['a'], e['b']) < 100 for e in joints)
    for it in items:
        # a column symbol that may still slide beside the column is judged where it will finally sit: when the slab
        # outline would cut it to a stub at the column axis (a column standing proud of an edge wall), it moves now to
        # the first candidate place where the bar lies in the slab, so the office length survives the clip
        if it.get('posCands') and len(it['posCands']) > 1:
            u0 = unit(it['a'], it['b'])
            n0 = perp(u0)
            L0 = dist(it['a'], it['b'])

            def kept_at(k, it=it, n0=n0):
                sg = longest(add(it['a'], n0, k), add(it['b'], n0, k))
                return dist(sg[0], sg[1]) if sg else 0
            if kept_at(0) < min(L0, 1000):
                k0 = next((k for k in it['posCands'] if kept_at(k) >= min(L0, 1000) - 1), None)
                if k0 is not None:
                    it['a'] = add(it['a'], n0, k0)
                    it['b'] = add(it['b'], n0, k0)
                    it['posCands'] = [k - k0 for k in it['posCands'] if kept_at(k) >= min(L0, 1000) - 1]
        seg = longest(it['a'], it['b'])
        if not seg:
            continue
        cut_a, cut_b = dist(seg[0], it['a']) > 1, dist(seg[1], it['b']) > 1
        if (cut_a and not at_joint(seg[0])) or (cut_b and not at_joint(seg[1])):
            old_l = dist(it['a'], it['b'])
            it['a'] = seg[0] if cut_a and not at_joint(seg[0]) else it['a']
            it['b'] = seg[1] if cut_b and not at_joint(seg[1]) else it['b']
            it['clipped'] = True
            # the written length follows the drawn bar (an edge drop's bar stops at the slab edge with its leg)
            new_l = dist(it['a'], it['b'])
            if re.search(r'^L=\d+', it.get('l2') or '', re.A):
                it['l2'] = f"L={js_round(new_l + (it.get('extra') or 0))}"
            if _t(it.get('length')):
                it['length'] = js_round(it['length'] - (old_l - new_l))
        if clip_at_openings(level, it, u_allow) is None:
            continue
        if it.get('bend'):
            _clip_bend(level, it, longest)
        if it.get('column') and dist(it['a'], it['b']) < 1000:
            continue  # a column bar cut to a stub between an opening and the edge is not worth drawing
        if it.get('dist'):
            ds = longest(it['dist']['p'], it['dist']['q'])
            if not ds or dist(ds[0], ds[1]) < 200:
                del it['dist']
            else:
                it['dist']['p'] = ds[0]
                it['dist']['q'] = ds[1]
                if it['dist'].get('textAt') and not point_in_polygon(it['dist']['textAt'], outline):
                    del it['dist']['textAt']
        # the distribution never runs into an opening: it stops before it (the piece at the bar is kept)
        if it.get('dist'):
            os_ = _outside_openings(level, it['dist']['p'], it['dist']['q'], mid(it['a'], it['b']))
            if not os_ or dist(os_[0], os_[1]) < 200:
                del it['dist']
            elif dist(os_[0], it['dist']['p']) > 1 or dist(os_[1], it['dist']['q']) > 1:
                it['dist']['p'] = os_[0]
                it['dist']['q'] = os_[1]
                it['dist'].pop('textAt', None)
        if it.get('ind'):
            kept = []
            for i in range(len(it['ind']) - 1):
                for p, q in clip_segment_to_polygon(it['ind'][i], it['ind'][i + 1], outline):
                    if dist(p, q) < 20:
                        continue
                    if kept and dist(kept[-1], p) < 1:
                        kept.append(q)
                    else:
                        kept.extend([p, q])
            it['ind'] = kept if len(kept) >= 2 else None
        out.append(it)
    return out


def _convex_hull(pts):
    """Convex hull (monotone chain) of a polygon's points."""
    P = sorted(pts, key=lambda p: (p['x'], p['y']))
    if len(P) < 3:
        return P

    def cross(o, a, b):
        return (a['x'] - o['x']) * (b['y'] - o['y']) - (a['y'] - o['y']) * (b['x'] - o['x'])
    lower = []
    for p in P:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(P):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


convex_hull = _convex_hull


def mark_core_walls(level):
    """
    Office rule: a concrete wall is treated like a column for the top bars over it, unless it belongs to a
    core: three or more wall faces (of one or several walls) around an opening. Marks `w.core`.
    """
    walls = [w for w in (level.get('walls') or []) if w.get('polygon')]
    for w in walls:
        w['core'] = False
    for o in level.get('openings') or []:
        poly = R.region_polygon(o)
        faces_at = []
        for w in walls:
            for i in range(len(w['polygon'])):
                a, b = w['polygon'][i], w['polygon'][(i + 1) % len(w['polygon'])]
                if dist(a, b) < 800:
                    continue
                if dist_to_polygon(mid(a, b), poly) < 400:
                    faces_at.append(w)
        if len(set(id(w) for w in faces_at)) + len(faces_at) >= 4 and len(faces_at) >= 3:
            for w in faces_at:
                w['core'] = True
    # a single U / L shaped wall polygon wrapping a void (a stair or lift core drawn as one outline) is a core as well
    for w in walls:
        if w['core']:
            continue
        hull = _convex_hull(w['polygon'])
        enclosed = abs(polygon_area(hull)) - abs(polygon_area(w['polygon']))
        if len(w['polygon']) >= 6 and enclosed > 1e6 and enclosed > 0.5 * abs(polygon_area(w['polygon'])):
            w['core'] = True
    # a wall running along the slab edge is a retaining wall: detail 2 (slab edge at any core or retaining wall) applies,
    # the wall U-bars along its inner face, not the column groups
    for w in walls:
        if w['core'] or not w.get('a') or not w.get('b') or not level.get('outline'):
            continue
        L = dist(w['a'], w['b'])
        if L < 1000:
            continue
        on_edge = 0
        for k in range(9):
            if dist_to_polygon(add(w['a'], unit(w['a'], w['b']), (L * k) / 8), level['outline']) < (w.get('t') or 250) / 2 + 300:
                on_edge += 1
        if on_edge >= 5:
            w['core'] = True
            w['retaining'] = True
    n = len([w for w in walls if w['core']])
    return {'core': n, 'isolated': len(walls) - n, 'retaining': len([w for w in walls if w.get('retaining')])}


def _merge_wall_segments(walls, tol=5):
    """Chained wall segments (RAM line supports drawn as short pieces) joined into straight walls."""
    out = []
    rest = [dict(w) for w in walls]
    while rest:
        w = rest.pop(0)
        grew = True
        while grew:
            grew = False
            for i in range(len(rest)):
                o = rest[i]
                u, v = unit(w['a'], w['b']), unit(o['a'], o['b'])
                ang = (math.acos(max(-1, min(1, abs(u['x'] * v['x'] + u['y'] * v['y'])))) * 180) / math.pi
                if ang > tol:
                    continue
                ends = [[w['b'], o['a'], ('b', o['b'])], [w['b'], o['b'], ('b', o['a'])], [w['a'], o['a'], ('a', o['b'])], [w['a'], o['b'], ('a', o['a'])]]
                hit = next((e for e in ends if dist(e[0], e[1]) < 50), None)
                if not hit:
                    continue
                w[hit[2][0]] = hit[2][1]
                rest.pop(i)
                grew = True
                break
        out.append(w)
    return out


merge_wall_segments = _merge_wall_segments


def _next_label(label, used):
    letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if re.search(r'^\d+$', label, re.A):
        n = int(label)
        while str(n) in used:
            n += 1
        return str(n)
    i = letters.find(label.upper())
    if i < 0:
        return label + "'"
    while letters[i] in used:
        i = (i + 1) % 26
    return letters[i]


def _scale_ent(e, k):
    c = {**e, 'x': e['x'] * k, 'y': e['y'] * k}
    if e.get('x2') is not None:
        c['x2'] = e['x2'] * k
        c['y2'] = e['y2'] * k
    if e.get('x3') is not None:
        c['x3'] = e['x3'] * k
        c['y3'] = e['y3'] * k
    if e.get('x4') is not None:
        c['x4'] = e['x4'] * k
        c['y4'] = e['y4'] * k
    if e.get('pts'):
        c['pts'] = [{**p, 'x': p['x'] * k, 'y': p['y'] * k} for p in e['pts']]
    if e.get('paths'):
        c['paths'] = [[{'x': p['x'] * k, 'y': p['y'] * k} for p in path] for path in e['paths']]
    if e.get('r') is not None:
        c['r'] = e['r'] * k
    if e.get('height') is not None:
        c['height'] = e['height'] * k
    if e.get('measure') is not None:
        c['measure'] = e['measure'] * k
    return c


# ------------------------------------------------------------------ the General Details rules
def design_additions(level, spec, opts=None):
    """
    Reinforcement the General Details add to the designer's plan, as drawable
    items in the office convention plus a bar list per face.
    """
    if any(w.get('polygon') and 'core' not in w for w in (level.get('walls') or [])):
        mark_core_walls(level)
    items = []
    bars = {'T': R.BarList('DT'), 'B': R.BarList('DB')}
    notes = []
    assumptions = []
    cover = spec.get('cover') or 25
    h = level['thickness']
    outline = level['outline']
    has_ram = level.get('ram') is not None  # (JS: `level.ram` is truthy for any object, an empty one included)

    def in_slab(p):
        return point_in_polygon(p, outline) and not any(point_in_polygon(p, w.get('polygon') or []) for w in (level.get('walls') or [])) and not any(point_in_polygon(p, R.region_polygon(o)) for o in (level.get('openings') or []))

    def add_bar(face, e):
        f = 'B' if face == 'B' else 'T'
        bars[f].add(e)
        if face == 'TB':
            bars['B'].add(e)

    def blocked_along(a, b):
        # parts of the edge a->b covered by columns or walls (as intervals of t along the edge)
        u, L = unit(a, b), dist(a, b)
        cuts = []
        for c in level['columns']:
            poly = R.region_polygon({'kind': 'circle', 'cx': c['cx'], 'cy': c['cy'], 'r': c['d'] / 2}) if c.get('shape') == 'circle' else rect_polygon({'x': c['cx'] - c['w'] / 2, 'y': c['cy'] - c['h'] / 2, 'w': c['w'], 'h': c['h']})
            if any(dist_to_seg(p, a, b) < 300 for p in poly) or dist_to_seg({'x': c['cx'], 'y': c['cy']}, a, b) < max(c['w'], c['h']):
                ts = [(p['x'] - a['x']) * u['x'] + (p['y'] - a['y']) * u['y'] for p in poly]
                cuts.append([min(ts) - 100, max(ts) + 100])
        for w in level.get('walls') or []:
            if any(dist_to_seg(p, a, b) < 300 for p in w['polygon']):
                ts = [(p['x'] - a['x']) * u['x'] + (p['y'] - a['y']) * u['y'] for p in w['polygon']]
                cuts.append([min(ts) - 100, max(ts) + 100])
        return {'runs': _subtract([[0, L]], cuts), 'u': u, 'L': L}

    # ---- perimeter rule (office): T12@150 between the column top bars along every edge; a symmetric U of 4 m at
    # a free edge, an L of the same 4 m (400 down into the beam + 3600 on top) where the edge carries a beam (detail 1 / detail 6)
    su = spec['uEdge']
    web = h - 2 * cover
    u_leg_top = ceil_to((su['total'] - web) / 2, 10)
    # the column / wall bar groups along the edge decide where the perimeter bars stop (the U-bars run before and after them)
    tc_res = R.top_at_columns(level, spec)

    def band_of(c, dir_):
        r = next((x for x in tc_res['columns'] if x['col'].get('id') == c.get('id') or any(m.get('id') == c.get('id') for m in (x['col'].get('merged') or []))), None)
        if not r:
            return 0
        g = max(r['per']['x']['straight'], r['per']['y']['straight']) if dir_ == 'across' else r['per'][dir_]['straight']
        return g

    # where a bar symbol goes along an opening side: the middle of the longest run free of the column / beam groups that
    # reach the side (so it never sits on the group of top bars across a beam alongside the opening)
    def side_symbol_at(a, bb):
        u, Ls = unit(a, bb), dist(a, bb)
        runs = R.edge_runs_between_columns(level, a, bb, h, band_of)
        if runs:
            best = None
            for r in runs:
                if not best or r[1] - r[0] > best[1] - best[0]:
                    best = r
            t1, t2 = best
            return add(a, u, (t1 + t2) / 2)
        # the whole side lies within a group's band: the point farthest from the group's own bar symbols (the support centres)
        centres = [(c['x'] - a['x']) * u['x'] + (c['y'] - a['y']) * u['y'] for c in
                   [{'x': c['cx'], 'y': c['cy']} for c in level['columns']] + [{'x': bm['cx'], 'y': bm['cy']} for bm in (level.get('beams') or []) if bm.get('interior')]]
        cands = [{'t': f * Ls, 'd': min([abs(t - f * Ls) for t in centres] + [1e9])} for f in [0.25, 0.5, 0.75]]
        best = sorted(cands, key=lambda p: -p['d'])[0]
        return add(a, u, best['t'])

    # consecutive slab edges of one kind (free / beam) form one chain: one long indication line and one bar symbol
    # every `perimSpan` along the whole chain, instead of a symbol per facet
    # (an edge with a retaining wall along it carries the wall U-bars of detail 2 instead)
    for e in level.get('edges') or []:
        if e.get('wall') is None:
            e['wall'] = any(w.get('retaining') for w in (level.get('walls') or [])) and R.side_lining(level, e['a'], e['b']) == 'wall'
    edges_in = [x for x in (level.get('edges') or []) if not x.get('joint') and not x['wall']]
    chains = []
    for e in edges_in:
        last = chains[-1] if chains else None
        if last and last['beam'] == bool(e.get('beam')) and dist(last['pts'][-1], e['a']) < 1:
            last['pts'].extend((e.get('pts') or [e['a'], e['b']])[1:])
            continue
        chains.append({'beam': bool(e.get('beam')), 'pts': list(e.get('pts') or [e['a'], e['b']])})
    if len(chains) > 1:
        f, l = chains[0], chains[-1]
        if f['beam'] == l['beam'] and dist(l['pts'][-1], f['pts'][0]) < 1:
            l['pts'].extend(f['pts'][1:])
            chains.pop(0)
    for e in chains:
        pts = e['pts']
        facets = []
        s0 = 0
        for i in range(len(pts) - 1):
            L = dist(pts[i], pts[i + 1])
            if L < 1:
                continue
            facets.append({'a': pts[i], 'b': pts[i + 1], 's0': s0, 'L': L})
            s0 += L
        if not facets:
            continue

        def at(sv, facets=facets):
            f = next((x for x in facets if sv <= x['s0'] + x['L']), None) or facets[-1]
            u = unit(f['a'], f['b'])
            return {'p': add(f['a'], u, sv - f['s0']), 'u': u, 'f': f}
        runs = []
        for f in facets:
            for t1, t2 in R.edge_runs_between_columns(level, f['a'], f['b'], h, band_of):
                last = runs[-1] if runs else None
                if last and abs(last[1] - (f['s0'] + t1)) < 1:
                    last[1] = f['s0'] + t2
                else:
                    runs.append([f['s0'] + t1, f['s0'] + t2])

        # the bar schedule counts every run between the column bars ...
        def zone_of(t1, t2, at=at):
            return grid_ref(level, bbox([at(t1)['p'], at(t2)['p']]))
        for t1, t2 in runs:
            ln = t2 - t1
            if ln < 2 * su['spacing']:
                continue
            count = math.floor(ln / su['spacing']) + 1
            if e['beam']:
                add_bar('T', {'dia': su['dia'], 'shape': f"L {fmt_num(su['beamLeg'])}+{fmt_num(su['beamTop'])}", 'length': su['beamLeg'] + su['beamTop'], 'qty': count, 'spacing': su['spacing'], 'zone': f"D1 EDGE BEAM {zone_of(t1, t2)}"})
            else:
                add_bar('T', {'dia': su['dia'], 'shape': f"U {fmt_num(u_leg_top)}/{fmt_num(web)}/{fmt_num(u_leg_top)}", 'length': su['total'], 'qty': count, 'spacing': su['spacing'], 'zone': f"D6 FREE EDGE {zone_of(t1, t2)}"})
        # ... and the plan shows one bar symbol per run between supports, on each facet the run crosses: every symbol
        # carries its own distribution dimension (the run on that facet, 350 inside the edge) with the dot where the
        # bar crosses it - the office rule that no bar is drawn without its distribution dimension
        if not runs:
            continue
        k = 0
        for run in runs:
            for f in facets:
                s1, s2 = max(run[0], f['s0']), min(run[1], f['s0'] + f['L'])
                if s2 - s1 < max(800, 2 * su['spacing']):
                    continue
                sv = (s1 + s2) / 2
                mm = at(sv)
                n_in = _inward(f['a'], f['b'], outline)
                zone = zone_of(s1, s2)
                dd = {'p': add(at(s1)['p'], n_in, PERIM_DIM_IN), 'q': add(at(s2)['p'], n_in, PERIM_DIM_IN)}
                if e['beam']:
                    items.append({'detail': 'D1', 'face': 'T', 'a': mm['p'], 'b': add(mm['p'], n_in, su['beamTop']), 'l1': f"T{fmt_num(su['dia'])}-{fmt_num(su['spacing'])} LBAR (T)", 'l2': f"L={fmt_num(su['beamLeg'] + su['beamTop'])}", 'dist': dd, 'side': 1, 'zone': zone, 'legEnd': 'start', 'noTag': k > 0})
                else:
                    items.append({'detail': 'D6', 'face': 'TB', 'a': mm['p'], 'b': add(mm['p'], n_in, u_leg_top), 'l1': f"T{fmt_num(su['dia'])}-{fmt_num(su['spacing'])} U-BAR", 'l2': f"L={fmt_num(su['total'])}", 'dist': dd, 'side': 1, 'zone': zone, 'hairpin': True, 'noTag': k > 0})
                k += 1

    # ---- D2 core walls: U-bars T12@200 + 10T12 (T&B) along the wall face
    lc = ceil_to(h - cover, 10)
    no_la = []
    for w in [x for x in (level.get('walls') or []) if x.get('core')]:  # core walls only: an isolated wall is reinforced like a column
        poly = w['polygon']
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            L = dist(a, b)
            if L < 1500:
                continue
            u = unit(a, b)
            n = perp(u)
            # slab side of this face: the side where a point 600 mm away lies in the slab
            m = mid(a, b)
            # (a point inside the hull of a U / L shaped wall is the core it encloses, not the slab)
            hull = _convex_hull(poly)

            # the face must open directly onto the slab: just off the face (150) is neither wall nor core, and 600 away is slab
            def slab_side(sg, m=m, n=n, poly=poly, hull=hull):
                q = add(m, n, sg * 150)
                return not point_in_polygon(q, poly) and not point_in_polygon(q, hull) and in_slab(add(m, n, sg * 600))
            dir_out = 1 if slab_side(1) else -1 if slab_side(-1) else 0
            if not dir_out:
                continue
            n_out = {'x': n['x'] * dir_out, 'y': n['y'] * dir_out}
            # LA follows the designer's wall top bar length next to this face when there is one
            la_list = sorted([t for t in (level.get('wallBarLengths') or []) if dist_to_seg(t, a, b) < 2500 and in_slab(add(m, n_out, 300))], key=lambda p: -p['L'])
            la0 = la_list[0] if la_list else None
            LA = la0['L'] if la0 else 1200
            count = math.floor(L / 200) + 1
            # the distribution along the wall face: 700 into the slab, else further in, else over the wall itself, whichever is free of writing
            # the U-bar starts inside the wall at the opening (core) face, passes through the wall and runs LA into the slab
            tw = js_round((w.get('t') or 250) / 10) * 10
            items.append({'detail': 'D2', 'face': 'TB', 'a': add(m, n_out, -tw), 'b': add(m, n_out, LA), 'l1': 'T12-200 U-BAR', 'l2': f"L={fmt_num(LA + tw + 1200 + lc)}", 'ind': [add(a, n_out, PERIM_DIM_IN), add(b, n_out, PERIM_DIM_IN)], 'hairpin': True, 'side': 1, 'zone': f"{w['id']} {grid_ref(level, bbox(poly))}"})
            add_bar('T', {'dia': 12, 'shape': f"U {fmt_num(LA + tw)}/{fmt_num(lc)}/1200", 'length': LA + tw + 1200 + lc, 'qty': count, 'spacing': 200, 'zone': f"D2 {w['id']}"})
            # the 10T12 (T&B) parallel bars of detail 2 only when asked for (office practice: the wall face gets the U-bars only)
            if (spec.get('walls') or {}).get('parallelBars'):
                par = min(12000, js_round(L + 1200))
                items.append({'detail': 'D2', 'face': 'TB', 'a': add(add(a, n_out, 400), u, -600), 'b': add(add(b, n_out, 400), u, 600), 'l1': '10T12 (T&B)', 'l2': f"L={fmt_num(par)}", 'side': -1, 'noTag': True})
                add_bar('T', {'dia': 12, 'shape': 'STR', 'length': par, 'qty': 5, 'zone': f"D2 {w['id']}"})
                add_bar('B', {'dia': 12, 'shape': 'STR', 'length': par, 'qty': 5, 'zone': f"D2 {w['id']}"})
            if not la0 and w['id'] not in no_la:
                no_la.append(w['id'])

    if no_la:
        assumptions.append(f"D2 AT {', '.join(no_la)}: NO DESIGNER'S WALL BAR LENGTH FOUND NEXT TO THE FACE; LA = 1200 mm USED." if len(no_la) <= 3 else f"D2 WALL U-BARS: LA = 1200 mm USED AT {len(no_la)} WALL FACES (NO DESIGNER'S WALL BAR LENGTH NEXT TO THEM).")

    # ---- D3 / D4 thickness zones: the bottom mesh inside a column drop is T12@150 (`spec.drops`), drawn as the two D4
    # groups through the column: each group as long as the drop (4 m without one), at least `minBeyond` past the column
    # face, distributed over the crossing group's length; the bar symbol sits beside the column (a vertical bar to its
    # left, a horizontal one above it) unless that place is taken
    sd = spec.get('drops') or R.DEFAULT_SPEC['drops']
    sc = spec.get('topColumns') or R.DEFAULT_SPEC['topColumns']
    for z in level.get('thickZones') or []:
        b = bbox(z['polygon'])
        notes.append({'x': b['cx'], 'y': b['maxY'] + 350, 'text': f"LAP 500 TYP. AT {js_str(z['thickness']) if _t(z.get('thickness')) else 'THK.'} / {fmt_num(h)} STEP (DET.3)"})
        col = drop_column(level, spec, z)
        if col:
            cc = {'x': col['cx'], 'y': col['cy']}
            size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}
            ln = {}
            for dir_ in ['x', 'y']:
                ln[dir_] = max(ceil_to(b['w'] if dir_ == 'x' else b['h'], 10), ceil_to(size[dir_] + 2 * _nn(sc.get('minBeyond'), 1500), 10))
            zone = f"D4 {z.get('id')} {grid_ref(level, b)}"
            for dir_ in ['x', 'y']:
                across = 'y' if dir_ == 'x' else 'x'
                L, W = ln[dir_], ln[across]
                a = {'x': cc['x'] - L / 2, 'y': cc['y']} if dir_ == 'x' else {'x': cc['x'], 'y': cc['y'] - L / 2}
                bb = {'x': cc['x'] + L / 2, 'y': cc['y']} if dir_ == 'x' else {'x': cc['x'], 'y': cc['y'] + L / 2}
                # the distribution line crosses the bar beside the column, over the crossing group's length
                s0 = max(-L / 2 + 200, -(size[dir_] / 2 + _nn(spec.get('barOffset'), 500) + 700))  # clear of the crossing bar beside the column
                dp = {'x': cc['x'] + s0, 'y': cc['y'] - W / 2} if dir_ == 'x' else {'x': cc['x'] - W / 2, 'y': cc['y'] + s0}
                dq = {'x': cc['x'] + s0, 'y': cc['y'] + W / 2} if dir_ == 'x' else {'x': cc['x'] + W / 2, 'y': cc['y'] + s0}
                # the drop bar (office rule): the bottom run stops `bendCover` (50) short of each drop face, rises with a
                # 90° bend over the step and continues `leg` (500) at the slab bottom to lap with the slab bottom bars (or
                # further when the office length reaches beyond the drop); its length counts the two rises and continuations
                step = max(50, (z.get('thickness') or h) - h)
                cov = _nn(sd.get('bendCover'), 50)
                z_lo = b['minX'] if dir_ == 'x' else b['minY']
                z_hi = b['maxX'] if dir_ == 'x' else b['maxY']
                c0 = cc['x'] if dir_ == 'x' else cc['y']
                run_a, run_b = min(z_lo + cov, c0 - 200), max(z_hi - cov, c0 + 200)
                cont_a = max(sd.get('leg') or 500, ceil_to(max(0, z_lo - (c0 - L / 2)), 10))
                cont_b = max(sd.get('leg') or 500, ceil_to(max(0, c0 + L / 2 - z_hi), 10))
                pa = {'x': run_a, 'y': cc['y']} if dir_ == 'x' else {'x': cc['x'], 'y': run_a}
                pb = {'x': run_b, 'y': cc['y']} if dir_ == 'x' else {'x': cc['x'], 'y': run_b}
                run = js_round(run_b - run_a)
                extra = 2 * step + cont_a + cont_b
                total = run + extra
                items.append({'detail': 'D4', 'face': 'B', 'a': pa, 'b': pb, 'l1': f"T{fmt_num(sd['dia'])}-{fmt_num(sd['spacing'])} (B)", 'l2': f"L={fmt_num(total)}", 'dist': {'p': dp, 'q': dq}, 'posCands': _bar_offsets(spec, size[across], W), 'side': 1, 'zone': zone, 'noTag': dir_ == 'y', 'keep': cc, 'bend': {'rise': step, 'beyondA': cont_a, 'beyondB': cont_b}, 'extra': extra})
                add_bar('B', {'dia': sd['dia'], 'shape': f"BEND90 {fmt_num(step)}+{fmt_num(max(cont_a, cont_b))}", 'length': total, 'qty': math.floor(W / sd['spacing']) + 1, 'spacing': sd['spacing'], 'zone': f"{zone} {dir_.upper()}"})
            continue
        # a thickened zone without a column (a strip, a band): extra bottom bars over the zone, 50 dia beyond it (detail 4)
        # (the bottom run stops `bendCover` short of the zone faces, rises with a 90° bend and continues 50 dia at the slab bottom)
        ext = 50 * sd['dia']
        cov_z = _nn(sd.get('bendCover'), 50)
        run_x = {'a': {'x': b['minX'] + cov_z, 'y': b['minY'] + b['h'] * 0.42}, 'b': {'x': b['maxX'] - cov_z, 'y': b['minY'] + b['h'] * 0.42}}
        run_y = {'a': {'x': b['minX'] + b['w'] * 0.62, 'y': b['minY'] + cov_z}, 'b': {'x': b['minX'] + b['w'] * 0.62, 'y': b['maxY'] - cov_z}}
        Lx, Ly = js_round(run_x['b']['x'] - run_x['a']['x']), js_round(run_y['b']['y'] - run_y['a']['y'])
        step_z = max(50, (z.get('thickness') or h) - h)
        extra_z = 2 * (step_z + ext)
        items.append({'detail': 'D4', 'face': 'B', 'a': run_x['a'], 'b': run_x['b'], 'l1': f"T{fmt_num(sd['dia'])}-{fmt_num(sd['spacing'])} (B) EXTRA", 'l2': f"L={fmt_num(Lx + extra_z)}", 'dist': {'p': {'x': b['minX'] + b['w'] * 0.35, 'y': b['minY']}, 'q': {'x': b['minX'] + b['w'] * 0.35, 'y': b['maxY']}}, 'side': 1, 'zone': f"{z.get('id')} {grid_ref(level, b)}", 'bend': {'rise': step_z, 'beyondA': ext, 'beyondB': ext}, 'extra': extra_z})
        items.append({'detail': 'D4', 'face': 'B', 'a': run_y['a'], 'b': run_y['b'], 'l1': f"T{fmt_num(sd['dia'])}-{fmt_num(sd['spacing'])} (B) EXTRA", 'l2': f"L={fmt_num(Ly + extra_z)}", 'dist': {'p': {'x': b['minX'], 'y': b['minY'] + b['h'] * 0.72}, 'q': {'x': b['maxX'], 'y': b['minY'] + b['h'] * 0.72}}, 'side': -1, 'noTag': True, 'bend': {'rise': step_z, 'beyondA': ext, 'beyondB': ext}, 'extra': extra_z})
        add_bar('B', {'dia': sd['dia'], 'shape': f"BEND90 {fmt_num(step_z)}+{fmt_num(ext)}", 'length': Lx + extra_z, 'qty': math.floor(b['h'] / sd['spacing']) + 1, 'spacing': sd['spacing'], 'zone': f"D4 {z.get('id')}"})
        add_bar('B', {'dia': sd['dia'], 'shape': f"BEND90 {fmt_num(step_z)}+{fmt_num(ext)}", 'length': Ly + extra_z, 'qty': math.floor(b['w'] / sd['spacing']) + 1, 'spacing': sd['spacing'], 'zone': f"D4 {z.get('id')}"})

    # ---- D5 corners: convex wall corners inside the slab (3T16) and re-entrant slab corners (3T12)
    def corner(c, bis, dia, zone):
        dir_ = perp(bis)
        ctr = add(c, bis, 350)
        dn, st = perp(dir_), add(ctr, dir_, -450)
        items.append({'detail': 'D5', 'face': 'TB', 'a': add(ctr, dir_, -1000), 'b': add(ctr, dir_, 1000), 'l1': f"3T{fmt_num(dia)}-200 (T&B)", 'l2': 'L=2000', 'dist': {'p': add(st, dn, -200), 'q': add(st, dn, 200)}, 'side': 1, 'zone': zone, 'triple': True})
        add_bar('T', {'dia': dia, 'shape': 'STR', 'length': 2000, 'qty': 3, 'spacing': 200, 'zone': zone})
        add_bar('B', {'dia': dia, 'shape': 'STR', 'length': 2000, 'qty': 3, 'spacing': 200, 'zone': zone})
    for w in ((level.get('walls') or []) if (spec.get('walls') or {}).get('cornerDiagonals') else []):  # wall-corner diagonals (detail 5) only when asked for
        poly = w['polygon']  # CCW
        for i in range(len(poly)):
            p0, p1, p2 = poly[(i + len(poly) - 1) % len(poly)], poly[i], poly[(i + 1) % len(poly)]
            u1, u2 = unit(p0, p1), unit(p1, p2)
            cross = u1['x'] * u2['y'] - u1['y'] * u2['x']
            if cross <= 0.2:
                continue  # only convex corners of the wall
            bis = unit({'x': 0, 'y': 0}, {'x': u1['x'] - u2['x'], 'y': u1['y'] - u2['y']})  # outward bisector
            if not in_slab(add(p1, bis, 400)):
                continue
            corner(p1, bis, 16, f"D5 {w['id']} CORNER")
    for i in range(len(outline)):
        p0, p1, p2 = outline[(i + len(outline) - 1) % len(outline)], outline[i], outline[(i + 1) % len(outline)]
        if dist(p0, p1) < 300 or dist(p1, p2) < 300:
            continue
        u1, u2 = unit(p0, p1), unit(p1, p2)
        cross = u1['x'] * u2['y'] - u1['y'] * u2['x']
        if cross >= -0.2:
            continue  # re-entrant corner of a CCW outline turns right
        if any(any(_near(p, p1, 400) for p in w['polygon']) for w in (level.get('walls') or [])):
            continue  # wall corners handled above
        bis = unit({'x': 0, 'y': 0}, {'x': u1['x'] - u2['x'], 'y': u1['y'] - u2['y']})  # at a re-entrant corner this bisector points into the slab
        if not in_slab(add(p1, bis, 400)):
            continue
        corner(p1, bis, 12, f"D5 SLAB CORNER {grid_ref(level, bbox([p1]))}")

    # ---- D7 MEP voids (openings not lined by walls)
    for o in level.get('openings') or []:
        poly = R.region_polygon(o)
        b = bbox(poly)
        # a RAM model without wall supports: an opening of shaft size (both sides >= `shaftMin`, 1.5 m) is a lift / stair
        # shaft whose walls are not modelled: no trimmers, the perimeter U-bars (T12@150, 4 m) along its sides instead
        # (a lift / stair shaft is walled in reality even when the RAM model has no wall there)
        shaft = min(b['w'], b['h']) >= ((spec.get('openings') or {}).get('shaftMin') or 1500) and has_ram and not R.opening_lined(level, o)
        if shaft:
            su = spec['uEdge']
            u_leg = ceil_to((su['total'] - (h - 2 * cover)) / 2, 10)
            sides_p = R.region_polygon(o)
            k = 0
            for i in range(len(sides_p)):
                a, bb = sides_p[i], sides_p[(i + 1) % len(sides_p)]
                if dist(a, bb) < 600:
                    continue
                lining = R.side_lining(level, a, bb)
                if lining == 'wall' or lining == 'column':
                    continue  # the wall U-bars of detail 2 cover this side
                u = unit(a, bb)
                n = perp(u)
                m = side_symbol_at(a, bb)
                n_out = n if in_slab(add(m, n, 700)) else {'x': -n['x'], 'y': -n['y']} if in_slab(add(m, n, -700)) else None
                if not n_out:
                    continue
                if lining == 'beam':
                    items.append({'detail': 'D1', 'face': 'T', 'a': m, 'b': add(m, n_out, su['beamTop']), 'l1': f"T{fmt_num(su['dia'])}-{fmt_num(su['spacing'])} LBAR (T)", 'l2': f"L={fmt_num(su['beamLeg'] + su['beamTop'])}", 'ind': [add(a, n_out, PERIM_DIM_IN), add(bb, n_out, PERIM_DIM_IN)], 'side': 1, 'zone': f"D1 {o.get('id')}", 'legEnd': 'start', 'noTag': k > 0})
                    add_bar('T', {'dia': su['dia'], 'shape': f"L {fmt_num(su['beamLeg'])}+{fmt_num(su['beamTop'])}", 'length': su['beamLeg'] + su['beamTop'], 'qty': math.floor(dist(a, bb) / su['spacing']) + 1, 'spacing': su['spacing'], 'zone': f"D1 SHAFT {o.get('id')} {grid_ref(level, b)}"})
                    k += 1
                    continue
                items.append({'detail': 'D6', 'face': 'TB', 'a': m, 'b': add(m, n_out, u_leg), 'l1': f"T{fmt_num(su['dia'])}-{fmt_num(su['spacing'])} U-BAR", 'l2': f"L={fmt_num(su['total'])}", 'ind': [add(a, n_out, PERIM_DIM_IN), add(bb, n_out, PERIM_DIM_IN)], 'side': 1, 'zone': f"D6 {o.get('id')}", 'hairpin': True, 'noTag': k > 0})
                add_bar('T', {'dia': su['dia'], 'shape': f"U {fmt_num(u_leg)}/{fmt_num(h - 2 * cover)}/{fmt_num(u_leg)}", 'length': su['total'], 'qty': math.floor(dist(a, bb) / su['spacing']) + 1, 'spacing': su['spacing'], 'zone': f"D6 SHAFT {o.get('id')} {grid_ref(level, b)}"})
                k += 1
            assumptions.append(f"{o.get('id')} ({grid_ref(level, b)}, {to_fixed(b['w'] / 1000, 1)} x {to_fixed(b['h'] / 1000, 1)} m) TAKEN AS A LIFT / STAIR SHAFT: NO TRIMMERS, U-BARS T{fmt_num(su['dia'])}@{fmt_num(su['spacing'])} (L-BARS AT A BEAM, THE WALL U-BARS AT A WALL) ALONG ITS SIDES; IF IT IS AN OPEN MEP VOID, SWITCH TO DETAIL 7.")
            continue
        if R.opening_lined(level, o):
            # enclosed opening: no trimmers; an L-bar (400 into the beam + `beamTop` on top) along every side that runs
            # along a beam, like the slab edge (the wall U-bars of detail 2 cover the sides along walls)
            nL = 0
            outer_sides = R.region_polygon(o)  # CCW: the slab is on the right-hand side of each edge... checked with inSlab below
            for i in range(len(outer_sides)):
                a, bb = outer_sides[i], outer_sides[(i + 1) % len(outer_sides)]
                if dist(a, bb) < 600 or R.side_lining(level, a, bb) != 'beam':
                    continue
                u = unit(a, bb)
                n = perp(u)
                m = side_symbol_at(a, bb)
                n_out = n if in_slab(add(m, n, 700)) else {'x': -n['x'], 'y': -n['y']} if in_slab(add(m, n, -700)) else None
                if not n_out:
                    continue
                su = spec['uEdge']
                count = math.floor(dist(a, bb) / su['spacing']) + 1
                items.append({'detail': 'D1', 'face': 'T', 'a': m, 'b': add(m, n_out, su['beamTop']), 'l1': f"T{fmt_num(su['dia'])}-{fmt_num(su['spacing'])} LBAR (T)", 'l2': f"L={fmt_num(su['beamLeg'] + su['beamTop'])}", 'ind': [add(a, n_out, PERIM_DIM_IN), add(bb, n_out, PERIM_DIM_IN)], 'side': 1, 'zone': f"D1 {o.get('id')}", 'legEnd': 'start', 'noTag': nL > 0})
                add_bar('T', {'dia': su['dia'], 'shape': f"L {fmt_num(su['beamLeg'])}+{fmt_num(su['beamTop'])}", 'length': su['beamLeg'] + su['beamTop'], 'qty': count, 'spacing': su['spacing'], 'zone': f"D1 OPENING {o.get('id')} {grid_ref(level, b)}"})
                nL += 1
            assumptions.append(f"D7 NOT ADDED AT {o.get('id')} ({grid_ref(level, b)}): OPENING ENCLOSED BY CONCRETE WALLS / BEAMS - NO ADDITIONAL TRIMMERS (OFFICE RULE); {f'L-BARS ALONG ITS {nL} BEAM SIDES' if nL else 'WALL U-BARS PER DETAIL 2'}.")
            continue
        # the designer already trimmed this opening (T&B call-outs next to it): keep the design, do not add detail 7
        if any(c.get('face') == 'TB' and dist_to_polygon(c, poly) < 800 for c in ((level.get('existing') or {}).get('callouts') or [])):
            assumptions.append(f"D7 NOT ADDED AT {o.get('id')} ({grid_ref(level, b)}): THE DESIGN PLAN ALREADY TRIMS THIS OPENING (T&B BARS).")
            continue
        size = max(b['w'], b['h']) / 1000
        row = next((r for r in VOID_TABLE if size <= r['max']), None) or VOID_TABLE[-1]
        if size > 2.5:
            assumptions.append(f"D7 APPLIED AT {o.get('id')} ({grid_ref(level, b)}, {to_fixed(b['w'] / 1000, 1)} x {to_fixed(b['h'] / 1000, 1)} m) AS AN MEP VOID; IF THIS IS A LIFT / STAIR SHAFT WITH ITS OWN DETAIL, DELETE THE ADDED BARS.")
        zone = f"D7 {o.get('id')} {grid_ref(level, b)}"
        rect = {'x': b['minX'], 'y': b['minY'], 'w': b['w'], 'h': b['h']}
        sides = [
            {'a': {'x': rect['x'], 'y': rect['y'] - 150}, 'b': {'x': rect['x'] + rect['w'], 'y': rect['y'] - 150}, 'n': {'x': 0, 'y': -1}},
            {'a': {'x': rect['x'] + rect['w'] + 150, 'y': rect['y']}, 'b': {'x': rect['x'] + rect['w'] + 150, 'y': rect['y'] + rect['h']}, 'n': {'x': 1, 'y': 0}},
            {'a': {'x': rect['x'], 'y': rect['y'] + rect['h'] + 150}, 'b': {'x': rect['x'] + rect['w'], 'y': rect['y'] + rect['h'] + 150}, 'n': {'x': 0, 'y': 1}},
            {'a': {'x': rect['x'] - 150, 'y': rect['y']}, 'b': {'x': rect['x'] - 150, 'y': rect['y'] + rect['h']}, 'n': {'x': -1, 'y': 0}},
        ]
        lb = 800 if row['u']['dia'] >= 16 else 600
        # three groups: G1 parallel to the lettered grids (the sides along X), G2 parallel to the numbered grids, G3 the 45° diagonals crossing both
        for i, s in enumerate(sides):
            L = max(1500, js_round(dist(s['a'], s['b']) + 1200))
            u = unit(s['a'], s['b'])
            grp = 'G1 (X)' if abs(u['y']) < 0.5 else 'G2 (Y)'
            st = add(s['a'], u, dist(s['a'], s['b']) * 0.35)
            items.append({'detail': 'D7', 'face': 'TB', 'a': add(s['a'], u, -600), 'b': add(s['b'], u, 600), 'l1': f"{fmt_num(row['long']['n'])}T{fmt_num(row['long']['dia'])}-{fmt_num(row['long']['s'])} (T&B)", 'l2': f"L={fmt_num(L)}", 'dist': {'p': st, 'q': add(st, s['n'], (row['long']['n'] - 1) * row['long']['s'])}, 'side': 1, 'zone': zone, 'noTag': i > 0})
            add_bar('T', {'dia': row['long']['dia'], 'shape': 'STR', 'length': L, 'qty': row['long']['n'], 'spacing': row['long']['s'], 'zone': f"{zone} {grp}"})
            add_bar('B', {'dia': row['long']['dia'], 'shape': 'STR', 'length': L, 'qty': row['long']['n'], 'spacing': row['long']['s'], 'zone': f"{zone} {grp}"})
            m = mid(s['a'], s['b'])
            count = math.floor(dist(s['a'], s['b']) / row['u']['s']) + 1
            if i < 2:
                items.append({'detail': 'D7', 'face': 'TB', 'a': add(m, s['n'], -150), 'b': add(m, s['n'], lb), 'l1': f"T{fmt_num(row['u']['dia'])}-{fmt_num(row['u']['s'])} U-BAR", 'l2': f"LB={fmt_num(lb)}", 'dist': {'p': add(s['a'], s['n'], lb * 0.75), 'q': add(s['b'], s['n'], lb * 0.75)}, 'side': -1, 'noTag': True})
            add_bar('T', {'dia': row['u']['dia'], 'shape': f"U {fmt_num(lb)}/{fmt_num(lc)}/{fmt_num(lb)}", 'length': 2 * lb + lc, 'qty': count, 'spacing': row['u']['s'], 'zone': zone})
        d = 1000 / math.sqrt(2)
        for cx, cy, sx, sy in [[b['minX'], b['minY'], -1, -1], [b['maxX'], b['minY'], 1, -1], [b['maxX'], b['maxY'], 1, 1], [b['minX'], b['maxY'], -1, 1]]:
            ctr = {'x': cx + sx * 250, 'y': cy + sy * 250}
            dir_ = {'x': sx, 'y': -sy}
            items.append({'detail': 'D7', 'face': 'TB', 'a': {'x': ctr['x'] - dir_['x'] * d, 'y': ctr['y'] - dir_['y'] * d}, 'b': {'x': ctr['x'] + dir_['x'] * d, 'y': ctr['y'] + dir_['y'] * d}, 'l1': f"T{fmt_num(row['diag'])} 45° (T&B)", 'l2': 'L=2000', 'side': 1, 'noTag': True})
        add_bar('T', {'dia': row['diag'], 'shape': 'DIAG 45', 'length': 2000, 'qty': 4, 'zone': f"{zone} G3 (45°)"})
        add_bar('B', {'dia': row['diag'], 'shape': 'DIAG 45', 'length': 2000, 'qty': 4, 'zone': f"{zone} G3 (45°)"})

    # ---- D8 pour (infill) strips: the office's pour strip detail (PT details 3): T12@200 straight bars 2 m long top
    # and bottom lapping across each joint, U-bars T12@200 (2400 total) closed at each face with the legs into the
    # slab, T12@150 along the strip top and bottom (fixed before the infill pour)
    sp8 = spec.get('pourStrip') or R.DEFAULT_SPEC['pourStrip']
    for ps in level.get('pourStrips') or []:
        b = bbox(ps['polygon'])
        along = {'x': 1, 'y': 0} if b['w'] >= b['h'] else {'x': 0, 'y': 1}
        acr = perp(along)
        Ls, Ws = max(b['w'], b['h']), min(b['w'], b['h'])
        c = {'x': b['cx'], 'y': b['cy']}
        ref = grid_ref(level, b)
        zone = f"D8 {ps.get('id')} {ref}"
        n_across = math.floor(Ls / sp8['spacing']) + 1

        # a strip cast against a retaining wall (a wall along one of its long faces) takes the office's wall variant
        # ("reinforcement details of pour strip with retaining wall"): U-bars T12@200 from the wall face, U-bars 2 m from
        # the slab side, T16@200 across, 7T16 top and bottom along the strip, bonding agent at the joint faces
        def face_of(sg, c=c, along=along, acr=acr, Ls=Ls, Ws=Ws):
            return [add(add(c, along, -Ls / 2), acr, sg * Ws / 2), add(add(c, along, Ls / 2), acr, sg * Ws / 2)]
        wall_sg = _nn(next((sg for sg in [-1, 1] if R.side_lining(level, *face_of(sg)) == 'wall'), None), 0)
        sw = sp8.get('wall') or {}
        # straight bars across the strip, top and bottom, one symbol at 35 % along (slid along the strip where a column
        # bar already sits there), distributed over the strip length
        at = add(c, along, -Ls * 0.15)
        slide = max(0, Ls / 2 - 600)
        pos_cands = [max(-slide, min(slide, k)) for k in [0, -Ls * 0.15, Ls * 0.15, -Ls * 0.3, Ls * 0.3, -Ls * 0.4, Ls * 0.4]]
        dist_p, dist_q = add(c, along, -Ls / 2), add(c, along, Ls / 2)
        d_off = (Ws / 2 + 400) * (-wall_sg if wall_sg else 1)  # the distribution on the slab side, never over the wall
        n_across_w = math.floor(Ls / (sw.get('spacing') or sp8['spacing'])) + 1 if wall_sg else n_across
        web = h - 2 * cover
        if wall_sg:
            # against a retaining wall (office detail): T12 @ 200 top and bottom, L = 2000, from the wall face into the slab
            wd, wsp, wl = sw.get('dia') or 12, sw.get('spacing') or 200, sw.get('length') or 2000
            face = add(at, acr, wall_sg * Ws / 2)
            inward_ = {'x': -wall_sg * acr['x'], 'y': -wall_sg * acr['y']}
            items.append({'detail': 'D8', 'face': 'TB', 'a': face, 'b': add(face, inward_, wl), 'l1': f"T{fmt_num(wd)}-{fmt_num(wsp)} TOP&BOTTOM", 'l2': f"L={fmt_num(wl)}", 'dist': {'p': add(dist_p, acr, d_off), 'q': add(dist_q, acr, d_off)}, 'side': 1, 'zone': zone, 'keep': at, 'posCands': pos_cands})
            add_bar('T', {'dia': wd, 'shape': 'STR', 'length': wl, 'qty': n_across_w, 'spacing': wsp, 'zone': zone})
            add_bar('B', {'dia': wd, 'shape': 'STR', 'length': wl, 'qty': n_across_w, 'spacing': wsp, 'zone': zone})
        else:
            # the office's internal pour strip detail: on each side of the strip one set of T12 @ 200 TOP & BOTTOM
            # L = 2000 lapping across the joint (from the far face of the strip, across it and into the slab on this
            # side), drawn as the pair at its own station, its dot on the distribution line of its side
            stations = {-1: -Ls * 0.3, 1: -Ls * 0.1}
            for sg in [-1, 1]:
                st_at = add(c, along, stations[sg])
                far = add(st_at, acr, -sg * Ws / 2)
                out = {'x': sg * acr['x'], 'y': sg * acr['y']}
                # the symbol may slide along the strip (clear of a column bar): candidates about its station, within the strip
                rel = [max(-slide, min(slide, stations[sg] + f * Ls)) - stations[sg] for f in [0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3]]
                cands = [(k if sg < 0 else -k) for k in dict.fromkeys(rel)]  # the bar's normal points +along on the -1 side, -along on the +1 side
                items.append({'detail': 'D8', 'face': 'TB', 'a': far, 'b': add(far, out, sp8['length']), 'l1': f"T{fmt_num(sp8['dia'])}-{fmt_num(sp8['spacing'])} TOP & BOTTOM", 'l2': f"L={fmt_num(sp8['length'])}", 'dist': {'p': add(dist_p, acr, sg * (Ws / 2 + 400)), 'q': add(dist_q, acr, sg * (Ws / 2 + 400))}, 'pairOff': 60, 'side': 1, 'zone': zone, 'keep': st_at, 'posCands': cands})
                add_bar('T', {'dia': sp8['dia'], 'shape': 'STR', 'length': sp8['length'], 'qty': n_across, 'spacing': sp8['spacing'], 'zone': zone})
                add_bar('B', {'dia': sp8['dia'], 'shape': 'STR', 'length': sp8['length'], 'qty': n_across, 'spacing': sp8['spacing'], 'zone': zone})
        # U-bars at each face of the strip, one symbol per face at 65 % along: an internal strip has the U closed at
        # the joint face with its legs out into the slab (`uTotal`, 2400: the office detail); at a wall the U sits in
        # the wall and comes out into the strip (`wall.uTotal`, 2500), the slab-side U straddles the joint (`wall.uSlab`, 2 m)
        at_u = add(c, along, Ls * 0.2)
        for sg in [-1, 1]:
            total = ((sw.get('uTotal') or sp8['uTotal']) if sg == wall_sg else (sw.get('uSlab') or 2000)) if wall_sg else sp8['uTotal']
            u_leg_s = ceil_to((total - web) / 2, 10)
            face = add(at_u, acr, sg * Ws / 2)
            leg_dir = {'x': -sg * acr['x'], 'y': -sg * acr['y']}  # into the strip
            u_dist = None
            if wall_sg and sg == wall_sg:
                # the U-bar at the wall sits inside the wall (anchored in it) and comes out into the strip; its closed end
                # one wall thickness behind the face (as deep as the leg allows)
                wall = next((w for w in (level.get('walls') or []) if w.get('polygon') and any(dist_to_seg(pp, *face_of(sg)) < 300 for pp in w['polygon'])), None)
                into = min((wall or {}).get('t') or 250, max(0, u_leg_s - 400))
                face = add(face, leg_dir, -into)
            elif wall_sg:
                # the U-bar from the slab side straddles the joint: half its leg in the slab, half in the strip
                face = add(face, leg_dir, -u_leg_s / 2)
            else:
                # internal strip: closed at the face, the legs out into the slab, the dot on this side's distribution line
                leg_dir = {'x': sg * acr['x'], 'y': sg * acr['y']}
                u_dist = {'p': add(dist_p, acr, sg * (Ws / 2 + 400)), 'q': add(dist_q, acr, sg * (Ws / 2 + 400))}
            items.append({'detail': 'D8', 'face': 'TB', 'a': face, 'b': add(face, leg_dir, u_leg_s), 'l1': f"T{fmt_num(sp8['uDia'])}-{fmt_num(sp8['uSpacing'])} U-BAR{' (WALL)' if wall_sg and sg == wall_sg else ''}", 'l2': f"L={fmt_num(total)}", 'hairpin': True, 'side': 1, 'zone': zone, 'noTag': True, 'dist': u_dist})
            add_bar('T', {'dia': sp8['uDia'], 'shape': f"U {fmt_num(u_leg_s)}/{fmt_num(web)}/{fmt_num(u_leg_s)}", 'length': total, 'qty': math.floor(Ls / sp8['uSpacing']) + 1, 'spacing': sp8['uSpacing'], 'zone': f"{zone} U{' WALL' if wall_sg and sg == wall_sg else ''}"})
        # longitudinal bars along the strip, top and bottom, fixed before the infill pour (7T16 each layer at a wall)
        long_dia = (sw.get('longDia') or sp8['longDia']) if wall_sg else sp8['longDia']
        long_spacing = (sw.get('longSpacing') or (None if sw.get('longCount') else sp8['longSpacing'])) if wall_sg else sp8['longSpacing']
        n_long = math.floor(Ws / long_spacing) + 1 if long_spacing else sw.get('longCount') or 7
        long_label = f"T{fmt_num(long_dia)}-{fmt_num(long_spacing)} (T&B) ALONG STRIP" if long_spacing else f"{fmt_num(n_long)}T{fmt_num(long_dia)} (T&B) ALONG STRIP"
        # the bars along the strip come in stock lengths lapped (never one 27 m bar): the plan writes the strip length and the pieces
        lap_l = R.lap_length(spec, long_dia)
        pieces = R.split_run(Ls, {'stock': spec.get('stock') or R.DEFAULT_SPEC.get('stock') or 12000, 'lap': lap_l})
        Lw = ceil_to(Ls, 10)
        items.append({'detail': 'D8', 'face': 'TB', 'a': add(c, along, -Ls / 2), 'b': add(c, along, Ls / 2), 'l1': long_label, 'l2': f"L={fmt_num(Lw)} ({len(pieces)} PCS, LAP {fmt_num(lap_l)})" if len(pieces) > 1 else f"L={fmt_num(Lw)}", 'dist': {'p': add(add(c, along, Ls * 0.4), acr, -Ws / 2), 'q': add(add(c, along, Ls * 0.4), acr, Ws / 2)}, 'side': -1, 'zone': zone, 'noTag': True})
        counts = {}
        for ln in pieces:
            counts[ln] = (counts.get(ln) or 0) + 1
        for ln, qty in counts.items():
            add_bar('TB', {'dia': long_dia, 'shape': 'STR', 'length': ln, 'qty': n_long * qty, 'spacing': long_spacing or None, 'zone': f"{zone} ALONG{f' (LAP {fmt_num(lap_l)})' if len(pieces) > 1 else ''}"})
        if wall_sg:
            assumptions.append(f"D8 AT {ps.get('id')} ({ref}): {js_round(Ws)} WIDE POUR STRIP, {to_fixed(Ls / 1000, 1)} m LONG, CAST AGAINST A RETAINING WALL - OFFICE DETAIL: U-BARS T{fmt_num(sp8['uDia'])}@{fmt_num(sp8['uSpacing'])} L={fmt_num(sw.get('uTotal') or sp8['uTotal'])} ANCHORED IN THE WALL AND OUT INTO THE STRIP, U-BARS T{fmt_num(sp8['uDia'])}@{fmt_num(sp8['uSpacing'])} L={fmt_num(sw.get('uSlab') or 2000)} FROM THE SLAB SIDE, T{fmt_num(sw.get('dia') or 12)}@{fmt_num(sw.get('spacing') or 200)} L={fmt_num(sw.get('length') or 2000)} TOP & BOTTOM FROM THE WALL FACE INTO THE SLAB, {long_label} (T&B); BONDING AGENT ON THE JOINT FACES; PROPS AND THE POUR SEQUENCE PER THE PT DESIGNER.")
        else:
            assumptions.append(f"D8 AT {ps.get('id')} ({ref}): {js_round(Ws)} WIDE POUR STRIP, {to_fixed(Ls / 1000, 1)} m LONG - OFFICE DETAIL: T{fmt_num(sp8['dia'])}@{fmt_num(sp8['spacing'])} L={fmt_num(sp8['length'])} TOP & BOTTOM LAPPING ACROSS EACH JOINT (FROM THE FAR FACE OF THE STRIP INTO THE SLAB), U-BARS T{fmt_num(sp8['uDia'])}@{fmt_num(sp8['uSpacing'])} L={fmt_num(sp8['uTotal'])} CLOSED AT EACH FACE WITH THE LEGS INTO THE SLAB, T{fmt_num(sp8['longDia'])}@{fmt_num(sp8['longSpacing'])} T&B ALONG IT FIXED BEFORE THE INFILL POUR; PROPS AND THE POUR SEQUENCE PER THE PT DESIGNER.")

    # ---- D9 blockwork support beam through the void between two openings: a strip of the slab between two openings
    # (150 min, up to `blockBeam.maxGap`) with no beam and no concrete wall in it carries the blockwork above as a beam:
    # 2T20 top and bottom along the strip, TA (tension anchorage) beyond each void end, T12@200 links along the strip
    bb9 = spec.get('blockBeam') or R.DEFAULT_SPEC['blockBeam']
    TA = R.development_length(spec, bb9['dia'], {'top': True})
    ops = [{'o': o, 'b': bbox(R.region_polygon(o))} for o in (level.get('openings') or [])]
    for i in range(len(ops)):
        for j in range(i + 1, len(ops)):
            A_, B_ = ops[i]['b'], ops[j]['b']
            for axis in ['x', 'y']:
                lo, hi, olo, ohi = ['minX', 'maxX', 'minY', 'maxY'] if axis == 'x' else ['minY', 'maxY', 'minX', 'maxX']
                gap = max(A_[lo] - B_[hi], B_[lo] - A_[hi])
                if gap < bb9['minWidth'] or gap > bb9['maxGap']:
                    continue
                s0, s1 = max(A_[olo], B_[olo]), min(A_[ohi], B_[ohi])
                if s1 - s0 < 300:
                    continue  # the openings do not face each other
                g0 = B_[hi] if A_[lo] - B_[hi] > 0 else A_[hi]
                gm = g0 + gap / 2
                pA = {'x': gm, 'y': s0} if axis == 'x' else {'x': s0, 'y': gm}
                pB = {'x': gm, 'y': s1} if axis == 'x' else {'x': s1, 'y': gm}
                u = unit(pA, pB)
                if R.side_lining(level, pA, pB):
                    continue  # a beam or a concrete wall between the openings carries the blockwork
                if not all(in_slab(add(pA, u, dist(pA, pB) * t)) for t in [0.15, 0.5, 0.85]):
                    continue
                a, b_end = add(pA, u, -TA), add(pB, u, TA)
                L, Ls = js_round(dist(a, b_end)), js_round(dist(pA, pB))
                ref = grid_ref(level, bbox([pA, pB]))
                zone = f"D9 {ops[i]['o'].get('id')}/{ops[j]['o'].get('id')} {ref}"
                n_links = math.floor(Ls / bb9['linkSpacing']) + 1
                lw, ld = js_round(gap - 2 * cover), h - 2 * cover
                items.append({'detail': 'D9', 'face': 'TB', 'a': a, 'b': b_end, 'l1': f"{fmt_num(bb9['count'])}T{fmt_num(bb9['dia'])} (T&B) + T{fmt_num(bb9['linkDia'])}-{fmt_num(bb9['linkSpacing'])} LINKS", 'l2': f"L={fmt_num(L)}", 'dist': {'p': pA, 'q': pB}, 'pairOff': min(120, gap / 2 - cover), 'side': 1, 'zone': zone, 'blockBeam': {'gap': gap, 'ta': TA}})
                add_bar('TB', {'dia': bb9['dia'], 'shape': 'STR', 'length': L, 'qty': bb9['count'], 'zone': zone})
                add_bar('T', {'dia': bb9['linkDia'], 'shape': f"LINK {fmt_num(lw)}x{fmt_num(ld)}", 'length': ceil_to(2 * (lw + ld) + 20 * bb9['linkDia'], 10), 'qty': n_links, 'spacing': bb9['linkSpacing'], 'zone': zone, 'note': 'LINKS'})
                assumptions.append(f"D9 AT {ops[i]['o'].get('id')} / {ops[j]['o'].get('id')} ({ref}): {js_round(gap)} mm STRIP BETWEEN THE TWO OPENINGS WITH NO BEAM / WALL - BLOCKWORK SUPPORT BEAM {fmt_num(bb9['count'])}T{fmt_num(bb9['dia'])} T&B (TA = {fmt_num(TA)} BEYOND EACH VOID) WITH T{fmt_num(bb9['linkDia'])}@{fmt_num(bb9['linkSpacing'])} LINKS; DELETE IF NO BLOCKWORK STANDS ON THIS STRIP.")

    # ---- D12 punching: the office PS detail (stirrup strips "rows - legs - T12" leaving every column face, rows at S)
    # with a RAM model only at the columns RAM designed stud rails for (the rails' length and stud area converted:
    # rows cover the longest rail, the legs match the rail area per face); without a punching design PS1 / PS2 placeholders
    punching = []
    sp = spec.get('punching') or R.DEFAULT_SPEC['punching']
    ps_dia, ps_s = sp.get('psDia') or 12, sp.get('rowSpacing') or 100
    leg_area = (math.pi * ps_dia * ps_dia) / 4
    ssr_sets = (level.get('ram') or {}).get('ssr') or []
    # the engineer's bypass: columns flagged by the punching check (not passing in RAM / by the indicative estimate) get the
    # office detail anyway, sized from the estimate, at the design engineer's responsibility (spec.punching.override)
    override = sp['override'] if sp.get('override') and (sp['override'].get('by') or sp['override'].get('columns')) else None
    override_ids = override_columns(level.get('punchingCheck'), override) if override else set()
    overridden = []
    for c in level['columns']:
        w = c['d'] if c.get('shape') == 'circle' else c['w']
        hh = c['d'] if c.get('shape') == 'circle' else c['h']
        set_ = next((st for st in ssr_sets if abs(st['loc']['x'] - c['cx']) < max(w, hh) and abs(st['loc']['y'] - c['cy']) < max(w, hh)), None)
        ov = next((k for k in ((level.get('punchingCheck') or {}).get('columns') or []) if js_str(k.get('id')).upper() == js_str(c.get('id')).upper()), None) if not set_ and js_str(c.get('id')).upper() in override_ids else None
        if has_ram and not set_ and not ov:
            continue  # RAM: no stud rails at this column = no punching reinforcement required
        dirs = {}
        if ov:
            det = ov.get('detail') or {'rows': 10 if ov.get('loc') == 'interior' else 12, 'legs': 4}
            edge = dist_to_polygon({'x': c['cx'], 'y': c['cy']}, outline) < max(w, hh) + 200
            dirs['x'] = dirs['y'] = {'rows': det['rows'], 'legs': det['legs'], 'sides': [-1, 1]}
            overridden.append({'col': c, 'check': ov, 'edge': edge})
        elif set_:
            per = {'x': {'len': 0}, 'y': {'len': 0}}
            by_side = {}
            for r in set_['rails']:
                dx, dy = r['b']['x'] - r['a']['x'], r['b']['y'] - r['a']['y']
                dir_ = 'x' if abs(dx) >= abs(dy) else 'y'
                per[dir_]['len'] = max(per[dir_]['len'], js_hypot(dx, dy))
                side = f"{dir_}{_sign(dx if dir_ == 'x' else dy)}"
                by_side[side] = (by_side.get(side) or 0) + 1
            for dir_ in ['x', 'y']:
                rails = max(by_side.get(f'{dir_}1') or 0, by_side.get(f'{dir_}-1') or 0)
                rows = max(2, math.ceil(per[dir_]['len'] / ps_s))
                legs = max(4, 2 * math.ceil((rails * set_['studArea']) / leg_area / 2))
                dirs[dir_] = {'rows': rows, 'legs': legs, 'sides': [sg for sg in [-1, 1] if by_side.get(f'{dir_}{sg}')]}  # an edge column has no rails towards the edge
        else:
            edge = dist_to_polygon({'x': c['cx'], 'y': c['cy']}, outline) < max(w, hh) + 200
            dirs['x'] = dirs['y'] = {'rows': 12 if edge else 10, 'legs': 4, 'sides': [-1, 1]}
        short = 'x' if w <= hh else 'y'
        long = 'y' if short == 'x' else 'x'

        def tag_of(d, dirs=dirs):
            return f"{fmt_num(dirs[d]['rows'])}R-{fmt_num(dirs[d]['legs'])}-T{fmt_num(ps_dia)}"
        punching.append({'col': c, 'dirs': dirs, 's': ps_s, 'dia': ps_dia, 'short': tag_of(short), 'long': tag_of(long), 'shortDir': short, 'source': set_.get('designedBy') if set_ else 'override' if ov else 'assumed', 'check': ov or None})

    # one PS type per distinct (short dir, long dir, S), the lighter first
    def key_of(p):
        return f"{p['short']}|{p['long']}|{fmt_num(p['s'])}"

    def _parse_int(s):
        m = re.match(r'^\s*[+-]?\d+', s)
        return int(m.group(0)) if m else 0
    keys = sorted(dict.fromkeys(key_of(p) for p in punching), key=_parse_int)
    ps_types = []
    for i, k in enumerate(keys):
        short, long, sv = k.split('|')
        cols = [p for p in punching if key_of(p) == k]
        for p in cols:
            p['type'] = f'PS{i + 1}'
            p['tag'] = short if short == long else f'{short} / {long}'
        ps_types.append({'id': f'PS{i + 1}', 'short': short, 'long': long, 's': _whole(float(sv)), 'where': ', '.join(js_str(p['col'].get('id')) for p in cols)})
    for p in punching:
        c = p['col']
        w = c['d'] if c.get('shape') == 'circle' else c['w']
        hh = c['d'] if c.get('shape') == 'circle' else c['h']
        for dir_ in ['x', 'y']:
            F = hh if dir_ == 'x' else w
            ns = _whole(p['dirs'][dir_]['legs'] / 2)
            sw = max(80, F / ns - 60)
            link_len = ceil_to(2 * (sw + h - 2 * cover) + 20 * ps_dia, 10)
            bars['T'].add({'dia': ps_dia, 'shape': f"LINK {js_round(sw)}x{fmt_num(h - 2 * cover)}", 'length': link_len, 'qty': p['dirs'][dir_]['rows'] * ns * 2, 'spacing': p['s'], 'zone': f"D12 {p['type']} {js_str(c.get('id'))} {dir_.upper()}", 'note': 'PUNCHING'})
    railed = [p for p in punching if p['source'] != 'override']
    if has_ram:
        assumptions.append(f"D12 PUNCHING: {len(railed)} COLUMNS CARRY STUD RAILS IN THE RAM MODEL ({', '.join(js_str(p['col'].get('id')) for p in railed)}) - DRAWN AS THE OFFICE STIRRUP DETAIL (PS TYPES), ROWS COVERING THE RAILS' LENGTH AT S={fmt_num(ps_s)}, LEGS MATCHING THE STUD AREA; THE OTHER COLUMNS NEED NO PUNCHING REINFORCEMENT PER RAM." if railed else 'D12 PUNCHING: NO STUD RAILS IN THE RAM MODEL - NO COLUMN NEEDS PUNCHING REINFORCEMENT PER RAM.')
    if overridden:
        who = ', '.join(js_str(v) for v in [override.get('by'), override.get('date')] if _t(v))
        ids = ', '.join(js_str(o['col'].get('id')) for o in overridden)
        ratios = '; '.join(f"{js_str(o['col'].get('id'))} vu/phi.vc = {js_str(o['check'].get('ratio'))}" for o in overridden)
        who_txt = f" ({who})" if who else ''
        note_txt = f": {js_str(override.get('note')).upper()}" if _t(override.get('note')) else ''
        assumptions.append(f"D12 PUNCHING - ENGINEER'S BYPASS: COLUMNS {ids} DO NOT PASS THE PUNCHING CHECK ({ratios}). NO THICKENING ADOPTED; PUNCHING REINFORCEMENT (PS) IS PROVIDED AT THESE COLUMNS FROM THE OFFICE ESTIMATE AT THE DESIGN ENGINEER'S RESPONSIBILITY{who_txt}{note_txt}.")
        by_txt = f" ({js_str(override.get('by')).upper()})" if _t(override.get('by')) else ''
        for o in overridden:
            w = o['col']['d'] if o['col'].get('shape') == 'circle' else o['col']['w']
            hh = o['col']['d'] if o['col'].get('shape') == 'circle' else o['col']['h']
            notes.append({'x': o['col']['cx'], 'y': o['col']['cy'] + hh / 2 + 700, 'text': f"{js_str(o['col'].get('id'))}: PUNCHING NOT PASSING - PS AT THE DESIGN ENGINEER'S RESPONSIBILITY{by_txt}", 'box': True, 'layer': 'PS-TAG'})
            del w  # (JS: `void w`)
    level['punchingOverridden'] = [o['col'].get('id') for o in overridden]

    return {'items': items, 'bars': bars, 'notes': notes, 'assumptions': assumptions, 'punching': punching, 'psTypes': ps_types}


def _subtract(intervals, cuts):
    """Intervals minus cuts (sorted output)."""
    out = [list(x) for x in intervals]
    for c1, c2 in cuts:
        nxt = []
        for a, b in out:
            if c2 <= a or c1 >= b:
                nxt.append([a, b])
                continue
            if c1 > a:
                nxt.append([a, c1])
            if c2 < b:
                nxt.append([c2, b])
        out = nxt
    return [[a, b] for a, b in out if b - a > 1]


subtract = _subtract


def _inward(a, b, outline):
    """Inward unit normal of the outline edge a->b (outline CCW)."""
    u = unit(a, b)
    n = perp(u)
    m = mid(a, b)
    return n if point_in_polygon(add(m, n, 200), outline) else {'x': -n['x'], 'y': -n['y']}


inward = _inward


# ------------------------------------------------------------------ office-convention drafting
# the reading direction of a text along a bar: left to right, or bottom to top when the bar is vertical (the office reads
# vertical writing standing at the RIGHT edge of the sheet; a bar within half a degree of vertical reads bottom to top,
# never top to bottom); `flip` is -1 when the reading direction is opposite to u
def _readable_rot(u):
    r = (math.atan2(u['y'], u['x']) * 180) / math.pi
    flip = 1
    if r > 90.5:
        r -= 180
        flip = -1
    elif r <= -89.5:
        r += 180
        flip = -1
    return {'rot': r, 'flip': flip}


readable_rot = _readable_rot

# ---------------------------------------------------------------- label placement
TEXT_W = 0.85  # advance per character in text heights (isocp), before the width factor


def text_box(p, s, h, rot=0, align='L', valign='B', wf=1):
    """Axis-aligned box of a text: anchor p, height h (model mm), rotation, alignment."""
    w, hh = len(js_str(s)) * h * TEXT_W * wf, h
    x0 = -w / 2 if align == 'C' else -w if align == 'R' else 0
    y0 = -hh / 2 if valign == 'M' else -hh if valign == 'T' else 0
    r = (rot * math.pi) / 180
    c, sn = math.cos(r), math.sin(r)
    return bbox([{'x': p['x'] + x * c - y * sn, 'y': p['y'] + x * sn + y * c} for x, y in [[x0, y0], [x0 + w, y0], [x0 + w, y0 + hh], [x0, y0 + hh]]])


class LabelPlacer:
    """
    Keeps the boxes of everything written on the plan (the designer's call-outs and dimensions,
    notes, columns, walls) so that every added label can move along its bar, or to the other side,
    to the first place where it overlaps nothing; when every place is taken, the least overlapping wins.
    """

    def __init__(self):
        self.boxes = []
        self.uTags = []
        self.level = None
        self.uAllow = None

    def add(self, b):
        if b and isinstance(b.get('minX'), (int, float)) and not isinstance(b.get('minX'), bool) and math.isfinite(b['minX']):
            self.boxes.append(b)

    def overlap(self, b):
        a = 0
        for o in self.boxes:
            w = min(b['maxX'], o['maxX']) - max(b['minX'], o['minX'])
            h = min(b['maxY'], o['maxY']) - max(b['minY'], o['minY'])
            if w > 0 and h > 0:
                a += w * h
        return a

    def pick(self, cands, boxes_of):
        best = None
        for c in cands:
            a = sum(self.overlap(b) for b in boxes_of(c))
            if a == 0:
                return c
            if not best or a < best['a']:
                best = {'c': c, 'a': a}
        return best['c'] if best else (cands[0] if cands else None)


Placer = LabelPlacer
placer = None


def attach_placer(pl, S, level, spec=None):
    """Start a placer for a plan pen: every text drawn through the pen registers its box."""
    global placer
    spec = spec or {}
    placer = LabelPlacer()
    placer.level = level
    placer.uAllow = R.U_BOTTOM_LEG + (level['thickness'] - 2 * (spec.get('cover') or 25))
    text0 = pl.text

    def text(p, s, o=None, **kw):
        o = _opts(o, kw)
        placer.add(text_box(p, s, (o.get('h') or 2.5) * S, o.get('rot') or 0, o.get('align') or 'L', o.get('valign') or 'B', o.get('widthFactor') or 1))
        return text0(p, s, o)
    pl.text = text
    for c in level.get('columns') or []:
        placer.add({'minX': c['cx'] - c['d'] / 2, 'minY': c['cy'] - c['d'] / 2, 'maxX': c['cx'] + c['d'] / 2, 'maxY': c['cy'] + c['d'] / 2} if c.get('shape') == 'circle' else {'minX': c['cx'] - c['w'] / 2, 'minY': c['cy'] - c['h'] / 2, 'maxX': c['cx'] + c['w'] / 2, 'maxY': c['cy'] + c['h'] / 2})
    for w in level.get('walls') or []:
        if w.get('polygon'):
            placer.add(bbox(w['polygon']))
    for o in level.get('openings') or []:
        placer.add(bbox(R.region_polygon(o)))  # a bar symbol never sits in an opening
    return placer


def place_text(pl, p, s, o, offsets, S):
    """A text placed at the first of the candidate anchors that overlaps nothing (candidates = offsets of p)."""
    if not placer:
        place_text.last = pl.text(p, s, o)
        return p
    h = (o.get('h') or 2.5) * S
    q = placer.pick([{'x': p['x'] + d['x'], 'y': p['y'] + d['y']} for d in offsets], lambda c: [text_box(c, s, h, o.get('rot') or 0, o.get('align') or 'L', o.get('valign') or 'B', o.get('widthFactor') or 1)])
    place_text.last = pl.text(q, s, o)  # (the entity, for the bar tags)
    return q


place_text.last = None


def _json_stringify(v):
    """JS `JSON.stringify` of the bar tag payload (whole numbers without a fraction, no spaces, unicode kept)."""
    def conv(x):
        if isinstance(x, dict):
            return {k: conv(y) for k, y in x.items()}
        if isinstance(x, list):
            return [conv(y) for y in x]
        if isinstance(x, float):
            return _whole(x)
        return x
    return json.dumps(conv(v), separators=(',', ':'), ensure_ascii=False)


def bar_tag(it, role, extra=None):
    """
    The bar tag written as extended data on every entity of a bar (its line, call-out, length, distribution dimension,
    dot and detail tag): `BAR`, the bar id, the entity's role and the bar's figures as JSON - call-out, length text,
    diameter, spacing, count (0 = a run of bars: the count follows the distribution width), face, cutting length,
    the drawn polyline length, the distribution width and the level. An edited sheet (a stretched bar, a re-written
    call-out) is read back by these tags to update the take-off (`lib/dxf-bars.mjs`).
    """
    extra = extra or {}
    l1 = js_str(it.get('l1') or '')
    m = re.search(r'(\d+)?\s*T(\d+)(?:-(\d+))?', l1, re.I | re.A)
    dia = int(m.group(2)) if m else 0
    s = int(m.group(3)) if m and m.group(3) else 0
    n = it['n'] if (it.get('n') or 0) > 0 else int(m.group(1)) if m and m.group(1) else 0
    m2 = re.search(r'L\s*=\s*(\d+)', js_str(it.get('l2') or ''), re.I | re.A)
    L = it.get('length') if _t(it.get('length')) else (int(m2.group(1)) if m2 and int(m2.group(1)) else None) or js_round(dist(it['a'], it['b']))
    dw = js_round(dist(it['dist']['p'], it['dist']['q'])) if it.get('dist') else 0
    payload = {'l1': l1, 'l2': js_str(it.get('l2') or ''), 'dia': dia, 's': s, 'n': n, 'face': it.get('face') or 'T', 'L': L, 'pl': js_round(it.get('_plen') or 0), 'dw': dw, 'lv': (placer.level.get('id') if placer and placer.level else None) or '', **extra}
    return [[1000, 'BAR'], [1000, it.get('id') or bar_id(it)], [1000, role], [1000, _json_stringify(payload)]]


def tag_entity(e, it, role, extra=None):
    if isinstance(e, dict):
        e['_role'] = role
        e['xdata'] = bar_tag(it, role, extra)
    return e


def retag_bar(it):
    """Every entity of the bar re-tagged with the bar's final figures (the distribution is decided after the line is drawn)."""
    for e in it.get('_ents') or []:
        if isinstance(e, dict):
            e['xdata'] = bar_tag(it, e.get('_role') or 'BAR')


def dist_width_of(it):
    """The width a bar's own distribution dimension spans: (count - 1) x spacing for a counted group, the spacing of a single bar."""
    l1 = js_str(it.get('l1') or '')
    count = re.search(r'^(\d+)\s*T\d+', l1, re.I | re.A)
    sp = re.search(r'-(\d{2,4})\b', l1, re.A)
    spacing = int(sp.group(1)) if sp else 200
    if count and int(count.group(1)) > 1:
        return max(spacing, 100) * (int(count.group(1)) - 1)
    if (it.get('n') or 0) > 1:
        return max(spacing, 100) * (it['n'] - 1)  # a group whose count is known (column bars)
    # a spacing-only bar stands for a run of bars: never a dimension of one spacing (unreadable, and not what it means)
    return max(spacing * 4, 1000)


def office_dim(pl, S, p, q, opts=None):
    """The distribution indicator: a real DIMENSION in style DIM100 (red lines, oblique ticks, green number)."""
    opts = opts or {}
    L = dist(p, q)
    if L < 1:
        return None
    u = unit(p, q)
    n = perp(u)
    text_at = opts.get('textAt')
    # a dimension shorter than its own text (a 400 group of three bars) carries the text past its end, where it reads
    if not text_at and L < DIM100['txt'] * (len(js_str(opts.get('text') or js_round(L))) * 0.8 + 1.5):
        text_at = add(add(q, u, DIM100['txt'] * 0.6 + (len(js_str(opts.get('text') or js_round(L))) * DIM100['txt'] * 0.8) / 2), n, DIM100['gap'] + DIM100['txt'] / 2)
    if placer:
        tm = text_at or add(mid(p, q), n, DIM100['gap'] + DIM100['txt'] / 2)
        placer.add(text_box(tm, opts.get('text') or js_str(js_round(L)), DIM100['txt'], _readable_rot(u)['rot'], 'C', 'M', 0.8))
    return pl.dimension(p, q, opts.get('dl') or p, {'style': 'DIM100', 'styleDef': DIM100, 'layer': 'diamension', 'textMid': text_at, 'text': opts.get('text')})


def office_dot(pl, S, p):
    return [pl.circle(p, DOT_R, {'layer': 'DOTS'}), pl.hatch([R.region_polygon({'kind': 'circle', 'cx': p['x'], 'cy': p['y'], 'r': DOT_R})], {'layer': 'DOTS', 'pattern': 'SOLID'})]


def office_bar(pl, S, it, phase=None):
    """One added bar in the office convention."""
    layer = 'REO-BOT' if it.get('face') == 'B' else 'REO-TOP'
    if phase != 'labels' and it.get('posCands') is not None:
        # the bar symbol beside the column: the first offset whose line crosses nothing (the column itself, walls, writing)
        u0 = unit(it['a'], it['b'])
        n0 = perp(u0)

        def box_of(k):
            A_, B_ = add(it['a'], n0, k), add(it['b'], n0, k)
            return [bbox([add(A_, n0, -80), add(A_, n0, 80), add(B_, n0, -80), add(B_, n0, 80)])]
        k = placer.pick(it['posCands'], box_of) if placer else it['posCands'][0]
        it['a'] = add(it['a'], n0, k)
        it['b'] = add(it['b'], n0, k)
        del it['posCands']
        if placer and placer.level:
            clip_at_openings(placer.level, it, placer.uAllow or 800)  # in its final place the bar still stops at an opening
        if placer:
            placer.add(bbox([add(it['a'], n0, -40), add(it['a'], n0, 40), add(it['b'], n0, -40), add(it['b'], n0, 40)]))  # later writing keeps off the bar
    u = unit(it['a'], it['b'])
    n = perp(u)
    rr = _readable_rot(u)
    rot, flip = rr['rot'], rr['flip']
    side = (it.get('side') or 1) * flip
    m0 = mid(it['a'], it['b'])
    if phase != 'labels':
        # the bar itself, its legs and its distribution dimension (drawn for every bar before any label is placed)
        ls = leg_side(u, it.get('face'))  # the legs of this bar: up / left for a bottom bar, down / right for a top bar
        # office rule: a bar is ONE continuous polyline - its run, its bends and its legs (a U-bar is one line, never
        # three) - so the drawing reads as the bar it is and the CAD user picks it up in one click
        if it.get('bend'):
            # the drop bar: the bottom run, a 90° rise over the step at each end (drawn as a leg across the bar, on the
            # leg side) and the continuation at the slab bottom lapping with the slab bottom bars
            # (no rise and no continuation on a side where they would leave the slab or enter an opening: `noA` / `noB`)
            bend = it['bend']
            r = max(bend.get('rise') or 50, 150)
            qa1 = add(it['a'], ls, r)
            qa2 = add(qa1, u, -_nn(bend.get('beyondA'), _nn(bend.get('beyond'), 500)))
            qb1 = add(it['b'], ls, r)
            qb2 = add(qb1, u, _nn(bend.get('beyondB'), _nn(bend.get('beyond'), 500)))
            pts = ([] if bend.get('noA') else [qa2, qa1]) + [it['a'], it['b']] + ([] if bend.get('noB') else [qb1, qb2])
        elif it.get('hairpin'):
            # the U on the plan: the two legs closed at the edge (a), one polyline leg - closing bar - leg
            pts = [add(it['b'], ls, 150), add(it['a'], ls, 150), it['a'], it['b']]
        else:
            pts = [add(it['a'], n, it['pairOff']) if it.get('pairOff') else it['a'], add(it['b'], n, it['pairOff']) if it.get('pairOff') else it['b']]
        # the ends: the leg of an L at the edge (`legEnd`) and the U / L ends at the boundary (`uEnd`), joined to the run
        ends = u_end_points(it['a'], it['b'], it['uEnd'], layer) if it.get('uEnd') is not None else {'pre': [], 'post': []}
        if it.get('legEnd') == 'start' and not (it.get('uEnd') or {}).get('start'):
            ends['pre'] = [add(it['a'], ls, 250)]
        if it.get('legEnd') == 'end' and not (it.get('uEnd') or {}).get('end'):
            ends['post'] = [add(it['b'], ls, 250)]
        if it.get('bend'):
            ends['pre'] = []
            ends['post'] = []  # a bent drop bar already ends in its own legs
        line = ends['pre'] + pts + ends['post']
        it['_plen'] = sum(dist(line[i - 1], line[i]) for i in range(1, len(line)))
        it['_ents'] = [tag_entity(bar_line(pl, line, layer), it, 'BAR')]
        if it.get('uEnd') is not None:
            u_end_tags(pl, S, it['a'], it['b'], it['uEnd'], layer, it)
        if it.get('triple'):
            it['_ents'].append(tag_entity(bar_line(pl, [add(it['a'], n, 200), add(it['b'], n, 200)], layer), it, 'BAR2'))
            it['_ents'].append(tag_entity(bar_line(pl, [add(it['a'], n, -200), add(it['b'], n, -200)], layer), it, 'BAR2'))
        if it.get('pairOff'):
            it['_ents'].append(tag_entity(bar_line(pl, [add(it['a'], n, -it['pairOff']), add(it['b'], n, -it['pairOff'])], layer), it, 'BAR2'))  # the second bar of a pair (blockwork beam)
        if it.get('distCands') and not it.get('dist'):
            def box_of_d(d):
                du = unit(d['p'], d['q'])
                dn = perp(du)
                return [text_box(d.get('textAt') or add(mid(d['p'], d['q']), dn, DIM100['gap'] + DIM100['txt'] / 2), d.get('text') or js_str(js_round(dist(d['p'], d['q']))), DIM100['txt'], _readable_rot(du)['rot'], 'C', 'M', 0.8)]
            it['dist'] = placer.pick(it['distCands'], box_of_d) if placer else it['distCands'][0]
        # office rule: every drawn bar carries a distribution dimension with the dot that ties them together.
        # A bar with an indication line takes the segment of it that it crosses as its dimension; any other bar
        # gets one across it at its symbol, as wide as its group (count x spacing, or the spacing of a single bar).
        if not it.get('dist') and it.get('ind') and len(it['ind']) >= 2:
            best = None
            for i in range(len(it['ind']) - 1):
                d = dist_to_seg(m0, it['ind'][i], it['ind'][i + 1])
                if not best or d < best['d']:
                    best = {'d': d, 'p': it['ind'][i], 'q': it['ind'][i + 1]}
            it['dist'] = {'p': best['p'], 'q': best['q']}
            it['ind'] = None
        if not it.get('dist'):
            w = dist_width_of(it)
            it['dist'] = {'p': add(m0, n, -w / 2), 'q': add(m0, n, w / 2)}
            it['distAuto'] = True
        if it.get('ind'):
            it['_ents'].append(tag_entity(pl.pline(it['ind'], {'layer': 'diamension'}), it, 'IND'))  # long indication line offset inside the edge: "this bar all along here"
        if it.get('dist'):
            # the dot where the bar axis crosses the distribution line; a bar whose axis misses its line by more than a
            # little (the symbol slid away from a clipped group dimension) takes the dimension across itself instead,
            # so that no bar is ever drawn without the dimension and the dot that tie the two together
            dot_at = None
            du = unit(it['dist']['p'], it['dist']['q'])
            Ld = dist(it['dist']['p'], it['dist']['q'])
            den = u['x'] * du['y'] - u['y'] * du['x']
            if abs(den) > 1e-6:
                t = ((m0['x'] - it['dist']['p']['x']) * u['y'] - (m0['y'] - it['dist']['p']['y']) * u['x']) / -den
                if t >= -300 and t <= Ld + 300:
                    dot_at = add(it['dist']['p'], du, max(0, min(Ld, t)))
                elif abs(den) > 0.3 and t > -4000 and t < Ld + 4000 and not it.get('distAuto'):
                    # the symbol slid past the end of its group dimension (clipped group, moved symbol): the dimension is
                    # stretched to the bar, so it still measures the run the bar stands for and the dot sits on the bar
                    c = add(it['dist']['p'], du, t)
                    if t < 0:
                        it['dist'] = {**it['dist'], 'p': c}
                    else:
                        it['dist'] = {**it['dist'], 'q': c}
                    dot_at = c
            if not dot_at:
                w = dist_width_of(it)
                it['dist'] = {'p': add(m0, n, -w / 2), 'q': add(m0, n, w / 2)}
                it['distAuto'] = True
                dot_at = m0
            it['_ents'].append(tag_entity(office_dim(pl, S, it['dist']['p'], it['dist']['q'], {'text': it['dist'].get('text'), 'textAt': it['dist'].get('textAt')}), it, 'DIST'))
            for e in office_dot(pl, S, dot_at):
                it['_ents'].append(tag_entity(e, it, 'DOT'))
        retag_bar(it)
        if phase == 'bars':
            return None
    # the call-out pair slides along the bar (and may swap sides) to the first place free of other writing
    to = {'layer': 'REO-TXT', 'style': 'BW', 'widthFactor': 0.8, 'rot': rot, 'align': 'C'}
    L = dist(it['a'], it['b'])
    w_txt = max(len(js_str(it.get('l1'))), len(js_str(it.get('l2')))) * CALL_H * TEXT_W * 0.8
    shifts = [k for k in [0, 400, -400, 800, -800, 1200, -1200, 1600, -1600, 2000, -2000, 2500, -2500, 3000, -3000] if abs(k) + w_txt / 2 <= L / 2 + 250]
    # a short bar (a U-bar leg at a wall face or an edge) lets its call-out slide past its ends (into the slab)
    if L < 2500:
        shifts = [0, 300, -300, 600, -600, 900, -900, 1200, -1200]
    if not shifts:
        shifts.append(0)
    # a short bar (a U-bar symbol on an edge or a wall face) can also carry its call-out beside it, along the edge
    sideways = [0, 600, -600, 1200, -1200, 1800, -1800, 2400, -2400] if L < 2500 else [0]
    cands = [{'k': k, 'sd': flip, 'j': j} for j in sideways for k in shifts]
    gap = 150 if it.get('hairpin') else 60  # a hairpin's second leg sits 150 beside the axis: the call-out on that side clears it
    # office convention: the bar call-out ("T12-150 (B)") above the bar and the length ("L=5340") under it in the
    # reading direction, the bar between them, both texts starting at the same point (left-aligned). The text's "up"
    # on the page is +n when the reading direction follows the bar, -n when it is flipped.
    w_max = max(len(js_str(it.get('l1'))), len(js_str(it.get('l2')))) * CALL_H * TEXT_W * 0.8

    def pair(c):
        k, j = c['k'], c.get('j') or 0
        mm = add(add(add(m0, u, k), n, j), u, -flip * w_max / 2)  # the common start (reading-left) of both lines

        def base(sg):
            return gap + 60 if sg < 0 else 60
        above, below = add(mm, n, flip * base(flip)), add(mm, n, -flip * base(-flip))
        return [[above, it.get('l1'), CALL_H, 'B', 'L'], [below, it.get('l2'), LEN_H, 'T', 'L']]
    best = placer.pick(cands, lambda c: [text_box(p, s, h, rot, al, va, 0.8) for p, s, h, va, al in pair(c)]) if placer else {'k': 0, 'sd': side, 'j': 0}
    it['_ents'] = it.get('_ents') or []
    for i, (p, s, h, va, al) in enumerate(pair(best)):
        it['_ents'].append(tag_entity(pl.text(p, s, {**to, 'h': h / S, 'valign': va, 'align': al}), it, 'CALLOUT' if i == 0 else 'LENGTH'))
    m = add(add(m0, u, best['k']), n, best.get('j') or 0)
    if it.get('detail') and not it.get('noTag'):
        def tag_at(k, sg):
            return add(add(add(m0, u, k), n, best.get('j') or 0), n, sg * 520)
        tag_cands = [tag_at(best['k'] + k, sg) for k in [0, 600, -600, 1200, -1200, 1800, -1800] for sg in [best['sd'], -best['sd']]]
        c = placer.pick(tag_cands, lambda q: [{'minX': q['x'] - 150, 'minY': q['y'] - 150, 'maxX': q['x'] + 150, 'maxY': q['y'] + 150}]) if placer else tag_at(best['k'], best['sd'])
        it['_ents'].append(tag_entity(pl.circle(c, 150, {'layer': 'DETAIL-REF'}), it, 'TAG'))
        it['_ents'].append(tag_entity(pl.text(c, it['detail'], {'layer': 'DETAIL-REF', 'h': 130 / S, 'align': 'C', 'valign': 'M', 'bold': True}), it, 'TAG'))
        if placer:
            placer.add({'minX': c['x'] - 150, 'minY': c['y'] - 150, 'maxX': c['x'] + 150, 'maxY': c['y'] + 150})
    retag_bar(it)
    # the bar with its writing and its distribution as one group (selectable together where the sheet is not a block)
    if getattr(pl, 'group', None) and len(it['_ents']) > 1:
        pl.group(f"BAR_{re.sub(r'[^A-Za-z0-9_:,.-]', '_', it.get('id') or bar_id(it))}", it['_ents'], js_str(it.get('l1') or ''))
    return None


def u_end_points(a, b, u_end, layer):
    """
    The end of a top bar at the slab boundary: a U (500 bottom leg, "U500") at a free edge or an opening, an L ("L400",
    the leg down into the beam) at an edge beam. `uEndPoints` gives the leg vertices to join to the bar's own polyline
    (`pre` before its start, `post` after its end: the bar stays ONE line), `uEndTags` writes the U500 / L400 tag.
    """
    u = unit(a, b)
    ls = leg_side(u, 'B' if re.search('BOT', layer) else 'T')  # top bar: legs down / right; bottom bar: up / left

    def legs(on, p, back):
        if not _t(on):
            return []
        tick = add(p, ls, 250)
        # a U is drawn as a U: the leg and the 500 bottom leg coming back along the bar from the edge (an L keeps its single leg into the beam)
        return [tick, add(tick, back, R.U_BOTTOM_LEG)] if on == 'U' else [tick]
    return {'pre': list(reversed(legs(u_end.get('start'), a, u))), 'post': legs(u_end.get('end'), b, {'x': -u['x'], 'y': -u['y']})}


def u_end_tags(pl, S, a, b, u_end, layer, it=None):
    u = unit(a, b)
    n = perp(u)
    rot = _readable_rot(u)['rot']
    ls = leg_side(u, 'B' if re.search('BOT', layer) else 'T')
    for on, p in [[u_end.get('start'), a], [u_end.get('end'), b]]:
        if not _t(on):
            continue
        if placer:
            if any(dist(q, p) < 400 for q in placer.uTags):
                continue  # one tag where two bars end together
            placer.uTags.append(p)
        offs = []
        for k in [0, 300, -300, 600, -600]:
            offs.append(add(add({'x': 0, 'y': 0}, u, k), ls, 300 + 110))
            offs.append(add(add({'x': 0, 'y': 0}, u, k), ls, -300))
        tag = f"L{fmt_num(DEFAULT_U['beamLeg'])}" if on == 'L' else f"U{fmt_num(R.U_BOTTOM_LEG)}"
        place_text(pl, add(p, n, 0), tag, {'layer': 'REO-TXT', 'style': 'BW', 'widthFactor': 0.8, 'h': 110 / S, 'rot': rot, 'align': 'C', 'valign': 'B'}, offs, S)
        if it is not None and place_text.last is not None:
            it['_ents'].append(tag_entity(place_text.last, it, 'UTAG'))


def draw_existing(pl, S, ex, faces):
    """The designer's own reinforcement, re-emitted verbatim in the same convention (top bars get the U end at the edge / openings)."""
    def keep(f):
        return f in faces
    for l in [x for x in ex['lines'] if keep(x.get('face'))]:
        layer = 'REO-BOT' if re.search('BOT', js_str(l.get('layer')), re.I) or l.get('face') == 'B' else 'REO-TOP'  # (js_str(None) is 'undefined', as the JS regex sees it)
        ends = u_end_points(l['a'], l['b'], l['uEnd'], layer) if l.get('uEnd') is not None and 'T' in faces else {'pre': [], 'post': []}
        bar_line(pl, ends['pre'] + [l['a'], l['b']] + ends['post'], layer)  # one polyline: the bar with its U / L legs
        if l.get('uEnd') is not None and 'T' in faces:
            u_end_tags(pl, S, l['a'], l['b'], l['uEnd'], layer)
    for it in [x for x in (ex.get('items') or []) if keep(x.get('face'))]:
        office_bar(pl, S, it)
    for c in [x for x in ex['callouts'] if keep(x.get('face'))]:
        ha = c.get('halign')
        align = (['L', 'C', 'R'][int(ha)] if isinstance(ha, (int, float)) and not isinstance(ha, bool) and ha == int(ha) and 0 <= int(ha) < 3 else None) or 'L'
        pl.text({'x': c['x'], 'y': c['y']}, c['text'], {'layer': 'REO-TXT', 'style': 'BW', 'widthFactor': c.get('widthFactor') or 0.8, 'h': (c.get('h') or CALL_H) / S, 'rot': c.get('rot'), 'align': align, 'valign': 'B'})
    for d in [x for x in ex['dims'] if keep(x.get('face'))]:
        draw_dimension(pl, S, d)
    for d in [x for x in ex['dots'] if keep(x.get('face'))]:
        office_dot(pl, S, d)


def draw_dimension(pl, S, e):
    """A DIMENSION entity read from the design plan, re-emitted as a real DIMENSION in style DIM100."""
    if e.get('x3') is None or e.get('x4') is None:
        return None
    p3, p4, dp = {'x': e['x3'], 'y': e['y3']}, {'x': e['x4'], 'y': e['y4']}, {'x': e['x'], 'y': e['y']}
    angle = (math.atan2(p4['y'] - p3['y'], p4['x'] - p3['x']) * 180) / math.pi if e.get('dimType') == 1 else (e.get('rotation') or 0)
    text_mid = {'x': e['x2'], 'y': e['y2']} if e.get('x2') is not None and (_t(e.get('x2')) or _t(e.get('y2'))) else None
    text = e['text'] if _t(e.get('text')) and e['text'] != '<>' and not re.search(r'^\s*$', e['text']) else None
    if placer:
        r = (angle * math.pi) / 180
        u = {'x': math.cos(r), 'y': math.sin(r)}
        n = perp(u)

        def along(p):
            return (p['x'] - dp['x']) * u['x'] + (p['y'] - dp['y']) * u['y']
        tm = text_mid or add(add(dp, u, (along(p3) + along(p4)) / 2), n, DIM100['gap'] + DIM100['txt'] / 2)
        placer.add(text_box(tm, text or js_str(js_round(abs(along(p4) - along(p3)))), DIM100['txt'], angle, 'C', 'M', 0.8))
    return pl.dimension(p3, p4, dp, {'style': 'DIM100', 'styleDef': DIM100, 'layer': 'diamension', 'angle': angle, 'textMid': text_mid, 'text': text})


def draw_mesh_labels(pl, S, level):
    """Mesh label in the designer's style: two lines of cyan text in a box."""
    for m in level.get('meshLabels') or []:
        n = len(m['lines'])
        w = max(len(l) for l in m['lines']) * 200 * 0.8 + 400
        hh = n * 330 + 200
        pl.rect({'x': m['x'] - 200, 'y': m['y'] - (n - 1) * 330 - 100, 'w': w, 'h': hh}, {'layer': '9_TEXT'})
        for i, ln in enumerate(m['lines']):
            pl.text({'x': m['x'], 'y': m['y'] - i * 330}, ln, {'layer': '9_TEXT', 'h': 200 / S, 'style': 'BW', 'widthFactor': 0.8})


def draw_designer_notes(pl, S, level, o=None):
    o = o or {}
    for c in level.get('camber') or []:
        pl.text({'x': c['x'], 'y': c['y']}, c['text'], {'layer': 'TEXT-4', 'h': 200 / S, 'style': 'BW', 'widthFactor': 0.8})
    for t in level.get('levelTags') or []:
        pl.text({'x': t['x'], 'y': t['y']}, f"{t['label']} {js_str(t['value'])}", {'layer': 'TEXT-4', 'h': 190 / S, 'style': 'BW', 'widthFactor': 0.8})
    if o.get('thickness') is not False:
        if o.get('zones') is not False and not o.get('regionLabels'):
            for z in level.get('thickZones') or []:
                b = bbox(z['polygon'])
                pl.text({'x': b['minX'] + 500, 'y': b['maxY'] - 450}, f"THK {js_str(z['thickness']) if _t(z.get('thickness')) else 'DROP'}", {'layer': 'S-TEXT', 'h': 200 / S, 'align': 'L', 'valign': 'M', 'style': 'BW', 'widthFactor': 0.8})
        for t in level.get('rcTags') or []:
            slab_tag(pl, S, t, level)


def slab_tag(pl, S, t, level):
    """
    The slab tag (office style): a boxed two-line label in the slab - `POST TENSION SLAB` (or `RC SLAB`) over the
    thickness `250 mm` - readable at a glance; the mesh labels of the reinforcement sheets go under the box (`t.below`).
    """
    pt = (len(((level.get('pt') or {}).get('zones') or [])) or 0) > 0 or (len(((level.get('ram') or {}).get('tendons') or [])) or 0) > 0
    lines = ['POST TENSION SLAB' if pt else 'RC SLAB', f"{js_str(t['thickness'])} mm"]
    H, gap, pad = 260, 140, 200  # model mm at 1:100 (2.6 mm text on paper)
    tw = max(len(l) for l in lines) * H * 0.8 * 0.85 + 2 * pad
    th = len(lines) * H + (len(lines) - 1) * gap + 2 * pad
    pl.rect({'x': t['x'] - tw / 2, 'y': t['y'] - th / 2, 'w': tw, 'h': th}, {'layer': 'S-TEXT'})
    for i, text in enumerate(lines):
        pl.text({'x': t['x'], 'y': t['y'] + th / 2 - pad - H / 2 - i * (H + gap)}, text, {'layer': 'S-TEXT', 'h': H / S, 'align': 'C', 'valign': 'M', 'style': 'BW', 'widthFactor': 0.8})
    t['below'] = t['y'] - th / 2 - 250  # where the next label under the box goes
    return t['below']


def zone_labels(pl, S, level, spec, face):
    """
    The thickness tag of every thickened zone (and, on the bottom sheet, the mesh written in it: the base mesh, or the
    drop mesh of detail 4 in a column drop) as one block of lines placed after the bars, at the first corner of the zone
    that is free of bars and writing (top-left, top-right, bottom-left, bottom-right, then just above the zone).
    """
    tm = spec.get('thicknessMesh') or R.DEFAULT_SPEC['thicknessMesh']
    sd = spec.get('drops') or R.DEFAULT_SPEC['drops']
    for z in level.get('thickZones') or []:
        b = bbox(z['polygon'])
        lines = [[f"THK {js_str(z['thickness']) if _t(z.get('thickness')) else 'DROP'}", 'S-TEXT', 200]]
        if face == 'B':
            lines.append([f"BOTTOM MESH T{fmt_num(sd['dia'])}@{fmt_num(sd['spacing'])} (D4)", '9_TEXT', 170] if drop_column(level, spec, z) else [f"BOTTOM MESH T{fmt_num(tm['dia'])}@{fmt_num(tm['spacing'])}", '9_TEXT', 170])
        w_max = max(len(t) * h * TEXT_W * 0.8 for t, _, h in lines)
        h_all = sum(h + 100 for _, _, h in lines)
        corners = [[b['minX'] + 150, b['maxY'] - 150], [b['maxX'] - 150 - w_max, b['maxY'] - 150], [b['minX'] + 150, b['minY'] + 150 + h_all], [b['maxX'] - 150 - w_max, b['minY'] + 150 + h_all], [b['minX'] + 150, b['maxY'] + 150 + h_all], [b['minX'] + 150, b['minY'] - 150]]

        def boxes_at(c):
            y = c[1]
            out = []
            for t, _, h in lines:
                out.append(text_box({'x': c[0], 'y': y - h}, t, h, 0, 'L', 'B', 0.8))
                y -= h + 100
            return out
        c = placer.pick(corners, boxes_at) if placer else corners[0]
        y = c[1]
        for t, layer, h in lines:
            pl.text({'x': c[0], 'y': y - h}, t, {'layer': layer, 'h': h / S, 'style': 'BW', 'widthFactor': 0.8})
            y -= h + 100


DEFAULT_U = R.DEFAULT_SPEC['uEdge']


def details_key_rows(keys):
    return [{'d': k, 'title': DETAILS.get(k)} for k in keys]


DETAIL_KEY_COLS = [{'key': 'd', 'title': 'REF', 'w': 16}, {'key': 'title', 'title': 'GENERAL DETAIL (SEE THE GENERAL DETAILS SHEET)', 'w': 160, 'align': 'L', 'max': 62}]

# ------------------------------------------------------------------ sheets
DESIGN_SHEETS = [
    {'key': 'dframing', 'base': 'DESIGN_FRAMING_PLAN', 'title': 'FRAMING PLAN - OUTLINE, COLUMNS, WALLS, OPENINGS, THICKNESS', 'no': '01'},
    {'key': 'dbottom', 'base': 'DESIGN_BOTTOM_REINFORCEMENT', 'title': 'BOTTOM REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', 'no': '02'},
    {'key': 'dtop', 'base': 'DESIGN_TOP_REINFORCEMENT', 'title': 'TOP REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', 'no': '03'},
    {'key': 'dpunch', 'base': 'DESIGN_PUNCHING_SHEAR', 'title': 'PUNCHING SHEAR REINFORCEMENT PLAN', 'no': '04'},
    # from a RAM model: the tendons, one direction per sheet, with the high / low points of the profile only
    {'key': 'dcablat', 'base': 'DESIGN_PT_CABLES_LATITUDE', 'title': 'PT CABLES - LATITUDE (DIRECTION 1) - DESIGN LAYOUT AND PROFILE POINTS', 'no': '05', 'ramOnly': True, 'set': 'latitude'},
    {'key': 'dcablon', 'base': 'DESIGN_PT_CABLES_LONGITUDE', 'title': 'PT CABLES - LONGITUDE (DIRECTION 2) - DESIGN LAYOUT AND PROFILE POINTS', 'no': '06', 'ramOnly': True, 'set': 'longitude'},
]


def design_notes(model, level):
    spec = model['spec']
    tos_txt = f", {level['levelTags'][0]['label']} {js_str(level['tos'])}" if _t(level.get('tos')) else ''
    zones_txt = f"; THICKENED ZONES {_join(list(dict.fromkeys(z.get('thickness') for z in level['thickZones'])), ' / ')} mm HATCHED" if level.get('thickZones') else ''
    return [
        common_notes(model, level)[0],
        f"SLAB THICKNESS {js_str(level['thickness'])} mm{tos_txt}{zones_txt}. CONCRETE f'c = {js_str(spec.get('fc'))} MPa, REINFORCEMENT fy = {js_str(spec.get('fy'))} MPa, COVER {js_str(spec.get('cover'))} mm ({js_str((spec.get('sources') or {}).get('cover'))}).",
        'BAR CALL-OUT (OFFICE CONVENTION): "T10-200 (T)" = BAR SIZE - SPACING (LAYER), "L=2400" = BAR LENGTH; THE RED DIMENSION ACROSS THE BARS IS THE WIDTH OVER WHICH THEY ARE DISTRIBUTED; (T) TOP, (B) BOTTOM, T&B BOTH.',
        'THE REINFORCEMENT DESIGNED BY THE OFFICE IS SHOWN AS DRAWN ON THE DESIGN PLAN. BARS MARKED WITH A CIRCLED "D#" ARE ADDED FROM THE GENERAL DETAILS SHEET (DETAIL NUMBER IN THE CIRCLE) AT THE LOCATIONS THE DETAIL REFERS TO; THE DETAIL GOVERNS FOR SHAPE AND ANCHORAGE.',
        f"BAR ENDS AT THE BOUNDARY: U ({fmt_num(R.U_BOTTOM_LEG)} BACK AT THE BOTTOM, \"U{fmt_num(R.U_BOTTOM_LEG)}\") AT A FREE EDGE OR AN OPENING, L ({fmt_num(DEFAULT_U['beamLeg'])} DOWN INTO THE BEAM, \"L{fmt_num(DEFAULT_U['beamLeg'])}\") AT AN EDGE BEAM; LEGS ADDED TO THE CUTTING LENGTH. TOP BARS OVER COLUMNS AND ISOLATED WALLS: TWO PERPENDICULAR GROUPS, EACH THE DROP PANEL OR 4 m LONG AND AT LEAST 1.5 m PAST THE FACE, DISTRIBUTED OVER THE CROSSING GROUP; 70 % ON TOP AT AN EDGE. CORE WALLS (3 OR MORE AROUND AN OPENING): WALL U-BARS. PERIMETER T{fmt_num(DEFAULT_U['dia'])}@{fmt_num(DEFAULT_U['spacing'])} BETWEEN THE COLUMN BARS: {fmt_num(DEFAULT_U['total'])} mm U AT A FREE EDGE, L ({fmt_num(DEFAULT_U['beamLeg'])} INTO THE BEAM + {fmt_num(DEFAULT_U['beamTop'])} ON TOP) AT AN EDGE BEAM; ONE SYMBOL PER RUN, THE LINE INSIDE THE EDGE IS ITS EXTENT. ENCLOSED OPENINGS: NO TRIMMERS; OTHERS: G1 / G2 PARALLEL TO THE SIDES, G3 AT 45°. NOTHING IS DRAWN OUTSIDE THE SLAB.",
    ]


def framing_sheet(model, level, meta, adds):
    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        draw_base(sheet, pl, level, {'columnHatchLayer': 's-hatch', 'regionLabels': True, 'gridTag': meta.get('gridTag'), 'pt': False, 'ubarRegions': False})
        draw_designer_notes(pl, S, level)
        for e in [x for x in level['edges'] if x.get('beam')]:
            m = mid(e['a'], e['b'])
            n_in = _inward(e['a'], e['b'], level['outline'])
            pl.text(add(m, n_in, 450), 'EDGE BEAM', {'layer': 'BEAM', 'h': 1.5, 'align': 'C', 'valign': 'M', 'rot': _readable_rot(unit(e['a'], e['b']))['rot']})
        rows = (
            [{'id': c.get('id'), 'element': 'COLUMN (ROUND)' if c.get('shape') == 'circle' else 'COLUMN', 'size': f"Ø{fmt_mm(c['d'])}" if c.get('shape') == 'circle' else f"{fmt_mm(c['w'])} x {fmt_mm(c['h'])}", 'location': f"X {fmt_mm(c['cx'])}, Y {fmt_mm(c['cy'])}"} for c in level['columns']]
            + [{'id': w.get('id'), 'element': f"WALL {fmt_mm(w['t'])} THK", 'size': f"{fmt_mm(w['w'])} x {fmt_mm(w['h'])}", 'location': grid_ref(level, bbox(w['polygon']))} for w in level['walls']]
            + [{'id': o.get('id'), 'element': 'OPENING', 'size': f"{fmt_mm(bbox(R.region_polygon(o))['w'])} x {fmt_mm(bbox(R.region_polygon(o))['h'])}", 'location': grid_ref(level, bbox(R.region_polygon(o)))} for o in level['openings']]
            + [{'id': z.get('id'), 'element': f"THICKENED ZONE {js_str(z['thickness']) if _t(z.get('thickness')) else ''} mm", 'size': f"{fmt_mm(bbox(z['polygon'])['w'])} x {fmt_mm(bbox(z['polygon'])['h'])}", 'location': grid_ref(level, bbox(z['polygon']))} for z in level['thickZones']]
            + [{'id': z.get('id'), 'element': 'POUR STRIP', 'size': f"{fmt_mm(z['width'])} x {fmt_mm(z['length'])}", 'location': grid_ref(level, bbox(z['polygon']))} for z in (level.get('pourStrips') or [])]
            + [{'id': bm.get('id'), 'element': 'BAND BEAM (THICKENED STRIP)' if bm.get('band') else 'INTERIOR BEAM' if bm.get('interior') else 'EDGE BEAM', 'size': f"{fmt_mm(bm['t'])}{' x ' + fmt_mm(bm['depth']) if _t(bm.get('depth')) else ''} L={fmt_mm(dist(bm['a'], bm['b']))}", 'location': grid_ref(level, bbox(bm['polygon']))} for bm in (level.get('beams') or []) if bm.get('polygon')]
        )
        cols = [{'key': 'id', 'title': 'ID', 'w': 20}, {'key': 'element', 'title': 'ELEMENT', 'w': 42}, {'key': 'size', 'title': 'SIZE (mm)', 'w': 45}, {'key': 'location', 'title': 'LOCATION / GRID', 'w': 78, 'align': 'L', 'max': 44}]
        # the beams live on the framing plan (office rule: no separate beam sheet): every typed beam carries its type,
        # section and bars beside it (drawBase), the beam schedule takes the table and the sections the detail boxes
        sch = level['beamSchedule'] if level.get('beamSchedule') and (level['beamSchedule'].get('types') or []) else None
        design_label = ('OFFICE DESIGN' if sch.get('design') == 'office' else 'HEAVIER OF RAM AND OFFICE DESIGN' if sch.get('design') == 'max' else 'RAM DESIGN') if sch else ''
        nxt = 0
        if sch:
            nxt = draw_beam_sections(sheet, sch, 0)
        if nxt < 3:
            d0 = sheet.detail_box(nxt, 'GENERAL DETAILS APPLIED ON THIS LEVEL', '')
            nxt += 1
            sheet.table(d0['x'] + 3, d0['y'] + d0['h'] - 10, DETAIL_KEY_COLS, details_key_rows(list(DETAILS.keys())), {'headH': 5, 'rowH': 4, 'h': 1.5, 'maxRows': 12})
        if nxt < 3:
            d1 = sheet.detail_box(nxt, 'NOTATION AND MATERIALS', 'N.T.S.')
            nxt += 1
            det1 = D.notation_legend({'thickness': level['thickness'], 'fc': model['spec'].get('fc'), 'fy': model['spec'].get('fy'), 'cover': model['spec'].get('cover')})
            det1.draw(sheet.detail_pen(d1, 12, det1.bbox))
        if nxt < 3:
            d2 = sheet.detail_box(nxt, 'TYPICAL SLAB SECTION AT COLUMN', '1:25')
            nxt += 1
            det2 = D.section_column({'h': level['thickness'], 'c1': (level['columns'][0].get('w') if level['columns'] else None) or 600, 'ext': 1200, 'dia': 10, 'spacing': 150, 'cover': model['spec'].get('cover'), 'hookLeg': R.hook_leg(10), 'shape': 'STR'})
            det2.draw(sheet.detail_pen(d2, 25, det2.bbox))
        failing = [b for b in ((sch or {}).get('office') or {}).get('beams') or [] if b.get('status') == 'fail']
        forces = []
        if sch and sch.get('office'):
            for b in sch['office']['beams'][:8]:
                fo = b.get('forces') or {}
                m_neg = _nn(fo.get('mNeg'), _nn(b.get('mu_neg'), ''))
                m_pos = _nn(fo.get('mPos'), _nn(b.get('mu_pos'), ''))
                forces.append(f"{js_str(b.get('id'))} {js_round(b['width'] / 50) * 50}x{js_round(b['depth'] / 50) * 50}: SPANS {'+'.join(to_fixed(sp['length'] / 1000, 1) for sp in b['spans'])} m, wu {js_str(b['loads']['wu'])} kN/m, Mu- {js_str(m_neg)} Mu+ {js_str(m_pos)} kN.m")
        if sch:
            kg = beam_steel_kg(sch)
            return {
                'rows': beam_schedule_rows(sch), 'cols': BEAM_SCHEDULE_COLS, 'scheduleTitle': f"BEAM SCHEDULE ({design_label})", 'totals': beam_schedule_totals(sch, kg), 'weight': js_round(kg),
                'elementRows': rows, 'elementCols': cols,
                'planTitles': [f"FRAMING PLAN WITH BEAM MARKS AND SECTIONS - {design_label}"],
                'general': design_notes(model, level)[:2] + ['SLAB OUTLINE, COLUMNS, WALLS, OPENINGS, THICKNESS ZONES AND BEAMS ARE READ FROM THE MODEL. EVERY BEAM CARRIES ITS TYPE (IN BRACKETS), ITS SECTION b x h AND THE BARS OF ITS TYPE BESIDE IT; A COLUMN, A WALL OR A DEEPER BEAM CROSSING A BEAM DIVIDES IT. THE TYPES ARE SCHEDULED HERE WITH THEIR SECTIONS.'] + list(beam_schedule_notes(model, level, sch)),
                'assumptions': forces + level_assumptions(model, level)[:2 if forces else 6],
                'legend': [['OUTLINE', 'SLAB EDGE', 'thick'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid'], ['WALL-HATCH', 'WALL (HATCHED)', 'hatch'], ['BEAM', 'BEAM (HATCHED) - TYPE, SECTION AND BARS BESIDE IT', 'hatch'], ['CALLOUT', f"BEAM NOT DESIGNED{' IN RAM' if sch.get('design') == 'ram' else ''}", 'hatch'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch']],
                'detailsUsed': min(3, nxt),
                'checks': [f"{len(sch['beams'])} beams, {len(sch['types'])} types, {len(sch['undesigned'])} without a design, {len(failing)} not passing the office check."],
            }
        return {
            'rows': rows, 'cols': cols, 'scheduleTitle': 'ELEMENT SCHEDULE',
            'general': design_notes(model, level)[:2] + ['SLAB OUTLINE, COLUMNS, WALLS, OPENINGS, STAIRS, THICKNESS ZONES, LEVELS AND CAMBER NOTES ARE READ FROM THE OFFICE DESIGN PLAN. EDGE BEAMS ARE LABELLED WHERE THE PLAN DRAWS THEM; DETAIL 1 APPLIES ALONG THEM.', 'SEE SHEETS 02 (BOTTOM), 03 (TOP) AND 04 (PUNCHING) FOR REINFORCEMENT; THE GENERAL DETAILS SHEET IS PART OF THIS SET.'],
            'assumptions': level_assumptions(model, level),
            'legend': [['OUTLINE', 'SLAB EDGE', 'thick'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid'], ['WALL-HATCH', 'WALL (HATCHED)', 'hatch'], ['BEAM', 'EDGE BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch'], ['POUR-STRIP-HATCH', 'POUR STRIP', 'hatch']],
            'detailsUsed': 3,
        }
    return draw


def rebar_sheet(model, level, meta, adds, face):
    def draw(sheet, pens):
        global placer
        pl = pens[0]
        S = sheet.S
        spec = model['spec']
        draw_base(sheet, pl, level, {'columnHatchLayer': 's-hatch', 'gridTag': meta.get('gridTag'), 'dims': False, 'pt': False, 'ubarRegions': False, 'regionLabels': False})
        attach_placer(pl, S, level, spec)  # everything written from here on is kept clear of what is already there
        draw_designer_notes(pl, S, level, {'thickness': True, 'zones': False})  # the zone tags are placed after the bars (zoneLabels)
        # office rule: the top sheet carries the top bars and every T&B bar (trimmers, U-bars, diagonals); the bottom sheet the bottom bars only
        faces = ['B'] if face == 'B' else ['T', 'TB']
        draw_existing(pl, S, level['existing'], faces)
        if face == 'B' or level.get('topMesh'):
            draw_mesh_labels(pl, S, level)
        if face == 'B':
            # office rule: the bottom mesh is written at every change of slab thickness (thickened zones, local RC thicknesses)
            tm = spec.get('thicknessMesh') or R.DEFAULT_SPEC['thicknessMesh']
            label = f"BOTTOM MESH T{fmt_num(tm['dia'])}@{fmt_num(tm['spacing'])}"
            # (inside a thickened zone the mesh is written with the zone tag after the bars, see zoneLabels: the drop mesh of detail 4 in a column drop)
            for t in [t for t in (level.get('rcTags') or []) if not any(point_in_polygon(t, z['polygon']) for z in (level.get('thickZones') or []))]:
                pl.text({'x': t['x'], 'y': _nn(t.get('below'), t['y'] - 350)}, label, {'layer': '9_TEXT', 'h': 170 / S, 'align': 'C', 'valign': 'M', 'style': 'BW', 'widthFactor': 0.8})
        mine = [it for it in adds['items'] if it.get('face') in faces]
        for it in mine:
            office_bar(pl, S, it, 'bars')  # bars and dimensions first ...
        zone_labels(pl, S, level, spec, face)  # ... the zone tags at a free corner of their zone ...
        for it in mine:
            office_bar(pl, S, it, 'labels')  # ... then every call-out finds a free place
        if face == 'T':
            for n in adds['notes']:
                at = place_text(pl, {'x': n['x'], 'y': n['y']}, n['text'], {'layer': n.get('layer') or 'DETAIL-REF', 'h': 150 / S, 'align': 'C', 'style': 'BW', 'widthFactor': 0.8}, [{'x': 0, 'y': dy} for dy in [0, 400, -400, 800, -800, 1200, -1200]], S)
                if n.get('box') and at:
                    tw = len(n['text']) * 150 * 0.8 * 0.85 + 200
                    pl.rect({'x': at['x'] - tw / 2, 'y': at['y'] - 100, 'w': tw, 'h': 150 + 200}, {'layer': n.get('layer') or 'DETAIL-REF'})
        if face == 'T' and level.get('topMesh') and level.get('meshSpec'):
            # the top mesh is written at the thickness tag like the bottom one (slab mesh option: both faces)
            tms = level.get('topMeshSpec') or level['meshSpec']
            for t in [t for t in (level.get('rcTags') or []) if not any(point_in_polygon(t, z['polygon']) for z in (level.get('thickZones') or []))]:
                pl.text({'x': t['x'], 'y': _nn(t.get('below'), t['y'] - 350)}, f"TOP MESH T{fmt_num(tms[0])}@{fmt_num(tms[1])}", {'layer': '9_TEXT', 'h': 170 / S, 'align': 'C', 'valign': 'M', 'style': 'BW', 'widthFactor': 0.8})
        placer = None
        lst = adds['bars'][face]
        rows = [r for r in lst.rows() if r.get('note') != 'PUNCHING']
        tot = {'weight_kg': js_round(sum(r['weight_kg'] for r in rows) * 10) / 10}
        used = sorted(dict.fromkeys(it.get('detail') for it in mine), key=lambda v: 'null' if v is None else js_str(v))
        d0 = sheet.detail_box(0, 'GENERAL DETAILS ADDED ON THIS SHEET', '')
        sheet.table(d0['x'] + 3, d0['y'] + d0['h'] - 10, DETAIL_KEY_COLS, details_key_rows(used if used else ['D1']), {'headH': 5, 'rowH': 4, 'h': 1.5, 'maxRows': 12})
        d1 = sheet.detail_box(1, 'MEP VOID REINFORCEMENT (DETAIL 7)', '')
        vcols = [{'key': 'size', 'title': 'VOID (m)', 'w': 26}, {'key': 'long', 'title': 'LONGITUDINAL T&B (EACH SIDE)', 'w': 60}, {'key': 'u', 'title': 'U-BAR', 'w': 34}, {'key': 'diag', 'title': 'DIAGONALS T&B (2 m)', 'w': 50}]
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, vcols, [{'size': f"{fmt_num(VOID_TABLE[i - 1]['max']) if i else 0} - {fmt_num(r['max'])}", 'long': f"{fmt_num(r['long']['n'])}T{fmt_num(r['long']['dia'])}-{fmt_num(r['long']['s'])}", 'u': f"T{fmt_num(r['u']['dia'])}-{fmt_num(r['u']['s'])}", 'diag': f"T{fmt_num(r['diag'])}"} for i, r in enumerate(VOID_TABLE)], {'headH': 5, 'rowH': 4, 'h': 1.5})
        d9 = next((it for it in adds['items'] if it.get('detail') == 'D9'), None) if face == 'T' else None
        d2 = sheet.detail_box(2, 'SECTION - MESH AND EXTRA BOTTOM BARS AT A THICKENED ZONE' if face == 'B' else 'SECTION - BLOCKWORK SUPPORT BEAM THROUGH VOID (DETAIL 9)' if d9 else 'SECTION - U-BAR AT A CORE WALL (DETAIL 2)', '1:20')
        bb9 = spec.get('blockBeam') or R.DEFAULT_SPEC['blockBeam']
        mesh_spec = level.get('meshSpec') or []
        if d9:
            det2 = D.block_beam_section({'h': level['thickness'], 'cover': spec.get('cover'), 'width': d9['blockBeam']['gap'], 'dia': bb9['dia'], 'count': bb9['count'], 'linkDia': bb9['linkDia'], 'linkSpacing': bb9['linkSpacing'], 'ta': d9['blockBeam']['ta']})
        elif face == 'B':
            det2 = D.section_mesh({'h': level['thickness'], 'cover': spec.get('cover'), 'dia': (mesh_spec[0] if mesh_spec else None) or 10, 'lap': R.lap_length(spec, (mesh_spec[0] if mesh_spec else None) or 10), 'spacing': (mesh_spec[1] if len(mesh_spec) > 1 else None) or 150})
        else:
            det2 = D.section_u_edge({'h': level['thickness'], 'cover': spec.get('cover'), 'leg': 1200, 'dia': 12, 'edgeDia': 12, 'spacing': 200})
        det2.draw(sheet.detail_pen(d2, 20, det2.bbox))
        tms = level.get('topMeshSpec') or level.get('meshSpec')
        if level.get('meshSpec'):
            ms = level['meshSpec']
            if level.get('topMesh') and tms and (tms[0] != ms[0] or tms[1] != ms[1]):
                mesh_txt = f"BOTTOM MESH T{fmt_num(ms[0])}@{fmt_num(ms[1])} AND TOP MESH T{fmt_num(tms[0])}@{fmt_num(tms[1])}"
            else:
                mesh_txt = f"MESH T{fmt_num(ms[0])}@{fmt_num(ms[1])} {'TOP & BOTTOM (BOTH FACES)' if level.get('topMesh') else 'BOTTOM ONLY'}"
            mesh_line = f"{mesh_txt} TWO WAY AS LABELLED ON THE PLAN (DESIGN){'; THE TOP MESH RUNS UNDER THE TOP BARS SHOWN, LAPPED AS THE BOTTOM MESH' if level.get('topMesh') and face == 'T' else ''}."
        else:
            mesh_line = 'NO MESH LABEL FOUND ON THE DESIGN PLAN.'
        drops = spec.get('drops') or R.DEFAULT_SPEC['drops']
        tmesh = spec.get('thicknessMesh') or R.DEFAULT_SPEC['thicknessMesh']
        return {
            'rows': rows, 'totals': f"ADDED FROM THE GENERAL DETAILS: {_locale_en(tot['weight_kg'])} kg (DESIGNER'S BARS NOT SCHEDULED HERE)", 'weight': tot['weight_kg'],
            'scheduleTitle': f"BAR SCHEDULE - GENERAL DETAILS ADDITIONS ({'BOTTOM' if face == 'B' else 'TOP'})",
            'planTitles': ['BOTTOM REINFORCEMENT PLAN' if face == 'B' else 'TOP REINFORCEMENT PLAN'],
            'general': design_notes(model, level) + [mesh_line,
                                                     f"BOTTOM SHEET: BOTTOM BARS ONLY. DETAIL 4 INSIDE A COLUMN DROP = THE DROP MESH T{fmt_num(drops['dia'])}@{fmt_num(drops['spacing'])} AS TWO GROUPS THROUGH THE COLUMN (AS LONG AS THE DROP, AT LEAST 1.5 m PAST THE COLUMN FACE); EXTRA BARS 50 dia BEYOND A THICKENED STRIP. THE BOTTOM MESH T{fmt_num(tmesh['dia'])}@{fmt_num(tmesh['spacing'])} IS WRITTEN AT EVERY CHANGE OF SLAB THICKNESS. T&B BARS (TRIMMERS, U-BARS, DIAGONALS) ARE DRAWN ON THE TOP SHEET; THEIR BOTTOM LAYER IS SCHEDULED HERE."
                                                     if face == 'B' else 'TOP SHEET: DETAIL 1 L-BARS ALONG EDGE BEAMS, DETAIL 2 U-BARS AND PARALLEL BARS AT CORE WALLS, DETAIL 5 CORNER DIAGONALS, DETAIL 7 VOID TRIMMERS (T&B); LAP 500 AT THICKNESS STEPS (DETAIL 3).'],
            'assumptions': list(adds['assumptions']) + list(level_assumptions(model, level)) + ['ANCHORAGE-DEPENDENT DETAILS (SLAB EDGE AT LIVE ANCHORS, BURSTING SPIRALS, PAN-BOX TRIMMERS) ARE NOT SHOWN: TO BE ADDED WITH THE TENDON LAYOUT.'],
            'legend': [['REO-BOT' if face == 'B' else 'REO-TOP', 'BOTTOM BAR (B)' if face == 'B' else 'TOP BAR (T)', 'thick'], ['diamension', 'DISTRIBUTION WIDTH', 'line'], ['DOTS', 'BAR / DISTRIBUTION DOT', 'line'], ['DETAIL-REF', 'D# = GENERAL DETAIL REFERENCE', 'line'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid'], ['WALL-HATCH', 'WALL', 'hatch']],
            'detailsUsed': 3,
        }
    return draw


def punching_sheet(model, level, meta, adds):
    def draw(sheet, pens):
        global placer
        pl = pens[0]
        S = sheet.S
        draw_base(sheet, pl, level, {'columnHatchLayer': 's-hatch', 'gridTag': meta.get('gridTag'), 'dims': False, 'pt': False, 'ubarRegions': False, 'regionLabels': False})
        attach_placer(pl, S, level)
        for p in adds['punching']:
            c = p['col']
            w = c['d'] if c.get('shape') == 'circle' else c['w']
            hh = c['d'] if c.get('shape') == 'circle' else c['h']
            # the stirrup strips: legs / 2 closed stirrups side by side leaving every face, `rows` rows at S (grey row lines)
            for dir_ in ['x', 'y']:
                rows, legs = p['dirs'][dir_]['rows'], p['dirs'][dir_]['legs']
                ns = max(1, _whole(legs / 2))
                ln = rows * p['s']
                F = hh if dir_ == 'x' else w
                pitch = F / ns
                sw = max(80, pitch - 60)
                t00 = (c['cy'] if dir_ == 'x' else c['cx']) - F / 2
                for sg in p['dirs'][dir_].get('sides') or [-1, 1]:
                    face = c['cx'] + sg * w / 2 if dir_ == 'x' else c['cy'] + sg * hh / 2

                    # nothing outside the slab: the strips stop at the slab edge / an opening
                    def end_at(d, face=face, sg=sg, dir_=dir_):
                        return {'x': face + sg * d, 'y': c['cy']} if dir_ == 'x' else {'x': c['cx'], 'y': face + sg * d}
                    ln = rows * p['s']
                    while ln > p['s'] and not point_in_polygon(end_at(ln), level['outline']):
                        ln -= p['s']
                    rows_in = js_round(ln / p['s'])
                    for i in range(math.ceil(ns)):  # (JS: `for (let i = 0; i < ns; i++)`)
                        t0 = t00 + pitch * i + (pitch - sw) / 2
                        pl.rect({'x': min(face, face + sg * ln), 'y': t0, 'w': ln, 'h': sw} if dir_ == 'x' else {'x': t0, 'y': min(face, face + sg * ln), 'w': sw, 'h': ln}, {'layer': 'REBAR-PUNCH', 'width': BAR_W})
                        for r in range(1, rows_in + 1):
                            o = face + sg * r * p['s']
                            if dir_ == 'x':
                                pl.line({'x': o, 'y': t0}, {'x': o, 'y': t0 + sw}, {'layer': 'PS-ROW'})
                            else:
                                pl.line({'x': t0, 'y': o}, {'x': t0 + sw, 'y': o}, {'layer': 'PS-ROW'})
                    # "S" at the first row of the outer strip, with its dot
                    s_at = {'x': face + sg * p['s'], 'y': t00 + F + 90} if dir_ == 'x' else {'x': t00 + F + 90, 'y': face + sg * p['s']}
                    pl.circle(s_at, 25, {'layer': 'DOTS'})
                    pl.text(add(s_at, {'x': 0, 'y': 1} if dir_ == 'x' else {'x': 1, 'y': 0}, 60), 'S', {'layer': 'PS-TAG', 'h': 100 / S, 'style': 'BW', 'widthFactor': 0.8, 'align': 'C', 'valign': 'B', 'rot': 0 if dir_ == 'x' else 90})
            # the tag beside the column: PS type over "rows - legs - bar"
            ext = {'x': p['dirs']['x']['rows'] * p['s'], 'y': p['dirs']['y']['rows'] * p['s']}
            base = {'x': c['cx'] + w / 2 + ext['x'] + 200, 'y': c['cy'] + hh / 2 + 150}
            offs = [{'x': x, 'y': y} for x, y in [[0, 0], [0, -hh - 300], [-w - ext['x'] * 2 - 400 - 1400, 0], [-w - ext['x'] * 2 - 400 - 1400, -hh - 300], [0, ext['y'] + 600], [0, -hh - ext['y'] - 900]]]
            q = placer.pick([{'x': base['x'] + d['x'], 'y': base['y'] + d['y']} for d in offs], lambda o: [text_box(o, p['tag'], 150, 0, 'L', 'B', 0.8), text_box({'x': o['x'], 'y': o['y'] + 240}, p['type'], 250, 0, 'L', 'B', 0.8)])
            pl.text({'x': q['x'], 'y': q['y'] + 240}, p['type'], {'layer': 'PS-TAG', 'h': 250 / S, 'style': 'BW', 'widthFactor': 0.8, 'bold': True})
            pl.text(q, p['tag'], {'layer': 'PS-TAG', 'h': 150 / S, 'style': 'BW', 'widthFactor': 0.8})
            if p.get('source') == 'override':
                # the engineer's bypass is written at the column, boxed, so nobody reads the PS as a RAM design
                txt = f"NOT PASSING (vu/phi.vc {js_str(_nn((p.get('check') or {}).get('ratio'), '?'))}) - PS AT THE DESIGN ENGINEER'S RESPONSIBILITY"
                at = place_text(pl, {'x': c['cx'], 'y': c['cy'] - hh / 2 - ext['y'] - 500}, txt, {'layer': 'PS-TAG', 'h': 150 / S, 'align': 'C', 'style': 'BW', 'widthFactor': 0.8}, [{'x': 0, 'y': dy} for dy in [0, -400, -800, 400]], S)
                tw = len(txt) * 150 * 0.8 * 0.85 + 200
                pl.rect({'x': at['x'] - tw / 2, 'y': at['y'] - 100, 'w': tw, 'h': 150 + 200}, {'layer': 'PS-TAG'})
        placer = None
        rows = [{'id': t['id'], 'short': t['short'], 'long': t['long'], 's': t['s'], 'where': t['where'], 'n': len([p for p in adds['punching'] if p.get('type') == t['id']])} for t in adds['psTypes']]
        cols = [{'key': 'id', 'title': 'TYPE', 'w': 18}, {'key': 'short', 'title': 'SHORT DIR.', 'w': 36}, {'key': 'long', 'title': 'LONG DIR.', 'w': 36}, {'key': 's', 'title': 'S', 'w': 14}, {'key': 'n', 'title': 'No.', 'w': 14}, {'key': 'where', 'title': 'COLUMNS', 'w': 67, 'align': 'L', 'max': 38}]
        d0 = sheet.detail_box(0, 'PUNCHING SHEAR REINFORCEMENT DETAIL (DETAIL 12 - PS TYPES)', 'N.T.S.')
        p0 = adds['punching'][0] if adds['punching'] else None
        det0 = D.punching_strips({'h': level['thickness'], 'cover': model['spec'].get('cover'), 'dia': p0['dia'] if p0 else 12, 's': p0['s'] if p0 else 100, 'rows': min(p0['dirs']['x']['rows'], 6) if p0 else 4, 'legs': p0['dirs']['x']['legs'] if p0 else 4})
        det0.draw(sheet.detail_pen(d0, 8, det0.bbox))
        d1 = sheet.detail_box(1, 'TAG KEY', '')
        for i, t in enumerate(['PUNCHING SHEAR RFT BAR TAGS   10R-4-T12', '10R - DENOTES NUMBER OF ROWS (FROM THE COLUMN FACE, AT S)', '4   - DENOTES NUMBER OF LEGS OF STIRRUPS (PER STRIP)', 'T12 - DENOTES BAR GRADE AND DIAMETER', 'S   - SPACING OF ROWS (mm)', 'SHORT DIR. = STRIPS RUNNING PARALLEL TO THE SHORT SIDE OF THE COLUMN', 'LONG DIR.  = STRIPS RUNNING PARALLEL TO THE LONG SIDE OF THE COLUMN']):
            sheet.pp.text(d1['x'] + 4, d1['y'] + d1['h'] - 14 - i * 5, t, {'layer': 'NOTES', 'h': 1.8})
        ram_ps = level.get('ram') is not None
        ovs = [p for p in adds['punching'] if p.get('source') == 'override']
        ov = (model['spec'].get('punching') or {}).get('override')
        check = level.get('punchingCheck')
        bypass = None
        if ovs:
            by_txt = f" - {js_str(ov.get('by')).upper()}" if ov and _t(ov.get('by')) else ''
            date_txt = f", {js_str(ov.get('date'))}" if ov and _t(ov.get('date')) else ''
            bypass = f"ENGINEER'S BYPASS: COLUMNS {', '.join(js_str(p['col'].get('id')) for p in ovs)} DO NOT PASS THE PUNCHING CHECK AND NO THICKENING WAS ADOPTED; THEIR PS TYPES ARE SIZED FROM THE OFFICE ESTIMATE AND PROVIDED AT THE DESIGN ENGINEER'S RESPONSIBILITY{by_txt}{date_txt}."
        check_line = None
        if check and check.get('columns'):
            failing = [k for k in check['columns'] if k.get('status') != 'ok']
            fpc = f", fpc {js_str(check['fpc_mpa'])} MPa" if check.get('fpc_mpa') is not None else ''
            over = ', '.join(f"{js_str(k.get('id'))} {js_str(k.get('ratio'))}" for k in failing) or 'NONE'
            check_line = f"INDICATIVE PUNCHING CHECK (SBC 304 / ACI 318 TWO-WAY SHEAR ON RAM'S TRIBUTARY AREAS AND LOADS, f'c {js_str(check.get('fc'))} MPa{fpc}): {len(failing)} OF {len(check['columns'])} COLUMNS OVER phi.vc ({over}); THE RAM PUNCHING REPORT GOVERNS."
        general = [g for g in [design_notes(model, level)[0], 'PUNCHING SHEAR REINFORCEMENT IS TAGGED PER COLUMN AS "ROWS - LEGS - BAR" (DETAIL 12): CLOSED STIRRUP STRIPS LEAVE EVERY COLUMN FACE, THE FIRST ROW AT S FROM THE FACE; STIRRUPS ENCLOSE THE TOP AND BOTTOM BARS.',
                                    'PS TYPES ARE DERIVED FROM THE STUD RAILS DESIGNED IN RAM CONCEPT (ROWS COVER THE RAIL LENGTH AT S, LEGS MATCH THE STUD AREA PER FACE); COLUMNS WITHOUT RAILS IN RAM CARRY NO PUNCHING REINFORCEMENT.' if ram_ps else 'PRELIMINARY: PS TYPES ARE PLACEHOLDERS (PS1 INTERIOR, PS2 EDGE / CORNER) UNTIL THE PUNCHING DESIGN OF EACH COLUMN IS AVAILABLE; THE DESIGN GOVERNS THE NUMBER OF ROWS AND LEGS.',
                                    bypass, check_line] if _t(g)]
        assumptions = [a for a in [next((t for t in adds['assumptions'] if re.search(r'^D12 PUNCHING:', t)), None) if ram_ps else 'PUNCHING DESIGN NOT AVAILABLE: PS1 = 10R-4-T12 @100 (INTERIOR), PS2 = 12R-4-T12 @100 (EDGE / CORNER) ASSUMED FROM THE GENERAL DETAILS SCHEDULE - TO BE CONFIRMED.',
                                          next((t for t in adds['assumptions'] if re.search(r'^D12 PUNCHING - ENGINEER', t)), None)] + list(level_assumptions(model, level)[:3]) if _t(a)]
        return {
            'rows': rows, 'cols': cols, 'scheduleTitle': 'SCHEDULE OF PUNCHING SHEAR REINFORCEMENT',
            'general': general,
            'assumptions': assumptions,
            'legend': [['REBAR-PUNCH', 'STIRRUP STRIPS (LEGS / 2 PER FACE)', 'thick'], ['PS-ROW', 'ROWS OF STIRRUPS AT S', 'line'], ['PS-TAG', 'PS TYPE / TAG', 'line'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid']],
            'detailsUsed': 2,
        }
    return draw


def design_cover(model, sheets, meta):
    def draw(sheet, pens=None):
        P = sheet.L['plan']
        pp = sheet.pp
        pp.text(P['x'] + 10, P['y'] + P['h'] - 16, (meta.get('project') or '').upper(), {'layer': 'TEXT-TITLE', 'h': 6, 'bold': True})
        pp.text(P['x'] + 10, P['y'] + P['h'] - 26, 'REINFORCEMENT DESIGN DRAWINGS - DRAWING INDEX', {'layer': 'TEXT-TITLE', 'h': 4})
        pp.text(P['x'] + 10, P['y'] + P['h'] - 34, f"{js_str(meta.get('company'))}  ·  {'CLIENT: ' + js_str(meta['client']) + '  ·  ' if _t(meta.get('client')) else ''}{meta.get('location') or ''}  ·  REV {js_str(meta.get('revision'))}  ·  {js_str(meta.get('date'))}", {'layer': 'TITLE', 'h': 2.6})
        cols = [{'key': 'no', 'title': 'DRAWING No.', 'w': 40}, {'key': 'title', 'title': 'DRAWING TITLE', 'w': 205}, {'key': 'level', 'title': 'LEVEL / PART', 'w': 110, 'align': 'L', 'max': 40}, {'key': 'block', 'title': 'BLOCK / XREF NAME', 'w': 150, 'align': 'L'}, {'key': 'scale', 'title': 'SCALE', 'w': 36}, {'key': 'wt', 'title': 'ADDED (kg)', 'w': 40}, {'key': 'rev', 'title': 'REV', 'w': 20}]
        rows = [{'no': s['drawingNo'], 'title': s['title'], 'level': 'ALL' if s['level'] == 'ALL' else f"{s['level']} - {s['levelName']}", 'block': s['blockName'], 'scale': f"1:{js_str(s['scale'])}" if _t(s.get('scale')) else 'NTS', 'wt': _locale_en(js_round(s['weight'])) if _t(s.get('weight')) else '-', 'rev': meta.get('revision')} for s in sheets]
        sheet.table(P['x'] + 10, P['y'] + P['h'] - 42, [{**c, 'align': c.get('align') or ('L' if c['key'] == 'title' else 'C')} for c in cols], rows, {'title': 'DRAWING INDEX / LIST OF SHEETS', 'rowH': 5, 'h': 2, 'headH': 6, 'titleH': 7})
        d0 = sheet.detail_box(0, 'PARTS READ FROM THE DESIGN PLAN', '')
        lcols = [{'key': 'id', 'title': 'ID', 'w': 14}, {'key': 'name', 'title': 'PART', 'w': 70, 'align': 'L', 'max': 34}, {'key': 'thk', 'title': 'THK', 'w': 16}, {'key': 'cols', 'title': 'COLS', 'w': 16}, {'key': 'walls', 'title': 'WALLS', 'w': 16}, {'key': 'op', 'title': 'OPEN.', 'w': 16}, {'key': 'bars', 'title': 'DESIGN BARS', 'w': 24}, {'key': 'area', 'title': 'AREA m²', 'w': d0['w'] - 6 - 172}]
        sheet.table(d0['x'] + 3, d0['y'] + d0['h'] - 10, lcols, [{'id': l['id'], 'name': l['name'], 'thk': l['thickness'], 'cols': len(l['columns']), 'walls': len(l['walls']), 'op': len(l['openings']), 'bars': len(l['existing']['lines']), 'area': js_round(abs(polygon_area(l['outline'])) / 1e6)} for l in model['levels']], {'headH': 5, 'rowH': 4, 'h': 1.6, 'maxRows': 24})
        d1 = sheet.detail_box(1, 'GENERAL DETAILS APPLIED', '')
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, DETAIL_KEY_COLS, details_key_rows(list(DETAILS.keys())), {'headH': 5, 'rowH': 4, 'h': 1.5, 'maxRows': 12})
        d2 = sheet.detail_box(2, 'HOW TO USE THE BLOCKS / XREFS', '')
        for i, h in enumerate(['EACH SHEET IS A BLOCK NAMED AS LISTED AND ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1.', 'REINFORCEMENT LAYERS FOLLOW THE OFFICE DESIGN CONVENTION (REO-TOP, REO-BOT, REO-TXT, diamension, DOTS); SHEET FURNITURE FOLLOWS THE SPAN TECH SPAN- STANDARD.', 'BARS ADDED FROM THE GENERAL DETAILS CARRY A CIRCLED D# ON LAYER DETAIL-REF (FREEZE THE LAYER TO HIDE THE REFERENCES).']):
            pp.mtext(d2['x'] + 4, d2['y'] + d2['h'] - 12 - i * 14, h, {'layer': 'NOTES', 'h': 1.8, 'width': d2['w'] - 8})
        return {'general': [f"DESIGN DRAWINGS GENERATED FROM THE OFFICE DESIGN PLAN: {len(model['levels'])} PART(S) READ."] + list(model['findings']), 'assumptions': [(f"[{a['level']}] " if _t(a.get('level')) else '') + a['text'] for a in model['assumptions']], 'legend': [], 'detailsUsed': 3}
    return draw


# ------------------------------------------------------------------ edits from the app
def bar_id(it, prefix=''):
    """A stable id for a bar: its detail / face and its geometry (rounded to 10 mm), so an edit finds the same bar on the next run."""
    def r(v):
        return js_round(v / 10)
    return f"{prefix}{it.get('detail') or ('RB' if _t(it.get('ram')) else it.get('face') or 'X')}:{r(it['a']['x'])},{r(it['a']['y'])}-{r(it['b']['x'])},{r(it['b']['y'])}"


def apply_edits(level, adds, edits, assumptions=None):
    """
    Applies the reinforcement edits made in the app to this level: `spec.edits` is a list of
      { op: 'delete', id }                       remove the bar
      { op: 'length', id, start, end }           move the start / end along the bar (mm, + = longer), the length re-written
      { op: 'spec', id, l1 }                     new call-out ("T16-150 (T)")
      { op: 'add', face, a, b, l1, level? }      a new bar between two points
    Ids are those of `planData` (barId). Edits that match no bar are reported on the sheet.
    """
    if assumptions is None:
        assumptions = []
    lst = [e for e in (edits or []) if e and (not e.get('level') or e['level'] == level['id'])]
    ex = level.get('existing') or {}
    pools = [
        {'name': 'items', 'arr': adds['items']},
        {'name': 'ram', 'arr': ex.get('items') or []},
        {'name': 'lines', 'arr': ex.get('lines') or []},
    ]
    for pool in pools:
        for it in pool['arr']:
            if not it.get('id'):
                it['id'] = bar_id(it, 'X' if pool['name'] == 'lines' else '')
    applied = 0
    unmatched = []

    def relabel(it):
        L = js_round((dist(it['a'], it['b']) + (it.get('extra') or 0)) / 10) * 10
        if it.get('l2') is not None:
            it['l2'] = f"L={fmt_num(L)}"
        if it.get('length') is not None:
            it['length'] = L

    def _num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return 0
        return 0 if math.isnan(f) else _whole(f)
    for e in lst:
        if e.get('op') == 'add':
            if not e.get('a') or not e.get('b'):
                continue
            a, b = {'x': _num(e['a']['x']), 'y': _num(e['a']['y'])}, {'x': _num(e['b']['x']), 'y': _num(e['b']['y'])}
            if dist(a, b) < 100:
                continue
            it = {'detail': None, 'face': 'B' if e.get('face') == 'B' else 'TB' if e.get('face') == 'TB' else 'T', 'a': a, 'b': b, 'l1': e.get('l1') or 'T12-150 (T)', 'l2': f"L={js_round(dist(a, b) / 10) * 10}", 'side': 1, 'noTag': True, 'edited': True, 'zone': 'EDIT'}
            if it['face'] != 'B':
                it['uEnd'] = {'start': False, 'end': False}
            adds['items'].append(it)
            it['id'] = bar_id(it)
            applied += 1
            continue
        found = None
        for pool in pools:
            it = next((x for x in pool['arr'] if x.get('id') == e.get('id')), None)
            if it:
                found = {'pool': pool, 'it': it}
                break
        if not found:
            unmatched.append(e.get('id'))
            continue
        pool, it = found['pool'], found['it']
        if e.get('op') == 'delete':
            pool['arr'].remove(it)
            applied += 1
        elif e.get('op') == 'length':
            u = unit(it['a'], it['b'])
            ds, de = _num(e.get('start')) or 0, _num(e.get('end')) or 0
            if dist(it['a'], it['b']) - ds - de < 200:
                unmatched.append(e.get('id'))
                continue
            it['a'] = add(it['a'], u, -ds)
            it['b'] = add(it['b'], u, de)
            relabel(it)
            it['edited'] = True
            applied += 1
        elif e.get('op') == 'spec':
            if _t(e.get('l1')):
                it['l1'] = js_str(e['l1'])
                it['edited'] = True
                applied += 1
    if applied or unmatched:
        level['edits'] = {'applied': applied, 'unmatched': unmatched}
        assumptions.append({'level': level['id'], 'text': f"{applied} reinforcement edits made by the engineer in the app applied to {level['name']} (bars deleted, re-lengthed, re-specified or added; the bar schedules count the generated bars only){f'; {len(unmatched)} edits matched no bar on this run and were skipped' if unmatched else ''}."})
    return {'applied': applied, 'unmatched': unmatched}


def plan_data(level, adds):
    """What the app's editor needs: the slab, its supports and every bar with its id."""
    ex = level.get('existing') or {}
    pools = [
        {'name': 'items', 'arr': adds['items'], 'kind': 'office'},
        {'name': 'ram', 'arr': ex.get('items') or [], 'kind': 'ram'},
        {'name': 'lines', 'arr': [l for l in (ex.get('lines') or []) if not l.get('tick')], 'kind': 'design'},
    ]
    bars = []
    for pool in pools:
        for it in pool['arr']:
            if not it.get('id'):
                it['id'] = bar_id(it, 'X' if pool['name'] == 'lines' else '')
            bars.append({'id': it['id'], 'kind': pool['kind'], 'detail': it.get('detail') or None, 'face': it.get('face') or 'T', 'a': {'x': js_round(it['a']['x']), 'y': js_round(it['a']['y'])}, 'b': {'x': js_round(it['b']['x']), 'y': js_round(it['b']['y'])}, 'l1': it.get('l1') or '', 'l2': it.get('l2') or '', 'zone': it.get('zone') or '', 'edited': bool(it.get('edited'))})

    def poly(o):
        return [{'x': js_round(p['x']), 'y': js_round(p['y'])} for p in (o['polygon'] if o.get('polygon') else R.region_polygon(o))]
    grid = level.get('grid')
    return {
        'id': level['id'], 'name': level['name'], 'thickness': level['thickness'], 'bbox': level.get('bbox'),
        'outline': [{'x': js_round(p['x']), 'y': js_round(p['y'])} for p in level['outline']],
        'openings': [{'id': o.get('id'), 'polygon': poly(o)} for o in (level.get('openings') or [])],
        'columns': [{'id': c.get('id'), 'cx': js_round(c['cx']), 'cy': js_round(c['cy']), 'w': js_round(c['d'] if c.get('shape') == 'circle' else c['w']), 'h': js_round(c['d'] if c.get('shape') == 'circle' else c['h']), 'shape': c.get('shape')} for c in (level.get('columns') or [])],
        'walls': [{'id': w.get('id'), 'polygon': poly(w)} for w in (level.get('walls') or []) if w.get('polygon')],
        'beams': [{'id': b.get('id'), 'polygon': poly(b), 'interior': bool(b.get('interior'))} for b in (level.get('beams') or []) if b.get('polygon')],
        'thickZones': [{'id': z.get('id'), 'thickness': z.get('thickness'), 'polygon': poly(z)} for z in (level.get('thickZones') or [])],
        'grid': {'x': [{'label': g.get('label'), 'x': js_round(g['x'])} for g in (grid.get('x') or [])], 'y': [{'label': g.get('label'), 'y': js_round(g['y'])} for g in (grid.get('y') or [])]} if grid else None,
        'bars': bars,
    }


# ------------------------------------------------------------------ package
def compose_design_package(model, meta_in=None):
    meta = {
        'company': 'SPAN TECH CONTRACTING', 'company_line': 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
        'project': 'PROJECT NAME', 'client': '', 'engineer': '', 'contractor': '', 'location': '', 'prefix': 'SPAN-DD', 'revision': '00',
        'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'prepared': '', 'checked': '', 'approved': '', 'status': 'DESIGN DRAWING - FOR REVIEW',
        **(meta_in or {}),
    }
    spec = model['spec']
    jobs = []
    for level in model['levels']:
        cores = mark_core_walls(level)
        if cores['isolated'] or cores['core']:
            model['assumptions'].append({'level': level['id'], 'text': f"{cores['isolated']} isolated walls in {level['name']} carry the column top bars (the group across the wall, 4 m / the drop panel and at least 1.5 m past the wall face each way; the group along it only on a wall up to {fmt_num(((spec.get('topColumns') or {}).get('wallAlongMax') or 6000) / 1000)} m); {cores['core']} core / retaining walls ({cores.get('retaining') or 0} along the slab edge) carry the wall U-bars of detail 2."})
        rule = apply_column_rule(level, spec, model['assumptions'])
        adds = design_additions(level, spec)
        for it in rule['added']:
            adds['items'].append(it)
        adds['items'] = clip_to_slab(level, adds['items'], spec)
        # the column groups are scheduled after the clipping (a bar stopped at an opening is shorter and ends in a U)
        for it in rule['added']:
            if any(it is x for x in adds['items']):
                adds['bars']['T'].add({'dia': spec['topColumns']['dia'], 'shape': f"{it['shape']} (U AT OPENING)" if it.get('clippedOpening') else it['shape'], 'length': it['length'], 'qty': it['n'], 'spacing': spec['topColumns']['spacing'], 'zone': f"{'BEAM' if it.get('beam') else 'COLUMN'} {js_str(it.get('column'))} {it['dir'].upper()}"})
        if level.get('existing'):
            ex = level['existing']
            ex['lines'] = clip_to_slab(level, ex['lines'], spec)
            if ex.get('items'):
                ex['items'] = clip_to_slab(level, ex['items'], spec)
            # the designer's / the column rule's distribution DIMENSIONs stop before an opening as well
            for d in ex.get('dims') or []:
                if d.get('x3') is None:
                    continue
                p, q = {'x': d['x3'], 'y': d['y3']}, {'x': d['x4'], 'y': d['y4']}
                os_ = _outside_openings(level, p, q, mid(p, q))
                if not os_:
                    d['dropped'] = True
                    continue
                if dist(os_[0], p) > 1 or dist(os_[1], q) > 1:
                    d['x3'], d['y3'], d['x4'], d['y4'] = os_[0]['x'], os_[0]['y'], os_[1]['x'], os_[1]['y']
                    d['x2'] = d['y2'] = None
                    d['text'] = None
            ex['dims'] = [d for d in ex['dims'] if not d.get('dropped')]
        # the engineer's edits from the app (delete / lengthen / re-spec / add bars), by stable bar id
        apply_edits(level, adds, spec.get('edits'), model['assumptions'])
        level['planData'] = plan_data(level, adds)
        level['additions'] = {'items': len(adds['items']), 'weight': {'T': adds['bars']['T'].totals()['weight_kg'], 'B': adds['bars']['B'].totals()['weight_kg']}}
        makers = {
            'dframing': framing_sheet,
            'dbottom': lambda m, l, mt, a: rebar_sheet(m, l, mt, a, 'B'),
            'dtop': lambda m, l, mt, a: rebar_sheet(m, l, mt, a, 'T'),
            'dpunch': punching_sheet,
            'dcablat': lambda m, l, mt, a: ram_cables_sheet(m, l, mt, set='latitude', variant='design'),
            'dcablon': lambda m, l, mt, a: ram_cables_sheet(m, l, mt, set='longitude', variant='design'),
        }
        for def_ in DESIGN_SHEETS:
            if def_.get('ramOnly') and level.get('ram') is None:
                continue
            if def_.get('set') and not any(t.get('spanSet') == def_['set'] for t in ((level.get('ram') or {}).get('tendons') or [])):
                continue
            if def_.get('needsBeams') and not ((level.get('beamSchedule') or {}).get('types') or []):
                continue
            jobs.append({'level': level, 'def': def_, 'draw': makers[def_['key']](model, level, meta, adds)})
    total = len(jobs) + 1
    sheets = [build_sheet(model=model, level=j['level'], def_=j['def'], meta=meta, index=i + 2, total=total, draw=j['draw']) for i, j in enumerate(jobs)]
    cover = build_sheet(model=model, level=None, def_={'key': 'cover', 'base': 'DESIGN_DRAWINGS_COVER_INDEX', 'title': 'COVER SHEET / DRAWING INDEX', 'no': '000'}, meta=meta, index=1, total=total, draw=design_cover(model, sheets, meta))
    all_ = [cover] + sheets
    plan = [l['planData'] for l in model['levels'] if l.get('planData')]
    for s in all_:
        for n, d in OFFICE_LAYERS.items():
            s['root'].layer(n, d)
        s['root'].text_style_def(OFFICE_TEXT_STYLE['name'], {'font': OFFICE_TEXT_STYLE['font'], 'widthFactor': OFFICE_TEXT_STYLE['widthFactor']})
        s['root'].dim_style_def('DIM100', DIM100)
    pack = pack_sheets(all_, meta, {'textStyles': {OFFICE_TEXT_STYLE['name']: {'font': OFFICE_TEXT_STYLE['font'], 'widthFactor': OFFICE_TEXT_STYLE['widthFactor']}}})
    pack['plan'] = plan
    return pack
