"""Strip footing detailed on the foundation plan (engineer: "the STRIP FOOTING has only a section - it must be detailed
on plan, its bars interlocked with the footings").

Model (strip_net.strip_runs): every run of the strip = centre line + width B, T / cross junctions already merged so the
through strip is one run. Per run:
  * LONGITUDINAL bars (bottom and top, nl per layer, + 2 side bars SB): one bar line from end to end of the run, THROUGH
    the isolated footings it crosses (they sit on the footing's bottom mesh / under its top mesh); at each end:
      - junction with another strip (corner / stem of a T): carried across to the FAR face - cover;
      - isolated footing / raft: anchored 60 d into it (or to its far face - cover when shallower);
      - free end: stopped at cover, bent down (leg h - 2 c).
    Over 12 m: equal pieces lapped 60 d, every second piece drawn offset so each lap shows.
  * TRANSVERSE U bars (bottom and top, top U = bottom U) @ s on every clear stretch between footings (inside a footing
    the footing mesh governs), first bar 50 from the face; at a T junction the through strip's bars run through.
Output: plan parts at 1:100 (A3) with the bars drawn, the call-outs, the stretch dimensions, + the typical junction
details, the cross section and the BBS with the real quantities (out/STRIP.dxf).
usage: python3 gen_st_plan.py         (after cd_scan.py; project.json -> strip)
"""
import json, math
from shapely.geometry import box, Point, LineString
import gen_cd, strip_net
from gen import new_doc, Sheet, TA, ST, BarList, callout, draw_bbs, draw_legend, project_notes

PRJ = json.load(open('project.json')); SP = PRJ.get('strip', {})
C = PRJ.get('footing_cover', 70)
B, H, d, ds, n_m = SP.get('B', 1550), SP.get('h', 600), SP.get('d', 14), SP.get('ds', 12), SP.get('n_m', 7)
NAME = SP.get('name', 'ST-01')
S = math.floor(1000 / n_m / 5) * 5
LP, LPS, LMAX = 60 * d, 60 * ds, 12000
LG = H - 2 * C                                             # leg of the U / of a bent end
NL = math.ceil((B - 2 * C) / S) + 1                        # longitudinal bars per layer
UL = B - 2 * C + 2 * LG                                    # transverse U length
CT = 200                                                   # call-out text height on the plan (1:100)


def pieces(L, lap):
    if L <= LMAX: return 1, int(math.ceil(L / 10) * 10)
    p = math.ceil((L - lap) / (LMAX - lap))
    return p, int(math.ceil((L + (p - 1) * lap) / p / 10) * 10)


def at(r, t, u=0):
    return (t, r['c'] + u) if r['o'] == 'H' else (r['c'] + u, t)


def band(r, lo, hi, w=None):
    w = w or B
    return box(lo, r['c'] - w / 2, hi, r['c'] + w / 2) if r['o'] == 'H' else box(r['c'] - w / 2, lo, r['c'] + w / 2, hi)


def end_of(r, side, runs, F):
    """What the run meets at its end (side -1 = lo, +1 = hi): dict(kind, ext = bar extension beyond the run end,
    what, leg = bent leg of the end bar, ldir = side of a plan leg (turn) / 0 = leg bent down (free end))."""
    v = r['hi'] if side > 0 else r['lo']
    E = lambda kind, ext, what=None, leg=0, ldir=0: dict(kind=kind, ext=ext, what=what, leg=leg, ldir=ldir)
    for q in runs:
        if q is r: continue
        if q['o'] != r['o'] and abs(q['c'] - (v + side * B / 2)) < 60 and q['lo'] - B - 60 <= r['c'] <= q['hi'] + B + 60:
            return E('node', B - C, q)                       # corner / stem of a T: to the far face of the other strip
        if q['o'] == r['o'] and 25 < abs(q['c'] - r['c']) < B and abs((q['lo'] if side > 0 else q['hi']) - (v + side * B)) < 60:
            return E('node', B - C, q)                       # jog: the strip steps sideways over one width
    ahead = band(r, v, v + side * 450) if side > 0 else band(r, v - 450, v)
    for f in F:                                           # footing on the line ahead (may stop short of it)
        if f['rc'].intersection(ahead).area > 0.3 * ahead.area * 0.5:
            x0, y0, x1, y1 = f['rc'].bounds
            a0, a1 = (x0, x1) if r['o'] == 'H' else (y0, y1)
            gap = max(0, (a0 - v) if side > 0 else (v - a1))
            depth = (a1 - v) if side > 0 else (v - a0)
            return E('ftg', min(gap + LP, depth - C), f)
    sq = band(r, v, v + side * B) if side > 0 else band(r, v - B, v)
    x0, y0, x1, y1 = sq.bounds
    cand = []                                             # turn: the strip turns 90 deg at its end into a footing beside it
    for s_ in (-1, 1):
        if r['o'] == 'H': sb = box(x0, y1, x1, y1 + 1200) if s_ > 0 else box(x0, y0 - 1200, x1, y0)
        else: sb = box(x1, y0, x1 + 1200, y1) if s_ > 0 else box(x0 - 1200, y0, x0, y1)
        for f in F:
            if f['rc'].intersection(sb).area > 0.05 * sb.area:
                fb = f['rc'].bounds
                face = (fb[1] if s_ > 0 else fb[3]) if r['o'] == 'H' else (fb[0] if s_ > 0 else fb[2])
                cand.append((abs(face - (r['c'] + s_ * B / 2)), s_, f))
    if cand:
        gap, s_, f = min(cand, key=lambda c: c[0])
        return E('turn', B - C, f, int(math.ceil((gap + B / 2 - C + LP) / 10) * 10), s_)
    return E('free', -C, None, LG, 0)


def model(els):
    F = [e for e in els if e['kind'] in ('F', 'M')]
    runs = strip_net.strip_runs(els)
    runs.sort(key=lambda r: (-round(r['c'] / 1000) if r['o'] == 'H' else 1e9 + round(r['c'] / 1000), r['lo']))
    for i, r in enumerate(runs):
        r['name'] = f'R{i + 1}'
        r['ends'] = [end_of(r, -1, runs, F), end_of(r, 1, runs, F)]
        r['a'] = r['lo'] - r['ends'][0]['ext']; r['b'] = r['hi'] + r['ends'][1]['ext']        # bar ends (along)
        # clear stretches: the run minus the footings that cover the strip width
        cuts = []
        for f in r['ftg']:
            g = f['rc'].intersection(band(r, r['lo'], r['hi']))
            x0, y0, x1, y1 = g.bounds
            w_ = (y1 - y0) if r['o'] == 'H' else (x1 - x0)
            if w_ >= 0.8 * B: cuts.append(((x0, x1) if r['o'] == 'H' else (y0, y1)) + (f,))
        cuts.sort(key=lambda c: c[0])
        st, t = [], r['lo']
        for a, b, f in cuts:
            if a - t > 200: st.append((t, a))
            t = max(t, b)
        if r['hi'] - t > 200: st.append((t, r['hi']))
        r['stretches'] = st; r['cuts'] = cuts
    return runs, F


def bars_of(r, bl):
    """Bar marks of a run -> list of call-out lines (mark, text) and the drawing data."""
    L = r['b'] - r['a']
    ga, gb = r['ends'][0]['leg'], r['ends'][1]['leg']
    p, Lp = pieces(L + ga + gb, LP)
    out = dict(p=p, Lp=Lp, L=L)
    # piece shapes: bent leg at a free end only
    marks = []
    for i in range(p):
        la = ga if i == 0 else 0; lb = gb if i == p - 1 else 0
        run_ = Lp - la - lb
        shp = ('U', la, run_, lb) if la and lb else ('L', la, run_) if la else ('L', lb, run_) if lb else ('S', Lp)
        marks.append((shp, Lp))
    lines = []
    seen = {}
    for shp, Lp_ in marks: seen[(shp, Lp_)] = seen.get((shp, Lp_), 0) + 1
    for lay in ('B', 'T'):
        for (shp, Lp_), n in seen.items():
            mk = bl.add(d, shp, Lp_, n * NL, 1, f'{lay}-LG')
            lines.append((mk, callout(n * NL, d, mk, Lp_, None, lay) + ('' if p == 1 else f'  ({p} PCS LAP {LP})' if lay == 'B' and (shp, Lp_) == marks[0] else '')))
    ps, Ls = pieces(L, LPS)
    mk = bl.add(ds, ('S', Ls), Ls, 2 * ps, 1, 'SB')
    lines.append((mk, callout(2 * ps, ds, mk, Ls, None, 'SB') + ('' if ps == 1 else f'  LAP {LPS}')))
    out['lines'] = lines
    tr = []
    for a, b in r['stretches']:
        n = max(2, math.ceil((b - a - 100) / S) + 1)
        mk = bl.add(d, ('U', LG, B - 2 * C, LG), UL, 2 * n, 1, 'TR')
        tr.append((a, b, n, mk))
    out['tr'] = tr
    return out


# ------------------------------------------------------------------------------------------------ drawing primitives
class Prims:
    """Everything of the plan in world coordinates; each sheet part draws what falls in its window."""
    def __init__(self): self.items = []
    def pl(self, pts, lay, w=0, lt=None): self.items.append(('pl', [tuple(p) for p in pts], lay, w, lt))
    def tx(self, s, x, y, h, lay, rot=0, align=TA.BOTTOM_LEFT): self.items.append(('tx', s, x, y, h, lay, rot, align))
    def mk(self, m, x, y, h): self.items.append(('mk', m, x, y, h))
    def dim(self, a, b, base, angle, text): self.items.append(('dim', a, b, base, angle, text))
    def draw(self, sh, Q, r, win):
        for it in self.items:
            k = it[0]
            if k == 'pl':
                ls = LineString(it[1]).intersection(win)
                for g in getattr(ls, 'geoms', [ls]):
                    if g.is_empty or g.geom_type != 'LineString': continue
                    e = sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in g.coords], dxfattribs={'layer': it[2], 'const_width': it[3]})
                    if it[4]: e.dxf.linetype = it[4]; e.dxf.ltscale = 120
            elif k == 'tx':
                if r.contains(Point(it[2], it[3])): sh.text(it[1], *Q(it[2], it[3]), it[4], it[5], rot=it[6], align=it[7])
            elif k == 'mk':
                if r.contains(Point(it[2], it[3])): sh.mark(*Q(it[2], it[3]), it[1], it[4])
            elif k == 'dim':
                if win.contains(Point(it[1])) and win.contains(Point(it[2])):
                    sh.dim(Q(*it[1]), Q(*it[2]), Q(*it[3]), angle=it[4], text=it[5])


def text_w(s, h): return len(s) * h * 0.82


def plan_prims(runs, els, bl):
    P = Prims(); occ = [e['rc'].buffer(50) for e in els]
    for r in runs:
        r['bars'] = bars_of(r, bl)
        occ.append(band(r, r['lo'] - B, r['hi'] + B, B + 200))
    for r in runs:
        bb = r['bars']; o = r['o']
        a, b = r['a'], r['b']
        # ---- longitudinal: bottom (continuous) at -B/4, top (dashed) at +B/4, pieces offset 90 so each lap shows
        for u, lay, lt in ((-B / 4, 'S-RFT-BOT', None), (B / 4, 'S-RFT-TOP', 'DASHED')):
            p, Lp = bb['p'], bb['Lp']
            ea, eb = r['ends']; ga, gb = ea['leg'], eb['leg']
            T = (b - a) + ga + gb
            starts = [0] if p == 1 else [i * (T - Lp) / (p - 1) for i in range(p)]
            off0 = ga
            for i, t0 in enumerate(starts):
                t1 = t0 + Lp
                s0, s1 = a + max(t0 - off0, 0), a + min(t1 - off0, b - a)
                uu = u + (90 if i % 2 else 0) * (1 if u < 0 else -1)
                pts = [at(r, s0, uu), at(r, s1, uu)]
                if i == 0 and ea['ldir']: pts.insert(0, at(r, s0, uu + ea['ldir'] * ea['leg']))     # plan leg into the footing
                if i == p - 1 and eb['ldir']: pts.append(at(r, s1, uu + eb['ldir'] * eb['leg']))
                P.pl(pts, lay, 25, lt)
                for tt, fl in ((s0, i == 0 and ea['kind'] == 'free'), (s1, i == p - 1 and eb['kind'] == 'free')):   # bent end: tick across the bar
                    if fl: P.pl([at(r, tt, uu - 120), at(r, tt, uu + 120)], lay, 25)
                if i and u < 0:
                    la, lb_ = a + t0 - off0, a + starts[i - 1] + Lp - off0
                    mx = (la + lb_) / 2
                    P.tx(f'LAP {LP}', *at(r, mx, u - 330), 150, 'S-DIM', 0 if o == 'H' else 90, TA.MIDDLE_CENTER)
        # ---- transverse U: one bar drawn per clear stretch + the distribution line with its count
        for a_, b_, n, mk in bb['tr']:
            m = (a_ + b_) / 2
            P.pl([at(r, m, -B / 2 + C), at(r, m, B / 2 - C)], 'S-RFT-BOT', 30)
            if b_ - a_ > 500:
                P.pl([at(r, a_ + 50, 0), at(r, b_ - 50, 0)], 'S-RFT-TXT', 0)
                for t_ in (a_ + 50, b_ - 50): P.pl([at(r, t_, -110), at(r, t_, 110)], 'S-RFT-TXT', 0)
        # ---- end notes (anchorage) and the run name
        for side, en in zip((-1, 1), r['ends']):
            kind, ext, what = en['kind'], en['ext'], en['what']
            v = r['hi'] if side > 0 else r['lo']
            t = f'TO FAR FACE -{C}' if kind == 'node' else f'{int(ext)} INTO {what.get("lab") or "FTG"}' if kind == 'ftg' else \
                f'TURN, LEG {en["leg"]} INTO {what.get("lab") or "FTG"}' if kind == 'turn' else f'END BENT DOWN {LG}'
            pos = at(r, v + side * (ext / 2 if kind != 'free' else -400), B / 4 + 260)
            P.tx(t, *pos, 130, 'S-DIM', 0 if o == 'H' else 90, TA.MIDDLE_CENTER)
        lab = f'{NAME} {r["name"]}'
        # ---- dimension chain of the stretches (outside, on the -u side)
        pts_ = sorted({r['lo'], r['hi']} | {c for a_, b_, f in r['cuts'] for c in (a_, b_) if r['lo'] < c < r['hi']})
        for x0, x1 in zip(pts_, pts_[1:]):
            if x1 - x0 < 150: continue
            if o == 'H': P.dim((x0, r['c'] - B / 2), (x1, r['c'] - B / 2), (x0, r['c'] - B / 2 - 450), 0, '<>')
            else: P.dim((r['c'] - B / 2, x0), (r['c'] - B / 2, x1), (r['c'] - B / 2 - 450, x0), 90, '<>')
        # ---- call-out block next to the run: run name, longitudinal + SB, transverse per stretch
        lines = [(None, f'{lab}   B={B}  h={H}')] + bb['lines'] + \
                [(mk, callout(n, d, mk, UL, S, 'B') + f' & T') for a_, b_, n, mk in bb['tr']]
        hh = CT * 1.55; Wb = max(text_w(t, CT) for m, t in lines) + 3 * CT; Hb = hh * len(lines)
        tgt = at(r, (r['lo'] + r['hi']) / 2, -B / 4)
        best = None
        for frac in (0.5, 0.3, 0.7, 0.15, 0.85, 0.4, 0.6):
            tm = r['lo'] + (r['hi'] - r['lo']) * frac
            for side in (1, -1):
                for gap in (900, 1600, 2600, 4000):
                    if o == 'H':
                        x0 = tm - Wb / 2; y0 = r['c'] + side * (B / 2 + gap) - (Hb if side < 0 else 0)
                    else:
                        x0 = r['c'] + side * (B / 2 + gap) - (Wb if side < 0 else 0); y0 = tm - Hb / 2
                    bx = box(x0, y0, x0 + Wb, y0 + Hb)
                    hit = sum(bx.intersection(g).area for g in occ)
                    if best is None or hit < best[0] - 1: best = (hit, bx, tm)
                    if hit == 0: break
                if best[0] == 0: break
            if best[0] == 0: break
        hit, bx, tm = best
        occ.append(bx.buffer(150)); r['cbox'] = bx
        x0, y0, x1, y1 = bx.bounds
        for i, (m, t) in enumerate(lines):
            yy = y1 - (i + 1) * hh + 0.3 * CT
            if m is None: P.tx(t, x0, yy, CT * 1.1, 'S-RFT-TXT')
            else:
                P.mk(m, x0 + 1.1 * CT, yy + CT / 2, CT); P.tx(t, x0 + 2.6 * CT, yy, CT, 'S-RFT-TXT')
        # leader: from the block edge facing the run to the bottom bar
        anchor = at(r, min(max(tm, r['lo'] + 200), r['hi'] - 200), -B / 4)
        if o == 'H': src = (min(max(anchor[0], x0 + 200), x1 - 200), y1 if anchor[1] > y1 else y0)
        else: src = (x1 if anchor[0] > x1 else x0, min(max(anchor[1], y0 + 200), y1 - 200))
        P.pl([src, anchor], 'S-RFT-TXT')
    return P


def tiles_of(runs):
    from shapely.ops import unary_union
    U = unary_union([band(r, r['a'] - 500, r['b'] + 500, B + 6000) for r in runs])
    X0, Y0, X1, Y1 = U.bounds
    TW, TH = 31000, 22000
    nx, ny = math.ceil((X1 - X0) / TW), math.ceil((Y1 - Y0) / TH)
    tw, th = (X1 - X0) / nx, (Y1 - Y0) / ny
    tiles = []
    for j in range(ny - 1, -1, -1):
        for i in range(nx):
            rr = box(X0 + i * tw, Y0 + j * th, X0 + (i + 1) * tw, Y0 + (j + 1) * th)
            if any(band(r, r['lo'], r['hi']).intersects(rr) for r in runs): tiles.append((i, j, rr))
    return tiles, (X0, Y0, X1, Y1)


def draw_parts(doc, runs, els, P, start_idx, meta0):
    tiles, ext = tiles_of(runs)
    num = {(i, j): k + 1 for k, (i, j, r) in enumerate(tiles)}
    idx = start_idx
    for k, (i, j, rr) in enumerate(tiles):
        meta = dict(meta0); meta['title'] = f'STRIP FOOTING {NAME} - REINFORCEMENT PLAN\nPART {k + 1} OF {len(tiles)}'
        sh = Sheet(doc, 0, -idx * 32000, meta); idx += 1
        rx0, ry0, rx1, ry1 = rr.bounds
        ox, oy = 3000 - rx0, 3600 - ry0
        Q = lambda x, y: (x + ox, y + oy)
        win = rr.buffer(800, join_style=2)
        for nm, fam, c, lo, hi in gen_cd.axis_lines():
            if fam == 'Y':
                if not (rx0 - 800 <= c <= rx1 + 800): continue
                a_, b_ = max(lo, ry0 - 800), min(hi, ry1 + 800)
                if a_ >= b_: continue
                sh.m.add_line(sh.P(*Q(c, a_)), sh.P(*Q(c, b_)), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 250})
                if hi >= ry1: gen_cd.bubble(sh, *Q(c, ry1 + 800 + 600), nm)
            else:
                if not (ry0 - 800 <= c <= ry1 + 800): continue
                a_, b_ = max(lo, rx0 - 800), min(hi, rx1 + 800)
                if a_ >= b_: continue
                sh.m.add_line(sh.P(*Q(a_, c)), sh.P(*Q(b_, c)), dxfattribs={'layer': 'S-CD-AX', 'linetype': 'CENTER', 'ltscale': 250})
                if lo <= rx0: gen_cd.bubble(sh, *Q(rx0 - 800 - 600, c), nm)
        # concrete: footings (+ their names) and the strip outline
        for e in els:
            g = e['rc'].intersection(win)
            for gg in getattr(g, 'geoms', [g]):
                if gg.is_empty or gg.geom_type != 'Polygon': continue
                sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in gg.exterior.coords], dxfattribs={'layer': 'S-GB-CONC', 'const_width': 20})
            if e['kind'] in ('F', 'M') and e['lab'] and rr.contains(e['rc'].centroid):
                x0, y0, x1, y1 = e['rc'].bounds
                sh.text(f"{e['lab']} h{e['h']}", *Q((x0 + x1) / 2, y1 - 120), 160, 'S-CD-TXT', align=TA.TOP_CENTER)
        for q in gen_cd.OPEN['rc'][1]:
            ls = LineString(q).intersection(win)
            for g in getattr(ls, 'geoms', [ls]):
                if g.is_empty or g.geom_type != 'LineString': continue
                sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in g.coords], dxfattribs={'layer': 'S-GB-CONC', 'const_width': 20})
        for r in runs:                                    # the strip outline itself (covers pieces drawn as lines only)
            ls = band(r, r['lo'], r['hi']).exterior.intersection(win)
            for g in getattr(ls, 'geoms', [ls]):
                if g.is_empty or g.geom_type != 'LineString': continue
                sh.m.add_lwpolyline([sh.P(*Q(*p)) for p in g.coords], dxfattribs={'layer': 'S-GB-CONC', 'const_width': 20})
        P.draw(sh, Q, rr, win)
        for r in runs:                                    # a run whose call-out is on another part: name + where
            vis = band(r, r['lo'], r['hi']).intersection(rr)
            if vis.is_empty or vis.area < B * 2000 or rr.contains(r['cbox'].centroid): continue
            other = next((n_ + 1 for n_, (_, _, t_) in enumerate(tiles) if t_.contains(r['cbox'].centroid)), None)
            x0, y0, x1, y1 = vis.bounds
            m = ((x0 + x1) / 2) if r['o'] == 'H' else ((y0 + y1) / 2)
            p_ = at(r, m, B / 2 + 300)
            sh.text(f'{NAME} {r["name"]} - BARS: SEE PART {other}', *Q(*p_), 220, 'S-RFT-TXT', rot=0 if r['o'] == 'H' else 90,
                    align=TA.BOTTOM_CENTER if r['o'] == 'H' else TA.TOP_CENTER)
        for (di, dj, side) in ((-1, 0, 'L'), (1, 0, 'R'), (0, 1, 'T'), (0, -1, 'B')):
            n = num.get((i + di, j + dj))
            if not n: continue
            if side in 'LR':
                x = rx0 if side == 'L' else rx1
                sh.line(Q(x, ry0), Q(x, ry1), 'S-SEC')
                sh.text(f'MATCH LINE - SEE PART {n}', *Q(x + (-250 if side == 'L' else 250), (ry0 + ry1) / 2), 220, 'S-SEC', rot=90,
                        align=TA.BOTTOM_CENTER if side == 'L' else TA.TOP_CENTER)
            else:
                y = ry1 if side == 'T' else ry0
                sh.line(Q(rx0, y), Q(rx1, y), 'S-SEC')
                sh.text(f'MATCH LINE - SEE PART {n}', *Q((rx0 + rx1) / 2, y + (250 if side == 'T' else -250)), 220, 'S-SEC',
                        align=TA.BOTTOM_CENTER if side == 'T' else TA.TOP_CENTER)
        gen_cd.key_plan(sh, tiles, k, ext)
        sh.text(f'STRIP FOOTING {NAME} - REINFORCEMENT PLAN  1:100', 1500, 1250, ST['panel'], 'S-SEC')
        sh.text(f'BOTTOM BARS: CONTINUOUS LINE; TOP BARS: DASHED. ONE BAR OF EACH SET DRAWN. TOP U = BOTTOM U. '
                f'SEE TYPICAL DETAILS FOR JUNCTIONS AND FOOTINGS.', 1500, 800, ST['note'], 'S-RFT-TXT')
    return idx, len(tiles)


# ------------------------------------------------------------------------------------------------ typical details 1:50
def detail_sheet(doc, idx, meta0):
    meta = dict(meta0); meta['title'] = f'STRIP FOOTING {NAME}\nTYPICAL JUNCTION DETAILS'
    sh = Sheet(doc, 0, -idx * 32000, meta)
    k = 2
    draw_legend(sh, 21000, 27900)

    def strip_h(Q, a, b, y, cl=True):                     # horizontal strip from a to b, centre y (real mm)
        sh.pline([Q(a, y - B / 2), Q(b, y - B / 2)], 'S-GB-CONC'); sh.pline([Q(a, y + B / 2), Q(b, y + B / 2)], 'S-GB-CONC')

    def lbars_h(Q, a, b, y, lay='S-RFT-BOT'):
        for j in range(NL):
            yy = y - B / 2 + C + (B - 2 * C) * j / (NL - 1)
            sh.pline([Q(a, yy), Q(b, yy)], lay, 12)

    def lbars_v(Q, x, a, b, lay='S-RFT-BOT'):
        for j in range(NL):
            xx = x - B / 2 + C + (B - 2 * C) * j / (NL - 1)
            sh.pline([Q(xx, a), Q(xx, b)], lay, 12)

    def tr_h(Q, a, b, y):
        t = a + 50
        while t <= b - 50 + 1:
            sh.line(Q(t, y - B / 2 + C), Q(t, y + B / 2 - C), 'S-RFT-STIR'); t += S

    def tr_v(Q, x, a, b):
        t = a + 50
        while t <= b - 50 + 1:
            sh.line(Q(x - B / 2 + C, t), Q(x + B / 2 - C, t), 'S-RFT-STIR'); t += S

    # (1) corner: both strips' bars carried to the far face - cover
    ox, oy = 2500, 15500; Q = lambda x, y: (ox + x * k, oy + y * k)
    L = 3500
    sh.pline([Q(0, 0), Q(L, 0), Q(L, B), Q(B, B), Q(B, L), Q(0, L)], 'S-GB-CONC', 0, True)
    lbars_h(Q, C, L, B / 2); lbars_v(Q, B / 2, C, L, 'S-RFT-TOP'); tr_h(Q, B, L, B / 2); tr_v(Q, B / 2, B, L)
    sh.dim(Q(0, -100), Q(B, -100), Q(0, -500), text=str(B))
    sh.text(f'BARS OF BOTH STRIPS TO THE FAR FACE - {C}', *Q(L / 2, -900), 170, 'S-RFT-TXT', align=TA.TOP_CENTER)
    sh.text('(1) CORNER  1:50', *Q(L / 2, -1500), ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # (2) T junction: through strip continuous (its U bars run through), stem bars to the far face - cover
    ox, oy = 12500, 15500; Q = lambda x, y: (ox + x * k, oy + y * k)
    L = 4500; y0 = 2500
    sh.pline([Q(0, y0), Q(L, y0), Q(L, y0 + B), Q(0, y0 + B)], 'S-GB-CONC', 0, True)
    xm = L / 2
    sh.pline([Q(xm - B / 2, 0), Q(xm - B / 2, y0)], 'S-GB-CONC'); sh.pline([Q(xm + B / 2, 0), Q(xm + B / 2, y0)], 'S-GB-CONC')
    lbars_h(Q, 0, L, y0 + B / 2); tr_h(Q, 0, L, y0 + B / 2)
    lbars_v(Q, xm, 0, y0 + B - C, 'S-RFT-TOP'); tr_v(Q, xm, 0, y0)
    sh.text('THROUGH STRIP: BARS CONTINUOUS, U BARS @%d THROUGH THE JUNCTION' % S, *Q(L / 2, y0 + B + 250), 170, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
    sh.text(f'STEM: BARS TO THE FAR FACE - {C}', *Q(xm + B / 2 + 150, y0 / 2), 170, 'S-RFT-TXT')
    sh.text('(2) T-JUNCTION  1:50', *Q(L / 2, -900), ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # (3) strip through / into an isolated footing
    ox, oy = 2500, 4000; Q = lambda x, y: (ox + x * k, oy + y * k)
    fL, fW = 2400, 2400; L = 7000; fx = 2300; y = fW / 2
    sh.pline([Q(fx, 0), Q(fx + fL, 0), Q(fx + fL, fW), Q(fx, fW)], 'S-GB-CONC', 0, True)
    sh.pline([Q(0, y - B / 2), Q(fx, y - B / 2)], 'S-GB-CONC'); sh.pline([Q(0, y + B / 2), Q(fx, y + B / 2)], 'S-GB-CONC')
    sh.pline([Q(fx + fL, y - B / 2), Q(L, y - B / 2)], 'S-GB-CONC'); sh.pline([Q(fx + fL, y + B / 2), Q(L, y + B / 2)], 'S-GB-CONC')
    lbars_h(Q, 0, L, y); tr_h(Q, 0, fx, y); tr_h(Q, fx + fL, L, y)
    for t in range(6):
        sh.line(Q(fx + C + t * (fL - 2 * C) / 5, C), Q(fx + C + t * (fL - 2 * C) / 5, fW - C), 'S-RFT-TOP')
    sh.text('STRIP BARS RUN THROUGH THE FOOTING ON ITS BOTTOM MESH (TOP BARS UNDER ITS TOP MESH); NO U BARS INSIDE THE FOOTING',
            *Q(L / 2, fW + 250), 170, 'S-RFT-TXT', align=TA.BOTTOM_CENTER)
    sh.text(f'STRIP ENDING IN A FOOTING: BARS ANCHORED 60d = {LP} (OR TO THE FAR FACE - {C})', *Q(L / 2, -500), 170, 'S-RFT-TXT', align=TA.TOP_CENTER)
    sh.text('(3) STRIP THROUGH / INTO AN ISOLATED FOOTING  1:50', *Q(L / 2, -1100), ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # notes
    for i, t in enumerate([f'LONGITUDINAL BARS OVER 12 M: EQUAL PIECES LAPPED 60d ({LP}); LAPS OF ADJACENT BARS STAGGERED.',
                           f'SIDE BARS SB 2 T {ds} LAPPED 60d ({LPS}).',
                           f'FREE END: BARS STOPPED AT COVER {C} AND BENT DOWN (LEG {LG}).',
                           'WHERE THE FOOTING IS SHALLOWER THAN THE STRIP THE STRIP DEPTH IS KEPT THROUGH IT (SEE REMARKS).']):
        sh.text(f'{i + 1}. {t}', 21000, 9000 - i * 420, ST['note'], 'S-RFT-TXT')
    return idx + 1


def main():
    import gen_st
    els, cols = gen_cd.build()
    runs, F = model(els)
    bl = BarList()
    meta0 = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                 rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='1:100', prefix='SDW-STR-FDN')
    meta0.update(PRJ.get('meta', {})); meta0['scale'] = '1:100'
    meta0['notes'] = project_notes(f'COVER FOOTINGS {C}; PLAIN CONCRETE 100.', f'LAP 60d; MAX. BAR 12 M.')
    doc = new_doc()
    for n_, col in gen_cd.LAYERS.items():
        if n_ not in doc.layers: doc.layers.add(n_, color=col)
    idx = gen_st.section_sheet(doc, 0, bl, B, H, SP.get('pcB', B + 200), n_m, d, ds, NAME)
    idx = detail_sheet(doc, idx, meta0)
    P = plan_prims(runs, els, bl)
    idx, nt = draw_parts(doc, runs, els, P, idx, meta0)
    meta = dict(meta0); meta['title'] = f'STRIP FOOTING {NAME}\nBBS'; meta['dwg'] = f'SDW-STR-FDN-{NAME}'
    nb = draw_bbs(doc, idx, bl.sorted(), meta)
    doc.saveas('out/STRIP.dxf')
    tot = sum(r['n_in'] * r['L'] / 1000 * r['d'] ** 2 / 162 for r in bl.sorted())
    print(f'strip: {len(runs)} runs {sum(r["hi"] - r["lo"] for r in runs) / 1000:.1f} m, plan parts {nt}, BBS sheets {nb}, steel {tot / 1000:.2f} t')
    for r in runs:
        print(r['name'], r['o'], round(r['c']), round(r['hi'] - r['lo']), [e['kind'] + ('/' + str(e['what'].get('lab') or e['what'].get('name')) if e['what'] else '') for e in r['ends']], 'bar', r['bars']['p'], 'x', r['bars']['Lp'],
              'stretches', [(round(b - a), n) for a, b, n, m in r['bars']['tr']])


if __name__ == '__main__':
    main()
