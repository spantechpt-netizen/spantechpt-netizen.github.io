# Roya Zone 7 GB plans: beams (pairs of edges), columns, labels, levels, dims per plan window
import pickle, math, collections, json, sys
import ezdxf, logging
from shapely.geometry import LineString, Polygon, Point, box
from shapely.ops import unary_union, polygonize
logging.getLogger('ezdxf').setLevel(logging.ERROR)
W_ = sys.argv[1]
G = pickle.load(open(W_ + '/geo.pkl', 'rb')); T = pickle.load(open(W_ + '/texts.pkl', 'rb'))
PLANS = {'P1': (224000, 116000, 256000, 162000), 'P2': (224000, 65700, 256000, 112000), 'P3': (224000, 12300, 256000, 58600)}
import os
COL_LAYERS = os.environ.get('COL_LAYERS', 'CORE-COLS-CONC').split(',')         # extra column layers (e.g. 'COLUMN MAIN')
BEAM_LAYERS = os.environ.get('BEAM_LAYERS', 'CORE-FNDN-GRBM').split(',')     # extra edge layers (e.g. '1-slab edge')
if os.environ.get('PLANS_JSON'): PLANS = {k: tuple(v) for k, v in json.loads(os.environ['PLANS_JSON']).items()}   # other areas: plan windows
doc = ezdxf.readfile(sys.argv[2]); msp = doc.modelspace()
lv = []
for e in msp.query('INSERT'):
    if e.dxf.name == 'A-LV-P':
        att = ' '.join(a.dxf.text for a in e.attribs)
        lv.append((e.dxf.insert.x, e.dxf.insert.y, att))
dims = []
for e in msp.query('DIMENSION'):
    try:
        p1, p2 = e.dxf.defpoint2, e.dxf.defpoint3
        dims.append(((p1.x, p1.y), (p2.x, p2.y), round(e.get_measurement()), e.dxf.text))
    except Exception: pass
out = {}
for nm, (x0, y0, x1, y1) in PLANS.items():
    W = box(x0, y0, x1, y1)
    L = []                                                              # polylines exploded into their segments (L-shaped edges)
    for g in G:
        if g[0] not in BEAM_LAYERS: continue
        for p_, q_ in zip(g[2], g[2][1:]):
            if p_ != q_ and W.contains(LineString([p_, q_]).centroid): L.append(LineString([p_, q_]))
    segs = []
    for i, a in enumerate(L):
        (ax0, ay0), (ax1, ay1) = a.coords[0], a.coords[-1]
        hor = abs(ay1 - ay0) < 5; ver = abs(ax1 - ax0) < 5
        if not (hor or ver): continue
        for b in L[i + 1:]:
            (bx0, by0), (bx1, by1) = b.coords[0], b.coords[-1]
            if hor and abs(by1 - by0) < 5:
                w = abs(by0 - ay0); lo, hi = max(min(ax0, ax1), min(bx0, bx1)), min(max(ax0, ax1), max(bx0, bx1))
                if 150 <= w <= 450 and hi - lo > 100:
                    segs.append(dict(o='H', c=(ay0 + by0) / 2, w=round(w), a=lo, b=hi))
            if ver and abs(bx1 - bx0) < 5:
                w = abs(bx0 - ax0); lo, hi = max(min(ay0, ay1), min(by0, by1)), min(max(ay0, ay1), max(by0, by1))
                if 150 <= w <= 450 and hi - lo > 100:
                    segs.append(dict(o='V', c=(ax0 + bx0) / 2, w=round(w), a=lo, b=hi))
    keep = []
    for s in segs:
        inner = [t for t in segs if t is not s and t['o'] == s['o'] and abs(t['c'] - s['c']) < s['w'] / 2 - 10 and t['w'] < s['w'] and min(t['b'], s['b']) - max(t['a'], s['a']) > 100]
        if not inner: keep.append(s)
    cols = []
    for g in G:
        if g[0] in COL_LAYERS and g[1] == 'LWPOLYLINE' and len(g[2]) >= 4:
            p = Polygon(g[2]).buffer(0)
            if W.contains(p.centroid) and p.area > 3e4: cols.append(p)
    cl = [L_ for L_ in [LineString(g[2]) for g in G if g[0] in COL_LAYERS and g[1] == 'LINE'] if W.contains(L_.centroid)]
    for f in polygonize(unary_union(cl)):
        if f.area > 3e4 and not any(c.intersects(f.buffer(-5)) for c in cols): cols.append(f)
    ded = []
    for c in sorted(cols, key=lambda c: -c.area):
        if not any(o.contains(c.buffer(-5)) or o.symmetric_difference(c).area < 0.05 * c.area for o in ded): ded.append(c)
    cols = ded
    labs = [(t[0].strip(), t[1], t[2]) for t in T if t[3] == '$0$CORE-COLS-IDEN' and W.contains(Point(t[1], t[2]))]
    out[nm] = dict(segs=keep, cols=[list(c.exterior.coords) for c in cols], labs=labs,
                   levels=[l for l in lv if W.contains(Point(l[0], l[1]))],
                   dims=[d for d in dims if W.contains(Point(d[0])) and W.contains(Point(d[1]))])
    print(nm, 'beam segs', len(keep), collections.Counter(s['w'] for s in keep), 'cols', len(cols), 'labels', collections.Counter(l[0] for l in labs), 'levels', out[nm]['levels'])
pickle.dump(out, open(W_ + '/plans.pkl', 'wb'))
