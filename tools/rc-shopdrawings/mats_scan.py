"""Combined footings / rafts / strap footings: outline polygons (project.json -> fnd_layers, default CORE-FNDN) with their label, the columns inside,
the ADD TOP / ADD BOT annotations inside. -> mats.pkl"""
import json, pickle, re, math, collections
from ezdxf import recover
from shapely.geometry import Polygon, Point
P = json.load(open('project.json'))
doc, _ = recover.readfile(P.get('dxf', 'main.dxf')); msp = doc.modelspace()
cx, cy, H = P['fnd_view']; W = H * 1.6
X0, X1, Y0, Y1 = cx - W / 2, cx + W / 2, cy - H / 2, cy + H / 2
polys, texts = [], []
FNDL = tuple(P.get('fnd_layers', ['CORE-FNDN']))
def walk(e, d=0, inh=None):
    t = e.dxftype()
    if inh and e.dxf.layer == '0': e.dxf.layer = inh          # layer 0 in a block = the INSERT's layer
    if t == 'INSERT' and d < 3:
        try:
            for v in e.virtual_entities(): walk(v, d + 1, e.dxf.layer)
        except Exception: pass
    elif t == 'LWPOLYLINE' and e.dxf.layer.endswith(FNDL):
        p = [(a, b) for a, b in e.get_points('xy')]
        if len(p) >= 4 and X0 < p[0][0] < X1 and Y0 < p[0][1] < Y1:
            try:
                pg = Polygon(p).buffer(0)
                if pg.area > 1e6: polys.append(pg)
            except Exception: pass
    elif t in ('TEXT', 'MTEXT'):
        s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if X0 < x < X1 and Y0 < y < Y1: texts.append((s, x, y, getattr(e.dxf, 'rotation', 0) or 0))
for e in msp: walk(e)
# unique polygons
up = []
for pg in polys:
    if not any(abs(pg.area - q.area) < 1e4 and pg.centroid.distance(q.centroid) < 50 for q in up): up.append(pg)
LAB = re.compile(r'^(CF\d+|RAFT-?\d+|ST-?\d+)$')
mats = []
for s, x, y, r in texts:
    if not LAB.match(s): continue
    cont = [pg for pg in up if pg.buffer(50).contains(Point(x, y)) and (s.startswith('ST') or pg.area > 12e6)]
    if not cont: continue
    pg = min(cont, key=lambda g: g.area)
    mats.append(dict(lab=s, poly=pg, lx=x, ly=y))
# the same outline labelled twice -> once
out = []
for m in mats:
    if not any(m['lab'] == o['lab'] and m['poly'].equals(o['poly']) for o in out): out.append(m)
adds = [t for t in texts if re.match(r'^T\s*\d+\s*@\s*\d+', t[0].upper())]   # additional bars written on the plan
Ls = [t for t in texts if re.match(r'^L\s*=\s*\d+', t[0].replace(' ', ''))]
for m in out:
    pg = m['poly']
    m['adds'] = [t for t in adds if pg.buffer(200).contains(Point(t[1], t[2]))]
    m['L_txt'] = [t for t in Ls if pg.buffer(200).contains(Point(t[1], t[2]))]
    b = pg.bounds; m['bbox'] = b; m['rect'] = abs(pg.area - (b[2] - b[0]) * (b[3] - b[1])) < 0.01 * pg.area
pickle.dump(out, open('mats.pkl', 'wb'))
c = collections.Counter(m['lab'] for m in out)
print(len(up), 'outlines;', len(out), 'labelled mats', dict(c))
for m in out:
    b = m['bbox']; print(' ', m['lab'], round(b[2] - b[0]), 'x', round(b[3] - b[1]), 'rect' if m['rect'] else 'POLY', 'adds', len(m['adds']))
