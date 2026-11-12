"""Combined footings / rafts from a foundation plan whose outlines may be in PIECES (open polylines, lines, closed
rings, duplicates): all line work on the foundation layers is noded and polygonized, every CF / RAFT label takes the
smallest face that contains it (= its real outline, any shape). -> mats.pkl (same records as mats_scan.py)

project.json:
  fnd_final: {"dxf": "final.dxf", "shift": [dx, dy]}   the plan to read and the shift to the working coordinates
  fnd_layers: ["CORE-FNDN", ...]                       foundation layers (suffix match)
usage: python3 mats_scan2.py"""
import json, pickle, re, collections
from ezdxf import recover
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union, polygonize
from shapely import affinity

P = json.load(open('project.json'))
SRC = P.get('fnd_final', {})
doc, _ = recover.readfile(SRC.get('dxf', P.get('dxf', 'main.dxf'))); msp = doc.modelspace()
DX, DY = SRC.get('shift', [0, 0])
FNDL = tuple(P.get('fnd_layers', ['CORE-FNDN']))
lines, texts, rbars, dims = [], [], [], []

def walk(e, d=0, inh=None):
    t = e.dxftype()
    if inh and e.dxf.layer == '0': e.dxf.layer = inh
    U = e.dxf.layer.upper()
    if 'RBAR' in U and not U.endswith(('-SY', '-TX', 'TXT')) and t in ('LWPOLYLINE', 'LINE'):
        p = [(a, b) for a, b in e.get_points('xy')] if t == 'LWPOLYLINE' else [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        if len(p) == 2: rbars.append((p, U))                  # an additional bar as drawn: true length and place
    if t == 'DIMENSION':
        try: dims.append(((e.dxf.defpoint2.x, e.dxf.defpoint2.y), (e.dxf.defpoint3.x, e.dxf.defpoint3.y)))
        except Exception: pass
    if t == 'INSERT' and d < 4:
        try:
            for v in e.virtual_entities(): walk(v, d + 1, e.dxf.layer)
        except Exception: pass
    elif t == 'LWPOLYLINE' and e.dxf.layer.endswith(FNDL):
        p = [(a, b) for a, b in e.get_points('xy')]
        if e.closed: p = p + [p[0]]
        if len(p) >= 2: lines.append(LineString(p))
    elif t == 'LINE' and e.dxf.layer.endswith(FNDL):
        lines.append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
    elif t in ('TEXT', 'MTEXT'):
        s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        texts.append((s, e.dxf.insert.x, e.dxf.insert.y, getattr(e.dxf, 'rotation', 0) or 0, e.dxf.layer))
for e in msp: walk(e)
net = unary_union([l for l in lines if l.length > 1])
faces = [f for f in polygonize(net) if f.area > 1e6]
print(len(lines), 'pieces ->', len(faces), 'faces')
LAB = re.compile(r'^(CF\d+[A-Z]?(-[A-Z])?|RAFT-?\d+[A-Z]?(-[A-Z])?)$')
mats = []
for s, x, y, r, lay in texts:
    if not LAB.match(s): continue
    cont = [f for f in faces if f.buffer(50).contains(Point(x, y)) and f.area > 6e6]
    if not cont: continue
    f = min(cont, key=lambda g: g.area)
    # the label may sit in a small closed piece INSIDE the mat (column / pit ring): take the face that is a mat
    mats.append(dict(lab=s, poly=f, lx=x, ly=y))
out = []
for m in mats:
    if not any(m['lab'] == o['lab'] and m['poly'].equals(o['poly']) for o in out): out.append(m)
# faces holding two different labels = two mats drawn as one ring? report
adds = [t for t in texts if re.match(r'^T\s*\d+\s*@\s*\d+', t[0].upper())]
Ls = [t for t in texts if re.match(r'^L\s*=\s*\d+', t[0].replace(' ', ''))]
import math
def add_zones(pg):
    """Additional bars of one mat from the DRAWN bar + its distribution dimension (never from the text position:
    the consultant writes the text about 1 m off the zone). -> list of dict(d, s, layer, along, L, a0, a1, z0, z1, n)"""
    res = []
    for p, U in rbars:
        (x0, y0), (x1, y1) = p
        if not (pg.buffer(250).contains(Point(x0, y0)) and pg.buffer(250).contains(Point(x1, y1))): continue
        horiz = abs(y1 - y0) < 5; vert = abs(x1 - x0) < 5
        if not (horiz or vert): continue
        L = round(math.dist(p[0], p[1]) / 10) * 10
        if L < 500: continue
        mid = ((x0 + x1) / 2, (y0 + y1) / 2)
        # its text: nearest "T d @ s" written along the bar
        cand = [t for t in adds if (abs((t[3] or 0) % 180 - 90) < 5) == vert]
        if not cand: continue
        t = min(cand, key=lambda t: math.dist((t[1], t[2]), mid))
        if math.dist((t[1], t[2]), mid) > 3500: continue
        mm_ = re.match(r'^T\s*(\d+)\s*@\s*(\d+)\s*(.*)$', t[0].upper())
        d, s_, rest = int(mm_.group(1)), int(mm_.group(2)), mm_.group(3)
        # its zone: the dimension across the bar that crosses it
        best = None
        for a, b in dims:
            if horiz and abs(a[0] - b[0]) < 30 and min(x0, x1) - 100 <= a[0] <= max(x0, x1) + 100 and min(a[1], b[1]) - 50 <= y0 <= max(a[1], b[1]) + 50:
                z = (min(a[1], b[1]), max(a[1], b[1]))
            elif vert and abs(a[1] - b[1]) < 30 and min(y0, y1) - 100 <= a[1] <= max(y0, y1) + 100 and min(a[0], b[0]) - 50 <= x0 <= max(a[0], b[0]) + 50:
                z = (min(a[0], b[0]), max(a[0], b[0]))
            else: continue
            if z[1] - z[0] > 300 and (best is None or z[1] - z[0] < best[1] - best[0]): best = z
        if best is None: continue
        a0, a1 = (min(x0, x1), max(x0, x1)) if horiz else (min(y0, y1), max(y0, y1))
        key = (horiz, round(a0), round(best[0]))
        if any(k['_k'] == key for k in res): continue
        res.append(dict(_k=key, d=d, s=s_, layer='T' if ('TOP' in rest or '-TP' in U) else 'B', note=rest.strip(),
                        along='X' if horiz else 'Y', L=L, a0=a0, a1=a1, z0=best[0], z1=best[1],
                        n=int(round((best[1] - best[0]) / s_)) + 1, x=(a0 + a1) / 2 if horiz else (best[0] + best[1]) / 2,
                        y=(best[0] + best[1]) / 2 if horiz else (a0 + a1) / 2))
    for r in res: r.pop('_k')
    return res
for m in out:
    pg = m['poly']
    m['zones'] = [dict(z, a0=z['a0'] + (DX if z['along'] == 'X' else DY), a1=z['a1'] + (DX if z['along'] == 'X' else DY),
                       z0=z['z0'] + (DY if z['along'] == 'X' else DX), z1=z['z1'] + (DY if z['along'] == 'X' else DX),
                       x=z['x'] + DX, y=z['y'] + DY) for z in add_zones(pg)]
    m['adds'] = [(s, x + DX, y + DY, r) for s, x, y, r, l in adds if pg.buffer(200).contains(Point(x, y))]
    m['L_txt'] = [(s, x + DX, y + DY, r) for s, x, y, r, l in Ls if pg.buffer(200).contains(Point(x, y))]
    m['poly'] = affinity.translate(pg.simplify(1), DX, DY); m['lx'] += DX; m['ly'] += DY
    b = m['poly'].bounds; m['bbox'] = b
    m['rect'] = abs(m['poly'].area - (b[2] - b[0]) * (b[3] - b[1])) < 0.01 * m['poly'].area
pickle.dump(out, open('mats.pkl', 'wb'))
c = collections.Counter(m['lab'] for m in out)
print(len(out), 'labelled mats', dict(c))
for m in out:
    b = m['bbox']
    print(' ', m['lab'], round(b[2] - b[0]), 'x', round(b[3] - b[1]), 'rect' if m['rect'] else f"POLY {len(m['poly'].exterior.coords) - 1} vertices", 'adds', len(m['adds']), 'zones', len(m['zones']), [(z['along'], z['d'], z['s'], z['layer'], z['L'], round(z['z1'] - z['z0']), z['n']) for z in m['zones']])
