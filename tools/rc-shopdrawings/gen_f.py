"""Isolated footing shop drawings, one A3 sheet per footing type, in the office ASD-style call-outs:
   (mark) 37Ø25  L=5.40m  S=11.0cm  - B2   ;  straight length + leg lengths in metres beside the bar,
   distribution line with the dot where the drawn bar crosses it, overall sizes in mm, thickness in a circle.
Panels: BOTTOM REINFORCEMENT PLAN @ X&Y, TOP REINFORCEMENT PLAN @ X&Y (when the schedule has top bars),
FOUNDATION SIDE REINFORCEMENT, and a section through the footing."""
import json, math, pickle, sys
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, ST, mm, project_notes

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
            tot = run + 2 * lg; lp = 60 * d
            p = 1 if tot <= 12000 else math.ceil((tot - lp) / (12000 - lp))       # equal pieces lapped 60 d
            Lp = int(math.ceil((tot + (p - 1) * lp) / p / 10) * 10)
            out.append(dict(layer=layer, tag=tag, along=along, d=d, s=s, n=count(across, s),
                            straight=run, leg=lg, L=run + 2 * lg if p == 1 else Lp, up=up, pieces=p, lap=lp))
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
    # chair Ø16: foot 300 / leg / top 400 / leg / foot 300 (out-to-out). It stands on the bottom mesh and carries
    # the top mesh: leg = h - 2 x cover - both bottom layers - both top layers (engineer: F6 650, T14 -> 454)
    ch_h = int(f['h'] - 2 * COVER - f['bot'][1] - f['bot'][3] - (f['top'][1] + f['top'][3] if f['top'][0] else 0))
    return dict(rows=rows, ds=ds, off=off, lx=lx, ly=ly, pieces=pieces, L=Lp, chairs=chair_n, ch_foot=300, ch_top=400, ch_h=ch_h,
                chair_L=int(math.ceil((2 * 300 + 2 * ch_h + 400) / 10) * 10))


def draw_sheet(doc, idx, f, meta, bl):
    sh = Sheet(doc, 0, -idx * 32000, meta)
    bars = bars_for(f)
    strip = f['L'] / f['W'] > 3.2                    # long narrow raft / combined footing: full-width panels stacked
    k = min(4.0, 23000 / f['L'], 4000 / f['W']) if strip else min(4.0, 9300 / f['W'], 14500 / f['L'])       # leaves room for the panel names between the rows     # drawing factor: 4 = 1:25 on the 1:100 frame
    for b in bars:
        if b['pieces'] == 1:
            b['mk'] = bl.add(b['d'], ('U', b['leg'], b['straight'], b['leg']), b['L'], b['n'], f['no'], b['tag'])
        else:                                    # end pieces with one leg, middle pieces straight
            b['mk'] = bl.add(b['d'], ('L', b['leg'], b['L'] - b['leg'], 0), b['L'], 2 * b['n'], f['no'], b['tag'])
            if b['pieces'] > 2: b['mk2'] = bl.add(b['d'], ('S', b['L']), b['L'], (b['pieces'] - 2) * b['n'], f['no'], b['tag'])
    def cot(b):                                  # call-out(s) of a main bar
        if b['pieces'] == 1: return callout(b['n'], b['d'], b['mk'], b['L'], b['s'], b['tag'])
        t = callout(2 * b['n'], b['d'], b['mk'], b['L'], b['s'], b['tag'])
        if b['pieces'] > 2: t += ' + ' + callout((b['pieces'] - 2) * b['n'], b['d'], b['mk2'], b['L'], b['s'], b['tag'])
        return t
    # additional bars written on the consultant's plan (ADD TOP / ADD BOT): straight, in their zone
    for a in f.get('adds', []):
        a['mk'] = bl.add(a['d'], ('S', a['L']), a['L'], a['n'], f['no'], 'ADD-' + a['layer'])
    sb = side_bars(f)
    sb['mk'] = bl.add(sb['ds'], ('ST', sb['lx'], sb['ly']) if sb['pieces'] == 1 else ('S', sb['L']), sb['L'], sb['rows'] * sb['pieces'], f['no'], 'SB')
    # chairs only carry a top mesh: none when the footing has no top reinforcement (engineer)
    sb['mk_ch'] = bl.add(16, ('CH', sb['ch_foot'], sb['ch_h'], sb['ch_top']), sb['chair_L'], sb['chairs'], f['no'], 'CH') if f['top'][0] else None
    mk = lambda b: b['mk']
    draw_legend(sh, 21000, 27900)
    sh.text(f['name'], 2000, 27900, ST['name'], 'S-AXIS-TXT')
    xc_ = 2000 + len(f['name']) * ST['name'] * 0.9 + 800                 # thickness circle and NO= after the name
    sh.circle(xc_, 28150, 520, 'S-SEC'); sh.text(str(f['h']), xc_, 28150, 380, 'S-SEC', align=TA.MIDDLE_CENTER)
    sh.text(f"NO={f['no']}", xc_ + 900, 27900, 500, 'S-AXIS-TXT')
    sh.text(f"PC {f['pcL']}x{f['pcW']}x{f['pcH']}   RC {f['L']}x{f['W']}x{f['h']}", xc_ + 4200, 27950, ST['sub'], 'S-SEC')

    R1, R2 = 14300, 2300
    panels = [('B', 'FOUNDATION BOTTOM REINFORCEMENT PLAN @ X&Y DIRECTION', 2000, R1)]
    if any(b['layer'] == 'T' for b in bars):
        panels.append(('T', 'FOUNDATION TOP REINFORCEMENT PLAN @ X&Y DIRECTION', 18200, R1))
    panels.append(('S', 'FOUNDATION SIDE REINFORCEMENT', 2000 if len(panels) == 2 else 18200, R2 if len(panels) == 2 else R1))
    if strip:                                        # rows: bottom / top / side, one above the other
        rows_y = [21300, 14300, 7300]
        panels = [(kd, tt, 2000, rows_y[i]) for i, (kd, tt, ox_, oy_) in enumerate(panels)]
    W_, H_ = f['L'] * k, f['W'] * k
    for kind, title, ox, oy in panels:
        P = lambda x, y: (ox + x * k, oy + y * k)
        sh.pline([P(0, 0), P(f['L'], 0), P(f['L'], f['W']), P(0, f['W'])], 'S-GB-CONC', 0, True)
        sh.text(f['name'], ox, oy + H_ + 250, 400, 'S-AXIS-TXT')          # panel name above the outline, clear of the bars
        for c_ in (f.get('cols') or ([f['col']] if f.get('col') else [])):
            sh.hatch_rect(*P(c_[0], c_[1]), *P(c_[2], c_[3]))
        tpos = {'B': (0.45, 0.82), 'T': (0.55, 0.20), 'S': (0.75, 0.32)}[kind]       # thickness tag in a free corner
        sh.circle(*P(f['L'] * tpos[0], f['W'] * tpos[1]), 330, 'S-SEC')
        sh.text(str(f['h']), *P(f['L'] * tpos[0], f['W'] * tpos[1]), 260, 'S-SEC', align=TA.MIDDLE_CENTER)
        if len(title) * ST['panel'] * 0.9 > W_: sh.text(title, ox, oy - 900, ST['panel'], 'S-SEC', align=TA.TOP_LEFT)
        else: sh.text(title, ox + W_ / 2, oy - 900, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
        # overall dims in mm
        sh.dim(P(0, 0), P(f['L'], 0), (ox, oy - 450), text=str(f['L']))
        sh.dim(P(0, 0), P(0, f['W']), (ox - 450, oy), angle=90, text=str(f['W']))
        obst_ = [(f['L'] * tpos[0] - 400 / k, f['W'] * tpos[1] - 400 / k, f['L'] * tpos[0] + 400 / k, f['W'] * tpos[1] + 400 / k)]   # thickness tag
        if kind in 'BT':
            for b in [b for b in bars if b['layer'] == kind]:
                m = mk(b)
                lay = 'S-RFT-BOT' if kind == 'B' else 'S-RFT-TOP'
                lgk = min(b['leg'] * k, 1100)                    # legs shown folded into the plan
                sgn = 1 if b['up'] else -1
                ccs_ = f.get('cols') or []
                def free_y(cands, band):          # bar line + its call-out band clear of every column
                    for c in cands:
                        y_ = f['W'] * c
                        if all(cc[3] < y_ + band[0] or cc[1] > y_ + band[1] for cc in ccs_): return y_
                    return f['W'] * cands[0]
                def free_x(cands, band):
                    for c in cands:
                        x_ = f['L'] * c
                        if all(cc[2] < x_ + band[0] or cc[0] > x_ + band[1] for cc in ccs_): return x_
                    return f['L'] * cands[0]
                if b['along'] == 'X':
                    cy_ = (0.18, 0.25, 0.12, 0.32, 0.4) if kind == 'B' else (0.82, 0.75, 0.88, 0.68, 0.6)
                    band = (-300, f['W'] * 0.09 + 500 / k) if kind == 'B' else (-f['W'] * 0.12 - 500 / k, 300)
                    y = free_y(cy_, band)
                    x0, x1 = COVER, f['L'] - COVER
                    pts = [(P(x0, y)[0], P(x0, y)[1] + sgn * lgk), P(x0, y), P(x1, y), (P(x1, y)[0], P(x1, y)[1] + sgn * lgk)]
                    sh.pline(pts, lay, 30, r=3 * b['d'] * k)
                    sh.text(mm(b['straight']) + (f"  ({b['pieces']} PIECES, LAP {b['lap']})" if b['pieces'] > 1 else ''), P((x0 + x1) / 2, y)[0], P(0, y)[1] + 150, ST['len'], 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(mm(b['leg']), P(x0, y)[0] + 100, P(0, y)[1] + sgn * lgk / 2, ST['len'], 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(mm(b['leg']), P(x1, y)[0] - 100, P(0, y)[1] + sgn * lgk / 2, ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    # distribution line across Y with the dot at the bar
                    xd = f['L'] * (0.13 if kind == 'B' else 0.90)
                    sh.line(P(xd, 0), P(xd, f['W']), 'S-DIM')
                    sh.circle(*P(xd, y), 90, 'S-DIM')
                    tx, ty = P(f['L'] * (0.17 if kind == 'B' else 0.24), y + (f['W'] * 0.09 if kind == 'B' else -f['W'] * 0.12))
                    if strip:                    # flat panel: call-out just clear of the bar's length text, and of the columns
                        ty = P(0, y)[1] + 150 + ST['len'] + 200 if kind == 'B' else P(0, y)[1] - 2.4 * ST['call'] - 150
                        twx = (len(cot(b)) * ST['call'] * 1.0 + 3.2 * ST['call']) / k
                        lyy = (ty - oy) / k
                        for c in [j / 40 for j in range(2, 30)]:
                            bx_ = (f['L'] * c, lyy - 50 / k, f['L'] * c + twx, lyy + 2 * ST['call'] / k)
                            if bx_[2] < f['L'] and all(cc[2] < bx_[0] or cc[0] > bx_[2] or cc[3] < bx_[1] or cc[1] > bx_[3] for cc in ccs_):
                                tx = P(bx_[0], 0)[0]; break
                    obst_.append((x0, y - 60 / k, x1, y + 60 / k))                                 # the bar itself
                    lt_ = len(mm(b['straight']) + (f"  ({b['pieces']} PIECES, LAP {b['lap']})" if b['pieces'] > 1 else '')) * ST['len'] * 0.9 / k
                    obst_.append(((x0 + x1) / 2 - lt_ / 2, y + 100 / k, (x0 + x1) / 2 + lt_ / 2, y + (150 + ST['len'] + 80) / k))   # its length text
                else:
                    cx_ = (0.84, 0.92, 0.76, 0.68, 0.6, 0.5) if kind == 'B' else (0.16, 0.08, 0.24, 0.32, 0.4, 0.5)
                    x = free_x(cx_, (-150 - 600 / k, 300))
                    if strip:                    # flat panel: bar and its horizontal call-out together in a free spot
                        txt0 = cot(b); tw0 = (len(txt0) * ST['call'] * 1.0 + 3.2 * ST['call']) / k; spot = None
                        def ovl0(bx_):
                            return sum(max(0, min(cc[2], bx_[2]) - max(cc[0], bx_[0])) * max(0, min(cc[3], bx_[3]) - max(cc[1], bx_[1]))
                                       for cc in list(ccs_) + obst_)
                        order = sorted([j / 40 for j in range(2, 39)], key=lambda c: abs(c - cx_[0]))
                        for c in order:
                            xx = f['L'] * c
                            if any(cc[0] - 100 < xx < cc[2] + 100 for cc in ccs_): continue
                            for fy in (0.5, 0.62, 0.38, 0.75, 0.25, 0.86, 0.14, 0.44, 0.56):
                                for x0_ in (xx + 450 / k, xx - 450 / k - tw0):            # right of the bar, or left of it
                                    bx_ = (x0_, f['W'] * fy - 50 / k, x0_ + tw0, f['W'] * fy + 2 * ST['call'] / k)
                                    if bx_[0] > 100 and bx_[2] < f['L'] - 100 and ovl0(bx_) == 0: spot = (xx, bx_); break
                                if spot: break
                            if spot: break
                        if spot: x = spot[0]
                    y0, y1 = COVER, f['W'] - COVER
                    pts = [(P(x, y0)[0] - sgn * lgk, P(x, y0)[1]), P(x, y0), P(x, y1), (P(x, y1)[0] - sgn * lgk, P(x, y1)[1])]
                    sh.pline(pts, lay, 30, r=3 * b['d'] * k)
                    sh.text(mm(b['straight']) + (f"  ({b['pieces']} PIECES, LAP {b['lap']})" if b['pieces'] > 1 else ''), P(x, 0)[0] + 200, P(x, (y0 + y1) / 2)[1], ST['len'], 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(mm(b['leg']), P(x, 0)[0] - sgn * lgk / 2, P(x, y0)[1] + 100, ST['len'], 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(mm(b['leg']), P(x, 0)[0] - sgn * lgk / 2, P(x, y1)[1] - 100, ST['len'], 'S-DIM', align=TA.TOP_CENTER)
                    yd = f['W'] * 0.10
                    sh.line(P(0, yd), P(f['L'], yd), 'S-DIM')
                    sh.circle(*P(x, yd), 90, 'S-DIM')
                    # call-out along the bar, on the side away from its length (clear of the column)
                    # placed between the X bar of the panel and the far leg, the mark at its lower end
                    hc = ST['call']; hx = 2 * hc * 1.1 + hc * 0.3
                    ylo = P(0, f['W'] * 0.18 if kind == 'B' else COVER)[1] + 200
                    yhi = P(0, f['W'] - COVER if kind == 'B' else f['W'] * 0.82)[1] - 250
                    txt_ = cot(b)
                    est_ = min(len(txt_) * hc * 0.9, yhi - ylo - hx)
                    if strip:                    # flat panel: the call-out written horizontally beside the bar, clear of columns
                        if spot:
                            best = spot[1]; sh.ctext(m, txt_, *P(best[0], best[1] + 50 / k), hc, 'S-RFT-TXT'); obst_.append(best); continue
                        tw_ = (len(txt_) * hc * 1.0 + 3.2 * hc) / k
                        def ovl(bx_):           # overlap with columns / other call-outs (0 = free)
                            return sum(max(0, min(cc[2], bx_[2]) - max(cc[0], bx_[0])) * max(0, min(cc[3], bx_[3]) - max(cc[1], bx_[1]))
                                       for cc in list(ccs_) + obst_)
                        cands = []
                        for dx_ in [450 / k + j * 1200 for j in range(8)] + [-(450 / k) - tw_ - j * 1200 for j in range(8)]:
                            for fy in (0.5, 0.62, 0.38, 0.75, 0.25):
                                x0_ = x + dx_
                                bx_ = (x0_, f['W'] * fy - 50 / k, x0_ + tw_, f['W'] * fy + 2 * hc / k)
                                if 0 < bx_[0] and bx_[2] < f['L']: cands.append((ovl(bx_), abs(dx_), bx_))
                        best = min(cands)[2] if cands else (x + 450 / k, f['W'] * 0.5)
                        sh.ctext(m, txt_, *P(best[0], best[1] + 50 / k), hc, 'S-RFT-TXT')
                        ym_ = best[1] + 50 / k + hc / 2 / k
                        if best[0] > x + 500 / k: sh.line(P(x, ym_), P(best[0], ym_), 'S-RFT-TXT')          # leader to its bar
                        elif best[2] < x - 300 / k: sh.line(P(best[2], ym_), P(x, ym_), 'S-RFT-TXT')
                        obst_.append(best)
                        continue
                    sh.ctext(m, txt_, P(x, 0)[0] - 120, ylo + hx + est_ / 2, hc, 'S-RFT-TXT', rot=90, align=TA.BOTTOM_CENTER, maxw=yhi - ylo - hx)
                    continue
                sh.ctext(m, cot(b), tx, ty, ST['call'], 'S-RFT-TXT')
                tl_ = (len(cot(b)) * ST['call'] * 0.9 + 2.6 * ST['call']) / k          # its box, kept clear by the Y call-out
                obst_.append(((tx - ox) / k, (ty - oy) / k - 100 / k, (tx - ox) / k + tl_, (ty - oy) / k + 2 * ST['call'] / k))
        if False:
            for a in [a for a in f.get('adds', []) if a['layer'] == kind]:
                ax_, ay_ = a['x'], a['y']; hl = a['L'] / 2
                p0, p1 = ((ax_ - hl, ay_), (ax_ + hl, ay_)) if a['along'] == 'X' else ((ax_, ay_ - hl), (ax_, ay_ + hl))
                p0 = (min(max(p0[0], COVER), f['L'] - COVER), min(max(p0[1], COVER), f['W'] - COVER))
                p1 = (min(max(p1[0], COVER), f['L'] - COVER), min(max(p1[1], COVER), f['W'] - COVER))
                sh.pline([P(*p0), P(*p1)], 'S-RFT-TOP' if kind == 'T' else 'S-RFT-BOT', 30)
                t_ = callout(a['n'], a['d'], a['mk'], a['L'], a['s'], 'ADD-' + a['layer'])
                if a['along'] == 'X': sh.ctext(a['mk'], t_, P(*p0)[0], P(*p0)[1] + 150, ST['call'] * 0.8)
                else: sh.ctext(a['mk'], t_, P(*p0)[0] - 120, (P(*p0)[1] + P(*p1)[1]) / 2, ST['call'] * 0.8, rot=90, align=TA.BOTTOM_CENTER)
        if kind in 'BT':
            pass
        else:
            o = sb['off']
            sh.pline([P(o, o), P(f['L'] - o, o), P(f['L'] - o, f['W'] - o), P(o, f['W'] - o)], 'S-RFT-STIR', 30, True, r=3 * sb['ds'] * k)
            sh.text(mm(sb['lx']), *P(f['L'] / 2, o + 60), ST['len'], 'S-DIM', align=TA.BOTTOM_CENTER)
            sh.text(mm(sb['ly']), P(f['L'] - o, 0)[0] - 120, P(0, f['W'] / 2)[1], ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.84)
            sh.ctext(sb['mk'], callout(sb['rows'] * sb['pieces'], sb['ds'], sb['mk'], sb['L'], layer='SB'), tx, ty, ST['call'], 'S-RFT-TXT')
            sh.text(f"({sb['rows']} ROW(S) INSIDE THE MAIN BARS" + (f", {sb['pieces']} PIECES / ROW LAPPED 60d)" if sb['pieces'] > 1 else ")"), tx, ty - 380, 200, 'S-RFT-TXT')
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.14)
            if sb['mk_ch']: sh.ctext(sb['mk_ch'], callout(sb['chairs'], 16, sb['mk_ch'], sb['chair_L'], 1000, 'CH'), tx, ty, ST['call'], 'S-RFT-TXT')
    # ---- SECTION along X (bars along X = lines, bars along Y = dots) ----
    ks = min(k, 9800 / (f['L'] + 200), 7500 / (f['h'] + 900))       # room for the call-outs before the title block
    sx, sy = 18200 + 100 * ks, R2 + 1700
    if strip: ks = min(ks, 2300 / (f['h'] + 900), 14000 / (f['L'] + 200)); sx, sy = 3800, 2600
    Q = lambda x, y: (sx + x * ks, sy + y * ks)
    L, h, c = f['L'], f['h'], COVER
    sh.pline([Q(-100, -100), Q(L + 100, -100), Q(L + 100, 0), Q(-100, 0)], 'S-GB-CONC', 0, True)          # PC
    sh.pline([Q(0, 0), Q(L, 0), Q(L, h), Q(0, h)], 'S-GB-CONC', 0, True)
    ccs = f.get('cols') or ([f['col']] if f.get('col') else [])
    for c_ in ccs: sh.hatch_rect(*Q(c_[0], h), *Q(c_[2], h + 700))                                     # columns / necks
    cx0, cx1 = (ccs[0][0], ccs[0][2]) if ccs else (L / 2, L / 2)
    def dots(y, d, s_, layer, xa, xb):          # cut bars between xa and xb; the end bars sit in the bends of the U
        n_ = max(1, round((xb - xa) / s_))
        for j in range(n_ + 1):
            x = xa + (xb - xa) * j / n_
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': layer}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(d / 2 * ks, 18), 0, 360)
    def dot2(xa, xb, s_):                                # second cut bar from the right end (clear of the bend)
        n_ = max(1, round((xb - xa) / s_)); return xb - (xb - xa) / n_
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
        lines.append((yX, BX['mk'], cot(BX), dot2(xl + (BX['d'] + BY['d']) / 2, xr - (BX['d'] + BY['d']) / 2, BY['s']) - BY['s'] * 1.5))   # on the line, between two dots
        lines.append((yY, BY['mk'], cot(BY), dot2(xl + (BX['d'] + BY['d']) / 2, xr - (BX['d'] + BY['d']) / 2, BY['s'])))   # a cut dot clear of the bend
    if tx_:
        bot_of_leg = c + (dB if bx_ else 0) + 15
        ins = (BX['d'] + 2) if bx_ else 0                # top U sits inside the bottom U legs, side bars inside both
        xl, xr = c + ins + TX['d'] / 2, L - c - ins - TX['d'] / 2
        sh.pline([Q(xl, bot_of_leg), Q(xl, tX), Q(xr, tX), Q(xr, bot_of_leg)], 'S-RFT-TOP', max(TX['d'] * ks, 20), r=3 * TX['d'] * ks)
        dots(tY, TY['d'], TY['s'], 'S-RFT-TOP', xl + (TX['d'] + TY['d']) / 2, xr - (TX['d'] + TY['d']) / 2)
        lines.append((tX, TX['mk'], cot(TX), dot2(xl + (TX['d'] + TY['d']) / 2, xr - (TX['d'] + TY['d']) / 2, TY['s']) - TY['s'] * 1.5))
        lines.append((tY, TY['mk'], cot(TY), dot2(xl + (TX['d'] + TY['d']) / 2, xr - (TX['d'] + TY['d']) / 2, TY['s'])))
    # side bars (rows) on both faces
    y0, y1 = (yY + 60) if bx_ else c + 60, (tY - 60) if tx_ else h - c - 60
    for i in range(side['rows']):
        y = y0 + (i + 1) * (y1 - y0) / (side['rows'] + 1)
        for x in (xs_, L - xs_):
            hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), max(6 * ks, 18), 0, 360)
        if i == 0: lines.append((y, side['mk'], callout(side['rows'] * side['pieces'], side['ds'], side['mk'], side['L'], layer='SB'), L - xs_))
    # chair (only with a top mesh): stands on the bottom mesh, carries the top mesh; every side dimensioned
    if bx_ and tx_ and sb['mk_ch']:
        yb_, yt_ = c + dB + 8, h - c - dT - 8
        xc = L * 0.30
        cp = [(xc - 500, yb_), (xc - 200, yb_), (xc - 200, yt_), (xc + 200, yt_), (xc + 200, yb_), (xc + 500, yb_)]
        sh.pline([Q(*p) for p in cp], 'S-RFT-STIR', max(16 * ks, 15), r=3 * 16 * ks)
        hd = min(ST['len'], 150)
        sh.text(str(sb['ch_foot']), Q(xc - 350, 0)[0], Q(0, yb_)[1] + 60, hd, 'S-DIM', align=TA.BOTTOM_CENTER)
        sh.text(str(sb['ch_foot']), Q(xc + 350, 0)[0], Q(0, yb_)[1] + 60, hd, 'S-DIM', align=TA.BOTTOM_CENTER)
        sh.text(str(sb['ch_top']), Q(xc, 0)[0], Q(0, yt_)[1] - 60, hd, 'S-DIM', align=TA.TOP_CENTER)
        sh.text(str(sb['ch_h']), Q(xc - 200, 0)[0] - 60, Q(0, (yb_ + yt_) / 2)[1], hd, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        lines.append(((yb_ + yt_) / 2, sb['mk_ch'], callout(sb['chairs'], 16, sb['mk_ch'], sb['chair_L'], 1000, 'CH'), xc + 200))
    # call-outs with leaders to the right
    yt = sorted(lines)
    for i, (y, mk_, t, xt) in enumerate(yt):                 # each leader ends ON its bar (line or cut dot)
        ty_ = Q(0, 0)[1] + i * 560 - 100
        sh.line(Q(xt, y), (Q(L + 100, 0)[0] + 350, ty_ + 90), 'S-RFT-TXT')
        sh.circle(*Q(xt, y), 25, 'S-RFT-TXT')
        sh.ctext(mk_, t, Q(L + 100, 0)[0] + 450, ty_, ST['call'], maxw=33600 - Q(L + 100, 0)[0] - 450)
    sh.dim(Q(0, -100), Q(L, -100), (Q(0, 0)[0], Q(0, -100)[1] - 400), text=str(L))
    sh.dim(Q(0, 0), Q(0, h), (Q(0, 0)[0] - 450, Q(0, 0)[1]), angle=90, text=str(h))
    sh.dim(Q(-100, -100), Q(-100, 0), (Q(-100, 0)[0] - 250, Q(0, -100)[1]), angle=90, text='100')
    sh.text(f'COVER {c}', Q(L / 2, 0)[0], Q(0, c / 2)[1], 150, 'S-DIM', align=TA.MIDDLE_CENTER)
    lev = PRJ.get('levels', {})
    if 'founding' in lev:
        fl = lev['founding']; tpc = fl + 0.10; tof = tpc + h / 1000
        marks_ = [(-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {tpc:+.2f}"), (h, f"T.O.F {tof:+.2f}")]
        if 'top_gb' in lev and not strip:
            neck = lev['top_gb'] - tof
            sh.text(f"NECK UP TO T.O.GB {lev['top_gb']:+.2f}", Q(cx1, 0)[0] + 300, Q(0, h + 560)[1], 170, 'S-DIM')
            sh.text(f"NECK H = {mm(neck * 1000)}", Q(cx1, 0)[0] + 300, Q(0, h + 300)[1], 170, 'S-DIM')
            for c_ in ccs: sh.break_line(Q(c_[0] - 150, h + 700), Q(c_[2] + 150, h + 700))     # break line on each neck
        for yy, lab in marks_:
            sh.line(Q(-1300, yy), Q(-150, yy), 'S-DIM')
            sh.text(lab, Q(-1300, yy)[0], Q(0, yy)[1] + 50, 150, 'S-DIM', align=TA.BOTTOM_RIGHT)
    sh.text(f"SECTION 1-1  ({f['name']}, {f['h']}, PC 100)", Q(L / 2, 0)[0], Q(0, -100)[1] - 900, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    if f.get('adds'): draw_adds(doc, idx + 1, f, meta)
    return bars


def draw_adds(doc, idx, f, meta):
    """Additional bars written on the consultant's plan (ADD BOT / ADD TOP), Roya raft style: own panels on a sheet."""
    m2 = dict(meta); m2['dwg'] = meta['dwg'] + '-ADD'; m2['title'] = meta['title'].split('\n')[0] + f"\nADDITIONAL RFT - {f['name']}"
    sh = Sheet(doc, 0, -idx * 32000, m2)
    draw_legend(sh, 21000, 27900)
    sh.text(f"{f['name']}  ADDITIONAL REINFORCEMENT", 2000, 27900, ST['name'], 'S-AXIS-TXT')
    k = min(4.0, 14000 / f['W'], 14500 / f['L'])
    for kind, title, ox, oy in (('B', 'ADDITIONAL BOTTOM REINFORCEMENT (ADD BOT)', 2000, 9000), ('T', 'ADDITIONAL TOP REINFORCEMENT (ADD TOP)', 18200, 9000)):
        P = lambda x, y: (ox + x * k, oy + y * k)
        W_ = f['L'] * k
        sh.pline([P(0, 0), P(f['L'], 0), P(f['L'], f['W']), P(0, f['W'])], 'S-GB-CONC', 0, True)
        for c_ in f.get('cols') or []: sh.hatch_rect(*P(c_[0], c_[1]), *P(c_[2], c_[3]))
        sh.dim(P(0, 0), P(f['L'], 0), (ox, oy - 450), text=str(f['L']))
        sh.dim(P(0, 0), P(0, f['W']), (ox - 450, oy), angle=90, text=str(f['W']))
        if len(title) * ST['panel'] * 0.9 > W_: sh.text(title, ox, oy - 900, ST['panel'], 'S-SEC', align=TA.TOP_LEFT)
        else: sh.text(title, ox + W_ / 2, oy - 900, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
        lst = [a for a in f['adds'] if a['layer'] == kind]
        if not lst: sh.text('- NONE -', ox + W_ / 2, oy + f['W'] * k / 2, ST['call'], 'S-SEC', align=TA.MIDDLE_CENTER)
        for i, a in enumerate(lst):
            hl = a['L'] / 2
            p0, p1 = ((a['x'] - hl, a['y']), (a['x'] + hl, a['y'])) if a['along'] == 'X' else ((a['x'], a['y'] - hl), (a['x'], a['y'] + hl))
            cl_ = lambda p: (min(max(p[0], COVER), f['L'] - COVER), min(max(p[1], COVER), f['W'] - COVER))
            p0, p1 = cl_(p0), cl_(p1)
            sh.pline([P(*p0), P(*p1)], 'S-RFT-TOP' if kind == 'T' else 'S-RFT-BOT', 40)
            # zone of the bars: dashed distribution line across the bar, mark on the bar, call-out listed under the panel
            mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
            hz = a['n'] * a['s'] / 2
            q0, q1 = ((mid[0], mid[1] - hz), (mid[0], mid[1] + hz)) if a['along'] == 'X' else ((mid[0] - hz, mid[1]), (mid[0] + hz, mid[1]))
            sh.line(P(*cl_(q0)), P(*cl_(q1)), 'S-DIM')
            sh.text(mm(a['L']), P(*mid)[0] + 60, P(*mid)[1] + 60, ST['len'], 'S-DIM', rot=0 if a['along'] == 'X' else 90)
            ty_ = oy - 2100 - i * 560
            sh.line(P(*mid), (ox + 350, ty_ + 90), 'S-RFT-TXT'); sh.circle(*P(*mid), 25, 'S-RFT-TXT')
            sh.ctext(a['mk'], callout(a['n'], a['d'], a['mk'], a['L'], a['s'], 'ADD-' + kind) + (f"  ({a['along']})"), ox + 450, ty_, ST['call'])
    sh.text('ADDITIONAL BARS AS WRITTEN ON THE CONSULTANT PLAN (LENGTH L, ZONE = LENGTH OF THE CROSSING BARS); STRAIGHT BARS.',
            2000, 1200, ST['note'], 'S-RFT-TXT', maxw=30000)


if __name__ == '__main__':
    lib = json.load(open('footings.json'))
    import os
    if os.path.exists('mats.json'): lib.update(json.load(open('mats.json')))     # combined footings / rafts
    names = sys.argv[1:] or list(lib)
    if names and names[0] == '@mats': names = list(json.load(open('mats.json')))
    doc = new_doc()
    bl = BarList()
    idx = 0
    for i, n in enumerate(names):
        f = lib[n]
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = project_notes('COVER FOOTINGS 70; PLAIN CONCRETE 100 UNDER FOOTINGS.', 'SIDE BARS INSIDE THE MAIN U-BARS; CH = CHAIRS (ONLY WITH A TOP MESH).')
        kind_ = 'RAFT' if n.startswith('RAFT') else 'COMBINED FOOTING' if n.startswith('CF') else 'FOUNDATION'
        meta['title'] = f"STRUCTURAL {kind_}\nREINFORCEMENT - {n}  (NO={f['no']})"
        meta['dwg'] = f"{meta['prefix'].replace('GB', 'FDN')}-{n}"
        draw_sheet(doc, idx, f, meta, bl)
        idx += 2 if f.get('adds') else 1
    meta['title'] = 'STRUCTURAL FOUNDATION'; meta['dwg'] = meta['prefix'].replace('GB', 'FDN')
    nb = draw_bbs(doc, idx, bl.sorted(), meta)
    doc.saveas('out/FOOTINGS.dxf')
    print('sheets', idx, '+ BBS', nb)
