"""The drawing canvas: wheel zoom at the cursor, pan with the middle / right button (or Space + drag), click to pick,
drag a rectangle (window role / zoom window). Rendering runs in a worker thread; while it runs the last image is
scaled to the new view at once, so zoom and pan never feel stuck even on a 70 MB plan."""
import base64, io, threading, time
import tkinter as tk

from PIL import Image

from .drawing import BG, render

try:
    from PIL import ImageTk
except Exception:                                             # Pillow without Tk support
    ImageTk = None


def _photo(img):
    if ImageTk is not None:
        try:
            return ImageTk.PhotoImage(img)
        except Exception:
            pass
    b = io.BytesIO(); img.save(b, 'PNG')
    return tk.PhotoImage(data=base64.b64encode(b.getvalue()))


class DrawingView(tk.Frame):
    def __init__(self, master, on_pick=None, on_hover=None, on_rect=None, on_status=None):
        super().__init__(master, bg=BG)
        self.cv = tk.Canvas(self, bg=BG, highlightthickness=0, cursor='crosshair')
        self.cv.pack(fill='both', expand=True)
        self.on_pick, self.on_hover, self.on_rect, self.on_status = on_pick, on_hover, on_rect, on_status
        self.model, self.win = None, None
        self.hidden, self.highlights, self.selected, self.rect, self.dim = frozenset(), [], None, None, False
        self.mode = 'pick'                                    # pick / rect / zoomwin
        self._img = self._photo = None; self._img_win = None
        self._gen = 0; self._pending = None; self._busy = False
        self._drag = None; self._band = None; self._hover_t = 0
        c = self.cv
        c.bind('<Configure>', lambda e: self.redraw(fast=False))
        c.bind('<MouseWheel>', self._wheel)
        c.bind('<Button-4>', lambda e: self._zoom_at(e.x, e.y, 1 / 1.25))
        c.bind('<Button-5>', lambda e: self._zoom_at(e.x, e.y, 1.25))
        for b in ('<ButtonPress-2>', '<ButtonPress-3>'):
            c.bind(b, self._pan_start)
        for b in ('<B2-Motion>', '<B3-Motion>'):
            c.bind(b, self._pan_move)
        for b in ('<ButtonRelease-2>', '<ButtonRelease-3>'):
            c.bind(b, self._pan_end)
        c.bind('<ButtonPress-1>', self._left_down)
        c.bind('<B1-Motion>', self._left_move)
        c.bind('<ButtonRelease-1>', self._left_up)
        c.bind('<Motion>', self._motion)
        c.bind('<Double-Button-2>', lambda e: self.fit())

    # ------------------------------------------------------------------ public
    def set_model(self, model, win=None):
        self.model = model; self.selected = None
        self.win = None
        self.after_idle(lambda: self.fit(win))

    def fit(self, win=None):
        if not self.model: return
        x0, y0, x1, y1 = win or self.model.extents()
        self.win = self._aspect((x0, y0, x1, y1)); self.redraw()

    def zoom_to(self, x, y, size):
        self.win = self._aspect((x - size, y - size, x + size, y + size)); self.redraw()

    def set_overlays(self, highlights=None, selected=None, rect=None, dim=None, hidden=None):
        if highlights is not None: self.highlights = highlights
        self.selected = selected
        self.rect = rect
        if dim is not None: self.dim = dim
        if hidden is not None: self.hidden = frozenset(hidden)
        self.redraw(fast=False)

    def set_mode(self, mode):
        self.mode = mode
        self.cv.config(cursor={'pick': 'crosshair', 'rect': 'tcross', 'zoomwin': 'sizing'}.get(mode, 'crosshair'))

    # ------------------------------------------------------------------ geometry
    def _size(self):
        return max(self.cv.winfo_width(), 50), max(self.cv.winfo_height(), 50)

    def _aspect(self, win):
        w, h = self._size()
        x0, y0, x1, y1 = win
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sx, sy = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
        if sx / sy > w / h: sy = sx * h / w
        else: sx = sy * w / h
        return (cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2)

    def to_model(self, px, py):
        w, h = self._size(); x0, y0, x1, y1 = self.win
        return x0 + px / w * (x1 - x0), y1 - py / h * (y1 - y0)

    def to_px(self, x, y):
        w, h = self._size(); x0, y0, x1, y1 = self.win
        return (x - x0) / (x1 - x0) * w, (y1 - y) / (y1 - y0) * h

    def units_per_px(self):
        return (self.win[2] - self.win[0]) / self._size()[0] if self.win else 1

    # ------------------------------------------------------------------ rendering
    def redraw(self, fast=True):
        if not self.model or not self.win: return
        self.win = self._aspect(self.win)
        if fast: self._preview()
        if self._pending: self.after_cancel(self._pending)
        self._pending = self.after(40 if fast else 1, self._start_render)

    def _preview(self):
        """the last image moved / scaled to the new window (instant), until the real render arrives"""
        if self._img is None or self._img_win is None: return
        w, h = self._size(); ox0, oy0, ox1, oy1 = self._img_win; iw, ih = self._img.size
        x0, y0, x1, y1 = self.win
        l = (x0 - ox0) / (ox1 - ox0) * iw; r = (x1 - ox0) / (ox1 - ox0) * iw
        t = (oy1 - y1) / (oy1 - oy0) * ih; b = (oy1 - y0) / (oy1 - oy0) * ih
        try:
            im = self._img.transform((w, h), Image.EXTENT, (l, t, r, b), Image.BILINEAR, fillcolor=BG)
        except TypeError:
            im = self._img.transform((w, h), Image.EXTENT, (l, t, r, b), Image.BILINEAR)
        self._show(im)

    def _start_render(self):
        self._pending = None
        self._gen += 1; gen = self._gen
        args = (self.model, self.win, self._size(), self.hidden, list(self.highlights), self.selected, self.rect, self.dim)
        def work():
            t0 = time.time()
            try:
                buf, (w, h) = render(*args)
                im = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'RGBA', 0, 1).convert('RGB')
            except Exception as e:
                im = None; err = str(e)
            dt = time.time() - t0
            def done():
                if gen != self._gen: return                  # a newer view was asked meanwhile
                if im is None:
                    self.on_status and self.on_status(f'render error: {err}'); return
                self._img, self._img_win = im, args[1]
                self._show(im)
                self.on_status and self.on_status(f'render {dt * 1000:.0f} ms')
            try:
                self.after(0, done)
            except RuntimeError:
                pass
        threading.Thread(target=work, daemon=True).start()

    def _show(self, im):
        self._photo = _photo(im)
        self.cv.delete('img')
        self.cv.create_image(0, 0, image=self._photo, anchor='nw', tags='img')
        self.cv.tag_lower('img')

    # ------------------------------------------------------------------ mouse
    def _wheel(self, e):
        self._zoom_at(e.x, e.y, 1 / 1.25 if e.delta > 0 else 1.25)

    def _zoom_at(self, px, py, f):
        if not self.win: return
        x, y = self.to_model(px, py)
        x0, y0, x1, y1 = self.win
        self.win = (x - (x - x0) * f, y - (y - y0) * f, x + (x1 - x) * f, y + (y1 - y) * f)
        self.redraw()

    def _pan_start(self, e):
        self._drag = ('pan', e.x, e.y, self.win); self.cv.config(cursor='fleur')

    def _pan_move(self, e):
        if not self._drag or self._drag[0] != 'pan': return
        _, sx, sy, w0 = self._drag
        u = (w0[2] - w0[0]) / self._size()[0]
        dx, dy = (e.x - sx) * u, (e.y - sy) * u
        self.win = (w0[0] - dx, w0[1] + dy, w0[2] - dx, w0[3] + dy)
        self._preview()

    def _pan_end(self, e):
        self._drag = None; self.set_mode(self.mode); self.redraw(fast=False)

    def _left_down(self, e):
        self._drag = ('left', e.x, e.y)
        if self.mode in ('rect', 'zoomwin'):
            self._band = self.cv.create_rectangle(e.x, e.y, e.x, e.y, outline='#ffd166', dash=(4, 3), width=2)

    def _left_move(self, e):
        if self._band:
            _, sx, sy = self._drag
            self.cv.coords(self._band, sx, sy, e.x, e.y)

    def _left_up(self, e):
        if not self._drag or not self.model: return
        _, sx, sy = self._drag; self._drag = None
        if self._band:
            self.cv.delete(self._band); self._band = None
            if abs(e.x - sx) > 5 and abs(e.y - sy) > 5:
                a, b = self.to_model(sx, sy), self.to_model(e.x, e.y)
                r = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
                if self.mode == 'zoomwin':
                    self.win = self._aspect(r); self.set_mode('pick'); self.redraw()
                elif self.on_rect:
                    self.on_rect(r)
            return
        x, y = self.to_model(e.x, e.y)
        hit = self.model.pick(x, y, self.units_per_px() * 6)
        self.on_pick and self.on_pick(hit, (x, y))

    def _motion(self, e):
        if not self.model or not self.win: return
        x, y = self.to_model(e.x, e.y)
        now = time.time()
        if self.on_hover and now - self._hover_t > 0.12:
            self._hover_t = now
            hit = self.model.pick(x, y, self.units_per_px() * 5)
            self.on_hover((x, y), self.model.describe(hit) if hit else None)
