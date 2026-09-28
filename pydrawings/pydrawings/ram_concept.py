"""
Reads a RAM Concept model (.cpt, SQLite from version 8 on) straight from
the file: slab areas and mesh, columns, wall line supports, tendons with
jacks, the designed reinforcement bands with every individual bar, shear
regions, punching checks and materials. Internal RAM units: length 0.1 mm,
stress 100 MPa (0.1 kN/mm²), area 0.01 mm².

(Port of shopdrawings/lib/ram-concept.mjs.)
"""
import math
import re
import sqlite3

from .geometry import (bbox, polygon_area, dist, clean_polygon, simplify_polygon, centroid, point_in_polygon,
                       clip_segment_to_polygon, dist_to_polygon, clip_polyline_to_polygon, js_round)
from .extract import chain_segments

NAN = float('nan')


def _num(v):
    """A JS number out of a column value: null / undefined -> NaN (the JS arithmetic gives NaN too)."""
    return NAN if v is None else v


def _L(v):  # 0.1 mm → mm
    return _num(v) / 10


def _MPa(v):
    return _num(v) * 100


def _mm2(v):
    return _num(v) / 100


def _js_string(v):
    """`String(v)` / `${v}` of JS: a whole float prints without `.0`, booleans in lower case, null as 'null'."""
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        if v != v:
            return 'NaN'
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
    return str(v)


_S = _js_string


def _round(v):
    """Math.round of JS (NaN stays NaN instead of raising)."""
    if isinstance(v, float) and (v != v or v in (math.inf, -math.inf)):
        return v
    return js_round(v)


def _nums(s):
    # String(s || '') then every number
    text = _S(s) if s else ''
    return [float(m) for m in re.findall(r'-?\d+(?:\.\d+)?', text)]


def _point(s):
    v = _nums(s)
    return {'x': _L(v[0] if len(v) > 0 else None), 'y': _L(v[1] if len(v) > 1 else None)}


def _points(s):
    v = _nums(s)
    out = []
    i = 0
    while i + 1 < len(v):
        out.append({'x': _L(v[i]), 'y': _L(v[i + 1])})
        i += 2
    return out


def _bools(s):
    text = _S(s) if s else ''
    return [b == 'true' for b in re.findall(r'true|false', text)]


def _js_mod(a, b):
    """The JS `%` (remainder with the sign of the dividend)."""
    return math.fmod(a, b)


def _mod180(a):
    """`((a % 180) + 180) % 180` of JS."""
    return _js_mod(_js_mod(a, 180) + 180, 180)


def _truthy(v):
    """JS truthiness of a column value (0, '', null, NaN are false)."""
    if v is None:
        return False
    if isinstance(v, float) and v != v:
        return False
    return bool(v)


def read_ram_concept(path):
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row

    def rows(t):
        try:
            return [dict(r) for r in db.execute(f'select * from "{t}"').fetchall()]
        except sqlite3.Error:
            return []

    def by_uid(lst):
        return {r['UID']: r for r in lst}

    # ---------------------------------------------------------------- materials / project
    cover = (rows('Cover') or [{}])[0]
    headings = [h for h in [cover.get('Heading1'), cover.get('Heading2'), cover.get('Heading3'), cover.get('Heading4')] if _truthy(h)]
    concrete = (rows('Concrete') or [{}])[0]

    def rebar_type(r):
        digits = re.sub(r'\D', '', _S(r.get('Name')))
        dia = (int(digits) if digits else 0) or _round(math.sqrt((4 * _mm2(r.get('As'))) / math.pi))
        return {**r, 'dia': dia, 'fy': _MPa(r.get('Fy')), 'area': _mm2(r.get('As'))}
    rebar_types = by_uid([rebar_type(r) for r in rows('Rebar')])
    pt_system = (rows('PTSystem') or [{}])[0]
    strand = (rows('StrandMaterial') or [{}])[0]
    duct = (rows('DuctSystem') or [{}])[0]
    anchor = (rows('AnchorSystem') or [{}])[0]
    span_seg = rows('SpanSegment')
    punch_checks = rows('PunchCheck')
    cover_top = _L(max(s.get('ColumnStripTopCover') or 0 for s in span_seg)) if span_seg else (_L(punch_checks[0].get('TopCover')) if punch_checks else 25)
    cover_bot = _L(max(s.get('ColumnStripBottomCover') or 0 for s in span_seg)) if span_seg else (_L(punch_checks[0].get('BottomCover')) if punch_checks else 25)
    fc = _round(_MPa(concrete.get('FcFinal'))) if _truthy(concrete.get('FcFinal')) else None
    fy = _round(list(rebar_types.values())[0]['fy']) if rebar_types else None

    # ---------------------------------------------------------------- slab areas and mesh
    slab_areas = [{'polygon': clean_polygon(_points(r.get('MultiPoint'))), 'thickness': _L(r.get('SlabThickness')), 'priority': r.get('Priority'), 'behaviour': r.get('SlabBehavior'), 'toc': _L(r.get('TOC'))} for r in rows('SlabArea')]
    nodes = {r['Point0']: _point(r['Point0']) for r in rows('ElementCornerNode')}
    edge_count = {}
    elem_thk = []

    def edge_key(a, b):
        return f'{_S(a)}|{_S(b)}' if a < b else f'{_S(b)}|{_S(a)}'

    def add_edge(a, b):
        k = edge_key(a, b)
        edge_count[k] = edge_count.get(k, 0) + 1
    for q in rows('QuadSlabElement'):
        n = [q.get('CornerNode0'), q.get('CornerNode1'), q.get('CornerNode2'), q.get('CornerNode3')]
        for i in range(4):
            add_edge(n[i], n[(i + 1) % 4])
        elem_thk.append({'thk': _L(q.get('SlabThickness')), 'toc': _L(q.get('TOC') or 0), 'n': n})
    for q in rows('TriSlabElement'):
        n = [q.get('CornerNode0'), q.get('CornerNode1'), q.get('CornerNode2')]
        for i in range(3):
            add_edge(n[i], n[(i + 1) % 3])
        elem_thk.append({'thk': _L(q.get('SlabThickness')), 'toc': _L(q.get('TOC') or 0), 'n': n})

    def node_of(k):
        return nodes.get(k) or _point(k)
    elements = []
    for e in elem_thk:
        poly = [node_of(k) for k in e['n']]
        elements.append({'thickness': e['thk'], 'toc': e['toc'], 'area': abs(polygon_area(poly)), 'centroid': centroid(poly)})

    def loops_of(counts):
        segs_of = []
        for k, c in counts.items():
            if c == 1:
                a, b = k.split('|')
                pa, pb = node_of(a), node_of(b)
                segs_of.append([pa, pb])
        lp = [simplify_polygon(p, 1) for p in chain_segments(segs_of, 2)]
        lp = [{'polygon': p, 'area': abs(polygon_area(p))} for p in lp if len(p) >= 3]
        lp.sort(key=lambda l: l['area'], reverse=True)
        return lp
    loops = loops_of(edge_count)
    # office rule: a slab at another level (a step in the top of concrete) is a separate slab entirely; the mesh is
    # taken apart by TOC and every level gets its own outline, so the step reads as a free edge of both slabs
    tocs = sorted(dict.fromkeys(_round(e['toc']) for e in elem_thk), reverse=True)
    bodies = []
    for toc in tocs:
        counts = {}
        for e in elem_thk:
            if _round(e['toc']) != toc:
                continue
            for i in range(len(e['n'])):
                a, b = e['n'][i], e['n'][(i + 1) % len(e['n'])]
                k = edge_key(a, b)
                counts[k] = counts.get(k, 0) + 1
        lp = [list(reversed(l['polygon'])) if polygon_area(l['polygon']) < 0 else l['polygon'] for l in loops_of(counts)]
        for poly in lp:
            if any(q is not poly and abs(polygon_area(q)) > abs(polygon_area(poly)) and point_in_polygon(poly[0], q) for q in lp):
                continue  # a hole of a body of the same level
            bodies.append({'polygon': poly, 'holes': [q for q in lp if q is not poly and point_in_polygon(q[0], poly) and abs(polygon_area(q)) < abs(polygon_area(poly))], 'toc': toc})
    outline = None
    holes = []
    all_loops = [list(reversed(l['polygon'])) if polygon_area(l['polygon']) < 0 else l['polygon'] for l in loops]
    if loops:
        outline = loops[0]['polygon']
        holes = [l['polygon'] for l in loops[1:] if point_in_polygon(l['polygon'][0], outline)]
    elif slab_areas:
        # (the JS sorts the slab areas in place here: the returned `areas` list is sorted too)
        slab_areas.sort(key=lambda a: abs(polygon_area(a['polygon'])), reverse=True)
        outline = slab_areas[0]['polygon']
    if outline and polygon_area(outline) < 0:
        outline = list(reversed(outline))
    # dominant thickness: by element area (approximate by counting elements)
    thk_count = {}
    for e in elem_thk:
        thk_count[e['thk']] = thk_count.get(e['thk'], 0) + 1
    thicknesses = sorted(thk_count.items(), key=lambda e: e[1], reverse=True)
    base_thickness = thicknesses[0][0] if thicknesses else ((slab_areas[0]['thickness'] if slab_areas else None) or 250)
    thick_zones = [{'id': f'Z{i + 1}', 'polygon': a['polygon'], 'thickness': a['thickness']} for i, a in enumerate([a for a in slab_areas if a['thickness'] > base_thickness + 1])]
    # beams: RAM beam objects (an axis, a width, a depth); an edge beam lies along the slab edge, an interior one has slab both sides
    beams = []
    for i, r in enumerate([r for r in rows('Beam') if _truthy(r.get('Point0')) and _truthy(r.get('Point1'))]):
        a, b = _point(r['Point0']), _point(r['Point1'])

        # (office convention: beam sizes are written to the nearest 50 mm, never with decimals: 350x600)
        def r50(v):
            return _round(v / 50) * 50
        w = r50(_L(r.get('Width') or 0)) or 300
        d = r50(_L(r.get('SlabThickness') or 0))
        ln = math.hypot(b['x'] - a['x'], b['y'] - a['y']) or 1
        n = {'x': -(b['y'] - a['y']) / ln, 'y': (b['x'] - a['x']) / ln}
        beams.append({'id': f'BM{i + 1}', 'a': a, 'b': b, 't': w, 'depth': d, 'toc': _L(r.get('TOC') or 0), 'meshedAsSlab': _truthy(r.get('BeamIsMeshedAsSlab')),
                      'polygon': [{'x': a['x'] + n['x'] * w / 2, 'y': a['y'] + n['y'] * w / 2}, {'x': b['x'] + n['x'] * w / 2, 'y': b['y'] + n['y'] * w / 2}, {'x': b['x'] - n['x'] * w / 2, 'y': b['y'] - n['y'] * w / 2}, {'x': a['x'] - n['x'] * w / 2, 'y': a['y'] - n['y'] * w / 2}]})
    beams = [bm for bm in beams if math.hypot(bm['b']['x'] - bm['a']['x'], bm['b']['y'] - bm['a']['y']) > 500]

    # ---------------------------------------------------------------- supports
    columns = []
    for i, r in enumerate(rows('Column')):
        p = _point(r.get('Point0'))
        w, h, angle = _L(r.get('B')), _L(r.get('D')), _mod180(((r.get('Angle') or 0) * 180) / math.pi)
        if w < 1:
            columns.append({'id': f'C{i + 1}', 'shape': 'circle', 'cx': p['x'], 'cy': p['y'], 'd': h, 'w': h, 'h': h, 'angle': 0, 'below': r.get('SupportSet') == 'below'})
            continue
        # an orthogonal column is stored with its plan sizes along X / Y (a column turned 90° swaps B and D):
        # every rule (top bars, punching, U-bars) then reads w along X and h along Y
        if abs(angle - 90) < 2:
            w, h = h, w
            angle = 0
        elif angle < 2 or angle > 178:
            angle = 0
        columns.append({'id': f'C{i + 1}', 'shape': 'rect', 'cx': p['x'], 'cy': p['y'], 'w': w, 'h': h, 'angle': angle, 'below': r.get('SupportSet') == 'below'})
    # a column above and a column below at the same point are one column on the plan (the one below drawn)
    i = len(columns) - 1
    while i >= 0:
        c = columns[i]
        twin = next((j for j, o in enumerate(columns) if j != i and abs(o['cx'] - c['cx']) < 50 and abs(o['cy'] - c['cy']) < 50), -1)
        if twin >= 0 and twin < i and (not c['below'] or columns[twin]['below']):
            del columns[i]
        elif twin >= 0 and twin < i:
            del columns[twin]
            i -= 1
        i -= 1
    # walls: RAM's own Wall objects (with their thickness; the set below the slab, or above when that is all there is)
    # plus plain line supports; a wall above and one below on the same line are one wall on the plan
    wall_rows = rows('Wall')
    below = [r for r in wall_rows if r.get('SupportSet') == 'below']
    chosen = below if below else wall_rows
    walls = [{'a': _point(r.get('Point0')), 'b': _point(r.get('Point1')), 't': _L(r.get('WallThickness')) if _truthy(r.get('WallThickness')) else None} for r in chosen]
    for r in rows('LineSupport'):
        a, b = _point(r.get('Point0')), _point(r.get('Point1'))
        if not any((math.hypot(w['a']['x'] - a['x'], w['a']['y'] - a['y']) < 50 and math.hypot(w['b']['x'] - b['x'], w['b']['y'] - b['y']) < 50) or (math.hypot(w['a']['x'] - b['x'], w['a']['y'] - b['y']) < 50 and math.hypot(w['b']['x'] - a['x'], w['b']['y'] - a['y']) < 50) for w in walls):
            walls.append({'a': a, 'b': b})

    # ---------------------------------------------------------------- tendons
    tendon_segs = rows('Tendon')
    jacks = rows('Jack')
    layers_by_id = {r['UID']: r for r in rows('TendonLayer')}
    levels_by_id = {r['UID']: r for r in rows('TendonLevel')}
    cat_parent = {r['UID']: r.get('ParentUID') for r in rows('TendonCategory')}
    jack_by_node = {j.get('TendonNode0'): j for j in jacks}

    def span_set_of(parent_uid):
        lvl = levels_by_id.get(cat_parent.get(parent_uid))
        layer = lvl and (layers_by_id.get(lvl.get('ParentUID')) or next((l for l in layers_by_id.values() if l.get('UID') == lvl.get('ParentUID')), None))
        if layer:
            return layer.get('SpanSet')
        # fall back: order of categories = order of layers
        keys = list(cat_parent.keys())
        idx = keys.index(parent_uid) if parent_uid in keys else -1
        layers_list = list(layers_by_id.values())
        return layers_list[idx].get('SpanSet') if 0 <= idx < len(layers_list) else 'latitude'
    # profile points: every tendon node carries its CGS elevation (reference 4 = above the soffit, 5 = below the
    # surface, 6 = from mid-depth) with the local slab surface / soffit, so heights above the soffit follow
    node_elev = {}
    for r in rows('TendonNode'):
        thk = _L((r.get('Surface') or 0) - (r.get('Soffit') or 0)) or None
        v = _L(r.get('ElevationValue') or 0)
        ref = r.get('ElevationReference')
        h = thk - v if ref == 5 and thk else (thk / 2 + v if ref == 6 and thk else v)
        node_elev[r.get('Point0')] = {'h': _round(h), 'v': _round(v), 'ref': ref, 'thickness': thk}
    # chain segments node to node
    adj = {}
    for s in tendon_segs:
        for n in [s.get('TendonNode0'), s.get('TendonNode1')]:
            if n not in adj:
                adj[n] = []
            adj[n].append(s)
    used = set()
    tendons = []
    for start in list(adj.keys()):
        if len(adj[start]) != 1:
            continue
        first = adj[start][0]
        if first['UID'] in used:
            continue
        node = start
        seg = first
        pts = [_point(node)]
        ne = node_elev.get(node)
        heights = [ne['h'] if ne else None]
        # the figure as entered in RAM at every node (mm, in the model's own reference) - printed as it is on the cable sheets
        elevs = [{'v': ne['v'], 'ref': ne['ref']} if ne else None]
        thks = [ne['thickness'] if ne else None]
        segs_of_tendon = []
        while seg and seg['UID'] not in used:
            used.add(seg['UID'])
            segs_of_tendon.append(seg)
            node = seg.get('TendonNode1') if seg.get('TendonNode0') == node else seg.get('TendonNode0')
            pts.append(_point(node))
            ne = node_elev.get(node)
            heights.append(ne['h'] if ne else None)
            elevs.append({'v': ne['v'], 'ref': ne['ref']} if ne else None)
            thks.append(ne['thickness'] if ne else None)
            seg = next((s for s in (adj.get(node) or []) if s['UID'] not in used), None)
        strands = max(_num(s.get('NumStrands')) for s in segs_of_tendon)
        length = sum(dist(pts[i - 1], pts[i]) for i in range(1, len(pts)))
        ends = [start if segs_of_tendon[0].get('TendonNode0') == start else start, node]  # (as in the JS: unused)
        jack_ends = [j for j in (jack_by_node.get(n) for n in [start, node]) if j]
        span_set = span_set_of(segs_of_tendon[0].get('ParentUID'))
        tendons.append({
            'id': '', 'spanSet': span_set, 'strands': strands, 'pts': pts, 'length': _round(length), 'segments': len(segs_of_tendon),
            'live': [bool(jack_by_node.get(start)), bool(jack_by_node.get(node))],
            'jackStress': _MPa(jack_ends[0].get('JackStress')) if jack_ends else None,
            'elongation': _round(sum(_L(j.get('Elongation')) for j in jack_ends)) if jack_ends else None,
            'elongations': [_round(_L(jack_by_node[n].get('Elongation'))) if jack_by_node.get(n) else None for n in [start, node]],  # per end (null at a dead end)
            'harped': _truthy(segs_of_tendon[0].get('Harped')),
            # the CGS profile: height above the soffit at every node (null when the model carries none), reverse-curve ratio
            'heights': None if all(h is None for h in heights) else heights,
            'elevs': None if all(h is None for h in heights) else elevs,
            'thks': None if all(h is None for h in thks) else thks,
            'inflection': segs_of_tendon[0].get('InflectionRatio') or 0.2,
            'thickness': (node_elev.get(start) or {}).get('thickness') or None,
        })
    # closed loops (no degree-1 node) are ignored; number tendons per span set
    strand_area = _mm2(strand.get('Aps')) if _truthy(strand.get('Aps')) else 98.7
    for s in ['latitude', 'longitude']:
        lst = sorted([t for t in tendons if t['spanSet'] == s], key=(lambda t: t['pts'][0]['y']) if s == 'latitude' else (lambda t: t['pts'][0]['x']))
        for i, t in enumerate(lst):
            t['id'] = f"{'TA' if s == 'latitude' else 'TB'}-{str(i + 1).rjust(2, '0')}"
    for t in tendons:
        t['jackForce'] = _round((t['jackStress'] * strand_area * t['strands']) / 1000) if t['jackStress'] else None

    # ---------------------------------------------------------------- designed reinforcement
    bands_raw = rows('ConcentratedRebar')
    indiv = rows('IndividualBars')

    def band_key(r, n):  # (as in the JS: defined but unused)
        return f"{_S(_js_mod(r.get('ParentUID'), 2))}|{_S(r.get('BarFace'))}|{_S(r.get('SpanDirection'))}|{_S(n)}|{_S(_round(r.get('AbsoluteElevation')))}"
    indiv_by_key = {}
    for b in indiv:
        k = f"{_S(b.get('BarFace'))}|{_S(b.get('SpanDirection'))}|{len(_points(b.get('Point0')))}|{_S(_round(_num(b.get('AbsoluteElevation'))))}"
        if k not in indiv_by_key:
            indiv_by_key[k] = []
        indiv_by_key[k].append(b)
    bands = []
    for i, r in enumerate(bands_raw):
        typ = rebar_types.get(r.get('BarType')) or {'dia': 12, 'name': 'T12'}
        p0, p1 = _point(r.get('Point0')), _point(r.get('Point1'))
        left, right = _point(r.get('LeftPoint')), _point(r.get('RightPoint'))
        k = f"{_S(r.get('BarFace'))}|{_S(r.get('SpanDirection'))}|{_S(r.get('BarCount'))}|{_S(_round(_num(r.get('AbsoluteElevation'))))}"
        # pick the individual-bar set whose bars lie on this band (closest first-bar midpoint to the band line)
        cands = indiv_by_key.get(k) or []
        best = None
        best_d = math.inf
        mid = {'x': (p0['x'] + p1['x']) / 2, 'y': (p0['y'] + p1['y']) / 2}
        for c in cands:
            a, b = _points(c.get('Point0')), _points(c.get('Point1'))
            cm = {'x': 0, 'y': 0}
            for j, p in enumerate(a):
                bj = b[j] if j < len(b) else {'x': NAN, 'y': NAN}  # (b[j] undefined in JS: NaN)
                cm = {'x': cm['x'] + (p['x'] + bj['x']) / 2 / len(a), 'y': cm['y'] + (p['y'] + bj['y']) / 2 / len(a)}
            d = dist(cm, mid)
            if d < best_d:
                best_d = d
                best = c
        bars = []
        if best:
            a, b = _points(best.get('Point0')), _points(best.get('Point1'))
            bars = [{'a': p, 'b': b[j] if j < len(b) else None} for j, p in enumerate(a)]
        else:
            n = r.get('BarCount')
            for j in range(int(n or 0)):
                f = j / (n - 1) if n > 1 else 0.5
                off = {'x': left['x'] + (right['x'] - left['x']) * f - mid['x'], 'y': left['y'] + (right['y'] - left['y']) * f - mid['y']}
                bars.append({'a': {'x': p0['x'] + off['x'], 'y': p0['y'] + off['y']}, 'b': {'x': p1['x'] + off['x'], 'y': p1['y'] + off['y']}})
        length = _round(sum(dist(b['a'], b['b']) for b in bars) / len(bars)) if bars else _round(dist(p0, p1))
        bands.append({
            'id': f'RB{i + 1}', 'face': 'T' if r.get('BarFace') == 1 else 'B', 'dir': r.get('SpanDirection'), 'dia': typ['dia'], 'typeName': typ.get('Name') or f"T{_S(typ['dia'])}",
            'designedBy': 'program' if r.get('DesignedBy') == 2 else 'user',  # RAM: 1 = drawn by the engineer, 2 = generated by the program for a design strip
            'count': r.get('BarCount'), 'spacing': _round(_L(r.get('BarSpacing'))), 'width': _round(dist(left, right)), 'length': length, 'elevation': _L(r.get('AbsoluteElevation')),
            'ends': [r.get('BarEnd0'), r.get('BarEnd1')], 'bars': bars, 'p0': p0, 'p1': p1, 'matched': bool(best),
        })

    # shear regions (stirrups)
    shear = []
    for i, r in enumerate(rows('TransverseRebarRegion')):
        typ = rebar_types.get(r.get('BarType')) or {'dia': 10}
        shear.append({'id': f'SR{i + 1}', 'a': _point(r.get('Point0')), 'b': _point(r.get('Point1')), 'dia': typ['dia'], 'legs': r.get('StirrupLegs'), 'spacing': _round(_L(r.get('StirrupSpacing'))), 'length': _round(dist(_point(r.get('Point0')), _point(r.get('Point1'))))})
    # the punching checks carry their settings only (RAM keeps no pass / fail result in the file): the tributary area RAM
    # computed (0.01 mm² → m²) and the cover to the bar centroid feed the office's indicative check (lib/punching.mjs)
    punching = [{'name': r.get('Name'), 'p': _point(r.get('Point0')), 'ssr': r.get('SsrSystem'), 'coverToCgs': _L(r.get('CoverToCGS')), 'tribArea': r['AutoTribArea'] / 1e8 if (r.get('AutoTribArea') or 0) > 0 else None, 'ssrDesired': _truthy(r.get('SsrDesignDesired'))} for r in punch_checks]
    # area loads by loading type (RAM units: N per 0.01 mm² → kN/m² is x 1e5; negative = downwards). The loading layer
    # (self_dead / other_dead / live_*) is reached through the category → loading level → loading layer chain.
    loading_types = {r['UID']: r.get('LoadingType') or _S(r.get('Name') or '').lower() for r in rows('LoadingLayer')}
    loading_levels = {r['UID']: r.get('ParentUID') for r in rows('LoadingLevel')}
    load_cats = {r['UID']: loading_types.get(loading_levels.get(r.get('ParentUID'))) or loading_types.get(r.get('ParentUID')) or 'unknown' for r in rows('AreaLoadCategory')}
    area_loads = []
    for r in rows('AreaLoad'):
        if not _truthy(r.get('MultiPoint')):
            continue
        typ = load_cats.get(r.get('ParentUID')) or 'unknown'
        q = -min(r.get('ALFz0') if r.get('ALFz0') is not None else 0, r.get('ALFz1') if r.get('ALFz1') is not None else 0, r.get('ALFz2') if r.get('ALFz2') is not None else 0) * 1e5  # kN/m², downwards positive
        kind = 'live' if re.search(r'live', _S(typ)) else ('dead' if re.search(r'other_dead|dead', _S(typ)) and not re.search(r'self', _S(typ)) else typ)
        area_loads.append({'type': kind, 'q': _round(q * 100) / 100, 'polygon': clean_polygon(_points(r.get('MultiPoint')))})
    area_loads = [l for l in area_loads if len(l['polygon']) >= 3]
    # stud rail sets (SSR) designed by RAM (or drawn by the user) at the columns that need punching reinforcement:
    # the rails (start / end per rail), the studs per rail and the stud spacing; the office draws its stirrup detail instead
    ssr_systems = by_uid(rows('SsrSystem'))
    ssr = []
    for i, r in enumerate([r for r in rows('SsrSet') if _truthy(r.get('Point0')) and _truthy(r.get('Point1')) and _truthy(r.get('LocationPoint'))]):
        p0, p1 = _points(r.get('Point0')), _points(r.get('Point1'))
        counts = [int(m) for m in re.findall(r'-?\d+', _S(r.get('StudCount')) if _truthy(r.get('StudCount')) else '')]
        sys_ = ssr_systems.get(r.get('SsrSystem')) or {}
        stud_area = _mm2(sys_['StudArea']) if _truthy(sys_.get('StudArea')) else 78.5
        ssr.append({
            'id': f'SSR{i + 1}', 'loc': _point(r.get('LocationPoint')), 'designedBy': 'program' if r.get('DesignedBy') == 2 else 'user',
            'first': _L(r.get('StudSpacingFirst') or 0), 'typ': _L(r.get('StudSpacingTypical') or 0), 'studArea': stud_area, 'studDia': _round(math.sqrt((4 * stud_area) / math.pi)),
            'rails': [{'a': a, 'b': p1[k] if k < len(p1) else a, 'count': (counts[k] if k < len(counts) else 0) or max([0, *counts])} for k, a in enumerate(p0)],
        })

    # background DXF geometry imported into RAM (for reference only)
    background = []
    for r in rows('DXFLine'):
        background.append({'type': 'LINE', 'layer': r.get('CadLayerName'), 'pts': [_point(r.get('Point0') or r.get('MultiPoint')), _point(r.get('Point1'))]})
    for r in rows('DXFPolyline'):
        background.append({'type': 'PLINE', 'layer': r.get('CadLayerName'), 'pts': _points(r.get('MultiPoint'))})

    db.close()
    return {
        'project': {'headings': headings, 'company': headings[0] if len(headings) > 0 else '', 'name': headings[1] if len(headings) > 1 else '', 'part': headings[2] if len(headings) > 2 else '', 'revision': headings[3] if len(headings) > 3 else ''},
        'materials': {'fc': fc, 'fcu': _round(_MPa(concrete.get('FcuFinal'))) if _truthy(concrete.get('FcuFinal')) else None, 'fy': fy, 'coverTop': cover_top, 'coverBot': cover_bot, 'concreteName': concrete.get('Name'), 'rebarTypes': [{'name': t.get('Name'), 'dia': t['dia'], 'area': t['area']} for t in rebar_types.values()]},
        'pt': {'system': pt_system.get('Name'), 'strandArea': strand_area, 'fpu': _MPa(strand.get('Fpu')) if _truthy(strand.get('Fpu')) else None, 'jackStress': _MPa(anchor.get('JackStress')) if _truthy(anchor.get('JackStress')) else None, 'strandsPerDuct': duct.get('StrandsPerDuct'), 'ductType': duct.get('PTSystemType'), 'ductWidth': _L(duct.get('DuctWidth')) if _truthy(duct.get('DuctWidth')) else None, 'ductHeight': _L(duct.get('DuctHeight')) if _truthy(duct.get('DuctHeight')) else None, 'fse': _MPa(pt_system.get('Fse')) if _truthy(pt_system.get('Fse')) else None},
        'slab': {'outline': outline, 'holes': holes, 'allLoops': all_loops, 'bodies': bodies, 'tocs': tocs, 'baseThickness': base_thickness, 'thicknesses': [{'thickness': thk, 'elements': n} for thk, n in thicknesses], 'thickZones': thick_zones, 'areas': slab_areas, 'elements': elements},
        'columns': columns, 'walls': walls, 'beams': beams, 'tendons': tendons, 'bands': bands, 'shear': shear, 'punching': punching, 'ssr': ssr, 'areaLoads': area_loads, 'background': background,
    }


def tendon_height_at(t, s):
    """
    The tendon CGS height above the soffit at a distance `s` along the tendon: between two nodes the profile is the
    usual reverse curve, a parabola over `inflection` x the span next to the high point tangent to the sagging
    parabola over the rest (straight when both nodes sit at one height).
    """
    if not t.get('heights'):
        return None
    acc = 0
    pts = t['pts']
    for i in range(len(pts) - 1):
        span = dist(pts[i], pts[i + 1])
        if s > acc + span + 1e-6 and i + 2 < len(pts):
            acc += span
            continue
        x = max(0, min(span, s - acc))
        e0, e1 = t['heights'][i], t['heights'][i + 1]
        if e0 is None or e1 is None:
            return e0 if e0 is not None else (e1 if e1 is not None else None)
        if abs(e1 - e0) < 1 or span < 1:
            return e0
        ir = t.get('inflection') or 0.2
        # measure from the high end
        from_high = x if e0 >= e1 else span - x
        eh, el = max(e0, e1), min(e0, e1)
        D = eh - el
        L1 = ir * span
        L2 = span - L1
        y = eh - (D * from_high * from_high) / (L1 * span) if from_high <= L1 else el + (D * (span - from_high) * (span - from_high)) / (L2 * span)
        return _round(y)
    return t['heights'][len(t['heights']) - 1]


def tendon_extremes(t):
    """High / low points of a tendon: every node that is a local maximum / minimum of the profile (ends included)."""
    if not t.get('heights'):
        return []
    out = []
    n = len(t['pts'])
    for i in range(n):
        h = t['heights'][i]
        if h is None:
            continue
        prev = t['heights'][i - 1] if i > 0 else None
        nxt = t['heights'][i + 1] if i + 1 < n else None
        hi = (prev is None or h >= prev) and (nxt is None or h >= nxt)
        lo = (prev is None or h <= prev) and (nxt is None or h <= nxt)
        if hi and lo:
            continue  # flat: a straight tendon
        out.append({'i': i, 'p': t['pts'][i], 'h': h, 'kind': 'H' if hi else 'L', 'end': i == 0 or i == n - 1})
    return out


# ---------------------------------------------------------------- to the generator's model
def _rot(p, c, a):
    s, k = math.sin(a), math.cos(a)
    x, y = p['x'] - c['x'], p['y'] - c['y']
    return {'x': c['x'] + x * k - y * s, 'y': c['y'] + x * s + y * k}


def mode_angle(angles):
    bins = {}
    for a in angles:
        k = _round(a / 2.5) * 2.5
        bins[k] = bins.get(k, 0) + 1
    ordered = sorted(bins.items(), key=lambda e: e[1], reverse=True)
    return (ordered[0][0] if ordered else None) or 0


# Split the RAM model into slab bodies (one level per disconnected slab
# outline), rotate each body into its own orthogonal frame and hand back a
# model the sheet composers understand, with the RAM design attached.
def clip_tendon(t, poly, tol=400):
    """
    A tendon cut to a polygon (a slab body, or a drawing part): the piece inside it with its profile arrays kept in
    step (heights and thicknesses interpolated at the cut), the cut ends marked (`cut`) and no longer live; null when
    the tendon has no piece inside. `tol` lets the anchors sit a little outside the slab edge.
    """
    c = clip_polyline_to_polygon(t['pts'], poly, tol)
    if not c or len(c['pts']) < 2:
        return None
    if not c.get('cutStart') and not c.get('cutEnd'):
        return t
    # a cut point was added at an end when the clipped polyline starts / ends away from the original points kept
    add_start = c.get('cutStart') and dist(c['pts'][0], t['pts'][c['from']]) > 1
    add_end = c.get('cutEnd') and dist(c['pts'][len(c['pts']) - 1], t['pts'][c['to']]) > 1

    def along(arr):
        if not arr:
            return arr
        kept = arr[c['from']:c['to'] + 1]

        def lerp(i, j, q):
            a = arr[i] if 0 <= i < len(arr) else None
            b = arr[j] if 0 <= j < len(arr) else None
            if a is None or b is None:
                return a if a is not None else (b if b is not None else None)
            Lg = dist(t['pts'][i], t['pts'][j]) or 1
            f = min(1, dist(t['pts'][i], q) / Lg)
            return a + (b - a) * f
        if add_start:
            kept.insert(0, lerp(c['from'], c['from'] - 1, c['pts'][0]))
        if add_end:
            kept.append(lerp(c['to'], c['to'] + 1, c['pts'][len(c['pts']) - 1]))
        return kept
    length = sum(dist(c['pts'][i - 1], c['pts'][i]) for i in range(1, len(c['pts'])))
    return {
        **t, 'pts': c['pts'], 'heights': along(t.get('heights')), 'thks': along(t.get('thks')), 'length': _round(length),
        'live': [False if c.get('cutStart') else t['live'][0], False if c.get('cutEnd') else t['live'][1]],
        'elongations': [None if c.get('cutStart') else t['elongations'][0], None if c.get('cutEnd') else t['elongations'][1]] if t.get('elongations') else t.get('elongations'),
        'cut': [bool(c.get('cutStart')), bool(c.get('cutEnd'))], 'fullLength': t.get('fullLength') or t.get('length'),
    }


def ram_to_model(ram, level_name='1ST FLOOR', level_id=None, spec=None):
    spec_overrides = spec if spec is not None else {}
    assumptions, findings = [], []
    # bodies: the outline plus every other outer loop
    loops = [p for p in [ram['slab'].get('outline'), *ram['slab'].get('holes', [])] if p]
    outer = ram['slab'].get('allLoops') or loops
    # one body per outer loop of each top-of-concrete level (a slab at another level is a separate slab: office rule)
    toc_bodies = ram['slab']['bodies'] if (ram['slab'].get('bodies') or []) else None
    bodies = [b['polygon'] for b in toc_bodies] if toc_bodies else [p for p in outer if not any(q is not p and abs(polygon_area(q)) > abs(polygon_area(p)) and point_in_polygon(p[0], q) for q in outer)]

    def toc_of(body):
        if not toc_bodies:
            return 0
        found = next((b for b in toc_bodies if b['polygon'] is body), None)
        return found.get('toc') if found and found.get('toc') is not None else 0

    def holes_of(body):
        if toc_bodies:
            found = next((b for b in toc_bodies if b['polygon'] is body), None)
            return (found.get('holes') if found else None) or []
        return [q for q in outer if q is not body and point_in_polygon(q[0], body) and abs(polygon_area(q)) < abs(polygon_area(body))]
    stepped = bool(toc_bodies) and len(set(b['toc'] for b in toc_bodies)) > 1

    def inside(p, poly):
        return point_in_polygon(p, poly)
    materials = ram['materials']
    spec = {
        'fc': materials.get('fc') or 30, 'fy': materials.get('fy') or 420, 'cover': max(materials.get('coverTop') or 25, materials.get('coverBot') or 25), 'stock': 12000, 'lambda': 1,
        **spec_overrides,
    }
    levels = []
    for i, body in enumerate(bodies):
        holes = holes_of(body)

        # a column whose centre sits on the slab edge (corner / edge columns) belongs to the body too
        def near(p, poly, tol):
            return inside(p, poly) or dist_to_polygon(p, poly) <= tol
        cols = [c for c in ram['columns'] if near({'x': c['cx'], 'y': c['cy']}, body, max(c['w'], c['h']) / 2) and not any(inside({'x': c['cx'], 'y': c['cy']}, h) for h in holes_of(body))]
        angle_cols = mode_angle([_mod180(c['angle']) for c in cols]) if cols else 0
        c0 = centroid(body)
        # the plan on the sheet (`spec.rotate`): 'auto' turns a plan that stands taller than wide by 90° so that its long
        # side lies along the landscape sheet (a plan that would not fit fits, or fits at a larger scale); 0 / 90 force it
        # (judged body by body: each body is its own plan on its own sheets)
        bb0 = bbox([_rot(p, c0, -(angle_cols * math.pi) / 180) for p in body])
        rot_opt = _S(spec_overrides.get('rotate') if spec_overrides.get('rotate') is not None else 'auto')
        turn = 90 if rot_opt == '90' else (0 if rot_opt == '0' else (90 if bb0['h'] > bb0['w'] * 1.05 else 0))
        angle_deg = angle_cols + turn
        theta = -(angle_deg * math.pi) / 180

        def R(p):
            return _rot(p, c0, theta)
        outline = [R(p) for p in body]
        areas_in = sorted([{**a, 'area': abs(polygon_area(a['polygon']))} for a in ram['slab']['areas'] if inside(centroid(a['polygon']), body)], key=lambda a: a['area'], reverse=True)
        by_thk = {}
        for e in ram['slab'].get('elements') or []:
            if inside(e['centroid'], body):
                by_thk[e['thickness']] = by_thk.get(e['thickness'], 0) + e['area']
        dominant_list = sorted(by_thk.items(), key=lambda e: e[1], reverse=True)
        dominant = dominant_list[0] if dominant_list else None
        body_thickness = dominant[0] if dominant else (areas_in[0]['thickness'] if areas_in else ram['slab']['baseThickness'])

        def beam_pieces(bm):
            pieces = [pc for pc in clip_segment_to_polygon(bm['a'], bm['b'], body) if dist(pc[0], pc[1]) > 300]
            if not pieces:
                return [{**bm, 'a': R(bm['a']), 'b': R(bm['b']), 'polygon': [R(p) for p in bm['polygon']]}]
            out = []
            for a, b in pieces:
                Lg = dist(a, b) or 1
                u = {'x': (b['x'] - a['x']) / Lg, 'y': (b['y'] - a['y']) / Lg}
                n = {'x': -u['y'], 'y': u['x']}
                w = bm['t'] / 2
                out.append({**bm, 'a': R(a), 'b': R(b), 'polygon': [R(p) for p in [{'x': a['x'] + n['x'] * w, 'y': a['y'] + n['y'] * w}, {'x': b['x'] + n['x'] * w, 'y': b['y'] + n['y'] * w}, {'x': b['x'] - n['x'] * w, 'y': b['y'] - n['y'] * w}, {'x': a['x'] - n['x'] * w, 'y': a['y'] - n['y'] * w}]]})
            return out
        level_beams = []
        for bm in ram.get('beams') or []:
            if inside(centroid(bm['polygon']), body) or near(centroid(bm['polygon']), body, bm['t']):
                level_beams.extend(beam_pieces(bm))
        level_walls = []
        for w in ram['walls']:
            for seg in clip_segment_to_polygon(w['a'], w['b'], body):
                a, b = seg[0], seg[1]
                if math.hypot(b['x'] - a['x'], b['y'] - a['y']) > 50:
                    level_walls.append({'a': R(a), 'b': R(b), 't': w.get('t')})

        def pour_strip(j, a):
            b = bbox(a['polygon'])
            return {'id': f'PS{j + 1}', 'polygon': [R(p) for p in a['polygon']], 'width': min(b['w'], b['h']), 'length': max(b['w'], b['h'])}
        level = {
            # the level code registered for the project (B1, GF, L03 ...) goes into the drawing numbers when given
            'id': (f'{_S(level_id)}-{i + 1}' if len(bodies) > 1 else _S(level_id)) if level_id else f"L{str(i + 1).rjust(2, '0')}", 'customId': bool(level_id),
            'name': f'{level_name} - BODY {i + 1}' if len(bodies) > 1 else level_name, 'rotation': angle_deg, 'frame': {'cx': c0['x'], 'cy': c0['y'], 'angle': angle_deg}, 'sheetTurn': turn,
            'thickness': body_thickness, 'outline': outline, 'bbox': bbox(outline),
            'columns': [{**c, 'id': f'C{j + 1}', 'cx': R({'x': c['cx'], 'y': c['cy']})['x'], 'cy': R({'x': c['cx'], 'y': c['cy']})['y'], 'angle': _round(_mod180(c['angle'] - angle_deg) * 10) / 10} for j, c in enumerate(cols)],
            # (a hole in the RAM mesh has a vertex at every element node: the collinear ones are dropped so that a long
            # void side is one side, with one U-bar symbol and one call-out)
            'openings': [{'id': f'O{j + 1}', 'kind': 'polygon', 'polygon': simplify_polygon([R(p) for p in h], 30)} for j, h in enumerate(holes)],
            'voids': [], 'sunken': [], 'stairs': [],
            # beams whose axis lies in this body (an edge beam along the slab edge, or an interior beam with slab both sides)
            # beams: the part of each beam axis inside this body (an axis crossing into another body is cut there)
            'beams': level_beams,
            'tos': toc_of(body) if stepped else None, 'toc': toc_of(body),
            'walls': level_walls,
            'thickZones': [{'id': f'Z{j + 1}', 'thickness': a['thickness'], 'polygon': [R(p) for p in a['polygon']]} for j, a in enumerate([a for a in areas_in if a['thickness'] > body_thickness + 1 and a['behaviour'] != 'custom'])],
            # a slab area of "custom" behaviour no wider than 1.5 m is a pour (infill) strip: the office's pour strip detail applies
            'pourStrips': [pour_strip(j, a) for j, a in enumerate([a for a in areas_in if a['behaviour'] == 'custom' and min(bbox(a['polygon'])['w'], bbox(a['polygon'])['h']) <= 1500])],
            'customZones': [{'polygon': [R(p) for p in a['polygon']], 'thickness': a['thickness']} for a in areas_in if a['behaviour'] == 'custom' and min(bbox(a['polygon'])['w'], bbox(a['polygon'])['h']) > 1500],
            'ubar': {'edges': 'all', 'circles': []},
            'pt': {'zones': [{'id': 'PT1', 'polygon': outline}], 'tendons': []},  # the whole body is post-tensioned
            'ram': {
                'bands': [{**b, 'p0': R(b['p0']), 'p1': R(b['p1']), 'bars': [{'a': R(bar['a']), 'b': R(bar['b'])} for bar in b['bars']]} for b in ram['bands'] if inside({'x': (b['p0']['x'] + b['p1']['x']) / 2, 'y': (b['p0']['y'] + b['p1']['y']) / 2}, body) or any(inside(bar['a'], body) for bar in b['bars'])],
                # a tendon is drawn on the body it lies in; one crossing into another body is cut at the edge (nothing drawn outside the slab)
                'tendons': [{**t, 'pts': [R(p) for p in t['pts']]} for t in [clip_tendon(t, body, 400) for t in ram['tendons'] if any(inside(p, body) for p in t['pts'])] if t],
                'shear': [{**s, 'a': R(s['a']), 'b': R(s['b'])} for s in ram['shear'] if inside({'x': (s['a']['x'] + s['b']['x']) / 2, 'y': (s['a']['y'] + s['b']['y']) / 2}, body)],
                'punching': [{**p, 'p': R(p['p'])} for p in ram['punching'] if near(p['p'], body, 500)],
                'ssr': [{**st, 'loc': R(st['loc']), 'rails': [{**r, 'a': R(r['a']), 'b': R(r['b'])} for r in st['rails']]} for st in (ram.get('ssr') or []) if near(st['loc'], body, 500)],
                'areaLoads': [{**l, 'polygon': [R(p) for p in l['polygon']]} for l in (ram.get('areaLoads') or []) if any(inside(p, body) for p in l['polygon']) or inside(centroid(l['polygon']), body)],
                'pt': ram['pt'],
            },
        }

        # grid from column positions in the local frame
        def cluster(vals):
            out = []
            for v in sorted(vals):
                l = out[-1] if out else None
                if l and abs(l['v'] - v) < 400:
                    l['n'] += 1
                    l['v'] = (l['v'] * (l['n'] - 1) + v) / l['n']
                else:
                    out.append({'v': v, 'n': 1})
            return [c['v'] for c in out]
        letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
        ob = level['bbox']
        level['grid'] = {
            'x': [{'label': letters[k % len(letters)], 'x': x, 'y1': ob['minY'], 'y2': ob['maxY']} for k, x in enumerate(cluster([c['cx'] for c in level['columns']]))],
            'y': [{'label': str(k + 1), 'y': y, 'x1': ob['minX'], 'x2': ob['maxX']} for k, y in enumerate(cluster([c['cy'] for c in level['columns']]))],
            'source': 'derived from column positions',
        }
        for c in level['columns']:
            gx = next((g for g in level['grid']['x'] if abs(g['x'] - c['cx']) < 400), None)
            gy = next((g for g in level['grid']['y'] if abs(g['y'] - c['cy']) < 400), None)
            if gx and gy:
                c['id'] = f"{gx['label']}/{gy['label']}"
        findings.append(f"{level['id']} {level['name']}: {_S(_round(abs(polygon_area(outline)) / 1e6))} m², {len(level['columns'])} columns, {len(level['walls'])} wall segments, {len(level['thickZones'])} thickened zones, {len(level['pourStrips'])} pour strips, {len(level['ram']['bands'])} designed bar bands, {len(level['ram']['tendons'])} tendons, {len(level['openings'])} openings{f', rotated {_S(angle_deg)}° to its local frame' if angle_deg else ''}.")
        if level['customZones']:
            sizes = ', '.join(f"{_S(_round(bbox(z['polygon'])['w'] / 1000))} x {_S(_round(bbox(z['polygon'])['h'] / 1000))} m" for z in level['customZones'])
            assumptions.append({'level': level['id'], 'text': f"{len(level['customZones'])} slab area(s) of \"custom\" behaviour wider than 1.5 m in {level['name']} ({sizes}) are drawn as slab; if one is a pour strip or a ramp, set it on the plan."})
        if angle_cols:
            assumptions.append({'level': level['id'], 'text': f"Body {i + 1} is rotated {_S(angle_cols)}° on the site; the plan is drawn in its local frame (north arrow rotated accordingly)."})
        if turn:
            why = f"its {_S(_round(bb0['h'] / 1000))} m side is longer than its {_S(_round(bb0['w'] / 1000))} m side: the long side lies along the sheet" if rot_opt == 'auto' else 'as set for the project'
            assumptions.append({'level': level['id'], 'text': f"{level['name']} is turned {_S(turn)}° on the sheet ({why}); the north arrow follows."})
        assumptions.append({'level': level['id'], 'text': 'Grid lines are not modelled in RAM Concept: the grid is derived from the column positions and lettered / numbered consecutively; to be replaced by the architectural grid references.'})
        levels.append(level)
    assumptions.append({'text': f"Reinforcement, tendons and materials are taken from the RAM Concept model (f'c {_S(spec['fc'])} MPa from {materials.get('concreteName') or 'the model'}, fy {_S(spec['fy'])} MPa, cover {_S(spec['cover'])} mm). Bar cutting lengths add SBC 304-18 hooks (12 Ø) where a bar ends at a free edge and split runs longer than 12 m with Class B laps."})
    assumptions.append({'text': f"Punching: RAM designed stud rails at {len(ram['ssr'])} columns (SSR sets); the design drawings convert them to the office stirrup detail (PS types) at those columns, the shop sheets show the minimum link arrangement to be confirmed against the RAM punching report." if (ram.get('ssr') or []) else 'Punching shear results are not stored in the RAM file (no stud rails designed): links are shown as the minimum detailing arrangement and are to be confirmed against the RAM punching report.'})
    assumptions.append({'text': 'The office standard reinforcement (bottom mesh, top bars over columns, edge U-bars, trimmers, punching links) is applied to the RAM slab exactly as for a G.A. drawing; the bands designed in RAM Concept are drawn on top of it as ADDITIONAL reinforcement (sheets 02A / 03A, marks ADD.B / ADD.T).'})
    pt_spec = {**spec, 'code_reference': None, 'sources': {'code': 'assumed', 'fc': 'RAM model', 'fy': 'RAM model', 'cover': 'RAM model'}, 'found': [f"RAM bar type {_S(t['name'])} ({_S(t['area'])} mm²)" for t in materials['rebarTypes']]}
    base = {'bottom': {'dia': 12, 'spacing': 200}, 'topColumns': {'dia': 16, 'spacing': 150}, 'uEdge': {'dia': 12, 'spacing': 200, 'leg': 1200, 'total': 4000, 'beamLeg': 400, 'beamTop': 3600}, 'uCircle': {'dia': 12, 'spacing': 150, 'leg': 1200}, 'edgeBars': {'dia': 12, 'count': 2}, 'ringBars': {'dia': 12, 'count': 2}, 'voids': {'dia': 12, 'count': 2}, 'openings': {'dia': 16, 'count': 2, 'diagDia': 12, 'diagCount': 2, 'uDia': 12, 'uSpacing': 200, 'uLeg': 600}, 'sunken': {'dia': 12, 'count': 2, 'uDia': 10, 'uSpacing': 200, 'uLeg': 600}, 'punching': {'dia': 10, 'legSpacing': 100, 'extentFactor': 2.0}}
    return {
        'source': {'units': 'mm (RAM internal 0.1 mm)', 'entities': len(ram['bands']) + len(ram['tendons']) + len(ram['columns']), 'layers': [], 'ram': True},
        # the office / project spec overrides the base per group: `uEdge: {total: 4400}` keeps the base's legs
        'code_reference': None, 'spec': {**base, **pt_spec, **{k: {**base[k], **pt_spec[k]} for k in base if isinstance(pt_spec.get(k), dict)}}, 'levels': levels, 'assumptions': assumptions, 'findings': findings, 'ram': ram,
    }
