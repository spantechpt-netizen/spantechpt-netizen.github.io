"""consultant DXF -> geo.pkl (layer, type, WCS points, color) + texts.pkl (text, x, y, layer, height, block path)"""
import pickle, logging, sys, ezdxf
logging.getLogger('ezdxf').setLevel(logging.ERROR)
doc = ezdxf.readfile(sys.argv[1]); msp = doc.modelspace(); out = sys.argv[2]
G, T = [], []
def walk(ents, path='', lay_parent=None, depth=0):
    for e in ents:
        t = e.dxftype(); lay = e.dxf.layer if not (e.dxf.layer == '0' and lay_parent) else lay_parent
        col = e.dxf.get('color', 256)
        try:
            if t == 'LINE': G.append((lay, t, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], col))
            elif t == 'LWPOLYLINE':
                pts = [(p.x, p.y) for p in e.vertices_in_wcs()]
                if e.closed and pts: pts.append(pts[0])
                G.append((lay, t, pts, col))
            elif t == 'TEXT': q = e.ocs().to_wcs(e.dxf.insert); T.append((e.dxf.text, q.x, q.y, lay, e.dxf.height, path))
            elif t == 'MTEXT': T.append((e.plain_text(), e.dxf.insert.x, e.dxf.insert.y, lay, e.dxf.char_height, path))
            elif t == 'INSERT' and depth < 6:
                for ins in (e.multi_insert() if e.mcount > 1 else [e]):
                    walk(ins.virtual_entities(), path + '/' + e.dxf.name, lay, depth + 1)
                for a in e.attribs: T.append((a.dxf.text, a.dxf.insert.x, a.dxf.insert.y, lay, a.dxf.height, path + '/' + e.dxf.name + '@'))
        except Exception as ex: print('ERR', t, path, ex)
walk(msp)
pickle.dump(G, open(out + '/geo.pkl', 'wb')); pickle.dump(T, open(out + '/texts.pkl', 'wb')); print(len(G), len(T))
