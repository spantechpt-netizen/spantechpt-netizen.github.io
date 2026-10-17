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
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, ST, mm, project_notes, fillet, draw_open_tie

PRJ = json.load(open('project.json'))
LEV = PRJ['levels']
ZONE = None                       # set per zone by gen_zone_cores
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
    from gen import zone_levels, footing_levels
    ZL = zone_levels(ZONE)
    fl, tpc, tof = footing_levels(f['h'], ZL)
    tgb = ZL['top_gb']
    Hn = max(0, round((tgb - tof) * 1000))
    starter = Hn == 0                   # wall starts at the footing (basement): starter bars, no neck
    yb = FC + max(f['bot'][1], f['bot'][3]) * 2              # verticals stand on the bottom mesh
    emb = f['h'] - yb
    V, nw, outer, inner = bars_of(ct)
    # ---- marks
    # vertical bars as the column necks (engineer, Oct 2026): STARTER from the footing (foot on the bottom mesh,
    # full Ld in the footing, up to T.O.F + lap) + straight NECK BAR from T.O.F to T.O.GB + lap
    LAPN, LDN = PRJ.get('neck_lap_d', 65), PRJ.get('neck_ld_d', 60)
    dv = {}
    for kind, d in (('C', ct['corner'][1]), ('W', ct['web'][0])):
        n = sum(1 for v in V if v[3] in (('C', 'E') if kind == 'C' else ('W',)))
        LD = LDN * d; lp = LAPN * d
        foot = max(12 * d, 300, int(math.ceil((LD - emb) / 10) * 10))
        vert = emb + lp
        Lv = int(round((vert + foot) / 10) * 10)
        Ln = int(round((Hn + lp) / 10) * 10)
        dv[kind] = dict(d=d, n=n, foot=foot, vert=vert, L=Lv, LD=LD, lp=lp, Ln=Ln,
                        mk=bl.add(d, ('L', foot, vert, 0), Lv, n, no, 'V'),
                        mkn=None if starter else bl.add(d, ('S', Ln), Ln, n, no, 'V'))
    dh, sh_ = ct['hor']
    n_h = math.floor((Hn - 100) / sh_) + 1 + 2               # neck + 2 in the footing
    # horizontal bars (approved core detail): per wall two U-bars (outer face + inner face), legs across the wall,
    # long side = wall length - 2 covers; the walls' U-bars overlap at the corners
    lu = t - 2 * CC
    walls = [('BACK WALL', W, 2), ('SIDE WALL', H, 4), ('RETURN', R, 4)]
    hu = {}
    for wn, Lw, k_ in walls:
        Lb = Lw - 2 * CC
        hu[wn] = dict(Lb=Lb, L=Lb + 2 * lu, n=k_ * n_h, per=k_,
                      mk=bl.add(dh, ('U', lu, Lb, lu), Lb + 2 * lu, k_ * n_h, no, 'H'))
    dl, sl = ct['link']
    links = []                                               # every second web bar pair across the wall
    for wall, pairs in (('left', (0, 1)), ('right', (0, 1)), ('bottom', (0, 1))):
        n = min(nw[wall]); links += [wall] * math.ceil(n / 2)
    links += ['ret'] * (math.ceil(min(nw['ret'][0], nw['ret'][1]) / 2) + math.ceil(min(nw['ret'][2], nw['ret'][3]) / 2))
    rows_l = math.floor((Hn - 100) / sl) + 1
    lw = t - 2 * CC
    ml = bl.add(dl, ('U', HOOK, lw, HOOK), lw + 2 * HOOK, len(links) * rows_l, no, 'LINK') if rows_l > 0 else None
    dt, stt = ct['ctie']
    tw = t - 2 * CC
    n_ct = math.floor((Hn - 100) / stt) + 1 + 2
    mt = bl.add(dt, ('HT', tw, tw), 4 * tw + 2 * HOOK, 4 * n_ct, no, 'TIE')

    # ================= sheet 1: plan section =================
    meta = dict(meta0); meta['title'] = f'CORE NECKS - {name} ON {f["name"]}\nPLAN SECTION'
    meta['dwg'] = f"{meta['prefix']}-{name.replace(' ', '')}-{f['name']}-1"
    s1 = Sheet(doc, 0, -idx * 32000, meta)
    draw_legend(s1, 21000, 27900)
    s1.text(f'{"STARTER BARS" if starter else "NECK"} {name}  {W}x{H}  t={t}  ON  {f["name"]}', 2000, 27900, ST['name'], 'S-AXIS-TXT')
    s1.text(f'NO={no}   T.O.F {tof:+.2f}   ' + ('WALL STARTS AT THE FOOTING (T.O.F = T.O.SLAB): STARTER BARS, NO NECK' if starter else f'T.O.GB {tgb:+.2f}   NECK H = {mm(Hn)}'), 2000, 27100, ST['sub'], 'S-SEC')
    s1.text(f'FOOTING {f["name"]}  h={f["h"]}   (SCHEDULE: SHEAR WALLS SCHEDULE - FROM FOUNDATION TO UPPER ROOF)', 2000, 26400, ST['sub'], 'S-SEC', maxw=18000)
    k = 4.0; ox, oy = 3200, 25200 - H * k
    P = lambda x, y: (ox + x * k, oy + y * k)
    outl = [(0, 0), (W, 0), (W, H), (W - R, H), (W - R, H - t), (W - t, H - t), (W - t, t), (t, t), (t, H - t), (R, H - t), (R, H), (0, H)]
    s1.pline([P(*p) for p in outl], 'S-GB-CONC', 0, True)
    c_ = CC + dh / 2
    def U_(a, b, legdir):                                    # U on its centre line: long side a-b, legs across the wall
        (ax, ay), (bx, by) = a, b
        lx, ly = legdir[0] * (t - 2 * c_), legdir[1] * (t - 2 * c_)
        s1.pline([P(ax + lx, ay + ly), P(ax, ay), P(bx, by), P(bx + lx, by + ly)], 'S-RFT-STIR', dh * k, r=3 * dh * k)
    o_ = 12                                                  # the two U-bars of a wall drawn just apart
    U_((c_, c_), (W - c_, c_), (0, 1)); U_((c_ + o_, t - c_), (W - c_ - o_, t - c_), (0, -1))            # back wall
    U_((c_, c_ + o_), (c_, H - c_), (1, 0)); U_((t - c_, c_), (t - c_, H - c_ - o_), (-1, 0))            # left wall
    U_((W - c_, c_ + o_), (W - c_, H - c_), (-1, 0)); U_((W - t + c_, c_), (W - t + c_, H - c_ - o_), (1, 0))  # right wall
    U_((c_ + o_, H - c_), (R - c_, H - c_), (0, -1)); U_((c_, H - t + c_), (R - c_ - o_, H - t + c_), (0, 1))  # left return
    U_((W - R + c_, H - c_), (W - c_ - o_, H - c_), (0, -1)); U_((W - R + c_ + o_, H - t + c_), (W - c_, H - t + c_), (0, 1))  # right return
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
    items = [(vc['mk'], callout(vc['n'], vc['d'], vc['mk'], vc['L'], layer='V') + f"  STARTERS ({ct['corner'][0]} PER CORNER + {ct['end'][0]} PER RETURN END)",
              (W - CC - dh - ct['corner'][1] / 2, H - CC - dh - ct['corner'][1] / 2)),
             ] + ([] if starter else [(vc['mkn'], callout(vc['n'], vc['d'], vc['mkn'], vc['Ln'], layer='V') + '  NECK BARS (BOUNDARY)', (CC + dh + ct['corner'][1] / 2, H - CC - dh - ct['corner'][1] / 2)),
                                    (vw['mkn'], callout(vw['n'], vw['d'], vw['mkn'], vw['Ln'], ct['web'][1], 'V') + '  NECK BARS EACH FACE', (ew_, H * 0.5))]) + [
             (mt, callout(4 * n_ct, dt, mt, 4 * tw + 2 * HOOK, stt, 'TIE') + '  4 CORNERS', (W - t / 2, H - t + CC + dh)),
             (hu['SIDE WALL']['mk'], callout(hu['SIDE WALL']['n'], dh, hu['SIDE WALL']['mk'], hu['SIDE WALL']['L'], sh_, 'H') + '  U-BARS SIDE WALLS (2 PER WALL)', (W - CC - dh / 2, H * 0.72)),
             (vw['mk'], callout(vw['n'], vw['d'], vw['mk'], vw['L'], ct['web'][1], 'V') + '  STARTERS EACH FACE',
              min((v for v in V if v[3] == 'W' and abs(v[0] - (W - ew_)) < 1), key=lambda v: abs(v[1] - H * 0.6))[:2]),
             ] + ([(ml, callout(len(links) * rows_l, dl, ml, lw + 2 * HOOK, sl, 'LINK') + f'  ({len(links)} PER ROW, {rows_l} ROWS)', (W - t / 2, H * 0.45))] if ml else []) + [
             (hu['BACK WALL']['mk'], callout(hu['BACK WALL']['n'], dh, hu['BACK WALL']['mk'], hu['BACK WALL']['L'], sh_, 'H') + '  U-BARS BACK WALL (2)', (W * 0.6, CC + dh / 2)),
             (hu['RETURN']['mk'], callout(hu['RETURN']['n'], dh, hu['RETURN']['mk'], hu['RETURN']['L'], sh_, 'H') + '  U-BARS RETURNS (2 PER RETURN)', (W - R / 2, H - CC - dh / 2))]
    for i, (mk, txt, at) in enumerate(items):
        y = cy - i * 800
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
    for j, (wn, Lw, k_) in enumerate(walls):                  # U-bars, every length written
        u = hu[wn]; kkj = min(kk, 3600 / u['Lb'])
        x0_, y0_ = 22300 + j * 4600, 14200
        hl = max(lu * kkj, 500)                                  # legs drawn long enough to read
        q = [(x0_, y0_ + hl), (x0_, y0_), (x0_ + u['Lb'] * kkj, y0_), (x0_ + u['Lb'] * kkj, y0_ + hl)]
        s1.text(str(u['Lb']), x0_ + u['Lb'] * kkj / 2, y0_ - 80, ST['len'] * 0.8, 'S-DIM', align=TA.TOP_CENTER)
        s1.text(str(lu), x0_ - 120, y0_ + hl / 2, ST['len'] * 0.8, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        s1.text(str(lu), x0_ + u['Lb'] * kkj + 120, y0_ + hl / 2, ST['len'] * 0.8, 'S-DIM', rot=90, align=TA.TOP_CENTER)
        s1.pline(q, 'S-RFT-STIR', 25, r=60)
        s1.ctext(u['mk'], f"{wn}  L={u['L']}", x0_, y0_ - 600, ST['call'] * 0.7, maxw=4300)
        s1.text(f"{u['per']} PER ROW x {n_h} ROWS", x0_, y0_ - 1000, ST['note'], 'S-RFT-TXT', maxw=4300)
    # link + tie
    lx, ly = 22300, 9000
    s1.pline(fillet([(lx, ly + HOOK * 4), (lx, ly), (lx + lw * 4, ly), (lx + lw * 4, ly + HOOK * 4)], 40), 'S-RFT-STIR', 25)
    s1.text(str(lw), lx + lw * 2, ly - 80, ST['len'] * 0.8, 'S-DIM', align=TA.TOP_CENTER)
    s1.text(f'{HOOK} (135 DEG)', lx + lw * 4 + 120, ly + HOOK * 2, ST['len'] * 0.7, 'S-DIM')
    if ml: s1.ctext(ml, f'LINK  L={lw + 2 * HOOK}', lx, ly - 900, ST['call'] * 0.85)
    tx_, ty_ = 28800, 8700
    draw_open_tie(s1, [(0, 0), (tw, 0), (tw, tw), (0, tw)], tx_, ty_, 5, None, rc=12, tail=HOOK, width=25, th=ST['len'] * 0.8)   # opened at the hooks
    s1.ctext(mt, f'CORNER TIE  L={4 * tw + 2 * HOOK}', tx_, ty_ - 900, ST['call'] * 0.85)
    s1.text('HORIZONTAL BARS: U-BARS PER WALL FACE (OUTER + INNER), LEGS ACROSS THE WALL, OVERLAPPING AT THE CORNERS; OUT-TO-OUT LENGTHS. LINKS @%d BOTH WAYS.' % sl,
            22300, 6600, ST['note'], 'S-RFT-TXT', maxw=12000)

    # ================= sheet 2: section through the wall + vertical bars detailed =================
    meta = dict(meta0); meta['title'] = f'CORE NECKS - {name} ON {f["name"]}\nSECTION + BAR DETAILS'
    meta['dwg'] = f"{meta['prefix']}-{name.replace(' ', '')}-{f['name']}-2"
    s2 = Sheet(doc, 0, -(idx + 1) * 32000, meta)
    draw_legend(s2, 21000, 27900)
    s2.text(f'{"STARTER BARS" if starter else "NECK"} {name}  ON  {f["name"]}  - SECTION THROUGH THE WALL', 2000, 27900, ST['name'] * 0.8, 'S-AXIS-TXT')
    top = f['h'] + Hn
    lpv = vw['lp']
    k2 = next(kk_ for kk_ in (4.0, 10 / 3, 2.5, 2.0, 1.6) if kk_ * (f['h'] + Hn + vc['lp'] + 900) <= 20500)
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
    # vertical bars: starters (feet turned into the core, up to T.O.F + lap) + neck bars (T.O.F to T.O.GB + lap)
    xo, xi = CC + dh + vw['d'] / 2, t - CC - dh - vw['d'] / 2
    ofs = 1.6 * vw['d']
    for x, yy_, sg in ((xo, yb, 1), (xi, yb + vw['d'], -1)):
        s2.pline([Q(x + vw['foot'], yy_), Q(x, yy_), Q(x, f['h'] + lpv)], 'S-RFT-TOP', max(vw['d'] * k2, 25), r=3 * vw['d'] * k2)
        if not starter:
            s2.pline([Q(x + sg * ofs, f['h']), Q(x + sg * ofs, top + lpv)], 'S-RFT-BOT', max(vw['d'] * k2, 25))
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
    XD = t + 3300
    if not starter: s2.dim(Q(XD, f['h']), Q(XD, top), Q(XD + 450, f['h']), angle=90, text=str(Hn))
    s2.dim(Q(XD, top), Q(XD, top + lpv), Q(XD + 450, top), angle=90, text=f'LAP {lpv}')
    if not starter: s2.dim(Q(-450, f['h']), Q(-450, f['h'] + lpv), Q(-850, f['h']), angle=90, text=f'LAP {lpv}')
    s2.dim(Q(xo - 160, yb), Q(xo - 160, f['h']), Q(fx0 + 400, yb), angle=90, text=str(emb))
    s2.dim(Q(xi, yb + vw['d']), Q(xi + vw['foot'], yb + vw['d']), Q(xi, yb + 260), text=str(vw['foot']))
    for yy_, lab in ((-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {tpc:+.2f}"),
                     (f['h'], f"T.O.F = T.O.SLAB {tof:+.2f}" if starter else f"T.O.F {tof:+.2f}")) + (() if starter else ((top, f"T.O.GB {tgb:+.2f}"),)):
        xl_ = Q(fx0, 0)[0]
        s2.line((xl_ - 3600, Q(0, yy_)[1]), (xl_ - 150, Q(0, yy_)[1]), 'S-DIM'); s2.text(lab, xl_ - 3600, Q(0, yy_)[1] + 50, 170, 'S-DIM')
    s2.text(f"Ld = {emb} + {vw['foot']} = {emb + vw['foot']} >= {LDN}d = {vw['LD']}  (T{vw['d']});  "
            f"T{vc['d']}: {emb} + {vc['foot']} = {emb + vc['foot']} >= {vc['LD']}", Q(fx0, 0)[0] - 3600, Q(0, -100)[1] - 900, ST['note'], 'S-DIM')
    s2.text('FEET TURNED INTO THE CORE, ON THE BOTTOM MESH', Q(fx0, 0)[0] - 3600, Q(0, -100)[1] - 1250, ST['note'], 'S-DIM')
    if not starter:
        s2.ctext(vw['mkn'], callout(vw['n'], vw['d'], vw['mkn'], vw['Ln'], ct['web'][1], 'V') + '  NECK BARS', Q(t + 300, 0)[0], Q(0, top + lpv * 0.5)[1], ST['call'] * 0.85)
    s2.ctext(vw['mk'], callout(vw['n'], vw['d'], vw['mk'], vw['L'], ct['web'][1], 'V') + '  STARTERS', Q(t + 300, 0)[0],
             Q(0, f['h'] + lpv * 0.5)[1] if not starter else Q(0, top + lpv * 0.5)[1], ST['call'] * 0.85)
    us = hu['SIDE WALL']
    s2.ctext(us['mk'], callout(us['n'], dh, us['mk'], us['L'], sh_, 'H') + '  U-BARS', Q(t + 300, 0)[0], Q(0, f['h'] + Hn * 0.55)[1], ST['call'] * 0.85)
    if ml: s2.ctext(ml, callout(len(links) * rows_l, dl, ml, lw + 2 * HOOK, sl, 'LINK'), Q(t + 300, 0)[0], Q(0, f['h'] + Hn * 0.55)[1] - 600, ST['call'] * 0.85)
    s2.text(f'SECTION THROUGH THE WALL  1:{round(100 / k2)}', Q(t / 2, 0)[0], Q(0, -100)[1] - 1600, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # vertical bars detailed outside (every length)
    for j, (key, ttl) in enumerate((('C', 'BOUNDARY BAR (CORNERS / RETURN ENDS)'), ('W', 'WEB BAR (EACH FACE)'))):
        v = dv[key]
        bx0, by0 = 20500 + j * 6800, 6200
        kb = min(13500 / (max(v['vert'], 0 if starter else emb + v['Ln']) + 600), 3.0)
        B_ = lambda x, y: (bx0 + x * kb, by0 + y * kb)
        fx_ = min(v['foot'] * kb, 3000) / kb
        s2.pline([B_(fx_, 0), B_(0, 0), B_(0, v['vert'])], 'S-RFT-TOP', max(v['d'] * kb, 30), r=3 * v['d'] * kb)
        s2.text(str(v['foot']), *B_(fx_ / 2, -100 / kb), ST['len'], 'S-DIM', align=TA.TOP_CENTER)
        s2.text(str(v['vert']), *B_(-150 / kb, v['vert'] / 2), ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        for yy_, tt in ((emb, f'T.O.F ({emb} IN FOOTING)'), (emb + v['lp'] / 2, f"LAP {v['lp']}")):
            s2.line(B_(-60 / kb, yy_), B_(350 / kb, yy_), 'S-DIM'); s2.text(tt, B_(400 / kb, 0)[0], B_(0, yy_)[1] - 60, ST['note'], 'S-DIM')
        if not starter:                                              # the neck bar beside it, from T.O.F
            nx_ = bx0 + 3400
            N_ = lambda y: (nx_, by0 + (emb + y) * kb)
            s2.pline([N_(0), N_(v['Ln'])], 'S-RFT-BOT', max(v['d'] * kb, 30))
            s2.text(str(v['Ln']), N_(v['Ln'] / 2)[0] - 150, N_(v['Ln'] / 2)[1], ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
            for yy_, tt in ((0, 'T.O.F'), (Hn, f'T.O.GB ({Hn})'), (Hn + v['lp'] / 2, f"LAP {v['lp']}")):
                s2.line((N_(yy_)[0] - 60, N_(yy_)[1]), (N_(yy_)[0] + 300, N_(yy_)[1]), 'S-DIM'); s2.text(tt, N_(yy_)[0] + 340, N_(yy_)[1] - 60, ST['note'] * 0.9, 'S-DIM')
            s2.ctext(v['mkn'], callout(v['n'], v['d'], v['mkn'], v['Ln'], layer='V'), nx_, by0 + (emb + v['Ln']) * kb + 300, ST['call'] * 0.75)
        s2.ctext(v['mk'], callout(v['n'], v['d'], v['mk'], v['L'], layer='V'), bx0, by0 + v['vert'] * kb + 700, ST['call'] * 0.75)
        s2.text(f"L = {v['foot']} + {v['vert']} = {v['L']}", bx0, by0 + v['vert'] * kb + 300, ST['note'], 'S-RFT-TXT')
        s2.text(ttl + ('' if starter else ': STARTER + NECK BAR'), bx0, by0 - 900, ST['panel'] * 0.7, 'S-SEC', maxw=6400)
        s2.text(f"Ld = {emb} + {v['foot']} = {emb + v['foot']} >= {LDN}d = {v['LD']}", bx0, by0 - 1300, ST['note'], 'S-DIM')
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
    meta0['notes'] = project_notes(f'COVER CORE WALLS {CC}.', 'VERTICAL BARS: STARTERS (Ld IN THE FOOTING, FEET INTO THE CORE) + NECK BARS TO T.O.GB + LAP 65d.')
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
