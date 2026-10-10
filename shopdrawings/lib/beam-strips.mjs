/**
 * Beam design through RAM Concept, the office way:
 *   1. `writeBeamStrips` rewrites the model's design strips: every span segment, strip boundary, span boundary and
 *      design section is dropped, and every beam gets one design strip on its centre line per span between its
 *      supports, with a splitter (strip boundary) on each of its edges, designed as a beam. RAM then analyses and
 *      designs the beams on Calc All.
 *   2. `beamSchedule` reads RAM's designed bars and stirrups back off the calculated model, beam by beam, groups
 *      the beams whose section and reinforcement are alike into types (B1, B2 …), and gives every beam its type,
 *      section and bars for the plan and the schedule.
 * The .cpt is an SQLite file: lengths are stored in 0.1 mm, points as `[x][y]`, and every object row sits in a
 * category with a sibling chain (PreviousSibUID / NextSibUID / ChildIndex).
 */
import { DatabaseSync } from 'node:sqlite';
import { copyFileSync } from 'node:fs';
import { dist, pointInPolygon, bbox } from './geometry.mjs';

const U = 10; // mm → 0.1 mm
const pt = (p) => `[${Math.round(p.x * U)}][${Math.round(p.y * U)}]`;
const poly = (pts) => pts.map((p) => `[${pt(p)}]`).join('');
const nums = (s) => (String(s || '').match(/-?\d+(\.\d+)?/g) || []).map(Number);
const point = (s) => { const v = nums(s); return { x: v[0] / U, y: v[1] / U }; };

const STRIP_TABLES = ['SpanSegment', 'SpanSegmentStrip', 'SpanBoundary', 'StripBoundary', 'DesignSection', 'SpanSegmentDeflectionCheckDesign', 'SpanDesign', 'DSDesign'];

function tableExists(db, t) { return !!db.prepare("select name from sqlite_master where type = 'table' and name = ?").get(t); }
function columnsOf(db, t) { return db.prepare(`pragma table_info("${t}")`).all().map((c) => c.name); }
function maxUid(db) {
  let m = 0;
  for (const { name } of db.prepare("select name from sqlite_master where type = 'table'").all()) {
    if (!columnsOf(db, name).includes('UID')) continue;
    const r = db.prepare(`select max(UID) as m from "${name}"`).get();
    if (r && r.m > m) m = r.m;
  }
  return m;
}

/** The spans of a beam: its axis cut at the supports (columns and walls) it crosses; each span with the support size at its ends. */
/** Beam sizes are written to the nearest 50 mm with no decimals (office convention): 350x600. */
export const size50 = (v) => Math.round((Number(v) || 0) / 50) * 50;

export function beamSpans(beam, columns, walls, beams = []) {
  const L = dist(beam.a, beam.b);
  const u = { x: (beam.b.x - beam.a.x) / L, y: (beam.b.y - beam.a.y) / L }, n = { x: -u.y, y: u.x };
  const alongX = Math.abs(u.x) >= Math.abs(u.y);
  const supports = [];
  for (const c of columns) {
    const d = { x: c.cx - beam.a.x, y: c.cy - beam.a.y };
    const t = d.x * u.x + d.y * u.y, off = Math.abs(d.x * n.x + d.y * n.y);
    const along = alongX ? (c.w || c.d || 300) : (c.h || c.d || 300), across = alongX ? (c.h || c.d || 300) : (c.w || c.d || 300);
    if (off <= beam.t / 2 + across / 2 && t >= -along / 2 && t <= L + along / 2) supports.push({ t: Math.max(0, Math.min(L, t)), along, across, kind: 'column' });
  }
  for (const w of walls || []) {
    // a wall crossing the axis is a support; a wall along the beam is not a span break
    const dx = w.b.x - w.a.x, dy = w.b.y - w.a.y;
    const den = u.x * dy - u.y * dx;
    if (Math.abs(den) < 1e-9) continue;
    const ex = w.a.x - beam.a.x, ey = w.a.y - beam.a.y;
    const t = (ex * dy - ey * dx) / den, s = (ex * u.y - ey * u.x) / den;
    if (s >= -1e-6 && s <= 1 + 1e-6 && t >= -100 && t <= L + 100) supports.push({ t: Math.max(0, Math.min(L, t)), along: w.t || 250, across: Math.hypot(dx, dy), kind: 'wall' });
  }
  // a deeper beam crossing this one carries it: it is a support too (office rule), the span breaks at its axis
  for (const ob of beams || []) {
    if (ob === beam || ob.id === beam.id || !ob.a || !ob.b || !((ob.depth || 0) > (beam.depth || 0))) continue;
    const dx = ob.b.x - ob.a.x, dy = ob.b.y - ob.a.y;
    const den = u.x * dy - u.y * dx;
    if (Math.abs(den) < 1e-9) continue;
    const ex = ob.a.x - beam.a.x, ey = ob.a.y - beam.a.y;
    const t = (ex * dy - ey * dx) / den, s = (ex * u.y - ey * u.x) / den;
    if (s >= -1e-6 && s <= 1 + 1e-6 && t >= -100 && t <= L + 100) supports.push({ t: Math.max(0, Math.min(L, t)), along: ob.t || 300, across: Math.hypot(dx, dy), kind: 'beam', beam: ob.id });
  }
  supports.sort((p, q) => p.t - q.t);
  // merge supports closer than half a metre (a wall meeting a column)
  const merged = [];
  for (const s of supports) { const last = merged[merged.length - 1]; if (last && s.t - last.t < 500) { last.along = Math.max(last.along, s.along); last.across = Math.max(last.across, s.across); } else merged.push({ ...s }); }
  const cuts = [0, ...merged.map((s) => s.t).filter((t) => t > 800 && t < L - 800), L];
  const spans = [];
  for (let i = 0; i + 1 < cuts.length; i++) {
    const t0 = cuts[i], t1 = cuts[i + 1];
    if (t1 - t0 < 500) continue;
    const s0 = merged.find((s) => Math.abs(s.t - t0) <= 1000), s1 = merged.find((s) => Math.abs(s.t - t1) <= 1000);
    spans.push({
      t0, t1, length: t1 - t0,
      a: { x: beam.a.x + u.x * t0, y: beam.a.y + u.y * t0 }, b: { x: beam.a.x + u.x * t1, y: beam.a.y + u.y * t1 },
      support0: s0 || null, support1: s1 || null,
    });
  }
  return { spans, u, n, alongX, spanSet: alongX ? 'latitude' : 'longitude', supports: merged };
}

/**
 * Rewrites the design strips of a RAM Concept model for beam design. `ram` is the model read with readRamConcept
 * (columns, walls and beams in mm); `src` is copied to `out` and the copy is edited. Returns what was written.
 */
export function writeBeamStrips(src, out, ram, { designSystem = 'beam', splitters = true } = {}) {
  copyFileSync(src, out);
  const db = new DatabaseSync(out);
  const summary = { beams: 0, spans: 0, splitters: 0, removed: {}, frames: [], missing: [] };
  try {
    db.exec('BEGIN');
    let uid = maxUid(db); // before anything is dropped: a UID is never reused
    for (const t of STRIP_TABLES) {
      if (!tableExists(db, t)) continue;
      summary.removed[t] = db.prepare(`select count(*) as n from "${t}"`).get().n;
      db.exec(`delete from "${t}"`);
    }
    const catOf = (table, spanSet) => (tableExists(db, table) ? db.prepare(`select UID from "${table}" where SpanSet = ?`).get(spanSet) : null);
    const segCols = tableExists(db, 'SpanSegment') ? columnsOf(db, 'SpanSegment') : null;
    if (!segCols) throw new Error('This model has no design strip tables (SpanSegment); is it a RAM Concept file?');
    const defaults = tableExists(db, 'DefaultSpanSegment') ? db.prepare('select * from DefaultSpanSegment limit 1').get() : null;
    const nextUid = () => ++uid;
    const chains = new Map(); // category uid -> [uids]
    const insertRow = (table, row) => {
      const info = db.prepare(`pragma table_info("${table}")`).all();
      const full = { PreviousSibUID: 0, NextSibUID: 0, ChildIndex: 0, Number: 0, ...row };
      // every NOT NULL column the row does not carry takes an empty value of its type
      for (const c of info) if (c.notnull && !(c.name in full)) full[c.name] = /INT|REAL|NUM|DOUB|FLOA/i.test(c.type || '') ? 0 : '';
      const keys = Object.keys(full).filter((k) => info.some((c) => c.name === k));
      db.prepare(`insert into "${table}" (${keys.map((k) => `"${k}"`).join(',')}) values (${keys.map(() => '?').join(',')})`).run(...keys.map((k) => full[k]));
      if (!chains.has(row.ParentUID)) chains.set(row.ParentUID, { table, uids: [] });
      chains.get(row.ParentUID).uids.push(row.UID);
    };
    const frameNo = { latitude: 0, longitude: 0 };
    for (const beam of ram.beams || []) {
      const { spans, n, spanSet } = beamSpans(beam, ram.columns || [], ram.walls || [], ram.beams || []);
      if (!spans.length) continue;
      const segCat = catOf('SpanSegmentCategory', spanSet), stripCat = catOf('SpanSegmentStripCategory', spanSet), boundCat = catOf('StripBoundaryCategory', spanSet);
      if (!segCat) { summary.missing.push(`${beam.id}: no ${spanSet} span segment category`); continue; }
      const frame = frameNo[spanSet]++;
      const frameLabel = frame + 1;
      summary.beams++;
      const spanUids = [];
      spans.forEach((sp, k) => {
        const segUid = nextUid();
        spanUids.push(segUid);
        const row = {
          ...(defaults || {}),
          UID: segUid, ParentUID: segCat.UID, RssUid: 0, Name: `${frameLabel}-${k + 1}`, DeflectionCheckList: '',
          Point0: pt(sp.a), Point1: pt(sp.b), SkewAngle: 0, SpanSet: spanSet, FrameNumber: frame, SpanNumber: k, SegmentNumber: 0,
          AtSupport0: sp.support0 ? 1 : 0, AtSupport1: sp.support1 ? 1 : 0,
          SupportWidth0: Math.round((sp.support0?.along || 0) * U), SupportWidth1: Math.round((sp.support1?.along || 0) * U),
          SupportTransverseWidth0: Math.round((sp.support0?.across || beam.t) * U), SupportTransverseWidth1: Math.round((sp.support1?.across || beam.t) * U),
          AutoSupportDetect: 1, LockStripGeneration: 0,
          SpanWidthCalc: 'auto', ColumnStripWidthCalc: 'full', MiddleStripUsesColumnStripProps: 1,
          ColumnStripDesignSystem: designSystem, MiddleStripDesignSystem: designSystem,
          ColumnStripStirrupLegs: defaults?.ColumnStripStirrupLegs || 2, MiddleStripStirrupLegs: defaults?.MiddleStripStirrupLegs || 2,
        };
        insertRow('SpanSegment', row);
        // the strip of the span: the beam's own width (RAM regenerates it on Calc All; written so the model opens with it)
        if (stripCat && tableExists(db, 'SpanSegmentStrip')) {
          const left = [{ x: sp.a.x + n.x * beam.t / 2, y: sp.a.y + n.y * beam.t / 2 }, { x: sp.b.x + n.x * beam.t / 2, y: sp.b.y + n.y * beam.t / 2 }];
          const right = [{ x: sp.a.x - n.x * beam.t / 2, y: sp.a.y - n.y * beam.t / 2 }, { x: sp.b.x - n.x * beam.t / 2, y: sp.b.y - n.y * beam.t / 2 }];
          insertRow('SpanSegmentStrip', { UID: nextUid(), ParentUID: stripCat.UID, RssUid: 0, Name: `${frameLabel}C-${k + 1}`, Point0: pt(sp.a), Point1: pt(sp.b), ResistanceLeftBoundary: poly(left), ResistanceRightBoundary: poly(right), DemandLeftBoundary: poly(left), DemandRightBoundary: poly(right), SpanSegment: segUid, StripType: 'center', AutoTribArea: 0, AutoInfluenceArea: 0 });
        }
        summary.spans++;
      });
      // the splitters: a strip boundary on each edge of the beam, the whole beam long
      if (splitters && boundCat && tableExists(db, 'StripBoundary')) {
        for (const sign of [1, -1]) {
          const edge = [{ x: beam.a.x + n.x * sign * beam.t / 2, y: beam.a.y + n.y * sign * beam.t / 2 }, { x: beam.b.x + n.x * sign * beam.t / 2, y: beam.b.y + n.y * sign * beam.t / 2 }];
          insertRow('StripBoundary', { UID: nextUid(), ParentUID: boundCat.UID, RssUid: 0, Name: '', Boundary: poly(edge), SpanSet: spanSet });
          summary.splitters++;
        }
      }
      summary.frames.push({ beam: beam.id, frame: frameLabel, spanSet, width: size50(beam.t), depth: size50(beam.depth), spans: spans.map((sp) => ({ length: Math.round(sp.length), support0: sp.support0?.kind || null, support1: sp.support1?.kind || null })), segments: spanUids });
    }
    // the sibling chains of every category written to
    for (const [parent, { table, uids }] of chains) {
      uids.forEach((id, i) => db.prepare(`update "${table}" set PreviousSibUID = ?, NextSibUID = ?, ChildIndex = ?, Number = ? where UID = ?`).run(i ? uids[i - 1] : 0, i + 1 < uids.length ? uids[i + 1] : 0, i, i, id));
    }
    db.exec('COMMIT');
  } catch (error) {
    try { db.exec('ROLLBACK'); } catch { /* not open */ }
    db.close();
    throw error;
  }
  db.close();
  return summary;
}

// ------------------------------------------------------------------ the schedule off the calculated model
const BAR_AREA = (d) => (Math.PI * d * d) / 4;
const barsText = (n, dia) => (n && dia ? `${n}T${dia}` : '-');

/**
 * RAM's beam design read back: for every beam the designed bands lying in it (top bars over the supports, bottom
 * bars in the span, the heaviest of each) and the stirrup regions in it (the closest spacing). Beams of one
 * section whose bars are alike share a type.
 */
/** Stirrup capacity of a set (mm²/mm): legs x bar area / spacing. */
const stirrupCapacity = (st) => (st && st.spacing > 0 ? (st.legs * BAR_AREA(st.dia)) / st.spacing : 0);
const areaOf = (set) => (set ? set.area || Math.round(set.n * BAR_AREA(set.dia)) : 0);
const markNumber = (mark) => { const m = /(\d+)\s*$/.exec(String(mark || '')); return m ? Number(m[1]) : 0; };

/**
 * Does the type carry the beam? Same section, and every set of the type at least as heavy as the beam asks
 * (top, bottom and stirrup capacity). A type is never changed: a beam it does not carry gets a new type.
 */
export function typeCovers(t, r, tol = 10) {
  if (Math.abs(t.width - r.width) > tol || Math.abs(t.depth - r.depth) > tol) return false;
  if (areaOf(r.top) > areaOf(t.top)) return false;
  if (areaOf(r.bottom) > areaOf(t.bottom)) return false;
  if (r.stirrups && stirrupCapacity(r.stirrups) > stirrupCapacity(t.stirrups) * 1.001) return false;
  return true;
}

/**
 * The beams of a level typed against the project's unified schedule: `library` is the list of types the project
 * already has (its own runs and the schedules imported from earlier projects). A beam takes the lightest library
 * type that carries it; the beams no type carries are grouped among themselves (one section, bars alike) into new
 * types numbered after the library's last mark. Library types are used as they are, never modified.
 */
export function beamSchedule(ram, level = null, { library = [], design = 'ram', office = null, assign = null, source = null, byOthers = null } = {}) {
  const beams = (level?.beams || ram.beams || []).map((b) => ({ ...b }));
  if (!beams.length) return null;
  const officeOf = (id) => (office?.beams || []).find((b) => String(b.id).toUpperCase() === String(id).toUpperCase()) || null;
  const bands = (level?.ram?.bands || ram.bands || []).filter((b) => b.designedBy === 'program' || b.designedBy == null);
  const shear = level?.ram?.shear || ram.shear || [];
  const expand = (bm, m) => { const u = { x: (bm.b.x - bm.a.x) / dist(bm.a, bm.b), y: (bm.b.y - bm.a.y) / dist(bm.a, bm.b) }, n = { x: -u.y, y: u.x }; const w = bm.t / 2 + m; return [{ x: bm.a.x + n.x * w - u.x * m, y: bm.a.y + n.y * w - u.y * m }, { x: bm.b.x + n.x * w + u.x * m, y: bm.b.y + n.y * w + u.y * m }, { x: bm.b.x - n.x * w + u.x * m, y: bm.b.y - n.y * w + u.y * m }, { x: bm.a.x - n.x * w - u.x * m, y: bm.a.y - n.y * w - u.y * m }]; };
  const rows = beams.map((bm) => {
    const zone = expand(bm, 150);
    const u = { x: (bm.b.x - bm.a.x) / dist(bm.a, bm.b), y: (bm.b.y - bm.a.y) / dist(bm.a, bm.b) };
    const mine = bands.filter((b) => {
      const m = { x: (b.p0.x + b.p1.x) / 2, y: (b.p0.y + b.p1.y) / 2 };
      const L = dist(b.p0, b.p1) || 1, v = { x: (b.p1.x - b.p0.x) / L, y: (b.p1.y - b.p0.y) / L };
      return pointInPolygon(m, zone) && Math.abs(u.x * v.x + u.y * v.y) > 0.9;
    });
    const heaviest = (face) => mine.filter((b) => b.face === face).map((b) => ({ n: b.count, dia: b.dia, area: b.count * BAR_AREA(b.dia), band: b })).sort((p, q) => q.area - p.area)[0] || null;
    const top = heaviest('T'), bottom = heaviest('B');
    const links = shear.filter((s) => pointInPolygon({ x: (s.a.x + s.b.x) / 2, y: (s.a.y + s.b.y) / 2 }, zone)).sort((p, q) => p.spacing - q.spacing);
    const st = links[0] || null;
    const ramSets = {
      top: top ? { n: top.n, dia: top.dia, area: Math.round(top.area), text: barsText(top.n, top.dia) } : null,
      bottom: bottom ? { n: bottom.n, dia: bottom.dia, area: Math.round(bottom.area), text: barsText(bottom.n, bottom.dia) } : null,
      stirrups: st ? { dia: st.dia, legs: st.legs, spacing: st.spacing, text: `T${st.dia}-${st.legs}L@${st.spacing}` } : null,
    };
    // the office design of the beam (lib/beam-design.mjs) beside RAM's; the design option picks the bars drawn:
    // 'ram' (RAM's bands), 'office' (the office design) or 'max' (set by set, the heavier of the two)
    const off = officeOf(bm.id);
    const offSets = off ? { top: off.top, bottom: off.bottom, stirrups: off.stirrups } : null;
    const heavier = (a, b2) => (!a ? b2 : !b2 ? a : (a.area || 0) >= (b2.area || 0) ? a : b2);
    const stiffer = (a, b2) => (!a ? b2 : !b2 ? a : stirrupCapacity(a) >= stirrupCapacity(b2) ? a : b2);
    const chosen = design === 'office' && offSets ? offSets
      : design === 'max' && offSets ? { top: heavier(ramSets.top, offSets.top), bottom: heavier(ramSets.bottom, offSets.bottom), stirrups: stiffer(ramSets.stirrups, offSets.stirrups) }
      : ramSets;
    return {
      id: bm.id, a: bm.a, b: bm.b, width: size50(bm.t), depth: size50(bm.depth), length: Math.round(dist(bm.a, bm.b)),
      ...chosen, ram: ramSets, office: offSets, design: design === 'ram' || !offSets ? 'ram' : design,
      bands: mine.length, designed: !!(chosen.top || chosen.bottom), ramDesigned: !!(ramSets.top || ramSets.bottom),
    };
  });
  // the project's schedule first: a designed beam takes the lightest existing type that carries it
  const lib = (library || []).filter((t) => t && t.mark && t.width && t.depth).map((t) => ({ ...t, top: t.top ? { ...t.top, area: areaOf(t.top), text: t.top.text || barsText(t.top.n, t.top.dia) } : null, bottom: t.bottom ? { ...t.bottom, area: areaOf(t.bottom), text: t.bottom.text || barsText(t.bottom.n, t.bottom.dia) } : null, stirrups: t.stirrups ? { ...t.stirrups, text: t.stirrups.text || `T${t.stirrups.dia}-${t.stirrups.legs}L@${t.stirrups.spacing}` } : null, beams: [], existing: true }));
  const weight = (t) => areaOf(t.top) + areaOf(t.bottom) + stirrupCapacity(t.stirrups) * 1000;
  // beams assigned a type by the engineer (`spec.beamAssign`, e.g. the consultant's schedule kept as it is): the beam
  // takes that type's bars as they are - no RAM / office design, no typing - and the type is used even if unverified
  // the consultant's RC beams (`byOthers`: ids): on the plan as they are, never designed, typed or scheduled here
  const othersSet = new Set((byOthers || []).map((v) => String(v).trim().toUpperCase()));
  const others = [];
  for (const r of rows) if (othersSet.has(String(r.id).toUpperCase())) { Object.assign(r, { byOthers: true, designed: false, mark: null, top: null, bottom: null, stirrups: null, design: 'others' }); others.push(r.id); }
  const assigned = [], unassigned = [];
  const assignOf = (id) => { if (!assign) return null; const k = Object.keys(assign).find((x) => String(x).trim().toUpperCase() === String(id).toUpperCase()); return k ? assign[k] : null; };
  for (const r of rows) {
    if (r.byOthers) continue;
    const mk = assignOf(r.id);
    if (!mk) continue;
    const t = lib.find((x) => String(x.mark).toUpperCase() === String(mk).trim().toUpperCase());
    if (!t) { unassigned.push(`${r.id} -> ${mk}`); continue; }
    t.beams.push(r.id);
    Object.assign(r, { mark: t.mark, existing: true, assigned: true, designed: true, top: t.top, bottom: t.bottom, stirrups: t.stirrups, design: 'assigned' });
    assigned.push(r.id);
  }
  const uncovered = [];
  for (const r of rows.filter((x) => x.designed && !x.assigned)) {
    const fits = lib.filter((t) => typeCovers(t, r)).sort((p, q) => weight(p) - weight(q))[0];
    if (fits) { fits.beams.push(r.id); r.mark = fits.mark; r.existing = true; } else uncovered.push(r);
  }
  // new types for the rest: one section, bars alike (within 15 % of the heaviest member's area, stirrups within 25 mm),
  // numbered after the last mark of the project's schedule; the existing types stay exactly as they are
  let next = Math.max(0, ...lib.map((t) => markNumber(t.mark))) + 1;
  const sorted = uncovered.sort((p, q) => (q.width * q.depth - p.width * p.depth) || ((q.top?.area || 0) + (q.bottom?.area || 0)) - ((p.top?.area || 0) + (p.bottom?.area || 0)));
  const added = [];
  for (const r of sorted) {
    const fits = added.find((t) => t.width === r.width && t.depth === r.depth
      && (!t.top || !r.top ? !t.top === !r.top : r.top.area >= 0.85 * t.top.area && r.top.area <= t.top.area)
      && (!t.bottom || !r.bottom ? !t.bottom === !r.bottom : r.bottom.area >= 0.85 * t.bottom.area && r.bottom.area <= t.bottom.area)
      && (!t.stirrups || !r.stirrups ? true : Math.abs(t.stirrups.spacing - r.stirrups.spacing) <= 25 && t.stirrups.dia === r.stirrups.dia));
    if (fits) { fits.beams.push(r.id); r.mark = fits.mark; continue; }
    const t = { mark: `B${next++}`, width: size50(r.width), depth: size50(r.depth), section: `${size50(r.width)}x${size50(r.depth)}`, top: r.top, bottom: r.bottom, stirrups: r.stirrups, beams: [r.id], isNew: true };
    added.push(t);
    r.mark = t.mark;
  }
  for (const r of rows) if (!r.designed) r.mark = null;
  const used = [...lib.filter((t) => t.beams.length), ...added].map((t) => ({ ...t, count: t.beams.length }));
  return {
    beams: rows, types: used, undesigned: rows.filter((r) => !r.designed && !r.byOthers).map((r) => r.id), ramUndesigned: rows.filter((r) => !r.ramDesigned && !r.assigned && !r.byOthers).map((r) => r.id),
    added: added.map((t) => ({ mark: t.mark, width: t.width, depth: t.depth, section: t.section, top: t.top, bottom: t.bottom, stirrups: t.stirrups })),
    library: lib.length, design, office: office ? { beams: office.beams, failing: office.failing, blocking: office.blocking, warnings: office.warnings, assumed: office.assumed } : null,
    assigned, unassigned, source: source || null, byOthers: others,
  };
}

/** The bar area of `nTdia` text, for the schedule totals. */
export const barSetArea = (n, dia) => Math.round(n * BAR_AREA(dia));
export { pt as cptPoint, point as cptPointOf, bbox as _bbox };
