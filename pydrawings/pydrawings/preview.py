"""
Turns a parsed drawing (from parse_dxf or from_libredwg_json) into a Canvas so
it can be previewed as SVG with the same renderer as the generated sheets.

Port of `shopdrawings/lib/preview.mjs`.
"""
from .canvas import Canvas


def drawing_to_canvas(model, space='model', layers=None):
    c = Canvas()
    model_layers = model.get('layers')
    if model_layers:
        for n, d in (model_layers.items() if isinstance(model_layers, dict) else model_layers):
            c.layer(n, {'color': d.get('color'), 'ltype': (d.get('ltype') or 'CONTINUOUS').upper(), 'lw': d['lw'] if d.get('lw') and d['lw'] < 29 else None})

    def add_to(target, e):
        if layers is not None and e.get('layer') not in layers:
            return
        o = {'layer': e.get('layer')}
        if e.get('color') is not None and e['color'] != 256 and e['color'] != 0:
            o['color'] = e['color']
        t = e.get('type')
        if t == 'LINE':
            target.line(e['x'], e['y'], e.get('x2'), e.get('y2'), o)
        elif t == 'LWPOLYLINE':
            if e.get('pts') and len(e['pts']) > 1:
                target.pline(e['pts'], {**o, 'closed': e.get('closed')})
        elif t == 'CIRCLE':
            target.circle(e['x'], e['y'], e.get('r'), o)
        elif t == 'ARC':
            target.arc(e['x'], e['y'], e.get('r'), e.get('a1'), e.get('a2'), o)
        elif t == 'SOLID':
            if e.get('pts') and len(e['pts']) >= 3:
                target.solid([*e['pts'], e['pts'][2]] if len(e['pts']) == 3 else e['pts'], o)
        elif t == 'TEXT':
            halign = e.get('halign')
            align = _lookup({0: 'L', 1: 'C', 2: 'R', 3: 'L', 4: 'C', 5: 'L'}, halign) or 'L'
            valign = _lookup({0: 'B', 1: 'B', 2: 'M', 3: 'T'}, e.get('valign')) or 'B'
            centred = halign == 4 or halign == 3 or halign == 5
            target.text(e['x'], e['y'], e.get('text') or '', {**o, 'h': e.get('height') or 2.5, 'rot': e.get('rotation') or 0, 'align': 'C' if centred else align, 'valign': 'M' if centred else valign})
        elif t == 'MTEXT':
            # attachment 1-3 top, 4-6 middle, 7-9 bottom; shift so the top-left pen matches
            h = e.get('height') or 2.5
            lines = len((e.get('text') or '').split('\n'))
            y = e['y']
            att = e.get('attachment') or 1
            if att >= 4 and att <= 6:
                y += (lines * h * 1.55) / 2
            elif att >= 7:
                y += lines * h * 1.55
            x = e['x']
            if att % 3 == 2 and e.get('width'):
                x -= e['width'] / 2
            elif att % 3 == 0 and e.get('width'):
                x -= e['width']
            target.mtext(x, y, e.get('text') or '', {**o, 'h': h, 'width': e.get('width') or 0, 'rot': e.get('rotation') or 0})
        elif t == 'HATCH':
            if e.get('paths') and len(e['paths']):
                target.hatch([p for p in e['paths'] if len(p) >= 3], {**o, 'pattern': 'SOLID' if (e.get('solid') or e.get('pattern') == 'SOLID') else 'ANSI31', 'scale': 30})
        elif t == 'INSERT':
            if e.get('name') and e['name'] in model['blocks']:
                sx = e['sx'] if e.get('sx') is not None else 1
                sy = e['sy'] if e.get('sy') is not None else (e['sx'] if e.get('sx') is not None else 1)
                target.insert(e['name'], e['x'], e['y'], {**o, 'sx': sx, 'sy': sy, 'rot': e.get('rotation') or 0})
                for a in e.get('attribs') or []:
                    add_to(target, a)

    for name, blk in model['blocks'].items():
        if name == '*Model_Space' or name.startswith('*Paper_Space'):
            continue
        b = c.block(name)
        base = blk.get('base') or {}
        bx, by = base.get('x') or 0, base.get('y') or 0
        for e in blk['entities']:
            add_to(b, shift(e, -bx, -by))
    ents = (model.get('paperspace') or []) if space == 'paper' else model['entities']
    for e in ents:
        add_to(c, e)
    return c


def _lookup(table, key):
    """JS object lookup with a numeric key (a float key equal to an integer hits the same property)."""
    try:
        return table.get(key)
    except TypeError:
        return None


def shift(e, dx, dy):
    if not dx and not dy:
        return e
    s = dict(e)
    if e.get('x') is not None:
        s['x'] = e['x'] + dx
        s['y'] = e['y'] + dy
    if e.get('x2') is not None:
        s['x2'] = e['x2'] + dx
        s['y2'] = e['y2'] + dy
    if e.get('pts'):
        s['pts'] = [{**p, 'x': p['x'] + dx, 'y': p['y'] + dy} for p in e['pts']]
    if e.get('paths'):
        s['paths'] = [[{**p, 'x': p['x'] + dx, 'y': p['y'] + dy} for p in path] for path in e['paths']]
    return s
