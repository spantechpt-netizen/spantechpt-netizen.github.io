"""Column neck (starter) shop drawings: one A3 sheet per (column type, footing type) pair.
The bar arrangement and the tie shapes are read from the consultant's COLUMN SCHEDULE block, so the section
is the designer's own; the elevation runs from the footing (bars bent 90 deg on the bottom mesh) to the top of
the grade beams plus the column lap. Call-outs in the office format, BBS sheet at the end."""
import json, math, pickle, re, sys
import ezdxf
from ezdxf import recover
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, lap, hooked_tie, fillet, tie_bar_centres, ST, mm, project_notes

PRJ = json.load(open('project.json'))
LEV = PRJ['levels']
COLC = 40                          # column cover (schedule note 4)
FC = PRJ.get('footing_cover', 70)


def read_schedule(dxf='main.dxf', block='COLUMN SCH'):
    """-> {type: dict(b, h, n, d, sets, dots=[(x,y)], ties=[(pts, closed)])} in mm, origin = section corner."""
    doc, _ = recover.readfile(dxf)
    ins = [e for e in doc.modelspace().query('INSERT') if e.dxf.name == block][0]
    ents = list(ins.virtual_entities())
    txt = [((v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text).strip(), v.dxf.insert.x, v.dxf.insert.y)
           for v in ents if v.dxftype() in ('TEXT', 'MTEXT')]
    types = sorted([t for t in txt if t[0] in ('C',) or (t[0].startswith('C') and t[0][1:].isdigit())], key=lambda t: -t[2])
    out = {}
    for i, (name, tx, ty) in enumerate(types):
        y_hi = (types[i - 1][2] + ty) / 2 if i else ty + 3000
        y_lo = (types[i + 1][2] + ty) / 2 if i + 1 < len(types) else ty - 6000
        inrow = lambda y: y_lo < y < y_hi
        outl = [v for v in ents if v.dxftype() == 'LWPOLYLINE' and v.dxf.layer.endswith('CORE-COLS') and inrow(v.get_points()[0][1])]
        if not outl: continue
        p = [(q[0], q[1]) for q in outl[0].get_points()]
        x0, y0 = min(a for a, b in p), min(b for a, b in p)
        x1, y1 = max(a for a, b in p), max(b for a, b in p)
        bars = next((t[0] for t in txt if inrow(t[2]) and ' T ' in t[0] and 'STIRR' not in t[0]), '0 T 0')
        stir = next((t[0] for t in txt if (inrow(t[2]) or abs(t[2] - y_hi) < 2500) and 'STIRR' in t[0] and t[2] > ty - 3000), '')
        n, d = int(bars.split('T')[0]), int(bars.split('T')[1])
        sets = int(stir.split(':')[1].split('X')[0]) if ':' in stir else 1
        per_m = int(stir.split('X')[1].split('T')[0]) if 'X' in stir else 8
        # real size from the label in the plan is in cm; the drawn outline gives the scale of the block
        # real size from the plan labels (e.g. 'C1 30X80'): the long side is drawn along x in the schedule
        sz = PRJ.get('column_sizes', {}).get(name)
        if not sz: continue
        wd, ht = max(sz), min(sz)
        k = (x1 - x0) / wd
        mm = lambda a, b: ((a - x0) / k, (b - y0) / k)
        dots = [mm(v.dxf.center.x, v.dxf.center.y) for v in ents if v.dxftype() == 'CIRCLE'
                and x0 - 5 <= v.dxf.center.x <= x1 + 5 and y0 - 5 <= v.dxf.center.y <= y1 + 5]
        ties = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE' or not v.dxf.layer.endswith('COLS-STEL'): continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not all(x0 - 5 <= a <= x1 + 5 and y0 - 5 <= b <= y1 + 5 for a, b in q): continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 150: continue                                  # hook tails drawn as separate short polylines
            ties.append(([mm(a, b) for a, b in q], bool(v.closed)))
        # tie shapes as the designer drew them one by one beside the section (complete closed shapes)
        shapes = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE' or not v.dxf.layer.endswith('COLS-STEL'): continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not all(a > x1 + 500 and inrow(b) for a, b in q): continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 300: continue
            shapes.append(([((a - min(p[0] for p in q)) / k, (b - min(p[1] for p in q)) / k) for a, b in q], bool(v.closed)))
        if shapes:     # the tie sketches are drawn at their own scale: the largest one is the outer tie (size - 2 x cover)
            big = max(shapes, key=lambda t: max(p[0] for p in t[0]))
            r = (wd - 2 * COLC) / max(p[0] for p in big[0])
            shapes = [([(a * r, b * r) for a, b in q], c) for q, c in shapes]
        # tie set from the section (to scale): closed / open shapes -> their box; single straight legs are paired
        tieset, legs = [], []
        for pts, closed in ties:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            w_, h_ = max(xs) - min(xs), max(ys) - min(ys)
            if w_ < 15: legs.append((sum(xs) / len(xs), min(ys), max(ys), pts))
            else: tieset.append(dict(poly=list(pts)))                 # the tie exactly as drawn (open ends = hook corner)
        legs.sort()
        for a, b in zip(legs[0::2], legs[1::2]):                     # a tie drawn as two facing C-legs = one closed tie
            pa = sorted(a[3], key=lambda p: p[1]); pb = sorted(b[3], key=lambda p: -p[1])
            tieset.append(dict(poly=pa + pb))
        out[name] = dict(tieset=tieset, shapes=shapes, b=min(sz), h=max(sz), dw=wd, dh=ht, n=n, d=d, sets=sets, per_m=per_m, dots=dots, ties=ties)
    return out


def read_schedule2(dxf='main.dxf', block='COLUMN SCH'):
    """Generic reader of every row of the column schedule, whatever layers the row uses (nested blocks expanded):
    bar circles (de-duplicated, mirrored when the sketch omits symmetric bars), tie polylines around them."""
    doc, _ = recover.readfile(dxf)
    ins = [e for e in doc.modelspace().query('INSERT') if e.dxf.name == block][0]
    ents = []
    def rec(e, d=0):
        for v in e.virtual_entities():
            if v.dxftype() == 'INSERT' and d < 4: rec(v, d + 1)
            else: ents.append(v)
    rec(ins)
    txt = [((v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text).strip(), v.dxf.insert.x, v.dxf.insert.y)
           for v in ents if v.dxftype() in ('TEXT', 'MTEXT')]
    types = sorted([t for t in txt if t[0] == 'C' or (t[0].startswith('C') and t[0][1:].isdigit())], key=lambda t: -t[2])
    out = {}
    for i, (name, tx, ty) in enumerate(types):
        y_hi = (types[i - 1][2] + ty) / 2 if i else ty + 3000
        y_lo = (types[i + 1][2] + ty) / 2 if i + 1 < len(types) else ty - 6000
        inrow = lambda y: y_lo < y < y_hi
        sz = PRJ.get('column_sizes', {}).get(name)
        bars = next((t[0] for t in txt if inrow(t[2]) and re.match(r'^\d+\s*T\s*\d+$', t[0])), None)
        stir = next((t[0] for t in txt if (inrow(t[2]) or abs(t[2] - y_hi) < 2500) and 'STIRR' in t[0] and t[2] > ty - 3000), '')
        if not sz or not bars: continue
        n, d = int(bars.split('T')[0]), int(bars.split('T')[1])
        sets = int(stir.split(':')[1].split('X')[0]) if ':' in stir else 1
        per_m = int(stir.split('X')[1].split('T')[0]) if 'X' in stir else 8
        circ = []
        for v in ents:
            if v.dxftype() == 'CIRCLE' and inrow(v.dxf.center.y):
                c = (v.dxf.center.x, v.dxf.center.y)
                if not any(math.dist(c, q) < 20 for q in circ): circ.append(c)
        if not circ: continue
        # the section is the left-most group of circles (tie sketches with dots may follow on the right)
        circ.sort()
        x0, y0 = min(c[0] for c in circ), min(c[1] for c in circ)
        span = max(sz) * 12                                     # generous: drawing scale is ~5-10 units / mm
        circ = [c for c in circ if c[0] - x0 < span]
        x1, y1 = max(c[0] for c in circ), max(c[1] for c in circ)
        if len(circ) < n:                                     # sketch shows one side only: mirror the missing bars
            for c in list(circ):
                for m_ in ((x0 + x1 - c[0], c[1]), (c[0], y0 + y1 - c[1]), (x0 + x1 - c[0], y0 + y1 - c[1])):
                    tol_ = 0.06 * min(x1 - x0, y1 - y0)          # ~ a bar diameter at the drawing's scale
                    if len(circ) < n and not any(math.dist(m_, q) < tol_ for q in circ): circ.append(m_)
        wd, ht = (max(sz), min(sz)) if (x1 - x0) >= (y1 - y0) else (min(sz), max(sz))
        e = COLC + 10 + d / 2
        k = ((x1 - x0) / max(1, wd - 2 * e) + (y1 - y0) / max(1, ht - 2 * e)) / 2
        mmf = lambda a, b: ((a - x0) / k + e, (b - y0) / k + e)
        dots = [mmf(*c) for c in circ]
        # sketches are imprecise: snap the bars to common rows / columns (within 20 mm)
        for ax_ in (0, 1):
            vals = sorted(set(round(p[ax_], 1) for p in dots)); grp = []
            for v_ in vals:
                if grp and v_ - grp[-1][-1] <= 20: grp[-1].append(v_)
                else: grp.append([v_])
            snap = {v_: sum(g) / len(g) for g in grp for v_ in g}
            dots = [tuple(snap[round(p[i], 1)] if i == ax_ else p[i] for i in (0, 1)) for p in dots]
        # bars along each face equally spaced between the corner bars (standard detailing; the sketch is approximate)
        mnx, mxx = min(p[0] for p in dots), max(p[0] for p in dots); mny, mxy = min(p[1] for p in dots), max(p[1] for p in dots)
        new = {}
        for ax_, lo_, hi_ in ((1, mny, mxy), (0, mnx, mxx)):
            for edge in (lo_, hi_):
                face = sorted([p for p in dots if abs(p[ax_] - edge) < 1], key=lambda p: p[1 - ax_])
                if len(face) > 2:
                    a0, a1 = face[0][1 - ax_], face[-1][1 - ax_]
                    for j, p in enumerate(face):
                        v_ = a0 + (a1 - a0) * j / (len(face) - 1)
                        new[p] = (v_, p[1]) if ax_ == 1 else (p[0], v_)
        dots_raw = dots
        dots = [new.get(p, p) for p in dots]
        ties = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE': continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not q or not all(x0 - 6 * 40 * k / 10 - 300 <= a <= x1 + 300 and y0 - 300 <= b <= y1 + 300 for a, b in q): continue
            if not inrow(q[0][1]) or v.dxf.layer.endswith(('S-COLS-IDEN', 'CORE-COLS', 'CORE-COLS-CONC-SEC')) or v.dxf.layer == 'column': continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 150: continue
            xs_ = [a for a, b in q]; ys_ = [b for a, b in q]
            if (max(xs_) - min(xs_)) / k > wd + 50 or (max(ys_) - min(ys_)) / k > ht + 50: continue   # outline / frame
            ties.append(([mmf(a, b) for a, b in q], bool(v.closed)))
        tieset, legs = [], []
        for pts, closed in ties:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if max(xs) - min(xs) < 15: legs.append((sum(xs) / len(xs), min(ys), max(ys), pts))
            elif max(ys) - min(ys) < 15: continue                  # straight horizontal piece (hook tail / link)
            else: tieset.append(dict(poly=list(pts)))
        legs.sort()
        for a_, b_ in zip(legs[0::2], legs[1::2]):
            pa = sorted(a_[3], key=lambda p: p[1]); pb = sorted(b_[3], key=lambda p: -p[1])
            tieset.append(dict(poly=pa + pb))
        out[name] = dict(tieset=tieset, shapes=[], b=min(sz), h=max(sz), dw=wd, dh=ht, n=n, d=d, sets=sets, per_m=per_m,
                         dots=dots, dots_raw=dots_raw, ties=ties)
    return out


def tie_length(pts, closed):
    L = sum(math.dist(pts[j], pts[j + 1]) for j in range(len(pts) - 1)) + (math.dist(pts[-1], pts[0]) if closed else 0)
    return int(round((L + 2 * 100) / 10) * 10)                 # + two 135-degree hooks of 100 mm


def draw_neck(doc, idx, col, f, meta, bl, no):
    """col: schedule entry; f: footing entry from footings.json."""
    sh = Sheet(doc, 0, -idx * 32000, meta)
    draw_legend(sh, 21000, 27900)
    tof = LEV['founding'] + 0.10 + f['h'] / 1000
    tgb = LEV['top_gb']
    Hn = round((tgb - tof) * 1000)
    d, lp = col['d'], lap(col['d'])
    yb = FC + max(f['bot'][1], f['bot'][3]) * 2                 # bars stand on the bottom mesh
    foot = max(12 * d, 300)                                      # 90-degree foot on the mesh
    vert = (f['h'] - yb) + Hn + lp                               # up to T.O.GB + column lap
    Lv = int(round((vert + foot) / 10) * 10)
    mv = bl.add(d, ('L', foot, vert, 0), Lv, col['n'], no, 'V')
    # bars: corner bars centred at cover + tie dia + d/2 from the faces, the others spaced as the designer drew them;
    # every tie wraps exactly the bars it holds in the designer's section, keeping its shape (rectangle, hexagon ...)
    from shapely.geometry import Polygon, MultiPoint, Point
    ds = 10
    W, H = col['dw'], col['dh']
    dx0, dy0 = min(p[0] for p in col['dots']), min(p[1] for p in col['dots'])
    dx1, dy1 = max(p[0] for p in col['dots']), max(p[1] for p in col['dots'])
    e = COLC + ds + d / 2
    T = lambda p: (e + (p[0] - dx0) * (W - 2 * e) / (dx1 - dx0), e + (p[1] - dy0) * (H - 2 * e) / (dy1 - dy0))
    col['bars'] = [T(p) for p in col['dots']]
    hall = MultiPoint(col['bars']).convex_hull
    lim_cl, lim_oo = hall.buffer(d / 2 + ds / 2, join_style=2), hall.buffer(d / 2 + ds, join_style=2)
    ties = []
    for t in col['tieset']:
        pg = Polygon(t['poly']).buffer(0)
        held = [T(p) for p, r_ in zip(col['dots'], col.get('dots_raw', col['dots'])) if pg.buffer(20).contains(Point(r_))]   # held as drawn
        if len(held) < 2: continue
        hull = MultiPoint(held).convex_hull
        cl = hull.buffer(d / 2 + ds / 2, join_style=2).intersection(lim_cl).simplify(1)   # centre line, cut flat at the outer tie
        oo = hull.buffer(d / 2 + ds, join_style=2).intersection(lim_oo).simplify(1)                      # out-to-out (bending dimensions)
        poly = [(round(x, 1), round(y, 1)) for x, y in list(cl.exterior.coords)[:-1]]
        out = [(round(x), round(y)) for x, y in list(oo.exterior.coords)[:-1]]
        xs = [p[0] for p in out]; ys = [p[1] for p in out]
        ties.append(dict(poly=out, w=round(max(xs) - min(xs)), hh=round(max(ys) - min(ys)),
                         L=int(round((oo.exterior.length + 2 * 100) / 10) * 10), draw=[(poly, True)]))   # out-to-out perimeter + two 135-deg hooks
    s = int(1000 / col['per_m'])
    n_neck = math.floor((Hn - 100) / s) + 1                      # T.O.F + 50 .. T.O.GB - 50 (ties continue through the GB joint)
    n_ftg = 2                                                    # two ties inside the footing to hold the starters
    merged = {}
    def shape_key(t, flip):
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly']); mxx = max(p[0] for p in t['poly'])
        return sorted(((mxx - p[0]) if flip else (p[0] - mnx), p[1] - mny) for p in t['poly'])
    same = lambda a, b: len(a) == len(b) and all(min(math.dist(p, q) for q in b) <= 4 for p in a)
    for i_, t in enumerate(ties):       # identical ties (e.g. the two end hexagons, one turned over) share one mark
        k0 = shape_key(t, False)
        hit = next((m for m in merged.values() if same(k0, m['key']) or same(shape_key(t, True), m['key'])), None)
        if hit: hit['k'] += 1; hit['draw'] += t['draw']
        else: merged[i_] = dict(t, k=1, key=k0)
    ties = list(merged.values())
    for t in ties:
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly'])
        t['norm'] = [(round(p[0] - mnx), round(p[1] - mny)) for p in t['poly']]
        t['mk'] = bl.add(10, ('POLY',) + tuple(t['norm']), t['L'], (n_neck + n_ftg) * t['k'], no, '')

    title = f"{col['name']}  {col['b']}x{col['h']}  ON  {f['name']}"
    sh.text(f'NECK {title}', 2000, 27900, ST['name'], 'S-AXIS-TXT')
    sh.text(f"FOOTING {f['name']} " + (f"(COMBINED / RAFT / STRAP - SEE PLAN)  h={f['h']}" if f.get('part') else f"{f['L']}x{f['W']}x{f['h']}")
            + (f"  - {f['note']}" if f.get('note') else ''), 2000, 26400, ST['sub'], 'S-SEC', maxw=18000)
    sh.text(f"NO={no}   T.O.F {tof:+.2f}   T.O.GB {tgb:+.2f}   NECK H = {mm(Hn)}", 2000, 27100, ST['sub'], 'S-SEC')

    # ---------- ELEVATION 1:25 (k=4) on the wide face ----------
    k = min(4.0, 21000 / (f['h'] + Hn + lp + 1400))
    ex, ey = 11000, 2600 + 100 * k
    Q = lambda x, y: (ex + x * k, ey + y * k)
    Lf = f['L']; cw = col['h'] if col['h'] >= col['b'] else col['b']          # wide face of the column
    fx0 = -Lf / 2
    sh.pline([Q(fx0 - 100, -100), Q(-fx0 + 100, -100), Q(-fx0 + 100, 0), Q(fx0 - 100, 0)], 'S-GB-CONC', 0, True)
    sh.pline([Q(fx0, 0), Q(-fx0, 0), Q(-fx0, f['h']), Q(fx0, f['h'])], 'S-GB-CONC', 0, True)
    top = f['h'] + Hn
    sh.pline([Q(-cw / 2, f['h']), Q(-cw / 2, top), Q(cw / 2, top), Q(cw / 2, f['h'])], 'S-GB-CONC')
    gb_h = 700
    for sx in (-1, 1):                                               # grade beams framing in (dashed outline)
        sh.pline([Q(sx * cw / 2, top), Q(sx * (cw / 2 + 1500), top), Q(sx * (cw / 2 + 1500), top - gb_h), Q(sx * cw / 2, top - gb_h)], 'S-SEC')
    sh.break_line(Q(-cw / 2 - 300, top + lp + 200), Q(cw / 2 + 300, top + lp + 200))            # break line of the column above
    sh.pline([Q(-cw / 2, top), Q(-cw / 2, top + lp + 200)], 'S-GB-CONC'); sh.pline([Q(cw / 2, top), Q(cw / 2, top + lp + 200)], 'S-GB-CONC')
    # bottom mesh of the footing
    sh.pline([Q(fx0 + FC, FC + 10), Q(-fx0 - FC, FC + 10)], 'S-RFT-BOT', 30)
    # vertical bars (two outer ones drawn), foot outwards on the mesh
    for sx in (-1, 1):
        x = sx * (cw / 2 - COLC - 10 - d / 2)
        sh.pline([Q(x + sx * foot, yb), Q(x, yb), Q(x, top + lp)], 'S-RFT-TOP', max(d * k, 25), r=3 * d * k)
    # ties
    y = f['h'] + 50
    while y <= top - 50:
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR'); y += s
    for y in (f['h'] - 150, f['h'] - 350):
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR')
    # distribution line of the ties: vertical line over the tie zone, ticks at the ties, leader to the call-outs
    xd = -cw / 2 + cw * 0.3
    y0d, y1d = f['h'] + 50, f['h'] + 50 + (n_neck - 1) * s
    sh.line(Q(xd, f['h'] - 350), Q(xd, y1d), 'S-DIM')
    for yy in (f['h'] - 350, f['h'] - 150, y0d, (y0d + y1d) / 2, y1d):
        sh.line(Q(xd - 25, yy - 25), Q(xd + 25, yy + 25), 'S-DIM')
    ylead = f['h'] + Hn * 0.55
    sh.line(Q(xd, ylead), (Q(cw / 2 + 120, 0)[0], Q(0, ylead)[1] + 100), 'S-DIM')
    # section cut A-A
    ya = f['h'] + Hn * 0.18
    sh.line(Q(-cw / 2 - 600, ya), Q(cw / 2 + 600, ya), 'S-SEC')
    for sx_ in (-1, 1):
        sh.line(Q(sx_ * (cw / 2 + 600), ya), Q(sx_ * (cw / 2 + 600), ya + 200), 'S-SEC')
        sh.text('A', Q(sx_ * (cw / 2 + 650), 0)[0], Q(0, ya + 220)[1], 300, 'S-SEC', align=TA.BOTTOM_CENTER)
    # dims and levels
    XD = cw / 2 + 2500                                               # dimension line clear of the call-outs
    sh.dim(Q(XD, f['h']), Q(XD, top), Q(XD + 400, f['h']), angle=90, text=f'{Hn}')
    sh.dim(Q(XD, top), Q(XD, top + lp), Q(XD + 400, top), angle=90, text=f'LAP {lp}')
    sh.dim(Q(fx0, 0), Q(fx0, f['h']), Q(fx0 - 400, 0), angle=90, text=str(f['h']))
    for yy, lab in ((-100, f"F.L (B.O.PC) {LEV['founding']:+.2f}"), (0, f"T.O.PC {LEV['founding'] + .1:+.2f}"),
                    (f['h'], f"T.O.F {tof:+.2f}"), (top - gb_h, f"B.O.GB {tgb - gb_h / 1000:+.2f}"), (top, f"T.O.GB {tgb:+.2f}")):
        sh.line(Q(fx0 - 1600, yy), Q(fx0 - 150, yy), 'S-DIM')
        sh.text(lab, Q(fx0 - 1600, 0)[0], Q(0, yy)[1] + 50, 170, 'S-DIM')
    # call-outs
    sh.ctext(mv, callout(col['n'], d, mv, Lv, layer='V'), Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1], ST['call'])
    sh.text(f"(FOOT {foot} ON THE BOTTOM MESH)", Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 400, ST['note'])
    for i, t in enumerate(ties):
        sh.ctext(t['mk'], callout((n_neck + n_ftg) * t['k'], 10, t['mk'], t['L'], s) + (f"  ({t['k']} PER SET)" if t['k'] > 1 else ''), Q(cw / 2 + 200, 0)[0], Q(0, f['h'] + Hn * 0.55)[1] - i * 520, ST['call'], maxw=(XD - cw / 2 - 350) * k)
    yt_ = Q(0, f['h'] + Hn * 0.55)[1] - len(ties) * 520 - 100
    sh.text(f"TIES {col['sets']} SETS @{s}", Q(cw / 2 + 200, 0)[0], yt_, ST['note'])
    sh.text(f"{n_neck} IN THE NECK + {n_ftg} IN THE FOOTING", Q(cw / 2 + 200, 0)[0], yt_ - 260, ST['note'])
    sh.text('ELEVATION  (COLUMN TIES CONTINUE THROUGH THE GB JOINT)', Q(0, 0)[0], Q(0, -100)[1] - 700, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)

    # ---------- SECTION A-A 1:10 (k=10) ----------
    ks = min(10.0, 9000 / max(col['b'], col['h']))
    sx0, sy0 = 24600, 14500
    P = lambda x, y: (sx0 + x * ks, sy0 + y * ks)
    sh.pline([P(0, 0), P(col['h'], 0), P(col['h'], col['b']), P(0, col['b'])], 'S-GB-CONC', 0, True) if False else None
    W, Hh = col['b_draw'], col['h_draw']
    sh.pline([P(0, 0), P(W, 0), P(W, Hh), P(0, Hh)], 'S-GB-CONC', 0, True)
    for t in ties:
        for pts, closed in t['draw']:
            for seg in hooked_tie(pts, col['bars'], rc=d / 2 + ds / 2):
                sh.pline([P(*p) for p in seg], 'S-RFT-STIR', 25)
    for (x, y) in col['bars']:
        hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-TOP'})
        hh.paths.add_edge_path().add_arc(sh.P(*P(x, y)), d / 2 * ks, 0, 360)
    sh.dim(P(0, 0), P(W, 0), (P(0, 0)[0], P(0, 0)[1] - 600), text=str(round(W)))
    sh.dim(P(0, 0), P(0, Hh), (P(0, 0)[0] - 600, P(0, 0)[1]), angle=90, text=str(round(Hh)))
    sh.text(f"SEC A-A  {col['name']} {col['b']}x{col['h']}   {col['n']} T {d}   COVER {COLC}", P(W / 2, 0)[0], P(0, 0)[1] - 1300, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # tie shapes with their lengths
    tx = 23500; by = 8400
    sh.text('TIE LENGTHS L INCLUDE TWO 135-DEG HOOKS x 100 (OUT-TO-OUT DIMENSIONS)', 23500, 11500, ST['note'], 'S-RFT-TXT', maxw=9500)
    for t in ties:
        kk = min(9.0, 2700 / max(1, t['hh']), 5500 / max(1, t['w']))
        nm = t['norm']; nn = len(nm)
        cb = tie_bar_centres(nm, d / 2 + 10)              # bar centres for the out-to-out shape
        Z = lambda p: (tx + p[0] * kk, by + p[1] * kk)
        segs = hooked_tie(nm, cb, tail=100, rc=d / 2 + 10)
        for sg_ in segs:
            sh.pline([Z(*[p]) if False else Z(p) for p in sg_], 'S-RFT-STIR', 20)
        # one or two sides dimensioned (engineer's note): the top side and the vertical side, plus one slanted side
        ed = [(nm[j], nm[(j + 1) % nn]) for j in range(nn)]
        hor = max((e_ for e_ in ed if abs(e_[0][1] - e_[1][1]) < 2), key=lambda e_: (e_[0][1], math.dist(*e_)), default=None)
        ver = max((e_ for e_ in ed if abs(e_[0][0] - e_[1][0]) < 2), key=lambda e_: (math.dist(*e_), -e_[0][0]), default=None)
        sl = [e_ for e_ in ed if abs(e_[0][1] - e_[1][1]) >= 2 and abs(e_[0][0] - e_[1][0]) >= 2 and math.dist(*e_) > 25]
        for e_ in [x for x in (hor, ver, sl[0] if sl else None) if x]:
            a_, b_ = e_
            pa_, pb_ = Z(a_), Z(b_)
            mx, my = (pa_[0] + pb_[0]) / 2, (pa_[1] + pb_[1]) / 2
            ang = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            if ang > 90.5 or ang <= -89.5: ang += 180
            cx_ = sum(p[0] for p in nm) / nn; cy_ = sum(p[1] for p in nm) / nn
            nx_, ny_ = (a_[0] + b_[0]) / 2 - cx_, (a_[1] + b_[1]) / 2 - cy_; hn = math.hypot(nx_, ny_) or 1
            sh.text(mm(math.dist(a_, b_)), mx + nx_ / hn * 200, my + ny_ / hn * 200, ST['len'], 'S-DIM', rot=ang, align=TA.MIDDLE_CENTER)
        e_ = segs[1][-1]
        sh.text('100', Z(e_)[0] + 60, Z(e_)[1] - 60, ST['len'], 'S-DIM', align=TA.TOP_LEFT)
        sh.ctext(t['mk'], f"{t['w']}x{t['hh']}" + (f"  x{t['k']}/SET" if t['k'] > 1 else ''), tx, by - 550, ST['call'], 'S-RFT-TXT')
        sh.text(f"L={mm(t['L'])}", tx, by - 1150, ST['call'], 'S-RFT-TXT')
        tx += max(t['w'] * kk, 3700) + 900
        if tx > 29500: tx = 23500; by -= 4300
    return Hn


if __name__ == '__main__':
    sched = read_schedule2()
    args = sys.argv[1:]
    if args and args[0].startswith('@'): args = open(args[0][1:]).read().split()        # @pairs.txt
    pairs = [tuple(a.split(':')) for a in args] or [('C1', 'F6', '11')]
    lib = json.load(open('footings.json'))
    import os
    if os.path.exists('footings_ext.json'): lib.update(json.load(open('footings_ext.json')))   # CF / RAFT / ST (h, steel; see plan)
    doc = new_doc(); bl = BarList()
    for i, (cn, fn, no) in enumerate(pairs):
        col = dict(sched[cn]); col['name'] = cn
        col['b_draw'], col['h_draw'] = col['dw'], col['dh']
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='ELEV 1:25 / SEC 1:10', prefix='SDW-STR-NCK')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = project_notes('COVER COLUMNS 40 (SCHEDULE NOTE 4).', 'VERTICAL BARS BENT 90 DEG ON THE FOOTING MESH.')
        meta['title'] = f'COLUMN NECKS\n{cn} ON {fn}'
        meta['dwg'] = f"{meta['prefix']}-{cn}-{fn}"
        Hn = draw_neck(doc, i, col, lib[fn], meta, bl, int(no))
        print(cn, fn, 'neck H', Hn)
    meta['title'] = 'COLUMN NECKS'; meta['dwg'] = 'SDW-STR-NCK'
    nb = draw_bbs(doc, len(pairs), bl.sorted(), meta)
    doc.saveas('out/NECKS.dxf'); print('sheets', len(pairs), '+ BBS', nb)
