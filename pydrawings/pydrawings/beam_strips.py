"""
Beam design through RAM Concept, the office way:
  1. `write_beam_strips` rewrites the model's design strips: every span segment, strip boundary, span boundary and
     design section is dropped, and every beam gets one design strip on its centre line per span between its
     supports, with a splitter (strip boundary) on each of its edges, designed as a beam. RAM then analyses and
     designs the beams on Calc All.
  2. `beam_schedule` reads RAM's designed bars and stirrups back off the calculated model, beam by beam, groups
     the beams whose section and reinforcement are alike into types (B1, B2 …), and gives every beam its type,
     section and bars for the plan and the schedule.
The .cpt is an SQLite file: lengths are stored in 0.1 mm, points as `[x][y]`, and every object row sits in a
category with a sibling chain (PreviousSibUID / NextSibUID / ChildIndex).

(Port of shopdrawings/lib/beam-strips.mjs.)
"""
import math
import re
import shutil
import sqlite3

from .geometry import dist, point_in_polygon, bbox, js_round

U = 10  # mm → 0.1 mm


def _js_string(v):
    """`${v}` of JS: a whole float prints without `.0`."""
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, float):
        if v != v:
            return 'NaN'
        if v.is_integer() and abs(v) < 1e21:
            return str(int(v))
    return str(v)


_S = _js_string


def _round(v):
    """Math.round of JS as an integer (a whole number is written to the file / the point text without decimals)."""
    r = js_round(v)
    return int(r) if isinstance(r, float) and r.is_integer() else r


def _pt(p):
    return f"[{_S(_round(p['x'] * U))}][{_S(_round(p['y'] * U))}]"


def _poly(pts):
    return ''.join(f'[{_pt(p)}]' for p in pts)


def _nums(s):
    text = _S(s) if s else ''  # String(s || '')
    return [float(m.group(0)) for m in re.finditer(r'-?\d+(\.\d+)?', text)]


def _point(s):
    v = _nums(s)
    return {'x': (v[0] if len(v) > 0 else float('nan')) / U, 'y': (v[1] if len(v) > 1 else float('nan')) / U}


STRIP_TABLES = ['SpanSegment', 'SpanSegmentStrip', 'SpanBoundary', 'StripBoundary', 'DesignSection', 'SpanSegmentDeflectionCheckDesign', 'SpanDesign', 'DSDesign']


def _table_exists(db, t):
    return bool(db.execute("select name from sqlite_master where type = 'table' and name = ?", (t,)).fetchone())


def _columns_of(db, t):
    return [c[1] for c in db.execute(f'pragma table_info("{t}")').fetchall()]


def _max_uid(db):
    m = 0
    for (name,) in db.execute("select name from sqlite_master where type = 'table'").fetchall():
        if 'UID' not in _columns_of(db, name):
            continue
        r = db.execute(f'select max(UID) as m from "{name}"').fetchone()
        if r and r[0] is not None and r[0] > m:
            m = r[0]
    return m


# The spans of a beam: its axis cut at the supports (columns and walls) it crosses; each span with the support size at its ends.
def size50(v):
    """Beam sizes are written to the nearest 50 mm with no decimals (office convention): 350x600."""
    try:
        n = float(v)  # Number(v)
    except (TypeError, ValueError):
        n = float('nan')
    if n != n or not n:  # (Number(v) || 0)
        n = 0
    return _round(n / 50) * 50


def beam_spans(beam, columns, walls, beams=None):
    if beams is None:
        beams = []
    L = dist(beam['a'], beam['b'])
    u = {'x': (beam['b']['x'] - beam['a']['x']) / L, 'y': (beam['b']['y'] - beam['a']['y']) / L}
    n = {'x': -u['y'], 'y': u['x']}
    along_x = abs(u['x']) >= abs(u['y'])
    supports = []
    for c in columns:
        d = {'x': c['cx'] - beam['a']['x'], 'y': c['cy'] - beam['a']['y']}
        t = d['x'] * u['x'] + d['y'] * u['y']
        off = abs(d['x'] * n['x'] + d['y'] * n['y'])
        along = (c.get('w') or c.get('d') or 300) if along_x else (c.get('h') or c.get('d') or 300)
        across = (c.get('h') or c.get('d') or 300) if along_x else (c.get('w') or c.get('d') or 300)
        if off <= beam['t'] / 2 + across / 2 and t >= -along / 2 and t <= L + along / 2:
            supports.append({'t': max(0, min(L, t)), 'along': along, 'across': across, 'kind': 'column'})
    for w in walls or []:
        # a wall crossing the axis is a support; a wall along the beam is not a span break
        dx, dy = w['b']['x'] - w['a']['x'], w['b']['y'] - w['a']['y']
        den = u['x'] * dy - u['y'] * dx
        if abs(den) < 1e-9:
            continue
        ex, ey = w['a']['x'] - beam['a']['x'], w['a']['y'] - beam['a']['y']
        t = (ex * dy - ey * dx) / den
        s = (ex * u['y'] - ey * u['x']) / den
        if s >= -1e-6 and s <= 1 + 1e-6 and t >= -100 and t <= L + 100:
            supports.append({'t': max(0, min(L, t)), 'along': w.get('t') or 250, 'across': math.hypot(dx, dy), 'kind': 'wall'})
    # a deeper beam crossing this one carries it: it is a support too (office rule), the span breaks at its axis
    for ob in beams or []:
        if ob is beam or ob.get('id') == beam.get('id') or not ob.get('a') or not ob.get('b') or not ((ob.get('depth') or 0) > (beam.get('depth') or 0)):
            continue
        dx, dy = ob['b']['x'] - ob['a']['x'], ob['b']['y'] - ob['a']['y']
        den = u['x'] * dy - u['y'] * dx
        if abs(den) < 1e-9:
            continue
        ex, ey = ob['a']['x'] - beam['a']['x'], ob['a']['y'] - beam['a']['y']
        t = (ex * dy - ey * dx) / den
        s = (ex * u['y'] - ey * u['x']) / den
        if s >= -1e-6 and s <= 1 + 1e-6 and t >= -100 and t <= L + 100:
            supports.append({'t': max(0, min(L, t)), 'along': ob.get('t') or 300, 'across': math.hypot(dx, dy), 'kind': 'beam', 'beam': ob.get('id')})
    supports.sort(key=lambda s: s['t'])
    # merge supports closer than half a metre (a wall meeting a column)
    merged = []
    for s in supports:
        last = merged[-1] if merged else None
        if last and s['t'] - last['t'] < 500:
            last['along'] = max(last['along'], s['along'])
            last['across'] = max(last['across'], s['across'])
        else:
            merged.append({**s})
    cuts = [0, *[t for t in (s['t'] for s in merged) if t > 800 and t < L - 800], L]
    spans = []
    for i in range(len(cuts) - 1):
        t0, t1 = cuts[i], cuts[i + 1]
        if t1 - t0 < 500:
            continue
        s0 = next((s for s in merged if abs(s['t'] - t0) <= 1000), None)
        s1 = next((s for s in merged if abs(s['t'] - t1) <= 1000), None)
        spans.append({
            't0': t0, 't1': t1, 'length': t1 - t0,
            'a': {'x': beam['a']['x'] + u['x'] * t0, 'y': beam['a']['y'] + u['y'] * t0}, 'b': {'x': beam['a']['x'] + u['x'] * t1, 'y': beam['a']['y'] + u['y'] * t1},
            'support0': s0 or None, 'support1': s1 or None,
        })
    return {'spans': spans, 'u': u, 'n': n, 'alongX': along_x, 'spanSet': 'latitude' if along_x else 'longitude', 'supports': merged}


def write_beam_strips(src, out, ram, design_system='beam', splitters=True):
    """
    Rewrites the design strips of a RAM Concept model for beam design. `ram` is the model read with read_ram_concept
    (columns, walls and beams in mm); `src` is copied to `out` and the copy is edited. Returns what was written.
    """
    shutil.copyfile(src, out)
    db = sqlite3.connect(out, isolation_level=None)  # (transactions run by hand: BEGIN / COMMIT / ROLLBACK as the JS)
    summary = {'beams': 0, 'spans': 0, 'splitters': 0, 'removed': {}, 'frames': [], 'missing': []}
    try:
        db.execute('BEGIN')
        uid = _max_uid(db)  # before anything is dropped: a UID is never reused
        for t in STRIP_TABLES:
            if not _table_exists(db, t):
                continue
            summary['removed'][t] = db.execute(f'select count(*) as n from "{t}"').fetchone()[0]
            db.execute(f'delete from "{t}"')

        def cat_of(table, span_set):
            if not _table_exists(db, table):
                return None
            r = db.execute(f'select UID from "{table}" where SpanSet = ?', (span_set,)).fetchone()
            return {'UID': r[0]} if r else None
        seg_cols = _columns_of(db, 'SpanSegment') if _table_exists(db, 'SpanSegment') else None
        if not seg_cols:
            raise ValueError('This model has no design strip tables (SpanSegment); is it a RAM Concept file?')
        defaults = None
        if _table_exists(db, 'DefaultSpanSegment'):
            cur = db.execute('select * from DefaultSpanSegment limit 1')
            r = cur.fetchone()
            defaults = dict(zip([c[0] for c in cur.description], r)) if r else None

        def next_uid():
            nonlocal uid
            uid += 1
            return uid
        chains = {}  # category uid -> [uids]

        def insert_row(table, row):
            info = db.execute(f'pragma table_info("{table}")').fetchall()  # (cid, name, type, notnull, dflt_value, pk)
            full = {'PreviousSibUID': 0, 'NextSibUID': 0, 'ChildIndex': 0, 'Number': 0, **row}
            # every NOT NULL column the row does not carry takes an empty value of its type
            for c in info:
                if c[3] and c[1] not in full:
                    full[c[1]] = 0 if re.search(r'INT|REAL|NUM|DOUB|FLOA', c[2] or '', re.I) else ''
            keys = [k for k in full if any(c[1] == k for c in info)]
            db.execute(f'insert into "{table}" ({",".join(chr(34) + k + chr(34) for k in keys)}) values ({",".join("?" for _ in keys)})', [full[k] for k in keys])
            if row['ParentUID'] not in chains:
                chains[row['ParentUID']] = {'table': table, 'uids': []}
            chains[row['ParentUID']]['uids'].append(row['UID'])
        frame_no = {'latitude': 0, 'longitude': 0}
        for beam in ram.get('beams') or []:
            bs = beam_spans(beam, ram.get('columns') or [], ram.get('walls') or [], ram.get('beams') or [])
            spans, n, span_set = bs['spans'], bs['n'], bs['spanSet']
            if not spans:
                continue
            seg_cat, strip_cat, bound_cat = cat_of('SpanSegmentCategory', span_set), cat_of('SpanSegmentStripCategory', span_set), cat_of('StripBoundaryCategory', span_set)
            if not seg_cat:
                summary['missing'].append(f"{beam['id']}: no {span_set} span segment category")
                continue
            frame = frame_no[span_set]
            frame_no[span_set] += 1
            frame_label = frame + 1
            summary['beams'] += 1
            span_uids = []
            for k, sp in enumerate(spans):
                seg_uid = next_uid()
                span_uids.append(seg_uid)
                s0, s1 = sp.get('support0') or {}, sp.get('support1') or {}
                row = {
                    **(defaults or {}),
                    'UID': seg_uid, 'ParentUID': seg_cat['UID'], 'RssUid': 0, 'Name': f'{frame_label}-{k + 1}', 'DeflectionCheckList': '',
                    'Point0': _pt(sp['a']), 'Point1': _pt(sp['b']), 'SkewAngle': 0, 'SpanSet': span_set, 'FrameNumber': frame, 'SpanNumber': k, 'SegmentNumber': 0,
                    'AtSupport0': 1 if sp.get('support0') else 0, 'AtSupport1': 1 if sp.get('support1') else 0,
                    'SupportWidth0': _round((s0.get('along') or 0) * U), 'SupportWidth1': _round((s1.get('along') or 0) * U),
                    'SupportTransverseWidth0': _round((s0.get('across') or beam['t']) * U), 'SupportTransverseWidth1': _round((s1.get('across') or beam['t']) * U),
                    'AutoSupportDetect': 1, 'LockStripGeneration': 0,
                    'SpanWidthCalc': 'auto', 'ColumnStripWidthCalc': 'full', 'MiddleStripUsesColumnStripProps': 1,
                    'ColumnStripDesignSystem': design_system, 'MiddleStripDesignSystem': design_system,
                    'ColumnStripStirrupLegs': (defaults or {}).get('ColumnStripStirrupLegs') or 2, 'MiddleStripStirrupLegs': (defaults or {}).get('MiddleStripStirrupLegs') or 2,
                }
                insert_row('SpanSegment', row)
                # the strip of the span: the beam's own width (RAM regenerates it on Calc All; written so the model opens with it)
                if strip_cat and _table_exists(db, 'SpanSegmentStrip'):
                    left = [{'x': sp['a']['x'] + n['x'] * beam['t'] / 2, 'y': sp['a']['y'] + n['y'] * beam['t'] / 2}, {'x': sp['b']['x'] + n['x'] * beam['t'] / 2, 'y': sp['b']['y'] + n['y'] * beam['t'] / 2}]
                    right = [{'x': sp['a']['x'] - n['x'] * beam['t'] / 2, 'y': sp['a']['y'] - n['y'] * beam['t'] / 2}, {'x': sp['b']['x'] - n['x'] * beam['t'] / 2, 'y': sp['b']['y'] - n['y'] * beam['t'] / 2}]
                    insert_row('SpanSegmentStrip', {'UID': next_uid(), 'ParentUID': strip_cat['UID'], 'RssUid': 0, 'Name': f'{frame_label}C-{k + 1}', 'Point0': _pt(sp['a']), 'Point1': _pt(sp['b']), 'ResistanceLeftBoundary': _poly(left), 'ResistanceRightBoundary': _poly(right), 'DemandLeftBoundary': _poly(left), 'DemandRightBoundary': _poly(right), 'SpanSegment': seg_uid, 'StripType': 'center', 'AutoTribArea': 0, 'AutoInfluenceArea': 0})
                summary['spans'] += 1
            # the splitters: a strip boundary on each edge of the beam, the whole beam long
            if splitters and bound_cat and _table_exists(db, 'StripBoundary'):
                for sign in [1, -1]:
                    edge = [{'x': beam['a']['x'] + n['x'] * sign * beam['t'] / 2, 'y': beam['a']['y'] + n['y'] * sign * beam['t'] / 2}, {'x': beam['b']['x'] + n['x'] * sign * beam['t'] / 2, 'y': beam['b']['y'] + n['y'] * sign * beam['t'] / 2}]
                    insert_row('StripBoundary', {'UID': next_uid(), 'ParentUID': bound_cat['UID'], 'RssUid': 0, 'Name': '', 'Boundary': _poly(edge), 'SpanSet': span_set})
                    summary['splitters'] += 1
            summary['frames'].append({'beam': beam['id'], 'frame': frame_label, 'spanSet': span_set, 'width': size50(beam['t']), 'depth': size50(beam.get('depth')), 'spans': [{'length': _round(sp['length']), 'support0': (sp.get('support0') or {}).get('kind') or None, 'support1': (sp.get('support1') or {}).get('kind') or None} for sp in spans], 'segments': span_uids})
        # the sibling chains of every category written to
        for parent, ch in chains.items():
            table, uids = ch['table'], ch['uids']
            for i, id_ in enumerate(uids):
                db.execute(f'update "{table}" set PreviousSibUID = ?, NextSibUID = ?, ChildIndex = ?, Number = ? where UID = ?', (uids[i - 1] if i else 0, uids[i + 1] if i + 1 < len(uids) else 0, i, i, id_))
        db.execute('COMMIT')
    except BaseException as error:
        try:
            db.execute('ROLLBACK')
        except sqlite3.Error:
            pass  # not open
        db.close()
        raise error
    db.close()
    return summary


# ------------------------------------------------------------------ the schedule off the calculated model
def BAR_AREA(d):
    return (math.pi * d * d) / 4


def _bars_text(n, dia):
    return f'{_S(n)}T{_S(dia)}' if n and dia else '-'


# RAM's beam design read back: for every beam the designed bands lying in it (top bars over the supports, bottom
# bars in the span, the heaviest of each) and the stirrup regions in it (the closest spacing). Beams of one
# section whose bars are alike share a type.
def _stirrup_capacity(st):
    """Stirrup capacity of a set (mm²/mm): legs x bar area / spacing."""
    return (st['legs'] * BAR_AREA(st['dia'])) / st['spacing'] if st and (st.get('spacing') or 0) > 0 else 0


def _area_of(s):
    return (s.get('area') or _round(s['n'] * BAR_AREA(s['dia']))) if s else 0


def _mark_number(mark):
    m = re.search(r'(\d+)\s*$', _S(mark) if mark is not None else '')
    return int(m.group(1)) if m else 0


def type_covers(t, r, tol=10):
    """
    Does the type carry the beam? Same section, and every set of the type at least as heavy as the beam asks
    (top, bottom and stirrup capacity). A type is never changed: a beam it does not carry gets a new type.
    """
    if abs(t['width'] - r['width']) > tol or abs(t['depth'] - r['depth']) > tol:
        return False
    if _area_of(r.get('top')) > _area_of(t.get('top')):
        return False
    if _area_of(r.get('bottom')) > _area_of(t.get('bottom')):
        return False
    if r.get('stirrups') and _stirrup_capacity(r['stirrups']) > _stirrup_capacity(t.get('stirrups')) * 1.001:
        return False
    return True


def beam_schedule(ram, level=None, library=None, design='ram', office=None, assign=None, source=None):
    """
    The beams of a level typed against the project's unified schedule: `library` is the list of types the project
    already has (its own runs and the schedules imported from earlier projects). A beam takes the lightest library
    type that carries it; the beams no type carries are grouped among themselves (one section, bars alike) into new
    types numbered after the library's last mark. Library types are used as they are, never modified.
    """
    if library is None:
        library = []
    beams = [{**b} for b in ((level or {}).get('beams') or ram.get('beams') or [])]
    if not beams:
        return None

    def office_of(id_):
        return next((b for b in ((office or {}).get('beams') or []) if _S(b.get('id')).upper() == _S(id_).upper()), None)
    level_ram = (level or {}).get('ram') or {}
    bands = [b for b in (level_ram.get('bands') or ram.get('bands') or []) if b.get('designedBy') == 'program' or b.get('designedBy') is None]
    shear = level_ram.get('shear') or ram.get('shear') or []

    def expand(bm, m):
        u = {'x': (bm['b']['x'] - bm['a']['x']) / dist(bm['a'], bm['b']), 'y': (bm['b']['y'] - bm['a']['y']) / dist(bm['a'], bm['b'])}
        n = {'x': -u['y'], 'y': u['x']}
        w = bm['t'] / 2 + m
        return [{'x': bm['a']['x'] + n['x'] * w - u['x'] * m, 'y': bm['a']['y'] + n['y'] * w - u['y'] * m}, {'x': bm['b']['x'] + n['x'] * w + u['x'] * m, 'y': bm['b']['y'] + n['y'] * w + u['y'] * m}, {'x': bm['b']['x'] - n['x'] * w + u['x'] * m, 'y': bm['b']['y'] - n['y'] * w + u['y'] * m}, {'x': bm['a']['x'] - n['x'] * w - u['x'] * m, 'y': bm['a']['y'] - n['y'] * w - u['y'] * m}]
    rows = []
    for bm in beams:
        zone = expand(bm, 150)
        u = {'x': (bm['b']['x'] - bm['a']['x']) / dist(bm['a'], bm['b']), 'y': (bm['b']['y'] - bm['a']['y']) / dist(bm['a'], bm['b'])}

        def in_zone(b):
            m = {'x': (b['p0']['x'] + b['p1']['x']) / 2, 'y': (b['p0']['y'] + b['p1']['y']) / 2}
            L = dist(b['p0'], b['p1']) or 1
            v = {'x': (b['p1']['x'] - b['p0']['x']) / L, 'y': (b['p1']['y'] - b['p0']['y']) / L}
            return point_in_polygon(m, zone) and abs(u['x'] * v['x'] + u['y'] * v['y']) > 0.9
        mine = [b for b in bands if in_zone(b)]

        def heaviest(face):
            lst = sorted([{'n': b['count'], 'dia': b['dia'], 'area': b['count'] * BAR_AREA(b['dia']), 'band': b} for b in mine if b['face'] == face], key=lambda x: x['area'], reverse=True)
            return lst[0] if lst else None
        top, bottom = heaviest('T'), heaviest('B')
        links = sorted([s for s in shear if point_in_polygon({'x': (s['a']['x'] + s['b']['x']) / 2, 'y': (s['a']['y'] + s['b']['y']) / 2}, zone)], key=lambda s: s['spacing'])
        st = links[0] if links else None
        ram_sets = {
            'top': {'n': top['n'], 'dia': top['dia'], 'area': _round(top['area']), 'text': _bars_text(top['n'], top['dia'])} if top else None,
            'bottom': {'n': bottom['n'], 'dia': bottom['dia'], 'area': _round(bottom['area']), 'text': _bars_text(bottom['n'], bottom['dia'])} if bottom else None,
            'stirrups': {'dia': st['dia'], 'legs': st['legs'], 'spacing': st['spacing'], 'text': f"T{_S(st['dia'])}-{_S(st['legs'])}L@{_S(st['spacing'])}"} if st else None,
        }
        # the office design of the beam (lib/beam-design.mjs) beside RAM's; the design option picks the bars drawn:
        # 'ram' (RAM's bands), 'office' (the office design) or 'max' (set by set, the heavier of the two)
        off = office_of(bm['id'])
        off_sets = {'top': off.get('top'), 'bottom': off.get('bottom'), 'stirrups': off.get('stirrups')} if off else None

        def heavier(a, b2):
            return b2 if not a else (a if not b2 else (a if (a.get('area') or 0) >= (b2.get('area') or 0) else b2))

        def stiffer(a, b2):
            return b2 if not a else (a if not b2 else (a if _stirrup_capacity(a) >= _stirrup_capacity(b2) else b2))
        chosen = off_sets if design == 'office' and off_sets \
            else ({'top': heavier(ram_sets['top'], off_sets['top']), 'bottom': heavier(ram_sets['bottom'], off_sets['bottom']), 'stirrups': stiffer(ram_sets['stirrups'], off_sets['stirrups'])} if design == 'max' and off_sets
                  else ram_sets)
        rows.append({
            'id': bm['id'], 'a': bm['a'], 'b': bm['b'], 'width': size50(bm['t']), 'depth': size50(bm.get('depth')), 'length': _round(dist(bm['a'], bm['b'])),
            **chosen, 'ram': ram_sets, 'office': off_sets, 'design': 'ram' if design == 'ram' or not off_sets else design,
            'bands': len(mine), 'designed': bool(chosen.get('top') or chosen.get('bottom')), 'ramDesigned': bool(ram_sets['top'] or ram_sets['bottom']),
        })
    # the project's schedule first: a designed beam takes the lightest existing type that carries it
    lib = []
    for t in library or []:
        if not (t and t.get('mark') and t.get('width') and t.get('depth')):
            continue
        lib.append({**t,
                    'top': {**t['top'], 'area': _area_of(t['top']), 'text': t['top'].get('text') or _bars_text(t['top'].get('n'), t['top'].get('dia'))} if t.get('top') else None,
                    'bottom': {**t['bottom'], 'area': _area_of(t['bottom']), 'text': t['bottom'].get('text') or _bars_text(t['bottom'].get('n'), t['bottom'].get('dia'))} if t.get('bottom') else None,
                    'stirrups': {**t['stirrups'], 'text': t['stirrups'].get('text') or f"T{_S(t['stirrups'].get('dia'))}-{_S(t['stirrups'].get('legs'))}L@{_S(t['stirrups'].get('spacing'))}"} if t.get('stirrups') else None,
                    'beams': [], 'existing': True})

    def weight(t):
        return _area_of(t.get('top')) + _area_of(t.get('bottom')) + _stirrup_capacity(t.get('stirrups')) * 1000
    # beams assigned a type by the engineer (`spec.beamAssign`, e.g. the consultant's schedule kept as it is): the beam
    # takes that type's bars as they are - no RAM / office design, no typing - and the type is used even if unverified
    assigned, unassigned = [], []

    def assign_of(id_):
        if not assign:
            return None
        k = next((x for x in assign.keys() if str(x).strip().upper() == str(id_).upper()), None)
        return assign[k] if k else None
    for r in rows:
        mk = assign_of(r['id'])
        if not mk:
            continue
        t = next((x for x in lib if str(x['mark']).upper() == str(mk).strip().upper()), None)
        if not t:
            unassigned.append(f"{r['id']} -> {mk}")
            continue
        t['beams'].append(r['id'])
        r.update({'mark': t['mark'], 'existing': True, 'assigned': True, 'designed': True, 'top': t.get('top'), 'bottom': t.get('bottom'), 'stirrups': t.get('stirrups'), 'design': 'assigned'})
        assigned.append(r['id'])
    uncovered = []
    for r in [x for x in rows if x['designed'] and not x.get('assigned')]:
        fitting = sorted([t for t in lib if type_covers(t, r)], key=weight)
        fits = fitting[0] if fitting else None
        if fits:
            fits['beams'].append(r['id'])
            r['mark'] = fits['mark']
            r['existing'] = True
        else:
            uncovered.append(r)
    # new types for the rest: one section, bars alike (within 15 % of the heaviest member's area, stirrups within 25 mm),
    # numbered after the last mark of the project's schedule; the existing types stay exactly as they are
    next_no = max([0, *[_mark_number(t['mark']) for t in lib]]) + 1
    uncovered.sort(key=lambda p: (-(p['width'] * p['depth']), -(((p.get('top') or {}).get('area') or 0) + ((p.get('bottom') or {}).get('area') or 0))))
    sorted_rows = uncovered
    added = []
    for r in sorted_rows:
        def alike(t):
            if not (t['width'] == r['width'] and t['depth'] == r['depth']):
                return False
            if not t.get('top') or not r.get('top'):
                if (not t.get('top')) != (not r.get('top')):
                    return False
            elif not (r['top']['area'] >= 0.85 * t['top']['area'] and r['top']['area'] <= t['top']['area']):
                return False
            if not t.get('bottom') or not r.get('bottom'):
                if (not t.get('bottom')) != (not r.get('bottom')):
                    return False
            elif not (r['bottom']['area'] >= 0.85 * t['bottom']['area'] and r['bottom']['area'] <= t['bottom']['area']):
                return False
            if not t.get('stirrups') or not r.get('stirrups'):
                return True
            return abs(t['stirrups']['spacing'] - r['stirrups']['spacing']) <= 25 and t['stirrups']['dia'] == r['stirrups']['dia']
        fits = next((t for t in added if alike(t)), None)
        if fits:
            fits['beams'].append(r['id'])
            r['mark'] = fits['mark']
            continue
        t = {'mark': f'B{next_no}', 'width': size50(r['width']), 'depth': size50(r['depth']), 'section': f"{_S(size50(r['width']))}x{_S(size50(r['depth']))}", 'top': r.get('top'), 'bottom': r.get('bottom'), 'stirrups': r.get('stirrups'), 'beams': [r['id']], 'isNew': True}
        next_no += 1
        added.append(t)
        r['mark'] = t['mark']
    for r in rows:
        if not r['designed']:
            r['mark'] = None
    used = [{**t, 'count': len(t['beams'])} for t in [*[t for t in lib if t['beams']], *added]]
    return {
        'beams': rows, 'types': used, 'undesigned': [r['id'] for r in rows if not r['designed']], 'ramUndesigned': [r['id'] for r in rows if not r['ramDesigned'] and not r.get('assigned')],
        'added': [{'mark': t['mark'], 'width': t['width'], 'depth': t['depth'], 'section': t['section'], 'top': t['top'], 'bottom': t['bottom'], 'stirrups': t['stirrups']} for t in added],
        'library': len(lib), 'design': design, 'office': {'beams': office.get('beams'), 'failing': office.get('failing'), 'blocking': office.get('blocking'), 'warnings': office.get('warnings'), 'assumed': office.get('assumed')} if office else None,
        'assigned': assigned, 'unassigned': unassigned, 'source': source or None,
    }


def bar_set_area(n, dia):
    """The bar area of `nTdia` text, for the schedule totals."""
    return _round(n * BAR_AREA(dia))


# export { pt as cptPoint, point as cptPointOf, bbox as _bbox };
cpt_point = _pt
cpt_point_of = _point
_bbox = bbox
