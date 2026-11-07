"""Raft of ANY outline (curved, stepped) with an orthogonal mesh at ANY angle - one A0 sheet per mesh layer.

Engineer (BLSC theatre raft, Nov 2026):
  * five separate plans: BOTTOM X, BOTTOM Y, TOP X, TOP Y, CHAIRS LAYOUT; then SECTIONS & DETAILS; then the BBS.
  * every bar row at its REAL length (cut by the real outline at the cover, no unified lengths); identical bars share
    a mark, every other bar its own mark; a call-out ON every bar: mark (hexagon), number, diameter, length, spacing,
    layer. Short bars: the call-out beyond the bar end, on its own line.
  * laps 60d staggered (alternate rows A / B): bottom mesh at midspan, top mesh at the supports (+/- span / 5),
    supports = the columns (projected on each axis); zones hatched only where bars are lapped.
  * U legs at both ends (raft.json leg), side bars along the real perimeter, chairs 1 / m2 standing on the bottom mesh.
  * the engineer's title block (project.json title_block) at the sheet scale of his sample (A0, 1:200 units).
raft.json (project data, never in the repository): name, no, h, cover, leg, angle (deg, X direction), poly (outline,
mm), cols [[x, y, r]], bot / top {dx, sx, dy, sy}, side {d, s, rows}, chair {d, per_m2, foot, top}, lap_d, stock,
levels {tor, bor}, scale (plan, default 30), title1, ref.
usage: RC_PROJECT=project.json python3 gen_raft.py raft.json OUT_PREFIX   -> OUT.dxf, OUT.sheets.json, OUT.bbs.json, OUT.report.txt
"""
import json, math, os, sys
from shapely.geometry import Polygon, LineString, Point, box
from shapely.affinity import rotate as srot
import gen
from gen import new_doc, Sheet, TA, callout, BarList, lap_patterns_zoned, lap_patterns, piece_shape, draw_bbs_grouped, unit_mass
from gen_mat import side_pieces

SC = 200                                      # sheet units per paper mm (A0 = 237800 x 168200)
HC = 330                                      # call-out text on the bars (1.65 mm)
HN = 420                                      # notes
HP = 760                                      # panel titles
HS = 300                                      # small (dims, labels)


class A0(Sheet):
    W, H = 237800, 168200
    dimstyle = 'GB200'


def dimstyle(doc):
    if 'GB200' not in doc.dimstyles:
        ds = doc.dimstyles.duplicate_entry('GB100', 'GB200'); ds.dxf.dimscale = 200; ds.dxf.dimtxsty = 'ROMANS'


class Raft:
    def __init__(self, f):
        self.f = f
        self.th = math.radians(f['angle'])
        c, s = math.cos(self.th), math.sin(self.th)
        self.G = lambda u, v: (u * c - v * s, u * s + v * c)            # local -> global (drawing) mm
        self.Lc = lambda x, y: (x * c + y * s, -x * s + y * c)          # global -> local
        self.poly = [tuple(p) for p in f['poly']]
        self.pl = Polygon([self.Lc(*p) for p in self.poly])
        self.C = f['cover']; self.h = f['h']; self.lg = f['leg']
        self.er = self.pl.buffer(-self.C, join_style=2)
        # columns / walls: [x, y, r] (round) or {"poly": [[x, y], ...]} (any shape, global mm) -> local polygons
        self.colp = []
        for c_ in f['cols']:
            if isinstance(c_, dict): self.colp.append(Polygon([self.Lc(*q) for q in c_['poly']]))
            else: self.colp.append(Point(self.Lc(c_[0], c_[1])).buffer(c_[2], 36))
        self.cols = [((g.centroid.x, g.centroid.y), max(math.dist((g.centroid.x, g.centroid.y), q) for q in g.exterior.coords)) for g in self.colp]
        self.stock = f.get('stock', 12000)

    def supports(self, axis):
        vals = sorted(p[0] if axis == 'X' else p[1] for p, r in self.cols)
        out = []
        for v in vals:                                                    # columns within 1 m = one support line
            if out and v - out[-1][-1] <= 1000: out[-1].append(v)
            else: out.append([v])
        return [sum(g) / len(g) for g in out]

    def zones(self, layer, axis):
        sup = self.supports(axis); z = []
        if layer == 'B':
            for a, b in zip(sup, sup[1:]):
                sp = b - a; m = (a + b) / 2; z.append((m - sp / 5, m + sp / 5))
        else:
            for i, s_ in enumerate(sup):
                sp = min(([sup[i + 1] - s_] if i + 1 < len(sup) else []) + ([s_ - sup[i - 1]] if i else []))
                z.append((s_ - sp / 5, s_ + sp / 5))
        return z

    def cut(self, t, axis):
        x0, y0, x1, y1 = self.er.bounds
        ln = LineString([(x0 - 10, t), (x1 + 10, t)]) if axis == 'X' else LineString([(t, y0 - 10), (t, y1 + 10)])
        g = self.er.intersection(ln); out = []
        for q in getattr(g, 'geoms', [g]):
            if q.is_empty or q.length < 300: continue
            b = q.bounds
            out.append((b[0], b[2]) if axis == 'X' else (b[1], b[3]))
        return sorted(out)

    def rows(self, axis, s):
        x0, y0, x1, y1 = self.er.bounds
        lo, hi = (y0, y1) if axis == 'X' else (x0, x1)
        n = math.ceil((hi - lo) / s) + 1; step = (hi - lo) / (n - 1)
        return [(i, lo + i * step, self.cut(lo + i * step, axis)) for i in range(n)], step


def chair_points(R, sp, foot, top, best=False):
    """chairs on a sp x sp grid along the mesh axes, the whole chair inside the cover line, >= 200 from columns.
    best: the grid shifted (quarter steps) to hold the most chairs (irregular / sloped footings)."""
    x0, y0, x1, y1 = R.er.bounds
    half = (2 * foot + top) / 2
    inner = R.er.buffer(-20)
    def grid(ox, oy):
        pts = []
        for i in range(-1, int((x1 - x0) // sp) + 2):
            for j in range(-1, int((y1 - y0) // sp) + 2):
                u, v = x0 + ox + i * sp, y0 + oy + j * sp
                if inner.contains(LineString([(u - half, v), (u + half, v)])) and all(g.distance(Point(u, v)) > 200 for g in R.colp):
                    pts.append((u, v))
        return pts
    if not best: return grid(sp / 2, sp / 2)
    return max((grid(ox, oy) for ox in (0, sp / 4, sp / 2, 3 * sp / 4) for oy in (0, sp / 4, sp / 2, 3 * sp / 4)), key=len)


def chairs_plan(sh, R, f, chair, area):
    """chairs layout as a small plan inside area (sheet units) - used on the sections sheet of straight-edged footings."""
    mkch, nch, chL, ch_h, foot, top, dch, sp = chair
    pts = chair_points(R, sp, foot, top, best=bool(f.get('chairs_best')))
    gx0, gy0, gx1, gy1 = Polygon(R.poly).bounds
    ax0, ay0, ax1, ay1 = area
    sc_ = next(v for v in (20, 25, 30, 40, 50, 75, 100, 125, 150, 200, 250) if (gx1 - gx0) * SC / v <= ax1 - ax0 - 2000 and (gy1 - gy0) * SC / v <= ay1 - ay0 - 6000)
    P = Plan(sh, R, SC / sc_, ax0 + 1000, ay0 + 3500, gx0, gy0)
    P.outline()
    for u, v in pts:
        sh.pline([P.SL(u - top / 2, v), P.SL(u + top / 2, v)], 'S-RFT-STIR', 60)
        for uu in (u - top / 2, u + top / 2):
            c_ = P.SL(uu, v)
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*c_), 70, 0, 360)
    if pts:
        topc = max(pts, key=lambda q: (q[1], -q[0])); cp = P.SL(*topc)
        lx, ly = ax0 + 1000, P.S(gx0, gy1)[1] + 1500
        sh.line(cp, (lx + 4000, ly - 100), 'S-RFT-TXT')
        P.ctext_along(mkch, callout(len(pts), dch, mkch, chL, sp, 'CH') + '  (DETAIL 4)', (lx, ly), 0, gap=0)
    sh.text(f"CHAIRS LAYOUT - {len(pts)} CHAIRS T{dch} @{sp} x {sp} ALONG X / Y  SCALE 1:{sc_}", ax0, ay0 + 1500, HP * 0.8, 'S-SEC', maxw=ax1 - ax0)
    sh.text(f"THICK LINE = CHAIR TOP {top}, DOTS = ITS LEGS; INSIDE THE COVER LINE, >= 200 FROM THE COLUMNS.", ax0, ay0 + 300, HN, 'S-RFT-TXT', maxw=ax1 - ax0)


def build_bars(R, bl, layer, axis, d, s, tag, report, alt=False):
    """every row of this mesh layer: real straight length (floor 10, centred), U legs, laps zoned + staggered."""
    rows, step = R.rows(axis, s)
    lp = R.f.get('lap_d', 60) * d; lg = R.lg
    zon_plan = R.zones(layer, axis)
    bars = []; k_lap = 0; warn = 0
    for i, t, segs in rows:
        for j, (a, b) in enumerate(segs):
            st = int(math.floor((b - a) / 10) * 10); m = (a + b) / 2
            a2, b2 = m - st / 2, m + st / 2
            T = st + 2 * lg
            pats = [[(0, T)]]
            if T > R.stock:
                zon = [(lg + max(z0, a2) - a2, lg + min(z1, b2) - a2) for z0, z1 in zon_plan if min(z1, b2) > max(z0, a2)]
                pz = lap_patterns_zoned(T, lp, zon, R.stock) if zon else None
                if pz is None:
                    pz = lap_patterns(T, lp, R.stock); warn += 1
                    report.append(f'{layer}{axis} row {i + 1}: laps cannot all sit in the zones (T={T}) - equal staggered pieces (CHECK)')
                pats = pz
            pat = pats[k_lap % len(pats)] if len(pats) > 1 else pats[0]
            if len(pats) > 1: k_lap += 1
            pcs = []
            for t0, t1 in pat:
                shp, L = piece_shape(t0, t1, T, lg, lg)
                mk = bl.add(d, shp, L, 1, 1, tag)
                pcs.append(dict(t0=t0, t1=t1, L=L, shp=shp, mark=mk, u0=a2 + max(0, t0 - lg), u1=a2 + min(st, t1 - lg)))
            bars.append(dict(row=i, t=t, a=a2, b=b2, st=st, T=T, pcs=pcs, lapped=len(pat) > 1, seg=j))
    # consecutive rows with the same pieces (marks and ends within 15 mm) -> one call-out group
    groups = []
    for br in bars:
        g = groups[-1] if groups else None
        if alt:                                                      # rows split by a notch: follow each part separately
            g = next((q for q in reversed(groups) if q[-1]['row'] == br['row'] - 1
                      and abs(q[-1]['a'] - br['a']) <= 15 and abs(q[-1]['b'] - br['b']) <= 15), g)
        same = (g and g[-1]['seg'] == br['seg'] and br['row'] == g[-1]['row'] + 1 and len(g[-1]['pcs']) == len(br['pcs'])
                and all(p['mark'] == q['mark'] and abs(p['u0'] - q['u0']) <= 15 for p, q in zip(g[-1]['pcs'], br['pcs'])))
        if alt and g and not same:                                   # alt: same bar (ends within 15), lap pattern A / B alternating
            same = (br['row'] == g[-1]['row'] + 1 and g[-1]['lapped'] == br['lapped'] and len(g[-1]['pcs']) == len(br['pcs'])
                    and abs(g[-1]['a'] - br['a']) <= 15 and abs(g[-1]['b'] - br['b']) <= 15)
        if same:
            g.append(br)
        else:
            groups.append([br])
    return dict(bars=bars, groups=groups, step=step, lp=lp, zones=zon_plan, warn=warn, d=d, s=s, tag=tag, layer=layer, axis=axis)


class Plan:
    """drawing of the raft on a sheet: global mm -> sheet units."""
    def __init__(self, sh, R, k, ox, oy, gx0, gy0):
        self.sh, self.R, self.k, self.ox, self.oy, self.gx0, self.gy0 = sh, R, k, ox, oy, gx0, gy0
        self.boxes = []                                             # placed text boxes (sheet coords, shapely)

    def S(self, x, y): return (self.ox + (x - self.gx0) * self.k, self.oy + (y - self.gy0) * self.k)
    def SL(self, u, v): return self.S(*self.R.G(u, v))

    def outline(self, layer='S-GB-CONC'):
        self.sh.pline([self.S(*p) for p in self.R.poly], layer, 0, True)
        for g in self.R.colp:
            pts = [self.SL(*q) for q in list(g.exterior.coords)[:-1]]
            hz = self.sh.m.add_hatch(color=8, dxfattribs={'layer': 'S-GB-COL'}); hz.set_pattern_fill('ANSI31', scale=90)
            hz.paths.add_polyline_path([self.sh.P(*q) for q in pts], is_closed=True)
            self.sh.pline(pts, 'S-GB-COL', 0, True)
            self.boxes.append(Polygon(pts).buffer(80))

    def edge_dims(self):
        """straight edges: length written outside; the curved edge: its radius."""
        R = self.R; P = R.poly; pg = Polygon(P); n = len(P)
        for i in range(n):
            a, b = P[i], P[(i + 1) % n]; Ls = math.dist(a, b)
            if Ls < 900: continue
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            nx, ny = (b[1] - a[1]) / Ls, -(b[0] - a[0]) / Ls
            if pg.contains(Point(mx + nx * 50, my + ny * 50)): nx, ny = -nx, -ny
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if ang > 90.5 or ang <= -89.5: ang += 180
            x, y = self.S(mx, my)
            self.sh.text(str(int(round(Ls))), x + nx * 700, y + ny * 700, HS * 1.3, 'S-DIM', rot=ang, align=TA.MIDDLE_CENTER)
        arc = R.f.get('arc')
        if arc:
            cx, cy, rr, (mx, my) = arc['c'][0], arc['c'][1], arc['r'], arc['mid']
            ux, uy = (mx - cx) / rr, (my - cy) / rr
            x, y = self.S(mx + ux * 900, my + uy * 900)
            self.sh.text(f'CURVED EDGE R = {int(round(rr))}', x, y, HS * 1.4, 'S-DIM',
                         rot=math.degrees(math.atan2(uy, ux)) - 90, align=TA.MIDDLE_CENTER)

    def axes_symbol(self, x, y):
        """mesh directions X / Y (local axes) at sheet point x, y."""
        th = self.R.th; L = 4500
        for ang, lab in ((th, 'X'), (th + math.pi / 2, 'Y')):
            ex, ey = math.cos(ang), math.sin(ang)
            self.sh.line((x, y), (x + ex * L, y + ey * L), 'S-DIM')
            for s_ in (1, -1):
                a2 = ang + math.pi + s_ * 0.35
                self.sh.line((x + ex * L, y + ey * L), (x + ex * L + math.cos(a2) * 600, y + ey * L + math.sin(a2) * 600), 'S-DIM')
            self.sh.text(lab, x + ex * (L + 700), y + ey * (L + 700), 600, 'S-DIM', align=TA.MIDDLE_CENTER)
        self.sh.text(f'X = {self.R.f["angle"]:.3f}°', x + 600, y - 900, HS * 1.3, 'S-DIM')

    def text_box(self, p, e, n, Lt, hh):
        """box of a text of length Lt starting at sheet point p along unit e, height hh on side n."""
        q = [p, (p[0] + e[0] * Lt, p[1] + e[1] * Lt), (p[0] + e[0] * Lt + n[0] * hh, p[1] + e[1] * Lt + n[1] * hh), (p[0] + n[0] * hh, p[1] + n[1] * hh)]
        return Polygon(q)

    def ctext_along(self, mk, s, p, ang, h=HC, layer='S-RFT-TXT', gap=110):
        """hexagon + call-out along a bar: p = sheet point on the bar where the hexagon starts, text on the +n side."""
        e = (math.cos(ang), math.sin(ang)); n = (-e[1], e[0])
        Rr = h * 1.1; hy = Rr * math.sin(math.pi / 3)
        c = (p[0] + e[0] * Rr + n[0] * (gap + hy), p[1] + e[1] * Rr + n[1] * (gap + hy))
        self.sh.pline([(c[0] + Rr * math.cos(ang + math.pi / 3 * j), c[1] + Rr * math.sin(ang + math.pi / 3 * j)) for j in range(6)], layer, 0, True)
        self.sh.text(f'{int(mk):02d}', c[0], c[1], h * (0.75 if int(mk) < 100 else 0.6), layer, rot=math.degrees(ang), align=TA.MIDDLE_CENTER)
        q = (p[0] + e[0] * (2 * Rr + h * 0.35) + n[0] * (gap + hy - h / 2), p[1] + e[1] * (2 * Rr + h * 0.35) + n[1] * (gap + hy - h / 2))
        self.sh.text(s, q[0], q[1], h, layer, rot=math.degrees(ang))

    def text_len(self, s, h=HC):
        return 2 * h * 1.1 + h * 0.35 + len(s) * h * 0.78


def draw_mesh_plan(sh, P, M, R):
    """one mesh layer (B/T) in one direction: zones, every bar, call-outs on the bars, distribution of groups."""
    axis, layer, d, s, tag = M['axis'], M['layer'], M['d'], M['s'], M['tag']
    lay = 'S-RFT-BOT' if layer == 'B' else 'S-RFT-TOP'
    ang = R.th + (0 if axis == 'X' else math.pi / 2)
    e = (math.cos(ang), math.sin(ang)); nrm = (-e[1], e[0])
    k = P.k
    Q = (lambda u, t: P.SL(u, t)) if axis == 'X' else (lambda u, t: P.SL(t, u))
    # lap zones (hatched) only where bars of this plan are lapped
    lapped_u = [(p['u1'] - M['lp'], p['u1']) for br in M['bars'] for p in br['pcs'][:-1]]
    x0, y0, x1, y1 = R.pl.bounds
    for z0, z1 in M['zones']:
        if not any(z0 - 5 <= (a + b) / 2 <= z1 + 5 for a, b in lapped_u): continue
        band = box(z0, y0 - 10, z1, y1 + 10) if axis == 'X' else box(x0 - 10, z0, x1 + 10, z1)
        cl = band.intersection(R.pl)
        for q in getattr(cl, 'geoms', [cl]):
            if q.is_empty or q.geom_type != 'Polygon' or q.area < 1e4: continue
            hz = sh.m.add_hatch(color=8, dxfattribs={'layer': 'S-DIM'}); hz.set_pattern_fill('ANSI31', scale=320)
            hz.paths.add_polyline_path([sh.P(*P.SL(*c)) for c in list(q.exterior.coords)[:-1]], is_closed=True)
    off = 18 * k                                                     # lapped piece drawn 18 mm aside
    for br in M['bars']:
        t = br['t']
        for j, p in enumerate(br['pcs']):
            dv = -off if j % 2 else 0
            a_, b_ = Q(p['u0'], t), Q(p['u1'], t)
            a_ = (a_[0] + nrm[0] * dv, a_[1] + nrm[1] * dv); b_ = (b_[0] + nrm[0] * dv, b_[1] + nrm[1] * dv)
            sh.pline([a_, b_], lay, 55)
            if j:                                                    # lap: small circles at both ends of the overlap
                for uu in (p['u0'], br['pcs'][j - 1]['u1']):
                    c_ = Q(uu, t); sh.circle(c_[0] - nrm[0] * off / 2, c_[1] - nrm[1] * off / 2, 70, 'S-DIM')
        for uu, sg in ((br['a'], -1), (br['b'], 1)):                 # U leg at both ends: tick across the bar end
            c_ = Q(uu, t)
            sh.line((c_[0] - nrm[0] * 220, c_[1] - nrm[1] * 220), (c_[0] + nrm[0] * 60, c_[1] + nrm[1] * 60), lay)
    # call-outs: one per group of identical consecutive rows, on its middle bar, every piece its own hexagon
    entries = []                                                     # (group, row shown, count, alternate) per lap pattern
    for gi, g in enumerate(M['groups']):
        var = {}
        for b_ in g: var.setdefault(tuple(p['mark'] for p in b_['pcs']), []).append(b_)
        for vi, rows_v in enumerate(var.values()):
            entries.append((gi, g, rows_v[len(rows_v) // 2], len(rows_v), vi > 0))
    for gi, g, br, n_, alt_ in entries:
        t = br['t']
        for j, p in enumerate(br['pcs']):
            txt = callout(n_, d, p['mark'], p['L'], s, tag, stg=br['lapped']) + ('  (ALTERNATE BARS)' if alt_ else '')
            Lt = P.text_len(txt); hh = M['step'] * k * 0.5 + HC * 1.1 * math.sin(math.pi / 3) + 30
            Lu = (p['u1'] - p['u0']) * k
            cand = []
            if Lu > Lt + 500:
                pref = [0.12, 0.42, 0.72][gi % 3]
                fr = sorted({round(v / 40, 3) for v in range(0, 41)}, key=lambda v: abs(v - pref))
                for f_ in fr:
                    u_ = p['u0'] + (250 + f_ * (Lu - Lt - 500)) / k
                    cand.append((Q(u_, t), 'in'))
            for side in ('end', 'start'):                           # beyond the bar end, on the bar's own line
                if side == 'end' and j == len(br['pcs']) - 1:
                    q0 = Q(p['u1'], t); cand.append(((q0[0] + e[0] * 900, q0[1] + e[1] * 900), side))
                if side == 'start' and j == 0:
                    q0 = Q(p['u0'], t); cand.append(((q0[0] - e[0] * (900 + Lt), q0[1] - e[1] * (900 + Lt)), side))
            placed = None
            for pt, kind in cand:
                bx = P.text_box(pt, e, nrm, Lt, hh)
                if any(bx.intersects(o) for o in P.boxes): continue
                if kind != 'in':
                    pg_s = Polygon([P.S(*c) for c in R.poly])
                    if bx.intersects(pg_s.buffer(-1)): continue
                placed = (pt, kind, bx); break
            if placed is None:
                pt, kind = cand[0] if cand else (Q(p['u0'], t), 'in'); bx = P.text_box(pt, e, nrm, Lt, hh)
                placed = (pt, kind, bx)
            pt, kind, bx = placed
            P.boxes.append(bx)
            P.ctext_along(p['mark'], txt, pt, ang, gap=max(60, M['step'] * k / 2 - HC * 1.1 * math.sin(math.pi / 3)))
            if kind == 'end':
                q0 = Q(p['u1'], t); sh.line((q0[0] + e[0] * 150, q0[1] + e[1] * 150), (pt[0] - e[0] * 100, pt[1] - e[1] * 100), 'S-RFT-TXT')
            elif kind == 'start':
                q0 = Q(p['u0'], t); sh.line((q0[0] - e[0] * 150, q0[1] - e[1] * 150), (pt[0] + e[0] * (Lt + 100), pt[1] + e[1] * (Lt + 100)), 'S-RFT-TXT')
        if len(g) > 1 and not alt_:                                  # distribution line of the group with ticks
            u_ = (max(b['pcs'][0]['u0'] for b in g) + min(b['pcs'][0]['u1'] for b in g)) / 2
            u_ = min(u_, min(b['pcs'][0]['u1'] for b in g) - 100)
            a_, b_ = Q(u_, g[0]['t']), Q(u_, g[-1]['t'])
            sh.line(a_, b_, 'S-DIM')
            for c_ in (a_, b_):
                sh.line((c_[0] - (e[0] + nrm[0]) * 150, c_[1] - (e[1] + nrm[1]) * 150), (c_[0] + (e[0] + nrm[0]) * 150, c_[1] + (e[1] + nrm[1]) * 150), 'S-DIM')


def place_plan(sh, R, scale, area):
    """fit the plan (global orientation) centred in area (x0, y0, x1, y1) of the sheet."""
    gx0, gy0, gx1, gy1 = Polygon(R.poly).bounds
    k = SC / scale
    ax0, ay0, ax1, ay1 = area
    ox = ax0 + ((ax1 - ax0) - (gx1 - gx0) * k) / 2; oy = ay0 + ((ay1 - ay0) - (gy1 - gy0) * k) / 2
    return Plan(sh, R, k, ox, oy, gx0, gy0)


def copy_legend(sh, tpl, origin):
    """the office call-out key exactly as on the engineer's sheet (model-space S-RFT-TXT entities of the template)."""
    ox, oy = origin
    for e in tpl.modelspace():
        if e.dxf.layer != 'S-RFT-TXT': continue
        p0 = e.dxf.insert if e.dxftype() == 'TEXT' else (e.dxf.start if e.dxftype() == 'LINE' else (e.get_points('xy')[0] if e.dxftype() == 'LWPOLYLINE' else None))
        if p0 is None or not (ox - 1 <= p0[0] <= ox + 42000 and oy - 1 <= p0[1] <= oy + 29700): continue     # this sheet's key only
        if e.dxftype() == 'TEXT':
            t = sh.m.add_text(e.dxf.text, height=e.dxf.height, rotation=e.dxf.rotation,
                              dxfattribs={'layer': 'S-RFT-TXT', 'style': e.dxf.style if e.dxf.style in sh.doc.styles else 'ROMANS'})
            t.dxf.insert = (e.dxf.insert.x - ox + sh.ox, e.dxf.insert.y - oy + sh.oy)
            for a in ('halign', 'valign', 'width'):
                if e.dxf.hasattr(a): t.dxf.set(a, e.dxf.get(a))
            if e.dxf.hasattr('align_point'): t.dxf.align_point = (e.dxf.align_point.x - ox + sh.ox, e.dxf.align_point.y - oy + sh.oy)
        elif e.dxftype() == 'LINE':
            sh.m.add_line((e.dxf.start.x - ox + sh.ox, e.dxf.start.y - oy + sh.oy), (e.dxf.end.x - ox + sh.ox, e.dxf.end.y - oy + sh.oy), dxfattribs={'layer': 'S-RFT-TXT'})
        elif e.dxftype() == 'LWPOLYLINE':
            pl = sh.m.add_lwpolyline([(x - ox + sh.ox, y - oy + sh.oy) for x, y in e.get_points('xy')], dxfattribs={'layer': 'S-RFT-TXT'})
            pl.closed = e.closed


def notes(sh, lines, x, y):
    for i, s in enumerate(lines):
        sh.text(s, x, y - i * HN * 1.7, HN, 'S-RFT-TXT', maxw=190000)


def section_marks(sh, P, R, secs):
    """cut lines of the sections on a plan: bubbles with the letter at both ends, outside the outline."""
    for lab, axis, t, (s0, s1) in secs:
        for sv, sg in ((s0, -1), (s1, 1)):
            u, v = ((sv + sg * 900, t) if axis == 'X' else (t, sv + sg * 900))
            u2, v2 = ((sv + sg * 2200, t) if axis == 'X' else (t, sv + sg * 2200))
            a_, b_ = P.SL(u, v), P.SL(u2, v2)
            sh.pline([a_, b_], 'S-SEC', 90)
            sh.circle(b_[0], b_[1], 1100, 'S-SEC')
            sh.text(lab, b_[0], b_[1], 1100, 'S-SEC', align=TA.MIDDLE_CENTER)


def main():
    f = json.load(open(sys.argv[1])); out = sys.argv[2]
    tb = gen.TB
    tpl = __import__('ezdxf').readfile(tb['dxf'])
    R = Raft(f)
    # curved edge: circle through the arc facets (radius on the plans)
    import numpy as np
    P_ = R.poly; seg = [math.dist(P_[i], P_[(i + 1) % len(P_)]) for i in range(len(P_))]
    idx = [i for i in range(len(P_)) if seg[i] < 700 and seg[i - 1] < 700]
    if len(idx) > 10:
        A = np.array([P_[i] for i in idx]); x, y = A[:, 0], A[:, 1]
        sol = np.linalg.lstsq(np.c_[2 * x, 2 * y, np.ones(len(x))], x * x + y * y, rcond=None)[0]
        r_ = math.sqrt(sol[2] + sol[0] ** 2 + sol[1] ** 2)
        f['arc'] = dict(c=(sol[0], sol[1]), r=r_, mid=tuple(A[len(A) // 2]))
    doc = new_doc(); dimstyle(doc)
    if tb.get('style') and tb['style'] not in doc.styles:
        st = tpl.styles.get(tb['style']); doc.styles.add(tb['style'], font=st.dxf.font)
    bl = BarList(); bl.cur = f['name']; rep = []
    scale = f.get('scale', 30)
    meta0 = dict(gen._PRJ.get('meta', {}))
    title1 = f.get('title1', 'STRUCTURAL COMBINED RAFT')
    sheets = []; si = 0

    def new_sheet(title, scale_txt):
        nonlocal si
        m = dict(meta0); m['title'] = f'{title1}\n{title}'; m['scale'] = scale_txt; m['size'] = 'A0'
        sh = A0(doc, 0, -si * 180000, m); sheets.append([0, -si * 180000, A0.W, A0.H, 1189, 841]); si += 1
        copy_legend(sh, tpl, (174052.0 + 0, 21856.0))                # template sheet origin (title block insert)
        return sh

    area = (6000, 15000, 201000, 150000)
    meshes = []
    for layer in ('B', 'T'):
        mesh = f['bot'] if layer == 'B' else f['top']
        for axis in ('X', 'Y'):
            long_ = axis == 'X'
            tag = (layer + ('1' if long_ else '2')) if layer == 'B' else (layer + ('2' if long_ else '1'))
            d, s = (mesh['dx'], mesh['sx']) if axis == 'X' else (mesh['dy'], mesh['sy'])
            meshes.append(build_bars(R, bl, layer, axis, d, s, tag, rep))
    # section lines through columns: A-A along Y, B-B along X
    cA = min(R.cols, key=lambda c: abs(c[0][0] - (R.pl.bounds[0] + R.pl.bounds[2]) / 2))[0]
    cB = min(R.cols, key=lambda c: abs(c[0][1] - (R.pl.bounds[1] + R.pl.bounds[3]) / 2))[0]
    def span(axis, t):
        g = R.pl.intersection(LineString([(R.pl.bounds[0] - 10, t), (R.pl.bounds[2] + 10, t)]) if axis == 'X' else LineString([(t, R.pl.bounds[1] - 10), (t, R.pl.bounds[3] + 10)]))
        b = g.bounds; return (b[0], b[2]) if axis == 'X' else (b[1], b[3])
    secs = [('A', 'Y', cA[0], span('Y', cA[0])), ('B', 'X', cB[1], span('X', cB[1]))]
    names = {'B1': 'BOTTOM REINFORCEMENT (B1) - BARS ALONG X', 'B2': 'BOTTOM REINFORCEMENT (B2) - BARS ALONG Y',
             'T2': 'TOP REINFORCEMENT (T2) - BARS ALONG X', 'T1': 'TOP REINFORCEMENT (T1) - BARS ALONG Y'}
    for M in meshes:
        sh = new_sheet(names[M['tag']], f'1:{scale}')
        P = place_plan(sh, R, scale, area)
        P.outline(); P.edge_dims()
        draw_mesh_plan(sh, P, M, R)
        section_marks(sh, P, R, secs)
        P.axes_symbol(10000, 26000)
        sh.text(f"{f['name']} - {names[M['tag']]}   ({len(M['bars'])} BARS, {len(M['groups'])} CALL-OUTS)   SCALE 1:{scale}", 6000, 10500, HP, 'S-SEC')
        zt = 'MIDSPAN (+/- SPAN/5)' if M['layer'] == 'B' else 'THE COLUMNS (+/- SPAN/5)'
        notes(sh, [f"T{M['d']} @{M['s']} {'BOTTOM' if M['layer'] == 'B' else 'TOP'} MESH, h = {R.h}, COVER {R.C}: EVERY BAR AT ITS REAL LENGTH TO THE OUTLINE - COVER; U LEGS {R.lg} AT BOTH ENDS (TICK AT THE BAR END, SEE EDGE DETAIL).",
                   f"LAPS {M['lp']} (60d) AT {zt}, HATCHED; ALTERNATE ROWS STAGGERED (PATTERN A / B, >= 500 APART); THE LAPPED PIECE IS DRAWN BESIDE THE BAR, CIRCLES = LAP ENDS.",
                   f"X PARALLEL TO THE STRAIGHT EDGE ({f['angle']:.3f}°), Y PERPENDICULAR. ONE CALL-OUT PER GROUP OF IDENTICAL ROWS (DISTRIBUTION LINE)."], 6000, 8200)
        rep.append(f"{M['tag']}: {len(M['bars'])} bars in {len(M['groups'])} call-out groups, lapped {sum(1 for b in M['bars'] if b['lapped'])}, supports {[round(v) for v in R.supports(M['axis'])]}")
    # chairs layout
    ch = f['chair']; dch = ch['d']; foot, top = ch['foot'], ch['top']
    db1, db2 = f['bot']['dx'], f['bot']['dy']; dt1, dt2 = f['top']['dx'], f['top']['dy']
    ch_h = int(R.h - 2 * R.C - db1 - db2 - dt1 - dt2)                 # top of bottom mesh -> underside of top mesh (BLSC 26-10)
    chL = int(math.ceil((2 * foot + 2 * ch_h + top) / 10) * 10)
    sp = int(round(1000 / math.sqrt(ch.get('per_m2', 1))))
    pts = chair_points(R, sp, foot, top)
    x0, y0, x1, y1 = R.er.bounds
    mkch = bl.add(dch, ('CH', foot, ch_h, top), chL, len(pts), 1, 'CH')
    sh = new_sheet('CHAIRS LAYOUT', f'1:{scale}')
    P = place_plan(sh, R, scale, area); P.outline(); P.edge_dims()
    for u, v in pts:                                                  # symbol: chair top (thick) + its two legs (dots)
        sh.pline([P.SL(u - top / 2, v), P.SL(u + top / 2, v)], 'S-RFT-STIR', 110)
        for uu in (u - top / 2, u + top / 2):
            c_ = P.SL(uu, v)
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*c_), 140, 0, 360)
    # typical spacing dims on one row / one column of chairs
    um, vm = sorted(pts, key=lambda q: (abs(q[1] - (y0 + y1) / 2), q[0]))[0]
    rowp = sorted([q for q in pts if abs(q[1] - vm) < 1], key=lambda q: q[0])
    if len(rowp) > 2:
        a_, b_ = P.SL(rowp[0][0], vm + 350), P.SL(rowp[1][0], vm + 350)
        sh.text(str(sp), (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2 + 200, HS * 1.3, 'S-DIM', rot=f['angle'], align=TA.BOTTOM_CENTER)
        sh.line(a_, b_, 'S-DIM')
    colp = sorted([q for q in pts if abs(q[0] - rowp[1][0]) < 1], key=lambda q: q[1]) if len(rowp) > 2 else []
    if len(colp) > 2:
        a_, b_ = P.SL(colp[0][0] + 700, colp[0][1]), P.SL(colp[0][0] + 700, colp[1][1])
        sh.line(a_, b_, 'S-DIM')
        sh.text(str(sp), (a_[0] + b_[0]) / 2 + 250, (a_[1] + b_[1]) / 2, HS * 1.3, 'S-DIM', rot=f['angle'] + 90, align=TA.BOTTOM_CENTER)
    section_marks(sh, P, R, secs); P.axes_symbol(10000, 26000)
    topc = max(pts, key=lambda q: q[1])                               # call-out above the straight edge, leader to the nearest chair
    cp = P.SL(*topc)
    sh.text(f"{f['name']} - CHAIRS LAYOUT   ({len(pts)} CHAIRS T{dch} @{sp} x {sp} ALONG X / Y)   SCALE 1:{scale}", 6000, 10500, HP, 'S-SEC')
    notes(sh, [f"CHAIRS T{dch}, 1 PER m2 ON A {sp} x {sp} GRID ALONG THE MESH AXES, TOP ALONG X; STANDING ON THE BOTTOM MESH, CARRYING THE TOP MESH (CHAIR DETAIL ON THE SECTIONS SHEET).",
               f"CHAIR H = {R.h} - 2x{R.C} - {db1}+{db2} (BOTTOM MESH) - {dt1}+{dt2} (TOP MESH) = {ch_h};  L = {foot} + {ch_h} + {top} + {ch_h} + {foot} = {chL}.",
               f"SYMBOL: THICK LINE = CHAIR TOP {top}, DOTS = ITS LEGS; FEET {foot} EACH SIDE ALONG X (DETAIL 4). NO CHAIR CLOSER THAN 200 TO A COLUMN; CHAIRS INSIDE THE COVER LINE."], 6000, 8200)
    # call-out of the chairs on the plan (one, with a leader to a chair)
    lx, ly = cp[0] - 4000, P.SL(topc[0], R.pl.bounds[3])[1] + 9000
    sh.line(cp, (lx - 200, ly + 200), 'S-RFT-TXT')
    P.ctext_along(mkch, callout(len(pts), dch, mkch, chL, sp, 'CH') + '  (SEE DETAIL 4)', (lx, ly), 0, h=HC * 1.4)
    rep.append(f'chairs: {len(pts)} T{dch} H={ch_h} L={chL} @{sp}')
    # side bars
    sd = f['side']; ds = sd['d']; lps = f.get('lap_d', 60) * ds
    dmain = max(db1, db2, dt1, dt2)
    ring = R.pl.buffer(-(R.C + dmain + ds / 2), join_style=2)
    ringg = [R.G(*q) for q in ring.exterior.coords]                   # pieces in global coords
    pcs = side_pieces(ringg, lps, R.stock)
    rows_sb = int(sd.get('rows', 1))
    grp = {}
    for pc in pcs: grp.setdefault(pc['key'], []).append(pc)
    pmk = {}
    for key_, lst in grp.items():
        sk = [tuple(map(int, q)) for q in LineString(lst[0]['local']).simplify(100).coords]     # BBS sketch: arc facets merged (L = real length)
        pmk[key_] = bl.add(ds, ('OPEN',) + tuple(sk), lst[0]['L'], rows_sb * len(lst), 1, 'SB')
    rep.append(f'side bars: {rows_sb} row x {len(pcs)} pieces ' + ', '.join(str(p['L']) for p in pcs))
    draw_sections_sheet(new_sheet('SECTIONS AND DETAILS', 'AS SHOWEN'), R, f, meshes, secs, pcs, pmk, grp, rows_sb, ds, lps,
                        (mkch, len(pts), chL, ch_h, foot, top, dch, sp), rep)
    # BBS (A3 sheets with the same title block, after the A0 sheets)
    first = 40
    meta = dict(meta0); meta['title'] = title1; meta['size'] = 'A3'; meta['scale'] = 'N.T.S'
    nb = draw_bbs_grouped(doc, first, bl.sorted(), meta, [(f"{f['name']}  (NO={f['no']})", f['name'], f['no'])])
    for i in range(nb): sheets.append([0, -(first + i) * 32000, 42000, 29700, 420, 297])
    doc.saveas(out + '.dxf')
    json.dump(sheets, open(out + '.sheets.json', 'w'))
    bl.export(out + '.bbs.json', {f['name']: ''}, {f['name']: f['no']})
    tot = sum(r['n_in'] * r['n_el'] * r['L'] / 1000 * unit_mass(r['d']) for r in bl.sorted())
    rep.append(f'marks {len(bl.rows)}, BBS sheets {nb}, steel {tot:,.1f} kg')
    open(out + '.report.txt', 'w').write('\n'.join(rep) + '\n')
    print('\n'.join(rep[-12:]))


def draw_sections_sheet(sh, R, f, meshes, secs, pcs, pmk, grp, rows_sb, ds, lps, chair, rep):
    h, C, lg = R.h, R.C, R.lg
    by = {M['tag']: M for M in meshes}
    db1, db2 = f['bot']['dx'], f['bot']['dy']; dt1, dt2 = f['top']['dx'], f['top']['dy']
    z_b1, z_b2 = C + db1 / 2, C + db1 + db2 / 2                      # bottom: B1 (X) lowest, B2 (Y) on it
    z_t1, z_t2 = h - C - dt2 / 2, h - C - dt2 - dt1 / 2               # top: T1 (Y) uppermost, T2 (X) under it
    lv = f.get('levels', {})
    EL = f.get('elem_abbr', 'RAFT')                                    # RAFT / F (combined footing)
    curved = bool(f.get('arc'))
    def level(x, y, txt):
        sh.pline([(x - 350, y + 600), (x, y), (x + 350, y + 600), (x - 350, y + 600)], 'S-DIM', 0, True)
        sh.line((x, y), (x + 3800, y), 'S-DIM')
        sh.text(txt, x + 500, y + 150, HS * 1.3, 'S-DIM')

    def long_section(lab, axis, t, s0, s1, ox, oy, k):
        """section along `axis` at t: concrete, columns (break lines), the bar row of this section in both layers
        (legs, laps), the cut bars of the other direction as dots, cover / thickness, levels."""
        Z = lambda s_, z: (ox + (s_ - s0) * k, oy + z * k)
        sh.pline([Z(s0, 0), Z(s1, 0), Z(s1, h), Z(s0, h)], 'S-GB-CONC', 0, True)
        sh.line((Z(s0, 0)[0] - 1500, oy), (Z(s1, 0)[0] + 1500, oy), 'S-DIM')                       # T.O.PC line
        for g in R.colp:                                             # columns cut by the section line
            cut_ = g.intersection(LineString([(t, -1e7), (t, 1e7)]) if axis == 'Y' else LineString([(-1e7, t), (1e7, t)]))
            if cut_.is_empty: continue
            bb = cut_.bounds; c0, c1 = (bb[1], bb[3]) if axis == 'Y' else (bb[0], bb[2])
            if c1 - c0 < 1: continue
            for xx in (c0, c1): sh.line(Z(xx, h), Z(xx, h + 900), 'S-GB-CONC')
            sh.break_line(Z(c0 - 150, h + 900), Z(c1 + 150, h + 900), 'S-GB-CONC', amp=250)
        tag_b, tag_t = ('B1', 'T2') if axis == 'X' else ('B2', 'T1')
        zb, zt = (z_b1, z_t2) if axis == 'X' else (z_b2, z_t1)
        for tag, zz, sg in ((tag_b, zb, 1), (tag_t, zt, -1)):
            M = by[tag]; br = min(M['bars'], key=lambda b: abs(b['t'] - t))
            lay = 'S-RFT-BOT' if tag[0] == 'B' else 'S-RFT-TOP'
            for j, p in enumerate(br['pcs']):
                dz = (-sg * M['d'] * 1.2) if j % 2 else 0
                pts = [Z(p['u0'], zz + dz), Z(p['u1'], zz + dz)]
                if p['t0'] <= 1: pts.insert(0, Z(p['u0'], zz + sg * lg))
                if p['t1'] >= br['T'] - 1: pts.append(Z(p['u1'], zz + sg * lg))
                sh.pline(pts, lay, max(M['d'] * k, 40), r=3 * M['d'] * k)
                if j:
                    a_ = Z(p['u0'], zz); b_ = Z(br['pcs'][j - 1]['u1'], zz)
                    yy = a_[1] + sg * 900
                    sh.line((a_[0], a_[1]), (a_[0], yy), 'S-DIM'); sh.line((b_[0], b_[1]), (b_[0], yy), 'S-DIM')
                    sh.text(f'LAP {M["lp"]}', (a_[0] + b_[0]) / 2, yy + (100 if sg > 0 else -100), HS * 1.2, 'S-DIM',
                            align=TA.BOTTOM_CENTER if sg > 0 else TA.TOP_CENTER)
            # call-out of the first piece of the row (mark + length), above / below the section
            p0 = br['pcs'][0]; q = Z(p0['u0'] + 1500, zz)
            ty = oy + (h * k + 1700 if sg < 0 else -1700)
            sh.line(q, (q[0] + 900, ty + (0 if sg < 0 else 400)), 'S-RFT-TXT')
            Pl = Plan(sh, R, 1, 0, 0, 0, 0)
            Pl.ctext_along(p0['mark'], f"{callout(1, M['d'], p0['mark'], p0['L'], M['s'], tag)}  (ROW {br['row'] + 1} OF {tag}"
                           f"{', ' + str(len(br['pcs'])) + ' PIECES' if len(br['pcs']) > 1 else ''})", (q[0] + 900, ty), 0, h=HC * 1.2, gap=0)
        # cut bars of the other direction (dots)
        for tag, zz in ((('B2', z_b2), ('T1', z_t1)) if axis == 'X' else (('B1', z_b1), ('T2', z_t2))):
            M = by[tag]
            for br in M['bars']:
                if br['a'] <= t <= br['b'] and s0 + C - 1 <= br['t'] <= s1 - C + 1:
                    c_ = Z(br['t'], zz)
                    hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-BOT' if tag[0] == 'B' else 'S-RFT-TOP'})
                    hh.paths.add_edge_path().add_arc(sh.P(*c_), max(M['d'] / 2 * k, 45), 0, 360)
        sh.dim(Z(s1, 0), Z(s1, h), (Z(s1, 0)[0] + 1800, oy), angle=90, text=str(h))
        if lv:                                                       # levels only when given (never invented)
            level(Z(s0, h)[0] - 11000, Z(s0, h)[1], f"T.O.{EL} {lv.get('tor', 0):+.2f}")
            level(Z(s0, 0)[0] - 11000, oy, f"B.O.{EL} = T.O.PC {lv.get('bor', 0):+.2f}")
        sh.text(f"SECTION {lab}-{lab}  (ALONG {axis}, THROUGH A COLUMN)  SCALE 1:{round(SC / k)}", ox, oy - 3600, HP, 'S-SEC')
        return Z

    k30 = SC / 30
    A = next(s for s in secs if s[0] == 'A'); B = next(s for s in secs if s[0] == 'B')
    long_section('B', 'X', B[2], B[3][0], B[3][1], 14000, 150000, k30)
    long_section('A', 'Y', A[2], A[3][0], A[3][1], 14000, 128000, k30)
    # ---- typical edge detail 1:10 (k = 20): legs, side bar, covers, chair
    k = 20; ox, oy = 14000, 88000; Wd = 1100
    Z = lambda x, z: (ox + x * k, oy + z * k)
    sh.pline([Z(Wd, 0), Z(0, 0), Z(0, h), Z(Wd, h)], 'S-GB-CONC')
    sh.break_line(Z(Wd, -60), Z(Wd, h + 60), 'S-GB-CONC') if False else sh.line(Z(Wd, -60), Z(Wd, h + 60), 'S-SEC')
    sh.line(Z(-300, 0), Z(Wd + 300, 0), 'S-DIM')
    xb = C                                                            # bar centre line at the cover (office: bars at the cover)
    sh.pline([Z(xb, z_b1 + lg), Z(xb, z_b1), Z(Wd, z_b1)], 'S-RFT-BOT', db1 * k, r=3 * db1 * k)
    sh.pline([Z(xb + db1 + 2, z_t2 - lg), Z(xb + db1 + 2, z_t2), Z(Wd, z_t2)], 'S-RFT-TOP', dt1 * k, r=3 * dt1 * k)
    for x_ in range(int(C + 166), int(Wd), 166):                       # Y bars cut (dots) on / under the X bars
        for zz, dd, lay in ((z_b2, db2, 'S-RFT-BOT'), (z_t1, dt2, 'S-RFT-TOP')):
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': lay}); hh.paths.add_edge_path().add_arc(sh.P(*Z(x_, zz)), dd / 2 * k, 0, 360)
    zs = (z_b2 + db2 / 2 + z_t2 - dt1 / 2) / 2                         # side bar at mid depth, inside the legs
    hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*Z(xb + db1 + ds / 2 + 6, zs)), ds / 2 * k, 0, 360)
    Pl = Plan(sh, R, 1, 0, 0, 0, 0)
    sm = pmk[next(iter(grp))]
    sh.line(Z(xb + db1 + ds, zs), Z(xb + 330, zs + 300), 'S-RFT-TXT')
    Pl.ctext_along(sm, f'T{ds} SIDE BAR ({rows_sb} ROW, ALONG THE PERIMETER)', Z(xb + 340, zs + 280), 0, h=HC, gap=0)
    mkb1 = by['B1']['groups'][len(by['B1']['groups']) // 2][0]['pcs'][0]
    sh.text(f'B1 / B2 : T{db1} @{f["bot"]["sx"]} / T{db2} @{f["bot"]["sy"]} - U LEG {lg} UP', *Z(520, z_b1 - 30), HS * 1.3, 'S-RFT-TXT', align=TA.TOP_LEFT)
    sh.text(f'T2 / T1 : T{dt1} @{f["top"]["sx"]} / T{dt2} @{f["top"]["sy"]} - U LEG {lg} DOWN', *Z(520, z_t1 + 30), HS * 1.3, 'S-RFT-TXT', align=TA.BOTTOM_LEFT)
    sh.text(f'LEG {lg}', *Z(xb - 25, z_b1 + lg / 2), HS * 1.2, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
    sh.text(f'LEG {lg}', *Z(xb + db1 + 30, z_t2 - lg / 2 - 40), HS * 1.2, 'S-DIM', rot=90, align=TA.TOP_CENTER)
    sh.dim(Z(0, 0), Z(0, h), (Z(0, 0)[0] - 2600, oy), angle=90, text=str(h))
    sh.dim(Z(0, 0), Z(0, C), (Z(0, 0)[0] - 1400, oy), angle=90, text=str(C))
    sh.dim(Z(0, h - C), Z(0, h), (Z(0, 0)[0] - 1400, oy), angle=90, text=str(C))
    sh.dim(Z(0, h), Z(C, h), (ox, Z(0, h)[1] + 1500), text=str(C))
    # chair in the detail (standing on the bottom mesh)
    mkch, nch, chL, ch_h, foot, top, dch, sp = chair
    xc = 760; zf = z_b2 + db2 / 2 + dch / 2
    sh.pline([Z(xc - top / 2 - foot * 0.55, zf), Z(xc - top / 2, zf), Z(xc - top / 2, zf + ch_h), Z(xc + top / 2, zf + ch_h), Z(xc + top / 2, zf), Z(Wd - 20, zf)], 'S-RFT-STIR', dch * k, r=2.5 * dch * k)
    sh.text('CHAIR', *Z(xc, zf + ch_h - 60), HS * 1.2, 'S-RFT-TXT', align=TA.TOP_CENTER)
    if lv:
        level(Z(Wd, h)[0] + 2500, Z(0, h)[1], f"T.O.{EL} {lv.get('tor', 0):+.2f}")
        level(Z(Wd, 0)[0] + 2500, oy, f"B.O.{EL} = T.O.PC {lv.get('bor', 0):+.2f}")
    sh.text('EDGE FACE (CURVED / STRAIGHT)' if curved else 'EDGE FACE', *Z(-60, h + 150), HS * 1.2, 'S-DIM', rot=90, align=TA.BOTTOM_LEFT)
    sh.text(f'DETAIL 1 - TYPICAL EDGE{" (CURVED AND STRAIGHT EDGES)" if curved else ""}  SCALE 1:10', ox - 2600, oy - 4200, HP, 'S-SEC')
    sh.text(f'BARS STOP AT COVER {C} FROM THE FACE{" (NORMAL TO THE CURVED FACE)" if curved else ""}, U LEGS {lg}: BOTTOM UP, TOP DOWN, LEGS SIDE BY SIDE; SIDE BAR T{ds} INSIDE THE LEGS.',
            ox - 2600, oy - 5300, HN, 'S-RFT-TXT', maxw=60000)
    # ---- detail 2: plan of the bar ends at the curved edge, 1:15 (enlarged where the bars are densest);
    #      straight-edged footings: the CHAIRS LAYOUT plan in its place (no separate chairs sheet)
    if not curved:
        chairs_plan(sh, R, f, chair, (98000, 84000, 146000, 120000))
    k2 = SC / 15
    if not curved: k2 = None
    if curved:
        arc = f.get('arc')
        am = R.Lc(*arc['mid']) if arc else R.pl.centroid.coords[0]
        wx, wy = 3200, 2400
        win = box(am[0] - wx / 2, am[1] - wy / 2, am[0] + wx / 2, am[1] + wy / 2)
        gx, gy = 98000, 84000
        D = lambda u, v: (gx + (u - win.bounds[0]) * k2, gy + (v - win.bounds[1]) * k2)
        sh.pline([D(*q) for q in win.exterior.coords], 'S-SEC', 0)
        def clipped(geom, layer, w=0):
            g = geom.intersection(win)
            for q in getattr(g, 'geoms', [g]):
                if q.is_empty: continue
                cs = list(q.coords) if q.geom_type == 'LineString' else (list(q.exterior.coords) if q.geom_type == 'Polygon' else [])
                if len(cs) > 1: sh.pline([D(*c) for c in cs], layer, w)
        clipped(R.pl.exterior, 'S-GB-CONC', 40)
        cvr = R.er.exterior
        g = cvr.intersection(win)
        for q in getattr(g, 'geoms', [g]):
            if q.is_empty or q.geom_type != 'LineString': continue
            cs = list(q.coords)
            for a_, b_ in zip(cs, cs[1:]):                                  # cover line dashed (short dashes)
                Ls = math.dist(a_, b_); nseg = max(1, int(Ls / 120))
                for i in range(0, nseg, 2):
                    p0 = (a_[0] + (b_[0] - a_[0]) * i / nseg, a_[1] + (b_[1] - a_[1]) * i / nseg)
                    p1 = (a_[0] + (b_[0] - a_[0]) * (i + 1) / nseg, a_[1] + (b_[1] - a_[1]) * (i + 1) / nseg)
                    sh.line(D(*p0), D(*p1), 'S-DIM')
        for tag, axis in (('B1', 'X'), ('B2', 'Y')):
            M = by[tag]
            for br in M['bars']:
                for p in br['pcs']:
                    ln = LineString([(p['u0'], br['t']), (p['u1'], br['t'])]) if axis == 'X' else LineString([(br['t'], p['u0']), (br['t'], p['u1'])])
                    clipped(ln, 'S-RFT-BOT', 25 * 2)
                for uu in (br['a'], br['b']):
                    q = (uu, br['t']) if axis == 'X' else (br['t'], uu)
                    if win.contains(Point(q)): sh.circle(*D(*q), 90, 'S-RFT-BOT')
        clipped(LineString(list(R.pl.buffer(-(C + max(db1, db2) + ds / 2), join_style=2).exterior.coords)), 'S-RFT-STIR', 30)
        # labels: one X bar and one Y bar ending in the window
        for tag, axis in (('B1', 'X'), ('B2', 'Y')):
            M = by[tag]; ang = R.th * 0 + (0 if axis == 'X' else math.pi / 2)
            cand = [br for br in M['bars'] if win.buffer(-300).contains(Point((br['b'], br['t']) if axis == 'X' else (br['t'], br['b'])))]
            if not cand: continue
            br = cand[len(cand) // 2]; p = br['pcs'][-1]
            q = (br['b'], br['t']) if axis == 'X' else (br['t'], br['b'])
            a0 = D(*q)
            tx, ty = (gx + wx * k2 + 1500, a0[1]) if axis == 'X' else (gx + wx * k2 + 1500, gy + wy * k2 - 1800)
            sh.line(a0, (tx - 200, ty + 200), 'S-RFT-TXT')
            Pl.ctext_along(p['mark'], callout(1, M['d'], p['mark'], p['L'], M['s'], tag) + f'  (ROW {br["row"] + 1})', (tx, ty), 0, h=HC * 1.2, gap=0)
        sh.text(f'COVER LINE {C} (DASHED) - EVERY BAR ENDS ON IT; CIRCLE = BAR END WITH ITS U LEG ({lg}); SIDE BAR T{ds} ALONG THE CURVE.',
                gx, gy - 1500, HN, 'S-RFT-TXT', maxw=60000)
        sh.text('DETAIL 2 - BOTTOM BAR ENDS AT THE CURVED EDGE (PLAN, MESH AXES HORIZONTAL)  SCALE 1:15', gx, gy - 3000, HP, 'S-SEC', maxw=95000)
    # ---- detail 3: staggered laps, 1:20 (k = 10)
    k3 = SC / 20; lx, ly = 14000, 40000
    M = by['B1']; lp = M['lp']
    for i, sh_ in enumerate((0, lp + 500, 0)):
        y = ly + i * 166 * k3
        x0 = lx + 400 * k3 + sh_ * k3
        sh.pline([(lx, y), (x0 + lp * k3, y)], 'S-RFT-BOT', 60)
        sh.pline([(x0, y - 30 * k3), (x0 + lp * k3 + 1800 * k3 if False else lx + (2 * lp + 2400) * k3, y - 30 * k3)], 'S-RFT-BOT', 60)
        sh.circle(x0, y - 15 * k3, 70, 'S-DIM'); sh.circle(x0 + lp * k3, y - 15 * k3, 70, 'S-DIM')
    sh.dim((lx + 400 * k3, ly - 30 * k3), (lx + (400 + lp) * k3, ly - 30 * k3), (lx, ly - 1500), text=f'{lp} (60d)')
    sh.dim((lx + (400 + lp) * k3, ly + 166 * k3), (lx + (400 + lp + 500) * k3, ly + 166 * k3), (lx, ly + 166 * k3 * 2 + 1800), text='>= 500')
    sh.dim((lx + (400 + lp + 500) * k3, ly + 166 * k3), (lx + (400 + 2 * lp + 500) * k3, ly + 166 * k3), (lx, ly + 166 * k3 * 2 + 1800), text=f'{lp}')
    sh.text('DETAIL 3 - STAGGERED LAPS (ALTERNATE ROWS, PATTERN A / B)  SCALE 1:20', lx, ly - 4200, HP, 'S-SEC')
    sh.text(f'LAP 60d = {lp} (T{M["d"]}); LAPS OF NEIGHBOURING BARS >= 500 APART, NEVER IN ONE SECTION; BOTTOM MESH AT MIDSPAN, TOP MESH AT THE COLUMNS (+/- SPAN/5).',
            lx, ly - 5300, HN, 'S-RFT-TXT', maxw=70000)
    # ---- detail 4: chair 1:10
    kc = 20; cx0, cy0 = 72000, 40000
    Q = lambda u, v: (cx0 + u * kc, cy0 + v * kc)
    u1, u2, u3 = foot, foot + top, 2 * foot + top
    sh.pline([Q(0, 0), Q(u1, 0), Q(u1, ch_h), Q(u2, ch_h), Q(u2, 0), Q(u3, 0)], 'S-RFT-STIR', dch * kc, r=2.5 * dch * kc)
    sh.line(Q(-200, -dch / 2 - db2 - db1 / 2), Q(u3 + 200, -dch / 2 - db2 - db1 / 2), 'S-DIM')
    for uu in (100, u1 - 80, u2 + 80, u3 - 100):
        sh.circle(*Q(uu, -dch / 2 - db2 / 2), db2 / 2 * kc, 'S-DIM')
    yt = ch_h + dch / 2 + dt1 / 2
    sh.line(Q(-200, yt), Q(u3 + 200, yt), 'S-DIM')
    for uu in (u1 + 60, (u1 + u2) / 2, u2 - 60):
        sh.circle(*Q(uu, ch_h + dch / 2 + dt1 + dt2 / 2), dt2 / 2 * kc, 'S-DIM')
    sh.text('TOP MESH', *Q(u3 + 300, yt), HS * 1.3, 'S-DIM', align=TA.MIDDLE_LEFT)
    sh.text('BOTTOM MESH', *Q(u3 + 300, -dch / 2 - db2), HS * 1.3, 'S-DIM', align=TA.MIDDLE_LEFT)
    yb = Q(0, 0)[1] - 2600
    for a_, b_, tx in ((0, u1, foot), (u1, u2, top), (u2, u3, foot)):
        sh.dim(Q(a_, 0), Q(b_, 0), (Q(0, 0)[0], yb), text=str(tx))
    sh.dim(Q(u1, 0), Q(u1, ch_h), (Q(u1, 0)[0] - 2200, cy0), angle=90, text=str(ch_h))
    sh.dim(Q(u2, 0), Q(u2, ch_h), (Q(u2, 0)[0] + 2200, cy0), angle=90, text=str(ch_h))
    Pl.ctext_along(mkch, callout(nch, dch, mkch, chL, sp, 'CH'), (cx0, Q(0, ch_h)[1] + 4200), 0, h=HC * 1.3, gap=0)
    sh.text(f'H = {h} - 2x{C} - {db1}+{db2} (BOTTOM MESH) - {dt1}+{dt2} (TOP MESH) = {ch_h} (TOP OF BOTTOM MESH TO UNDERSIDE OF TOP MESH)',
            cx0, Q(0, ch_h)[1] + 3000, HN, 'S-RFT-TXT', maxw=80000)
    sh.text(f'L = {foot} + {ch_h} + {top} + {ch_h} + {foot} = {chL}   (T{dch}, 1 CHAIR PER m2 @{sp} x {sp})', cx0, Q(0, ch_h)[1] + 2000, HN, 'S-RFT-TXT', maxw=80000)
    sh.text('DETAIL 4 - CHAIR  SCALE 1:10', cx0, cy0 - 4200 - 1200, HP, 'S-SEC')
    # ---- side bars plan 1:100 (k = 2) with pieces, marks and laps
    kp = SC / 100
    gx0, gy0, gx1, gy1 = Polygon(R.poly).bounds
    px, py = 150000, 40000
    S_ = lambda x, y: (px + (x - gx0) * kp, py + (y - gy0) * kp)
    sh.pline([S_(*q) for q in R.poly], 'S-GB-CONC', 0, True)
    cen = Polygon(R.poly).centroid
    for pc in pcs:
        sh.pline([S_(*q) for q in pc['pts']], 'S-RFT-STIR', 40)
        mx, my = S_(*pc['mid']); nx, ny = pc['nrm']
        sh.line((mx, my), (mx + nx * 1400, my + ny * 1400), 'S-RFT-TXT')
        Pl.ctext_along(pmk[pc['key']], f'L={pc["L"]}', (mx + nx * 1500 - (0 if nx >= 0 else 3200), my + ny * 1500), 0, h=HS * 1.2, gap=0)
        if pc.get('lap'):
            for q in pc['lap'][:2]: sh.circle(*S_(*q), 90, 'S-DIM')
    sh.text(f'SIDE BARS T{ds} ALONG THE REAL PERIMETER - {rows_sb} ROW, {len(pcs)} PIECES, LAPS {lps} (60d) AWAY FROM THE CORNERS  SCALE 1:100', px - 4000, py - 3000, HP * 0.8, 'S-SEC', maxw=85000)
    sb_s = f["side"].get("s", "")
    sh.text((f'T{ds} @{sb_s} (ENGINEER)' if sb_s else f'T{ds} - {rows_sb} ROW') + ': AT MID DEPTH BETWEEN THE MESHES, INSIDE THE U LEGS.', px - 4000, py - 4300, HN, 'S-RFT-TXT', maxw=85000)
    rep.append('sections: A-A at u=%d, B-B at v=%d' % (A[2], B[2]))


if __name__ == '__main__':
    main()
