"""Core (shear-wall) necks per zone: cores of the foundation plan (pair_cores.py search) -> the footing type under each
on the FINAL plan -> zone -> out/ZONES/AREA_n_CORE_NECKS.dxf with its BBS.
A core on an unlabelled footing takes project.json -> core_default_footing (reported)."""
import sys, json, collections
from ezdxf import recover
from shapely.geometry import Polygon
import zone_util as Z
import gen_core
from gen import new_doc, seq_zone, seq_save, seq_none, BarList, draw_bbs

P = Z.PRJ
LAY = P.get('core_outline_layer', 'CORE-COLS-CONC')
cx, cy, hv = P['fnd_view']; X0, X1, Y0, Y1 = cx - hv * 0.5, cx + hv * 0.5, cy - hv * 0.5, cy + hv * 0.5
sizes = {tuple(sorted((v['W'], v['H']))): k for k, v in P['core_types'].items()}
doc, _ = recover.readfile(P.get('dxf', 'main.dxf'))
def walk(e, lay=None, d=0):
    if lay and e.dxf.layer == '0': e.dxf.layer = lay
    if e.dxftype() == 'INSERT':
        if d < 6:
            try:
                for v in e.virtual_entities(): yield from walk(v, e.dxf.layer, d + 1)
            except Exception: pass
    else: yield e
found = {}
for top in doc.modelspace():
    for e in walk(top):
        if e.dxftype() != 'LWPOLYLINE' or e.dxf.layer != LAY: continue
        p = [(q[0], q[1]) for q in e.get_points()]
        if len(p) != 12: continue
        xs = [a for a, b in p]; ys = [b for a, b in p]
        if not (X0 < min(xs) < X1 and Y0 < min(ys) < Y1): continue
        key = tuple(sorted((round(max(xs) - min(xs)), round(max(ys) - min(ys)))))
        if key in sizes: found[(round(min(xs)), round(min(ys)))] = (sizes[key], Polygon(p))
pairs = collections.defaultdict(collections.Counter); notes = []
for (x, y), (typ, pg) in sorted(found.items()):
    c = pg.centroid
    kind, fn, _ = Z.footing_at(c.x, c.y)
    if fn is None:
        fn = P.get('core_default_footing', 'F11'); notes.append(f'{typ} at {x},{y}: footing unlabelled on the final plan - taken as {fn}')
    pairs[Z.zone_of(c.x, c.y)][(typ, fn)] += 1
L = Z.lib()
for zn in (sys.argv[1:] or Z.NAMES):
    gen_core.ZONE = zn
    if not pairs[zn]: seq_none('CORES', zn); continue
    d = new_doc(); bl = BarList(); idx = 0
    seq_zone(d, zn, 'CORES', Z.NAMES)                      # running sheet numbers across the zones
    m0 = Z.base_meta(zn, 'SDW-STR-NCK', '1:25', 'COVER CORE WALLS 40; Ld IN THE FOOTING >= 60d, FEET INTO THE CORE.')
    m0['venue'] = P.get('core_venue', 'CW')                  # core walls numbered apart (30100 ...)
    for (typ, fn), no in sorted(pairs[zn].items()):
        f = dict(L[fn]); f.setdefault('name', fn)
        m = dict(m0); m['title'] = f'CORE NECKS - {zn}'
        gen_core.draw_pair(d, idx, typ, P['core_types'][typ], f, no, bl, m); idx += 2
    m = dict(m0); m['title'] = f'CORE NECKS - {zn}\nBBS'; m['dwg'] = f'SDW-STR-NCK-CORES-{Z.CODES[zn]}'
    nb = draw_bbs(d, idx, bl.sorted(), m)
    seq_save(d)
    d.saveas(f"out/ZONES/{zn.replace(' ', '_')}_CORE_NECKS.dxf")
    print(zn, dict(pairs[zn]), 'sheets', idx, '+ BBS', nb)
print('\n'.join(notes))
