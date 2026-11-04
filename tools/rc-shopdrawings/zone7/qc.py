import json, sys
W_, PN = sys.argv[1], sys.argv[2]
sys.path.insert(0, W_); sys.argv = ['x']; import gen_gbsec as G
LJ = json.load(open(f'{W_}/lines_final_{PN}.json')); C = json.load(open(f'{W_}/gbsec_{PN}.json'))
bad = []; tot = {}; built = {}; nst = 0
for sh in [s for s in C['sheets'] if s.get('kind') != 'plan']:
    if sh.get('kind') == 'starter':
        ss = G.StarterSet(built[sh['line']], **C['starter_bar']); m = ss.marks[0]
        if m['L'] != sum(G.bbs_parts(m)) or m['n'] != 16: bad.append(('starter', m['n'], m['L']))
        tot[16] = tot.get(16, 0) + m['n'] * m['L'] / 1000 * G.UW(16)
        print(sh['seq'], f"{sh['sec']}-{sh['sec']}", 'STARTERS', f"{m['n']} T16-{m['L']} ({ss.leg}+{ss.inside}+{ss.lap})", round(m['n'] * m['L'] / 1000 * G.UW(16), 2)); continue
    L = next(l for l in LJ[PN] if l['code'] == sh['line']); L = G.beam_ends(L, LJ[PN], C['schedule'])
    if L.get('starters_abs'): L['starters'] = [(v - L['a'], s) for v, s in L['starters_abs']]
    ln = G.Line(L, C['schedule'], C['columns'], 850); ln.build([]); built[sh['line']] = ln
    p = C['schedule'][ln.typ]
    for m in ln.marks:
        pr = G.bbs_parts(m)
        if pr and sum(pr) != m['L']: bad.append((sh['seq'], 'length', m['mark']))
        if m['pos'] == 'T' and m['d'] != p['dt'] or m['pos'] == 'B' and m['d'] != p['db']: bad.append((sh['seq'], 'dia'))
        tot[m['d']] = tot.get(m['d'], 0) + m['n'] * m['L'] / 1000 * G.UW(m['d'])
    for b_ in 'TB':
        n = sum(pc['n'] for b in ln.bars if b['pos'] == b_ for pc in b['pieces'][:1])
        if n != (p['nt'] if b_ == 'T' else p['nb']): bad.append((sh['seq'], 'count', b_))
    for st in ln.stirs:
        ps = st['pos']; g = [b - a for a, b in zip(ps, ps[1:])] or [0]; nst += st['n']
        if st.get('opening'):
            if max(g) > 125 or ps[0] < st['a'] or ps[-1] > st['b']: bad.append((sh['seq'], 'opening stirrups'))
        elif ps[0] - st['a'] != 50 or st['b'] - ps[-1] != 50 or max(g) > 125 or min(g) < 60: bad.append((sh['seq'], 'stirrups'))
    for m in ln.marks:
        if m['pos'] == 'S' and m['n'] != sum(st['n'] for st in ln.stirs if st['mark'] == m['mark']): bad.append((sh['seq'], 'bbs stirrups'))
    kg = sum(m['n'] * m['L'] / 1000 * G.UW(m['d']) for m in ln.marks)
    print(sh['seq'], f"{sh['sec']}-{sh['sec']}", ln.typ, f"{ln.w}x{ln.h}", f"{ln.top / 1000:+.2f}", round(ln.len), '|'.join(q['lab'].split(' (')[0] for q in ln.sup), [s_['n'] for s_ in ln.stirs], f"{kg:.2f}")
print('QC problems:', bad or 'none', '| stirrups', nst)
print('totals', {d: round(v, 2) for d, v in sorted(tot.items())}, round(sum(tot.values()), 2))
