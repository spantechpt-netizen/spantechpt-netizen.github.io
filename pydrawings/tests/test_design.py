"""Tests for pydrawings.design (run from `pydrawings/`: python3 -m unittest tests.test_design).
Ported from test/shopdrawings.test.js (the pour strip wall test, the polyline test, the drop bar at the slab edge test)."""
import math
import re
import unittest

from pydrawings.rebar import DEFAULT_SPEC
from pydrawings.design import design_additions, mark_core_walls, clip_to_slab, office_bar, draw_existing


def make_spec():
    spec = {**DEFAULT_SPEC, 'cover': 25}
    for k in ['uEdge', 'topColumns', 'thicknessMesh', 'openings', 'punching', 'drops']:
        spec[k] = {**DEFAULT_SPEC[k]}
    return spec


class RecordingPen:
    """The JS test's recording pen: keeps the polylines and the texts, answers everything else with an empty entity."""

    def __init__(self):
        self.plines = []
        self.texts = []

    def pline(self, pts, o=None, **kw):
        e = {'pts': pts, 'layer': (o or {}).get('layer') or kw.get('layer')}
        self.plines.append(e)
        return e

    def text(self, p, s, o=None, **kw):
        self.texts.append(s)
        return {'str': s}

    def circle(self, *a, **kw):
        return {}

    def line(self, *a, **kw):
        return {}

    def dimension(self, *a, **kw):
        return {}

    def hatch(self, *a, **kw):
        return {}


class TestDesign(unittest.TestCase):
    def test_pour_strip_against_retaining_wall(self):
        outline = [{'x': 0, 'y': 0}, {'x': 30000, 'y': 0}, {'x': 30000, 'y': 8000}, {'x': 0, 'y': 8000}]
        level = {
            'id': 'L01', 'name': 'T', 'thickness': 250, 'outline': outline, 'bbox': {'minX': 0, 'minY': 0, 'maxX': 30000, 'maxY': 8000, 'w': 30000, 'h': 8000},
            'grid': {'x': [{'x': 0, 'label': 'A'}, {'x': 30000, 'label': 'B'}], 'y': [{'y': 0, 'label': '1'}, {'y': 8000, 'label': '2'}]},
            'columns': [], 'openings': [], 'voids': [], 'sunken': [], 'stairs': [], 'thickZones': [], 'beams': [], 'edges': [],
            # (the JS fixture has no cx / cy / w / h on the wall: JS reads them as undefined in rebar.topAtColumns, Python needs them)
            'walls': [{'id': 'W1', 'a': {'x': 0, 'y': 0}, 'b': {'x': 0, 'y': 8000}, 't': 250, 'polygon': [{'x': -250, 'y': 0}, {'x': 0, 'y': 0}, {'x': 0, 'y': 8000}, {'x': -250, 'y': 8000}], 'length': 8000, 'cx': -125, 'cy': 4000, 'w': 250, 'h': 8000}],
            'pourStrips': [{'id': 'PS1', 'polygon': [{'x': 0, 'y': 0}, {'x': 1000, 'y': 0}, {'x': 1000, 'y': 8000}, {'x': 0, 'y': 8000}], 'width': 1000, 'length': 8000},
                           {'id': 'PS2', 'polygon': [{'x': 15000, 'y': 0}, {'x': 16000, 'y': 0}, {'x': 16000, 'y': 8000}, {'x': 15000, 'y': 8000}], 'width': 1000, 'length': 8000}],
            'existing': {'lines': [], 'callouts': [], 'dims': [], 'dots': [], 'items': []}, 'ram': {'tendons': [], 'bands': []},
        }
        spec = make_spec()
        mark_core_walls(level)
        adds = design_additions(level, spec)
        d8 = [it for it in adds['items'] if it['detail'] == 'D8' and 'PS1' in it['zone']]
        tb = next((it for it in d8 if it['l1'] == 'T12-200 TOP&BOTTOM'), None)
        self.assertTrue(tb and tb['l2'] == 'L=2000' and tb['face'] == 'TB' and round(tb['a']['x']) == 0 and round(tb['b']['x']) == 2000 and tb.get('posCands'), 'straight T12-200 top and bottom, 2 m from the wall face into the slab, the symbol free to slide along the strip')
        u_wall = next((it for it in d8 if it['l1'] == 'T12-200 U-BAR (WALL)'), None)
        self.assertTrue(u_wall and u_wall['l2'] == 'L=2500' and u_wall.get('hairpin') and round(u_wall['a']['x']) == -250 and u_wall['b']['x'] > 500, 'the wall U-bar 2500 anchored one wall thickness inside the wall, out into the strip')
        u_slab = next((it for it in d8 if it['l1'] == 'T12-200 U-BAR'), None)
        self.assertTrue(u_slab and u_slab['l2'] == 'L=2000' and u_slab.get('hairpin') and u_slab['a']['x'] > 1000 and u_slab['b']['x'] < 1000, 'the slab-side U-bar 2000 straddles the joint')
        along = next(it for it in d8 if re.search('ALONG STRIP', it['l1']))
        self.assertEqual(along['l1'], 'T12-150 (T&B) ALONG STRIP')
        self.assertEqual(along['l2'], 'L=8000')
        self.assertTrue(any(re.search('CAST AGAINST A RETAINING WALL - OFFICE DETAIL', a) for a in adds['assumptions']))
        # a plain strip far from the wall keeps the standard detail, and its 8 m bars need no lap; a 27 m strip would
        plain = [it for it in adds['items'] if it['detail'] == 'D8' and 'PS2' in it['zone']]
        # the internal strip (office detail): on each side T12-200 TOP & BOTTOM L=2000 from the far face of the strip across it
        # into the slab on that side, and a U-bar T12-200 L=2400 closed at the face with its legs out into the slab
        tbs = [it for it in plain if it['l1'] == 'T12-200 TOP & BOTTOM']
        self.assertEqual(len(tbs), 2)
        self.assertTrue(all(it['l2'] == 'L=2000' and it['face'] == 'TB' and it.get('pairOff') and it.get('posCands') and it.get('dist') for it in tbs), 'a pair symbol per side, sliding along the strip, with its distribution')
        left = next((it for it in tbs if it['b']['x'] < it['a']['x']), None)
        right = next((it for it in tbs if it['b']['x'] > it['a']['x']), None)
        self.assertTrue(left and round(left['a']['x']) == 16000 and round(left['b']['x']) == 14000 and left['dist']['p']['x'] < 15000, 'the left set: from the right face across the strip 1 m into the slab on the left, its dot on the left line')
        self.assertTrue(right and round(right['a']['x']) == 15000 and round(right['b']['x']) == 17000 and right['dist']['p']['x'] > 16000, 'the right set: from the left face to 1 m past the right face')
        us = [it for it in plain if it['l1'] == 'T12-200 U-BAR']
        self.assertEqual(len(us), 2)
        self.assertTrue(all(it.get('hairpin') and it['l2'] == 'L=2400' and it.get('dist') for it in us), 'U-bars 2400 with their dots')
        self.assertTrue(any(round(it['a']['x']) == 15000 and it['b']['x'] < 14000 for it in us) and any(round(it['a']['x']) == 16000 and it['b']['x'] > 17000 for it in us), 'closed at each face, legs (2400 - 200) / 2 = 1100 out into the slab')
        self.assertTrue(any(re.search(r'PS2.*OFFICE DETAIL: T12@200 L=2000 TOP & BOTTOM LAPPING ACROSS EACH JOINT', a) for a in adds['assumptions']))
        level['pourStrips'] = [{'id': 'PS3', 'polygon': [{'x': 5000, 'y': 0}, {'x': 32000, 'y': 0}, {'x': 32000, 'y': 1000}, {'x': 5000, 'y': 1000}], 'width': 1000, 'length': 27000}]
        level['outline'] = [{'x': 0, 'y': 0}, {'x': 40000, 'y': 0}, {'x': 40000, 'y': 8000}, {'x': 0, 'y': 8000}]
        level['bbox'] = {'minX': 0, 'minY': 0, 'maxX': 40000, 'maxY': 8000, 'w': 40000, 'h': 8000}
        long = next(it for it in design_additions(level, spec)['items'] if it['detail'] == 'D8' and re.search('ALONG STRIP', it['l1']))
        self.assertTrue(re.search(r'^L=27000 \(3 PCS, LAP \d+\)$', long['l2']), f"a 27 m bar is written in stock pieces with the lap: {long['l2']}")

    def test_every_bar_is_one_polyline(self):
        S = 100
        # a hairpin (pour strip / wall U-bar): leg - closing bar - leg in ONE polyline of 4 vertices
        pl = RecordingPen()
        office_bar(pl, S, {'detail': 'D8', 'face': 'TB', 'a': {'x': 0, 'y': 0}, 'b': {'x': 0, 'y': 1100}, 'l1': 'T12-200 U-BAR', 'l2': 'L=2400', 'hairpin': True, 'side': 1, 'noTag': True}, 'bars')
        self.assertEqual(len(pl.plines), 1, 'one line, not three')
        self.assertEqual(len(pl.plines[0]['pts']), 4)
        # a top bar ending in a U at one end and an L at the other: the legs join the run (5 + 1 + 1 = one polyline)
        pl = RecordingPen()
        office_bar(pl, S, {'detail': None, 'face': 'T', 'a': {'x': 0, 'y': 0}, 'b': {'x': 4000, 'y': 0}, 'l1': 'T12-150 (T)', 'l2': 'L=4000', 'side': 1, 'noTag': True, 'uEnd': {'start': 'U', 'end': 'L'}}, 'bars')
        self.assertEqual(len(pl.plines), 1)
        self.assertEqual(len(pl.plines[0]['pts']), 5, 'U leg (2 vertices) + run (2) + L leg (1)')
        self.assertTrue('U500' in pl.texts and 'L400' in pl.texts, 'the end tags are still written')
        # the L-bar at an edge beam: its leg is part of the run
        pl = RecordingPen()
        office_bar(pl, S, {'detail': 'D1', 'face': 'T', 'a': {'x': 0, 'y': 0}, 'b': {'x': 3600, 'y': 0}, 'l1': 'T12-150 LBAR (T)', 'l2': 'L=4000', 'side': 1, 'legEnd': 'start', 'noTag': True}, 'bars')
        self.assertEqual(len(pl.plines), 1)
        self.assertEqual(len(pl.plines[0]['pts']), 3)
        # a drop bar: rises and continuations in the same polyline; a side clipped at the slab edge draws no leg there
        pl = RecordingPen()
        office_bar(pl, S, {'detail': 'D4', 'face': 'B', 'a': {'x': 1050, 'y': 0}, 'b': {'x': 5950, 'y': 0}, 'l1': 'T12-150 (B)', 'l2': 'L=7000', 'side': 1, 'noTag': True, 'bend': {'rise': 50, 'beyondA': 1500, 'beyondB': 500}, 'extra': 2100}, 'bars')
        self.assertEqual(len(pl.plines), 1)
        self.assertEqual(len(pl.plines[0]['pts']), 6)
        pl = RecordingPen()
        office_bar(pl, S, {'detail': 'D4', 'face': 'B', 'a': {'x': 1050, 'y': 0}, 'b': {'x': 5950, 'y': 0}, 'l1': 'T12-150 (B)', 'l2': 'L=5450', 'side': 1, 'noTag': True, 'bend': {'rise': 50, 'beyondA': 0, 'beyondB': 500, 'noA': True}, 'extra': 550}, 'bars')
        self.assertEqual(len(pl.plines[0]['pts']), 4, 'no rise and no continuation on the clipped side')
        # the designer's own bars re-emitted with their U ends: one polyline each
        pl = RecordingPen()
        draw_existing(pl, S, {'lines': [{'face': 'T', 'a': {'x': 0, 'y': 0}, 'b': {'x': 3000, 'y': 0}, 'uEnd': {'start': 'U', 'end': False}}], 'callouts': [], 'dims': [], 'dots': [], 'items': []}, ['T'])
        self.assertEqual(len(pl.plines), 1)
        self.assertEqual(len(pl.plines[0]['pts']), 4)

    def test_drop_bar_beside_slab_edge_or_opening(self):
        outline = [{'x': 0, 'y': 0}, {'x': 20000, 'y': 0}, {'x': 20000, 'y': 12000}, {'x': 0, 'y': 12000}]
        level = {
            'id': 'L01', 'name': 'T', 'thickness': 250, 'outline': outline, 'bbox': {'minX': 0, 'minY': 0, 'maxX': 20000, 'maxY': 12000, 'w': 20000, 'h': 12000},
            'grid': {'x': [{'x': 0, 'label': 'A'}, {'x': 20000, 'label': 'B'}], 'y': [{'y': 0, 'label': '1'}, {'y': 12000, 'label': '2'}]},
            # an edge column whose drop panel touches the slab edge (x = 0) and an opening 400 past the drop's other face
            'columns': [{'id': 'C1', 'shape': 'rect', 'cx': 1300, 'cy': 6000, 'w': 600, 'h': 600}],
            'thickZones': [{'id': 'Z1', 'kind': 'drop', 'thickness': 400, 'polygon': [{'x': 0, 'y': 4500}, {'x': 2600, 'y': 4500}, {'x': 2600, 'y': 7500}, {'x': 0, 'y': 7500}]}],
            'openings': [{'id': 'O1', 'kind': 'polygon', 'polygon': [{'x': 3000, 'y': 5000}, {'x': 4500, 'y': 5000}, {'x': 4500, 'y': 7000}, {'x': 3000, 'y': 7000}]}],
            'voids': [], 'sunken': [], 'stairs': [], 'beams': [], 'edges': [], 'walls': [],
            'existing': {'lines': [], 'callouts': [], 'dims': [], 'dots': [], 'items': []}, 'ram': {'tendons': [], 'bands': []},
        }
        spec = make_spec()
        mark_core_walls(level)
        adds = design_additions(level, spec)
        adds['items'] = clip_to_slab(level, adds['items'], spec)  # as the package does before drawing
        d4x = next((it for it in adds['items'] if it['detail'] == 'D4' and abs(it['a']['y'] - it['b']['y']) < 1), None)
        self.assertTrue(d4x, 'the drop bar along X')
        self.assertTrue(d4x['bend'].get('noA') and d4x['bend']['beyondA'] == 0, 'at the slab edge: no rise, no continuation outside the slab')
        self.assertTrue(d4x['bend']['beyondB'] == 400 and not d4x['bend'].get('noB'), f"towards the opening the continuation (run end 2550, opening at 3000) stops 50 before it ({d4x['bend']['beyondB']})")
        self.assertEqual(d4x['l2'], f"L={math.floor(math.hypot(d4x['a']['x'] - d4x['b']['x'], d4x['a']['y'] - d4x['b']['y']) + d4x['extra'] + 0.5)}", 'the written length follows the drawn bar')
        self.assertEqual(d4x['extra'], d4x['bend']['rise'] + d4x['bend']['beyondB'], 'one rise (the 150 step) and the shortened continuation only')
        d4y = next((it for it in adds['items'] if it['detail'] == 'D4' and abs(it['a']['x'] - it['b']['x']) < 1), None)
        self.assertTrue(d4y and not d4y['bend'].get('noA') and not d4y['bend'].get('noB') and d4y['bend']['beyondA'] == d4y['bend']['beyondB'], 'the Y bar keeps both legs inside the slab')


if __name__ == '__main__':
    unittest.main()
