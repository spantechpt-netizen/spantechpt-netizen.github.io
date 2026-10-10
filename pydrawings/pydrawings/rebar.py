"""
Reinforcement engine: development / lap lengths, bar splitting, and the
zone generators behind each rebar sheet.

Code basis (applied unless the drawings say otherwise): SBC 304-18, the
Saudi Building Code concrete structures requirements, which adopts
ACI 318-14. Clause references below are to SBC 304-18 / ACI 318-14.

Port of `shopdrawings/lib/rebar.mjs` (line by line). Records are plain dicts with the JS keys.

Note on the `_supports` cache: the JS version keeps the merged-support list on the level as a non-enumerable
property (`Object.defineProperty(level, '_supports', { enumerable: false })`) so that it never reaches
`model.json`. Python dicts have no non-enumerable keys and are not weak-referenceable, so `support_columns`
stores the cache under the private key `'_supports'` (see `SUPPORTS_KEY`) of the level dict. **Whoever writes
the model to JSON must drop keys starting with `_`** (e.g. `json.dumps(obj, default=...)` after a
`{k: v for k, v in level.items() if not k.startswith('_')}` pass); `level['maxSpan']` on the other hand IS an
ordinary enumerable property in JS and stays in the file.
"""
import math
import re

from .geometry import (
    bbox, ceil_to, chords_at_x, chords_at_y, circle_polygon, dist, edges, grow_rect,
    perimeter, point_in_polygon, polygon_area, rect_polygon, subtract_intervals, js_round, fmt_num, dist_to_polygon,
)

DEFAULT_SPEC = {
    'fc': 30,  # MPa — assumed if the drawing does not state concrete grade
    'fy': 420,  # MPa — Grade 60 deformed bars (SASO ASTM A615)
    'cover': 25,  # mm top and bottom, slab not exposed to weather
    'stock': 12000,  # mm — standard stock bar length
    'lambda': 1,  # normal-weight concrete
    'bottom': {'dia': 12, 'spacing': 200},  # bottom bonded mesh in PT zones, both ways
    # top bars over columns, both ways. Office rule: an interior column bar covers the drop panel when there is
    # one, otherwise `length` (4 m, set per slab); an edge column bar ends in a U at the edge and runs `edgeFactor`
    # of the interior length on top. rule: 'office' | 'code' (ln/6 each side, SBC 304-18 §8.7.5.5)
    'topColumns': {'dia': 16, 'spacing': 150, 'rule': 'office', 'length': 4000, 'edgeFactor': 0.7, 'dropMargin': 0, 'dropMax': 6000, 'minBeyond': 1500, 'wallAlongMax': 6000},
    # perimeter bars between the column top bars (office rule): T12@150, a U of `total` length at a free edge
    # (equal top and bottom legs), an L of the same 4 m total at an edge beam (`beamLeg` down into the beam + `beamTop` on top)
    'uEdge': {'dia': 12, 'spacing': 150, 'total': 4000, 'beamLeg': 400, 'beamTop': 3600, 'leg': 1200},
    'uCircle': {'dia': 12, 'spacing': 150, 'leg': 1200},  # U-bars around circular regions
    'edgeBars': {'dia': 12, 'count': 2},  # longitudinal bars inside edge U-bars, top and bottom
    'ringBars': {'dia': 12, 'count': 2},  # ring bars around circular regions, top and bottom
    'voids': {'dia': 12, 'count': 2},  # trimmer bars each side of a void, top and bottom
    'openings': {'dia': 16, 'count': 2, 'diagDia': 12, 'diagCount': 2, 'uDia': 12, 'uSpacing': 200, 'uLeg': 600},
    'sunken': {'dia': 12, 'count': 2, 'uDia': 10, 'uSpacing': 200, 'uLeg': 600},  # trimmers and hairpins at sunken-slab steps
    'punching': {'dia': 10, 'legSpacing': 100, 'extentFactor': 2.0, 'psDia': 12, 'rowSpacing': 100},  # shop: preliminary links; design: the office PS detail (rows - legs - T12 @ rowSpacing)
    'walls': {'parallelBars': False, 'cornerDiagonals': False},  # design mode: the wall face gets the U-bars only unless these are switched on
    'perimSpan': 12000,  # design mode: one perimeter bar symbol every 12 m on a long indication line along the edge
    'thicknessMesh': {'dia': 10, 'spacing': 200},  # office rule: the bottom mesh written at every change of slab thickness (per the design)
    'drops': {'dia': 12, 'spacing': 150, 'leg': 500},  # office rule: the bottom mesh inside a column drop (detail 4 groups through the column, 500 legs at both ends)
    'barOffset': 500,  # design mode: the bar symbol sits beside the column (a vertical bar to its left, a horizontal one above it)
    'pourStrip': {'dia': 12, 'spacing': 200, 'length': 2000, 'uDia': 12, 'uSpacing': 200, 'uTotal': 2400, 'longDia': 12, 'longSpacing': 150, 'wall': {'uTotal': 2500, 'uSlab': 2000, 'dia': 12, 'spacing': 200, 'length': 2000, 'longDia': 12, 'longSpacing': 150}},  # the office pour strip detail: T12@200 T&B L=2000 lapping across each joint, U-bars T12@200 L=2400 closed at each face with the legs into the slab, T12@150 T&B along; against a retaining wall: U-bar T12@200 L=2500 anchored in the wall, U-bar T12@200 L=2000 from the slab side, T12@200 T&B L=2000 from the wall face into the slab, T12@150 T&B along
    'blockBeam': {'dia': 16, 'count': 2, 'linkDia': 12, 'linkSpacing': 200, 'minWidth': 150, 'maxGap': 500},  # detail 9 (office): a slab strip of 150..500 between two openings gets 2T16 T&B with T12@200 links
}

# the private key of the merged-support cache on a level dict (see the module docstring)
SUPPORTS_KEY = '_supports'


def _o(o, kw):
    """Merge a JS-style options dict with keyword arguments (keywords win)."""
    out = dict(o or {})
    out.update(kw)
    return out


def _nn(v, default):
    """JS `v ?? default`."""
    return default if v is None else v


def _unique(items):
    """JS `[...new Set(items)]` for a list of (unhashable) records: first occurrence kept, identity compared."""
    out = []
    for it in items:
        if not any(x is it for x in out):
            out.append(it)
    return out


def _object_values(d):
    """JS `Object.values(obj)`: non-negative integer keys first in ascending order, the rest in insertion order."""
    ints = sorted(k for k in d if isinstance(k, (int, float)) and not isinstance(k, bool) and k >= 0 and float(k).is_integer())
    rest = [k for k in d if k not in ints]
    return [d[k] for k in ints] + [d[k] for k in rest]


def _sign(v):
    """JS `Math.sign`."""
    return (v > 0) - (v < 0)


def BAR_AREA(dia):
    return (math.pi * dia * dia) / 4


def bar_weight_per_m(dia):
    return 0.006165 * dia * dia  # kg/m, density 7850 kg/m³


def development_length(spec, dia, opts=None, **kw):
    """
    Tension development length, SBC 304-18 §25.4.2.3 (ACI 318-14 Table 25.4.2.2),
    simplified expressions with clear spacing / cover conditions satisfied.
    Metric form: ld = fy·ψt·ψe / (2.1·λ·√f'c) · db for db ≤ 20 mm,
                 ld = fy·ψt·ψe / (1.7·λ·√f'c) · db for db > 20 mm.
    """
    o = _o(opts, kw)
    top = o.get('top', False)
    epoxy = o.get('epoxy', False)
    psi_t = 1.3 if top else 1.0
    psi_e = 1.2 if epoxy else 1.0
    product = min(psi_t * psi_e, 1.7)
    k = 2.1 if dia <= 20 else 1.7
    ld = (spec['fy'] * product) / (k * (spec.get('lambda') or 1) * math.sqrt(spec['fc'])) * dia
    return ceil_to(max(ld, 300), 10)


def lap_length(spec, dia, opts=None, **kw):
    """Class B tension lap splice, §25.5.2.1: 1.3·ld, not less than 300 mm."""
    return ceil_to(max(1.3 * development_length(spec, dia, _o(opts, kw)), 300), 50)


def hook_development_length(spec, dia):
    """Standard 90° hook development, §25.4.3.1: 0.24·ψe·fy/(λ√f'c)·db ≥ max(8db, 150)."""
    ldh = (0.24 * spec['fy']) / ((spec.get('lambda') or 1) * math.sqrt(spec['fc'])) * dia
    return ceil_to(max(ldh, 8 * dia, 150), 10)


def hook_leg(dia):
    """90° hook extension for a straight bar terminating at a free edge: 12·db, §25.3.1."""
    return ceil_to(12 * dia, 10)


def length_table(spec, dias=(10, 12, 14, 16, 18, 20, 25)):
    """Summary table of lengths per diameter, used in the notes block."""
    return [{
        'dia': dia,
        'ld_bottom': development_length(spec, dia),
        'ld_top': development_length(spec, dia, top=True),
        'lap_bottom': lap_length(spec, dia),
        'lap_top': lap_length(spec, dia, top=True),
        'ldh': hook_development_length(spec, dia),
    } for dia in dias]


def split_run(L, opts=None, **kw):
    """
    Split a run of length L into stock pieces overlapping by `lap`. With
    `stagger` the first piece is a half stock so adjacent bars lap in
    different places (≤ 50 % of bars lapped at one section).
    Returns cutting lengths rounded up to 10 mm.
    """
    o = _o(opts, kw)
    stock = o['stock']
    lap = o['lap']
    stagger = o.get('stagger', False)
    if L <= stock:
        return [ceil_to(L, 10)]
    pieces = []
    covered = 0
    first = True
    while covered < L - 1:
        start = 0 if first else covered - lap
        ln = min(stock, L - start)
        if first and stagger:
            ln = min(ln, ceil_to(stock / 2, 100))
        pieces.append(ceil_to(ln, 10))
        covered = start + ln
        first = False
        if len(pieces) > 100:
            break
    return pieces


class BarList:
    """
    Accumulates bar entries and issues marks per (dia, shape, cutting length),
    the way the reference drawings do (`T2-05` = fifth cutting length of the
    top layer 2). Spacing is informational: the same mark may be placed at
    different spacings in different rows.
    """

    def __init__(self, prefix='M'):
        self.prefix = prefix if prefix.endswith('-') else prefix + ('-' if len(prefix) > 1 else '')
        self.entries = []

    def add(self, e):
        # e: { dia, shape, length, qty, spacing?, zone, note? }
        key = f"{fmt_num(e['dia'])}|{e['shape']}|{fmt_num(e['length'])}|{e.get('note') or ''}"
        m = next((x for x in self.entries if x['key'] == key), None)
        if not m:
            # `spacings` / `zones` are JS Sets: ordered lists without repeats here
            m = {'key': key, 'mark': '', 'dia': e['dia'], 'shape': e['shape'], 'length': e['length'], 'spacings': [], 'note': e.get('note') or '', 'qty': 0, 'zones': []}
            self.entries.append(m)
            self.rows()  # keep marks stable as entries arrive
        m['qty'] += e['qty']
        if e.get('spacing'):
            if e['spacing'] not in m['spacings']:
                m['spacings'].append(e['spacing'])
        if e.get('zone'):
            if e['zone'] not in m['zones']:
                m['zones'].append(e['zone'])
        return m

    def rows(self):
        """Sorted rows with marks, totals and weights."""
        sorted_ = sorted(self.entries, key=lambda a: (a['dia'], a['shape'], -a['length']))
        for i, m in enumerate(sorted_):
            m['mark'] = f"{self.prefix}{i + 1:02d}"
        return [{
            'mark': m['mark'], 'dia': m['dia'], 'shape': m['shape'],
            'spacing': '-' if len(m['spacings']) == 0 else m['spacings'][0] if len(m['spacings']) == 1 else 'VAR.',
            'length': m['length'], 'qty': m['qty'],
            'total_m': js_round((m['length'] * m['qty']) / 100) / 10,
            'weight_kg': js_round((m['length'] * m['qty'] / 1000) * bar_weight_per_m(m['dia']) * 10) / 10,
            'zones': ', '.join(m['zones']), 'note': m['note'],
        } for m in sorted_]

    def totals(self):
        rows = self.rows()
        by_dia = {}
        for r in rows:
            by_dia[r['dia']] = by_dia.get(r['dia']) or {'dia': r['dia'], 'total_m': 0, 'weight_kg': 0}
            by_dia[r['dia']]['total_m'] += r['total_m']
            by_dia[r['dia']]['weight_kg'] += r['weight_kg']
        weight = sum(r['weight_kg'] for r in rows)
        return {'weight_kg': js_round(weight * 10) / 10, 'byDia': [{**d, 'total_m': js_round(d['total_m'] * 10) / 10, 'weight_kg': js_round(d['weight_kg'] * 10) / 10} for d in _object_values(by_dia)]}


def merge_rows(*lists):
    """Merge several bar lists into one set of schedule rows (marks kept)."""
    return [r for l in lists for r in l.rows()]


def merge_totals(*lists):
    rows = merge_rows(*lists)
    by_dia = {}
    for r in rows:
        by_dia[r['dia']] = by_dia.get(r['dia']) or {'dia': r['dia'], 'total_m': 0, 'weight_kg': 0}
        by_dia[r['dia']]['total_m'] += r['total_m']
        by_dia[r['dia']]['weight_kg'] += r['weight_kg']
    return {'weight_kg': js_round(sum(r['weight_kg'] for r in rows) * 10) / 10, 'byDia': [{**d, 'total_m': js_round(d['total_m'] * 10) / 10, 'weight_kg': js_round(d['weight_kg'] * 10) / 10} for d in _object_values(by_dia)]}


# rows whose chords agree within `tol` are one group (a curved or skew edge otherwise gives one mark per bar)
def _rows_same(a, b, tol=5):
    return len(a) == len(b) and all(abs(c[0] - b[i][0]) < tol and abs(c[1] - b[i][1]) < tol for i, c in enumerate(a))


def _opening_cuts(level, axis, coord, cover):
    # Intervals along `axis` where a bar at `coord` (perpendicular axis) crosses an opening.
    cuts = []
    for o in level.get('openings') or []:
        poly = region_polygon(o)
        chords = chords_at_y(poly, coord) if axis == 'x' else chords_at_x(poly, coord)
        for a, b in chords:
            cuts.append([a - cover, b + cover])
    return cuts


def region_polygon(o):
    if o.get('kind') == 'circle':
        return circle_polygon(o['cx'], o['cy'], o['r'], 36)
    if o.get('kind') == 'rect':
        return rect_polygon(o['rect'])
    return o['polygon']


def region_bbox(o):
    return bbox(region_polygon(o))


# Bars parallel to X are layer "2", bars parallel to Y are layer "1" (reference drawing convention).
LAYER_CODE = {'X': '2', 'Y': '1'}


def bottom_mesh(level, spec):
    """Sheet: bottom mesh in PT zones (or over the whole slab when no zone is drawn)."""
    s = spec['bottom']
    lap = lap_length(spec, s['dia'])
    lists = {'X': BarList('B2'), 'Y': BarList('B1')}
    zones = []
    cover = spec['cover']
    pt_zones = level['pt']['zones'] if level['pt']['zones'] else [{'id': 'PT1', 'polygon': level['outline']}]
    group_tol = _nn(s.get('groupTol'), 250)
    length_step = _nn(s.get('lengthStep'), 500)
    varied = False
    for zone in pt_zones:
        poly = zone['polygon']
        b = bbox(poly)
        for dir_ in ['X', 'Y']:
            along = 'x' if dir_ == 'X' else 'y'
            bars = lists[dir_]
            start = (b['minY'] if dir_ == 'X' else b['minX']) + cover + s['spacing'] / 2
            end = (b['maxY'] if dir_ == 'X' else b['maxX']) - cover
            groups = []
            c = start
            while c <= end:
                chords = chords_at_y(poly, c) if dir_ == 'X' else chords_at_x(poly, c)
                chords = [[a + cover, bb - cover] for a, bb in chords]
                chords = [[a, bb] for a, bb in chords if bb - a > 300]
                chords = subtract_intervals(chords, _opening_cuts(level, along, c, cover))
                if not chords:
                    c += s['spacing']
                    continue
                last = groups[-1] if groups else None
                if last and _rows_same(last['ref'], chords, group_tol):
                    last['rows'] += 1
                    last['end'] = c
                    # the group bar covers every row of the group: union of the chords
                    last['chords'] = [[min(a, chords[i][0]), max(bb, chords[i][1])] for i, (a, bb) in enumerate(last['chords'])]
                    if not _rows_same(last['chords'], chords):
                        last['varied'] = True
                else:
                    groups.append({'chords': chords, 'ref': chords, 'rows': 1, 'start': c, 'end': c})
                c += s['spacing']
            if any(g.get('varied') for g in groups):
                varied = True
            # a curved / skew edge: many one- or two-row groups; their cut lengths are binned to `lengthStep`
            # and consecutive groups that fall in the same bins are merged into one drawn group
            curved = len([g for g in groups if g['rows'] < 3]) >= 5 or len(groups) > 8
            if curved:
                varied = True

                def binned(g):
                    return '|'.join(fmt_num(ceil_to(bb - a, length_step)) for a, bb in g['chords'])

                merged = []
                for g in groups:
                    last = merged[-1] if merged else None
                    if last and len(last['chords']) == len(g['chords']) and binned(last) == binned(g):
                        last['rows'] += g['rows']
                        last['end'] = g['end']
                        last['chords'] = [[min(a, g['chords'][i][0]), max(bb, g['chords'][i][1])] for i, (a, bb) in enumerate(last['chords'])]
                    else:
                        merged.append({**g, 'varied': True})
                groups[:] = merged
            for gi, g in enumerate(groups):
                g['id'] = f"{zone['id']}-{'B2' if LAYER_CODE[dir_] == '2' else 'B1'}-{gi + 1}"
                runs = []
                for a, bb in g['chords']:
                    L = bb - a
                    pieces = [(ceil_to(ln, length_step) if curved else ln) for ln in split_run(L, stock=spec['stock'], lap=lap)]
                    marks = [bars.add({'dia': s['dia'], 'shape': 'STR', 'length': ln, 'qty': g['rows'], 'spacing': s['spacing'], 'zone': g['id']}) for ln in pieces]
                    runs.append({'a': a, 'b': bb, 'L': L, 'pieces': pieces, 'marks': marks})
                g['runs'] = runs
            zones.append({'id': f"{zone['id']}-{dir_}", 'zoneId': zone['id'], 'dir': dir_, 'code': f"B{LAYER_CODE[dir_]}", 'polygon': poly, 'groups': groups, 'spacing': s['spacing'], 'dia': s['dia']})
    return {
        'zones': zones, 'lists': lists, 'lap': lap, 'dia': s['dia'], 'spacing': s['spacing'], 'varied': varied,
        'assumptions': (
            ([] if level['pt']['zones'] else ['No PT zone boundary found on the drawing: bottom mesh applied over the whole slab.'])
            + ([f"Mesh rows at curved / skew edges: rows are grouped within {fmt_num(group_tol)} mm and cut lengths are scheduled in {fmt_num(length_step)} mm steps (the group's longest row rounded up); bars are cut to the edge less cover on site."] if varied else [])
        ),
    }


def neighbour(level, col, dir_, sign):
    # Nearest column along dir ('x' or 'y') on the same line (within a 1.5 m band).
    perp = 'cy' if dir_ == 'x' else 'cx'
    along_key = 'cx' if dir_ == 'x' else 'cy'
    # a long support (wall) looks for the next support anywhere along its own length
    half_perp = ((col.get('d') or 0) if col.get('shape') == 'circle' else ((col.get('h') if dir_ == 'x' else col.get('w')) or 0)) / 2
    best = None
    sup = level.get(SUPPORTS_KEY)
    for o in (sup['list'] if sup and sup.get('list') else level['columns']):
        if o is col or o.get('id') == col.get('id') or any(m.get('id') == o.get('id') for m in (col.get('merged') or [])) or any(m.get('id') == col.get('id') for m in (o.get('merged') or [])):
            continue
        if abs(o[perp] - col[perp]) > half_perp + 1500:
            continue
        d = (o[along_key] - col[along_key]) * sign
        if d <= 0:
            continue
        if not best or d < best['d']:
            best = {'col': o, 'd': d}
    return best


def edge_distance(level, col, dir_, sign, cover):
    # Distance from column centre to slab edge along dir, in direction sign: a march from the centre to the first
    # point outside the outline (robust at notches and where the outline has a vertex on the column's axis)
    # (marched from the centre and from either side of the column's footprint: a column whose axis lies on an
    # outline edge, half in a perimeter wall, still reads the slab on its far side)
    across = col['d'] if col.get('shape') == 'circle' else col['h'] if dir_ == 'x' else col['w']
    step, max_ = 25, 15000
    best = -1
    for off in [0, across / 2 - 30, -(across / 2 - 30)]:
        c0 = {'x': col['cx'], 'y': col['cy'] + off} if dir_ == 'x' else {'x': col['cx'] + off, 'y': col['cy']}
        if not point_in_polygon(c0, level['outline']):
            continue
        d = 0
        while d < max_:
            q = {'x': c0['x'] + sign * (d + step), 'y': c0['y']} if dir_ == 'x' else {'x': c0['x'], 'y': c0['y'] + sign * (d + step)}
            if not point_in_polygon(q, level['outline']):
                break
            d += step
        if d > best:
            best = d  # d = max: no edge within reach in this direction
    if best >= 0:
        return max(0, best - cover)
    chords = chords_at_y(level['outline'], col['cy']) if dir_ == 'x' else chords_at_x(level['outline'], col['cx'])
    c = col['cx'] if dir_ == 'x' else col['cy']
    for a, b in chords:
        if c >= a - 1 and c <= b + 1:
            return (b - c if sign > 0 else c - a) - cover
    return 2000  # column outside the outline chords (e.g. on a notch); conservative stub


U_BOTTOM_LEG = 500


def top_edge_end(level, spec):
    """
    Office rule: a top bar that ends at the outer slab edge or at an opening
    ends in a U (down the slab depth and back 500 mm at the bottom). Returns
    the extra length added at such an end, its label and the shape code.
    """
    leg = ceil_to((level['thickness'] - 2 * spec['cover']) + U_BOTTOM_LEG, 10)
    return {'leg': leg, 'label': f"U{U_BOTTOM_LEG}", 'note': f"U end: {fmt_num(level['thickness'] - 2 * spec['cover'])} down + {U_BOTTOM_LEG} bottom"}


def _near_segment(p, a, b, tol):
    """p within `tol` of segment a-b (the inline lambda of edgeEndAt / topAtColumns)."""
    L = dist(a, b) or 1
    t = max(0, min(L, ((p['x'] - a['x']) * (b['x'] - a['x']) + (p['y'] - a['y']) * (b['y'] - a['y'])) / L))
    return math.hypot(p['x'] - (a['x'] + (b['x'] - a['x']) / L * t), p['y'] - (a['y'] + (b['y'] - a['y']) / L * t)) < tol


def column_on_beam(level, c):
    """
    A column standing on a beam (an edge beam, an interior beam - not a band, which is slab) does not punch the slab:
    the beam carries it. True when the beam's body passes through the column (its centre inside the beam polygon, or
    the polygon within half the column's smaller side of the centre).
    """
    cc = {'x': c['cx'], 'y': c['cy']}
    half = min(c['d'] if c.get('shape') == 'circle' else c['w'], c['d'] if c.get('shape') == 'circle' else c['h']) / 2
    return next((b for b in (level.get('beams') or []) if b.get('polygon') and not b.get('band') and (point_in_polygon(cc, b['polygon']) or dist_to_polygon(cc, b['polygon']) < half)), None)


def edge_end_at(level, spec, p):
    """
    Office rule for a top bar ending at the slab boundary: a U (500 bottom leg) at a free edge, an L
    (`uEdge.beamLeg` down into the beam) where the outer edge carries a beam parallel to it. The
    nearest outline segment to the bar end decides; an opening edge is always a U.
    """
    u = top_edge_end(level, spec)
    if any(_near_segment(p, e['a'], e['b'], 600) for e in (level.get('jointEdges') or [])):
        return {'type': None, 'leg': 0, 'label': '', 'note': 'continues into the neighbouring part'}
    outline = level.get('outline') or []
    best = None
    for i in range(len(outline)):
        a, b = outline[i], outline[(i + 1) % len(outline)]
        L = dist(a, b) or 1
        t = max(0, min(L, ((p['x'] - a['x']) * (b['x'] - a['x']) + (p['y'] - a['y']) * (b['y'] - a['y'])) / L))
        d = math.hypot(p['x'] - (a['x'] + ((b['x'] - a['x']) / L) * t), p['y'] - (a['y'] + ((b['y'] - a['y']) / L) * t))
        if not best or d < best['d']:
            best = {'d': d, 'a': a, 'b': b}
    if best and best['d'] < 600 and edge_has_beam(level, best['a'], best['b']):
        leg = (spec.get('uEdge') or {}).get('beamLeg') or 400
        return {'type': 'L', 'leg': leg, 'label': f"L{fmt_num(leg)}", 'note': f"L end: {fmt_num(leg)} down into the edge beam"}
    return {'type': 'U', **u}


def side_lining(level, a, b):
    """
    What lines one side of an opening: 'beam' (a beam line parallel within 400 mm over half the
    side), 'wall' (a wall polygon edge), 'column' (a column face), or null for a free side.
    """
    dx, dy = b['x'] - a['x'], b['y'] - a['y']
    ln = math.hypot(dx, dy) or 1
    ux, uy = dx / ln, dy / ln

    def dist_to_seg(p, e):
        L2 = e['length'] * e['length'] or 1
        t = max(0, min(1, ((p['x'] - e['a']['x']) * e['dx'] + (p['y'] - e['a']['y']) * e['dy']) / L2))
        return math.hypot(p['x'] - (e['a']['x'] + e['dx'] * t), p['y'] - (e['a']['y'] + e['dy'] * t))

    def covers(sg):
        if sg['length'] < 200:
            return False
        vx, vy = sg['dx'] / sg['length'], sg['dy'] / sg['length']
        if abs(ux * vx + uy * vy) < 0.95:
            return False
        t1 = (sg['a']['x'] - a['x']) * ux + (sg['a']['y'] - a['y']) * uy
        t2 = (sg['b']['x'] - a['x']) * ux + (sg['b']['y'] - a['y']) * uy
        lo, hi = max(0, min(t1, t2)), min(ln, max(t1, t2))
        if hi - lo < 0.5 * ln:
            return False
        mid = {'x': a['x'] + ux * (lo + hi) / 2, 'y': a['y'] + uy * (lo + hi) / 2}
        return dist_to_seg(mid, sg) < 400

    def seg_of(p, q):
        ddx, ddy = q['x'] - p['x'], q['y'] - p['y']
        return {'a': p, 'b': q, 'dx': ddx, 'dy': ddy, 'length': math.hypot(ddx, ddy)}

    for w in level.get('walls') or []:
        if w.get('polygon') and any(covers(e) for e in edges(w['polygon'])):
            return 'wall'
    for bm in level.get('beams') or []:
        if covers(seg_of(bm['a'], bm['b'])):
            return 'beam'
    for c in level.get('columns') or []:
        poly = region_polygon({'kind': 'circle', 'cx': c['cx'], 'cy': c['cy'], 'r': c['d'] / 2}) if c.get('shape') == 'circle' else [{'x': c['cx'] - c['w'] / 2, 'y': c['cy'] - c['h'] / 2}, {'x': c['cx'] + c['w'] / 2, 'y': c['cy'] - c['h'] / 2}, {'x': c['cx'] + c['w'] / 2, 'y': c['cy'] + c['h'] / 2}, {'x': c['cx'] - c['w'] / 2, 'y': c['cy'] + c['h'] / 2}]
        if any(covers(e) for e in edges(poly)):
            return 'column'
    return None


def opening_lined(level, region):
    """
    Office rule: an opening enclosed by concrete walls, beams (or column faces at its corners)
    needs no additional trimmer bars, only the L-bars along its beams and the wall U-bars.
    """
    poly = region_polygon(region)
    sides = [e for e in edges(poly) if e['length'] > 200]
    if not sides:
        return False
    return all(side_lining(level, side['a'], side['b']) is not None for side in sides)


def edge_has_beam(level, a, b):
    """
    True when the slab edge a->b carries an edge beam: a beam line lies ON the edge (within 60 mm, over half
    the edge or 2 m) and its partner line runs parallel 150..900 mm inside (the beam's inner face). A beam
    merely near the edge (an interior beam beside it) is not an edge beam. `spec.edgeBeams === false` disables.
    """
    if level.get('noEdgeBeams'):
        return False
    L = dist(a, b) or 1
    ux, uy = (b['x'] - a['x']) / L, (b['y'] - a['y']) / L

    def along(p):
        return (p['x'] - a['x']) * ux + (p['y'] - a['y']) * uy

    def off(p):
        return (p['x'] - a['x']) * -uy + (p['y'] - a['y']) * ux  # signed distance from the edge line

    def parallel(bm):
        bl = dist(bm['a'], bm['b']) or 1
        return abs(ux * (bm['b']['x'] - bm['a']['x']) / bl + uy * (bm['b']['y'] - bm['a']['y']) / bl) >= 0.98

    def coverage(bm):
        t1, t2 = along(bm['a']), along(bm['b'])
        lo, hi = max(0, min(t1, t2)), min(L, max(t1, t2))
        return hi - lo

    beams = [bm for bm in (level.get('beams') or []) if parallel(bm)]
    in_side = _sign(off(_centroid_of(level['outline'])) or 1)

    # a beam body (RAM beam object, a band): its outer face lies on the edge and its axis sits inside it
    def body_on_edge(bm):
        poly = bm.get('polygon')
        if not poly:
            return False
        on = False
        for i, p in enumerate(poly):
            q = poly[(i + 1) % len(poly)]
            if abs(off(p)) < 60 and abs(off(q)) < 60 and coverage({'a': p, 'b': q}) > min(1000, 0.5 * L):
                on = True
                break
        return on and (off(bm['a']) + off(bm['b'])) / 2 * in_side > 50 and coverage(bm) > 1000

    if any(body_on_edge(bm) for bm in beams):
        return True
    # a beam drawn as two face lines: one on the edge, the other 150 to 900 inside
    on_edge = [bm for bm in beams if not bm.get('polygon') and abs(off(bm['a'])) < 60 and abs(off(bm['b'])) < 60 and (coverage(bm) > 0.5 * L or coverage(bm) > 2000)]
    if not on_edge:
        return False

    def inner(bm):
        d = (off(bm['a']) + off(bm['b'])) / 2 * in_side
        return d > 150 and d < 900 and coverage(bm) > 1000

    return any(inner(bm) for bm in beams)


def _centroid_of(poly):
    x = y = 0
    for p in poly:
        x += p['x']
        y += p['y']
    return {'x': x / (len(poly) or 1), 'y': y / (len(poly) or 1)}


def edge_runs_between_columns(level, a, b, h, band_of=None):
    L = dist(a, b) or 1
    ux, uy = (b['x'] - a['x']) / L, (b['y'] - a['y']) / L
    cuts = []
    # (an interior beam whose group of top bars reaches this edge stops the perimeter bars like a column's group)
    supports = (list(level['columns'])
                + [{'id': w['id'], 'shape': 'rect', 'cx': w['cx'], 'cy': w['cy'], 'w': w['w'], 'h': w['h'], 'isWall': True} for w in (level.get('walls') or []) if w.get('polygon') and w.get('t') and not w.get('core')]
                + [{'id': bm['id'], 'shape': 'rect', 'cx': bm['cx'], 'cy': bm['cy'], 'w': bm['w'], 'h': bm['h'], 'isWall': True, 'isBeam': True, 'along': bm.get('along')} for bm in (level.get('beams') or []) if bm.get('polygon') and bm.get('interior')])
    for c in supports:
        t = (c['cx'] - a['x']) * ux + (c['cy'] - a['y']) * uy
        off = abs((c['cx'] - a['x']) * -uy + (c['cy'] - a['y']) * ux)
        size = c['d'] if c.get('shape') == 'circle' else max(c['w'], c['h'])
        reach = max(size, 1000, (band_of and band_of(c, 'across')) or 0) / 2 + 500
        if t < -size or t > L + size or off > reach:
            continue  # not a support on this edge
        along = 'x' if abs(ux) > 0.7 else 'y'
        if c.get('isBeam') and c.get('along') != along:
            continue  # a beam ending at this edge: its group sits along the beam, away from the edge
        # the perimeter bars stop where the support's bars along the edge are (their group width), else at c2 + 1.5h each side
        band = (band_of(c, along) if band_of else None) or ((c['d'] if c.get('shape') == 'circle' else (c['w'] if along == 'x' else c['h'])) + 3 * h)
        cuts.append([t - band / 2, t + band / 2])
    return [[p, q] for p, q in subtract_intervals([[0, L]], cuts) if q - p > 300]


# Sheet: additional top bars over columns (PT two-way slab, §8.7.5.5).
def support_columns(level, gap=500):
    """
    Office rule: two columns standing next to each other (faces closer than `topColumns.mergeGap`, 500 mm, and
    overlapping along the other axis) are one support for the top bars - one group of reinforcement over both,
    never two overlapping groups. The merged support is the rectangle around them; its members are kept in `merged`
    (the punching check and the schedule still see the columns themselves).
    """
    cols = level.get('columns') or []
    cache = level.get(SUPPORTS_KEY)
    if cache and cache.get('gap') == gap and cache.get('n') == len(cols):
        return cache['list']

    def box(c):
        w = c['d'] if c.get('shape') == 'circle' else c['w']
        h = c['d'] if c.get('shape') == 'circle' else c['h']
        return {'minX': c['cx'] - w / 2, 'maxX': c['cx'] + w / 2, 'minY': c['cy'] - h / 2, 'maxY': c['cy'] + h / 2}

    def touch(A, B):
        gx = max(A['minX'] - B['maxX'], B['minX'] - A['maxX'])
        gy = max(A['minY'] - B['maxY'], B['minY'] - A['maxY'])
        return (gx <= gap and gy <= 0) or (gy <= gap and gx <= 0)  # close along one axis, overlapping along the other

    parent = list(range(len(cols)))

    def find(i):
        if parent[i] == i:
            return i
        parent[i] = find(parent[i])
        return parent[i]

    boxes = [box(c) for c in cols]
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            if touch(boxes[i], boxes[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i, c in enumerate(cols):
        k = find(i)
        if k not in groups:
            groups[k] = []
        groups[k].append(c)
    lst = []
    for g in groups.values():
        if len(g) == 1:
            lst.append(g[0])
            continue
        b = {'minX': min(box(c)['minX'] for c in g), 'maxX': max(box(c)['maxX'] for c in g), 'minY': min(box(c)['minY'] for c in g), 'maxY': max(box(c)['maxY'] for c in g)}
        m = {'id': '+'.join(c['id'] for c in g), 'shape': 'rect', 'cx': (b['minX'] + b['maxX']) / 2, 'cy': (b['minY'] + b['maxY']) / 2, 'w': b['maxX'] - b['minX'], 'h': b['maxY'] - b['minY']}
        if 'angle' in g[0]:
            m['angle'] = g[0]['angle']  # (`angle: g[0].angle` - an undefined angle is dropped by JSON.stringify in JS, so the key is left out here)
        m['merged'] = g
        lst.append(m)
    level[SUPPORTS_KEY] = {'gap': gap, 'n': len(cols), 'list': lst}  # a cache, never written to the model file (drop `_` keys when writing JSON)
    return lst


def _js_max(*vals):
    """JS Math.max: NaN when any value is NaN."""
    import math as _m
    return float('nan') if any(isinstance(v, float) and _m.isnan(v) for v in vals) else max(vals)


def top_at_columns(level, spec):
    s = spec['topColumns']
    supports = support_columns(level, _nn(s.get('mergeGap'), 500))
    h = level['thickness']
    cover = spec['cover']
    lists = {'x': BarList('T2'), 'y': BarList('T1')}
    types = []
    columns = []
    checks = []
    # walls below carry top bars too: a wall is treated as a long rectangular support (bars across it
    # along its length, bars along it within t + 3h), without joining the grid or the punching sheet
    # (an isolated wall gets the two column groups over it; a core wall - three or more walls around an opening - keeps the wall U-bars)
    # (a wall record without cx / cy / w / h reads NaN in the JS: kept here as NaN, never as a KeyError)
    _nan = float('nan')
    wall_supports = [{'id': w['id'], 'shape': 'rect', 'cx': w.get('cx', _nan), 'cy': w.get('cy', _nan), 'w': w.get('w', _nan), 'h': w.get('h', _nan), 'isWall': True, 'core': bool(w.get('core')),
                      'skipAlong': ('x' if w.get('w', _nan) >= w.get('h', _nan) else 'y') if _js_max(w.get('w', _nan), w.get('h', _nan)) > (s.get('wallAlongMax') or 6000) else None}
                     for w in (level.get('walls') or []) if w.get('polygon') and w.get('t')]
    # office rule: an interior beam (slab on both sides) carries a group of top bars across it, `length` (4 m) or
    # `minBeyond` (1.5 m) past each face whichever is larger, distributed along the beam; nothing along it
    beam_supports = [{'id': b['id'], 'shape': 'rect', 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h'], 'isWall': True, 'isBeam': True, 'core': False, 'skipAlong': b.get('along'), 'beam': b}
                     for b in (level.get('beams') or []) if b.get('polygon') and b.get('interior')]
    if not level.get('maxSpan'):
        mx = 0
        for c in supports:
            for dir_ in ['x', 'y']:
                for sign in [-1, 1]:
                    nb = neighbour(level, c, dir_, sign)
                    if nb and nb['d'] > mx:
                        mx = nb['d']
        level['maxSpan'] = mx or 8000
    for col in supports + wall_supports + beam_supports:
        size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}
        per = {}
        # spans to the next support in each direction, found first so that the strip width
        # (Acf) of one direction can use the span of the other
        span_of = {}
        for dir_ in ['x', 'y']:
            c1 = size[dir_]
            ext, hooks, spans = {}, {}, []
            nbs, to_edges = {}, {}
            for sign in [-1, 1]:
                nb = neighbour(level, col, dir_, sign)
                to_edge = edge_distance(level, col, dir_, sign, cover)
                # a drawing joint with the neighbouring part is not a slab edge: the slab goes on
                if level.get('jointEdges'):
                    hit = {'x': col['cx'] + sign * (to_edge + c1 / 2), 'y': col['cy']} if dir_ == 'x' else {'x': col['cx'], 'y': col['cy'] + sign * (to_edge + c1 / 2)}
                    if any(_near_segment(hit, e['a'], e['b'], 400) for e in level['jointEdges']):
                        to_edge = 1e9
                nbs[sign] = nb
                to_edges[sign] = to_edge
                if nb:
                    spans.append(nb['d'])
                else:
                    cap = ceil_to(max(level.get('maxSpan') or 0, 6 * 1.5 * h) / 6, 50)
                    spans.append(2 * min(to_edge, cap * 6))
            if col.get('isBeam') and col.get('skipAlong') == dir_:
                # along the beam: nothing is drawn; the group across it is distributed over the beam's own length
                ext[-1] = 0
                ext[1] = 0
            elif (s.get('rule') or 'office') == 'office' and (not col.get('isWall') or not col.get('core')):
                # office rule: interior bar covers the drop panel or runs `length` in total; an edge column bar
                # ends in a U at the slab edge and continues `edgeFactor` x the interior length on top
                # a drop panel is a thickened zone of limited size around the column (`dropMax`, 6 m); a long thickened strip is not one
                drop = None if col.get('isBeam') else next((z for z in (level.get('thickZones') or []) if point_in_polygon({'x': col['cx'], 'y': col['cy']}, z['polygon']) and max(bbox(z['polygon'])['w'], bbox(z['polygon'])['h']) <= (s.get('dropMax') or 6000)), None)
                # with a drop panel the bars are exactly as long as the drop (+ `dropMargin` each side, 0 by default);
                # without one they are `length` (4 m) in total
                Lint = s.get('length') or 4000
                if drop:
                    zb = bbox(drop['polygon'])
                    Lint = ceil_to((zb['w'] if dir_ == 'x' else zb['h']) + 2 * _nn(s.get('dropMargin'), 0), 10)
                # office rule: the bars project at least `minBeyond` (1.5 m) past the face of the column / wall on each side
                beyond = _nn(s.get('minBeyond'), 1500)
                Lint = max(Lint, ceil_to(c1 + 2 * beyond, 10))
                half = (Lint - c1) / 2
                # an edge column: the bar would reach the slab edge, or end inside the perimeter U-bar zone (the U-bar's top
                # leg from the edge): then it runs to the edge and ends in the U, and the perimeter U-bars stop before / after it
                u_edge = spec.get('uEdge') or {}
                u_zone = max(0, (u_edge['total'] - (h - 2 * cover)) / 2) if u_edge.get('total') else 1200
                edge_sign = next((sg for sg in [-1, 1] if to_edges[sg] - c1 / 2 - half < u_zone), None)
                if edge_sign is None:
                    ext[-1] = half
                    ext[1] = half
                else:
                    other = -edge_sign
                    ext[edge_sign] = max(to_edges[edge_sign] - c1 / 2, 0)
                    hooks[edge_sign] = True
                    # the far side still reaches the drop panel edge (the interior half) and at least `minBeyond` past the face
                    ext[other] = max(ceil_to(_nn(s.get('edgeFactor'), 0.7) * Lint, 50) - ext[edge_sign] - c1, beyond, half if drop else 0)
                    if to_edges[other] - c1 / 2 < ext[other]:
                        ext[other] = max(to_edges[other] - c1 / 2, 0)
                        hooks[other] = True  # corner column: U both ends
                # office rule: a bar across a beam that reaches an adjacent parallel beam is shortened to end over it (its far face)
                if col.get('isBeam'):
                    along_key = col.get('skipAlong')
                    my_lo = col['cx'] - col['w'] / 2 if along_key == 'x' else col['cy'] - col['h'] / 2
                    my_hi = col['cx'] + col['w'] / 2 if along_key == 'x' else col['cy'] + col['h'] / 2
                    for sign in [-1, 1]:
                        for nb in beam_supports:
                            if nb is col or nb.get('skipAlong') != along_key:
                                continue
                            n_lo = nb['cx'] - nb['w'] / 2 if along_key == 'x' else nb['cy'] - nb['h'] / 2
                            n_hi = nb['cx'] + nb['w'] / 2 if along_key == 'x' else nb['cy'] + nb['h'] / 2
                            if min(my_hi, n_hi) - max(my_lo, n_lo) < 500:
                                continue  # not alongside this beam
                            centre = ((nb['cx'] - col['cx']) if dir_ == 'x' else (nb['cy'] - col['cy'])) * sign
                            nb_half = (nb['w'] if dir_ == 'x' else nb['h']) / 2
                            d_near, d_far = centre - nb_half, centre + nb_half
                            if d_near <= c1 / 2 or c1 / 2 + ext[sign] <= d_near:
                                continue  # behind, or not reached
                            ext[sign] = min(ext[sign], max(d_far - c1 / 2, 0))
                            hooks[sign] = False
            else:
                for sign in [-1, 1]:
                    nb, to_edge = nbs[sign], to_edges[sign]
                    if nb:
                        nb_size = nb['col']['d'] if nb['col'].get('shape') == 'circle' else (nb['col']['w'] if dir_ == 'x' else nb['col']['h'])
                        ln = nb['d'] - c1 / 2 - nb_size / 2
                        e = ceil_to(ln / 6, 50)
                        if c1 / 2 + e > to_edge:
                            e = max(to_edge - c1 / 2, 0)
                            hooks[sign] = True
                        ext[sign] = e
                    else:
                        # no support on this side: the bar runs to the slab edge, but never further than
                        # a sixth of the longest span found in the level (a wall at the far end of a slab
                        # must not pull the bars across the whole slab)
                        cap = ceil_to(max(level.get('maxSpan') or 0, 6 * 1.5 * h) / 6, 50)
                        to_edge_ext = max(to_edge - c1 / 2, 0)
                        ext[sign] = min(to_edge_ext, cap)
                        hooks[sign] = ext[sign] == to_edge_ext
            span_of[dir_] = {'ext': ext, 'hooks': hooks, 'spans': spans}
        for dir_ in ['x', 'y']:
            c1 = size[dir_]
            c2 = size['y' if dir_ == 'x' else 'x']
            ext, hooks, spans = span_of[dir_]['ext'], span_of[dir_]['hooks'], span_of[dir_]['spans']
            other = span_of['y' if dir_ == 'x' else 'x']['spans']
            # Minimum bonded reinforcement over the column: As = 0.00075·Acf (§8.6.2.3),
            # Acf = h × larger tributary width of the strip. Over a wall only the span
            # across the wall is a slab span (its own length is not).
            if col.get('isWall'):
                l2 = (max(other) if size['x'] > size['y'] else max(spans)) if dir_ == 'x' else (max(other) if size['y'] > size['x'] else max(spans))
            else:
                l2 = max(*spans, *other)
            # office rule: the bars of one direction are distributed over the length of the crossing bars at the
            # same column (the two groups cover the same square); code rule: within c2 + 1.5h each side (§8.7.5.5.1)
            o = span_of['y' if dir_ == 'x' else 'x']
            other_straight = o['ext'][-1] + c2 + o['ext'][1]
            band = other_straight if (s.get('rule') or 'office') == 'office' and not col.get('isWall') else c2 + 3 * h
            n = max(4, math.floor(band / s['spacing']) + 1)
            as_req = 0.00075 * h * l2
            n_req = 0 if col.get('isWall') else math.ceil(as_req / BAR_AREA(s['dia']))  # §8.6.2.3 is a column rule; over a wall the spacing governs
            if n_req > n:
                n = n_req
            straight = js_round((ext[-1] + c1 + ext[1]) / 10) * 10  # (column sizes read from a drawing carry float noise)
            # a top bar ending at the slab edge ends in a U (500 bottom leg), or in an L where the edge carries a beam
            ends = {}
            for sign in [-1, 1]:
                if not hooks.get(sign):
                    continue
                end_pt = {'x': col['cx'] + sign * (c1 / 2 + ext[sign]), 'y': col['cy']} if dir_ == 'x' else {'x': col['cx'], 'y': col['cy'] + sign * (c1 / 2 + ext[sign])}
                end = edge_end_at(level, spec, end_pt)
                if end['type']:
                    ends[sign] = end
                else:
                    hooks[sign] = False  # the bar simply continues into the neighbouring part
            legs = ((ends.get(-1) or {}).get('leg') or 0) + ((ends.get(1) or {}).get('leg') or 0)
            length = ceil_to(straight + legs, 10)
            shape = ''.join((ends.get(sg) or {}).get('type') or '' for sg in [-1, 1]) or 'STR'
            first = ends.get(-1) or ends.get(1) or top_edge_end(level, spec)
            # (`hookLabels.start` / `.end` are `undefined` in JS when there is no U / L end: JSON.stringify drops
            # them, so the keys are left out here too - read them with .get())
            hook_labels = {}
            if -1 in ends:
                hook_labels['start'] = ends[-1]['label']
            if 1 in ends:
                hook_labels['end'] = ends[1]['label']
            per[dir_] = {'ext': ext, 'hooks': hooks,
                         'hookTypes': {-1: (ends.get(-1) or {}).get('type') or None, 1: (ends.get(1) or {}).get('type') or None},
                         'hookLabels': hook_labels,
                         'n': n, 'length': length, 'shape': shape, 'band': band, 'asReq': js_round(as_req), 'asProv': js_round(n * BAR_AREA(s['dia'])), 'straight': straight,
                         'hookLeg': first['leg'], 'hookLabel': first['label'], 'c1': c1, 'code': 'T2' if dir_ == 'x' else 'T1'}
            checks.append({'column': col['id'], 'dir': dir_.upper(), 'asReq': js_round(as_req), 'asProv': js_round(n * BAR_AREA(s['dia'])), 'n': n})
        key = f"{fmt_num(per['x']['length'])}|{per['x']['n']}|{per['x']['shape']}|{fmt_num(per['y']['length'])}|{per['y']['n']}|{per['y']['shape']}"
        type_ = next((t for t in types if t['key'] == key), None)
        if not type_:
            type_ = {'key': key, 'id': f"TC{len(types) + 1}", 'x': per['x'], 'y': per['y'], 'columns': []}
            types.append(type_)
        type_['columns'].append(col['id'])
        columns.append({'col': col, 'type': type_, 'per': per})
    for t in types:
        for dir_ in ['x', 'y']:
            p = t[dir_]
            note = '' if p['shape'] == 'STR' else (f"L end: {fmt_num((spec.get('uEdge') or {}).get('beamLeg') or 400)} down into the edge beam" if re.search('L', p['shape']) and not re.search('U', p['shape']) else top_edge_end(level, spec)['note'])
            p['mark'] = lists[dir_].add({'dia': s['dia'], 'shape': p['shape'], 'length': p['length'], 'qty': p['n'] * len(t['columns']), 'spacing': s['spacing'], 'zone': t['id'], 'note': note})
    return {'types': types, 'columns': columns, 'lists': lists, 'checks': checks, 'dia': s['dia'], 'spacing': s['spacing'], 'rule': s.get('rule') or 'office', 'length': s.get('length') or 4000, 'edgeFactor': _nn(s.get('edgeFactor'), 0.7), 'uEnd': top_edge_end(level, spec)}


def u_bars(level, spec):
    """Sheet: U-bars along slab edges and around circular regions."""
    h = level['thickness']
    cover = spec['cover']
    bars = BarList('U')
    web = h - 2 * cover
    edge_items = []
    circle_items = []
    assumptions = []

    edge_list = edges(level['outline']) if level['ubar']['edges'] == 'all' else [{'a': e['a'], 'b': e['b'], 'length': dist(e['a'], e['b']), 'dx': e['b']['x'] - e['a']['x'], 'dy': e['b']['y'] - e['a']['y']} for e in level['ubar']['edges']]
    su, se = spec['uEdge'], spec['edgeBars']
    lap_e = lap_length(spec, se['dia'])
    # office perimeter rule: T12@150 between the column top bars, a symmetric U at a free edge, an L at an edge beam
    u_leg_top = ceil_to((su['total'] - web) / 2, 10)
    u_len = ceil_to(2 * u_leg_top + web, 10)
    l_len = su['beamLeg'] + su['beamTop']
    for i, e in enumerate(edge_list):
        if e['length'] < 2 * su['spacing']:
            continue
        beam = edge_has_beam(level, e['a'], e['b'])
        runs = edge_runs_between_columns(level, e['a'], e['b'], h)
        n = sum(math.floor((q - p) / su['spacing']) + 1 for p, q in runs)
        if not n:
            continue
        u_mark = (bars.add({'dia': su['dia'], 'shape': 'L', 'length': l_len, 'qty': n, 'spacing': su['spacing'], 'zone': f"E{i + 1}", 'note': f"{fmt_num(su['beamLeg'])} in beam + {fmt_num(su['beamTop'])} top"})
                  if beam else
                  bars.add({'dia': su['dia'], 'shape': 'U', 'length': u_len, 'qty': n, 'spacing': su['spacing'], 'zone': f"E{i + 1}", 'note': f"legs {fmt_num(u_leg_top)} T&B"}))
        run_l = e['length'] - 2 * cover
        pieces = split_run(run_l, stock=spec['stock'], lap=lap_e)
        marks = [bars.add({'dia': se['dia'], 'shape': 'STR', 'length': ln, 'qty': 2 * se['count'], 'zone': f"E{i + 1}", 'note': 'edge bar T&B'}) for ln in pieces]
        edge_items.append({'id': f"E{i + 1}", 'a': e['a'], 'b': e['b'], 'length': e['length'], 'n': n, 'beam': beam, 'runs': runs, 'leg': su['beamTop'] if beam else u_leg_top, 'uMark': u_mark, 'marks': _unique(marks), 'pieces': pieces})
    sc, sr = spec['uCircle'], spec['ringBars']
    for i, c in enumerate(level['ubar']['circles']):
        r_out = c['r'] + cover
        n = math.ceil((2 * math.pi * r_out) / sc['spacing'])
        u_l = ceil_to(2 * sc['leg'] + web, 10)
        u_mark = bars.add({'dia': sc['dia'], 'shape': 'U', 'length': u_l, 'qty': n, 'spacing': sc['spacing'], 'zone': c['id'], 'note': f"legs {fmt_num(sc['leg'])}"})
        ring_r = r_out + sc['dia'] + sr['dia'] / 2
        lap_r = lap_length(spec, sr['dia'])
        ring_l = ceil_to(2 * math.pi * ring_r + lap_r, 10)
        ring_pieces = split_run(ring_l, stock=spec['stock'], lap=lap_r)
        ring_marks = [bars.add({'dia': sr['dia'], 'shape': 'RING', 'length': ln, 'qty': 2 * sr['count'], 'zone': c['id'], 'note': f"R={js_round(ring_r)}"}) for ln in ring_pieces]
        circle_items.append({**c, 'n': n, 'uMark': u_mark, 'ringMarks': _unique(ring_marks), 'ringR': ring_r})
    return {'edgeItems': edge_items, 'circleItems': circle_items, 'bars': bars, 'assumptions': assumptions, 'uEdge': su, 'uCircle': sc, 'edgeBars': se, 'ringBars': sr, 'uLen': u_len, 'lLen': l_len, 'uLegTop': u_leg_top, 'web': web}


def _trimmers_around(level, spec, region, s, bars, lap):
    """
    Trimmer bars around a rectangular / polygonal region. Each edge gets `count`
    bars top and bottom, parallel to the edge, anchored ld beyond the corners.
    Bars that would leave the slab are stopped at the edge with a hook.
    """
    dia, count = s['dia'], s['count']
    cover = spec['cover']
    ld = development_length(spec, dia, top=True)
    poly = region_polygon(region)
    items = []
    for i, e in enumerate(edges(poly)):
        ux, uy = e['dx'] / e['length'], e['dy'] / e['length']
        # Outward normal: polygon may be either orientation, pick the side outside the region.
        nx, ny = -uy, ux
        mid = {'x': (e['a']['x'] + e['b']['x']) / 2, 'y': (e['a']['y'] + e['b']['y']) / 2}
        if point_in_polygon({'x': mid['x'] + nx * 10, 'y': mid['y'] + ny * 10}, poly):
            nx, ny = -nx, -ny
        hooks = {}
        ext = {}
        for sign, p in [(-1, e['a']), (1, e['b'])]:
            # Extend beyond the corner along the edge direction, clipped by the slab outline.
            probe = {'x': p['x'] + sign * ux * ld, 'y': p['y'] + sign * uy * ld}
            if point_in_polygon(probe, level['outline']):
                ext[sign] = ld
            else:
                # find distance to slab boundary by stepping
                d = 0
                while d < ld:
                    if not point_in_polygon({'x': p['x'] + sign * ux * d, 'y': p['y'] + sign * uy * d}, level['outline']):
                        break
                    d += 25
                ext[sign] = max(d - cover, 0)
                hooks[sign] = True
        hook_n = (1 if hooks.get(-1) else 0) + (1 if hooks.get(1) else 0)
        straight = e['length'] + ext[-1] + ext[1]
        length = ceil_to(straight + hook_n * hook_leg(dia), 10)
        shape = 'STR' if hook_n == 0 else 'L' if hook_n == 1 else 'C'
        pieces = split_run(length, stock=spec['stock'], lap=lap) if length > spec['stock'] else [length]
        marks = [bars.add({'dia': dia, 'shape': 'STR' if len(pieces) > 1 else shape, 'length': ln, 'qty': 2 * count, 'zone': region['id'], 'note': 'T&B'}) for ln in pieces]
        offsets = []
        for k in range(count):
            offsets.append(cover + dia / 2 + k * 75)
        items.append({'edge': e, 'ux': ux, 'uy': uy, 'nx': nx, 'ny': ny, 'ext': ext, 'hooks': hooks, 'length': length, 'shape': shape, 'marks': _unique(marks), 'offsets': offsets, 'ld': ld})
    return items


def around_voids(level, spec):
    """Sheet: reinforcement around voids / acuars and sunken slabs."""
    bars = BarList('V')
    sv = spec['voids']
    lap = lap_length(spec, sv['dia'], top=True)
    regions = [{'kind': 'VOID', 'region': v, 'trimmers': _trimmers_around(level, spec, v, sv, bars, lap)} for v in level['voids']]
    ss = spec.get('sunken') or {'dia': 12, 'count': 2, 'uDia': 10, 'uSpacing': 200, 'uLeg': 600}
    h = level['thickness']
    u_len = ceil_to(2 * ss['uLeg'] + (h - 2 * spec['cover']), 10)
    for sk in level.get('sunken') or []:
        trimmers = _trimmers_around(level, spec, sk, ss, bars, lap)
        per = perimeter(region_polygon(sk))
        n_u = max(0, math.floor((per - 4 * spec['cover']) / ss['uSpacing']))
        u_mark = bars.add({'dia': ss['uDia'], 'shape': 'U', 'length': u_len, 'qty': n_u, 'spacing': ss['uSpacing'], 'zone': sk['id'], 'note': f"legs {fmt_num(ss['uLeg'])}"}) if n_u else None
        regions.append({'kind': 'SUNKEN', 'region': sk, 'trimmers': trimmers, 'uMark': u_mark, 'nU': n_u})
    return {'regions': regions, 'bars': bars, 'dia': sv['dia'], 'count': sv['count'], 'ld': development_length(spec, sv['dia'], top=True), 'sunken': ss, 'uLen': u_len}


def punching(level, spec):
    """
    Punching shear links around columns: minimum detailing arrangement per
    SBC 304-18 §8.7.6 / §22.6.8 (first row at d/2 from the face, rows at d/2,
    legs along the face at ~100 mm). Extent 2h beyond the face is an
    assumption: the number of rows is to be verified against the punching
    design (Vu) before fabrication.
    """
    sp = spec.get('punching') or {'dia': 10, 'legSpacing': 100, 'extentFactor': 2.0}
    h = level['thickness']
    cover = spec['cover']
    d = h - cover - 16
    # (both branches of the JS ternary are the same expression; ported as it is)
    row_spacing = math.floor(d / 2 / 5) * 5 if ceil_to(max(d / 2, 50), 5) > d / 2 else math.floor(d / 2 / 5) * 5
    extent = sp['extentFactor'] * h
    rows = max(2, math.ceil(extent / row_spacing))
    bars = BarList('PS')
    link_len = ceil_to(2 * 110 + (h - 2 * cover) + 2 * max(6 * sp['dia'], 75), 10)
    types = []
    columns = []
    # walls are line supports: no punching links
    for col in level['columns']:
        size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}
        sides = []
        for dir_, sign in [('x', -1), ('x', 1), ('y', -1), ('y', 1)]:
            to_edge = edge_distance(level, col, dir_, sign, cover)
            face_len = size['y' if dir_ == 'x' else 'x']
            room = to_edge - size[dir_] / 2
            if room < row_spacing:
                continue  # face at the slab edge
            n_rows = min(rows, math.floor(room / row_spacing))
            links = math.floor(face_len / sp['legSpacing']) + 1
            sides.append({'dir': dir_, 'sign': sign, 'nRows': n_rows, 'links': links, 'faceLen': face_len, 'offset': size[dir_] / 2})
        label = ' / '.join(list(dict.fromkeys(sorted(f"{sd['nRows']}X{sd['links']}-T{fmt_num(sp['dia'])}-{fmt_num(row_spacing)}" for sd in sides))))
        key = f"{len(sides)}|{label}"
        t = next((x for x in types if x['key'] == key), None)
        if not t:
            t = {'key': key, 'id': f"PS{len(types) + 1}", 'sides': sides, 'size': size, 'columns': [], 'label': label}
            types.append(t)
        t['columns'].append(col['id'])
        columns.append({'col': col, 'type': t, 'sides': sides})
        n = sum(sd['nRows'] * sd['links'] for sd in sides)
        if n:
            bars.add({'dia': sp['dia'], 'shape': 'LINK', 'length': link_len, 'qty': n, 'spacing': row_spacing, 'zone': t['id'], 'note': f"legs 110, web {fmt_num(h - 2 * cover)}"})
    return {'types': types, 'columns': columns, 'bars': bars, 'dia': sp['dia'], 'rowSpacing': row_spacing, 'rows': rows, 'extent': extent, 'linkLen': link_len, 'd': d, 'legSpacing': sp['legSpacing']}


def around_openings(level, spec):
    """Sheet: reinforcement around openings: trimmers, corner diagonals, edge U-bars."""
    bars = BarList('O')
    so = spec['openings']
    h = level['thickness']
    cover = spec['cover']
    lap = lap_length(spec, so['dia'], top=True)
    diag_l = ceil_to(max(1200, 2 * development_length(spec, so['diagDia'], top=True)), 50)
    u_len = ceil_to(2 * so['uLeg'] + (h - 2 * cover), 10)
    lined = [o for o in level['openings'] if opening_lined(level, o)]
    regions = []
    for o in level['openings']:
        if any(o is l for l in lined):
            continue
        trimmers = _trimmers_around(level, spec, o, so, bars, lap)
        poly = region_polygon(o)
        corners = []
        if o.get('kind') != 'circle':
            for i, p in enumerate(poly):
                prev, nxt = poly[(i + len(poly) - 1) % len(poly)], poly[(i + 1) % len(poly)]
                # bisector pointing away from the region
                v1 = {'x': prev['x'] - p['x'], 'y': prev['y'] - p['y']}
                v2 = {'x': nxt['x'] - p['x'], 'y': nxt['y'] - p['y']}
                l1, l2 = math.hypot(v1['x'], v1['y']) or 1, math.hypot(v2['x'], v2['y']) or 1
                bx, by = v1['x'] / l1 + v2['x'] / l2, v1['y'] / l1 + v2['y'] / l2
                bl = math.hypot(bx, by) or 1
                bx /= bl
                by /= bl
                if point_in_polygon({'x': p['x'] + bx * 20, 'y': p['y'] + by * 20}, poly):
                    bx, by = -bx, -by
                # diagonal bar is perpendicular to the bisector, centred a little outside the corner
                c = {'x': p['x'] - bx * 100, 'y': p['y'] - by * 100}
                corners.append({'p': p, 'c': c, 'dx': -by, 'dy': bx})
        diag_mark = bars.add({'dia': so['diagDia'], 'shape': 'DIAG', 'length': diag_l, 'qty': len(corners) * so['diagCount'] * 2, 'zone': o['id'], 'note': 'T&B at corners'}) if corners else None
        per = perimeter(poly)
        n_u = max(0, math.floor((per - 4 * cover) / so['uSpacing']))
        u_mark = bars.add({'dia': so['uDia'], 'shape': 'U', 'length': u_len, 'qty': n_u, 'spacing': so['uSpacing'], 'zone': o['id'], 'note': f"legs {fmt_num(so['uLeg'])}"})
        regions.append({'region': o, 'trimmers': trimmers, 'corners': corners, 'diagMark': diag_mark, 'uMark': u_mark, 'nU': n_u})
    return {'regions': regions, 'bars': bars, 'spec': so, 'diagL': diag_l, 'uLen': u_len, 'ld': development_length(spec, so['dia'], top=True), 'lined': lined}


# export { growRect, polygonArea, regionPolygon as polygonOf };
polygon_of = region_polygon
__all__ = [
    'DEFAULT_SPEC', 'SUPPORTS_KEY', 'BAR_AREA', 'bar_weight_per_m', 'development_length', 'lap_length', 'hook_development_length',
    'hook_leg', 'length_table', 'split_run', 'BarList', 'merge_rows', 'merge_totals', 'region_polygon', 'region_bbox',
    'LAYER_CODE', 'bottom_mesh', 'neighbour', 'edge_distance', 'top_edge_end', 'U_BOTTOM_LEG', 'edge_end_at', 'side_lining',
    'opening_lined', 'edge_has_beam', 'edge_runs_between_columns', 'support_columns', 'top_at_columns', 'u_bars',
    'around_voids', 'punching', 'around_openings', 'grow_rect', 'polygon_area', 'polygon_of', 'perimeter',
]
