"""apply the engineer's final RFI answers to the beam lines of one part (Zone 7).
 - code per line = labels inside the line's extent; two codes -> the one with the larger bar diameter (RFI-08 / 7)
 - red beams on the plan = T.O.GB +0.55, from column face to column face, own bars and legs (RFI-03)
 - beam ending at CORE 1: the wall it meets is the end support (Ld = 60d straight / with a leg) (RFI-11)"""
import json, pickle, re, sys
from shapely.geometry import Polygon, LineString, Point, box
W_, PN, CFG = sys.argv[1], sys.argv[2], sys.argv[3]
LJ = json.load(open(W_ + '/lines.json')); P = pickle.load(open(W_ + '/plans.pkl', 'rb'))[PN]; G = pickle.load(open(W_ + '/geo.pkl', 'rb'))
sched = json.load(open(CFG))['schedule']
W = box(*{'P1': (224000, 116000, 256000, 162000), 'P2': (224000, 65700, 256000, 112000), 'P3': (224000, 12300, 256000, 58600)}[PN])
core = max((Polygon(c) for c in P['cols']), key=lambda p: p.area)
red = [g for g in G if g[0] == 'CORE-FNDN-GRBM' and g[3] == 1 and W.contains(LineString(g[2]).centroid)]
dia = lambda t: max(sched[t]['dt'], sched[t]['db']) if t in sched else 0
out, log = [], []
for l in LJ[PN]:
    l = dict(l)
    for q in l['sup']:                                                  # column with no label on the plan: plan size only (RFI)
        if q['lab'] == '?':
            q['lab'] = "COL {}X{} (NO LABEL)".format(*sorted((round((q['x1'] - q['x0']) / 10), round((q['y1'] - q['y0']) / 10)))); log.append(f"{l['code']}: column without label {q['lab']}")
    labs = []
    for t, x, y in P['labs']:
        if not re.match(r'^(GB|TB)\d', t): continue
        al, pp = (x, y - l['c']) if l['o'] == 'H' else (y, x - l['c'])
        if l['a'] - 300 <= al <= l['b'] + 300 and abs(pp) < 700: labs.append(t)
    if not labs: labs = list(l['types'])
    typ = max(sorted(set(labs)), key=lambda t: (dia(t), labs.count(t))) if labs else '?'
    l['typ'] = typ; l['labels'] = sorted(set(labs))
    if len(set(labs)) > 1: log.append(f"{l['code']}: labels {sorted(set(labs))} -> {typ} (larger bar diameter, RFI-08/7)")
    if not labs: log.append(f"{l['code']}: NO CODE ON THE PLAN")
    cs = [q for q in l['sup'] if q['lab'].startswith('CORE')]
    if cs:
        q = cs[0]; ax = LineString([(l['a'], l['c']), (l['b'], l['c'])] if l['o'] == 'H' else [(l['c'], l['a']), (l['c'], l['b'])])
        outside = (l['a'] < q['s0'] - 50, l['b'] > q['s1'] + 50)
        if not any(outside):
            l['held'] = 'INSIDE-CORE'; log.append(f"{l['code']}: lies inside the core wall footprint"); out.append(l); continue
        pieces = ax.intersection(core)
        segs = sorted(([pc.coords[0][0 if l['o'] == 'H' else 1], pc.coords[-1][0 if l['o'] == 'H' else 1]] for pc in getattr(pieces, 'geoms', [pieces])), key=min)
        segs = [sorted(s) for s in segs]
        if outside[0]: w0, w1 = segs[0]; l['b'] = w1
        else: w0, w1 = segs[-1]; l['a'] = w0
        t_ = round(w1 - w0); Ld = 60 * dia(typ)
        if t_ - 40 >= Ld:
            if outside[0]: w1 = w0 + Ld + 300; l['b'] = w1
            else: w0 = w1 - Ld - 300; l['a'] = w0
        l['sup'] = [s for s in l['sup'] if not s['lab'].startswith('CORE')] + [dict(lab='CORE 1 WALL', s0=w0, s1=w1, core=True, t=t_, face=(w0 if outside[0] else w1))]
        l['sup'].sort(key=lambda s: s['s0']); l['L'] = round(l['b'] - l['a'])
        log.append(f"{l['code']}: core wall end {round(w0)}..{round(w1)} (t={t_})")
    rr = []
    for g in red:
        (x0, y0), (x1, y1) = g[2][0], g[2][-1]
        if l['o'] == 'V' and abs(x0 - x1) < 5 and abs(x0 - l['c']) <= l['w'] / 2 + 5: rr.append(sorted((y0, y1)))
        if l['o'] == 'H' and abs(y0 - y1) < 5 and abs(y0 - l['c']) <= l['w'] / 2 + 5: rr.append(sorted((x0, x1)))
    if rr:
        r0, r1 = min(r[0] for r in rr), max(r[1] for r in rr)
        sa = next((s for s in l['sup'] if abs(s['s1'] - r0) < 60), None); sb = next((s for s in l['sup'] if abs(s['s0'] - r1) < 60), None)
        if sa is None or sb is None:
            l['held'] = 'RED-NOT-AT-COLUMNS'; log.append(f"{l['code']}: red part {r0:.0f}..{r1:.0f} does not start / end at column faces"); out.append(l); continue
        parts = [(l['a'], sa['s1'], 850), (sa['s0'], sb['s1'], 550), (sb['s0'], l['b'], 850)]
        for k, (a, b, top) in enumerate(parts):
            if b - a < 400: continue
            m = dict(l, a=a, b=b, L=round(b - a), top=top, code=f"{l['code']}{'abc'[k]}",
                     sup=[s for s in l['sup'] if s['s1'] > a + 5 and s['s0'] < b - 5], cross=[s for s in l['cross'] if a < s['s0'] < b])
            out.append(m); log.append(f"{m['code']}: {a:.0f}..{b:.0f} T.O.GB {top / 1000:+.2f} supports {[s['lab'] for s in m['sup']]}")
        continue
    l['top'] = 850
    out.append(l)
json.dump({PN: out}, open(f'{W_}/lines_final_{PN}.json', 'w'), indent=1)
print('\n'.join(log)); print(len(out), 'lines')
