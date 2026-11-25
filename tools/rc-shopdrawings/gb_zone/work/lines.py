# beam lines per plan: collinear segments merged through columns, ends extended into the end supports,
# supports (columns) and crossing beams along each line, type from the nearest GB label, level tags
import pickle, json, math, re, collections, sys, os
from shapely.geometry import Polygon, Point, LineString, box
W_ = sys.argv[1]
D = pickle.load(open(W_ + '/plans.pkl', 'rb'))
SIZE = lambda lab: (lambda m: (int(m.group(1)) * 10, int(m.group(2)) * 10) if m else None)(re.search(r'(\d+)X(\d+)', lab))
out = {}
for pn, P in D.items():
    cols = [Polygon(c) for c in P['cols']]
    clab = []
    for c in cols:
        ls = [l for l in P['labs'] if re.match(r'^C\d|^CORE', l[0])]
        l = min(ls, key=lambda l: c.distance(Point(l[1], l[2]))) if ls else None
        if l and c.distance(Point(l[1], l[2])) < 1500: clab.append(l[0]); continue
        _mr = list(c.minimum_rotated_rectangle.exterior.coords)                       # true size (column turned in this frame)
        dims = sorted((round(math.dist(_mr[0], _mr[1])), round(math.dist(_mr[1], _mr[2]))))          # label further away: size must match
        ok = [l_ for l_ in ls if c.distance(Point(l_[1], l_[2])) < float(os.environ.get('COL_LAB_R', 2000)) and SIZE(l_[0]) and all(abs(a_ - b_) <= 60 for a_, b_ in zip(sorted(SIZE(l_[0])), dims))]
        clab.append(min(ok, key=lambda l_: c.distance(Point(l_[1], l_[2])))[0] if ok else '?')
    for s_ in P['segs']: s_['w'] = 200 if abs(s_['w'] - 200) <= 8 else (300 if abs(s_['w'] - 300) <= 8 else s_['w'])
    segs0 = sorted(P['segs'], key=lambda s: (s['o'], s['w'], s['c']))      # C2 R01: cluster by centre (|dc| < 30) then along the line -
    segs, cl = [], []                                                     # rounding c / 60 split one line and swallowed its lower pieces
    for s in segs0:
        if cl and (s['o'] != cl[-1]['o'] or s['w'] != cl[-1]['w'] or s['c'] - cl[-1]['c'] >= 30): segs += sorted(cl, key=lambda q: q['a']); cl = []
        cl.append(s)
    segs += sorted(cl, key=lambda q: q['a'])
    rect = lambda s: box(s['a'], s['c'] - s['w'] / 2, s['b'], s['c'] + s['w'] / 2) if s['o'] == 'H' else box(s['c'] - s['w'] / 2, s['a'], s['c'] + s['w'] / 2, s['b'])
    lines = []
    for s in segs:
        g = lines[-1] if lines else None
        if g and g['o'] == s['o'] and abs(g['c'] - s['c']) < 30 and abs(g['w'] - s['w']) <= 8:
            gap = box(g['b'], s['c'] - 10, s['a'], s['c'] + 10) if s['o'] == 'H' else box(s['c'] - 10, g['b'], s['c'] + 10, s['a'])
            if s['a'] >= g['a'] - 30 and (s['a'] - g['b'] < 30 or any(c.contains(gap) or c.buffer(20).contains(gap) for c in cols)):
                g['b'] = max(g['b'], s['b']); continue
        lines.append(dict(s))
    res = []
    for g in lines:
        for end in ('a', 'b'):
            p = Point((g[end], g['c']) if g['o'] == 'H' else (g['c'], g[end]))
            for c in cols:
                if c.distance(p) < float(os.environ.get('COL_SNAP', 60)) and c.area < 3e6:
                    x0, y0, x1, y1 = c.bounds
                    lo, hi = (x0, x1) if g['o'] == 'H' else (y0, y1)
                    if end == 'a' and lo < g['a'] + 5: g['a'] = lo
                    if end == 'b' and hi > g['b'] - 5: g['b'] = hi
        r = rect(g)
        sup = []
        for c, lab in zip(cols, clab):
            if c.intersects(r.buffer(-2)) and c.area < 3e6:
                x0, y0, x1, y1 = c.bounds
                lo, hi = (x0, x1) if g['o'] == 'H' else (y0, y1)
                sup.append(dict(s0=max(lo, g['a']), s1=min(hi, g['b']), lab=lab, size=SIZE(lab), x0=round(x0), y0=round(y0), x1=round(x1), y1=round(y1)))
        core = [c for c, lab in zip(cols, clab) if c.area >= 3e6 and c.intersects(r.buffer(-2))]
        cross = []
        for s in segs:
            if s['o'] != g['o'] and rect(s).intersects(r):
                lo, hi = s['c'] - s['w'] / 2, s['c'] + s['w'] / 2
                if any(min(hi, q['s1']) > max(lo, q['s0']) for q in sup): continue
                cross.append(dict(s0=lo, s1=hi, w=s['w']))
        gl = [l for l in P['labs'] if re.match(r'^(GB|TB)\d', l[0]) and r.buffer(900).contains(Point(l[1], l[2]))]
        types = collections.Counter(l[0] for l in gl)
        lv = [l for l in P['levels'] if r.buffer(1500).contains(Point(l[0], l[1]))]
        res.append(dict(o=g['o'], c=round(g['c']), w=g['w'], a=round(g['a']), b=round(g['b']), L=round(g['b'] - g['a']), sup=sorted(sup, key=lambda q: q['s0']),
                        cross=sorted(cross, key=lambda q: q['s0']), core=bool(core), types=dict(types), tlab=[(l[0], round(l[1] if g['o'] == 'H' else l[2])) for l in gl], levels=[l[2] for l in lv],
                        lev_at=[round(l[1] if g['o'] == 'V' else l[0]) for l in lv]))
    res.sort(key=lambda l: (l['o'] != 'H', -l['c'] if l['o'] == 'H' else l['c'], l['a']))
    for i, l in enumerate(res): l['code'] = f'{pn}-GB-{i + 1:02d}'
    out[pn] = res
    for l in res: print(pn, l['code'], l['o'], l['w'], l['L'], l['types'], 'sup', [(round(q['s1'] - q['s0']), q['lab']) for q in l['sup']], 'cross', len(l['cross']), 'core' if l['core'] else '', l['levels'])
json.dump(out, open(W_ + '/lines.json', 'w'), indent=1)
