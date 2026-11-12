"""Slabs on grade / thin rafts written as a NOTE on the foundation plan (no CF / RAFT mark): e.g.
"7 T 12 /m - TOP & BOTTOM - 200 MM THICK CONNECTED WITH FOOTING" inside the area closed by the strip footings.
The foundation line work is polygonized (like mats_scan2.py); a face > 500 m2 holding a "nnn MM THICK" note and a
"n T d /m" note is a slab: its outer outline (footings inside are under it, the slab runs over them), thickness,
mesh, TOP / BOTTOM. -> slabs.json (working coordinates)."""
import json, re
from ezdxf import recover
from shapely.geometry import Point, LineString, Polygon
from shapely.ops import unary_union, polygonize

P = json.load(open('project.json')); SRC = P.get('fnd_final', {})
doc, _ = recover.readfile(SRC.get('dxf', P.get('dxf', 'main.dxf'))); DX, DY = SRC.get('shift', [0, 0])
FNDL = tuple(P.get('fnd_layers', ['CORE-FNDN']))
lines, texts = [], []
def walk(e, d=0, inh=None):
    t = e.dxftype()
    if inh and e.dxf.layer == '0': e.dxf.layer = inh
    if t == 'INSERT' and d < 3:
        try:
            for v in e.virtual_entities(): walk(v, d + 1, e.dxf.layer)
        except Exception: pass
    elif t == 'LWPOLYLINE' and e.dxf.layer.endswith(FNDL):
        p = [(a, b) for a, b in e.get_points('xy')]
        if e.closed: p = p + [p[0]]
        if len(p) >= 2: lines.append(LineString(p))
    elif t == 'LINE' and e.dxf.layer.endswith(FNDL):
        lines.append(LineString([(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]))
    elif t in ('TEXT', 'MTEXT'):
        texts.append(((e.plain_text() if t == 'MTEXT' else e.dxf.text).strip(), e.dxf.insert.x, e.dxf.insert.y))
for e in doc.modelspace(): walk(e)
faces = [f for f in polygonize(unary_union([l for l in lines if l.length > 1])) if f.area > 500e6]
out = []
for f in faces:
    ins = [(s, x, y) for s, x, y in texts if f.contains(Point(x, y))]
    th = [int(m.group(1)) for s, x, y in ins for m in [re.search(r'(\d+)\s*MM\s+THICK', s.upper())] if m]
    ms = [(int(m.group(1)), int(m.group(2)), s) for s, x, y in ins for m in [re.match(r'^(\d+)\s*T\s*(\d+)\s*/\s*M', s.upper())] if m]
    if not th or not ms: continue
    n, d, s0 = ms[0]
    both = any('TOP' in s.upper() and 'BOT' in s.upper() for s, x, y in ins)
    ext = Polygon(f.exterior.coords)
    # ramps: a corridor narrower than ~4 m between two strips, next to a "RAMP START" note, is the sloped ramp slab
    # (own detail): removed from the corridor end up to the note (the ramp start line)
    from shapely.geometry import box
    ramps = []
    thin = ext.difference(ext.buffer(-1950, join_style=2).buffer(1950, join_style=2))
    comps = [g for g in getattr(thin, 'geoms', [thin]) if g.area > 20e6]
    for s, x, y in ins:
        if 'RAMP' not in s.upper(): continue
        near = [g for g in comps if g.distance(Point(x, y)) < 6000]
        if not near: continue
        g = min(near, key=lambda g: g.distance(Point(x, y)))
        b0, b1, b2, b3 = g.bounds
        rb = box(b0, min(b1, y), b2, max(b3, y)) if (b3 - b1) >= (b2 - b0) else box(min(b0, x), b1, max(b2, x), b3)
        r = ext.intersection(rb)
        if r.area > 0: ramps.append(r if r.geom_type == 'Polygon' else max(r.geoms, key=lambda q: q.area)); ext = ext.difference(rb)
    if ext.geom_type != 'Polygon': ext = max(ext.geoms, key=lambda g: g.area)
    out.append(dict(h=th[0], n=n, d=d, top=both or 'TOP' in s0.upper(), poly=[[x + DX, y + DY] for x, y in ext.simplify(1).exterior.coords][:-1],
                    note=' / '.join(s for s, x, y in ins if re.search(r'THICK|/\s*M|TOP|BOT', s.upper())),
                    ramps=[[[x + DX, y + DY] for x, y in r.exterior.coords] for r in ramps]))
json.dump(out, open('slabs.json', 'w'))
for o in out: print('slab h', o['h'], f"{o['n']} T {o['d']}/m", 'top+bot' if o['top'] else 'bottom', len(o['poly']), 'corners, ramps cut', len(o['ramps']), '|', o['note'])
