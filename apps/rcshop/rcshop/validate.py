"""What is still missing before a module can run - in words the engineer can act on."""
import json, os, shutil

REQUIRED = {
    'core': [('dxf', 'converted drawing (DXF in work/)'), ('meta', 'title block values')],
    'gb': [('layout', 'layout whose viewport frames the GB plan'), ('beam_layer', 'layer of the GB edges'),
           ('label_layer', 'layer of the GB1/GB2 tags'), ('col_layers', 'column outline layers'),
           ('axis_block', 'grid bubble block'), ('schedule', 'grade beam schedule {GB1: {b, h, nb, db, nt, dt, ds, s}}'), ('levels', 'founding / top of GB levels')],
    'footings': [],
    'necks': [('column_sizes', 'column marks and sizes'), ('fnd_view', 'centre x, y and height of the foundation plan view')],
    'cd': [('fnd_view', 'centre x, y and height of the foundation plan view')],
    'mats': [],
    'zones': [('fnd_final', '{dxf, shift} of the final foundation plan with the AREA clouds')],
    'cores': [('core_types', 'core types (walls, bars)')],
    'strip': [('strip', 'strip footing section and bars')],
    'pool': [],
}
FILES = {'footings': ['footings.json'], 'necks': ['footings.json'], 'mats': ['footings_ext.json'],
         'zones': ['footings.json'], 'pool': ['pool.json']}


def problems(ws):
    out = []
    pj = ws.work / 'project.json'
    if not pj.exists():
        return ['project.json does not exist - create it from the survey draft (Data files > New from draft)']
    try:
        P = json.loads(pj.read_text(encoding='utf-8'))
    except ValueError as e:
        return [f'project.json is not valid JSON: {e}']
    for m in ws.modules:
        for k, what in REQUIRED.get(m, []):
            if k not in P or P[k] in ('', [], {}):
                out.append(f'[{m}] project.json "{k}": {what}')
        for f in FILES.get(m, []):
            if not (ws.work / f).exists():
                out.append(f'[{m}] {f} missing')
    if P.get('dxf') and not (ws.work / P['dxf']).exists():
        out.append(f'project.json "dxf": {P["dxf"]} is not in work/ (add the drawing)')
    for k, sub in (('fnd_final', 'dxf'), ('fnd_final', 'zones'), ('title_block', 'dxf')):
        v = (P.get(k) or {}).get(sub, '')
        if v and os.path.isabs(v):
            out.append(f'project.json {k}.{sub} is an absolute path ({v}) - put the file in work/ and give its name only')
    tb = P.get('title_block')
    if tb and not (ws.work / tb.get('dxf', '')).exists():
        out.append(f'title_block.dxf {tb.get("dxf")} is not in work/')
    return out


def new_from_draft(ws):
    """project.json from the survey's draft (layers / blocks / views guessed) - to be checked by the engineer"""
    src = ws.work / 'survey' / 'project.draft.json'
    dst = ws.work / 'project.json'
    if dst.exists():
        raise FileExistsError('project.json already exists')
    if not src.exists():
        raise FileNotFoundError('run the "survey" step first')
    P = json.loads(src.read_text(encoding='utf-8'))
    if not P.get('dxf'): P['dxf'] = ws.meta.get('main_dxf', '')
    dst.write_text(json.dumps(P, indent=1, ensure_ascii=False), encoding='utf-8')
    return dst
