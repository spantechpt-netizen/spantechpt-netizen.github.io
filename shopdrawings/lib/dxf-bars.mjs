/**
 * Bars read back from an edited sheet DXF.
 *
 * Every entity of a bar on the design sheets (its polyline, call-out, length text, distribution dimension, dot, tags)
 * carries the bar's tag as extended data under the application `SPANTECH` (see `barTag` in design.mjs):
 *   1000 "BAR", 1000 <bar id>, 1000 <role>, 1000 <JSON figures>
 * The figures are the ones the sheet was drawn with: call-out, length text, diameter, spacing, count (0 = a run of
 * bars whose count follows the distribution width), face, cutting length, the polyline's drawn length, the
 * distribution width and the level.
 *
 * When the engineer edits the sheet in AutoCAD - stretches a bar (STRETCH moves the polyline and the dimension
 * together), re-writes the call-out (`T16-150 (T)`), moves the distribution dimension - the drawing is uploaded back
 * and the take-off is updated from what is now drawn:
 *   - the cutting length follows the drawn polyline (the original cutting length plus the change in the drawn length),
 *   - the diameter and spacing follow the call-out text,
 *   - the count of a run of bars follows the distribution width (width / spacing + 1); a counted group keeps its count
 *     unless the call-out now says another count (`7T16`),
 * and the steel of the level moves by the difference, bar by bar. Bars that were not touched change nothing.
 */
import { parseDxf } from './dxf-reader.mjs';
import { barWeightPerM } from './rebar.mjs';

const APP = 'SPANTECH';
const r1 = (v) => Math.round(v * 10) / 10;

/** The bars of a DXF (model space and every block), each with what is now drawn for it. */
export function readBars(dxfText) {
  const dxf = typeof dxfText === 'string' ? parseDxf(dxfText) : dxfText;
  const ents = [...dxf.entities, ...[...dxf.blocks.values()].flatMap((b) => b.entities)];
  const bars = new Map();
  for (const e of ents) {
    const x = e.xdata?.[APP];
    if (!x) continue;
    const strs = x.filter(([c]) => c === 1000).map(([, v]) => v);
    if (strs[0] !== 'BAR' || strs.length < 4) continue;
    const [, id, role, json] = strs;
    let payload;
    try { payload = JSON.parse(json); } catch { continue; }
    let b = bars.get(id);
    if (!b) { b = { id, payload, now: {} }; bars.set(id, b); }
    if (role === 'BAR' && e.type === 'LWPOLYLINE') b.now.pl = polylineLength(e.pts, e.closed);
    else if (role === 'CALLOUT' && e.text != null) b.now.l1 = String(e.text).trim();
    else if (role === 'LENGTH' && e.text != null) b.now.l2 = String(e.text).trim();
    else if (role === 'DIST' && e.type === 'DIMENSION') b.now.dw = dimensionMeasure(e);
  }
  return [...bars.values()];
}

function polylineLength(pts, closed) {
  let L = 0;
  for (let i = 1; i < pts.length; i++) L += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
  if (closed && pts.length > 2) L += Math.hypot(pts[0].x - pts[pts.length - 1].x, pts[0].y - pts[pts.length - 1].y);
  return L;
}

/** What a rotated dimension measures now: its two definition points projected on its direction (code 42 as a fallback). */
function dimensionMeasure(e) {
  if (e.x3 != null && e.x4 != null) {
    const ang = ((e.rotation || 0) * Math.PI) / 180;
    const u = { x: Math.cos(ang), y: Math.sin(ang) };
    const dx = e.x4 - e.x3, dy = e.y4 - e.y3;
    const along = Math.abs(dx * u.x + dy * u.y);
    if (along > 1e-6) return along;
    return Math.hypot(dx, dy);
  }
  return Number(e.measure) || 0;
}

/** The call-out figures: count (0 = a run), diameter, spacing. */
export function parseCallout(text) {
  const m = /(\d+)?\s*T(\d+)(?:-(\d+))?/i.exec(String(text || ''));
  if (!m) return null;
  return { n: m[1] ? Number(m[1]) : 0, dia: Number(m[2]), s: m[3] ? Number(m[3]) : 0 };
}

const round10 = (v) => Math.round(v / 10) * 10;

/** One bar's figures before and after the edit, and whether anything moved. */
export function barFigures(bar) {
  const P = bar.payload, now = bar.now;
  const countOf = (n, s, dw) => (n > 0 ? n : s > 0 && dw > 0 ? Math.floor(dw / s + 1e-6) + 1 : 1);
  const before = { dia: P.dia, s: P.s, n: P.n, L: P.L, dw: P.dw, count: countOf(P.n, P.s, P.dw) };
  const call = now.l1 != null ? parseCallout(now.l1) : null;
  // the call-out decides the diameter and spacing; a count written in it (`7T16`) decides the count, otherwise the
  // group keeps its count (a run of bars, n = 0, follows the distribution width)
  const dia = call?.dia || P.dia, s = call ? call.s || (call.n ? 0 : P.s) : P.s, n = call?.n || P.n;
  const dL = now.pl != null && P.pl ? now.pl - P.pl : 0;
  const L = Math.max(0, round10(P.L + dL));
  const dw = now.dw != null ? Math.round(now.dw) : P.dw;
  const after = { dia, s, n, L, dw, count: countOf(n, s, dw) };
  const kgOf = (f) => (f.count * f.L / 1000) * barWeightPerM(f.dia);
  before.kg = r1(kgOf(before)); after.kg = r1(kgOf(after));
  const changed = before.dia !== after.dia || before.s !== after.s || before.count !== after.count || Math.abs(before.L - after.L) >= 10;
  return { id: bar.id, face: P.face, level: P.lv || '', l1: now.l1 || P.l1, l2: now.l2 || P.l2, before, after, changed };
}

/** The take-off change of an edited sheet: every changed bar and the steel difference by face and diameter. */
export function takeoffFromBars(bars) {
  const figures = bars.map(barFigures);
  const changed = figures.filter((f) => f.changed);
  const delta = { kg: 0, top_kg: 0, bottom_kg: 0, other_kg: 0, byDia: {} };
  for (const f of changed) {
    const d = f.after.kg - f.before.kg;
    delta.kg += d;
    if (f.face === 'T') delta.top_kg += d; else if (f.face === 'B') delta.bottom_kg += d; else delta.other_kg += d;
    for (const [sign, fig] of [[-1, f.before], [1, f.after]]) {
      const key = fig.dia;
      delta.byDia[key] = delta.byDia[key] || { dia: key, kg: 0, total_m: 0, count: 0 };
      delta.byDia[key].kg += sign * fig.kg;
      delta.byDia[key].total_m += sign * (fig.count * fig.L) / 1000;
      delta.byDia[key].count += sign * fig.count;
    }
  }
  for (const k of ['kg', 'top_kg', 'bottom_kg', 'other_kg']) delta[k] = r1(delta[k]);
  delta.byDia = Object.values(delta.byDia).map((d) => ({ ...d, kg: r1(d.kg), total_m: r1(d.total_m) })).filter((d) => d.kg || d.count).sort((a, b) => a.dia - b.dia);
  const level = (changed[0] || figures[0])?.level || '';
  return { bars: figures.length, changed: changed.length, level, delta, list: changed };
}

/**
 * The run's take-off with an edited sheet's change applied to its level (steel by face and diameter, the project
 * totals re-summed); the note says which file, who and when.
 */
export function applyTakeoff(quantities, levelId, change, note = {}) {
  const q = JSON.parse(JSON.stringify(quantities || { levels: [], totals: {} }));
  const level = q.levels.find((l) => l.id === levelId) || q.levels[0];
  if (!level) return q;
  const st = level.steel;
  st.kg = r1(st.kg + change.delta.kg);
  st.top_kg = r1((st.top_kg || 0) + change.delta.top_kg);
  st.bottom_kg = r1((st.bottom_kg || 0) + change.delta.bottom_kg);
  st.other_kg = r1((st.other_kg || 0) + change.delta.other_kg);
  for (const d of change.delta.byDia) {
    const row = st.byDia.find((x) => x.dia === d.dia);
    if (row) { row.kg = r1(row.kg + d.kg); row.total_m = r1(row.total_m + d.total_m); row.count = (row.count || 0) + d.count; }
    else st.byDia.push({ dia: d.dia, kg: r1(d.kg), total_m: r1(d.total_m), count: d.count });
  }
  st.byDia = st.byDia.filter((x) => x.kg > 0 || x.count > 0).sort((a, b) => a.dia - b.dia);
  const net = level.concrete?.net_area_m2;
  st.kg_per_m2 = net ? Math.round((st.kg / net) * 100) / 100 : st.kg_per_m2;
  st.kg_per_m3 = level.concrete?.total_m3 ? r1(st.kg / level.concrete.total_m3) : st.kg_per_m3;
  level.edited = [...(level.edited || []), { ...note, bars: change.changed, delta_kg: change.delta.kg }];
  // the project totals re-summed
  const sumBy = (get) => r1(q.levels.reduce((s, l) => s + (get(l) || 0), 0));
  const byDia = {};
  for (const l of q.levels) for (const d of l.steel.byDia || []) { byDia[d.dia] = byDia[d.dia] || { dia: d.dia, total_m: 0, kg: 0, count: 0 }; byDia[d.dia].total_m += d.total_m; byDia[d.dia].kg += d.kg; byDia[d.dia].count += d.count || 0; }
  q.totals = q.totals || {};
  q.totals.steel = {
    ...(q.totals.steel || {}),
    kg: sumBy((l) => l.steel.kg), top_kg: sumBy((l) => l.steel.top_kg), bottom_kg: sumBy((l) => l.steel.bottom_kg), other_kg: sumBy((l) => l.steel.other_kg), mesh_kg: sumBy((l) => l.steel.mesh_kg),
    byDia: Object.values(byDia).sort((a, b) => a.dia - b.dia).map((d) => ({ ...d, total_m: r1(d.total_m), kg: r1(d.kg) })),
  };
  const netAll = q.totals.concrete?.net_area_m2;
  if (netAll) q.totals.steel.kg_per_m2 = Math.round((q.totals.steel.kg / netAll) * 100) / 100;
  q.edited = [...(q.edited || []), { level: level.id, ...note, bars: change.changed, delta_kg: change.delta.kg }];
  return q;
}
