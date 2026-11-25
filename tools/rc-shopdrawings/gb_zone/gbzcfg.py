"""Config loader shared by extc.py / build.py / post_r02.py / post_curved.py.
The config is ONE JSON file named by env GBZ_CONFIG (see gbzone.example.json for every key).
Relative paths: 'root' relative to the config file's folder, every other path relative to root."""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, 'work')

# zone behaviour flags: defaults = the modern behaviour
FLAG_DEFAULTS = dict(
    strict_grouping=True,      # one detail = identical beams only (length, spans, supports, steel), tol group_tol
    group_tol=25,              # grouping tolerance (mm) with strict_grouping
    legacy_tol=500,            # grouping tolerance (mm) without strict_grouping (same type / width / n spans, spans within)
    hook=100,                  # stirrup hook length (env GB_HOOK of gen_gbsec); 0 = gen_gbsec default max(10 ds, 75)
    free_ends=True,            # classify free ends on the plan (on a beam / overhang past a crossing beam / cantilever)
    drop_pieces=True,          # drop 'column only' pieces and pieces lying inside a longer collinear piece
    pack_detail=True,          # gen_gbsec pack_detail (additional bars packed into fewer detail rows)
    post=True,                 # run post_r02.py (clean plan, CONC DIM, SOG, typical sheet, marks)
    bubbles_off_texts=True,    # move section bubbles off the plan texts (column / beam labels)
    use_eng_marks=True,        # use <zone>/eng_marks.json (engineer's bubble positions) when the file exists
    wing_marks=False,          # automatic section marks for the parts P2.. on the P1-frame plan (without eng_marks)
    curves=True,               # curved beams from <zone>/curves.json when the file exists
    curve_marks='convex',      # curved-beam bubble: 'convex' (bubble outside, caption inside) or 'above' (bubble above, caption below)
    curve_drop_labels=[],      # plan labels ignored on a curved beam wider than 250 (e.g. a label of the straight beam next to it)
    merge_c_tol=30,            # collinear pieces merged into one line when their centre lines are within this (mm)
    scale=125,                 # PLAN / CONC DIM scale
    col_snap=60,               # extraction: beam end snapped to a column within this (mm)
    col_lab_r=2000,            # extraction: column label search radius (mm) when the label must match the size
    base_deg=0.0,              # rotation of the source plan (deg) making the main wing orthogonal
    rev='00', date='', sheet_date=None, rev_rows=[], sog_note='', name=None, src=None,
)

DEFAULT_LAYERS = dict(beam=['S-BEAM', 'S-BEAM-HDLN', 'S-FNDN'], col=['S-COLS'], label=['S-COLS-IDEN', 'S-BEAM-IDEN'],
                      purge_prefixes=['S-', 'A-'])


class Cfg:
    def __init__(self, zone=None, path=None):
        path = path or os.environ.get('GBZ_CONFIG')
        if not path: raise SystemExit('set GBZ_CONFIG=<config.json>')
        self.path = os.path.abspath(path)
        C = json.load(open(self.path)); self.C = C
        self.root = os.path.abspath(os.path.join(os.path.dirname(self.path), C.get('root', '.')))
        self.layers = dict(DEFAULT_LAYERS, **C.get('layers', {}))
        self.zone = zone
        if zone is not None:
            if zone not in C['zones']: raise SystemExit(f'zone {zone!r} not in config zones {list(C["zones"])}')
            z = dict(FLAG_DEFAULTS); z.update(C.get('zone_defaults', {})); z.update(C['zones'][zone]); self.z = z
            self.ZN = z.get('name') or zone.upper()
            if z.get('sheet_date') is None: z['sheet_date'] = z.get('date', '')

    def p(self, rel):                                 # path relative to root
        return rel if os.path.isabs(rel) else os.path.join(self.root, rel)

    def get(self, k, d=None): return self.C.get(k, d)

    def fmt(self, s, **kw):                           # {zone} {ZONE} {prj} + extra fields; unknown fields kept literally
        class _D(dict):
            def __missing__(self, k): return '{' + k + '}'
        d = _D(zone=self.ZN, ZONE=self.ZN, prj=self.C.get('project', 'PRJ'), rev=self.z.get('rev', '00'))
        d.update(kw)
        return s.format_map(d)

    # zone folders
    def zdir(self, *a): return os.path.join(self.root, self.zone, *a)
    def partdir(self, pn): return os.path.join(self.root, f'{self.zone}_{pn}')
    def builddir(self): return os.path.join(self.root, f'{self.zone}_build')
    def rotsrc(self, pn): return os.path.join(self.root, 'src', f'{self.zone}_{pn}.dxf')
    def parts(self): return [p[0] for p in self.z['parts']]
    def out_dir(self): return self.p(self.C.get('out_dir', 'out'))
    def out_file(self, first):
        return os.path.join(self.out_dir(), self.fmt(self.C.get('out_name', '{prj}-GB-{zone}-{first}-R{rev}.dxf'), first=first))
