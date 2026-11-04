"""Anything drawn outside its sheet frame?  usage: python3 fitcheck.py out/ZONES/*.dxf
A sheet frame = the title-block insert on layer S-FRAME (or the 42000 x 29700 sheet at its origin). An entity whose
centre is on a sheet but whose extents leave the sheet by more than TOL is reported with the sheet title."""
import sys, collections, logging
logging.getLogger('ezdxf').setLevel(logging.ERROR)
import ezdxf
from ezdxf import bbox
TOL = 20
tot = 0
for f in sys.argv[1:]:
    doc = ezdxf.readfile(f); msp = doc.modelspace()
    frames = []
    for e in msp.query('INSERT'):
        if e.dxf.layer == 'S-FRAME':
            b = bbox.extents([e], fast=True)
            if b.has_data: frames.append((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y))
    bad = collections.defaultdict(list)
    for e in msp:
        if e.dxf.layer == 'S-FRAME': continue
        b = bbox.extents([e], fast=True)
        if not b.has_data: continue
        cx, cy = (b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2
        fr = next((r for r in frames if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]), None)
        if fr is None:
            bad['(no sheet)'].append((e.dxftype(), e.dxf.layer, round(cx), round(cy))); continue
        out = max(fr[0] - b.extmin.x, fr[1] - b.extmin.y, b.extmax.x - fr[2], b.extmax.y - fr[3])
        if out > TOL: bad[fr].append((e.dxftype(), e.dxf.layer, round(out)))
    n = sum(len(v) for v in bad.values()); tot += n
    print(f'{f}: {len(frames)} sheets, {len(bad)} with something outside, {n} entities')
    for fr, v in list(bad.items())[:6]:
        print("   ", fr if isinstance(fr, str) else tuple(round(x) for x in fr), v[:4], flush=True)
print('TOTAL outside', tot)
