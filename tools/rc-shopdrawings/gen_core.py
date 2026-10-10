"""Core (shear-wall) necks: U-shaped lift / stair cores from the footing / raft to the top of the grade beams + lap.

project.json:
  core_types: {"CORE 1": {"W": 2800, "H": 3000, "t": 300, "ret": 900,          outer size (W across the opening),
                          "corner": [8, 18], "end": [4, 18],                    wall thickness, return length
                          "web": [16, 125], "hor": [12, 125],                   boundary bars per corner / per return end
                          "link": [10, 300], "ctie": [10, 125]}}               web verticals, horizontals, links, corner ties
  core_pairs: [["CORE 1", "F11", 3], ...]     (core type, footing under it, number) - pair_cores.py lists them
U shape, local axes: x across (0..W), y along (0..H), opening (door) at the top between the two returns.
Per pair two sheets: (1) PLAN SECTION 1:25 with every bar, horizontal bars / links / corner ties detailed with their
lengths; (2) SECTION through the wall 1:25 (footing, feet, Ld, lap, levels) + the vertical bars detailed outside with
every length. BBS at the end. Vertical bars: Ld in the footing = straight part + foot >= 60 d; feet turned into the
core (always room there)."""
import json, math, sys
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, ST, mm, project_notes, fillet

PRJ = json.load(open('project.json'))
LEV = PRJ['levels']
CC = PRJ.get('core_cover', 40)
FC = PRJ.get('footing_cover', 70)
HOOK = 100                                                  # 135-deg hook tail of ties / links


def bars_of(ct):
    """Vertical bars of the U core -> list of (x, y, d, kind) ; horizontal bar paths (outer / inner) ; link places."""
    W, H, t, R = ct['W'], ct['H'], ct['t'], ct['ret']
    dh = ct['hor'][0]
    dc, dw = ct['corner'][1], ct['web'][0]
    e = CC + dh + dc / 2                                    # boundary bars: cover + horizontal bar + d/2
    ew = CC + dh + dw / 2
    V = []
    def box(xs, ys):
        for x in xs:
            for y in ys:
                if (x, y) != (xs[1], ys[1]): V.append((x, y, dc, 'C'))
    for xs in ((e, t / 2, t - e), (W - e, W - t / 2, W - t + e)):
        for ys in ((e, t / 2, t - e), (H - e, H - t / 2, H - t + e)):
            box(xs, ys)
    ends = []
    for sgn, xe in ((1, R - e), (-1, W - R + e)):          # return ends: column at the end + one back on the inner face
        pts = [(xe, H - e), (xe, H - t / 2), (xe, H - t + e), (xe - sgn * 100, H - t + e)][:ct['end'][0]]
        for x, y in pts: V.append((x, y, dc, 'E'))
        ends.append(xe)
    s = ct['web'][1]
    def run(fixed, a, b, axis):                             # web bars between two boundary bars a < b at spacing <= s
        n = math.ceil((b - a) / s) - 1
        for i in range(1, n + 1):
            u = a + (b - a) * i / (n + 1)
            V.append(((fixed, u) if axis == 'y' else (u, fixed)) + (dw, 'W'))
        return n
    nw = {}
    nw['left'] = [run(x, t - e, H - t + e, 'y') for x in (ew, t - ew)]
    nw['right'] = [run(x, t - e, H - t + e, 'y') for x in (W - ew, W - t + ew)]
    nw['bottom'] = [run(y, t - e, W - t + e, 'x') for y in (ew, t - ew)]
    nw['ret'] = [run(H - ew, t - e, ends[0], 'x'), run(H - t + ew, t - e, ends[0] - 100, 'x'),
                 run(H - ew, ends[1], W - t + e, 'x'),
                 run(H - t + ew, ends[1] + 100, W - t + e, 'x')]
    # horizontal bars (centre line), outer and inner face, hooked across the wall at the return ends
    c = CC + dh / 2
    outer = [(R - c, H - t + c), (R - c, H - c), (c, H - c), (c, c), (W - c, c), (W - c, H - c), (W - R + c, H - c), (W - R + c, H - t + c)]
    inner = [(R - c, H - c), (R - c, H - t + c), (t - c, H - t + c), (t - c, t - c), (W - t + c, t - c), (W - t + c, H - t + c),
             (W - R + c, H - t + c), (W - R + c, H - c)]
    return V, nw, outer, inner


def seglen(p): return [math.dist(a, b) for a, b in zip(p, p[1:])]


def ootl(p, d):
    """Out-to-out bending lengths of an open bar given on its centre line (outer corners + d/2 each side)."""
    L = seglen(p)
    return [round(x + d) if 0 < i < len(L) - 1 else round(x + d / 2) for i, x in enumerate(L)]


def draw_pair(doc, idx, name, ct, f, no, bl, meta0):
    W, H, t, R = ct['W'], ct['H'], ct['t'], ct['ret']
    tof = LEV['founding'] + 0.10 + f['h'] / 1000
    tgb = LEV['top_gb']
    Hn = round((tgb - tof) * 1000)
    yb = FC + max(f['bot'][1], f['bot'][3]) * 2              # verticals stand on the bottom mesh
    emb = f['h'] - yb
    V, nw, outer, inner = bars_of(ct)
    # ---- marks
    dv = {}
    for kind, d in (('C', ct['corner'][1]), ('W', ct['web'][0])):
        n = sum(1 for v in V if v[3] in (('C', 'E') if kind == 'C' else ('W',)))
        LD = 60 * d; foot = max(12 * d, 300, int(math.ceil((LD - emb) / 10) * 10))
        vert = emb + Hn + 60 * d
        Lv = int(round((vert + foot) / 10) * 10)
        dv[kind] = dict(d=d, n=n, foot=foot, vert=vert, L=Lv, LD=LD, mk=bl.add(d, ('L', foot, vert, 0), Lv, n, no, 'V'))
    dh, sh_ = ct['hor']
    n_h = math.floor((Hn - 100) / sh_) + 1 + 2               # neck + 2 in the footing
    Ho, Hi = ootl(outer, dh), ootl(inner, dh)
    def oo_pts(pth, L):                                      # the bar redrawn with its out-to-out segment lengths
        q = [(0, 0)]
        for (a, b), l in zip(zip(pth, pth[1:]), L):
            dx, dy = b[0] - a[0], b[1] - a[1]; n = math.hypot(dx, dy)
            q.append((q[-1][0] + round(dx / n * l), q[-1][1] + round(dy / n * l)))
        return tuple(q)
    mo = bl.add(dh, ('OPEN',) + oo_pts(outer, Ho), sum(Ho), n_h, no, 'H')
    mi = bl.add(dh, ('OPEN',) + oo_pts(inner, Hi), sum(Hi), n_h, no, 'H')
    dl, sl = ct['link']
    links = []                                               # every second web bar pair across the wall
    for wall, pairs in (('left', (0, 1)), ('right', (0, 1)), ('bottom', (0, 1))):
        n = min(nw[wall]); links += [wall] * math.ceil(n / 2)
    links += ['ret'] * (math.ceil(min(nw['ret'][0], nw['ret'][1]) / 2) + math.ceil(min(nw['ret'][2], nw['ret'][3]) / 2))
    rows_l = math.floor((Hn - 100) / sl) + 1
    lw = t - 2 * CC
    ml = bl.add(dl, ('U', HOOK, lw, HOOK), lw + 2 * HOOK, len(links) * rows_l, no, 'LINK')
    dt, stt = ct['ctie']
    tw = t - 2 * CC
    n_ct = math.floor((Hn - 100) / stt) + 1 + 2
    mt = bl.add(dt, ('ST', tw, tw), 4 * tw + 2 * HOOK, 4 * n_ct, no, 'TIE')

    # ================= sheet 1: plan section =================
    meta = dict(meta0); meta['title'] = f'CORE NECKS - {name} ON {f["name"]}\nPLAN SECTION'
    meta['dwg'] = f"{meta['prefix']}-{name.replace(' ', '')}-{f['name']}-1"
    s1 = Sheet(doc, 0, -idx * 32000, meta)
    draw_legend(s1, 21000, 27900)
    s1.text(f'NECK {name}  {W}x{H}  t={t}  ON  {f["name"]}', 2000, 27900, ST['name'], 'S-AXIS-TXT')
    s1.text(f'NO={no}   T.O.F {tof:+.2f}   T.O.GB {tgb:+.2f}   NECK H = {mm(Hn)}', 2000, 27100, ST['sub'], 'S-SEC')
    s1.text(f'FOOTING {f["name"]}  h={f["h"]}   (SCHEDULE: SHEAR WALLS SCHEDULE - FROM FOUNDATION TO UPPER ROOF)', 2000, 26400, ST['sub'], 'S-SEC', maxw=18000)
    k = 4.0; ox, oy = 3200, 25200 - H * k
    P = lambda x, y: (ox + x * k, oy + y * k)
    outl = [(0, 0), (W, 0), (W, H), (W - R, H), (W - R, H - t), (W - t, H - t), (W - t, t), (t, t), (t, H - t), (R, H - t), (R, H), (0, H)]
    s1.pline([P(*p) for p in outl], 'S-GB-CONC', 0, True)
    for pth, lay in ((outer, 'S-RFT-STIR'), (inner, 'S-RFT-STIR')):
        s1.pline([P(*p) for p in pth], lay, dh * k, r=3 * dh * k)
    for x, y, d, kd in V:
        hh = s1.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-TOP'})
        hh.paths.add_edge_path().add_arc(s1.P(*P(x, y)), d / 2 * k, 0, 360)
    # corner ties
    e = CC + dh + ct['corner'][1] / 2
    for x0 in (CC + dh / 2 + dt / 2, W - t + CC + dh / 2 + dt / 2):
        for y0 in (CC + dh / 2 + dt / 2, H - t + CC + dh / 2 + dt / 2):
            w_ = t - 2 * (CC + dh / 2 + dt / 2)
            s1.pline([P(x0, y0), P(x0 + w_, y0), P(x0 + w_, y0 + w_), P(x0, y0 + w_)], 'S-RFT-STIR', 0, True, r=2 * dt * k)
    # links: drawn on the web bars (every second)
    def link(a, b):
        s1.pline([P(*a), P(*b)], 'S-RFT-STIR', 12)
    for wall, xs in (('left', (CC + dh + ct['web'][0] / 2, t - CC - dh - ct['web'][0] / 2)),
                     ('right', (W - t + CC + dh + ct['web'][0] / 2, W - CC - dh - ct['web'][0] / 2))):
        ys = sorted(y for x, y, d, kd in V if kd == 'W' and abs(x - xs[0]) < 1)
        for y in ys[::2]: link((xs[0], y), (xs[1], y))
    yy = (CC + dh + ct['web'][0] / 2, t - CC - dh - ct['web'][0] / 2)
    xs_ = sorted(x for x, y, d, kd in V if kd == 'W' and abs(y - yy[0]) < 1)
    for x in xs_[::2]: link((x, yy[0]), (x, yy[1]))
    # dims
    s1.dim(P(0, 0), P(W, 0), (P(0, 0)[0], P(0, 0)[1] - 900), text=str(W))
    s1.dim(P(0, 0), P(0, H), (P(0, 0)[0] - 900, P(0, 0)[1]), angle=90, text=str(H))
    s1.dim(P(0, H), P(R, H), (P(0, H)[0], P(0, H)[1] + 700), text=str(R))
    s1.dim(P(R, H), P(W - R, H), (P(R, H)[0], P(0, H)[1] + 700), text=str(W - 2 * R))
    s1.dim(P(W - R, H), P(W, H), (P(W - R, H)[0], P(0, H)[1] + 700), text=str(R))
    s1.dim(P(0, H / 2), P(t, H / 2), (P(0, 0)[0], P(0, H / 2)[1] + 400), text=str(t))
    s1.text('DOOR / OPENING', *P(W / 2, H - t / 2), 220, 'S-SEC', align=TA.MIDDLE_CENTER)
    # call-outs (right of the plan) with leaders
    cx = P(W, 0)[0] + 1800; cy = P(0, H)[1] - 200
    vc, vw = dv['C'], dv['W']
    ew_ = CC + dh + ct['web'][0] / 2
    items = [(vc['mk'], callout(vc['n'], vc['d'], vc['mk'], vc['L'], layer='V') + f"  ({ct['corner'][0]} PER CORNER + {ct['end'][0]} PER RETURN END)",
              (W - CC - dh - ct['corner'][1] / 2, H - CC - dh - ct['corner'][1] / 2)),
             (mt, callout(4 * n_ct, dt, mt, 4 * tw + 2 * HOOK, stt, 'TIE') + '  4 CORNERS', (W - t / 2, H - t + CC + dh)),
             (mo, callout(n_h, dh, mo, sum(Ho), sh_, 'H') + '  OUTER FACE', (W - CC - dh / 2, H * 0.72)),
             (vw['mk'], callout(vw['n'], vw['d'], vw['mk'], vw['L'], ct['web'][1], 'V') + '  EACH FACE',
              min((v for v in V if v[3] == 'W' and abs(v[0] - (W - ew_)) < 1), key=lambda v: abs(v[1] - H * 0.6))[:2]),
             (ml, callout(len(links) * rows_l, dl, ml, lw + 2 * HOOK, sl, 'LINK') + f'  ({len(links)} PER ROW, {rows_l} ROWS)', (W - t / 2, H * 0.45)),
             (mi, callout(n_h, dh, mi, sum(Hi), sh_, 'H') + '  INNER FACE', (W - t + CC + dh / 2, H * 0.3))]
    for i, (mk, txt, at) in enumerate(items):
        y = cy - i * 900
        s1.ctext(mk, txt, cx, y, ST['call'] * 0.85, maxw=12500)
        a_ = P(*at)
        s1.pline([a_, (P(W, 0)[0] + 500, a_[1]), (cx - 80, y + 100)], 'S-DIM')
        s1.circle(*a_, 30, 'S-DIM')
    s1.text(f'PLAN SECTION  {name}  1:25   (COVER {CC}; VERTICAL BARS INSIDE THE HORIZONTAL BARS)', P(W / 2, 0)[0], P(0, 0)[1] - 1700,
            ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # horizontal bar / link / tie details (out-to-out lengths)
    def bar_detail(pth, L, mk, x0, y0, kk, title):
        q = [(x0 + x * kk, y0 + y * kk) for x, y in pth]
        s1.pline(q, 'S-RFT-STIR', 25, r=60)
        for (a, b), Ls in zip(zip(q, q[1:]), L):
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            vert_ = abs(a[0] - b[0]) < 1
            short = Ls < 400
            s1.text(str(Ls), mx + (-120 if vert_ else 0) + (0 if not short else (260 if mx > x0 + 2600 else -260) * 0), my + (0 if vert_ else 90) + (500 if short else 0), ST['len'] * 0.8, 'S-DIM',
                    rot=90 if vert_ else 0, align=TA.BOTTOM_CENTER)
        s1.ctext(mk, f'{title}  L={sum(L)}', x0, y0 - 900, ST['call'] * 0.85)
    kk = min(5200 / W, 5600 / H)
    bar_detail(outer, Ho, mo, 22300, 14200, kk, 'OUTER H-BAR')
    bar_detail(inner, Hi, mi, 28800, 14200, kk, 'INNER H-BAR')
    # link + tie
    lx, ly = 22300, 9000
    s1.pline(fillet([(lx, ly + HOOK * 4), (lx, ly), (lx + lw * 4, ly), (lx + lw * 4, ly + HOOK * 4)], 40), 'S-RFT-STIR', 25)
    s1.text(str(lw), lx + lw * 2, ly - 80, ST['len'] * 0.8, 'S-DIM', align=TA.TOP_CENTER)
    s1.text(f'{HOOK} (135 DEG)', lx + lw * 4 + 120, ly + HOOK * 2, ST['len'] * 0.7, 'S-DIM')
    s1.ctext(ml, f'LINK  L={lw + 2 * HOOK}', lx, ly - 900, ST['call'] * 0.85)
    tx_, ty_ = 28800, 8700
    s1.pline([(tx_, ty_), (tx_ + tw * 5, ty_), (tx_ + tw * 5, ty_ + tw * 5), (tx_, ty_ + tw * 5)], 'S-RFT-STIR', 25, True, r=60)
    s1.line((tx_ + 60, ty_ + tw * 5 - 60), (tx_ + 400, ty_ + tw * 5 - 400), 'S-RFT-STIR')
    s1.text(f'{tw}x{tw}', tx_ + tw * 2.5, ty_ - 80, ST['len'] * 0.8, 'S-DIM', align=TA.TOP_CENTER)
    s1.ctext(mt, f'CORNER TIE  L={4 * tw + 2 * HOOK}', tx_, ty_ - 900, ST['call'] * 0.85)
    s1.text('HORIZONTAL BARS: OUT-TO-OUT LENGTHS; HOOKED ACROSS THE WALL AT THE RETURN ENDS. LINKS @%d BOTH WAYS.' % sl,
            22300, 6600, ST['note'], 'S-RFT-TXT', maxw=12000)

    # ================= sheet 2: section through the wall + vertical bars detailed =================
    meta = dict(meta0); meta['title'] = f'CORE NECKS - {name} ON {f["name"]}\nSECTION + BAR DETAILS'
    meta['dwg'] = f"{meta['prefix']}-{name.replace(' ', '')}-{f['name']}-2"
    s2 = Sheet(doc, 0, -(idx + 1) * 32000, meta)
    draw_legend(s2, 21000, 27900)
    s2.text(f'NECK {name}  ON  {f["name"]}  - SECTION THROUGH THE WALL', 2000, 27900, ST['name'] * 0.8, 'S-AXIS-TXT')
    top = f['h'] + Hn
    lpv = 60 * vw['d']
    k2 = next(kk_ for kk_ in (4.0, 10 / 3, 2.5, 2.0) if kk_ * (f['h'] + Hn + 60 * vc['d'] + 900) <= 20500)
    ex, ey = 9200, 2600 + 100 * k2
    Q = lambda x, y: (ex + x * k2, ey + y * k2)
    fx0, fx1 = -1200, t + 2200                                      # footing shown 1200 outside, 2200 inside (break)
    s2.pline([Q(fx0 - 100, -100), Q(fx1, -100)], 'S-GB-CONC'); s2.pline([Q(fx0 - 100, -100), Q(fx0 - 100, 0), Q(fx0, 0)], 'S-GB-CONC')
    s2.pline([Q(fx1, 0), Q(fx0, 0), Q(fx0, f['h']), Q(0, f['h'])], 'S-GB-CONC')
    s2.pline([Q(t, f['h']), Q(fx1, f['h'])], 'S-GB-CONC')
    s2.pline([Q(fx1, -100), Q(fx1, f['h'])], 'S-SEC')
    s2.text('(BREAK)', *Q(fx1 + 60, f['h'] / 2), 150, 'S-SEC')
    s2.pline([Q(0, f['h']), Q(0, top + lpv + 300)], 'S-GB-CONC'); s2.pline([Q(t, f['h']), Q(t, top + lpv + 300)], 'S-GB-CONC')
    s2.break_line(Q(-300, top + lpv + 300), Q(t + 300, top + lpv + 300))
    s2.text('OUTSIDE', *Q(-600, top - 600), 170, 'S-SEC', align=TA.BOTTOM_RIGHT); s2.text('INSIDE CORE', *Q(t + 300, top - 600), 170, 'S-SEC')
    s2.pline([Q(fx0 + FC, FC + 10), Q(fx1, FC + 10)], 'S-RFT-BOT', 30)
    # vertical bars, feet turned into the core
    xo, xi = CC + dh + vw['d'] / 2, t - CC - dh - vw['d'] / 2
    for x, yy_, lpx in ((xo, yb, lpv), (xi, yb + vw['d'], lpv)):
        s2.pline([Q(x + vw['foot'], yy_), Q(x, yy_), Q(x, top + lpx)], 'S-RFT-TOP', max(vw['d'] * k2, 25), r=3 * vw['d'] * k2)
    # horizontal bars (dots both faces) and links
    xh = (CC + dh / 2, t - CC - dh / 2)
    y = f['h'] - 150; ys_h = [f['h'] - 350, f['h'] - 150]
    y = f['h'] + 50
    while y <= top - 50: ys_h.append(y); y += sh_
    for y in ys_h:
        for x in xh:
            hh = s2.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'})
            hh.paths.add_edge_path().add_arc(s2.P(*Q(x, y)), dh / 2 * k2, 0, 360)
    y = f['h'] + 50
    while y <= top - 50:
        s2.line(Q(xh[0], y + 30), Q(xh[1], y + 30), 'S-RFT-STIR'); y += sl
    # levels, dims
    XD = t + 1500
    s2.dim(Q(XD, f['h']), Q(XD, top), Q(XD + 450, f['h']), angle=90, text=str(Hn))
    s2.dim(Q(XD, top), Q(XD, top + lpv), Q(XD + 450, top), angle=90, text=f'LAP {lpv}')
    s2.dim(Q(xo - 160, yb), Q(xo - 160, f['h']), Q(fx0 + 400, yb), angle=90, text=str(emb))
    s2.dim(Q(xi, yb + vw['d']), Q(xi + vw['foot'], yb + vw['d']), Q(xi, yb + 260), text=str(vw['foot']))
    for yy_, lab in ((-100, f"F.L (B.O.PC) {LEV['founding']:+.2f}"), (0, f"T.O.PC {LEV['founding'] + .1:+.2f}"),
                     (f['h'], f"T.O.F {tof:+.2f}"), (top, f"T.O.GB {tgb:+.2f}")):
        xl_ = Q(fx0, 0)[0]
        s2.line((xl_ - 3600, Q(0, yy_)[1]), (xl_ - 150, Q(0, yy_)[1]), 'S-DIM'); s2.text(lab, xl_ - 3600, Q(0, yy_)[1] + 50, 170, 'S-DIM')
    s2.text(f"Ld = {emb} + {vw['foot']} = {emb + vw['foot']} >= 60d = {vw['LD']}  (T{vw['d']});  "
            f"T{vc['d']}: {emb} + {vc['foot']} = {emb + vc['foot']} >= {vc['LD']}", Q(fx0, 0)[0] - 3600, Q(0, -100)[1] - 900, ST['note'], 'S-DIM')
    s2.text('FEET TURNED INTO THE CORE, ON THE BOTTOM MESH', Q(fx0, 0)[0] - 3600, Q(0, -100)[1] - 1250, ST['note'], 'S-DIM')
    s2.ctext(vw['mk'], callout(vw['n'], vw['d'], vw['mk'], vw['L'], ct['web'][1], 'V'), Q(t + 300, 0)[0], Q(0, top + lpv * 0.5)[1], ST['call'] * 0.85)
    s2.ctext(mo, callout(n_h, dh, mo, sum(Ho), sh_, 'H'), Q(t + 300, 0)[0], Q(0, f['h'] + Hn * 0.55)[1], ST['call'] * 0.85)
    s2.ctext(ml, callout(len(links) * rows_l, dl, ml, lw + 2 * HOOK, sl, 'LINK'), Q(t + 300, 0)[0], Q(0, f['h'] + Hn * 0.55)[1] - 600, ST['call'] * 0.85)
    s2.text(f'SECTION THROUGH THE WALL  1:{round(100 / k2)}', Q(t / 2, 0)[0], Q(0, -100)[1] - 1600, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # vertical bars detailed outside (every length)
    for j, (key, ttl) in enumerate((('C', 'BOUNDARY BAR (CORNERS / RETURN ENDS)'), ('W', 'WEB BAR (EACH FACE)'))):
        v = dv[key]
        bx0, by0 = 20500 + j * 6800, 6200
        kb = min(13500 / (v['vert'] + 600), 3.0)
        B_ = lambda x, y: (bx0 + x * kb, by0 + y * kb)
        fx_ = min(v['foot'] * kb, 3000) / kb
        s2.pline([B_(fx_, 0), B_(0, 0), B_(0, v['vert'])], 'S-RFT-TOP', max(v['d'] * kb, 30), r=3 * v['d'] * kb)
        s2.text(str(v['foot']), *B_(fx_ / 2, -100 / kb), ST['len'], 'S-DIM', align=TA.TOP_CENTER)
        s2.text(str(v['vert']), *B_(-150 / kb, v['vert'] / 2), ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        for yy_, tt in ((emb, f'T.O.F ({emb} IN FOOTING)'), (emb + Hn, f'T.O.GB (NECK {Hn})'), (emb + Hn + 60 * v['d'], f'LAP {60 * v["d"]}')):
            s2.line(B_(-60 / kb, yy_), B_(350 / kb, yy_), 'S-DIM'); s2.text(tt, B_(400 / kb, 0)[0], B_(0, yy_)[1] - 60, ST['note'], 'S-DIM')
        s2.ctext(v['mk'], callout(v['n'], v['d'], v['mk'], v['L'], layer='V'), bx0, by0 + v['vert'] * kb + 700, ST['call'] * 0.85)
        s2.text(f"L = {v['foot']} + {v['vert']} = {v['L']}", bx0, by0 + v['vert'] * kb + 300, ST['note'], 'S-RFT-TXT')
        s2.text(ttl, bx0, by0 - 900, ST['panel'] * 0.8, 'S-SEC', maxw=6200)
        s2.text(f"Ld = {emb} + {v['foot']} = {emb + v['foot']} >= 60d = {v['LD']}", bx0, by0 - 1300, ST['note'], 'S-DIM')
    return Hn, dv


def main():
    types = PRJ['core_types']; pairs = PRJ['core_pairs']
    lib = json.load(open('footings.json'))
    import os
    if os.path.exists('footings_ext.json'): lib.update(json.load(open('footings_ext.json')))
    doc = new_doc(); bl = BarList()
    meta0 = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                 rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='1:25', prefix='SDW-STR-NCK')
    meta0.update(PRJ.get('meta', {})); meta0['scale'] = '1:25'
    meta0['notes'] = project_notes(f'COVER CORE WALLS {CC}.', 'VERTICAL BARS: Ld IN THE FOOTING >= 60d (STRAIGHT + FOOT), FEET INTO THE CORE.')
    idx = 0
    for nm, fn, no in pairs:
        f = dict(lib[fn]); f.setdefault('name', fn)
        Hn, dv = draw_pair(doc, idx, nm, types[nm], f, int(no), bl, meta0)
        print(nm, fn, no, 'neck', Hn, {k: (v['n'], v['d'], v['foot'], v['vert'], v['L']) for k, v in dv.items()})
        idx += 2
    meta = dict(meta0); meta['title'] = 'CORE NECKS'; meta['dwg'] = 'SDW-STR-NCK-CORES'
    nb = draw_bbs(doc, idx, bl.sorted(), meta)
    doc.saveas('out/CORE_NECKS.dxf'); print('sheets', idx, '+ BBS', nb)


if __name__ == '__main__':
    main()
