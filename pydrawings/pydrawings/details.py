"""
Small section / plan details drawn at large scale in the bottom strip of a
sheet. Each builder returns { bbox, draw(pen) } with geometry in mm.

Port of `shopdrawings/lib/details.mjs`. Each builder takes the JS options object either as one dict (JS keys,
camelCase or snake_case) or as keyword arguments in snake_case (`hook_leg=`, `u_return=`, `ring_dia=` ...) and
returns a `Detail` with `.bbox` (dict with the JS keys) and `.draw(pen)`; `d['bbox']` / `d['draw']` work too.
The pen is the one `Sheet.detail_pen(...)` / `Sheet.make_pen(...)` return: `pen.line(a, b, **o)`,
`pen.pline(pts, **o)`, `pen.rect({'x','y','w','h'}, **o)`, `pen.circle(c, r, **o)`, `pen.arc(c, r, a1, a2, **o)`,
`pen.text(p, s, **o)`, `pen.hatch(polys, **o)`, `pen.solid(pts, **o)`, `pen.dim(a, b, off, **o)`,
`pen.bar_ends(a, b, **o)` (JS `barEnds`), with the option keys of the JS (`layer`, `lw`, `h`, `align`, `valign`,
`ltype`, `pattern`, `spacing`, `text`, `color`).
"""
import math
import re

from .geometry import circle_polygon, rect_polygon, js_round, fmt_num

_n = fmt_num  # `${v}` of a number in a JS template string


class Detail:
    """The `{ bbox, draw }` record a detail builder returns."""

    def __init__(self, bbox, draw):
        self.bbox = bbox
        self.draw = draw

    def __getitem__(self, k):
        return getattr(self, k)

    def get(self, k, default=None):
        return getattr(self, k, default)


def _snake(k):
    return re.sub(r'([A-Z])', lambda m: '_' + m.group(1).lower(), k)


def _args(o, kw):
    """The JS options object: a dict (camelCase or snake_case keys) and / or snake_case keywords."""
    out = {}
    for k, v in (o or {}).items():
        out[_snake(k)] = v
    for k, v in kw.items():
        out[_snake(k)] = v
    return out


def _conc(pen, poly, spacing=1.6):
    return pen.hatch([poly], layer='DETAIL-HATCH', pattern='ANSI31', spacing=spacing)


def section_mesh(o=None, **kw):
    a = _args(o, kw)
    h, cover, dia, lap, spacing = a['h'], a['cover'], a['dia'], a['lap'], a['spacing']
    L = 2600
    y0 = cover + dia / 2

    def draw(pen):
        pen.rect({'x': 0, 'y': 0, 'w': L, 'h': h}, layer='DETAIL', lw=35)
        _conc(pen, rect_polygon({'x': 0, 'y': 0, 'w': L, 'h': h}))
        pen.line({'x': 100, 'y': y0}, {'x': L / 2 + lap / 2, 'y': y0}, layer='REBAR-BOT', lw=70)
        pen.line({'x': L / 2 - lap / 2, 'y': y0 + dia * 1.4}, {'x': L - 100, 'y': y0 + dia * 1.4}, layer='REBAR-BOT', lw=70)
        pen.bar_ends({'x': 100, 'y': y0}, {'x': L / 2 + lap / 2, 'y': y0}, layer='REBAR-BOT')
        pen.bar_ends({'x': L / 2 - lap / 2, 'y': y0 + dia * 1.4}, {'x': L - 100, 'y': y0 + dia * 1.4}, layer='REBAR-BOT')
        # cross bars of the mesh (other direction) as dots
        x = 250
        while x < L:
            pen.circle({'x': x, 'y': y0 + dia * 2.6}, dia / 2, layer='REBAR-BOT')
            x += spacing
        pen.dim({'x': L / 2 - lap / 2, 'y': 0}, {'x': L / 2 + lap / 2, 'y': 0}, -7, text=f"LAP {_n(lap)}")
        pen.dim({'x': 0, 'y': 0}, {'x': 0, 'y': h}, 6, text=f"{_n(h)}")
        pen.dim({'x': L, 'y': 0}, {'x': L, 'y': cover}, -6, text=f"{_n(cover)}")
        pen.text({'x': L / 2, 'y': h + 120}, f"T{_n(dia)}@{_n(spacing)} B.W. BOTTOM MESH - CLASS B LAP, STAGGERED", layer='REBAR-TEXT', h=1.9, align='C')
        pen.text({'x': L / 2, 'y': -420}, 'BOTTOM BARS CONTINUOUS THROUGH COLUMNS, STOPPED AT OPENINGS', layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -250, 'maxX': L + 250, 'minY': -520, 'maxY': h + 420, 'cx': L / 2, 'cy': (h - 100) / 2}, draw)


def section_column(o=None, **kw):
    a = _args(o, kw)
    h, c1, ext, dia, spacing, cover, hook_leg, shape = a['h'], a['c1'], a['ext'], a['dia'], a['spacing'], a['cover'], a['hook_leg'], a.get('shape')
    u_return = a.get('u_return', 0) or 0
    half = c1 / 2 + ext + 350

    def draw(pen):
        pen.rect({'x': -half, 'y': 0, 'w': 2 * half, 'h': h}, layer='DETAIL', lw=35)
        _conc(pen, rect_polygon({'x': -half, 'y': 0, 'w': 2 * half, 'h': h}))
        pen.rect({'x': -c1 / 2, 'y': -900, 'w': c1, 'h': 900}, layer='COLUMN', lw=35)
        _conc(pen, rect_polygon({'x': -c1 / 2, 'y': -900, 'w': c1, 'h': 900}), 2.2)
        yt = h - cover - dia / 2
        xa, xb = -c1 / 2 - ext, c1 / 2 + ext
        pts = []
        yb = cover + dia / 2 + 40  # bottom leg of a U end, just above the bottom mesh
        u_end = u_return > 0 and bool(re.search('U', str(shape)))
        if u_end:
            pts.extend([{'x': xa + u_return, 'y': yb}, {'x': xa, 'y': yb}])
        elif shape != 'STR':
            pts.append({'x': xa, 'y': yt - hook_leg})
        pts.extend([{'x': xa, 'y': yt}, {'x': xb, 'y': yt}])
        if shape == 'UU' and u_end:
            pts.extend([{'x': xb, 'y': yb}, {'x': xb - u_return, 'y': yb}])
        elif shape == 'C':
            pts.append({'x': xb, 'y': yt - hook_leg})
        pen.pline(pts, layer='REBAR-TOP', lw=70)
        if u_end:
            pen.dim({'x': xa, 'y': yb - 60}, {'x': xa + u_return, 'y': yb - 60}, -5, text=f"{_n(u_return)}")
        pen.bar_ends({'x': xa, 'y': yt}, {'x': xb, 'y': yt}, layer='REBAR-TOP')
        # bottom mesh
        pen.line({'x': -half + 60, 'y': cover + 6}, {'x': half - 60, 'y': cover + 6}, layer='REBAR-BOT', lw=35)
        # tendon (schematic)
        pen.pline([{'x': -half, 'y': h / 2 - 40}, {'x': -c1 / 2, 'y': h - cover - 45}, {'x': c1 / 2, 'y': h - cover - 45}, {'x': half, 'y': h / 2 - 40}], layer='PT-TENDON', ltype='DASHED')
        pen.dim({'x': xa, 'y': h}, {'x': -c1 / 2, 'y': h}, 7, text=f"{js_round(ext)} (≥ ln/6)")
        pen.dim({'x': c1 / 2, 'y': h}, {'x': xb, 'y': h}, 7, text=f"{js_round(ext)} (≥ ln/6)")
        pen.dim({'x': -c1 / 2, 'y': h}, {'x': c1 / 2, 'y': h}, 7, text=f"{_n(c1)}")
        pen.dim({'x': half, 'y': 0}, {'x': half, 'y': h}, -6, text=f"{_n(h)}")
        pen.text({'x': 0, 'y': h + 320}, f"T{_n(dia)}@{_n(spacing)} TOP E.W. OVER THE COLUMN - LENGTH PER THE OFFICE RULE (SEE NOTES)" if u_return > 0 else f"T{_n(dia)}@{_n(spacing)} TOP E.W. WITHIN c + 3h - EXTEND ≥ ln/6 FROM FACE OF SUPPORT", layer='REBAR-TEXT', h=1.9, align='C')
        pen.text({'x': 0, 'y': -980}, f"COLUMN  ·  BAR ENDING AT THE SLAB EDGE / AN OPENING ENDS IN A U: DOWN THE SLAB, {_n(u_return)} BACK AT THE BOTTOM" if u_return > 0 else f"COLUMN  ·  90° HOOK {_n(hook_leg)} (12Ø) WHERE BAR ENDS AT SLAB EDGE", layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -half - 200, 'maxX': half + 200, 'minY': -1000, 'maxY': h + 520, 'cx': 0, 'cy': (h - 500) / 2}, draw)


def section_u_edge(o=None, **kw):
    a = _args(o, kw)
    h, cover, leg, dia, edge_dia, spacing = a['h'], a['cover'], a['leg'], a['dia'], a['edge_dia'], a['spacing']
    L = leg + 500

    def draw(pen):
        pen.rect({'x': 0, 'y': 0, 'w': L, 'h': h}, layer='DETAIL', lw=35)
        _conc(pen, rect_polygon({'x': 0, 'y': 0, 'w': L, 'h': h}))
        c = cover + dia / 2
        pen.pline([{'x': leg, 'y': c}, {'x': c, 'y': c}, {'x': c, 'y': h - c}, {'x': leg, 'y': h - c}], layer='REBAR-U', lw=70)
        pen.bar_ends({'x': leg, 'y': c}, {'x': leg, 'y': c}, layer='REBAR-U')
        pen.bar_ends({'x': leg, 'y': h - c}, {'x': leg, 'y': h - c}, layer='REBAR-U')
        # longitudinal edge bars T&B
        for y in [c + dia + 4, h - c - dia - 4]:
            for x in [c + dia + 20, c + dia + 110]:
                pen.circle({'x': x, 'y': y}, edge_dia / 2, layer='REBAR-U')
        # anchorage block at the edge
        pen.rect({'x': 0, 'y': h / 2 - 90, 'w': 260, 'h': 180}, layer='PT-TENDON', lw=35)
        pen.text({'x': 300, 'y': h / 2 - 20}, 'PT ANCHORAGE', layer='PT-TENDON', h=1.5)
        pen.pline([{'x': 260, 'y': h / 2}, {'x': L, 'y': h / 2 - 30}], layer='PT-TENDON', ltype='DASHED')
        pen.dim({'x': 0, 'y': 0}, {'x': leg, 'y': 0}, -7, text=f"LEG {_n(leg)}")
        pen.dim({'x': L, 'y': 0}, {'x': L, 'y': h}, -6, text=f"{_n(h)}")
        pen.dim({'x': 0, 'y': h}, {'x': cover, 'y': h}, 6, text=f"{_n(cover)}")
        pen.text({'x': L / 2, 'y': h + 300}, f"T{_n(dia)}@{_n(spacing)} U-BARS AT SLAB EDGE + 2T{_n(edge_dia)} T&B LONGITUDINAL", layer='REBAR-TEXT', h=1.9, align='C')
        pen.text({'x': L / 2, 'y': -400}, 'BURSTING / SPALLING STEEL AT PT ANCHORAGE ZONE, ALL FREE EDGES', layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -420, 'maxX': L + 150, 'minY': -480, 'maxY': h + 460, 'cx': (L - 300) / 2, 'cy': h / 2}, draw)


def plan_u_circle(o=None, **kw):
    a = _args(o, kw)
    r, cover, leg, spacing, dia, ring_r, ring_dia = a['r'], a['cover'], a['leg'], a['spacing'], a['dia'], a['ring_r'], a['ring_dia']
    R = r + cover + leg + 450

    def draw(pen):
        pen.circle({'x': 0, 'y': 0}, r, layer='OPENING', lw=35)
        pen.hatch([circle_polygon(0, 0, r, 40)], layer='OPENING-HATCH', pattern='ANSI37', spacing=2)
        pen.circle({'x': 0, 'y': 0}, ring_r, layer='REBAR-U', lw=50)
        pen.circle({'x': 0, 'y': 0}, ring_r + 60, layer='REBAR-U', lw=50)
        n = math.ceil((2 * math.pi * (r + cover)) / spacing)
        for i in range(n):
            ang = (i / n) * math.pi * 2
            ca, sa = math.cos(ang), math.sin(ang)
            r0, r1 = r + cover, r + cover + leg
            off = 35
            pen.line({'x': r0 * ca - off * sa, 'y': r0 * sa + off * ca}, {'x': r1 * ca - off * sa, 'y': r1 * sa + off * ca}, layer='REBAR-U', lw=50)
            pen.line({'x': r0 * ca + off * sa, 'y': r0 * sa - off * ca}, {'x': r1 * ca + off * sa, 'y': r1 * sa - off * ca}, layer='REBAR-U', lw=50)
            pen.arc({'x': r0 * ca, 'y': r0 * sa}, off, (ang * 180) / math.pi + 90, (ang * 180) / math.pi + 270, layer='REBAR-U', lw=50)
        pen.dim({'x': 0, 'y': 0}, {'x': r, 'y': 0}, -5, text=f"R {js_round(r)}")
        pen.dim({'x': r + cover, 'y': 0}, {'x': r + cover + leg, 'y': 0}, -5, text=f"{_n(leg)}")
        pen.text({'x': 0, 'y': R - 120}, f"{n}T{_n(dia)}@{_n(spacing)} RADIAL U-BARS (LEGS {_n(leg)}) + {2}T{_n(ring_dia)} RINGS T&B", layer='REBAR-TEXT', h=1.9, align='C')
        pen.text({'x': 0, 'y': -R + 40}, 'U-BARS TOP & BOTTOM LEGS; RINGS LAPPED CLASS B', layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -R, 'maxX': R, 'minY': -R - 250, 'maxY': R + 250, 'cx': 0, 'cy': 0}, draw)


def plan_trimmers(o=None, **kw):
    a = _args(o, kw)
    w, h, ld, count, dia = a['w'], a['h'], a['ld'], a['count'], a['dia']
    diag, diag_dia, diag_l, u_spacing, u_dia, label = a.get('diag'), a.get('diag_dia'), a.get('diag_l'), a.get('u_spacing'), a.get('u_dia'), a.get('label')
    m = ld + 420

    def draw(pen):
        pen.rect({'x': 0, 'y': 0, 'w': w, 'h': h}, layer='OPENING', lw=35)
        pen.line({'x': 0, 'y': 0}, {'x': w, 'y': h}, layer='OPENING')
        pen.line({'x': w, 'y': 0}, {'x': 0, 'y': h}, layer='OPENING')
        pen.text({'x': w / 2, 'y': h / 2 + 60}, label or 'OPENING', layer='OPENING', h=1.8, align='C')
        for k in range(count):
            o_ = 60 + k * 75
            # bottom & top edges
            pen.line({'x': -ld, 'y': -o_}, {'x': w + ld, 'y': -o_}, layer='REBAR-TRIM', lw=60)
            pen.line({'x': -ld, 'y': h + o_}, {'x': w + ld, 'y': h + o_}, layer='REBAR-TRIM', lw=60)
            pen.line({'x': -o_, 'y': -ld}, {'x': -o_, 'y': h + ld}, layer='REBAR-TRIM', lw=60)
            pen.line({'x': w + o_, 'y': -ld}, {'x': w + o_, 'y': h + ld}, layer='REBAR-TRIM', lw=60)
            pen.bar_ends({'x': -ld, 'y': -o_}, {'x': w + ld, 'y': -o_}, layer='REBAR-TRIM')
            pen.bar_ends({'x': -o_, 'y': -ld}, {'x': -o_, 'y': h + ld}, layer='REBAR-TRIM')
        if diag:
            d = diag_l / 2 / math.sqrt(2)
            for cx, cy, sx, sy in [[0, 0, -1, -1], [w, 0, 1, -1], [w, h, 1, 1], [0, h, -1, 1]]:
                c = {'x': cx + sx * 140, 'y': cy + sy * 140}
                for off in [-40, 40]:
                    ox, oy = -sy * off / math.sqrt(2), sx * off / math.sqrt(2)
                    pen.line({'x': c['x'] - sy * d + ox, 'y': c['y'] + sx * d + oy}, {'x': c['x'] + sy * d + ox, 'y': c['y'] - sx * d + oy}, layer='REBAR-TRIM', lw=60)
        if u_spacing:
            x = 100
            while x < w:
                pen.line({'x': x, 'y': 0}, {'x': x, 'y': -300}, layer='REBAR-U')
                pen.line({'x': x, 'y': h}, {'x': x, 'y': h + 300}, layer='REBAR-U')
                x += u_spacing
            y = 100
            while y < h:
                pen.line({'x': 0, 'y': y}, {'x': -300, 'y': y}, layer='REBAR-U')
                pen.line({'x': w, 'y': y}, {'x': w + 300, 'y': y}, layer='REBAR-U')
                y += u_spacing
        pen.dim({'x': -ld, 'y': -m + 250}, {'x': 0, 'y': -m + 250}, 0, text=f"ld {_n(ld)}")
        pen.dim({'x': w, 'y': -m + 250}, {'x': w + ld, 'y': -m + 250}, 0, text=f"ld {_n(ld)}")
        pen.dim({'x': 0, 'y': -m + 250}, {'x': w, 'y': -m + 250}, 0, text='W')
        pen.text({'x': w / 2, 'y': h + m - 60}, f"{_n(count)}T{_n(dia)} T&B EACH SIDE, ANCHORED ld BEYOND CORNERS{f'  +  2T{_n(diag_dia)} DIAG. T&B L={_n(diag_l)}' if diag else ''}{f'  +  T{_n(u_dia)}@{_n(u_spacing)} U-BARS AT FREE EDGES' if u_spacing else ''}", layer='REBAR-TEXT', h=1.8, align='C')

    return Detail({'minX': -m, 'maxX': w + m, 'minY': -m - 350, 'maxY': h + m + 250, 'cx': w / 2, 'cy': h / 2 - 50}, draw)


def section_trimmer(o=None, **kw):
    a = _args(o, kw)
    h, cover, count, dia, u_leg, u_dia, with_u = a['h'], a['cover'], a['count'], a['dia'], a['u_leg'], a.get('u_dia'), a.get('with_u')
    L = max(u_leg + 500, 1400)

    def draw(pen):
        pen.rect({'x': 0, 'y': 0, 'w': L, 'h': h}, layer='DETAIL', lw=35)
        _conc(pen, rect_polygon({'x': 0, 'y': 0, 'w': L, 'h': h}))
        pen.text({'x': -60, 'y': h / 2}, 'OPENING', layer='OPENING', h=1.8, align='R', valign='M')
        c = cover + dia / 2
        for k in range(count):
            x = c + 40 + k * 75
            pen.circle({'x': x, 'y': c + 10}, dia / 2, layer='REBAR-TRIM')
            pen.circle({'x': x, 'y': h - c - 10}, dia / 2, layer='REBAR-TRIM')
        if with_u:
            pen.pline([{'x': u_leg, 'y': c}, {'x': c, 'y': c}, {'x': c, 'y': h - c}, {'x': u_leg, 'y': h - c}], layer='REBAR-U', lw=60)
        pen.line({'x': 300, 'y': c + 30}, {'x': L - 60, 'y': c + 30}, layer='REBAR-BOT', lw=35)
        pen.dim({'x': L, 'y': 0}, {'x': L, 'y': h}, -6, text=f"{_n(h)}")
        if with_u:
            pen.dim({'x': 0, 'y': 0}, {'x': u_leg, 'y': 0}, -7, text=f"LEG {_n(u_leg)}")
        pen.text({'x': L / 2, 'y': h + 200}, f"{_n(count)}T{_n(dia)} TRIMMERS T&B{f' + T{_n(u_dia)} U-BAR' if with_u else ''} - SECTION AT EDGE", layer='REBAR-TEXT', h=1.9, align='C')
        pen.text({'x': L / 2, 'y': -380}, 'TRIMMERS PLACED IN THE SAME LAYER AS THE MAIN MESH', layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -420, 'maxX': L + 150, 'minY': -450, 'maxY': h + 380, 'cx': (L - 300) / 2, 'cy': h / 2}, draw)


def tendon_profile(o=None, **kw):
    a = _args(o, kw)
    span, h = a['span'], a['h']

    def draw(pen):
        pen.rect({'x': 0, 'y': 0, 'w': span, 'h': h}, layer='DETAIL', lw=35)
        for x in [0, span]:
            pen.rect({'x': x - 250, 'y': -700, 'w': 500, 'h': 700}, layer='COLUMN')
        pts = []
        for i in range(21):
            t = i / 20
            x = span * t
            y = h - 60 - (h - 120) * 4 * t * (1 - t)
            pts.append({'x': x, 'y': y})
        pen.pline(pts, layer='PT-TENDON', ltype='DASHED', lw=50)
        for i in range(1, 4):
            pen.dim({'x': (span * i) / 4, 'y': 0}, {'x': (span * i) / 4, 'y': 60 + (h - 120) * 4 * (i / 4) * (1 - i / 4)}, 0, text='____')
        pen.text({'x': span / 2, 'y': h + 250}, 'TYPICAL TENDON PROFILE - HEIGHTS TO BE FILLED AFTER PT DESIGN', layer='CABLE-TEXT', h=1.9, align='C')
        pen.text({'x': span / 2, 'y': -300}, 'DRAPE POINTS AT L/4 - L/2 - 3L/4 (TEMPLATE)', layer='NOTES', h=1.6, align='C')

    return Detail({'minX': -400, 'maxX': span + 400, 'minY': -800, 'maxY': h + 450, 'cx': span / 2, 'cy': (h - 350) / 2}, draw)


def tendon_legend():
    def live_end(pen, x, y):
        pen.line({'x': x, 'y': y}, {'x': x + 600, 'y': y}, layer='CABLE', lw=50)
        pen.solid([{'x': x + 600, 'y': y - 60}, {'x': x + 720, 'y': y}, {'x': x + 600, 'y': y + 60}, {'x': x + 600, 'y': y + 60}], layer='CABLE')

    def dead_end(pen, x, y):
        pen.line({'x': x, 'y': y}, {'x': x + 600, 'y': y}, layer='CABLE', lw=50)
        pen.circle({'x': x + 640, 'y': y}, 50, layer='CABLE', lw=50)

    def intermediate(pen, x, y):
        pen.line({'x': x, 'y': y}, {'x': x + 720, 'y': y}, layer='CABLE', lw=50)
        pen.line({'x': x + 360, 'y': y - 80}, {'x': x + 360, 'y': y + 80}, layer='CABLE', lw=50)

    def group(pen, x, y):
        pen.line({'x': x, 'y': y}, {'x': x + 720, 'y': y}, layer='CABLE', lw=50)
        pen.text({'x': x + 360, 'y': y + 60}, 'n x 15.24', layer='CABLE-TEXT', h=1.6, align='C')

    def added_bar(pen, x, y):
        pen.line({'x': x, 'y': y - 80}, {'x': x + 720, 'y': y - 80}, layer='REBAR-U', lw=50)

    rows = [
        ['LIVE (STRESSING) END', live_end],
        ['DEAD END', dead_end],
        ['INTERMEDIATE STRESSING', intermediate],
        ['TENDON GROUP (n STRANDS)', group],
        ['ADDED BAR AT ANCHOR', added_bar],
    ]

    def draw(pen):
        pen.text({'x': 0, 'y': 60}, 'TENDON SYMBOLS (TO BE USED WHEN THE LAYOUT IS ADDED)', layer='CABLE-TEXT', h=1.8)
        for i, (label, fn) in enumerate(rows):
            y = -180 - i * 260
            fn(pen, 0, y)
            pen.text({'x': 900, 'y': y - 40}, label, layer='NOTES', h=1.7)

    return Detail({'minX': -100, 'maxX': 3400, 'minY': -len(rows) * 260, 'maxY': 250, 'cx': 1650, 'cy': -len(rows) * 130 + 90}, draw)


def notation_legend(o=None, **kw):
    a = _args(o, kw)
    thickness, fc, fy, cover = a['thickness'], a['fc'], a['fy'], a['cover']
    items = [
        ['OUTLINE', 'thick', 'SLAB EDGE / OUTLINE'],
        ['COLUMN', 'hatch', 'COLUMN BELOW'],
        ['OPENING', 'line', 'OPENING (CROSSED)'],
        ['VOID', 'hatch2', 'VOID / ACUAR FORMER ZONE'],
        ['PT-ZONE', 'line', 'PT SLAB ZONE BOUNDARY'],
        ['REBAR-U', 'line', 'U-BAR REGION (CIRCULAR)'],
        ['GRID', 'line', 'GRID LINE'],
    ]

    def draw(pen):
        pen.text({'x': 0, 'y': 60}, f"SLAB {_n(thickness)} mm  ·  f'c {_n(fc)} MPa  ·  fy {_n(fy)} MPa  ·  COVER {_n(cover)} mm", layer='TEXT-TITLE', h=1.8)
        for i, (layer, kind, label) in enumerate(items):
            y = -160 - i * 230
            if kind == 'hatch' or kind == 'hatch2':
                pen.rect({'x': 0, 'y': y - 70, 'w': 600, 'h': 140}, layer=layer)
                pen.hatch([rect_polygon({'x': 0, 'y': y - 70, 'w': 600, 'h': 140})], layer=layer + '-HATCH', pattern='ANSI37' if kind == 'hatch2' else 'ANSI31', spacing=1)
            else:
                pen.line({'x': 0, 'y': y}, {'x': 600, 'y': y}, layer=layer, lw=50 if kind == 'thick' else None)
            pen.text({'x': 760, 'y': y - 50}, label, layer='NOTES', h=1.7)

    return Detail({'minX': -100, 'maxX': 3400, 'minY': -len(items) * 230 - 300, 'maxY': 250, 'cx': 1650, 'cy': -len(items) * 115 - 20}, draw)


def punching_link(o=None, **kw):
    """Punching link (closed C-link) shape with its bending dimensions, reference style."""
    a = _args(o, kw)
    h, cover, dia, row_spacing, leg_spacing, rows = a['h'], a['cover'], a['dia'], a['row_spacing'], a['leg_spacing'], a['rows']
    web = h - 2 * cover

    def draw(pen):
        # link in elevation
        pen.pline([{'x': 0, 'y': 0}, {'x': 110, 'y': 0}, {'x': 110, 'y': -web}, {'x': 0, 'y': -web}], layer='REBAR-PUNCH', lw=70)
        pen.line({'x': 0, 'y': 0}, {'x': 0, 'y': -60}, layer='REBAR-PUNCH', lw=70)
        pen.line({'x': 0, 'y': -web}, {'x': 0, 'y': -web + 60}, layer='REBAR-PUNCH', lw=70)
        pen.dim({'x': 0, 'y': 0}, {'x': 110, 'y': 0}, 4, text='110')
        pen.dim({'x': 110, 'y': 0}, {'x': 110, 'y': -web}, -4, text=_n(web))
        pen.dim({'x': 0, 'y': -web}, {'x': 110, 'y': -web}, -4, text='110')
        pen.text({'x': 55, 'y': 120}, f"T{_n(dia)} LINK", layer='REBAR-TEXT', h=1.8, align='C')
        # plan arrangement beside it
        ox = 600
        pen.rect({'x': ox, 'y': -web - 100, 'w': 300, 'h': web + 100}, layer='COLUMN')
        pen.solid([{'x': ox, 'y': -web - 100}, {'x': ox + 300, 'y': -web - 100}, {'x': ox + 300, 'y': 0}, {'x': ox, 'y': 0}], layer='COLUMN-HATCH')
        for r in range(1, rows + 1):
            x = ox + 300 + r * row_spacing
            pen.line({'x': x, 'y': -web - 100}, {'x': x, 'y': 0}, layer='REBAR-PUNCH')
            yy = -web - 100 + 40
            while yy < 0:
                pen.circle({'x': x, 'y': yy}, 8, layer='REBAR-PUNCH')
                yy += leg_spacing / 2
        pen.dim({'x': ox + 300, 'y': 40}, {'x': ox + 300 + row_spacing, 'y': 40}, 3, text=f"{_n(row_spacing)} (d/2)")
        pen.dim({'x': ox + 300, 'y': -web - 160}, {'x': ox + 300 + rows * row_spacing, 'y': -web - 160}, -3, text=f"{_n(rows)} ROWS")
        pen.text({'x': ox + 150, 'y': -web / 2}, 'COL.', layer='TEXT', h=1.6, align='C', valign='M', color=7)
        pen.text({'x': 400, 'y': -web - 380}, f"LINKS T{_n(dia)}: {_n(rows)} ROWS @ {_n(row_spacing)} FROM FACE, LEGS @ {_n(leg_spacing)} ALONG THE FACE", layer='REBAR-TEXT', h=1.7, align='C')

    return Detail({'minX': -700, 'maxX': 1500, 'minY': -web - 500, 'maxY': 450, 'cx': 400, 'cy': -web / 2}, draw)


def punching_strips(o=None, **kw):
    """
    The office punching detail (PS types): stirrup strips leaving every column face, `legs` legs (legs / 2 closed
    stirrups side by side) in `rows` rows at S from the face. Plan at the column, the strip section (number of legs)
    and the strip elevation (number of rows) with the tag key.
    """
    a = _args(o, kw)
    h, cover, dia, s, rows, legs = a['h'], a['cover'], a['dia'], a['s'], a['rows'], a['legs']
    ns = max(1, legs / 2)
    c1, ln = 700, rows * s
    pitch = c1 / ns
    sw = pitch - 60
    web = h - 2 * cover

    def draw(pen):
        # plan
        pen.solid([{'x': -c1 / 2, 'y': -c1 / 2}, {'x': c1 / 2, 'y': -c1 / 2}, {'x': c1 / 2, 'y': c1 / 2}, {'x': -c1 / 2, 'y': c1 / 2}], layer='COLUMN-HATCH')
        pen.rect({'x': -c1 / 2, 'y': -c1 / 2, 'w': c1, 'h': c1}, layer='COLUMN')
        for dir_ in ['x', 'y']:
            for sg in [-1, 1]:
                i = 0
                while i < ns:
                    t0 = -c1 / 2 + pitch * i + 30
                    face = sg * c1 / 2
                    r = {'x': min(face, face + sg * ln), 'y': t0, 'w': ln, 'h': sw} if dir_ == 'x' else {'x': t0, 'y': min(face, face + sg * ln), 'w': sw, 'h': ln}
                    pen.rect(r, layer='REBAR-PUNCH', lw=35)
                    for k in range(1, rows + 1):
                        o_ = face + sg * k * s
                        if dir_ == 'x':
                            pen.line({'x': o_, 'y': t0}, {'x': o_, 'y': t0 + sw}, layer='DETAIL')
                        else:
                            pen.line({'x': t0, 'y': o_}, {'x': t0 + sw, 'y': o_}, layer='DETAIL')
                    i += 1
        pen.dim({'x': c1 / 2, 'y': -c1 / 2 - 150}, {'x': c1 / 2 + s, 'y': -c1 / 2 - 150}, -3, text=f"S={_n(s)}")
        pen.dim({'x': c1 / 2, 'y': c1 / 2 + 150}, {'x': c1 / 2 + ln, 'y': c1 / 2 + 150}, 3, text=f"{_n(rows)} ROWS")
        pen.text({'x': 0, 'y': -c1 / 2 - ln - 380}, f"PLAN: {_n(rows)}R-{_n(legs)}-T{_n(dia)} EACH SIDE, S={_n(s)}", layer='REBAR-TEXT', h=1.7, align='C')
        # strip section: the closed stirrups side by side (number of legs) - to the right
        ox, oy = c1 / 2 + ln + 350, -c1 / 2 - ln - 100
        pen.rect({'x': ox, 'y': oy, 'w': ns * pitch + 60, 'h': web + 2 * cover}, layer='DETAIL', lw=35)
        i = 0
        while i < ns:
            x0 = ox + 30 + pitch * i + 30
            pen.rect({'x': x0, 'y': oy + cover, 'w': sw, 'h': web}, layer='REBAR-PUNCH', lw=50)
            for xx, yy in [[x0, oy + cover], [x0 + sw, oy + cover], [x0, oy + cover + web], [x0 + sw, oy + cover + web]]:
                pen.circle({'x': xx, 'y': yy}, 12, layer='REBAR-PUNCH')
            i += 1
        pen.text({'x': ox + (ns * pitch + 60) / 2, 'y': oy - 260}, f"SECTION: {_n(legs)} LEGS ({_n(ns)} STIRRUPS T{_n(dia)})", layer='REBAR-TEXT', h=1.6, align='C')
        # strip elevation: the rows - above the section
        ey = oy + web + 2 * cover + 350
        pen.rect({'x': ox, 'y': ey, 'w': ln + 200, 'h': web + 2 * cover}, layer='DETAIL', lw=35)
        for k in range(1, rows + 1):
            pen.line({'x': ox + k * s, 'y': ey + cover}, {'x': ox + k * s, 'y': ey + cover + web}, layer='REBAR-PUNCH', lw=50)
        pen.dim({'x': ox, 'y': ey + web + 2 * cover + 40}, {'x': ox + rows * s, 'y': ey + web + 2 * cover + 40}, 3, text=f"{_n(rows)} ROWS @ S={_n(s)}")
        pen.text({'x': ox + (ln + 200) / 2, 'y': ey - 220}, 'ELEVATION: NO. OF ROWS FROM THE COLUMN FACE', layer='REBAR-TEXT', h=1.6, align='C')

    return Detail({'minX': -c1 / 2 - ln - 350, 'maxX': c1 / 2 + ln + 1500, 'minY': -c1 / 2 - ln - 700, 'maxY': c1 / 2 + ln + 950, 'cx': 500, 'cy': 0}, draw)


def block_beam_section(o=None, **kw):
    """Detail 9: blockwork support beam through the void between two openings - section through the strip."""
    a = _args(o, kw)
    h, cover, width, dia, count, link_dia, link_spacing, ta = a['h'], a['cover'], a['width'], a['dia'], a['count'], a['link_dia'], a['link_spacing'], a['ta']
    w = max(width, 150)

    def draw(pen):
        pen.rect({'x': -w / 2, 'y': 0, 'w': w, 'h': h}, layer='DETAIL', lw=35)
        _conc(pen, rect_polygon({'x': -w / 2, 'y': 0, 'w': w, 'h': h}))
        pen.rect({'x': -w / 2 - 800, 'y': 0, 'w': 800, 'h': h}, layer='DETAIL')
        pen.rect({'x': w / 2, 'y': 0, 'w': 800, 'h': h}, layer='DETAIL')
        pen.text({'x': -w / 2 - 400, 'y': h / 2}, 'VOID', layer='TEXT', h=1.6, align='C', valign='M')
        pen.text({'x': w / 2 + 400, 'y': h / 2}, 'VOID', layer='TEXT', h=1.6, align='C', valign='M')
        # blockwork above
        y = h
        while y < h + 600:
            pen.rect({'x': -w / 2, 'y': y, 'w': w, 'h': 200}, layer='DETAIL')
            y += 200
        pen.text({'x': 0, 'y': h + 700}, 'BLOCKWORK WALL ABOVE', layer='TEXT', h=1.6, align='C')
        # link and bars
        pen.rect({'x': -w / 2 + cover, 'y': cover, 'w': w - 2 * cover, 'h': h - 2 * cover}, layer='REBAR-PUNCH', lw=50)
        xs = [-w / 2 + cover + dia, w / 2 - cover - dia] if count > 1 else [0]
        for x in xs:
            pen.circle({'x': x, 'y': cover + dia}, dia / 2 + 2, layer='REBAR-BOT')
            pen.circle({'x': x, 'y': h - cover - dia}, dia / 2 + 2, layer='REBAR-TOP')
        pen.dim({'x': -w / 2, 'y': -120}, {'x': w / 2, 'y': -120}, -4, text=f"{js_round(width)} (150 MIN.)")
        pen.dim({'x': w / 2 + 850, 'y': 0}, {'x': w / 2 + 850, 'y': h}, -4, text=f"{_n(h)}")
        pen.text({'x': 0, 'y': -520}, f"{_n(count)}T{_n(dia)} TOP & BOTTOM, EXTEND TA = {_n(ta)} BEYOND EACH VOID · T{_n(link_dia)}@{_n(link_spacing)} LINKS", layer='REBAR-TEXT', h=1.7, align='C')

    return Detail({'minX': -w / 2 - 900, 'maxX': w / 2 + 900, 'minY': -700, 'maxY': h + 1100, 'cx': 0, 'cy': h / 2}, draw)


__all__ = [
    'Detail', 'section_mesh', 'section_column', 'section_u_edge', 'plan_u_circle', 'plan_trimmers', 'section_trimmer',
    'tendon_profile', 'tendon_legend', 'notation_legend', 'punching_link', 'punching_strips', 'block_beam_section',
]
