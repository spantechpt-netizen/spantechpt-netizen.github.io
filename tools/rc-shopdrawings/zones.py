"""Zones (AREA 1, AREA 2 ...) of a foundation plan -> zones.json, for packages per zone (sheets + BBS per zone).

The consultant draws each zone as a closed polyline (often a revision-cloud with hundreds of vertices, layer 0 or a
zone layer) with a big text "AREA n" inside; one zone may have NO outline = everything not inside another zone.
usage: python3 zones.py final.dxf [dx,dy]      dx,dy = shift to the coordinates of the working drawing
                                              (rev_compare.py prints it)
writes zones.json {"AREA 2": [[x, y], ...], ..., "_rest": "AREA 1"} and prints each zone's size."""
import json, re, sys
from ezdxf import recover
from shapely.geometry import Polygon, Point

src = sys.argv[1]
dx, dy = map(float, sys.argv[2].split(',')) if len(sys.argv) > 2 else (0, 0)
doc, _ = recover.readfile(src); msp = doc.modelspace()
lab, polys = [], []
for e in msp:
    t = e.dxftype()
    if t in ('TEXT', 'MTEXT'):
        s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        if re.match(r'^(AREA|ZONE)\s*\w+$', s, re.I): lab.append((s.upper(), e.dxf.insert.x, e.dxf.insert.y))
    elif t == 'LWPOLYLINE' and e.closed:
        p = [(q[0], q[1]) for q in e.get_points()]
        if len(p) >= 4:
            try:
                g = Polygon(p).buffer(0)
                if g.geom_type == 'Polygon' and g.area > 1e8: polys.append(g)
            except Exception: pass
Z = {}
for s, x, y in lab:
    inside = [g for g in polys if g.contains(Point(x, y)) and not any(Point(a, b).within(g) for t_, a, b in lab if t_ != s)]
    if inside: Z[s] = min(inside, key=lambda g: g.area)
rest = [s for s, x, y in lab if s not in Z]
out = {k: [[a + dx, b + dy] for a, b in g.exterior.coords] for k, g in Z.items()}
if len(rest) == 1: out['_rest'] = rest[0]
json.dump(out, open('zones.json', 'w'))
for k, g in sorted(Z.items()):
    x0, y0, x1, y1 = g.bounds; print(f'{k}: {(x1 - x0) / 1000:.1f} x {(y1 - y0) / 1000:.1f} m, {len(g.exterior.coords)} vertices')
print('zone without an outline (= the rest):', rest)
