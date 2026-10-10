"""Cores on the foundation plan -> core_pairs for gen_core.py.
Finds the core outlines (closed polylines with the U shape, 12 vertices, on project.json -> core_outline_layer,
default CORE-COLS-CONC) inside fnd_view whose size matches a core type (W x H either way round), drops copies,
and reports the footing / raft under each (more than half the core area). Needs cd_scan.py run first (gen_cd.build).
usage: python3 pair_cores.py            -> prints the pairs and writes core_pairs.json"""
import json, collections
from ezdxf import recover
from shapely.geometry import Polygon
import gen_cd

PRJ = json.load(open('project.json'))
LAY = PRJ.get('core_outline_layer', 'CORE-COLS-CONC')
cx, cy, hv = PRJ['fnd_view']; X0, X1, Y0, Y1 = cx - hv * 0.5, cx + hv * 0.5, cy - hv * 0.5, cy + hv * 0.5
sizes = {tuple(sorted((v['W'], v['H']))): k for k, v in PRJ['core_types'].items()}
doc, _ = recover.readfile(PRJ.get('dxf', 'main.dxf'))

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
els, cols = gen_cd.build()
cnt = collections.Counter()
for (x, y), (typ, pg) in sorted(found.items()):
    under = [e for e in els if e['rc'].intersection(pg).area > 0.5 * pg.area]
    lab = under[0]['lab'] if under and under[0]['lab'] else '?'
    print(typ, 'at', x, y, 'on', lab, under[0]['kind'] if under else '-', under[0]['h'] if under else '-')
    cnt[(typ, lab)] += 1
pairs = [[t, f, n] for (t, f), n in sorted(cnt.items())]
json.dump(pairs, open('core_pairs.json', 'w'))
print('core_pairs:', pairs, '(a "?" footing: name it in project.json -> core_pairs by hand)')
