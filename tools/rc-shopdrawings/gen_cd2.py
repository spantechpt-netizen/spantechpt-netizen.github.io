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
    for n, c in (('S-CD-RC', 7), ('S-CD-PC', 8), ('S-CD-COL', 1), ('S-CD-TXT', 3), ('S-CD-SRC', 8), ('S-CD-RED', 1), ('S-CD-CLOSE', 6)):
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


def fit_text(sh, s, x, y, h_max, width, layer, rot=0, align=None, h_min=60):
    """text that stays inside the element: height so the string fits the width (engineer: names inside the footing)."""
    h = max(h_min, min(h_max, width * 0.86 / max(1, len(s) * 0.62)))
    return sh.text(s, x, y, h, layer, align=align or TA.MIDDLE_CENTER, rot=rot), h


def red_mark(sh, Q, p, note, r=900):
    sh.m.add_circle(sh.P(*Q(*p)), r, dxfattribs={'layer': 'S-CD-RED'})
    sh.text(note, *Q(p[0] + r + 150, p[1]), 350, 'S-CD-RED', align=TA.MIDDLE_LEFT, maxw=30000)


def foundations(E, src, flayers, win, meta):
    lines = source_lines(src, set(flayers.split(',')), win)
    xs = [x for p in lines for x, _ in p]; ys = [y for p in lines for _, y in p]
    ext = (min(xs) - 3000, min(ys) - 3000, max(xs) + 3000, max(ys) + 3000)
    doc, sh, Q = setup(meta, 'FOUNDATION CONC DIM\nALL FOOTINGS - ONE PLAN', lines, ext)
    for p in E.get('closures', []):                      # lines added to close the consultant's open outlines
        sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in p], dxfattribs={'layer': 'S-CD-CLOSE', 'const_width': 40})
    els = [(i, Polygon(f['poly']).buffer(0)) for i, f in enumerate(E['footings']) if f['poly']]
    n_dim = 0; done = set()
    for i, g in els:
        f = E['footings'][i]
        lay = 'S-CD-RED' if f.get('red') else 'S-CD-RC'
        sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in g.exterior.coords], dxfattribs={'layer': lay, 'const_width': 40})
        pc = g.buffer(100, join_style=2)
        pl = sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in pc.exterior.coords], dxfattribs={'layer': 'S-CD-PC', 'linetype': 'DASHED'}); pl.dxf.ltscale = 200
        u, v, L, W = axes_of(g)
        c = (g.centroid.x, g.centroid.y) if g.contains(g.centroid) else (g.representative_point().x, g.representative_point().y)
        ang = math.degrees(math.atan2(u[1], u[0]))
        if ang > 90: ang -= 180
        if ang <= -90: ang += 180
        import re as _re
        lw = [int(x) * 10 for x in _re.findall(r'\d+', f['name'])][:2]
        size = (f"{lw[0]}x{lw[1]} h{f['h']}" if f['kind'] == 'F' and len(lw) == 2 else f"h{f['h']}")
        # name + size INSIDE the footing (engineer, 25-10-2026), along its long side
        up = (-math.sin(math.radians(ang)), math.cos(math.radians(ang)))          # the text's own "up" (after the flip)
        _, hn = fit_text(sh, f['name'], *Q(c[0] + up[0] * 60, c[1] + up[1] * 60), 300, L - 200, lay if f.get('red') else 'S-CD-TXT', rot=ang, align=TA.BOTTOM_CENTER)
        fit_text(sh, size, *Q(c[0] - up[0] * 60, c[1] - up[1] * 60), min(200, hn * 0.75), L - 200, 'S-CD-TXT', rot=ang, align=TA.TOP_CENTER)
        if f.get('red') and f.get('note'): red_mark(sh, Q, c, f['note'], r=0)
        # the footing's own dimensions: L along its long side, W along its short side (outside the PC line)
        rr = list(g.minimum_rotated_rectangle.exterior.coords)[:4]
        ed = sorted([(rr[k], rr[(k + 1) % 4]) for k in range(4)], key=lambda e_: -math.dist(*e_))
        for (a_, b_) in (ed[0], ed[2] if math.dist(*ed[2]) < math.dist(*ed[0]) - 1 else ed[1]):
            dl = math.dist(a_, b_)
            if dl < 300: continue
            da = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            if da > 90.01: da -= 180
            if da <= -89.99: da += 180
            mx, my = (a_[0] + b_[0]) / 2 - c[0], (a_[1] + b_[1]) / 2 - c[1]; hm = math.hypot(mx, my) or 1
            base = (a_[0] + mx / hm * 350, a_[1] + my / hm * 350)
            sh.dim(Q(*a_), Q(*b_), Q(*base), angle=da, text=MM(dl)); n_dim += 1
            if f['kind'] == 'F': break                                   # isolated: one side here, the other below
        if f['kind'] == 'F':
            a_, b_ = ed[2] if abs(math.dist(*ed[2]) - math.dist(*ed[0])) > 1 else ed[1]
            dl = math.dist(a_, b_); da = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            if da > 90.01: da -= 180
            if da <= -89.99: da += 180
            mx, my = (a_[0] + b_[0]) / 2 - c[0], (a_[1] + b_[1]) / 2 - c[1]; hm = math.hypot(mx, my) or 1
            sh.dim(Q(*a_), Q(*b_), Q(a_[0] + mx / hm * 350, a_[1] + my / hm * 350), angle=da, text=MM(dl)); n_dim += 1
        # clear distance to the next footing along its own axes (each pair once)
        for d in (u, v, (-u[0], -u[1]), (-v[0], -v[1])):
            e0 = exit_point(g, c, d)
            if e0 is None: continue
            hit = ray_hit(e0, d, els, i, 12000)
            if not hit: continue
            j = next(k for k, gg in els if gg.distance(Point(hit[1])) < 1)
            key = (min(i, j), max(i, j))
            if key in done: continue
            done.add(key)
            gap = hit[0]
            if gap < 50: continue
            da = math.degrees(math.atan2(d[1], d[0]))
            if da > 90.01: da -= 180
            if da <= -89.99: da += 180
            sh.dim(Q(*e0), Q(*hit[1]), Q(*e0), angle=da, text=MM(gap))
            n_dim += 1
    for f in E['footings']:
        if not f['poly']:
            red_mark(sh, Q, f['lab'], f"{f['name']}: {f.get('note', 'NO OUTLINE')}")
    sh.text('FOUNDATION CONC DIM - ALL FOOTINGS  1:200', 2300, 3000, 500, 'S-CD-TXT')
    sh.text('RC FOOTING (THICK) WITH ITS L x W DIMENSIONS / PC = RC + 100 EACH SIDE (DASHED) / CONSULTANT LINE WORK (GREY) / LINES ADDED BY SPAN TECH TO CLOSE '
            'AN OPEN CONSULTANT OUTLINE (MAGENTA) / RED = OUTLINE NOT DEFINED OR IN CONFLICT - SEE THE NOTE AND THE RFI, NOT FOR CONSTRUCTION. '
            'NAMES AS THE REINFORCEMENT SHEETS AND THE BBS. DIMENSIONS BETWEEN FOOTINGS = CLEAR DISTANCE BETWEEN RC FACES ALONG EACH FOOTING\'S OWN AXES (MM). '
            'NO GRID LINES IN THE CONSULTANT DWG (RFI-20).', 2300, 1900, 260, 'S-CD-TXT', maxw=200000)
    doc.saveas('out/CONC_DIM_FOUNDATIONS.dxf')
    return n_dim, meta


def columns(E, src, clayers, win, meta):
    lines = source_lines(src, set(clayers.split(',')), win)
    xs = [x for p in lines for x, _ in p]; ys = [y for p in lines for _, y in p]
    ext = (min(xs) - 3000, min(ys) - 3000, max(xs) + 3000, max(ys) + 3000)
    doc, sh, Q = setup(meta, 'COLUMN CONC DIM\nALL COLUMNS - ONE PLAN', lines, ext)
    cs = [(i, Polygon(c['poly']).buffer(0)) for i, c in enumerate(E['columns']) if c['poly']]
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
        sz = f"D{round(L, -1):.0f}" if c.get('round') else f"{round(W, -1):.0f}x{round(L, -1):.0f}"
        up = (-math.sin(math.radians(ang)), math.cos(math.radians(ang)))
        sh.text(f"{c['name']}  {sz}", *Q(cc[0] - up[0] * (W / 2 + 120), cc[1] - up[1] * (W / 2 + 120)), 220, 'S-CD-TXT', align=TA.TOP_CENTER, rot=ang)
        if c.get('note'): sh.text(c['note'], *Q(cc[0] + up[0] * (W / 2 + 120), cc[1] + up[1] * (W / 2 + 120)), 150, 'S-CD-RED', align=TA.BOTTOM_CENTER, rot=ang)
        # CLEAR distance face to face to the next column along each own axis (engineer, 25-10-2026), close to the columns
        for d in (u, v, (-u[0], -u[1]), (-v[0], -v[1])):
            e0 = exit_point(g, cc, d)
            if e0 is None: continue
            hit = ray_hit(e0, d, cs, i, 12000)
            if not hit: continue
            j = next(k for k, gg in cs if gg.distance(Point(hit[1])) < 1)
            if (min(i, j), max(i, j)) in done: continue
            done.add((min(i, j), max(i, j)))
            da = math.degrees(math.atan2(d[1], d[0]))
            if da > 90.01: da -= 180
            if da <= -89.99: da += 180
            sh.dim(Q(*e0), Q(*hit[1]), Q(*e0), angle=da, text=MM(hit[0]))
            n_dim += 1
    for c in E['columns']:
        if not c['poly']: red_mark(sh, Q, c['lab'], f"{c['name']}: {c.get('note', '')}", r=700)
    sh.text('COLUMN CONC DIM - ALL COLUMNS  1:200', 2300, 3000, 500, 'S-CD-TXT')
    sh.text('COLUMNS HATCHED WITH THE SCHEDULE NAME AND SIZE; DIMENSIONS = CLEAR DISTANCE FACE TO FACE TO THE NEXT COLUMN ALONG ITS OWN AXES (MM). '
            'ROUND COLUMNS WITH THE SCHEDULE DIAMETER (THEATRE COLUMN D800 - DRAWN D400 ON THE CONSULTANT PLAN). RED = OUTLINE NOT DEFINED - SEE RFI-12. '
            'NO GRID LINES IN THE CONSULTANT DWG (RFI-20).', 2300, 1900, 260, 'S-CD-TXT', maxw=200000)
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
