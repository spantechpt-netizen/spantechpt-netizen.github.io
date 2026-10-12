"""Packages per zone: isolated footings + combined footings / rafts of ONE zone, its own sheets and BBS.

inputs: zones.json (zones.py, working coordinates; "_rest" = the zone without an outline), footings.json, mats.json
(mats_build.py: `at` = label positions of every mat of a type), the footing labels of the final plan
(project.json -> fnd_final {dxf, shift}). Drawing number Area field = zone code (project.json -> zone_codes or Z01..).
usage: python3 gen_zones.py [AREA 2 ...]      -> out/ZONES/AREA_n_FOUNDATIONS.dxf"""
import json, os, re, sys, collections, pickle
from ezdxf import recover
from shapely.geometry import Polygon, Point
import gen_f, gen_mat, gen_cd
from gen import new_doc, BarList, draw_bbs, project_notes, Sheet, TA, ST

PRJ = json.load(open('project.json'))
SRC = PRJ['fnd_final']; DX, DY = SRC['shift']
Z = json.load(open(SRC.get('zones', 'zones.json')))
REST = Z.pop('_rest', None)
ZP = {k: Polygon(v) for k, v in Z.items()}
names = sorted(list(ZP) + ([REST] if REST else []), key=lambda s: int(re.sub(r'\D', '', s) or 0))
CODES = PRJ.get('zone_codes') or {n: f"Z{int(re.sub(r'D', '', re.sub(r'[^0-9]', '', n)) or 0):02d}" for n in names}

def zone_of(x, y):
    for k, g in ZP.items():
        if g.contains(Point(x, y)): return k
    return REST

# isolated footings: labels of the final plan
cache = 'final_labels.pkl'
if os.path.exists(cache): labs = pickle.load(open(cache, 'rb'))
else:
    doc, _ = recover.readfile(SRC['dxf']); labs = []
    for e in doc.modelspace():
        if e.dxftype() == 'TEXT' and re.match(r'^(F\d+[A-Z]?|Fx|F)$', e.dxf.text.strip()) and e.dxf.layer.upper().endswith('IDEN'):
            labs.append((e.dxf.text.strip(), e.dxf.insert.x + DX, e.dxf.insert.y + DY))
    pickle.dump(labs, open(cache, 'wb'))
FT = json.load(open('footings.json')); MT = json.load(open('mats.json'))
iso = collections.defaultdict(collections.Counter)
for s, x, y in labs: iso[zone_of(x, y)][s] += 1
mats = collections.defaultdict(collections.Counter)
for n, f in MT.items():
    for x, y in f.get('at') or []: mats[zone_of(x, y)][n] += 1

ELS, COLS = gen_cd.build()
def key_plan(doc, idx, zn, meta):
    """Sheet 1 of a zone: every footing of the zone with the TYPE it is detailed as (several plan marks are
    detailed as more than one type: RAFT-2 -> RAFT-2-T2 ...), grid, zone outline."""
    m = dict(meta); m['title'] = f'STRUCTURAL FOUNDATION - {zn}\nKEY PLAN OF THE ZONE (TYPES)'
    sh = Sheet(doc, 0, -idx * 32000, m)
    zg = ZP.get(zn)
    MP = pickle.load(open('mats.pkl', 'rb'))                 # mats on their real outline (mats_scan2.py)
    polys = [(m['poly'], (m['lx'], m['ly'])) for m in MP if zone_of(m['lx'], m['ly']) == zn]
    polys += [(e['rc'], None) for e in ELS if e['kind'] == 'F' and zone_of(e['rc'].centroid.x, e['rc'].centroid.y) == zn
              and not any(p.intersects(e['rc'].buffer(-50)) for p, _ in polys)]
    if not polys: return 0
    from shapely.ops import unary_union
    X0, Y0, X1, Y1 = unary_union([p for p, _ in polys]).bounds
    k = min(31000 / (X1 - X0 + 4000), 21500 / (Y1 - Y0 + 4000))
    ox, oy = 2500 - (X0 - 2000) * k, 3600 - (Y0 - 2000) * k
    Q = lambda x, y: (ox + x * k, oy + y * k)
    if zg is not None:
        sh.pline([Q(*p) for p in zg.exterior.coords], 'S-SEC', 0)
    for nm, fam, c, lo, hi in gen_cd.axis_lines():
        if fam == 'Y' and X0 - 1500 <= c <= X1 + 1500:
            a_, b_ = max(lo, Y0 - 1500), min(hi, Y1 + 1500)
            if a_ < b_: sh.line(Q(c, a_), Q(c, b_), 'S-AXIS'); sh.text(nm, *Q(c, Y1 + 1700), 180, 'S-AXIS-TXT', align=TA.BOTTOM_CENTER)
        if fam == 'X' and Y0 - 1500 <= c <= Y1 + 1500:
            a_, b_ = max(lo, X0 - 1500), min(hi, X1 + 1500)
            if a_ < b_: sh.line(Q(a_, c), Q(b_, c), 'S-AXIS'); sh.text(nm, *Q(X0 - 1700, c), 180, 'S-AXIS-TXT', align=TA.MIDDLE_RIGHT)
    at = [(n, x, y) for n, f in MT.items() for x, y in (f.get('at') or [])]
    for g, e in polys:
        sh.pline([Q(*p) for p in g.exterior.coords], 'S-GB-CONC', 15)
        c_ = Point(*e) if e and g.contains(Point(*e)) else g.representative_point()
        hit = [n for n, x, y in at if g.buffer(300).contains(Point(x, y))]
        lab = hit[0] if hit else (min(((s, (x - c_.x) ** 2 + (y - c_.y) ** 2) for s, x, y in labs), key=lambda t: t[1])[0] if labs else '')
        if True:
            sh.text(lab, *Q(c_.x, c_.y), max(120, min(260, 0.18 * min(g.bounds[2] - g.bounds[0], g.bounds[3] - g.bounds[1]) * k)), 'S-RFT-TXT', align=TA.MIDDLE_CENTER)
    sh.text(f'{zn} - KEY PLAN: EVERY FOOTING WITH THE TYPE IT IS DETAILED AS  (1:{round(100 / k)})', 2500, 1500, ST['panel'], 'S-SEC')
    sh.text('A PLAN MARK DETAILED AS MORE THAN ONE TYPE (DIFFERENT SIZE / SHAPE / ADDITIONAL BARS) GETS -T2, -T3 ... ; '
            'CONSULTANT MARKS (RAFT-1A, RAFT-2-B ...) ARE KEPT AS WRITTEN.', 2500, 900, ST['note'], 'S-RFT-TXT', maxw=33000)
    return 1

os.makedirs('out/ZONES', exist_ok=True)
want = sys.argv[1:] or names
summary = []
for zn in want:
    doc = new_doc(); bl = BarList(); idx = 0; rep = []
    base = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
    base.update(PRJ.get('meta', {})); base['area'] = CODES[zn]
    base['notes'] = project_notes('COVER FOOTINGS 70; PLAIN CONCRETE 100 UNDER FOOTINGS.', f'{zn}: QUANTITIES OF THIS ZONE ONLY.')
    idx += key_plan(doc, idx, zn, base)
    order = sorted(iso[zn], key=lambda s: (len(s), s))
    for n in order:
        if n not in FT: rep.append(f'{n}: not in the schedule'); continue
        f = dict(FT[n]); f['no'] = iso[zn][n]
        meta = dict(base); meta['title'] = f"STRUCTURAL FOUNDATION - {zn}\nREINFORCEMENT - {n}  (NO={f['no']})"; meta['dwg'] = f'SDW-STR-FDN-{n}'
        gen_f.draw_sheet(doc, idx, f, meta, bl); idx += 2 if f.get('adds') else 1
    for n in sorted(mats[zn], key=lambda s: (not s.startswith('CF'), s)):
        f = dict(MT[n]); f['no'] = mats[zn][n]
        kind = 'RAFT' if n.startswith('RAFT') else 'COMBINED FOOTING'
        meta = dict(base); meta['title'] = f"STRUCTURAL {kind} - {zn}\nREINFORCEMENT - {n}  (NO={f['no']})"; meta['dwg'] = f'SDW-STR-FDN-{n}'
        if f.get('rect', True):
            gen_f.draw_sheet(doc, idx, f, meta, bl); idx += 2 if f.get('adds') else 1
        else:
            idx += gen_mat.draw_mat(doc, idx, f, meta, bl, rep)
    meta = dict(base); meta['title'] = f'STRUCTURAL FOUNDATION - {zn}\nBBS'; meta['dwg'] = f'SDW-STR-FDN-{CODES[zn]}'
    nb = draw_bbs(doc, idx, bl.sorted(), meta)
    fn = f"out/ZONES/{zn.replace(' ', '_')}_FOUNDATIONS.dxf"
    doc.saveas(fn)
    kg = sum(r['n_in'] * r['n_el'] * r['L'] / 1000 * r['d'] ** 2 / 162 for r in bl.sorted())
    summary.append((zn, CODES[zn], dict(iso[zn]), dict(mats[zn]), idx, nb, round(kg / 1000, 2)))
    print(zn, CODES[zn], 'isolated', dict(iso[zn]), 'mats', dict(mats[zn]), 'sheets', idx, '+ BBS', nb, 'steel t', round(kg / 1000, 2))
    for r in rep: print('   ', r)
json.dump(summary, open('out/ZONES/summary.json', 'w'), indent=1)
