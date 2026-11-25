"""Extract the beam lines of a zone, part by part: the source plan is rotated by base_deg + the part's extra angle,
window = the part region (given in the base_deg frame) -> <root>/<zone>_<part>/{lines.json, part.json, plans.pkl, geo.pkl, texts.pkl}.
usage: GBZ_CONFIG=cfg.json python3 extc.py <zone> [part ...]      (no part = every part of the zone in the config)
config: zones.<zone>.parts = [[name, extra_deg, "x0,y0,x1,y1"], ...], base_deg, col_snap, col_lab_r, src (default <zone>/src/<zone>.dxf),
        layers.{beam, col, label}."""
import sys, os, json, math, pickle, subprocess, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gbzcfg import Cfg, HERE, WORK
import ezdxf as _ez

z = sys.argv[1]; K = Cfg(z); Zc = K.z
want = sys.argv[2:]
BASE = float(Zc.get('base_deg', 0))
LB, LC, LL = K.layers['beam'], K.layers['col'], K.layers['label']
SNAP_L = set(LB) | set(LC)
SRC0 = K.p(Zc.get('src') or f'{z}/src/{z}.dxf')


def one(part, extra, reg):
    W = K.partdir(part); os.makedirs(W, exist_ok=True)
    ang = BASE + extra; src = K.rotsrc(part); os.makedirs(os.path.dirname(src), exist_ok=True)
    subprocess.run(['python3', os.path.join(HERE, 'rot.py'), SRC0, src, str(ang)], check=True, capture_output=True)
    c, s_ = math.cos(math.radians(-extra)), math.sin(math.radians(-extra))
    pts = [(x, y) for x in (reg[0], reg[2]) for y in (reg[1], reg[3])]
    rp = [(x * c - y * s_, x * s_ + y * c) for x, y in pts]
    win = [min(p[0] for p in rp), min(p[1] for p in rp), max(p[0] for p in rp), max(p[1] for p in rp)]
    env = dict(os.environ, PLANS_JSON=json.dumps({part: win}), BEAM_LAYERS=','.join(LB), COL_LAYERS=','.join(LC), LABEL_LAYERS=','.join(LL),
               COL_SNAP=str(Zc.get('col_snap', 60)), COL_LAB_R=str(Zc.get('col_lab_r', 2000)))
    run = lambda *a: subprocess.run(['python3', *a], env=env, capture_output=True, text=True, cwd=W)
    r = run(os.path.join(WORK, 'dump.py'), src, W); print(r.stdout[-200:], r.stderr[-300:])
    G = pickle.load(open(W + '/geo.pkl', 'rb')); n = 0
    for h in _ez.readfile(src).modelspace().query('HATCH'):          # column hatches -> closed outlines (some columns miss an edge line)
        if h.dxf.layer not in LC: continue
        for path in h.paths:
            try:
                vs = [(v[0], v[1]) for v in path.vertices] if hasattr(path, 'vertices') else [(e.start[0], e.start[1]) for e in path.edges]
            except Exception: continue
            if len(vs) >= 3: G.append((h.dxf.layer, 'LWPOLYLINE', vs + [vs[0]], 256))
    for i, (lay, t, pts_, col) in enumerate(G):                    # snap near-orthogonal beam / column edges (rotation residue)
        if lay not in SNAP_L: continue
        q = list(pts_)
        for k in range(len(q) - 1):
            (x0, y0), (x1, y1) = q[k], q[k + 1]
            if abs(x1 - x0) < 30 and abs(y1 - y0) > 200 and abs(x1 - x0) > 0.01: m = (x0 + x1) / 2; q[k] = (m, y0); q[k + 1] = (m, y1); n += 1
            elif abs(y1 - y0) < 30 and abs(x1 - x0) > 200 and abs(y1 - y0) > 0.01: m = (y0 + y1) / 2; q[k] = (x0, m); q[k + 1] = (x1, m); n += 1
        G[i] = (lay, t, q, col)
    grid = collections.defaultdict(list)                           # merge endpoints closer than 3 mm (open corners after the rotation)
    for i, (lay, t, pts_, col) in enumerate(G):
        if lay not in SNAP_L: continue
        for k, p_ in enumerate(pts_): grid[(round(p_[0] / 5), round(p_[1] / 5))].append((i, k))
    rep = {}
    for key, lst in grid.items():
        for i, k in lst:
            if (i, k) in rep: continue
            p_ = G[i][2][k]; cl = []
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j, m in grid.get((key[0] + dx, key[1] + dy), []):
                        q_ = G[j][2][m]
                        if (j, m) not in rep and abs(q_[0] - p_[0]) < 3 and abs(q_[1] - p_[1]) < 3: cl.append((j, m))
            mx = sum(G[j][2][m][0] for j, m in cl) / len(cl); my = sum(G[j][2][m][1] for j, m in cl) / len(cl)
            for j, m in cl: rep[(j, m)] = (mx, my)
    for (i, k), v in rep.items(): G[i][2][k] = v
    pickle.dump(G, open(W + '/geo.pkl', 'wb'))
    r = run(os.path.join(WORK, 'extract.py'), W, src); print(r.stdout[-600:], r.stderr[-600:])
    r = run(os.path.join(WORK, 'lines.py'), W); open(W + '/lines.log', 'w').write(r.stdout + r.stderr); print(r.stdout[-3000:], r.stderr[-800:])
    json.dump(dict(win=win, ang=ang, src=src), open(W + '/part.json', 'w'))


for name, extra, reg in Zc['parts']:
    if want and name not in want: continue
    reg = list(map(float, reg.split(','))) if isinstance(reg, str) else list(map(float, reg))
    print('==', z, name, 'angle', BASE + float(extra), 'region', reg)
    one(name, float(extra), reg)
