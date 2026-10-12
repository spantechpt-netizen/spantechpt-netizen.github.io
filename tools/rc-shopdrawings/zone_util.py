"""Shared by the per-zone generators: zones, the footing labels of the final plan, which footing TYPE stands at a
point (isolated footing mark of the final plan, or the CF / raft TYPE of mats.json), the zone of a point."""
import json, os, re, pickle, math
from shapely.geometry import Polygon, Point

PRJ = json.load(open('project.json'))
SRC = PRJ['fnd_final']; DX, DY = SRC['shift']
_Z = json.load(open(SRC.get('zones', 'zones.json')))
REST = _Z.pop('_rest', None)
ZP = {k: Polygon(v) for k, v in _Z.items()}
NAMES = sorted(list(ZP) + ([REST] if REST else []), key=lambda s: int(re.sub(r'\D', '', s) or 0))
CODES = PRJ.get('zone_codes') or {n: f"Z{int(re.sub(r'[^0-9]', '', n) or 0):02d}" for n in NAMES}


def zone_of(x, y):
    for k, g in ZP.items():
        if g.contains(Point(x, y)): return k
    return REST


def zone_share(geom):
    """{zone: length or area share} of a line / polygon (working coordinates)."""
    out = {}; tot = geom.length if geom.geom_type.endswith('LineString') else geom.area
    rest = geom
    for k, g in ZP.items():
        part = geom.intersection(g); v = part.length if geom.geom_type.endswith('LineString') else part.area
        if v > 0: out[k] = v / tot
        rest = rest.difference(g)
    v = rest.length if geom.geom_type.endswith('LineString') else rest.area
    if v > 1e-6 * tot and REST: out[REST] = out.get(REST, 0) + v / tot
    return out


def final_labels():
    cache = 'final_labels.pkl'
    if os.path.exists(cache): return pickle.load(open(cache, 'rb'))
    from ezdxf import recover
    doc, _ = recover.readfile(SRC['dxf']); labs = []
    for e in doc.modelspace():
        if e.dxftype() == 'TEXT' and re.match(r'^(F\d+[A-Z]?|Fx|F)$', e.dxf.text.strip()) and e.dxf.layer.upper().endswith('IDEN'):
            labs.append((e.dxf.text.strip(), e.dxf.insert.x + DX, e.dxf.insert.y + DY))
    pickle.dump(labs, open(cache, 'wb')); return labs


FT = json.load(open('footings.json')); MT = json.load(open('mats.json'))
EXT = json.load(open('footings_ext.json')) if os.path.exists('footings_ext.json') else {}
MP = pickle.load(open('mats.pkl', 'rb'))
LABS = final_labels()
_ELS = None


def els():
    global _ELS
    if _ELS is None:
        import gen_cd
        _ELS = gen_cd.build()
    return _ELS


def mat_type_of(m):
    """mats.pkl record -> its type name in mats.json (by the label position)."""
    for n, f in MT.items():
        for x, y in f.get('at') or []:
            if abs(x - m['lx']) < 1 and abs(y - m['ly']) < 1: return n
    return None


def footing_at(x, y):
    """type of the footing under a point: ('mat', name, polygon) / ('iso', mark, polygon) / (None, None, None)."""
    p = Point(x, y)
    for m in MP:
        if m['poly'].buffer(10).contains(p):
            return 'mat', mat_type_of(m), m['poly']
    E, _ = els()
    for e in E:
        if e['kind'] == 'F' and e['rc'].buffer(10).contains(p):
            inside = [s for s, lx, ly in LABS if e['rc'].buffer(300).contains(Point(lx, ly))]
            if inside: return 'iso', inside[0], e['rc']
    return None, None, None


def lib():
    L = dict(EXT); L.update(FT); L.update(MT); return L


def base_meta(zn, prefix, scale='AS SHOWN', extra_note=''):
    from gen import project_notes
    m = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
             rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale=scale, prefix=prefix)
    m.update(PRJ.get('meta', {})); m['area'] = CODES[zn]; m['scale'] = scale
    m['notes'] = project_notes(extra_note, f'{zn}: QUANTITIES OF THIS ZONE ONLY.') if extra_note else project_notes(f'{zn}: QUANTITIES OF THIS ZONE ONLY.')
    return m
