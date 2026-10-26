"""Strip footing network from the foundation plan: pairs of parallel RC edges one strip width apart (any source:
closed outlines, outlines merged with the footings, open lines, 2-point polylines) -> centre-line runs; runs on the
same line separated only by a footing are one run through that footing."""
import collections
from shapely.geometry import box
import gen_cd

def strip_runs(els, B=None, tol=40, minlen=1500):
    B = B or gen_cd.STRIP['B']
    segs = []
    def add(q, closed):
        qq = list(q) + ([q[0]] if closed else [])
        for (a, b), (c, d) in zip(qq, qq[1:]):
            if abs(b - d) < 2 and abs(a - c) > 300: segs.append(('H', (b + d) / 2, min(a, c), max(a, c)))
            elif abs(a - c) < 2 and abs(b - d) > 300: segs.append(('V', (a + c) / 2, min(b, d), max(b, d)))
    for q in list(gen_cd.SCAN['rc']) + gen_cd.OPEN['rc'][0]: add(q, True)
    for q in gen_cd.OPEN['rc'][1]: add(q, False)
    runs = []
    for o in 'HV':
        L = sorted([s for s in segs if s[0] == o], key=lambda s: s[1])
        for i, a in enumerate(L):
            for b in L[i + 1:]:
                g = b[1] - a[1]
                if g > B + tol: break
                if abs(g - B) <= tol:
                    lo, hi = max(a[2], b[2]), min(a[3], b[3])
                    if hi - lo > 300: runs.append(dict(o=o, c=(a[1] + b[1]) / 2, lo=lo, hi=hi))
    F = [e for e in els if e['kind'] in ('F', 'M')]
    band = lambda r, lo, hi: box(lo, r['c'] - B / 2, hi, r['c'] + B / 2) if r['o'] == 'H' else box(r['c'] - B / 2, lo, r['c'] + B / 2, hi)
    m = collections.defaultdict(list)
    for r in runs: m[(r['o'], round(r['c'] / 25))].append(r)
    out = []
    for k, rs in m.items():
        rs.sort(key=lambda r: r['lo']); cur = None
        for r in rs:
            if cur and r['lo'] <= cur['hi'] + 10: cur['hi'] = max(cur['hi'], r['hi']); continue
            if cur and r['lo'] - cur['hi'] < 7000:                 # gap filled by a footing: the strip goes through it
                gap = band(cur, cur['hi'], r['lo'])
                if sum(f['rc'].intersection(gap).area for f in F) > 0.8 * gap.area:
                    cur['hi'] = max(cur['hi'], r['hi']); continue
            cur = dict(o=r['o'], c=r['c'], lo=r['lo'], hi=r['hi']); out.append(cur)
    # not a strip: a band that lies inside one footing / raft
    out = [r for r in out if r['hi'] - r['lo'] >= minlen and
           not any(f['rc'].buffer(20).contains(band(r, r['lo'], r['hi'])) for f in F)]
    # not a strip either: the gap between two footings that happens to be B wide (both edges are footing faces)
    def on_ftg(r, side):
        from shapely.geometry import LineString
        y = r['c'] + side * B / 2
        ln = LineString([(r['lo'], y), (r['hi'], y)]) if r['o'] == 'H' else LineString([(y, r['lo']), (y, r['hi'])])
        return sum(f['rc'].exterior.buffer(25).intersection(ln).length for f in F) / ln.length
    out = [r for r in out if max(on_ftg(r, -1), on_ftg(r, 1)) < 0.8]
    # T / cross junctions: the through strip shows as two runs one strip width apart with the other strip ending
    # (or passing) in the gap -> one run through the junction (its bars run through)
    def meets(q, v, c):
        return abs(q['c'] - v) < 60 + B / 2 and abs(abs(q['c'] - v) - B / 2) < 60 and q['lo'] - B - 60 <= c <= q['hi'] + B + 60
    changed = True
    while changed:
        changed = False
        for a in out:
            for b in out:
                if a is b or a['o'] != b['o'] or abs(a['c'] - b['c']) > 25 or not (B - tol <= b['lo'] - a['hi'] <= B + tol): continue
                mid = (a['hi'] + b['lo']) / 2
                if any(q['o'] != a['o'] and abs(q['c'] - mid) < 60 and (q['lo'] - B - 60 <= a['c'] <= q['hi'] + B + 60) for q in out):
                    a['hi'] = b['hi']; out.remove(b); changed = True; break
            if changed: break
    for r in out:
        r['B'] = B
        bx = band(r, r['lo'], r['hi'])
        r['ftg'] = [f for f in F if f['rc'].intersection(bx).area > 0.2e6]
    return out

if __name__ == '__main__':
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    els, cols = gen_cd.build()
    rs = strip_runs(els)
    print(len(rs), 'runs', round(sum(r['hi'] - r['lo'] for r in rs) / 1000, 1), 'm')
    for r in sorted(rs, key=lambda r: (r['o'], round(r['c']), r['lo'])):
        print(r['o'], round(r['c']), round(r['lo']), round(r['hi']), round(r['hi'] - r['lo']), [f['lab'] for f in r['ftg']])
    fig, ax = plt.subplots(figsize=(14, 18))
    for e in els:
        x, y = e['rc'].exterior.xy; ax.plot(x, y, 'g-', lw=.4)
    for q in gen_cd.OPEN['rc'][1]:
        ax.plot([p[0] for p in q], [p[1] for p in q], 'c-', lw=.4)
    for r in rs:
        B = r['B']; x0, y0, x1, y1 = (r['lo'], r['c'] - B / 2, r['hi'], r['c'] + B / 2) if r['o'] == 'H' else (r['c'] - B / 2, r['lo'], r['c'] + B / 2, r['hi'])
        ax.fill([x0, x1, x1, x0], [y0, y0, y1, y1], 'r', alpha=.35)
    ax.set_aspect('equal')
    fig.savefig('strip_net.png', dpi=55)
