"""Combined footings / rafts -> footing types for gen_f.py (mats.json): identical outlines (label + size + additional
bars) grouped as one type with NO = count; columns inside; additional bars from the plan notes."""
import json, pickle, re, math, collections
P = json.load(open('project.json')); ext = json.load(open('footings_ext.json'))
mats = pickle.load(open('mats.pkl', 'rb')); np_ = pickle.load(open('neck_pairs.pkl', 'rb'))
out = {}; groups = collections.OrderedDict(); notes = []
def adds_of(m, x0, y0):
    res = []
    for s, x, y, rot in m['adds']:
        mm_ = re.match(r'^T\s*(\d+)\s*@\s*(\d+)\s*(.*)$', s.upper()); d, sp, rest = int(mm_.group(1)), int(mm_.group(2)), mm_.group(3)
        along = 'Y' if abs((rot or 0) % 180 - 90) < 5 else 'X'
        Ls = sorted(m['L_txt'], key=lambda t: math.dist((t[1], t[2]), (x, y)))
        L = int(re.sub(r'\D', '', Ls[0][0])) if Ls and math.dist((Ls[0][1], Ls[0][2]), (x, y)) < 900 else None
        res.append(dict(d=d, s=sp, layer='T' if 'TOP' in rest else 'B', note=rest.strip(), along=along, x=x - x0, y=y - y0, L=L))
    for a in res:                                        # bars in a zone: count over the length of the crossing bars
        cross = [b for b in res if b['along'] != a['along'] and b['layer'] == a['layer'] and b['L'] and math.dist((a['x'], a['y']), (b['x'], b['y'])) < 3000]
        width = cross[0]['L'] if cross else a['L'] or 1000
        a['n'] = int(width / a['s']) + 1
    return [a for a in res if a['L']]
for m in mats:
    if m['lab'].startswith('ST'): continue
    b = m['bbox']; L, W = round(b[2] - b[0]), round(b[3] - b[1])
    ad = adds_of(m, b[0], b[1])
    key = (m['lab'], L, W, tuple(sorted((a['d'], a['s'], a['L'], a['layer'], a['along']) for a in ad)))
    groups.setdefault(key, []).append((m, ad))
cnt = collections.Counter()
for (lab, L, W, _), items in groups.items():
    cnt[lab] += 1
    name = lab if cnt[lab] == 1 else f'{lab}-{chr(64 + cnt[lab])}'
    m, ad = items[0]; b = m['bbox']
    base = ext.get(lab); src = lab
    if base is None: continue
    cols = []
    for k in np_['cl']:
        if m['poly'].contains(__import__('shapely.geometry', fromlist=['Point']).Point(*k['c'])):
            r = k['r'].get(k['t']) or next(iter(k['r'].values()))
            cols.append([round(r[0] - b[0]), round(r[1] - b[1]), round(r[2] - b[0]), round(r[3] - b[1]), k['t']])
    if W > L:                                   # long side along x on the sheet: turn the plan 90 deg (x, y) -> (y, L - x)
        cols = [[c[1], L - c[2], c[3], L - c[0], c[4]] for c in cols]
        for a in ad:
            a['x'], a['y'] = a['y'], L - a['x']; a['along'] = 'Y' if a['along'] == 'X' else 'X'
        L, W = W, L
    f = dict(base, name=name, L=L, W=W, pcL=L + 200, pcW=W + 200, no=len(items), cols=cols, adds=ad, part=False,
             col=cols[0][:4] if cols else [L / 2 - 200, W / 2 - 200, L / 2 + 200, W / 2 + 200], mat=True,
             rect=bool(m['rect']))
    if not m['rect']: notes.append(f'{name}: outline is not a rectangle - detailed on its bounding rectangle {L}x{W}')
    out[name] = f
json.dump(out, open('mats.json', 'w'), indent=1)
print(len(out), 'mat types,', sum(f['no'] for f in out.values()), 'mats')
for n, f in out.items(): print(' ', n, f['L'], f['W'], f['h'], 'NO', f['no'], 'cols', len(f['cols']), 'adds', len(f['adds']))
print('\n'.join(notes))
