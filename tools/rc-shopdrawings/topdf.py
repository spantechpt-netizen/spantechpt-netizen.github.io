import sys,ezdxf,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from ezdxf import bbox
from ezdxf.addons.drawing import RenderContext,Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration,BackgroundPolicy,ColorPolicy
f,out=sys.argv[1],sys.argv[2]
doc=ezdxf.readfile(f); msp=doc.modelspace()
if '--one' in sys.argv:            # one big sheet at the origin: --one W,H,paper_w_in,paper_h_in (A0 1:200 = 237800,168200,46.81,33.11)
    W,H,pw,ph=map(float,sys.argv[sys.argv.index('--one')+1].split(','))
    cfg=Configuration(background_policy=BackgroundPolicy.WHITE,color_policy=ColorPolicy.BLACK,min_lineweight=0.1)
    with PdfPages(out) as pdf:
        fig=plt.figure(figsize=(pw,ph)); ax=fig.add_axes([0,0,1,1])
        Frontend(RenderContext(doc),MatplotlibBackend(ax),config=cfg).draw_layout(msp,finalize=False)
        ax.set_xlim(0,W); ax.set_ylim(0,H); ax.set_aspect('equal'); ax.axis('off')
        pdf.savefig(fig); plt.close(fig)
    sys.exit(0)
# sheet index of every entity (sheets are stacked every -32000 in y): render each page with its own entities only
page={}
for e in msp:
    try:
        b=bbox.extents([e],fast=True)
        y=(b.extmin.y+b.extmax.y)/2 if b.has_data else 0
    except Exception: y=0
    page[e.dxf.handle]=int((-y+31999)//32000) if y<29700 else 0
n=int(sys.argv[3]) if len(sys.argv)>3 else max(page.values())+1
cfg=Configuration(background_policy=BackgroundPolicy.WHITE,color_policy=ColorPolicy.BLACK,min_lineweight=0.1)
with PdfPages(out) as pdf:
    for i in range(n):
        y0=-i*32000
        fig=plt.figure(figsize=(16.54,11.69)); ax=fig.add_axes([0,0,1,1])
        Frontend(RenderContext(doc),MatplotlibBackend(ax),config=cfg).draw_layout(msp,finalize=False,
            filter_func=lambda e,i=i: page.get(e.dxf.handle,0)==i)
        ax.set_xlim(0,42000); ax.set_ylim(y0,y0+29700); ax.set_aspect('equal'); ax.axis('off')
        pdf.savefig(fig); plt.close(fig)
