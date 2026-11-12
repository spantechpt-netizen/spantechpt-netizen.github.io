"""Swimming pool - STRUCTURAL CONCRETE DIMENSION drawings (CONC. DIM.): plan, long section, cross sections, details.
A1 paper layouts with the project frame (same frame / title fields as the GB section-sheet packages), every drawing
in model space at 1:1 (mm), viewports at the drawing scales; layers / text style / dimension styles of the package.

pool_cd.json (project data, never in the repository):
  L, W              inner length (x, west -> east) / width (y)
  wall              wall thickness;  tow  structural top of walls (mm, e.g. 900 = +0.90);  finish  F.F.L - structural
  profile           [[x, z], ...] structural TOP of the floor (z in mm) along x from the west inner face, straight between
  soffit            [[x, z], ...] underside of the floor (as the consultant section), x may run under the walls
  under             [[name, thickness], ...] layers under the floor, top down (e.g. screed 50, membrane, PC 100)
  under_proj        projection of the layers beyond the wall outer faces; soil [thickness, projection beyond them]
  channel           {w, lip, floor_top, slab}  perimeter overflow channel outside the walls (top of lip = tow)
  waterstop         height of the waterstop at the wall / floor joint
  sections          {"S1": ["x", y], "S2": ["y", x], ...}  cut positions (plan coordinates, inner SW corner = 0, 0)
  sheets / frame / title fields as gen_gbsec (frame block dxf + block name + field positions)
usage: python3 gen_pool_cd.py pool_cd.json OUT.dxf
"""
import json, math, sys
import ezdxf
import ezdxf.recover
from ezdxf.enums import TextEntityAlignment as TA

C = json.load(open(sys.argv[1])); OUT = sys.argv[2]
L, W, T = C['L'], C['W'], C['wall']; TOW = C['tow']; FIN = C.get('finish', 0)
PROF = [tuple(p) for p in C['profile']]; SOF = [tuple(p) for p in C['soffit']]
CH = C['channel']; WS = C.get('waterstop', 300)
UND = C['under']; UT = sum(t for _, t in UND); UPR = C.get('under_proj', 150); SOIL_T, SOIL_P = C.get('soil', [700, 700])
STYLE = 'ROMANS'
LAY = {'SP-CONC': (7, 50), 'SP-CONC-HATCH': (8, 13), 'SP-UNDER': (8, 25), 'SP-SOIL': (8, 13), 'SP-DIM': (2, 18), 'SP-TXT': (7, 25),
       'SP-LVL': (3, 18), 'SP-SEC': (4, 35), 'SP-WSTOP': (6, 50), 'SP-HIDDEN': (8, 18), 'SP-WATER': (5, 18), 'SP-TITLE': (7, 25), 'SP-VPORT': (8, 13)}


def zt(x):                                     # structural top of the floor at x
    x = min(max(x, PROF[0][0]), PROF[-1][0])
    for (x0, z0), (x1, z1) in zip(PROF, PROF[1:]):
        if x0 <= x <= x1: return z0 + (z1 - z0) * (x - x0) / ((x1 - x0) or 1)
    return PROF[-1][1]


def lv(z): return f"{z / 1000:+.2f}" if abs(z) > 0.5 else '±0.00'


class D:
    """drawing helper: model origin (ox, oy), view scale sc (text sizes = paper mm x sc)."""
    def __init__(self, msp, ox, oy, sc):
        self.m, self.ox, self.oy, self.sc = msp, ox, oy, sc
    def P(self, x, y): return (self.ox + x, self.oy + y)
    def pl(self, pts, layer, closed=False, lt=None):
        e = self.m.add_lwpolyline([self.P(*q) for q in pts], close=closed, dxfattribs={'layer': layer})
        if lt: e.dxf.linetype = lt
        return e
    def ln(self, a, b, layer, lt=None):
        e = self.m.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': layer})
        if lt: e.dxf.linetype = lt
        return e
    def tx(self, s, x, y, h=2.5, layer='SP-TXT', al=TA.BOTTOM_LEFT, rot=0):
        t = self.m.add_text(s, height=h * self.sc, rotation=rot, dxfattribs={'layer': layer, 'style': STYLE})
        t.set_placement(self.P(x, y), align=al); return t
    def hatch(self, pts, layer, pattern, scale):
        h = self.m.add_hatch(color=8, dxfattribs={'layer': layer}); h.set_pattern_fill(pattern, scale=scale * self.sc / 10)
        h.paths.add_polyline_path([self.P(*q) for q in pts], is_closed=True); return h
    def dim(self, a, b, base, angle=0, text='<>'):
        d = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle, text=text,
                                  dimstyle=f'SPCD{self.sc}', dxfattribs={'layer': 'SP-DIM'}); d.render()
    def chain(self, xs, y, vertical=False, off=0):
        """dimension chain along x (or y when vertical) at y (x), every piece written with its value"""
        for a, b in zip(xs, xs[1:]):
            if vertical: self.dim((off, a), (off, b), (y, a), angle=90, text=str(round(b - a)))
            else: self.dim((a, off), (b, off), (a, y), text=str(round(b - a)))
    def level(self, x, z, txt, right=True, layer='SP-LVL'):
        s = self.sc; zz = 1.0 * s
        self.pl([(x, z), (x - zz * 0.6, z + zz), (x + zz * 0.6, z + zz)], layer, True)
        x1 = x + zz * 12 if right else x - zz * 12
        self.ln((x - zz * 1.0 if right else x + zz * 1.0, z), (x1, z), layer)
        self.tx(txt, x + zz * 1.2 if right else x - zz * 1.2, z + zz * 0.25, 2.0, layer, TA.BOTTOM_LEFT if right else TA.BOTTOM_RIGHT)
    def bubble(self, x, y, s_, r=6):
        self.m.add_circle(self.P(x, y), r * self.sc, dxfattribs={'layer': 'SP-SEC'})
        self.tx(s_, x, y, 5, 'SP-SEC', TA.MIDDLE_CENTER)


# ------------------------------------------------------------------ section geometry (along a cut)
def wall_section(d, u0, side, top, bot, label_wall=True):
    """wall + channel at one end of a section: u0 = inner face (u), side = -1 (wall to the left) / +1 (right);
    top = T.O.W, bot = floor soffit under the wall. Returns the outer u of the channel lip."""
    s = side; ui, uo = u0, u0 + s * T
    ch0, ch1, lip = uo, uo + s * CH['w'], uo + s * (CH['w'] + CH['lip'])
    cs = CH['floor_top'] - CH['slab']
    # wall (inner face from the floor top, outer face down to the soffit), channel slab and lip in one outline
    pts = [(ui, top), (ui, None), (uo, bot), (uo, cs), (lip, cs), (lip, top), (ch1, top), (ch1, CH['floor_top']), (ch0, CH['floor_top']), (ch0, top)]
    return pts, (ch0, ch1, lip, cs)


def draw_cut(d, us, zf, label, axis_txt, show_profile=None):
    """one section through the pool: us = (west/south inner face u = 0, other inner face u = Lc), zf(u) = floor top;
    draws walls, channel, floor, layers under it, soil, waterstops, levels and every dimension."""
    Lc = us
    zsof = (lambda u: soffit(u)) if show_profile else (lambda u: zf(u) - C['floor'])
    # floor + walls outline (concrete)
    left_bot, right_bot = zsof(0), zsof(Lc)
    ch = CH; cs = ch['floor_top'] - ch['slab']
    # outline: from the west lip around to the east lip (concrete in section)
    floor_top = [(u, zf(u)) for u in ([0] + [p[0] for p in PROF if 0 < p[0] < Lc] if show_profile else [0]) + [Lc]]
    soff = ([(-T, left_bot)] + ([(x, z) for x, z in SOF if -T < x < Lc + T] if show_profile else []) + [(Lc + T, right_bot)])
    if not show_profile: soff = [(-T, zsof(0)), (Lc + T, zsof(0))]
    outline = ([(-T - ch['w'] - ch['lip'], TOW), (-T - ch['w'], TOW), (-T - ch['w'], ch['floor_top']), (-T, ch['floor_top']), (-T, TOW), (0, TOW)]
               + floor_top + [(Lc, TOW), (Lc + T, TOW), (Lc + T, ch['floor_top']), (Lc + T + ch['w'], ch['floor_top']), (Lc + T + ch['w'], TOW),
                              (Lc + T + ch['w'] + ch['lip'], TOW), (Lc + T + ch['w'] + ch['lip'], cs), (Lc + T, cs)]
               + soff[::-1] + [(-T, cs), (-T - ch['w'] - ch['lip'], cs)])
    d.pl(outline, 'SP-CONC', True)
    d.hatch(outline, 'SP-CONC-HATCH', 'ANSI31', 8)
    # layers under the floor and the soil (projections beyond the wall outer faces)
    def offset(pts, dz, du0, du1):
        q = [(u, z + dz) for u, z in pts]; q[0] = (q[0][0] - du0, q[0][1]); q[-1] = (q[-1][0] + du1, q[-1][1]); return q
    under_top = soff
    acc = 0
    for name, t_ in UND:
        a = offset(under_top, -acc, UPR, UPR); b = offset(under_top, -(acc + t_), UPR, UPR)
        if t_ > 0:
            poly = a + b[::-1]
            d.pl(poly, 'SP-UNDER', True)
            if 'P.C' in name.upper() or 'PLAIN' in name.upper(): d.hatch(poly, 'SP-UNDER', 'AR-CONC', 0.6)
        else:
            d.pl(a, 'SP-WSTOP', lt='DASHED')
        acc += t_
    sb = offset(under_top, -UT, UPR, UPR); se = offset(under_top, -(UT + SOIL_T), UPR + SOIL_P, UPR + SOIL_P)
    sb2 = [(sb[0][0] - SOIL_P, sb[0][1])] + sb + [(sb[-1][0] + SOIL_P, sb[-1][1])]
    poly = sb2 + se[::-1]
    d.pl(poly, 'SP-SOIL', True); d.hatch(poly, 'SP-SOIL', 'EARTH', 1.5)
    # waterstops at the wall / floor joints (centre of the wall, WS high, centred on the joint)
    for u, z in ((-T / 2, zf(0)), (Lc + T / 2, zf(Lc))):
        d.pl([(u - 6, z - WS / 2), (u + 6, z - WS / 2), (u + 6, z + WS / 2), (u - 6, z + WS / 2)], 'SP-WSTOP', True)
        d.ln((u - T / 2, z), (u + T / 2, z), 'SP-WSTOP', 'DASHED')                     # construction joint
    # water / finish line
    d.ln((0, TOW + FIN), (Lc, TOW + FIN), 'SP-WATER', 'DASHED')
    return soff


def soffit(u):
    pts = SOF
    u = min(max(u, pts[0][0]), pts[-1][0])
    for (x0, z0), (x1, z1) in zip(pts, pts[1:]):
        if x0 <= u <= x1: return z0 + (z1 - z0) * (u - x0) / ((x1 - x0) or 1)
    return pts[-1][1]


def main():
    doc = ezdxf.new('R2010', setup=True); doc.units = 4; doc.header['$INSUNITS'] = 4; doc.header['$MEASUREMENT'] = 1
    for k, (c, lw) in LAY.items(): doc.layers.add(k, color=c, lineweight=lw)
    doc.styles.add(STYLE, font='arial.ttf')
    for sc in (5, 10, 20, 25, 50, 75, 100):
        ds = doc.dimstyles.duplicate_entry('EZDXF', f'SPCD{sc}')
        ds.dxf.dimscale = sc; ds.dxf.dimtxt = 2.0; ds.dxf.dimasz = 1.6; ds.dxf.dimexo = 1.0; ds.dxf.dimexe = 1.0; ds.dxf.dimgap = 0.6
        ds.dxf.dimtad = 1; ds.dxf.dimdec = 0; ds.dxf.dimblk = 'ARCHTICK'; ds.dxf.dimtxsty = STYLE; ds.dxf.dimclrd = 2; ds.dxf.dimclre = 2
    msp = doc.modelspace()
    # frame block (project frame from an approved package file)
    fr = C['frame']; FR = None
    if fr.get('block_dxf'):                                         # plain copy of the frame block (as the GB packages: AutoCAD-safe)
        import logging; logging.getLogger('ezdxf').setLevel(logging.ERROR)
        import gen_gbsec
        gen_gbsec.TXT_STYLE = STYLE
        src = ezdxf.recover.readfile(fr['block_dxf'])[0]
        FR = gen_gbsec.frame_block(doc, src, fr['block'])
    report = []

    def new_sheet(sh):
        lay = doc.layouts.new(sh['tab']); lay.page_setup(size=(841, 594), margins=(0, 0, 0, 0), units='mm')
        k = 841 / 1189.0
        if FR: lay.add_blockref(FR, (0, 0), dxfattribs={'xscale': k, 'yscale': k, 'layer': 'SP-TITLE'})
        for f, (fx, fy, fh) in fr['title'].items():
            v = sh.get(f, fr.get('defaults', {}).get(f, ''))
            for j, part in enumerate(str(v).split('\n')):
                if not part: continue
                t = lay.add_text(part, height=fh * k, dxfattribs={'layer': 'SP-TITLE', 'style': STYLE})
                t.set_placement((fx * k, (fy - j * fh * 1.6) * k), align=TA.MIDDLE_CENTER)
        return lay

    def vp(lay, cx, cy, w, h, mx, my, sc, title):
        v = lay.add_viewport(center=(cx, cy), size=(w, h), view_center_point=(mx, my), view_height=h * sc)
        v.dxf.status = 1; v.dxf.layer = 'SP-VPORT'
        lay.add_text(title, height=3.5, dxfattribs={'layer': 'SP-TITLE', 'style': STYLE}).set_placement((cx - w / 2 + 2, cy - h / 2 - 6))

    S = C['sheets']; ch = CH; cs = ch['floor_top'] - ch['slab']
    E = T + ch['w'] + ch['lip']                                     # wall + channel + lip
    # ================================================================== 1. CONC. DIM. PLAN (model at 0, 0)
    sc = 50; d = D(msp, 0, 0, sc)
    rect = lambda o: [(-o, -o), (L + o, -o), (L + o, W + o), (-o, W + o)]
    d.pl(rect(0), 'SP-CONC', True); d.pl(rect(T), 'SP-CONC', True)
    wall = rect(T) + [rect(T)[0]] + rect(0)[::-1] + [rect(0)[-1]]
    hz = msp.add_hatch(color=8, dxfattribs={'layer': 'SP-CONC-HATCH'}); hz.set_pattern_fill('ANSI31', scale=sc / 10 * 8)
    hz.paths.add_polyline_path([d.P(*q) for q in rect(T)], is_closed=True); hz.paths.add_polyline_path([d.P(*q) for q in rect(0)], is_closed=True)
    d.pl(rect(T + ch['w']), 'SP-CONC', True); d.pl(rect(E), 'SP-CONC', True)                       # channel inner face of the lip / lip
    hz2 = msp.add_hatch(color=8, dxfattribs={'layer': 'SP-CONC-HATCH'}); hz2.set_pattern_fill('ANSI31', scale=sc / 10 * 8)
    hz2.paths.add_polyline_path([d.P(*q) for q in rect(E)], is_closed=True); hz2.paths.add_polyline_path([d.P(*q) for q in rect(T + ch['w'])], is_closed=True)
    d.pl(rect(T + UPR), 'SP-HIDDEN', True, 'DASHED')                                              # layers under the floor (outline)
    kinks = [p[0] for p in PROF if 0 < p[0] < L]
    for x in kinks: d.ln((x, 0), (x, W), 'SP-HIDDEN', 'DASHED2')
    zones = [0] + kinks + [L]
    for a, b in zip(zones, zones[1:]):
        za, zb = zt(a), zt(b); xm = (a + b) / 2
        if abs(za - zb) < 1:
            d.tx(f"T.O.S {lv(za)}", xm, W * 0.62, 3.0, 'SP-LVL', TA.MIDDLE_CENTER)
            d.tx(f"(F.F.L {lv(za + FIN)})", xm, W * 0.62 - 6 * sc, 2.5, 'SP-LVL', TA.MIDDLE_CENTER)
        else:
            rise = abs(zb - za); run = b - a
            d.tx(f"SLOPE 1:{run / rise:.2f}", xm, W * 0.62, 2.5, 'SP-LVL', TA.MIDDLE_CENTER, rot=0)
            yy = W * 0.62 - 6 * sc; x0_, x1_ = (a + run * 0.15, b - run * 0.15)
            hi, lo = (x1_, x0_) if zb > za else (x0_, x1_)
            d.ln((hi, yy), (lo, yy), 'SP-LVL')
            sgn = 1 if lo > hi else -1
            d.pl([(lo, yy), (lo - sgn * 1.8 * sc, yy + 0.6 * sc), (lo - sgn * 1.8 * sc, yy - 0.6 * sc)], 'SP-LVL', True)
            d.tx('DOWN', (hi + lo) / 2, yy - 4 * sc, 2.0, 'SP-LVL', TA.MIDDLE_CENTER)
    d.tx(f"{T}THK. RC WALL", L / 2, W + T / 2, 2.2, 'SP-TXT', TA.MIDDLE_CENTER); d.tx(f"{T}THK. RC WALL", L / 2, -T / 2, 2.2, 'SP-TXT', TA.MIDDLE_CENTER)
    d.tx(f"{T}THK. RC WALL", -T / 2, W / 2, 2.2, 'SP-TXT', TA.MIDDLE_CENTER, rot=90); d.tx(f"{T}THK. RC WALL", L + T / 2, W / 2, 2.2, 'SP-TXT', TA.MIDDLE_CENTER, rot=90)
    d.tx(f"T.O.W {lv(TOW)}", L * 0.25, W - 4 * sc, 2.5, 'SP-LVL', TA.MIDDLE_CENTER)
    d.tx(f"OVERFLOW CHANNEL {ch['w']} (FLOOR {lv(ch['floor_top'])}), LIP {ch['lip']} (TOP {lv(TOW)}) - GRATING BY OTHERS", L * 0.5, W + E + 3 * sc, 2.2, 'SP-TXT', TA.BOTTOM_CENTER)
    d.tx(f"LAYERS UNDER THE FLOOR ({' + '.join(n for n, _ in UND)}) - OUTLINE {UPR} BEYOND THE WALLS (DASHED)", L * 0.5, -E - 3 * sc, 2.0, 'SP-TXT', TA.TOP_CENTER)
    # dimension chains: top (overall), along the zones, sides
    xs = [-E, -T, 0, L, L + T, L + E]                                 # channel + lip together (each part in D1 / D2)
    d.chain(xs, W + E + 12 * sc); d.dim((-T, 0), (L + T, 0), (-T, W + E + 20 * sc), text=str(round(L + 2 * T)))
    d.dim((-E, 0), (L + E, 0), (-E, W + E + 28 * sc), text=str(round(L + 2 * E)))
    d.chain(zones, -E - 12 * sc); d.dim((0, 0), (L, 0), (0, -E - 20 * sc), text=str(L))
    ys = [-E, -T, 0, W, W + T, W + E]
    d.chain(ys, -E - 12 * sc, vertical=True); d.dim((0, -T), (0, W + T), (-E - 20 * sc, -T), angle=90, text=str(round(W + 2 * T)))
    d.dim((0, -E), (0, W + E), (-E - 28 * sc, -E), angle=90, text=str(round(W + 2 * E)))
    d.chain([0, W], L + E + 12 * sc, vertical=True)
    # section marks
    secs = C['sections']
    for nm, (ax, pos) in secs.items():
        if ax == 'x':                                                  # cut along x (long section) at y = pos
            a_, b_ = (-E - 30 * sc, pos), (L + E + 22 * sc, pos)
        else:
            a_, b_ = (pos, -E - 26 * sc), (pos, W + E + 34 * sc)
        d.ln(a_, b_, 'SP-SEC', 'DASHDOT')
        for q in (a_, b_): d.bubble(q[0] + (0 if ax == 'y' else (-7 * sc if q[0] < 0 else 7 * sc)), q[1] + (0 if ax == 'x' else (-7 * sc if q[1] < 0 else 7 * sc)), nm)
    # ================================================================== 2. LONG SECTION S1 (model at 0, -60000)
    out_draw = {}
    oyL = -60000; scL = 50; d1 = D(msp, 0, oyL, scL)
    nm1 = next(n for n, (ax, _) in secs.items() if ax == 'x')
    draw_cut(d1, L, zt, nm1, 'X', show_profile=True)
    # dimensions: zones along the floor top, under the floor (soffit kinks), overall
    d1.chain([-E, -T, 0, L, L + T, L + E], TOW + 14 * scL)
    d1.chain(zones, TOW + 6 * scL)
    sk = [p[0] for p in SOF if 0 < p[0] < L]
    d1.chain([0] + sk + [L], min(z for _, z in SOF) - UT - SOIL_T - 10 * scL)
    for x in zones[:-1]:                                               # floor thickness (vertical) on every flat
        pass
    for a, b in zip(zones, zones[1:]):
        if abs(zt(a) - zt(b)) < 1:
            xm = (a + b) / 2
            d1.dim((xm, soffit(xm)), (xm, zt(xm)), (xm + 1500, soffit(xm)), angle=90, text=str(round(zt(xm) - soffit(xm))))
            d1.level(xm - 900, zt(xm), f"T.O.S {lv(zt(xm))} (F.F.L {lv(zt(xm) + FIN)})")
            d1.level(xm - 900, soffit(xm), f"B.O.S {lv(soffit(xm))}")
            d1.level(xm - 2400, soffit(xm) - UT, f"B.O.P.C {lv(soffit(xm) - UT)}")
            d1.level(xm - 2400, soffit(xm) - UT - SOIL_T, f"EXC. {lv(soffit(xm) - UT - SOIL_T)}")
            d1.dim((xm + 2200, soffit(xm) - UT), (xm + 2200, soffit(xm)), (xm + 2900, soffit(xm) - UT), angle=90, text=str(UT))
            d1.dim((xm + 2200, soffit(xm) - UT - SOIL_T), (xm + 2200, soffit(xm) - UT), (xm + 2900, soffit(xm) - UT - SOIL_T), angle=90, text=str(SOIL_T))
            d1.dim((xm - 2600, zt(xm)), (xm - 2600, TOW), (xm - 3300, zt(xm)), angle=90, text=str(round(TOW - zt(xm))))
        else:
            xm = (a + b) / 2; rise = abs(zt(b) - zt(a))
            d1.tx(f"SLOPE 1:{(b - a) / rise:.2f} ({b - a} / {round(rise)})", xm, zt(xm) + 3 * scL, 2.2, 'SP-LVL', TA.BOTTOM_CENTER)
    d1.level(-E - 300, TOW, f"T.O.W {lv(TOW)} (F.F.L / WATER {lv(TOW + FIN)})", right=False)
    d1.level(L + E + 300, TOW, f"T.O.W {lv(TOW)}")
    xs_ = (PROF[1][0] + PROF[2][0]) / 2
    d1.tx(f"COMPACTED SOIL {SOIL_T}", xs_, soffit(xs_) - UT - SOIL_T / 2 + 60, 2.0, 'SP-TXT', TA.BOTTOM_CENTER)
    d1.tx("ACCORDING TO SPECIFICATION", xs_, soffit(xs_) - UT - SOIL_T / 2 - 60, 2.0, 'SP-TXT', TA.TOP_CENTER)
    out_draw['S1'] = (d1, -E - 4600, L + E + 2800, min(z for _, z in SOF) - UT - SOIL_T - 16 * scL, TOW + 22 * scL)
    # ================================================================== 3. CROSS SECTIONS (model at 0, -90000 ...)
    crosses = [(n, pos) for n, (ax, pos) in secs.items() if ax == 'y']
    oy = -90000
    for n, pos in crosses:
        z = zt(pos); zs_ = soffit(pos)
        dc = D(msp, 0, oy, 50)
        draw_cut(dc, W, lambda u, z=z: z, n, 'Y', show_profile=False)
        dc.chain([-E, -T, 0, W, W + T, W + E], TOW + 12 * 50)
        dc.dim((-E, 0), (W + E, 0), (-E, TOW + 20 * 50), text=str(round(W + 2 * E)))
        dc.dim((W / 2, zs_), (W / 2, z), (W / 2 + 1200, zs_), angle=90, text=str(round(z - zs_)))
        dc.dim((W / 2 - 2000, z), (W / 2 - 2000, TOW), (W / 2 - 2700, z), angle=90, text=str(round(TOW - z)))
        dc.dim((W + T + 600, zs_ - UT), (W + T + 600, zs_), (W + T + 1300, zs_ - UT), angle=90, text=str(UT))
        dc.dim((W + T + 600, zs_ - UT - SOIL_T), (W + T + 600, zs_ - UT), (W + T + 1300, zs_ - UT - SOIL_T), angle=90, text=str(SOIL_T))
        dc.level(W * 0.25, z, f"T.O.S {lv(z)} (F.F.L {lv(z + FIN)})"); dc.level(W * 0.25, zs_, f"B.O.S {lv(zs_)}")
        dc.level(W * 0.62, zs_ - UT, f"B.O.P.C {lv(zs_ - UT)}"); dc.level(W * 0.62, zs_ - UT - SOIL_T, f"EXC. {lv(zs_ - UT - SOIL_T)}")
        dc.level(-E - 300, TOW, f"T.O.W {lv(TOW)} (F.F.L / WATER {lv(TOW + FIN)})", right=False)
        out_draw[n] = (dc, -E - 4600, W + E + 2600, zs_ - UT - SOIL_T - 8 * 50, TOW + 24 * 50)
        oy -= 12000
    # ================================================================== 4. DETAILS (model at 60000, ...)
    dets = []
    # D1 / D2: wall - floor - channel at the deep and the shallow ends, 1:10
    for i, (nm_, xw, side) in enumerate((('D1', 0, -1), ('D2', L, 1))):
        ox, oy_ = 80000, -130000 - i * 10000
        dd = D(msp, ox - xw, oy_, 20)
        draw_cut(dd, L, zt, 'D', 'X', show_profile=True)
        zf_, zs_ = zt(xw), soffit(xw - side * 1)
        u_out = xw + side * T; u_ch = xw + side * (T + ch['w']); u_lip = xw + side * E
        dd.chain(sorted([xw, u_out, u_ch, u_lip]), TOW + 9 * 10)
        dd.dim((u_lip + side * 1300, zf_), (u_lip + side * 1300, TOW), (u_lip + side * 1600, zf_), angle=90, text=str(round(TOW - zf_)))
        dd.dim((u_lip + side * 1300, cs), (u_lip + side * 1300, TOW), (u_lip + side * 1900, cs), angle=90, text=str(round(TOW - cs)))
        dd.dim((u_ch, ch['floor_top']), (u_ch, TOW), (u_ch - side * 80, ch['floor_top']), angle=90, text=str(round(TOW - ch['floor_top'])))
        dd.dim((u_lip + side * 1300, zs_), (u_lip + side * 1300, zf_), (u_lip + side * 1600, zs_), angle=90, text=str(round(zf_ - zs_)))
        dd.dim((u_lip + side * 1300, zs_ - UT), (u_lip + side * 1300, zs_), (u_lip + side * 1600, zs_ - UT), angle=90, text=str(UT))
        dd.dim((u_out, zs_ - UT - 80), (u_out + side * UPR, zs_ - UT - 80), (u_out, zs_ - UT - 250), text=str(UPR))
        dd.dim((u_ch, cs), (u_ch, ch['floor_top']), (u_ch - side * 60, cs), angle=90, text=str(ch['slab']))
        dd.level(xw - side * 600, zf_, f"T.O.S {lv(zf_)} (F.F.L {lv(zf_ + FIN)})", right=side < 0)
        dd.level(xw - side * 600, TOW, f"T.O.W {lv(TOW)}", right=side < 0)
        dd.level(u_lip + side * 250, ch['floor_top'], f"CHANNEL FLOOR {lv(ch['floor_top'])}", right=side > 0)
        acc = 0
        for k_, (name, t_) in enumerate(UND):
            yy = zs_ - acc - t_ / 2
            ly_ = zs_ + 150 + (len(UND) - 1 - k_) * 150                # labels outside the wall, under the channel
            ux_ = u_out + side * (UPR - 60)
            dd.ln((ux_, yy), (ux_ + side * 250, ly_), 'SP-TXT')
            dd.tx(f"{name}" + (f" {t_}" if t_ else ''), ux_ + side * 280, ly_, 1.8, 'SP-TXT', TA.MIDDLE_LEFT if side > 0 else TA.MIDDLE_RIGHT)
            acc += t_
        wu = xw + side * T / 2
        ly_ = zf_ + min(700, (TOW - zf_) * 0.55)
        dd.ln((wu, zf_ + WS / 2), (wu - side * 700, ly_), 'SP-TXT')
        dd.tx(f"WATERSTOP H = {WS}", wu - side * 730, ly_ + 30, 1.8, 'SP-TXT', TA.BOTTOM_RIGHT if side > 0 else TA.BOTTOM_LEFT)
        dd.tx("AT THE WALL / FLOOR JOINT", wu - side * 730, ly_ - 30, 1.8, 'SP-TXT', TA.TOP_RIGHT if side > 0 else TA.TOP_LEFT)
        dd.dim((wu, zf_ - WS / 2), (wu, zf_ + WS / 2), (wu + side * 250, zf_ - WS / 2), angle=90, text=str(WS))
        lo_u, hi_u = (u_lip - 2100, xw + 1500) if side < 0 else (xw - 1500, u_lip + 2100)
        dets.append((nm_, dd, lo_u, hi_u, zs_ - UT - 350, TOW + 300,
                     f"{nm_} - WALL / FLOOR / OVERFLOW CHANNEL AT THE {'DEEP (WEST)' if side < 0 else 'SHALLOW (EAST)'} END"))
    # D3 / D4: floor at the level changes, 1:20
    k_ = [i for i in range(1, len(PROF) - 1)]
    slopes = [(PROF[i], PROF[i + 1]) for i in range(len(PROF) - 1) if abs(PROF[i][1] - PROF[i + 1][1]) > 1]
    for j, ((xa, za), (xb, zb)) in enumerate(slopes):
        ox, oy_ = 80000, -160000 - j * 10000
        dd = D(msp, ox - xa, oy_, 25)
        draw_cut(dd, L, zt, 'D', 'X', show_profile=True)
        sa = [p for p in SOF if xa - 200 <= p[0] <= xb + 200]
        dd.chain([xa - 1500, xa, xb, xb + 1500], max(za, zb) + 800)
        dd.chain([xa - 1500] + [p[0] for p in sa] + [xb + 1500], min(z for _, z in sa) - UT - 400)
        dd.dim((xa - 1000, soffit(xa - 1000)), (xa - 1000, za), (xa - 1300, soffit(xa - 1000)), angle=90, text=str(round(za - soffit(xa - 1000))))
        dd.dim((xb + 1000, soffit(xb + 1000)), (xb + 1000, zb), (xb + 1300, soffit(xb + 1000)), angle=90, text=str(round(zb - soffit(xb + 1000))))
        dd.level(xa - 1400, za, f"T.O.S {lv(za)}", right=False); dd.level(xb + 1400, zb, f"T.O.S {lv(zb)}")
        dd.tx(f"SLOPE 1:{(xb - xa) / abs(zb - za):.2f}", (xa + xb) / 2, (za + zb) / 2 + 250, 1.8, 'SP-LVL', TA.BOTTOM_CENTER)
        dd.tx("SOFFIT AS THE CONSULTANT SECTION", (xa + xb) / 2, (za + zb) / 2 - C['floor'] - UT - 450, 1.6, 'SP-TXT', TA.TOP_CENTER)
        dets.append((f'D{3 + j}', dd, xa - 2400, xb + 2400, min(za, zb) - C['floor'] - UT - 650, max(za, zb) + 1050,
                     f"D{3 + j} - FLOOR AT THE LEVEL CHANGE x = {xa} .. {xb} (SLOPE 1:{(xb - xa) / abs(zb - za):.2f})"))
    # ================================================================== sheets
    sh = S[0]; lay = new_sheet(sh)
    x0, y0, x1, y1 = -E - 46 * sc, -E - 42 * sc, L + E + 38 * sc, W + E + 50 * sc
    w, h = (x1 - x0) / sc, (y1 - y0) / sc
    vp(lay, 14 + w / 2, 594 - 20 - h / 2, w, h, (x0 + x1) / 2, (y0 + y1) / 2, sc, f"CONC. DIM. PLAN   SCALE 1:{sc}")
    notes = C.get('notes', [])
    for j, s2 in enumerate(notes): lay.add_text(s2, height=2.5, dxfattribs={'layer': 'SP-TITLE', 'style': STYLE}).set_placement((14, 594 - 20 - h - 18 - j * 4.6))
    # long section sheet
    lay = new_sheet(S[1]); dd, a, b, lo, hi = out_draw['S1']
    w, h = (b - a) / scL, (hi - lo) / scL
    vp(lay, 14 + w / 2, 594 - 30 - h / 2, w, h, (a + b) / 2, oyL + (lo + hi) / 2, scL, f"SECTION {nm1}-{nm1} (LONGITUDINAL)   SCALE 1:{scL}")
    # cross sections sheet
    lay = new_sheet(S[2]); yv = 594 - 20
    for n, pos in crosses:
        dc, a, b, lo, hi = out_draw[n]
        w, h = (b - a) / 50, (hi - lo) / 50
        vp(lay, 14 + w / 2, yv - h / 2, w, h, (a + b) / 2, dc.oy + (lo + hi) / 2, 50, f"SECTION {n}-{n} (CROSS AT x = {pos} FROM THE WEST INNER FACE - FLOOR LEVEL CONSTANT ACROSS THE WIDTH)   SCALE 1:50")
        yv -= h + 16
    # details sheet
    lay = new_sheet(S[3]); xv, yv, rowh = 14, 594 - 20, 0
    for nm_, dd, a, b, lo, hi, title in dets:
        sc_ = dd.sc; w, h = (b - a) / sc_, (hi - lo) / sc_
        if xv + w > 712: xv, yv = 14, yv - rowh - 16; rowh = 0
        vp(lay, xv + w / 2, yv - h / 2, w, h, dd.ox + (a + b) / 2, dd.oy + (lo + hi) / 2, sc_, f"{title}   SCALE 1:{sc_}")
        xv += w + 14; rowh = max(rowh, h)
    for nm in [l.name for l in doc.layouts if l.name.startswith('Layout')]:
        try: doc.layouts.delete(nm)
        except Exception: pass
    for i, s_ in enumerate(S):
        try: doc.layouts.get(s_['tab']).dxf.taborder = i + 1
        except Exception: pass
    for e in list(doc.entitydb.values()):                             # every layer an entity names exists in the table
        try:
            if e.dxf.hasattr('layer') and e.dxf.layer not in doc.layers: doc.layers.add(e.dxf.layer)
        except Exception: pass
    au = doc.audit(); print('audit', len(au.errors), 'errors')
    doc.saveas(OUT); print('saved', OUT)


if __name__ == '__main__':
    main()
