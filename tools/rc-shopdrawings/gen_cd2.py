"""Concrete-dimension plans for a drawing WITHOUT grid lines and with ROTATED elements (generic; gen_cd.py stays the
grid-based Roya version).

    python3 gen_cd2.py cd_elements.json source.dxf "FOOTING_LAYERS" "COLUMN_LAYERS" x0,y0,x1,y1

cd_elements.json (project data, mm): {"footings": [{name, kind F/CF/RAFT (+'?' = no closed outline), poly, h, lab}],
"columns": [{name, size, poly}]}. Two A0 sheets at 1:200 on the project title block:
  out/CONC_DIM_FOUNDATIONS.dxf - every footing (the source line work of the footing layers, so nothing is left out)
      + PC outline (RC + 100, dashed) + name / size / h of each element + CLEAR DISTANCES between neighbouring
      footings, measured along each footing's own axes (aligned dimensions, rotated parts of the building too);
  out/CONC_DIM_COLUMNS.dxf - every column (source line work) hatched, schedule name + size, and the C/C distance to
      the next column along each column's own axes.
Grid lines: none in the source -> the sheets say so (RFI); add axes here when a drawing with grids arrives.
"""
import json, math, sys, logging
import ezdxf
from ezdxf import recover, path as P
from shapely.geometry import Polygon, LineString, Point
from gen import new_doc, Sheet, TA, mm as MM
logging.getLogger('ezdxf').setLevel(logging.ERROR)


class BigSheet(Sheet):
    W, H = 237800, 168200                      # A0 at 1:200
    dimstyle = 'GB200'


def source_lines(src, layers, win):
    doc, _ = recover.readfile(src)
    x0, y0, x1, y1 = win
    out = []
    def walk(e, d=0):
        if e.dxftype() == 'INSERT' and d < 6:
            try:
                for v in e.virtual_entities(): yield from walk(v, d + 1)
            except Exception: pass
        else: yield e
    for top in doc.modelspace():
        for e in walk(top):
            if e.dxf.layer not in layers: continue
            t = e.dxftype()
            try:
                if t == 'LINE': p = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
                elif t in ('LWPOLYLINE', 'ARC', 'CIRCLE', 'POLYLINE', 'ELLIPSE', 'SPLINE'): p = [(v.x, v.y) for v in P.make_path(e).flattening(0.005)]
                else: continue
            except Exception: continue
            if len(p) > 1 and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in p): out.append([(x * 1000, y * 1000) for x, y in p])
    return out


def axes_of(poly):
    """unit vectors along the sides of the minimum rotated rectangle (long side first)."""
    rr = poly.minimum_rotated_rectangle; c = list(rr.exterior.coords)
    a = (c[1][0] - c[0][0], c[1][1] - c[0][1]); b = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    la, lb = math.hypot(*a), math.hypot(*b)
    u = (a[0] / la, a[1] / la); v = (b[0] / lb, b[1] / lb)
    return (u, v, la, lb) if la >= lb else (v, u, lb, la)


def ray_hit(p0, d, polys, skip, maxlen):
    """first polygon (not skip) hit by the ray p0 + t d, t in (0, maxlen] -> (t, point) or None."""
    ln = LineString([p0, (p0[0] + d[0] * maxlen, p0[1] + d[1] * maxlen)])
    best = None
    for i, g in polys:
        if i == skip or not ln.intersects(g): continue
        x = ln.intersection(g)
        pts = [x] if x.geom_type == 'Point' else list(getattr(x, 'geoms', [x]))
        for q in pts:
            for c in (q.coords if q.geom_type != 'Polygon' else q.exterior.coords):
                t = (c[0] - p0[0]) * d[0] + (c[1] - p0[1]) * d[1]
                if t > 1 and (best is None or t < best[0]): best = (t, c)
    return best


def exit_point(g, c, d):
    """where the ray from the centre c along d leaves polygon g."""
    far = (c[0] + d[0] * 1e6, c[1] + d[1] * 1e6)
    x = LineString([c, far]).intersection(g.exterior)
    pts = [x] if x.geom_type == 'Point' else [q for q in getattr(x, 'geoms', []) if q.geom_type == 'Point']
    if not pts: return None
    return max(((q.x, q.y) for q in pts), key=lambda q: (q[0] - c[0]) * d[0] + (q[1] - c[1]) * d[1])


def setup(meta, title, src_lines, ext):
    doc = new_doc()
    if 'GB200' not in doc.dimstyles:
        ds = doc.dimstyles.new('GB200')
        ds.dxf.dimtxt = 2.0; ds.dxf.dimscale = 200; ds.dxf.dimasz = 1.5; ds.dxf.dimexo = 1.0; ds.dxf.dimexe = 1.0
        ds.dxf.dimgap = 0.6; ds.dxf.dimtad = 1; ds.dxf.dimdec = 0; ds.dxf.dimtih = 0; ds.dxf.dimtoh = 0; ds.dxf.dimblk = 'ARCHTICK'
    for n, c in (('S-CD-RC', 7), ('S-CD-PC', 8), ('S-CD-COL', 1), ('S-CD-TXT', 3), ('S-CD-SRC', 8)):
        if n not in doc.layers: doc.layers.add(n, color=c)
    m = dict(meta); m['title'] = title; m['scale'] = '1:200'; m['size'] = 'A0'
    sh = BigSheet(doc, 0, 0, m)
    X0, Y0, X1, Y1 = ext
    ax0, ay0, ax1, ay1 = 2300, 5200, 205500, 165900
    ox = ax0 + (ax1 - ax0 - (X1 - X0)) / 2 - X0; oy = ay0 + (ay1 - ay0 - (Y1 - Y0)) / 2 - Y0
    Q = lambda x, y: (x + ox, y + oy)
    for p in src_lines:
        sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in p], dxfattribs={'layer': 'S-CD-SRC'})
    return doc, sh, Q


def foundations(E, src, flayers, win, meta):
    lines = source_lines(src, set(flayers.split(',')), win)
    xs = [x for p in lines for x, _ in p]; ys = [y for p in lines for _, y in p]
    ext = (min(xs) - 3000, min(ys) - 3000, max(xs) + 3000, max(ys) + 3000)
    doc, sh, Q = setup(meta, 'FOUNDATION CONC DIM\nALL FOOTINGS - ONE PLAN', lines, ext)
    els = [(i, Polygon(f['poly']).buffer(0)) for i, f in enumerate(E['footings']) if f['poly']]
    n_dim = 0; done = set()
    for i, g in els:
        f = E['footings'][i]
        sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in g.exterior.coords], dxfattribs={'layer': 'S-CD-RC', 'const_width': 40})
        pc = g.buffer(100, join_style=2)
        pl = sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in pc.exterior.coords], dxfattribs={'layer': 'S-CD-PC', 'linetype': 'DASHED'}); pl.dxf.ltscale = 200
        u, v, L, W = axes_of(g)
        c = (g.centroid.x, g.centroid.y)
        ang = math.degrees(math.atan2(u[1], u[0]))
        if ang > 90: ang -= 180
        if ang <= -90: ang += 180
        txt = f"{f['name']}" + ("" if f['kind'] == 'F' else '')
        import re as _re
        lw = [int(x) * 10 for x in _re.findall(r'\d+', f['name'])][:2]
        size = (f"{lw[0]}x{lw[1]} h{f['h']}" if f['kind'] == 'F' and len(lw) == 2 else f"h{f['h']}  ({round(L, -1):.0f}x{round(W, -1):.0f} MAX)")
        sh.text(txt, *Q(c[0], c[1] + 160), 300, 'S-CD-TXT', align=TA.BOTTOM_CENTER, rot=ang if W < 1800 else 0)
        sh.text(size, *Q(c[0], c[1] - 60), 200, 'S-CD-TXT', align=TA.TOP_CENTER, rot=ang if W < 1800 else 0)
        # clear distance to the next footing along +u and +v (each pair once: the neighbour does - u / - v)
        for d in (u, v, (-u[0], -u[1]), (-v[0], -v[1])):
            e0 = exit_point(g, c, d)
            if e0 is None: continue
            hit = ray_hit(e0, d, els, i, 12000)
            if not hit: continue
            j = next(k for k, gg in els if gg.distance(Point(hit[1])) < 1)
            key = (min(i, j), max(i, j))
            if key in done: continue                                  # each pair once
            done.add(key)
            gap = hit[0]
            if gap < 50: continue
            da = math.degrees(math.atan2(d[1], d[0]))
            if da > 90.01: da -= 180
            if da <= -89.99: da += 180                                 # dimension text always readable
            r = sh.dim(Q(*e0), Q(*hit[1]), Q(*e0), angle=da, text=MM(gap))
            n_dim += 1
    for f in E['footings']:
        if not f['poly']:
            sh.text(f['name'] + ' (!)', *Q(*f['lab']), 260, 'S-CD-TXT', align=TA.MIDDLE_CENTER)
    sh.text('FOUNDATION CONC DIM - ALL FOOTINGS  1:200', 2300, 3000, 500, 'S-CD-TXT')
    sh.text('RC FOOTING (THICK) / PC = RC + 100 EACH SIDE (DASHED) / CONSULTANT LINE WORK (GREY). NAMES AS THE REINFORCEMENT SHEETS AND THE BBS. '
            'DIMENSIONS = CLEAR DISTANCE BETWEEN RC FACES ALONG EACH FOOTING\'S OWN AXES (MM). (!) = NO CLOSED OUTLINE ON THE CONSULTANT PLAN - SEE RFI. '
            'NO GRID LINES IN THE CONSULTANT DWG: POSITIONS FROM THE GRIDS PENDING RFI.', 2300, 1900, 260, 'S-CD-TXT', maxw=200000)
    doc.saveas('out/CONC_DIM_FOUNDATIONS.dxf')
    return n_dim, meta


def columns(E, src, clayers, win, meta):
    lines = source_lines(src, set(clayers.split(',')), win)
    xs = [x for p in lines for x, _ in p]; ys = [y for p in lines for _, y in p]
    ext = (min(xs) - 3000, min(ys) - 3000, max(xs) + 3000, max(ys) + 3000)
    doc, sh, Q = setup(meta, 'COLUMN CONC DIM\nALL COLUMNS - ONE PLAN', lines, ext)
    cs = [(i, Polygon(c['poly']).buffer(0)) for i, c in enumerate(E['columns'])]
    n_dim = 0; done = set()
    for i, g in cs:
        c = E['columns'][i]
        h = sh.m.add_hatch(color=1, dxfattribs={'layer': 'S-CD-COL'}); h.set_pattern_fill('ANSI31', scale=20)
        h.paths.add_polyline_path([sh.P(*Q(*q)) for q in list(g.exterior.coords)[:-1]], is_closed=True)
        sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in g.exterior.coords], dxfattribs={'layer': 'S-CD-RC', 'const_width': 30})
        u, v, L, W = axes_of(g)
        cc = (g.centroid.x, g.centroid.y)
        ang = math.degrees(math.atan2(u[1], u[0]))
        if ang > 90: ang -= 180
        if ang <= -90: ang += 180
        sh.text(f"{c['name']}", *Q(cc[0] - v[0] * (W / 2 + 120), cc[1] - v[1] * (W / 2 + 120)), 300, 'S-CD-TXT', align=TA.TOP_CENTER, rot=ang)
        # C/C to the next column along each own axis (lateral offset <= 600, within 12 m)
        for d in (u, v):
            best = None
            for j, gg in cs:
                if j == i: continue
                q = (gg.centroid.x - cc[0], gg.centroid.y - cc[1])
                t = q[0] * d[0] + q[1] * d[1]; off = abs(q[0] * -d[1] + q[1] * d[0])
                if 300 < t < 12000 and off < 600 and (best is None or t < best[0]): best = (t, (gg.centroid.x, gg.centroid.y), j)
            if best and (min(i, best[2]), max(i, best[2])) in done: best = None    # each pair once
            if best:
                done.add((min(i, best[2]), max(i, best[2])))
                da = math.degrees(math.atan2(d[1], d[0]))
                if da > 90.01: da -= 180
                if da <= -89.99: da += 180
                p1 = (cc[0] + d[0] * best[0], cc[1] + d[1] * best[0])
                sh.dim(Q(*cc), Q(*p1), Q(cc[0] - d[1] * 700, cc[1] + d[0] * 700), angle=da, text=MM(best[0]))
                n_dim += 1
    sh.text('COLUMN CONC DIM - ALL COLUMNS  1:200', 2300, 3000, 500, 'S-CD-TXT')
    sh.text('COLUMNS HATCHED WITH THE SCHEDULE NAME; DIMENSIONS = C/C DISTANCE TO THE NEXT COLUMN ALONG ITS OWN AXES (MM). SIZES PER THE COLUMN SCHEDULE. '
            'NO GRID LINES IN THE CONSULTANT DWG: POSITIONS FROM THE GRIDS PENDING RFI. "?" = NO SCHEDULE TYPE - SEE RFI.', 2300, 1900, 260, 'S-CD-TXT', maxw=200000)
    doc.saveas('out/CONC_DIM_COLUMNS.dxf')
    return n_dim


if __name__ == '__main__':
    E = json.load(open(sys.argv[1]))
    src, fl, cl, win = sys.argv[2], sys.argv[3], sys.argv[4], [float(v) for v in sys.argv[5].split(',')]
    PRJ = json.load(open('project.json'))
    meta = dict(PRJ.get('meta', {}))
    n1, _ = foundations(E, src, fl, win, meta)
    n2 = columns(E, src, cl, win, meta)
    print('foundations dims', n1, '| columns dims', n2)
