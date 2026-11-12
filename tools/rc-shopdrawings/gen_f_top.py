"""One drawn bar set of a footing re-issued to the footing's real outline (engineer, BLSC 07-11-2026, F1 / F2:
"complete only the reinforcement shown, same drawing method, lengths and distribution to the real dimensions of
each footing; NO other bar, mesh or direction may be added").

The consultant shows one bar (shape + diameter + spacing + layer) in one direction. Every row of that direction is
cut by the outline at the cover; the main part takes the real length (floor 10), the end parts keep the drawn values
(e.g. 650 at one end, 610 + 600 at the other). Every row drawn, one call-out per group of identical rows on its
bar, the drawn shape developed on the first bar as in the original, a bar detail, BBS (office A3 format).

ft.json (project data, never in the repository): {name: {name, no, poly [[x, y]...] (mm, as drawn), cover, d, s,
axis "X" | "Y", tag (layer, e.g. T2), ends {"lo": [parts at the low-coordinate end], "hi": [...]}, nos [sheet no.]}}
usage: RC_PROJECT=project.json python3 gen_f_top.py ft.json NAME OUT_PREFIX
"""
import json, math, sys
from shapely.geometry import Polygon
import gen, gen_raft as GR
from gen import new_doc, BarList, callout, draw_bbs_grouped, unit_mass, TA
from gen_cf_real import fit_scale, set_text


def shape_pts(main, lo, hi):
    """developed sketch (main bar horizontal, hi end on the left): first end part down, second part turned outward."""
    pts = [(0, 0), (main, 0)]
    if hi:
        pts.insert(0, (0, -hi[0]))
        if len(hi) > 1: pts.insert(0, (-hi[1], -hi[0]))
    if lo:
        pts.append((main, -lo[0]))
        if len(lo) > 1: pts.append((main + lo[1], -lo[0]))
    return pts


def main():
    data = json.load(open(sys.argv[1])); f = data[sys.argv[2]]; out = sys.argv[3]
    tb = gen.TB
    tpl = __import__('ezdxf').readfile(tb['dxf'])
    f.update(h=1000, leg=0, angle=0, cols=[])
    R = GR.Raft(f)
    doc = new_doc(); GR.dimstyle(doc)
    if tb.get('style') and tb['style'] not in doc.styles:
        st = tpl.styles.get(tb['style']); doc.styles.add(tb['style'], font=st.dxf.font)
    bl = BarList(); bl.cur = f['name']; rep = []
    d, s, axis, tag = f['d'], f['s'], f['axis'], f['tag']
    lo, hi = f['ends'].get('lo', []), f['ends'].get('hi', [])
    rows, step = R.rows(axis, s)
    bars = []
    for i, t, segs in rows:
        for j, (a, b) in enumerate(segs):
            st = int(math.floor((b - a) / 10) * 10); m = (a + b) / 2
            pts = shape_pts(st, lo, hi)
            L = st + sum(lo) + sum(hi)
            mk = bl.add(d, ('OPEN',) + tuple(pts), L, 1, 1, tag)
            bars.append(dict(row=i, t=t, a=m - st / 2, b=m + st / 2, st=st, T=L, seg=j, lapped=False,
                             pcs=[dict(t0=0, t1=L, L=L, shp=None, mark=mk, u0=m - st / 2, u1=m + st / 2)]))
    groups = []
    for br in bars:
        g = next((q for q in reversed(groups) if q[-1]['row'] == br['row'] - 1 and q[-1]['pcs'][0]['mark'] == br['pcs'][0]['mark']
                  and abs(q[-1]['a'] - br['a']) <= 15), None)
        if g: g.append(br)
        else: groups.append([br])
    M = dict(bars=bars, groups=groups, step=step, lp=60 * d, zones=[], warn=0, d=d, s=s, tag=tag, layer=tag[0], axis=axis)
    scale = fit_scale(R, 150000, 120000)
    set_text(int(min(2.4, max(1.65, step / scale * 0.42)) * GR.SC))
    m = dict(gen._PRJ.get('meta', {})); m['title'] = f'STRUCTURAL COMBINED FOOTING\n{f["name"]} - TOP REINFORCEMENT ({tag}) - BARS ALONG {axis}'
    m['scale'] = f'1:{scale}'; m['size'] = 'A0'; m['seq'] = str(f['nos'][0])
    sh = GR.A0(doc, 0, 0, m); sheets = [[0, 0, GR.A0.W, GR.A0.H, 1189, 841, m['seq']]]
    GR.copy_legend(sh, tpl, tuple(tb.get('legend_origin', (174052.0, 21856.0))))
    P = GR.place_plan(sh, R, scale, (6000, 16000, 156000, 150000))
    P.outline(); P.edge_dims()
    GR.draw_mesh_plan(sh, P, M, R)
    # the drawn shape developed on the first bar (as on the original sheet): end parts turned into the plan
    br = bars[0]; Q = (lambda u, v: P.SL(v, u)) if axis == 'Y' else (lambda u, v: P.SL(u, v))
    lay = 'S-RFT-TOP' if tag[0] == 'T' else 'S-RFT-BOT'
    for end, parts, sg in (('hi', hi, 1), ('lo', lo, -1)):
        if not parts: continue
        u0 = br['b'] if end == 'hi' else br['a']
        p1 = Q(u0, br['t']); p2 = Q(u0, br['t'] + parts[0]); pl = [p1, p2]
        if len(parts) > 1: pl.append(Q(u0 + sg * parts[1], br['t'] + parts[0]))
        sh.pline(pl, lay, 55, r=3 * d * P.k)
        for a_, b_, v in zip(pl, pl[1:], parts):
            sh.text(str(v), (a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2 + 200, GR.HS * 1.3, 'S-DIM', align=TA.BOTTOM_CENTER,
                    rot=0 if abs(a_[1] - b_[1]) < 1 else 90)
    # bar detail (the shape with every part, main part = real length of each row)
    bx, by_ = 165000, 120000
    sk = shape_pts(4000, lo, hi); kk = 4.0
    X = lambda p: (bx + (p[0] - min(q[0] for q in sk)) * kk, by_ + (p[1] - min(q[1] for q in sk)) * kk)
    sh.pline([X(p) for p in sk], lay, 60, r=3 * d * kk)
    names = ['MAIN = REAL LENGTH OF THE ROW' if math.dist(a, b) == 4000 else str(int(round(math.dist(a, b)))) for a, b in zip(sk, sk[1:])]
    for a, b, nm in zip(sk, sk[1:], names):
        qa, qb = X(a), X(b)
        sh.text(nm, (qa[0] + qb[0]) / 2 + (0 if abs(qa[1] - qb[1]) < 1 else -250), (qa[1] + qb[1]) / 2 + (250 if abs(qa[1] - qb[1]) < 1 else 0),
                GR.HS * 1.4, 'S-DIM', rot=0 if abs(qa[1] - qb[1]) < 1 else 90, align=TA.BOTTOM_CENTER)
    sh.text(f'BAR DETAIL - T{d} @{s} -{tag} (AS THE DRAWN BAR)', bx, by_ - 2500, GR.HP * 0.8, 'S-SEC')
    sh.text(f'L = {" + ".join(str(v) for v in hi)}{" + " if hi else ""}MAIN{" + " if lo else ""}{" + ".join(str(v) for v in lo)}; MAIN = ROW LENGTH TO THE OUTLINE - 2 x COVER {R.C}.',
            bx, by_ - 3700, GR.HN, 'S-RFT-TXT', maxw=60000)
    sh.text(f"{f['name']} - TOP REINFORCEMENT ({tag}) - BARS ALONG {axis}   ({len(bars)} BARS, {len(groups)} CALL-OUTS)   SCALE 1:{scale}", 6000, 12500, GR.HP, 'S-SEC')
    GR.notes(sh, [f"ONLY THE BAR SET SHOWN ON THE APPROVED DRAWING: T{d} @{s} -{tag} ALONG {axis}. NO OTHER MESH, DIRECTION OR BAR IS ADDED.",
                  f"EVERY ROW AT ITS REAL LENGTH: MAIN PART = OUTLINE - COVER {R.C} AT BOTH ENDS (FLOOR 10); END PARTS AS DRAWN ({'/'.join(map(str, hi))} AT THE UPPER END, {'/'.join(map(str, lo))} AT THE LOWER END).",
                  "ONE CALL-OUT PER GROUP OF IDENTICAL ROWS ON ITS BAR; EVERY OTHER BAR ITS OWN MARK (SEE BBS). THE END PARTS ARE SHOWN DEVELOPED ON THE FIRST BAR."], 6000, 9200)
    rep.append(f"{f['name']}: {len(bars)} bars {tag} along {axis} @{round(step, 1)}, {len(groups)} call-out groups, lengths {min(b['T'] for b in bars)}..{max(b['T'] for b in bars)}")
    si = 1; extra = iter('ABCDEFGHIJKLMNOP'); bbs_nos = []
    class BS(gen.Sheet):
        def __init__(self, doc_, ox, oy, m_):
            m_ = dict(m_); m_['seq'] = str(f['nos'][0]) + next(extra); bbs_nos.append(m_['seq']); super().__init__(doc_, ox, oy, m_)
    meta = dict(gen._PRJ.get('meta', {})); meta['title'] = f'STRUCTURAL COMBINED FOOTING\n{f["name"]}'; meta['size'] = 'A3'; meta['scale'] = 'N.T.S'
    first = 7
    nb = draw_bbs_grouped(doc, first, bl.sorted(), meta, [(f"{f['name']}  (NO={f['no']}) - {tag} ONLY", f['name'], f['no'])], Sheet_=BS)
    for i in range(nb): sheets.append([0, -(first + i) * 32000, 42000, 29700, 420, 297, bbs_nos[i]])
    doc.saveas(out + '.dxf'); json.dump(sheets, open(out + '.sheets.json', 'w'))
    bl.export(out + '.bbs.json', {f['name']: ''}, {f['name']: f['no']})
    tot = sum(r['n_in'] * r['n_el'] * r['L'] / 1000 * unit_mass(r['d']) for r in bl.sorted())
    rep.append(f'sheets {[s_[6] for s_ in sheets]}; scale 1:{scale}; marks {len(bl.rows)}, steel {tot:,.1f} kg')
    open(out + '.report.txt', 'w').write('\n'.join(rep) + '\n'); print('\n'.join(rep))


if __name__ == '__main__':
    main()
