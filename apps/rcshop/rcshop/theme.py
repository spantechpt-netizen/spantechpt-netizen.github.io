"""Look of the program: dark nav rail on the left (page + subtitle, like Auto PT Suite), light pages, one accent."""
import sys
import tkinter as tk
from tkinter import ttk

RAIL = '#14202e'; RAIL_HI = '#1f3247'; RAIL_TXT = '#e6edf5'; RAIL_SUB = '#8aa0b6'
ACCENT = '#f28c28'; ACCENT_DK = '#d9741a'
BG = '#f4f6f9'; CARD = '#ffffff'; LINE = '#dde3ea'; TXT = '#1d2733'; MUTED = '#6b7a8a'
OK, WARN, BAD, INFO = '#1b7f3b', '#b36b00', '#c62828', '#1f5fbf'
FONT = 'Segoe UI' if sys.platform.startswith('win') else 'DejaVu Sans'
MONO = 'Consolas' if sys.platform.startswith('win') else 'DejaVu Sans Mono'


def apply(root):
    root.configure(bg=BG)
    s = ttk.Style(root)
    try:
        s.theme_use('clam')
    except tk.TclError:
        pass
    s.configure('.', font=(FONT, 10), background=BG, foreground=TXT)
    s.configure('TFrame', background=BG)
    s.configure('Card.TFrame', background=CARD, relief='flat')
    s.configure('TLabel', background=BG, foreground=TXT)
    s.configure('Card.TLabel', background=CARD)
    s.configure('Muted.TLabel', foreground=MUTED)
    s.configure('CardMuted.TLabel', background=CARD, foreground=MUTED)
    s.configure('H1.TLabel', font=(FONT, 16, 'bold'))
    s.configure('H2.TLabel', font=(FONT, 11, 'bold'))
    s.configure('CardH2.TLabel', font=(FONT, 11, 'bold'), background=CARD)
    s.configure('TButton', padding=(10, 5), background='#e9edf2', bordercolor=LINE)
    s.map('TButton', background=[('active', '#dfe5ec')])
    s.configure('Accent.TButton', background=ACCENT, foreground='white', bordercolor=ACCENT_DK, font=(FONT, 10, 'bold'))
    s.map('Accent.TButton', background=[('active', ACCENT_DK), ('disabled', '#e0b48c')])
    s.configure('Tool.TButton', padding=(6, 3))
    s.configure('Treeview', rowheight=24, fieldbackground=CARD, background=CARD, bordercolor=LINE)
    s.configure('Treeview.Heading', font=(FONT, 9, 'bold'), background='#e9edf2')
    s.map('Treeview', background=[('selected', '#cfe1f7')], foreground=[('selected', TXT)])
    s.configure('TNotebook', background=BG); s.configure('TNotebook.Tab', padding=(12, 5))
    s.configure('TCheckbutton', background=BG); s.configure('Card.TCheckbutton', background=CARD)
    s.configure('Horizontal.TProgressbar', background=ACCENT, troughcolor='#e3e8ee')
    s.configure('TEntry', fieldbackground=CARD); s.configure('TCombobox', fieldbackground=CARD)


class NavRail(tk.Frame):
    """left rail: brand, then one entry per page (title + subtitle); the active one is marked with the accent"""
    def __init__(self, master, pages, on_select):
        super().__init__(master, bg=RAIL, width=210)
        self.pack_propagate(False)
        self.on_select, self.items = on_select, {}
        tk.Label(self, text='RC SHOP', bg=RAIL, fg='white', font=(FONT, 16, 'bold')).pack(anchor='w', padx=18, pady=(18, 0))
        tk.Label(self, text='Span Tech · shop drawings', bg=RAIL, fg=RAIL_SUB, font=(FONT, 9)).pack(anchor='w', padx=18, pady=(0, 16))
        for key, title, sub in pages:
            f = tk.Frame(self, bg=RAIL, cursor='hand2')
            f.pack(fill='x')
            bar = tk.Frame(f, bg=RAIL, width=4); bar.pack(side='left', fill='y')
            box = tk.Frame(f, bg=RAIL); box.pack(side='left', fill='x', expand=True, padx=(12, 6), pady=6)
            t = tk.Label(box, text=title, bg=RAIL, fg=RAIL_TXT, font=(FONT, 10, 'bold'), anchor='w'); t.pack(fill='x')
            s = tk.Label(box, text=sub, bg=RAIL, fg=RAIL_SUB, font=(FONT, 8), anchor='w'); s.pack(fill='x')
            for w in (f, box, t, s):
                w.bind('<Button-1>', lambda e, k=key: self.on_select(k))
                w.bind('<Enter>', lambda e, k=key: self._hover(k, True))
                w.bind('<Leave>', lambda e, k=key: self._hover(k, False))
            self.items[key] = (f, bar, box, t, s)
        self.active = None
        tk.Frame(self, bg=RAIL).pack(fill='both', expand=True)
        self.foot = tk.Label(self, text='', bg=RAIL, fg=RAIL_SUB, font=(FONT, 8), justify='left', anchor='w')
        self.foot.pack(fill='x', padx=18, pady=10)

    def _paint(self, k, bg, bar):
        f, b, box, t, s = self.items[k]
        for w in (f, box, t, s): w.configure(bg=bg)
        b.configure(bg=bar)

    def _hover(self, k, on):
        if k != self.active:
            self._paint(k, RAIL_HI if on else RAIL, RAIL)

    def select(self, k):
        if self.active: self._paint(self.active, RAIL, RAIL)
        self.active = k; self._paint(k, RAIL_HI, ACCENT)
