"""Sheets of any size -> one multi-page black & white PDF.

usage: python3 topdf_sheets.py drawing.dxf out.pdf sheets.json
sheets.json: [[x0, y0, W, H, paper_w_mm, paper_h_mm], ...] - the model-space window of every sheet (written by the
generator next to the DXF). Each page renders only the entities whose box centre is inside its window."""
import json, sys
import ezdxf, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from ezdxf import bbox
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, HatchPolicy

f, out, sj = sys.argv[1:4]
doc = ezdxf.readfile(f); msp = doc.modelspace()
sheets = json.load(open(sj))
cen = {}
for e in msp:
    try:
        b = bbox.extents([e], fast=True)
        if b.has_data: cen[e.dxf.handle] = ((b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2)
    except Exception:
        pass
cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK, min_lineweight=0.1,
                    hatch_policy=HatchPolicy.SHOW_APPROXIMATE_PATTERN)          # light PDF (patterns as PDF hatches)
only = [int(v) for v in sys.argv[4].split(',')] if len(sys.argv) > 4 else None
with PdfPages(out) as pdf:
    for i, (x0, y0, W, H, pw, ph) in enumerate(sheets):
        if only and i not in only: continue
        inside = lambda e: (lambda c: c is not None and x0 <= c[0] <= x0 + W and y0 <= c[1] <= y0 + H)(cen.get(e.dxf.handle))
        fig = plt.figure(figsize=(pw / 25.4, ph / 25.4)); ax = fig.add_axes([0, 0, 1, 1])
        Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(msp, finalize=False, filter_func=inside)
        ax.set_xlim(x0, x0 + W); ax.set_ylim(y0, y0 + H); ax.set_aspect('equal'); ax.axis('off')
        pdf.savefig(fig); plt.close(fig)
        print('page', i + 1, flush=True)
