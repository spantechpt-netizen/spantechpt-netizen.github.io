"""Answer the two questions asked again and again while reading a new drawing.

  python3 probe.py drawing.dxf text "ADD TOP"            where is this text? (position, layer, block path)
  python3 probe.py drawing.dxf text "^F3A$" --re         same with a regular expression
  python3 probe.py drawing.dxf at 2983652,2112164 [r]    what is drawn around this point? (type, layer, block, size)
  python3 probe.py drawing.dxf around "F6" 3000          the texts within r of every "F6" (schedule rows, labels)

Model space and nested blocks are searched (an entity on layer 0 inside a block reports the INSERT's layer).
"""
import re, sys
from collections import Counter
from ezdxf import recover, bbox

src, mode = sys.argv[1], sys.argv[2]
doc, _ = recover.readfile(src)
msp = doc.modelspace()

def walk(e, path='', d=0, inh=None):
    if inh and e.dxf.layer == '0': e.dxf.layer = inh
    if e.dxftype() == 'INSERT':
        yield e, path
        for a in e.attribs: yield a, path + '/' + e.dxf.name
        if d < 5:
            try:
                for v in e.virtual_entities():
                    if v.dxftype() != 'ATTRIB': yield from walk(v, path + '/' + e.dxf.name, d + 1, e.dxf.layer)
            except Exception: pass
    else:
        yield e, path

def text(e):
    t = e.dxftype()
    if t == 'MTEXT': return re.sub(r'\s+', ' ', e.plain_text()).strip()
    if t in ('TEXT', 'ATTRIB'): return e.dxf.text.strip()
    return None

if mode in ('text', 'around'):
    key = sys.argv[3]
    rx = re.compile(key if '--re' in sys.argv else re.escape(key), re.I)
    T = [(text(e), e.dxf.insert.x, e.dxf.insert.y, e.dxf.layer, p) for e, p in (w for x in msp for w in walk(x)) if text(e)]
    hits = [t for t in T if rx.search(t[0])]
    print(len(hits), 'hits;', Counter((t[3], t[4] or '(model space)') for t in hits).most_common(6))
    if hits:
        print('x range', round(min(t[1] for t in hits)), round(max(t[1] for t in hits)), ' y range', round(min(t[2] for t in hits)), round(max(t[2] for t in hits)))
    for t in hits[:40]:
        print(f'  {t[0][:50]:50s} {t[1]:12.0f} {t[2]:12.0f}  {t[3]}  {t[4]}')
        if mode == 'around':
            r = float(sys.argv[4]) if len(sys.argv) > 4 else 3000
            near = sorted([u for u in T if abs(u[1] - t[1]) < 3 * r and abs(u[2] - t[2]) < r and u is not t], key=lambda u: (-round(u[2] - t[2], -1), u[1]))
            print('     ', [(u[0][:25], round(u[1] - t[1]), round(u[2] - t[2])) for u in near[:30]])
elif mode == 'at':
    x, y = map(float, sys.argv[3].split(','))
    r = float(sys.argv[4]) if len(sys.argv) > 4 else 500
    c = Counter()
    for top in msp:
        for e, p in walk(top):
            try:
                b = bbox.extents([e], fast=True)
            except Exception: continue
            if not b.has_data or b.size.x > 50000 or b.size.y > 50000: continue
            if b.extmin.x - r <= x <= b.extmax.x + r and b.extmin.y - r <= y <= b.extmax.y + r:
                c[(e.dxftype(), e.dxf.layer, e.dxf.name if e.dxftype() == 'INSERT' else '', p or '-', round(b.size.x), round(b.size.y), text(e) or '')] += 1
    for k, n in c.most_common(60): print(n, k)
