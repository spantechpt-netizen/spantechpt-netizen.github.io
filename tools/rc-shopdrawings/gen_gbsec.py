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
UW = lambda d: d * d / 162.0
LAYERS = {'GB-CONC': 7, 'GB-COL': 8, 'GB-RFT-TOP': 1, 'GB-RFT-BOT': 5, 'GB-STIR': 3, 'GB-TXT': 7, 'GB-DIM': 2,
          'GB-SEC': 4, 'COL-RFT': 6, 'COL-TIE': 6, 'GB-HATCH': 8, 'GB-TITLE': 7, 'GB-VPORT': 8, 'GB-LAP': 30}


def up10(v): return int(math.ceil(v / 10.0) * 10)


class Line:
    """one beam line: along coordinate u (mm from its start), levels, supports, bars, stirrups"""
    def __init__(self, L, sched, cols, top):
        self.L = L; self.code = L['code']; self.typ = max(L['types'], key=L['types'].get) if L['types'] else '?'
        p = sched[self.typ]; self.p = p
        self.w = L['w']; self.h = p['h']; self.top = top
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

    def spans(self):
        """clear spans between support faces (u)"""
        s = self.sup
        return [(s[i]['u1'], s[i + 1]['u0']) for i in range(len(s) - 1)]

    def build(self, report):
        p = self.p
        # longitudinal bars: straight from the end faces - cover, legs at both ends
        x0, x1 = COVER, self.len - COVER
        self.bars = []
        for pos, n, d, lg in (('T', p['nt'], p['dt'], LEG_T), ('B', p['nb'], p['db'], LEG_B)):
            lg = min(lg, self.h - 2 * COVER - 20)
            T = (x1 - x0) + 2 * lg; lp = 60 * d
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
                    zones.append((c0 - x0 + lg, c1 - x0 + lg))
            pats = lap_patterns_zoned(T, lp, zones) if T > STOCK and zones else None
            if pats and getattr(self, 'shortq', False):
                used = [u for pt in pats for (t0, t1) in pt[1:] for u in [t0 + lp / 2 - lg + x0]]
                for u in used:
                    for q in self.sup:
                        pass
                report.append(f'{self.code} {pos}: a quarter span next to a column is shorter than the lap {lp} - laps there run past the quarter (see RFI)')
            if T > STOCK and not pats:
                pats = lap_patterns(T, lp); report.append(f'{self.code} {pos}: laps could not be placed in the quarter spans next to the columns (RFI)')
            if T <= STOCK: pats = [[(0, T)]]
            cnt = [math.ceil(n / len(pats)), n - math.ceil(n / len(pats))] if len(pats) == 2 else [n]
            for pi, (pat, c) in enumerate(zip(pats, cnt)):
                pieces = []
                for t0, t1 in pat:
                    a_ = lg if t0 <= 1 else 0; b_ = lg if t1 >= T - 1 else 0
                    Ls = up10(t1 - t0)
                    st = Ls - a_ - b_
                    if a_ and b_: shape, dims = '21', dict(A=a_, B=st, C=b_)
                    elif a_ or b_: shape, dims = '11', dict(A=st, B=a_ or b_)
                    else: shape, dims = '00', dict(A=Ls)
                    desc = f"{'TOP' if pos == 'T' else 'BOTTOM'} {'(PATTERN ' + 'AB'[pi] + ')' if len(pats) == 2 else ''}".strip()
                    mk = self.mark(d, shape, tuple(sorted(dims.items())), Ls, c, pos, desc, 'R' if (b_ and not a_) else 'L')
                    # u position of the piece (developed t -> u)
                    u0 = x0 + max(0, t0 - lg); u1 = x0 + min(x1 - x0, t1 - lg)
                    pieces.append(dict(mark=mk, t0=t0, t1=t1, u0=u0, u1=u1, L=Ls, legL=bool(a_), legR=bool(b_), n=c))
                self.bars.append(dict(pos=pos, d=d, lg=lg, lp=lp, pat=pi, npat=len(pats), n=c, pieces=pieces))
        # stirrups: face to face of the columns, first one 50 from the face; through crossing beams
        s = p['s']; self.stirs = []
        ws, hs = self.w - 2 * COVER, self.h - 2 * COVER
        hook = max(10 * p['ds'], 75)
        Lst = up10(2 * (ws + hs) + 2 * hook)
        mk = self.mark(p['ds'], '51', (('A', ws), ('B', hs)), Lst, 0, 'S', 'STIRRUP')
        for a, b in self.spans():
            a, b = round(a), round(b); cl = b - a                  # whole mm (no float loss in the count)
            if cl < 150: continue
            n = int((cl - 100) // s) + 1
            self.stirs.append(dict(a=a, b=b, n=n, s=s, mark=mk, first=a + 50, last=a + 50 + (n - 1) * s))
        for m in self.marks:
            if m['mark'] == mk: m['n'] = sum(x['n'] for x in self.stirs)
        self.stir_dims = (ws, hs, Lst, hook)


# ------------------------------------------------------------------------------------------------ drawing helpers
class MS:
    def __init__(self, msp, ox, oy, th):
        self.m, self.ox, self.oy, self.th = msp, ox, oy, th          # th: text height for the view scale
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
                                  dimstyle='GBSEC%d' % round(self.th / 2.5), dxfattribs={'layer': 'GB-DIM'})
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
            if pc['legL'] and u_lo <= u0: pts.insert(0, (u0, y + sg * b_['lg']))
            if pc['legR'] and u1 <= u_hi: pts.append((u1, y + sg * b_['lg']))
            ms.pl(pts, lay, w=max(d * 0.7, 10))
            # mark + call-out on the piece (text above for top bars, below for bottom bars)
            um = clip((u0 + u1) / 2 + (k % 2) * 0)
            if u_lo + 300 < um < u_hi - 300:
                yy = (top + th * (1.6 + 2.8 * b_['pat'])) if pos == 'T' else (bot - th * (2.2 + 2.8 * b_['pat']))
                ms.ln((um, y), (um, yy - (0 if pos == 'T' else -th * 0.2)), 'GB-TXT')
                ms.hexmark(um, yy + th * 0.5 if pos == 'T' else yy - th * 0.5, pc['mark'], th * 0.8)
                ms.tx(callout(pc['n'], d, pc['mark'], pc['L']) + (f"  ({'AB'[b_['pat']]})" if b_['npat'] == 2 else ''), um + th * 1.1, (yy + th * 0.15) if pos == 'T' else (yy - th * 0.85), h=th * 0.8)
            # laps: dimension between consecutive pieces of the same pattern
            if k + 1 < len(b_['pieces']):
                nx = b_['pieces'][k + 1]
                l0, l1 = nx['u0'], u1
                if u_lo <= l0 and l1 <= u_hi:
                    yl = y + (-1 if pos == 'T' else 1) * (th * 0.9 + 40)
                    ms.dim((l0, y), (l1, y), (l0, yl), text=f"LAP {b_['lp']}")
    # stirrups: every stirrup drawn, zones dimensioned face to face
    for st in ln.stirs:
        u = st['first']
        while u <= st['last'] + 1:
            if u_lo <= u <= u_hi: ms.ln((u, bot + 40), (u, top - 40), 'GB-STIR')
            u += st['s']
        if u_lo <= st['a'] and st['b'] <= u_hi:
            yd = bot - th * (8.2 if not detail else 3.0)
            ms.dim((st['a'], bot), (st['first'], bot), (st['a'], yd), text='50')
            ms.dim((st['first'], bot), (st['last'], bot), (st['a'], yd), text=f"{st['n'] - 1}x{st['s']}={(st['n'] - 1) * st['s']}")
            ms.dim((st['last'], bot), (st['b'], bot), (st['a'], yd), text=f"{round(st['b'] - st['last'])}")
            ms.hexmark((st['a'] + st['b']) / 2 - th * 3.2, yd - th * 2.2, st['mark'], th * 0.8)
            ms.tx(callout(st['n'], ln.p['ds'], st['mark'], ln.stir_dims[2], st['s']), (st['a'] + st['b']) / 2 - th * 2.0, yd - th * 2.6, h=th * 0.8)
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
        rowh = (lg + 1350) if pos == 'T' else 1550
        lay = 'GB-RFT-TOP' if pos == 'T' else 'GB-RFT-BOT'
        yb = y - (300 if pos == 'T' else rowh - 900)                               # bar line of this row
        ms.tx(f"{'TOP' if pos == 'T' else 'BOTTOM'} BARS" + (f" - PATTERN {'AB'[b_['pat']]}" if b_['npat'] == 2 else '') + f" ({b_['n']} T{d})",
              -2600, yb - th * 0.4, h=th * 0.8)
        for k, pc in enumerate(b_['pieces']):
            off = (k % 2) * 450 * (-1 if pos == 'T' else 1)                       # neighbouring pieces apart so the lap shows
            yy = yb + off; sg = -1 if pos == 'T' else 1
            pts = [(pc['u0'], yy), (pc['u1'], yy)]
            if pc['legL']: pts.insert(0, (pc['u0'], yy + sg * lg))
            if pc['legR']: pts.append((pc['u1'], yy + sg * lg))
            ms.pl(pts, lay, w=max(d * 0.7, 10))
            st = round(pc['u1'] - pc['u0'])
            ms.tx(str(st), (pc['u0'] + pc['u1']) / 2, yy + th * 0.35, h=th * 0.85, al=TA.BOTTOM_CENTER)
            for flag, uu in ((pc['legL'], pc['u0']), (pc['legR'], pc['u1'])):
                if flag: ms.tx(str(lg), uu + (th * 0.9 if uu == pc['u0'] else -th * 0.3), yy + sg * lg / 2, h=th * 0.8, rot=90, al=TA.MIDDLE_CENTER)
            um = pc['u0'] + min(1500, (pc['u1'] - pc['u0']) * 0.15)
            ytx = yy + th * 1.6
            ms.hexmark(um, ytx + th * 0.4, pc['mark'], th * 0.8)
            parts = ([str(lg)] if pc['legL'] else []) + [str(st)] + ([str(lg)] if pc['legR'] else [])
            ms.tx(f"{callout(pc['n'], d, pc['mark'], pc['L'])}   L = {' + '.join(parts)} = {pc['L']}", um + th * 1.2, ytx, h=th * 0.8)
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
    ms.tx(f"T{p['ds']} @{p['s']} ({round(1000 / p['s'])} T{p['ds']}/m)", W + th * 2.8, H / 2 - th * 0.4, h=th * 0.75)
    ms.dim((0, 0), (W, 0), (0, -th * 5), text=str(W))
    ms.dim((0, 0), (0, H), (-th * 2.5, 0), angle=90, text=str(H))
    ms.dim((W, H), (W - COVER, H), (W, H + th * 4.5), text=str(COVER))
    ms.tx(f'COVER {COVER}', W + th * 0.6, H + th * 3.2, 'GB-DIM', h=th * 0.7)
    ms.tx(f'SECTION {label}-{label}', W / 2, -th * 9.5, 'GB-SEC', h=th * 1.4, al=TA.TOP_CENTER)
    # the stirrup alone with every dimension (out-to-out) and its hooks
    sx = W + th * 2.8 + 1300
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


def draw_bbs(lay, x, y, ln, beam, secname='', wmax=400.0, ymin=22.0):
    """BBS of this section only, in the office table approved on the footings / column necks (gen.draw_bbs_grouped):
    mark in a hexagon, steel grade, diameter, number in the element / of elements / total, the bar sketch with every
    part written on it, length (m), mass, total mass; total by diameter and of the section under it. Paper mm."""
    from gen import _symbol
    rows = sorted(ln.marks, key=lambda m: m['mark'])
    W = sum(w for _, w in BBS_COLS); rh = 950; head = 1700; tit = 900
    Ht = tit + head + rh * len(rows) + 1500
    k = min(wmax / W, (y - ymin) / Ht)
    sh = PS(lay, x, y - Ht * k, k); ytop = Ht                           # local units, origin at the table's lower-left
    bot = ytop - tit - head - rh * len(rows)
    sh.pline([(0, ytop), (W, ytop), (W, bot), (0, bot)], '', 0, True)
    sh.text(f'BBS - {secname} ({beam}) - THIS SECTION ONLY', W / 2, ytop - tit / 2, 300, align=TA.MIDDLE_CENTER)
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
    l = copy.deepcopy(l); typ = lambda q: max(q['types'], key=q['types'].get) if q['types'] else '?'
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


def main(lines_json, cfg_json, out):
    LJ = json.load(open(lines_json)); C = json.load(open(cfg_json))
    sched, cols = C['schedule'], C['columns']
    from ezdxf import recover as _rc
    src = _rc.readfile(C['frame']['dxf'])[0] if C.get('frame') else None
    doc = ezdxf.new('R2018', setup=True); doc.units = 4                          # mm
    for k, v in LAYERS.items():
        if k not in doc.layers: doc.layers.add(k, color=v)
    for sc_ in (20, 50, 100):                                   # dimension styles scaled for the viewport scales
        ds = doc.dimstyles.duplicate_entry('EZDXF', 'GBSEC%d' % sc_)
        ds.dxf.dimscale = sc_; ds.dxf.dimtxt = 2.0; ds.dxf.dimasz = 1.8; ds.dxf.dimexo = 1.0; ds.dxf.dimexe = 1.0; ds.dxf.dimgap = 0.8
        ds.dxf.dimtad = 1; ds.dxf.dimdec = 0; ds.dxf.dimblk = 'ARCHTICK'
    if src is not None:                                                         # the project title block (frame + key plan)
        from ezdxf.addons import importer
        im = importer.Importer(src, doc); im.import_block(C['frame']['block']); im.finalize()
    msp = doc.modelspace(); report = []
    # the reinforcement plan(s): the engineer's plan geometry copied 1:1 in place (measurable), our marks on it
    if C.get('plan_copy'):
        from ezdxf.addons import importer
        im = importer.Importer(src, doc)
        ents = [e for e in src.modelspace() if e.dxf.layer not in ('S-FRAME',) and e.dxftype() != 'VIEWPORT']
        win = C['plan_copy']['window']
        from ezdxf import bbox as _bb
        keep = []
        for e in ents:
            try: b = _bb.extents([e], fast=True)
            except Exception: continue
            if b.has_data and any(w[0] <= (b.extmin.x + b.extmax.x) / 2 <= w[2] and w[1] <= (b.extmin.y + b.extmax.y) / 2 <= w[3] for w in win):
                keep.append(e)
        dims_ = [e for e in keep if e.dxftype() == 'DIMENSION']
        im.import_entities([e for e in keep if e.dxftype() != 'DIMENSION'], msp); im.finalize()
        for e in dims_:                                         # the engineer's dimensions, exploded (lines + text) in place
            try:
                for v in e.virtual_entities():
                    if v.dxftype() in ('LINE', 'TEXT', 'MTEXT', 'SOLID', 'LWPOLYLINE', 'POINT'):
                        v.dxf.layer = 'GB-DIM'; msp.add_entity(v)
            except Exception: pass
    bases = {}
    for k, sheet in enumerate(C['sheets']):
        if sheet.get('kind') == 'plan':
            continue
        L = next(l for l in LJ[sheet['plan']] if l['code'] == sheet['line'])
        L = beam_ends(L, LJ[sheet['plan']], sched)
        ln = Line(L, sched, cols, sheet.get('top', C['levels']['top_gb']))
        ln.build(report)
        ox, oy = C['model_origin'][0], C['model_origin'][1] - k * 20000
        draw_long(MS(msp, ox, oy, 125), ln, cols)                                    # 1:50 text 2.5 mm
        y_det = ln.top - ln.h - 2900                                                  # bar detailing (tafreed) under the section
        y_end = draw_detailing(MS(msp, ox, oy, 125), ln, y_det)
        xs_x = ox + ln.len + 5000
        draw_xsec(MS(msp, xs_x, oy + ln.top - ln.h, 50), ln, sheet['xsec'])
        bases[sheet['line']] = (ln, ox, oy, xs_x)
        # cut of the cross section on the long section (mid of the first span), letter = sheet['xsec']
        sp = ln.spans()[0]; ua = (sp[0] + sp[1]) / 2 - 600
        ms = MS(msp, ox, oy, 125)
        for yy in (ln.top + 250, ln.top - ln.h - 250):
            ms.pl([(ua, yy), (ua, yy + (300 if yy > ln.top else -300))], 'GB-SEC', w=20)
        ms.tx(sheet['xsec'], ua + 60, ln.top + 600, 'GB-SEC', h=200); ms.tx(sheet['xsec'], ua + 60, ln.top - ln.h - 800, 'GB-SEC', h=200)
        # ---- paper-space sheet
        Wp, Hp = sheet.get('size', [841, 594])
        lay = doc.layouts.new(sheet['tab'])
        lay.page_setup(size=(Wp, Hp), margins=(0, 0, 0, 0), units='mm')
        sc = Wp / 1189.0
        if src is not None:
            lay.add_blockref(C['frame']['block'], (0, 0), dxfattribs={'xscale': sc, 'yscale': sc, 'layer': 'GB-TITLE'})
        for f, (fx, fy, fh) in C['frame']['title'].items():
            v = sheet.get(f, C['frame'].get('defaults', {}).get(f, ''))
            for j, part in enumerate(str(v).split('\n')):
                t = lay.add_text(part, height=fh * sc, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'})
                t.set_placement((fx * sc, (fy - j * fh * 1.6) * sc), align=TA.MIDDLE_CENTER)
        X0, Y1 = 14, Hp - 14
        def vp(cx, cy, w, h, mcx, mcy, scale, title):
            v = lay.add_viewport(center=(cx, cy), size=(w, h), view_center_point=(mcx, mcy), view_height=h * scale)
            v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
            lay.add_text(title, height=3.5, dxfattribs={'layer': 'GB-TITLE'}).set_placement((cx - w / 2 + 2, cy - h / 2 - 6))
        # SECTION A-A: the longitudinal section with the full bar detailing, 1:50
        ytop_m, ybot_m = ln.top + 2300, y_end - 300
        wl = (ln.len + 4400) / 50.0; hl = (ytop_m - ybot_m) / 50.0
        vp(X0 + wl / 2, Y1 - hl / 2 - 4, wl, hl, ox + ln.len / 2 - 1200, oy + (ytop_m + ybot_m) / 2, 50,
           f"SECTION {sheet['sec']}-{sheet['sec']}  -  {ln.typ} {ln.w}x{ln.h}, T.O.GB {ln.top / 1000:+.2f} - LONGITUDINAL SECTION + BAR DETAILING   SCALE 1:50")
        # cross section (stirrup) 1:20
        wx = (ln.w + 5600) / 20.0; hx = (ln.h + 2600) / 20.0
        yj = Y1 - hl - 22 - hx / 2
        vp(X0 + wx / 2, yj, wx, hx, xs_x + ln.w / 2 + 1900, oy + ln.top - ln.h / 2 - 200, 20,
           f"SECTION {sheet['xsec']}-{sheet['xsec']}  ({ln.typ} {ln.w}x{ln.h}) - STIRRUP T{ln.p['ds']} @{ln.p['s']}   SCALE 1:20")
        # BBS of this section, notes
        bx, by = X0 + wx + 14, Y1 - hl - 22
        hb, tot = draw_bbs(lay, bx, by, ln, ln.typ, f"SECTION {sheet['sec']}-{sheet['sec']}", wmax=1030 * sc - 8 - bx)
        notes = [f"NOTES (SECTION {sheet['sec']}-{sheet['sec']}, {ln.typ}):",
                 f"1. T.O.GB {ln.top / 1000:+.2f}, B.O.GB {(ln.top - ln.h) / 1000:+.2f}, BEAM {ln.w}x{ln.h} AS THE PLAN; COVER {COVER} ALL FACES.",
                 f"2. LAPS 60d ({', '.join(sorted({str(b_['lp']) for b_ in ln.bars}))}) IN THE FIRST / LAST QUARTER OF THE SPAN NEXT TO A COLUMN, PATTERNS A / B STAGGERED.",
                 f"3. END LEGS: TOP BARS {LEG_T} DOWN, BOTTOM BARS {LEG_B} UP, AT THE FAR FACE OF THE END COLUMN (COVER {COVER}).",
                 f"4. STIRRUPS T{ln.p['ds']} @{ln.p['s']} ({round(1000 / ln.p['s'])}/m PER THE SCHEDULE) FROM COLUMN FACE TO COLUMN FACE, FIRST 50 FROM THE FACE; NONE INSIDE THE COLUMNS.",
                 "5. COLUMN BARS AND TIES (MAGENTA) ARE THE COLUMN'S: FROM THE NECK THROUGH THE BEAM TO THE G.F - NOT IN THIS BBS.",
                 f"6. STIRRUPS {round(1000 / ln.p['s'])} T{ln.p['ds']}/m THROUGHOUT (NO DENSER ZONE IN THE SCHEDULE).",
                 "7. BAR DETAILING UNDER THE SECTION: EVERY BAR WITH ITS STRAIGHT LENGTH, LEGS AND LAPS; MARKS AS THE BBS."]
        if any(q.get('beam') for q in ln.sup):
            notes.append(f"8. END ON A BEAM: BARS TO THE FAR FACE OF THE SUPPORTING BEAM - COVER {COVER}, SAME LEGS; STIRRUPS FROM ITS FACE (OFFICE RULE - SEE RFI-08).")
        for j, s_ in enumerate(notes):
            lay.add_text(s_, height=2.3, dxfattribs={'layer': 'GB-TITLE'}).set_placement((X0, yj - hx / 2 - 16 - j * 4.6))
    # beam codes + section marks on the copied plan (model space, text 2.5 mm at 1:100)
    secs = {s_['line']: s_['sec'] for s_ in C['sheets'] if s_.get('kind') != 'plan'}
    for pn in C.get('plan_marks', []):
        for l in LJ[pn]:
            mid = (l['a'] + l['b']) / 2
            x, y = (mid, l['c']) if l['o'] == 'H' else (l['c'], mid)
            rot = 0 if l['o'] == 'H' else 90
            dx, dy = (0, l['w'] / 2 + 330) if l['o'] == 'H' else (-(l['w'] / 2 + 330), 0)
            if l['code'] in C.get('held', {}):                     # held line: HOLD + the RFI on the plan
                t_ = msp.add_text(f"HOLD - {C['held'][l['code']]}", height=200, rotation=rot, dxfattribs={'layer': 'GB-SEC', 'color': 1})
                t_.set_placement((x - dx * 2.2, y - dy * 2.2) if l['o'] == 'H' else (x + dx * 2.2, y), align=TA.MIDDLE_CENTER)
            if l['code'] in secs:                                   # longitudinal section cut: marks at both ends
                for e_, sg in ((l['a'], -1), (l['b'], 1)):
                    px, py = (e_ + sg * 700, l['c']) if l['o'] == 'H' else (l['c'], e_ + sg * 700)
                    msp.add_circle((px, py), 330, dxfattribs={'layer': 'GB-SEC', 'color': 4})
                    msp.add_text(secs[l['code']], height=300, dxfattribs={'layer': 'GB-SEC', 'color': 4}).set_placement((px, py), align=TA.MIDDLE_CENTER)
                    q0 = (e_ + sg * 370, l['c']) if l['o'] == 'H' else (l['c'], e_ + sg * 370)
                    msp.add_line(q0, (e_, l['c']) if l['o'] == 'H' else (l['c'], e_), dxfattribs={'layer': 'GB-SEC', 'color': 4, 'lineweight': 50})
    # plan sheets
    for k, sheet in enumerate(C['sheets']):
        if sheet.get('kind') != 'plan': continue
        Wp, Hp = sheet.get('size', [841, 594]); sc = Wp / 1189.0
        lay = doc.layouts.new(sheet['tab']); lay.page_setup(size=(Wp, Hp), margins=(0, 0, 0, 0), units='mm')
        if src is not None: lay.add_blockref(C['frame']['block'], (0, 0), dxfattribs={'xscale': sc, 'yscale': sc, 'layer': 'GB-TITLE'})
        for f, (fx, fy, fh) in C['frame']['title'].items():
            v = sheet.get(f, C['frame'].get('defaults', {}).get(f, ''))
            for j, part in enumerate(str(v).split('\n')):
                t = lay.add_text(part, height=fh * sc, dxfattribs={'layer': 'GB-TITLE', 'style': 'STANDARD'})
                t.set_placement((fx * sc, (fy - j * fh * 1.6) * sc), align=TA.MIDDLE_CENTER)
        x0, y0, x1, y1 = sheet['window']; s_ = sheet.get('scale', 100)
        w, h = (x1 - x0) / s_, (y1 - y0) / s_
        v = lay.add_viewport(center=(14 + w / 2, Hp - 14 - h / 2), size=(w, h), view_center_point=((x0 + x1) / 2, (y0 + y1) / 2), view_height=h * s_)
        v.dxf.status = 1; v.dxf.layer = 'GB-VPORT'
        lay.add_text(f"{sheet['caption']}   SCALE 1:{s_}", height=3.5, dxfattribs={'layer': 'GB-TITLE'}).set_placement((14, Hp - 14 - h - 7))
        for j, s2 in enumerate(sheet.get('notes', [])):
            lay.add_text(s2, height=2.4, dxfattribs={'layer': 'GB-TITLE'}).set_placement((14 + w + 10, Hp - 30 - j * 4.5))
    for nm in [l.name for l in doc.layouts if l.name.startswith('Layout')]:
        try: doc.layouts.delete(nm)
        except Exception: pass
    doc.saveas(out)
    return doc, bases, report


if __name__ == '__main__':
    doc, bases, rep = main(*sys.argv[1:4])
    print('\n'.join(rep)); print('saved', sys.argv[3])
