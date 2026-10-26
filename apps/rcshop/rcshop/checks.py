"""Every output DXF before it leaves the office: ezdxf audit, objects AutoCAD rejects in files that came through a
converter (ATTRIB without block, OLE frames, embedded objects), anything drawn outside its sheet frame, sheet count
(A3 frames) and BBS weight lines."""
import ezdxf
from ezdxf import bbox

BAD = ('ATTRIB', 'OLE2FRAME', 'OLEFRAME', 'EMBEDDED_OBJECT')


def check_file(path):
    doc = ezdxf.readfile(str(path))
    aud = doc.audit()
    msp = doc.modelspace()
    bad = {t: len(msp.query(t)) for t in BAD}
    bad = {k: v for k, v in bad.items() if v}
    frames = sum(1 for e in msp.query('INSERT') if e.dxf.layer == 'S-FRAME') or \
        sum(1 for e in msp.query('LWPOLYLINE') if e.dxf.layer == 'S-FRAME' and e.closed) // 2
    weight = [e.dxf.text for e in msp.query('TEXT') if e.dxf.text.startswith('TOTAL STEEL WEIGHT')]
    return dict(errors=len(aud.errors), fixes=len(aud.fixes), bad=bad, sheets=frames, weight=weight[-1] if weight else '',
                outside=outside_frames(msp))


def outside_frames(msp, tol=20):
    """Entities whose centre is on a sheet (title-block insert on S-FRAME) but which leave that sheet."""
    fr = []
    for e in msp.query('INSERT'):
        if e.dxf.layer == 'S-FRAME':
            b = bbox.extents([e], fast=True)
            if b.has_data: fr.append((b.extmin.x, b.extmin.y, b.extmax.x, b.extmax.y))
    if not fr: return 0
    n = 0
    for e in msp:
        if e.dxf.layer == 'S-FRAME': continue
        b = bbox.extents([e], fast=True)
        if not b.has_data: continue
        cx, cy = (b.extmin.x + b.extmax.x) / 2, (b.extmin.y + b.extmax.y) / 2
        r = next((r for r in fr if r[0] <= cx <= r[2] and r[1] <= cy <= r[3]), None)
        if r and max(r[0] - b.extmin.x, r[1] - b.extmin.y, b.extmax.x - r[2], b.extmax.y - r[3]) > tol: n += 1
    return n


def run(ws, log=print):
    files = ws.outputs()
    if not files:
        log('no DXF in work/out'); return 1
    rows, fail = [], 0
    for f in files:
        try:
            r = check_file(f)
        except Exception as e:
            r = dict(errors=1, fixes=0, bad={'READ': str(e)}, sheets=0, weight='')
        ok = r['errors'] == 0 and not r['bad'] and not r.get('outside')
        fail += not ok
        rel = f.relative_to(ws.work / 'out')
        line = f"{'OK  ' if ok else 'FAIL'} {rel}  sheets {r['sheets']}  audit errors {r['errors']}" + \
               (f"  unsafe {r['bad']}" if r['bad'] else '') + (f"  OUTSIDE THE FRAME {r['outside']}" if r.get('outside') else '') + \
               (f"  {r['weight']}" if r['weight'] else '')
        rows.append(line); log(line)
    rep = ws.logs / 'check.txt'
    rep.write_text('\n'.join(rows) + f'\n{len(files)} files, {fail} failed\n', encoding='utf-8')
    log(f'{len(files)} files checked, {fail} failed -> logs/check.txt')
    return 1 if fail else 0
