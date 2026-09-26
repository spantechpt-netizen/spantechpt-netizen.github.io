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

/** Accumulates bar entries and issues marks per (dia, shape, length, sheet). */
export class BarList {
  constructor(prefix = 'M') { this.prefix = prefix; this.entries = []; }

  add(e) {
    // e: { dia, shape, length, qty, spacing?, zone, note?, group? }
    const key = `${e.dia}|${e.shape}|${e.length}|${e.spacing || ''}|${e.note || ''}`;
    let m = this.entries.find((x) => x.key === key);
    if (!m) {
      m = { key, mark: '', dia: e.dia, shape: e.shape, length: e.length, spacing: e.spacing || '', note: e.note || '', qty: 0, zones: new Set() };
      this.entries.push(m);
    }
    m.qty += e.qty;
    if (e.zone) m.zones.add(e.zone);
    return m;
  }

  /** Sorted rows with marks, totals and weights. */
  rows() {
    const sorted = [...this.entries].sort((a, b) => a.dia - b.dia || a.shape.localeCompare(b.shape) || b.length - a.length);
    sorted.forEach((m, i) => { m.mark = `${this.prefix}${String(i + 1).padStart(2, '0')}`; });
    return sorted.map((m) => ({
      mark: m.mark, dia: m.dia, shape: m.shape, spacing: m.spacing, length: m.length, qty: m.qty,
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

const rowsSame = (a, b) => a.length === b.length && a.every((c, i) => Math.abs(c[0] - b[i][0]) < 5 && Math.abs(c[1] - b[i][1]) < 5);

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

/** Sheet: bottom mesh in PT zones (or over the whole slab when no zone is drawn). */
export function bottomMesh(level, spec) {
  const s = spec.bottom;
  const lap = lapLength(spec, s.dia);
  const bars = new BarList('B');
  const zones = [];
  const cover = spec.cover;
  const ptZones = level.pt.zones.length ? level.pt.zones : [{ id: 'PT1', polygon: level.outline }];
  for (const zone of ptZones) {
    const poly = zone.polygon;
    const b = bbox(poly);
    for (const dir of ['X', 'Y']) {
      const along = dir === 'X' ? 'x' : 'y';
      const start = (dir === 'X' ? b.minY : b.minX) + cover + s.spacing / 2;
      const end = (dir === 'X' ? b.maxY : b.maxX) - cover;
      const groups = [];
      let idx = 0;
      for (let c = start; c <= end; c += s.spacing, idx++) {
        let chords = dir === 'X' ? chordsAtY(poly, c) : chordsAtX(poly, c);
        chords = chords.map(([a, bb]) => [a + cover, bb - cover]).filter(([a, bb]) => bb - a > 300);
        chords = subtractIntervals(chords, openingCuts(level, along, c, cover));
        if (!chords.length) continue;
        const last = groups[groups.length - 1];
        if (last && rowsSame(last.chords, chords)) { last.rows++; last.end = c; }
        else groups.push({ chords, rows: 1, start: c, end: c });
      }
      groups.forEach((g, gi) => {
        g.id = `${zone.id}-${dir}${gi + 1}`;
        g.runs = g.chords.map(([a, bb]) => {
          const L = bb - a;
          const A = splitRun(L, { stock: spec.stock, lap, stagger: false });
          const B = splitRun(L, { stock: spec.stock, lap, stagger: true });
          const qtyA = Math.ceil(g.rows / 2), qtyB = Math.floor(g.rows / 2);
          const marks = [];
          for (const [pieces, qty] of [[A, qtyA], [B, qtyB]]) {
            if (!qty) continue;
            for (const len of pieces) marks.push(bars.add({ dia: s.dia, shape: 'STR', length: len, qty, spacing: s.spacing, zone: g.id }));
          }
          return { a, b: bb, L, piecesA: A, piecesB: B, marks: [...new Set(marks)] };
        });
      });
      zones.push({ id: `${zone.id}-${dir}`, zoneId: zone.id, dir, polygon: poly, groups, spacing: s.spacing, dia: s.dia });
    }
  }
  return {
    zones, bars, lap,
    callout: (g) => `${g.rows}T${s.dia}@${s.spacing} B`,
    assumptions: level.pt.zones.length ? [] : ['No PT zone boundary found on the drawing: bottom mesh applied over the whole slab.'],
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
  const bars = new BarList('C');
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
      per[dir] = { ext, hooks, n, length, shape, band, asReq: Math.round(asReq), asProv: Math.round(n * BAR_AREA(s.dia)), straight };
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
      bars.add({ dia: s.dia, shape: p.shape, length: p.length, qty: p.n * t.columns.length, spacing: s.spacing, zone: t.id, note: p.shape === 'STR' ? '' : `hook ${hookLeg(s.dia)}` });
    }
  }
  return { types, columns, bars, checks, dia: s.dia, spacing: s.spacing };
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

/** Sheet: reinforcement around voids (void formers / cores). */
export function aroundVoids(level, spec) {
  const bars = new BarList('V');
  const sv = spec.voids;
  const lap = lapLength(spec, sv.dia, { top: true });
  const regions = level.voids.map((v) => ({ region: v, trimmers: trimmersAround(level, spec, v, sv, bars, lap) }));
  return { regions, bars, dia: sv.dia, count: sv.count, ld: developmentLength(spec, sv.dia, { top: true }) };
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
