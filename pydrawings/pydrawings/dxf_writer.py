"""
Writes a Canvas (model space + block definitions) as an AutoCAD 2000
(AC1015) ASCII DXF. No dependencies; every object gets a handle and an
owner so AutoCAD opens the file without a recover pass.

Text is encoded with \\U+XXXX escapes for anything outside ASCII, which is
how R2000 DXF carries Arabic; AutoCAD 2007 and later shape it correctly.

Port of `shopdrawings/lib/dxf-writer.mjs`.
"""
import math
import re

from .canvas import LINETYPES, js_str
from .geometry import to_fixed

HATCH_PATTERNS = {
    'ANSI31': [{'angle': 45, 'base': [0, 0], 'offset': [0, 3.175], 'dashes': []}],
    'ANSI37': [
        {'angle': 45, 'base': [0, 0], 'offset': [0, 3.175], 'dashes': []},
        {'angle': 135, 'base': [0, 0], 'offset': [0, 3.175], 'dashes': []},
    ],
    'DOTS': [{'angle': 0, 'base': [0, 0], 'offset': [0.79, 0.79], 'dashes': [0, -1.59]}],
    'ANSI31-WIDE': [{'angle': 45, 'base': [0, 0], 'offset': [0, 6.35], 'dashes': []}],
}


def num(v):
    """A coordinate / measure: `v.toFixed(6)` with the trailing zeros (and dot) stripped; '0' for anything not finite."""
    if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
        return '0'
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return '0'
    s = re.sub(r'\.?0+$', '', to_fixed(v, 6))
    return '0' if s == '-0' else s


def encode_text(s):
    out = ''
    for ch in str(s):
        c = ord(ch)
        if c < 127:
            out += ch
        elif c <= 0xffff:
            out += '\\U+' + format(c, 'X').rjust(4, '0')
        else:
            out += '?'
    return out


class Handles:
    def __init__(self):
        self.n = 0x100

    def next(self):
        h = format(self.n, 'X')
        self.n += 1
        return h


# The application name the bar tags (XDATA) are registered under.
XDATA_APP = 'SPANTECH'


_s = js_str  # JS `String(value)` for a group value (numbers without a trailing `.0`)


def to_dxf(root, opts=None):
    opts = opts or {}
    H = Handles()
    L = []

    def tag(code, value):
        L.append(str(code))
        L.append(_s(value))

    # Fixed object handles.
    h_root_dict = H.next()
    h_group_dict = H.next()
    h_plot_dict = H.next()
    h_placeholder = H.next()
    h_layout_dict = H.next()
    h_layout_model = H.next()
    h_layout_paper = H.next()
    h_blk_rec_table = H.next()
    h_ms_rec = H.next()
    h_ps_rec = H.next()
    h_ms_block = H.next()
    h_ms_end = H.next()
    h_ps_block = H.next()
    h_ps_end = H.next()
    block_rec = {}
    for name in root.blocks.keys():
        block_rec[name] = H.next()

    ext = root.bbox() or {'minX': 0, 'minY': 0, 'maxX': 1000, 'maxY': 1000, 'w': 1000, 'h': 1000, 'cx': 500, 'cy': 500}

    # ------------------------------------------------------------ HEADER
    tag(0, 'SECTION'); tag(2, 'HEADER')
    tag(9, '$ACADVER'); tag(1, 'AC1015')
    tag(9, '$DWGCODEPAGE'); tag(3, 'ANSI_1252')
    tag(9, '$INSBASE'); tag(10, 0); tag(20, 0); tag(30, 0)
    tag(9, '$EXTMIN'); tag(10, num(ext['minX'])); tag(20, num(ext['minY'])); tag(30, 0)
    tag(9, '$EXTMAX'); tag(10, num(ext['maxX'])); tag(20, num(ext['maxY'])); tag(30, 0)
    tag(9, '$LIMMIN'); tag(10, 0); tag(20, 0)
    tag(9, '$LIMMAX'); tag(10, num(ext['maxX'])); tag(20, num(ext['maxY']))
    tag(9, '$ORTHOMODE'); tag(70, 0)
    tag(9, '$LTSCALE'); tag(40, num(opts['ltscale'] if opts.get('ltscale') is not None else 1))
    tag(9, '$TEXTSIZE'); tag(40, 2.5)
    tag(9, '$TEXTSTYLE'); tag(7, 'STANDARD')
    tag(9, '$CLAYER'); tag(8, '0')
    tag(9, '$CELTYPE'); tag(6, 'BYLAYER')
    tag(9, '$CECOLOR'); tag(62, 256)
    tag(9, '$DIMSTYLE'); tag(2, 'STANDARD')
    tag(9, '$INSUNITS'); tag(70, 4)  # millimetres
    tag(9, '$MEASUREMENT'); tag(70, 1)  # metric
    tag(9, '$PDMODE'); tag(70, 0)
    tag(9, '$PSLTSCALE'); tag(70, 1)
    tag(9, '$TILEMODE'); tag(70, 1)
    tag(9, '$HANDSEED'); tag(5, 'FFFFFF')
    tag(0, 'ENDSEC')

    # ------------------------------------------------------------ CLASSES
    tag(0, 'SECTION'); tag(2, 'CLASSES'); tag(0, 'ENDSEC')

    # ------------------------------------------------------------ TABLES
    tag(0, 'SECTION'); tag(2, 'TABLES')

    def table(name, records, extra=None):
        h = h_blk_rec_table if name == 'BLOCK_RECORD' else H.next()
        tag(0, 'TABLE'); tag(2, name); tag(5, h); tag(330, 0); tag(100, 'AcDbSymbolTable'); tag(70, len(records))
        if extra:
            extra()
        for r in records:
            r(h)
        tag(0, 'ENDTAB')

    def vport(owner):
        tag(0, 'VPORT'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbViewportTableRecord')
        tag(2, '*Active'); tag(70, 0)
        tag(10, 0); tag(20, 0); tag(11, 1); tag(21, 1)
        tag(12, num(ext['cx'])); tag(22, num(ext['cy']))
        tag(13, 0); tag(23, 0); tag(14, 10); tag(24, 10); tag(15, 10); tag(25, 10)
        tag(16, 0); tag(26, 0); tag(36, 1); tag(17, 0); tag(27, 0); tag(37, 0)
        tag(40, num(ext['h'] * 1.1 or 1000)); tag(41, num((ext['w'] or 1000) / (ext['h'] or 1000) * 1.0))
        tag(42, 50); tag(43, 0); tag(44, 0); tag(50, 0); tag(51, 0)
        tag(71, 0); tag(72, 1000); tag(73, 1); tag(74, 3); tag(75, 0); tag(76, 0); tag(77, 0); tag(78, 0)
        tag(281, 0); tag(65, 1); tag(110, 0); tag(120, 0); tag(130, 0); tag(111, 1); tag(121, 0); tag(131, 0)
        tag(112, 0); tag(122, 1); tag(132, 0); tag(79, 0); tag(146, 0)

    table('VPORT', [vport])

    def ltype_record(name, desc, pattern):
        def rec(owner):
            tag(0, 'LTYPE'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbLinetypeTableRecord')
            tag(2, name); tag(70, 0); tag(3, desc); tag(72, 65); tag(73, len(pattern))
            tag(40, num(sum(abs(v) for v in pattern)))
            for d in pattern:
                tag(49, num(d)); tag(74, 0)
        return rec

    table('LTYPE', [
        ltype_record('ByBlock', '', []),
        ltype_record('ByLayer', '', []),
        *[ltype_record(n, d['desc'], d['pattern']) for n, d in LINETYPES.items()],
    ])

    def layer_record(name, d):
        def rec(owner):
            tag(0, 'LAYER'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbLayerTableRecord')
            tag(2, name); tag(70, 0); tag(62, d['color'] if d.get('color') is not None else 7); tag(6, d.get('ltype') or 'CONTINUOUS')
            tag(370, d['lw'] if d.get('lw') is not None else -3); tag(390, h_placeholder)
        return rec

    table('LAYER', [layer_record(name, d) for name, d in root.layers.items()])

    text_styles = getattr(root, 'text_styles', None)
    text_style = getattr(root, 'text_style', None)
    styles = list(text_styles.items()) if text_styles else [['STANDARD', {'font': (text_style or {}).get('font') or 'arial.ttf'}]]
    styles = [list(s) for s in styles]
    if not any(s[0] == 'STANDARD' for s in styles):
        styles.insert(0, ['STANDARD', {'font': 'arial.ttf'}])
    style_handles = {}

    def style_record(name, d):
        def rec(owner):
            hs = H.next()
            style_handles[name] = hs
            tag(0, 'STYLE'); tag(5, hs); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbTextStyleTableRecord')
            tag(2, name); tag(70, 0); tag(40, 0); tag(41, d.get('widthFactor') or 1); tag(50, 0); tag(71, 0); tag(42, 2.5); tag(3, d.get('font') or 'arial.ttf'); tag(4, '')
        return rec

    table('STYLE', [style_record(name, d) for name, d in styles])

    table('VIEW', [])
    table('UCS', [])

    def appid_acad(owner):
        tag(0, 'APPID'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbRegAppTableRecord'); tag(2, 'ACAD'); tag(70, 0)

    def appid_spantech(owner):
        # the application the bar tags (XDATA) are registered under: every entity of a bar carries its id and figures
        tag(0, 'APPID'); tag(5, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbRegAppTableRecord'); tag(2, XDATA_APP); tag(70, 0)

    table('APPID', [appid_acad, appid_spantech])

    dim_styles = [(n, d) for n, d in (getattr(root, 'dim_styles', None) or {}).items() if n != 'STANDARD']

    def dimstyle_standard(owner):
        tag(0, 'DIMSTYLE'); tag(105, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbDimStyleTableRecord')
        tag(2, 'STANDARD'); tag(70, 0); tag(40, 1); tag(41, 2.5); tag(42, 0.625); tag(43, 3.75); tag(44, 1.25); tag(140, 2.5); tag(141, 2.5); tag(147, 0.625)

    def dimstyle_record(name, d):
        def rec(owner):
            # a DIMSTYLE in model units: oblique ticks (dimtsz) instead of arrow blocks, text above the line
            tag(0, 'DIMSTYLE'); tag(105, H.next()); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbDimStyleTableRecord')
            tag(2, name); tag(70, 0); tag(3, ''); tag(4, '')
            tag(40, num(d['scale'] if d.get('scale') is not None else 1)); tag(41, num(d.get('asz'))); tag(42, num(d.get('exo'))); tag(43, num(3.75)); tag(44, num(d.get('exe'))); tag(45, 0); tag(46, 0); tag(47, 0); tag(48, 0)
            tag(140, num(d.get('txt'))); tag(141, 2.5); tag(142, num(d.get('tsz'))); tag(143, 25.4); tag(144, 1); tag(145, 0); tag(146, 1); tag(147, num(d.get('gap'))); tag(148, 0)
            tag(71, 0); tag(72, 0); tag(73, 0); tag(74, 0); tag(75, 1 if d.get('se1') else 0); tag(76, 1 if d.get('se2') else 0); tag(77, d['tad'] if d.get('tad') is not None else 1); tag(78, 8); tag(79, 3)
            tag(170, 0); tag(171, 3); tag(172, 1); tag(173, 0); tag(174, 0); tag(175, 0); tag(176, d['clrd'] if d.get('clrd') is not None else 256); tag(177, d['clre'] if d.get('clre') is not None else 256); tag(178, d['clrt'] if d.get('clrt') is not None else 256); tag(179, 2)
            tag(271, d['dec'] if d.get('dec') is not None else 0); tag(272, 2); tag(273, 2); tag(274, 3); tag(275, 0); tag(276, 0); tag(277, 2); tag(278, 44); tag(279, 0)
            tag(280, 0); tag(281, 0); tag(282, 0); tag(283, 0); tag(284, 8); tag(285, 0); tag(286, 0); tag(288, 0); tag(289, 3)
            tag(340, style_handles.get(d.get('txsty')) or style_handles.get('STANDARD')); tag(371, -2); tag(372, -2)
        return rec

    table('DIMSTYLE', [dimstyle_standard, *[dimstyle_record(n, d) for n, d in dim_styles]], lambda: tag(100, 'AcDbDimStyleTable'))

    def block_record(h, name, layout):
        def rec(owner):
            tag(0, 'BLOCK_RECORD'); tag(5, h); tag(330, owner); tag(100, 'AcDbSymbolTableRecord'); tag(100, 'AcDbBlockTableRecord')
            tag(2, name); tag(340, layout or 0)
        return rec

    table('BLOCK_RECORD', [
        block_record(h_ms_rec, '*Model_Space', h_layout_model),
        block_record(h_ps_rec, '*Paper_Space', h_layout_paper),
        *[block_record(h, name, 0) for name, h in block_rec.items()],
    ])
    tag(0, 'ENDSEC')

    # ------------------------------------------------------------ entities
    def entity_header(type_, e, owner, paper=False):
        h = H.next()
        e['_h'] = h  # kept for the GROUP objects
        tag(0, type_); tag(5, h); tag(330, owner); tag(100, 'AcDbEntity')
        if paper:
            tag(67, 1)
        tag(8, e.get('layer') or '0')
        if e.get('ltype'):
            tag(6, e['ltype'])
        if e.get('color') is not None:
            tag(62, e['color'])
        if e.get('lw') is not None:
            tag(370, e['lw'])

    def write_entity(e, owner):
        t = e.get('t')
        if t == 'line':
            entity_header('LINE', e, owner); tag(100, 'AcDbLine')
            tag(10, num(e['x1'])); tag(20, num(e['y1'])); tag(30, 0); tag(11, num(e['x2'])); tag(21, num(e['y2'])); tag(31, 0)
        elif t == 'pline':
            entity_header('LWPOLYLINE', e, owner); tag(100, 'AcDbPolyline')
            tag(90, len(e['pts'])); tag(70, 1 if e.get('closed') else 0); tag(43, num(e.get('width') or 0))
            for p in e['pts']:
                tag(10, num(p['x'])); tag(20, num(p['y']))
                if p.get('bulge'):
                    tag(42, num(p['bulge']))
        elif t == 'circle':
            entity_header('CIRCLE', e, owner); tag(100, 'AcDbCircle')
            tag(10, num(e['cx'])); tag(20, num(e['cy'])); tag(30, 0); tag(40, num(e['r']))
        elif t == 'arc':
            entity_header('ARC', e, owner); tag(100, 'AcDbCircle')
            tag(10, num(e['cx'])); tag(20, num(e['cy'])); tag(30, 0); tag(40, num(e['r']))
            tag(100, 'AcDbArc'); tag(50, num(e['a1'])); tag(51, num(e['a2']))
        elif t == 'solid':
            entity_header('SOLID', e, owner); tag(100, 'AcDbTrace')
            p = e['pts']
            q = [p[0], p[1], (p[3] if len(p) > 3 else None) or p[2], p[2]]  # SOLID takes a bow-tie order
            for i, pt in enumerate(q):
                tag(10 + i, num(pt['x'])); tag(20 + i, num(pt['y'])); tag(30 + i, 0)
        elif t == 'text':
            entity_header('TEXT', e, owner); tag(100, 'AcDbText')
            h_align = {'L': 0, 'C': 1, 'R': 2}.get(e.get('align'))
            h_align = 0 if h_align is None else h_align
            v_align = {'B': 0, 'M': 2, 'T': 3}.get(e.get('valign'))
            v_align = 0 if v_align is None else v_align
            tag(10, num(e['x'])); tag(20, num(e['y'])); tag(30, 0); tag(40, num(e['h'])); tag(1, encode_text(e['str']))
            if e.get('rot'):
                tag(50, num(e['rot']))
            if e.get('widthFactor'):
                tag(41, num(e['widthFactor']))
            tag(7, e.get('style') or 'STANDARD'); tag(72, h_align)
            if h_align or v_align:
                tag(11, num(e['x'])); tag(21, num(e['y'])); tag(31, 0)
            tag(100, 'AcDbText'); tag(73, v_align)
        elif t == 'mtext':
            entity_header('MTEXT', e, owner); tag(100, 'AcDbMText')
            tag(10, num(e['x'])); tag(20, num(e['y'])); tag(30, 0); tag(40, num(e['h']))
            if e.get('width'):
                tag(41, num(e['width']))
            tag(71, e.get('attach') or 1); tag(72, 1)
            s = encode_text(re.sub(r'\r?\n', lambda m: '\\P', e['str']))
            chunks = re.findall(r'[^\n\r]{1,250}', s) or ['']  # JS `.` (no line terminators) in chunks of 250
            for c in chunks[:-1]:
                tag(3, c)
            tag(1, chunks[-1])
            tag(7, e.get('style') or 'STANDARD')
            if e.get('rot'):
                tag(50, num(e['rot']))
            tag(44, num(e.get('lineSpacing') or 1))
        elif t == 'hatch':
            entity_header('HATCH', e, owner); tag(100, 'AcDbHatch')
            tag(10, 0); tag(20, 0); tag(30, 0); tag(210, 0); tag(220, 0); tag(230, 1)
            solid = e.get('pattern') == 'SOLID'
            tag(2, e.get('pattern')); tag(70, 1 if solid else 0); tag(71, 0)
            polys = e['polys']
            tag(91, len(polys))
            for poly in polys:
                tag(92, 2 | (1 if poly is polys[0] else 16)); tag(72, 0); tag(73, 1); tag(93, len(poly))
                for p in poly:
                    tag(10, num(p['x'])); tag(20, num(p['y']))
                tag(97, 0)
            tag(75, 0 if len(polys) > 1 else 1); tag(76, 1 if solid else 1)
            if not solid:
                d = HATCH_PATTERNS.get(e.get('pattern')) or HATCH_PATTERNS['ANSI31']
                tag(52, num(e.get('angle') or 0)); tag(41, num(e.get('scale') or 1)); tag(77, 0); tag(78, len(d))
                sc = e.get('scale') or 1
                rot = ((e.get('angle') or 0) * math.pi) / 180
                for ln in d:
                    a = ln['angle'] + (e.get('angle') or 0)
                    tt = (ln['angle'] * math.pi) / 180 + rot
                    ox, oy = ln['offset'][0] * sc, ln['offset'][1] * sc
                    tag(53, num(a)); tag(43, num(ln['base'][0] * sc)); tag(44, num(ln['base'][1] * sc))
                    tag(45, num(ox * math.cos(tt) - oy * math.sin(tt))); tag(46, num(ox * math.sin(tt) + oy * math.cos(tt)))
                    tag(79, len(ln['dashes']))
                    for dd in ln['dashes']:
                        tag(49, num(dd * sc))
            # no group 47 (pixel size): AutoCAD reads it only for boundary paths flagged 'derived' (0x4)
            # and otherwise rejects the file with "expected group code 98"
            tag(98, 0)
        elif t == 'dimension':
            # rotated dimension with its picture block; AutoCAD regenerates the picture from the style when edited
            entity_header('DIMENSION', e, owner); tag(100, 'AcDbDimension')
            tag(2, e['block']); tag(3, e.get('style') or 'STANDARD')
            tag(10, num(e['dl']['x'])); tag(20, num(e['dl']['y'])); tag(30, 0)
            tag(11, num(e['textMid']['x'])); tag(21, num(e['textMid']['y'])); tag(31, 0)
            tag(70, 32); tag(71, 5); tag(42, num(e['measure'])); tag(1, e.get('text') or '<>')
            # (AutoCAD regenerates the text along the dimension line reading from the bottom or the right, which is how the
            # office reads: no text turn is written)
            tag(100, 'AcDbAlignedDimension')
            tag(13, num(e['p1']['x'])); tag(23, num(e['p1']['y'])); tag(33, 0)
            tag(14, num(e['p2']['x'])); tag(24, num(e['p2']['y'])); tag(34, 0)
            tag(50, num(e.get('angle') or 0))
            tag(100, 'AcDbRotatedDimension')
        elif t == 'insert':
            entity_header('INSERT', e, owner); tag(100, 'AcDbBlockReference')
            tag(2, e['name']); tag(10, num(e['x'])); tag(20, num(e['y'])); tag(30, 0)
            tag(41, num(e.get('sx') or 1)); tag(42, num(e.get('sy') or e.get('sx') or 1)); tag(43, 1); tag(50, num(e.get('rot') or 0))
        else:
            return
        # extended data (the bar tags): after every normal group of the entity, under the registered application
        if e.get('xdata') and len(e['xdata']):
            tag(1001, XDATA_APP); tag(1002, '{')
            for code, value in e['xdata']:
                tag(code, encode_text(js_str(value))[:255] if code == 1000 else num(value))
            tag(1002, '}')

    # ------------------------------------------------------------ BLOCKS
    tag(0, 'SECTION'); tag(2, 'BLOCKS')

    def block_begin(h, rec, name, paper, anonymous=False):
        tag(0, 'BLOCK'); tag(5, h); tag(330, rec); tag(100, 'AcDbEntity')
        if paper:
            tag(67, 1)
        tag(8, '0'); tag(100, 'AcDbBlockBegin')
        tag(2, name); tag(70, 1 if anonymous else 0); tag(10, 0); tag(20, 0); tag(30, 0); tag(3, name); tag(1, '')

    def block_end(h, rec, paper):
        tag(0, 'ENDBLK'); tag(5, h); tag(330, rec); tag(100, 'AcDbEntity')
        if paper:
            tag(67, 1)
        tag(8, '0'); tag(100, 'AcDbBlockEnd')

    block_begin(h_ms_block, h_ms_rec, '*Model_Space', False); block_end(h_ms_end, h_ms_rec, False)
    block_begin(h_ps_block, h_ps_rec, '*Paper_Space', True); block_end(h_ps_end, h_ps_rec, True)
    for name, blk in root.blocks.items():
        rec = block_rec[name]
        block_begin(H.next(), rec, name, False, bool(getattr(blk, 'anonymous', False)))
        for e in blk.entities:
            write_entity(e, rec)
        block_end(H.next(), rec, False)
    tag(0, 'ENDSEC')

    # ------------------------------------------------------------ ENTITIES
    tag(0, 'SECTION'); tag(2, 'ENTITIES')
    for e in root.entities:
        write_entity(e, h_ms_rec)
    tag(0, 'ENDSEC')

    # ------------------------------------------------------------ OBJECTS
    tag(0, 'SECTION'); tag(2, 'OBJECTS')
    tag(0, 'DICTIONARY'); tag(5, h_root_dict); tag(330, 0); tag(100, 'AcDbDictionary'); tag(281, 1)
    tag(3, 'ACAD_GROUP'); tag(350, h_group_dict)
    tag(3, 'ACAD_LAYOUT'); tag(350, h_layout_dict)
    tag(3, 'ACAD_PLOTSTYLENAME'); tag(350, h_plot_dict)
    # the groups (a bar with its call-out, length, distribution dimension and dot as one selectable group): only the
    # entities that were written (model space) can be grouped; entities inside a block definition cannot
    in_model = {id(e) for e in root.entities}
    groups = []
    for g in (getattr(root, 'groups', None) or []):
        handles = [e['_h'] for e in g['entities'] if e.get('_h') and id(e) in in_model]
        if len(handles) > 1:
            groups.append({**g, 'handles': handles})
    h_groups = [H.next() for _ in groups]
    tag(0, 'DICTIONARY'); tag(5, h_group_dict); tag(330, h_root_dict); tag(100, 'AcDbDictionary'); tag(281, 1)
    for i, g in enumerate(groups):
        tag(3, g['name']); tag(350, h_groups[i])
    for i, g in enumerate(groups):
        tag(0, 'GROUP'); tag(5, h_groups[i]); tag(330, h_group_dict); tag(100, 'AcDbGroup'); tag(300, g.get('desc') or g['name']); tag(70, 0); tag(71, 1)
        for h in g['handles']:
            tag(340, h)
    tag(0, 'ACDBDICTIONARYWDFLT'); tag(5, h_plot_dict); tag(330, h_root_dict); tag(100, 'AcDbDictionary'); tag(281, 1)
    tag(3, 'Normal'); tag(350, h_placeholder); tag(100, 'AcDbDictionaryWithDefault'); tag(340, h_placeholder)
    tag(0, 'ACDBPLACEHOLDER'); tag(5, h_placeholder); tag(330, h_plot_dict)
    tag(0, 'DICTIONARY'); tag(5, h_layout_dict); tag(330, h_root_dict); tag(100, 'AcDbDictionary'); tag(281, 1)
    tag(3, 'Model'); tag(350, h_layout_model)
    tag(3, 'Layout1'); tag(350, h_layout_paper)

    def layout(h, name, rec, order, flags):
        tag(0, 'LAYOUT'); tag(5, h); tag(330, h_layout_dict)
        tag(100, 'AcDbPlotSettings'); tag(1, ''); tag(2, 'none_device'); tag(4, ''); tag(6, '')
        tag(40, 0); tag(41, 0); tag(42, 0); tag(43, 0); tag(44, 0); tag(45, 0); tag(46, 0); tag(47, 0); tag(48, 0); tag(49, 0)
        tag(140, 0); tag(141, 0); tag(142, 1); tag(143, 1); tag(70, flags); tag(72, 0); tag(73, 0); tag(74, 5); tag(7, ''); tag(75, 16)
        tag(147, 1); tag(148, 0); tag(149, 0)
        tag(100, 'AcDbLayout'); tag(1, name); tag(70, 1); tag(71, order)
        tag(10, 0); tag(20, 0); tag(11, 12); tag(21, 9); tag(12, 0); tag(22, 0); tag(32, 0)
        tag(14, 0); tag(24, 0); tag(34, 0); tag(15, 0); tag(25, 0); tag(35, 0); tag(146, 0)
        tag(13, 0); tag(23, 0); tag(33, 0); tag(16, 1); tag(26, 0); tag(36, 0); tag(17, 0); tag(27, 1); tag(37, 0); tag(76, 0)
        tag(330, rec)

    layout(h_layout_model, 'Model', h_ms_rec, 0, 1712)
    layout(h_layout_paper, 'Layout1', h_ps_rec, 1, 688)
    tag(0, 'ENDSEC')
    tag(0, 'EOF')

    # Patch the real HANDSEED now that we know it.
    seed = format(H.n + 1, 'X')
    idx = L.index('$HANDSEED')
    L[idx + 2] = seed
    return '\n'.join(L) + '\n'
