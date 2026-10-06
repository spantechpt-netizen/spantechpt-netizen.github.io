"""Grade-beam shop drawings, one set of A3 sheets per grid axis (Roya-style call-outs).
Each sheet: plan strip (top bars above the beam, bottom bars below), longitudinal section, cross sections."""
import math, pickle, sys, json
from gen import SCHED, COVER, STOCK, leg, lap, new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, hooked_tie, tie_bar_centres, ST, mm, project_notes
LEV = json.load(open('project.json')).get('levels', {})

WIN = 29500          # beam length per sheet at 1:100
X0 = 1800            # sheet x of window start
Y_PLAN, Y_ELEV, Y_SEC = 22000, 13200, 2600
AX = json.load(open('axes.json'))


def axis_items(axis, runs, cols, tol=300):
    hor = axis[0] == 'X'
    c0 = AX[axis]
    rs = [r for r in runs if r['hor'] == hor and abs(r['c'] - c0) <= tol]
    rs.sort(key=lambda r: r['lo'])
    # groups: consecutive runs closer than 1500 (a column / crossing beam between them)
    groups = []
    for r in rs:
        if groups and r['lo'] - groups[-1]['hi'] <= 1500 and abs(r['c'] - groups[-1]['c']) <= 200:
            groups[-1]['runs'].append(r); groups[-1]['hi'] = max(groups[-1]['hi'], r['hi'])
        else:
            groups.append(dict(c=r['c'], lo=r['lo'], hi=r['hi'], runs=[r]))
    # supports along the axis band
    sup = []
    for c in cols:
        lo, hi, a, b = (c[0], c[2], c[1], c[3]) if hor else (c[1], c[3], c[0], c[2])
        if a - 30 <= c0 + 0 and b + 30 >= c0 - 0 or any(a - 30 <= g['c'] <= b + 30 for g in groups):
            sup.append([lo, hi, 'C'])
    for o in runs:
        if o['hor'] == hor: continue
        if o['lo'] - 1000 <= c0 <= o['hi'] + 1000:
            sup.append([o['c'] - o['w'] / 2, o['c'] + o['w'] / 2, o['lab'] or 'GB'])
    sup.sort()
    merged = []
    for s in sup:
        if merged and s[0] <= merged[-1][1] + 5:
            merged[-1][1] = max(merged[-1][1], s[1])
        else:
            merged.append(list(s))
    lo = min(g['lo'] for g in groups); hi = max(g['hi'] for g in groups)
    merged = [s for s in merged if any(s[1] >= g['lo'] - 1200 and s[0] <= g['hi'] + 1200 for g in groups)]
    return hor, c0, groups, merged


def detail(groups, sup):
    """Bars and stirrups in axis coordinates."""
    bars, stirs, secs = [], [], []
    def anchor(pos, side):
        best = None
        for a, b, t in sup:
            if side < 0 and a - 5 <= pos <= b + 1000 and a <= pos + 5:   # support at / before the start
                if b >= pos - 1000: best = a + COVER if best is None else min(best, a + COVER)
            if side > 0 and a - 1000 <= pos <= b + 5 and b >= pos - 5:
                best = b - COVER if best is None else max(best, b - COVER)
        return best if best is not None else pos - side * COVER
    for gi, g in enumerate(groups):
        segs = []
        for r in sorted(g['runs'], key=lambda r: r['lo']):
            t = r['lab'] or 'GB1'
            if segs and segs[-1]['t'] == t:
                segs[-1]['b'] = r['hi']
            else:
                segs.append(dict(t=t, a=r['lo'], b=r['hi'], w=r['w']))
        g['segs'] = segs
        for si, s in enumerate(segs):
            p = SCHED[s['t']]
            secs.append(dict(u=s['a'] + 300, t=s['t'], g=gi))
            ea = anchor(s['a'], -1) if si == 0 else s['a'] - 0      # type change inside a group: anchor into the support between
            eb = anchor(s['b'], +1) if si == len(segs) - 1 else s['b']
            if si > 0: ea = anchor(s['a'], -1)
            if si < len(segs) - 1: eb = anchor(s['b'], +1)
            inner = [x for x in sup if x[0] >= ea - 5 and x[1] <= eb + 5]
            # clear spans = the beam length between support faces (no stirrups inside a column / crossing beam)
            spans, x = [], s['a']
            for a_, b_, _t in sorted(sup):
                if b_ <= x or a_ >= s['b']: continue
                if a_ - x > 300: spans.append((x, a_))
                x = max(x, b_)
            if s['b'] - x > 300: spans.append((x, s['b']))
            def top_ok(x):   # top bars: lap in the middle third of a span
                return any(a + (b - a) / 3 <= x <= b - (b - a) / 3 for a, b in spans)
            def bot_ok(x):   # bottom bars: lap at supports (within L/4 of a support face)
                return any(a - 50 <= x <= b + 50 for a, b, _ in inner) or any(abs(x - a) < (b - a) / 4 or abs(x - b) < (b - a) / 4 for a, b in spans)
            for pos, n, d, ok in (('T', p['nt'], p['dt'], top_ok), ('B', p['nb'], p['db'], bot_ok)):
                lg, lp = leg(d), lap(d)
                total = eb - ea + 2 * lg
                nbar = 1 if total <= STOCK else math.ceil((total - lp) / (STOCK - lp))
                target = min(STOCK, (total + (nbar - 1) * lp) / nbar + 300) if nbar > 1 else STOCK
                x, k = ea, 0
                while True:
                    first = k == 0
                    rem = eb - x + (lg if first else 0) + lg
                    if rem <= STOCK:
                        bars.append(dict(pos=pos, n=n, d=d, x0=x, x1=eb, legL=first, legR=True, row=k % 2)); break
                    e = x + target - (lg if first else 0)
                    e = min(e, x + STOCK - (lg if first else 0))
                    lo_lim = x + max(4000, target - 3000)
                    e0 = e
                    while e > lo_lim and not (ok(e) and ok(e - lp)): e -= 50
                    if e <= lo_lim:
                        e = e0
                        while e < x + STOCK - (lg if first else 0) and not (ok(e) and ok(e - lp)): e += 50
                    e = round(e / 10) * 10
                    bars.append(dict(pos=pos, n=n, d=d, x0=x, x1=e, legL=first, legR=False, row=k % 2))
                    x, k = e - lp, k + 1
            c = 30 if p['b'] <= 300 else 40
            ls = 2 * (p['b'] - 2 * c + p['h'] - 80) + 200
            for a, b in spans:
                n = math.floor((b - a - 100) / p['s']) + 1
                stirs.append(dict(a=a, b=b, n=n, d=p['ds'], L=ls, s=p['s'], t=s['t']))
    for pos in 'TB':
        last_end = {0: -1e18, 1: -1e18}
        for b in sorted([b for b in bars if b['pos'] == pos], key=lambda b: b['x0']):
            b['row'] = 0 if b['x0'] > last_end[0] + 2500 else 1 if b['x0'] > last_end[1] + 2500 else 0
            last_end[b['row']] = b['x1']
    for b in bars:
        b['L'] = round(b['x1'] - b['x0'] + (leg(b['d']) if b['legL'] else 0) + (leg(b['d']) if b['legR'] else 0))
    return bars, stirs, secs


def windows(groups, sup):
    lo = min(g['lo'] for g in groups) - 1000; hi = max(g['hi'] for g in groups) + 1000
    cuts, x = [], lo
    while hi - x > WIN:
        lim = x + WIN
        cand = [g['lo'] - 500 for g in groups if x + 3000 < g['lo'] - 500 <= lim]          # cut in a gap
        cand += [(a + b) / 2 for a, b, t in sup if x + 3000 < (a + b) / 2 <= lim]           # or at a support
        nx = max(cand) if cand else lim
        cuts.append((x, nx)); x = nx
    cuts.append((x, hi))
    return cuts


def draw_axis(doc, axis, runs, cols, meta0, start_sheet=1):
    hor, c0, groups, sup = axis_items(axis, runs, cols)
    if not groups: return []
    bars, stirs, secs = detail(groups, sup)
    bl = BarList()
    for b in bars:
        lg = leg(b['d'])
        shape = ('U' if b['legL'] and b['legR'] else 'L', lg if b['legL'] else 0, round(b['x1'] - b['x0']), lg if b['legR'] else 0)
        b['mk'] = bl.add(b['d'], shape, b['L'], b['n'], 1, b['pos'])
    for g in groups:
        for sg in g['segs']:
            ss = [s for s in stirs if sg['a'] - 1500 <= s['a'] and s['b'] <= sg['b'] + 1500 and s['t'] == sg['t']]
            for s in ss:
                p = SCHED[s['t']]; c = 30 if p['b'] <= 300 else 40
                s['mk'] = bl.add(s['d'], ('ST', p['b'] - 2 * c, p['h'] - 80), s['L'], s['n'], 1)
    out = []
    wins = windows(groups, sup)
    perp = {k: v for k, v in AX.items() if (k[0] == 'Y') == hor}
    sec_no = 0
    for wi, (w0, w1) in enumerate(wins):
        U = lambda u: X0 + (u - w0)
        meta = dict(meta0)
        meta['title'] = f'GRADE BEAMS REINFORCEMENT\nAXIS {axis}  ({wi + 1}/{len(wins)})'
        meta['dwg'] = f'{meta0["prefix"]}-{axis}-{wi + 1:02d}'
        sh = Sheet(doc, 0, -(start_sheet - 1 + len(out)) * 32000, meta)
        out.append(meta['dwg'])
        vis = lambda a, b: b > w0 and a < w1
        sh.text(f'AXIS {axis}', 1800, 27900, ST['name'], 'S-AXIS-TXT')
        sh.text(f'GRADE BEAMS ON AXIS {axis} - PLAN  1:100', 1800, 27200, ST['sub'], 'S-SEC')
        # perpendicular grid lines + bubbles
        for k, v in perp.items():
            if w0 - 200 <= v <= w1 + 200:
                x = U(v)
                # grid lines broken where bars, call-outs and dimensions are written (no text on lines)
                for y0_, y1_ in ((Y_PLAN + 3150, Y_PLAN + 3450), (Y_PLAN - 700, Y_PLAN + 700), (Y_PLAN - 3800, Y_PLAN - 3550),
                                 (Y_ELEV + 1100, Y_ELEV + 1650), (Y_ELEV - 1000, Y_ELEV + 250)):
                    sh.line((x, y0_), (x, y1_), 'S-AXIS')
                sh.circle(x, Y_PLAN + 3900, 450, 'S-AXIS')
                sh.text(k, x, Y_PLAN + 3900, 380, 'S-AXIS-TXT', align=TA.MIDDLE_CENTER)
                sh.circle(x, Y_ELEV + 2100, 450, 'S-AXIS')
                sh.text(k, x, Y_ELEV + 2100, 380, 'S-AXIS-TXT', align=TA.MIDDLE_CENTER)
        # beams + supports on plan
        for g in groups:
            for r in g['runs']:
                if not vis(r['lo'], r['hi']): continue
                a, b = max(r['lo'], w0), min(r['hi'], w1)
                for sgn in (-1, 1):
                    sh.line((U(a), Y_PLAN + sgn * r['w'] / 2), (U(b), Y_PLAN + sgn * r['w'] / 2), 'S-GB-CONC')
                sh.text(r['lab'] or 'GB?', U((a + b) / 2), Y_PLAN - r['w'] / 2 - 120, 200, 'S-GB-CONC', align=TA.TOP_CENTER)
        for a, b, t in sup:
            if vis(a, b):
                sh.hatch_rect(U(max(a, w0)), Y_PLAN - 400, U(min(b, w1)), Y_PLAN + 400)
        # bars on plan: bars drawn first, then every text is placed in a free spot (no text on lines / other text)
        occ = []
        def hit(bx):
            return any(bx[0] < o[2] and o[0] < bx[2] and bx[1] < o[3] and o[1] < bx[3] for o in occ)
        def tw(t, h): return len(t) * h * 0.9
        def put(cands):
            for bx in cands:
                if not hit(bx): occ.append(bx); return bx
            occ.append(cands[0]); return cands[0]
        ROW = lambda pos, row: Y_PLAN + (1 if pos == 'T' else -1) * (1300 + 1100 * row)
        for k_, v in perp.items():
            if w0 - 200 <= v <= w1 + 200:
                occ += [(U(v) - 30, Y_PLAN - 700, U(v) + 30, Y_PLAN + 700), (U(v) - 500, Y_PLAN + 3150, U(v) + 500, Y_PLAN + 4400),
                        (U(v) - 30, Y_PLAN - 3800, U(v) + 30, Y_PLAN - 3550)]
        for g in groups:
            for r_ in g['runs']:
                if vis(r_['lo'], r_['hi']):
                    a_, b_ = U(max(r_['lo'], w0)), U(min(r_['hi'], w1))
                    occ.append((a_, Y_PLAN - 420, b_, Y_PLAN + 420))
                    occ.append((U((max(r_['lo'], w0) + min(r_['hi'], w1)) / 2) - 400, Y_PLAN - r_['w'] / 2 - 400, U((max(r_['lo'], w0) + min(r_['hi'], w1)) / 2) + 400, Y_PLAN - r_['w'] / 2))
        drawn = []
        for b in bars:
            if not vis(b['x0'], b['x1']): continue
            if min(b['x1'], w1) - max(b['x0'], w0) < 1500 and (b['x0'] < w0 or b['x1'] > w1): continue   # tiny continuation stub
            off = 1 if b['pos'] == 'T' else -1
            base = ROW(b['pos'], b['row'])
            lg = leg(b['d'])
            a, c = max(b['x0'], w0), min(b['x1'], w1)
            pts = []
            if b['legL'] and b['x0'] >= w0: pts.append((U(a), base - off * lg))
            pts += [(U(a), base), (U(c), base)]
            if b['legR'] and b['x1'] <= w1: pts.append((U(c), base - off * lg))
            sh.pline(pts, 'S-RFT-TOP' if b['pos'] == 'T' else 'S-RFT-BOT', 40, r=150)
            occ.append((U(a) - 40, min(base, base - off * lg) - 40, U(c) + 40, max(base, base - off * lg) + 40))
            drawn.append((b, a, c, base, off, lg))
        hC, hL = ST['call'], ST['len']
        for b, a, c, base, off, lg in drawn:
            m = b['mk']
            if b['legL'] and b['x0'] >= w0:
                x_ = U(a) - 160; ym_ = base - off * lg / 2; occ.append((x_ - hL, ym_ - 350, x_, ym_ + 350))
                sh.text(mm(lg), x_, base - off * lg / 2, hL, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
            if b['legR'] and b['x1'] <= w1:
                x_ = U(c) + 380; ym_ = base - off * lg / 2; occ.append((x_ - hL, ym_ - 350, x_, ym_ + 350))
                sh.text(mm(lg), x_, base - off * lg / 2, hL, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        for pos in 'TB':
            rows = sorted([b for b in bars if b['pos'] == pos], key=lambda b: b['x0'])
            for a, b in zip(rows, rows[1:]):
                # a real lap only: same bar size and overlap = 60 d (bars of two beams anchored in one column are not laps)
                if b['x0'] < a['x1'] and w0 <= b['x0'] and a['x1'] <= w1 and a['d'] == b['d'] and abs((a['x1'] - b['x0']) - lap(a['d'])) < 60:
                    off = 1 if pos == 'T' else -1
                    lo, hi = sorted((ROW(pos, 0), ROW(pos, 1)))
                    x0_, x1_ = U(b['x0']), U(a['x1'])
                    cands = [(x0_ - 100, y - 150, x1_ + 100, y + 300) for y in ((lo + hi) / 2 - 150, (lo + hi) / 2 - 50, (lo + hi) / 2 + 50, (lo + hi) / 2 - 250, (lo + hi) / 2 + 150, (lo + hi) / 2 - 450,
                                                                           hi + 700 if pos == 'T' else lo - 1000)]
                    bx = put(cands)
                    sh.dim((x0_, bx[1] + 210), (x1_, bx[1] + 210), (x0_, bx[1] + 210), text=str(round(a['x1'] - b['x0'])))
        for b, a, c, base, off, lg in drawn:
            m = b['mk']; t = callout(b['n'], b['d'], m, b['L'], layer=b['pos'])
            W_ = tw(t, hC) + 2.6 * hC
            xs = [U(a) + 300 + k * 350 for k in range(60) if U(a) + 300 + k * 350 + W_ <= max(U(c), U(a) + 300 + W_)]
            # short bars: the call-out may also start left of the bar (a leader then points to the bar)
            xs_out = [U(a) + 300 - k * 350 for k in range(1, int(W_ / 350) + 1)]
            # call-out on the outer side of the bar (above top bars, below bottom bars), lengths on the inner side
            yc = (lambda dy: base + 80 + dy) if off > 0 else (lambda dy: base - 80 - hC * 1.9 - dy)     # box holds the hexagon
            bx = put([(x, yc(dy), x + W_, yc(dy) + hC * 1.9) for dy, xx in ((0, xs), (450, xs), (0, xs_out), (450, xs_out), (900, xs), (900, xs_out))
                      for x in xx])          # prefer right over the bar; beside it only when there is no room
            sh.ctext(m, t, bx[0], bx[1] + hC * 0.3, hC)
            xh = bx[0] + 1.1 * hC                                     # leader from the hexagon to the nearest point of the bar
            if abs((bx[1] if off > 0 else bx[3]) - base) > 300 or not (U(a) <= xh <= U(c)):
                xb_ = min(max(xh, U(a) + 100), U(c) - 100)
                sh.line((xh, bx[1] if off > 0 else bx[3]), (xb_, base + off * 40), 'S-RFT-TXT')
            lt = mm(b['x1'] - b['x0']); Wl = tw(lt, hL); cx = U((a + c) / 2)
            yl0 = base - 100 - hL if off > 0 else base + 100                # inner side band
            cands = [(cx + dx - Wl / 2, yl0 - off * dy, cx + dx + Wl / 2, yl0 - off * dy + hL) for dy in (0, 300)
                     for dx in (0, 600, -600, 1200, -1200, 1800, -1800, 300, -300)
                     if U(a) - 200 <= cx + dx - Wl / 2 and cx + dx + Wl / 2 <= U(c) + 200] or [(cx - Wl / 2, yl0, cx + Wl / 2, yl0 + hL)]
            bx = put(cands)
            sh.text(lt, (bx[0] + bx[2]) / 2, bx[1], hL, 'S-DIM', align=TA.BOTTOM_CENTER)
            if b['x0'] < w0:
                bx = put([(U(a) + 100, yl0, U(a) + 100 + tw('CONT.', 180), yl0 + 180)])
                sh.text('CONT.', bx[0], bx[1], 180, 'S-DIM', align=TA.BOTTOM_LEFT)
            if b['x1'] > w1:
                bx = put([(U(c) - 100 - tw('CONT.', 180), yl0, U(c) - 100, yl0 + 180)])
                sh.text('CONT.', bx[2], bx[1], 180, 'S-DIM', align=TA.BOTTOM_RIGHT)
        # ---- elevation ----
        sh.text(f'LONGITUDINAL SECTION - AXIS {axis}  1:100', 1800, Y_ELEV + 3000, ST['sub'], 'S-SEC')
        hmax = 700
        for g in groups:
            for s in g['segs']:
                if not vis(s['a'], s['b']): continue
                p = SCHED[s['t']]; a, b = max(s['a'], w0), min(s['b'], w1)
                sh.pline([(U(a), Y_ELEV), (U(b), Y_ELEV), (U(b), Y_ELEV - p['h']), (U(a), Y_ELEV - p['h'])], 'S-GB-CONC', closed=True)
        for a, b, t in sup:
            if vis(a, b):
                sh.hatch_rect(U(max(a, w0)), Y_ELEV - hmax - 400, U(min(b, w1)), Y_ELEV)
        for b in bars:
            if not vis(b['x0'], b['x1']): continue
            p = SCHED['GB1']
            for g in groups:
                for s in g['segs']:
                    if s['a'] - 1500 <= b['x0'] <= s['b']: p = SCHED[s['t']]
            dy = -1 if b['pos'] == 'T' else 1
            y = Y_ELEV - COVER - 20 - 25 * b['row'] if b['pos'] == 'T' else Y_ELEV - p['h'] + COVER + 20 + 25 * b['row']
            lg = min(leg(b['d']), p['h'] - 150)
            a, c = max(b['x0'], w0), min(b['x1'], w1)
            pts = []
            if b['legL'] and b['x0'] >= w0: pts.append((U(a), y + dy * lg))
            pts += [(U(a), y), (U(c), y)]
            if b['legR'] and b['x1'] <= w1: pts.append((U(c), y + dy * lg))
            sh.pline(pts, 'S-RFT-TOP' if b['pos'] == 'T' else 'S-RFT-BOT', 25, r=60)
        for s in stirs:
            if not vis(s['a'], s['b']): continue
            p = SCHED[s['t']]
            x = s['a'] + 50
            while x <= s['b'] - 50:
                if w0 <= x <= w1: sh.line((U(x), Y_ELEV - COVER), (U(x), Y_ELEV - p['h'] + COVER), 'S-RFT-STIR')
                x += s['s']
            a, b = max(s['a'], w0), min(s['b'], w1)
            sh.dim((U(a), Y_ELEV), (U(b), Y_ELEV), (U(a), Y_ELEV + 600), text=f"{round(s['b'] - s['a'])}")

        if any(vis(a, b) for a, b, t in sup):
            sh.text('COLUMN TIES CONTINUE THROUGH THE JOINT - GB STIRRUPS STOP AT THE COLUMN FACE', 1800, Y_ELEV - hmax - 1900, 200, 'S-RFT-TXT')
        # one stirrup call-out per beam type segment (count summed over its spans)
        for g in groups:
            for sg in g['segs']:
                ss = [s for s in stirs if sg['a'] - 1500 <= s['a'] and s['b'] <= sg['b'] + 1500 and s['t'] == sg['t'] and vis(s['a'], s['b'])]
                if not ss: continue
                n = sum(s['n'] for s in ss if w0 <= (s['a'] + s['b']) / 2 <= w1)
                if not n: continue
                a = max(sg['a'], w0)
                sh.ctext(ss[0]['mk'], callout(n, ss[0]['d'], ss[0]['mk'], ss[0]['L'], ss[0]['s']), U(a) + 900, Y_ELEV - hmax - 1100, ST['call'])
        # ---- cross sections ----
        sh.text('CROSS SECTIONS  1:20', 1800, Y_SEC + 4900, ST['sub'], 'S-SEC')
        sx = 2600
        for sc in secs:
            if not (w0 <= sc['u'] <= w1): continue
            sec_no += 1
            p = SCHED[sc['t']]; f = 5
            x = U(sc['u'])
            sh.line((x, Y_ELEV + 900), (x, Y_ELEV - hmax - 500), 'S-SEC')
            sh.circle(x, Y_ELEV - hmax - 900, 330, 'S-SEC')
            sh.text(str(sec_no), x, Y_ELEV - hmax - 900, 300, 'S-SEC', align=TA.MIDDLE_CENTER)
            bx, by = sx, Y_SEC
            W_, H_ = p['b'] * f, p['h'] * f
            c = 30 if p['b'] <= 300 else 40          # side cover (Roya: 200 wide -> stirrup 140)
            ct = COVER                                # top / bottom cover
            ds = p['ds']
            Q = lambda x, y: (bx + x * f, by + y * f)
            sh.pline([Q(0, 0), Q(p['b'], 0), Q(p['b'], p['h']), Q(0, p['h'])], 'S-GB-CONC', 0, True)
            # stirrup: outer face at the cover, drawn on its centre line
            x0s, x1s, y0s, y1s = c + ds / 2, p['b'] - c - ds / 2, ct + ds / 2, p['h'] - ct - ds / 2
            # stirrup on its centre line, curved at every bend; 135-degree hooks wrap the top-left bar, 100 mm tails
            dm = max(p['dt'], p['db'])
            cbars = [(x0s + ds / 2 + dm / 2, y0s + ds / 2 + dm / 2), (x1s - ds / 2 - dm / 2, y0s + ds / 2 + dm / 2),
                     (x1s - ds / 2 - dm / 2, y1s - ds / 2 - dm / 2), (x0s + ds / 2 + dm / 2, y1s - ds / 2 - dm / 2)]
            for seg in hooked_tie([(x0s, y0s), (x1s, y0s), (x1s, y1s), (x0s, y1s)], cbars, tail=100, rc=dm / 2 + ds / 2):
                sh.pline([Q(*q) for q in seg], 'S-RFT-STIR', ds * f)
            for row, n, d in (('T', p['nt'], p['dt']), ('B', p['nb'], p['db'])):
                yy = p['h'] - ct - ds - d / 2 if row == 'T' else ct + ds + d / 2
                xa, xb = c + ds + d / 2, p['b'] - c - ds - d / 2
                for j in range(n):
                    xx = xa + j * (xb - xa) / (n - 1)
                    h = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-TOP' if row == 'T' else 'S-RFT-BOT'})
                    h.paths.add_edge_path().add_arc(sh.P(*Q(xx, yy)), d / 2 * f, 0, 360)
                # leader + call-out
                sh.line(Q(xb, yy), (bx + W_ + 200, Q(0, yy)[1]), 'S-RFT-TXT')
                sh.text(f"{n} T {d} -{row}", bx + W_ + 250, Q(0, yy)[1] - 90, 200)
            sh.dim(Q(0, 0), Q(p['b'], 0), (bx, by - 350), text=str(p['b']))
            sh.dim(Q(0, 0), Q(0, p['h']), (bx - 350, by), angle=90, text=str(p['h']))
            sh.text(str(ct), Q(p['b'] / 2, ct / 2)[0], Q(0, ct / 2)[1], 120, 'S-DIM', align=TA.MIDDLE_CENTER)
            sh.text(str(ct), Q(p['b'] / 2, 0)[0], Q(0, p['h'] - ct / 2)[1], 120, 'S-DIM', align=TA.MIDDLE_CENTER)
            sh.text(str(c), Q(c / 2, 0)[0], Q(0, p['h'] / 2)[1], 120, 'S-DIM', rot=90, align=TA.MIDDLE_CENTER)
            sh.text(f"T{p['ds']} @{p['s']}", bx + W_ + 250, by + H_ / 2, 200)
            # stirrup shape with dims (Roya style)
            sx2 = bx + W_ + 3000                                      # stirrup sketch clear of the call-outs
            a_, b_ = (p['b'] - 2 * c) * f * 0.6, (p['h'] - 80) * f * 0.6
            kk_ = 0.6 * f; sk = [(0, 0), (a_ / kk_, 0), (a_ / kk_, b_ / kk_), (0, b_ / kk_)]
            for seg in hooked_tie(sk, tie_bar_centres(sk, dm / 2 + ds), tail=100, rc=dm / 2 + ds):
                sh.pline([(sx2 + q[0] * kk_, by + 300 + q[1] * kk_) for q in seg], 'S-RFT-STIR', 30)
            sh.text(mm(p['b'] - 2 * c), sx2 + a_ / 2, by + 150, ST['len'], 'S-DIM', align=TA.TOP_CENTER)
            sh.text(mm(p['h'] - 80), sx2 + a_ + 150, by + 300 + b_ / 2, ST['len'], 'S-DIM', rot=90, align=TA.TOP_CENTER)
            sh.text(f"SEC {sec_no}", bx + W_ / 2, by - 700, 300, 'S-SEC', align=TA.TOP_CENTER)
            sh.text(f"{sc['t']} {p['b']}x{p['h']}", bx + W_ / 2, by - 1150, 200, 'S-SEC', align=TA.TOP_CENTER)
            sx += W_ + 3000 + a_ + 1600
        draw_legend(sh, 21000, 27900)
        # levels on the longitudinal section
        if 'top_gb' in LEV:
            tg = LEV['top_gb']
            for yy, nm_, lv in ((Y_ELEV, 'T.O.GB', tg), (Y_ELEV - hmax, 'B.O.GB', tg - hmax / 1000)):
                sh.line((X0 - 1250, yy), (X0 - 300, yy), 'S-DIM')            # name above, value under the level line
                sh.text(nm_, X0 - 1250, yy + 50, 150, 'S-DIM')
                sh.text(f"{lv:+.2f}", X0 - 1250, yy - 50, 150, 'S-DIM', align=TA.TOP_LEFT)
    # BBS of the axis set
    meta = dict(meta0); meta['title'] = f'GRADE BEAMS AXIS {axis}'; meta['dwg'] = f'{meta0["prefix"]}-{axis}'
    nb = draw_bbs(doc, start_sheet - 1 + len(out), bl.sorted(), meta, Sheet)
    out += [f'{meta["dwg"]}-BBS{i + 1:02d}' for i in range(nb)]
    return out


if __name__ == '__main__':
    runs = pickle.load(open('runs.pkl', 'rb')); cols = pickle.load(open('cols.pkl', 'rb'))
    axes = sys.argv[1:] or ['X11']
    meta0 = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                 rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='1:100 / SEC 1:20', prefix='SDW-STR-GB')
    meta0.update(json.load(open('project.json')).get('meta', {}))
    meta0['notes'] = project_notes('COVER GRADE BEAMS 40.', 'GB STIRRUPS STOP AT THE COLUMN FACE; COLUMN TIES CONTINUE THROUGH THE JOINT.')
    for a in axes:
        doc = new_doc()
        names = draw_axis(doc, a, runs, cols, meta0)
        doc.saveas(f'out/GB_AXIS_{a}.dxf')
        print(a, names)
