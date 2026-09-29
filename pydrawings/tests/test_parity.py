"""
Parity with the Node generator: the same input through `python -m pydrawings` and `node shopdrawings/cli.mjs`
gives the same sheets (file names), the same texts on every sheet (multiset of TEXT / MTEXT strings), the same
entity counts per type, the same schedules (CSV), the same quantities / punching / beams JSON, and every DXF passes
the ezdxf audit. Skipped where Node is not installed (the Python package stands on its own).
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parent
sys.path.insert(0, str(PKG))

from pydrawings.dxf_reader import parse_dxf  # noqa: E402
from tests.synthetic_cpt import build_synthetic_cpt  # noqa: E402

NODE = shutil.which('node')
NODE_CLI = REPO / 'shopdrawings' / 'cli.mjs'


def _stats(path):
    """Entity counts per type and the multiset of texts of a sheet DXF (model space and every block)."""
    dxf = parse_dxf(Path(path).read_text(encoding='utf8', errors='replace'))
    ents = list(dxf['entities'])
    for b in dxf['blocks'].values():
        ents.extend(b['entities'])
    counts = collections.Counter(e['type'] for e in ents)
    texts = collections.Counter((e.get('text') or '').strip() for e in ents if e['type'] in ('TEXT', 'MTEXT'))
    return counts, texts


def _audit(path):
    try:
        from ezdxf import recover
    except Exception:  # pragma: no cover - ezdxf is optional
        return 0
    doc, auditor = recover.readfile(str(path))
    return len(auditor.errors)


def _run_node(args, out):
    subprocess.run([NODE, str(NODE_CLI), *args, '--out', str(out), '--no-svg'], check=True, cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_py(args, out):
    subprocess.run([sys.executable, '-m', 'pydrawings', *args, '--out', str(out), '--no-svg'], check=True, cwd=str(PKG), stdout=subprocess.DEVNULL)


@unittest.skipUnless(NODE and NODE_CLI.exists(), 'Node reference generator not available')
class ParityWithNode(unittest.TestCase):
    maxDiff = None

    def _compare(self, node_out, py_out):
        fa = sorted(p.name for p in (node_out / 'dxf').glob('*.dxf'))
        fb = sorted(p.name for p in (py_out / 'dxf').glob('*.dxf'))
        self.assertEqual(fa, fb, 'the same sheets with the same drawing numbers and titles')
        for name in fa:
            ca, ta = _stats(node_out / 'dxf' / name)
            cb, tb = _stats(py_out / 'dxf' / name)
            self.assertEqual(dict(ca), dict(cb), f'{name}: entity counts per type')
            missing = {t: n for t, n in ta.items() if tb.get(t) != n}
            extra = {t: n for t, n in tb.items() if ta.get(t) != n}
            self.assertEqual((missing, extra), ({}, {}), f'{name}: texts on the sheet')
            self.assertEqual(_audit(py_out / 'dxf' / name), 0, f'{name}: ezdxf audit of the Python DXF')
        pa = sorted(p.name for p in (node_out / 'schedules').glob('*.csv'))
        pb = sorted(p.name for p in (py_out / 'schedules').glob('*.csv'))
        self.assertEqual(pa, pb, 'the same schedule files')
        for name in pa:
            self.assertEqual((node_out / 'schedules' / name).read_text(encoding='utf8'), (py_out / 'schedules' / name).read_text(encoding='utf8'), f'{name}: schedule rows')
        for name in ('quantities.json', 'punching.json', 'beams.json', 'plan.json'):
            a, b = node_out / name, py_out / name
            self.assertEqual(a.exists(), b.exists(), f'{name} written by both')
            if a.exists():
                self.assertEqual(json.loads(a.read_text(encoding='utf8')), json.loads(b.read_text(encoding='utf8')), f'{name}: identical')
        pkg = [p for p in ('SHOP_DRAWINGS_PACKAGE.dxf', 'DESIGN_DRAWINGS_PACKAGE.dxf') if (node_out / p).exists()]
        for name in pkg:
            self.assertTrue((py_out / name).exists(), f'{name} written')
            self.assertEqual(_audit(py_out / name), 0, f'{name}: ezdxf audit')
        ma = json.loads((node_out / 'model.json').read_text(encoding='utf8'))
        mb = json.loads((py_out / 'model.json').read_text(encoding='utf8'))
        self.assertEqual([l['id'] for l in ma['levels']], [l['id'] for l in mb['levels']], 'the same levels')
        for x, y in zip(ma['levels'], mb['levels']):
            for key in ('columns', 'walls', 'beams', 'openings', 'thickZones', 'pourStrips'):
                self.assertEqual(len(x.get(key) or []), len(y.get(key) or []), f"{x['id']}: {key}")
        self.assertEqual(ma.get('assumptions'), mb.get('assumptions'), 'the assumptions printed on the sheets')
        self.assertEqual(ma.get('findings'), mb.get('findings'), 'the findings')

    def _both(self, args, level_id=None):
        tmp = Path(tempfile.mkdtemp(prefix='parity-'))
        node_out, py_out = tmp / 'node', tmp / 'py'
        if level_id:
            # the level code goes through the config (meta.levelId) in both generators
            cfg = tmp / 'config.json'
            cfg.write_text(json.dumps({'meta': {'levelId': level_id}, 'spec': {}}), encoding='utf8')
            args = [*args, '--config', str(cfg)]
        _run_node(args, node_out)
        _run_py(args, py_out)
        self._compare(node_out, py_out)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_sample_structural_shop_package(self):
        self._both(['--input', str(REPO / 'shopdrawings' / 'samples' / 'sample-structural-input.dxf')])

    def test_synthetic_ram_shop_package(self):
        d = tempfile.mkdtemp(prefix='ram-')
        self._both(['--input', build_synthetic_cpt(d), '--mode', 'shop', '--level', 'BASEMENT'], level_id='B1')

    def test_synthetic_ram_design_package(self):
        d = tempfile.mkdtemp(prefix='ram-')
        self._both(['--input', build_synthetic_cpt(d), '--mode', 'design', '--level', 'BASEMENT'], level_id='B1')

    def test_synthetic_ram_design_package_with_beams(self):
        d = tempfile.mkdtemp(prefix='ram-')
        self._both(['--input', build_synthetic_cpt(d, beam=True), '--mode', 'design', '--level', 'BASEMENT'], level_id='B1')

    def test_synthetic_ram_design_package_stepped(self):
        d = tempfile.mkdtemp(prefix='ram-')
        self._both(['--input', build_synthetic_cpt(d, step=True), '--mode', 'design', '--level', 'BASEMENT'], level_id='B1')


if __name__ == '__main__':
    unittest.main()
