"""Shared helpers: A3 1:100 sheet frame + title block in model space, layers, dim style, schedule, bar rules."""
import math, pickle, sys
import ezdxf
from ezdxf.enums import TextEntityAlignment as TA

import json as _json, os as _os
# beam schedule comes from the project file: {"schedule": {"GB1": {"b":200,"h":700,"nb":4,"db":16,"nt":4,"dt":16,"ds":10,"s":125}, ...}}
_PRJ = _json.load(open(_os.environ.get('RC_PROJECT', 'project.json')))
SCHED = _PRJ.get('schedule', {})      # GB schedule (none for a footings-only package)
TB = _PRJ.get('title_block')       # office / client title block (tb_template.py); None -> the built-in frame
COVER = 40          # grade beams, contact with soil
STOCK = 12000
LAP = 60            # x d
HOOK = 135
def leg(d, pos=None):
    """GB end leg (hook down / up into the support). Engineer, Oct 2026: bottom bars >= 200, top bars >= 600
    (project.json gb_leg_bot / gb_leg_top)."""
    base = 200 if d <= 16 else 250
    if pos == 'T': return max(base, _PRJ.get('gb_leg_top', 600))
    if pos == 'B': return max(base, _PRJ.get('gb_leg_bot', 200))
    return base
def lap(d): return LAP * d

LAYERS = {  # name: color
    'S-GB-CONC': 7, 'S-GB-COL': 8, 'S-AXIS': 8, 'S-AXIS-TXT': 1,
    'S-RFT-TOP': 1, 'S-RFT-BOT': 5, 'S-RFT-STIR': 3, 'S-RFT-TXT': 7,
    'S-DIM': 2, 'S-SEC': 4, 'S-TITLE': 7, 'S-FRAME': 7,
}

def new_doc():
    doc = ezdxf.new('R2018', setup=True)
    for n, c in LAYERS.items():
        doc.layers.add(n, color=c)
    doc.styles.add('ROMANS', font='arial.ttf')
    ds = doc.dimstyles.new('GB100')
    ds.dxf.dimtxt = 2.0; ds.dxf.dimscale = 100; ds.dxf.dimasz = 1.5; ds.dxf.dimexo = 1.0
    ds.dxf.dimexe = 1.0; ds.dxf.dimgap = 0.6; ds.dxf.dimtad = 1; ds.dxf.dimdec = 0
    ds.dxf.dimtih = 0; ds.dxf.dimtoh = 0; ds.dxf.dimblk = 'ARCHTICK'
    if TB:                                   # the title-block block (frame, logos, key plan, notes) once per file
        from ezdxf import xref
        tpl = ezdxf.readfile(TB['dxf'])
        ld = xref.Loader(tpl, doc); ld.load_block_layout(tpl.blocks.get(TB['block'])); ld.execute()
        doc.set_raster_variables(frame=0, quality=1, units='mm')   # logos (IMAGE) of the template: no frame line
    doc._tb_seq = {}                          # running sheet number per venue code
    return doc



# ---- running sheet numbers across the zones (engineer, Oct 2026): every package continues its numbering from the
# last sheet of the zone before (AREA 1 .. AREA 7), from title_block.seq_start (necks 20100, cores 30100, ...).
SEQ_FILE = _os.path.join('out', 'ZONES', 'sheet_seq.json')


def seq_zone(doc, zone, kind, names):
    """Start this zone's numbering after the sheets of the zones before it (counts kept in SEQ_FILE)."""
    data = _json.load(open(SEQ_FILE)) if _os.path.exists(SEQ_FILE) else {}
    rec = data.get(kind, {}); base = {}
    for z in names:
        if z == zone: break
        if z not in rec: print(f'(!) sheet numbers: {kind} of {z} not generated yet - numbers of {zone} assume 0 sheets there')
        for v, n in rec.get(z, {}).items(): base[v] = base.get(v, 0) + n
    st = TB.get('seq_start', {}) if TB else {}
    for v, n in base.items(): doc._tb_seq[v] = int(st.get(v, 1)) - 1 + n
    doc._seq_key = (kind, zone, names); doc._seq_from = dict(doc._tb_seq)


def seq_none(kind, zone):
    """A zone with no sheet of this package: record 0 so the zones after it number on."""
    data = _json.load(open(SEQ_FILE)) if _os.path.exists(SEQ_FILE) else {}
    data.setdefault(kind, {})[zone] = {}
    _os.makedirs(_os.path.dirname(SEQ_FILE), exist_ok=True)
    _json.dump(data, open(SEQ_FILE, 'w'), indent=1)


def seq_save(doc):
    """Record how many sheets of each code this zone used (call before saving)."""
    if not getattr(doc, '_seq_key', None): return
    kind, zone, names = doc._seq_key
    st = TB.get('seq_start', {}) if TB else {}
    cnt = {v: n - doc._seq_from.get(v, int(st.get(v, 1)) - 1) for v, n in doc._tb_seq.items()}
    data = _json.load(open(SEQ_FILE)) if _os.path.exists(SEQ_FILE) else {}
    old = data.setdefault(kind, {}).get(zone)
    data[kind][zone] = cnt
    _os.makedirs(_os.path.dirname(SEQ_FILE), exist_ok=True)
    _json.dump(data, open(SEQ_FILE, 'w'), indent=1)
    if old is not None and old != cnt and zone != names[-1]:
        print(f'(!) sheet numbers: {kind} {zone} now has {cnt} sheets (was {old}) - regenerate the zones after it')


# ---- one project, one style: the same text sizes, length format and notes on every element sheet
ST = dict(name=500, sub=280, panel=260, call=250, len=220, note=170, level=170)


def zone_levels(zone=None):
    """project.json levels, with the zone's own values on top: levels = {founding, top_gb, zones: {"AREA 1": {tof, top_gb}}}.
    founding = bottom of PC (all footings on one level); tof = top of footing fixed (footings drop below it, e.g. a
    basement where the slab, strips and footings share one top level)."""
    L = dict(_PRJ.get('levels', {}))
    L.update((L.pop('zones', None) or {}).get(zone or '', {}))
    return L


def footing_levels(h, L):
    """-> (F.L = bottom of PC, T.O.PC, T.O.F) of a footing h mm deep"""
    if L.get('tof') is not None:
        tof = L['tof']; fl = tof - h / 1000 - 0.10
    else:
        fl = L.get('founding', -3.0); tof = fl + 0.10 + h / 1000
    return round(fl, 3), round(fl + 0.10, 3), round(tof, 3)


def mm(v):
    """Lengths are always written in mm (engineer's rule): integer, no unit."""
    return str(int(round(v)))


def project_notes(*extra):
    return ['ALL DIMENSIONS, BAR LENGTHS AND LAPS IN MM; LEVELS IN M.', *extra,
            'LAP SPLICE = 60 BAR DIAMETER (SBC); MAX. BAR LENGTH 12000.',
            'ALL BENDS CURVED; TIES / STIRRUPS 135-DEG HOOKS x 100.', "fc' = 35 MPa, fy = 420 MPa."]


def fillet(pts, r, closed=False, n=6):
    """Polyline with every corner replaced by an arc of radius r (bars are bent, never sharp). r is clamped so the
    arcs never use more than 45 % of an edge."""
    if r <= 0 or len(pts) < 3: return list(pts)
    m = len(pts)
    idx = range(m) if closed else range(1, m - 1)
    out = [] if closed else [pts[0]]
    for i in idx:
        a, v, b = pts[i - 1], pts[i], pts[(i + 1) % m]
        la, lb = math.dist(a, v), math.dist(b, v)
        if la < 1e-6 or lb < 1e-6: out.append(v); continue
        ua = ((a[0] - v[0]) / la, (a[1] - v[1]) / la); ub = ((b[0] - v[0]) / lb, (b[1] - v[1]) / lb)
        cosg = max(-1.0, min(1.0, ua[0] * ub[0] + ua[1] * ub[1]))
        g = math.acos(cosg)                                      # inner angle at the corner
        if g > math.radians(178) or g < 1e-3: out.append(v); continue
        t = min(r / math.tan(g / 2), 0.45 * la, 0.45 * lb)       # tangent distance
        rr = t * math.tan(g / 2)
        pa = (v[0] + ua[0] * t, v[1] + ua[1] * t); pb = (v[0] + ub[0] * t, v[1] + ub[1] * t)
        bis = (ua[0] + ub[0], ua[1] + ub[1]); hb = math.hypot(*bis)
        dc = rr / math.sin(g / 2)
        c = (v[0] + bis[0] / hb * dc, v[1] + bis[1] / hb * dc)
        a0 = math.atan2(pa[1] - c[1], pa[0] - c[0]); a1 = math.atan2(pb[1] - c[1], pb[0] - c[0])
        da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
        out += [(c[0] + rr * math.cos(a0 + da * k / n), c[1] + rr * math.sin(a0 + da * k / n)) for k in range(n + 1)]
    if not closed: out.append(pts[-1])
    return out


def tie_bar_centres(nm, off):
    """Bar centres just inside every corner of an out-to-out tie outline (for sketches): off = d/2 + tie dia."""
    nn = len(nm); res = []
    for j in range(nn):
        a_, v_, b_ = nm[j - 1], nm[j], nm[(j + 1) % nn]
        ua = ((a_[0] - v_[0]) / math.dist(a_, v_), (a_[1] - v_[1]) / math.dist(a_, v_))
        ub = ((b_[0] - v_[0]) / math.dist(b_, v_), (b_[1] - v_[1]) / math.dist(b_, v_))
        sn = math.sqrt(max(1e-9, (1 - (ua[0] * ub[0] + ua[1] * ub[1])) / 2))
        u_ = (ua[0] + ub[0], ua[1] + ub[1]); h_ = math.hypot(*u_) or 1
        res.append((v_[0] + u_[0] / h_ * off / sn, v_[1] + u_[1] / h_ * off / sn))
    return res


def hooked_tie(pts, bars, tail=75, rc=0):
    """Tie centre line as drawn on the section: open at its top-left corner, where both ends wrap 135 deg around
    the corner bar and run into the core (engineer's note). -> list of polylines."""
    ytop = max(p[1] for p in pts)
    def ang(j):
        a, v, b = pts[j - 1], pts[j], pts[(j + 1) % len(pts)]
        x1, y1, x2, y2 = a[0] - v[0], a[1] - v[1], b[0] - v[0], b[1] - v[1]
        return abs(math.degrees(math.atan2(x1 * y2 - y1 * x2, x1 * x2 + y1 * y2)))
    top = [j for j in range(len(pts)) if abs(pts[j][1] - ytop) < 15]
    sq = [j for j in top if abs(ang(j) - 90) < 10] or top            # a square corner on the top side, leftmost
    i = min(sq, key=lambda j: pts[j][0])
    V = pts[i]; Pa, Pb = pts[i - 1], pts[(i + 1) % len(pts)]
    c = min(bars, key=lambda b: math.dist(b, V))
    ua = ((Pa[0] - V[0]) / math.dist(Pa, V), (Pa[1] - V[1]) / math.dist(Pa, V))
    ub = ((Pb[0] - V[0]) / math.dist(Pb, V), (Pb[1] - V[1]) / math.dist(Pb, V))
    u = (ua[0] + ub[0], ua[1] + ub[1]); u = (u[0] / math.hypot(*u), u[1] / math.hypot(*u))   # into the core (bisector)
    def foot(A):                                                                   # tangent point on edge A-V
        ex, ey = V[0] - A[0], V[1] - A[1]; L = math.hypot(ex, ey)
        tt = ((c[0] - A[0]) * ex + (c[1] - A[1]) * ey) / L ** 2
        return (A[0] + tt * ex, A[1] + tt * ey), (ex / L, ey / L)
    def hook(A):
        T, dv = foot(A)
        rr = math.dist(T, c)
        th = math.atan2(T[1] - c[1], T[0] - c[0])
        sg = 1 if (T[0] - c[0]) * dv[1] - (T[1] - c[1]) * dv[0] > 0 else -1      # +1 = counter-clockwise
        th_end = math.atan2(-u[0], u[1]) if sg > 0 else math.atan2(u[0], -u[1])
        sweep = (th_end - th) * sg % (2 * math.pi)
        arc = [(c[0] + rr * math.cos(th + sg * sweep * k / 16), c[1] + rr * math.sin(th + sg * sweep * k / 16)) for k in range(17)]
        e = arc[-1]
        return T, arc + [(e[0] + u[0] * tail, e[1] + u[1] * tail)]
    Ta, ha = hook(Pa); Tb, hb = hook(Pb)
    n = len(pts)
    body = [Tb] + [pts[(i + k) % n] for k in range(1, n)] + [Ta]
    return [fillet(body, rc) if rc else body, ha, hb]                # every bend curved, never a sharp corner


def opened_tie(pts, bars=None, tail=100, rc=0, swing=25):
    """Tie for the bending sketch / BBS, OPENED at its hook corner (engineer's sample): the side at the hook
    corner (the one going down from it) is swung out by `swing` degrees about its far end, so the two 135-deg hooks stand apart and the closing
    point shows. bars=None: the corner bar is put at rc from both faces. -> (polylines, moved) where moved maps the
    swung side (P, V) -> (P, V') for writing its length along it."""
    if bars is None:                                  # corner bars only: one inside every corner
        bars = []
        n0 = len(pts)
        for j in range(n0):
            a, v, b = pts[j - 1], pts[j], pts[(j + 1) % n0]
            la, lb = math.dist(a, v), math.dist(b, v)
            if la < 1e-6 or lb < 1e-6: continue
            bs = ((a[0] - v[0]) / la + (b[0] - v[0]) / lb, (a[1] - v[1]) / la + (b[1] - v[1]) / lb)
            hb_ = math.hypot(*bs) or 1
            cosg = max(-1, min(1, ((a[0] - v[0]) * (b[0] - v[0]) + (a[1] - v[1]) * (b[1] - v[1])) / la / lb))
            dc = max(rc, 20) / max(math.sin(math.acos(cosg) / 2), 0.2)
            bars.append((v[0] + bs[0] / hb_ * dc, v[1] + bs[1] / hb_ * dc))
    body, ha, hb = hooked_tie(pts, bars, tail=tail, rc=0)
    n = len(pts)
    V = min(pts, key=lambda p: math.dist(p, body[0]) + math.dist(p, body[-1]))     # the hook corner
    Pb, Pa = body[1], body[-2]                        # far ends of the two sides meeting at the hook corner
    cx, cy = sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n
    def rot(p, c, a):
        ca, sa = math.cos(a), math.sin(a)
        return (c[0] + (p[0] - c[0]) * ca - (p[1] - c[1]) * sa, c[1] + (p[0] - c[0]) * sa + (p[1] - c[1]) * ca)
    lo_a, lo_b = V[1] - Pa[1], V[1] - Pb[1]           # swing the side going DOWN from the corner (the sample's left side)
    end_a = lo_a > lo_b + 1 if abs(lo_a - lo_b) > 1 else math.dist(Pa, V) <= math.dist(Pb, V)
    P = Pa if end_a else Pb
    sh_ = min(math.dist(Pa, V), math.dist(Pb, V))
    sw = min(math.radians(swing), math.atan2(max(tail, 0.45 * sh_), math.dist(P, V)))   # long side: a smaller angle
    a = max((sw, -sw), key=lambda a: math.dist(rot(V, P, a), (cx, cy)))
    mvh = lambda h, T: [(q[0] + rot(T, P, a)[0] - T[0], q[1] + rot(T, P, a)[1] - T[1]) for q in h]   # hook moved, not turned
    if end_a:
        body = body[:-1] + [rot(body[-1], P, a)]; ha = mvh(ha, ha[0]); fixed = hb
    else:
        body = [rot(body[0], P, a)] + body[1:]; hb = mvh(hb, hb[0]); fixed = ha
    return [fillet(body, rc) if rc else body, ha, hb], {(tuple(P), tuple(V)): (P, rot(V, P, a)), 'tail': (fixed[-2], fixed[-1])}


def draw_open_tie(sh, pts, x0, y0, k, bars=None, rc=0, tail=100, layer='S-RFT-STIR', width=20, th=None, lab_layer='S-DIM'):
    """Bending sketch of a tie / stirrup, opened at its hook corner (opened_tie), every side written along it and
    100 along the hook tail. pts = out-to-out shape (mm); drawn at scale k with its left edge at x0, bottom at y0.
    Returns the drawn width."""
    th = th or ST['len']
    segs, moved = opened_tie(pts, bars, tail=tail, rc=rc)
    xa = min(p[0] for sg in segs for p in sg); xb = max(p[0] for sg in segs for p in sg)
    Z = lambda p: (x0 + (p[0] - xa) * k, y0 + p[1] * k)
    for sg in segs:
        sh.pline([Z(p) for p in sg], layer, width)
    n = len(pts); cx = sum(p[0] for p in pts) / n; cy = sum(p[1] for p in pts) / n
    for j in range(n):
        e = (tuple(pts[j]), tuple(pts[(j + 1) % n]))
        Ls = math.dist(*e)
        if Ls < 25: continue
        a, b = moved.get(e) or tuple(reversed(moved.get((e[1], e[0]), ()))) or e
        pa, pb = Z(a), Z(b); mx, my = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        if ang > 90.5 or ang <= -89.5: ang += 180
        nx, ny = (a[0] + b[0]) / 2 - cx, (a[1] + b[1]) / 2 - cy; hn = math.hypot(nx, ny) or 1
        sh.text(mm(Ls), mx + nx / hn * th * 1.4, my + ny / hn * th * 1.4, th, lab_layer, rot=ang, align=TA.MIDDLE_CENTER)
    ta, tb = moved['tail']
    tang = math.degrees(math.atan2(tb[1] - ta[1], tb[0] - ta[0]))
    if tang > 90.5 or tang <= -89.5: tang += 180
    pm = Z(((ta[0] + tb[0]) / 2, (ta[1] + tb[1]) / 2)); zc = Z((cx, cy))
    nr = min((math.radians(tang + 90), math.radians(tang - 90)),            # on the side towards the inside of the tie
             key=lambda r: math.dist((pm[0] + math.cos(r), pm[1] + math.sin(r)), zc))
    sh.text(str(int(tail)), pm[0] + th * 1.1 * math.cos(nr), pm[1] + th * 1.1 * math.sin(nr), th * 0.85, lab_layer, rot=tang, align=TA.MIDDLE_CENTER)
    return (xb - xa) * k



class Sheet:
    W, H = 42000, 29700      # A3 at 1:100
    def __init__(self, doc, ox, oy, meta):
        self.doc, self.m, self.ox, self.oy, self.meta = doc, doc.modelspace(), ox, oy, meta
        self.frame()
    def P(self, x, y): return (self.ox + x, self.oy + y)
    def line(self, a, b, layer):
        self.m.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': layer})
    def pline(self, pts, layer, width=0, closed=False, r=0):
        if r: pts = fillet(pts, r, closed)                     # bars are bent: curved corners
        e = self.m.add_lwpolyline([self.P(*p) for p in pts], dxfattribs={'layer': layer, 'const_width': width})
        e.closed = closed; return e
    def text(self, s, x, y, h=250, layer='S-RFT-TXT', rot=0, align=TA.BOTTOM_LEFT, maxw=None):
        t = self.m.add_text(s, height=h, rotation=rot, dxfattribs={'layer': layer, 'style': 'ROMANS'})
        est = len(s) * h * 0.9                                   # rough text width; squeeze to fit a box
        if maxw and est > maxw: t.dxf.width = round(maxw / est, 2)
        t.set_placement(self.P(x, y), align=align); return t
    def break_line(self, a, b, layer='S-GB-CONC', amp=260):
        """Standard break line from a to b (sheet coords, horizontal): straight, with one zig-zag in the middle."""
        (x0, y), (x1, _) = a, b
        m, w = (x0 + x1) / 2, min(amp * 0.7, abs(x1 - x0) / 6)
        self.pline([(x0, y), (m - w, y), (m - w / 3, y + amp), (m + w / 3, y - amp), (m + w, y), (x1, y)], layer)
    def circle(self, x, y, r, layer):
        self.m.add_circle(self.P(x, y), r, dxfattribs={'layer': layer})
    def dim(self, a, b, base, angle=0, text='<>'):
        M = 300                                     # a dimension that would leave the sheet frame is not drawn
        inside = lambda x, y: M <= x <= self.W - M and M <= y <= self.H - M
        line_ok = (M <= base[1] <= self.H - M) if angle % 180 == 0 else (M <= base[0] <= self.W - M)   # the dimension line
        if not (inside(*a) and inside(*b) and line_ok): return None
        d = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle,
                                  dimstyle=getattr(self, 'dimstyle', 'GB100'), text=text, dxfattribs={'layer': 'S-DIM'})
        d.render()
    def mark(self, x, y, n, h=250, layer='S-RFT-TXT'):
        """Bar mark in a hexagon (office convention), centred at x, y."""
        R = h * 1.1
        self.pline([(x + R * math.cos(math.radians(60 * k)), y + R * math.sin(math.radians(60 * k))) for k in range(6)], layer, 0, True)
        self.text(f'{int(n):02d}' if str(n).isdigit() else str(n), x, y, h * 0.75, layer, align=TA.MIDDLE_CENTER)
    def ctext(self, mk, s, x, y, h=250, layer='S-RFT-TXT', rot=0, align=TA.BOTTOM_LEFT, maxw=None):
        """Bar call-out with its mark in a hexagon in front of it. rot 0: (x, y) = lower-left of the hexagon;
        rot 90 with BOTTOM_CENTER: text centred on (x, y) along the bar, hexagon at its lower end."""
        R = h * 1.1
        if rot == 0:
            self.mark(x + R, y + h / 2, mk, h)
            return self.text(s, x + 2 * R + h * 0.35, y, h, layer, maxw=None if maxw is None else maxw - 2 * R)
        t = self.text(s, x, y, h, layer, rot=rot, align=align, maxw=maxw)
        est = len(s) * h * 0.9 * (t.dxf.width if t.dxf.hasattr('width') else 1)
        self.mark(x - R - 20, y - est / 2 - R - h * 0.3, mk, h)          # clear of the bar on the right
        return t
    def hatch_rect(self, x0, y0, x1, y1, layer='S-GB-COL'):
        h = self.m.add_hatch(color=8, dxfattribs={'layer': layer})
        h.paths.add_polyline_path([self.P(x0, y0), self.P(x1, y0), self.P(x1, y1), self.P(x0, y1)], is_closed=True)
        h.set_pattern_fill('ANSI31', scale=20)
        self.pline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True)

    def frame(self):
        if TB: return self.frame_tb()
        W, H = self.W, self.H
        self.pline([(0, 0), (W, 0), (W, H), (0, H)], 'S-FRAME', closed=True)
        self.pline([(500, 500), (W - 500, 500), (W - 500, H - 500), (500, H - 500)], 'S-FRAME', 50, True)
        tx = W - 8200
        self.line((tx, 500), (tx, H - 500), 'S-FRAME')
        m = self.meta
        rows = [('Client:', m['client']), ('Project:', m['project']), ('Site Supervision Consultant :', m['consultant']),
                ('Contractor', m['contractor']), ('Shop Drawings Prepared By:', 'SPAN TECH'),
                ('Drawing Title:', m['title']), ('Reference File:', m['ref']), ('Authored By:', m['author']),
                ('Checked By:', m['checker']), ('Approved By:', m['approver'])]
        y = H - 900
        for k, v in rows:
            self.text(k, tx + 200, y, 200, 'S-TITLE')
            for i, part in enumerate(v.split('\n')):
                self.text(part, tx + 400, y - 450 - i * 380, 280, 'S-TITLE', maxw=7500)
            y -= 1250 + 380 * (v.count('\n'))
            self.line((tx, y + 300), (W - 500, y + 300), 'S-FRAME')
        self.text('SHOP DRAWING', tx + 4100, 6700, 450, 'S-TITLE', align=TA.MIDDLE_CENTER)
        self.text('GENERAL NOTES:', tx + 200, 6000, 220, 'S-TITLE')
        for i, n in enumerate(m.get('notes') or ['ALL DIMENSIONS IN MM UNLESS OTHERWISE SPECIFIED.',
                               'CONCRETE COVER FOR GRADE BEAMS = 40 MM.',
                               'LAP SPLICE = 60 BAR DIAMETER (SBC).',
                               'MAX. BAR LENGTH = 12.0 M.',
                               'STIRRUP HOOKS 135 DEG. - 100 MM.']):
            self.text(f'{i+1}. {n}', tx + 300, 5600 - i * 270, 150, 'S-TITLE', maxw=7600)
        self.text('Drawing Number:', tx + 200, 3700, 200, 'S-TITLE')
        self.text(m['dwg'], tx + 300, 3200, 260, 'S-TITLE')
        self.text(f"Scale: {m.get('scale','AS SHOWN')}   Size: A3   Rev: {m['rev']}", tx + 300, 2600, 220, 'S-TITLE', maxw=7600)
        self.text(f"Rev {m['rev']}  {m['rev_desc']}  {m['date']}", tx + 300, 2100, 200, 'S-TITLE')


def _tb_frame(self):
    """Office / client title block: the block of the template scaled so its paper sheet = this sheet, plus the
    per-sheet values (title, reference, scale, size, drawing number, area / venue / sequence / rev, date)."""
    x0, y0, x1, y1 = TB['paper']
    k = self.W / (x1 - x0)
    self.m.add_blockref(TB['block'], self.P(-x0 * k, -y0 * k), dxfattribs={'xscale': k, 'yscale': k, 'layer': 'S-FRAME'})
    m, c = self.meta, TB.get('code', {})
    venue = m.get('venue') or next((v for key, v in TB.get('venue_by_title', []) if key in m.get('title', '').upper()),
                                    c.get('venue', 'XX'))
    seqs = self.doc._tb_seq
    seqs[venue] = seqs.get(venue, int(TB.get('seq_start', {}).get(venue, 1)) - 1) + 1
    rev = m.get('rev', '00')
    val = dict(title=m.get('title', ''), ref=' '.join(m.get('ref', '').split('\n')), scale=m.get('scale', 'AS SHOWN'),
               size=m.get('size') or TB.get('size', 'A3'), area=m.get('area') or c.get('area', ''), venue=venue, seq=str(seqs[venue]), rev=rev,
               date=m.get('date', ''))
    if c.get('format'):              # project's own numbering, e.g. "{project_id}-{dwg_type}-{orig}-{doc_type}-{venue}-{seq}-{rev}"
        val['dwg'] = c['format'].format(**{**c, **val})
    else:
        val['dwg'] = '-'.join(str(v) for v in (c.get('project_id', ''), c.get('dwg_type', ''), c.get('orig', ''),
                                              c.get('doc_type', ''), val['area'], venue, val['seq'], rev))
    self.meta['dwg_no'] = val['dwg']
    for key, (px, py, h, w) in TB['fields'].items():
        lines = str(val.get(key, '')).split('\n')
        for i, ln in enumerate(lines):
            yy = (py - y0) * k - (i - (len(lines) - 1) / 2) * h * k * 1.6
            t = self.text(ln.strip(), (px - x0) * k, yy, h * k, 'S-TITLE', align=TA.MIDDLE_CENTER)
            t.dxf.style = TB.get('style', 'ROMANS')
            est = len(ln.strip()) * h * k * 0.72                 # squeeze into the cell (wide fonts too)
            if est > w * k: t.dxf.width = round(w * k / est, 2)


Sheet.frame_tb = _tb_frame


# ---------------------------------------------------------------- bar call-outs and BBS (office format)
def callout(n, d, mark, L, s=None, layer=None, stg=False):
    """'15 T 12-12000-150 -STG -B1' = no. of bars, T (high tensile), dia, length mm, spacing mm, staggered, layer
    position. The bar mark is NOT repeated in the text: it is in the hexagon in front (engineer, Oct 2026).
    Spacing / STG / layer only when they apply."""
    t = f"{n} T {d}-{int(round(L))}"                      # engineer: dashes between dia and length
    if s: t += f"-{int(round(s))}"
    if stg: t += " -STG"
    if layer: t += f" -{layer}"
    return t


def unit_mass(d):                     # kg/m, d^2/162 (T16 -> 1.58)
    return d * d / 162.0


class BarList:
    """Package-wide bar marks: one mark per (diameter, shape, length); counts accumulate for the BBS."""
    def __init__(self):
        self.rows = {}
        self.cur = None                       # element being drawn (set by the generator): BBS export per element
    def add(self, d, shape, L, n_in, n_el=1, layer=''):
        key = (d, tuple(shape), int(round(L)))
        r = self.rows.get(key)
        if r is None:
            r = self.rows[key] = dict(mark=len(self.rows) + 1, d=d, shape=shape, L=int(round(L)), n_in=0, n_el=n_el, layer=layer)
        u = r.setdefault('use', {})
        u[str(self.cur)] = u.get(str(self.cur), 0) + n_in * n_el      # bars of this mark in this element type (all of them)
        un = r.setdefault('use_n', {})                                # how many elements carry this mark (0: not counted per element)
        un[str(self.cur)] = un.get(str(self.cur), 0) + (n_el if n_el > 1 else 0)
        if r['n_el'] != n_el:                 # the same bar in elements with different counts: keep the TOTAL right
            r['n_in'] = r['n_in'] * r['n_el'] + n_in * n_el; r['n_el'] = 1
        else:
            r['n_in'] += n_in
        return r['mark']
    def sorted(self):
        return sorted(self.rows.values(), key=lambda r: r['mark'])
    def export(self, path, dwg=None, counts=None):
        """BBS rows (mark, d, shape, L, counts, use per element) + element -> drawing number, for the Excel BBS."""
        import json as _j
        _j.dump(dict(rows=[dict(r, shape=list(r['shape'])) for r in self.sorted()], dwg=dwg or {}, counts=counts or {}), open(path, 'w'), indent=1)


def draw_legend(sh, x, y, g=1):
    """g: geometry factor of a big sheet whose text() already scales the heights."""
    parts = [('15', 'No. OF\nBARS'), ('T', '( HIGH\nTENSILE)'), ('12-', 'BAR\nDIAMETER'),
             ('12000-', 'LENGTH\nOF BAR\nMM'), ('150', 'SPACING\nMM'), ('-STG', 'STAGGERED RFT'), ('- B1', 'LAYER\nPOSITION')]
    sh.mark(x + 280 * g, y + 130 * g, 0, 260)                     # the bar mark: hexagon in front of the call-out
    sh.line((x + 280 * g, y - 180 * g), (x + 280 * g, y - 1450 * g), 'S-RFT-TXT')
    for j, part in enumerate(('BAR', 'MARK')):
        sh.text(part, x + 280 * g, y - (1550 + j * 230) * g, 160, 'S-RFT-TXT', align=TA.TOP_CENTER)
    cx = x + 700 * g
    for i, (v, lab) in enumerate(parts):
        w = (400 + 230 * len(v)) * g
        sh.text(v, cx + w / 2, y, 260, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
        ly = y - (700 + (i % 2) * 500) * g
        sh.line((cx + w / 2, y - 80 * g), (cx + w / 2, ly + 250 * g), 'S-RFT-TXT')
        for j, part in enumerate(lab.split('\n')):
            sh.text(part, cx + w / 2, ly - j * 230 * g, 160, 'S-RFT-TXT', align=TA.TOP_CENTER)
        cx += w + 250 * g


def _symbol(sh, x, y, w, h, shape, d):
    """Small bar sketch with segment lengths, inside a BBS cell (x, y = lower-left, w x h)."""
    kind, seg = shape[0], shape[1:]
    lens = None
    if kind == 'HT':          # rectangular tie / stirrup with 135-deg hooks: drawn opened at the hooks like POLY,
        a_, b_ = seg[0], seg[1]                   # proportions kept within 1:2.5 so a narrow stirrup still reads
        da, db = max(a_, b_ / 2.5), max(b_, a_ / 2.5)
        kind, seg, lens = 'POLY', ((0, 0), (da, 0), (da, db), (0, db)), [a_, b_, a_, b_]
    m = 1
    cy, cx = y + h * 0.45, x + w * 0.2
    if kind == 'S':
        L = w * 0.6
        sh.line((cx, cy), (cx + L, cy), 'S-RFT-TXT'); sh.text(str(seg[0]), cx + L / 2, cy + 60, 130, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
    elif kind in ('U', 'L', 'J'):
        a, run = seg[0], seg[1]; b = seg[2] if len(seg) > 2 else 0
        L = w * 0.6; lg = h * 0.3
        pts = []
        if a: pts.append((cx, cy + lg))
        pts += [(cx, cy), (cx + L, cy)]
        if b: pts.append((cx + L, cy + lg))
        sh.pline(pts, 'S-RFT-TXT', r=60)
        sh.text(str(run), cx + L / 2, cy - 60, 130, 'S-RFT-TXT', align=TA.TOP_CENTER)
        if a: sh.text(str(a), cx - 60, cy + lg / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
        if b: sh.text(str(b), cx + L + 180, cy + lg / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'ST':
        bw, bh = seg[0], seg[1]
        sw, shh = w * 0.25, h * 0.6
        x0, y0 = x + w * 0.35, y + h * 0.2
        sh.pline([(x0, y0), (x0 + sw, y0), (x0 + sw, y0 + shh), (x0, y0 + shh)], 'S-RFT-TXT', 0, True, r=40)
        sh.line((x0, y0 + shh - 60), (x0 + 120, y0 + shh - 180), 'S-RFT-TXT')
        sh.text(str(bw), x0 + sw / 2, y0 - 40, 120, 'S-RFT-TXT', align=TA.TOP_CENTER)
        sh.text(str(bh), x0 + sw + 160, y0 + shh / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'POLY':      # tie of any shape, drawn to its own proportions
        pts = [(a, b) for a, b in seg]
        segs, moved = opened_tie(pts, None, tail=100, rc=15)          # opened at the hooks, as on the sheet
        xa_ = min(p[0] for sg_ in segs for p in sg_)
        bw = (max(p[0] for sg_ in segs for p in sg_) - xa_) or 1; bh = max(p[1] for p in pts) or 1
        kk = min(w * 0.5 / bw, h * 0.5 / bh)
        x0, y0 = x + w * 0.25 - xa_ * kk, y + h * 0.25
        for sg_ in segs:
            sh.pline([(x0 + a * kk, y0 + b * kk) for a, b in sg_], 'S-RFT-TXT', 0, False)
        q = [(x0 + a * kk, y0 + b * kk) for a, b in pts]
        cx, cy = sum(p[0] for p in q) / len(q), sum(p[1] for p in q) / len(q)
        swq = {}                                                          # the swung side written where it is drawn
        for (P_, V_), (_, W_) in [(k_, v_) for k_, v_ in moved.items() if k_ != 'tail']:
            swq[frozenset((pts.index(P_), pts.index(V_)))] = {pts.index(P_): q[pts.index(P_)], pts.index(V_): (x0 + W_[0] * kk, y0 + W_[1] * kk)}
        nt = 120 if len(pts) <= 4 else 95
        for i in range(len(pts)):                      # every side written (engineer's rule)
            a, b = pts[i], pts[(i + 1) % len(pts)]
            Ls = lens[i] if lens else math.dist(a, b)
            if Ls < 25: continue
            i2 = (i + 1) % len(q); o_ = swq.get(frozenset((i, i2)))
            qa, qb = (o_[i], o_[i2]) if o_ else (q[i], q[i2])
            mx, my = (qa[0] + qb[0]) / 2, (qa[1] + qb[1]) / 2
            vert = abs(qa[0] - qb[0]) < abs(qa[1] - qb[1])
            if vert:
                sgn = 1 if mx >= cx else -1
                sh.text(str(int(round(Ls))), mx + sgn * 50, my, nt, 'S-RFT-TXT', rot=90,
                        align=TA.TOP_CENTER if sgn > 0 else TA.BOTTOM_CENTER)
            else:
                sgn = 1 if my >= cy else -1
                sh.text(str(int(round(Ls))), mx, my + sgn * 50, nt, 'S-RFT-TXT',
                        align=TA.BOTTOM_CENTER if sgn > 0 else TA.TOP_CENTER)
    elif kind == 'OPEN':      # open bar of any shape (wall horizontal bar with its hooks), to its own proportions
        pts = [(a, b) for a, b in seg]
        x0_, y0_ = min(p[0] for p in pts), min(p[1] for p in pts)
        bw = (max(p[0] for p in pts) - x0_) or 1; bh = (max(p[1] for p in pts) - y0_) or 1
        kk = min(w * 0.5 / bw, h * 0.62 / bh)
        X, Y = x + w * 0.25, y + h * 0.18
        q = [(X + (a - x0_) * kk, Y + (b - y0_) * kk) for a, b in pts]
        sh.pline(q, 'S-RFT-TXT', 0, False, r=25)
        big = max(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        for (a, b), (qa, qb) in zip(zip(pts, pts[1:]), zip(q, q[1:])):
            if math.dist(a, b) < 0.3 * big: continue
            sh.text(str(int(round(math.dist(a, b)))), (qa[0] + qb[0]) / 2, (qa[1] + qb[1]) / 2 + 40, 110, 'S-RFT-TXT',
                    rot=90 if abs(qa[0] - qb[0]) < 1 else 0, align=TA.BOTTOM_CENTER)
    elif kind == 'PROF':      # bar following a sloped profile (pool floor) + its legs: x / z scaled apart, every part written
        pts = [(a, b) for a, b in seg]
        x0_, y0_ = min(p[0] for p in pts), min(p[1] for p in pts)
        bw = (max(p[0] for p in pts) - x0_) or 1; bh = (max(p[1] for p in pts) - y0_) or 1
        kx = w * 0.6 / bw; ky = min(h * 0.5 / bh, 40 * kx) if bh > 1 else 0
        X, Y = x + w * 0.2, y + h * 0.22
        q = [(X + (a - x0_) * kx, Y + (b - y0_) * ky) for a, b in pts]
        if ky * bh < h * 0.15:                                   # flat bar: lift the legs so they show
            q = [(qx, Y + (h * 0.3 if (i in (0, len(q) - 1) and abs(pts[i][0] - pts[1 if i == 0 else -2][0]) < 1) else 0)) for i, (qx, qy) in enumerate(q)]
        sh.pline(q, 'S-RFT-TXT', 0, False, r=20)
        for (a, b), (qa, qb) in zip(zip(pts, pts[1:]), zip(q, q[1:])):
            Ls = math.dist(a, b)
            if Ls < 100: continue
            vert = abs(a[0] - b[0]) < 1
            sh.text(str(int(round(Ls))), (qa[0] + qb[0]) / 2 + (-50 if vert else 0), (qa[1] + qb[1]) / 2 + (0 if vert else 40), 110,
                    'S-RFT-TXT', rot=90 if vert else 0, align=TA.BOTTOM_CENTER)
    elif kind == 'CH':        # chair: foot / leg / top / leg / foot
        f_, lg, top = seg
        u = w * 0.13; hh = h * 0.42; x0 = x + w * 0.12; y0 = y + h * 0.18
        sh.pline([(x0, y0), (x0 + u, y0), (x0 + u, y0 + hh), (x0 + 2.6 * u, y0 + hh), (x0 + 2.6 * u, y0), (x0 + 3.6 * u, y0)], 'S-RFT-TXT', r=30)
        # every side with its own length (engineer's note)
        sh.text(str(f_), x0 + u / 2, y0 + 50, 120, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
        sh.text(str(f_), x0 + 3.1 * u, y0 + 50, 120, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
        sh.text(str(top), x0 + 1.8 * u, y0 + hh + 50, 120, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
        sh.text(str(lg), x0 + u - 50, y0 + hh / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
        sh.text(str(lg), x0 + 2.6 * u + 170, y0 + hh / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)


def draw_bbs(doc, first_idx, rows, meta, Sheet_=None):
    """BBS sheets in the office table layout. Returns the number of sheets added."""
    S = Sheet_ or Sheet
    cols = [('Position', 2000), ('Steel grade', 1900), ('Diameter', 1900), ('in the\nelement', 2100), ('of elements', 2100),
            ('total', 1900), ('Symbol ( mm)', 6200), ('Length ( m)', 2300), ('Mass ( kg)', 2300), ('Total mass\n( kg)', 2500)]
    per = 22
    pages = [rows[i:i + per] for i in range(0, len(rows), per)] or [[]]
    grand = sum(r['n_in'] * r['L'] / 1000 * unit_mass(r['d']) * r['n_el'] for r in rows)
    for pi, page in enumerate(pages):
        m = dict(meta); m['title'] = (meta.get('title', '').split('\n')[0] + '\nBAR BENDING SCHEDULE (BBS)').strip()
        m['dwg'] = meta.get('dwg', '') + f'-BBS{pi + 1:02d}'
        sh = S(doc, 0, -(first_idx + pi) * 32000, m)
        x0, ytop = 1800, 27600
        W = sum(w for _, w in cols)
        sh.text('BBS', x0 + W / 2, ytop - 450, 300, 'S-TITLE', align=TA.MIDDLE_CENTER)
        hy = ytop - 900; rh = 950; head = 1700
        sh.pline([(x0, ytop), (x0 + W, ytop), (x0 + W, hy - head - rh * len(page)), (x0, hy - head - rh * len(page))], 'S-FRAME', 0, True)
        sh.line((x0, hy), (x0 + W, hy), 'S-FRAME'); sh.line((x0, hy - head), (x0 + W, hy - head), 'S-FRAME')
        cx = x0
        for i, (name, w) in enumerate(cols):
            if i > 0: sh.line((cx, hy if i not in (4, 5) else hy - head / 2), (cx, hy - head - rh * len(page)), 'S-FRAME')
            yy = hy - head / 2 if i not in (3, 4, 5) else hy - head * 0.75
            for j, part in enumerate(name.split('\n')):
                sh.text(part, cx + w / 2, yy + 120 - j * 260, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
            cx += w
        nx = x0 + sum(w for _, w in cols[:3])
        sh.line((nx, hy - head / 2), (nx + sum(w for _, w in cols[3:6]), hy - head / 2), 'S-FRAME')
        sh.text('Number', nx + sum(w for _, w in cols[3:6]) / 2, hy - head / 4, 220, 'S-TITLE', align=TA.MIDDLE_CENTER)
        for k, r in enumerate(page):
            y = hy - head - rh * (k + 1)
            sh.line((x0, y), (x0 + W, y), 'S-FRAME')
            mass = r['n_in'] * r['L'] / 1000 * unit_mass(r['d'])
            vals = [None, 'T', str(r['d']), str(r['n_in']), str(r['n_el']), str(r['n_in'] * r['n_el']), None,
                    f"{r['L'] / 1000:.2f}", f"{mass:.2f}", f"{mass * r['n_el']:.2f}"]
            cx = x0
            for i, (name, w) in enumerate(cols):
                if i == 0:
                    sh.mark(cx + w / 2, y + rh / 2, r['mark'], 240, 'S-TITLE')
                elif i == 6:
                    _symbol(sh, cx, y, w, rh, r['shape'], r['d'])
                else:
                    sh.text(vals[i], cx + w / 2, y + rh / 2, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                cx += w
        if pi == len(pages) - 1:
            y = hy - head - rh * len(page) - 700
            sh.text(f"TOTAL STEEL WEIGHT = {grand:,.2f} kg  ({grand / 1000:.3f} t)", x0 + W, y, 260, 'S-TITLE', align=TA.MIDDLE_RIGHT)
    return len(pages)


def draw_bbs_grouped(doc, first_idx, rows, meta, groups, Sheet_=None):
    """BBS with ONE TABLE PER ELEMENT (engineer, 25-10-2026: a BBS per footing / per neck model, titled with its
    name, its own total), then a summary per diameter. groups: [(title, element key in BarList 'use', no. of
    elements)]. Marks stay package-wide (the same mark may appear in two tables with that element's count).
    Returns the number of sheets added."""
    S = Sheet_ or Sheet
    cols = [('Position', 2000), ('Steel grade', 1900), ('Diameter', 1900), ('in the\nelement', 2100), ('of elements', 2100),
            ('total', 1900), ('Symbol ( mm)', 6200), ('Length ( m)', 2300), ('Mass ( kg)', 2300), ('Total mass\n( kg)', 2500)]
    W = sum(w for _, w in cols); x0 = 1800; rh = 950; head = 1700; tit = 900; gap = 1500
    tables = []
    for title, key, nel in groups:
        rs = []
        for r in rows:
            q = r.get('use', {}).get(str(key), 0)
            if q:
                ne = r.get('use_n', {}).get(str(key)) or nel             # elements that carry this mark (necks: per footing mesh)
                rs.append(dict(r, n_in=round(q / max(1, ne)), n_el=ne, q=q))
        if rs: tables.append((title, rs))
    by_d = {}
    for _, rs in tables:
        for r in rs: by_d[r['d']] = by_d.get(r['d'], 0) + r['q'] * r['L'] / 1000 * unit_mass(r['d'])
    pages, cur, y = [], [], 27600
    for t in tables:
        h = tit + head + rh * len(t[1]) + 700
        if cur and y - h < 1500: pages.append(cur); cur, y = [], 27600
        cur.append(t); y -= h + gap
    sumh = tit + 1000 + 700 * (len(by_d) + 1)
    if cur and y - sumh < 1500: pages.append(cur); cur = []
    cur.append(('__SUMMARY__', None)); pages.append(cur)
    for pi, page in enumerate(pages):
        m = dict(meta); m['title'] = (meta.get('title', '').split('\n')[0] + '\nBAR BENDING SCHEDULE (BBS)').strip()
        m['dwg'] = meta.get('dwg', '') + f'-BBS{pi + 1:02d}'
        sh = S(doc, 0, -(first_idx + pi) * 32000, m)
        ytop = 27600
        for title, rs in page:
            if title == '__SUMMARY__':
                ds_ = sorted(by_d); cw = [3000, 3500, 4000]; WW = sum(cw)
                sh.pline([(x0, ytop), (x0 + WW, ytop), (x0 + WW, ytop - tit - 1000 - 700 * (len(ds_) + 1)), (x0, ytop - tit - 1000 - 700 * (len(ds_) + 1))], 'S-FRAME', 0, True)
                sh.text('SUMMARY OF STEEL BY DIAMETER (NET, NO WASTE)', x0 + WW / 2, ytop - tit / 2, 280, 'S-TITLE', align=TA.MIDDLE_CENTER)
                yy = ytop - tit; sh.line((x0, yy), (x0 + WW, yy), 'S-FRAME')
                for i, (hd, cx_) in enumerate(zip(('Diameter (mm)', 'Unit mass (kg/m)', 'Total mass (kg)'), (0, cw[0], cw[0] + cw[1]))):
                    sh.text(hd, x0 + cx_ + cw[i] / 2, yy - 500, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                    if i: sh.line((x0 + cx_, yy), (x0 + cx_, ytop - tit - 1000 - 700 * (len(ds_) + 1)), 'S-FRAME')
                yy -= 1000; sh.line((x0, yy), (x0 + WW, yy), 'S-FRAME')
                for d in ds_ + ['TOTAL']:
                    v = (str(d), f'{unit_mass(d):.3f}', f'{by_d[d]:,.2f}') if d != 'TOTAL' else ('TOTAL', '', f'{sum(by_d.values()):,.2f}  ({sum(by_d.values()) / 1000:.3f} t)')
                    for i, (vv, cx_) in enumerate(zip(v, (0, cw[0], cw[0] + cw[1]))):
                        sh.text(vv, x0 + cx_ + cw[i] / 2, yy - 350, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                    yy -= 700; sh.line((x0, yy), (x0 + WW, yy), 'S-FRAME')
                continue
            bot = ytop - tit - head - rh * len(rs)
            sh.pline([(x0, ytop), (x0 + W, ytop), (x0 + W, bot), (x0, bot)], 'S-FRAME', 0, True)
            sh.text(title, x0 + W / 2, ytop - tit / 2, 300, 'S-TITLE', align=TA.MIDDLE_CENTER)
            hy = ytop - tit
            sh.line((x0, hy), (x0 + W, hy), 'S-FRAME'); sh.line((x0, hy - head), (x0 + W, hy - head), 'S-FRAME')
            cx = x0
            for i, (name, w) in enumerate(cols):
                if i > 0: sh.line((cx, hy if i not in (4, 5) else hy - head / 2), (cx, bot), 'S-FRAME')
                yy = hy - head / 2 if i not in (3, 4, 5) else hy - head * 0.75
                for j, part in enumerate(name.split('\n')):
                    sh.text(part, cx + w / 2, yy + 120 - j * 260, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                cx += w
            nx = x0 + sum(w for _, w in cols[:3])
            sh.line((nx, hy - head / 2), (nx + sum(w for _, w in cols[3:6]), hy - head / 2), 'S-FRAME')
            sh.text('Number', nx + sum(w for _, w in cols[3:6]) / 2, hy - head / 4, 220, 'S-TITLE', align=TA.MIDDLE_CENTER)
            tot = 0
            for k, r in enumerate(rs):
                y = hy - head - rh * (k + 1)
                sh.line((x0, y), (x0 + W, y), 'S-FRAME')
                mass_el = r['q'] / r['n_el'] * r['L'] / 1000 * unit_mass(r['d'])   # average per element when VAR
                total = r['q'] * r['L'] / 1000 * unit_mass(r['d']); tot += total
                per_ = r['q'] / r['n_el']
                vals = [None, 'T', str(r['d']), f"{per_:g}" if abs(per_ - round(per_)) < 1e-6 else 'VAR', str(r['n_el']), str(r['q']), None,
                        f"{r['L'] / 1000:.3f}", f"{mass_el:.2f}", f"{total:.2f}"]
                cx = x0
                for i, (name, w) in enumerate(cols):
                    if i == 0: sh.mark(cx + w / 2, y + rh / 2, r['mark'], 240, 'S-TITLE')
                    elif i == 6: _symbol(sh, cx, y, w, rh, r['shape'], r['d'])
                    else: sh.text(vals[i], cx + w / 2, y + rh / 2, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                    cx += w
            sh.text(f"TOTAL STEEL WEIGHT ({title}) = {tot:,.2f} kg  ({tot / 1000:.3f} t)", x0 + W, bot - 450, 240, 'S-TITLE', align=TA.MIDDLE_RIGHT)
            ytop = bot - 700 - gap
    return len(pages)


# ---------------------------------------------------------------- bars longer than a stock bar (engineer, Oct 2026)
def lap_patterns(T, lp, stock=12000):
    """A bar of developed length T (legs included) longer than the stock: pieces lapped lp, in TWO patterns used on
    alternate bars so that the laps of neighbouring bars are STAGGERED (lap centres >= 1.3 lp apart) - never all the
    laps in one line (engineer: "the laps were all in the middle of the raft").
    -> [pattern A, pattern B], each a list of (t0, t1) along the developed bar; [[(0, T)]] when no lap is needed."""
    if T <= stock: return [[(0, T)]]
    up = lambda v: math.ceil(v / 10) * 10
    def ivs(cuts):
        b = [0] + cuts + [T]
        return [(max(0, b[i] - (lp / 2 if i else 0)), min(T, b[i + 1] + (lp / 2 if i + 1 < len(b) - 1 else 0))) for i in range(len(b) - 1)]
    p = math.ceil((T - lp) / (stock - lp))
    while True:
        cA = [i * T / p for i in range(1, p)]
        for dl in (1.3 * lp, -1.3 * lp, 1.6 * lp, -1.6 * lp):
            cB = [c + dl for c in cA]
            A, B = ivs(cA), ivs(cB)
            if all(0 < t1 - t0 <= stock for t0, t1 in A + B):
                return [[(t0, t0 + up(t1 - t0)) if t1 < T else (T - up(T - t0), T) for t0, t1 in A],
                        [(t0, t0 + up(t1 - t0)) if t1 < T else (T - up(T - t0), T) for t0, t1 in B]]
        p += 1


def piece_shape(t0, t1, T, leg_a, leg_b):
    """BBS shape of a piece of a bar with legs leg_a (start) / leg_b (end)."""
    L = int(round(t1 - t0))
    a = leg_a if t0 <= 1 and leg_a else 0; b = leg_b if t1 >= T - 1 and leg_b else 0
    if a and b: return ('U', a, L - a - b, b), L
    if a: return ('L', a, L - a, 0), L
    if b: return ('L', b, L - b, 0), L
    return ('S', L), L


def lapped_marks(bl, d, T, leg_a, leg_b, n, n_el, tag, lp=None, stock=12000):
    """BarList marks of n bars of developed length T: one pattern = one mark set; pattern A on half the bars,
    B on the other half. -> (patterns, [(mark, count, L)])"""
    lp = lp or 60 * d
    pats = lap_patterns(T, lp, stock)
    counts = [math.ceil(n / len(pats)), n - math.ceil(n / len(pats))] if len(pats) == 2 else [n]
    tot = {}
    for pat, c in zip(pats, counts):
        for t0, t1 in pat:
            shp, L = piece_shape(t0, t1, T, leg_a, leg_b)
            tot[(shp, L)] = tot.get((shp, L), 0) + c
    marks = [(bl.add(d, shp, L, c, n_el, tag), c, L) for (shp, L), c in tot.items()]
    return pats, marks
