# exec'd inside post_r02.py: CURVED BEAMS sheet (FIRST + 4) - top / bottom bars drawn ALONG the curve
# (curved bars following the beam curvature, not straight bars with separate bends). Input <zone>/curves.json.
# Bars, marks and lengths are read back from the developed sections already in the file (same marks as the BBS).
from shapely.geometry import LineString as _LS, Point as _P, Polygon as _PG
_CV = json.load(open(K.zdir('curves.json')))
_GS = json.load(open(BW + '/gbsec.json'))
_ox = _GS['model_origin'][0]                                           # x of the developed sections (gen_gbsec model_origin)
_A = math.radians(-PJ[P0]['ang'])                                    # original -> plan (P1 frame)
_rp = lambda x, y: (x * math.cos(_A) - y * math.sin(_A), x * math.sin(_A) + y * math.cos(_A))
_titles = sorted([t for t in msp.query('TEXT') if t.dxf.layer == 'GB-SEC' and t.dxf.text.startswith('SECTION ') and '  -  ' in t.dxf.text and abs(t.dxf.insert.x - _ox) < 40000],
                 key=lambda t: t.dxf.insert.y)
_lab = [t for t in msp.query('TEXT') if re.match(r'^(TOP|BOTTOM) (ADDITIONAL )?BARS', t.dxf.text) and abs(t.dxf.insert.x - (_ox - 2600)) < 50]
_pl = [e for e in msp.query('LWPOLYLINE') if e.dxf.layer in ('GB-RFT-TOP', 'GB-RFT-BOT')]
_tx = [t for t in msp.query('TEXT') if abs(t.dxf.insert.x - _ox) < 40000]
_st = [e for e in msp.query('LINE') if e.dxf.layer == 'GB-STIR']
def _radii(pts):
    ln_ = _LS(pts); st = 1200; rs = []
    s_ = 0.0
    while s_ + 2 * st <= ln_.length:
        (x1, y1), (x2, y2), (x3, y3) = [(lambda q: (q.x, q.y))(ln_.interpolate(s_ + k * st)) for k in (0, 1, 2)]
        a_ = math.dist((x1, y1), (x2, y2)); b_ = math.dist((x2, y2), (x3, y3)); c_ = math.dist((x1, y1), (x3, y3))
        ar = abs((x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)) / 2
        if ar > 1: rs.append(a_ * b_ * c_ / (4 * ar))
        s_ += st
    out = []
    for r in rs:
        r = round(r / 100) * 100
        if not out or abs(out[-1] - r) > 600: out.append(r)
    return out
CVV = []
for cv in _CV:
    sup = cv['sup']; sh = 0
    if not sup or sup[0]['s0'] > 50: sh = 200
    elif sup[0]['s1'] - sup[0]['s0'] < 100: sh = 300
    _rep = cv['code']
    for _sh in _GS['sheets']:
        if cv['code'] in (_sh.get('members') or []): _rep = _sh.get('line', _rep)
    T = next(t for t in _titles if f"({_rep})" in t.dxf.text or re.search(r'[(:,] ?' + re.escape(cv['code']) + r'[,)]', t.dxf.text))
    above = [t.dxf.insert.y for t in _titles if t.dxf.insert.y > T.dxf.insert.y + 100]
    ytop = min(above) if above else T.dxf.insert.y + 60000
    th = T.dxf.height / 1.6; sec = T.dxf.text.split()[1]
    rows = sorted([t for t in _lab if T.dxf.insert.y < t.dxf.insert.y < ytop], key=lambda t: -t.dxf.insert.y)
    bars = []
    for k, rt in enumerate(rows):
        pos = 'T' if rt.dxf.text.startswith('TOP') else 'B'
        yb = rt.dxf.insert.y + th * 0.4
        for e in _pl:
            pts = [(p[0], p[1]) for p in e.get_points()]
            hz = [(p, q) for p, q in zip(pts, pts[1:]) if abs(p[1] - q[1]) < 1 and abs(p[0] - q[0]) > 50]
            if not hz: continue
            (p, q) = max(hz, key=lambda s_: abs(s_[0][0] - s_[1][0]))
            if abs(p[1] - yb) > 520 or not (_ox - 100 <= min(p[0], q[0]) and max(p[0], q[0]) <= _ox + cv['L'] + 800): continue
            u0, u1 = sorted((p[0] - _ox, q[0] - _ox)); yy = p[1]
            um = u0 + min(1500, (u1 - u0) * 0.15)
            cand = [t for t in _tx if re.match(r'^\d+ T\d+-\d+', t.dxf.text) and abs(t.dxf.insert.y - (yy + th * 1.6)) < th * 0.6 and abs(t.dxf.insert.x - (_ox + um + th * 1.45)) < th * 2]
            mk = [t for t in _tx if re.fullmatch(r'\d{1,3}', t.dxf.text) and math.dist((t.dxf.align_point.x if t.dxf.halign else t.dxf.insert.x, t.dxf.align_point.y if t.dxf.halign else t.dxf.insert.y), (_ox + um, yy + th * 2.0)) < th * 1.2]
            call = cand[0].dxf.text.split('   ')[0] if cand else ''
            bars.append(dict(pos=pos, row=k, u0=u0, u1=u1, call=call, mark=mk[0].dxf.text if mk else '', add='ADDITIONAL' in rt.dxf.text))
    lsec_y = rows[0].dxf.insert.y if rows else T.dxf.insert.y
    stir = sorted({round(e.dxf.start.x - _ox) for e in _st if lsec_y < min(e.dxf.start.y, e.dxf.end.y) < ytop and -50 <= e.dxf.start.x - _ox <= cv['L'] + 600 and abs(e.dxf.start.x - e.dxf.end.x) < 1})
    pts = [_rp(*p) for p in (json.loads(cv['pts']) if isinstance(cv['pts'], str) else cv['pts'])]
    CVV.append(dict(cv=cv, sh=sh, sec=sec, bars=bars, stir=stir, pts=pts, radii=_radii((json.loads(cv['pts']) if isinstance(cv['pts'], str) else cv['pts'])[1:-1] if cv.get('ext') else (json.loads(cv['pts']) if isinstance(cv['pts'], str) else cv['pts']))))
    print('curved', cv['code'], sec, 'bars', len(bars), 'stirrups', len(stir), 'R', CVV[-1]['radii'])
# ---- drawing (model space, far below the SOG copy)
for nm_, col_ in (('GB-CRV-CONC', 7), ('GB-CRV-TOP', 1), ('GB-CRV-BOT', 5), ('GB-CRV-STIR', 3), ('GB-CRV-TXT', 7)):
    if nm_ not in doc.layers: doc.layers.add(nm_, color=col_)
def _ext(line, s0, s1):                                                # substring along the centre line, straight extension past the ends
    L_ = line.length; cs = list(line.coords)
    def at(s):
        if s < 0:
            (x0, y0), (x1, y1) = cs[0], cs[1]; d_ = math.dist(cs[0], cs[1]); return (x0 + (x0 - x1) / d_ * -s, y0 + (y0 - y1) / d_ * -s)
        if s > L_:
            (x0, y0), (x1, y1) = cs[-2], cs[-1]; d_ = math.dist(cs[-2], cs[-1]); return (x1 + (x1 - x0) / d_ * (s - L_), y1 + (y1 - y0) / d_ * (s - L_))
        p = line.interpolate(s); return (p.x, p.y)
    n = max(2, int(abs(s1 - s0) / 100))
    return [at(s0 + (s1 - s0) * i / n) for i in range(n + 1)]
def _off(pts, d):                                                      # offset a polyline sideways (left normal) by d
    out = []
    for i, (x, y) in enumerate(pts):
        a_ = pts[max(0, i - 1)]; b_ = pts[min(len(pts) - 1, i + 1)]
        dx, dy = b_[0] - a_[0], b_[1] - a_[1]; L_ = math.hypot(dx, dy) or 1
        out.append((x - dy / L_ * d, y + dx / L_ * d))
    return out
def _txt(s, x, y, h, lay, rot=0):
    t_ = msp.add_text(s, height=h, rotation=rot, dxfattribs={'layer': lay, 'style': STY}); t_.set_placement((x, y), align=TA.MIDDLE_LEFT); return t_
# layout: one row per curve, TOP | BOTTOM views; scale chosen to fit the sheet, text sized to it
_rows = []
for V in CVV:
    xs = [p[0] for p in V['pts']]; ys = [p[1] for p in V['pts']]
    _rows.append((max(max(xs) - min(xs) + 2000, 7200), max(ys) - min(ys) + 2000))
_LBL = 4200; _GAP = 1500
for _sc in (40, 50, 60, 75, 100, 125):
    th = 2.5 * _sc
    W_ = max(2 * (w_ + _LBL) + _GAP for w_, h_ in _rows); H_ = sum(h_ + th * 6 + _GAP for w_, h_ in _rows) + th * 2.2 * 7
    if W_ / _sc <= 700 and H_ / _sc <= 555: break
views = []; ycur = -260000; X00 = 0
for V, (rw, rh) in zip(CVV, _rows):
    cv = V['cv']; line = _LS(V['pts']); w = cv['w']; Ld = line.length; sh = V['sh']
    xs = [p[0] for p in V['pts']]; ys = [p[1] for p in V['pts']]
    cxm, cym = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    for vi, pos in enumerate(('T', 'B')):
        dx = X00 + vi * (rw + _LBL + _GAP) + _LBL * 0.75 + 1000 - min(xs); dy = ycur - max(ys) - 1000
        Tr = lambda p: (p[0] + dx, p[1] + dy)
        cl = _ext(line, -sh, Ld + 200)
        for sd in (w / 2, -w / 2): msp.add_lwpolyline([Tr(p) for p in _off(cl, sd)], dxfattribs={'layer': 'GB-CRV-CONC'})
        msp.add_lwpolyline([Tr(p) for p in cl], dxfattribs={'layer': 'GB-PL-AXIS'})
        for q in cv['sup']:
            a_, b_ = q['s0'], q['s1']
            if b_ - a_ < 50: b_ = a_ + 300
            poly = _off(_ext(line, a_, b_), w / 2 + 150) + _off(_ext(line, a_, b_), -w / 2 - 150)[::-1]
            msp.add_lwpolyline([Tr(p) for p in poly], close=True, dxfattribs={'layer': 'GB-CRV-CONC'})
            h_ = msp.add_hatch(dxfattribs={'layer': 'GB-PL-COL-HATCH'}); h_.set_pattern_fill('ANSI31', scale=10); h_.paths.add_polyline_path([Tr(p) for p in poly], is_closed=True)
        bs = sorted([b for b in V['bars'] if b['pos'] == pos], key=lambda b: (b['u0'] + b['u1']) / 2)
        rws = sorted({b['row'] for b in bs}); lay = 'GB-CRV-TOP' if pos == 'T' else 'GB-CRV-BOT'
        used = []
        for b in bs:
            k = rws.index(b['row']); n_ = len(rws)
            off = (-w / 2 + 55 + (w - 110) * k / max(1, n_ - 1)) if n_ > 1 else 0
            s0, s1 = b['u0'] - sh, b['u1'] - sh
            pl = [Tr(p) for p in _off(_ext(line, s0, s1), off)]
            msp.add_lwpolyline(pl, dxfattribs={'layer': lay, 'const_width': max(14, _sc * 0.25)})
            for e_ in (pl[0], pl[-1]): msp.add_circle(e_, _sc * 0.6, dxfattribs={'layer': lay})          # bar ends
            sm = (s0 + s1) / 2; mid = Tr(_off(_ext(line, sm - 1, sm + 1), off)[0])
            pa = _off(_ext(line, sm - 1, sm + 1), 1)[0]; c0 = _ext(line, sm - 1, sm + 1)[0]
            sg = 1 if math.dist(pa, (cxm, cym)) > math.dist(c0, (cxm, cym)) else -1        # outward (convex) side
            d_ = w / 2 + th * 2; tw_ = (len(b['call']) + 10) * th * 0.85
            for _i in range(40):
                q_ = Tr(_off(_ext(line, sm - 1, sm + 1), sg * d_)[0])
                rgt = q_[0] >= mid[0]
                bb_ = (q_[0], q_[1] - th * 0.8, q_[0] + tw_, q_[1] + th * 0.8) if rgt else (q_[0] - tw_, q_[1] - th * 0.8, q_[0], q_[1] + th * 0.8)
                if all(bb_[2] < u_[0] or bb_[0] > u_[2] or bb_[3] < u_[1] or bb_[1] > u_[3] for u_ in used): break
                d_ += th * 1.7
            used.append(bb_)
            msp.add_line(mid, q_, dxfattribs={'layer': 'GB-CRV-TXT'})
            t_ = msp.add_text(f"({b['mark']}) {b['call']}" + (' ADD' if b['add'] else ''), height=th, dxfattribs={'layer': 'GB-CRV-TXT', 'style': STY})
            t_.set_placement((q_[0] + (th * 0.4 if q_[0] >= mid[0] else -th * 0.4), q_[1]), align=TA.MIDDLE_LEFT if q_[0] >= mid[0] else TA.MIDDLE_RIGHT)
        if pos == 'T':
            for u in V['stir']:
                pr = _ext(line, u - sh - 1, u - sh + 1)
                msp.add_line(Tr(_off(pr, w / 2 - 30)[0]), Tr(_off(pr, -w / 2 + 30)[0]), dxfattribs={'layer': 'GB-CRV-STIR'})
        bx0 = X00 + vi * (rw + _LBL + _GAP); by0 = dy + min(ys) - 1000
        _txt(f"{cv['code']} (SECTION {V['sec']}) - {'TOP BARS' if pos == 'T' else 'BOTTOM BARS'} ALONG THE CURVE" + (' + RADIAL STIRRUPS' if pos == 'T' else ''), bx0, by0 - th * 1.5, th * 1.6, 'GB-CRV-TXT')
        _txt(f"R (CENTRE LINE) = {' / '.join(f'{r / 1000:.1f}' for r in V['radii'][:5])} m,  DEVELOPED L = {round(Ld)}", bx0, by0 - th * 3.6, th, 'GB-CRV-TXT')
        views.append((bx0, by0 - th * 4.5, bx0 + rw + _LBL, dy + max(ys) + 1000))
    ycur = min(v[1] for v in views) - _GAP
CX0 = min(v[0] for v in views); CY0 = min(v[1] for v in views); CX1 = max(v[2] for v in views); CY1 = max(v[3] for v in views)
_notes = [K.fmt(s_, hook=ZC.get('hook') or 100) for s_ in K.get('curved_notes', [
          'NOTES - CURVED GRADE BEAMS:',
          '1. TOP AND BOTTOM BARS FOLLOW THE BEAM CURVE: EVERY BAR PRE-BENT TO THE RADIUS OF ITS BAR LINE BEFORE FIXING - NO STRAIGHT BARS WITH SEPARATE BENDS.',
          '2. BAR MARKS (n), LENGTHS, LAPS 60d AND END LEGS AS THE DEVELOPED SECTIONS AND THE BBS (LENGTH MEASURED ALONG THE BAR LINE); LEGS IN THE VERTICAL PLANE.',
          '3. STIRRUPS RADIAL (PERPENDICULAR TO THE CURVE), SPACING MEASURED ON THE BEAM CENTRE LINE - SAME NUMBER AND ZONES AS THE DEVELOPED SECTION.',
          '4. CROSS SECTION, COVER 40 AND STIRRUP SHAPE (HOOKS 135 x {hook}): SEE THE CROSS SECTION ON THE DEVELOPED SECTION SHEET OF EACH CURVE.',
          '5. O = BAR END.  RED = TOP BARS, BLUE = BOTTOM BARS, GREEN = STIRRUPS.'])]
for i, s_ in enumerate(_notes): _txt(s_, CX0, CY0 - th * 1.5 - i * th * 2.2, th * (1.3 if i == 0 else 1.0), 'GB-CRV-TXT')
CY0 -= th * 2.2 * (len(_notes) + 1)
L3 = clone_sheet(FIRST + 4, 'CURVED BEAMS', 'CURVED GRADE BEAMS - CURVED REINFORCEMENT', f'CURVED GRADE BEAMS {" / ".join(c_["code"] for c_ in _CV)} - TOP AND BOTTOM BARS ALONG THE CURVE, RADIAL STIRRUPS   SCALE 1:{_sc}', (CX0, CY0, CX1, CY1), _sc)
_v = [e for e in L3 if e.dxftype() == 'VIEWPORT'][-1]
_v.dxf.width = (CX1 - CX0) / _sc; _v.dxf.height = (CY1 - CY0) / _sc; _v.dxf.center = (12 + _v.dxf.width / 2, 590 - _v.dxf.height / 2); _v.dxf.view_height = CY1 - CY0
_v.dxf.view_center_point = ((CX0 + CX1) / 2, (CY0 + CY1) / 2, 0)
for t_ in L3.query('TEXT'):
    if 'SCALE 1:' in t_.dxf.text: t_.dxf.insert = (14, 590 - _v.dxf.height - 8)
