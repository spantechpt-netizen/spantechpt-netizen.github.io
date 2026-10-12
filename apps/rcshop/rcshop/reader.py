"""Drawing reader page: the engineer teaches the program how this consultant draws, on the drawing itself.

left    the roles (what the engine must find) as cards: colour, value, what the value catches on the drawing
centre  the drawing (zoom / pan / pick); every taught role is highlighted in its colour, live
right   inspector of the clicked entity + layers (count, show / hide / isolate) + find text
Save writes the keys into work/project.json (and they can be kept as the consultant's reading profile)."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import numpy as np

from . import roles as R
from . import theme as T
from .canvasview import DrawingView


class RoleCard(tk.Frame):
    def __init__(self, master, role, on_click):
        super().__init__(master, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE, cursor='hand2')
        self.role = role
        tk.Frame(self, bg=role.color, width=6).pack(side='left', fill='y')
        box = tk.Frame(self, bg=T.CARD); box.pack(side='left', fill='both', expand=True, padx=8, pady=5)
        top = tk.Frame(box, bg=T.CARD); top.pack(fill='x')
        self.state = tk.Label(top, text='●', bg=T.CARD, fg=T.MUTED, font=(T.FONT, 10))
        self.state.pack(side='right')
        tk.Label(top, text=role.title, bg=T.CARD, fg=T.TXT, font=(T.FONT, 10, 'bold'), anchor='w').pack(side='left')
        self.val = tk.Label(box, text='not set', bg=T.CARD, fg=T.MUTED, font=(T.MONO, 8), anchor='w', justify='left', wraplength=250)
        self.val.pack(fill='x')
        self.info = tk.Label(box, text='', bg=T.CARD, fg=T.MUTED, font=(T.FONT, 8), anchor='w', justify='left', wraplength=250)
        self.info.pack(fill='x')
        for w in (self, box, top, self.val, self.info, self.state):
            w.bind('<Button-1>', lambda e: on_click(role.key))

    def show(self, value, info, active, ok):
        txt = 'not set' if value in (None, '', [], {}) else (', '.join(map(str, value)) if isinstance(value, list) else str(value))
        self.val.config(text=txt[:160], fg=T.TXT if ok is not None else T.MUTED)
        self.info.config(text=info)
        if ok == 'suggested':
            self.state.config(text='?', fg=T.ACCENT); self.info.config(text='SUGGESTED - check it, then Confirm.  ' + info)
        else:
            self.state.config(text='✔' if ok else ('!' if ok is False else '●'), fg=T.OK if ok else (T.BAD if ok is False else T.MUTED))
        self.config(highlightbackground=T.ACCENT if active else T.LINE, highlightthickness=2 if active else 1)


class ReaderPage(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.model = None; self.values = {}; self.extra = {}; self.dirty = False
        self.active = R.ROLES[1].key; self.hidden = set(); self.picked = None
        self._find_hits, self._find_i, self._find_q = [], 0, ''
        self._build()

    # ------------------------------------------------------------------ layout
    def _build(self):
        bar = ttk.Frame(self); bar.pack(fill='x', padx=10, pady=(10, 6))
        ttk.Label(bar, text='Drawing reader', style='H1.TLabel').pack(side='left')
        ttk.Label(bar, text='  teach the program how this consultant draws', style='Muted.TLabel').pack(side='left')
        self.btn_save = ttk.Button(bar, text='Save to project.json', style='Accent.TButton', command=self.save)
        self.btn_save.pack(side='right')
        ttk.Button(bar, text='Save as profile...', command=self.save_profile).pack(side='right', padx=6)
        ttk.Button(bar, text='✨ Suggest', command=self.suggest).pack(side='right')

        tb = ttk.Frame(self); tb.pack(fill='x', padx=10, pady=(0, 6))
        ttk.Label(tb, text='Drawing').pack(side='left')
        self.cmb = ttk.Combobox(tb, width=26, state='readonly'); self.cmb.pack(side='left', padx=4)
        ttk.Button(tb, text='Open', style='Tool.TButton', command=self.load_selected).pack(side='left')
        ttk.Separator(tb, orient='vertical').pack(side='left', fill='y', padx=8)
        ttk.Button(tb, text='Fit', style='Tool.TButton', command=lambda: self.view.fit()).pack(side='left')
        ttk.Button(tb, text='Zoom window', style='Tool.TButton', command=lambda: self.view.set_mode('zoomwin')).pack(side='left', padx=2)
        ttk.Label(tb, text='View').pack(side='left', padx=(10, 2))
        self.cmb_lay = ttk.Combobox(tb, width=18, state='readonly'); self.cmb_lay.pack(side='left')
        self.cmb_lay.bind('<<ComboboxSelected>>', lambda e: self.goto_layout(self.cmb_lay.get()))
        self.v_dim = tk.BooleanVar(value=False); self.v_all = tk.BooleanVar(value=True)
        ttk.Checkbutton(tb, text='Focus (grey the rest)', variable=self.v_dim, command=self.refresh_overlays).pack(side='left', padx=10)
        ttk.Checkbutton(tb, text='Show every role', variable=self.v_all, command=self.refresh_overlays).pack(side='left')
        self.find = ttk.Entry(tb, width=18); self.find.pack(side='right')
        self.find.bind('<Return>', lambda e: self.find_text())
        ttk.Label(tb, text='Find text').pack(side='right', padx=4)

        body = ttk.PanedWindow(self, orient='horizontal'); body.pack(fill='both', expand=True, padx=10, pady=(0, 6))
        # roles
        left = ttk.Frame(body, width=300); body.add(left, weight=0)
        ttk.Label(left, text='WHAT TO TEACH', style='Muted.TLabel', font=(T.FONT, 8, 'bold')).pack(anchor='w', pady=(0, 4))
        holder = tk.Canvas(left, bg=T.BG, highlightthickness=0, width=290)
        sb = ttk.Scrollbar(left, orient='vertical', command=holder.yview)
        self.cards_fr = tk.Frame(holder, bg=T.BG)
        self.cards_fr.bind('<Configure>', lambda e: holder.configure(scrollregion=holder.bbox('all')))
        holder.create_window((0, 0), window=self.cards_fr, anchor='nw', width=285)
        holder.configure(yscrollcommand=sb.set)
        holder.pack(side='left', fill='both', expand=True); sb.pack(side='left', fill='y')
        holder.bind_all('<MouseWheel>', lambda e: holder.yview_scroll(-1 if e.delta > 0 else 1, 'units') if str(e.widget).startswith(str(holder)) else None)
        self.cards = {}
        for r in R.ROLES:
            c = RoleCard(self.cards_fr, r, self.set_active); c.pack(fill='x', pady=3, padx=2); self.cards[r.key] = c
        # canvas + role tools under it
        mid = ttk.Frame(body); body.add(mid, weight=1)
        self.how = tk.Label(mid, text='', bg='#fff4e6', fg=T.TXT, font=(T.FONT, 10), anchor='w', padx=10, pady=6)
        self.how.pack(fill='x')
        self.tools = ttk.Frame(mid); self.tools.pack(fill='x', pady=2)
        self.view = DrawingView(mid, on_pick=self.on_pick, on_hover=self.on_hover, on_rect=self.on_rect, on_status=self.on_status)
        self.view.pack(fill='both', expand=True)
        st = tk.Frame(mid, bg=T.RAIL); st.pack(fill='x')
        self.st_xy = tk.Label(st, text='', bg=T.RAIL, fg=T.RAIL_TXT, font=(T.MONO, 9), width=28, anchor='w'); self.st_xy.pack(side='left', padx=6)
        self.st_hover = tk.Label(st, text='', bg=T.RAIL, fg=T.RAIL_SUB, font=(T.MONO, 9), anchor='w'); self.st_hover.pack(side='left', fill='x', expand=True)
        self.st_r = tk.Label(st, text='', bg=T.RAIL, fg=T.RAIL_SUB, font=(T.MONO, 9)); self.st_r.pack(side='right', padx=6)
        # inspector + layers
        right = ttk.Frame(body, width=290); body.add(right, weight=0)
        ttk.Label(right, text='INSPECTOR', style='Muted.TLabel', font=(T.FONT, 8, 'bold')).pack(anchor='w')
        self.insp = tk.Text(right, height=9, width=30, bg=T.CARD, fg=T.TXT, relief='flat', font=(T.MONO, 9), wrap='word',
                            highlightthickness=1, highlightbackground=T.LINE)
        self.insp.pack(fill='x', pady=(2, 4))
        ib = ttk.Frame(right); ib.pack(fill='x')
        ttk.Button(ib, text='Use for the role', style='Tool.TButton', command=self.assign_picked).pack(side='left')
        ttk.Button(ib, text='Select layer', style='Tool.TButton', command=self.select_picked_layer).pack(side='left', padx=4)
        nb = ttk.Notebook(right); nb.pack(fill='both', expand=True, pady=(8, 0))
        mt = ttk.Frame(nb); nb.add(mt, text='Matches')
        self.match_info = ttk.Label(mt, text='', style='Muted.TLabel', wraplength=270, justify='left'); self.match_info.pack(anchor='w', pady=2)
        self.mlist = ttk.Treeview(mt, columns=('n',), show='tree headings', height=14)
        self.mlist.heading('#0', text='caught'); self.mlist.heading('n', text='×')
        self.mlist.column('#0', width=170); self.mlist.column('n', width=50, anchor='e')
        self.mlist.pack(fill='both', expand=True)
        self.mlist.bind('<Double-1>', lambda e: self.zoom_match_item())
        ttk.Label(mt, text='double-click: zoom to the next one', style='Muted.TLabel').pack(anchor='w')
        lt = ttk.Frame(nb); nb.add(lt, text='Layers')
        self.lay_filter = ttk.Entry(lt); self.lay_filter.pack(fill='x', pady=2)
        self.lay_filter.bind('<KeyRelease>', lambda e: self.fill_layers())
        self.lay = ttk.Treeview(lt, columns=('n',), show='tree headings', height=14, selectmode='extended')
        self.lay.heading('#0', text='layer'); self.lay.heading('n', text='items')
        self.lay.column('#0', width=180); self.lay.column('n', width=55, anchor='e')
        self.lay.tag_configure('off', foreground='#9aa6b2')
        self.lay.pack(fill='both', expand=True)
        self.lay.bind('<Double-1>', lambda e: self.toggle_layers())
        lb = ttk.Frame(lt); lb.pack(fill='x', pady=2)
        ttk.Button(lb, text='Hide/Show', style='Tool.TButton', command=self.toggle_layers).pack(side='left')
        ttk.Button(lb, text='Isolate', style='Tool.TButton', command=self.isolate_layers).pack(side='left', padx=3)
        ttk.Button(lb, text='All', style='Tool.TButton', command=self.show_all_layers).pack(side='left')
        ttk.Button(lb, text='Use for role', style='Tool.TButton', command=self.assign_layers).pack(side='right')
        self.suggested = set(); self._mcycle = {}
        c = self.view.cv
        c.bind('<Enter>', lambda e: c.focus_set())
        c.bind('<Key-f>', lambda e: self.view.fit()); c.bind('<Key-z>', lambda e: self.view.set_mode('zoomwin'))
        c.bind('<Escape>', lambda e: self.set_active(self.active))
        c.bind('<Control-s>', lambda e: self.save())
        for n, r in enumerate(R.ROLES[:9]):
            c.bind(f'<Key-{n + 1}>', lambda e, k=r.key: self.set_active(k))
        self.set_active(self.active)

    # ------------------------------------------------------------------ project
    def on_show(self):
        ws = self.app.ws
        if not ws: return
        dw = ws.drawings()
        self.cmb['values'] = dw
        P = ws.project()
        if not self.dirty:
            self.values = {r.key: P.get(r.key) for r in R.ROLES}
            self.extra = {k: P.get(k) for k in ('axis_attr', 'axis_family_attr')}
        cur = P.get('dxf') or ws.meta.get('main_dxf')
        if cur in dw and (self.model is None or self.model.path.name != cur):
            self.cmb.set(cur); self.load_selected()
        self.refresh_cards()

    def load_selected(self):
        name = self.cmb.get()
        if not name or not self.app.ws: return
        path = self.app.ws.work / name
        self.app.busy_start(f'reading {name} (first time on a big plan: up to a few minutes, then cached)')
        def work():
            from .drawing import DrawingModel
            try:
                m = DrawingModel(path, log=lambda s: self.app.say(s))
            except Exception as e:
                self.after(0, lambda: (self.app.busy_end(), messagebox.showerror('RC Shop', f'cannot read {name}: {e}'))); return
            self.after(0, lambda: self._loaded(m))
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, m):
        self.app.busy_end()
        self.model = m; self.hidden = set(); self.picked = None
        self.cmb_lay['values'] = [k for k, w in m.layouts.items() if w]
        self.fill_layers()
        win = None
        fv = self.values.get('fnd_view')
        if self.values.get('layout') in m.layouts and m.layouts[self.values['layout']]:
            win = max(m.layouts[self.values['layout']], key=lambda w: (w[2] - w[0]) * (w[3] - w[1]))
        elif fv:
            win = R.window_rect(fv)
        self.view.set_model(m, win)
        self.refresh_cards(); self.refresh_overlays()

    # ------------------------------------------------------------------ roles
    def set_active(self, key):
        self.active = key
        r = R.BY_KEY[key]
        self.how.config(text=f'  {r.title}:  {r.how}')
        self.view.set_mode('rect' if r.kind == 'window' else 'pick')
        for w in self.tools.winfo_children(): w.destroy()
        if r.kind == 'textre':
            ttk.Label(self.tools, text='pattern').pack(side='left')
            self.re_ent = ttk.Entry(self.tools, width=48, font=(T.MONO, 9)); self.re_ent.pack(side='left', padx=4)
            self.re_ent.insert(0, self.values.get(key) or '')
            ttk.Button(self.tools, text='Apply', style='Tool.TButton', command=self.apply_re).pack(side='left')
        if r.kind == 'block':
            ttk.Label(self.tools, text='axis name in').pack(side='left')
            self.cb_num = ttk.Combobox(self.tools, width=10, state='readonly'); self.cb_num.pack(side='left', padx=3)
            ttk.Label(self.tools, text='family (X/Y) in').pack(side='left')
            self.cb_fam = ttk.Combobox(self.tools, width=10, state='readonly'); self.cb_fam.pack(side='left', padx=3)
            for cb, k in ((self.cb_num, 'axis_attr'), (self.cb_fam, 'axis_family_attr')):
                cb.bind('<<ComboboxSelected>>', lambda e, cb=cb, k=k: self._set_extra(k, cb.get()))
            self._fill_tags()
        if r.kind == 'layout':
            ttk.Label(self.tools, text='layout').pack(side='left')
            cb = ttk.Combobox(self.tools, width=28, state='readonly', values=list(self.cmb_lay['values'] or []))
            cb.pack(side='left', padx=4)
            if self.values.get('layout'): cb.set(self.values['layout'])
            cb.bind('<<ComboboxSelected>>', lambda e: (self._set('layout', cb.get()), self.goto_layout(cb.get())))
        ttk.Button(self.tools, text='Clear', style='Tool.TButton', command=lambda: self._set(key, None)).pack(side='right')
        if key in self.suggested:
            ttk.Button(self.tools, text='Confirm suggestion', style='Accent.TButton', command=self.confirm).pack(side='right', padx=4)
        ttk.Button(self.tools, text='Zoom to matches', style='Tool.TButton', command=self.zoom_matches).pack(side='right', padx=4)
        self.refresh_cards(); self.refresh_overlays()

    def _set(self, key, v, msg='', suggested=False):
        self.values[key] = v; self.dirty = True
        if suggested: self.suggested.add(key)
        else: self.suggested.discard(key)
        if msg: self.app.say(f'{R.BY_KEY[key].title}: {msg}')
        if key == 'axis_block' and v and self.model:
            num, fam, tags = R.guess_axis_tags(self.model, v)
            if num and not self.extra.get('axis_attr'): self.extra['axis_attr'] = num
            if fam and not self.extra.get('axis_family_attr'): self.extra['axis_family_attr'] = fam
            self.app.say(f'grid bubble attributes: {tags}')
            self._fill_tags()
        if R.BY_KEY[key].kind == 'textre' and hasattr(self, 're_ent'):
            self.re_ent.delete(0, 'end'); self.re_ent.insert(0, v or '')
        self.refresh_cards(); self.refresh_overlays()

    def _set_extra(self, k, v):
        self.extra[k] = v; self.dirty = True; self.refresh_cards(); self.refresh_overlays()

    def _fill_tags(self):
        if not hasattr(self, 'cb_num') or not self.model or not self.values.get('axis_block'): return
        _, _, tags = R.guess_axis_tags(self.model, self.values['axis_block'])
        for cb, k in ((self.cb_num, 'axis_attr'), (self.cb_fam, 'axis_family_attr')):
            cb['values'] = list(tags)
            if self.extra.get(k): cb.set(self.extra[k])

    def apply_re(self):
        p = self.re_ent.get().strip()
        if p and R.compile_full(p) is None:
            messagebox.showwarning('RC Shop', 'not a valid pattern'); return
        self._set(self.active, p or None, f'pattern {p}')

    def refresh_cards(self):
        for k, c in self.cards.items():
            r = R.BY_KEY[k]; v = self.values.get(k)
            info, ok = '', None
            if v not in (None, '', [], {}) and self.model is not None:
                if r.kind in ('layer', 'layers', 'suffix', 'textre', 'block'):
                    pis, tis, info = R.matches(self.model, r, v, self.extra)
                    ok = (len(pis) + len(tis)) > 0
                elif r.kind == 'window':
                    info, ok = f'{v[2]:.0f} high around ({v[0]:.0f}, {v[1]:.0f})', True
                elif r.kind == 'layout':
                    ok = v in self.model.layouts; info = 'layout found' if ok else 'no such layout in this drawing'
                if r.kind == 'block':
                    info += f"   name: {self.extra.get('axis_attr') or '?'}  family: {self.extra.get('axis_family_attr') or '?'}"
            elif v not in (None, '', [], {}):
                ok = True; info = 'open the drawing to see what it catches'
            if r.module not in (self.app.ws.modules if self.app.ws else []):
                info = (info + '   ' if info else '') + f'(module "{r.module}" is off)'
            c.show(v, info, k == self.active, 'suggested' if (k in self.suggested and ok) else ok)
        self.btn_save.config(text='Save to project.json' + (' *' if self.dirty else ''))
        self.fill_matches()

    def refresh_overlays(self):
        if not self.model: return
        hl = []
        for r in R.ROLES:
            v = self.values.get(r.key)
            if v in (None, '', [], {}) or r.kind in ('window', 'layout'): continue
            if r.key != self.active and not self.v_all.get(): continue
            pis, tis, _ = R.matches(self.model, r, v, self.extra)
            hl.append((pis, tis, r.color, 2.4 if r.key == self.active else 1.2))
        hl.sort(key=lambda h: h[3])                          # the active role on top
        rect = None
        fv = self.values.get('fnd_view')
        if fv and (self.active == 'fnd_view' or self.v_all.get()):
            rect = R.window_rect(fv)
        self.view.set_overlays(hl, self.picked, rect, self.v_dim.get(), self._hidden_ids())

    # ------------------------------------------------------------------ canvas events
    def on_pick(self, hit, xy):
        self.picked = hit
        d = self.model.describe(hit) if hit else {}
        self.show_inspector(d)
        if hit:
            self.assign_picked(quiet=True)
        else:
            self.refresh_overlays()

    def assign_picked(self, quiet=False):
        if not self.picked or not self.model: return
        r = R.BY_KEY[self.active]
        if r.kind in ('window', 'layout'):
            self.refresh_overlays(); return
        v, msg = R.value_from_click(self.model, r, self.picked, self.values.get(r.key))
        if v != self.values.get(r.key):
            self._set(r.key, v, msg)
        else:
            if not quiet or msg: self.app.say(msg)
            self.refresh_overlays()

    def on_rect(self, rect):
        r = R.BY_KEY[self.active]
        if r.kind == 'window':
            self._set(r.key, R.window_value(rect), 'window set')

    def on_hover(self, xy, d):
        self.st_xy.config(text=f'x {xy[0]:,.0f}   y {xy[1]:,.0f}')
        if d:
            s = f"{d['type']}  {d['layer']}" + (f"  '{d.get('text', '')[:40]}'" if d.get('text') else '') + \
                (f"  [{d['insert']['block']}]" if d.get('insert') else '')
        else:
            s = ''
        self.st_hover.config(text=s)

    def on_status(self, s):
        self.st_r.config(text=s)

    def show_inspector(self, d):
        self.insp.config(state='normal'); self.insp.delete('1.0', 'end')
        if not d:
            self.insp.insert('end', 'click an entity on the drawing')
        else:
            for k in ('type', 'layer', 'text', 'height', 'block', 'length', 'size', 'vertices', 'closed', 'x', 'y'):
                if k in d and d[k] not in ('', None):
                    self.insp.insert('end', f'{k:9s} {d[k]}\n')
            if d.get('insert'):
                i = d['insert']
                self.insp.insert('end', f"\nblock    {i['block']}\nat       {i['x']}, {i['y']}\n")
                for t, v in list(i['attribs'].items())[:8]:
                    self.insp.insert('end', f'  {t} = {v}\n')
        self.insp.config(state='disabled')

    # ------------------------------------------------------------------ suggestions / matches
    def suggest(self):
        if not self.model: return
        got = R.suggest(self.model)
        new = {k: v for k, v in got.items() if self.values.get(k) in (None, '', [], {})}
        for k, v in new.items():
            self._set(k, v, 'suggested', suggested=True)
        if 'axis_block' in new:
            self._set_extra('axis_attr', self.extra.get('axis_attr'))
        self.app.say(f'{len(new)} roles suggested from layer names, labels and blocks - check each (orange ?) and confirm'
                     if new else 'nothing to suggest: every role already has a value')
        self.set_active(next(iter(new), self.active))

    def confirm(self):
        self.suggested.discard(self.active); self.dirty = True
        nxt = next((r.key for r in R.ROLES if r.key in self.suggested), None)
        self.set_active(nxt or self.active)

    def fill_matches(self):
        if not hasattr(self, 'mlist'): return
        self.mlist.delete(*self.mlist.get_children()); self._mcycle = {}
        r = R.BY_KEY[self.active]; v = self.values.get(r.key)
        if not self.model or v in (None, '', [], {}) or r.kind in ('window', 'layout'):
            self.match_info.config(text=''); return
        pis, tis, info = R.matches(self.model, r, v, self.extra)
        self.match_info.config(text=info[:200])
        groups = {}
        if len(tis):
            for i in tis:
                groups.setdefault(self.model.t_text[i].strip().upper(), []).append(('text', int(i)))
        else:
            for i in pis[:200000]:
                groups.setdefault(self.model.layers[self.model.p_layer[i]], []).append(('poly', int(i)))
        for k in sorted(groups, key=lambda k: (-len(groups[k]), k))[:500]:
            self.mlist.insert('', 'end', iid=k, text=k, values=(len(groups[k]),))
        self._mgroups = groups

    def zoom_match_item(self):
        sel = self.mlist.selection()
        if not sel or not self.model: return
        items = self._mgroups.get(sel[0], [])
        if not items: return
        n = self._mcycle.get(sel[0], 0); self._mcycle[sel[0]] = n + 1
        kind, i = items[n % len(items)]
        if kind == 'text':
            x, y = self.model.t_xy[i]; size = max(self.model.t_h[i] * 30, 1500)
        else:
            x, y = (self.model.bx0[i] + self.model.bx1[i]) / 2, (self.model.by0[i] + self.model.by1[i]) / 2
            size = max(self.model.bx1[i] - self.model.bx0[i], self.model.by1[i] - self.model.by0[i], 1500) * 1.5
        self.picked = (kind, i); self.show_inspector(self.model.describe(self.picked))
        self.view.zoom_to(x, y, size); self.refresh_overlays()
        self.app.say(f'{sel[0]}: {n % len(items) + 1} of {len(items)}')

    # ------------------------------------------------------------------ layers
    def fill_layers(self):
        if not self.model: return
        f = self.lay_filter.get().strip().upper()
        self.lay.delete(*self.lay.get_children())
        order = np.argsort(-self.model.layer_count)
        for i in order:
            n = self.model.layers[i]
            if self.model.layer_count[i] == 0 or (f and f not in n.upper()): continue
            self.lay.insert('', 'end', iid=str(i), text=('   ' if i not in self.hidden else '✕ ') + n,
                            values=(int(self.model.layer_count[i]),), tags=('off',) if i in self.hidden else ())

    def _hidden_ids(self):
        return set(self.hidden)

    def toggle_layers(self):
        for s in self.lay.selection():
            i = int(s); self.hidden.symmetric_difference_update({i})
        self.fill_layers(); self.refresh_overlays()

    def isolate_layers(self):
        sel = {int(s) for s in self.lay.selection()}
        if not sel: return
        self.hidden = set(range(len(self.model.layers))) - sel
        self.fill_layers(); self.refresh_overlays()

    def show_all_layers(self):
        self.hidden = set(); self.fill_layers(); self.refresh_overlays()

    def select_picked_layer(self):
        if not self.picked: return
        d = self.model.describe(self.picked)
        i = self.model.layers.index(d['layer'])
        self.lay_filter.delete(0, 'end'); self.fill_layers()
        if self.lay.exists(str(i)):
            self.lay.selection_set(str(i)); self.lay.see(str(i))

    def assign_layers(self):
        r = R.BY_KEY[self.active]
        names = [self.model.layers[int(s)] for s in self.lay.selection()]
        if not names or r.kind not in ('layer', 'layers', 'suffix'): return
        if r.kind == 'layer':
            self._set(r.key, names[0], f'layer {names[0]}')
        else:
            names = [R.short_layer(n) for n in names] if r.kind == 'suffix' else names
            cur = list(self.values.get(r.key) or [])
            self._set(r.key, cur + [n for n in names if n not in cur], 'added ' + ', '.join(names))

    # ------------------------------------------------------------------ navigation
    def goto_layout(self, name):
        if not self.model or not self.model.layouts.get(name): return
        self.view.fit(max(self.model.layouts[name], key=lambda w: (w[2] - w[0]) * (w[3] - w[1])))

    def zoom_matches(self):
        r = R.BY_KEY[self.active]; v = self.values.get(r.key)
        if not self.model or v in (None, '', [], {}): return
        if r.kind == 'window':
            self.view.fit(R.window_rect(v)); return
        pis, tis, _ = R.matches(self.model, r, v, self.extra)
        xs, ys = [], []
        if len(pis):
            xs += [self.model.bx0[pis].min(), self.model.bx1[pis].max()]; ys += [self.model.by0[pis].min(), self.model.by1[pis].max()]
        if len(tis):
            xs += [self.model.t_xy[tis, 0].min(), self.model.t_xy[tis, 0].max()]; ys += [self.model.t_xy[tis, 1].min(), self.model.t_xy[tis, 1].max()]
        if xs:
            dx, dy = (max(xs) - min(xs)) * 0.05 + 500, (max(ys) - min(ys)) * 0.05 + 500
            self.view.fit((min(xs) - dx, min(ys) - dy, max(xs) + dx, max(ys) + dy))

    def find_text(self):
        q = self.find.get().strip().upper()
        if not q or not self.model: return
        if not self._find_hits or self._find_q != q:
            self._find_q = q; self._find_i = 0
            self._find_hits = [i for i, s in enumerate(self.model.t_upper) if q in s]
        if not self._find_hits:
            self.app.say(f'"{q}" not found'); return
        i = self._find_hits[self._find_i % len(self._find_hits)]; self._find_i += 1
        x, y = self.model.t_xy[i]; h = self.model.t_h[i]
        self.picked = ('text', int(i)); self.show_inspector(self.model.describe(self.picked))
        self.view.zoom_to(x, y, max(h * 40, 2000)); self.refresh_overlays()
        self.app.say(f'"{q}": {self._find_i}/{len(self._find_hits)}  {self.model.t_text[i]}')

    # ------------------------------------------------------------------ save
    def save(self):
        if not self.app.ws: return
        if self.suggested and not messagebox.askyesno('RC Shop', f'{len(self.suggested)} suggested roles are not confirmed yet:\n' +
                ', '.join(R.BY_KEY[k].title for k in self.suggested) + '\n\nSave them anyway?'):
            return
        vals = dict(self.values)
        vals.update({k: v for k, v in self.extra.items() if v})
        wrote = R.save(self.app.ws, vals)
        self.dirty = False; self.suggested = set(); self.refresh_cards()
        self.app.say('project.json: ' + ', '.join(wrote)); self.app.refresh_all()

    def save_profile(self):
        if self.dirty: self.save()
        self.app.save_profile()
