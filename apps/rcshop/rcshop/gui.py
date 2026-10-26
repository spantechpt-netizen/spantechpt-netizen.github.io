"""RC Shop main window: nav rail on the left (like Auto PT Suite), one page per stage, footer with progress and Start."""
import json, os, queue, shlex, subprocess, sys, threading, traceback
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter.simpledialog import askstring

from . import __version__, profiles, validate
from . import theme as T
from .paths import settings, save_settings, DEFAULTS
from .steps import MODULES
from .workspace import Workspace

NAV = [('project', 'Project', 'Method, drawings, modules'),
       ('reader', 'Drawing reader', 'Teach it the drawing'),
       ('data', 'Data files', 'Schedules and settings'),
       ('run', 'Run', 'Steps, log and progress'),
       ('review', 'Review', 'Check and preview sheets'),
       ('deliver', 'Deliver', 'Zip for the engineer'),
       ('profiles', 'Profiles', 'How each consultant draws'),
       ('settings', 'Settings', 'Converter, engine, limits')]
STATE_COL = {'done': T.OK, 'ready': T.INFO, 'stale': T.WARN, 'blocked': '#8a96a3', 'failed': T.BAD}


def open_path(p):
    p = str(p)
    if sys.platform.startswith('win'):
        os.startfile(p)                                       # noqa: the Windows shell opens folders / files
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', p])


def header(parent, title, sub):
    f = ttk.Frame(parent); f.pack(fill='x', padx=18, pady=(14, 8))
    ttk.Label(f, text=title, style='H1.TLabel').pack(side='left')
    ttk.Label(f, text='   ' + sub, style='Muted.TLabel').pack(side='left', pady=(6, 0))
    return f


def card(parent, title=None, **pack):
    outer = tk.Frame(parent, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE)
    outer.pack(**({'fill': 'x', 'padx': 18, 'pady': 6} | pack))
    if title:
        ttk.Label(outer, text=title, style='CardH2.TLabel').pack(anchor='w', padx=12, pady=(10, 4))
    return outer


class App(tk.Tk):
    def __init__(self, project=None):
        super().__init__()
        self.title(f'RC Shop {__version__} - Span Tech'); self.geometry('1440x880'); self.minsize(1100, 680)
        T.apply(self)
        self.ws, self.busy, self.q = None, False, queue.Queue()
        self.rail = T.NavRail(self, NAV, self.show); self.rail.pack(side='left', fill='y')
        main = ttk.Frame(self); main.pack(side='left', fill='both', expand=True)
        self.pages_fr = ttk.Frame(main); self.pages_fr.pack(fill='both', expand=True)
        self._footer(main)
        self.pages = {}
        from .reader import ReaderPage
        builders = dict(project=self._page_project, reader=lambda p: ReaderPage(p, self), data=self._page_data,
                        run=self._page_run, review=self._page_review, deliver=self._page_deliver,
                        profiles=self._page_profiles, settings=self._page_settings)
        for key, _, _ in NAV:
            fr = ttk.Frame(self.pages_fr)
            page = builders[key](fr)
            if isinstance(page, ttk.Frame) and page is not fr:
                page.pack(fill='both', expand=True)
            self.pages[key] = (fr, page)
        self.current = None
        self.show('project')
        if project:
            self.load(project)
        self.after(100, self._poll)

    # ------------------------------------------------------------------ frame
    def _footer(self, main):
        f = tk.Frame(main, bg=T.CARD, highlightthickness=1, highlightbackground=T.LINE); f.pack(fill='x', side='bottom')
        self.status = tk.Label(f, text='open or create a project', bg=T.CARD, fg=T.MUTED, anchor='w', font=(T.FONT, 9))
        self.status.pack(side='left', fill='x', expand=True, padx=12, pady=8)
        self.prog = ttk.Progressbar(f, mode='indeterminate', length=180); self.prog.pack(side='left', padx=8)
        self.btn_start = ttk.Button(f, text='Start  ▶  run all ready steps', style='Accent.TButton', command=self.run_all)
        self.btn_start.pack(side='right', padx=12, pady=6)

    def show(self, key):
        if self.current:
            self.pages[self.current][0].pack_forget()
        self.current = key
        fr, page = self.pages[key]
        fr.pack(fill='both', expand=True)
        self.rail.select(key)
        if hasattr(page, 'on_show'):
            page.on_show()
        getattr(self, f'_show_{key}', lambda: None)()

    def say(self, s):
        self.q.put(('log', str(s)))

    def busy_start(self, msg=''):
        self.busy = True; self.prog.start(12); self.btn_start.state(['disabled'])
        if msg: self.say(msg)

    def busy_end(self):
        self.busy = False; self.prog.stop(); self.btn_start.state(['!disabled'])

    def _poll(self):
        try:
            while True:
                kind, s = self.q.get_nowait()
                if kind == 'log':
                    self.status.config(text=s.splitlines()[-1][:180] if s else '')
                    for w in (getattr(self, 'log', None),):
                        if w is not None:
                            w.config(state='normal'); w.insert('end', s + '\n'); w.see('end'); w.config(state='disabled')
                elif kind == 'done':
                    self.busy_end(); self.refresh_all()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _bg(self, fn, *a, msg=''):
        if self.busy:
            messagebox.showinfo('RC Shop', 'something is still running'); return
        self.busy_start(msg)
        def work():
            try:
                fn(*a)
            except Exception as e:
                self.say(f'ERROR: {e}\n{traceback.format_exc()}')
            self.q.put(('done', None))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ project
    def new_project(self):
        d = filedialog.askdirectory(title='Folder for the new project (empty)')
        if not d: return
        name = askstring('RC Shop', 'Project name:', initialvalue=Path(d).name, parent=self) or Path(d).name
        self.load(Workspace.create(d, name).root)

    def open_project(self):
        d = filedialog.askdirectory(title='Project folder (holds rcshop.json)')
        if d: self.load(d)

    def load(self, d):
        try:
            self.ws = Workspace(d)
        except Exception as e:
            messagebox.showerror('RC Shop', str(e)); return
        self.rail.foot.config(text=f'{self.ws.name}\n{self.ws.root}')
        self.say(f'project {self.ws.name}')
        self.refresh_all()
        page = self.pages[self.current][1]
        if hasattr(page, 'on_show'): page.on_show()

    def refresh_all(self):
        if not self.ws: return
        for k in ('project', 'data', 'run', 'review', 'deliver', 'profiles'):
            getattr(self, f'_show_{k}', lambda: None)()

    def _page_project(self, p):
        header(p, 'Project', 'method, drawings and what to produce')
        c = card(p); b = tk.Frame(c, bg=T.CARD); b.pack(fill='x', padx=12, pady=10)
        ttk.Button(b, text='New project', style='Accent.TButton', command=self.new_project).pack(side='left')
        ttk.Button(b, text='Open project', command=self.open_project).pack(side='left', padx=6)
        self.lbl_proj = ttk.Label(b, text='no project open', style='CardMuted.TLabel'); self.lbl_proj.pack(side='left', padx=12)
        row = ttk.Frame(p); row.pack(fill='both', expand=True)
        c = card(row, 'Drawings', side='left', fill='both', expand=True, padx=(18, 6))
        self.dwg = ttk.Treeview(c, columns=('role', 'size'), show='tree headings', height=8)
        self.dwg.heading('#0', text='file'); self.dwg.heading('role', text=''); self.dwg.heading('size', text='MB')
        self.dwg.column('role', width=80); self.dwg.column('size', width=60, anchor='e')
        self.dwg.pack(fill='both', expand=True, padx=12)
        bb = tk.Frame(c, bg=T.CARD); bb.pack(fill='x', padx=12, pady=8)
        ttk.Button(bb, text='Add DWG / DXF', command=self.add_drawing).pack(side='left')
        ttk.Button(bb, text='Set as main', command=self.set_main).pack(side='left', padx=4)
        ttk.Button(bb, text='Open in reader', command=lambda: self.show('reader')).pack(side='left')
        ttk.Button(bb, text='Survey report', command=lambda: self.open_rel('survey/survey.md')).pack(side='right')
        c = card(row, 'What to produce', side='left', fill='both', expand=True, padx=(6, 18))
        self.modvars = {}
        for m, d in MODULES.items():
            v = tk.BooleanVar(); self.modvars[m] = v
            ttk.Checkbutton(c, text=d, variable=v, style='Card.TCheckbutton', command=self.modules_changed,
                            state='disabled' if m == 'core' else 'normal').pack(anchor='w', padx=14, pady=2)
        c = card(p, 'Next')
        self.next_lbl = ttk.Label(c, text='', style='Card.TLabel', justify='left', wraplength=1000); self.next_lbl.pack(anchor='w', padx=12, pady=(0, 10))

    def _show_project(self):
        if not self.ws: return
        self.lbl_proj.config(text=f'{self.ws.name}   ·   {self.ws.root}')
        self.dwg.delete(*self.dwg.get_children())
        for n in self.ws.drawings():
            f = self.ws.work / n
            role = 'main' if n == self.ws.meta.get('main_dxf') else ('final plan' if n == (self.ws.project().get('fnd_final') or {}).get('dxf') else '')
            self.dwg.insert('', 'end', iid=n, text=n, values=(role, f'{f.stat().st_size / 1e6:.1f}'))
        for m, v in self.modvars.items():
            v.set(m in self.ws.modules)
        probs = validate.problems(self.ws)
        if not self.ws.drawings():
            nxt = '1. Add the consultant drawing (DWG or DXF).'
        elif not (self.ws.work / 'project.json').exists():
            nxt = '2. Run the survey (Run page), then create project.json from its draft (Data files), then teach the drawing (Drawing reader).'
        elif probs:
            nxt = 'Still missing:\n  ' + '\n  '.join(probs[:8])
        else:
            nxt = 'Everything the selected modules need is there - press Start.'
        self.next_lbl.config(text=nxt)

    def modules_changed(self):
        if self.ws:
            self.ws.set_modules([m for m, v in self.modvars.items() if v.get()]); self.refresh_all()

    def add_drawing(self):
        if not self.ws: return
        fs = filedialog.askopenfilenames(filetypes=[('Drawings', '*.dwg *.dxf'), ('All', '*.*')])
        if fs: self._bg(self._add, fs, msg='converting ...')

    def _add(self, fs):
        from .convert import to_dxf
        for f in fs:
            dxf = to_dxf(self.ws.add_input(f), self.ws.work, log=self.say)
            if not self.ws.meta.get('main_dxf'): self.ws.set_main(dxf.name)
            self.say(f'added {dxf.name}')

    def set_main(self):
        if self.ws and self.dwg.selection():
            self.ws.set_main(self.dwg.selection()[0]); self.refresh_all()

    def open_rel(self, rel):
        if self.ws:
            p = self.ws.work / rel
            open_path(p) if p.exists() else messagebox.showinfo('RC Shop', f'{rel} does not exist yet')

    # ------------------------------------------------------------------ data files
    def _page_data(self, p):
        header(p, 'Data files', 'schedules and settings the engine reads')
        row = ttk.PanedWindow(p, orient='horizontal'); row.pack(fill='both', expand=True, padx=18, pady=(0, 10))
        left = ttk.Frame(row); row.add(left, weight=1)
        self.data = ttk.Treeview(left, columns=('state',), show='tree headings', height=8)
        self.data.heading('#0', text='file'); self.data.heading('state', text='')
        self.data.column('state', width=70)
        self.data.pack(fill='x')
        self.data.bind('<<TreeviewSelect>>', lambda e: self._open_data())
        self.data_what = ttk.Label(left, text='', style='Muted.TLabel', wraplength=330, justify='left'); self.data_what.pack(anchor='w', pady=6)
        ttk.Button(left, text='project.json from survey draft', command=self.from_draft).pack(fill='x', pady=2)
        ttk.Button(left, text="What's missing?", command=self.show_problems).pack(fill='x', pady=2)
        right = ttk.Frame(row); row.add(right, weight=3)
        tb = ttk.Frame(right); tb.pack(fill='x')
        ttk.Button(tb, text='Save', style='Accent.TButton', command=self._save_data).pack(side='left')
        ttk.Button(tb, text='Check JSON', command=self._check_data).pack(side='left', padx=6)
        self.data_msg = ttk.Label(tb, text='', style='Muted.TLabel'); self.data_msg.pack(side='left', padx=8)
        self.ed = ScrolledText(right, font=(T.MONO, 10), undo=True, bg=T.CARD, relief='flat',
                               highlightthickness=1, highlightbackground=T.LINE)
        self.ed.pack(fill='both', expand=True, pady=6)
        self.ed_file = None

    def _show_data(self):
        if not self.ws: return
        sel = self.data.selection()
        self.data.delete(*self.data.get_children())
        for n, what, ok in self.ws.data_files():
            self.data.insert('', 'end', iid=n, text=n, values=('present' if ok else 'missing',))
        if sel and self.data.exists(sel[0]): self.data.selection_set(sel[0])

    def _open_data(self):
        if not self.ws or not self.data.selection(): return
        n = self.data.selection()[0]
        from .workspace import DATA_FILES
        self.data_what.config(text=DATA_FILES.get(n, ''))
        self.ed_file = self.ws.work / n
        self.ed.delete('1.0', 'end')
        self.ed.insert('1.0', self.ed_file.read_text(encoding='utf-8') if self.ed_file.exists() else '{\n}\n')
        self.data_msg.config(text=str(self.ed_file), foreground=T.MUTED)

    def _check_data(self):
        try:
            json.loads(self.ed.get('1.0', 'end')); self.data_msg.config(text='valid JSON', foreground=T.OK); return True
        except ValueError as e:
            self.data_msg.config(text=f'error: {e}', foreground=T.BAD)
            if getattr(e, 'lineno', None):
                self.ed.see(f'{e.lineno}.0'); self.ed.tag_remove('err', '1.0', 'end')
                self.ed.tag_add('err', f'{e.lineno}.0', f'{e.lineno}.end'); self.ed.tag_config('err', background='#ffd6d6')
            return False

    def _save_data(self):
        if not self.ed_file or not self._check_data(): return
        data = json.loads(self.ed.get('1.0', 'end'))
        self.ed_file.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        self.data_msg.config(text='saved', foreground=T.OK); self.refresh_all()

    def from_draft(self):
        try:
            validate.new_from_draft(self.ws); self.refresh_all(); self.data.selection_set('project.json')
        except Exception as e:
            messagebox.showwarning('RC Shop', str(e))

    def show_problems(self):
        if not self.ws: return
        p = validate.problems(self.ws)
        messagebox.showinfo('What is missing', '\n'.join(p) if p else 'Nothing missing for the selected modules.')

    # ------------------------------------------------------------------ run
    def _page_run(self, p):
        header(p, 'Run', 'every step with what it needs; Start runs all that are ready')
        pan = ttk.PanedWindow(p, orient='vertical'); pan.pack(fill='both', expand=True, padx=18, pady=(0, 10))
        top = ttk.Frame(pan); pan.add(top, weight=3)
        self.tree = ttk.Treeview(top, columns=('status', 'detail'), show='tree headings')
        self.tree.heading('#0', text='step'); self.tree.heading('status', text='status'); self.tree.heading('detail', text='')
        self.tree.column('#0', width=480); self.tree.column('status', width=80, anchor='center'); self.tree.column('detail', width=420)
        for st, c in STATE_COL.items():
            self.tree.tag_configure(st, foreground=c)
        self.tree.tag_configure('group', font=(T.FONT, 9, 'bold'))
        self.tree.pack(fill='both', expand=True)
        b = ttk.Frame(top); b.pack(fill='x', pady=6)
        ttk.Button(b, text='Run selected step', command=self.run_selected).pack(side='left')
        ttk.Label(b, text='  args').pack(side='left'); self.extra = ttk.Entry(b, width=22); self.extra.pack(side='left', padx=4)
        ttk.Label(b, text='(e.g. AREA 2 = one zone)', style='Muted.TLabel').pack(side='left')
        ttk.Button(b, text='Open log', command=self.open_log).pack(side='right')
        self.log = ScrolledText(pan, height=12, font=(T.MONO, 9), state='disabled', bg='#0f1620', fg='#d6e2ee',
                                insertbackground='white', relief='flat')
        pan.add(self.log, weight=2)

    def _show_run(self):
        if not self.ws: return
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        groups = {}
        names = {'read': 'READ THE DRAWING', 'generate': 'SHOP DRAWINGS', 'finish': 'CHECK AND DELIVER'}
        for s in self.ws.steps():
            if s.group not in groups:
                groups[s.group] = self.tree.insert('', 'end', iid='g_' + s.group, text=names.get(s.group, s.group), open=True, tags=('group',))
            st, det = self.ws.status(s)
            self.tree.insert(groups[s.group], 'end', iid=s.id, text=f'{s.title}', values=(st, det), tags=(st,))
        if sel and self.tree.exists(sel[0]): self.tree.selection_set(sel[0])

    def run_selected(self):
        sel = self.tree.selection()
        if not self.ws or not sel or sel[0].startswith('g_'): return
        extra = shlex.split(self.extra.get()) if self.extra.get().strip() else []
        from .runner import run_step
        self._bg(run_step, self.ws, sel[0], extra, self.say, msg=f'running {sel[0]} ...')

    def run_all(self):
        if not self.ws: return
        from .runner import run_ready
        if self.current not in ('run',): self.show('run')
        self._bg(run_ready, self.ws, self.say, msg='running every ready step ...')

    def open_log(self):
        sel = self.tree.selection()
        if self.ws and sel and not sel[0].startswith('g_'):
            p = self.ws.logs / f'{sel[0]}.log'
            open_path(p) if p.exists() else messagebox.showinfo('RC Shop', 'no log yet')

    # ------------------------------------------------------------------ review
    def _page_review(self, p):
        header(p, 'Review', 'check every sheet before it leaves the office')
        pan = ttk.PanedWindow(p, orient='horizontal'); pan.pack(fill='both', expand=True, padx=18, pady=(0, 10))
        left = ttk.Frame(pan, width=360); pan.add(left, weight=0)
        self.outs = ttk.Treeview(left, columns=('st',), show='tree headings')
        self.outs.heading('#0', text='output'); self.outs.heading('st', text='check'); self.outs.column('st', width=60, anchor='center')
        self.outs.tag_configure('OK', foreground=T.OK); self.outs.tag_configure('FAIL', foreground=T.BAD)
        self.outs.pack(fill='both', expand=True)
        self.outs.bind('<<TreeviewSelect>>', lambda e: self._preview_out())
        b = ttk.Frame(left); b.pack(fill='x', pady=6)
        ttk.Button(b, text='Run check', command=lambda: self._run_step('check')).pack(side='left')
        ttk.Button(b, text='Open file', command=self._open_out).pack(side='left', padx=4)
        nb = ttk.Frame(left); nb.pack(fill='x', pady=(0, 6))
        ttk.Button(nb, text='◀ sheet', command=lambda: self._sheet(-1)).pack(side='left')
        self.sheet_lbl = ttk.Label(nb, text='', width=12, anchor='center'); self.sheet_lbl.pack(side='left')
        ttk.Button(nb, text='sheet ▶', command=lambda: self._sheet(1)).pack(side='left')
        ttk.Button(nb, text='all', command=lambda: self.prev.fit()).pack(side='left', padx=4)
        self.rev_info = ttk.Label(left, text='', style='Muted.TLabel', wraplength=340, justify='left'); self.rev_info.pack(anchor='w')
        from .canvasview import DrawingView
        self.prev = DrawingView(pan, on_status=lambda s: None); pan.add(self.prev, weight=1)
        self._prev_models = {}

    def _show_review(self):
        if not self.ws: return
        rep = {}
        cp = self.ws.logs / 'check.txt'
        if cp.exists():
            for ln in cp.read_text(encoding='utf-8').splitlines():
                parts = ln.split()
                if len(parts) > 1 and parts[0] in ('OK', 'FAIL'):
                    rep[parts[1]] = (parts[0], ln)
        self._rep = rep
        sel = self.outs.selection()
        self.outs.delete(*self.outs.get_children())
        for f in self.ws.outputs():
            rel = str(f.relative_to(self.ws.work / 'out')).replace('\\', '/')
            st = rep.get(rel, ('', ''))[0]
            self.outs.insert('', 'end', iid=rel, text=rel, values=(st or '-',), tags=(st,) if st else ())
        if sel and self.outs.exists(sel[0]): self.outs.selection_set(sel[0])

    def _preview_out(self):
        sel = self.outs.selection()
        if not self.ws or not sel: return
        rel = sel[0]
        self.rev_info.config(text=self._rep.get(rel, ('', 'not checked yet'))[1])
        path = self.ws.work / 'out' / rel
        def work():
            from .drawing import DrawingModel
            m = self._prev_models.get(rel) or DrawingModel(path, log=self.say)
            self._prev_models[rel] = m
            self.after(0, lambda: self._prev_loaded(m))
        self.busy_start(f'opening {rel}')
        threading.Thread(target=work, daemon=True).start()

    def _prev_loaded(self, m):
        self.busy_end()
        x0, y0, x1, y1 = m.extents()
        big = (x1 - x0) > 100000                                 # A0 sheets (1:200) are stacked every 172000
        self._sh = (237800, 168200, 172000) if big else (42000, 29700, 32000)
        self._n_sheets = max(1, int(round(-min(y0, 0) / self._sh[2])) + 1)
        self._sheet_i = 0
        self.prev.set_model(m, self._sheet_win(0)); self._sheet(0)

    def _sheet_win(self, i):
        W, H, step = self._sh
        return (-W * 0.01, -i * step - H * 0.01, W * 1.01, -i * step + H * 1.01)

    def _sheet(self, d):
        if not getattr(self, '_n_sheets', 0): return
        self._sheet_i = max(0, min(self._n_sheets - 1, self._sheet_i + d))
        self.sheet_lbl.config(text=f'{self._sheet_i + 1} / {self._n_sheets}')
        if d: self.prev.fit(self._sheet_win(self._sheet_i))

    def _open_out(self):
        sel = self.outs.selection()
        if self.ws and sel: open_path(self.ws.work / 'out' / sel[0])

    def _run_step(self, sid):
        if not self.ws: return
        from .runner import run_step
        self._bg(run_step, self.ws, sid, (), self.say, msg=f'running {sid} ...')

    # ------------------------------------------------------------------ deliver
    def _page_deliver(self, p):
        header(p, 'Deliver', 'zip parts under the size limit, one folder per package / zone')
        c = card(p); b = tk.Frame(c, bg=T.CARD); b.pack(fill='x', padx=12, pady=10)
        ttk.Button(b, text='Pack the delivery', style='Accent.TButton', command=lambda: self._run_step('package')).pack(side='left')
        ttk.Button(b, text='Open deliveries folder', command=lambda: self.ws and open_path(self.ws.deliveries)).pack(side='left', padx=6)
        c = card(p, 'Deliveries', fill='both', expand=True)
        self.dlv = ttk.Treeview(c, columns=('mb',), show='tree headings')
        self.dlv.heading('#0', text='file'); self.dlv.heading('mb', text='MB'); self.dlv.column('mb', width=80, anchor='e')
        self.dlv.pack(fill='both', expand=True, padx=12, pady=(0, 12))

    def _show_deliver(self):
        if not self.ws: return
        self.dlv.delete(*self.dlv.get_children())
        for z in sorted(self.ws.deliveries.glob('*.zip'), reverse=True):
            self.dlv.insert('', 'end', text=z.name, values=(f'{z.stat().st_size / 1e6:.1f}',))

    # ------------------------------------------------------------------ profiles
    def _page_profiles(self, p):
        header(p, 'Reading profiles', 'how each consultant draws: layers, blocks, label patterns, views')
        c = card(p, fill='both', expand=True)
        ttk.Label(c, text='A profile is saved from a project whose drawing has been taught, and applied to the next project '
                          'of the same consultant. Schedules, levels and title-block values never go into a profile.',
                  style='CardMuted.TLabel', wraplength=900, justify='left').pack(anchor='w', padx=12)
        self.prof = ttk.Treeview(c, columns=('src', 'note'), show='tree headings', height=10)
        self.prof.heading('#0', text='profile'); self.prof.heading('src', text='saved from'); self.prof.heading('note', text='keys')
        self.prof.pack(fill='both', expand=True, padx=12, pady=8)
        b = tk.Frame(c, bg=T.CARD); b.pack(fill='x', padx=12, pady=(0, 12))
        ttk.Button(b, text='Save this project as a profile', style='Accent.TButton', command=self.save_profile).pack(side='left')
        ttk.Button(b, text='Apply to this project', command=self.apply_profile).pack(side='left', padx=6)

    def _show_profiles(self):
        self.prof.delete(*self.prof.get_children())
        from .paths import PROFILES_DIR
        for name in profiles.list_profiles():
            try:
                d = json.loads((PROFILES_DIR / f'{name}.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                d = {}
            self.prof.insert('', 'end', iid=name, text=name, values=(d.get('source', ''), ', '.join(d.get('keys', {}))))

    def save_profile(self):
        if not self.ws: return
        name = askstring('RC Shop', 'Profile name (consultant / office):', parent=self)
        if name:
            try:
                profiles.save_from(self.ws, name); self.say(f'profile "{name}" saved'); self._show_profiles()
            except Exception as e:
                messagebox.showwarning('RC Shop', str(e))

    def apply_profile(self):
        if not self.ws or not self.prof.selection(): return
        name = self.prof.selection()[0]
        wrote = profiles.apply_to(self.ws, name)
        self.say(f'profile {name}: {len(wrote)} keys written ({", ".join(wrote)})'); self.refresh_all()

    # ------------------------------------------------------------------ settings
    LABELS = {'engine_dir': 'Engine folder (holds gen.py)', 'engine_python': 'Python for the engine (empty = built in)',
              'oda_converter': 'ODA File Converter (.exe)', 'dwg2dxf': 'LibreDWG dwg2dxf', 'max_zip_mb': 'Delivery part limit (MB)'}

    def _page_settings(self, p):
        header(p, 'Settings', 'saved for this user, all projects')
        c = card(p); g = tk.Frame(c, bg=T.CARD); g.pack(fill='x', padx=12, pady=12)
        s = settings(); self.setvars = {}
        for i, (k, lab) in enumerate(self.LABELS.items()):
            ttk.Label(g, text=lab, style='Card.TLabel').grid(row=i, column=0, sticky='w', pady=4)
            v = tk.StringVar(value=str(s.get(k, DEFAULTS[k]))); self.setvars[k] = v
            ttk.Entry(g, textvariable=v, width=80).grid(row=i, column=1, sticky='we', padx=8)
            if k != 'max_zip_mb':
                ttk.Button(g, text='...', width=3, command=lambda k=k: self._browse(k)).grid(row=i, column=2)
        g.columnconfigure(1, weight=1)
        ttk.Button(c, text='Save settings', style='Accent.TButton', command=self._save_settings).pack(anchor='e', padx=12, pady=(0, 12))

    def _browse(self, k):
        p = filedialog.askdirectory() if k == 'engine_dir' else filedialog.askopenfilename()
        if p: self.setvars[k].set(p)

    def _save_settings(self):
        s = settings()
        for k, v in self.setvars.items():
            s[k] = int(v.get() or 30) if k == 'max_zip_mb' else v.get().strip()
        save_settings(s); self.say('settings saved')


def main(project=None):
    App(project).mainloop()
    return 0
