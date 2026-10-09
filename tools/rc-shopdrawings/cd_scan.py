"""Concrete-dimension plan: scan the foundation plan window -> cd_scan.pkl
RC outlines (fnd_layers), PC outlines (fnd_pc_layers), columns (fnd_col_layers), footing labels, grid bubbles."""
import json, math, pickle, re, sys
from ezdxf import recover
P = json.load(open('project.json'))
doc, _ = recover.readfile(P.get('dxf', 'main.dxf')); msp = doc.modelspace()
cx, cy, H = P['fnd_view']; W = H * 1.6
X0, X1, Y0, Y1 = cx - W / 2, cx + W / 2, cy - H / 2, cy + H / 2
inw = lambda x, y: X0 < x < X1 and Y0 < y < Y1
RC = tuple(P.get('fnd_layers', ['CORE-FNDN']) + P.get('cd_rc_layers_extra', [])); PC = tuple(P.get('fnd_pc_layers', ['CORE-FNDN-FTNG-PC']))
COL = tuple(P.get('fnd_col_layers', ['CORE-COLS-CONC']))
LBL = re.compile(P.get('footing_label_re', r'(F\d*A?|Fx|CF\d+|FF\d+|RAFT-?\d*|ST-?\d*)'))
out = dict(rc=[], pc=[], col=[], lab=[], ax=[])
def walk(e, d=0, inh=None):
    if inh and e.dxf.layer == '0': e.dxf.layer = inh
    t = e.dxftype()
    if t == 'INSERT':
        if e.dxf.name == P.get('axis_block', 'A-AX') and inw(e.dxf.insert.x, e.dxf.insert.y):
            at = {a.dxf.tag: a.dxf.text for a in e.attribs}
            out['ax'].append((at.get(P.get('axis_family_attr', 'X'), '').upper(), at.get(P.get('axis_attr', '00'), ''), e.dxf.insert.x, e.dxf.insert.y))
        if d < 3:
            try:
                for v in e.virtual_entities(): walk(v, d + 1, e.dxf.layer)
            except Exception: pass
    elif t == 'LINE':                                    # outline edges drawn as single lines (strip faces ...)
        a_, b_ = (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
        if not inw(*a_) or math.dist(a_, b_) < 50: return
        L = e.dxf.layer
        if L.endswith(RC + PC): out.setdefault('open', []).append(([a_, b_], 'pc' if L.endswith(PC) else 'rc'))
    elif t == 'LWPOLYLINE':
        p = [(a, b) for a, b in e.get_points('xy')]
        if len(p) < 2 or not inw(*p[0]): return
        if len(p) == 2:                                   # a 2-point polyline = one outline edge (strip faces ...)
            L = e.dxf.layer
            if L.endswith(RC + PC) and math.dist(p[0], p[1]) >= 50: out.setdefault('open', []).append((p, 'pc' if L.endswith(PC) else 'rc'))
            return
        L = e.dxf.layer
        dx, dy = abs(p[0][0] - p[-1][0]), abs(p[0][1] - p[-1][1])
        # an open outline whose missing side is horizontal / vertical (or tiny) is a closed shape drawn without the
        # flag; closing any other open line would make a diagonal: keep it as a plain line
        closed = e.closed or dx < 5 or dy < 5 or math.hypot(dx, dy) < 300
        if not closed:                                    # open outline pieces: drawn as lines, not elements
            if L.endswith(RC + PC): out.setdefault('open', []).append((p, 'pc' if L.endswith(PC) else 'rc'))
            return
        if L.endswith(RC): out['rc'].append(p)
        elif L.endswith(PC): out['pc'].append(p)
        elif L.endswith(COL): out['col'].append(p)
    elif t in ('TEXT', 'MTEXT'):
        s = (e.plain_text() if t == 'MTEXT' else e.dxf.text).strip()
        if LBL.fullmatch(s) and inw(e.dxf.insert.x, e.dxf.insert.y): out['lab'].append((s, e.dxf.insert.x, e.dxf.insert.y))
for e in msp: walk(e)
pickle.dump(out, open('cd_scan.pkl', 'wb'))
print({k: len(v) for k, v in out.items()})
