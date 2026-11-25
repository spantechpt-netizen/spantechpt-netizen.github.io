"""Curved grade beams of a zone -> <root>/<zone>/curves.json: developed lines (centre polyline in ORIGINAL coords, supports =
columns crossing the band), read by build.py / post_curved.py.
usage: GBZ_CONFIG=cfg.json python3 curves.py <zone> [--ext 400]
  --ext E: a curve running column face to column face is extended E straight into each column (tangent) so the developed
  section gets real column supports; post_curved reports the radius without the extensions ("ext")."""
import json, math, pickle, ezdxf, ezdxf.recover, re
from shapely.geometry import LineString, Point, Polygon
from shapely.affinity import rotate
from shapely.ops import unary_union
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gbzcfg import Cfg
K = Cfg(sys.argv[1]); EXT = int(sys.argv[sys.argv.index('--ext') + 1]) if '--ext' in sys.argv else 0
d = ezdxf.recover.readfile(K.p(K.z['src']))[0]; m = d.modelspace()
arcs = [e for e in m.query('ARC') if e.dxf.layer.startswith('S-BEAM') and e.dxf.radius > 1000]
groups = {}
for a in arcs:
    k = (round(a.dxf.center.x), round(a.dxf.center.y)); groups.setdefault(k, []).append(a)
pieces = []
for k, es in groups.items():
    rs = sorted({round(e.dxf.radius) for e in es}); w = rs[-1] - rs[0]; rm = (rs[0] + rs[-1]) / 2
    a0 = min(e.dxf.start_angle for e in es); a1 = max(e.dxf.end_angle for e in es)
    n = max(8, int((a1 - a0) * 2))
    pts = [(k[0] + rm * math.cos(math.radians(a0 + (a1 - a0) * i / n)), k[1] + rm * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    pieces.append(dict(c=k, w=w, pts=pts))
# chain pieces whose ends meet (compound curve)
curves = []
used = set()
for i, p in enumerate(pieces):
    if i in used: continue
    chain = [p]; used.add(i); changed = True
    while changed:
        changed = False
        for j, q in enumerate(pieces):
            if j in used or abs(q['w'] - p['w']) > 20: continue
            for end in (0, -1):
                for qe in (0, -1):
                    if math.dist(chain[end]['pts'][end] if end == 0 else chain[-1]['pts'][-1], q['pts'][qe]) < 400:
                        qq = dict(q, pts=q['pts'] if (qe == 0) == (end == -1) else q['pts'][::-1])
                        if end == -1: chain.append(qq)
                        else: chain.insert(0, qq)
                        used.add(j); changed = True; break
                if changed: break
            if changed: break
    pts = [pt for c in chain for pt in c['pts']]
    curves.append(dict(w=p['w'], pts=pts))
# columns (original coords) from the parts
cols = []
for pn in K.parts():
    pj = json.load(open(K.partdir(pn) + '/part.json')); pk = pickle.load(open(K.partdir(pn) + '/plans.pkl', 'rb'))[pn]
    for c in pk['cols']:
        pg = Polygon(c)
        if pg.is_valid and pg.area > 5e4: cols.append(rotate(pg, pj['ang'], origin=(0, 0)))
cu = unary_union(cols); cols = list(getattr(cu, 'geoms', [cu]))
labs = []
for e in m.query('MTEXT TEXT'):
    t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).replace('*', 'X').strip()
    if e.dxf.layer in ('S-BEAM-IDEN', 'S-COLS-IDEN'): labs.append((t, e.dxf.insert.x, e.dxf.insert.y, e.dxf.layer))
out = []
for i, cv in enumerate(curves):
    ln = LineString(cv['pts']); band = ln.buffer(cv['w'] / 2 + 30)
    L = ln.length; sup = []
    for c in cols:
        if c.intersects(band):
            ss = [ln.project(Point(q)) for q in c.exterior.coords]
            lab = min((l for l in labs if l[3] == 'S-COLS-IDEN'), key=lambda l: c.distance(Point(l[1], l[2])))
            sup.append(dict(s0=max(0, min(ss)), s1=min(L, max(ss)), lab=lab[0] if c.distance(Point(lab[1], lab[2])) < 1500 else 'COL', size=None))
    sup.sort(key=lambda q: q['s0'])
    tl = [(l[0], ln.project(Point(l[1], l[2]))) for l in labs if l[3] == 'S-BEAM-IDEN' and ln.distance(Point(l[1], l[2])) < 900 and re.match(r'^GB\d', l[0])]
    out.append(dict(code=f'CV-{i + 1:02d}', w=cv['w'], L=round(L), pts=[(round(x), round(y)) for x, y in cv['pts']], sup=sup, tlab=tl))
    print(out[-1]['code'], 'w', cv['w'], 'L', round(L), 'ends', [tuple(round(v) for v in cv['pts'][0])], [tuple(round(v) for v in cv['pts'][-1])], 'sup', [(round(q['s0']), round(q['s1']), q['lab']) for q in sup], 'labels', tl)
if EXT:                                                     # extend face-to-face curves into the end columns
    for cv in out:
        pts = cv['pts']; ext = lambda a, b: [round(a[0] + (a[0] - b[0]) / math.dist(a, b) * EXT), round(a[1] + (a[1] - b[1]) / math.dist(a, b) * EXT)]
        lab = lambda q: q['lab']
        l0, l1 = (lab(cv['sup'][0]), lab(cv['sup'][-1])) if cv['sup'] else ('COL', 'COL')
        L0 = cv['L']; cv['pts'] = [ext(pts[0], pts[1])] + pts + [ext(pts[-1], pts[-2])]; cv['L'] = L0 + 2 * EXT; cv['ext'] = EXT
        cv['sup'] = [dict(s0=0, s1=EXT, lab=l0, size=None), dict(s0=L0 + EXT, s1=L0 + 2 * EXT, lab=l1, size=None)]
        cv['tlab'] = [[t, s + EXT] for t, s in cv['tlab']]
json.dump(out, open(K.zdir('curves.json'), 'w'))
