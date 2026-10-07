"""Strip footing under the walls (ST-01): typical cross section, a plan of a typical stretch with the lap and corner
details, and a BBS per metre run (the strip length is measured on the foundation plan - see plan)."""
import json, math
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, ST, mm, project_notes
PRJ = json.load(open('project.json')); LEV = PRJ.get('levels', {})
C = PRJ.get('footing_cover', 70)


def main(name='ST-01', B=1550, h=600, pcB=1750, n_m=7, d=14, ds=12):
    s = math.floor(1000 / n_m / 5) * 5                    # 7 / m -> 140
    lg = h - 2 * C; lp = 60 * d
    nl = math.ceil((B - 2 * C) / s) + 1                   # longitudinal bars across the width (per layer)
    meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='SEC 1:20 / PLAN 1:50', prefix='SDW-STR-FDN')
    meta.update(PRJ.get('meta', {}))
    meta['notes'] = project_notes('COVER FOOTINGS 70; PLAIN CONCRETE 100.', 'STRIP LENGTH: SEE FOUNDATION PLAN; BBS PER METRE RUN.')
    meta['title'] = f'STRIP FOOTING UNDER WALLS\nREINFORCEMENT - {name}'; meta['dwg'] = f'SDW-STR-FDN-{name}'
    doc = new_doc(); bl = BarList(); sh = Sheet(doc, 0, 0, meta)
    draw_legend(sh, 21000, 27900)
    sh.text(name, 2000, 27900, ST['name'], 'S-AXIS-TXT')
    xc_ = 2000 + len(name) * ST['name'] * 0.9 + 800
    sh.circle(xc_, 28150, 520, 'S-SEC'); sh.text(str(h), xc_, 28150, 380, 'S-SEC', align=TA.MIDDLE_CENTER)
    sh.text(f'PC {pcB}x100   RC {B}x{h}', xc_ + 900, 27950, ST['sub'], 'S-SEC')
    sh.text('STRIP FOOTING UNDER THE WALLS - LENGTH: SEE FOUNDATION PLAN', 2000, 27100, ST['sub'], 'S-SEC')
    # marks (per metre run)
    tB = bl.add(d, ('U', lg, B - 2 * C, lg), B - 2 * C + 2 * lg, n_m, 1, 'B-TR')
    tT = bl.add(d, ('U', lg, B - 2 * C, lg), B - 2 * C + 2 * lg, n_m, 1, 'T-TR')        # top U = bottom U (legs side by side)
    lb = bl.add(d, ('S', 12000), 12000, round(nl * 1000 / (12000 - lp), 2), 1, 'B-LG')
    lt = bl.add(d, ('S', 12000), 12000, round(nl * 1000 / (12000 - lp), 2), 1, 'T-LG')
    sbm = bl.add(ds, ('S', 12000), 12000, round(2 * 1000 / (12000 - 60 * ds), 2), 1, 'SB')
    # ---- typical cross section 1:20 (factor 5 on the 1:100 frame) ----
    k = 5; ox, oy = 3500, 12500
    Q = lambda x, y: (ox + x * k, oy + y * k)
    sh.pline([Q(-100, -100), Q(B + 100, -100), Q(B + 100, 0), Q(-100, 0)], 'S-GB-CONC', 0, True)
    sh.pline([Q(0, 0), Q(B, 0), Q(B, h), Q(0, h)], 'S-GB-CONC', 0, True)
    sh.pline([Q(B / 2 - 150, h), Q(B / 2 - 150, h + 500)], 'S-SEC'); sh.pline([Q(B / 2 + 150, h), Q(B / 2 + 150, h + 500)], 'S-SEC')
    sh.break_line(Q(B / 2 - 300, h + 500), Q(B / 2 + 300, h + 500))
    sh.text('WALL (SEE WALL DETAILS)', *Q(B / 2 + 250, h + 300), 170, 'S-SEC')
    yb = C + d / 2; yt = h - C - d / 2
    xl, xr = C + d / 2, B - C - d / 2
    sh.pline([Q(xl, h - C - 2 * d - 15), Q(xl, yb), Q(xr, yb), Q(xr, h - C - 2 * d - 15)], 'S-RFT-BOT', d * k, r=3 * d * k)
    sh.pline([Q(xl, C + 2 * d + 15), Q(xl, yt), Q(xr, yt), Q(xr, C + 2 * d + 15)], 'S-RFT-TOP', d * k, r=3 * d * k)
    def dot(x, y, dd, lay):
        hh = sh.m.add_hatch(color=7, dxfattribs={'layer': lay}); hh.paths.add_edge_path().add_arc(sh.P(*Q(x, y)), dd / 2 * k, 0, 360)
    xa, xb = xl + d, xr - d
    for j in range(nl):
        x = xa + (xb - xa) * j / (nl - 1)
        dot(x, yb + d, d, 'S-RFT-BOT'); dot(x, yt - d, d, 'S-RFT-TOP')
    xs = C + d + ds / 2 + 2                                       # side bars inside the (one) main U leg
    for x in (xs, B - xs): dot(x, h / 2, ds, 'S-RFT-STIR')
    lines = [(yt, tT, callout(n_m, d, tT, B - 2 * C + 2 * lg, s, 'T-TR') + '  /M', xr - 300),
             (yt - d, lt, callout(nl, d, lt, 12000, s, 'T-LG') + '  CONT.', xa + (xb - xa) * (nl - 2) / (nl - 1)),
             (h / 2, sbm, callout(2, ds, sbm, 12000, None, 'SB') + '  CONT.', B - xs),
             (yb + d, lb, callout(nl, d, lb, 12000, s, 'B-LG') + '  CONT.', xa + (xb - xa) * (nl - 2) / (nl - 1)),
             (yb, tB, callout(n_m, d, tB, B - 2 * C + 2 * lg, s, 'B-TR') + '  /M', xr - 300)]
    for i, (y, mk_, t, xt) in enumerate(sorted(lines, key=lambda l: l[0])):
        ty_ = Q(0, 0)[1] + i * 600 + 200
        sh.line(Q(xt, y), (Q(B, 0)[0] + 900, ty_ + 90), 'S-RFT-TXT'); sh.circle(*Q(xt, y), 25, 'S-RFT-TXT')
        sh.ctext(mk_, t, Q(B, 0)[0] + 1000, ty_, ST['call'])
    sh.dim(Q(0, -100), Q(B, -100), (Q(0, 0)[0], Q(0, -100)[1] - 450), text=str(B))
    sh.dim(Q(0, 0), Q(0, h), (Q(0, 0)[0] - 500, Q(0, 0)[1]), angle=90, text=str(h))
    sh.text(f'COVER {C}', Q(B / 2, 0)[0], Q(0, C / 2)[1], 150, 'S-DIM', align=TA.MIDDLE_CENTER)
    if 'founding' in LEV:
        fl = LEV['founding']
        for yy, lab in ((-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {fl + .1:+.2f}"), (h, f"T.O.F {fl + .1 + h / 1000:+.2f}")):
            sh.line((ox - 2300, Q(0, yy)[1]), (ox - 750, Q(0, yy)[1]), 'S-DIM'); sh.text(lab, ox - 2300, Q(0, yy)[1] + 50, 150, 'S-DIM')
    sh.text(f'TYPICAL CROSS SECTION  {name}  1:20', Q(B / 2, 0)[0], Q(0, -100)[1] - 1000, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # ---- typical stretch on plan 1:50 (factor 2): transverse bars @s, longitudinal bars lapped 60d staggered ----
    k2 = 2; px, py = 2000, 3000; Ls = 6000
    R = lambda x, y: (px + x * k2, py + y * k2)
    sh.pline([R(0, 0), R(Ls, 0), R(Ls, B), R(0, B)], 'S-GB-CONC', 0, True)
    sh.break_line(R(Ls - 10, -200), R(Ls - 10, -200)) if False else None
    x = C
    while x < Ls - C:
        sh.line(R(x, C), R(x, B - C), 'S-RFT-BOT'); x += s
    for j in range(nl):
        yy = C + (B - 2 * C) * j / (nl - 1)
        cut = 2500 if j % 2 == 0 else 3500                       # laps staggered: half the bars lapped at each place
        sh.pline([R(0, yy), R(cut + lp / 2, yy)], 'S-RFT-BOT', 18); sh.pline([R(cut - lp / 2, yy + 15), R(Ls, yy + 15)], 'S-RFT-BOT', 18)
    sh.dim(R(2500 - lp / 2, B + 150), R(2500 + lp / 2, B + 150), R(2500 - lp / 2, B + 400), text=f'LAP {lp}')
    sh.dim(R(3500 - lp / 2, -150), R(3500 + lp / 2, -150), R(3500 - lp / 2, -500), text=f'LAP {lp}')
    sh.dim(R(C, B + 150), R(C + s, B + 150), R(C, B + 900), text=f'@{s}')
    sh.text(f'TYPICAL STRETCH ON PLAN 1:50 - TRANSVERSE BARS @{s}, LONGITUDINAL BARS LAPPED 60d ({lp}), LAPS STAGGERED',
            px, py - 1600, ST['panel'], 'S-SEC', maxw=15000)
    # corner / T-junction note (longitudinal bars run through, outer bars bent round the corner + 60d)
    sh.text('AT CORNERS AND T-JUNCTIONS: OUTER LONGITUDINAL BARS BENT ROUND THE CORNER AND CARRIED 60d BEYOND;', 18000, 7600, ST['note'], 'S-RFT-TXT')
    sh.text('INNER BARS CARRIED TO THE FAR FACE - COVER + 60d LEG. WHERE AN ISOLATED FOOTING MERGES WITH THE STRIP,', 18000, 7250, ST['note'], 'S-RFT-TXT')
    sh.text('THE FOOTING REINFORCEMENT GOVERNS INSIDE THE FOOTING AND THE STRIP BARS ARE LAPPED 60d INTO IT.', 18000, 6900, ST['note'], 'S-RFT-TXT')
    sh.text('BBS PER METRE RUN OF STRIP: MULTIPLY BY THE STRIP LENGTH MEASURED ON THE FOUNDATION PLAN.', 18000, 6400, ST['note'], 'S-RFT-TXT')
    meta['title'] = 'STRIP FOOTING ST-01\nBBS PER METRE RUN'; meta['dwg'] = 'SDW-STR-FDN-ST-01'
    nb = draw_bbs(doc, 1, bl.sorted(), meta)
    doc.saveas('out/STRIP.dxf'); print('strip sheet + BBS', nb)


if __name__ == '__main__':
    main(**PRJ.get('strip', {}))          # project.json -> strip: {name, B, h, pcB, n_m, d}
