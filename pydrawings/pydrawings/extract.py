"""
Reads the combined structural drawing and pulls out what the rebar sheets
need: slab outlines per level, grid, columns, PT zones, openings, voids and
U-bar regions, plus any design data written in the notes.

Nothing is asked of the user: where the drawing is silent an assumption
is recorded and printed on the sheet.

Port of `shopdrawings/lib/extract.mjs`. The input `dxf` is the dict returned by `dxf_reader.parse_dxf`
(`{'header': {...}, 'blocks': {name: {'name', 'base', 'entities'}}, 'entities': [...]}`); entities are plain dicts
with the JS keys (type, layer, x, y, pts, closed, text, r, name, height, rotation, halign, x2, y2, paths, ...).
"""
import json
import math
import re
from functools import cmp_to_key

from .geometry import (
    bbox, expand_bbox, bbox_contains, clean_polygon, polygon_area, as_axis_rect, point_in_polygon, centroid,
    transform_point, dist, rect_polygon, circle_polygon, js_round, fmt_num,
)
from .rebar import DEFAULT_SPEC

id_ = id  # Python's built-in `id` (object identity): `_build_level` shadows `id` with the level id

# JS `\d` matches ASCII digits only; Python's `\d` also matches other Unicode digits, so `[0-9]` is used throughout.
LAYER_RULES = [
    ['grid', re.compile(r'GRID|AXIS|AXES|\bAXE\b|محور|محاور', re.I | re.A)],
    ['ubar', re.compile(r'U[-_ ]?BARS?|HAIRPIN', re.I)],
    ['void', re.compile(r'VOID|ACU|ACOU|AKWAR|أكوار|اكوار|كور|HOLLOW|COBIAX|BUBBLE', re.I)],
    ['opening', re.compile(r'OPEN|SHAFT|DUCT|فتح|HOLE|SLEEVE', re.I)],
    ['drop', re.compile(r'DROP', re.I)],
    ['pourstrip', re.compile(r'POUR|CLOSURE[-_ ]?STRIP|CONSTRUCTION[-_ ]?JOINT', re.I)],
    ['wall', re.compile(r'WALL|حائط|حوائط|SHEAR', re.I)],
    ['sunken', re.compile(r'SUNK|RECESS|منخفض', re.I)],
    ['stair', re.compile(r'STAIR|سلم|درج', re.I)],
    ['beam', re.compile(r'BEAM|كمر', re.I)],
    ['pt', re.compile(r'(^|[^A-Z])PT([^A-Z]|$)|P-T|TENDON|POST[-_ ]?TEN|كابل|كوابل', re.I)],
    ['column', re.compile(r'COL(?!OR)|COLUMN|عمود|أعمدة|اعمدة', re.I)],
    ['slab', re.compile(r'SLAB|OUTLINE|EDGE|BOUND|حدود|بلاطة|SOG|DECK', re.I)],
    ['notes', re.compile(r'NOTE|TEXT|ANNO|ملاحظ', re.I)],
]


def classify_layer(name):
    for kind, rx in LAYER_RULES:
        if rx.search(name or ''):
            return kind
    return 'other'


def _nz(v):
    """JS reads a missing coordinate as `undefined` (NaN downstream); the port reads it as 0."""
    return v if v is not None else 0


def _centroid(poly):
    """`centroid` of a degenerate polygon returns its bbox in JS (no x / y: NaN downstream, every test false);
    the port returns NaN coordinates so the same comparisons fail the same way."""
    c = centroid(poly)
    if 'x' not in c:
        return {'x': float('nan'), 'y': float('nan')}
    return c


def flatten(dxf):
    """Explode INSERTs so block geometry becomes plain entities in drawing coordinates."""
    out = []
    blocks = dxf.get('blocks') or {}

    def walk(ents, t, depth, block_name, sink):
        for e in ents:
            if e.get('type') == 'INSERT':
                blk = blocks.get(e.get('name'))
                if not blk or depth > 4:
                    continue
                sx = e.get('sx') if e.get('sx') is not None else 1
                sy = e.get('sy') if e.get('sy') is not None else (e.get('sx') if e.get('sx') is not None else 1)
                tt = {'x': e.get('x'), 'y': e.get('y'), 'sx': sx, 'sy': sy, 'rotation': e.get('rotation') or 0}
                shifted = [_shift_entity(be, blk.get('base')) for be in blk.get('entities') or []]
                inner = []
                walk(shifted, None, depth + 1, e.get('name'), inner)
                placed = [transform_entity(ie, tt) for ie in inner]
                outer = [transform_entity(ie, t) for ie in placed] if t else placed
                sink.extend(outer)
                # Record the insert itself as a candidate column / symbol with its exploded bbox.
                pts = [p for ie in outer for p in entity_points(ie)]
                at = transform_point({'x': e.get('x'), 'y': e.get('y')}, t) if t else {'x': e.get('x'), 'y': e.get('y')}
                sink.append({'type': 'INSERT', 'layer': e.get('layer'), 'name': e.get('name'), 'x': at['x'], 'y': at['y'], 'pts': pts, 'blockBbox': bbox(pts) if pts else None})
                for a in e.get('attribs') or []:
                    sink.append(transform_entity(a, t) if t else dict(a))
                continue
            te = transform_entity(e, t) if t else dict(e)
            te['fromBlock'] = block_name or None
            sink.append(te)

    walk(dxf.get('entities') or [], None, 0, None, out)
    return out


def _shift_entity(e, base):
    if not base or (not base.get('x') and not base.get('y')):
        return e
    return transform_entity(e, {'x': -base['x'], 'y': -base['y'], 'sx': 1, 'sy': 1, 'rotation': 0})


def transform_entity(e, t):
    def T(p):
        return transform_point(p, t)
    scale = abs(t.get('sx') or 1)
    c = dict(e)
    p = T({'x': _nz(e.get('x')), 'y': _nz(e.get('y'))})
    c['x'] = p['x']
    c['y'] = p['y']
    if e.get('x2') is not None:
        q = T({'x': e['x2'], 'y': _nz(e.get('y2'))})
        c['x2'] = q['x']
        c['y2'] = q['y']
    if e.get('x3') is not None:
        q = T({'x': e['x3'], 'y': _nz(e.get('y3'))})
        c['x3'] = q['x']
        c['y3'] = q['y']
    if e.get('x4') is not None:
        q = T({'x': e['x4'], 'y': _nz(e.get('y4'))})
        c['x4'] = q['x']
        c['y4'] = q['y']
    if e.get('type') == 'DIMENSION':
        c['measure'] = (e.get('measure') or 0) * scale
        c['rotation'] = (e.get('rotation') or 0) + (t.get('rotation') or 0)
    if e.get('pts'):
        c['pts'] = [{**q, **T(q)} for q in e['pts']]
    if e.get('paths'):
        c['paths'] = [[T(q) for q in path] for path in e['paths']]
    if e.get('r') is not None:
        c['r'] = e['r'] * scale
    if e.get('height') is not None:
        c['height'] = e['height'] * scale
    if e.get('rotation') is not None and e.get('type') == 'TEXT':
        c['rotation'] = (e.get('rotation') or 0) + (t.get('rotation') or 0)
    return c


def entity_points(e):
    t = e.get('type')
    if t == 'LINE':
        return [{'x': e.get('x'), 'y': e.get('y')}, {'x': e.get('x2'), 'y': e.get('y2')}]
    if t in ('LWPOLYLINE', 'SOLID', 'TRACE'):
        return e.get('pts') or []
    if t in ('CIRCLE', 'ARC'):
        return [{'x': e['x'] - e['r'], 'y': e['y'] - e['r']}, {'x': e['x'] + e['r'], 'y': e['y'] + e['r']}]
    if t == 'HATCH':
        return [p for path in (e.get('paths') or []) for p in path]
    if t in ('TEXT', 'MTEXT'):
        return [{'x': e.get('x'), 'y': e.get('y')}]
    if t == 'DIMENSION':
        return ([{'x': e.get('x'), 'y': e.get('y')}]
                + ([{'x': e['x3'], 'y': e.get('y3')}] if e.get('x3') is not None else [])
                + ([{'x': e['x4'], 'y': e.get('y4')}] if e.get('x4') is not None else []))
    return []


def closed_polys(e):
    # Closed polygons carried by an entity (polyline, solid or hatch path).
    t = e.get('type')
    if t == 'LWPOLYLINE':
        src = e.get('pts') or []
        pts = clean_polygon(src)
        closed = e.get('closed') or (len(src) > 3 and dist(src[0], src[-1]) < 50)  # a polyline drawn back to its start (within 50 mm) is a closed outline
        return [pts] if closed and len(pts) >= 3 else []
    if t == 'SOLID' or t == 'TRACE':
        return [clean_polygon(e.get('pts') or [])]
    if t == 'HATCH':
        return [p for p in (clean_polygon(path) for path in (e.get('paths') or [])) if len(p) >= 3]
    return []


def _text_of(e):
    return (e.get('text') or '').strip()


def detect_units(dxf, ents):
    u = (dxf.get('header') or {}).get('$INSUNITS')
    if u == 4:
        return {'scale': 1, 'name': 'mm', 'source': '$INSUNITS'}
    if u == 6:
        return {'scale': 1000, 'name': 'm', 'source': '$INSUNITS'}
    if u == 5:
        return {'scale': 10, 'name': 'cm', 'source': '$INSUNITS'}
    pts = [p for e in ents for p in entity_points(e)]
    if not pts:
        return {'scale': 1, 'name': 'mm', 'source': 'assumed'}
    b = bbox(pts)
    extent = max(b['w'], b['h'])
    if extent < 500:
        return {'scale': 1000, 'name': 'm', 'source': 'inferred from extents'}
    if extent < 5000:
        return {'scale': 10, 'name': 'cm', 'source': 'inferred from extents'}
    return {'scale': 1, 'name': 'mm', 'source': 'inferred from extents'}


def _scale_entity(e, k):
    if k == 1:
        return e
    return transform_entity(e, {'x': 0, 'y': 0, 'sx': k, 'sy': k, 'rotation': 0})


def region_from(e, poly):
    """Region shape from a closed polygon or circle entity."""
    if e.get('type') == 'CIRCLE':
        return {'kind': 'circle', 'cx': e['x'], 'cy': e['y'], 'r': e['r']}
    rect = as_axis_rect(poly, 5)
    if rect:
        return {'kind': 'rect', 'rect': rect}
    # circle drawn as bulged polyline
    b = bbox(poly)
    if len(poly) >= 8 and abs(b['w'] - b['h']) < 0.05 * b['w']:
        c = _centroid(poly)
        rs = [dist(p, c) for p in poly]
        r = sum(rs) / len(rs)
        if all(abs(v - r) < 0.05 * r for v in rs):
            return {'kind': 'circle', 'cx': c['x'], 'cy': c['y'], 'r': r}
    return {'kind': 'polygon', 'polygon': list(reversed(poly)) if polygon_area(poly) < 0 else poly}


def _region_polygon_of(r):
    return circle_polygon(r['cx'], r['cy'], r['r']) if r['kind'] == 'circle' else rect_polygon(r['rect']) if r['kind'] == 'rect' else r['polygon']


def _region_center(r):
    if r['kind'] == 'circle':
        return {'x': r['cx'], 'y': r['cy']}
    if r['kind'] == 'rect':
        return {'x': r['rect']['x'] + r['rect']['w'] / 2, 'y': r['rect']['y'] + r['rect']['h'] / 2}
    return _centroid(r['polygon'])


def _region_area(r):
    if r['kind'] == 'circle':
        return math.pi * r['r'] * r['r']
    if r['kind'] == 'rect':
        return r['rect']['w'] * r['rect']['h']
    return abs(polygon_area(r['polygon']))


def extract_model(dxf, options=None):
    options = options or {}
    assumptions = []
    findings = []
    raw = flatten(dxf)
    units = detect_units(dxf, raw)
    ents = [_scale_entity(e, units['scale']) for e in raw]
    if units['source'] != '$INSUNITS':
        assumptions.append({'text': f"Drawing units not declared; {units['name']} {units['source']}."})
    findings.append(f"Drawing units: {units['name']} ({units['source']}); {len(ents)} entities read.")

    for e in ents:
        e['kind'] = classify_layer(str(e.get('layer') if e.get('layer') is not None else '') + ' ' + (e.get('name') or ''))
        if e['kind'] == 'other' and e.get('fromBlock'):
            e['kind'] = classify_layer(e['fromBlock'])
    texts = [e for e in ents if (e.get('type') == 'TEXT' or e.get('type') == 'MTEXT') and _text_of(e)]

    # ---------------------------------------------------------- slab outlines
    outlines = []
    for e in [x for x in ents if x['kind'] == 'slab']:
        for p in closed_polys(e):
            if abs(polygon_area(p)) > 10e6:
                outlines.append(p)
    if not outlines:
        segs = []
        for e in [x for x in ents if x['kind'] == 'slab']:
            if e.get('type') == 'LINE':
                segs.append([{'x': e['x'], 'y': e['y']}, {'x': e['x2'], 'y': e['y2']}])
            elif e.get('type') == 'LWPOLYLINE' and not e.get('closed') and len(e.get('pts') or []) >= 2:
                for i in range(len(e['pts']) - 1):
                    segs.append([e['pts'][i], e['pts'][i + 1]])
        for loop in chain_segments(segs):
            if abs(polygon_area(loop)) > 10e6:
                outlines.append(loop)
        if outlines:
            findings.append('Slab edge drawn as separate lines: chained into closed outline(s).')
    if not outlines:
        cands = []
        for e in [x for x in ents if x['kind'] != 'grid' and x.get('type') == 'LWPOLYLINE']:
            for p in closed_polys(e):
                if abs(polygon_area(p)) > 20e6:
                    cands.append(p)
        outlines = [p for p in cands if not any(q is not p and abs(polygon_area(q)) > abs(polygon_area(p)) and point_in_polygon(p[0], q) for q in cands)]
        if outlines:
            assumptions.append({'text': 'No slab outline layer found: the largest closed polylines were taken as slab outlines.'})
    if not outlines:
        pts = [p for e in ents if e['kind'] == 'column' for p in entity_points(e)]
        b = bbox(pts if pts else [p for e in ents for p in entity_points(e)])
        outlines = [rect_polygon({'x': b['minX'] - 1000, 'y': b['minY'] - 1000, 'w': b['w'] + 2000, 'h': b['h'] + 2000})]
        assumptions.append({'text': 'No slab outline could be read: a rectangle 1.0 m outside the column extents was assumed as the slab edge.'})
    nested_outlines = [p for p in outlines if any(q is not p and abs(polygon_area(q)) > abs(polygon_area(p)) and point_in_polygon(_centroid(p), q) for q in outlines)]
    outlines = [p for p in outlines if not any(p is n for n in nested_outlines)]
    outlines = [list(reversed(p)) if polygon_area(p) < 0 else p for p in outlines]

    # Plans usually sit side by side left to right, then top to bottom.
    def _order(a, b):
        A, B = bbox(a), bbox(b)
        return B['minY'] - A['minY'] if abs(A['minY'] - B['minY']) > max(A['h'], B['h']) * 0.5 else A['minX'] - B['minX']
    outlines.sort(key=cmp_to_key(_order))

    # ---------------------------------------------------------- global design data
    all_text = '\n'.join(_text_of(t) for t in texts)
    spec = read_spec_from_text(all_text, assumptions, options.get('spec') or {})

    levels = [
        _build_level(outline, i, ents, texts, spec, assumptions, findings,
                     {**options, 'nested': [p for p in nested_outlines if point_in_polygon(_centroid(p), outline)]})
        for i, outline in enumerate(outlines)
    ]
    code_ref = spec.get('code_reference')
    return {
        'source': {'units': units['name'], 'entities': len(ents), 'layers': sorted(dict.fromkeys(e.get('layer') for e in ents))},
        'code_reference': code_ref,
        'spec': spec,
        'levels': levels,
        'assumptions': assumptions,
        'findings': findings,
    }


_CODE_RX = [
    re.compile(r'SBC\s*[- ]?[0-9]{3}(?:[- ]?[0-9]{2,4})?'),
    re.compile(r'ACI\s*[- ]?318(?:[- ]?[0-9]{2})?'),
    re.compile(r'BS\s*[- ]?8110'),
    re.compile(r'EN\s*1992|EUROCODE\s*2|EC\s*2'),
]
_FC_RX = [
    re.compile(r"F['’`]?C\s*[=:]?\s*([0-9]{2})"),
    re.compile(r'C\s?([0-9]{2})/[0-9]{2}'),
    re.compile(r'CONCRETE[^0-9\n]{0,40}([0-9]{2})\s*(?:MPA|N/MM)'),
]
_FY_RX = re.compile(r'F\s*Y\s*[=:]?\s*([0-9]{3})')
_GRADE_RX = re.compile(r'GRADE\s*(60|420|500)')
_COVER_RX = re.compile(r'COVER[^0-9\n]{0,25}([0-9]{2})')
# Bar specs with a context word on the same line.
_BAR_RX = re.compile(r'(?:T|Y|H|N|D|#|Ø|Φ|DIA\.?)?\s*([0-9]{2})\s*@\s*([0-9]{2,3})', re.I)


def read_spec_from_text(text, assumptions, overrides=None):
    spec = json.loads(json.dumps(DEFAULT_SPEC))
    src = {}
    T = text.upper()
    code = None
    for rx in _CODE_RX:
        code = rx.search(T)
        if code:
            break
    if code:
        spec['code_reference'] = re.sub(r'\s+', ' ', code.group(0)).strip()
        src['code'] = 'drawing'
    else:
        spec['code_reference'] = None
        src['code'] = 'assumed'
        assumptions.append({'text': 'Design code not stated on the drawings: SBC 304-18 (Saudi Building Code, based on ACI 318-14) applied for development, anchorage and lap lengths. To be adjusted on receipt of the final design criteria.'})

    m = None
    for rx in _FC_RX:
        m = rx.search(T)
        if m:
            break
    if m:
        spec['fc'] = int(m.group(1))
        src['fc'] = 'drawing'
    else:
        src['fc'] = 'assumed'
        assumptions.append({'text': f"Concrete grade not stated: f'c = {spec['fc']} MPa assumed (conservative for anchorage lengths)."})
    m = _FY_RX.search(T)
    if m:
        spec['fy'] = int(m.group(1))
        src['fy'] = 'drawing'
    else:
        m = _GRADE_RX.search(T)
        if m:
            spec['fy'] = 420 if m.group(1) == '60' else int(m.group(1))
            src['fy'] = 'drawing'
        else:
            src['fy'] = 'assumed'
            assumptions.append({'text': f"Reinforcement grade not stated: fy = {spec['fy']} MPa (Grade 60) assumed."})
    m = _COVER_RX.search(T)
    if m:
        spec['cover'] = int(m.group(1))
        src['cover'] = 'drawing'
    else:
        src['cover'] = 'assumed'
        assumptions.append({'text': f"Concrete cover not stated: {spec['cover']} mm top and bottom assumed for slabs (SBC 304-18 Table 20.6.1.3.1)."})

    # Bar specs with a context word on the same line.
    lines = text.split('\n')
    found = []
    for line in lines:
        U = line.upper()
        for mm in _BAR_RX.finditer(line):
            dia, spacing = int(mm.group(1)), int(mm.group(2))
            if dia < 8 or dia > 40 or spacing < 50 or spacing > 600:
                continue
            target = None
            if re.search(r'BOT|SOFFIT|BOTTOM|B\.?W\.?|MESH', U) and not re.search(r'TOP', U):
                target = 'bottom'
            elif re.search(r'TOP|OVER\s*COL|COLUMN|SUPPORT', U):
                target = 'topColumns'
            elif re.search(r'U[- ]?BAR|HAIRPIN', U):
                target = 'uEdge'
            elif re.search(r'OPEN', U):
                target = 'openings'
            elif re.search(r'VOID', U):
                target = 'voids'
            if not target:
                continue
            spec[target] = {**(spec.get(target) or {}), 'dia': dia, 'spacing': spacing}
            found.append(f'{target}: T{dia}@{spacing} from note "{line.strip()[:60]}"')
    if not any(f.startswith('bottom') for f in found):
        assumptions.append({'text': f"Bottom mesh not specified: T{spec['bottom']['dia']}@{spec['bottom']['spacing']} both ways assumed as bonded reinforcement in PT zones."})
    if not any(f.startswith('topColumns') for f in found):
        assumptions.append({'text': f"Top bars over columns not specified: T{spec['topColumns']['dia']}@{spec['topColumns']['spacing']} both ways assumed within c + 3h, checked against As,min = 0.00075·Acf (SBC 304-18 §8.6.2.3)."})
    if not any(f.startswith('uEdge') for f in found):
        assumptions.append({'text': f"Edge U-bars not specified: T{spec['uEdge']['dia']}@{spec['uEdge']['spacing']} with {spec['uEdge']['leg']} mm legs assumed at PT anchorage edges."})
    if not any(f.startswith('openings') for f in found):
        assumptions.append({'text': f"Opening trimmers not specified: {spec['openings']['count']}T{spec['openings']['dia']} T&B each side + {spec['openings']['diagCount']}T{spec['openings']['diagDia']} diagonals at corners assumed."})
    if not any(f.startswith('voids') for f in found):
        assumptions.append({'text': f"Void trimmers not specified: {spec['voids']['count']}T{spec['voids']['dia']} T&B each side assumed."})
    assumptions.append({'text': f"Stock bar length {fmt_num(spec['stock'] / 1000)} m; laps staggered so that not more than 50 % of bars lap at one section."})
    spec.update(overrides or {})
    spec['sources'] = src
    spec['found'] = found
    return spec


_TITLE_RX = re.compile(r'FLOOR|ROOF|LEVEL|SLAB|PLAN|BASEMENT|GROUND|PODIUM|MEZZ|TYPICAL|بلاطة|دور|سقف|أرضي|ارضي|قبو|بدروم', re.I)
_THK_RX = re.compile(r'(?:SLAB\s*)?(?:THK|THICK(?:NESS)?|TH\s*=|T\s*=|H\s*=)\s*[:=]?\s*([0-9]{3})|([0-9]{3})\s*(?:MM)?\s*(?:THK|THICK)|PT\s*SLAB\s*([0-9]{3})', re.I)
_THK_SKIP_RX = re.compile(r'SUNK|DROP|BEAM|WALL|RECESS|COL', re.I)
_THK_WEIGHT_RX = re.compile(r'PT|SLAB', re.I)
_TAG_RX = re.compile(r'T\.?O\.?[SC]\b|TOS|TOC|LEVEL|LVL|S\.?S\.?L', re.I | re.A)
_NUMBER_RX = re.compile(r'[+-]?[0-9]+(\.[0-9]+)?')
_VOID_WORDS_RX = re.compile(r'VOID|ACU|AKWAR|كور|HOLLOW')
_SUNKEN_TH_RX = re.compile(r'TH\s*=?\s*([0-9]{3})')


def _build_level(outline, index, ents, texts, spec, assumptions, findings, options=None):
    options = options or {}
    id = f'L{index + 1:02d}'
    ob = bbox(outline)
    region = expand_bbox(ob, max(ob['w'], ob['h']) * 0.25)

    def in_region(p):
        return bbox_contains(region, p)

    def near(p, d=500):
        return (point_in_polygon(p, outline) or point_in_polygon({'x': p['x'] + d, 'y': p['y']}, outline)
                or point_in_polygon({'x': p['x'] - d, 'y': p['y']}, outline) or point_in_polygon({'x': p['x'], 'y': p['y'] + d}, outline)
                or point_in_polygon({'x': p['x'], 'y': p['y'] - d}, outline))

    level_texts = [t for t in texts if in_region({'x': t['x'], 'y': t['y']})]
    level_text_ids = set(id_(t) for t in level_texts)
    A = {'level': id}

    # ------------------------------------------------------------ name
    heights = sorted((t.get('height') or 0) for t in level_texts)
    median = (heights[len(heights) // 2] if heights else 0) or 250
    name = None
    titles = [t for t in level_texts if _TITLE_RX.search(t['text']) and ((t.get('height') or 0) >= median * 1.5 or t['y'] < ob['minY'])]
    titles.sort(key=lambda t: -(t.get('height') or 0))
    if titles:
        name = re.sub(r'\s+', ' ', titles[0]['text']).strip()
    level_names = options.get('levelNames')
    if not name and level_names and index < len(level_names) and level_names[index]:
        name = level_names[index]
    if not name:
        name = f'LEVEL {index + 1}'
        assumptions.append({**A, 'text': f'No plan title found near slab {index + 1}: named "{name}".'})

    # ------------------------------------------------------------ thickness
    thickness = None
    thk_votes = {}
    for t in level_texts + texts:
        if _THK_SKIP_RX.search(t['text']):
            continue
        m = _THK_RX.search(re.sub(r'\s+', ' ', t['text']))
        if not m:
            continue
        v = int(m.group(1) or m.group(2) or m.group(3))
        if v < 100 or v > 800:
            continue
        w = (10 if id_(t) in level_text_ids else 1) * (3 if _THK_WEIGHT_RX.search(t['text']) else 1)
        thk_votes[v] = (thk_votes.get(v) or 0) + w
    if thk_votes:
        thickness = sorted(thk_votes.items(), key=lambda kv: -kv[1])[0][0]
    if not thickness:
        thickness = 250
        assumptions.append({**A, 'text': f'Slab thickness not stated for {name}: {thickness} mm assumed.'})

    # ------------------------------------------------------------ grid
    grid_lines = [e for e in ents if e['kind'] == 'grid' and (e.get('type') == 'LINE' or (e.get('type') == 'LWPOLYLINE' and len(e.get('pts') or []) == 2))]
    gx, gy = [], []

    def label_for(p):
        best = None
        for t in texts:
            s = t['text'].strip()
            if len(s) > 3 or re.search(r'\s', s):
                continue
            d = dist({'x': t['x'], 'y': t['y']}, p)
            if d < 3000 and (not best or d < best['d']):
                best = {'d': d, 's': s}
        return best['s'] if best else None

    for g in grid_lines:
        a = {'x': g['x'], 'y': g['y']} if g.get('type') == 'LINE' else g['pts'][0]
        b = {'x': g['x2'], 'y': g['y2']} if g.get('type') == 'LINE' else g['pts'][1]
        ln = dist(a, b)
        if ln < 1000:
            continue
        touches = ((a['x'] >= region['minX'] and a['x'] <= region['maxX'] and ((a['y'] <= region['maxY'] and b['y'] >= region['minY']) or (b['y'] <= region['maxY'] and a['y'] >= region['minY'])))
                   or (a['y'] >= region['minY'] and a['y'] <= region['maxY'] and ((a['x'] <= region['maxX'] and b['x'] >= region['minX']) or (b['x'] <= region['maxX'] and a['x'] >= region['minX']))))
        if not touches:
            continue
        label = label_for(a) or label_for(b)
        if abs(a['x'] - b['x']) < 0.02 * ln:
            gx.append({'label': label, 'x': (a['x'] + b['x']) / 2, 'y1': min(a['y'], b['y']), 'y2': max(a['y'], b['y'])})
        elif abs(a['y'] - b['y']) < 0.02 * ln:
            gy.append({'label': label, 'y': (a['y'] + b['y']) / 2, 'x1': min(a['x'], b['x']), 'x2': max(a['x'], b['x'])})

    def dedupe(arr, key):
        out = []
        arr.sort(key=lambda p: p[key])
        for g in arr:
            last = out[-1] if out else None
            if last and abs(last[key] - g[key]) < 100:
                if not last.get('label') and g.get('label'):
                    last['label'] = g['label']
                continue
            out.append(g)
        return out

    grid = {'x': dedupe(gx, 'x'), 'y': dedupe(gy, 'y'), 'source': 'drawing'}

    # ------------------------------------------------------------ columns
    columns = []

    def push_column(c):
        if not near({'x': c['cx'], 'y': c['cy']}, 300):
            return
        if any(dist({'x': o['cx'], 'y': o['cy']}, {'x': c['cx'], 'y': c['cy']}) < 150 for o in columns):
            return
        columns.append(c)

    for e in [x for x in ents if x['kind'] == 'column']:
        if e.get('type') == 'CIRCLE' and (e.get('r') or 0) > 100 and (e.get('r') or 0) < 1500:
            push_column({'shape': 'circle', 'cx': e['x'], 'cy': e['y'], 'd': 2 * e['r'], 'w': 2 * e['r'], 'h': 2 * e['r']})
            continue
        if e.get('type') == 'INSERT' and e.get('blockBbox'):
            b = e['blockBbox']
            if b['w'] > 150 and b['w'] < 3000 and b['h'] > 150 and b['h'] < 3000:
                push_column({'shape': 'rect', 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h']})
            continue
        for p in closed_polys(e):
            b = bbox(p)
            if b['w'] < 150 or b['h'] < 150 or b['w'] > 3000 or b['h'] > 3000:
                continue
            push_column({'shape': 'rect', 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h']})
    if not columns:
        for e in [x for x in ents if x.get('type') == 'LWPOLYLINE' and x['kind'] != 'grid' and x['kind'] != 'slab']:
            for p in closed_polys(e):
                b = bbox(p)
                if b['w'] < 200 or b['h'] < 200 or b['w'] > 1500 or b['h'] > 1500 or b['w'] / b['h'] > 4 or b['h'] / b['w'] > 4:
                    continue
                if not point_in_polygon({'x': b['cx'], 'y': b['cy']}, outline):
                    continue
                push_column({'shape': 'rect', 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h']})
        if columns:
            assumptions.append({**A, 'text': 'No column layer found: small closed rectangles inside the slab were taken as columns.'})
    if not grid['x'] or not grid['y']:
        # Derive a grid from column lines.
        def cluster(vals):
            out = []
            for v in sorted(vals):
                l = out[-1] if out else None
                if l and abs(l['v'] - v) < 600:
                    l['n'] += 1
                    l['v'] = (l['v'] * (l['n'] - 1) + v) / l['n']
                else:
                    out.append({'v': v, 'n': 1})
            return [c['v'] for c in out]
        if not grid['x']:
            grid['x'] = [{'label': None, 'x': x, 'y1': ob['minY'], 'y2': ob['maxY']} for x in cluster([c['cx'] for c in columns])]
        if not grid['y']:
            grid['y'] = [{'label': None, 'y': y, 'x1': ob['minX'], 'x2': ob['maxX']} for y in cluster([c['cy'] for c in columns])]
        grid['source'] = 'derived from column positions'
        assumptions.append({**A, 'text': f'Grid lines not found for {name}: grid derived from column positions.'})
    letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
    for i, g in enumerate(grid['x']):
        if not g.get('label'):
            g['label'] = letters[i % len(letters)]
        if g.get('y1') is None:
            g['y1'] = ob['minY']
            g['y2'] = ob['maxY']
    for i, g in enumerate(grid['y']):
        if not g.get('label'):
            g['label'] = str(i + 1)
        if g.get('x1') is None:
            g['x1'] = ob['minX']
            g['x2'] = ob['maxX']
    for i, c in enumerate(columns):
        gxn = _nearest(grid['x'], 'x', c['cx'])
        gyn = _nearest(grid['y'], 'y', c['cy'])
        c['id'] = f"{gxn['label']}/{gyn['label']}" if gxn and gyn and abs(gxn['x'] - c['cx']) < 600 and abs(gyn['y'] - c['cy']) < 600 else f'C{i + 1}'
    columns.sort(key=lambda c: (-c['cy'], c['cx']))

    # ------------------------------------------------------------ openings / voids / u-bar / pt
    openings, voids, ubar_circles, pt_zones, tendons = [], [], [], [], []
    sunken, beams, stairs = [], [], []
    walls, thick_zones, pour_strips = [], [], []
    ubar_edges = []
    # level tags (T.O.S +0.60 style block attributes): the value written nearest a "T.O.S" attribute
    level_tags = []
    attribs = [e for e in ents if e.get('type') == 'ATTRIB' and e.get('text')]
    for t in [a for a in attribs if _TAG_RX.search(a['text'])]:
        vs = [a for a in attribs if a is not t and _NUMBER_RX.fullmatch(a['text'].strip())]
        vs.sort(key=lambda a: dist(a, t))
        v = vs[0] if vs else None
        if v and dist(v, t) < 1500 and near({'x': v['x'], 'y': v['y']}):
            level_tags.append({'x': v['x'], 'y': v['y'], 'label': t['text'].strip().upper(), 'value': v['text'].strip()})
    # the same tag written as plain text ("T.O.C" over "+0.40", the office plans and the zone files)
    for t in [x for x in level_texts if re.fullmatch(r'T\.?O\.?[SC]\.?', _text_of(x), re.I | re.A)]:
        vs = [u for u in level_texts if u is not t and re.fullmatch(r'[+-]?[0-9]+(\.[0-9]+)?', _text_of(u), re.A) and dist(u, t) < 1200]
        vs.sort(key=lambda u: dist(u, t))
        v = vs[0] if vs else None
        if v and near({'x': v['x'], 'y': v['y']}) and not any(dist(g, v) < 10 for g in level_tags):
            level_tags.append({'x': v['x'], 'y': v['y'], 'label': _text_of(t).upper(), 'value': _text_of(v)})
    for e in ents:
        if e['kind'] == 'wall':
            for p in closed_polys(e):
                b = bbox(p)
                if min(b['w'], b['h']) < 120 or min(b['w'], b['h']) > 1200 or not near({'x': b['cx'], 'y': b['cy']}, 800):
                    continue
                along = 'x' if b['w'] >= b['h'] else 'y'
                a = {'x': b['minX'], 'y': b['cy']} if along == 'x' else {'x': b['cx'], 'y': b['minY']}
                bb = {'x': b['maxX'], 'y': b['cy']} if along == 'x' else {'x': b['cx'], 'y': b['maxY']}
                walls.append({'polygon': p, 'a': a, 'b': bb, 'cx': b['cx'], 'cy': b['cy'], 'w': b['w'], 'h': b['h'], 't': min(b['w'], b['h']), 'length': max(b['w'], b['h'])})
            continue
        if e['kind'] == 'drop':
            for p in closed_polys(e):
                b = bbox(p)
                if not near({'x': b['cx'], 'y': b['cy']}) or abs(polygon_area(p)) < 0.5e6:
                    continue
                if any(dist(_centroid(z['polygon']), {'x': b['cx'], 'y': b['cy']}) < 100 for z in thick_zones):
                    continue
                # the drop's depth written inside it ("550"), when the plan gives it
                tin = next((t for t in texts if re.fullmatch(r'[0-9]{3}', _text_of(t), re.A) and point_in_polygon(t, p)), None)
                thick_zones.append({'polygon': list(reversed(p)) if polygon_area(p) < 0 else p, 'thickness': int(_text_of(tin)) if tin else None, 'kind': 'drop'})
            continue
        if e['kind'] == 'pourstrip':
            for p in closed_polys(e):
                b = bbox(p)
                if not near({'x': b['cx'], 'y': b['cy']}):
                    continue
                pour_strips.append({'polygon': list(reversed(p)) if polygon_area(p) < 0 else p, 'width': min(b['w'], b['h']), 'length': max(b['w'], b['h'])})
            continue

    def text_near(p, r=1500):
        return ' '.join(_text_of(t) for t in texts if dist({'x': t['x'], 'y': t['y']}, p) < r).upper()

    def is_column_shape(rg):
        return any(dist(_region_center(rg), {'x': c['cx'], 'y': c['cy']}) < 150 for c in columns)

    for e in ents:
        if e['kind'] == 'beam':
            if e.get('type') == 'LINE':
                if near({'x': e['x'], 'y': e['y']}, 800) or near({'x': e['x2'], 'y': e['y2']}, 800):
                    beams.append({'a': {'x': e['x'], 'y': e['y']}, 'b': {'x': e['x2'], 'y': e['y2']}})
            elif e.get('type') == 'LWPOLYLINE':
                pts = e.get('pts') or []
                for i in range(len(pts) - 1):
                    if near(pts[i], 800):
                        beams.append({'a': pts[i], 'b': pts[i + 1]})
            continue
        if e['kind'] == 'stair':
            if e.get('type') == 'LWPOLYLINE' and len(e.get('pts') or []) > 1 and near(e['pts'][0], 800):
                stairs.append({'pts': e['pts'], 'closed': e.get('closed')})
            elif e.get('type') == 'LINE' and near({'x': e['x'], 'y': e['y']}, 800):
                stairs.append({'pts': [{'x': e['x'], 'y': e['y']}, {'x': e['x2'], 'y': e['y2']}]})
            continue
        if e['kind'] == 'sunken':
            for p in closed_polys(e):
                rg = region_from(e, p)
                c = _region_center(rg)
                if not near(c) or _region_area(rg) < 0.2e6:
                    continue
                if not any(dist(_region_center(o), c) < 100 for o in sunken):
                    sunken.append(rg)
            continue
        if e['kind'] not in ('void', 'opening', 'ubar', 'pt'):
            continue
        if e.get('type') == 'CIRCLE':
            rg = {'kind': 'circle', 'cx': e['x'], 'cy': e['y'], 'r': e['r']}
            if not near({'x': e['x'], 'y': e['y']}):
                continue
            if e['kind'] == 'ubar':
                ubar_circles.append(rg)
            elif e['kind'] == 'opening':
                openings.append(rg)
                ubar_circles.append({**rg, 'fromOpening': True})
            elif e['kind'] == 'void':
                voids.append(rg)
            continue
        if e['kind'] == 'pt' and (e.get('type') == 'LINE' or (e.get('type') == 'LWPOLYLINE' and not e.get('closed'))):
            pts = [{'x': e['x'], 'y': e['y']}, {'x': e['x2'], 'y': e['y2']}] if e.get('type') == 'LINE' else (e.get('pts') or [])
            if any(point_in_polygon(p, outline) for p in pts):
                tendons.append({'pts': pts})
            continue
        if e['kind'] == 'ubar' and (e.get('type') == 'LINE' or (e.get('type') == 'LWPOLYLINE' and not e.get('closed'))):
            pts = [{'x': e['x'], 'y': e['y']}, {'x': e['x2'], 'y': e['y2']}] if e.get('type') == 'LINE' else (e.get('pts') or [])
            for i in range(len(pts) - 1):
                if near(pts[i], 300) and near(pts[i + 1], 300):
                    ubar_edges.append({'a': pts[i], 'b': pts[i + 1]})
            continue
        for p in closed_polys(e):
            rg = region_from(e, p)
            c = _region_center(rg)
            if not near(c):
                continue
            if is_column_shape(rg):
                continue
            if e['kind'] == 'pt':
                if _region_area(rg) > 1e6:
                    pt_zones.append(rg)
                continue
            if e['kind'] == 'ubar':
                if rg['kind'] == 'circle':
                    ubar_circles.append(rg)
                continue
            kind = voids if e['kind'] == 'void' else openings
            if not any(dist(_region_center(o), c) < 100 for o in kind):
                kind.append(rg)
    for kind, lst in [['opening', openings], ['void', voids], ['sunken', sunken]]:
        # Openings drawn as a rectangle with a cross: each diagonal's bbox is the opening.
        diag = []
        segs = []

        def add(a, b):
            if not near(a, 300) and not near(b, 300):
                return
            if abs(a['x'] - b['x']) > 1 and abs(a['y'] - b['y']) > 1:
                diag.append(bbox([a, b]))
            else:
                segs.append([a, b])

        for e in [x for x in ents if x['kind'] == kind]:
            if e.get('type') == 'LINE':
                add({'x': e['x'], 'y': e['y']}, {'x': e['x2'], 'y': e['y2']})
            elif e.get('type') == 'LWPOLYLINE' and not e.get('closed'):
                pts = e.get('pts') or []
                for i in range(len(pts) - 1):
                    add(pts[i], pts[i + 1])
        found = []
        for b in diag:
            if b['w'] < 150 or b['h'] < 150 or b['w'] * b['h'] > 60e6:
                continue
            rg = {'kind': 'rect', 'rect': {'x': b['minX'], 'y': b['minY'], 'w': b['w'], 'h': b['h']}}
            if is_column_shape(rg):
                continue
            if not any(dist(_region_center(o), _region_center(rg)) < 50 for o in found):
                found.append(rg)
        if not found:
            for loop in chain_segments(segs):
                rg = region_from({'type': 'LWPOLYLINE'}, loop)
                if _region_area(rg) < 0.05e6 or _region_area(rg) > 60e6 or is_column_shape(rg):
                    continue
                found.append(rg)
        for rg in found:
            if not any(dist(_region_center(o), _region_center(rg)) < 100 for o in lst):
                lst.append(rg)

    # Drop duplicates (a hatch boundary on top of an outline, or a region inside another of the same kind).
    def dedupe_regions(lst):
        out = []
        for rg in lst:
            c = _region_center(rg)
            if any(point_in_polygon(c, _region_polygon_of(o)) and abs(_region_area(o) - _region_area(rg)) < 0.5 * max(_region_area(o), _region_area(rg)) for o in out):
                continue
            out.append(rg)
        return out

    openings[:] = dedupe_regions(openings)
    voids[:] = dedupe_regions(voids)
    sunken[:] = dedupe_regions(sunken)
    if not openings and not voids:
        # Heuristic: closed shapes inside the slab that are on no recognisable layer.
        for e in [x for x in ents if x.get('type') == 'LWPOLYLINE' and x['kind'] == 'other']:
            for p in closed_polys(e):
                rg = region_from(e, p)
                area = _region_area(rg)
                if area < 0.05e6 or area > 60e6:
                    continue
                c = _region_center(rg)
                if not point_in_polygon(c, outline) or is_column_shape(rg):
                    continue
                words = text_near(c)
                if _VOID_WORDS_RX.search(words):
                    voids.append(rg)
                else:
                    openings.append(rg)
                    assumptions.append({**A, 'text': f"Closed shape at ({js_round(c['x'])}, {js_round(c['y'])}) inside {name} has no layer or label: treated as an opening."})
    # nested slab outlines drawn on the slab layer: zones at another level (steps) when their level tag differs
    nested = options.get('nested') or []

    def tag_in(poly):
        return [t for t in level_tags if point_in_polygon(t, poly)]

    def _main_tag():
        inside = [t for t in level_tags if not any(point_in_polygon(t, p) for p in nested)]
        c = {}
        for t in inside:
            c[t['value']] = (c.get(t['value']) or 0) + 1
        ranked = sorted(c.items(), key=lambda kv: -kv[1])
        return (ranked[0][0] if ranked else None) or None
    main_tag = _main_tag()
    for p in nested:
        poly = list(reversed(p)) if polygon_area(p) < 0 else p
        tags = tag_in(poly)
        tag = tags[0] if tags else None
        step = js_round((float(tag['value']) - float(main_tag)) * 1000) if tag and main_tag else None
        if tag and step is not None and step != 0:
            sunken.append({'kind': 'polygon', 'polygon': poly, 'tos': tag['value'], 'step': step, 'thickness': None, 'fromOutline': True})
        elif not tag:
            sunken.append({'kind': 'polygon', 'polygon': poly, 'thickness': None, 'fromOutline': True})
            assumptions.append({**A, 'text': f'Slab zone inside {name} drawn as a separate outline with no level tag: treated as a stepped (sunken / raised) zone.'})
    for i, o in enumerate(openings):
        o['id'] = f'O{i + 1}'
    for i, o in enumerate(sunken):
        o['id'] = f'S{i + 1}'
        words = text_near(_region_center(o), 2500)
        m = _SUNKEN_TH_RX.search(words)
        o['thickness'] = int(m.group(1)) if m else None
    for i, v in enumerate(voids):
        v['id'] = f'V{i + 1}'
    for i, u in enumerate(ubar_circles):
        u['id'] = f'R{i + 1}'
    for i, z in enumerate(pt_zones):
        z['id'] = f'PT{i + 1}'
        z['polygon'] = z.get('polygon') or (rect_polygon(z['rect']) if z['kind'] == 'rect' else circle_polygon(z['cx'], z['cy'], z['r']))
    for i, w in enumerate(walls):
        w['id'] = f'W{i + 1}'
    for i, z in enumerate(thick_zones):
        z['id'] = f'D{i + 1}'
    for i, z in enumerate(pour_strips):
        z['id'] = f'PS{i + 1}'
    if any(z.get('thickness') is None for z in thick_zones):
        assumptions.append({**A, 'text': f"{len([z for z in thick_zones if z.get('thickness') is None])} drop panels read from the drawing; their depth is not stated: to be taken from the structural drawings (top bars over the columns are detailed for the slab thickness)."})
    if pour_strips:
        assumptions.append({**A, 'text': f"{len(pour_strips)} pour strips read from the drawing: the mesh runs through the strip and laps inside it (Class B); the strip is cast after stressing per the PT designer's sequence."})
    if walls:
        findings.append(f"{id} {name}: {len(walls)} walls below ({js_round(sum(w['length'] for w in walls) / 1000)} m), {len(thick_zones)} drop panels, {len(pour_strips)} pour strips, {len(level_tags)} level tags{f' (main T.O.S {main_tag})' if main_tag else ''}.")

    findings.append(f"{id} {name}: {len(columns)} columns, grid {'-'.join(str(g['label']) for g in grid['x'])} / {'-'.join(str(g['label']) for g in grid['y'])}, {len(openings)} openings, {len(voids)} voids, {len(sunken)} sunken slabs, {len(beams)} beam lines, {len(ubar_circles)} circular U-bar regions, {len(pt_zones)} PT zones, {len(tendons)} tendon lines, slab {thickness} mm.")

    return {
        'id': id, 'name': name, 'thickness': thickness, 'outline': outline, 'bbox': ob, 'grid': grid, 'columns': columns,
        'openings': openings, 'voids': voids, 'sunken': sunken, 'beams': beams, 'stairs': stairs, 'walls': walls,
        'thickZones': thick_zones, 'pourStrips': pour_strips, 'levelTags': level_tags, 'tos': main_tag,
        'ubar': {'edges': ubar_edges if ubar_edges else 'all', 'circles': ubar_circles},
        'pt': {'zones': pt_zones, 'tendons': tendons},
    }


def _nearest(arr, k, v):
    """`arr.reduce((b, g) => (Math.abs(g[k] - v) < Math.abs((b ? b[k] : Infinity) - v) ? g : b), null)`."""
    b = None
    for g in arr:
        if abs(g[k] - v) < abs((b[k] if b else math.inf) - v):
            b = g
    return b



def chain_segments(segs, tol=5):
    """Join line segments end-to-end (within tol) into closed loops."""
    used = [False] * len(segs)
    loops = []

    def same(a, b):
        return abs(a['x'] - b['x']) <= tol and abs(a['y'] - b['y']) <= tol

    for i in range(len(segs)):
        if used[i]:
            continue
        used[i] = True
        loop = [segs[i][0], segs[i][1]]
        guard = 0
        while True:
            guard += 1
            if not (guard - 1 < len(segs) + 1):  # `while (guard++ < segs.length + 1)`
                break
            tail = loop[-1]
            if len(loop) > 2 and same(tail, loop[0]):
                loop.pop()
                break
            found, flip = -1, False
            for j in range(len(segs)):
                if used[j]:
                    continue
                if same(segs[j][0], tail):
                    found, flip = j, False
                    break
                if same(segs[j][1], tail):
                    found, flip = j, True
                    break
            if found < 0:
                break
            used[found] = True
            loop.append(segs[found][0] if flip else segs[found][1])
        if len(loop) >= 3 and same(loop[-1], loop[0]):
            loop.pop()
        if len(loop) >= 3:
            loops.append(clean_polygon(loop))
    return loops
