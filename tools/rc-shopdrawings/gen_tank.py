"""Rectangular RC tank (raft + four walls + roof slab with an opening) - reinforcement shop drawings in the office
style: raft plan (bottom / top meshes), wall elevations + wall plan (horizontal rings), roof plan (bottom / top meshes,
bars cut at the opening), sections, BBS. Model space 1:1 (mm), paper layouts with the project frame block.

tank.json (project data): Lx, Ly outer plan sizes; wall; raft {h, top, cover, leg, d, s}; roof {h, top, cover, leg, d, s,
opening: [x0, y0, x1, y1]}; walls {cover, d, s_v, s_h}; lap_d; stock; frame {dxf, block, layout: {...}, fields: {...}};
sheets [{tab, title2, seq, dwg}]; sections {"3": "y", "4": "x"} (cut across y = transverse at mid length, ...).
usage: python3 gen_tank.py tank.json OUT.dxf"""
import json, math, sys
import ezdxf, ezdxf.recover
from ezdxf.enums import TextEntityAlignment as TA

C = json.load(open(sys.argv[1])); OUT = sys.argv[2]
LX, LY, TW = C['Lx'], C['Ly'], C['wall']
RF, RO, WL = C['raft'], C['roof'], C['walls']
LAPD, STOCK = C.get('lap_d', 60), C.get('stock', 12000)
STYLE = 'ROMANS'
up10 = lambda v: int(math.ceil(v / 10.0) * 10)
LAY = {'TK-CONC': (7, 35), 'TK-HATCH': (8, 13), 'TK-RFT-BOT': (5, 35), 'TK-RFT-TOP': (1, 35), 'TK-RFT-WALL': (3, 35),
       'TK-TXT': (7, 25), 'TK-DIM': (2, 18), 'TK-SEC': (4, 35), 'TK-HIDDEN': (8, 18), 'TK-TITLE': (7, 25), 'TK-VPORT': (8, 13)}


# ------------------------------------------------------------------ bars
class Marks:
    def __init__(self): self.rows = []
    def add(self, d, shape, n, elem, desc, pos):
        L = sum(v for v in shape[1:])
        for r in self.rows:                                          # one mark per bar and position (B1 / T1 apart)
            if r['d'] == d and r['shape'] == shape and r['pos'] == pos:
                r['n'] += n; r['use'].append((elem, n)); return r['mark']
        self.rows.append(dict(mark=len(self.rows) + 1, d=d, shape=shape, L=up10(L), n=n, use=[(elem, n)], desc=desc, pos=pos))
        return self.rows[-1]['mark']


def positions(a, b, s):
    n = math.ceil((b - a) / s - 1e-9) + 1
    return [a + (b - a) * i / (n - 1) for i in range(n)], (b - a) / (n - 1)


def callout(n, d, L, s=None, tag=None):
    t = f"{n} T {d}-{L}"
    if s: t += f"-{round(s)}"
    if tag: t += f" -{tag}"
    return t


M = Marks(); B = {}
# raft: B1 / T1 short (along y, outer layers), B2 / T2 long (along x); U legs leg_r (bottom up, top down)
c, lg, d, s = RF['cover'], RF['leg'], RF['d'], RF['s']
for tag, ax, top in (('B1', 'y', 0), ('B2', 'x', 0), ('T1', 'y', 1), ('T2', 'x', 1)):
    run = (LY if ax == 'y' else LX) - 2 * c
    xs, st = positions(c, (LX if ax == 'y' else LY) - c, s)
    shp = ('U', lg, run, lg)
    mk = M.add(d, shp, len(xs), 'RAFT', f"RAFT {'TOP' if top else 'BOTTOM'} {tag} ({'SHORT' if ax == 'y' else 'LONG'} DIR.)", 'R' + tag)
    B['R' + tag] = dict(mark=mk, n=len(xs), s=s, run=run, ax=ax, top=top, xs=xs, d=d, leg=lg)
# walls: vertical U (leg raft / vertical / leg roof), both faces; horizontal rings both faces, U + S pieces, laps staggered
cw, dw = WL['cover'], WL['d']
zb_v = RF['top'] - RF['h'] + RF['cover'] + 2 * RF['d'] + dw / 2        # on the raft bottom mesh
zt_v = RO['top'] - RO['cover'] - 2 * RO['d'] - dw / 2                  # under the roof top mesh
VL = round(zt_v - zb_v)
vshape = ('U', RF['leg'], VL, RO['leg'])
walls = {'S/N (LONG)': dict(n_el=2, out=(cw, LX - cw), inn=(TW + cw, LX - TW - cw), corner=True),
         'E/W (SHORT)': dict(n_el=2, out=(cw, LY - cw), inn=(TW + cw, LY - TW - cw), corner=False)}
for k, w in walls.items():
    po, so = positions(*w['out'], WL['s_v']); pi, si = positions(*w['inn'], WL['s_v'])
    n_out = len(po) - (0 if w['corner'] else 2)                      # corner bars counted on the long walls
    w.update(po=po, pi=pi, so=so, si=si, n_out=n_out, n_in=len(pi))
VN = sum((w['n_out'] + w['n_in']) * w['n_el'] for w in walls.values())
B['WV'] = dict(mark=M.add(dw, vshape, VN, 'WALLS', 'WALL VERTICAL (BOTH FACES)', 'V'), n=VN, shape=vshape)
SV, SH = WL['s_v'], WL['s_h']
zh0, zh1 = RF['top'] + 100, RO['top'] - RO['h'] - 100
rows_h, sh_h = positions(zh0, zh1, WL['s_h'])
lp = LAPD * dw
rings = {}
for face, (a, b) in (('OUTER', (LX - 2 * cw, LY - 2 * cw)), ('INNER', (LX - 2 * TW - 2 * cw, LY - 2 * TW - 2 * cw))):
    pats = []
    for straight in (STOCK - 3000, STOCK - 4800):                    # pattern A / B: laps 900 apart
        arm = (a + 2 * lp - straight) / 2
        pats.append(dict(arm=round(arm), straight=round(straight), U=('U', round(arm), round(b), round(arm)), S=('S', round(straight))))
    nA = math.ceil(len(rows_h) / 2); nB = len(rows_h) - nA
    for p, n in zip(pats, (nA, nB)):
        ab = 'A' if p is pats[0] else 'B'
        p['mU'] = M.add(dw, p['U'], 2 * n, 'WALLS', f'WALL H {face} - U (SHORT WALL) ROWS {ab}', 'H' + face)
        p['mS'] = M.add(dw, p['S'], 2 * n, 'WALLS', f'WALL H {face} - STRAIGHT (LONG WALL) ROWS {ab}', 'H' + face)
        p['n'] = n
    rings[face] = dict(a=a, b=b, pats=pats)
# roof: RB1 / RT1 short (along y), RB2 / RT2 long; bars through the opening cut at it (leg at the cut edge)
cr, lgr, dr, sr = RO['cover'], RO['leg'], RO['d'], RO['s']
ox0, oy0, ox1, oy1 = RO['opening']
for tag, ax, top in (('B1', 'y', 0), ('B2', 'x', 0), ('T1', 'y', 1), ('T2', 'x', 1)):
    xs, st = positions(cr, (LX if ax == 'y' else LY) - cr, sr)
    full = (LY if ax == 'y' else LX) - 2 * cr
    lo, hi = (ox0, ox1) if ax == 'y' else (oy0, oy1)
    cut = [x for x in xs if lo - dr / 2 < x < hi + dr / 2]
    cutrun = ((oy0 if ax == 'y' else ox0) - cr) - cr               # from the far edge to the opening edge (cover both)
    mk = M.add(dr, ('U', lgr, full, lgr), len(xs) - len(cut), 'ROOF', f"ROOF {'TOP' if top else 'BOTTOM'} {tag} ({'SHORT' if ax == 'y' else 'LONG'} DIR.)", 'F' + tag)
    mkc = M.add(dr, ('U', lgr, cutrun, lgr), len(cut), 'ROOF', f"ROOF {'TOP' if top else 'BOTTOM'} {tag} - CUT AT OPENING", 'F' + tag) if cut else None
    B['F' + tag] = dict(mark=mk, n=len(xs) - len(cut), s=sr, run=full, ax=ax, top=top, xs=xs, cut=cut, mkc=mkc, cutrun=cutrun, d=dr, leg=lgr)


# ------------------------------------------------------------------ drawing helper (as gen_pool_cd)
class D:
    def __init__(self, msp, ox, oy, sc): self.m, self.ox, self.oy, self.sc = msp, ox, oy, sc
    def P(self, x, y): return (self.ox + x, self.oy + y)
    def pl(self, pts, layer, closed=False, lt=None, w=0):
        e = self.m.add_lwpolyline([self.P(*q) for q in pts], close=closed, dxfattribs={'layer': layer})
        if lt: e.dxf.linetype = lt
        if w: e.dxf.const_width = w
        return e
    def ln(self, a, b, layer, lt=None):
        e = self.m.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': layer})
        if lt: e.dxf.linetype = lt
    def tx(self, s, x, y, h=2.0, layer='TK-TXT', al=TA.BOTTOM_LEFT, rot=0):
        t = self.m.add_text(s, height=h * self.sc, rotation=rot, dxfattribs={'layer': layer, 'style': STYLE}); t.set_placement(self.P(x, y), align=al); return t
    def hexmark(self, x, y, n, h=2.0):
        R = h * 1.3 * self.sc
        self.pl([(x + R * math.cos(math.radians(60 * k)), y + R * math.sin(math.radians(60 * k))) for k in range(6)], 'TK-TXT', True)
        self.tx(f'{n:02d}', x, y, h * 0.62, 'TK-TXT', TA.MIDDLE_CENTER)
    def ctext(self, mk, s, x, y, h=2.0, rot=0):
        """hexagon + call-out (x, y = left end of the hexagon, text baseline at the hexagon centre - h/2)"""
        R = h * 1.3 * self.sc
        if rot == 0:
            self.hexmark(x + R, y, mk, h); self.tx(s, x + 2 * R + 0.4 * h * self.sc, y - h * self.sc / 2, h)
        else:
            self.hexmark(x, y + R, mk, h); self.tx(s, x + h * self.sc / 2, y + 2 * R + 0.4 * h * self.sc, h, rot=90)
    def dim(self, a, b, base, angle=0, text='<>'):
        dd = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle, text=text, dimstyle=f'TKD{self.sc}', dxfattribs={'layer': 'TK-DIM'}); dd.render()
    def hatch(self, pts, pattern='ANSI31', scale=8, holes=()):
        h = self.m.add_hatch(color=8, dxfattribs={'layer': 'TK-HATCH'}); h.set_pattern_fill(pattern, scale=scale * self.sc / 10)
        h.dxf.hatch_style = 0                                        # odd parity: holes stay empty
        h.paths.add_polyline_path([self.P(*q) for q in pts], is_closed=True, flags=1)
        for hp in holes: h.paths.add_polyline_path([self.P(*q) for q in hp], is_closed=True, flags=16)
    def cutmark(self, n, a, b, r=2.2):
        """section cut: thick stubs at both ends of a-b with a numbered circle beyond each, arrow side = left of a->b"""
        R = r * self.sc; ux, uy = (b[0] - a[0]), (b[1] - a[1]); L = math.hypot(ux, uy); ux, uy = ux / L, uy / L
        for (px, py), sg in ((a, -1), (b, 1)):
            q = (px + sg * ux * 4 * self.sc, py + sg * uy * 4 * self.sc)
            self.pl([(px, py), q], 'TK-SEC', w=0.5 * self.sc)
            c = (q[0] + sg * ux * R, q[1] + sg * uy * R)
            self.m.add_circle(self.P(*c), R, dxfattribs={'layer': 'TK-SEC'}); self.tx(str(n), c[0], c[1], r * 0.9, 'TK-SEC', TA.MIDDLE_CENTER)
            nx, ny = -uy, ux                                         # view arrow
            self.pl([(px + nx * 2.5 * self.sc - ux * 0.8 * self.sc, py + ny * 2.5 * self.sc - uy * 0.8 * self.sc), (px + nx * 3.6 * self.sc, py + ny * 3.6 * self.sc),
                     (px + nx * 2.5 * self.sc + ux * 0.8 * self.sc, py + ny * 2.5 * self.sc + uy * 0.8 * self.sc)], 'TK-SEC', True)
            self.ln((px, py), (px + nx * 2.5 * self.sc, py + ny * 2.5 * self.sc), 'TK-SEC')
    def dot(self, x, y, r, layer):
        h = self.m.add_hatch(color=7, dxfattribs={'layer': layer}); h.paths.add_edge_path().add_arc(self.P(x, y), r, 0, 360)


def mesh_plan(d, key, lay_name, title, opening=None):
    """plan of one mesh layer pair (bottom or top): outline, opening, one bar per direction with folded legs,
    distribution lines, call-outs with hexagons."""
    sc = d.sc
    d.pl([(0, 0), (LX, 0), (LX, LY), (0, LY)], 'TK-CONC', True)
    d.pl([(TW, TW), (LX - TW, TW), (LX - TW, LY - TW), (TW, LY - TW)], 'TK-HIDDEN', True, 'DASHED')
    if opening:
        x0, y0, x1, y1 = opening
        d.pl([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], 'TK-CONC', True); d.ln((x0, y0), (x1, y1), 'TK-CONC'); d.ln((x0, y1), (x1, y0), 'TK-CONC')
    tags = [t for t in B if t.startswith(key)]
    lay = lambda b: 'TK-RFT-TOP' if b['top'] else 'TK-RFT-BOT'
    for t in tags:
        b = B[t]; cov = RF['cover'] if key == 'R' else RO['cover']; lgk = min(b['leg'], 450)
        fold = (-1 if b['top'] else 1)
        if b['ax'] == 'y':                                           # bars along y, drawn at 30 % of the length
            x = b['xs'][round(len(b['xs']) * 0.3)]
            d.pl([(x + fold * lgk, cov), (x, cov), (x, LY - cov), (x + fold * lgk, LY - cov)], lay(b), w=b['d'])
            y0d = LY * 0.62; d.ln((b['xs'][0], y0d), (b['xs'][-1], y0d), 'TK-DIM')
            for xx in (b['xs'][0], b['xs'][-1]): d.ln((xx - 60, y0d - 60), (xx + 60, y0d + 60), 'TK-DIM')
            d.m.add_circle(d.P(x, y0d), 40, dxfattribs={'layer': 'TK-DIM'})
            d.ctext(b['mark'], callout(b['n'], b['d'], up10(b['run'] + 2 * b['leg']), b['s'], t[1:]), x + 3 * sc, LY * 0.30, 2.0)
            if b.get('cut'):
                xc = b['cut'][len(b['cut']) // 2]
                d.pl([(xc + fold * lgk, cov), (xc, cov), (xc, cov + b['cutrun']), (xc + fold * lgk, cov + b['cutrun'])], lay(b), w=b['d'])
                d.ctext(b['mkc'], callout(len(b['cut']), b['d'], up10(b['cutrun'] + 2 * b['leg']), b['s'], t[1:]) + ' (AT THE OPENING)',
                        xc - 2 * sc - 2700, -6 * sc, 1.8)
                d.ln((xc, cov + 200), (xc - 1.5 * sc, -5 * sc), 'TK-TXT')
        else:
            y = b['xs'][round(len(b['xs']) * 0.45)]
            d.pl([(cov, y + fold * lgk), (cov, y), (LX - cov, y), (LX - cov, y + fold * lgk)], lay(b), w=b['d'])
            x0d = LX * 0.12; d.ln((x0d, b['xs'][0]), (x0d, b['xs'][-1]), 'TK-DIM')
            for yy in (b['xs'][0], b['xs'][-1]): d.ln((x0d - 60, yy - 60), (x0d + 60, yy + 60), 'TK-DIM')
            d.m.add_circle(d.P(x0d, y), 40, dxfattribs={'layer': 'TK-DIM'})
            d.ctext(b['mark'], callout(b['n'], b['d'], up10(b['run'] + 2 * b['leg']), b['s'], t[1:]), LX * 0.45, y + 2.6 * sc, 2.0)
            if b.get('cut'):
                yc = b['cut'][len(b['cut']) // 2]
                d.pl([(cov, yc + fold * lgk), (cov, yc), (cov + b['cutrun'], yc), (cov + b['cutrun'], yc + fold * lgk)], lay(b), w=b['d'])
                d.ctext(b['mkc'], callout(len(b['cut']), b['d'], up10(b['cutrun'] + 2 * b['leg']), b['s'], t[1:]) + ' (AT THE OPENING)',
                        LX * 0.45, LY + 5 * sc, 1.8)
                d.ln((LX * 0.6, yc), (LX * 0.45 + 2 * sc, LY + 4 * sc), 'TK-TXT')
    d.dim((0, 0), (LX, 0), (0, -13 * sc), text=str(LX)); d.dim((LX, 0), (LX, LY), (LX + 13 * sc, 0), angle=90, text=str(LY))


def main():
    doc = ezdxf.new('R2010', setup=True); doc.units = 4; doc.header['$INSUNITS'] = 4; doc.header['$MEASUREMENT'] = 1
    for k, (cc, lw) in LAY.items(): doc.layers.add(k, color=cc, lineweight=lw)
    doc.styles.add(STYLE, font='arial.ttf')
    for sc in (5, 10, 15, 20, 25, 30, 40, 50, 75, 100):
        ds = doc.dimstyles.duplicate_entry('EZDXF', f'TKD{sc}')
        ds.dxf.dimscale = sc; ds.dxf.dimtxt = 2.0; ds.dxf.dimasz = 1.5; ds.dxf.dimexo = 1.0; ds.dxf.dimexe = 1.0; ds.dxf.dimgap = 0.6
        ds.dxf.dimtad = 1; ds.dxf.dimdec = 0; ds.dxf.dimblk = 'ARCHTICK'; ds.dxf.dimtxsty = STYLE
    msp = doc.modelspace()
    import logging; logging.getLogger('ezdxf').setLevel(logging.ERROR)
    import gen_gbsec
    gen_gbsec.TXT_STYLE = STYLE
    fr = C['frame']; src = ezdxf.recover.readfile(fr['dxf'])[0]
    FR = gen_gbsec.frame_block(doc, src, fr['block'])
    blk = doc.blocks.get(FR)
    for e in list(blk):                                              # per-sheet values come from the sheets, not the block
        if e.dxftype() == 'TEXT' and e.dxf.text.strip() in fr.get('strip', []): blk.delete_entity(e)
    P = fr['paper']                                                  # [w, h] mm, insert, scale of the block
    def new_sheet(sh):
        lay = doc.layouts.new(sh['tab']); lay.page_setup(size=(P['w'], P['h']), margins=(0, 0, 0, 0), units='mm')
        k = P['scale']; ix, iy = P['insert']
        lay.add_blockref(FR, (ix, iy), dxfattribs={'xscale': k, 'yscale': k, 'layer': 'TK-TITLE'})
        for f, (fx, fy, fh, al) in fr['fields'].items():
            v = sh.get(f, fr.get('defaults', {}).get(f, ''))
            lines = str(v).split('\n')
            for j, part in enumerate(lines):
                if not part: continue
                yy = fy - (j - (len(lines) - 1) / 2) * fh * 1.6 if al == 'MC' else fy - j * fh * 1.6
                t = lay.add_text(part, height=fh * k, dxfattribs={'layer': 'TK-TITLE', 'style': STYLE})
                t.set_placement((ix + fx * k, iy + yy * k), align=TA.MIDDLE_CENTER if al == 'MC' else TA.BOTTOM_LEFT)
        return lay
    def vp(lay, cx, cy, w, h, mx, my, sc, title):
        v = lay.add_viewport(center=(cx, cy), size=(w, h), view_center_point=(mx, my), view_height=h * sc)
        v.dxf.status = 1; v.dxf.layer = 'TK-VPORT'
        lay.add_text(title, height=2.5, dxfattribs={'layer': 'TK-TITLE', 'style': STYLE}).set_placement((cx - w / 2 + 1, cy - h / 2 - 4.5))
    AW = fr.get('area_w', 350); AH = P['h'] - 10
    S = {s_['key']: s_ for s_ in C['sheets']}
    from shapely.geometry import box
    from shapely.ops import unary_union
    def solid(dd, rects):
        """union of concrete rectangles: outline + hatch (holes kept)"""
        u = unary_union([box(*r) for r in rects]); polys = list(getattr(u, 'geoms', [u]))
        for g in polys:
            ext = list(g.exterior.coords)[:-1]; holes = [list(i.coords)[:-1] for i in g.interiors]
            dd.pl(ext, 'TK-CONC', True)
            for hp in holes: dd.pl(hp, 'TK-CONC', True)
            dd.hatch(ext, holes=holes)
    def leader_ct(dd, mk, txt, x0, y, px, pz, h=2.0, right=True, xe=None):
        """call-out at (x0, y) with a leader from the text end (or the hexagon) to the bar point (px, pz)"""
        dd.ctext(mk, txt, x0, y, h)
        R = h * 1.3 * dd.sc
        if xe is None: xe = x0 + 2 * R + 0.4 * h * dd.sc + len(txt) * h * dd.sc * 0.68 + 0.6 * h * dd.sc if right else x0
        xt = x0 + 2 * R + 1.0 * h * dd.sc + len(txt) * h * dd.sc * 0.68
        if xe > xt: dd.ln((xt, y), (xe, y), 'TK-TXT')
        dd.ln((xe, y), (px, pz), 'TK-TXT'); dd.dot(px, pz, 0.45 * dd.sc, 'TK-TXT')
    X3 = C.get('cut3_x', round(LX * 0.22)); Y4 = C.get('cut4_y', (oy0 + oy1) / 2)
    def cuts(dd):
        dd.cutmark(3, (X3, -1 * dd.sc), (X3, LY + 1 * dd.sc)); dd.cutmark(4, (LX + 1 * dd.sc, Y4), (-1 * dd.sc, Y4))
    # ---------------------------------------------------------- 1. raft plan (bottom mesh / top mesh), 1:50
    sc = 50; d1 = D(msp, 0, 0, sc); d2 = D(msp, 0, -9000, sc)
    mesh_plan(d1, 'RB', 'B', 'BOTTOM')
    mesh_plan(d2, 'RT', 'T', 'TOP')
    for dd, nm in ((d1, 'BOTTOM MESH B1 / B2'), (d2, 'TOP MESH T1 / T2')):
        cuts(dd)
        dd.tx(f"RAFT {RF['h']} THK. (T.O.R {RF['top'] / 1000:+.2f}) - {nm}: T{RF['d']} @{RF['s']} EACH WAY, U LEGS {RF['leg']} ({'UP' if 'BOTTOM' in nm else 'DOWN'}), COVER {RF['cover']}", 0, LY + 11 * sc, 2.0)
    lay = new_sheet(S['raft'])
    mx0, mx1 = -14 * sc, LX + 18 * sc
    for i, (dd, nm) in enumerate(((d1, 'BOTTOM'), (d2, 'TOP'))):
        y0, y1 = dd.oy - 17 * sc, dd.oy + LY + 15 * sc
        w, h = (mx1 - mx0) / sc, (y1 - y0) / sc
        vp(lay, 8 + w / 2, AH - 6 - h / 2 - i * (h + 14), w, h, (mx0 + mx1) / 2, (y0 + y1) / 2, sc, f"RAFT REINFORCEMENT - {nm} MESH   SCALE 1:{sc}")
    # ---------------------------------------------------------- 2. walls: long-wall elevation (outer face), wall plan (rings)
    ew = D(msp, 0, -22000, sc)                                       # elevation of a long wall (outer face view), z up
    zb, zt = RF['top'] - RF['h'], RO['top']
    ew.pl([(0, zb), (LX, zb), (LX, zt), (0, zt)], 'TK-CONC', True)
    ew.ln((0, RF['top']), (LX, RF['top']), 'TK-HIDDEN', 'DASHED'); ew.ln((0, RO['top'] - RO['h']), (LX, RO['top'] - RO['h']), 'TK-HIDDEN', 'DASHED')
    wl = walls['S/N (LONG)']
    for x in wl['po'][::max(1, len(wl['po']) // 6)]:                 # a few vertical bars, the others by the distribution
        ew.pl([(x, zb_v), (x, zt_v)], 'TK-RFT-WALL', w=dw)
    zd = (zb_v + zt_v) / 2 - 200
    ew.ln((wl['po'][0], zd), (wl['po'][-1], zd), 'TK-DIM')
    for xx in (wl['po'][0], wl['po'][-1]): ew.ln((xx - 60, zd - 60), (xx + 60, zd + 60), 'TK-DIM')
    xv = wl['po'][len(wl['po']) // 2]
    leader_ct(ew, B['WV']['mark'], callout(wl['n_out'], dw, up10(sum(vshape[1:])), SV, 'V OUTER FACE') + f"   (INNER FACE: {wl['n_in']} BARS SAME MARK @{SV})",
              LX * 0.08, zb - 4 * sc, wl['po'][0], zb_v + 600, right=False)
    pA, pB = rings['OUTER']['pats']
    for i, z in enumerate(rows_h):                                   # horizontal rows, patterns A / B alternate, laps marked
        p = pA if i % 2 == 0 else pB
        a1 = p['arm']
        ew.ln((cw, z), (cw + a1, z), 'TK-RFT-WALL'); ew.ln((cw + a1 - lp, z + 25), (cw + a1 - lp + p['straight'], z + 25), 'TK-RFT-WALL')
        ew.ln((LX - cw - a1, z), (LX - cw, z), 'TK-RFT-WALL')
    ew.ln((LX * 0.93, rows_h[0]), (LX * 0.93, rows_h[-1]), 'TK-DIM')
    leader_ct(ew, pA['mS'], callout(2 * pA['n'], dw, pA['straight'], SH, 'H OUTER ROWS A (STRAIGHT)'), LX * 0.30, zt + 7.5 * sc, LX * 0.22, rows_h[-1] + 25, 1.8, right=False)
    leader_ct(ew, pB['mS'], callout(2 * pB['n'], dw, pB['straight'], SH, 'H OUTER ROWS B (STRAIGHT)'), LX * 0.30, zt + 3.5 * sc, LX * 0.26, rows_h[-2] + 25, 1.8, right=False)
    ew.dim((0, zb), (LX, zb), (0, zb - 11 * sc), text=str(LX))
    ew.dim((LX, zb), (LX, zt), (LX + 5 * sc, zb), angle=90, text=str(zt - zb))
    ew.dim((LX, RF['top']), (LX, RO['top'] - RO['h']), (LX + 10 * sc, zb), angle=90, text=str(RO['top'] - RO['h'] - RF['top']))
    ew.tx(f"HORIZONTAL BARS: {len(rows_h)} ROWS EACH FACE @{SH} (FIRST / LAST 100 FROM RAFT TOP / ROOF SOFFIT); LAPS {lp} (60d), ROWS A / B STAGGERED. INNER FACE SAME, MARKS ON THE PLAN", 0, zb - 16 * sc, 1.8)
    wp = D(msp, 0, -32000, sc)                                       # wall plan: rings, U at the short walls + straight on the long walls
    ring_o = [(0, 0), (LX, 0), (LX, LY), (0, LY)]; ring_i = [(TW, TW), (LX - TW, TW), (LX - TW, LY - TW), (TW, LY - TW)]
    wp.pl(ring_o, 'TK-CONC', True); wp.pl(ring_i, 'TK-CONC', True); wp.hatch(ring_o, holes=[ring_i])
    for face, off in (('OUTER', cw), ('INNER', TW + cw)):
        r = rings[face]; p = r['pats'][0]
        x0, y0, x1, y1 = off + dw / 2, off + dw / 2, LX - off - dw / 2, LY - off - dw / 2
        e = 30 if face == 'OUTER' else -30
        wp.pl([(x0 + p['arm'], y0), (x0, y0), (x0, y1), (x0 + p['arm'], y1)], 'TK-RFT-WALL', w=dw)
        wp.pl([(x1 - p['arm'], y0 + e), (x1, y0 + e), (x1, y1 - e), (x1 - p['arm'], y1 - e)], 'TK-RFT-WALL', w=dw)
        for yy in (y0 + e, y1 - e):
            wp.pl([(x0 + p['arm'] - lp, yy), (x0 + p['arm'] - lp + p['straight'], yy)], 'TK-RFT-WALL', w=dw)
        ty = (LY + 4 * sc) if face == 'OUTER' else (-5 * sc)
        pz = y1 if face == 'OUTER' else y0
        leader_ct(wp, p['mU'], callout(2 * p['n'], dw, up10(sum(p['U'][1:])), SH, f"H {face} U - ROWS A") + f";  ROWS B: {r['pats'][1]['mU']:02d}", LX * 0.08, ty, 300, pz, 1.8, right=False)
        leader_ct(wp, p['mS'], callout(2 * p['n'], dw, p['straight'], SH, f"H {face} STRAIGHT - ROWS A") + f";  ROWS B: {r['pats'][1]['mS']:02d}", LX * 0.52, ty, LX * 0.47, pz + e, 1.8, right=False)
    pO = rings['OUTER']['pats'][0]
    wp.dim((cw, LY), (cw + pO['arm'], LY), (cw, LY + 9 * sc), text=str(pO['arm']))
    wp.dim((cw + pO['arm'] - lp, LY), (cw + pO['arm'], LY), (cw, LY + 12.5 * sc), text=f"{lp} LAP")
    wp.dim((0, 0), (LX, 0), (0, -12 * sc), text=str(LX)); wp.dim((LX, 0), (LX, LY), (LX + 6 * sc, 0), angle=90, text=str(LY))
    lay = new_sheet(S['walls'])
    y_ = AH - 6
    for dd, (a, b, lo, hi), title in ((ew, (-8 * sc, LX + 16 * sc, zb - 19 * sc, zt + 11 * sc), f"LONG WALL (S / N) - OUTER FACE ELEVATION   SCALE 1:{sc}"),
                                      (wp, (-8 * sc, LX + 16 * sc, -15 * sc, LY + 17 * sc), f"WALLS - PLAN OF THE HORIZONTAL BARS (BOTH FACES)   SCALE 1:{sc}")):
        w, h = (b - a) / sc, (hi - lo) / sc
        vp(lay, 8 + w / 2, y_ - h / 2, w, h, (a + b) / 2, dd.oy + (lo + hi) / 2, sc, title); y_ -= h + 14
    # ---------------------------------------------------------- 3. roof plan, 1:50
    r1 = D(msp, 0, -42000, sc); r2 = D(msp, 0, -51000, sc)
    mesh_plan(r1, 'FB', 'B', 'BOTTOM', RO['opening']); mesh_plan(r2, 'FT', 'T', 'TOP', RO['opening'])
    for dd, nm in ((r1, 'BOTTOM MESH B1 / B2'), (r2, 'TOP MESH T1 / T2')):
        cuts(dd)
        dd.tx(f"ROOF {RO['h']} THK. (T.O.S {RO['top'] / 1000:+.2f}) - {nm}: T{RO['d']} @{RO['s']} EACH WAY, U LEGS {RO['leg']}, COVER {RO['cover']}; OPENING {ox1 - ox0} x {oy1 - oy0}, NO TRIMMING BARS",
              0, LY + 11 * sc, 2.0)
    lay = new_sheet(S['roof'])
    for i, (dd, nm) in enumerate(((r1, 'BOTTOM'), (r2, 'TOP'))):
        y0, y1 = dd.oy - 17 * sc, dd.oy + LY + 15 * sc
        w, h = (mx1 - mx0) / sc, (y1 - y0) / sc
        vp(lay, 8 + w / 2, AH - 6 - h / 2 - i * (h + 14), w, h, (mx0 + mx1) / 2, (y0 + y1) / 2, sc, f"ROOF SLAB REINFORCEMENT - {nm} MESH   SCALE 1:{sc}")
    # ---------------------------------------------------------- 4. sections 3-3 (transverse, 1:30) and 4-4 (longitudinal, 1:50)
    zr0, zr1, zf0, zf1 = RF['top'] - RF['h'], RF['top'], RO['top'] - RO['h'], RO['top']
    pc = C.get('blinding', 200)
    def section(dd, L, walls_key, roof_gap, short_tag, long_tag, lab):
        """generic cut: L = length along the cut, bars of direction long_tag drawn with legs, short_tag as dots"""
        rects = [(0, zr0, L, zr1), (0, zr1, TW, zf0), (L - TW, zr1, L, zf0)]
        if roof_gap: rects += [(0, zf0, roof_gap[0], zf1), (roof_gap[1], zf0, L, zf1)]
        else: rects.append((0, zf0, L, zf1))
        solid(dd, rects)
        dd.pl([(-150, zr0 - pc), (L + 150, zr0 - pc), (L + 150, zr0), (-150, zr0)], 'TK-HIDDEN', True)
        dd.tx(f'P.C {pc}', L * 0.5, zr0 - pc / 2, 1.6, 'TK-TXT', TA.MIDDLE_CENTER)
        pts = {}
        cR, dR, cF, dF = RF['cover'], RF['d'], RO['cover'], RO['d']
        for t, z, sg in (('RB' + long_tag, zr0 + cR + dR * 1.5, 1), ('RT' + long_tag, zr1 - cR - dR * 1.5, -1)):
            dd.pl([(cR, z + sg * RF['leg']), (cR, z), (L - cR, z), (L - cR, z + sg * RF['leg'])], 'TK-RFT-TOP' if sg < 0 else 'TK-RFT-BOT', w=dR); pts[t] = z
        for t, z in (('RB' + short_tag, zr0 + cR + dR / 2), ('RT' + short_tag, zr1 - cR - dR / 2)):
            for yy in positions(cR + dR, L - cR - dR, RF['s'])[0]: dd.dot(yy, z, dR / 2, 'TK-RFT-BOT')
            pts[t] = z
        for t, z, sg in (('FB' + long_tag, zf0 + cF + dF * 1.5, 1), ('FT' + long_tag, zf1 - cF - dF * 1.5, -1)):
            run = (cF, roof_gap[0] - cF) if roof_gap else (cF, L - cF)
            dd.pl([(run[0], z + sg * RO['leg']), (run[0], z), (run[1], z), (run[1], z + sg * RO['leg'])], 'TK-RFT-TOP' if sg < 0 else 'TK-RFT-BOT', w=dF); pts[t] = z
        for t, z in (('FB' + short_tag, zf0 + cF + dF / 2), ('FT' + short_tag, zf1 - cF - dF / 2)):
            for yy in positions(cF + dF, L - cF - dF, RO['s'])[0]:
                if not roof_gap or not (roof_gap[0] - dF < yy < roof_gap[1] + dF): dd.dot(yy, z, dF / 2, 'TK-RFT-BOT')
            pts[t] = z
        for xw, sg in ((0, 1), (L, -1)):                             # wall verticals (legs inward) + horizontal dots
            for face in ('OUT', 'IN'):
                x = xw + sg * (cw + dw / 2) if face == 'OUT' else xw + sg * (TW - cw - dw / 2)
                dd.pl([(x + sg * RF['leg'], zb_v), (x, zb_v), (x, zt_v), (x + sg * RO['leg'], zt_v)], 'TK-RFT-WALL', w=dw)
                for z in rows_h: dd.dot(x + sg * dw * (1 if face == 'OUT' else -1), z, dw / 2, 'TK-RFT-WALL')
        return pts
    def levels(dd, x, L):
        for z, nm in ((zf1, 'T.O.ROOF'), (zf0, 'B.O.ROOF'), (zr1, 'T.O.RAFT'), (zr0, 'B.O.RAFT'), (zr0 - pc, 'B.O.P.C')):
            dd.ln((L + 150, z), (x + 14 * 1.6 * dd.sc * 0.82, z), 'TK-DIM')
            dd.tx(f"{nm} {z / 1000:+.2f}", x, z + 0.5 * dd.sc, 1.6, 'TK-DIM', TA.BOTTOM_LEFT)
    s3 = D(msp, 30000, -22000, 30)
    p3 = section(s3, LY, 'S/N (LONG)', None, '2', '1', 3)
    cR, cF = RF['cover'], RO['cover']
    xl = -2750
    for i, (t, px) in enumerate((('FT1', 800), ('FT2', 1000), ('FB2', 1200), ('FB1', 1400))):
        b = B[t]; leader_ct(s3, b['mark'], callout(b['n'], b['d'], up10(b['run'] + 2 * b['leg']), b['s'], t[1:]), xl, 600 - 180 * i, px, p3[t], 1.8, xe=-700)
    for i, (t, px) in enumerate((('RT1', 1400), ('RT2', 1200), ('RB2', 1000), ('RB1', 800))):
        b = B[t]; leader_ct(s3, b['mark'], callout(b['n'], b['d'], up10(b['run'] + 2 * b['leg']), b['s'], t[1:]), xl, -1700 - 180 * i, px, p3[t], 1.8, xe=-700)
    leader_ct(s3, B['WV']['mark'], callout(B['WV']['n'], dw, up10(sum(vshape[1:])), SV, 'V BOTH FACES'), xl, -650, cw + dw / 2, -650, 1.8)
    zh = min(rows_h, key=lambda z: abs(z + 1000))
    leader_ct(s3, pA['mS'], f"T{dw} @{SH} H EACH FACE - SEE SHEET {S['walls']['seq']}", xl, -1000, cw + 1.5 * dw, zh, 1.8)
    s3.dim((0, -1300), (TW, -1300), (0, -1300), text=str(TW)); s3.dim((TW, -1300), (LY - TW, -1300), (0, -1300), text=str(LY - 2 * TW))
    s3.dim((LY - TW, -1300), (LY, -1300), (0, -1300), text=str(TW))
    for a_, b2, t_ in ((zr0, zr1, RF['h']), (zr1, zf0, zf0 - zr1), (zf0, zf1, RO['h'])):
        s3.dim((LY, a_), (LY, b2), (LY + 450, zr0), angle=90, text=str(t_))
    levels(s3, LY + 800, LY)
    s4 = D(msp, 30000, -42000, 50)
    gap = (ox0, ox1) if oy0 < Y4 < oy1 else None
    p4 = section(s4, LX, 'E/W (SHORT)', gap, '1', '2', 4)
    for t, px in (('FT2', 1600), ('FB2', 2600), ('FT1', 3600), ('FB1', 4600)):
        b = B[t]; mk = b['mkc'] if (gap and t[-1] == '2') else b['mark']
        s4.hexmark(px + 700, zf1 + 550, mk, 1.8); s4.ln((px + 700 - 120, zf1 + 450), (px, p4[t]), 'TK-TXT'); s4.dot(px, p4[t], 22, 'TK-TXT')
    for t, px in (('RB2', 1600), ('RT2', 2600), ('RB1', 3600), ('RT1', 4600)):
        b = B[t]; s4.hexmark(px + 700, zr0 - pc - 550, b['mark'], 1.8); s4.ln((px + 700 - 120, zr0 - pc - 450), (px, p4[t]), 'TK-TXT'); s4.dot(px, p4[t], 22, 'TK-TXT')
    s4.hexmark(-700, -700, B['WV']['mark'], 1.8); s4.ln((-580, -700), (cw + dw / 2, -700), 'TK-TXT')
    s4.hexmark(-700, -1300, rings['OUTER']['pats'][0]['mU'], 1.8); s4.ln((-580, -1300), (cw + 1.5 * dw, min(rows_h, key=lambda z: abs(z + 1300))), 'TK-TXT')
    s4.dim((0, zr0 - pc), (LX, zr0 - pc), (0, zr0 - pc - 1050), text=str(LX))
    if gap: s4.dim((gap[0], zf1), (gap[1], zf1), (0, zf1 + 300), text=f"{gap[1] - gap[0]} OPENING")  # dim line at zf1 + 300
    levels(s4, LX + 500, LX)
    lay = new_sheet(S['sections'])
    a, b_, lo, hi = -2850, LY + 2450, zr0 - pc - 250, zf1 + 300
    w3, h3 = (b_ - a) / 30, (hi - lo) / 30
    vp(lay, 8 + w3 / 2, AH - 6 - h3 / 2, w3, h3, s3.ox + (a + b_) / 2, s3.oy + (lo + hi) / 2, 30, f"SECTION 3-3 (TRANSVERSE)   SCALE 1:30")
    a, b_, lo, hi = -1100, LX + 2600, zr0 - pc - 1300, zf1 + 750
    w4, h4 = (b_ - a) / 50, (hi - lo) / 50
    vp(lay, 8 + w4 / 2, AH - 6 - h3 - 10 - h4 / 2, w4, h4, s4.ox + (a + b_) / 2, s4.oy + (lo + hi) / 2, 50, f"SECTION 4-4 (LONGITUDINAL, THROUGH THE OPENING)   SCALE 1:50  -  MARKS AS SECTION 3-3 / PLANS")
    import textwrap
    notes = ["NOTES:",
             "1. DIMENSIONS FROM THE CONC. DIM. PLAN; REINFORCEMENT FROM THE RFT DETAIL (RFI BT-01 / BT-02). DIMENSIONS IN mm, LEVELS IN m.",
             f"2. CLEAR COVER: RAFT {RF['cover']}, ROOF {RO['cover']}, WALLS {WL['cover']} (RFI BT-03 / BT-05).",
             f"3. LAPS AND ANCHORAGE 60d = {lp} (RFI BT-04). MAX. BAR LENGTH {STOCK}.",
             f"4. U LEGS: RAFT BARS AND WALL BARS INTO THE RAFT {RF['leg']}; ROOF BARS AND WALL BARS INTO THE ROOF {RO['leg']} (RFI BT-03 / BT-08).",
             "5. RAFT AND ROOF: BOTTOM AND TOP MESH EACH WAY (RFI BT-06).",
             "6. ROOF OPENING: BARS STOP AT THE OPENING EDGE WITH A U LEG; NO TRIMMING BARS (RFI BT-07).",
             "7. NO WATERSTOPS / JOINTS SHOWN (RFI BT-12).",
             "8. WALL HORIZONTAL BARS: CONTINUOUS RINGS EACH FACE (U AT THE SHORT WALLS + STRAIGHT ON THE LONG WALLS), LAPS 60d STAGGERED ROWS A / B - PROPOSAL, RFI BT-19.",
             "9. WALL VERTICAL BARS SIT ON THE RAFT BOTTOM MESH AND STOP UNDER THE ROOF TOP MESH."]
    xn = 8 + w3 + 6; yn = AH - 10; wn = 345 - xn
    for j, s2 in enumerate(notes):
        for k_, part in enumerate(textwrap.wrap(s2, int(wn / (1.8 * 0.78)), subsequent_indent='   ')):
            lay.add_text(part, height=1.8, dxfattribs={'layer': 'TK-TITLE', 'style': STYLE}).set_placement((xn, yn)); yn -= 3.2
        yn -= 1.2
    # ---------------------------------------------------------- 5. BBS
    from gen import _symbol
    from gen_gbsec import PS, BBS_COLS, UW
    COLS = list(BBS_COLS) + [('Description', 6800)]
    lay = new_sheet(S['bbs'])
    Wt = sum(w_ for _, w_ in COLS); k = min(fr.get('bbs_k', 0.0145), 335.0 / Wt); rh = 950; head = 1700; tit = 900
    rows = M.rows; Ht = tit + head + rh * len(rows) + 1800
    k = min(k, (AH - 10) / Ht)
    ps = PS(lay, 8, AH - 6 - Ht * k, k); ytop = Ht; bot = ytop - tit - head - rh * len(rows)
    ps.pline([(0, ytop), (Wt, ytop), (Wt, bot), (0, bot)], '', 0, True)
    ps.text(f"BBS - {C['name']} (NO = 1)", Wt / 2, ytop - tit / 2, 300, align=TA.MIDDLE_CENTER)
    hy = ytop - tit; ps.line((0, hy), (Wt, hy), ''); ps.line((0, hy - head), (Wt, hy - head), '')
    cx = 0
    for i, (name, w_) in enumerate(COLS):
        if i > 0: ps.line((cx, hy if i not in (4, 5) else hy - head / 2), (cx, bot), '')
        yy = hy - head / 2 if i not in (3, 4, 5) else hy - head * 0.75
        for j, part in enumerate(name.split('\n')): ps.text(part, cx + w_ / 2, yy + 120 - j * 260, 200, align=TA.MIDDLE_CENTER)
        cx += w_
    nx = sum(w_ for _, w_ in COLS[:3]); ps.line((nx, hy - head / 2), (nx + sum(w_ for _, w_ in COLS[3:6]), hy - head / 2), '')
    ps.text('Number', nx + sum(w_ for _, w_ in COLS[3:6]) / 2, hy - head / 4, 220, align=TA.MIDDLE_CENTER)
    tot = {}
    for r_, m in enumerate(rows):
        yr = hy - head - rh * (r_ + 1); ps.line((0, yr), (Wt, yr), '')
        mass = m['n'] * m['L'] / 1000.0 * UW(m['d']); tot[m['d']] = tot.get(m['d'], 0) + mass
        vals = [None, 'T', str(m['d']), str(m['n']), '1', str(m['n']), None, f"{m['L'] / 1000:.3f}", f'{mass:.2f}', f'{mass:.2f}', None]
        cx = 0
        for i, (name, w_) in enumerate(COLS):
            if i == 0: ps.mark(cx + w_ / 2, yr + rh / 2, m['mark'], 240)
            elif i == 6: _symbol(ps, cx, yr, w_, rh, m['shape'], m['d'])
            elif i == 10: ps.text(m['desc'], cx + 150, yr + rh / 2, 165, align=TA.MIDDLE_LEFT)
            else: ps.text(vals[i], cx + w_ / 2, yr + rh / 2, 200, align=TA.MIDDLE_CENTER)
            cx += w_
    ps.text('TOTAL BY DIAMETER:  ' + '    '.join(f'T{dd_} = {v:,.2f} kg' for dd_, v in sorted(tot.items())), 0, bot - 500, 220, align=TA.MIDDLE_LEFT)
    ps.text(f"TOTAL STEEL WEIGHT ({C['name']}) = {sum(tot.values()):,.2f} kg  ({sum(tot.values()) / 1000:.3f} t)", Wt, bot - 1100, 240, align=TA.MIDDLE_RIGHT)
    # ---------------------------------------------------------- finish
    for nm in [l.name for l in doc.layouts if l.name.startswith('Layout')]:
        try: doc.layouts.delete(nm)
        except Exception: pass
    for i, s_ in enumerate(C['sheets']):
        try: doc.layouts.get(s_['tab']).dxf.taborder = i + 1
        except Exception: pass
    for e in list(doc.entitydb.values()):
        try:
            if e.dxf.hasattr('layer') and e.dxf.layer not in doc.layers: doc.layers.add(e.dxf.layer)
        except Exception: pass
    au = doc.audit(); print('audit', len(au.errors), 'errors'); doc.saveas(OUT); print('saved', OUT)
    json.dump([dict(r, shape=list(r['shape'])) for r in M.rows], open(OUT.replace('.dxf', '.bbs.json'), 'w'), indent=1)
    for r in M.rows: print(f"{r['mark']:02d} T{r['d']} {r['shape']} L={r['L']} n={r['n']}  {r['desc']}")
    print('total kg', round(sum(r['n'] * r['L'] / 1000 * r['d'] ** 2 / 162 for r in M.rows), 2))


if __name__ == '__main__':
    main()
