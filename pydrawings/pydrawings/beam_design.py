"""
The office beam design: the beams of a RAM level analysed and designed here, beside (or instead of) the bars RAM
designed for them.

RAM Concept keeps no strip forces in the .cpt, so the moments and shears come from the program's own analysis:
every beam is a continuous beam over the columns and walls it rests on (the same spans the beam strips use), the
load on it is the slab it carries (a tributary width to the next parallel beam / wall / column line or the slab
edge on each side) with the slab self-weight, the beam web below the slab and the area loads by loading type
read from the file, factored 1.2 D + 1.6 L. The elastic envelope comes from the three-moment equation with the
live load patterned (all spans, alternate spans, adjacent pairs); an end span framing into a column takes at
least wu L² / 16 hogging (SBC 304 / ACI 318 6.5). Flexure is designed as a singly reinforced rectangular section
(tension-controlled, As,min), shear with two-legged stirrups (Vc = 0.17 sqrt(f'c) b d, Vs limits, spacing
limits, minimum stirrups), and the deflection is checked by the span / depth table first and by calculation
(Branson's Ie, immediate + long-term with lambda = 2, L / 240 in all and L / 360 live) where the table is not met.

The result is indicative: the RAM design report governs. A beam failing deflection (or a section that cannot
carry its moment / shear) blocks the run in the app until the engineer decides, exactly like the punching alert.
"""
import math

from .geometry import dist, point_in_polygon, dist_to_polygon, js_round, fmt_num  # noqa: F401 (distToPolygon imported in JS, unused)
from .beam_strips import beam_spans
from .rebar import beams_by_others

PHI_F = 0.9
PHI_V = 0.75
CONCRETE = 25  # kN/m³


def BAR_AREA(d):
    return (math.pi * d * d) / 4


def _bars_text(n, dia):
    return f'{n}T{dia}' if (n and dia) else '-'


def r1(v):
    return js_round(v * 10) / 10


def r2(v):
    return js_round(v * 100) / 100


ASSUMED = {'dead': 2.5, 'live': 2.0}  # kN/m² when the file carries no area loads
MAIN_DIAS = [12, 16, 20, 25, 32]


def pick_bars(as_req, width, cover=40):
    """Bars of the smallest area not under `asReq` (mm²) that fit the width (at least two, clear spacing >= max(25, dia))."""
    best = None
    for dia in MAIN_DIAS:
        s = max(25, dia)
        n_max = max(2, math.floor((width - 2 * cover - 2 * 10 + s) / (dia + s)))
        for n in range(2, n_max + 1):
            area = n * BAR_AREA(dia)
            if area < as_req:
                continue
            if (not best) or area < best['area'] - 1 or (abs(area - best['area']) <= 1 and n < best['n']):
                best = {'n': n, 'dia': dia, 'area': js_round(area), 'text': _bars_text(n, dia)}
            break
    if not best:
        dia = 32
        n = math.ceil(as_req / BAR_AREA(dia))
        best = {'n': n, 'dia': dia, 'area': js_round(n * BAR_AREA(dia)), 'text': _bars_text(n, dia), 'overflow': True}
    return best


def three_moment(L, w, m_end=(0, 0)):
    """
    Support moments of a continuous beam (three-moment equation, pinned ends with known end moments): `L` in mm,
    `w` per span in kN/m, `mEnd` = [left, right] hogging moments in kN·m (negative) applied at the ends (cantilevers).
    """
    n = len(L)
    M = [0] * (n + 1)
    M[0] = m_end[0] or 0
    M[n] = m_end[1] or 0
    if n < 2:
        return M
    # unknowns M[1..n-1]; tridiagonal system in kN·m and m
    Lm = [v / 1000 for v in L]
    a, b, c, d = [], [], [], []
    for i in range(1, n):
        a.append(Lm[i - 1])
        b.append(2 * (Lm[i - 1] + Lm[i]))
        c.append(Lm[i])
        rhs = -(w[i - 1] * Lm[i - 1] ** 3 + w[i] * Lm[i] ** 3) / 4
        if i == 1:
            rhs -= M[0] * Lm[0]
        if i == n - 1:
            rhs -= M[n] * Lm[n - 1]
        d.append(rhs)
    # Thomas algorithm
    m = len(d)
    for i in range(1, m):
        f = a[i] / b[i - 1]
        b[i] -= f * c[i - 1]
        d[i] -= f * d[i - 1]
    x = [0] * m
    x[m - 1] = d[m - 1] / b[m - 1]
    for i in range(m - 2, -1, -1):
        x[i] = (d[i] - c[i] * x[i + 1]) / b[i]
    for i in range(1, n):
        M[i] = x[i - 1]
    return M


def _span_forces(L, w, Ma, Mb):
    """Span results from the end moments: max positive moment, the end shears (kN, kN·m; L in mm, w kN/m)."""
    Lm = L / 1000
    Va = (w * Lm) / 2 + (Mb - Ma) / Lm  # reaction at a (upwards) for hogging moments negative
    Vb = w * Lm - Va
    x = max(0, min(Lm, Va / w)) if w > 0 else Lm / 2
    Mmax = Ma + Va * x - (w * x * x) / 2
    return {'Va': Va, 'Vb': Vb, 'Mpos': max(0, Mmax), 'x': x * 1000}


def analyse_beam(spans, wD, wL, cantilevers=None):
    """
    The envelope of a beam over its spans under dead + patterned live load: hogging at every support (min), sagging
    per span (max), shears at each span end (max), and the service (unfactored, all spans) moments for deflection.
    """
    if cantilevers is None:
        cantilevers = {'left': None, 'right': None}
    L = [s['length'] for s in spans]
    n = len(L)
    cases = []
    all_ = [1 for _ in spans]
    cases.append(all_)
    if n > 1:
        cases.append([1 if i % 2 == 0 else 0 for i in range(n)])
        cases.append([1 if i % 2 == 1 else 0 for i in range(n)])
        for i in range(1, n):
            cases.append([1 if (k == i - 1 or k == i) else 0 for k in range(n)])

    def factored(live):
        return [1.2 * wD + 1.6 * wL * live[i] for i in range(n)]

    def end_m(wLc):
        left = cantilevers.get('left')
        right = cantilevers.get('right')
        return [-(wLc * (left / 1000) ** 2) / 2 if left else 0, -(wLc * (right / 1000) ** 2) / 2 if right else 0]

    Mneg = [0] * (n + 1)
    Mpos = [0] * n
    Vend = [[0, 0] for _ in spans]
    for live in cases:
        w = factored(live)
        M = three_moment(L, w, end_m(1.2 * wD + 1.6 * wL))
        for i in range(n + 1):
            Mneg[i] = min(Mneg[i], M[i])
        for i in range(n):
            f = _span_forces(L[i], w[i], M[i], M[i + 1])
            Mpos[i] = max(Mpos[i], f['Mpos'])
            Vend[i][0] = max(Vend[i][0], abs(f['Va']))
            Vend[i][1] = max(Vend[i][1], abs(f['Vb']))

    # service, all spans loaded, dead and live apart (for the deflection)
    def svc(w):
        M = three_moment(L, [w for _ in spans], end_m(w))
        return {'M': M, 'pos': [_span_forces(L[i], w, M[i], M[i + 1])['Mpos'] for i in range(n)]}

    return {'Mneg': Mneg, 'Mpos': Mpos, 'Vend': Vend, 'service': {'dead': svc(wD), 'live': svc(wL)}}


def flexure_as(Mu, b, d, fc, fy):
    """Required tension steel (mm²) of a rectangular section for Mu (kN·m); null when the section cannot carry it singly reinforced."""
    if Mu <= 0:
        return {'as': 0, 'ok': True}
    M = (Mu * 1e6) / PHI_F  # N·mm
    k = (fy * fy) / (1.7 * fc * b)
    disc = (fy * d) ** 2 - 4 * k * M
    if disc < 0:
        return {'as': None, 'ok': False}
    as_ = (fy * d - math.sqrt(disc)) / (2 * k)
    a = (as_ * fy) / (0.85 * fc * b)
    beta1 = 0.85 if fc <= 28 else max(0.65, 0.85 - 0.05 * ((fc - 28) / 7))
    c = a / beta1
    et = (0.003 * (d - c)) / c
    return {'as': as_, 'ok': et >= 0.004, 'et': r2(et)}


def shear_design(Vu, b, d, fc, fy):
    """Stirrups for Vu (kN) at d from the face: dia / legs / spacing, or null when the section is too small in shear."""
    sq = math.sqrt(fc)
    Vc = 0.17 * sq * b * d  # N
    VsMax = 0.66 * sq * b * d
    VuN = Vu * 1000
    if VuN > PHI_V * (Vc + VsMax):
        return {'ok': False, 'Vc': r1(Vc / 1000), 'Vs': r1((VuN / PHI_V - Vc) / 1000)}
    Vs = max(0, VuN / PHI_V - Vc)
    heavy = Vs > 0.33 * sq * b * d
    for dia in [10, 12]:
        for legs in [2, 4]:
            Av = legs * BAR_AREA(dia)
            s = min(d / 4 if heavy else d / 2, 300 if heavy else 600, (Av * fy) / (0.062 * sq * b), (Av * fy) / (0.35 * b))
            if Vs > 0:
                s = min(s, (Av * fy * d) / Vs)
            if VuN <= 0.5 * PHI_V * Vc:
                s = min(d / 2, 600)  # no shear reinforcement required: nominal stirrups
            s = max(50, math.floor(s / 25) * 25)
            if s >= 75 or (dia == 12 and legs == 4):
                return {'ok': True, 'dia': dia, 'legs': legs, 'spacing': s, 'Vc': r1(Vc / 1000), 'Vs': r1(Vs / 1000), 'text': f'T{dia}-{legs}L@{s}'}
    return {'ok': False, 'Vc': r1(Vc / 1000), 'Vs': r1(Vs / 1000)}


def deflection_check(o=None, **kw):
    """Deflection of one span: the span / depth table, else the calculated immediate + long-term deflection against L/240 and L/360 (live).

    Takes the JS options object as a dict (`{'L', 'b', 'h', 'd', 'as', 'fc', 'ends', 'Ma', 'MaLeft', 'MaRight', 'live', 'cantilever'}`)
    or as keywords (`as_` for the JS `as`, a Python keyword).
    """
    o = dict(o or {})
    o.update(kw)
    L = o['L']
    b = o.get('b')
    h = o.get('h')
    d = o.get('d')
    as_ = o.get('as', o.get('as_'))
    fc = o.get('fc')
    ends = o.get('ends')
    Ma = o.get('Ma')
    MaLeft = o.get('MaLeft')
    MaRight = o.get('MaRight')
    live = o.get('live')
    cantilever = o.get('cantilever', False)
    ratio_table = 8 if cantilever else 21 if ends == 2 else 18.5 if ends == 1 else 16
    h_min = L / ratio_table
    out = {'L': L, 'h_min': js_round(h_min), 'table_ok': h >= h_min, 'ratio': 0, 'ok': True}
    if out['table_ok']:
        return out
    Ec = 4700 * math.sqrt(fc)
    n = 200000 / Ec
    Ig = (b * h ** 3) / 12
    Mcr = (0.62 * math.sqrt(fc) * Ig) / (h / 2)  # N·mm
    A = b / 2
    B = n * as_
    C = -n * as_ * d
    kd = (-B + math.sqrt(B * B - 4 * A * C)) / (2 * A)
    Icr = (b * kd ** 3) / 3 + n * as_ * (d - kd) ** 2
    total = max(1, Ma) * 1e6  # N·mm, service all loads
    rr = min(1, Mcr / total) ** 3
    Ie = min(Ig, rr * Ig + (1 - rr) * Icr)
    live_share = live / Ma if Ma > 0 else 0
    if cantilever:
        delta = ((Ma * 1e6) * L * L) / (4 * Ec * Ie)  # w L^4 / (8 E I) with M = w L^2 / 2
    else:
        delta = ((5 * L * L) / (48 * Ec * Ie)) * (Ma - 0.1 * (abs(MaLeft or 0) + abs(MaRight or 0))) * 1e6
    delta = max(0, delta)
    d_live = delta * live_share
    d_dead = delta - d_live
    long_term = 2.0 * d_dead + d_live  # lambda = 2 on the sustained (dead) part, immediate live on top
    Leff = 2 * L if cantilever else L
    out['delta_immediate'] = r1(delta)
    out['delta_live'] = r1(d_live)
    out['delta_long_term'] = r1(long_term)
    out['limit_total'] = r1(Leff / 240)
    out['limit_live'] = r1(Leff / 360)
    out['ratio'] = r2(max(long_term / (Leff / 240), d_live / (Leff / 360)))
    out['ok'] = out['ratio'] <= 1
    out['Ie_ratio'] = r2(Ie / Ig)
    return out


def _tributary_width(bm, level, spans):
    """The slab width each side of the beam that loads it (mm): half way to the next parallel beam / wall / column line, or to the slab edge."""
    L = dist(bm['a'], bm['b']) or 1
    u = {'x': (bm['b']['x'] - bm['a']['x']) / L, 'y': (bm['b']['y'] - bm['a']['y']) / L}
    nrm = {'x': -u['y'], 'y': u['x']}
    mid = {'x': (bm['a']['x'] + bm['b']['x']) / 2, 'y': (bm['a']['y'] + bm['b']['y']) / 2}

    def along(p):
        return (p['x'] - bm['a']['x']) * u['x'] + (p['y'] - bm['a']['y']) * u['y']

    def offset(p):
        return (p['x'] - bm['a']['x']) * nrm['x'] + (p['y'] - bm['a']['y']) * nrm['y']

    cap = max(3000, 0.6 * max([s['length'] for s in spans] + [0]))
    sides = {}
    for sg in [1, -1]:
        best = cap * 2
        # parallel beams and walls overlapping this beam's length
        others = [x for x in (level.get('beams') or []) if x is not bm and x.get('id') != bm.get('id')] + list(level.get('walls') or [])
        for o in others:
            if not o.get('a') or not o.get('b'):
                continue
            Lo = dist(o['a'], o['b']) or 1
            v = {'x': (o['b']['x'] - o['a']['x']) / Lo, 'y': (o['b']['y'] - o['a']['y']) / Lo}
            if abs(u['x'] * v['x'] + u['y'] * v['y']) < 0.9:
                continue
            t0 = along(o['a'])
            t1 = along(o['b'])
            if max(t0, t1) < 0 or min(t0, t1) > L:
                continue
            off = offset(o['a']) * sg
            if off > bm['t'] / 2 + 50:
                best = min(best, off / 2)
        # a column line beside the beam (columns off its axis, within its length)
        for c in level.get('columns') or []:
            p = {'x': c['cx'], 'y': c['cy']}
            t = along(p)
            off = offset(p) * sg
            if t < -500 or t > L + 500:
                continue
            if off > max(c.get('w') or 0, c.get('h') or 0, c.get('d') or 0) / 2 + bm['t'] / 2 + 50:
                best = min(best, off / 2)
        # the slab edge, walked along the normal from the beam middle
        edge = 0
        s = 100
        while s <= cap * 2:
            p = {'x': mid['x'] + nrm['x'] * sg * s, 'y': mid['y'] + nrm['y'] * sg * s}
            if not point_in_polygon(p, level['outline']):
                edge = s
                break
            edge = s
            s += 100
        best = min(best, edge, cap)
        sides[sg] = max(0, best)
    return {'left': js_round(sides[1]), 'right': js_round(sides[-1]), 'total': js_round(sides[1] + sides[-1])}


def design_beams(level, spec=None):
    """
    Designs every beam of the level. `spec`: fc, fy, beamCover (40), beams.ramFailed (ids the engineer reports failing
    deflection in RAM). Returns per beam the loads, the envelope, the bars designed and the checks, plus the lists of
    failing / blocking beams.
    """
    if spec is None:
        spec = {}
    out = {'method': 'office', 'beams': [], 'failing': [], 'blocking': [], 'warnings': [], 'assumed': []}
    beams = level.get('beams') or []
    if not len(beams):
        return out
    fc = spec.get('fc') or 30
    fy = spec.get('fy') or 420
    cover = spec.get('beamCover') or 40
    loads = (level.get('ram') or {}).get('areaLoads') or []
    h_slab = level.get('thickness') or 250
    ram_failed = set(str(v).strip().upper() for v in ((spec.get('beams') or {}).get('ramFailed') or []))
    # beams assigned a type of the consultant's / project's schedule (spec.beamAssign) keep that design: not designed here
    assigned = set(str(v).strip().upper() for v in (spec.get('beamAssign') or {}).keys())
    others = beams_by_others(level, spec)  # the consultant's RC beams: not the office's to design
    no_loads = not len(loads)
    if no_loads:
        out['assumed'].append(f"no area loads in the model: SDL {fmt_num(ASSUMED['dead'])} kN/m² and LL {fmt_num(ASSUMED['live'])} kN/m² assumed")  # JS prints 2 for 2.0
    # a beam end on a drawing joint (a part of a split slab): the slab - and the beam - go on beyond it
    joints = level.get('jointEdges') or []
    pc = level.get('partCut')

    def dist_to_seg(p, a, b):
        L2 = (b['x'] - a['x']) ** 2 + (b['y'] - a['y']) ** 2
        t = max(0, min(1, ((p['x'] - a['x']) * (b['x'] - a['x']) + (p['y'] - a['y']) * (b['y'] - a['y'])) / L2)) if L2 else 0
        return math.hypot(p['x'] - (a['x'] + t * (b['x'] - a['x'])), p['y'] - (a['y'] + t * (b['y'] - a['y'])))

    def at_joint(p):
        if any(dist_to_seg(p, e['a'], e['b']) < 400 for e in joints):
            return True
        if not pc:
            return False
        overlap = pc.get('overlap') if pc.get('overlap') is not None else 600
        pj = pc.get('joints') or {}
        return bool((pj.get('lo') and abs(p[pc['axis']] - (pc['lo'] - overlap)) < 400) or (pj.get('hi') and abs(p[pc['axis']] - (pc['hi'] + overlap)) < 400))

    for bm in beams:
        if str(bm['id']).upper() in assigned or str(bm['id']).upper() in others:
            continue
        sp = beam_spans(bm, level.get('columns') or [], level.get('walls') or [], beams)  # (a deeper beam crossing it is a support)
        L = dist(bm['a'], bm['b'])
        mid = {'x': (bm['a']['x'] + bm['b']['x']) / 2, 'y': (bm['a']['y'] + bm['b']['y']) / 2}
        q = {}
        for kind in ['dead', 'live']:
            here = [l for l in loads if l.get('type') == kind and point_in_polygon(mid, l['polygon'])]
            any_ = [l for l in loads if l.get('type') == kind]
            q[kind] = max(l['q'] for l in here) if len(here) else max(l['q'] for l in any_) if len(any_) else ASSUMED[kind]
        # spans: the end pieces beyond the first / last support are cantilevers - unless the piece ends at a drawing
        # joint (the slab was split into parts for the sheets): there the beam goes on into the neighbouring part and is
        # continuous, so that end is taken as an interior support (hogging wu L² / 16), never as a free end
        spans = list(sp['spans'])
        cant = {'left': None, 'right': None}
        joint_ends = []
        if len(spans) and not spans[0].get('support0') and at_joint(bm['a']):
            spans[0] = {**spans[0], 'support0': {'kind': 'joint'}}
            joint_ends.append('start')
        if len(spans) and not spans[-1].get('support1') and at_joint(bm['b']):
            spans[-1] = {**spans[-1], 'support1': {'kind': 'joint'}}
            joint_ends.append('end')
        if len(joint_ends):
            out['warnings'].append(f"{bm['id']}: continues into the neighbouring part at its {' and '.join(joint_ends)} (drawing joint) - designed as a continuous beam, not a cantilever; the whole beam is designed on the unsplit slab")
        if len(spans) > 1 and not spans[0].get('support0'):
            cant['left'] = spans[0]['length']
            spans = spans[1:]
        if len(spans) > 1 and not spans[-1].get('support1'):
            cant['right'] = spans[-1]['length']
            spans = spans[:-1]
        no_supports = not any(s.get('support0') or s.get('support1') for s in spans)
        trib = _tributary_width(bm, level, spans)
        depth = bm.get('depth') or h_slab
        web = (CONCRETE * (bm['t'] / 1000) * max(0, depth - h_slab)) / 1000  # kN/m
        wD = r2((CONCRETE * (h_slab / 1000) + q['dead']) * (trib['total'] / 1000) + web)
        wL = r2(q['live'] * (trib['total'] / 1000))
        wu = r2(1.2 * wD + 1.6 * wL)
        env = analyse_beam(spans, wD, wL, cant)
        d = depth - cover - 10 - 8
        b = bm['t']
        reasons = []

        # hogging at the supports: at least wu L² / 16 at an end framing into a column, wu L² / 24 into a wall
        def support_kind(i):
            if i == 0:
                return (spans[0].get('support0') or {}).get('kind')
            if i == len(spans):
                return (spans[-1].get('support1') or {}).get('kind')
            return 'interior'

        Mneg = []
        for i, m in enumerate(env['Mneg']):
            kind = support_kind(i)
            Ls = (spans[0]['length'] if i == 0 else spans[i - 1]['length']) / 1000
            mn = (wu * Ls * Ls) / 16 if kind == 'column' else (wu * Ls * Ls) / 24 if kind == 'wall' else 0
            Mneg.append(-max(abs(m), mn if kind else 0))

        def as_of(m):
            f = flexure_as(m, b, d, fc, fy)
            if not f['ok']:
                reasons.append('flexure')
            return f['as'] if f['as'] is not None else math.inf

        top_as = max([as_of(abs(m)) for m in Mneg] + [0])
        bot_as = max([as_of(m) for m in env['Mpos']] + [0])
        as_min = max((0.25 * math.sqrt(fc)) / fy, 1.4 / fy) * b * d
        top = pick_bars(max(top_as, as_min), b, cover) if math.isfinite(top_as) else None
        bottom = pick_bars(max(bot_as, as_min), b, cover) if math.isfinite(bot_as) else None
        # shear at d from every support face
        Vu = 0
        for i, s in enumerate(spans):
            for k, sup in [[0, s.get('support0')], [1, s.get('support1')]]:
                face = (((sup or {}).get('along') or 0) / 2 + d) / 1000
                Vu = max(Vu, env['Vend'][i][k] - wu * face)
        if cant['left']:
            Vu = max(Vu, wu * (cant['left'] / 1000))
        if cant['right']:
            Vu = max(Vu, wu * (cant['right'] / 1000))
        sh = shear_design(Vu, b, d, fc, fy)
        if not sh['ok']:
            reasons.append('shear')
        # deflection per span, the worst governs
        defl = []
        for i, s in enumerate(spans):
            ends = (1 if (i > 0 or cant['left']) else 0) + (1 if (i < len(spans) - 1 or cant['right']) else 0)
            MaD = env['service']['dead']['pos'][i]
            MaL = env['service']['live']['pos'][i]
            as_here = max((bottom or {}).get('area') or 0, as_min)
            defl.append({'span': i + 1, **deflection_check({
                'L': s['length'], 'b': b, 'h': depth, 'd': d, 'as': as_here, 'fc': fc, 'ends': ends, 'Ma': MaD + MaL,
                'MaLeft': env['service']['dead']['M'][i] + env['service']['live']['M'][i],
                'MaRight': env['service']['dead']['M'][i + 1] + env['service']['live']['M'][i + 1], 'live': MaL})})
        for side, Lc in [['left', cant['left']], ['right', cant['right']]]:
            if Lc:
                MaD = (wD * (Lc / 1000) ** 2) / 2
                MaL = (wL * (Lc / 1000) ** 2) / 2
                defl.append({'span': side, **deflection_check({
                    'L': Lc, 'b': b, 'h': depth, 'd': d, 'as': max((top or {}).get('area') or 0, as_min), 'fc': fc, 'ends': 1,
                    'Ma': MaD + MaL, 'live': MaL, 'cantilever': True})})
        worst_list = sorted(defl, key=lambda p: -p['ratio'])
        worst = worst_list[0] if worst_list else {'ok': True, 'ratio': 0}
        if not worst['ok']:
            reasons.append('deflection')
        id_ = str(bm['id']).upper()
        uniq = list(dict.fromkeys(reasons))
        row = {
            'id': bm['id'], 'width': b, 'depth': depth, 'length': js_round(L),
            'spans': [{'length': js_round(s['length']), 'support0': (s.get('support0') or {}).get('kind') or None, 'support1': (s.get('support1') or {}).get('kind') or None,
                       'Mneg': r1(abs(Mneg[i])), 'Mpos': r1(env['Mpos'][i]), 'Vmax': r1(max(env['Vend'][i]))} for i, s in enumerate(spans)],
            'cantilevers': cant, 'no_supports': no_supports, 'trib_mm': trib,
            'loads': {'slab_kn_m2': r2(CONCRETE * h_slab / 1000), 'dead_kn_m2': q['dead'], 'live_kn_m2': q['live'], 'web_kn_m': r2(web), 'wD': wD, 'wL': wL, 'wu': wu},
            'Mneg_max': r1(max(abs(m) for m in Mneg)), 'Mpos_max': r1(max(env['Mpos'] + [0])), 'Vu': r1(Vu), 'd': d,
            'as_top_req': js_round(max(top_as, as_min)) if math.isfinite(top_as) else None,
            'as_bottom_req': js_round(max(bot_as, as_min)) if math.isfinite(bot_as) else None,
            'top': top, 'bottom': bottom,
            'stirrups': {'dia': sh['dia'], 'legs': sh['legs'], 'spacing': sh['spacing'], 'text': sh['text']} if sh['ok'] else None, 'shear': sh,
            'deflection': {**worst, 'spans': defl}, 'reasons': uniq, 'ram_failed': id_ in ram_failed,
            'status': 'fail' if (len(uniq) or id_ in ram_failed) else 'ok',
        }
        out['beams'].append(row)
        if row['status'] == 'fail':
            out['failing'].append(bm['id'])
            out['blocking'].append(bm['id'])
        if no_supports:
            out['warnings'].append(bm['id'])
    return out


def beam_blocking_after(check, decision):
    """Which failing beams still block the run after the engineer's decision."""
    if not check:
        return []
    blocking = check.get('blocking') or []
    if not decision or decision.get('mode') == 'deepen' or decision.get('mode') == 'thicken':
        return list(blocking)
    if decision.get('columns') == 'all' or decision.get('beams') == 'all' or not (decision.get('beams') or decision.get('columns')):
        covered = set(str(v).upper() for v in blocking)
    else:
        covered = set(str(v).strip().upper() for v in (decision.get('beams') or decision.get('columns')))
    return [id_ for id_ in blocking if str(id_).upper() not in covered]
