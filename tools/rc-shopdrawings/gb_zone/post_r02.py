"""Post-processing of a GB zone package (generic): clean plans redrawn from the extracted geometry.
- PLAN (reinforcement plan window) and CONC DIM: source copy removed; beams = ONE layer (union outline, no internal lines,
  closed joints), columns = ONE layer; beam / column labels; the section marks of gen_gbsec stay.
- CONC DIM: reference axes on the beam centre lines (no grid in the consultant plan) + chained dimensions + beam sizes.
- SOG: slab panels = the closed areas between the beams (one layer GB-SOG, blue, closed polylines), numbered with areas.
- TYPICAL DETAILS sheet: the typical detail + GB schedule of a reference DXF (config 'typical'), copied as drawn.
- curved beams (post_curved.py), engineer section bubbles (<zone>/eng_marks.json), bubbles moved off the plan texts.
usage: GBZ_CONFIG=cfg.json post_r02.py out.dxf FIRST zone   (normally run by build.py)"""
import sys, os, json, pickle, math, re
import ezdxf, ezdxf.recover
from ezdxf.addons import Importer
from ezdxf import bbox
from ezdxf.enums import TextEntityAlignment as TA
from shapely.geometry import box, Polygon, Point, LineString
from shapely.ops import unary_union
from shapely.affinity import rotate, translate

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from gbzcfg import Cfg
OUT = sys.argv[1]; FIRST = int(sys.argv[2]); Z = sys.argv[3]
K = Cfg(Z); ZC = K.z; ZN = K.ZN; BW = K.builddir(); BH = int(K.get('beam_h', 600)); HL = round(BH / 10)
LYB, LYC = K.layers['beam'], K.layers['col']
doc = ezdxf.readfile(OUT); msp = doc.modelspace()
LF = json.load(open(BW + '/lines_final.json'))
P0 = K.parts()[0]
PJ = {pn: json.load(open(K.partdir(pn) + '/part.json')) for pn in LF}
RAW = {pn: json.load(open(K.partdir(pn) + '/lines.json'))[pn] for pn in LF}
PK = {pn: pickle.load(open(K.partdir(pn) + '/plans.pkl', 'rb'))[pn] for pn in LF}
A1 = PJ[P0]['ang']
toP1 = lambda g, pn: rotate(g, PJ[pn]['ang'] - A1, origin=(0, 0))
OFF = {'PLAN': (0, 0), 'CD': (0, -80000), 'SOG': (0, -160000)}
for nm, col in (('GB-PL-BEAM', 7), ('GB-PL-COL', 7), ('GB-PL-COL-HATCH', 8), ('GB-PL-TXT', 7), ('GB-PL-AXIS', 1), ('GB-PL-DIM', 2), ('GB-SOG', 5), ('GB-SOG-TXT', 5)):
    if nm not in doc.layers: doc.layers.add(nm, color=col)
doc.layers.get('GB-PL-AXIS').dxf.linetype = 'CENTER' if 'CENTER' in doc.linetypes else 'Continuous'
STY = 'ROMANS' if 'ROMANS' in doc.styles else 'Standard'
WIN = PJ[P0]['win']
# ---------------------------------------------------------------- remove the source copy (plan + CONC DIM windows)
cache = bbox.Cache(); n_del = 0
for e in list(msp):
    lay = e.dxf.layer
    if not (any(lay.startswith(p_) for p_ in K.layers['purge_prefixes']) or lay == 'GB-CD'): continue
    try: b = bbox.extents([e], cache=cache)
    except Exception: continue
    if not b.has_data: continue
    x, y = b.center.x, b.center.y
    for k in ('PLAN', 'CD'):
        ox, oy = OFF[k]
        if WIN[0] - 3000 + ox <= x <= WIN[2] + 3000 + ox and WIN[1] - 3000 + oy <= y <= WIN[3] + 3000 + oy:
            msp.delete_entity(e); n_del += 1; break
print('source entities removed', n_del)
# ---------------------------------------------------------------- geometry (P1 frame)
def lrect(l): return box(l['a'], l['c'] - l['w'] / 2, l['b'], l['c'] + l['w'] / 2) if l['o'] == 'H' else box(l['c'] - l['w'] / 2, l['a'], l['c'] + l['w'] / 2, l['b'])
BEAMS = []; LINES = []
for pn, ls in LF.items():
    cov = set()
    for l in ls:
        if l.get('curved'): continue
        cov.update(l.get('merged', [l['code']])); LINES.append((pn, l)); BEAMS.append(toP1(lrect(l), pn))
    for l in RAW[pn]:
        if l['code'] not in cov: BEAMS.append(toP1(lrect(l), pn)); LINES.append((pn, dict(l, extra=True)))
COLS = []
for pn in LF:
    for c in PK[pn]['cols']:
        pg = Polygon(c)
        if pg.is_valid and pg.area > 2e4: COLS.append((pn, toP1(pg, pn)))
uc = unary_union([c for _, c in COLS])
colpolys = list(uc.geoms) if uc.geom_type == 'MultiPolygon' else [uc]
colpolys = [c.minimum_rotated_rectangle if c.area / c.minimum_rotated_rectangle.area > 0.97 else c for c in colpolys if c.area > 2e4]
CU = unary_union(colpolys)
UB = unary_union(BEAMS).buffer(1, join_style=2).buffer(-1, join_style=2)
BEAM_ONLY = UB.difference(CU)
ALL = unary_union([UB, CU])
# column labels: label of a support in the lines, else the nearest C-label of the part
CLAB = []
for c in colpolys:
    lab = None
    for pn, l in LINES:
        for q in l.get('sup', []):
            if 'x0' in q:
                r = toP1(box(q['x0'], q['y0'], q['x1'], q['y1']), pn)
                if r.centroid.distance(c.centroid) < 150: lab = q['lab'] if not q['lab'].startswith('COL ') else q['lab'].replace(' (NO LABEL)', ''); break
        if lab: break
    if not lab:
        best = None
        for pn in LF:
            for t, x, y in PK[pn]['labs']:
                if re.match(r'^C\d', t):
                    pt = toP1(Point(x, y), pn); dd = pt.distance(c)
                    if dd < 1500 and (best is None or dd < best[0]): best = (dd, t)
        lab = best[1] if best else ''
    CLAB.append(lab)

def poly_out(g, layer, dx, dy, closed=True):
    gs = list(g.geoms) if hasattr(g, 'geoms') else [g]
    for p_ in gs:
        if p_.geom_type != 'Polygon' or p_.is_empty: continue
        for ring in [p_.exterior] + list(p_.interiors):
            msp.add_lwpolyline([(x + dx, y + dy) for x, y in ring.coords[:-1]], close=True, dxfattribs={'layer': layer})

def tx(s, x, y, h, layer='GB-PL-TXT', rot=0, al=TA.MIDDLE_CENTER):
    t = msp.add_text(s, height=h, rotation=rot, dxfattribs={'layer': layer, 'style': STY}); t.set_placement((x, y), align=al); return t

ENG = None
if True:                                                           # the consultant geometry itself (P1 frame), arcs as polylines
    sh3 = dict(dx=0, dy=0)
    SRCE = []
    for v in ezdxf.recover.readfile(K.rotsrc(P0))[0].modelspace():
        if v.dxftype() == 'ARC':
            a0, a1 = v.dxf.start_angle, v.dxf.end_angle
            if a1 < a0: a1 += 360
            n = max(4, int((a1 - a0) / 2)); c = v.dxf.center; r = v.dxf.radius
            pts = [(c.x + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), c.y + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
            e2 = ezdxf.new().modelspace().add_lwpolyline(pts, dxfattribs={'layer': v.dxf.layer}); SRCE.append(e2)
        elif v.dxftype() == 'CIRCLE' and v.dxf.layer in LYC:
            c = v.dxf.center; r = v.dxf.radius
            e2 = ezdxf.new().modelspace().add_lwpolyline([(c.x + r * math.cos(math.radians(i * 10)), c.y + r * math.sin(math.radians(i * 10))) for i in range(37)], dxfattribs={'layer': v.dxf.layer}); SRCE.append(e2)
        else: SRCE.append(v)
    ENG = []
    for v in SRCE:
        if v.dxf.layer not in LYB and v.dxf.layer not in LYC: continue
        if v.dxftype() == 'LINE': pts = [(v.dxf.start.x - sh3['dx'], v.dxf.start.y - sh3['dy']), (v.dxf.end.x - sh3['dx'], v.dxf.end.y - sh3['dy'])]
        elif v.dxftype() == 'LWPOLYLINE':
            pts = [(q[0] - sh3['dx'], q[1] - sh3['dy']) for q in v.get_points()]
            if v.closed: pts.append(pts[0])
        else: continue
        ENG.append(('GB-PL-COL' if v.dxf.layer in LYC else 'GB-PL-BEAM', pts))
    print('engineer base entities', len(ENG))
def draw_base(k, labels=True):
    dx, dy = OFF[k]
    seen = set()
    for lay_, pts in ENG:
        key = (lay_, tuple((round(x), round(y)) for x, y in pts)); key2 = (lay_, key[1][::-1])
        if key in seen or key2 in seen: continue                        # duplicates removed
        seen.add(key); msp.add_lwpolyline([(x + dx, y + dy) for x, y in pts], dxfattribs={'layer': lay_})
    for c, lab in zip(colpolys, CLAB):
        h = msp.add_hatch(color=8, dxfattribs={'layer': 'GB-PL-COL-HATCH'}); h.set_pattern_fill('ANSI31', scale=15)
        h.paths.add_polyline_path([(x + dx, y + dy) for x, y in c.exterior.coords[:-1]], is_closed=True)
        if labels and lab:
            cx, cy = c.centroid.x, c.centroid.y; b_ = c.bounds
            tx(lab, cx + dx, b_[3] + dy + 260, 200)
    if labels:                                                     # beam type per span, beside the beam
        for pn, l in LINES:
            st = l.get('span_typ') or [l.get('typ', '')]
            sup = sorted(l.get('sup', []), key=lambda q: q['s0'])
            spans = [(q['s1'], r['s0']) for q, r in zip(sup, sup[1:])] or [(l['a'], l['b'])]
            prev = None
            for (s0, s1), t in zip(spans, st + [st[-1]] * len(spans)):
                if s1 - s0 < 800 or (t == prev and len(spans) > 1 and (s1 - s0) < 2500): prev = t; continue
                prev = t; m = (s0 + s1) / 2
                txt = f"{t or 'GB?'}-{round(l['w'] / 10)}X{HL}" + (' (RFI)' if l.get('held') else '')
                p0 = Point(m, l['c'] + l['w'] / 2 + 230) if l['o'] == 'H' else Point(l['c'] - l['w'] / 2 - 230, m)
                p0 = toP1(p0, pn); rot = (0 if l['o'] == 'H' else 90) + PJ[pn]['ang'] - A1
                tx(txt, p0.x + dx, p0.y + dy, 190, rot=rot)

# ---------------------------------------------------------------- PLAN + CD + SOG
draw_base('PLAN')
CURVED = bool(ZC.get('curves', True)) and os.path.exists(K.zdir('curves.json'))
if CURVED:                                                         # curved beams: section letter + type on the curve (developed sections)
    GS = json.load(open(BW + '/gbsec.json'))
    secof = {}
    for sh_ in GS['sheets']:
        for mc in (sh_.get('members') or [sh_.get('line')]): secof[mc] = sh_.get('sec')
    for cv in json.load(open(K.zdir('curves.json'))):
        lnc = rotate(LineString(cv['pts']), -A1, origin=(0, 0)); mp = lnc.interpolate(0.5, normalized=True)
        q = lnc.interpolate(0.52, normalized=True); ang_ = math.degrees(math.atan2(q.y - mp.y, q.x - mp.x))
        if ang_ > 90: ang_ -= 180
        if ang_ < -90: ang_ += 180
        sec_ = secof.get(cv['code'], '?')
        if ZC.get('curve_marks', 'convex') == 'convex':            # bubble on the convex side, caption on the concave side (no text on the column labels)
            cs_ = list(lnc.coords); chm = ((cs_[0][0] + cs_[-1][0]) / 2, (cs_[0][1] + cs_[-1][1]) / 2); ux, uy = mp.x - chm[0], mp.y - chm[1]; nn = math.hypot(ux, uy) or 1; ux, uy = ux / nn, uy / nn
            bxy = (mp.x + ux * 900, mp.y + uy * 900); cxy = (mp.x - ux * 2200, mp.y - uy * 2200)
        else:
            bxy = (mp.x, mp.y + 900); cxy = (mp.x, mp.y - 450)
        msp.add_circle(bxy, 420, dxfattribs={'layer': 'GB-SEC'})
        tx(sec_, bxy[0], bxy[1], 300, 'GB-SEC')
        tx(f"{cv['code']} CURVED (DEVELOPED L={cv['L']})", cxy[0], cxy[1], 170, rot=ang_)
draw_base('CD')
dxc, dyc = OFF['CD']
# axes per part and orientation: clusters of beam centre lines
ds_name = next((d.dxf.name for d in doc.dimstyles if d.dxf.name.upper() in ('GBSEC125', 'GBSEC100')), 'Standard')
AX = []
DOV = {'dimlfac': 1.0, 'dimdec': 0, 'dimscale': 125, 'dimtxt': 2.0, 'dimasz': 1.5}
FF = 0
if True:                                                          # face to face between opposite parallel beams (engineer R03), every pair once
    for pn in LF:
        ls = [l for p_, l in LINES if p_ == pn]
        done = set()
        for l in ls:
            for side in (1, -1):
                f1 = l['c'] + side * l['w'] / 2
                cands = []
                for m in ls:
                    if m is l or m['o'] != l['o']: continue
                    f2 = m['c'] - side * m['w'] / 2
                    gap = (f2 - f1) * side
                    ov0, ov1 = max(l['a'], m['a']), min(l['b'], m['b'])
                    if gap > 150 and ov1 - ov0 > 400: cands.append((gap, m, f2, ov0, ov1))
                if not cands: continue
                gap, m, f2, ov0, ov1 = min(cands, key=lambda t: t[0])
                key = tuple(sorted((l['code'], m['code'])))
                if key in done: continue
                done.add(key)
                u = (ov0 + ov1) / 2
                if l['o'] == 'H': p1, p2 = Point(u, f1), Point(u, f2)
                else: p1, p2 = Point(f1, u), Point(f2, u)
                p1, p2 = toP1(p1, pn), toP1(p2, pn)
                d = msp.add_aligned_dim(p1=(p1.x + OFF['CD'][0], p1.y + OFF['CD'][1]), p2=(p2.x + OFF['CD'][0], p2.y + OFF['CD'][1]), distance=0,
                                        dimstyle=next((d.dxf.name for d in doc.dimstyles if d.dxf.name.upper() in ('GBSEC125', 'GBSEC100')), 'Standard'),
                                        override={'dimlfac': 1.0, 'dimdec': 0, 'dimscale': 125, 'dimtxt': 1.8, 'dimasz': 1.4}, dxfattribs={'layer': 'GB-PL-DIM'})
                d.render(); FF += 1
    print('face to face dims', FF)
print('axes', AX)
# SOG panels: closed areas between the beams
dxs, dys = OFF['SOG']
draw_base('SOG', labels=False)
holes = []
gs = list(ALL.geoms) if hasattr(ALL, 'geoms') else [ALL]
for g in gs:
    for r in g.interiors:
        pg = Polygon(r)
        if pg.area > 1.0e6: holes.append(pg)
if True:                                                          # every closed area between the beams (consultant geometry incl. curves)
    from shapely.ops import polygonize as _pz
    UU = unary_union([LineString(pts).buffer(150, cap_style=2) for _, pts in ENG if len(pts) > 1] + [ALL.buffer(150, join_style=2)])
    faces = []
    for g in getattr(UU, 'geoms', [UU]):
        for r in g.interiors:
            f = Polygon(r).buffer(150, join_style=2)                    # back to the beam faces
            if f.area > 1.5e6 and f.area / f.length > 250: faces.append(f)
    holes = sorted(faces, key=lambda f: -f.area)
    print('SOG faces', len(holes))
if os.path.exists(K.zdir('sog_eng.json')):                      # engineer-drawn SOG panels (model coordinates of the SOG copy)
    from shapely.geometry import Polygon as _Pg
    for pts in json.load(open(K.zdir('sog_eng.json'))):
        pg = _Pg([(x - dxs, y - dys) for x, y in pts]).buffer(0)
        holes = [h for h in holes if h.intersection(pg).area < 0.2 * h.area] + [pg]
    print('SOG engineer panels added')
holes.sort(key=lambda p_: (-round(p_.centroid.y / 3000), p_.centroid.x))
for i, pg in enumerate(holes):
    e = msp.add_lwpolyline([(x + dxs, y + dys) for x, y in pg.exterior.coords[:-1]], close=True, dxfattribs={'layer': 'GB-SOG', 'color': 5})
    c = pg.representative_point()
    tx(f'SOG-{i + 1:02d}', c.x + dxs, c.y + dys + 180, 300, 'GB-SOG-TXT')
    tx(f'A = {pg.area / 1e6:.2f} m2', c.x + dxs, c.y + dys - 250, 200, 'GB-SOG-TXT')
print('SOG panels', len(holes))
json.dump([dict(name=f'SOG-{i + 1:02d}', area=round(pg.area / 1e6, 2), pts=[(round(x), round(y)) for x, y in pg.exterior.coords]) for i, pg in enumerate(holes)],
          open(BW + '/sog_panels.json', 'w'))
# ---------------------------------------------------------------- typical details from the engineer's file
TY = K.C['typical']
eng = ezdxf.recover.readfile(K.p(TY['dxf']))[0]
em = eng.modelspace()
XW = TY.get('explode_window')                                     # blocks inserted in this window: exploded (dims / leaders as plain geometry)
for ins in list(em.query('INSERT')):                              # the typical detail block: exploded, dimensions / leaders as plain geometry
    if not XW or not (XW[0] < ins.dxf.insert.x < XW[2] and XW[1] < ins.dxf.insert.y < XW[3]): continue
    for v in ins.virtual_entities():
        if v.dxftype() in ('DIMENSION', 'LEADER', 'MLEADER', 'INSERT'):
            try:
                for w in v.virtual_entities():
                    if w.dxftype() not in ('POINT',): em.add_entity(w)
            except Exception as ex: print('explode', v.dxftype(), ex)
        else: em.add_entity(v)
    em.delete_entity(ins)
TW = tuple(TY['window'])
ents = []
ec = bbox.Cache()
for e in eng.modelspace():
    try: b = bbox.extents([e], cache=ec)
    except Exception: continue
    if b.has_data and TW[0] <= b.center.x <= TW[2] and TW[1] <= b.center.y <= TW[3]: ents.append(e)
busy = [e for e in msp if (lambda b: b.has_data and TW[0] <= b.center.x <= TW[2] and TW[1] <= b.center.y <= TW[3])(bbox.extents([e], cache=cache))]
imp = Importer(eng, doc); imp.import_entities(ents, msp); imp.finalize()
print('typical entities', len(ents), 'busy before', len(busy))
# ---------------------------------------------------------------- new layouts (frame as the PLAN sheet)
plan_lay = next(l for l in doc.layouts if l.name.startswith(f'{ZN}-GB-{FIRST + 1} '))
def clone_sheet(no, tabname, t2, caption, mwin, scale):
    L = doc.layouts.new(f'{ZN}-GB-{no} {tabname}')
    L.page_setup(size=(841, 594), margins=(0, 0, 0, 0), units='mm')
    for e in plan_lay:
        if e.dxftype() == 'VIEWPORT': continue
        c = e.copy()
        if c.dxftype() == 'TEXT':
            t = c.dxf.text
            if t == 'REINFORCEMENT PLAN': c.dxf.text = t2
            elif t == str(FIRST + 1): c.dxf.text = str(no)
            elif f'-{FIRST + 1}-' in t: c.dxf.text = t.replace(f'-{FIRST + 1}-', f'-{no}-')
            elif t.startswith('GRADE BEAM REINFORCEMENT PLAN'): c.dxf.text = caption
        L.add_entity(c)
    w, h = (mwin[2] - mwin[0]) / scale, (mwin[3] - mwin[1]) / scale
    v = L.add_viewport(center=(12 + 712 / 2, 590 - 568 / 2), size=(min(w, 712), min(h, 568)), view_center_point=((mwin[0] + mwin[2]) / 2, (mwin[1] + mwin[3]) / 2), view_height=min(h, 568) * scale)
    v.dxf.status = 2; v.dxf.layer = 'GB-VPORT'
    return L
pv = next(e for e in plan_lay if e.dxftype() == 'VIEWPORT' and e.dxf.view_height > 5000)
sc = pv.dxf.view_height / pv.dxf.height
vc = pv.dxf.view_center_point
mwin = (vc.x - pv.dxf.width * sc / 2, vc.y - pv.dxf.height * sc / 2 + OFF['SOG'][1], vc.x + pv.dxf.width * sc / 2, vc.y + pv.dxf.height * sc / 2 + OFF['SOG'][1])
SN = ZC.get('sog_note') or ''
L1 = clone_sheet(FIRST + 2, 'SOG PLAN', 'S.O.G SLABS IDENTIFICATION PLAN', f'S.O.G SLABS BETWEEN THE GRADE BEAMS - ZONE {ZN} (LAYER GB-SOG, BLUE, CLOSED OUTLINES = INNER FACES OF THE BEAMS)' + ((' - ' + K.fmt(SN)) if SN else '') + f'   SCALE 1:{round(sc)}', mwin, sc)
TSC = TY.get('scale', 85)
L2 = clone_sheet(FIRST + 3, 'TYPICAL DETAILS', TY.get('t2', 'TYPICAL DETAILS + GB SCHEDULE'), K.fmt(TY.get('caption', 'TYPICAL DETAIL OF CONTINUOUS GROUND BEAM R.F.T. + GROUND BEAM SCHEDULE')) + f'   SCALE 1:{TSC}', TW, TSC)
if True:                                                           # plan windows fitted to the whole zone (all wings)
    xs_ = [x for _, pts in ENG for x, _ in pts]; ys_ = [y for _, pts in ENG for _, y in pts]
    X0_, X1_, Y0_, Y1_ = min(xs_) - 2500, max(xs_) + 2500, min(ys_) - 2500, max(ys_) + 2500
    for l in doc.layouts:
        k_ = 'CD' if l.name.endswith('CONC DIM') else 'PLAN' if l.name.endswith(' PLAN') and 'SOG' not in l.name else 'SOG' if 'SOG PLAN' in l.name else None
        if not k_: continue
        vps = [e for e in l if e.dxftype() == 'VIEWPORT']
        v = max(vps[1:] or vps, key=lambda e: e.dxf.view_height)
        dx_, dy_ = OFF[k_]; w_, h_ = X1_ - X0_, Y1_ - Y0_
        sc_ = 25 * math.ceil(max(w_ / 700, h_ / 560) / 25)
        v.dxf.width = w_ / sc_; v.dxf.height = h_ / sc_; v.dxf.center = (12 + w_ / sc_ / 2, 590 - h_ / sc_ / 2)
        v.dxf.view_center_point = ((X0_ + X1_) / 2 + dx_, (Y0_ + Y1_) / 2 + dy_, 0); v.dxf.view_height = h_
        for t_ in l.query('TEXT'):
            if 'SCALE 1:' in t_.dxf.text: t_.dxf.text = t_.dxf.text.rsplit('SCALE 1:', 1)[0] + f'SCALE 1:{sc_}'; t_.dxf.insert = (14, 590 - h_ / sc_ - 8)
if os.path.exists(K.zdir('eng_add.json')):                      # beams drawn by the engineer on the issued plan -> every plan copy
    EA = json.load(open(K.zdir('eng_add.json')))
    for k_ in ('PLAN', 'CD', 'SOG'):
        ox_, oy_ = OFF[k_]
        for (x0_, y0_), (x1_, y1_) in EA['lines']: msp.add_line((x0_ + ox_, y0_ + oy_), (x1_ + ox_, y1_ + oy_), dxfattribs={'layer': 'GB-PL-BEAM'})
        if k_ != 'SOG':
            for t_, x_, y_, r_ in EA['texts']: tx(t_, x_ + ox_, y_ + oy_, 190, 'GB-PL-TXT', rot=r_)
if CURVED: exec(open(os.path.join(HERE, 'post_curved.py')).read())     # curved bars sheet (FIRST + 4)
# tab order: CONC DIM, PLAN, SOG, TYPICAL, sections, BBS
names = [l.name for l in doc.layouts if l.name != 'Model']
def key(n):
    m = re.search(rf'{ZN}-GB-(\d+)', n); return int(m.group(1)) if m else 99999
for i, n in enumerate(sorted(names, key=key)): doc.layouts.get(n).dxf.taborder = i + 1
for l in doc.layouts:
    for j, e in enumerate([e for e in l if e.dxftype() == 'VIEWPORT']): e.dxf.id = j + 1; e.dxf.status = j + 1
EMF = K.zdir('eng_marks.json'); EMOK = bool(ZC.get('use_eng_marks', True)) and os.path.exists(EMF)
if (len(LF) > 1 and ZC.get('wing_marks', False)) or EMOK:                                   # section marks of the other wings (P2..) on the P1-frame plan / engineer bubbles
    GS = json.load(open(BW + '/gbsec.json'))
    secs = {}
    for s_ in GS['sheets']:
        mem = s_.get('members') or []
        if s_.get('line') and s_.get('sec'): secs.setdefault(s_['line'], s_['sec'])
        for j, mc in enumerate(mem): secs[mc] = f"{s_['sec']}-{j + 1}" if len(mem) > 1 else s_['sec']
    W0 = PJ[P0]['win']; inwin = lambda x, y: W0[0] - 3000 <= x <= W0[2] + 3000 and W0[1] - 3000 <= y <= W0[3] + 3000
    placed = [(e.dxf.center.x, e.dxf.center.y) for e in msp.query('CIRCLE') if inwin(e.dxf.center.x, e.dxf.center.y)]
    boxes = []
    for e in msp.query('TEXT'):
        q_ = e.dxf.insert
        if not inwin(q_.x, q_.y): continue
        hh = e.dxf.height; w_ = len(e.dxf.text) * hh * 0.8; r_ = e.dxf.get('rotation', 0) % 180
        boxes.append(box(q_.x - w_ / 2 - 60, q_.y - hh, q_.x + w_ / 2 + 60, q_.y + hh) if r_ < 30 or r_ > 150 else box(q_.x - hh, q_.y - w_ / 2 - 60, q_.x + hh, q_.y + w_ / 2 + 60))
    BX = unary_union(boxes) if boxes else None; BM = unary_union(BEAMS)
    nmk = 0
    EM = json.load(open(EMF)) if EMOK else None
    if EM:                                                     # C1: the engineer's section bubbles on the issued plan -> every mark at his position
        for e in list(msp.query('CIRCLE TEXT LINE')):
            q_ = e.dxf.center if e.dxftype() == 'CIRCLE' else (e.dxf.insert if e.dxftype() == 'TEXT' else e.dxf.start)
            if e.dxf.layer == 'GB-SEC' and inwin(q_.x, q_.y): msp.delete_entity(e)
        placed = []
        ends = []
        for pn, l in LINES:
            if l.get('extra') or l['code'] not in secs: continue
            for e_ in (l['a'], l['b']):
                ends.append((pn, l, e_, toP1(Point((e_, l['c']) if l['o'] == 'H' else (l['c'], e_)), pn)))
        EMU = {}
        segl = {}
        for j_, (pn_, l_, e_, p_) in enumerate(ends): segl.setdefault(id(l_), []).append(j_)
        TG = EM.get('targets', EM['circles'])
        lead = [] if EM.get('mode') == 'dist' else [k_ for k_ in range(len(EM['circles'])) if math.dist(EM['circles'][k_], TG[k_]) > 1]
        for k_ in lead:                                           # 1) bubbles with a leader: the beam the leader tip touches, the bubble's side, end nearest the tip
            (cx_, cy_), (tx_, ty_) = EM['circles'][k_], TG[k_]
            cand_ = []
            for lid_, js_ in segl.items():
                pa_, pb_ = ends[js_[0]][3], ends[js_[1]][3]
                sg_ = LineString([(pa_.x, pa_.y), (pb_.x, pb_.y)])
                cand_.append((sg_.distance(Point(tx_, ty_)), sg_.distance(Point(cx_, cy_)), js_))
            m0_ = min(c_[0] for c_ in cand_) if cand_ else 9e9
            for c0_, c1_, js_ in sorted([c_ for c_ in cand_ if c_[0] < m0_ + 600], key=lambda c_: c_[1]) + sorted([c_ for c_ in cand_ if c_[0] >= m0_ + 600], key=lambda c_: c_[0]):
                if c0_ > 2500: break
                j_ = min(js_, key=lambda j_: math.dist((tx_, ty_), (ends[j_][3].x, ends[j_][3].y)))
                if j_ not in EMU.values(): EMU[k_] = j_; break
        rest = [k_ for k_ in range(len(EM['circles'])) if k_ not in EMU]          # 2) the others: global min distance to the free line ends
        _cm = {}
        for k_ in rest:
            for j_, (_, _, _, p_) in enumerate(ends):
                if j_ in EMU.values(): continue
                d_ = min(math.dist(EM['circles'][k_], (p_.x, p_.y)), math.dist(TG[k_], (p_.x, p_.y)))
                if d_ < 3500: _cm[k_, j_] = d_
        R_ = {}
        for (k_, j_), d_ in sorted(_cm.items(), key=lambda kv: kv[1]):
            if k_ not in R_ and j_ not in R_.values(): R_[k_] = j_
        C_ = lambda k_, j_: _cm.get((k_, j_), 1e7)
        for _it in range(200):
            imp_ = False
            for a_ in list(R_):
                for b_ in list(R_):
                    if a_ < b_ and C_(a_, R_[b_]) + C_(b_, R_[a_]) < C_(a_, R_[a_]) + C_(b_, R_[b_]) - 1: R_[a_], R_[b_] = R_[b_], R_[a_]; imp_ = True
            for k_ in rest:
                if k_ in R_: continue
                for a_ in list(R_):
                    alt_ = [j_ for (kk_, j_) in _cm if kk_ == a_ and j_ not in R_.values()]
                    if C_(k_, R_[a_]) < 1e6 and alt_: R_[k_] = R_[a_]; R_[a_] = min(alt_, key=lambda j_: C_(a_, j_)); imp_ = True; break
            if not imp_: break
        EMU.update({k_: j_ for k_, j_ in R_.items() if C_(k_, j_) < 1e6})
        for k_, j_ in EMU.items():
            cx_, cy_ = EM['circles'][k_]; pn, l, e_, p_ = ends[j_]
            msp.add_circle((cx_, cy_), 300, dxfattribs={'layer': 'GB-SEC', 'color': 4}); placed.append((cx_, cy_))
            t_ = msp.add_text(secs[l['code']], height=260 if len(secs[l['code']]) <= 2 else 150, dxfattribs={'layer': 'GB-SEC', 'color': 4, 'style': STY}); t_.set_placement((cx_, cy_), align=TA.MIDDLE_CENTER)
            tx_, ty_ = EM.get('targets', EM['circles'])[k_]
            dvx, dvy = cx_ - tx_, cy_ - ty_; dl = math.hypot(dvx, dvy) or 1
            if dl > 400: msp.add_line((tx_, ty_), (cx_ - dvx / dl * 300, cy_ - dvy / dl * 300), dxfattribs={'layer': 'GB-SEC', 'color': 4})
            nmk += 1
        done_ = {(id(ends[j_][1]), ends[j_][2]) for j_ in EMU.values()}
        print('engineer marks used', len(EMU), 'of', len(EM['circles']))
    for pn, l in LINES:
        if (pn == P0 and not EM) or l.get('extra') or l['code'] not in secs: continue
        for e_, sg in ((l['a'], -1), (l['b'], 1)):
            if EM and (id(l), e_) in done_: continue
            best = None
            for k_ in range(0, 8):
                for side in (1, -1):
                    u_ = e_ + sg * (450 + 650 * k_); v_ = side * (l['w'] / 2 + 420)
                    q = toP1(Point((u_, l['c'] + v_) if l['o'] == 'H' else (l['c'] + v_, u_)), pn)
                    cpt = q.buffer(320)
                    if any(math.dist((q.x, q.y), p_) < 680 for p_ in placed) or (BX is not None and cpt.intersects(BX)) or cpt.intersects(BM): continue
                    best = q; break
                if best: break
            if best is None: best = toP1(Point((e_ + sg * 450, l['c'] + l['w'] / 2 + 420) if l['o'] == 'H' else (l['c'] + l['w'] / 2 + 420, e_ + sg * 450)), pn)
            endp = toP1(Point((e_, l['c']) if l['o'] == 'H' else (l['c'], e_)), pn)
            dvx, dvy = best.x - endp.x, best.y - endp.y; dl = math.hypot(dvx, dvy) or 1
            if dl > 800: msp.add_line((endp.x, endp.y), (best.x - dvx / dl * 300, best.y - dvy / dl * 300), dxfattribs={'layer': 'GB-SEC', 'color': 4})
            placed.append((best.x, best.y))
            msp.add_circle((best.x, best.y), 300, dxfattribs={'layer': 'GB-SEC', 'color': 4})
            t_ = msp.add_text(secs[l['code']], height=260 if len(secs[l['code']]) <= 2 else 150, dxfattribs={'layer': 'GB-SEC', 'color': 4, 'style': STY}); t_.set_placement((best.x, best.y), align=TA.MIDDLE_CENTER)
            nmk += 1
    print('wing section marks', nmk)
if ZC.get('bubbles_off_texts', True):                            # section bubbles clear of the plan texts (column labels)
    _bx = []
    for t_ in msp.query('TEXT[layer=="GB-PL-TXT"]'):
        w_ = len(t_.dxf.text) * t_.dxf.height * 0.9; _bx.append((t_.dxf.insert.x - w_ / 2, t_.dxf.insert.y - t_.dxf.height, t_.dxf.insert.x + w_ / 2, t_.dxf.insert.y + t_.dxf.height))
    _hit = lambda x, y, r: any(not (x + r < b[0] or x - r > b[2] or y + r < b[1] or y - r > b[3]) for b in _bx)
    _tx = list(msp.query('TEXT[layer=="GB-SEC"]')); nmv = 0
    for c_ in msp.query('CIRCLE[layer=="GB-SEC"]'):
        x, y, r = c_.dxf.center.x, c_.dxf.center.y, c_.dxf.radius
        if not _hit(x, y, r): continue
        for k in range(1, 12):
            if not _hit(x + k * 250, y - k * 150, r): break
        dx_, dy_ = k * 250, -k * 150
        c_.dxf.center = (x + dx_, y + dy_)
        for t_ in _tx:
            if abs(t_.dxf.insert.x - x) < 5 and abs(t_.dxf.insert.y - y) < 5:
                t_.set_placement((x + dx_, y + dy_), align=TA.MIDDLE_CENTER)
        nmv += 1
    print('section bubbles moved off texts', nmv)
a = doc.audit(); print('audit', len(a.errors))
doc.saveas(OUT); print('saved', OUT)
