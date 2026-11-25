"""GRADE BEAMS of one zone - section-sheet package (CONC DIM, PLAN, SOG, TYPICAL, [CURVED], one sheet per group of identical
beams, BBS) from the extracted beam lines of every part of the zone (extc.py), with the GB schedule of the config
(continuous + ADDITIONAL bars: top at the supports, bottom at midspan; stirrups @support / @midspan).
usage: GBZ_CONFIG=cfg.json python3 build.py <zone> <first sheet no>
Everything project / zone specific comes from the config (gbzone.example.json documents every key).

NOTES (generic version of the project pipeline; drawing behaviour unchanged for the modern zones):
- kept behind zone flags (defaults = modern behaviour): strict_grouping (False = legacy grouping: same type / width / number
  of spans, spans within legacy_tol), hook, free_ends, drop_pieces, pack_detail, post, merge_c_tol (was 60 for one zone,
  30 elsewhere), bubbles_off_texts, use_eng_marks, wing_marks (auto marks of the parts P2.. for multi-part zones), curves,
  curve_marks ('convex' / 'above'), curve_drop_labels, scale.
- file driven (used when the file exists in <root>/<zone>/): line_edits.json (+ CGB labels from the plan), curves.json,
  secnames.json, eng_marks.json, eng_add.json, sog_eng.json.
- dropped (one-off branches of the first zones): post_r02 legacy plan base (union outline + automatic axes / chained
  dimensions instead of the consultant geometry and face-to-face dims), the engineer R03 plan block / shift file and the SOG
  panels read from the engineer's labels (one zone, one revision); the zone-specific RFI captions of the SOG sheet are now
  zones.<zone>.sog_note; revision rows are zones.<zone>.rev_rows.
- extc.py replaces ext.py / env GB_BASE / GB_SRC: base_deg + parts in the config.
"""
import json, os, sys, string, subprocess, pickle, copy, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from gbzcfg import Cfg, WORK
Z = sys.argv[1]; K = Cfg(Z); ZC = K.z; ZN = K.ZN; FIRST = int(sys.argv[2])
REV, DATE = ZC['rev'], ZC['date']
PARTS = K.parts()
if ZC.get('hook'): os.environ['GB_HOOK'] = str(ZC['hook'])
W = K.builddir(); os.makedirs(W, exist_ok=True)
# ---- GB schedule
SCH = {k: dict(v) for k, v in K.C['schedule'].items() if not k.startswith('_')}
BH = int(K.get('beam_h', 600)); TOP = int(K.get('top_gb', 850)); DEF = K.get('default_type', 'GB2'); CANT = K.get('cantilever_type', 'CGB')
HL = round(BH / 10)
for v in SCH.values(): v['h'] = v.get('h', BH)
area_ = lambda t: SCH[t]['nb'] * SCH[t]['db'] ** 2 + SCH[t]['nba'] * SCH[t]['dba'] ** 2 + SCH[t]['nt'] * SCH[t]['dt'] ** 2 + SCH[t]['nta'] * SCH[t]['dta'] ** 2
LJ, PJ = {}, {}
REM, held, DROPPED = {}, {}, []
for pn in PARTS:
    P = K.partdir(pn); PJ[pn] = json.load(open(P + '/part.json')); LJ[pn] = json.load(open(P + '/lines.json'))[pn]
    PJ[pn]['src'] = K.rotsrc(pn)
if os.path.exists(K.zdir('line_edits.json')):                   # engineer markups on the plan (a beam drawn / extended by the engineer)
    for ed in json.load(open(K.zdir('line_edits.json'))):
        l = next(x for x in LJ[ed['part']] if x['o'] == ed['o'] and abs(x['c'] - ed['c']) < 60 and abs(x[ed['end']] - ed['at']) < 100)
        l[ed['end']] = ed['to']; l['L'] = round(l['b'] - l['a']); l['sup'] = sorted(l['sup'] + ed.get('sup', []), key=lambda q: q['s0']); l['tlab'] = l.get('tlab', []) + [tuple(t) for t in ed.get('tlab', [])]
        for t in ed.get('tlab', []): l['types'][t[0]] = l['types'].get(t[0], 0) + 1
        REM[l['code']] = ed['note']
    for pn in PARTS:                                            # cantilever labels (cantilever end of a GB line) -> span label
        labs = pickle.load(open(K.partdir(pn) + '/plans.pkl', 'rb'))[pn]['labs']
        for t in labs:
            if not t[0].startswith(CANT): continue
            cand = [x for x in LJ[pn] if (x['o'] == 'H' and x['a'] - 300 <= t[1] <= x['b'] + 300 and abs(x['c'] - t[2]) < 900) or (x['o'] == 'V' and x['a'] - 300 <= t[2] <= x['b'] + 300 and abs(x['c'] - t[1]) < 900)]
            if cand:
                x = min(cand, key=lambda x: abs(x['c'] - (t[2] if x['o'] == 'H' else t[1])))
                x['tlab'] = x.get('tlab', []) + [(t[0], round(t[1] if x['o'] == 'H' else t[2]))]
sys.path.insert(0, WORK); os.environ['RC_PROJECT'] = K.p(K.get('project_json', 'project.json')); sys.argv_ = sys.argv; sys.argv = ['x']
import gen_gbsec as G_
sys.argv = sys.argv_
# ---- curved grade beams -> developed lines (far from the plan, own sections; marks drawn by post on the curve)
CURVED = bool(ZC.get('curves', True)) and os.path.exists(K.zdir('curves.json'))
SUPB = f'{DEF} 200x{BH} (SUPPORTING BEAM)'
if CURVED:
    for i, cv in enumerate(json.load(open(K.zdir('curves.json')))):
        sup = [dict(q) for q in cv['sup']]; L0 = cv['L']; sh = 0
        if not sup or sup[0]['s0'] > 50:                         # start not on a column: on the beam / column face drawn -> 200 support
            sh = 200; sup = [dict(s0=0, s1=200, lab=SUPB, beam=True)] + [dict(q, s0=q['s0'] + sh, s1=q['s1'] + sh) for q in sup]
        elif sup[0]['s1'] - sup[0]['s0'] < 100:
            sh = 300; sup = [dict(s0=0, s1=300, lab='COL (CURVE START)')] + [dict(q, s0=q['s0'] + sh, s1=q['s1'] + sh) for q in sup[1:]]
        L = L0 + sh
        if sup[-1]['s1'] < L - 50: sup.append(dict(s0=L, s1=L + 200, lab=SUPB, beam=True)); L += 200
        tl = [(t, s + sh) for t, s in cv['tlab'] if not any(d_ in t for d_ in ZC.get('curve_drop_labels', [])) or cv['w'] < 250]
        typs = {}
        for t, _ in tl: typs[t] = typs.get(t, 0) + 1
        LJ[PARTS[0]].append(dict(o='H', c=-400000 - 4000 * i, w=cv['w'], a=0, b=L, L=round(L), sup=sup, cross=[], core=False, types=typs, tlab=tl,
                                 levels=[], lev_at=[], code=cv['code'], curved=True))
# ---- one beam broken by a crossing beam (collinear pieces, gap = the crossing width) -> one line, the junction a support
MERGED = []
CTOL = ZC.get('merge_c_tol', 30)
for pn in list(LJ):
    ls = LJ[pn]
    changed = True
    while changed:
        changed = False
        for l1 in ls:
            for l2 in ls:
                if l1 is l2 or l1['o'] != l2['o'] or abs(l1['c'] - l2['c']) > 60 or abs(l1['w'] - l2['w']) > 10: continue
                gap = l2['a'] - l1['b']
                shared = gap < -300 and l2['a'] > l1['a'] and any(abs(q['s0'] - r['s0']) <= 50 and q['s0'] - 50 <= l2['a'] and l1['b'] <= q['s1'] + 50 for q in l1['sup'] for r in l2['sup'])   # two beams ending on the same column = one line
                if abs(l1['c'] - l2['c']) > CTOL and not shared: continue
                if not (-300 <= gap <= 700) and not shared: continue
                xb = [m for m in ls if m['o'] != l1['o'] and m['c'] - m['w'] / 2 - 30 <= l1['b'] and m['c'] + m['w'] / 2 + 30 >= l2['a']
                      and m['a'] - l1['w'] / 2 - 60 <= l1['c'] <= m['b'] + l1['w'] / 2 + 60]
                m = xb[0] if xb else None
                sup = l1['sup'] + [q for q in l2['sup'] if all(abs(q['s0'] - r['s0']) > 50 for r in l1['sup'])]                       # the beam framing in rests on this one: a crossing, not a support
                tt = dict(l1.get('types', {}))
                for k, v in l2.get('types', {}).items(): tt[k] = tt.get(k, 0) + v
                l1.update(b=max(l1['b'], l2['b']), L=round(max(l1['b'], l2['b']) - l1['a']), sup=sorted(sup, key=lambda q: q['s0']), cross=sorted(l1['cross'] + ([dict(s0=l1['b'], s1=l2['a'], w=m['w'])] if m else []) + l2['cross'], key=lambda q: q['s0']),
                          types=tt, tlab=l1.get('tlab', []) + l2.get('tlab', []), merged=l1.get('merged', [l1['code']]) + l2.get('merged', [l2['code']]))
                ls.remove(l2); MERGED.append((pn, l1['merged'])); changed = True; break
            if changed: break
for pn, lines in LJ.items():
    for l in lines:
        l['w'] = 200 if abs(l['w'] - 200) <= 8 else (300 if abs(l['w'] - 300) <= 8 else l['w'])
        labs = [t for t in l.get('types', {}) if re.match(r'^GB\d', t)]
        typs = sorted({t.split('-')[0] for t in labs})
        if not typs:
            l['typ'] = DEF; REM[l['code']] = f'NO CODE ON THE PLAN -> {DEF} (MOST COMMON IN THE ZONE) - RFI'
        else:
            l['typ'] = max(typs, key=area_)
            if len(typs) > 1: REM[l['code']] = f"LABELS {'+'.join(sorted(set(labs)))} -> {l['typ']} (LARGER STEEL)"
            ws = {int(t.split('-')[1].split('X')[0]) * 10 for t in labs if '-' in t}
            if l['w'] not in ws and ws: REM[l['code']] = (REM.get(l['code'], '') + '; ' if l['code'] in REM else '') + f"DRAWN {l['w']} vs LABEL {'/'.join(map(str, sorted(ws)))} - DRAWN USED"
        l['labels'] = sorted(set(labs)); l['top'] = TOP
        for q in l['sup']:
            if q['lab'] == '?': q['lab'] = "COL {}X{} (NO LABEL)".format(*sorted((round((q['x1'] - q['x0']) / 10), round((q['y1'] - q['y0']) / 10))))
# ---- GB type per clear span (label inside the span); an unlabelled span = continuation of the previous one
for pn, lines in LJ.items():
    for l in lines:
        sp = sorted(l['sup'], key=lambda q: q['s0']); st = []
        for q, r in zip(sp, sp[1:]):
            inn = [t[0].split('-')[0] for t in l.get('tlab', []) if q['s0'] - 300 <= t[1] <= r['s1'] + 300 and re.match(r'^(GB\d|' + re.escape(CANT) + ')', t[0])]
            inn = [t for t in inn if t in SCH]
            st.append(CANT if CANT in inn else (max(inn, key=area_) if inn else None))
        for i in range(len(st)):
            if st[i] is None and i > 0: st[i] = st[i - 1]
        for i in range(len(st) - 1, -1, -1):
            if st[i] is None and i < len(st) - 1: st[i] = st[i + 1]
        st = [t or l['typ'] for t in st]
        l['span_typ'] = st
        if st: l['typ'] = max(set(st), key=area_)
# ---- ends on a beam of ANOTHER wing (other rotation): found in the original plan coordinates
from shapely.geometry import Point as _Pt, box as _bx
from shapely.affinity import rotate as _rot
def _rect(l): return _bx(l['a'], l['c'] - l['w'] / 2, l['b'], l['c'] + l['w'] / 2) if l['o'] == 'H' else _bx(l['c'] - l['w'] / 2, l['a'], l['c'] + l['w'] / 2, l['b'])
ORECT = {(pn, l['code']): _rot(_rect(l), PJ[pn]['ang'], origin=(0, 0)) for pn in LJ for l in LJ[pn]}
XWING = []
for pn in LJ:
    for l in LJ[pn]:
        for end in ('a', 'b'):
            e = l[end]
            if any(q['s0'] - 60 <= e <= q['s1'] + 60 for q in l['sup']): continue
            if G_.beam_ends(dict(l, sup=l['sup'] + [dict(lab='x', s0=l['a' if end == 'b' else 'b'] - 1, s1=l['a' if end == 'b' else 'b'] + 1)]), LJ[pn], SCH) is not None: continue
            pt = _rot(_Pt((e, l['c']) if l['o'] == 'H' else (l['c'], e)), PJ[pn]['ang'], origin=(0, 0))
            hit = [(k, r) for k, r in ORECT.items() if k[0] != pn and r.buffer(120).contains(pt)]
            if not hit: continue
            (pn2, c2), r2 = hit[0]; l2 = next(x for x in LJ[pn2] if x['code'] == c2)
            sg = 1 if end == 'b' else -1; s0, s1 = sorted((e, e + sg * l2['w']))
            l['sup'] = sorted(l['sup'] + [dict(lab=f"{l2['typ']} {l2['w']}x{BH} (SUPPORTING BEAM, {pn2})", s0=s0, s1=s1, beam=True)], key=lambda q: q['s0'])
            l[end] = s0 if end == 'a' else s1; l['L'] = round(l['b'] - l['a']); XWING.append(f"{l['code']} end {end} on {c2}")
for pn, lines in LJ.items():
    keep = []
    for l in lines:
        if not l['sup'] and l['b'] - l['a'] < 1000: DROPPED.append(l['code']); continue
        keep.append(l)
    LJ[pn] = keep
    for l in keep:
        r = G_.beam_ends(l, keep, SCH)
        if r is None:
            ends_ok = all(any(q['s0'] - 60 <= l[e] <= q['s1'] + 60 for q in l['sup']) for e in ('a', 'b'))
            if not ends_ok: held[l['code']] = 'END NOT ON A COLUMN / BEAM - RFI'
        clear = (l['b'] - l['a']) - sum(min(q['s1'], l['b']) - max(q['s0'], l['a']) for q in l['sup'] if q['s1'] > l['a'] and q['s0'] < l['b'])
        if l['code'] not in held and clear < 300: held[l['code']] = 'COLUMN ONLY, NO BEAM SPAN'
FEN = K.get('free_end_note', '')
if ZC.get('free_ends', True):                                    # free ends classified on the plan
    for pn in LJ:
        for l in LJ[pn]:
            if held.get(l['code']) != 'END NOT ON A COLUMN / BEAM - RFI': continue
            res = []
            for end in ('a', 'b'):
                e = l[end]
                if any(q['s0'] - 60 <= e <= q['s1'] + 60 for q in l['sup']): continue
                bl = G_.beam_ends(dict(l, sup=l['sup'] + [dict(lab='x', s0=l['a' if end == 'b' else 'b'] - 1, s1=l['a' if end == 'b' else 'b'] + 1)]), LJ[pn], SCH)
                if bl is not None: res.append(f'END {end.upper()} ON A BEAM'); continue
                sg = -1 if end == 'a' else 1                          # a beam crossed just before the end: supported, short overhang beyond it
                xs = [q for q in LJ[pn] if q['o'] != l['o'] and q['a'] - q['w'] / 2 - 80 <= l['c'] <= q['b'] + q['w'] / 2 + 80 and 0 < sg * (e - q['c']) <= 600]
                if xs:
                    q = min(xs, key=lambda q: abs(e - q['c']))
                    l['sup'] = sorted(l['sup'] + [dict(lab=f"{q['typ']} {q['w']}x{BH} (SUPPORTING BEAM)", s0=q['c'] - q['w'] / 2, s1=q['c'] + q['w'] / 2, beam=True)], key=lambda r: r['s0'])
                    res.append(f"END {end.upper()} ON BEAM {q['code']} + OVERHANG {round(abs(e - q['c']) - q['w'] / 2)}"); continue
                res.append(f'END {end.upper()} FREE = CANTILEVER')
            if all('FREE' not in r for r in res): held.pop(l['code']); REM[l['code']] = '; '.join(res) + FEN
            else: held[l['code']] = 'CANTILEVER - ' + '; '.join(res) + FEN
if ZC.get('drop_pieces', True):                                  # pieces that are only the column at a wing junction, or a piece inside another line -> not beams
    from shapely.geometry import box as _b2
    _r = lambda l: _b2(l['a'], l['c'] - l['w'] / 2, l['b'], l['c'] + l['w'] / 2) if l['o'] == 'H' else _b2(l['c'] - l['w'] / 2, l['a'], l['c'] + l['w'] / 2, l['b'])
    for pn in LJ:
        keep = []
        for l in LJ[pn]:
            dup = any(m is not l and m['o'] == l['o'] and _r(l).intersection(_r(m).buffer(60)).area > 0.8 * _r(l).area and m['L'] > l['L'] for m in LJ[pn])
            if held.get(l['code'], '').startswith('COLUMN ONLY') or dup:
                DROPPED.append(l['code'] + (' (DUPLICATE PIECE)' if dup else ' (COLUMN ONLY)')); held.pop(l['code'], None); continue
            keep.append(l)
        LJ[pn] = keep
for pn in LJ:
    for l in LJ[pn]:
        if l['code'] in held: l['held'] = held[l['code']]
json.dump(LJ, open(W + '/lines_final.json', 'w'), indent=1)
# ---------------------------------------------------------------- sheets
letters = list(string.ascii_uppercase) + [a + b for a in string.ascii_uppercase for b in string.ascii_uppercase]
t1 = K.fmt(K.get('t1', 'GRADE BEAMS - ZONE {zone}'))
DWGP = K.get('dwg_pattern', '{prj}-GB-{zone}-{no}-{rev}')
dwg = lambda no: K.fmt(DWGP, no=no, rev=REV)
base = dict(date=ZC['sheet_date'], rev=REV, area=K.get('area', 'GB'), venue=ZN, t1=t1)
P1 = PJ[PARTS[0]]; WIN = P1['win']
OFF = (0, -80000)
SC = ZC.get('scale', 125)
cd = dict(kind='cd', tab=f'{ZN}-GB-{FIRST} CONC DIM', window=[WIN[0] + OFF[0], WIN[1] + OFF[1], WIN[2] + OFF[0], WIN[3] + OFF[1]], scale=SC,
          t2='CONCRETE DIMENSIONS PLAN', seq=str(FIRST), dwg=dwg(FIRST), **base)
plan = dict(kind='plan', tab=f'{ZN}-GB-{FIRST + 1} PLAN', window=WIN, scale=SC, t2='REINFORCEMENT PLAN', seq=str(FIRST + 1), dwg=dwg(FIRST + 1), **base)
NSEC0 = FIRST + (5 if CURVED else 4)                            # FIRST+2 SOG plan, FIRST+3 typical details, [FIRST+4 curved beams] (post_r02.py)
sheets, li, no = [], 0, NSEC0
order = [(pn, l) for pn in PARTS for l in sorted([x for x in LJ[pn] if x['code'] not in held], key=lambda l: (l['o'] != 'H', -l['c'] if l['o'] == 'H' else l['c'], l['a']))]
order += [(pn, l) for pn in PARTS for l in LJ[pn] if l['code'] in held]          # no beam left out - held lines detailed last, RFI on the sheet
SECFIX = json.load(open(K.zdir('secnames.json'))) if os.path.exists(K.zdir('secnames.json')) else {}
GROUPS = []                                                   # similar beams
STRICT = bool(ZC.get('strict_grouping', True))                # one detail = identical beams only (length, spans, supports, steel)
TOL = ZC.get('group_tol', 25) if STRICT else ZC.get('legacy_tol', 500)
def _geo(pn, l):
    L = G_.beam_ends(l, LJ[pn], SCH) or l
    sup = sorted(L['sup'], key=lambda q: q['s0'])
    return [r['s0'] - q['s1'] for q, r in zip(sup, sup[1:])], L['b'] - L['a']
def _sig(pn, l):
    L = G_.beam_ends(l, LJ[pn], SCH) or l
    return [(round(q['s1'] - q['s0']), q.get('beam', False)) for q in sorted(L['sup'], key=lambda q: q['s0'])]
for pn, l in order:
    sp, ln_ = _geo(pn, l)
    for g in GROUPS:
        if g['typ'] == l['typ'] and g['w'] == l['w'] and len(g['sp']) == len(sp) and ((g['st'] == l.get('span_typ') and all(abs(a - b) <= TOL for a, b in zip(g['sp'], sp))) or (g['st'] == l.get('span_typ', [])[::-1] and all(abs(a - b) <= TOL for a, b in zip(g['sp'], sp[::-1])))):
            if STRICT:
                sg_ = _sig(pn, l)
                if abs(g['len'] - ln_) > TOL or not (all(abs(a[0] - b[0]) <= TOL and a[1] == b[1] for a, b in zip(g['sig'], sg_)) or all(abs(a[0] - b[0]) <= TOL and a[1] == b[1] for a, b in zip(g['sig'], sg_[::-1]))) or len(g['sig']) != len(sg_): continue
            g['all'].append((ln_, pn, l)); break
    else: GROUPS.append(dict(typ=l['typ'], w=l['w'], sp=sp, st=l.get('span_typ'), all=[(ln_, pn, l)], len=ln_, sig=_sig(pn, l)))
for g in GROUPS:
    g['all'].sort(key=lambda t: -t[0]); _, g['pn'], g['l'] = g['all'][0]; g['members'] = [t[2]['code'] for t in g['all']]
for g in GROUPS:
    pn, l = g['pn'], g['l']
    sec, xs = letters[li], letters[li + 1]; li += 2
    fx = [SECFIX[c] for c in g['members'] if c in SECFIX]           # section names as marked on the plan by the engineer
    if fx: sec = fx[0]; xs = letters[letters.index(sec) + 1]
    nm = len(g['members'])
    sheets.append(dict(plan=pn, line=l['code'], members=g['members'], sec=sec, xsec=xs, tab=f'{ZN}-GB-{no} {sec}-{sec} {l["typ"]}',
                       t2=f'{l["typ"]} {l["w"]}x{BH} - SECTION {sec}-{sec}' + (f' ({nm} No.)' if nm > 1 else ''), seq=str(no), dwg=dwg(no), **base)); no += 1
print('GROUPS', len(GROUPS), 'from', len(order), 'lines')
last = no - 1; BBS0 = no
plan['caption'] = f'GRADE BEAM REINFORCEMENT PLAN - ZONE {ZN} (DRAWN ROTATED {P1["ang"]:.2f} DEG: BEAMS ORTHOGONAL) - SECTIONS {NSEC0} TO {last}, BBS FROM {BBS0}'
cd['caption'] = f'GRADE BEAM CONCRETE DIMENSIONS PLAN - ZONE {ZN} (CONCRETE ONLY - REINFORCEMENT ON SHEETS {FIRST + 1} TO {last})'
_lv = dict(top=f'{TOP / 1000:+.2f}', bot=f'{(TOP - BH) / 1000:+.2f}', h=BH)
cd['legend'] = [K.fmt(s, **_lv) for s in K.get('cd_legend', ['T.O.GB {top}, B.O.GB {bot} (h {h}).', 'b = PLAN WIDTH (200 / 300), h = GB SCHEDULE DEPTH {h}.', 'DIMENSIONS IN mm, LEVELS IN m.'])]
A6 = json.load(open(K.p(K.C['layout_json'])))
C = {k: A6[k] for k in ('layout', 'scales', 'prefer_side', 'model_origin', 'top_lap', 'right_margin_th', 'text_style', 'dxfversion')}
C['strict'] = STRICT; C['notes'] = True; C['blsc'] = True; C['pack_detail'] = bool(ZC.get('pack_detail', True)); C['eng_layout'] = True; C['bbs_k'] = K.get('bbs_k', 0.0125)
C['rev_row'] = [list(r) for r in ZC.get('rev_rows', [])]
C['scales'] = list(C['scales']) + [100, 125]
FR = K.get('frame', {})
C['frame'] = dict(A6['frame']); C['frame'].update(dxf=P1['src'], block=FR.get('block', 'LAY'), block_dxf=K.p(FR['block_dxf']) if FR.get('block_dxf') else A6['frame'].get('block_dxf'),
                                                    defaults=dict(dict(ref=K.fmt(K.get('ref_text', 'ZONE {zone}.dxf')), area=K.get('area', 'GB'), venue=ZN, rev=REV, date=DATE), **{k: K.fmt(v) for k, v in FR.get('defaults', {}).items()}))
if FR.get('title'): C['frame']['title'] = FR['title']
C.update(schedule=SCH, columns={}, levels={'top_gb': TOP}, sheets=[cd, plan] + sheets, held=held, remarks=REM, plan_copy={'window': [WIN]}, plan_marks=[PARTS[0]],
         bbs_seq=BBS0, bbs_dwg=K.fmt(K.get('bbs_dwg', DWGP), no='{no}', rev='{rev}'), tab_prefix=f'{ZN}-GB-', summary_title=K.fmt(K.get('summary_title', 'SUMMARY - GRADE BEAMS ZONE {zone}')),
         cd_copy={'offset': list(OFF), 'text_h': 190}, summary_d=tuple(K.get('summary_d', (8, 14, 16))), bbs_fields=dict(base))
json.dump(C, open(W + '/gbsec.json', 'w'), indent=1)
print('MERGED', MERGED); print('XWING', XWING); print(len(sheets), 'section sheets', FIRST + 2, '..', last, '| BBS from', BBS0, '| held', len(held), '| remarks', len(REM), '| dropped', DROPPED)
for k, v in held.items(): print('  HOLD', k, v)
for k, v in REM.items(): print('  REM ', k, v)
OUTF = K.out_file(FIRST); os.makedirs(os.path.dirname(OUTF), exist_ok=True)
r = subprocess.run(['python3', os.path.join(WORK, 'gen_gbsec.py'), W + '/lines_final.json', W + '/gbsec.json', OUTF], capture_output=True, text=True, cwd=W)
print(r.stdout[-2500:], r.stderr[-2500:])
if ZC.get('post', True):
    r = subprocess.run(['python3', os.path.join(HERE, 'post_r02.py'), OUTF, str(FIRST), Z], capture_output=True, text=True); print(r.stdout[-3000:], r.stderr[-3000:])
