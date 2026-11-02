"""Grade-beam shop drawings in the "section sheet" format (Roya Zone 7, engineer 01-11-2026).

Every beam line gets ONE sheet (paper-space layout) with: the longitudinal section (viewport 1:50), its cross
sections and a beam-column joint detail (viewports 1:20), and the BBS of that section only. Model space holds every
element at its REAL size in mm (measurable); only the viewports carry the scale. Rules:
  * T.O.GB per line (default +0.85, tagged lines +0.55), h 700, cover 40 on every face.
  * top / bottom bars from the schedule, laps 60d inside the first / last quarter of the span next to a column,
    two staggered patterns (A / B), every piece its own mark; end legs: top 600 down, bottom 200 up.
  * stirrups from column face to column face (first 50 from the face), never inside the column; count from the
    schedule spacing over the clear span; column bars shown continuing from the neck to the G.F (not in the GB BBS),
    column ties continuing through the joint.
  * shape codes BS 8666: 00 straight, 11 one leg, 21 two legs (U), 51 closed link.

    python3 gen_gbsec.py lines.json gbsec.json out.dxf
gbsec.json: {schedule: {GB1: {b, h, nt, dt, nb, db, ds, s}}, columns: {C1: {n, d, td, ts}}, sheets: [{line: code,
plan: P1, dwg: '...-50225-00', title: '...'}], frame: {dxf, block, title: {field: [x, y, h]}}, levels: {...}}
"""
import json, math, sys
import ezdxf
from ezdxf.enums import TextEntityAlignment as TA
from gen import lap_patterns_zoned, lap_patterns, callout

COVER = 40
LEG_T, LEG_B = 600, 200
STOCK = 12000
LD_D = 60                       # development length = 60 d (general note 7 of the consultant's drawing)
SCALES = (20, 25, 30, 40, 50)   # longitudinal section: the largest that fits the sheet
XSCALE = 10                     # cross section scale
TXT = 3.0                       # paper text height (mm) of the call-outs on the sections


def gbcall(n, d, L, s=None):
    """office bar description: 2 T16-10370 / 45 T10-1880-125"""
    return f"{n} T{d}-{int(round(L))}" + (f"-{int(round(s))}" if s else '')
UW = lambda d: d * d / 162.0
LAYERS = {'GB-CONC': 7, 'GB-COL': 8, 'GB-RFT-TOP': 1, 'GB-RFT-BOT': 5, 'GB-STIR': 3, 'GB-TXT': 7, 'GB-DIM': 2,
          'GB-SEC': 4, 'GB-STARTER': 6, 'COL-RFT': 6, 'COL-TIE': 6, 'GB-HATCH': 8, 'GB-TITLE': 7, 'GB-VPORT': 8, 'GB-LAP': 30}


def up10(v): return int(math.ceil(v / 10.0) * 10)


class Line:
    """one beam line: along coordinate u (mm from its start), levels, supports, bars, stirrups"""
    def __init__(self, L, sched, cols, top):
        self.L = L; self.code = L['code']; self.typ = L.get('typ') or (max(L['types'], key=L['types'].get) if L['types'] else '?')
        p = sched[self.typ]; self.p = p
        self.w = L['w']; self.h = p['h']; self.top = L.get('top', top)
        self.len = L['b'] - L['a']
        self.sup = [dict(q, u0=q['s0'] - L['a'], u1=q['s1'] - L['a']) for q in L['sup']]
        self.cross = [dict(q, u0=q['s0'] - L['a'], u1=q['s1'] - L['a']) for q in L['cross']]
        self.cols = cols
        self.marks = []                                  # dict(mark, d, shape, dims, L, n, pos, desc)

    def mark(self, d, shape, dims, Lc, n, pos, desc, side='L'):
        for m in self.marks:
            if m['d'] == d and m['shape'] == shape and m['dims'] == dims and m['L'] == Lc and m['pos'] == pos:
                m['n'] += n; return m['mark']
        m = dict(mark=len(self.marks) + 1, d=d, shape=shape, dims=dims, L=Lc, n=n, pos=pos, desc=desc, side=side)
        self.marks.append(m); return m['mark']

    def end_bar(self, end, d, lg):
        """(u of the bar end, leg) at one end of the line"""
        q = self.sup[0] if end == 'a' else self.sup[-1]
        at = q is not None and ((end == 'a' and q['u0'] <= 5) or (end == 'b' and q['u1'] >= self.len - 5))
        far = COVER if end == 'a' else self.len - COVER
        if at and q.get('core'):
            Ld = LD_D * d; face = q['face'] - self.L['a']
            if q['t'] - COVER >= Ld:
                return (face - Ld if end == 'a' else face + Ld), 0
            return far, max(Ld - (q['t'] - COVER), lg)
        return far, min(lg, self.h - 2 * COVER - 20)

    def spans(self):
        """clear spans between support faces (u)"""
        s = self.sup
        return [(s[i]['u1'], s[i + 1]['u0']) for i in range(len(s) - 1)]

    def build(self, report):
        p = self.p
        # longitudinal bars: to the far face of the end supports - cover with the end legs; at a core wall: Ld = 60 d
        # (straight when the wall along the axis is long enough, else to the far face - cover + a leg to complete Ld)
        self.bars = []
        for pos, n, d, lg in (('T', p['nt'], p['dt'], LEG_T), ('B', p['nb'], p['db'], LEG_B)):
            ends = [self.end_bar('a', d, lg), self.end_bar('b', d, lg)]
            (x0, lgA), (x1, lgB) = ends
            T = (x1 - x0) + lgA + lgB; lp = 60 * d
            # allowed lap zones: the quarter of the span next to every interior column (engineer), whole lap inside
            zones = []
            sp = self.spans()
            for i in range(1, len(self.sup) - 1):
                q = self.sup[i]; sl = sp[i - 1][1] - sp[i - 1][0]; sr = sp[i][1] - sp[i][0]
                for z0, z1 in ((q['u0'] - sl / 4, q['u0']), (q['u1'], q['u1'] + sr / 4)):
                    c0, c1 = z0 + lp / 2, z1 - lp / 2
                    if c1 < c0:                                   # quarter shorter than the lap: the lap ends at the column
                        cc = (q['u0'] - lp / 2) if z1 <= q['u0'] + 1 else (q['u1'] + lp / 2)   # face, never inside the column
                        c0, c1 = cc - 5, cc + 5
                        self.shortq = True
                    zones.append((c0 - x0 + lgA, c1 - x0 + lgA))
            pats = lap_patterns_zoned(T, lp, zones) if T > STOCK and zones else None
            if pats and getattr(self, 'shortq', False):
                report.append(f'{self.code} {pos}: a quarter span next to a column is shorter than the lap {lp} - laps there run past the quarter (see RFI)')
            if T > STOCK and not pats:
                pats = lap_patterns(T, lp); report.append(f'{self.code} {pos}: laps could not be placed in the quarter spans next to the columns (RFI)')
            if T <= STOCK: pats = [[(0, T)]]
            cnt = [math.ceil(n / len(pats)), n - math.ceil(n / len(pats))] if len(pats) == 2 else [n]
            for pi, (pat, c) in enumerate(zip(pats, cnt)):
                pieces = []
                for t0, t1 in pat:
                    a_ = lgA if t0 <= 1 else 0; b_ = lgB if t1 >= T - 1 else 0
                    Ls = up10(t1 - t0)
                    st = Ls - a_ - b_
                    if a_ and b_: shape, dims = '21', dict(A=a_, B=st, C=b_)
                    elif a_ or b_: shape, dims = '11', dict(A=st, B=a_ or b_)
                    else: shape, dims = '00', dict(A=Ls)
                    desc = f"{'TOP' if pos == 'T' else 'BOTTOM'} {'(PATTERN ' + 'AB'[pi] + ')' if len(pats) == 2 else ''}".strip()
                    mk = self.mark(d, shape, tuple(sorted(dims.items())), Ls, c, pos, desc, 'R' if (b_ and not a_) else 'L')
                    # u position of the piece (developed t -> u)
                    u0 = x0 + max(0, t0 - lgA); u1 = x0 + min(x1 - x0, t1 - lgA)
                    pieces.append(dict(mark=mk, t0=t0, t1=t1, u0=u0, u1=u1, L=Ls, legL=a_, legR=b_, n=c))
                self.bars.append(dict(pos=pos, d=d, lg=max(lgA, lgB), lp=lp, pat=pi, npat=len(pats), n=c, pieces=pieces))
        # stirrups: face to face of the columns, first one 50 from the face; through crossing beams
        s = p['s']; self.stirs = []
        ws, hs = self.w - 2 * COVER, self.h - 2 * COVER
        hook = max(10 * p['ds'], 75)
        Lst = up10(2 * (ws + hs) + 2 * hook)
        mk = self.mark(p['ds'], '51', (('A', ws), ('B', hs)), Lst, 0, 'S', 'STIRRUP')
        for a, b in self.spans():
            a, b = round(a), round(b); cl = b - a                  # whole mm (no float loss in the count)
            if cl < 150: continue
            # first AND last stirrup 50 from the support faces (engineer, 02-11-2026): spacing s, one closing
            # space <= s before the last stirrup when the clear length is not a multiple of s
            Lc = cl - 100; n = math.ceil(Lc / s - 1e-9) + 1
            pos = [a + 50 + i * s for i in range(n - 1)] + [b - 50]
            close = Lc - (n - 2) * s; tail = [close]
            if 0 < close < s / 2 and n >= 4:                       # short closing space: the last two spaces made equal
                c1 = (s + close) // 2; tail = [c1, s + close - c1]
                pos = pos[:-2] + [b - 50 - tail[1], b - 50]
            self.stirs.append(dict(a=a, b=b, n=n, s=s, mark=mk, first=a + 50, last=b - 50, pos=pos, close=close, tail=tail))
        for m in self.marks:
            if m['mark'] == mk: m['n'] = sum(x['n'] for x in self.stirs)
        self.stir_dims = (ws, hs, Lst, hook)


# ------------------------------------------------------------------------------------------------ drawing helpers
class MS:
    def __init__(self, msp, ox, oy, th, sc=None):
        self.m, self.ox, self.oy, self.th = msp, ox, oy, th          # th: text height for the view scale
        self.sc = sc or round(th / 2.5)                              # view scale (dimension style)
    def P(self, u, y): return (self.ox + u, self.oy + y)
    def pl(self, pts, layer, closed=False, w=0):
        e = self.m.add_lwpolyline([self.P(*q) for q in pts], close=closed, dxfattribs={'layer': layer})
        if w: e.dxf.const_width = w
        return e
    def ln(self, a, b, layer): return self.m.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': layer})
    def tx(self, s, u, y, layer='GB-TXT', h=None, rot=0, al=TA.BOTTOM_LEFT):
        t = self.m.add_text(s, height=h or self.th, rotation=rot, dxfattribs={'layer': layer, 'style': 'STANDARD'})
        t.set_placement(self.P(u, y), align=al); return t
    def hexmark(self, u, y, n, h=None):
        h = h or self.th; R = h * 1.05
        self.pl([(u + R * math.cos(math.radians(60 * k)), y + R * math.sin(math.radians(60 * k))) for k in range(6)], 'GB-TXT', True)
        self.tx(f'{n:02d}', u, y, h=h * 0.7, al=TA.MIDDLE_CENTER)
    def dim(self, a, b, base, angle=0, text='<>'):
        d = self.m.add_linear_dim(base=self.P(*base), p1=self.P(*a), p2=self.P(*b), angle=angle, text=text,
                                  dimstyle='GBSEC%d' % self.sc, dxfattribs={'layer': 'GB-DIM'})
        d.render()
    def hatch(self, pts, layer='GB-HATCH', pattern='ANSI31', scale=20):
        h = self.m.add_hatch(color=8, dxfattribs={'layer': layer}); h.set_pattern_fill(pattern, scale=scale)
        h.paths.add_polyline_path([self.P(*q) for q in pts], is_closed=True)
    def circle(self, u, y, r, layer, fill=False):
        if fill:
            h = self.m.add_hatch(color=7, dxfattribs={'layer': layer}); h.paths.add_edge_path().add_arc(self.P(u, y), r, 0, 360)
        else: self.m.add_circle(self.P(u, y), r, dxfattribs={'layer': layer})
    def brk(self, a, b, layer='GB-CONC'):
        (ua, ya), (ub, yb) = a, b; mu, my = (ua + ub) / 2, (ya + yb) / 2; z = max(abs(ub - ua), abs(yb - ya)) / 10
        if abs(yb - ya) < abs(ub - ua): self.pl([a, (mu - z, my), (mu - z / 2, my + z), (mu + z / 2, my - z), (mu + z, my), b], layer)
        else: self.pl([a, (mu, my - z), (mu + z, my - z / 2), (mu - z, my + z / 2), (mu, my + z), b], layer)


def draw_long(ms, ln, cols, u_lo=None, u_hi=None, detail=False):
    """longitudinal section of the line between u_lo..u_hi (whole line if None), y = level in mm (T.O.GB at top)."""
    th = ms.th; p = ln.p; H = ln.h; top = ln.top; bot = top - H
    u_lo = 0 if u_lo is None else u_lo; u_hi = ln.len if u_hi is None else u_hi
    clip = lambda u: min(max(u, u_lo), u_hi)
    # concrete: beam outline + PC-free (beam on the slab / soil), columns with breaks
    ms.pl([(u_lo, bot), (u_hi, bot)], 'GB-CONC'); ms.pl([(u_lo, top), (u_hi, top)], 'GB-CONC')
    if u_lo > 0: ms.brk((u_lo, bot - 150), (u_lo, top + 150))
    else: ms.pl([(0, bot), (0, top)], 'GB-CONC')
    if u_hi < ln.len: ms.brk((u_hi, bot - 150), (u_hi, top + 150))
    else: ms.pl([(ln.len, bot), (ln.len, top)], 'GB-CONC')
    ext = 900 if not detail else 1200
    for q in ln.sup:
        if q['u1'] < u_lo or q['u0'] > u_hi: continue
        a, b = clip(q['u0']), clip(q['u1'])
        if q.get('under_wall'):                                     # the beam runs on under the core wall (wall above it)
            ms.pl([(a, top), (a, top + 900)], 'GB-CONC'); ms.pl([(b, bot), (b, top + 900)], 'GB-CONC')
            ms.brk((a - 100, top + 900), (b + 100, top + 900))
            ms.hatch([(a, top), (b, top), (b, top + 900), (a, top + 900)], 'GB-HATCH', 'ANSI31', 25)
            ms.tx(q['lab'], (a + b) / 2, top + 900 + th * 1.2, al=TA.BOTTOM_CENTER, h=th * 0.9)
            ms.tx(f"{ln.typ} UNDER THE WALL ({q.get('wt', '')})", (a + b) / 2, bot - th * 12.6, al=TA.MIDDLE_CENTER, h=th * 0.75)
            ms.tx("NO STIRRUPS IN THE WALL", (a + b) / 2, bot - th * 13.9, al=TA.MIDDLE_CENTER, h=th * 0.75)
            continue
        if q.get('core'):                                           # core wall: hatched, above and below the beam
            for y0, y1 in ((bot - 900, bot), (top, top + 900)):
                ms.pl([(a, y0), (a, y1)], 'GB-CONC'); ms.pl([(b, y0), (b, y1)], 'GB-CONC')
            ms.pl([(a, bot), (a, top)] if q['u0'] > 5 else [(b, bot), (b, top)], 'GB-CONC')
            ms.brk((a - 100, bot - 900), (b + 100, bot - 900)); ms.brk((a - 100, top + 900), (b + 100, top + 900))
            if q['t'] > b - a + 5:                                  # wall continues along the axis: break line at the cut
                xe = a if q['u0'] <= 5 else b
                ms.brk((xe, bot - 900), (xe, top + 900))
            ms.hatch([(a, bot - 900), (b, bot - 900), (b, top + 900), (a, top + 900)], 'GB-HATCH', 'ANSI31', 25)
            ms.tx('CORE 1 WALL' + (f" (t = {q['t']})" if q['t'] <= b - a + 5 else ' (ALONG THE BEAM AXIS)'), (a + b) / 2, top + 900 + th * 1.2, al=TA.BOTTOM_CENTER, h=th * 0.9)
            continue
        if q.get('beam'):                                           # end on a beam: its cross section, cut
            ms.pl([(a, bot), (a, top)], 'GB-CONC'); ms.pl([(b, bot), (b, top)], 'GB-CONC')
            ms.hatch([(a, bot), (b, bot), (b, top), (a, top)], 'GB-HATCH', 'ANSI31', 15)
            first = q is ln.sup[0]                                   # label kept inside the view: left / right aligned
            yl = top + 900 + th * (1.2 if first else 2.8)          # second label one row higher: never on the first
            ms.tx(q['lab'], a if first else b, yl, al=TA.BOTTOM_LEFT if first else TA.BOTTOM_RIGHT, h=th * 0.9)
            ms.ln(((a + b) / 2, top), ((a + b) / 2, yl - th * 0.2), 'GB-TXT')
            continue
        for y0, y1 in ((bot - ext, bot), (top, top + ext)):
            ms.pl([(a, y0), (a, y1)], 'GB-CONC'); ms.pl([(b, y0), (b, y1)], 'GB-CONC')
        ms.brk((a - 100, bot - ext), (b + 100, bot - ext)); ms.brk((a - 100, top + ext), (b + 100, top + ext))
        lab = q['lab'].split()[0]; cs = cols.get(lab)
        ms.tx(q['lab'], (a + b) / 2, top + ext + th * 1.2, al=TA.BOTTOM_CENTER, h=th * 0.9)
        if cs:                                                     # column bars: from the neck below, on to the G.F above
            dc = cs['d']; e = 40 + cs['td'] + dc / 2
            for uc in (q['u0'] + e, q['u1'] - e):
                if u_lo <= uc <= u_hi:
                    ms.pl([(uc, bot - ext + 60), (uc, top + ext - 60)], 'COL-RFT', w=max(dc * 0.6, 8))
            yt = bot + 50
            while yt < top - 25:                                   # column ties continue through the joint
                ms.ln((max(a, q['u0'] + 40), yt), (min(b, q['u1'] - 40), yt), 'COL-TIE'); yt += cs['ts']
            if detail:                                             # the column bars written on the joint detail
                ms.tx(f"COLUMN BARS {lab}: {cs['n']} T{dc} FROM THE NECK", b + th * 0.6, bot - ext + th * 0.6, 'COL-RFT', h=th * 0.75)
                ms.tx("COLUMN BARS CONTINUE TO THE G.F", b + th * 0.6, top + ext - th * 1.6, 'COL-RFT', h=th * 0.75)
                ms.tx(f"COLUMN TIES T{cs['td']} @{cs['ts']} CONTINUE THROUGH THE JOINT", b + th * 0.6, top + th * 1.2, 'COL-TIE', h=th * 0.75)
                ms.tx("GB STIRRUPS STOP AT THE COLUMN FACES", a - th * 14, bot - th * 9.5, 'GB-STIR', h=th * 0.75)
        ms.hatch([(a, bot - ext), (b, bot - ext), (b, top + ext), (a, top + ext)], 'GB-HATCH', 'ANSI31', 40 if not detail else 15)
    for q in ln.cross:                                             # crossing beams (cut): dashed outline
        if q['u1'] < u_lo or q['u0'] > u_hi: continue
        e_ = ms.pl([(q['u0'], bot), (q['u0'], top)], 'GB-SEC'); e_.dxf.linetype = 'DASHED'
        e_ = ms.pl([(q['u1'], bot), (q['u1'], top)], 'GB-SEC'); e_.dxf.linetype = 'DASHED'
    # longitudinal bars (pattern B drawn a little inside pattern A so both show)
    for b_ in ln.bars:
        d = b_['d']; pos = b_['pos']; off = 40 + p['ds'] + d / 2 + (d * 1.6 if b_['pat'] else 0)
        y = top - off if pos == 'T' else bot + off
        lay = 'GB-RFT-TOP' if pos == 'T' else 'GB-RFT-BOT'
        for k, pc in enumerate(b_['pieces']):
            u0, u1 = pc['u0'], pc['u1']
            if u1 < u_lo or u0 > u_hi: continue
            pts = [(clip(u0), y), (clip(u1), y)]
            sg = -1 if pos == 'T' else 1
            if pc['legL'] and u_lo <= u0: pts.insert(0, (u0, y + sg * pc['legL']))
            if pc['legR'] and u1 <= u_hi: pts.append((u1, y + sg * pc['legR']))
            ms.pl(pts, lay, w=max(d * 0.7, 10))
            # mark + call-out on the piece (text above for top bars, below for bottom bars)
            um = clip((u0 + u1) / 2 + (k % 2) * 0)
            if u_lo + 300 < um < u_hi - 300:
                yy = (top + th * (1.6 + 2.8 * b_['pat'])) if pos == 'T' else (bot - th * (2.2 + 2.8 * b_['pat']))
                ms.ln((um, y), (um, yy - (0 if pos == 'T' else -th * 0.2)), 'GB-TXT')
                ms.hexmark(um, yy + th * 0.5 if pos == 'T' else yy - th * 0.5, pc['mark'], th * 0.8)
                ms.tx(gbcall(pc['n'], d, pc['L']) + (f"  ({'AB'[b_['pat']]})" if b_['npat'] == 2 else ''), um + th * 1.1, (yy + th * 0.15) if pos == 'T' else (yy - th * 0.85), h=th * 0.8)
            # laps: dimension between consecutive pieces of the same pattern
            if k + 1 < len(b_['pieces']):
                nx = b_['pieces'][k + 1]
                l0, l1 = nx['u0'], u1
                if u_lo <= l0 and l1 <= u_hi:
                    yl = y + (-1 if pos == 'T' else 1) * (th * 0.9 + 40)
                    ms.dim((l0, y), (l1, y), (l0, yl), text=f"LAP {b_['lp']}")
    # stirrups: every stirrup drawn, zones dimensioned face to face
    for st in ln.stirs:
        for u in st['pos']:
            if u_lo <= u <= u_hi: ms.ln((u, bot + 40), (u, top - 40), 'GB-STIR')
        if u_lo <= st['a'] and st['b'] <= u_hi:
            yd = bot - th * (8.2 if not detail else 3.0)
            ms.dim((st['a'], bot), (st['first'], bot), (st['a'], yd), text='50')
            if st['close'] == st['s'] or st['n'] < 3:
                ms.dim((st['first'], bot), (st['last'], bot), (st['a'], yd), text=f"{st['n'] - 1}x{st['s']}={round(st['last'] - st['first'])}")
                ms.dim((st['last'], bot), (st['b'], bot), (st['a'], yd), text='50')
            else:                                                   # closing spaces + the last 50 in one dimension (readable)
                k_ = len(st['tail']); p2 = st['pos'][-1 - k_]
                ms.dim((st['first'], bot), (p2, bot), (st['a'], yd), text=f"{st['n'] - 1 - k_}x{st['s']}={(st['n'] - 1 - k_) * st['s']}")
                ms.dim((p2, bot), (st['b'], bot), (st['a'], yd), text='+'.join(str(round(v)) for v in st['tail']) + '+50')
            ms.hexmark((st['a'] + st['b']) / 2 - th * 3.2, yd - th * 2.2, st['mark'], th * 0.8)
            ms.tx(gbcall(st['n'], ln.p['ds'], ln.stir_dims[2], st['s']), (st['a'] + st['b']) / 2 - th * 2.0, yd - th * 2.6, h=th * 0.8)
    # stair starter bars (plan positions, projecting out of the beam): marked on the section
    for k, (us, side) in enumerate(ln.L.get('starters', [])):
        if not (u_lo <= us <= u_hi): continue
        e_ = ms.pl([(us, bot + 60), (us, top - 60)], 'GB-STARTER', w=16); e_.dxf.linetype = 'DASHED'
        ms.circle(us, (top + bot) / 2, 30, 'GB-STARTER', fill=True)
    if ln.L.get('starters'):
        us_ = [u for u, _ in ln.L['starters']]
        yd = top + th * 3.2
        prev = None
        for u in sorted(us_):
            if prev is not None: ms.dim((prev, top), (u, top), (prev, yd), text=str(round(u - prev)))
            prev = u
        ref = ln.sup[-1]['u0'] if ln.sup[-1].get('core') else ln.len
        ms.dim((max(us_), top), (ref, top), (max(us_), yd), text=str(round(ref - max(us_))))
        ms.tx(f"{len(us_)} T16 STAIR STARTER BARS ({ln.L['starters'][0][1]}) - AS THE PLAN", min(us_), bot - th * 16.5, 'GB-STARTER', h=th * 0.8)
        ms.tx(ln.L.get('starter_ref', f"SHAPE / LENGTH: {ln.L.get('rfi_starters', 'RFI')}"), min(us_), bot - th * 17.8, 'GB-STARTER', h=th * 0.8)
        ms.ln((min(us_), (top + bot) / 2), (min(us_), bot - th * 15.5), 'GB-STARTER')
    # anchorage in a core wall: Ld written at the wall
    for q in ln.sup:
        if not q.get('core'): continue
        at_a = q['u0'] <= 5
        for b_ in ln.bars:
            if b_['pat']: continue
            d = b_['d']; Ld = LD_D * d; tw = q['t'] - COVER
            lgv = max(Ld - tw, b_['lg'])
            txt = (f"Ld = {LD_D}d = {Ld} STRAIGHT IN THE WALL" if tw >= Ld else
                   f"Ld = {LD_D}d = {Ld}: {tw} STRAIGHT IN THE WALL + LEG {lgv}" + (f" (MIN. LEG; {Ld - tw} NEEDED)" if lgv > Ld - tw else ''))
            yy = (top + th * 6.0) if b_['pos'] == 'T' else (bot - th * 13.8)
            ms.tx(f"{'TOP' if b_['pos'] == 'T' else 'BOTTOM'} T{d}: {txt}", (q['u1'] + th) if at_a else (q['u0'] - th), yy, 'GB-DIM', h=th * 0.75,
                  al=TA.BOTTOM_LEFT if at_a else TA.BOTTOM_RIGHT)
    # spans / columns chain + levels
    if not detail:
        yc = top + 900 + th * 4.5
        pts = [0] + [v for q in ln.sup for v in (q['u0'], q['u1'])] + [ln.len]
        pts = sorted(set(round(v) for v in pts))
        for a, b in zip(pts, pts[1:]):
            if b - a > 5: ms.dim((a, top), (b, top), (a, yc), text=str(b - a))
        ms.dim((0, top), (ln.len, top), (0, yc + th * 3), text=str(round(ln.len)))
    for yy, lab in ((top, f'T.O.GB {top / 1000:+.2f}'), (bot, f'B.O.GB {bot / 1000:+.2f}')):
        ms.ln((u_lo - (2200 if not detail else 900), yy), (u_lo - 100, yy), 'GB-DIM')
        ms.tx(lab, u_lo - (2200 if not detail else 900), yy + th * 0.3, 'GB-DIM', h=th * 0.8)
    ms.dim((u_lo - 300, bot), (u_lo - 300, top), (u_lo - 600, bot), angle=90, text=str(H))


def draw_detailing(ms, ln, y0):
    """full bar detailing (tafreed) under the longitudinal section: every longitudinal bar drawn at its place with its
    straight length, its legs and the laps between pieces written on it; mark + count + cutting length. -> lowest y"""
    th = ms.th; y = y0
    for b_ in ln.bars:
        pos = b_['pos']; d = b_['d']; lg = b_['lg']
        rowh = lg + 1350 + 2.5 * th
        lay = 'GB-RFT-TOP' if pos == 'T' else 'GB-RFT-BOT'
        yb = y - 300 - th if pos == 'T' else y - lg - 900 - th                     # bar line of this row
        ms.tx(f"{'TOP' if pos == 'T' else 'BOTTOM'} BARS" + (f" - PATTERN {'AB'[b_['pat']]}" if b_['npat'] == 2 else '') + f" ({b_['n']} T{d})",
              -2600, yb - th * 0.4, h=th * 0.8)
        for k, pc in enumerate(b_['pieces']):
            off = (k % 2) * 450 * (-1 if pos == 'T' else 1)                       # neighbouring pieces apart so the lap shows
            yy = yb + off; sg = -1 if pos == 'T' else 1
            pts = [(pc['u0'], yy), (pc['u1'], yy)]
            if pc['legL']: pts.insert(0, (pc['u0'], yy + sg * pc['legL']))
            if pc['legR']: pts.append((pc['u1'], yy + sg * pc['legR']))
            ms.pl(pts, lay, w=max(d * 0.7, 10))
            st = round(pc['u1'] - pc['u0'])
            ms.tx(str(st), (pc['u0'] + pc['u1']) / 2, yy + th * 0.35, h=th * 0.85, al=TA.BOTTOM_CENTER)
            for lgv, uu, left in ((pc['legL'], pc['u0'], True), (pc['legR'], pc['u1'], False)):
                if lgv: ms.tx(str(lgv), uu + (th * 0.9 if left else -th * 0.3), yy + sg * lgv / 2, h=th * 0.8, rot=90, al=TA.MIDDLE_CENTER)
            um = pc['u0'] + min(1500, (pc['u1'] - pc['u0']) * 0.15)
            ytx = yy + th * 1.6
            ms.hexmark(um, ytx + th * 0.4, pc['mark'], th * 0.8)
            parts = ([str(pc['legL'])] if pc['legL'] else []) + [str(st)] + ([str(pc['legR'])] if pc['legR'] else [])
            ms.tx(f"{gbcall(pc['n'], d, pc['L'])}   L = {' + '.join(parts)} = {pc['L']}", um + th * 1.2, ytx, h=th * 0.8)
            if k + 1 < len(b_['pieces']):                                         # the lap with the next piece
                nx = b_['pieces'][k + 1]
                ms.dim((nx['u0'], yb), (pc['u1'], yb), (nx['u0'], yb + sg * (-1) * (th * 2.0 + 450)), text=f"LAP {b_['lp']} (60d)")
        y -= rowh
    return y


def draw_xsec(ms, ln, label):
    """cross section of the line's beam type: concrete, stirrup with 135-deg hooks, bars, every dimension."""
    th = ms.th; p = ln.p; W, H = ln.w, ln.h
    ms.pl([(0, 0), (W, 0), (W, H), (0, H)], 'GB-CONC', True)
    ws, hs, Lst, hook = ln.stir_dims
    c = COVER + p['ds'] / 2
    ms.pl([(c, c), (W - c, c), (W - c, H - c), (c, H - c)], 'GB-STIR', True, w=p['ds'])
    ms.pl([(c + 15, H - c), (c + 15 + hook * 0.7, H - c - hook * 0.7)], 'GB-STIR', w=p['ds'])
    ms.pl([(c, H - c - 15), (c + hook * 0.7, H - c - 15 - hook * 0.7)], 'GB-STIR', w=p['ds'])
    for pos, n, d, y in (('T', p['nt'], p['dt'], H - COVER - p['ds'] - p['dt'] / 2), ('B', p['nb'], p['db'], COVER + p['ds'] + p['db'] / 2)):
        x0, x1 = COVER + p['ds'] + d / 2, W - COVER - p['ds'] - d / 2
        for i in range(n):
            ms.circle(x0 + (x1 - x0) * i / max(1, n - 1), y, d / 2, 'GB-RFT-TOP' if pos == 'T' else 'GB-RFT-BOT', fill=True)
        mk = next(m['mark'] for m in ln.marks if m['pos'] == pos)
        yy = H + th * 1.5 if pos == 'T' else -th * 2.5
        ms.ln(((x0 + x1) / 2, y), ((x0 + x1) / 2, yy), 'GB-TXT')
        ms.hexmark((x0 + x1) / 2 + th * 1.2, yy + th * 0.4, mk, th * 0.8)
        marks_ = sorted({m['mark'] for m in ln.marks if m['pos'] == pos})
        ms.tx(f"{n} T{d} {'TOP' if pos == 'T' else 'BOTTOM'} (MARKS {', '.join(f'{x:02d}' for x in marks_)})", (x0 + x1) / 2 + th * 2.4, yy, h=th * 0.75)
    ms.hexmark(W + th * 1.6, H / 2, ln.stirs[0]['mark'] if ln.stirs else 0, th * 0.8)
    ms.tx(f"STIRRUPS {round(1000 / p['s'])}T{p['ds']}/m' (GB SCHEDULE)", W + th * 2.8, H / 2 - th * 0.4, h=th * 0.75)
    if ln.L.get('starters'):                                       # stair starter bar out of the beam side (dashed)
        e_ = ms.pl([(0, H / 2), (-th * 9, H / 2)], 'GB-STARTER', w=16); e_.dxf.linetype = 'DASHED'
        ms.tx(f"T16 STAIR STARTER ({ln.L['starters'][0][1]})", -th * 9, H / 2 + th * 0.5, 'GB-STARTER', h=th * 0.7)
        if ln.L.get('starter_ref'): ms.tx(ln.L['starter_ref'].replace('STAIR STARTERS: ', ''), -th * 9, H / 2 - th * 1.2, 'GB-STARTER', h=th * 0.6)
    ms.dim((0, 0), (W, 0), (0, -th * 5), text=str(W))
    ms.dim((0, 0), (0, H), (-th * 2.5, 0), angle=90, text=str(H))
    ms.dim((W, H), (W - COVER, H), (W, H + th * 4.5), text=str(COVER))
    ms.tx(f'COVER {COVER}', W + th * 0.6, H + th * 3.2, 'GB-DIM', h=th * 0.7)
    ms.tx(f'SECTION {label}-{label}', W / 2, -th * 8.0, 'GB-SEC', h=th * 1.4, al=TA.TOP_CENTER)
    # the stirrup alone with every dimension (out-to-out) and its hooks
    sx = W + th * 26
    ms.pl([(sx, 0), (sx + ws, 0), (sx + ws, hs), (sx, hs)], 'GB-STIR', True, w=p['ds'])
    ms.pl([(sx + 20, hs), (sx + 20 + hook * 0.7, hs - hook * 0.7)], 'GB-STIR', w=p['ds'])
    ms.pl([(sx, hs - 20), (sx + hook * 0.7, hs - 20 - hook * 0.7)], 'GB-STIR', w=p['ds'])
    ms.dim((sx, 0), (sx + ws, 0), (sx, -th * 2.5), text=str(ws))
    ms.dim((sx + ws, 0), (sx + ws, hs), (sx + ws + th * 2.5, 0), angle=90, text=str(hs))
    ms.tx(f'HOOKS 135 DEG x {hook}', sx, hs + th * 1.0, h=th * 0.7)
    ms.tx(f'L = 2 x ({ws} + {hs}) + 2 x {hook} = {Lst}', sx, -th * 4.6, h=th * 0.7)


class PS:
    """paper-space drawing in the units of the office BBS (gen.py), scaled by k into sheet mm: lets the approved
    footing / neck BBS table and its bar sketches (gen._symbol) be drawn unchanged on a paper layout."""
    def __init__(self, lay, x0, y0, k): self.l, self.x0, self.y0, self.k = lay, x0, y0, k
    def P(self, x, y): return (self.x0 + x * self.k, self.y0 + y * self.k)
    def line(self, a, b, layer): self.l.add_line(self.P(*a), self.P(*b), dxfattribs={'layer': 'GB-TITLE'})
    def pline(self, pts, layer, width=0, closed=False, r=0):
        from gen import fillet
        if r: pts = fillet(pts, r, closed)
        e = self.l.add_lwpolyline([self.P(*q) for q in pts], dxfattribs={'layer': 'GB-TITLE'}); e.closed = closed; return e
    def text(self, s, x, y, h=250, layer='', rot=0, align=TA.BOTTOM_LEFT, maxw=None):
        t = self.l.add_text(s, height=h * self.k, rotation=rot, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'})
        t.set_placement(self.P(x, y), align=align); return t
    def circle(self, x, y, r, layer): self.l.add_circle(self.P(x, y), r * self.k, dxfattribs={'layer': 'GB-TITLE'})
    def mark(self, x, y, n, h=250, layer=''):
        R = h * 1.1
        self.pline([(x + R * math.cos(math.radians(60 * j)), y + R * math.sin(math.radians(60 * j))) for j in range(6)], '', 0, True)
        self.text(f'{int(n):02d}', x, y, h * 0.75, align=TA.MIDDLE_CENTER)


def bbs_shape(m):
    """BBS sketch of a mark in the office shape keys (gen._symbol): S straight, L one leg, U two legs, HT stirrup."""
    dm = dict(m['dims'])
    if m['shape'] == '00': return ('S', dm['A'])
    if m['shape'] == '11': return ('L', 0, dm['A'], dm['B']) if m.get('side') == 'R' else ('L', dm['B'], dm['A'])
    if m['shape'] == '21': return ('U', dm['A'], dm['B'], dm['C'])
    return ('HT', dm['A'], dm['B'])


def bbs_parts(m):
    """the parts of the bar, in order, as written on its sketch (they add up to the cutting length)"""
    sh = bbs_shape(m)
    if sh[0] == 'HT': return None
    return [v for v in sh[1:] if v]


BBS_COLS = [('Position', 2000), ('Steel grade', 1900), ('Diameter', 1900), ('in the\nelement', 2100), ('of elements', 2100),
            ('total', 1900), ('Symbol ( mm)', 6200), ('Length ( m)', 2300), ('Mass ( kg)', 2300), ('Total mass\n( kg)', 2500)]


def bbs_height(ln, k):
    return (900 + 1700 + 950 * len(ln.marks) + 1500) * k


def draw_bbs(lay, x, y, ln, beam, secname='', k=0.018, sheet_no=''):
    """BBS of one section, in the office table approved on the footings / column necks (gen.draw_bbs_grouped):
    mark in a hexagon, steel grade, diameter, number in the element / of elements / total, the bar sketch with every
    part written on it, length (m), mass, total mass; total by diameter and of the section under it. (x, y) = the
    table's top-left in paper mm, k = paper mm per table unit. Returns (height, kg by diameter)."""
    from gen import _symbol
    rows = sorted(ln.marks, key=lambda m: m['mark'])
    W = sum(w for _, w in BBS_COLS); rh = 950; head = 1700; tit = 900
    Ht = tit + head + rh * len(rows) + 1500
    sh = PS(lay, x, y - Ht * k, k); ytop = Ht                           # local units, origin at the table's lower-left
    bot = ytop - tit - head - rh * len(rows)
    sh.pline([(0, ytop), (W, ytop), (W, bot), (0, bot)], '', 0, True)
    sh.text(f'BBS - {secname} ({beam} {ln.w}x{ln.h}, T.O.GB {ln.top / 1000:+.2f})' + (f' - SHEET {sheet_no}' if sheet_no else ''), W / 2, ytop - tit / 2, 300, align=TA.MIDDLE_CENTER)
    hy = ytop - tit
    sh.line((0, hy), (W, hy), ''); sh.line((0, hy - head), (W, hy - head), '')
    cx = 0
    for i, (name, w) in enumerate(BBS_COLS):
        if i > 0: sh.line((cx, hy if i not in (4, 5) else hy - head / 2), (cx, bot), '')
        yy = hy - head / 2 if i not in (3, 4, 5) else hy - head * 0.75
        for j, part in enumerate(name.split('\n')):
            sh.text(part, cx + w / 2, yy + 120 - j * 260, 200, align=TA.MIDDLE_CENTER)
        cx += w
    nx = sum(w for _, w in BBS_COLS[:3])
    sh.line((nx, hy - head / 2), (nx + sum(w for _, w in BBS_COLS[3:6]), hy - head / 2), '')
    sh.text('Number', nx + sum(w for _, w in BBS_COLS[3:6]) / 2, hy - head / 4, 220, align=TA.MIDDLE_CENTER)
    tot = {}
    for r_, m in enumerate(rows):
        yr = hy - head - rh * (r_ + 1)
        sh.line((0, yr), (W, yr), '')
        mass = m['n'] * m['L'] / 1000.0 * UW(m['d']); tot[m['d']] = tot.get(m['d'], 0) + mass
        vals = [None, 'T', str(m['d']), str(m['n']), '1', str(m['n']), None, f"{m['L'] / 1000:.3f}", f'{mass:.2f}', f'{mass:.2f}']
        cx = 0
        for i, (name, w) in enumerate(BBS_COLS):
            if i == 0: sh.mark(cx + w / 2, yr + rh / 2, m['mark'], 240)
            elif i == 6: _symbol(sh, cx, yr, w, rh, bbs_shape(m), m['d'])
            else: sh.text(vals[i], cx + w / 2, yr + rh / 2, 200, align=TA.MIDDLE_CENTER)
            cx += w
    sh.text('TOTAL BY DIAMETER:  ' + '    '.join(f'T{d} = {v:,.2f} kg' for d, v in sorted(tot.items())), 0, bot - 500, 220, align=TA.MIDDLE_LEFT)
    sh.text(f'TOTAL STEEL WEIGHT ({secname}, {beam}) = {sum(tot.values()):,.2f} kg  ({sum(tot.values()) / 1000:.3f} t)', W, bot - 1100, 240, align=TA.MIDDLE_RIGHT)
    return Ht * k, tot


def beam_ends(l, lines, sched):
    """a line end with no column: the beam it frames into becomes the end support (office rule of the approved Roya
    package: bars to the FAR face of the end support - cover, same legs; stirrups from its face). Returns a copy of
    the line extended to that far face, or None when an end has nothing under it (held, RFI)."""
    import copy
    l = copy.deepcopy(l); typ = lambda q: q.get('typ') or (max(q['types'], key=q['types'].get) if q['types'] else '?')
    for end in ('a', 'b'):
        e = l[end]
        if any(q['s0'] - 60 <= e <= q['s1'] + 60 for q in l['sup']): continue
        hits = [q for q in lines if q['o'] != l['o'] and abs(q['c'] - e) <= q['w'] / 2 + 80 and q['a'] - 80 <= l['c'] <= q['b'] + 80]
        if not hits: return None
        q = hits[0]; s0, s1 = q['c'] - q['w'] / 2, q['c'] + q['w'] / 2
        l['sup'].append(dict(lab=f"{typ(q)} {q['w']}x{sched.get(typ(q), {}).get('h', 700)} (SUPPORTING BEAM)", s0=s0, s1=s1, beam=True))
        if end == 'a': l['a'] = min(l['a'], s0)
        else: l['b'] = max(l['b'], s1)
    l['sup'].sort(key=lambda q: q['s0'])
    return l


class StarterSet:
    """stair starter bars out of a beam (engineer 02-11-2026): shaped like column starters - a leg inside the beam
    (leg), straight across the beam inside the stirrup, projecting a lap of lap_d x d out of the beam."""
    def __init__(self, ln, d=16, leg=250, lap_d=65):
        self.ln = ln; self.d = d; self.leg = leg; self.lap = lap_d * d
        self.inside = ln.w - COVER - ln.p['ds']                      # across the beam, inside the stirrup
        self.st = self.inside + self.lap; self.Lc = self.st + self.leg
        self.n = len(ln.L.get('starters', []))
        self.marks = [dict(mark=1, d=d, shape='11', dims=(('A', self.st), ('B', leg)), L=self.Lc, n=self.n, pos='S', side='L')]
        self.w, self.h, self.top, self.typ = ln.w, ln.h, ln.top, f'STAIR STARTERS IN {ln.typ}'


def draw_starter_section(ms, ss, label):
    """cross section of the beam through a starter bar (1:10): the bar, its leg in the beam and its projection."""
    th = ms.th; ln = ss.ln; p = ln.p; W, H = ln.w, ln.h
    ms.pl([(0, 0), (W, 0), (W, H), (0, H)], 'GB-CONC', True)
    c = COVER + p['ds'] / 2
    ms.pl([(c, c), (W - c, c), (W - c, H - c), (c, H - c)], 'GB-STIR', True, w=p['ds'])
    for pos, n, d, y in (('T', p['nt'], p['dt'], H - COVER - p['ds'] - p['dt'] / 2), ('B', p['nb'], p['db'], COVER + p['ds'] + p['db'] / 2)):
        x0, x1 = COVER + p['ds'] + d / 2, W - COVER - p['ds'] - d / 2
        for i in range(n): ms.circle(x0 + (x1 - x0) * i / max(1, n - 1), y, d / 2, 'GB-RFT-TOP' if pos == 'T' else 'GB-RFT-BOT', fill=True)
    ys = H - COVER - p['ds'] - p['dt'] - ss.d / 2                    # under the top bars
    xe = W - COVER - p['ds']                                          # inner face of the far stirrup leg
    ms.pl([(xe, ys - ss.leg), (xe, ys), (-ss.lap, ys)], 'GB-STARTER', w=ss.d)
    ms.dim((xe, ys), (0, ys), (xe, ys + th * 3.5), text=str(ss.inside))
    ms.dim((0, ys), (-ss.lap, ys), (0, ys + th * 3.5), text=f"{ss.lap} ({round(ss.lap / ss.d)}d)")
    ms.dim((xe, ys), (xe, ys - ss.leg), (xe + th * 3, ys), angle=90, text=str(ss.leg))
    ms.hexmark(-ss.lap / 2, ys - th * 2.2, 1, th * 0.8)
    ms.tx(f"{gbcall(ss.n, ss.d, ss.Lc)}   L = {ss.leg} + {ss.inside} + {ss.lap} = {ss.Lc}", -ss.lap / 2 + th * 1.2, ys - th * 2.6, 'GB-STARTER', h=th * 0.8)
    ms.tx(f"TO THE STAIR ({ln.L['starters'][0][1]}) - LAP {round(ss.lap / ss.d)}d", -ss.lap, ys + th * 6.0, 'GB-STARTER', h=th * 0.75)
    ms.dim((0, 0), (W, 0), (0, -th * 4), text=str(W))
    ms.dim((W, 0), (W, H), (W + th * 6.5, 0), angle=90, text=str(H))
    ms.tx(f'SECTION {label}-{label}', W / 2, -th * 7.0, 'GB-SEC', h=th * 1.4, al=TA.TOP_CENTER)


def draw_starter_plan(ms, ss, ref_face_u):
    """the starters along the beam (plan strip, 1:20): positions dimensioned from the core / beam faces."""
    th = ms.th; ln = ss.ln; W = ln.w
    us = [u for u, _ in ln.L['starters']]
    u0, u1 = min(us) - 600, ref_face_u + 300
    ms.pl([(u0, 0), (ref_face_u, 0)], 'GB-CONC'); ms.pl([(u0, W), (ref_face_u, W)], 'GB-CONC')
    ms.brk((u0, -150), (u0, W + 150))
    ms.pl([(ref_face_u, -300), (ref_face_u, W + 300)], 'GB-CONC')
    ms.hatch([(ref_face_u, -300), (u1, -300), (u1, W + 300), (ref_face_u, W + 300)], 'GB-HATCH', 'ANSI31', 25)
    ms.tx('CORE 1 WALL', ref_face_u + 40, W + 400, h=th * 0.8)
    for u in us:
        ms.pl([(u, W - COVER - ln.p['ds']), (u, -ss.lap)], 'GB-STARTER', w=ss.d)
    prev = None
    for u in sorted(us) + [ref_face_u]:
        if prev is not None: ms.dim((prev, -ss.lap), (u, -ss.lap), (prev, -ss.lap - th * 3), text=str(round(u - prev)))
        prev = u
    ms.dim((min(us), 0), (min(us), -ss.lap), (min(us) - th * 3.5, 0), angle=90, text=str(ss.lap))
    ms.tx(f"GB2 {W}x{ln.h} (PLAN)", u0 + 100, W + th * 0.6, h=th * 0.8)
    ms.tx(f"{ss.n} T{ss.d} STAIR STARTER BARS - POSITIONS AS THE PLAN ({ln.L['starters'][0][1]})", u0 + 100, -ss.lap - th * 6.5, 'GB-STARTER', h=th * 0.8)


# ------------------------------------------------------------------------- clean copy of the consultant's entities
BAD_LAYER = set('<>/\\":;?*|=`,')


def _layer(doc, src, name):
    nm = ''.join('_' if ch in BAD_LAYER else ch for ch in (name or '0'))[:250] or '0'
    if nm not in doc.layers:
        col = 7
        try: col = src.layers.get(name).dxf.color
        except Exception: pass
        doc.layers.add(nm, color=abs(col) if col else 7)
    return nm


def clean_copy(doc, src, ents, dst, depth=0, keep_layer=None):
    """the consultant's entities exploded into plain primitives on our own table entries: no foreign block, text
    style, dimension style, linetype, xdata or proxy object can reach the file (what makes a DXF open everywhere)."""
    from ezdxf import path as _path
    from ezdxf.tools import pattern as _pat
    n = 0
    for e in ents:
        t = e.dxftype()
        try:
            lay = keep_layer or _layer(doc, src, e.dxf.layer)
            at = {'layer': lay}
            if e.dxf.hasattr('color') and e.dxf.color not in (None, 256): at['color'] = e.dxf.color
            if e.dxf.hasattr('true_color'): at['true_color'] = e.dxf.true_color
            lt = e.dxf.get('linetype', 'BYLAYER')
            if lt and lt.upper() not in ('BYLAYER', 'BYBLOCK') and lt in doc.linetypes: at['linetype'] = lt
            if t == 'INSERT':
                if depth > 6: continue
                for ins in (e.multi_insert() if e.mcount > 1 else [e]):
                    n += clean_copy(doc, src, ins.virtual_entities(), dst, depth + 1)
                for a_ in e.attribs:
                    if a_.dxf.text.strip(): n += clean_copy(doc, src, [a_], dst, depth + 1)
            elif t in ('DIMENSION', 'ARC_DIMENSION', 'LEADER', 'MLEADER', 'MULTILEADER', 'POLYLINE', 'ACAD_TABLE'):
                if depth > 6: continue
                n += clean_copy(doc, src, e.virtual_entities(), dst, depth + 1, keep_layer=lay)
            elif t == 'LINE':
                dst.add_line(e.dxf.start, e.dxf.end, dxfattribs=at); n += 1
            elif t == 'LWPOLYLINE':
                ocs = e.ocs(); z = e.dxf.extrusion.z
                pts = [(*ocs.to_wcs((x, y, e.dxf.elevation)).vec2, sw, ew, (b if z >= 0 else -b)) for x, y, sw, ew, b in e.get_points('xyseb')]
                pl = dst.add_lwpolyline(pts, format='xyseb', close=e.closed, dxfattribs=at)
                if e.dxf.hasattr('const_width'): pl.dxf.const_width = e.dxf.const_width
                n += 1
            elif t in ('CIRCLE', 'ARC'):
                c = e.ocs().to_wcs(e.dxf.center); z = e.dxf.extrusion.z
                if t == 'CIRCLE': dst.add_circle(c, e.dxf.radius, dxfattribs=at)
                else:
                    sa, ea = (e.dxf.start_angle, e.dxf.end_angle) if z >= 0 else (180 - e.dxf.end_angle, 180 - e.dxf.start_angle)
                    dst.add_arc(c, e.dxf.radius, sa, ea, dxfattribs=at)
                n += 1
            elif t in ('TEXT', 'ATTRIB'):
                if not e.dxf.text.strip(): continue
                ocs = e.ocs(); rot = e.dxf.get('rotation', 0) if e.dxf.extrusion.z >= 0 else 180 - e.dxf.get('rotation', 0)
                tx = dst.add_text(e.dxf.text, height=e.dxf.height, rotation=rot, dxfattribs=dict(at, style='STANDARD'))
                tx.dxf.insert = ocs.to_wcs(e.dxf.insert)
                if e.dxf.hasattr('align_point'): tx.dxf.align_point = ocs.to_wcs(e.dxf.align_point)
                for k_ in ('halign', 'valign', 'width', 'oblique'):
                    if e.dxf.hasattr(k_): tx.dxf.set(k_, e.dxf.get(k_))
                n += 1
            elif t == 'MTEXT':
                mt = dst.add_mtext(e.plain_text(), dxfattribs=dict(at, style='STANDARD', char_height=e.dxf.char_height,
                                   attachment_point=e.dxf.get('attachment_point', 1), insert=e.dxf.insert))
                if e.dxf.hasattr('width'): mt.dxf.width = e.dxf.width
                if e.dxf.hasattr('text_direction'): mt.dxf.text_direction = e.dxf.text_direction
                elif e.dxf.hasattr('rotation'): mt.dxf.rotation = e.dxf.rotation
                n += 1
            elif t == 'HATCH':
                h = dst.add_hatch(dxfattribs=at)
                pn = e.dxf.pattern_name
                if e.dxf.solid_fill or pn == 'SOLID': h.set_solid_fill(color=at.get('color', 7))
                else:
                    h.set_pattern_fill(pn if pn in _pat.ISO_PATTERN else 'ANSI31', scale=e.dxf.get('pattern_scale', 1) or 1, angle=e.dxf.get('pattern_angle', 0))
                for pth in _path.from_hatch(e):
                    pts = [v.vec2 for v in pth.flattening(1.0)]
                    if len(pts) > 2: h.paths.add_polyline_path(pts, is_closed=True)
                n += 1
            elif t in ('SOLID', 'TRACE', '3DFACE'):
                v = [e.dxf.get(k_) for k_ in ('vtx0', 'vtx1', 'vtx2', 'vtx3') if e.dxf.hasattr(k_)]
                if e.dxftype() != '3DFACE' and e.dxf.extrusion.z < 0: v = [e.ocs().to_wcs(q) for q in v]
                dst.add_solid(v, dxfattribs=at); n += 1
            elif t in ('ELLIPSE', 'SPLINE'):
                pts = [q.vec2 for q in e.flattening(1.0)] if t == 'SPLINE' else [q.vec2 for q in e.flattening(1.0)]
                if len(pts) > 1: dst.add_lwpolyline(pts, dxfattribs=at); n += 1
        except Exception:
            continue
    return n


def frame_block(doc, src, name):
    """the project's title block re-built from plain primitives (block 'ST_FRAME')"""
    b = doc.blocks.new('ST_FRAME')
    clean_copy(doc, src, src.blocks[name], b)
    return 'ST_FRAME'


def main(lines_json, cfg_json, out):
    LJ = json.load(open(lines_json)); C = json.load(open(cfg_json))
    sched, cols = C['schedule'], C['columns']
    from ezdxf import recover as _rc
    import logging; logging.getLogger('ezdxf').setLevel(logging.ERROR)
    src = _rc.readfile(C['frame']['dxf'])[0] if C.get('frame') else None
    doc = ezdxf.new(C.get('dxfversion', 'R2010'), setup=True); doc.units = 4                     # mm
    doc.header['$INSUNITS'] = 4; doc.header['$MEASUREMENT'] = 1
    for k, v in LAYERS.items():
        if k not in doc.layers: doc.layers.add(k, color=v)
    for sc_ in (10, 15, 20, 25, 30, 40, 50, 100):              # dimension styles scaled for the viewport scales
        ds = doc.dimstyles.duplicate_entry('EZDXF', 'GBSEC%d' % sc_)
        ds.dxf.dimscale = sc_; ds.dxf.dimtxt = 2.5; ds.dxf.dimasz = 2.0; ds.dxf.dimexo = 1.0; ds.dxf.dimexe = 1.0; ds.dxf.dimgap = 0.8
        ds.dxf.dimtad = 1; ds.dxf.dimdec = 0; ds.dxf.dimblk = 'ARCHTICK'
    FR = frame_block(doc, src, C['frame']['block']) if src is not None else None
    msp = doc.modelspace(); report = []
    # the reinforcement plan: the engineer's plan copied 1:1 in place (measurable), as plain entities, our marks on it
    if C.get('plan_copy'):
        from ezdxf import bbox as _bb
        win = C['plan_copy']['window']; keep = []
        for e in src.modelspace():
            if e.dxf.layer in ('S-FRAME',) or e.dxftype() == 'VIEWPORT': continue
            try: b = _bb.extents([e], fast=True)
            except Exception: continue
            if b.has_data and any(w[0] <= (b.extmin.x + b.extmax.x) / 2 <= w[2] and w[1] <= (b.extmin.y + b.extmax.y) / 2 <= w[3] for w in win):
                keep.append(e)
        report.append(f'plan copy: {clean_copy(doc, src, keep, msp)} entities')

    def new_sheet(sheet, Wp=841, Hp=594):
        lay = doc.layouts.new(sheet['tab'])
        lay.page_setup(size=(Wp, Hp), margins=(0, 0, 0, 0), units='mm')
        sc = Wp / 1189.0
        if FR: lay.add_blockref(FR, (0, 0), dxfattribs={'xscale': sc, 'yscale': sc, 'layer': 'GB-TITLE'})
        for f, (fx, fy, fh) in C['frame']['title'].items():
            v = sheet.get(f, C['frame'].get('defaults', {}).get(f, ''))
            for j, part in enumerate(str(v).split('\n')):
                t = lay.add_text(part, height=fh * sc, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'})
                t.set_placement((fx * sc, (fy - j * fh * 1.6) * sc), align=TA.MIDDLE_CENTER)
        return lay, sc

    def vp(lay, cx, cy, w, h, mcx, mcy, scale, title):
        v = lay.add_viewport(center=(cx, cy), size=(w, h), view_center_point=(mcx, mcy), view_height=h * scale)
        v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        lay.add_text(title, height=3.5, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((cx - w / 2 + 2, cy - h / 2 - 6))

    sections = [s_ for s_ in C['sheets'] if s_.get('kind') != 'plan']
    built = []; oy = C['model_origin'][1]
    for sheet in sections:
        if sheet.get('kind') == 'starter':                               # stair starter bars: own section + own BBS
            gl = next(l_ for s__, l_ in built if s__['line'] == sheet['line'])
            ss = StarterSet(gl, **C.get('starter_bar', {}))
            thx = TXT * XSCALE; ox = C['model_origin'][0]
            draw_starter_section(MS(msp, ox, oy, thx, XSCALE), ss, sheet['sec'])
            ref = next(q['u0'] for q in gl.sup if q.get('core'))
            px = ox + 4000
            draw_starter_plan(MS(msp, px, oy, TXT * 20, 20), ss, ref)
            lay, sc = new_sheet(sheet)
            X0, Y1 = 14, 594 - 14
            wm, hm = ss.lap + gl.w + 1500, gl.h + 1500
            vp(lay, X0 + wm / XSCALE / 2, Y1 - hm / XSCALE / 2, wm / XSCALE, hm / XSCALE, ox - ss.lap - 400 + wm / 2, oy - 550 + hm / 2, XSCALE,
               f"SECTION {sheet['sec']}-{sheet['sec']}  -  STAIR STARTER BARS {ss.n} T{ss.d} ({gl.typ} {gl.w}x{gl.h})   SCALE 1:{XSCALE}")
            us = [u for u, _ in gl.L['starters']]
            wp, hp = (ref + 1400) - (min(us) - 700), gl.w + ss.lap + TXT * 20 * 9 + 1100
            vp(lay, X0 + wm / XSCALE + 20 + wp / 40, Y1 - hp / 40, wp / 20, hp / 20, px + (min(us) - 700 + ref + 1400) / 2, oy + gl.w + 1000 - hp / 2, 20,
               f"STAIR STARTER BARS - PLAN ALONG THE {gl.typ} (SECTION {sheet['sec']}-{sheet['sec']} ON SHEET {sheet['seq']})   SCALE 1:20")
            notes = [f"NOTES (SECTION {sheet['sec']}-{sheet['sec']}, STAIR STARTER BARS):",
                     f"1. {ss.n} T{ss.d} STAIR STARTER BARS OUT OF THE {gl.typ} {gl.w}x{gl.h} (SECTION {sheet.get('parent_sec', '')}), AT THE POSITIONS OF THE PLAN.",
                     f"2. SHAPE AS THE COLUMN STARTERS: LEG {ss.leg} INSIDE THE BEAM, ACROSS THE BEAM INSIDE THE STIRRUP ({ss.inside}), PROJECTING A LAP OF {round(ss.lap / ss.d)}d = {ss.lap}.",
                     f"3. CUTTING LENGTH L = {ss.leg} + {ss.inside} + {ss.lap} = {ss.Lc}; BAR MARK 01 OF THIS SECTION; OWN BBS TABLE (SECTION {sheet['sec']}-{sheet['sec']}).",
                     "4. SHOWN UNDER THE TOP BARS OF THE BEAM, PROJECTING INTO THE STAIR."]
            for j, s2 in enumerate(notes):
                lay.add_text(s2, height=2.5, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((X0, Y1 - max(hm / XSCALE, hp / 20) - 20 - j * 4.6))
            built.append((sheet, ss)); oy -= 6000
            continue
        L = next(l for l in LJ[sheet['plan']] if l['code'] == sheet['line'])
        L = beam_ends(L, LJ[sheet['plan']], sched)
        if L.get('starters_abs'):
            L['starters'] = [(v - L['a'], side) for v, side in L['starters_abs']]
        ln = Line(L, sched, cols, C['levels']['top_gb']); ln.build(report)
        Wp, Hp = sheet.get('size', [841, 594]); sc = Wp / 1189.0
        AW, AH = 1030 * sc - 24, Hp - 28                                      # drawing area left of the title column
        thx = TXT * XSCALE; xl = thx * (12 if ln.L.get('starters') else 8)       # cross-section window (model mm)
        hx_m = ln.h + 1000; wx_m = xl + ln.w + 26 * thx + max(ln.stir_dims[0], 700) + 300
        Wx, Hx = wx_m / XSCALE, hx_m / XSCALE
        Hn, Hn_side = 13 * 4.6 + 6, 24 * 4.6 + 6                             # notes block (stacked / beside, wrapped)
        pick = None
        for s_ in SCALES:                                                    # the largest scale that fits
            th = TXT * s_
            Hm = 2300 + th * 4 + ln.h + 2900 + sum(b_['lg'] + 1350 + 2.5 * th for b_ in ln.bars) + 300
            Wm = ln.len + 3400 + 1000 + (th * 10 if ln.L.get('starters') else 0)
            W1, H1 = Wm / s_, Hm / s_
            if W1 <= AW and H1 + 14 + Hx + 12 + Hn <= AH: pick = (s_, 'stack', W1, H1, Wm, Hm); break
            if W1 + 12 + Wx <= AW and H1 <= AH and Hx + 14 + Hn_side <= AH: pick = (s_, 'side', W1, H1, Wm, Hm); break
        if pick is None:                                                     # notes beside the cross section (stacked)
            for s_ in SCALES:
                th = TXT * s_
                Hm = 2300 + th * 4 + ln.h + 2900 + sum(b_['lg'] + 1350 + 2.5 * th for b_ in ln.bars) + 300
                Wm = ln.len + 3400 + 1000 + (th * 10 if ln.L.get('starters') else 0)
                W1, H1 = Wm / s_, Hm / s_
                if W1 <= AW and H1 + 14 + max(Hx, Hn) + 12 <= AH: pick = (s_, 'stack', W1, H1, Wm, Hm); break
        if pick is None:
            s_ = SCALES[-1]; th = TXT * s_
            Hm = 2300 + th * 4 + ln.h + 2900 + sum(b_['lg'] + 1350 + 2.5 * th for b_ in ln.bars) + 300; Wm = ln.len + 4400
            pick = (s_, 'stack', Wm / s_, Hm / s_, Wm, Hm); report.append(f"{sheet['line']}: does not fit the sheet at 1:{s_}")
        s_, mode, W1, H1, Wm, Hm = pick; th = TXT * s_
        ox = C['model_origin'][0]
        ms = MS(msp, ox, oy, th, s_)
        draw_long(ms, ln, cols)
        y_det = ln.top - ln.h - 2900
        y_end = draw_detailing(ms, ln, y_det)
        xs_x = ox + ln.len + 6000
        draw_xsec(MS(msp, xs_x, oy + ln.top - ln.h, TXT * XSCALE, XSCALE), ln, sheet['xsec'])
        sp = ln.spans()[0]; ua = (sp[0] + sp[1]) / 2 - 600                  # cut of the cross section on the long section
        for yy in (ln.top + 250, ln.top - ln.h - 250):
            ms.pl([(ua, yy), (ua, yy + (300 if yy > ln.top else -300))], 'GB-SEC', w=th * 0.15)
        ms.tx(sheet['xsec'], ua - th * 0.5, ln.top + 400, 'GB-SEC', h=th * 1.4, al=TA.MIDDLE_RIGHT); ms.tx(sheet['xsec'], ua - th * 0.5, ln.top - ln.h - 400, 'GB-SEC', h=th * 1.4, al=TA.MIDDLE_RIGHT)
        # ---- the section sheet (no BBS on it: the BBS sheets follow)
        lay, sc = new_sheet(sheet, Wp, Hp)
        X0, Y1 = 14, Hp - 14
        ytop_m = ln.top + 2300 + th * 4; ybot_m = ytop_m - Hm
        vp(lay, X0 + W1 / 2, Y1 - H1 / 2, W1, H1, ox - 3400 + Wm / 2, oy + (ytop_m + ybot_m) / 2, s_,
           f"SECTION {sheet['sec']}-{sheet['sec']}  -  {ln.typ} {ln.w}x{ln.h}, T.O.GB {ln.top / 1000:+.2f} - LONGITUDINAL SECTION + BAR DETAILING   SCALE 1:{s_}")
        if mode == 'stack': xc, yc = X0 + Wx / 2, Y1 - H1 - 14 - Hx / 2
        else: xc, yc = X0 + W1 + 12 + Wx / 2, Y1 - Hx / 2
        vp(lay, xc, yc, Wx, Hx, xs_x - xl + wx_m / 2, oy + ln.top - ln.h - 550 + hx_m / 2, XSCALE,
           f"SECTION {sheet['xsec']}-{sheet['xsec']}  ({ln.typ} {ln.w}x{ln.h}) - STIRRUPS {round(1000 / ln.p['s'])}T{ln.p['ds']}/m'   SCALE 1:{XSCALE}")
        nds = round(1000 / ln.p['s'])
        notes = [f"NOTES (SECTION {sheet['sec']}-{sheet['sec']}, {ln.typ}):",
                 f"1. T.O.GB {ln.top / 1000:+.2f}, B.O.GB {(ln.top - ln.h) / 1000:+.2f}, BEAM {ln.w}x{ln.h} AS THE PLAN AND THE GB SCHEDULE ({ln.typ}); COVER {COVER} ALL FACES.",
                 f"2. LAPS 60d ({', '.join(sorted({str(b_['lp']) for b_ in ln.bars}))}) IN THE FIRST / LAST QUARTER OF THE SPAN NEXT TO A COLUMN, PATTERNS A / B STAGGERED; SHORT SPANS: LAP ENDS AT THE COLUMN FACE.",
                 f"3. END LEGS: TOP BARS {LEG_T} DOWN, BOTTOM BARS {LEG_B} UP, AT THE FAR FACE OF THE END SUPPORT - COVER {COVER}.",
                 f"4. STIRRUPS {nds}T{ln.p['ds']}/m' AS THE GB SCHEDULE ({ln.p['s']} c/c), FROM SUPPORT FACE TO SUPPORT FACE: FIRST AND LAST STIRRUP 50 FROM THE FACES, CLOSING SPACES < {ln.p['s']} AS DIMENSIONED; NONE INSIDE COLUMNS / WALLS.",
                 "5. COLUMN BARS AND TIES (MAGENTA) ARE THE COLUMN'S, AS THE COLUMN SCHEDULE: SHOWN FOR COORDINATION ONLY - NOT IN THE GB BBS / WEIGHTS.",
                 "6. BAR DETAILING UNDER THE SECTION: EVERY BAR WITH ITS STRAIGHT LENGTH, LEGS AND LAPS; MARKS AS THE BBS SHEETS.",
                 "7. AT BEAM CROSSINGS THE BARS OF THE BEAM WITH THE LARGER BAR DIAMETER PASS FIRST."]
        if any(q.get('beam') for q in ln.sup):
            notes.append(f"{len(notes)}. END ON A BEAM: BARS TO THE FAR FACE OF THE SUPPORTING BEAM - COVER {COVER}, SAME LEGS; STIRRUPS FROM ITS FACE; ITS OWN STIRRUPS CONTINUE.")
        if any(q.get('core') for q in ln.sup):
            notes.append(f"{len(notes)}. CORE 1 WALL: Ld = {LD_D}d (GENERAL NOTE 7) - STRAIGHT IN THE WALL WHERE IT IS LONG ENOUGH, ELSE TO ITS FAR FACE - COVER + LEG TO COMPLETE Ld; NO STIRRUPS IN THE WALL.")
        if ln.top != C['levels']['top_gb']:
            notes.append(f"{len(notes)}. BEAM AT T.O.GB {ln.top / 1000:+.2f} (RED ON THE PLAN): REINFORCED ON ITS OWN, LEGS IN ITS END COLUMNS; NOT CONTINUOUS WITH THE BEAMS AT {C['levels']['top_gb'] / 1000:+.2f}.")
        if ln.L.get('starters'):
            notes.append(f"{len(notes)}. STAIR STARTER BARS T16 AT THE PLAN POSITIONS: {ln.L.get('starter_ref', 'SEE THE STARTER SECTION')}.")
        nx_, ny_ = (X0 + Wx + 12, Y1 - H1 - 14 - 4) if mode == 'stack' else (X0 + W1 + 12, Y1 - Hx - 14 - 4)
        import textwrap
        wrap = max(40, int((1030 * sc - 10 - nx_) / 2.6))                  # notes kept left of the title column
        lines_ = [w_ for s2 in notes for w_ in (textwrap.wrap(s2, wrap, subsequent_indent='    ') or [''])]
        for j, s2 in enumerate(lines_):
            lay.add_text(s2, height=2.5, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((nx_, ny_ - j * 4.6))
        built.append((sheet, ln))
        oy -= Hm + 4000
    # ---- BBS sheets: one table per section, in section order (approved footing / neck format)
    K = C.get('bbs_k', 0.018); TW = sum(w for _, w in BBS_COLS) * K
    pages, cur, yy = [], [], 0
    for sheet, ln in built:
        hgt = bbs_height(ln, K) + 10
        if cur and yy + hgt > 594 - 28: pages.append(cur); cur, yy = [], 0
        cur.append((sheet, ln)); yy += hgt
    if cur: pages.append(cur)
    seq0 = int(C['bbs_seq']); summ = []; bbs_tabs = []
    for pi, page in enumerate(pages):
        no = seq0 + pi
        sh_ = dict(sections[0]); sh_.update(tab=f"Z07-GB-{no} BBS {pi + 1:02d}", t2=f"BAR BENDING SCHEDULE (BBS) {pi + 1}/{len(pages)}",
                                            dwg=C['bbs_dwg'].format(no=no), seq=str(no), scale_txt='-', size_txt='A1')
        lay, sc = new_sheet(sh_); bbs_tabs.append(sh_['tab'])
        y = 594 - 14
        for sheet, ln in page:
            h_, tot = draw_bbs(lay, 14, y, ln, ln.typ, f"SECTION {sheet['sec']}-{sheet['sec']}", K, sheet['seq'])
            summ.append((sheet, ln, tot)); y -= h_ + 10
        report.append(f"BBS sheet {no}: " + ', '.join(f"{s_['sec']}-{s_['sec']}" for s_, _ in page))
    # summary of the package on the last BBS sheet, right of the tables
    x0 = 14 + TW + 14; y = 594 - 14; rw = 6.0
    cw = [24, 30, 22, 22, 22, 26]
    hdr = ['SECTION', 'SHEET', 'T10 (kg)', 'T16 (kg)', 'T18 (kg)', 'TOTAL (kg)']
    lay.add_text('SUMMARY - GROUND BEAMS ZONE 7 PART 1 (NET, NO WASTE)', height=3.2, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((x0, y))
    rows = [[f"{s_['sec']}-{s_['sec']}", s_['seq']] + [f"{t.get(d, 0):,.2f}" for d in (10, 16, 18)] + [f"{sum(t.values()):,.2f}"] for s_, _, t in summ]
    g = {d: sum(t.get(d, 0) for _, _, t in summ) for d in (10, 16, 18)}
    rows.append(['TOTAL', ''] + [f"{g[d]:,.2f}" for d in (10, 16, 18)] + [f"{sum(g.values()):,.2f}"])
    y -= 4
    for r_i, row in enumerate([hdr] + rows):
        cx = x0
        for c_i, (v, w) in enumerate(zip(row, cw)):
            lay.add_lwpolyline([(cx, y), (cx + w, y), (cx + w, y - rw), (cx, y - rw)], close=True, dxfattribs={'layer': 'GB-TITLE'})
            t = lay.add_text(v, height=2.4, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}); t.set_placement((cx + w / 2, y - rw / 2), align=TA.MIDDLE_CENTER)
            cx += w
        y -= rw
    # ---- section marks / HOLD on the copied plan
    secs = {s_['line']: s_['sec'] for s_ in sections if s_.get('kind') != 'starter'}
    for s_ in sections:                                                  # starter section: cut across the beam on the plan
        if s_.get('kind') != 'starter': continue
        l = next(l_ for l_ in LJ[s_['plan']] if l_['code'] == s_['line'])
        yv = sum(v for v, _ in l['starters_abs']) / len(l['starters_abs'])
        for xv, sg in ((l['c'] - l['w'] / 2 - 1300, -1), (l['c'] + l['w'] / 2 + 500, 1)):
            msp.add_circle((xv, yv), 300, dxfattribs={'layer': 'GB-SEC', 'color': 4})
            msp.add_text(s_['sec'], height=260, dxfattribs={'layer': 'GB-SEC', 'color': 4, 'style': 'STANDARD'}).set_placement((xv, yv), align=TA.MIDDLE_CENTER)
        msp.add_line((l['c'] - l['w'] / 2 - 1000, yv), (l['c'] + l['w'] / 2 + 200, yv), dxfattribs={'layer': 'GB-SEC', 'color': 4, 'linetype': 'DASHED'})
    for pn in C.get('plan_marks', []):
        for l in LJ[pn]:
            mid = (l['a'] + l['b']) / 2
            x, y = (mid, l['c']) if l['o'] == 'H' else (l['c'], mid)
            rot = 0 if l['o'] == 'H' else 90
            dx, dy = (0, l['w'] / 2 + 330) if l['o'] == 'H' else (-(l['w'] / 2 + 330), 0)
            if l['code'] in C.get('held', {}):
                t_ = msp.add_text(f"HOLD - {C['held'][l['code']]}", height=200, rotation=rot, dxfattribs={'layer': 'GB-SEC', 'color': 1, 'style': 'STANDARD'})
                t_.set_placement((x - dx * 2.2, y - dy * 2.2) if l['o'] == 'H' else (x + dx * 2.2, y), align=TA.MIDDLE_CENTER)
            if l['code'] in secs:
                for e_, sg in ((l['a'], -1), (l['b'], 1)):
                    px, py = (e_ + sg * 450, l['c'] + l['w'] / 2 + 420) if l['o'] == 'H' else (l['c'] - l['w'] / 2 - 420, e_ + sg * 450)
                    msp.add_circle((px, py), 300, dxfattribs={'layer': 'GB-SEC', 'color': 4})
                    msp.add_text(secs[l['code']], height=260, dxfattribs={'layer': 'GB-SEC', 'color': 4, 'style': 'STANDARD'}).set_placement((px, py), align=TA.MIDDLE_CENTER)
    # ---- plan sheet
    for sheet in C['sheets']:
        if sheet.get('kind') != 'plan': continue
        lay, sc = new_sheet(sheet)
        x0, y0, x1, y1 = sheet['window']; s_ = sheet.get('scale', 100)
        w, h = (x1 - x0) / s_, (y1 - y0) / s_
        v = lay.add_viewport(center=(14 + w / 2, 594 - 14 - h / 2), size=(w, h), view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=h * s_)
        v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        lay.add_text(f"{sheet['caption']}   SCALE 1:{s_}", height=3.5, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((14, 594 - 14 - h - 7))
        for j, s2 in enumerate(sheet.get('notes', [])):
            lay.add_text(s2, height=2.5, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'}).set_placement((14 + w + 10, 594 - 30 - j * 4.6))
    for nm in [l.name for l in doc.layouts if l.name.startswith('Layout')]:
        try: doc.layouts.delete(nm)
        except Exception: pass
    # plan sheet first in the tab order
    order = [s_['tab'] for s_ in C['sheets'] if s_.get('kind') == 'plan'] + [s_['tab'] for s_ in sections] + bbs_tabs
    for i, nm in enumerate(order):
        try: doc.layouts.get(nm).dxf.taborder = i + 1
        except Exception: pass
    for e in list(doc.entitydb.values()):                         # every layer an entity names exists in the table
        try:
            if e.dxf.hasattr('layer') and e.dxf.layer not in doc.layers: doc.layers.add(e.dxf.layer)
        except Exception: pass
    au = doc.audit(); report.append(f'audit: {len(au.errors)} errors, {len(au.fixes)} fixes')
    doc.saveas(out)
    return doc, built, report


if __name__ == '__main__':
    doc, built, rep = main(*sys.argv[1:4])
    print('\n'.join(rep)); print('saved', sys.argv[3])
