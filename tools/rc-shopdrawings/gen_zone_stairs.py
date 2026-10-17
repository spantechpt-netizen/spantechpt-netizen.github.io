"""Stair starter bars per zone (engineer, Oct 2026): every stair starter drawn on the plans (outline + its bars) -> the
footing under it on the final plan -> one sheet per (stair starter, footing) like the column necks: STARTER bars from
the footing (foot on the bottom mesh, full Ld in the footing, + lap above T.O.F) and straight bars from T.O.F to
T.O.GB + lap (none where T.O.F = T.O.GB: starters only), ties through the footing and the stub.
project.json "stairs": {dxf, outline_layer, bar_layer, size [b, h] of the outline, to_work [dx, dy] (drawing ->
working coordinates), plans [{y_min | y_max, shift [dx, dy] onto the foundation plan}], name, b, h, d, tie [d, s]}
usage: python3 gen_zone_stairs.py [AREA 2 ...]   -> out/ZONES/AREA_n_STAIRS.dxf (sheets numbered from seq_start SC)"""
import sys, collections, logging
logging.getLogger('ezdxf').setLevel(logging.ERROR)
from ezdxf import recover
import zone_util as Z
import gen_n
from gen import new_doc, seq_zone, seq_save, seq_none, BarList, draw_bbs

C = Z.PRJ['stairs']
doc_, _ = recover.readfile(C['dxf'])


def walk(e, d=0):
    if e.dxftype() == 'INSERT' and d < 5:
        try:
            for v in e.virtual_entities(): yield from walk(v, d + 1)
        except Exception: pass
    else: yield e


rects, dots = set(), []
for top in doc_.modelspace():
    for e in walk(top):
        t = e.dxftype()
        if t == 'LWPOLYLINE' and e.closed and e.dxf.layer == C['outline_layer']:
            p = [q[:2] for q in e.get_points()]; xs = [a for a, b in p]; ys = [b for a, b in p]
            if sorted((round(max(xs) - min(xs)), round(max(ys) - min(ys)))) == sorted(C['size']):
                rects.add((round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))))
        elif t == 'CIRCLE' and e.dxf.layer == C['bar_layer']:
            dots.append((e.dxf.center.x, e.dxf.center.y))


def to_work(x, y):
    for pl in C['plans']:
        if ('y_min' in pl and y >= pl['y_min']) or ('y_max' in pl and y < pl['y_max']):
            x, y = x + pl['shift'][0], y + pl['shift'][1]; break
    return x + C['to_work'][0], y + C['to_work'][1]


found = []
for r in sorted(rects):
    nb = sum(1 for x, y in dots if r[0] <= x <= r[2] and r[1] <= y <= r[3])
    cx, cy = to_work((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
    kind, fn, _ = Z.footing_at(cx, cy)
    flag = None
    if fn is None:                                   # just off a footing outline: the nearest within 1 m, flagged
        from shapely.geometry import Point
        E, _c = Z.els()
        near = sorted((e['rc'].distance(Point(cx, cy)), e) for e in E if e.get('lab') and e['kind'] in ('F', 'M'))
        if near and near[0][0] < 1000:
            e = near[0][1]; flag = round(near[0][0])
            from shapely.ops import nearest_points
            q = nearest_points(e['rc'].buffer(-30), Point(cx, cy))[0]          # just inside that footing: its type
            fn = Z.footing_at(q.x, q.y)[1] or e['lab']
    found.append(dict(r=r, n=nb, c=(round(cx), round(cy)), fn=fn, zone=Z.zone_of(cx, cy), flag=flag))
for s in found: print('stair starter', s)
pairs = collections.defaultdict(collections.Counter); lost = []
for s in found:
    if s['fn'] is None: lost.append(s); continue
    pairs[s['zone']][(s['n'], s['fn'])] += 1


def stair_col(n):
    b, h, d = C['b'], C['h'], C['d']
    dots = [(round(i * (h - 2 * 70) / (n - 1), 1), 0.0) for i in range(n)]       # one row on the centre line
    tie = [(-60, -110), (h - 140 + 60, -110), (h - 140 + 60, 110), (-60, 110)]
    return dict(name=C.get('name', 'STAIR STARTER'), b=b, h=h, dw=h, dh=b, n=n, d=d, sets=1, per_m=1000 / C['tie'][1],
                dots=dots, dots_raw=dots, tieset=[dict(poly=tie)], shapes=[], ties=[], b_draw=h, h_draw=b,
                perimeter_tie=True, title_prefix='', elev_title='ELEVATION  (STAIR STARTER: STARTERS FROM THE FOOTING + BARS TO T.O.GB + LAP)')


L = Z.lib()
for zn in (sys.argv[1:] or Z.NAMES):
    if not pairs[zn]: seq_none('STAIRS', zn); continue
    gen_n.ZONE = zn
    from gen import zone_levels
    doc = new_doc(); bl = BarList(); i = 0
    seq_zone(doc, zn, 'STAIRS', Z.NAMES)
    for (n, fn), no in sorted(pairs[zn].items()):
        f = dict(L[fn]); f.setdefault('name', fn)
        col = stair_col(n)
        meta = Z.base_meta(zn, 'SDW-STR-STR', 'ELEV 1:25 / SEC 1:10', 'STAIR STARTERS: Ld IN THE FOOTING >= 60d (STRAIGHT + FOOT); LAP 65d.')
        meta['venue'] = 'SC'; meta['title'] = f'STAIR STARTER BARS - {zn}\nON {fn}'
        gen_n.draw_neck(doc, i, col, f, meta, bl, int(no)); i += 1
    meta = Z.base_meta(zn, 'SDW-STR-STR'); meta['venue'] = 'SC'; meta['title'] = f'STAIR STARTER BARS - {zn}\nBBS'
    nbb = draw_bbs(doc, i, bl.sorted(), meta)
    seq_save(doc)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_STAIRS.dxf")
    print(zn, dict(pairs[zn]), 'sheets', i, '+ BBS', nbb)
if lost: print('stair starters on no footing of the final plan:', [(s['c'], s['zone']) for s in lost])
print('attached to the nearest footing (mm off its outline - check):', [(s['zone'], s['fn'], s['flag'], s['c']) for s in found if s['flag'] is not None])
