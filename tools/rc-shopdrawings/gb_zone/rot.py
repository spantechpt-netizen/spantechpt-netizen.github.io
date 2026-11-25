"""rotate a consultant plan so the beams are orthogonal (about the origin), labels '*' -> 'X'"""
import sys, ezdxf, math
from ezdxf.math import Matrix44
src, out, ang = sys.argv[1], sys.argv[2], float(sys.argv[3])
d = ezdxf.readfile(src); m = Matrix44.z_rotate(math.radians(-ang))
for e in list(d.modelspace()):
    try:
        if e.dxftype() == 'MTEXT': e.text = e.text.replace('*', 'X')
        if e.dxftype() == 'TEXT': e.dxf.text = e.dxf.text.replace('*', 'X')
        e.transform(m)
    except Exception as ex:
        try: e.explode()
        except Exception: pass
d.saveas(out); print('ok', out)
