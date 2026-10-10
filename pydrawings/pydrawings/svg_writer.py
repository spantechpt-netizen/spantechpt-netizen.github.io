"""
Renders a Canvas as an SVG so a sheet can be previewed in a browser (or in
this repository) without AutoCAD. Blocks are expanded inline.

Port of `shopdrawings/lib/svg-writer.mjs`.
"""
import math
import re

from .canvas import opts as _opts
from .dxf_writer import encode_text  # noqa: F401  (the JS imports it and voids it)
from .geometry import fmt_num, js_round, to_fixed

ACI = {1: '#ff2b2b', 2: '#e6c700', 3: '#22b14c', 4: '#1ec8d8', 5: '#3a6cff', 6: '#e13cd6', 7: '#1c1c1c', 8: '#8a8a8a', 9: '#c0c0c0', 30: '#ff8c1a', 40: '#ffbf00', 256: '#1c1c1c'}


def color(i):
    try:
        return ACI.get(i) or '#1c1c1c'
    except TypeError:  # an unhashable value indexes nothing in JS either
        return '#1c1c1c'


def esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


DASH = {'DASHED': '12,6', 'HIDDEN': '6,3', 'CENTER': '30,6,6,6', 'DASHDOT': '12,6,1,6', 'PHANTOM': '30,6,6,6,6,6'}

_N = fmt_num  # a number inside a template literal prints as JS `String(number)`


def to_svg(root, opts=None, **kw):
    opts = _opts(opts, kw)
    b = root.bbox()
    if not b:
        return '<svg xmlns="http://www.w3.org/2000/svg"/>'
    pad = opts['pad'] if opts.get('pad') is not None else max(b['w'], b['h']) * 0.01
    min_x, min_y, W, Hh = b['minX'] - pad, b['minY'] - pad, b['w'] + 2 * pad, b['h'] + 2 * pad
    px_w = opts.get('width') or 1600
    px_h = js_round((px_w * Hh) / W)
    unit = W / px_w  # drawing units per pixel
    out = []
    layers = root.layers

    def stroke_for(e):
        L = layers.get(e.get('layer')) or {'color': 7}
        c = e['color'] if e.get('color') is not None else L.get('color')
        lw = e['lw'] if e.get('lw') is not None else (L['lw'] if L.get('lw') is not None else 0)
        dash_type = e.get('ltype') or L.get('ltype')
        width = max(unit * 0.9, (lw / 100) * (opts.get('lwScale') or 1) * unit * 2.2)
        s = f'stroke="{color(c)}" stroke-width="{to_fixed(width, 3)}" fill="none" stroke-linecap="round" stroke-linejoin="round"'
        if DASH.get(dash_type):
            s += ' stroke-dasharray="' + ','.join(to_fixed(float(v) * unit * 2.5, 2) for v in DASH[dash_type].split(',')) + '"'
        return {'s': s, 'c': color(c), 'width': width}

    def Y(y):
        return -y

    def tx(x, y, t):
        r = ((t.get('rot') or 0) * math.pi) / 180
        px, py = x * (t.get('sx') or 1), y * (t.get('sy') or 1)
        return {'x': (t.get('x') or 0) + px * math.cos(r) - py * math.sin(r), 'y': (t.get('y') or 0) + px * math.sin(r) + py * math.cos(r)}

    pattern_n = [0]
    defs = []

    def render(canvas, t):
        for e in canvas.entities:
            st = stroke_for(e)
            kind = e.get('t')
            if kind == 'line':
                a, c = tx(e['x1'], e['y1'], t), tx(e['x2'], e['y2'], t)
                out.append(f'<line x1="{_N(a["x"])}" y1="{_N(Y(a["y"]))}" x2="{_N(c["x"])}" y2="{_N(Y(c["y"]))}" {st["s"]}/>')
            elif kind == 'pline':
                pts = [tx(p['x'], p['y'], t) for p in e['pts']]
                d = ' '.join(f'{"L" if i else "M"}{_N(p["x"])} {_N(Y(p["y"]))}' for i, p in enumerate(pts)) + (' Z' if e.get('closed') else '')
                out.append(f'<path d="{d}" {st["s"]}/>')
            elif kind == 'circle':
                c = tx(e['cx'], e['cy'], t)
                out.append(f'<circle cx="{_N(c["x"])}" cy="{_N(Y(c["y"]))}" r="{_N(e["r"] * (t.get("sx") or 1))}" {st["s"]}/>')
            elif kind == 'arc':
                c = tx(e['cx'], e['cy'], t)
                r = e['r'] * (t.get('sx') or 1)
                a1, a2 = ((e['a1'] + (t.get('rot') or 0)) * math.pi) / 180, ((e['a2'] + (t.get('rot') or 0)) * math.pi) / 180
                p1 = {'x': c['x'] + r * math.cos(a1), 'y': c['y'] + r * math.sin(a1)}
                p2 = {'x': c['x'] + r * math.cos(a2), 'y': c['y'] + r * math.sin(a2)}
                sweep = e['a2'] - e['a1']
                while sweep < 0:
                    sweep += 360
                out.append(f'<path d="M{_N(p1["x"])} {_N(Y(p1["y"]))} A{_N(r)} {_N(r)} 0 {1 if sweep > 180 else 0} 0 {_N(p2["x"])} {_N(Y(p2["y"]))}" {st["s"]}/>')
            elif kind == 'solid':
                pts = [tx(p['x'], p['y'], t) for p in e['pts']]
                points = ' '.join(_N(p['x']) + ',' + _N(Y(p['y'])) for p in pts)
                out.append(f'<polygon points="{points}" fill="{st["c"]}" stroke="none"/>')
            elif kind == 'hatch':
                parts = []
                for poly in e['polys']:
                    segs = []
                    for i, p in enumerate(poly):
                        q = tx(p['x'], p['y'], t)
                        segs.append(f'{"L" if i else "M"}{_N(q["x"])} {_N(Y(q["y"]))}')
                    parts.append(' '.join(segs) + ' Z')
                d = ' '.join(parts)
                if e.get('pattern') == 'SOLID':
                    fill = st['c']
                else:
                    pid = f'hp{pattern_n[0]}'
                    pattern_n[0] += 1
                    sp = 3.175 * (e.get('scale') or 1) * (t.get('sx') or 1)
                    angle = (0 if e.get('pattern') == 'DOTS' else 45) + (e.get('angle') or 0)
                    double = e.get('pattern') == 'ANSI37'
                    second = f'<line x1="0" y1="0" x2="{_N(sp)}" y2="0" stroke="{st["c"]}" stroke-width="{to_fixed(unit * 0.9, 3)}"/>' if double else ''
                    defs.append(f'<pattern id="{pid}" patternUnits="userSpaceOnUse" width="{_N(sp)}" height="{_N(sp)}" patternTransform="rotate({_N(-angle)})"><line x1="0" y1="0" x2="0" y2="{_N(sp)}" stroke="{st["c"]}" stroke-width="{to_fixed(unit * 0.9, 3)}"/>{second}</pattern>')
                    fill = f'url(#{pid})'
                out.append(f'<path d="{d}" fill="{fill}" fill-rule="evenodd" stroke="none" opacity="{1 if e.get("pattern") == "SOLID" else 0.9}"/>')
            elif kind == 'text':
                p = tx(e['x'], e['y'], t)
                h = e['h'] * (t.get('sx') or 1)
                anchor = {'L': 'start', 'C': 'middle', 'R': 'end'}.get(e.get('align')) or 'start'
                base = {'B': 'auto', 'M': 'central', 'T': 'hanging'}.get(e.get('valign')) or 'auto'
                rot = -((e.get('rot') or 0) + (t.get('rot') or 0))
                L = layers.get(e.get('layer')) or {'color': 7}
                c = color(e['color'] if e.get('color') is not None else L.get('color'))
                bold = ' font-weight="bold"' if e.get('bold') else ''
                out.append(f'<text x="{_N(p["x"])}" y="{_N(Y(p["y"]))}" font-size="{to_fixed(h * 1.38, 3)}" font-family="Arial, Helvetica, sans-serif" text-anchor="{anchor}" dominant-baseline="{base}" fill="{c}" transform="rotate({_N(rot)} {_N(p["x"])} {_N(Y(p["y"]))})"{bold}>{esc(e["str"])}</text>')
            elif kind == 'mtext':
                p = tx(e['x'], e['y'], t)
                h = e['h'] * (t.get('sx') or 1)
                L = layers.get(e.get('layer')) or {'color': 7}
                c = color(e['color'] if e.get('color') is not None else L.get('color'))
                lines = wrap(e['str'], _floor_div(e['width'], h * 0.78) if e.get('width') else 0)
                lh = h * 1.55 * (e.get('lineSpacing') or 1)
                bold = ' font-weight="bold"' if e.get('bold') else ''
                for i, ln in enumerate(lines):
                    out.append(f'<text x="{_N(p["x"])}" y="{_N(Y(p["y"] - h - i * lh))}" font-size="{to_fixed(h * 1.38, 3)}" font-family="Arial, Helvetica, sans-serif" fill="{c}"{bold}>{esc(ln)}</text>')
            elif kind == 'dimension':
                blk = root.blocks.get(e.get('block'))
                if blk:
                    render(blk, t)
            elif kind == 'insert':
                blk = root.blocks.get(e.get('name'))
                if not blk:
                    continue
                o = tx(e['x'], e['y'], t)
                render(blk, {'x': o['x'], 'y': o['y'], 'sx': (t.get('sx') or 1) * (e.get('sx') or 1), 'sy': (t.get('sy') or 1) * (e.get('sy') or e.get('sx') or 1), 'rot': (t.get('rot') or 0) + (e.get('rot') or 0)})

    render(root, {'x': 0, 'y': 0, 'sx': 1, 'sy': 1, 'rot': 0})
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{_N(px_w)}" height="{_N(px_h)}" viewBox="{_N(min_x)} {_N(-(min_y + Hh))} {_N(W)} {_N(Hh)}">'
            + f'<defs>{"".join(defs)}</defs><rect x="{_N(min_x)}" y="{_N(-(min_y + Hh))}" width="{_N(W)}" height="{_N(Hh)}" fill="#ffffff"/>{chr(10).join(out)}</svg>')


def _floor_div(a, b):
    """JS `Math.floor(a / b)`: a zero divisor gives Infinity (no wrapping) instead of an exception."""
    if b == 0:
        return math.inf if a >= 0 else -math.inf
    return math.floor(a / b)


def wrap(s, max_chars):
    paras = re.split(r'\r?\n', str(s))
    if not max_chars or max_chars < 8:
        return paras
    lines = []
    for p in paras:
        words = re.split(r'\s+', p)
        cur = ''
        for w in words:
            if len((cur + ' ' + w).strip()) > max_chars and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + ' ' if cur else '') + w
        lines.append(cur)
    return lines
