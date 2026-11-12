"""A project on disk:

    <project>/rcshop.json   name, enabled modules, step history
    <project>/input/        the drawings as received (never changed)
    <project>/work/         the engine's folder: project.json, footings.json, ..., converted DXF, out/
    <project>/logs/         one log per step, check report
    <project>/deliveries/   zip parts sent to the engineer
"""
import glob, json, os, shutil, time
from pathlib import Path

from .steps import STEPS, BY_ID, MODULES
from .paths import engine_dir

# the generator each per-zone script runs (its rules live there)
USES = {'gen_zone_necks.py': ('gen_n.py',), 'gen_zone_cores.py': ('gen_core.py',), 'gen_zone_gb.py': ('gen2.py',),
        'gen_zones.py': ('gen_f.py', 'gen_mat.py', 'gen_cd.py'), 'gen_zone_cd.py': ('gen_cd.py',), 'gen_zone_strip.py': ('gen_st.py',),
        'gen_zone_stairs.py': ('gen_n.py',)}

DATA_FILES = {
    'project.json': 'drawing reading (layers, blocks, views), GB schedule, title block, levels, zones',
    'footings.json': 'isolated footing schedule (L, W, h, bars) + counts',
    'footings_ext.json': 'combined footings / rafts / strip schedule',
    'pool.json': 'swimming pool geometry, profile and bars',
}


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.work, self.input = self.root / 'work', self.root / 'input'
        self.logs, self.deliveries = self.root / 'logs', self.root / 'deliveries'
        self.meta_file = self.root / 'rcshop.json'
        if not self.meta_file.exists():
            raise FileNotFoundError(f'not an RC Shop project: {self.root}')
        self.meta = json.loads(self.meta_file.read_text(encoding='utf-8'))

    # ------------------------------------------------------------------ create / save
    @classmethod
    def create(cls, root, name='', modules=None):
        root = Path(root)
        for d in ('input', 'work', 'work/out', 'logs', 'deliveries'):
            (root / d).mkdir(parents=True, exist_ok=True)
        meta = dict(name=name or root.name, modules=modules or ['core'], history={}, created=time.strftime('%Y-%m-%d %H:%M'))
        if not (root / 'rcshop.json').exists():
            (root / 'rcshop.json').write_text(json.dumps(meta, indent=1), encoding='utf-8')
        return cls(root)

    def save(self):
        self.meta_file.write_text(json.dumps(self.meta, indent=1), encoding='utf-8')

    @property
    def name(self): return self.meta.get('name') or self.root.name

    @property
    def modules(self): return [m for m in self.meta.get('modules', ['core']) if m in MODULES]

    def set_modules(self, mods):
        self.meta['modules'] = ['core'] + [m for m in mods if m != 'core' and m in MODULES]; self.save()

    def steps(self):
        return [s for s in STEPS if s.module in self.modules]

    # ------------------------------------------------------------------ project data
    def project(self):
        p = self.work / 'project.json'
        try:
            return json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}

    def vars(self):
        """values for {name} in the step definitions"""
        P = self.project(); v = {'dxf': P.get('dxf') or self.meta.get('main_dxf', ''), 'main_dxf': self.meta.get('main_dxf', '')}
        fin = P.get('fnd_final') or {}
        v['final_dxf'] = fin.get('dxf', '')
        v['final_shift'] = ','.join(str(a) for a in fin.get('shift', [0, 0]))
        try:
            v['axes'] = sorted(json.loads((self.work / 'axes.json').read_text(encoding='utf-8')))
        except (OSError, ValueError):
            v['axes'] = []
        return v

    def resolve(self, items, v=None):
        v = v or self.vars(); out = []
        for it in items:
            if it.startswith('{') and it.endswith('}') and isinstance(v.get(it[1:-1]), list):
                out += v[it[1:-1]]
            else:
                out.append(it.format(**{k: x for k, x in v.items() if not isinstance(x, list)}))
        return out

    # ------------------------------------------------------------------ status
    def _mtime(self, rel):
        hits = glob.glob(str(self.work / rel))
        return max((os.path.getmtime(h) for h in hits), default=None) if hits else None

    def _engine_mtime(self, step):
        """Newest of the step's engine script and the shared drawing library (gen.py): an updated rule makes the
        sheets drawn before it stale."""
        if not step.script: return 0
        try: eng = engine_dir()
        except FileNotFoundError: return 0
        files = (step.script, 'gen.py') + USES.get(step.script, ())
        return max((os.path.getmtime(eng / f) for f in files if (eng / f).exists()), default=0)

    def status(self, step):
        """-> (state, detail): blocked / ready / done / stale / failed"""
        v = self.vars()
        if '{axes}' in step.args and not v['axes']:
            return 'blocked', 'axes.json missing (run "extract")'
        try:
            needs = self.resolve(step.needs, v); makes = self.resolve(step.makes, v)
        except KeyError as e:
            return 'blocked', f'missing value {e}'
        missing = [n for n in needs if not n or self._mtime(n) is None]
        if missing:
            return 'blocked', 'missing: ' + ', '.join(m or '(path not set in project.json)' for m in missing) + \
                   (f' - {step.hint}' if step.hint else '')
        h = self.meta.get('history', {}).get(step.id)
        if h and h.get('rc') not in (0, None):
            return 'failed', f"last run failed ({h.get('when', '')}) - see logs/{step.id}.log"
        made = [self._mtime(m) for m in makes]
        if not makes or any(m is None for m in made):
            return 'ready', ''
        newest_need = max(self._mtime(n) for n in needs) if needs else 0
        if min(made) + 1 < newest_need:
            return 'stale', 'an input changed after the last run'
        if min(made) + 1 < self._engine_mtime(step):
            return 'stale', 'the program was updated after the last run (new drafting rules) - run it again'
        return 'done', h.get('when', '') if h else ''

    def record(self, step_id, rc, seconds):
        self.meta.setdefault('history', {})[step_id] = dict(rc=rc, when=time.strftime('%Y-%m-%d %H:%M'), seconds=round(seconds, 1))
        self.save()

    # ------------------------------------------------------------------ files
    def add_input(self, path):
        """copy a received drawing into input/ (kept as received) -> its path there"""
        self.input.mkdir(exist_ok=True)
        dst = self.input / Path(path).name
        if Path(path).resolve() != dst.resolve():
            shutil.copy2(path, dst)
        return dst

    def set_main(self, dxf_name):
        self.meta['main_dxf'] = dxf_name; self.save()

    def drawings(self):
        return sorted(p.name for p in self.work.glob('*.dxf'))

    def data_files(self):
        return [(n, d, (self.work / n).exists()) for n, d in DATA_FILES.items()]

    def outputs(self):
        return sorted(p for p in (self.work / 'out').rglob('*.dxf'))
