"""
A tiny drawing model shared by the DXF writer and the SVG preview.

A Canvas is a list of entities on named layers plus a registry of blocks
(which are canvases themselves). Sheets are composed as blocks, so every
sheet can be inserted, exploded or attached as an Xref inside AutoCAD.

Port of `shopdrawings/lib/canvas.mjs`. Entities are dicts with the JS keys verbatim (camelCase: `widthFactor`,
`textMid`, `lineSpacing`, `arrowSize` ...); the Python methods take the options as an optional dict `o` and/or
snake_case keyword arguments (`width_factor=`, `text_mid=`, `style_def=`, `arrow_size=`, `line_spacing=`), which are
mapped to the JS keys inside.
"""
import math
import re

from .geometry import js_round, fmt_num, js_hypot

# ACI colour index and linetype per standard layer.
STANDARD_LAYERS = {
    '0': {'color': 7, 'ltype': 'CONTINUOUS'},
    'FRAME': {'color': 7, 'ltype': 'CONTINUOUS', 'lw': 50},
    'TITLE': {'color': 7, 'ltype': 'CONTINUOUS', 'lw': 25},
    'TEXT': {'color': 7, 'ltype': 'CONTINUOUS'},
    'TEXT-TITLE': {'color': 2, 'ltype': 'CONTINUOUS'},
    'NOTES': {'color': 7, 'ltype': 'CONTINUOUS'},
    'GRID': {'color': 8, 'ltype': 'CENTER'},
    'GRID-BUBBLE': {'color': 8, 'ltype': 'CONTINUOUS'},
    'OUTLINE': {'color': 4, 'ltype': 'CONTINUOUS', 'lw': 35},
    'COLUMN': {'color': 5, 'ltype': 'CONTINUOUS', 'lw': 35},
    'COLUMN-HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'OPENING': {'color': 6, 'ltype': 'CONTINUOUS'},
    'OPENING-HATCH': {'color': 6, 'ltype': 'CONTINUOUS'},
    'VOID': {'color': 30, 'ltype': 'DASHED'},
    'VOID-HATCH': {'color': 30, 'ltype': 'CONTINUOUS'},
    'PT-ZONE': {'color': 4, 'ltype': 'DASHDOT'},
    'PT-TENDON': {'color': 3, 'ltype': 'CONTINUOUS'},
    'PT-HATCH': {'color': 4, 'ltype': 'CONTINUOUS'},
    'REBAR-BOT': {'color': 1, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REBAR-TOP': {'color': 5, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REBAR-U': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REBAR-TRIM': {'color': 2, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REBAR-EXTENT': {'color': 1, 'ltype': 'CONTINUOUS'},
    'REBAR-TEXT': {'color': 7, 'ltype': 'CONTINUOUS'},
    'REBAR-MESH': {'color': 4, 'ltype': 'CONTINUOUS'},
    'REBAR-PUNCH': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 20},
    'REBAR-RED': {'color': 1, 'ltype': 'CONTINUOUS'},
    'REBAR': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 50},
    'REBAR-B1': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 50},
    'REBAR-B2': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 50},
    'REBAR-T1': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 50},
    'REBAR-T2': {'color': 6, 'ltype': 'CONTINUOUS', 'lw': 50},
    'STAIR': {'color': 8, 'ltype': 'CONTINUOUS'},
    'WALL': {'color': 8, 'ltype': 'CONTINUOUS', 'lw': 50},
    'WALL-HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'POUR-STRIP': {'color': 30, 'ltype': 'DASHED'},
    'POUR-STRIP-HATCH': {'color': 30, 'ltype': 'CONTINUOUS'},
    'LEVEL': {'color': 4, 'ltype': 'CONTINUOUS'},
    'SLAB-THK': {'color': 3, 'ltype': 'DASHED'},
    'SLAB-THK-HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'CABLE-LIVE': {'color': 3, 'ltype': 'CONTINUOUS'},
    'CABLE-HL': {'color': 1, 'ltype': 'CONTINUOUS'},
    'CABLE-CHAIR': {'color': 6, 'ltype': 'CONTINUOUS'},
    # the office's cable shop-drawing layers (Auto PT Suite convention): one set per tendon direction
    'Tendons-A': {'color': 4, 'ltype': 'CONTINUOUS', 'lw': 35}, 'Tendons-B': {'color': 4, 'ltype': 'CONTINUOUS', 'lw': 35},
    'Text-Profile-A': {'color': 2, 'ltype': 'CONTINUOUS'}, 'Text-Profile-B': {'color': 2, 'ltype': 'CONTINUOUS'},
    'Text-Profile-A-HIGH': {'color': 2, 'ltype': 'CONTINUOUS'}, 'Text-Profile-B-HIGH': {'color': 2, 'ltype': 'CONTINUOUS'},
    'Text-Profile-A-LOW': {'color': 4, 'ltype': 'CONTINUOUS'}, 'Text-Profile-B-LOW': {'color': 4, 'ltype': 'CONTINUOUS'},
    'Hline-Profile-A': {'color': 8, 'ltype': 'CONTINUOUS'}, 'Hline-Profile-B': {'color': 8, 'ltype': 'CONTINUOUS'},
    'Hline-Profile-A-HIGH': {'color': 2, 'ltype': 'CONTINUOUS'}, 'Hline-Profile-B-HIGH': {'color': 2, 'ltype': 'CONTINUOUS'},
    'Hline-Profile-A-LOW': {'color': 4, 'ltype': 'CONTINUOUS'}, 'Hline-Profile-B-LOW': {'color': 4, 'ltype': 'CONTINUOUS'},
    'PT-HighLow-A': {'color': 6, 'ltype': 'CONTINUOUS'}, 'PT-HighLow-B': {'color': 6, 'ltype': 'CONTINUOUS'},
    'Dimensions-Profile-A': {'color': 1, 'ltype': 'CONTINUOUS'}, 'Dimensions-Profile-B': {'color': 1, 'ltype': 'CONTINUOUS'},
    'Dimensions-Sec-A': {'color': 1, 'ltype': 'CONTINUOUS'}, 'Dimensions-Sec-B': {'color': 1, 'ltype': 'CONTINUOUS'},
    'Details-A': {'color': 4, 'ltype': 'CONTINUOUS'}, 'Details-B': {'color': 4, 'ltype': 'CONTINUOUS'},
    'PT-Notes': {'color': 7, 'ltype': 'CONTINUOUS'},
    'PT-Cross-A': {'color': 4, 'ltype': 'CONTINUOUS', 'lw': 35}, 'PT-Cross-B': {'color': 5, 'ltype': 'CONTINUOUS', 'lw': 35}, 'PT-Cross-Gap': {'color': 8, 'ltype': 'CONTINUOUS'}, 'PT-Cross-Tight': {'color': 2, 'ltype': 'CONTINUOUS'}, 'PT-Cross-Clash': {'color': 1, 'ltype': 'CONTINUOUS'}, 'PT-Cross-Mark': {'color': 3, 'ltype': 'CONTINUOUS'}, 'PT-Cross-Text': {'color': 2, 'ltype': 'CONTINUOUS'},
    'BEAM': {'color': 3, 'ltype': 'CONTINUOUS', 'lw': 25},
    'SUNKEN': {'color': 4, 'ltype': 'CONTINUOUS'},
    'SUNKEN-HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'CALLOUT': {'color': 3, 'ltype': 'CONTINUOUS'},
    'DIM': {'color': 8, 'ltype': 'CONTINUOUS'},
    'DETAIL': {'color': 7, 'ltype': 'CONTINUOUS'},
    'DETAIL-HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'SCHEDULE': {'color': 7, 'ltype': 'CONTINUOUS'},
    'SCHEDULE-TEXT': {'color': 7, 'ltype': 'CONTINUOUS'},
    'HATCH': {'color': 8, 'ltype': 'CONTINUOUS'},
    'CABLE': {'color': 3, 'ltype': 'CONTINUOUS', 'lw': 50},
    'CABLE-TEXT': {'color': 3, 'ltype': 'CONTINUOUS'},
    'XREF': {'color': 7, 'ltype': 'CONTINUOUS'},
}

# DIMSTYLE defaults in model units (a 1:100 architectural style: 250 text, 150 oblique ticks).
DEFAULT_DIMSTYLE = {'txt': 250, 'asz': 150, 'tsz': 150, 'exo': 50, 'exe': 100, 'gap': 70, 'tad': 1, 'clrt': 3, 'clrd': 256, 'clre': 256, 'dec': 0, 'txsty': 'STANDARD', 'scale': 1}

LINETYPES = {
    'CONTINUOUS': {'desc': 'Solid line', 'pattern': []},
    'DASHED': {'desc': 'Dashed __ __ __', 'pattern': [12.7, -6.35]},
    'HIDDEN': {'desc': 'Hidden __ __ __', 'pattern': [6.35, -3.175]},
    'CENTER': {'desc': 'Center ____ _ ____ _', 'pattern': [31.75, -6.35, 6.35, -6.35]},
    'DASHDOT': {'desc': 'Dash dot __ . __ . __', 'pattern': [12.7, -6.35, 0, -6.35]},
    'PHANTOM': {'desc': 'Phantom ____ _ _ ____', 'pattern': [31.75, -6.35, 6.35, -6.35, 6.35, -6.35]},
}


def js_key(k):
    """A snake_case Python keyword to the JS (camelCase) option key: width_factor -> widthFactor."""
    return re.sub(r'_([a-z0-9])', lambda m: m.group(1).upper(), k)


def opts(o=None, kw=None):
    """Merge an options dict (JS keys or snake_case) and keyword arguments into one dict with the JS keys."""
    out = {}
    for src in (o, kw):
        if src:
            for k, v in src.items():
                out[js_key(k)] = v
    return out


def js_str(v):
    """JS `String(v)`: numbers through fmt_num, everything else through str()."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return fmt_num(v)
    if v is None:
        return 'undefined'
    return str(v)


def _pt(p):
    return {'x': p['x'], 'y': p['y']}


class Canvas:
    def __init__(self, name='*Model_Space', root=None):
        self.name = name
        self.entities = []
        self.root = root or self
        self.anonymous = False
        if not root:
            self.blocks = {}
            self.layers = {k: dict(v) for k, v in STANDARD_LAYERS.items()}
            self.text_style = {'name': 'STANDARD', 'font': 'arial.ttf'}
            self.text_styles = {'STANDARD': {'font': 'arial.ttf'}}
            self.dim_styles = {}
            self.dim_count = 0
            self.groups = []  # the JS creates it lazily on the first group(); an empty list reads the same

    def dim_style_def(self, name, d):
        """Register a dimension style (DXF DIMSTYLE record) usable as `style` on dimension entities."""
        self.root.dim_styles[name] = {**DEFAULT_DIMSTYLE, **d}
        return name

    def text_style_def(self, name, d):
        """Register a text style (DXF STYLE table entry) usable as `style` on text entities."""
        self.root.text_styles[name] = d
        return name

    def apply_layer_standard(self, map_):
        """
        Apply a layer standard: rename every layer (in the table, in entities and
        in blocks) and take colour / linetype / lineweight from the standard.
        `map` is { internalName: { name, color?, ltype?, lw? } }.
        """
        root = self.root

        def rename(canvas):
            for e in canvas.entities:
                if map_.get(e.get('layer')):
                    e['layer'] = map_[e['layer']]['name']

        rename(root)
        for blk in root.blocks.values():
            rename(blk)
        nxt = {}
        for name, d in root.layers.items():
            m = map_.get(name)
            if not m:
                nxt[name] = d
                continue
            merged = {**d, **({'color': m['color']} if m.get('color') is not None else {}),
                      **({'ltype': m['ltype']} if m.get('ltype') else {}),
                      **({'lw': m['lw']} if m.get('lw') is not None else {})}
            nxt[m['name']] = {**nxt[m['name']], **merged} if m['name'] in nxt else merged
        root.layers = nxt
        return self

    def layer(self, name, def_=None, **kw):
        d = opts(def_, kw)
        if def_ is not None or kw:  # JS `if (def)`: any object given (even an empty one) resets the layer
            self.root.layers[name] = {'color': 7, 'ltype': 'CONTINUOUS', **d}
        elif name not in self.root.layers:
            self.root.layers[name] = {'color': 7, 'ltype': 'CONTINUOUS'}
        return name

    def block(self, name):
        """Create (or fetch) a block definition."""
        root = self.root
        if name not in root.blocks:
            root.blocks[name] = Canvas(name, root)
        return root.blocks[name]

    def add(self, e):
        if not e.get('layer'):
            e['layer'] = '0'
        self.layer(e['layer'])
        self.entities.append(e)
        return e

    def group(self, name, entities, desc=None):
        """A named group of entities (selected together in AutoCAD): a bar with its texts and its distribution dimension."""
        root = self.root
        if root.groups is None:
            root.groups = []
        root.groups.append({'name': name, 'desc': desc, 'entities': [e for e in entities if e]})

    def line(self, x1, y1, x2, y2, o=None, **kw):
        return self.add({'t': 'line', 'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, **opts(o, kw)})

    def pline(self, pts, o=None, **kw):
        o = opts(o, kw)
        return self.add({'t': 'pline', 'pts': [{'x': p['x'], 'y': p['y'], 'bulge': p.get('bulge') or 0} for p in pts], 'closed': bool(o.get('closed')), **o})

    def rect(self, x, y, w, h, o=None, **kw):
        return self.pline([{'x': x, 'y': y}, {'x': x + w, 'y': y}, {'x': x + w, 'y': y + h}, {'x': x, 'y': y + h}], {**opts(o, kw), 'closed': True})

    def circle(self, cx, cy, r, o=None, **kw):
        return self.add({'t': 'circle', 'cx': cx, 'cy': cy, 'r': r, **opts(o, kw)})

    def arc(self, cx, cy, r, a1, a2, o=None, **kw):
        return self.add({'t': 'arc', 'cx': cx, 'cy': cy, 'r': r, 'a1': a1, 'a2': a2, **opts(o, kw)})

    def text(self, x, y, s, o=None, **kw):
        """Single-line text. align: L|C|R, valign: B|M|T, h: height, rot: degrees."""
        o = opts(o, kw)
        # no text is ever upside down, and a vertical text reads bottom to top (the office reads a plan standing at its
        # bottom edge for horizontal writing and at its RIGHT edge for vertical writing): a rotation in (90.5, 270.5] is
        # turned by 180° with the anchor mirrored, so the text keeps its place
        rot = _number(o.get('rot')) or 0
        rot = (math.fmod(rot, 360) + 360) % 360
        align = o.get('align') or 'L'
        valign = o.get('valign') or 'B'
        if rot > 90.5 and rot <= 270.5:
            rot -= 180
            align = 'R' if align == 'L' else 'L' if align == 'R' else align
            valign = 'T' if valign == 'B' else 'B' if valign == 'T' else valign
        return self.add({'t': 'text', 'x': x, 'y': y, 'str': js_str(s), 'h': o.get('h') or 2.5, **o, 'rot': rot, 'align': align, 'valign': valign})

    def mtext(self, x, y, s, o=None, **kw):
        """Multi-line text, attached top-left, wrapped at width."""
        o = opts(o, kw)
        return self.add({'t': 'mtext', 'x': x, 'y': y, 'str': js_str(s), 'h': o.get('h') or 2.5, 'width': o.get('width') or 0, 'attach': o.get('attach') or 1, **o})

    def hatch(self, polys, o=None, **kw):
        """Hatch a list of polygons (outer + islands). pattern: SOLID | ANSI31 | ANSI37 | DOTS."""
        o = opts(o, kw)
        return self.add({'t': 'hatch', 'polys': [[_pt(q) for q in p] for p in polys], 'pattern': o.get('pattern') or 'ANSI31', 'scale': o.get('scale') or 1, 'angle': o.get('angle') or 0, **o})

    def solid(self, pts, o=None, **kw):
        return self.add({'t': 'solid', 'pts': [_pt(p) for p in pts], **opts(o, kw)})

    def insert(self, name, x, y, o=None, **kw):
        o = opts(o, kw)
        return self.add({'t': 'insert', 'name': name, 'x': x, 'y': y, 'sx': o.get('sx') or 1, 'sy': o.get('sy') or o.get('sx') or 1, 'rot': o.get('rot') or 0, **o})

    def dimension(self, p1, p2, dl, o=None, **kw):
        """
        A real DIMENSION entity (rotated dimension) measuring p1 -> p2 with the
        dimension line through `dl`, drawn with the named DIMSTYLE. AutoCAD needs
        the dimension picture as an anonymous block (*D1, *D2 ...), so the
        geometry is generated here from the style (extension lines, dimension
        line, oblique ticks, text) and stored in that block; other CAD readers
        and the SVG preview render the same block.
          o.style     DIMSTYLE name (registered with dimStyleDef; DEFAULT_DIMSTYLE otherwise)
          o.angle     dimension line angle in degrees (default: the direction p1 -> p2)
          o.textMid   text middle point (default: on the dimension line, offset by gap + txt/2)
          o.text      text override ("<>" = measured value)
        Style fields se1 / se2 suppress the extension lines (DIMSE1 / DIMSE2).
        """
        o = opts(o, kw)
        root = self.root
        if o.get('styleDef') and o.get('style') and o['style'] not in root.dim_styles:
            root.dim_style_def(o['style'], o['styleDef'])
        st = root.dim_styles.get(o.get('style')) or DEFAULT_DIMSTYLE
        layer = o.get('layer') or 'DIM'
        angle = o['angle'] if o.get('angle') is not None else (math.atan2(p2['y'] - p1['y'], p2['x'] - p1['x']) * 180) / math.pi
        r = (angle * math.pi) / 180
        u = {'x': math.cos(r), 'y': math.sin(r)}
        n = {'x': -u['y'], 'y': u['x']}

        def along(p):
            return (p['x'] - dl['x']) * u['x'] + (p['y'] - dl['y']) * u['y']

        a = {'x': dl['x'] + u['x'] * along(p1), 'y': dl['y'] + u['y'] * along(p1)}
        b = {'x': dl['x'] + u['x'] * along(p2), 'y': dl['y'] + u['y'] * along(p2)}
        measure = abs(along(p2) - along(p1))
        text = o['text'].replace('<>', fmt_num(js_round(measure)), 1) if o.get('text') and o['text'] != '<>' else fmt_num(js_round(measure))
        rot = (math.fmod(angle, 360) + 360) % 360
        if rot > 90.5 and rot <= 270.5:
            rot -= 180  # vertical dimension text reads bottom to top (the reader stands at the right edge)
        tm = o.get('textMid') or {'x': (a['x'] + b['x']) / 2 + n['x'] * (st['gap'] + st['txt'] / 2), 'y': (a['y'] + b['y']) / 2 + n['y'] * (st['gap'] + st['txt'] / 2)}
        # the dimension picture
        root.dim_count += 1
        name = f'*D{root.dim_count}'
        blk = root.block(name)
        blk.anonymous = True
        line_o = {'layer': layer, 'color': None if st['clrd'] == 256 else st['clrd']}
        for src, end, sup in [[p1, a, st.get('se1')], [p2, b, st.get('se2')]]:
            if sup:
                continue  # extension line suppressed by the style (dimse1 / dimse2)
            off = (end['x'] - src['x']) * n['x'] + (end['y'] - src['y']) * n['y']
            if abs(off) > st['exo'] + 1:
                sg = _sign(off)
                blk.line(src['x'] + n['x'] * sg * st['exo'], src['y'] + n['y'] * sg * st['exo'], end['x'] + n['x'] * sg * st['exe'], end['y'] + n['y'] * sg * st['exe'], line_o)
        blk.line(a['x'], a['y'], b['x'], b['y'], line_o)
        for c in [a, b]:
            blk.line(c['x'] - (u['x'] + n['x']) * st['tsz'] * 0.5, c['y'] - (u['y'] + n['y']) * st['tsz'] * 0.5, c['x'] + (u['x'] + n['x']) * st['tsz'] * 0.5, c['y'] + (u['y'] + n['y']) * st['tsz'] * 0.5, line_o)
        ts = root.text_styles.get(st['txsty'])
        blk.text(tm['x'], tm['y'], text, {'layer': layer, 'color': None if st['clrt'] == 256 else st['clrt'], 'h': st['txt'], 'rot': rot, 'align': 'C', 'valign': 'M', 'style': st['txsty'], 'widthFactor': ts.get('widthFactor') if ts else None})
        return self.add({'t': 'dimension', 'p1': _pt(p1), 'p2': _pt(p2), 'dl': _pt(dl), 'angle': angle, 'textMid': tm, 'text': o['text'] if o.get('text') and o['text'] != '<>' else '<>', 'measure': measure, 'style': o.get('style') or 'STANDARD', 'block': name, 'layer': layer, **({'color': o['color']} if o.get('color') is not None else {})})

    def arrow(self, fx, fy, tx, ty, size, o=None, **kw):
        """Arrow head as a filled triangle pointing from (fx,fy) towards (tx,ty)."""
        a = math.atan2(ty - fy, tx - fx)
        s = size
        p1 = {'x': tx, 'y': ty}
        p2 = {'x': tx - s * math.cos(a - 0.3), 'y': ty - s * math.sin(a - 0.3)}
        p3 = {'x': tx - s * math.cos(a + 0.3), 'y': ty - s * math.sin(a + 0.3)}
        return self.solid([p1, p2, p3, p3], opts(o, kw))

    def leader(self, pts, o=None, **kw):
        """Leader: polyline from text point through vertices to the target, arrow at the target."""
        o = opts(o, kw)
        for i in range(len(pts) - 1):
            self.line(pts[i]['x'], pts[i]['y'], pts[i + 1]['x'], pts[i + 1]['y'], o)
        n = len(pts)
        if n >= 2:
            self.arrow(pts[n - 2]['x'], pts[n - 2]['y'], pts[n - 1]['x'], pts[n - 1]['y'], o.get('arrowSize') or 2.5, o)

    def dim(self, p1, p2, offset, o=None, **kw):
        """
        A dimension drawn as lines and text (no DIMENSION entity, so it stays
        editable as plain geometry). p1 → p2 measured, offset perpendicular.
        """
        o = opts(o, kw)
        dx, dy = p2['x'] - p1['x'], p2['y'] - p1['y']
        L = js_hypot(dx, dy)
        if L < 1e-6:
            return None
        nx, ny = -dy / L, dx / L
        a = {'x': p1['x'] + nx * offset, 'y': p1['y'] + ny * offset}
        b = {'x': p2['x'] + nx * offset, 'y': p2['y'] + ny * offset}
        ext = o.get('ext') or 2
        tick = o.get('tick') or 1.5
        layer = o.get('layer') or 'DIM'
        self.line(p1['x'], p1['y'], a['x'] + nx * ext, a['y'] + ny * ext, {'layer': layer})
        self.line(p2['x'], p2['y'], b['x'] + nx * ext, b['y'] + ny * ext, {'layer': layer})
        self.line(a['x'], a['y'], b['x'], b['y'], {'layer': layer})
        for p in [a, b]:
            ux, uy = dx / L, dy / L
            self.line(p['x'] - (ux + nx) * tick * 0.7, p['y'] - (uy + ny) * tick * 0.7, p['x'] + (ux + nx) * tick * 0.7, p['y'] + (uy + ny) * tick * 0.7, {'layer': layer})
        rot = (math.atan2(dy, dx) * 180) / math.pi
        if rot > 90.5 or rot <= -89.5:
            rot += 180
        m = {'x': (a['x'] + b['x']) / 2 + nx * (o.get('h') or 2.5) * 0.4, 'y': (a['y'] + b['y']) / 2 + ny * (o.get('h') or 2.5) * 0.4}
        self.text(m['x'], m['y'], o['text'] if o.get('text') is not None else fmt_num(js_round(L)), {'layer': layer, 'h': o.get('h') or 2.5, 'rot': rot, 'align': 'C', 'valign': 'B'})
        return None

    def bbox(self):
        b = None

        def push(x, y):
            nonlocal b
            if not b:
                b = {'minX': x, 'minY': y, 'maxX': x, 'maxY': y}
            else:
                b['minX'] = min(b['minX'], x)
                b['minY'] = min(b['minY'], y)
                b['maxX'] = max(b['maxX'], x)
                b['maxY'] = max(b['maxY'], y)

        for e in self.entities:
            t = e.get('t')
            if t == 'line':
                push(e['x1'], e['y1'])
                push(e['x2'], e['y2'])
            elif t == 'pline':
                for p in e['pts']:
                    push(p['x'], p['y'])
            elif t == 'solid':
                for p in e['pts']:
                    push(p['x'], p['y'])
            elif t == 'hatch':
                for poly in e['polys']:
                    for p in poly:
                        push(p['x'], p['y'])
            elif t == 'circle' or t == 'arc':
                push(e['cx'] - e['r'], e['cy'] - e['r'])
                push(e['cx'] + e['r'], e['cy'] + e['r'])
            elif t == 'text':
                push(e['x'], e['y'])
                push(e['x'] + e['h'] * 0.8 * len(e['str']), e['y'] + e['h'])
            elif t == 'mtext':
                push(e['x'], e['y'])
            elif t == 'dimension':
                push(e['p1']['x'], e['p1']['y'])
                push(e['p2']['x'], e['p2']['y'])
                push(e['dl']['x'], e['dl']['y'])
            elif t == 'insert':
                blk = self.root.blocks.get(e['name'])
                bb = blk.bbox() if blk else None
                if bb:
                    push(e['x'] + bb['minX'] * e['sx'], e['y'] + bb['minY'] * e['sy'])
                    push(e['x'] + bb['maxX'] * e['sx'], e['y'] + bb['maxY'] * e['sy'])
        if b:
            b['w'] = b['maxX'] - b['minX']
            b['h'] = b['maxY'] - b['minY']
            b['cx'] = (b['minX'] + b['maxX']) / 2
            b['cy'] = (b['minY'] + b['maxY']) / 2
        return b


def _number(v):
    """JS `Number(v) || 0` for a rotation option: None / non-numeric -> 0."""
    if v is None or isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return 0 if isinstance(v, float) and math.isnan(v) else v
    try:
        return float(str(v).strip() or 0)
    except ValueError:
        return 0


def _sign(v):
    """JS `Math.sign`."""
    return 1 if v > 0 else -1 if v < 0 else 0
