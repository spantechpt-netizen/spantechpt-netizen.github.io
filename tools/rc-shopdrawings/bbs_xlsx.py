"""BBS workbook with formulas from the generators' exports (out/*.bbs.json, written by BarList.export).

    python3 bbs_xlsx.py BBS.xlsx out/FOOTINGS.bbs.json out/NECKS.bbs.json [...]

One sheet per element group (isolated footings / combined footings / rafts / column necks / other), one row per
(element type, bar mark): drawing number, element, mark, diameter, shape code + segment lengths, quantity, cutting
length, total length = qty x L, unit weight = d^2 / 162, weight = total length x unit weight (Excel formulas). A summary
sheet totals every diameter per group and the grand total with SUMIFS, so editing a quantity updates everything.
Net engineering quantities only: no waste allowance is added.
"""
import json, re, sys
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SHAPE = {'S': 'STRAIGHT', 'U': 'U-BAR', 'L': 'L-BAR', 'POLY': 'TIE (CLOSED, 2 HOOKS 135)', 'HT': 'STIRRUP (2 HOOKS 135)',
         'ST': 'CLOSED LOOP (LAPPED)', 'CH': 'CHAIR', 'OPEN': 'OPEN BAR', 'PROF': 'BENT BAR (PROFILE)'}


def group_of(el):
    if ' ON ' in el: return 'Column necks'
    if el.upper().startswith('CF'): return 'Combined footings'
    if el.upper().startswith('RAFT'): return 'Rafts'
    if el.upper().startswith('F'): return 'Isolated footings'
    return 'Other'


def segs(shape):
    kind, rest = shape[0], shape[1:]
    if kind == 'POLY':                                   # tie: out-to-out sides
        pts = [tuple(p) for p in rest]
        import math
        return [round(math.dist(pts[i], pts[(i + 1) % len(pts)])) for i in range(len(pts))][:6]
    return [v for v in rest if isinstance(v, (int, float))][:6]


def main(out, files):
    rows = []
    for fn in files:
        d = json.load(open(fn))
        for r in d['rows']:
            for el, q in r.get('use', {'?': r['n_in'] * r['n_el']}).items():
                rows.append(dict(dwg=d['dwg'].get(el, ''), el=el, mark=r['mark'], src=fn, d=r['d'], shape=r['shape'],
                                 q=q, L=r['L'], layer=r.get('layer', '')))
    wb = Workbook(); wb.remove(wb.active)
    hdr = Font(bold=True, color='FFFFFF'); fill = PatternFill('solid', fgColor='1D3557'); thin = Side(style='thin', color='999999')
    head = ['Drawing No.', 'Element', 'Bar mark', 'Dia (mm)', 'Shape', 'A', 'B', 'C', 'D', 'E', 'F', 'Quantity',
            'Cutting length (mm)', 'Total length (m)', 'Unit weight (kg/m) = d²/162', 'Total weight (kg)', 'Layer / note', 'Source']
    groups = ['Isolated footings', 'Combined footings', 'Rafts', 'Column necks', 'Other']
    used = []
    for g in groups:
        rs = [r for r in rows if group_of(r['el']) == g]
        if not rs: continue
        used.append(g)
        ws = wb.create_sheet(g[:31]); ws.append(head)
        for c in ws[1]: c.font = hdr; c.fill = fill; c.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
        for i, r in enumerate(sorted(rs, key=lambda r: (r['dwg'], r['mark'])), 2):
            sg = segs(r['shape']) + [None] * 6
            ws.append([r['dwg'], r['el'], f"{r['mark']:02d}", r['d'], SHAPE.get(r['shape'][0], r['shape'][0])] + sg[:6] +
                      [r['q'], r['L'], f'=L{i}*M{i}/1000', f'=D{i}^2/162', f'=N{i}*O{i}', r['layer'], r['src']])
            ws[f'N{i}'].number_format = '0.00'; ws[f'O{i}'].number_format = '0.000'; ws[f'P{i}'].number_format = '#,##0.00'
        n = ws.max_row
        ws.append(['TOTAL'] + [''] * 12 + [f'=SUM(N2:N{n})', '', f'=SUM(P2:P{n})'])
        ws[f'P{n + 1}'].number_format = '#,##0.00'; ws[f'N{n + 1}'].number_format = '0.00'
        for c in ws[n + 1]: c.font = Font(bold=True)
        for row in ws.iter_rows():
            for c in row: c.border = Border(top=thin, bottom=thin, left=thin, right=thin)
        for j, w in enumerate([30, 22, 8, 8, 24, 7, 7, 7, 7, 7, 7, 9, 12, 12, 14, 14, 14, 22], 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = 'C2'
    # summary by diameter and group (formulas)
    dias = sorted(set(r['d'] for r in rows))
    ws = wb.create_sheet('Summary', 0)
    ws.append(['Diameter (mm)', 'Unit weight (kg/m)'] + [f'{g} (kg)' for g in used] + ['Total (kg)', 'Total (t)'])
    for c in ws[1]: c.font = hdr; c.fill = fill; c.alignment = Alignment(wrap_text=True, horizontal='center', vertical='center')
    for i, d in enumerate(dias, 2):
        cells = [f"=SUMIFS('{g[:31]}'!P:P,'{g[:31]}'!D:D,A{i})" for g in used]
        last = get_column_letter(2 + len(used))
        ws.append([d, f'=A{i}^2/162'] + cells + [f'=SUM(C{i}:{last}{i})', f'={get_column_letter(3 + len(used))}{i}/1000'])
    n = ws.max_row
    ws.append(['TOTAL', ''] + [f'=SUM({get_column_letter(3 + j)}2:{get_column_letter(3 + j)}{n})' for j in range(len(used) + 2)])
    for c in ws[n + 1]: c.font = Font(bold=True)
    for row in ws.iter_rows(min_row=2):
        for c in row[1:]: c.number_format = '#,##0.00'
    for j in range(1, len(used) + 5): ws.column_dimensions[get_column_letter(j)].width = 18
    ws.cell(n + 3, 1, 'Net engineering quantities (no waste allowance). Weight = quantity x cutting length x d²/162.')
    wb.save(out)
    print(out, len(rows), 'rows', used)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
