/**
 * Composes the drawing package in the reference drafting convention:
 *   - one representative bar per group, pieces along the run with the lap
 *     of the next piece drawn offset, call-out `9T12@400-T2-05-(L=11300)`
 *     above the bar, straight length below, hook leg at hooked ends;
 *   - one plan per reinforcement layer (T1/T2, B1/B2) side by side;
 *   - mesh labels `Ø12@200-B1` per zone; columns solid, walls hatched,
 *     slab edge and beams green, openings crossed, sunken slabs hatched.
 * Each sheet is a block in its own Canvas so it can be written as a
 * stand-alone DXF (Xref) and also collected into the package DXF.
 */
import { Canvas } from './canvas.mjs';
import { Sheet, chooseScale, layoutFor } from './sheet.mjs';
import * as R from './rebar.mjs';
import * as D from './details.mjs';
import { bbox, expandBbox, edges, rectPolygon, circlePolygon, dist, pointInPolygon, centroid } from './geometry.mjs';

/** Column outline as a polygon (rotated columns supported). */
export function columnPolygon(c) {
  if (c.shape === 'circle') return circlePolygon(c.cx, c.cy, c.d / 2, 24);
  const a = ((c.angle || 0) * Math.PI) / 180, cs = Math.cos(a), sn = Math.sin(a);
  return [[-c.w / 2, -c.h / 2], [c.w / 2, -c.h / 2], [c.w / 2, c.h / 2], [-c.w / 2, c.h / 2]].map(([x, y]) => ({ x: c.cx + x * cs - y * sn, y: c.cy + x * sn + y * cs }));
}

export const SHEET_DEFS = [
  { key: 'framing', base: 'FRAMING_FORMWORK_NOTATION', title: 'FRAMING / FORMWORK NOTATION PLAN', no: '01' },
  { key: 'bottom', base: 'FRAMING_REBAR_SLAB_PT_BOTTOM', title: 'BOTTOM REINFORCEMENT PLAN (B1 / B2)', no: '02', plans: 2 },
  { key: 'top', base: 'FRAMING_REBAR_ADDITIONAL_AT_COLUMNS', title: 'ADDITIONAL TOP REINFORCEMENT OVER COLUMNS (T1 / T2)', no: '03', plans: 2 },
  // only when the input is a RAM Concept model: the designed bands as additional reinforcement
  { key: 'addbottom', base: 'FRAMING_REBAR_ADDITIONAL_BOTTOM_RAM', title: 'ADDITIONAL BOTTOM REINFORCEMENT (ADD.B1 / ADD.B2) - RAM DESIGN', no: '02A', plans: 2, ramOnly: true },
  { key: 'addtop', base: 'FRAMING_REBAR_ADDITIONAL_TOP_RAM', title: 'ADDITIONAL TOP REINFORCEMENT (ADD.T1 / ADD.T2) - RAM DESIGN', no: '03A', plans: 2, ramOnly: true },
  { key: 'ubars', base: 'FRAMING_REBAR_U_BARS_AROUND_REGIONS', title: 'U-BARS AT SLAB EDGES AND AROUND CIRCULAR REGIONS', no: '04' },
  { key: 'voids', base: 'FRAMING_REBAR_AROUND_VOIDS_ACUARS', title: 'REINFORCEMENT AROUND VOIDS / ACUARS AND SUNKEN SLABS', no: '05' },
  { key: 'openings', base: 'FRAMING_REBAR_AROUND_OPENINGS', title: 'REINFORCEMENT AROUND OPENINGS', no: '06' },
  { key: 'cables', base: 'CABLES_SCHEDULE_EMPTY_TEMPLATE', title: 'PT CABLES LAYOUT AND SCHEDULE - EMPTY TEMPLATE', no: '07' },
  { key: 'punching', base: 'FRAMING_REBAR_PUNCHING_LINKS', title: 'PUNCHING SHEAR REINFORCEMENT PLAN (PRELIMINARY)', no: '08' },
];

const SCHEDULE_COLS = [
  { key: 'mark', title: 'MARK', w: 17 },
  { key: 'dia', title: 'Ø', w: 8 },
  { key: 'shape', title: 'SHAPE', w: 13 },
  { key: 'spacing', title: 'SPAC.', w: 12 },
  { key: 'length', title: 'LENGTH\n(mm)', w: 17 },
  { key: 'qty', title: 'QTY', w: 13 },
  { key: 'total_m', title: 'TOTAL\n(m)', w: 16 },
  { key: 'weight_kg', title: 'WT.\n(kg)', w: 17 },
  { key: 'zones', title: 'ZONES / REMARKS', w: 72, align: 'L', max: 44 },
];

const CALL_H = 2.1, LEN_H = 1.7, HOOK_H = 1.5;
const REBAR_STYLE = 'ST-REBAR';
const fmtMM = (v) => Math.round(v).toLocaleString('en-US');
const regionBox = (o) => R.regionBbox(o);
const sizeOf = (o) => (o.kind === 'circle' ? `Ø${fmtMM(2 * o.r)}` : o.kind === 'rect' ? `${fmtMM(o.rect.w)} x ${fmtMM(o.rect.h)}` : `${fmtMM(regionBox(o).w)} x ${fmtMM(regionBox(o).h)} (POLY)`);
const totalsLine = (tot) => `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`;

/** "B-C / 2-3" style reference for a region. */
export function gridRef(level, b) {
  const near = (arr, key, v) => arr.reduce((best, g) => (Math.abs(g[key] - v) < Math.abs((best ? best[key] : Infinity) - v) ? g : best), null);
  const x1 = near(level.grid.x, 'x', b.minX), x2 = near(level.grid.x, 'x', b.maxX);
  const y1 = near(level.grid.y, 'y', b.minY), y2 = near(level.grid.y, 'y', b.maxY);
  const xs = x1 && x2 ? (x1 === x2 ? x1.label : `${x1.label}-${x2.label}`) : '';
  const ys = y1 && y2 ? (y1 === y2 ? y1.label : `${y1.label}-${y2.label}`) : '';
  return `${xs} / ${ys}`;
}

// ------------------------------------------------------------------ base plan
function drawBase(sheet, pl, level, o = {}) {
  const S = sheet.S;
  const ob = level.bbox;
  const bubbleR = 4 * S;
  const tag = o.gridTag;
  const bubble = (x, y, label) => {
    pl.circle({ x, y }, bubbleR, { layer: 'GRID-BUBBLE' });
    pl.text({ x, y: tag ? y + 0.6 * S : y }, label, { layer: 'TEXT', h: 3, align: 'C', valign: 'M', bold: true });
    if (tag) pl.text({ x, y: y - 2.2 * S }, tag, { layer: 'TEXT-TITLE', h: 1.4, align: 'C', valign: 'M' });
  };
  for (const g of level.grid.x) {
    pl.line({ x: g.x, y: ob.minY - 3000 }, { x: g.x, y: ob.maxY + 3000 }, { layer: 'GRID' });
    bubble(g.x, ob.maxY + 3000 + bubbleR, g.label);
    bubble(g.x, ob.minY - 3000 - bubbleR, g.label);
  }
  for (const g of level.grid.y) {
    pl.line({ x: ob.minX - 3000, y: g.y }, { x: ob.maxX + 3000, y: g.y }, { layer: 'GRID' });
    bubble(ob.minX - 3000 - bubbleR, g.y, g.label);
    bubble(ob.maxX + 3000 + bubbleR, g.y, g.label);
  }
  const gx = level.grid.x, gy = level.grid.y;
  if (o.dims !== false) {
    for (let i = 0; i + 1 < gx.length; i++) pl.dim({ x: gx[i].x, y: ob.minY - 5200 }, { x: gx[i + 1].x, y: ob.minY - 5200 }, -6, { h: 1.8 });
    if (gx.length > 1) pl.dim({ x: gx[0].x, y: ob.minY - 5200 }, { x: gx[gx.length - 1].x, y: ob.minY - 5200 }, -12, { h: 1.8 });
    for (let i = 0; i + 1 < gy.length; i++) pl.dim({ x: ob.maxX + 5200, y: gy[i].y }, { x: ob.maxX + 5200, y: gy[i + 1].y }, -6, { h: 1.8 });
    if (gy.length > 1) pl.dim({ x: ob.maxX + 5200, y: gy[0].y }, { x: ob.maxX + 5200, y: gy[gy.length - 1].y }, -12, { h: 1.8 });
  }
  // slab outline, beams, walls, thickened zones, stairs
  // walls below first so a wall on the slab edge does not hide the green edge line
  for (const w of level.walls || []) pl.line(w.a, w.b, { layer: 'WALL' });
  pl.pline(level.outline, { layer: 'OUTLINE', closed: true, color: 3 });
  for (const bm of level.beams || []) pl.line(bm.a, bm.b, { layer: 'BEAM' });
  if (o.thickZones !== false) for (const z of level.thickZones || []) {
    pl.pline(z.polygon, { layer: 'SLAB-THK', closed: true });
    pl.hatch([z.polygon], { layer: 'SLAB-THK-HATCH', pattern: 'ANSI31', spacing: 3 });
    if (o.regionLabels) { const c = centroid(z.polygon); pl.text({ x: c.x, y: c.y }, `${z.id} THK=${z.thickness}`, { layer: 'SLAB-THK', h: 1.5, align: 'C', valign: 'M' }); }
  }
  if (o.stairs !== false) for (const st of level.stairs || []) pl.pline(st.pts, { layer: 'STAIR', closed: !!st.closed });
  // PT zones
  if (o.pt !== false) for (const z of level.pt.zones) {
    pl.pline(z.polygon, { layer: 'PT-ZONE', closed: true });
    const zb = bbox(z.polygon);
    pl.text({ x: zb.minX + 600, y: zb.maxY - 900 }, `${z.id} - PT SLAB ZONE`, { layer: 'PT-ZONE', h: 2.2 });
  }
  // columns: solid black (rotated columns drawn as polygons)
  for (const c of level.columns) {
    const poly = columnPolygon(c);
    if (c.shape === 'circle') pl.circle({ x: c.cx, y: c.cy }, c.d / 2, { layer: 'COLUMN' }); else pl.pline(poly, { layer: 'COLUMN', closed: true });
    pl.hatch([poly], { layer: 'COLUMN-HATCH', pattern: 'SOLID', color: 7 });
    if (o.columnIds) pl.text({ x: c.cx + c.w / 2 + 150, y: c.cy + c.h / 2 + 150 }, c.id, { layer: 'TEXT', h: 1.5 });
  }
  // openings: crossed
  for (const op of level.openings) {
    const poly = R.polygonOf(op);
    pl.pline(poly, { layer: 'OPENING', closed: true });
    const b = bbox(poly);
    if (op.kind !== 'circle') { pl.line({ x: b.minX, y: b.minY }, { x: b.maxX, y: b.maxY }, { layer: 'OPENING' }); pl.line({ x: b.maxX, y: b.minY }, { x: b.minX, y: b.maxY }, { layer: 'OPENING' }); }
    if (o.regionLabels) pl.text({ x: b.cx, y: b.maxY + 200 }, `${op.id} OPENING ${sizeOf(op)}`, { layer: 'OPENING', h: 1.5, align: 'C' });
  }
  // voids
  for (const v of level.voids) {
    const poly = R.polygonOf(v);
    pl.pline(poly, { layer: 'VOID', closed: true });
    pl.hatch([poly], { layer: 'VOID-HATCH', pattern: 'ANSI37', spacing: 2.5 });
    const b = bbox(poly);
    if (o.regionLabels) pl.text({ x: b.cx, y: b.maxY + 200 }, `${v.id} VOID ${sizeOf(v)}`, { layer: 'VOID', h: 1.5, align: 'C' });
  }
  // sunken slabs
  for (const sk of level.sunken || []) {
    const poly = R.polygonOf(sk);
    pl.pline(poly, { layer: 'SUNKEN', closed: true });
    pl.hatch([poly], { layer: 'SUNKEN-HATCH', pattern: 'ANSI31', spacing: 1.5 });
    if (o.regionLabels) { const c = centroid(poly); pl.text({ x: c.x, y: c.y + 120 }, `${sk.id} SUNKEN SLAB`, { layer: 'SUNKEN', h: 1.4, align: 'C' }); pl.text({ x: c.x, y: c.y - 150 }, `TH=${sk.thickness || '?'}mm`, { layer: 'SUNKEN', h: 1.4, align: 'C' }); }
  }
  // circular U-bar regions
  if (o.ubarRegions !== false) for (const u of level.ubar.circles) {
    if (!u.fromOpening) pl.circle({ x: u.cx, y: u.cy }, u.r, { layer: 'REBAR-U', ltype: 'DASHDOT' });
    if (o.regionLabels) pl.text({ x: u.cx, y: u.cy - u.r - 700 }, `${u.id} U-BAR REGION Ø${fmtMM(2 * u.r)}`, { layer: 'REBAR-U', h: 1.5, align: 'C' });
  }
}

// ------------------------------------------------------------------ bar drafting
/**
 * A run of bars in the reference convention. `a`→`b` is the bar axis at
 * true length; `pieces` are cutting lengths; hooks at `hooks.start` /
 * `hooks.end`. The lap of every following piece is drawn offset.
 */
function drawRun(pl, S, { a, b, pieces, lap, hooks = {}, hookLeg = 0, label, layer = 'REBAR', offsetSide = 1, textSide = 1 }) {
  const L = dist(a, b) || 1;
  const ux = (b.x - a.x) / L, uy = (b.y - a.y) / L;
  const nx = -uy, ny = ux;
  const at = (s, off = 0) => ({ x: a.x + ux * s + nx * off, y: a.y + uy * s + ny * off });
  let rot = (Math.atan2(uy, ux) * 180) / Math.PI;
  if (rot > 90 || rot <= -90) rot += 180;
  const flip = rot !== (Math.atan2(uy, ux) * 180) / Math.PI ? -1 : 1; // text reads left-to-right / bottom-to-top
  const tn = textSide * flip;
  let pos = 0;
  const last = pieces.length - 1;
  const straights = pieces.map((cut, i) => cut - (i === 0 && hooks.start ? hookLeg : 0) - (i === last && hooks.end ? hookLeg : 0));
  for (let i = 0; i <= last; i++) {
    const s0 = i === 0 ? 0 : pos - lap;
    const s1 = s0 + straights[i];
    const axisStart = i === 0 ? s0 : Math.min(s0 + lap, s1);
    pl.line(at(axisStart), at(s1), { layer });
    if (i > 0) pl.line(at(s0, offsetSide * 150), at(axisStart, offsetSide * 150), { layer });
    if (i === 0 && hooks.start) pl.line(at(0), at(0, -offsetSide * 250), { layer });
    if (i === last && hooks.end) pl.line(at(s1), at(s1, -offsetSide * 250), { layer });
    const mid = (axisStart + s1) / 2;
    pl.text(at(mid, tn * 0.55 * S), label(i, pieces[i], straights[i]), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: CALL_H, rot, align: 'C', valign: 'B' });
    pl.text(at(mid, -tn * (LEN_H + 0.5) * S), String(Math.round(straights[i])), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: LEN_H, rot, align: 'C', valign: 'B' });
    if (i === 0 && hooks.start) pl.text(at(-0.4 * S, tn * 0.55 * S), String(hookLeg), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: HOOK_H, rot, align: 'R', valign: 'B' });
    if (i === last && hooks.end) pl.text(at(s1 + 0.4 * S, tn * 0.55 * S), String(hookLeg), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: HOOK_H, rot, align: 'L', valign: 'B' });
    pos = s1;
  }
  pl.barEnds(at(0), at(pos), { layer, size: 0.6 });
}

const callout = (n, dia, spacing, mark, len) => `${n}T${dia}${spacing ? `@${spacing}` : ''}-${mark}-(L=${len})`;

/**
 * Designed bands from RAM Concept: one representative bar (the middle one)
 * per band, pieces split at stock length, hooks where a bar ends at the
 * slab edge. Returns the bar lists per layer code.
 */
/** Office layer code of a band: 1 = bars parallel to the numbered grids (Y), 2 = parallel to the lettered grids (X). */
export function bandCode(b) {
  const rep = b.bars[Math.floor(b.bars.length / 2)] || { a: b.p0, b: b.p1 };
  return Math.abs(rep.b.y - rep.a.y) > Math.abs(rep.b.x - rep.a.x) ? 1 : 2;
}

function drawRamBands(pl, S, level, spec, face, plans) {
  const lists = { 1: new R.BarList(`ADD.${face}1`), 2: new R.BarList(`ADD.${face}2`) };
  const bands = level.ram.bands.filter((b) => b.face === face);
  const nearEdge = (p) => { const e = edges(level.outline); return e.some((ed) => { const L = ed.length || 1; const t = Math.max(0, Math.min(1, ((p.x - ed.a.x) * ed.dx + (p.y - ed.a.y) * ed.dy) / (L * L))); return dist(p, { x: ed.a.x + ed.dx * t, y: ed.a.y + ed.dy * t }) < 250; }); };
  let k = 0;
  for (const b of bands) {
    const code = bandCode(b);
    const pen = plans[code];
    if (!pen || !b.bars.length) continue;
    const rep = b.bars[Math.floor(b.bars.length / 2)];
    const hooks = { start: nearEdge(rep.a) || b.ends[0] !== 1, end: nearEdge(rep.b) || b.ends[1] !== 1 };
    const hk = R.hookLeg(b.dia);
    const straight = dist(rep.a, rep.b);
    const cut = Math.ceil((straight + (hooks.start ? hk : 0) + (hooks.end ? hk : 0)) / 10) * 10;
    const lap = R.lapLength(spec, b.dia, { top: face === 'T' });
    const pieces = cut > spec.stock ? R.splitRun(cut, { stock: spec.stock, lap }) : [cut];
    const marks = pieces.map((len) => lists[code].add({ dia: b.dia, shape: pieces.length > 1 ? 'STR' : hooks.start && hooks.end ? 'C' : hooks.start || hooks.end ? 'L' : 'STR', length: len, qty: b.count, spacing: b.spacing, zone: b.id, note: hooks.start || hooks.end ? `hook ${hk}` : '' }));
    const side = k++ % 2 ? -1 : 1;
    drawRun(pen, S, { a: rep.a, b: rep.b, pieces, lap, hooks: pieces.length > 1 ? {} : hooks, hookLeg: hk, layer: `REBAR-${face}${code}`, textSide: side, offsetSide: side, label: (i, c) => callout(b.count, b.dia, b.spacing, marks[i].mark, c) });
    // band width as a light range line at the first and last bar
    const first = b.bars[0], last = b.bars[b.bars.length - 1];
    if (b.bars.length > 1) { pen.line(first.a, first.b, { layer: 'REBAR-EXTENT', ltype: 'DASHED' }); pen.line(last.a, last.b, { layer: 'REBAR-EXTENT', ltype: 'DASHED' }); }
  }
  return lists;
}

/** U-bar / hairpin symbol in plan at point p, legs along n (unit), width w. */
function hairpin(pl, p, n, leg, w = 100, layer = 'REBAR-U') {
  const t = { x: -n.y, y: n.x };
  const a = { x: p.x + t.x * w / 2, y: p.y + t.y * w / 2 }, b = { x: p.x - t.x * w / 2, y: p.y - t.y * w / 2 };
  pl.pline([{ x: a.x + n.x * leg, y: a.y + n.y * leg }, a, b, { x: b.x + n.x * leg, y: b.y + n.y * leg }], { layer });
}

const commonNotes = (model, level) => [
  'ALL DIMENSIONS ARE IN MILLIMETRES, LEVELS IN METRES UNLESS NOTED OTHERWISE. DO NOT SCALE; FOLLOW THE WRITTEN DIMENSIONS.',
  `CONCRETE f'c = ${model.spec.fc} MPa (${model.spec.sources.fc}). REINFORCEMENT: DEFORMED BARS fy = ${model.spec.fy} MPa (${model.spec.sources.fy}). CLEAR COVER ${model.spec.cover} mm TOP AND BOTTOM (${model.spec.sources.cover}).`,
  `SLAB THICKNESS ${level.thickness} mm. THIS SHEET IS TO BE READ WITH THE CONSULTANT'S STRUCTURAL DRAWINGS (G.A.) AND THE PT LAYOUT; DISCREPANCIES TO BE REFERRED TO THE ENGINEER BEFORE FABRICATION.`,
  'BAR CALL-OUT: [No.] T[Ø] @[SPACING] - [LAYER-MARK] - (L = CUTTING LENGTH). STRAIGHT LENGTH IS WRITTEN UNDER THE BAR; A HOOK LEG IS WRITTEN AT THE HOOKED END. T1/T2 = TOP LAYERS, B1/B2 = BOTTOM LAYERS (1 = BARS PARALLEL TO THE NUMBERED GRIDS, 2 = PARALLEL TO THE LETTERED GRIDS).',
  'THE DRAWN BAR IS REPRESENTATIVE OF THE GROUP; THE NUMBER OF BARS IN THE CALL-OUT IS PLACED AT THE GIVEN SPACING ACROSS THE ZONE. A SHORT OFFSET LINE MARKS THE LAP OF THE FOLLOWING PIECE.',
  'TENSION LAPS ARE CLASS B (1.3 ld) PER SBC 304-18 §25.5.2, SO ALL BARS OF A ROW MAY LAP AT THE SAME SECTION. BARS ENDING AT A FREE EDGE TERMINATE WITH A STANDARD 90° HOOK (12 Ø) UNLESS NOTED.',
];

const lengthNote = (model, dias) => R.lengthTable(model.spec, dias).map((r) => `Ø${r.dia}: ld ${r.ld_bottom} (bot) / ${r.ld_top} (top) · LAP ${r.lap_bottom} (bot) / ${r.lap_top} (top) · ldh ${r.ldh}`);

const codeText = (model) => (model.spec.sources.code === 'drawing'
  ? `${model.code_reference} AS STATED ON THE STRUCTURAL DRAWINGS. DEVELOPMENT, ANCHORAGE AND LAP LENGTHS PER SBC 304-18 CHAPTER 25 (ACI 318-14 BASIS).`
  : 'SAUDI PRACTICE ASSUMED: SBC 304-18 (SAUDI BUILDING CODE - CONCRETE STRUCTURES, BASED ON ACI 318-14) FOR DEVELOPMENT, ANCHORAGE AND LAP LENGTHS. TO BE ADJUSTED ON RECEIPT OF THE FINAL DESIGN CRITERIA / CONSULTANT REQUIREMENTS.');

const levelAssumptions = (model, level) => model.assumptions.filter((a) => !a.level || a.level === level.id).map((a) => a.text);

/** Build one sheet. `draw(sheet, pens)` returns { rows, cols, scheduleTitle, totals, general, legend, extra, detailsUsed } */
function buildSheet({ model, level, def, meta, index, total, draw }) {
  const root = new Canvas();
  const blockName = level ? `${def.base}_${level.id}` : def.base;
  const L = layoutFor('A1');
  // plan margin: room for the grid bubbles (3000 + 2 x 4S) plus a little air; the
  // scale is picked with a provisional margin and the margin re-fitted to it.
  const marginFor = (sc) => 3000 + 8 * (sc / 100) + 400;
  let pb = level ? expandBbox(level.bbox, marginFor(200)) : null;
  const stacked = [{ x: L.plan.x, y: L.plan.y + L.plan.h / 2, w: L.plan.w, h: L.plan.h / 2 }, { x: L.plan.x, y: L.plan.y, w: L.plan.w, h: L.plan.h / 2 }];
  const pick = () => {
    let areas = def.plans === 2 ? L.halves : [L.plan];
    if (level && def.plans === 2 && chooseScale(pb, stacked[0]) < chooseScale(pb, L.halves[0])) areas = stacked;
    return areas;
  };
  let areas = pick();
  let scale = level ? Math.max(...areas.map((a) => chooseScale(pb, a))) : 100;
  if (level) { pb = expandBbox(level.bbox, marginFor(scale)); areas = pick(); scale = Math.max(...areas.map((a) => chooseScale(pb, a))); }
  const sheet = new Sheet(root, { blockName, scale });
  sheet.frame();
  const pens = level ? areas.map((a) => sheet.setPlan(pb, a)) : [];
  const r = draw(sheet, pens) || {};
  const drawingNo = level ? `${meta.prefix}-${level.id}-${def.no}` : `${meta.prefix}-000`;

  let leftover = [];
  if (r.rows) {
    const Sc = sheet.L.schedule;
    const maxRows = Math.floor((Sc.h - 6 - 6 - 5 - 6) / 4);
    const res = sheet.table(Sc.x, Sc.y + Sc.h - 3, r.cols || SCHEDULE_COLS, r.rows, { title: r.scheduleTitle || 'BAR BENDING SCHEDULE', maxRows, totals: r.totals || null });
    leftover = res.leftover;
    if (leftover.length) {
      const used = r.detailsUsed ?? 3;
      const box = sheet.L.details[Math.min(used, 2)];
      sheet.pp.rect(box.x, box.y, box.w, box.h, { layer: 'FRAME' });
      const cols = (r.cols || SCHEDULE_COLS).map((c) => ({ ...c, w: (c.w * (box.w - 6)) / 185 }));
      const res2 = sheet.table(box.x + 3, box.y + box.h - 3, cols, leftover, { title: (r.scheduleTitle || 'BAR BENDING SCHEDULE') + ' (CONT.)', maxRows: Math.floor((box.h - 22) / 4), totals: r.totals || null });
      leftover = res2.leftover;
    }
  }
  sheet.keyPlan(level ? level.outline : (model.levels[0] && model.levels[0].outline));
  sheet.notes({ general: r.general || [], assumptions: r.assumptions || [], codeRef: codeText(model), legend: r.legend || [], extra: r.extra || [] });
  sheet.refsBlock(meta);
  sheet.titleBlock({
    ...meta,
    title: def.title,
    level: level ? `${level.id} - ${level.name}` : 'ALL LEVELS',
    drawingNo,
    sheet: `${index} OF ${total}`,
    scale: level ? `1:${scale} (DETAILS AS NOTED)` : 'N.T.S.',
    gridRef: level ? `${level.grid.x[0]?.label}-${level.grid.x[level.grid.x.length - 1]?.label} / ${level.grid.y[0]?.label}-${level.grid.y[level.grid.y.length - 1]?.label}` : 'ALL',
    index: `${meta.prefix}-000`,
    codeRef: model.code_reference ? `${model.code_reference} (ON DRAWINGS)` : 'SBC 304-18 (ASSUMED)',
  });
  if (level) {
    const titles = r.planTitles || [def.title];
    areas.forEach((a, i) => sheet.planTitleAt(a, i + 1, `${level.name} - ${titles[i] || def.title}`, `SCALE : 1:${scale}`));
  }
  root.insert(blockName, 0, 0);
  return { root, sheet, blockName, drawingNo, title: def.title, level: level ? level.id : 'ALL', levelName: level ? level.name : '', scale, key: def.key, rows: r.rows || [], csvCols: r.cols || SCHEDULE_COLS, weight: r.weight || 0, leftoverRows: leftover.length, checks: r.checks || [] };
}

// ------------------------------------------------------------------ sheets
function framingSheet(model, level, meta) {
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { regionLabels: true, columnIds: true, gridTag: meta.gridTag });
    pl.text({ x: level.bbox.minX + 800, y: level.bbox.minY - 1200 }, `PT FLAT SLAB TH=${level.thickness}mm${level.thickZones?.length ? ` (THICKENED ZONES ${[...new Set(level.thickZones.map((z) => z.thickness))].join(' / ')} mm HATCHED)` : ''}`, { layer: 'TEXT', h: 2.6, bold: true });
    for (const op of level.openings) { const b = regionBox(op); pl.bubble({ x: b.maxX, y: b.maxY }, op.id, { dx: 7, dy: 7, layer: 'CALLOUT', r: 3, h: 1.6 }); }
    for (const v of level.voids) { const b = regionBox(v); pl.bubble({ x: b.minX, y: b.maxY }, v.id, { dx: -7, dy: 7, layer: 'CALLOUT', r: 3, h: 1.6 }); }
    for (const u of level.ubar.circles) pl.bubble({ x: u.cx, y: u.cy }, u.id, { dx: 9, dy: -9, layer: 'CALLOUT' });
    const rows = [
      ...level.columns.map((c) => ({ id: c.id, element: c.shape === 'circle' ? 'COLUMN (ROUND)' : c.w > 3 * c.h || c.h > 3 * c.w ? 'WALL / BLADE COL.' : 'COLUMN', size: c.shape === 'circle' ? `Ø${fmtMM(c.d)}` : `${fmtMM(c.w)} x ${fmtMM(c.h)}`, location: `X ${fmtMM(c.cx)}, Y ${fmtMM(c.cy)}` })),
      ...level.openings.map((o) => ({ id: o.id, element: 'OPENING', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...level.voids.map((o) => ({ id: o.id, element: 'VOID / ACUAR', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...(level.sunken || []).map((o) => ({ id: o.id, element: `SUNKEN SLAB TH=${o.thickness || '?'}`, size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...(level.thickZones || []).map((z) => ({ id: z.id, element: `THICKENED ZONE / BAND ${z.thickness} mm`, size: `${fmtMM(bbox(z.polygon).w)} x ${fmtMM(bbox(z.polygon).h)}`, location: gridRef(level, bbox(z.polygon)) })),
      ...(level.walls && level.walls.length ? [{ id: 'W', element: 'WALLS BELOW (LINE SUPPORTS)', size: `${(level.walls.reduce((s, w) => s + dist(w.a, w.b), 0) / 1000).toFixed(1)} m`, location: `${level.walls.length} SEGMENTS` }] : []),
      ...level.ubar.circles.map((o) => ({ id: o.id, element: 'U-BAR REGION', size: `Ø${fmtMM(2 * o.r)}`, location: gridRef(level, { minX: o.cx - o.r, maxX: o.cx + o.r, minY: o.cy - o.r, maxY: o.cy + o.r }) })),
    ];
    const cols = [{ key: 'id', title: 'ID', w: 20 }, { key: 'element', title: 'ELEMENT', w: 42 }, { key: 'size', title: 'SIZE (mm)', w: 45 }, { key: 'location', title: 'LOCATION / GRID', w: 78, align: 'L', max: 44 }];
    const d0 = sheet.detailBox(0, 'TYPICAL SLAB SECTION AT COLUMN', '1:25');
    const det0 = D.sectionColumn({ h: level.thickness, c1: level.columns[0]?.w || 600, ext: 1200, dia: model.spec.topColumns.dia, spacing: model.spec.topColumns.spacing, cover: model.spec.cover, hookLeg: R.hookLeg(model.spec.topColumns.dia), shape: 'STR' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'NOTATION AND MATERIALS', 'N.T.S.');
    const det1 = D.notationLegend({ thickness: level.thickness, fc: model.spec.fc, fy: model.spec.fy, cover: model.spec.cover });
    det1.draw(sheet.detailPen(d1, 12, det1.bbox));
    const d2 = sheet.detailBox(2, 'SLAB EDGE / PT ANCHORAGE ZONE', '1:10');
    const det2 = D.sectionUEdge({ h: level.thickness, cover: model.spec.cover, leg: model.spec.uEdge.leg, dia: model.spec.uEdge.dia, edgeDia: model.spec.edgeBars.dia, spacing: model.spec.uEdge.spacing });
    det2.draw(sheet.detailPen(d2, 10, det2.bbox));
    return {
      rows, cols, scheduleTitle: 'ELEMENT SCHEDULE',
      general: [
        ...commonNotes(model, level).slice(0, 3),
        'COLUMN POSITIONS, SLAB OUTLINE, BEAMS, OPENINGS, SUNKEN SLABS AND VOIDS ARE READ FROM THE CONSULTANT\'S G.A. DRAWING; VERIFY AGAINST THE ARCHITECTURAL DRAWINGS BEFORE FORMWORK.',
        'OPENINGS ARE CROSSED; SUNKEN SLABS AND VOID / ACUAR ZONES ARE HATCHED; CIRCULAR U-BAR REGIONS ARE DASH-DOT CIRCLES. SEE SHEETS 02-08 FOR REINFORCEMENT.',
        'FORMWORK LEVELS AND CAMBER PER PT DESIGN. NO PENETRATIONS OTHER THAN THOSE SHOWN WITHOUT THE ENGINEER\'S APPROVAL.',
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['OUTLINE', 'SLAB EDGE (GREEN)', 'thick'], ['COLUMN-HATCH', 'COLUMN / WALL', 'solid'], ['BEAM', 'BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SUNKEN-HATCH', 'SUNKEN SLAB', 'hatch'], ['VOID', 'VOID / ACUAR', 'line'], ['PT-ZONE', 'PT ZONE', 'line']],
      detailsUsed: 3,
    };
  };
}

function bottomSheet(model, level, meta) {
  const res = R.bottomMesh(level, model.spec);
  return (sheet, [plY, plX]) => {
    const S = sheet.S;
    const pens = { Y: plY, X: plX };
    for (const dir of ['Y', 'X']) {
      const pl = pens[dir];
      drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false });
      for (const z of res.zones.filter((zz) => zz.dir === dir)) {
        // mesh label spread over the zone: sample points inside the slab, keep up to four well apart
        const zb = bbox(z.polygon);
        const placed = [];
        const minGap = Math.max(zb.w, zb.h) / 4;
        for (const fy of [0.5, 0.2, 0.8, 0.35, 0.65]) for (const fx of [0.2, 0.5, 0.8, 0.35, 0.65]) {
          const p = { x: zb.minX + zb.w * fx, y: zb.minY + zb.h * fy };
          if (placed.length >= 4 || !pointInPolygon(p, z.polygon) || placed.some((q) => dist(p, q) < minGap)) continue;
          if ((level.openings || []).some((o) => pointInPolygon(p, R.regionPolygon(o)))) continue;
          placed.push(p);
          pl.text(p, `Ø${z.dia}@${z.spacing}-${z.code}`, { layer: 'REBAR-MESH', h: 2.6, align: 'C', valign: 'M' });
        }
        let k = 0;
        for (const g of z.groups) {
          if (g.rows < 3) continue; // small groups at openings are scheduled but not drawn
          const mid = (g.start + g.end) / 2;
          const side = k++ % 2 ? -1 : 1;
          for (const run of g.runs) {
            const a = dir === 'X' ? { x: run.a, y: mid } : { x: mid, y: run.a };
            const b = dir === 'X' ? { x: run.b, y: mid } : { x: mid, y: run.b };
            drawRun(pl, S, { a, b, pieces: run.pieces, lap: res.lap, textSide: side, offsetSide: side, layer: `REBAR-${z.code}`, label: (i, cut) => callout(g.rows, z.dia, z.spacing, run.marks[i].mark, cut) });
          }
        }
      }
    }
    const rows = R.mergeRows(res.lists.Y, res.lists.X);
    const tot = R.mergeTotals(res.lists.Y, res.lists.X);
    const d0 = sheet.detailBox(0, 'SECTION - BOTTOM MESH AND LAP', '1:20');
    const det0 = D.sectionMesh({ h: level.thickness, cover: model.spec.cover, dia: res.dia, lap: res.lap, spacing: res.spacing });
    det0.draw(sheet.detailPen(d0, 20, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT OPENING - MESH STOPPED', '1:10');
    const det1 = D.sectionTrimmer({ h: level.thickness, cover: model.spec.cover, count: model.spec.openings.count, dia: model.spec.openings.dia, uLeg: model.spec.openings.uLeg, uDia: model.spec.openings.uDia, withU: true });
    det1.draw(sheet.detailPen(d1, 10, det1.bbox));
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      planTitles: ['BOTTOM REINFORCEMENT PLAN (B1)', 'BOTTOM REINFORCEMENT PLAN (B2)'],
      general: [
        ...commonNotes(model, level),
        `BOTTOM MESH Ø${res.dia}@${res.spacing} BOTH WAYS IN THE PT ZONE(S) AS BONDED REINFORCEMENT: B1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), B2 PARALLEL TO THE LETTERED GRIDS (PLAN 2). BARS RUN CONTINUOUSLY THROUGH COLUMNS AND STOP AT OPENINGS (DETAIL 2).`,
        'BAR LENGTHS ARE CUT FROM THE ZONE BOUNDARY LESS COVER; RUNS LONGER THAN ONE STOCK LENGTH ARE SPLIT INTO PIECES WITH CLASS B LAPS, EACH PIECE CALLED OUT SEPARATELY. GROUPS OF FEWER THAN THREE BARS (ROWS INTERRUPTED BY OPENINGS) ARE NOT DRAWN BUT ARE SCHEDULED UNDER THEIR ZONE.',
        ...lengthNote(model, [res.dia]),
      ],
      assumptions: [...levelAssumptions(model, level), ...res.assumptions],
      legend: [['REBAR', `T${res.dia} BOTTOM BAR (REPRESENTATIVE)`, 'thick'], ['REBAR-MESH', 'MESH LABEL PER ZONE', 'line'], ['OPENING', 'OPENING', 'line']],
      detailsUsed: 2,
    };
  };
}

/** Bottom or top sheet from the RAM Concept design: plan 1 = span direction 1 (latitude), plan 2 = direction 2 (longitude). */
function ramBarsSheet(model, level, meta, face) {
  return (sheet, [pl1, pl2]) => {
    const S = sheet.S;
    for (const pl of [pl1, pl2]) drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, regionLabels: false });
    const lists = drawRamBands([pl1, pl2][0] && pl1, S, level, model.spec, face, { 1: pl1, 2: pl2 });
    const rows = R.mergeRows(lists[1], lists[2]);
    const tot = R.mergeTotals(lists[1], lists[2]);
    const label = face === 'B' ? 'ADDITIONAL BOTTOM' : 'ADDITIONAL TOP';
    const dias = [...new Set(level.ram.bands.filter((b) => b.face === face).map((b) => b.dia))].sort((a, b) => a - b);
    if (face === 'B') {
      const d0 = sheet.detailBox(0, 'SECTION - BOTTOM BARS AND LAP', '1:20');
      const det0 = D.sectionMesh({ h: level.thickness, cover: model.spec.cover, dia: dias[0] || 12, lap: R.lapLength(model.spec, dias[0] || 12), spacing: 200 });
      det0.draw(sheet.detailPen(d0, 20, det0.bbox));
    } else {
      const d0 = sheet.detailBox(0, 'SECTION AT SUPPORT - TOP BARS', '1:25');
      const det0 = D.sectionColumn({ h: level.thickness, c1: level.columns[0]?.w || 300, ext: 1500, dia: dias[0] || 16, spacing: 150, cover: model.spec.cover, hookLeg: R.hookLeg(dias[0] || 16), shape: 'STR' });
      det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    }
    const d1 = sheet.detailBox(1, `${face === 'B' ? 'BOTTOM' : 'TOP'} BANDS FROM RAM CONCEPT (${level.ram.bands.filter((b) => b.face === face).length})`, '');
    const bcols = [{ key: 'id', title: 'BAND', w: 16 }, { key: 'dir', title: 'DIR', w: 12 }, { key: 'bars', title: 'BARS', w: 40, align: 'L' }, { key: 'len', title: 'L (mm)', w: 20 }, { key: 'w', title: 'WIDTH', w: 20 }, { key: 'elev', title: 'ELEV.', w: 20 }, { key: 'note', title: 'NOTE', w: (d1.w - 6) - 128, align: 'L', max: 30 }];
    const brows = level.ram.bands.filter((b) => b.face === face).map((b) => ({ id: b.id, dir: `${bandCode(b)} (RAM ${b.dir})`, bars: `${b.count}T${b.dia}@${b.spacing}`, len: b.length, w: b.width, elev: Math.round(b.elevation), note: b.spacing < 75 ? 'CHECK SPACING' : '' }));
    sheet.table(d1.x + 3, d1.y + d1.h - 10, bcols, brows, { maxRows: Math.floor((d1.h - 18) / 3.2), headH: 5, rowH: 3.2, h: 1.3 });
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      planTitles: [`${label} REINFORCEMENT (ADD.${face}1)`, `${label} REINFORCEMENT (ADD.${face}2)`],
      general: [
        ...commonNotes(model, level),
        `${label} BARS (ADD.${face}1 / ADD.${face}2) ARE THE BANDS DESIGNED IN THE RAM CONCEPT MODEL (CONCENTRATED REINFORCEMENT, EVERY INDIVIDUAL BAR READ FROM THE MODEL), PLACED IN ADDITION TO THE STANDARD ${face === 'B' ? 'BOTTOM MESH OF SHEET 02' : 'TOP BARS OVER COLUMNS OF SHEET 03'}. ADD.${face}1 = BARS PARALLEL TO THE NUMBERED GRIDS, ADD.${face}2 = PARALLEL TO THE LETTERED GRIDS. THE DRAWN BAR IS THE MIDDLE BAR OF EACH BAND; THE DASHED LINES MARK THE FIRST AND LAST BAR OF THE BAND.`,
        'BANDS WITH A SPACING UNDER 75 mm ARE FLAGGED "CHECK SPACING" IN THE BAND TABLE (DETAIL 2) AND ARE TO BE CONFIRMED WITH THE DESIGNER BEFORE FABRICATION.',
        ...lengthNote(model, dias.length ? dias : [12]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [[`REBAR-${face}1`, `${label} BAR (REPRESENTATIVE)`, 'thick'], ['REBAR-EXTENT', 'FIRST / LAST BAR OF BAND', 'line'], ['WALL', 'WALL BELOW', 'thick'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch']],
      detailsUsed: 2,
    };
  };
}

function topSheet(model, level, meta) {
  const res = R.topAtColumns(level, model.spec);
  return (sheet, [plY, plX]) => {
    const S = sheet.S;
    const s = model.spec.topColumns;
    const pens = { y: plY, x: plX };
    for (const dir of ['y', 'x']) {
      const pl = pens[dir];
      drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, ubarRegions: false });
      const seen = new Set();
      for (const { col, type, per } of res.columns) {
        const p = per[dir];
        const c1 = p.c1;
        const a0 = (dir === 'x' ? col.cx : col.cy) - c1 / 2 - p.ext[-1];
        const b0 = (dir === 'x' ? col.cx : col.cy) + c1 / 2 + p.ext[1];
        const t = dir === 'x' ? col.cy : col.cx;
        const a = dir === 'x' ? { x: a0, y: t } : { x: t, y: a0 };
        const b = dir === 'x' ? { x: b0, y: t } : { x: t, y: b0 };
        drawRun(pl, S, { a, b, pieces: [p.length], lap: 0, hooks: { start: !!p.hooks[-1], end: !!p.hooks[1] }, hookLeg: p.hookLeg, layer: `REBAR-${p.code}`, label: (i, cut) => callout(p.n, s.dia, s.spacing, type[dir].mark.mark, cut) });
        const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
        pl.bubble({ x: col.cx + size.x / 2, y: col.cy + size.y / 2 }, type.id, { dx: 6, dy: 6, layer: 'CALLOUT', r: 3, h: 1.6 });
        seen.add(type.id);
      }
    }
    const t0 = res.types[0];
    const d0 = sheet.detailBox(0, 'SECTION AT COLUMN - TOP BARS', '1:25');
    const c0 = res.columns[0]?.col;
    const det0 = D.sectionColumn({ h: level.thickness, c1: c0 ? (c0.shape === 'circle' ? c0.d : c0.w) : 600, ext: t0 ? Math.max(t0.x.ext[-1], t0.x.ext[1]) : 1200, dia: s.dia, spacing: s.spacing, cover: model.spec.cover, hookLeg: R.hookLeg(s.dia), shape: t0 ? t0.x.shape : 'STR' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'TOP BAR TYPES OVER COLUMNS', '');
    const typeCols = [{ key: 'id', title: 'TYPE', w: 14 }, { key: 'x', title: 'T2 (PLAN 2) BARS', w: 50, align: 'L' }, { key: 'y', title: 'T1 (PLAN 1) BARS', w: 50, align: 'L' }, { key: 'as', title: 'As req/prov', w: 30 }, { key: 'cols', title: 'COLUMNS', w: (d1.w - 6) - 144, align: 'L', max: 30 }];
    const typeRows = res.types.map((t) => ({ id: t.id, x: `${t.x.n}T${s.dia} ${t.x.mark.mark} L=${t.x.length} ${t.x.shape}`, y: `${t.y.n}T${s.dia} ${t.y.mark.mark} L=${t.y.length} ${t.y.shape}`, as: `${Math.max(t.x.asReq, t.y.asReq)}/${Math.min(t.x.asProv, t.y.asProv)}`, cols: t.columns.join(', ') }));
    sheet.table(d1.x + 3, d1.y + d1.h - 10, typeCols, typeRows, { maxRows: Math.floor((d1.h - 18) / 4), headH: 5, rowH: 4, h: 1.5 });
    const rows = R.mergeRows(res.lists.y, res.lists.x);
    const tot = R.mergeTotals(res.lists.y, res.lists.x);
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg, checks: res.checks,
      planTitles: ['ADDITIONAL TOP REINFORCEMENT (T1)', 'ADDITIONAL TOP REINFORCEMENT (T2)'],
      general: [
        ...commonNotes(model, level),
        `ADDITIONAL TOP BARS T${s.dia}@${s.spacing} OVER EVERY COLUMN: T1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), T2 PARALLEL TO THE LETTERED GRIDS (PLAN 2), PLACED WITHIN c2 + 1.5h EACH SIDE OF THE COLUMN (SBC 304-18 §8.7.5.5.1) AND EXTENDING NOT LESS THAN ln/6 BEYOND THE FACE OF SUPPORT (§8.7.5.5.2).`,
        'MINIMUM BONDED REINFORCEMENT OVER COLUMNS As = 0.00075·Acf (§8.6.2.3) IS CHECKED PER COLUMN; WHERE IT GOVERNS THE BAR COUNT IS INCREASED (TYPE TABLE, DETAIL 2). TOP BARS SIT BELOW THE TOP COVER, ABOVE THE TENDONS, ON CHAIRS.',
        ...lengthNote(model, [s.dia]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR', `T${s.dia} TOP BAR (REPRESENTATIVE)`, 'thick'], ['CALLOUT', 'TOP BAR TYPE', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
      detailsUsed: 2,
    };
  };
}

function ubarSheet(model, level, meta) {
  const res = R.uBars(level, model.spec);
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, ubarRegions: false, pt: false });
    const su = model.spec.uEdge, se = model.spec.edgeBars, sc = model.spec.uCircle, sr = model.spec.ringBars;
    const cover = model.spec.cover;
    for (const e of res.edgeItems) {
      const ux = (e.b.x - e.a.x) / e.length, uy = (e.b.y - e.a.y) / e.length;
      const nx = -uy, ny = ux; // inward for a CCW outline
      // longitudinal edge bars as a run (representative)
      const a = { x: e.a.x + nx * (cover + 60) + ux * cover, y: e.a.y + ny * (cover + 60) + uy * cover };
      const b = { x: e.b.x + nx * (cover + 60) - ux * cover, y: e.b.y + ny * (cover + 60) - uy * cover };
      drawRun(pl, S, { a, b, pieces: e.pieces, lap: R.lapLength(model.spec, se.dia), label: (i, cut) => `${2 * se.count}T${se.dia}-T&B-${e.marks[Math.min(i, e.marks.length - 1)].mark}-(L=${cut})`, offsetSide: 1, textSide: 1 });
      const step = su.spacing * 4;
      for (let d = cover + su.spacing / 2; d < e.length - cover; d += step) hairpin(pl, { x: e.a.x + ux * d + nx * cover, y: e.a.y + uy * d + ny * cover }, { x: nx, y: ny }, su.leg, 120);
      const mid = { x: (e.a.x + e.b.x) / 2 + nx * (su.leg + 500), y: (e.a.y + e.b.y) / 2 + ny * (su.leg + 500) };
      let rot = (Math.atan2(uy, ux) * 180) / Math.PI; if (rot > 90 || rot <= -90) rot += 180;
      pl.text(mid, `${e.n}T${su.dia}@${su.spacing}-${e.uMark.mark}-(L=${e.uMark.length}) U-BARS LEGS ${su.leg}`, { layer: 'REBAR-TEXT', h: CALL_H, rot, align: 'C' });
      pl.bubble({ x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 }, e.id, { dx: -nx * 6, dy: -ny * 6, layer: 'CALLOUT', r: 3, h: 1.6 });
    }
    for (const c of res.circleItems) {
      pl.circle({ x: c.cx, y: c.cy }, c.r, { layer: c.fromOpening ? 'OPENING' : 'REBAR-U', ltype: c.fromOpening ? undefined : 'DASHDOT' });
      pl.circle({ x: c.cx, y: c.cy }, c.ringR, { layer: 'REBAR' });
      const nDraw = Math.min(c.n, 16);
      for (let i = 0; i < nDraw; i++) { const ang = (i / nDraw) * Math.PI * 2; hairpin(pl, { x: c.cx + (c.r + cover) * Math.cos(ang), y: c.cy + (c.r + cover) * Math.sin(ang) }, { x: Math.cos(ang), y: Math.sin(ang) }, sc.leg, 120); }
      pl.bubble({ x: c.cx, y: c.cy }, c.id, { dx: 10, dy: 10, layer: 'CALLOUT' });
      pl.text({ x: c.cx, y: c.cy - c.r - cover - sc.leg - 500 }, `${c.n}T${sc.dia}@${sc.spacing}-${c.uMark.mark}-(L=${c.uMark.length}) RADIAL U-BARS + ${2 * sr.count}T${sr.dia}-RING-${c.ringMarks.map((m) => m.mark).join('/')}`, { layer: 'REBAR-TEXT', h: CALL_H, align: 'C' });
    }
    const d0 = sheet.detailBox(0, 'U-BAR AT SLAB EDGE - SECTION', '1:10');
    const det0 = D.sectionUEdge({ h: level.thickness, cover, leg: su.leg, dia: su.dia, edgeDia: se.dia, spacing: su.spacing });
    det0.draw(sheet.detailPen(d0, 10, det0.bbox));
    const d1 = sheet.detailBox(1, 'U-BARS AROUND CIRCULAR REGION - PLAN', '1:25');
    const c0 = res.circleItems[0] || { r: 1000, ringR: 1000 + cover + sc.dia + sr.dia / 2 };
    const det1 = D.planUCircle({ r: c0.r, cover, leg: sc.leg, spacing: sc.spacing, dia: sc.dia, ringR: c0.ringR, ringDia: sr.dia });
    det1.draw(sheet.detailPen(d1, 25, det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `U-BARS T${su.dia}@${su.spacing} WITH ${su.leg} mm LEGS TOP AND BOTTOM ALONG ALL PT ANCHORAGE EDGES (BURSTING / SPALLING STEEL), WITH ${se.count}T${se.dia} LONGITUDINAL BARS TOP AND BOTTOM INSIDE THE U-BARS (DRAWN AS ONE REPRESENTATIVE BAR PER EDGE). U-BAR DEPTH = SLAB THICKNESS - 2 x COVER = ${res.web} mm.`,
        `AROUND CIRCULAR REGIONS: RADIAL U-BARS T${sc.dia}@${sc.spacing} (LEGS ${sc.leg}) PLUS ${sr.count}T${sr.dia} RING BARS TOP AND BOTTOM, RINGS LAPPED CLASS B.`,
        'U-BARS ARE PLACED BEFORE THE ANCHORAGES ARE FIXED; DO NOT CUT U-BARS TO SUIT ANCHORAGE POCKETS - RELOCATE WITHIN THE SPACING.',
        ...lengthNote(model, [...new Set([su.dia, se.dia, sc.dia])]),
      ],
      assumptions: [...levelAssumptions(model, level), ...res.assumptions],
      legend: [['REBAR-U', 'U-BAR (HAIRPIN SYMBOL)', 'thick'], ['REBAR', 'EDGE / RING BAR', 'thick'], ['CALLOUT', 'EDGE / REGION ID', 'line']],
      detailsUsed: 2,
    };
  };
}

function drawTrimmers(pl, S, regions, spec, kindLabel, opts = {}) {
  for (const { region, trimmers, corners, diagMark, uMark, nU, diagL, kind } of regions) {
    const poly = R.polygonOf(region);
    for (const t of trimmers) {
      const off = t.offsets[0];
      const a = { x: t.edge.a.x - t.ux * t.ext[-1] + t.nx * off, y: t.edge.a.y - t.uy * t.ext[-1] + t.ny * off };
      const b = { x: t.edge.b.x + t.ux * t.ext[1] + t.nx * off, y: t.edge.b.y + t.uy * t.ext[1] + t.ny * off };
      const hk = R.hookLeg(spec.dia);
      drawRun(pl, S, { a, b, pieces: [t.length], lap: 0, hooks: { start: !!t.hooks[-1], end: !!t.hooks[1] }, hookLeg: hk, layer: 'REBAR-TRIM', label: (i, cut) => `${2 * spec.count}T${spec.dia}-T&B-${t.marks[0].mark}-(L=${cut})`, offsetSide: -1, textSide: -1 });
    }
    if (corners) for (const c of corners) {
      pl.line({ x: c.c.x - c.dx * diagL / 2, y: c.c.y - c.dy * diagL / 2 }, { x: c.c.x + c.dx * diagL / 2, y: c.c.y + c.dy * diagL / 2 }, { layer: 'REBAR-TRIM' });
    }
    if (corners && corners.length && diagMark) {
      const c = corners[0];
      let rot = (Math.atan2(c.dy, c.dx) * 180) / Math.PI; if (rot > 90 || rot <= -90) rot += 180;
      pl.text({ x: c.c.x - c.dy * 0.6 * S, y: c.c.y + c.dx * 0.6 * S }, `${2 * spec.diagCount}T${spec.diagDia}-DIAG-${diagMark.mark}-(L=${diagMark.length}) AT ${corners.length} CORNERS`, { layer: 'REBAR-TEXT', h: LEN_H, rot, align: 'C' });
    }
    if (uMark && nU) {
      const uSpec = opts.uSpec || spec;
      for (const e of edges(poly)) {
        const ux = e.dx / e.length, uy = e.dy / e.length;
        let nx = -uy, ny = ux;
        const mid = { x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 };
        if (pointInPolygon({ x: mid.x + nx * 10, y: mid.y + ny * 10 }, poly)) { nx = -nx; ny = -ny; }
        for (let d = uSpec.uSpacing; d < e.length - uSpec.uSpacing / 2; d += uSpec.uSpacing * 3) hairpin(pl, { x: e.a.x + ux * d, y: e.a.y + uy * d }, { x: nx, y: ny }, uSpec.uLeg, 100);
      }
    }
    const b = regionBox(region);
    pl.bubble({ x: b.maxX, y: b.maxY }, region.id, { dx: 10, dy: 8, layer: 'CALLOUT', r: 3, h: 1.6 });
    const lines = [`${region.id} ${kind || kindLabel} ${sizeOf(region)}`];
    if (uMark && nU) lines.push(`${nU}T${(opts.uSpec || spec).uDia}@${(opts.uSpec || spec).uSpacing}-${uMark.mark}-(L=${uMark.length}) U-BARS AT FREE EDGES`);
    lines.forEach((ln, i) => pl.text({ x: b.maxX + 13 * S, y: b.maxY + (6.5 - i * 2.4) * S }, ln, { layer: 'REBAR-TEXT', h: LEN_H }));
  }
}

function voidsSheet(model, level, meta) {
  const res = R.aroundVoids(level, model.spec);
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, ubarRegions: false, pt: false });
    drawTrimmers(pl, sheet.S, res.regions.map((r) => ({ ...r, corners: null, diagMark: null })), model.spec.voids, 'VOID', { uSpec: res.sunken });
    const sv = model.spec.voids, ss = res.sunken;
    const d0 = sheet.detailBox(0, 'TRIMMER BARS AROUND VOID / SUNKEN SLAB - PLAN', '1:25');
    const det0 = D.planTrimmers({ w: 1500, h: 1000, ld: res.ld, count: sv.count, dia: sv.dia, diag: false, uSpacing: ss.uSpacing, uDia: ss.uDia, label: 'VOID / SUNKEN' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT SUNKEN SLAB STEP', '1:10');
    const det1 = D.sectionTrimmer({ h: level.thickness, cover: model.spec.cover, count: ss.count, dia: ss.dia, uLeg: ss.uLeg, uDia: ss.uDia, withU: true });
    det1.draw(sheet.detailPen(d1, 10, det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `${sv.count}T${sv.dia} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY VOID / ACUAR ZONE AND SUNKEN SLAB, ANCHORED ld = ${res.ld} mm BEYOND THE CORNERS INTO THE SOLID SLAB; STOPPED WITH A 90° HOOK WHERE THE ANCHORAGE WOULD LEAVE THE SLAB.`,
        `SUNKEN SLABS: T${ss.uDia}@${ss.uSpacing} HAIRPINS (LEGS ${ss.uLeg}) ALONG THE STEP IN ADDITION TO THE TRIMMERS; THE MAIN MESH IS CRANKED THROUGH THE STEP (DETAIL 2). VOID FORMERS TO BE TIED AGAINST FLOTATION; NO TENDON DEVIATION THROUGH VOIDS WITHOUT THE PT DESIGNER'S APPROVAL.`,
        ...lengthNote(model, [...new Set([sv.dia, ss.dia, ss.uDia])]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR', `T${sv.dia} TRIMMER BAR`, 'thick'], ['REBAR-U', `T${ss.uDia} HAIRPIN`, 'line'], ['SUNKEN-HATCH', 'SUNKEN SLAB', 'hatch'], ['VOID-HATCH', 'VOID / ACUAR', 'hatch']],
      detailsUsed: 2,
    };
  };
}

function openingsSheet(model, level, meta) {
  const res = R.aroundOpenings(level, model.spec);
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, ubarRegions: false, pt: false });
    drawTrimmers(pl, sheet.S, res.regions.map((r) => ({ ...r, diagL: res.diagL, kind: 'OPENING' })), model.spec.openings, 'OPENING');
    const so = model.spec.openings;
    const d0 = sheet.detailBox(0, 'TRIMMERS AND DIAGONALS AT OPENING - PLAN', '1:25');
    const det0 = D.planTrimmers({ w: 1500, h: 1000, ld: res.ld, count: so.count, dia: so.dia, diag: true, diagDia: so.diagDia, diagL: res.diagL, uSpacing: so.uSpacing, uDia: so.uDia, label: 'OPENING' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT OPENING EDGE', '1:10');
    const det1 = D.sectionTrimmer({ h: level.thickness, cover: model.spec.cover, count: so.count, dia: so.dia, uLeg: so.uLeg, uDia: so.uDia, withU: true });
    det1.draw(sheet.detailPen(d1, 10, det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `${so.count}T${so.dia} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY OPENING (CALL-OUT "nT${so.dia}-T&B-MARK-(L)"), ANCHORED ld = ${res.ld} mm BEYOND THE CORNERS; ${so.diagCount}T${so.diagDia} DIAGONAL BARS TOP AND BOTTOM AT EACH RE-ENTRANT CORNER, L = ${res.diagL} mm; T${so.uDia}@${so.uSpacing} U-BARS WITH ${so.uLeg} mm LEGS ALONG THE FREE EDGES.`,
        'THE MAIN MESH IS STOPPED AT THE OPENING FACE LESS COVER; TRIMMERS REPLACE THE INTERRUPTED BARS. TENDONS ARE DEVIATED AROUND OPENINGS PER THE PT LAYOUT - NO TENDON MAY BE CUT.',
        ...lengthNote(model, [...new Set([so.dia, so.diagDia, so.uDia])]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR', `T${so.dia} TRIMMER / T${so.diagDia} DIAGONAL`, 'thick'], ['REBAR-U', `T${so.uDia} U-BAR (HAIRPIN)`, 'line'], ['OPENING', 'OPENING', 'line'], ['CALLOUT', 'OPENING ID', 'line']],
      detailsUsed: 2,
    };
  };
}

function punchingSheet(model, level, meta) {
  const res = R.punching(level, model.spec);
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, ubarRegions: false, pt: false });
    for (const { col, type, sides } of res.columns) {
      const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
      for (const sd of sides) {
        const faceLen = sd.faceLen;
        for (let r = 1; r <= sd.nRows; r++) {
          const dOff = sd.offset + r * res.rowSpacing;
          const a = sd.dir === 'x' ? { x: col.cx + sd.sign * dOff, y: col.cy - faceLen / 2 } : { x: col.cx - faceLen / 2, y: col.cy + sd.sign * dOff };
          const b = sd.dir === 'x' ? { x: col.cx + sd.sign * dOff, y: col.cy + faceLen / 2 } : { x: col.cx + faceLen / 2, y: col.cy + sd.sign * dOff };
          pl.line(a, b, { layer: 'REBAR-PUNCH' });
          for (let k = 0; k < sd.links; k++) {
            const f = sd.links > 1 ? k / (sd.links - 1) : 0.5;
            const p = { x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f };
            pl.line(sd.dir === 'x' ? { x: p.x - 40, y: p.y } : { x: p.x, y: p.y - 40 }, sd.dir === 'x' ? { x: p.x + 40, y: p.y } : { x: p.x, y: p.y + 40 }, { layer: 'REBAR-PUNCH' });
          }
        }
        const lp = sd.dir === 'x' ? { x: col.cx + sd.sign * (sd.offset + (sd.nRows + 1) * res.rowSpacing + 0.3 * S), y: col.cy + faceLen / 2 + 0.3 * S } : { x: col.cx + faceLen / 2 + 0.3 * S, y: col.cy + sd.sign * (sd.offset + (sd.nRows + 1) * res.rowSpacing) };
        pl.text(lp, `${sd.nRows}X${sd.links}-T${res.dia}-${res.rowSpacing}`, { layer: 'REBAR-TEXT', h: 1.6, rot: sd.dir === 'x' ? 90 : 0 });
      }
      pl.text({ x: col.cx - size.x / 2 - 1.5 * S, y: col.cy + size.y / 2 + 1.5 * S }, type.id, { layer: 'REBAR-RED', h: 2.5, align: 'R' });
    }
    for (const sr of level.ram?.shear || []) {
      pl.line(sr.a, sr.b, { layer: 'REBAR-PUNCH' });
      pl.barEnds(sr.a, sr.b, { layer: 'REBAR-PUNCH', size: 0.8 });
      let rotd = (Math.atan2(sr.b.y - sr.a.y, sr.b.x - sr.a.x) * 180) / Math.PI; if (rotd > 90 || rotd <= -90) rotd += 180;
      pl.text({ x: (sr.a.x + sr.b.x) / 2, y: (sr.a.y + sr.b.y) / 2 + 0.5 * S }, `${sr.id}: T${sr.dia}-${sr.legs}LEGS@${sr.spacing} (${sr.length})`, { layer: 'REBAR-TEXT', h: 1.6, rot: rotd, align: 'C' });
    }
    const d0 = sheet.detailBox(0, 'PUNCHING LINK - SHAPE AND ARRANGEMENT', '1:10');
    const det0 = D.punchingLink({ h: level.thickness, cover: model.spec.cover, dia: res.dia, rowSpacing: res.rowSpacing, legSpacing: res.legSpacing, rows: res.rows });
    det0.draw(sheet.detailPen(d0, 10, det0.bbox));
    const d1 = sheet.detailBox(1, 'PUNCHING TYPES (PS)', '');
    const tcols = [{ key: 'id', title: 'TYPE', w: 14 }, { key: 'size', title: 'COLUMN', w: 26 }, { key: 'arr', title: 'ROWS X LINKS - T - SPACING (PER FACE)', w: 90, align: 'L', max: 52 }, { key: 'cols', title: 'COLUMNS', w: (d1.w - 6) - 130, align: 'L', max: 36 }];
    sheet.table(d1.x + 3, d1.y + d1.h - 10, tcols, res.types.map((t) => ({ id: t.id, size: `${fmtMM(t.size.x)}x${fmtMM(t.size.y)}`, arr: t.label, cols: t.columns.join(', ') })), { maxRows: Math.floor((d1.h - 18) / 4), headH: 5, rowH: 4, h: 1.5 });
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: totalsLine(tot), weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level).slice(0, 3),
        `PRELIMINARY: PUNCHING LINKS ARE SHOWN AS THE MINIMUM DETAILING ARRANGEMENT (SBC 304-18 §8.7.6 / §22.6.8): T${res.dia} CLOSED LINKS, FIRST ROW AT d/2 = ${res.rowSpacing} mm FROM THE COLUMN FACE, ROWS AT d/2, LEGS AT ${res.legSpacing} mm ALONG THE FACE, EXTENDING ${res.extent} mm (2h) BEYOND THE FACE. THE NUMBER OF ROWS AND LINK SIZE ARE TO BE CONFIRMED AGAINST THE PUNCHING DESIGN (Vu) BEFORE FABRICATION.`,
        'CALL-OUT PER FACE: [ROWS] X [LINKS PER ROW] - T[Ø] - [ROW SPACING]. FACES AT A SLAB EDGE CARRY NO LINKS. LINKS ENCLOSE THE TOP AND BOTTOM BARS.',
        'PS TYPES GROUP COLUMNS WITH THE SAME ARRANGEMENT (TABLE, DETAIL 2).',
      ],
      assumptions: ['PUNCHING SHEAR DEMAND (Vu) NOT AVAILABLE: LINK ROWS SET BY MINIMUM DETAILING AND 2h EXTENT; SUBJECT TO DESIGN CONFIRMATION.', ...(level.ram ? [`RAM CONCEPT SPECIFIES STUD RAILS (${level.ram.punching[0]?.ssr ? 'SSR SYSTEM ' + level.ram.punching[0].ssr : 'SSR'}) AT ${level.ram.punching.length} PUNCHING CHECKS; THE STUD LAYOUT FROM THE RAM PUNCHING REPORT GOVERNS OVER THE LINKS SHOWN. SHEAR REGIONS (SR) ARE THE RAM TRANSVERSE REINFORCEMENT REGIONS.`] : []), ...levelAssumptions(model, level).slice(0, 4)],
      legend: [['REBAR-PUNCH', 'ROW OF LINKS', 'thick'], ['REBAR-RED', 'PS TYPE LABEL', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
      detailsUsed: 2,
    };
  };
}

/** Cables sheet from the RAM Concept tendons: plan 1 latitude, plan 2 longitude. */
function ramCablesSheet(model, level, meta) {
  return (sheet, [pl1, pl2]) => {
    const S = sheet.S;
    const pt = level.ram.pt;
    for (const pl of [pl1, pl2]) drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, regionLabels: false, ubarRegions: false });
    const rows = [];
    for (const t of level.ram.tendons) {
      const pl = t.spanSet === 'latitude' ? pl1 : pl2;
      pl.pline(t.pts, { layer: 'CABLE' });
      const [a, b] = [t.pts[0], t.pts[t.pts.length - 1]];
      const endSym = (p, q, live) => {
        const L = dist(p, q) || 1, ux = (q.x - p.x) / L, uy = (q.y - p.y) / L;
        if (live) pl.solid([{ x: p.x, y: p.y }, { x: p.x + ux * 1.2 * S - uy * 0.5 * S, y: p.y + uy * 1.2 * S + ux * 0.5 * S }, { x: p.x + ux * 1.2 * S + uy * 0.5 * S, y: p.y + uy * 1.2 * S - ux * 0.5 * S }, { x: p.x, y: p.y }], { layer: 'CABLE-LIVE' });
        else pl.circle(p, 0.5 * S, { layer: 'CABLE-LIVE' });
      };
      endSym(a, t.pts[1], t.live[0]); endSym(b, t.pts[t.pts.length - 2], t.live[1]);
      const mi = Math.floor(t.pts.length / 2);
      const m1 = t.pts[mi - 1] || a, m2 = t.pts[mi] || b;
      let rotd = (Math.atan2(m2.y - m1.y, m2.x - m1.x) * 180) / Math.PI; if (rotd > 90 || rotd <= -90) rotd += 180;
      pl.text({ x: (m1.x + m2.x) / 2, y: (m1.y + m2.y) / 2 + 0.5 * S }, `${t.id} (${t.strands}S)`, { layer: 'CABLE-TEXT', h: 1.7, rot: rotd, align: 'C' });
      rows.push({ id: t.id, type: `${pt.ductType || 'bonded'} ${t.harped ? 'H' : ''}`.trim(), strands: t.strands, profile: t.spanSet === 'latitude' ? 'P-LAT' : 'P-LON', length: (t.length / 1000).toFixed(2), live: t.live.filter(Boolean).length === 2 ? 'BOTH' : t.live[0] ? 'START' : t.live[1] ? 'END' : '-', jack: t.jackForce ?? '', elong: t.elongation ?? '', qty: 1, remarks: `${t.segments} SEG.` });
    }
    const cols = [
      { key: 'id', title: 'TENDON\nID', w: 16 }, { key: 'type', title: 'TYPE', w: 16 }, { key: 'strands', title: 'No.\nSTR.', w: 12 }, { key: 'profile', title: 'PROFILE\nREF.', w: 18 },
      { key: 'length', title: 'LENGTH\n(m)', w: 17 }, { key: 'live', title: 'LIVE\nEND', w: 16 }, { key: 'jack', title: 'JACK\n(kN)', w: 17 }, { key: 'elong', title: 'ELONG.\n(mm)', w: 17 }, { key: 'qty', title: 'QTY', w: 12 }, { key: 'remarks', title: 'REMARKS', w: 44, align: 'L' },
    ];
    const totalStrandM = level.ram.tendons.reduce((s, t) => s + (t.length / 1000) * t.strands, 0);
    const d0 = sheet.detailBox(0, 'TYPICAL TENDON PROFILE', '1:50');
    const span = level.grid.x.length > 1 ? level.grid.x[1].x - level.grid.x[0].x : 7500;
    const det0 = D.tendonProfile({ span, h: level.thickness });
    det0.draw(sheet.detailPen(d0, 50, det0.bbox));
    const d1 = sheet.detailBox(1, 'TENDON SYMBOLS', 'N.T.S.');
    const det1 = D.tendonLegend();
    det1.draw(sheet.detailPen(d1, 12, det1.bbox));
    const manyTendons = level.ram.tendons.length > 30;
    if (!manyTendons) {
      const d2 = sheet.detailBox(2, 'STRESSING RECORD', '');
      const recCols = [{ key: 'a', title: 'TENDON', w: 24 }, { key: 'b', title: 'DATE', w: 26 }, { key: 'c', title: 'GAUGE\n(bar)', w: 26 }, { key: 'd', title: 'ELONG.\nCALC.', w: 30 }, { key: 'e', title: 'ELONG.\nMEAS.', w: 30 }, { key: 'f', title: '%', w: 18 }, { key: 'g', title: 'SIGN', w: d2.w - 6 - 154 }];
      sheet.table(d2.x + 3, d2.y + d2.h - 10, recCols, level.ram.tendons.map((t) => ({ a: t.id, d: t.elongation ?? '' })), { maxRows: Math.floor((d2.h - 18) / 3.2), headH: 6, rowH: 3.2, h: 1.3 });
    }
    return {
      rows, cols, scheduleTitle: 'PT CABLES SCHEDULE (RAM CONCEPT)', detailsUsed: manyTendons ? 2 : 3, totals: `${level.ram.tendons.length} TENDONS · ${Math.round(totalStrandM)} m STRAND · ${level.ram.tendons.filter((t) => t.live[0]).length + level.ram.tendons.filter((t) => t.live[1]).length} LIVE ENDS`,
      planTitles: ['PT TENDON LAYOUT - LATITUDE (DIRECTION 1)', 'PT TENDON LAYOUT - LONGITUDE (DIRECTION 2)'],
      general: [
        commonNotes(model, level)[0],
        `PT SYSTEM: ${pt.system || ''} - ${pt.ductType || 'bonded'} FLAT DUCT ${pt.ductWidth ? `${pt.ductWidth} x ${pt.ductHeight} mm` : ''}, ${pt.strandsPerDuct || ''} STRANDS PER DUCT MAX. STRAND ${Math.round(Math.sqrt((4 * pt.strandArea) / Math.PI) * 10) / 10} mm, Aps = ${pt.strandArea} mm², fpu = ${Math.round(pt.fpu || 1860)} MPa, JACKING STRESS ${Math.round(level.ram.tendons[0]?.jackStress || pt.jackStress || 0)} MPa (${Math.round(((level.ram.tendons[0]?.jackStress || pt.jackStress || 0) / (pt.fpu || 1860)) * 100)} % fpu), EFFECTIVE STRESS ${Math.round(pt.fse || 0)} MPa.`,
        'TENDON PATHS, STRAND COUNTS, STRESSING ENDS, JACKING FORCES AND CALCULATED ELONGATIONS ARE READ FROM THE RAM CONCEPT MODEL. LIVE (STRESSING) ENDS ARE SHOWN WITH AN ARROW, DEAD ENDS WITH A CIRCLE. TENDON PROFILES PER THE RAM PROFILE REPORT (HIGH POINTS OVER SUPPORTS, LOW POINTS AT MID-SPAN).',
        'STRESSING AT NOT LESS THAN THE SPECIFIED TRANSFER STRENGTH; ELONGATION TOLERANCE ±7 % (SBC 304-18 §20.3.2 / PTI). RECORD EVERY TENDON IN DETAIL 3.',
      ],
      assumptions: levelAssumptions(model, level).slice(0, 4),
      legend: [['CABLE', 'TENDON', 'thick'], ['CABLE-LIVE', 'LIVE END (ARROW) / DEAD END (CIRCLE)', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL', 'WALL BELOW', 'thick']],
    };
  };
}

function cablesSheet(model, level, meta) {
  if (level.ram) return ramCablesSheet(model, level, meta);
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, columnIds: true, regionLabels: true, ubarRegions: false });
    sheet.stamp('EMPTY TEMPLATE - NO TENDONS SHOWN', 'TENDON LAYOUT, PROFILES AND QUANTITIES TO BE ADDED ON COMPLETION OF THE PT DESIGN');
    const cols = [
      { key: 'id', title: 'TENDON\nID', w: 16 }, { key: 'type', title: 'TYPE', w: 16 }, { key: 'strands', title: 'No.\nSTR.', w: 12 }, { key: 'profile', title: 'PROFILE\nREF.', w: 18 },
      { key: 'length', title: 'LENGTH\n(m)', w: 17 }, { key: 'live', title: 'LIVE\nEND', w: 16 }, { key: 'jack', title: 'JACK\n(kN)', w: 17 }, { key: 'elong', title: 'ELONG.\n(mm)', w: 17 }, { key: 'qty', title: 'QTY', w: 12 }, { key: 'remarks', title: 'REMARKS', w: 44, align: 'L' },
    ];
    const rows = Array.from({ length: 22 }, (_, i) => ({ id: `T-${String(i + 1).padStart(2, '0')}`, type: '', strands: '', profile: '', length: '', live: '', jack: '', elong: '', qty: '', remarks: '' }));
    const d0 = sheet.detailBox(0, 'TYPICAL TENDON PROFILE (TEMPLATE)', '1:50');
    const span = level.grid.x.length > 1 ? level.grid.x[1].x - level.grid.x[0].x : 7500;
    const det0 = D.tendonProfile({ span, h: level.thickness });
    det0.draw(sheet.detailPen(d0, 50, det0.bbox));
    const d1 = sheet.detailBox(1, 'TENDON SYMBOLS', 'N.T.S.');
    const det1 = D.tendonLegend();
    det1.draw(sheet.detailPen(d1, 12, det1.bbox));
    const d2 = sheet.detailBox(2, 'STRESSING RECORD (TEMPLATE)', '');
    const recCols = [{ key: 'a', title: 'TENDON', w: 24 }, { key: 'b', title: 'DATE', w: 26 }, { key: 'c', title: 'GAUGE\n(bar)', w: 26 }, { key: 'd', title: 'ELONG.\nCALC.', w: 30 }, { key: 'e', title: 'ELONG.\nMEAS.', w: 30 }, { key: 'f', title: '%', w: 18 }, { key: 'g', title: 'SIGN', w: d2.w - 6 - 154 }];
    sheet.table(d2.x + 3, d2.y + d2.h - 10, recCols, Array.from({ length: 20 }, () => ({})), { maxRows: Math.floor((d2.h - 18) / 4), headH: 6, rowH: 4, h: 1.5 });
    return {
      rows, cols, scheduleTitle: 'PT CABLES SCHEDULE - TEMPLATE',
      general: [
        commonNotes(model, level)[0],
        'THIS SHEET IS A TEMPLATE. TENDON PATHS, PROFILES, STRAND COUNTS, JACKING FORCES AND ELONGATIONS WILL BE ADDED AFTER THE PT DESIGN IS COMPLETE AND APPROVED; NOTHING ON THIS SHEET IS TO BE USED FOR FABRICATION.',
        'PT SYSTEM: BONDED / UNBONDED (TO BE CONFIRMED). STRAND: 15.24 mm (0.6") 7-WIRE LOW-RELAXATION, fpu = 1860 MPa, ASTM A416 / SASO EQUIVALENT (TO BE CONFIRMED).',
        'STRESSING AT NOT LESS THAN THE SPECIFIED TRANSFER STRENGTH; JACKING FORCE ≤ 0.80 fpu·Aps; ELONGATION TOLERANCE ±7 % (SBC 304-18 §20.3.2 / PTI). STRESSING RECORD PER TENDON TO BE KEPT ON THE TEMPLATE IN DETAIL 3.',
        'GRID, COLUMNS, SLAB OUTLINE, BEAMS, OPENINGS AND SUNKEN SLABS ARE SHOWN FOR REFERENCE ONLY, AS READ FROM THE G.A.',
      ],
      assumptions: ['TENDON LAYOUT NOT YET DESIGNED: SCHEDULE AND PROFILE LEFT BLANK BY INTENT.', ...levelAssumptions(model, level).slice(0, 3)],
      legend: [['CABLE', 'TENDON (TO BE ADDED)', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['OPENING', 'OPENING', 'line']],
      detailsUsed: 3,
    };
  };
}

function coverSheet(model, sheets, meta) {
  return (sheet) => {
    const P = sheet.L.plan;
    const pp = sheet.pp;
    pp.text(P.x + 10, P.y + P.h - 16, (meta.project || '').toUpperCase(), { layer: 'TEXT-TITLE', h: 6, bold: true });
    pp.text(P.x + 10, P.y + P.h - 26, 'REINFORCEMENT AND PT CABLES SHOP DRAWINGS - DRAWING INDEX', { layer: 'TEXT-TITLE', h: 4 });
    pp.text(P.x + 10, P.y + P.h - 34, `${meta.company}  ·  ${meta.client ? 'CLIENT: ' + meta.client + '  ·  ' : ''}${meta.location || ''}  ·  REV ${meta.revision}  ·  ${meta.date}`, { layer: 'TITLE', h: 2.6 });
    const cols = [{ key: 'no', title: 'DRAWING No.', w: 40 }, { key: 'title', title: 'DRAWING TITLE', w: 205 }, { key: 'level', title: 'LEVEL', w: 110, align: 'L', max: 40 }, { key: 'block', title: 'BLOCK / XREF NAME', w: 150, align: 'L' }, { key: 'scale', title: 'SCALE', w: 36 }, { key: 'wt', title: 'REBAR (kg)', w: 40 }, { key: 'rev', title: 'REV', w: 20 }];
    const rows = sheets.map((s) => ({ no: s.drawingNo, title: s.title, level: s.level === 'ALL' ? 'ALL' : `${s.level} - ${s.levelName}`, block: s.blockName, scale: s.scale ? `1:${s.scale}` : 'NTS', wt: s.weight ? Math.round(s.weight).toLocaleString('en-US') : '-', rev: meta.revision }));
    const totalW = sheets.reduce((s, x) => s + (x.weight || 0), 0);
    sheet.table(P.x + 10, P.y + P.h - 42, cols.map((c) => ({ ...c, align: c.align || (c.key === 'title' ? 'L' : 'C') })), rows, { title: 'DRAWING INDEX / LIST OF SHEETS', rowH: 5, h: 2, headH: 6, titleH: 7, totals: `TOTAL SCHEDULED REINFORCEMENT (ALL LEVELS) ${Math.round(totalW).toLocaleString('en-US')} kg` });
    const d0 = sheet.detailBox(0, 'LEVELS READ FROM THE STRUCTURAL DRAWINGS', '');
    const lcols = [{ key: 'id', title: 'ID', w: 14 }, { key: 'name', title: 'LEVEL', w: 70, align: 'L', max: 34 }, { key: 'thk', title: 'THK', w: 16 }, { key: 'cols', title: 'COLS', w: 16 }, { key: 'op', title: 'OPEN.', w: 16 }, { key: 'sk', title: 'SUNK.', w: 16 }, { key: 'vo', title: 'VOIDS', w: 16 }, { key: 'area', title: 'AREA m²', w: d0.w - 6 - 164 }];
    sheet.table(d0.x + 3, d0.y + d0.h - 10, lcols, model.levels.map((l) => ({ id: l.id, name: l.name, thk: l.thickness, cols: l.columns.length, op: l.openings.length, sk: (l.sunken || []).length, vo: l.voids.length, area: Math.round(Math.abs(R.polygonArea(l.outline)) / 1e6) })), { headH: 5, rowH: 4, h: 1.6, maxRows: 24 });
    const d1 = sheet.detailBox(1, 'DEVELOPMENT / LAP LENGTHS APPLIED (mm)', '');
    const tcols = [{ key: 'dia', title: 'Ø', w: 16 }, { key: 'ld_bottom', title: 'ld BOT', w: 30 }, { key: 'ld_top', title: 'ld TOP', w: 30 }, { key: 'lap_bottom', title: 'LAP BOT', w: 32 }, { key: 'lap_top', title: 'LAP TOP', w: 32 }, { key: 'ldh', title: 'ldh HOOK', w: d1.w - 6 - 140 }];
    sheet.table(d1.x + 3, d1.y + d1.h - 10, tcols, R.lengthTable(model.spec), { headH: 5, rowH: 4, h: 1.6 });
    const d2 = sheet.detailBox(2, 'HOW TO USE THE BLOCKS / XREFS', '');
    const how = ['EACH SHEET IS A BLOCK NAMED AS LISTED; THE SAME NAME IS ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1 AND THE FRAME IS SCALED BY THE SHEET SCALE.', 'LAYERS PER THE SPAN TECH STANDARD (ST-): ST-RB-B1 / B2 / T1 / T2 (BARS), ST-RB-UBAR, ST-RB-TRIM, ST-RB-PUNCH, ST-RB-TEXT (CALL-OUTS), ST-RB-MESH, ST-RB-TYPE, ST-GRID, ST-SLAB-EDGE, ST-COL, ST-BEAM, ST-OPENING, ST-SUNKEN, ST-VOID, ST-PT-*, ST-SHEET-*, ST-DIM, ST-CALLOUT.', 'EXPLODE A BLOCK TO EDIT; RE-RUN THE GENERATOR AFTER THE CONSULTANT REVISES THE G.A. AND RE-ATTACH.'];
    how.forEach((h, i) => pp.mtext(d2.x + 4, d2.y + d2.h - 12 - i * 14, h, { layer: 'NOTES', h: 1.8, width: d2.w - 8 }));
    return {
      general: [
        `PACKAGE GENERATED FROM THE CONSULTANT'S STRUCTURAL DRAWINGS: ${model.levels.length} SLAB LEVEL(S) READ.`,
        ...model.findings,
        `DESIGN DATA READ FROM THE DRAWINGS: ${model.spec.found.length ? model.spec.found.join('; ') : 'NONE (ALL REINFORCEMENT ASSUMED, SEE ASSUMPTIONS)'}.`,
      ],
      assumptions: model.assumptions.map((a) => (a.level ? `[${a.level}] ` : '') + a.text),
      legend: [],
      detailsUsed: 3,
    };
  };
}

// ------------------------------------------------------------------ package
export function composePackage(model, metaIn = {}) {
  const meta = {
    company: 'SPAN TECH CONTRACTING', company_line: 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
    project: 'PROJECT NAME', client: '', engineer: '', contractor: '', location: '', prefix: 'ST-SD', revision: '00',
    date: new Date().toISOString().slice(0, 10), prepared: '', checked: '', approved: '', status: 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
    ...metaIn,
  };
  const makers = { framing: framingSheet, bottom: bottomSheet, top: topSheet, addbottom: (m, l, mt) => ramBarsSheet(m, l, mt, 'B'), addtop: (m, l, mt) => ramBarsSheet(m, l, mt, 'T'), ubars: ubarSheet, voids: voidsSheet, openings: openingsSheet, cables: cablesSheet, punching: punchingSheet };
  const jobs = [];
  for (const level of model.levels) for (const def0 of SHEET_DEFS) {
    if (def0.ramOnly && !level.ram) continue;
    const def = level.ram && def0.key === 'cables' ? { ...def0, plans: 2, title: 'PT CABLES LAYOUT AND SCHEDULE (RAM CONCEPT)' } : def0;
    jobs.push({ level, def, draw: makers[def.key](model, level, meta) });
  }
  const total = jobs.length + 1;
  const sheets = jobs.map((j, i) => buildSheet({ model, level: j.level, def: j.def, meta, index: i + 2, total, draw: j.draw }));
  const cover = buildSheet({ model, level: null, def: { key: 'cover', base: 'SHOP_DRAWINGS_COVER_INDEX', title: 'COVER SHEET / DRAWING INDEX', no: '000' }, meta, index: 1, total, draw: coverSheet(model, sheets, meta) });
  const all = [cover, ...sheets];
  const std = meta.layerStandard;
  for (const s of all) {
    if (std?.textStyles) for (const [n, d] of Object.entries(std.textStyles)) s.root.textStyleDef(n, d);
    if (std?.layers) s.root.applyLayerStandard(std.layers);
  }

  const pkg = new Canvas();
  if (std?.textStyles) for (const [n, d] of Object.entries(std.textStyles)) pkg.textStyleDef(n, d);
  const perRow = 4;
  const gapX = 900 * 100, gapY = 650 * 100;
  all.forEach((s, i) => {
    for (const [name, def] of s.root.layers) if (!pkg.layers.has(name)) pkg.layers.set(name, def);
    pkg.blocks.set(s.blockName, s.root.blocks.get(s.blockName));
    const x = (i % perRow) * gapX, y = -Math.floor(i / perRow) * gapY;
    pkg.insert(s.blockName, x, y);
    pkg.text(x, y + 594 * s.scale + 1500, `${s.drawingNo}  ${s.title}${s.level !== 'ALL' ? `  (${s.level})` : ''}`, { layer: 'XREF', h: 1200 });
  });
  if (std?.layers) pkg.applyLayerStandard(std.layers);
  return { meta, sheets: all, pkg };
}
