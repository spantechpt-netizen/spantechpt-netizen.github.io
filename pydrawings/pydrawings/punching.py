"""
Indicative punching check of every column of a RAM level, and the office's decision rule around it.

RAM Concept keeps no punching result in the .cpt (the PunchCheck rows are settings; the SsrSet rows exist only
where RAM designed stud rails), so the program cannot read "this column fails" from the file. It estimates the
check itself from what the file does hold - the tributary area RAM computed for each punching check, the area
loads by loading type, the slab thickness at the column, the concrete grade and the average precompression of
the tendons - with the SBC 304 / ACI 318 two-way shear rules (PT provisions where they apply). The estimate is
indicative: it flags the columns the engineer must look at in the RAM punching report; the engineer's own list
of columns failing in RAM (`spec.punching.ramFailed`) is flagged whatever the estimate says.

A flagged column blocks the run until the engineer decides: thicken the slab / drop and re-run, declare the column
passing in RAM (the estimate was conservative), or bypass at the design engineer's responsibility - then the
office punching detail (PS strips) is provided at that column, sized from the estimate, with the engineer's name
and the date printed on the sheets (`spec.punching.override`).
"""
import math

from .geometry import bbox, dist, polygon_area, point_in_polygon, dist_to_polygon, js_round
from .rebar import column_on_beam, column_in_band

PHI = 0.75
GAMMA = {'interior': 1.15, 'edge': 1.3, 'corner': 1.4}  # unbalanced moment allowance on the direct shear
ALPHA_S = {'interior': 40, 'edge': 30, 'corner': 20}
CONCRETE = 25  # kN/m³


def r2(v):
    return js_round(v * 100) / 100


def punching_check(level, spec=None):
    """The columns of a level checked one by one. `spec.punching`: { ramFailed: [ids], override, ramOk, psDia, rowSpacing }."""
    if spec is None:
        spec = {}
    out = {'method': 'indicative', 'columns': [], 'flagged': [], 'blocking': [], 'warnings': []}
    if not level.get('ram'):
        return out
    sp = spec.get('punching') or {}
    fc = spec.get('fc') or 30
    fy = spec.get('fy') or 420
    sqrt_fc = math.sqrt(fc)
    outline = level.get('outline') or []
    loads = level['ram'].get('areaLoads') or []
    ssr_sets = level['ram'].get('ssr') or []
    checks = level['ram'].get('punching') or []
    ram_failed = set(v for v in (str(v).strip().upper() for v in (sp.get('ramFailed') or [])) if v)
    ram_ok = set(str(v).strip().upper() for v in (sp.get('ramOk') or []))
    fpc = precompression(level)
    trib_estimate = tributary_areas(level)  # m² per column id, nearest-column share of the slab (used where RAM has no punching check)
    ps_dia = sp.get('psDia') or 12
    ps_s = sp.get('rowSpacing') or 100
    leg_area = (math.pi * ps_dia * ps_dia) / 4
    for c in level.get('columns') or []:
        w = c.get('d') if c.get('shape') == 'circle' else c.get('w')
        hh = c.get('d') if c.get('shape') == 'circle' else c.get('h')
        cc = {'x': c['cx'], 'y': c['cy']}
        zone = next((z for z in (level.get('thickZones') or []) if point_in_polygon(cc, z['polygon'])), None)
        h = zone['thickness'] if zone else level.get('thickness')
        # a column standing on a beam is carried by the beam: no punching of the slab, no check, nothing flagged
        # (unless the engineer reports it failing in RAM: their report wins and the column is checked and flagged)
        beam = column_on_beam(level, c)
        if beam and str(c.get('id')).upper() not in ram_failed:
            out['columns'].append({'id': c.get('id'), 'loc': 'beam', 'h': h, 'd': None, 'trib_m2': None, 'wu_kn_m2': None, 'Vu_kn': None, 'bo_mm': None, 'vu_mpa': None, 'phi_vc_mpa': None, 'phi_vmax_mpa': None, 'ratio': None, 'fpc_mpa': None, 'rule': 'BEAM', 'ssr': False, 'trib_source': '-', 'ram_failed': False, 'ram_ok': False, 'status': 'on beam', 'beam': beam.get('id')})
            continue
        # the office's scope limited to the PT band beams (`spec.scope: 'bands'`): a column outside every band stands in the
        # consultant's slab - its punching is the consultant's design, not checked here (the engineer's RAM report still wins)
        if spec.get('scope') == 'bands' and not column_in_band(level, c, spec) and str(c.get('id')).upper() not in ram_failed:
            out['columns'].append({'id': c.get('id'), 'loc': 'slab', 'h': h, 'd': None, 'trib_m2': None, 'wu_kn_m2': None, 'Vu_kn': None, 'bo_mm': None, 'vu_mpa': None, 'phi_vc_mpa': None, 'phi_vmax_mpa': None, 'ratio': None, 'fpc_mpa': None, 'rule': 'OTHERS', 'ssr': False, 'trib_source': '-', 'ram_failed': False, 'ram_ok': False, 'status': 'out of scope'})
            continue
        pc = next((p for p in checks if dist(p['p'], cc) < max(w, hh, 400)), None)
        d = max(h - ((pc or {}).get('coverToCgs') or (spec.get('cover') or 25) + 16), 0.6 * h)
        st_set = next((st for st in ssr_sets if dist(st['loc'], cc) < max(w, hh, 400)), None)
        # location: edges of the slab outline within the shear perimeter reach
        reach = max(w, hh) / 2 + 2 * d + 100
        edges = _edges_near(outline, cc, reach) if len(outline) else 0
        loc = 'corner' if edges >= 2 else 'edge' if edges == 1 else 'interior'
        # loads on the tributary area (RAM's own tributary area when the punching check carries it)
        trib = (pc or {}).get('tribArea') or trib_estimate.get(c.get('id')) or 0
        q = {'dead': 0, 'live': 0}
        for kind in ['dead', 'live']:
            here = [l for l in loads if l.get('type') == kind and point_in_polygon(cc, l['polygon'])]
            any_ = [l for l in loads if l.get('type') == kind]
            q[kind] = max(l['q'] for l in here) if len(here) else max(l['q'] for l in any_) if len(any_) else 0
        sw = CONCRETE * (h / 1000)
        wu = 1.2 * (sw + q['dead']) + 1.6 * q['live']  # kN/m²
        Vu = wu * trib * GAMMA[loc]  # kN
        # critical perimeter at d/2 from the faces
        c1, c2 = w, hh
        per = _perimeter_at(loc, c1, c2, d / 2, c.get('shape') == 'circle')
        vu = (Vu * 1000) / (per['bo'] * d)  # MPa
        beta = max(c1, c2) / max(1, min(c1, c2))
        aS = ALPHA_S[loc]
        # ACI 318-19 22.6.5: PT provisions for interior columns with a known precompression, else the non-prestressed vc
        pt_rule = loc == 'interior' and fpc is not None and fc <= 70
        if pt_rule:
            vc = min(0.29, 0.083 * aS * d / per['bo'] + 0.125) * sqrt_fc + 0.3 * min(3.5, max(0.9, fpc))
        else:
            vc = min(0.33, 0.17 * (1 + 2 / beta), 0.083 * (aS * d / per['bo'] + 2)) * sqrt_fc
        v_max = 0.5 * sqrt_fc  # the most the office stirrup detail can carry (stud rails 0.66)
        ratio = vu / (PHI * vc)
        ratio_max = vu / (PHI * v_max)
        status = 'ok' if ratio <= 1 else 'reinforce' if ratio_max <= 1 else 'fail'
        id_ = str(c.get('id')).upper()
        col = {
            'id': c.get('id'), 'loc': loc, 'h': h, 'd': js_round(d), 'trib_m2': r2(trib), 'wu_kn_m2': r2(wu), 'Vu_kn': js_round(Vu), 'bo_mm': js_round(per['bo']),
            'vu_mpa': r2(vu), 'phi_vc_mpa': r2(PHI * vc), 'phi_vmax_mpa': r2(PHI * v_max), 'ratio': r2(ratio),
            'fpc_mpa': r2(min(3.5, max(0.9, fpc))) if pt_rule else None, 'rule': 'PT' if pt_rule else 'RC', 'ssr': bool(st_set),
            'trib_source': 'RAM' if (pc or {}).get('tribArea') else 'estimated',
            'ram_failed': id_ in ram_failed, 'ram_ok': id_ in ram_ok, 'status': status,
        }
        # what the office detail would need at this column if it is reinforced here (rows at S covering the outer perimeter
        # where the concrete alone carries 0.17 sqrt(f'c); legs from Av/s = (vu - phi 0.17 sqrt(f'c)) bo / (phi fy))
        if status != 'ok' or col['ram_failed']:
            vcs = 0.17 * sqrt_fc
            bo_out = (Vu * 1000) / (PHI * vcs * d)
            x = max(0, (bo_out - per['b00']) / per['k'] - d / 2)
            rows = min(30, max(10 if loc == 'interior' else 12, math.ceil(x / ps_s) + 1))  # capped at 3 m of strips: past that the slab needs thickening, not stirrups
            av_s = max(0, (vu - PHI * vcs) * per['bo'] / (PHI * fy))  # mm²/mm
            strips = 4 if loc == 'interior' else 3 if loc == 'edge' else 2
            legs = min(12, max(4, 2 * math.ceil((av_s * ps_s) / leg_area / strips / 2)))
            col['detail'] = {'rows': rows, 'legs': legs, 's': ps_s, 'dia': ps_dia, 'avS': r2(av_s)}
        out['columns'].append(col)
        flagged = col['ram_failed'] or (status == 'fail' and not col['ram_ok']) or (status == 'reinforce' and not st_set and not col['ram_ok'])
        if flagged:
            out['flagged'].append(col['id'])
            if col['ram_failed'] or status == 'fail':
                out['blocking'].append(col['id'])
            else:
                out['warnings'].append(col['id'])
    out['fpc_mpa'] = r2(fpc) if fpc is not None else None
    out['fc'] = fc
    return out


def tributary_areas(level):
    """The slab area nearest to each column (m²): the outline sampled on a grid, every sample given to its nearest column.

    Returns a dict column id -> m² (the JS returns a Map)."""
    out = {}
    cols = level.get('columns') or []
    outline = level.get('outline') or []
    if not len(cols) or len(outline) < 3:
        return out
    b = bbox(outline)
    A = abs(polygon_area(outline))
    step = max(200, math.sqrt(A / 4000))
    holes = [p for p in (o.get('polygon') for o in (level.get('openings') or [])) if p and len(p) >= 3]
    walls = [w for w in (level.get('walls') or []) if w.get('polygon') and len(w['polygon']) >= 3]
    counts = {}
    y = b['minY'] + step / 2
    while y < b['maxY']:
        x = b['minX'] + step / 2
        while x < b['maxX']:
            p = {'x': x, 'y': y}
            if not point_in_polygon(p, outline) or any(point_in_polygon(p, h) for h in holes):
                x += step
                continue
            best = None
            bd = math.inf
            for c in cols:
                dd = math.hypot(c['cx'] - x, c['cy'] - y)
                if dd < bd:
                    bd = dd
                    best = c
            # a wall nearer than the nearest column carries this sample
            if any(dist_to_polygon(p, w['polygon']) < bd for w in walls):
                x += step
                continue
            counts[best.get('id')] = (counts.get(best.get('id')) or 0) + 1
            x += step
        y += step
    for id_, n in counts.items():
        out[id_] = (n * step * step) / 1e6
    return out


def _edges_near(outline, p, reach):
    """Slab edges of the outline within `reach` of the column centre (each straight side counted once)."""
    n = 0
    for i in range(len(outline)):
        a = outline[i]
        b = outline[(i + 1) % len(outline)]
        if dist(a, b) < 50:
            continue
        if _dist_to_segment(p, a, b) < reach:
            n += 1
    return min(n, 2)


def _dist_to_segment(p, a, b):
    dx = b['x'] - a['x']
    dy = b['y'] - a['y']
    l2 = dx * dx + dy * dy
    t = max(0, min(1, ((p['x'] - a['x']) * dx + (p['y'] - a['y']) * dy) / l2)) if l2 else 0
    return math.hypot(p['x'] - (a['x'] + t * dx), p['y'] - (a['y'] + t * dy))


def _perimeter_at(loc, c1, c2, r, circle):
    """The critical perimeter at offset r from the column faces: b0(r) = b00 + k r (k = 8 / 4 / 2 interior / edge / corner)."""
    if circle:
        D = c1
        if loc == 'interior':
            return {'bo': math.pi * (D + 2 * r), 'b00': math.pi * D, 'k': 2 * math.pi}
        if loc == 'edge':
            return {'bo': (math.pi * (D + 2 * r)) / 2 + D + 2 * r, 'b00': (math.pi * D) / 2 + D, 'k': math.pi + 2}
        return {'bo': (math.pi * (D + 2 * r)) / 4 + D + 2 * r, 'b00': (math.pi * D) / 4 + D, 'k': math.pi / 2 + 2}
    if loc == 'interior':
        return {'bo': 2 * (c1 + c2) + 8 * r, 'b00': 2 * (c1 + c2), 'k': 8}
    if loc == 'edge':
        return {'bo': c1 + 2 * c2 + 4 * r, 'b00': c1 + 2 * c2, 'k': 4}
    return {'bo': c1 + c2 + 2 * r, 'b00': c1 + c2, 'k': 2}


def precompression(level):
    """Average precompression of the level (MPa): the effective force of each tendon set over the slab section across it."""
    ram = level.get('ram') or {}
    tendons = ram.get('tendons') or []
    pt = ram.get('pt') or {}
    if not len(tendons) or not pt.get('strandArea') or not pt.get('fse') or not (level.get('outline') or []):
        return None
    b = bbox(level['outline'])
    h = level.get('thickness') or 0
    vals = []
    for set_ in ['latitude', 'longitude']:
        ts = [t for t in tendons if t.get('spanSet') == set_]
        if not len(ts):
            continue
        # the tendons of a set run one way: the section across them is the slab extent perpendicular to their direction
        dir_ = []
        for t in ts:
            a = t['pts'][0]
            z = t['pts'][-1]
            dir_.append('x' if abs(z['x'] - a['x']) >= abs(z['y'] - a['y']) else 'y')
        along_x = len([v for v in dir_ if v == 'x']) >= len(dir_) / 2
        width = b['h'] if along_x else b['w']  # mm
        F = sum((t.get('strands') or 1) * pt['strandArea'] * pt['fse'] for t in ts)  # N
        if width > 0 and h > 0:
            vals.append(F / (width * h))
    if not len(vals):
        return None
    return sum(vals) / len(vals)


def override_columns(check, override):
    """The columns to draw punching reinforcement at under an engineer's bypass (`override.columns` = 'all' → every flagged column)."""
    if not override or not check:
        return set()
    if override.get('columns') == 'all' or not override.get('columns'):
        return set(check.get('flagged') or [])
    return set(str(v).strip().upper() for v in override['columns'])


def blocking_after(check, decision):
    """Which flagged columns still block the run after the engineer's decision."""
    if not check:
        return []
    blocking = list(dict.fromkeys(check.get('blocking') or []))  # new Set(check.blocking): unique, insertion order kept
    if not decision or decision.get('mode') == 'thicken':
        return list(blocking)
    if decision.get('columns') == 'all' or not decision.get('columns'):
        covered = set(str(v).upper() for v in (check.get('flagged') or []))
    else:
        covered = set(str(v).strip().upper() for v in decision['columns'])
    return [id_ for id_ in blocking if str(id_).upper() not in covered]
