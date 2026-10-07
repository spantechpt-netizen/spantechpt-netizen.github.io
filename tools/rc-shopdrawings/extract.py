"""Read a consultant's structural DXF and extract the grade-beam model for the shop-drawing generator.

usage: python3 extract.py project.json
project.json keys (see project.example.json):
  dxf          converted drawing (dwg2dxf from LibreDWG git master reads R2013-R2018)
  layout       paper-space layout whose viewport frames the GB plan (e.g. "4-SOG")
  beam_layer   layer of the GB edge lines (pairs of parallel lines)
  label_layer  layer of the GB1/GB2.. tags
  col_layers   layers of column outlines (searched in model space and inside big blocks)
  axis_block   block of the grid bubbles; axis_attr = attribute tag holding the number
  widths       beam widths to pair (mm)
writes: runs.pkl (beam runs), cols.pkl (column rectangles), axes.json (axis name -> coordinate)
"""
import json, pickle, sys
from collections import defaultdict
from ezdxf import recover, bbox

cfg = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'project.json'))
doc, aud = recover.readfile(cfg['dxf'])
msp = doc.modelspace()

# 1. window = the GB-plan viewport of the given layout
vp = [v for v in doc.layouts.get(cfg['layout']).query('VIEWPORT') if v.dxf.view_center_point.x > 1e4 or v.dxf.view_height > 1e4]
v = max(vp, key=lambda v: v.dxf.view_height)
c, h = v.dxf.view_center_point, v.dxf.view_height
w = h * v.dxf.width / v.dxf.height
X0, X1, Y0, Y1 = c.x - w / 2, c.x + w / 2, c.y - h / 2, c.y + h / 2
inw = lambda p: X0 < p[0] < X1 and Y0 < p[1] < Y1
print('window', round(X0), round(Y0), round(X1), round(Y1))

# 2. axes: bubbles of the axis block; vertical grid lines carry the "Y" names, horizontal the "X" names
axes = {}
for i in msp.query(f'INSERT[name=="{cfg["axis_block"]}"]'):
    if not inw(i.dxf.insert): continue
    at = {a.dxf.tag: a.dxf.text for a in i.attribs}
    num = at.get(cfg.get('axis_attr', '00'))
    fam = at.get(cfg.get('axis_family_attr', 'X'), '').upper()
    if not num: continue
    name = fam + num
    coord = i.dxf.insert.x if fam == 'Y' else i.dxf.insert.y
    axes.setdefault(name, coord)
json.dump(axes, open('axes.json', 'w'), indent=1)
print('axes', len(axes))

# 3. beam edge segments
segs = []
for e in msp.query('LINE LWPOLYLINE'):
    if e.dxf.layer != cfg['beam_layer']: continue
    if e.dxftype() == 'LINE':
        pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
    else:
        pts = [(p[0], p[1]) for p in e.get_points()]
        if e.closed: pts.append(pts[0])
    for a, b in zip(pts, pts[1:]):
        if inw(a): segs.append((a, b))
txt = [(e.dxf.text, e.dxf.insert.x, e.dxf.insert.y) for e in msp.query('TEXT') if e.dxf.layer == cfg['label_layer'] and inw(e.dxf.insert)]

W = set(cfg.get('widths', [200, 350, 400]))
def norm(s, hor):
    (x0, y0), (x1, y1) = s
    return (min(x0, x1), max(x0, x1), (y0 + y1) / 2) if hor else (min(y0, y1), max(y0, y1), (x0 + x1) / 2)
pieces = []
for hor in (True, False):
    L = [norm(s, hor) for s in segs if (abs(s[0][1] - s[1][1]) < 2 if hor else abs(s[0][0] - s[1][0]) < 2)]
    L = sorted([l for l in L if l[1] - l[0] > 150], key=lambda l: l[2])
    for i, a in enumerate(L):
        for b in L[i + 1:]:
            d = b[2] - a[2]
            if d > max(W) + 20: break
            wid = min(W, key=lambda x: abs(x - d))
            if abs(wid - d) > 25: continue
            lo, hi = max(a[0], b[0]), min(a[1], b[1])
            if hi - lo > 200: pieces.append(dict(hor=hor, c=(a[2] + b[2]) / 2, w=wid, lo=lo, hi=hi))
groups = defaultdict(list)
for p in pieces: groups[(p['hor'], round(p['c'] / 10) * 10, p['w'])].append(p)
runs = []
for (hor, cc, wid), ps in groups.items():
    ps.sort(key=lambda p: p['lo']); cur = None
    for p in ps:
        if cur and p['lo'] <= cur['hi'] + 1: cur['hi'] = max(cur['hi'], p['hi'])
        else:
            cur = dict(hor=hor, c=cc, w=wid, lo=p['lo'], hi=p['hi']); runs.append(cur)
for r in runs:
    best = None
    for t, x, y in txt:
        u, vv = (x, y) if r['hor'] else (y, x)
        if r['lo'] - 200 <= u <= r['hi'] + 200:
            d = abs(vv - r['c'])
            if d < 900 and (best is None or d < best[0]): best = (d, t)
    r['lab'] = best[1] if best else None
    fam = 'X' if r['hor'] else 'Y'
    cand = {k: val for k, val in axes.items() if k[0] == fam}
    if cand:
        k = min(cand, key=lambda k: abs(cand[k] - r['c'])); r['axis'], r['off'] = k, r['c'] - cand[k]
pickle.dump(runs, open('runs.pkl', 'wb'))
print('runs', len(runs), 'unlabelled', sum(r['lab'] is None for r in runs))

# 4. columns: model-space outlines + outlines inside big blocks (e.g. canopy columns on pads)
cols = []
def rect(pts, layer):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    wd, ht = max(xs) - min(xs), max(ys) - min(ys)
    if 150 <= wd <= 3000 and 150 <= ht <= 3000 and inw((xs[0], ys[0])):
        cols.append((min(xs), min(ys), max(xs), max(ys), layer))
def walk(e, depth=0):
    if e.dxftype() == 'INSERT' and depth < 4:
        try:
            for ve in e.virtual_entities(): yield from walk(ve, depth + 1)
        except Exception: pass
    else: yield e
for e in msp.query('LWPOLYLINE'):
    if e.dxf.layer in cfg['col_layers']: rect([(p[0], p[1]) for p in e.get_points()], e.dxf.layer)
for e in msp.query('INSERT'):
    b = bbox.extents([e], fast=True)
    # small column blocks (e.g. hatched column inserted on a ...COLS-CONC... layer): use the block extents
    if b.has_data and any(k in e.dxf.layer.upper() for k in cfg.get('col_block_keys', ['COLS-CONC'])) and 150 <= b.size.x <= 3000 and 150 <= b.size.y <= 3000:
        rect([(b.extmin.x, b.extmin.y), (b.extmax.x, b.extmax.y)], e.dxf.layer); continue
    if not b.has_data or b.size.x < 20000 or b.extmax.x < X0 or b.extmin.x > X1 or b.extmax.y < Y0 or b.extmin.y > Y1: continue
    for ve in walk(e):
        if ve.dxftype() == 'LWPOLYLINE' and any(k in ve.dxf.layer.upper() for k in cfg.get('col_keys', ['COL'])):
            rect([(p[0], p[1]) for p in ve.get_points()], ve.dxf.layer)
pickle.dump(cols, open('cols.pkl', 'wb'))
print('columns', len(cols))
