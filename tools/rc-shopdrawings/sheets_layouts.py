"""Model-space sheets -> one paper-space layout per sheet (engineer, BLSC 07-11-2026: "the frame, the panda and all
sheet data in the LAYOUT, MODEL for the drawing only").

For every sheet window of OUT.sheets.json ([x0, y0, W, H, paper_w, paper_h, number]): the title block INSERT
(S-FRAME) and the S-TITLE texts of that window move to a new layout named after the sheet number, scaled to the
paper (mm); one viewport shows the model window at the sheet scale. Everything else stays in model space.
usage: python3 sheets_layouts.py IN.dxf IN.sheets.json OUT.dxf
"""
import json, sys
import ezdxf
from ezdxf.math import Matrix44
from ezdxf import bbox

doc = ezdxf.readfile(sys.argv[1]); sheets = json.load(open(sys.argv[2])); msp = doc.modelspace()
MOVE = ('S-FRAME', 'S-TITLE')
cand = []
for e in msp:
    if e.dxf.layer not in MOVE: continue
    try:
        b = bbox.extents([e], fast=True)
        if b.has_data: cand.append((e, b.center))
    except Exception:
        pass
if 'VIEWPORTS' not in doc.layers: doc.layers.add('VIEWPORTS', color=8).dxf.plot = 0
for i, sh in enumerate(sheets):
    x0, y0, W, H, pw, ph = sh[:6]
    name = str(sh[6]) if len(sh) > 6 else f'S{i + 1:02d}'
    lay = doc.layouts.new(name)
    lay.page_setup(size=(pw, ph), margins=(0, 0, 0, 0), units='mm')
    k = pw / W
    m = Matrix44.translate(-x0, -y0, 0) @ Matrix44.scale(k, k, k)
    for e, c in cand:
        if x0 <= c[0] <= x0 + W and y0 <= c[1] <= y0 + H:
            msp.move_to_layout(e, lay); e.transform(m)
    vp = lay.add_viewport(center=(pw / 2, ph / 2), size=(pw, ph), view_center_point=(x0 + W / 2, y0 + H / 2), view_height=H)
    vp.dxf.status = 1; vp.dxf.layer = 'VIEWPORTS'
for nm in [l.name for l in doc.layouts if l.name.startswith('Layout')]:
    try: doc.layouts.delete(nm)
    except Exception: pass
for i, sh in enumerate(sheets):
    doc.layouts.get(str(sh[6]) if len(sh) > 6 else f'S{i + 1:02d}').dxf.taborder = i + 1
au = doc.audit(); print('audit', len(au.errors), 'errors,', len(sheets), 'layouts')
doc.saveas(sys.argv[3])
