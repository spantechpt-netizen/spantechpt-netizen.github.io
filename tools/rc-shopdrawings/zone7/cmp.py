import ezdxf, logging, sys
from collections import Counter, defaultdict
logging.getLogger('ezdxf').setLevel(logging.ERROR)
A = ezdxf.readfile(sys.argv[1]); B = ezdxf.readfile(sys.argv[2])
def key(e):
    t = e.dxftype(); r = lambda v: round(v / 5) * 5
    try:
        if t == 'LINE': return (t, e.dxf.layer, tuple(sorted([(r(e.dxf.start.x), r(e.dxf.start.y)), (r(e.dxf.end.x), r(e.dxf.end.y))])))
        if t == 'LWPOLYLINE': return (t, e.dxf.layer, tuple((r(p[0]), r(p[1])) for p in e.get_points('xy')))
        if t == 'CIRCLE': return (t, e.dxf.layer, r(e.dxf.center.x), r(e.dxf.center.y), r(e.dxf.radius))
        if t == 'DIMENSION': return (t, e.dxf.layer, r(e.dxf.defpoint2.x), r(e.dxf.defpoint2.y), r(e.dxf.defpoint3.x), r(e.dxf.defpoint3.y), e.dxf.get('text', ''))
        if t in ('TEXT', 'MTEXT'):
            s = (e.dxf.text if t == 'TEXT' else e.plain_text()).strip(); q = e.dxf.insert
            return (t, e.dxf.layer, s, round(q.x / 100), round(q.y / 100))
        if t == 'INSERT': return (t, e.dxf.layer, e.dxf.name, r(e.dxf.insert.x), r(e.dxf.insert.y))
        if t == 'VIEWPORT': return (t, round(e.dxf.center.x), round(e.dxf.center.y), round(e.dxf.width), round(e.dxf.height), round(e.dxf.view_height), round(e.dxf.view_center_point.x / 10), round(e.dxf.view_center_point.y / 10))
        if t == 'HATCH': return (t, e.dxf.layer, len(e.paths))
    except Exception: return None
    return (t, e.dxf.layer)
def pos(e):
    try:
        t = e.dxftype()
        if t == 'LINE': return e.dxf.start
        if t == 'LWPOLYLINE': p = next(iter(e.get_points('xy'))); return p
        if t == 'CIRCLE': return e.dxf.center
        if t == 'DIMENSION': return e.dxf.defpoint2
        if t in ('TEXT', 'MTEXT', 'INSERT'): return e.dxf.insert
    except Exception: pass
    return None
wins = []
for l in A.layouts:
    if l.name == 'Model': continue
    for v in l.query('VIEWPORT'):
        if v.dxf.id == 1: continue
        sc = v.dxf.view_height / v.dxf.height; c = v.dxf.view_center_point
        wins.append((l.name.split()[0], c.x - v.dxf.width * sc / 2, c.y - v.dxf.view_height / 2, c.x + v.dxf.width * sc / 2, c.y + v.dxf.view_height / 2))
def sheet(p):
    if p is None: return '?'
    for nm, x0, y0, x1, y1 in wins:
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1: return nm
    return 'outside views'
def coll(lay, model):
    c = Counter(); ps = {}
    for e in lay:
        k = key(e)
        if k is None: continue
        c[k] += 1; ps[k] = pos(e)
    return c, ps
rep = defaultdict(lambda: [Counter(), Counter(), []])
(ca, pa), (cb, pb) = coll(A.modelspace(), 1), coll(B.modelspace(), 1)
for k in (cb - ca).elements(): s = sheet(pb[k]); rep['MODEL ' + s][0][k[:2]] += 1; rep['MODEL ' + s][2].append(('+',) + k[:4])
for k in (ca - cb).elements(): s = sheet(pa[k]); rep['MODEL ' + s][1][k[:2]] += 1; rep['MODEL ' + s][2].append(('-',) + k[:4])
names = [l.name for l in A.layouts if l.name != 'Model']
for l in B.layouts:
    if l.name == 'Model': continue
    la = A.layouts.get(l.name) if l.name in names else None
    ca_, _ = coll(la, 0) if la is not None else (Counter(), {})
    cb_, _ = coll(l, 0)
    for k in (cb_ - ca_).elements(): rep['PAPER ' + l.name.split()[0]][0][k[:2]] += 1; rep['PAPER ' + l.name.split()[0]][2].append(('+',) + k[:5])
    for k in (ca_ - cb_).elements(): rep['PAPER ' + l.name.split()[0]][1][k[:2]] += 1; rep['PAPER ' + l.name.split()[0]][2].append(('-',) + k[:5])
print('layouts only ours', [n for n in names if n not in [l.name for l in B.layouts]], '| only theirs', [l.name for l in B.layouts if l.name not in names and l.name != 'Model'])
for s, (a, r_, det) in sorted(rep.items()):
    print(f'{s:24s} added {sum(a.values()):4d} removed {sum(r_.values()):4d}  +{dict(a)}  -{dict(r_)}')
import pickle; pickle.dump({k: v[2] for k, v in rep.items()}, open(sys.argv[3], 'wb'))
