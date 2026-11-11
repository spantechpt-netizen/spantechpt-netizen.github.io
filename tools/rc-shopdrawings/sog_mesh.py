"""Slab on grade between the grade beams (engineer, RFI A5-09 answer, 11-11-2026): every panel between the GB faces,
top of S.O.G = top of GB, thickness 150, ONE bottom mesh T10@150 (main + distribution bars only), bars stop 50 from
the GB faces, bottom cover 50, laps 60d. One sheet with the X bars, one with the Y bars, each with its own BBS.
Called from gen_gbsec.main when cfg 'sog_mesh' is set:
  sog_mesh {d, s, t, cover_gb, cover_bot, lap_d, sheets [no_x, no_y], exclude [[x, y] points inside panels with no
  S.O.G (ramp)], exclude_note [...], offset_x [dx, dy], offset_y [dx, dy], keep_layers [...], window [x0, y0, x1, y1],
  scale, bbs_k}
Model space: each plan at real size (mm), shifted by its offset; BBS tables in model space too, all shown on the
sheets through viewports (engineer: "BBS inside the model, then in the layout like the sections")."""
import math, collections
from shapely.geometry import box, Point, LineString, Polygon
from shapely.ops import unary_union


def panels(lines, gap=60):
    R = []
    for l in lines:
        w = l['w']
        R.append(box(l['a'], l['c'] - w / 2, l['b'], l['c'] + w / 2) if l['o'] == 'H' else box(l['c'] - w / 2, l['a'], l['c'] + w / 2, l['b']))
        for q in l['sup']:
            if 'x0' in q: R.append(box(q['x0'], q['y0'], q['x1'], q['y1']))
    U = unary_union(R).buffer(gap, join_style=2).buffer(-gap, join_style=2)
    big = max(getattr(U, 'geoms', [U]), key=lambda g: g.area)
    rest = Polygon(big.exterior).difference(U)
    return U, [g for g in getattr(rest, 'geoms', [rest]) if g.geom_type == 'Polygon' and g.area > 0.5e6]


def bars_of(pg, axis, s, cov):
    """bars along x (axis X, spaced in y) or along y, inside the panel shrunk by the cover to the GB faces"""
    ins = pg.buffer(-cov, join_style=2)
    if ins.is_empty: return []
    x0, y0, x1, y1 = ins.bounds
    a0, a1 = (y0, y1) if axis == 'X' else (x0, x1)
    n = int(math.floor((a1 - a0) / s)) + 1
    off = (a1 - a0 - (n - 1) * s) / 2
    out = []
    for k in range(n):
        u = a0 + off + k * s
        ln = LineString([(x0 - 10, u), (x1 + 10, u)]) if axis == 'X' else LineString([(u, y0 - 10), (u, y1 + 10)])
        g = ln.intersection(ins)
        for seg in (getattr(g, 'geoms', None) or [g]):
            if seg.is_empty or seg.length < 300: continue
            p, q = seg.coords[0], seg.coords[-1]
            a, b = (min(p[0], q[0]), max(p[0], q[0])) if axis == 'X' else (min(p[1], q[1]), max(p[1], q[1]))
            out.append(dict(u=u, a=a, b=b))
    return out


def pieces_of(L, lap, stock=12000):
    """a bar longer than the stock: equal pieces lapped"""
    if L <= stock: return [L]
    n = math.ceil((L - lap) / (stock - lap))
    p = int(math.ceil((L + (n - 1) * lap) / n / 10) * 10)
    return [p] * n


def groups_of(P, axis, s, cov):
    """per panel: neighbouring bars with the same length and start = one group (drawn once, with its range)"""
    out = []
    for pi, p in enumerate(P):
        cur = None
        for b in sorted(bars_of(p, axis, s, cov), key=lambda b: (round(b['a'] / 50), int(round((b['b'] - b['a']) / 10)), b['u'])):
            L = int(round((b['b'] - b['a']) / 10) * 10)
            key = (L, round(b['a'] / 50))
            if cur and cur['key'] == key and abs(b['u'] - cur['bs'][-1]['u'] - s) < 1: cur['bs'].append(b)
            else:
                cur = dict(key=key, L=L, bs=[b], panel=pi); out.append(cur)
    return out


class _Ln:                                                              # what gen_gbsec.draw_bbs reads of a "line"
    def __init__(self, marks): self.marks = marks; self.w = self.h = 0; self.top = 0


def build(doc, msp, LJ, C, new_sheet, report, src, clean_copy, G):
    TA = G['TA']; draw_bbs = G['draw_bbs']; BBS_COLS = G['BBS_COLS']; TXT_STYLE = G['TXT_STYLE']; LV = G['LV']; gbcall = G['gbcall']
    M = C['sog_mesh']; d, s, t = M.get('d', 10), M.get('s', 150), M.get('t', 150)
    cov, covb, lapd = M.get('cover_gb', 50), M.get('cover_bot', 50), M.get('lap_d', 60); lap = lapd * d
    top = C.get('levels', {}).get('top_gb', 850)
    for nm, col in (('SOG-PANEL', 3), ('SOG-TXT', 7), ('SOG-SEC', 7)):
        if nm not in doc.layers: doc.layers.add(nm, color=col)
    lines = [l for pn in C.get('plan_marks', []) for l in LJ[pn]]
    U, P = panels(lines)
    excl = [p for p in P if any(p.contains(Point(*q)) for q in M.get('exclude', []))]
    P = [p for p in P if p not in excl]
    P.sort(key=lambda p: (-p.centroid.y, p.centroid.x))
    report.append(f'S.O.G panels: {len(P)} ({sum(p.area for p in P) / 1e6:,.1f} m2), excluded {len(excl)}')
    win = M['window']; tabs = []
    from ezdxf import bbox as _bb
    keep = []                                                           # background: grid, beams, columns (no texts / dims)
    for e in src.modelspace():
        if e.dxf.layer not in M['keep_layers'] or e.dxftype() in ('VIEWPORT', 'DIMENSION', 'HATCH', 'TEXT', 'MTEXT'): continue
        try: b = _bb.extents([e], fast=True)
        except Exception: continue
        if b.has_data and win[0] <= (b.extmin.x + b.extmax.x) / 2 <= win[2] and win[1] <= (b.extmin.y + b.extmax.y) / 2 <= win[3]: keep.append(e)
    K = M.get('bbs_k', 0.016)
    nxt = max(set(C.get('_bbs_used', [])) | set(M['sheets'])) + 1
    BXM = M.get('bbs_model', [win[2] + 20000, win[1]])
    sc = M.get('scale', 100); th = 2.4 * sc                              # call-out text: 2.4 mm on the sheet
    mark0 = 1; summary = []
    for si, axis in enumerate(('X', 'Y')):
        dx, dy = M['offset_x'] if axis == 'X' else M['offset_y']
        Q = lambda x, y, dx=dx, dy=dy: (x + dx, y + dy)
        n0 = len(msp); clean_copy(doc, src, keep, msp)
        for e in list(msp)[n0:]:
            try: e.translate(dx, dy, 0); e.dxf.color = 8
            except Exception: pass
        for p in P:
            msp.add_lwpolyline([Q(*q) for q in p.exterior.coords], close=True, dxfattribs={'layer': 'SOG-PANEL'})
        if excl:
            for p in excl:
                h = msp.add_hatch(color=8, dxfattribs={'layer': 'SOG-PANEL'}); h.set_pattern_fill('ANSI37', scale=150)
                h.paths.add_polyline_path([Q(*q) for q in p.exterior.coords][:-1], is_closed=True)
            c = max(excl, key=lambda p: p.area).representative_point()
            for j, s2 in enumerate(M.get('exclude_note', ['NO S.O.G'])):
                msp.add_text(s2, height=th * 1.1, rotation=90, dxfattribs={'layer': 'SOG-TXT', 'color': 1, 'style': TXT_STYLE}).set_placement(Q(c.x + (j - 0.5) * th * 1.8, c.y), align=TA.MIDDLE_CENTER)
        grs = groups_of(P, axis, s, cov)
        marks = {}
        for g in grs:
            g['pcs'] = pieces_of(g['L'], lap)
            for pl in sorted(set(g['pcs'])):
                m = marks.setdefault(pl, dict(d=d, shape='00', dims=[('A', pl)], L=pl, n=0))
                m['n'] += g['pcs'].count(pl) * len(g['bs'])
        rows = sorted(marks.values(), key=lambda m: -m['L'])
        for i, m in enumerate(rows): m['mark'] = mark0 + i
        mark0 += len(rows)
        boxes = []
        for g in grs:
            bs = g['bs']; mid = bs[len(bs) // 2]; u0, u1, um = bs[0]['u'], bs[-1]['u'], mid['u']; a, b_ = mid['a'], mid['b']
            P1, P2 = (Q(a, um), Q(b_, um)) if axis == 'X' else (Q(um, a), Q(um, b_))
            msp.add_lwpolyline([P1, P2], dxfattribs={'layer': 'GB-RFT-BOT', 'lineweight': 50})
            for k in range(1, len(g['pcs'])):                          # lap zones marked on the bar
                st = a + k * (g['pcs'][0] - lap)
                z = (Q(st, um), Q(st + lap, um)) if axis == 'X' else (Q(um, st), Q(um, st + lap))
                msp.add_lwpolyline(list(z), dxfattribs={'layer': 'GB-LAP', 'const_width': 70})
            if len(bs) > 1:                                             # the range of the group, ticks at the end bars
                f_ = 0.12
                R1, R2 = (Q(a + (b_ - a) * f_, u0), Q(a + (b_ - a) * f_, u1)) if axis == 'X' else (Q(u0, a + (b_ - a) * f_), Q(u1, a + (b_ - a) * f_))
                msp.add_line(R1, R2, dxfattribs={'layer': 'GB-DIM'})
                for e2 in (R1, R2): msp.add_line((e2[0] - th * 0.3, e2[1] - th * 0.3), (e2[0] + th * 0.3, e2[1] + th * 0.3), dxfattribs={'layer': 'GB-DIM'})
            mk = sorted({marks[pl]['mark'] for pl in g['pcs']})
            txt = gbcall(len(bs), d, g['pcs'][0] if len(g['pcs']) > 1 else g['L'], s)
            if len(g['pcs']) > 1: txt += f" x {len(g['pcs'])} PCS (LAP {lap})"
            # hexagon + text centred on the bar, just above it (rotated with the Y bars); slid along the bar if taken
            Lt = (len(txt) * 0.78 + 2.4) * th
            for f in (0.5, 0.35, 0.65, 0.25, 0.75):
                cm = (P1[0] + (P2[0] - P1[0]) * f, P1[1] + (P2[1] - P1[1]) * f)
                bx = (cm[0] - Lt / 2, cm[1] + 30, cm[0] + Lt / 2, cm[1] + 30 + th * 1.3) if axis == 'X' else (cm[0] - 30 - th * 1.3, cm[1] - Lt / 2, cm[0] - 30, cm[1] + Lt / 2)
                if not any(not (bx[2] < q[0] or bx[0] > q[2] or bx[3] < q[1] or bx[1] > q[3]) for q in boxes): break
            boxes.append(bx)
            rot = 0 if axis == 'X' else 90
            hx = (bx[0] + th * 0.9, (bx[1] + bx[3]) / 2) if axis == 'X' else ((bx[0] + bx[2]) / 2, bx[1] + th * 0.9)
            R_ = th * 0.75
            msp.add_lwpolyline([(hx[0] + R_ * math.cos(math.radians(60 * j + rot)), hx[1] + R_ * math.sin(math.radians(60 * j + rot))) for j in range(6)], close=True, dxfattribs={'layer': 'GB-TXT'})
            msp.add_text('/'.join(f'{v:02d}' for v in mk), height=th * 0.55 if len(mk) == 1 else th * 0.4, rotation=rot, dxfattribs={'layer': 'GB-TXT', 'style': TXT_STYLE}).set_placement(hx, align=TA.MIDDLE_CENTER)
            tp = (bx[0] + th * 2.0, (bx[1] + bx[3]) / 2) if axis == 'X' else ((bx[0] + bx[2]) / 2, bx[1] + th * 2.0)
            msp.add_text(txt, height=th, rotation=rot, dxfattribs={'layer': 'GB-TXT', 'style': TXT_STYLE}).set_placement(tp, align=TA.MIDDLE_LEFT)
        nb = sum(len(g['bs']) for g in grs)
        report.append(f'S.O.G {axis}: {nb} bars in {len(grs)} groups, {len(rows)} marks')
        # ---- the BBS of this direction in model space (pages of the sheet height)
        ln = _Ln(rows); W = sum(w for _, w in BBS_COLS); rh = 950
        wpl = (M['plan_window'][2] - M['plan_window'][0]) / sc
        side = 14 + wpl + 14 + W * K <= M.get('title_x', 715)          # BBS beside the plan, else on its own sheets
        per = max(5, int(((560 - 150 if side else 560) / K - 900 - 1700 - 1500) / rh))
        chunks = [rows[i:i + per] for i in range(0, len(rows), per)]
        bx0, by0 = BXM[0] + si * 30000, BXM[1]
        tabs_axis = []
        for ci, ch in enumerate(chunks):
            yb = by0 - ci * (600 / K)
            h_, tot = draw_bbs(msp, bx0, yb, _Ln(ch), 'BOTTOM MESH', f'S.O.G {axis}', k=1.0, title=f"BBS - S.O.G {axis}-DIRECTION BARS (T{d}@{s} BOTTOM, {t} THK)" + (f" - PART {ci + 1}/{len(chunks)}" if len(chunks) > 1 else ''))
            summary.append((axis, tot)); tabs_axis.append((bx0, yb, h_))
        # ---- the sheet: plan viewport + typical section + BBS viewport(s)
        no = M['sheets'][si]
        sh_ = dict(C['bbs_fields']); sh_.update(tab=f"{C.get('tab_prefix', '')}{no} S.O.G {axis}", t2=f'SLAB ON GRADE - {axis}-DIRECTION REINFORCEMENT', seq=str(no), dwg=C['bbs_dwg'].format(no=no, rev=sh_.get('rev', '00')))
        lay, _ = new_sheet(sh_); tabs.append(sh_['tab'])
        x0, y0, x1, y1 = M['plan_window']; w, h = (x1 - x0) / sc, (y1 - y0) / sc
        cx, cy = 14 + w / 2, 594 - 14 - h / 2
        v = lay.add_viewport(center=(cx, cy), size=(w, h), view_center_point=((x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy), view_height=h * sc); v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        lay.add_text(f'S.O.G - {axis}-DIRECTION BARS (BOTTOM MESH T{d}@{s})   SCALE 1:{sc}', height=3.5, dxfattribs={'layer': 'GB-TITLE', 'style': TXT_STYLE}).set_placement((14, 594 - 14 - h - 7))
        # BBS (first chunk) right of the plan
        xb = 14 + w + 14; yt = 594 - 14
        bxm, bym, hh = tabs_axis[0]
        Wp, Hp = W * K, (hh * K if side else 0)
        if side: v = lay.add_viewport(center=(xb + Wp / 2, yt - Hp / 2), size=(Wp + 4, Hp + 4), view_center_point=(bxm + W / 2, bym - hh / 2), view_height=(Hp + 4) / K)
        if side: v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        # notes + typical section under the BBS
        notes = [f'NOTES - SLAB ON GRADE ({axis}-DIRECTION SHEET):',
                 f'1. S.O.G {t} THICK BETWEEN THE GRADE BEAMS, T.O.S.O.G = T.O.GB {LV(top)} ({M.get("ref_note", "RFI A5-09 ANSWER")}).',
                 f'2. ONE BOTTOM MESH T{d}@{s} BOTH WAYS (X BARS ON SHEET {M["sheets"][0]}, Y BARS ON SHEET {M["sheets"][1]}).',
                 f'3. BARS STOP {cov} FROM THE GRADE BEAM FACES; BOTTOM COVER {covb}.',
                 f'4. BARS LONGER THAN 12000: EQUAL PIECES LAPPED {lap} ({lapd}d), LAP ZONES MARKED ON THE BAR.',
                 '5. EACH CALL-OUT = ONE GROUP OF EQUAL BARS; THE TICKED LINE = THE RANGE OF THE GROUP.',
                 '6. ' + M.get('exclude_txt', 'HATCHED AREA: NO S.O.G.'),
                 '7. DIMENSIONS / LENGTHS IN mm, LEVELS IN m.']
        yn = yt - Hp - (12 if side else 16)
        for j, s2 in enumerate(notes):
            lay.add_text(s2, height=2.6 if j == 0 else 2.3, dxfattribs={'layer': 'GB-TITLE', 'style': TXT_STYLE}).set_placement((xb, yn - j * 4.4))
        # typical section (model, real size) shown at 1:20 under the notes
        sx, sy = BXM[0] + si * 30000, BXM[1] + 6000
        _section(msp, sx, sy, t, d, s, cov, covb, top, axis, TA, TXT_STYLE, LV, G, M.get('backfill'))
        s2c = 20; ww, hh2 = 3800 / s2c, 1300 / s2c
        ys = yn - len(notes) * 4.4 - 6
        if ys - hh2 > 30:
            v = lay.add_viewport(center=(xb + ww / 2, ys - hh2 / 2), size=(ww, hh2), view_center_point=(sx + 1700, sy - 330), view_height=hh2 * s2c); v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
            lay.add_text(f'TYPICAL SECTION GB / S.O.G   SCALE 1:{s2c}', height=3.0, dxfattribs={'layer': 'GB-TITLE', 'style': TXT_STYLE}).set_placement((xb, ys - hh2 - 6))
        # BBS overflow: own sheets
        rest = list(range(1 if side else 0, len(tabs_axis))); extra = []
        ncol = max(1, int((M.get('title_x', 715) - 14) // (W * K + 14)))     # BBS parts side by side on a BBS sheet
        for gi in range(0, len(rest), ncol):
            no2 = nxt; nxt += 1; extra.append(no2)
            sh2 = dict(C['bbs_fields']); sh2.update(tab=f"{C.get('tab_prefix', '')}{no2} S.O.G {axis} BBS", t2=f'SLAB ON GRADE - {axis}-DIRECTION BBS', seq=str(no2), dwg=C['bbs_dwg'].format(no=no2, rev=sh2.get('rev', '00')))
            lay2, _ = new_sheet(sh2); tabs.append(sh2['tab'])
            for j, ci in enumerate(rest[gi:gi + ncol]):
                bxm, bym, hh = tabs_axis[ci]; Hp2 = hh * K; x2 = 14 + j * (W * K + 14)
                v = lay2.add_viewport(center=(x2 + W * K / 2, 580 - Hp2 / 2), size=(W * K + 4, Hp2 + 4), view_center_point=(bxm + W / 2, bym - hh / 2), view_height=(Hp2 + 4) / K); v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        if not side:
            lay.add_text(f'BBS OF THE {axis} BARS: SHEET {", ".join(map(str, extra))}', height=3.0, dxfattribs={'layer': 'GB-TITLE', 'style': TXT_STYLE}).set_placement((xb, 594 - 14 - 4))
        report.append(f'S.O.G {axis}: sheet {no}' + (f' + BBS sheets {extra}' if extra else ''))
    tot = sum(sum(t_.values()) for _, t_ in summary)
    report.append(f'S.O.G steel: {tot:,.1f} kg')
    C['_sog_total'] = tot
    return tabs


def _section(msp, x, y, t, d, s, cov, covb, top, axis, TA, TXT_STYLE, LV, G, backfill=None):
    """typical section: GB 200 x 700 cut, S.O.G t thick on both sides at the GB top, bottom mesh, the 50 gaps"""
    gb_w, gb_h = 200, 700; L = 1400
    A = lambda u, v: (x + u, y + v)                               # u along the section, v up from the S.O.G top (0)
    def pl(pts, layer='SOG-SEC', closed=False, w=0):
        e = msp.add_lwpolyline([A(*p) for p in pts], dxfattribs={'layer': layer, 'const_width': w}); e.closed = closed; return e
    def tx(s_, u, v, h=60, al=TA.BOTTOM_LEFT, layer='SOG-TXT'):
        msp.add_text(s_, height=h, dxfattribs={'layer': layer, 'style': TXT_STYLE}).set_placement(A(u, v), align=al)
    g0 = L; g1 = L + gb_w
    pl([(g0, 0), (g1, 0), (g1, -gb_h), (g0, -gb_h)], closed=True)
    pl([(0, 0), (g0, 0)]); pl([(0, -t), (g0, -t)]); pl([(g1, 0), (g1 + L, 0)]); pl([(g1, -t), (g1 + L, -t)])
    for u in (0, g1 + L): pl([(u, 60), (u, -t - 60)], 'SOG-SEC')
    yb = -t + covb + d / 2
    pl([(30, yb), (g0 - cov, yb)], 'GB-RFT-BOT', w=d); pl([(g1 + cov, yb), (g1 + L - 30, yb)], 'GB-RFT-BOT', w=d)
    k = 0
    while 75 + k * s < g0 - cov:                                       # cut bars of the other direction (dots)
        c = A(75 + k * s, yb + d); msp.add_circle(c, d / 2, dxfattribs={'layer': 'GB-RFT-BOT'})
        c = A(g1 + 75 + k * s, yb + d); msp.add_circle(c, d / 2, dxfattribs={'layer': 'GB-RFT-BOT'}); k += 1
    h = msp.add_hatch(color=8, dxfattribs={'layer': 'SOG-SEC'}); h.set_pattern_fill('ANSI31', scale=8)
    h.paths.add_polyline_path([A(g0, 0), A(g1, 0), A(g1, -gb_h), A(g0, -gb_h)], is_closed=True)
    tx(f'S.O.G {t} THK', 100, 60, 65)
    tx(f'T.O.GB = T.O.S.O.G {LV(top)}', g1 + 150, 60, 60)
    tx(f'BARS END {cov} FROM THE GB FACES', 100, -t - 300 if not backfill else 200, 55)
    tx(f'T{d}@{s} BOTTOM MESH (BOTH WAYS)', g1 + 150, -t - 160 if not backfill else 200, 55 if not backfill else 48)
    if not backfill: tx(f'BOTTOM COVER {covb}', g1 + 150, -t - 260, 55)
    tx('GB (SEE GB SECTIONS)', g0 - 150, -gb_h - 120, 55)
    if backfill:                                                      # backfill under the slab: shown, thickness not given
        for u0, u1 in ((0, g0), (g1, g1 + L)):
            h = msp.add_hatch(color=8, dxfattribs={'layer': 'SOG-SEC'}); h.set_pattern_fill('AR-SAND', scale=4)
            h.paths.add_polyline_path([A(u0, -t), A(u1, -t), A(u1, -t - 350), A(u0, -t - 350)], is_closed=True)
        tx(backfill, 100, -930, 50)
    for u0, u1, v in ((g0 - cov, g0, yb - 90), (g1, g1 + cov, yb - 90)):
        pl([(u0, v), (u1, v)], 'GB-DIM'); pl([(u0, v - 25), (u0, v + 25)], 'GB-DIM'); pl([(u1, v - 25), (u1, v + 25)], 'GB-DIM')
    tx(str(cov), g0 - cov / 2, yb - 160, 45, TA.MIDDLE_CENTER); tx(str(cov), g1 + cov / 2, yb - 160, 45, TA.MIDDLE_CENTER)
