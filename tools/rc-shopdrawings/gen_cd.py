"""Concrete dimensions of the foundations (setting-out drawing for the site):
  * PLAN 1:100 in parts (A3 sheets), every RC footing (continuous) and its PC (dashed), columns, grid; each isolated /
    combined footing / raft dimensioned from the nearest grid line in both directions (axis -> edges) with its overall
    size, name, RC and PC size and thickness;
  * SECTIONS along EVERY grid line (both directions): PC + RC footings cut by the line, column necks (stub), founding
    level, T.O.PC, T.O.F of each footing, and two dimension chains along the line: footing edges + grid lines (sizes
    and the clear distances between footings) and grid line to grid line. Empty stretches are shortened with a break
    (the dimensions keep the real distances).

usage: python3 cd_scan.py && python3 gen_cd.py        (project data: project.json, footings.json, footings_ext.json)
inputs: cd_scan.pkl (RC / PC outlines, columns, labels, bubbles of the foundation plan), cd_axes.json (grid lines)
output: out/CONCRETE_DIM.dxf
Sizes: isolated and fence footings take the SCHEDULE size centred on the drawn footing (engineer: the schedule
governs); combined footings, rafts and strips keep the drawn outline. Thickness from the schedules.
"""
import json, math, pickle, re, sys
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from gen import new_doc, Sheet, TA, ST, mm

PRJ = json.load(open('project.json'))
LEV = PRJ.get('levels', {})
FL = LEV.get('founding', -3.0)                      # bottom of PC
PCH = PRJ.get('pc_thickness', 100)
SCH = json.load(open('footings.json'))
EXT = json.load(open('footings_ext.json'))
FENCE = PRJ.get('fence_footings', {})               # {"FF1": {"L":1900,"W":1900,"h":600,"pcL":2100,"pcW":2100}}
SCAN = pickle.load(open('cd_scan.pkl', 'rb'))
AXES = json.load(open('cd_axes.json'))
STRIP = PRJ.get('strip', {})

TF = 1.0                                            # text / offset factor (2 = A0 at 1:200)
STRIP_EL = dict(lab='ST-01', kind='ST', h=None, base='ST-01')
LAYERS = {'S-CD-RC': 7, 'S-CD-PC': 2, 'S-CD-AX': 1, 'S-CD-COL': 8, 'S-CD-TXT': 7, 'S-CD-DIM': 3, 'S-CD-SEC': 4}


# ---------------------------------------------------------------- model of the foundation plan
def rect_of(pg):
    x0, y0, x1, y1 = pg.bounds
    return abs(pg.area - (x1 - x0) * (y1 - y0)) < 0.01 * pg.area


def merge_split(raw, gap=450):
    """The consultant often draws one footing in pieces cut by a beam / wall line (FF1 = 2 halves 200 apart): two
    rectangles with the same span in one direction and a gap <= a beam width in the other are one footing."""
    rs, other = [], []
    for p in raw:
        try: pg = Polygon(p).buffer(0)
        except Exception: continue
        if pg.is_empty: continue
        (rs if rect_of(pg) else other).append(list(pg.bounds))
    changed = True
    while changed:
        changed = False
        for i in range(len(rs)):
            for j in range(i + 1, len(rs)):
                a, b = rs[i], rs[j]
                samex = abs(a[0] - b[0]) < 15 and abs(a[2] - b[2]) < 15
                samey = abs(a[1] - b[1]) < 15 and abs(a[3] - b[3]) < 15
                gy = max(a[1], b[1]) - min(a[3], b[3]); gx = max(a[0], b[0]) - min(a[2], b[2])
                if (samex and -15 <= gy <= gap) or (samey and -15 <= gx <= gap):
                    rs[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del rs[j]; changed = True; break
            if changed: break
    return [list(box(*r).exterior.coords) for r in rs] + [p for p in raw if not rect_of(Polygon(p).buffer(0))]


def _segs_open(chains):
    out = []
    for q in chains:
        for (a, b), (c, d) in zip(q, q[1:]):
            if abs(a - c) < 2: out.append(('V', (a + c) / 2, min(b, d), max(b, d)))
            elif abs(b - d) < 2: out.append(('H', (b + d) / 2, min(a, c), max(a, c)))
    return out


def chain_open(pieces, tol=6):
    """Open outline pieces joined end to end; the chains that close are shapes (a footing drawn as two L lines or as
    four separate lines). Returns (closed loops, still-open chains)."""
    key = lambda p: (round(p[0] / tol), round(p[1] / tol))
    todo = [list(p) for p in pieces if len(p) >= 2]
    loops, opens = [], []
    while todo:
        cur = todo.pop()
        grown = True
        while grown and key(cur[0]) != key(cur[-1]):
            grown = False
            for i, q in enumerate(todo):
                if key(q[0]) == key(cur[-1]): cur += q[1:]
                elif key(q[-1]) == key(cur[-1]): cur += q[::-1][1:]
                elif key(q[-1]) == key(cur[0]): cur = q + cur[1:]
                elif key(q[0]) == key(cur[0]): cur = q[::-1] + cur[1:]
                else: continue
                todo.pop(i); grown = True; break
        (loops if len(cur) >= 4 and key(cur[0]) == key(cur[-1]) else opens).append(cur)
    return loops, opens


OPEN = {k: chain_open([p for p, kk in SCAN.get('open', []) if kk == k]) for k in ('rc', 'pc')}


def _segs(raw):
    out = []
    for p in raw:
        q = list(p) + [p[0]]
        for (a, b), (c, d) in zip(q, q[1:]):
            if abs(a - c) < 2: out.append(('V', (a + c) / 2, min(b, d), max(b, d)))
            elif abs(b - d) < 2: out.append(('H', (b + d) / 2, min(a, c), max(a, c)))
    return out
SEGS = None


def fit_rect(x, y, L, W, raw):
    """Schedule rectangle L x W (either way round) placed where its four sides lie most on the drawn outline lines,
    containing the label (x, y). For footings drawn in pieces or merged with a wall strip."""
    global SEGS
    if SEGS is None: SEGS = _segs(raw + OPEN['rc'][0]) + _segs_open(OPEN['rc'][1])
    R = max(L, W) * 1.3
    near = [s for s in SEGS if (s[0] == 'V' and abs(s[1] - x) < R and s[3] > y - R and s[2] < y + R) or
            (s[0] == 'H' and abs(s[1] - y) < R and s[3] > x - R and s[2] < x + R)]
    vs = [s for s in near if s[0] == 'V']; hs = [s for s in near if s[0] == 'H']
    def on(kind, c, a, b):
        return sum(max(0, min(b, s[3]) - max(a, s[2])) for s in (vs if kind == 'V' else hs) if abs(s[1] - c) < 3)
    best = None
    for (lx, ly) in ((L, W), (W, L)):
        xs = {s[1] for s in vs} | {s[1] - lx for s in vs}
        ys = {s[1] for s in hs} | {s[1] - ly for s in hs}
        for x0 in xs:
            if not (x0 - 300 <= x <= x0 + lx + 300): continue
            for y0 in ys:
                if not (y0 - 300 <= y <= y0 + ly + 300): continue
                sc = on('V', x0, y0, y0 + ly) + on('V', x0 + lx, y0, y0 + ly) + on('H', y0, x0, x0 + lx) + on('H', y0 + ly, x0, x0 + lx)
                sc /= 2 * (lx + ly)
                if best is None or sc > best[0]: best = (sc, x0, y0, lx, ly)
    return best


def build():
    polys = []
    seen = set()
    for p in merge_split(SCAN['rc'] + OPEN['rc'][0]):
        try: pg = Polygon(p).buffer(0)
        except Exception: continue
        if pg.is_empty or pg.area < 0.4e6 or pg.area > 3000e6: continue
        key = tuple(round(v / 20) for v in pg.bounds) + (round(pg.area / 1e5),)
        if key in seen: continue
        seen.add(key); polys.append(pg)
    pcs = []
    for p in merge_split(SCAN['pc'] + OPEN['pc'][0]):
        try: pg = Polygon(p).buffer(0)
        except Exception: continue
        if not pg.is_empty and pg.area > 0.4e6: pcs.append(pg)
    els = [dict(rc=pg, lab=None) for pg in polys]
    for s, x, y in SCAN['lab']:
        pt = Point(x, y)
        cont = [e for e in els if e['rc'].buffer(50).contains(pt)]
        if not cont: cont = [e for e in els if e['rc'].distance(pt) < 600]
        if not cont:
            sch = SCH.get(s) or FENCE.get(s)
            fr = fit_rect(x, y, sch['L'], sch['W'], SCAN['rc']) if sch else None
            if fr and fr[0] > 0.45:
                _, fx, fy, flx, fly = fr
                els.append(dict(rc=box(fx, fy, fx + flx, fy + fly), lab=s, lpos=(x, y), fitted=round(fr[0], 2)))
            continue
        e = min(cont, key=lambda e: e['rc'].area)
        if e['lab'] is None: e['lab'] = s; e['lpos'] = (x, y)
        elif (SCH.get(s) or FENCE.get(s)) and e['lab'] != s:     # a second footing label in the same drawn outline
            els.append(dict(rc=e['rc'], lab=s, lpos=(x, y)))
    for e in els:
        lab, pg = e['lab'], e['rc']
        base = lab
        if lab and lab not in SCH and lab not in FENCE and lab not in EXT:
            m = re.match(r'(RAFT)-?0?(\d+)', lab or '')
            if m: base = next((k for k in EXT if re.fullmatch(r'RAFT-?0?' + m.group(2), k)), lab)
            if lab.replace(' ', '') in EXT: base = lab.replace(' ', '')
        e['base'] = base
        sch = SCH.get(base) or FENCE.get(base)
        x0, y0, x1, y1 = pg.bounds
        thin = sch and min((x1 - x0) / min(sch['L'], sch['W']), (y1 - y0) / min(sch['L'], sch['W'])) < 0.6
        if sch and (not rect_of(pg) or thin):                    # drawn in pieces / merged with a wall strip
            lx_, ly_ = e['lpos']
            fr = fit_rect(lx_, ly_, sch['L'], sch['W'], SCAN['rc'])
            if fr and fr[0] > 0.45:
                _, fx, fy, flx, fly = fr
                pg = box(fx, fy, fx + flx, fy + fly); e['rc'] = pg; e['fitted'] = round(fr[0], 2)
        if sch and rect_of(pg):                                   # schedule size centred on the drawn footing
            c = pg.centroid; x0, y0, x1, y1 = pg.bounds
            L, W = (sch['L'], sch['W']) if ((x1 - x0) >= (y1 - y0)) == (sch['L'] >= sch['W']) else (sch['W'], sch['L'])
            e['drawn'] = (round(x1 - x0), round(y1 - y0))
            e['rc'] = box(c.x - L / 2, c.y - W / 2, c.x + L / 2, c.y + W / 2)
            pL, pW = (sch['pcL'], sch['pcW']) if L == sch['L'] else (sch['pcW'], sch['pcL'])
            e['pc'] = box(c.x - pL / 2, c.y - pW / 2, c.x + pL / 2, c.y + pW / 2)
            e['h'] = sch['h']; e['kind'] = 'F'
            e['changed'] = abs(e['drawn'][0] - L) > 3 or abs(e['drawn'][1] - W) > 3
        else:
            cand = [q for q in pcs if q.contains(pg.representative_point()) and q.area > pg.area * 0.98]
            e['pc'] = min(cand, key=lambda q: q.area) if cand else pg.buffer(PCH, join_style=2)
            ext = EXT.get(base) or {}
            e['h'] = ext.get('h') or (STRIP.get('h') if (lab or '').startswith('ST') else None)
            narrow = pg.buffer(-820).is_empty                   # an unlabelled piece of the wall strip
            e['kind'] = 'ST' if ((lab or '').startswith('ST') or (not lab and narrow)) else ('M' if lab else '?')
            if e['kind'] == 'ST' and not e['h']: e['h'] = STRIP.get('h')
            e['changed'] = False
    # unlabelled pieces of a footing already placed (halves cut by a beam, bumps) are not separate elements
    typed = [e for e in els if e['kind'] == 'F']
    els = [e for e in els if e['lab'] or not any(e['rc'].intersection(t['rc']).area > 0.6 * e['rc'].area for t in typed)]
    cols = []
    for p in SCAN['col']:
        xs = [a for a, b in p]; ys = [b for a, b in p]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if 150 <= w <= 2000 and 150 <= h <= 2000:
            c = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
            if not any(math.dist(c, q['c']) < 100 for q in cols):
                cols.append(dict(c=c, r=box(min(xs), min(ys), max(xs), max(ys))))
    return els, cols


def axis_lines():
    out = []
    for nm, a in AXES.items():
        for c, lo, hi in a['segs']:
            out.append((nm, a['fam'], c, lo, hi))
    return out


def nearest_axis(fam, along_lo, along_hi, centre):
    """Grid line of family fam whose extent covers [along_lo, along_hi] (partly), nearest to centre."""
    best = None
    for nm, a in AXES.items():
        if a['fam'] != fam: continue
        for c, lo, hi in a['segs']:
            if hi < along_lo - 2000 or lo > along_hi + 2000: continue
            d = abs(c - centre)
            if best is None or d < best[0]: best = (d, nm, c)
    return best


# ---------------------------------------------------------------- plan sheets
def draw_plan(doc, els, cols, start_idx, meta0):
    ext = unary_union([e['pc'] for e in els]).bounds
    X0, Y0, X1, Y1 = ext[0] - 1500, ext[1] - 1500, ext[2] + 1500, ext[3] + 1500
    TW, TH = 31000, 23000                                         # real extent per A3 sheet at 1:100
    nx, ny = math.ceil((X1 - X0) / TW), math.ceil((Y1 - Y0) / TH)
    tw, th = (X1 - X0) / nx, (Y1 - Y0) / ny
    tiles = []
    for j in range(ny - 1, -1, -1):                               # top row first
        for i in range(nx):
            r = box(X0 + i * tw, Y0 + j * th, X0 + (i + 1) * tw, Y0 + (j + 1) * th)
            if any(e['rc'].intersects(r) for e in els): tiles.append((i, j, r))
    num = {(i, j): k + 1 for k, (i, j, r) in enumerate(tiles)}
    idx = start_idx
    for k, (i, j, r) in enumerate(tiles):
        meta = dict(meta0); meta['title'] = f'CONCRETE DIMENSIONS\nFOUNDATION PLAN - PART {k + 1} OF {len(tiles)}'
        sh = Sheet(doc, 0, -idx * 32000, meta); idx += 1
        rx0, ry0, rx1, ry1 = r.bounds
        ox, oy = 3000 - rx0, 3400 - ry0                           # tile -> sheet (1:100, real mm)
        Q = lambda x, y: (x + ox, y + oy)
        win = r.buffer(1200, join_style=2)                         # show a little of the neighbours
        # grid
        for nm, fam, c, lo, hi in axis_lines():
            if fam == 'Y':
                if not (rx0 - 1200 <= c <= rx1 + 1200): continue
                a_, b_ = max(lo, ry0 - 1200), min(hi, ry1 + 1200)
                if a_ >= b_: continue
                ln = sh.m.add_line(sh.P(*Q(c, a_)), sh.P(*Q(c, b_)), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 250})
                if hi >= ry1: bubble(sh, *Q(c, ry1 + 1200 + 600), nm)
            else:
                if not (ry0 - 1200 <= c <= ry1 + 1200): continue
                a_, b_ = max(lo, rx0 - 1200), min(hi, rx1 + 1200)
                if a_ >= b_: continue
                sh.m.add_line(sh.P(*Q(a_, c)), sh.P(*Q(b_, c)), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 250})
                if lo <= rx0: bubble(sh, *Q(rx0 - 1200 - 600, c), nm)
        # footings (clipped to the window), columns
        for e in els:
            for key, lay, lt in (('pc', 'S-CD-PC', 'DASHED'), ('rc', 'S-CD-RC', None)):
                g = e[key].intersection(win)
                if g.is_empty: continue
                for gg in getattr(g, 'geoms', [g]):
                    if gg.geom_type != 'Polygon': continue
                    pl = sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in gg.exterior.coords], dxfattribs={'layer': lay, 'const_width': 0 if lt else 25})
                    if lt: pl.dxf.linetype = lt; pl.dxf.ltscale = 120
        for c in cols:
            if not c['r'].within(win): continue
            x0, y0, x1, y1 = c['r'].bounds
            sh.hatch_rect(*Q(x0, y0), *Q(x1, y1), 'S-CD-COL')
        # labels + dimensions of the footings whose centre is in this tile
        for e in els:
            cc = e['rc'].centroid
            if not r.contains(cc): continue
            label_plan(sh, Q, e)
            bb = e['rc'].bounds
            if e['kind'] in ('F', 'M') or (e['kind'] == '?' and max(bb[2] - bb[0], bb[3] - bb[1]) < 15000): dims_plan(sh, Q, e)
        # match lines / neighbours
        for (di, dj, side) in ((-1, 0, 'L'), (1, 0, 'R'), (0, 1, 'T'), (0, -1, 'B')):
            n = num.get((i + di, j + dj))
            if not n: continue
            if side in 'LR':
                x = rx0 if side == 'L' else rx1
                sh.line(Q(x, ry0), Q(x, ry1), 'S-CD-SEC')
                sh.text(f'MATCH LINE - SEE PART {n}', *Q(x + (-250 if side == 'L' else 250), (ry0 + ry1) / 2), 220, 'S-CD-SEC', rot=90,
                        align=TA.BOTTOM_CENTER if side == 'L' else TA.TOP_CENTER)
            else:
                y = ry1 if side == 'T' else ry0
                sh.line(Q(rx0, y), Q(rx1, y), 'S-CD-SEC')
                sh.text(f'MATCH LINE - SEE PART {n}', *Q((rx0 + rx1) / 2, y + (250 if side == 'T' else -250)), 220, 'S-CD-SEC',
                        align=TA.BOTTOM_CENTER if side == 'T' else TA.TOP_CENTER)
        key_plan(sh, tiles, k, (X0, Y0, X1, Y1))
        sh.text('FOUNDATION PLAN - CONCRETE DIMENSIONS  1:100', 1500, 1250, ST['panel'], 'S-CD-SEC')
        sh.text('RC FOOTING (CONTINUOUS) / PC 100 (DASHED); ALL DIMENSIONS IN MM; SIZES OF ISOLATED FOOTINGS PER SCHEDULE.',
                1500, 800, ST['note'], 'S-CD-TXT')
    return idx, len(tiles)


class BigSheet(Sheet):
    W, H = 237800, 168200                     # A0 at 1:200
    dimstyle = 'GB200'


def draw_full_plan(doc, els, cols, meta0):
    """The whole foundation plan on one A0 sheet at 1:200."""
    global TF
    TF = 2.0
    meta = dict(meta0); meta['title'] = 'CONCRETE DIMENSIONS\nFOUNDATION PLAN (WHOLE SITE)'; meta['scale'] = '1:200'; meta['size'] = 'A0'
    sh = BigSheet(doc, 0, 0, meta)
    gx = [s for a in AXES.values() for s in a['segs']]
    xs = [c for nm, a in AXES.items() if a['fam'] == 'Y' for c, lo, hi in a['segs']] + [lo for nm, a in AXES.items() if a['fam'] == 'X' for c, lo, hi in a['segs']] + \
         [hi for nm, a in AXES.items() if a['fam'] == 'X' for c, lo, hi in a['segs']]
    ys = [c for nm, a in AXES.items() if a['fam'] == 'X' for c, lo, hi in a['segs']] + [lo for nm, a in AXES.items() if a['fam'] == 'Y' for c, lo, hi in a['segs']] + \
         [hi for nm, a in AXES.items() if a['fam'] == 'Y' for c, lo, hi in a['segs']]
    X0, X1, Y0, Y1 = min(xs) - 2500, max(xs) + 2500, min(ys) - 2500, max(ys) + 2500
    ax0, ay0, ax1, ay1 = 2300, 5200, 205500, 165900               # drawing area of the frame (sheet units)
    ox = ax0 + (ax1 - ax0 - (X1 - X0)) / 2 - X0; oy = ay0 + (ay1 - ay0 - (Y1 - Y0)) / 2 - Y0
    Q = lambda x, y: (x + ox, y + oy)
    for nm, a in AXES.items():
        for c, lo, hi in a['segs']:
            p0, p1 = (Q(lo - 1500, c), Q(hi + 1500, c)) if a['fam'] == 'X' else (Q(c, lo - 1500), Q(c, hi + 1500))
            sh.m.add_line(sh.P(*p0), sh.P(*p1), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 500})
        segs = a['segs']
        if a['fam'] == 'X':
            bubble(sh, *Q(segs[0][1] - 1500 - 1100, segs[0][0]), nm); bubble(sh, *Q(segs[-1][2] + 1500 + 1100, segs[-1][0]), nm)
        else:
            bubble(sh, *Q(segs[0][0], segs[0][1] - 1500 - 1100), nm); bubble(sh, *Q(segs[-1][0], segs[-1][2] + 1500 + 1100), nm)
    for e in els:
        for key, lay, lt in (('pc', 'S-CD-PC', 'DASHED'), ('rc', 'S-CD-RC', None)):
            for gg in getattr(e[key], 'geoms', [e[key]]):
                if gg.geom_type != 'Polygon': continue
                pl = sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in gg.exterior.coords], dxfattribs={'layer': lay, 'const_width': 0 if lt else 40})
                if lt: pl.dxf.linetype = lt; pl.dxf.ltscale = 200
    for p, kind in SCAN.get('open', []):
        pl = sh.m.add_lwpolyline([sh.P(*Q(*q)) for q in p], dxfattribs={'layer': 'S-CD-PC' if kind == 'pc' else 'S-CD-RC',
                                                                          'const_width': 0 if kind == 'pc' else 40})
        if kind == 'pc': pl.dxf.linetype = 'DASHED'; pl.dxf.ltscale = 200
    for c in cols:
        x0, y0, x1, y1 = c['r'].bounds
        sh.hatch_rect(*Q(x0, y0), *Q(x1, y1), 'S-CD-COL')
    for e in els:
        label_plan(sh, Q, e)
        bb = e['rc'].bounds
        if e['kind'] in ('F', 'M') or (e['kind'] == '?' and max(bb[2] - bb[0], bb[3] - bb[1]) < 15000): dims_plan(sh, Q, e)
    n = gap_dims(sh, Q, els)
    sh.text('FOUNDATION PLAN - CONCRETE DIMENSIONS  1:200', ax0, 3000, 500, 'S-CD-SEC')
    sh.text('RC FOOTING (CONTINUOUS) / PC 100 (DASHED, RC + 100 EACH SIDE); ALL DIMENSIONS IN MM; SIZES OF ISOLATED FOOTINGS PER '
            'SCHEDULE; DIMENSIONS BETWEEN FOOTINGS = CLEAR DISTANCE BETWEEN RC FACES.', ax0, 1900, 300, 'S-CD-TXT')
    TF = 1.0
    return n


def bubble(sh, x, y, nm):
    sh.circle(x, y, 520 * TF, 'S-CD-AX')
    sh.text(nm, x, y, (380 if len(nm) <= 3 else 300) * TF, 'S-CD-AX', align=TA.MIDDLE_CENTER)


def label_plan(sh, Q, e):
    lab = e['lab'] or ''
    x0, y0, x1, y1 = e['rc'].bounds
    rp = e['rc'].representative_point() if e['kind'] != 'F' else e['rc'].centroid
    if e['kind'] == 'F':
        pb = e['pc'].bounds
        t2 = f"{x1 - x0:.0f}x{y1 - y0:.0f}  h={e['h']}"
        t3 = f"PC {pb[2] - pb[0]:.0f}x{pb[3] - pb[1]:.0f}x{PCH}"
        cx, cy = (x0 + x1) / 2, pb[3] + 80 * TF                 # above the footing, clear of the column
        if TF == 1:
            sh.text(t3, *Q(cx, cy), 150, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
            sh.text(t2, *Q(cx, cy + 230), 170, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
            sh.text(lab, *Q(cx, cy + 490), 300, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
        else:                                                   # whole plan: name + RC size / h (PC = RC + 2 x 100)
            if min(x1 - x0, y1 - y0) >= 2400:                   # big enough: inside, upper part (clear of the column)
                cy = y1 - 120 * TF - 420 * TF
            sh.text(f"{x1 - x0:.0f}x{y1 - y0:.0f} h{e['h']}", *Q(cx, cy), 150 * TF, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
            sh.text(lab, *Q(cx, cy + 210 * TF), 220 * TF, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
        if e.get('changed'):
            sh.text(f"(DRAWN {e['drawn'][0]}x{e['drawn'][1]})", *Q(cx, y0 + 250), 140 * TF, 'S-CD-TXT', align=TA.BOTTOM_CENTER, maxw=(x1 - x0) - 100)
    else:
        if not lab: return                                       # unlabelled pieces (strip parts ...): no text
        t = lab + (f"  B={STRIP.get('B', '')}" if e['kind'] == 'ST' else '') + (f"  h={e['h']}" if e['h'] else '')
        sh.text(t, *Q(rp.x, rp.y), 260 * TF, 'S-CD-TXT', align=TA.MIDDLE_CENTER)


def dims_plan(sh, Q, e):
    """axis -> edges chain under the footing (x) and left of it (y); overall size outside the chain."""
    x0, y0, x1, y1 = e['rc'].bounds
    px0, py0, px1, py1 = e['pc'].bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    ny = nearest_axis('Y', y0, y1, cx)                    # vertical grid line -> x chain
    pts = [x0, x1]
    if ny and ny[0] < 8000: pts.append(ny[2])
    pts = sorted(set(round(p) for p in pts))
    yb = py0 - 450 * TF
    for a, b in zip(pts, pts[1:]):
        if b - a > 1: sh.dim(Q(a, y0), Q(b, y0), Q(a, yb), text=mm(b - a))
    if len(pts) > 2 and TF == 1: sh.dim(Q(x0, y0), Q(x1, y0), Q(x0, yb - 450 * TF), text=mm(x1 - x0))
    nx_ = nearest_axis('X', x0, x1, cy)                   # horizontal grid line -> y chain
    pts = [y0, y1]
    if nx_ and nx_[0] < 8000: pts.append(nx_[2])
    pts = sorted(set(round(p) for p in pts))
    xb = px0 - 450 * TF
    for a, b in zip(pts, pts[1:]):
        if b - a > 1: sh.dim(Q(x0, a), Q(x0, b), Q(xb, a), angle=90, text=mm(b - a))
    if len(pts) > 2 and TF == 1: sh.dim(Q(x0, y0), Q(x0, y1), Q(xb - 450 * TF, y0), angle=90, text=mm(y1 - y0))


def gap_dims(sh, Q, els):
    """Clear distance between neighbouring RC footings in both directions (engineer): for every footing the nearest
    footing to its right and above it whose extent overlaps it across; the dimension runs between the two faces in
    the middle of the overlap (each pair once; left / below come from the neighbour)."""
    rs = [(e, e['rc'].bounds) for e in els if e['kind'] in ('F', 'M', '?', 'ST')]
    n = 0
    for e, (x0, y0, x1, y1) in rs:
        if max(x1 - x0, y1 - y0) > 30000: continue
        for d in ('x', 'y'):
            best = None
            for f, (a0, b0, a1, b1) in rs:
                if f is e or max(a1 - a0, b1 - b0) > 30000: continue
                if d == 'x':
                    ov = min(y1, b1) - max(y0, b0); gap = a0 - x1
                else:
                    ov = min(x1, a1) - max(x0, a0); gap = b0 - y1
                if ov > 200 and 30 < gap < 15000 and (best is None or gap < best[0]):
                    best = (gap, f, (a0, b0, a1, b1), ov)
            if not best: continue
            gap, f, (a0, b0, a1, b1), ov = best
            if d == 'x':
                ym = (max(y0, b0) + min(y1, b1)) / 2
                sh.dim(Q(x1, ym), Q(a0, ym), Q(x1, ym), text=mm(gap))
            else:
                xm = (max(x0, a0) + min(x1, a1)) / 2
                sh.dim(Q(xm, y1), Q(xm, b0), Q(xm, y1), angle=90, text=mm(gap))
            n += 1
    return n


def key_plan(sh, tiles, k, ext):
    X0, Y0, X1, Y1 = ext
    s = min(4200 / (X1 - X0), 2100 / (Y1 - Y0))                 # bottom right, under the drawing
    bx, by = 35600 - (X1 - X0) * s, 250
    for n, (i, j, r) in enumerate(tiles):
        a, b, c, d = r.bounds
        pts = [(bx + (a - X0) * s, by + (b - Y0) * s), (bx + (c - X0) * s, by + (b - Y0) * s),
               (bx + (c - X0) * s, by + (d - Y0) * s), (bx + (a - X0) * s, by + (d - Y0) * s)]
        sh.pline(pts, 'S-CD-SEC', 40 if n == k else 0, True)
        sh.text(str(n + 1), (pts[0][0] + pts[2][0]) / 2, (pts[0][1] + pts[2][1]) / 2, 260 if n == k else 180, 'S-CD-SEC', align=TA.MIDDLE_CENTER)
    sh.text('KEY PLAN', bx - 200, by + (Y1 - Y0) * s / 2, 220, 'S-CD-SEC', align=TA.MIDDLE_RIGHT)


# ---------------------------------------------------------------- sections along every grid line
def cuts_along(nm, fam, c, lo, hi, els, cols):
    """Everything the grid line cuts: [(kind, u0, u1, data)] with u along the line."""
    ln = LineString([(lo, c), (hi, c)]) if fam == 'X' else LineString([(c, lo), (c, hi)])
    U = (lambda p: p[0]) if fam == 'X' else (lambda p: p[1])
    out = []
    for e in els:
        if not e['rc'].intersects(ln) and not e['pc'].intersects(ln): continue
        for key in ('pc', 'rc'):
            g = e[key].intersection(ln)
            for gg in getattr(g, 'geoms', [g]):
                if gg.is_empty or gg.geom_type != 'LineString' or gg.length < 50: continue
                us = sorted(U(p) for p in gg.coords)
                out.append((key, us[0], us[-1], e))
    for col in cols:
        g = col['r'].intersection(ln)
        if g.is_empty or g.length < 50: continue
        us = sorted(U(p) for p in g.coords)
        host = next((e for e in els if e['rc'].contains(Point(*col['c']))), None)
        if host: out.append(('col', us[0], us[-1], host))
    # wall strips drawn as open lines: two crossings one strip width apart = one strip cut (RC and PC)
    B = STRIP.get('B')
    if B:
        for kind, chains, width in (('rc', OPEN['rc'][1], B), ('pc', OPEN['pc'][1], STRIP.get('pcB', B + 2 * PCH))):
            pts = []
            for q in chains:
                g = LineString(q).intersection(ln)
                for gg in getattr(g, 'geoms', [g]):
                    if gg.geom_type == 'Point': pts.append(U((gg.x, gg.y)))
            pts = sorted(set(round(p) for p in pts))
            i = 0
            while i + 1 < len(pts):
                if abs(pts[i + 1] - pts[i] - width) < 60:
                    out.append((kind, pts[i], pts[i + 1], STRIP_EL)); i += 2
                else: i += 1
    crossing = []
    for nm2, a in AXES.items():
        if a['fam'] == fam: continue
        for c2, lo2, hi2 in a['segs']:
            if lo <= c2 <= hi and lo2 - 1 <= c <= hi2 + 1: crossing.append((c2, nm2))
    return out, sorted(set(crossing))


def section_windows(cuts, crossing, maxlen=29000, gap=2500, shown_gap=1600):
    """Group along the line; long empty stretches shortened. Returns windows: list of (pieces, crossing) where pieces
    map real u -> drawn u."""
    if not cuts: return []
    iv = sorted((u0, u1) for k, u0, u1, e in cuts)
    occ_iv = []                                                # footing intervals (no merging) for the cut points
    for a, b in iv:
        if occ_iv and a <= occ_iv[-1][1]: occ_iv[-1][1] = max(occ_iv[-1][1], b)
        else: occ_iv.append([a, b])
    occ = []
    for a, b in iv:
        if occ and a <= occ[-1][1] + gap: occ[-1][1] = max(occ[-1][1], b)
        else: occ.append([a, b])
    lo, hi = occ[0][0] - 1500, occ[-1][1] + 1500
    marks = [u for u, n in crossing if lo - 3000 <= u <= hi + 3000]
    lo, hi = min([lo] + marks) - 800, max([hi] + marks) + 800
    # breaks where nothing is drawn and no grid line falls
    keep = [(a - 800, b + 800) for a, b in occ] + [(u - 800, u + 800) for u in marks]
    keep.sort(); merged = []
    for a, b in keep:
        if merged and a <= merged[-1][1] + gap: merged[-1][1] = max(merged[-1][1], b)
        else: merged.append([a, b])
    segs = []          # (real0, real1, drawn0)
    d = 0
    for i, (a, b) in enumerate(merged):
        if i: d += shown_gap
        segs.append((a, b, d)); d += b - a
    # split into windows of <= maxlen drawn length
    wins, cur, start = [], [], 0
    for a, b, d0 in segs:
        if cur and d0 + (b - a) - start > maxlen:
            wins.append(cur); cur = []; start = d0
        if (b - a) > maxlen:                                   # one long run: cut it in a gap between footings
            gaps = sorted((g0 + g1) / 2 for (p0, g0), (g1, p1) in zip(occ_iv, occ_iv[1:]) if g1 > g0 and a < g0 and g1 < b)
            u = a
            if cur: wins.append(cur); cur = []
            while b - u > maxlen:
                ok = [g for g in gaps if u + 3000 < g <= u + maxlen]
                v = ok[-1] if ok else u + maxlen
                wins.append([(u, v, 0)]); u = v
            cur = [(u, b, 0)]; start = d0 + (u - a); continue
        cur.append((a, b, d0 - start))
    if cur: wins.append(cur)
    # a part with no footing (only grid lines) is not drawn
    return [w for w in wins if any(u1 > w[0][0] and u0 < w[-1][1] for k, u0, u1, e in cuts if k == 'rc')]


def draw_sections(doc, els, cols, start_idx, meta0):
    idx = start_idx
    lines = sorted(axis_lines(), key=lambda t: (t[1], t[0]))
    strips = []
    for nm, fam, c, lo, hi in lines:
        cuts, crossing = cuts_along(nm, fam, c, lo, hi, els, cols)
        for wi, win in enumerate(section_windows(cuts, crossing)):
            strips.append((nm, fam, c, cuts, crossing, win, wi))
    per = 3
    nsh = math.ceil(len(strips) / per)
    for s0 in range(0, len(strips), per):
        meta = dict(meta0); meta['title'] = f'CONCRETE DIMENSIONS\nSECTIONS ALONG THE GRID LINES ({s0 // per + 1}/{nsh})'
        sh = Sheet(doc, 0, -idx * 32000, meta); idx += 1
        for k, st in enumerate(strips[s0:s0 + per]):
            draw_strip(sh, 3200, 28400 - k * 8400, *st)
        sh.text('SECTIONS 1:100 - ALL DIMENSIONS IN MM, LEVELS IN M. BROKEN LINES: STRETCH SHORTENED (REAL DISTANCE DIMENSIONED).',
                1500, 800, ST['note'], 'S-CD-TXT')
    return idx, len(strips)


def draw_strip(sh, X, Ytop, nm, fam, c, cuts, crossing, win, wi):
    """One section strip: X = left of the drawing, Ytop = top of the strip band (bubbles)."""
    vs = 1.0                                                 # vertical scale = horizontal (1:100)
    yF = Ytop - 4600                                         # drawn level of T.O.PC
    def U(u):
        for a, b, d in win:
            if a - 1 <= u <= b + 1: return X + d + (u - a)
        # inside a shortened gap: proportional
        for (a, b, d), (a2, b2, d2) in zip(win, win[1:]):
            if b < u < a2: return X + d + (b - a) + (u - b) / (a2 - b) * (d2 - d - (b - a))
        return None
    Y = lambda lev_mm: yF + (lev_mm) * vs                   # mm above T.O.PC
    lo_r, hi_r = win[0][0], win[-1][1]
    title = f"SECTION ALONG AXIS {nm}" + (f"  (PART {wi + 1})" if wi else '')
    # datum lines (F.L and T.O.PC) with breaks at shortened stretches
    for (a, b, d) in win:
        sh.line((U(a), Y(-PCH)), (U(b), Y(-PCH)), 'S-CD-SEC')
    for (a, b, d), (a2, b2, d2) in zip(win, win[1:]):
        xm = (U(b) + U(a2)) / 2
        sh.break_line((U(b), Y(-PCH)), (U(a2), Y(-PCH)), 'S-CD-SEC', amp=150)
    # grid lines + bubbles
    for u, n in crossing:
        if not (lo_r <= u <= hi_r): continue
        x = U(u)
        if x is None: continue
        sh.m.add_line(sh.P(x, Y(-PCH) - 300), sh.P(x, Ytop - 1100), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 150})
        bubble(sh, x, Ytop - 600, n)
    # PC, RC, necks
    rcs = []; labelled = {}; lab_x = []
    for kind, u0, u1, e in cuts:
        a, b = max(u0, lo_r), min(u1, hi_r)
        if b - a < 30: continue
        xa, xb = U(a), U(b)
        if xa is None or xb is None: continue
        if kind == 'pc':
            sh.pline([(xa, Y(-PCH)), (xb, Y(-PCH)), (xb, Y(0)), (xa, Y(0))], 'S-CD-PC', 0, True)
        elif kind == 'rc':
            h = e['h'] or 600
            sh.pline([(xa, Y(0)), (xb, Y(0)), (xb, Y(h)), (xa, Y(h))], 'S-CD-RC', 30, True)
            rcs.append((a, b, e))
            kl = (id(e), round(a)) if e is STRIP_EL else id(e)     # every strip cut labelled, other footings once
            if kl in labelled: continue
            labelled[kl] = 1
            tof = FL + PCH / 1000 + h / 1000
            lab = (e['lab'] or ('ST-01' if e['kind'] == 'ST' else '')) + (f" h={h}" if e['h'] else ' h=?')
            xm = (xa + xb) / 2
            row = sum(1 for q in lab_x if abs(q - xm) < 2000)            # stagger labels of close footings
            lab_x.append(xm)
            yl = Y(h) + 650 + row * 520
            sh.text(lab, xm, yl + 250, 170, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
            sh.text(f'T.O.F {tof:+.2f}', xm, yl, 150, 'S-CD-TXT', align=TA.BOTTOM_CENTER)
        else:
            h = e['h'] or 600
            sh.hatch_rect(xa, Y(h), xb, Y(h) + 600, 'S-CD-COL')
            sh.break_line((xa - 120, Y(h) + 600), (xb + 120, Y(h) + 600), 'S-CD-SEC', amp=120)
    # levels at the left
    for lev, txt, dy in ((-PCH, f'F.L {FL:+.2f}', -60), (0, f'T.O.PC {FL + PCH / 1000:+.2f}', 60)):
        sh.line((X - 2100, Y(lev)), (X - 150, Y(lev)), 'S-CD-SEC')
        sh.text(txt, X - 2100, Y(lev) + dy, 140, 'S-CD-TXT', align=TA.BOTTOM_LEFT if dy > 0 else TA.TOP_LEFT)
    # chain 1: RC edges + grid lines; chain 2: grid line to grid line (real distances)
    pts = sorted(set([round(a) for a, b, e in rcs] + [round(b) for a, b, e in rcs] +
                     [round(u) for u, n in crossing if lo_r <= u <= hi_r]))
    yd1, yd2 = Y(-PCH) - 1200, Y(-PCH) - 2000
    for a, b in zip(pts, pts[1:]):
        if b - a < 20: continue
        xa, xb = U(a), U(b)
        sh.dim((xa, Y(-PCH)), (xb, Y(-PCH)), (xa, yd1), text=mm(b - a))
    ax_ = [u for u, n in crossing if lo_r <= u <= hi_r]
    for a, b in zip(ax_, ax_[1:]):
        sh.dim((U(a), Y(-PCH)), (U(b), Y(-PCH)), (U(a), yd2), text=mm(b - a))
    sh.text(title + '  1:100', X, Y(-PCH) - 2700, ST['panel'], 'S-CD-SEC', align=TA.TOP_LEFT)


def main():
    els, cols = build()
    STRIP_EL['h'] = STRIP.get('h'); STRIP_EL['lab'] = STRIP.get('name', 'ST-01')
    doc = new_doc()
    for n, col in LAYERS.items():
        if n not in doc.layers: doc.layers.add(n, color=col)
    meta0 = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                 rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='1:100', prefix='SDW-STR-CD')
    meta0.update(PRJ.get('meta', {})); meta0['scale'] = '1:100'
    meta0['notes'] = ['ALL DIMENSIONS IN MM; LEVELS IN M.', 'PC 100 UNDER ALL FOOTINGS.']
    if '--parts' in sys.argv:                                  # plan in A3 parts (1:100) + sections in one file
        idx, nt = draw_plan(doc, els, cols, 0, meta0)
    else:                                                      # whole plan on one A0 sheet (1:200), own file
        pdoc = new_doc()
        for n, col in LAYERS.items():
            if n not in pdoc.layers: pdoc.layers.add(n, color=col)
        ds = pdoc.dimstyles.duplicate_entry('GB100', 'GB200'); ds.dxf.dimscale = 200
        ng = draw_full_plan(pdoc, els, cols, meta0)
        pdoc.saveas('out/CONCRETE_DIM_PLAN.dxf')
        print('whole plan: out/CONCRETE_DIM_PLAN.dxf, gaps dimensioned', ng)
        idx, nt = 0, 0
    idx2, ns = draw_sections(doc, els, cols, idx, meta0)
    doc.saveas('out/CONCRETE_DIM.dxf' if '--parts' in sys.argv else 'out/CONCRETE_DIM_SECTIONS.dxf')
    unl = [e for e in els if not e['lab']]
    print(f'plan parts {nt}, section strips {ns}, sheets {idx2}; footings {len(els)} (unlabelled {len(unl)}), '
          f'schedule size differs from drawn: {sum(1 for e in els if e.get("changed"))}; h unknown: {sum(1 for e in els if not e["h"])}')


if __name__ == '__main__':
    main()
