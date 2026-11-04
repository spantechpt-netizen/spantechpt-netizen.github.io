"""Wall necks (load-bearing / retaining walls standing on combined footings or rafts) - one generic sheet per wall type.

    python3 gen_w.py walls.json footings.json

walls.json (project data, read from the plan): [{type, t (mm), Lc (centre-line length, m), at [x, y] (m), poly (mm),
foot (footing name under it, optional)}]. project.json -> wall_necks: {d: 16, foot: 300, s: 200, lap_d: 65,
mesh_d: 18 (bottom mesh of the footing when not known), note: "..."}.
Per type: SECTION through the wall 1:20 (footing VAR, PC, T.O.PC, T.O.GB, vertical bars on both faces, 90-degree foot
on the bottom mesh, lap above T.O.GB), BAR DETAIL (foot + vertical + lap = L), KEY PLAN of the walls of the type,
count = 2 faces x (centre-line length / s + 1) per wall piece; BBS one table per type (draw_bbs_grouped).
Values not given on the drawings (spacing, horizontal bars) are written on the sheet with the RFI number.
"""
import json, math, sys
from gen import new_doc, Sheet, TA, ST, BarList, draw_legend, callout, draw_bbs_grouped, footing_levels, zone_levels, mm, _PRJ as PRJ

FC = PRJ.get('footing_cover', 70)


def draw_wall(doc, idx, wt, pieces, meta, bl):
    W = PRJ.get('wall_necks', {})
    d, foot, s, lapd = W.get('d', 16), W.get('foot', 300), W.get('s', 200), W.get('lap_d', 65)
    t = max(set(p['t'] for p in pieces), key=lambda v: sum(1 for p in pieces if p['t'] == v))
    ZL = zone_levels(None); tgb = ZL['top_gb']
    h_rep = 800
    fl, tpc, tof = footing_levels(h_rep, ZL)
    dm = W.get('mesh_d', 18)
    lp = lapd * d
    v = round((tgb - tpc) * 1000) - (FC + 2 * dm)                # bar foot on the bottom mesh -> T.O.GB
    L = foot + v + lp
    n = sum(2 * (math.ceil(p['Lc'] * 1000 / s) + 1) for p in pieces)
    Ltot = sum(p['Lc'] for p in pieces)
    mk = bl.add(d, ('L', foot, v + lp, 0), L, n, 1, 'V')
    sh = Sheet(doc, 0, -idx * 32000, meta)
    draw_legend(sh, 21000, 27900)
    sh.text(f'WALL NECK {wt}  (t = {t})', 2000, 27900, ST['name'], 'S-AXIS-TXT')
    sh.text(f'{len(pieces)} WALL PIECES, CENTRE-LINE LENGTH {Ltot:.1f} m   T.O.PC {tpc:+.2f}   T.O.GB {tgb:+.2f}   FOOTING / RAFT THICKNESS VAR', 2000, 27100, ST['sub'], 'S-SEC', maxw=18000)
    if W.get('note'): sh.text(W['note'], 2000, 26400, ST['note'], 'S-SEC', maxw=18000)
    # ---- section 1:20 (k = 5)
    k = min(5.0, 17000 / (h_rep + (tgb - tof) * 1000 + lp + 900))
    ox, oy = 9000, 2600
    Q = lambda x, y: (ox + x * k, oy + y * k)
    fw = 2600
    Hn = round((tgb - tof) * 1000)
    sh.pline([Q(-fw / 2 - 100, -100), Q(fw / 2 + 100, -100), Q(fw / 2 + 100, 0), Q(-fw / 2 - 100, 0)], 'S-GB-CONC', 0, True)
    sh.pline([Q(-fw / 2, 0), Q(fw / 2, 0), Q(fw / 2, h_rep), Q(t / 2, h_rep), Q(t / 2, h_rep + Hn + lp + 300)], 'S-GB-CONC')
    sh.pline([Q(-fw / 2, 0), Q(-fw / 2, h_rep), Q(-t / 2, h_rep), Q(-t / 2, h_rep + Hn + lp + 300)], 'S-GB-CONC')
    sh.break_line(Q(-t / 2 - 300, h_rep + Hn + lp + 300), Q(t / 2 + 300, h_rep + Hn + lp + 300))
    sh.pline([Q(-fw / 2 + FC, FC + dm), Q(fw / 2 - FC, FC + dm)], 'S-RFT-BOT', 30)
    yb = FC + 2 * dm
    for sx in (-1, 1):
        x = sx * (t / 2 - 40 - d / 2)                                   # wall cover 40 (panda: walls 30 - 40)
        sh.pline([Q(x + sx * foot, yb), Q(x, yb), Q(x, h_rep + Hn + lp)], 'S-RFT-TOP', max(d * k, 25), r=3 * d * k)
    for yy, lab in ((-100, f'F.L (B.O.PC) {fl:+.2f}'), (0, f'T.O.PC {tpc:+.2f}'), (h_rep, 'T.O.F / T.O.RAFT VAR'), (h_rep + Hn, f'T.O.GB {tgb:+.2f}')):
        sh.line((1300, Q(0, yy)[1]), Q(-fw / 2 - 150, yy), 'S-DIM'); sh.text(lab, 1300, Q(0, yy)[1] + 50, 170, 'S-DIM')
    XD = t / 2 + 1500
    sh.dim(Q(XD, yb), Q(XD, h_rep + Hn), Q(XD + 300, yb), angle=90, text=str(v))
    sh.dim(Q(XD, h_rep + Hn), Q(XD, h_rep + Hn + lp), Q(XD + 300, h_rep + Hn), angle=90, text=f'LAP {lp}')
    sh.dim(Q(-fw / 2, 0), Q(-fw / 2, h_rep), Q(-fw / 2 - 400, 0), angle=90, text='VAR')
    sh.dim(Q(-t / 2, h_rep + Hn + 200), Q(t / 2, h_rep + Hn + 200), Q(-t / 2, h_rep + Hn + 500), text=str(t))
    sh.ctext(mk, callout(n, d, mk, L, s, 'V') + '  BOTH FACES', Q(t / 2 + 250, 0)[0], Q(0, h_rep + Hn * 0.55)[1], ST['call'], maxw=9000)
    sh.text(f'(FOOT {foot} ON THE BOTTOM MESH, UP TO T.O.GB + LAP {lp} = {lapd}d)', Q(t / 2 + 250, 0)[0], Q(0, h_rep + Hn * 0.55)[1] - 400, ST['note'], maxw=9000)
    sh.text('HORIZONTAL BARS AND WALL TIES: PER THE WALL DESIGN (NOT ON THE DRAWINGS - RFI-17)', Q(t / 2 + 250, 0)[0], Q(0, h_rep + Hn * 0.55)[1] - 750, ST['note'], 'S-DIM', maxw=9000)
    sh.text(f'SECTION THROUGH THE WALL {wt} (TYPICAL)', Q(0, 0)[0], Q(0, -100)[1] - 700, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # ---- bar detail
    bx, by = 1800, 17500; kb = min(6500 / (v + lp), 1.6)
    B = lambda x, y: (bx + x * kb, by + y * kb)
    sh.pline([B(foot, 0), B(0, 0), B(0, v + lp)], 'S-RFT-TOP', max(d * kb, 30), r=3 * d * kb)
    sh.text(str(foot), *B(foot / 2, -150 / kb), ST['len'], 'S-DIM', align=TA.TOP_CENTER)
    sh.text(str(v + lp), *B(-160 / kb, (v + lp) / 2), ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
    for yy, tx in ((v, f'T.O.GB ({v} FROM THE FOOT)'), (v + lp / 2, f'LAP {lp}')):
        sh.line(B(-60, yy), B(380 / kb, yy), 'S-DIM'); sh.text(tx, B(420 / kb, 0)[0], B(0, yy)[1] - 60, ST['note'], 'S-DIM')
    sh.ctext(mk, callout(n, d, mk, L, s, 'V'), bx, by + (v + lp) * kb + 700, ST['call'])
    sh.text(f'L = {foot} + {v} + {lp} = {L}', bx, by + (v + lp) * kb + 300, ST['note'], 'S-RFT-TXT')
    sh.text('BAR DETAIL (WALL NECK BAR)', bx, by - 850, ST['panel'], 'S-SEC')
    # ---- key plan of the walls of this type
    xs = [x for p in pieces for x, _ in p['poly']]; ys = [y for p in pieces for _, y in p['poly']]
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    kk = min(11500 / max(1, X1 - X0), 9000 / max(1, Y1 - Y0))
    for p in pieces:
        sh.pline([(23500 + (x - X0) * kk, 13500 + (y - Y0) * kk) for x, y in p['poly']], 'S-GB-CONC', 25, True)
    sh.text(f'KEY PLAN - WALLS {wt} (n = {len(pieces)}, L = {Ltot:.1f} m)', 23500, 13000, ST['panel'], 'S-SEC', align=TA.TOP_LEFT, maxw=12000)
    sh.text(f'COUNT: 2 FACES x (L / {s} + 1) PER WALL PIECE = {n} BARS', 23500, 12400, ST['note'], 'S-SEC', align=TA.TOP_LEFT, maxw=12000)
    return n, L


if __name__ == '__main__':
    walls = json.load(open(sys.argv[1]))
    doc = new_doc(); bl = BarList(); dwgmap = {}; types = {}
    for w in walls:
        if w['type'] != '?': types.setdefault(w['type'], []).append(w)
    for i, (wt, ps) in enumerate(sorted(types.items())):
        meta = dict(PRJ.get('meta', {})); meta['title'] = f'WALL NECKS\n{wt}'; meta['scale'] = 'SEC 1:20'
        bl.cur = wt
        n, L = draw_wall(doc, i, wt, ps, meta, bl)
        dwgmap[wt] = meta.get('dwg_no', '')
        print(wt, len(ps), 'pieces', n, 'bars', L)
    meta['title'] = 'WALL NECKS'
    nb = draw_bbs_grouped(doc, len(types), bl.sorted(), meta, [(f'WALL NECK {wt}  (t = {max(p["t"] for p in ps)})', wt, 1) for wt, ps in sorted(types.items())])
    doc.saveas('out/WALL_NECKS.dxf'); bl.export('out/WALL_NECKS.bbs.json', dwgmap, {wt: 1 for wt in types})   # one element = all walls of the type (pieces differ in length)
    print('sheets', len(types), '+ BBS', nb)
