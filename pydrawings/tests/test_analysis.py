"""Tests of the analysis modules: beam_design, punching (decision rules), quantities (cost study) and dxf_bars."""
import copy
import unittest

from pydrawings.beam_design import three_moment, analyse_beam, flexure_as, pick_bars, shear_design, deflection_check, beam_blocking_after
from pydrawings.dxf_bars import parse_callout, bar_figures, takeoff_from_bars, apply_takeoff
from pydrawings.punching import blocking_after, override_columns
from pydrawings.quantities import cost_study


class BeamDesignTest(unittest.TestCase):
    def test_three_moment_two_equal_spans(self):
        # two 6 m spans, w = 30 kN/m on both: M at the middle support = -w L² / 8 = -135 kN·m
        M = three_moment([6000, 6000], [30, 30])
        self.assertEqual(len(M), 3)
        self.assertEqual(M[0], 0)
        self.assertEqual(M[2], 0)
        self.assertAlmostEqual(M[1], -30 * 36 / 8, places=6)
        # a single span has no interior support
        self.assertEqual(three_moment([6000], [30]), [0, 0])
        # the end moments are carried through
        self.assertEqual(three_moment([6000], [30], [-10, -20]), [-10, -20])

    def test_analyse_beam_two_equal_spans(self):
        wD, wL = 20, 10
        spans = [{'length': 6000}, {'length': 6000}]
        env = analyse_beam(spans, wD, wL)
        wu = 1.2 * wD + 1.6 * wL
        lo = wu * 36 / 8  # both spans fully loaded: 144 kN·m
        self.assertLess(env['Mneg'][1], 0, 'hogging at the middle support is negative')
        self.assertGreaterEqual(abs(env['Mneg'][1]), lo - 1e-9)
        self.assertLess(abs(env['Mneg'][1]), lo * 1.1, 'patterned live load adds a little, not much')
        self.assertEqual(env['Mneg'][0], 0)
        self.assertEqual(env['Mneg'][2], 0)
        # sagging: alternate span loaded gives more than the all-loaded case (9 wu L²/128 = 101.25)
        self.assertGreater(env['Mpos'][0], 9 * wu * 36 / 128 - 1e-9)
        self.assertLess(env['Mpos'][0], wu * 36 / 8)
        # shears: the middle support end carries more than the outer end
        self.assertGreater(env['Vend'][0][1], env['Vend'][0][0])
        self.assertAlmostEqual(env['Vend'][0][1], 5 * wu * 6 / 8, delta=1)
        # service moments, all spans loaded, dead and live apart
        self.assertAlmostEqual(env['service']['dead']['M'][1], -wD * 36 / 8, places=6)
        self.assertAlmostEqual(env['service']['live']['M'][1], -wL * 36 / 8, places=6)
        self.assertEqual(len(env['service']['dead']['pos']), 2)

    def test_analyse_beam_cantilever(self):
        env = analyse_beam([{'length': 6000}], 20, 10, {'left': 2000, 'right': None})
        wu = 1.2 * 20 + 1.6 * 10
        self.assertAlmostEqual(env['Mneg'][0], -wu * 4 / 2, places=6)
        self.assertEqual(env['Mneg'][1], 0)

    def test_flexure_as(self):
        f = flexure_as(200, 300, 550, 30, 420)
        self.assertTrue(f['ok'])
        self.assertGreater(f['as'], 900)
        self.assertLess(f['as'], 1400)
        self.assertIn('et', f)
        self.assertEqual(flexure_as(0, 300, 550, 30, 420), {'as': 0, 'ok': True})
        # a section far too small cannot carry the moment singly reinforced
        self.assertEqual(flexure_as(2000, 200, 300, 30, 420), {'as': None, 'ok': False})

    def test_pick_bars(self):
        best = pick_bars(900, 300)
        self.assertEqual(best['text'], '3T20')
        self.assertEqual(best['n'], 3)
        self.assertEqual(best['dia'], 20)
        self.assertEqual(best['area'], 942)
        self.assertNotIn('overflow', best)
        # a very large requirement overflows the width into 32s
        big = pick_bars(20000, 300)
        self.assertTrue(big.get('overflow'))
        self.assertEqual(big['dia'], 32)

    def test_shear_design(self):
        sh = shear_design(150, 300, 550, 30, 420)
        self.assertTrue(sh['ok'])
        self.assertIn(sh['dia'], (10, 12))
        self.assertIn(sh['legs'], (2, 4))
        self.assertGreaterEqual(sh['spacing'], 50)
        self.assertEqual(sh['spacing'] % 25, 0)
        self.assertEqual(sh['text'], f"T{sh['dia']}-{sh['legs']}L@{sh['spacing']}")
        self.assertIn('Vc', sh)
        self.assertIn('Vs', sh)
        # far too much shear for the section
        self.assertFalse(shear_design(2000, 300, 550, 30, 420)['ok'])

    def test_deflection_check(self):
        out = deflection_check({'L': 6000, 'b': 300, 'h': 600, 'd': 532, 'as': 942, 'fc': 30, 'ends': 2, 'Ma': 100, 'MaLeft': -80, 'MaRight': -80, 'live': 30})
        self.assertTrue(out['table_ok'])
        self.assertTrue(out['ok'])
        self.assertEqual(out['h_min'], 286)
        self.assertEqual(out['ratio'], 0)
        # keywords work too (`as_` for the JS `as`)
        out2 = deflection_check(L=6000, b=300, h=600, d=532, as_=942, fc=30, ends=2, Ma=100, live=30)
        self.assertTrue(out2['table_ok'])
        # a shallow span goes to the calculation
        thin = deflection_check({'L': 6000, 'b': 300, 'h': 250, 'd': 192, 'as': 942, 'fc': 30, 'ends': 0, 'Ma': 100, 'MaLeft': 0, 'MaRight': 0, 'live': 30})
        self.assertFalse(thin['table_ok'])
        for k in ('delta_immediate', 'delta_live', 'delta_long_term', 'limit_total', 'limit_live', 'Ie_ratio'):
            self.assertIn(k, thin)
        self.assertEqual(thin['limit_total'], 25)
        self.assertEqual(thin['limit_live'], 16.7)
        self.assertGreater(thin['ratio'], 0)

    def test_beam_blocking_after(self):
        check = {'blocking': ['B1', 'B2']}
        self.assertEqual(beam_blocking_after(None, None), [])
        self.assertEqual(beam_blocking_after(check, None), ['B1', 'B2'])
        self.assertEqual(beam_blocking_after(check, {'mode': 'deepen'}), ['B1', 'B2'])
        self.assertEqual(beam_blocking_after(check, {'mode': 'bypass'}), [])
        self.assertEqual(beam_blocking_after(check, {'mode': 'bypass', 'beams': [' b1 ']}), ['B2'])


class PunchingRulesTest(unittest.TestCase):
    def test_blocking_after(self):
        check = {'flagged': ['C1', 'C2', 'C3'], 'blocking': ['C1', 'C2', 'C2']}
        self.assertEqual(blocking_after(None, None), [])
        self.assertEqual(blocking_after(check, None), ['C1', 'C2'])
        self.assertEqual(blocking_after(check, {'mode': 'thicken'}), ['C1', 'C2'])
        self.assertEqual(blocking_after(check, {'mode': 'bypass'}), [])
        self.assertEqual(blocking_after(check, {'mode': 'bypass', 'columns': ['c1']}), ['C2'])

    def test_override_columns(self):
        check = {'flagged': ['C1', 'C2']}
        self.assertEqual(override_columns(check, None), set())
        self.assertEqual(override_columns(check, {'columns': 'all'}), {'C1', 'C2'})
        self.assertEqual(override_columns(check, {'columns': [' c2 ']}), {'C2'})


class QuantitiesTest(unittest.TestCase):
    def test_cost_study(self):
        q = {'levels': [{'id': 'L01', 'name': 'TYPICAL', 'steel': {'kg': 1000}, 'concrete': {'total_m3': 25, 'formwork_m2': 100, 'net_area_m2': 100},
                         'cables': {'kg': 200, 'live_ends': 10, 'dead_ends': 10, 'duct_small_m': 50, 'duct_large_m': 10.04}}],
             'totals': {'steel': {'kg': 1000}, 'concrete': {'total_m3': 25, 'formwork_m2': 100, 'net_area_m2': 100}, 'cables': None}}
        cs = cost_study(q, {'markup_pct': 10})
        self.assertEqual(cs['currency'], 'SAR')
        self.assertEqual(cs['rates']['markup_pct'], 10)
        lvl = cs['levels'][0]
        self.assertEqual([l['key'] for l in lvl['lines']], ['steel', 'rebar_labour', 'concrete', 'formwork', 'strand', 'anchor_live', 'anchor_dead', 'duct', 'pt_labour'])
        self.assertEqual(lvl['lines'][0]['amount'], 3200)
        self.assertEqual(lvl['lines'][7]['qty'], 60.0)
        direct = 3200 + 350 + 25 * 280 + 100 * 45 + 200 * 9.5 + 10 * 45 + 10 * 25 + 60 * 6 + 100 * 18
        self.assertEqual(lvl['direct'], direct)
        self.assertEqual(lvl['markup'], round(direct * 0.1))
        self.assertEqual(lvl['total'], lvl['direct'] + lvl['markup'] + lvl['vat'])
        self.assertEqual([l['key'] for l in cs['totals']['lines']], ['steel', 'rebar_labour', 'concrete', 'formwork'])


def _bar(id_, l1, dia, s, n, L, pl, dw, face='T', now=None):
    return {'id': id_, 'payload': {'l1': l1, 'l2': f'L={L}', 'dia': dia, 's': s, 'n': n, 'face': face, 'L': L, 'pl': pl, 'dw': dw, 'lv': 'L01'},
            'now': now if now is not None else {'pl': pl, 'l1': l1, 'l2': f'L={L}', 'dw': dw}}


class DxfBarsTest(unittest.TestCase):
    def test_parse_callout(self):
        self.assertEqual(parse_callout('7T16-150 (T)'), {'n': 7, 'dia': 16, 's': 150})
        self.assertEqual(parse_callout('T12-200 (B)'), {'n': 0, 'dia': 12, 's': 200})
        self.assertEqual(parse_callout('4T20'), {'n': 4, 'dia': 20, 's': 0})
        self.assertIsNone(parse_callout('no bars here'))
        self.assertIsNone(parse_callout(None))

    def test_takeoff(self):
        untouched = _bar('B1', 'T12-150 (T)', 12, 150, 0, 4000, 4000, 3000)
        stretched = _bar('B2', 'T12-150 (T)', 12, 150, 0, 4000, 4000, 3000, now={'pl': 5000, 'l1': 'T12-150 (T)', 'dw': 3000})
        heavier = _bar('B3', 'T12-150 (B)', 12, 150, 0, 4000, 4000, 3000, face='B', now={'pl': 4000, 'l1': 'T16-150 (B)', 'dw': 3000})
        # an untouched bar changes nothing
        u = takeoff_from_bars([untouched])
        self.assertEqual(u['changed'], 0)
        self.assertEqual(u['delta']['kg'], 0)
        self.assertEqual(u['bars'], 1)
        self.assertEqual(u['level'], 'L01')
        self.assertEqual(u['delta']['byDia'], [])
        fu = bar_figures(untouched)
        self.assertFalse(fu['changed'])
        self.assertEqual(fu['before']['count'], 21)  # 3000 / 150 + 1
        self.assertEqual(fu['before'], fu['after'])
        # a stretched polyline adds its metre to the cutting length; a call-out re-written T12 -> T16 raises the kg
        edited = takeoff_from_bars([untouched, stretched, heavier])
        self.assertEqual(edited['changed'], 2)
        self.assertEqual(edited['bars'], 3)
        fs = next(f for f in edited['list'] if f['id'] == 'B2')
        fh = next(f for f in edited['list'] if f['id'] == 'B3')
        self.assertEqual(fs['after']['L'], fs['before']['L'] + 1000)
        self.assertEqual(fs['after']['dia'], 12)
        self.assertEqual(fh['after']['dia'], 16)
        self.assertEqual(fh['after']['s'], 150)
        self.assertEqual(fh['after']['count'], fh['before']['count'])
        self.assertGreater(fh['after']['kg'], fh['before']['kg'])
        self.assertGreater(edited['delta']['kg'], 0)
        self.assertGreater(edited['delta']['top_kg'], 0)
        self.assertGreater(edited['delta']['bottom_kg'], 0)
        self.assertEqual(edited['delta']['other_kg'], 0)
        dias = [d['dia'] for d in edited['delta']['byDia']]
        self.assertEqual(dias, [12, 16])
        d16 = edited['delta']['byDia'][1]
        self.assertEqual(d16['count'], fh['after']['count'])
        self.assertEqual(d16['kg'], fh['after']['kg'])
        # applied to the run's take-off: the level's steel and the project totals move by the difference
        q = {'levels': [{'id': 'L01', 'steel': {'kg': 1000, 'top_kg': 600, 'bottom_kg': 400, 'other_kg': 0,
                                                 'byDia': [{'dia': 12, 'kg': 500, 'total_m': 560, 'count': 100}, {'dia': 16, 'kg': 500, 'total_m': 320, 'count': 50}]},
                         'concrete': {'net_area_m2': 100, 'total_m3': 25}}],
             'totals': {'steel': {'kg': 1000}, 'concrete': {'net_area_m2': 100}}}
        q0 = copy.deepcopy(q)
        q2 = apply_takeoff(q, 'L01', edited, {'file': 'top.dxf', 'by': 'Eng. Test', 'date': '2026-09-28'})
        self.assertEqual(q2['levels'][0]['steel']['kg'], round((1000 + edited['delta']['kg']) * 10) / 10)
        self.assertEqual(q2['totals']['steel']['kg'], q2['levels'][0]['steel']['kg'])
        self.assertEqual(q2['levels'][0]['edited'][0]['bars'], 2)
        self.assertEqual(q2['levels'][0]['edited'][0]['by'], 'Eng. Test')
        self.assertEqual(q2['edited'][0]['level'], 'L01')
        self.assertAlmostEqual(q2['levels'][0]['steel']['kg_per_m2'], q2['levels'][0]['steel']['kg'] / 100, places=2)
        self.assertEqual(q2['totals']['steel']['kg_per_m2'], q2['levels'][0]['steel']['kg_per_m2'])
        self.assertEqual([d['dia'] for d in q2['levels'][0]['steel']['byDia']], [12, 16])
        self.assertEqual(q2['levels'][0]['steel']['byDia'][1]['count'], 50 + d16['count'])
        self.assertEqual(q, q0, 'the original is left alone')
        self.assertEqual(q['levels'][0]['steel']['kg'], 1000)


if __name__ == '__main__':
    unittest.main()
