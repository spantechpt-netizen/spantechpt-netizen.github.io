"""
Composes the drawing package in the reference drafting convention:
  - one representative bar per group, pieces along the run with the lap
    of the next piece drawn offset, call-out `9T12@400-T2-05-(L=11300)`
    above the bar, straight length below, hook leg at hooked ends;
  - one plan per reinforcement layer (T1/T2, B1/B2) side by side;
  - mesh labels `Ø12@200-B1` per zone; columns solid, walls hatched,
    slab edge and beams green, openings crossed, sunken slabs hatched.
Each sheet is a block in its own Canvas so it can be written as a
stand-alone DXF (Xref) and also collected into the package DXF.
(Port of shopdrawings/lib/sheets.mjs.)
"""
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from .canvas import Canvas, opts, js_str
from .sheet import Sheet, choose_scale, layout_for, DEFAULT_FRAME  # noqa: F401  (DEFAULT_FRAME imported as in JS)
from . import rebar as R
from . import details as D
from . import ram_concept as RC
from .geometry import bbox, expand_bbox, edges, rect_polygon, circle_polygon, dist, point_in_polygon, centroid, polygon_area, js_round, fmt_num, to_fixed
from .beam_strips import size50, beam_spans

# The office distribution-dimension style (DIM100): the value on the line, no extension lines.
DIM_ZONE = {'txt': 250, 'asz': 150, 'tsz': 150, 'exo': 0, 'exe': 0, 'gap': 70, 'tad': 1, 'clrt': 3, 'clrd': 256, 'clre': 256, 'dec': 0, 'txsty': 'BW', 'se1': True, 'se2': True}


# ------------------------------------------------------------------ small JS helpers
_s = js_str  # JS `String(v)` / template interpolation


def _locale(v):
    """JS `Number.prototype.toLocaleString('en-US')`: thousands separators, up to three decimals."""
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, int):
        return f'{v:,}'
    d = Decimal(repr(float(v))).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)
    s = format(d, ',f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s


def _is_obj(v):
    return isinstance(v, (dict, list))


def _uniq(items):
    """JS `[...new Set(items)]`: primitives by value, records by identity, first occurrence kept."""
    out = []
    for it in items:
        if _is_obj(it):
            if not any(x is it for x in out):
                out.append(it)
        elif not any((not _is_obj(x)) and x == it and type(x) is type(it) for x in out):
            out.append(it)
    return out


def _js_join(items, sep=','):
    """JS `Array.prototype.join`: null / undefined print empty, a record prints `[object Object]`."""
    out = []
    for it in items:
        if it is None:
            out.append('')
        elif isinstance(it, dict):
            out.append('[object Object]')
        elif isinstance(it, list):
            out.append(_js_join(it, ','))
        else:
            out.append(js_str(it))
    return sep.join(out)


def _js_number(s):
    """JS `Number(string)`: None for NaN."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return s
    s = str(s).strip()
    if s == '':
        return 0
    try:
        v = float(s)
    except ValueError:
        return None
    return int(v) if v == int(v) and abs(v) < 1e15 else v


def _index_of(arr, item):
    for i, x in enumerate(arr):
        if x is item:
            return i
    return -1


def _pad2(n):
    return str(n).rjust(2, '0')


def _upper(s):
    return js_str(s).upper()


def _ang(u):
    return (math.atan2(u['y'], u['x']) * 180) / math.pi


def _rot_of(uy, ux):
    """The text rotation of a bar / edge: reads left-to-right / bottom-to-top."""
    rot = (math.atan2(uy, ux) * 180) / math.pi
    if rot > 90.5 or rot <= -89.5:
        rot += 180
    return rot


def column_polygon(c):
    """Column outline as a polygon (rotated columns supported)."""
    if c.get('shape') == 'circle':
        return circle_polygon(c['cx'], c['cy'], c['d'] / 2, 24)
    a = ((c.get('angle') or 0) * math.pi) / 180
    cs, sn = math.cos(a), math.sin(a)
    return [{'x': c['cx'] + x * cs - y * sn, 'y': c['cy'] + x * sn + y * cs}
            for x, y in [[-c['w'] / 2, -c['h'] / 2], [c['w'] / 2, -c['h'] / 2], [c['w'] / 2, c['h'] / 2], [-c['w'] / 2, c['h'] / 2]]]


SHEET_DEFS = [
    {'key': 'framing', 'base': 'FRAMING_FORMWORK_NOTATION', 'title': 'FRAMING / FORMWORK NOTATION PLAN', 'no': '01'},
    {'key': 'bottom', 'base': 'FRAMING_REBAR_SLAB_PT_BOTTOM', 'title': 'BOTTOM REINFORCEMENT PLAN (B1 / B2)', 'no': '02', 'plans': 2},
    {'key': 'top', 'base': 'FRAMING_REBAR_ADDITIONAL_AT_COLUMNS', 'title': 'ADDITIONAL TOP REINFORCEMENT OVER COLUMNS (T1 / T2)', 'no': '03', 'plans': 2},
    # only when the input is a RAM Concept model: the designed bands as additional reinforcement
    {'key': 'addbottom', 'base': 'FRAMING_REBAR_ADDITIONAL_BOTTOM_RAM', 'title': 'ADDITIONAL BOTTOM REINFORCEMENT (ADD.B1 / ADD.B2) - RAM DESIGN', 'no': '02A', 'plans': 2, 'ramOnly': True},
    {'key': 'addtop', 'base': 'FRAMING_REBAR_ADDITIONAL_TOP_RAM', 'title': 'ADDITIONAL TOP REINFORCEMENT (ADD.T1 / ADD.T2) - RAM DESIGN', 'no': '03A', 'plans': 2, 'ramOnly': True},
    {'key': 'ubars', 'base': 'FRAMING_REBAR_U_BARS_AROUND_REGIONS', 'title': 'U-BARS AT SLAB EDGES AND AROUND CIRCULAR REGIONS', 'no': '04'},
    {'key': 'voids', 'base': 'FRAMING_REBAR_AROUND_VOIDS_ACUARS', 'title': 'REINFORCEMENT AROUND VOIDS / ACUARS AND SUNKEN SLABS', 'no': '05'},
    {'key': 'openings', 'base': 'FRAMING_REBAR_AROUND_OPENINGS', 'title': 'REINFORCEMENT AROUND OPENINGS', 'no': '06'},
    {'key': 'cables', 'base': 'CABLES_SCHEDULE_EMPTY_TEMPLATE', 'title': 'PT CABLES LAYOUT AND SCHEDULE - EMPTY TEMPLATE', 'no': '07', 'drawingOnly': True},
    # from a RAM model the cables come one direction per sheet, with the chair heights along every tendon (no tendon sections)
    {'key': 'cables_lat', 'base': 'CABLES_LATITUDE_SHOP', 'title': 'PT CABLES - LATITUDE (DIRECTION 1) - LAYOUT, CHAIRS AND SCHEDULE', 'no': '07A', 'ramOnly': True, 'set': 'latitude'},
    {'key': 'cables_lon', 'base': 'CABLES_LONGITUDE_SHOP', 'title': 'PT CABLES - LONGITUDE (DIRECTION 2) - LAYOUT, CHAIRS AND SCHEDULE', 'no': '07B', 'ramOnly': True, 'set': 'longitude'},
    {'key': 'cables_cross', 'base': 'CABLES_CROSSINGS_SHOP', 'title': 'PT CABLES - TENDON CROSSINGS - WHICH TENDON PASSES OVER', 'no': '07C', 'ramOnly': True},
    {'key': 'punching', 'base': 'FRAMING_REBAR_PUNCHING_LINKS', 'title': 'PUNCHING SHEAR REINFORCEMENT PLAN (PRELIMINARY)', 'no': '08'},
    # from a RAM model calculated with one design strip per beam: the beams typed, marked and scheduled
    {'key': 'beams', 'base': 'BEAM_MARKS_SECTIONS_SCHEDULE', 'title': 'BEAM MARKS, SECTIONS AND REINFORCEMENT SCHEDULE - RAM DESIGN', 'no': '09', 'ramOnly': True, 'needsBeams': True},
]
SHEETS = SHEET_DEFS

SCHEDULE_COLS = [
    {'key': 'mark', 'title': 'MARK', 'w': 17},
    {'key': 'dia', 'title': 'Ø', 'w': 8},
    {'key': 'shape', 'title': 'SHAPE', 'w': 13},
    {'key': 'spacing', 'title': 'SPAC.', 'w': 12},
    {'key': 'length', 'title': 'LENGTH\n(mm)', 'w': 17},
    {'key': 'qty', 'title': 'QTY', 'w': 13},
    {'key': 'total_m', 'title': 'TOTAL\n(m)', 'w': 16},
    {'key': 'weight_kg', 'title': 'WT.\n(kg)', 'w': 17},
    {'key': 'zones', 'title': 'ZONES / REMARKS', 'w': 72, 'align': 'L', 'max': 44},
]

CALL_H, LEN_H, HOOK_H = 2.1, 1.7, 1.5
REBAR_STYLE = 'SPAN-REBAR'


def fmt_mm(v):
    return _locale(js_round(v))


fmtMM = fmt_mm  # noqa: N816  (the JS export name)


def _region_box(o):
    return R.region_bbox(o)


def _size_of(o):
    if o.get('kind') == 'circle':
        return f"Ø{fmt_mm(2 * o['r'])}"
    if o.get('kind') == 'rect':
        return f"{fmt_mm(o['rect']['w'])} x {fmt_mm(o['rect']['h'])}"
    rb = _region_box(o)
    return f"{fmt_mm(rb['w'])} x {fmt_mm(rb['h'])} (POLY)"


def totals_line(tot):
    return f"TOTAL {_locale(tot['weight_kg'])} kg  ·  " + '  '.join(f"Ø{_s(d['dia'])}: {_s(d['total_m'])} m" for d in tot['byDia'])


def grid_ref(level, b):
    """"B-C / 2-3" style reference for a region."""
    def near(arr, key, v):
        best = None
        for g in arr:
            if abs(g[key] - v) < abs((best[key] if best else math.inf) - v):
                best = g
        return best
    x1, x2 = near(level['grid']['x'], 'x', b['minX']), near(level['grid']['x'], 'x', b['maxX'])
    y1, y2 = near(level['grid']['y'], 'y', b['minY']), near(level['grid']['y'], 'y', b['maxY'])
    xs = (x1['label'] if x1 is x2 else f"{x1['label']}-{x2['label']}") if x1 and x2 else ''
    ys = (y1['label'] if y1 is y2 else f"{y1['label']}-{y2['label']}") if y1 and y2 else ''
    return f'{xs} / {ys}'


# ------------------------------------------------------------------ base plan
def draw_base(sheet, pl, level, o=None, **kw):
    o = opts(o, kw)
    S = sheet.S
    ob = level['bbox']
    bubble_r = 4 * S
    tag = o.get('gridTag')

    def bubble(x, y, label):
        pl.circle({'x': x, 'y': y}, bubble_r, {'layer': 'GRID-BUBBLE'})
        pl.text({'x': x, 'y': y + 0.6 * S if tag else y}, label, {'layer': 'TEXT', 'h': 3, 'align': 'C', 'valign': 'M', 'bold': True})
        if tag:
            pl.text({'x': x, 'y': y - 2.2 * S}, tag, {'layer': 'TEXT-TITLE', 'h': 1.4, 'align': 'C', 'valign': 'M'})

    for g in level['grid']['x']:
        pl.line({'x': g['x'], 'y': ob['minY'] - 3000}, {'x': g['x'], 'y': ob['maxY'] + 3000}, {'layer': 'GRID'})
        bubble(g['x'], ob['maxY'] + 3000 + bubble_r, g['label'])
        bubble(g['x'], ob['minY'] - 3000 - bubble_r, g['label'])
    for g in level['grid']['y']:
        pl.line({'x': ob['minX'] - 3000, 'y': g['y']}, {'x': ob['maxX'] + 3000, 'y': g['y']}, {'layer': 'GRID'})
        bubble(ob['minX'] - 3000 - bubble_r, g['y'], g['label'])
        bubble(ob['maxX'] + 3000 + bubble_r, g['y'], g['label'])
    gx, gy = level['grid']['x'], level['grid']['y']
    if o.get('dims') is not False:
        for i in range(len(gx) - 1):
            pl.dim({'x': gx[i]['x'], 'y': ob['minY'] - 5200}, {'x': gx[i + 1]['x'], 'y': ob['minY'] - 5200}, -6, {'h': 1.8})
        if len(gx) > 1:
            pl.dim({'x': gx[0]['x'], 'y': ob['minY'] - 5200}, {'x': gx[-1]['x'], 'y': ob['minY'] - 5200}, -12, {'h': 1.8})
        for i in range(len(gy) - 1):
            pl.dim({'x': ob['maxX'] + 5200, 'y': gy[i]['y']}, {'x': ob['maxX'] + 5200, 'y': gy[i + 1]['y']}, -6, {'h': 1.8})
        if len(gy) > 1:
            pl.dim({'x': ob['maxX'] + 5200, 'y': gy[0]['y']}, {'x': ob['maxX'] + 5200, 'y': gy[-1]['y']}, -12, {'h': 1.8})
    # slab outline, beams, walls, thickened zones, stairs
    # walls below first so a wall on the slab edge does not hide the green edge line
    for w in level.get('walls') or []:
        # (hatch dense enough to read as a wall at 1:150: 0.25 mm on paper between the lines)
        if w.get('polygon'):
            pl.pline(w['polygon'], {'layer': 'WALL', 'closed': True})
            pl.hatch([w['polygon']], {'layer': 'WALL-HATCH', 'pattern': 'ANSI31', 'spacing': 0.25})
        else:
            pl.line(w['a'], w['b'], {'layer': 'WALL'})
    pl.pline(level['outline'], {'layer': 'OUTLINE', 'closed': True, 'color': 3})
    for bm in level.get('beams') or []:
        if bm.get('polygon') and not bm.get('band'):
            pl.pline(bm['polygon'], {'layer': 'BEAM', 'closed': True})
            # the beam's name beside it (above a horizontal beam, left of a vertical one - never inside it), once per
            # span between the columns / walls crossing it: a support divides the beam, so one RAM beam with a column
            # in it reads as separate beams either side
            if o.get('regionLabels'):
                sp = beam_spans(bm, level.get('columns') or [], level.get('walls') or [], level.get('beams') or [])
                rot = 0 if sp['alongX'] else 90
                # a beam typed in the beam schedule reads its type mark with its section, its bars written on the other side
                bsch = level.get('beamSchedule') or {}
                rec = next((b for b in (bsch.get('beams') or []) if b['id'] == bm['id']), None)
                size = f"{_s(size50(bm.get('t')))}{('x' + _s(size50(bm['depth']))) if bm.get('depth') else ''}"
                label = f"{bm['id']} [{rec['mark']}] BEAM {size}" if rec and rec.get('mark') else f"{bm['id']} BEAM {size}"
                chk = next((x for x in ((bsch.get('office') or {}).get('beams') or []) if _upper(x['id']) == _upper(bm['id'])), None)
                bars_text = None
                if rec:
                    if rec.get('mark'):
                        bars_text = f"{(rec.get('top') or {}).get('text') or '-'} / {(rec.get('bottom') or {}).get('text') or '-'} / {(rec.get('stirrups') or {}).get('text') or '-'}"
                    else:
                        bars_text = 'NOT DESIGNED' + (' IN RAM' if bsch.get('design') == 'ram' else '')
                    if chk and chk.get('status') == 'fail':
                        bars_text += f" - NOT PASSING ({', '.join(chk['reasons'] if len(chk['reasons']) else ['RAM']).upper()})"
                if rec:
                    pl.hatch([bm['polygon']], {'layer': 'BEAM' if rec.get('mark') else 'CALLOUT', 'pattern': 'ANSI31', 'spacing': 1.2})
                off = (bm.get('t') or 300) / 2 + 350
                side = {'x': 0, 'y': 1} if sp['alongX'] else {'x': -1, 'y': 0}
                H = 1.8

                def width_of(text):
                    return len(text) * H * sheet.S * 0.9  # the label's length on the plan (model mm)
                longest = None
                for span in sp['spans']:
                    if longest is None or span['length'] > longest['length']:
                        longest = span
                for span in sp['spans']:
                    t0 = span['t0'] + (span['support0']['along'] / 2 if span.get('support0') else 0)
                    t1 = span['t1'] - (span['support1']['along'] / 2 if span.get('support1') else 0)
                    if t1 - t0 < 1200:
                        continue
                    # a short span between two supports takes the mark alone, so neighbouring labels never run into each other
                    text = label if width_of(label) + 300 <= t1 - t0 else bm['id'] if width_of(bm['id']) + 300 <= t1 - t0 else None
                    if not text:
                        continue
                    m = {'x': bm['a']['x'] + sp['u']['x'] * (t0 + t1) / 2, 'y': bm['a']['y'] + sp['u']['y'] * (t0 + t1) / 2}
                    at = {'x': m['x'] + side['x'] * off, 'y': m['y'] + side['y'] * off}
                    if not point_in_polygon(at, level['outline']):
                        at = {'x': m['x'] - side['x'] * off, 'y': m['y'] - side['y'] * off}  # an edge beam: the label on the slab side
                    pl.text(at, text, {'layer': 'BEAM', 'h': H, 'align': 'C', 'valign': 'M', 'rot': rot})
                    # the bars of the type on the other side of the beam (once, on the longest span)
                    if bars_text and span is longest and (width_of(bars_text) * 0.85 + 300 <= t1 - t0 or 'NOT PASSING' in bars_text or 'NOT DESIGNED' in bars_text):
                        other = {'x': m['x'] - (at['x'] - m['x']), 'y': m['y'] - (at['y'] - m['y'])}
                        pl.text(other, bars_text, {'layer': 'TEXT', 'h': 1.6, 'align': 'C', 'valign': 'M', 'rot': rot})
        elif not bm.get('polygon'):
            pl.line(bm['a'], bm['b'], {'layer': 'BEAM'})
    if o.get('thickZones') is not False:
        for z in level.get('thickZones') or []:
            pl.pline(z['polygon'], {'layer': 'SLAB-THK', 'closed': True})
            pl.hatch([z['polygon']], {'layer': 'SLAB-THK-HATCH', 'pattern': 'ANSI31', 'spacing': 3})
            # the office look of a drop on the framing plan: `THK=400` in the zone's lower-left corner (no id, clear of the
            # column at its centre) and the zone's two sizes dimensioned inside it - the width along its top edge, the
            # height along its right edge (DIM100 style, the value on the line)
            if o.get('regionLabels'):
                zb = bbox(z['polygon'])
                pl.text({'x': zb['minX'] + 300, 'y': zb['minY'] + 250}, f"THK={_s(z['thickness'])}" if z.get('thickness') else 'DROP', {'layer': 'SLAB-THK', 'h': 2.2, 'align': 'L', 'valign': 'B'})
                inset = min(700, zb['h'] / 4, zb['w'] / 4)
                top, right = {'y': zb['maxY'] - inset}, {'x': zb['maxX'] - inset}
                pl.dimension({'x': zb['minX'], 'y': top['y']}, {'x': zb['maxX'], 'y': top['y']}, {'x': zb['minX'], 'y': top['y']}, {'style': 'DIM100', 'styleDef': DIM_ZONE, 'layer': 'diamension', 'text': _s(js_round(zb['w']))})
                pl.dimension({'x': right['x'], 'y': zb['minY']}, {'x': right['x'], 'y': zb['maxY']}, {'x': right['x'], 'y': zb['minY']}, {'style': 'DIM100', 'styleDef': DIM_ZONE, 'layer': 'diamension', 'text': _s(js_round(zb['h']))})
    # pour strips: dashed outline, light hatch, label on the framing plan only
    if o.get('pourStrips') is not False:
        for ps in level.get('pourStrips') or []:
            pl.pline(ps['polygon'], {'layer': 'POUR-STRIP', 'closed': True})
            pl.hatch([ps['polygon']], {'layer': 'POUR-STRIP-HATCH', 'pattern': 'ANSI37', 'spacing': 2.5})
            # (office rule: the strip is named, its width is not written on the plan - the hatch shows it; the width stays in the element list)
            if o.get('regionLabels'):
                b = bbox(ps['polygon'])
                vertical = b['h'] > b['w']
                pl.text({'x': b['cx'], 'y': b['cy']}, f"{ps['id']} POUR STRIP", {'layer': 'POUR-STRIP', 'h': 1.5, 'align': 'C', 'valign': 'M', 'rot': 90 if vertical else 0})
    # level tags
    if o.get('regionLabels'):
        for t in level.get('levelTags') or []:
            pl.text({'x': t['x'], 'y': t['y']}, f"{_s(t['label'])} {_s(t['value'])}", {'layer': 'LEVEL', 'h': 1.8, 'align': 'C', 'valign': 'M'})
    if o.get('stairs') is not False:
        for st in level.get('stairs') or []:
            pl.pline(st['pts'], {'layer': 'STAIR', 'closed': bool(st.get('closed'))})
    # PT zones
    if o.get('pt') is not False:
        for z in level['pt']['zones']:
            pl.pline(z['polygon'], {'layer': 'PT-ZONE', 'closed': True})
            zb = bbox(z['polygon'])
            pl.text({'x': zb['minX'] + 600, 'y': zb['maxY'] - 900}, f"{z['id']} - PT SLAB ZONE", {'layer': 'PT-ZONE', 'h': 2.2})
    # columns: solid black (rotated columns drawn as polygons)
    for c in level['columns']:
        poly = column_polygon(c)
        if c.get('shape') == 'circle':
            pl.circle({'x': c['cx'], 'y': c['cy']}, c['d'] / 2, {'layer': 'COLUMN'})
        else:
            pl.pline(poly, {'layer': 'COLUMN', 'closed': True})
        pl.hatch([poly], {'layer': o.get('columnHatchLayer') or 'COLUMN-HATCH', 'pattern': 'SOLID'})  # solid grey, by layer (the office's s-hatch look)
        # (office rule: column ids are not written on the plans - the grid reference locates a column; the ids live in the schedules and notes)
    # openings: crossed
    for op in level['openings']:
        poly = R.polygon_of(op)
        pl.pline(poly, {'layer': 'OPENING', 'closed': True})
        b = bbox(poly)
        if op.get('kind') != 'circle':
            pl.line({'x': b['minX'], 'y': b['minY']}, {'x': b['maxX'], 'y': b['maxY']}, {'layer': 'OPENING'})
            pl.line({'x': b['maxX'], 'y': b['minY']}, {'x': b['minX'], 'y': b['maxY']}, {'layer': 'OPENING'})
        # (office rule: an opening is not labelled on the plan - the crossed outline says what it is; its id and size stay in the element list)
    # voids
    for v in level['voids']:
        poly = R.polygon_of(v)
        pl.pline(poly, {'layer': 'VOID', 'closed': True})
        pl.hatch([poly], {'layer': 'VOID-HATCH', 'pattern': 'ANSI37', 'spacing': 2.5})
        b = bbox(poly)
        if o.get('regionLabels'):
            pl.text({'x': b['cx'], 'y': b['maxY'] + 200}, f"{v['id']} VOID {_size_of(v)}", {'layer': 'VOID', 'h': 1.5, 'align': 'C'})
    # sunken slabs
    for sk in level.get('sunken') or []:
        poly = R.polygon_of(sk)
        pl.pline(poly, {'layer': 'SUNKEN', 'closed': True})
        pl.hatch([poly], {'layer': 'SUNKEN-HATCH', 'pattern': 'ANSI31', 'spacing': 1.5})
        if o.get('regionLabels'):
            c = centroid(poly)
            step = sk.get('step')
            pl.text({'x': c['x'], 'y': c['y'] + 120}, f"{sk['id']} {'RAISED' if step > 0 else 'SUNKEN'} ZONE T.O.S {_s(sk.get('tos'))}" if step else f"{sk['id']} SUNKEN SLAB", {'layer': 'SUNKEN', 'h': 1.4, 'align': 'C'})
            pl.text({'x': c['x'], 'y': c['y'] - 150}, f"STEP {'+' if step > 0 else ''}{_s(step)} mm" if step else f"TH={_s(sk.get('thickness') or '?')}mm", {'layer': 'SUNKEN', 'h': 1.4, 'align': 'C'})
    # circular U-bar regions
    if o.get('ubarRegions') is not False:
        for u in level['ubar']['circles']:
            if not u.get('fromOpening'):
                pl.circle({'x': u['cx'], 'y': u['cy']}, u['r'], {'layer': 'REBAR-U', 'ltype': 'DASHDOT'})
            if o.get('regionLabels'):
                pl.text({'x': u['cx'], 'y': u['cy'] - u['r'] - 700}, f"{u['id']} U-BAR REGION Ø{fmt_mm(2 * u['r'])}", {'layer': 'REBAR-U', 'h': 1.5, 'align': 'C'})


# ------------------------------------------------------------------ bar drafting
def _draw_run(pl, S, o=None, **kw):
    """
    A run of bars in the reference convention. `a`→`b` is the bar axis at
    true length; `pieces` are cutting lengths; hooks at `hooks.start` /
    `hooks.end`. The lap of every following piece is drawn offset.
    """
    o = opts(o, kw)
    a, b, pieces, lap = o['a'], o['b'], o['pieces'], o['lap']
    hooks = o.get('hooks') or {}
    hook_leg = o.get('hookLeg') or 0
    hook_label = o.get('hookLabel')
    hook_labels = o.get('hookLabels') or {}
    label = o['label']
    layer = o.get('layer') or 'REBAR'
    offset_side = o['offsetSide'] if o.get('offsetSide') is not None else 1
    text_side = o['textSide'] if o.get('textSide') is not None else 1
    L = dist(a, b) or 1
    ux, uy = (b['x'] - a['x']) / L, (b['y'] - a['y']) / L
    nx, ny = -uy, ux

    def at(s, off=0):
        return {'x': a['x'] + ux * s + nx * off, 'y': a['y'] + uy * s + ny * off}
    rot0 = (math.atan2(uy, ux) * 180) / math.pi
    rot = rot0
    if rot > 90.5 or rot <= -89.5:
        rot += 180
    flip = -1 if rot != rot0 else 1  # text reads left-to-right / bottom-to-top
    tn = text_side * flip
    pos = 0
    last = len(pieces) - 1
    straights = [cut - (hook_leg if i == 0 and hooks.get('start') else 0) - (hook_leg if i == last and hooks.get('end') else 0) for i, cut in enumerate(pieces)]
    for i in range(last + 1):
        s0 = 0 if i == 0 else pos - lap
        s1 = s0 + straights[i]
        axis_start = s0 if i == 0 else min(s0 + lap, s1)
        pl.line(at(axis_start), at(s1), {'layer': layer})
        if i > 0:
            pl.line(at(s0, offset_side * 150), at(axis_start, offset_side * 150), {'layer': layer})
        if i == 0 and hooks.get('start'):
            pl.line(at(0), at(0, -offset_side * 250), {'layer': layer})
        if i == last and hooks.get('end'):
            pl.line(at(s1), at(s1, -offset_side * 250), {'layer': layer})
        mid = (axis_start + s1) / 2
        pl.text(at(mid, tn * 0.55 * S), label(i, pieces[i], straights[i]), {'layer': 'REBAR-TEXT', 'style': REBAR_STYLE, 'h': CALL_H, 'rot': rot, 'align': 'C', 'valign': 'B'})
        pl.text(at(mid, -tn * (LEN_H + 0.5) * S), _s(js_round(straights[i])), {'layer': 'REBAR-TEXT', 'style': REBAR_STYLE, 'h': LEN_H, 'rot': rot, 'align': 'C', 'valign': 'B'})
        if i == 0 and hooks.get('start'):
            pl.text(at(-0.4 * S, tn * 0.55 * S), hook_labels.get('start') or hook_label or _s(hook_leg), {'layer': 'REBAR-TEXT', 'style': REBAR_STYLE, 'h': HOOK_H, 'rot': rot, 'align': 'R', 'valign': 'B'})
        if i == last and hooks.get('end'):
            pl.text(at(s1 + 0.4 * S, tn * 0.55 * S), hook_labels.get('end') or hook_label or _s(hook_leg), {'layer': 'REBAR-TEXT', 'style': REBAR_STYLE, 'h': HOOK_H, 'rot': rot, 'align': 'L', 'valign': 'B'})
        pos = s1
    pl.bar_ends(at(0), at(pos), {'layer': layer, 'size': 0.6})


def _callout(n, dia, spacing, mark, len_):
    return f"{_s(n)}T{_s(dia)}{('@' + _s(spacing)) if spacing else ''}-{_s(mark)}-(L={_s(len_)})"


def band_code(b):
    """Office layer code of a band: 1 = bars parallel to the numbered grids (Y), 2 = parallel to the lettered grids (X)."""
    bars = b['bars']
    rep = bars[len(bars) // 2] if bars else {'a': b['p0'], 'b': b['p1']}
    return 1 if abs(rep['b']['y'] - rep['a']['y']) > abs(rep['b']['x'] - rep['a']['x']) else 2


def _draw_ram_bands(pl, S, level, spec, face, plans):
    """
    Designed bands from RAM Concept: one representative bar (the middle one)
    per band, pieces split at stock length, hooks where a bar ends at the
    slab edge. Returns the bar lists per layer code.
    """
    lists = {1: R.BarList(f'ADD.{face}1'), 2: R.BarList(f'ADD.{face}2')}
    bands = [b for b in level['ram']['bands'] if b['face'] == face]

    def near_edge(p):
        for ed in edges(level['outline']):
            L = ed['length'] or 1
            t = max(0, min(1, ((p['x'] - ed['a']['x']) * ed['dx'] + (p['y'] - ed['a']['y']) * ed['dy']) / (L * L)))
            if dist(p, {'x': ed['a']['x'] + ed['dx'] * t, 'y': ed['a']['y'] + ed['dy'] * t}) < 250:
                return True
        return False
    k = 0
    for b in bands:
        code = band_code(b)
        pen = plans.get(code)
        if not pen or not len(b['bars']):
            continue
        rep = b['bars'][len(b['bars']) // 2]
        hooks = {'start': near_edge(rep['a']) or b['ends'][0] != 1, 'end': near_edge(rep['b']) or b['ends'][1] != 1}
        u_end = R.top_edge_end(level, spec) if face == 'T' else None  # top bars end in a U (500 bottom leg) at the edge
        hk = u_end['leg'] if u_end else R.hook_leg(b['dia'])
        straight = dist(rep['a'], rep['b'])
        cut = math.ceil((straight + (hk if hooks['start'] else 0) + (hk if hooks['end'] else 0)) / 10) * 10
        lap = R.lap_length(spec, b['dia'], top=face == 'T')
        pieces = R.split_run(cut, stock=spec['stock'], lap=lap) if cut > spec['stock'] else [cut]
        shape = 'STR' if len(pieces) > 1 else ('UU' if u_end else 'C') if hooks['start'] and hooks['end'] else ('U' if u_end else 'L') if hooks['start'] or hooks['end'] else 'STR'
        note = (u_end['note'] if u_end else f'hook {_s(hk)}') if hooks['start'] or hooks['end'] else ''
        marks = [lists[code].add({'dia': b['dia'], 'shape': shape, 'length': ln, 'qty': b['count'], 'spacing': b['spacing'], 'zone': b['id'], 'note': note}) for ln in pieces]
        side = -1 if k % 2 else 1
        k += 1
        _draw_run(pen, S, {'a': rep['a'], 'b': rep['b'], 'pieces': pieces, 'lap': lap, 'hooks': {} if len(pieces) > 1 else hooks, 'hookLeg': hk, 'hookLabel': u_end['label'] if u_end else None, 'layer': f'REBAR-{face}{code}', 'textSide': side, 'offsetSide': side,
                            'label': lambda i, c, *_, b=b, marks=marks: _callout(b['count'], b['dia'], b['spacing'], marks[i]['mark'], c)})
        # band width as a light range line at the first and last bar
        first, last = b['bars'][0], b['bars'][-1]
        if len(b['bars']) > 1:
            pen.line(first['a'], first['b'], {'layer': 'REBAR-EXTENT', 'ltype': 'DASHED'})
            pen.line(last['a'], last['b'], {'layer': 'REBAR-EXTENT', 'ltype': 'DASHED'})
    return lists


def _hairpin(pl, p, n, leg, w=100, layer='REBAR-U'):
    """U-bar / hairpin symbol in plan at point p, legs along n (unit), width w."""
    t = {'x': -n['y'], 'y': n['x']}
    a = {'x': p['x'] + t['x'] * w / 2, 'y': p['y'] + t['y'] * w / 2}
    b = {'x': p['x'] - t['x'] * w / 2, 'y': p['y'] - t['y'] * w / 2}
    pl.pline([{'x': a['x'] + n['x'] * leg, 'y': a['y'] + n['y'] * leg}, a, b, {'x': b['x'] + n['x'] * leg, 'y': b['y'] + n['y'] * leg}], {'layer': layer})


def common_notes(model, level):
    spec = model['spec']
    src = spec['sources']
    return [
        'ALL DIMENSIONS ARE IN MILLIMETRES, LEVELS IN METRES UNLESS NOTED OTHERWISE. DO NOT SCALE; FOLLOW THE WRITTEN DIMENSIONS.',
        f"CONCRETE f'c = {_s(spec['fc'])} MPa ({_s(src['fc'])}). REINFORCEMENT: DEFORMED BARS fy = {_s(spec['fy'])} MPa ({_s(src['fy'])}). CLEAR COVER {_s(spec['cover'])} mm TOP AND BOTTOM ({_s(src['cover'])}).",
        f"SLAB THICKNESS {_s(level['thickness'])} mm. THIS SHEET IS TO BE READ WITH THE CONSULTANT'S STRUCTURAL DRAWINGS (G.A.) AND THE PT LAYOUT; DISCREPANCIES TO BE REFERRED TO THE ENGINEER BEFORE FABRICATION.",
        'BAR CALL-OUT: [No.] T[Ø] @[SPACING] - [LAYER-MARK] - (L = CUTTING LENGTH). STRAIGHT LENGTH IS WRITTEN UNDER THE BAR; A HOOK LEG IS WRITTEN AT THE HOOKED END. T1/T2 = TOP LAYERS, B1/B2 = BOTTOM LAYERS (1 = BARS PARALLEL TO THE NUMBERED GRIDS, 2 = PARALLEL TO THE LETTERED GRIDS).',
        'THE DRAWN BAR IS REPRESENTATIVE OF THE GROUP; THE NUMBER OF BARS IN THE CALL-OUT IS PLACED AT THE GIVEN SPACING ACROSS THE ZONE. A SHORT OFFSET LINE MARKS THE LAP OF THE FOLLOWING PIECE.',
        'TENSION LAPS ARE CLASS B (1.3 ld) PER SBC 304-18 §25.5.2, SO ALL BARS OF A ROW MAY LAP AT THE SAME SECTION. BARS ENDING AT A FREE EDGE TERMINATE WITH A STANDARD 90° HOOK (12 Ø) UNLESS NOTED.',
    ]


def _length_note(model, dias):
    return [f"Ø{_s(r['dia'])}: ld {_s(r['ld_bottom'])} (bot) / {_s(r['ld_top'])} (top) · LAP {_s(r['lap_bottom'])} (bot) / {_s(r['lap_top'])} (top) · ldh {_s(r['ldh'])}" for r in R.length_table(model['spec'], dias)]


def code_text(model):
    if model['spec']['sources'].get('code') == 'drawing':
        return f"{_s(model.get('code_reference'))} AS STATED ON THE STRUCTURAL DRAWINGS. DEVELOPMENT, ANCHORAGE AND LAP LENGTHS PER SBC 304-18 CHAPTER 25 (ACI 318-14 BASIS)."
    return 'SAUDI PRACTICE ASSUMED: SBC 304-18 (SAUDI BUILDING CODE - CONCRETE STRUCTURES, BASED ON ACI 318-14) FOR DEVELOPMENT, ANCHORAGE AND LAP LENGTHS. TO BE ADJUSTED ON RECEIPT OF THE FINAL DESIGN CRITERIA / CONSULTANT REQUIREMENTS.'


def level_assumptions(model, level):
    return [a['text'] for a in model['assumptions'] if not a.get('level') or a['level'] == level['id']]


def content_bbox(level):
    """
    The extent of everything a level's sheets draw: the slab outline with the walls, beams, columns, thickness zones,
    openings and tendons that reach beyond it (a wall or beam running past the slab edge, a tendon anchored outside).
    The sheet scale is picked on this, so the plan never runs out of the frame.
    """
    pts = list(level.get('outline') or [])
    for w in level.get('walls') or []:
        if w.get('polygon'):
            pts.extend(w['polygon'])
        elif w.get('a') and w.get('b'):
            pts.extend([w['a'], w['b']])
    for bm in level.get('beams') or []:
        if bm.get('a') and bm.get('b'):
            pts.extend([bm['a'], bm['b']])
    for c in level.get('columns') or []:
        r = max(c.get('w') or 0, c.get('h') or 0, c.get('d') or 0) / 2
        pts.extend([{'x': c['cx'] - r, 'y': c['cy'] - r}, {'x': c['cx'] + r, 'y': c['cy'] + r}])
    for z in list(level.get('thickZones') or []) + list(level.get('openings') or []):
        if z.get('polygon'):
            pts.extend(z['polygon'])
    for t in (level.get('ram') or {}).get('tendons') or []:
        pts.extend(t.get('pts') or [])
    b = bbox(pts) if len(pts) >= 2 else level['bbox']
    # nothing farther than a bay from the slab drives the scale (a stray reference entity must not shrink the plan)
    lim = expand_bbox(level['bbox'], 6000)
    return bbox([{'x': max(b['minX'], lim['minX']), 'y': max(b['minY'], lim['minY'])}, {'x': min(b['maxX'], lim['maxX']), 'y': min(b['maxY'], lim['maxY'])}])


def build_sheet(o=None, model=None, level=None, def_=None, meta=None, index=None, total=None, draw=None, **kw):
    """Build one sheet. `draw(sheet, pens)` returns { rows, cols, scheduleTitle, totals, general, legend, extra, detailsUsed }"""
    if o:
        model = o.get('model', model)
        level = o.get('level', level)
        def_ = o.get('def', o.get('def_', def_))
        meta = o.get('meta', meta)
        index = o.get('index', index)
        total = o.get('total', total)
        draw = o.get('draw', draw)
    def_ = kw.get('def', def_)
    root = Canvas()
    block_name = f"{def_['base']}_{level['id']}" if level else def_['base']
    frame_opts = meta.get('frame') or {}
    L = layout_for(frame_opts.get('size') or 'A1', frame_opts)

    # plan margin: room for the grid bubbles (3000 + 2 x 4S) plus a little air; the
    # scale is picked with a provisional margin and the margin re-fitted to it.
    def margin_for(sc):
        return 3000 + 8 * (sc / 100) + 400
    extent = content_bbox(level) if level else None
    pb = expand_bbox(extent, margin_for(200)) if level else None
    stacked = [{'x': L['plan']['x'], 'y': L['plan']['y'] + L['plan']['h'] / 2, 'w': L['plan']['w'], 'h': L['plan']['h'] / 2}, {'x': L['plan']['x'], 'y': L['plan']['y'], 'w': L['plan']['w'], 'h': L['plan']['h'] / 2}]

    def pick():
        areas = L['halves'] if def_.get('plans') == 2 else [L['plan']]
        if level and def_.get('plans') == 2 and choose_scale(pb, stacked[0]) < choose_scale(pb, L['halves'][0]):
            areas = stacked
        return areas
    areas = pick()
    scale = max(choose_scale(pb, a) for a in areas) if level else 100
    if level:
        pb = expand_bbox(extent, margin_for(scale))
        areas = pick()
        scale = max(choose_scale(pb, a) for a in areas)
    sheet = Sheet(root, block_name=block_name, scale=scale, frame=frame_opts)
    custom = isinstance(meta.get('frameEntities'), list) and len(meta['frameEntities']) > 0
    if not custom:
        sheet.frame()
    pens = [sheet.set_plan(pb, a) for a in areas] if level else []
    r = draw(sheet, pens) or {}
    drawing_no = f"{_s(meta.get('prefix'))}-{level['id']}-{def_['no']}" if level else f"{_s(meta.get('prefix'))}-000"

    leftover = []
    if r.get('rows') is not None and sheet.L['schedule']['h'] > 0:
        Sc = sheet.L['schedule']
        row_h = r.get('rowH') or 4
        max_rows = math.floor((Sc['h'] - 6 - 6 - 5 - 6) / row_h)
        res = sheet.table(Sc['x'], Sc['y'] + Sc['h'] - 3, r.get('cols') or SCHEDULE_COLS, r['rows'], {'title': r.get('scheduleTitle') or 'BAR BENDING SCHEDULE', 'maxRows': max_rows, 'rowH': row_h, 'h': min(1.7, r['rowH'] * 0.45) if r.get('rowH') else 1.7, 'totals': r.get('totals') or None})
        leftover = res['leftover']
        details_used = r['detailsUsed'] if r.get('detailsUsed') is not None else 3
        if len(leftover) and (details_used >= 3 or not (sheet.L['strip']['h'] > 0)):
            sheet.pp.text(Sc['x'] + 2, Sc['y'] + 1.5, f"+ {len(leftover)} MORE ROWS - SEE THE SCHEDULE FILE OF THIS SHEET", {'layer': 'SCHEDULE-TEXT', 'h': 1.6})
        elif len(leftover):
            used = details_used
            box = sheet.L['details'][min(used, 2)]
            sheet.pp.rect(box['x'], box['y'], box['w'], box['h'], {'layer': 'FRAME'})
            cols = [{**c, 'w': (c['w'] * (box['w'] - 6)) / 185} for c in (r.get('cols') or SCHEDULE_COLS)]
            res2 = sheet.table(box['x'] + 3, box['y'] + box['h'] - 3, cols, leftover, {'title': (r.get('scheduleTitle') or 'BAR BENDING SCHEDULE') + ' (CONT.)', 'maxRows': math.floor((box['h'] - 22) / row_h), 'rowH': row_h, 'h': min(1.7, r['rowH'] * 0.45) if r.get('rowH') else 1.7, 'totals': r.get('totals') or None})
            leftover = res2['leftover']
    if sheet.L['keyplan']['h'] > 0:
        sheet.key_plan(level['outline'] if level else (model['levels'][0]['outline'] if model['levels'] else None))
    sheet.notes({'general': r.get('general') or [], 'assumptions': r.get('assumptions') or [], 'codeRef': code_text(model), 'legend': r.get('legend') or [], 'extra': r.get('extra') or []})

    def lab(arr, i):
        return _s(arr[i]['label']) if arr else 'undefined'
    title_data = {
        **meta,
        'title': def_['title'],
        'level': f"{level['id']} - {level['name']}" if level else 'ALL LEVELS',
        'drawingNo': drawing_no,
        'sheet': f'{_s(index)} OF {_s(total)}',
        'scale': f'1:{_s(scale)} (DETAILS AS NOTED)' if level else 'N.T.S.',
        'gridRef': f"{lab(level['grid']['x'], 0)}-{lab(level['grid']['x'], -1)} / {lab(level['grid']['y'], 0)}-{lab(level['grid']['y'], -1)}" if level else 'ALL',
        'index': f"{_s(meta.get('prefix'))}-000",
        'codeRef': f"{model['code_reference']} (ON DRAWINGS)" if model.get('code_reference') else 'SBC 304-18 (ASSUMED)',
    }
    if custom:
        # the office's own frame carries the title block and references; the sheet's data fills its {TOKENS}
        sheet.custom_frame(meta['frameEntities'], {
            'PROJECT': (meta.get('project') or '').upper(), 'PROJECT_CODE': meta.get('projectCode') or '', 'CLIENT': meta.get('client') or '', 'CONSULTANT': meta.get('engineer') or '', 'ENGINEER': meta.get('engineer') or '', 'CONTRACTOR': meta.get('contractor') or '',
            'LOCATION': meta.get('location') or '', 'COMPANY': meta.get('company') or '', 'COMPANY_LINE': meta.get('company_line') or '', 'TITLE': def_['title'], 'LEVEL': title_data['level'], 'LEVEL_NAME': level['name'] if level else '', 'DRAWING_NO': drawing_no, 'REV': meta.get('revision') or '00',
            'DATE': meta.get('date') or '', 'SCALE': title_data['scale'], 'SHEET': title_data['sheet'], 'PREPARED': meta.get('prepared') or '', 'DESIGNER': meta.get('designer') or meta.get('prepared') or '', 'CHECKED': meta.get('checked') or '', 'APPROVED': meta.get('approved') or '', 'STATUS': meta.get('status') or '', 'GRID_REF': title_data['gridRef'], 'INDEX': title_data['index'], 'CODE_REF': title_data['codeRef'],
        })
    else:
        if sheet.L['refs']['h'] > 0:
            sheet.refs_block(meta)
        sheet.title_block(title_data)
    if level:
        titles = r.get('planTitles') or [def_['title']]
        for i, a in enumerate(areas):
            sheet.plan_title_at(a, i + 1, f"{level['name']} - {titles[i] if i < len(titles) and titles[i] else def_['title']}", f'SCALE : 1:{_s(scale)}')
    root.insert(block_name, 0, 0)
    return {'root': root, 'sheet': sheet, 'blockName': block_name, 'drawingNo': drawing_no, 'title': def_['title'], 'level': level['id'] if level else 'ALL', 'levelName': level['name'] if level else '', 'scale': scale, 'key': def_['key'], 'rows': r.get('rows') or [], 'csvCols': r.get('cols') or SCHEDULE_COLS, 'weight': r.get('weight') or 0, 'leftoverRows': len(leftover), 'checks': r.get('checks') or []}


def _summarise(items, key_of, row_of):
    """Group items by key when there are more than six of them; one schedule row per group."""
    if len(items) <= 6:
        return [row_of(it, key_of(it), 1, it['id'], [it]) for it in items]
    groups = {}
    for it in items:
        groups.setdefault(key_of(it), []).append(it)
    return [row_of(g[0], key_of(g[0]), len(g), f"{g[0]['id']}-{g[-1]['id']}" if len(g) > 1 else g[0]['id'], g) for g in groups.values()]


# ------------------------------------------------------------------ sheets
def _framing_sheet(model, level, meta):
    def draw(sheet, pens):
        pl = pens[0]
        spec = model['spec']
        draw_base(sheet, pl, level, {'regionLabels': True, 'gridTag': meta.get('gridTag')})
        thk_list = _uniq([z['thickness'] for z in (level.get('thickZones') or []) if z.get('thickness')])
        drops = len([z for z in (level.get('thickZones') or []) if not z.get('thickness')])
        pl.text({'x': level['bbox']['minX'] + 800, 'y': level['bbox']['minY'] - 1200},
                f"PT FLAT SLAB TH={_s(level['thickness'])}mm{(' T.O.S ' + _s(level['tos'])) if level.get('tos') else ''}{(' (THICKENED ZONES ' + ' / '.join(_s(t) for t in thk_list) + ' mm HATCHED)') if len(thk_list) else ''}{(' (' + _s(drops) + ' DROP PANELS HATCHED - DEPTH PER STRUCTURAL DRAWINGS)') if drops else ''}",
                {'layer': 'TEXT', 'h': 2.6, 'bold': True})
        for op in level['openings']:
            b = _region_box(op)
            pl.bubble({'x': b['maxX'], 'y': b['maxY']}, op['id'], {'dx': 7, 'dy': 7, 'layer': 'CALLOUT', 'r': 3, 'h': 1.6})
        for v in level['voids']:
            b = _region_box(v)
            pl.bubble({'x': b['minX'], 'y': b['maxY']}, v['id'], {'dx': -7, 'dy': 7, 'layer': 'CALLOUT', 'r': 3, 'h': 1.6})
        for u in level['ubar']['circles']:
            pl.bubble({'x': u['cx'], 'y': u['cy']}, u['id'], {'dx': 9, 'dy': -9, 'layer': 'CALLOUT'})

        def col_row(c):
            if c.get('shape') == 'circle':
                element, size = 'COLUMN (ROUND)', f"Ø{fmt_mm(c['d'])}"
            else:
                element = 'WALL / BLADE COL.' if c['w'] > 3 * c['h'] or c['h'] > 3 * c['w'] else 'COLUMN'
                size = f"{fmt_mm(c['w'])} x {fmt_mm(c['h'])}"
            return {'id': c['id'], 'element': element, 'size': size, 'location': f"X {fmt_mm(c['cx'])}, Y {fmt_mm(c['cy'])}"}

        def sunken_row(o):
            step = o.get('step')
            return {'id': o['id'], 'element': f"{'RAISED' if step > 0 else 'SUNKEN'} ZONE T.O.S {_s(o.get('tos'))} (STEP {_s(step)})" if step else f"SUNKEN SLAB TH={_s(o.get('thickness') or '?')}", 'size': _size_of(o), 'location': grid_ref(level, _region_box(o))}

        def thk_key(z):
            zb = bbox(z['polygon'])
            return (f"THK {_s(z['thickness'])}" if z.get('thickness') else 'DROP') + f" {fmt_mm(zb['w'])} x {fmt_mm(zb['h'])}"

        def thk_row(z, key, n, ids, all_):
            zb = bbox(z['polygon'])
            more = f' ({n} No.)' if n > 1 else ''
            return {'id': ids, 'element': f"THICKENED ZONE / BAND {_s(z['thickness'])} mm{more}" if z.get('thickness') else f"DROP PANEL (DEPTH PER STRUCT. DWG){more}", 'size': f"{fmt_mm(zb['w'])} x {fmt_mm(zb['h'])}", 'location': 'AT COLUMNS - SEE PLAN' if n > 1 else grid_ref(level, zb)}

        def wall_key(w):
            return f"T{js_round(w['t'] / 10) * 10}"

        def wall_row(w, key, n, ids, all_):
            return {'id': ids, 'element': f"WALL BELOW {fmt_mm(w['t'])} THK{(' (' + _s(n) + ' No.)') if n > 1 else ''}", 'size': f"{to_fixed(sum(x['length'] for x in all_) / 1000, 1)} m TOTAL" if n > 1 else f"{fmt_mm(w['t'])} x {fmt_mm(w['length'])}", 'location': 'SEE PLAN (HATCHED)' if n > 1 else grid_ref(level, bbox(w['polygon']))}
        walls = level.get('walls') or []
        line_walls = [w for w in walls if not w.get('polygon')]
        rows = [
            *[col_row(c) for c in level['columns']],
            *[{'id': o['id'], 'element': 'OPENING', 'size': _size_of(o), 'location': grid_ref(level, _region_box(o))} for o in level['openings']],
            *[{'id': o['id'], 'element': 'VOID / ACUAR', 'size': _size_of(o), 'location': grid_ref(level, _region_box(o))} for o in level['voids']],
            *[sunken_row(o) for o in (level.get('sunken') or [])],
            *_summarise(level.get('thickZones') or [], thk_key, thk_row),
            *[{'id': z['id'], 'element': 'POUR STRIP', 'size': f"{fmt_mm(z['width'])} x {fmt_mm(z['length'])}", 'location': grid_ref(level, bbox(z['polygon']))} for z in (level.get('pourStrips') or [])],
            *_summarise([w for w in walls if w.get('polygon')], wall_key, wall_row),
            *([{'id': 'W', 'element': 'WALLS BELOW (LINE SUPPORTS)', 'size': f"{to_fixed(sum(dist(w['a'], w['b']) for w in line_walls) / 1000, 1)} m", 'location': f"{len(line_walls)} SEGMENTS"}] if level.get('walls') and line_walls else []),
            *[{'id': o['id'], 'element': 'U-BAR REGION', 'size': f"Ø{fmt_mm(2 * o['r'])}", 'location': grid_ref(level, {'minX': o['cx'] - o['r'], 'maxX': o['cx'] + o['r'], 'minY': o['cy'] - o['r'], 'maxY': o['cy'] + o['r']})} for o in level['ubar']['circles']],
        ]
        cols = [{'key': 'id', 'title': 'ID', 'w': 20}, {'key': 'element', 'title': 'ELEMENT', 'w': 42}, {'key': 'size', 'title': 'SIZE (mm)', 'w': 45}, {'key': 'location', 'title': 'LOCATION / GRID', 'w': 78, 'align': 'L', 'max': 44}]
        d0 = sheet.detail_box(0, 'TYPICAL SLAB SECTION AT COLUMN', '1:25')
        det0 = D.section_column({'h': level['thickness'], 'c1': (level['columns'][0].get('w') if level['columns'] else None) or 600, 'ext': 1200, 'dia': spec['topColumns']['dia'], 'spacing': spec['topColumns']['spacing'], 'cover': spec['cover'], 'hookLeg': R.hook_leg(spec['topColumns']['dia']), 'shape': 'STR'})
        det0.draw(sheet.detail_pen(d0, 25, det0.bbox))
        d1 = sheet.detail_box(1, 'NOTATION AND MATERIALS', 'N.T.S.')
        det1 = D.notation_legend({'thickness': level['thickness'], 'fc': spec['fc'], 'fy': spec['fy'], 'cover': spec['cover']})
        det1.draw(sheet.detail_pen(d1, 12, det1.bbox))
        d2 = sheet.detail_box(2, 'SLAB EDGE / PT ANCHORAGE ZONE', '1:10')
        det2 = D.section_u_edge({'h': level['thickness'], 'cover': spec['cover'], 'leg': spec['uEdge']['leg'], 'dia': spec['uEdge']['dia'], 'edgeDia': spec['edgeBars']['dia'], 'spacing': spec['uEdge']['spacing']})
        det2.draw(sheet.detail_pen(d2, 10, det2.bbox))
        return {
            'rows': rows, 'cols': cols, 'scheduleTitle': 'ELEMENT SCHEDULE',
            'general': [
                *common_notes(model, level)[:3],
                'COLUMN POSITIONS, SLAB OUTLINE, BEAMS, OPENINGS, SUNKEN SLABS AND VOIDS ARE READ FROM THE CONSULTANT\'S G.A. DRAWING; VERIFY AGAINST THE ARCHITECTURAL DRAWINGS BEFORE FORMWORK.',
                'OPENINGS ARE CROSSED; SUNKEN SLABS AND VOID / ACUAR ZONES ARE HATCHED; CIRCULAR U-BAR REGIONS ARE DASH-DOT CIRCLES. SEE SHEETS 02-08 FOR REINFORCEMENT.',
                'FORMWORK LEVELS AND CAMBER PER PT DESIGN. NO PENETRATIONS OTHER THAN THOSE SHOWN WITHOUT THE ENGINEER\'S APPROVAL.',
            ],
            'assumptions': level_assumptions(model, level),
            'legend': [['OUTLINE', 'SLAB EDGE (GREEN)', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL-HATCH', 'WALL BELOW (HATCHED)', 'hatch'], ['BEAM', 'BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SUNKEN-HATCH', 'SUNKEN / STEPPED ZONE', 'hatch'], ['SLAB-THK-HATCH', 'DROP PANEL / THICKENED ZONE', 'hatch'], ['POUR-STRIP-HATCH', 'POUR STRIP', 'hatch'], ['VOID', 'VOID / ACUAR', 'line'], ['PT-ZONE', 'PT ZONE', 'line']],
            'detailsUsed': 3,
        }
    return draw


def _bottom_sheet(model, level, meta):
    res = R.bottom_mesh(level, model['spec'])

    def draw(sheet, pens):
        pl_y, pl_x = pens[0], pens[1]
        S = sheet.S
        spec = model['spec']
        pens_of = {'Y': pl_y, 'X': pl_x}
        for dir_ in ['Y', 'X']:
            pl = pens_of[dir_]
            draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False})
            for z in [zz for zz in res['zones'] if zz['dir'] == dir_]:
                # mesh label spread over the zone: sample points inside the slab, keep up to four well apart
                zb = bbox(z['polygon'])
                placed = []
                min_gap = max(zb['w'], zb['h']) / 4
                for fy in [0.5, 0.2, 0.8, 0.35, 0.65]:
                    for fx in [0.2, 0.5, 0.8, 0.35, 0.65]:
                        p = {'x': zb['minX'] + zb['w'] * fx, 'y': zb['minY'] + zb['h'] * fy}
                        if len(placed) >= 4 or not point_in_polygon(p, z['polygon']) or any(dist(p, q) < min_gap for q in placed):
                            continue
                        if any(point_in_polygon(p, R.region_polygon(o)) for o in (level.get('openings') or [])):
                            continue
                        placed.append(p)
                        pl.text(p, f"Ø{_s(z['dia'])}@{_s(z['spacing'])}-{z['code']}", {'layer': 'REBAR-MESH', 'h': 2.6, 'align': 'C', 'valign': 'M'})
                k = 0
                for g in z['groups']:
                    if g['rows'] < 3:
                        continue  # small groups at openings are scheduled but not drawn
                    mid = (g['start'] + g['end']) / 2
                    side = -1 if k % 2 else 1
                    k += 1
                    for run in g['runs']:
                        a = {'x': run['a'], 'y': mid} if dir_ == 'X' else {'x': mid, 'y': run['a']}
                        b = {'x': run['b'], 'y': mid} if dir_ == 'X' else {'x': mid, 'y': run['b']}
                        _draw_run(pl, S, {'a': a, 'b': b, 'pieces': run['pieces'], 'lap': res['lap'], 'textSide': side, 'offsetSide': side, 'layer': f"REBAR-{z['code']}",
                                          'label': lambda i, cut, *_, g=g, z=z, run=run: _callout(g['rows'], z['dia'], z['spacing'], run['marks'][i]['mark'], cut)})
        # office rule: the bottom mesh is written at every change of slab thickness
        tm = spec.get('thicknessMesh') or R.DEFAULT_SPEC['thicknessMesh']
        for z in [z['polygon'] for z in (level.get('thickZones') or [])] + [R.polygon_of(o) for o in (level.get('sunken') or [])]:
            b = bbox(z)
            pl_y.text({'x': b['minX'] + 500, 'y': b['maxY'] - 700}, f"BOTTOM MESH T{_s(tm['dia'])}@{_s(tm['spacing'])}", {'layer': 'REBAR-MESH', 'h': 2.2})
        rows = R.merge_rows(res['lists']['Y'], res['lists']['X'])
        tot = R.merge_totals(res['lists']['Y'], res['lists']['X'])
        d0 = sheet.detail_box(0, 'SECTION - BOTTOM MESH AND LAP', '1:20')
        det0 = D.section_mesh({'h': level['thickness'], 'cover': spec['cover'], 'dia': res['dia'], 'lap': res['lap'], 'spacing': res['spacing']})
        det0.draw(sheet.detail_pen(d0, 20, det0.bbox))
        d1 = sheet.detail_box(1, 'SECTION AT OPENING - MESH STOPPED', '1:10')
        det1 = D.section_trimmer({'h': level['thickness'], 'cover': spec['cover'], 'count': spec['openings']['count'], 'dia': spec['openings']['dia'], 'uLeg': spec['openings']['uLeg'], 'uDia': spec['openings']['uDia'], 'withU': True})
        det1.draw(sheet.detail_pen(d1, 10, det1.bbox))
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'planTitles': ['BOTTOM REINFORCEMENT PLAN (B1)', 'BOTTOM REINFORCEMENT PLAN (B2)'],
            'general': [
                *common_notes(model, level),
                f"BOTTOM MESH Ø{_s(res['dia'])}@{_s(res['spacing'])} BOTH WAYS IN THE PT ZONE(S) AS BONDED REINFORCEMENT: B1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), B2 PARALLEL TO THE LETTERED GRIDS (PLAN 2). BARS RUN CONTINUOUSLY THROUGH COLUMNS AND STOP AT OPENINGS (DETAIL 2).",
                'BAR LENGTHS ARE CUT FROM THE ZONE BOUNDARY LESS COVER; RUNS LONGER THAN ONE STOCK LENGTH ARE SPLIT INTO PIECES WITH CLASS B LAPS, EACH PIECE CALLED OUT SEPARATELY. GROUPS OF FEWER THAN THREE BARS (ROWS INTERRUPTED BY OPENINGS) ARE NOT DRAWN BUT ARE SCHEDULED UNDER THEIR ZONE.',
                f"THE BOTTOM MESH (T{_s(tm['dia'])}@{_s(tm['spacing'])}, PER THE DESIGN) IS WRITTEN AT EVERY CHANGE OF SLAB THICKNESS (THICKENED / STEPPED ZONES).",
                *_length_note(model, [res['dia']]),
            ],
            'assumptions': [*level_assumptions(model, level), *res['assumptions']],
            'legend': [['REBAR', f"T{_s(res['dia'])} BOTTOM BAR (REPRESENTATIVE)", 'thick'], ['REBAR-MESH', 'MESH LABEL PER ZONE', 'line'], ['OPENING', 'OPENING', 'line']],
            'detailsUsed': 2,
        }
    return draw


def _ram_bars_sheet(model, level, meta, face):
    """Bottom or top sheet from the RAM Concept design: plan 1 = span direction 1 (latitude), plan 2 = direction 2 (longitude)."""
    def draw(sheet, pens):
        pl1, pl2 = pens[0], pens[1]
        S = sheet.S
        spec = model['spec']
        for pl in [pl1, pl2]:
            draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False, 'regionLabels': False})
        lists = _draw_ram_bands(pl1, S, level, spec, face, {1: pl1, 2: pl2})
        rows = R.merge_rows(lists[1], lists[2])
        tot = R.merge_totals(lists[1], lists[2])
        label = 'ADDITIONAL BOTTOM' if face == 'B' else 'ADDITIONAL TOP'
        bands = [b for b in level['ram']['bands'] if b['face'] == face]
        dias = sorted(_uniq([b['dia'] for b in bands]))
        if face == 'B':
            d0 = sheet.detail_box(0, 'SECTION - BOTTOM BARS AND LAP', '1:20')
            det0 = D.section_mesh({'h': level['thickness'], 'cover': spec['cover'], 'dia': dias[0] if dias else 12, 'lap': R.lap_length(spec, dias[0] if dias else 12), 'spacing': 200})
            det0.draw(sheet.detail_pen(d0, 20, det0.bbox))
        else:
            d0 = sheet.detail_box(0, 'SECTION AT SUPPORT - TOP BARS', '1:25')
            det0 = D.section_column({'h': level['thickness'], 'c1': (level['columns'][0].get('w') if level['columns'] else None) or 300, 'ext': 1500, 'dia': dias[0] if dias else 16, 'spacing': 150, 'cover': spec['cover'], 'hookLeg': R.hook_leg(dias[0] if dias else 16), 'shape': 'STR'})
            det0.draw(sheet.detail_pen(d0, 25, det0.bbox))
        d1 = sheet.detail_box(1, f"{'BOTTOM' if face == 'B' else 'TOP'} BANDS FROM RAM CONCEPT ({len(bands)})", '')
        bcols = [{'key': 'id', 'title': 'BAND', 'w': 16}, {'key': 'dir', 'title': 'DIR', 'w': 12}, {'key': 'bars', 'title': 'BARS', 'w': 40, 'align': 'L'}, {'key': 'len', 'title': 'L (mm)', 'w': 20}, {'key': 'w', 'title': 'WIDTH', 'w': 20}, {'key': 'elev', 'title': 'ELEV.', 'w': 20}, {'key': 'note', 'title': 'NOTE', 'w': (d1['w'] - 6) - 128, 'align': 'L', 'max': 30}]
        brows = [{'id': b['id'], 'dir': f"{band_code(b)} (RAM {_s(b.get('dir'))})", 'bars': f"{_s(b['count'])}T{_s(b['dia'])}@{_s(b['spacing'])}", 'len': b['length'], 'w': b['width'], 'elev': js_round(b['elevation']), 'note': 'CHECK SPACING' if b['spacing'] < 75 else ''} for b in bands]
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, bcols, brows, {'maxRows': math.floor((d1['h'] - 18) / 3.2), 'headH': 5, 'rowH': 3.2, 'h': 1.3})
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'planTitles': [f'{label} REINFORCEMENT (ADD.{face}1)', f'{label} REINFORCEMENT (ADD.{face}2)'],
            'general': [
                *common_notes(model, level),
                f"{label} BARS (ADD.{face}1 / ADD.{face}2) ARE THE BANDS DESIGNED IN THE RAM CONCEPT MODEL (CONCENTRATED REINFORCEMENT, EVERY INDIVIDUAL BAR READ FROM THE MODEL), PLACED IN ADDITION TO THE STANDARD {'BOTTOM MESH OF SHEET 02' if face == 'B' else 'TOP BARS OVER COLUMNS OF SHEET 03'}. ADD.{face}1 = BARS PARALLEL TO THE NUMBERED GRIDS, ADD.{face}2 = PARALLEL TO THE LETTERED GRIDS. THE DRAWN BAR IS THE MIDDLE BAR OF EACH BAND; THE DASHED LINES MARK THE FIRST AND LAST BAR OF THE BAND.",
                'BANDS WITH A SPACING UNDER 75 mm ARE FLAGGED "CHECK SPACING" IN THE BAND TABLE (DETAIL 2) AND ARE TO BE CONFIRMED WITH THE DESIGNER BEFORE FABRICATION.',
                *_length_note(model, dias if len(dias) else [12]),
            ],
            'assumptions': level_assumptions(model, level),
            'legend': [[f'REBAR-{face}1', f'{label} BAR (REPRESENTATIVE)', 'thick'], ['REBAR-EXTENT', 'FIRST / LAST BAR OF BAND', 'line'], ['WALL', 'WALL BELOW', 'thick'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch']],
            'detailsUsed': 2,
        }
    return draw


def _top_sheet(model, level, meta):
    res = R.top_at_columns(level, model['spec'])

    def draw(sheet, pens):
        pl_y, pl_x = pens[0], pens[1]
        S = sheet.S
        s = model['spec']['topColumns']
        pens_of = {'y': pl_y, 'x': pl_x}
        for dir_ in ['y', 'x']:
            pl = pens_of[dir_]
            draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False, 'ubarRegions': False})
            seen = set()
            for item in res['columns']:
                col, type_, per = item['col'], item['type'], item['per']
                p = per[dir_]
                c1 = p['c1']
                a0 = (col['cx'] if dir_ == 'x' else col['cy']) - c1 / 2 - p['ext'][-1]
                b0 = (col['cx'] if dir_ == 'x' else col['cy']) + c1 / 2 + p['ext'][1]
                t = col['cy'] if dir_ == 'x' else col['cx']
                a = {'x': a0, 'y': t} if dir_ == 'x' else {'x': t, 'y': a0}
                b = {'x': b0, 'y': t} if dir_ == 'x' else {'x': t, 'y': b0}
                _draw_run(pl, S, {'a': a, 'b': b, 'pieces': [p['length']], 'lap': 0, 'hooks': {'start': bool(p['hooks'].get(-1)), 'end': bool(p['hooks'].get(1))}, 'hookLeg': p['hookLeg'], 'hookLabel': p.get('hookLabel'), 'hookLabels': p.get('hookLabels'), 'layer': f"REBAR-{p['code']}",
                                  'label': lambda i, cut, *_, p=p, type_=type_, dir_=dir_: _callout(p['n'], s['dia'], s['spacing'], type_[dir_]['mark']['mark'], cut)})
                # the width the bars are distributed over (office rule: the length of the crossing bars at this column)
                if p.get('band'):
                    st = a0 + (b0 - a0) * 0.3
                    q1 = {'x': st, 'y': t - p['band'] / 2} if dir_ == 'x' else {'x': t - p['band'] / 2, 'y': st}
                    q2 = {'x': st, 'y': t + p['band'] / 2} if dir_ == 'x' else {'x': t + p['band'] / 2, 'y': st}
                    pl.dim(q1, q2, 0, {'layer': 'DIM', 'h': 1.6, 'text': _s(js_round(p['band']))})
                size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}
                pl.bubble({'x': col['cx'] + size['x'] / 2, 'y': col['cy'] + size['y'] / 2}, type_['id'], {'dx': 6, 'dy': 6, 'layer': 'CALLOUT', 'r': 3, 'h': 1.6})
                seen.add(type_['id'])
        t0 = res['types'][0] if res['types'] else None
        d0 = sheet.detail_box(0, 'SECTION AT COLUMN - TOP BARS', '1:25')
        c0 = res['columns'][0]['col'] if res['columns'] else None
        if t0:
            shape = 'U' if (res['rule'] == 'office' and t0['x']['shape'] == 'STR' and any('U' in t['x']['shape'] or 'U' in t['y']['shape'] for t in res['types'])) else t0['x']['shape']
        else:
            shape = 'U'
        det0 = D.section_column({'h': level['thickness'], 'c1': ((c0['d'] if c0.get('shape') == 'circle' else c0['w']) if c0 else 600), 'ext': max(t0['x']['ext'][-1], t0['x']['ext'][1]) if t0 else 1200, 'dia': s['dia'], 'spacing': s['spacing'], 'cover': model['spec']['cover'], 'hookLeg': res['uEnd']['leg'], 'shape': shape, 'uReturn': R.U_BOTTOM_LEG})
        det0.draw(sheet.detail_pen(d0, 25, det0.bbox))
        d1 = sheet.detail_box(1, 'TOP BAR TYPES OVER COLUMNS', '')
        type_cols = [{'key': 'id', 'title': 'TYPE', 'w': 14}, {'key': 'x', 'title': 'T2 (PLAN 2) BARS', 'w': 50, 'align': 'L'}, {'key': 'y', 'title': 'T1 (PLAN 1) BARS', 'w': 50, 'align': 'L'}, {'key': 'as', 'title': 'As req/prov', 'w': 30}, {'key': 'cols', 'title': 'COLUMNS', 'w': (d1['w'] - 6) - 144, 'align': 'L', 'max': 30}]
        type_rows = [{'id': t['id'], 'x': f"{_s(t['x']['n'])}T{_s(s['dia'])} {t['x']['mark']['mark']} L={_s(t['x']['length'])} {t['x']['shape']}", 'y': f"{_s(t['y']['n'])}T{_s(s['dia'])} {t['y']['mark']['mark']} L={_s(t['y']['length'])} {t['y']['shape']}", 'as': f"{_s(max(t['x']['asReq'], t['y']['asReq']))}/{_s(min(t['x']['asProv'], t['y']['asProv']))}", 'cols': ', '.join(t['columns'])} for t in res['types']]
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, type_cols, type_rows, {'maxRows': math.floor((d1['h'] - 18) / 4), 'headH': 5, 'rowH': 4, 'h': 1.5})
        rows = R.merge_rows(res['lists']['y'], res['lists']['x'])
        tot = R.merge_totals(res['lists']['y'], res['lists']['x'])
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'], 'checks': res['checks'],
            'planTitles': ['ADDITIONAL TOP REINFORCEMENT (T1)', 'ADDITIONAL TOP REINFORCEMENT (T2)'],
            'general': [
                *common_notes(model, level),
                (f"ADDITIONAL TOP BARS T{_s(s['dia'])}@{_s(s['spacing'])} OVER EVERY COLUMN: T1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), T2 PARALLEL TO THE LETTERED GRIDS (PLAN 2), PLACED WITHIN c2 + 1.5h EACH SIDE OF THE COLUMN. OFFICE RULE: AN INTERIOR COLUMN BAR COVERS THE DROP PANEL WHERE THERE IS ONE, OTHERWISE {_s(res['length'])} mm IN TOTAL; AN EDGE COLUMN BAR ENDS IN A U AT THE SLAB EDGE (DOWN THE SLAB, {R.U_BOTTOM_LEG} mm BACK AT THE BOTTOM) AND RUNS {js_round(res['edgeFactor'] * 100)} % OF THE INTERIOR LENGTH ({js_round(res['edgeFactor'] * res['length'])} mm) ON TOP FROM THE EDGE."
                 if res['rule'] == 'office' else
                 f"ADDITIONAL TOP BARS T{_s(s['dia'])}@{_s(s['spacing'])} OVER EVERY COLUMN: T1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), T2 PARALLEL TO THE LETTERED GRIDS (PLAN 2), PLACED WITHIN c2 + 1.5h EACH SIDE OF THE COLUMN (SBC 304-18 §8.7.5.5.1) AND EXTENDING NOT LESS THAN ln/6 BEYOND THE FACE OF SUPPORT (§8.7.5.5.2)."),
                f"EVERY TOP BAR THAT ENDS AT THE OUTER SLAB EDGE OR AT AN OPENING ENDS IN A U: VERTICAL LEG THROUGH THE SLAB DEPTH AND A {R.U_BOTTOM_LEG} mm BOTTOM LEG (\"{res['uEnd']['label']}\" AT THE BAR END; SHAPE U / UU IN THE SCHEDULE, THE CUTTING LENGTH INCLUDES BOTH LEGS).",
                'MINIMUM BONDED REINFORCEMENT OVER COLUMNS As = 0.00075·Acf (§8.6.2.3) IS CHECKED PER COLUMN; WHERE IT GOVERNS THE BAR COUNT IS INCREASED (TYPE TABLE, DETAIL 2). TOP BARS SIT BELOW THE TOP COVER, ABOVE THE TENDONS, ON CHAIRS.',
                *_length_note(model, [s['dia']]),
            ],
            'assumptions': level_assumptions(model, level),
            'legend': [['REBAR', f"T{_s(s['dia'])} TOP BAR (REPRESENTATIVE)", 'thick'], ['CALLOUT', 'TOP BAR TYPE', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
            'detailsUsed': 2,
        }
    return draw


def _ubar_sheet(model, level, meta):
    res = R.u_bars(level, model['spec'])

    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        spec = model['spec']
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'ubarRegions': False, 'pt': False})
        su, se, sc, sr = spec['uEdge'], spec['edgeBars'], spec['uCircle'], spec['ringBars']
        cover = spec['cover']
        for e in res['edgeItems']:
            ux, uy = (e['b']['x'] - e['a']['x']) / e['length'], (e['b']['y'] - e['a']['y']) / e['length']
            nx, ny = -uy, ux  # inward for a CCW outline
            # longitudinal edge bars as a run (representative)
            a = {'x': e['a']['x'] + nx * (cover + 60) + ux * cover, 'y': e['a']['y'] + ny * (cover + 60) + uy * cover}
            b = {'x': e['b']['x'] + nx * (cover + 60) - ux * cover, 'y': e['b']['y'] + ny * (cover + 60) - uy * cover}
            _draw_run(pl, S, {'a': a, 'b': b, 'pieces': e['pieces'], 'lap': R.lap_length(spec, se['dia']), 'offsetSide': 1, 'textSide': 1,
                              'label': lambda i, cut, *_, e=e: f"{_s(2 * se['count'])}T{_s(se['dia'])}-T&B-{e['marks'][min(i, len(e['marks']) - 1)]['mark']}-(L={_s(cut)})"})
            step = su['spacing'] * 4
            for p, q in e['runs']:
                d = p + su['spacing'] / 2
                while d < q:
                    at = {'x': e['a']['x'] + ux * d + nx * cover, 'y': e['a']['y'] + uy * d + ny * cover}
                    if e.get('beam'):
                        pl.line(at, {'x': at['x'] + nx * e['leg'], 'y': at['y'] + ny * e['leg']}, {'layer': 'REBAR-U'})
                        pl.line(at, {'x': at['x'] - nx * 200, 'y': at['y'] - ny * 200}, {'layer': 'REBAR-U'})
                    else:
                        _hairpin(pl, at, {'x': nx, 'y': ny}, e['leg'], 120)
                    d += step
            mid = {'x': (e['a']['x'] + e['b']['x']) / 2 + nx * (su['leg'] + 500), 'y': (e['a']['y'] + e['b']['y']) / 2 + ny * (su['leg'] + 500)}
            rot = _rot_of(uy, ux)
            um = e['uMark']
            pl.text(mid, f"{_s(e['n'])}T{_s(su['dia'])}@{_s(su['spacing'])}-{um['mark']}-(L={_s(um['length'])}) L-BARS {_s(su['beamLeg'])} IN BEAM + {_s(su['beamTop'])} TOP" if e.get('beam') else f"{_s(e['n'])}T{_s(su['dia'])}@{_s(su['spacing'])}-{um['mark']}-(L={_s(um['length'])}) U-BARS LEGS {_s(e['leg'])} T&B", {'layer': 'REBAR-TEXT', 'h': CALL_H, 'rot': rot, 'align': 'C'})
            pl.bubble({'x': (e['a']['x'] + e['b']['x']) / 2, 'y': (e['a']['y'] + e['b']['y']) / 2}, e['id'], {'dx': -nx * 6, 'dy': -ny * 6, 'layer': 'CALLOUT', 'r': 3, 'h': 1.6})
        for c in res['circleItems']:
            pl.circle({'x': c['cx'], 'y': c['cy']}, c['r'], {'layer': 'OPENING'} if c.get('fromOpening') else {'layer': 'REBAR-U', 'ltype': 'DASHDOT'})
            pl.circle({'x': c['cx'], 'y': c['cy']}, c['ringR'], {'layer': 'REBAR'})
            n_draw = min(c['n'], 16)
            for i in range(n_draw):
                ang = (i / n_draw) * math.pi * 2
                _hairpin(pl, {'x': c['cx'] + (c['r'] + cover) * math.cos(ang), 'y': c['cy'] + (c['r'] + cover) * math.sin(ang)}, {'x': math.cos(ang), 'y': math.sin(ang)}, sc['leg'], 120)
            pl.bubble({'x': c['cx'], 'y': c['cy']}, c['id'], {'dx': 10, 'dy': 10, 'layer': 'CALLOUT'})
            pl.text({'x': c['cx'], 'y': c['cy'] - c['r'] - cover - sc['leg'] - 500}, f"{_s(c['n'])}T{_s(sc['dia'])}@{_s(sc['spacing'])}-{c['uMark']['mark']}-(L={_s(c['uMark']['length'])}) RADIAL U-BARS + {_s(2 * sr['count'])}T{_s(sr['dia'])}-RING-{'/'.join(m['mark'] for m in c['ringMarks'])}", {'layer': 'REBAR-TEXT', 'h': CALL_H, 'align': 'C'})
        d0 = sheet.detail_box(0, 'U-BAR AT SLAB EDGE - SECTION', '1:10')
        det0 = D.section_u_edge({'h': level['thickness'], 'cover': cover, 'leg': res['uLegTop'], 'dia': su['dia'], 'edgeDia': se['dia'], 'spacing': su['spacing']})
        det0.draw(sheet.detail_pen(d0, 10, det0.bbox))
        d1 = sheet.detail_box(1, 'U-BARS AROUND CIRCULAR REGION - PLAN', '1:25')
        c0 = res['circleItems'][0] if res['circleItems'] else {'r': 1000, 'ringR': 1000 + cover + sc['dia'] + sr['dia'] / 2}
        det1 = D.plan_u_circle({'r': c0['r'], 'cover': cover, 'leg': sc['leg'], 'spacing': sc['spacing'], 'dia': sc['dia'], 'ringR': c0['ringR'], 'ringDia': sr['dia']})
        det1.draw(sheet.detail_pen(d1, 25, det1.bbox))
        rows = res['bars'].rows()
        tot = res['bars'].totals()
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'general': [
                *common_notes(model, level),
                f"OFFICE PERIMETER RULE: T{_s(su['dia'])}@{_s(su['spacing'])} ALONG THE WHOLE SLAB PERIMETER BETWEEN THE COLUMN TOP BARS. AT A FREE EDGE A U-BAR {_s(su['total'])} mm LONG WITH EQUAL TOP AND BOTTOM LEGS ({_s(res['uLegTop'])} mm, DEPTH {_s(res['web'])} mm); AT AN EDGE BEAM AN L-BAR {_s(res['lLen'])} mm LONG: {_s(su['beamLeg'])} mm LEG DOWN INTO THE BEAM AND {_s(su['beamTop'])} mm ON TOP IN THE SLAB. WITH {_s(se['count'])}T{_s(se['dia'])} LONGITUDINAL BARS TOP AND BOTTOM INSIDE THEM (ONE REPRESENTATIVE BAR PER EDGE).",
                f"AROUND CIRCULAR REGIONS: RADIAL U-BARS T{_s(sc['dia'])}@{_s(sc['spacing'])} (LEGS {_s(sc['leg'])}) PLUS {_s(sr['count'])}T{_s(sr['dia'])} RING BARS TOP AND BOTTOM, RINGS LAPPED CLASS B.",
                'U-BARS ARE PLACED BEFORE THE ANCHORAGES ARE FIXED; DO NOT CUT U-BARS TO SUIT ANCHORAGE POCKETS - RELOCATE WITHIN THE SPACING.',
                *_length_note(model, _uniq([su['dia'], se['dia'], sc['dia']])),
            ],
            'assumptions': [*level_assumptions(model, level), *res['assumptions']],
            'legend': [['REBAR-U', 'U-BAR (HAIRPIN) / L-BAR AT EDGE BEAM (LEG SYMBOL)', 'thick'], ['REBAR', 'EDGE / RING BAR', 'thick'], ['CALLOUT', 'EDGE / REGION ID', 'line']],
            'detailsUsed': 2,
        }
    return draw


def _draw_trimmers(pl, S, regions, spec, kind_label, o=None, **kw):
    o = opts(o, kw)
    for rg in regions:
        region, trimmers, corners, diag_mark, u_mark, n_u, diag_l, kind = rg['region'], rg['trimmers'], rg.get('corners'), rg.get('diagMark'), rg.get('uMark'), rg.get('nU'), rg.get('diagL'), rg.get('kind')
        poly = R.polygon_of(region)
        for t in trimmers:
            off = t['offsets'][0]
            a = {'x': t['edge']['a']['x'] - t['ux'] * t['ext'][-1] + t['nx'] * off, 'y': t['edge']['a']['y'] - t['uy'] * t['ext'][-1] + t['ny'] * off}
            b = {'x': t['edge']['b']['x'] + t['ux'] * t['ext'][1] + t['nx'] * off, 'y': t['edge']['b']['y'] + t['uy'] * t['ext'][1] + t['ny'] * off}
            hk = R.hook_leg(spec['dia'])
            _draw_run(pl, S, {'a': a, 'b': b, 'pieces': [t['length']], 'lap': 0, 'hooks': {'start': bool(t['hooks'].get(-1)), 'end': bool(t['hooks'].get(1))}, 'hookLeg': hk, 'layer': 'REBAR-TRIM',
                              'label': lambda i, cut, *_, t=t: f"{_s(2 * spec['count'])}T{_s(spec['dia'])}-T&B-{t['marks'][0]['mark']}-(L={_s(cut)})", 'offsetSide': -1, 'textSide': -1})
        if corners:
            for c in corners:
                pl.line({'x': c['c']['x'] - c['dx'] * diag_l / 2, 'y': c['c']['y'] - c['dy'] * diag_l / 2}, {'x': c['c']['x'] + c['dx'] * diag_l / 2, 'y': c['c']['y'] + c['dy'] * diag_l / 2}, {'layer': 'REBAR-TRIM'})
        if corners and len(corners) and diag_mark:
            c = corners[0]
            rot = _rot_of(c['dy'], c['dx'])
            pl.text({'x': c['c']['x'] - c['dy'] * 0.6 * S, 'y': c['c']['y'] + c['dx'] * 0.6 * S}, f"{_s(2 * spec['diagCount'])}T{_s(spec['diagDia'])}-DIAG-{diag_mark['mark']}-(L={_s(diag_mark['length'])}) AT {len(corners)} CORNERS", {'layer': 'REBAR-TEXT', 'h': LEN_H, 'rot': rot, 'align': 'C'})
        if u_mark and n_u:
            u_spec = o.get('uSpec') or spec
            for e in edges(poly):
                ux, uy = e['dx'] / e['length'], e['dy'] / e['length']
                nx, ny = -uy, ux
                mid = {'x': (e['a']['x'] + e['b']['x']) / 2, 'y': (e['a']['y'] + e['b']['y']) / 2}
                if point_in_polygon({'x': mid['x'] + nx * 10, 'y': mid['y'] + ny * 10}, poly):
                    nx, ny = -nx, -ny
                d = u_spec['uSpacing']
                while d < e['length'] - u_spec['uSpacing'] / 2:
                    _hairpin(pl, {'x': e['a']['x'] + ux * d, 'y': e['a']['y'] + uy * d}, {'x': nx, 'y': ny}, u_spec['uLeg'], 100)
                    d += u_spec['uSpacing'] * 3
        b = _region_box(region)
        pl.bubble({'x': b['maxX'], 'y': b['maxY']}, region['id'], {'dx': 10, 'dy': 8, 'layer': 'CALLOUT', 'r': 3, 'h': 1.6})
        lines = [f"{region['id']} {kind or kind_label} {_size_of(region)}"]
        if u_mark and n_u:
            us = o.get('uSpec') or spec
            lines.append(f"{_s(n_u)}T{_s(us['uDia'])}@{_s(us['uSpacing'])}-{u_mark['mark']}-(L={_s(u_mark['length'])}) U-BARS AT FREE EDGES")
        for i, ln in enumerate(lines):
            pl.text({'x': b['maxX'] + 13 * S, 'y': b['maxY'] + (6.5 - i * 2.4) * S}, ln, {'layer': 'REBAR-TEXT', 'h': LEN_H})


def _voids_sheet(model, level, meta):
    res = R.around_voids(level, model['spec'])

    def draw(sheet, pens):
        pl = pens[0]
        spec = model['spec']
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'ubarRegions': False, 'pt': False})
        _draw_trimmers(pl, sheet.S, [{**r, 'corners': None, 'diagMark': None} for r in res['regions']], spec['voids'], 'VOID', {'uSpec': res['sunken']})
        sv, ss = spec['voids'], res['sunken']
        d0 = sheet.detail_box(0, 'TRIMMER BARS AROUND VOID / SUNKEN SLAB - PLAN', '1:25')
        det0 = D.plan_trimmers({'w': 1500, 'h': 1000, 'ld': res['ld'], 'count': sv['count'], 'dia': sv['dia'], 'diag': False, 'uSpacing': ss['uSpacing'], 'uDia': ss['uDia'], 'label': 'VOID / SUNKEN'})
        det0.draw(sheet.detail_pen(d0, 25, det0.bbox))
        d1 = sheet.detail_box(1, 'SECTION AT SUNKEN SLAB STEP', '1:10')
        det1 = D.section_trimmer({'h': level['thickness'], 'cover': spec['cover'], 'count': ss['count'], 'dia': ss['dia'], 'uLeg': ss['uLeg'], 'uDia': ss['uDia'], 'withU': True})
        det1.draw(sheet.detail_pen(d1, 10, det1.bbox))
        rows = res['bars'].rows()
        tot = res['bars'].totals()
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'general': [
                *common_notes(model, level),
                f"{_s(sv['count'])}T{_s(sv['dia'])} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY VOID / ACUAR ZONE AND SUNKEN SLAB, ANCHORED ld = {_s(res['ld'])} mm BEYOND THE CORNERS INTO THE SOLID SLAB; STOPPED WITH A 90° HOOK WHERE THE ANCHORAGE WOULD LEAVE THE SLAB.",
                f"SUNKEN SLABS: T{_s(ss['uDia'])}@{_s(ss['uSpacing'])} HAIRPINS (LEGS {_s(ss['uLeg'])}) ALONG THE STEP IN ADDITION TO THE TRIMMERS; THE MAIN MESH IS CRANKED THROUGH THE STEP (DETAIL 2). VOID FORMERS TO BE TIED AGAINST FLOTATION; NO TENDON DEVIATION THROUGH VOIDS WITHOUT THE PT DESIGNER'S APPROVAL.",
                *_length_note(model, _uniq([sv['dia'], ss['dia'], ss['uDia']])),
            ],
            'assumptions': level_assumptions(model, level),
            'legend': [['REBAR', f"T{_s(sv['dia'])} TRIMMER BAR", 'thick'], ['REBAR-U', f"T{_s(ss['uDia'])} HAIRPIN", 'line'], ['SUNKEN-HATCH', 'SUNKEN SLAB', 'hatch'], ['VOID-HATCH', 'VOID / ACUAR', 'hatch']],
            'detailsUsed': 2,
        }
    return draw


def _openings_sheet(model, level, meta):
    res = R.around_openings(level, model['spec'])

    def draw(sheet, pens):
        pl = pens[0]
        spec = model['spec']
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'ubarRegions': False, 'pt': False})
        _draw_trimmers(pl, sheet.S, [{**r, 'diagL': res['diagL'], 'kind': 'OPENING'} for r in res['regions']], spec['openings'], 'OPENING')
        so = spec['openings']
        for o in res.get('lined') or []:
            b = _region_box(o)
            pl.text({'x': b['cx'], 'y': b['cy']}, f"{o['id']}: ENCLOSED BY WALLS / BEAMS - NO TRIMMERS", {'layer': 'REBAR-TEXT', 'h': 1.5, 'align': 'C', 'valign': 'M'})
        # the three bar groups around every opening: parallel to the two sides and the 45° diagonals crossing them
        group_rows = []
        for r in res['regions']:
            tr_x = [t for t in r['trimmers'] if abs(t['uy']) < 0.5]
            tr_y = [t for t in r['trimmers'] if abs(t['uy']) >= 0.5]

            def g(id_, dir_label, lst, r=r):
                return {'id': r['region']['id'], 'g': id_, 'dir': dir_label, 'bars': f"{len(lst)} SIDES x {_s(so['count'])} T{_s(so['dia'])} T&B = {_s(len(lst) * 2 * so['count'])}" if len(lst) else '-', 'marks': _js_join(_uniq([m for t in lst for m in t['marks']]), ', ')}
            group_rows.extend([g('G1', 'PARALLEL TO THE LETTERED GRIDS (X)', tr_x), g('G2', 'PARALLEL TO THE NUMBERED GRIDS (Y)', tr_y),
                               {'id': r['region']['id'], 'g': 'G3', 'dir': 'DIAGONAL 45° ACROSS G1 AND G2', 'bars': f"{len(r['corners'])} CORNERS x {_s(so['diagCount'])} T{_s(so['diagDia'])} T&B = {_s(len(r['corners']) * 2 * so['diagCount'])}" if len(r['corners']) else '-', 'marks': r['diagMark']['mark'] if r.get('diagMark') else ''}])
        d0 = sheet.detail_box(0, 'TRIMMERS AND DIAGONALS AT OPENING - PLAN', '1:25')
        det0 = D.plan_trimmers({'w': 1500, 'h': 1000, 'ld': res['ld'], 'count': so['count'], 'dia': so['dia'], 'diag': True, 'diagDia': so['diagDia'], 'diagL': res['diagL'], 'uSpacing': so['uSpacing'], 'uDia': so['uDia'], 'label': 'OPENING'})
        det0.draw(sheet.detail_pen(d0, 25, det0.bbox))
        d1 = sheet.detail_box(1, 'SECTION AT OPENING EDGE', '1:10')
        d2 = sheet.detail_box(2, 'BAR GROUPS AROUND EACH OPENING (G1 / G2 PARALLEL, G3 DIAGONAL)', '')
        gcols = [{'key': 'id', 'title': 'OPEN.', 'w': 16}, {'key': 'g', 'title': 'GRP', 'w': 12}, {'key': 'dir', 'title': 'DIRECTION', 'w': 78, 'align': 'L', 'max': 40}, {'key': 'bars', 'title': 'BARS (No.)', 'w': 62, 'align': 'L', 'max': 32}, {'key': 'marks', 'title': 'MARKS', 'w': d2['w'] - 6 - 168, 'align': 'L', 'max': 24}]
        sheet.table(d2['x'] + 3, d2['y'] + d2['h'] - 10, gcols, group_rows, {'headH': 5, 'rowH': 3.6, 'h': 1.4, 'maxRows': math.floor((d2['h'] - 18) / 3.6)})
        det1 = D.section_trimmer({'h': level['thickness'], 'cover': spec['cover'], 'count': so['count'], 'dia': so['dia'], 'uLeg': so['uLeg'], 'uDia': so['uDia'], 'withU': True})
        det1.draw(sheet.detail_pen(d1, 10, det1.bbox))
        rows = res['bars'].rows()
        tot = res['bars'].totals()
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'general': [
                *common_notes(model, level),
                f"{_s(so['count'])}T{_s(so['dia'])} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY OPENING (CALL-OUT \"nT{_s(so['dia'])}-T&B-MARK-(L)\"), ANCHORED ld = {_s(res['ld'])} mm BEYOND THE CORNERS; {_s(so['diagCount'])}T{_s(so['diagDia'])} DIAGONAL BARS TOP AND BOTTOM AT EACH RE-ENTRANT CORNER, L = {_s(res['diagL'])} mm; T{_s(so['uDia'])}@{_s(so['uSpacing'])} U-BARS WITH {_s(so['uLeg'])} mm LEGS ALONG THE FREE EDGES.",
                'THE MAIN MESH IS STOPPED AT THE OPENING FACE LESS COVER; TRIMMERS REPLACE THE INTERRUPTED BARS. TENDONS ARE DEVIATED AROUND OPENINGS PER THE PT LAYOUT - NO TENDON MAY BE CUT.',
                *_length_note(model, _uniq([so['dia'], so['diagDia'], so['uDia']])),
            ],
            'assumptions': level_assumptions(model, level),
            'legend': [['REBAR', f"T{_s(so['dia'])} TRIMMER / T{_s(so['diagDia'])} DIAGONAL", 'thick'], ['REBAR-U', f"T{_s(so['uDia'])} U-BAR (HAIRPIN)", 'line'], ['OPENING', 'OPENING', 'line'], ['CALLOUT', 'OPENING ID', 'line']],
            'detailsUsed': 2,
        }
    return draw


def _punching_sheet(model, level, meta):
    res = R.punching(level, model['spec'])

    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'ubarRegions': False, 'pt': False})
        for item in res['columns']:
            col, type_, sides = item['col'], item['type'], item['sides']
            size = {'x': col['d'] if col.get('shape') == 'circle' else col['w'], 'y': col['d'] if col.get('shape') == 'circle' else col['h']}
            for sd in sides:
                face_len = sd['faceLen']
                for r in range(1, sd['nRows'] + 1):
                    d_off = sd['offset'] + r * res['rowSpacing']
                    a = {'x': col['cx'] + sd['sign'] * d_off, 'y': col['cy'] - face_len / 2} if sd['dir'] == 'x' else {'x': col['cx'] - face_len / 2, 'y': col['cy'] + sd['sign'] * d_off}
                    b = {'x': col['cx'] + sd['sign'] * d_off, 'y': col['cy'] + face_len / 2} if sd['dir'] == 'x' else {'x': col['cx'] + face_len / 2, 'y': col['cy'] + sd['sign'] * d_off}
                    pl.line(a, b, {'layer': 'REBAR-PUNCH'})
                    for k in range(sd['links']):
                        f = k / (sd['links'] - 1) if sd['links'] > 1 else 0.5
                        p = {'x': a['x'] + (b['x'] - a['x']) * f, 'y': a['y'] + (b['y'] - a['y']) * f}
                        pl.line({'x': p['x'] - 40, 'y': p['y']} if sd['dir'] == 'x' else {'x': p['x'], 'y': p['y'] - 40}, {'x': p['x'] + 40, 'y': p['y']} if sd['dir'] == 'x' else {'x': p['x'], 'y': p['y'] + 40}, {'layer': 'REBAR-PUNCH'})
                lp = {'x': col['cx'] + sd['sign'] * (sd['offset'] + (sd['nRows'] + 1) * res['rowSpacing'] + 0.3 * S), 'y': col['cy'] + face_len / 2 + 0.3 * S} if sd['dir'] == 'x' else {'x': col['cx'] + face_len / 2 + 0.3 * S, 'y': col['cy'] + sd['sign'] * (sd['offset'] + (sd['nRows'] + 1) * res['rowSpacing'])}
                pl.text(lp, f"{_s(sd['nRows'])}X{_s(sd['links'])}-T{_s(res['dia'])}-{_s(res['rowSpacing'])}", {'layer': 'REBAR-TEXT', 'h': 1.6, 'rot': 90 if sd['dir'] == 'x' else 0})
            pl.text({'x': col['cx'] - size['x'] / 2 - 1.5 * S, 'y': col['cy'] + size['y'] / 2 + 1.5 * S}, type_['id'], {'layer': 'REBAR-RED', 'h': 2.5, 'align': 'R'})
        for sr in (level.get('ram') or {}).get('shear') or []:
            pl.line(sr['a'], sr['b'], {'layer': 'REBAR-PUNCH'})
            pl.bar_ends(sr['a'], sr['b'], {'layer': 'REBAR-PUNCH', 'size': 0.8})
            rotd = _rot_of(sr['b']['y'] - sr['a']['y'], sr['b']['x'] - sr['a']['x'])
            pl.text({'x': (sr['a']['x'] + sr['b']['x']) / 2, 'y': (sr['a']['y'] + sr['b']['y']) / 2 + 0.5 * S}, f"{sr['id']}: T{_s(sr['dia'])}-{_s(sr['legs'])}LEGS@{_s(sr['spacing'])} ({_s(sr['length'])})", {'layer': 'REBAR-TEXT', 'h': 1.6, 'rot': rotd, 'align': 'C'})
        d0 = sheet.detail_box(0, 'PUNCHING LINK - SHAPE AND ARRANGEMENT', '1:10')
        det0 = D.punching_link({'h': level['thickness'], 'cover': model['spec']['cover'], 'dia': res['dia'], 'rowSpacing': res['rowSpacing'], 'legSpacing': res['legSpacing'], 'rows': res['rows']})
        det0.draw(sheet.detail_pen(d0, 10, det0.bbox))
        d1 = sheet.detail_box(1, 'PUNCHING TYPES (PS)', '')
        tcols = [{'key': 'id', 'title': 'TYPE', 'w': 14}, {'key': 'size', 'title': 'COLUMN', 'w': 26}, {'key': 'arr', 'title': 'ROWS X LINKS - T - SPACING (PER FACE)', 'w': 90, 'align': 'L', 'max': 52}, {'key': 'cols', 'title': 'COLUMNS', 'w': (d1['w'] - 6) - 130, 'align': 'L', 'max': 36}]
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, tcols, [{'id': t['id'], 'size': f"{fmt_mm(t['size']['x'])}x{fmt_mm(t['size']['y'])}", 'arr': t['label'], 'cols': ', '.join(t['columns'])} for t in res['types']], {'maxRows': math.floor((d1['h'] - 18) / 4), 'headH': 5, 'rowH': 4, 'h': 1.5})
        rows = res['bars'].rows()
        tot = res['bars'].totals()
        ram = level.get('ram')
        ram_note = []
        if ram:
            p0 = ram['punching'][0] if ram['punching'] else None
            ram_note = [f"RAM CONCEPT SPECIFIES STUD RAILS ({('SSR SYSTEM ' + _s(p0['ssr'])) if p0 and p0.get('ssr') else 'SSR'}) AT {len(ram['punching'])} PUNCHING CHECKS; THE STUD LAYOUT FROM THE RAM PUNCHING REPORT GOVERNS OVER THE LINKS SHOWN. SHEAR REGIONS (SR) ARE THE RAM TRANSVERSE REINFORCEMENT REGIONS."]
        return {
            'rows': rows, 'totals': totals_line(tot), 'weight': tot['weight_kg'],
            'general': [
                *common_notes(model, level)[:3],
                f"PRELIMINARY: PUNCHING LINKS ARE SHOWN AS THE MINIMUM DETAILING ARRANGEMENT (SBC 304-18 §8.7.6 / §22.6.8): T{_s(res['dia'])} CLOSED LINKS, FIRST ROW AT d/2 = {_s(res['rowSpacing'])} mm FROM THE COLUMN FACE, ROWS AT d/2, LEGS AT {_s(res['legSpacing'])} mm ALONG THE FACE, EXTENDING {_s(res['extent'])} mm (2h) BEYOND THE FACE. THE NUMBER OF ROWS AND LINK SIZE ARE TO BE CONFIRMED AGAINST THE PUNCHING DESIGN (Vu) BEFORE FABRICATION.",
                'CALL-OUT PER FACE: [ROWS] X [LINKS PER ROW] - T[Ø] - [ROW SPACING]. FACES AT A SLAB EDGE CARRY NO LINKS. LINKS ENCLOSE THE TOP AND BOTTOM BARS.',
                'PS TYPES GROUP COLUMNS WITH THE SAME ARRANGEMENT (TABLE, DETAIL 2).',
            ],
            'assumptions': ['PUNCHING SHEAR DEMAND (Vu) NOT AVAILABLE: LINK ROWS SET BY MINIMUM DETAILING AND 2h EXTENT; SUBJECT TO DESIGN CONFIRMATION.', *ram_note, *level_assumptions(model, level)[:4]],
            'legend': [['REBAR-PUNCH', 'ROW OF LINKS', 'thick'], ['REBAR-RED', 'PS TYPE LABEL', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
            'detailsUsed': 2,
        }
    return draw


# ------------------------------------------------------------------ office cable drawings (design 05/06, shop 07A/07B)
# The conventions of the office's cable shop-drawing program (Auto PT Suite, ShopOnly build): chair-height stations
# along every tendon, the odd spacing dimensioned, high / low points on their own layers with a circle on the point,
# live / dead anchor blocks, the five-cell tag on every tendon, anchor spacing dimensioned at the face, one schedule
# row per mark (tendons of one strand count and one profile share a mark), the chair / duct / quantity schedules and
# the seven general notes.
CAB = {
    'step': 1000, 'minStation': 500, 'roundH': 5, 'chairDrop': 10, 'anchorSet': 6, 'dimSkip': [980, 1020],
    'txt': 2.0, 'dimTxt': 1.6, 'tick': 0.8, 'tagClear': 250, 'tagXs': [800, 1131.3, 1773.2, 2608.5, 3387.5, 3979], 'tagLead': 750, 'tagHalf': 175,
    'smallDuctMax': 3, 'ductSmall': '20x50', 'ductLarge': '20x70', 'anchorAllowance': 300,
}
CAB_NOTES = [
    'ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE.',
    'FIGURES ALONG EACH TENDON ARE CHAIR HEIGHTS TO THE UNDERSIDE OF THE DUCT, MEASURED FROM THE SOFFIT OF THE SLAB (OR OF THE DROP PANEL WHERE THE POINT FALLS INSIDE ONE).',
    'STATIONS ARE AT 1000 mm CENTRES; THE ODD SPACING BEFORE A HIGH OR LOW POINT IS DIMENSIONED.',
    'HIGH POINTS AND LOW POINTS ARE ON THEIR OWN LAYERS AND COLOURS.',
    'EXTENSIONS ARE TAKEN FROM THE ANALYSIS. ONE LIVE END: THE CALCULATED VALUE LESS 6 mm SEATING. TWO LIVE ENDS: THE SUM OF BOTH ENDS WITH NO DEDUCTION.',
    'ANCHOR NUMBERS ARE FILLED ON SITE AGAINST THE STRESSING RECORD.',
    'DO NOT CUT STRAND TAILS BEFORE THE STRESSING RECORD IS APPROVED.',
]
STRAND_DIA = {98.7: '12.7', 140: '15.24', 150: '15.7', 100: '12.9'}
PT_TEXT = {'style': 'PT-PROFILE', 'widthFactor': 0.75}


def along_tendon(t, s):
    """The point and unit tangent at `s` along a tendon."""
    pts = t['pts']
    acc = 0
    for i in range(len(pts) - 1):
        L = dist(pts[i], pts[i + 1])
        if s <= acc + L + 1e-6 or i + 2 >= len(pts):
            u = {'x': (pts[i + 1]['x'] - pts[i]['x']) / L, 'y': (pts[i + 1]['y'] - pts[i]['y']) / L} if L > 0 else {'x': 1, 'y': 0}
            d = max(0, min(L, s - acc))
            return {'p': {'x': pts[i]['x'] + u['x'] * d, 'y': pts[i]['y'] + u['y'] * d}, 'u': u}
        acc += L
    return {'p': pts[-1], 'u': {'x': 1, 'y': 0}}


def cable_stations(t, thickness_at, o=None, chair_drop=None, cgs=False, figures='ram', **kw):
    """
    The chair-height stations of a tendon (office rule): every profile node, and exactly 1000 between them from each
    node on, the remainder before the next node kept as the one odd spacing (merged into the last metre when it is
    under 500). `figures` 'ram' (the default): at every profile node the figure exactly as entered in RAM Concept (mm,
    in the model's own reference - above the soffit, or below the surface - no chair drop, no rounding), and at the
    stations between them the tendon CGS above the soffit rounded to 5; 'chair': height = CGS above the soffit less
    the chair drop (the chair carries the underside of the duct), rounded to 5 and never above the slab (`cgs` gives
    the profile height itself).
    """
    o = opts(o, kw)
    chair_drop = o['chairDrop'] if o.get('chairDrop') is not None else (CAB['chairDrop'] if chair_drop is None else chair_drop)
    cgs = o.get('cgs', cgs)
    figures = o.get('figures', figures)
    if not t.get('heights'):
        return []
    st = [0]
    for i in range(1, len(t['pts'])):
        st.append(st[i - 1] + dist(t['pts'][i - 1], t['pts'][i]))
    ext = {e['i']: e['kind'] for e in RC.tendon_extremes(t)}
    stations = [0]
    for i in range(len(st) - 1):
        a, b = st[i], st[i + 1]
        L = b - a
        if L <= 1e-9:
            continue
        n = math.floor(L / CAB['step'] + 1e-9)
        tail = L - n * CAB['step']
        if n >= 1 and tail < CAB['minStation'] - 1e-9:
            n -= 1
        for k in range(1, n + 1):
            stations.append(a + k * CAB['step'])
        stations.append(b)
    out = []
    seen = set()
    for s in stations:
        key = js_round(s)
        if key in seen:
            continue
        seen.add(key)
        pu = along_tendon(t, s)
        p, u = pu['p'], pu['u']
        i_node = -1
        for i in range(len(st)):
            if abs(st[i] - s) < 1e-3:
                i_node = i
                break
        # (an anchor is an anchor, never a high / low point: the office profile flags come from the control points between)
        kind = '' if i_node < 0 else 'end' if i_node == 0 or i_node == len(st) - 1 else 'high' if ext.get(i_node) == 'H' else 'low' if ext.get(i_node) == 'L' else ''
        thks = t.get('thks')
        th = (thks[i_node] if (i_node >= 0 and thks and i_node < len(thks)) else None) or thickness_at(p)
        cg = RC.tendon_height_at(t, s)
        if cg is None:
            continue
        elevs = t.get('elevs')
        ram_v = elevs[i_node]['v'] if (figures == 'ram' and i_node >= 0 and elevs and i_node < len(elevs) and elevs[i_node]) else None
        if ram_v is not None:
            h = ram_v  # the RAM figure as it is
        else:
            h = cg if (figures == 'ram' or cgs) else cg - chair_drop
            h = max(0, min(h, th))
            h = js_round(h / CAB['roundH']) * CAB['roundH']
        out.append({'s': s, 'p': p, 'u': u, 'h': h, 'kind': kind, 'i': i_node, 'th': th})
    return out


def cable_extension(t):
    """The written extension (office rule): two live ends = the sum of both RAM figures; one = RAM's figure less 6 mm seating."""
    es = [v for v in (t.get('elongations') or []) if v is not None]
    if len(es) >= 2:
        return js_round(sum(es))
    if len(es) == 1:
        return max(0, js_round(es[0] - CAB['anchorSet']))
    return js_round(t['elongation']) if t.get('elongation') is not None else None


def cable_blocks(root, G):
    """The office anchor and tag blocks (geometry of the office template, in model mm at 1:100, scaled by G to the sheet scale)."""
    def P(pts):
        return [{'x': x * G, 'y': y * G} for x, y in pts]
    if 'LiveEnd' not in root.blocks:
        b = root.block('LiveEnd')
        b.pline(P([[90, -110], [0, -125], [0, 125], [90, 110]]), {'layer': '0'})
        b.pline(P([[300, 55], [300, -55], [310, -55], [310, 55]]), {'layer': '0', 'closed': True})
        b.pline(P([[90, -126], [107, -125], [109, -111], [109, 111], [107, 125], [90, 126]]), {'layer': '0'})
        b.pline(P([[310, 35], [800, 35], [800, -35], [310, -35]]), {'layer': '0', 'closed': True})
        b.pline(P([[195, -91], [205, -91], [205, 91], [195, 91]]), {'layer': '0', 'closed': True})
        b.circle(149 * G, 0, 12.5 * G, {'layer': '0'})
    if 'DeadEnd' not in root.blocks:
        b = root.block('DeadEnd')
        b.pline(P([[70, 35], [500, 35], [500, -35], [70, -35]]), {'layer': '0', 'closed': True})
        b.pline(P([[0, -125], [0, 125], [70, 125], [70, -125]]), {'layer': '0', 'closed': True})


def _live_count(t):
    return sum(1 for v in t['live'] if v)


def _seq_of(t, tendons):
    parts = (t.get('id') or '').split('-')
    n = _js_number(parts[1]) if len(parts) > 1 else None
    return n if n else _index_of(tendons, t) + 1


def ram_cables_sheet(model, level, meta, o=None, set_='latitude', variant='shop', **kw):
    """
    The cable sheet of one tendon direction from the RAM Concept model, in the office convention.
      variant 'design' (sheets 05 / 06): tendons, anchors, tags without extension, the high / low points with the
        CGS height of the profile - no chairs, no extension;
      variant 'shop' (07A / 07B): the chair heights at every station, the odd spacings dimensioned, extensions on
        the tags and in the schedule, chair / duct / quantity schedules and the stressing record.
    """
    o = opts(o, kw)
    set_ = o.get('set', o.get('set_', set_))
    variant = o.get('variant', variant)

    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        G = S / 100  # paper mm -> model mm; block geometry drawn for 1:100 scales with the sheet
        pt = level['ram']['pt']
        design = variant == 'design'
        fam = 'A' if set_ == 'latitude' else 'B'
        TH, TICK = CAB['txt'] * S, CAB['tick'] * S * 0.6
        root = sheet.blk.root
        root.text_style_def('PT-PROFILE', {'font': 'romans.shx', 'widthFactor': 0.75})
        cable_blocks(root, G)
        dim_station = {'txt': CAB['dimTxt'] * S, 'tsz': CAB['tick'] * S, 'asz': CAB['tick'] * S, 'exe': 1.2 * S, 'exo': 0.8 * S, 'gap': 0.8 * S, 'tad': 1, 'clrt': 2, 'clrd': 256, 'clre': 256, 'dec': 0, 'txsty': 'PT-PROFILE'}
        dim_spacing = {**dim_station, 'txt': CAB['dimTxt'] * 1.25 * S}
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False, 'regionLabels': False, 'ubarRegions': False})

        outline = level.get('outline') or []
        openings = [p for p in (R.region_polygon(o_) for o_ in (level.get('openings') or [])) if p and len(p) >= 3]
        zones = [z for z in (level.get('thickZones') or []) if z.get('polygon') and z.get('thickness')]
        thickness_at = thickness_fn(level)

        def outside_slab(p):
            return (len(outline) >= 3 and not point_in_polygon(p, outline)) or any(point_in_polygon(p, o_) for o_ in openings)
        tendons = [t for t in level['ram']['tendons'] if t.get('spanSet') == set_]
        # the figures written: RAM's own profile values at the high / low points (spec.cables.figures 'ram', the default) or the
        # chair heights (RAM's CGS height less the chair drop, rounded to 5; 'chair') - on the design sheets too
        figures = 'chair' if (model['spec'].get('cables') or {}).get('figures') == 'chair' else 'ram'
        ram_fig = figures == 'ram'
        samples_of = {id(t): cable_stations(t, thickness_at, cgs=False, figures=figures) for t in tendons}
        # marks: tendons of one strand count and one profile (high / low / end stations within 100 mm and 5 mm) share one
        # (always from the chair stations, so the design and shop sheets and the crossings plan name a tendon alike)
        mark_of = cable_marks_of(tendons, fam, thickness_at, figures)

        station_count = dim_count = skipped = no_profile = 0
        anchors = []
        chair_counts = {}
        rows_by_mark = {}
        rows = []
        for t in tendons:
            smp = samples_of[id(t)]
            if not t.get('heights'):
                no_profile += 1
            pl.pline(t['pts'], {'layer': f'Tendons-{fam}'})
            # the stations: a tick across the tendon, the height parallel to it; high / low points bigger, on their own
            # layers, with the circle on the point itself (design sheets: the high / low points only, as the profile)
            shown = [x for x in smp if x['kind'] == 'high' or x['kind'] == 'low'] if design else smp
            for x in shown:
                k = _index_of(smp, x)
                a, b = smp[max(k - 1, 0)]['p'], smp[min(k + 1, len(smp) - 1)]['p']
                L = dist(a, b)
                n = {'x': -(b['y'] - a['y']) / L, 'y': (b['x'] - a['x']) / L} if L > 1e-9 else {'x': 0, 'y': 1}
                suffix = '-HIGH' if x['kind'] == 'high' else '-LOW' if x['kind'] == 'low' else ''
                big = 1.35 if suffix else 1
                pl.line({'x': x['p']['x'] - n['x'] * TICK * big, 'y': x['p']['y'] - n['y'] * TICK * big}, {'x': x['p']['x'] + n['x'] * TICK * big, 'y': x['p']['y'] + n['y'] * TICK * big}, {'layer': f'Hline-Profile-{fam}{suffix}'})
                if suffix:
                    pl.circle(x['p'], TICK * 0.55, {'layer': f'PT-HighLow-{fam}'})
                off = TH * 0.35 * big
                pl.text({'x': x['p']['x'] + n['x'] * off, 'y': x['p']['y'] + n['y'] * off}, _s(x['h']), {'layer': f'Text-Profile-{fam}{suffix}', 'h': CAB['txt'], 'rot': _ang({'x': n['y'], 'y': -n['x']}), 'align': 'C', 'valign': 'B', **PT_TEXT})
                station_count += 1
                if not design:
                    chair_counts[x['h']] = (chair_counts.get(x['h']) or 0) + 1
            # the odd spacings: a dimension along the tendon between consecutive stations, except the regular metre
            if not design:
                for k in range(len(smp) - 1):
                    a, b = smp[k]['p'], smp[k + 1]['p']
                    gap = smp[k + 1]['s'] - smp[k]['s']
                    if gap >= CAB['dimSkip'][0] and gap <= CAB['dimSkip'][1]:
                        skipped += 1
                        continue
                    L = dist(a, b)
                    if L < 1:
                        continue
                    n = {'x': -(b['y'] - a['y']) / L, 'y': (b['x'] - a['x']) / L}
                    m = {'x': (a['x'] + b['x']) / 2 - n['x'] * TH * 2.5, 'y': (a['y'] + b['y']) / 2 - n['y'] * TH * 2.5}
                    pl.dimension(a, b, m, {'style': 'PT-DIM-STATION', 'styleDef': dim_station, 'layer': f'Dimensions-Profile-{fam}'})
                    dim_count += 1
            # the anchors: the live-end block where a jack sits in the model, the dead-end block elsewhere
            p0 = t['pts'][0]
            p1 = t['pts'][1] if len(t['pts']) > 1 else p0
            q0 = t['pts'][-1]
            q1 = t['pts'][-2] if len(t['pts']) > 1 else q0
            out0, out1 = _ang({'x': p0['x'] - p1['x'], 'y': p0['y'] - p1['y']}), _ang({'x': q0['x'] - q1['x'], 'y': q0['y'] - q1['y']})
            cut = t.get('cut') or [False, False]
            for p, a, live, is_cut in [[p0, out0, t['live'][0], cut[0]], [q0, out1, t['live'][1], cut[1]]]:
                Q = pl.P(p)
                if is_cut:
                    # the tendon continues on the next part / body: a break mark and CONT. instead of an anchor
                    ux, uy = math.cos((a * math.pi) / 180), math.sin((a * math.pi) / 180)
                    pl.line({'x': p['x'] - uy * TICK * 1.6, 'y': p['y'] + ux * TICK * 1.6}, {'x': p['x'] + uy * TICK * 1.6, 'y': p['y'] - ux * TICK * 1.6}, {'layer': f'Details-{fam}'})
                    pl.text({'x': p['x'] + ux * TH * 0.8, 'y': p['y'] + uy * TH * 0.8}, 'CONT.', {'layer': f'Text-Profile-{fam}', 'h': CAB['txt'], 'rot': _ang({'x': ux, 'y': uy}), 'align': 'C', 'valign': 'B', **PT_TEXT})
                    continue
                sheet.blk.insert('LiveEnd' if live else 'DeadEnd', Q['x'], Q['y'], {'rot': a + 180, 'layer': f'Details-{fam}'})
            # the tag on the tendon line, out of its live end (the start when both or neither are live): five cells on a
            # leader; where the box would sit in the slab it steps 250 aside towards the outside
            ext = None if design else cable_extension(t)
            length_m = to_fixed(t['length'] / 1000, 1)
            tag_at, tag_ang = ([q0, out1] if cut[0] and not cut[1] else [p0, out0] if cut[1] and not cut[0] else [p0, out0] if t['live'][0] or not t['live'][1] else [q0, out1])
            u = {'x': math.cos((tag_ang * math.pi) / 180), 'y': math.sin((tag_ang * math.pi) / 180)}
            n = {'x': -u['y'], 'y': u['x']}
            xs = [v * G for v in CAB['tagXs']]
            ins = tag_at
            centre = {'x': tag_at['x'] + u['x'] * (xs[0] + xs[5]) / 2, 'y': tag_at['y'] + u['y'] * (xs[0] + xs[5]) / 2}
            if not outside_slab(centre):
                probe = 3000
                out_pos = outside_slab({'x': centre['x'] + n['x'] * probe, 'y': centre['y'] + n['y'] * probe})
                out_neg = outside_slab({'x': centre['x'] - n['x'] * probe, 'y': centre['y'] - n['y'] * probe})
                sign = 1 if out_pos and not out_neg else -1 if out_neg and not out_pos else 1
                ins = {'x': tag_at['x'] + n['x'] * CAB['tagClear'] * G * sign, 'y': tag_at['y'] + n['y'] * CAB['tagClear'] * G * sign}
                pl.line(tag_at, ins, {'layer': f'Details-{fam}'})

            def at(x, y, ins=ins, u=u, n=n):
                return {'x': ins['x'] + u['x'] * x + n['x'] * y, 'y': ins['y'] + u['y'] * x + n['y'] * y}
            hh = CAB['tagHalf'] * G
            pl.line(at(0, 0), at(CAB['tagLead'] * G, 0), {'layer': f'Details-{fam}'})
            pl.line(at(xs[0], -hh), at(xs[5], -hh), {'layer': f'Details-{fam}'})
            pl.line(at(xs[0], hh), at(xs[5], hh), {'layer': f'Details-{fam}'})
            for x in xs:
                pl.line(at(x, -hh), at(x, hh), {'layer': f'Details-{fam}'})
            cells = [_s(t['strands']), '' if ext is None else _s(ext), length_m, mark_of.get(id(t)), _s(_seq_of(t, tendons))]
            for i, v in enumerate(cells):
                if v:
                    pl.text(at((xs[i] + xs[i + 1]) / 2, -100 * G), v, {'layer': f'Details-{fam}', 'h': CAB['txt'], 'rot': tag_ang, 'align': 'C', 'valign': 'B', 'color': 3, **PT_TEXT})
            if not cut[0]:
                anchors.append({'p': p0, 'live': t['live'][0]})
            if not cut[1]:
                anchors.append({'p': q0, 'live': t['live'][1]})
            # one schedule row per mark
            mark = mark_of.get(id(t))
            row = rows_by_mark.get(mark)
            if not row:
                row = {'mark': mark, 'qty': 0, 'seqs': [], 'strands': t['strands'], 'length': length_m, 'live': _live_count(t), 'elong': '' if ext is None else ext, 'chairs': 0, 'type': '', 'guts': '', 'jack': '', '_t': t}
                rows_by_mark[mark] = row
                rows.append(row)
            row['qty'] += 1
            row['seqs'].append(_seq_of(t, tendons))
            row['chairs'] += len(smp)
        # the strand line of the schedule: type, breaking load and the jacking force per strand
        area, fpu = pt.get('strandArea') or 140, pt.get('fpu') or 1860
        jack_ratio = ((tendons[0].get('jackStress') if tendons else None) or pt.get('jackStress') or 0.78 * fpu) / fpu
        dia = STRAND_DIA.get(js_round(area * 10) / 10) or STRAND_DIA.get(js_round(area)) or '15.24'
        for r in rows:
            chunks = []
            seqs = sorted(r['seqs'])
            for i in range(0, len(seqs), 6):
                chunks.append(','.join(_s(v) for v in seqs[i:i + 6]))
            r['anchors'] = ' / '.join(chunks)
            r['type'] = dia
            r['guts'] = js_round((area * fpu) / 1000)
            r['jack'] = js_round((area * jack_ratio * fpu) / 1000)
            del r['_t']
        # the anchor spacing at every face line, dimensioned perpendicular to the tendons, outside the slab
        # (the tendons' own direction on the sheet, not the family name: a plan turned 90° runs the latitude set vertically)
        runs_along_x = sum((1 if abs(t['pts'][-1]['x'] - t['pts'][0]['x']) >= abs(t['pts'][-1]['y'] - t['pts'][0]['y']) else -1) for t in tendons) >= 0
        axis, across = ('y', 'x') if runs_along_x else ('x', 'y')
        groups = {}
        for a in anchors:
            groups.setdefault(js_round(a['p'][across] / 2000), []).append(a['p'])
        for g in groups.values():
            if len(g) < 2:
                continue
            g.sort(key=lambda p: p[axis])
            for i in range(len(g) - 1):
                p, q = g[i], g[i + 1]
                if abs(q[axis] - p[axis]) < 200:
                    continue
                mid = {'x': (p['x'] + q['x']) / 2, 'y': (p['y'] + q['y']) / 2}
                perp = {'x': 1, 'y': 0} if runs_along_x else {'x': 0, 'y': 1}
                # the dimension line halfway between the anchors and the tag blocks (the tag starts `tagXs[0]` out of the
                # anchor): it never sits over the tags
                d = (CAB['tagXs'][0] * G) / 2
                plus = {'x': mid['x'] + perp['x'] * d, 'y': mid['y'] + perp['y'] * d}
                minus = {'x': mid['x'] - perp['x'] * d, 'y': mid['y'] - perp['y'] * d}
                dl = plus if outside_slab(plus) and not outside_slab(minus) else minus
                pl.dimension(p, q, dl, {'style': 'PT-DIM-SPACING', 'styleDef': dim_spacing, 'angle': 90 if runs_along_x else 0, 'layer': f'Dimensions-Sec-{fam}'})

        # ---- schedule and details
        dir_title = 'DIRECTION A (LATITUDE)' if fam == 'A' else 'DIRECTION B (LONGITUDE)'
        cols = [
            {'key': 'mark', 'title': 'MARK\nNO.', 'w': 16}, {'key': 'qty', 'title': 'QTY', 'w': 10}, {'key': 'anchors', 'title': 'ANCHOR NO.\n(SEE NOTE 6)', 'w': 30, 'align': 'L'}, {'key': 'strands', 'title': 'NO. OF\nSTRANDS', 'w': 14},
            {'key': 'length', 'title': 'LENGTH\n(M)', 'w': 16}, {'key': 'live', 'title': 'NO. OF\nLIVE ENDS', 'w': 16},
            *([] if design else [{'key': 'elong', 'title': 'EXTENSION\n(MM)', 'w': 18}]),
            {'key': 'type', 'title': 'STRAND\nTYPE', 'w': 16}, {'key': 'guts', 'title': 'GUTS\n(KN)', 'w': 16},
            *([] if design else [{'key': 'jack', 'title': 'JACKING FORCE\nPER STRAND (KN)', 'w': 33}]),
        ]
        W = sum(c['w'] for c in cols)
        if design:
            cols[2]['w'] += 185 - W
        elif W != 185:
            cols[2]['w'] += 185 - W
        strands = sum(t['strands'] for t in tendons)
        live_ends = len([a for a in anchors if a['live']])
        strand_m = sum((t['length'] / 1000) * t['strands'] for t in tendons)
        kg_per_m = (area * 7850) / 1e6
        details_used = 2
        if not design:
            # 1: chair height schedule (the dead-end chairs, 300 wide, on their own rows)
            d1 = sheet.detail_box(0, 'PROFILE FIGURE SCHEDULE' if ram_fig else 'CHAIR HEIGHT SCHEDULE', '')
            base = level['thickness']
            dead = {}
            for t in tendons:
                tcut = t.get('cut') or []
                for p, live, is_cut in [[t['pts'][0], t['live'][0], tcut[0] if len(tcut) > 0 else None], [t['pts'][-1], t['live'][1], tcut[1] if len(tcut) > 1 else None]]:
                    if live or is_cut:
                        continue
                    th = thickness_at(p)
                    h = js_round(max(0, th - base / 2 - 10 if th > base + 1e-6 else base / 2 - 10))
                    dead[h] = (dead.get(h) or 0) + 1
            chair_rows = [{'h': _s(h), 'n': n} for h, n in sorted(chair_counts.items(), key=lambda e: e[0])]
            for h, n in sorted(dead.items(), key=lambda e: e[0]):
                chair_rows.append({'h': f'{_s(h)} DEAD END', 'n': n})
            chair_cols = [{'key': 'h', 'title': 'HEIGHT\n(mm)', 'w': 26}, {'key': 'n', 'title': 'QTY', 'w': 14}]
            per_col = max(1, math.floor((d1['h'] - 18) / 3.2))
            left, cx0 = chair_rows, d1['x'] + 3
            while len(left) and cx0 + 40 <= d1['x'] + d1['w']:
                res = sheet.table(cx0, d1['y'] + d1['h'] - 10, chair_cols, left, {'maxRows': per_col, 'headH': 6, 'rowH': 3.2, 'h': 1.3})
                left = res['leftover']
                cx0 += 44
            sheet.pp.text(d1['x'] + 3, d1['y'] + 2, 'FIGURES AS ENTERED IN RAM CONCEPT AT THE PROFILE POINTS, CGS ABOVE THE SOFFIT AT THE 1000 STATIONS. DEAD-END CHAIRS 300 mm WIDE (SLAB / 2 - 10, OR DROP - SLAB / 2 - 10).' if ram_fig else f"DEAD-END CHAIRS 300 mm WIDE (SLAB / 2 - 10, OR DROP - SLAB / 2 - 10). CHAIR SET {CAB['chairDrop']} mm BELOW THE TENDON CENTRELINE.", {'layer': 'NOTES', 'h': 1.4})
            # 2: duct schedule and bill of quantities
            d2 = sheet.detail_box(1, 'DUCT SCHEDULE AND BILL OF QUANTITIES', '')

            def duct_len(t):
                return max(0, t['length'] / 1000 - (1 if _live_count(t) == 1 else 0))
            small = [t for t in tendons if t['strands'] <= CAB['smallDuctMax']]
            large = [t for t in tendons if t['strands'] > CAB['smallDuctMax']]
            duct_cols = [{'key': 'a', 'title': 'DUCT SIZE\n(mm)', 'w': 24}, {'key': 'b', 'title': 'STRANDS', 'w': 20}, {'key': 'c', 'title': 'TENDONS', 'w': 18}, {'key': 'd', 'title': 'LENGTH\n(m)', 'w': 22}]
            r1 = sheet.table(d2['x'] + 3, d2['y'] + d2['h'] - 10, duct_cols, [
                {'a': CAB['ductSmall'], 'b': f"UP TO {CAB['smallDuctMax']}", 'c': len(small), 'd': js_round(sum(duct_len(t) for t in small))},
                {'a': CAB['ductLarge'], 'b': f"OVER {CAB['smallDuctMax']}", 'c': len(large), 'd': js_round(sum(duct_len(t) for t in large))},
            ], {'headH': 6, 'rowH': 3.5, 'h': 1.4})
            net_area = abs(polygon_area(outline)) / 1e6 - sum(abs(polygon_area(o_)) / 1e6 for o_ in openings)
            cutting = sum(t['strands'] * (t['length'] / 1000 + (CAB['anchorAllowance'] / 1000) * max(1, _live_count(t))) for t in tendons)
            kg = cutting * kg_per_m
            boq_cols = [{'key': 'a', 'title': 'ITEM', 'w': 56, 'align': 'L'}, {'key': 'b', 'title': 'VALUE', 'w': 28, 'align': 'R'}]
            sheet.table(d2['x'] + 3, r1['y'] - 4, boq_cols, [
                {'a': 'TENDONS', 'b': len(tendons)}, {'a': 'STRANDS', 'b': strands}, {'a': 'STRAND LENGTH (CUT, 300 PER ANCHOR)', 'b': f'{js_round(cutting)} m'},
                {'a': 'NET SLAB AREA (OPENINGS DEDUCTED)', 'b': f'{to_fixed(net_area, 1)} m2'}, {'a': 'STRAND WEIGHT', 'b': f'{js_round(kg)} kg'},
                {'a': 'RATE', 'b': f"{to_fixed(kg / net_area, 2) if net_area else '-'} kg/m2"}, {'a': 'RATE', 'b': f"{to_fixed(cutting / net_area, 2) if net_area else '-'} strand-m/m2"},
            ], {'headH': 5, 'rowH': 3.2, 'h': 1.3})
            # 3: stressing record (unless the schedule needs the box for its continuation)
            max_rows = math.floor((sheet.L['schedule']['h'] - 23) / 3)
            if len(rows) > max_rows:
                details_used = 2
            else:
                d3 = sheet.detail_box(2, 'STRESSING RECORD', '')
                rec_cols = [{'key': 'a', 'title': 'TENDON', 'w': 22}, {'key': 'm', 'title': 'MARK', 'w': 16}, {'key': 'b', 'title': 'DATE', 'w': 24}, {'key': 'c', 'title': 'GAUGE\n(bar)', 'w': 22}, {'key': 'd', 'title': 'EXT.\nCALC.', 'w': 22}, {'key': 'e', 'title': 'EXT.\nMEAS.', 'w': 22}, {'key': 'f', 'title': '%', 'w': 14}, {'key': 'g', 'title': 'SIGN', 'w': max(20, d3['w'] - 6 - 142)}]
                sheet.table(d3['x'] + 3, d3['y'] + d3['h'] - 10, rec_cols, [{'a': t.get('id'), 'm': mark_of.get(id(t)), 'd': cable_extension(t) if cable_extension(t) is not None else ''} for t in tendons], {'maxRows': math.floor((d3['h'] - 18) / 3.2), 'headH': 6, 'rowH': 3.2, 'h': 1.3})
                details_used = 3
        else:
            d1 = sheet.detail_box(0, 'PROFILE POINTS', '')
            pp = sheet.pp
            for i, h in enumerate(['THE FIGURE AT EVERY HIGH / LOW POINT (THE CIRCLE MARKS THE POINT ITSELF) IS THE TENDON PROFILE VALUE IN mm EXACTLY AS ENTERED IN RAM CONCEPT, IN THE REFERENCE OF THE MODEL (ABOVE THE SLAB SOFFIT, OR BELOW THE SLAB SURFACE AT THE SUPPORTS). THE FIGURES AT EVERY STATION BETWEEN THEM ARE GIVEN ON THE SHOP DRAWINGS.' if ram_fig else f"THE FIGURE AT EVERY HIGH / LOW POINT (THE CIRCLE MARKS THE POINT ITSELF) IS THE CHAIR HEIGHT IN mm: THE TENDON CGS HEIGHT ABOVE THE SLAB SOFFIT AS DESIGNED IN RAM CONCEPT LESS {CAB['chairDrop']} mm, ROUNDED TO {CAB['roundH']}. THE CHAIR HEIGHTS AT EVERY STATION BETWEEN THEM ARE GIVEN ON THE SHOP DRAWINGS.",
                                   'DESIGN DRAWING: STRAND COUNTS, PATHS, STRESSING ENDS AND PROFILE POINTS ONLY. EXTENSIONS, JACKING FORCES AND CHAIRS ARE ON THE SHOP DRAWINGS.']):
                pp.mtext(d1['x'] + 4, d1['y'] + d1['h'] - 12 - i * 14, h, {'layer': 'NOTES', 'h': 1.7, 'width': d1['w'] - 8})
            d2 = sheet.detail_box(1, 'TENDON SYMBOLS', 'N.T.S.')
            det = D.tendon_legend()
            det.draw(sheet.detail_pen(d2, 12, det.bbox))
        cover = model['spec'].get('cover') or 25
        drop = max(z['thickness'] for z in zones) if len(zones) else None
        if design:
            notes = [
                common_notes(model, level)[0],
                f"PT SYSTEM: {_s(pt.get('system') or '')} - {_s(pt.get('ductType') or 'bonded')} FLAT DUCT {(_s(pt.get('ductWidth')) + ' x ' + _s(pt.get('ductHeight')) + ' mm') if pt.get('ductWidth') else ''}, {_s(pt.get('strandsPerDuct') or '')} STRANDS PER DUCT MAX. STRAND {dia} mm, Aps = {_s(area)} mm², fpu = {js_round(fpu)} MPa.",
                f"TENDON PATHS, STRAND COUNTS, STRESSING ENDS AND THE HIGH / LOW POINTS OF THE PROFILE ARE READ FROM THE RAM CONCEPT MODEL ({station_count} PROFILE POINTS ON THIS SHEET{('; ' + _s(no_profile) + ' TENDONS CARRY NO PROFILE IN THE MODEL') if no_profile else ''}). THE TAG ON EVERY TENDON READS STRANDS / LENGTH / MARK / No.; TENDONS OF ONE STRAND COUNT AND ONE PROFILE SHARE A MARK. THE OTHER DIRECTION IS ON ITS OWN SHEET.",
                'DESIGN DRAWING - NOT FOR FABRICATION. EXTENSIONS, JACKING FORCES AND CHAIR HEIGHTS ARE GIVEN ON THE SHOP DRAWINGS.',
            ]
        else:
            notes = [
                *CAB_NOTES,
                f"SLAB {_s(level['thickness'])}{(' / DROP ' + _s(drop)) if drop else ''} · COVER TOP {_s(cover)} BOTTOM {_s(cover)} · {'THE FIGURES AT THE HIGH / LOW POINTS ARE THE PROFILE VALUES EXACTLY AS ENTERED IN RAM CONCEPT (ABOVE THE SOFFIT, OR BELOW THE SURFACE, AS IN THE MODEL); THE FIGURES AT THE 1000 STATIONS BETWEEN THEM ARE THE TENDON CGS ABOVE THE SOFFIT' if ram_fig else ('CHAIR SET ' + str(CAB['chairDrop']) + ' mm BELOW THE TENDON CENTRELINE')}. STRAND {dia} mm, Aps = {_s(area)} mm², fpu = {js_round(fpu)} MPa, JACKING {js_round(jack_ratio * 100)} % fpu. THE TAG ON EVERY TENDON READS STRANDS / EXTENSION / LENGTH / MARK / No. THE OTHER DIRECTION IS ON ITS OWN SHEET.{(' ' + _s(no_profile) + ' TENDONS CARRY NO PROFILE IN THE MODEL: THEIR CHAIRS ARE TO BE SET FROM THE RAM PROFILE REPORT.') if no_profile else ''}",
            ]
        return {
            'rows': rows, 'cols': cols, 'rowH': 3, 'scheduleTitle': f"TENDON SCHEDULE ({fam}){' - DESIGN' if design else ''}", 'detailsUsed': details_used,
            'totals': f"{len(tendons)} TENDONS · {_s(strands)} STRANDS · {js_round(strand_m)} m STRAND · {live_ends} LIVE ENDS{'' if design else ' · ' + _s(station_count) + ' CHAIRS'}",
            'weight': js_round(strand_m * kg_per_m),
            'planTitles': [f'PT TENDON LAYOUT - {dir_title} - DESIGN (HIGH / LOW POINTS)' if design else f'TENDON PROFILES - {dir_title}' if ram_fig else f'CHAIR HEIGHTS - {dir_title}'],
            'general': notes,
            'assumptions': level_assumptions(model, level)[:3],
            'legend': [
                [f'Tendons-{fam}', f'TENDON, {dir_title}', 'thick'],
                [f'Text-Profile-{fam}-HIGH', 'HIGH POINT - RAM PROFILE VALUE AS ENTERED' if ram_fig else f"HIGH POINT CHAIR HEIGHT (CGS - {CAB['chairDrop']})", 'line'],
                [f'Text-Profile-{fam}-LOW', 'LOW POINT - RAM PROFILE VALUE AS ENTERED' if ram_fig else f"LOW POINT CHAIR HEIGHT (CGS - {CAB['chairDrop']})", 'line'],
                *([] if design else [[f'Text-Profile-{fam}', 'INTERMEDIATE CGS ABOVE SOFFIT (1000 STATIONS)' if ram_fig else 'INTERMEDIATE CHAIR HEIGHT (1000 STATIONS)', 'line'], [f'Dimensions-Profile-{fam}', 'ODD STATION SPACING', 'line']]),
                [f'Details-{fam}', 'LIVE END (BLOCK) / DEAD END (BLOCK) / TENDON TAG', 'line'],
                [f'Dimensions-Sec-{fam}', 'ANCHOR SPACING AT THE FACE', 'line'],
                ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL', 'WALL BELOW', 'thick'],
            ],
            'checks': [f'{skipped} regular 1000 mm station spacings left undimensioned; {dim_count} odd spacings dimensioned.'] if skipped else [],
        }
    return draw


def cable_marks_of(tendons, fam, thickness_at, figures='ram'):
    """The marks of one direction: tendons of one strand count and one profile (chair stations) share a mark; keyed by tendon (its id())."""
    sig_to_mark = {}
    mark_of = {}
    for t in tendons:
        smp = cable_stations(t, thickness_at, figures=figures)
        flags = ','.join(x['kind'] + _s(js_round(x['s'] / 100)) + ':' + _s(x['h']) for x in smp if x['kind'])
        sig = f"{_s(t['strands'])}|{flags}|{'' if len(smp) else js_round(t['length'] / 100)}"
        mark = sig_to_mark.get(sig)
        if not mark:
            mark = f'{fam}.{_pad2(len(sig_to_mark) + 1)}'
            sig_to_mark[sig] = mark
        mark_of[id(t)] = mark
    return mark_of


def thickness_fn(level):
    """Local thickness at a plan point: the thickened zone it falls in, else the slab."""
    zones = [z for z in (level.get('thickZones') or []) if z.get('polygon') and z.get('thickness')]

    def at(p):
        for z in zones:
            if point_in_polygon(p, z['polygon']):
                return z['thickness']
        return level['thickness']
    return at


# ------------------------------------------------------------------ tendon crossings: which tendon passes over
CROSS = {'duct': 20, 'tol': 10, 'endClear': 50, 'gapPaper': 1.6}


def _seg_cross(a0, a1, b0, b1):
    dx1, dy1, dx2, dy2 = a1['x'] - a0['x'], a1['y'] - a0['y'], b1['x'] - b0['x'], b1['y'] - b0['y']
    den = dx1 * dy2 - dy1 * dx2
    if abs(den) < 1e-12:
        return None
    ex, ey = b0['x'] - a0['x'], b0['y'] - a0['y']
    ta, tb = (ex * dy2 - ey * dx2) / den, (ex * dy1 - ey * dx1) / den
    if ta < -1e-9 or ta > 1 + 1e-9 or tb < -1e-9 or tb > 1 + 1e-9:
        return None
    ta, tb = max(0, min(1, ta)), max(0, min(1, tb))
    return {'x': a0['x'] + ta * dx1, 'y': a0['y'] + ta * dy1, 'ta': ta, 'tb': tb}


def tendon_crossings(level, thickness_at=None):
    """
    Every crossing of two tendons in plan (office rule): where it is, the station on each tendon, each tendon's depth
    from the top there (from the same profile the chair heights come from), the gap and which one passes over.
    Clash = gap under `tol` (10 mm: the two ducts sit at one level); tight = under the duct height (20) but no clash.
    An end standing on another tendon (within `endClear`) is not a crossing.
    """
    if thickness_at is None:
        thickness_at = thickness_fn(level)
    tendons = [t for t in ((level.get('ram') or {}).get('tendons') or []) if t.get('heights') and len(t['pts']) >= 2]
    geo = []
    for t in tendons:
        st = [0]
        for i in range(1, len(t['pts'])):
            st.append(st[i - 1] + dist(t['pts'][i - 1], t['pts'][i]))
        geo.append({'t': t, 'st': st, 'total': st[-1], 'bb': bbox(t['pts'])})
    out = []
    for i in range(len(geo)):
        gi = geo[i]
        for j in range(i + 1, len(geo)):
            gj = geo[j]
            if gi['bb']['maxX'] < gj['bb']['minX'] or gj['bb']['maxX'] < gi['bb']['minX'] or gi['bb']['maxY'] < gj['bb']['minY'] or gj['bb']['maxY'] < gi['bb']['minY']:
                continue
            seen = set()
            for a in range(len(gi['t']['pts']) - 1):
                for b in range(len(gj['t']['pts']) - 1):
                    hit = _seg_cross(gi['t']['pts'][a], gi['t']['pts'][a + 1], gj['t']['pts'][b], gj['t']['pts'][b + 1])
                    if not hit:
                        continue
                    sa = gi['st'][a] + hit['ta'] * (gi['st'][a + 1] - gi['st'][a])
                    sb = gj['st'][b] + hit['tb'] * (gj['st'][b + 1] - gj['st'][b])
                    if sa < CROSS['endClear'] or sa > gi['total'] - CROSS['endClear'] or sb < CROSS['endClear'] or sb > gj['total'] - CROSS['endClear']:
                        continue
                    key = f"{js_round(hit['x'])},{js_round(hit['y'])}"
                    if key in seen:
                        continue
                    seen.add(key)
                    pt = {'x': hit['x'], 'y': hit['y']}
                    th = thickness_at(pt)
                    ha, hb = RC.tendon_height_at(gi['t'], sa), RC.tendon_height_at(gj['t'], sb)
                    if ha is None or hb is None:
                        continue
                    da, db = js_round(th - ha), js_round(th - hb)
                    gap = abs(da - db)
                    over = 'a' if da < db else 'b' if db < da else '='
                    out.append({'pt': pt, 'a': gi['t'], 'b': gj['t'], 'sa': sa, 'sb': sb, 'da': da, 'db': db, 'gap': gap, 'over': over, 'clash': gap < CROSS['tol'], 'tight': gap >= CROSS['tol'] and gap < CROSS['duct']})
    return out


def _cut_tendon(t, cuts, half):
    """The tendon's polyline with a gap of `half` each side of every station in `cuts` taken out."""
    st = [0]
    for i in range(1, len(t['pts'])):
        st.append(st[i - 1] + dist(t['pts'][i - 1], t['pts'][i]))
    total = st[-1]
    gaps = []
    for s in sorted(cuts):
        a, b = max(0, s - half), min(total, s + half)
        if gaps and a <= gaps[-1][1]:
            gaps[-1][1] = max(gaps[-1][1], b)
        else:
            gaps.append([a, b])
    keep = []
    u = 0
    for a, b in gaps:
        if a > u + 1e-6:
            keep.append([u, a])
        u = b
    if total > u + 1e-6:
        keep.append([u, total])
    pieces = [[along_tendon(t, u0)['p'], *[p for k, p in enumerate(t['pts']) if u0 + 1e-6 < st[k] and st[k] < u1 - 1e-6], along_tendon(t, u1)['p']] for u0, u1 in keep]
    return [pc for pc in pieces if len(pc) >= 2]


def ram_crossings_sheet(model, level, meta):
    """
    The crossings sheet (office convention): both directions on one plan, the tendon that passes over drawn
    continuous and the one under broken at the crossing, the gap in mm at every crossing with the family on top,
    tight gaps in yellow, clashes in a red circle; the marks at both ends of every tendon; the clashes and tight
    crossings listed in the schedule.
    """
    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        TH = CAB['txt'] * S
        sheet.blk.root.text_style_def('PT-PROFILE', {'font': 'romans.shx', 'widthFactor': 0.75})
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False, 'regionLabels': False, 'ubarRegions': False})
        thickness_at = thickness_fn(level)

        def fam_of(t):
            return 'A' if t.get('spanSet') == 'latitude' else 'B'
        tendons_all = level['ram']['tendons']
        marks = {**cable_marks_of([t for t in tendons_all if t.get('spanSet') == 'latitude'], 'A', thickness_at), **cable_marks_of([t for t in tendons_all if t.get('spanSet') != 'latitude'], 'B', thickness_at)}
        crossings = tendon_crossings(level, thickness_at)
        under = {}
        for c in crossings:
            if c['over'] == 'a':
                under.setdefault(id(c['b']), []).append(c['sb'])
            elif c['over'] == 'b':
                under.setdefault(id(c['a']), []).append(c['sa'])
        half = max(200, CROSS['gapPaper'] * S)
        for t in tendons_all:
            if len(t['pts']) < 2:
                continue
            layer = f'PT-Cross-{fam_of(t)}'
            for pc in _cut_tendon(t, under.get(id(t)) or [], half):
                pl.pline(pc, {'layer': layer})
            for end, nxt in [[t['pts'][0], t['pts'][1]], [t['pts'][-1], t['pts'][-2]]]:
                L = dist(end, nxt) or 1
                u = {'x': (end['x'] - nxt['x']) / L, 'y': (end['y'] - nxt['y']) / L}
                pl.text({'x': end['x'] + u['x'] * TH * 2.2, 'y': end['y'] + u['y'] * TH * 2.2}, marks.get(id(t)) or t.get('id'), {'layer': 'PT-Cross-Mark', 'h': CAB['txt'] * 0.8, 'rot': _ang(u), 'align': 'C', 'valign': 'M', **PT_TEXT})
        for c in crossings:
            if c['clash']:
                pl.circle(c['pt'], TH * 1.3, {'layer': 'PT-Cross-Clash'})
                pl.text({'x': c['pt']['x'], 'y': c['pt']['y'] + TH * 1.6}, f"CLASH {_s(c['gap'])}", {'layer': 'PT-Cross-Clash', 'h': CAB['txt'] * 0.8, 'align': 'C', 'valign': 'B', **PT_TEXT})
            else:
                top = c['a'] if c['over'] == 'a' else c['b']
                pl.text({'x': c['pt']['x'] + TH * 0.45, 'y': c['pt']['y'] + TH * 0.45}, f"{fam_of(top)} {_s(c['gap'])}", {'layer': 'PT-Cross-Tight' if c['tight'] else 'PT-Cross-Gap', 'h': CAB['txt'] * (0.8 if c['tight'] else 0.65), 'align': 'L', 'valign': 'B', **PT_TEXT})
        clashes = [c for c in crossings if c['clash']]
        tight = [c for c in crossings if c['tight']]

        def row_of(c):
            return {'a': marks.get(id(c['a'])) or c['a'].get('id'), 'b': marks.get(id(c['b'])) or c['b'].get('id'), 'ida': c['a'].get('id'), 'idb': c['b'].get('id'), 'grid': grid_ref(level, bbox([c['pt']])), 'da': c['da'], 'db': c['db'], 'gap': c['gap'], 'over': '-' if c['over'] == '=' else fam_of(c['a'] if c['over'] == 'a' else c['b']), 'status': 'CLASH' if c['clash'] else 'TIGHT'}
        rows = [row_of(c) for c in [*clashes, *tight]]
        cols = [
            {'key': 'a', 'title': 'MARK\nA', 'w': 16}, {'key': 'ida', 'title': 'TENDON\nA', 'w': 18}, {'key': 'b', 'title': 'MARK\nB', 'w': 16}, {'key': 'idb', 'title': 'TENDON\nB', 'w': 18}, {'key': 'grid', 'title': 'GRID', 'w': 24},
            {'key': 'da', 'title': 'DEPTH A\n(mm)', 'w': 18}, {'key': 'db', 'title': 'DEPTH B\n(mm)', 'w': 18}, {'key': 'gap', 'title': 'GAP\n(mm)', 'w': 16}, {'key': 'over', 'title': 'OVER', 'w': 15}, {'key': 'status', 'title': 'STATUS', 'w': 26},
        ]
        # 1: legend of the plan; 2: how to read it and the count per direction
        d1 = sheet.detail_box(0, 'LEGEND', 'N.T.S.')
        pp = sheet.pp
        legend = [
            ['PT-Cross-A', 'line', 'CONTINUOUS LINE = THE TENDON THAT PASSES OVER (A = DIRECTION A / LATITUDE, B = DIRECTION B / LONGITUDE)'],
            ['PT-Cross-B', 'broken', 'BROKEN LINE = THE TENDON THAT PASSES UNDER (BROKEN AT THE CROSSING)'],
            ['PT-Cross-Gap', 'circle', 'FIGURE AT THE CROSSING = THE DIRECTION ON TOP AND THE VERTICAL GAP BETWEEN THE TWO DUCT CENTRES, mm'],
            ['PT-Cross-Tight', 'circle', f"YELLOW FIGURE = TIGHT: GAP UNDER THE DUCT HEIGHT ({CROSS['duct']} mm) - THE LOWER DUCT BENDS A LITTLE"],
            ['PT-Cross-Clash', 'circle', f"RED CIRCLE = CLASH: GAP UNDER {CROSS['tol']} mm, THE TWO DUCTS SIT AT THE SAME LEVEL - THE PROFILE IS TO BE CORRECTED"],
            ['PT-Cross-Mark', 'text', 'MARK AT BOTH ENDS OF EVERY TENDON (AS ON THE CABLE SHEETS)'],
        ]
        for i, (layer, kind, text) in enumerate(legend):
            y, x = d1['y'] + d1['h'] - 14 - i * 6, d1['x'] + 4
            if kind == 'line':
                pp.line(x, y + 0.6, x + 10, y + 0.6, {'layer': layer})
            elif kind == 'broken':
                pp.line(x, y + 0.6, x + 3.5, y + 0.6, {'layer': layer})
                pp.line(x + 6.5, y + 0.6, x + 10, y + 0.6, {'layer': layer})
            elif kind == 'circle':
                pp.circle(x + 5, y + 0.6, 1.2, {'layer': layer})
            else:
                pp.text(x + 5, y, 'A.01', {'layer': layer, 'h': 1.6, 'align': 'C'})
            pp.mtext(x + 13, y + 2.2, text, {'layer': 'NOTES', 'h': 1.5, 'width': d1['w'] - 20})
        d2 = sheet.detail_box(1, 'CROSSINGS SUMMARY', '')
        n_a = len([t for t in tendons_all if t.get('spanSet') == 'latitude'])
        n_b = len(tendons_all) - n_a
        over_a = len([c for c in crossings if fam_of(c['a'] if c['over'] == 'a' else c['b']) == 'A' and c['over'] != '='])
        n_eq = len([c for c in crossings if c['over'] == '='])
        for i, h in enumerate([f"{n_a} TENDONS IN DIRECTION A AND {n_b} IN DIRECTION B: {len(crossings)} CROSSINGS. DIRECTION A PASSES OVER AT {over_a}, DIRECTION B AT {len(crossings) - over_a - n_eq}.",
                               f"{len(clashes)} CLASHES (GAP UNDER {CROSS['tol']} mm) AND {len(tight)} TIGHT CROSSINGS (UNDER THE {CROSS['duct']} mm DUCT HEIGHT) - LISTED IN THE SCHEDULE. A CLASH MEANS THE TWO DUCTS CANNOT BOTH SIT AT THEIR PROFILE: THE MORE LIGHTLY LOADED TENDON IS TO BE LOWERED UNDER (OR RAISED OVER) THE OTHER BY ONE DUCT HEIGHT IN RAM AND THE SHEETS RE-ISSUED.",
                               'A TIGHT CROSSING IS NOT A DESIGN ERROR: IN A SLAB TENDONED BOTH WAYS THE TWO PROFILES MUST PASS THROUGH ONE LEVEL SOMEWHERE ON THE SLOPE; THE LOWER DUCT BENDS A LITTLE ON SITE.',
                               'DEPTHS ARE FROM THE TOP OF THE SLAB (OR OF THE DROP PANEL WHERE THE CROSSING FALLS INSIDE ONE) TO THE DUCT CENTRE, FROM THE SAME PROFILE THE CHAIR HEIGHTS ARE TAKEN FROM.']):
            pp.mtext(d2['x'] + 4, d2['y'] + d2['h'] - 12 - i * 13, h, {'layer': 'NOTES', 'h': 1.6, 'width': d2['w'] - 8})
        return {
            'rows': rows, 'cols': cols, 'rowH': 3, 'scheduleTitle': 'TENDON CROSSINGS - CLASHES AND TIGHT GAPS', 'detailsUsed': 2,
            'totals': f"{len(crossings)} CROSSINGS · {len(clashes)} CLASHES (< {CROSS['tol']} mm) · {len(tight)} TIGHT (< {CROSS['duct']} mm)",
            'planTitles': ['TENDON CROSSINGS - WHICH TENDON PASSES OVER (BOTH DIRECTIONS)'],
            'general': [
                common_notes(model, level)[0],
                'BOTH TENDON DIRECTIONS ARE DRAWN TOGETHER: AT EVERY CROSSING THE TENDON DRAWN CONTINUOUS PASSES OVER AND THE ONE DRAWN BROKEN PASSES UNDER; THE FIGURE GIVES THE DIRECTION ON TOP AND THE GAP BETWEEN THE DUCT CENTRES IN mm.',
                f"CROSSINGS UNDER {CROSS['tol']} mm ARE CLASHES (RED CIRCLE) AND ARE LISTED IN THE SCHEDULE WITH BOTH DEPTHS; CROSSINGS UNDER THE {CROSS['duct']} mm DUCT HEIGHT ARE TIGHT (YELLOW).",
                'THE CHAIR HEIGHTS, EXTENSIONS AND SCHEDULES OF EACH DIRECTION ARE ON ITS OWN SHEET (07A / 07B); THIS SHEET IS FOR THE PLACING SEQUENCE AND THE PROFILE CHECK ONLY.',
            ],
            'assumptions': level_assumptions(model, level)[:3],
            'legend': [['PT-Cross-A', 'TENDON, DIRECTION A - CONTINUOUS WHERE IT PASSES OVER', 'thick'], ['PT-Cross-B', 'TENDON, DIRECTION B - CONTINUOUS WHERE IT PASSES OVER', 'thick'], ['PT-Cross-Gap', 'GAP AT THE CROSSING (mm) + DIRECTION ON TOP', 'line'], ['PT-Cross-Tight', 'TIGHT GAP (UNDER THE DUCT HEIGHT)', 'line'], ['PT-Cross-Clash', 'CLASH (RED CIRCLE)', 'line'], ['PT-Cross-Mark', 'TENDON MARK', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
            'checks': [f"{len(crossings)} tendon crossings: {len(clashes)} clashes under {CROSS['tol']} mm, {len(tight)} tight under the {CROSS['duct']} mm duct."],
        }
    return draw


# ------------------------------------------------------------------ beams (RAM design read back)
def _bars_of(rec):
    return f"{(rec.get('top') or {}).get('text') or '-'} / {(rec.get('bottom') or {}).get('text') or '-'} / {(rec.get('stirrups') or {}).get('text') or '-'}"


def _office_check(office, id_):
    return next((x for x in ((office or {}).get('beams') or []) if _upper(x['id']) == _upper(id_)), None)


def _not_passing(chk):
    return f" - NOT PASSING ({', '.join(chk['reasons'] if len(chk['reasons']) else ['RAM']).upper()})" if chk and chk.get('status') == 'fail' else ''


def beams_sheet(model, level, meta):
    """
    The beams of the level as RAM designed them (one design strip per beam span, see lib/beam-strips.mjs): every beam
    labelled with its type and section on the plan, the types scheduled (section, top bars over the supports, bottom
    bars in the span, stirrups, the beams of the type) and drawn in section.
    """
    def draw(sheet, pens):
        pl = pens[0]
        S = sheet.S
        sch = level.get('beamSchedule') or {'beams': [], 'types': [], 'undesigned': []}
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'dims': False, 'regionLabels': False, 'ubarRegions': False})
        for bm in sch['beams']:
            L = dist(bm['a'], bm['b']) or 1
            u = {'x': (bm['b']['x'] - bm['a']['x']) / L, 'y': (bm['b']['y'] - bm['a']['y']) / L}
            n = {'x': -u['y'], 'y': u['x']}
            w2 = bm['width'] / 2
            poly = [{'x': bm['a']['x'] + n['x'] * w2, 'y': bm['a']['y'] + n['y'] * w2}, {'x': bm['b']['x'] + n['x'] * w2, 'y': bm['b']['y'] + n['y'] * w2}, {'x': bm['b']['x'] - n['x'] * w2, 'y': bm['b']['y'] - n['y'] * w2}, {'x': bm['a']['x'] - n['x'] * w2, 'y': bm['a']['y'] - n['y'] * w2}]
            pl.hatch([poly], {'layer': 'BEAM' if bm.get('mark') else 'CALLOUT', 'pattern': 'ANSI31', 'spacing': 1.2})
            m = {'x': (bm['a']['x'] + bm['b']['x']) / 2, 'y': (bm['a']['y'] + bm['b']['y']) / 2}
            rot = (math.atan2(u['y'], u['x']) * 180) / math.pi
            off = bm['width'] / 2 + 0.6 * S
            pl.text({'x': m['x'] + n['x'] * off, 'y': m['y'] + n['y'] * off}, f"{bm.get('mark') or '??'} {_s(size50(bm['width']))}x{_s(size50(bm['depth']))}", {'layer': 'CALLOUT', 'h': 2.2, 'rot': rot, 'align': 'C', 'valign': 'B', 'bold': True})
            chk = _office_check(sch.get('office'), bm['id'])
            bars = (_bars_of(bm) if bm.get('mark') else 'NOT DESIGNED' + (' IN RAM' if sch.get('design') == 'ram' else '')) + _not_passing(chk)
            pl.text({'x': m['x'] - n['x'] * off, 'y': m['y'] - n['y'] * off}, bars, {'layer': 'TEXT', 'h': 1.6, 'rot': rot, 'align': 'C', 'valign': 'T'})
            pl.text({'x': bm['a']['x'] + u['x'] * 400 + n['x'] * off, 'y': bm['a']['y'] + u['y'] * 400 + n['y'] * off}, bm['id'], {'layer': 'TEXT', 'h': 1.3, 'rot': rot, 'align': 'L', 'valign': 'B'})
        design_label = 'OFFICE DESIGN' if sch.get('design') == 'office' else 'HEAVIER OF RAM AND OFFICE DESIGN' if sch.get('design') == 'max' else 'RAM DESIGN'
        office = sch.get('office') or None
        failing = [b for b in ((office or {}).get('beams') or []) if b.get('status') == 'fail']
        ov = (model['spec'].get('beams') or {}).get('override')
        bypass = ov if ov and (ov.get('by') or ov.get('beams')) else None  # noqa: F841  (kept as in the JS)
        # the office design forces per beam (the first twelve; the rest in REPORT.md)
        forces = []
        if office:
            for b in office['beams'][:12]:
                dfl = b['deflection']
                defl = 'OK BY SPAN/DEPTH' if dfl.get('table_ok') else f"{_s(dfl.get('ratio'))} OF LIMIT{'' if dfl.get('ok') else ' - NOT PASSING'}"
                forces.append(f"{b['id']} {_s(size50(b['width']))}x{_s(size50(b['depth']))}: SPANS {'+'.join(to_fixed(sp['length'] / 1000, 1) for sp in b['spans'])} m, TRIB {to_fixed(b['trib_mm']['total'] / 1000, 1)} m, wu {_s(b['loads']['wu'])} kN/m, Mu- {_s(b['Mneg_max'])} / Mu+ {_s(b['Mpos_max'])} kN.m, Vu {_s(b['Vu'])} kN -> {_bars_of(b)}; DEFL. {defl}{'; REPORTED FAILING IN RAM' if b.get('ram_failed') else ''}")
        if office and len(office['beams']) > 12:
            forces.append(f"{len(office['beams']) - 12} MORE BEAMS IN REPORT.md.")
        rows, cols = beam_schedule_rows(sch), BEAM_SCHEDULE_COLS
        details_used = draw_beam_sections(sheet, sch, 0)
        kg = beam_steel_kg(sch)
        return {
            'rows': rows, 'cols': cols, 'scheduleTitle': f'BEAM SCHEDULE ({design_label})', 'detailsUsed': details_used, 'totals': beam_schedule_totals(sch, kg),
            'weight': js_round(kg),
            'planTitles': [f'BEAM MARKS AND SECTIONS - {design_label}'],
            'general': [common_notes(model, level)[0], *beam_schedule_notes(model, level, sch)],
            'assumptions': [*forces, *level_assumptions(model, level)[:1 if len(forces) else 3]],
            'legend': [['BEAM', 'BEAM (HATCHED) - TYPE AND SECTION BESIDE IT', 'hatch'], ['CALLOUT', f"BEAM NOT DESIGNED{' IN RAM' if sch.get('design') == 'ram' else ''}", 'hatch'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
            'checks': [f"{len(sch['beams'])} beams, {len(sch['types'])} types, {len(sch['undesigned'])} without a design, {len(failing)} not passing the office check."],
        }
    return draw


def beam_schedule_rows(sch):
    """The rows of the beam schedule: one per type, the new types starred under a unified project schedule."""
    return [{'mark': f"{t['mark']} *" if t.get('isNew') and sch.get('library') else t['mark'], 'section': f"{_s(t['width'])} x {_s(t['depth'])}", 'top': (t.get('top') or {}).get('text') or '-', 'bottom': (t.get('bottom') or {}).get('text') or '-',
             'stirrups': f"T{_s(t['stirrups']['dia'])}-{_s(t['stirrups']['legs'])} LEGS @ {_s(t['stirrups']['spacing'])}" if t.get('stirrups') else '-', 'count': t['count'], 'beams': ', '.join(t['beams'])} for t in sch['types']]


# The beam schedule columns (type, section, bars, stirrups, count, beams).
BEAM_SCHEDULE_COLS = [
    {'key': 'mark', 'title': 'TYPE', 'w': 14}, {'key': 'section', 'title': 'SECTION\nb x h (mm)', 'w': 24}, {'key': 'top', 'title': 'TOP BARS\n(SUPPORTS)', 'w': 24}, {'key': 'bottom', 'title': 'BOTTOM BARS\n(SPAN)', 'w': 24},
    {'key': 'stirrups', 'title': 'STIRRUPS', 'w': 34}, {'key': 'count', 'title': 'No.', 'w': 10}, {'key': 'beams', 'title': 'BEAMS', 'w': 55, 'align': 'L', 'max': 34},
]


def draw_beam_sections(sheet, sch, first=0):
    """The sections of the types drawn four to a detail box at 1:25 from box `first`; returns the number of boxes used in all."""
    # the sections of the types, four to a box, at 1:25
    details_used = first
    per_box = 4
    bi = 0
    while bi + first < 3 and bi * per_box < len(sch['types']):
        group = sch['types'][bi * per_box:(bi + 1) * per_box]
        d = sheet.detail_box(bi + first, f"BEAM SECTIONS {group[0]['mark']}{(' - ' + group[-1]['mark']) if len(group) > 1 else ''}", '1:25')
        details_used = bi + first + 1
        gap = 600
        x = 0
        max_h = max(t['depth'] for t in group)
        items = []
        for t in group:
            items.append({'t': t, 'x': x})
            x += t['width'] + gap
        gb = {'minX': -200, 'maxX': x - gap + 200, 'minY': -1400, 'maxY': max_h + 300, 'cx': (x - gap) / 2, 'cy': (max_h - 1100) / 2}
        pen = sheet.detail_pen(d, 25, gb)
        for it in items:
            t, x0 = it['t'], it['x']
            cov, b, h = 40, t['width'], t['depth']
            pen.pline([{'x': x0, 'y': 0}, {'x': x0 + b, 'y': 0}, {'x': x0 + b, 'y': h}, {'x': x0, 'y': h}], {'layer': 'OUTLINE', 'closed': True, 'lw': 35})
            pen.pline([{'x': x0 + cov, 'y': cov}, {'x': x0 + b - cov, 'y': cov}, {'x': x0 + b - cov, 'y': h - cov}, {'x': x0 + cov, 'y': h - cov}], {'layer': 'REBAR', 'closed': True})

            def row_of(set_, y):
                if not set_:
                    return
                nb, r = set_['n'], set_['dia'] / 2
                x1, x2 = x0 + cov + 12, x0 + b - cov - 12
                for i in range(math.ceil(nb)):  # JS `i < nb` on a fractional count
                    xx = x1 + ((x2 - x1) * i) / (nb - 1) if nb > 1 else (x1 + x2) / 2
                    pen.circle({'x': xx, 'y': y}, r, {'layer': 'REBAR'})
                    pen.hatch([[{'x': xx - r, 'y': y - r}, {'x': xx + r, 'y': y - r}, {'x': xx + r, 'y': y + r}, {'x': xx - r, 'y': y + r}]], {'layer': 'REBAR', 'pattern': 'SOLID'})
            row_of(t.get('top'), h - cov - 20)
            row_of(t.get('bottom'), cov + 20)
            pen.text({'x': x0 + b / 2, 'y': -250}, f"{t['mark']}  {_s(size50(b))}x{_s(size50(h))}", {'layer': 'TEXT', 'h': 2.2, 'align': 'C', 'valign': 'T', 'bold': True})
            pen.text({'x': x0 + b / 2, 'y': -620}, f"TOP {(t.get('top') or {}).get('text') or '-'}  BOT {(t.get('bottom') or {}).get('text') or '-'}", {'layer': 'TEXT', 'h': 1.6, 'align': 'C', 'valign': 'T'})
            pen.text({'x': x0 + b / 2, 'y': -950}, f"T{_s(t['stirrups']['dia'])}-{_s(t['stirrups']['legs'])}L @ {_s(t['stirrups']['spacing'])}" if t.get('stirrups') else '-', {'layer': 'TEXT', 'h': 1.6, 'align': 'C', 'valign': 'T'})
            pen.text({'x': x0 + b / 2, 'y': -1250}, f"{_s(t['count'])} BEAM{'S' if t['count'] > 1 else ''}", {'layer': 'NOTES', 'h': 1.4, 'align': 'C', 'valign': 'T'})
        bi += 1
    return details_used


def beam_steel_kg(sch):
    """The main bars of the typed beams, kg (top and bottom areas over the beams' lengths)."""
    s = 0
    for t in sch['types']:
        for id_ in t['beams']:
            bm = next((b for b in sch['beams'] if b['id'] == id_), None)
            s += (((t.get('top') or {}).get('area') or 0) + ((t.get('bottom') or {}).get('area') or 0)) * (bm['length'] if bm else 0) * 7850 / 1e9
    return s


def beam_schedule_totals(sch, kg=None):
    if kg is None:
        kg = beam_steel_kg(sch)
    return f"{len(sch['beams'])} BEAMS IN {len(sch['types'])} TYPES{(' · ' + _s(len(sch['undesigned'])) + ' NOT DESIGNED') if len(sch['undesigned']) else ''} · MAIN BARS ≈ {js_round(kg)} kg"


_CONSULTANT_SCHEDULE = "THE CONSULTANT'S BEAM SCHEDULE"


def beam_schedule_notes(model, level, sch):
    """The notes of the beam design (how the bars were found, the beams without a design, the failing ones, the unified schedule)."""
    office = sch.get('office') or None
    failing = [b for b in ((office or {}).get('beams') or []) if b.get('status') == 'fail']
    ov = (model['spec'].get('beams') or {}).get('override')
    bypass = ov if ov and (ov.get('by') or ov.get('beams')) else None
    design = sch.get('design')
    assumed = (office or {}).get('assumed') if office else None
    added = sch.get('added')
    notes = [
        f"EVERY BEAM CARRIES ITS TYPE AND SECTION (b x h) ON THE PLAN; THE BARS OF THE TYPE ARE IN THE SCHEDULE AND THE SECTIONS. {'THE BARS ARE THE OFFICE DESIGN: EVERY BEAM ANALYSED AS A CONTINUOUS BEAM OVER ITS COLUMNS AND WALLS UNDER THE SLAB IT CARRIES (SELF-WEIGHT, THE AREA LOADS OF THE MODEL, 1.2 D + 1.6 L, LIVE LOAD PATTERNED), FLEXURE, SHEAR AND DEFLECTION PER SBC 304 / ACI 318.' if design == 'office' else 'THE BARS ARE, SET BY SET, THE HEAVIER OF THE RAM CONCEPT DESIGN AND THE OFFICE DESIGN (CONTINUOUS-BEAM ANALYSIS ON THE MODEL LOADS, SBC 304 / ACI 318).' if design == 'max' else 'TOP BARS ARE THE HEAVIEST RAM DESIGNED OVER THE SUPPORTS OF THE BEAM, BOTTOM BARS THE HEAVIEST IN ITS SPANS, STIRRUPS THE CLOSEST SPACING RAM DESIGNED IN IT.'}",
        'THE DESIGN COMES FROM ONE RAM CONCEPT DESIGN STRIP ON THE CENTRE LINE OF EVERY BEAM SPAN, BOUNDED BY A SPLITTER ON EACH EDGE OF THE BEAM, DESIGNED AS A BEAM. BEAMS OF ONE SECTION WHOSE BARS ARE ALIKE (WITHIN 15 %) SHARE A TYPE AND TAKE THE HEAVIER BARS.' if design == 'ram' else
        f"THE OFFICE DESIGN FORCES OF EVERY BEAM ARE LISTED IN THE ASSUMPTIONS AND IN REPORT.md; {('; '.join(assumed).upper() + '. ') if assumed else ''}THE RAM DESIGN REPORT GOVERNS. BEAMS OF ONE SECTION WHOSE BARS ARE ALIKE (WITHIN 15 %) SHARE A TYPE AND TAKE THE HEAVIER BARS.",
        f"{(_s(len(sch['undesigned'])) + ' BEAM(S) CARRY NO ' + ('RAM ' if design == 'ram' else '') + 'DESIGN (' + ', '.join(_s(u) for u in sch['undesigned'][:10]) + '): RUN CALC ALL ON THE MODEL WITH THE BEAM STRIPS AND RE-ISSUE. ') if len(sch['undesigned']) else ''}CONTINUING TOP BARS, LAPS AND ANCHORAGES PER THE OFFICE BEAM DETAILS; STIRRUP SPACING TO BE HALVED OVER 2h FROM EVERY SUPPORT FACE.",
        (f"BEAMS NOT PASSING THE OFFICE CHECK: {'; '.join(b['id'] + ' (' + (', '.join(b['reasons']) or 'REPORTED FAILING IN RAM') + ')' for b in failing).upper()}"
         + (f" - ACCEPTED AT THE DESIGN ENGINEER'S RESPONSIBILITY ({', '.join(_s(v) for v in [bypass.get('by'), bypass.get('date')] if v).upper()}){(': ' + _s(bypass['note']).upper()) if bypass.get('note') else ''}" if bypass else ' - TO BE RESOLVED (DEEPEN THE BEAM OR CONFIRM AGAINST THE RAM REPORT)') + '.') if len(failing) else None,
        (f"BEAMS {', '.join(_s(b) for b in sch['assigned'])} CARRY THE TYPES OF {_s(sch.get('source') or _CONSULTANT_SCHEDULE).upper()} AS ASSIGNED BY THE ENGINEER ({', '.join(_s(m) for m in dict.fromkeys(b.get('mark') for b in sch['beams'] if b.get('assigned')))}): THEIR BARS ARE THAT SCHEDULE'S, NOT DESIGNED OR CHECKED HERE{('; NO TYPE ON RECORD FOR ' + ', '.join(_s(u) for u in sch['unassigned'])) if sch.get('unassigned') else ''}.") if sch.get('assigned') else None,
        (f"BEAM TYPES FOLLOW THE PROJECT'S UNIFIED BEAM SCHEDULE ({_s(sch['library'])} TYPES ON RECORD): A BEAM TAKES THE LIGHTEST TYPE THAT CARRIES IT; {('TYPES MARKED * (' + ', '.join(t['mark'] for t in added) + ') ARE NEW ON THIS SHEET, ADDED FOR BEAMS NO EXISTING TYPE CARRIES - THE EXISTING TYPES ARE UNCHANGED.') if added else 'NO NEW TYPE WAS NEEDED ON THIS SHEET.'}") if sch.get('library') else None,
    ]
    return [n for n in notes if n]


def _cables_sheet(model, level, meta):
    def draw(sheet, pens):
        pl = pens[0]
        draw_base(sheet, pl, level, {'gridTag': meta.get('gridTag'), 'regionLabels': True, 'ubarRegions': False})
        sheet.stamp('EMPTY TEMPLATE - NO TENDONS SHOWN', 'TENDON LAYOUT, PROFILES AND QUANTITIES TO BE ADDED ON COMPLETION OF THE PT DESIGN')
        cols = [
            {'key': 'id', 'title': 'TENDON\nID', 'w': 16}, {'key': 'type', 'title': 'TYPE', 'w': 16}, {'key': 'strands', 'title': 'No.\nSTR.', 'w': 12}, {'key': 'profile', 'title': 'PROFILE\nREF.', 'w': 18},
            {'key': 'length', 'title': 'LENGTH\n(m)', 'w': 17}, {'key': 'live', 'title': 'LIVE\nEND', 'w': 16}, {'key': 'jack', 'title': 'JACK\n(kN)', 'w': 17}, {'key': 'elong', 'title': 'ELONG.\n(mm)', 'w': 17}, {'key': 'qty', 'title': 'QTY', 'w': 12}, {'key': 'remarks', 'title': 'REMARKS', 'w': 44, 'align': 'L'},
        ]
        rows = [{'id': f'T-{_pad2(i + 1)}', 'type': '', 'strands': '', 'profile': '', 'length': '', 'live': '', 'jack': '', 'elong': '', 'qty': '', 'remarks': ''} for i in range(22)]
        d0 = sheet.detail_box(0, 'TYPICAL TENDON PROFILE (TEMPLATE)', '1:50')
        gx = level['grid']['x']
        span = gx[1]['x'] - gx[0]['x'] if len(gx) > 1 else 7500
        det0 = D.tendon_profile({'span': span, 'h': level['thickness']})
        det0.draw(sheet.detail_pen(d0, 50, det0.bbox))
        d1 = sheet.detail_box(1, 'TENDON SYMBOLS', 'N.T.S.')
        det1 = D.tendon_legend()
        det1.draw(sheet.detail_pen(d1, 12, det1.bbox))
        d2 = sheet.detail_box(2, 'STRESSING RECORD (TEMPLATE)', '')
        rec_cols = [{'key': 'a', 'title': 'TENDON', 'w': 24}, {'key': 'b', 'title': 'DATE', 'w': 26}, {'key': 'c', 'title': 'GAUGE\n(bar)', 'w': 26}, {'key': 'd', 'title': 'ELONG.\nCALC.', 'w': 30}, {'key': 'e', 'title': 'ELONG.\nMEAS.', 'w': 30}, {'key': 'f', 'title': '%', 'w': 18}, {'key': 'g', 'title': 'SIGN', 'w': d2['w'] - 6 - 154}]
        sheet.table(d2['x'] + 3, d2['y'] + d2['h'] - 10, rec_cols, [{} for _ in range(20)], {'maxRows': math.floor((d2['h'] - 18) / 4), 'headH': 6, 'rowH': 4, 'h': 1.5})
        return {
            'rows': rows, 'cols': cols, 'scheduleTitle': 'PT CABLES SCHEDULE - TEMPLATE',
            'general': [
                common_notes(model, level)[0],
                'THIS SHEET IS A TEMPLATE. TENDON PATHS, PROFILES, STRAND COUNTS, JACKING FORCES AND ELONGATIONS WILL BE ADDED AFTER THE PT DESIGN IS COMPLETE AND APPROVED; NOTHING ON THIS SHEET IS TO BE USED FOR FABRICATION.',
                'PT SYSTEM: BONDED / UNBONDED (TO BE CONFIRMED). STRAND: 15.24 mm (0.6") 7-WIRE LOW-RELAXATION, fpu = 1860 MPa, ASTM A416 / SASO EQUIVALENT (TO BE CONFIRMED).',
                'STRESSING AT NOT LESS THAN THE SPECIFIED TRANSFER STRENGTH; JACKING FORCE ≤ 0.80 fpu·Aps; ELONGATION TOLERANCE ±7 % (SBC 304-18 §20.3.2 / PTI). STRESSING RECORD PER TENDON TO BE KEPT ON THE TEMPLATE IN DETAIL 3.',
                'GRID, COLUMNS, SLAB OUTLINE, BEAMS, OPENINGS AND SUNKEN SLABS ARE SHOWN FOR REFERENCE ONLY, AS READ FROM THE G.A.',
            ],
            'assumptions': ['TENDON LAYOUT NOT YET DESIGNED: SCHEDULE AND PROFILE LEFT BLANK BY INTENT.', *level_assumptions(model, level)[:3]],
            'legend': [['CABLE', 'TENDON (TO BE ADDED)', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['OPENING', 'OPENING', 'line']],
            'detailsUsed': 3,
        }
    return draw


def _cover_sheet(model, sheets, meta):
    def draw(sheet, pens=None):
        P = sheet.L['plan']
        pp = sheet.pp
        pp.text(P['x'] + 10, P['y'] + P['h'] - 16, (meta.get('project') or '').upper(), {'layer': 'TEXT-TITLE', 'h': 6, 'bold': True})
        pp.text(P['x'] + 10, P['y'] + P['h'] - 26, 'REINFORCEMENT AND PT CABLES SHOP DRAWINGS - DRAWING INDEX', {'layer': 'TEXT-TITLE', 'h': 4})
        pp.text(P['x'] + 10, P['y'] + P['h'] - 34, f"{_s(meta.get('company'))}  ·  {('CLIENT: ' + _s(meta['client']) + '  ·  ') if meta.get('client') else ''}{_s(meta.get('location') or '')}  ·  REV {_s(meta.get('revision'))}  ·  {_s(meta.get('date'))}", {'layer': 'TITLE', 'h': 2.6})
        cols = [{'key': 'no', 'title': 'DRAWING No.', 'w': 40}, {'key': 'title', 'title': 'DRAWING TITLE', 'w': 205}, {'key': 'level', 'title': 'LEVEL', 'w': 110, 'align': 'L', 'max': 40}, {'key': 'block', 'title': 'BLOCK / XREF NAME', 'w': 150, 'align': 'L'}, {'key': 'scale', 'title': 'SCALE', 'w': 36}, {'key': 'wt', 'title': 'REBAR (kg)', 'w': 40}, {'key': 'rev', 'title': 'REV', 'w': 20}]
        rows = [{'no': s['drawingNo'], 'title': s['title'], 'level': 'ALL' if s['level'] == 'ALL' else f"{s['level']} - {s['levelName']}", 'block': s['blockName'], 'scale': f"1:{_s(s['scale'])}" if s.get('scale') else 'NTS', 'wt': _locale(js_round(s['weight'])) if s.get('weight') else '-', 'rev': meta.get('revision')} for s in sheets]
        total_w = sum((x.get('weight') or 0) for x in sheets)
        sheet.table(P['x'] + 10, P['y'] + P['h'] - 42, [{**c, 'align': c.get('align') or ('L' if c['key'] == 'title' else 'C')} for c in cols], rows, {'title': 'DRAWING INDEX / LIST OF SHEETS', 'rowH': 5, 'h': 2, 'headH': 6, 'titleH': 7, 'totals': f'TOTAL SCHEDULED REINFORCEMENT (ALL LEVELS) {_locale(js_round(total_w))} kg'})
        d0 = sheet.detail_box(0, 'LEVELS READ FROM THE STRUCTURAL DRAWINGS', '')
        lcols = [{'key': 'id', 'title': 'ID', 'w': 14}, {'key': 'name', 'title': 'LEVEL', 'w': 70, 'align': 'L', 'max': 34}, {'key': 'thk', 'title': 'THK', 'w': 16}, {'key': 'cols', 'title': 'COLS', 'w': 16}, {'key': 'op', 'title': 'OPEN.', 'w': 16}, {'key': 'sk', 'title': 'SUNK.', 'w': 16}, {'key': 'vo', 'title': 'VOIDS', 'w': 16}, {'key': 'area', 'title': 'AREA m²', 'w': d0['w'] - 6 - 164}]
        sheet.table(d0['x'] + 3, d0['y'] + d0['h'] - 10, lcols, [{'id': l['id'], 'name': l['name'], 'thk': l['thickness'], 'cols': len(l['columns']), 'op': len(l['openings']), 'sk': len(l.get('sunken') or []), 'vo': len(l['voids']), 'area': js_round(abs(polygon_area(l['outline'])) / 1e6)} for l in model['levels']], {'headH': 5, 'rowH': 4, 'h': 1.6, 'maxRows': 24})
        d1 = sheet.detail_box(1, 'DEVELOPMENT / LAP LENGTHS APPLIED (mm)', '')
        tcols = [{'key': 'dia', 'title': 'Ø', 'w': 16}, {'key': 'ld_bottom', 'title': 'ld BOT', 'w': 30}, {'key': 'ld_top', 'title': 'ld TOP', 'w': 30}, {'key': 'lap_bottom', 'title': 'LAP BOT', 'w': 32}, {'key': 'lap_top', 'title': 'LAP TOP', 'w': 32}, {'key': 'ldh', 'title': 'ldh HOOK', 'w': d1['w'] - 6 - 140}]
        sheet.table(d1['x'] + 3, d1['y'] + d1['h'] - 10, tcols, R.length_table(model['spec']), {'headH': 5, 'rowH': 4, 'h': 1.6})
        d2 = sheet.detail_box(2, 'HOW TO USE THE BLOCKS / XREFS', '')
        how = ['EACH SHEET IS A BLOCK NAMED AS LISTED; THE SAME NAME IS ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1 AND THE FRAME IS SCALED BY THE SHEET SCALE.', 'LAYERS PER THE SPAN TECH STANDARD (SPAN-): SPAN-RB-B1 / B2 / T1 / T2 (BARS), SPAN-RB-UBAR, SPAN-RB-TRIM, SPAN-RB-PUNCH, SPAN-RB-TEXT (CALL-OUTS), SPAN-RB-MESH, SPAN-RB-TYPE, SPAN-GRID, SPAN-SLAB-EDGE, SPAN-COL, SPAN-BEAM, SPAN-OPENING, SPAN-SUNKEN, SPAN-VOID, SPAN-PT-*, SPAN-SHEET-*, SPAN-DIM, SPAN-CALLOUT.', 'EXPLODE A BLOCK TO EDIT; RE-RUN THE GENERATOR AFTER THE CONSULTANT REVISES THE G.A. AND RE-ATTACH.']
        for i, h in enumerate(how):
            pp.mtext(d2['x'] + 4, d2['y'] + d2['h'] - 12 - i * 14, h, {'layer': 'NOTES', 'h': 1.8, 'width': d2['w'] - 8})
        found = model['spec'].get('found') or []
        return {
            'general': [
                f"PACKAGE GENERATED FROM THE CONSULTANT'S STRUCTURAL DRAWINGS: {len(model['levels'])} SLAB LEVEL(S) READ.",
                *model['findings'],
                f"DESIGN DATA READ FROM THE DRAWINGS: {'; '.join(_s(f) for f in found) if len(found) else 'NONE (ALL REINFORCEMENT ASSUMED, SEE ASSUMPTIONS)'}.",
            ],
            'assumptions': [(f"[{a['level']}] " if a.get('level') else '') + a['text'] for a in model['assumptions']],
            'legend': [],
            'detailsUsed': 3,
        }
    return draw


# ------------------------------------------------------------------ package
def compose_package(model, meta_in=None):
    meta = {
        'company': 'SPAN TECH CONTRACTING', 'company_line': 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
        'project': 'PROJECT NAME', 'client': '', 'engineer': '', 'contractor': '', 'location': '', 'prefix': 'SPAN-SD', 'revision': '00',
        'date': datetime.now(timezone.utc).strftime('%Y-%m-%d'), 'prepared': '', 'checked': '', 'approved': '', 'status': 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
        **(meta_in or {}),
    }
    makers = {
        'framing': _framing_sheet, 'bottom': _bottom_sheet, 'top': _top_sheet,
        'addbottom': lambda m, l, mt: _ram_bars_sheet(m, l, mt, 'B'), 'addtop': lambda m, l, mt: _ram_bars_sheet(m, l, mt, 'T'),
        'ubars': _ubar_sheet, 'voids': _voids_sheet, 'openings': _openings_sheet, 'cables': _cables_sheet,
        'cables_lat': lambda m, l, mt: ram_cables_sheet(m, l, mt, set_='latitude', variant='shop'),
        'cables_lon': lambda m, l, mt: ram_cables_sheet(m, l, mt, set_='longitude', variant='shop'),
        'cables_cross': ram_crossings_sheet, 'punching': _punching_sheet, 'beams': beams_sheet,
    }
    jobs = []
    for level in model['levels']:
        for def_ in SHEET_DEFS:
            if def_.get('ramOnly') and not level.get('ram'):
                continue
            if def_.get('drawingOnly') and level.get('ram'):
                continue  # the empty cable template gives way to the RAM cable sheets
            if def_.get('set') and not any(t.get('spanSet') == def_['set'] for t in (level['ram'].get('tendons') or [])):
                continue  # no tendons in this direction
            if def_.get('needsBeams') and not len((level.get('beamSchedule') or {}).get('types') or []):
                continue  # no beam designed in RAM
            jobs.append({'level': level, 'def': def_, 'draw': makers[def_['key']](model, level, meta)})
    total = len(jobs) + 1
    sheets = [build_sheet(model=model, level=j['level'], def_=j['def'], meta=meta, index=i + 2, total=total, draw=j['draw']) for i, j in enumerate(jobs)]
    cover = build_sheet(model=model, level=None, def_={'key': 'cover', 'base': 'SHOP_DRAWINGS_COVER_INDEX', 'title': 'COVER SHEET / DRAWING INDEX', 'no': '000'}, meta=meta, index=1, total=total, draw=_cover_sheet(model, sheets, meta))
    return pack_sheets([cover, *sheets], meta)


def pack_sheets(all_, meta, o=None, **kw):
    """Apply the layer standard to every sheet and collect all sheet blocks into one package canvas."""
    o = opts(o, kw)
    std = meta.get('layerStandard')
    for s in all_:
        if std and std.get('textStyles'):
            for n, d in std['textStyles'].items():
                s['root'].text_style_def(n, d)
        if std and std.get('layers'):
            s['root'].apply_layer_standard(std['layers'])
    pkg = Canvas()
    if std and std.get('textStyles'):
        for n, d in std['textStyles'].items():
            pkg.text_style_def(n, d)
    for n, d in (o.get('textStyles') or {}).items():
        pkg.text_style_def(n, d)
    per_row = 4
    # the sheets sit in a grid spaced by the largest sheet (841 x 594 paper mm at the largest scale), so no two overlap
    max_scale = max(100, *[(s.get('scale') or 100) for s in all_])
    gap_x, gap_y = 900 * max_scale, 650 * max_scale
    for i, s in enumerate(all_):
        root = s['root']
        for name, d in root.layers.items():
            if name not in pkg.layers:
                pkg.layers[name] = d
        for name, d in (root.text_styles or {}).items():
            if name not in pkg.text_styles:
                pkg.text_styles[name] = d
        for name, d in (root.dim_styles or {}).items():
            if name not in pkg.dim_styles:
                pkg.dim_styles[name] = d
        pkg.blocks[s['blockName']] = root.blocks.get(s['blockName'])
        # the blocks the sheet inserts (anchors LiveEnd / DeadEnd, symbols) go with it; the dimension pictures are renumbered below
        for bn, bd in root.blocks.items():
            if bn != s['blockName'] and not bn.startswith('*D') and bn not in pkg.blocks:
                pkg.blocks[bn] = bd
        # dimension picture blocks (*D1, *D2 ...) are numbered per sheet: renumber them package-wide (in the sheet root too, so both stay consistent)
        # (all renames are decided first, then applied once, so *D1 → *D143 never collides with the sheet's own *D143)
        renames = {}
        for bn in list(root.blocks.keys()):
            if bn.startswith('*D'):
                pkg.dim_count += 1
                renames[bn] = f'*D{pkg.dim_count}'
        if renames:
            fresh = {}
            for bn, bd in root.blocks.items():
                fresh[renames.get(bn) or bn] = bd
            root.blocks = fresh
            for bn, nn in renames.items():
                pkg.blocks[nn] = root.blocks.get(nn)

            def rename(cv):
                for e in cv.entities:
                    if e.get('t') == 'dimension' and e.get('block') in renames:
                        e['block'] = renames[e['block']]
            rename(root)
            for b2 in root.blocks.values():
                rename(b2)
        x, y = (i % per_row) * gap_x, -math.floor(i / per_row) * gap_y
        pkg.insert(s['blockName'], x, y)
        pkg.text(x, y + 594 * s['scale'] + 1500, f"{s['drawingNo']}  {s['title']}{('  (' + s['level'] + ')') if s['level'] != 'ALL' else ''}", {'layer': 'XREF', 'h': 1200})
    if std and std.get('layers'):
        pkg.apply_layer_standard(std['layers'])
    return {'meta': meta, 'sheets': all_, 'pkg': pkg}
