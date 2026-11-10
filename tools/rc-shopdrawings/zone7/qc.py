import json, sys
W_, PN = sys.argv[1], sys.argv[2]; sys_argv = list(sys.argv)
sys.path.insert(0, W_); sys.argv = ['x']; import gen_gbsec as G
LJ = json.load(open(f'{W_}/lines_final_{PN}.json')); C = json.load(open(f'{W_}/gbsec_{PN}.json'))
bad = []; tot = {}; built = {}; nst = 0; G.TOP_LAP = C.get('top_lap', 'support'); kgs = {}; laps = []
for sh in [s for s in C['sheets'] if s.get('kind') not in ('plan', 'sog', 'cd')]:
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
    for b in ln.bars:                                               # every top lap at midspan (middle 2/5 of a clear span)
        for p1, p2 in zip(b['pieces'], b['pieces'][1:]):
            lo, hi = p2['u0'], p1['u1']; cen = (lo + hi) / 2
            if b['pos'] == 'T' and G.TOP_LAP == 'midspan':
                ok = any(a + (bb - a) * 0.3 - 25 <= lo and hi <= a + (bb - a) * 0.7 + 25 for a, bb in ln.spans()) or \
                     any(abs(cen - (a + bb) / 2) < 10 for a, bb in ln.spans())
                if not ok: bad.append((sh['seq'], 'top lap not at midspan', round(lo), round(hi)))
            laps.append((sh['seq'], b['pos'], round(lo), round(hi)))
    kg = sum(m['n'] * m['L'] / 1000 * G.UW(m['d']) for m in ln.marks); kgs[f"{sh['sec']}-{sh['sec']}"] = kg
    print(sh['seq'], f"{sh['sec']}-{sh['sec']}", ln.typ, f"{ln.w}x{ln.h}", f"{ln.top / 1000:+.2f}", round(ln.len), '|'.join(q['lab'].split(' (')[0] for q in ln.sup), [s_['n'] for s_ in ln.stirs], f"{kg:.2f}")
if len(sys_argv) > 3:                                                # the summary table of the DXF against the bars built here
    import ezdxf, logging; logging.getLogger('ezdxf').setLevel(logging.ERROR)
    d = ezdxf.readfile(sys_argv[3]); found = {}
    for lay in d.layouts:
        if 'BBS' not in lay.name: continue
        ts = sorted([e for e in lay.query('TEXT') if e.dxf.layer == 'GB-TITLE' and e.dxf.insert.x > 300], key=lambda e: (-round((e.dxf.align_point.y if e.dxf.halign else e.dxf.insert.y) * 2), e.dxf.insert.x))
        rows = {}
        for e in ts:
            y = round((e.dxf.align_point.y if e.dxf.halign else e.dxf.insert.y) * 2); rows.setdefault(y, []).append(e.dxf.text)
        for r in rows.values():
            for i, t in enumerate(r):
                if t.count('-') == 1 and t.split('-')[0] == t.split('-')[1] and t.split('-')[0].isalpha() and len(r) >= i + 6:
                    found[t] = float(r[i + 5].replace(',', ''))
    for k, v in kgs.items():
        if k not in found or abs(found[k] - v) > 0.05: bad.append(('summary', k, round(v, 2), found.get(k)))
    print('summary rows checked', len(found))
print('QC problems:', bad or 'none', '| stirrups', nst)
print('totals', {d: round(v, 2) for d, v in sorted(tot.items())}, round(sum(tot.values()), 2))
