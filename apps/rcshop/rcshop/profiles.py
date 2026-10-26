"""Reading profiles: how ONE consultant draws (layers, blocks, label patterns, views). Saved from a finished project,
applied to the next project of the same consultant so the drawing is read without starting from zero.
The project's own data (schedules, levels, sizes, title block values, zones) is never part of a profile."""
import json, re
from pathlib import Path

from .paths import PROFILES_DIR

READING_KEYS = ['layout', 'beam_layer', 'label_layer', 'col_layers', 'axis_block', 'axis_attr', 'axis_family_attr',
                'widths', 'fnd_layers', 'fnd_col_layers', 'fnd_pc_layers', 'footing_label_re', 'col_keys',
                'col_block_keys', 'column_schedule_block', 'sched_outline_layers', 'grid_layers',
                'core_outline_layer', 'cd_rc_layers_extra', 'pc_thickness', 'core_cover',
                'stairs.outline_layer', 'stairs.bar_layer', 'stairs.size', 'sog.tag_block', 'sog.thk_block',
                'sog.beam_layer', 'sog.col_layers']        # 'a.b' = key b inside object a


def _file(name):
    return PROFILES_DIR / (re.sub(r'[^\w\-. ]', '_', name).strip() + '.json')


def list_profiles():
    return sorted(p.stem for p in PROFILES_DIR.glob('*.json')) if PROFILES_DIR.exists() else []


def save_from(ws, name, note=''):
    P = ws.project()
    from .roles import get_value
    prof = {k: get_value(P, k) for k in READING_KEYS if get_value(P, k) not in (None, '', [], {})}
    if not prof:
        raise ValueError('project.json has no reading keys to save')
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    _file(name).write_text(json.dumps(dict(name=name, note=note, source=ws.name, keys=prof), indent=1), encoding='utf-8')
    return _file(name)


def apply_to(ws, name, overwrite=False):
    """merge a profile into work/project.json -> keys written"""
    prof = json.loads(_file(name).read_text(encoding='utf-8'))['keys']
    pj = ws.work / 'project.json'
    P = ws.project()
    from .roles import get_value
    wrote = [k for k in prof if overwrite or get_value(P, k) is None]
    for k in wrote:
        if '.' in k:
            a, b = k.split('.', 1)
            if not isinstance(P.get(a), dict): P[a] = {}
            P[a][b] = prof[k]
        else:
            P[k] = prof[k]
    pj.write_text(json.dumps(P, indent=1, ensure_ascii=False), encoding='utf-8')
    return wrote
