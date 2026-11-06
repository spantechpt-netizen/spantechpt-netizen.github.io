"""Axes + columns layout for a RADIAL (theatre / amphitheatre) structure that the consultant drew without axes.

Engineer (BLSC theatre, Nov 2026): "make the axes yourself, no overlaps".
  * centre and ring radii = least-squares fit of the columns (rings found by radius gaps); every column gets a radial
    axis through it, except a column within MERGE_DEG of another one's radial (that one keeps the outer column's axis and
    its tangential offset is dimensioned and tabled);
  * radial axes numbered 1..n by angle, rings lettered A, B ... from the centre out; radial lines stop short of the centre
    (no convergence clutter), bubbles at the outer end, ring arcs extended past the outline with bubbles at both ends;
  * angle between consecutive radial axes as an arc dimension, ring radii on the ring arcs, centre marked with its
    coordinates; every column D (hatched) with its label placed in a free spot;
  * setting-out table: column, axes, R, angle, radial / tangential offset from the intersection, X / Y;
  * every text / bubble placed through one collision list; a final check lists any overlap left (must be 0).
usage: RC_PROJECT=project.json python3 gen_axes_radial.py raft.json OUT [scale=50]
"""
import json, math, sys
import numpy as np
from shapely.geometry import Polygon, Point, LineString, box
from shapely.affinity import rotate as srot
import gen
from gen import new_doc, TA
from gen_raft import A0, dimstyle, copy_legend, SC

MERGE_DEG = 2.0                     # columns closer than this (degrees) share one radial axis


def fit_rings(C, c0):
    """c0: first guess of the centre (centre of the curved outline edge); rings split where the radii jump > 1 m."""
    C = np.array(C); c0 = np.array(c0, float)
    r = np.hypot(*(C - c0).T); order = np.argsort(r); gaps = np.diff(r[order])
    ring = np.zeros(len(C), int)
    for g in np.where(gaps > 1000)[0]: ring[order[g + 1:]] += 1
    nr = ring.max() + 1
    p = np.r_[c0, [r[ring == k].mean() for k in range(nr)]]
    def res(p): return np.hypot(*(C - p[:2]).T) - p[2:][ring]
    for _ in range(40):                                              # Gauss-Newton: one centre, one radius per ring
        r0 = res(p); J = np.zeros((len(C), len(p)))
        for k in range(len(p)):
            q = p.copy(); q[k] += 1e-3; J[:, k] = (res(q) - r0) / 1e-3
        p = p - np.linalg.lstsq(J, r0, rcond=None)[0]
    return p[:2], p[2:], ring, res(p)


class Placer:
    """one collision list for every text / bubble / column of the sheet (sheet units)."""
    def __init__(self): self.obst = []
    def free(self, g, pad=0): return not any(g.buffer(pad).intersects(o) for o in self.obst)
    def add(self, g): self.obst.append(g)


def fmt0(v):
    v = int(round(v)); return '0' if v == 0 else f'{v:+d}'


def text_poly(x, y, s, h, rot, align='MC'):
    w = len(s) * h * 0.78; hh = h
    dx = {'L': 0, 'C': -w / 2, 'R': -w}[align[1]]; dy = {'B': 0, 'M': -hh / 2, 'T': -hh}[align[0]]
    b = box(x + dx, y + dy, x + dx + w, y + dy + hh)
    return srot(b, rot, origin=(x, y))


def main():
    f = json.load(open(sys.argv[1])); out = sys.argv[2]
    scale = int(sys.argv[3]) if len(sys.argv) > 3 else 50
    k = SC / scale
    cols = [(c[0], c[1], c[2]) for c in f['cols']]
    # the curved edge of the outline: circle through the LONGEST run of consecutive short facets
    P = [tuple(p) for p in f['poly']]; n = len(P)
    short = [math.dist(P[i], P[(i + 1) % n]) < 700 for i in range(n)]
    best, cur = (0, 0), None
    for i in range(n + 1):
        if i < n and short[i]: cur = i if cur is None else cur
        else:
            if cur is not None and i - cur > best[1] - best[0]: best = (cur, i)
            cur = None
    A_ = np.array([P[i % n] for i in range(best[0], best[1] + 1)])
    s_ = np.linalg.lstsq(np.c_[2 * A_, np.ones(len(A_))], (A_ ** 2).sum(1), rcond=None)[0]
    ecx, ecy = s_[:2]; eR = math.sqrt(s_[2] + ecx ** 2 + ecy ** 2)
    (cx, cy), radii, ring, res = fit_rings([c[:2] for c in cols], (ecx, ecy))
    ang = lambda x, y: math.degrees(math.atan2(y - cy, x - cx))
    # radial axes: one per column, merged within MERGE_DEG (the outer column keeps the axis)
    cl = sorted(range(len(cols)), key=lambda i: ang(*cols[i][:2]))
    axes = []
    for i in cl:
        a = ang(*cols[i][:2])
        if axes and abs(a - axes[-1]['a']) < MERGE_DEG:
            ax = axes[-1]; ax['cols'].append(i)
            if ring[i] > ring[ax['owner']]: ax['owner'] = i; ax['a'] = a
        else:
            axes.append(dict(a=a, cols=[i], owner=i))
    for n, ax in enumerate(axes): ax['name'] = str(n + 1); ax['a'] = round(ax['a'], 2)
    rings = [dict(name=chr(65 + j), R=int(round(radii[j] / 10) * 10)) for j in range(len(radii))]
    # setting-out of every column
    tab = []
    for i, (x, y, r) in enumerate(cols):
        ax = next(a for a in axes if i in a['cols']); rg = rings[ring[i]]
        rr = math.dist((x, y), (cx, cy)); aa = ang(x, y)
        tab.append(dict(i=i, name=f"{rg['name']}-{ax['name']}", ax=ax['name'], ring=rg['name'], x=x, y=y, D=int(round(2 * r)),
                        R=rr, a=aa, dr=rr - rg['R'], dt=rr * math.sin(math.radians(aa - ax['a']))))
    tab.sort(key=lambda t: (t['ring'], int(t['ax'])))
    # ------------------------------------------------------------------ sheet
    doc = new_doc(); dimstyle(doc)
    tb = gen.TB; tpl = __import__('ezdxf').readfile(tb['dxf'])
    if tb.get('style') and tb['style'] not in doc.styles:
        doc.styles.add(tb['style'], font=tpl.styles.get(tb['style']).dxf.font)
    m = dict(gen._PRJ.get('meta', {})); m['title'] = f"{f.get('title1', 'STRUCTURAL COMBINED RAFT')}\nAXES AND COLUMNS LAYOUT - {f['name']}"
    m['scale'] = f'1:{scale}'; m['size'] = 'A0'
    sh = A0(doc, 0, 0, m); copy_legend_off = None
    PL = Placer()
    # extents of the plan: outline + rings + bubbles
    rmax = max(eR, max(radii)) + 2600
    a_lo, a_hi = min(a['a'] for a in axes), max(a['a'] for a in axes)
    pts = list(P) + [(cx + rmax * math.cos(math.radians(t)), cy + rmax * math.sin(math.radians(t))) for t in np.linspace(a_lo - 3, a_hi + 3, 40)] + [(cx, cy)]
    gx0 = min(p[0] for p in pts) - 2500; gx1 = max(p[0] for p in pts) + 2500
    gy0 = min(p[1] for p in pts) - 1500; gy1 = max(p[1] for p in pts) + 2500
    area = (6000, 14000, 150000, 158000)
    ox = area[0] + ((area[2] - area[0]) - (gx1 - gx0) * k) / 2; oy = area[1] + ((area[3] - area[1]) - (gy1 - gy0) * k) / 2
    S = lambda x, y: (ox + (x - gx0) * k, oy + (y - gy0) * k)
    PS = lambda r, t: S(cx + r * math.cos(math.radians(t)), cy + r * math.sin(math.radians(t)))
    BR = 1300; BT = 900; HT = 480; HS = 380                         # bubble radius / text, texts (sheet units)
    pg_s = Polygon([S(*p) for p in P])

    def text(s, x, y, h, rot=0, align='MC', layer='S-AXIS-TXT', pad=60, place=True):
        rot = (rot + 180) % 360 - 180                                  # readable from the bottom / right
        if rot > 90.01: rot -= 180
        if rot <= -90.01: rot += 180
        t = sh.text(s, x, y, h, layer, rot=rot, align={'MC': TA.MIDDLE_CENTER, 'ML': TA.MIDDLE_LEFT, 'MR': TA.MIDDLE_RIGHT,
                                                       'BC': TA.BOTTOM_CENTER, 'BL': TA.BOTTOM_LEFT, 'TC': TA.TOP_CENTER}[align])
        if place: PL.add(text_poly(x, y, s, h, rot, align).buffer(pad))
        return t

    def bubble(x, y, s):
        sh.circle(x, y, BR, 'S-AXIS'); text(s, x, y, BT, place=False); PL.add(Point(x, y).buffer(BR + 80))

    # raft outline (context, thin) and columns
    sh.pline([S(*p) for p in P], 'S-GB-CONC', 0, True)
    for x, y, r in cols:
        q = [S(x + r * math.cos(t), y + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 37)[:-1]]
        hz = sh.m.add_hatch(color=8, dxfattribs={'layer': 'S-GB-COL'}); hz.set_pattern_fill('ANSI31', scale=40)
        hz.paths.add_polyline_path([sh.P(*v) for v in q], is_closed=True); sh.pline(q, 'S-GB-COL', 0, True)
        PL.add(Polygon(q).buffer(60))
    # radial axes: from r0 (short of the centre) to past the outline, bubble at the outer end
    r0 = min(radii) - 2200
    for ax in axes:
        t = ax['a']
        r_end = max(eR, max(radii)) + 1100
        # stop where the line leaves the outline + 900, at least past the outer ring
        ln = LineString([(cx + r0 * math.cos(math.radians(t)), cy + r0 * math.sin(math.radians(t))),
                         (cx + (eR + 5000) * math.cos(math.radians(t)), cy + (eR + 5000) * math.sin(math.radians(t)))])
        g = ln.intersection(Polygon(P)); far = max((math.dist((cx, cy), q) for q in (getattr(g, 'geoms', [g])[-1].coords if not g.is_empty else [])), default=max(radii))
        r_end = max(far + 1200, max(radii) + 1200, max(eR, max(radii)) + 450 + 900)     # bubbles past the angle dimension arc
        a_, b_ = PS(r0, t), PS(r_end, t)
        sh.pline([a_, b_], 'S-AXIS', 0).dxf.linetype = 'CENTER' if 'CENTER' in doc.linetypes else 'CONTINUOUS'
        bx, by = PS(r_end + BR / k, t)
        bubble(bx, by, ax['name']); ax['bub'] = (bx, by)
        PL.add(LineString([a_, b_]).buffer(40))
    # ring axes: arcs past the first / last radial axis until outside the outline, bubbles at both ends
    for j, rg in enumerate(rings):
        R = rg['R']; t0, t1 = a_lo - 2.5, a_hi + 2.5
        while pg_s.contains(Point(PS(R, t0))) and t0 > a_lo - 6: t0 -= 0.5     # past the outline, at most 6 deg
        while pg_s.contains(Point(PS(R, t1))) and t1 < a_hi + 6: t1 += 0.5
        t0 -= 1500 / R * 180 / math.pi; t1 += 1500 / R * 180 / math.pi
        arc = [PS(R, t) for t in np.linspace(t0, t1, 120)]
        e = sh.pline(arc, 'S-AXIS', 0); e.dxf.linetype = 'CENTER' if 'CENTER' in doc.linetypes else 'CONTINUOUS'
        PL.add(LineString(arc).buffer(40))
        for tt, sg in ((t0, -1), (t1, 1)):
            ex, ey = PS(R + 0, tt)
            tx, ty = PS(R, tt + sg * (BR / k) / R * 180 / math.pi)
            bubble(tx, ty, rg['name'])
        rg['t0'], rg['t1'] = t0, t1
    # ring radii written on their arcs, inside the first span (free spot search along the arc)
    for rg in rings:
        s = f"{rg['name']}: R = {rg['R']}"
        for tt in list(np.linspace(axes[0]['a'] + 1, axes[-1]['a'] - 1, 60)):
            x, y = PS(rg['R'] + 220 / k * 2.2, tt); rot = tt - 90
            g = text_poly(x, y, s, HS, rot)
            if PL.free(g, 40): text(s, x, y, HS, rot); break
    # angles between consecutive radial axes: arc dimension outside the outline (radius just inside the bubbles)
    rd = max(eR, max(radii)) + 450                                    # radius of the angle dimensions
    for a1, a2 in zip(axes, axes[1:]):
        ta, tb = a1['a'], a2['a']
        arc = [PS(rd, t) for t in np.linspace(ta, tb, 30)]
        sh.pline(arc, 'S-DIM', 0)
        for t in (ta, tb):
            p1, p2 = PS(rd - 150, t), PS(rd + 150, t); sh.line(p1, p2, 'S-DIM')
            q1, q2 = PS(rd - 120, t - 0.25), PS(rd + 120, t + 0.25); sh.line(q1, q2, 'S-DIM')
        s = f"{tb - ta:.2f}°"
        tm = (ta + tb) / 2; placed = False
        for dr in (350, 650, -450, 950):
            x, y = PS(rd + dr, tm); rot = tm - 90
            g = text_poly(x, y, s, HS, rot)
            if PL.free(g, 30): text(s, x, y, HS, rot); placed = True; break
        if not placed: text(s, *PS(rd + 1300, tm), HS, tm - 90)
        PL.add(LineString(arc).buffer(30))
    # centre of the axes
    c_ = S(cx, cy)
    sh.line((c_[0] - 900, c_[1]), (c_[0] + 900, c_[1]), 'S-AXIS'); sh.line((c_[0], c_[1] - 900), (c_[0], c_[1] + 900), 'S-AXIS')
    sh.circle(c_[0], c_[1], 250, 'S-AXIS'); PL.add(Point(c_).buffer(950))
    for dx_, dy_, al in ((1300, 900, 'BL'), (1300, -1500, 'BL'), (-1300, 900, 'MR')):
        s1 = f'CENTRE OF AXES  X = {cx:.0f}  Y = {cy:.0f}'
        g = text_poly(c_[0] + dx_, c_[1] + dy_, s1, HS, 0, al)
        if PL.free(g, 40):
            text(s1, c_[0] + dx_, c_[1] + dy_, HS, 0, al); break
    # column labels: D + inner column tangential offset, in a free spot around each column
    for t in tab:
        x, y = S(t['x'], t['y'])
        lab = f"{t['name']}  D{t['D']}"
        done = False
        for rr_ in (900, 1300, 1800, 2400):
            for th in range(0, 360, 20):
                tx, ty = x + rr_ * math.cos(math.radians(th)), y + rr_ * math.sin(math.radians(th))
                al = 'ML' if math.cos(math.radians(th)) >= 0 else 'MR'
                g = text_poly(tx, ty, lab, HS, 0, al)
                if PL.free(g, 40):
                    text(lab, tx, ty, HS, 0, al, layer='S-RFT-TXT')
                    if rr_ > 1300: sh.line((x, y), (tx, ty), 'S-RFT-TXT')
                    done = True; break
            if done: break
        if not done: print('(!) no free place for', lab)
    # tangential offset of a column sharing an axis (dimension from the radial axis)
    for t in tab:
        if abs(t['dt']) >= 20:
            ax = next(a for a in axes if a['name'] == t['ax'])
            p_col = S(t['x'], t['y']); p_ax = PS(t['R'], ax['a'])
            sh.line(p_ax, p_col, 'S-DIM')
            s = f"{t['name']}: {abs(t['dt']):.0f} mm OFF AXIS {t['ax']} (CENTRE TO AXIS)"
            done = False
            for rr_ in (2200, 2800, 3500, 4500):                          # leader label in a free spot
                for th in range(200, 560, 15):
                    tx, ty = p_col[0] + rr_ * math.cos(math.radians(th)), p_col[1] + rr_ * math.sin(math.radians(th))
                    al = 'ML' if math.cos(math.radians(th)) >= 0 else 'MR'
                    ld = LineString([p_col, (tx, ty)])
                    if PL.free(text_poly(tx, ty, s, HS, 0, al), 40) and not any(ld.crosses(o.exterior) for o in PL.obst if o.geom_type == 'Polygon' and o.area < 5e7 and not o.contains(Point(p_col))):
                        sh.line(p_col, (tx, ty), 'S-RFT-TXT'); text(s, tx, ty, HS, 0, al, layer='S-DIM'); done = True; break
                if done: break
            if not done: print('(!) no place for', s)
    # setting-out table (right of the plan)
    tx0, ty0 = 152000, 150000
    cw = [5200, 2600, 2600, 5600, 4800, 3600, 3600]
    heads = ['COLUMN', 'AXIS', 'RING', 'R FROM CENTRE', 'ANGLE (DEG)', 'dR', 'dT']
    rh = 1150; W = sum(cw)
    sh.text('COLUMNS SETTING-OUT (FROM THE CENTRE OF AXES)', tx0, ty0 + 700, 520, 'S-SEC')
    y = ty0
    def row(vals, yy, hh=HS):
        xx = tx0
        for v, w in zip(vals, cw):
            sh.text(str(v), xx + w / 2, yy - rh / 2, hh, 'S-RFT-TXT', align=TA.MIDDLE_CENTER); xx += w
        sh.line((tx0, yy - rh), (tx0 + W, yy - rh), 'S-FRAME')
    sh.line((tx0, y), (tx0 + W, y), 'S-FRAME'); row(heads, y, 300); y -= rh
    for t in tab:
        row([f"{t['name']} D{t['D']}", t['ax'], t['ring'], f"{t['R']:.0f}", f"{t['a']:.2f}", fmt0(t['dr']), fmt0(t['dt'])], y); y -= rh
    xx = tx0
    for w in [0] + cw:
        xx += w; sh.line((xx, ty0), (xx, y), 'S-FRAME')
    sh.text('dR = R - RING RADIUS, dT = DISTANCE FROM THE RADIAL AXIS (mm); ANGLES COUNTER-CLOCKWISE FROM DRAWING X.', tx0, y - 700, 300, 'S-RFT-TXT', maxw=W)
    # axes table
    y -= 2400
    sh.text('AXES', tx0, y + 700, 520, 'S-SEC')
    cw2 = [3000, 9000, 9000]; W2 = sum(cw2)
    sh.line((tx0, y), (tx0 + W2, y), 'S-FRAME')
    def row2(vals, yy, hh=HS):
        xx = tx0
        for v, w in zip(vals, cw2):
            sh.text(str(v), xx + w / 2, yy - rh / 2, hh, 'S-RFT-TXT', align=TA.MIDDLE_CENTER); xx += w
        sh.line((tx0, yy - rh), (tx0 + W2, yy - rh), 'S-FRAME')
    y0t = y; row2(['AXIS', 'TYPE', 'ANGLE (DEG) / RADIUS (mm)'], y, 300); y -= rh
    for ax in axes: row2([ax['name'], 'RADIAL', f"{ax['a']:.2f}"], y); y -= rh
    for rg in rings: row2([rg['name'], 'RING (ARC)', f"R = {rg['R']}"], y); y -= rh
    xx = tx0
    for w in [0] + cw2:
        xx += w; sh.line((xx, y0t), (xx, y), 'S-FRAME')
    # notes
    notes = [f"AXES MADE BY SPAN TECH (THE CONSULTANT DRAWING HAS NO AXES): CENTRE AND RING RADII = BEST FIT OF THE {len(cols)} COLUMNS (MAX. OFFSET {max(abs(t['dr']) for t in tab):.0f} mm); RADIAL AXIS THROUGH EVERY COLUMN.",
             f"CENTRE OF THE CURVED RAFT EDGE (R = {eR:.0f}) IS {math.dist((ecx, ecy), (cx, cy)):.0f} mm FROM THE CENTRE OF AXES - SEE RFI.",
             f"COLUMNS ROUND D{tab[0]['D']} (CONSULTANT BLOCK); RAFT OUTLINE SHOWN THIN FOR REFERENCE. DIMENSIONS IN mm, ANGLES IN DEGREES."]
    for i, s in enumerate(notes): sh.text(s, 6000, 9500 - i * 750, 400, 'S-RFT-TXT', maxw=145000)
    sh.text(f"{f['name']} - AXES AND COLUMNS LAYOUT   SCALE 1:{scale}", 6000, 11300, 760, 'S-SEC')
    # overlap check: every text against every other text / bubble (sheet coords)
    texts = []
    for e in sh.m.query('TEXT'):
        if e.dxf.layer == 'S-TITLE' or not (0 < e.dxf.insert.x < 205000 and 0 < e.dxf.insert.y < 168200): continue
        ha, va = e.dxf.get('halign', 0), e.dxf.get('valign', 0)
        al = {0: 'B', 1: 'B', 2: 'M', 3: 'T'}[va] + {0: 'L', 1: 'C', 2: 'R'}.get(ha, 'L')
        anc = e.dxf.align_point if (ha or va) and e.dxf.hasattr('align_point') else e.dxf.insert
        g = text_poly(anc[0], anc[1], e.dxf.text, e.dxf.height, e.dxf.rotation, al)
        if e.dxf.get('width', 1) != 1: g = srot(g, 0)
        texts.append((e.dxf.text, g))
    ov = []
    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if texts[i][1].intersection(texts[j][1]).area > 1e3: ov.append((texts[i][0], texts[j][0]))
    doc.saveas(out + '.dxf')
    json.dump([[0, 0, A0.W, A0.H, 1189, 841]], open(out + '.sheets.json', 'w'))
    json.dump(dict(centre=[cx, cy], rings=rings, axes=[dict(name=a['name'], angle=a['a']) for a in axes], columns=tab,
                   edge_centre=[ecx, ecy], edge_R=eR, overlaps=ov), open(out + '.json', 'w'), indent=1)
    print('centre', round(cx), round(cy), 'rings', rings, 'axes', [(a['name'], a['a']) for a in axes])
    print('max dR', round(max(abs(t['dr']) for t in tab)), 'dT', [(t['name'], round(t['dt'])) for t in tab if abs(t['dt']) > 5])
    print('edge centre offset', round(math.dist((ecx, ecy), (cx, cy))), 'text overlaps', len(ov), ov[:5])


if __name__ == '__main__':
    main()
