import sys, ezdxf, os
from collections import Counter
f = sys.argv[1]; doc = ezdxf.readfile(f)
print('version', doc.dxfversion, doc.acad_release, 'units', doc.units)
au = doc.audit(); print('audit errors', len(au.errors), 'fixes', len(au.fixes))
OK = {'LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'HATCH', 'INSERT', 'DIMENSION', 'VIEWPORT', 'SOLID', 'POINT'}
types = Counter(); bad = Counter(); miss = Counter(); styles = Counter()
lays = {l.dxf.name for l in doc.layers}; lts = {l.dxf.name.upper() for l in doc.linetypes}; sts = {s.dxf.name.upper() for s in doc.styles}
blks = {b.name for b in doc.blocks}; dss = {d.dxf.name for d in doc.dimstyles}
def chk(e, ours):
    t = e.dxftype(); types[t] += 1
    if t not in OK: bad[t] += 1
    if e.dxf.layer not in lays: miss['layer:' + e.dxf.layer] += 1
    lt = e.dxf.get('linetype', 'BYLAYER').upper()
    if lt not in ('BYLAYER', 'BYBLOCK') and lt not in lts: miss['ltype:' + lt] += 1
    if t in ('TEXT', 'MTEXT'):
        if e.dxf.get('style', 'STANDARD').upper() not in sts: miss['style:' + e.dxf.style] += 1
        if ours and e.dxf.layer.startswith('GB-'): styles[e.dxf.get('style', 'Standard')] += 1
    if t == 'INSERT' and e.dxf.name not in blks: miss['block:' + e.dxf.name] += 1
    if t == 'DIMENSION' and e.dxf.get('dimstyle', 'Standard') not in dss: miss['dimstyle:' + e.dxf.dimstyle] += 1
    if e.xdata is not None or e.has_extension_dict: miss['xdata/extdict:' + t] += 1
for lay in doc.layouts:
    for e in lay: chk(e, True)
for b in doc.blocks:
    if b.name.lower().startswith(('*model', '*paper')): continue
    for e in b: chk(e, False)
print('entities', sum(types.values()), dict(types))
print('non-plain types', dict(bad) or 'none'); print('unresolved / extra data', dict(miss) or 'none')
print('our text styles', dict(styles)); print('dimension text style', {d.dxf.name: d.dxf.get('dimtxsty') for d in doc.dimstyles if d.dxf.name.startswith('GBSEC')}.get('GBSEC50'))
print('layouts', len([l for l in doc.layouts]) - 1, '| size MB', round(os.path.getsize(f) / 1e6, 2))
