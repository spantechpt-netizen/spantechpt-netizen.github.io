"""Column necks: pair every column of the foundation plan with the footing it stands on.
project.json -> fnd_view: [centre x, centre y, height] of the foundation-plan window (aspect 1.6).
Columns: outlines on the layers ending with project.json -> fnd_col_layers (default CORE-COLS-CONC; model space + blocks), typed by size (column_sizes), duplicates merged
(type from the nearest plan label such as 'C3 35X80').
project.json -> column_labels: {"dxf": final plan, "shift": [dx, dy]}: the column labels of that plan are read too (a
final plan often labels every column, the working one only some). A column whose drawn size is not in column_sizes
but equals the size written on its label ('C8 30X100' when C8 is 35x100) is kept as a size variant 'C8@300x1000'. Isolated footings (in footings.json): every label matched to
its nearest column, nearest pairs first. Combined footings / rafts / straps (labels CF*, RAFT*, ST*): every column
inside their outline (outline layers: fnd_layers, default CORE-FNDN). -> neck_pairs.txt (C:F:count for gen_n.py) + neck_pairs.pkl (details, unmatched)."""
import json, pickle, collections, re, math
from ezdxf import recover
P = json.load(open('project.json'))
doc, _ = recover.readfile(P.get('dxf', 'main.dxf')); msp = doc.modelspace()
cx, cy, H = P['fnd_view']; W = H * 1.6
X0, X1, Y0, Y1 = cx - W / 2, cx + W / 2, cy - H / 2, cy + H / 2
sizes = P['column_sizes']; bysize = {tuple(sorted(v)): k for k, v in sizes.items()}
sched = json.load(open('footings.json'))
COLL = tuple(P.get('fnd_col_layers', ['CORE-COLS-CONC'])); FNDL = tuple(P.get('fnd_layers', ['CORE-FNDN']))
crect, frect, labs, flabs = [], [], [], []
cexp = {}; crect_f = []; clines, clines_f = [], []                 # crect_f: column outlines of the final plan (only refine the columns found here)
LBL = re.compile(P.get('footing_label_re', r'(F\d*A?|Fx|CF\d+|FF\d+|RAFT-?\d*|ST-?\d*)'))
def walk(e, d=0, inh=None, sh=(0, 0), win=True):
    t = e.dxftype()
    if inh and e.dxf.layer == '0': e.dxf.layer = inh          # layer 0 in a block = the INSERT's layer
    if t == 'INSERT' and d < 3:
        try:
            for v in e.virtual_entities(): walk(v, d + 1, e.dxf.layer, sh, win)
        except Exception: pass
    elif t == 'LWPOLYLINE':
        p = e.get_points('xy')
        if len(p) < 4: return
        xs = [a + sh[0] for a, b in p]; ys = [b + sh[1] for a, b in p]
        if not (X0 < min(xs) < X1 and Y0 < min(ys) < Y1): return
        r = (min(xs), min(ys), max(xs), max(ys))
        if e.dxf.layer.endswith(COLL):
            (crect if win else crect_f).append(r); cexp[r] = cexp.get(r, False) or d == 0   # drawn on its own (not a block)
        elif e.dxf.layer.endswith(FNDL) and win: frect.append(r)
    elif t == 'LINE' and e.dxf.layer.endswith(COLL):     # columns drawn as four loose lines (assembled below)
        a_, b_ = e.dxf.start, e.dxf.end
        p = ((a_.x + sh[0], a_.y + sh[1]), (b_.x + sh[0], b_.y + sh[1]))
        if X0 < p[0][0] < X1 and Y0 < p[0][1] < Y1: (clines if win else clines_f).append(p)
    elif t in ('TEXT', 'MTEXT') and win:
        s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if not (X0 < x < X1 and Y0 < y < Y1): return
        m = re.match(r'^(C\d*)\s+(\d+)\s*X\s*(\d+)', s.upper())
        if m: labs.append((m.group(1), x, y, int(m.group(2)) * 10, int(m.group(3)) * 10))
        elif LBL.fullmatch(s): flabs.append((s, x, y))
for e in msp: walk(e)
CLF = P.get('column_labels')
if CLF:                                      # the column labels of the final plan (shifted to these coordinates)
    ldoc, _ = recover.readfile(CLF['dxf']); sdx, sdy = CLF.get('shift', [0, 0])
    if CLF.get('columns', True):             # the final plan's column outlines too (corrections drawn over the blocks)
        for e in ldoc.modelspace(): walk(e, 0, None, (sdx, sdy), False)
    for e in ldoc.modelspace():
        if e.dxftype() not in ('TEXT', 'MTEXT'): continue
        s = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip().upper()
        m = re.match(r'^(C\d*)\s+(\d+)\s*X\s*(\d+)$', s)
        if m:
            x, y = e.dxf.insert.x + sdx, e.dxf.insert.y + sdy
            if not any(l[0] == m.group(1) and math.dist((l[1], l[2]), (x, y)) < 300 for l in labs):
                labs.append((m.group(1), x, y, int(m.group(2)) * 10, int(m.group(3)) * 10))
def line_rects(lines):
    """closed rectangles made of loose LINEs (column outlines drawn line by line)"""
    from shapely.geometry import LineString
    from shapely.ops import unary_union, polygonize
    out = []
    if not lines: return out
    for f_ in polygonize(unary_union([LineString(p) for p in lines if math.dist(*p) > 1])):
        x0_, y0_, x1_, y1_ = f_.bounds
        if 150 <= x1_ - x0_ <= 1500 and 150 <= y1_ - y0_ <= 1500 and abs(f_.area - (x1_ - x0_) * (y1_ - y0_)) < 0.02 * f_.area:
            out.append((x0_, y0_, x1_, y1_))
    return out
for r in line_rects(clines): crect.append(r); cexp[r] = True
for r in line_rects(clines_f): crect_f.append(r); cexp[r] = True
frect = sorted(set(frect))
fo = []
for s, x, y in flabs:                       # each label -> smallest footing outline containing it (or near it)
    big = [r for r in frect if r[2] - r[0] > 900 and r[3] - r[1] > 900]
    cont = [r for r in big if r[0] - 50 <= x <= r[2] + 50 and r[1] - 50 <= y <= r[3] + 50] or \
           [r for r in big if r[0] - 600 <= x <= r[2] + 600 and r[1] - 600 <= y <= r[3] + 600]
    fo.append(dict(lab=s, x=x, y=y, r=min(cont, key=lambda r: (r[2] - r[0]) * (r[3] - r[1])) if cont else None))
cl = []
crect_f_set = set(crect_f) - set(crect)
for r in crect + crect_f:
    sz = tuple(sorted((round((r[2] - r[0]) / 50) * 50, round((r[3] - r[1]) / 50) * 50)))
    t = bysize.get(sz)
    if not t:                                # a size variant written on its label (C8 30X100)
        c_ = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
        lab = [l for l in labs if tuple(sorted(l[3:5])) == sz and l[0] in sizes and math.dist((l[1], l[2]), c_) < 2500]
        if not lab: continue
        t = f"{lab[0][0]}@{sz[0]}x{sz[1]}"; sizes.setdefault(t, list(sz))
    c = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
    for k in cl:
        if math.dist(k['c'], c) <= 450:
            k['cand'].add(t); k['r'].setdefault(t, r)
            if cexp.get(r): k['exp'].add(t)
            break
    else:
        if r in crect_f_set: continue                        # a final-plan outline with no column here: not a new column
        cl.append(dict(c=c, cand={t}, r={t: r}, exp={t} if cexp.get(r) else set()))   # r: the outline of each candidate type
for k in cl:
    near = [l for l in labs if (l[0] in k['cand'] or any(c.startswith(l[0] + '@') for c in k['cand'])) and math.dist((l[1], l[2]), k['c']) < 3000]
    close_ = [l for l in near if math.dist((l[1], l[2]), k['c']) < 1500]
    if len(k['cand']) == 1:
        k['t'] = next(iter(k['cand']))
    elif len(k['exp']) == 1 and not (close_ and min(close_, key=lambda l: math.dist((l[1], l[2]), k['c']))[0] not in k['exp']):
        k['t'] = next(iter(k['exp']))         # an outline drawn on its own over a generic column block: the real column
    elif len(k['exp']) == 1:                  # its label says otherwise: the label wins, reported
        k['t'] = min(close_, key=lambda l: math.dist((l[1], l[2]), k['c']))[0]
        k['conflict'] = f"label {k['t']} but drawn {next(iter(k['exp']))} ({'x'.join(str(int(v)) for v in sizes[next(iter(k['exp']))])})"
    elif near:
        lt = min(near, key=lambda l: math.dist((l[1], l[2]), k['c']))[0]
        k['t'] = lt if lt in k['cand'] else next(c for c in k['cand'] if c.startswith(lt + '@'))
    else:
        k['t'] = max(k['cand'], key=lambda t: sizes[t][0] * sizes[t][1])
pairs = collections.Counter(); used = set(); det = []
iso = [o for o in fo if o['lab'] in sched]
cand = sorted((math.dist(k['c'], (o['x'], o['y'])), j, i) for j, o in enumerate(iso) for i, k in enumerate(cl)
              if math.dist(k['c'], (o['x'], o['y'])) <= 1.6 * max(sched[o['lab']]['L'], sched[o['lab']]['W']))
done = set()
for dd, j, i in cand:
    if j in done or i in used: continue
    done.add(j); used.add(i); pairs[(cl[i]['t'], iso[j]['lab'])] += 1; det.append((cl[i]['t'], iso[j]['lab'], cl[i]['c']))
det += [(None, o['lab'], (o['x'], o['y'])) for j, o in enumerate(iso) if j not in done]
for o in fo:                                 # combined footings / rafts / straps: all columns inside
    if o['lab'] in sched or not o['r'] or not re.match(r'(CF|RAFT|ST)', o['lab']): continue
    r = o['r']
    for i, k in enumerate(cl):
        if i not in used and r[0] <= k['c'][0] <= r[2] and r[1] <= k['c'][1] <= r[3]:
            used.add(i); pairs[(k['t'], o['lab'])] += 1; det.append((k['t'], o['lab'], k['c']))
for i, k in enumerate(cl):                   # a second column on an isolated footing: the labelled outline around it
    if i in used: continue
    cont = [o for o in fo if o['r'] and o['r'][0] <= k['c'][0] <= o['r'][2] and o['r'][1] <= k['c'][1] <= o['r'][3]]
    if cont:
        o = min(cont, key=lambda o: (o['r'][2] - o['r'][0]) * (o['r'][3] - o['r'][1]))
        used.add(i); pairs[(k['t'], o['lab'])] += 1; det.append((k['t'], o['lab'], k['c']))
left = [k for i, k in enumerate(cl) if i not in used]
order = lambda kv: (int(re.sub(r'\D', '', kv[0][0].split('@')[0]) or 0), kv[0][0], kv[0][1])
open('neck_pairs.txt', 'w').write('\n'.join(f'{t}:{l}:{n}' for (t, l), n in sorted(pairs.items(), key=order)) + '\n')
pickle.dump(dict(pairs=pairs, det=det, left=left, cl=cl), open('neck_pairs.pkl', 'wb'))
print('columns', len(cl), 'necks', sum(pairs.values()), 'pairs', len(pairs), 'no footing', len(left),
      'labels without column', sum(1 for t, l, c in det if t is None))
