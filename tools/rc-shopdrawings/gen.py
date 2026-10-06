"""Shared helpers: A3 1:100 sheet frame + title block in model space, layers, dim style, schedule, bar rules."""
import math, pickle, sys
import ezdxf
from ezdxf.enums import TextEntityAlignment as TA

import json as _json, os as _os
# beam schedule comes from the project file: {"schedule": {"GB1": {"b":200,"h":700,"nb":4,"db":16,"nt":4,"dt":16,"ds":10,"s":125}, ...}}
SCHED = _json.load(open(_os.environ.get('RC_PROJECT', 'project.json')))['schedule']
COVER = 40          # grade beams, contact with soil
STOCK = 12000
LAP = 60            # x d
HOOK = 135
def leg(d): return 200 if d <= 16 else 250
def lap(d): return LAP * d

LAYERS = {  # name: color
    'S-GB-CONC': 7, 'S-GB-COL': 8, 'S-AXIS': 1, 'S-AXIS-TXT': 1,
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
    return doc


# ---- one project, one style: the same text sizes, length format and notes on every element sheet
ST = dict(name=500, sub=280, panel=260, call=250, len=220, note=170, level=170)


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
        d = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle,
                                  dimstyle='GB100', text=text, dxfattribs={'layer': 'S-DIM'})
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


# ---------------------------------------------------------------- bar call-outs and BBS (office format)
def callout(n, d, mark, L, s=None, layer=None, stg=False):
    """'15 T 12 00 12000 150 -STG -B1' = no. of bars, T (high tensile), dia, bar mark, length mm, spacing mm,
    staggered, layer position. Spacing / STG / layer only when they apply."""
    t = f"{n} T {d}-{mark:02d}-{int(round(L))}"          # engineer: dashes between dia, mark and length
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
    def add(self, d, shape, L, n_in, n_el=1, layer=''):
        key = (d, tuple(shape), int(round(L)))
        r = self.rows.get(key)
        if r is None:
            r = self.rows[key] = dict(mark=len(self.rows) + 1, d=d, shape=shape, L=int(round(L)), n_in=0, n_el=n_el, layer=layer)
        r['n_in'] += n_in
        return r['mark']
    def sorted(self):
        return sorted(self.rows.values(), key=lambda r: r['mark'])


def draw_legend(sh, x, y):
    """Key of the call-out, as on the office sheets."""
    parts = [('15', 'No. OF\nBARS'), ('T', '( HIGH\nTENSILE)'), ('12-', 'BAR\nDIAMETER'), ('00-', 'BAR\nMARK'),
             ('12000-', 'LENGTH\nOF BAR\nMM'), ('150', 'SPACING\nMM'), ('-STG', 'STAGGERED RFT'), ('- B1', 'LAYER\nPOSITION')]
    cx = x
    for i, (v, lab) in enumerate(parts):
        w = 400 + 230 * len(v)
        sh.text(v, cx + w / 2, y, 260, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
        ly = y - 700 - (i % 2) * 500
        sh.line((cx + w / 2, y - 80), (cx + w / 2, ly + 250), 'S-RFT-TXT')
        for j, part in enumerate(lab.split('\n')):
            sh.text(part, cx + w / 2, ly - j * 230, 160, 'S-RFT-TXT', align=TA.TOP_CENTER)
        cx += w + 250


def _symbol(sh, x, y, w, h, shape, d):
    """Small bar sketch with segment lengths, inside a BBS cell (x, y = lower-left, w x h)."""
    kind, seg = shape[0], shape[1:]
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
        bw = max(p[0] for p in pts) or 1; bh = max(p[1] for p in pts) or 1
        kk = min(w * 0.45 / bw, h * 0.7 / bh)
        x0, y0 = x + w * 0.3, y + h * 0.15
        sh.pline([(x0 + a * kk, y0 + b * kk) for a, b in pts], 'S-RFT-TXT', 0, True, r=40)
        sh.text(str(int(bw)), x0 + bw * kk / 2, y0 - 40, 120, 'S-RFT-TXT', align=TA.TOP_CENTER)
        sh.text(str(int(bh)), x0 + bw * kk + 160, y0 + bh * kk / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'CH':        # chair: foot / leg / top / leg / foot
        f_, lg, top = seg
        u = w * 0.12; hh = h * 0.35; x0 = x + w * 0.15; y0 = y + h * 0.25
        sh.pline([(x0, y0), (x0 + u, y0), (x0 + u, y0 + hh), (x0 + 2.5 * u, y0 + hh), (x0 + 2.5 * u, y0), (x0 + 3.5 * u, y0)], 'S-RFT-TXT', r=30)
        sh.text(f"{f_}/{lg}/{top}", x0 + 4 * u, y0, 120, 'S-RFT-TXT')


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
