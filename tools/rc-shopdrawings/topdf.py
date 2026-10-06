import sys,ezdxf,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from ezdxf.addons.drawing import RenderContext,Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration,BackgroundPolicy,ColorPolicy
f,out,n=sys.argv[1],sys.argv[2],int(sys.argv[3])
doc=ezdxf.readfile(f); msp=doc.modelspace()
cfg=Configuration(background_policy=BackgroundPolicy.WHITE,color_policy=ColorPolicy.BLACK,min_lineweight=0.1)
with PdfPages(out) as pdf:
    for i in range(n):
        y0=-i*32000
        fig=plt.figure(figsize=(16.54,11.69)); ax=fig.add_axes([0,0,1,1])
        Frontend(RenderContext(doc),MatplotlibBackend(ax),config=cfg).draw_layout(msp,finalize=False,
            filter_func=lambda e: True)
        ax.set_xlim(0,42000); ax.set_ylim(y0,y0+29700); ax.set_aspect('equal'); ax.axis('off')
        pdf.savefig(fig); plt.close(fig)
