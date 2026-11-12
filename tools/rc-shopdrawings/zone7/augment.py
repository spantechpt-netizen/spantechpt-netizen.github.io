"""consultant DXF + the beams the engineer added on the issued part files (AREA 7 update, 07-11-2026) -> consultant_A7.dxf
Only entities on the beam / label / level / dimension layers near the new beams, absent from the consultant drawing
(block texts included), plus the consultant beam-edge lines the engineer extended to meet the new beams."""
import sys, logging, ezdxf
from ezdxf.disassemble import recursive_decompose
logging.getLogger('ezdxf').setLevel(logging.ERROR)
cons_f, out, *parts = sys.argv[1:]          # parts: file:x0,y0,x1,y1;x0,y0,x1,y1 (new-beam boxes, consultant coords)
C = ezdxf.readfile(cons_f); M = C.modelspace()
LAY = {'CORE-FNDN-GRBM', '$0$CORE-COLS-IDEN', 'A-TEXT', 'A-DIM'}
r = lambda v: round(v / 10) * 10
def key(e):
    t = e.dxftype()
    if t == 'LINE': return (t, e.dxf.layer, tuple(sorted([(r(e.dxf.start.x), r(e.dxf.start.y)), (r(e.dxf.end.x), r(e.dxf.end.y))])))
    if t in ('TEXT', 'MTEXT'):
        s = (e.dxf.text if t == 'TEXT' else e.plain_text()).strip(); return (t if t == 'TEXT' else 'TEXT', s, round(e.dxf.insert.x / 100), round(e.dxf.insert.y / 100))
    return None
have = set()
for e in recursive_decompose(M):
    try:
        k = key(e)
        if k: have.add(k)
        if e.dxftype() == 'MTEXT': have.add(('TEXT', e.plain_text().strip(), round(e.dxf.insert.x / 100), round(e.dxf.insert.y / 100)))
    except Exception: pass
lines = {e.dxf.handle: e for e in M.query('LINE[layer=="CORE-FNDN-GRBM"]')}
added, fixed = 0, 0
for spec in parts:
    f, bx = spec.split(':'); boxes = [tuple(map(float, b.split(','))) for b in bx.split(';')]
    P = ezdxf.readfile(f); PM = P.modelspace()
    lonly = [b for b in boxes if len(b) == 5]; boxes = [b for b in boxes if len(b) == 4]   # 5th value: lines only (extensions)
    near = lambda x, y, pad, bx=None: any(b[0] - pad <= x <= b[2] + pad and b[1] - pad <= y <= b[3] + pad for b in (bx or boxes))
    for e in PM:
        t = e.dxftype()
        if e.dxf.layer not in LAY or t not in ('LINE', 'TEXT', 'MTEXT'): continue
        if t == 'LINE':
            s_, q_ = e.dxf.start, e.dxf.end; pts = [(s_.x, s_.y), (q_.x, q_.y), ((s_.x + q_.x) / 2, (s_.y + q_.y) / 2)]
            ok = any(near(x, y, 60) for x, y in pts) or (e.dxf.layer == 'CORE-FNDN-GRBM' and lonly and any(near(x, y, 60, lonly) for x, y in pts))
            if e.dxf.layer == 'A-DIM': ok = any(near(x, y, 600) for x, y in pts)
            if not ok: continue
            p = s_
        else:
            p = e.dxf.insert; s0 = (e.dxf.text if t == 'TEXT' else e.plain_text()).strip()
            if e.dxf.layer == '$0$CORE-COLS-IDEN' and not s0.startswith(('GB', 'TB')): continue    # column labels are the consultant's
            if not near(p.x, p.y, 600): continue
        k = key(e)
        if k in have: continue
        if t == 'LINE' and e.dxf.layer == 'CORE-FNDN-GRBM':        # an extended consultant edge: replace the old one
            s, q = e.dxf.start, e.dxf.end
            for h, c in list(lines.items()):
                cs, cq = c.dxf.start, c.dxf.end
                same_y = abs(cs.y - s.y) < 3 and abs(cq.y - q.y) < 3 and abs(s.y - q.y) < 3
                same_x = abs(cs.x - s.x) < 3 and abs(cq.x - q.x) < 3 and abs(s.x - q.x) < 3
                if (same_y and min(cs.x, cq.x) - 3 <= max(s.x, q.x) and min(s.x, q.x) <= max(cs.x, cq.x) + 3) or \
                   (same_x and min(cs.y, cq.y) - 3 <= max(s.y, q.y) and min(s.y, q.y) <= max(cs.y, cq.y) + 3):
                    if abs((cq - cs).magnitude - (q - s).magnitude) < 120:
                        print('  extend', [round(v) for v in (cs.x, cs.y, cq.x, cq.y)], '->', [round(v) for v in (s.x, s.y, q.x, q.y)])
                        M.delete_entity(c); del lines[h]; fixed += 1
                        break
        att = {'layer': e.dxf.layer, 'color': e.dxf.get('color', 256)}
        if t == 'LINE':
            M.add_line(e.dxf.start, e.dxf.end, dxfattribs=dict(att, linetype=e.dxf.get('linetype', 'BYLAYER')))
        elif t == 'TEXT':
            st = e.dxf.get('style', 'Standard'); st = st if st in C.styles else 'Standard'
            n = M.add_text(e.dxf.text, height=e.dxf.height, rotation=e.dxf.get('rotation', 0), dxfattribs=dict(att, style=st))
            n.dxf.insert = e.dxf.insert
            for a in ('halign', 'valign', 'width'):
                if e.dxf.hasattr(a): n.dxf.set(a, e.dxf.get(a))
            if e.dxf.hasattr('align_point'): n.dxf.align_point = e.dxf.align_point
        else:
            st = e.dxf.get('style', 'Standard'); st = st if st in C.styles else 'Standard'
            n = M.add_mtext(e.text, dxfattribs=dict(att, style=st, char_height=e.dxf.char_height, insert=e.dxf.insert,
                                                    attachment_point=e.dxf.get('attachment_point', 1), rotation=e.dxf.get('rotation', 0)))
        have.add(k); added += 1
        print('  +', t, e.dxf.layer, (e.dxf.text if t == 'TEXT' else (e.plain_text() if t == 'MTEXT' else '')), [round(p.x), round(p.y)])
print('added', added, 'extended', fixed)
C.saveas(out)
