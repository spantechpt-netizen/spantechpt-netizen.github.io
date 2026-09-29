"""
Reads an ASCII DXF (any release from R12 up) into plain entities:
  { type, layer, ... } with points in drawing units.

Only what the extractor needs is decoded: LINE, LWPOLYLINE, POLYLINE,
CIRCLE, ARC, TEXT, MTEXT, INSERT, SOLID, HATCH (boundary paths) and the
BLOCKS section so INSERTs can be exploded. Everything else is skipped.

Port of `shopdrawings/lib/dxf-reader.mjs`. Entities are dicts with the JS keys (type, layer, x, y, xs, ys, x2, y2,
x3, y3, x4, y4, r, height, sx, sy, rotation, a1, a2, flags, halign, text, pts, closed, paths, pattern, name, style,
color, measure, dimType, dimstyle, bulges, xdata); `blocks` is a dict name -> {'name', 'base', 'entities'}.
"""
import math
import re

_NAN = float('nan')
_FLOAT_RE = re.compile(r'^[+-]?(?:Infinity|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)')
_INT_RE = re.compile(r'^[+-]?\d+')


def parse_float(s):
    """JS `parseFloat`: the leading decimal number of the string, NaN when there is none."""
    if isinstance(s, (int, float)) and not isinstance(s, bool):
        return float(s)
    m = _FLOAT_RE.match(str(s).lstrip())
    if not m:
        return _NAN
    t = m.group(0)
    if t.endswith('Infinity'):
        return -math.inf if t.startswith('-') else math.inf
    return float(t)


def parse_int(s):
    """JS `parseInt(s, 10)`: the leading integer of the string, NaN when there is none."""
    m = _INT_RE.match(str(s).lstrip())
    return int(m.group(0)) if m else _NAN


def _t(v):
    """JS truthiness of a parsed value (NaN, 0, '', None are falsy)."""
    if v is None:
        return False
    if isinstance(v, float):
        return not (v == 0 or math.isnan(v))
    return bool(v)


def _int(v):
    """JS `ToInt32` for the bitwise operators (NaN -> 0)."""
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return 0
    return int(v)


def decode_text(s):
    s = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), str(s))
    return re.sub(r'\\M\+[0-9A-Fa-f]{5}', '?', s)


def strip_mtext(s):
    """Strip MTEXT inline formatting codes down to readable text."""
    s = decode_text(s)
    s = s.replace('\\P', '\n')
    s = s.replace('\\~', ' ')
    s = re.sub(r'\\[A-Za-z][^;\\]*;', '', s)
    s = re.sub(r'[{}]', '', s)
    return re.sub(r'%%[cCdDpP]', lambda m: {'c': 'Ø', 'd': '°', 'p': '±'}[m.group(0)[2].lower()], s)


def pairs(text):
    lines = re.split(r'\r?\n', text)
    i = 0
    n = len(lines)
    while i + 1 < n:
        code = parse_int(lines[i].strip())
        if isinstance(code, float) and math.isnan(code):
            i += 2
            continue
        yield [code, lines[i + 1]]
        i += 2


def NUMERIC(code):
    return (code >= 10 and code <= 59) or (code >= 60 and code <= 79) or (code >= 90 and code <= 99) or (code >= 140 and code <= 149) or (code >= 170 and code <= 179) or (code >= 210 and code <= 239) or (code >= 370 and code <= 389)


def build_entity(type_, groups):
    """Turn a run of [code, value] pairs for one entity into an object."""
    e = {'type': type_, 'layer': '0', 'xs': [], 'ys': [], 'bulges': []}
    text_buf = ''
    xapp = None  # the application of the extended data being read (codes 1000-1071 after a 1001)
    for code, raw in groups:
        if code >= 1000:
            if code == 1001:
                xapp = raw.strip()
                e['xdata'] = e.get('xdata') or {}
                e['xdata'][xapp] = e['xdata'].get(xapp) or []
            elif xapp and code != 1002:
                e['xdata'][xapp].append([code, raw.strip() if code == 1000 or code == 1003 or code == 1005 else parse_float(raw)])
            continue
        v = parse_float(raw) if NUMERIC(code) else raw
        if code == 8:
            e['layer'] = raw.strip()
        elif code == 2:
            e['name'] = raw.strip()
        elif code == 10:
            e['xs'].append(v)
        elif code == 20:
            e['ys'].append(v)
        elif code == 11:
            e['x2'] = v
        elif code == 21:
            e['y2'] = v
        elif code == 13:
            e['x3'] = v
        elif code == 23:
            e['y3'] = v
        elif code == 14:
            e['x4'] = v
        elif code == 24:
            e['y4'] = v
        elif code == 7:
            e['style'] = raw.strip()
        elif code == 40:
            e['r'] = v
            e['height'] = v
        elif code == 41:
            e['sx'] = v
            if type_ == 'MTEXT':
                e['width'] = v
        elif code == 42:
            if type_ == 'LWPOLYLINE' or type_ == 'VERTEX':
                i = len(e['xs']) - 1  # a sparse JS array: the holes read as 0 below
                while len(e['bulges']) <= i:
                    e['bulges'].append(0)
                if i >= 0:
                    e['bulges'][i] = v
            elif type_ == 'DIMENSION':
                e['measure'] = v
            else:
                e['sy'] = v
        elif code == 50:
            e['rotation'] = v
            e['a1'] = v
        elif code == 51:
            e['a2'] = v
        elif code == 70:
            e['flags'] = v
        elif code == 72:
            e['halign'] = v
        elif code == 1:
            text_buf += raw
        elif code == 3:
            if type_ == 'DIMENSION':
                e['dimstyle'] = raw.strip()
            else:
                text_buf = raw + text_buf  # MTEXT continuation chunks come first
        elif code == 62:
            e['color'] = v
    if type_ == 'MTEXT':
        # Codes 3 precede the final 1: rebuild in order.
        chunks = [r for c, r in groups if c == 3]
        last = next((g for g in groups if g[0] == 1), None)
        e['text'] = strip_mtext(''.join(chunks) + (last[1] if last else ''))
    elif type_ == 'TEXT' or type_ == 'ATTRIB' or type_ == 'ATTDEF':
        e['text'] = strip_mtext(text_buf)
    e['x'] = e['xs'][0] if len(e['xs']) else 0
    e['y'] = e['ys'][0] if len(e['ys']) else 0
    if type_ == 'TEXT' and _t(e.get('halign')) and e.get('x2') is not None:
        e['x'] = e['x2']
        e['y'] = e.get('y2')
    if type_ == 'DIMENSION':
        # 10/20 dimension line point, 11/21 text midpoint, 13/23 + 14/24 the measured points, 50 rotation, 70 type, 42 measurement, 1 text override
        e['dimType'] = _int(e.get('flags') or 0) & 7
        e['text'] = text_buf.strip()
    if type_ == 'LWPOLYLINE':
        e['pts'] = [{'x': x, 'y': e['ys'][i] if i < len(e['ys']) else None, 'bulge': (e['bulges'][i] if i < len(e['bulges']) else 0) or 0} for i, x in enumerate(e['xs'])]
        e['closed'] = bool(_int(e.get('flags') or 0) & 1)
    if type_ == 'SOLID' or type_ == 'TRACE':
        p = [[c, parse_float(r)] for c, r in groups if c >= 10 and c <= 13]
        q = [[c, parse_float(r)] for c, r in groups if c >= 20 and c <= 23]
        pts = [{'x': x, 'y': (next((qq for qq in q if qq[0] == c + 10), None) or [0, 0])[1]} for c, x in p]
        e['pts'] = [pts[0], pts[1], pts[3], pts[2]] if len(pts) == 4 else pts
        e['closed'] = True
    if type_ == 'HATCH':
        # Boundary paths: polyline paths (92 & 2) or edge paths made of lines.
        e['paths'] = []
        i = 0
        g = groups
        while i < len(g):
            if g[i][0] == 92:
                flags = parse_int(g[i][1])
                path = []
                i += 1
                if _int(flags) & 2:
                    n = 0
                    while i < len(g) and g[i][0] != 97 and g[i][0] != 92:
                        if g[i][0] == 93:
                            n = parse_int(g[i][1])
                        if g[i][0] == 10:
                            path.append({'x': parse_float(g[i][1]), 'y': parse_float(g[i + 1][1] if i + 1 < len(g) and g[i + 1][0] == 20 else 0)})
                        i += 1
                    del n
                else:
                    while i < len(g) and g[i][0] != 97 and g[i][0] != 92:
                        if g[i][0] == 72 and g[i][1].strip() == '1':
                            # line edge: 10 20 11 21
                            x1, y1 = parse_float(g[i + 1][1]), parse_float(g[i + 2][1])
                            path.append({'x': x1, 'y': y1})
                            i += 4
                            continue
                        i += 1
                if len(path) >= 3:
                    e['paths'].append(path)
                continue
            i += 1
        e['pattern'] = e.get('name')
    return e


_KEPT = ['LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'INSERT', 'SOLID', 'TRACE', 'HATCH', 'ATTRIB', 'POINT', 'DIMENSION']


def parse_dxf(text):
    header = {}
    blocks = {}
    entities = []
    state = {'section': None, 'current': None, 'target': entities, 'block': None, 'polyline': None, 'header_var': None}

    def flush():
        current = state['current']
        if not current:
            return
        ent = build_entity(current['type'], current['groups'])
        state['current'] = None
        if ent['type'] == 'BLOCK':
            block = {'name': ent.get('name'), 'base': {'x': ent['x'], 'y': ent['y']}, 'entities': []}
            blocks[block['name']] = block
            state['block'] = block
            state['target'] = block['entities']
            return
        if ent['type'] == 'ENDBLK':
            state['block'] = None
            state['target'] = entities
            return
        if ent['type'] == 'POLYLINE':
            state['polyline'] = {'type': 'LWPOLYLINE', 'layer': ent['layer'], 'pts': [], 'closed': bool(_int(ent.get('flags') or 0) & 1)}
            return
        if ent['type'] == 'VERTEX' and state['polyline']:
            state['polyline']['pts'].append({'x': ent['x'], 'y': ent['y'], 'bulge': (ent['bulges'][0] if ent['bulges'] else 0) or 0})
            return
        if ent['type'] == 'SEQEND':
            if state['polyline']:
                state['target'].append(state['polyline'])
                state['polyline'] = None
            return
        if ent['type'] in _KEPT:
            state['target'].append(ent)

    for code, value in pairs(text):
        if code == 0:
            v = value.strip()
            if v == 'SECTION':
                flush()
                state['section'] = None
                continue
            if v == 'ENDSEC':
                flush()
                state['section'] = None
                continue
            if v == 'EOF':
                flush()
                break
            if state['section'] == 'HEADER':
                continue
            if state['section'] == 'BLOCKS' or state['section'] == 'ENTITIES':
                flush()
                state['current'] = {'type': v, 'groups': []}
            continue
        if code == 2 and state['section'] is None and not state['current']:
            state['section'] = value.strip()
            continue
        if state['section'] == 'HEADER':
            if code == 9:
                state['header_var'] = value.strip()
            elif state['header_var'] and (code == 70 or code == 40 or code == 1 or code == 10 or code == 3):
                if state['header_var'] not in header:
                    header[state['header_var']] = parse_float(value) if NUMERIC(code) else value.strip()
            continue
        if state['current']:
            state['current']['groups'].append([code, value])
    return {'header': header, 'blocks': blocks, 'entities': entities}
