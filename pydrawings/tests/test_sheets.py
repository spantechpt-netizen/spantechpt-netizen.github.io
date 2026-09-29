"""
End-to-end tests of `pydrawings.sheets.compose_package` (the shop drawing package) against the Node reference output.

Two packages are built the way `shopdrawings/cli.mjs generate()` builds them:
  - the bundled sample structural drawing (`shopdrawings/samples/sample-structural-input.dxf`) through `parse_dxf` +
    `extract_model`;
  - the synthetic RAM Concept model (`tests/synthetic_cpt.py`) through `read_ram_concept` + `ram_to_model` with the
    beam / punching checks the CLI attaches to every level.
Every sheet is written with `to_dxf`, audited with ezdxf (0 errors) and compared with the Node DXF of the same sheet:
the multiset of TEXT strings and the number of entities per type (the sheet block walked with its inserted blocks,
the anonymous dimension pictures left out) must be identical.

The Node packages are read from `PYDRAWINGS_PARITY_DIR` (default: the session scratchpad `parity` folder, with
`node-sample-shop/dxf` and `node-plain-shop/dxf`); the parity checks are skipped when that folder is missing.
"""
import collections
import json
import os
import re
import shutil
import tempfile
import unittest

from pydrawings.dxf_reader import parse_dxf
from pydrawings.dxf_writer import to_dxf
from pydrawings.extract import extract_model
from pydrawings.sheets import compose_package, SHEET_DEFS, SCHEDULE_COLS, build_sheet, content_bbox, tendon_crossings, cable_stations, thickness_fn
from pydrawings.ram_concept import read_ram_concept, ram_to_model
from pydrawings.beam_strips import beam_schedule
from pydrawings.beam_design import design_beams
from pydrawings.punching import punching_check
from .synthetic_cpt import build_synthetic_cpt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SAMPLE_DXF = os.path.join(REPO, 'shopdrawings', 'samples', 'sample-structural-input.dxf')
LAYERS = os.path.join(REPO, 'pydrawings', 'pydrawings', 'layers.spantech.json')
PARITY = os.environ.get('PYDRAWINGS_PARITY_DIR') or '/tmp/claude-0/-home-user-spantechpt-netizen-github-io/ace90775-dd61-5b8d-b296-811049650024/scratchpad/parity'
NODE_SAMPLE = os.path.join(PARITY, 'node-sample-shop', 'dxf')
NODE_PLAIN = os.path.join(PARITY, 'node-plain-shop', 'dxf')


def sheet_stats(path):
    """Entity counts per type and the multiset of TEXT / MTEXT strings of a sheet DXF (the sheet block and the blocks it inserts)."""
    with open(path, encoding='utf-8') as fh:
        dxf = parse_dxf(fh.read())
    counts, texts = collections.Counter(), collections.Counter()

    def walk(ents):
        for e in ents:
            counts[e['type']] += 1
            if e['type'] in ('TEXT', 'MTEXT'):
                texts[(e.get('text') or '').strip()] += 1
            if e['type'] == 'INSERT' and not e['name'].startswith('*') and e['name'] in dxf['blocks']:
                walk(dxf['blocks'][e['name']]['entities'])
    walk(dxf['entities'])
    return counts, texts


def audit_errors(path):
    try:
        from ezdxf import recover
    except ImportError:  # pragma: no cover - the audit needs ezdxf
        return None
    doc, aud = recover.readfile(path)
    return len(aud.errors)


def write_package(pack, out):
    os.makedirs(os.path.join(out, 'dxf'), exist_ok=True)
    files = []
    for s in pack['sheets']:
        base = f"{s['drawingNo']}_{s['blockName']}"
        p = os.path.join(out, 'dxf', base + '.dxf')
        with open(p, 'w', encoding='utf-8') as fh:
            fh.write(to_dxf(s['root'], {'ltscale': s['scale'] / 4}))
        files.append(p)
    return files


class SheetsBase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='sheets-')
        with open(LAYERS) as fh:
            self.std = json.load(fh)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def assert_parity(self, node_dir, out, tolerate=None):
        """Same file names, same entity counts, same texts (tolerate: {file: predicate on a Node-only text})."""
        tolerate = tolerate or {}
        node_files = sorted(os.listdir(node_dir))
        py_files = sorted(os.listdir(os.path.join(out, 'dxf')))
        self.assertEqual(node_files, py_files)
        for f in node_files:
            cn, tn = sheet_stats(os.path.join(node_dir, f))
            cp, tp = sheet_stats(os.path.join(out, 'dxf', f))
            self.assertEqual(dict(cn), dict(cp), f'{f}: entity counts per type differ')
            only_node, only_py = tn - tp, tp - tn
            ok = tolerate.get(f)
            if ok:
                self.assertTrue(all(ok(t) for t in only_node), f'{f}: texts missing in the Python sheet: {sorted(only_node)}')
                self.assertEqual(sum(only_node.values()), sum(only_py.values()), f'{f}: replaced texts differ in number: {sorted(only_py)}')
            else:
                self.assertEqual(dict(only_node), {}, f'{f}: texts missing in the Python sheet')
                self.assertEqual(dict(only_py), {}, f'{f}: extra texts in the Python sheet')


class SamplePackageTest(SheetsBase):
    """The bundled sample drawing: two levels, eight sheets each, plus the cover."""

    def build(self):
        with open(SAMPLE_DXF, encoding='utf-8', errors='replace') as fh:
            dxf = parse_dxf(fh.read())
        model = extract_model(dxf, {'spec': {}, 'levelNames': ['SAMPLE STRUCTURAL INPUT']})
        return compose_package(model, {'project': 'PROJECT NAME', 'prefix': 'SPAN-SD', 'layerStandard': self.std, 'mode': 'shop', 'date': '2026-09-28'})

    def test_sample_package(self):
        pack = self.build()
        self.assertEqual(len(pack['sheets']), 17)
        self.assertEqual([s['drawingNo'] for s in pack['sheets']][:4], ['SPAN-SD-000', 'SPAN-SD-L01-01', 'SPAN-SD-L01-02', 'SPAN-SD-L01-03'])
        self.assertEqual(pack['sheets'][0]['key'], 'cover')
        self.assertEqual(pack['sheets'][0]['level'], 'ALL')
        self.assertEqual(sorted(k for k in pack['sheets'][1]), sorted(['root', 'sheet', 'blockName', 'drawingNo', 'title', 'level', 'levelName', 'scale', 'key', 'rows', 'csvCols', 'weight', 'leftoverRows', 'checks']))
        self.assertEqual(pack['sheets'][2]['key'], 'bottom')
        self.assertTrue(pack['sheets'][2]['weight'] > 0)
        self.assertIs(pack['sheets'][2]['csvCols'], SCHEDULE_COLS)
        # the package canvas holds every sheet block and the layer standard names
        self.assertTrue(all(s['blockName'] in pack['pkg'].blocks for s in pack['sheets']))
        self.assertIn('SPAN-SHEET-FRAME', pack['pkg'].layers)
        files = write_package(pack, self.dir)
        self.assertEqual(len(files), 17)
        for p in files:
            n = audit_errors(p)
            if n is not None:
                self.assertEqual(n, 0, f'ezdxf audit errors in {os.path.basename(p)}')
        if not os.path.isdir(NODE_SAMPLE):
            self.skipTest(f'Node reference package not found at {NODE_SAMPLE}')
        self.assertEqual(sorted(os.listdir(NODE_SAMPLE)), sorted(os.path.basename(p) for p in files))
        self.assert_parity(NODE_SAMPLE, self.dir)


class RamPackageTest(SheetsBase):
    """The synthetic RAM Concept model: the RAM-only sheets (02A / 03A / 07A / 07B / 07C) and the punching sheet with the RAM assumptions."""

    def build(self):
        ram = read_ram_concept(build_synthetic_cpt(self.dir))
        # The JS ramToModel base spec carries no uEdge.total / beamLeg / beamTop: JS reads them as undefined (NaN on the
        # U-bar sheet of the Node reference). The office values are given here explicitly, so the test reads the same
        # whether or not ram_concept.py supplies them itself.
        model = ram_to_model(ram, level_name='BASEMENT', level_id=None, spec={'uEdge': {'dia': 12, 'spacing': 200, 'leg': 1200, 'total': 4000, 'beamLeg': 400, 'beamTop': 3600}})
        for l in model['levels']:  # what cli.mjs attaches to every level of a RAM model
            l['beamCheck'] = design_beams(l, {**model['spec']})
            l['beamSchedule'] = beam_schedule(ram, l, library=[], design='ram', office=l['beamCheck'])
            l['punchingCheck'] = punching_check(l, {**model['spec'], 'punching': {**(model['spec'].get('punching') or {})}})
        h = ram['project']
        meta = {'layerStandard': self.std, 'mode': 'shop', 'date': '2026-09-28', 'project': ' - '.join(v for v in [h.get('name'), h.get('part')] if v) or 'PROJECT NAME',
                'company': h.get('company') or 'SPAN TECH CONTRACTING', 'revision': re.sub(r'^rev\.?\s*', '', h.get('revision') or '', flags=re.I) or '00'}
        return model, compose_package(model, meta)

    def test_ram_package(self):
        model, pack = self.build()
        nos = [s['drawingNo'] for s in pack['sheets']]
        self.assertEqual(nos, ['SPAN-SD-000', 'SPAN-SD-L01-01', 'SPAN-SD-L01-02', 'SPAN-SD-L01-03', 'SPAN-SD-L01-02A', 'SPAN-SD-L01-03A', 'SPAN-SD-L01-04', 'SPAN-SD-L01-05', 'SPAN-SD-L01-06', 'SPAN-SD-L01-07A', 'SPAN-SD-L01-07B', 'SPAN-SD-L01-07C', 'SPAN-SD-L01-08'])
        self.assertEqual(pack['meta']['project'], 'SYNTHETIC SLAB - PART 1')
        self.assertEqual(pack['meta']['revision'], 'R0')
        lat = next(s for s in pack['sheets'] if s['key'] == 'cables_lat')
        self.assertEqual(lat['rows'][0]['mark'], 'A.01')
        self.assertEqual(lat['rows'][0]['type'], '12.7')
        self.assertIn('LiveEnd', lat['root'].blocks)
        self.assertIn('DeadEnd', lat['root'].blocks)
        self.assertIn('LiveEnd', pack['pkg'].blocks)
        cross = next(s for s in pack['sheets'] if s['key'] == 'cables_cross')
        self.assertEqual(len(cross['checks']), 1)
        level = model['levels'][0]
        self.assertEqual(len(tendon_crossings(level)), 1)
        self.assertTrue(len(cable_stations(level['ram']['tendons'][0], thickness_fn(level))) > 2)
        files = write_package(pack, self.dir)
        for p in files:
            n = audit_errors(p)
            if n is not None:
                self.assertEqual(n, 0, f'ezdxf audit errors in {os.path.basename(p)}')
        if not os.path.isdir(NODE_PLAIN):
            self.skipTest(f'Node reference package not found at {NODE_PLAIN}')
        # the Node reference wrote NaN / undefined where its RAM spec lacks the uEdge keys: those texts (U-bar sheet) and
        # the cover's weight cells that read them (the sheet's '-' weight, the package total without it) are the only
        # tolerated differences
        nan = lambda t: 'NaN' in t or 'undefined' in t  # noqa: E731
        cover_wt = lambda t: t == '-' or t.startswith('TOTAL SCHEDULED REINFORCEMENT')  # noqa: E731
        self.assert_parity(NODE_PLAIN, self.dir, tolerate={'SPAN-SD-L01-04_FRAMING_REBAR_U_BARS_AROUND_REGIONS_L01.dxf': nan, 'SPAN-SD-000_SHOP_DRAWINGS_COVER_INDEX.dxf': cover_wt})


class SheetApiTest(unittest.TestCase):
    def test_defs_and_bbox(self):
        self.assertEqual([d['no'] for d in SHEET_DEFS], ['01', '02', '03', '02A', '03A', '04', '05', '06', '07', '07A', '07B', '07C', '08', '09'])
        level = {'outline': [{'x': 0, 'y': 0}, {'x': 10000, 'y': 0}, {'x': 10000, 'y': 8000}, {'x': 0, 'y': 8000}], 'bbox': {'minX': 0, 'minY': 0, 'maxX': 10000, 'maxY': 8000, 'w': 10000, 'h': 8000, 'cx': 5000, 'cy': 4000},
                 'walls': [{'a': {'x': -2000, 'y': 0}, 'b': {'x': 3000, 'y': 0}}], 'columns': [{'cx': 12000, 'cy': 4000, 'w': 600, 'h': 600}]}
        b = content_bbox(level)
        self.assertEqual((b['minX'], b['maxX']), (-2000, 12300))

    def test_build_sheet_signature(self):
        self.assertTrue(callable(build_sheet))


if __name__ == '__main__':
    unittest.main()
