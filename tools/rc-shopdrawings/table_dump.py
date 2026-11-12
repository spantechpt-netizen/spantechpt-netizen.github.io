"""Read a schedule drawn as lines + texts (GB schedule, footing schedule, column schedule, level table ...) into rows
and columns, whether it sits in model space or inside a block (nested blocks expanded).

usage:
  python3 table_dump.py drawing.dxf "FOOTING SCHEDULE"              find the title, read the table under it
  python3 table_dump.py drawing.dxf "FOOTING SCHEDULE" x0,y0,x1,y1  read exactly this window (from survey / rend.py)
  python3 table_dump.py drawing.dxf --block "COLUMN SCH"             every text of one block, as rows
writes table.csv (one line per row, cells left to right) and prints it.

Rows = texts whose y agree within 0.6 x the median text height; cells = texts of the row sorted by x. Merged cells
(one value over several rows, e.g. a common spacing) appear once on the row nearest to their middle: copy them down
when typing the schedule into the project data. Sketch-type schedules (column sections, beam sections drawn to
scale) carry the geometry, not text: read those with the element readers (gen_n.read_schedule2 for columns).
"""
import csv, re, sys
from ezdxf import recover

src, key = sys.argv[1], sys.argv[2]
doc, _ = recover.readfile(src)
msp = doc.modelspace()

T = []
def walk(e, path='', d=0):
    t = e.dxftype()
    if t == 'INSERT':
        for a in e.attribs:
            T.append((a.dxf.text.strip(), a.dxf.insert.x, a.dxf.insert.y, a.dxf.height, path + '/' + e.dxf.name))
        if d < 5:
            try:
                for v in e.virtual_entities():
                    if v.dxftype() != 'ATTRIB': walk(v, path + '/' + e.dxf.name, d + 1)
            except Exception: pass
    elif t in ('TEXT', 'MTEXT'):
        s = re.sub(r'\s+', ' ', e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        h = e.dxf.char_height if t == 'MTEXT' else e.dxf.height
        if s: T.append((s, e.dxf.insert.x, e.dxf.insert.y, h, path))
for e in msp: walk(e)

if key == '--block':
    sel = [t for t in T if t[4].split('/')[1:2] == [sys.argv[3]]]
else:
    if len(sys.argv) > 3:
        x0, y0, x1, y1 = map(float, sys.argv[3].split(','))
    else:
        hits = [t for t in T if key.upper() in t[0].upper()]
        if not hits: sys.exit(f'title "{key}" not found')
        for h in hits: print('title found:', h[0][:60], round(h[1]), round(h[2]), 'h', round(h[3]), 'block', h[4] or '-')
        s, tx, ty, th, _ = max(hits, key=lambda t: t[3])
        # the table: texts below the title, within 60 title heights left/right, down to the first empty band
        cand = sorted([t for t in T if ty - 400 * th < t[2] < ty and abs(t[1] - tx) < 60 * th], key=lambda t: -t[2])
        x0, x1, y1, y0 = tx - 60 * th, tx + 60 * th, ty + th, ty
        last = ty
        for t in cand:
            if last - t[2] > 8 * th: break
            last = t[2]; y0 = t[2] - th
        print(f'window used {x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}  (pass it explicitly to adjust)')
    sel = [t for t in T if x0 <= t[1] <= x1 and y0 <= t[2] <= y1]

if not sel: sys.exit('no text in the window')
hs = sorted(t[3] for t in sel if t[3]); hm = hs[len(hs) // 2] if hs else 100
rows = []
for t in sorted(sel, key=lambda t: -t[2]):
    if rows and abs(rows[-1][0] - t[2]) <= 0.6 * hm: rows[-1][1].append(t)
    else: rows.append([t[2], [t]])
with open('table.csv', 'w', newline='') as f:
    w = csv.writer(f)
    for y, cells in rows:
        cells.sort(key=lambda t: t[1])
        w.writerow([round(y)] + [c[0] for c in cells])
        print(f'{y:12.0f} | ' + ' | '.join(c[0] for c in cells))
print(len(rows), 'rows -> table.csv')
