"""Put the project's own plan into the key-plan cell of a title-block template (project copy of the template).

    python3 tb_keyplan.py template.dxf BLOCK out.dxf source.dxf "LAYER1,LAYER2" x0,y0,x1,y1 cx0,cy0,cx1,cy1 [old_block] ["caption"]

- source.dxf + layers + window x0,y0,x1,y1 (drawing units): the line work copied (blocks expanded, hatches skipped);
- cx0..cy1: the free part of the key-plan cell in BLOCK units (leave the cell title and the north arrow free);
- old_block: the INSERT inside BLOCK that holds the template project's key plan (deleted, with dimension
  polylines inside the cell); the new plan goes on layer S-KEYPLAN, scaled to fit and centred, caption under it.
Find the cell first: list BLOCK entities around the "Key Plan" text (lines of the cell, inserts inside it).
"""
import sys, ezdxf, logging
from ezdxf import recover, bbox, path as P
logging.getLogger('ezdxf').setLevel(logging.ERROR)


def plan_lines(src, layers, win):
    doc, _ = recover.readfile(src)
    x0, y0, x1, y1 = win
    out = []
    def walk(e, d=0):
        if e.dxftype() == 'INSERT' and d < 6:
            try:
                for v in e.virtual_entities(): yield from walk(v, d + 1)
            except Exception: pass
        else: yield e
    for top in doc.modelspace():
        for e in walk(top):
            if e.dxf.layer not in layers: continue
            t = e.dxftype()
            try:
                if t == 'LINE': p = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
                elif t in ('LWPOLYLINE', 'ARC', 'CIRCLE', 'POLYLINE', 'ELLIPSE', 'SPLINE'):
                    p = [(v.x, v.y) for v in P.make_path(e).flattening(0.01 * max(x1 - x0, y1 - y0) / 100)]
                else: continue
            except Exception: continue
            if len(p) > 1 and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in p): out.append(p)
    return out


def main(tpl, block, out, src, layers, win, cell, old=None, caption=''):
    L = plan_lines(src, set(layers.split(',')), [float(v) for v in win.split(',')])
    xs = [x for p in L for x, _ in p]; ys = [y for p in L for _, y in p]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    d = ezdxf.readfile(tpl); b = d.blocks.get(block)
    BX0, BY0, BX1, BY1 = [float(v) for v in cell.split(',')]
    for e in list(b):
        try: bb = bbox.extents([e], fast=True)
        except Exception: continue
        if not bb.has_data: continue
        inside = BX0 - 10 <= bb.extmin.x and bb.extmax.x <= BX1 + 15 and BY0 - 10 <= bb.extmin.y and bb.extmax.y <= BY1 + 10
        if (e.dxftype() == 'INSERT' and old and e.dxf.name == old) or (inside and e.dxftype() == 'LWPOLYLINE' and e.dxf.layer.upper().endswith('DIM')):
            b.delete_entity(e)
    if 'S-KEYPLAN' not in d.layers: d.layers.add('S-KEYPLAN', color=8)
    k = min((BX1 - BX0) / (x1 - x0), (BY1 - BY0) / (y1 - y0))
    ox = BX0 + ((BX1 - BX0) - (x1 - x0) * k) / 2; oy = BY0 + ((BY1 - BY0) - (y1 - y0) * k) / 2
    for p in L:
        b.add_lwpolyline([(ox + (x - x0) * k, oy + (y - y0) * k) for x, y in p], dxfattribs={'layer': 'S-KEYPLAN'})
    if caption:
        b.add_text(caption, height=(BY1 - BY0) / 50, dxfattribs={'layer': 'S-KEYPLAN'}).set_placement((BX0, BY0 - (BY1 - BY0) / 25))
    d.saveas(out)
    print(out, len(L), 'lines, scale', round(k, 4))


if __name__ == '__main__':
    main(*sys.argv[1:])
