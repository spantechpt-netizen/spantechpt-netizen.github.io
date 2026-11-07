"""Combined footings of any outline re-issued on A0 sheets with the gen_raft method (engineer, BLSC 07-11-2026:
"bars not clear, call-outs far from their bars, lengths hard to read; laps: bottom at midspan, top at the supports;
keep the sheet numbers; BBS inside the package").

Every bar row at its real length (cut by the outline at the cover), one call-out ON each group of identical rows,
laps 60d staggered (bottom mesh at midspan, top mesh at the columns, +/- span / 5), U legs, side bars along the
real perimeter, chairs, sections through the columns, edge / lap / chair details, BBS (office A3 format).

cf.json (project data, never in the repository): {name: {name, no, h, cover, leg, poly [[x, y]...] (mm),
cols [{"poly": [[x, y]...]} | [x, y, r]], bot / top {dx, sx, dy, sy}, side {d, s, rows}, chair {d, per_m2, foot, top},
lap_d, stock, nos [sheet numbers of the original issue], levels (optional)}}.
Sheets: 5+ numbers -> one plan per mesh layer and direction (B1, B2, T2, T1), then SECTIONS & DETAILS (side bars,
chairs layout); 3 numbers -> BOTTOM X & Y, TOP X & Y, SECTIONS & DETAILS. Extra sheets (BBS) take the last number
with a letter (10292A, 10292B ...) - to be confirmed by the engineer.
usage: RC_PROJECT=project.json python3 gen_cf_real.py cf.json NAME OUT_PREFIX  -> OUT.dxf, OUT.sheets.json, OUT.bbs.json, OUT.report.txt
"""
import json, math, sys
from shapely.geometry import LineString, Polygon
import gen, gen_raft as GR
from gen import new_doc, BarList, callout, draw_bbs_grouped, unit_mass
from gen_mat import side_pieces

SCALES = (20, 25, 30, 40, 50, 75, 100)


def fit_scale(R, w, h):
    gx0, gy0, gx1, gy1 = Polygon(R.poly).bounds
    return next((v for v in SCALES if (gx1 - gx0) * GR.SC / v <= w and (gy1 - gy0) * GR.SC / v <= h), SCALES[-1])


def set_text(hc):
    """call-out text height on the plans (sheet units): bigger where the rows are far apart on paper."""
    GR.HC = hc
    GR.Plan.ctext_along.__defaults__ = (hc, 'S-RFT-TXT', 110)
    GR.Plan.text_len.__defaults__ = (hc,)


def main():
    data = json.load(open(sys.argv[1])); f = data[sys.argv[2]]; out = sys.argv[3]
    tb = gen.TB
    tpl = __import__('ezdxf').readfile(tb['dxf'])
    f.setdefault('angle', 0); f.setdefault('elem_abbr', 'F')
    R = GR.Raft(f)
    doc = new_doc(); GR.dimstyle(doc)
    if tb.get('style') and tb['style'] not in doc.styles:
        st = tpl.styles.get(tb['style']); doc.styles.add(tb['style'], font=st.dxf.font)
    bl = BarList(); bl.cur = f['name']; rep = []
    meta0 = dict(gen._PRJ.get('meta', {}))
    title1 = 'STRUCTURAL COMBINED FOOTING'
    nos = [str(n) for n in f['nos']]
    sheets = []; si = 0; extra = iter('ABCDEFGHIJKLMNOP')

    def next_no():
        return nos[si] if si < len(nos) else nos[-1] + next(extra)

    def new_sheet(title, scale_txt):
        nonlocal si
        m = dict(meta0); m['title'] = f'{title1}\n{f["name"]} - {title}'; m['scale'] = scale_txt; m['size'] = 'A0'; m['seq'] = next_no()
        sh = GR.A0(doc, 0, -si * 180000, m); sheets.append([0, -si * 180000, GR.A0.W, GR.A0.H, 1189, 841, m['seq']]); si += 1
        GR.copy_legend(sh, tpl, tuple(tb.get('legend_origin', (174052.0, 21856.0))))
        return sh

    meshes = []
    for layer in ('B', 'T'):
        mesh = f['bot'] if layer == 'B' else f['top']
        for axis in ('X', 'Y'):
            tag = (layer + ('1' if axis == 'X' else '2')) if layer == 'B' else (layer + ('2' if axis == 'X' else '1'))
            d, s = (mesh['dx'], mesh['sx']) if axis == 'X' else (mesh['dy'], mesh['sy'])
            meshes.append(GR.build_bars(R, bl, layer, axis, d, s, tag, rep, alt=True))
    by = {M['tag']: M for M in meshes}
    # section lines through the columns nearest the middle: A-A along Y, B-B along X
    cA = min(R.cols, key=lambda c: abs(c[0][0] - (R.pl.bounds[0] + R.pl.bounds[2]) / 2))[0]
    cB = min(R.cols, key=lambda c: abs(c[0][1] - (R.pl.bounds[1] + R.pl.bounds[3]) / 2))[0]
    def span(axis, t):
        g = R.pl.intersection(LineString([(R.pl.bounds[0] - 10, t), (R.pl.bounds[2] + 10, t)]) if axis == 'X' else LineString([(t, R.pl.bounds[1] - 10), (t, R.pl.bounds[3] + 10)]))
        b = g.bounds; return (b[0], b[2]) if axis == 'X' else (b[1], b[3])
    secs = [('A', 'Y', cA[0], span('Y', cA[0])), ('B', 'X', cB[1], span('X', cB[1]))]
    names = {'B1': 'BOTTOM REINFORCEMENT (B1) - BARS ALONG X', 'B2': 'BOTTOM REINFORCEMENT (B2) - BARS ALONG Y',
             'T2': 'TOP REINFORCEMENT (T2) - BARS ALONG X', 'T1': 'TOP REINFORCEMENT (T1) - BARS ALONG Y'}
    paired = len(nos) < 5
    full = (6000, 16000, 201000, 150000)
    halves = [(6000, 16000, 100500, 150000), (106500, 16000, 201000, 150000)]
    if paired:
        scale = max(fit_scale(R, 92000, 128000) for _ in (0,))
        groups = [('B', ['B1', 'B2'], 'BOTTOM REINFORCEMENT (B1 / B2) - BARS ALONG X & Y'), ('T', ['T2', 'T1'], 'TOP REINFORCEMENT (T2 / T1) - BARS ALONG X & Y')]
    else:
        scale = fit_scale(R, 190000, 128000)
        groups = [(t[0], [t], names[t]) for t in ('B1', 'B2', 'T2', 'T1')]
    step_paper = min(M['s'] for M in meshes) / scale                     # mm between rows on paper
    set_text(int(min(2.4, max(1.65, step_paper * 0.42)) * GR.SC))
    for layer, tags, title in groups:
        sh = new_sheet(title, f'1:{scale}')
        for j, tag in enumerate(tags):
            M = by[tag]; area = halves[j] if paired else full
            P = GR.place_plan(sh, R, scale, area)
            P.outline(); P.edge_dims()
            GR.draw_mesh_plan(sh, P, M, R)
            GR.section_marks(sh, P, R, secs)
            sh.text(f"{names[tag]}   ({len(M['bars'])} BARS, {len(M['groups'])} CALL-OUTS)   SCALE 1:{scale}", area[0], 12500, GR.HP * (0.8 if paired else 1), 'S-SEC')
            rep.append(f"{tag}: {len(M['bars'])} bars in {len(M['groups'])} call-out groups, lapped {sum(1 for b in M['bars'] if b['lapped'])}, supports {[round(v) for v in R.supports(M['axis'])]}")
        M = by[tags[0]]
        zt = 'MIDSPAN (+/- SPAN/5)' if layer == 'B' else 'THE COLUMNS (+/- SPAN/5)'
        lapped = any(b['lapped'] for t in tags for b in by[t]['bars'])
        GR.notes(sh, [f"T{M['d']} @{M['s']} {'BOTTOM' if layer == 'B' else 'TOP'} MESH, h = {R.h}, COVER {R.C}: EVERY BAR AT ITS REAL LENGTH TO THE OUTLINE - COVER; U LEGS {R.lg} AT BOTH ENDS ({'UP' if layer == 'B' else 'DOWN'}, TICK AT THE BAR END, SEE DETAIL 1).",
                      (f"LAPS {M['lp']} (60d) AT {zt}, HATCHED; ALTERNATE ROWS STAGGERED (PATTERN A / B, >= 500 APART); THE LAPPED PIECE IS DRAWN BESIDE THE BAR, CIRCLES = LAP ENDS."
                       if lapped else f"NO LAPS: EVERY BAR IN ONE PIECE (<= {R.stock}). IF A LAP IS EVER NEEDED: {M['lp']} (60d) AT {zt}, STAGGERED."),
                      "ONE CALL-OUT PER GROUP OF IDENTICAL ROWS ON ITS MIDDLE BAR (DISTRIBUTION LINE WITH TICKS = THE GROUP); EVERY OTHER BAR ITS OWN MARK."], 6000, 9200)
    # chairs (on the sections sheet), side bars, sections and details
    ch = f['chair']; dch = ch['d']; foot, top = ch['foot'], ch['top']
    db1, db2 = f['bot']['dx'], f['bot']['dy']; dt1, dt2 = f['top']['dx'], f['top']['dy']
    ch_h = int(R.h - 2 * R.C - db1 - db2 - dt1 - dt2)
    chL = int(math.ceil((2 * foot + 2 * ch_h + top) / 10) * 10)
    sp = int(round(1000 / math.sqrt(ch.get('per_m2', 1))))
    f['chairs_best'] = True
    pts = GR.chair_points(R, sp, foot, top, best=True)
    mkch = bl.add(dch, ('CH', foot, ch_h, top), chL, len(pts), 1, 'CH')
    rep.append(f'chairs: {len(pts)} T{dch} H={ch_h} L={chL} @{sp}')
    sd = f['side']; ds = sd['d']; lps = f.get('lap_d', 60) * ds
    ring = R.pl.buffer(-(R.C + max(db1, db2, dt1, dt2) + ds / 2), join_style=2)
    pcs = side_pieces([R.G(*q) for q in ring.exterior.coords], lps, R.stock)
    rows_sb = int(sd.get('rows', 1)); grp = {}
    for pc in pcs: grp.setdefault(pc['key'], []).append(pc)
    pmk = {}
    for key_, lst in grp.items():
        sk = [tuple(map(int, q)) for q in LineString(lst[0]['local']).simplify(100).coords]
        pmk[key_] = bl.add(ds, ('OPEN',) + tuple(sk), lst[0]['L'], rows_sb * len(lst), 1, 'SB')
    rep.append(f'side bars: {rows_sb} row x {len(pcs)} pieces ' + ', '.join(str(p['L']) for p in pcs))
    set_text(330)
    GR.draw_sections_sheet(new_sheet('SECTIONS, DETAILS, SIDE BARS, CHAIRS', 'AS SHOWEN'), R, f, meshes, secs, pcs, pmk, grp, rows_sb, ds, lps,
                           (mkch, len(pts), chL, ch_h, foot, top, dch, sp), rep)
    # BBS: office A3 format, one table for the footing, then the summary
    first = math.ceil(si * 180000 / 32000) + 1
    bbs_nos = []
    class BS(gen.Sheet):
        def __init__(self, doc_, ox, oy, m):
            m = dict(m); m['seq'] = next_no(); bbs_nos.append(m['seq']); super().__init__(doc_, ox, oy, m)
    meta = dict(meta0); meta['title'] = f'{title1}\n{f["name"]}'; meta['size'] = 'A3'; meta['scale'] = 'N.T.S'
    def bump():
        nonlocal si; si += 1
    class BS2(BS):
        def __init__(self, doc_, ox, oy, m):
            super().__init__(doc_, ox, oy, m); bump()
    nb = draw_bbs_grouped(doc, first, bl.sorted(), meta, [(f"{f['name']}  (NO={f['no']})", f['name'], f['no'])], Sheet_=BS2)
    for i in range(nb): sheets.append([0, -(first + i) * 32000, 42000, 29700, 420, 297, bbs_nos[i]])
    doc.saveas(out + '.dxf')
    json.dump(sheets, open(out + '.sheets.json', 'w'))
    bl.export(out + '.bbs.json', {f['name']: ''}, {f['name']: f['no']})
    tot = sum(r['n_in'] * r['n_el'] * r['L'] / 1000 * unit_mass(r['d']) for r in bl.sorted())
    rep.append(f'sheets {[s_[6] for s_ in sheets]}; plan scale 1:{scale}; marks {len(bl.rows)}, steel {tot:,.1f} kg')
    open(out + '.report.txt', 'w').write('\n'.join(rep) + '\n')
    print('\n'.join(rep))


if __name__ == '__main__':
    main()
