"""Slab on grade (S.O.G) per zone (engineer, Oct 2026): the panels between the grade beams that carry an S.O.G tag on
the GB plan; the mesh starts at the inner faces of the grade beams + cover (50). Per zone one sheet with every bar in
X and one sheet with every bar in Y, the details written on the plan (bar groups, counts, lengths, spacing, range),
then the BBS of the zone.
project.json "sog": {dxf (plan with the tags), tag_block, thk_block, window [x0,y0,x1,y1] of that plan,
  to_gb [dx, dy] (tag plan -> GB plan of runs.pkl), d, s, cover, lap_d, layer, h}
uses runs.pkl / cols.pkl (GB plan), gb_to_fnd (GB plan -> foundation plan, for the zones).
usage: python3 gen_zone_sog.py [AREA 2 ...]   -> out/ZONES/AREA_n_SOG.dxf (sheets numbered from seq_start SG)"""
import sys, math, pickle, collections, logging, json
logging.getLogger('ezdxf').setLevel(logging.ERROR)
from ezdxf import recover
from shapely.geometry import box, Point, LineString, MultiPolygon
from shapely.ops import unary_union
import zone_util as Z
from gen import new_doc, seq_zone, seq_save, seq_none, BarList, draw_bbs, Sheet, TA, ST, callout, STOCK

C = Z.PRJ['sog']
GX, GY = Z.PRJ['gb_to_fnd']
d, s, cov = C['d'], C['s'], C['cover']
lapL = C.get('lap_d', 40) * d

# ---- tags on the plan (mesh + slab thickness)
doc_, _ = recover.readfile(C['dxf'])
X0, Y0, X1, Y1 = C['window']; TX, TY = C['to_gb']
tags, thk = [], []
for e in doc_.modelspace().query('INSERT'):
    x, y = e.dxf.insert.x, e.dxf.insert.y
    if not (X0 < x < X1 and Y0 < y < Y1): continue
    if e.dxf.name == C['tag_block']: tags.append((x + TX, y + TY))
    elif e.dxf.name == C.get('thk_block'):
        v = next((a.dxf.text for a in e.attribs), '')
        if v.isdigit(): thk.append((x + TX, y + TY, int(v)))
# ---- panels between the grade beams: every pair of parallel GB edge lines on the plan (any width 140..460) = a beam,
# plus the column / core outlines
def beam_pieces(msp, layer):
    segs = []
    for e in msp.query('LINE LWPOLYLINE'):
        if e.dxf.layer != layer: continue
        pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)] if e.dxftype() == 'LINE' else \
              [p[:2] for p in e.get_points()] + ([e.get_points()[0][:2]] if e.closed else [])
        for a, b in zip(pts, pts[1:]):
            if X0 < a[0] < X1 and Y0 < a[1] < Y1: segs.append((a, b))
    out = []
    for hor in (True, False):
        L = []
        for (x0, y0), (x1, y1) in segs:
            if hor and abs(y0 - y1) < 2: L.append((min(x0, x1), max(x0, x1), (y0 + y1) / 2))
            if not hor and abs(x0 - x1) < 2: L.append((min(y0, y1), max(y0, y1), (x0 + x1) / 2))
        L = sorted([l for l in L if l[1] - l[0] > 150], key=lambda l: l[2])
        for i, a in enumerate(L):
            for b in L[i + 1:]:
                w = b[2] - a[2]
                if w > 460: break
                if w < 140: continue
                lo, hi = max(a[0], b[0]), min(a[1], b[1])
                if hi - lo > 300:
                    out.append(box(lo + TX, a[2] + TY, hi + TX, b[2] + TY) if hor else box(a[2] + TX, lo + TY, b[2] + TX, hi + TY))
    return out
msp_ = doc_.modelspace()
rects = beam_pieces(msp_, C.get('beam_layer', 'CORE-FNDN-GRBM'))
for e in msp_.query('LWPOLYLINE'):
    if e.dxf.layer in C.get('col_layers', ['CORE-COLS-CONC']) and e.closed:
        p = [q[:2] for q in e.get_points()]
        if X0 < p[0][0] < X1 and Y0 < p[0][1] < Y1:
            from shapely.geometry import Polygon as _Pg
            g = _Pg([(x + TX, y + TY) for x, y in p]).buffer(0)
            if 0 < g.area < 12e6: rects.append(g)
U = unary_union([r.buffer(2, join_style=2) for r in rects])
env = box(*U.bounds).buffer(1000)
GAP = C.get('close_gap', 250)                                    # beams that stop short of a joint: gaps up to 2 x GAP closed
rest = env.difference(U.buffer(GAP, join_style=2))
pieces = list(rest.geoms) if isinstance(rest, MultiPolygon) else [rest]
outer = env.exterior
panels = []


def ray_rect(tx, ty):
    """Room of a tag the beam network leaves open (beams drawn broken at the joints): rays from the tag to the nearest
    beam faces (three rays a side, the nearest wall wins) -> the rectangle between them."""
    def hit(dx, dy):
        best = 60000
        for o in (-900, 0, 900):
            a = (tx + (o if dx == 0 else 0), ty + (o if dy == 0 else 0))
            g = LineString([a, (a[0] + dx * 60000, a[1] + dy * 60000)]).intersection(U)
            if g.is_empty: continue
            pts = [c for gg in (getattr(g, 'geoms', None) or [g]) for c in gg.coords]
            best = min(best, min(abs(c[0] - a[0]) + abs(c[1] - a[1]) for c in pts))
        return best
    r, l, t_, b_ = hit(1, 0), hit(-1, 0), hit(0, 1), hit(0, -1)
    if max(r, l, t_, b_) >= 60000: return None
    g = box(tx - l, ty - b_, tx + r, ty + t_).difference(U)
    return max(getattr(g, 'geoms', [g]), key=lambda q: q.area) if not g.is_empty else None


cells = [c for c in pieces if not c.intersects(outer) and c.area >= 1e6]
used = []
for t in tags:
    if any(p['pg'].contains(Point(t)) for p in panels): continue
    cell = next((c for c in cells if c.contains(Point(t))), None)
    how = 'closed'
    if cell is not None:
        pg = cell.buffer(GAP, join_style=2).difference(U)            # back to the beam faces
        if isinstance(pg, MultiPolygon): pg = max(pg.geoms, key=lambda g: g.area)
    else:
        pg = ray_rect(*t); how = 'rays'
        if pg is None or pg.area < 1e6: print('(!) S.O.G tag with no room found at', [round(v) for v in t]); continue
    if panels:                                                       # never two panels over the same slab
        pg = pg.difference(unary_union([p['pg'] for p in panels]))
        if isinstance(pg, MultiPolygon): pg = max(pg.geoms, key=lambda g: g.area)
        if pg.is_empty or pg.area < 1e6: continue
    th = [h for x, y, h in thk if pg.contains(Point(x, y))]
    c = pg.representative_point()
    panels.append(dict(pg=pg, h=max(th) if th else C.get('h', 100), zone=Z.zone_of(c.x + GX, c.y + GY), how=how))
print('panels with an S.O.G tag:', len(panels), collections.Counter(p['zone'] for p in panels), 'tags', len(tags), collections.Counter(p['how'] for p in panels))


def bars_of(pg, axis):
    """Bars across the panel (axis 'X' = bars along x, spaced in y) inside the panel shrunk by the cover."""
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
            (p, q) = (seg.coords[0], seg.coords[-1])
            out.append(dict(u=u, a=min(p[0], q[0]) if axis == 'X' else min(p[1], q[1]), b=max(p[0], q[0]) if axis == 'X' else max(p[1], q[1])))
    return out


def pieces_of(L):
    """A bar longer than the stock: equal pieces lapped (lap_d x d)."""
    if L <= STOCK: return [L]
    n = math.ceil((L - lapL) / (STOCK - lapL))
    p = int(math.ceil((L + (n - 1) * lapL) / n / 10) * 10)
    return [p] * n


r10 = lambda v: int(round(v / 10) * 10)
want = sys.argv[1:] or Z.NAMES
for zn in want:
    P_ = [p for p in panels if p['zone'] == zn]
    if not P_: seq_none('SOG', zn); print(zn, 'no S.O.G'); continue
    doc = new_doc(); bl = BarList()
    seq_zone(doc, zn, 'SOG', Z.NAMES)
    # one sheet per direction for the whole zone: a long zone is cut at gaps between its panels into parts drawn side
    # by side (or one above the other) on the same sheet, the layout with the largest scale wins
    def parts_of(m, along):                                    # along 'y': cut in y, parts side by side
        PP = sorted(P_, key=lambda p: p['pg'].bounds[1 if along == 'y' else 0])
        lo, hi = (1, 3) if along == 'y' else (0, 2)
        tot0, tot1 = min(p['pg'].bounds[lo] for p in PP), max(p['pg'].bounds[hi] for p in PP)
        out, cur, cur_hi = [], [], -1e18
        for p in PP:
            b0 = p['pg'].bounds[lo]
            target = tot0 + (tot1 - tot0) * (len(out) + 1) / m
            if cur and b0 >= cur_hi - 1 and cur_hi >= target and len(out) < m - 1:
                out.append(cur); cur = []
            cur.append(p); cur_hi = max(cur_hi, p['pg'].bounds[hi])
        out.append(cur)
        return out
    best = None
    for along in ('y', 'x'):
        for m in (1, 2, 3, 4):
            parts = parts_of(m, along)
            bb = [unary_union([p['pg'] for p in g]).bounds for g in parts]
            ws = [b_[2] - b_[0] + 2000 for b_ in bb]; hs = [b_[3] - b_[1] + 2000 for b_ in bb]
            if along == 'y': k_ = min((32500 - 1500 * (len(parts) - 1)) / sum(ws), 22500 / max(hs))
            else: k_ = min(32500 / max(ws), (22500 - 1500 * (len(parts) - 1)) / sum(hs))
            if best is None or k_ > best[0] * 1.05: best = (k_, along, parts, bb)
    k, along, parts, bb = best
    k = min(k, 1.0)
    scale = f'1:{int(round(100 / k / 25) * 25)}'
    lay = []                                                   # per part: (panels, bounds, origin)
    cx_, cy_ = 1200, 2600 + 22500
    if along == 'y': parts, bb = parts[::-1], bb[::-1]               # north part first (left)
    for g, b_ in zip(parts, bb):
        w_, h_ = (b_[2] - b_[0] + 2000) * k, (b_[3] - b_[1] + 2000) * k
        if along == 'y': ox_, oy_ = cx_, 2600 + (22500 - h_); cx_ += w_ + 1500
        else: ox_, oy_ = 1200, cy_ - h_; cy_ -= h_ + 1500
        lay.append((g, b_, ox_ - (b_[0] - 1000) * k, oy_ - (b_[1] - 1000) * k))
    for si, axis in enumerate(('X', 'Y')):
        meta = Z.base_meta(zn, 'SDW-STR-SOG', scale, f"S.O.G: T{d}@{s} {C.get('layer', 'BOTTOM')}, MESH FROM THE INNER FACES OF THE GRADE BEAMS + COVER {cov}.")
        meta['venue'] = 'SG'; meta['title'] = f'SLAB ON GRADE - {zn}\n{axis}-DIRECTION REINFORCEMENT'
        sh = Sheet(doc, 0, -si * 32000, meta)
        sh.text(f'S.O.G  {zn}  -  {axis}-DIRECTION BARS  ({scale})' + (f'  -  {len(lay)} PARTS' if len(lay) > 1 else ''), 1200, 27900, ST['name'] * 0.8, 'S-AXIS-TXT')
        sh.text(f"T{d}@{s} {C.get('layer', 'BOTTOM')}  -  BARS START {cov} FROM THE INNER FACES OF THE GRADE BEAMS  -  LAPS {lapL} (={C.get('lap_d', 40)}d) WHERE LONGER THAN {STOCK}",
                1200, 27250, ST['sub'] * 0.7, 'S-SEC', maxw=33500)
        ax = json.load(open('axes.json'))
        for pi, (g, (zx0, zy0, zx1, zy1), ox, oy) in enumerate(lay):
            Q = lambda x, y, ox=ox, oy=oy: (ox + x * k, oy + y * k)
            for p in g: p['Q'] = Q
            win = box(zx0 - 600, zy0 - 600, zx1 + 600, zy1 + 600)
            for r in rects:                                        # grade beams (light) and the S.O.G panels
                if r.intersects(win):
                    rr = r.intersection(win)
                    for gg in getattr(rr, 'geoms', [rr]):
                        if gg.geom_type == 'Polygon': sh.pline([Q(*q) for q in list(gg.exterior.coords)], 'S-GB-COL', 0)
            for p in g:
                sh.pline([Q(*q) for q in list(p['pg'].exterior.coords)], 'S-GB-CONC', 0)
            for nm, v in ax.items():                               # grid (grey, small)
                if nm.startswith('Y') and zx0 - 1000 < v < zx1 + 1000:
                    sh.line(Q(v, zy0 - 800), Q(v, zy1 + 800), 'S-AXIS'); sh.text(nm, *Q(v, zy1 + 900), 150, 'S-AXIS', align=TA.BOTTOM_CENTER)
                if nm.startswith('X') and zy0 - 1000 < v < zy1 + 1000:
                    sh.line(Q(zx0 - 800, v), Q(zx1 + 800, v), 'S-AXIS'); sh.text(nm, *Q(zx0 - 900, v), 150, 'S-AXIS', align=TA.MIDDLE_RIGHT)
            if len(lay) > 1:
                sh.text(f'PART {pi + 1}/{len(lay)}', *Q(zx0 - 900, zy0 - 900), 200, 'S-SEC', align=TA.TOP_LEFT)
        nb_tot = 0
        for p in P_:
            Q = p['Q']
            B = bars_of(p['pg'], axis)
            if not B: continue
            grp = collections.OrderedDict()                        # equal lengths in a row -> one group (range)
            for b in sorted(B, key=lambda b: (b['u'], b['a'])):
                L = r10(b['b'] - b['a'])
                key = (L, round(b['a'] / 50))
                grp.setdefault(key, []).append(b)
            # merge groups of the same length that touch (different start by a few mm)
            for (L, _), bs in grp.items():
                pcs = pieces_of(L)
                mk = None
                for pl in sorted(set(pcs)):
                    mk = bl.add(d, ('S', pl), pl, pcs.count(pl) * len(bs), 1, f'SOG-{axis}')
                nb_tot += len(bs)
                u0, u1 = bs[0]['u'], bs[-1]['u']; um = bs[len(bs) // 2]['u']
                a, b_ = bs[len(bs) // 2]['a'], bs[len(bs) // 2]['b']
                if axis == 'X':
                    P1, P2 = Q(a, um), Q(b_, um); R1, R2 = Q(a + (b_ - a) * 0.2, u0), Q(a + (b_ - a) * 0.2, u1)
                else:
                    P1, P2 = Q(um, a), Q(um, b_); R1, R2 = Q(u0, a + (b_ - a) * 0.2), Q(u1, a + (b_ - a) * 0.2)
                sh.pline([P1, P2], 'S-RFT-BOT', 30)                 # the bar of the group
                for e_ in (P1, P2):
                    sh.line((e_[0] - 40, e_[1] - 40), (e_[0] + 40, e_[1] + 40), 'S-RFT-BOT')
                sh.line(R1, R2, 'S-DIM')                           # the range of the group, ticks at the end bars
                for e_ in (R1, R2):
                    sh.line((e_[0] - 50, e_[1] - 50), (e_[0] + 50, e_[1] + 50), 'S-DIM')
                txt = callout(len(bs), d, mk, L if len(pcs) == 1 else max(pcs), s) + ('' if len(pcs) == 1 else f' ({len(pcs)} PCS LAPPED)')
                hT = max(110, min(170, 0.35 * min(abs(P2[0] - P1[0]) + abs(P2[1] - P1[1]), 9e9) / max(len(txt), 1) * 1.6))
                mx, my = (P1[0] + P2[0]) / 2, (P1[1] + P2[1]) / 2
                sh.ctext(mk, txt, mx, my + 40, hT, rot=0 if axis == 'X' else 90, align=TA.BOTTOM_CENTER)
        sh.text(f'{nb_tot} BARS T{d} IN {axis} IN THIS ZONE (SEE BBS).  SLAB {"/".join(sorted({str(p["h"]) for p in P_}))} THICK ON GRADE.',
                1200, 1500, ST['note'], 'S-RFT-TXT', maxw=33000)
    meta = Z.base_meta(zn, 'SDW-STR-SOG'); meta['venue'] = 'SG'; meta['title'] = f'SLAB ON GRADE - {zn}\nBBS'
    nbb = draw_bbs(doc, 2, bl.sorted(), meta)
    seq_save(doc)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_SOG.dxf")
    print(zn, 'panels', len(P_), 'sheets 2 + BBS', nbb)
