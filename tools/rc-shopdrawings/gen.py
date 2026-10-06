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
        for i, n in enumerate(['ALL DIMENSIONS IN MM UNLESS OTHERWISE SPECIFIED.',
                               'CONCRETE COVER FOR GRADE BEAMS = 40 MM.',
                               'LAP SPLICE = 60 BAR DIAMETER (SBC).',
                               'MAX. BAR LENGTH = 12.0 M.',
                               'STIRRUP HOOKS 135 DEG. - 100 MM.']):
            self.text(f'{i+1}. {n}', tx + 300, 5550 - i * 330, 170, 'S-TITLE')
        self.text('Drawing Number:', tx + 200, 3700, 200, 'S-TITLE')
        self.text(m['dwg'], tx + 300, 3200, 260, 'S-TITLE')
        self.text(f"Scale: {m.get('scale','AS SHOWN')}   Size: A3   Rev: {m['rev']}", tx + 300, 2600, 220, 'S-TITLE')
        self.text(f"Rev {m['rev']}  {m['rev_desc']}  {m['date']}", tx + 300, 2100, 200, 'S-TITLE')
