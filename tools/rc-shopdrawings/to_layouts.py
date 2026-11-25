"""Title block (banda) in the LAYOUT only (engineer, Oct-Nov 2026). Every model sheet of gen_f / gen_n -> one paper layout (A1 841x594,
ST_FRAME as in FOUNDATION layout 100) with the title values in paper space and one viewport on the sheet's drawing;
the frame block and the title texts are removed from the model. usage: to_layouts.py in.dxf out.dxf"""
import sys, json, os, ezdxf, re
src, dst = sys.argv[1:3]
P = json.load(open(os.environ.get('RC_PROJECT', 'project.json'))); TB = P['title_block']
x0, y0, x1, y1 = TB['paper']; k = 42000 / (x1 - x0)
LY = TB.get('layout', {}); INS = tuple(LY.get('insert', (13.3646, 4.4647))); SC = LY.get('scale', 0.70731707)   # frame insert / scale as in the consultant's layout
PAPER = tuple(LY.get('size', (841, 594)))
s_ = SC / k                                                    # model sheet unit -> paper mm
px0, py0 = INS[0] + x0 * SC, INS[1] + y0 * SC                  # paper position of the sheet origin
d = ezdxf.readfile(src); m = d.modelspace()
if 'S-VPORT' not in d.layers: d.layers.add('S-VPORT', color=8).dxf.plot = 0
frames = sorted([e for e in m.query('INSERT') if e.dxf.name == TB['block']], key=lambda e: -e.dxf.insert.y)
for i, fr in enumerate(frames):
    ox, oy = fr.dxf.insert.x + x0 * k, fr.dxf.insert.y + y0 * k
    inside = lambda p: ox - 10 <= p.x <= ox + 42010 and oy - 10 <= p.y <= oy + 29710
    titles = [t for t in m.query('TEXT') if t.dxf.layer == 'S-TITLE' and inside(t.dxf.insert)]
    seq = next((t.dxf.text for t in titles if re.fullmatch(r'\d{3,6}', t.dxf.text.strip())), str(i + 1))
    tt = [t.dxf.text.strip() for t in titles]
    el = ('BBS' if any('BAR BENDING' in x for x in tt) else None) or next((x.split(' - ', 1)[1].split('(')[0].strip() for x in tt if 'REINFORCEMENT - ' in x), None) or \
         next((x.split()[0] for x in tt if re.match(r'^C[\d*]+\s', x)), None) or next((x.split(' - ', 1)[1].split(' ON ')[0].strip() for x in tt if x.startswith('CORE NECKS - ')), None) or ('BBS' if any('BAR BENDING' in x for x in tt) else '')
    name = re.sub(r"[^A-Za-z0-9 _.*-]", "-", f"{seq} {el}".strip()).replace('*', 'S')
    while name in d.layouts: name += '_'
    L = d.layouts.new(name)
    L.page_setup(size=PAPER, margins=(0, 0, 0, 0), units='mm')
    L.add_blockref(TB['block'], INS, dxfattribs={'xscale': SC, 'yscale': SC, 'layer': 'S-FRAME'})
    P_ = lambda x, y: (px0 + (x - ox) * s_, py0 + (y - oy) * s_)
    for t in titles:
        c = t.copy()
        c.dxf.insert = P_(t.dxf.insert.x, t.dxf.insert.y)
        if t.dxf.hasattr('align_point'): c.dxf.align_point = P_(t.dxf.align_point.x, t.dxf.align_point.y)
        c.dxf.height = t.dxf.height * s_
        L.add_entity(c); m.delete_entity(t)
    w, h = 42000 * s_, 29700 * s_
    v = L.add_viewport(center=(px0 + w / 2, py0 + h / 2), size=(w, h), view_center_point=(ox + 21000, oy + 14850), view_height=29700)
    v.dxf.status = 2; v.dxf.layer = 'S-VPORT'
    m.delete_entity(fr)
for n in [l.name for l in d.layouts if l.name not in ('Model',) and len(l) == 0]:
    try: d.layouts.delete(n)
    except Exception: pass
a = d.audit(); d.saveas(dst); print('layouts', len(frames), 'audit', len(a.errors))
