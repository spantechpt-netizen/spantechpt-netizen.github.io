"""Strip footing per zone: the whole network is modelled once (run ends need their neighbours), each run goes to the
zone holding the larger part of it (reported when a run crosses a zone line), then the zone's section, details,
plan parts and BBS -> out/ZONES/AREA_n_STRIP.dxf."""
import sys, collections
import zone_util as Z
import gen_st_plan as G, gen_st, gen_cd
from gen import new_doc, seq_zone, seq_save, seq_none, BarList, draw_bbs

els, cols = gen_cd.build()
runs, F = G.model(els)
by = collections.defaultdict(list); notes = []
for r in runs:
    sh = Z.zone_share(G.band(r, r['lo'], r['hi']))
    zn = max(sh, key=sh.get); by[zn].append(r)
    if len(sh) > 1 and min(sh.values()) > 0.02:
        notes.append(f"{G.NAME} {r['name']} crosses {', '.join(f'{k} {v:.0%}' for k, v in sh.items())} -> {zn}")
for zn in (sys.argv[1:] or Z.NAMES):
    gen_st.ZONE = zn; gen_cd.ZONE = zn
    rs = by.get(zn)
    if not rs: seq_none('STRIP', zn); continue
    bl = BarList(); doc = new_doc()
    seq_zone(doc, zn, 'STRIP', Z.NAMES)                      # running sheet numbers across the zones
    for n_, col in gen_cd.LAYERS.items():
        if n_ not in doc.layers: doc.layers.add(n_, color=col)
    m0 = Z.base_meta(zn, 'SDW-STR-FDN', '1:100', f'COVER FOOTINGS {G.C}; LAP 60d; MAX. BAR 12 M.')
    idx = gen_st.section_sheet(doc, 0, bl, G.B, G.H, G.SP.get('pcB', G.B + 200), G.n_m, G.d, G.ds, G.NAME, meta0=m0)
    idx = G.detail_sheet(doc, idx, m0)
    P = G.plan_prims(rs, els, bl)
    m1 = dict(m0); m1['title'] = f'STRIP FOOTING - {zn}'
    idx, nt = G.draw_parts(doc, rs, els, P, idx, m0)
    m = dict(m0); m['title'] = f'STRIP FOOTING {G.NAME} - {zn}\nBBS'; m['dwg'] = f'SDW-STR-FDN-{G.NAME}-{Z.CODES[zn]}'
    nb = draw_bbs(doc, idx, bl.sorted(), m)
    seq_save(doc)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_STRIP.dxf")
    print(zn, 'runs', [r['name'] for r in rs], round(sum(r['hi'] - r['lo'] for r in rs) / 1000, 1), 'm; plan parts', nt, 'BBS', nb)
print('\n'.join(notes))
