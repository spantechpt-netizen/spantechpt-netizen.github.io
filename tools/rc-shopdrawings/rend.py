import sys,ezdxf,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from ezdxf import recover,bbox
from ezdxf.addons.drawing import RenderContext,Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration,BackgroundPolicy,ColorPolicy
f,out,win=sys.argv[1],sys.argv[2],[float(v) for v in sys.argv[3].split(',')]
px=int(sys.argv[4]) if len(sys.argv)>4 else 4000
doc,_=recover.readfile(f); msp=doc.modelspace()
x0,y0,x1,y1=win
def ok(e):
    try:
        b=bbox.extents([e],fast=True)
        if not b.has_data: return False
        return not(b.extmax.x<x0 or b.extmin.x>x1 or b.extmax.y<y0 or b.extmin.y>y1)
    except Exception: return False
cfg=Configuration(background_policy=BackgroundPolicy.WHITE,color_policy=ColorPolicy.BLACK if '--bw' in sys.argv else ColorPolicy.COLOR,min_lineweight=0.1)
w,h=x1-x0,y1-y0
fig=plt.figure(figsize=(px/100,px/100*h/w),dpi=100); ax=fig.add_axes([0,0,1,1])
Frontend(RenderContext(doc),MatplotlibBackend(ax),config=cfg).draw_layout(msp,finalize=False,filter_func=ok)
ax.set_xlim(x0,x1); ax.set_ylim(y0,y1); ax.set_aspect('equal'); ax.axis('off')
fig.savefig(out,dpi=100,facecolor='white')
