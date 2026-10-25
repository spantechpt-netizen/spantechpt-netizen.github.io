"""Rafts / combined footings of ANY outline (stepped, L, notched, skewed) detailed on their real shape.

mats.json entry with `poly` (outline, local mm, long side along x) - written by mats_build.py from mats_scan2.py.
Rules (engineer, Oct 2026 - "the raft had execution errors: understand where every bar stops, where the distribution
changes, the laps, everything"):
  * MESH (bottom and top, both directions): every bar runs from face to face of the concrete at its own place, stops
    at the cover, U legs (h - 2c) at both ends (top U = bottom U, legs side by side). The polygon is cut by the bar
    lines; consecutive bars with the same piece(s) form one RANGE (one mark, one distribution line); a range changes
    exactly where the outline steps. Where the line crosses a notch the bar is two separate bars (two marks).
  * a bar longer than 12 m: equal pieces lapped 60 d, drawn as pieces.
  * ADD bars: from the drawn bar + its dimension (mats_scan2.py), each bar clipped to the concrete (cover); a bar
    shortened by the outline gets its own mark, a bar left shorter than 60 d is dropped - both reported.
  * re-entrant corners: 2 T16 L=1500 diagonal bars, bottom and top (Span Tech proposal - in the remarks).
  * side bars along the real perimeter (rows <= 300), laps 60 d away from the corners; chairs 1 / m2.
Sheets per type: BOTTOM X, BOTTOM Y, TOP X, TOP Y (plan with every range), ADD + corner bars, SIDE BARS + SECTION.
usage: python3 gen_mat.py NAME [NAME ...]   (or imported: draw_mat(doc, idx, f, meta, bl) -> sheets used)"""
import json, math, sys
from shapely.geometry import Polygon, LineString, Point
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, ST, mm, project_notes, lapped_marks
import gen_f

PRJ = json.load(open(__import__('os').environ.get('RC_PROJECT', 'project.json')))
C = PRJ.get('footing_cover', 70)
STOCK = 12000
TOL = 50                                                   # rows within 50 mm of the same ends = one range


class BigTF:                                              # A0 at 1:200: the A3 text sizes x 2
    def __new__(cls, doc, ox, oy, meta):
        import gen_cd
        class _B(gen_cd.BigSheet):
            def text(self, s_, x, y, h=250, layer='S-RFT-TXT', rot=0, align=TA.BOTTOM_LEFT, maxw=None):
                return super().text(s_, x, y, h if layer == 'S-TITLE' else h * 2, layer, rot, align, maxw)
            def ctext(self, mk, s_, x, y, h=250, layer='S-RFT-TXT', rot=0, align=TA.BOTTOM_LEFT, maxw=None):
                return super().ctext(mk, s_, x, y, h, layer, rot, align, maxw)
            def mark(self, x, y, n, h=250, layer='S-RFT-TXT'):
                return super().mark(x, y, n, h * 2, layer)
        if 'GB200' not in doc.dimstyles:
            ds = doc.dimstyles.duplicate_entry('GB100', 'GB200'); ds.dxf.dimscale = 200
        return _B(doc, ox, oy, meta)


def spacing(per_m): return math.floor(1000 / per_m / 5 + 0.01) * 5   # 6.667 /m -> 150 (not 145)


def pieces(L, lp):
    if L <= STOCK: return 1, int(math.ceil(L / 10) * 10)
    p = math.ceil((L - lp) / (STOCK - lp))
    return p, int(math.ceil((L + (p - 1) * lp) / p / 10) * 10)


def cut(er, t, axis):
    x0, y0, x1, y1 = er.bounds
    ln = LineString([(x0 - 10, t), (x1 + 10, t)]) if axis == 'X' else LineString([(t, y0 - 10), (t, y1 + 10)])
    g = er.intersection(ln); out = []
    for q in getattr(g, 'geoms', [g]):
        if q.is_empty or q.length < 300: continue
        b = q.bounds
        out.append((b[0], b[2]) if axis == 'X' else (b[1], b[3]))
    return sorted(out)


def ranges(pg, d, s, axis):
    """rows of bars (along `axis`) over the polygon -> list of ranges dict(t0, t1, n, segs=[(a, b)])"""
    er = pg.buffer(-C, join_style=2)
    x0, y0, x1, y1 = er.bounds
    lo, hi = ((y0, y1) if axis == 'X' else (x0, x1))
    n = math.ceil((hi - lo) / s) + 1
    step = (hi - lo) / (n - 1)
    er1 = pg.buffer(-(C + 2), join_style=2)                 # a row ON a step face belongs to the side it stops at
    def keep(t, i):                                         # pieces at the cover, but only where the row is really inside
        sg = cut(er, t, axis)
        if i in (0, n - 1): return sg
        s1 = cut(er1, t, axis)
        return [(a, b) for a, b in sg if any(a1 < b and b1 > a for a1, b1 in s1)]
    rows = [(lo + i * step, keep(lo + i * step, i)) for i in range(n)]
    out = []
    for t, sg in rows:
        if not sg: continue
        g = out[-1] if out else None
        if g and len(g['segs']) == len(sg) and all(abs(a - a2) <= TOL and abs(b - b2) <= TOL for (a, b), (a2, b2) in zip(g['segs'], sg)):
            g['t1'] = t; g['n'] += 1
            g['segs'] = [(min(a, a2), max(b, b2)) for (a, b), (a2, b2) in zip(g['segs'], sg)]
        else:
            out.append(dict(t0=t, t1=t, n=1, segs=sg))
    return out, step


def reentrant(poly):
    n = len(poly); pg = Polygon(poly); out = []
    ccw = pg.exterior.is_ccw
    for i in range(n):
        a, b, c = poly[i - 1], poly[i], poly[(i + 1) % n]
        cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        if (cr < 0) == ccw and abs(cr) > 1:
            u = ((a[0] - b[0]) / math.dist(a, b) + (c[0] - b[0]) / math.dist(b, c), (a[1] - b[1]) / math.dist(a, b) + (c[1] - b[1]) / math.dist(b, c))
            nu = math.hypot(*u) or 1
            out.append((b, (-u[0] / nu, -u[1] / nu)))           # corner + bisector INTO the concrete
    return out


def draw_mat(doc, idx0, f, meta0, bl, report):
    global C
    C = f.get('cover', PRJ.get('footing_cover', 70))
    poly = [tuple(p) for p in f['poly']]
    pg = Polygon(f['bar_poly']) if f.get('bar_poly') else Polygon(poly)      # bars may run past the outline (into the strip)
    pg_out = Polygon(poly)
    big = bool(f.get('big')); G = 2 if big else 1
    SH = BigTF if big else Sheet
    WS, HS = (237800, 168200) if big else (42000, 29700)
    L, W, h = f['L'], f['W'], f['h']
    lg = f.get('leg', h - 2 * C)
    long_x = L >= W
    idx = idx0
    k = next((100 / dn for dn in (50, 75, 100, 125, 150, 200, 250) if 100 / dn <= min(15500 / L, 18500 / W)), 0.4) if not big else next((200 / dn for dn in (100, 125, 150, 200, 250, 300, 400, 500)
                                                               if 200 / dn <= min(WS * 0.6 / L, HS * 0.78 / W)), 0.4)
    scale_txt = f'1:{round((200 if big else 100) / k)}'

    def frame(title):
        nonlocal idx
        m = dict(meta0); m['title'] = f"{m['title'].split(chr(10))[0]}\n{f['name']} - {title}"
        m['dwg'] = f"{meta0['dwg']}-{len([1 for _ in range(idx - idx0)]) + 1:02d}"
        if big: m['size'] = 'A0'; m['scale'] = scale_txt
        sh = SH(doc, 0, -idx * (32000 if not big else 172000), m); idx += 1
        meta0.setdefault('dwg_first', m.get('dwg_no', '')); meta0['dwg_no'] = meta0['dwg_first'] + ('' if idx - idx0 == 1 else f" ... {m.get('dwg_no', '').split('-')[-2]}")
        draw_legend(sh, WS * 0.5, HS * 0.94, G)
        sh.text(f"{f['name']}  h={h}  (NO={f['no']})  OUTLINE {len(poly)} CORNERS", WS * 0.048, HS * 0.94, ST['name'] * 0.8, 'S-AXIS-TXT')
        return sh

    ox, oy = (2600, 3800 + max(0, (18500 - W * k) / 2)) if not big else (WS * 0.04, HS * 0.1)
    P = lambda x, y: (ox + x * k, oy + y * k)

    def outline(sh, dims=True):
        sh.pline([P(*p) for p in poly], 'S-GB-CONC', 25 * G, True)
        for c_ in f.get('cols') or []: sh.hatch_rect(*P(c_[0], c_[1]), *P(c_[2], c_[3]))
        if dims:                                           # every edge dimensioned outside the outline
            cx, cy = pg_out.centroid.x, pg_out.centroid.y
            for a, b in zip(poly, poly[1:] + poly[:1]):
                Ls = math.dist(a, b)
                if Ls < 50: continue
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                nx, ny = (b[1] - a[1]) / Ls, -(b[0] - a[0]) / Ls
                if pg_out.contains(Point(mx + nx * 50, my + ny * 50)): nx, ny = -nx, -ny
                ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                if ang > 90.5 or ang <= -89.5: ang += 180
                sh.text(str(round(Ls)), *P(mx + nx * 260 / k, my + ny * 260 / k), 170, 'S-DIM', rot=ang, align=TA.MIDDLE_CENTER)
        for (cx, cy), u in reentrant(poly):
            sh.circle(*P(cx, cy), 90, 'S-DIM')

    # ------------------------------------------------ mesh sheets
    for layer, per, up in (('B', f['bot'], True), ('T', f['top'], False)):
        if not per or not per[0]: continue
        for axis, n_m, d in (('X', per[0], per[1]), ('Y', per[2], per[3])):
            s = spacing(n_m)
            is_long = (axis == 'X') == long_x
            tag = (layer + ('1' if is_long else '2')) if layer == 'B' else (layer + ('2' if is_long else '1'))
            rg, step = ranges(pg, d, s, axis)
            sh = frame(f"{'BOTTOM' if layer == 'B' else 'TOP'} REINFORCEMENT - BARS ALONG {axis}")
            outline(sh)
            # allowed lap zones by the supports (engineer, BLSC): bottom at midspan, top at the supports, +/- span / 5
            sup = sorted((f.get('supports') or {}).get(axis, []))
            zx = []
            for i_ in range(len(sup) - 1):
                sp = sup[i_ + 1] - sup[i_]
                if layer == 'B': zx.append(((sup[i_] + sup[i_ + 1]) / 2 - sp / 5, (sup[i_] + sup[i_ + 1]) / 2 + sp / 5))
            if layer == 'T':
                for i_, s_ in enumerate(sup):
                    spans = [sup[i_ + 1] - s_] if i_ + 1 < len(sup) else []
                    spans += [s_ - sup[i_ - 1]] if i_ else []
                    if spans: zx.append((s_ - min(spans) / 5, s_ + min(spans) / 5))
            ext_ = (0, W) if axis == 'X' else (0, L)
            run_ = L if axis == 'X' else W
            zx = [(max(0, a_), min(run_, b_)) for a_, b_ in zx if min(run_, b_) > max(0, a_)]   # bands stay inside the mat
            for a_, b_ in zx:                                  # hatched bands across the mat
                r_ = [(a_, ext_[0]), (b_, ext_[0]), (b_, ext_[1]), (a_, ext_[1])] if axis == 'X' else [(ext_[0], a_), (ext_[1], a_), (ext_[1], b_), (ext_[0], b_)]
                hz = sh.m.add_hatch(color=8, dxfattribs={'layer': 'S-DIM'}); hz.set_pattern_fill('ANSI37', scale=25)
                hz.paths.add_polyline_path([sh.P(*P(*q)) for q in r_], is_closed=True)
            if zx:
                sh.text(('LAP ZONES (HATCHED): BOTTOM MESH AT MIDSPAN (+/- SPAN/5)' if layer == 'B' else 'LAP ZONES (HATCHED): TOP MESH AT THE SUPPORTS (+/- SPAN/5)')
                        + f' - LAP {60 * d} (60d), ALTERNATE BARS STAGGERED >= 500', WS * 0.048, HS * 0.905, ST['note'] * G, 'S-DIM', maxw=WS * 0.5)
            lay = 'S-RFT-BOT' if layer == 'B' else 'S-RFT-TOP'
            lp = 60 * d
            items = []
            for gi, g in enumerate(rg):
                tm = (g['t0'] + g['t1']) / 2
                for a, b in g['segs']:
                    straight = round(b - a); tot = straight + 2 * lg
                    zon = [(lg + max(a_, a) - a, lg + min(b_, b) - a) for a_, b_ in zx if min(b_, b) > max(a_, a)] if zx else None
                    pats, marks = lapped_marks(bl, d, tot, lg, lg, g['n'], f['no'], tag, lp, zones=zon)
                    if zx and tot > 12000 and len(pats) == 2 and not any(z0 <= (pats[0][0][1] - lp / 2) <= z1 for z0, z1 in zon):
                        report.append(f"{f['name']} {layer}{axis}: laps could not be placed in the support zones - equal pieces used (CHECK)")
                        if not getattr(sh, '_lapwarn', False):
                            sh._lapwarn = True
                            sh.text('(!) WITH 12 m BARS THE LAPS CANNOT ALL BE INSIDE THE ALLOWED ZONES (SUPPORTS TOO FAR APART): SHOWN AS EQUAL STAGGERED PIECES - RFI (NOT FOR CONSTRUCTION)',
                                    WS * 0.048, HS * 0.875, ST['note'] * G, 'S-DIM', maxw=WS * 0.55).dxf.color = 1
                    mk = marks[0][0]
                    txt = ' + '.join(callout(c, d, m_, L_, s if not i else None, tag) + (' -STG' if len(marks) > 1 and not i else '')
                                     for i, (m_, c, L_) in enumerate(marks))
                    # the bar with its U legs folded into the plan (engineer: "the legs are not drawn"), pieces + laps
                    Q = (lambda u, t: P(u, t)) if axis == 'X' else (lambda u, t: P(t, u))
                    sgn = 1 if up else -1
                    lgk = min(lg * k, 1100)
                    pa, pb = Q(a, tm), Q(b, tm)
                    if axis == 'X': pts = [(pa[0], pa[1] + sgn * lgk), pa, pb, (pb[0], pb[1] + sgn * lgk)]
                    else: pts = [(pa[0] - sgn * lgk, pa[1]), pa, pb, (pb[0] - sgn * lgk, pb[1])]
                    bb = dict(d=d, leg=lg, straight=straight, pats=pats)
                    gen_f.draw_bar(sh, pts, bb, lay, k, sgn * 110)
                    for pq, al in (((pts[0], pts[1]), (pts[3], pts[2])) if lg else ()):          # leg lengths
                        mx_, my_ = (pq[0] + al[0]) / 2, (pq[1] + al[1]) / 2
                        sh.text(str(lg), mx_ + (90 if axis == 'X' else 0), my_ + (0 if axis == 'X' else 90), 150, 'S-DIM',
                                rot=90 if axis == 'X' else 0, align=TA.MIDDLE_CENTER)
                    if len(pats[0]) == 1:
                        mq = Q((a + b) / 2, tm)
                        sh.text(str(straight), mq[0] + (0 if axis == 'X' else -150), mq[1] + (150 if axis == 'X' else 0), 160, 'S-DIM',
                                rot=0 if axis == 'X' else 90, align=TA.BOTTOM_CENTER)
                    # distribution line over the range with ticks, at a quarter of the bar
                    ud = a + (b - a) * (0.18 + 0.12 * (gi % 3))
                    if g['n'] > 1:
                        sh.line(Q(ud, g['t0']), Q(ud, g['t1']), 'S-DIM')
                        for t_ in (g['t0'], g['t1']): sh.line(Q(ud - 60 / k, t_ - 60 / k), Q(ud + 60 / k, t_ + 60 / k), 'S-DIM')
                    sh.circle(*Q(ud, tm), 30, 'S-DIM')
                    items.append((Q(ud, tm), mk, txt, g, (a, b)))
            # call-out list right of the plan, leaders to the dot on each range
            lx = P(L, 0)[0] + 900 * G
            items.sort(key=lambda it: -it[0][1])
            ytop = min(HS * 0.86, P(0, W)[1]); dy = max(420 * G, min(650 * G, (ytop - 3000 * G) / max(1, len(items))))
            for i, (pt, mk, txt, g, ab) in enumerate(items):
                ty = ytop - i * dy
                sh.pline([pt, (lx - 150, ty + 90)], 'S-RFT-TXT')
                sh.ctext(mk, txt + f"   [{round(g['t0'] - (g['t0'] - C))}]" if False else txt, lx, ty, ST['call'] * 0.75,
                         maxw=WS * 0.95 - lx - 6800 * G)
                report.append(f"{f['name']} {layer}{axis}: {g['n']} bars, piece {round(ab[1] - ab[0])}, rows {round(g['t0'])}..{round(g['t1'])}")
            sh.text(f"{'BOTTOM' if layer == 'B' else 'TOP'} REINFORCEMENT - BARS ALONG {axis}  ({len(rg)} RANGES)  {scale_txt}",
                    ox, 2500 * G, ST['panel'], 'S-SEC')
            sh.text(f'EVERY BAR FROM FACE TO FACE - COVER {C}, U LEGS {lg}; ONE BAR DRAWN PER RANGE, DISTRIBUTION LINE = THE RANGE; '
                    'CIRCLES = RE-ENTRANT CORNERS (SEE CORNER BARS).', ox, 1900 * G, ST['note'], 'S-RFT-TXT', maxw=WS * 0.8)

    if f.get('mesh_only'):                                 # a slab cast with its strips: mesh sheets only
        return idx - idx0
    # ------------------------------------------------ ADD bars + corner bars
    sh = frame('ADDITIONAL BARS + RE-ENTRANT CORNER BARS')
    outline(sh, dims=False)
    er = pg.buffer(-C, join_style=2)
    items = []
    for a_ in f.get('adds') or []:
        if 'a0' not in a_: continue
        d, s_, ax = a_['d'], a_['s'], a_['along']
        n = a_['n']; zs = [a_['z0'] + i * (a_['z1'] - a_['z0']) / max(1, n - 1) for i in range(n)]
        groups = {}; dropped = 0; clipped = 0
        for t in zs:
            sg = cut(er, t, ax)
            got = []
            for a, b in sg:
                a2, b2 = max(a, a_['a0']), min(b, a_['a1'])
                if b2 - a2 <= 0: continue
                got.append((a2, b2))
            for a2, b2 in got:
                Ls = round((b2 - a2) / 10) * 10
                if Ls < 60 * d: dropped += 1; continue
                if Ls < a_['L'] - 20: clipped += 1
                groups.setdefault(Ls, []).append((t, a2, b2))
            if not got: dropped += 1
        lay = 'S-RFT-TOP' if a_['layer'] == 'T' else 'S-RFT-BOT'
        Q = (lambda u, t: P(u, t)) if ax == 'X' else (lambda u, t: P(t, u))
        for Ls, rows in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            mk = bl.add(d, ('S', Ls), Ls, len(rows), f['no'], 'ADD-' + a_['layer'])
            tm = rows[len(rows) // 2]
            sh.pline([Q(tm[1], tm[0]), Q(tm[2], tm[0])], lay, 40)
            sh.line(Q((tm[1] + tm[2]) / 2, rows[0][0]), Q((tm[1] + tm[2]) / 2, rows[-1][0]), 'S-DIM')
            items.append((Q((tm[1] + tm[2]) / 2, tm[0]), mk, callout(len(rows), d, mk, Ls, s_, 'ADD-' + a_['layer']) + f'  ({ax})'))
        if clipped or dropped:
            report.append(f"{f['name']}: ADD T{d}@{s_} L={a_['L']} ({ax}) runs past the concrete - {clipped} bars cut to the outline"
                          f"{f', {dropped} dropped (shorter than 60d)' if dropped else ''}")
    # re-entrant corner bars (bottom + top)
    rc = reentrant(poly)
    if rc:
        mkc = bl.add(16, ('S', 1500), 1500, 2 * len(rc) * (2 if f['top'][0] else 1), f['no'], 'DIAG')
        for (cx, cy), u in rc:
            vx, vy = -u[1], u[0]
            for o in (0, 100):
                for dist in (C + 350, C + 550, C + 800, C + 1100):          # first place where the whole bar is in concrete
                    ccx, ccy = cx + u[0] * (dist + o), cy + u[1] * (dist + o)
                    p0 = (ccx + vx * 750, ccy + vy * 750); p1 = (ccx - vx * 750, ccy - vy * 750)
                    if er.contains(LineString([p0, p1])): break
                else:
                    seg = er.intersection(LineString([p0, p1]))
                    report.append(f"{f['name']}: corner bar at {round(cx)},{round(cy)} does not fit 1500 - check on site")
                sh.pline([P(*p0), P(*p1)], 'S-RFT-BOT', 30)
        items.append((P(*rc[0][0]), mkc, callout(2 * len(rc) * (2 if f['top'][0] else 1), 16, mkc, 1500, None, 'DIAG') +
                      f'  (2 BOT{" + 2 TOP" if f["top"][0] else ""} AT EACH OF {len(rc)} RE-ENTRANT CORNERS)'))
        report.append(f"{f['name']}: {len(rc)} re-entrant corners - 2 T16 L=1500 diagonal bars bottom & top (SPAN TECH PROPOSAL)")
    lx = P(L, 0)[0] + 900 * G; ytop = min(HS * 0.86, P(0, W)[1])
    if not items: sh.text('- NO ADDITIONAL BARS -', *P(L / 2, W / 2), ST['call'], 'S-SEC', align=TA.MIDDLE_CENTER)
    for i, (pt, mk, txt) in enumerate(sorted(items, key=lambda it: -it[0][1])):
        ty = ytop - i * 650 * G
        sh.pline([pt, (lx - 150, ty + 90)], 'S-RFT-TXT')
        sh.ctext(mk, txt, lx, ty, ST['call'] * 0.75, maxw=WS * 0.95 - lx - 6800 * G)
    sh.text(f'ADDITIONAL BARS (AS DRAWN ON THE CONSULTANT PLAN, CLIPPED TO THE CONCRETE) + RE-ENTRANT CORNER BARS  {scale_txt}', ox, 2500 * G, ST['panel'], 'S-SEC')
    sh.text('ADD BARS STRAIGHT, IN A LAYER UNDER THE TOP MESH (ADD TOP) / ON THE BOTTOM MESH (ADD BOT); ZONE = DISTRIBUTION LINE.',
            ox, 1900 * G, ST['note'], 'S-RFT-TXT', maxw=WS * 0.8)

    # ------------------------------------------------ side bars + chairs + section
    sh = frame('SIDE BARS, CHAIRS, SECTION')
    outline(sh, dims=False)
    ds = 12; lps = 60 * ds
    free = h - 2 * C; rows = int(PRJ['side_rows']) if PRJ.get('side_rows') else max(1, math.ceil(free / 300) - 1)
    dmain = max(f['bot'][1], f['bot'][3], f['top'][1] if f['top'][0] else 0, f['top'][3] if f['top'][0] else 0)
    ring = pg.buffer(-(C + dmain + ds / 2), join_style=2)
    per = ring.exterior.length
    if per + lps <= STOCK:
        segs_pieces = [per + lps]
    else:
        np_ = math.ceil(per / (STOCK - lps))
        segs_pieces = [per / np_ + lps] * np_
    Lsb = int(math.ceil(max(segs_pieces) / 10) * 10)
    mksb = bl.add(ds, ('S', Lsb), Lsb, rows * len(segs_pieces), f['no'], 'SB')
    sh.pline([P(*q) for q in list(ring.exterior.coords)], 'S-RFT-STIR', 20, True)
    chairs = max(4, math.ceil(pg.area / 1e6))
    ch_h = int(h - 2 * C - f['bot'][1] - f['bot'][3] - (f['top'][1] + f['top'][3] if f['top'][0] else 0))
    if PRJ.get('chair_under_bottom'):             # T16 chair foot under the bottom mesh (engineer, BLSC)
        ch_h = int(h - 2 * C - (f['top'][1] + f['top'][3] if f['top'][0] else 0) + 16)
    chL = int(math.ceil((2 * 300 + 2 * ch_h + 400) / 10) * 10)
    lines = [(mksb, callout(rows * len(segs_pieces), ds, mksb, Lsb, None, 'SB') +
              (f'  ({rows} ROWS, {len(segs_pieces)} PCS PER ROW, LAP {lps} AWAY FROM THE CORNERS)' if len(segs_pieces) > 1 else f'  ({rows} ROWS, CLOSED LOOP, LAP {lps})'))]
    if f['top'][0]:
        mkch = bl.add(16, ('CH', 300, ch_h, 400), chL, chairs, f['no'], 'CH')
        lines.append((mkch, callout(chairs, 16, mkch, chL, 1000, 'CH') + ('  (1 PER m2 - FOOT UNDER THE BOTTOM MESH, CARRY THE TOP MESH)' if PRJ.get('chair_under_bottom') else '  (1 PER m2 - ON THE BOTTOM MESH, CARRY THE TOP MESH)')))
    lx = P(L, 0)[0] + 900
    for i, (mk, txt) in enumerate(lines):
        sh.ctext(mk, txt, lx, min(25600, P(0, W)[1]) - i * 650, ST['call'] * 0.75, maxw=WS * 0.95 - lx - 6800 * G)
    report.append(f"{f['name']}: side bars {rows} rows x {len(segs_pieces)} pcs L={Lsb}; chairs {chairs}")
    # typical section 1:25 at an edge
    ks = 4; sx0, sy0 = lx, 5200
    S = lambda x, y: (sx0 + x * ks, sy0 + y * ks)
    Wd = 2200
    sh.pline([S(0, -100), S(Wd, -100), S(Wd, 0), S(-100, 0), S(-100, -100)], 'S-GB-CONC')
    sh.pline([S(0, 0), S(Wd, 0)], 'S-GB-CONC'); sh.pline([S(0, 0), S(0, h), S(Wd, h)], 'S-GB-CONC')
    sh.break_line(S(Wd, -150), S(Wd, h + 150)) if False else sh.line(S(Wd, -100), S(Wd, h), 'S-SEC')
    db, dt_ = f['bot'][1], (f['top'][1] if f['top'][0] else 0)
    yb, yt = C + db / 2, h - C - dt_ / 2
    xb = C + db / 2
    sh.pline([S(xb, h - C - 2 * dmain - 20), S(xb, yb), S(Wd, yb)], 'S-RFT-BOT', db * ks, r=3 * db * ks)
    if dt_: sh.pline([S(xb + dt_ + 4, C + 2 * dmain + 20), S(xb + dt_ + 4, yt), S(Wd, yt)], 'S-RFT-TOP', dt_ * ks, r=3 * dt_ * ks)
    for r in range(rows):
        y = C + dmain + (free - 2 * dmain) * (r + 1) / (rows + 1)
        hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-STIR'}); hh.paths.add_edge_path().add_arc(sh.P(*S(xb + dmain + ds / 2 + 6, y)), ds / 2 * ks, 0, 360)
    if dt_:
        xc = 900
        sh.pline([S(xc - 500, yb + db), S(xc - 200, yb + db), S(xc - 200, yt - dt_), S(xc + 200, yt - dt_), S(xc + 200, yb + db), S(xc + 500, yb + db)], 'S-RFT-STIR', 16 * ks, r=40)
    sh.dim(S(0, 0), S(0, h), (S(0, 0)[0] - 500, S(0, 0)[1]), angle=90, text=str(h))
    sh.text(f'TYPICAL EDGE SECTION 1:25 - U LEGS {lg} SIDE BY SIDE, SIDE BARS INSIDE, CHAIR', sx0, sy0 - 1100, ST['panel'] * 0.8, 'S-SEC', maxw=40000 - sx0 - 6800)
    sh.text(f'SIDE BARS T{ds} ALONG THE REAL PERIMETER  {scale_txt}', ox, 2500, ST['panel'], 'S-SEC')
    return idx - idx0


if __name__ == '__main__':
    lib = json.load(open('mats.json'))
    names = sys.argv[1:] or [n for n, f in lib.items() if not f.get('rect', True)]
    doc = new_doc(); bl = BarList(); idx = 0; rep = []; dwgmap = {}
    for n in names:
        f = lib[n]; bl.cur = n
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = project_notes(f'COVER FOOTINGS {C}; PLAIN CONCRETE 100 UNDER FOOTINGS.', 'BARS DETAILED ON THE REAL OUTLINE; RANGES PER STEP.')
        meta['title'] = f"STRUCTURAL {'RAFT' if n.startswith('RAFT') else 'COMBINED FOOTING'}\nREINFORCEMENT - {n}"
        meta['dwg'] = f"SDW-STR-FDN-{n}"
        idx += draw_mat(doc, idx, f, meta, bl, rep)
        dwgmap[n] = meta.get('dwg_no', '')
    meta['title'] = 'STRUCTURAL RAFTS - REAL OUTLINE'
    if PRJ.get('bbs_per_element'):
        from gen import draw_bbs_grouped
        nb = draw_bbs_grouped(doc, idx, bl.sorted(), meta, [(f"{n}  (NO={lib[n]['no']})", n, lib[n]['no']) for n in names])
    else:
        nb = draw_bbs(doc, idx, bl.sorted(), meta)
    doc.saveas('out/MATS_POLY.dxf'); bl.export('out/MATS_POLY.bbs.json', dwgmap, {n: lib[n]['no'] for n in names})
    print('sheets', idx, '+ BBS', nb)
    print('\n'.join(rep))
