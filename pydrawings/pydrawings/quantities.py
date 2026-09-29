"""
Quantity take-off of a package: the reinforcement scheduled on its sheets, the concrete of the slab read from the
model (net of openings, drops and beams added, formwork) and the post-tensioning (tendons, strands, strand length
at cutting length, weight, anchors, ducts). Every figure comes from the same model and schedules the drawings
were made from, so the take-off and the drawings never disagree.
"""
import math
import re

from .geometry import polygon_area, dist, js_round
from . import rebar as R

STRAND_DENSITY = 7850  # kg/m³
CUT_ALLOWANCE = 300  # mm of strand per stressed anchor
SMALL_DUCT_MAX = 3  # strands in a 20x50 duct; over that 20x70


def r1(v):
    return js_round(v * 10) / 10


def r2(v):
    return js_round(v * 100) / 100


def _area(poly):
    return abs(polygon_area(poly)) if (poly and len(poly) >= 3) else 0


def _perimeter(poly):
    return sum(dist(p, poly[(i + 1) % len(poly)]) for i, p in enumerate(poly)) if (poly and len(poly) >= 2) else 0


def _num(v):
    """JS `Number(v)`: None -> 0, numbers as they are, numeric strings parsed, anything else NaN."""
    if v is None:
        return 0
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        s = v.strip()
        if s == '':
            return 0
        try:
            return float(s)
        except ValueError:
            return math.nan
    return math.nan


def _finite(v):
    return isinstance(v, (int, float)) and math.isfinite(v)


def steel_of(level, sheets):
    """The reinforcement of one level: every scheduled row of its sheets, by diameter and by face."""
    by_dia = {}
    kg = 0
    top = 0
    bottom = 0
    other = 0
    for s in sheets:
        if s.get('level') != level.get('id'):
            continue
        title = str(s.get('title'))
        face = 'T' if re.search('TOP', title, re.I) else 'B' if re.search('BOTTOM', title, re.I) else 'O'
        for r in s.get('rows') or []:
            w = _num(r.get('weight_kg'))
            if not _finite(w) or not w:
                continue
            dia = _num(r.get('dia')) or 0
            if not _finite(dia):
                dia = 0  # Number(r.dia) || 0: NaN is falsy in JS
            if dia not in by_dia:
                by_dia[dia] = {'dia': dia, 'total_m': 0, 'kg': 0, 'count': 0}
            total_m = _num(r.get('total_m'))
            by_dia[dia]['total_m'] += total_m if _finite(total_m) and total_m else 0
            by_dia[dia]['kg'] += w
            qty = _num(r.get('qty'))
            by_dia[dia]['count'] += qty if _finite(qty) and qty else 0
            kg += w
            if face == 'T':
                top += w
            elif face == 'B':
                bottom += w
            else:
                other += w
    return {
        'kg': r1(kg), 'top_kg': r1(top), 'bottom_kg': r1(bottom), 'other_kg': r1(other),
        'byDia': [{'dia': d['dia'], 'total_m': r1(d['total_m']), 'kg': r1(d['kg']), 'count': d['count']} for d in sorted(by_dia.values(), key=lambda d: d['dia'])],
    }


def mesh_of(level):
    """
    The slab mesh of a design level made from a RAM model (the office mesh written in the notes, not scheduled on the
    sheets): both directions on each face, laps and stock allowance included, from the net slab area.
    """
    if not level.get('ram') or not level.get('meshSpec'):
        return None
    dia, spacing = level['meshSpec'][0], level['meshSpec'][1]
    if not dia or not spacing:
        return None
    faces = 2 if level.get('topMesh') else 1
    if level.get('topMesh'):
        tspec = level.get('topMeshSpec') or level['meshSpec']
        tdia, tspacing = tspec[0], tspec[1]
    else:
        tdia, tspacing = 0, 0
    gross = _area(level.get('outline')) / 1e6
    openings = sum(_area(R.region_polygon(o)) / 1e6 for o in (level.get('openings') or []))
    net = max(0, gross - openings)

    def per_face(sp):
        return net * (1000 / sp) * 2 * 1.12  # both directions, 12 % laps and waste

    m_bottom = per_face(spacing)
    m_top = per_face(tspacing) if faces == 2 else 0
    kg = m_bottom * R.bar_weight_per_m(dia) + m_top * R.bar_weight_per_m(tdia or dia)
    return {'dia': dia, 'spacing': spacing, 'top_dia': tdia or None, 'top_spacing': tspacing or None, 'faces': faces,
            'faces_label': 'TOP & BOTTOM' if faces == 2 else 'BOTTOM', 'net_area_m2': r1(net), 'total_m': r1(m_bottom + m_top),
            'bottom_m': r1(m_bottom), 'top_m': r1(m_top), 'kg': r1(kg), 'bottom_kg': r1(m_bottom * R.bar_weight_per_m(dia)),
            'top_kg': r1(m_top * R.bar_weight_per_m(tdia or dia))}


def concrete_of(level):
    """The concrete of one level: slab net of openings, the extra of drops / thickened zones, the extra of beams below the slab, formwork."""
    gross = _area(level.get('outline')) / 1e6
    openings = sum(_area(R.region_polygon(o)) / 1e6 for o in (level.get('openings') or []))
    net = max(0, gross - openings)
    thk = (level.get('thickness') or 0) / 1000
    slab = net * thk
    drops = 0
    drop_area = 0
    for z in level.get('thickZones') or []:
        if not z.get('polygon') or not z.get('thickness') or z['thickness'] <= (level.get('thickness') or 0):
            continue
        a = _area(z['polygon']) / 1e6
        drop_area += a
        drops += a * ((z['thickness'] - level['thickness']) / 1000)
    beams = 0
    beam_len = 0
    for b in level.get('beams') or []:
        if not b.get('a') or not b.get('b') or not b.get('depth') or b['depth'] <= (level.get('thickness') or 0):
            continue
        L = dist(b['a'], b['b']) / 1000
        beam_len += L
        beams += L * ((b.get('t') or 0) / 1000) * ((b['depth'] - level['thickness']) / 1000)
    per = _perimeter(level.get('outline')) / 1000 + sum(_perimeter(R.region_polygon(o)) / 1000 for o in (level.get('openings') or []))
    return {
        'thickness': level.get('thickness') or 0,
        'gross_area_m2': r1(gross), 'openings_m2': r1(openings), 'net_area_m2': r1(net),
        'slab_m3': r1(slab), 'drops_m3': r1(drops), 'drop_area_m2': r1(drop_area), 'beams_m3': r1(beams), 'beam_length_m': r1(beam_len),
        'total_m3': r1(slab + drops + beams),
        'soffit_formwork_m2': r1(net + drop_area * 0), 'edge_formwork_m2': r1(per * thk), 'formwork_m2': r1(net + per * thk),
        'perimeter_m': r1(per),
    }


def cables_of(level):
    """The post-tensioning of one level from the RAM tendons: per direction and in all."""
    ram = level.get('ram') or {}
    tendons = ram.get('tendons') or []
    if not len(tendons):
        return None
    strand_area = (ram.get('pt') or {}).get('strandArea') or 140
    kg_per_m = (strand_area * STRAND_DENSITY) / 1e6
    dirs = {}
    for t in tendons:
        key = 'A' if t.get('spanSet') == 'latitude' else 'B'
        if key not in dirs:
            dirs[key] = {'direction': key, 'tendons': 0, 'strands': 0, 'tendon_m': 0, 'strand_m': 0, 'cutting_m': 0, 'live_ends': 0, 'dead_ends': 0, 'duct_small_m': 0, 'duct_large_m': 0}
        d = dirs[key]
        live = len([v for v in t['live'] if v])
        Lm = t['length'] / 1000
        d['tendons'] += 1
        d['strands'] += t['strands']
        d['tendon_m'] += Lm
        d['strand_m'] += Lm * t['strands']
        d['cutting_m'] += (Lm + (CUT_ALLOWANCE / 1000) * max(1, live)) * t['strands']
        d['live_ends'] += live
        d['dead_ends'] += 2 - live
        duct = max(0, Lm - (1 if live == 1 else 0))
        if t['strands'] <= SMALL_DUCT_MAX:
            d['duct_small_m'] += duct
        else:
            d['duct_large_m'] += duct
    lst = [{**d, 'tendon_m': r1(d['tendon_m']), 'strand_m': r1(d['strand_m']), 'cutting_m': r1(d['cutting_m']),
            'duct_small_m': r1(d['duct_small_m']), 'duct_large_m': r1(d['duct_large_m']), 'kg': r1(d['cutting_m'] * kg_per_m)}
           for d in sorted(dirs.values(), key=lambda d: d['direction'])]

    def sum_(k):
        return r1(sum(d[k] for d in lst))

    net = concrete_of(level)['net_area_m2']
    kg = sum_('kg')
    return {
        'strand_area_mm2': strand_area, 'strand_kg_per_m': r2(kg_per_m), 'duct_small': '20x50', 'duct_large': '20x70',
        'directions': lst,
        'tendons': sum(d['tendons'] for d in lst), 'strands': sum(d['strands'] for d in lst),
        'tendon_m': sum_('tendon_m'), 'strand_m': sum_('strand_m'), 'cutting_m': sum_('cutting_m'), 'kg': kg,
        'live_ends': sum(d['live_ends'] for d in lst), 'dead_ends': sum(d['dead_ends'] for d in lst),
        'duct_small_m': sum_('duct_small_m'), 'duct_large_m': sum_('duct_large_m'),
        'kg_per_m2': r2(kg / net) if net else None, 'strand_m_per_m2': r2(sum_('strand_m') / net) if net else None,
    }


def quantities(model, pack):
    """The take-off of a whole package: one entry per level and the totals."""
    sheets = (pack or {}).get('sheets') or []
    levels = []
    for level in model.get('levels') or []:
        concrete = concrete_of(level)
        steel = steel_of(level, sheets)
        cables = cables_of(level)
        mesh = mesh_of(level)
        if mesh:
            # the mesh joins the take-off with the scheduled bars (its own line, and in the diameter totals)
            steel['mesh_kg'] = mesh['kg']
            steel['kg'] = r1(steel['kg'] + mesh['kg'])
            steel['top_kg'] = r1(steel['top_kg'] + mesh['top_kg'])
            steel['bottom_kg'] = r1(steel['bottom_kg'] + mesh['bottom_kg'])
            for dia, m, kg in [[mesh['dia'], mesh['bottom_m'], mesh['bottom_kg']], [mesh['top_dia'], mesh['top_m'], mesh['top_kg']]]:
                if not dia or not kg:
                    continue
                d = next((x for x in steel['byDia'] if x['dia'] == dia), None)
                if d:
                    d['kg'] = r1(d['kg'] + kg)
                    d['total_m'] = r1(d['total_m'] + m)
                else:
                    steel['byDia'].append({'dia': dia, 'total_m': m, 'kg': kg, 'count': 0})
            steel['byDia'].sort(key=lambda d: d['dia'])
        levels.append({
            'id': level.get('id'), 'name': level.get('name'), 'thickness': level.get('thickness'),
            'steel': {**steel, 'kg_per_m2': r2(steel['kg'] / concrete['net_area_m2']) if concrete['net_area_m2'] else None,
                      'kg_per_m3': r1(steel['kg'] / concrete['total_m3']) if concrete['total_m3'] else None},
            'mesh': mesh, 'concrete': concrete, 'cables': cables,
        })

    def sum_by(get):
        return r1(sum((get(l) or 0) for l in levels))

    by_dia = {}
    for l in levels:
        for d in l['steel']['byDia']:
            if d['dia'] not in by_dia:
                by_dia[d['dia']] = {'dia': d['dia'], 'total_m': 0, 'kg': 0, 'count': 0}
            by_dia[d['dia']]['total_m'] += d['total_m']
            by_dia[d['dia']]['kg'] += d['kg']
            by_dia[d['dia']]['count'] += d['count']
    pt_levels = [l for l in levels if l['cables']]
    totals = {
        'steel': {'kg': sum_by(lambda l: l['steel']['kg']), 'top_kg': sum_by(lambda l: l['steel']['top_kg']), 'bottom_kg': sum_by(lambda l: l['steel']['bottom_kg']),
                  'other_kg': sum_by(lambda l: l['steel']['other_kg']), 'mesh_kg': sum_by(lambda l: l['steel'].get('mesh_kg')),
                  'byDia': [{**d, 'total_m': r1(d['total_m']), 'kg': r1(d['kg'])} for d in sorted(by_dia.values(), key=lambda d: d['dia'])]},
        'concrete': {'gross_area_m2': sum_by(lambda l: l['concrete']['gross_area_m2']), 'openings_m2': sum_by(lambda l: l['concrete']['openings_m2']),
                     'net_area_m2': sum_by(lambda l: l['concrete']['net_area_m2']), 'slab_m3': sum_by(lambda l: l['concrete']['slab_m3']),
                     'drops_m3': sum_by(lambda l: l['concrete']['drops_m3']), 'beams_m3': sum_by(lambda l: l['concrete']['beams_m3']),
                     'total_m3': sum_by(lambda l: l['concrete']['total_m3']), 'formwork_m2': sum_by(lambda l: l['concrete']['formwork_m2']),
                     'edge_formwork_m2': sum_by(lambda l: l['concrete']['edge_formwork_m2'])},
        'cables': {
            'tendons': sum(l['cables']['tendons'] for l in pt_levels), 'strands': sum(l['cables']['strands'] for l in pt_levels),
            'tendon_m': sum_by(lambda l: (l['cables'] or {}).get('tendon_m')), 'strand_m': sum_by(lambda l: (l['cables'] or {}).get('strand_m')),
            'cutting_m': sum_by(lambda l: (l['cables'] or {}).get('cutting_m')), 'kg': sum_by(lambda l: (l['cables'] or {}).get('kg')),
            'live_ends': sum(l['cables']['live_ends'] for l in pt_levels), 'dead_ends': sum(l['cables']['dead_ends'] for l in pt_levels),
            'duct_small_m': sum_by(lambda l: (l['cables'] or {}).get('duct_small_m')), 'duct_large_m': sum_by(lambda l: (l['cables'] or {}).get('duct_large_m')),
        } if len(pt_levels) else None,
    }
    net = totals['concrete']['net_area_m2']
    totals['steel']['kg_per_m2'] = r2(totals['steel']['kg'] / net) if net else None
    if totals['cables']:
        totals['cables']['kg_per_m2'] = r2(totals['cables']['kg'] / net) if net else None
        totals['cables']['strand_m_per_m2'] = r2(totals['cables']['strand_m'] / net) if net else None
    return {'levels': levels, 'totals': totals}


def cost_study(q, rates=None):
    """
    The cost study: the take-off priced with the office rates. `rates` (per unit, one currency): steel_per_ton,
    rebar_labour_per_ton, concrete_per_m3, formwork_per_m2, strand_per_kg, anchor_live, anchor_dead, duct_per_m,
    pt_labour_per_m2, markup_pct, vat_pct. Returns the lines per level and in all.
    """
    if rates is None:
        rates = {}
    R0 = {'steel_per_ton': 3200, 'rebar_labour_per_ton': 350, 'concrete_per_m3': 280, 'formwork_per_m2': 45, 'strand_per_kg': 9.5,
          'anchor_live': 45, 'anchor_dead': 25, 'duct_per_m': 6, 'pt_labour_per_m2': 18, 'markup_pct': 15, 'vat_pct': 15, 'currency': 'SAR', **rates}

    def lines_of(steel, concrete, cables):
        lines = [
            {'key': 'steel', 'unit': 't', 'qty': r2(steel['kg'] / 1000), 'rate': R0['steel_per_ton']},
            {'key': 'rebar_labour', 'unit': 't', 'qty': r2(steel['kg'] / 1000), 'rate': R0['rebar_labour_per_ton']},
            {'key': 'concrete', 'unit': 'm3', 'qty': concrete['total_m3'], 'rate': R0['concrete_per_m3']},
            {'key': 'formwork', 'unit': 'm2', 'qty': concrete['formwork_m2'], 'rate': R0['formwork_per_m2']},
        ]
        if cables:
            lines.extend([
                {'key': 'strand', 'unit': 'kg', 'qty': cables['kg'], 'rate': R0['strand_per_kg']},
                {'key': 'anchor_live', 'unit': 'no', 'qty': cables['live_ends'], 'rate': R0['anchor_live']},
                {'key': 'anchor_dead', 'unit': 'no', 'qty': cables['dead_ends'], 'rate': R0['anchor_dead']},
                {'key': 'duct', 'unit': 'm', 'qty': r1(cables['duct_small_m'] + cables['duct_large_m']), 'rate': R0['duct_per_m']},
                {'key': 'pt_labour', 'unit': 'm2', 'qty': concrete['net_area_m2'], 'rate': R0['pt_labour_per_m2']},
            ])
        for l in lines:
            l['amount'] = js_round(l['qty'] * l['rate'])
        direct = sum(l['amount'] for l in lines)
        markup = js_round((direct * (R0.get('markup_pct') or 0)) / 100)
        vat = js_round(((direct + markup) * (R0.get('vat_pct') or 0)) / 100)
        return {'lines': lines, 'direct': direct, 'markup': markup, 'vat': vat, 'total': direct + markup + vat,
                'per_m2': js_round((direct + markup) / concrete['net_area_m2']) if concrete['net_area_m2'] else None}

    return {
        'currency': R0['currency'], 'rates': R0,
        'levels': [{'id': l.get('id'), 'name': l.get('name'), **lines_of(l['steel'], l['concrete'], l.get('cables'))} for l in q['levels']],
        'totals': lines_of(q['totals']['steel'], q['totals']['concrete'], q['totals'].get('cables')),
    }
