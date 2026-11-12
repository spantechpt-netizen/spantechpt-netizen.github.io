"""What the engineer changed between two issues of a foundation plan (the 'final' sent back after review).

usage: python3 rev_check.py old.dxf new.dxf [dx,dy]      dx,dy = shift of both plans to the working coordinates

Reports (positions in working coordinates):
  1. the shift between the two plans (vote over equal footing outlines; 0,0 when the file was only edited)
  2. footing labels renamed / gone / new (a label that only moved with its schedule table shows as gone + new)
  3. footing outlines resized / gone / new
  4. column labels: count per mark, labels whose size differs from the outline drawn there
  5. texts drawn in red that are new (engineers mark their corrections in red)
  6. level tags (block A-LV-P or 'nn.nn' texts) and notes about elevations
Then: re-read the schedule with table_dump.py and diff it against footings.json / footings_ext.json by hand."""
import collections, logging, math, re, sys
logging.getLogger('ezdxf').setLevel(logging.ERROR)
from ezdxf import recover

FL = re.compile(r'^(F\d*[A-Z]?|Fx|FF\d+|CF\d+|RAFT-?\d+(-?[A-Z])?|ST-\d+)$')
CL = re.compile(r'^(C\d*)\s+(\d+)\s*[Xx]\s*(\d+)$')


def read(src):
    doc, _ = recover.readfile(src); msp = doc.modelspace()
    D = dict(lab=[], rc=[], col=[], clab=[], lvl=[], red=[], note=[])

    def walk(e, lay=None, d=0, blk=''):
        if lay and e.dxf.layer == '0': e.dxf.layer = lay
        if e.dxftype() == 'INSERT':
            if e.dxf.name == 'A-LV-P':
                D['lvl'].append(({a.dxf.tag: a.dxf.text for a in e.attribs}, e.dxf.insert.x, e.dxf.insert.y))
            if d < 5:
                try:
                    for v in e.virtual_entities(): yield from walk(v, e.dxf.layer, d + 1, blk or e.dxf.name)
                except Exception: pass
        else:
            yield e, blk, d
    for top in msp:
        for e, blk, d in walk(top):
            t = e.dxftype(); L = e.dxf.layer.upper()
            if t == 'LWPOLYLINE' and e.closed:
                p = [(q[0], q[1]) for q in e.get_points()]
                if len(p) < 4: continue
                xs = [a for a, b in p]; ys = [b for a, b in p]
                r = (min(xs), min(ys), max(xs), max(ys))
                if 'FNDN' in L and 'RBAR' not in L: D['rc'].append(r)
                elif L.endswith('COLS-CONC'): D['col'].append(r)
            elif t in ('TEXT', 'MTEXT'):
                s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
                x, y = e.dxf.insert.x, e.dxf.insert.y
                if FL.match(s): D['lab'].append((s, x, y))
                m = CL.match(s)
                if m: D['clab'].append((m.group(1), int(m.group(2)) * 10, int(m.group(3)) * 10, x, y))
                if 'ELEVATION' in s.upper() or 'LEVEL' in s.upper(): D['note'].append((s, x, y))
                lay = doc.layers.get(e.dxf.layer) if e.dxf.layer in doc.layers else None
                c = e.dxf.get('color', 256)
                if d == 0 and (c == 1 or (c == 256 and lay is not None and lay.color == 1)):
                    D['red'].append((s, x, y))
    return D


def main():
    O, N = read(sys.argv[1]), read(sys.argv[2])
    for D in (O, N):                         # footing labels of the plan only (not the schedule's rows)
        D['lab'] = [l for l in D['lab'] if any(r[0] - 2000 < l[1] < r[2] + 2000 and r[1] - 2000 < l[2] < r[3] + 2000 for r in D['rc'])]
    WX, WY = map(float, sys.argv[3].split(',')) if len(sys.argv) > 3 else (0, 0)
    sz = lambda r: (round(r[2] - r[0]), round(r[3] - r[1]))
    by = collections.defaultdict(list)
    for r in O['rc']: by[sz(r)].append(r)
    votes = collections.Counter()
    for a in N['rc']:
        for b in by.get(sz(a), [])[:60]: votes[(round(b[0] - a[0], -1), round(b[1] - a[1], -1))] += 1
    (SX, SY), nv = votes.most_common(1)[0] if votes else ((0, 0), 0)
    print(f'1. shift new -> old {SX:.0f},{SY:.0f} ({nv} outlines agree)')
    mv = lambda x, y: (round(x + SX + WX), round(y + SY + WY))
    Nl = [(s, x + SX, y + SY) for s, x, y in N['lab']]
    near = lambda p, lst, r=1500: [q for q in lst if math.hypot(q[1] - p[1], q[2] - p[2]) < r]
    print('2. footing labels')
    for o in O['lab']:
        m = near(o, Nl)
        if not m: print('   GONE   ', o[0], *mv(o[1] - SX, o[2] - SY))
        elif o[0] not in [q[0] for q in m]: print('   RENAMED', o[0], '->', sorted({q[0] for q in m}), *mv(o[1] - SX, o[2] - SY))
    for n in Nl:
        if not near(n, O['lab']): print('   NEW    ', n[0], *mv(n[1] - SX, n[2] - SY))
    print('3. footing outlines')
    Nr = [(r[0] + SX, r[1] + SY, r[2] + SX, r[3] + SY) for r in N['rc']]
    cen = lambda r: ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
    key = lambda r: tuple(round(v) for v in r)
    kn = {key(r) for r in Nr}; ko = {key(r) for r in O['rc']}
    lab_in = lambda r, labs: sorted({l[0] for l in labs if r[0] - 300 < l[1] < r[2] + 300 and r[1] - 300 < l[2] < r[3] + 300})
    for r in O['rc']:
        if key(r) in kn: continue
        c = [s for s in Nr if math.dist(cen(s), cen(r)) < 1500]
        if c and any(abs(a - b) > 60 for a, b in zip(r, c[0])):
            print('   RESIZED', lab_in(r, O['lab']), f'{sz(r)[0]}x{sz(r)[1]} -> {sz(c[0])[0]}x{sz(c[0])[1]}', *mv(*cen(r)))
        elif not c:
            print('   GONE   ', lab_in(r, O['lab']), f'{sz(r)[0]}x{sz(r)[1]}', *mv(*cen(r)))
    for s in Nr:
        if key(s) not in ko and not [r for r in O['rc'] if math.dist(cen(s), cen(r)) < 1500]:
            print('   NEW    ', lab_in(s, Nl), f'{sz(s)[0]}x{sz(s)[1]}', *mv(*cen(s)))
    print('4. column labels', dict(collections.Counter(t for t, *_ in O['clab'])), '->', dict(collections.Counter(t for t, *_ in N['clab'])))
    for t, b, h, x, y in N['clab']:
        cs = [r for r in N['col'] if max(0, abs(cen(r)[0] - x) - sz(r)[0] / 2) + max(0, abs(cen(r)[1] - y) - sz(r)[1] / 2) < 600]
        if cs:
            r = min(cs, key=lambda r: math.dist(cen(r), (x, y)))
            if sorted(sz(r)) != sorted((b, h)) and all(abs(a - c) > 30 for a, c in zip(sorted(sz(r)), sorted((b, h)))):
                print(f'   label {t} {b}x{h} beside an outline {sz(r)[0]}x{sz(r)[1]}', *mv(x, y))
    print('5. new red texts')
    for s, x, y in N['red']:
        if not any(o[0] == s and math.hypot(o[1] - x - SX, o[2] - y - SY) < 300 for o in O['red']):
            print('  ', s, *mv(x, y))
    print('6. levels', [(a, *mv(x, y)) for a, x, y in N['lvl']])
    for s, x, y in N['note']: print('   note:', s[:200])


if __name__ == '__main__':
    main()
