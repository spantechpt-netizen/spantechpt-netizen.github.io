"""Survey a consultant's structural DXF before any shop-drawing work: what is drawn where, on which layer, inside
which block, and which layer / block / text family carries the grid, the columns, the grade beams, the footings and
the schedules. Works on any office's drawing (no layer names are assumed); the result is a report to read and a
draft project.json to check by eye on the renders (rend.py).

usage: python3 survey.py drawing.dxf [outdir]          (outdir default: survey/)
writes:
  survey.md            the report (sections 1-9 below)
  texts.csv            every TEXT / MTEXT / ATTRIB (model space + paper space, nested blocks expanded)
  project.draft.json   draft keys for extract.py / pair_necks.py (CHECK every value before use)
"""
import csv, json, math, os, re, sys
from collections import Counter, defaultdict
from ezdxf import recover, bbox

src = sys.argv[1]
out = sys.argv[2] if len(sys.argv) > 2 else 'survey'
os.makedirs(out, exist_ok=True)
doc, aud = recover.readfile(src)
msp = doc.modelspace()
R = []                                  # report lines
P = lambda *a: R.append(' '.join(str(x) for x in a))

# ---------------------------------------------------------------- label families (text -> element)
FAM = [
    ('grade beam', r'^(GB|TB|G\.B|T\.B|SB|STB|B)\s*-?\s*\d+[A-Z]?$'),
    ('column', r'^(C|SC|NC)\s*-?\s*\d*[A-Z]?$'),
    ('column+size', r'^(C|SC|NC)\s*-?\s*\d*[A-Z]?\s*\(?\s*\d+\s*[Xx×\*]\s*\d+'),
    ('footing', r'^(F|IF|PF|PC)\s*-?\s*\d*[A-Z]?$'),
    ('combined ftg', r'^(CF|CB|CMF)\s*-?\s*\d+[A-Z]?$'),
    ('raft', r'^(RAFT|R|MAT)\s*-?\s*\d+[A-Z]?$'),
    ('strip ftg', r'^(ST|SF|WF|STF)\s*-?\s*\d+[A-Z]?$'),
    ('fence ftg', r'^(FF|FC)\s*-?\s*\d+[A-Z]?$'),
    ('wall', r'^(W|RW|SW)\s*-?\s*\d+[A-Z]?$'),
    ('rebar n T d', r'^\d+\s*(T|Y|Ø|Φ|%%C|#)\s*\d+'),
    ('rebar T d @ s', r'(T|Y|Ø|Φ|%%C|#)\s*\d+\s*(@|/)\s*\d+'),
    ('bars per m', r'\d+\s*(T|Y|Ø|Φ|%%C)\s*\d+\s*/\s*M'),
    ('stirrups', r'STIRR|TIES|LINKS|STRP'),
    ('level', r'(^|\s)[+\-]\s*\d+\.\d{2,3}\b'),
    ('schedule title', r'SCHEDULE|SCHED\b|TABLE|DETAILS? OF'),
    ('plan title', r'PLAN\b'),
    ('section title', r'SECTION|SEC\.'),
]
FAM = [(n, re.compile(p, re.I)) for n, p in FAM]

# ---------------------------------------------------------------- walk everything (nested blocks expanded)
def pos(e):
    t = e.dxftype()
    try:
        if t == 'LINE': return e.dxf.start.x, e.dxf.start.y
        if t == 'LWPOLYLINE':
            p = e.get_points('xy'); return p[0] if p else None
        if t in ('CIRCLE', 'ARC'): return e.dxf.center.x, e.dxf.center.y
        if t in ('TEXT', 'MTEXT', 'INSERT', 'ATTRIB'): return e.dxf.insert.x, e.dxf.insert.y
        if t == 'POLYLINE':
            v = next(iter(e.vertices), None); return (v.dxf.location.x, v.dxf.location.y) if v else None
        if t == 'HATCH':
            b = bbox.extents([e], fast=True); return (b.center.x, b.center.y) if b.has_data else None
    except Exception:
        return None
    return None

def txt_of(e):
    t = e.dxftype()
    try:
        s = e.plain_text() if t == 'MTEXT' else e.dxf.text
    except Exception:
        return None
    s = re.sub(r'\s+', ' ', s or '').strip()
    return s or None

def theight(e):
    try: return e.dxf.char_height if e.dxftype() == 'MTEXT' else e.dxf.height
    except Exception: return 0

prims = []        # (type, layer, x, y, path)  path = block names from model space down ('' = model space)
texts = []        # (text, x, y, layer, height, space, path)
types = Counter(); proxies = Counter(); polys = []; lines = []
def walk(e, path='', depth=0, inh=None):
    t = e.dxftype()
    if inh and e.dxf.layer == '0':
        e.dxf.layer = inh               # entity on layer 0 inside a block shows on the INSERT's layer (AutoCAD rule)
    types[t] += 1
    if t in ('ACAD_PROXY_ENTITY',) or t.startswith('RBCR') or t.startswith('AEC'):
        proxies[t] += 1
    if t == 'INSERT':
        p = pos(e)
        if p: prims.append((t, e.dxf.layer, p[0], p[1], path + '/' + e.dxf.name))
        for a in e.attribs:
            s = txt_of(a)
            if s: texts.append((s, a.dxf.insert.x, a.dxf.insert.y, a.dxf.layer, theight(a), 'model', path + '/' + e.dxf.name + '@' + a.dxf.tag))
        if depth < 5:
            try:
                for v in e.virtual_entities():
                    if v.dxftype() == 'ATTRIB': continue
                    walk(v, path + '/' + e.dxf.name, depth + 1, e.dxf.layer)
            except Exception:
                pass
        return
    p = pos(e)
    if p is None: return
    if t == 'LWPOLYLINE': polys.append(e)
    elif t == 'LINE': lines.append(e)
    if t in ('TEXT', 'MTEXT'):
        s = txt_of(e)
        if s: texts.append((s, p[0], p[1], e.dxf.layer, theight(e), 'model', path))
    prims.append((t, e.dxf.layer, p[0], p[1], path))

for e in msp: walk(e)
paper_txt = []
for lay in doc.layouts:
    if lay.name == 'Model': continue
    for e in lay:
        if e.dxftype() in ('TEXT', 'MTEXT'):
            s = txt_of(e)
            if s: paper_txt.append((s, lay.name, theight(e)))
        elif e.dxftype() == 'INSERT':
            for a in e.attribs:
                s = txt_of(a)
                if s: paper_txt.append((s, lay.name + '/' + e.dxf.name + '@' + a.dxf.tag, theight(a)))

with open(os.path.join(out, 'texts.csv'), 'w', newline='') as f:
    w = csv.writer(f); w.writerow(['text', 'x', 'y', 'layer', 'height', 'space', 'block_path'])
    for t in texts: w.writerow([t[0], round(t[1]), round(t[2]), t[3], round(t[4], 1), t[5], t[6]])
    for s, lay, h in paper_txt: w.writerow([s, '', '', '', round(h, 1), 'paper:' + lay, ''])

# ---------------------------------------------------------------- 1. file
hdr = doc.header
U = {0: 'unitless', 1: 'inch', 2: 'feet', 4: 'mm', 5: 'cm', 6: 'm'}
P('# Survey of', os.path.basename(src)); P()
P('## 1. File')
P(f'- DXF version {doc.dxfversion}; $INSUNITS = {hdr.get("$INSUNITS", 0)} ({U.get(hdr.get("$INSUNITS", 0), "?")}); audit fixes/errors {len(aud.fixes)}/{len(aud.errors)}')
xs = [p[2] for p in prims]; ys = [p[3] for p in prims]
if xs: P(f'- model extents x {min(xs):.0f} .. {max(xs):.0f}, y {min(ys):.0f} .. {max(ys):.0f}')
P('- entity types (blocks expanded):', ', '.join(f'{k} {v}' for k, v in types.most_common(14)))
cls = []
try: cls = [c.dxf.name for c in doc.classes]
except Exception: pass
asd = [c for c in cls if c.upper().startswith(('RBCR', 'ACAD_PROXY'))]
if proxies or asd:
    P(f'- **WARNING**: proxy / ASD / AEC objects ({dict(proxies)} classes {asd[:8]}) -> reinforcement drawn with Autodesk '
      'Structural Detailing or Architecture objects is LOST in the conversion. Ask for an exploded DWG or the plotted PDF.')
P()

# ---------------------------------------------------------------- 2. layers
P('## 2. Layers (model space, nested blocks expanded) - top 60')
lay = defaultdict(Counter); inblk = Counter()
for t, l, x, y, path in prims:
    lay[l][t] += 1
    if path: inblk[l] += 1
P('| layer | entities | in blocks | types | note |'); P('|---|---|---|---|---|')
for l, c in sorted(lay.items(), key=lambda kv: -sum(kv[1].values()))[:60]:
    note = 'bound xref ($0$)' if '$0$' in l else ('xref' if '|' in l else '')
    P(f'| {l} | {sum(c.values())} | {inblk[l]} | ' + ', '.join(f'{k} {v}' for k, v in c.most_common(4)) + f' | {note} |')
P()

# ---------------------------------------------------------------- 3. blocks
P('## 3. Blocks inserted in model space - top 40')
bl = Counter(e.dxf.name for e in msp.query('INSERT'))
P('| block | inserts | size (first insert) | attribute tags = sample values | texts inside |'); P('|---|---|---|---|---|')
blocks_info = {}
for name, n in bl.most_common(40):
    e = next(i for i in msp.query('INSERT') if i.dxf.name == name)
    try:
        b = bbox.extents([e], fast=True); size = (round(b.size.x), round(b.size.y)) if b.has_data else None
    except Exception:
        size = None
    tags = {}
    for i in list(msp.query(f'INSERT[name=="{name}"]'))[:50]:
        for a in i.attribs:
            tags.setdefault(a.dxf.tag, set()).add(a.dxf.text)
    nt = sum(1 for t in texts if t[6].startswith('/' + name) and '@' not in t[6])
    blocks_info[name] = dict(n=n, size=size, tags={k: sorted(v)[:6] for k, v in tags.items()}, ntext=nt)
    P(f'| {name} | {n} | {size} | ' + '; '.join(f'{k}={sorted(v)[:5]}' for k, v in tags.items())[:160] + f' | {nt} |')
P()

# ---------------------------------------------------------------- 4. drawings in model space (islands)
P('## 4. Separate drawings in model space (islands of entities) with their biggest titles')
islands = []
if xs:
    sx, sy = sorted(xs), sorted(ys); q = len(sx) // 1000          # ignore far-away strays (0.1 %)
    mnx, mxx, mny, mxy = sx[q], sx[-1 - q], sy[q], sy[-1 - q]
    span = max(mxx - mnx, mxy - mny); cell = max(span / 250, 1)
    occ = Counter((int((x - mnx) / cell), int((y - mny) / cell)) for t, l, x, y, p in prims
                  if mnx <= x <= mxx and mny <= y <= mxy)
    seen = set()
    for c0 in occ:
        if c0 in seen or occ[c0] < 3: continue
        stack, comp = [c0], []
        seen.add(c0)
        while stack:
            c = stack.pop(); comp.append(c)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    q = (c[0] + dx, c[1] + dy)
                    if q in occ and q not in seen and occ[q] >= 3: seen.add(q); stack.append(q)
        n = sum(occ[c] for c in comp)
        if n < 200: continue
        X0 = min(c[0] for c in comp) * cell + mnx; X1 = (max(c[0] for c in comp) + 1) * cell + mnx
        Y0 = min(c[1] for c in comp) * cell + mny; Y1 = (max(c[1] for c in comp) + 1) * cell + mny
        islands.append(dict(win=(X0, Y0, X1, Y1), n=n))
    islands.sort(key=lambda d: -d['n'])
    for d in islands[:30]:
        X0, Y0, X1, Y1 = d['win']
        tt = sorted([t for t in texts if X0 <= t[1] <= X1 and Y0 <= t[2] <= Y1 and len(t[0]) > 3], key=lambda t: -t[4])
        tl = [t[0][:50] for t in tt[:4]]
        P(f'- window {X0:.0f},{Y0:.0f},{X1:.0f},{Y1:.0f} ({(X1 - X0) / 1000:.0f} x {(Y1 - Y0) / 1000:.0f} k units, {d["n"]} entities): {tl}')
P('  (render a window: `python3 rend.py drawing.dxf out.png x0,y0,x1,y1 4000`)'); P()

# ---------------------------------------------------------------- 5. layouts / viewports
P('## 5. Paper layouts and the model window each viewport shows')
vps = []
for L in doc.layouts:
    if L.name == 'Model': continue
    for v in L.query('VIEWPORT'):
        d = v.dxf
        if d.get('id', 2) == 1 or not d.get('height'): continue
        c, h = d.view_center_point, d.view_height
        w = h * d.width / d.height
        win = (c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2)
        tt = sorted([t for t in texts if win[0] <= t[1] <= win[2] and win[1] <= t[2] <= win[3] and len(t[0]) > 3], key=lambda t: -t[4])
        if h / d.height < 1.5 and not tt: continue          # title-block / paper detail viewport
        vps.append(dict(layout=L.name, win=win, scale=h / d.height, view=[c.x, c.y, h]))
        P(f'- layout **{L.name}**: model window {win[0]:.0f},{win[1]:.0f},{win[2]:.0f},{win[3]:.0f}  scale 1:{h / d.height:.0f}  '
          f'titles {[t[0][:40] for t in tt[:3]]}')
    pt = [s for s, ln, h in paper_txt if ln.split('/')[0] == L.name and re.search(r'PLAN|SCHED|SECTION|DETAIL|FOUND|BEAM', s, re.I)]
    if pt: P(f'  paper-space titles in {L.name}: {pt[:6]}')
if not vps: P('- no viewports: plans are only in model space (use section 4 windows)')
P()

# ---------------------------------------------------------------- 6. label families
P('## 6. Text families (what each element is called, on which layer, inside which block)')
fam_hits = defaultdict(list)
for t in texts:
    for n, rx in FAM:
        if rx.search(t[0]): fam_hits[n].append(t)
for n, _ in FAM:
    h = fam_hits.get(n, [])
    if not h: continue
    vals = Counter(t[0] for t in h)
    P(f'- **{n}**: {len(h)} texts, {len(vals)} distinct. values {[v for v, _ in vals.most_common(12)]}')
    P(f'  layers {Counter(t[3] for t in h).most_common(4)}; blocks {Counter((t[6].split("@")[0] or "(model space)") for t in h).most_common(3)}')
P()

# ---------------------------------------------------------------- 7. candidates
P('## 7. Candidates (check each on a render)')
# 7a grid bubbles: blocks with short attribute values (1-4 chars) inserted many times
grid = []
for name, inf in blocks_info.items():
    if inf['n'] < 6 or not inf['tags']: continue
    short = [k for k, v in inf['tags'].items() if v and all(len(s) <= 4 for s in v)]
    if short and inf['size'] and max(inf['size']) < 5000: grid.append((inf['n'], name, inf['tags']))
grid.sort(reverse=True)
for n, name, tags in grid[:4]: P(f'- grid bubble block? **{name}** x{n}: tags {tags}')
gl = [(sum(c.values()), l) for l, c in lay.items() if re.search(r'AXIS|GRID|AXES|CENTER|CL', l, re.I)]
if gl: P(f'- grid line layers? {sorted(gl, reverse=True)[:4]}')

# 7b rectangles per layer: columns (150-2000) and footing outlines (800-20000)
rects = defaultdict(list)
def addrect(e, layer):
    try: p = e.get_points('xy')
    except Exception: return
    if len(p) < 4 or len(p) > 6: return
    xs_, ys_ = [a for a, b in p], [b for a, b in p]
    w, h = max(xs_) - min(xs_), max(ys_) - min(ys_)
    # orthogonal rectangle only
    if all(min(abs(a - min(xs_)), abs(a - max(xs_))) < 2 for a in xs_) and all(min(abs(b - min(ys_)), abs(b - max(ys_))) < 2 for b in ys_):
        rects[layer].append((min(xs_), min(ys_), max(xs_), max(ys_)))
for e in polys: addrect(e, e.dxf.layer)
col_lab = fam_hits.get('column', []) + fam_hits.get('column+size', [])
ftg_lab = [t for n in ('footing', 'combined ftg', 'raft', 'strip ftg', 'fence ftg') for t in fam_hits.get(n, [])]
def near_count(rs, labs, grow):
    n = 0
    for x0, y0, x1, y1 in rs[:3000]:
        if any(x0 - grow <= t[1] <= x1 + grow and y0 - grow <= t[2] <= y1 + grow for t in labs): n += 1
    return n
colc, ftgc = [], []
for l, rs in rects.items():
    small = [r for r in rs if 150 <= r[2] - r[0] <= 2000 and 150 <= r[3] - r[1] <= 2000]
    big = [r for r in rs if 800 <= r[2] - r[0] <= 30000 and 800 <= r[3] - r[1] <= 30000]
    if len(small) >= 5:
        sz = Counter(tuple(sorted((int(round(r[2] - r[0], -1)), int(round(r[3] - r[1], -1))))) for r in small)
        colc.append((('COL' in l.upper()) * 1000 + near_count(small, col_lab, 1500), l, len(small), sz.most_common(6)))
    if len(big) >= 3 and ftg_lab:
        sz = Counter(tuple(sorted((int(round(r[2] - r[0], -1)), int(round(r[3] - r[1], -1))))) for r in big)
        ftgc.append((near_count(big, ftg_lab, 0), l, len(big), sz.most_common(5)))
for s, l, n, sz in sorted(colc, reverse=True)[:5]:
    P(f'- column outlines? layer **{l}**: {n} rectangles, sizes {sz}')
for s, l, n, sz in sorted(ftgc, reverse=True)[:5]:
    P(f'- footing outlines? layer **{l}**: {n} rectangles 0.8-30 m, {s} contain a footing label; sizes {sz} '
      '(PC outline = RC + 2 x PC projection: compare with the schedule)')

# 7c beam edges: layers with many parallel orthogonal segments at a constant distance 150-600
segs = defaultdict(list)
for e in lines + polys:                       # model space and inside blocks
    try:
        if e.dxftype() == 'LINE': pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        else:
            pts = e.get_points('xy'); pts = list(pts) + ([pts[0]] if e.closed else [])
    except Exception: continue
    for a, b in zip(pts, pts[1:]):
        segs[e.dxf.layer].append((a, b))
beamc = []
for l, ss in segs.items():
    if len(ss) < 40 or len(ss) > 300000: continue
    d = Counter(); npair = 0; cells = set(); plist = []
    for hor in (True, False):
        L = []
        for (x0, y0), (x1, y1) in ss:
            if hor and abs(y0 - y1) < 2 and abs(x1 - x0) > 500: L.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2))
            if not hor and abs(x0 - x1) < 2 and abs(y1 - y0) > 500: L.append((min(y0, y1), max(y0, y1), (x0 + x1) / 2))
        L.sort(key=lambda s: s[2])
        for i, a in enumerate(L):
            for b in L[i + 1:i + 30]:
                g = b[2] - a[2]
                if g > 650: break
                lo, hi = max(a[0], b[0]), min(a[1], b[1])
                if g >= 140 and hi - lo > 500:
                    d[round(g / 10) * 10] += 1; npair += 1
                    cc = (a[2] + b[2]) / 2
                    for u in range(int(lo // 1000), int(hi // 1000) + 1):
                        cells.add((u, int(cc // 1000)) if hor else (int(cc // 1000), u))
                    if len(plist) < 20000: plist.append((hor, cc, lo, hi, round(g / 10) * 10))
    if npair >= 20:
        # a grade-beam label (GB1, TB2 ...) sits on or next to its beam: count labels on this layer's pairs
        lab = sum(1 for t in fam_hits.get('grade beam', [])
                  if any((int(t[1] // 1000) + i, int(t[2] // 1000) + j) in cells for i in (-1, 0, 1) for j in (-1, 0, 1)))
        beamc.append((lab, npair, l, d.most_common(5), plist))
def label_widths(plist):
    # extract.py's rule: a label belongs to the nearest pair it stands beside (along the pair +-200, across <= 900)
    lw = defaultdict(Counter)
    for t in fam_hits.get('grade beam', []):
        best = None
        for hor, cc, lo, hi, g in plist:
            u, v = (t[1], t[2]) if hor else (t[2], t[1])
            if lo - 200 <= u <= hi + 200 and abs(v - cc) < 900 and (best is None or abs(v - cc) < best[0]): best = (abs(v - cc), g)
        if best: lw[re.sub(r'\s', '', t[0]).upper()][best[1]] += 1
    return lw
beamc.sort(key=lambda b: (b[0], b[1]), reverse=True)
for i, (lab, n, l, d, pl) in enumerate(beamc[:6]):
    P(f'- beam edges? layer **{l}**: {n} parallel pairs, {lab} GB/TB labels on them; gaps (gap: count) {d}')
    if i == 0:
        LW = label_widths(pl)
        P('  drawn width of each label (label: {width: count}) -> compare with the schedule: ' +
          '; '.join(f'{k} {dict(v.most_common(3))}' for k, v in sorted(LW.items())))

# 7d schedules: titles and the block / window holding them
for t in fam_hits.get('schedule title', [])[:25]:
    P(f'- schedule title "{t[0][:60]}" at {t[1]:.0f},{t[2]:.0f} layer {t[3]} h {t[4]:.0f} block {t[6] or "-"}')
P()

# ---------------------------------------------------------------- 8. scale / units sanity
P('## 8. Units')
sizes = [r[2] - r[0] for l in rects for r in rects[l] if r[2] - r[0] > 0]
if colc:
    l = sorted(colc, reverse=True)[0][1]
    med = sorted(r[2] - r[0] for r in rects[l])[len(rects[l]) // 2]
    unit = 'mm' if med > 100 else ('cm' if med > 10 else 'm')
    P(f'- typical column side on {l} = {med:.0f} drawing units -> drawing is in **{unit}** '
      '(scale every coordinate to mm before extract.py if not mm)')
P()

# ---------------------------------------------------------------- 9. draft project.json
draft = dict(dxf=os.path.basename(src))
if grid:
    n, name, tags = grid[0]; draft['axis_block'] = name
    # number tag = values with digits; family tag = single letters
    num = [k for k, v in tags.items() if any(re.search(r'\d', s) for s in v)]
    fam = [k for k, v in tags.items() if all(re.fullmatch(r'[A-Za-z]', s) for s in v)]
    if num: draft['axis_attr'] = num[0]
    if fam: draft['axis_family_attr'] = fam[0]
if beamc:
    lab, n, l, d, pl = beamc[0]
    draft['beam_layer'] = l
    W_ = Counter()
    for k, v in LW.items():
        for g, c in v.items():
            if c >= max(2, 0.1 * sum(v.values())): W_[g] += c
    draft['widths'] = sorted(W_) or sorted(g for g, c in d[:3])
gbl = fam_hits.get('grade beam', [])
if gbl: draft['label_layer'] = Counter(t[3] for t in gbl).most_common(1)[0][0]
if colc: draft['col_layers'] = [l for s, l, n, sz in sorted(colc, reverse=True)[:2]]
def n_in(v, labs): return sum(1 for t in labs if v['win'][0] < t[1] < v['win'][2] and v['win'][1] < t[2] < v['win'][3])
gb_lab = fam_hits.get('grade beam', [])
if vps and gb_lab:
    best = max(vps, key=lambda v: n_in(v, gb_lab))
    if n_in(best, gb_lab): draft['layout'] = best['layout']          # the plan that carries the GB labels
if vps and ftg_lab:
    best = max(vps, key=lambda v: n_in(v, ftg_lab))
    if n_in(best, ftg_lab): draft['fnd_view'] = [round(best['view'][0]), round(best['view'][1]), round(best['view'][2])]
cs = {}
for t in fam_hits.get('column+size', []):
    m = re.match(r'^((?:C|SC|NC)-?\d*[A-Z]?)\s*[-(]?\s+\(?\s*(\d+)\s*[Xx×\*]\s*(\d+)', t[0], re.I)
    if m:
        a, b = int(m.group(2)), int(m.group(3))
        if max(a, b) < 150: a, b = a * 10, b * 10            # written in cm (C1 30X80)
        cs[m.group(1).replace(' ', '').upper()] = [a, b]
if cs: draft['column_sizes'] = dict(sorted(cs.items()))
if ftgc:
    top = max(f[0] for f in ftgc)
    good = [f for f in ftgc if f[0] >= 0.5 * top]
    # the RC outline, not the PC one (PC = RC + projection) - check against the schedule sizes
    draft['fnd_layers'] = [min(good, key=lambda f: ('PC' in f[1].upper(), -f[0]))[1]]
if colc: draft['fnd_col_layers'] = [sorted(colc, reverse=True)[0][1]]
# column schedule block: the top-level block holding the stirrup / column-schedule texts
cb = Counter()
for t in fam_hits.get('stirrups', []) + fam_hits.get('schedule title', []):
    if t[6].count('/') >= 1:
        cb[t[6].split('/')[1]] += 10 if re.search(r'COLUMN SCHED', t[0], re.I) else 1
if cb: draft['column_schedule_block'] = cb.most_common(1)[0][0]
draft['schedule'] = {'GB1': dict(b=0, h=0, nb=0, db=0, nt=0, dt=0, ds=0, s=0)}
draft['levels'] = dict(founding=None, top_gb=None)
draft['meta'] = dict(project='', client='', consultant='', contractor='', ref='', prefix='SDW-STR-GB')
json.dump(draft, open(os.path.join(out, 'project.draft.json'), 'w'), indent=1)
P('## 9. Draft project.json (CHECK every value on a render; schedule / levels / meta are typed from the drawing)')
P('```json'); P(json.dumps(draft, indent=1)); P('```')

open(os.path.join(out, 'survey.md'), 'w').write('\n'.join(R) + '\n')
print('\n'.join(R))
