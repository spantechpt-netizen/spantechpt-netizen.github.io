"""Grade beams per zone: every beam run (runs.pkl, GB plan coordinates) is moved to the foundation plan
(project.json -> gb_to_fnd [dx, dy], found by matching the grid lines) and goes to the zone holding the larger part
of its length (runs crossing a zone line are reported); then the --all packing of gen2.py with the zone's runs only
-> out/ZONES/AREA_n_GRADE_BEAMS.dxf with its BBS."""
import sys, json, pickle, collections
from shapely.geometry import LineString
import zone_util as Z
sys_argv = sys.argv[:]; sys.argv = sys.argv[:1]
import gen2
from gen import new_doc, BarList, draw_bbs, Sheet, ST
sys.argv = sys_argv

runs = pickle.load(open('runs.pkl', 'rb')); cols = pickle.load(open('cols.pkl', 'rb'))
DXg, DYg = Z.PRJ.get('gb_to_fnd', [0, 0])
by = collections.defaultdict(list); notes = []
for r in runs:
    ln = LineString([(r['lo'] + DXg, r['c'] + DYg), (r['hi'] + DXg, r['c'] + DYg)]) if r['hor'] else \
         LineString([(r['c'] + DXg, r['lo'] + DYg), (r['c'] + DXg, r['hi'] + DYg)])
    if ln.length < 1: continue
    sh = Z.zone_share(ln)
    cl = {k: v for k, v in sh.items() if k != Z.REST}       # the gaps between the zone clouds count as the rest zone:
    zn = max(cl, key=cl.get) if cl and max(cl.values()) >= 0.15 else max(sh, key=sh.get)   # prefer a cloud zone
    by[zn].append(r)
    if len(sh) > 1 and sorted(sh.values())[-2] > 0.1:
        notes.append(f"{r.get('lab', 'GB')} on {r['axis']} ({round(r['hi'] - r['lo'])} long) crosses {', '.join(f'{k} {v:.0%}' for k, v in sh.items())} -> {zn}")
for zn in (sys.argv[1:] or Z.NAMES):
    rz = by.get(zn)
    if not rz: continue
    meta0 = Z.base_meta(zn, 'SDW-STR-GB', '1:100 / SEC 1:20', 'COVER GRADE BEAMS 40; GB STIRRUPS STOP AT THE COLUMN FACE.')
    doc = new_doc(); bl = BarList(); reg = []
    st = dict(n=0, open=[]); cur = {}
    def finish(o):
        if o['types']:
            sh = o['sh']; sx = 2600
            sh.text('TYPICAL CROSS SECTIONS  1:20  (CUT MARKS ON THE LONGITUDINAL SECTIONS)', 1800, gen2.Y_SEC + 4900, ST['sub'], 'S-SEC')
            for t in sorted(o['types'], key=lambda t: gen2.SEC_LBL[t]):
                if sx > 27000: break
                sx += gen2.draw_gb_section(sh, sx, gen2.Y_SEC, t, gen2.SEC_LBL[t])
    def slot(width, label):
        for o in st['open']:
            if o['used'] + 1500 + width <= 32800:
                xo = o['used'] + 1500; o['used'] = xo + width; cur['o'] = o
                return o['sh'], xo, False, None
        st['n'] += 1
        meta = dict(meta0); meta['title'] = f'GRADE BEAMS REINFORCEMENT - {zn}\nSHEET {st["n"]:03d}'
        meta['dwg'] = f'{meta0["prefix"]}-{Z.CODES[zn]}-{st["n"]:03d}'
        o = dict(sh=Sheet(doc, 0, -(st['n'] - 1) * 32000, meta), used=gen2.X0 + width, types=set())
        st['open'].append(o); cur['o'] = o
        if len(st['open']) > 4: finish(st['open'].pop(0))
        return o['sh'], gen2.X0, True, meta['dwg']
    class Types:
        def add(self, t): cur['o']['types'].add(t)
    axes = sorted({r['axis'] for r in rz if r.get('axis')}, key=lambda a: (a[0], a))
    for a in axes:
        for off, _rs in gen2.axis_lines(a, rz):
            if sum(r['hi'] - r['lo'] for r in _rs) < 1000: continue
            reg += gen2.draw_axis(doc, a, rz, cols, meta0, off=off, bl=bl, slot=slot, sec_types=Types())
    for o in st['open']: finish(o)
    n = st['n'] + 1
    meta = dict(meta0); meta['title'] = f'GRADE BEAMS - {zn}\nBAR BENDING SCHEDULE (BBS)'; meta['dwg'] = f'{meta0["prefix"]}-{Z.CODES[zn]}-BBS'
    nb = draw_bbs(doc, n - 1, bl.sorted(), meta, Sheet)
    doc.saveas(f"out/ZONES/{zn.replace(' ', '_')}_GRADE_BEAMS.dxf")
    print(zn, 'runs', len(rz), 'axes', len(axes), 'sheets', n - 1, '+ BBS', nb)
print(len(notes), 'beam runs cross a zone line (put in the zone with the larger part):')
print('\n'.join(notes))
