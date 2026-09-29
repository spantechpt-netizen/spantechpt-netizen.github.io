"""Tests for `pydrawings.extract` on a hand-built drawing dict (the shape `dxf_reader.parse_dxf` returns)."""
import unittest

from pydrawings.extract import extract_model, classify_layer, read_spec_from_text, chain_segments


def _rect(x, y, w, h, layer):
    return {'type': 'LWPOLYLINE', 'layer': layer, 'closed': True,
            'pts': [{'x': x, 'y': y, 'bulge': 0}, {'x': x + w, 'y': y, 'bulge': 0}, {'x': x + w, 'y': y + h, 'bulge': 0}, {'x': x, 'y': y + h, 'bulge': 0}]}


def _text(x, y, s, layer, h=200, type_='TEXT'):
    return {'type': type_, 'layer': layer, 'x': x, 'y': y, 'xs': [x], 'ys': [y], 'text': s, 'height': h, 'rotation': 0, 'halign': 0}


def build_sample_dxf():
    # a 30 x 20 m slab, two 600 x 600 columns, one opening, a T.O.S +12.35 tag (block attributes in real drawings)
    ents = [
        _rect(0, 0, 30000, 20000, '0-slab'),
        _rect(10000 - 300, 10000 - 300, 600, 600, '0-columns'),
        _rect(20000 - 300, 10000 - 300, 600, 600, '0-columns'),
        _rect(5000, 5000, 1500, 1200, '0-openings'),
        _text(15000, 3000, 'T.O.S', 'A-TEXT', type_='ATTRIB'),
        _text(15000, 2700, '+12.35', 'A-TEXT', type_='ATTRIB'),
    ]
    return {'header': {'$INSUNITS': 4}, 'blocks': {}, 'entities': ents}


class ExtractModelTest(unittest.TestCase):
    def test_extract_model(self):
        model = extract_model(build_sample_dxf(), {})
        self.assertEqual(len(model['levels']), 1)
        L = model['levels'][0]
        self.assertEqual(L['id'], 'L01')
        self.assertEqual([(p['x'], p['y']) for p in L['outline']], [(0, 0), (30000, 0), (30000, 20000), (0, 20000)])
        self.assertEqual(L['bbox']['w'], 30000)
        self.assertEqual(L['bbox']['h'], 20000)
        self.assertEqual(len(L['columns']), 2)
        self.assertEqual(sorted((c['cx'], c['cy'], c['w'], c['h']) for c in L['columns']), [(10000, 10000, 600, 600), (20000, 10000, 600, 600)])
        self.assertEqual(len(L['openings']), 1)
        self.assertEqual(L['openings'][0]['kind'], 'rect')
        self.assertEqual(L['openings'][0]['id'], 'O1')
        self.assertEqual(L['openings'][0]['rect'], {'x': 5000, 'y': 5000, 'w': 1500, 'h': 1200})
        self.assertEqual(len(L['levelTags']), 1)
        self.assertEqual(L['levelTags'][0]['value'], '+12.35')
        self.assertEqual(L['levelTags'][0]['label'], 'T.O.S')
        self.assertEqual(L['tos'], '+12.35')
        # no grid drawn: derived from the columns, lettered / numbered
        self.assertEqual(L['grid']['source'], 'derived from column positions')
        self.assertEqual([g['label'] for g in L['grid']['x']], ['A', 'B'])
        self.assertEqual([g['label'] for g in L['grid']['y']], ['1'])
        self.assertEqual(sorted(c['id'] for c in L['columns']), ['A/1', 'B/1'])
        self.assertEqual(L['thickness'], 250)
        self.assertEqual(L['name'], 'LEVEL 1')
        self.assertEqual(model['source']['units'], 'mm')
        self.assertEqual(model['source']['layers'], ['0-columns', '0-openings', '0-slab', 'A-TEXT'])
        self.assertTrue(any('Slab thickness not stated' in a['text'] for a in model['assumptions']))
        self.assertTrue(any(f.startswith('L01 LEVEL 1: 2 columns, grid A-B / 1, 1 openings') for f in model['findings']))

    def test_level_names_option(self):
        model = extract_model(build_sample_dxf(), {'levelNames': ['BASEMENT']})
        self.assertEqual(model['levels'][0]['name'], 'BASEMENT')

    def test_classify_layer(self):
        self.assertEqual(classify_layer('S-COLS'), 'column')
        self.assertEqual(classify_layer('S-COLUMN-HATCH'), 'column')
        self.assertEqual(classify_layer('S-SLAB-OPENING'), 'opening')
        self.assertEqual(classify_layer('S-GRID'), 'grid')
        self.assertEqual(classify_layer('S-PT-ZONE'), 'pt')
        self.assertEqual(classify_layer('S-VOIDS'), 'void')
        self.assertEqual(classify_layer('S-UBAR'), 'ubar')
        self.assertEqual(classify_layer('S-SLAB-EDGE'), 'slab')
        self.assertEqual(classify_layer('COLOR-FILL'), 'other')

    def test_read_spec_from_text(self):
        assumptions = []
        spec = read_spec_from_text("DESIGN CODE: SBC 304-18\nCONCRETE f'c = 40 MPa\nfy = 420 MPa\nCOVER 30 mm\nBOTTOM MESH T10@150 B.W.\nTOP BARS OVER COLUMNS T20@100", assumptions)
        self.assertEqual(spec['code_reference'], 'SBC 304-18')
        self.assertEqual(spec['fc'], 40)
        self.assertEqual(spec['fy'], 420)
        self.assertEqual(spec['cover'], 30)
        self.assertEqual((spec['bottom']['dia'], spec['bottom']['spacing']), (10, 150))
        self.assertEqual((spec['topColumns']['dia'], spec['topColumns']['spacing']), (20, 100))
        self.assertEqual(spec['sources']['fc'], 'drawing')
        bare = []
        s2 = read_spec_from_text('', bare)
        self.assertIsNone(s2['code_reference'])
        self.assertTrue(any(a['text'].startswith('Design code not stated') for a in bare))
        self.assertTrue(any(a['text'] == 'Stock bar length 12 m; laps staggered so that not more than 50 % of bars lap at one section.' for a in bare))

    def test_chain_segments(self):
        segs = [[{'x': 0, 'y': 0}, {'x': 100, 'y': 0}], [{'x': 100, 'y': 100}, {'x': 0, 'y': 100}],
                [{'x': 100, 'y': 0}, {'x': 100, 'y': 100}], [{'x': 0, 'y': 100}, {'x': 0, 'y': 0}]]
        loops = chain_segments(segs)
        self.assertEqual(len(loops), 1)
        self.assertEqual([(p['x'], p['y']) for p in loops[0]], [(0, 0), (100, 0), (100, 100), (0, 100)])


if __name__ == '__main__':
    unittest.main()
