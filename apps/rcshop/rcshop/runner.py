"""Run a step: an engine script in the project's work/ folder (separate process: the engine scripts keep module
state and read their inputs on import), or a built-in step (check / package)."""
import os, runpy, subprocess, sys, time
from pathlib import Path

from .paths import FROZEN, engine_dir, settings
from .steps import BY_ID


def engine_cmd(script, args):
    s = settings()
    if s.get('engine_python'):
        return [s['engine_python'], str(engine_dir() / script), *args]
    if FROZEN:                                   # the program runs the script itself (rcshop.exe engine ...)
        return [sys.executable, 'engine', script, *args]
    return [sys.executable, str(engine_dir() / script), *args]


def run_engine_inline(script, args):
    """`rcshop engine <script> args`: run one engine script in this process (used by the frozen program)."""
    eng = engine_dir()
    sys.path.insert(0, str(eng))
    sys.argv = [str(eng / script), *args]
    os.environ.setdefault('MPLBACKEND', 'Agg')
    runpy.run_path(str(eng / script), run_name='__main__')


def run_step(ws, step_id, extra_args=(), log=print):
    step = BY_ID[step_id]
    t0 = time.time()
    ws.logs.mkdir(exist_ok=True)
    for d in ('out', 'out/ZONES', 'out/POOL'):
        (ws.work / d).mkdir(parents=True, exist_ok=True)
    lines = []
    def emit(s):
        lines.append(s); log(s)
    if not step.script:
        from . import checks, package
        try:
            rc = (checks.run if step_id == 'check' else package.run)(ws, emit)
        except Exception as e:                   # a built-in step never kills the program
            emit(f'ERROR: {e}'); rc = 1
    else:
        args = ws.resolve(step.args) + list(extra_args)
        cmd = engine_cmd(step.script, args)
        env = dict(os.environ, MPLBACKEND='Agg', PYTHONPATH=str(engine_dir()) + os.pathsep + os.environ.get('PYTHONPATH', ''),
                   PYTHONIOENCODING='utf-8', RC_PROJECT='project.json')
        emit(f'> {step.script} {" ".join(args)}')
        p = subprocess.Popen(cmd, cwd=ws.work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding='utf-8', errors='replace')
        for ln in p.stdout:
            emit(ln.rstrip('\n'))
        rc = p.wait()
    dt = time.time() - t0
    emit(f'[{step_id}] {"OK" if rc == 0 else "FAILED (exit %s)" % rc} in {dt:.1f} s')
    (ws.logs / f'{step_id}.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    ws.record(step_id, rc, dt)
    return rc


def run_ready(ws, log=print, include_stale=True):
    """run every step that can run, in pipeline order, until nothing more becomes ready"""
    done = set()
    while True:
        todo = [s for s in ws.steps() if s.id not in done and ws.status(s)[0] in (('ready', 'stale') if include_stale else ('ready',))]
        if not todo:
            return
        s = todo[0]; done.add(s.id)
        if run_step(ws, s.id, log=log) != 0:
            log(f'stopped: {s.id} failed'); return
