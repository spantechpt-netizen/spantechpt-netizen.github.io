"""A consultant drawing flattened for the interactive reader: every line / polyline / arc / circle (blocks and
dimensions expanded, layer '0' inheriting the insert's layer) as a polyline, every TEXT / MTEXT / ATTRIB as a text,
every top-level INSERT with its attributes, every paper layout with its viewport windows.

Built once per DXF (can take a minute on a big plan) and cached next to it in .rcshop_cache/ as numpy arrays.
render() draws a window of it to an RGBA image with matplotlib Agg (no pyplot, thread-safe per call);
pick() finds the entity under a point."""
import hashlib, math, os, pickle, time
from pathlib import Path

import numpy as np

CACHE_VERSION = 4
KINDS = ['LINE', 'POLY', 'ARC', 'CIRCLE', 'CURVE', 'DIM', 'HATCH']


def _sig(path):
    st = os.stat(path)
    return f'{st.st_size}-{int(st.st_mtime)}-{CACHE_VERSION}'


class DrawingModel:
    def __init__(self, path, log=print):
        self.path = Path(path)
        cache = self.path.parent / '.rcshop_cache' / (self.path.name + '.pkl')
        sig = _sig(self.path)
        if cache.exists():
            try:
                d = pickle.load(open(cache, 'rb'))
                if d.get('sig') == sig:
                    self.__dict__.update(d['data']); self._index(); log(f'{self.path.name}: from cache'); return
            except Exception:
                pass
        t0 = time.time()
        self._build(log)
        cache.parent.mkdir(exist_ok=True)
        data = {k: v for k, v in self.__dict__.items() if k not in ('path',) and not k.startswith('_')}
        pickle.dump(dict(sig=sig, data=data), open(cache, 'wb'), protocol=4)
        self._index()
        log(f'{self.path.name}: {len(self.p_layer)} lines, {len(self.t_text)} texts, {len(self.ins)} blocks in {time.time() - t0:.0f} s')

    # ------------------------------------------------------------------ flatten
    def _build(self, log):
        import logging
        logging.getLogger('ezdxf').setLevel(logging.ERROR)
        from ezdxf import recover, path as zpath
        log(f'reading {self.path.name} ...')
        doc, _ = recover.readfile(str(self.path))
        msp = doc.modelspace()
        layers, blocks = {}, {'': 0}
        lid = lambda n: layers.setdefault(n, len(layers))
        bid = lambda n: blocks.setdefault(n, len(blocks))
        pts, off, p_layer, p_kind, p_block, p_ins = [], [0], [], [], [], []
        t_xy, t_h, t_rot, t_text, t_layer, t_block, t_ins = [], [], [], [], [], [], []
        ins = []                                          # (block, x, y, layer, {tag: value})

        def add_poly(xy, layer, kind, blk, ii):
            if len(xy) < 2: return
            pts.extend(xy); off.append(len(pts))
            p_layer.append(lid(layer)); p_kind.append(KINDS.index(kind)); p_block.append(bid(blk)); p_ins.append(ii)

        def add_text(x, y, h, rot, s, layer, blk, ii):
            s = (s or '').strip()
            if not s: return
            t_xy.append((x, y)); t_h.append(h or 1); t_rot.append(rot or 0); t_text.append(s[:200])
            t_layer.append(lid(layer)); t_block.append(bid(blk)); t_ins.append(ii)

        n = [0]
        def walk(e, depth, inh, blk, ii, dim=False):
            n[0] += 1
            if n[0] % 50000 == 0: log(f'  {n[0]} entities ...')
            t = e.dxftype()
            layer = e.dxf.get('layer', '0')
            if layer == '0' and inh: layer = inh
            try:
                if t == 'LINE':
                    s, f = e.dxf.start, e.dxf.end
                    add_poly([(s.x, s.y), (f.x, f.y)], layer, 'DIM' if dim else 'LINE', blk, ii)
                elif t in ('LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE'):
                    if t == 'POLYLINE' and (e.is_poly_face_mesh or e.is_polygon_mesh):
                        return
                    p = zpath.make_path(e)
                    xy = [(v.x, v.y) for v in p.flattening(distance=max(1.0, _size(e) / 400))]
                    if t == 'CIRCLE' and xy: xy.append(xy[0])
                    kind = {'LWPOLYLINE': 'POLY', 'POLYLINE': 'POLY', 'ARC': 'ARC', 'CIRCLE': 'CIRCLE'}.get(t, 'CURVE')
                    add_poly(xy, layer, 'DIM' if dim else kind, blk, ii)
                elif t == 'TEXT' or t == 'ATTRIB':
                    a = e.dxf.insert
                    add_text(a.x, a.y, e.dxf.get('height', 1), e.dxf.get('rotation', 0), e.plain_text(), layer, blk, ii)
                elif t == 'MTEXT':
                    a = e.dxf.insert
                    add_text(a.x, a.y, e.dxf.get('char_height', 1), e.dxf.get('rotation', 0), e.plain_text(), layer, blk, ii)
                elif t == 'DIMENSION' and depth < 4:
                    for v in e.virtual_entities():
                        walk(v, depth + 1, layer, blk, ii, True)
                elif t == 'INSERT' and depth < 4:
                    if depth == 0:
                        att = {a.dxf.tag: a.dxf.text for a in e.attribs}
                        ins.append((e.dxf.name, e.dxf.insert.x, e.dxf.insert.y, layer, att))
                        ii = len(ins) - 1; blk = e.dxf.name
                        for a in e.attribs:
                            walk(a, depth + 1, layer, blk, ii)
                    for v in e.virtual_entities():
                        walk(v, depth + 1, layer, blk, ii, dim)
            except Exception:
                pass

        for e in msp:
            walk(e, 0, None, '', -1)
        self.layers = [k for k, _ in sorted(layers.items(), key=lambda kv: kv[1])]
        self.blocks = [k for k, _ in sorted(blocks.items(), key=lambda kv: kv[1])]
        self.pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        self.off = np.asarray(off, dtype=np.int64)
        self.p_layer = np.asarray(p_layer, dtype=np.int32); self.p_kind = np.asarray(p_kind, dtype=np.int8)
        self.p_block = np.asarray(p_block, dtype=np.int32); self.p_ins = np.asarray(p_ins, dtype=np.int32)
        self.t_xy = np.asarray(t_xy, dtype=np.float64).reshape(-1, 2); self.t_h = np.asarray(t_h)
        self.t_rot = np.asarray(t_rot); self.t_text = t_text
        self.t_layer = np.asarray(t_layer, dtype=np.int32); self.t_block = np.asarray(t_block, dtype=np.int32)
        self.t_ins = np.asarray(t_ins, dtype=np.int32)
        self.ins = ins
        self.layouts = {}
        for lay in doc.layouts:
            if lay.name == 'Model': continue
            wins = []
            for v in lay.query('VIEWPORT'):
                try:
                    c, hh = v.dxf.view_center_point, v.dxf.view_height
                    if hh <= 0 or v.dxf.get('id', 2) == 1: continue
                    ww = hh * v.dxf.width / max(v.dxf.height, 1e-9)
                    wins.append((c.x - ww / 2, c.y - hh / 2, c.x + ww / 2, c.y + hh / 2))
                except Exception:
                    pass
            self.layouts[lay.name] = wins

    # ------------------------------------------------------------------ index
    def _index(self):
        o = self.off
        n = len(o) - 1
        if n > 0:
            idx = np.repeat(np.arange(n), np.diff(o))
            self.bx0 = np.full(n, np.inf); self.by0 = np.full(n, np.inf)
            self.bx1 = np.full(n, -np.inf); self.by1 = np.full(n, -np.inf)
            np.minimum.at(self.bx0, idx, self.pts[:, 0]); np.minimum.at(self.by0, idx, self.pts[:, 1])
            np.maximum.at(self.bx1, idx, self.pts[:, 0]); np.maximum.at(self.by1, idx, self.pts[:, 1])
        else:
            self.bx0 = self.by0 = self.bx1 = self.by1 = np.zeros(0)
        self.layer_count = np.bincount(self.p_layer, minlength=len(self.layers)) + \
            np.bincount(self.t_layer, minlength=len(self.layers)) if len(self.layers) else np.zeros(0, int)
        self.t_upper = [s.upper() for s in self.t_text]

    def extents(self):
        """robust extents: the dense part of the drawing (2-98 % of the vertices), not a stray far entity"""
        if not len(self.pts):
            return (0, 0, 1000, 1000)
        x0, x1 = np.percentile(self.pts[:, 0], [1, 99]); y0, y1 = np.percentile(self.pts[:, 1], [1, 99])
        dx, dy = (x1 - x0) * 0.05 + 1, (y1 - y0) * 0.05 + 1
        return (x0 - dx, y0 - dy, x1 + dx, y1 + dy)

    def poly(self, i):
        return self.pts[self.off[i]:self.off[i + 1]]

    # ------------------------------------------------------------------ query
    def visible(self, win, min_size=0.0):
        x0, y0, x1, y1 = win
        m = (self.bx1 >= x0) & (self.bx0 <= x1) & (self.by1 >= y0) & (self.by0 <= y1)
        if min_size > 0:
            m &= ((self.bx1 - self.bx0) + (self.by1 - self.by0)) >= min_size
        return np.nonzero(m)[0]

    def visible_texts(self, win):
        if not len(self.t_xy): return np.zeros(0, int)
        x0, y0, x1, y1 = win
        x, y = self.t_xy[:, 0], self.t_xy[:, 1]
        return np.nonzero((x >= x0) & (x <= x1) & (y >= y0) & (y <= y1))[0]

    def pick(self, x, y, tol):
        """nearest entity to (x, y) within tol -> ('text', i) / ('poly', i) / None"""
        best, bd = None, tol
        ti = self.visible_texts((x - tol * 6, y - tol * 6, x + tol * 6, y + tol * 6))
        for i in ti:
            tx, ty = self.t_xy[i]; h = self.t_h[i]
            w = len(self.t_text[i]) * h * 0.8
            r = math.radians(self.t_rot[i]); ux, uy = math.cos(r), math.sin(r)
            u = (x - tx) * ux + (y - ty) * uy; v = -(x - tx) * uy + (y - ty) * ux
            if -tol <= u <= w + tol and -tol - h * 0.2 <= v <= h * 1.2 + tol:
                d = 0 if (0 <= u <= w and 0 <= v <= h) else tol * 0.5
                if d < bd or best is None:
                    best, bd = ('text', int(i)), d
        if best:
            return best
        cand = self.visible((x - tol, y - tol, x + tol, y + tol))
        for i in cand:
            p = self.poly(i)
            a, b = p[:-1], p[1:]
            ab = b - a; L2 = (ab ** 2).sum(1); L2[L2 == 0] = 1e-12
            t = np.clip(((x - a[:, 0]) * ab[:, 0] + (y - a[:, 1]) * ab[:, 1]) / L2, 0, 1)
            d = np.hypot(a[:, 0] + t * ab[:, 0] - x, a[:, 1] + t * ab[:, 1] - y).min()
            if d < bd:
                best, bd = ('poly', int(i)), d
        return best

    def describe(self, hit):
        if not hit: return {}
        kind, i = hit
        if kind == 'text':
            d = dict(type='TEXT', layer=self.layers[self.t_layer[i]], text=self.t_text[i], height=round(float(self.t_h[i]), 1),
                     x=round(float(self.t_xy[i][0])), y=round(float(self.t_xy[i][1])), block=self.blocks[self.t_block[i]], ins=int(self.t_ins[i]))
        else:
            p = self.poly(i)
            L = float(np.hypot(*np.diff(p, axis=0).T).sum())
            closed = bool(np.allclose(p[0], p[-1]))
            d = dict(type=KINDS[self.p_kind[i]], layer=self.layers[self.p_layer[i]], block=self.blocks[self.p_block[i]],
                     ins=int(self.p_ins[i]), length=round(L), vertices=len(p), closed=closed,
                     size=f'{self.bx1[i] - self.bx0[i]:.0f} x {self.by1[i] - self.by0[i]:.0f}')
        if d['ins'] >= 0:
            b, bx, by, bl, att = self.ins[d['ins']]
            d['insert'] = dict(block=b, x=round(bx), y=round(by), layer=bl, attribs=att)
        return d


def _size(e):
    try:
        if e.dxftype() in ('CIRCLE', 'ARC'):
            return 2 * e.dxf.radius
        from ezdxf import bbox
        b = bbox.extents([e], fast=True)
        return max(b.size.x, b.size.y) if b.has_data else 100
    except Exception:
        return 100


# ---------------------------------------------------------------------------- rendering
BG = '#0f1620'


def layer_color(name):
    """stable, readable colour per layer on the dark background"""
    h = int(hashlib.md5(name.encode('utf-8', 'replace')).hexdigest()[:6], 16)
    import colorsys
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360, 0.62, 0.45)
    return (r, g, b, 0.85)


def render(model, win, size, hidden=frozenset(), highlights=(), selected=None, rect=None, dim=False):
    """-> (RGBA bytes, (w, h)). win = model window (x0, y0, x1, y1) already at the widget's aspect.
    highlights = [(poly index array, text index array, colour, line width)], drawn over the drawing;
    dim = grey the drawing so highlights stand out."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.collections import LineCollection
    w, h = max(size[0], 10), max(size[1], 10)
    fig = Figure(figsize=(w / 100, h / 100), dpi=100, facecolor=BG)
    FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_facecolor(BG); ax.axis('off')
    ax.set_xlim(win[0], win[2]); ax.set_ylim(win[1], win[3])
    px = (win[2] - win[0]) / w                                 # model units per pixel
    vis = model.visible(win, min_size=px * 0.8)
    if len(hidden):
        hid = np.isin(model.p_layer[vis], np.fromiter(hidden, int))
        vis = vis[~hid]
    if len(vis):
        segs = [model.poly(i) for i in vis]
        if dim:
            cols = [(0.45, 0.5, 0.56, 0.35)] * len(vis)
        else:
            lc = {}
            cols = [lc.setdefault(l, layer_color(model.layers[l])) for l in model.p_layer[vis]]
        ax.add_collection(LineCollection(segs, colors=cols, linewidths=0.6, antialiased=True))
    ti = model.visible_texts(win)
    if len(hidden) and len(ti):
        ti = ti[~np.isin(model.t_layer[ti], np.fromiter(hidden, int))]
    hpx = model.t_h[ti] / px if len(ti) else np.zeros(0)
    ti = ti[hpx >= 4] if len(ti) else ti
    if 0 < len(ti) <= 1500:
        for i in ti:
            fs = min(max(model.t_h[i] / px * 0.72, 4), 40)
            ax.text(model.t_xy[i][0], model.t_xy[i][1], model.t_text[i][:60], fontsize=fs, rotation=model.t_rot[i],
                    color=(0.55, 0.6, 0.66) if dim else layer_color(model.layers[model.t_layer[i]]),
                    ha='left', va='bottom', rotation_mode='anchor', clip_on=True)
    for pis, tis, col, lw in highlights:
        pis = np.asarray(pis, int); tis = np.asarray(tis, int)
        if len(pis):
            m = (model.bx1[pis] >= win[0]) & (model.bx0[pis] <= win[2]) & (model.by1[pis] >= win[1]) & (model.by0[pis] <= win[3])
            sel = pis[m]
            if len(sel):
                ax.add_collection(LineCollection([model.poly(i) for i in sel[:60000]], colors=col, linewidths=lw))
        if len(tis):
            xy = model.t_xy[tis]
            m = (xy[:, 0] >= win[0]) & (xy[:, 0] <= win[2]) & (xy[:, 1] >= win[1]) & (xy[:, 1] <= win[3])
            sel = tis[m]
            if len(sel) > 400 or (len(sel) and (model.t_h[sel] / px).max() < 4):
                ax.scatter(model.t_xy[sel, 0], model.t_xy[sel, 1], s=14, c=col, marker='s', linewidths=0)
            else:
                for i in sel:
                    fs = min(max(model.t_h[i] / px * 0.72, 6), 40)
                    ax.text(model.t_xy[i][0], model.t_xy[i][1], model.t_text[i][:60], fontsize=fs, rotation=model.t_rot[i],
                            color=col, ha='left', va='bottom', rotation_mode='anchor', fontweight='bold', clip_on=True,
                            bbox=dict(boxstyle='square,pad=0.15', fc=(0, 0, 0, 0.55), ec=col, lw=0.8))
    if selected:
        kind, i = selected
        if kind == 'poly':
            p = model.poly(i); ax.plot(p[:, 0], p[:, 1], color='#ffffff', lw=2.6, solid_capstyle='round')
        else:
            ax.plot([model.t_xy[i][0]], [model.t_xy[i][1]], marker='o', ms=9, mfc='none', mec='#ffffff', mew=2)
    if rect:
        x0, y0, x1, y1 = rect
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color='#ffd166', lw=1.6, ls='--')
    fig.canvas.draw()
    buf = fig.canvas.buffer_rgba()
    return bytes(buf), (w, h)
