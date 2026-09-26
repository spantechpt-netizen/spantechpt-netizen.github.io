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
  topColumns: { dia: 16, spacing: 150 }, // top bars over columns, both ways
  uEdge: { dia: 12, spacing: 200, leg: 1200 }, // U-bars at slab edges (PT anchorage zones)
  uCircle: { dia: 12, spacing: 150, leg: 1200 }, // U-bars around circular regions
  edgeBars: { dia: 12, count: 2 }, // longitudinal bars inside edge U-bars, top and bottom
  ringBars: { dia: 12, count: 2 }, // ring bars around circular regions, top and bottom
  voids: { dia: 12, count: 2 }, // trimmer bars each side of a void, top and bottom
  openings: { dia: 16, count: 2, diagDia: 12, diagCount: 2, uDia: 12, uSpacing: 200, uLeg: 600 },
  sunken: { dia: 12, count: 2, uDia: 10, uSpacing: 200, uLeg: 600 }, // trimmers and hairpins at sunken-slab steps
  punching: { dia: 10, legSpacing: 100, extentFactor: 2.0 }, // preliminary punching links around columns
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
  let best = null;
  for (const o of level.columns) {
    if (o === col) continue;
    if (Math.abs(o[perp] - col[perp]) > 1500) continue;
    const d = (o[alongKey] - col[alongKey]) * sign;
    if (d <= 0) continue;
    if (!best || d < best.d) best = { col: o, d };
  }
  return best;
}

function edgeDistance(level, col, dir, sign, cover) {
  // Distance from column centre to slab edge along dir, in direction sign.
  const chords = dir === 'x' ? chordsAtY(level.outline, col.cy) : chordsAtX(level.outline, col.cx);
  const c = dir === 'x' ? col.cx : col.cy;
  for (const [a, b] of chords) if (c >= a - 1 && c <= b + 1) return (sign > 0 ? b - c : c - a) - cover;
  return 2000; // column outside the outline chords (e.g. on a notch); conservative stub
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
  for (const col of level.columns) {
    const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
    const per = {};
    for (const dir of ['x', 'y']) {
      const c1 = size[dir];
      const c2 = size[dir === 'x' ? 'y' : 'x'];
      const ext = {};
      const hooks = {};
      const spans = [];
      for (const sign of [-1, 1]) {
        const nb = neighbour(level, col, dir, sign);
        const toEdge = edgeDistance(level, col, dir, sign, cover);
        if (nb) {
          const nbSize = nb.col.shape === 'circle' ? nb.col.d : (dir === 'x' ? nb.col.w : nb.col.h);
          const ln = nb.d - c1 / 2 - nbSize / 2;
          spans.push(nb.d);
          let e = ceilTo(ln / 6, 50);
          if (c1 / 2 + e > toEdge) { e = Math.max(toEdge - c1 / 2, 0); hooks[sign] = true; }
          ext[sign] = e;
        } else {
          ext[sign] = Math.max(toEdge - c1 / 2, 0);
          hooks[sign] = true;
          spans.push(2 * toEdge);
        }
      }
      // Minimum bonded reinforcement over the column: As = 0.00075·Acf (§8.6.2.3),
      // Acf = h × larger tributary width of the strip.
      const l2 = spans.length ? Math.max(...spans) : 2 * edgeDistance(level, col, dir, 1, 0);
      const band = c2 + 3 * h; // bars placed within c2 + 1.5h each side, §8.7.5.5.1
      let n = Math.max(4, Math.floor(band / s.spacing) + 1);
      const asReq = 0.00075 * h * l2;
      const nReq = Math.ceil(asReq / BAR_AREA(s.dia));
      if (nReq > n) n = nReq;
      const hookN = (hooks[-1] ? 1 : 0) + (hooks[1] ? 1 : 0);
      const straight = ext[-1] + c1 + ext[1];
      const length = ceilTo(straight + hookN * hookLeg(s.dia), 10);
      const shape = hookN === 0 ? 'STR' : hookN === 1 ? 'L' : 'C';
      per[dir] = { ext, hooks, n, length, shape, band, asReq: Math.round(asReq), asProv: Math.round(n * BAR_AREA(s.dia)), straight, hookLeg: hookLeg(s.dia), c1, code: dir === 'x' ? 'T2' : 'T1' };
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
      p.mark = lists[dir].add({ dia: s.dia, shape: p.shape, length: p.length, qty: p.n * t.columns.length, spacing: s.spacing, zone: t.id, note: p.shape === 'STR' ? '' : `hook ${hookLeg(s.dia)}` });
    }
  }
  return { types, columns, lists, checks, dia: s.dia, spacing: s.spacing };
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
  if (level.ubar.edges === 'all') assumptions.push('U-bar edge zones not marked on the drawing: U-bars applied along the entire slab perimeter (PT anchorage zones).');
  const su = spec.uEdge, se = spec.edgeBars;
  const lapE = lapLength(spec, se.dia);
  const uLen = ceilTo(2 * su.leg + web, 10);
  edgeList.forEach((e, i) => {
    if (e.length < 2 * su.spacing) return;
    const n = Math.floor((e.length - 2 * cover) / su.spacing) + 1;
    const uMark = bars.add({ dia: su.dia, shape: 'U', length: uLen, qty: n, spacing: su.spacing, zone: `E${i + 1}`, note: `legs ${su.leg}` });
    const runL = e.length - 2 * cover;
    const pieces = splitRun(runL, { stock: spec.stock, lap: lapE });
    const marks = pieces.map((len) => bars.add({ dia: se.dia, shape: 'STR', length: len, qty: 2 * se.count, zone: `E${i + 1}`, note: 'edge bar T&B' }));
    edgeItems.push({ id: `E${i + 1}`, a: e.a, b: e.b, length: e.length, n, uMark, marks: [...new Set(marks)], pieces });
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
  return { edgeItems, circleItems, bars, assumptions, uEdge: su, uCircle: sc, edgeBars: se, ringBars: sr, uLen, web };
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
  const regions = level.openings.map((o) => {
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
  return { regions, bars, spec: so, diagL, uLen, ld: developmentLength(spec, so.dia, { top: true }) };
}

export { growRect, polygonArea, regionPolygon as polygonOf };
