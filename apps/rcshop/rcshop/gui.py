"""RC Shop window: project, drawings, data files, modules, reading profiles, the pipeline steps and the log."""
import json, os, queue, subprocess, sys, threading, traceback
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from . import __version__, profiles, validate
from .paths import settings, save_settings, DEFAULTS
from .steps import MODULES
from .workspace import Workspace

COLORS = {'done': '#1b7f3b', 'ready': '#1f5fbf', 'stale': '#b36b00', 'blocked': '#888888', 'failed': '#c62828'}


def open_path(p):
    p = str(p)
    if sys.platform.startswith('win'):
        os.startfile(p)                                       # noqa: the Windows shell opens folders / files
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', p])


class JsonEditor(tk.Toplevel):
    """edit one data file; saved only when it is valid JSON"""
    def __init__(self, master, path, on_save):
        super().__init__(master)
        self.path, self.on_save = Path(path), on_save
        self.title(f'{self.path.name} - RC Shop'); self.geometry('820x640')
        bar = ttk.Frame(self); bar.pack(fill='x')
        ttk.Button(bar, text='Save', command=self.save).pack(side='left', padx=4, pady=4)
        ttk.Button(bar, text='Check JSON', command=self.check).pack(side='left')
        self.msg = ttk.Label(bar, text=str(self.path)); self.msg.pack(side='left', padx=8)
        self.txt = ScrolledText(self, font=('Consolas', 10), undo=True); self.txt.pack(fill='both', expand=True)
        self.txt.insert('1.0', self.path.read_text(encoding='utf-8') if self.path.exists() else '{\n}\n')

    def check(self):
        try:
            json.loads(self.txt.get('1.0', 'end')); self.msg.config(text='valid JSON', foreground='#1b7f3b'); return True
        except ValueError as e:
            self.msg.config(text=f'error: {e}', foreground='#c62828')
            if getattr(e, 'lineno', None):
                self.txt.see(f'{e.lineno}.0'); self.txt.tag_remove('err', '1.0', 'end')
                self.txt.tag_add('err', f'{e.lineno}.0', f'{e.lineno}.end'); self.txt.tag_config('err', background='#ffd6d6')
            return False

    def save(self):
        if not self.check(): return
        data = json.loads(self.txt.get('1.0', 'end'))
        self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
        self.msg.config(text='saved', foreground='#1b7f3b'); self.on_save()


class SettingsDialog(tk.Toplevel):
    LABELS = {'engine_dir': 'Engine folder (holds gen.py)', 'engine_python': 'Python for the engine (empty = built in)',
              'oda_converter': 'ODA File Converter (.exe)', 'dwg2dxf': 'LibreDWG dwg2dxf', 'max_zip_mb': 'Delivery part limit (MB)'}

    def __init__(self, master):
        super().__init__(master); self.title('Settings - RC Shop'); self.resizable(True, False)
        s = settings(); self.vars = {}
        for i, (k, lab) in enumerate(self.LABELS.items()):
            ttk.Label(self, text=lab).grid(row=i, column=0, sticky='w', padx=6, pady=3)
            v = tk.StringVar(value=str(s.get(k, DEFAULTS[k]))); self.vars[k] = v
            ttk.Entry(self, textvariable=v, width=60).grid(row=i, column=1, sticky='we', padx=4)
            if k != 'max_zip_mb':
                ttk.Button(self, text='...', width=3, command=lambda k=k: self.browse(k)).grid(row=i, column=2)
        ttk.Button(self, text='Save', command=self.save).grid(row=len(self.LABELS), column=1, sticky='e', pady=6)
        self.columnconfigure(1, weight=1)

    def browse(self, k):
        p = filedialog.askdirectory() if k == 'engine_dir' else filedialog.askopenfilename()
        if p: self.vars[k].set(p)

    def save(self):
        s = settings()
        for k, v in self.vars.items():
            s[k] = int(v.get() or 30) if k == 'max_zip_mb' else v.get().strip()
        save_settings(s); self.destroy()


class App(tk.Tk):
    def __init__(self, project=None):
        super().__init__()
        self.title(f'RC Shop {__version__} - Span Tech'); self.geometry('1280x820'); self.minsize(1000, 640)
        self.ws, self.busy, self.q = None, False, queue.Queue()
        self._build()
        if project:
            self.load(project)
        self.after(100, self._poll)

    # ------------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self); top.pack(fill='x', padx=6, pady=4)
        ttk.Button(top, text='New project', command=self.new_project).pack(side='left')
        ttk.Button(top, text='Open project', command=self.open_project).pack(side='left', padx=4)
        ttk.Button(top, text='Settings', command=lambda: SettingsDialog(self)).pack(side='left')
        self.lbl = ttk.Label(top, text='no project open', font=('Segoe UI', 11, 'bold')); self.lbl.pack(side='left', padx=12)

        pan = ttk.PanedWindow(self, orient='vertical'); pan.pack(fill='both', expand=True, padx=6)
        upper = ttk.PanedWindow(pan, orient='horizontal'); pan.add(upper, weight=4)

        nb = ttk.Notebook(upper); upper.add(nb, weight=2)
        # drawings
        f = ttk.Frame(nb); nb.add(f, text='Drawings')
        self.dwg = tk.Listbox(f, height=8); self.dwg.pack(fill='both', expand=True, padx=4, pady=4)
        b = ttk.Frame(f); b.pack(fill='x')
        ttk.Button(b, text='Add DWG / DXF', command=self.add_drawing).pack(side='left', padx=2)
        ttk.Button(b, text='Set as main', command=self.set_main).pack(side='left', padx=2)
        ttk.Button(b, text='Survey report', command=lambda: self.open_rel('survey/survey.md')).pack(side='left', padx=2)
        # data files
        f = ttk.Frame(nb); nb.add(f, text='Data files')
        self.data = ttk.Treeview(f, columns=('state', 'what'), show='tree headings', height=8)
        self.data.heading('#0', text='file'); self.data.heading('state', text=''); self.data.heading('what', text='holds')
        self.data.column('#0', width=140); self.data.column('state', width=70); self.data.column('what', width=360)
        self.data.pack(fill='both', expand=True, padx=4, pady=4)
        self.data.bind('<Double-1>', lambda e: self.edit_data())
        b = ttk.Frame(f); b.pack(fill='x')
        ttk.Button(b, text='Edit', command=self.edit_data).pack(side='left', padx=2)
        ttk.Button(b, text='project.json from survey draft', command=self.from_draft).pack(side='left', padx=2)
        ttk.Button(b, text="What's missing?", command=self.show_problems).pack(side='left', padx=2)
        # modules
        f = ttk.Frame(nb); nb.add(f, text='Modules')
        self.modvars = {}
        for m, d in MODULES.items():
            v = tk.BooleanVar(); self.modvars[m] = v
            ttk.Checkbutton(f, text=f'{m}: {d}', variable=v, command=self.modules_changed,
                            state='disabled' if m == 'core' else 'normal').pack(anchor='w', padx=6, pady=1)
        # profiles
        f = ttk.Frame(nb); nb.add(f, text='Reading profiles')
        ttk.Label(f, text='How a consultant draws (layers, blocks, labels, views) - reused for his next project.',
                  wraplength=420).pack(anchor='w', padx=4, pady=4)
        self.prof = tk.Listbox(f, height=8); self.prof.pack(fill='both', expand=True, padx=4)
        b = ttk.Frame(f); b.pack(fill='x', pady=2)
        ttk.Button(b, text='Save this project as profile', command=self.save_profile).pack(side='left', padx=2)
        ttk.Button(b, text='Apply to this project', command=self.apply_profile).pack(side='left', padx=2)

        # steps
        right = ttk.Frame(upper); upper.add(right, weight=3)
        self.tree = ttk.Treeview(right, columns=('status', 'detail'), show='tree headings')
        self.tree.heading('#0', text='step'); self.tree.heading('status', text='status'); self.tree.heading('detail', text='')
        self.tree.column('#0', width=470); self.tree.column('status', width=70, anchor='center'); self.tree.column('detail', width=300)
        for st, c in COLORS.items():
            self.tree.tag_configure(st, foreground=c)
        self.tree.pack(fill='both', expand=True, pady=(4, 2))
        b = ttk.Frame(right); b.pack(fill='x')
        self.btn_run = ttk.Button(b, text='Run step', command=self.run_selected); self.btn_run.pack(side='left', padx=2)
        ttk.Label(b, text='args:').pack(side='left'); self.extra = ttk.Entry(b, width=18); self.extra.pack(side='left')
        self.btn_all = ttk.Button(b, text='Run all ready', command=self.run_all); self.btn_all.pack(side='left', padx=6)
        ttk.Button(b, text='Refresh', command=self.refresh).pack(side='left')
        ttk.Button(b, text='Output folder', command=lambda: self.open_rel('out')).pack(side='right', padx=2)
        ttk.Button(b, text='Deliveries', command=lambda: self.ws and open_path(self.ws.deliveries)).pack(side='right', padx=2)

        self.log = ScrolledText(pan, height=12, font=('Consolas', 9), state='disabled'); pan.add(self.log, weight=2)

    # ------------------------------------------------------------------ project
    def new_project(self):
        d = filedialog.askdirectory(title='Folder for the new project (empty)')
        if not d: return
        self.load(Workspace.create(d).root)

    def open_project(self):
        d = filedialog.askdirectory(title='Project folder (holds rcshop.json)')
        if d: self.load(d)

    def load(self, d):
        try:
            self.ws = Workspace(d)
        except Exception as e:
            messagebox.showerror('RC Shop', str(e)); return
        self.lbl.config(text=f'{self.ws.name}   ({self.ws.root})')
        for m, v in self.modvars.items():
            v.set(m in self.ws.modules)
        self.refresh()

    def modules_changed(self):
        if self.ws:
            self.ws.set_modules([m for m, v in self.modvars.items() if v.get()]); self.refresh()

    def refresh(self):
        if not self.ws: return
        self.dwg.delete(0, 'end')
        for n in self.ws.drawings():
            self.dwg.insert('end', n + ('   [main]' if n == self.ws.meta.get('main_dxf') else ''))
        self.data.delete(*self.data.get_children())
        for n, what, ok in self.ws.data_files():
            self.data.insert('', 'end', iid=n, text=n, values=('present' if ok else 'missing', what))
        self.prof.delete(0, 'end')
        for p in profiles.list_profiles():
            self.prof.insert('end', p)
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        groups = {}
        for s in self.ws.steps():
            if s.group not in groups:
                groups[s.group] = self.tree.insert('', 'end', iid='g_' + s.group, text=s.group.upper(), open=True)
            st, det = self.ws.status(s)
            self.tree.insert(groups[s.group], 'end', iid=s.id, text=f'{s.id}  -  {s.title}', values=(st, det), tags=(st,))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])

    # ------------------------------------------------------------------ drawings / data
    def add_drawing(self):
        if not self.ws: return
        fs = filedialog.askopenfilenames(filetypes=[('Drawings', '*.dwg *.dxf'), ('All', '*.*')])
        if fs:
            self._bg(self._add, fs)

    def _add(self, fs):
        from .convert import to_dxf
        for f in fs:
            src = self.ws.add_input(f)
            dxf = to_dxf(src, self.ws.work, log=self.say)
            if not self.ws.meta.get('main_dxf'):
                self.ws.set_main(dxf.name)
            self.say(f'added {dxf.name}')

    def set_main(self):
        if self.ws and self.dwg.curselection():
            self.ws.set_main(self.dwg.get(self.dwg.curselection()[0]).split()[0]); self.refresh()

    def open_rel(self, rel):
        if self.ws:
            p = self.ws.work / rel
            open_path(p) if p.exists() else messagebox.showinfo('RC Shop', f'{rel} does not exist yet')

    def edit_data(self):
        if not self.ws or not self.data.selection(): return
        JsonEditor(self, self.ws.work / self.data.selection()[0], self.refresh)

    def from_draft(self):
        try:
            p = validate.new_from_draft(self.ws); self.refresh(); JsonEditor(self, p, self.refresh)
        except Exception as e:
            messagebox.showwarning('RC Shop', str(e))

    def show_problems(self):
        if not self.ws: return
        p = validate.problems(self.ws)
        messagebox.showinfo('What is missing', '\n'.join(p) if p else 'Nothing missing for the selected modules.')

    def save_profile(self):
        if not self.ws: return
        name = simple_input(self, 'Profile name (consultant / office):')
        if name:
            try:
                profiles.save_from(self.ws, name); self.refresh()
            except Exception as e:
                messagebox.showwarning('RC Shop', str(e))

    def apply_profile(self):
        if not self.ws or not self.prof.curselection(): return
        name = self.prof.get(self.prof.curselection()[0])
        wrote = profiles.apply_to(self.ws, name)
        self.say(f'profile {name}: {len(wrote)} keys written to project.json ({", ".join(wrote)})'); self.refresh()

    # ------------------------------------------------------------------ running
    def run_selected(self):
        sel = self.tree.selection()
        if not self.ws or not sel or sel[0].startswith('g_'): return
        import shlex
        extra = shlex.split(self.extra.get()) if self.extra.get().strip() else []
        from .runner import run_step
        self._bg(run_step, self.ws, sel[0], extra, self.say)

    def run_all(self):
        if not self.ws: return
        from .runner import run_ready
        self._bg(run_ready, self.ws, self.say)

    def _bg(self, fn, *a):
        if self.busy:
            messagebox.showinfo('RC Shop', 'a step is still running'); return
        self.busy = True
        for b in (self.btn_run, self.btn_all): b.state(['disabled'])
        def work():
            try:
                fn(*a)
            except Exception as e:
                self.say(f'ERROR: {e}\n{traceback.format_exc()}')
            self.q.put(('done', None))
        threading.Thread(target=work, daemon=True).start()

    def say(self, s):
        self.q.put(('log', str(s)))

    def _poll(self):
        try:
            while True:
                kind, s = self.q.get_nowait()
                if kind == 'log':
                    self.log.config(state='normal'); self.log.insert('end', s + '\n'); self.log.see('end'); self.log.config(state='disabled')
                else:
                    self.busy = False
                    for b in (self.btn_run, self.btn_all): b.state(['!disabled'])
                    self.refresh()
        except queue.Empty:
            pass
        self.after(100, self._poll)


def simple_input(master, prompt):
    from tkinter.simpledialog import askstring
    return askstring('RC Shop', prompt, parent=master)


def main(project=None):
    App(project).mainloop()
    return 0
