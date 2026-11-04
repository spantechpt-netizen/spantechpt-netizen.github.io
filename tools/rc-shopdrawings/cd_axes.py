"""Grid of the foundation plan: A-AXIS-ST line segments grouped per coordinate, named by the bubble at their end.
-> cd_axes.json {name: {fam, segs: [[coord, lo, hi], ...]}}"""
import json, pickle, collections, math
from ezdxf import recover
P = json.load(open('project.json')); doc, _ = recover.readfile(P.get('dxf', 'main.dxf')); msp = doc.modelspace()
cx, cy, H = P['fnd_view']; W = H * 1.6; X0, X1, Y0, Y1 = cx - W / 2, cx + W / 2, cy - H / 2, cy + H / 2
GL = tuple(P.get('grid_layers', ['A-AXIS-ST']))
segs = []
for e in msp.query('LINE'):
    if not e.dxf.layer.endswith(GL): continue
    a, b = e.dxf.start, e.dxf.end
    if not (X0 < a.x < X1 and Y0 < a.y < Y1): continue
    if abs(a.y - b.y) < 1: segs.append(('X', (a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
    elif abs(a.x - b.x) < 1: segs.append(('Y', (a.x + b.x) / 2, min(a.y, b.y), max(a.y, b.y)))
bub = pickle.load(open('cd_scan.pkl', 'rb'))['ax']
grp = collections.defaultdict(list)
for f, c, lo, hi in segs: grp[(f, round(c / 5) * 5)].append([c, lo, hi])
axes = {}
for (f, c), ss in grp.items():
    # merge collinear pieces
    ss.sort(key=lambda s: s[1]); m = []
    for s in ss:
        if m and s[1] <= m[-1][2] + 50: m[-1][2] = max(m[-1][2], s[2])
        else: m.append(list(s))
    if sum(s[2] - s[1] for s in m) < 3000: continue
    # name: the bubble of that family nearest to an end of the line (bubble on the line's extension)
    best = None
    for bf, bn, bx, by in bub:
        if bf != f: continue
        u, v = (bx, by) if f == 'X' else (by, bx)          # u along the line, v across
        if abs(v - c) > 400: continue
        dd = min(abs(u - m[0][1]), abs(u - m[-1][2]))
        if best is None or dd < best[0]: best = (dd, bf + bn)
    if not best or best[0] > 6000: continue
    nm = best[1]
    ax = axes.setdefault(nm, dict(fam=f, segs=[]))
    ax['segs'] += [[c, s[1], s[2]] for s in m]
# bubbles with no grid line (line on another layer / missing): the line between the two bubbles of that name
byname = collections.defaultdict(list)
for bf, bn, bx, by in bub: byname[bf + bn].append((bx, by))
for nm, pts in byname.items():
    if nm in axes or len(pts) < 2: continue
    f = nm[0]
    c = sum(p[1] if f == 'X' else p[0] for p in pts) / len(pts)
    us = [p[0] if f == 'X' else p[1] for p in pts]
    axes[nm] = dict(fam=f, segs=[[c, min(us), max(us)]])
    print('axis from bubbles only:', nm)
for nm, a in axes.items(): a['segs'].sort(key=lambda s: s[1])
json.dump(axes, open('cd_axes.json', 'w'), indent=0)
print(len(axes), sorted(axes))
for nm in ('Y01', 'X10*', 'Y23*', 'X01'): print(nm, axes.get(nm))
