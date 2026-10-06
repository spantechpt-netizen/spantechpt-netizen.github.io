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


class Sheet:
    W, H = 42000, 29700      # A3 at 1:100
    def __init__(self, doc, ox, oy, meta):
        self.doc, self.m, self.ox, self.oy, self.meta = doc, doc.modelspace(), ox, oy, meta
        self.frame()
    def P(self, x, y): return (self.ox + x, self.oy + y)
    def line(self, a, b, layer):
        self.m.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': layer})
    def pline(self, pts, layer, width=0, closed=False):
        e = self.m.add_lwpolyline([self.P(*p) for p in pts], dxfattribs={'layer': layer, 'const_width': width})
        e.closed = closed; return e
    def text(self, s, x, y, h=250, layer='S-RFT-TXT', rot=0, align=TA.BOTTOM_LEFT):
        t = self.m.add_text(s, height=h, rotation=rot, dxfattribs={'layer': layer, 'style': 'ROMANS'})
        t.set_placement(self.P(x, y), align=align); return t
    def circle(self, x, y, r, layer):
        self.m.add_circle(self.P(x, y), r, dxfattribs={'layer': layer})
    def dim(self, a, b, base, angle=0, text='<>'):
        d = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle,
                                  dimstyle='GB100', text=text, dxfattribs={'layer': 'S-DIM'})
        d.render()
    def mark(self, x, y, n, h=250):
        self.circle(x, y, h * 0.9, 'S-RFT-TXT')
        self.text(str(n), x, y, h, align=TA.MIDDLE_CENTER)
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
                self.text(part, tx + 400, y - 450 - i * 380, 280, 'S-TITLE')
            y -= 1250 + 380 * (v.count('\n'))
            self.line((tx, y + 300), (W - 500, y + 300), 'S-FRAME')
        self.text('SHOP DRAWING', tx + 4100, 6700, 450, 'S-TITLE', align=TA.MIDDLE_CENTER)
        self.text('GENERAL NOTES:', tx + 200, 6000, 220, 'S-TITLE')
        for i, n in enumerate(m.get('notes') or ['ALL DIMENSIONS IN MM UNLESS OTHERWISE SPECIFIED.',
                               'CONCRETE COVER FOR GRADE BEAMS = 40 MM.',
                               'LAP SPLICE = 60 BAR DIAMETER (SBC).',
                               'MAX. BAR LENGTH = 12.0 M.',
                               'STIRRUP HOOKS 135 DEG. - 100 MM.']):
            self.text(f'{i+1}. {n}', tx + 300, 5550 - i * 330, 170, 'S-TITLE')
        self.text('Drawing Number:', tx + 200, 3700, 200, 'S-TITLE')
        self.text(m['dwg'], tx + 300, 3200, 260, 'S-TITLE')
        self.text(f"Scale: {m.get('scale','AS SHOWN')}   Size: A3   Rev: {m['rev']}", tx + 300, 2600, 220, 'S-TITLE')
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
        sh.pline(pts, 'S-RFT-TXT')
        sh.text(str(run), cx + L / 2, cy - 60, 130, 'S-RFT-TXT', align=TA.TOP_CENTER)
        if a: sh.text(str(a), cx - 60, cy + lg / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
        if b: sh.text(str(b), cx + L + 180, cy + lg / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'ST':
        bw, bh = seg[0], seg[1]
        sw, shh = w * 0.25, h * 0.6
        x0, y0 = x + w * 0.35, y + h * 0.2
        sh.pline([(x0, y0), (x0 + sw, y0), (x0 + sw, y0 + shh), (x0, y0 + shh)], 'S-RFT-TXT', 0, True)
        sh.line((x0, y0 + shh - 60), (x0 + 120, y0 + shh - 180), 'S-RFT-TXT')
        sh.text(str(bw), x0 + sw / 2, y0 - 40, 120, 'S-RFT-TXT', align=TA.TOP_CENTER)
        sh.text(str(bh), x0 + sw + 160, y0 + shh / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'POLY':      # tie of any shape, drawn to its own proportions
        pts = [(a, b) for a, b in seg]
        bw = max(p[0] for p in pts) or 1; bh = max(p[1] for p in pts) or 1
        kk = min(w * 0.45 / bw, h * 0.7 / bh)
        x0, y0 = x + w * 0.3, y + h * 0.15
        sh.pline([(x0 + a * kk, y0 + b * kk) for a, b in pts], 'S-RFT-TXT', 0, True)
        sh.text(str(int(bw)), x0 + bw * kk / 2, y0 - 40, 120, 'S-RFT-TXT', align=TA.TOP_CENTER)
        sh.text(str(int(bh)), x0 + bw * kk + 160, y0 + bh * kk / 2, 120, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER)
    elif kind == 'CH':        # chair: foot / leg / top / leg / foot
        f_, lg, top = seg
        u = w * 0.12; hh = h * 0.35; x0 = x + w * 0.15; y0 = y + h * 0.25
        sh.pline([(x0, y0), (x0 + u, y0), (x0 + u, y0 + hh), (x0 + 2.5 * u, y0 + hh), (x0 + 2.5 * u, y0), (x0 + 3.5 * u, y0)], 'S-RFT-TXT')
        sh.text(f"{f_}/{lg}/{top}", x0 + 4 * u, y0, 120, 'S-RFT-TXT')


def draw_bbs(doc, first_idx, rows, meta, Sheet_=None):
    """BBS sheets in the office table layout. Returns the number of sheets added."""
    S = Sheet_ or Sheet
    cols = [('Position', 2000), ('Steel grade', 1900), ('Diameter', 1900), ('in the\nelement', 2100), ('of elements', 2100),
            ('total', 1900), ('Symbol ( m)', 6200), ('Length ( m)', 2300), ('Mass ( kg)', 2300), ('Total mass\n( kg)', 2500)]
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
                    sh.circle(cx + w / 2, y + rh / 2, 260, 'S-TITLE'); sh.text(str(r['mark']), cx + w / 2, y + rh / 2, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                elif i == 6:
                    _symbol(sh, cx, y, w, rh, r['shape'], r['d'])
                else:
                    sh.text(vals[i], cx + w / 2, y + rh / 2, 200, 'S-TITLE', align=TA.MIDDLE_CENTER)
                cx += w
        if pi == len(pages) - 1:
            y = hy - head - rh * len(page) - 700
            sh.text(f"TOTAL STEEL WEIGHT = {grand:,.2f} kg  ({grand / 1000:.3f} t)", x0 + W, y, 260, 'S-TITLE', align=TA.MIDDLE_RIGHT)
    return len(pages)
