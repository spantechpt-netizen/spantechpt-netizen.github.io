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
        P = json.loads((ws.work / 'project.json').read_text())
        P['beam_layer'] = 'S-GB'; (ws.work / 'project.json').write_text(json.dumps(P))
        profiles.save_from(ws, 'Test consultant')
        assert 'Test consultant' in profiles.list_profiles()
        print('smoke test OK:', zips[0].name)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
