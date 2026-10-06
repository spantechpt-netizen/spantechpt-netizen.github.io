"""Isolated footing shop drawings, one A3 sheet per footing type, in the office ASD-style call-outs:
   (mark) 37Ø25  L=5.40m  S=11.0cm  - B2   ;  straight length + leg lengths in metres beside the bar,
   distribution line with the dot where the drawn bar crosses it, overall sizes in mm, thickness in a circle.
Panels: BOTTOM REINFORCEMENT PLAN @ X&Y, TOP REINFORCEMENT PLAN @ X&Y (when the schedule has top bars),
FOUNDATION SIDE REINFORCEMENT, and a section through the footing."""
import json, math, pickle, sys
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs

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
            if layer == 'T' and f['bot'][0]:                     # top U sits inside the legs of the bottom U
                run -= 2 * (f['bot'][1] if along == 'X' else f['bot'][3])
            across = f['W'] if along == 'X' else f['L']
            is_long = (along == 'X') == long_is_x
            tag = (layer + ('1' if is_long else '2')) if layer == 'B' else (layer + ('2' if is_long else '1'))
            out.append(dict(layer=layer, tag=tag, along=along, d=d, s=s, n=count(across, s),
                            straight=run, leg=lg, L=run + 2 * lg, up=up))
    return out


def side_bars(f, ds=12):
    """Perimeter side bars (loops) placed INSIDE the main U-bar legs (engineer, Oct 2026): the 70 mm cover stays on
    the main bars, the loop size is reduced by the main bar diameter and its own. Rows every <= 300 mm of free height.
    Loops longer than a stock bar are made of equal pieces lapped 60 d. Chairs Ø16 @100x100cm."""
    dB = max(f['bot'][1], f['bot'][3])
    dB += max(f['top'][1], f['top'][3]) if f['top'][0] else 0    # inside the bottom AND the top U legs
    off = COVER + dB + ds / 2                                    # centre line of the loop from the face
    lx, ly = round(f['L'] - 2 * off), round(f['W'] - 2 * off)
    free = f['h'] - 2 * COVER
    rows = max(1, math.ceil(free / 300) - 1)
    per = 2 * (lx + ly)
    lp = 60 * ds
    pieces = 1 if per + lp <= 12000 else math.ceil(per / (12000 - lp))
    Lp = round((per / pieces + lp) / 10) * 10
    chair_n = max(4, math.ceil(f['L'] / 1000) * math.ceil(f['W'] / 1000))
    return dict(rows=rows, ds=ds, off=off, lx=lx, ly=ly, pieces=pieces, L=Lp, chairs=chair_n,
                chair_L=300 + (f['h'] - 2 * COVER - 120) * 2 // 1 + 400 + 300)


def draw_sheet(doc, idx, f, meta, bl):
    sh = Sheet(doc, 0, -idx * 32000, meta)
    bars = bars_for(f)
    k = min(4.0, 10000 / f['W'], 14500 / f['L'])     # drawing factor: 4 = 1:25 on the 1:100 frame
    for b in bars:
        b['mk'] = bl.add(b['d'], ('U', b['leg'], b['straight'], b['leg']), b['L'], b['n'], f['no'], b['tag'])
    sb = side_bars(f)
    sb['mk'] = bl.add(sb['ds'], ('ST', sb['lx'], sb['ly']) if sb['pieces'] == 1 else ('S', sb['L']), sb['L'], sb['rows'] * sb['pieces'], f['no'], 'SB')
    sb['mk_ch'] = bl.add(16, ('CH', 300, f['h'] - 2 * COVER - 120, 400), sb['chair_L'], sb['chairs'], f['no'], 'CH')
    mk = lambda b: b['mk']
    draw_legend(sh, 21000, 27900)
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
        sh.text(f['name'], ox, oy + H_ + 250, 400, 'S-AXIS-TXT')          # panel name above the outline, clear of the bars
        cx0, cy0, cx1, cy1 = f['col']
        sh.hatch_rect(*P(cx0, cy0), *P(cx1, cy1))
        sh.circle(*P(f['L'] * 0.70, f['W'] * 0.32), 330, 'S-SEC')
        sh.text(str(f['h']), *P(f['L'] * 0.70, f['W'] * 0.32), 260, 'S-SEC', align=TA.MIDDLE_CENTER)
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
                    sh.pline(pts, lay, 30, r=3 * b['d'] * k)
                    sh.text(f"{b['straight'] / 1000:.2f}", P((x0 + x1) / 2, y)[0], P(0, y)[1] + 150, 260, 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x0, y)[0] + 100, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x1, y)[0] - 100, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    # distribution line across Y with the dot at the bar
                    xd = f['L'] * (0.13 if kind == 'B' else 0.90)
                    sh.line(P(xd, 0), P(xd, f['W']), 'S-DIM')
                    sh.circle(*P(xd, y), 90, 'S-DIM')
                    tx, ty = P(f['L'] * (0.17 if kind == 'B' else 0.24), y + (f['W'] * 0.09 if kind == 'B' else -f['W'] * 0.12))
                else:
                    x = f['L'] * (0.84 if kind == 'B' else 0.16)
                    y0, y1 = COVER, f['W'] - COVER
                    pts = [(P(x, y0)[0] - sgn * lgk, P(x, y0)[1]), P(x, y0), P(x, y1), (P(x, y1)[0] - sgn * lgk, P(x, y1)[1])]
                    sh.pline(pts, lay, 30, r=3 * b['d'] * k)
                    sh.text(f"{b['straight'] / 1000:.2f}", P(x, 0)[0] + 200, P(x, (y0 + y1) / 2)[1], 260, 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y0)[1] + 100, 220, 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y1)[1] - 100, 220, 'S-DIM', align=TA.TOP_CENTER)
                    yd = f['W'] * 0.10
                    sh.line(P(0, yd), P(f['L'], yd), 'S-DIM')
                    sh.circle(*P(x, yd), 90, 'S-DIM')
                    # call-out along the bar, on the side away from its length (clear of the column)
                    sh.ctext(m, callout(b['n'], b['d'], m, b['L'], b['s'], b['tag']), P(x, 0)[0] - 120, P(0, (y0 + y1) / 2)[1] + (700 if kind == 'B' else 0), 230, 'S-RFT-TXT',
                            rot=90, align=TA.BOTTOM_CENTER, maxw=H_ - 800)
                    continue
                sh.ctext(m, callout(b['n'], b['d'], m, b['L'], b['s'], b['tag']), tx, ty, 260, 'S-RFT-TXT')
        else:
            o = sb['off']
            sh.pline([P(o, o), P(f['L'] - o, o), P(f['L'] - o, f['W'] - o), P(o, f['W'] - o)], 'S-RFT-STIR', 30, True, r=3 * sb['ds'] * k)
            sh.text(f"{sb['lx'] / 1000:.2f}", *P(f['L'] / 2, o + 60), 230, 'S-DIM', align=TA.BOTTOM_CENTER)
            sh.text(f"{sb['ly'] / 1000:.2f}", P(f['L'] - o, 0)[0] - 120, P(0, f['W'] / 2)[1], 230, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.84)
            sh.ctext(sb['mk'], callout(sb['rows'] * sb['pieces'], sb['ds'], sb['mk'], sb['L'], layer='SB'), tx, ty, 260, 'S-RFT-TXT')
            sh.text(f"({sb['rows']} ROW(S) INSIDE THE MAIN BARS" + (f", {sb['pieces']} PIECES / ROW LAPPED 60d)" if sb['pieces'] > 1 else ")"), tx, ty - 380, 200, 'S-RFT-TXT')
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.14)
            sh.ctext(sb['mk_ch'], callout(sb['chairs'], 16, sb['mk_ch'], sb['chair_L'], 1000, 'CHAIRS'), tx, ty, 260, 'S-RFT-TXT')
    # ---- SECTION along X (bars along X = lines, bars along Y = dots) ----
    ks = min(k, 9800 / (f['L'] + 200), 7500 / (f['h'] + 900))       # room for the call-outs before the title block
    sx, sy = 18200 + 100 * ks, R2 + 1700
    Q = lambda x, y: (sx + x * ks, sy + y * ks)
    L, h, c = f['L'], f['h'], COVER
    sh.pline([Q(-100, -100), Q(L + 100, -100), Q(L + 100, 0), Q(-100, 0)], 'S-GB-CONC', 0, True)          # PC
    sh.pline([Q(0, 0), Q(L, 0), Q(L, h), Q(0, h)], 'S-GB-CONC', 0, True)
    cx0, cx1 = f['col'][0], f['col'][2]
    sh.hatch_rect(*Q(cx0, h), *Q(cx1, h + 700))                                                         # column / neck
    def dots(y, d, s_, layer, xa, xb):          # cut bars between xa and xb; the end bars sit in the bends of the U
        n_ = max(1, round((xb - xa) / s_))
        for j in range(n_ + 1):
            x = xa + (xb - xa) * j / n_
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': layer}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(d / 2 * ks, 18), 0, 360)
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
    side = sb
    xs_ = c + (BX['d'] if bx_ else 0) + (TX['d'] + 2 if tx_ else 0) + side['ds'] / 2 + 2   # side bars INSIDE both U legs
    if bx_:
        top_of_leg = (h - c - dT - 15) if tx_ else (h - c)
        xl, xr = c + BX['d'] / 2, L - c - BX['d'] / 2
        sh.pline([Q(xl, top_of_leg), Q(xl, yX), Q(xr, yX), Q(xr, top_of_leg)], 'S-RFT-BOT', max(BX['d'] * ks, 20), r=3 * BX['d'] * ks)
        dots(yY, BY['d'], BY['s'], 'S-RFT-BOT', xl + (BX['d'] + BY['d']) / 2, xr - (BX['d'] + BY['d']) / 2)
        lines.append((yX, BX['mk'], callout(BX['n'], BX['d'], BX['mk'], BX['L'], BX['s'], BX['tag'])))
        lines.append((yY, BY['mk'], callout(BY['n'], BY['d'], BY['mk'], BY['L'], BY['s'], BY['tag'])))
    if tx_:
        bot_of_leg = c + (dB if bx_ else 0) + 15
        ins = (BX['d'] + 2) if bx_ else 0                # top U sits inside the bottom U legs, side bars inside both
        xl, xr = c + ins + TX['d'] / 2, L - c - ins - TX['d'] / 2
        sh.pline([Q(xl, bot_of_leg), Q(xl, tX), Q(xr, tX), Q(xr, bot_of_leg)], 'S-RFT-TOP', max(TX['d'] * ks, 20), r=3 * TX['d'] * ks)
        dots(tY, TY['d'], TY['s'], 'S-RFT-TOP', xl + (TX['d'] + TY['d']) / 2, xr - (TX['d'] + TY['d']) / 2)
        lines.append((tX, TX['mk'], callout(TX['n'], TX['d'], TX['mk'], TX['L'], TX['s'], TX['tag'])))
        lines.append((tY, TY['mk'], callout(TY['n'], TY['d'], TY['mk'], TY['L'], TY['s'], TY['tag'])))
    # side bars (rows) on both faces
    y0, y1 = (yY + 60) if bx_ else c + 60, (tY - 60) if tx_ else h - c - 60
    for i in range(side['rows']):
        y = y0 + (i + 1) * (y1 - y0) / (side['rows'] + 1)
        for x in (xs_, L - xs_):
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(6 * ks, 18), 0, 360)
        if i == 0: lines.append((y, side['mk'], callout(side['rows'] * side['pieces'], side['ds'], side['mk'], side['L'], layer='SB')))
    # call-outs with leaders to the right
    yt = sorted(lines)
    for i, (y, mk_, t) in enumerate(yt):
        ty_ = Q(0, 0)[1] + i * 450 - 100
        sh.line(Q(L - c, y), (Q(L + 100, 0)[0] + 350, ty_ + 90), 'S-RFT-TXT')
        sh.ctext(mk_, t, Q(L + 100, 0)[0] + 450, ty_, 200)
    sh.dim(Q(0, -100), Q(L, -100), (Q(0, 0)[0], Q(0, -100)[1] - 400), text=str(L))
    sh.dim(Q(0, 0), Q(0, h), (Q(0, 0)[0] - 450, Q(0, 0)[1]), angle=90, text=str(h))
    sh.dim(Q(-100, -100), Q(-100, 0), (Q(-100, 0)[0] - 250, Q(0, -100)[1]), angle=90, text='100')
    sh.text(f'COVER {c}', Q(L / 2, 0)[0], Q(0, c / 2)[1], 150, 'S-DIM', align=TA.MIDDLE_CENTER)
    lev = PRJ.get('levels', {})
    if 'founding' in lev:
        fl = lev['founding']; tpc = fl + 0.10; tof = tpc + h / 1000
        marks_ = [(-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {tpc:+.2f}"), (h, f"T.O.F {tof:+.2f}")]
        if 'top_gb' in lev:
            neck = lev['top_gb'] - tof
            sh.text(f"NECK UP TO T.O.GB {lev['top_gb']:+.2f}", Q(cx1, 0)[0] + 300, Q(0, h + 560)[1], 170, 'S-DIM')
            sh.text(f"NECK H = {neck:.2f} m", Q(cx1, 0)[0] + 300, Q(0, h + 300)[1], 170, 'S-DIM')
            sh.break_line(Q(cx0 - 150, h + 700), Q(cx1 + 150, h + 700))                 # break line on the neck
        for yy, lab in marks_:
            sh.line(Q(-1300, yy), Q(-150, yy), 'S-DIM')
            sh.text(lab, Q(-1300, yy)[0], Q(0, yy)[1] + 50, 150, 'S-DIM', align=TA.BOTTOM_RIGHT)
    sh.text(f"SECTION 1-1  ({f['name']}, {f['h']} mm, PC 100 mm)", Q(L / 2, 0)[0], Q(0, -100)[1] - 900, 260, 'S-SEC', align=TA.TOP_CENTER)
    return bars


if __name__ == '__main__':
    lib = json.load(open('footings.json'))
    names = sys.argv[1:] or list(lib)
    doc = new_doc()
    bl = BarList()
    for i, n in enumerate(names):
        f = lib[n]
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = ['ALL DIMENSIONS IN MM, BAR LENGTHS IN M.', 'CONCRETE COVER FOR FOOTINGS = 70 MM.',
                         'PLAIN CONCRETE 100 MM UNDER FOOTINGS.', 'LAP SPLICE = 60 BAR DIAMETER (SBC).', 'MAX. BAR LENGTH = 12.0 M.']
        meta['title'] = f"STRUCTURAL FOUNDATION\nREINFORCEMENT - {n}  (NO={f['no']})"
        meta['dwg'] = f"{meta['prefix'].replace('GB', 'FDN')}-{n}"
        draw_sheet(doc, i, f, meta, bl)
    meta['title'] = 'STRUCTURAL FOUNDATION'; meta['dwg'] = meta['prefix'].replace('GB', 'FDN')
    nb = draw_bbs(doc, len(names), bl.sorted(), meta)
    doc.saveas('out/FOOTINGS.dxf')
    print('sheets', len(names), '+ BBS', nb)
