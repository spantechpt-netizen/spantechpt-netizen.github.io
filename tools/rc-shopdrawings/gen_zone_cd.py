"""Concrete dimensions per zone, on the FINAL plan marks: the scan of the plan geometry is relabelled with the final
plan's labels (isolated marks + CF / raft marks), so a re-assigned footing (F6 -> F6A ...) gets its new schedule size;
footings no longer on the final plan (fence package, removed footings) are dropped. Per zone: plan parts 1:100 +
sections along every grid line through the zone -> out/ZONES/AREA_n_CONCRETE_DIM.dxf"""
import sys, re, math
from shapely.geometry import Point
import zone_util as Z
import gen_cd
from gen import new_doc

old = list(gen_cd.SCAN['lab'])
newlabs = [(s, x, y) for s, x, y in Z.LABS] + [(m['lab'], m['lx'], m['ly']) for m in Z.MP] + \
          [(s, x, y) for s, x, y in old if s.startswith('ST')]
gen_cd.SCAN['lab'] = newlabs
gen_cd.SCH.update(Z.FT)                                    # the new schedule rows (F6A, F15B ...)
gen_cd.STRIP_EL['h'] = gen_cd.STRIP.get('h'); gen_cd.STRIP_EL['lab'] = gen_cd.STRIP.get('name', 'ST-01')
els, cols = gen_cd.build()
gone_pts = [Point(x, y) for s, x, y in old if not s.startswith('ST') and not any(math.hypot(x - a, y - b) < 1500 for t, a, b in newlabs)]
keep = []
for e in els:
    if not e['lab'] and any(e['rc'].buffer(300).contains(p) for p in gone_pts): continue    # not on the final plan
    keep.append(e)
print('elements', len(els), '-> kept', len(keep), '(dropped: not on the final plan)')
_cuts = gen_cd.cuts_along
CUR = {}
def cuts_zone(nm, fam, c, lo, hi, els_, cols_):
    """strip cuts (open wall lines, not elements) only where the cut lies in the current zone"""
    out, crossing = _cuts(nm, fam, c, lo, hi, els_, cols_)
    keep_ = []
    for k, a, b, e in out:
        if e is gen_cd.STRIP_EL:
            u = (a + b) / 2; x, y = (u, c) if fam == 'X' else (c, u)
            if Z.zone_of(x, y) != CUR['zn']: continue
        keep_.append((k, a, b, e))
    return keep_, crossing
gen_cd.cuts_along = cuts_zone
for zn in (sys.argv[1:] or Z.NAMES):
    CUR['zn'] = zn
    ez = [e for e in keep if Z.zone_of(e['rc'].centroid.x, e['rc'].centroid.y) == zn]
    if not ez: continue
    cz = [c for c in cols if any(e['rc'].buffer(200).contains(Point(*c['c'])) for e in ez)]
    doc = new_doc()
    for n, col in gen_cd.LAYERS.items():
        if n not in doc.layers: doc.layers.add(n, color=col)
    m0 = Z.base_meta(zn, 'SDW-STR-CD', '1:100')
    m0['notes'] = ['ALL DIMENSIONS IN MM; LEVELS IN M.', 'PC 100 UNDER ALL FOOTINGS.', f'{zn} ONLY - SEE KEY PLAN FOR THE ZONE.']
    gen_cd.TF = 1.0
    idx, nt = gen_cd.draw_plan(doc, ez, cz, 0, m0)
    idx2, ns = gen_cd.draw_sections(doc, ez, cz, idx, m0)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_CONCRETE_DIM.dxf")
    ch = [f"{e['lab']} drawn {e['drawn']}" for e in ez if e.get('changed')]
    print(zn, 'elements', len(ez), 'plan parts', nt, 'section strips', ns, 'sheets', idx2, '| schedule size differs from drawn:', ch)
