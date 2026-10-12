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
    if m.get('zones'):                          # exact zones from the drawn bar + dimension (mats_scan2.py)
        ad = []
        for z in m['zones']:
            o0, o1 = (b[0], b[1]) if z['along'] == 'X' else (b[1], b[0])     # origin along / across
            ad.append(dict(d=z['d'], s=z['s'], layer=z['layer'], note=z['note'], along=z['along'], L=z['L'], n=z['n'],
                           a0=z['a0'] - o0, a1=z['a1'] - o0, z0=z['z0'] - o1, z1=z['z1'] - o1, x=z['x'] - b[0], y=z['y'] - b[1]))
        if len(m['zones']) < len([a for a in m['adds']]):
            notes.append(f"{m['lab']}: {len(m['adds'])} ADD texts, {len(m['zones'])} drawn zones - check")
    else:
        ad = adds_of(m, b[0], b[1])
    shape = tuple((round(x - b[0], -1), round(y - b[1], -1)) for x, y in m['poly'].exterior.coords) if not m['rect'] else ()
    key = (m['lab'], L, W, shape, tuple(sorted((a['d'], a['s'], a['L'], a['layer'], a['along']) for a in ad)))
    groups.setdefault(key, []).append((m, ad))
cnt = collections.Counter()
on_plan = {m['lab'] for m in mats}
BASE = lambda lab: re.sub(r'^(RAFT-?\d+|CF\d+)[A-Z]?(-[A-Z])?$', r'\1', lab)
for (lab, L, W, shape, _), items in groups.items():
    cnt[lab] += 1
    if cnt[lab] == 1: name = lab
    else:                                       # TYPE number, never a letter: the consultant's own marks use letters
        name = f'{lab}-T{cnt[lab]}'               # (RAFT-1B, RAFT-2-B) - a RAFT-1-B of ours would be read as his RAFT-1B
    m, ad = items[0]; b = m['bbox']
    base = ext.get(lab) or ext.get(BASE(lab)); src = lab
    if base is None: continue
    cols = []
    for k in np_['cl']:
        if m['poly'].contains(__import__('shapely.geometry', fromlist=['Point']).Point(*k['c'])):
            r = k['r'].get(k['t']) or next(iter(k['r'].values()))
            cols.append([round(r[0] - b[0]), round(r[1] - b[1]), round(r[2] - b[0]), round(r[3] - b[1]), k['t']])
    poly = [[round(x - b[0]), round(y - b[1])] for x, y in m['poly'].exterior.coords][:-1]
    if W > L:                                   # long side along x on the sheet: turn the plan 90 deg (x, y) -> (y, L - x)
        cols = [[c[1], L - c[2], c[3], L - c[0], c[4]] for c in cols]
        poly = [[y, L - x] for x, y in poly]
        for a in ad:
            a['x'], a['y'] = a['y'], L - a['x']
            if 'a0' in a:
                if a['along'] == 'X': a['a0'], a['a1'] = L - a['a1'], L - a['a0']
                else: a['z0'], a['z1'] = L - a['z1'], L - a['z0']
            a['along'] = 'Y' if a['along'] == 'X' else 'X'
        L, W = W, L
    f = dict(base, name=name, L=L, W=W, pcL=L + 200, pcW=W + 200, no=len(items), cols=cols, adds=ad, part=False,
             col=cols[0][:4] if cols else [L / 2 - 200, W / 2 - 200, L / 2 + 200, W / 2 + 200], mat=True,
             rect=bool(m['rect']), poly=poly, base=BASE(lab), at=[[round(x), round(y)] for x, y in ((it[0]['lx'], it[0]['ly']) for it in items)])
    if not m['rect']: notes.append(f'{name}: outline is not a rectangle ({len(poly)} corners) - detailed on its real shape (gen_mat.py)')
    out[name] = f
json.dump(out, open('mats.json', 'w'), indent=1)
print(len(out), 'mat types,', sum(f['no'] for f in out.values()), 'mats')
for n, f in out.items(): print(' ', n, f['L'], f['W'], f['h'], 'NO', f['no'], 'cols', len(f['cols']), 'adds', len(f['adds']))
print('\n'.join(notes))
