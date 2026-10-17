"""Roles: the things the engine has to find in a consultant's drawing. The engineer teaches each one by clicking an
example on the drawing; the program turns the click into the project.json key the engine reads, and shows at once
everything else in the drawing that the key would catch (so a wrong layer or pattern is seen before any run).

kind:  layer   one layer, exact name          (engine compares with ==)
       layers  several layers, exact names    (engine: `in`)
       suffix  several layers, name ending    (engine: endswith; an xref prefix "...$0$" is dropped)
       textre  a text pattern (regex), built from the clicked texts
       block   a block name + which attribute holds the number / the family
       window  a rectangle dragged on the drawing  -> [centre x, centre y, height]
       rect    a rectangle dragged on the drawing  -> [x0, y0, x1, y1]
A key with a dot ('stairs.outline_layer') is stored inside that object of project.json.
       layout  a paper layout whose biggest viewport frames the plan
"""
import json, re
from dataclasses import dataclass

import numpy as np


@dataclass
class Role:
    key: str
    title: str
    kind: str
    color: str
    module: str
    how: str


ROLES = [
    Role('layout', 'GB plan layout', 'layout', '#9b8cff', 'gb', 'Pick the paper layout that shows the grade-beam plan.'),
    Role('beam_layer', 'Grade-beam edges', 'layer', '#ff9f1c', 'gb', 'Click one edge line of a grade beam.'),
    Role('label_layer', 'Grade-beam labels', 'layer', '#ff5d8f', 'gb', 'Click a GB1 / GB2 ... label.'),
    Role('col_layers', 'Column outlines', 'layers', '#2ec4b6', 'gb', 'Click a column outline (click again on another layer to add it).'),
    Role('axis_block', 'Grid bubbles', 'block', '#4cc9f0', 'gb', 'Click a grid bubble; then choose the attribute holding the axis name.'),
    Role('fnd_view', 'Foundation plan window', 'window', '#ffd166', 'cd', 'Drag a rectangle around the foundation plan.'),
    Role('fnd_layers', 'Footing / raft outlines', 'suffix', '#f77f00', 'cd', 'Click a footing outline (reinforced concrete).'),
    Role('fnd_pc_layers', 'Plain concrete (PC) outlines', 'suffix', '#a5a58d', 'cd', 'Click the PC outline under a footing.'),
    Role('fnd_col_layers', 'Columns on the foundation plan', 'suffix', '#06d6a0', 'necks', 'Click a column on the foundation plan.'),
    Role('footing_label_re', 'Footing labels', 'textre', '#ef476f', 'cd', 'Click footing labels (F1, F6A, CF2, RAFT-1 ...): each click widens the pattern.'),
    Role('grid_layers', 'Grid lines', 'suffix', '#8ecae6', 'cd', 'Click a grid line.'),
    Role('core_outline_layer', 'Core walls', 'layer', '#c77dff', 'cores', 'Click the outline of a core (shear walls).'),
    Role('stairs.outline_layer', 'Stair starter outlines', 'layer', '#ffbe0b', 'stairs', 'Click the outline of a stair starter (the strip its bars stand in).'),
    Role('stairs.bar_layer', 'Stair starter bars', 'layer', '#fb5607', 'stairs', 'Click one bar (circle) inside a stair starter.'),
    Role('sog.window', 'S.O.G plan window', 'rect', '#90be6d', 'sog', 'Drag a rectangle around the plan that carries the S.O.G tags.'),
    Role('sog.tag_block', 'S.O.G mesh tags', 'block', '#43aa8b', 'sog', 'Click an S.O.G tag (the mesh symbol in a slab panel).'),
    Role('sog.thk_block', 'Slab thickness tags', 'block', '#4d908e', 'sog', 'Click a slab thickness tag (100 / 150).'),
]
BY_KEY = {r.key: r for r in ROLES}


def short_layer(name):
    """an xref-bound layer 'FILE$0$CORE-FNDN' -> 'CORE-FNDN' (the engine matches the end of the name)"""
    return name.split('$')[-1] if '$' in name else name


# ---------------------------------------------------------------------------- text patterns
def text_pattern(sample):
    """'F6A' -> F\\d+[A-Z]?  'RAFT-2' -> RAFT-\\d+  'CF12' -> CF\\d+  (letters before the number kept, the number
    generalised, letters after it optional)"""
    s = sample.strip().upper()
    m = re.match(r'^([A-Z]+)([-_ ]?)(\d+)([A-Z]*)(?:([-_])([A-Z0-9]+))?$', s)
    if not m:
        return re.escape(s)
    pre, sep, _num, suf, sep2, tail = m.groups()
    p = re.escape(pre) + (re.escape(sep) + '?' if sep else '') + r'\d+[A-Z]?'      # F6 also catches F6A
    if sep2:
        p += f'(?:{re.escape(sep2)}[A-Z0-9]+)?'
    return p


def merge_patterns(pats):
    pats = list(dict.fromkeys(p for p in pats if p))
    if not pats: return ''
    return pats[0] if len(pats) == 1 else '(' + '|'.join(pats) + ')'


def compile_full(p):
    try:
        return re.compile(r'^(?:' + p + r')$', re.I)
    except re.error:
        return None


# ---------------------------------------------------------------------------- matches on the drawing
def matches(model, role, value, extra=None):
    """-> (poly indices, text indices, short description) of everything the value catches"""
    empty = np.zeros(0, int)
    if value in (None, '', [], {}):
        return empty, empty, 'not set'
    k = role.kind
    if k in ('layer', 'layers', 'suffix'):
        names = [value] if isinstance(value, str) else list(value)
        if k == 'suffix':
            ids = [i for i, n in enumerate(model.layers) if any(n.endswith(s) for s in names)]
        else:
            ids = [i for i, n in enumerate(model.layers) if n in names]
        pis = np.nonzero(np.isin(model.p_layer, ids))[0]
        tis = np.nonzero(np.isin(model.t_layer, ids))[0] if role.key == 'label_layer' else empty
        if role.key == 'label_layer':
            return empty, tis, f'{len(tis)} texts on {len(ids)} layer(s)'
        closed = sum(1 for i in pis[:20000] if np.allclose(model.poly(i)[0], model.poly(i)[-1]))
        return pis, empty, f'{len(pis)} lines ({closed} closed) on {len(ids)} layer(s)'
    if k == 'textre':
        rx = compile_full(value)
        if rx is None:
            return empty, empty, 'invalid pattern'
        tis = np.array([i for i, s in enumerate(model.t_text) if rx.match(s.strip())], dtype=int)
        distinct = sorted({model.t_text[i].strip().upper() for i in tis})
        return empty, tis, f'{len(tis)} labels, {len(distinct)} distinct: ' + ', '.join(distinct[:30]) + (' ...' if len(distinct) > 30 else '')
    if k == 'block':
        ii = [j for j, b in enumerate(model.ins) if b[0] == value]
        pis = np.nonzero(np.isin(model.p_ins, ii))[0]
        tis = np.nonzero(np.isin(model.t_ins, ii))[0]
        if role.key != 'axis_block':
            return pis, tis, f'{len(ii)} inserts of {value}'
        tag = (extra or {}).get('axis_attr')
        names = sorted({model.ins[j][4].get(tag, '') for j in ii}) if tag else []
        return pis, tis, f'{len(ii)} bubbles' + (f', axes: {", ".join(n for n in names if n)[:200]}' if names else '')
    return empty, empty, ''


# ---------------------------------------------------------------------------- clicks -> values
def value_from_click(model, role, hit, current):
    """the new value of a role after a click on `hit` (toggle for multi-layer roles)"""
    d = model.describe(hit)
    if not d:
        return current, 'nothing under the cursor'
    lay = d['layer']
    if role.kind == 'layer':
        return lay, f'layer {lay}'
    if role.kind in ('layers', 'suffix'):
        name = short_layer(lay) if role.kind == 'suffix' else lay
        cur = list(current or [])
        if name in cur:
            cur.remove(name); return cur, f'removed {name}'
        return cur + [name], f'added {name}'
    if role.kind == 'textre':
        if d['type'] != 'TEXT':
            return current, 'click a text'
        p = text_pattern(d['text'])
        cur = current or ''
        parts = (cur[1:-1].split('|') if cur.startswith('(') and cur.endswith(')') else [cur]) if cur else []
        if cur and compile_full(cur) and compile_full(cur).match(d['text'].strip()):
            return current, f'"{d["text"]}" already caught'
        return merge_patterns(parts + [p]), f'pattern for "{d["text"]}": {p}'
    if role.kind == 'block':
        ins = d.get('insert')
        if not ins:
            return current, 'not a block - click on the bubble itself'
        return ins['block'], f'block {ins["block"]}  attributes {ins["attribs"]}'
    return current, ''


def guess_axis_tags(model, block):
    """which attribute holds the axis name and which the family (X / Y): from the values seen"""
    tags = {}
    for b in model.ins:
        if b[0] != block: continue
        for t, v in b[4].items():
            tags.setdefault(t, set()).add(v.strip().upper())
    num = fam = None
    for t, vals in tags.items():
        if vals and vals <= {'X', 'Y', 'H', 'V', ''}:
            fam = t
        elif vals and num is None and any(re.search(r'\d', v) for v in vals):
            num = t
    return num, fam, {t: sorted(v)[:12] for t, v in tags.items()}


def window_value(rect):
    x0, y0, x1, y1 = rect
    return [round((x0 + x1) / 2), round((y0 + y1) / 2), round(abs(y1 - y0))]


def window_rect(v, aspect=1.6):
    cx, cy, H = v; W = H * aspect
    return (cx - W / 2, cy - H / 2, cx + W / 2, cy + H / 2)


# ---------------------------------------------------------------------------- project.json
def get_value(P, key):
    """a role's value in project.json ('a.b' = key b inside object a)"""
    if '.' not in key: return P.get(key)
    a, b = key.split('.', 1)
    return (P.get(a) or {}).get(b) if isinstance(P.get(a), dict) else None


def rect_value(rect):
    x0, y0, x1, y1 = rect
    return [round(min(x0, x1)), round(min(y0, y1)), round(max(x0, x1)), round(max(y0, y1))]


def save(ws, values):
    """merge the taught keys into work/project.json -> keys written"""
    pj = ws.work / 'project.json'
    P = ws.project()
    for k, v in values.items():
        if v not in (None, '', [], {}):
            if '.' in k:
                a, b = k.split('.', 1)
                if not isinstance(P.get(a), dict): P[a] = {}
                P[a][b] = v
                if a in ('stairs', 'sog') and not P[a].get('dxf'):
                    P[a]['dxf'] = ws.project().get('dxf') or ws.meta.get('main_dxf', '')   # the plan being read
            else:
                P[k] = v
    pj.write_text(json.dumps(P, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    return [k for k, v in values.items() if v not in (None, '', [], {})]


# ---------------------------------------------------------------------------- first guesses
KEYWORDS = {
    'beam_layer': (['GRBM', 'GRADE', 'G-BEAM', 'TIE-BEAM', 'TIEBEAM'], []),
    'col_layers': (['COLS-CONC', 'COLUMN', 'COL-CONC'], ['IDEN', 'TXT', 'HATCH', 'DIM']),
    'grid_layers': (['AXIS', 'GRID'], ['TXT', 'TEXT', 'LABEL', 'BUBBLE', 'DIM']),
    'fnd_layers': (['FNDN', 'FOUND', 'FTNG', 'FOOTING'], ['PC', 'IDEN', 'TXT', 'GRBM', 'HATCH', 'DIM', 'RBAR']),
    'fnd_pc_layers': (['-PC', 'PLAIN', 'BLIND', 'P.C'], ['TXT', 'IDEN']),
    'fnd_col_layers': (['COLS-CONC', 'COLUMN'], ['IDEN', 'TXT', 'HATCH']),
    'core_outline_layer': (['CORE-WALL', 'SHEAR', 'CORE'], ['IDEN', 'TXT', 'FNDN', 'COLS']),
}
LABEL_HINTS = {'label_layer': r'^GB-?\d+[A-Z]?$', 'footing_label_re': r'^(F|CF|FF|RAFT|ST|SF|MF)-?\d+[A-Z]?(-[A-Z])?$'}


def suggest(model):
    """first guesses for the roles, from layer names, label texts and blocks -> {key: value}. They are only proposals:
    the reader shows what each one catches and the engineer confirms or corrects with a click."""
    out = {}
    cnt = model.layer_count
    for key, (inc, exc) in KEYWORDS.items():
        r = BY_KEY[key]
        exc = exc + ['RFT', 'RBAR', 'PATT', 'SECT', 'ANNO', 'TEXT', 'SLAB']
        cands = [(int(cnt[i]), n) for i, n in enumerate(model.layers)          # the layer's own name, not its xref path
                 if cnt[i] > 0 and any(k in short_layer(n).upper() for k in inc) and not any(k in short_layer(n).upper() for k in exc)]
        if not cands: continue
        cands.sort(reverse=True)
        if r.kind == 'layer':
            out[key] = cands[0][1]
        else:
            names = [short_layer(n) if r.kind == 'suffix' else n for c, n in cands[:3] if c >= max(5, cands[0][0] * 0.05)]
            out[key] = list(dict.fromkeys(names))
    # GB label layer: the layer holding most GB1-like texts
    rx = re.compile(LABEL_HINTS['label_layer'], re.I)
    hits = {}
    for i, s in enumerate(model.t_text):
        if rx.match(s.strip()):
            hits[model.t_layer[i]] = hits.get(model.t_layer[i], 0) + 1
    if hits:
        out['label_layer'] = model.layers[max(hits, key=hits.get)]
    # footing labels: one pattern per prefix actually used
    rx = re.compile(LABEL_HINTS['footing_label_re'], re.I)
    pats = [text_pattern(s) for s in sorted({s.strip().upper() for s in model.t_text if rx.match(s.strip())})]
    if pats:
        out['footing_label_re'] = merge_patterns(pats)
    # grid bubbles: the block inserted most often whose attributes look like axis names
    best = None
    by = {}
    for b in model.ins:
        if b[4]: by.setdefault(b[0], []).append(b[4])
    for name, atts in by.items():
        vals = [v for a in atts for v in a.values()]
        axisy = sum(1 for v in vals if re.match(r"^[A-Z]?\d{1,3}[A-Z'*]?$|^[A-Z]{1,2}'?$", v.strip(), re.I))
        if len(atts) >= 6 and axisy >= 0.6 * len(vals) and (best is None or len(atts) > best[1]):
            best = (name, len(atts))
    if best:
        out['axis_block'] = best[0]
    # layouts: the one named like a foundation / GB plan
    for key, words in (('layout', ['SOG', 'GRADE', 'GB', 'TIE']), ):
        for name, wins in model.layouts.items():
            if wins and any(w in name.upper() for w in words):
                out[key] = name; break
    for name, wins in model.layouts.items():
        if wins and any(w in name.upper() for w in ('FOUND', 'FND', 'FTNG', 'FOOT')):
            w = max(wins, key=lambda w: (w[2] - w[0]) * (w[3] - w[1]))
            out['fnd_view'] = window_value(w); break
    return out
