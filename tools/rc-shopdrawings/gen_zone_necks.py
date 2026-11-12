"""Column necks per zone, re-paired on the FINAL plan: every column (neck_pairs.pkl -> cl: centre + type) takes the
footing type it stands on in the final plan (isolated mark, or the CF / raft TYPE of mats.json, or the strip), the
zone of its centre -> one DXF per zone (out/ZONES/AREA_n_NECKS.dxf) with its BBS.
usage: python3 gen_zone_necks.py [AREA 2 ...]"""
import sys, pickle, collections, json
import zone_util as Z
import gen_n
from gen import new_doc, seq_zone, seq_save, BarList, draw_bbs

np_ = pickle.load(open('neck_pairs.pkl', 'rb'))
pairs = collections.defaultdict(collections.Counter); lost = []; flagged = []
strip_runs = None
for k in np_['cl']:
    x, y = k['c']; t = k['t']
    kind, fn, _ = Z.footing_at(x, y)
    if fn is None:
        # a column on the wall strip
        try:
            import gen_st_plan, strip_net
            if strip_runs is None:
                E, _c = Z.els(); strip_runs = strip_net.strip_runs(E)
            if any(gen_st_plan.band(r, r['lo'], r['hi']).buffer(50).contains(__import__('shapely.geometry', fromlist=['Point']).Point(x, y)) for r in strip_runs):
                fn = Z.PRJ.get('strip', {}).get('name', 'ST-01')
        except Exception: pass
    if fn is None:                                       # close to an isolated footing (drawn outline short): attach + flag
        E, _c = Z.els()
        from shapely.geometry import Point as _P
        near = [e for e in E if e['kind'] == 'F' and e['rc'].distance(_P(x, y)) < 1500]
        labs_ = [s for e in near for s, lx, ly in Z.LABS if e['rc'].buffer(300).contains(_P(lx, ly))]
        if labs_:
            fn = labs_[0]; flagged.append((t, fn, round(x), round(y)))
    if fn is None: lost.append((t, round(x), round(y))); continue
    pairs[Z.zone_of(x, y)][(t, fn)] += 1
sched = gen_n.read_schedule2()
L = Z.lib()
want = sys.argv[1:] or Z.NAMES
summary = {}
for zn in want:
    gen_n.ZONE = zn
    from gen import zone_levels
    _L = zone_levels(zn); WHAT = 'COLUMN STARTER BARS' if _L.get('tof') is not None and _L.get('top_gb', 1e9) <= _L['tof'] else 'COLUMN NECKS'
    doc = new_doc(); bl = BarList(); i = 0; checks = []
    seq_zone(doc, zn, 'NECKS', Z.NAMES)                      # running sheet numbers across the zones
    for (cn, fn), no in sorted(pairs[zn].items()):
        if fn not in L: checks.append(f'{cn} on {fn}: footing type unknown'); continue
        f = dict(L[fn]); f.setdefault('name', fn)
        base, _, var = cn.partition('@')               # size variant 'C8@300x1000': the C8 section on the drawn size
        col = dict(sched[base]); col['name'] = cn
        if var:
            a_, b_ = sorted(int(v) for v in var.split('x'))
            col['b'], col['h'] = a_, b_
            col['dw'], col['dh'] = (b_, a_) if col['dw'] >= col['dh'] else (a_, b_)
            checks.append(f'{cn} on {fn}: column drawn {a_}x{b_}, schedule {base} {min(sched[base]["dw"], sched[base]["dh"])}x{max(sched[base]["dw"], sched[base]["dh"])} - bars of {base} on the drawn size')
        col['b_draw'], col['h_draw'] = col['dw'], col['dh']
        meta = Z.base_meta(zn, 'SDW-STR-NCK', 'ELEV 1:25 / SEC 1:10', 'COVER COLUMNS 40; Ld IN THE FOOTING >= 60d (STRAIGHT + FOOT).')
        meta['venue'] = 'NK'; meta['title'] = f'{WHAT} - {zn}\n{cn} ON {fn}'; meta['dwg'] = f'SDW-STR-NCK-{cn}-{fn}'
        Hn, ld = gen_n.draw_neck(doc, i, col, f, meta, bl, int(no)); i += 1
        if not ld[3]: checks.append(f'{cn} on {fn}: Ld does not fit - see sheet')
        if ld[4]: checks.append(f'{cn} on {fn}: feet turned inwards')
    meta = Z.base_meta(zn, 'SDW-STR-NCK'); meta['venue'] = 'NK'; meta['title'] = f'{WHAT} - {zn}\nBBS'; meta['dwg'] = f'SDW-STR-NCK-{Z.CODES[zn]}'
    nb = draw_bbs(doc, i, bl.sorted(), meta)
    seq_save(doc)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_NECKS.dxf")
    n_cols = sum(pairs[zn].values())
    summary[zn] = dict(sheets=i, bbs=nb, columns=n_cols, pairs={f'{a}:{b}': c for (a, b), c in sorted(pairs[zn].items())}, checks=checks)
    print(zn, 'columns', n_cols, 'neck sheets', i, '+ BBS', nb, checks)
print('columns on no footing of the final plan (not in this package):', len(lost), collections.Counter(t for t, x, y in lost))
print('attached to a footing within 1.5 m (check):', flagged)
json.dump(dict(summary=summary, lost=lost, flagged=flagged), open('out/ZONES/necks_summary.json', 'w'), indent=1)
