"""Swimming pool / open tank with a SLOPED floor: concrete dimensions, floor bottom and top meshes, long wall elevation,
cross sections, corner detail and BBS in one DXF.

pool.json (read from the consultant's pool sheet: plan dims, the long section levels, the reinforcement texts):
  L, W          inner length / width (mm), t wall thickness, h floor thickness, blind blinding
  profile       [[x, depth], ...]  depth of the FLOOR TOP below the wall top (TOC) along the length, x from the
                inner face of the shallow wall (0 .. L); straight between the points (slope parts)
  cover         {bot, top, wall}
  floor         {B1: [d, s, 'Y'], B2: [d, s, 'X'], T1: ..., T2: ...}   B1 / T1 = outer layers
  wall          {V: [d, s] vertical bars each face (C bar: over the top + foot into the floor),
                 H: [d, s] horizontal bars each face, U: [d, leg] U bar at every wall end, first: level of the top bar}
  step_v        vertical bars of a wall over the slope: one length per step (mm) - the foot stays in the floor
usage: python3 gen_pool.py [pool.json]  -> out/POOL/<code>_POOL.dxf"""
import json, math, sys, os
from ezdxf.enums import TextEntityAlignment as TA
from gen import new_doc, Sheet, BarList, draw_bbs, callout, lap_patterns, lapped_marks, ST, project_notes, draw_legend
import gen_f

P = json.load(open(sys.argv[1] if len(sys.argv) > 1 else 'pool.json'))
L, W, t, h, BL = P['L'], P['W'], P['t'], P['h'], P.get('blind', 150)
cb, ct, cw = P['cover']['bot'], P['cover']['top'], P['cover']['wall']
PR = [tuple(p) for p in P['profile']]
STEP = P.get('step_v', 200)
LG = h - cb - ct                                   # U legs of the floor bars (bottom up / top down)
up10 = lambda v: int(math.ceil(v / 10) * 10)


def depth(x):
    x = min(max(x, PR[0][0]), PR[-1][0])
    for (x0, d0), (x1, d1) in zip(PR, PR[1:]):
        if x0 <= x <= x1: return d0 + (d1 - d0) * (x - x0) / ((x1 - x0) or 1)
    return PR[-1][1]
zt = lambda x: -depth(x)
zb = lambda x: -depth(x) - h
KINKS = [x for x, _ in PR if 0 < x < L]
DMAX, DMIN = max(d for _, d in PR), min(d for _, d in PR)


def plen(pts): return sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))


def sub(pts, t0, t1):
    """part of a polyline between arc lengths t0..t1"""
    out, acc = [], 0
    for a, b in zip(pts, pts[1:]):
        Ls = math.dist(a, b)
        if Ls == 0: continue
        s0, s1 = max(t0, acc), min(t1, acc + Ls)
        if s0 < s1:
            pa = (a[0] + (b[0] - a[0]) * (s0 - acc) / Ls, a[1] + (b[1] - a[1]) * (s0 - acc) / Ls)
            pb = (a[0] + (b[0] - a[0]) * (s1 - acc) / Ls, a[1] + (b[1] - a[1]) * (s1 - acc) / Ls)
            if not out: out.append(pa)
            out.append(pb)
        acc += Ls
    return out


def shape_of(pts):
    x0, y0 = min(p[0] for p in pts), min(p[1] for p in pts)
    return ('PROF',) + tuple((int(round(a - x0)), int(round(b - y0))) for a, b in pts)


bl = BarList()
BARS = {}

# ---------------------------------------------------------------- floor
def floor_x(tag):
    d, s, _ = P['floor'][tag]
    bot = tag.startswith('B')
    du = P['floor']['B1' if bot else 'T1'][0]           # the X bars are the inner layer (B2 / T2)
    z = (lambda x: zb(x) + cb + du + d / 2) if bot else (lambda x: zt(x) - ct - du - d / 2)
    sg = 1 if bot else -1
    x0, x1 = -t + cw, L + t - cw
    xs = [x0] + KINKS + [x1]
    run = [(x, z(x)) for x in xs]
    pts = [(x0, z(x0) + sg * LG)] + run + [(x1, z(x1) + sg * LG)]
    T = up10(plen(pts)); lp = 60 * d
    n = math.ceil((W + 2 * t - 2 * cw) / s) + 1
    pats = lap_patterns(T, lp)
    cnt = [math.ceil(n / len(pats)), n - math.ceil(n / len(pats))] if len(pats) == 2 else [n]
    marks = {}
    for pat, c in zip(pats, cnt):
        for t0, t1 in pat:
            q = sub(pts, t0, t1)
            key = shape_of(q); Lp = int(round(t1 - t0))
            mk = bl.add(d, key, Lp, c, 1, tag)
            marks[mk] = (marks.get(mk, (0, Lp))[0] + c, Lp)
    BARS[tag] = dict(d=d, s=s, n=n, T=T, pts=pts, run=run, pats=pats, leg=LG, straight=T - 2 * LG, tag=tag,
                     marks=[(m, c, Lp) for m, (c, Lp) in marks.items()], lap=lp)


def floor_y(tag):
    d, s, _ = P['floor'][tag]
    bot = tag.startswith('B')
    dx = P['floor']['B2' if bot else 'T2'][0]
    zoff = (cb + d / 2) if bot else -(ct + d / 2)
    run = [(x, (zb(x) if bot else zt(x)) + zoff) for x in [-t + cw] + KINKS + [L + t - cw]]
    Sdev = plen(run)
    n = math.ceil(Sdev / s) + 1
    straight = W + 2 * t - 2 * cw; T = straight + 2 * LG
    pats, marks = lapped_marks(bl, d, T, LG, LG, n, 1, tag)
    BARS[tag] = dict(d=d, s=s, n=n, T=T, pats=pats, leg=LG, straight=straight, tag=tag, marks=marks, run=run, lap=60 * d)


for tg in ('B1', 'T1'): floor_y(tg)
for tg in ('B2', 'T2'): floor_x(tg)

# ---------------------------------------------------------------- walls
dV, sV = P['wall']['V']; dH, sH = P['wall']['H']; dU, legU = P['wall']['U']
FIRST = P['wall'].get('first', 100)
legV = t - 2 * cw                                      # over the top of the wall, and the foot into the floor
footV = max(legV, 12 * dV)
def positions(a, b, s):
    n = math.ceil((b - a) / s) + 1
    return [a + (b - a) * i / (n - 1) for i in range(n)]
def vreq(x): return depth(x) + h - cw - cb - P['floor']['B1'][0] - P['floor']['B2'][0]   # foot on the bottom mesh


def v_groups(xs):
    req = [vreq(x) for x in xs]
    flat = sorted({round(r) for r in req if sum(1 for q in req if abs(q - r) < 0.5) >= 3})
    base = min(req)
    cands = sorted(set(flat + [round(base + k * STEP) for k in range(int((max(req) - base) // STEP) + 1)]))
    g = {}
    for x, r in zip(xs, req):
        c = max(v for v in cands if v <= r + 0.5)
        g.setdefault(c, []).append(x)
    return sorted(g.items())


WALLV = []      # (wall, face, straight, [x...], mark)
def add_v(wall, face, xs, n_el):
    for st, grp in v_groups(xs):
        st = int(math.floor(st / 10) * 10)
        mk = bl.add(dV, ('U', legV, st, footV), legV + st + footV, len(grp), n_el, 'V')
        WALLV.append(dict(wall=wall, face=face, st=st, xs=grp, mk=mk, n=len(grp), n_el=n_el))


add_v('LONG', 'OUTER', positions(-t + cw, L + t - cw, sV), 2)
add_v('LONG', 'INNER', positions(cw, L - cw, sV), 2)
for wall, x in (('SHALLOW', -t / 2), ('DEEP', L + t / 2)):
    yo, yi = positions(-t + cw, W + t - cw, sV), positions(cw, W - cw, sV)
    for face, ys in (('OUTER', yo), ('INNER', yi)):
        st = int(math.floor(vreq(x) / 10) * 10)
        mk = bl.add(dV, ('U', legV, st, footV), legV + st + footV, len(ys), 1, 'V')
        WALLV.append(dict(wall=wall, face=face, st=st, xs=ys, mk=mk, n=len(ys), n_el=1))

LEVELS = [FIRST + i * sH for i in range(int((DMAX - 100 - FIRST) // sH) + 1)]
def span(z):
    """the part of the long wall holding a horizontal bar at level z (wall above the floor, 100 clear)"""
    xs = [x for x in range(0, L + 1, 10) if depth(x) >= z + 100]
    if not xs: return None
    a, b = min(xs), max(xs)
    return (-t + cw if a == 0 else a, L + t - cw if b == L else b)


WALLH = []      # long walls: one record per bar length (levels grouped)
grp = {}
for z in LEVELS:
    sp = span(z)
    if sp: grp.setdefault(sp, []).append(z)
for (a, b), zs in sorted(grp.items(), key=lambda kv: kv[1][0]):
    Lh = up10(b - a)
    pats, marks = lapped_marks(bl, dH, Lh, 0, 0, len(zs) * 2, 2, 'H')       # 2 faces x 2 long walls
    WALLH.append(dict(wall='LONG', a=a, b=b, zs=zs, T=Lh, pats=pats, marks=marks, d=dH, s=sH, leg=0, straight=Lh, lap=60 * dH))
SHORT_LV = {}
for wall, x in (('SHALLOW', 0), ('DEEP', L)):
    zs = [z for z in LEVELS if depth(x) >= z + 100]
    SHORT_LV[wall] = zs
    Lh = W + 2 * t - 2 * cw
    pats, marks = lapped_marks(bl, dH, Lh, 0, 0, len(zs) * 2, 1, 'H')
    WALLH.append(dict(wall=wall, a=-t + cw, b=W + t - cw, zs=zs, T=Lh, pats=pats, marks=marks, d=dH, s=sH, leg=0, straight=Lh, lap=60 * dH))
# U bar at every wall end and every level: legs lapped with both faces, base across the wall at the far face
nU = 2 * (len(SHORT_LV['SHALLOW']) + len(SHORT_LV['DEEP'])) * 2          # long walls (2) x 2 ends + short walls x 2 ends
mkU = bl.add(dU, ('U', legU, t - 2 * cw, legU), 2 * legU + t - 2 * cw, nU, 1, 'U')

# ---------------------------------------------------------------- sheets
meta0 = dict(client='', project='', consultant='', contractor='', ref=P.get('ref', ''), author='', checker='', approver='',
             rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='1:100', prefix='SDW-STR-SP')
PRJ = json.load(open(os.environ.get('RC_PROJECT', 'project.json')))
meta0.update(PRJ.get('meta', {})); meta0['ref'] = P.get('ref', meta0.get('ref', ''))
meta0['area'] = P.get('code', 'SP'); meta0['venue'] = P.get('venue', 'SP')
NOTES = project_notes(f"COVER: FLOOR BOTTOM {cb}, FLOOR TOP {ct}, WALLS {cw} (BOTH FACES).",
                      "FLOOR BARS FOLLOW THE FLOOR SLOPE, BENT AT THE SLOPE CHANGES; LENGTHS = DEVELOPED LENGTHS.",
                      "LAPS STAGGERED: ALTERNATE BARS IN PATTERN A / B.")
meta0['notes'] = NOTES
doc = new_doc(); IDX = [0]


def sheet(title, scale='1:100'):
    m = dict(meta0); m['title'] = f"{P['name']}\n{title}"; m['dwg'] = f"SDW-STR-SP-{IDX[0] + 1:02d}"; m['scale'] = scale
    sh = Sheet(doc, 0, -IDX[0] * 32000, m); IDX[0] += 1
    return sh


def T_(ox, oy, k):
    return lambda x, y: (ox + x * k, oy + y * k)


def cot(b):
    return ' + '.join(callout(c, b['d'], m_, L_, b['s'] if not i else None, b['tag'] if 'tag' in b else None, stg=len(b['marks']) > 1 and not i)
                      for i, (m_, c, L_) in enumerate(b['marks']))


def long_section(sh, X, show_dims=True):
    out = [(-t, 0), (-t, zb(-t))] + [(x, zb(x)) for x in KINKS] + [(L + t, zb(L + t)), (L + t, 0), (L, 0), (L, zt(L))] + \
          [(x, zt(x)) for x in reversed(KINKS)] + [(0, zt(0)), (0, 0)]
    sh.pline([X(*p) for p in out], 'S-GB-CONC', 25, True)
    bl_ = [(-t - 100, zb(-t) - BL)] + [(x, zb(x) - BL) for x in KINKS] + [(L + t + 100, zb(L + t) - BL)]
    sh.pline([X(*p) for p in bl_], 'S-GB-CONC', 0)
    if show_dims:
        y0 = X(0, 0)[1] + 700
        xs = [-t, 0] + KINKS + [L, L + t]
        for a, b in zip(xs, xs[1:]):
            sh.dim(X(a, 0), X(b, 0), (0, y0), text=str(int(round(b - a))))
        for x in (0, L):
            xx = X(x, 0)[0] + (500 if x == 0 else -500)
            sh.dim(X(x, 0), X(x, zt(x)), (xx, 0), angle=90, text=str(int(round(depth(x)))))
        for xk in KINKS[:1]:
            sl = abs(depth(KINKS[1] if len(KINKS) > 1 else L) - depth(xk)) / ((KINKS[1] if len(KINKS) > 1 else L) - xk)
            mx = (xk + (KINKS[1] if len(KINKS) > 1 else L)) / 2
            px, py = X(mx, zt(mx) + 250)
            sh.text(f'SLOPE 1:{round(1 / sl)}  ({sl * 100:.0f} %)', px, py, ST['note'], 'S-DIM', align=TA.BOTTOM_CENTER)


def cross_section(sh, X, x):
    d = depth(x)
    out = [(-t, 0), (-t, -d - h), (W + t, -d - h), (W + t, 0), (W, 0), (W, -d), (0, -d), (0, 0)]
    sh.pline([X(*p) for p in out], 'S-GB-CONC', 25, True)
    sh.pline([X(-t - 100, -d - h - BL), X(W + t + 100, -d - h - BL)], 'S-GB-CONC', 0)
    return d


# ---- sheet 1: concrete dimensions
sh = sheet('CONCRETE DIMENSIONS - PLAN AND SECTIONS')
X = T_(3000, 14500 + t, 1)
sh.pline([X(-t, -t), X(L + t, -t), X(L + t, W + t), X(-t, W + t)], 'S-GB-CONC', 25, True)
sh.pline([X(0, 0), X(L, 0), X(L, W), X(0, W)], 'S-GB-CONC', 25, True)
for xk in KINKS:
    sh.pline([X(xk, 0), X(xk, W)], 'S-DIM', 0)
xs = [-t, 0] + KINKS + [L, L + t]
for a, b in zip(xs, xs[1:]):
    sh.dim(X(a, W + t), X(b, W + t), (0, X(0, W + t)[1] + 500), text=str(int(round(b - a))))
sh.dim(X(-t, W + t), X(L + t, W + t), (0, X(0, W + t)[1] + 1100), text=str(L + 2 * t))
for a, b in ((-t, 0), (0, W), (W, W + t)):
    sh.dim(X(L + t, a), X(L + t, b), (X(L + t, 0)[0] + 500, 0), angle=90, text=str(int(round(b - a))))
sh.dim(X(L + t, -t), X(L + t, W + t), (X(L + t, 0)[0] + 1100, 0), angle=90, text=str(W + 2 * t))
for x in [0] + KINKS + [L]:
    px, py = X(x + (300 if x < L else -300), W / 2)
    sh.text(f'FLOOR TOP -{depth(x) / 1000:.2f}', px, py, ST['note'], 'S-DIM', rot=90, align=TA.MIDDLE_CENTER)
sh.text(f'WALL TOP (TOC) = +0.00 ; FLOOR {h} THK ; WALLS {t} THK ; BLINDING {BL}', X(0, -t)[0], X(0, -t)[1] - 700, ST['note'], 'S-DIM')
sh.text('PLAN', X(L / 2, 0)[0], X(0, -t)[1] - 1300, ST['sub'], 'S-SEC', align=TA.MIDDLE_CENTER)
X1 = T_(3000, 11000, 1)
long_section(sh, X1)
sh.text('SECTION 1 (ALONG THE POOL)', X1(L / 2, 0)[0], X1(0, -DMAX - h)[1] - 700, ST['sub'], 'S-SEC', align=TA.MIDDLE_CENTER)
for i, (nm, x) in enumerate((('SECTION 2 (DEEP END)', L), ('SECTION 3 (SHALLOW END)', 0))):
    Xs = T_(1700 + i * 15600, 4600, 1)
    d = cross_section(sh, Xs, x)
    sh.dim(Xs(-t, 0), Xs(0, 0), (0, Xs(0, 0)[1] + 500), text=str(t))
    sh.dim(Xs(0, 0), Xs(W, 0), (0, Xs(0, 0)[1] + 500), text=str(W))
    sh.dim(Xs(W, 0), Xs(W + t, 0), (0, Xs(0, 0)[1] + 500), text=str(t))
    sh.dim(Xs(W + t, 0), Xs(W + t, -d), (Xs(W + t, 0)[0] + 400, 0), angle=90, text=str(int(d)))
    sh.dim(Xs(W + t, -d), Xs(W + t, -d - h), (Xs(W + t, 0)[0] + 400, 0), angle=90, text=str(h))
    sh.text(nm, Xs(W / 2, 0)[0], Xs(0, -DMAX - h)[1] - 600, ST['sub'], 'S-SEC', align=TA.MIDDLE_CENTER)


# ---- sheets 2 / 3: floor meshes (plan + section along the pool)
def floor_sheet(lay):
    yb, xb = BARS[lay + '1'], BARS[lay + '2']
    word = 'BOTTOM' if lay == 'B' else 'TOP'
    sh = sheet(f'FLOOR {word} REINFORCEMENT')
    draw_legend(sh, 19000, 28300)
    X = T_(3000, 12700 + t, 1)
    sh.pline([X(-t, -t), X(L + t, -t), X(L + t, W + t), X(-t, W + t)], 'S-GB-CONC', 25, True)
    sh.pline([X(0, 0), X(L, 0), X(L, W), X(0, W)], 'S-GB-CONC', 0, True)
    for xk in KINKS: sh.pline([X(xk, 0), X(xk, W)], 'S-DIM', 0)
    lyr = 'S-RFT-BOT' if lay == 'B' else 'S-RFT-TOP'
    # Y bars (outer layer) - one bar drawn, distribution along the developed floor
    bx = L * 0.12
    y0, y1 = -t + cw, W + t - cw
    lgk = min(LG, 1100)
    pts = [X(bx + lgk, y0), X(bx, y0), X(bx, y1), X(bx + lgk, y1)]
    gen_f.draw_bar(sh, pts, yb, lyr, 1, 260, legs=(LG, LG))
    sh.pline([X(-t + cw, W * 0.82), X(L + t - cw, W * 0.82)], 'S-DIM', 0)
    for xx in (-t + cw, L + t - cw):
        sh.line(X(xx, W * 0.82 - 250), X(xx, W * 0.82 + 250), 'S-DIM')
    px, py = X(bx + 900, W * 0.82 + 120)
    sh.ctext(yb['marks'][0][0], f"{lay}1: " + cot(yb), px, py, ST['call'] * 0.9)
    # X bars (inner layer) along the pool, bent at the slope changes
    by = W * 0.35
    pts = [X(-t + cw, by - lgk), X(-t + cw, by), X(L + t - cw, by), X(L + t - cw, by - lgk)]
    gen_f.draw_bar(sh, pts, xb, lyr, 1, 260, legs=(LG, LG))
    sh.pline([X(L * 0.62, -t + cw), X(L * 0.62, W + t - cw)], 'S-DIM', 0)
    for yy in (-t + cw, W + t - cw):
        sh.line(X(L * 0.62 - 250, yy), X(L * 0.62 + 250, yy), 'S-DIM')
    px, py = X(4300, W * 0.58)
    sh.ctext(xb['marks'][0][0], f"{lay}2: " + cot(xb), px, py, ST['call'] * 0.9)
    sh.text(f'FLOOR {word} REINFORCEMENT - PLAN 1:100 (U LEGS {LG} FOLDED; LENGTHS DEVELOPED ALONG THE SLOPE)',
            X(-t, 0)[0], X(0, -t)[1] - 650, ST['panel'], 'S-SEC')
    # section along the pool: the X bar on its real profile, pattern A and B
    Xs = T_(3000, 8300, 1)
    long_section(sh, Xs, show_dims=False)
    for pi, pat in enumerate(xb['pats']):
        for i, (a, b) in enumerate(pat):
            q = sub(xb['pts'], a, b)
            off = (-1 if lay == 'B' else 1) * (0 if pi == 0 else 0) + (40 if i % 2 else 0)
            if pi == 1: continue                         # section shows pattern A; pattern B on the plan
            sh.pline([Xs(x, z + off) for x, z in q], lyr, 20, r=40)
    for x, z in sub(yb['run'], 0, plen(yb['run']))[:1]:
        pass
    run = yb['run']; S_ = plen(run)
    for i in range(yb['n']):
        p = sub(run, 0, min(S_, i * S_ / (yb['n'] - 1)))[-1] if i else run[0]
        sh.circle(*Xs(p[0], p[1] + (0 if lay == 'B' else 0)), 20, lyr)
    for xk in KINKS:
        px, py = Xs(xk, zb(xk) - BL - 350)
        sh.text(f'BEND AT x={xk}', px, py, ST['note'], 'S-DIM', align=TA.TOP_CENTER)
    sh.text(f'SECTION 1 - FLOOR {word} BARS ON THE FLOOR PROFILE (PATTERN A; PATTERN B = ALTERNATE BARS, SEE PLAN)',
            Xs(-t, 0)[0], Xs(0, -DMAX - h)[1] - 1100, ST['panel'], 'S-SEC')
    # developed bars of the two patterns
    yy = 2900
    for pi, pat in enumerate(xb['pats']):
        x = 3000
        sh.text(f"{lay}2 PATTERN {'AB'[pi]}:", 1000, yy - pi * 700, ST['note'], 'S-RFT-TXT')
        for a, b in pat:
            q = shape_of(sub(xb['pts'], a, b))
            mk = next(r['mark'] for r in bl.sorted() if r['shape'] == q and r['L'] == int(round(b - a)))
            sh.text(f'[{mk:02d}] {int(round(b - a))}', 3600 + a * 0.6, yy - pi * 700, ST['note'], 'S-RFT-TXT')
            sh.pline([(3600 + a * 0.6, yy - pi * 700 - 120), (3600 + b * 0.6, yy - pi * 700 - 120)], lyr, 25)
    sh.text('(DEVELOPED LENGTHS, SCALE 1:167)', 1000, yy - 1250, ST['note'] * 0.9, 'S-DIM')


floor_sheet('B'); floor_sheet('T')


# ---- sheet 4: long wall elevation at 1:50 in two halves
sh = sheet('LONG WALLS - ELEVATION (INNER FACE; OUTER FACE THE SAME OVER THE FULL LENGTH)', '1:50')
draw_legend(sh, 19000, 28300)
k = 2
HALVES = [(-t, L / 2, 25600), (L / 2, L + t, 18600)]
def clip(a, b, lo, hi): return (max(a, lo), min(b, hi)) if min(b, hi) > max(a, lo) else None
for hi_, (lo, hi, oy) in enumerate(HALVES):
    X = T_(2000 - lo * k, oy, k)
    sh.pline([X(lo, 0), X(hi, 0)], 'S-GB-CONC', 25)
    xs_ = [lo] + [x for x in [0] + KINKS + [L] if lo < x < hi] + [hi]
    sh.pline([X(x, zt(x)) for x in xs_ if 0 <= x <= L] or [X(lo, zt(lo))], 'S-GB-CONC', 25)
    sh.pline([X(x, zb(x)) for x in xs_], 'S-GB-CONC', 0)
    for x in (-t, 0, L, L + t):
        if lo <= x <= hi: sh.pline([X(x, 0), X(x, zb(x))], 'S-GB-CONC', 0 if x in (0, L) else 25)
    for v in [v for v in WALLV if v['wall'] == 'LONG' and v['face'] == 'INNER']:
        a, b = min(v['xs']), max(v['xs'])
        xm = v['xs'][len(v['xs']) // 2]
        zt_ = -cw; zf = zt_ - v['st']
        if lo <= xm <= hi:
            sh.pline([X(xm, zf), X(xm, zt_)], 'S-RFT-BOT', 25)
            sh.circle(*X(xm, zf), 40, 'S-RFT-BOT')                 # the foot turns into the floor (see sections)
            sh.mark(*X(xm, zb(xm) - 350), v['mk'], 230)
        c = clip(a, b, lo, hi)
        if c:
            ym = (zt_ + zf) / 2
            sh.pline([X(c[0], ym), X(c[1], ym)], 'S-DIM', 0)
            for xx in (a, b):
                if lo <= xx <= hi: sh.line(X(xx, ym - 60), X(xx, ym + 60), 'S-DIM')
    for hrec in [r for r in WALLH if r['wall'] == 'LONG']:
        for li, z in enumerate(hrec['zs']):
            pat = hrec['pats'][li % len(hrec['pats'])]
            for i, (a, b) in enumerate(pat):
                c = clip(hrec['a'] + a, hrec['a'] + b, lo, hi)
                if not c: continue
                o = 25 if i % 2 else 0
                sh.pline([X(c[0], -z - o), X(c[1], -z - o)], 'S-RFT-TOP', 15)
                mid = hrec['a'] + (a + b) / 2
                if lo <= mid <= hi:
                    sh.text(f"{int(round(b - a))}", *X(mid, -z - o + 25), ST['len'] * 0.45, 'S-DIM', align=TA.BOTTOM_CENTER)
            if lo <= hrec['a'] + 300 <= hi or (lo <= hrec['a'] and hrec['a'] <= hi):
                sh.mark(*X(max(hrec['a'], lo) + 250, -z), hrec['marks'][0][0], 110)
    sh.text(f"PART {hi_ + 1}: x = {lo:.0f} .. {hi:.0f} (x FROM THE INNER FACE OF THE SHALLOW WALL)  1:50", 2000, oy - (DMAX + h) * k - 900, ST['panel'], 'S-SEC')
y = 10500
sh.text('VERTICAL BARS (EACH FACE, BOTH LONG WALLS):', 1200, y, ST['panel'], 'S-SEC'); y -= 600
done = set()
for i, v in enumerate([v for v in WALLV if v['wall'] == 'LONG']):
    if v['face'] != 'INNER': continue
    vo = next((o for o in WALLV if o['wall'] == 'LONG' and o['face'] == 'OUTER' and o['st'] == v['st']), None)
    px, py = 1200 + (len(done) % 2) * 15500, y - (len(done) // 2) * 480
    done.add(v['mk'])
    sh.ctext(v['mk'], f"{callout(v['n'] + (vo['n'] if vo else 0), dV, v['mk'], legV + v['st'] + footV, sV, 'V')}  (INNER x {v['xs'][0]:.0f}..{v['xs'][-1]:.0f})  PER WALL", px, py, ST['call'] * 0.7)
y = y - ((len(done) + 1) // 2) * 480 - 300
sh.text('HORIZONTAL BARS (EACH FACE, BOTH LONG WALLS; LEVELS BELOW TOC):', 1200, y, ST['panel'], 'S-SEC'); y -= 600
for hrec in [r for r in WALLH if r['wall'] == 'LONG']:
    sh.ctext(hrec['marks'][0][0], f"{', '.join(str(z) for z in hrec['zs'])}: " +
             ' + '.join(callout(c, dH, m_, L_, sH if not j else None, 'H', stg=len(hrec['marks']) > 1 and not j) for j, (m_, c, L_) in enumerate(hrec['marks'])),
             1200, y, ST['call'] * 0.7); y -= 450
sh.text('VERTICAL BARS: C BAR OVER THE WALL TOP + FOOT ON THE FLOOR BOTTOM MESH; OVER THE SLOPE ONE LENGTH PER '
        f'{STEP} MM OF DEPTH (THE FOOT RISES < {STEP} MM INSIDE THE FLOOR). HORIZONTAL BARS STOP 100 ABOVE THE FLOOR.', 1200, y - 200, ST['note'], 'S-DIM')

# ---- sheet 5: cross sections 2 / 3 at 1:50
sh = sheet('SECTIONS 2 (DEEP END) AND 3 (SHALLOW END) - REINFORCEMENT', '1:50')
draw_legend(sh, 19000, 28300)
k = 2
for i, (nm, wall, x, oy) in enumerate((('SECTION 2 - DEEP END', 'DEEP', L - 2000, 21000), ('SECTION 3 - SHALLOW END', 'SHALLOW', 2000, 7600))):
    Xs = T_(3200, oy, k)
    d = cross_section(sh, Xs, x)
    zbm = -d - h + cb
    # floor Y bars (outer layers) with legs, X bars as dots
    for tg, z0, sg in (('B1', -d - h + cb + 7, 1), ('T1', -d - ct - 7, -1)):
        b = BARS[tg]; lyr = 'S-RFT-BOT' if tg[0] == 'B' else 'S-RFT-TOP'
        y0, y1 = -t + cw, W + t - cw
        sh.pline([Xs(y0, z0 + sg * LG), Xs(y0, z0), Xs(y1, z0), Xs(y1, z0 + sg * LG)], lyr, 25, r=40)
        px, py = Xs(W * (0.25 if tg == 'B1' else 0.12), z0)
        sh.ctext(b['marks'][0][0], f"{tg}: " + cot(b), px, py + (-700 if tg == 'B1' else 250), ST['call'] * 0.75)
    for tg, z0 in (('B2', -d - h + cb + 14 + 7), ('T2', -d - ct - 14 - 7)):
        lyr = 'S-RFT-BOT' if tg[0] == 'B' else 'S-RFT-TOP'
        for yy in positions(-t + cw + 50, W + t - cw - 50, BARS[tg]['s']):
            sh.circle(*Xs(yy, z0), 14, lyr)
        px, py = Xs(W * 0.8, z0)
        sh.ctext(BARS[tg]['marks'][0][0], f"{tg} @{BARS[tg]['s']} (SEE FLOOR SHEETS)", px, py + (-700 if tg == 'B2' else 250), ST['call'] * 0.7)
    # walls: C bars both faces, horizontal bars as dots
    vv = [v for v in WALLV if v['wall'] == wall]
    st = vv[0]['st']
    zt_ = -cw
    for yw, sgn in ((-t, 1), (W + t, -1)):
        xo = yw + sgn * cw; xi = yw + sgn * (t - cw)
        for xf, into in ((xo, sgn), (xi, sgn)):
            zf = zt_ - st
            sh.pline([Xs(xf + (sgn * legV if xf == xo else -sgn * legV), zt_), Xs(xf, zt_), Xs(xf, zf), Xs(xf + into * footV, zf)],
                     'S-RFT-BOT', 25, r=40)
        for z in SHORT_LV[wall]:
            for xf in (xo + sgn * 20, xi - sgn * 20):
                sh.circle(*Xs(xf, -z), 12, 'S-RFT-TOP')
    for j, v in enumerate(vv):
        px, py = Xs(-t, 0)[0] - 1800 + j * 0, Xs(0, 0)[1] + 700 + j * 520
        sh.ctext(v['mk'], f"{v['face']} FACE: " + callout(v['n'], dV, v['mk'], legV + v['st'] + footV, sV, 'V'), px + 1800, py, ST['call'] * 0.75)
    hr = next(r for r in WALLH if r['wall'] == wall)
    px, py = Xs(W * 0.35, 0)[0], Xs(0, 0)[1] + 700
    sh.ctext(hr['marks'][0][0], f"H (E.F.), LEVELS {', '.join(map(str, hr['zs']))}: " +
             ' + '.join(callout(c, dH, m_, L_, sH if not j else None, 'H', stg=len(hr['marks']) > 1 and not j) for j, (m_, c, L_) in enumerate(hr['marks'])),
             px, py, ST['call'] * 0.7)
    sh.text(nm + '  1:50', Xs(W / 2, 0)[0], Xs(0, -d - h)[1] - 900, ST['sub'], 'S-SEC', align=TA.MIDDLE_CENTER)

# ---- sheet 6: corner detail (plan) 1:10
sh = sheet('TYPICAL CORNER - HORIZONTAL BARS AND U BARS (4 CORNERS, EVERY LEVEL)', '1:20')
k = 5
X = T_(7000, 7000, k)
E = 1900
sh.pline([X(-t, -t), X(E, -t), X(E, 0), X(0, 0), X(0, E), X(-t, E)], 'S-GB-CONC', 25, True)
off = dH / 2
# long wall (along x) bars both faces to the far face, short wall (along y) the same, one bar diameter above
for yf in (-t + cw + off, -cw - off):
    sh.pline([X(-t + cw, yf), X(E, yf)], 'S-RFT-TOP', 30)
for xf in (-t + cw + off + dH, -cw - off - dH):
    sh.pline([X(xf, -t + cw), X(xf, E)], 'S-RFT-BOT', 30)
# U bars: base across the wall at the far face
yb0, yb1 = -t + cw + off + 2 * dH, -cw - off - 2 * dH
sh.pline([X(-t + cw + 2 * dH + legU, yb0 + 4), X(-t + cw + 2 * dH, yb0 + 4), X(-t + cw + 2 * dH, yb1 - 4), X(-t + cw + 2 * dH + legU, yb1 - 4)], 'S-RFT-STIR', 30, r=60)
sh.pline([X(yb0 + 4, -t + cw + 3 * dH + legU), X(yb0 + 4, -t + cw + 3 * dH), X(yb1 - 4, -t + cw + 3 * dH), X(yb1 - 4, -t + cw + 3 * dH + legU)], 'S-RFT-STIR', 30, r=60)
for xx in positions(-t + cw, E, sV):
    for yy in (-t + cw - 10, -cw + 10):
        sh.circle(*X(xx, yy), 7 * k / 10 * 1.0, 'S-RFT-BOT')
sh.ctext(mkU, callout(nU, dU, mkU, 2 * legU + t - 2 * cw) + f'  U BAR {legU}/{t - 2 * cw}/{legU} AT EVERY WALL END, EVERY LEVEL', *X(-t, E + 400), ST['call'])
sh.text('LONG WALL', *X(E * 0.6, -t - 220), ST['sub'], 'S-SEC', align=TA.MIDDLE_CENTER)
sh.text('SHORT WALL', *X(-t - 220, E * 0.75), ST['sub'], 'S-SEC', rot=90, align=TA.MIDDLE_CENTER)
sh.text('U BAR OF THE LONG WALL', *X(legU + 150, -cw - 3 * dH), ST['note'], 'S-RFT-TXT', align=TA.MIDDLE_LEFT)
sh.text('U BAR OF THE SHORT WALL', *X(-cw - 3 * dH, legU + 150), ST['note'], 'S-RFT-TXT', rot=90, align=TA.MIDDLE_LEFT)
sh.mark(*X(legU / 2, -t - 250), mkU, 200); sh.mark(*X(-t - 250, legU / 2), mkU, 200)
sh.text(f'LONG-WALL BARS RUN TO THE FAR FACE OF THE SHORT WALL; SHORT-WALL BARS ONE DIAMETER ABOVE; U LEGS {legU} >= 60d = {60 * dU}.',
        *X(-t, -t - 420), ST['note'], 'S-DIM')
sh.dim(X(-t, -t), X(0, -t), (0, X(0, -t)[1] - 500), text=str(t))
sh.dim(X(-t, -t), X(-t, 0), (X(-t, 0)[0] - 500, 0), angle=90, text=str(t))

# ---- BBS
m = dict(meta0); m['title'] = f"{P['name']}\nBBS"; m['dwg'] = 'SDW-STR-SP-BBS'
nb = draw_bbs(doc, IDX[0], bl.sorted(), m)
os.makedirs('out/POOL', exist_ok=True)
fn = f"out/POOL/{P.get('code', 'SP')}_POOL.dxf"
doc.saveas(fn)
tot = sum(r['n_in'] * r['n_el'] * r['L'] / 1000 * r['d'] ** 2 / 162 for r in bl.sorted())
print(fn, 'sheets', IDX[0], '+ BBS', nb, 'marks', len(bl.rows), f'steel {tot / 1000:.2f} t')
for tg, b in BARS.items():
    print(' ', tg, 'n', b['n'], 'T', b['T'], 'pieces', [(m_, c, L_) for m_, c, L_ in b['marks']])
for v in WALLV: print('  V', v['wall'], v['face'], v['st'], v['n'], 'x', v['n_el'])
for r in WALLH: print('  H', r['wall'], r['zs'], r['T'], r['marks'])
print('  U', nU)
