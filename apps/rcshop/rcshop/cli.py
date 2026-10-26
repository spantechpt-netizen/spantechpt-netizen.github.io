"""Command line (also what the GUI does underneath):

  rcshop new <dir> [--name N] [--modules gb,footings,...]
  rcshop add <dir> <drawing.dwg|dxf> [--main]       copy, convert, make it the main drawing
  rcshop status <dir>
  rcshop check <dir>                                 what project.json / data files still miss
  rcshop draft <dir>                                 project.json from the survey draft
  rcshop run <dir> <step> [-- engine args]           one step (e.g. run P zone_fnd -- "AREA 2")
  rcshop run <dir> --all                             every ready / stale step in order
  rcshop profile save|apply|list <dir> [name]
  rcshop gui [dir]
  rcshop engine <script> [args]                      (internal) run an engine script in this process
"""
import sys

from .steps import MODULES, BY_ID


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__); return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == 'engine':
        from .runner import run_engine_inline
        run_engine_inline(rest[0], rest[1:]); return 0
    if cmd == 'gui':
        from .gui import main as gui_main
        return gui_main(rest[0] if rest else None)
    from .workspace import Workspace
    if cmd == 'new':
        name = rest[rest.index('--name') + 1] if '--name' in rest else ''
        mods = rest[rest.index('--modules') + 1].split(',') if '--modules' in rest else []
        ws = Workspace.create(rest[0], name)
        ws.set_modules(mods); print('project', ws.root, 'modules', ws.modules); return 0
    ws = Workspace(rest[0])
    if cmd == 'add':
        from .convert import to_dxf
        src = ws.add_input(rest[1])
        dxf = to_dxf(src, ws.work)
        if '--main' in rest or not ws.meta.get('main_dxf'):
            ws.set_main(dxf.name)
        print('drawing', dxf.name, '(main)' if ws.meta.get('main_dxf') == dxf.name else ''); return 0
    if cmd == 'status':
        print(f'{ws.name}  modules: {", ".join(ws.modules)}')
        for s in ws.steps():
            st, det = ws.status(s)
            print(f'  {s.id:13s} {st:8s} {s.title}' + (f'  [{det}]' if det else ''))
        return 0
    if cmd == 'check':
        from .validate import problems
        p = problems(ws)
        print('\n'.join(p) if p else 'nothing missing'); return 1 if p else 0
    if cmd == 'draft':
        from .validate import new_from_draft
        print(new_from_draft(ws)); return 0
    if cmd == 'run':
        from .runner import run_step, run_ready
        if rest[1] == '--all':
            run_ready(ws); return 0
        extra = rest[rest.index('--') + 1:] if '--' in rest else []
        if rest[1] not in BY_ID:
            print('unknown step; steps:', ', '.join(BY_ID)); return 2
        return run_step(ws, rest[1], extra)
    if cmd == 'profile':
        from . import profiles
        sub = rest[1] if len(rest) > 1 else 'list'
        if sub == 'list': print('\n'.join(profiles.list_profiles())); return 0
        if sub == 'save': print(profiles.save_from(ws, rest[2])); return 0
        if sub == 'apply': print('keys written:', profiles.apply_to(ws, rest[2])); return 0
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main())
