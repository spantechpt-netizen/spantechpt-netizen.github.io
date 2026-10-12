"""A new revision of the foundation plan against the one the package was made from.
usage: python3 rev_compare.py new.dxf          (cd_scan.pkl of the OLD drawing in the current folder)
1. shift between the two drawings: vote over same-size RC rectangles (the new file is often re-based);
2. per footing label (by position, 1.5 m): renamed (= type reassigned), gone, new;
3. read the new schedule with table_dump.py and diff it against footings.json by hand (new rows, changed depth).
Prints the shift (pass it to zones.py) and the changes."""
import collections, math, pickle, re, sys
from ezdxf import recover

rx = re.compile(r'^(F\d+[A-Z]?|FF\d+|CF\d+|RAFT-?\d+(-?[A-Z])?|ST-\d+)$')
doc, _ = recover.readfile(sys.argv[1]); msp = doc.modelspace()
def walk(e, lay=None, d=0):
    if lay and e.dxf.layer == '0': e.dxf.layer = lay
    if e.dxftype() == 'INSERT':
        if d < 6:
            try:
                for v in e.virtual_entities(): yield from walk(v, e.dxf.layer, d + 1)
            except Exception: pass
    else: yield e
R, L, G = [], [], []
for top in msp:
    for e in walk(top):
        t = e.dxftype()
        if t == 'LWPOLYLINE' and 'FNDN' in e.dxf.layer.upper():
            p = [(q[0], q[1]) for q in e.get_points()]
            G.append(p)                                      # any foundation geometry (open strip edges too)
            if e.closed and len(p) >= 4: R.append(p)
        elif t == 'LINE' and 'FNDN' in e.dxf.layer.upper():
            G.append([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
        elif t in ('TEXT', 'MTEXT'):
            s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
            if rx.match(s): L.append((s, e.dxf.insert.x, e.dxf.insert.y))
old = pickle.load(open('cd_scan.pkl', 'rb'))
rect = lambda p: (min(a for a, b in p), min(b for a, b in p), round(max(a for a, b in p) - min(a for a, b in p)), round(max(b for a, b in p) - min(b for a, b in p)))
bysz = collections.defaultdict(list)
for b in map(rect, old['rc']): bysz[b[2:]].append(b)
votes = collections.Counter()
for a in map(rect, R):
    for b in bysz.get(a[2:], [])[:60]: votes[(round(b[0] - a[0], -1), round(b[1] - a[1], -1))] += 1
(DX, DY), nv = votes.most_common(1)[0]
boxes = [rect(p) for p in G]                                 # labels of the plan only (not the schedule rows)
L = [l for l in L if any(b[0] - 2000 < l[1] < b[0] + b[2] + 2000 and b[1] - 2000 < l[2] < b[1] + b[3] + 2000 for b in boxes)]
print(f'shift new -> old: {DX:.0f},{DY:.0f}  ({nv} rectangles agree)')
N = [(s, x + DX, y + DY) for s, x, y in L]
O = [(s, x, y) for s, x, y in old['lab'] if rx.match(s)]
near = lambda p, lst: [q for q in lst if math.hypot(q[1] - p[1], q[2] - p[2]) < 1500]
for o in O:
    m = near(o, N)
    if not m: print('GONE   ', o[0], round(o[1]), round(o[2]))
    elif o[0] not in [q[0] for q in m]: print('RENAMED', o[0], '->', sorted({q[0] for q in m}), round(o[1]), round(o[2]))
for n in N:
    if not near(n, O): print('NEW    ', n[0], round(n[1]), round(n[2]))
co, cn = collections.Counter(s for s, x, y in O), collections.Counter(s for s, x, y in N)
print('label counts changed:', {k: (co[k], cn[k]) for k in sorted(set(co) | set(cn)) if co[k] != cn[k]})
