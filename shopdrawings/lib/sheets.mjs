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
import { Sheet, chooseScale, layoutFor, DEFAULT_FRAME } from './sheet.mjs';
import * as R from './rebar.mjs';
import * as D from './details.mjs';
import * as RC from './ram-concept.mjs';
import { bbox, expandBbox, edges, rectPolygon, circlePolygon, dist, pointInPolygon, centroid, polygonArea } from './geometry.mjs';
import { size50 } from './beam-strips.mjs';

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
  { key: 'cables', base: 'CABLES_SCHEDULE_EMPTY_TEMPLATE', title: 'PT CABLES LAYOUT AND SCHEDULE - EMPTY TEMPLATE', no: '07', drawingOnly: true },
  // from a RAM model the cables come one direction per sheet, with the chair heights along every tendon (no tendon sections)
  { key: 'cables_lat', base: 'CABLES_LATITUDE_SHOP', title: 'PT CABLES - LATITUDE (DIRECTION 1) - LAYOUT, CHAIRS AND SCHEDULE', no: '07A', ramOnly: true, set: 'latitude' },
  { key: 'cables_lon', base: 'CABLES_LONGITUDE_SHOP', title: 'PT CABLES - LONGITUDE (DIRECTION 2) - LAYOUT, CHAIRS AND SCHEDULE', no: '07B', ramOnly: true, set: 'longitude' },
  { key: 'cables_cross', base: 'CABLES_CROSSINGS_SHOP', title: 'PT CABLES - TENDON CROSSINGS - WHICH TENDON PASSES OVER', no: '07C', ramOnly: true },
  { key: 'punching', base: 'FRAMING_REBAR_PUNCHING_LINKS', title: 'PUNCHING SHEAR REINFORCEMENT PLAN (PRELIMINARY)', no: '08' },
  // from a RAM model calculated with one design strip per beam: the beams typed, marked and scheduled
  { key: 'beams', base: 'BEAM_MARKS_SECTIONS_SCHEDULE', title: 'BEAM MARKS, SECTIONS AND REINFORCEMENT SCHEDULE - RAM DESIGN', no: '09', ramOnly: true, needsBeams: true },
];

export const SCHEDULE_COLS = [
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
const REBAR_STYLE = 'SPAN-REBAR';
export const fmtMM = (v) => Math.round(v).toLocaleString('en-US');
const regionBox = (o) => R.regionBbox(o);
const sizeOf = (o) => (o.kind === 'circle' ? `Ø${fmtMM(2 * o.r)}` : o.kind === 'rect' ? `${fmtMM(o.rect.w)} x ${fmtMM(o.rect.h)}` : `${fmtMM(regionBox(o).w)} x ${fmtMM(regionBox(o).h)} (POLY)`);
export const totalsLine = (tot) => `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`;

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
export function drawBase(sheet, pl, level, o = {}) {
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
  for (const w of level.walls || []) {
    // (hatch dense enough to read as a wall at 1:150: 0.25 mm on paper between the lines)
    if (w.polygon) { pl.pline(w.polygon, { layer: 'WALL', closed: true }); pl.hatch([w.polygon], { layer: 'WALL-HATCH', pattern: 'ANSI31', spacing: 0.25 }); }
    else pl.line(w.a, w.b, { layer: 'WALL' });
  }
  pl.pline(level.outline, { layer: 'OUTLINE', closed: true, color: 3 });
  for (const bm of level.beams || []) {
    if (bm.polygon && !bm.band) { pl.pline(bm.polygon, { layer: 'BEAM', closed: true }); if (o.regionLabels && bm.interior) { const c = centroid(bm.polygon); pl.text({ x: c.x, y: c.y }, `${bm.id} BEAM ${Math.round(bm.t)}${bm.depth ? 'x' + Math.round(bm.depth) : ''}`, { layer: 'BEAM', h: 1.5, align: 'C', valign: 'M', rot: Math.abs(bm.b.x - bm.a.x) >= Math.abs(bm.b.y - bm.a.y) ? 0 : 90 }); } }
    else if (!bm.polygon) pl.line(bm.a, bm.b, { layer: 'BEAM' });
  }
  if (o.thickZones !== false) for (const z of level.thickZones || []) {
    pl.pline(z.polygon, { layer: 'SLAB-THK', closed: true });
    pl.hatch([z.polygon], { layer: 'SLAB-THK-HATCH', pattern: 'ANSI31', spacing: 3 });
    if (o.regionLabels) { const c = centroid(z.polygon); pl.text({ x: c.x, y: c.y }, z.thickness ? `${z.id} THK=${z.thickness}` : `${z.id} DROP`, { layer: 'SLAB-THK', h: 1.5, align: 'C', valign: 'M' }); }
  }
  // pour strips: dashed outline, light hatch, label on the framing plan only
  if (o.pourStrips !== false) for (const ps of level.pourStrips || []) {
    pl.pline(ps.polygon, { layer: 'POUR-STRIP', closed: true });
    pl.hatch([ps.polygon], { layer: 'POUR-STRIP-HATCH', pattern: 'ANSI37', spacing: 2.5 });
    if (o.regionLabels) { const b = bbox(ps.polygon); const vertical = b.h > b.w; pl.text({ x: b.cx, y: b.cy }, `${ps.id} POUR STRIP ${fmtMM(ps.width)}`, { layer: 'POUR-STRIP', h: 1.5, align: 'C', valign: 'M', rot: vertical ? 90 : 0 }); }
  }
  // level tags
  if (o.regionLabels) for (const t of level.levelTags || []) pl.text({ x: t.x, y: t.y }, `${t.label} ${t.value}`, { layer: 'LEVEL', h: 1.8, align: 'C', valign: 'M' });
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
    pl.hatch([poly], { layer: o.columnHatchLayer || 'COLUMN-HATCH', pattern: 'SOLID' }); // solid grey, by layer (the office's s-hatch look)
    // (office rule: column ids are not written on the plans - the grid reference locates a column; the ids live in the schedules and notes)
  }
  // openings: crossed
  for (const op of level.openings) {
    const poly = R.polygonOf(op);
    pl.pline(poly, { layer: 'OPENING', closed: true });
    const b = bbox(poly);
    if (op.kind !== 'circle') { pl.line({ x: b.minX, y: b.minY }, { x: b.maxX, y: b.maxY }, { layer: 'OPENING' }); pl.line({ x: b.maxX, y: b.minY }, { x: b.minX, y: b.maxY }, { layer: 'OPENING' }); }
    // (office rule: an opening is not labelled on the plan - the crossed outline says what it is; its id and size stay in the element list)
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
    if (o.regionLabels) { const c = centroid(poly); pl.text({ x: c.x, y: c.y + 120 }, sk.step ? `${sk.id} ${sk.step > 0 ? 'RAISED' : 'SUNKEN'} ZONE T.O.S ${sk.tos}` : `${sk.id} SUNKEN SLAB`, { layer: 'SUNKEN', h: 1.4, align: 'C' }); pl.text({ x: c.x, y: c.y - 150 }, sk.step ? `STEP ${sk.step > 0 ? '+' : ''}${sk.step} mm` : `TH=${sk.thickness || '?'}mm`, { layer: 'SUNKEN', h: 1.4, align: 'C' }); }
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
function drawRun(pl, S, { a, b, pieces, lap, hooks = {}, hookLeg = 0, hookLabel, hookLabels = {}, label, layer = 'REBAR', offsetSide = 1, textSide = 1 }) {
  const L = dist(a, b) || 1;
  const ux = (b.x - a.x) / L, uy = (b.y - a.y) / L;
  const nx = -uy, ny = ux;
  const at = (s, off = 0) => ({ x: a.x + ux * s + nx * off, y: a.y + uy * s + ny * off });
  let rot = (Math.atan2(uy, ux) * 180) / Math.PI;
  if (rot >= 89.5 || rot < -90.5) rot += 180;
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
    if (i === 0 && hooks.start) pl.text(at(-0.4 * S, tn * 0.55 * S), hookLabels.start || hookLabel || String(hookLeg), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: HOOK_H, rot, align: 'R', valign: 'B' });
    if (i === last && hooks.end) pl.text(at(s1 + 0.4 * S, tn * 0.55 * S), hookLabels.end || hookLabel || String(hookLeg), { layer: 'REBAR-TEXT', style: REBAR_STYLE, h: HOOK_H, rot, align: 'L', valign: 'B' });
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
    const uEnd = face === 'T' ? R.topEdgeEnd(level, spec) : null; // top bars end in a U (500 bottom leg) at the edge
    const hk = uEnd ? uEnd.leg : R.hookLeg(b.dia);
    const straight = dist(rep.a, rep.b);
    const cut = Math.ceil((straight + (hooks.start ? hk : 0) + (hooks.end ? hk : 0)) / 10) * 10;
    const lap = R.lapLength(spec, b.dia, { top: face === 'T' });
    const pieces = cut > spec.stock ? R.splitRun(cut, { stock: spec.stock, lap }) : [cut];
    const marks = pieces.map((len) => lists[code].add({ dia: b.dia, shape: pieces.length > 1 ? 'STR' : hooks.start && hooks.end ? (uEnd ? 'UU' : 'C') : hooks.start || hooks.end ? (uEnd ? 'U' : 'L') : 'STR', length: len, qty: b.count, spacing: b.spacing, zone: b.id, note: hooks.start || hooks.end ? (uEnd ? uEnd.note : `hook ${hk}`) : '' }));
    const side = k++ % 2 ? -1 : 1;
    drawRun(pen, S, { a: rep.a, b: rep.b, pieces, lap, hooks: pieces.length > 1 ? {} : hooks, hookLeg: hk, hookLabel: uEnd ? uEnd.label : undefined, layer: `REBAR-${face}${code}`, textSide: side, offsetSide: side, label: (i, c) => callout(b.count, b.dia, b.spacing, marks[i].mark, c) });
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

export const commonNotes = (model, level) => [
  'ALL DIMENSIONS ARE IN MILLIMETRES, LEVELS IN METRES UNLESS NOTED OTHERWISE. DO NOT SCALE; FOLLOW THE WRITTEN DIMENSIONS.',
  `CONCRETE f'c = ${model.spec.fc} MPa (${model.spec.sources.fc}). REINFORCEMENT: DEFORMED BARS fy = ${model.spec.fy} MPa (${model.spec.sources.fy}). CLEAR COVER ${model.spec.cover} mm TOP AND BOTTOM (${model.spec.sources.cover}).`,
  `SLAB THICKNESS ${level.thickness} mm. THIS SHEET IS TO BE READ WITH THE CONSULTANT'S STRUCTURAL DRAWINGS (G.A.) AND THE PT LAYOUT; DISCREPANCIES TO BE REFERRED TO THE ENGINEER BEFORE FABRICATION.`,
  'BAR CALL-OUT: [No.] T[Ø] @[SPACING] - [LAYER-MARK] - (L = CUTTING LENGTH). STRAIGHT LENGTH IS WRITTEN UNDER THE BAR; A HOOK LEG IS WRITTEN AT THE HOOKED END. T1/T2 = TOP LAYERS, B1/B2 = BOTTOM LAYERS (1 = BARS PARALLEL TO THE NUMBERED GRIDS, 2 = PARALLEL TO THE LETTERED GRIDS).',
  'THE DRAWN BAR IS REPRESENTATIVE OF THE GROUP; THE NUMBER OF BARS IN THE CALL-OUT IS PLACED AT THE GIVEN SPACING ACROSS THE ZONE. A SHORT OFFSET LINE MARKS THE LAP OF THE FOLLOWING PIECE.',
  'TENSION LAPS ARE CLASS B (1.3 ld) PER SBC 304-18 §25.5.2, SO ALL BARS OF A ROW MAY LAP AT THE SAME SECTION. BARS ENDING AT A FREE EDGE TERMINATE WITH A STANDARD 90° HOOK (12 Ø) UNLESS NOTED.',
];

const lengthNote = (model, dias) => R.lengthTable(model.spec, dias).map((r) => `Ø${r.dia}: ld ${r.ld_bottom} (bot) / ${r.ld_top} (top) · LAP ${r.lap_bottom} (bot) / ${r.lap_top} (top) · ldh ${r.ldh}`);

export const codeText = (model) => (model.spec.sources.code === 'drawing'
  ? `${model.code_reference} AS STATED ON THE STRUCTURAL DRAWINGS. DEVELOPMENT, ANCHORAGE AND LAP LENGTHS PER SBC 304-18 CHAPTER 25 (ACI 318-14 BASIS).`
  : 'SAUDI PRACTICE ASSUMED: SBC 304-18 (SAUDI BUILDING CODE - CONCRETE STRUCTURES, BASED ON ACI 318-14) FOR DEVELOPMENT, ANCHORAGE AND LAP LENGTHS. TO BE ADJUSTED ON RECEIPT OF THE FINAL DESIGN CRITERIA / CONSULTANT REQUIREMENTS.');

export const levelAssumptions = (model, level) => model.assumptions.filter((a) => !a.level || a.level === level.id).map((a) => a.text);

/** Build one sheet. `draw(sheet, pens)` returns { rows, cols, scheduleTitle, totals, general, legend, extra, detailsUsed } */
/**
 * The extent of everything a level's sheets draw: the slab outline with the walls, beams, columns, thickness zones,
 * openings and tendons that reach beyond it (a wall or beam running past the slab edge, a tendon anchored outside).
 * The sheet scale is picked on this, so the plan never runs out of the frame.
 */
export function contentBbox(level) {
  const pts = [...(level.outline || [])];
  for (const w of level.walls || []) { if (w.polygon) pts.push(...w.polygon); else if (w.a && w.b) pts.push(w.a, w.b); }
  for (const bm of level.beams || []) { if (bm.a && bm.b) pts.push(bm.a, bm.b); }
  for (const c of level.columns || []) { const r = Math.max(c.w || 0, c.h || 0, c.d || 0) / 2; pts.push({ x: c.cx - r, y: c.cy - r }, { x: c.cx + r, y: c.cy + r }); }
  for (const z of [...(level.thickZones || []), ...(level.openings || [])]) if (z.polygon) pts.push(...z.polygon);
  for (const t of level.ram?.tendons || []) pts.push(...(t.pts || []));
  const b = pts.length >= 2 ? bbox(pts) : level.bbox;
  // nothing farther than a bay from the slab drives the scale (a stray reference entity must not shrink the plan)
  const lim = expandBbox(level.bbox, 6000);
  return bbox([{ x: Math.max(b.minX, lim.minX), y: Math.max(b.minY, lim.minY) }, { x: Math.min(b.maxX, lim.maxX), y: Math.min(b.maxY, lim.maxY) }]);
}

export function buildSheet({ model, level, def, meta, index, total, draw }) {
  const root = new Canvas();
  const blockName = level ? `${def.base}_${level.id}` : def.base;
  const frameOpts = meta.frame || {};
  const L = layoutFor(frameOpts.size || 'A1', frameOpts);
  // plan margin: room for the grid bubbles (3000 + 2 x 4S) plus a little air; the
  // scale is picked with a provisional margin and the margin re-fitted to it.
  const marginFor = (sc) => 3000 + 8 * (sc / 100) + 400;
  const extent = level ? contentBbox(level) : null;
  let pb = level ? expandBbox(extent, marginFor(200)) : null;
  const stacked = [{ x: L.plan.x, y: L.plan.y + L.plan.h / 2, w: L.plan.w, h: L.plan.h / 2 }, { x: L.plan.x, y: L.plan.y, w: L.plan.w, h: L.plan.h / 2 }];
  const pick = () => {
    let areas = def.plans === 2 ? L.halves : [L.plan];
    if (level && def.plans === 2 && chooseScale(pb, stacked[0]) < chooseScale(pb, L.halves[0])) areas = stacked;
    return areas;
  };
  let areas = pick();
  let scale = level ? Math.max(...areas.map((a) => chooseScale(pb, a))) : 100;
  if (level) { pb = expandBbox(extent, marginFor(scale)); areas = pick(); scale = Math.max(...areas.map((a) => chooseScale(pb, a))); }
  const sheet = new Sheet(root, { blockName, scale, frame: frameOpts });
  const custom = Array.isArray(meta.frameEntities) && meta.frameEntities.length > 0;
  if (!custom) sheet.frame();
  const pens = level ? areas.map((a) => sheet.setPlan(pb, a)) : [];
  const r = draw(sheet, pens) || {};
  const drawingNo = level ? `${meta.prefix}-${level.id}-${def.no}` : `${meta.prefix}-000`;

  let leftover = [];
  if (r.rows && sheet.L.schedule.h > 0) {
    const Sc = sheet.L.schedule;
    const rowH = r.rowH || 4;
    const maxRows = Math.floor((Sc.h - 6 - 6 - 5 - 6) / rowH);
    const res = sheet.table(Sc.x, Sc.y + Sc.h - 3, r.cols || SCHEDULE_COLS, r.rows, { title: r.scheduleTitle || 'BAR BENDING SCHEDULE', maxRows, rowH, h: r.rowH ? Math.min(1.7, r.rowH * 0.45) : 1.7, totals: r.totals || null });
    leftover = res.leftover;
    if (leftover.length && (r.detailsUsed ?? 3) >= 3) {
      sheet.pp.text(Sc.x + 2, Sc.y + 1.5, `+ ${leftover.length} MORE ROWS - SEE THE SCHEDULE FILE OF THIS SHEET`, { layer: 'SCHEDULE-TEXT', h: 1.6 });
    } else if (leftover.length) {
      const used = r.detailsUsed ?? 3;
      const box = sheet.L.details[Math.min(used, 2)];
      sheet.pp.rect(box.x, box.y, box.w, box.h, { layer: 'FRAME' });
      const cols = (r.cols || SCHEDULE_COLS).map((c) => ({ ...c, w: (c.w * (box.w - 6)) / 185 }));
      const res2 = sheet.table(box.x + 3, box.y + box.h - 3, cols, leftover, { title: (r.scheduleTitle || 'BAR BENDING SCHEDULE') + ' (CONT.)', maxRows: Math.floor((box.h - 22) / rowH), rowH, h: r.rowH ? Math.min(1.7, r.rowH * 0.45) : 1.7, totals: r.totals || null });
      leftover = res2.leftover;
    }
  }
  if (sheet.L.keyplan.h > 0) sheet.keyPlan(level ? level.outline : (model.levels[0] && model.levels[0].outline));
  sheet.notes({ general: r.general || [], assumptions: r.assumptions || [], codeRef: codeText(model), legend: r.legend || [], extra: r.extra || [] });
  const titleData = {
    ...meta,
    title: def.title,
    level: level ? `${level.id} - ${level.name}` : 'ALL LEVELS',
    drawingNo,
    sheet: `${index} OF ${total}`,
    scale: level ? `1:${scale} (DETAILS AS NOTED)` : 'N.T.S.',
    gridRef: level ? `${level.grid.x[0]?.label}-${level.grid.x[level.grid.x.length - 1]?.label} / ${level.grid.y[0]?.label}-${level.grid.y[level.grid.y.length - 1]?.label}` : 'ALL',
    index: `${meta.prefix}-000`,
    codeRef: model.code_reference ? `${model.code_reference} (ON DRAWINGS)` : 'SBC 304-18 (ASSUMED)',
  };
  if (custom) {
    // the office's own frame carries the title block and references; the sheet's data fills its {TOKENS}
    sheet.customFrame(meta.frameEntities, {
      PROJECT: (meta.project || '').toUpperCase(), PROJECT_CODE: meta.projectCode || '', CLIENT: meta.client || '', CONSULTANT: meta.engineer || '', ENGINEER: meta.engineer || '', CONTRACTOR: meta.contractor || '',
      LOCATION: meta.location || '', COMPANY: meta.company || '', COMPANY_LINE: meta.company_line || '', TITLE: def.title, LEVEL: titleData.level, LEVEL_NAME: level ? level.name : '', DRAWING_NO: drawingNo, REV: meta.revision || '00',
      DATE: meta.date || '', SCALE: titleData.scale, SHEET: titleData.sheet, PREPARED: meta.prepared || '', DESIGNER: meta.designer || meta.prepared || '', CHECKED: meta.checked || '', APPROVED: meta.approved || '', STATUS: meta.status || '', GRID_REF: titleData.gridRef, INDEX: titleData.index, CODE_REF: titleData.codeRef,
    });
  } else {
    if (sheet.L.refs.h > 0) sheet.refsBlock(meta);
    sheet.titleBlock(titleData);
  }
  if (level) {
    const titles = r.planTitles || [def.title];
    areas.forEach((a, i) => sheet.planTitleAt(a, i + 1, `${level.name} - ${titles[i] || def.title}`, `SCALE : 1:${scale}`));
  }
  root.insert(blockName, 0, 0);
  return { root, sheet, blockName, drawingNo, title: def.title, level: level ? level.id : 'ALL', levelName: level ? level.name : '', scale, key: def.key, rows: r.rows || [], csvCols: r.cols || SCHEDULE_COLS, weight: r.weight || 0, leftoverRows: leftover.length, checks: r.checks || [] };
}

/** Group items by key when there are more than six of them; one schedule row per group. */
function summarise(items, keyOf, rowOf) {
  if (items.length <= 6) return items.map((it) => rowOf(it, keyOf(it), 1, it.id, [it]));
  const groups = new Map();
  for (const it of items) { const k = keyOf(it); if (!groups.has(k)) groups.set(k, []); groups.get(k).push(it); }
  return [...groups.values()].map((g) => rowOf(g[0], keyOf(g[0]), g.length, g.length > 1 ? `${g[0].id}-${g[g.length - 1].id}` : g[0].id, g));
}

// ------------------------------------------------------------------ sheets
function framingSheet(model, level, meta) {
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { regionLabels: true, gridTag: meta.gridTag });
    const thkList = [...new Set((level.thickZones || []).map((z) => z.thickness).filter(Boolean))];
    const drops = (level.thickZones || []).filter((z) => !z.thickness).length;
    pl.text({ x: level.bbox.minX + 800, y: level.bbox.minY - 1200 }, `PT FLAT SLAB TH=${level.thickness}mm${level.tos ? ` T.O.S ${level.tos}` : ''}${thkList.length ? ` (THICKENED ZONES ${thkList.join(' / ')} mm HATCHED)` : ''}${drops ? ` (${drops} DROP PANELS HATCHED - DEPTH PER STRUCTURAL DRAWINGS)` : ''}`, { layer: 'TEXT', h: 2.6, bold: true });
    for (const op of level.openings) { const b = regionBox(op); pl.bubble({ x: b.maxX, y: b.maxY }, op.id, { dx: 7, dy: 7, layer: 'CALLOUT', r: 3, h: 1.6 }); }
    for (const v of level.voids) { const b = regionBox(v); pl.bubble({ x: b.minX, y: b.maxY }, v.id, { dx: -7, dy: 7, layer: 'CALLOUT', r: 3, h: 1.6 }); }
    for (const u of level.ubar.circles) pl.bubble({ x: u.cx, y: u.cy }, u.id, { dx: 9, dy: -9, layer: 'CALLOUT' });
    const rows = [
      ...level.columns.map((c) => ({ id: c.id, element: c.shape === 'circle' ? 'COLUMN (ROUND)' : c.w > 3 * c.h || c.h > 3 * c.w ? 'WALL / BLADE COL.' : 'COLUMN', size: c.shape === 'circle' ? `Ø${fmtMM(c.d)}` : `${fmtMM(c.w)} x ${fmtMM(c.h)}`, location: `X ${fmtMM(c.cx)}, Y ${fmtMM(c.cy)}` })),
      ...level.openings.map((o) => ({ id: o.id, element: 'OPENING', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...level.voids.map((o) => ({ id: o.id, element: 'VOID / ACUAR', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...(level.sunken || []).map((o) => ({ id: o.id, element: o.step ? `${o.step > 0 ? 'RAISED' : 'SUNKEN'} ZONE T.O.S ${o.tos} (STEP ${o.step})` : `SUNKEN SLAB TH=${o.thickness || '?'}`, size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...summarise((level.thickZones || []), (z) => (z.thickness ? `THK ${z.thickness}` : 'DROP') + ` ${fmtMM(bbox(z.polygon).w)} x ${fmtMM(bbox(z.polygon).h)}`, (z, key, n, ids) => ({ id: ids, element: z.thickness ? `THICKENED ZONE / BAND ${z.thickness} mm${n > 1 ? ` (${n} No.)` : ''}` : `DROP PANEL (DEPTH PER STRUCT. DWG)${n > 1 ? ` (${n} No.)` : ''}`, size: `${fmtMM(bbox(z.polygon).w)} x ${fmtMM(bbox(z.polygon).h)}`, location: n > 1 ? 'AT COLUMNS - SEE PLAN' : gridRef(level, bbox(z.polygon)) })),
      ...(level.pourStrips || []).map((z) => ({ id: z.id, element: 'POUR STRIP', size: `${fmtMM(z.width)} x ${fmtMM(z.length)}`, location: gridRef(level, bbox(z.polygon)) })),
      ...summarise((level.walls || []).filter((w) => w.polygon), (w) => `T${Math.round(w.t / 10) * 10}`, (w, key, n, ids, all) => ({ id: ids, element: `WALL BELOW ${fmtMM(w.t)} THK${n > 1 ? ` (${n} No.)` : ''}`, size: n > 1 ? `${(all.reduce((s, x) => s + x.length, 0) / 1000).toFixed(1)} m TOTAL` : `${fmtMM(w.t)} x ${fmtMM(w.length)}`, location: n > 1 ? 'SEE PLAN (HATCHED)' : gridRef(level, bbox(w.polygon)) })),
      ...(level.walls && level.walls.some((w) => !w.polygon) ? [{ id: 'W', element: 'WALLS BELOW (LINE SUPPORTS)', size: `${(level.walls.filter((w) => !w.polygon).reduce((s, w) => s + dist(w.a, w.b), 0) / 1000).toFixed(1)} m`, location: `${level.walls.filter((w) => !w.polygon).length} SEGMENTS` }] : []),
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
      legend: [['OUTLINE', 'SLAB EDGE (GREEN)', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL-HATCH', 'WALL BELOW (HATCHED)', 'hatch'], ['BEAM', 'BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SUNKEN-HATCH', 'SUNKEN / STEPPED ZONE', 'hatch'], ['SLAB-THK-HATCH', 'DROP PANEL / THICKENED ZONE', 'hatch'], ['POUR-STRIP-HATCH', 'POUR STRIP', 'hatch'], ['VOID', 'VOID / ACUAR', 'line'], ['PT-ZONE', 'PT ZONE', 'line']],
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
    // office rule: the bottom mesh is written at every change of slab thickness
    const tm = model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh;
    for (const z of [...(level.thickZones || []).map((z) => z.polygon), ...(level.sunken || []).map((o) => R.polygonOf(o))]) {
      const b = bbox(z); plY.text({ x: b.minX + 500, y: b.maxY - 700 }, `BOTTOM MESH T${tm.dia}@${tm.spacing}`, { layer: 'REBAR-MESH', h: 2.2 });
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
        `THE BOTTOM MESH (T${(model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh).dia}@${(model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh).spacing}, PER THE DESIGN) IS WRITTEN AT EVERY CHANGE OF SLAB THICKNESS (THICKENED / STEPPED ZONES).`,
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
        drawRun(pl, S, { a, b, pieces: [p.length], lap: 0, hooks: { start: !!p.hooks[-1], end: !!p.hooks[1] }, hookLeg: p.hookLeg, hookLabel: p.hookLabel, hookLabels: p.hookLabels, layer: `REBAR-${p.code}`, label: (i, cut) => callout(p.n, s.dia, s.spacing, type[dir].mark.mark, cut) });
        // the width the bars are distributed over (office rule: the length of the crossing bars at this column)
        if (p.band) {
          const st = a0 + (b0 - a0) * 0.3;
          const q1 = dir === 'x' ? { x: st, y: t - p.band / 2 } : { x: t - p.band / 2, y: st }, q2 = dir === 'x' ? { x: st, y: t + p.band / 2 } : { x: t + p.band / 2, y: st };
          pl.dim(q1, q2, 0, { layer: 'DIM', h: 1.6, text: String(Math.round(p.band)) });
        }
        const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
        pl.bubble({ x: col.cx + size.x / 2, y: col.cy + size.y / 2 }, type.id, { dx: 6, dy: 6, layer: 'CALLOUT', r: 3, h: 1.6 });
        seen.add(type.id);
      }
    }
    const t0 = res.types[0];
    const d0 = sheet.detailBox(0, 'SECTION AT COLUMN - TOP BARS', '1:25');
    const c0 = res.columns[0]?.col;
    const det0 = D.sectionColumn({ h: level.thickness, c1: c0 ? (c0.shape === 'circle' ? c0.d : c0.w) : 600, ext: t0 ? Math.max(t0.x.ext[-1], t0.x.ext[1]) : 1200, dia: s.dia, spacing: s.spacing, cover: model.spec.cover, hookLeg: res.uEnd.leg, shape: t0 ? (res.rule === 'office' && t0.x.shape === 'STR' && res.types.some((t) => /U/.test(t.x.shape) || /U/.test(t.y.shape)) ? 'U' : t0.x.shape) : 'U', uReturn: R.U_BOTTOM_LEG });
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
        res.rule === 'office'
          ? `ADDITIONAL TOP BARS T${s.dia}@${s.spacing} OVER EVERY COLUMN: T1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), T2 PARALLEL TO THE LETTERED GRIDS (PLAN 2), PLACED WITHIN c2 + 1.5h EACH SIDE OF THE COLUMN. OFFICE RULE: AN INTERIOR COLUMN BAR COVERS THE DROP PANEL WHERE THERE IS ONE, OTHERWISE ${res.length} mm IN TOTAL; AN EDGE COLUMN BAR ENDS IN A U AT THE SLAB EDGE (DOWN THE SLAB, ${R.U_BOTTOM_LEG} mm BACK AT THE BOTTOM) AND RUNS ${Math.round(res.edgeFactor * 100)} % OF THE INTERIOR LENGTH (${Math.round(res.edgeFactor * res.length)} mm) ON TOP FROM THE EDGE.`
          : `ADDITIONAL TOP BARS T${s.dia}@${s.spacing} OVER EVERY COLUMN: T1 PARALLEL TO THE NUMBERED GRIDS (PLAN 1), T2 PARALLEL TO THE LETTERED GRIDS (PLAN 2), PLACED WITHIN c2 + 1.5h EACH SIDE OF THE COLUMN (SBC 304-18 §8.7.5.5.1) AND EXTENDING NOT LESS THAN ln/6 BEYOND THE FACE OF SUPPORT (§8.7.5.5.2).`,
        `EVERY TOP BAR THAT ENDS AT THE OUTER SLAB EDGE OR AT AN OPENING ENDS IN A U: VERTICAL LEG THROUGH THE SLAB DEPTH AND A ${R.U_BOTTOM_LEG} mm BOTTOM LEG ("${res.uEnd.label}" AT THE BAR END; SHAPE U / UU IN THE SCHEDULE, THE CUTTING LENGTH INCLUDES BOTH LEGS).`,
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
      for (const [p, q] of e.runs) for (let d = p + su.spacing / 2; d < q; d += step) {
        const at = { x: e.a.x + ux * d + nx * cover, y: e.a.y + uy * d + ny * cover };
        if (e.beam) { pl.line(at, { x: at.x + nx * e.leg, y: at.y + ny * e.leg }, { layer: 'REBAR-U' }); pl.line(at, { x: at.x - nx * 200, y: at.y - ny * 200 }, { layer: 'REBAR-U' }); }
        else hairpin(pl, at, { x: nx, y: ny }, e.leg, 120);
      }
      const mid = { x: (e.a.x + e.b.x) / 2 + nx * (su.leg + 500), y: (e.a.y + e.b.y) / 2 + ny * (su.leg + 500) };
      let rot = (Math.atan2(uy, ux) * 180) / Math.PI; if (rot >= 89.5 || rot < -90.5) rot += 180;
      pl.text(mid, e.beam ? `${e.n}T${su.dia}@${su.spacing}-${e.uMark.mark}-(L=${e.uMark.length}) L-BARS ${su.beamLeg} IN BEAM + ${su.beamTop} TOP` : `${e.n}T${su.dia}@${su.spacing}-${e.uMark.mark}-(L=${e.uMark.length}) U-BARS LEGS ${e.leg} T&B`, { layer: 'REBAR-TEXT', h: CALL_H, rot, align: 'C' });
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
    const det0 = D.sectionUEdge({ h: level.thickness, cover, leg: res.uLegTop, dia: su.dia, edgeDia: se.dia, spacing: su.spacing });
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
        `OFFICE PERIMETER RULE: T${su.dia}@${su.spacing} ALONG THE WHOLE SLAB PERIMETER BETWEEN THE COLUMN TOP BARS. AT A FREE EDGE A U-BAR ${su.total} mm LONG WITH EQUAL TOP AND BOTTOM LEGS (${res.uLegTop} mm, DEPTH ${res.web} mm); AT AN EDGE BEAM AN L-BAR ${res.lLen} mm LONG: ${su.beamLeg} mm LEG DOWN INTO THE BEAM AND ${su.beamTop} mm ON TOP IN THE SLAB. WITH ${se.count}T${se.dia} LONGITUDINAL BARS TOP AND BOTTOM INSIDE THEM (ONE REPRESENTATIVE BAR PER EDGE).`,
        `AROUND CIRCULAR REGIONS: RADIAL U-BARS T${sc.dia}@${sc.spacing} (LEGS ${sc.leg}) PLUS ${sr.count}T${sr.dia} RING BARS TOP AND BOTTOM, RINGS LAPPED CLASS B.`,
        'U-BARS ARE PLACED BEFORE THE ANCHORAGES ARE FIXED; DO NOT CUT U-BARS TO SUIT ANCHORAGE POCKETS - RELOCATE WITHIN THE SPACING.',
        ...lengthNote(model, [...new Set([su.dia, se.dia, sc.dia])]),
      ],
      assumptions: [...levelAssumptions(model, level), ...res.assumptions],
      legend: [['REBAR-U', 'U-BAR (HAIRPIN) / L-BAR AT EDGE BEAM (LEG SYMBOL)', 'thick'], ['REBAR', 'EDGE / RING BAR', 'thick'], ['CALLOUT', 'EDGE / REGION ID', 'line']],
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
      let rot = (Math.atan2(c.dy, c.dx) * 180) / Math.PI; if (rot >= 89.5 || rot < -90.5) rot += 180;
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
    for (const o of res.lined || []) { const b = regionBox(o); pl.text({ x: b.cx, y: b.cy }, `${o.id}: ENCLOSED BY WALLS / BEAMS - NO TRIMMERS`, { layer: 'REBAR-TEXT', h: 1.5, align: 'C', valign: 'M' }); }
    // the three bar groups around every opening: parallel to the two sides and the 45° diagonals crossing them
    const groupRows = res.regions.flatMap((r) => {
      const trX = r.trimmers.filter((t) => Math.abs(t.uy) < 0.5), trY = r.trimmers.filter((t) => Math.abs(t.uy) >= 0.5);
      const g = (id, dirLabel, list) => ({ id: r.region.id, g: id, dir: dirLabel, bars: list.length ? `${list.length} SIDES x ${so.count} T${so.dia} T&B = ${list.length * 2 * so.count}` : '-', marks: [...new Set(list.flatMap((t) => t.marks))].join(', ') });
      return [g('G1', 'PARALLEL TO THE LETTERED GRIDS (X)', trX), g('G2', 'PARALLEL TO THE NUMBERED GRIDS (Y)', trY), { id: r.region.id, g: 'G3', dir: 'DIAGONAL 45° ACROSS G1 AND G2', bars: r.corners.length ? `${r.corners.length} CORNERS x ${so.diagCount} T${so.diagDia} T&B = ${r.corners.length * 2 * so.diagCount}` : '-', marks: r.diagMark ? r.diagMark.mark : '' }];
    });
    const d0 = sheet.detailBox(0, 'TRIMMERS AND DIAGONALS AT OPENING - PLAN', '1:25');
    const det0 = D.planTrimmers({ w: 1500, h: 1000, ld: res.ld, count: so.count, dia: so.dia, diag: true, diagDia: so.diagDia, diagL: res.diagL, uSpacing: so.uSpacing, uDia: so.uDia, label: 'OPENING' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT OPENING EDGE', '1:10');
    const d2 = sheet.detailBox(2, 'BAR GROUPS AROUND EACH OPENING (G1 / G2 PARALLEL, G3 DIAGONAL)', '');
    const gcols = [{ key: 'id', title: 'OPEN.', w: 16 }, { key: 'g', title: 'GRP', w: 12 }, { key: 'dir', title: 'DIRECTION', w: 78, align: 'L', max: 40 }, { key: 'bars', title: 'BARS (No.)', w: 62, align: 'L', max: 32 }, { key: 'marks', title: 'MARKS', w: d2.w - 6 - 168, align: 'L', max: 24 }];
    sheet.table(d2.x + 3, d2.y + d2.h - 10, gcols, groupRows, { headH: 5, rowH: 3.6, h: 1.4, maxRows: Math.floor((d2.h - 18) / 3.6) });
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
      let rotd = (Math.atan2(sr.b.y - sr.a.y, sr.b.x - sr.a.x) * 180) / Math.PI; if (rotd >= 89.5 || rotd < -90.5) rotd += 180;
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

/**
 * Cables sheet from the RAM Concept tendons, one direction (`set`) per sheet.
 *   variant 'shop'   - the fabrication sheet: strands, live ends, jacking forces and elongations in the schedule, and the
 *                      chair heights written along every tendon at `pt.chairSpacing` (1 m); no tendon sections
 *   variant 'design' - the design sheet: tendon paths and strand counts with the high / low points and their CGS
 *                      heights only; no elongations, no jacking forces, no stressing record
 */
// ------------------------------------------------------------------ office cable drawings (design 05/06, shop 07A/07B)
// The conventions of the office's cable shop-drawing program (Auto PT Suite, ShopOnly build): chair-height stations
// along every tendon, the odd spacing dimensioned, high / low points on their own layers with a circle on the point,
// live / dead anchor blocks, the five-cell tag on every tendon, anchor spacing dimensioned at the face, one schedule
// row per mark (tendons of one strand count and one profile share a mark), the chair / duct / quantity schedules and
// the seven general notes.
const CAB = {
  step: 1000, minStation: 500, roundH: 5, chairDrop: 10, anchorSet: 6, dimSkip: [980, 1020],
  txt: 2.0, dimTxt: 1.6, tick: 0.8, tagClear: 250, tagXs: [800, 1131.3, 1773.2, 2608.5, 3387.5, 3979], tagLead: 750, tagHalf: 175,
  smallDuctMax: 3, ductSmall: '20x50', ductLarge: '20x70', anchorAllowance: 300,
};
const CAB_NOTES = [
  'ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE.',
  'FIGURES ALONG EACH TENDON ARE CHAIR HEIGHTS TO THE UNDERSIDE OF THE DUCT, MEASURED FROM THE SOFFIT OF THE SLAB (OR OF THE DROP PANEL WHERE THE POINT FALLS INSIDE ONE).',
  'STATIONS ARE AT 1000 mm CENTRES; THE ODD SPACING BEFORE A HIGH OR LOW POINT IS DIMENSIONED.',
  'HIGH POINTS AND LOW POINTS ARE ON THEIR OWN LAYERS AND COLOURS.',
  'EXTENSIONS ARE TAKEN FROM THE ANALYSIS. ONE LIVE END: THE CALCULATED VALUE LESS 6 mm SEATING. TWO LIVE ENDS: THE SUM OF BOTH ENDS WITH NO DEDUCTION.',
  'ANCHOR NUMBERS ARE FILLED ON SITE AGAINST THE STRESSING RECORD.',
  'DO NOT CUT STRAND TAILS BEFORE THE STRESSING RECORD IS APPROVED.',
];
const STRAND_DIA = { 98.7: '12.7', 140: '15.24', 150: '15.7', 100: '12.9' };
const PT_TEXT = { style: 'PT-PROFILE', widthFactor: 0.75 };

/** The point and unit tangent at `s` along a tendon. */
function alongTendon(t, s) {
  const pts = t.pts;
  let acc = 0;
  for (let i = 0; i + 1 < pts.length; i++) {
    const L = dist(pts[i], pts[i + 1]);
    if (s <= acc + L + 1e-6 || i + 2 >= pts.length) {
      const u = L > 0 ? { x: (pts[i + 1].x - pts[i].x) / L, y: (pts[i + 1].y - pts[i].y) / L } : { x: 1, y: 0 };
      const d = Math.max(0, Math.min(L, s - acc));
      return { p: { x: pts[i].x + u.x * d, y: pts[i].y + u.y * d }, u };
    }
    acc += L;
  }
  return { p: pts[pts.length - 1], u: { x: 1, y: 0 } };
}

/**
 * The chair-height stations of a tendon (office rule): every profile node, and exactly 1000 between them from each
 * node on, the remainder before the next node kept as the one odd spacing (merged into the last metre when it is
 * under 500). Height = CGS above the soffit less the chair drop (the chair carries the underside of the duct),
 * rounded to 5 and never above the slab; `cgs` gives the profile height itself (design sheets).
 */
function cableStations(t, thicknessAt, { chairDrop = CAB.chairDrop, cgs = false } = {}) {
  if (!t.heights) return [];
  const st = [0];
  for (let i = 1; i < t.pts.length; i++) st.push(st[i - 1] + dist(t.pts[i - 1], t.pts[i]));
  const ext = new Map(RC.tendonExtremes(t).map((e) => [e.i, e.kind]));
  const stations = [0];
  for (let i = 0; i + 1 < st.length; i++) {
    const a = st[i], b = st[i + 1], L = b - a;
    if (L <= 1e-9) continue;
    let n = Math.floor(L / CAB.step + 1e-9);
    const tail = L - n * CAB.step;
    if (n >= 1 && tail < CAB.minStation - 1e-9) n--;
    for (let k = 1; k <= n; k++) stations.push(a + k * CAB.step);
    stations.push(b);
  }
  const out = [];
  const seen = new Set();
  for (const s of stations) {
    const key = Math.round(s);
    if (seen.has(key)) continue;
    seen.add(key);
    const { p, u } = alongTendon(t, s);
    let iNode = -1;
    for (let i = 0; i < st.length; i++) if (Math.abs(st[i] - s) < 1e-3) { iNode = i; break; }
    // (an anchor is an anchor, never a high / low point: the office profile flags come from the control points between)
    const kind = iNode < 0 ? '' : iNode === 0 || iNode === st.length - 1 ? 'end' : ext.get(iNode) === 'H' ? 'high' : ext.get(iNode) === 'L' ? 'low' : '';
    const th = (iNode >= 0 && t.thks?.[iNode]) || thicknessAt(p);
    const cg = RC.tendonHeightAt(t, s);
    if (cg == null) continue;
    let h = cgs ? cg : cg - chairDrop;
    h = Math.max(0, Math.min(h, th));
    h = Math.round(h / CAB.roundH) * CAB.roundH;
    out.push({ s, p, u, h, kind, i: iNode, th });
  }
  return out;
}

/** The written extension (office rule): two live ends = the sum of both RAM figures; one = RAM's figure less 6 mm seating. */
function cableExtension(t) {
  const es = (t.elongations || []).filter((v) => v != null);
  if (es.length >= 2) return Math.round(es.reduce((a, b) => a + b, 0));
  if (es.length === 1) return Math.max(0, Math.round(es[0] - CAB.anchorSet));
  return t.elongation != null ? Math.round(t.elongation) : null;
}

/** The office anchor and tag blocks (geometry of the office template, in model mm at 1:100, scaled by G to the sheet scale). */
function cableBlocks(root, G) {
  const P = (pts) => pts.map(([x, y]) => ({ x: x * G, y: y * G }));
  if (!root.blocks.has('LiveEnd')) {
    const b = root.block('LiveEnd');
    b.pline(P([[90, -110], [0, -125], [0, 125], [90, 110]]), { layer: '0' });
    b.pline(P([[300, 55], [300, -55], [310, -55], [310, 55]]), { layer: '0', closed: true });
    b.pline(P([[90, -126], [107, -125], [109, -111], [109, 111], [107, 125], [90, 126]]), { layer: '0' });
    b.pline(P([[310, 35], [800, 35], [800, -35], [310, -35]]), { layer: '0', closed: true });
    b.pline(P([[195, -91], [205, -91], [205, 91], [195, 91]]), { layer: '0', closed: true });
    b.circle(149 * G, 0, 12.5 * G, { layer: '0' });
  }
  if (!root.blocks.has('DeadEnd')) {
    const b = root.block('DeadEnd');
    b.pline(P([[70, 35], [500, 35], [500, -35], [70, -35]]), { layer: '0', closed: true });
    b.pline(P([[0, -125], [0, 125], [70, 125], [70, -125]]), { layer: '0', closed: true });
  }
}

/**
 * The cable sheet of one tendon direction from the RAM Concept model, in the office convention.
 *   variant 'design' (sheets 05 / 06): tendons, anchors, tags without extension, the high / low points with the
 *     CGS height of the profile - no chairs, no extension;
 *   variant 'shop' (07A / 07B): the chair heights at every station, the odd spacings dimensioned, extensions on
 *     the tags and in the schedule, chair / duct / quantity schedules and the stressing record.
 */
export function ramCablesSheet(model, level, meta, { set = 'latitude', variant = 'shop' } = {}) {
  return (sheet, [pl]) => {
    const S = sheet.S, G = S / 100; // paper mm -> model mm; block geometry drawn for 1:100 scales with the sheet
    const pt = level.ram.pt;
    const design = variant === 'design';
    const fam = set === 'latitude' ? 'A' : 'B';
    const TH = CAB.txt * S, TICK = CAB.tick * S * 0.6;
    const root = sheet.blk.root;
    root.textStyleDef('PT-PROFILE', { font: 'romans.shx', widthFactor: 0.75 });
    cableBlocks(root, G);
    const dimStation = { txt: CAB.dimTxt * S, tsz: CAB.tick * S, asz: CAB.tick * S, exe: 1.2 * S, exo: 0.8 * S, gap: 0.8 * S, tad: 1, clrt: 2, clrd: 256, clre: 256, dec: 0, txsty: 'PT-PROFILE' };
    const dimSpacing = { ...dimStation, txt: CAB.dimTxt * 1.25 * S };
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, regionLabels: false, ubarRegions: false });

    const outline = level.outline || [];
    const openings = (level.openings || []).map((o) => R.regionPolygon(o)).filter((p) => p && p.length >= 3);
    const zones = (level.thickZones || []).filter((z) => z.polygon && z.thickness);
    const thicknessAt = thicknessFn(level);
    const outsideSlab = (p) => (outline.length >= 3 && !pointInPolygon(p, outline)) || openings.some((o) => pointInPolygon(p, o));
    const tendons = level.ram.tendons.filter((t) => t.spanSet === set);
    // every height written is the chair height: RAM's CGS height less the chair drop (10 mm), rounded to 5 - on the design sheets too
    const samplesOf = new Map(tendons.map((t) => [t, cableStations(t, thicknessAt, { cgs: false })]));
    // marks: tendons of one strand count and one profile (high / low / end stations within 100 mm and 5 mm) share one
    // (always from the chair stations, so the design and shop sheets and the crossings plan name a tendon alike)
    const markOf = cableMarksOf(tendons, fam, thicknessAt);
    const seqOf = (t) => Number((t.id || '').split('-')[1]) || tendons.indexOf(t) + 1;
    const ang = (u) => (Math.atan2(u.y, u.x) * 180) / Math.PI;

    let stationCount = 0, dimCount = 0, skipped = 0, noProfile = 0;
    const anchors = [];
    const chairCounts = new Map();
    const rowsByMark = new Map();
    const rows = [];
    for (const t of tendons) {
      const smp = samplesOf.get(t);
      if (!t.heights) noProfile++;
      pl.pline(t.pts, { layer: `Tendons-${fam}` });
      // the stations: a tick across the tendon, the height parallel to it; high / low points bigger, on their own
      // layers, with the circle on the point itself (design sheets: the high / low points only, as the profile)
      const shown = design ? smp.filter((x) => x.kind === 'high' || x.kind === 'low') : smp;
      shown.forEach((x) => {
        const k = smp.indexOf(x);
        const a = smp[Math.max(k - 1, 0)].p, b = smp[Math.min(k + 1, smp.length - 1)].p;
        const L = dist(a, b);
        const n = L > 1e-9 ? { x: -(b.y - a.y) / L, y: (b.x - a.x) / L } : { x: 0, y: 1 };
        const suffix = x.kind === 'high' ? '-HIGH' : x.kind === 'low' ? '-LOW' : '';
        const big = suffix ? 1.35 : 1;
        pl.line({ x: x.p.x - n.x * TICK * big, y: x.p.y - n.y * TICK * big }, { x: x.p.x + n.x * TICK * big, y: x.p.y + n.y * TICK * big }, { layer: `Hline-Profile-${fam}${suffix}` });
        if (suffix) pl.circle(x.p, TICK * 0.55, { layer: `PT-HighLow-${fam}` });
        const off = TH * 0.35 * big;
        pl.text({ x: x.p.x + n.x * off, y: x.p.y + n.y * off }, `${x.h}`, { layer: `Text-Profile-${fam}${suffix}`, h: CAB.txt, rot: ang({ x: n.y, y: -n.x }), align: 'C', valign: 'B', ...PT_TEXT });
        stationCount++;
        if (!design) chairCounts.set(x.h, (chairCounts.get(x.h) || 0) + 1);
      });
      // the odd spacings: a dimension along the tendon between consecutive stations, except the regular metre
      if (!design) {
        for (let k = 0; k + 1 < smp.length; k++) {
          const a = smp[k].p, b = smp[k + 1].p;
          const gap = smp[k + 1].s - smp[k].s;
          if (gap >= CAB.dimSkip[0] && gap <= CAB.dimSkip[1]) { skipped++; continue; }
          const L = dist(a, b);
          if (L < 1) continue;
          const n = { x: -(b.y - a.y) / L, y: (b.x - a.x) / L };
          const m = { x: (a.x + b.x) / 2 - n.x * TH * 2.5, y: (a.y + b.y) / 2 - n.y * TH * 2.5 };
          pl.dimension(a, b, m, { style: 'PT-DIM-STATION', styleDef: dimStation, layer: `Dimensions-Profile-${fam}` });
          dimCount++;
        }
      }
      // the anchors: the live-end block where a jack sits in the model, the dead-end block elsewhere
      const p0 = t.pts[0], p1 = t.pts[1] || p0, q0 = t.pts[t.pts.length - 1], q1 = t.pts[t.pts.length - 2] || q0;
      const out0 = ang({ x: p0.x - p1.x, y: p0.y - p1.y }), out1 = ang({ x: q0.x - q1.x, y: q0.y - q1.y });
      const cut = t.cut || [false, false];
      for (const [p, a, live, isCut] of [[p0, out0, t.live[0], cut[0]], [q0, out1, t.live[1], cut[1]]]) {
        const Q = pl.P(p);
        if (isCut) {
          // the tendon continues on the next part / body: a break mark and CONT. instead of an anchor
          const ux = Math.cos((a * Math.PI) / 180), uy = Math.sin((a * Math.PI) / 180);
          pl.line({ x: p.x - uy * TICK * 1.6, y: p.y + ux * TICK * 1.6 }, { x: p.x + uy * TICK * 1.6, y: p.y - ux * TICK * 1.6 }, { layer: `Details-${fam}` });
          pl.text({ x: p.x + ux * TH * 0.8, y: p.y + uy * TH * 0.8 }, 'CONT.', { layer: `Text-Profile-${fam}`, h: CAB.txt, rot: ang({ x: ux, y: uy }), align: 'C', valign: 'B', ...PT_TEXT });
          continue;
        }
        sheet.blk.insert(live ? 'LiveEnd' : 'DeadEnd', Q.x, Q.y, { rot: a + 180, layer: `Details-${fam}` });
      }
      // the tag on the tendon line, out of its live end (the start when both or neither are live): five cells on a
      // leader; where the box would sit in the slab it steps 250 aside towards the outside
      const ext = design ? null : cableExtension(t);
      const lengthM = (t.length / 1000).toFixed(1);
      const [tagAt, tagAng] = cut[0] && !cut[1] ? [q0, out1] : cut[1] && !cut[0] ? [p0, out0] : t.live[0] || !t.live[1] ? [p0, out0] : [q0, out1];
      const u = { x: Math.cos((tagAng * Math.PI) / 180), y: Math.sin((tagAng * Math.PI) / 180) }, n = { x: -u.y, y: u.x };
      const xs = CAB.tagXs.map((v) => v * G);
      let ins = tagAt;
      const centre = { x: tagAt.x + u.x * (xs[0] + xs[5]) / 2, y: tagAt.y + u.y * (xs[0] + xs[5]) / 2 };
      if (!outsideSlab(centre)) {
        const probe = 3000;
        const outPos = outsideSlab({ x: centre.x + n.x * probe, y: centre.y + n.y * probe }), outNeg = outsideSlab({ x: centre.x - n.x * probe, y: centre.y - n.y * probe });
        const sign = outPos && !outNeg ? 1 : outNeg && !outPos ? -1 : 1;
        ins = { x: tagAt.x + n.x * CAB.tagClear * G * sign, y: tagAt.y + n.y * CAB.tagClear * G * sign };
        pl.line(tagAt, ins, { layer: `Details-${fam}` });
      }
      const at = (x, y) => ({ x: ins.x + u.x * x + n.x * y, y: ins.y + u.y * x + n.y * y });
      const hh = CAB.tagHalf * G;
      pl.line(at(0, 0), at(CAB.tagLead * G, 0), { layer: `Details-${fam}` });
      pl.line(at(xs[0], -hh), at(xs[5], -hh), { layer: `Details-${fam}` });
      pl.line(at(xs[0], hh), at(xs[5], hh), { layer: `Details-${fam}` });
      for (const x of xs) pl.line(at(x, -hh), at(x, hh), { layer: `Details-${fam}` });
      const cells = [String(t.strands), ext == null ? '' : String(ext), lengthM, markOf.get(t), String(seqOf(t))];
      cells.forEach((v, i) => { if (v) pl.text(at((xs[i] + xs[i + 1]) / 2, -100 * G), v, { layer: `Details-${fam}`, h: CAB.txt, rot: tagAng, align: 'C', valign: 'B', color: 3, ...PT_TEXT }); });
      if (!cut[0]) anchors.push({ p: p0, live: t.live[0] });
      if (!cut[1]) anchors.push({ p: q0, live: t.live[1] });
      // one schedule row per mark
      const mark = markOf.get(t);
      let row = rowsByMark.get(mark);
      if (!row) {
        row = { mark, qty: 0, seqs: [], strands: t.strands, length: lengthM, live: t.live.filter(Boolean).length, elong: ext == null ? '' : ext, chairs: 0, type: '', guts: '', jack: '', _t: t };
        rowsByMark.set(mark, row); rows.push(row);
      }
      row.qty++; row.seqs.push(seqOf(t)); row.chairs += smp.length;
    }
    // the strand line of the schedule: type, breaking load and the jacking force per strand
    const area = pt.strandArea || 140, fpu = pt.fpu || 1860;
    const jackRatio = (tendons[0]?.jackStress || pt.jackStress || 0.78 * fpu) / fpu;
    const dia = STRAND_DIA[Math.round(area * 10) / 10] || STRAND_DIA[Math.round(area)] || '15.24';
    for (const r of rows) {
      const chunks = []; const seqs = [...r.seqs].sort((a, b) => a - b);
      for (let i = 0; i < seqs.length; i += 6) chunks.push(seqs.slice(i, i + 6).join(','));
      r.anchors = chunks.join(' / ');
      r.type = dia; r.guts = Math.round((area * fpu) / 1000); r.jack = Math.round((area * jackRatio * fpu) / 1000);
      delete r._t;
    }
    // the anchor spacing at every face line, dimensioned perpendicular to the tendons, outside the slab
    // (the tendons' own direction on the sheet, not the family name: a plan turned 90° runs the latitude set vertically)
    const runsAlongX = tendons.reduce((sum, t) => { const a = t.pts[0], b = t.pts[t.pts.length - 1]; return sum + (Math.abs(b.x - a.x) >= Math.abs(b.y - a.y) ? 1 : -1); }, 0) >= 0;
    const axis = runsAlongX ? 'y' : 'x', across = runsAlongX ? 'x' : 'y';
    const groups = new Map();
    for (const a of anchors) { const key = Math.round(a.p[across] / 2000); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(a.p); }
    for (const g of groups.values()) {
      if (g.length < 2) continue;
      g.sort((p, q) => p[axis] - q[axis]);
      for (let i = 0; i + 1 < g.length; i++) {
        const p = g[i], q = g[i + 1];
        if (Math.abs(q[axis] - p[axis]) < 200) continue;
        const mid = { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
        const perp = runsAlongX ? { x: 1, y: 0 } : { x: 0, y: 1 };
        // the dimension line halfway between the anchors and the tag blocks (the tag starts `tagXs[0]` out of the
        // anchor): it never sits over the tags
        const d = (CAB.tagXs[0] * G) / 2;
        const plus = { x: mid.x + perp.x * d, y: mid.y + perp.y * d }, minus = { x: mid.x - perp.x * d, y: mid.y - perp.y * d };
        const dl = outsideSlab(plus) && !outsideSlab(minus) ? plus : minus;
        pl.dimension(p, q, dl, { style: 'PT-DIM-SPACING', styleDef: dimSpacing, angle: runsAlongX ? 90 : 0, layer: `Dimensions-Sec-${fam}` });
      }
    }

    // ---- schedule and details
    const dirTitle = fam === 'A' ? 'DIRECTION A (LATITUDE)' : 'DIRECTION B (LONGITUDE)';
    const cols = [
      { key: 'mark', title: 'MARK\nNO.', w: 16 }, { key: 'qty', title: 'QTY', w: 10 }, { key: 'anchors', title: 'ANCHOR NO.\n(SEE NOTE 6)', w: 30, align: 'L' }, { key: 'strands', title: 'NO. OF\nSTRANDS', w: 14 },
      { key: 'length', title: 'LENGTH\n(M)', w: 16 }, { key: 'live', title: 'NO. OF\nLIVE ENDS', w: 16 },
      ...(design ? [] : [{ key: 'elong', title: 'EXTENSION\n(MM)', w: 18 }]),
      { key: 'type', title: 'STRAND\nTYPE', w: 16 }, { key: 'guts', title: 'GUTS\n(KN)', w: 16 },
      ...(design ? [] : [{ key: 'jack', title: 'JACKING FORCE\nPER STRAND (KN)', w: 33 }]),
    ];
    const W = cols.reduce((s, c) => s + c.w, 0);
    if (design) cols[2].w += 185 - W; else if (W !== 185) cols[2].w += 185 - W;
    const strands = tendons.reduce((s, t) => s + t.strands, 0);
    const liveEnds = anchors.filter((a) => a.live).length;
    const strandM = tendons.reduce((s, t) => s + (t.length / 1000) * t.strands, 0);
    const kgPerM = (area * 7850) / 1e6;
    let detailsUsed = 2;
    if (!design) {
      // 1: chair height schedule (the dead-end chairs, 300 wide, on their own rows)
      const d1 = sheet.detailBox(0, 'CHAIR HEIGHT SCHEDULE', '');
      const base = level.thickness;
      const dead = new Map();
      for (const t of tendons) for (const [p, live, isCut] of [[t.pts[0], t.live[0], t.cut?.[0]], [t.pts[t.pts.length - 1], t.live[1], t.cut?.[1]]]) {
        if (live || isCut) continue;
        const th = thicknessAt(p);
        const h = Math.round(Math.max(0, th > base + 1e-6 ? th - base / 2 - 10 : base / 2 - 10));
        dead.set(h, (dead.get(h) || 0) + 1);
      }
      const chairRows = [...chairCounts.entries()].sort((a, b) => a[0] - b[0]).map(([h, n]) => ({ h: String(h), n }));
      for (const [h, n] of [...dead.entries()].sort((a, b) => a[0] - b[0])) chairRows.push({ h: `${h} DEAD END`, n });
      const chairCols = [{ key: 'h', title: 'HEIGHT\n(mm)', w: 26 }, { key: 'n', title: 'QTY', w: 14 }];
      const perCol = Math.max(1, Math.floor((d1.h - 18) / 3.2));
      let left = chairRows, cx0 = d1.x + 3;
      while (left.length && cx0 + 40 <= d1.x + d1.w) {
        const res = sheet.table(cx0, d1.y + d1.h - 10, chairCols, left, { maxRows: perCol, headH: 6, rowH: 3.2, h: 1.3 });
        left = res.leftover; cx0 += 44;
      }
      sheet.pp.text(d1.x + 3, d1.y + 2, `DEAD-END CHAIRS 300 mm WIDE (SLAB / 2 - 10, OR DROP - SLAB / 2 - 10). CHAIR SET ${CAB.chairDrop} mm BELOW THE TENDON CENTRELINE.`, { layer: 'NOTES', h: 1.4 });
      // 2: duct schedule and bill of quantities
      const d2 = sheet.detailBox(1, 'DUCT SCHEDULE AND BILL OF QUANTITIES', '');
      const ductLen = (t) => Math.max(0, t.length / 1000 - (t.live.filter(Boolean).length === 1 ? 1 : 0));
      const small = tendons.filter((t) => t.strands <= CAB.smallDuctMax), large = tendons.filter((t) => t.strands > CAB.smallDuctMax);
      const ductCols = [{ key: 'a', title: 'DUCT SIZE\n(mm)', w: 24 }, { key: 'b', title: 'STRANDS', w: 20 }, { key: 'c', title: 'TENDONS', w: 18 }, { key: 'd', title: 'LENGTH\n(m)', w: 22 }];
      const r1 = sheet.table(d2.x + 3, d2.y + d2.h - 10, ductCols, [
        { a: CAB.ductSmall, b: `UP TO ${CAB.smallDuctMax}`, c: small.length, d: Math.round(small.reduce((s, t) => s + ductLen(t), 0)) },
        { a: CAB.ductLarge, b: `OVER ${CAB.smallDuctMax}`, c: large.length, d: Math.round(large.reduce((s, t) => s + ductLen(t), 0)) },
      ], { headH: 6, rowH: 3.5, h: 1.4 });
      const netArea = Math.abs(polygonArea(outline)) / 1e6 - openings.reduce((s, o) => s + Math.abs(polygonArea(o)) / 1e6, 0);
      const cutting = tendons.reduce((s, t) => s + t.strands * (t.length / 1000 + (CAB.anchorAllowance / 1000) * Math.max(1, t.live.filter(Boolean).length)), 0);
      const kg = cutting * kgPerM;
      const boqCols = [{ key: 'a', title: 'ITEM', w: 56, align: 'L' }, { key: 'b', title: 'VALUE', w: 28, align: 'R' }];
      sheet.table(d2.x + 3, r1.y - 4, boqCols, [
        { a: 'TENDONS', b: tendons.length }, { a: 'STRANDS', b: strands }, { a: 'STRAND LENGTH (CUT, 300 PER ANCHOR)', b: `${Math.round(cutting)} m` },
        { a: 'NET SLAB AREA (OPENINGS DEDUCTED)', b: `${netArea.toFixed(1)} m2` }, { a: 'STRAND WEIGHT', b: `${Math.round(kg)} kg` },
        { a: 'RATE', b: `${netArea ? (kg / netArea).toFixed(2) : '-'} kg/m2` }, { a: 'RATE', b: `${netArea ? (cutting / netArea).toFixed(2) : '-'} strand-m/m2` },
      ], { headH: 5, rowH: 3.2, h: 1.3 });
      // 3: stressing record (unless the schedule needs the box for its continuation)
      const maxRows = Math.floor((sheet.L.schedule.h - 23) / 3);
      if (rows.length > maxRows) { detailsUsed = 2; } else {
      const d3 = sheet.detailBox(2, 'STRESSING RECORD', '');
      const recCols = [{ key: 'a', title: 'TENDON', w: 22 }, { key: 'm', title: 'MARK', w: 16 }, { key: 'b', title: 'DATE', w: 24 }, { key: 'c', title: 'GAUGE\n(bar)', w: 22 }, { key: 'd', title: 'EXT.\nCALC.', w: 22 }, { key: 'e', title: 'EXT.\nMEAS.', w: 22 }, { key: 'f', title: '%', w: 14 }, { key: 'g', title: 'SIGN', w: Math.max(20, d3.w - 6 - 142) }];
      sheet.table(d3.x + 3, d3.y + d3.h - 10, recCols, tendons.map((t) => ({ a: t.id, m: markOf.get(t), d: cableExtension(t) ?? '' })), { maxRows: Math.floor((d3.h - 18) / 3.2), headH: 6, rowH: 3.2, h: 1.3 });
      detailsUsed = 3;
      }
    } else {
      const d1 = sheet.detailBox(0, 'PROFILE POINTS', '');
      const pp = sheet.pp;
      [`THE FIGURE AT EVERY HIGH / LOW POINT (THE CIRCLE MARKS THE POINT ITSELF) IS THE CHAIR HEIGHT IN mm: THE TENDON CGS HEIGHT ABOVE THE SLAB SOFFIT AS DESIGNED IN RAM CONCEPT LESS ${CAB.chairDrop} mm, ROUNDED TO ${CAB.roundH}. THE CHAIR HEIGHTS AT EVERY STATION BETWEEN THEM ARE GIVEN ON THE SHOP DRAWINGS.`,
        'DESIGN DRAWING: STRAND COUNTS, PATHS, STRESSING ENDS AND PROFILE POINTS ONLY. EXTENSIONS, JACKING FORCES AND CHAIRS ARE ON THE SHOP DRAWINGS.'].forEach((h, i) => pp.mtext(d1.x + 4, d1.y + d1.h - 12 - i * 14, h, { layer: 'NOTES', h: 1.7, width: d1.w - 8 }));
      const d2 = sheet.detailBox(1, 'TENDON SYMBOLS', 'N.T.S.');
      const det = D.tendonLegend();
      det.draw(sheet.detailPen(d2, 12, det.bbox));
    }
    const cover = model.spec.cover || 25;
    const drop = zones.length ? Math.max(...zones.map((z) => z.thickness)) : null;
    const notes = design ? [
      commonNotes(model, level)[0],
      `PT SYSTEM: ${pt.system || ''} - ${pt.ductType || 'bonded'} FLAT DUCT ${pt.ductWidth ? `${pt.ductWidth} x ${pt.ductHeight} mm` : ''}, ${pt.strandsPerDuct || ''} STRANDS PER DUCT MAX. STRAND ${dia} mm, Aps = ${area} mm², fpu = ${Math.round(fpu)} MPa.`,
      `TENDON PATHS, STRAND COUNTS, STRESSING ENDS AND THE HIGH / LOW POINTS OF THE PROFILE ARE READ FROM THE RAM CONCEPT MODEL (${stationCount} PROFILE POINTS ON THIS SHEET${noProfile ? `; ${noProfile} TENDONS CARRY NO PROFILE IN THE MODEL` : ''}). THE TAG ON EVERY TENDON READS STRANDS / LENGTH / MARK / No.; TENDONS OF ONE STRAND COUNT AND ONE PROFILE SHARE A MARK. THE OTHER DIRECTION IS ON ITS OWN SHEET.`,
      'DESIGN DRAWING - NOT FOR FABRICATION. EXTENSIONS, JACKING FORCES AND CHAIR HEIGHTS ARE GIVEN ON THE SHOP DRAWINGS.',
    ] : [
      ...CAB_NOTES,
      `SLAB ${level.thickness}${drop ? ` / DROP ${drop}` : ''} · COVER TOP ${cover} BOTTOM ${cover} · CHAIR SET ${CAB.chairDrop} mm BELOW THE TENDON CENTRELINE. STRAND ${dia} mm, Aps = ${area} mm², fpu = ${Math.round(fpu)} MPa, JACKING ${Math.round(jackRatio * 100)} % fpu. THE TAG ON EVERY TENDON READS STRANDS / EXTENSION / LENGTH / MARK / No. THE OTHER DIRECTION IS ON ITS OWN SHEET.${noProfile ? ` ${noProfile} TENDONS CARRY NO PROFILE IN THE MODEL: THEIR CHAIRS ARE TO BE SET FROM THE RAM PROFILE REPORT.` : ''}`,
    ];
    return {
      rows, cols, rowH: 3, scheduleTitle: `TENDON SCHEDULE (${fam})${design ? ' - DESIGN' : ''}`, detailsUsed,
      totals: `${tendons.length} TENDONS · ${strands} STRANDS · ${Math.round(strandM)} m STRAND · ${liveEnds} LIVE ENDS${design ? '' : ` · ${stationCount} CHAIRS`}`,
      weight: Math.round(strandM * kgPerM),
      planTitles: [design ? `PT TENDON LAYOUT - ${dirTitle} - DESIGN (HIGH / LOW POINTS)` : `CHAIR HEIGHTS - ${dirTitle}`],
      general: notes,
      assumptions: levelAssumptions(model, level).slice(0, 3),
      legend: [
        [`Tendons-${fam}`, `TENDON, ${dirTitle}`, 'thick'],
        [`Text-Profile-${fam}-HIGH`, `HIGH POINT CHAIR HEIGHT (CGS - ${CAB.chairDrop})`, 'line'],
        [`Text-Profile-${fam}-LOW`, `LOW POINT CHAIR HEIGHT (CGS - ${CAB.chairDrop})`, 'line'],
        ...(design ? [] : [[`Text-Profile-${fam}`, 'INTERMEDIATE CHAIR HEIGHT (1000 STATIONS)', 'line'], [`Dimensions-Profile-${fam}`, 'ODD STATION SPACING', 'line']]),
        [`Details-${fam}`, 'LIVE END (BLOCK) / DEAD END (BLOCK) / TENDON TAG', 'line'],
        [`Dimensions-Sec-${fam}`, 'ANCHOR SPACING AT THE FACE', 'line'],
        ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL', 'WALL BELOW', 'thick'],
      ],
      checks: skipped ? [`${skipped} regular 1000 mm station spacings left undimensioned; ${dimCount} odd spacings dimensioned.`] : [],
    };
  };
}

/** The marks of one direction: tendons of one strand count and one profile (chair stations) share a mark; keyed by tendon. */
function cableMarksOf(tendons, fam, thicknessAt) {
  const sigToMark = new Map();
  const markOf = new Map();
  for (const t of tendons) {
    const smp = cableStations(t, thicknessAt);
    const sig = `${t.strands}|${smp.filter((x) => x.kind).map((x) => `${x.kind}${Math.round(x.s / 100)}:${x.h}`).join(',')}|${smp.length ? '' : Math.round(t.length / 100)}`;
    let mark = sigToMark.get(sig);
    if (!mark) { mark = `${fam}.${String(sigToMark.size + 1).padStart(2, '0')}`; sigToMark.set(sig, mark); }
    markOf.set(t, mark);
  }
  return markOf;
}

/** Local thickness at a plan point: the thickened zone it falls in, else the slab. */
function thicknessFn(level) {
  const zones = (level.thickZones || []).filter((z) => z.polygon && z.thickness);
  return (p) => { for (const z of zones) if (pointInPolygon(p, z.polygon)) return z.thickness; return level.thickness; };
}

// ------------------------------------------------------------------ tendon crossings: which tendon passes over
const CROSS = { duct: 20, tol: 10, endClear: 50, gapPaper: 1.6 };

function segCross(a0, a1, b0, b1) {
  const dx1 = a1.x - a0.x, dy1 = a1.y - a0.y, dx2 = b1.x - b0.x, dy2 = b1.y - b0.y;
  const den = dx1 * dy2 - dy1 * dx2;
  if (Math.abs(den) < 1e-12) return null;
  const ex = b0.x - a0.x, ey = b0.y - a0.y;
  let ta = (ex * dy2 - ey * dx2) / den, tb = (ex * dy1 - ey * dx1) / den;
  if (ta < -1e-9 || ta > 1 + 1e-9 || tb < -1e-9 || tb > 1 + 1e-9) return null;
  ta = Math.max(0, Math.min(1, ta)); tb = Math.max(0, Math.min(1, tb));
  return { x: a0.x + ta * dx1, y: a0.y + ta * dy1, ta, tb };
}

/**
 * Every crossing of two tendons in plan (office rule): where it is, the station on each tendon, each tendon's depth
 * from the top there (from the same profile the chair heights come from), the gap and which one passes over.
 * Clash = gap under `tol` (10 mm: the two ducts sit at one level); tight = under the duct height (20) but no clash.
 * An end standing on another tendon (within `endClear`) is not a crossing.
 */
export function tendonCrossings(level, thicknessAt = thicknessFn(level)) {
  const tendons = (level.ram?.tendons || []).filter((t) => t.heights && t.pts.length >= 2);
  const geo = tendons.map((t) => { const st = [0]; for (let i = 1; i < t.pts.length; i++) st.push(st[i - 1] + dist(t.pts[i - 1], t.pts[i])); return { t, st, total: st[st.length - 1], bb: bbox(t.pts) }; });
  const out = [];
  for (let i = 0; i < geo.length; i++) {
    const gi = geo[i];
    for (let j = i + 1; j < geo.length; j++) {
      const gj = geo[j];
      if (gi.bb.maxX < gj.bb.minX || gj.bb.maxX < gi.bb.minX || gi.bb.maxY < gj.bb.minY || gj.bb.maxY < gi.bb.minY) continue;
      const seen = new Set();
      for (let a = 0; a + 1 < gi.t.pts.length; a++) for (let b = 0; b + 1 < gj.t.pts.length; b++) {
        const hit = segCross(gi.t.pts[a], gi.t.pts[a + 1], gj.t.pts[b], gj.t.pts[b + 1]);
        if (!hit) continue;
        const sa = gi.st[a] + hit.ta * (gi.st[a + 1] - gi.st[a]), sb = gj.st[b] + hit.tb * (gj.st[b + 1] - gj.st[b]);
        if (sa < CROSS.endClear || sa > gi.total - CROSS.endClear || sb < CROSS.endClear || sb > gj.total - CROSS.endClear) continue;
        const key = `${Math.round(hit.x)},${Math.round(hit.y)}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const pt = { x: hit.x, y: hit.y };
        const th = thicknessAt(pt);
        const ha = RC.tendonHeightAt(gi.t, sa), hb = RC.tendonHeightAt(gj.t, sb);
        if (ha == null || hb == null) continue;
        const da = Math.round(th - ha), db = Math.round(th - hb);
        const gap = Math.abs(da - db);
        const over = da < db ? 'a' : db < da ? 'b' : '=';
        out.push({ pt, a: gi.t, b: gj.t, sa, sb, da, db, gap, over, clash: gap < CROSS.tol, tight: gap >= CROSS.tol && gap < CROSS.duct });
      }
    }
  }
  return out;
}

/** The tendon's polyline with a gap of `half` each side of every station in `cuts` taken out. */
function cutTendon(t, cuts, half) {
  const st = [0];
  for (let i = 1; i < t.pts.length; i++) st.push(st[i - 1] + dist(t.pts[i - 1], t.pts[i]));
  const total = st[st.length - 1];
  const gaps = [];
  for (const s of [...cuts].sort((p, q) => p - q)) {
    const a = Math.max(0, s - half), b = Math.min(total, s + half);
    if (gaps.length && a <= gaps[gaps.length - 1][1]) gaps[gaps.length - 1][1] = Math.max(gaps[gaps.length - 1][1], b); else gaps.push([a, b]);
  }
  const keep = [];
  let u = 0;
  for (const [a, b] of gaps) { if (a > u + 1e-6) keep.push([u, a]); u = b; }
  if (total > u + 1e-6) keep.push([u, total]);
  return keep.map(([u0, u1]) => [alongTendon(t, u0).p, ...t.pts.filter((_, k) => u0 + 1e-6 < st[k] && st[k] < u1 - 1e-6), alongTendon(t, u1).p]).filter((pc) => pc.length >= 2);
}

/**
 * The crossings sheet (office convention): both directions on one plan, the tendon that passes over drawn
 * continuous and the one under broken at the crossing, the gap in mm at every crossing with the family on top,
 * tight gaps in yellow, clashes in a red circle; the marks at both ends of every tendon; the clashes and tight
 * crossings listed in the schedule.
 */
export function ramCrossingsSheet(model, level, meta) {
  return (sheet, [pl]) => {
    const S = sheet.S, TH = CAB.txt * S;
    sheet.blk.root.textStyleDef('PT-PROFILE', { font: 'romans.shx', widthFactor: 0.75 });
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, regionLabels: false, ubarRegions: false });
    const thicknessAt = thicknessFn(level);
    const famOf = (t) => (t.spanSet === 'latitude' ? 'A' : 'B');
    const marks = new Map([...cableMarksOf(level.ram.tendons.filter((t) => t.spanSet === 'latitude'), 'A', thicknessAt), ...cableMarksOf(level.ram.tendons.filter((t) => t.spanSet !== 'latitude'), 'B', thicknessAt)]);
    const crossings = tendonCrossings(level, thicknessAt);
    const under = new Map();
    for (const c of crossings) {
      if (c.over === 'a') { if (!under.has(c.b)) under.set(c.b, []); under.get(c.b).push(c.sb); }
      else if (c.over === 'b') { if (!under.has(c.a)) under.set(c.a, []); under.get(c.a).push(c.sa); }
    }
    const half = Math.max(200, CROSS.gapPaper * S);
    const ang = (u) => (Math.atan2(u.y, u.x) * 180) / Math.PI;
    for (const t of level.ram.tendons) {
      if (t.pts.length < 2) continue;
      const layer = `PT-Cross-${famOf(t)}`;
      for (const pc of cutTendon(t, under.get(t) || [], half)) pl.pline(pc, { layer });
      for (const [end, nxt] of [[t.pts[0], t.pts[1]], [t.pts[t.pts.length - 1], t.pts[t.pts.length - 2]]]) {
        const L = dist(end, nxt) || 1, u = { x: (end.x - nxt.x) / L, y: (end.y - nxt.y) / L };
        pl.text({ x: end.x + u.x * TH * 2.2, y: end.y + u.y * TH * 2.2 }, marks.get(t) || t.id, { layer: 'PT-Cross-Mark', h: CAB.txt * 0.8, rot: ang(u), align: 'C', valign: 'M', ...PT_TEXT });
      }
    }
    for (const c of crossings) {
      if (c.clash) {
        pl.circle(c.pt, TH * 1.3, { layer: 'PT-Cross-Clash' });
        pl.text({ x: c.pt.x, y: c.pt.y + TH * 1.6 }, `CLASH ${c.gap}`, { layer: 'PT-Cross-Clash', h: CAB.txt * 0.8, align: 'C', valign: 'B', ...PT_TEXT });
      } else {
        const top = c.over === 'a' ? c.a : c.b;
        pl.text({ x: c.pt.x + TH * 0.45, y: c.pt.y + TH * 0.45 }, `${famOf(top)} ${c.gap}`, { layer: c.tight ? 'PT-Cross-Tight' : 'PT-Cross-Gap', h: CAB.txt * (c.tight ? 0.8 : 0.65), align: 'L', valign: 'B', ...PT_TEXT });
      }
    }
    const clashes = crossings.filter((c) => c.clash), tight = crossings.filter((c) => c.tight);
    const rowOf = (c) => ({ a: marks.get(c.a) || c.a.id, b: marks.get(c.b) || c.b.id, ida: c.a.id, idb: c.b.id, grid: gridRef(level, bbox([c.pt])), da: c.da, db: c.db, gap: c.gap, over: c.over === '=' ? '-' : famOf(c.over === 'a' ? c.a : c.b), status: c.clash ? 'CLASH' : 'TIGHT' });
    const rows = [...clashes, ...tight].map(rowOf);
    const cols = [
      { key: 'a', title: 'MARK\nA', w: 16 }, { key: 'ida', title: 'TENDON\nA', w: 18 }, { key: 'b', title: 'MARK\nB', w: 16 }, { key: 'idb', title: 'TENDON\nB', w: 18 }, { key: 'grid', title: 'GRID', w: 24 },
      { key: 'da', title: 'DEPTH A\n(mm)', w: 18 }, { key: 'db', title: 'DEPTH B\n(mm)', w: 18 }, { key: 'gap', title: 'GAP\n(mm)', w: 16 }, { key: 'over', title: 'OVER', w: 15 }, { key: 'status', title: 'STATUS', w: 26 },
    ];
    // 1: legend of the plan; 2: how to read it and the count per direction
    const d1 = sheet.detailBox(0, 'LEGEND', 'N.T.S.');
    const pp = sheet.pp;
    const legend = [
      ['PT-Cross-A', 'line', 'CONTINUOUS LINE = THE TENDON THAT PASSES OVER (A = DIRECTION A / LATITUDE, B = DIRECTION B / LONGITUDE)'],
      ['PT-Cross-B', 'broken', 'BROKEN LINE = THE TENDON THAT PASSES UNDER (BROKEN AT THE CROSSING)'],
      ['PT-Cross-Gap', 'circle', 'FIGURE AT THE CROSSING = THE DIRECTION ON TOP AND THE VERTICAL GAP BETWEEN THE TWO DUCT CENTRES, mm'],
      ['PT-Cross-Tight', 'circle', `YELLOW FIGURE = TIGHT: GAP UNDER THE DUCT HEIGHT (${CROSS.duct} mm) - THE LOWER DUCT BENDS A LITTLE`],
      ['PT-Cross-Clash', 'circle', `RED CIRCLE = CLASH: GAP UNDER ${CROSS.tol} mm, THE TWO DUCTS SIT AT THE SAME LEVEL - THE PROFILE IS TO BE CORRECTED`],
      ['PT-Cross-Mark', 'text', 'MARK AT BOTH ENDS OF EVERY TENDON (AS ON THE CABLE SHEETS)'],
    ];
    legend.forEach(([layer, kind, text], i) => {
      const y = d1.y + d1.h - 14 - i * 6, x = d1.x + 4;
      if (kind === 'line') pp.line(x, y + 0.6, x + 10, y + 0.6, { layer });
      else if (kind === 'broken') { pp.line(x, y + 0.6, x + 3.5, y + 0.6, { layer }); pp.line(x + 6.5, y + 0.6, x + 10, y + 0.6, { layer }); }
      else if (kind === 'circle') pp.circle(x + 5, y + 0.6, 1.2, { layer });
      else pp.text(x + 5, y, 'A.01', { layer, h: 1.6, align: 'C' });
      pp.mtext(x + 13, y + 2.2, text, { layer: 'NOTES', h: 1.5, width: d1.w - 20 });
    });
    const d2 = sheet.detailBox(1, 'CROSSINGS SUMMARY', '');
    const nA = level.ram.tendons.filter((t) => t.spanSet === 'latitude').length, nB = level.ram.tendons.length - nA;
    const overA = crossings.filter((c) => famOf(c.over === 'a' ? c.a : c.b) === 'A' && c.over !== '=').length;
    [`${nA} TENDONS IN DIRECTION A AND ${nB} IN DIRECTION B: ${crossings.length} CROSSINGS. DIRECTION A PASSES OVER AT ${overA}, DIRECTION B AT ${crossings.length - overA - crossings.filter((c) => c.over === '=').length}.`,
      `${clashes.length} CLASHES (GAP UNDER ${CROSS.tol} mm) AND ${tight.length} TIGHT CROSSINGS (UNDER THE ${CROSS.duct} mm DUCT HEIGHT) - LISTED IN THE SCHEDULE. A CLASH MEANS THE TWO DUCTS CANNOT BOTH SIT AT THEIR PROFILE: THE MORE LIGHTLY LOADED TENDON IS TO BE LOWERED UNDER (OR RAISED OVER) THE OTHER BY ONE DUCT HEIGHT IN RAM AND THE SHEETS RE-ISSUED.`,
      `A TIGHT CROSSING IS NOT A DESIGN ERROR: IN A SLAB TENDONED BOTH WAYS THE TWO PROFILES MUST PASS THROUGH ONE LEVEL SOMEWHERE ON THE SLOPE; THE LOWER DUCT BENDS A LITTLE ON SITE.`,
      'DEPTHS ARE FROM THE TOP OF THE SLAB (OR OF THE DROP PANEL WHERE THE CROSSING FALLS INSIDE ONE) TO THE DUCT CENTRE, FROM THE SAME PROFILE THE CHAIR HEIGHTS ARE TAKEN FROM.'].forEach((h, i) => pp.mtext(d2.x + 4, d2.y + d2.h - 12 - i * 13, h, { layer: 'NOTES', h: 1.6, width: d2.w - 8 }));
    return {
      rows, cols, rowH: 3, scheduleTitle: 'TENDON CROSSINGS - CLASHES AND TIGHT GAPS', detailsUsed: 2,
      totals: `${crossings.length} CROSSINGS · ${clashes.length} CLASHES (< ${CROSS.tol} mm) · ${tight.length} TIGHT (< ${CROSS.duct} mm)`,
      planTitles: ['TENDON CROSSINGS - WHICH TENDON PASSES OVER (BOTH DIRECTIONS)'],
      general: [
        commonNotes(model, level)[0],
        'BOTH TENDON DIRECTIONS ARE DRAWN TOGETHER: AT EVERY CROSSING THE TENDON DRAWN CONTINUOUS PASSES OVER AND THE ONE DRAWN BROKEN PASSES UNDER; THE FIGURE GIVES THE DIRECTION ON TOP AND THE GAP BETWEEN THE DUCT CENTRES IN mm.',
        `CROSSINGS UNDER ${CROSS.tol} mm ARE CLASHES (RED CIRCLE) AND ARE LISTED IN THE SCHEDULE WITH BOTH DEPTHS; CROSSINGS UNDER THE ${CROSS.duct} mm DUCT HEIGHT ARE TIGHT (YELLOW).`,
        'THE CHAIR HEIGHTS, EXTENSIONS AND SCHEDULES OF EACH DIRECTION ARE ON ITS OWN SHEET (07A / 07B); THIS SHEET IS FOR THE PLACING SEQUENCE AND THE PROFILE CHECK ONLY.',
      ],
      assumptions: levelAssumptions(model, level).slice(0, 3),
      legend: [['PT-Cross-A', 'TENDON, DIRECTION A - CONTINUOUS WHERE IT PASSES OVER', 'thick'], ['PT-Cross-B', 'TENDON, DIRECTION B - CONTINUOUS WHERE IT PASSES OVER', 'thick'], ['PT-Cross-Gap', 'GAP AT THE CROSSING (mm) + DIRECTION ON TOP', 'line'], ['PT-Cross-Tight', 'TIGHT GAP (UNDER THE DUCT HEIGHT)', 'line'], ['PT-Cross-Clash', 'CLASH (RED CIRCLE)', 'line'], ['PT-Cross-Mark', 'TENDON MARK', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
      checks: [`${crossings.length} tendon crossings: ${clashes.length} clashes under ${CROSS.tol} mm, ${tight.length} tight under the ${CROSS.duct} mm duct.`],
    };
  };
}

// ------------------------------------------------------------------ beams (RAM design read back)
/**
 * The beams of the level as RAM designed them (one design strip per beam span, see lib/beam-strips.mjs): every beam
 * labelled with its type and section on the plan, the types scheduled (section, top bars over the supports, bottom
 * bars in the span, stirrups, the beams of the type) and drawn in section.
 */
export function beamsSheet(model, level, meta) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    const sch = level.beamSchedule || { beams: [], types: [], undesigned: [] };
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, regionLabels: false, ubarRegions: false });
    for (const bm of sch.beams) {
      const L = dist(bm.a, bm.b) || 1, u = { x: (bm.b.x - bm.a.x) / L, y: (bm.b.y - bm.a.y) / L }, n = { x: -u.y, y: u.x };
      const poly = [{ x: bm.a.x + n.x * bm.width / 2, y: bm.a.y + n.y * bm.width / 2 }, { x: bm.b.x + n.x * bm.width / 2, y: bm.b.y + n.y * bm.width / 2 }, { x: bm.b.x - n.x * bm.width / 2, y: bm.b.y - n.y * bm.width / 2 }, { x: bm.a.x - n.x * bm.width / 2, y: bm.a.y - n.y * bm.width / 2 }];
      pl.hatch([poly], { layer: bm.mark ? 'BEAM' : 'CALLOUT', pattern: 'ANSI31', spacing: 1.2 });
      const m = { x: (bm.a.x + bm.b.x) / 2, y: (bm.a.y + bm.b.y) / 2 };
      let rot = (Math.atan2(u.y, u.x) * 180) / Math.PI;
      const off = bm.width / 2 + 0.6 * S;
      pl.text({ x: m.x + n.x * off, y: m.y + n.y * off }, `${bm.mark || '??'} ${size50(bm.width)}x${size50(bm.depth)}`, { layer: 'CALLOUT', h: 2.2, rot, align: 'C', valign: 'B', bold: true });
      const chk = (sch.office?.beams || []).find((x) => String(x.id).toUpperCase() === String(bm.id).toUpperCase());
      const bars = (bm.mark ? `${bm.top?.text || '-'} / ${bm.bottom?.text || '-'} / ${bm.stirrups?.text || '-'}` : `NOT DESIGNED${sch.design === 'ram' ? ' IN RAM' : ''}`) + (chk && chk.status === 'fail' ? ` - NOT PASSING (${(chk.reasons.length ? chk.reasons : ['RAM']).join(', ').toUpperCase()})` : '');
      pl.text({ x: m.x - n.x * off, y: m.y - n.y * off }, bars, { layer: 'TEXT', h: 1.6, rot, align: 'C', valign: 'T' });
      pl.text({ x: bm.a.x + u.x * 400 + n.x * off, y: bm.a.y + u.y * 400 + n.y * off }, bm.id, { layer: 'TEXT', h: 1.3, rot, align: 'L', valign: 'B' });
    }
    const designLabel = sch.design === 'office' ? 'OFFICE DESIGN' : sch.design === 'max' ? 'HEAVIER OF RAM AND OFFICE DESIGN' : 'RAM DESIGN';
    const office = sch.office || null;
    const failing = (office?.beams || []).filter((b) => b.status === 'fail');
    const bypass = model.spec.beams?.override && (model.spec.beams.override.by || model.spec.beams.override.beams) ? model.spec.beams.override : null;
    // the office design forces per beam (the first twelve; the rest in REPORT.md)
    const forces = office ? office.beams.slice(0, 12).map((b) => `${b.id} ${size50(b.width)}x${size50(b.depth)}: SPANS ${b.spans.map((sp) => (sp.length / 1000).toFixed(1)).join('+')} m, TRIB ${(b.trib_mm.total / 1000).toFixed(1)} m, wu ${b.loads.wu} kN/m, Mu- ${b.Mneg_max} / Mu+ ${b.Mpos_max} kN.m, Vu ${b.Vu} kN -> ${b.top?.text || '-'} / ${b.bottom?.text || '-'} / ${b.stirrups?.text || '-'}; DEFL. ${b.deflection.table_ok ? 'OK BY SPAN/DEPTH' : `${b.deflection.ratio} OF LIMIT${b.deflection.ok ? '' : ' - NOT PASSING'}`}${b.ram_failed ? '; REPORTED FAILING IN RAM' : ''}`) : [];
    if (office && office.beams.length > 12) forces.push(`${office.beams.length - 12} MORE BEAMS IN REPORT.md.`);
    const rows = sch.types.map((t) => ({ mark: t.isNew && sch.library ? `${t.mark} *` : t.mark, section: `${t.width} x ${t.depth}`, top: t.top?.text || '-', bottom: t.bottom?.text || '-', stirrups: t.stirrups ? `T${t.stirrups.dia}-${t.stirrups.legs} LEGS @ ${t.stirrups.spacing}` : '-', count: t.count, beams: t.beams.join(', ') }));
    const cols = [
      { key: 'mark', title: 'TYPE', w: 14 }, { key: 'section', title: 'SECTION\nb x h (mm)', w: 24 }, { key: 'top', title: 'TOP BARS\n(SUPPORTS)', w: 24 }, { key: 'bottom', title: 'BOTTOM BARS\n(SPAN)', w: 24 },
      { key: 'stirrups', title: 'STIRRUPS', w: 34 }, { key: 'count', title: 'No.', w: 10 }, { key: 'beams', title: 'BEAMS', w: 55, align: 'L', max: 34 },
    ];
    // the sections of the types, four to a box, at 1:25
    let detailsUsed = 0;
    const perBox = 4;
    for (let bi = 0; bi < 3 && bi * perBox < sch.types.length; bi++) {
      const group = sch.types.slice(bi * perBox, (bi + 1) * perBox);
      const d = sheet.detailBox(bi, `BEAM SECTIONS ${group[0].mark}${group.length > 1 ? ` - ${group[group.length - 1].mark}` : ''}`, '1:25');
      detailsUsed = bi + 1;
      const gap = 600;
      let x = 0;
      const maxH = Math.max(...group.map((t) => t.depth));
      const items = group.map((t) => { const it = { t, x }; x += t.width + gap; return it; });
      const gb = { minX: -200, maxX: x - gap + 200, minY: -1400, maxY: maxH + 300, cx: (x - gap) / 2, cy: (maxH - 1100) / 2 };
      const pen = sheet.detailPen(d, 25, gb);
      for (const { t, x: x0 } of items) {
        const cov = 40, b = t.width, h = t.depth;
        pen.pline([{ x: x0, y: 0 }, { x: x0 + b, y: 0 }, { x: x0 + b, y: h }, { x: x0, y: h }], { layer: 'OUTLINE', closed: true, lw: 35 });
        pen.pline([{ x: x0 + cov, y: cov }, { x: x0 + b - cov, y: cov }, { x: x0 + b - cov, y: h - cov }, { x: x0 + cov, y: h - cov }], { layer: 'REBAR', closed: true });
        const rowOf = (set, y) => { if (!set) return; const nb = set.n, r = set.dia / 2; const x1 = x0 + cov + 12, x2 = x0 + b - cov - 12; for (let i = 0; i < nb; i++) { const xx = nb > 1 ? x1 + ((x2 - x1) * i) / (nb - 1) : (x1 + x2) / 2; pen.circle({ x: xx, y }, r, { layer: 'REBAR' }); pen.hatch([[{ x: xx - r, y: y - r }, { x: xx + r, y: y - r }, { x: xx + r, y: y + r }, { x: xx - r, y: y + r }]], { layer: 'REBAR', pattern: 'SOLID' }); } };
        rowOf(t.top, h - cov - 20); rowOf(t.bottom, cov + 20);
        pen.text({ x: x0 + b / 2, y: -250 }, `${t.mark}  ${size50(b)}x${size50(h)}`, { layer: 'TEXT', h: 2.2, align: 'C', valign: 'T', bold: true });
        pen.text({ x: x0 + b / 2, y: -620 }, `TOP ${t.top?.text || '-'}  BOT ${t.bottom?.text || '-'}`, { layer: 'TEXT', h: 1.6, align: 'C', valign: 'T' });
        pen.text({ x: x0 + b / 2, y: -950 }, t.stirrups ? `T${t.stirrups.dia}-${t.stirrups.legs}L @ ${t.stirrups.spacing}` : '-', { layer: 'TEXT', h: 1.6, align: 'C', valign: 'T' });
        pen.text({ x: x0 + b / 2, y: -1250 }, `${t.count} BEAM${t.count > 1 ? 'S' : ''}`, { layer: 'NOTES', h: 1.4, align: 'C', valign: 'T' });
      }
    }
    const kg = sch.types.reduce((s, t) => s + t.beams.reduce((ss, id) => { const bm = sch.beams.find((b) => b.id === id); return ss + ((t.top?.area || 0) + (t.bottom?.area || 0)) * (bm ? bm.length : 0) * 7850 / 1e9; }, 0), 0);
    return {
      rows, cols, scheduleTitle: `BEAM SCHEDULE (${designLabel})`, detailsUsed, totals: `${sch.beams.length} BEAMS IN ${sch.types.length} TYPES${sch.undesigned.length ? ` · ${sch.undesigned.length} NOT DESIGNED` : ''} · MAIN BARS ≈ ${Math.round(kg)} kg`,
      weight: Math.round(kg),
      planTitles: [`BEAM MARKS AND SECTIONS - ${designLabel}`],
      general: [
        commonNotes(model, level)[0],
        `EVERY BEAM CARRIES ITS TYPE AND SECTION (b x h) ON THE PLAN; THE BARS OF THE TYPE ARE IN THE SCHEDULE AND THE SECTIONS. ${sch.design === 'office' ? 'THE BARS ARE THE OFFICE DESIGN: EVERY BEAM ANALYSED AS A CONTINUOUS BEAM OVER ITS COLUMNS AND WALLS UNDER THE SLAB IT CARRIES (SELF-WEIGHT, THE AREA LOADS OF THE MODEL, 1.2 D + 1.6 L, LIVE LOAD PATTERNED), FLEXURE, SHEAR AND DEFLECTION PER SBC 304 / ACI 318.' : sch.design === 'max' ? 'THE BARS ARE, SET BY SET, THE HEAVIER OF THE RAM CONCEPT DESIGN AND THE OFFICE DESIGN (CONTINUOUS-BEAM ANALYSIS ON THE MODEL LOADS, SBC 304 / ACI 318).' : 'TOP BARS ARE THE HEAVIEST RAM DESIGNED OVER THE SUPPORTS OF THE BEAM, BOTTOM BARS THE HEAVIEST IN ITS SPANS, STIRRUPS THE CLOSEST SPACING RAM DESIGNED IN IT.'}`,
        sch.design === 'ram' ? 'THE DESIGN COMES FROM ONE RAM CONCEPT DESIGN STRIP ON THE CENTRE LINE OF EVERY BEAM SPAN, BOUNDED BY A SPLITTER ON EACH EDGE OF THE BEAM, DESIGNED AS A BEAM. BEAMS OF ONE SECTION WHOSE BARS ARE ALIKE (WITHIN 15 %) SHARE A TYPE AND TAKE THE HEAVIER BARS.' : `THE OFFICE DESIGN FORCES OF EVERY BEAM ARE LISTED IN THE ASSUMPTIONS AND IN REPORT.md; ${sch.office?.assumed?.length ? sch.office.assumed.join('; ').toUpperCase() + '. ' : ''}THE RAM DESIGN REPORT GOVERNS. BEAMS OF ONE SECTION WHOSE BARS ARE ALIKE (WITHIN 15 %) SHARE A TYPE AND TAKE THE HEAVIER BARS.`,
        `${sch.undesigned.length ? `${sch.undesigned.length} BEAM(S) CARRY NO ${sch.design === 'ram' ? 'RAM ' : ''}DESIGN (${sch.undesigned.slice(0, 10).join(', ')}): RUN CALC ALL ON THE MODEL WITH THE BEAM STRIPS AND RE-ISSUE. ` : ''}CONTINUING TOP BARS, LAPS AND ANCHORAGES PER THE OFFICE BEAM DETAILS; STIRRUP SPACING TO BE HALVED OVER 2h FROM EVERY SUPPORT FACE.`,
        failing.length ? `BEAMS NOT PASSING THE OFFICE CHECK: ${failing.map((b) => `${b.id} (${b.reasons.join(', ') || 'REPORTED FAILING IN RAM'})`).join('; ').toUpperCase()}${bypass ? ` - ACCEPTED AT THE DESIGN ENGINEER'S RESPONSIBILITY (${[bypass.by, bypass.date].filter(Boolean).join(', ').toUpperCase()})${bypass.note ? ': ' + String(bypass.note).toUpperCase() : ''}` : ' - TO BE RESOLVED (DEEPEN THE BEAM OR CONFIRM AGAINST THE RAM REPORT)'}.` : null,
        sch.library ? `BEAM TYPES FOLLOW THE PROJECT'S UNIFIED BEAM SCHEDULE (${sch.library} TYPES ON RECORD): A BEAM TAKES THE LIGHTEST TYPE THAT CARRIES IT; ${sch.added?.length ? `TYPES MARKED * (${sch.added.map((t) => t.mark).join(', ')}) ARE NEW ON THIS SHEET, ADDED FOR BEAMS NO EXISTING TYPE CARRIES - THE EXISTING TYPES ARE UNCHANGED.` : 'NO NEW TYPE WAS NEEDED ON THIS SHEET.'}` : null,
      ],
      assumptions: [...forces, ...levelAssumptions(model, level).slice(0, forces.length ? 1 : 3)],
      legend: [['BEAM', 'BEAM (HATCHED) - TYPE AND SECTION BESIDE IT', 'hatch'], ['CALLOUT', `BEAM NOT DESIGNED${sch.design === 'ram' ? ' IN RAM' : ''}`, 'hatch'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
      checks: [`${sch.beams.length} beams, ${sch.types.length} types, ${sch.undesigned.length} without a design, ${failing.length} not passing the office check.`],
    };
  };
}

function cablesSheet(model, level, meta) {
  return (sheet, [pl]) => {
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, regionLabels: true, ubarRegions: false });
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
    const how = ['EACH SHEET IS A BLOCK NAMED AS LISTED; THE SAME NAME IS ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1 AND THE FRAME IS SCALED BY THE SHEET SCALE.', 'LAYERS PER THE SPAN TECH STANDARD (SPAN-): SPAN-RB-B1 / B2 / T1 / T2 (BARS), SPAN-RB-UBAR, SPAN-RB-TRIM, SPAN-RB-PUNCH, SPAN-RB-TEXT (CALL-OUTS), SPAN-RB-MESH, SPAN-RB-TYPE, SPAN-GRID, SPAN-SLAB-EDGE, SPAN-COL, SPAN-BEAM, SPAN-OPENING, SPAN-SUNKEN, SPAN-VOID, SPAN-PT-*, SPAN-SHEET-*, SPAN-DIM, SPAN-CALLOUT.', 'EXPLODE A BLOCK TO EDIT; RE-RUN THE GENERATOR AFTER THE CONSULTANT REVISES THE G.A. AND RE-ATTACH.'];
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
    project: 'PROJECT NAME', client: '', engineer: '', contractor: '', location: '', prefix: 'SPAN-SD', revision: '00',
    date: new Date().toISOString().slice(0, 10), prepared: '', checked: '', approved: '', status: 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
    ...metaIn,
  };
  const makers = { framing: framingSheet, bottom: bottomSheet, top: topSheet, addbottom: (m, l, mt) => ramBarsSheet(m, l, mt, 'B'), addtop: (m, l, mt) => ramBarsSheet(m, l, mt, 'T'), ubars: ubarSheet, voids: voidsSheet, openings: openingsSheet, cables: cablesSheet, cables_lat: (m, l, mt) => ramCablesSheet(m, l, mt, { set: 'latitude', variant: 'shop' }), cables_lon: (m, l, mt) => ramCablesSheet(m, l, mt, { set: 'longitude', variant: 'shop' }), cables_cross: ramCrossingsSheet, punching: punchingSheet, beams: beamsSheet };
  const jobs = [];
  for (const level of model.levels) for (const def of SHEET_DEFS) {
    if (def.ramOnly && !level.ram) continue;
    if (def.drawingOnly && level.ram) continue; // the empty cable template gives way to the RAM cable sheets
    if (def.set && !(level.ram.tendons || []).some((t) => t.spanSet === def.set)) continue; // no tendons in this direction
    if (def.needsBeams && !(level.beamSchedule?.types || []).length) continue; // no beam designed in RAM
    jobs.push({ level, def, draw: makers[def.key](model, level, meta) });
  }
  const total = jobs.length + 1;
  const sheets = jobs.map((j, i) => buildSheet({ model, level: j.level, def: j.def, meta, index: i + 2, total, draw: j.draw }));
  const cover = buildSheet({ model, level: null, def: { key: 'cover', base: 'SHOP_DRAWINGS_COVER_INDEX', title: 'COVER SHEET / DRAWING INDEX', no: '000' }, meta, index: 1, total, draw: coverSheet(model, sheets, meta) });
  return packSheets([cover, ...sheets], meta);
}

/** Apply the layer standard to every sheet and collect all sheet blocks into one package canvas. */
export function packSheets(all, meta, opts = {}) {
  const std = meta.layerStandard;
  for (const s of all) {
    if (std?.textStyles) for (const [n, d] of Object.entries(std.textStyles)) s.root.textStyleDef(n, d);
    if (std?.layers) s.root.applyLayerStandard(std.layers);
  }
  const pkg = new Canvas();
  if (std?.textStyles) for (const [n, d] of Object.entries(std.textStyles)) pkg.textStyleDef(n, d);
  for (const [n, d] of Object.entries(opts.textStyles || {})) pkg.textStyleDef(n, d);
  const perRow = 4;
  // the sheets sit in a grid spaced by the largest sheet (841 x 594 paper mm at the largest scale), so no two overlap
  const maxScale = Math.max(100, ...all.map((s) => s.scale || 100));
  const gapX = 900 * maxScale, gapY = 650 * maxScale;
  all.forEach((s, i) => {
    for (const [name, def] of s.root.layers) if (!pkg.layers.has(name)) pkg.layers.set(name, def);
    for (const [name, def] of s.root.textStyles || []) if (!pkg.textStyles.has(name)) pkg.textStyles.set(name, def);
    for (const [name, def] of s.root.dimStyles || []) if (!pkg.dimStyles.has(name)) pkg.dimStyles.set(name, def);
    pkg.blocks.set(s.blockName, s.root.blocks.get(s.blockName));
    // the blocks the sheet inserts (anchors LiveEnd / DeadEnd, symbols) go with it; the dimension pictures are renumbered below
    for (const [bn, bd] of s.root.blocks) if (bn !== s.blockName && !bn.startsWith('*D') && !pkg.blocks.has(bn)) pkg.blocks.set(bn, bd);
    // dimension picture blocks (*D1, *D2 ...) are numbered per sheet: renumber them package-wide (in the sheet root too, so both stay consistent)
    // (all renames are decided first, then applied once, so *D1 → *D143 never collides with the sheet's own *D143)
    const renames = new Map();
    for (const bn of s.root.blocks.keys()) if (bn.startsWith('*D')) renames.set(bn, `*D${++pkg.dimCount}`);
    if (renames.size) {
      const fresh = new Map();
      for (const [bn, bd] of s.root.blocks) fresh.set(renames.get(bn) || bn, bd);
      s.root.blocks = fresh;
      for (const [bn, nn] of renames) pkg.blocks.set(nn, s.root.blocks.get(nn));
      const rename = (cv) => { for (const e of cv.entities) if (e.t === 'dimension' && renames.has(e.block)) e.block = renames.get(e.block); };
      rename(s.root); for (const b2 of s.root.blocks.values()) rename(b2);
    }
    const x = (i % perRow) * gapX, y = -Math.floor(i / perRow) * gapY;
    pkg.insert(s.blockName, x, y);
    pkg.text(x, y + 594 * s.scale + 1500, `${s.drawingNo}  ${s.title}${s.level !== 'ALL' ? `  (${s.level})` : ''}`, { layer: 'XREF', h: 1200 });
  });
  if (std?.layers) pkg.applyLayerStandard(std.layers);
  return { meta, sheets: all, pkg };
}
