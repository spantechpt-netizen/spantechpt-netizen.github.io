"""Isolated footing shop drawings, one A3 sheet per footing type, in the office ASD-style call-outs:
   (mark) 37Ø25  L=5.40m  S=11.0cm  - B2   ;  straight length + leg lengths in metres beside the bar,
   distribution line with the dot where the drawn bar crosses it, overall sizes in mm, thickness in a circle.
Panels: BOTTOM REINFORCEMENT PLAN @ X&Y, TOP REINFORCEMENT PLAN @ X&Y (when the schedule has top bars),
FOUNDATION SIDE REINFORCEMENT, and a section through the footing."""
import json, math, pickle, sys
from gen import new_doc, Sheet, TA

PRJ = json.load(open('project.json'))
COVER = PRJ.get('footing_cover', 70)
PHI = '%%c'                       # AutoCAD diameter symbol


def spacing(per_m):               # n bars per metre -> spacing in mm, floored to 5 mm
    return math.floor(1000 / per_m / 5) * 5


def count(width, s):              # bars distributed over width - 2c
    return math.ceil((width - 2 * COVER) / s) + 1


def bars_for(f):
    """f: dict(name, L (x size), W (y size), h, bot=(n_x,d_x,n_y,d_y) per m, top=same or None) -> bar list"""
    out = []
    lg = f['h'] - 2 * COVER
    for layer, (nx, dx, ny, dy), up in (('B', f['bot'], True), ('T', f['top'], False)):
        if not nx: continue
        sx, sy = spacing(nx), spacing(ny)
        # long-direction bars are the outer layer (B1 / T2), short-direction bars the inner (B2 / T1) - Roya FC11
        long_is_x = f['L'] >= f['W']
        for along, n_m, d, s in (('X', nx, dx, sx), ('Y', ny, dy, sy)):
            run = (f['L'] if along == 'X' else f['W']) - 2 * COVER
            across = f['W'] if along == 'X' else f['L']
            is_long = (along == 'X') == long_is_x
            tag = (layer + ('1' if is_long else '2')) if layer == 'B' else (layer + ('2' if is_long else '1'))
            out.append(dict(layer=layer, tag=tag, along=along, d=d, s=s, n=count(across, s),
                            straight=run, leg=lg, L=run + 2 * lg, up=up))
    return out


def side_bars(f):
    """Perimeter side bars Ø12 (loops) - rows every <= 300 mm of the free height; chairs Ø16 @100x100cm."""
    free = f['h'] - 2 * COVER
    rows = max(1, math.ceil(free / 300) - 1)
    per = 2 * (f['L'] - 2 * COVER + f['W'] - 2 * COVER) + 2 * 60 * 12        # loop + lap 60d
    chair_n = max(4, math.ceil(f['L'] / 1000) * math.ceil(f['W'] / 1000))
    return dict(rows=rows, L=per, chairs=chair_n, chair_L=300 + (f['h'] - 2 * COVER - 120) * 2 // 1 + 400 + 300)


def draw_sheet(doc, idx, f, meta):
    sh = Sheet(doc, 0, -idx * 32000, meta)
    bars = bars_for(f)
    k = min(4.0, 10000 / f['W'], 14500 / f['L'])     # drawing factor: 4 = 1:25 on the 1:100 frame
    marks = {}
    def mk(b):
        key = (b['d'], b['L'], b['tag'])
        if key not in marks: marks[key] = len(marks) + 1
        return marks[key]
    sh.text(f['name'], 2000, 27900, 600, 'S-AXIS-TXT')
    sh.circle(4800, 28150, 520, 'S-SEC'); sh.text(str(f['h']), 4800, 28150, 380, 'S-SEC', align=TA.MIDDLE_CENTER)
    sh.text(f"NO={f['no']}", 5700, 27900, 500, 'S-AXIS-TXT')
    sh.text(f"PC {f['pcL']}x{f['pcW']}x{f['pcH']}   RC {f['L']}x{f['W']}x{f['h']} mm", 9000, 27950, 280, 'S-SEC')

    R1, R2 = 14300, 2300
    panels = [('B', 'FOUNDATION BOTTOM REINFORCEMENT PLAN @ X&Y DIRECTION', 2000, R1)]
    if any(b['layer'] == 'T' for b in bars):
        panels.append(('T', 'FOUNDATION TOP REINFORCEMENT PLAN @ X&Y DIRECTION', 18200, R1))
    panels.append(('S', 'FOUNDATION SIDE REINFORCEMENT', 2000 if len(panels) == 2 else 18200, R2 if len(panels) == 2 else R1))
    W_, H_ = f['L'] * k, f['W'] * k
    for kind, title, ox, oy in panels:
        P = lambda x, y: (ox + x * k, oy + y * k)
        sh.pline([P(0, 0), P(f['L'], 0), P(f['L'], f['W']), P(0, f['W'])], 'S-GB-CONC', 0, True)
        sh.text(f['name'], ox + 250, oy + H_ - 650, 400, 'S-AXIS-TXT')
        cx0, cy0, cx1, cy1 = f['col']
        sh.hatch_rect(*P(cx0, cy0), *P(cx1, cy1))
        sh.circle(*P(f['L'] * 0.62, f['W'] * 0.72), 330, 'S-SEC')
        sh.text(str(f['h']), *P(f['L'] * 0.62, f['W'] * 0.72), 260, 'S-SEC', align=TA.MIDDLE_CENTER)
        sh.text(title, ox + W_ / 2, oy - 900, 260, 'S-SEC', align=TA.TOP_CENTER)
        # overall dims in mm
        sh.dim(P(0, 0), P(f['L'], 0), (ox, oy - 450), text=str(f['L']))
        sh.dim(P(0, 0), P(0, f['W']), (ox - 450, oy), angle=90, text=str(f['W']))
        if kind in 'BT':
            for b in [b for b in bars if b['layer'] == kind]:
                m = mk(b)
                lay = 'S-RFT-BOT' if kind == 'B' else 'S-RFT-TOP'
                lgk = min(b['leg'] * k, 1100)                    # legs shown folded into the plan
                sgn = 1 if b['up'] else -1
                if b['along'] == 'X':
                    y = f['W'] * (0.18 if kind == 'B' else 0.82)
                    x0, x1 = COVER, f['L'] - COVER
                    pts = [(P(x0, y)[0], P(x0, y)[1] + sgn * lgk), P(x0, y), P(x1, y), (P(x1, y)[0], P(x1, y)[1] + sgn * lgk)]
                    sh.pline(pts, lay, 30)
                    sh.text(f"{b['straight'] / 1000:.2f}", P((x0 + x1) / 2, y)[0], P(0, y)[1] + 150, 260, 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x0, y)[0] - 150, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x1, y)[0] + 380, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    # distribution line across Y with the dot at the bar
                    xd = f['L'] * 0.13
                    sh.line(P(xd, 0), P(xd, f['W']), 'S-DIM')
                    sh.circle(*P(xd, y), 90, 'S-DIM')
                    tx, ty = P(f['L'] * 0.10, y + (f['W'] * 0.09 if kind == 'B' else -f['W'] * 0.12))
                else:
                    x = f['L'] * (0.84 if kind == 'B' else 0.16)
                    y0, y1 = COVER, f['W'] - COVER
                    pts = [(P(x, y0)[0] - sgn * lgk, P(x, y0)[1]), P(x, y0), P(x, y1), (P(x, y1)[0] - sgn * lgk, P(x, y1)[1])]
                    sh.pline(pts, lay, 30)
                    sh.text(f"{b['straight'] / 1000:.2f}", P(x, 0)[0] + 200, P(x, (y0 + y1) / 2)[1], 260, 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y0)[1] - 180, 220, 'S-DIM', align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y1)[1] + 180, 220, 'S-DIM', align=TA.BOTTOM_CENTER)
                    yd = f['W'] * 0.10
                    sh.line(P(0, yd), P(f['L'], yd), 'S-DIM')
                    sh.circle(*P(x, yd), 90, 'S-DIM')
                    tx, ty = P(f['L'] * 0.30, f['W'] * (0.45 if kind == 'B' else 0.55))
                sh.text(str(m), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
                sh.text(f"{b['n']}{PHI}{b['d']}  L={b['L'] / 1000:.2f}m  S={b['s'] / 10:.1f}cm  - {b['tag']}", tx, ty, 260, 'S-RFT-TXT')
        else:
            sb = side_bars(f)
            off = 150 / k if k < 4 else 40
            loop = [P(COVER / 2, COVER / 2), P(f['L'] - COVER / 2, COVER / 2), P(f['L'] - COVER / 2, f['W'] - COVER / 2), P(COVER / 2, f['W'] - COVER / 2)]
            sh.pline(loop, 'S-RFT-STIR', 30, True)
            m = mk(dict(d=12, L=sb['L'], tag='SB'))
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.86)
            sh.text(str(m), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
            sh.text(f"{sb['rows']}{PHI}12  L={min(sb['L'], 12000) / 1000:.2f}m  (PER ROW, LAP 60d)  - SB", tx, ty, 260, 'S-RFT-TXT')
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.12)
            m2 = mk(dict(d=16, L=sb['chair_L'], tag='CH'))
            sh.text(str(m2), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
            sh.text(f"{sb['chairs']}{PHI}16  L={sb['chair_L'] / 1000:.2f}m  S=100*100CM  - CHAIRS", tx, ty, 260, 'S-RFT-TXT')
    # ---- SECTION along X (bars along X = lines, bars along Y = dots) ----
    ks = min(k, 13000 / (f['L'] + 200), 7500 / (f['h'] + 900))
    sx, sy = 18200 + 100 * ks, R2 + 1700
    Q = lambda x, y: (sx + x * ks, sy + y * ks)
    L, h, c = f['L'], f['h'], COVER
    sh.pline([Q(-100, -100), Q(L + 100, -100), Q(L + 100, 0), Q(-100, 0)], 'S-GB-CONC', 0, True)          # PC
    sh.pline([Q(0, 0), Q(L, 0), Q(L, h), Q(0, h)], 'S-GB-CONC', 0, True)
    cx0, cx1 = f['col'][0], f['col'][2]
    sh.hatch_rect(*Q(cx0, h), *Q(cx1, h + 700))                                                         # column / neck
    def dots(y, d, s_, layer):
        n = count(f['W'] if True else f['L'], s_)
        x = c + d / 2 + 20
        step = (L - 2 * c - d - 40) / max(1, round((L - 2 * c) / s_))
        while x <= L - c - d / 2 - 19:
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': layer}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(d / 2 * ks, 18), 0, 360)
            x += step
    bx_ = [b for b in bars if b['layer'] == 'B']; tx_ = [b for b in bars if b['layer'] == 'T']
    lines = []
    def by_dir(lst, along): return next((b for b in lst if b['along'] == along), None)
    # bottom: outer layer (B1) sits on the cover
    if bx_:
        BX, BY = by_dir(bx_, 'X'), by_dir(bx_, 'Y')
        outer_is_x = BX['tag'] == 'B1'
        yX = c + BX['d'] / 2 if outer_is_x else c + BY['d'] + BX['d'] / 2
        yY = c + BX['d'] + BY['d'] / 2 if outer_is_x else c + BY['d'] / 2
        dB = BX['d'] + BY['d']
    if tx_:
        TX, TY = by_dir(tx_, 'X'), by_dir(tx_, 'Y')
        outer_is_x_t = TX['tag'] == 'T2'
        tX = h - c - TX['d'] / 2 if outer_is_x_t else h - c - TY['d'] - TX['d'] / 2
        tY = h - c - TX['d'] - TY['d'] / 2 if outer_is_x_t else h - c - TY['d'] / 2
        dT = TX['d'] + TY['d']
    side = side_bars(f)
    xs_ = c + 6                                     # side bars just inside the cover
    if bx_:
        top_of_leg = (h - c - dT - 15) if tx_ else (h - c)
        xl, xr = c + 12 + BX['d'] / 2, L - c - 12 - BX['d'] / 2
        sh.pline([Q(xl, top_of_leg), Q(xl, yX), Q(xr, yX), Q(xr, top_of_leg)], 'S-RFT-BOT', max(BX['d'] * ks, 20))
        dots(yY, BY['d'], BY['s'], 'S-RFT-BOT')
        lines.append((yX, f"({mk(BX)}) {BX['n']}{PHI}{BX['d']} @{BX['s']} - {BX['tag']}"))
        lines.append((yY, f"({mk(BY)}) {BY['n']}{PHI}{BY['d']} @{BY['s']} - {BY['tag']}"))
    if tx_:
        bot_of_leg = c + (dB if bx_ else 0) + 15
        ins = (BX['d'] + 6) if bx_ else 0           # top U sits inside the bottom U legs
        xl, xr = c + 12 + ins + TX['d'] / 2, L - c - 12 - ins - TX['d'] / 2
        sh.pline([Q(xl, bot_of_leg), Q(xl, tX), Q(xr, tX), Q(xr, bot_of_leg)], 'S-RFT-TOP', max(TX['d'] * ks, 20))
        dots(tY, TY['d'], TY['s'], 'S-RFT-TOP')
        lines.append((tX, f"({mk(TX)}) {TX['n']}{PHI}{TX['d']} @{TX['s']} - {TX['tag']}"))
        lines.append((tY, f"({mk(TY)}) {TY['n']}{PHI}{TY['d']} @{TY['s']} - {TY['tag']}"))
    # side bars (rows) on both faces
    y0, y1 = (yY + 60) if bx_ else c + 60, (tY - 60) if tx_ else h - c - 60
    for i in range(side['rows']):
        y = y0 + (i + 1) * (y1 - y0) / (side['rows'] + 1)
        for x in (xs_, L - xs_):
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(6 * ks, 18), 0, 360)
        if i == 0: lines.append((y, f"{side['rows']}{PHI}12 - SB (EACH FACE)"))
    # call-outs with leaders to the right
    yt = sorted(lines)
    for i, (y, t) in enumerate(yt):
        ty_ = Q(0, 0)[1] + i * 420 - 100
        sh.line(Q(L - c, y), (Q(L + 100, 0)[0] + 350, ty_ + 90), 'S-RFT-TXT')
        sh.text(t, Q(L + 100, 0)[0] + 450, ty_, 200)
    sh.dim(Q(0, -100), Q(L, -100), (Q(0, 0)[0], Q(0, -100)[1] - 400), text=str(L))
    sh.dim(Q(0, 0), Q(0, h), (Q(0, 0)[0] - 450, Q(0, 0)[1]), angle=90, text=str(h))
    sh.dim(Q(-100, -100), Q(-100, 0), (Q(-100, 0)[0] - 250, Q(0, -100)[1]), angle=90, text='100')
    sh.text(f'COVER {c}', Q(L / 2, 0)[0], Q(0, c / 2)[1], 150, 'S-DIM', align=TA.MIDDLE_CENTER)
    sh.text(f"SECTION 1-1  ({f['name']}, {f['h']} mm, PC 100 mm)", Q(L / 2, 0)[0], Q(0, -100)[1] - 900, 260, 'S-SEC', align=TA.TOP_CENTER)
    return marks


if __name__ == '__main__':
    lib = json.load(open('footings.json'))
    names = sys.argv[1:] or list(lib)
    doc = new_doc()
    for i, n in enumerate(names):
        f = lib[n]
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = ['ALL DIMENSIONS IN MM, BAR LENGTHS IN M.', 'CONCRETE COVER FOR FOOTINGS = 70 MM.',
                         'PLAIN CONCRETE 100 MM UNDER FOOTINGS.', 'LAP SPLICE = 60 BAR DIAMETER (SBC).', 'MAX. BAR LENGTH = 12.0 M.']
        meta['title'] = f"STRUCTURAL FOUNDATION\nREINFORCEMENT - {n}  (NO={f['no']})"
        meta['dwg'] = f"{meta['prefix'].replace('GB', 'FDN')}-{n}"
        draw_sheet(doc, i, f, meta)
    doc.saveas('out/FOOTINGS.dxf')
    print('sheets', len(names))
