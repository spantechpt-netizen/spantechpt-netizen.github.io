"""Smoke test with no project data: a pool from the engine's example -> sheets, check, delivery zip.
run: python tests/test_smoke.py   (needs ezdxf, shapely, matplotlib)"""
import json, os, shutil, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
os.environ['RCSHOP_HOME'] = tempfile.mkdtemp(prefix='rcshop_home_')

from rcshop.paths import engine_dir            # noqa: E402
from rcshop.workspace import Workspace         # noqa: E402
from rcshop.runner import run_step             # noqa: E402
from rcshop import profiles                     # noqa: E402


def main():
    root = Path(tempfile.mkdtemp(prefix='rcshop_test_'))
    try:
        ws = Workspace.create(root / 'P', 'Smoke Pool')
        ws.set_modules(['pool'])
        shutil.copy(engine_dir() / 'pool.example.json', ws.work / 'pool.json')
        (ws.work / 'project.json').write_text(json.dumps({
            'dxf': '', 'schedule': {}, 'meta': {'project': 'TEST', 'ref': 'example'}}), encoding='utf-8')
        st = {s.id: ws.status(s)[0] for s in ws.steps()}
        assert st['gen_pool'] == 'ready', st
        assert st['survey'] == 'blocked', st                    # no drawing yet
        assert run_step(ws, 'gen_pool', log=lambda s: None) == 0
        assert ws.status(next(s for s in ws.steps() if s.id == 'gen_pool'))[0] == 'done'
        assert run_step(ws, 'check', log=lambda s: None) == 0
        assert run_step(ws, 'package', log=lambda s: None) == 0
        zips = list(ws.deliveries.glob('*.zip'))
        assert len(zips) == 1 and zips[0].stat().st_size > 10000, zips
        # the reader's model, roles and render on the generated sheets (no consultant drawing needed)
        from rcshop.drawing import DrawingModel, render
        from rcshop import roles as R
        m = DrawingModel(ws.outputs()[0], log=lambda s: None)
        assert len(m.p_layer) > 1000 and len(m.t_text) > 100
        buf, size = render(m, m.extents(), (800, 600))
        assert len(buf) == size[0] * size[1] * 4
        t = next(i for i, s in enumerate(m.t_text) if s.startswith('TOTAL STEEL'))
        assert m.pick(*m.t_xy[t], 50) == ('text', t)
        role = R.BY_KEY['fnd_layers']
        i = int(next(k for k, l in enumerate(m.p_layer) if m.layers[l] == 'S-GB-CONC'))
        v, _ = R.value_from_click(m, role, ('poly', i), None)
        assert v == ['S-GB-CONC'], v
        pis, tis, info = R.matches(m, role, v)
        assert len(pis) > 10, info
        assert R.text_pattern('F6A') == r'F\d+[A-Z]?' and R.compile_full(R.text_pattern('RAFT-2')).match('RAFT-12')
        P = json.loads((ws.work / 'project.json').read_text())
        P['beam_layer'] = 'S-GB'; (ws.work / 'project.json').write_text(json.dumps(P))
        profiles.save_from(ws, 'Test consultant')
        assert 'Test consultant' in profiles.list_profiles()
        print('smoke test OK:', zips[0].name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
