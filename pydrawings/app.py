#!/usr/bin/env python3
"""
Span Tech drawings - the desktop app of the Python drawings generator, in ONE file.

    python3 app.py                       starts the app and opens it in the browser (http://127.0.0.1:8765)
    python3 app.py --port 9000           another port
    python3 app.py --no-browser          just the server
    python3 app.py --data D:/DRAWINGS    where the projects and the packages are kept (default: data/ beside this file)

The page is the Drawings module of the Span Tech CRM (the same design and the same screens: projects, levels,
generation runs, revisions, previews, the punching and beam alerts with the engineer's decisions, the beam strips
model, the take-off updated from a sheet edited in AutoCAD, the quantities and the cost study, the project's beam
schedule, the project files, the settings with the reinforcement defaults, the frame and the office frame DXF);
the generator is the `pydrawings` package next to this file. Standard library only: no server to install, no
database - the projects, levels, runs and settings are one JSON file (`data/db.json`) and every package is a
folder under `data/projects/<project>/runs/<run>/`.
"""
import argparse
import datetime as _dt
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from pydrawings.cli import generate, load_layer_standard, DEFAULT_LAYER_STANDARD  # noqa: E402
from pydrawings.quantities import cost_study  # noqa: E402
from pydrawings.punching import blocking_after  # noqa: E402
from pydrawings.beam_design import beam_blocking_after  # noqa: E402
from pydrawings.dxf_bars import read_bars, takeoff_from_bars, apply_takeoff  # noqa: E402

VERSION = '1.0.0'
MAX_UPLOAD = 400 * 1024 * 1024
MODES = ['design', 'shop']
RAM_BANDS = ['all', 'user', 'none']
MESH_FACES = ['bottom', 'both']
BEAM_DESIGN = ['ram', 'office', 'max']
ROTATIONS = ['auto', '0', '90']
RUN_STATUS = ['draft', 'issued', 'superseded', 'blocked', 'failed', 'running']
FILE_CATEGORIES = ['design', 'ram', 'pt_design', 'pt_shop']
SUBMITTAL_STATUS = ['draft', 'submitted', 'approved', 'approved_as_noted', 'resubmit', 'rejected', 'withdrawn']
SUBMITTAL_PURPOSES = ['approval', 'information', 'resubmission', 'as_built']
PURPOSE_LABELS = {'approval': 'FOR APPROVAL', 'information': 'FOR INFORMATION', 'resubmission': 'RE-SUBMISSION', 'as_built': 'AS BUILT'}
STATUS_LABELS = {'draft': 'DRAFT', 'submitted': 'SUBMITTED', 'approved': 'APPROVED', 'approved_as_noted': 'APPROVED AS NOTED', 'resubmit': 'REVISE AND RESUBMIT', 'rejected': 'REJECTED', 'withdrawn': 'WITHDRAWN'}
PUNCHING_DECISIONS = ['thicken', 'ram_ok', 'bypass', 'clear']
BEAM_DECISIONS = ['deepen', 'ram_ok', 'bypass', 'clear']

FRAME_DEFAULTS = {'size': 'A1', 'rightWidth': 185, 'bottomStrip': 125, 'titleH': 150, 'refsH': 52, 'keyH': 46, 'schedH': 140, 'keyplan': True, 'refs': True, 'schedule': True, 'details': False}
RATE_DEFAULTS = {'currency': 'SAR', 'steel_per_ton': 3200, 'rebar_labour_per_ton': 350, 'concrete_per_m3': 280, 'formwork_per_m2': 45, 'strand_per_kg': 9.5, 'anchor_live': 45, 'anchor_dead': 25, 'duct_per_m': 6, 'pt_labour_per_m2': 18, 'markup_pct': 15, 'vat_pct': 15}
RATE_KEYS = [k for k in RATE_DEFAULTS if k != 'currency']
# the submittal (transmittal) form: one template for the whole office, filled from the project and the runs
SUBMITTAL_DEFAULTS = {
    'prefix': 'SPAN-SUB', 'title': 'DRAWING SUBMITTAL / TRANSMITTAL', 'title_ar': 'طلب اعتماد مخططات',
    'intro': 'We are pleased to submit the following drawings for your review and approval. Kindly return one signed copy of this form with your comments.',
    'purposes': list(SUBMITTAL_PURPOSES), 'responses': ['APPROVED', 'APPROVED AS NOTED', 'REVISE AND RESUBMIT', 'REJECTED'], 'signatures': ['PREPARED BY', 'CHECKED BY', 'APPROVED BY'],
    'footer': 'This submittal is issued under the office quality procedure; drawings are identified by their number and revision as printed in the title block. A revised drawing is re-submitted under a new submittal number that names the superseded revision.',
    'contact': '',
}
DRAWING_DEFAULTS = {
    'project_prefix': 'P', 'design_prefix': 'SPAN-DD', 'shop_prefix': 'SPAN-SD',
    'company': 'SPAN TECH CONTRACTING', 'company_line': 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
    'prepared': 'SPAN TECH DESIGN OFFICE', 'checked': '', 'approved': '', 'designer': '',
    'status_design': 'DESIGN DRAWING - FOR REVIEW', 'status_shop': 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
    'default_mode': 'design', 'ram_bands': 'all', 'mesh': 'bottom', 'beam_design': 'ram', 'rotate': 'auto',
    'spec': {}, 'frame': FRAME_DEFAULTS, 'frame_dxf': None, 'frame_dxf_name': None, 'frame_dxf_entities': None, 'rates': RATE_DEFAULTS, 'submittal': SUBMITTAL_DEFAULTS,
}


class ApiError(Exception):
    def __init__(self, status, message, message_ar=None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.message_ar = message_ar or message


def bad_request(en, ar=None):
    return ApiError(400, en, ar)


def not_found(en, ar=None):
    return ApiError(404, en, ar)


def now_iso():
    return _dt.datetime.now().replace(microsecond=0).isoformat()


def today():
    return _dt.date.today().isoformat()


# ----------------------------------------------------------------------------------------------------- the store
class Store:
    """Projects, levels, runs, files and settings in one JSON file, written whole after every change."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'db.json'
        self.lock = threading.RLock()
        self.data = {'settings': {}, 'projects': [], 'levels': [], 'runs': [], 'files': [], 'submittals': [], 'counters': {}, 'next_id': 1}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding='utf8')))
                self.data.setdefault('submittals', [])
            except Exception:
                backup = self.path.with_suffix('.broken.json')
                shutil.copyfile(self.path, backup)
                print(f'! db.json could not be read; a copy is kept at {backup}')

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding='utf8')
            os.replace(tmp, self.path)

    def new_id(self):
        with self.lock:
            n = self.data['next_id']
            self.data['next_id'] = n + 1
            return n

    def counter(self, key):
        with self.lock:
            n = self.data['counters'].get(key, 0) + 1
            self.data['counters'][key] = n
            return n

    def table(self, name):
        return self.data[name]

    def get(self, name, id_):
        for row in self.data[name]:
            if row['id'] == id_:
                return row
        return None

    def remove(self, name, pred):
        self.data[name] = [r for r in self.data[name] if not pred(r)]


STORE = None
DATA = None
GEN_LOCK = threading.Lock()  # one package at a time: generating is pure CPU


def project_dir(pid):
    return DATA / 'projects' / str(pid)


def run_dir(pid, rid):
    return project_dir(pid) / 'runs' / str(rid)


def frame_path():
    return DATA / 'frame.dxf'


def reference_path(pid, lid):
    return project_dir(pid) / 'ref' / f'{lid}.dxf'


def drawing_settings():
    stored = STORE.data.get('settings') or {}
    out = {**DRAWING_DEFAULTS, **stored}
    out['spec'] = {**(DRAWING_DEFAULTS['spec']), **(stored.get('spec') or {})}
    out['frame'] = {**FRAME_DEFAULTS, **(stored.get('frame') or {})}
    out['rates'] = {**RATE_DEFAULTS, **(stored.get('rates') or {})}
    out['submittal'] = {**SUBMITTAL_DEFAULTS, **(stored.get('submittal') or {})}
    return out


# --------------------------------------------------------------------------------------------------- validation
def s(v, max_len=200, fallback=None):
    if v is None:
        return fallback
    v = str(v).strip()
    return v[:max_len] if v else fallback


def one_of(v, allowed, fallback=None):
    v = None if v is None else str(v)
    if v in allowed:
        return v
    if fallback is not None:
        return fallback
    raise bad_request(f'{v}: one of {", ".join(allowed)} expected', f'{v}: القيمة لازم تكون واحدة من {", ".join(allowed)}')


def num(v, fallback=None):
    if v is None or v == '':
        return fallback
    try:
        f = float(v)
    except Exception:
        return fallback
    return int(f) if f == int(f) else f


def normalise_code(v, field='code'):
    v = re.sub(r'[^A-Za-z0-9-]+', '', str(v or '')).upper()
    if not v:
        raise bad_request(f'{field}: letters, digits and dashes only', f'{field}: حروف وأرقام وشرطات بس')
    return v[:20]


def column_list(v):
    items = v if isinstance(v, list) else re.split(r'[,;\s]+', str(v or ''))
    return [str(x).strip().upper() for x in items if str(x).strip()][:500]


def next_project_code(settings):
    year = _dt.date.today().year
    n = STORE.counter(f'drawing_projects:{year}')
    return f"{settings.get('project_prefix') or 'P'}{str(year)[-2:]}-{n:03d}"


# ------------------------------------------------------------------------------------------------ records
def load_project(pid):
    p = STORE.get('projects', int(pid))
    if not p:
        raise not_found('Project not found', 'المشروع مش موجود')
    return p


def load_level(lid):
    l = STORE.get('levels', int(lid))
    if not l:
        raise not_found('Level not found', 'الدور مش موجود')
    return l


def load_run(rid):
    r = STORE.get('runs', int(rid))
    if not r:
        raise not_found('Run not found', 'الإصدار مش موجود')
    return r


def project_levels(pid):
    return sorted([l for l in STORE.table('levels') if l['project_id'] == pid], key=lambda l: (l.get('sort_order') or 0, l['id']))


def project_runs(pid):
    return sorted([r for r in STORE.table('runs') if r['project_id'] == pid], key=lambda r: -r['serial'])


def public_run(run, with_report=False):
    level = STORE.get('levels', run['level_id']) or {}
    out = {k: v for k, v in run.items() if k != 'report_md' or with_report}
    out['level_code'] = level.get('code')
    out['level_name'] = level.get('name')
    out['level_zone'] = level.get('zone')
    for k in ('sheets', 'assumptions', 'findings', 'beams'):
        out.setdefault(k, [])
    return out


def public_project(p):
    levels = project_levels(p['id'])
    runs = [r for r in project_runs(p['id']) if r['status'] not in ('failed', 'running')]
    out = dict(p)
    out['level_count'] = len(levels)
    out['run_count'] = len(runs)
    out['last_run_at'] = runs[0]['created_at'] if runs else None
    return out


def public_level(l):
    runs = [r for r in project_runs(l['project_id']) if r['level_id'] == l['id'] and r['status'] not in ('failed', 'running')]
    out = dict(l)
    out['run_count'] = len(runs)
    out['last_revision'] = runs[0]['revision'] if runs else None
    out['last_run_at'] = runs[0]['created_at'] if runs else None
    out.setdefault('punching', {})
    out.setdefault('reference', None)
    return out


def level_title(level):
    return ' - '.join([v for v in [level.get('name'), level.get('zone')] if v]).upper()


def project_fields(body, partial=False):
    out = {}
    name = s(body.get('name'))
    if not partial and not name:
        raise bad_request('name is required', 'اسم المشروع مطلوب')
    if name is not None or not partial:
        out['name'] = name
    for k in ('name_ar', 'client', 'consultant', 'contractor', 'location', 'prepared', 'checked', 'approved'):
        if k in body or not partial:
            out[k] = s(body.get(k))
    if 'country' in body or not partial:
        out['country'] = one_of(body.get('country'), ['SA', 'EG', 'QA', ''], fallback='') or None
    if 'notes' in body or not partial:
        out['notes'] = s(body.get('notes'), 2000)
    for k, allowed, d in (('default_mode', MODES, 'design'), ('ram_bands', RAM_BANDS, 'all'), ('mesh', MESH_FACES, 'bottom'), ('beam_design', BEAM_DESIGN, 'ram'), ('rotate', ROTATIONS, 'auto')):
        if k in body or not partial:
            out[k] = one_of(body.get(k), allowed, fallback=d)
    if 'spec' in body or not partial:
        spec = body.get('spec') or {}
        if not isinstance(spec, dict):
            raise bad_request('spec must be a JSON object', 'المواصفات لازم تكون JSON object')
        out['spec'] = spec
    return out


def level_fields(body, partial=False):
    out = {}
    if 'code' in body or not partial:
        out['code'] = normalise_code(body.get('code'))
    if 'name' in body or not partial:
        name = s(body.get('name'))
        if not name:
            raise bad_request('name is required', 'اسم الدور مطلوب')
        out['name'] = name
    for k in ('zone', 'notes'):
        if k in body or not partial:
            out[k] = s(body.get(k), 2000 if k == 'notes' else 200)
    if 'wall_thickness' in body or not partial:
        out['wall_thickness'] = num(body.get('wall_thickness'))
    if 'sort_order' in body or not partial:
        out['sort_order'] = num(body.get('sort_order'), 0)
    return out


# ------------------------------------------------------------------------------------------ beam types
def beam_mark_no(mark):
    m = re.search(r'(\d+)\s*$', str(mark or ''))
    return int(m.group(1)) if m else 0


def same_beam_type(a, b):
    g = lambda x, k1, k2: ((x.get(k1) or {}).get(k2) or 0)
    return a.get('width') == b.get('width') and a.get('depth') == b.get('depth') and g(a, 'top', 'area') == g(b, 'top', 'area') and g(a, 'bottom', 'area') == g(b, 'bottom', 'area') \
        and g(a, 'stirrups', 'dia') == g(b, 'stirrups', 'dia') and g(a, 'stirrups', 'legs') == g(b, 'stirrups', 'legs') and g(a, 'stirrups', 'spacing') == g(b, 'stirrups', 'spacing')


def append_beam_types(project, incoming, source):
    """Appends types to the project's schedule, never changing the ones on record (identical skipped, clashing marks renumbered)."""
    types = project.setdefault('beam_types', [])
    nxt = max([0] + [beam_mark_no(t.get('mark')) for t in types]) + 1
    added = []
    for t in incoming or []:
        if not t or not t.get('width') or not t.get('depth'):
            continue
        if any(same_beam_type(x, t) for x in types):
            continue
        clean = {'mark': t.get('mark'), 'width': t['width'], 'depth': t['depth'], 'section': f"{t['width']}x{t['depth']}", 'top': t.get('top'), 'bottom': t.get('bottom'), 'stirrups': t.get('stirrups'), 'source': {**source, 'mark': t.get('mark')}, 'created_at': now_iso()}
        if not clean['mark'] or any(x.get('mark') == clean['mark'] for x in types):
            clean['mark'] = f'B{nxt}'
        nxt = max(nxt, beam_mark_no(clean['mark'])) + 1
        types.append(clean)
        added.append(clean)
    return types, added


# --------------------------------------------------------------------------------------------- generation
def run_meta(settings, project, level, mode, revision):
    prefix_base = settings['shop_prefix'] if mode == 'shop' else settings['design_prefix']
    designer = str(settings.get('designer') or '')
    return {
        'designer': designer,
        'preparedInitials': ''.join(w[0] for w in designer.split() if w).upper()[:4] if designer else '',
        'prefix': f"{prefix_base}-{project['code']}",
        'project': project.get('name'), 'projectCode': project['code'],
        'client': project.get('client') or '', 'engineer': project.get('consultant') or '', 'contractor': project.get('contractor') or '', 'location': project.get('location') or '',
        'company': settings['company'], 'company_line': settings['company_line'],
        'prepared': designer or project.get('prepared') or settings.get('prepared') or '',
        'checked': project.get('checked') or settings.get('checked') or '',
        'approved': project.get('approved') or settings.get('approved') or '',
        'status': settings['status_shop'] if mode == 'shop' else settings['status_design'],
        'revision': revision, 'date': today(), 'levelId': level['code'],
        'frame': settings['frame'],
        'frameDxf': str(frame_path()) if settings.get('frame_dxf') and frame_path().exists() else None,
    }


def zip_folder(out_dir, zip_path, folder):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(out_dir).rglob('*')):
            if p.is_file():
                z.write(p, f'{folder}/{p.relative_to(out_dir).as_posix()}')


def start_run(level, project, query, source_run=None, upload=None):
    """One package: the record, the source file, the generator, the ZIP; blocked when the punching / beam check says so."""
    settings = drawing_settings()
    q = query or {}
    mode = one_of(q.get('mode'), MODES, fallback=(source_run or {}).get('mode') or project.get('default_mode') or settings['default_mode'])
    ram_bands = one_of(q.get('ram_bands'), RAM_BANDS, fallback=(source_run or {}).get('ram_bands') or project.get('ram_bands') or settings['ram_bands'])
    mesh = one_of(q.get('mesh'), MESH_FACES, fallback=(source_run or {}).get('mesh') or project.get('mesh') or settings['mesh'])
    beam_design = one_of(q.get('beam_design'), BEAM_DESIGN, fallback=(source_run or {}).get('beam_design') or project.get('beam_design') or settings['beam_design'])
    rotate = one_of(q.get('rotate'), ROTATIONS, fallback=(source_run or {}).get('rotate') or project.get('rotate') or settings['rotate'])
    revision = s(q.get('revision'), 6)
    if revision is None:
        previous = len([r for r in STORE.table('runs') if r['level_id'] == level['id'] and r['mode'] == mode and r['status'] not in ('failed', 'running')])
        revision = f'{previous:02d}'
    else:
        revision = revision.zfill(2) if re.fullmatch(r'\d{1,2}', revision) else revision.upper()
    notes = s(q.get('notes'), 2000)
    meta = run_meta(settings, project, level, mode, revision)
    with STORE.lock:
        run = {
            'id': STORE.new_id(), 'project_id': project['id'], 'level_id': level['id'], 'serial': STORE.counter(f"drawing_runs:{project['id']}"),
            'mode': mode, 'revision': revision, 'ram_bands': ram_bands, 'mesh': mesh, 'beam_design': beam_design, 'rotate': rotate, 'notes': notes,
            'prefix': meta['prefix'], 'source_name': s(q.get('name')) or (source_run or {}).get('source_name'), 'status': 'running',
            'created_at': now_iso(), 'created_by_name': settings.get('designer') or None, 'sheet_count': 0, 'sheets': [], 'assumptions': [], 'findings': [],
        }
        STORE.table('runs').append(run)
        STORE.save()
    d = run_dir(project['id'], run['id'])
    out = d / 'out'
    try:
        d.mkdir(parents=True, exist_ok=True)
        if upload:
            tmp, src_name, src_bytes = upload
            shutil.move(str(tmp), str(d / src_name))
        else:
            if not (source_run or {}).get('source_file'):
                raise bad_request('The earlier run kept no model file', 'الإصدار القديم مفيهوش ملف الموديل')
            shutil.copyfile(run_dir(source_run['project_id'], source_run['id']) / source_run['source_file'], d / source_run['source_file'])
            src_name, src_bytes = source_run['source_file'], source_run.get('source_bytes')
        run['source_file'] = src_name
        run['source_bytes'] = src_bytes
        ref = level.get('reference')
        reference = {'file': str(reference_path(project['id'], level['id'])), **{k: v for k, v in ref.items() if k not in ('name', 'summary', 'bytes')}} if ref else None
        rec = level.get('punching') or {}
        decision = rec.get('decision') if rec.get('decision') and rec['decision'].get('mode') != 'clear' else None
        beam_decision = rec.get('beam_decision') if rec.get('beam_decision') and rec['beam_decision'].get('mode') != 'clear' else None
        project_spec = project.get('spec') or {}
        punching_spec = {**((settings['spec'] or {}).get('punching') or {}), **(project_spec.get('punching') or {}), 'ramFailed': rec.get('ram_failed') or []}
        if decision and decision['mode'] == 'ram_ok':
            punching_spec['ramOk'] = (decision.get('flagged') or []) if decision.get('columns') == 'all' else decision.get('columns')
        if decision and decision['mode'] == 'bypass':
            punching_spec['override'] = {'columns': decision.get('columns'), 'by': decision.get('by'), 'date': decision.get('date'), 'note': decision.get('note')}
        beams_spec = {**(project_spec.get('beams') or {}), 'ramFailed': rec.get('beams_ram_failed') or []}
        if beam_decision and beam_decision['mode'] == 'bypass':
            beams_spec['override'] = {'beams': beam_decision.get('columns'), 'by': beam_decision.get('by'), 'date': beam_decision.get('date'), 'note': beam_decision.get('note')}
        spec = {**(settings['spec'] or {}), **project_spec, 'ramBands': ram_bands, 'mesh': mesh, 'rotate': rotate, 'punching': punching_spec,
                'beamTypes': project.get('beam_types') or [], 'beamDesign': beam_design, 'beams': beams_spec}
        if level.get('wall_thickness'):
            spec['wallThickness'] = level['wall_thickness']
        if reference:
            spec['reference'] = reference
        t0 = time.time()
        with GEN_LOCK:
            res = generate(input_dxf=str(d / src_name), out=str(out), meta=meta, spec=spec, svg=True, level_names=[level_title(level)], layer_standard=load_layer_standard(DEFAULT_LAYER_STANDARD), mode=mode)
        model, pack = res['model'], res['pack']
        if not model['levels']:
            raise bad_request('No slab was found in this file: it is not a RAM Concept model with a meshed slab (or not the plan DXF the generator reads).',
                              'الملف ده مفيهوش بلاطة: مش موديل رام فيه بلاطة متعملة لها مش (أو مش المسقط DXF اللي البرنامج بيقراه).')
        folder = f"{meta['prefix']}-{level['code']}_REV{revision}"
        zip_folder(out, d / 'package.zip', folder)
        report = (out / 'REPORT.md').read_text(encoding='utf8') if (out / 'REPORT.md').exists() else None
        punching = [{**pc, 'blocking_after': blocking_after(pc, decision)} for pc in res.get('punching') or []]
        blocking = [c for pc in punching for c in pc['blocking_after']]
        punching_rec = {'levels': punching, 'blocking': blocking, 'warnings': [w for pc in punching for w in pc.get('warnings') or []], 'decision': decision, 'ram_failed': rec.get('ram_failed') or []} if punching else None
        beam_checks = [{**bc, 'blocking_after': beam_blocking_after(bc, beam_decision)} for bc in res.get('beamChecks') or []]
        beam_blocking = [b for bc in beam_checks for b in bc['blocking_after']]
        beam_rec = {'design': beam_design, 'levels': beam_checks, 'blocking': beam_blocking, 'warnings': [w for bc in beam_checks for w in bc.get('warnings') or []], 'decision': beam_decision, 'ram_failed': rec.get('beams_ram_failed') or []} if beam_checks else None
        beams = [{'level': l['id'], 'name': l['name'], **l['beamSchedule']} for l in model['levels'] if l.get('beamSchedule')]
        with STORE.lock:
            run.update({
                'status': 'blocked' if blocking or beam_blocking else 'draft',
                'punching': punching_rec, 'beam_check': beam_rec,
                'sheet_count': len(pack['sheets']),
                'sheets': [{'no': sh['drawingNo'], 'title': sh['title'], 'block': sh['blockName'], 'level': sh.get('level'), 'level_name': sh.get('levelName'), 'scale': sh.get('scale') or None,
                            'weight': round(sh['weight']) if sh.get('weight') else None, 'file': f"{sh['drawingNo']}_{sh['blockName']}"} for sh in pack['sheets']],
                'assumptions': [(f"[{a['level']}] " if a.get('level') else '') + str(a.get('text')) for a in model.get('assumptions') or []],
                'findings': list(model.get('findings') or []),
                'report_md': report, 'duration_ms': int((time.time() - t0) * 1000),
                'quantities': res.get('quantities'), 'beams': beams,
                'levels': [{'id': l['id'], 'name': l['name'], 'thickness': l.get('thickness'), 'columns': len(l.get('columns') or [])} for l in model['levels']],
            })
            new_types = [{**t, 'level': lv['level']} for lv in beams for t in lv.get('added') or []]
            if new_types:
                append_beam_types(project, new_types, {'project_id': project['id'], 'project_code': project['code'], 'run_id': run['id'], 'revision': revision, 'level': level['code'], 'by': settings.get('designer')})
            STORE.save()
        return run
    except Exception as e:  # the run is kept as failed with its message
        message = str(e).split('\n')[0][:500] if isinstance(e, ApiError) else (str(e) or e.__class__.__name__)[:500]
        traceback.print_exc()
        with STORE.lock:
            run['status'] = 'failed'
            run['error'] = message
            STORE.save()
        if isinstance(e, ApiError):
            raise
        raise ApiError(500, message, message)


def current_runs(project):
    """The run the take-off of every level comes from: issued first, else the latest draft."""
    runs = [r for r in project_runs(project['id']) if r['status'] not in ('failed', 'running')]
    picked = []
    for level in project_levels(project['id']):
        mine = [r for r in runs if r['level_id'] == level['id'] and r.get('quantities')]
        rank = lambda r: ((2 if r['status'] == 'issued' else 1 if r['status'] == 'draft' else 0) * 10 + (1 if r['mode'] == project.get('default_mode') else 0), r['serial'])
        mine.sort(key=rank, reverse=True)
        if mine:
            picked.append((level, mine[0]))
    return picked


def project_quantities(project):
    picked = current_runs(project)
    levels = []
    for level, run in picked:
        for l in run['quantities'].get('levels') or []:
            levels.append({**l, 'level_code': level['code'], 'level_name': level['name'], 'run_id': run['id'], 'run_serial': run['serial'], 'revision': run['revision'], 'mode': run['mode'], 'run_status': run['status']})
    r1 = lambda v: round(v * 10) / 10
    sum_by = lambda get: r1(sum((get(l) or 0) for l in levels))
    by_dia = {}
    for l in levels:
        for d in l['steel'].get('byDia') or []:
            row = by_dia.setdefault(d['dia'], {'dia': d['dia'], 'total_m': 0, 'kg': 0, 'count': 0})
            row['total_m'] += d.get('total_m') or 0
            row['kg'] += d.get('kg') or 0
            row['count'] += d.get('count') or 0
    pt = [l for l in levels if l.get('cables')]
    c = lambda l, k: (l.get('cables') or {}).get(k)
    totals = {
        'steel': {'kg': sum_by(lambda l: l['steel']['kg']), 'top_kg': sum_by(lambda l: l['steel'].get('top_kg')), 'bottom_kg': sum_by(lambda l: l['steel'].get('bottom_kg')), 'other_kg': sum_by(lambda l: l['steel'].get('other_kg')), 'mesh_kg': sum_by(lambda l: l['steel'].get('mesh_kg')),
                  'byDia': [{**d, 'total_m': r1(d['total_m']), 'kg': r1(d['kg'])} for d in sorted(by_dia.values(), key=lambda d: d['dia'])]},
        'concrete': {k: sum_by(lambda l, k=k: l['concrete'].get(k)) for k in ('gross_area_m2', 'openings_m2', 'net_area_m2', 'slab_m3', 'drops_m3', 'beams_m3', 'total_m3', 'formwork_m2', 'edge_formwork_m2')},
        'cables': {'tendons': sum(c(l, 'tendons') or 0 for l in pt), 'strands': sum(c(l, 'strands') or 0 for l in pt), 'tendon_m': sum_by(lambda l: c(l, 'tendon_m')), 'strand_m': sum_by(lambda l: c(l, 'strand_m')), 'cutting_m': sum_by(lambda l: c(l, 'cutting_m')), 'kg': sum_by(lambda l: c(l, 'kg')),
                   'live_ends': sum(c(l, 'live_ends') or 0 for l in pt), 'dead_ends': sum(c(l, 'dead_ends') or 0 for l in pt), 'duct_small_m': sum_by(lambda l: c(l, 'duct_small_m')), 'duct_large_m': sum_by(lambda l: c(l, 'duct_large_m'))} if pt else None,
    }
    net = totals['concrete']['net_area_m2']
    totals['steel']['kg_per_m2'] = round(totals['steel']['kg'] / net * 100) / 100 if net else None
    if totals['cables']:
        totals['cables']['kg_per_m2'] = round(totals['cables']['kg'] / net * 100) / 100 if net else None
        totals['cables']['strand_m_per_m2'] = round(totals['cables']['strand_m'] / net * 100) / 100 if net else None
    return {'levels': levels, 'totals': totals, 'runs': [{'level_id': lv['id'], 'level_code': lv['code'], 'run_id': r['id'], 'serial': r['serial'], 'revision': r['revision'], 'mode': r['mode'], 'status': r['status']} for lv, r in picked]}


def open_in_file_manager(path):
    path = str(path)
    if platform.system() == 'Windows':
        os.startfile(path)  # noqa: S606 - the OS file manager
    elif platform.system() == 'Darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


# --------------------------------------------------------------------------------------------- the API
ROUTES = []


def route(method, pattern):
    rx = re.compile('^' + re.sub(r':(\w+)', r'(?P<\1>[^/]+)', pattern) + '$')

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


@route('GET', '/api/bootstrap')
def api_bootstrap(h, m):
    return {'settings': drawing_settings(), 'version': VERSION, 'data_dir': str(DATA), 'python': platform.python_version(), 'projects': len(STORE.table('projects'))}


@route('GET', '/api/settings')
def api_settings(h, m):
    return {'settings': drawing_settings()}


@route('PUT', '/api/settings')
def api_settings_put(h, m):
    body = h.json_body()
    if not isinstance(body, dict):
        raise bad_request('settings must be an object', 'الإعدادات لازم تكون object')
    with STORE.lock:
        current = STORE.data.get('settings') or {}
        keep = {k: current.get(k) for k in ('frame_dxf', 'frame_dxf_name', 'frame_dxf_entities') if k in current}
        clean = {k: v for k, v in body.items() if k in DRAWING_DEFAULTS and k not in ('frame_dxf', 'frame_dxf_name', 'frame_dxf_entities')}
        if 'submittal' in clean and not isinstance(clean['submittal'], dict):
            raise bad_request('submittal must be an object', 'قالب طلب الاعتماد لازم يكون object')
        if 'spec' in clean and not isinstance(clean['spec'], dict):
            raise bad_request('spec must be a JSON object', 'المواصفات لازم تكون JSON object')
        STORE.data['settings'] = {**current, **clean, **keep}
        STORE.save()
    return {'settings': drawing_settings()}


@route('POST', '/api/settings/reset')
def api_settings_reset(h, m):
    with STORE.lock:
        STORE.data['settings'] = {}
        STORE.save()
    return {'settings': drawing_settings()}


@route('POST', '/api/settings/frame')
def api_frame_upload(h, m):
    name = s(h.query.get('name'), 200, 'frame.dxf')
    if not name.lower().endswith('.dxf'):
        raise bad_request('The frame must be a DXF file', 'الفريم لازم يكون DXF')
    h.save_upload(frame_path())
    from pydrawings.cli import frame_entities
    try:
        ents = frame_entities(frame_path().read_text(encoding='utf8', errors='replace'))
    except Exception as e:
        frame_path().unlink(missing_ok=True)
        raise bad_request(f'The frame could not be read: {str(e)[:200]}', f'الفريم مش مقروء: {str(e)[:200]}')
    if not ents:
        frame_path().unlink(missing_ok=True)
        raise bad_request('No entities in that DXF', 'مفيش كيانات في الملف ده')
    with STORE.lock:
        STORE.data.setdefault('settings', {}).update({'frame_dxf': 'frame.dxf', 'frame_dxf_name': name, 'frame_dxf_entities': len(ents)})
        STORE.save()
    return {'frame_dxf': 'frame.dxf', 'name': name, 'entities': len(ents)}


@route('GET', '/api/settings/frame')
def api_frame_get(h, m):
    if not frame_path().exists():
        raise not_found('No frame uploaded', 'مفيش فريم مرفوع')
    return h.send_file(frame_path(), 'application/dxf', drawing_settings().get('frame_dxf_name') or 'frame.dxf')


@route('DELETE', '/api/settings/frame')
def api_frame_delete(h, m):
    frame_path().unlink(missing_ok=True)
    with STORE.lock:
        for k in ('frame_dxf', 'frame_dxf_name', 'frame_dxf_entities'):
            STORE.data.setdefault('settings', {})[k] = None
        STORE.save()
    return {'ok': True}


@route('GET', '/api/projects')
def api_projects(h, m):
    q = (h.query.get('q') or '').lower()
    rows = []
    for p in sorted(STORE.table('projects'), key=lambda p: p['created_at'], reverse=True):
        hay = ' '.join(str(p.get(k) or '') for k in ('name', 'name_ar', 'code', 'client', 'consultant', 'location')).lower()
        if not q or q in hay:
            rows.append(public_project(p))
    return {'projects': rows, 'total': len(rows), 'settings': drawing_settings()}


@route('POST', '/api/projects')
def api_project_create(h, m):
    body = h.json_body()
    fields = project_fields(body)
    settings = drawing_settings()
    with STORE.lock:
        code = normalise_code(body['code']) if body.get('code') else next_project_code(settings)
        if any(p['code'] == code for p in STORE.table('projects')):
            raise ApiError(409, f'A project with code {code} already exists', f'فيه مشروع بنفس الكود {code}')
        p = {'id': STORE.new_id(), 'code': code, **fields, 'beam_types': [], 'created_at': now_iso(), 'updated_at': now_iso()}
        STORE.table('projects').append(p)
        STORE.save()
    return {'project': public_project(p)}


@route('GET', '/api/projects/:id')
def api_project(h, m):
    p = load_project(m['id'])
    return {'project': public_project(p), 'levels': [public_level(l) for l in project_levels(p['id'])],
            'runs': [public_run(r) for r in project_runs(p['id']) if r['status'] != 'running'],
            'files': sorted([f for f in STORE.table('files') if f['project_id'] == p['id']], key=lambda f: f['created_at'], reverse=True),
            'submittals': project_submittals(p['id']),
            'settings': drawing_settings(), 'projects': [{'id': x['id'], 'code': x['code'], 'name': x.get('name'), 'beam_types': len(x.get('beam_types') or [])} for x in STORE.table('projects') if x['id'] != p['id']]}


@route('PATCH', '/api/projects/:id')
def api_project_update(h, m):
    p = load_project(m['id'])
    body = h.json_body()
    fields = project_fields(body, partial=True)
    with STORE.lock:
        if body.get('code'):
            code = normalise_code(body['code'])
            if any(x['code'] == code and x['id'] != p['id'] for x in STORE.table('projects')):
                raise ApiError(409, f'A project with code {code} already exists', f'فيه مشروع بنفس الكود {code}')
            p['code'] = code
        p.update(fields)
        p['updated_at'] = now_iso()
        STORE.save()
    return {'project': public_project(p)}


@route('DELETE', '/api/projects/:id')
def api_project_delete(h, m):
    p = load_project(m['id'])
    with STORE.lock:
        STORE.remove('runs', lambda r: r['project_id'] == p['id'])
        STORE.remove('levels', lambda l: l['project_id'] == p['id'])
        STORE.remove('files', lambda f: f['project_id'] == p['id'])
        STORE.remove('submittals', lambda x: x['project_id'] == p['id'])
        STORE.remove('projects', lambda x: x['id'] == p['id'])
        STORE.save()
    shutil.rmtree(project_dir(p['id']), ignore_errors=True)
    return {'ok': True}


@route('POST', '/api/projects/:id/levels')
def api_level_create(h, m):
    p = load_project(m['id'])
    body = h.json_body()
    fields = level_fields(body)
    with STORE.lock:
        if any(l['project_id'] == p['id'] and l['code'] == fields['code'] for l in STORE.table('levels')):
            raise ApiError(409, f"Level {fields['code']} is already registered", f"الدور {fields['code']} متسجل قبل كده")
        if not fields.get('sort_order'):
            fields['sort_order'] = len(project_levels(p['id'])) + 1
        rec = {'ram_failed': column_list(body.get('ram_failed_columns')), 'beams_ram_failed': column_list(body.get('ram_failed_beams'))}
        l = {'id': STORE.new_id(), 'project_id': p['id'], **fields, 'punching': rec, 'reference': None, 'created_at': now_iso()}
        STORE.table('levels').append(l)
        STORE.save()
    return {'level': public_level(l)}


@route('PATCH', '/api/levels/:id')
def api_level_update(h, m):
    l = load_level(m['id'])
    body = h.json_body()
    fields = level_fields(body, partial=True)
    with STORE.lock:
        if fields.get('code') and any(x['project_id'] == l['project_id'] and x['code'] == fields['code'] and x['id'] != l['id'] for x in STORE.table('levels')):
            raise ApiError(409, f"Level {fields['code']} is already registered", f"الدور {fields['code']} متسجل قبل كده")
        rec = l.setdefault('punching', {})
        if 'ram_failed_columns' in body:
            rec['ram_failed'] = column_list(body.get('ram_failed_columns'))
        if 'ram_failed_beams' in body:
            rec['beams_ram_failed'] = column_list(body.get('ram_failed_beams'))
        l.update(fields)
        STORE.save()
    return {'level': public_level(l)}


@route('DELETE', '/api/levels/:id')
def api_level_delete(h, m):
    l = load_level(m['id'])
    with STORE.lock:
        for r in [r for r in STORE.table('runs') if r['level_id'] == l['id']]:
            shutil.rmtree(run_dir(r['project_id'], r['id']), ignore_errors=True)
        STORE.remove('runs', lambda r: r['level_id'] == l['id'])
        STORE.remove('levels', lambda x: x['id'] == l['id'])
        STORE.save()
    reference_path(l['project_id'], l['id']).unlink(missing_ok=True)
    return {'ok': True}


@route('POST', '/api/levels/:id/reference')
def api_reference_upload(h, m):
    l = load_level(m['id'])
    name = s(h.query.get('name'), 200, 'reference.dxf')
    if not name.lower().endswith('.dxf'):
        raise bad_request('The reference plan must be a DXF file (export the DWG with DXFOUT)', 'المخطط المرجعي لازم يكون DXF (اطلع الـ DWG بـ DXFOUT)')
    path = reference_path(l['project_id'], l['id'])
    saved = h.save_upload(path)
    from pydrawings.reference import read_reference_plan
    try:
        plan = read_reference_plan(path.read_text(encoding='utf8', errors='replace'))
        bb = (plan['levels'][0].get('bbox') if plan.get('levels') else None) or None
        summary = {'columns': len(plan['columns']), 'outlines': len(plan['outlines']), 'grid_x': [g['label'] for g in plan['grid']['x']], 'grid_y': [g['label'] for g in plan['grid']['y']],
                   'grid_from_drawing': plan.get('gridFromDrawing'), 'units': plan.get('units'), 'entities': plan.get('entities'),
                   'bbox': {k: round(bb[k]) for k in ('minX', 'minY', 'maxX', 'maxY')} if bb else None}
    except Exception as e:
        path.unlink(missing_ok=True)
        raise bad_request(f'The reference plan could not be read: {str(e)[:200]}', f'المخطط المرجعي مش مقروء: {str(e)[:200]}')
    if not summary['columns'] and not summary['outlines']:
        path.unlink(missing_ok=True)
        raise bad_request('No columns or slab outline found in that DXF', 'مفيش أعمدة ولا حدود بلاطة في الملف ده')
    with STORE.lock:
        cur = l.get('reference') or {}
        l['reference'] = {**cur, 'name': name, 'use': cur.get('use') or {'grid': True, 'columns': True, 'outline': True}, 'align': cur.get('align') or {'mode': 'auto'}, 'summary': summary, 'bytes': saved}
        STORE.save()
    return {'level': public_level(l)}


@route('PATCH', '/api/levels/:id/reference')
def api_reference_update(h, m):
    l = load_level(m['id'])
    if not l.get('reference'):
        raise not_found('No reference plan on this level', 'الدور ده مفيهوش مخطط مرجعي')
    body = h.json_body()
    with STORE.lock:
        ref = l['reference']
        if body.get('use'):
            u = body['use']
            ref['use'] = {'grid': u.get('grid') is not False, 'columns': u.get('columns') is not False, 'outline': u.get('outline') is not False}
        if body.get('align'):
            a = body['align']
            mode = one_of(a.get('mode'), ['auto', 'point'])
            if mode == 'point':
                def n(v, f):
                    try:
                        return float(v)
                    except Exception:
                        raise bad_request(f'{f}: a number is required', f'{f}: لازم رقم')
                ref['align'] = {'mode': mode, 'dxf': {'x': n((a.get('dxf') or {}).get('x'), 'dxf.x'), 'y': n((a.get('dxf') or {}).get('y'), 'dxf.y')}, 'ram': {'x': n((a.get('ram') or {}).get('x'), 'ram.x'), 'y': n((a.get('ram') or {}).get('y'), 'ram.y')}, 'rot': int(a.get('rot')) if str(a.get('rot')) in ('0', '90', '180', '270') else 0}
            else:
                ref['align'] = {'mode': mode}
        STORE.save()
    return {'level': public_level(l)}


@route('DELETE', '/api/levels/:id/reference')
def api_reference_delete(h, m):
    l = load_level(m['id'])
    reference_path(l['project_id'], l['id']).unlink(missing_ok=True)
    with STORE.lock:
        l['reference'] = None
        STORE.save()
    return {'level': public_level(l)}


@route('POST', '/api/levels/:id/generate')
def api_generate(h, m):
    l = load_level(m['id'])
    p = load_project(l['project_id'])
    name = s(h.query.get('name'), 200, 'model.cpt')
    ext = os.path.splitext(name)[1].lower()
    if ext not in ('.cpt', '.dxf', '.json', '.dwg'):
        raise bad_request('Upload a RAM Concept model (.cpt) or a plan DXF', 'ارفع موديل رام (.cpt) أو مسقط DXF')
    tmp = DATA / 'tmp' / f'{int(time.time() * 1000)}{ext}'
    size = h.save_upload(tmp)
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(name))
    try:
        run = start_run(l, p, h.query, upload=(tmp, safe, size))
    finally:
        tmp.unlink(missing_ok=True)
    return {'run': public_run(run)}


@route('GET', '/api/runs/:id')
def api_run(h, m):
    r = load_run(m['id'])
    p = load_project(r['project_id'])
    return {'run': public_run(r, with_report=True), 'project': public_project(p)}


@route('PATCH', '/api/runs/:id')
def api_run_update(h, m):
    r = load_run(m['id'])
    body = h.json_body()
    with STORE.lock:
        if 'notes' in body:
            r['notes'] = s(body.get('notes'), 2000)
        if body.get('status'):
            status = one_of(body['status'], ['draft', 'issued'])
            if r['status'] in ('failed', 'running'):
                raise bad_request('This run produced no drawings', 'الإصدار ده مطلعش لوحات')
            if r['status'] == 'blocked' and status == 'issued':
                raise bad_request('A blocked run cannot be issued before the engineer decides', 'الإصدار المتوقف مينفعش يتعتمد قبل قرار المهندس')
            if status == 'issued':
                for x in STORE.table('runs'):
                    if x['level_id'] == r['level_id'] and x['mode'] == r['mode'] and x['status'] == 'issued' and x['id'] != r['id']:
                        x['status'] = 'superseded'
                r['issued_at'] = now_iso()
            r['status'] = status
        STORE.save()
    return {'run': public_run(r)}


@route('DELETE', '/api/runs/:id')
def api_run_delete(h, m):
    r = load_run(m['id'])
    with STORE.lock:
        STORE.remove('runs', lambda x: x['id'] == r['id'])
        STORE.save()
    shutil.rmtree(run_dir(r['project_id'], r['id']), ignore_errors=True)
    return {'ok': True}


@route('GET', '/api/runs/:id/zip')
def api_run_zip(h, m):
    r = load_run(m['id'])
    path = run_dir(r['project_id'], r['id']) / 'package.zip'
    if not path.exists():
        raise not_found('No package on this run', 'الإصدار ده ملوش باكدج')
    lv = STORE.get('levels', r['level_id']) or {}
    return h.send_file(path, 'application/zip', f"{r['prefix']}-{lv.get('code')}_REV{r['revision']}.zip")


@route('GET', '/api/runs/:id/file/:kind/:name')
def api_run_file(h, m):
    r = load_run(m['id'])
    kind = one_of(m['kind'], ['dxf', 'preview', 'schedules', 'root', 'source', 'edited'])
    name = urllib.parse.unquote(m['name'])
    if '/' in name or '\\' in name or name.startswith('.'):
        raise bad_request('bad file name', 'اسم ملف غلط')
    base = run_dir(r['project_id'], r['id'])
    path = base / name if kind == 'source' else base / 'edited' / name if kind == 'edited' else base / 'out' / name if kind == 'root' else base / 'out' / kind / name
    if not path.exists():
        raise not_found('File not found', 'الملف مش موجود')
    types = {'.dxf': 'application/dxf', '.svg': 'image/svg+xml', '.csv': 'text/csv; charset=utf-8', '.json': 'application/json', '.md': 'text/plain; charset=utf-8', '.cpt': 'application/octet-stream', '.zip': 'application/zip'}
    return h.send_file(path, types.get(path.suffix.lower(), 'application/octet-stream'), name if h.query.get('download') else None)


@route('POST', '/api/runs/:id/open')
def api_run_open(h, m):
    r = load_run(m['id'])
    d = run_dir(r['project_id'], r['id'])
    if not d.exists():
        raise not_found('Run folder not found', 'فولدر الإصدار مش موجود')
    try:
        open_in_file_manager(d / 'out' if (d / 'out').exists() else d)
    except Exception as e:
        raise bad_request(f'Could not open the folder: {e}', f'الفولدر ما اتفتحش: {e}')
    return {'path': str(d)}


@route('POST', '/api/runs/:id/takeoff')
def api_run_takeoff(h, m):
    r = load_run(m['id'])
    name = s(h.query.get('name'), 200, 'edited.dxf')
    if not name.lower().endswith('.dxf'):
        raise bad_request('Upload the edited sheet as DXF', 'ارفع اللوحة المعدلة بصيغة DXF')
    d = run_dir(r['project_id'], r['id']) / 'edited'
    file_name = f"{int(time.time() * 1000)}-{re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(name))}"
    h.save_upload(d / file_name)
    bars = read_bars((d / file_name).read_text(encoding='utf8', errors='replace'))
    if not bars:
        raise bad_request('No tagged bars in this DXF: upload a sheet generated by the program (its bars carry their tags)', 'مفيش أسياخ معلّمة في الملف ده: ارفع لوحة طالعة من البرنامج (أسياخها شايلة علاماتها)')
    change = takeoff_from_bars(bars)
    current = r.get('quantities')
    level_id = change.get('level') or ((current or {}).get('levels') or [{}])[0].get('id')
    settings = drawing_settings()
    q = apply_takeoff(current, level_id, change, {'file': os.path.basename(name), 'by': settings.get('designer'), 'date': today()})
    with STORE.lock:
        r['quantities'] = q
        STORE.save()
    return {'run': public_run(r), 'takeoff': {'file': os.path.basename(name), 'bars': change['bars'], 'changed': change['changed'], 'level': level_id, 'delta': change['delta'], 'list': change['list'][:200]}}


@route('POST', '/api/runs/:id/beam-strips')
def api_beam_strips(h, m):
    r = load_run(m['id'])
    if not r.get('source_file') or not r['source_file'].lower().endswith('.cpt'):
        raise bad_request('This run was not made from a RAM Concept model', 'الإصدار ده مش من موديل رام')
    src = run_dir(r['project_id'], r['id']) / r['source_file']
    out = run_dir(r['project_id'], r['id']) / 'beam-strips.cpt'
    from pydrawings.ram_concept import read_ram_concept
    from pydrawings.beam_strips import write_beam_strips
    try:
        ram = read_ram_concept(str(src))
        if not ram.get('beams'):
            raise bad_request('The model has no beams', 'الموديل مفيهوش كمرات')
        summary = write_beam_strips(str(src), str(out), ram)
    except ApiError:
        raise
    except Exception as e:
        raise bad_request(f'The beam strips could not be written: {str(e)[:200]}', f'الشرائح ما اتكتبتش: {str(e)[:200]}')
    lv = STORE.get('levels', r['level_id']) or {}
    info = {**summary, 'file': 'beam-strips.cpt', 'name': f"{r['prefix']}-{lv.get('code')}_REV{r['revision']}_BEAM-STRIPS.cpt", 'created_at': now_iso(), 'by': drawing_settings().get('designer')}
    with STORE.lock:
        r['beam_strips'] = info
        STORE.save()
    return {'beam_strips': info}


@route('GET', '/api/runs/:id/beam-strips')
def api_beam_strips_get(h, m):
    r = load_run(m['id'])
    info = r.get('beam_strips')
    if not info:
        raise not_found('No beam strips model on this run', 'الإصدار ده ملوش موديل شرائح كمرات')
    return h.send_file(run_dir(r['project_id'], r['id']) / 'beam-strips.cpt', 'application/octet-stream', info['name'])


def _decision(h, m, kind):
    r = load_run(m['id'])
    l = load_level(r['level_id'])
    p = load_project(l['project_id'])
    body = h.json_body()
    rec = l.setdefault('punching', {})
    key = 'decision' if kind == 'punching' else 'beam_decision'
    mode = one_of(body.get('mode'), PUNCHING_DECISIONS if kind == 'punching' else BEAM_DECISIONS)
    if mode == 'clear':
        with STORE.lock:
            rec.pop(key, None)
            STORE.save()
        return {'run': public_run(r), 'decision': None}
    current = r.get('punching') if kind == 'punching' else r.get('beam_check')
    hold = 'thicken' if kind == 'punching' else 'deepen'
    if not current or (not (current.get('blocking') or []) and not (kind == 'punching' and (current.get('warnings') or [])) and mode != hold):
        raise bad_request('This run is not blocked by this check', 'الإصدار ده مش متوقف بسبب الفحص ده')
    if mode in ('bypass', 'ram_ok') and body.get('acknowledge') is not True:
        raise bad_request("The decision needs the engineer's acknowledgement", 'القرار محتاج إقرار المهندس')
    flagged = list(dict.fromkeys(x for lv in current.get('levels') or [] for x in (lv.get('flagged') if kind == 'punching' else lv.get('failing')) or []))
    picked_raw = body.get('columns') if kind == 'punching' else body.get('beams')
    picked = 'all' if picked_raw in (None, 'all') else column_list(picked_raw)
    if picked != 'all' and not picked:
        raise bad_request('Pick the items the decision covers', 'اختار العناصر اللي القرار بيغطيها')
    settings = drawing_settings()
    decision = {'mode': mode, 'columns': picked, 'beams': picked, 'flagged': flagged, 'by': settings.get('designer') or 'DESIGN ENGINEER', 'date': today(), 'run_id': r['id'], 'revision': r['revision'], 'note': s(body.get('note'), 1000)}
    with STORE.lock:
        rec[key] = decision
        STORE.save()
    if mode == hold:
        return {'run': public_run(r), 'decision': decision}
    nxt = start_run(l, p, {'revision': r['revision'], 'notes': r.get('notes')}, source_run=r)
    if nxt['status'] != 'blocked':
        with STORE.lock:
            r['status'] = 'superseded'
            STORE.save()
    return {'run': public_run(nxt), 'decision': decision, 'previous': r['id']}


@route('POST', '/api/runs/:id/punching-decision')
def api_punching_decision(h, m):
    return _decision(h, m, 'punching')


@route('POST', '/api/runs/:id/beam-decision')
def api_beam_decision(h, m):
    return _decision(h, m, 'beam')


@route('POST', '/api/runs/:id/regenerate')
def api_regenerate(h, m):
    r = load_run(m['id'])
    l = load_level(r['level_id'])
    p = load_project(l['project_id'])
    body = h.json_body() if h.content_length else {}
    return {'run': public_run(start_run(l, p, {**{k: v for k, v in body.items() if v is not None}}, source_run=r))}


@route('GET', '/api/projects/:id/quantities')
def api_quantities(h, m):
    p = load_project(m['id'])
    return {'project': {'id': p['id'], 'code': p['code'], 'name': p.get('name')}, **project_quantities(p)}


@route('GET', '/api/projects/:id/cost')
def api_cost(h, m):
    p = load_project(m['id'])
    rates = dict(drawing_settings()['rates'])
    for k, v in h.query.items():
        if k in rates and k != 'currency':
            n = num(v)
            if n is not None:
                rates[k] = n
    q = project_quantities(p)
    return {'project': {'id': p['id'], 'code': p['code'], 'name': p.get('name')}, 'quantities': q, 'cost': cost_study(q, rates)}


@route('GET', '/api/projects/:id/beam-types')
def api_beam_types(h, m):
    return {'beam_types': load_project(m['id']).get('beam_types') or []}


@route('POST', '/api/projects/:id/beam-types/import')
def api_beam_types_import(h, m):
    p = load_project(m['id'])
    body = h.json_body()
    src = load_project(body.get('from_project_id') or 0)
    if src['id'] == p['id']:
        raise bad_request('Pick another project', 'اختار مشروع تاني')
    only = set(x.upper() for x in column_list(body.get('marks'))) if body.get('marks') else None
    incoming = [t for t in src.get('beam_types') or [] if not only or str(t.get('mark')).upper() in only]
    with STORE.lock:
        types, added = append_beam_types(p, incoming, {'project_id': src['id'], 'project_code': src['code'], 'imported': True, 'by': drawing_settings().get('designer')})
        STORE.save()
    return {'beam_types': types, 'added': len(added), 'skipped': len(incoming) - len(added)}


@route('DELETE', '/api/projects/:id/beam-types/:mark')
def api_beam_type_delete(h, m):
    p = load_project(m['id'])
    mark = urllib.parse.unquote(m['mark']).upper()
    used = [r for r in project_runs(p['id']) if any(str(t.get('mark', '')).upper() == mark for lv in r.get('beams') or [] for t in lv.get('types') or [])]
    if used:
        raise bad_request(f'Type {mark} is printed on run #{used[0]["serial"]}', f'النموذج {mark} مطبوع على الإصدار #{used[0]["serial"]}')
    with STORE.lock:
        p['beam_types'] = [t for t in p.get('beam_types') or [] if str(t.get('mark', '')).upper() != mark]
        STORE.save()
    return {'beam_types': p['beam_types']}


@route('POST', '/api/projects/:id/files')
def api_file_upload(h, m):
    p = load_project(m['id'])
    category = one_of(h.query.get('category'), FILE_CATEGORIES)
    name = s(h.query.get('name'), 200, 'file')
    fid = STORE.new_id()
    safe = re.sub(r'[^A-Za-z0-9._-]+', '_', os.path.basename(name))
    path = project_dir(p['id']) / 'files' / f'{fid}_{safe}'
    size = h.save_upload(path)
    level_id = num(h.query.get('level_id'))
    with STORE.lock:
        f = {'id': fid, 'project_id': p['id'], 'category': category, 'name': name, 'file': path.name, 'bytes': size, 'level_id': level_id,
             'level_code': (STORE.get('levels', level_id) or {}).get('code') if level_id else None, 'revision': s(h.query.get('revision'), 12), 'note': s(h.query.get('note'), 500),
             'created_at': now_iso(), 'uploaded_by_name': drawing_settings().get('designer')}
        STORE.table('files').append(f)
        STORE.save()
    return {'file': f}


@route('GET', '/api/files/:id')
def api_file_get(h, m):
    f = STORE.get('files', int(m['id']))
    if not f:
        raise not_found('File not found', 'الملف مش موجود')
    return h.send_file(project_dir(f['project_id']) / 'files' / f['file'], 'application/octet-stream', f['name'])


@route('DELETE', '/api/files/:id')
def api_file_delete(h, m):
    f = STORE.get('files', int(m['id']))
    if not f:
        raise not_found('File not found', 'الملف مش موجود')
    (project_dir(f['project_id']) / 'files' / f['file']).unlink(missing_ok=True)
    with STORE.lock:
        STORE.remove('files', lambda x: x['id'] == f['id'])
        STORE.save()
    return {'ok': True}


# --------------------------------------------------------------------------------------------- submittals
def html_esc(v):
    return str('' if v is None else v).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#39;')


def submittal_code(prefix, project_code, serial, revision=0):
    """`SPAN-SUB-P26-001-003` (+ `-R1` when the same submittal is re-issued)."""
    return f"{prefix}-{project_code}-{int(serial):03d}{('-R' + str(revision)) if revision else ''}"


def project_submittals(pid):
    return sorted([x for x in STORE.table('submittals') if x['project_id'] == pid], key=lambda x: -x['serial'])


def load_submittal(sid):
    x = STORE.get('submittals', int(sid))
    if not x:
        raise not_found('Submittal not found', 'طلب الاعتماد مش موجود')
    return x


def submittal_items(runs, only=None, previous=None):
    """
    The items of a submittal from the runs picked: every plan sheet of each run (the cover / index sheet is not a
    drawing to approve), or only the sheet numbers listed in `only`. Each item names the earlier submittal and
    revision of the same drawing number when there was one, so the form says what it supersedes.
    """
    items, seen = [], set()
    for run in runs:
        for sh in run.get('sheets') or []:
            if sh.get('level') == 'ALL' and re.search(r'COVER|INDEX', sh.get('title') or '', re.I):
                continue
            if only and sh['no'] not in only:
                continue
            if sh['no'] in seen:
                continue
            seen.add(sh['no'])
            item = {'run_id': run['id'], 'mode': run['mode'], 'level': sh.get('level'), 'level_name': sh.get('level_name') or run.get('level_name') or '', 'no': sh['no'], 'title': sh['title'], 'rev': run['revision'], 'file': sh.get('file'), 'scale': sh.get('scale') or None}
            prior = sorted([{'code': p['code'], 'rev': it['rev'], 'status': p['status'], 'date': p['date']} for p in (previous or []) for it in (p.get('items') or []) if it['no'] == sh['no']], key=lambda x: x['date'] or '', reverse=True)
            if prior:
                item.update({'prev_rev': prior[0]['rev'], 'prev_submittal': prior[0]['code'], 'prev_status': prior[0]['status']})
            items.append(item)
    return items


def submittal_html(submittal, project, settings, items):
    """The printable form (A4, prints from the browser): office header, project block, the drawing list, the response boxes."""
    tpl = settings.get('submittal') or {}
    S = submittal
    e = html_esc
    purpose = PURPOSE_LABELS.get(S.get('purpose'), S.get('purpose'))
    status = STATUS_LABELS.get(S.get('status'), S.get('status'))
    def row_of(i, it):
        level = 'ALL' if it.get('level') == 'ALL' else str(it.get('level')) + ((' - ' + it['level_name']) if it.get('level_name') else '')
        prev = (e(it.get('prev_rev')) + ' <span class="tiny">(' + e(it.get('prev_submittal')) + ')</span>') if it.get('prev_rev') is not None else '-'
        scale = ('1:' + e(it['scale'])) if it.get('scale') else 'NTS'
        return ('<tr><td class="c">' + str(i + 1) + '</td><td class="mono">' + e(it.get('no')) + '</td><td>' + e(it.get('title')) + '</td><td class="mono">' + e(level) + '</td>'
                '<td class="c mono">' + e(it.get('rev')) + '</td><td class="c mono">' + prev + '</td><td class="c">' + scale + '</td><td class="resp"></td></tr>')
    rows = ''.join(row_of(i, it) for i, it in enumerate(items))
    responses = ''.join(f'<label><span class="box"></span> {e(r)}</label>' for r in (tpl.get('responses') or []))
    signatures = ''.join(f'<div class="sig"><div class="line"></div><div>{e(sg)}</div><div class="tiny">NAME / SIGN / DATE</div></div>' for sg in (tpl.get('signatures') or []))
    kinds = {'shop': 'SHOP DRAWINGS', 'design': 'DESIGN DRAWINGS', 'mixed': 'DESIGN AND SHOP DRAWINGS'}
    response = (f'<table class="meta"><tr><td class="k">RESPONSE</td><td>{e(S.get("response_notes"))}</td><td class="k">DATE / BY</td><td>{e(S.get("response_date"))} {e(S.get("response_by"))}</td></tr></table>'
                if S.get('response_notes') or S.get('response_date') else '')
    notes = f'<div class="intro"><b>NOTES:</b> {e(S.get("notes"))}</div>' if S.get('notes') else ''
    designer = settings.get('designer') or ''
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>' + e(S.get('code')) + ' - ' + e(tpl.get('title') or 'SUBMITTAL') + '</title>\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n<style>\n'
            '  @page { size: A4; margin: 12mm; }\n'
            '  body { font: 11px/1.4 Arial, Helvetica, sans-serif; color: #111; margin: 0; padding: 12mm; max-width: 190mm; }\n'
            '  .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0b3d6b; padding-bottom: 6px; }\n'
            '  .head .co { font-size: 18px; font-weight: 700; color: #0b3d6b; letter-spacing: .5px; }\n  .head .line { font-size: 10px; color: #555; }\n  .head .no { text-align: right; }\n'
            '  .head .no .code { font-family: Consolas, Menlo, monospace; font-size: 16px; font-weight: 700; }\n'
            '  h1 { font-size: 15px; margin: 10px 0 2px; color: #0b3d6b; }\n  h1 small { display: block; font-size: 11px; color: #555; font-weight: 400; }\n'
            '  table.meta { width: 100%; border-collapse: collapse; margin: 8px 0; }\n  table.meta td { border: 1px solid #999; padding: 4px 6px; vertical-align: top; }\n'
            '  table.meta td.k { width: 18%; background: #eef3f8; font-weight: 700; }\n  table.list { width: 100%; border-collapse: collapse; margin-top: 6px; }\n'
            '  table.list th, table.list td { border: 1px solid #666; padding: 4px 5px; text-align: left; }\n  table.list th { background: #0b3d6b; color: #fff; font-weight: 700; font-size: 10px; }\n'
            '  .c { text-align: center !important; }\n  .mono { font-family: Consolas, Menlo, monospace; }\n  .tiny { font-size: 9px; color: #555; }\n  .resp { width: 22mm; }\n  .intro { margin: 8px 0; }\n'
            '  .responses { display: flex; flex-wrap: wrap; gap: 10px 22px; margin: 10px 0; padding: 8px; border: 1px solid #666; }\n'
            '  .responses label { display: inline-flex; align-items: center; gap: 6px; font-weight: 700; }\n  .box { display: inline-block; width: 12px; height: 12px; border: 1.5px solid #111; }\n'
            '  .sigs { display: flex; gap: 14px; margin-top: 14px; }\n  .sig { flex: 1; text-align: center; font-weight: 700; }\n  .sig .line { height: 34px; border-bottom: 1px solid #111; margin-bottom: 4px; }\n'
            '  .foot { margin-top: 12px; font-size: 9px; color: #555; border-top: 1px solid #999; padding-top: 6px; }\n'
            '  .status { display: inline-block; padding: 2px 8px; border: 1.5px solid #0b3d6b; border-radius: 3px; font-weight: 700; color: #0b3d6b; }\n'
            '  .print { position: fixed; top: 8px; right: 8px; padding: 6px 12px; font: 12px Arial; }\n  @media print { .print { display: none; } body { padding: 0; } }\n'
            '</style></head>\n<body>\n<button class="print" onclick="window.print()">Print / PDF</button>\n'
            '<div class="head">\n  <div><div class="co">' + e(settings.get('company')) + '</div><div class="line">' + e(settings.get('company_line')) + ((' · ' + e(tpl['contact'])) if tpl.get('contact') else '') + '</div></div>\n'
            '  <div class="no"><div class="tiny">SUBMITTAL No.</div><div class="code">' + e(S.get('code')) + '</div><div class="tiny">DATE ' + e(S.get('date')) + '</div></div>\n</div>\n'
            '<h1>' + e(tpl.get('title') or 'DRAWING SUBMITTAL') + '<small>' + e(tpl.get('title_ar')) + '</small></h1>\n<table class="meta">\n'
            '  <tr><td class="k">PROJECT</td><td>' + e(project.get('name')) + ((' · ' + e(project['name_ar'])) if project.get('name_ar') else '') + ' <span class="mono">(' + e(project.get('code')) + ')</span></td><td class="k">STATUS</td><td><span class="status">' + e(status) + '</span></td></tr>\n'
            '  <tr><td class="k">TO</td><td>' + e(S.get('to_name') or project.get('consultant')) + '</td><td class="k">ATTENTION</td><td>' + e(S.get('attention')) + '</td></tr>\n'
            '  <tr><td class="k">CLIENT</td><td>' + e(project.get('client')) + '</td><td class="k">CONTRACTOR</td><td>' + e(project.get('contractor')) + '</td></tr>\n'
            '  <tr><td class="k">LOCATION</td><td>' + e(project.get('location')) + '</td><td class="k">PURPOSE</td><td>' + e(purpose) + ' · ' + e(kinds.get(S.get('kind'), S.get('kind'))) + '</td></tr>\n'
            '  <tr><td class="k">SUBJECT</td><td colspan="3">' + e(S.get('subject')) + '</td></tr>\n</table>\n'
            '<div class="intro">' + e(tpl.get('intro')) + '</div>\n<table class="list">\n'
            '  <thead><tr><th class="c">#</th><th>DRAWING No.</th><th>TITLE</th><th>LEVEL</th><th class="c">REV</th><th class="c">SUPERSEDES REV</th><th class="c">SCALE</th><th class="c">ACTION</th></tr></thead>\n'
            '  <tbody>' + (rows or '<tr><td colspan="8" class="c">NO DRAWINGS</td></tr>') + '</tbody>\n</table>\n'
            '<div class="tiny" style="margin-top:4px">' + str(len(items)) + ' DRAWING(S). ACTION CODES: A = APPROVED · B = APPROVED AS NOTED · C = REVISE AND RESUBMIT · D = REJECTED.</div>\n'
            + notes + '<div class="responses">' + responses + '</div>\n' + response +
            '<div class="sigs">' + signatures + '<div class="sig"><div class="line"></div><div>RECEIVED BY (CONSULTANT)</div><div class="tiny">NAME / SIGN / DATE</div></div></div>\n'
            '<div class="foot">' + e(tpl.get('footer')) + ((' · Prepared in ' + e(settings.get('company')) + ' PT Suite by ' + e(designer)) if designer else '') + '</div>\n</body></html>')


@route('GET', '/api/projects/:id/submittals')
def api_submittals(h, m):
    return {'submittals': project_submittals(load_project(m['id'])['id'])}


@route('POST', '/api/projects/:id/submittals')
def api_submittal_create(h, m):
    p = load_project(m['id'])
    body = h.json_body()
    settings = drawing_settings()
    run_ids = [int(v) for v in (body.get('run_ids') if isinstance(body.get('run_ids'), list) else []) if str(v).isdigit()]
    if not run_ids:
        raise bad_request('Pick at least one drawing run', 'اختار إصدار لوحات واحد على الأقل')
    runs = [public_run(load_run(i)) for i in run_ids]
    if any(r['project_id'] != p['id'] for r in runs):
        raise bad_request('A run of another project was picked', 'فيه إصدار من مشروع تاني')
    if any(r['status'] in ('failed', 'running') for r in runs):
        raise bad_request('A run without drawings was picked', 'فيه إصدار مطلعش لوحات')
    if any(r['status'] == 'blocked' for r in runs):
        raise bad_request('A run blocked by the punching / beam check cannot be submitted', 'فيه إصدار متوقف بسبب البانشنج أو الكمرات: مينفعش يتقدم قبل قرار المهندس')
    only = [str(v) for v in body['sheets']] if isinstance(body.get('sheets'), list) and body['sheets'] else None
    previous = sorted([x for x in project_submittals(p['id']) if x['status'] != 'withdrawn'], key=lambda x: x['serial'])
    items = submittal_items(runs, only, previous)
    if not items:
        raise bad_request('No drawings to submit', 'مفيش لوحات تتقدم')
    modes = set(r['mode'] for r in runs)
    kind = 'mixed' if len(modes) > 1 else runs[0]['mode']
    resub = any(it.get('prev_rev') is not None for it in items)
    levels = list(dict.fromkeys(str(it['level']) for it in items))
    with STORE.lock:
        serial = STORE.counter(f"drawing_submittals:{p['id']}")
        sub = {
            'id': STORE.new_id(), 'project_id': p['id'], 'serial': serial, 'code': submittal_code(settings['submittal'].get('prefix') or 'SPAN-SUB', p['code'], serial), 'revision': 0, 'kind': kind,
            'subject': s(body.get('subject'), 300) or f"{'DESIGN' if kind == 'design' else 'SHOP' if kind == 'shop' else 'DESIGN AND SHOP'} DRAWINGS - {', '.join(levels)}{' (RE-SUBMISSION)' if resub else ''}",
            'to_name': s(body.get('to_name')) or p.get('consultant') or None, 'attention': s(body.get('attention')),
            'purpose': one_of(body.get('purpose'), SUBMITTAL_PURPOSES, fallback='resubmission' if resub else 'approval'),
            'date': s(body.get('date'), 10) or today(), 'items': items, 'notes': s(body.get('notes'), 4000), 'status': 'draft',
            'created_at': now_iso(), 'created_by_name': settings.get('designer') or None,
        }
        STORE.table('submittals').append(sub)
        STORE.save()
    return {'submittal': sub}


@route('GET', '/api/submittals/:id')
def api_submittal(h, m):
    x = load_submittal(m['id'])
    return {'submittal': x, 'project': public_project(load_project(x['project_id']))}


@route('GET', '/api/submittals/:id/form')
def api_submittal_form(h, m):
    x = load_submittal(m['id'])
    h.send_html(submittal_html(x, public_project(load_project(x['project_id'])), drawing_settings(), x.get('items') or []))
    return None


@route('PATCH', '/api/submittals/:id')
def api_submittal_update(h, m):
    x = load_submittal(m['id'])
    body = h.json_body()
    settings = drawing_settings()
    p = load_project(x['project_id'])
    with STORE.lock:
        for k, mx in (('subject', 300), ('to_name', 200), ('attention', 200), ('notes', 4000), ('date', 10), ('response_date', 10), ('response_notes', 4000), ('response_by', 200)):
            if k in body:
                x[k] = s(body.get(k), mx)
        if body.get('purpose') is not None:
            x['purpose'] = one_of(body['purpose'], SUBMITTAL_PURPOSES)
        if body.get('status') is not None:
            x['status'] = one_of(body['status'], SUBMITTAL_STATUS)
        # re-issuing the same submittal (a correction before the consultant answers) bumps its own revision: -R1, -R2 ...
        if body.get('reissue'):
            x['revision'] = (x.get('revision') or 0) + 1
            x['code'] = submittal_code(settings['submittal'].get('prefix') or 'SPAN-SUB', p['code'], x['serial'], x['revision'])
            x['status'] = 'draft'
        STORE.save()
    return {'submittal': x}


@route('DELETE', '/api/submittals/:id')
def api_submittal_delete(h, m):
    x = load_submittal(m['id'])
    with STORE.lock:
        STORE.remove('submittals', lambda y: y['id'] == x['id'])
        STORE.save()
    return {'ok': True}


# ----------------------------------------------------------------------------------------- the HTTP layer
class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = f'SpanTechDrawings/{VERSION}'

    def log_message(self, fmt, *args):  # quiet, one line per request
        if '--verbose' in sys.argv:
            sys.stderr.write('%s - %s\n' % (self.address_string(), fmt % args))

    # ---- helpers the routes use
    @property
    def content_length(self):
        return int(self.headers.get('Content-Length') or 0)

    def json_body(self):
        n = self.content_length
        if n > 20 * 1024 * 1024:
            raise bad_request('Body too large', 'الطلب أكبر من اللازم')
        raw = self.rfile.read(n) if n else b''
        if not raw:
            return {}
        try:
            return json.loads(raw.decode('utf8'))
        except Exception:
            raise bad_request('Malformed JSON body', 'الطلب مش JSON صحيح')

    def save_upload(self, path):
        """The raw request body streamed to `path` (the file name travels in the query, as in the CRM)."""
        n = self.content_length
        if n > MAX_UPLOAD:
            raise bad_request(f'That file is {n / 1048576:.1f} MB; the limit is {MAX_UPLOAD // 1048576} MB.', f'الملف {n / 1048576:.1f} ميجا، والحد الأقصى {MAX_UPLOAD // 1048576} ميجا.')
        if not n:
            raise bad_request('The file was empty.', 'الملف فاضي.')
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        left = n
        with open(path, 'wb') as f:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            path.unlink(missing_ok=True)
            raise bad_request('The upload stopped early', 'الرفع اتقطع')
        return n

    def send_file(self, path, ctype, download_name=None):
        path = Path(path)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        if download_name:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(download_name))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)
        return None

    def send_json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False, default=_json_default).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def send_html(self, html):
        data = html.encode('utf8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    # ---- dispatch
    def dispatch(self, method):
        parsed = urllib.parse.urlsplit(self.path)
        self.query = {k: v[-1] for k, v in urllib.parse.parse_qs(parsed.query, keep_blank_values=True).items()}
        path = parsed.path
        if method == 'GET' and path in ('/', '/index.html'):
            return self.send_html(PAGE)
        if method == 'GET' and path == '/favicon.ico':
            self.send_response(204)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return None
        for m, rx, fn in ROUTES:
            if m != method:
                continue
            match = rx.match(path)
            if not match:
                continue
            try:
                out = fn(self, match.groupdict())
            except ApiError as e:
                return self.send_json(e.status, {'error': e.message, 'error_ar': e.message_ar})
            except Exception as e:
                traceback.print_exc()
                return self.send_json(500, {'error': str(e) or e.__class__.__name__, 'error_ar': str(e) or e.__class__.__name__})
            if out is not None:
                return self.send_json(200, out)
            return None
        return self.send_json(404, {'error': f'No route {method} {path}', 'error_ar': 'المسار مش موجود'})

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def do_PUT(self):
        self.dispatch('PUT')

    def do_PATCH(self):
        self.dispatch('PATCH')

    def do_DELETE(self):
        self.dispatch('DELETE')


def _json_default(o):
    if isinstance(o, float) and (o != o or o in (float('inf'), float('-inf'))):
        return None
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    return str(o)


def main(argv=None):
    global STORE, DATA
    ap = argparse.ArgumentParser(description='Span Tech drawings - the Python generator with the CRM drawings screens, in one file')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PYDRAWINGS_PORT') or 8765))
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--data', default=os.environ.get('PYDRAWINGS_DATA') or str(HERE / 'data'))
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args(argv)
    DATA = Path(a.data).resolve()
    STORE = Store(DATA)
    (DATA / 'tmp').mkdir(parents=True, exist_ok=True)
    port = a.port
    server = None
    for attempt in range(20):
        try:
            server = ThreadingHTTPServer((a.host, port), Handler)
            break
        except OSError:
            port += 1
    if server is None:
        print('No free port found', file=sys.stderr)
        return 1
    server.daemon_threads = True
    url = f'http://{a.host}:{port}/'
    print(f'Span Tech drawings {VERSION} - {url}')
    print(f'  data: {DATA}')
    print('  Ctrl+C stops the app')
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# ==============================================================================================================
# the page: the CRM Drawings module (design system, strings and screens) on the local API above
# ==============================================================================================================
PAGE = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a2647">
<title>Span Tech · لوحات التسليح</title>
<link rel="icon" href="">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap" media="print" onload="this.media='all'">
<style>
/* Span Tech CRM design system (app.css), the parts the Drawings module uses */
:root{--brand-900:#0a2647;--brand-800:#103d7a;--brand-700:#1a56a7;--brand-600:#2670c9;--brand-500:#3d8bdd;--brand-100:#e3eefb;--brand-50:#f2f7fd;--accent-600:#c9761a;--accent-100:#fdf1e2;--ok-700:#14683f;--ok-600:#178553;--ok-100:#e3f5ec;--warn-700:#8a5a00;--warn-100:#fdf3dc;--danger-700:#a32020;--danger-600:#c62828;--danger-100:#fdeaea;--ink-900:#111827;--ink-700:#374151;--ink-500:#6b7280;--ink-400:#9ca3af;--ink-300:#d1d5db;--ink-200:#e5e7eb;--ink-100:#f3f4f6;--ink-50:#f9fafb;--white:#fff;--radius:10px;--radius-sm:6px;--radius-lg:16px;--shadow-sm:0 1px 2px rgba(16,24,40,.06),0 1px 3px rgba(16,24,40,.1);--shadow-md:0 4px 8px -2px rgba(16,24,40,.1),0 2px 4px -2px rgba(16,24,40,.06);--shadow-lg:0 12px 16px -4px rgba(16,24,40,.08),0 4px 6px -2px rgba(16,24,40,.03);--sidebar-w:248px;--header-h:60px;--font-ar:'Cairo','Tajawal','Segoe UI','Noto Naskh Arabic','Traditional Arabic',Tahoma,sans-serif;--font-en:'Inter','Segoe UI',system-ui,-apple-system,'Helvetica Neue',Arial,sans-serif}
:root[dir='rtl']{--font:var(--font-ar)}:root[dir='ltr']{--font:var(--font-en)}
*,*::before,*::after{box-sizing:border-box}html,body{height:100%}
body{margin:0;font-family:var(--font);font-size:14px;line-height:1.6;color:var(--ink-900);background:var(--ink-50);-webkit-font-smoothing:antialiased}
.num,td.num,th.num,input[type='number']{font-variant-numeric:tabular-nums;font-feature-settings:'tnum';direction:ltr;unicode-bidi:plaintext}
h1,h2,h3,h4{margin:0 0 .5rem;font-weight:700;line-height:1.3;color:var(--ink-900)}h1{font-size:1.5rem}h2{font-size:1.2rem}h3{font-size:1.02rem}h4{font-size:.92rem}
p{margin:0 0 .75rem}a{color:var(--brand-700);text-decoration:none}a:hover{text-decoration:underline}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.45rem;padding:.5rem .9rem;border:1px solid transparent;border-radius:var(--radius-sm);background:var(--brand-700);color:var(--white);font-family:inherit;font-size:.875rem;font-weight:600;line-height:1.2;cursor:pointer;white-space:nowrap;transition:background .15s,box-shadow .15s,opacity .15s}
.btn:hover{background:var(--brand-800)}.btn:active{transform:translateY(1px)}.btn:disabled{opacity:.5;cursor:not-allowed}
.btn-secondary{background:var(--white);color:var(--ink-700);border-color:var(--ink-300)}.btn-secondary:hover{background:var(--ink-100)}
.btn-ghost{background:transparent;color:var(--brand-700)}.btn-ghost:hover{background:var(--brand-50)}
.btn-danger{background:var(--danger-600)}.btn-danger:hover{background:var(--danger-700)}.btn-success{background:var(--ok-700)}
.btn-sm{padding:.3rem .6rem;font-size:.8rem}.btn-lg{padding:.65rem 1.3rem;font-size:.95rem}.btn-block{width:100%}.btn-icon{padding:.35rem;width:30px;height:30px}
.field{margin-bottom:.85rem}.field>label{display:block;margin-bottom:.28rem;font-size:.8rem;font-weight:600;color:var(--ink-700)}.field .hint{margin-top:.22rem;font-size:.74rem;color:var(--ink-500)}
input[type='text'],input[type='search'],input[type='number'],input[type='date'],select,textarea{width:100%;padding:.48rem .65rem;border:1px solid var(--ink-300);border-radius:var(--radius-sm);background:var(--white);color:var(--ink-900);font-family:inherit;font-size:.875rem;line-height:1.5;transition:border-color .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{outline:none;border-color:var(--brand-500);box-shadow:0 0 0 3px var(--brand-100)}
input:disabled,select:disabled,textarea:disabled{background:var(--ink-100);color:var(--ink-500)}textarea{min-height:76px;resize:vertical}select{cursor:pointer}
.checkbox{display:flex;align-items:center;gap:.45rem;cursor:pointer;font-size:.85rem}.checkbox input{width:16px;height:16px;accent-color:var(--brand-700);cursor:pointer}
.grid{display:grid;gap:.85rem}.grid-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid-4{grid-template-columns:repeat(4,minmax(0,1fr))}
@media (max-width:900px){.grid-3,.grid-4{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:640px){.grid-2,.grid-3,.grid-4{grid-template-columns:1fr}}
.app{display:flex;min-height:100vh}
.sidebar{position:fixed;inset-block:0;inset-inline-start:0;width:var(--sidebar-w);z-index:40;display:flex;flex-direction:column;background:var(--brand-900);color:#cdd9e9;transition:transform .2s ease}
.sidebar-brand{display:flex;align-items:center;gap:.6rem;padding:1rem 1.1rem;border-bottom:1px solid rgba(255,255,255,.08)}
.sidebar-brand img{height:40px;width:40px;padding:3px;flex-shrink:0;object-fit:contain;background:var(--white);border-radius:8px}
.sidebar-brand .name{font-size:1rem;font-weight:700;color:var(--white);letter-spacing:.01em}.sidebar-brand .sub{font-size:.7rem;color:#8fa6c4}
.sidebar-nav{flex:1;padding:.7rem .6rem;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:.65rem;padding:.55rem .7rem;margin-bottom:.15rem;border-radius:var(--radius-sm);color:#cdd9e9;font-size:.875rem;font-weight:500;cursor:pointer;transition:background .15s,color .15s}
.nav-item:hover{background:rgba(255,255,255,.07);color:var(--white);text-decoration:none}.nav-item.active{background:var(--brand-700);color:var(--white);font-weight:600}.nav-item svg{width:18px;height:18px;flex-shrink:0}
.sidebar-footer{padding:.7rem;border-top:1px solid rgba(255,255,255,.08);font-size:.78rem}.sidebar-user{display:flex;align-items:center;gap:.55rem;padding:.4rem .3rem}
.avatar{display:grid;place-items:center;flex-shrink:0;width:32px;height:32px;border-radius:50%;background:var(--brand-600);color:var(--white);font-size:.8rem;font-weight:700}
.sidebar-user .who{min-width:0}.sidebar-user .who b{display:block;color:var(--white);font-size:.82rem;font-weight:600}.sidebar-user .who span{color:#8fa6c4;font-size:.72rem;word-break:break-all}
.main{flex:1;min-width:0;margin-inline-start:var(--sidebar-w)}
.topbar{position:sticky;top:0;z-index:30;display:flex;align-items:center;gap:.75rem;height:var(--header-h);padding:0 1.2rem;background:var(--white);border-bottom:1px solid var(--ink-200)}
.topbar h1{margin:0;font-size:1.15rem}.topbar-actions{margin-inline-start:auto;display:flex;align-items:center;gap:.5rem}.menu-toggle{display:none}
.lang-switch{display:inline-flex;border:1px solid var(--ink-300);border-radius:var(--radius-sm);overflow:hidden}
.lang-switch button{padding:.3rem .6rem;border:0;background:var(--white);color:var(--ink-700);font-family:inherit;font-size:.78rem;font-weight:600;cursor:pointer}.lang-switch button.active{background:var(--brand-700);color:var(--white)}
.content{padding:1.2rem;max-width:1560px}
@media (max-width:1024px){.sidebar{transform:translateX(calc(var(--sidebar-w) * -1))}:root[dir='rtl'] .sidebar{transform:translateX(var(--sidebar-w))}.sidebar.open{transform:translateX(0)}.main{margin-inline-start:0}.menu-toggle{display:inline-flex}.content{padding:.9rem}}
.scrim{position:fixed;inset:0;z-index:35;background:rgba(17,24,39,.45)}
.card{background:var(--white);border:1px solid var(--ink-200);border-radius:var(--radius);box-shadow:var(--shadow-sm);margin-bottom:1rem}
.card-header{display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;padding:.8rem 1rem;border-bottom:1px solid var(--ink-200)}.card-header h2,.card-header h3{margin:0}.card-header .spacer{margin-inline-start:auto}
.card-body{padding:1rem}.card-body.tight{padding:.6rem}.card-body.flush{padding:0}
.kpi-grid{display:grid;gap:.8rem;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));margin-bottom:1rem}
.kpi{padding:.9rem 1rem;background:var(--white);border:1px solid var(--ink-200);border-radius:var(--radius);box-shadow:var(--shadow-sm);border-inline-start:3px solid var(--brand-600)}
.kpi .label{font-size:.76rem;font-weight:600;color:var(--ink-500);text-transform:uppercase;letter-spacing:.03em}.kpi .value{margin-top:.25rem;font-size:1.55rem;font-weight:700;color:var(--ink-900);line-height:1.2;overflow:hidden;text-overflow:ellipsis}.kpi .meta{margin-top:.1rem;font-size:.76rem;color:var(--ink-500)}
.kpi.ok{border-inline-start-color:var(--ok-700)}.kpi.warn{border-inline-start-color:var(--warn-700)}.kpi.danger{border-inline-start-color:var(--danger-600)}.kpi.accent{border-inline-start-color:var(--accent-600)}
.table-wrap{overflow-x:auto}table.data{width:100%;border-collapse:collapse;font-size:.85rem}
table.data th{padding:.6rem .7rem;background:var(--ink-50);border-bottom:1px solid var(--ink-200);font-size:.74rem;font-weight:700;color:var(--ink-500);text-transform:uppercase;letter-spacing:.03em;text-align:start;white-space:nowrap}
table.data td{padding:.6rem .7rem;border-bottom:1px solid var(--ink-100);vertical-align:middle}table.data tbody tr:hover{background:var(--brand-50)}table.data tbody tr.clickable{cursor:pointer}
table.data td.num,table.data th.num{text-align:end}table.data .muted{color:var(--ink-500);font-size:.8rem}table.data tfoot td{padding:.6rem .7rem;font-weight:700;border-top:2px solid var(--ink-200)}
.empty{padding:2.5rem 1rem;text-align:center;color:var(--ink-400)}.empty svg{width:40px;height:40px;margin-bottom:.5rem;opacity:.45}
.badge{display:inline-flex;align-items:center;gap:.3rem;padding:.15rem .5rem;border-radius:999px;font-size:.73rem;font-weight:600;white-space:nowrap;background:var(--ink-100);color:var(--ink-700)}
.badge.blue{background:var(--brand-100);color:var(--brand-800)}.badge.green{background:var(--ok-100);color:var(--ok-700)}.badge.amber{background:var(--warn-100);color:var(--warn-700)}.badge.red{background:var(--danger-100);color:var(--danger-700)}.badge.orange{background:var(--accent-100);color:var(--accent-600)}.badge.grey{background:var(--ink-100);color:var(--ink-500)}
.toolbar{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;margin-bottom:.85rem}.toolbar .search-box{position:relative;flex:1;min-width:190px;max-width:340px}.toolbar .search-box input{padding-inline-start:2rem}
.toolbar .search-box svg{position:absolute;inset-block-start:50%;inset-inline-start:.55rem;width:15px;height:15px;transform:translateY(-50%);color:var(--ink-400);pointer-events:none}.toolbar select{width:auto;min-width:120px}.toolbar .spacer{margin-inline-start:auto}
.modal-backdrop{position:fixed;inset:0;z-index:60;display:flex;align-items:flex-start;justify-content:center;padding:2.5rem 1rem;overflow-y:auto;background:rgba(17,24,39,.55)}
.modal{width:100%;max-width:620px;background:var(--white);border-radius:var(--radius-lg);box-shadow:var(--shadow-lg);animation:pop .16s ease-out}.modal.wide{max-width:980px}.modal.narrow{max-width:420px}
@keyframes pop{from{opacity:0;transform:translateY(-8px) scale(.99)}}
.modal-header{display:flex;align-items:center;gap:.6rem;padding:.9rem 1.1rem;border-bottom:1px solid var(--ink-200)}.modal-header h2{margin:0;font-size:1.05rem}
.modal-header .close{margin-inline-start:auto;width:30px;height:30px;border:0;border-radius:var(--radius-sm);background:transparent;color:var(--ink-500);font-size:1.3rem;line-height:1;cursor:pointer}.modal-header .close:hover{background:var(--ink-100)}
.modal-body{padding:1.1rem;max-height:68vh;overflow-y:auto}.modal-footer{display:flex;gap:.5rem;justify-content:flex-end;padding:.85rem 1.1rem;border-top:1px solid var(--ink-200);background:var(--ink-50);border-radius:0 0 var(--radius-lg) var(--radius-lg)}
.toasts{position:fixed;z-index:90;inset-block-end:1.2rem;inset-inline-end:1.2rem;display:flex;flex-direction:column;gap:.5rem;max-width:380px}
.toast{display:flex;align-items:flex-start;gap:.55rem;padding:.7rem .9rem;border-radius:var(--radius);background:var(--ink-900);color:var(--white);font-size:.85rem;box-shadow:var(--shadow-lg);animation:slide-in .18s ease-out}.toast.success{background:var(--ok-700)}.toast.error{background:var(--danger-700)}
@keyframes slide-in{from{opacity:0;transform:translateY(8px)}}
.alert{padding:.6rem .8rem;border-radius:var(--radius-sm);font-size:.82rem;font-weight:600;margin-bottom:.7rem}.alert.danger{background:var(--danger-100);color:var(--danger-700)}.alert.warn{background:var(--warn-100);color:var(--warn-700)}.alert.ok{background:var(--ok-100);color:var(--ok-700)}.alert.info{background:var(--brand-100);color:var(--brand-800)}
.row{display:flex;align-items:center;gap:.5rem}.row.wrap{flex-wrap:wrap}.spacer{margin-inline-start:auto}.muted{color:var(--ink-500)}.small{font-size:.8rem}.tiny{font-size:.73rem}.bold{font-weight:700}.center{text-align:center}.end{text-align:end}.nowrap{white-space:nowrap}
.mt-0{margin-top:0}.mt-1{margin-top:.5rem}.mt-2{margin-top:1rem}.mb-0{margin-bottom:0}.mb-1{margin-bottom:.5rem}.mb-2{margin-bottom:1rem}.hidden{display:none !important}.text-danger{color:var(--danger-700)}
.detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:.8rem}.detail-item .k{font-size:.73rem;font-weight:600;color:var(--ink-500);text-transform:uppercase;letter-spacing:.03em}.detail-item .v{font-size:.9rem;font-weight:500}
.tabs{display:flex;gap:.2rem;border-bottom:1px solid var(--ink-200);margin-bottom:1rem;overflow-x:auto}
.tabs button{padding:.55rem .9rem;border:0;border-bottom:2px solid transparent;background:transparent;color:var(--ink-500);font-family:inherit;font-size:.87rem;font-weight:600;cursor:pointer;white-space:nowrap}.tabs button:hover{color:var(--brand-700)}.tabs button.active{color:var(--brand-700);border-bottom-color:var(--brand-700)}
.spinner{width:16px;height:16px;border:2px solid rgba(255,255,255,.35);border-top-color:var(--white);border-radius:50%;animation:spin .6s linear infinite;display:inline-block}.spinner.dark{border-color:rgba(16,24,40,.2);border-top-color:var(--brand-700)}
@keyframes spin{to{transform:rotate(360deg)}}.loading-page{display:grid;place-items:center;min-height:60vh;color:var(--ink-400)}
.busy{position:fixed;inset:0;z-index:80;display:grid;place-items:center;background:rgba(255,255,255,.7);backdrop-filter:blur(1px)}.busy .box{display:flex;align-items:center;gap:.8rem;padding:1rem 1.4rem;background:var(--white);border:1px solid var(--ink-200);border-radius:var(--radius);box-shadow:var(--shadow-lg);font-weight:600}
pre.report{font-family:var(--font-en);font-size:.78rem;white-space:pre-wrap;margin:0;max-height:420px;overflow:auto;direction:ltr;text-align:left}
.help ol,.help ul{padding-inline-start:1.3rem}.help code{font-family:Consolas,Menlo,monospace;font-size:.82rem;background:var(--ink-100);padding:.05rem .3rem;border-radius:4px;direction:ltr;unicode-bidi:embed}
.help pre{direction:ltr;text-align:left;background:var(--ink-900);color:#e5e7eb;padding:.7rem .9rem;border-radius:var(--radius-sm);font-size:.8rem;overflow:auto}
@media print{.sidebar,.topbar,.toolbar,.no-print{display:none !important}.main{margin:0 !important}body{background:var(--white)}}
</style>
</head>
<body>
<div id="root"><div class="loading-page">…</div></div>
<script>
'use strict';
const ICON_B64 = 'iVBORw0KGgoAAAANSUhEUgAAAQAAAAEACAYAAABccqhmAACe6UlEQVR42uz9ebxd2VUein5jzLnWbk6nvq++kS2VC2MZN0lAMuaCAUOAmyPSEUMIMolD8uD9EhKSm1MnJORyCSHEgCk984xNbBMd3OHCrnJXJXflplQuu0qqvkolVemo1J9u773WnHOM+8eca+19JJPk5vFwVXkNfkYqSeecffZZc8wxvvF93wCaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmiiiSaaaKKJJppoookmmmjihRLUvAUv6Z+nNm9JE/+94OYteFEe8iv+d+DAgQwAYe9e8z/5c738czTRRBMvtiQwPT1tZmZmLAC86y1o6/AwN4e6iSZewgnA7DlwIAOmDQB84JNf+uH/NPeNY//mdz/ywbvvvrt9+c2uqnTo0CHT3PhNNC3ASyAOHLidjxw86N756xPd9338gbfffzJ8+FP3X3p5z27+cd/tXg1Ap6cPcfoZMxHp/v37AwCdmZmhb9IGNNEkgCZe6DEzM8MzM3ebgwff6u646+5XXrjqp977paflH3/+2GmzsvCcZE6DL/MMAM6cOUp79uwxAOi3/+APNt7zhQe/CwDPzs7Km970plb6+dPIr018G5aSTby4fl4KAO+762v/+vF5+VcPPHmpff78os/bll3f8Wt3b5Uf2pPfsu/1ex7ec+BAduTg7V71HvMr/+bkn80/f+n7b7xmzX/7+bfefGDDhtctTk8fMsAc5ubmpOoUmrf42yts8xa8WEJJFZh759y6sOMV/+mrTy+95cjjp0BiQidvWSdegzJKJ7ywUmYAsAfAERCAu7HS62/4xCe/ro9etfknnz8/uPX2d37oV976D378w7GdOJAdPHjQN+9x0wI0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+AfpxY1NvA0REREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREREb98+L/DHD4cktdZbAAAAABJRU5ErkJggg==';
document.querySelector('link[rel=icon]').href = `data:image/png;base64,${ICON_B64}`;
// ----------------------------------------------------------------------------------------------------- i18n
const DICT = {"ar":{"app_name":"سبان تك","loading":"بيحمّل…","search":"دوّر","all":"الكل","save":"حفظ","cancel":"إلغاء","close":"إقفال","delete":"مسح","edit":"تعديل","open":"افتح","back":"رجوع","actions":"إجراءات","saved":"اتحفظ ✓","deleted":"اتمسح","error":"حصل خطأ","none":"مفيش","yes":"أيوه","no":"لأ","nothing_here":"مفيش حاجة هنا","status":"الحالة","owner":"المهندس المسؤول","notes":"ملاحظات","settings":"الإعدادات","reset_defaults":"رجّع الافتراضي","dw_title":"لوحات التسليح من الرام","dw_projects":"المشاريع","dw_project":"المشروع","dw_new_project":"مشروع جديد","dw_edit_project":"تعديل بيانات المشروع","dw_project_hint":"سجّل بيانات المشروع مرة واحدة — كل لوحة تتطلع بعد كده هتاخد نفس البيانات في الكارت (الاسم، العميل، الاستشاري، المقاول، الموقع، التوقيعات).","dw_code":"كود المشروع","dw_code_hint":"سيبه فاضي وهيتولّد أوتوماتيك (مثال P26-001)","dw_name":"اسم المشروع (إنجليزي — اللي هيتكتب على اللوحة)","dw_name_ar":"اسم المشروع (عربي)","dw_client":"العميل / المالك","dw_consultant":"الاستشاري","dw_contractor":"المقاول الرئيسي","dw_location":"الموقع","dw_prepared":"أعدّه","dw_checked":"راجعه","dw_approved":"اعتمده","dw_signatures_hint":"لو سيبتهم فاضيين هيتاخدوا من إعدادات اللوحات.","dw_default_mode":"نوع اللوحات الافتراضي","dw_ram_bands":"حديد الرام","dw_mode_design":"لوحات تصميم (Design)","dw_mode_shop":"شوب درونج (Shop)","dw_bands_all":"كل الحديد من الرام (يدوي + بروجرام)","dw_bands_user":"حديد المصمم بس (بدون حديد البروجرام)","dw_bands_none":"قواعد المكتب بس (بدون حديد الرام)","dw_notes":"ملاحظات","dw_spec":"تعديلات المواصفات (JSON — اختياري)","dw_levels":"الأدوار / الزونات","dw_level":"الدور","dw_new_level":"زوّد دور","dw_edit_level":"تعديل الدور","dw_level_code":"كود الدور","dw_level_code_hint":"بيدخل في رقم اللوحة: B1، GF، L03 …","dw_level_name":"اسم الدور (زي ما هيتكتب على اللوحة)","dw_zone":"الزون (اختياري)","dw_wall_thickness":"سمك الحوائط (مم)","dw_wall_thickness_hint":"لو الرام مفيهوش سمك للحوائط","dw_sort_order":"الترتيب","dw_no_levels":"لسه مفيش أدوار متسجلة — زوّد الأدوار الأول وبعدين ارفع ملف الرام لكل دور.","dw_runs":"الإصدارات","dw_run":"إصدار","dw_no_runs":"لسه مفيش لوحات متطلعة للمشروع ده.","dw_generate":"اطلع اللوحات","dw_generate_for":"اطلع لوحات","dw_file":"ملف الرام (.cpt) أو المسقط (.dxf)","dw_revision":"المراجعة (Rev)","dw_revision_hint":"سيبه فاضي وهيتحسب أوتوماتيك (00 ثم 01 …)","dw_generating":"بيرفع الملف وبيطلع اللوحات… ممكن ياخد دقيقة.","dw_generated":"اللوحات اتطلعت ✓","dw_serial":"السيريال","dw_mode":"النوع","dw_sheets":"اللوحات","dw_sheet_no":"رقم اللوحة","dw_sheet_title":"عنوان اللوحة","dw_scale":"المقياس","dw_weight":"الوزن (كجم)","dw_takeoff_update":"تحديث الحصر من DXF معدّل","dw_takeoff_hint":"عدّلت اللوحة في الأوتوكاد (Stretch لسيخ، تغيير القطر أو التوزيع في الكتابة)؟ ارفع الـ DXF المعدّل والبرنامج يلاقي كل سيخ بعلامته ويحدّث حصر الحديد بالفرق.","dw_takeoff_updated":"اتحدّث الحصر: {changed} سيخ متغيّر من {bars}، الفرق {kg} كجم","dw_download_zip":"تحميل الباكدج (ZIP)","dw_download_dxf":"DXF","dw_preview":"معاينة","dw_assumptions":"الافتراضات المكتوبة على اللوحات","dw_findings":"اللي اتقرا من الموديل","dw_report":"التقرير","dw_source":"الملف المرفوع","dw_duration":"زمن الإخراج","dw_status_done":"جاهز","dw_status_failed":"فشل","dw_status_running":"شغال","dw_by":"بواسطة","dw_date":"التاريخ","dw_last_run":"آخر إصدار","dw_last_rev":"آخر مراجعة","dw_delete_project_confirm":"هتمسح المشروع بكل أدواره وكل اللوحات المتطلعة له. متأكد؟","dw_delete_level_confirm":"هتمسح الدور وكل اللوحات المتطلعة له. متأكد؟","dw_delete_run_confirm":"هتمسح الإصدار ده وملفاته. متأكد؟","dw_numbering":"ترقيم اللوحات","dw_numbering_hint":"رقم اللوحة = البادئة - كود المشروع - كود الدور - رقم اللوحة، مثال: SPAN-DD-P26-001-B1-02","dw_settings":"إعدادات اللوحات","dw_project_prefix":"بادئة كود المشروع","dw_design_prefix":"بادئة لوحات التصميم","dw_shop_prefix":"بادئة الشوب درونج","dw_company":"اسم الشركة على الكارت","dw_company_line":"السطر تحت اسم الشركة","dw_status_design":"حالة لوحات التصميم","dw_status_shop":"حالة الشوب درونج","dw_workflow":"خطوات العمل","dw_open_workflow":"افتح دليل خطوات العمل","dw_open_file_workflow":"Workflow ملف الرام (من الاستلام للتسليم)","dw_step1":"١- سجّل المشروع (مرة واحدة).","dw_step2":"٢- زوّد الأدوار / الزونات بأكوادها.","dw_step3":"٣- ارفع ملف الرام لكل دور واطلع اللوحات.","dw_step4":"٤- حمّل الباكدج وراجع الافتراضات المكتوبة على اللوحات.","dw_search":"دوّر بالاسم أو الكود أو العميل","dw_tab_levels":"الأدوار والإصدارات","dw_tab_files":"ملفات المشروع","dw_tab_history":"سجل المراجعات","dw_files_design":"ملفات التصميم الأصلية","dw_files_ram":"ملفات الرام","dw_files_pt_design":"مخططات البوست تنشن التصميمية","dw_files_pt_shop":"مخططات البوست تنشن التنفيذية (شوب درونج)","dw_files_hint":"كل ملفات المشروع في مكان واحد: المخططات الأصلية (معماري / إنشائي)، موديلات الرام، ومخططات البوست تنشن التصميمية والتنفيذية. الباكدجات المتطلعة من البرنامج بتظهر هنا أوتوماتيك.","dw_upload_file":"ارفع ملف","dw_file_name":"الملف","dw_file_note":"ملاحظة","dw_file_rev":"المراجعة","dw_file_size":"الحجم","dw_file_by":"رفعه","dw_file_category":"القسم","dw_no_files":"مفيش ملفات في القسم ده","dw_delete_file_confirm":"هتمسح الملف ده. متأكد؟","dw_generated_package":"باكدج متطلع من البرنامج","dw_run_notes":"وصف التعديل / ملاحظات الإصدار","dw_run_notes_hint":"اكتب إيه اللي اتغير في الموديل أو المخططات عن المراجعة اللي قبلها","dw_run_status":"حالة الإصدار","dw_status_draft":"مسودة","dw_status_issued":"صادر","dw_status_superseded":"ملغي (استُبدل)","dw_status_blocked":"متوقف — بانشنج","dw_rotate":"اتجاه المخطط على اللوحة","dw_rotate_auto":"تلقائي (لف 90° لو المخطط أطول من عرضه)","dw_rotate_0":"زي ما هو (بدون لف)","dw_rotate_90":"لف 90°","dw_rotate_hint":"لو المخطط مش هيكفي اللوحة بالعرض، البرنامج يلفه 90 درجة عشان طوله يبقى على طول اللوحة (وسهم الشمال يلف معاه). ممكن تجبره على 0 أو 90.","dw_mesh":"شبكة البلاطة","dw_mesh_bottom":"شبكة سفلية بس","dw_mesh_both":"شبكة علوية وسفلية","dw_mesh_hint":"الشبكة اللي بتتكتب على لوحات التصميم وبتدخل في حصر الحديد.","dw_ram_failed":"أعمدة مش مسيّفة بانشنج في الرام","dw_ram_failed_hint":"اكتب أرقام الأعمدة زي ما هي على لوحة الفريمنج (A/1, B/3 …) — البرنامج مش بيقدر يقرا نتيجة البانشنج من ملف الرام، فلازم تكتبها بنفسك. كل عمود هنا بيوقف الإصدار لحد ما تاخد قرار.","dw_punch_title":"تنبيه بانشنج — الإصدار متوقف","dw_punch_blocked":"فيه أعمدة مش مسيّفة بانشنج ({n}): {cols}. الإصدار ده مينفعش يتعتمد ولا يتقدم في طلب اعتماد قبل قرار المهندس المصمم.","dw_punch_warn":"أعمدة محتاجة مراجعة في تقرير البانشنج بتاع الرام (تقدير البرنامج بيقول محتاجة تسليح بانشنج والرام معملش لها stud rails): {cols}","dw_punch_hint":"الرام مش بيخزّن نتيجة البانشنج في الملف. البرنامج بيعمل تقدير استرشادي (SBC 304 / ACI 318 على مساحات التوزيع والأحمال من الموديل) وبيعتمد على الأعمدة اللي كتبتها إنها مش مسيّفة في الرام. تقرير البانشنج بتاع الرام هو المرجع.","dw_punch_col":"عمود","dw_punch_loc":"الموقع","dw_punch_trib":"مساحة التوزيع (م²)","dw_punch_vu":"Vu (kN)","dw_punch_ratio":"vu / φvc","dw_punch_status":"التقدير","dw_punch_ok":"مسيّف","dw_punch_reinforce":"محتاج تسليح بانشنج","dw_punch_fail":"مش مسيّف حتى بالكانات","dw_punch_in_ram":"مش مسيّف في الرام (حسب المهندس)","dw_punch_ssr":"stud rails في الرام","dw_punch_loc_interior":"داخلي","dw_punch_loc_edge":"طرفي","dw_punch_loc_corner":"ركني","dw_punch_thicken":"هزوّد سمك الدروب / البلاطة","dw_punch_thicken_hint":"الإصدار يفضل متوقف. عدّل الموديل في الرام (دروب أو سمك أكبر في المنطقة دي) وارفعه إصدار جديد.","dw_punch_ram_ok":"الأعمدة دي مسيّفة في تقرير الرام","dw_punch_ram_ok_hint":"تقدير البرنامج كان متحفظ. بإقرارك إن تقرير البانشنج بتاع الرام بيسيّف الأعمدة دي هيتعاد الإخراج من غير تسليح بانشنج عندها.","dw_punch_bypass":"أتخطى المشكلة على مسؤوليتي","dw_punch_bypass_hint":"هيتحط تسليح بانشنج (PS) عند الأعمدة دي من تقدير البرنامج، وهيتكتب على اللوحات إنه على مسؤولية المهندس المصمم باسمك والتاريخ.","dw_punch_ack":"أقر إني المهندس المصمم المسؤول عن القرار ده وإن اسمي هيتكتب على اللوحات","dw_punch_note":"سبب القرار (اختياري — بيتكتب في الافتراضات على اللوحة)","dw_punch_columns":"الأعمدة اللي القرار بيغطيها","dw_punch_all_flagged":"كل الأعمدة المعلّمة","dw_punch_decided":"القرار: {mode} — {by}، {date}","dw_punch_clear":"ألغي القرار","dw_punch_mode_thicken":"زيادة السمك","dw_punch_mode_bypass":"تخطّي على مسؤولية المهندس","dw_punch_mode_ram_ok":"مسيّف في الرام","dw_punch_regenerated":"اتعاد الإخراج بالقرار","dw_designer":"المهندس المصمم (اللي طلّع الإصدار)","dw_designer_hint":"اسم المستخدم اللي طلّع الإصدار بيتكتب في خانة PREPARED / DESIGNED BY على كل لوحة.","dw_mesh_kg":"وزن الشبكة (كجم)","dw_beam_design":"تصميم الكمرات","dw_bd_ram":"حديد الرام (شرائح التصميم)","dw_bd_office":"تصميم المكتب (تحليل المومنت والشير)","dw_bd_max":"الأكبر في القيمتين (الرام أو تصميم المكتب)","dw_bd_hint":"تصميم المكتب: كل كمرة بتتحلل كمرة مستمرة على ركائزها بأحمال البلاطة اللي شايلاها (الوزن الذاتي + أحمال الموديل، 1.2D + 1.6L مع تبديل الحي)، وبيتصمم حديدها وكاناتها وبيتفحص الدفلكشن (SBC 304 / ACI 318). الرام مش بيخزّن القوى في الملف، فالتحليل من البرنامج وتقرير الرام هو المرجع.","dw_ram_failed_beams":"كمرات مش مسيّفة دفلكشن في الرام","dw_ram_failed_beams_hint":"أرقام الكمرات زي ما هي على لوحة الكمرات (BM1, BM3 …). كل كمرة هنا بتوقف الإصدار لحد ما تاخد قرار.","dw_beam_check":"فحص الكمرات (تصميم المكتب)","dw_beam_check_title":"تنبيه الكمرات — الإصدار متوقف","dw_beam_blocked":"فيه كمرات مش مسيّفة ({n}): {beams}. الإصدار ده مينفعش يتعتمد ولا يتقدم قبل قرار المهندس المصمم.","dw_beam_forces":"القوى والتصميم","dw_beam_spans":"البحور (م)","dw_beam_trib":"عرض التحميل (م)","dw_beam_wu":"wu (kN/m)","dw_beam_mneg":"Mu- (kN·m)","dw_beam_mpos":"Mu+ (kN·m)","dw_beam_vu":"Vu (kN)","dw_beam_defl":"الدفلكشن","dw_beam_defl_table":"مسيّف بالسمك/البحر","dw_beam_defl_ratio":"{r} من الحد","dw_beam_status":"الحالة","dw_beam_ok":"مسيّفة","dw_beam_fail":"مش مسيّفة","dw_beam_reason_deflection":"دفلكشن","dw_beam_reason_flexure":"القطاع مش شايل المومنت","dw_beam_reason_shear":"القطاع مش شايل الشير","dw_beam_in_ram":"مش مسيّفة في الرام (حسب المهندس)","dw_beam_no_supports":"مفيش ركائز اتلقت على الكمرة (اتحسبت بحر واحد)","dw_beam_ram_bars":"حديد الرام","dw_beam_office_bars":"تصميم المكتب","dw_beam_chosen":"المرسوم","dw_beam_deepen":"هزوّد عمق الكمرة","dw_beam_deepen_hint":"الإصدار يفضل متوقف. عدّل الكمرة في الرام وارفع الموديل إصدار جديد.","dw_beam_ram_ok":"الكمرات دي مسيّفة في تقرير الرام","dw_beam_ram_ok_hint":"تقدير البرنامج كان متحفظ. بإقرارك إن تقرير الرام بيسيّف الكمرات دي هيتعاد الإخراج بنفس المراجعة.","dw_beam_bypass":"أتخطى على مسؤوليتي","dw_beam_bypass_hint":"هيتعاد الإخراج زي ما هو، ومكتوب على لوحة الكمرات إن الكمرات دي مش مسيّفة ومقبولة على مسؤولية المهندس المصمم باسمك والتاريخ.","dw_beam_columns":"الكمرات اللي القرار بيغطيها","dw_beam_mode_deepen":"زيادة العمق","dw_beam_mode_bypass":"تخطّي على مسؤولية المهندس","dw_beam_mode_ram_ok":"مسيّفة في الرام","dw_issue":"اعتمد كإصدار صادر","dw_issue_confirm":"هيتعلّم الإصدار ده \"صادر\" وأي إصدار صادر قبله لنفس الدور هيبقى ملغي. تمام؟","dw_history":"سجل المراجعات","dw_history_hint":"كل إصدار لكل دور: المراجعة، الحالة، إيه اللي اتغير، وفرق وزن الحديد عن اللي قبله.","dw_weight_t":"حديد علوي (كجم)","dw_weight_b":"حديد سفلي (كجم)","dw_delta":"الفرق","dw_save_notes":"احفظ الملاحظات","dw_files_multi":"ملفات الرام (ممكن تختار أكتر من ملف)","dw_files_map_hint":"كل ملف بيتربط بدور: البرنامج بيقترح الدور من اسم الملف وتقدر تغيّره.","dw_batch_progress":"بيطلع {n} من {total}…","dw_batch_done":"خلص: {ok} نجح، {fail} فشل","dw_file_level":"الدور لكل ملف","dw_edit_rebar":"عدّل التسليح","dw_editor":"محرر التسليح","dw_editor_hint":"اضغط على سيخ عشان تختاره (Shift لأكتر من سيخ). عدّل الطول أو المواصفة أو امسحه أو زوّد سيخ جديد، ثم احفظ التعديلات وأعد الإخراج عشان تطلع مراجعة جديدة بالتعديلات.","dw_selected":"مختار","dw_delete_bars":"امسح","dw_extend_start":"البداية","dw_extend_end":"النهاية","dw_apply_length":"طبّق","dw_new_spec":"مواصفة جديدة (مثال T16-150 (T))","dw_add_bar":"زوّد سيخ","dw_add_bar_hint":"اضغط نقطة البداية ثم نقطة النهاية على المسقط","dw_pan":"تحريك","dw_select":"اختيار","dw_fit":"ملء الشاشة","dw_edits_pending":"تعديلات لسه ما اتحفظتش","dw_edits_list":"التعديلات المحفوظة على الدور","dw_save_edits":"احفظ التعديلات","dw_regenerate":"أعد الإخراج بالتعديلات","dw_clear_edits":"امسح كل التعديلات","dw_edits_saved":"التعديلات اتحفظت ✓","dw_regenerated":"الإصدار الجديد اتطلع ✓","dw_face_t":"علوي (T)","dw_face_b":"سفلي (B)","dw_show_top":"العلوي","dw_show_bottom":"السفلي","dw_frame":"فريم اللوحة (الباندا حوالين اللوحة)","dw_frame_hint":"مقاسات الشريط الأيمن والصناديق بالملليمتر على الورق (A1). ممكن تقفل صناديق (الكي بلان، المراجع، الجدول، شريط التفاصيل) والمساحة بتروح للملاحظات.","dw_frame_size":"مقاس الورقة","dw_frame_right":"عرض الشريط الأيمن","dw_frame_bottom":"ارتفاع شريط التفاصيل","dw_frame_title":"ارتفاع كارت اللوحة","dw_frame_refs":"ارتفاع المراجع والمراجعات","dw_frame_key":"ارتفاع الكي بلان","dw_frame_sched":"ارتفاع الجدول","dw_frame_keyplan":"كي بلان","dw_frame_refsbox":"المراجع والمراجعات","dw_frame_schedule":"الجدول","dw_frame_details":"شريط التفاصيل","dw_rebar_defaults":"افتراضيات حديد التسليح","dw_rebar_defaults_hint":"القطر والتوزيع والطول اللي البرنامج بيكتبهم على اللوحات لو مفيش قيمة من الرام أو المشروع: حديد الأعمدة العلوي (مجموعتين فوق كل عمود بالطول المكتوب أو طول الدروب)، حديد الدروبات (تفصيلة 4: شبكة الدروب السفلية بأرجل)، الشبكة السفلية، والشبكة العلوية (لما تختار شبكة على الوجهين). كمان أطوال الـ U-Bar: سيخ الداير على الحافة الحرة، وسيخ البورستريب الداخلي، وسيخ البورستريب جنب الحائط الساند (اللي جوه الحائط واللي من ناحية البلاطة)، والحديد العلوي والسفلي العابر للبورستريب. كلها قابلة للتعديل هنا ولكل مشروع من خانة تعديلات المواصفات.","dw_rd_columns":"حديد الأعمدة العلوي","dw_rd_drops":"حديد الدروبات","dw_rd_bottom":"الشبكة السفلية","dw_rd_top":"الشبكة العلوية","dw_rd_dia":"القطر (مم)","dw_rd_spacing":"التوزيع (مم)","dw_rd_length":"الطول (مم)","dw_rd_leg":"الرجل (مم)","dw_rd_utotal":"طول السيخ الكلي (مم)","dw_rd_uedge":"U-Bar الداير (الحافة الحرة)","dw_rd_pstrip":"U-Bar البورستريب","dw_rd_pstrip_tb":"البورستريب - حديد علوي وسفلي عابر","dw_rd_pstrip_wall":"U-Bar البورستريب جوه الحائط الساند","dw_rd_pstrip_slab":"U-Bar البورستريب من ناحية البلاطة (عند الحائط)","dw_frame_dxf":"فريم المكتب (DXF)","dw_frame_dxf_hint":"ارفع فريم المكتب كملف DXF مرسوم بالملليمتر على الورق (A1: 841×594، الأصل في الركن الأسفل الأيسر). اكتب في نصوصه رموز زي <PROJECT> <CLIENT> <CONSULTANT> <CONTRACTOR> <LOCATION> <TITLE> <LEVEL> <DRAWING_NO> <REV> <DATE> <SCALE> <SHEET> <PREPARED> <CHECKED> <APPROVED> <STATUS> <PROJECT_CODE> <COMPANY> وهتتملي أوتوماتيك في كل لوحة. الفريم ده بيحل محل الفريم والكارت المدمجين.","dw_frame_upload":"ارفع فريم DXF","dw_frame_remove":"شيل الفريم","dw_frame_current":"الفريم الحالي","dw_frame_none":"مفيش فريم مرفوع — بيتستخدم الفريم المدمج","dw_tab_submittals":"طلبات الاعتماد","dw_tab_quantities":"الحصر والتكلفة","dw_tab_beam_types":"جدول الكمرات","dw_bt_hint":"جدول نماذج الكمرات موحّد على مستوى المشروع: أي إصدار لأي دور بيستخدم النماذج اللي هنا زي ما هي؛ الكمرة اللي مفيش نموذج بيسيّفها بتاخد نموذج جديد بيتضاف هنا، والنماذج الموجودة ماتتعدلش أبداً.","dw_bt_empty":"لسه مفيش نماذج كمرات في المشروع: هتتضاف أوتوماتيك مع أول إصدار فيه كمرات متصممة، أو استدعي جدول مشروع سابق.","dw_bt_import":"استدعاء جدول مشروع سابق","dw_bt_from":"المشروع","dw_bt_import_hint":"نماذج المشروع المختار بتتضاف لجدول المشروع ده (المكرر بيتجاهل، والرقم المكرر بياخد رقم جديد).","dw_bt_imported":"اتضاف {added} نموذج ({skipped} مكرر اتجاهل)","dw_bt_source":"المصدر","dw_bt_source_run":"إصدار {run} · {level} REV {rev}","dw_bt_source_import":"مستدعى من {code}","dw_bt_new":"جديد في الإصدار ده","dw_bt_existing":"من جدول المشروع","dw_bt_delete_confirm":"هتمسح النموذج ده من جدول المشروع (مينفعش لو مكتوب على لوحات إصدار). متأكد؟","dw_bt_added_on_run":"نماذج اتضافت لجدول المشروع من الإصدار ده: {marks}","dw_reference":"المخطط المرجعي (أعمدة / محاور / حدود البلاطة)","dw_reference_short":"مخطط مرجعي","dw_beams":"تصميم الكمرات","dw_beams_hint":"الخطوة الأولى: البرنامج بياخد موديل الرام بتاع الإصدار ده، يمسح كل الـ design strips اللي فيه، ويرسم strip على سنتر لاين كل كمرة (شريحة لكل بحر بين ركائزها) وsplitter على كل حرف من حروفها، بتصميم \"كمرة\". حمّل الموديل الجاهز، افتحه في الرام، اعمل Calc All واحفظه. الخطوة التانية: ارفع الموديل المحسوب كإصدار جديد للدور: الكمرات هتطلع مقسّمة نماذج (B1, B2 …) ومكتوب على كل كمرة نموذجها وقطاعها، وجدول التسليح والقطاعات على لوحة الكمرات.","dw_beams_prepare":"جهّز موديل الرام بشرائح الكمرات","dw_beams_download":"حمّل الموديل (.cpt)","dw_beams_prepared":"الموديل جاهز: {beams} كمرة، {spans} بحر، {splitters} splitter — {removed} شريحة قديمة اتشالت","dw_beams_none":"الإصدار ده مفيهوش كمرات متصممة في الرام لسه.","dw_beams_types":"نماذج الكمرات","dw_beam_type":"النموذج","dw_beam_section":"القطاع b×h","dw_beam_top":"حديد علوي (ركائز)","dw_beam_bottom":"حديد سفلي (بحر)","dw_beam_stirrups":"كانات","dw_beam_count":"العدد","dw_beam_list":"الكمرات","dw_beams_undesigned":"كمرات من غير تصميم في الرام","dw_reference_hint":"ارفع مخطط الدور من المعماري أو الإنشائي كملف DXF (اطلع الـ DWG بـ DXFOUT) فيه المحاور بفقاعاتها والأعمدة وحدود البلاطة. اللوحات هتستخدم محاور المشروع وأعمدته وحدوده بدل اللي في الرام. البرنامج بيطابق المخطط على موديل الرام أوتوماتيك بمطابقة الأعمدة (أي إزاحة، ودوران 0/90/180/270)، أو حدد نقطة موحدة بنفسك: إحداثياتها في المخطط وإحداثياتها في الرام (تقاطع محورين أو ركن عمود).","dw_reference_upload":"ارفع DXF","dw_reference_none":"مفيش مخطط مرجعي — بتتاخد المحاور والأعمدة والحدود من الرام","dw_reference_current":"المخطط الحالي","dw_reference_remove":"شيل المخطط","dw_reference_found":"اللي اتقرا من المخطط","dw_reference_columns":"أعمدة","dw_reference_outlines":"حدود بلاطة","dw_reference_grid":"المحاور","dw_reference_grid_derived":"المخطط مفيهوش فقاعات محاور — المحاور هتتستنتج من الأعمدة","dw_reference_use":"استخدم من المخطط","dw_use_grid":"المحاور","dw_use_columns":"الأعمدة","dw_use_outline":"حدود البلاطة","dw_reference_align":"طريقة التوفيق","dw_align_auto":"أوتوماتيك — مطابقة الأعمدة","dw_align_point":"نقطة موحدة أحددها","dw_align_dxf":"إحداثيات النقطة في المخطط (مم)","dw_align_ram":"إحداثيات نفس النقطة في الرام (مم)","dw_align_rot":"دوران المخطط","dw_align_x":"X","dw_align_y":"Y","dw_reference_saved":"المخطط المرجعي اتحفظ ✓ — هيتستخدم في الإصدار الجاي","dw_delete_reference_confirm":"هتشيل المخطط المرجعي من الدور. متأكد؟","dw_submittals_hint":"طلب الاعتماد (Submittal / Transmittal) بيتعمل من الإصدارات اللي تختارها: أرقام اللوحات وأسماءها ومراجعاتها بتتكتب فيه أوتوماتيك من كارت اللوحة، ورقمه متسلسل على مستوى المشروع (SPAN-SUB-P26-001-001). لو لوحة اتعدلت واتقدمت تاني، الطلب الجديد بيكتب المراجعة اللي حل محلها ورقم الطلب القديم. النموذج موحد لكل الشركة من إعدادات اللوحات.","dw_new_submittal":"طلب اعتماد جديد","dw_submittal":"طلب اعتماد","dw_submittal_no":"رقم الطلب","dw_submittal_to":"إلى (الاستشاري)","dw_submittal_attention":"عناية","dw_submittal_subject":"الموضوع","dw_submittal_purpose":"الغرض","dw_purpose_approval":"للاعتماد","dw_purpose_information":"للعلم","dw_purpose_resubmission":"إعادة تقديم","dw_purpose_as_built":"حسب التنفيذ (As built)","dw_submittal_runs":"الإصدارات اللي هتتقدم","dw_submittal_sheets":"اللوحات","dw_submittal_all_sheets":"كل لوحات الإصدار","dw_submittal_items":"عدد اللوحات","dw_submittal_date":"تاريخ التقديم","dw_submittal_open_form":"افتح النموذج (طباعة / PDF)","dw_submittal_mark":"غيّر الحالة","dw_submittal_response":"رد الاستشاري","dw_submittal_response_date":"تاريخ الرد","dw_submittal_response_by":"الرد من","dw_submittal_reissue":"أعد إصدار النموذج (R+1)","dw_submittal_supersedes":"بيحل محل","dw_no_submittals":"مفيش طلبات اعتماد لسه","dw_delete_submittal_confirm":"هتمسح طلب الاعتماد ده. متأكد؟","dw_sstatus_draft":"مسودة","dw_sstatus_submitted":"مُقدَّم","dw_sstatus_approved":"معتمد","dw_sstatus_approved_as_noted":"معتمد بملاحظات","dw_sstatus_resubmit":"يُعاد التقديم","dw_sstatus_rejected":"مرفوض","dw_sstatus_withdrawn":"مسحوب","dw_submittal_template":"نموذج طلب الاعتماد (موحد للشركة)","dw_submittal_template_hint":"النموذج ده بيتطبع لكل طلب اعتماد في كل المشاريع: البادئة، العنوان، المقدمة، صناديق الرد، خطوط التوقيع والتذييل. غيّره هنا مرة واحدة ويتغيّر في كل مكان.","dw_sub_prefix":"بادئة رقم الطلب","dw_sub_title":"عنوان النموذج","dw_sub_title_ar":"العنوان بالعربي","dw_sub_intro":"المقدمة","dw_sub_responses":"صناديق الرد (سطر لكل صندوق)","dw_sub_signatures":"خطوط التوقيع (سطر لكل توقيع)","dw_sub_footer":"التذييل","dw_sub_contact":"بيانات الاتصال في الترويسة","dw_quantities_hint":"الحصر بيتحسب من نفس الموديل والجداول اللي اتطلعت منها اللوحات: الحديد من جداول التسليح، الخرسانة من مسقط البلاطة (بعد خصم الفتحات، مع زيادة الدروبات والكمرات)، والكابلات من كابلات الرام. لكل دور بيتاخد الإصدار الصادر (أو آخر مسودة).","dw_qty_steel":"حديد التسليح","dw_qty_concrete":"الخرسانة","dw_qty_cables":"الكابلات (البوست تنشن)","dw_qty_by_dia":"حسب القطر","dw_qty_total_m":"الطول (م)","dw_qty_kg":"الوزن (كجم)","dw_qty_count":"العدد","dw_qty_top":"علوي","dw_qty_bottom":"سفلي","dw_qty_other":"أخرى","dw_qty_gross":"المساحة الكلية (م²)","dw_qty_openings":"الفتحات (م²)","dw_qty_net":"المساحة الصافية (م²)","dw_qty_thk":"السمك (مم)","dw_qty_slab":"البلاطة (م³)","dw_qty_drops":"الدروبات (م³)","dw_qty_beams":"الكمرات (م³)","dw_qty_total_m3":"إجمالي الخرسانة (م³)","dw_qty_formwork":"الشدات (م²)","dw_qty_tendons":"الكابلات","dw_qty_strands":"الخيوط","dw_qty_tendon_m":"طول الكابلات (م)","dw_qty_strand_m":"طول الخيوط (م)","dw_qty_cutting_m":"طول القص (م)","dw_qty_strand_kg":"وزن الخيوط (كجم)","dw_qty_live":"مراسي حية","dw_qty_dead":"مراسي ميتة","dw_qty_duct_small":"داكت 20×50 (م)","dw_qty_duct_large":"داكت 20×70 (م)","dw_qty_kg_m2":"كجم/م²","dw_qty_source":"الإصدار المستخدم","dw_no_quantities":"مفيش حصر لسه — اطلع لوحات لدور واحد على الأقل.","dw_export_csv":"تصدير CSV","dw_qty_totals":"الإجمالي","dw_cost":"دراسة التكلفة","dw_cost_hint":"الحصر × أسعار الوحدة من الإعدادات (تقدر تغيّرها هنا كتجربة من غير ما تحفظ). الأسعار الرسمية للشركة في إعدادات اللوحات.","dw_cost_item":"البند","dw_cost_unit":"الوحدة","dw_cost_qty":"الكمية","dw_cost_rate":"سعر الوحدة","dw_cost_amount":"القيمة","dw_cost_steel":"حديد تسليح (توريد)","dw_cost_rebar_labour":"حديد تسليح (تصنيع وتركيب)","dw_cost_concrete":"خرسانة","dw_cost_formwork":"شدات","dw_cost_strand":"خيوط (استراند)","dw_cost_anchor_live":"مراسي حية","dw_cost_anchor_dead":"مراسي ميتة","dw_cost_duct":"داكت","dw_cost_pt_labour":"عمالة البوست تنشن","dw_cost_direct":"التكلفة المباشرة","dw_cost_markup":"مصاريف وربح","dw_cost_vat":"ضريبة القيمة المضافة","dw_cost_total":"الإجمالي","dw_cost_per_m2":"التكلفة/م²","dw_cost_apply":"أعد الحساب","dw_rates":"أسعار الوحدة (دراسة التكلفة)","dw_rates_hint":"أسعار الشركة الافتراضية لدراسة التكلفة، بعملة واحدة.","dw_rate_currency":"العملة","dw_rate_steel_per_ton":"حديد (لكل طن)","dw_rate_rebar_labour_per_ton":"تصنيع وتركيب الحديد (لكل طن)","dw_rate_concrete_per_m3":"خرسانة (لكل م³)","dw_rate_formwork_per_m2":"شدات (لكل م²)","dw_rate_strand_per_kg":"استراند (لكل كجم)","dw_rate_anchor_live":"مرساة حية (للواحدة)","dw_rate_anchor_dead":"مرساة ميتة (للواحدة)","dw_rate_duct_per_m":"داكت (لكل م)","dw_rate_pt_labour_per_m2":"عمالة البوست تنشن (لكل م²)","dw_rate_markup_pct":"مصاريف وربح %","dw_rate_vat_pct":"ضريبة القيمة المضافة %"},"en":{"app_name":"Span Tech","loading":"Loading…","search":"Search","all":"All","save":"Save","cancel":"Cancel","close":"Close","delete":"Delete","edit":"Edit","open":"Open","back":"Back","actions":"Actions","saved":"Saved","deleted":"Deleted","error":"Something went wrong","none":"None","yes":"Yes","no":"No","nothing_here":"Nothing here","status":"Status","owner":"Account engineer","notes":"Notes","settings":"Settings","reset_defaults":"Restore defaults","dw_title":"Reinforcement drawings from RAM","dw_projects":"Projects","dw_project":"Project","dw_new_project":"New project","dw_edit_project":"Edit project data","dw_project_hint":"Register the project once — every drawing generated afterwards carries the same title-block data (name, client, consultant, contractor, location, signatures).","dw_code":"Project code","dw_code_hint":"Leave empty to number it automatically (e.g. P26-001)","dw_name":"Project name (English — as printed on the sheets)","dw_name_ar":"Project name (Arabic)","dw_client":"Client / owner","dw_consultant":"Consultant","dw_contractor":"Main contractor","dw_location":"Location","dw_prepared":"Prepared by","dw_checked":"Checked by","dw_approved":"Approved by","dw_signatures_hint":"Left empty, these come from the drawings settings.","dw_default_mode":"Default drawing type","dw_ram_bands":"RAM reinforcement","dw_mode_design":"Design drawings","dw_mode_shop":"Shop drawings","dw_bands_all":"All RAM bands (user + program)","dw_bands_user":"Designer bands only (no program bands)","dw_bands_none":"Office rules only (no RAM bands)","dw_notes":"Notes","dw_spec":"Specification overrides (JSON — optional)","dw_levels":"Levels / zones","dw_level":"Level","dw_new_level":"Add level","dw_edit_level":"Edit level","dw_level_code":"Level code","dw_level_code_hint":"Goes into the drawing number: B1, GF, L03 …","dw_level_name":"Level name (as printed on the sheets)","dw_zone":"Zone (optional)","dw_wall_thickness":"Wall thickness (mm)","dw_wall_thickness_hint":"When the RAM model carries no wall thickness","dw_sort_order":"Order","dw_no_levels":"No levels registered yet — add the levels first, then upload the RAM file for each one.","dw_runs":"Runs","dw_run":"Run","dw_no_runs":"No drawings generated for this project yet.","dw_generate":"Generate drawings","dw_generate_for":"Generate for","dw_file":"RAM model (.cpt) or plan (.dxf)","dw_revision":"Revision","dw_revision_hint":"Leave empty to number it automatically (00, then 01 …)","dw_generating":"Uploading the file and generating the sheets… this can take a minute.","dw_generated":"Drawings generated ✓","dw_serial":"Serial","dw_mode":"Type","dw_sheets":"Sheets","dw_sheet_no":"Drawing No.","dw_sheet_title":"Title","dw_scale":"Scale","dw_weight":"Weight (kg)","dw_takeoff_update":"Update take-off from edited DXF","dw_takeoff_hint":"Edited the sheet in AutoCAD (stretched a bar, changed a diameter or spacing in its call-out)? Upload the edited DXF: every bar is found by its tag and the steel take-off moves by the difference.","dw_takeoff_updated":"Take-off updated: {changed} bars changed of {bars}, difference {kg} kg","dw_download_zip":"Download package (ZIP)","dw_download_dxf":"DXF","dw_preview":"Preview","dw_assumptions":"Assumptions printed on the sheets","dw_findings":"Read from the model","dw_report":"Report","dw_source":"Uploaded file","dw_duration":"Generation time","dw_status_done":"Ready","dw_status_failed":"Failed","dw_status_running":"Running","dw_by":"By","dw_date":"Date","dw_last_run":"Last run","dw_last_rev":"Last revision","dw_delete_project_confirm":"This deletes the project, its levels and every drawing generated for it. Continue?","dw_delete_level_confirm":"This deletes the level and every drawing generated for it. Continue?","dw_delete_run_confirm":"This deletes this run and its files. Continue?","dw_numbering":"Sheet numbering","dw_numbering_hint":"Drawing No. = prefix - project code - level code - sheet, e.g. SPAN-DD-P26-001-B1-02","dw_settings":"Drawings settings","dw_project_prefix":"Project code prefix","dw_design_prefix":"Design drawings prefix","dw_shop_prefix":"Shop drawings prefix","dw_company":"Company name on the title block","dw_company_line":"Line under the company name","dw_status_design":"Design drawings status","dw_status_shop":"Shop drawings status","dw_workflow":"Workflow","dw_open_workflow":"Open the workflow guide","dw_open_file_workflow":"RAM file workflow (from receipt to delivery)","dw_step1":"1. Register the project (once).","dw_step2":"2. Add its levels / zones with their codes.","dw_step3":"3. Upload the RAM file for each level and generate.","dw_step4":"4. Download the package and review the assumptions printed on the sheets.","dw_search":"Search by name, code or client","dw_tab_levels":"Levels & runs","dw_tab_files":"Project files","dw_tab_history":"Revision history","dw_files_design":"Original design files","dw_files_ram":"RAM files","dw_files_pt_design":"PT design drawings","dw_files_pt_shop":"PT shop drawings","dw_files_hint":"Everything of the project in one place: the original drawings (architectural / structural), the RAM models, and the PT design and shop drawings. Packages generated here appear automatically.","dw_upload_file":"Upload file","dw_file_name":"File","dw_file_note":"Note","dw_file_rev":"Revision","dw_file_size":"Size","dw_file_by":"Uploaded by","dw_file_category":"Section","dw_no_files":"No files in this section","dw_delete_file_confirm":"This deletes the file. Continue?","dw_generated_package":"Package generated here","dw_run_notes":"Change description / revision notes","dw_run_notes_hint":"What changed in the model or the drawings since the previous revision","dw_run_status":"Run status","dw_status_draft":"Draft","dw_status_issued":"Issued","dw_status_superseded":"Superseded","dw_status_blocked":"Blocked — punching","dw_rotate":"Plan orientation on the sheet","dw_rotate_auto":"Auto (turn 90° when the plan is taller than wide)","dw_rotate_0":"As modelled (no turn)","dw_rotate_90":"Turn 90°","dw_rotate_hint":"A plan that would not fit the landscape sheet is turned 90° so that its long side lies along the sheet (the north arrow follows). Force 0 or 90 when needed.","dw_mesh":"Slab mesh","dw_mesh_bottom":"Bottom mesh only","dw_mesh_both":"Top and bottom mesh","dw_mesh_hint":"The mesh written on the design sheets and counted in the take-off.","dw_ram_failed":"Columns failing punching in RAM","dw_ram_failed_hint":"Column ids as printed on the framing sheet (A/1, B/3 …). The program cannot read the punching verdict from the RAM file, so you report it here. Each of these columns blocks the run until a decision is taken.","dw_punch_title":"Punching alert — run blocked","dw_punch_blocked":"Columns not passing punching ({n}): {cols}. This run cannot be issued or submitted before the design engineer decides.","dw_punch_warn":"Columns to look at in the RAM punching report (the estimate says they need punching reinforcement and RAM designed no stud rails): {cols}","dw_punch_hint":"RAM keeps no punching result in the file. The program makes an indicative check (SBC 304 / ACI 318 on the tributary areas and loads of the model) and relies on the columns you report as failing in RAM. The RAM punching report governs.","dw_punch_col":"Column","dw_punch_loc":"Location","dw_punch_trib":"Tributary (m²)","dw_punch_vu":"Vu (kN)","dw_punch_ratio":"vu / φvc","dw_punch_status":"Estimate","dw_punch_ok":"Passing","dw_punch_reinforce":"Needs punching reinforcement","dw_punch_fail":"Not passing even with stirrups","dw_punch_in_ram":"Failing in RAM (reported)","dw_punch_ssr":"Stud rails in RAM","dw_punch_loc_interior":"Interior","dw_punch_loc_edge":"Edge","dw_punch_loc_corner":"Corner","dw_punch_thicken":"Thicken the drop / slab","dw_punch_thicken_hint":"The run stays blocked. Change the model in RAM (a drop or a thicker slab in that zone) and upload it as a new run.","dw_punch_ram_ok":"These columns pass in the RAM report","dw_punch_ram_ok_hint":"The estimate was conservative. Acknowledging that the RAM punching report passes these columns regenerates the run without punching reinforcement at them.","dw_punch_bypass":"Bypass at my own responsibility","dw_punch_bypass_hint":"Punching reinforcement (PS) from the program estimate is provided at these columns and the sheets state it is at the design engineer's responsibility, with your name and the date.","dw_punch_ack":"I acknowledge that I am the design engineer responsible for this decision and that my name is printed on the drawings","dw_punch_note":"Reason (optional — printed in the sheet assumptions)","dw_punch_columns":"Columns the decision covers","dw_punch_all_flagged":"All flagged columns","dw_punch_decided":"Decision: {mode} — {by}, {date}","dw_punch_clear":"Clear the decision","dw_punch_mode_thicken":"Thicken","dw_punch_mode_bypass":"Bypass at the engineer's responsibility","dw_punch_mode_ram_ok":"Passing in RAM","dw_punch_regenerated":"Regenerated under the decision","dw_designer":"Design engineer (who generated the run)","dw_designer_hint":"The name of the user generating the run is printed in the PREPARED / DESIGNED BY box on every sheet.","dw_mesh_kg":"Mesh weight (kg)","dw_beam_design":"Beam design","dw_bd_ram":"RAM bars (design strips)","dw_bd_office":"Office design (moment and shear analysis)","dw_bd_max":"The heavier of the two (RAM or the office design)","dw_bd_hint":"Office design: every beam is analysed as a continuous beam over its supports under the slab it carries (self-weight + the model loads, 1.2D + 1.6L with patterned live load), its bars and stirrups designed and its deflection checked (SBC 304 / ACI 318). RAM keeps no forces in the file, so the analysis is the program's and the RAM report governs.","dw_ram_failed_beams":"Beams failing deflection in RAM","dw_ram_failed_beams_hint":"Beam ids as printed on the beam sheet (BM1, BM3 …). Each of these beams blocks the run until a decision is taken.","dw_beam_check":"Beam check (office design)","dw_beam_check_title":"Beam alert — run blocked","dw_beam_blocked":"Beams not passing ({n}): {beams}. This run cannot be issued or submitted before the design engineer decides.","dw_beam_forces":"Forces and design","dw_beam_spans":"Spans (m)","dw_beam_trib":"Tributary (m)","dw_beam_wu":"wu (kN/m)","dw_beam_mneg":"Mu- (kN·m)","dw_beam_mpos":"Mu+ (kN·m)","dw_beam_vu":"Vu (kN)","dw_beam_defl":"Deflection","dw_beam_defl_table":"OK by span / depth","dw_beam_defl_ratio":"{r} of the limit","dw_beam_status":"Status","dw_beam_ok":"Passing","dw_beam_fail":"Not passing","dw_beam_reason_deflection":"deflection","dw_beam_reason_flexure":"section cannot carry the moment","dw_beam_reason_shear":"section cannot carry the shear","dw_beam_in_ram":"Failing in RAM (reported)","dw_beam_no_supports":"No supports found on the beam (analysed as one span)","dw_beam_ram_bars":"RAM bars","dw_beam_office_bars":"Office design","dw_beam_chosen":"Drawn","dw_beam_deepen":"Deepen the beam","dw_beam_deepen_hint":"The run stays blocked. Change the beam in RAM and upload the model as a new run.","dw_beam_ram_ok":"These beams pass in the RAM report","dw_beam_ram_ok_hint":"The estimate was conservative. Acknowledging that the RAM report passes these beams regenerates the run at the same revision.","dw_beam_bypass":"Bypass at my own responsibility","dw_beam_bypass_hint":"The run is regenerated as is, and the beam sheet states these beams are not passing and accepted at the design engineer's responsibility with your name and the date.","dw_beam_columns":"Beams the decision covers","dw_beam_mode_deepen":"Deepen","dw_beam_mode_bypass":"Bypass at the engineer's responsibility","dw_beam_mode_ram_ok":"Passing in RAM","dw_issue":"Mark as issued","dw_issue_confirm":"This run becomes the issued revision; the earlier issued run of this level becomes superseded. Continue?","dw_history":"Revision history","dw_history_hint":"Every run per level: revision, status, what changed, and the reinforcement weight change against the previous one.","dw_weight_t":"Top steel (kg)","dw_weight_b":"Bottom steel (kg)","dw_delta":"Change","dw_save_notes":"Save notes","dw_files_multi":"RAM files (several can be selected)","dw_files_map_hint":"Each file is generated for one level: the level is suggested from the file name and can be changed.","dw_batch_progress":"Generating {n} of {total}…","dw_batch_done":"Done: {ok} succeeded, {fail} failed","dw_file_level":"Level per file","dw_edit_rebar":"Edit reinforcement","dw_editor":"Reinforcement editor","dw_editor_hint":"Click a bar to select it (Shift for several). Change its length or call-out, delete it, or add a new bar; then save the edits and regenerate to get a new revision with them.","dw_selected":"selected","dw_delete_bars":"Delete","dw_extend_start":"Start","dw_extend_end":"End","dw_apply_length":"Apply","dw_new_spec":"New call-out (e.g. T16-150 (T))","dw_add_bar":"Add bar","dw_add_bar_hint":"Click the start point, then the end point on the plan","dw_pan":"Pan","dw_select":"Select","dw_fit":"Fit","dw_edits_pending":"Unsaved edits","dw_edits_list":"Saved edits of this level","dw_save_edits":"Save edits","dw_regenerate":"Regenerate with edits","dw_clear_edits":"Clear all edits","dw_edits_saved":"Edits saved ✓","dw_regenerated":"New run generated ✓","dw_face_t":"Top (T)","dw_face_b":"Bottom (B)","dw_show_top":"Top","dw_show_bottom":"Bottom","dw_frame":"Sheet frame (the band around the sheet)","dw_frame_hint":"Sizes of the right-hand strip and its boxes in paper mm (A1). Boxes can be switched off (key plan, references, schedule, detail strip) and their room goes to the notes.","dw_frame_size":"Sheet size","dw_frame_right":"Right strip width","dw_frame_bottom":"Detail strip height","dw_frame_title":"Title block height","dw_frame_refs":"References / revisions height","dw_frame_key":"Key plan height","dw_frame_sched":"Schedule height","dw_frame_keyplan":"Key plan","dw_frame_refsbox":"References & revisions","dw_frame_schedule":"Schedule","dw_frame_details":"Detail strip","dw_rebar_defaults":"Reinforcement defaults","dw_rebar_defaults_hint":"The diameter, spacing and length the program writes on the sheets when the RAM model or the project gives none: the column top bars (two groups over every column, the length given or the drop panel), the drop bars (detail 4: the drop bottom mesh with legs), the bottom mesh and the top mesh (under the both-faces option). Also the U-bar lengths: the perimeter U-bar at a free edge, the internal pour strip U-bar, the pour strip U-bars at a retaining wall (in the wall / from the slab side) and the top & bottom bars across a pour strip. All editable here and per project through the specification overrides.","dw_rd_columns":"Column top bars","dw_rd_drops":"Drop bars","dw_rd_bottom":"Bottom mesh","dw_rd_top":"Top mesh","dw_rd_dia":"Diameter (mm)","dw_rd_spacing":"Spacing (mm)","dw_rd_length":"Length (mm)","dw_rd_leg":"Leg (mm)","dw_rd_utotal":"Total bar length (mm)","dw_rd_uedge":"Perimeter U-bar (free edge)","dw_rd_pstrip":"Pour strip U-bar","dw_rd_pstrip_tb":"Pour strip - top & bottom bars across","dw_rd_pstrip_wall":"Pour strip U-bar in the retaining wall","dw_rd_pstrip_slab":"Pour strip U-bar from the slab side (at a wall)","dw_frame_dxf":"Office frame (DXF)","dw_frame_dxf_hint":"Upload the office frame as a DXF drawn in paper mm (A1: 841×594, origin at the bottom-left corner). Write tokens in its texts such as <PROJECT> <CLIENT> <CONSULTANT> <CONTRACTOR> <LOCATION> <TITLE> <LEVEL> <DRAWING_NO> <REV> <DATE> <SCALE> <SHEET> <PREPARED> <CHECKED> <APPROVED> <STATUS> <PROJECT_CODE> <COMPANY>; they are filled on every sheet. This frame replaces the built-in frame and title block.","dw_frame_upload":"Upload frame DXF","dw_frame_remove":"Remove frame","dw_frame_current":"Current frame","dw_frame_none":"No frame uploaded — the built-in frame is used","dw_tab_submittals":"Submittals","dw_tab_quantities":"Quantities & cost","dw_tab_beam_types":"Beam schedule","dw_bt_hint":"The beam type schedule is unified across the project: every run of every level uses the types on record as they are; a beam no type carries gets a new type appended here, and the existing types are never changed.","dw_bt_empty":"No beam types on record yet: they are added with the first run carrying designed beams, or call up the schedule of an earlier project.","dw_bt_import":"Call up an earlier project's schedule","dw_bt_from":"Project","dw_bt_import_hint":"The types of the project picked are appended to this project's schedule (identical ones skipped, clashing marks renumbered).","dw_bt_imported":"{added} type(s) added ({skipped} identical skipped)","dw_bt_source":"Source","dw_bt_source_run":"Run {run} · {level} REV {rev}","dw_bt_source_import":"Imported from {code}","dw_bt_new":"New on this run","dw_bt_existing":"From the project schedule","dw_bt_delete_confirm":"This removes the type from the project schedule (not allowed while it is printed on a run). Continue?","dw_bt_added_on_run":"Types added to the project schedule by this run: {marks}","dw_reference":"Reference plan (columns / grid / slab edges)","dw_reference_short":"Reference plan","dw_beams":"Beam design","dw_beams_hint":"Step one: the program takes this run's RAM model, drops every design strip in it, and draws a strip on the centre line of every beam (one per span between its supports) with a splitter on each of its edges, designed as a beam. Download the prepared model, open it in RAM, Calc All and save. Step two: upload the calculated model as the next run of the level: the beams come back grouped into types (B1, B2 …), every beam labelled with its type and section, and the reinforcement schedule and sections on the beams sheet.","dw_beams_prepare":"Prepare the RAM model with beam strips","dw_beams_download":"Download the model (.cpt)","dw_beams_prepared":"Model ready: {beams} beams, {spans} spans, {splitters} splitters — {removed} old strip rows removed","dw_beams_none":"No beam designed in RAM on this run yet.","dw_beams_types":"Beam types","dw_beam_type":"Type","dw_beam_section":"Section b×h","dw_beam_top":"Top bars (supports)","dw_beam_bottom":"Bottom bars (span)","dw_beam_stirrups":"Stirrups","dw_beam_count":"Count","dw_beam_list":"Beams","dw_beams_undesigned":"Beams without a RAM design","dw_reference_hint":"Upload the level's plan from the architect or the structural engineer as DXF (DXFOUT from the DWG) with the grid bubbles, the columns and the slab edges. The sheets then carry the project's grid, columns and edges instead of RAM's. The plan is fitted on the RAM model automatically by matching the columns (any shift, turned 0/90/180/270), or give a common point yourself: its coordinates in the drawing and in RAM (a grid intersection or a column corner).","dw_reference_upload":"Upload DXF","dw_reference_none":"No reference plan — grid, columns and edges come from RAM","dw_reference_current":"Current plan","dw_reference_remove":"Remove plan","dw_reference_found":"Read from the plan","dw_reference_columns":"columns","dw_reference_outlines":"slab outlines","dw_reference_grid":"Grid","dw_reference_grid_derived":"No grid bubbles in the plan — the grid will be derived from its columns","dw_reference_use":"Use from the plan","dw_use_grid":"Grid","dw_use_columns":"Columns","dw_use_outline":"Slab edges","dw_reference_align":"Alignment","dw_align_auto":"Automatic — match the columns","dw_align_point":"A common point I give","dw_align_dxf":"Point in the drawing (mm)","dw_align_ram":"Same point in RAM (mm)","dw_align_rot":"Drawing turn","dw_align_x":"X","dw_align_y":"Y","dw_reference_saved":"Reference plan saved ✓ — used on the next run","dw_delete_reference_confirm":"Remove the reference plan from this level?","dw_submittals_hint":"A submittal (transmittal) is made from the runs you pick: the drawing numbers, titles and revisions are filled in from the title blocks, and its number is sequential per project (SPAN-SUB-P26-001-001). When a revised drawing is submitted again, the new form names the revision it supersedes and the earlier submittal. The template is one for the whole office, in the Drawings settings.","dw_new_submittal":"New submittal","dw_submittal":"Submittal","dw_submittal_no":"Submittal No.","dw_submittal_to":"To (consultant)","dw_submittal_attention":"Attention","dw_submittal_subject":"Subject","dw_submittal_purpose":"Purpose","dw_purpose_approval":"For approval","dw_purpose_information":"For information","dw_purpose_resubmission":"Re-submission","dw_purpose_as_built":"As built","dw_submittal_runs":"Runs to submit","dw_submittal_sheets":"Sheets","dw_submittal_all_sheets":"All sheets of the run","dw_submittal_items":"Drawings","dw_submittal_date":"Submission date","dw_submittal_open_form":"Open the form (print / PDF)","dw_submittal_mark":"Set status","dw_submittal_response":"Consultant's response","dw_submittal_response_date":"Response date","dw_submittal_response_by":"Response by","dw_submittal_reissue":"Re-issue the form (R+1)","dw_submittal_supersedes":"Supersedes","dw_no_submittals":"No submittals yet","dw_delete_submittal_confirm":"Delete this submittal?","dw_sstatus_draft":"Draft","dw_sstatus_submitted":"Submitted","dw_sstatus_approved":"Approved","dw_sstatus_approved_as_noted":"Approved as noted","dw_sstatus_resubmit":"Revise and resubmit","dw_sstatus_rejected":"Rejected","dw_sstatus_withdrawn":"Withdrawn","dw_submittal_template":"Submittal form template (office-wide)","dw_submittal_template_hint":"This template prints on every submittal in every project: prefix, title, intro, response boxes, signature lines and footer. Change it here once and it changes everywhere.","dw_sub_prefix":"Submittal number prefix","dw_sub_title":"Form title","dw_sub_title_ar":"Title (Arabic)","dw_sub_intro":"Intro","dw_sub_responses":"Response boxes (one per line)","dw_sub_signatures":"Signature lines (one per line)","dw_sub_footer":"Footer","dw_sub_contact":"Contact line in the header","dw_quantities_hint":"The take-off comes from the same model and schedules the drawings were made from: steel from the bar schedules, concrete from the slab plan (openings deducted, drops and beams added), cables from the RAM tendons. Each level uses its issued run (or its latest draft).","dw_qty_steel":"Reinforcement","dw_qty_concrete":"Concrete","dw_qty_cables":"Cables (post-tensioning)","dw_qty_by_dia":"By diameter","dw_qty_total_m":"Length (m)","dw_qty_kg":"Weight (kg)","dw_qty_count":"Count","dw_qty_top":"Top","dw_qty_bottom":"Bottom","dw_qty_other":"Other","dw_qty_gross":"Gross area (m²)","dw_qty_openings":"Openings (m²)","dw_qty_net":"Net area (m²)","dw_qty_thk":"Thickness (mm)","dw_qty_slab":"Slab (m³)","dw_qty_drops":"Drops (m³)","dw_qty_beams":"Beams (m³)","dw_qty_total_m3":"Total concrete (m³)","dw_qty_formwork":"Formwork (m²)","dw_qty_tendons":"Tendons","dw_qty_strands":"Strands","dw_qty_tendon_m":"Tendon length (m)","dw_qty_strand_m":"Strand length (m)","dw_qty_cutting_m":"Cutting length (m)","dw_qty_strand_kg":"Strand weight (kg)","dw_qty_live":"Live anchors","dw_qty_dead":"Dead anchors","dw_qty_duct_small":"Duct 20x50 (m)","dw_qty_duct_large":"Duct 20x70 (m)","dw_qty_kg_m2":"kg/m²","dw_qty_source":"Run used","dw_no_quantities":"No take-off yet — generate drawings for at least one level.","dw_export_csv":"Export CSV","dw_qty_totals":"Totals","dw_cost":"Cost study","dw_cost_hint":"Take-off × unit rates from the settings (change them here as a what-if without saving). The official office rates live in the Drawings settings.","dw_cost_item":"Item","dw_cost_unit":"Unit","dw_cost_qty":"Quantity","dw_cost_rate":"Rate","dw_cost_amount":"Amount","dw_cost_steel":"Reinforcement (supply)","dw_cost_rebar_labour":"Reinforcement (cut, bend, fix)","dw_cost_concrete":"Concrete","dw_cost_formwork":"Formwork","dw_cost_strand":"Strand","dw_cost_anchor_live":"Live anchors","dw_cost_anchor_dead":"Dead anchors","dw_cost_duct":"Duct","dw_cost_pt_labour":"PT labour","dw_cost_direct":"Direct cost","dw_cost_markup":"Overheads & profit","dw_cost_vat":"VAT","dw_cost_total":"Total","dw_cost_per_m2":"Cost / m²","dw_cost_apply":"Recalculate","dw_rates":"Unit rates (cost study)","dw_rates_hint":"The office default rates for the cost study, one currency.","dw_rate_currency":"Currency","dw_rate_steel_per_ton":"Steel (per ton)","dw_rate_rebar_labour_per_ton":"Rebar labour (per ton)","dw_rate_concrete_per_m3":"Concrete (per m³)","dw_rate_formwork_per_m2":"Formwork (per m²)","dw_rate_strand_per_kg":"Strand (per kg)","dw_rate_anchor_live":"Live anchor (each)","dw_rate_anchor_dead":"Dead anchor (each)","dw_rate_duct_per_m":"Duct (per m)","dw_rate_pt_labour_per_m2":"PT labour (per m²)","dw_rate_markup_pct":"Overheads & profit %","dw_rate_vat_pct":"VAT %"}};
const EXTRA = {
  ar: {
    app_name: 'Span Tech', app_sub: 'لوحات التسليح · Python', nav_projects: 'المشاريع', nav_settings: 'الإعدادات', nav_help: 'المساعدة',
    country: 'الدولة', country_SA: 'السعودية', country_EG: 'مصر', country_QA: 'قطر',
    dw_designer_name: 'اسم المهندس المصمم (PREPARED / DESIGNED BY)', dw_designer_name_hint: 'الاسم اللي بيتكتب في خانة PREPARED / DESIGNED BY على كل لوحة، وبيتسجل على القرارات.',
    dw_open_folder: 'افتح فولدر الإصدار', dw_data_folder: 'فولدر البيانات', dw_generating: 'بيطلع اللوحات… خليك على الصفحة', dw_generation_took: 'الإخراج خد {s} ثانية',
    dw_run_failed: 'الإصدار فشل', dw_regenerate: 'أعد الإخراج بنفس الموديل', dw_regenerate_hint: 'بيطلع إصدار جديد من نفس ملف الرام بالإعدادات الحالية (بعد تعديل الإعدادات أو المخطط المرجعي مثلاً).',
    dw_takeoff_kg: 'الحديد بعد التعديل (كجم)', dw_run_quantities: 'حصر الإصدار', dw_frame_uploaded: 'الفريم اترفع', dw_edited_files: 'لوحات معدّلة مرفوعة',
    help_title: 'خطوات العمل على البرنامج', help_intro: 'البرنامج ده هو مولّد لوحات التسليح والبوست تنشن (نسخة البايثون) بنفس شاشات نظام الـ CRM: كل حاجة بتتحفظ على جهازك في فولدر البيانات.',
    help_cli: 'من سطر الأوامر (نفس المولّد بدون الشاشات)', help_files: 'اللي بيطلع في كل إصدار',
    help_files_text: 'ملف DXF لكل لوحة (dxf/)، الباكدج الكامل، معاينات SVG (preview/)، جداول CSV (schedules/)، model.json و quantities.json و punching.json و beams.json و REPORT.md، وملف ZIP بكل ده.',
    help_data: 'فولدر البيانات: كل المشاريع والإصدارات والإعدادات في db.json وفولدر projects/. انسخ الفولدر ده عشان تاخد نسخة احتياطية أو تنقله لجهاز تاني.',
    dw_files_none: 'مفيش ملفات في القسم ده.', dw_history_none: 'لسه مفيش إصدارات.', print: 'طباعة', create: 'إنشاء', optional: 'اختياري',
  },
  en: {
    app_name: 'Span Tech', app_sub: 'Drawings · Python', nav_projects: 'Projects', nav_settings: 'Settings', nav_help: 'Help',
    country: 'Country', country_SA: 'Saudi Arabia', country_EG: 'Egypt', country_QA: 'Qatar',
    dw_designer_name: 'Design engineer (PREPARED / DESIGNED BY)', dw_designer_name_hint: 'Printed in the PREPARED / DESIGNED BY box of every sheet and recorded on the decisions.',
    dw_open_folder: 'Open the run folder', dw_data_folder: 'Data folder', dw_generating: 'Generating the drawings… stay on the page', dw_generation_took: 'Generation took {s} s',
    dw_run_failed: 'The run failed', dw_regenerate: 'Regenerate from the same model', dw_regenerate_hint: 'A new run from the same RAM file with the current settings (after changing the settings or the reference plan, for instance).',
    dw_takeoff_kg: 'Steel after the edit (kg)', dw_run_quantities: 'Run take-off', dw_frame_uploaded: 'Frame uploaded', dw_edited_files: 'Edited sheets uploaded',
    help_title: 'How to work with the program', help_intro: 'This is the reinforcement / PT drawings generator (the Python version) with the same screens as the CRM Drawings module: everything is kept on your machine in the data folder.',
    help_cli: 'From the command line (the generator without the screens)', help_files: 'What every run writes',
    help_files_text: 'One DXF per sheet (dxf/), the package DXF, SVG previews (preview/), CSV schedules (schedules/), model.json, quantities.json, punching.json, beams.json, REPORT.md, and a ZIP of it all.',
    help_data: 'The data folder: every project, run and setting in db.json and the projects/ folder. Copy that folder for a backup or to move to another machine.',
    dw_files_none: 'No files in this section.', dw_history_none: 'No runs yet.', print: 'Print', create: 'Create', optional: 'optional',
  },
};
for (const l of ['ar', 'en']) Object.assign(DICT[l], EXTRA[l]);
let LANG = 'ar';
try { LANG = localStorage.getItem('lang') || 'ar'; } catch (e) { /* private window */ }
const t = (key, fallback) => DICT[LANG][key] ?? DICT.en[key] ?? fallback ?? key;
const isRTL = () => LANG === 'ar';
const pick = (row, base) => (isRTL() && row[`${base}_ar`]) || row[base];
function setLang(lang) {
  LANG = lang;
  try { localStorage.setItem('lang', lang); } catch (e) { /* ignore */ }
  applyDirection(); render();
}
function applyDirection() {
  const html = document.documentElement;
  html.lang = LANG; html.dir = isRTL() ? 'rtl' : 'ltr';
  document.title = isRTL() ? 'Span Tech · لوحات التسليح' : 'Span Tech · Drawings';
}
function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', { year: 'numeric', month: 'short', day: '2-digit' });
}
function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return `${formatDate(value)} · ${d.toLocaleTimeString(isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', { hour: '2-digit', minute: '2-digit' })}`;
}
const fill = (key, vars) => Object.entries(vars).reduce((text, [k, v]) => text.replace(`{${k}}`, v), t(key));
const num = (v, d = 1) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 }));
const fmtBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${Math.round(n / 1024)} KB` : `${n || 0} B`);
const csvOf = (rows) => rows.map((r) => r.map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(',')).join('\n');
function downloadText(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([`\ufeff${text}`], { type: 'text/csv;charset=utf-8' }));
  a.download = name; document.body.append(a); a.click(); a.remove();
}

// ------------------------------------------------------------------------------------------------ DOM toolkit
function el(spec, props = {}, children = []) {
  const text = String(spec);
  const hash = text.indexOf('#');
  let id = ''; let rest = text;
  if (hash !== -1) { const after = text.slice(hash + 1); const dot = after.indexOf('.'); id = dot === -1 ? after : after.slice(0, dot); rest = text.slice(0, hash) + (dot === -1 ? '' : after.slice(dot)); }
  const [tag, ...classes] = rest.split('.');
  const node = document.createElement(tag || 'div');
  if (id) node.id = id;
  if (classes.length) node.className = classes.filter(Boolean).join(' ');
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = `${node.className} ${value}`.trim();
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value === true ? '' : value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
const ICONS = {
  drawings: 'M3 3h18v18H3zM3 9h18M9 3v18M15 9v12M3 15h6', settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35', plus: 'M12 5v14M5 12h14', menu: 'M3 12h18M3 6h18M3 18h18',
  trash: 'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', edit: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z',
  check: 'M20 6L9 17l-5-5', x: 'M18 6L6 18M6 6l12 12', empty: 'M20 13V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7M4 13h4l1.5 3h5L16 13h4v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z',
  chevron: 'M9 18l6-6-6-6', bell: 'M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 0 1-3.46 0', back: 'M19 12H5M12 19l-7-7 7-7',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3', upload: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12',
  layers: 'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5', play: 'M5 3l14 9-14 9V3z', help: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3M12 17h.01',
  folder: 'M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z', refresh: 'M23 4v6h-6M1 20v-6h6M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15',
};
function icon(name, size = 18) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('width', size); svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none'); svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '2'); svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
  svg.innerHTML = `<path d="${ICONS[name] || ICONS.empty}"/>`;
  return svg;
}
let toastHost;
function toast(message, kind = 'info', ms = 3600) {
  if (!toastHost) { toastHost = el('div.toasts'); document.body.append(toastHost); }
  const node = el('div.toast', { class: kind, text: message });
  toastHost.append(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transition = 'opacity .25s'; setTimeout(() => node.remove(), 250); }, ms);
}
const toastError = (error) => toast(error?.localised || error?.message || t('error'), 'error', 5200);
function openModal({ title, body, footer, size = '', onClose }) {
  const backdrop = el('div.modal-backdrop');
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); document.body.style.overflow = ''; onClose?.(); };
  const onKey = (event) => { if (event.key === 'Escape') close(); };
  const modal = el(`div.modal${size ? `.${size}` : ''}`, {}, [
    el('div.modal-header', {}, [el('h2', { text: title || '' }), el('button.close', { type: 'button', text: '×', onclick: close })]),
    el('div.modal-body', {}, [typeof body === 'function' ? body(close) : body]),
    footer ? el('div.modal-footer', {}, [typeof footer === 'function' ? footer(close) : footer]) : null,
  ]);
  backdrop.append(modal);
  backdrop.addEventListener('click', (event) => { if (event.target === backdrop) close(); });
  document.addEventListener('keydown', onKey);
  document.body.style.overflow = 'hidden';
  document.body.append(backdrop);
  return { close, modal };
}
function confirmDialog(message, { danger = true, confirmLabel } = {}) {
  return new Promise((resolve) => {
    let answered = false;
    const settle = (value) => { if (answered) return; answered = true; resolve(value); };
    openModal({
      title: t('confirm_title', isRTL() ? 'تأكيد' : 'Confirm'), size: 'narrow', body: el('p', { text: message }),
      footer: (dismiss) => el('div.row', {}, [
        el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: () => { settle(false); dismiss(); } }),
        el(`button.btn${danger ? '.btn-danger' : ''}`, { type: 'button', text: confirmLabel || t('delete'), onclick: () => { settle(true); dismiss(); } }),
      ]),
      onClose: () => settle(false),
    });
  });
}
function field({ name, label, type = 'text', value = '', options, required = false, placeholder = '', hint = '', min, max, step, rows, disabled = false, dir }) {
  let input;
  if (type === 'select') {
    input = el('select', { name, disabled });
    for (const option of options || []) { const node = el('option', { value: option.value, text: option.label }); if (String(option.value) === String(value ?? '')) node.selected = true; input.append(node); }
  } else if (type === 'textarea') { input = el('textarea', { name, placeholder, disabled, rows: rows || 3 }); input.value = value ?? ''; }
  else if (type === 'checkbox') {
    input = el('input', { type: 'checkbox', name, disabled }); input.checked = Boolean(value);
    return el('div.field', {}, [el('label.checkbox', {}, [input, el('span', { text: label })]), hint ? el('div.hint', { text: hint }) : null]);
  } else { input = el('input', { type, name, placeholder, disabled, min, max, step }); input.value = value ?? ''; if (type === 'number') input.classList.add('num'); }
  if (required) input.required = true;
  if (dir) input.dir = dir;
  return el('div.field', {}, [label ? el('label', {}, [label, required ? el('span', { style: { color: 'var(--danger-600)' }, text: ' *' }) : null]) : null, input, hint ? el('div.hint', { text: hint }) : null]);
}
function readForm(root) {
  const data = {};
  for (const input of root.querySelectorAll('[name]')) {
    if (input.type === 'checkbox') data[input.name] = input.checked;
    else if (input.type === 'number') data[input.name] = input.value === '' ? null : Number(input.value);
    else data[input.name] = input.value === '' ? null : input.value;
  }
  return data;
}
function dataTable({ columns, rows, onRowClick, empty, footer }) {
  if (!rows || rows.length === 0) return el('div.empty', {}, [icon('empty', 40), el('div', { text: empty || t('nothing_here') })]);
  const head = el('tr', {}, columns.map((c) => el('th', { class: c.className || '', text: c.label })));
  const body = el('tbody', {}, rows.map((row) => {
    const tr = el('tr', { class: onRowClick ? 'clickable' : '' }, columns.map((c) => {
      const cell = el('td', { class: c.className || '' });
      const content = c.render ? c.render(row) : row[c.key];
      if (content instanceof Node) cell.append(content); else cell.textContent = content ?? '—';
      return cell;
    }));
    if (onRowClick) tr.addEventListener('click', (event) => { if (event.target.closest('button, a, input, select')) return; onRowClick(row); });
    return tr;
  }));
  const table = el('table.data', {}, [el('thead', {}, [head]), body]);
  if (footer) table.append(el('tfoot', {}, [footer]));
  return el('div.table-wrap', {}, [table]);
}
const pageHeader = (title, actions = []) => el('div.toolbar', {}, [el('h1', { style: { margin: 0 }, text: title }), el('div.spacer'), ...actions]);
let busyNode;
function busy(on, text) {
  if (busyNode) { busyNode.remove(); busyNode = null; }
  if (on) { busyNode = el('div.busy', {}, [el('div.box', {}, [el('span.spinner.dark'), el('span', { text: text || t('loading') })])]); document.body.append(busyNode); }
}

// ----------------------------------------------------------------------------------------------------- API
async function call(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const res = await fetch(url, opts);
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch (e) { data = { error: text }; }
  if (!res.ok) { const err = new Error(data.error || res.statusText); err.localised = isRTL() ? data.error_ar || data.error : data.error; throw err; }
  return data;
}
async function upload(url, file, query = {}) {
  const qs = new URLSearchParams({ name: file.name, ...Object.fromEntries(Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== '')) });
  const res = await fetch(`${url}?${qs}`, { method: 'POST', body: file, headers: { 'Content-Type': 'application/octet-stream' } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { const err = new Error(data.error || res.statusText); err.localised = isRTL() ? data.error_ar || data.error : data.error; throw err; }
  return data;
}
const api = {
  bootstrap: () => call('GET', '/api/bootstrap'),
  settings: () => call('GET', '/api/settings'), saveSettings: (s) => call('PUT', '/api/settings', s), resetSettings: () => call('POST', '/api/settings/reset'),
  uploadFrame: (f) => upload('/api/settings/frame', f), deleteFrame: () => call('DELETE', '/api/settings/frame'), frameUrl: () => '/api/settings/frame',
  projects: (q) => call('GET', `/api/projects?q=${encodeURIComponent(q || '')}`), project: (id) => call('GET', `/api/projects/${id}`),
  createProject: (d) => call('POST', '/api/projects', d), updateProject: (id, d) => call('PATCH', `/api/projects/${id}`, d), deleteProject: (id) => call('DELETE', `/api/projects/${id}`),
  createLevel: (pid, d) => call('POST', `/api/projects/${pid}/levels`, d), updateLevel: (id, d) => call('PATCH', `/api/levels/${id}`, d), deleteLevel: (id) => call('DELETE', `/api/levels/${id}`),
  uploadReference: (id, f) => upload(`/api/levels/${id}/reference`, f), updateReference: (id, d) => call('PATCH', `/api/levels/${id}/reference`, d), deleteReference: (id) => call('DELETE', `/api/levels/${id}/reference`),
  generate: (lid, f, q) => upload(`/api/levels/${lid}/generate`, f, q),
  run: (id) => call('GET', `/api/runs/${id}`), updateRun: (id, d) => call('PATCH', `/api/runs/${id}`, d), deleteRun: (id) => call('DELETE', `/api/runs/${id}`),
  runZipUrl: (id) => `/api/runs/${id}/zip`, runFileUrl: (id, kind, name, download) => `/api/runs/${id}/file/${kind}/${encodeURIComponent(name)}${download ? '?download=1' : ''}`,
  openRunFolder: (id) => call('POST', `/api/runs/${id}/open`), takeoff: (id, f) => upload(`/api/runs/${id}/takeoff`, f),
  prepareBeamStrips: (id) => call('POST', `/api/runs/${id}/beam-strips`), beamStripsUrl: (id) => `/api/runs/${id}/beam-strips`,
  punchingDecision: (id, d) => call('POST', `/api/runs/${id}/punching-decision`, d), beamDecision: (id, d) => call('POST', `/api/runs/${id}/beam-decision`, d), regenerate: (id, d) => call('POST', `/api/runs/${id}/regenerate`, d || {}),
  quantities: (pid) => call('GET', `/api/projects/${pid}/quantities`), cost: (pid, rates) => call('GET', `/api/projects/${pid}/cost?${new URLSearchParams(Object.fromEntries(Object.entries(rates || {}).filter(([, v]) => v != null)))}`),
  beamTypes: (pid) => call('GET', `/api/projects/${pid}/beam-types`), importBeamTypes: (pid, d) => call('POST', `/api/projects/${pid}/beam-types/import`, d), deleteBeamType: (pid, mark) => call('DELETE', `/api/projects/${pid}/beam-types/${encodeURIComponent(mark)}`),
  uploadFile: (pid, f, q) => upload(`/api/projects/${pid}/files`, f, q), fileUrl: (id) => `/api/files/${id}`, deleteFile: (id) => call('DELETE', `/api/files/${id}`),
  createSubmittal: (pid, d) => call('POST', `/api/projects/${pid}/submittals`, d), updateSubmittal: (id, d) => call('PATCH', `/api/submittals/${id}`, d), deleteSubmittal: (id) => call('DELETE', `/api/submittals/${id}`), submittalFormUrl: (id) => `/api/submittals/${id}/form`,
};

// --------------------------------------------------------------------------------------------- shell + router
const MODES = ['design', 'shop'], BANDS = ['all', 'user', 'none'], MESHES = ['bottom', 'both'], BEAM_DESIGNS = ['ram', 'office', 'max'], ROTATIONS = ['auto', '0', '90'], FILE_CATEGORIES = ['design', 'ram', 'pt_design', 'pt_shop'];
const SUBMITTAL_STATUS = ['draft', 'submitted', 'approved', 'approved_as_noted', 'resubmit', 'rejected', 'withdrawn'], PURPOSES = ['approval', 'information', 'resubmission', 'as_built'];
const modeLabel = (mode) => t(mode === 'shop' ? 'dw_mode_shop' : 'dw_mode_design');
const bandsLabel = (b) => t(`dw_bands_${b || 'all'}`);
const meshLabel = (m) => t(`dw_mesh_${m || 'bottom'}`);
const beamDesignLabel = (v) => t(`dw_bd_${v || 'ram'}`);
const rotateLabel = (v) => t(`dw_rotate_${v == null || v === '' ? 'auto' : v}`);
const statusBadge = (status) => el('span', { class: `badge ${status === 'issued' ? 'green' : status === 'failed' || status === 'blocked' ? 'red' : status === 'superseded' ? 'grey' : status === 'running' ? 'amber' : 'blue'}`, text: t(`dw_status_${status || 'running'}`) });
const levelLabel = (level) => [level.code, [level.name, level.zone].filter(Boolean).join(' - ')].filter(Boolean).join(' · ');
const exampleNo = (settings, project, level) => `${project?.default_mode === 'shop' ? settings.shop_prefix : settings.design_prefix}-${project?.code || 'P26-001'}-${level?.code || 'B1'}-02`;
function debounce(fn, ms) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); }; }
let BOOT = { settings: {}, version: '', data_dir: '' };
let projectTab = 'levels';
const navigate = (path) => { location.hash = `#/${path}`; };
function route() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  return { view: parts[0] || 'projects', params: parts.slice(1) };
}
async function render() {
  const root = document.getElementById('root');
  const { view, params } = route();
  const nav = [['projects', 'nav_projects', 'drawings'], ['settings', 'nav_settings', 'settings'], ['help', 'nav_help', 'help']];
  const sidebar = el('aside.sidebar', {}, [
    el('div.sidebar-brand', {}, [el('img', { src: `data:image/png;base64,${ICON_B64}`, alt: '' }), el('div', {}, [el('div.name', { text: t('app_name') }), el('div.sub', { text: t('app_sub') })])]),
    el('nav.sidebar-nav', {}, nav.map(([key, label, ic]) => el('a.nav-item', { href: `#/${key}`, class: view === key ? 'active' : '' }, [icon(ic), t(label)]))),
    el('div.sidebar-footer', {}, [el('div.sidebar-user', {}, [el('div.avatar', { text: (BOOT.settings.designer || 'ST').trim().split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase() }), el('div.who', {}, [el('b', { text: BOOT.settings.designer || t('app_name') }), el('span', { text: `v${BOOT.version} · ${BOOT.data_dir}` })])])]),
  ]);
  const content = el('div.content');
  const topbar = el('header.topbar', {}, [
    el('button.btn.btn-secondary.btn-icon.menu-toggle', { type: 'button', onclick: () => sidebar.classList.toggle('open') }, [icon('menu', 16)]),
    el('h1', { text: view === 'settings' ? t('dw_settings') : view === 'help' ? t('nav_help') : t('dw_title') }),
    el('div.topbar-actions', {}, [el('div.lang-switch', {}, [el('button', { type: 'button', class: LANG === 'ar' ? 'active' : '', text: 'عربي', onclick: () => setLang('ar') }), el('button', { type: 'button', class: LANG === 'en' ? 'active' : '', text: 'EN', onclick: () => setLang('en') })])]),
  ]);
  clear(root).append(el('div.app', {}, [sidebar, el('div.main', {}, [topbar, content])]));
  content.append(el('div.loading-page', { text: t('loading') }));
  try {
    let page;
    if (view === 'settings') page = await settingsPage();
    else if (view === 'help') page = helpPage();
    else if (params[0] && params[1] === 'run' && params[2]) page = await runPage(params[0], params[2]);
    else if (params[0]) { if (params[1] === 'tab' && params[2]) projectTab = params[2]; page = await projectPage(params[0]); }
    else page = await listPage();
    clear(content).append(page);
  } catch (error) { clear(content).append(el('div.alert.danger', { text: error.localised || error.message })); }
}
window.addEventListener('hashchange', render);

// ------------------------------------------------------------------------------------------------ projects
function workflowCard() {
  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_workflow') })]),
    el('div.card-body', {}, [el('ol', { style: { margin: 0, paddingInlineStart: '1.2rem' } }, ['dw_step1', 'dw_step2', 'dw_step3', 'dw_step4'].map((key) => el('li', { text: t(key).replace(/^[\d١-٩]+[-.]\s*/, '') }))), el('div.mt-1', {}, [el('a', { href: '#/help', text: t('nav_help') })])]),
  ]);
}
const filters = { q: '' };
async function listPage() {
  const page = el('div');
  const listHost = el('div');
  const search = el('input', { type: 'search', placeholder: t('dw_search'), value: filters.q, oninput: debounce((e) => { filters.q = e.target.value; refresh(); }, 280) });
  page.append(el('div.toolbar', {}, [el('div.search-box', {}, [icon('search', 15), search]), el('div.spacer'), el('button.btn', { type: 'button', onclick: () => openProjectForm(null, (p) => navigate(`projects/${p.id}`)) }, [icon('plus', 16), t('dw_new_project')])]));
  page.append(el('div.alert.info', { text: t('dw_project_hint') }));
  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [listHost])]));
  page.append(workflowCard());
  async function refresh() {
    clear(listHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { projects } = await api.projects(filters.q);
      clear(listHost).append(dataTable({
        rows: projects, empty: t('nothing_here'), onRowClick: (row) => navigate(`projects/${row.id}`),
        columns: [
          { label: t('dw_project'), render: (row) => el('div', {}, [el('div.bold', { text: pick(row, 'name') }), el('div.tiny.muted', { text: row.code, dir: 'ltr' })]) },
          { label: t('dw_client'), render: (row) => row.client || '—' }, { label: t('dw_consultant'), render: (row) => row.consultant || '—' }, { label: t('dw_location'), render: (row) => row.location || '—' },
          { label: t('dw_levels'), className: 'num', render: (row) => row.level_count }, { label: t('dw_runs'), className: 'num', render: (row) => row.run_count },
          { label: t('dw_last_run'), render: (row) => (row.last_run_at ? formatDate(row.last_run_at) : '—') },
        ],
      }));
    } catch (error) { clear(listHost).append(el('div.alert.danger', { text: error.localised || error.message })); }
  }
  refresh();
  return page;
}
function openProjectForm(project, after) {
  const isNew = !project;
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'code', label: t('dw_code'), value: project?.code || '', dir: 'ltr', hint: isNew ? t('dw_code_hint') : '' }),
      field({ name: 'name', label: t('dw_name'), value: project?.name || '', dir: 'ltr', required: true }),
      field({ name: 'name_ar', label: t('dw_name_ar'), value: project?.name_ar || '', dir: 'rtl' }),
      field({ name: 'location', label: t('dw_location'), value: project?.location || '', dir: 'ltr' }),
      field({ name: 'client', label: t('dw_client'), value: project?.client || '', dir: 'ltr' }),
      field({ name: 'consultant', label: t('dw_consultant'), value: project?.consultant || '', dir: 'ltr' }),
      field({ name: 'contractor', label: t('dw_contractor'), value: project?.contractor || '', dir: 'ltr' }),
      field({ name: 'country', label: t('country'), type: 'select', value: project?.country || '', options: [{ value: '', label: '—' }, ...['SA', 'EG', 'QA'].map((c) => ({ value: c, label: t(`country_${c}`) }))] }),
      field({ name: 'prepared', label: t('dw_prepared'), value: project?.prepared || '', dir: 'ltr', hint: t('dw_signatures_hint') }),
      field({ name: 'checked', label: t('dw_checked'), value: project?.checked || '', dir: 'ltr' }),
      field({ name: 'approved', label: t('dw_approved'), value: project?.approved || '', dir: 'ltr' }),
      field({ name: 'default_mode', label: t('dw_default_mode'), type: 'select', value: project?.default_mode || BOOT.settings.default_mode || 'design', options: MODES.map((m) => ({ value: m, label: modeLabel(m) })) }),
      field({ name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: project?.ram_bands || BOOT.settings.ram_bands || 'all', options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })) }),
      field({ name: 'mesh', label: t('dw_mesh'), type: 'select', value: project?.mesh || BOOT.settings.mesh || 'bottom', hint: t('dw_mesh_hint'), options: MESHES.map((m) => ({ value: m, label: meshLabel(m) })) }),
      field({ name: 'rotate', label: t('dw_rotate'), type: 'select', value: project?.rotate || BOOT.settings.rotate || 'auto', hint: t('dw_rotate_hint'), options: ROTATIONS.map((m) => ({ value: m, label: rotateLabel(m) })) }),
      field({ name: 'beam_design', label: t('dw_beam_design'), type: 'select', value: project?.beam_design || BOOT.settings.beam_design || 'ram', hint: t('dw_bd_hint'), options: BEAM_DESIGNS.map((m) => ({ value: m, label: beamDesignLabel(m) })) }),
    ]),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: project?.notes || '', rows: 2 }),
    field({ name: 'spec', label: t('dw_spec'), type: 'textarea', value: project?.spec && Object.keys(project.spec).length ? JSON.stringify(project.spec, null, 2) : '', rows: 3, dir: 'ltr' }),
  ]);
  const { close } = openModal({
    title: isNew ? t('dw_new_project') : t('dw_edit_project'), size: 'wide', body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', { type: 'button', text: t('save'), onclick: async (event) => {
        const data = readForm(form);
        if (data.spec) { try { data.spec = JSON.parse(data.spec); } catch (e) { toast(`${t('dw_spec')}: JSON`, 'error'); return; } } else data.spec = {};
        if (!data.code) delete data.code;
        event.currentTarget.disabled = true;
        try { const result = isNew ? await api.createProject(data) : await api.updateProject(project.id, data); toast(t('saved'), 'success'); close(); after?.(result.project); }
        catch (error) { toastError(error); event.currentTarget.disabled = false; }
      } }),
    ]),
  });
}
function openLevelForm(projectId, level, after) {
  const isNew = !level;
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'code', label: t('dw_level_code'), value: level?.code || '', dir: 'ltr', required: true, hint: t('dw_level_code_hint') }),
      field({ name: 'name', label: t('dw_level_name'), value: level?.name || '', dir: 'ltr', required: true }),
      field({ name: 'zone', label: t('dw_zone'), value: level?.zone || '', dir: 'ltr' }),
      field({ name: 'wall_thickness', label: t('dw_wall_thickness'), type: 'number', value: level?.wall_thickness ?? '', min: 100, max: 2000, step: 10, hint: t('dw_wall_thickness_hint') }),
      field({ name: 'sort_order', label: t('dw_sort_order'), type: 'number', value: level?.sort_order ?? '', min: 0, max: 999 }),
    ]),
    field({ name: 'ram_failed_columns', label: t('dw_ram_failed'), value: (level?.punching?.ram_failed || []).join(', '), dir: 'ltr', hint: t('dw_ram_failed_hint') }),
    field({ name: 'ram_failed_beams', label: t('dw_ram_failed_beams'), value: (level?.punching?.beams_ram_failed || []).join(', '), dir: 'ltr', hint: t('dw_ram_failed_beams_hint') }),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: level?.notes || '', rows: 2 }),
  ]);
  const { close } = openModal({
    title: isNew ? t('dw_new_level') : t('dw_edit_level'), body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', { type: 'button', text: t('save'), onclick: async (event) => {
        const data = readForm(form);
        if (data.sort_order === null) delete data.sort_order;
        event.currentTarget.disabled = true;
        try { if (isNew) await api.createLevel(projectId, data); else await api.updateLevel(level.id, data); toast(t('saved'), 'success'); close(); after?.(); }
        catch (error) { toastError(error); event.currentTarget.disabled = false; }
      } }),
    ]),
  });
}
function openReferenceForm(level, after) {
  let ref = level.reference || null;
  const status = el('div.small');
  const found = el('div');
  const drawFound = () => {
    clear(found);
    if (!ref) { status.textContent = t('dw_reference_none'); return; }
    const sm = ref.summary || {};
    status.textContent = `${t('dw_reference_current')}: ${ref.name || ''}`;
    found.append(el('div.small.mt-1', {}, [
      el('div', { text: `${t('dw_reference_found')}: ${sm.columns ?? '?'} ${t('dw_reference_columns')} · ${sm.outlines ?? '?'} ${t('dw_reference_outlines')} · ${sm.units || ''}` }),
      el('div', { text: `${t('dw_reference_grid')}: ${(sm.grid_x || []).join(' ')} / ${(sm.grid_y || []).join(' ')}`, dir: 'ltr' }),
      sm.grid_from_drawing === false ? el('div.muted', { text: t('dw_reference_grid_derived') }) : null,
      sm.bbox ? el('div.tiny.muted', { text: `DXF extents: ${sm.bbox.minX}, ${sm.bbox.minY} → ${sm.bbox.maxX}, ${sm.bbox.maxY} mm`, dir: 'ltr' }) : null,
    ]));
  };
  drawFound();
  const input = el('input', { type: 'file', accept: '.dxf', style: { display: 'none' } });
  input.addEventListener('change', async () => {
    const file = input.files?.[0]; if (!file) return;
    try { busy(true); const res = await api.uploadReference(level.id, file); ref = res.level.reference; drawFound(); toast(t('saved'), 'success'); } catch (error) { toastError(error); } finally { busy(false); }
  });
  const use = ref?.use || { grid: true, columns: true, outline: true };
  const align = ref?.align || { mode: 'auto' };
  const pointFields = el('div.grid.grid-2', {}, [
    el('div', {}, [el('label.small', { text: t('dw_align_dxf') }), el('div.grid.grid-2', {}, [field({ name: 'dxf_x', label: t('dw_align_x'), type: 'number', value: align.dxf?.x ?? '', step: 1 }), field({ name: 'dxf_y', label: t('dw_align_y'), type: 'number', value: align.dxf?.y ?? '', step: 1 })])]),
    el('div', {}, [el('label.small', { text: t('dw_align_ram') }), el('div.grid.grid-2', {}, [field({ name: 'ram_x', label: t('dw_align_x'), type: 'number', value: align.ram?.x ?? '', step: 1 }), field({ name: 'ram_y', label: t('dw_align_y'), type: 'number', value: align.ram?.y ?? '', step: 1 })])]),
    field({ name: 'rot', label: t('dw_align_rot'), type: 'select', value: String(align.rot || 0), options: [0, 90, 180, 270].map((v) => ({ value: String(v), label: `${v}°` })) }),
  ]);
  const modeSel = field({ name: 'mode', label: t('dw_reference_align'), type: 'select', value: align.mode || 'auto', options: [{ value: 'auto', label: t('dw_align_auto') }, { value: 'point', label: t('dw_align_point') }] });
  const syncMode = () => { pointFields.style.display = modeSel.querySelector('select').value === 'point' ? '' : 'none'; };
  modeSel.querySelector('select').addEventListener('change', syncMode); syncMode();
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.alert.info', { text: t('dw_reference_hint') }),
    el('div.row.wrap', {}, [input, el('button.btn.btn-sm', { type: 'button', onclick: () => input.click() }, [icon('upload', 14), t('dw_reference_upload')]), status]),
    found, el('h4.mt-1', { text: t('dw_reference_use') }),
    el('div.grid.grid-3', {}, [field({ name: 'use_grid', label: t('dw_use_grid'), type: 'checkbox', value: use.grid !== false }), field({ name: 'use_columns', label: t('dw_use_columns'), type: 'checkbox', value: use.columns !== false }), field({ name: 'use_outline', label: t('dw_use_outline'), type: 'checkbox', value: use.outline !== false })]),
    modeSel, pointFields,
  ]);
  const { close } = openModal({
    title: `${t('dw_reference')} — ${levelLabel(level)}`, size: 'wide', body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      ref || level.reference ? el('button.btn-secondary.btn', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_delete_reference_confirm')))) return; try { await api.deleteReference(level.id); toast(t('deleted'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }, [icon('trash', 14), t('dw_reference_remove')]) : null,
      el('button.btn', { type: 'button', text: t('save'), onclick: async () => {
        if (!ref) { input.click(); return; }
        const d = readForm(form);
        const payload = { use: { grid: d.use_grid, columns: d.use_columns, outline: d.use_outline }, align: d.mode === 'point' ? { mode: 'point', dxf: { x: d.dxf_x, y: d.dxf_y }, ram: { x: d.ram_x, y: d.ram_y }, rot: Number(d.rot) } : { mode: 'auto' } };
        try { await api.updateReference(level.id, payload); toast(t('dw_reference_saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); }
      } }),
    ]),
  });
}
function guessLevel(fileName, levels) {
  const name = fileName.toUpperCase().replace(/[_\-.]+/g, ' ');
  return levels.find((l) => new RegExp(`(^|\\s)${l.code.toUpperCase().replace(/[-]/g, ' ')}(\\s|$)`).test(name)) || levels.find((l) => l.name && name.includes(l.name.toUpperCase())) || levels.find((l) => l.zone && name.includes(l.zone.toUpperCase())) || levels[0];
}
function openGenerateForm(project, levels, settings, preselected) {
  const fileInput = el('input', { type: 'file', name: 'files', accept: '.cpt,.dxf', multiple: true, required: true });
  const mapHost = el('div');
  const status = el('div.small.muted.mt-1');
  let picked = [];
  fileInput.addEventListener('change', () => {
    picked = [...(fileInput.files || [])].map((file) => ({ file, levelId: (preselected && fileInput.files.length === 1 ? preselected : guessLevel(file.name, levels))?.id }));
    clear(mapHost);
    if (picked.length < 1) return;
    mapHost.append(el('div.tiny.muted', { text: t('dw_files_map_hint') }));
    mapHost.append(dataTable({ rows: picked, columns: [
      { label: t('dw_file'), render: (row) => el('span', { text: row.file.name, dir: 'ltr' }) }, { label: t('dw_file_size'), render: (row) => fmtBytes(row.file.size) },
      { label: t('dw_level'), render: (row) => el('select', { onchange: (e) => { row.levelId = Number(e.target.value); } }, levels.map((l) => { const o = el('option', { value: l.id, text: levelLabel(l) }); if (l.id === row.levelId) o.selected = true; return o; })) },
    ] }));
  });
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'mode', label: t('dw_mode'), type: 'select', value: project.default_mode || settings.default_mode || 'design', options: MODES.map((m) => ({ value: m, label: modeLabel(m) })) }),
      field({ name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: project.ram_bands || settings.ram_bands || 'all', options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })) }),
      field({ name: 'mesh', label: t('dw_mesh'), type: 'select', value: project.mesh || settings.mesh || 'bottom', options: MESHES.map((m) => ({ value: m, label: meshLabel(m) })) }),
      field({ name: 'rotate', label: t('dw_rotate'), type: 'select', value: project.rotate || settings.rotate || 'auto', options: ROTATIONS.map((m) => ({ value: m, label: rotateLabel(m) })) }),
      field({ name: 'beam_design', label: t('dw_beam_design'), type: 'select', value: project.beam_design || settings.beam_design || 'ram', options: BEAM_DESIGNS.map((m) => ({ value: m, label: beamDesignLabel(m) })) }),
    ]),
    field({ name: 'revision', label: t('dw_revision'), value: '', dir: 'ltr', hint: t('dw_revision_hint') }),
    field({ name: 'notes', label: t('dw_run_notes'), type: 'textarea', value: '', rows: 2, hint: t('dw_run_notes_hint') }),
    el('div.field', {}, [el('label', { text: t('dw_files_multi') }), fileInput]), mapHost,
    el('div.tiny.muted', { text: `${t('dw_numbering')}: ${exampleNo(settings, project, preselected || levels[0])}`, dir: 'ltr' }), status,
  ]);
  const { close } = openModal({
    title: `${t('dw_generate')} — ${project.code}`, size: 'wide', body: form,
    footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn', { type: 'button', onclick: async (event) => {
        const button = event.currentTarget;
        const data = readForm(form);
        if (!picked.length) { fileInput.focus(); return; }
        button.disabled = true;
        const results = [];
        for (let i = 0; i < picked.length; i++) {
          const { file, levelId } = picked[i];
          status.textContent = `${fill('dw_batch_progress', { n: i + 1, total: picked.length })} ${file.name}`;
          busy(true, `${t('dw_generating')} — ${file.name}`);
          try { const { run } = await api.generate(levelId, file, { mode: data.mode, ram_bands: data.ram_bands, mesh: data.mesh, beam_design: data.beam_design, rotate: data.rotate, revision: data.revision || undefined, notes: data.notes || undefined }); results.push({ ok: true, run, file }); }
          catch (error) { results.push({ ok: false, error, file }); }
          finally { busy(false); }
        }
        const ok = results.filter((r) => r.ok);
        status.textContent = fill('dw_batch_done', { ok: ok.length, fail: results.length - ok.length });
        if (ok.length === results.length) toast(t('dw_generated'), 'success'); else toastError(results.find((r) => !r.ok).error);
        if (results.length === 1 && ok.length === 1) { close(); navigate(`projects/${project.id}/run/${ok[0].run.id}`); return; }
        if (ok.length) { close(); render(); return; }
        button.disabled = false;
      } }, [icon('play', 16), t('dw_generate')]),
    ]),
  });
}

// ------------------------------------------------------------------------------------------------- project
async function projectPage(projectId) {
  const body = el('div');
  async function load() {
    clear(body).append(el('div.loading-page', { text: t('loading') }));
    let data;
    try { data = await api.project(projectId); } catch (error) { clear(body).append(el('div.alert.danger', { text: error.localised || error.message })); return; }
    const { project, levels, runs, settings, files, projects, submittals } = data;
    clear(body);
    body.append(pageHeader(`${project.code} · ${pick(project, 'name')}`, [
      el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate('projects') }, [icon('back', 16), t('back')]),
      el('button.btn-secondary.btn', { type: 'button', onclick: () => openProjectForm(project, load) }, [icon('edit', 16), t('edit')]),
      levels.length ? el('button.btn', { type: 'button', onclick: () => openGenerateForm(project, levels, settings, null) }, [icon('play', 16), t('dw_generate')]) : null,
      el('button.btn-danger.btn', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_delete_project_confirm')))) return; try { await api.deleteProject(project.id); toast(t('deleted'), 'success'); navigate('projects'); } catch (error) { toastError(error); } } }, [icon('trash', 16), t('delete')]),
    ]));
    const item = (label, value, dir) => el('div.detail-item', {}, [el('div.k', { text: label }), el('div.v', { text: value || '—', dir })]);
    body.append(el('div.card', {}, [el('div.card-body', {}, [el('div.detail-grid', {}, [
      item(t('dw_client'), project.client, 'ltr'), item(t('dw_consultant'), project.consultant, 'ltr'), item(t('dw_contractor'), project.contractor, 'ltr'), item(t('dw_location'), project.location, 'ltr'),
      item(t('dw_prepared'), settings.designer || project.prepared || settings.prepared, 'ltr'), item(t('dw_checked'), project.checked || settings.checked, 'ltr'), item(t('dw_approved'), project.approved || settings.approved, 'ltr'),
      item(t('dw_default_mode'), modeLabel(project.default_mode)), item(t('dw_ram_bands'), bandsLabel(project.ram_bands)), item(t('dw_mesh'), meshLabel(project.mesh)), item(t('dw_beam_design'), beamDesignLabel(project.beam_design)), item(t('dw_rotate'), rotateLabel(project.rotate)),
      item(t('dw_numbering'), exampleNo(settings, project, levels[0]), 'ltr'),
    ]), project.notes ? el('div.small.muted.mt-1', { text: project.notes }) : null])]));
    const tabs = el('div.tabs');
    const panel = el('div');
    const TABS = [
      { key: 'levels', label: t('dw_tab_levels'), build: () => levelsPanel() },
      { key: 'files', label: t('dw_tab_files'), build: () => filesPanel() },
      { key: 'history', label: t('dw_tab_history'), build: () => historyPanel() },
      { key: 'submittals', label: t('dw_tab_submittals'), build: () => submittalsPanel(project, levels, runs, submittals || [], settings, load) },
      { key: 'quantities', label: t('dw_tab_quantities'), build: () => quantitiesPanel(project) },
      { key: 'beam_types', label: t('dw_tab_beam_types'), build: () => beamTypesPanel(project, projects, load) },
    ];
    const draw = () => { clear(tabs); for (const tab of TABS) tabs.append(el('button', { type: 'button', class: tab.key === projectTab ? 'active' : '', text: tab.label, onclick: () => { projectTab = tab.key; history.replaceState(null, '', `#/projects/${project.id}/tab/${tab.key}`); draw(); clear(panel).append(tab.build()); } })); };
    draw();
    panel.append((TABS.find((x) => x.key === projectTab) || TABS[0]).build());
    body.append(tabs, panel);

    function levelsPanel() {
      const host = el('div');
      host.append(el('div.card', {}, [
        el('div.card-header', {}, [el('h3', { text: t('dw_levels') }), el('div.spacer'), el('button.btn.btn-sm', { type: 'button', onclick: () => openLevelForm(project.id, null, load) }, [icon('plus', 14), t('dw_new_level')])]),
        el('div.card-body.flush', {}, [levels.length ? dataTable({ rows: levels, columns: [
          { label: t('dw_sort_order'), className: 'num', render: (row) => row.sort_order },
          { label: t('dw_level_code'), render: (row) => el('span.bold', { text: row.code, dir: 'ltr' }) },
          { label: t('dw_level_name'), render: (row) => el('span', { text: [row.name, row.zone].filter(Boolean).join(' - '), dir: 'ltr' }) },
          { label: t('dw_wall_thickness'), className: 'num', render: (row) => row.wall_thickness || '—' },
          { label: t('dw_runs'), className: 'num', render: (row) => row.run_count },
          { label: t('dw_last_rev'), render: (row) => (row.last_revision != null ? `REV ${row.last_revision}` : '—') },
          { label: t('dw_last_run'), render: (row) => (row.last_run_at ? formatDate(row.last_run_at) : '—') },
          { label: t('dw_ram_failed'), render: (row) => (row.punching?.ram_failed?.length ? el('span.badge.red', { text: row.punching.ram_failed.join(', '), dir: 'ltr' }) : '—') },
          { label: t('dw_reference_short'), render: (row) => (row.reference ? el('span.badge.green', { text: `${row.reference.summary?.columns ?? '?'} ${t('dw_reference_columns')} · ${(row.reference.summary?.grid_x || []).join('')}/${(row.reference.summary?.grid_y || []).join('')}`, dir: 'ltr' }) : '—') },
          { label: t('actions'), render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
            el('button.btn.btn-sm', { type: 'button', title: t('dw_generate'), onclick: () => openGenerateForm(project, levels, settings, row) }, [icon('play', 14), t('dw_generate_for')]),
            el('button.btn-secondary.btn.btn-sm', { type: 'button', title: t('dw_reference'), onclick: () => openReferenceForm(row, load) }, [icon('upload', 14), t('dw_reference_short')]),
            el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('edit'), onclick: () => openLevelForm(project.id, row, load) }, [icon('edit', 14)]),
            el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('delete'), onclick: async () => { if (!(await confirmDialog(t('dw_delete_level_confirm')))) return; try { await api.deleteLevel(row.id); toast(t('deleted'), 'success'); load(); } catch (error) { toastError(error); } } }, [icon('trash', 14)]),
          ]) },
        ] }) : el('div.empty', {}, [icon('layers', 40), el('div', { text: t('dw_no_levels') })])]),
      ]));
      host.append(el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: t('dw_runs') })]), el('div.card-body.flush', {}, [runsTable(runs, project, load)])]));
      return host;
    }
    function filesPanel() {
      const host = el('div');
      host.append(el('div.alert.info', { text: t('dw_files_hint') }));
      for (const cat of FILE_CATEGORIES) {
        const mine = (files || []).filter((f) => f.category === cat);
        const generated = cat === 'pt_design' || cat === 'pt_shop' ? runs.filter((r) => r.status !== 'failed' && r.status !== 'running' && (cat === 'pt_design' ? r.mode === 'design' : r.mode === 'shop')) : [];
        const rows = [...generated.map((r) => ({ generated: true, id: `run-${r.id}`, run: r, name: `${r.prefix}-${r.level_code}_REV${r.revision}.zip`, bytes: null, revision: r.revision, note: r.notes || t('dw_generated_package'), created_at: r.created_at, uploaded_by_name: r.created_by_name, level_code: r.level_code, status: r.status })), ...mine];
        const input = el('input', { type: 'file', style: { display: 'none' } });
        input.addEventListener('change', async () => {
          const file = input.files?.[0]; if (!file) return;
          const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
            field({ name: 'level_id', label: t('dw_level'), type: 'select', value: '', options: [{ value: '', label: '—' }, ...levels.map((l) => ({ value: l.id, label: levelLabel(l) }))] }),
            field({ name: 'revision', label: t('dw_file_rev'), value: '', dir: 'ltr' }), field({ name: 'note', label: t('dw_file_note'), value: '' }),
          ]);
          const { close } = openModal({ title: `${t('dw_upload_file')} — ${file.name}`, body: form, footer: el('div.row', {}, [
            el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
            el('button.btn', { type: 'button', text: t('save'), onclick: async () => { const d = readForm(form); try { busy(true); await api.uploadFile(project.id, file, { category: cat, level_id: d.level_id, revision: d.revision, note: d.note }); toast(t('saved'), 'success'); close(); load(); } catch (error) { toastError(error); } finally { busy(false); } } }),
          ]) });
        });
        host.append(el('div.card', {}, [
          el('div.card-header', {}, [el('h3', { text: t(`dw_files_${cat}`) }), el('span.badge.grey', { text: String(rows.length) }), el('div.spacer'), input, el('button.btn.btn-sm', { type: 'button', onclick: () => input.click() }, [icon('upload', 14), t('dw_upload_file')])]),
          el('div.card-body.flush', {}, [rows.length ? dataTable({ rows, columns: [
            { label: t('dw_file_name'), render: (row) => el('div', {}, [el('div.bold', { text: row.name, dir: 'ltr' }), row.generated ? el('div.tiny.muted', { text: `${t('dw_run')} #${row.run.serial} · ${levelLabel({ code: row.run.level_code, name: row.run.level_name, zone: row.run.level_zone })}`, dir: 'ltr' }) : null]) },
            { label: t('dw_level'), render: (row) => row.level_code || '—' }, { label: t('dw_file_rev'), render: (row) => row.revision || '—' },
            { label: t('status'), render: (row) => (row.generated ? statusBadge(row.status) : '—') }, { label: t('dw_file_note'), render: (row) => row.note || '—' },
            { label: t('dw_file_size'), render: (row) => (row.bytes != null ? fmtBytes(row.bytes) : '—') }, { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
            { label: t('actions'), render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
              row.generated ? el('a.btn.btn-sm', { href: api.runZipUrl(row.run.id) }, [icon('download', 14), 'ZIP']) : el('a.btn.btn-sm', { href: api.fileUrl(row.id) }, [icon('download', 14), (isRTL() ? 'تحميل' : 'Download')]),
              row.generated ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => navigate(`projects/${project.id}/run/${row.run.id}`) }, [icon('chevron', 14), t('open')]) : el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_delete_file_confirm')))) return; try { await api.deleteFile(row.id); toast(t('deleted'), 'success'); load(); } catch (error) { toastError(error); } } }, [icon('trash', 14)]),
            ]) },
          ] }) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_files_none') })])]),
        ]));
      }
      return host;
    }
    function historyPanel() {
      const host = el('div');
      host.append(el('div.alert.info', { text: t('dw_history_hint') }));
      for (const level of levels) {
        const mine = runs.filter((r) => r.level_id === level.id).sort((a, b) => a.serial - b.serial);
        const rows = mine.map((r, i) => { const w = runWeights(r); const prev = mine[i - 1] ? runWeights(mine[i - 1]) : null; return { ...r, w, delta: prev ? (w.T + w.B) - (prev.T + prev.B) : null }; }).reverse();
        host.append(el('div.card', {}, [
          el('div.card-header', {}, [el('h3', { text: levelLabel(level), dir: 'ltr' }), el('span.badge.grey', { text: String(rows.length) })]),
          el('div.card-body.flush', {}, [rows.length ? dataTable({ rows, onRowClick: (row) => navigate(`projects/${project.id}/run/${row.id}`), columns: [
            { label: t('dw_serial'), className: 'num', render: (r) => `#${r.serial}` }, { label: t('dw_revision'), render: (r) => `REV ${r.revision}` }, { label: t('dw_mode'), render: (r) => modeLabel(r.mode) },
            { label: t('status'), render: (r) => statusBadge(r.status) }, { label: t('dw_run_notes'), render: (r) => el('span.small', { text: r.notes || '—' }) },
            { label: t('dw_sheets'), className: 'num', render: (r) => r.sheet_count }, { label: t('dw_weight_t'), className: 'num', render: (r) => num(r.w.T, 0) }, { label: t('dw_weight_b'), className: 'num', render: (r) => num(r.w.B, 0) },
            { label: t('dw_delta'), className: 'num', render: (r) => (r.delta == null ? '—' : el('span', { class: r.delta > 0 ? 'text-danger' : '', text: `${r.delta > 0 ? '+' : ''}${num(r.delta, 0)}` })) },
            { label: t('dw_date'), render: (r) => formatDateTime(r.created_at) },
          ] }) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_history_none') })])]),
        ]));
      }
      return host;
    }
  }
  await load();
  return body;
}
function runWeights(run) {
  const w = { T: 0, B: 0 };
  for (const s of run.sheets || []) { if (!s.weight) continue; if (/TOP/i.test(s.title)) w.T += s.weight; else if (/BOTTOM/i.test(s.title)) w.B += s.weight; }
  return w;
}
function runsTable(runs, project, reload) {
  return dataTable({ rows: runs, empty: t('dw_no_runs'), onRowClick: (row) => navigate(`projects/${project.id}/run/${row.id}`), columns: [
    { label: t('dw_serial'), className: 'num', render: (row) => `#${row.serial}` },
    { label: t('dw_level'), render: (row) => el('span', { text: levelLabel({ code: row.level_code, name: row.level_name, zone: row.level_zone }), dir: 'ltr' }) },
    { label: t('dw_mode'), render: (row) => modeLabel(row.mode) }, { label: t('dw_revision'), render: (row) => `REV ${row.revision}` }, { label: t('dw_sheets'), className: 'num', render: (row) => row.sheet_count },
    { label: t('status'), render: (row) => statusBadge(row.status) }, { label: t('dw_run_notes'), render: (row) => el('span.small', { text: row.notes || row.error || '—' }) },
    { label: t('dw_date'), render: (row) => formatDateTime(row.created_at) },
    { label: t('actions'), render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
      row.status !== 'failed' && row.status !== 'running' ? el('a.btn.btn-sm', { href: api.runZipUrl(row.id), title: t('dw_download_zip') }, [icon('download', 14), 'ZIP']) : null,
      el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('delete'), onclick: async () => { if (!(await confirmDialog(t('dw_delete_run_confirm')))) return; try { await api.deleteRun(row.id); toast(t('deleted'), 'success'); reload(); } catch (error) { toastError(error); } } }, [icon('trash', 14)]),
    ]) },
  ] });
}
function quantitiesPanel(project) {
  const host = el('div');
  host.append(el('div.alert.info', { text: t('dw_quantities_hint') }));
  const body = el('div.loading-page', { text: t('loading') });
  host.append(body);
  (async () => {
    let q, costData;
    try { q = await api.quantities(project.id); costData = await api.cost(project.id); } catch (error) { clear(body).append(el('div.alert.danger', { text: error.localised || error.message })); return; }
    clear(body); body.classList.remove('loading-page');
    if (!q.levels.length) { body.append(el('div.empty', {}, [icon('empty', 40), el('div', { text: t('dw_no_quantities') })])); return; }
    const T = q.totals;
    const rowsAll = [...q.levels, { id: t('dw_qty_totals'), name: '', level_code: '', totals: true, steel: T.steel, concrete: T.concrete, cables: T.cables }];
    const cell = (v, d) => el('span', { text: num(v, d), dir: 'ltr' });
    const levelCell = (row) => el('div', {}, [el('div.bold', { text: row.totals ? row.id : `${row.level_code} · ${row.name}`, dir: 'ltr' }), row.totals ? null : el('div.tiny.muted', { text: `${t('dw_qty_source')}: #${row.run_serial} REV ${row.revision} · ${modeLabel(row.mode)}`, dir: 'ltr' })]);
    const dias = T.steel.byDia.map((d) => d.dia);
    const exportBtn = (name, rows) => el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => downloadText(name, csvOf(rows)) }, [icon('download', 14), t('dw_export_csv')]);
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_steel') }), el('div.spacer'), exportBtn(`${project.code}_steel.csv`, [['LEVEL', 'TOP kg', 'BOTTOM kg', 'OTHER kg', 'MESH kg', 'TOTAL kg', 'kg/m2', ...dias.map((d) => `T${d} kg`)], ...rowsAll.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.steel.top_kg, r.steel.bottom_kg, r.steel.other_kg, r.steel.mesh_kg ?? 0, r.steel.kg, r.steel.kg_per_m2 ?? '', ...dias.map((d) => r.steel.byDia.find((x) => x.dia === d)?.kg ?? 0)])])]),
      el('div.card-body.flush', {}, [dataTable({ rows: rowsAll, columns: [
        { label: t('dw_level'), render: levelCell }, { label: t('dw_qty_top'), className: 'num', render: (r) => cell(r.steel.top_kg, 0) }, { label: t('dw_qty_bottom'), className: 'num', render: (r) => cell(r.steel.bottom_kg, 0) },
        { label: t('dw_qty_other'), className: 'num', render: (r) => cell(r.steel.other_kg, 0) }, { label: t('dw_mesh_kg'), className: 'num', render: (r) => cell(r.steel.mesh_kg ?? 0, 0) },
        { label: t('dw_qty_kg'), className: 'num', render: (r) => el('span.bold', { text: num(r.steel.kg, 0), dir: 'ltr' }) }, { label: t('dw_qty_kg_m2'), className: 'num', render: (r) => cell(r.steel.kg_per_m2, 2) },
        ...dias.map((d) => ({ label: `T${d}`, className: 'num', render: (r) => cell(r.steel.byDia.find((x) => x.dia === d)?.kg ?? 0, 0) })),
      ] })]),
    ]));
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_concrete') }), el('div.spacer'), exportBtn(`${project.code}_concrete.csv`, [['LEVEL', 'THK mm', 'GROSS m2', 'OPENINGS m2', 'NET m2', 'SLAB m3', 'DROPS m3', 'BEAMS m3', 'TOTAL m3', 'FORMWORK m2'], ...rowsAll.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.concrete.thickness ?? '', r.concrete.gross_area_m2, r.concrete.openings_m2, r.concrete.net_area_m2, r.concrete.slab_m3, r.concrete.drops_m3, r.concrete.beams_m3, r.concrete.total_m3, r.concrete.formwork_m2])])]),
      el('div.card-body.flush', {}, [dataTable({ rows: rowsAll, columns: [
        { label: t('dw_level'), render: levelCell }, { label: t('dw_qty_thk'), className: 'num', render: (r) => (r.concrete.thickness ? cell(r.concrete.thickness, 0) : '—') },
        { label: t('dw_qty_gross'), className: 'num', render: (r) => cell(r.concrete.gross_area_m2) }, { label: t('dw_qty_openings'), className: 'num', render: (r) => cell(r.concrete.openings_m2) }, { label: t('dw_qty_net'), className: 'num', render: (r) => cell(r.concrete.net_area_m2) },
        { label: t('dw_qty_slab'), className: 'num', render: (r) => cell(r.concrete.slab_m3) }, { label: t('dw_qty_drops'), className: 'num', render: (r) => cell(r.concrete.drops_m3) }, { label: t('dw_qty_beams'), className: 'num', render: (r) => cell(r.concrete.beams_m3) },
        { label: t('dw_qty_total_m3'), className: 'num', render: (r) => el('span.bold', { text: num(r.concrete.total_m3), dir: 'ltr' }) }, { label: t('dw_qty_formwork'), className: 'num', render: (r) => cell(r.concrete.formwork_m2) },
      ] })]),
    ]));
    const pt = rowsAll.filter((r) => r.cables);
    if (pt.length) body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_qty_cables') }), el('div.spacer'), exportBtn(`${project.code}_cables.csv`, [['LEVEL', 'TENDONS', 'STRANDS', 'TENDON m', 'STRAND m', 'CUTTING m', 'STRAND kg', 'kg/m2', 'LIVE', 'DEAD', 'DUCT 20x50 m', 'DUCT 20x70 m'], ...pt.map((r) => [r.totals ? 'TOTAL' : `${r.level_code} ${r.name}`, r.cables.tendons, r.cables.strands, r.cables.tendon_m, r.cables.strand_m, r.cables.cutting_m, r.cables.kg, r.cables.kg_per_m2 ?? '', r.cables.live_ends, r.cables.dead_ends, r.cables.duct_small_m, r.cables.duct_large_m])])]),
      el('div.card-body.flush', {}, [dataTable({ rows: pt, columns: [
        { label: t('dw_level'), render: levelCell }, { label: t('dw_qty_tendons'), className: 'num', render: (r) => cell(r.cables.tendons, 0) }, { label: t('dw_qty_strands'), className: 'num', render: (r) => cell(r.cables.strands, 0) },
        { label: t('dw_qty_tendon_m'), className: 'num', render: (r) => cell(r.cables.tendon_m, 0) }, { label: t('dw_qty_strand_m'), className: 'num', render: (r) => cell(r.cables.strand_m, 0) }, { label: t('dw_qty_cutting_m'), className: 'num', render: (r) => cell(r.cables.cutting_m, 0) },
        { label: t('dw_qty_strand_kg'), className: 'num', render: (r) => el('span.bold', { text: num(r.cables.kg, 0), dir: 'ltr' }) }, { label: t('dw_qty_kg_m2'), className: 'num', render: (r) => cell(r.cables.kg_per_m2, 2) },
        { label: t('dw_qty_live'), className: 'num', render: (r) => cell(r.cables.live_ends, 0) }, { label: t('dw_qty_dead'), className: 'num', render: (r) => cell(r.cables.dead_ends, 0) },
        { label: t('dw_qty_duct_small'), className: 'num', render: (r) => cell(r.cables.duct_small_m, 0) }, { label: t('dw_qty_duct_large'), className: 'num', render: (r) => cell(r.cables.duct_large_m, 0) },
      ] })]),
    ]));
    const costHost = el('div');
    const RATE_KEYS = ['steel_per_ton', 'rebar_labour_per_ton', 'concrete_per_m3', 'formwork_per_m2', 'strand_per_kg', 'anchor_live', 'anchor_dead', 'duct_per_m', 'pt_labour_per_m2', 'markup_pct', 'vat_pct'];
    const ratesForm = el('form', { onsubmit: (e) => e.preventDefault() }, [el('div.grid.grid-4', {}, RATE_KEYS.map((k) => field({ name: k, label: t(`dw_rate_${k}`), type: 'number', value: costData.cost.rates[k], min: 0, step: 0.01 })))]);
    const drawCost = (c) => {
      clear(costHost);
      const cur = c.currency;
      const rowsCost = [...c.levels.map((l, i) => ({ ...l, level_code: q.levels[i]?.level_code || l.id })), { id: t('dw_qty_totals'), totals: true, ...c.totals }];
      const lineKeys = c.totals.lines.map((l) => l.key);
      costHost.append(dataTable({ rows: rowsCost, columns: [
        { label: t('dw_level'), render: (r) => el('span.bold', { text: r.totals ? r.id : `${r.level_code} · ${r.name}`, dir: 'ltr' }) },
        ...lineKeys.map((k) => ({ label: t(`dw_cost_${k}`), className: 'num', render: (r) => cell(r.lines.find((l) => l.key === k)?.amount, 0) })),
        { label: t('dw_cost_direct'), className: 'num', render: (r) => cell(r.direct, 0) }, { label: t('dw_cost_markup'), className: 'num', render: (r) => cell(r.markup, 0) }, { label: t('dw_cost_vat'), className: 'num', render: (r) => cell(r.vat, 0) },
        { label: `${t('dw_cost_total')} (${cur})`, className: 'num', render: (r) => el('span.bold', { text: num(r.total, 0), dir: 'ltr' }) }, { label: t('dw_cost_per_m2'), className: 'num', render: (r) => cell(r.per_m2, 0) },
      ] }));
      costHost.append(el('div.card-body', {}, [dataTable({ rows: c.totals.lines, columns: [
        { label: t('dw_cost_item'), render: (l) => t(`dw_cost_${l.key}`) }, { label: t('dw_cost_unit'), render: (l) => l.unit }, { label: t('dw_cost_qty'), className: 'num', render: (l) => cell(l.qty, 2) },
        { label: `${t('dw_cost_rate')} (${cur})`, className: 'num', render: (l) => cell(l.rate, 2) }, { label: `${t('dw_cost_amount')} (${cur})`, className: 'num', render: (l) => el('span.bold', { text: num(l.amount, 0), dir: 'ltr' }) },
      ] })]));
    };
    drawCost(costData.cost);
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_cost') }), el('div.spacer'),
        exportBtn(`${project.code}_cost.csv`, [['ITEM', 'UNIT', 'QTY', 'RATE', 'AMOUNT'], ...costData.cost.totals.lines.map((l) => [l.key, l.unit, l.qty, l.rate, l.amount]), ['DIRECT', '', '', '', costData.cost.totals.direct], ['MARKUP', '', '', '', costData.cost.totals.markup], ['VAT', '', '', '', costData.cost.totals.vat], ['TOTAL', '', '', '', costData.cost.totals.total]]),
        el('button.btn.btn-sm', { type: 'button', onclick: async () => { try { costData = await api.cost(project.id, readForm(ratesForm)); drawCost(costData.cost); } catch (error) { toastError(error); } } }, [icon('play', 14), t('dw_cost_apply')])]),
      el('div.card-body', {}, [el('div.small.muted', { text: t('dw_cost_hint') }), ratesForm]), el('div.card-body.flush', {}, [costHost]),
    ]));
  })();
  return host;
}
function beamTypesPanel(project, others, reload) {
  const host = el('div');
  host.append(el('div.alert.info', { text: t('dw_bt_hint') }));
  const body = el('div.loading-page', { text: t('loading') });
  host.append(body);
  (async () => {
    let types;
    try { types = (await api.beamTypes(project.id)).beam_types; } catch (error) { clear(body).append(el('div.alert.danger', { text: error.localised || error.message })); return; }
    clear(body); body.classList.remove('loading-page');
    const sourceOf = (tp) => (tp.source?.imported ? fill('dw_bt_source_import', { code: tp.source.project_code }) : tp.source?.run_id ? fill('dw_bt_source_run', { run: `#${tp.source.run_id}`, level: tp.source.level || '', rev: tp.source.revision || '' }) : '—');
    body.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_beams_types') }), el('span.badge.grey', { text: String(types.length) }), el('div.spacer'), el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => openBeamTypesImport(project, others, reload) }, [icon('download', 14), t('dw_bt_import')])]),
      el('div.card-body.flush', {}, [types.length ? dataTable({ rows: types, columns: [
        { label: t('dw_beam_type'), render: (r) => el('span.bold', { text: r.mark, dir: 'ltr' }) }, { label: t('dw_beam_section'), render: (r) => el('span', { text: `${r.width} x ${r.depth}`, dir: 'ltr' }) },
        { label: t('dw_beam_top'), render: (r) => r.top?.text || '—' }, { label: t('dw_beam_bottom'), render: (r) => r.bottom?.text || '—' }, { label: t('dw_beam_stirrups'), render: (r) => (r.stirrups ? `T${r.stirrups.dia}-${r.stirrups.legs}L @ ${r.stirrups.spacing}` : '—') },
        { label: t('dw_bt_source'), render: (r) => el('span.small', { text: sourceOf(r), dir: 'ltr' }) }, { label: t('dw_date'), render: (r) => formatDate(r.created_at) },
        { label: t('actions'), render: (r) => el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_bt_delete_confirm')))) return; try { await api.deleteBeamType(project.id, r.mark); toast(t('deleted'), 'success'); reload(); } catch (error) { toastError(error); } } }, [icon('trash', 14)]) },
      ] }) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_bt_empty') })])]),
    ]));
  })();
  return host;
}
function openBeamTypesImport(project, others, after) {
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.small.muted', { text: t('dw_bt_import_hint') }),
    field({ name: 'from_project_id', label: t('dw_bt_from'), type: 'select', value: '', options: (others || []).map((p) => ({ value: p.id, label: `${p.code} · ${p.name || ''} (${p.beam_types})` })) }),
  ]);
  const { close } = openModal({ title: t('dw_bt_import'), body: form, footer: el('div.row', {}, [
    el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
    el('button.btn', { type: 'button', text: t('save'), onclick: async () => { const d = readForm(form); if (!d.from_project_id) return; try { const res = await api.importBeamTypes(project.id, { from_project_id: Number(d.from_project_id) }); toast(fill('dw_bt_imported', { added: res.added, skipped: res.skipped }), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }),
  ]) });
}

// ------------------------------------------------------------------------------------------------------ run
async function runPage(projectId, runId) {
  const page = el('div');
  let data;
  try { data = await api.run(runId); } catch (error) { page.append(el('div.alert.danger', { text: error.localised || error.message })); return page; }
  const { run, project } = data;
  const level = { code: run.level_code, name: run.level_name, zone: run.level_zone };
  const produced = run.status !== 'failed' && run.status !== 'running';
  page.append(pageHeader(`${project.code} · ${levelLabel(level)} · REV ${run.revision}`, [
    el('button.btn-secondary.btn', { type: 'button', onclick: () => navigate(`projects/${project.id}`) }, [icon('back', 16), t('back')]),
    produced && run.status !== 'issued' && run.status !== 'blocked' ? el('button.btn-success.btn', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_issue_confirm'), { danger: false, confirmLabel: t('dw_issue') }))) return; try { await api.updateRun(run.id, { status: 'issued' }); toast(t('saved'), 'success'); render(); } catch (error) { toastError(error); } } }, [icon('check', 16), t('dw_issue')]) : null,
    produced ? el('a.btn', { href: api.runZipUrl(run.id) }, [icon('download', 16), t('dw_download_zip')]) : null,
    produced ? el('button.btn-secondary.btn', { type: 'button', onclick: async () => { try { await api.openRunFolder(run.id); } catch (error) { toastError(error); } } }, [icon('folder', 16), t('dw_open_folder')]) : null,
    produced && run.quantities ? el('button.btn-secondary.btn', { type: 'button', title: t('dw_takeoff_hint'), onclick: () => {
      const input = el('input', { type: 'file', accept: '.dxf' });
      input.onchange = async () => { const file = input.files && input.files[0]; if (!file) return; try { busy(true); const res = await api.takeoff(run.id, file); const d = res.takeoff; toast(fill('dw_takeoff_updated', { changed: d.changed, bars: d.bars, kg: (d.delta.kg >= 0 ? '+' : '') + d.delta.kg }), 'success'); render(); } catch (error) { toastError(error); } finally { busy(false); } };
      input.click();
    } }, [icon('upload', 16), t('dw_takeoff_update')]) : null,
    run.source_file ? el('button.btn-secondary.btn', { type: 'button', title: t('dw_regenerate_hint'), onclick: async () => { try { busy(true, t('dw_generating')); const res = await api.regenerate(run.id, { notes: run.notes }); toast(t('dw_generated'), 'success'); navigate(`projects/${project.id}/run/${res.run.id}`); } catch (error) { toastError(error); } finally { busy(false); } } }, [icon('refresh', 16), t('dw_regenerate')]) : null,
    el('button.btn-danger.btn', { type: 'button', onclick: async () => { if (!(await confirmDialog(t('dw_delete_run_confirm')))) return; try { await api.deleteRun(run.id); toast(t('deleted'), 'success'); navigate(`projects/${project.id}`); } catch (error) { toastError(error); } } }, [icon('trash', 16), t('delete')]),
  ]));
  const kpi = (label, value) => el('div.kpi', {}, [el('div.label', { text: label }), el('div.value', { text: value, dir: 'ltr' })]);
  page.append(el('div.kpi-grid', {}, [
    kpi(t('dw_serial'), `#${run.serial}`), kpi(t('dw_sheets'), String(run.sheet_count)), kpi(t('dw_mode'), modeLabel(run.mode)), kpi(t('dw_ram_bands'), bandsLabel(run.ram_bands)), kpi(t('dw_mesh'), meshLabel(run.mesh)),
    kpi(t('dw_beam_design'), beamDesignLabel(run.beam_design)), kpi(t('dw_rotate'), rotateLabel(run.rotate)), kpi(t('dw_designer'), run.created_by_name || '—'),
    kpi(t('dw_duration'), run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)} s` : '—'), kpi(t('dw_source'), run.source_name || run.source_file || '—'),
  ]));
  if (run.status === 'failed') page.append(el('div.alert.danger', { text: `${t('dw_run_failed')}: ${run.error || t('error')}` }));
  if (run.punching) page.append(punchingCard(run, project));
  if (run.beam_check) page.append(beamCheckCard(run, project));
  const notesBox = el('textarea', { rows: 2, placeholder: t('dw_run_notes_hint') });
  notesBox.value = run.notes || '';
  page.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_run_notes') }), el('div.spacer'), statusBadge(run.status)]),
    el('div.card-body', {}, [notesBox, el('div.row.mt-1', {}, [el('button.btn.btn-sm', { type: 'button', text: t('dw_save_notes'), onclick: async () => { try { await api.updateRun(run.id, { notes: notesBox.value }); toast(t('saved'), 'success'); } catch (error) { toastError(error); } } })])]),
  ]));
  if (produced && /\.cpt$/i.test(run.source_file || '')) {
    const bsHost = el('div');
    const drawStrips = (info) => { clear(bsHost); if (info) bsHost.append(el('div.row.wrap', { style: { gap: '.5rem', alignItems: 'center' } }, [el('span.badge.green', { text: fill('dw_beams_prepared', { beams: info.beams, spans: info.spans, splitters: info.splitters, removed: Object.values(info.removed || {}).reduce((a, b) => a + b, 0) }) }), el('a.btn.btn-sm', { href: api.beamStripsUrl(run.id) }, [icon('download', 14), t('dw_beams_download')])])); };
    drawStrips(run.beam_strips);
    const types = (run.beams || []).flatMap((lv) => (lv.types || []).map((tp) => ({ ...tp, level: lv.level })));
    const undesigned = (run.beams || []).flatMap((lv) => lv.undesigned || []);
    const addedMarks = (run.beams || []).flatMap((lv) => (lv.added || []).map((tp) => tp.mark));
    page.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('dw_beams') }), el('div.spacer'), el('button.btn.btn-sm', { type: 'button', onclick: async (e) => { const b = e.currentTarget; b.disabled = true; try { const { beam_strips } = await api.prepareBeamStrips(run.id); drawStrips(beam_strips); toast(t('saved'), 'success'); } catch (error) { toastError(error); } b.disabled = false; } }, [icon('play', 14), t('dw_beams_prepare')])]),
      el('div.card-body', {}, [el('div.small.muted', { text: t('dw_beams_hint') }), bsHost, addedMarks.length ? el('div.mt-1', {}, [el('span.badge.amber', { text: fill('dw_bt_added_on_run', { marks: addedMarks.join(', ') }), dir: 'ltr' })]) : null]),
      types.length ? el('div.card-body.flush', {}, [dataTable({ rows: types, columns: [
        { label: t('dw_beam_type'), render: (r) => el('span.row', { style: { gap: '.3rem', alignItems: 'center' } }, [el('span.bold', { text: `${r.mark}`, dir: 'ltr' }), el('span', { class: `badge ${r.isNew ? 'amber' : 'grey'}`, text: t(r.isNew ? 'dw_bt_new' : 'dw_bt_existing') })]) },
        { label: t('dw_level'), render: (r) => r.level }, { label: t('dw_beam_section'), render: (r) => el('span', { text: `${r.width} x ${r.depth}`, dir: 'ltr' }) },
        { label: t('dw_beam_top'), render: (r) => r.top?.text || '—' }, { label: t('dw_beam_bottom'), render: (r) => r.bottom?.text || '—' }, { label: t('dw_beam_stirrups'), render: (r) => (r.stirrups ? `T${r.stirrups.dia}-${r.stirrups.legs}L @ ${r.stirrups.spacing}` : '—') },
        { label: t('dw_beam_count'), className: 'num', render: (r) => r.count }, { label: t('dw_beam_list'), render: (r) => el('span.small', { text: (r.beams || []).join(', '), dir: 'ltr' }) },
      ] })]) : el('div.card-body', {}, [el('div.small.muted', { text: t('dw_beams_none') })]),
      undesigned.length ? el('div.card-body', {}, [el('div.small', { text: `${t('dw_beams_undesigned')}: ${undesigned.join(', ')}`, dir: 'ltr' })]) : null,
    ]));
  }
  const previewHost = el('div');
  const showPreview = (sheet) => {
    clear(previewHost).append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${sheet.no} — ${sheet.title}`, dir: 'ltr' }), el('div.spacer'), el('a.btn-secondary.btn.btn-sm', { href: api.runFileUrl(run.id, 'preview', `${sheet.file}.svg`), target: '_blank', rel: 'noopener' }, [icon('chevron', 14), t('open')]), el('a.btn.btn-sm', { href: api.runFileUrl(run.id, 'dxf', `${sheet.file}.dxf`, true) }, [icon('download', 14), t('dw_download_dxf')])]),
      el('div.card-body.tight', {}, [el('img', { src: api.runFileUrl(run.id, 'preview', `${sheet.file}.svg`), alt: sheet.no, style: { width: '100%', height: 'auto', display: 'block', background: '#fff' } })]),
    ]));
    previewHost.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };
  page.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_sheets') })]),
    el('div.card-body.flush', {}, [dataTable({ rows: run.sheets, onRowClick: showPreview, columns: [
      { label: t('dw_sheet_no'), render: (row) => el('span.bold', { text: row.no, dir: 'ltr' }) }, { label: t('dw_sheet_title'), render: (row) => el('span', { text: row.title, dir: 'ltr' }) },
      { label: t('dw_level'), render: (row) => el('span', { text: row.level === 'ALL' ? 'ALL' : `${row.level} - ${row.level_name || ''}`, dir: 'ltr' }) }, { label: t('dw_scale'), render: (row) => (row.scale ? `1:${row.scale}` : 'NTS') },
      { label: t('dw_weight'), className: 'num', render: (row) => (row.weight ? row.weight.toLocaleString('en-US') : '—') },
      { label: t('actions'), render: (row) => el('div.row', { style: { gap: '.3rem' } }, [el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => showPreview(row) }, [icon('search', 14), t('dw_preview')]), el('a.btn.btn-sm', { href: api.runFileUrl(run.id, 'dxf', `${row.file}.dxf`, true) }, [icon('download', 14), t('dw_download_dxf')])]) },
    ] })]),
  ]));
  page.append(previewHost);
  if (run.quantities?.totals) {
    const S = run.quantities.totals.steel, C = run.quantities.totals.concrete;
    page.append(el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: t('dw_run_quantities') })]), el('div.card-body', {}, [el('div.detail-grid', {}, [
      el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_kg') }), el('div.v', { text: num(S.kg, 0), dir: 'ltr' })]), el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_kg_m2') }), el('div.v', { text: num(S.kg_per_m2, 2), dir: 'ltr' })]),
      el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_net') }), el('div.v', { text: num(C.net_area_m2), dir: 'ltr' })]), el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_total_m3') }), el('div.v', { text: num(C.total_m3), dir: 'ltr' })]),
      ...(run.quantities.totals.cables ? [el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_tendons') }), el('div.v', { text: num(run.quantities.totals.cables.tendons, 0), dir: 'ltr' })]), el('div.detail-item', {}, [el('div.k', { text: t('dw_qty_strand_kg') }), el('div.v', { text: num(run.quantities.totals.cables.kg, 0), dir: 'ltr' })])] : []),
    ]), ...(run.quantities.levels || []).flatMap((l) => (l.edited || []).map((e) => el('div.tiny.muted.mt-1', { text: `${e.file || ''} · ${e.by || ''} · ${e.date || ''} · ${e.bars} bars · ${e.delta_kg >= 0 ? '+' : ''}${e.delta_kg} kg`, dir: 'ltr' })))])]));
  }
  const list = (title, items) => (items && items.length ? el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: `${title} (${items.length})` })]), el('div.card-body', {}, [el('ul.small', { style: { margin: 0, paddingInlineStart: '1.2rem' }, dir: 'ltr' }, items.map((text) => el('li', { text })))])]) : null);
  page.append(list(t('dw_assumptions'), run.assumptions));
  page.append(list(t('dw_findings'), run.findings));
  if (run.report_md) page.append(el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: t('dw_report') })]), el('div.card-body', {}, [el('pre.report', { text: run.report_md })])]));
  return page;
}
function punchingCard(run, project) {
  const P = run.punching;
  const blocking = P.blocking || [];
  const warnings = (P.warnings || []).filter((id) => !blocking.includes(id));
  const columns = (P.levels || []).flatMap((lv) => (lv.columns || []).map((c) => ({ ...c, level: lv.level, overridden: (lv.overridden || []).includes(c.id) })));
  const shown = columns.filter((c) => c.status !== 'ok' || c.ram_failed || c.overridden || blocking.includes(c.id));
  const statusOf = (c) => { const parts = []; if (c.ram_failed) parts.push(t('dw_punch_in_ram')); parts.push(t(`dw_punch_${c.status}`)); if (c.ssr) parts.push(t('dw_punch_ssr')); if (c.overridden) parts.push(t('dw_punch_mode_bypass')); return parts.join(' · '); };
  const decision = P.decision;
  const body = el('div.card-body', {}, [
    blocking.length ? el('div.alert.danger', {}, [el('strong', { text: fill('dw_punch_blocked', { n: blocking.length, cols: blocking.join(', ') }) })]) : null,
    warnings.length ? el('div.alert.warn', { text: fill('dw_punch_warn', { cols: warnings.join(', ') }) }) : null,
    decision ? el('div.small.mt-1', {}, [el('span.badge.blue', { text: fill('dw_punch_decided', { mode: t(`dw_punch_mode_${decision.mode}`), by: decision.by, date: decision.date }) }), decision.note ? el('span.muted', { text: ` ${decision.note}` }) : null]) : null,
    el('div.tiny.muted.mt-1', { text: t('dw_punch_hint') }),
    shown.length ? dataTable({ rows: shown, columns: [
      { label: t('dw_punch_col'), render: (c) => el('span.bold', { text: `${c.id}`, dir: 'ltr' }) }, { label: t('dw_level'), render: (c) => c.level }, { label: t('dw_punch_loc'), render: (c) => t(`dw_punch_loc_${c.loc}`) },
      { label: t('dw_punch_trib'), className: 'num', render: (c) => `${c.trib_m2}` }, { label: t('dw_punch_vu'), className: 'num', render: (c) => `${c.Vu_kn}` }, { label: t('dw_punch_ratio'), className: 'num', render: (c) => el('span', { class: c.ratio > 1 ? 'text-danger bold' : '', text: `${c.ratio}` }) },
      { label: t('dw_punch_status'), render: (c) => el('span', { class: `badge ${blocking.includes(c.id) ? 'red' : c.status === 'ok' && !c.ram_failed ? 'green' : 'amber'}`, text: statusOf(c) }) },
    ] }) : null,
  ]);
  const act = async (mode, extra = {}) => { try { busy(true, mode === 'thicken' ? t('loading') : t('dw_generating')); const res = await api.punchingDecision(run.id, { mode, ...extra }); toast(mode === 'thicken' ? t('saved') : t('dw_punch_regenerated'), 'success'); navigate(`projects/${project.id}/run/${res.run.id}`); render(); } catch (error) { toastError(error); } finally { busy(false); } };
  const flagged = [...new Set([...blocking, ...warnings])];
  const decide = (mode) => {
    const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
      el('div.alert.warn', { text: t(mode === 'bypass' ? 'dw_punch_bypass_hint' : 'dw_punch_ram_ok_hint') }),
      field({ name: 'columns', label: t('dw_punch_columns'), value: flagged.join(', '), dir: 'ltr', hint: t('dw_punch_all_flagged') }), field({ name: 'note', label: t('dw_punch_note'), type: 'textarea', value: '', rows: 2 }),
      el('label.row', { style: { gap: '.5rem', alignItems: 'flex-start' } }, [el('input', { type: 'checkbox', name: 'acknowledge' }), el('span', { text: t('dw_punch_ack') })]),
    ]);
    const { close } = openModal({ title: t(mode === 'bypass' ? 'dw_punch_bypass' : 'dw_punch_ram_ok'), body: form, footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn-danger.btn', { type: 'button', text: t(mode === 'bypass' ? 'dw_punch_bypass' : 'dw_punch_ram_ok'), onclick: async (e) => { if (!form.querySelector('input[name=acknowledge]').checked) { toast(t('dw_punch_ack'), 'error'); return; } const d = readForm(form); e.currentTarget.disabled = true; close(); await act(mode, { columns: d.columns && d.columns.trim() ? d.columns : 'all', note: d.note || undefined, acknowledge: true }); } }),
    ]) });
  };
  if ((blocking.length || warnings.length) && run.status !== 'superseded') body.append(el('div.row.wrap.mt-1', { style: { gap: '.5rem' } }, [
    el('button.btn-secondary.btn', { type: 'button', title: t('dw_punch_thicken_hint'), onclick: () => act('thicken') }, [icon('edit', 14), t('dw_punch_thicken')]),
    el('button.btn.btn-success', { type: 'button', title: t('dw_punch_ram_ok_hint'), onclick: () => decide('ram_ok') }, [icon('check', 14), t('dw_punch_ram_ok')]),
    el('button.btn-danger.btn', { type: 'button', title: t('dw_punch_bypass_hint'), onclick: () => decide('bypass') }, [icon('bell', 14), t('dw_punch_bypass')]),
    decision ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => act('clear') }, [t('dw_punch_clear')]) : null,
  ]));
  return el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: blocking.length ? t('dw_punch_title') : t('dw_punch_status') }), el('div.spacer'), statusBadge(run.status)]), body]);
}
function beamCheckCard(run, project) {
  const B = run.beam_check;
  const blocking = B.blocking || [];
  const rows = (B.levels || []).flatMap((lv) => (lv.beams || []).map((b) => ({ ...b, level: lv.level })));
  const schedRows = (run.beams || []).flatMap((lv) => lv.beams || []);
  const sched = (id) => schedRows.find((r) => String(r.id).toUpperCase() === String(id).toUpperCase());
  const decision = B.decision;
  const reasonsOf = (b) => [...(b.ram_failed ? [t('dw_beam_in_ram')] : []), ...(b.reasons || []).map((r) => t(`dw_beam_reason_${r}`))].join(' · ');
  const body = el('div.card-body', {}, [
    blocking.length ? el('div.alert.danger', {}, [el('strong', { text: fill('dw_beam_blocked', { n: blocking.length, beams: blocking.join(', ') }) })]) : null,
    decision ? el('div.small.mt-1', {}, [el('span.badge.blue', { text: fill('dw_punch_decided', { mode: t(`dw_beam_mode_${decision.mode}`), by: decision.by, date: decision.date }) }), decision.note ? el('span.muted', { text: ` ${decision.note}` }) : null]) : null,
    el('div.tiny.muted.mt-1', { text: t('dw_bd_hint') }),
    (B.levels || []).some((lv) => (lv.assumed || []).length) ? el('div.tiny.muted', { text: (B.levels || []).flatMap((lv) => lv.assumed || []).join('; '), dir: 'ltr' }) : null,
    rows.length ? dataTable({ rows, columns: [
      { label: t('dw_beam_list'), render: (b) => el('span.bold', { text: `${b.id} ${b.width}x${b.depth}`, dir: 'ltr' }) },
      { label: t('dw_beam_spans'), render: (b) => el('span', { text: (b.spans || []).map((s) => (s.length / 1000).toFixed(1)).join(' + ') + (b.no_supports ? ' ?' : ''), dir: 'ltr', title: b.no_supports ? t('dw_beam_no_supports') : '' }) },
      { label: t('dw_beam_trib'), className: 'num', render: (b) => ((b.trib_mm?.total || 0) / 1000).toFixed(1) }, { label: t('dw_beam_wu'), className: 'num', render: (b) => `${b.loads?.wu ?? '—'}` },
      { label: t('dw_beam_mneg'), className: 'num', render: (b) => `${b.Mneg_max}` }, { label: t('dw_beam_mpos'), className: 'num', render: (b) => `${b.Mpos_max}` }, { label: t('dw_beam_vu'), className: 'num', render: (b) => `${b.Vu}` },
      { label: t('dw_beam_ram_bars'), render: (b) => { const r = sched(b.id); return el('span', { text: r?.ram ? `${r.ram.top?.text || '-'} / ${r.ram.bottom?.text || '-'} / ${r.ram.stirrups?.text || '-'}` : '—', dir: 'ltr' }); } },
      { label: t('dw_beam_office_bars'), render: (b) => el('span', { text: `${b.top?.text || '-'} / ${b.bottom?.text || '-'} / ${b.stirrups?.text || '-'}`, dir: 'ltr' }) },
      { label: t('dw_beam_chosen'), render: (b) => { const r = sched(b.id); return el('span.bold', { text: r ? `${r.mark || '??'}: ${r.top?.text || '-'} / ${r.bottom?.text || '-'} / ${r.stirrups?.text || '-'}` : '—', dir: 'ltr' }); } },
      { label: t('dw_beam_defl'), render: (b) => el('span', { class: b.deflection?.ok ? '' : 'text-danger bold', text: b.deflection?.table_ok ? t('dw_beam_defl_table') : fill('dw_beam_defl_ratio', { r: b.deflection?.ratio }) }) },
      { label: t('dw_beam_status'), render: (b) => el('span', { class: `badge ${blocking.includes(b.id) ? 'red' : b.status === 'ok' ? 'green' : 'amber'}`, text: b.status === 'ok' && !b.ram_failed ? t('dw_beam_ok') : `${t('dw_beam_fail')}: ${reasonsOf(b)}` }) },
    ] }) : null,
  ]);
  const act = async (mode, extra = {}) => { try { busy(true, mode === 'deepen' ? t('loading') : t('dw_generating')); const res = await api.beamDecision(run.id, { mode, ...extra }); toast(mode === 'deepen' ? t('saved') : t('dw_punch_regenerated'), 'success'); navigate(`projects/${project.id}/run/${res.run.id}`); render(); } catch (error) { toastError(error); } finally { busy(false); } };
  const flagged = [...new Set((B.levels || []).flatMap((lv) => lv.failing || []))];
  const decide = (mode) => {
    const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
      el('div.alert.warn', { text: t(mode === 'bypass' ? 'dw_beam_bypass_hint' : 'dw_beam_ram_ok_hint') }),
      field({ name: 'beams', label: t('dw_beam_columns'), value: flagged.join(', '), dir: 'ltr', hint: t('dw_punch_all_flagged') }), field({ name: 'note', label: t('dw_punch_note'), type: 'textarea', value: '', rows: 2 }),
      el('label.row', { style: { gap: '.5rem', alignItems: 'flex-start' } }, [el('input', { type: 'checkbox', name: 'acknowledge' }), el('span', { text: t('dw_punch_ack') })]),
    ]);
    const { close } = openModal({ title: t(mode === 'bypass' ? 'dw_beam_bypass' : 'dw_beam_ram_ok'), body: form, footer: el('div.row', {}, [
      el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
      el('button.btn-danger.btn', { type: 'button', text: t(mode === 'bypass' ? 'dw_beam_bypass' : 'dw_beam_ram_ok'), onclick: async (e) => { if (!form.querySelector('input[name=acknowledge]').checked) { toast(t('dw_punch_ack'), 'error'); return; } const d = readForm(form); e.currentTarget.disabled = true; close(); await act(mode, { beams: d.beams && d.beams.trim() ? d.beams : 'all', note: d.note || undefined, acknowledge: true }); } }),
    ]) });
  };
  if (blocking.length && run.status !== 'superseded') body.append(el('div.row.wrap.mt-1', { style: { gap: '.5rem' } }, [
    el('button.btn-secondary.btn', { type: 'button', title: t('dw_beam_deepen_hint'), onclick: () => act('deepen') }, [icon('edit', 14), t('dw_beam_deepen')]),
    el('button.btn.btn-success', { type: 'button', title: t('dw_beam_ram_ok_hint'), onclick: () => decide('ram_ok') }, [icon('check', 14), t('dw_beam_ram_ok')]),
    el('button.btn-danger.btn', { type: 'button', title: t('dw_beam_bypass_hint'), onclick: () => decide('bypass') }, [icon('bell', 14), t('dw_beam_bypass')]),
    decision ? el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => act('clear') }, [t('dw_punch_clear')]) : null,
  ]));
  return el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: blocking.length ? t('dw_beam_check_title') : t('dw_beam_check') }), el('div.spacer'), el('span.badge.grey', { text: beamDesignLabel(B.design) }), statusBadge(run.status)]), body]);
}

// ---------------------------------------------------------------------------------------------- submittals
const submittalBadge = (status) => el('span', { class: `badge ${status === 'approved' ? 'green' : status === 'approved_as_noted' || status === 'submitted' ? 'blue' : status === 'resubmit' || status === 'rejected' ? 'red' : status === 'withdrawn' ? 'grey' : 'amber'}`, text: t(`dw_sstatus_${status}`) });
function submittalsPanel(project, levels, runs, submittals, settings, reload) {
  const host = el('div');
  host.append(el('div.alert.info', { text: t('dw_submittals_hint') }));
  const usable = runs.filter((r) => r.status !== 'failed' && r.status !== 'running');
  host.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_tab_submittals') }), el('span.badge.grey', { text: String(submittals.length) }), el('div.spacer'), usable.length ? el('button.btn.btn-sm', { type: 'button', onclick: () => openSubmittalForm(project, levels, usable, settings, reload) }, [icon('plus', 14), t('dw_new_submittal')]) : null]),
    el('div.card-body.flush', {}, [submittals.length ? dataTable({ rows: submittals, columns: [
      { label: t('dw_submittal_no'), render: (row) => el('span.bold', { text: row.code, dir: 'ltr' }) }, { label: t('dw_submittal_date'), render: (row) => row.date },
      { label: t('dw_submittal_subject'), render: (row) => el('span', { text: row.subject || '—', dir: 'ltr' }) },
      { label: t('dw_submittal_to'), render: (row) => el('span', { text: [row.to_name, row.attention].filter(Boolean).join(' · ') || '—', dir: 'ltr' }) },
      { label: t('dw_submittal_purpose'), render: (row) => t(`dw_purpose_${row.purpose}`) }, { label: t('dw_submittal_items'), className: 'num', render: (row) => row.items.length },
      { label: t('status'), render: (row) => submittalBadge(row.status) },
      { label: t('dw_submittal_response'), render: (row) => el('span.small', { text: [row.response_date, row.response_notes].filter(Boolean).join(' — ') || '—' }) },
      { label: t('actions'), render: (row) => el('div.row', { style: { gap: '.3rem' } }, [
        el('a.btn.btn-sm', { href: api.submittalFormUrl(row.id), target: '_blank', rel: 'noopener', title: t('dw_submittal_open_form') }, [icon('chevron', 14), t('print')]),
        el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => openSubmittalStatus(row, reload) }, [icon('edit', 14), t('dw_submittal_mark')]),
        el('button.btn-secondary.btn.btn-sm.btn-icon', { type: 'button', title: t('delete'), onclick: async () => { if (!(await confirmDialog(t('dw_delete_submittal_confirm')))) return; try { await api.deleteSubmittal(row.id); toast(t('deleted'), 'success'); reload(); } catch (error) { toastError(error); } } }, [icon('trash', 14)]),
      ]) },
    ] }) : el('div.empty', {}, [icon('empty', 32), el('div', { text: t('dw_no_submittals') })])]),
  ]));
  for (const sub of submittals) {
    host.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${sub.code} · ${sub.subject || ''}`, dir: 'ltr' }), el('div.spacer'), submittalBadge(sub.status)]),
      el('div.card-body.flush', {}, [dataTable({ rows: sub.items, columns: [
        { label: t('dw_sheet_no'), render: (row) => el('span.bold', { text: row.no, dir: 'ltr' }) }, { label: t('dw_sheet_title'), render: (row) => el('span', { text: row.title, dir: 'ltr' }) },
        { label: t('dw_level'), render: (row) => el('span', { text: row.level === 'ALL' ? 'ALL' : `${row.level} - ${row.level_name || ''}`, dir: 'ltr' }) }, { label: t('dw_revision'), render: (row) => `REV ${row.rev}` },
        { label: t('dw_submittal_supersedes'), render: (row) => (row.prev_rev != null ? el('span', { text: `REV ${row.prev_rev} (${row.prev_submittal})`, dir: 'ltr' }) : '—') },
      ] })]),
    ]));
  }
  return host;
}
function openSubmittalForm(project, levels, runs, settings, after) {
  const levelOf = (r) => levelLabel({ code: r.level_code, name: r.level_name, zone: r.level_zone });
  const picked = new Map();
  const runsHost = el('div');
  const sheetsHost = el('div');
  const drawSheets = () => {
    clear(sheetsHost);
    for (const run of runs.filter((r) => picked.has(r.id))) {
      const chosen = picked.get(run.id);
      const sheets = run.sheets.filter((sh) => !(sh.level === 'ALL' && /COVER|INDEX/i.test(sh.title)));
      sheetsHost.append(el('div.card', {}, [
        el('div.card-header', {}, [el('h3', { text: `#${run.serial} · ${levelOf(run)} · REV ${run.revision}`, dir: 'ltr' }), el('div.spacer'), el('label.small', {}, [el('input', { type: 'checkbox', checked: chosen === null, onchange: (e) => { picked.set(run.id, e.target.checked ? null : new Set(sheets.map((x) => x.no))); drawSheets(); } }), ' ', t('dw_submittal_all_sheets')])]),
        el('div.card-body', {}, [el('div.grid.grid-2', {}, sheets.map((sh) => el('label.small', {}, [el('input', { type: 'checkbox', checked: chosen === null || chosen.has(sh.no), disabled: chosen === null, onchange: (e) => { if (e.target.checked) chosen.add(sh.no); else chosen.delete(sh.no); } }), ' ', el('span', { text: `${sh.no} — ${sh.title}`, dir: 'ltr' })])))]),
      ]));
    }
  };
  runsHost.append(dataTable({ rows: runs, columns: [
    { label: '', render: (row) => el('input', { type: 'checkbox', onchange: (e) => { if (e.target.checked) picked.set(row.id, null); else picked.delete(row.id); drawSheets(); } }) },
    { label: t('dw_serial'), className: 'num', render: (row) => `#${row.serial}` }, { label: t('dw_level'), render: (row) => el('span', { text: levelOf(row), dir: 'ltr' }) },
    { label: t('dw_mode'), render: (row) => modeLabel(row.mode) }, { label: t('dw_revision'), render: (row) => `REV ${row.revision}` }, { label: t('status'), render: (row) => statusBadge(row.status) }, { label: t('dw_sheets'), className: 'num', render: (row) => row.sheet_count },
  ] }));
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'to_name', label: t('dw_submittal_to'), value: project.consultant || '', dir: 'ltr' }), field({ name: 'attention', label: t('dw_submittal_attention'), value: '', dir: 'ltr' }),
      field({ name: 'purpose', label: t('dw_submittal_purpose'), type: 'select', value: 'approval', options: PURPOSES.map((p) => ({ value: p, label: t(`dw_purpose_${p}`) })) }),
      field({ name: 'date', label: t('dw_submittal_date'), type: 'date', value: new Date().toISOString().slice(0, 10) }),
    ]),
    field({ name: 'subject', label: t('dw_submittal_subject'), value: '', dir: 'ltr', hint: t('optional') }), field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: '', rows: 2 }),
    el('h4.mt-1', { text: t('dw_submittal_runs') }), runsHost, el('h4.mt-1', { text: t('dw_submittal_sheets') }), sheetsHost,
    el('div.tiny.muted', { text: `${t('dw_submittal_no')}: ${settings.submittal?.prefix || 'SPAN-SUB'}-${project.code}-001`, dir: 'ltr' }),
  ]);
  const { close } = openModal({ title: t('dw_new_submittal'), size: 'wide', body: form, footer: el('div.row', {}, [
    el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
    el('button.btn', { type: 'button', text: t('create'), onclick: async (event) => {
      if (!picked.size) { toast(t('dw_submittal_runs'), 'error'); return; }
      const data = readForm(form);
      const sheets = [...picked.values()].some((v) => v !== null) ? runs.filter((r) => picked.has(r.id)).flatMap((r) => (picked.get(r.id) === null ? r.sheets.map((x) => x.no) : [...picked.get(r.id)])) : undefined;
      event.currentTarget.disabled = true;
      try { const { submittal } = await api.createSubmittal(project.id, { ...data, subject: data.subject || undefined, run_ids: [...picked.keys()], sheets }); toast(t('saved'), 'success'); close(); window.open(api.submittalFormUrl(submittal.id), '_blank', 'noopener'); after?.(); }
      catch (error) { toastError(error); event.currentTarget.disabled = false; }
    } }),
  ]) });
}
function openSubmittalStatus(sub, after) {
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'status', label: t('status'), type: 'select', value: sub.status, options: SUBMITTAL_STATUS.map((v) => ({ value: v, label: t(`dw_sstatus_${v}`) })) }),
      field({ name: 'date', label: t('dw_submittal_date'), type: 'date', value: sub.date || '' }), field({ name: 'to_name', label: t('dw_submittal_to'), value: sub.to_name || '', dir: 'ltr' }),
      field({ name: 'attention', label: t('dw_submittal_attention'), value: sub.attention || '', dir: 'ltr' }), field({ name: 'response_date', label: t('dw_submittal_response_date'), type: 'date', value: sub.response_date || '' }),
      field({ name: 'response_by', label: t('dw_submittal_response_by'), value: sub.response_by || '', dir: 'ltr' }),
    ]),
    field({ name: 'subject', label: t('dw_submittal_subject'), value: sub.subject || '', dir: 'ltr' }), field({ name: 'response_notes', label: t('dw_submittal_response'), type: 'textarea', value: sub.response_notes || '', rows: 2 }),
    field({ name: 'notes', label: t('dw_notes'), type: 'textarea', value: sub.notes || '', rows: 2 }),
  ]);
  const { close } = openModal({ title: `${sub.code}`, size: 'wide', body: form, footer: el('div.row', {}, [
    el('button.btn-secondary.btn', { type: 'button', text: t('cancel'), onclick: () => close() }),
    el('button.btn-secondary.btn', { type: 'button', text: t('dw_submittal_reissue'), onclick: async () => { try { await api.updateSubmittal(sub.id, { ...readForm(form), reissue: true }); toast(t('saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }),
    el('button.btn', { type: 'button', text: t('save'), onclick: async () => { try { await api.updateSubmittal(sub.id, readForm(form)); toast(t('saved'), 'success'); close(); after?.(); } catch (error) { toastError(error); } } }),
  ]) });
}

// ------------------------------------------------------------------------------------------------ settings
async function settingsPage() {
  const { settings: current } = await api.settings();
  const spec = current.spec && Object.keys(current.spec).length ? JSON.stringify(current.spec, null, 2) : '';
  const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'designer', label: t('dw_designer_name'), value: current.designer || '', dir: 'ltr', hint: t('dw_designer_name_hint') }),
      field({ name: 'project_prefix', label: t('dw_project_prefix'), value: current.project_prefix || 'P', dir: 'ltr' }),
      field({ name: 'design_prefix', label: t('dw_design_prefix'), value: current.design_prefix || 'SPAN-DD', dir: 'ltr' }), field({ name: 'shop_prefix', label: t('dw_shop_prefix'), value: current.shop_prefix || 'SPAN-SD', dir: 'ltr' }),
      field({ name: 'default_mode', label: t('dw_default_mode'), type: 'select', value: current.default_mode || 'design', options: MODES.map((m) => ({ value: m, label: modeLabel(m) })) }),
      field({ name: 'ram_bands', label: t('dw_ram_bands'), type: 'select', value: current.ram_bands || 'all', options: BANDS.map((b) => ({ value: b, label: bandsLabel(b) })) }),
      field({ name: 'mesh', label: t('dw_mesh'), type: 'select', value: current.mesh || 'bottom', hint: t('dw_mesh_hint'), options: MESHES.map((m) => ({ value: m, label: meshLabel(m) })) }),
      field({ name: 'beam_design', label: t('dw_beam_design'), type: 'select', value: current.beam_design || 'ram', hint: t('dw_bd_hint'), options: BEAM_DESIGNS.map((m) => ({ value: m, label: beamDesignLabel(m) })) }),
      field({ name: 'rotate', label: t('dw_rotate'), type: 'select', value: current.rotate || 'auto', hint: t('dw_rotate_hint'), options: ROTATIONS.map((m) => ({ value: m, label: rotateLabel(m) })) }),
      field({ name: 'company', label: t('dw_company'), value: current.company || '', dir: 'ltr' }), field({ name: 'company_line', label: t('dw_company_line'), value: current.company_line || '', dir: 'ltr' }),
      field({ name: 'prepared', label: t('dw_prepared'), value: current.prepared || '', dir: 'ltr' }), field({ name: 'checked', label: t('dw_checked'), value: current.checked || '', dir: 'ltr' }), field({ name: 'approved', label: t('dw_approved'), value: current.approved || '', dir: 'ltr' }),
      field({ name: 'status_design', label: t('dw_status_design'), value: current.status_design || '', dir: 'ltr' }), field({ name: 'status_shop', label: t('dw_status_shop'), value: current.status_shop || '', dir: 'ltr' }),
    ]),
    field({ name: 'spec', label: t('dw_spec'), type: 'textarea', value: spec, rows: 4, dir: 'ltr' }),
  ]);
  const fr = { size: 'A1', rightWidth: 185, bottomStrip: 125, titleH: 150, refsH: 52, keyH: 46, schedH: 140, keyplan: true, refs: true, schedule: true, details: false, ...(current.frame || {}) };
  const frameForm = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-3', {}, [
      field({ name: 'size', label: t('dw_frame_size'), type: 'select', value: fr.size, options: ['A0', 'A1', 'A2'].map((v) => ({ value: v, label: v })) }),
      field({ name: 'rightWidth', label: t('dw_frame_right'), type: 'number', value: fr.rightWidth, min: 120, max: 400, step: 5 }), field({ name: 'bottomStrip', label: t('dw_frame_bottom'), type: 'number', value: fr.bottomStrip, min: 0, max: 300, step: 5 }),
      field({ name: 'titleH', label: t('dw_frame_title'), type: 'number', value: fr.titleH, min: 60, max: 300, step: 5 }), field({ name: 'refsH', label: t('dw_frame_refs'), type: 'number', value: fr.refsH, min: 0, max: 200, step: 2 }),
      field({ name: 'keyH', label: t('dw_frame_key'), type: 'number', value: fr.keyH, min: 0, max: 200, step: 2 }), field({ name: 'schedH', label: t('dw_frame_sched'), type: 'number', value: fr.schedH, min: 0, max: 400, step: 5 }),
    ]),
    el('div.grid.grid-4', {}, [field({ name: 'keyplan', label: t('dw_frame_keyplan'), type: 'checkbox', value: fr.keyplan !== false }), field({ name: 'refs', label: t('dw_frame_refsbox'), type: 'checkbox', value: fr.refs !== false }), field({ name: 'schedule', label: t('dw_frame_schedule'), type: 'checkbox', value: fr.schedule !== false }), field({ name: 'details', label: t('dw_frame_details'), type: 'checkbox', value: fr.details !== false })]),
  ]);
  const frameInput = el('input', { type: 'file', accept: '.dxf', style: { display: 'none' } });
  const frameStatus = el('div.small', { text: current.frame_dxf ? `${t('dw_frame_current')}: ${current.frame_dxf_name || 'frame.dxf'} (${current.frame_dxf_entities || '?'} entities)` : t('dw_frame_none') });
  frameInput.addEventListener('change', async () => {
    const file = frameInput.files?.[0]; if (!file) return;
    try { const res = await api.uploadFrame(file); current.frame_dxf = res.frame_dxf; frameStatus.textContent = `${t('dw_frame_current')}: ${res.name} (${res.entities} entities)`; toast(t('dw_frame_uploaded'), 'success'); } catch (error) { toastError(error); }
  });
  const rates = { ...current.rates };
  const RATE_KEYS = ['steel_per_ton', 'rebar_labour_per_ton', 'concrete_per_m3', 'formwork_per_m2', 'strand_per_kg', 'anchor_live', 'anchor_dead', 'duct_per_m', 'pt_labour_per_m2', 'markup_pct', 'vat_pct'];
  const sp = current.spec || {};
  const rd = { tc: { dia: 16, spacing: 150, length: 4000, ...(sp.topColumns || {}) }, dr: { dia: 12, spacing: 150, leg: 500, ...(sp.drops || {}) }, bm: { dia: 12, spacing: 200, ...(sp.bottom || {}) }, tm: { dia: 12, spacing: 200, ...(sp.bottom || {}), ...(sp.topMesh || {}) },
    ue: { dia: 12, spacing: 150, total: 4000, ...(sp.uEdge || {}) }, ps: { uDia: 12, uSpacing: 200, uTotal: 2400, dia: 12, spacing: 200, length: 2000, ...(sp.pourStrip || {}) }, pw: { uTotal: 2500, uSlab: 2000, ...(sp.pourStrip?.wall || {}) } };
  const numField = (name, label, value, step = 1) => field({ name, label, type: 'number', value, min: 6, max: 12000, step });
  const rebarForm = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.small.muted', { text: t('dw_rebar_defaults_hint') }),
    el('div.grid.grid-3', {}, [
      numField('tc_dia', `${t('dw_rd_columns')} — ${t('dw_rd_dia')}`, rd.tc.dia), numField('tc_spacing', `${t('dw_rd_columns')} — ${t('dw_rd_spacing')}`, rd.tc.spacing, 5), numField('tc_length', `${t('dw_rd_columns')} — ${t('dw_rd_length')}`, rd.tc.length, 50),
      numField('dr_dia', `${t('dw_rd_drops')} — ${t('dw_rd_dia')}`, rd.dr.dia), numField('dr_spacing', `${t('dw_rd_drops')} — ${t('dw_rd_spacing')}`, rd.dr.spacing, 5), numField('dr_leg', `${t('dw_rd_drops')} — ${t('dw_rd_leg')}`, rd.dr.leg, 50),
      numField('bm_dia', `${t('dw_rd_bottom')} — ${t('dw_rd_dia')}`, rd.bm.dia), numField('bm_spacing', `${t('dw_rd_bottom')} — ${t('dw_rd_spacing')}`, rd.bm.spacing, 5), el('div'),
      numField('tm_dia', `${t('dw_rd_top')} — ${t('dw_rd_dia')}`, rd.tm.dia), numField('tm_spacing', `${t('dw_rd_top')} — ${t('dw_rd_spacing')}`, rd.tm.spacing, 5), el('div'),
      numField('ue_dia', `${t('dw_rd_uedge')} — ${t('dw_rd_dia')}`, rd.ue.dia), numField('ue_spacing', `${t('dw_rd_uedge')} — ${t('dw_rd_spacing')}`, rd.ue.spacing, 5), numField('ue_total', `${t('dw_rd_uedge')} — ${t('dw_rd_utotal')}`, rd.ue.total, 50),
      numField('ps_udia', `${t('dw_rd_pstrip')} — ${t('dw_rd_dia')}`, rd.ps.uDia), numField('ps_uspacing', `${t('dw_rd_pstrip')} — ${t('dw_rd_spacing')}`, rd.ps.uSpacing, 5), numField('ps_utotal', `${t('dw_rd_pstrip')} — ${t('dw_rd_utotal')}`, rd.ps.uTotal, 50),
      numField('ps_dia', `${t('dw_rd_pstrip_tb')} — ${t('dw_rd_dia')}`, rd.ps.dia), numField('ps_spacing', `${t('dw_rd_pstrip_tb')} — ${t('dw_rd_spacing')}`, rd.ps.spacing, 5), numField('ps_length', `${t('dw_rd_pstrip_tb')} — ${t('dw_rd_length')}`, rd.ps.length, 50),
      numField('pw_utotal', `${t('dw_rd_pstrip_wall')} — ${t('dw_rd_utotal')}`, rd.pw.uTotal, 50), numField('pw_uslab', `${t('dw_rd_pstrip_slab')} — ${t('dw_rd_utotal')}`, rd.pw.uSlab, 50), el('div'),
    ]),
  ]);
  const ratesForm = el('form', { onsubmit: (e) => e.preventDefault() }, [el('div.grid.grid-4', {}, [field({ name: 'currency', label: t('dw_rate_currency'), value: rates.currency, dir: 'ltr' }), ...RATE_KEYS.map((k) => field({ name: k, label: t(`dw_rate_${k}`), type: 'number', value: rates[k], min: 0, step: 0.01 }))])]);
  const sub = { prefix: 'SPAN-SUB', title: '', title_ar: '', intro: '', responses: [], signatures: [], footer: '', contact: '', ...(current.submittal || {}) };
  const subForm = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-3', {}, [field({ name: 'prefix', label: t('dw_sub_prefix'), value: sub.prefix, dir: 'ltr' }), field({ name: 'title', label: t('dw_sub_title'), value: sub.title, dir: 'ltr' }), field({ name: 'title_ar', label: t('dw_sub_title_ar'), value: sub.title_ar, dir: 'rtl' })]),
    field({ name: 'contact', label: t('dw_sub_contact'), value: sub.contact, dir: 'ltr' }), field({ name: 'intro', label: t('dw_sub_intro'), type: 'textarea', value: sub.intro, rows: 2, dir: 'ltr' }),
    el('div.grid.grid-2', {}, [field({ name: 'responses', label: t('dw_sub_responses'), type: 'textarea', value: (sub.responses || []).join('\n'), rows: 4, dir: 'ltr' }), field({ name: 'signatures', label: t('dw_sub_signatures'), type: 'textarea', value: (sub.signatures || []).join('\n'), rows: 4, dir: 'ltr' })]),
    field({ name: 'footer', label: t('dw_sub_footer'), type: 'textarea', value: sub.footer, rows: 2, dir: 'ltr' }),
  ]);
  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('dw_settings') }), el('div.spacer'), el('span.tiny.muted', { text: `${t('dw_data_folder')}: ${BOOT.data_dir}`, dir: 'ltr' })]),
    el('div.card-body', {}, [
      el('div.alert.info', { text: t('dw_numbering_hint'), dir: 'ltr' }), form,
      el('h4.mt-2', { text: t('dw_rebar_defaults') }), rebarForm,
      el('h4.mt-2', { text: t('dw_submittal_template') }), el('div.small.muted', { text: t('dw_submittal_template_hint') }), subForm,
      el('h4.mt-2', { text: t('dw_rates') }), el('div.small.muted', { text: t('dw_rates_hint') }), ratesForm,
      el('h4.mt-2', { text: t('dw_frame') }), el('div.small.muted', { text: t('dw_frame_hint') }), frameForm,
      el('h4.mt-2', { text: t('dw_frame_dxf') }), el('div.small.muted', { text: t('dw_frame_dxf_hint'), dir: 'ltr' }), frameStatus,
      el('div.row.wrap.mt-1', {}, [frameInput, el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: () => frameInput.click() }, [icon('upload', 14), t('dw_frame_upload')]), current.frame_dxf ? el('a.btn-secondary.btn.btn-sm', { href: api.frameUrl() }, [icon('download', 14), 'DXF']) : null,
        el('button.btn-secondary.btn.btn-sm', { type: 'button', onclick: async () => { try { await api.deleteFrame(); current.frame_dxf = null; frameStatus.textContent = t('dw_frame_none'); toast(t('saved'), 'success'); } catch (error) { toastError(error); } } }, [icon('trash', 14), t('dw_frame_remove')])]),
      el('div.row.mt-2', {}, [
        el('button.btn', { type: 'button', text: t('save'), onclick: async () => {
          const data = readForm(form);
          let parsed = {};
          if (data.spec) { try { parsed = JSON.parse(data.spec); } catch (e) { toast(`${t('dw_spec')}: JSON`, 'error'); return; } }
          delete data.spec;
          const rb = readForm(rebarForm);
          const n = (v, d) => (v == null || v === '' || Number.isNaN(Number(v)) ? d : Number(v));
          parsed.topColumns = { ...(parsed.topColumns || {}), dia: n(rb.tc_dia, 16), spacing: n(rb.tc_spacing, 150), length: n(rb.tc_length, 4000) };
          parsed.drops = { ...(parsed.drops || {}), dia: n(rb.dr_dia, 12), spacing: n(rb.dr_spacing, 150), leg: n(rb.dr_leg, 500) };
          parsed.bottom = { ...(parsed.bottom || {}), dia: n(rb.bm_dia, 12), spacing: n(rb.bm_spacing, 200) };
          parsed.topMesh = { ...(parsed.topMesh || {}), dia: n(rb.tm_dia, 12), spacing: n(rb.tm_spacing, 200) };
          parsed.uEdge = { ...(parsed.uEdge || {}), dia: n(rb.ue_dia, 12), spacing: n(rb.ue_spacing, 150), total: n(rb.ue_total, 4000) };
          parsed.pourStrip = { ...(parsed.pourStrip || {}), uDia: n(rb.ps_udia, 12), uSpacing: n(rb.ps_uspacing, 200), uTotal: n(rb.ps_utotal, 2400), dia: n(rb.ps_dia, 12), spacing: n(rb.ps_spacing, 200), length: n(rb.ps_length, 2000), wall: { ...(parsed.pourStrip?.wall || {}), uTotal: n(rb.pw_utotal, 2500), uSlab: n(rb.pw_uslab, 2000) } };
          const frame = readForm(frameForm);
          for (const k of ['rightWidth', 'bottomStrip', 'titleH', 'refsH', 'keyH', 'schedH']) if (frame[k] == null) delete frame[k];
          const rateData = readForm(ratesForm);
          for (const k of RATE_KEYS) if (rateData[k] == null) delete rateData[k];
          const subData = readForm(subForm);
          const lines = (v) => String(v || '').split('\n').map((x) => x.trim()).filter(Boolean);
          const submittal = { ...sub, ...subData, responses: lines(subData.responses), signatures: lines(subData.signatures) };
          try { const res = await api.saveSettings({ ...current, ...data, spec: parsed, frame: { ...fr, ...frame }, rates: { ...rates, ...rateData }, submittal }); BOOT.settings = res.settings; toast(t('saved'), 'success'); render(); } catch (error) { toastError(error); }
        } }),
        el('button.btn-secondary.btn', { type: 'button', text: t('reset_defaults', isRTL() ? 'رجّع الافتراضي' : 'Reset defaults'), onclick: async () => { if (!(await confirmDialog(t('reset_defaults', isRTL() ? 'رجّع الافتراضي' : 'Reset defaults') + '?', { danger: true, confirmLabel: t('reset_defaults', 'Reset') }))) return; try { const res = await api.resetSettings(); BOOT.settings = res.settings; toast(t('saved'), 'success'); render(); } catch (error) { toastError(error); } } }),
      ]),
    ]),
  ]);
}

// ---------------------------------------------------------------------------------------------------- help
function helpPage() {
  const ar = isRTL();
  return el('div.help', {}, [
    el('div.card', {}, [el('div.card-header', {}, [el('h3', { text: t('help_title') })]), el('div.card-body', {}, [
      el('p', { text: t('help_intro') }),
      el('ol', {}, ['dw_step1', 'dw_step2', 'dw_step3', 'dw_step4'].map((k) => el('li', { text: t(k).replace(/^[\d١-٩]+[-.]\s*/, '') }))),
      el('ul', {}, [
        el('li', { text: ar ? 'الإصدار المتوقف (بانشنج أو كمرات): قرار المهندس من صفحة الإصدار (زيادة السمك / مسيّف في الرام / تخطّي على مسؤوليته) وبيتعاد الإخراج بنفس المراجعة.' : 'A blocked run (punching or beams): the engineer decides on the run page (thicken / passing in RAM / bypass at own responsibility) and the run is regenerated at the same revision.' }),
        el('li', { text: ar ? 'تصميم الكمرات من الرام: "جهّز موديل الرام بشرائح الكمرات" من صفحة الإصدار، احسبه في الرام، وارفعه إصدار جديد.' : 'Beam design through RAM: "Prepare the RAM model with beam strips" on the run page, calculate it in RAM, upload it as the next run.' }),
        el('li', { text: ar ? 'عدّلت اللوحة في الأوتوكاد؟ "تحديث الحصر من DXF معدّل" بيقرأ الأسياخ من علاماتها ويحرّك الحصر بالفرق.' : 'Edited the sheet in AutoCAD? "Update take-off from edited DXF" reads the bars by their tags and moves the take-off by the difference.' }),
        el('li', { text: t('help_data') }),
      ]),
      el('h4', { text: t('help_files') }), el('p', { text: t('help_files_text') }),
      el('h4', { text: t('help_cli') }),
      el('pre', { text: 'python3 -m pydrawings --input SLAB.cpt --out ./design --mode design --level "1ST FLOOR" --level-id L01\npython3 -m pydrawings --input SLAB.cpt --out ./shop --mode shop --level "1ST FLOOR"\npython3 -m pydrawings --input RFT.dxf --out ./design --mode design --level "TYPICAL FLOOR"\npython3 app.py --port 9000 --data D:/DRAWINGS' }),
      el('div.tiny.muted', { text: `v${BOOT.version} · Python ${BOOT.python || ''} · ${BOOT.data_dir}`, dir: 'ltr' }),
    ])]),
  ]);
}

// ---------------------------------------------------------------------------------------------------- boot
(async () => {
  applyDirection();
  try { BOOT = await api.bootstrap(); } catch (e) { /* the page still renders */ }
  if (!location.hash) location.hash = '#/projects';
  render();
})();
</script>
</body>
</html>
"""


if __name__ == '__main__':
    sys.exit(main())
