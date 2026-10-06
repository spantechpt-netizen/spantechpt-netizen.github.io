"""Column neck (starter) shop drawings: one A3 sheet per (column type, footing type) pair.
The bar arrangement and the tie shapes are read from the consultant's COLUMN SCHEDULE block, so the section
is the designer's own; the elevation runs from the footing (bars bent 90 deg on the bottom mesh) to the top of
the grade beams plus the column lap. Call-outs in the office format, BBS sheet at the end."""
import json, math, pickle, sys
import ezdxf
from ezdxf import recover
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, lap

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
    # every tie keeps the designer's exact shape: the drawn tie set is placed so the outer tie sits on the 40 mm cover
    allp = [p for t in col['tieset'] for p in t['poly']]
    ox0, oy0 = min(p[0] for p in allp), min(p[1] for p in allp)
    ox1, oy1 = max(p[0] for p in allp), max(p[1] for p in allp)
    W, H = col['dw'], col['dh']
    sx_, sy_ = (W - 2 * COLC) / (ox1 - ox0), (H - 2 * COLC) / (oy1 - oy0)
    T = lambda p: (round(COLC + (p[0] - ox0) * sx_, 1), round(COLC + (p[1] - oy0) * sy_, 1))
    ties = []
    for t in col['tieset']:
        poly = [T(p) for p in t['poly']]
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        per = sum(math.dist(poly[j], poly[(j + 1) % len(poly)]) for j in range(len(poly)))
        ties.append(dict(poly=poly, w=round(max(xs) - min(xs)), hh=round(max(ys) - min(ys)),
                         L=int(round((per + 2 * 100) / 10) * 10), draw=[(poly, True)]))   # perimeter of the real shape + two 135-deg hooks
    s = int(1000 / col['per_m'])
    n_neck = math.floor((Hn - 100) / s) + 1                      # T.O.F + 50 .. T.O.GB - 50 (ties continue through the GB joint)
    n_ftg = 2                                                    # two ties inside the footing to hold the starters
    merged = {}
    for t in ties:                      # identical ties (e.g. the two end hexagons) share one mark
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly']); mxx = max(p[0] for p in t['poly'])
        k1 = tuple(sorted((round(p[0] - mnx), round(p[1] - mny)) for p in t['poly']))
        k2 = tuple(sorted((round(mxx - p[0]), round(p[1] - mny)) for p in t['poly']))     # the same bar turned over
        key = min(k1, k2)
        if key in merged: merged[key]['k'] += 1; merged[key]['draw'] += t['draw']
        else: merged[key] = dict(t, k=1)
    ties = list(merged.values())
    for t in ties:
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly'])
        t['norm'] = [(round(p[0] - mnx), round(p[1] - mny)) for p in t['poly']]
        t['mk'] = bl.add(10, ('POLY',) + tuple(t['norm']), t['L'], (n_neck + n_ftg) * t['k'], no, '')

    title = f"{col['name']}  {col['b']}x{col['h']}  ON  {f['name']}"
    sh.text(f'NECK {title}', 2000, 27900, 520, 'S-AXIS-TXT')
    sh.text(f"FOOTING {f['name']} {f['L']}x{f['W']}x{f['h']}", 2000, 26400, 240, 'S-SEC')
    sh.text(f"NO={no}   T.O.F {tof:+.2f}   T.O.GB {tgb:+.2f}   NECK H = {Hn / 1000:.2f} m", 2000, 27100, 280, 'S-SEC')

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
    sh.line(Q(-cw / 2 - 300, top + lp + 150), Q(cw / 2 + 300, top + lp + 250), 'S-GB-CONC')     # break line of the column above
    sh.pline([Q(-cw / 2, top), Q(-cw / 2, top + lp + 200)], 'S-GB-CONC'); sh.pline([Q(cw / 2, top), Q(cw / 2, top + lp + 200)], 'S-GB-CONC')
    # bottom mesh of the footing
    sh.pline([Q(fx0 + FC, FC + 10), Q(-fx0 - FC, FC + 10)], 'S-RFT-BOT', 30)
    # vertical bars (two outer ones drawn), foot outwards on the mesh
    for sx in (-1, 1):
        x = sx * (cw / 2 - COLC - 10 - d / 2)
        sh.pline([Q(x + sx * foot, yb), Q(x, yb), Q(x, top + lp)], 'S-RFT-TOP', max(d * k, 25))
    # ties
    y = f['h'] + 50
    while y <= top - 50:
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR'); y += s
    for y in (f['h'] - 150, f['h'] - 350):
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR')
    # dims and levels
    sh.dim(Q(cw / 2 + 1700, f['h']), Q(cw / 2 + 1700, top), Q(cw / 2 + 2100, f['h']), angle=90, text=f'{Hn}')
    sh.dim(Q(cw / 2 + 1700, top), Q(cw / 2 + 1700, top + lp), Q(cw / 2 + 2100, top), angle=90, text=f'LAP {lp}')
    sh.dim(Q(fx0, 0), Q(fx0, f['h']), Q(fx0 - 400, 0), angle=90, text=str(f['h']))
    for yy, lab in ((-100, f"F.L (B.O.PC) {LEV['founding']:+.2f}"), (0, f"T.O.PC {LEV['founding'] + .1:+.2f}"),
                    (f['h'], f"T.O.F {tof:+.2f}"), (top - gb_h, f"B.O.GB {tgb - gb_h / 1000:+.2f}"), (top, f"T.O.GB {tgb:+.2f}")):
        sh.line(Q(fx0 - 1600, yy), Q(fx0 - 150, yy), 'S-DIM')
        sh.text(lab, Q(fx0 - 1600, 0)[0], Q(0, yy)[1] + 50, 170, 'S-DIM')
    # call-outs
    sh.text(callout(col['n'], d, mv, Lv, layer='V'), Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1], 230)
    sh.text(f"(FOOT {foot} ON THE BOTTOM MESH)", Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 330, 170)
    for i, t in enumerate(ties):
        sh.text(callout((n_neck + n_ftg) * t['k'], 10, t['mk'], t['L'], s) + (f"  ({t['k']} PER SET)" if t['k'] > 1 else ''), Q(cw / 2 + 200, 0)[0], Q(0, f['h'] + Hn * 0.55)[1] - i * 330, 210)
    sh.text(f"TIES {col['sets']} SETS @{s} - {n_neck} IN THE NECK + {n_ftg} IN THE FOOTING", Q(cw / 2 + 200, 0)[0], Q(0, f['h'] + Hn * 0.55)[1] - len(ties) * 330 - 100, 170)
    sh.text('ELEVATION  (COLUMN TIES CONTINUE THROUGH THE GB JOINT)', Q(0, 0)[0], Q(0, -100)[1] - 700, 240, 'S-SEC', align=TA.TOP_CENTER)

    # ---------- SECTION A-A 1:10 (k=10) ----------
    ks = min(10.0, 9000 / max(col['b'], col['h']))
    sx0, sy0 = 23500, 14500
    P = lambda x, y: (sx0 + x * ks, sy0 + y * ks)
    sh.pline([P(0, 0), P(col['h'], 0), P(col['h'], col['b']), P(0, col['b'])], 'S-GB-CONC', 0, True) if False else None
    W, Hh = col['b_draw'], col['h_draw']
    sh.pline([P(0, 0), P(W, 0), P(W, Hh), P(0, Hh)], 'S-GB-CONC', 0, True)
    for t in ties:
        for pts, closed in t['draw']:
            sh.pline([P(*p) for p in pts], 'S-RFT-STIR', 25, closed)
        for pts, closed in t['draw']:
            cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
    for (x, y) in col['dots']:
        hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-TOP'})
        hh.paths.add_edge_path().add_arc(sh.P(*P(x, y)), d / 2 * ks, 0, 360)
    sh.dim(P(0, 0), P(W, 0), (P(0, 0)[0], P(0, 0)[1] - 600), text=str(round(W)))
    sh.dim(P(0, 0), P(0, Hh), (P(0, 0)[0] - 600, P(0, 0)[1]), angle=90, text=str(round(Hh)))
    sh.text(f"SEC A-A  {col['name']} {col['b']}x{col['h']}   {col['n']} T {d}   COVER {COLC}", P(W / 2, 0)[0], P(0, 0)[1] - 1300, 260, 'S-SEC', align=TA.TOP_CENTER)
    # tie shapes with their lengths
    tx = 23500; by = 7200
    for t in ties:
        kk = min(9.0, 2700 / max(1, t['hh']), 5500 / max(1, t['w']))
        pts = [(tx + p[0] * kk, by + p[1] * kk) for p in t['norm']]
        sh.pline(pts, 'S-RFT-STIR', 20, True)
        for j in range(len(t['norm'])):                      # every side of the real shape with its length
            a_, b_ = t['norm'][j], t['norm'][(j + 1) % len(t['norm'])]
            ln = math.dist(a_, b_)
            if ln < 25: continue
            mx, my = (pts[j][0] + pts[(j + 1) % len(pts)][0]) / 2, (pts[j][1] + pts[(j + 1) % len(pts)][1]) / 2
            ang = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            if ang > 90.5 or ang <= -89.5: ang += 180
            sh.text(str(int(round(ln))), mx, my + 50, 170, 'S-DIM', rot=ang, align=TA.BOTTOM_CENTER)
        sh.text(f"({t['mk']})  {t['w']}x{t['hh']}  L={t['L']}" + (f"  x{t['k']}/SET" if t['k'] > 1 else ''), tx, by - 600, 170, 'S-RFT-TXT')
        tx += t['w'] * kk + 1500
        if tx > 29500: tx = 23500; by -= 3600
    return Hn


if __name__ == '__main__':
    sched = read_schedule()
    pairs = [tuple(a.split(':')) for a in sys.argv[1:]] or [('C1', 'F6', '11')]
    lib = json.load(open('footings.json'))
    doc = new_doc(); bl = BarList()
    for i, (cn, fn, no) in enumerate(pairs):
        col = dict(sched[cn]); col['name'] = cn
        col['b_draw'], col['h_draw'] = col['dw'], col['dh']
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='ELEV 1:25 / SEC 1:10', prefix='SDW-STR-NCK')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = ['ALL DIMENSIONS IN MM.', 'COLUMN COVER 40 MM (SCHEDULE NOTE 4).', 'VERTICAL BARS BENT 90 DEG ON THE FOOTING MESH.',
                         'LAP SPLICE = 60 BAR DIAMETER (SBC).', 'TIES 135 DEG HOOKS 100 MM.']
        meta['title'] = f'COLUMN NECKS\n{cn} ON {fn}'
        meta['dwg'] = f"{meta['prefix']}-{cn}-{fn}"
        Hn = draw_neck(doc, i, col, lib[fn], meta, bl, int(no))
        print(cn, fn, 'neck H', Hn)
    meta['title'] = 'COLUMN NECKS'; meta['dwg'] = 'SDW-STR-NCK'
    nb = draw_bbs(doc, len(pairs), bl.sorted(), meta)
    doc.saveas('out/NECKS.dxf'); print('sheets', len(pairs), '+ BBS', nb)
