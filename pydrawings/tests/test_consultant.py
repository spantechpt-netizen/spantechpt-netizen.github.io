"""The consultant's bars kept as drawn (spec.designerBars), the column rule on the listed columns only, beams assigned to
the consultant's types (spec.beamAssign), the office rules switched off (spec.rules) and the project grid (spec.grid).
Ported from test/shopdrawings.test.js ("the consultant's bars kept as drawn ...")."""
import copy
import json
import math
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from pydrawings.cli import generate
from pydrawings.design import apply_column_rule
from pydrawings.dxf_bars import parse_callout
from pydrawings.punching import punching_check
from tests.synthetic_cpt import build_synthetic_cpt


class TestConsultantBars(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='cons-'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_consultant_bars_assigned_beams_rules_grid(self):
        cpt = build_synthetic_cpt(str(self.tmp), beam=True)
        spec = {
            'mesh': 'both',
            'grid': {'x': [{'label': '1', 'x': 0}, {'label': '2', 'x': 6000}, {'label': '3', 'x': 12000}], 'y': [{'label': 'A', 'y': 0}, {'label': 'B', 'y': 4000}, {'label': 'C', 'y': 8000}]},
            'topColumns': {'only': ['B/2']},
            'beams': {'topBars': False, 'source': 'QUANTUM DWG No. 4'},
            'rules': {'perimeter': False, 'corners': False, 'drops': False, 'voids': False},
            'consultant': {'name': 'Quantum Group', 'drawing': 'dwg 4', 'notes': ['Slab 260 per the consultant']},
            'beamTypes': [{'mark': 'K1', 'width': 300, 'depth': 600, 'top': {'n': 3, 'dia': 16}, 'bottom': {'n': 4, 'dia': 18}, 'stirrups': {'dia': 8, 'legs': 2, 'spacing': 150}}],
            'beamAssign': {'bm1': 'K1', 'BM2': 'k1'},
            'designerBars': [
                {'id': 'CT-B2', 'face': 'T', 'dia': 18, 'perMetre': 7, 'a': {'x': 4000, 'y': 4000}, 'b': {'x': 8000, 'y': 4000}, 'width': 2000, 'zone': 'COL B/2 X'},
                {'id': 'CB-1', 'face': 'B', 'dia': 12, 'count': 3, 'a': {'x': 2000, 'y': 2000}, 'b': {'x': 8000, 'y': 2000}, 'width': 3000, 'zone': 'MID-SPAN'},
                {'id': 'BT-1', 'face': 'T', 'dia': 16, 'count': 4, 'beam': 'BM1', 'a': {'x': 9000, 'y': 3000}, 'b': {'x': 9000, 'y': 5000}, 'zone': 'BEAM BM1 SUPPORT'},
            ],
        }
        out = self.tmp / 'out'
        r = generate(input_dxf=cpt, out=str(out), meta={}, spec=spec, svg=False, level_names=['GROUND'], mode='design')
        L = r['model']['levels'][0]
        # the project's grid: the columns carry its references, the model's own numbers kept beside them
        self.assertEqual(L['grid']['source'], 'config')
        self.assertEqual(sorted(c['id'] for c in L['columns']), ['A/1', 'A/3', 'B/2', 'C/1', 'C/3'])
        self.assertTrue(all(re.fullmatch(r'C\d+', c['ramId']) for c in L['columns']), 'the RAM column number is kept as ramId')
        self.assertTrue(any(re.search(r"Grid lines and references are the project's own \(1, 2, 3 / A, B, C", a['text']) for a in r['model']['assumptions']))
        # the consultant's bars as designer items: call-out, length, distribution, kept out of the office rules' way
        des = [it for it in L['existing']['items'] if it.get('designer')]
        self.assertEqual(len(des), 3)
        self.assertTrue(all(it.get('fixed') and it.get('noTag') for it in des))
        ct = next(it for it in des if it.get('id') == 'CT-B2')
        self.assertEqual([ct['l1'], ct['l2'], ct['face'], ct['dia'], ct['spacing'], ct['count']], ['7T18/m (T)', 'L=4000', 'T', 18, 143, 14])
        self.assertEqual(round(math.hypot(ct['dist']['p']['x'] - ct['dist']['q']['x'], ct['dist']['p']['y'] - ct['dist']['q']['y'])), 2000, 'distribution width as given')
        cb = next(it for it in des if it.get('id') == 'CB-1')
        self.assertEqual([cb['l1'], cb['l2'], cb['count'], cb['spacing']], ['3T12 (B)', 'L=6000', 3, 0])
        bt = next(it for it in des if it.get('id') == 'BT-1')
        self.assertTrue(bt.get('beam') == 'BM1' and bt.get('distAuto') and not bt.get('uEnd'), 'a beam support bar: no given distribution (the office one-bar dimension is drawn), no end legs')
        self.assertTrue(any(re.search(r"3 bars of the consultant's drawing \(Quantum Group, dwg 4\) are drawn", a['text']) for a in r['model']['assumptions']))
        self.assertEqual(L.get('designerBars'), 3)
        # the column rule: only B/2, and only across the consultant's bars (the x group is theirs); nothing on the beams
        lv = copy.deepcopy({**L, 'punchingCheck': None, 'beamSchedule': None, 'beamCheck': None})
        rule = apply_column_rule(lv, r['model']['spec'])
        self.assertTrue(rule['added'] and all(it.get('column') == 'B/2' and it.get('dir') == 'y' for it in rule['added']), json.dumps([[it.get('column'), it.get('dir')] for it in rule['added']]))
        self.assertEqual(ct['l2'], 'L=4000', "the consultant's bar is not re-lengthed")
        # the beams carry the consultant's types: no office design, no typing, the source named on the framing plan
        sch = L['beamSchedule']
        self.assertEqual([sch['assigned'], sch['unassigned'], sch['undesigned'], sch['source']], [['BM1', 'BM2'], [], [], 'QUANTUM DWG No. 4'])
        self.assertTrue(len(sch['types']) == 1 and sch['types'][0]['mark'] == 'K1' and sch['types'][0]['count'] == 2)
        self.assertEqual(len(L['beamCheck']['beams']), 0, 'assigned beams are not designed by the office')
        framing = Path(next(f for f in r['files'] if re.search(r'FRAMING.*\.dxf$', f))).read_text()
        self.assertTrue('QUANTUM DWG NO. 4' in framing and 'CARRY THE TYPES OF QUANTUM DWG NO. 4 AS ASSIGNED BY THE ENGINEER (K1)' in framing)
        # punching: the columns standing on the edge beam are the beam's, the interior one is checked
        pc = r['punching'][0]
        self.assertEqual(sorted([c['id'], c['beam']] for c in pc['columns'] if c['status'] == 'on beam'), [['A/1', 'BM2'], ['A/3', 'BM2']])
        self.assertTrue(next(c for c in pc['columns'] if c['id'] == 'B/2')['status'] == 'ok' and len(pc['blocking']) == 0)
        reported = punching_check(L, {**r['model']['spec'], 'punching': {'ramFailed': ['a/1']}})
        self.assertTrue(next(c for c in reported['columns'] if c['id'] == 'A/1')['ram_failed'] and 'A/1' in reported['blocking'], "the engineer's report of a RAM failure wins over the beam")
        # the rules switched off and the consultant's notes on the sheets
        top = Path(next(f for f in r['files'] if re.search(r'TOP_REINFORCEMENT.*\.dxf$', f))).read_text()
        self.assertTrue('\n1\n7T18/m (T)\n' in top and '\n1\n4T16 (T)\n' in top, "the consultant's call-outs as given")
        self.assertNotIn('\n1\nT12-150 U-BAR\n', top, 'perimeter rule off: no U-bar drawn')
        self.assertIn('SLAB 260 PER THE CONSULTANT', top, "the consultant's note on the sheet")
        self.assertIn("GENERAL DETAILS + CONSULTANT'S BARS (TOP)", top)
        bot = Path(next(f for f in r['files'] if re.search(r'BOTTOM_REINFORCEMENT.*\.dxf$', f))).read_text()
        self.assertTrue('\n1\n3T12 (B)\n' in bot and 'LAP 500' not in bot, "the consultant's bottom bars; no drop detail (rule off)")
        self.assertIn("the consultant's bars as drawn", (out / 'REPORT.md').read_text())
        # the per-metre call-out form reads as a run
        self.assertEqual(parse_callout('7T18/m'), {'n': 0, 'dia': 18, 's': 143})
        self.assertEqual(parse_callout('3T12-150'), {'n': 3, 'dia': 12, 's': 150})


if __name__ == '__main__':
    unittest.main()


class TestScopeBands(unittest.TestCase):
    """The office's scope limited to the PT band beams (spec.scope 'bands'): RC slab tag, no mesh, no slab rules, beams by
    others, columns outside the bands not checked. Ported from test/shopdrawings.test.js."""

    def test_scope_bands(self):
        tmp = Path(tempfile.mkdtemp(prefix='scope-'))
        try:
            cpt = build_synthetic_cpt(str(tmp), beam=True)
            r = generate(input_dxf=cpt, out=str(tmp / 'out'), meta={}, spec={'scope': 'bands', 'consultant': {'name': 'Quantum Group', 'drawing': 'dwg 4'}}, svg=False, level_names=['GROUND'], mode='design')
            L = r['model']['levels'][0]
            self.assertEqual([L.get('scope'), L.get('meshFaces'), L.get('meshSpec'), L.get('meshLabels')], ['bands', 'none', None, []])
            self.assertIsNone(r['quantities']['levels'][0].get('mesh'), 'no mesh in the take-off')
            spec = r['model']['spec']
            self.assertEqual([spec['topColumns'].get('only'), spec['beams'].get('topBars'), spec['rules'].get('perimeter')], ['bands', False, False])
            sch = L['beamSchedule']
            self.assertEqual([sch['byOthers'], sch['undesigned'], len(sch['types'])], [['BM1', 'BM2'], [], 0])
            self.assertEqual(len(L['beamCheck']['beams']), 0)
            framing = Path(next(f for f in r['files'] if re.search(r'FRAMING.*\.dxf$', f))).read_text()
            self.assertTrue('RC BEAM 300x600 (BY OTHERS)' in framing and '\n1\nRC SLAB\n' in framing and 'POST TENSION SLAB' not in framing, 'RC slab tag, beams by others')
            pc = r['punching'][0]
            self.assertTrue(all(c['status'] in ('on beam', 'out of scope') for c in pc['columns']) and not pc['blocking'], json.dumps([[c['id'], c['status']] for c in pc['columns']]))
            top = Path(next(f for f in r['files'] if re.search(r'TOP_REINFORCEMENT.*\.dxf$', f))).read_text()
            self.assertTrue('U-BAR\n' not in top and 'MESH T' not in top and 'SCOPE OF THESE DRAWINGS: THE POST-TENSIONED BAND BEAMS ONLY' in top and 'PT BAND BEAMS - TOP REINFORCEMENT PLAN' in top)
            self.assertIn("NO SLAB MESH ON THIS SHEET: THE SLAB REINFORCEMENT IS THE CONSULTANT'S (BY OTHERS).", top)
            bot = Path(next(f for f in r['files'] if re.search(r'BOTTOM_REINFORCEMENT.*\.dxf$', f))).read_text()
            self.assertTrue('LAP 500' not in bot and 'BOTTOM MESH T' not in bot, 'no drop detail, no mesh indication')
            self.assertTrue(any(re.search(r'scope in GROUND is the post-tensioned band beams only', a['text']) for a in r['model']['assumptions']))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
