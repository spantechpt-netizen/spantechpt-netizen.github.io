/**
 * Reinforcement engine: development / lap lengths, bar splitting, and the
 * zone generators behind each rebar sheet.
 *
 * Code basis (applied unless the drawings say otherwise): SBC 304-18, the
 * Saudi Building Code concrete structures requirements, which adopts
 * ACI 318-14. Clause references below are to SBC 304-18 / ACI 318-14.
 */
import {
  bbox, ceilTo, chordsAtX, chordsAtY, circlePolygon, dist, edges, growRect,
  perimeter, pointInPolygon, polygonArea, rectPolygon, subtractIntervals,
} from './geometry.mjs';

export const DEFAULT_SPEC = {
  fc: 30, // MPa — assumed if the drawing does not state concrete grade
  fy: 420, // MPa — Grade 60 deformed bars (SASO ASTM A615)
  cover: 25, // mm top and bottom, slab not exposed to weather
  stock: 12000, // mm — standard stock bar length
  lambda: 1, // normal-weight concrete
  bottom: { dia: 12, spacing: 200 }, // bottom bonded mesh in PT zones, both ways
  // top bars over columns, both ways. Office rule: an interior column bar covers the drop panel when there is
  // one, otherwise `length` (4 m, set per slab); an edge column bar ends in a U at the edge and runs `edgeFactor`
  // of the interior length on top. rule: 'office' | 'code' (ln/6 each side, SBC 304-18 §8.7.5.5)
  topColumns: { dia: 16, spacing: 150, rule: 'office', length: 4000, edgeFactor: 0.7, dropMargin: 0, dropMax: 6000, minBeyond: 1500, wallAlongMax: 6000 },
  // perimeter bars between the column top bars (office rule): T12@150, a U of `total` length at a free edge
  // (equal top and bottom legs), an L of the same 4 m total at an edge beam (`beamLeg` down into the beam + `beamTop` on top)
  uEdge: { dia: 12, spacing: 150, total: 4000, beamLeg: 400, beamTop: 3600, leg: 1200 },
  uCircle: { dia: 12, spacing: 150, leg: 1200 }, // U-bars around circular regions
  edgeBars: { dia: 12, count: 2 }, // longitudinal bars inside edge U-bars, top and bottom
  ringBars: { dia: 12, count: 2 }, // ring bars around circular regions, top and bottom
  voids: { dia: 12, count: 2 }, // trimmer bars each side of a void, top and bottom
  openings: { dia: 16, count: 2, diagDia: 12, diagCount: 2, uDia: 12, uSpacing: 200, uLeg: 600 },
  sunken: { dia: 12, count: 2, uDia: 10, uSpacing: 200, uLeg: 600 }, // trimmers and hairpins at sunken-slab steps
  punching: { dia: 10, legSpacing: 100, extentFactor: 2.0, psDia: 12, rowSpacing: 100 }, // shop: preliminary links; design: the office PS detail (rows - legs - T12 @ rowSpacing)
  walls: { parallelBars: false, cornerDiagonals: false }, // design mode: the wall face gets the U-bars only unless these are switched on
  perimSpan: 12000, // design mode: one perimeter bar symbol every 12 m on a long indication line along the edge
  thicknessMesh: { dia: 10, spacing: 200 }, // office rule: the bottom mesh written at every change of slab thickness (per the design)
  drops: { dia: 12, spacing: 150, leg: 500 }, // office rule: the bottom mesh inside a column drop (detail 4 groups through the column, 500 legs at both ends)
  barOffset: 500, // design mode: the bar symbol sits beside the column (a vertical bar to its left, a horizontal one above it)
  pourStrip: { dia: 16, spacing: 200, length: 3000, uDia: 12, uSpacing: 200, uTotal: 2400, longDia: 12, longSpacing: 150, wall: { uTotal: 2500, uSlab: 2000, dia: 12, spacing: 200, length: 2000, longDia: 12, longSpacing: 150 } }, // PT details 3: the office pour strip detail; against a retaining wall: U-bar T12@200 L=2500 anchored in the wall, U-bar T12@200 L=2000 from the slab side, T12@200 T&B L=2000 from the wall face into the slab, T12@150 T&B along
  blockBeam: { dia: 16, count: 2, linkDia: 12, linkSpacing: 200, minWidth: 150, maxGap: 500 }, // detail 9 (office): a slab strip of 150..500 between two openings gets 2T16 T&B with T12@200 links
};

export const BAR_AREA = (dia) => (Math.PI * dia * dia) / 4;
export const barWeightPerM = (dia) => 0.006165 * dia * dia; // kg/m, density 7850 kg/m³

/**
 * Tension development length, SBC 304-18 §25.4.2.3 (ACI 318-14 Table 25.4.2.2),
 * simplified expressions with clear spacing / cover conditions satisfied.
 * Metric form: ld = fy·ψt·ψe / (2.1·λ·√f'c) · db for db ≤ 20 mm,
 *              ld = fy·ψt·ψe / (1.7·λ·√f'c) · db for db > 20 mm.
 */
export function developmentLength(spec, dia, { top = false, epoxy = false } = {}) {
  const psiT = top ? 1.3 : 1.0;
  const psiE = epoxy ? 1.2 : 1.0;
  const product = Math.min(psiT * psiE, 1.7);
  const k = dia <= 20 ? 2.1 : 1.7;
  const ld = (spec.fy * product) / (k * (spec.lambda || 1) * Math.sqrt(spec.fc)) * dia;
  return ceilTo(Math.max(ld, 300), 10);
}

/** Class B tension lap splice, §25.5.2.1: 1.3·ld, not less than 300 mm. */
export function lapLength(spec, dia, opts = {}) {
  return ceilTo(Math.max(1.3 * developmentLength(spec, dia, opts), 300), 50);
}

/** Standard 90° hook development, §25.4.3.1: 0.24·ψe·fy/(λ√f'c)·db ≥ max(8db, 150). */
export function hookDevelopmentLength(spec, dia) {
  const ldh = (0.24 * spec.fy) / ((spec.lambda || 1) * Math.sqrt(spec.fc)) * dia;
  return ceilTo(Math.max(ldh, 8 * dia, 150), 10);
}

/** 90° hook extension for a straight bar terminating at a free edge: 12·db, §25.3.1. */
export const hookLeg = (dia) => ceilTo(12 * dia, 10);

/** Summary table of lengths per diameter, used in the notes block. */
export function lengthTable(spec, dias = [10, 12, 14, 16, 18, 20, 25]) {
  return dias.map((dia) => ({
    dia,
    ld_bottom: developmentLength(spec, dia),
    ld_top: developmentLength(spec, dia, { top: true }),
    lap_bottom: lapLength(spec, dia),
    lap_top: lapLength(spec, dia, { top: true }),
    ldh: hookDevelopmentLength(spec, dia),
  }));
}

/**
 * Split a run of length L into stock pieces overlapping by `lap`. With
 * `stagger` the first piece is a half stock so adjacent bars lap in
 * different places (≤ 50 % of bars lapped at one section).
 * Returns cutting lengths rounded up to 10 mm.
 */
export function splitRun(L, { stock, lap, stagger = false }) {
  if (L <= stock) return [ceilTo(L, 10)];
  const pieces = [];
  let covered = 0;
  let first = true;
  while (covered < L - 1) {
    const start = first ? 0 : covered - lap;
    let len = Math.min(stock, L - start);
    if (first && stagger) len = Math.min(len, ceilTo(stock / 2, 100));
    pieces.push(ceilTo(len, 10));
    covered = start + len;
    first = false;
    if (pieces.length > 100) break;
  }
  return pieces;
}

/**
 * Accumulates bar entries and issues marks per (dia, shape, cutting length),
 * the way the reference drawings do (`T2-05` = fifth cutting length of the
 * top layer 2). Spacing is informational: the same mark may be placed at
 * different spacings in different rows.
 */
export class BarList {
  constructor(prefix = 'M') { this.prefix = prefix.endsWith('-') ? prefix : prefix + (prefix.length > 1 ? '-' : ''); this.entries = []; }

  add(e) {
    // e: { dia, shape, length, qty, spacing?, zone, note? }
    const key = `${e.dia}|${e.shape}|${e.length}|${e.note || ''}`;
    let m = this.entries.find((x) => x.key === key);
    if (!m) {
      m = { key, mark: '', dia: e.dia, shape: e.shape, length: e.length, spacings: new Set(), note: e.note || '', qty: 0, zones: new Set() };
      this.entries.push(m);
      this.rows(); // keep marks stable as entries arrive
    }
    m.qty += e.qty;
    if (e.spacing) m.spacings.add(e.spacing);
    if (e.zone) m.zones.add(e.zone);
    return m;
  }

  /** Sorted rows with marks, totals and weights. */
  rows() {
    const sorted = [...this.entries].sort((a, b) => a.dia - b.dia || a.shape.localeCompare(b.shape) || b.length - a.length);
    sorted.forEach((m, i) => { m.mark = `${this.prefix}${String(i + 1).padStart(2, '0')}`; });
    return sorted.map((m) => ({
      mark: m.mark, dia: m.dia, shape: m.shape, spacing: m.spacings.size === 0 ? '-' : m.spacings.size === 1 ? [...m.spacings][0] : 'VAR.', length: m.length, qty: m.qty,
      total_m: Math.round((m.length * m.qty) / 100) / 10,
      weight_kg: Math.round((m.length * m.qty / 1000) * barWeightPerM(m.dia) * 10) / 10,
      zones: [...m.zones].join(', '), note: m.note,
    }));
  }

  totals() {
    const rows = this.rows();
    const byDia = {};
    for (const r of rows) {
      byDia[r.dia] = byDia[r.dia] || { dia: r.dia, total_m: 0, weight_kg: 0 };
      byDia[r.dia].total_m += r.total_m;
      byDia[r.dia].weight_kg += r.weight_kg;
    }
    const weight = rows.reduce((s, r) => s + r.weight_kg, 0);
    return { weight_kg: Math.round(weight * 10) / 10, byDia: Object.values(byDia).map((d) => ({ ...d, total_m: Math.round(d.total_m * 10) / 10, weight_kg: Math.round(d.weight_kg * 10) / 10 })) };
  }
}

/** Merge several bar lists into one set of schedule rows (marks kept). */
export function mergeRows(...lists) {
  return lists.flatMap((l) => l.rows());
}
export function mergeTotals(...lists) {
  const rows = mergeRows(...lists);
  const byDia = {};
  for (const r of rows) { byDia[r.dia] = byDia[r.dia] || { dia: r.dia, total_m: 0, weight_kg: 0 }; byDia[r.dia].total_m += r.total_m; byDia[r.dia].weight_kg += r.weight_kg; }
  return { weight_kg: Math.round(rows.reduce((s, r) => s + r.weight_kg, 0) * 10) / 10, byDia: Object.values(byDia).map((d) => ({ ...d, total_m: Math.round(d.total_m * 10) / 10, weight_kg: Math.round(d.weight_kg * 10) / 10 })) };
}

// rows whose chords agree within `tol` are one group (a curved or skew edge otherwise gives one mark per bar)
const rowsSame = (a, b, tol = 5) => a.length === b.length && a.every((c, i) => Math.abs(c[0] - b[i][0]) < tol && Math.abs(c[1] - b[i][1]) < tol);

function openingCuts(level, axis, coord, cover) {
  // Intervals along `axis` where a bar at `coord` (perpendicular axis) crosses an opening.
  const cuts = [];
  for (const o of level.openings || []) {
    const poly = regionPolygon(o);
    const chords = axis === 'x' ? chordsAtY(poly, coord) : chordsAtX(poly, coord);
    for (const [a, b] of chords) cuts.push([a - cover, b + cover]);
  }
  return cuts;
}

export function regionPolygon(o) {
  if (o.kind === 'circle') return circlePolygon(o.cx, o.cy, o.r, 36);
  if (o.kind === 'rect') return rectPolygon(o.rect);
  return o.polygon;
}

export function regionBbox(o) { return bbox(regionPolygon(o)); }

/** Bars parallel to X are layer "2", bars parallel to Y are layer "1" (reference drawing convention). */
export const LAYER_CODE = { X: '2', Y: '1' };

/** Sheet: bottom mesh in PT zones (or over the whole slab when no zone is drawn). */
export function bottomMesh(level, spec) {
  const s = spec.bottom;
  const lap = lapLength(spec, s.dia);
  const lists = { X: new BarList('B2'), Y: new BarList('B1') };
  const zones = [];
  const cover = spec.cover;
  const ptZones = level.pt.zones.length ? level.pt.zones : [{ id: 'PT1', polygon: level.outline }];
  const groupTol = s.groupTol ?? 250;
  const lengthStep = s.lengthStep ?? 500;
  let varied = false;
  for (const zone of ptZones) {
    const poly = zone.polygon;
    const b = bbox(poly);
    for (const dir of ['X', 'Y']) {
      const along = dir === 'X' ? 'x' : 'y';
      const bars = lists[dir];
      const start = (dir === 'X' ? b.minY : b.minX) + cover + s.spacing / 2;
      const end = (dir === 'X' ? b.maxY : b.maxX) - cover;
      const groups = [];
      for (let c = start; c <= end; c += s.spacing) {
        let chords = dir === 'X' ? chordsAtY(poly, c) : chordsAtX(poly, c);
        chords = chords.map(([a, bb]) => [a + cover, bb - cover]).filter(([a, bb]) => bb - a > 300);
        chords = subtractIntervals(chords, openingCuts(level, along, c, cover));
        if (!chords.length) continue;
        const last = groups[groups.length - 1];
        if (last && rowsSame(last.ref, chords, groupTol)) {
          last.rows++; last.end = c;
          // the group bar covers every row of the group: union of the chords
          last.chords = last.chords.map(([a, bb], i) => [Math.min(a, chords[i][0]), Math.max(bb, chords[i][1])]);
          if (!rowsSame(last.chords, chords)) last.varied = true;
        } else groups.push({ chords, ref: chords, rows: 1, start: c, end: c });
      }
      if (groups.some((g) => g.varied)) varied = true;
      // a curved / skew edge: many one- or two-row groups; their cut lengths are binned to `lengthStep`
      // and consecutive groups that fall in the same bins are merged into one drawn group
      const curved = groups.filter((g) => g.rows < 3).length >= 5 || groups.length > 8;
      if (curved) {
        varied = true;
        const binned = (g) => g.chords.map(([a, bb]) => ceilTo(bb - a, lengthStep)).join('|');
        const merged = [];
        for (const g of groups) {
          const last = merged[merged.length - 1];
          if (last && last.chords.length === g.chords.length && binned(last) === binned(g)) {
            last.rows += g.rows; last.end = g.end;
            last.chords = last.chords.map(([a, bb], i) => [Math.min(a, g.chords[i][0]), Math.max(bb, g.chords[i][1])]);
          } else merged.push({ ...g, varied: true });
        }
        groups.length = 0; groups.push(...merged);
      }
      groups.forEach((g, gi) => {
        g.id = `${zone.id}-${LAYER_CODE[dir] === '2' ? 'B2' : 'B1'}-${gi + 1}`;
        g.runs = g.chords.map(([a, bb]) => {
          const L = bb - a;
          const pieces = splitRun(L, { stock: spec.stock, lap }).map((len) => (curved ? ceilTo(len, lengthStep) : len));
          const marks = pieces.map((len) => bars.add({ dia: s.dia, shape: 'STR', length: len, qty: g.rows, spacing: s.spacing, zone: g.id }));
          return { a, b: bb, L, pieces, marks };
        });
      });
      zones.push({ id: `${zone.id}-${dir}`, zoneId: zone.id, dir, code: `B${LAYER_CODE[dir]}`, polygon: poly, groups, spacing: s.spacing, dia: s.dia });
    }
  }
  return {
    zones, lists, lap, dia: s.dia, spacing: s.spacing, varied,
    assumptions: [
      ...(level.pt.zones.length ? [] : ['No PT zone boundary found on the drawing: bottom mesh applied over the whole slab.']),
      ...(varied ? [`Mesh rows at curved / skew edges: rows are grouped within ${groupTol} mm and cut lengths are scheduled in ${lengthStep} mm steps (the group's longest row rounded up); bars are cut to the edge less cover on site.`] : []),
    ],
  };
}

function neighbour(level, col, dir, sign) {
  // Nearest column along dir ('x' or 'y') on the same line (within a 1.5 m band).
  const perp = dir === 'x' ? 'cy' : 'cx';
  const alongKey = dir === 'x' ? 'cx' : 'cy';
  // a long support (wall) looks for the next support anywhere along its own length
  const halfPerp = (col.shape === 'circle' ? (col.d || 0) : (dir === 'x' ? col.h : col.w) || 0) / 2;
  let best = null;
  for (const o of level.columns) {
    if (o === col || o.id === col.id) continue;
    if (Math.abs(o[perp] - col[perp]) > halfPerp + 1500) continue;
    const d = (o[alongKey] - col[alongKey]) * sign;
    if (d <= 0) continue;
    if (!best || d < best.d) best = { col: o, d };
  }
  return best;
}

function edgeDistance(level, col, dir, sign, cover) {
  // Distance from column centre to slab edge along dir, in direction sign: a march from the centre to the first
  // point outside the outline (robust at notches and where the outline has a vertex on the column's axis)
  // (marched from the centre and from either side of the column's footprint: a column whose axis lies on an
  // outline edge, half in a perimeter wall, still reads the slab on its far side)
  const across = col.shape === 'circle' ? col.d : dir === 'x' ? col.h : col.w;
  const step = 25, max = 15000;
  let best = -1;
  for (const off of [0, across / 2 - 30, -(across / 2 - 30)]) {
    const c0 = dir === 'x' ? { x: col.cx, y: col.cy + off } : { x: col.cx + off, y: col.cy };
    if (!pointInPolygon(c0, level.outline)) continue;
    let d = 0;
    while (d < max) { const q = dir === 'x' ? { x: c0.x + sign * (d + step), y: c0.y } : { x: c0.x, y: c0.y + sign * (d + step) }; if (!pointInPolygon(q, level.outline)) break; d += step; }
    if (d > best) best = d; // d = max: no edge within reach in this direction
  }
  if (best >= 0) return Math.max(0, best - cover);
  const chords = dir === 'x' ? chordsAtY(level.outline, col.cy) : chordsAtX(level.outline, col.cx);
  const c = dir === 'x' ? col.cx : col.cy;
  for (const [a, b] of chords) if (c >= a - 1 && c <= b + 1) return (sign > 0 ? b - c : c - a) - cover;
  return 2000; // column outside the outline chords (e.g. on a notch); conservative stub
}

/**
 * Office rule: a top bar that ends at the outer slab edge or at an opening
 * ends in a U (down the slab depth and back 500 mm at the bottom). Returns
 * the extra length added at such an end, its label and the shape code.
 */
export function topEdgeEnd(level, spec) {
  const leg = ceilTo((level.thickness - 2 * spec.cover) + U_BOTTOM_LEG, 10);
  return { leg, label: `U${U_BOTTOM_LEG}`, note: `U end: ${level.thickness - 2 * spec.cover} down + ${U_BOTTOM_LEG} bottom` };
}
export const U_BOTTOM_LEG = 500;

/**
 * Office rule for a top bar ending at the slab boundary: a U (500 bottom leg) at a free edge, an L
 * (`uEdge.beamLeg` down into the beam) where the outer edge carries a beam parallel to it. The
 * nearest outline segment to the bar end decides; an opening edge is always a U.
 */
export function edgeEndAt(level, spec, p) {
  const u = topEdgeEnd(level, spec);
  if ((level.jointEdges || []).some((e) => { const L = dist(e.a, e.b) || 1; const t = Math.max(0, Math.min(L, ((p.x - e.a.x) * (e.b.x - e.a.x) + (p.y - e.a.y) * (e.b.y - e.a.y)) / L)); return Math.hypot(p.x - (e.a.x + (e.b.x - e.a.x) / L * t), p.y - (e.a.y + (e.b.y - e.a.y) / L * t)) < 600; })) return { type: null, leg: 0, label: '', note: 'continues into the neighbouring part' };
  const outline = level.outline || [];
  let best = null;
  for (let i = 0; i < outline.length; i++) {
    const a = outline[i], b = outline[(i + 1) % outline.length];
    const L = dist(a, b) || 1;
    const t = Math.max(0, Math.min(L, ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / L));
    const d = Math.hypot(p.x - (a.x + ((b.x - a.x) / L) * t), p.y - (a.y + ((b.y - a.y) / L) * t));
    if (!best || d < best.d) best = { d, a, b };
  }
  if (best && best.d < 600 && edgeHasBeam(level, best.a, best.b)) {
    const leg = spec.uEdge?.beamLeg || 400;
    return { type: 'L', leg, label: `L${leg}`, note: `L end: ${leg} down into the edge beam` };
  }
  return { type: 'U', ...u };
}

/**
 * What lines one side of an opening: 'beam' (a beam line parallel within 400 mm over half the
 * side), 'wall' (a wall polygon edge), 'column' (a column face), or null for a free side.
 */
export function sideLining(level, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
  const ux = dx / len, uy = dy / len;
  const distToSeg = (p, e) => { const L2 = e.length * e.length || 1; const t = Math.max(0, Math.min(1, ((p.x - e.a.x) * e.dx + (p.y - e.a.y) * e.dy) / L2)); return Math.hypot(p.x - (e.a.x + e.dx * t), p.y - (e.a.y + e.dy * t)); };
  const covers = (sg) => {
    if (sg.length < 200) return false;
    const vx = sg.dx / sg.length, vy = sg.dy / sg.length;
    if (Math.abs(ux * vx + uy * vy) < 0.95) return false;
    const t1 = (sg.a.x - a.x) * ux + (sg.a.y - a.y) * uy, t2 = (sg.b.x - a.x) * ux + (sg.b.y - a.y) * uy;
    const lo = Math.max(0, Math.min(t1, t2)), hi = Math.min(len, Math.max(t1, t2));
    if (hi - lo < 0.5 * len) return false;
    const mid = { x: a.x + ux * (lo + hi) / 2, y: a.y + uy * (lo + hi) / 2 };
    return distToSeg(mid, sg) < 400;
  };
  const segOf = (p, q) => { const ddx = q.x - p.x, ddy = q.y - p.y; return { a: p, b: q, dx: ddx, dy: ddy, length: Math.hypot(ddx, ddy) }; };
  for (const w of level.walls || []) if (w.polygon && edges(w.polygon).some(covers)) return 'wall';
  for (const bm of level.beams || []) if (covers(segOf(bm.a, bm.b))) return 'beam';
  for (const c of level.columns || []) {
    const poly = c.shape === 'circle' ? regionPolygon({ kind: 'circle', cx: c.cx, cy: c.cy, r: c.d / 2 }) : [{ x: c.cx - c.w / 2, y: c.cy - c.h / 2 }, { x: c.cx + c.w / 2, y: c.cy - c.h / 2 }, { x: c.cx + c.w / 2, y: c.cy + c.h / 2 }, { x: c.cx - c.w / 2, y: c.cy + c.h / 2 }];
    if (edges(poly).some(covers)) return 'column';
  }
  return null;
}

/**
 * Office rule: an opening enclosed by concrete walls, beams (or column faces at its corners)
 * needs no additional trimmer bars, only the L-bars along its beams and the wall U-bars.
 */
export function openingLined(level, region) {
  const poly = regionPolygon(region);
  const sides = edges(poly).filter((e) => e.length > 200);
  if (!sides.length) return false;
  return sides.every((side) => sideLining(level, side.a, side.b) != null);
}

/**
 * True when the slab edge a->b carries an edge beam: a beam line lies ON the edge (within 60 mm, over half
 * the edge or 2 m) and its partner line runs parallel 150..900 mm inside (the beam's inner face). A beam
 * merely near the edge (an interior beam beside it) is not an edge beam. `spec.edgeBeams === false` disables.
 */
export function edgeHasBeam(level, a, b) {
  if (level.noEdgeBeams) return false;
  const L = dist(a, b) || 1;
  const ux = (b.x - a.x) / L, uy = (b.y - a.y) / L;
  const along = (p) => (p.x - a.x) * ux + (p.y - a.y) * uy;
  const off = (p) => (p.x - a.x) * -uy + (p.y - a.y) * ux; // signed distance from the edge line
  const parallel = (bm) => { const bl = dist(bm.a, bm.b) || 1; return Math.abs(ux * (bm.b.x - bm.a.x) / bl + uy * (bm.b.y - bm.a.y) / bl) >= 0.98; };
  const coverage = (bm) => { const t1 = along(bm.a), t2 = along(bm.b); const lo = Math.max(0, Math.min(t1, t2)), hi = Math.min(L, Math.max(t1, t2)); return hi - lo; };
  const beams = (level.beams || []).filter(parallel);
  const inSide = Math.sign(off(centroidOf(level.outline)) || 1);
  // a beam body (RAM beam object, a band): its outer face lies on the edge and its axis sits inside it
  const bodyOnEdge = (bm) => bm.polygon && bm.polygon.some((p, i) => { const q = bm.polygon[(i + 1) % bm.polygon.length]; return Math.abs(off(p)) < 60 && Math.abs(off(q)) < 60 && coverage({ a: p, b: q }) > Math.min(1000, 0.5 * L); }) && (off(bm.a) + off(bm.b)) / 2 * inSide > 50 && coverage(bm) > 1000;
  if (beams.some(bodyOnEdge)) return true;
  // a beam drawn as two face lines: one on the edge, the other 150 to 900 inside
  const onEdge = beams.filter((bm) => !bm.polygon && Math.abs(off(bm.a)) < 60 && Math.abs(off(bm.b)) < 60 && (coverage(bm) > 0.5 * L || coverage(bm) > 2000));
  if (!onEdge.length) return false;
  return beams.some((bm) => { const d = (off(bm.a) + off(bm.b)) / 2 * inSide; return d > 150 && d < 900 && coverage(bm) > 1000; });
}
function centroidOf(poly) { let x = 0, y = 0; for (const p of poly) { x += p.x; y += p.y; } return { x: x / (poly.length || 1), y: y / (poly.length || 1) }; }

export function edgeRunsBetweenColumns(level, a, b, h, bandOf) {
  const L = dist(a, b) || 1;
  const ux = (b.x - a.x) / L, uy = (b.y - a.y) / L;
  const cuts = [];
  // (an interior beam whose group of top bars reaches this edge stops the perimeter bars like a column's group)
  const supports = [...level.columns, ...(level.walls || []).filter((w) => w.polygon && w.t && !w.core).map((w) => ({ id: w.id, shape: 'rect', cx: w.cx, cy: w.cy, w: w.w, h: w.h, isWall: true })), ...(level.beams || []).filter((bm) => bm.polygon && bm.interior).map((bm) => ({ id: bm.id, shape: 'rect', cx: bm.cx, cy: bm.cy, w: bm.w, h: bm.h, isWall: true, isBeam: true, along: bm.along }))];
  for (const c of supports) {
    const t = (c.cx - a.x) * ux + (c.cy - a.y) * uy;
    const off = Math.abs((c.cx - a.x) * -uy + (c.cy - a.y) * ux);
    const size = c.shape === 'circle' ? c.d : Math.max(c.w, c.h);
    const reach = Math.max(size, 1000, (bandOf && bandOf(c, 'across')) || 0) / 2 + 500;
    if (t < -size || t > L + size || off > reach) continue; // not a support on this edge
    const along = Math.abs(ux) > 0.7 ? 'x' : 'y';
    if (c.isBeam && c.along !== along) continue; // a beam ending at this edge: its group sits along the beam, away from the edge
    // the perimeter bars stop where the support's bars along the edge are (their group width), else at c2 + 1.5h each side
    const band = (bandOf && bandOf(c, along)) || (c.shape === 'circle' ? c.d : (along === 'x' ? c.w : c.h)) + 3 * h;
    cuts.push([t - band / 2, t + band / 2]);
  }
  return subtractIntervals([[0, L]], cuts).filter(([p, q]) => q - p > 300);
}

/** Sheet: additional top bars over columns (PT two-way slab, §8.7.5.5). */
export function topAtColumns(level, spec) {
  const s = spec.topColumns;
  const h = level.thickness;
  const cover = spec.cover;
  const lists = { x: new BarList('T2'), y: new BarList('T1') };
  const types = [];
  const columns = [];
  const checks = [];
  // walls below carry top bars too: a wall is treated as a long rectangular support (bars across it
  // along its length, bars along it within t + 3h), without joining the grid or the punching sheet
  // (an isolated wall gets the two column groups over it; a core wall - three or more walls around an opening - keeps the wall U-bars)
  const wallSupports = (level.walls || []).filter((w) => w.polygon && w.t).map((w) => ({ id: w.id, shape: 'rect', cx: w.cx, cy: w.cy, w: w.w, h: w.h, isWall: true, core: !!w.core, skipAlong: Math.max(w.w, w.h) > (s.wallAlongMax || 6000) ? (w.w >= w.h ? 'x' : 'y') : null }));
  // office rule: an interior beam (slab on both sides) carries a group of top bars across it, `length` (4 m) or
  // `minBeyond` (1.5 m) past each face whichever is larger, distributed along the beam; nothing along it
  const beamSupports = (level.beams || []).filter((b) => b.polygon && b.interior).map((b) => ({ id: b.id, shape: 'rect', cx: b.cx, cy: b.cy, w: b.w, h: b.h, isWall: true, isBeam: true, core: false, skipAlong: b.along, beam: b }));
  if (!level.maxSpan) {
    let mx = 0;
    for (const c of level.columns) for (const dir of ['x', 'y']) for (const sign of [-1, 1]) { const nb = neighbour(level, c, dir, sign); if (nb && nb.d > mx) mx = nb.d; }
    level.maxSpan = mx || 8000;
  }
  for (const col of [...level.columns, ...wallSupports, ...beamSupports]) {
    const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
    const per = {};
    // spans to the next support in each direction, found first so that the strip width
    // (Acf) of one direction can use the span of the other
    const spanOf = {};
    for (const dir of ['x', 'y']) {
      const c1 = size[dir];
      const ext = {}, hooks = {}, spans = [];
      const nbs = {}, toEdges = {};
      for (const sign of [-1, 1]) {
        const nb = neighbour(level, col, dir, sign);
        let toEdge = edgeDistance(level, col, dir, sign, cover);
        // a drawing joint with the neighbouring part is not a slab edge: the slab goes on
        if (level.jointEdges?.length) {
          const hit = dir === 'x' ? { x: col.cx + sign * (toEdge + c1 / 2), y: col.cy } : { x: col.cx, y: col.cy + sign * (toEdge + c1 / 2) };
          if (level.jointEdges.some((e) => { const L = dist(e.a, e.b) || 1; const t = Math.max(0, Math.min(L, ((hit.x - e.a.x) * (e.b.x - e.a.x) + (hit.y - e.a.y) * (e.b.y - e.a.y)) / L)); return Math.hypot(hit.x - (e.a.x + (e.b.x - e.a.x) / L * t), hit.y - (e.a.y + (e.b.y - e.a.y) / L * t)) < 400; })) toEdge = 1e9;
        }
        nbs[sign] = nb; toEdges[sign] = toEdge;
        if (nb) spans.push(nb.d); else { const cap = ceilTo(Math.max(level.maxSpan || 0, 6 * 1.5 * h) / 6, 50); spans.push(2 * Math.min(toEdge, cap * 6)); }
      }
      if (col.isBeam && col.skipAlong === dir) {
        // along the beam: nothing is drawn; the group across it is distributed over the beam's own length
        ext[-1] = 0; ext[1] = 0;
      } else if ((s.rule || 'office') === 'office' && (!col.isWall || !col.core)) {
        // office rule: interior bar covers the drop panel or runs `length` in total; an edge column bar
        // ends in a U at the slab edge and continues `edgeFactor` x the interior length on top
        // a drop panel is a thickened zone of limited size around the column (`dropMax`, 6 m); a long thickened strip is not one
        const drop = col.isBeam ? null : (level.thickZones || []).find((z) => pointInPolygon({ x: col.cx, y: col.cy }, z.polygon) && Math.max(bbox(z.polygon).w, bbox(z.polygon).h) <= (s.dropMax || 6000));
        // with a drop panel the bars are exactly as long as the drop (+ `dropMargin` each side, 0 by default);
        // without one they are `length` (4 m) in total
        let Lint = s.length || 4000;
        if (drop) { const zb = bbox(drop.polygon); Lint = ceilTo((dir === 'x' ? zb.w : zb.h) + 2 * (s.dropMargin ?? 0), 10); }
        // office rule: the bars project at least `minBeyond` (1.5 m) past the face of the column / wall on each side
        const beyond = s.minBeyond ?? 1500;
        Lint = Math.max(Lint, ceilTo(c1 + 2 * beyond, 10));
        const half = (Lint - c1) / 2;
        // an edge column: the bar would reach the slab edge, or end inside the perimeter U-bar zone (the U-bar's top
        // leg from the edge): then it runs to the edge and ends in the U, and the perimeter U-bars stop before / after it
        const uZone = spec.uEdge?.total ? Math.max(0, (spec.uEdge.total - (h - 2 * cover)) / 2) : 1200;
        const edgeSign = [-1, 1].find((sg) => toEdges[sg] - c1 / 2 - half < uZone);
        if (edgeSign == null) { ext[-1] = half; ext[1] = half; }
        else {
          const other = -edgeSign;
          ext[edgeSign] = Math.max(toEdges[edgeSign] - c1 / 2, 0); hooks[edgeSign] = true;
          // the far side still reaches the drop panel edge (the interior half) and at least `minBeyond` past the face
          ext[other] = Math.max(ceilTo((s.edgeFactor ?? 0.7) * Lint, 50) - ext[edgeSign] - c1, beyond, drop ? half : 0);
          if (toEdges[other] - c1 / 2 < ext[other]) { ext[other] = Math.max(toEdges[other] - c1 / 2, 0); hooks[other] = true; } // corner column: U both ends
        }
        // office rule: a bar across a beam that reaches an adjacent parallel beam is shortened to end over it (its far face)
        if (col.isBeam) {
          const alongKey = col.skipAlong;
          const myLo = alongKey === 'x' ? col.cx - col.w / 2 : col.cy - col.h / 2, myHi = alongKey === 'x' ? col.cx + col.w / 2 : col.cy + col.h / 2;
          for (const sign of [-1, 1]) {
            for (const nb of beamSupports) {
              if (nb === col || nb.skipAlong !== alongKey) continue;
              const nLo = alongKey === 'x' ? nb.cx - nb.w / 2 : nb.cy - nb.h / 2, nHi = alongKey === 'x' ? nb.cx + nb.w / 2 : nb.cy + nb.h / 2;
              if (Math.min(myHi, nHi) - Math.max(myLo, nLo) < 500) continue; // not alongside this beam
              const centre = (dir === 'x' ? nb.cx - col.cx : nb.cy - col.cy) * sign;
              const nbHalf = (dir === 'x' ? nb.w : nb.h) / 2;
              const dNear = centre - nbHalf, dFar = centre + nbHalf;
              if (dNear <= c1 / 2 || c1 / 2 + ext[sign] <= dNear) continue; // behind, or not reached
              ext[sign] = Math.min(ext[sign], Math.max(dFar - c1 / 2, 0));
              hooks[sign] = false;
            }
          }
        }
      } else {
        for (const sign of [-1, 1]) {
          const nb = nbs[sign], toEdge = toEdges[sign];
          if (nb) {
            const nbSize = nb.col.shape === 'circle' ? nb.col.d : (dir === 'x' ? nb.col.w : nb.col.h);
            const ln = nb.d - c1 / 2 - nbSize / 2;
            let e = ceilTo(ln / 6, 50);
            if (c1 / 2 + e > toEdge) { e = Math.max(toEdge - c1 / 2, 0); hooks[sign] = true; }
            ext[sign] = e;
          } else {
            // no support on this side: the bar runs to the slab edge, but never further than
            // a sixth of the longest span found in the level (a wall at the far end of a slab
            // must not pull the bars across the whole slab)
            const cap = ceilTo(Math.max(level.maxSpan || 0, 6 * 1.5 * h) / 6, 50);
            const toEdgeExt = Math.max(toEdge - c1 / 2, 0);
            ext[sign] = Math.min(toEdgeExt, cap);
            hooks[sign] = ext[sign] === toEdgeExt;
          }
        }
      }
      spanOf[dir] = { ext, hooks, spans };
    }
    for (const dir of ['x', 'y']) {
      const c1 = size[dir];
      const c2 = size[dir === 'x' ? 'y' : 'x'];
      const { ext, hooks, spans } = spanOf[dir];
      const other = spanOf[dir === 'x' ? 'y' : 'x'].spans;
      // Minimum bonded reinforcement over the column: As = 0.00075·Acf (§8.6.2.3),
      // Acf = h × larger tributary width of the strip. Over a wall only the span
      // across the wall is a slab span (its own length is not).
      const l2 = col.isWall ? (dir === 'x' ? (size.x > size.y ? Math.max(...other) : Math.max(...spans)) : (size.y > size.x ? Math.max(...other) : Math.max(...spans)))
        : Math.max(...spans, ...other);
      // office rule: the bars of one direction are distributed over the length of the crossing bars at the
      // same column (the two groups cover the same square); code rule: within c2 + 1.5h each side (§8.7.5.5.1)
      const o = spanOf[dir === 'x' ? 'y' : 'x'];
      const otherStraight = o.ext[-1] + c2 + o.ext[1];
      const band = (s.rule || 'office') === 'office' && !col.isWall ? otherStraight : c2 + 3 * h;
      let n = Math.max(4, Math.floor(band / s.spacing) + 1);
      const asReq = 0.00075 * h * l2;
      const nReq = col.isWall ? 0 : Math.ceil(asReq / BAR_AREA(s.dia)); // §8.6.2.3 is a column rule; over a wall the spacing governs
      if (nReq > n) n = nReq;
      const straight = Math.round((ext[-1] + c1 + ext[1]) / 10) * 10; // (column sizes read from a drawing carry float noise)
      // a top bar ending at the slab edge ends in a U (500 bottom leg), or in an L where the edge carries a beam
      const ends = {};
      for (const sign of [-1, 1]) {
        if (!hooks[sign]) continue;
        const endPt = dir === 'x' ? { x: col.cx + sign * (c1 / 2 + ext[sign]), y: col.cy } : { x: col.cx, y: col.cy + sign * (c1 / 2 + ext[sign]) };
        const end = edgeEndAt(level, spec, endPt);
        if (end.type) ends[sign] = end; else hooks[sign] = false; // the bar simply continues into the neighbouring part
      }
      const legs = (ends[-1]?.leg || 0) + (ends[1]?.leg || 0);
      const length = ceilTo(straight + legs, 10);
      const shape = [-1, 1].map((sg) => ends[sg]?.type || '').join('') || 'STR';
      const first = ends[-1] || ends[1] || topEdgeEnd(level, spec);
      per[dir] = { ext, hooks, hookTypes: { [-1]: ends[-1]?.type || null, [1]: ends[1]?.type || null }, hookLabels: { start: ends[-1]?.label, end: ends[1]?.label }, n, length, shape, band, asReq: Math.round(asReq), asProv: Math.round(n * BAR_AREA(s.dia)), straight, hookLeg: first.leg, hookLabel: first.label, c1, code: dir === 'x' ? 'T2' : 'T1' };
      checks.push({ column: col.id, dir: dir.toUpperCase(), asReq: Math.round(asReq), asProv: Math.round(n * BAR_AREA(s.dia)), n });
    }
    const key = `${per.x.length}|${per.x.n}|${per.x.shape}|${per.y.length}|${per.y.n}|${per.y.shape}`;
    let type = types.find((t) => t.key === key);
    if (!type) {
      type = { key, id: `TC${types.length + 1}`, x: per.x, y: per.y, columns: [] };
      types.push(type);
    }
    type.columns.push(col.id);
    columns.push({ col, type, per });
  }
  for (const t of types) {
    for (const dir of ['x', 'y']) {
      const p = t[dir];
      p.mark = lists[dir].add({ dia: s.dia, shape: p.shape, length: p.length, qty: p.n * t.columns.length, spacing: s.spacing, zone: t.id, note: p.shape === 'STR' ? '' : /L/.test(p.shape) && !/U/.test(p.shape) ? `L end: ${spec.uEdge?.beamLeg || 400} down into the edge beam` : topEdgeEnd(level, spec).note });
    }
  }
  return { types, columns, lists, checks, dia: s.dia, spacing: s.spacing, rule: s.rule || 'office', length: s.length || 4000, edgeFactor: s.edgeFactor ?? 0.7, uEnd: topEdgeEnd(level, spec) };
}

/** Sheet: U-bars along slab edges and around circular regions. */
export function uBars(level, spec) {
  const h = level.thickness;
  const cover = spec.cover;
  const bars = new BarList('U');
  const web = h - 2 * cover;
  const edgeItems = [];
  const circleItems = [];
  const assumptions = [];

  const edgeList = level.ubar.edges === 'all' ? edges(level.outline) : level.ubar.edges.map((e) => ({ a: e.a, b: e.b, length: dist(e.a, e.b), dx: e.b.x - e.a.x, dy: e.b.y - e.a.y }));
  const su = spec.uEdge, se = spec.edgeBars;
  const lapE = lapLength(spec, se.dia);
  // office perimeter rule: T12@150 between the column top bars, a symmetric U at a free edge, an L at an edge beam
  const uLegTop = ceilTo((su.total - web) / 2, 10);
  const uLen = ceilTo(2 * uLegTop + web, 10);
  const lLen = su.beamLeg + su.beamTop;
  edgeList.forEach((e, i) => {
    if (e.length < 2 * su.spacing) return;
    const beam = edgeHasBeam(level, e.a, e.b);
    const runs = edgeRunsBetweenColumns(level, e.a, e.b, h);
    const n = runs.reduce((sum, [p, q]) => sum + Math.floor((q - p) / su.spacing) + 1, 0);
    if (!n) return;
    const uMark = beam
      ? bars.add({ dia: su.dia, shape: 'L', length: lLen, qty: n, spacing: su.spacing, zone: `E${i + 1}`, note: `${su.beamLeg} in beam + ${su.beamTop} top` })
      : bars.add({ dia: su.dia, shape: 'U', length: uLen, qty: n, spacing: su.spacing, zone: `E${i + 1}`, note: `legs ${uLegTop} T&B` });
    const runL = e.length - 2 * cover;
    const pieces = splitRun(runL, { stock: spec.stock, lap: lapE });
    const marks = pieces.map((len) => bars.add({ dia: se.dia, shape: 'STR', length: len, qty: 2 * se.count, zone: `E${i + 1}`, note: 'edge bar T&B' }));
    edgeItems.push({ id: `E${i + 1}`, a: e.a, b: e.b, length: e.length, n, beam, runs, leg: beam ? su.beamTop : uLegTop, uMark, marks: [...new Set(marks)], pieces });
  });

  const sc = spec.uCircle, sr = spec.ringBars;
  level.ubar.circles.forEach((c, i) => {
    const rOut = c.r + cover;
    const n = Math.ceil((2 * Math.PI * rOut) / sc.spacing);
    const uL = ceilTo(2 * sc.leg + web, 10);
    const uMark = bars.add({ dia: sc.dia, shape: 'U', length: uL, qty: n, spacing: sc.spacing, zone: c.id, note: `legs ${sc.leg}` });
    const ringR = rOut + sc.dia + sr.dia / 2;
    const lapR = lapLength(spec, sr.dia);
    const ringL = ceilTo(2 * Math.PI * ringR + lapR, 10);
    const ringPieces = splitRun(ringL, { stock: spec.stock, lap: lapR });
    const ringMarks = ringPieces.map((len) => bars.add({ dia: sr.dia, shape: 'RING', length: len, qty: 2 * sr.count, zone: c.id, note: `R=${Math.round(ringR)}` }));
    circleItems.push({ ...c, n, uMark, ringMarks: [...new Set(ringMarks)], ringR });
  });
  return { edgeItems, circleItems, bars, assumptions, uEdge: su, uCircle: sc, edgeBars: se, ringBars: sr, uLen, lLen, uLegTop, web };
}

/**
 * Trimmer bars around a rectangular / polygonal region. Each edge gets `count`
 * bars top and bottom, parallel to the edge, anchored ld beyond the corners.
 * Bars that would leave the slab are stopped at the edge with a hook.
 */
function trimmersAround(level, spec, region, { dia, count }, bars, lap) {
  const cover = spec.cover;
  const ld = developmentLength(spec, dia, { top: true });
  const poly = regionPolygon(region);
  const items = [];
  edges(poly).forEach((e, i) => {
    const ux = e.dx / e.length, uy = e.dy / e.length;
    // Outward normal: polygon may be either orientation, pick the side outside the region.
    let nx = -uy, ny = ux;
    const mid = { x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 };
    if (pointInPolygon({ x: mid.x + nx * 10, y: mid.y + ny * 10 }, poly)) { nx = -nx; ny = -ny; }
    const hooks = {};
    const ext = {};
    for (const [sign, p] of [[-1, e.a], [1, e.b]]) {
      // Extend beyond the corner along the edge direction, clipped by the slab outline.
      const probe = { x: p.x + sign * ux * ld, y: p.y + sign * uy * ld };
      if (pointInPolygon(probe, level.outline)) ext[sign] = ld;
      else {
        // find distance to slab boundary by stepping
        let d = 0;
        for (; d < ld; d += 25) if (!pointInPolygon({ x: p.x + sign * ux * d, y: p.y + sign * uy * d }, level.outline)) break;
        ext[sign] = Math.max(d - cover, 0);
        hooks[sign] = true;
      }
    }
    const hookN = (hooks[-1] ? 1 : 0) + (hooks[1] ? 1 : 0);
    const straight = e.length + ext[-1] + ext[1];
    const length = ceilTo(straight + hookN * hookLeg(dia), 10);
    const shape = hookN === 0 ? 'STR' : hookN === 1 ? 'L' : 'C';
    const pieces = length > spec.stock ? splitRun(length, { stock: spec.stock, lap }) : [length];
    const marks = pieces.map((len) => bars.add({ dia, shape: pieces.length > 1 ? 'STR' : shape, length: len, qty: 2 * count, zone: region.id, note: 'T&B' }));
    const offsets = [];
    for (let k = 0; k < count; k++) offsets.push(cover + dia / 2 + k * 75);
    items.push({ edge: e, ux, uy, nx, ny, ext, hooks, length, shape, marks: [...new Set(marks)], offsets, ld });
  });
  return items;
}

/** Sheet: reinforcement around voids / acuars and sunken slabs. */
export function aroundVoids(level, spec) {
  const bars = new BarList('V');
  const sv = spec.voids;
  const lap = lapLength(spec, sv.dia, { top: true });
  const regions = level.voids.map((v) => ({ kind: 'VOID', region: v, trimmers: trimmersAround(level, spec, v, sv, bars, lap) }));
  const ss = spec.sunken || { dia: 12, count: 2, uDia: 10, uSpacing: 200, uLeg: 600 };
  const h = level.thickness;
  const uLen = ceilTo(2 * ss.uLeg + (h - 2 * spec.cover), 10);
  for (const sk of level.sunken || []) {
    const trimmers = trimmersAround(level, spec, sk, ss, bars, lap);
    const per = perimeter(regionPolygon(sk));
    const nU = Math.max(0, Math.floor((per - 4 * spec.cover) / ss.uSpacing));
    const uMark = nU ? bars.add({ dia: ss.uDia, shape: 'U', length: uLen, qty: nU, spacing: ss.uSpacing, zone: sk.id, note: `legs ${ss.uLeg}` }) : null;
    regions.push({ kind: 'SUNKEN', region: sk, trimmers, uMark, nU });
  }
  return { regions, bars, dia: sv.dia, count: sv.count, ld: developmentLength(spec, sv.dia, { top: true }), sunken: ss, uLen };
}

/**
 * Punching shear links around columns: minimum detailing arrangement per
 * SBC 304-18 §8.7.6 / §22.6.8 (first row at d/2 from the face, rows at d/2,
 * legs along the face at ~100 mm). Extent 2h beyond the face is an
 * assumption: the number of rows is to be verified against the punching
 * design (Vu) before fabrication.
 */
export function punching(level, spec) {
  const sp = spec.punching || { dia: 10, legSpacing: 100, extentFactor: 2.0 };
  const h = level.thickness;
  const cover = spec.cover;
  const d = h - cover - 16;
  const rowSpacing = ceilTo(Math.max(d / 2, 50), 5) > d / 2 ? Math.floor(d / 2 / 5) * 5 : Math.floor(d / 2 / 5) * 5;
  const extent = sp.extentFactor * h;
  const rows = Math.max(2, Math.ceil(extent / rowSpacing));
  const bars = new BarList('PS');
  const linkLen = ceilTo(2 * 110 + (h - 2 * cover) + 2 * Math.max(6 * sp.dia, 75), 10);
  const types = [];
  const columns = [];
  // walls are line supports: no punching links
  for (const col of level.columns) {
    const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
    const sides = [];
    for (const [dir, sign] of [['x', -1], ['x', 1], ['y', -1], ['y', 1]]) {
      const toEdge = edgeDistance(level, col, dir, sign, cover);
      const faceLen = size[dir === 'x' ? 'y' : 'x'];
      const room = toEdge - size[dir] / 2;
      if (room < rowSpacing) continue; // face at the slab edge
      const nRows = Math.min(rows, Math.floor(room / rowSpacing));
      const links = Math.floor(faceLen / sp.legSpacing) + 1;
      sides.push({ dir, sign, nRows, links, faceLen, offset: size[dir] / 2 });
    }
    const label = sides.map((sd) => `${sd.nRows}X${sd.links}-T${sp.dia}-${rowSpacing}`).sort().filter((v, i, a) => a.indexOf(v) === i).join(' / ');
    const key = `${sides.length}|${label}`;
    let t = types.find((x) => x.key === key);
    if (!t) { t = { key, id: `PS${types.length + 1}`, sides, size, columns: [], label }; types.push(t); }
    t.columns.push(col.id);
    columns.push({ col, type: t, sides });
    const n = sides.reduce((s, sd) => s + sd.nRows * sd.links, 0);
    if (n) bars.add({ dia: sp.dia, shape: 'LINK', length: linkLen, qty: n, spacing: rowSpacing, zone: t.id, note: `legs 110, web ${h - 2 * cover}` });
  }
  return { types, columns, bars, dia: sp.dia, rowSpacing, rows, extent, linkLen, d, legSpacing: sp.legSpacing };
}

/** Sheet: reinforcement around openings: trimmers, corner diagonals, edge U-bars. */
export function aroundOpenings(level, spec) {
  const bars = new BarList('O');
  const so = spec.openings;
  const h = level.thickness;
  const cover = spec.cover;
  const lap = lapLength(spec, so.dia, { top: true });
  const diagL = ceilTo(Math.max(1200, 2 * developmentLength(spec, so.diagDia, { top: true })), 50);
  const uLen = ceilTo(2 * so.uLeg + (h - 2 * cover), 10);
  const lined = level.openings.filter((o) => openingLined(level, o));
  const regions = level.openings.filter((o) => !lined.includes(o)).map((o) => {
    const trimmers = trimmersAround(level, spec, o, so, bars, lap);
    const poly = regionPolygon(o);
    const corners = o.kind === 'circle' ? [] : poly.map((p, i) => {
      const prev = poly[(i + poly.length - 1) % poly.length], next = poly[(i + 1) % poly.length];
      // bisector pointing away from the region
      const v1 = { x: prev.x - p.x, y: prev.y - p.y }, v2 = { x: next.x - p.x, y: next.y - p.y };
      const l1 = Math.hypot(v1.x, v1.y) || 1, l2 = Math.hypot(v2.x, v2.y) || 1;
      let bx = v1.x / l1 + v2.x / l2, by = v1.y / l1 + v2.y / l2;
      const bl = Math.hypot(bx, by) || 1; bx /= bl; by /= bl;
      if (pointInPolygon({ x: p.x + bx * 20, y: p.y + by * 20 }, poly)) { bx = -bx; by = -by; }
      // diagonal bar is perpendicular to the bisector, centred a little outside the corner
      const c = { x: p.x - bx * 100, y: p.y - by * 100 };
      return { p, c, dx: -by, dy: bx };
    });
    const diagMark = corners.length ? bars.add({ dia: so.diagDia, shape: 'DIAG', length: diagL, qty: corners.length * so.diagCount * 2, zone: o.id, note: 'T&B at corners' }) : null;
    const per = perimeter(poly);
    const nU = Math.max(0, Math.floor((per - 4 * cover) / so.uSpacing));
    const uMark = bars.add({ dia: so.uDia, shape: 'U', length: uLen, qty: nU, spacing: so.uSpacing, zone: o.id, note: `legs ${so.uLeg}` });
    return { region: o, trimmers, corners, diagMark, uMark, nU };
  });
  return { regions, bars, spec: so, diagL, uLen, ld: developmentLength(spec, so.dia, { top: true }), lined };
}

export { growRect, polygonArea, regionPolygon as polygonOf };
