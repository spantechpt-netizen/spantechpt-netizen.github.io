"""configuration of one Zone 7 part (P2 as issued, P3), same rules as Part 2 R00."""
import json, string, sys
W_, PN, FRAME_DXF, first_no, letters_from, date = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5], sys.argv[6]
LF = json.load(open(f'{W_}/lines_final_{PN}.json')); L = {l['code']: l for l in LF[PN]}
raw = {l['code']: l for l in json.load(open(W_ + '/lines.json'))[PN]}
C = json.load(open(W_ + '/cfg_base.json'))
spec = json.load(open(f'{W_}/spec_{PN}.json'))                        # part-specific decisions (merges, starters, window)
out = list(LF[PN])
for mg in spec.get('under_wall_self', []):                             # the beam itself runs on under the core wall (one line on the plan)
    g = raw[mg['line']]; q = next(q for q in g['sup'] if q['lab'].startswith('CORE'))
    m = dict(g, typ=mg['typ'], labels=[mg['typ']], top=850, cross=[],
             sup=[x for x in g['sup'] if not x['lab'].startswith('CORE')] + [dict(lab='CORE 1 WALL ABOVE', s0=q['s0'], s1=q['s1'], under_wall=True, wt=g['w'], openings=mg.get('openings', []))])
    for x in m['sup']:
        if x['lab'] == '?': x['lab'] = "COL {}X{} (NO LABEL)".format(*sorted((round((x['x1'] - x['x0']) / 10), round((x['y1'] - x['y0']) / 10))))
    m['sup'].sort(key=lambda x: x['s0'])
    out = [m if l['code'] == mg['line'] else l for l in out]
for mg in spec.get('merge_under_wall', []):                            # RFI-16: beam under the core wall + the beam reaching it
    g_out, g_in = raw[mg['outer']], raw[mg['inner']]
    m = dict(g_out, code=mg['outer'], b=max(g_out['b'], g_in['b']) if mg.get('dir', 1) > 0 else g_out['b'], typ='GB1', labels=['GB1'], top=850, cross=[],
             sup=[q for q in g_out['sup'] if not q['lab'].startswith('CORE')] + [dict(lab='CORE 1 WALL ABOVE', s0=g_in['a'], s1=g_in['b'], under_wall=True, wt=g_in['w'])])
    if mg.get('dir', 1) < 0: m['a'] = min(g_out['a'], g_in['a'])
    m['sup'].sort(key=lambda q: q['s0']); m['L'] = round(m['b'] - m['a'])
    out = [m if l['code'] == mg['outer'] else l for l in out if l['code'] != mg['inner']]
for mg in spec.get('merge_broken', []):                                 # one beam drawn broken where two beams meet it
    a_, b_ = next(l for l in out if l['code'] == mg[0]), next(l for l in out if l['code'] == mg[1])
    m = dict(a_, b=b_['b'], sup=a_['sup'] + b_['sup'], cross=a_.get('cross', []) + mg[2]); m['L'] = round(m['b'] - m['a'])
    out = [m if l['code'] == mg[0] else l for l in out if l['code'] != mg[1]]
sb = dict(kind='column', d=16, leg=200, lap_d=65, per_pos=2, zone=1400, s=185, end=50)
for st_code in spec.get('starters', []):
    st = next(l for l in out if l['code'] == st_code)
    face = next(q['face'] for q in st['sup'] if q.get('core')); sg = 1 if st['b'] <= face + 400 else -1   # beam runs toward the core: +
    sg = 1 if abs(st['b'] - next(q['s1'] for q in st['sup'] if q.get('core'))) < 5 else -1
    st['starters_abs'] = [(face - sg * (sb['end'] + i * sb['s']), 'UP') for i in range(8)]
    st.update(starter_kind='column', starter_lap=sb['lap_d'] * sb['d'], starter_lap_d=sb['lap_d'], starter_zone=sb['zone'], starter_foot=sb['leg'])
sched = C['schedule']['GB2']; Lc = sb['leg'] + (sched['h'] - 40 - sched['ds']) + sb['lap_d'] * sb['d']
LF[PN] = out
i0 = string.ascii_uppercase.index(letters_from[0])
letters = [a + b for a in string.ascii_uppercase[i0:] for b in string.ascii_uppercase]
codes = [l['code'] for l in out if not l.get('held')]
frame = C['frame']; frame['block_dxf'] = FRAME_DXF; frame['block'] = 'ST_FRAME'; frame['defaults'].update(rev='00', date=date)
pno = 'PART ' + PN[1]
plan = dict(kind='plan', tab=f'Z07-GB-{first_no} PLAN {PN}', window=spec['plan_window'], scale=spec.get('plan_scale', 75), t1='GROUND BEAMS - ZONE 7',
            t2=f'REINFORCEMENT PLAN - {pno}', dwg=f'NVMNR2-SD-STCO.-STR-Z07-GB-{first_no}-00', seq=str(first_no), rev='00')
sheets, li, no = [], 0, first_no + 1
for c in codes:
    l = next(x for x in out if x['code'] == c); t = l['typ']; sec, xs = letters[li], letters[li + 1]; li += 2
    sheets.append(dict(plan=PN, line=c, sec=sec, xsec=xs, tab=f'Z07-GB-{no} {sec}-{sec} {t}', t1='GROUND BEAMS - ZONE 7', t2=f'{t} - SECTION {sec}-{sec}',
                       dwg=f'NVMNR2-SD-STCO.-STR-Z07-GB-{no}-00', seq=str(no), rev='00')); no += 1
    if c in spec.get('starters', []):
        st = next(x for x in out if x['code'] == c)
        ssec = letters[li]; li += 2
        st['starter_ref'] = f"STAIR STARTERS: 16 T16-{Lc} (8 @{sb['s']} x 2), SEE SECTION {ssec}-{ssec} (SHEET {no})"
        sheets.append(dict(plan=PN, kind='starter', line=c, sec=ssec, xsec=letters[li - 1], parent_sec=f'{sec}-{sec}', tab=f'Z07-GB-{no} {ssec}-{ssec} STARTERS',
                           t1='GROUND BEAMS - ZONE 7', t2=f'STAIR STARTER BARS - SECTION {ssec}-{ssec}', dwg=f'NVMNR2-SD-STCO.-STR-Z07-GB-{no}-00', seq=str(no), rev='00')); no += 1
last = no - 1
plan['caption'] = f'GRADE BEAM REINFORCEMENT PLAN - ZONE 7 ({pno}) - SECTIONS ON SHEETS {first_no + 1} TO {last}, BBS FROM {last + 1}'
C.update(sheets=[plan] + sheets, held={c: l['held'] for c, l in ((l['code'], l) for l in out) if l.get('held')}, plan_copy={'window': [spec['copy_window']]},
         plan_marks=[PN], bbs_seq=last + 1, bbs_dwg='NVMNR2-SD-STCO.-STR-Z07-GB-{no}-00', starter_bar=sb, starter_scales=[5, 15],
         notes=False, layout={'x0': 12, 'aw': 712, 'ah': 568}, scales=[20, 25, 30, 35, 40, 45, 50], prefer_side=True,
         text_style={'name': 'ROMANS', 'font': 'arial.ttf'}, model_origin=[320000, 170000], dxfversion='R2010',
         plan_dims=spec.get('plan_dims', []))
C['starter_scales'] = spec.get('starter_scales', [5, 15])
json.dump(LF, open(f'{W_}/lines_final_{PN}.json', 'w'), indent=1); json.dump(C, open(f'{W_}/gbsec_{PN}.json', 'w'), indent=1)
print(len(sheets), 'section sheets', first_no + 1, '..', last, '| BBS from', last + 1, '| starter L', Lc, '| held', C['held'])
