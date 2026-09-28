"""Foundation tests: geometry helpers, Canvas, DXF writer / reader round trip, SVG, Sheet.

Run from the repository root:   python3 -m unittest pydrawings/tests/test_foundation.py
or from `pydrawings/`:          python3 -m unittest tests/test_foundation.py
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]  # <repo>/pydrawings, the folder that holds the package
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))
if getattr(sys.modules.get('pydrawings'), '__file__', None) is None:
    # `python -m unittest pydrawings/tests/...` from the repo root imports the OUTER folder as a namespace package
    # named `pydrawings`; swap in the real package (pydrawings/pydrawings/__init__.py) under that name and keep the
    # loader's `pydrawings.tests` reachable as an attribute (unittest walks the dotted name after importing it)
    _ns_tests = sys.modules.get('pydrawings.tests')
    sys.modules.pop('pydrawings', None)
    import pydrawings  # noqa: E402
    if _ns_tests is not None:
        pydrawings.tests = _ns_tests

from pydrawings.geometry import js_round, fmt_num, to_fixed, js_hypot, bbox, point_in_polygon, dist_to_seg, ceil_to, unit, perp, add, mid, DrawingsError  # noqa: E402
from pydrawings.canvas import Canvas, DEFAULT_DIMSTYLE, STANDARD_LAYERS  # noqa: E402
from pydrawings.dxf_writer import to_dxf, encode_text, XDATA_APP, num  # noqa: E402
from pydrawings.dxf_reader import parse_dxf, strip_mtext, decode_text  # noqa: E402
from pydrawings.svg_writer import to_svg, wrap  # noqa: E402
from pydrawings.preview import drawing_to_canvas  # noqa: E402
from pydrawings.sheet import Sheet, layout_for, choose_scale, DEFAULT_FRAME, SHEET_SIZES, SCALES, DETAIL_SCALES  # noqa: E402

try:
    import ezdxf  # noqa: F401
    from ezdxf import recover
except ImportError:  # pragma: no cover
    recover = None


def P(x, y, **k):
    return {'x': x, 'y': y, **k}


def build_canvas():
    c = Canvas()
    line = c.line(0, 0, 1000, 500, layer='OUTLINE', xdata=[[1000, 'bar:B1 Ø12'], [1040, 3.75], [1070, 7]])
    pl = c.pline([P(0, 0), P(500, 0, bulge=0.5), P(500, 300)], layer='REBAR-BOT', width=35, closed=True, lw=35)
    t90 = c.text(100, 100, 'ROTATED 90', layer='TEXT', h=250, rot=90, align='L', valign='B')
    t180 = c.text(100, 100, 'ROTATED 180', layer='TEXT', h=250, rot=180, align='R', valign='T')
    t45 = c.text(100, 100, 'ROTATED 45', layer='TEXT', h=250, rot=45, align='C', valign='M')
    circ = c.circle(300, 300, 150.75, layer='COLUMN', color=1)
    hatch = c.hatch([[P(0, 0), P(100, 0), P(100, 100)], [P(10, 10), P(20, 10), P(20, 20)]], layer='HATCH', pattern='ANSI37', scale=30)
    c.mtext(10, 20, 'Line one\nline two', layer='NOTES', h=100, width=2000)
    dim = c.dimension(P(0, 0), P(1234.5, 0), P(0, -500), style='ST100', style_def={'txt': 250, 'asz': 150, 'tsz': 150, 'exo': 50, 'exe': 100, 'gap': 70, 'se2': True}, layer='DIM', xdata=[[1000, 'bar:B1'], [1040, 1234.5]])
    vdim = c.dimension(P(0, 0), P(0, 2000), P(-600, 0), text='L=<> mm')
    c.group('BAR-1', [pl, dim, vdim, None], 'bar 1')
    return c, {'line': line, 'pl': pl, 't90': t90, 't180': t180, 't45': t45, 'circ': circ, 'hatch': hatch, 'dim': dim, 'vdim': vdim}


class TestNumberHelpers(unittest.TestCase):
    def test_js_round(self):
        self.assertEqual(js_round(2.5), 3)
        self.assertEqual(js_round(-2.5), -2)
        self.assertEqual(js_round(-2.6), -3)
        self.assertEqual(js_round(0.49999), 0)

    def test_fmt_num(self):
        self.assertEqual(fmt_num(3.0), '3')
        self.assertEqual(fmt_num(2.5), '2.5')
        self.assertEqual(fmt_num(3), '3')
        self.assertEqual(fmt_num(-0.0), '0')
        self.assertEqual(fmt_num(1e-7), '1e-7')
        self.assertEqual(fmt_num(1.5e-5), '0.000015')
        self.assertEqual(fmt_num(1e16), '10000000000000000')
        self.assertEqual(fmt_num(0.1 + 0.2), '0.30000000000000004')

    def test_to_fixed_and_num(self):
        self.assertEqual(to_fixed(2.5, 0), '3')
        self.assertEqual(to_fixed(1234.5678, 3), '1234.568')
        self.assertEqual(to_fixed(0.0078125, 6), '0.007813')  # JS rounds the exact half away from zero
        self.assertEqual(num(100.0), '100')
        self.assertEqual(num(0.1234567), '0.123457')
        self.assertEqual(num(-0.0000001), '0')
        self.assertEqual(num(None), '0')
        self.assertEqual(num(20.0), '20')

    def test_js_hypot(self):
        self.assertEqual(js_hypot(3, 4), 5)
        self.assertEqual(js_hypot(800, 10), 800.0624975587846)  # the V8 value (Python's math.hypot ends in ...845)

    def test_geometry_helpers(self):
        self.assertEqual(ceil_to(1234.5, 10), 1240)
        self.assertEqual(ceil_to(1230.0000000001, 10), 1230)
        self.assertEqual(unit(P(0, 0), P(0, 5)), {'x': 0, 'y': 1})
        self.assertEqual(perp({'x': 1, 'y': 0}), {'x': -0, 'y': 1})
        self.assertEqual(add(P(1, 1), {'x': 1, 'y': 0}, 3), {'x': 4, 'y': 1})
        self.assertEqual(mid(P(0, 0), P(2, 4)), {'x': 1, 'y': 2})
        self.assertAlmostEqual(dist_to_seg(P(5, 5), P(0, 0), P(10, 0)), 5)
        self.assertAlmostEqual(dist_to_seg(P(5, 5), P(0, 0), P(0, 0)), js_hypot(5, 5))
        poly = [P(0, 0), P(10, 0), P(10, 10), P(0, 10)]
        self.assertTrue(point_in_polygon(P(5, 5), poly))
        self.assertFalse(point_in_polygon(P(15, 5), poly))
        b = bbox(poly)
        self.assertEqual((b['w'], b['h'], b['cx'], b['cy']), (10, 10, 5, 5))
        self.assertTrue(issubclass(DrawingsError, Exception))


class TestCanvas(unittest.TestCase):
    def test_reading_rule(self):
        c, e = build_canvas()
        # 90 is in [89.5, 269.5): turned by 180 with the anchor mirrored
        self.assertEqual((e['t90']['rot'], e['t90']['align'], e['t90']['valign']), (-90, 'R', 'T'))
        self.assertEqual((e['t180']['rot'], e['t180']['align'], e['t180']['valign']), (0, 'L', 'B'))
        self.assertEqual((e['t45']['rot'], e['t45']['align'], e['t45']['valign']), (45, 'C', 'M'))
        self.assertEqual(c.text(0, 0, 'x', rot=-90)['rot'], 270)
        self.assertEqual(c.text(0, 0, 3.0)['str'], '3')

    def test_entities_keep_js_keys(self):
        c, e = build_canvas()
        self.assertEqual(e['pl']['t'], 'pline')
        self.assertEqual(e['pl']['pts'][1]['bulge'], 0.5)
        self.assertEqual(e['pl']['width'], 35)
        self.assertTrue(e['pl']['closed'])
        self.assertEqual(e['line']['xdata'][0], [1000, 'bar:B1 Ø12'])
        self.assertEqual(e['hatch']['pattern'], 'ANSI37')
        self.assertEqual(e['circ']['color'], 1)
        wf = c.text(0, 0, 'w', width_factor=0.8, style='X')
        self.assertEqual(wf['widthFactor'], 0.8)
        self.assertIn('OUTLINE', c.layers)
        self.assertEqual(c.layers['OUTLINE'], STANDARD_LAYERS['OUTLINE'])

    def test_dimension(self):
        c, e = build_canvas()
        d = e['dim']
        self.assertEqual(d['t'], 'dimension')
        self.assertEqual(d['block'], '*D1')
        self.assertEqual(d['style'], 'ST100')
        self.assertEqual(d['measure'], 1234.5)
        self.assertEqual(d['text'], '<>')
        self.assertEqual(c.dim_styles['ST100']['txt'], 250)
        self.assertEqual(c.dim_styles['ST100']['clrt'], DEFAULT_DIMSTYLE['clrt'])
        blk = c.blocks['*D1']
        self.assertTrue(blk.anonymous)
        kinds = [x['t'] for x in blk.entities]
        # one extension line (se2 suppresses the second), the dimension line, two ticks and the text
        self.assertEqual(kinds, ['line', 'line', 'line', 'line', 'text'])
        self.assertEqual(blk.entities[-1]['str'], '1235')
        self.assertEqual(blk.entities[-1]['h'], 250)
        v = e['vdim']
        self.assertEqual(v['text'], 'L=<> mm')
        self.assertEqual(c.blocks['*D2'].entities[-1]['str'], 'L=2000 mm')
        self.assertEqual(c.blocks['*D2'].entities[-1]['rot'], 270)  # -90 (reads top to bottom), normalised by text()
        self.assertEqual(len(c.groups), 1)
        self.assertEqual(len(c.groups[0]['entities']), 3)  # the None is dropped


class TestDxfRoundTrip(unittest.TestCase):
    def setUp(self):
        self.canvas, self.ents = build_canvas()
        self.dxf = to_dxf(self.canvas)

    def test_sections_and_entities(self):
        d = self.dxf
        for s in ['HEADER', 'CLASSES', 'TABLES', 'BLOCKS', 'ENTITIES', 'OBJECTS']:
            self.assertIn(f'0\nSECTION\n2\n{s}\n', d)
        self.assertTrue(d.startswith('0\nSECTION\n2\nHEADER\n9\n$ACADVER\n1\nAC1015\n'))
        self.assertTrue(d.endswith('0\nEOF\n'))
        for t in ['LINE', 'LWPOLYLINE', 'TEXT', 'MTEXT', 'CIRCLE', 'HATCH', 'DIMENSION']:
            self.assertIn(f'\n0\n{t}\n', d)
        self.assertIn('1001\nSPANTECH\n1002\n{\n1000\nbar:B1 \\U+00D812\n1040\n3.75\n1070\n7\n1002\n}\n', d)
        self.assertIn('\n2\nACAD\n', d)
        self.assertIn(f'\n2\n{XDATA_APP}\n', d)
        self.assertIn('\n0\nDIMSTYLE\n105\n', d)
        self.assertIn('\n2\nST100\n', d)
        self.assertIn('\n0\nBLOCK_RECORD\n', d)
        self.assertIn('\n2\n*D1\n', d)
        self.assertIn('\n3\nACAD_GROUP\n', d)
        self.assertIn('\n0\nGROUP\n', d)
        self.assertIn('\n300\nbar 1\n', d)
        self.assertIn('\n0\nLAYOUT\n', d)
        self.assertIn('\n1\nLayout1\n', d)
        self.assertNotIn('$HANDSEED\n5\nFFFFFF', d)
        self.assertEqual(encode_text('Ø12 عربي'), '\\U+00D812 \\U+0639\\U+0631\\U+0628\\U+064A')
        self.assertIn('\n43\n35\n', d)  # the polyline constant width
        self.assertIn('\n42\n0.5\n', d)  # and its bulge

    def test_parse_back(self):
        p = parse_dxf(self.dxf)
        self.assertEqual(p['header']['$ACADVER'], 'AC1015')
        self.assertEqual(p['header']['$INSUNITS'], 4)
        types = [e['type'] for e in p['entities']]
        self.assertEqual(types.count('LINE'), 1)
        self.assertEqual(types.count('LWPOLYLINE'), 1)
        self.assertEqual(types.count('TEXT'), 3)
        self.assertEqual(types.count('CIRCLE'), 1)
        self.assertEqual(types.count('HATCH'), 1)
        self.assertEqual(types.count('MTEXT'), 1)
        self.assertEqual(types.count('DIMENSION'), 2)
        line = next(e for e in p['entities'] if e['type'] == 'LINE')
        self.assertEqual((line['x'], line['y'], line['x2'], line['y2']), (0, 0, 1000, 500))
        self.assertEqual(line['layer'], 'OUTLINE')
        self.assertEqual(line['xdata']['SPANTECH'], [[1000, 'bar:B1 \\U+00D812'], [1040, 3.75], [1070, 7]])  # XDATA strings stay raw, as in the JS reader
        pl = next(e for e in p['entities'] if e['type'] == 'LWPOLYLINE')
        self.assertTrue(pl['closed'])
        self.assertEqual(pl['pts'][1], {'x': 500, 'y': 0, 'bulge': 0.5})
        t = [e for e in p['entities'] if e['type'] == 'TEXT']
        self.assertEqual(t[0]['text'], 'ROTATED 90')
        self.assertEqual((t[0]['rotation'], t[0]['halign']), (-90, 2))
        self.assertEqual(t[0]['x'], 100)  # the alignment point (11/21) is the anchor
        h = next(e for e in p['entities'] if e['type'] == 'HATCH')
        self.assertEqual(h['pattern'], 'ANSI37')
        self.assertEqual(len(h['paths']), 2)
        d = next(e for e in p['entities'] if e['type'] == 'DIMENSION')
        self.assertEqual(d['measure'], 1234.5)
        self.assertEqual(d['dimstyle'], 'ST100')
        self.assertEqual(d['dimType'], 0)
        self.assertEqual((d['x3'], d['y3'], d['x4'], d['y4']), (0, 0, 1234.5, 0))
        self.assertNotIn('xdata', d)  # Canvas.dimension builds its record explicitly (no xdata carried), as in the JS
        m = next(e for e in p['entities'] if e['type'] == 'MTEXT')
        self.assertEqual(m['text'], 'Line one\nline two')
        self.assertIn('*D1', p['blocks'])
        self.assertEqual(p['blocks']['*D1']['entities'][-1]['type'], 'TEXT')
        self.assertEqual(p['blocks']['*D1']['entities'][-1]['text'], '1235')
        self.assertEqual(strip_mtext('{\\fArial|b1;Hello}\\PWorld %%c12 %%d'), 'Hello\nWorld Ø12 °')
        self.assertEqual(decode_text('\\U+0639x'), 'عx')

    def test_svg_and_preview(self):
        svg = to_svg(self.canvas, width=800)
        self.assertTrue(svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" width="800" height="'))
        self.assertIn('<circle ', svg)
        self.assertIn('ROTATED 90', svg)
        self.assertIn('url(#hp0)', svg)
        self.assertEqual(wrap('the quick brown fox jumps', 10), ['the quick', 'brown fox', 'jumps'])
        back = drawing_to_canvas(parse_dxf(self.dxf))
        self.assertEqual(len(back.entities), len(self.canvas.entities) - 2)  # the two DIMENSIONs are not previewed (as in the JS)
        self.assertIn('<svg', to_svg(back))

    @unittest.skipIf(recover is None, 'ezdxf not installed')
    def test_ezdxf_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'foundation.dxf')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(self.dxf)
            doc, auditor = recover.readfile(path)
        self.assertEqual(len(auditor.errors), 0, [str(e.message) for e in auditor.errors])
        self.assertEqual(doc.dxfversion, 'AC1015')
        self.assertEqual(len(doc.modelspace()), len(self.canvas.entities))
        self.assertIn('*D1', [b.name for b in doc.blocks])
        self.assertIn('ST100', [s.dxf.name for s in doc.dimstyles])


class TestSheet(unittest.TestCase):
    def test_layout_for(self):
        L = layout_for('A1')
        self.assertEqual((L['w'], L['h']), (841, 594))
        # no bottom strip by default (details: false): the plan takes the full height between the margins
        self.assertEqual(L['plan'], {'x': 20, 'y': 10, 'w': 831 - 185 - 20, 'h': 574})
        self.assertEqual(L['strip']['h'], 0)
        self.assertEqual(L['title'], {'x': 646, 'y': 10, 'w': 185, 'h': 150})
        self.assertEqual(L['keyplan']['y'], 584 - 46)
        Ld = layout_for('A1', {'details': True})
        self.assertEqual(Ld['strip']['h'], 125)
        self.assertEqual(Ld['plan']['y'], 135)
        self.assertEqual(len(Ld['details']), 3)
        self.assertEqual(layout_for('A0')['w'], SHEET_SIZES['A0']['w'])
        self.assertEqual(DEFAULT_FRAME['rightWidth'], 185)
        self.assertEqual(choose_scale({'w': 40000, 'h': 20000}, L['plan']), 75)
        self.assertEqual(SCALES[0], 50)
        self.assertIn(12.5, DETAIL_SCALES)

    def test_set_plan_pen_draws_into_block(self):
        root = Canvas()
        sh = Sheet(root, block_name='SHEET-01', size='A1', scale=100)
        sh.frame()
        n0 = len(sh.blk.entities)
        self.assertGreater(n0, 0)
        pen = sh.set_plan({'cx': 500, 'cy': 500, 'w': 1000, 'h': 1000})
        self.assertIs(sh.pl, pen)
        self.assertIs(pen.area, sh.L['plan'])
        e = pen.pline([P(0, 0), P(1000, 0), P(1000, 1000)], layer='OUTLINE', closed=True, lw=35)
        self.assertIs(sh.blk.entities[-1], e)
        self.assertEqual(root.blocks['SHEET-01'], sh.blk)
        self.assertEqual(len(root.entities), 0)  # nothing in model space until the sheet is inserted
        self.assertEqual(e['lw'], 35)
        self.assertTrue(e['closed'])
        # the plan is centred in the plan area (offset by +7 paper mm for the plan title)
        L = sh.L['plan']
        self.assertAlmostEqual(e['pts'][0]['x'], (L['x'] + L['w'] / 2) * 100 - 500)
        self.assertAlmostEqual(e['pts'][0]['y'], (L['y'] + L['h'] / 2 + 7) * 100 - 500)
        t = pen.text(P(0, 0), 'PLAN', layer='TEXT', h=3, rot=90)
        self.assertEqual(t['h'], 300)
        self.assertEqual((t['rot'], t['align'], t['valign']), (-90, 'R', 'T'))
        d = pen.dimension(P(0, 0), P(500, 0), P(0, 1200), style='ST100', style_def={'txt': 250})
        self.assertEqual(d['t'], 'dimension')
        self.assertEqual(pen.dim(P(0, 0), P(500, 0), -50), None)
        self.assertEqual(sh.blk.entities[-1]['str'], '500')
        root.insert('SHEET-01', 0, 0, layer='XREF')
        self.assertIn('\n2\nSHEET-01\n', to_dxf(root))

    def test_detail_box_off_and_table_skip(self):
        root = Canvas()
        sh = Sheet(root, block_name='S2', size='A2', scale=50, frame={'keyplan': False, 'refs': False})
        self.assertEqual(sh.L['keyplan']['h'], 0)
        box = sh.detail_box(0, 'DETAIL', '1:20')
        self.assertTrue(box['off'])
        n = len(sh.blk.entities)
        pen = sh.detail_pen(box, 20, {'minX': 0, 'maxX': 1, 'minY': 0, 'maxY': 1, 'cx': 0, 'cy': 0})
        pen.line(P(0, 0), P(1, 1), layer='DETAIL')
        self.assertEqual(len(sh.blk.entities), n)  # drawn into the scratch canvas
        self.assertIs(sh.blk, root.blocks['S2'])
        r = sh.table(sh.L['strip']['x'] + 1, sh.L['strip']['y'], [{'key': 'a', 'title': 'A', 'w': 20}], [{'a': 1}])
        self.assertEqual(r, {'y': sh.L['strip']['y'], 'leftover': []})
        self.assertEqual(len(sh.blk.entities), n)
        # a real table in the schedule box
        S = sh.L['schedule']
        r = sh.table(S['x'] + 2, S['y'] + S['h'] - 2, [{'key': 'a', 'title': 'A', 'w': 20, 'max': 3}], [{'a': 'abcdef'}, {'a': 2.0}], title='T', max_rows=1, totals='TOT')
        self.assertEqual(len(r['leftover']), 1)
        self.assertLess(r['y'], S['y'] + S['h'] - 2)
        texts = [e['str'] for e in sh.blk.entities if e['t'] == 'text']
        self.assertIn('ab…', texts)
        # with a strip the detail box is real and the pen falls back to the next standard scale when it overflows
        sh3 = Sheet(root, block_name='S3', frame={'details': True})
        box = sh3.detail_box(1, 'DETAIL B', '1:20')
        self.assertFalse(box.get('off'))
        pen = sh3.detail_pen(box, 20, {'minX': 0, 'maxX': 6000, 'minY': 0, 'maxY': 2000, 'cx': 3000, 'cy': 1000})
        self.assertEqual(box['label']['str'], '1:40')
        self.assertEqual(pen.k, 100 / 40)
        sh3.title_block({'project': 'P', 'title': 'T', 'drawingNo': 'ST-01'})
        sh3.refs_block({})
        sh3.key_plan([P(0, 0), P(100, 0), P(100, 50)])
        y = sh3.notes(general=['one'], code_ref='ACI 318-19', legend=[['REBAR-BOT', 'bottom', 'thick']])
        self.assertLess(y, sh3.L['notes']['y'] + sh3.L['notes']['h'])
        sh3.plan_title('PLAN', '1:100')
        sh3.stamp('FOR APPROVAL', 'sub')
        strs = [e['str'] for e in sh3.blk.entities if e['t'] == 'text']
        self.assertIn('SPAN TECH CONTRACTING', strs)
        self.assertIn('SHOP DRAWING - FOR CONSULTANT APPROVAL', strs)
        self.assertIn('ملاحظات عامة', strs)


if __name__ == '__main__':
    unittest.main()
