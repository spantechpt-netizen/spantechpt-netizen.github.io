"""
One drawing sheet composed as a block. The sheet frame, title band, notes
and schedule live in "paper millimetres" and are scaled up by the drawing
scale, while the slab plan is placed at true size (1 unit = 1 mm) — the
usual Middle-East convention of a frame scaled around model-space geometry,
so everything on the plan measures correctly in AutoCAD.

The right-hand strip follows the layout of the reference drawings: key
plan, schedule, notes, coordination / contract references, revisions and
the title block with project, client, engineer, contractor and the
shop-drawing author.

Port of `shopdrawings/lib/sheet.mjs`. The pens (`sheet.pp`, the paper pen, and the plan / detail pens made by
`make_pen`) are small objects whose methods take the drawing options as an optional dict and/or snake_case keywords
(`layer=..., closed=True, lw=35, h=2.5, arrow_size=..., text_mid=...`), mapped to the JS entity keys inside.
"""
import math
import re

from .canvas import Canvas, opts as _opts, js_str
from .geometry import fmt_num, js_round
from .svg_writer import wrap

SHEET_SIZES = {'A1': {'w': 841, 'h': 594}, 'A0': {'w': 1189, 'h': 841}, 'A2': {'w': 594, 'h': 420}}
SCALES = [50, 75, 100, 125, 150, 200, 250, 300, 400, 500]
DETAIL_SCALES = [5, 10, 12.5, 15, 20, 25, 30, 40, 50, 75, 100, 150, 200, 250, 300]

# Fixed layout of an A1 sheet in paper mm (origin bottom-left).
# Frame options (`meta.frame`, paper mm): the right-hand strip width and the height of each of its boxes, the
# bottom detail strip, and which boxes are drawn (`keyplan`, `refs`, `schedule`, `details`); a box switched off
# gives its room to the notes. `size` picks A0 / A1 / A2.
DEFAULT_FRAME = {'size': 'A1', 'rightWidth': 185, 'bottomStrip': 125, 'titleH': 150, 'refsH': 52, 'keyH': 46, 'schedH': 140, 'keyplan': True, 'refs': True, 'schedule': True, 'details': False, 'margin': {'left': 20, 'bottom': 10, 'right': 10, 'top': 10}}


def _number(v):
    """JS `Number(v) || 0`: None / a non-numeric string -> 0 (the `||` fallback is applied by the caller)."""
    if v is None or isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).strip() or 0)
    except ValueError:
        return 0


def layout_for(size='A1', frame_opts=None):
    frame_opts = frame_opts or {}
    F = {**DEFAULT_FRAME, **frame_opts, 'margin': {**DEFAULT_FRAME['margin'], **(frame_opts.get('margin') or {})}}
    sz = SHEET_SIZES.get(size) or SHEET_SIZES.get(F.get('size')) or SHEET_SIZES['A1']
    w, h = sz['w'], sz['h']
    right = max(120, _number(F.get('rightWidth')) or 185)
    x0, y0, x1, y1 = F['margin']['left'], F['margin']['bottom'], w - F['margin']['right'], h - F['margin']['top']
    rx = x1 - right
    strip = 0 if F.get('details') is False else max(0, _number(F.get('bottomStrip')) or 125)
    title_h = max(60, _number(F.get('titleH')) or 150)
    refs_h = 0 if F.get('refs') is False else max(0, _number(F.get('refsH')) or 52)
    key_h = 0 if F.get('keyplan') is False else max(0, _number(F.get('keyH')) or 46)
    sched_h = 0 if F.get('schedule') is False else max(0, _number(F.get('schedH')) or 140)
    notes_h = max(40, y1 - y0 - title_h - refs_h - key_h - sched_h)
    plan = {'x': x0, 'y': y0 + strip, 'w': rx - x0, 'h': y1 - y0 - strip}
    return {
        'w': w, 'h': h,
        'frame': {'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0},
        'title': {'x': rx, 'y': y0, 'w': right, 'h': title_h},
        'refs': {'x': rx, 'y': y0 + title_h, 'w': right, 'h': refs_h},
        'notes': {'x': rx, 'y': y0 + title_h + refs_h, 'w': right, 'h': notes_h},
        'schedule': {'x': rx, 'y': y0 + title_h + refs_h + notes_h, 'w': right, 'h': sched_h},
        'keyplan': {'x': rx, 'y': y1 - key_h, 'w': right, 'h': key_h},
        'plan': plan,
        'halves': [{'x': plan['x'], 'y': plan['y'], 'w': plan['w'] / 2, 'h': plan['h']}, {'x': plan['x'] + plan['w'] / 2, 'y': plan['y'], 'w': plan['w'] / 2, 'h': plan['h']}],
        'strip': {'x': x0, 'y': y0, 'w': rx - x0, 'h': strip},
        'details': [{'x': x0 + (i * (rx - x0)) / 3, 'y': y0, 'w': (rx - x0) / 3, 'h': strip} for i in [0, 1, 2]],
        'opts': F,
    }


def choose_scale(bbox_mm, area, margin=12):
    w, h = area['w'] - 2 * margin, area['h'] - 2 * margin - 14  # 14: room for the plan title
    for s in SCALES:
        if bbox_mm['w'] / s <= w and bbox_mm['h'] / s <= h:
            return s
    return SCALES[-1]


def _cx(r):
    return r['x'] + r['w'] / 2


def _cy(r):
    return r['y'] + r['h'] / 2


def _upper(s):
    return str(s).upper()


class PaperPen:
    """The paper pen (`sheet.pp`): coordinates and text heights in paper mm, scaled by S into the sheet block."""

    def __init__(self, sheet):
        self.sheet = sheet

    @property
    def S(self):
        return self.sheet.S

    @property
    def blk(self):
        return self.sheet.blk

    def M(self, p):
        return {'x': p['x'] * self.S, 'y': p['y'] * self.S}

    def line(self, x1, y1, x2, y2, o=None, **kw):
        S = self.S
        return self.blk.line(x1 * S, y1 * S, x2 * S, y2 * S, _opts(o, kw))

    def rect(self, x, y, w, h, o=None, **kw):
        S = self.S
        return self.blk.rect(x * S, y * S, w * S, h * S, _opts(o, kw))

    def pline(self, pts, o=None, **kw):
        return self.blk.pline([self.M(p) for p in pts], _opts(o, kw))

    def circle(self, x, y, r, o=None, **kw):
        S = self.S
        return self.blk.circle(x * S, y * S, r * S, _opts(o, kw))

    def arc(self, x, y, r, a1, a2, o=None, **kw):
        S = self.S
        return self.blk.arc(x * S, y * S, r * S, a1, a2, _opts(o, kw))

    def text(self, x, y, s, o=None, **kw):
        S = self.S
        o = _opts(o, kw)
        return self.blk.text(x * S, y * S, s, {**o, 'h': (o.get('h') or 2.5) * S})

    def mtext(self, x, y, s, o=None, **kw):
        S = self.S
        o = _opts(o, kw)
        return self.blk.mtext(x * S, y * S, s, {**o, 'h': (o.get('h') or 2.5) * S, 'width': (o.get('width') or 0) * S})

    def hatch(self, polys, o=None, **kw):
        S = self.S
        o = _opts(o, kw)
        return self.blk.hatch([[self.M(p) for p in poly] for poly in polys], {**o, 'scale': ((o.get('spacing') or 2) * S) / 3.175})

    def solid(self, pts, o=None, **kw):
        return self.blk.solid([self.M(p) for p in pts], _opts(o, kw))

    def leader(self, pts, o=None, **kw):
        S = self.S
        o = _opts(o, kw)
        return self.blk.leader([self.M(p) for p in pts], {**o, 'arrowSize': (o.get('arrowSize') or 2) * S})

    def dim(self, p1, p2, off, o=None, **kw):
        S = self.S
        o = _opts(o, kw)
        return self.blk.dim(self.M(p1), self.M(p2), off * S, {**o, 'h': (o.get('h') or 2) * S, 'ext': (o.get('ext') or 2) * S, 'tick': (o.get('tick') or 1.2) * S, 'text': o.get('text')})


class Pen:
    """A pen mapping mm geometry through P (scale k) with paper-mm text heights (see Sheet.make_pen)."""

    def __init__(self, P, k, S, blk):
        self.P = P
        self.k = k
        self.S = S
        self.blk = blk
        self.area = None

    def line(self, a, b, o=None, **kw):
        A, B = self.P(a), self.P(b)
        return self.blk.line(A['x'], A['y'], B['x'], B['y'], _opts(o, kw))

    def pline(self, pts, o=None, **kw):
        return self.blk.pline([self.P(p) for p in pts], _opts(o, kw))

    def rect(self, r, o=None, **kw):
        P = self.P
        return self.blk.pline([P(p) for p in [{'x': r['x'], 'y': r['y']}, {'x': r['x'] + r['w'], 'y': r['y']}, {'x': r['x'] + r['w'], 'y': r['y'] + r['h']}, {'x': r['x'], 'y': r['y'] + r['h']}]], {**_opts(o, kw), 'closed': True})

    def circle(self, c, r, o=None, **kw):
        C = self.P(c)
        return self.blk.circle(C['x'], C['y'], r * self.k, _opts(o, kw))

    def arc(self, c, r, a1, a2, o=None, **kw):
        C = self.P(c)
        return self.blk.arc(C['x'], C['y'], r * self.k, a1, a2, _opts(o, kw))

    def text(self, p, s, o=None, **kw):
        Q = self.P(p)
        o = _opts(o, kw)
        return self.blk.text(Q['x'], Q['y'], s, {**o, 'h': (o.get('h') or 2.5) * self.S})

    def mtext(self, p, s, o=None, **kw):
        Q = self.P(p)
        o = _opts(o, kw)
        return self.blk.mtext(Q['x'], Q['y'], s, {**o, 'h': (o.get('h') or 2.5) * self.S, 'width': (o.get('width') or 0) * self.S})

    def hatch(self, polys, o=None, **kw):
        o = _opts(o, kw)
        return self.blk.hatch([[self.P(p) for p in poly] for poly in polys], {**o, 'scale': ((o.get('spacing') or 1.5) * self.S) / 3.175})

    def solid(self, pts, o=None, **kw):
        return self.blk.solid([self.P(p) for p in pts], _opts(o, kw))

    def arrow(self, a, b, o=None, **kw):
        A, B = self.P(a), self.P(b)
        o = _opts(o, kw)
        return self.blk.arrow(A['x'], A['y'], B['x'], B['y'], (o.get('size') or 1.5) * self.S, o)

    def leader(self, pts, o=None, **kw):
        o = _opts(o, kw)
        return self.blk.leader([self.P(p) for p in pts], {**o, 'arrowSize': (o.get('arrowSize') or 1.5) * self.S})

    def dim(self, a, b, off, o=None, **kw):
        o = _opts(o, kw)
        S = self.S
        text = o['text'] if o.get('text') is not None else fmt_num(js_round(math.hypot(b['x'] - a['x'], b['y'] - a['y'])))
        return self.blk.dim(self.P(a), self.P(b), off * S, {**o, 'h': (o.get('h') or 1.8) * S, 'ext': (o.get('ext') or 1.5) * S, 'tick': (o.get('tick') or 1) * S, 'text': text})

    def dimension(self, p1, p2, dl, o=None, **kw):
        """A real DIMENSION entity (see Canvas.dimension); sizes come from the DIMSTYLE in model units."""
        o = _opts(o, kw)
        P = self.P
        return self.blk.dimension(P(p1), P(p2), P(dl), {**o, 'textMid': P(o['textMid']) if o.get('textMid') else None})

    def bubble(self, p, label, o=None, **kw):
        """Circle with a label, at a plan point, offset in paper mm."""
        o = _opts(o, kw)
        S = self.S
        blk = self.blk
        r = (o.get('r') or 3.5) * S
        Q = self.P(p)
        X, Y = Q['x'] + (o.get('dx') or 0) * S, Q['y'] + (o.get('dy') or 0) * S
        blk.circle(X, Y, r, {'layer': o.get('layer') or 'CALLOUT'})
        blk.text(X, Y, label, {'layer': o.get('layer') or 'CALLOUT', 'h': (o.get('h') or 2) * S, 'align': 'C', 'valign': 'M'})
        if o.get('dx') or o.get('dy'):
            d = math.hypot(o.get('dx') or 0, o.get('dy') or 0) * S
            ex, ey = X - ((o.get('dx') or 0) * S * r) / d, Y - ((o.get('dy') or 0) * S * r) / d
            blk.line(ex, ey, Q['x'], Q['y'], {'layer': o.get('layer') or 'CALLOUT'})
        return {'x': X, 'y': Y}

    def bar_ends(self, a, b, o=None, **kw):
        """Short perpendicular ticks at both bar ends (bar extent convention)."""
        o = _opts(o, kw)
        A, B = self.P(a), self.P(b)
        L = math.hypot(B['x'] - A['x'], B['y'] - A['y']) or 1
        nx, ny = -(B['y'] - A['y']) / L, (B['x'] - A['x']) / L
        t = (o.get('size') or 1) * self.S
        self.blk.line(A['x'] - nx * t, A['y'] - ny * t, A['x'] + nx * t, A['y'] + ny * t, o)
        self.blk.line(B['x'] - nx * t, B['y'] - ny * t, B['x'] + nx * t, B['y'] + ny * t, o)


class Sheet:
    def __init__(self, root, block_name=None, size='A1', scale=100, frame=None, **kw):
        # the JS takes one options object { blockName, size, scale, frame }: accept it (or its keys) here too
        o = _opts(None, kw)
        if isinstance(block_name, dict):  # Sheet(root, {'blockName': ..., 'size': ..., 'scale': ..., 'frame': ...})
            o = {**_opts(block_name), **o}
            block_name = None
            size = o.get('size', size)
            scale = o.get('scale', scale)
            frame = o.get('frame', frame)
        block_name = o.get('blockName', block_name)
        frame = frame or {}
        self.root = root
        self.block_name = block_name
        self.blk = root.block(block_name)
        self.S = scale
        self.size = frame.get('size') or size
        self.L = layout_for(self.size, frame)
        # ---- paper pen: coordinates and text heights in paper mm
        self.pp = PaperPen(self)
        self.pl = None

    @property
    def blockName(self):  # noqa: N802  (the JS attribute name, kept for records that read it)
        return self.block_name

    def set_plan(self, bbox_mm, area=None):
        """Place a plan (true-size mm geometry) centred in an area (default: the plan area)."""
        if area is None:
            area = self.L['plan']
        S = self.S
        ox = _cx(area) * S - bbox_mm['cx']
        oy = (_cy(area) + 7) * S - bbox_mm['cy']  # leave room for the plan title below
        pen = self.make_pen(lambda p: {'x': p['x'] + ox, 'y': p['y'] + oy}, 1)
        pen.area = area
        if not self.pl:
            self.pl = pen
        return pen

    def detail_pen(self, box, detail_scale, gb, inner=None):
        """
        Pen for a detail drawn at `detailScale` (e.g. 20 for 1:20) inside a paper
        box: geometry in mm is centred in the box's inner area. Falls back to the
        next standard scale when the nominal one overflows the box.
        """
        if inner is None:
            inner = {'top': 9, 'pad': 6}
        S = self.S
        if box.get('off'):
            scratch = Canvas('_scratch')
            blk = self.blk
            self.blk = scratch
            try:
                return self.make_pen(lambda p: {'x': p['x'], 'y': p['y']}, 1)
            finally:
                self.blk = blk
        ax, ay = box['x'] + inner['pad'], box['y'] + inner['pad']
        aw, ah = box['w'] - 2 * inner['pad'], box['h'] - inner['top'] - 2 * inner['pad']
        gw, gh = (gb['maxX'] - gb['minX']), (gb['maxY'] - gb['minY'])
        need = max(gw / aw, gh / ah)
        scale = detail_scale
        if need > scale:
            scale = next((v for v in DETAIL_SCALES if v >= need), None) or math.ceil(need)
        if box.get('label') and scale != detail_scale and not box.get('nts'):
            box['label']['str'] = f'1:{fmt_num(scale)}'
        k = S / scale
        acx, acy = (ax + aw / 2) * S, (ay + ah / 2) * S

        def P(p):
            return {'x': acx + (p['x'] - gb['cx']) * k, 'y': acy + (p['y'] - gb['cy']) * k}

        return self.make_pen(P, k)

    def make_pen(self, P, k):
        """A pen mapping mm geometry through P (scale k) with paper-mm text heights."""
        return Pen(P, k, self.S, self.blk)

    # ------------------------------------------------------------ sheet furniture
    def frame(self):
        L = self.L
        w, h, frame = L['w'], L['h'], L['frame']
        pp = self.pp
        pp.rect(0, 0, w, h, {'layer': 'FRAME', 'lw': 13})
        pp.rect(frame['x'], frame['y'], frame['w'], frame['h'], {'layer': 'FRAME'})
        for x, y, dx, dy in [[w / 2, 0, 0, 6], [w / 2, h, 0, -6], [0, h / 2, 6, 0], [w, h / 2, -6, 0]]:
            pp.line(x, y, x + dx, y + dy, {'layer': 'FRAME'})
        cols, rows = 8, 6
        for i in range(cols + 1):
            x = frame['x'] + (frame['w'] * i) / cols
            pp.line(x, frame['y'] + frame['h'], x, h, {'layer': 'FRAME', 'lw': 13})
            pp.line(x, 0, x, frame['y'], {'layer': 'FRAME', 'lw': 13})
            if i < cols:
                pp.text(x + frame['w'] / cols / 2, h - 5, str(i + 1), {'layer': 'FRAME', 'h': 2.5, 'align': 'C', 'valign': 'M'})
                pp.text(x + frame['w'] / cols / 2, 5, str(i + 1), {'layer': 'FRAME', 'h': 2.5, 'align': 'C', 'valign': 'M'})
        for j in range(rows + 1):
            y = frame['y'] + (frame['h'] * j) / rows
            pp.line(0, y, frame['x'], y, {'layer': 'FRAME', 'lw': 13})
            pp.line(frame['x'] + frame['w'], y, w, y, {'layer': 'FRAME', 'lw': 13})
            if j < rows:
                pp.text(frame['x'] / 2, y + frame['h'] / rows / 2, 'ABCDEF'[rows - 1 - j], {'layer': 'FRAME', 'h': 2.5, 'align': 'C', 'valign': 'M'})
                pp.text(w - 5, y + frame['h'] / rows / 2, 'ABCDEF'[rows - 1 - j], {'layer': 'FRAME', 'h': 2.5, 'align': 'C', 'valign': 'M'})
        title, refs, notes, schedule, keyplan, plan, strip = L['title'], L['refs'], L['notes'], L['schedule'], L['keyplan'], L['plan'], L['strip']
        pp.line(title['x'], frame['y'], title['x'], frame['y'] + frame['h'], {'layer': 'FRAME'})
        if strip['h']:
            pp.line(plan['x'], strip['y'] + strip['h'], plan['x'] + plan['w'], strip['y'] + strip['h'], {'layer': 'FRAME'})
        for r in [refs, notes, schedule, keyplan]:
            if r['h']:
                pp.line(r['x'], r['y'], r['x'] + r['w'], r['y'], {'layer': 'FRAME'})

    def custom_frame(self, entities, fields=None):
        """
        The office's own frame: the entities of a DXF drawn in paper mm (A1 origin at the bottom-left corner), placed on
        the sheet in place of the built-in frame, references block and title block. `<TOKENS>` in its texts are replaced
        with the sheet's data (PROJECT, PROJECT_CODE, CLIENT, CONSULTANT, CONTRACTOR, LOCATION, COMPANY, COMPANY_LINE,
        TITLE, LEVEL, DRAWING_NO, REV, DATE, SCALE, SHEET, PREPARED, DESIGNER (the engineer who ran the program), CHECKED,
        APPROVED, STATUS, GRID_REF, INDEX).
        """
        fields = fields or {}
        pp = self.pp

        # tokens are written <PROJECT>, %PROJECT% or {PROJECT} (AutoCAD treats braces in MTEXT as formatting, so the first two are safer)
        def sub(s):
            return re.sub(r'[<{%]([A-Z][A-Z_]*)[>}%]', lambda m: js_str(fields[m.group(1)]) if fields.get(m.group(1)) is not None else m.group(0), js_str(s) if s is not None else '')

        n = 0
        for e in entities or []:
            layer = f"FRAME-{e['layer']}" if e.get('layer') and e['layer'] != '0' else 'FRAME'
            t = e.get('type')
            if t == 'LINE':
                pp.line(e['x'], e['y'], e.get('x2'), e.get('y2'), {'layer': layer})
                n += 1
            elif t == 'LWPOLYLINE' and e.get('pts') and len(e['pts']) > 1:
                pp.pline(e['pts'], {'layer': layer, 'closed': bool(e.get('closed'))})
                n += 1
            elif t == 'CIRCLE':
                pp.circle(e['x'], e['y'], e.get('r'), {'layer': layer})
                n += 1
            elif t == 'ARC':
                pp.arc(e['x'], e['y'], e.get('r'), e.get('a1') or 0, e.get('a2') or 360, {'layer': layer})
                n += 1
            elif t == 'SOLID' or t == 'TRACE':
                if e.get('xs') and len(e['xs']) >= 3:
                    pp.solid([{'x': x, 'y': e['ys'][i] if i < len(e['ys']) else None} for i, x in enumerate(e['xs'])], {'layer': layer})
                    n += 1
            elif t == 'TEXT' or t == 'ATTRIB' or t == 'ATTDEF':
                s = sub(e.get('text'))
                if s.strip():
                    halign = e.get('halign')
                    pp.text(e['x'], e['y'], s, {'layer': layer, 'h': e.get('height') or 2.5, 'rot': e.get('rotation') or 0, 'align': 'C' if halign == 1 else 'R' if halign == 2 else 'L', 'widthFactor': e['sx'] if e.get('sx') and e['sx'] < 2 else None})
                    n += 1
            elif t == 'MTEXT':
                s = sub(e.get('text'))
                if s.strip():
                    pp.mtext(e['x'], e['y'], s, {'layer': layer, 'h': e.get('height') or 2.5, 'width': e.get('width') or 0, 'rot': e.get('rotation') or 0})
                    n += 1
        return n

    def key_plan(self, outline, label='KEY PLAN'):
        """Key plan box: the slab outline reduced into the box, with a north arrow."""
        K = self.L['keyplan']
        pp = self.pp
        pp.text(K['x'] + 2, K['y'] + K['h'] - 4.5, label, {'layer': 'TITLE', 'h': 2.2})
        box = {'x': K['x'] + 40, 'y': K['y'] + 3, 'w': K['w'] - 80, 'h': K['h'] - 9}
        pp.rect(box['x'], box['y'], box['w'], box['h'], {'layer': 'TITLE'})
        if outline and len(outline):
            min_x, min_y, max_x, max_y = math.inf, math.inf, -math.inf, -math.inf
            for p in outline:
                min_x = min(min_x, p['x'])
                max_x = max(max_x, p['x'])
                min_y = min(min_y, p['y'])
                max_y = max(max_y, p['y'])
            k = min((box['w'] - 6) / ((max_x - min_x) or 1), (box['h'] - 6) / ((max_y - min_y) or 1))
            pts = [{'x': box['x'] + box['w'] / 2 + (p['x'] - (min_x + max_x) / 2) * k, 'y': box['y'] + box['h'] / 2 + (p['y'] - (min_y + max_y) / 2) * k} for p in outline]
            pp.pline(pts, {'layer': 'OUTLINE', 'closed': True})
            pp.hatch([pts], {'layer': 'HATCH', 'pattern': 'ANSI31', 'spacing': 1.2})
        nx, ny = K['x'] + K['w'] - 20, K['y'] + K['h'] / 2 - 3
        pp.circle(nx, ny, 6, {'layer': 'TEXT'})
        pp.solid([{'x': nx, 'y': ny + 5}, {'x': nx - 2.5, 'y': ny - 3.5}, {'x': nx, 'y': ny - 1.2}, {'x': nx + 2.5, 'y': ny - 3.5}], {'layer': 'TEXT'})
        pp.text(nx, ny + 7.5, 'N', {'layer': 'TEXT', 'h': 2.5, 'align': 'C'})

    def refs_block(self, meta):
        """Coordination, contract references and the revision table."""
        R = self.L['refs']
        pp = self.pp
        x0, w = R['x'], R['w']
        y = R['y'] + R['h']

        def row(h):
            nonlocal y
            y -= h
            pp.line(x0, y, x0 + w, y, {'layer': 'TITLE'})
            return y

        # coordinated with
        top = y
        y = row(5)
        pp.text(x0 + w / 2, top - 2.5, 'COORDINATED WITH THE FOLLOWING DISCIPLINES', {'layer': 'TITLE', 'h': 1.7, 'align': 'C', 'valign': 'M'})
        top = y
        y = row(6)
        coordinated = meta.get('coordinated')
        for i, d in enumerate(['ARCH.', 'STRUCT.', 'MEP', 'EL.']):
            cxp = x0 + (w * i) / 4
            if i:
                pp.line(cxp, y, cxp, top, {'layer': 'TITLE'})
            pp.text(cxp + 1.5, top - 2.2, d, {'layer': 'TITLE', 'h': 1.5})
            pp.text(cxp + w / 8, y + 1, (coordinated[i] if coordinated and i < len(coordinated) and coordinated[i] else None) or '', {'layer': 'TEXT-TITLE', 'h': 1.6, 'align': 'C'})
        # contract drawing references
        top = y
        y = row(5)
        pp.text(x0 + w / 2, top - 2.5, 'CONTRACT DRAWING REFERENCES', {'layer': 'TITLE', 'h': 1.7, 'align': 'C', 'valign': 'M'})
        top = y
        y = row(4)
        for i, d in enumerate(['ARCHITECTURAL', 'STRUCTURAL', 'MEP']):
            cxp = x0 + (w * i) / 3
            if i:
                pp.line(cxp, y, cxp, top, {'layer': 'TITLE'})
            pp.text(cxp + w / 6, top - 2, d, {'layer': 'TITLE', 'h': 1.5, 'align': 'C', 'valign': 'M'})
        top = y
        y = row(4)
        for i in range(3):
            cxp = x0 + (w * i) / 3
            if i:
                pp.line(cxp, y, cxp, top, {'layer': 'TITLE'})
            pp.line(cxp + w / 3 - 12, y, cxp + w / 3 - 12, top, {'layer': 'TITLE'})
            pp.text(cxp + 1.5, top - 2.7, 'DRAWING No.', {'layer': 'TITLE', 'h': 1.3})
            pp.text(cxp + w / 3 - 6, top - 2.7, 'REV.', {'layer': 'TITLE', 'h': 1.3, 'align': 'C'})
        refs_list = meta.get('references') or []
        for r in range(2):
            top = y
            y = row(4)
            for i in range(3):
                cxp = x0 + (w * i) / 3
                if i:
                    pp.line(cxp, y, cxp, top, {'layer': 'TITLE'})
                pp.line(cxp + w / 3 - 12, y, cxp + w / 3 - 12, top, {'layer': 'TITLE'})
                matching = [q for q in refs_list if q.get('discipline') == ['ARCH', 'STRUCT', 'MEP'][i]]
                ref = matching[r] if r < len(matching) else None
                if ref:
                    pp.text(cxp + 1.5, y + 1, ref.get('no'), {'layer': 'TEXT-TITLE', 'h': 1.4})
                    pp.text(cxp + w / 3 - 6, y + 1, ref.get('rev') or '', {'layer': 'TEXT-TITLE', 'h': 1.4, 'align': 'C'})
        # revisions
        top = y
        y = row(4)
        cols = [[0, 'REV.', 12], [12, 'DESCRIPTION', 118], [130, 'DATE', 30], [160, 'BY', 25]]
        for ox, label, cw in cols:
            if ox:
                pp.line(x0 + ox, y, x0 + ox, top, {'layer': 'TITLE'})
            pp.text(x0 + ox + cw / 2, top - 2, label, {'layer': 'TITLE', 'h': 1.4, 'align': 'C', 'valign': 'M'})
        revs = meta['revisions'] if meta.get('revisions') and len(meta['revisions']) else [{'rev': meta.get('revision') or '00', 'description': meta.get('issued') or 'ISSUED FOR APPROVAL', 'date': meta.get('date') or '', 'by': meta.get('preparedInitials') or ''}]
        rows_left = math.floor((y - R['y']) / 4)
        for r in range(rows_left):
            top = y
            y = row(4)
            rv = revs[r] if r < len(revs) else None
            for ox, _label, cw in cols:
                if ox:
                    pp.line(x0 + ox, y, x0 + ox, top, {'layer': 'TITLE'})
                if not rv:
                    continue
                idx = next(i for i, c in enumerate(cols) if c[0] == ox)
                v = [rv.get('rev'), rv.get('description'), rv.get('date'), rv.get('by')][idx] or ''
                pp.text(x0 + ox + (1.5 if ox == 12 else cw / 2), y + 1, v, {'layer': 'TEXT-TITLE', 'h': 1.5, 'align': 'L' if ox == 12 else 'C'})

    def title_block(self, meta):
        """Title block: project / client / engineer / contractor / author / title / numbers / signatures."""
        T = self.L['title']
        pp = self.pp
        x0, w = T['x'], T['w']
        y = T['y'] + T['h']

        def row(h):
            nonlocal y
            y -= h
            pp.line(x0, y, x0 + w, y, {'layer': 'TITLE'})
            return y

        def label(x, yy, s):
            return pp.text(x + 1.5, yy - 3, s, {'layer': 'TITLE', 'h': 1.5})

        def value(x, yy, s, h=2.6, o=None):
            return pp.text(x + 1.5, yy - 3 - h - 1, s, {'layer': 'TEXT-TITLE', 'h': h, **(o or {})})

        def vline(x, y1, y2):
            return pp.line(x, y1, x, y2, {'layer': 'TITLE'})

        def box(h, lab, val, vh=2.6, second=None):
            nonlocal y
            top = y
            y = row(h)
            label(x0, top, lab)
            if val:
                value(x0, top, val, vh)
            if second:
                pp.text(x0 + 1.5, y + 1.3, second, {'layer': 'TITLE', 'h': 1.7})

        if True:
            top = y
            y = row(15)
            label(x0, top, 'PROJECT')
            lines = wrap(_upper(meta.get('project') or ''), 62)[:2]
            for i, ln in enumerate(lines):
                pp.text(x0 + 1.5, top - 6.2 - i * 3, ln, {'layer': 'TEXT-TITLE', 'h': 2.1})
            pp.text(x0 + 1.5, y + 1.3, '   '.join(s for s in [_upper(meta['location']) if meta.get('location') else '', f"PROJECT CODE: {js_str(meta['projectCode'])}" if meta.get('projectCode') else ''] if s), {'layer': 'TITLE', 'h': 1.7})
        box(9, 'THE CLIENT', meta.get('client') or '', 2.2)
        box(9, 'THE ENGINEER (CONSULTANT)', meta.get('engineer') or '', 2.2)
        box(9, 'MAIN CONTRACTOR', meta.get('contractor') or '', 2.2)
        # shop drawing author (company)
        top = y
        y = row(16)
        label(x0, top, 'POST-TENSION SUB-CONTRACTOR / SHOP DRAWINGS BY')
        pp.text(x0 + w / 2, top - 8.5, _upper(meta.get('company') or 'SPAN TECH CONTRACTING'), {'layer': 'TEXT-TITLE', 'h': 4, 'align': 'C', 'valign': 'M', 'bold': True})
        pp.text(x0 + w / 2, top - 13.5, meta.get('company_line') or 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR', {'layer': 'TITLE', 'h': 1.7, 'align': 'C', 'valign': 'M'})
        # title
        top = y
        y = row(20)
        label(x0, top, 'DRAWING TITLE')
        title_lines = wrap(' - '.join(js_str(s) for s in [meta.get('titlePrefix'), meta.get('title')] if s), 40)[:3]
        for i, ln in enumerate(title_lines):
            pp.text(x0 + 1.5, top - 7.5 - i * 3.9, ln, {'layer': 'TEXT-TITLE', 'h': 2.9, 'bold': True})
        if meta.get('level'):
            pp.text(x0 + 1.5, y + 1.3, meta['level'], {'layer': 'TITLE', 'h': 2})
        # drawing no / rev / date
        top = y
        y = row(11)
        c3 = [x0, x0 + w * 0.5, x0 + w * 0.72]
        vline(c3[1], y, top)
        vline(c3[2], y, top)
        label(c3[0], top, 'DRAWING No.')
        value(c3[0], top, meta.get('drawingNo') or '', 3.2)
        label(c3[1], top, 'REV.')
        value(c3[1], top, meta.get('revision') or '00', 3.2)
        label(c3[2], top, 'DATE')
        value(c3[2], top, meta.get('date') or '', 2.4)
        # scale / sheet / grid ref
        top = y
        y = row(11)
        c3b = [x0, x0 + w * 0.4, x0 + w * 0.66]
        vline(c3b[1], y, top)
        vline(c3b[2], y, top)
        label(c3b[0], top, 'SCALE (A1)')
        value(c3b[0], top, meta.get('scale') or f'1:{fmt_num(self.S)}', 2.4)
        label(c3b[1], top, 'SHEET')
        value(c3b[1], top, meta.get('sheet') or '', 2.4)
        label(c3b[2], top, 'GRID REFERENCE')
        value(c3b[2], top, meta.get('gridRef') or '', 2.2)
        # signatures
        top = y
        y = row(15)
        c3c = [x0, x0 + w / 3, x0 + (2 * w) / 3]
        vline(c3c[1], y, top)
        vline(c3c[2], y, top)
        # PREPARED carries the engineer who ran the program (meta.designer) - the office name only when no one is logged in
        for i, (k, v) in enumerate([['PREPARED / DESIGNED BY', meta.get('designer') or meta.get('prepared')], ['CHECKED', meta.get('checked')], ['APPROVED', meta.get('approved')]]):
            label(c3c[i], top, k)
            pp.text(c3c[i] + 1.5, top - 7.5, _upper(v or ''), {'layer': 'TEXT-TITLE', 'h': 1.6 if v and len(js_str(v)) > 22 else 2})
            pp.text(c3c[i] + 1.5, y + 1.3, 'SIGN / DATE: ..........', {'layer': 'TITLE', 'h': 1.4})
        # index / code / block
        top = y
        y = row(10)
        c3d = [x0, x0 + w * 0.3, x0 + w * 0.62]
        vline(c3d[1], y, top)
        vline(c3d[2], y, top)
        label(c3d[0], top, 'DRAWING INDEX')
        value(c3d[0], top, meta.get('index') or '', 2)
        label(c3d[1], top, 'CODE REFERENCE')
        value(c3d[1], top, meta.get('codeRef') or '', 1.8)
        label(c3d[2], top, 'BLOCK / XREF')
        value(c3d[2], top, self.block_name, 1.4)
        # status fills the rest
        rest = y - T['y']
        pp.text(x0 + w / 2, T['y'] + rest / 2, meta.get('status') or 'SHOP DRAWING - FOR CONSULTANT APPROVAL', {'layer': 'TEXT-TITLE', 'h': 2.3, 'align': 'C', 'valign': 'M', 'bold': True})
        pp.rect(T['x'], T['y'], T['w'], T['h'], {'layer': 'TITLE', 'lw': 50})

    def notes(self, o=None, general=None, assumptions=None, code_ref=None, legend=None, extra=None, **kw):
        """Notes column: general notes, assumptions, code reference, legend."""
        o = _opts(o, kw)
        general = o.get('general', general) or []
        assumptions = o.get('assumptions', assumptions) or []
        code_ref = o.get('codeRef', code_ref)
        code_ref = '' if code_ref is None else code_ref
        legend = o.get('legend', legend) or []
        extra = o.get('extra', extra) or []
        N = self.L['notes']
        pp = self.pp
        x = N['x'] + 3
        y = N['y'] + N['h'] - 3

        def head(en, ar):
            nonlocal y
            y -= 3.2
            pp.text(x, y, en, {'layer': 'TEXT-TITLE', 'h': 2.4, 'bold': True})
            if ar:
                pp.text(N['x'] + N['w'] - 3, y, ar, {'layer': 'TEXT-TITLE', 'h': 2.2, 'align': 'R'})
            y -= 1.1
            pp.line(x, y, N['x'] + N['w'] - 3, y, {'layer': 'NOTES'})
            y -= 1.3

        def para(s, h=1.75):
            nonlocal y
            lines = wrap(s, math.floor((N['w'] - 8) / (h * 0.78)))
            y -= h
            pp.mtext(x, y + h, s, {'layer': 'NOTES', 'h': h, 'width': N['w'] - 7})
            y -= (len(lines) - 1) * h * 1.55 + 1.3

        head('GENERAL NOTES', 'ملاحظات عامة')
        for i, g in enumerate(general):
            para(f'{i + 1}. {js_str(g)}')
        if len(assumptions):
            head('ASSUMPTIONS', 'افتراضات')
            for i, g in enumerate(assumptions):
                para(f'A{i + 1}. {js_str(g)}', 1.65)
        head('CODE REFERENCE', 'المرجع الكودي')
        para(code_ref, 1.75)
        for e in extra:
            head(e.get('title'), e.get('ar'))
            for ln in e.get('lines') or []:
                para(ln, 1.65)
        if len(legend):
            head('LEGEND', 'مفتاح الرموز')
            for layer, text, kind in legend:
                y -= 2.2
                if kind == 'hatch':
                    pp.hatch([[{'x': x, 'y': y - 0.8}, {'x': x + 8, 'y': y - 0.8}, {'x': x + 8, 'y': y + 1.8}, {'x': x, 'y': y + 1.8}]], {'layer': layer, 'spacing': 1})
                elif kind == 'solid':
                    pp.solid([{'x': x, 'y': y - 0.8}, {'x': x + 8, 'y': y - 0.8}, {'x': x + 8, 'y': y + 1.8}, {'x': x, 'y': y + 1.8}], {'layer': layer})
                else:
                    pp.line(x, y + 0.5, x + 8, y + 0.5, {'layer': layer, 'lw': 50 if kind == 'thick' else None})
                pp.text(x + 10, y, text, {'layer': 'NOTES', 'h': 1.7})
                y -= 0.8
        return y

    def table(self, x, y_top, cols, rows, o=None, title=None, row_h=4, h=1.7, head_h=5, title_h=6, max_rows=None, layer='SCHEDULE', text_layer='SCHEDULE-TEXT', totals=None, **kw):
        """Generic table. cols: [{ key, title, w, align }] ; rows: objects."""
        o = _opts(o, kw)
        title = o.get('title', title)
        row_h = o['rowH'] if o.get('rowH') is not None else row_h
        h = o['h'] if o.get('h') is not None else h
        head_h = o['headH'] if o.get('headH') is not None else head_h
        title_h = o['titleH'] if o.get('titleH') is not None else title_h
        max_rows = o['maxRows'] if o.get('maxRows') is not None else max_rows
        layer = o['layer'] if o.get('layer') is not None else layer
        text_layer = o['textLayer'] if o.get('textLayer') is not None else text_layer
        totals = o.get('totals', totals)
        L = self.L
        # a table meant for a detail box while the bottom strip is off is not drawn
        if not (L['strip']['h'] > 0) and x < L['strip']['x'] + L['strip']['w'] and y_top <= L['strip']['y'] + 1:
            return {'y': y_top, 'leftover': []}
        pp = self.pp
        W = sum(c['w'] for c in cols)
        y = y_top
        if title:
            pp.rect(x, y - title_h, W, title_h, {'layer': layer})
            pp.text(x + W / 2, y - title_h / 2, title, {'layer': 'TEXT-TITLE', 'h': 2.6, 'align': 'C', 'valign': 'M', 'bold': True})
            y -= title_h
        pp.rect(x, y - head_h, W, head_h, {'layer': layer})
        cx0 = x
        for c in cols:
            lines = js_str(c.get('title')).split('\n')
            for i, ln in enumerate(lines):
                pp.text(cx0 + c['w'] / 2, y - head_h / 2 + ((len(lines) - 1) / 2 - i) * (h + 0.4), ln, {'layer': text_layer, 'h': h - 0.1, 'align': 'C', 'valign': 'M', 'bold': True})
            cx0 += c['w']
        y -= head_h
        if max_rows is None or (isinstance(max_rows, float) and math.isinf(max_rows)):
            shown, leftover = rows[:], []
        else:
            shown, leftover = rows[:max_rows], rows[max_rows:]
        for r in shown:
            cx0 = x
            for c in cols:
                v = '' if r.get(c.get('key')) is None else js_str(r[c['key']])
                ax = cx0 + 1 if c.get('align') == 'L' else cx0 + c['w'] - 1 if c.get('align') == 'R' else cx0 + c['w'] / 2
                mx = c.get('max')
                pp.text(ax, y - row_h / 2, v[:mx - 1] + '…' if mx is not None and len(v) > mx else v, {'layer': text_layer, 'h': h, 'align': c.get('align') or 'C', 'valign': 'M'})
                cx0 += c['w']
            y -= row_h
            pp.line(x, y, x + W, y, {'layer': layer, 'lw': 5})
        if totals and not len(leftover):
            pp.rect(x, y - row_h - 0.5, W, row_h + 0.5, {'layer': layer})
            pp.text(x + 2, y - (row_h + 0.5) / 2, totals, {'layer': text_layer, 'h': h, 'valign': 'M', 'bold': True})
            y -= row_h + 0.5
        cx0 = x
        top = y_top - (title_h if title else 0)
        for c in cols:
            pp.line(cx0, top, cx0, y, {'layer': layer})
            cx0 += c['w']
        pp.line(x + W, top, x + W, y, {'layer': layer})
        pp.line(x, y, x + W, y, {'layer': layer})
        return {'y': y, 'leftover': leftover}

    def detail_box(self, i, title, scale_label=None):
        """Box for a detail in the bottom strip, with title strip and scale."""
        # the office keeps the bottom strip off (the plan takes the whole width): a detail asked for then goes nowhere -
        # a box that is off, whose pen draws into a scratch canvas and whose tables are skipped
        if not (self.L['strip']['h'] > 0):
            return {'x': 0, 'y': 0, 'w': 0, 'h': 0, 'off': True, 'label': None, 'nts': True}
        d = self.L['details'][i]
        pp = self.pp
        pp.rect(d['x'], d['y'], d['w'], d['h'], {'layer': 'FRAME'})
        pp.line(d['x'], d['y'] + d['h'] - 8, d['x'] + d['w'], d['y'] + d['h'] - 8, {'layer': 'FRAME'})
        pp.circle(d['x'] + 7, d['y'] + d['h'] - 4, 3, {'layer': 'CALLOUT'})
        pp.text(d['x'] + 7, d['y'] + d['h'] - 4, str(i + 1), {'layer': 'CALLOUT', 'h': 2.2, 'align': 'C', 'valign': 'M'})
        pp.text(d['x'] + 12, d['y'] + d['h'] - 4, title, {'layer': 'TEXT-TITLE', 'h': 2.4, 'valign': 'M', 'bold': True})
        d['label'] = pp.text(d['x'] + d['w'] - 2, d['y'] + d['h'] - 4, scale_label or '', {'layer': 'TITLE', 'h': 1.8, 'align': 'R', 'valign': 'M'})
        d['nts'] = (not scale_label) or bool(re.search(r'N\.T\.S', js_str(scale_label)))
        return d

    def plan_title_at(self, area, n, title, scale_label):
        """Plan title in the reference style: circled number, underlined title, scale below."""
        pp = self.pp
        x, y = area['x'] + 10, area['y'] + 6
        pp.circle(x + 4, y + 1.2, 4, {'layer': 'CALLOUT'})
        pp.text(x + 4, y + 1.2, js_str(n), {'layer': 'CALLOUT', 'h': 3.2, 'align': 'C', 'valign': 'M'})
        pp.text(x + 11, y, title, {'layer': 'TEXT-TITLE', 'h': 3.4, 'bold': True})
        pp.line(x + 11, y - 1.2, x + 11 + len(js_str(title)) * 2.6, y - 1.2, {'layer': 'TITLE', 'lw': 35})
        pp.text(x + 11, y - 4.2, scale_label, {'layer': 'TITLE', 'h': 2})

    def plan_title(self, title, scale_label):
        self.plan_title_at(self.L['plan'], 1, title, scale_label)

    def stamp(self, text, sub=None):
        """Status stamp in a box (used for the cable template)."""
        P = self.L['plan']
        w, h = 150, 22
        x, y = P['x'] + P['w'] - w - 8, P['y'] + P['h'] - h - 8
        self.pp.rect(x, y, w, h, {'layer': 'CALLOUT', 'lw': 50})
        self.pp.text(x + w / 2, y + h - 7, text, {'layer': 'CALLOUT', 'h': 4, 'align': 'C', 'valign': 'M', 'bold': True})
        if sub:
            self.pp.text(x + w / 2, y + 6, sub, {'layer': 'CALLOUT', 'h': 2.2, 'align': 'C', 'valign': 'M'})
