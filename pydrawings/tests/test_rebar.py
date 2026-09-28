"""Tests for pydrawings.rebar (run from `pydrawings/`: python3 -m unittest tests.test_rebar)."""
import unittest

from pydrawings.rebar import (
    DEFAULT_SPEC, U_BOTTOM_LEG, bar_weight_per_m, split_run, lap_length, support_columns, top_at_columns, BarList,
    SUPPORTS_KEY, punching, length_table,
)


def make_level(columns, w=20000, h=12000, thickness=250):
    outline = [{'x': 0, 'y': 0}, {'x': w, 'y': 0}, {'x': w, 'y': h}, {'x': 0, 'y': h}]
    return {
        'id': 'L1', 'thickness': thickness, 'outline': outline,
        'bbox': {'minX': 0, 'minY': 0, 'maxX': w, 'maxY': h, 'w': w, 'h': h, 'cx': w / 2, 'cy': h / 2},
        'columns': columns, 'walls': [], 'beams': [], 'openings': [], 'thickZones': [],
    }


class TestRebar(unittest.TestCase):
    def test_default_spec(self):
        self.assertEqual(DEFAULT_SPEC['uEdge']['total'], 4000)
        self.assertEqual(DEFAULT_SPEC['topColumns']['dia'], 16)
        self.assertEqual(DEFAULT_SPEC['lambda'], 1)
        self.assertEqual(DEFAULT_SPEC['blockBeam']['maxGap'], 500)
        self.assertEqual(DEFAULT_SPEC['pourStrip']['wall']['uTotal'], 2500)
        self.assertEqual(U_BOTTOM_LEG, 500)

    def test_bar_weight(self):
        self.assertAlmostEqual(bar_weight_per_m(12), 0.006165 * 144)
        self.assertAlmostEqual(bar_weight_per_m(12), 0.88776)

    def test_lap_and_split(self):
        lap = lap_length(DEFAULT_SPEC, 12)
        # ld = 420 / (2.1 * sqrt(30)) * 12 = 438.2 -> 440; 1.3 * 440 = 572 -> 600
        self.assertEqual(lap, 600)
        pieces = split_run(27000, stock=12000, lap=lap)
        self.assertEqual(len(pieces), 3)
        self.assertEqual(pieces, [12000, 12000, 4200])
        self.assertEqual(split_run(9000, {'stock': 12000, 'lap': lap}), [9000])
        self.assertEqual(split_run(27000, stock=12000, lap=lap, stagger=True)[0], 6000)

    def test_length_table(self):
        t = length_table(DEFAULT_SPEC)
        self.assertEqual([r['dia'] for r in t], [10, 12, 14, 16, 18, 20, 25])
        self.assertEqual(t[1]['lap_bottom'], 600)

    def test_support_columns_merge(self):
        # C1 / C2: 500 x 500 columns, faces 300 mm apart -> one support; C3 1200 mm away stays alone
        cols = [
            {'id': 'C1', 'shape': 'rect', 'cx': 5000, 'cy': 6000, 'w': 500, 'h': 500},
            {'id': 'C2', 'shape': 'rect', 'cx': 5800, 'cy': 6000, 'w': 500, 'h': 500},
            {'id': 'C3', 'shape': 'rect', 'cx': 12000, 'cy': 6000, 'w': 500, 'h': 500},
            {'id': 'C4', 'shape': 'rect', 'cx': 13700, 'cy': 6000, 'w': 500, 'h': 500},
        ]
        level = make_level(cols)
        sup = support_columns(level)
        self.assertEqual([c['id'] for c in sup], ['C1+C2', 'C3', 'C4'])
        m = sup[0]
        self.assertEqual(m['shape'], 'rect')
        self.assertEqual(m['w'], 1300)
        self.assertEqual(m['h'], 500)
        self.assertEqual(m['cx'], 5400)
        self.assertEqual([c['id'] for c in m['merged']], ['C1', 'C2'])
        self.assertIs(sup[1], cols[2])
        # cached on the level under the private key, reused on the second call
        self.assertIn(SUPPORTS_KEY, level)
        self.assertIs(support_columns(level), sup)
        self.assertIsNot(support_columns(level, 100), sup)

    def test_top_at_columns(self):
        cols = [
            {'id': 'C1', 'shape': 'rect', 'cx': 6000, 'cy': 6000, 'w': 500, 'h': 500},
            {'id': 'C2', 'shape': 'rect', 'cx': 14000, 'cy': 6000, 'w': 500, 'h': 500},
        ]
        level = make_level(cols)
        t = top_at_columns(level, DEFAULT_SPEC)
        self.assertEqual(len(t['columns']), 2)
        self.assertEqual(level['maxSpan'], 8000)
        for c in t['columns']:
            per = c['per']
            self.assertGreaterEqual(per['x']['straight'], 4000)
            self.assertGreaterEqual(per['y']['straight'], 4000)
            self.assertEqual(per['x']['shape'], 'STR')
            self.assertEqual(per['x']['code'], 'T2')
            self.assertEqual(per['y']['code'], 'T1')
            self.assertGreaterEqual(per['x']['n'], 4)
            self.assertIn('mark', c['type']['x'])  # (as in JS: the mark sits on the type's per, i.e. the first column's)
        # both columns are interior: one type, 4 m bars each way
        self.assertEqual(len(t['types']), 1)
        self.assertEqual(t['types'][0]['id'], 'TC1')
        self.assertEqual(t['types'][0]['columns'], ['C1', 'C2'])
        self.assertEqual(t['types'][0]['x']['length'], 4000)
        self.assertEqual(t['uEnd']['leg'], 700)
        self.assertEqual(t['uEnd']['label'], 'U500')
        rows = t['lists']['x'].rows()
        self.assertEqual(rows[0]['mark'], 'T2-01')
        self.assertEqual(rows[0]['qty'], t['types'][0]['x']['n'] * 2)
        self.assertEqual(len(t['checks']), 4)

    def test_bar_list_marks(self):
        bl = BarList('T2')
        a = bl.add({'dia': 12, 'shape': 'STR', 'length': 3000, 'qty': 4, 'spacing': 150, 'zone': 'Z1'})
        b = bl.add({'dia': 12, 'shape': 'STR', 'length': 5000, 'qty': 2, 'spacing': 200, 'zone': 'Z2'})
        bl.add({'dia': 12, 'shape': 'STR', 'length': 3000, 'qty': 1, 'spacing': 200, 'zone': 'Z1'})
        rows = bl.rows()
        self.assertEqual([r['mark'] for r in rows], ['T2-01', 'T2-02'])
        self.assertEqual(rows[0]['length'], 5000)  # longer first within a diameter / shape
        self.assertIs(a, [e for e in bl.entries if e['length'] == 3000][0])
        self.assertEqual(rows[1]['qty'], 5)
        self.assertEqual(rows[1]['spacing'], 'VAR.')
        self.assertEqual(rows[0]['spacing'], 200)
        self.assertEqual(rows[1]['total_m'], 15)
        self.assertEqual(rows[1]['weight_kg'], 13.3)
        tot = bl.totals()
        self.assertEqual(tot['byDia'][0]['dia'], 12)
        self.assertAlmostEqual(tot['weight_kg'], 13.3 + rows[0]['weight_kg'])
        self.assertEqual(BarList('U').prefix, 'U')
        self.assertEqual(BarList('PS').prefix, 'PS-')

    def test_punching(self):
        cols = [{'id': 'C1', 'shape': 'rect', 'cx': 6000, 'cy': 6000, 'w': 500, 'h': 500}]
        p = punching(make_level(cols), DEFAULT_SPEC)
        self.assertEqual(p['d'], 209)
        self.assertEqual(p['rowSpacing'], 100)
        self.assertEqual(p['rows'], 5)
        self.assertEqual(len(p['columns'][0]['sides']), 4)
        self.assertEqual(p['types'][0]['label'], '5X6-T10-100')


if __name__ == '__main__':
    unittest.main()
