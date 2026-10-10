"""Render a DXF layout to PNG for visual checks (needs: pip install ezdxf matplotlib).

usage: python3 render_dxf.py <file.dxf> <Model|LayoutName> <out.png> [px=4000] [xmin,ymin,xmax,ymax] [--bw]
The window (5th argument, model units = mm) zooms on one spot of the sheet; --bw renders every layer black.
"""
import sys, ezdxf
from ezdxf import recover, bbox
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, ColorPolicy, BackgroundPolicy
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
f, layout, out = sys.argv[1], sys.argv[2], sys.argv[3]
px = int(sys.argv[4]) if len(sys.argv) > 4 else 4000
win = [float(v) for v in sys.argv[5].split(',')] if len(sys.argv) > 5 else None  # xmin,ymin,xmax,ymax
doc, aud = recover.readfile(f)
lay = doc.modelspace() if layout == 'Model' else doc.layouts.get(layout)
ext = bbox.extents(lay, fast=True)
if win: x0, y0, x1, y1 = win
else: x0, y0 = ext.extmin.x, ext.extmin.y; x1, y1 = ext.extmax.x, ext.extmax.y
w, h = x1 - x0, y1 - y0
fig = plt.figure(figsize=(px / 100, px / 100 * h / w), dpi=100)
ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
ctx = RenderContext(doc)
cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK if '--bw' in sys.argv else ColorPolicy.COLOR, min_lineweight=0.15)
be = MatplotlibBackend(ax, adjust_figure=False)
Frontend(ctx, be, config=cfg).draw_layout(lay, finalize=True)
ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal')
fig.savefig(out, dpi=100, facecolor='white')
print(out, 'extents', round(x0), round(y0), round(x1), round(y1))
