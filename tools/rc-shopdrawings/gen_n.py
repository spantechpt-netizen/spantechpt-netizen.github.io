"""Column neck (starter) shop drawings: one A3 sheet per (column type, footing type) pair.
The bar arrangement and the tie shapes are read from the consultant's COLUMN SCHEDULE block, so the section
is the designer's own; the elevation runs from the footing (bars bent 90 deg on the bottom mesh) to the top of
the grade beams plus the column lap. Call-outs in the office format, BBS sheet at the end."""
import json, math, pickle, re, sys
import ezdxf
from ezdxf import recover
from gen import new_doc, Sheet, TA, callout, BarList, draw_legend, draw_bbs, lap, hooked_tie, opened_tie, fillet, tie_bar_centres, ST, mm, project_notes

PRJ = json.load(open(__import__('os').environ.get('RC_PROJECT', 'project.json')))
LEV = PRJ['levels']
ZONE = None                       # set per zone by gen_zone_necks (zone levels: project.json levels.zones)
COLC = 40                          # column cover (schedule note 4)
FC = PRJ.get('footing_cover', 70)


def read_schedule(dxf='main.dxf', block='COLUMN SCH'):
    """-> {type: dict(b, h, n, d, sets, dots=[(x,y)], ties=[(pts, closed)])} in mm, origin = section corner."""
    dxf = dxf or PRJ.get('dxf', 'main.dxf'); block = block or PRJ.get('column_schedule_block', 'COLUMN SCH')
    doc, _ = recover.readfile(dxf)
    ins = [e for e in doc.modelspace().query('INSERT') if e.dxf.name == block][0]
    ents = list(ins.virtual_entities())
    txt = [((v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text).strip(), v.dxf.insert.x, v.dxf.insert.y)
           for v in ents if v.dxftype() in ('TEXT', 'MTEXT')]
    types = sorted([t for t in txt if t[0] in ('C',) or (t[0].startswith('C') and t[0][1:].isdigit())], key=lambda t: -t[2])
    out = {}
    for i, (name, tx, ty) in enumerate(types):
        y_hi = (types[i - 1][2] + ty) / 2 if i else ty + 3000
        y_lo = (types[i + 1][2] + ty) / 2 if i + 1 < len(types) else ty - 6000
        inrow = lambda y: y_lo < y < y_hi
        outl = [v for v in ents if v.dxftype() == 'LWPOLYLINE' and v.dxf.layer.endswith('CORE-COLS') and inrow(v.get_points()[0][1])]
        if not outl: continue
        p = [(q[0], q[1]) for q in outl[0].get_points()]
        x0, y0 = min(a for a, b in p), min(b for a, b in p)
        x1, y1 = max(a for a, b in p), max(b for a, b in p)
        bars = next((t[0] for t in txt if inrow(t[2]) and ' T ' in t[0] and 'STIRR' not in t[0]), '0 T 0')
        stir = next((t[0] for t in txt if (inrow(t[2]) or abs(t[2] - y_hi) < 2500) and 'STIRR' in t[0] and t[2] > ty - 3000), '')
        n, d = int(bars.split('T')[0]), int(bars.split('T')[1])
        sets = int(stir.split(':')[1].split('X')[0]) if ':' in stir else 1
        per_m = int(stir.split('X')[1].split('T')[0]) if 'X' in stir else 8
        # real size from the label in the plan is in cm; the drawn outline gives the scale of the block
        # real size from the plan labels (e.g. 'C1 30X80'): the long side is drawn along x in the schedule
        sz = PRJ.get('column_sizes', {}).get(name)
        if not sz: continue
        wd, ht = max(sz), min(sz)
        k = (x1 - x0) / wd
        mm = lambda a, b: ((a - x0) / k, (b - y0) / k)
        dots = [mm(v.dxf.center.x, v.dxf.center.y) for v in ents if v.dxftype() == 'CIRCLE'
                and x0 - 5 <= v.dxf.center.x <= x1 + 5 and y0 - 5 <= v.dxf.center.y <= y1 + 5]
        ties = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE' or not v.dxf.layer.endswith('COLS-STEL'): continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not all(x0 - 5 <= a <= x1 + 5 and y0 - 5 <= b <= y1 + 5 for a, b in q): continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 150: continue                                  # hook tails drawn as separate short polylines
            ties.append(([mm(a, b) for a, b in q], bool(v.closed)))
        # tie shapes as the designer drew them one by one beside the section (complete closed shapes)
        shapes = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE' or not v.dxf.layer.endswith('COLS-STEL'): continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not all(a > x1 + 500 and inrow(b) for a, b in q): continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 300: continue
            shapes.append(([((a - min(p[0] for p in q)) / k, (b - min(p[1] for p in q)) / k) for a, b in q], bool(v.closed)))
        if shapes:     # the tie sketches are drawn at their own scale: the largest one is the outer tie (size - 2 x cover)
            big = max(shapes, key=lambda t: max(p[0] for p in t[0]))
            r = (wd - 2 * COLC) / max(p[0] for p in big[0])
            shapes = [([(a * r, b * r) for a, b in q], c) for q, c in shapes]
        # tie set from the section (to scale): closed / open shapes -> their box; single straight legs are paired
        tieset, legs = [], []
        for pts, closed in ties:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            w_, h_ = max(xs) - min(xs), max(ys) - min(ys)
            if w_ < 15: legs.append((sum(xs) / len(xs), min(ys), max(ys), pts))
            else: tieset.append(dict(poly=list(pts)))                 # the tie exactly as drawn (open ends = hook corner)
        legs.sort()
        for a, b in zip(legs[0::2], legs[1::2]):                     # a tie drawn as two facing C-legs = one closed tie
            pa = sorted(a[3], key=lambda p: p[1]); pb = sorted(b[3], key=lambda p: -p[1])
            tieset.append(dict(poly=pa + pb))
        out[name] = dict(tieset=tieset, shapes=shapes, b=min(sz), h=max(sz), dw=wd, dh=ht, n=n, d=d, sets=sets, per_m=per_m, dots=dots, ties=ties)
    return out


def read_schedule2(dxf=None, block=None):
    """Generic reader of every row of the column schedule, whatever layers the row uses (nested blocks expanded):
    bar circles (de-duplicated, mirrored when the sketch omits symmetric bars), tie polylines around them."""
    dxf = dxf or PRJ.get('dxf', 'main.dxf'); block = block or PRJ.get('column_schedule_block', 'COLUMN SCH')
    doc, _ = recover.readfile(dxf)
    ins = [e for e in doc.modelspace().query('INSERT') if e.dxf.name == block][0]
    ents = []
    def rec(e, d=0):
        for v in e.virtual_entities():
            if v.dxftype() == 'INSERT' and d < 4: rec(v, d + 1)
            else: ents.append(v)
    rec(ins)
    txt = [((v.plain_text() if v.dxftype() == 'MTEXT' else v.dxf.text).strip(), v.dxf.insert.x, v.dxf.insert.y)
           for v in ents if v.dxftype() in ('TEXT', 'MTEXT')]
    types = sorted([t for t in txt if t[0] == 'C' or (t[0].startswith('C') and t[0][1:].isdigit())], key=lambda t: -t[2])
    out = {}
    for i, (name, tx, ty) in enumerate(types):
        y_hi = (types[i - 1][2] + ty) / 2 if i else ty + 3000
        y_lo = (types[i + 1][2] + ty) / 2 if i + 1 < len(types) else ty - 6000
        inrow = lambda y: y_lo < y < y_hi
        sz = PRJ.get('column_sizes', {}).get(name)
        bars = next((t[0] for t in txt if inrow(t[2]) and re.match(r'^\d+\s*T\s*\d+$', t[0])), None)
        stir = next((t[0] for t in txt if (inrow(t[2]) or abs(t[2] - y_hi) < 2500) and 'STIRR' in t[0] and t[2] > ty - 3000), '')
        if not sz or not bars: continue
        n, d = int(bars.split('T')[0]), int(bars.split('T')[1])
        sets = int(stir.split(':')[1].split('X')[0]) if ':' in stir else 1
        per_m = int(stir.split('X')[1].split('T')[0]) if 'X' in stir else 8
        circ = []
        for v in ents:
            if v.dxftype() == 'CIRCLE' and inrow(v.dxf.center.y):
                c = (v.dxf.center.x, v.dxf.center.y)
                if not any(math.dist(c, q) < 20 for q in circ): circ.append(c)
        if not circ: continue
        # the section is the left-most group of circles (tie sketches with dots may follow on the right)
        circ.sort()
        x0, y0 = min(c[0] for c in circ), min(c[1] for c in circ)
        span = max(sz) * 12                                     # generous: drawing scale is ~5-10 units / mm
        circ = [c for c in circ if c[0] - x0 < span]
        x1, y1 = max(c[0] for c in circ), max(c[1] for c in circ)
        if len(circ) < n:                                     # sketch shows one side only: mirror the missing bars
            for c in list(circ):
                for m_ in ((x0 + x1 - c[0], c[1]), (c[0], y0 + y1 - c[1]), (x0 + x1 - c[0], y0 + y1 - c[1])):
                    tol_ = 0.06 * min(x1 - x0, y1 - y0)          # ~ a bar diameter at the drawing's scale
                    if len(circ) < n and not any(math.dist(m_, q) < tol_ for q in circ): circ.append(m_)
        wd, ht = (max(sz), min(sz)) if (x1 - x0) >= (y1 - y0) else (min(sz), max(sz))
        e = COLC + 10 + d / 2
        k = ((x1 - x0) / max(1, wd - 2 * e) + (y1 - y0) / max(1, ht - 2 * e)) / 2
        mmf = lambda a, b: ((a - x0) / k + e, (b - y0) / k + e)
        dots = [mmf(*c) for c in circ]
        # sketches are imprecise: snap the bars to common rows / columns (within 20 mm)
        for ax_ in (0, 1):
            vals = sorted(set(round(p[ax_], 1) for p in dots)); grp = []
            for v_ in vals:
                if grp and v_ - grp[-1][-1] <= 20: grp[-1].append(v_)
                else: grp.append([v_])
            snap = {v_: sum(g) / len(g) for g in grp for v_ in g}
            dots = [tuple(snap[round(p[i], 1)] if i == ax_ else p[i] for i in (0, 1)) for p in dots]
        # bars along each face equally spaced between the corner bars (standard detailing; the sketch is approximate)
        mnx, mxx = min(p[0] for p in dots), max(p[0] for p in dots); mny, mxy = min(p[1] for p in dots), max(p[1] for p in dots)
        new = {}
        for ax_, lo_, hi_ in ((1, mny, mxy), (0, mnx, mxx)):
            for edge in (lo_, hi_):
                face = sorted([p for p in dots if abs(p[ax_] - edge) < 1], key=lambda p: p[1 - ax_])
                if len(face) > 2:
                    a0, a1 = face[0][1 - ax_], face[-1][1 - ax_]
                    for j, p in enumerate(face):
                        v_ = a0 + (a1 - a0) * j / (len(face) - 1)
                        new[p] = (v_, p[1]) if ax_ == 1 else (p[0], v_)
        dots_raw = dots
        dots = [new.get(p, p) for p in dots]
        ties = []
        for v in ents:
            if v.dxftype() != 'LWPOLYLINE': continue
            q = [(a, b) for a, b, *_ in v.get_points()]
            if not q or not all(x0 - 6 * 40 * k / 10 - 300 <= a <= x1 + 300 and y0 - 300 <= b <= y1 + 300 for a, b in q): continue
            if not inrow(q[0][1]) or v.dxf.layer.endswith(tuple(PRJ.get('sched_outline_layers', ['S-COLS-IDEN', 'CORE-COLS', 'CORE-COLS-CONC-SEC']))) or v.dxf.layer == 'column': continue
            L = sum(math.dist(q[j], q[j + 1]) for j in range(len(q) - 1)) + (math.dist(q[-1], q[0]) if v.closed else 0)
            if L / k < 150: continue
            xs_ = [a for a, b in q]; ys_ = [b for a, b in q]
            if (max(xs_) - min(xs_)) / k > wd + 50 or (max(ys_) - min(ys_)) / k > ht + 50: continue   # outline / frame
            ties.append(([mmf(a, b) for a, b in q], bool(v.closed)))
        tieset, legs = [], []
        for pts, closed in ties:
            xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
            if max(xs) - min(xs) < 15: legs.append((sum(xs) / len(xs), min(ys), max(ys), pts))
            elif max(ys) - min(ys) < 15: continue                  # straight horizontal piece (hook tail / link)
            else: tieset.append(dict(poly=list(pts)))
        legs.sort()
        for a_, b_ in zip(legs[0::2], legs[1::2]):
            pa = sorted(a_[3], key=lambda p: p[1]); pb = sorted(b_[3], key=lambda p: -p[1])
            tieset.append(dict(poly=pa + pb))
        out[name] = dict(tieset=tieset, shapes=[], b=min(sz), h=max(sz), dw=wd, dh=ht, n=n, d=d, sets=sets, per_m=per_m,
                         dots=dots, dots_raw=dots_raw, ties=ties)
    return out


def tie_length(pts, closed):
    L = sum(math.dist(pts[j], pts[j + 1]) for j in range(len(pts) - 1)) + (math.dist(pts[-1], pts[0]) if closed else 0)
    return int(round((L + 2 * 100) / 10) * 10)                 # + two 135-degree hooks of 100 mm


def draw_neck(doc, idx, col, f, meta, bl, no, members=None):
    """members: [(footing, no. of columns)] -> ONE generic sheet for the column type on all its footings (engineer,
    25-10-2026: footing VAR, neck H VAR; one neck-bar mark per bottom-mesh diameter, ties counted over the real columns).
    f is then the representative footing used for the drawing."""
    """col: schedule entry; f: footing entry from footings.json."""
    sh = Sheet(doc, 0, -idx * 32000, meta)
    draw_legend(sh, 21000, 27900)
    from gen import zone_levels, footing_levels
    ZL = zone_levels(ZONE)
    fl, tpc, tof = footing_levels(f['h'], ZL)
    tgb = ZL['top_gb']
    Hn = max(0, round((tgb - tof) * 1000))
    starter = Hn == 0                  # column starts at the footing (basement): starter bars, no neck
    LAPN, LDN = PRJ.get('neck_lap_d', 65), PRJ.get('neck_ld_d', 60)
    d = col['d']; lp = LAPN * d                                  # lap of the starters above T.O.F and of the neck bars above T.O.GB
    yb = FC + max(f['bot'][1], f['bot'][3]) * 2                 # bars stand on the bottom mesh
    # development inside the footing (engineer + general note: Ld >= 60 d, measured along the bar from T.O.F):
    # straight part in the footing + the 90-degree foot on the bottom mesh; the foot is lengthened to make it up
    emb = f['h'] - yb                                            # T.O.F -> bar on the mesh
    LD = LDN * d
    foot = max(12 * d, 300, int(math.ceil((LD - emb) / 10) * 10))
    xbar = (max(col['b'], col['h']) / 2 - COLC - 10 - d / 2)
    room = min(f.get('L', 1e9), f.get('W', 1e9)) / 2 - FC - xbar   # foot must stay inside the footing (cover)
    inward = foot > room                                          # no room outwards: feet turned inwards (under the column)
    room_in = min(f.get('L', 1e9), f.get('W', 1e9)) / 2 - FC + xbar
    ld_ok = emb + foot >= LD and foot <= (room_in if inward else room)
    # project rule (neck_mode 'single', e.g. Al Ruya): ONE bar per position - foot (neck_foot, 300) on the bottom mesh,
    # straight up to T.O.GB + lap (neck_lap_d x d); no separate starter / neck bar, no Ld rule beyond the given foot
    single = PRJ.get('neck_mode') == 'single' and not starter
    if single:
        foot = int(PRJ.get('neck_foot', 300)); inward = False; ld_ok = True
    # engineer (Oct 2026): STARTER bars anchored in the footing (Ld) and out 65 d above T.O.F; separate straight NECK
    # bars from T.O.F up to T.O.GB + 65 d (lapped with the starters above the footing, with the column above the GB)
    vert = emb + (Hn if single else 0) + lp
    Lv = int(round((vert + foot) / 10) * 10)
    model = []                                                    # (mesh d, vertical foot->T.O.GB, L, mark, no. of columns, footings)
    if members and single:
        grp = {}
        for fm, nm in members:
            dm = max(fm['bot'][1], fm['bot'][3]); g = grp.setdefault(dm, [0, []]); g[0] += nm; g[1].append(f"{fm['name']} ({nm})")
        for dm in sorted(grp):
            vv = round((tgb - (footing_levels(f['h'], ZL)[1])) * 1000) - (FC + dm * 2)      # T.O.PC -> T.O.GB - cover - mesh
            model.append(dict(dm=dm, v=vv, L=int(round(foot + vv + lp)), no=grp[dm][0], fts=grp[dm][1]))
        if PRJ.get('neck_unify_length'):        # engineer (BLSC): ONE cutting length per column type = the longest; the
            Lu = max(m_['L'] for m_ in model)    # extra length goes into the lap above T.O.GB (lap >= 65d everywhere)
            mk_u = bl.add(d, ('L', foot, Lu - foot, 0), Lu, col['n'], sum(m_['no'] for m_ in model), 'V')
            for m_ in model: m_['lap'] = Lu - foot - m_['v']; m_['L'] = Lu; m_['mk'] = mk_u
        else:
            for m_ in model:
                m_['lap'] = lp; m_['mk'] = bl.add(d, ('L', foot, m_['v'] + lp, 0), m_['L'], col['n'], m_['no'], 'V')
        rep_ = next(m for m in model if m['dm'] == max(f['bot'][1], f['bot'][3]))
        mv, Lv = rep_['mk'], rep_['L']; no = sum(nm for _, nm in members)
        if PRJ.get('neck_unify_length'): vert = Lv - foot
    else:
        mv = bl.add(d, ('L', foot, vert, 0), Lv, col['n'], no, 'V')
    Ln = int(round((Hn + lp) / 10) * 10)
    mn = None if (starter or single) else bl.add(d, ('S', Ln), Ln, col['n'], no, 'V')
    # bars: corner bars centred at cover + tie dia + d/2 from the faces, the others spaced as the designer drew them;
    # every tie wraps exactly the bars it holds in the designer's section, keeping its shape (rectangle, hexagon ...)
    from shapely.geometry import Polygon, MultiPoint, Point
    ds = 10
    W, H = col['dw'], col['dh']
    dx0, dy0 = min(p[0] for p in col['dots']), min(p[1] for p in col['dots'])
    dx1, dy1 = max(p[0] for p in col['dots']), max(p[1] for p in col['dots'])
    e = COLC + ds + d / 2
    T = lambda p: (e + (p[0] - dx0) * (W - 2 * e) / (dx1 - dx0) if dx1 > dx0 else W / 2,         # one row of bars (stair starter): on the centre line
                   e + (p[1] - dy0) * (H - 2 * e) / (dy1 - dy0) if dy1 > dy0 else H / 2)
    col['bars'] = [T(p) for p in col['dots']]
    hall = MultiPoint(col['bars']).convex_hull
    lim_cl, lim_oo = hall.buffer(d / 2 + ds / 2, join_style=2), hall.buffer(d / 2 + ds, join_style=2)
    ties = []
    for t in col['tieset']:
        pg = Polygon(t['poly']).buffer(0)
        held = [T(p) for p, r_ in zip(col['dots'], col.get('dots_raw', col['dots'])) if pg.buffer(20).contains(Point(r_))]   # held as drawn
        if len(held) < 2: continue
        hull = MultiPoint(held).convex_hull
        cl = hull.buffer(d / 2 + ds / 2, join_style=2).intersection(lim_cl).simplify(1)   # centre line, cut flat at the outer tie
        oo = hull.buffer(d / 2 + ds, join_style=2).intersection(lim_oo).simplify(1)                      # out-to-out (bending dimensions)
        if col.get('perimeter_tie'):                     # one row of bars (stair starter): a tie round the section at the cover
            from shapely.geometry import box as _box
            cl = _box(COLC + ds / 2, COLC + ds / 2, W - COLC - ds / 2, H - COLC - ds / 2)
            oo = _box(COLC, COLC, W - COLC, H - COLC)
        poly = [(round(x, 1), round(y, 1)) for x, y in list(cl.exterior.coords)[:-1]]
        out = [(round(x), round(y)) for x, y in list(oo.exterior.coords)[:-1]]
        xs = [p[0] for p in out]; ys = [p[1] for p in out]
        ties.append(dict(poly=out, w=round(max(xs) - min(xs)), hh=round(max(ys) - min(ys)),
                         L=int(round((oo.exterior.length + 2 * 100) / 10) * 10), draw=[(poly, True)]))   # out-to-out perimeter + two 135-deg hooks
    s = int(1000 / col['per_m'])
    n_neck = max(0, math.floor((Hn - 100) / s) + 1)              # first 50 above T.O.F .. last >= 50 below T.O.GB
    n_ftg = max(2, math.floor((emb - 100) / s) + 1)              # the footing at the same spacing: first 50 below T.O.F
    merged = {}
    def shape_key(t, flip):
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly']); mxx = max(p[0] for p in t['poly'])
        return sorted(((mxx - p[0]) if flip else (p[0] - mnx), p[1] - mny) for p in t['poly'])
    same = lambda a, b: len(a) == len(b) and all(min(math.dist(p, q) for q in b) <= 4 for p in a)
    for i_, t in enumerate(ties):       # identical ties (e.g. the two end hexagons, one turned over) share one mark
        k0 = shape_key(t, False)
        hit = next((m for m in merged.values() if same(k0, m['key']) or same(shape_key(t, True), m['key'])), None)
        if hit: hit['k'] += 1; hit['draw'] += t['draw']
        else: merged[i_] = dict(t, k=1, key=k0)
    ties = list(merged.values())
    for t in ties:
        mnx = min(p[0] for p in t['poly']); mny = min(p[1] for p in t['poly'])
        t['norm'] = [(round(p[0] - mnx), round(p[1] - mny)) for p in t['poly']]
        if model:                                                 # ties over the real columns: neck and footing parts per footing
            tot_ = 0; per = {}
            for fm, nm in members:
                _, _, tof_m = footing_levels(fm['h'], ZL); Hm = max(0, round((tgb - tof_m) * 1000))
                em = fm['h'] - (FC + max(fm['bot'][1], fm['bot'][3]) * 2)
                n_c = (max(0, math.floor((Hm - 100) / s) + 1) + max(2, math.floor((em - 100) / s) + 1)) * t['k']   # per column
                tot_ += n_c * nm; g_ = per.setdefault(n_c, [0, set()]); g_[0] += nm; g_[1].add(fm['h'])
            t['tot'] = tot_ // t['k']; t['per'] = per
            t['mk'] = bl.add(10, ('POLY',) + tuple(t['norm']), t['L'], tot_, 1, '')
            row_ = next(r_ for r_ in bl.rows.values() if r_['mark'] == t['mk'])     # exact rows per footing depth in the BBS
            row_.setdefault('split', {})[str(bl.cur)] = [(n_c, g_[0], 'FTG h' + '/'.join(str(h_) for h_ in sorted(g_[1]))) for n_c, g_ in sorted(per.items())]
        else:
            t['mk'] = bl.add(10, ('POLY',) + tuple(t['norm']), t['L'], (n_neck + n_ftg) * t['k'], no, '')

    title = f"{col['name']}  {col['b']}x{col['h']}" + ('' if model else f"  ON  {f['name']}")
    sh.text(col.get('title_prefix', 'STARTER BARS ' if starter else 'NECK ') + title, 2000, 27900, ST['name'], 'S-AXIS-TXT')
    if model:
        nft = sum(len(m_['fts']) for m_ in model)
        sh.text(f"ON {nft} FOOTING TYPES - {no} COLUMNS (LIST BELOW / KEY PLAN)", 2000, 26400, ST['sub'], 'S-SEC', maxw=18000)
        words = ', '.join(x for m_ in model for x in m_['fts']).split(' '); lines_, cur_ = [], ''
        for w_ in words:
            if len(cur_) + len(w_) > 95: lines_.append(cur_); cur_ = ''
            cur_ += w_ + ' '
        lines_.append(cur_)
        for j, ln_ in enumerate(lines_[:9]):
            sh.text(ln_.strip(), 7800, 24600 - j * 300, ST['note'] * 0.9, 'S-SEC', maxw=13500)
    else:
        sh.text(f"FOOTING {f['name']} " + (f"(COMBINED / RAFT / STRAP - SEE PLAN)  h={f['h']}" if f.get('part') else f"{f['L']}x{f['W']}x{f['h']}")
                + (f"  - {f['note']}" if f.get('note') else ''), 2000, 26400, ST['sub'], 'S-SEC', maxw=18000)
    if col.get('note'): sh.text(col['note'], 2000, 25800, ST['note'], 'S-SEC', maxw=18000)   # project remark (RFI)
    sh.text((f"NO={no}   T.O.F VAR   T.O.GB {tgb:+.2f}   NECK H = VAR   FOOTING THICKNESS VAR" if model else
             f"NO={no}   T.O.F {tof:+.2f}   " + ("COLUMN STARTS AT THE FOOTING (T.O.F = T.O.SLAB): STARTER BARS, NO NECK" if starter else
                                               f"T.O.GB {tgb:+.2f}   NECK H = {mm(Hn)}")), 2000, 27100, ST['sub'], 'S-SEC')

    # ---------- ELEVATION 1:25 (k=4) on the wide face ----------
    k = min(4.0, 21000 / (f['h'] + Hn + lp + 1400))
    ex, ey = 11000, 2600 + 100 * k
    Q = lambda x, y: (ex + x * k, ey + y * k)
    Lf = f['L']; cw = col['h'] if col['h'] >= col['b'] else col['b']          # wide face of the column
    fx0 = -Lf / 2
    # a wide footing is cut with break lines so the elevation stays inside the frame (engineer, Oct 2026)
    fxl, fxr = max(fx0, -(ex - 3200) / k), min(-fx0, (22300 - ex) / k)
    cutl, cutr = fxl > fx0 + 1, fxr < -fx0 - 1
    pl_, pr_ = fxl - (0 if cutl else 100), fxr + (0 if cutr else 100)
    sh.pline([Q(pl_, -100), Q(pr_, -100)], 'S-GB-CONC'); sh.pline([Q(pl_, 0), Q(pr_, 0)], 'S-GB-CONC')
    sh.pline([Q(fxl, f['h']), Q(fxr, f['h'])], 'S-GB-CONC')
    for xx_, cut_, pp_ in ((fxl, cutl, pl_), (fxr, cutr, pr_)):
        if cut_:
            yb0, yb1 = Q(0, -100)[1] - 150, Q(0, f['h'])[1] + 150; xs0 = Q(xx_, 0)[0]
            m_ = (yb0 + yb1) / 2; a_ = min(180, (yb1 - yb0) / 6)
            sh.pline([(xs0, yb0), (xs0, m_ - a_), (xs0 + 160, m_ - a_ / 3), (xs0 - 160, m_ + a_ / 3), (xs0, m_ + a_), (xs0, yb1)], 'S-SEC')
        else:
            sh.pline([Q(pp_, -100), Q(pp_, 0)], 'S-GB-CONC'); sh.pline([Q(xx_, 0), Q(xx_, f['h'])], 'S-GB-CONC')
    top = f['h'] + Hn
    sh.pline([Q(-cw / 2, f['h']), Q(-cw / 2, top), Q(cw / 2, top), Q(cw / 2, f['h'])], 'S-GB-CONC')
    gb_h = 700
    if starter:                                                      # the slab on the footing (top flush)
        gb_h = 200
        for sx in (-1, 1):
            sh.pline([Q(sx * cw / 2, top), Q(max(fxl - 600, -(ex - 1500) / k) if sx < 0 else min(fxr + 600, (22300 - ex) / k), top)], 'S-SEC')
    else:
        for sx in (-1, 1):                                           # grade beams framing in (dashed outline)
            sh.pline([Q(sx * cw / 2, top), Q(sx * (cw / 2 + 1500), top), Q(sx * (cw / 2 + 1500), top - gb_h), Q(sx * cw / 2, top - gb_h)], 'S-SEC')
    sh.break_line(Q(-cw / 2 - 300, top + lp + 200), Q(cw / 2 + 300, top + lp + 200))            # break line of the column above
    sh.pline([Q(-cw / 2, top), Q(-cw / 2, top + lp + 200)], 'S-GB-CONC'); sh.pline([Q(cw / 2, top), Q(cw / 2, top + lp + 200)], 'S-GB-CONC')
    # bottom mesh of the footing
    sh.pline([Q(fxl + (0 if cutl else FC), FC + 10), Q(fxr - (0 if cutr else FC), FC + 10)], 'S-RFT-BOT', 30)
    # vertical bars (two outer ones drawn), foot outwards on the mesh
    for sx in (-1, 1):
        x = sx * (cw / 2 - COLC - 10 - d / 2)
        xs_ = x if (starter or single) else x - sx * d * 1.6         # starter just inside the neck bar it laps with
        yb_ = yb - (0 if sx < 0 or not inward else d)
        sh.pline([Q(xs_ + (-sx if inward else sx) * foot, yb_), Q(xs_, yb_), Q(xs_, f['h'] + (Hn if single else 0) + lp)], 'S-RFT-TOP', max(d * k, 25), r=3 * d * k)
        if not (starter or single):
            sh.pline([Q(x, f['h']), Q(x, top + lp)], 'S-RFT-TOP', max(d * k, 25))
    # ties
    y = f['h'] + 50
    while y <= top - 50:
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR'); y += s
    yf_low = f['h'] - 50 - (n_ftg - 1) * s
    for j in range(n_ftg):                                       # ties in the footing at the same spacing
        y = f['h'] - 50 - j * s
        sh.line(Q(-cw / 2 + COLC, y), Q(cw / 2 - COLC, y), 'S-RFT-STIR')
    # distribution line of the ties: vertical line over the tie zone, ticks at the ties, leader to the call-outs
    xd = -cw / 2 + cw * 0.3
    y0d, y1d = f['h'] + 50, f['h'] + 50 + (n_neck - 1) * s
    sh.line(Q(xd, yf_low), Q(xd, max(y1d, f['h'] - 50)), 'S-DIM')
    for yy in (yf_low, f['h'] - 50) + ((y0d, (y0d + y1d) / 2, y1d) if n_neck else ()):
        sh.line(Q(xd - 25, yy - 25), Q(xd + 25, yy + 25), 'S-DIM')
    ylead = f['h'] + Hn * 0.55
    ya_ = f['h'] + Hn * 0.18
    yl_ = max(Q(0, ylead)[1], Q(0, ya_)[1] + 1900 + 520 * len(ties))           # to the first tie call-out
    sh.line(Q(xd, min(ylead, top - 60)), (Q(cw / 2 + 120, 0)[0], yl_ + 100), 'S-DIM')
    # section cut A-A
    ya = f['h'] + Hn * 0.18
    sh.line(Q(-cw / 2 - 600, ya), Q(cw / 2 + 600, ya), 'S-SEC')
    for sx_ in (-1, 1):
        sh.line(Q(sx_ * (cw / 2 + 600), ya), Q(sx_ * (cw / 2 + 600), ya + 200), 'S-SEC')
        sh.text('A', Q(sx_ * (cw / 2 + 650), 0)[0], Q(0, ya + 220)[1], 300, 'S-SEC', align=TA.BOTTOM_CENTER)
    # dims and levels
    XD = min(cw / 2 + 2500, (20800 - ex) / k)                       # dimension line clear of the call-outs, of section A-A and the tie sketches
    if not starter:
        sh.dim(Q(XD, f['h']), Q(XD, top), Q(XD + 400, f['h']), angle=90, text='VAR' if model else f'{Hn}')
    sh.dim(Q(XD, top), Q(XD, top + lp), Q(XD + 400, top), angle=90, text=f'LAP {lp}' + (' MIN' if model and PRJ.get('neck_unify_length') else ''))
    if not (starter or single):
        sh.dim(Q(XD - 900, f['h']), Q(XD - 900, f['h'] + lp), Q(XD - 500, f['h']), angle=90, text=f'LAP {lp}')
    if single:                                                       # vertical part of the bar: foot -> T.O.GB
        sh.dim(Q(XD - 900, yb), Q(XD - 900, top), Q(XD - 500, yb), angle=90, text=f'{top - yb}')
    sh.text('FIRST TIE 50 FROM T.O.F' + ('' if starter else ' / T.O.GB'), Q(-cw / 2, 0)[0] - 200, Q(0, f['h'] + 60)[1], ST['note'] * 0.8, 'S-DIM', align=TA.BOTTOM_RIGHT)
    sh.dim(Q(fxl, 0), Q(fxl, f['h']), Q(fxl - 400, 0), angle=90, text='VAR (FOOTING THICKNESS)' if model else str(f['h']))
    marks_ = ((-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {tpc:+.2f}"), (f['h'], f"T.O.F = T.O.SLAB {tof:+.2f}")) if starter else \
             ((-100, f"F.L (B.O.PC) {fl:+.2f}"), (0, f"T.O.PC {tpc:+.2f}"), (f['h'], 'T.O.F VAR' if model else f"T.O.F {tof:+.2f}"),
              (top - gb_h, f"B.O.GB {tgb - gb_h / 1000:+.2f}"), (top, f"T.O.GB {tgb:+.2f}"))
    for yy, lab in marks_:
        xl = max(Q(fxl - 1600, 0)[0], 1300)                      # level marks stay on the sheet (wide footings)
        sh.line((xl, Q(0, yy)[1]), Q(fxl - 150, yy), 'S-DIM')
        sh.text(lab, xl, Q(0, yy)[1] + 50, 170, 'S-DIM')
    # call-outs
    if starter:
        sh.ctext(mv, callout(col['n'], d, mv, Lv, layer='V') + '  STARTER', Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1], ST['call'])
        sh.text(f"(FOOT {foot} {'TURNED INWARDS ' if inward else ''}ON THE BOTTOM MESH)", Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 400, ST['note'])
    elif single:
        sh.ctext(mv, callout(col['n'], d, mv, Lv, layer='V') + '  NECK BARS', Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1], ST['call'])
        sh.text(f"(FOOT {foot} ON THE BOTTOM MESH, UP TO T.O.GB + LAP {lp} = {LAPN}d)", Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 400, ST['note'])
        if model: sh.text('LAP ABOVE T.O.GB BY THE FOOTING MESH: SEE THE TABLE ABOVE' if PRJ.get('neck_unify_length') else 'LENGTH BY THE FOOTING MESH: SEE THE TABLE ABOVE', Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 700, ST['note'])
    else:
        sh.ctext(mn, callout(col['n'], d, mn, Ln, layer='V') + '  NECK BARS', Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1], ST['call'])
        sh.text(f"(T.O.F TO T.O.GB + LAP {lp})", Q(cw / 2 + 200, 0)[0], Q(0, top + lp * 0.6)[1] - 400, ST['note'])
        ys_ = Q(0, f['h'])[1] + 2600                                # left of the neck, between T.O.F and B.O.GB
        xs_ = 1500
        sh.ctext(mv, callout(col['n'], d, mv, Lv, layer='V') + '  STARTERS', xs_, ys_, ST['call'])
        sh.text(f"(FOOT {foot} {'TURNED INWARDS ' if inward else ''}ON THE BOTTOM MESH", xs_, ys_ - 400, ST['note'])
        sh.text(f"+ LAP {lp} ABOVE T.O.F)", xs_, ys_ - 700, ST['note'])
    # Ld in the footing on the elevation
    sh.dim(Q(-cw / 2 - 250, yb), Q(-cw / 2 - 250, f['h']), Q(-cw / 2 - 650, yb), angle=90, text='VAR' if model else f'{emb}')
    if not single: sh.text(f"Ld = {emb} + {foot} = {emb + foot} {'>=' if emb + foot >= LD else '<'} {LDN}d = {LD}" + ('' if ld_ok else '  (!) SEE NOTE'),
            *((1500, Q(0, f['h'])[1] + 1500) if not starter else (Q(fxr, 0)[0] - 5200, Q(0, f['h'] * 0.45)[1])), ST['note'], 'S-DIM')
    # ---------- the bar detailed outside (bending detail with every length) ----------
    bx0, by0 = 2600, 18100
    kb = min(6300 / (max(vert, 0 if starter else Ln) + 600), 2.0)
    B_ = lambda x, y: (bx0 + x * kb, by0 + y * kb)
    fx_ = min(foot * kb, 3500) / kb                                  # drawn foot (long feet shortened on the sketch)
    sh.pline([B_(fx_, 0), B_(0, 0), B_(0, vert)], 'S-RFT-TOP', max(d * kb, 30), r=3 * d * kb)
    sh.text(str(foot), *B_(fx_ / 2, -120 / kb * 1.0), ST['len'], 'S-DIM', align=TA.TOP_CENTER)
    sh.text(str(vert), *B_(-140 / kb, vert / 2), ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
    for yy, t in (((emb, f'T.O.F = T.O.SLAB (IN FOOTING {emb})'),) if starter else ((emb, 'T.O.F (VAR)' if model else f'T.O.F (IN FOOTING {emb})'), (emb + Hn, f'T.O.GB ({emb + Hn} FROM THE FOOT' + (f", MESH T{max(f['bot'][1], f['bot'][3])})" if model else ')'))) if single else ((emb, f'T.O.F (IN FOOTING {emb})'),)):
        sh.line(B_(-60, yy), B_(380 / kb, yy), 'S-DIM'); sh.text(t, B_(420 / kb, 0)[0], B_(0, yy)[1] - 60, ST['note'], 'S-DIM')
    sh.text(f'LAP {lp}', B_(420 / kb, 0)[0], B_(0, emb + (Hn if single else 0) + lp / 2)[1], ST['note'], 'S-DIM')
    sh.ctext(mv, callout(col['n'], d, mv, Lv, layer='V'), bx0, by0 + vert * kb + 700, ST['call'])
    sh.text(f'L = {foot} + {vert} = {Lv}', bx0, by0 + vert * kb + 300, ST['note'], 'S-RFT-TXT')
    if not (starter or single):                                      # the neck bar beside it, from T.O.F
        nx0 = bx0 + 5200
        N_ = lambda y: (nx0, by0 + (emb + y) * kb)
        sh.pline([N_(0), N_(Ln)], 'S-RFT-TOP', max(d * kb, 30))
        sh.text(str(Ln), N_(Ln / 2)[0] - 140, N_(Ln / 2)[1], ST['len'], 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
        for yy, t in ((0, 'T.O.F'), (Hn, f'T.O.GB ({Hn})'), (Hn + lp / 2, f'LAP {lp}')):
            sh.line((N_(yy)[0] - 60, N_(yy)[1]), (N_(yy)[0] + 300, N_(yy)[1]), 'S-DIM'); sh.text(t, N_(yy)[0] + 340, N_(yy)[1] - 60, ST['note'], 'S-DIM')
        sh.ctext(mn, callout(col['n'], d, mn, Ln, layer='V'), nx0, by0 + (emb + Ln) * kb + 700, ST['call'])
    sh.text('BAR DETAIL (NECK BAR)' if single else 'BAR DETAIL (STARTER' + ('' if starter else ' + NECK BAR') + ')', bx0, by0 - 850, ST['panel'], 'S-SEC', maxw=7000)
    if inward: sh.text('FOOT TURNED INWARDS (NO ROOM OUTWARDS)', bx0, by0 - 1250, ST['note'], 'S-RFT-TXT')
    if not ld_ok:
        sh.text(f'(!) FOOT {foot} DOES NOT FIT IN THE FOOTING EVEN TURNED INWARDS: CONSULTANT TO CONFIRM',
                bx0, by0 - 1600, ST['note'], 'S-DIM', maxw=8000)
    yc0 = max(Q(0, f['h'] + Hn * 0.55)[1], Q(0, ya)[1] + 520 * len(ties) + 1900)   # tie call-outs (and the tie note) above the section cut A-A
    for i, t in enumerate(ties):
        sh.ctext(t['mk'], callout((n_neck + n_ftg) * t['k'], 10, t['mk'], t['L'], s) + (f"  ({t['k']} PER SET)" if t['k'] > 1 else ''), Q(cw / 2 + 200, 0)[0], yc0 - i * 520, ST['call'], maxw=(XD - cw / 2 - 350) * k)
    yt_ = yc0 - len(ties) * 520 - 100
    sh.text(f"TIES {col['sets']} SETS @{s}", Q(cw / 2 + 200, 0)[0], yt_, ST['note'])
    sh.text(f"{n_neck} IN THE NECK + {n_ftg} IN THE FOOTING" if not model else
            f"TOTAL {sum(t.get('tot', 0) for t in ties[:1])} SETS FOR {no} COLUMNS (NECK + FOOTING DEPTH)", Q(cw / 2 + 200, 0)[0], yt_ - 260, ST['note'], maxw=(XD - cw / 2 - 350) * k)
    if model:                                                   # neck bar length by the footing's bottom mesh
        tx0, ty0 = 7800, 24600 - min(9, len(lines_)) * 300 - 900
        sh.text(('ONE CUTTING LENGTH FOR THE TYPE (THE LONGEST); EXTRA LENGTH = LONGER LAP ABOVE T.O.GB' if PRJ.get('neck_unify_length') else 'NECK BAR LENGTH BY FOOTING BOTTOM MESH')
                + ' (T.O.PC TO T.O.GB = %d)' % round((tgb - footing_levels(f['h'], ZL)[1]) * 1000), tx0, ty0, ST['note'], 'S-SEC', maxw=13500)
        for j, m_ in enumerate(model):
            yy = ty0 - 500 - j * 450
            sh.ctext(m_['mk'], f"{col['n'] * m_['no']} T {d}-{m_['L']}  MESH T{m_['dm']}: FOOT {foot} + {m_['v']} (TO T.O.GB) + LAP {m_['lap']}" + (f" (= {lp} + {m_['lap'] - lp})" if m_['lap'] > lp else '') + f"   ({m_['no']} COL.)", tx0, yy, ST['note'] * 1.2, maxw=13500)
    sh.text(col.get('elev_title') or ('ELEVATION  (STARTER BARS - THE COLUMN TIES CONTINUE ABOVE THE SLAB)' if starter else 'ELEVATION  (COLUMN TIES CONTINUE THROUGH THE GB JOINT)'), Q(0, 0)[0], Q(0, -100)[1] - 700, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)

    # ---------- SECTION A-A 1:10 (k=10) ----------
    ks = min(10.0, 9000 / max(col['b'], col['h']))
    sx0, sy0 = 24600, 14500
    P = lambda x, y: (sx0 + x * ks, sy0 + y * ks)
    sh.pline([P(0, 0), P(col['h'], 0), P(col['h'], col['b']), P(0, col['b'])], 'S-GB-CONC', 0, True) if False else None
    W, Hh = col['b_draw'], col['h_draw']
    sh.pline([P(0, 0), P(W, 0), P(W, Hh), P(0, Hh)], 'S-GB-CONC', 0, True)
    for t in ties:
        for pts, closed in t['draw']:
            hb_ = col['bars'] if not col.get('perimeter_tie') else [(x_, y_) for x_ in (min(p[0] for p in pts) + d / 2 + ds / 2, max(p[0] for p in pts) - d / 2 - ds / 2)
                                                                   for y_ in (min(p[1] for p in pts) + d / 2 + ds / 2, max(p[1] for p in pts) - d / 2 - ds / 2)]
            for seg in hooked_tie(pts, hb_, rc=d / 2 + ds / 2):
                sh.pline([P(*p) for p in seg], 'S-RFT-STIR', 25)
    for (x, y) in col['bars']:
        hh = sh.m.add_hatch(color=7, dxfattribs={'layer': 'S-RFT-TOP'})
        hh.paths.add_edge_path().add_arc(sh.P(*P(x, y)), d / 2 * ks, 0, 360)
    sh.dim(P(0, 0), P(W, 0), (P(0, 0)[0], P(0, 0)[1] - 600), text=str(round(W)))
    sh.dim(P(0, 0), P(0, Hh), (P(0, 0)[0] - 600, P(0, 0)[1]), angle=90, text=str(round(Hh)))
    sh.text(f"SEC A-A  {col['name']} {col['b']}x{col['h']}   {col['n']} T {d}   COVER {COLC}", P(W / 2, 0)[0], P(0, 0)[1] - 1300, ST['panel'], 'S-SEC', align=TA.TOP_CENTER)
    # tie shapes with their lengths
    TX0 = max(23500, Q(fxr, 0)[0] + 900)                       # clear of the footing
    tx = TX0; by = 8400
    sh.text('TIE LENGTHS L INCLUDE TWO 135-DEG HOOKS x 100 (OUT-TO-OUT DIMENSIONS)', 23500, 11500, ST['note'], 'S-RFT-TXT', maxw=9500)
    for t in ties:
        kk = min(9.0, 2700 / max(1, t['hh']), 5500 / max(1, t['w']))
        nm = t['norm']; nn = len(nm)
        cb = tie_bar_centres(nm, d / 2 + 10)              # bar centres for the out-to-out shape
        segs, moved = opened_tie(nm, cb, tail=100, rc=d / 2 + 10)      # opened at the hooks (engineer's sample)
        xa_ = min(p[0] for sg_ in segs for p in sg_); xb_ = max(p[0] for sg_ in segs for p in sg_)
        if tx > TX0 and tx + (xb_ - xa_) * kk > 35600: tx = TX0; by -= 4300          # next row (title block at 36000)
        Z = lambda p: (tx + (p[0] - xa_) * kk, by + p[1] * kk)
        for sg_ in segs:
            sh.pline([Z(p) for p in sg_], 'S-RFT-STIR', 20)
        ta_, tb_ = moved['tail']                                       # the hook tail written 100 along it
        tang = math.degrees(math.atan2(tb_[1] - ta_[1], tb_[0] - ta_[0]))
        if tang > 90.5 or tang <= -89.5: tang += 180
        pm_ = Z(((ta_[0] + tb_[0]) / 2, (ta_[1] + tb_[1]) / 2))
        nrm = math.radians(tang + 90)
        sh.text('100', pm_[0] + 130 * math.cos(nrm), pm_[1] + 130 * math.sin(nrm), ST['len'], 'S-DIM', rot=tang, align=TA.MIDDLE_CENTER)
        # one or two sides dimensioned (engineer's note): the top side and the vertical side, plus one slanted side
        ed = [(nm[j], nm[(j + 1) % nn]) for j in range(nn)]
        hor = max((e_ for e_ in ed if abs(e_[0][1] - e_[1][1]) < 2), key=lambda e_: (e_[0][1], math.dist(*e_)), default=None)
        ver = max((e_ for e_ in ed if abs(e_[0][0] - e_[1][0]) < 2), key=lambda e_: (math.dist(*e_), -e_[0][0]), default=None)
        sl = [e_ for e_ in ed if abs(e_[0][1] - e_[1][1]) >= 2 and abs(e_[0][0] - e_[1][0]) >= 2 and math.dist(*e_) > 25]
        for e_ in [x for x in ed if math.dist(*x) > 25]:                 # every side written (engineer, Oct 2026)
            k_ = (tuple(e_[0]), tuple(e_[1]))
            a_, b_ = moved.get(k_) or tuple(reversed(moved.get((k_[1], k_[0]), ()))) or e_   # the swung side where it is drawn
            pa_, pb_ = Z(a_), Z(b_)
            mx, my = (pa_[0] + pb_[0]) / 2, (pa_[1] + pb_[1]) / 2
            ang = math.degrees(math.atan2(b_[1] - a_[1], b_[0] - a_[0]))
            if ang > 90.5 or ang <= -89.5: ang += 180
            cx_ = sum(p[0] for p in nm) / nn; cy_ = sum(p[1] for p in nm) / nn
            nx_, ny_ = (a_[0] + b_[0]) / 2 - cx_, (a_[1] + b_[1]) / 2 - cy_; hn = math.hypot(nx_, ny_) or 1
            sh.text(mm(math.dist(a_, b_)), mx + nx_ / hn * 200, my + ny_ / hn * 200, ST['len'], 'S-DIM', rot=ang, align=TA.MIDDLE_CENTER)
        sh.ctext(t['mk'], f"{t['w']}x{t['hh']}" + (f"  x{t['k']}/SET" if t['k'] > 1 else ''), tx, by - 800, ST['call'], 'S-RFT-TXT')
        sh.text(f"L={mm(t['L'])}", tx, by - 1400, ST['call'], 'S-RFT-TXT')
        tx += max((xb_ - xa_) * kk, 3700) + 900
    return Hn, (emb, foot, LD, ld_ok, inward)


if __name__ == '__main__':
    # column sections typed / read for the project (project.json column_sections) or read from the schedule block
    sched = {k: dict(v, tieset=[dict(poly=t) for t in v['ties']], shapes=[], dots_raw=v['dots'], ties=[])
             for k, v in PRJ['column_sections'].items()} if PRJ.get('column_sections') else read_schedule2()
    args = sys.argv[1:]
    if args and args[0] == '--models':          # one generic sheet per column type: models.json {type: [[footing, no], ...]}
        models = json.load(open(args[1]))
        lib = json.load(open('footings.json'))
        import os
        if os.path.exists('footings_ext.json'): lib.update(json.load(open('footings_ext.json')))
        doc = new_doc(); bl = BarList(); dwgmap = {}
        for i, (cn, mem) in enumerate(models.items()):
            col = dict(sched[cn]); col['name'] = cn; col['b_draw'], col['h_draw'] = col['dw'], col['dh']
            members = [(lib[fn], int(n)) for fn, n in mem]
            rep = max(members, key=lambda m: m[1])[0]
            meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                        rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='ELEV 1:25 / SEC 1:10', prefix='SDW-STR-NCK')
            meta.update(PRJ.get('meta', {}))
            meta['title'] = f'COLUMN NECKS\n{cn}  {col["b"]}x{col["h"]}'
            bl.cur = cn
            draw_neck(doc, i, col, rep, meta, bl, sum(n for _, n in members), members=members)
            dwgmap[cn] = meta.get('dwg_no', '')
            print(cn, 'model on', len(members), 'footing types,', sum(n for _, n in members), 'columns')
        meta['title'] = 'COLUMN NECKS'; meta['dwg'] = 'SDW-STR-NCK'
        from gen import draw_bbs_grouped
        nb = draw_bbs_grouped(doc, len(models), bl.sorted(), meta,
                              [(f"{cn}  {sched[cn]['b']}x{sched[cn]['h']}  (NO={sum(int(n) for _, n in m)})", cn, sum(int(n) for _, n in m)) for cn, m in models.items()])
        doc.saveas('out/NECKS.dxf'); bl.export('out/NECKS.bbs.json', dwgmap, {cn: sum(int(n) for _, n in m) for cn, m in models.items()}); print('sheets', len(models), '+ BBS', nb)
        sys.exit(0)
    if args and args[0].startswith('@'): args = open(args[0][1:]).read().split()        # @pairs.txt
    pairs = [tuple(a.split(':')) for a in args] or [('C1', 'F6', '11')]
    lib = json.load(open('footings.json'))
    import os
    if os.path.exists('footings_ext.json'): lib.update(json.load(open('footings_ext.json')))   # CF / RAFT / ST (h, steel; see plan)
    doc = new_doc(); bl = BarList(); dwgmap = {}
    for i, (cn, fn, no) in enumerate(pairs):
        col = dict(sched[cn]); col['name'] = cn
        col['b_draw'], col['h_draw'] = col['dw'], col['dh']
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='ELEV 1:25 / SEC 1:10', prefix='SDW-STR-NCK')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = project_notes('COVER COLUMNS 40 (SCHEDULE NOTE 4).', 'VERTICAL BARS BENT 90 DEG ON THE FOOTING MESH; Ld IN THE FOOTING >= 60d (STRAIGHT + FOOT).')
        meta['title'] = f'COLUMN NECKS\n{cn} ON {fn}'
        meta['dwg'] = f"{meta['prefix']}-{cn}-{fn}"
        bl.cur = f'{cn} ON {fn}'
        Hn, ld = draw_neck(doc, i, col, lib[fn], meta, bl, int(no))
        dwgmap[f'{cn} ON {fn}'] = meta.get('dwg_no', '')
        print(cn, fn, 'neck H', Hn, 'Ld emb+foot', ld[0], '+', ld[1], '>= 60d', ld[2], 'OK' if ld[3] else 'CHECK', 'INWARDS' if ld[4] else '')
    meta['title'] = 'COLUMN NECKS'; meta['dwg'] = 'SDW-STR-NCK'
    if PRJ.get('bbs_per_element'):           # one BBS table per neck model, titled with the column type
        from gen import draw_bbs_grouped
        nb = draw_bbs_grouped(doc, len(pairs), bl.sorted(), meta, [(f"{cn}  (NO={no})", f'{cn} ON {fn}', int(no)) for cn, fn, no in pairs])
    else:
        nb = draw_bbs(doc, len(pairs), bl.sorted(), meta)
    doc.saveas('out/NECKS.dxf'); bl.export('out/NECKS.bbs.json', dwgmap, {f'{cn} ON {fn}': int(no) for cn, fn, no in pairs}); print('sheets', len(pairs), '+ BBS', nb)
