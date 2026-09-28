"""
Reinforcement + PT cables shop-drawing generator - the standalone Python version.

  python -m pydrawings --input <combined-structural.dxf> --out <dir> [options]
  python -m pydrawings --sample --out ./sample-output

Options
  --project "..."  --client "..."  --location "..."  --company "..."
  --prefix SPAN-SD  --rev 00  --date YYYY-MM-DD
  --prepared "..."  --checked "..."  --approved "..."
  --config file.json      project meta and spec overrides ({ "meta": {...}, "spec": {...}, "layers": "path" })
  --layers file.json      layer standard (default: pydrawings/layers.spantech.json)
  --level "1ST FLOOR"     level name (default: from the file name)
  --level-id B1           the level code that goes into the drawing numbers
  --mode design           design drawings from the office's own RFT plan, or from a RAM Concept .cpt, + the General
                          Details rules (default: shop)
  --no-svg                skip the SVG previews

Output
  <out>/dxf/<DRAWING_NO>_<BLOCK>.dxf   one DXF per sheet (block + insert, xref-able)
  <out>/SHOP_DRAWINGS_PACKAGE.dxf      every sheet block in one file (DESIGN_DRAWINGS_PACKAGE.dxf in design mode)
  <out>/preview/*.svg                  browser previews
  <out>/schedules/*.csv                bar bending schedules
  <out>/model.json, REPORT.md          what was read, what was assumed
"""
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .dxf_reader import parse_dxf
from .libredwg_json import from_libredwg_json
from .ram_concept import read_ram_concept, ram_to_model
from .extract import extract_model, flatten
from .sheets import compose_package
from .quantities import quantities
from .reference import read_reference_plan, apply_reference
from .beam_strips import beam_schedule
from .punching import punching_check
from .beam_design import design_beams
from .design import extract_design, prepare_ram_design, compose_design_package
from .dxf_writer import to_dxf
from .svg_writer import to_svg
from . import rebar as R
from .geometry import js_round, fmt_num, to_fixed

HERE = Path(__file__).resolve().parent
DEFAULT_LAYER_STANDARD = HERE / 'layers.spantech.json'
SAMPLE_INPUT = HERE.parent.parent / 'shopdrawings' / 'samples' / 'sample-structural-input.dxf'


def parse_args(argv):
    """The CLI flags: `--key value`, `--no-svg`, `--sample` (the JS parseArgs)."""
    a = {'svg': True}
    i = 0
    while i < len(argv):
        k = argv[i]
        if not k.startswith('--'):
            i += 1
            continue
        key = k[2:]
        if key == 'no-svg':
            a['svg'] = False
            i += 1
            continue
        if key == 'sample':
            a['sample'] = True
            i += 1
            continue
        a[key] = argv[i + 1] if i + 1 < len(argv) else None
        i += 2
    return a


def load_drawing(input_path, input_text=None):
    """Load a DXF, a LibreDWG JSON export, or a DWG (converted with `dwgread` when it is on PATH)."""
    if input_text is not None:
        return parse_dxf(input_text)
    ext = Path(input_path).suffix.lower()
    if ext == '.json':
        return from_libredwg_json(json.loads(Path(input_path).read_text(encoding='utf8')))
    if ext == '.dwg':
        tool = os.environ.get('DWGREAD') or 'dwgread'
        json_path = re.sub(r'\.dwg$', '.libredwg.json', str(input_path), flags=re.I)
        try:
            subprocess.run([tool, '-O', 'json', '-o', json_path, str(input_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            raise ValueError(f'Cannot convert DWG: {tool} (LibreDWG) not found or failed. Export the drawing as DXF (DXFOUT) or JSON (dwgread -O json) first.')
        return from_libredwg_json(json.loads(Path(json_path).read_text(encoding='utf8')))
    return parse_dxf(Path(input_path).read_text(encoding='utf8', errors='replace'))


def level_name_from_file(input_path):
    """Level name guessed from the file name, e.g. S02D__FIRST_FLOOR_SLAB_G.A -> "S02D FIRST FLOOR SLAB"."""
    if not input_path:
        return None
    base = re.sub(r'\.[^.]+$', '', os.path.basename(str(input_path)))
    base = re.sub(r'\.libredwg$', '', base)
    name = re.sub(r'[_-]+', ' ', base)
    name = re.sub(r'\bG\.?A\.?\b', '', name, flags=re.I)
    name = re.sub(r'\s+', ' ', name).strip().upper()
    return name or None


def load_layer_standard(path=DEFAULT_LAYER_STANDARD):
    return json.loads(Path(path).read_text(encoding='utf8'))


def generate(input_dxf=None, input_text=None, out=None, meta=None, spec=None, svg=True, level_names=None, layer_standard=None, mode='shop'):
    """The whole package from one input: the model, the sheets, every file under `out`."""
    meta = dict(meta or {})
    spec = dict(spec or {})
    meta = {'layerStandard': layer_standard or load_layer_standard(), **meta, 'mode': mode}
    # the office's own sheet frame: a DXF in paper mm whose texts carry <TOKENS> (see Sheet.custom_frame)
    if meta.get('frameDxf') and os.path.exists(meta['frameDxf']):
        meta['frameEntities'] = frame_entities(Path(meta['frameDxf']).read_text(encoding='utf8', errors='replace'))
    is_cpt = bool(input_dxf) and re.search(r'\.cpt$', str(input_dxf), re.I) is not None
    if mode == 'design' and is_cpt:
        # design drawings straight from the RAM Concept model: its designed bands + the General Details rules
        ram = read_ram_concept(input_dxf)
        level_name = (level_names and level_names[0]) or level_name_from_file(input_dxf) or '1ST FLOOR'
        raw = ram_to_model(ram, level_name=level_name, level_id=meta.get('levelId'), spec=spec)
        _use_reference_plan(raw, ram, spec)
        for l in raw['levels']:
            l['beamCheck'] = design_beams(l, {**(raw.get('spec') or {}), **spec})
            l['beamSchedule'] = beam_schedule(ram, l, library=spec.get('beamTypes') or [], design=spec.get('beamDesign') or 'ram', office=l['beamCheck'])
            l['punchingCheck'] = punching_check(l, {**(raw.get('spec') or {}), **spec, 'punching': {**((raw.get('spec') or {}).get('punching') or {}), **(spec.get('punching') or {})}})
        model = prepare_ram_design(raw, {'levelName': level_name, 'spec': spec, 'wallThickness': spec.get('wallThickness')})
        h = ram['project']
        meta = {'project': ' - '.join([v for v in [h.get('name'), h.get('part')] if v]) or meta.get('project'), 'company': h.get('company') or meta.get('company'), 'revision': re.sub(r'^rev\.?\s*', '', h.get('revision') or '', flags=re.I) or meta.get('revision'), **meta}
    elif mode == 'design':
        # design drawings: the office's own design plan + the General Details rules
        dxf = load_drawing(input_dxf, input_text)
        model = extract_design(dxf, {'spec': spec, 'levelNames': level_names or ([level_name_from_file(input_dxf)] if input_dxf else [])})
    elif is_cpt:
        ram = read_ram_concept(input_dxf)
        model = ram_to_model(ram, level_name=(level_names and level_names[0]) or level_name_from_file(input_dxf) or '1ST FLOOR', level_id=meta.get('levelId'), spec=spec)
        _use_reference_plan(model, ram, spec)
        for l in model['levels']:
            l['beamCheck'] = design_beams(l, {**(model.get('spec') or {}), **spec})
            l['beamSchedule'] = beam_schedule(ram, l, library=spec.get('beamTypes') or [], design=spec.get('beamDesign') or 'ram', office=l['beamCheck'])
            l['punchingCheck'] = punching_check(l, {**(model.get('spec') or {}), **spec, 'punching': {**((model.get('spec') or {}).get('punching') or {}), **(spec.get('punching') or {})}})
        h = ram['project']
        meta = {'project': ' - '.join([v for v in [h.get('name'), h.get('part')] if v]) or meta.get('project'), 'company': h.get('company') or meta.get('company'), 'revision': re.sub(r'^rev\.?\s*', '', h.get('revision') or '', flags=re.I) or meta.get('revision'), **meta}
    else:
        dxf = load_drawing(input_dxf, input_text)
        model = extract_model(dxf, {'spec': spec, 'levelNames': level_names or ([level_name_from_file(input_dxf)] if input_dxf else [])})
    pack = compose_design_package(model, meta) if mode == 'design' else compose_package(model, meta)
    out = Path(out or 'shopdrawings-output')
    (out / 'dxf').mkdir(parents=True, exist_ok=True)
    (out / 'schedules').mkdir(parents=True, exist_ok=True)
    if svg:
        (out / 'preview').mkdir(parents=True, exist_ok=True)
    files = []
    for s in pack['sheets']:
        base = f"{s['drawingNo']}_{s['blockName']}"
        dxf_path = out / 'dxf' / f'{base}.dxf'
        dxf_path.write_text(to_dxf(s['root'], {'ltscale': (s.get('scale') or 100) / 4}), encoding='utf8')
        files.append(str(dxf_path))
        if svg:
            (out / 'preview' / f'{base}.svg').write_text(to_svg(s['root'], {'width': 2400}), encoding='utf8')
        if s.get('rows') and s.get('key') != 'cables':
            cols = s['csvCols']
            lines = [','.join(c['title'].replace('\n', ' ') for c in cols)]
            for r in s['rows']:
                lines.append(','.join('"' + _csv_cell(r.get(c['key'])).replace('"', '""') + '"' for c in cols))
            (out / 'schedules' / f'{base}.csv').write_text('\n'.join(lines) + '\n', encoding='utf8')
    max_scale = max([s.get('scale') or 100 for s in pack['sheets']] or [100])
    (out / ('DESIGN_DRAWINGS_PACKAGE.dxf' if mode == 'design' else 'SHOP_DRAWINGS_PACKAGE.dxf')).write_text(to_dxf(pack['pkg'], {'ltscale': max_scale / 4}), encoding='utf8')
    (out / 'model.json').write_text(json_dumps(serializable(model), indent=2), encoding='utf8')
    if pack.get('plan'):
        (out / 'plan.json').write_text(json_dumps(pack['plan']), encoding='utf8')
    qty = quantities(model, pack)
    (out / 'quantities.json').write_text(json_dumps(qty, indent=2), encoding='utf8')
    punching = [{'level': l['id'], 'name': l['name'], **l['punchingCheck'], 'overridden': l.get('punchingOverridden') or []} for l in model['levels'] if l.get('punchingCheck')]
    if punching:
        (out / 'punching.json').write_text(json_dumps(punching, indent=2), encoding='utf8')
    beam_checks = [{'level': l['id'], 'name': l['name'], 'design': spec.get('beamDesign') or 'ram', **l['beamCheck']} for l in model['levels'] if l.get('beamCheck') and l['beamCheck'].get('beams')]
    if beam_checks:
        (out / 'beams.json').write_text(json_dumps(beam_checks, indent=2), encoding='utf8')
    (out / 'REPORT.md').write_text(report(model, pack), encoding='utf8')
    return {'model': model, 'pack': pack, 'files': files, 'quantities': qty, 'punching': punching, 'beamChecks': beam_checks}


def _csv_cell(v):
    """JS `String(r[c.key] ?? '')`: numbers print like JS, None is empty."""
    if v is None:
        return ''
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return fmt_num(v)
    return str(v)


def _use_reference_plan(model, ram, spec):
    """
    The reference plan of the level (`spec.reference`: { file | text, use: { grid, columns, outline }, align: { mode:
    'auto' | 'point', dxf: {x, y}, ram: {x, y}, rot } }): the architect's grid, columns and slab edges replace the
    RAM ones, matched on the columns or on the point given.
    """
    ref = spec.get('reference') if spec else None
    if not ref or (not ref.get('file') and not ref.get('text')):
        return
    text = ref.get('text') or (Path(ref['file']).read_text(encoding='utf8', errors='replace') if ref.get('file') and os.path.exists(ref['file']) else None)
    if not text:
        model['findings'].append(f"Reference plan {ref.get('file')} not found; the RAM geometry is used.")
        return
    plan = read_reference_plan(text)
    apply_reference(model, plan, {'use': ref.get('use') or {}, 'align': ref.get('align') or None, 'ramColumns': ram['columns']})


def frame_entities(text):
    """The entities of a frame DXF (paper mm, bottom-left origin), blocks exploded, ready for Sheet.custom_frame."""
    dxf = parse_dxf(text)
    ents = flatten(dxf)
    k = 1  # a frame is drawn in paper millimetres
    kinds = ['LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF', 'SOLID', 'TRACE']
    out = []
    for e in ents:
        if e.get('type') not in kinds:
            continue
        if k == 1:
            out.append(e)
        else:
            out.append({**e, 'x': e['x'] * k, 'y': e['y'] * k, 'x2': e['x2'] * k if e.get('x2') is not None else e.get('x2'), 'y2': e['y2'] * k if e.get('y2') is not None else e.get('y2'), 'r': e['r'] * k if e.get('r') is not None else e.get('r'), 'height': e['height'] * k if e.get('height') is not None else e.get('height'), 'pts': [{**q, 'x': q['x'] * k, 'y': q['y'] * k} for q in e['pts']] if e.get('pts') else e.get('pts')})
    return out


def _json_default(v):
    if isinstance(v, (set, frozenset)):
        return list(v)
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else v
    return str(v)


def _normalise(v):
    """
    What `JSON.stringify` would write: keys starting with `_` (the caches the rules keep on the level) dropped,
    callables and sets left out / listed, whole floats written as integers (JS has one number type), NaN as null.
    """
    if isinstance(v, dict):
        return {str(k): _normalise(x) for k, x in v.items() if not (isinstance(k, str) and k.startswith('_')) and not callable(x)}
    if isinstance(v, (list, tuple)):
        return [_normalise(x) for x in v]
    if isinstance(v, (set, frozenset)):
        return [_normalise(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return int(v) if v.is_integer() and abs(v) < 1e15 else v
    if callable(v):
        return None
    return v


def json_dumps(v, indent=None):
    """JSON as the Node CLI writes it (2-space indent when asked, no trailing spaces, UTF-8 kept)."""
    return json.dumps(_normalise(v), indent=indent, ensure_ascii=False, default=_json_default, separators=(',', ':') if indent is None else (',', ': '))


def serializable(model):
    return _normalise(model)


def _n(v):
    """JS `${v}` for a number in a report cell."""
    if v is None:
        return 'undefined'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, (int, float)):
        return fmt_num(v)
    return str(v)


def _locale(n):
    """`toLocaleString('en-US')` of a whole number."""
    return f'{int(n):,}'


def report(model, pack):
    L = []
    meta = pack['meta']
    design = meta.get('mode') == 'design'
    spec = model.get('spec') or {}
    sources = spec.get('sources') or {}
    L.append(f"# {'Design drawing package' if design else 'Shop drawing package'} - {meta.get('project')}")
    L.append('')
    L.append(f"Generated {meta.get('date')} · rev {meta.get('revision')} · {len(pack['sheets'])} sheets")
    L.append('')
    L.append('## What was read from the office design plan' if design else '## What was read from the structural drawings')
    L.append('')
    for f in model.get('findings') or []:
        L.append(f'- {f}')
    L.append(f"- Code reference: {model.get('code_reference') or 'not stated'} ({sources.get('code')}); f'c {_n(spec.get('fc'))} MPa ({sources.get('fc')}); fy {_n(spec.get('fy'))} MPa ({sources.get('fy')}); cover {_n(spec.get('cover'))} mm ({sources.get('cover')}).")
    for f in spec.get('found') or []:
        L.append(f'- Reinforcement note applied: {f}')
    L.append('')
    L.append('## Assumptions printed on the sheets')
    L.append('')
    for a in model.get('assumptions') or []:
        L.append(f"- {'[' + str(a['level']) + '] ' if a.get('level') else ''}{a.get('text')}")
    L.append('')
    L.append('## Development and lap lengths applied (mm)')
    L.append('')
    L.append('| Ø | ld bottom | ld top | lap bottom | lap top | ldh |')
    L.append('|---|---|---|---|---|---|')
    for r in R.length_table(spec):
        L.append(f"| {_n(r['dia'])} | {_n(r['ld_bottom'])} | {_n(r['ld_top'])} | {_n(r['lap_bottom'])} | {_n(r['lap_top'])} | {_n(r['ldh'])} |")
    L.append('')
    L.append('## Sheets')
    L.append('')
    L.append('| Drawing No | Title | Level | Block / Xref | Scale | Rebar (kg) |')
    L.append('|---|---|---|---|---|---|')
    for s in pack['sheets']:
        L.append(f"| {s.get('drawingNo')} | {s.get('title')} | {s.get('level')} | `{s.get('blockName')}` | {('1:' + _n(s['scale'])) if s.get('scale') else 'NTS'} | {js_round(s['weight']) if s.get('weight') else '-'} |")
    total = sum((x.get('weight') or 0) for x in pack['sheets'])
    L.append('')
    L.append(f"Reinforcement added from the General Details: **{_locale(js_round(total))} kg** (the designer's own bars are kept as drawn and not scheduled here)." if design
             else f"Total scheduled reinforcement: **{_locale(js_round(total))} kg** (cables excluded - template only).")
    checked = [l for l in model['levels'] if l.get('punchingCheck') and l['punchingCheck'].get('columns')]
    if checked:
        L.append('')
        L.append('## Indicative punching check (RAM keeps no punching result in the file - the RAM punching report governs)')
        L.append('')
        L.append('| Level | Column | Location | h | Trib. m² | wu kN/m² | Vu kN | vu MPa | phi.vc MPa | Ratio | Status |')
        L.append('|---|---|---|---|---|---|---|---|---|---|---|')
        for l in checked:
            for c in l['punchingCheck']['columns']:
                ps_note = " (PS AT THE ENGINEER'S RESPONSIBILITY)" if c.get('id') in (l.get('punchingOverridden') or []) else ''
                L.append(f"| {l['id']} | {c.get('id')} | {c.get('loc')} | {_n(c.get('h'))} | {_n(c.get('trib_m2'))} | {_n(c.get('wu_kn_m2'))} | {_n(c.get('Vu_kn'))} | {_n(c.get('vu_mpa'))} | {_n(c.get('phi_vc_mpa'))} | {_n(c.get('ratio'))} | {c.get('status')}{' (SSR in RAM)' if c.get('ssr') else ''}{' (FAILS IN RAM)' if c.get('ram_failed') else ''}{ps_note} |")
        for l in checked:
            if l['punchingCheck'].get('flagged'):
                L.append(f"\n**{l['id']}: columns to look at in the RAM punching report: {', '.join(l['punchingCheck']['flagged'])}** (blocking: {', '.join(l['punchingCheck'].get('blocking') or []) or 'none'}).")
    beam_levels = [l for l in model['levels'] if l.get('beamCheck') and l['beamCheck'].get('beams')]
    if beam_levels:
        L.append('')
        L.append('## Office beam design (continuous-beam analysis on the model loads - the RAM design report governs)')
        L.append('')
        L.append('| Level | Beam | b x h | Spans (m) | Trib. (m) | wu kN/m | Mu- kN·m | Mu+ kN·m | Vu kN | Top | Bottom | Stirrups | Deflection | Status |')
        L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for l in beam_levels:
            for b in l['beamCheck']['beams']:
                d = b.get('deflection') or {}
                if d.get('table_ok'):
                    span0 = (b.get('spans') or [{}])[0].get('length') if b.get('spans') else None
                    ratio = _n(js_round(span0 / d['h_min'] * 10) / 10) if d.get('h_min') and span0 is not None else '?'
                    defl = f'h >= L/{ratio} ok'
                else:
                    defl = f"{_n(d.get('ratio'))} of the limit"
                L.append(f"| {l['id']} | {b.get('id')} | {_n(b.get('width'))}x{_n(b.get('depth'))} | {' + '.join(to_fixed(s['length'] / 1000, 1) for s in b.get('spans') or [])} | {to_fixed((b.get('trib_mm') or {}).get('total', 0) / 1000, 1)} | {_n((b.get('loads') or {}).get('wu'))} | {_n(b.get('Mneg_max'))} | {_n(b.get('Mpos_max'))} | {_n(b.get('Vu'))} | {(b.get('top') or {}).get('text') or '-'} | {(b.get('bottom') or {}).get('text') or '-'} | {(b.get('stirrups') or {}).get('text') or '-'} | {defl} | {b.get('status')}{' (' + ', '.join(b['reasons']) + ')' if b.get('reasons') else ''}{' (FAILS IN RAM)' if b.get('ram_failed') else ''} |")
        for l in beam_levels:
            if l['beamCheck'].get('assumed'):
                L.append(f"\n{l['id']}: {'; '.join(l['beamCheck']['assumed'])}.")
        for l in beam_levels:
            if l['beamCheck'].get('failing'):
                L.append(f"\n**{l['id']}: beams not passing the office check: {', '.join(l['beamCheck']['failing'])}.**")
    if not design:
        # (a sheet's checks are objects on the column sheets and plain sentences elsewhere: the JS spread of a string is harmless)
        checks = [{**(c if isinstance(c, dict) else {}), 'level': s.get('level')} for s in pack['sheets'] for c in (s.get('checks') or [])]
        governed = [c for c in checks if isinstance(c, dict) and c.get('asProv') is not None and c.get('asReq') is not None and c['asProv'] < c['asReq']]
        L.append('')
        L.append(f'## Top bar As,min checks: {len(checks)} column-directions checked, {len(governed)} short')
    return '\n'.join(L) + '\n'


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    out = Path(a.get('out') or 'shopdrawings-output').resolve()
    input_path = str(SAMPLE_INPUT) if a.get('sample') else a.get('input')
    if not input_path or not os.path.exists(input_path):
        print('usage: python -m pydrawings --input <combined-structural.dxf> --out <dir> [--project "..."] [--config file.json]', file=sys.stderr)
        return 2
    cfg = {'meta': {}, 'spec': {}}
    if a.get('config'):
        cfg = {'meta': {}, 'spec': {}, **json.loads(Path(a['config']).read_text(encoding='utf8'))}
    meta = dict(cfg.get('meta') or {})
    for k in ['project', 'client', 'location', 'company', 'prefix', 'prepared', 'checked', 'approved', 'date']:
        if a.get(k):
            meta[k] = a[k]
    if a.get('rev'):
        meta['revision'] = a['rev']
    if a.get('level-id'):
        meta['levelId'] = a['level-id']
    t0 = time.time()
    layer_standard = load_layer_standard(a.get('layers') or cfg.get('layers') or DEFAULT_LAYER_STANDARD)
    res = generate(input_dxf=input_path, out=out, meta=meta, spec=cfg.get('spec') or {}, svg=a['svg'], layer_standard=layer_standard, level_names=[a['level']] if a.get('level') else None, mode=a.get('mode') or cfg.get('mode') or 'shop')
    model, pack, files = res['model'], res['pack'], res['files']
    print('\n'.join(model.get('findings') or []))
    print(f"\n{len(pack['sheets'])} sheets → {out}  ({len(files)} DXF, {int((time.time() - t0) * 1000)} ms)")
    for s in pack['sheets']:
        print(f"  {s['drawingNo']}  {str(s['blockName']).ljust(44)} 1:{_n(s.get('scale'))}  {str(js_round(s['weight'])) + ' kg' if s.get('weight') else ''}")
    print(f"\nAssumptions ({len(model.get('assumptions') or [])}) are printed on every sheet; see REPORT.md")
    return 0
