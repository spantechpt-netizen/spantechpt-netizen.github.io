"""Isolated footing shop drawings, one A3 sheet per footing type, in the office ASD-style call-outs:
   (mark) 37Ø25  L=5.40m  S=11.0cm  - B2   ;  straight length + leg lengths in metres beside the bar,
   distribution line with the dot where the drawn bar crosses it, overall sizes in mm, thickness in a circle.
Panels: BOTTOM REINFORCEMENT PLAN @ X&Y, TOP REINFORCEMENT PLAN @ X&Y (when the schedule has top bars),
FOUNDATION SIDE REINFORCEMENT, and a section through the footing."""
import json, math, pickle, sys
from gen import new_doc, Sheet, TA

PRJ = json.load(open('project.json'))
COVER = PRJ.get('footing_cover', 70)
PHI = '%%c'                       # AutoCAD diameter symbol


def spacing(per_m):               # n bars per metre -> spacing in mm, floored to 5 mm
    return math.floor(1000 / per_m / 5) * 5


def count(width, s):              # bars distributed over width - 2c
    return math.ceil((width - 2 * COVER) / s) + 1


def bars_for(f):
    """f: dict(name, L (x size), W (y size), h, bot=(n_x,d_x,n_y,d_y) per m, top=same or None) -> bar list"""
    out = []
    lg = f['h'] - 2 * COVER
    for layer, (nx, dx, ny, dy), up in (('B', f['bot'], True), ('T', f['top'], False)):
        if not nx: continue
        sx, sy = spacing(nx), spacing(ny)
        # long-direction bars are the outer layer (B1 / T2), short-direction bars the inner (B2 / T1) - Roya FC11
        long_is_x = f['L'] >= f['W']
        for along, n_m, d, s in (('X', nx, dx, sx), ('Y', ny, dy, sy)):
            run = (f['L'] if along == 'X' else f['W']) - 2 * COVER
            across = f['W'] if along == 'X' else f['L']
            is_long = (along == 'X') == long_is_x
            tag = (layer + ('1' if is_long else '2')) if layer == 'B' else (layer + ('2' if is_long else '1'))
            out.append(dict(layer=layer, tag=tag, along=along, d=d, s=s, n=count(across, s),
                            straight=run, leg=lg, L=run + 2 * lg, up=up))
    return out


def side_bars(f):
    """Perimeter side bars Ø12 (loops) - rows every <= 300 mm of the free height; chairs Ø16 @100x100cm."""
    free = f['h'] - 2 * COVER
    rows = max(1, math.ceil(free / 300) - 1)
    per = 2 * (f['L'] - 2 * COVER + f['W'] - 2 * COVER) + 2 * 60 * 12        # loop + lap 60d
    chair_n = max(4, math.ceil(f['L'] / 1000) * math.ceil(f['W'] / 1000))
    return dict(rows=rows, L=per, chairs=chair_n, chair_L=300 + (f['h'] - 2 * COVER - 120) * 2 // 1 + 400 + 300)


def draw_sheet(doc, idx, f, meta):
    sh = Sheet(doc, 0, -idx * 32000, meta)
    bars = bars_for(f)
    k = min(4.0, 10000 / f['W'], 14500 / f['L'])     # drawing factor: 4 = 1:25 on the 1:100 frame
    marks = {}
    def mk(b):
        key = (b['d'], b['L'], b['tag'])
        if key not in marks: marks[key] = len(marks) + 1
        return marks[key]
    sh.text(f['name'], 2000, 27900, 600, 'S-AXIS-TXT')
    sh.circle(4800, 28150, 520, 'S-SEC'); sh.text(str(f['h']), 4800, 28150, 380, 'S-SEC', align=TA.MIDDLE_CENTER)
    sh.text(f"NO={f['no']}", 5700, 27900, 500, 'S-AXIS-TXT')
    sh.text(f"PC {f['pcL']}x{f['pcW']}x{f['pcH']}   RC {f['L']}x{f['W']}x{f['h']} mm", 9000, 27950, 280, 'S-SEC')

    R1, R2 = 14300, 2300
    panels = [('B', 'FOUNDATION BOTTOM REINFORCEMENT PLAN @ X&Y DIRECTION', 2000, R1)]
    if any(b['layer'] == 'T' for b in bars):
        panels.append(('T', 'FOUNDATION TOP REINFORCEMENT PLAN @ X&Y DIRECTION', 18200, R1))
    panels.append(('S', 'FOUNDATION SIDE REINFORCEMENT', 2000 if len(panels) == 2 else 18200, R2 if len(panels) == 2 else R1))
    W_, H_ = f['L'] * k, f['W'] * k
    for kind, title, ox, oy in panels:
        P = lambda x, y: (ox + x * k, oy + y * k)
        sh.pline([P(0, 0), P(f['L'], 0), P(f['L'], f['W']), P(0, f['W'])], 'S-GB-CONC', 0, True)
        sh.text(f['name'], ox + 250, oy + H_ - 650, 400, 'S-AXIS-TXT')
        cx0, cy0, cx1, cy1 = f['col']
        sh.hatch_rect(*P(cx0, cy0), *P(cx1, cy1))
        sh.circle(*P(f['L'] * 0.62, f['W'] * 0.72), 330, 'S-SEC')
        sh.text(str(f['h']), *P(f['L'] * 0.62, f['W'] * 0.72), 260, 'S-SEC', align=TA.MIDDLE_CENTER)
        sh.text(title, ox + W_ / 2, oy - 900, 260, 'S-SEC', align=TA.TOP_CENTER)
        # overall dims in mm
        sh.dim(P(0, 0), P(f['L'], 0), (ox, oy - 450), text=str(f['L']))
        sh.dim(P(0, 0), P(0, f['W']), (ox - 450, oy), angle=90, text=str(f['W']))
        if kind in 'BT':
            for b in [b for b in bars if b['layer'] == kind]:
                m = mk(b)
                lay = 'S-RFT-BOT' if kind == 'B' else 'S-RFT-TOP'
                lgk = min(b['leg'] * k, 1100)                    # legs shown folded into the plan
                sgn = 1 if b['up'] else -1
                if b['along'] == 'X':
                    y = f['W'] * (0.18 if kind == 'B' else 0.82)
                    x0, x1 = COVER, f['L'] - COVER
                    pts = [(P(x0, y)[0], P(x0, y)[1] + sgn * lgk), P(x0, y), P(x1, y), (P(x1, y)[0], P(x1, y)[1] + sgn * lgk)]
                    sh.pline(pts, lay, 30)
                    sh.text(f"{b['straight'] / 1000:.2f}", P((x0 + x1) / 2, y)[0], P(0, y)[1] + 150, 260, 'S-DIM', align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x0, y)[0] - 150, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x1, y)[0] + 380, P(0, y)[1] + sgn * lgk / 2, 220, 'S-DIM', rot=90, align=TA.BOTTOM_CENTER)
                    # distribution line across Y with the dot at the bar
                    xd = f['L'] * 0.13
                    sh.line(P(xd, 0), P(xd, f['W']), 'S-DIM')
                    sh.circle(*P(xd, y), 90, 'S-DIM')
                    tx, ty = P(f['L'] * 0.10, y + (f['W'] * 0.09 if kind == 'B' else -f['W'] * 0.12))
                else:
                    x = f['L'] * (0.84 if kind == 'B' else 0.16)
                    y0, y1 = COVER, f['W'] - COVER
                    pts = [(P(x, y0)[0] - sgn * lgk, P(x, y0)[1]), P(x, y0), P(x, y1), (P(x, y1)[0] - sgn * lgk, P(x, y1)[1])]
                    sh.pline(pts, lay, 30)
                    sh.text(f"{b['straight'] / 1000:.2f}", P(x, 0)[0] + 200, P(x, (y0 + y1) / 2)[1], 260, 'S-DIM', rot=90, align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y0)[1] - 180, 220, 'S-DIM', align=TA.TOP_CENTER)
                    sh.text(f"{b['leg'] / 1000:.2f}", P(x, 0)[0] - sgn * lgk / 2, P(x, y1)[1] + 180, 220, 'S-DIM', align=TA.BOTTOM_CENTER)
                    yd = f['W'] * 0.10
                    sh.line(P(0, yd), P(f['L'], yd), 'S-DIM')
                    sh.circle(*P(x, yd), 90, 'S-DIM')
                    tx, ty = P(f['L'] * 0.30, f['W'] * (0.45 if kind == 'B' else 0.55))
                sh.text(str(m), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
                sh.text(f"{b['n']}{PHI}{b['d']}  L={b['L'] / 1000:.2f}m  S={b['s'] / 10:.1f}cm  - {b['tag']}", tx, ty, 260, 'S-RFT-TXT')
        else:
            sb = side_bars(f)
            off = 150 / k if k < 4 else 40
            loop = [P(COVER / 2, COVER / 2), P(f['L'] - COVER / 2, COVER / 2), P(f['L'] - COVER / 2, f['W'] - COVER / 2), P(COVER / 2, f['W'] - COVER / 2)]
            sh.pline(loop, 'S-RFT-STIR', 30, True)
            m = mk(dict(d=12, L=sb['L'], tag='SB'))
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.86)
            sh.text(str(m), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
            sh.text(f"{sb['rows']}{PHI}12  L={min(sb['L'], 12000) / 1000:.2f}m  (PER ROW, LAP 60d)  - SB", tx, ty, 260, 'S-RFT-TXT')
            tx, ty = P(f['L'] * 0.12, f['W'] * 0.12)
            m2 = mk(dict(d=16, L=sb['chair_L'], tag='CH'))
            sh.text(str(m2), tx - 120, ty + 60, 180, 'S-AXIS-TXT', align=TA.BOTTOM_RIGHT)
            sh.text(f"{sb['chairs']}{PHI}16  L={sb['chair_L'] / 1000:.2f}m  S=100*100CM  - CHAIRS", tx, ty, 260, 'S-RFT-TXT')
    # section through the footing (1:25)
    sx, sy = 18200, R2 + 1500
    if True:
        L_, h_ = f['L'] * k, f['h'] * k
        pc = 100 * k
        sh.pline([(sx - 100 * k, sy - pc), (sx + L_ + 100 * k, sy - pc), (sx + L_ + 100 * k, sy), (sx - 100 * k, sy)], 'S-GB-CONC', 0, True)
        sh.pline([(sx, sy), (sx + L_, sy), (sx + L_, sy + h_), (sx, sy + h_)], 'S-GB-CONC', 0, True)
        c = COVER * k
        for b in bars:
            if b['along'] != 'X': continue
            if b['layer'] == 'B':
                sh.pline([(sx + c, sy + c + b['leg'] * k), (sx + c, sy + c), (sx + L_ - c, sy + c), (sx + L_ - c, sy + c + b['leg'] * k)], 'S-RFT-BOT', 30)
            else:
                sh.pline([(sx + c, sy + h_ - c - b['leg'] * k), (sx + c, sy + h_ - c), (sx + L_ - c, sy + h_ - c), (sx + L_ - c, sy + h_ - c - b['leg'] * k)], 'S-RFT-TOP', 30)
        sh.text(f"SECTION  ({f['h']} mm, PC 100 mm)", sx + L_ / 2, sy - pc - 500, 260, 'S-SEC', align=TA.TOP_CENTER)
    return marks


if __name__ == '__main__':
    lib = json.load(open('footings.json'))
    names = sys.argv[1:] or list(lib)
    doc = new_doc()
    for i, n in enumerate(names):
        f = lib[n]
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = ['ALL DIMENSIONS IN MM, BAR LENGTHS IN M.', 'CONCRETE COVER FOR FOOTINGS = 70 MM.',
                         'PLAIN CONCRETE 100 MM UNDER FOOTINGS.', 'LAP SPLICE = 60 BAR DIAMETER (SBC).', 'MAX. BAR LENGTH = 12.0 M.']
        meta['title'] = f"STRUCTURAL FOUNDATION\nREINFORCEMENT - {n}  (NO={f['no']})"
        meta['dwg'] = f"{meta['prefix'].replace('GB', 'FDN')}-{n}"
        draw_sheet(doc, i, f, meta)
    doc.saveas('out/FOOTINGS.dxf')
    print('sheets', len(names))
