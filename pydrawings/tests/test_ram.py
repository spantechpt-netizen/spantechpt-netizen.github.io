"""The RAM Concept reader and the beam strips on the synthetic model (the same facts test/shopdrawings.test.js checks)."""
import os
import re
import shutil
import sqlite3
import tempfile
import unittest

from pydrawings.ram_concept import read_ram_concept, ram_to_model, clip_tendon, mode_angle, tendon_height_at, tendon_extremes
from pydrawings.beam_strips import beam_spans, write_beam_strips, beam_schedule, type_covers, size50
from .synthetic_cpt import build_synthetic_cpt


def bbox_of(pts):
    xs, ys = [p['x'] for p in pts], [p['y'] for p in pts]
    return {'w': max(xs) - min(xs), 'h': max(ys) - min(ys)}


class RamConceptTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='ram-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_read_ram_concept(self):
        """a RAM Concept file is read into a level with its bands, tendons and walls clipped to the slab"""
        ram = read_ram_concept(build_synthetic_cpt(self.dir))
        self.assertEqual(ram['project']['name'], 'SYNTHETIC SLAB')
        self.assertEqual(ram['materials']['fc'], 32)
        self.assertEqual(ram['materials']['fy'], 420)
        self.assertEqual(ram['materials']['coverTop'], 35)
        self.assertEqual(ram['slab']['baseThickness'], 250)
        self.assertEqual(len(ram['slab']['outline']), 4, 'mesh boundary chained into the slab outline')
        self.assertEqual(len(ram['columns']), 5)
        self.assertEqual(ram['columns'][4]['shape'], 'circle')
        self.assertEqual(ram['columns'][4]['d'], 600)
        # the second column is turned 90°: B and D swapped, angle 0
        self.assertEqual((ram['columns'][1]['w'], ram['columns'][1]['h'], ram['columns'][1]['angle']), (800, 400, 0))
        self.assertEqual(len(ram['tendons']), 2, 'tendon segments chained node to node')
        lat = next(t for t in ram['tendons'] if t['spanSet'] == 'latitude')
        self.assertEqual(lat['strands'], 4)
        self.assertEqual(lat['length'], 12000)
        self.assertEqual(lat['live'], [True, False])
        self.assertEqual(lat['jackStress'], 1488)
        self.assertEqual(lat['jackForce'], round((1488 * 98.7 * 4) / 1000))
        self.assertEqual(lat['heights'], [125, 210, 125])
        self.assertEqual(lat['id'], 'TA-01')
        self.assertEqual(lat['elongations'], [85, None])
        self.assertEqual(len(ram['bands']), 2)
        bottom = next(b for b in ram['bands'] if b['face'] == 'B')
        self.assertEqual(bottom['dia'], 12)
        self.assertEqual(bottom['count'], 5)
        self.assertEqual(bottom['spacing'], 200)
        self.assertTrue(bottom['matched'], 'individual bars were matched to the band')
        self.assertEqual(len(bottom['bars']), 5)
        self.assertEqual(bottom['length'], 12000)
        top = next(b for b in ram['bands'] if b['face'] == 'T')
        self.assertEqual(top['dia'], 16)
        self.assertEqual(len(top['bars']), 6, 'bars synthesised from the band width when RAM stores no individual bars')
        self.assertEqual(ram['shear'][0]['spacing'], 150)
        self.assertEqual(len(ram['walls']), 1)
        self.assertEqual(len(ram['punching']), 1)
        self.assertEqual(ram['punching'][0]['tribArea'], 24)
        self.assertEqual(len(ram['ssr']), 1)
        self.assertEqual(len(ram['ssr'][0]['rails']), 16)
        self.assertEqual(ram['ssr'][0]['rails'][0]['count'], 10)
        self.assertEqual(ram['ssr'][0]['studDia'], 10)
        self.assertEqual(ram['slab']['tocs'], [0])
        self.assertEqual(len(ram['slab']['bodies']), 1)
        self.assertEqual(ram['beams'], [])
        self.assertEqual(ram['areaLoads'], [])
        self.assertEqual(ram['pt']['strandArea'], 98.7)
        self.assertAlmostEqual(ram['pt']['fpu'], 1860)

    def test_ram_to_model(self):
        ram = read_ram_concept(build_synthetic_cpt(self.dir))
        model = ram_to_model(ram, level_name='TEST')
        self.assertEqual(len(model['levels']), 1)
        level = model['levels'][0]
        self.assertEqual(level['id'], 'L01')
        self.assertEqual(level['name'], 'TEST')
        self.assertEqual(level['thickness'], 250, 'dominant thickness by mesh element area')
        self.assertEqual(len(level['outline']), 4)
        self.assertEqual(len(level['thickZones']), 1)
        self.assertEqual(level['thickZones'][0]['thickness'], 400)
        self.assertEqual(len(level['walls']), 1)
        self.assertTrue(level['walls'][0]['a']['x'] >= -1 and level['walls'][0]['b']['x'] <= 5001, 'wall clipped to the slab outline')
        self.assertEqual(len(level['columns']), 5)
        self.assertEqual(len(level['grid']['x']), 3)
        self.assertEqual(len(level['grid']['y']), 3)
        self.assertEqual([g['label'] for g in level['grid']['x']], ['A', 'B', 'C'])
        self.assertTrue(any(c['id'] == 'B/2' for c in level['columns']), 'column ids from the derived grid')
        self.assertEqual(len(level['ram']['bands']), 2)
        self.assertEqual(len(level['ram']['tendons']), 2)
        self.assertEqual(len(level['ram']['punching']), 1)
        self.assertEqual(len(level['ram']['ssr']), 1)
        self.assertEqual(level['sheetTurn'], 0)
        self.assertEqual(level['rotation'], 0)
        self.assertIsNone(level['tos'])
        self.assertEqual(level['toc'], 0)
        self.assertEqual(level['pt']['zones'][0]['polygon'], level['outline'])
        self.assertTrue(any(re.search(r'RAM Concept', a['text']) for a in model['assumptions']))
        self.assertTrue(any(re.search(r'Grid lines are not modelled', a['text']) for a in model['assumptions']))
        self.assertTrue(any(re.search(r'stud rails at 1 columns', a['text']) for a in model['assumptions']))
        self.assertEqual(model['findings'], ['L01 TEST: 96 m², 5 columns, 1 wall segments, 1 thickened zones, 0 pour strips, 2 designed bar bands, 2 tendons, 0 openings.'])
        self.assertEqual(model['spec']['fc'], 32)
        self.assertEqual(model['spec']['cover'], 35)
        self.assertEqual(model['spec']['found'], ['RAM bar type T12 (113 mm²)', 'RAM bar type T16 (201 mm²)'])
        self.assertTrue(model['source']['ram'])
        # a custom level id goes into the level id
        m2 = ram_to_model(ram, level_name='BASEMENT', level_id='B1')
        self.assertEqual((m2['levels'][0]['id'], m2['levels'][0]['customId']), ('B1', True))

    def test_step_bodies_and_rotate(self):
        """office rule: a slab at another top-of-concrete level is a separate slab; the plan is turned 90° on the sheet when it stands taller than wide (auto), or as forced"""
        ram = read_ram_concept(build_synthetic_cpt(self.dir, step=True))
        self.assertEqual(ram['slab']['tocs'], [0, -300])
        self.assertEqual(len(ram['slab']['bodies']), 2)
        tall = next(b for b in ram['slab']['bodies'] if bbox_of(b['polygon'])['h'] > bbox_of(b['polygon'])['w'] * 1.05)
        i = ram['slab']['bodies'].index(tall)
        auto = ram_to_model(ram, level_name='TURN', spec={})
        forced0 = ram_to_model(ram, level_name='TURN', spec={'rotate': '0'})
        forced90 = ram_to_model(ram, level_name='TURN', spec={'rotate': 90})
        self.assertEqual(len(auto['levels']), 2, 'two slabs')
        self.assertEqual(auto['levels'][i]['sheetTurn'], 90)
        self.assertEqual(auto['levels'][i]['rotation'], 90)
        self.assertTrue(auto['levels'][i]['bbox']['w'] > auto['levels'][i]['bbox']['h'], 'turned: the long side now lies along the sheet')
        self.assertTrue(any(re.search(r'turned 90° on the sheet', a['text']) for a in auto['assumptions']))
        self.assertEqual(forced0['levels'][i]['sheetTurn'], 0)
        self.assertTrue(forced0['levels'][i]['bbox']['h'] > forced0['levels'][i]['bbox']['w'])
        self.assertTrue(all(l['sheetTurn'] == 90 for l in forced90['levels']), 'forced: every body turned')
        # no sheet turn: the site coordinates are read
        upper, lower = forced0['levels']
        self.assertEqual(round(lower['bbox']['minX']), 8000)
        self.assertEqual(round(upper['bbox']['maxX']), 8000)
        self.assertEqual(lower['toc'], -300)
        self.assertEqual(lower['tos'], -300)
        self.assertEqual((upper['id'], lower['id']), ('L01', 'L02'))
        self.assertEqual(upper['name'], 'TURN - BODY 1')
        # the latitude tendon crossing into the lower body is cut at the step on both bodies
        self.assertTrue(all(t['cut'] == [False, True] for t in upper['ram']['tendons'] if t['spanSet'] == 'latitude'))
        self.assertTrue(all(t['cut'] == [True, False] and t['live'] == [False, False] for t in lower['ram']['tendons']))

    def test_helpers(self):
        self.assertEqual(mode_angle([]), 0)
        self.assertEqual(mode_angle([0, 0, 90]), 0)
        self.assertEqual(mode_angle([91, 89, 0]), 90)
        t = {'pts': [{'x': 0, 'y': 0}, {'x': 6000, 'y': 0}, {'x': 12000, 'y': 0}], 'heights': [125, 210, 125], 'thks': [250, 250, 250], 'live': [True, False], 'elongations': [85, None], 'length': 12000, 'inflection': 0.2}
        self.assertEqual(tendon_height_at(t, 0), 125)
        self.assertEqual(tendon_height_at(t, 6000), 210)
        self.assertEqual([e['kind'] for e in tendon_extremes(t)], ['L', 'H', 'L'])
        poly = [{'x': 0, 'y': -1000}, {'x': 8000, 'y': -1000}, {'x': 8000, 'y': 1000}, {'x': 0, 'y': 1000}]
        c = clip_tendon(t, poly, 0)
        self.assertEqual(c['cut'], [False, True])
        self.assertEqual(c['live'], [True, False])
        self.assertEqual(c['fullLength'], 12000)
        self.assertEqual(len(c['pts']), len(c['heights']))
        self.assertEqual(c['heights'][:2], [125, 210])
        self.assertIs(clip_tendon(t, [{'x': 20000, 'y': 0}, {'x': 21000, 'y': 0}, {'x': 21000, 'y': 1000}], 0), None)
        self.assertIs(clip_tendon(t, [{'x': -1, 'y': -1}, {'x': 13000, 'y': -1}, {'x': 13000, 'y': 1}, {'x': -1, 'y': 1}], 0), t)


class BeamStripsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='spantech-beams-')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_size50(self):
        """beam sizes are written to the nearest 50 mm with no decimals (350x600)"""
        self.assertEqual(size50(350.00000000000073), 350)
        self.assertEqual(size50(337), 350)
        self.assertEqual(size50(612.4), 600)
        self.assertEqual(f'{size50(349.999)}x{size50(600.0001)}', '350x600')
        self.assertEqual(size50(None), 0)

    def test_beam_strips(self):
        """beam design through RAM: one strip per beam span with a splitter on each edge written into the .cpt, and the designed beams read back into types"""
        src = build_synthetic_cpt(self.dir, beam=True)
        ram = read_ram_concept(src)
        self.assertEqual(len(ram['beams']), 2)
        self.assertEqual([(b['id'], b['t'], b['depth']) for b in ram['beams']], [('BM1', 300, 600), ('BM2', 300, 600)])
        # the edge beam along y = 150 runs from the column at (0, 0) to the one at (12000, 0): one span, both ends supported
        edge = beam_spans(next(b for b in ram['beams'] if b['id'] == 'BM2'), ram['columns'], ram['walls'])
        self.assertEqual(edge['spanSet'], 'latitude')
        self.assertEqual(len(edge['spans']), 1)
        self.assertTrue(edge['spans'][0]['support0'] and edge['spans'][0]['support0']['kind'] == 'column' and edge['spans'][0]['support1'] and edge['spans'][0]['support1']['kind'] == 'column')
        out = os.path.join(self.dir, 'beam-strips.cpt')
        sm = write_beam_strips(src, out, ram)
        self.assertEqual([sm['beams'], sm['spans'], sm['splitters']], [2, 2, 4])
        self.assertEqual(sm['removed']['SpanSegment'], 2, 'the old slab strips are gone')
        self.assertEqual(sm['removed']['SpanDesign'], 1, 'stale strip results are gone')
        db = sqlite3.connect(f'file:{out}?mode=ro', uri=True)
        db.row_factory = sqlite3.Row
        segs = [dict(r) for r in db.execute('select * from SpanSegment order by SpanSet, ChildIndex').fetchall()]
        self.assertEqual(len(segs), 2)
        self.assertTrue(all(r['ColumnStripDesignSystem'] == 'beam' and r['MiddleStripDesignSystem'] == 'beam' and r['ColumnStripWidthCalc'] == 'full' for r in segs), 'designed as beams')
        lat = next(r for r in segs if r['SpanSet'] == 'latitude')
        self.assertEqual([lat['Point0'], lat['Point1'], lat['Name'], lat['FrameNumber'], lat['SpanNumber'], lat['AtSupport0'], lat['AtSupport1'], lat['SupportWidth0'], lat['SupportWidth1']], ['[0][1500]', '[120000][1500]', '1-1', 0, 0, 1, 1, 4000, 8000], 'the strip on the beam centre line, in 0.1 mm, with the column sizes at its ends')
        self.assertEqual(lat['ParentUID'], db.execute("select UID from SpanSegmentCategory where SpanSet = 'latitude'").fetchone()['UID'], 'in the latitude category')
        self.assertTrue(lat['UID'] > 931 and all(r['PreviousSibUID'] == 0 and r['NextSibUID'] == 0 and r['ChildIndex'] == 0 for r in segs), 'fresh UIDs, one child per category chained')
        bounds = [dict(r) for r in db.execute("select Boundary, SpanSet from StripBoundary where SpanSet = 'longitude' order by ChildIndex").fetchall()]
        self.assertEqual([b['Boundary'] for b in bounds], ['[[88500][0]][[88500][80000]]', '[[91500][0]][[91500][80000]]'], 'a splitter on each edge of the 300 wide beam at x = 9 m')
        chain = [dict(r) for r in db.execute("select UID, PreviousSibUID, NextSibUID, ChildIndex, Number from StripBoundary where SpanSet = 'longitude' order by ChildIndex").fetchall()]
        self.assertTrue(chain[0]['PreviousSibUID'] == 0 and chain[0]['NextSibUID'] == chain[1]['UID'] and chain[1]['PreviousSibUID'] == chain[0]['UID'] and chain[1]['NextSibUID'] == 0 and chain[1]['Number'] == 1, 'sibling chain')
        strips = [dict(r) for r in db.execute('select Name, StripType, SpanSegment from SpanSegmentStrip').fetchall()]
        self.assertEqual(len(strips), 2)
        self.assertTrue(any(r['Name'] == '1C-1' and r['SpanSegment'] == lat['UID'] for r in strips))
        db.close()
        # the schedule off the (already calculated) synthetic model: the interior beam carries RAM's 4T16 top / 3T16 bottom / T12 @ 125 links
        sch = beam_schedule(ram)
        self.assertEqual(len(sch['types']), 1)
        t = sch['types'][0]
        self.assertEqual([t['mark'], t['section'], t['top']['text'], t['bottom']['text'], t['stirrups']['text'], t['count'], t['beams']], ['B1', '300x600', '4T16', '3T16', 'T12-2L@125', 1, ['BM1']])
        self.assertEqual(sch['undesigned'], ['BM2'], 'the edge beam has no RAM bars in it')
        self.assertEqual([x['mark'] for x in sch['added']], ['B1'], 'without a project schedule the type is new')
        # the project's unified schedule: a type on record that carries the beam is used as it is (the lightest one that does),
        # a heavier or different-section record leaves the beam to a new type numbered after the last mark; records never change

        def rec(mark, top, bottom, spacing=125, width=300, depth=600):
            return {'mark': mark, 'width': width, 'depth': depth, 'top': {'n': top, 'dia': 16}, 'bottom': {'n': bottom, 'dia': 16}, 'stirrups': {'dia': 12, 'legs': 2, 'spacing': spacing}}
        with_lib = beam_schedule(ram, None, library=[rec('B1', 6, 4, 100), rec('B2', 4, 3), rec('B3', 4, 3, 125, 400, 700)])
        self.assertEqual([[x['mark'], x['count'], bool(x.get('existing'))] for x in with_lib['types']], [['B2', 1, True]], 'the lightest record that carries the beam (B2, not the heavier B1)')
        self.assertEqual(with_lib['added'], [], 'no new type')
        self.assertEqual(next(b for b in with_lib['beams'] if b['id'] == 'BM1')['mark'], 'B2')
        too_light = beam_schedule(ram, None, library=[rec('B1', 3, 3), rec('B7', 4, 3, 125, 400, 700)])
        self.assertEqual([[x['mark'], bool(x.get('isNew'))] for x in too_light['types']], [['B8', True]], 'no record carries 4T16 top: a new type after the last mark, B1 untouched')
        self.assertEqual([[x['mark'], x['top']['text']] for x in too_light['added']], [['B8', '4T16']])
        self.assertTrue(type_covers(rec('X', 4, 3, 125), {'width': 300, 'depth': 600, 'top': {'n': 4, 'dia': 16}, 'bottom': {'n': 3, 'dia': 16}, 'stirrups': {'dia': 12, 'legs': 2, 'spacing': 150}})
                        and not type_covers(rec('X', 4, 3, 150), {'width': 300, 'depth': 600, 'top': {'n': 4, 'dia': 16}, 'bottom': {'n': 3, 'dia': 16}, 'stirrups': {'dia': 12, 'legs': 2, 'spacing': 125}}), 'stirrup capacity counts')
        # the office design beside RAM's: 'office' takes it, 'max' the heavier set by set
        office = {'beams': [{'id': 'bm1', 'top': {'n': 5, 'dia': 16, 'area': 1005, 'text': '5T16'}, 'bottom': {'n': 2, 'dia': 16, 'area': 402, 'text': '2T16'}, 'stirrups': {'dia': 10, 'legs': 2, 'spacing': 200, 'text': 'T10-2L@200'}}], 'failing': [], 'blocking': [], 'warnings': [], 'assumed': []}
        mx = beam_schedule(ram, None, design='max', office=office)
        bm1 = next(b for b in mx['beams'] if b['id'] == 'BM1')
        self.assertEqual((bm1['top']['text'], bm1['bottom']['text'], bm1['stirrups']['text'], bm1['design']), ('5T16', '3T16', 'T12-2L@125', 'max'))
        off = beam_schedule(ram, None, design='office', office=office)
        self.assertEqual(next(b for b in off['beams'] if b['id'] == 'BM1')['top']['text'], '5T16')
        self.assertEqual(off['office']['failing'], [])
        # the beams of the level model: the beam strips also work off ram_to_model's level
        model = ram_to_model(ram, level_name='BEAM TEST', spec={'rotate': '0'})
        self.assertEqual(len(model['levels'][0]['beams']), 2)
        self.assertIsNotNone(beam_schedule(ram, model['levels'][0]))

    def test_deeper_beam_is_a_support(self):
        """a beam crossing a deeper beam is carried by it: the span breaks there, like at a column or a wall"""
        shallow = {'id': 'BM1', 'a': {'x': 0, 'y': 5000}, 'b': {'x': 12000, 'y': 5000}, 't': 300, 'depth': 500}
        deep = {'id': 'BM2', 'a': {'x': 6000, 'y': 0}, 'b': {'x': 6000, 'y': 10000}, 't': 400, 'depth': 800}
        same = {'id': 'BM3', 'a': {'x': 9000, 'y': 0}, 'b': {'x': 9000, 'y': 10000}, 't': 300, 'depth': 500}
        sp = beam_spans(shallow, [], [], [shallow, deep, same])
        self.assertEqual(len(sp['spans']), 2, 'two spans either side of the deeper beam; the equal beam is no support')
        self.assertEqual(len(sp['supports']), 1)
        self.assertEqual(sp['supports'][0]['kind'], 'beam')
        self.assertEqual(round(sp['supports'][0]['t']), 6000)
        self.assertEqual(round(sp['supports'][0]['along']), 400, 'the support is as wide as the deeper beam')
        back = beam_spans(deep, [], [], [shallow, deep])
        self.assertEqual(len(back['spans']), 1, 'the deeper beam is not carried by the shallow one')
        # a wall crossing the axis is a support; a wall along it is not
        sp2 = beam_spans(shallow, [], [{'a': {'x': 4000, 'y': 0}, 'b': {'x': 4000, 'y': 10000}, 't': 200}, {'a': {'x': 0, 'y': 5000}, 'b': {'x': 12000, 'y': 5000}, 't': 200}])
        self.assertEqual([s['kind'] for s in sp2['supports']], ['wall'])
        self.assertEqual(len(sp2['spans']), 2)

    def test_loads_file(self):
        ram = read_ram_concept(build_synthetic_cpt(self.dir, loads={'dead': 2, 'live': 3}))
        self.assertEqual([(l['type'], l['q']) for l in ram['areaLoads']], [('dead', 2), ('live', 3)])
        self.assertTrue(os.path.basename(build_synthetic_cpt(self.dir, beam=True, loads={'dead': 3, 'live': 4})) == 'synthetic-beam-loads3-4.cpt')


if __name__ == '__main__':
    unittest.main()
