"""
The reference plan: the architect's (or the structural) drawing of the level, uploaded next to the RAM model so
that the sheets carry the project's own grid, the columns as drawn and the slab edges instead of what RAM
holds. The two are matched in one point: automatically by fitting the columns of the drawing onto the columns
of the model (any translation, the drawing turned by 0 / 90 / 180 / 270), or by a common point given by hand
(a grid intersection or a column corner read in both), with an optional turn.

Port of `shopdrawings/lib/reference.mjs`.
"""
import math
import re

from .dxf_reader import parse_dxf
from .extract import extract_model
from .geometry import bbox, dist, centroid, polygon_area, point_in_polygon, js_round

MATCH_TOL = 300  # mm: a drawing column this close to a model column is the same column
ROTATIONS = [0, 90, 180, 270]


def _rot_deg(p, deg, c=None):
    if c is None:
        c = {'x': 0, 'y': 0}
    a = (deg * math.pi) / 180
    s, k = math.sin(a), math.cos(a)
    x, y = p['x'] - c['x'], p['y'] - c['y']
    return {'x': c['x'] + x * k - y * s, 'y': c['y'] + x * s + y * k}


def _number(v):
    """JS `Number(v) || 0`."""
    if v is None or v is False:
        return 0
    if v is True:
        return 1
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0
    if math.isnan(n) or n == 0:
        return 0
    return int(n) if n == int(n) else n


def _js_mod(a, m):
    """JS `%` keeps the sign of the dividend."""
    return a % m if a >= 0 else -((-a) % m)


def read_reference_plan(text, options=None):
    """Reads the drawing: its slab outlines, columns and grid (labels from the bubbles), in mm."""
    options = options or {}
    dxf = parse_dxf(text)
    model = extract_model(dxf, {'levelNames': options.get('levelNames')})
    levels = [{
        'name': l['name'],
        'outline': l['outline'], 'bbox': l['bbox'],
        'columns': [{'shape': c.get('shape') or 'rect', 'cx': c['cx'], 'cy': c['cy'], 'w': c.get('w'), 'h': c.get('h'), 'd': c.get('d'), 'angle': c.get('angle') or 0} for c in (l.get('columns') or [])],
        'grid': {'x': [{'label': g['label'], 'x': g['x']} for g in ((l.get('grid') or {}).get('x') or [])],
                 'y': [{'label': g['label'], 'y': g['y']} for g in ((l.get('grid') or {}).get('y') or [])],
                 'source': (l.get('grid') or {}).get('source') or 'drawing'},
        'openings': l.get('openings') or [],
        'walls': l.get('walls') or [],
    } for l in model['levels']]
    all_ = {'columns': [c for l in levels for c in l['columns']], 'outlines': [l['outline'] for l in levels]}
    # one grid for the whole drawing: the labels of the largest plan (they are the same lines for every plan on it)
    ranked = sorted(levels, key=lambda l: -abs(polygon_area(l['outline'])))
    main = ranked[0] if ranked else None
    return {
        'units': model['source']['units'], 'entities': model['source']['entities'], 'levels': levels, 'columns': all_['columns'], 'outlines': all_['outlines'],
        'grid': main['grid'] if main else {'x': [], 'y': [], 'source': 'none'},
        'gridFromDrawing': main['grid']['source'] == 'drawing' if main else False,
        'findings': model['findings'], 'assumptions': [a['text'] for a in model['assumptions']],
    }


def align_by_columns(ref_columns, ram_columns):
    """
    The transform that puts the drawing onto the model, fitted on the columns: for every turn and every pairing of
    a drawing column with a model column the translation that makes them coincide is tried, and the one that puts
    the most drawing columns on model columns wins. Returns { rot, dx, dy, matched, total, score } where a drawing
    point maps as rot(p, rot) + (dx, dy).
    """
    refs = [{'x': c['cx'], 'y': c['cy']} for c in ref_columns]
    rams = [{'x': c['cx'], 'y': c['cy']} for c in ram_columns]
    if not refs or not rams:
        return None

    def key(p):
        return f"{js_round(p['x'] / MATCH_TOL)},{js_round(p['y'] / MATCH_TOL)}"
    cells = {}
    for p in rams:
        k = key(p)
        if k not in cells:
            cells[k] = []
        cells[k].append(p)

    def has_near(p):
        cx, cy = js_round(p['x'] / MATCH_TOL), js_round(p['y'] / MATCH_TOL)
        for i in range(-1, 2):
            for j in range(-1, 2):
                for q in cells.get(f'{cx + i},{cy + j}') or []:
                    if dist(p, q) <= MATCH_TOL:
                        return True
        return False

    best = None
    sample = [p for i, p in enumerate(refs) if i % math.ceil(len(refs) / 60) == 0] if len(refs) > 60 else refs
    for rot in ROTATIONS:
        turned = [_rot_deg(p, rot) for p in refs]
        turned_sample = [_rot_deg(p, rot) for p in sample]
        tried = set()
        for a in turned_sample:
            for b in rams:
                dx, dy = b['x'] - a['x'], b['y'] - a['y']
                tk = f'{js_round(dx / 50)},{js_round(dy / 50)}'
                if tk in tried:
                    continue
                tried.add(tk)
                matched = 0
                for p in turned:
                    if has_near({'x': p['x'] + dx, 'y': p['y'] + dy}):
                        matched += 1
                score = matched - math.hypot(dx, dy) / 1e9 - (1e-3 if rot else 0)
                if not best or score > best['score']:
                    best = {'rot': rot, 'dx': dx, 'dy': dy, 'matched': matched, 'total': len(refs), 'score': score}
    if not best:
        return None
    # refine the translation on the matched pairs (the mean offset), so a column drawn a little off does not pull it
    turned = [_rot_deg(p, best['rot']) for p in refs]
    sx, sy, n = 0, 0, 0
    for p in turned:
        q = {'x': p['x'] + best['dx'], 'y': p['y'] + best['dy']}
        nears = sorted([r for r in rams if dist(r, q) <= MATCH_TOL], key=lambda r: dist(r, q))
        near = nears[0] if nears else None
        if near:
            sx += near['x'] - p['x']
            sy += near['y'] - p['y']
            n += 1
    if n:
        best['dx'] = sx / n
        best['dy'] = sy / n
    best['dx'] = js_round(best['dx'])
    best['dy'] = js_round(best['dy'])
    return best


def align_by_point(o=None, **kw):
    """The transform from a common point: the drawing point `dxf` (turned by `rot`) lands on the model point `ram`.
    Takes the JS options object `{dxf, ram, rot = 0}` as a dict (or as keywords)."""
    o = {**(o or {}), **kw}
    dxf, ram, rot = o.get('dxf'), o.get('ram'), o.get('rot') if o.get('rot') is not None else 0
    t = _rot_deg(dxf, rot)
    return {'rot': rot, 'dx': ram['x'] - t['x'], 'dy': ram['y'] - t['y'], 'matched': None, 'total': None, 'byPoint': True}


def apply_reference(model, ref, opts=None, **kw):
    """
    Applies the reference to the model: the grid (labels and positions), the columns and the slab outline of every
    level are taken from the drawing where `use` says so. `ramColumns` are the model's columns in its own (world)
    coordinates, the same frame the transform is fitted in; each level carries `frame` (the turn of its body into
    the local drawing frame) so the drawing geometry follows it. Returns what was done for the report.
    The JS options object `{ use = {}, align = null, ramColumns = [] }` is `opts` (or keywords `use`, `align`,
    `ram_columns` / `ramColumns`).
    """
    o = {**(opts or {}), **kw}
    use = o.get('use') or {}
    align = o.get('align')
    ram_columns = o.get('ramColumns') if o.get('ramColumns') is not None else (o.get('ram_columns') or [])
    want = {'grid': use.get('grid') is not False, 'columns': use.get('columns') is not False, 'outline': use.get('outline') is not False}
    if align and align.get('mode') == 'point' and align.get('dxf') and align.get('ram'):
        T = align_by_point({'dxf': align['dxf'], 'ram': align['ram'], 'rot': _number(align.get('rot')) or 0})
    else:
        T = align_by_columns(ref['columns'], ram_columns)
    findings, assumptions = [], []
    if not T:
        findings.append('Reference plan: no columns to fit the drawing on the model; the drawing was not used.')
        return {'transform': None, 'findings': findings, 'assumptions': assumptions, 'used': {}}

    def to_world(p):
        q = _rot_deg(p, T['rot'])
        return {'x': q['x'] + T['dx'], 'y': q['y'] + T['dy']}

    used = {'grid': 0, 'columns': 0, 'outline': 0, 'unmatchedRam': [], 'unmatchedRef': []}
    ref_cols_world = [{**c, **to_world({'x': c['cx'], 'y': c['cy']}), 'angle': _js_mod((c.get('angle') or 0) + T['rot'], 180)} for c in ref['columns']]
    for level in model['levels']:
        fr = level.get('frame') or {'cx': 0, 'cy': 0, 'angle': 0}

        def to_local(p, fr=fr):
            return _rot_deg(p, -fr['angle'], {'x': fr['cx'], 'y': fr['cy']})

        def map_(p):
            return to_local(to_world(p))
        ob = level.get('bbox')
        # the outline: the drawing outline whose centre falls in this body (or the nearest), when it is one body
        if want['outline'] and ref['outlines']:
            cands = [{'poly': poly, 'c': centroid(poly)} for poly in ([map_(p) for p in poly] for poly in ref['outlines'])]
            mine = [o_ for o_ in cands if point_in_polygon(o_['c'], level['outline']) or point_in_polygon(centroid(level['outline']), o_['poly'])]
            if len(mine) == 1:
                poly = mine[0]['poly']
                a0, a1 = abs(polygon_area(level['outline'])), abs(polygon_area(poly))
                level['ramOutline'] = level['outline']
                level['outline'] = list(reversed(poly)) if polygon_area(poly) < 0 else poly
                level['bbox'] = bbox(level['outline'])
                if len(((level.get('pt') or {}).get('zones') or [])) == 1:
                    level['pt']['zones'][0]['polygon'] = level['outline']
                used['outline'] += 1
                if abs(a1 - a0) / max(a0, 1) > 0.05:
                    assumptions.append({'level': level['id'], 'text': f"The slab edge of {level['name']} is taken from the reference plan ({js_round(a1 / 1e6)} m²); the RAM slab is {js_round(a0 / 1e6)} m² ({js_round(((a1 - a0) / a0) * 100)} %): check the model against the drawing."})
            elif len(mine) > 1:
                findings.append(f"Reference plan: {len(mine)} slab outlines of the drawing fall in {level['name']}; the RAM outline is kept.")
            else:
                findings.append(f"Reference plan: no slab outline of the drawing matches {level['name']}; the RAM outline is kept.")
        # the columns: those of the drawing inside this body, sized as drawn; RAM columns with no drawn column are reported
        if want['columns'] and ref_cols_world:
            in_body = [c for c in ({**c, **to_local({'x': c['x'], 'y': c['y']})} for c in ref_cols_world)
                       if point_in_polygon({'x': c['x'], 'y': c['y']}, level['outline']) or (level.get('ramOutline') and point_in_polygon({'x': c['x'], 'y': c['y']}, level['ramOutline']))]
            ram_cols = level.get('columns') or []
            cols = []
            for j, c in enumerate(in_body):
                twins = sorted([r for r in ram_cols if dist({'x': r['cx'], 'y': r['cy']}, {'x': c['x'], 'y': c['y']}) <= MATCH_TOL], key=lambda r: dist({'x': r['cx'], 'y': r['cy']}, c))
                twin = twins[0] if twins else None
                cols.append({**(twin or {}), 'id': f'C{j + 1}', 'shape': c.get('shape'), 'cx': c['x'], 'cy': c['y'], 'w': c.get('w'), 'h': c.get('h'), 'd': c.get('d'), 'angle': c.get('angle'),
                             'below': twin.get('below') if twin else True, 'fromReference': True, 'ramId': (twin.get('id') if twin else None) or None})
            unmatched_ram = [r for r in ram_cols if not any(c['ramId'] == r.get('id') for c in cols)]
            for r in unmatched_ram:
                used['unmatchedRam'].append(f"{level['id']} {r.get('id')} ({js_round(r['cx'])}, {js_round(r['cy'])})")
            for c in [c for c in cols if not c['ramId']]:
                used['unmatchedRef'].append(f"{level['id']} {c['id']} ({js_round(c['cx'])}, {js_round(c['cy'])})")
            level['ramColumns'] = ram_cols
            level['columns'] = cols
            used['columns'] += len(cols)
        # the grid: the drawing's labels and lines, across the body
        if want['grid'] and ref.get('grid') and (ref['grid']['x'] or ref['grid']['y']):
            gx, gy = [], []
            ob2 = level.get('bbox') or ob
            lv0 = ref['levels'][0] if ref.get('levels') else None
            b0 = (lv0.get('bbox') or {}) if lv0 else {}
            min_y = b0.get('minY') if b0.get('minY') is not None else 0
            min_x = b0.get('minX') if b0.get('minX') is not None else 0
            lines = ([{'label': g['label'], 'a': {'x': g['x'], 'y': min_y}, 'b': {'x': g['x'], 'y': min_y + 1000}} for g in ref['grid']['x']]
                     + [{'label': g['label'], 'a': {'x': min_x, 'y': g['y']}, 'b': {'x': min_x + 1000, 'y': g['y']}} for g in ref['grid']['y']])
            for ln in lines:
                A, B = map_(ln['a']), map_(ln['b'])
                vertical = abs(B['x'] - A['x']) < abs(B['y'] - A['y'])
                if vertical:
                    if A['x'] >= ob2['minX'] - 3000 and A['x'] <= ob2['maxX'] + 3000:
                        gx.append({'label': ln['label'], 'x': A['x'], 'y1': ob2['minY'], 'y2': ob2['maxY']})
                elif A['y'] >= ob2['minY'] - 3000 and A['y'] <= ob2['maxY'] + 3000:
                    gy.append({'label': ln['label'], 'y': A['y'], 'x1': ob2['minX'], 'x2': ob2['maxX']})
            if gx and gy:
                level['grid'] = {'x': sorted(gx, key=lambda p: p['x']), 'y': sorted(gy, key=lambda p: p['y']), 'source': 'reference plan'}
                used['grid'] += 1
                for c in level.get('columns') or []:
                    cx = _near(level['grid']['x'], 'x', c['cx'])
                    cy = _near(level['grid']['y'], 'y', c['cy'])
                    if cx and cy and abs(cx['x'] - c['cx']) < 600 and abs(cy['y'] - c['cy']) < 600:
                        c['id'] = f"{cx['label']}/{cy['label']}"
            else:
                findings.append(f"Reference plan: the grid of the drawing does not reach {level['name']} after alignment; the derived grid is kept.")
    # the assumption about the derived grid no longer holds where the drawing's grid is used
    if used['grid']:
        model['assumptions'] = [a for a in (model.get('assumptions') or []) if not re.search(r'Grid lines are not modelled in RAM Concept', a.get('text') or '')]
    how = (f"matched on the given point (turned {T['rot']}°)" if T.get('byPoint')
           else f"fitted on the columns: {T['matched']} of {T['total']} drawing columns fall on model columns (turned {T['rot']}°, shift {js_round(T['dx'])}, {js_round(T['dy'])} mm)")
    used_parts = [s for s in ['grid' if used['grid'] else None, f"{used['columns']} columns" if used['columns'] else None, 'slab edge' if used['outline'] else None] if s]
    findings.append(f"Reference plan {how}; used: {', '.join(used_parts) or 'nothing'}.")
    if not T.get('byPoint') and T.get('matched') is not None and T['matched'] < min(3, T['total']):
        assumptions.append({'text': f"The reference plan could be fitted on only {T['matched']} column(s) of the model: give the common point by hand and check the drawing units."})
    if used['unmatchedRam']:
        assumptions.append({'text': f"{len(used['unmatchedRam'])} RAM column(s) have no column on the reference plan and are not drawn: {'; '.join(used['unmatchedRam'][:8])}{' …' if len(used['unmatchedRam']) > 8 else ''}."})
    if used['unmatchedRef']:
        assumptions.append({'text': f"{len(used['unmatchedRef'])} column(s) of the reference plan have no column in the RAM model (drawn as on the plan, no RAM design at them): {'; '.join(used['unmatchedRef'][:8])}{' …' if len(used['unmatchedRef']) > 8 else ''}."})
    assumptions.append({'text': f"Grid{', columns' if used['columns'] else ''}{' and slab edges' if used['outline'] else ''} are taken from the reference plan (the architectural / structural drawing), {'aligned on the point given' if T.get('byPoint') else 'aligned on the columns'}; the RAM model provides the design."})
    model['findings'].extend(findings)
    model['assumptions'].extend(assumptions)
    return {'transform': T, 'findings': findings, 'assumptions': assumptions, 'used': used}


def _near(arr, k, v):
    """`arr.reduce((b, g) => (Math.abs(g[k] - v) < Math.abs((b ? b[k] : Infinity) - v) ? g : b), null)`."""
    b = None
    for g in arr:
        if abs(g[k] - v) < abs((b[k] if b else math.inf) - v):
            b = g
    return b
