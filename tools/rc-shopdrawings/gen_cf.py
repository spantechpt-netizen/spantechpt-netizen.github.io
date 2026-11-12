"""All combined footings in ONE file (engineer, 26-10-2026): rectangular CF on the footing sheet (gen_f.draw_sheet),
CF of any outline / with laps on the real-outline sheets (gen_mat.draw_mat), one BarList, one BBS per element.

    python3 gen_cf.py CF60-1 CF80-12 ...        (names in footings.json = rectangular, in mats.json = real outline)
"""
import json, sys
from gen import new_doc, BarList, project_notes, draw_bbs_grouped
import gen_f, gen_mat

PRJ = gen_f.PRJ
if __name__ == '__main__':
    rect = json.load(open('footings.json')); shp = json.load(open('mats.json'))
    names = sys.argv[1:]
    doc = new_doc(); bl = BarList(); dwgmap = {}; idx = 0; rep = []
    for n in names:
        meta = dict(client='', project='', consultant='', contractor='', ref='', author='', checker='', approver='',
                    rev='00', rev_desc='ISSUED FOR APPROVAL', date='', scale='AS SHOWN', prefix='SDW-STR-FDN')
        meta.update(PRJ.get('meta', {}))
        meta['notes'] = project_notes('COVER FOOTINGS 70; PLAIN CONCRETE 100 UNDER FOOTINGS.', 'SIDE BARS INSIDE THE MAIN U-BARS; CH = CHAIRS.')
        bl.cur = n
        if n in rect:
            f = rect[n]
            meta['title'] = f"STRUCTURAL COMBINED FOOTING\nREINFORCEMENT - {n}  (NO={f['no']})"; meta['dwg'] = f'SDW-STR-FDN-{n}'
            gen_f.draw_sheet(doc, idx, f, meta, bl); idx += 2 if f.get('adds') else 1
        else:
            f = shp[n]
            meta['title'] = f"STRUCTURAL COMBINED FOOTING\nREINFORCEMENT - {n}"; meta['dwg'] = f'SDW-STR-FDN-{n}'
            idx += gen_mat.draw_mat(doc, idx, f, meta, bl, rep)
        dwgmap[n] = meta.get('dwg_no', '')
    lib = dict(shp, **rect)
    meta['title'] = 'STRUCTURAL COMBINED FOOTINGS'; meta['dwg'] = 'SDW-STR-FDN'
    nb = draw_bbs_grouped(doc, idx, bl.sorted(), meta, [(f"{n}  (NO={lib[n]['no']})", n, lib[n]['no']) for n in names])
    doc.saveas('out/COMBINED_FOOTINGS.dxf'); bl.export('out/COMBINED_FOOTINGS.bbs.json', dwgmap, {n: lib[n]['no'] for n in names})
    print('sheets', idx, '+ BBS', nb)
    print('\n'.join(rep))
