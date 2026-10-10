"""
Reads the JSON that LibreDWG's `dwgread -O json` writes for a DWG and
turns it into the same entity model `parse_dxf` produces, so a DWG can be
fed to the extractor without AutoCAD:

  dwgread -O json -o drawing.json drawing.dwg
  python -m pydrawings --input drawing.json ...

Only what the extractor and the preview need is converted.

Port of `shopdrawings/lib/libredwg-json.mjs`.
"""
import math

from .dxf_reader import strip_mtext


def _ref(h):
    return h[-1] if isinstance(h, list) and h else None


def _deg(r):
    return ((r or 0) * 180) / math.pi


LINEWT = {29: None, 30: None, 31: None}


def _at(arr, i, default=None):
    """`arr?.[i] ?? default` on a JSON array that may be missing or short."""
    if isinstance(arr, list) and i < len(arr) and arr[i] is not None:
        return arr[i]
    return default


def from_libredwg_json(json):
    objs = json.get('OBJECTS') or []
    by_handle = {}
    for o in objs:
        by_handle[o['handle'][2]] = o

    def name_of(h):
        o = by_handle.get(_ref(h))
        return o.get('name') if o else None

    # layers and linetypes
    layers = {}
    for o in objs:
        if o.get('object') == 'LAYER':
            color = o.get('color') if isinstance(o.get('color'), dict) else None
            idx = color.get('index') if color else None
            layers[o.get('name')] = {
                'color': idx if idx is not None else 7,
                'ltype': name_of(o.get('ltype')) or 'CONTINUOUS',
                'lw': o.get('linewt'),
                'off': bool((o.get('flag0') or 0) & 1) and False,  # `!!(o.flag0 & 1) && false`: always false in the JS too
                'frozen': bool((o.get('flag0') or 0) & 1),
            }
    styles = {}
    for o in objs:
        if o.get('object') == 'STYLE':
            styles[o.get('name')] = {'font': o.get('font_file')}

    def convert(o):
        layer = name_of(o.get('layer')) or '0'
        color = o.get('color') if isinstance(o.get('color'), dict) else None
        idx = color.get('index') if color else None
        lw = o.get('linewt')
        base = {'type': o.get('entity'), 'layer': layer, 'color': idx if idx is not None else 256, 'lw': lw if lw not in LINEWT else None, 'handle': o['handle'][2]}
        ent = o.get('entity')
        if ent == 'LINE':
            return {**base, 'x': o['start'][0], 'y': o['start'][1], 'x2': o['end'][0], 'y2': o['end'][1]}
        if ent == 'LWPOLYLINE':
            bulges = o.get('bulges')
            pts = [{'x': p[0], 'y': p[1], 'bulge': (_at(bulges, i) if bulges else 0) or 0} for i, p in enumerate(o.get('points') or [])]
            return {**base, 'pts': pts, 'closed': bool((o.get('flag') or 0) & 512), 'width': o.get('const_width') or 0}
        if ent == 'POLYLINE_2D':
            pts = []
            for vh in o.get('vertex') or []:
                v = by_handle.get(_ref(vh))
                if v and v.get('point'):
                    pts.append({'x': v['point'][0], 'y': v['point'][1], 'bulge': v.get('bulge') or 0})
            return {**base, 'type': 'LWPOLYLINE', 'pts': pts, 'closed': bool((o.get('flag') or 0) & 1)}
        if ent == 'CIRCLE':
            return {**base, 'x': o['center'][0], 'y': o['center'][1], 'r': o.get('radius')}
        if ent == 'ARC':
            return {**base, 'x': o['center'][0], 'y': o['center'][1], 'r': o.get('radius'), 'a1': _deg(o.get('start_angle')), 'a2': _deg(o.get('end_angle'))}
        if ent in ('TEXT', 'ATTRIB', 'ATTDEF'):
            aligned = (o.get('horiz_alignment') or 0) or (o.get('vert_alignment') or 0)
            p = o['alignment_pt'] if aligned and o.get('alignment_pt') else o['ins_pt']
            return {**base, 'type': 'TEXT', 'x': p[0], 'y': p[1], 'height': o.get('height'), 'text': strip_mtext(o.get('text_value') or ''),
                    'rotation': _deg(o.get('rotation')), 'halign': o.get('horiz_alignment') or 0, 'valign': o.get('vert_alignment') or 0,
                    'style': name_of(o.get('style')), 'tag': o.get('tag')}
        if ent == 'MTEXT':
            xd = o.get('x_axis_dir')
            return {**base, 'x': o['ins_pt'][0], 'y': o['ins_pt'][1], 'height': o.get('text_height'), 'width': o.get('rect_width'),
                    'text': strip_mtext(o.get('text') or ''), 'attachment': o.get('attachment'),
                    'rotation': _deg(math.atan2(_at(xd, 1) or 0, _at(xd, 0, 1))), 'style': name_of(o.get('style'))}
        if ent in ('INSERT', 'MINSERT'):
            attribs = []
            for ah in o.get('attribs') or []:
                a = by_handle.get(_ref(ah))
                if a and a.get('entity') == 'ATTRIB':
                    attribs.append(convert(a))
            return {**base, 'type': 'INSERT', 'name': name_of(o.get('block_header')), 'x': o['ins_pt'][0], 'y': o['ins_pt'][1],
                    'sx': _at(o.get('scale'), 0, 1), 'sy': _at(o.get('scale'), 1, 1), 'rotation': _deg(o.get('rotation')), 'attribs': attribs}
        if ent in ('SOLID', 'TRACE'):
            c = [{'x': p[0], 'y': p[1]} for p in [o['corner1'], o['corner2'], o.get('corner4') or o['corner3'], o['corner3']]]
            return {**base, 'type': 'SOLID', 'pts': c, 'closed': True}
        if ent == 'HATCH':
            paths = []
            for p in o.get('paths') or []:
                if p.get('polyline_paths'):
                    paths.append([{'x': q['point'][0], 'y': q['point'][1], 'bulge': q.get('bulge') or 0} for q in p['polyline_paths']])
                elif p.get('segs'):
                    pts = []
                    for s in p['segs']:
                        if s.get('curve_type') == 1 and s.get('first_endpoint'):
                            pts.append({'x': s['first_endpoint'][0], 'y': s['first_endpoint'][1]})
                    if len(pts) >= 3:
                        paths.append(pts)
            return {**base, 'paths': paths, 'pattern': o.get('name'), 'solid': bool(o.get('is_solid_fill'))}
        if ent == 'LEADER':
            pts = [{'x': p[0], 'y': p[1], 'bulge': 0} for p in o.get('points') or []]
            return {**base, 'type': 'LWPOLYLINE', 'pts': pts, 'closed': False, 'leader': True}
        if ent and ent.startswith('DIMENSION'):
            blk = name_of(o.get('block'))
            return {**base, 'type': 'INSERT', 'name': blk, 'x': 0, 'y': 0, 'sx': 1, 'sy': 1, 'rotation': 0, 'dimension': True,
                    'text': o.get('user_text') or '', 'measurement': o.get('act_measurement')}
        return None

    blocks = {}
    modelspace = []
    paperspace = []
    for o in objs:
        if o.get('object') == 'BLOCK_HEADER':
            ents = []
            for h in o.get('entities') or []:
                e = by_handle.get(_ref(h))
                if not e or not e.get('entity'):
                    continue
                c = convert(e)
                if c:
                    ents.append(c)
            name = o.get('name') or ''
            if name == '*Model_Space':
                modelspace = ents
            elif name.startswith('*Paper_Space'):
                paperspace.extend(ents)
            blocks[name] = {'name': name, 'base': {'x': _at(o.get('base_pt'), 0) or 0, 'y': _at(o.get('base_pt'), 1) or 0},
                            'entities': ents, 'xref': bool(o.get('blkisxref')), 'xrefPath': o.get('xref_pname') or ''}
    H = json.get('HEADER') or {}
    header = {'$INSUNITS': H.get('INSUNITS'), '$LTSCALE': H.get('LTSCALE'), '$DIMSCALE': H.get('DIMSCALE'), '$TEXTSIZE': H.get('TEXTSIZE')}
    return {'header': header, 'blocks': blocks, 'entities': modelspace, 'paperspace': paperspace, 'layers': layers, 'styles': styles,
            'layouts': [n for n in blocks.keys() if n.startswith('*Paper_Space')]}
