/**
 * Composes the drawing package: one block per sheet, per slab level, plus a
 * cover / index sheet. Each sheet gets its own Canvas so it can be written as
 * a stand-alone DXF (for Xref) and also collected into the package DXF.
 */
import { Canvas } from './canvas.mjs';
import { Sheet, chooseScale, layoutFor } from './sheet.mjs';
import * as R from './rebar.mjs';
import * as D from './details.mjs';
import { bbox, expandBbox, edges, rectPolygon, circlePolygon, dist } from './geometry.mjs';

export const SHEET_DEFS = [
  { key: 'framing', base: 'FRAMING_FORMWORK_NOTATION', title: 'FRAMING / FORMWORK NOTATION PLAN', no: '01' },
  { key: 'bottom', base: 'FRAMING_REBAR_SLAB_PT_BOTTOM', title: 'REBAR - BOTTOM REINFORCEMENT IN PT SLAB', no: '02' },
  { key: 'top', base: 'FRAMING_REBAR_ADDITIONAL_AT_COLUMNS', title: 'REBAR - ADDITIONAL TOP BARS OVER COLUMNS', no: '03' },
  { key: 'ubars', base: 'FRAMING_REBAR_U_BARS_AROUND_REGIONS', title: 'REBAR - U-BARS AT SLAB EDGES AND AROUND CIRCULAR REGIONS', no: '04' },
  { key: 'voids', base: 'FRAMING_REBAR_AROUND_VOIDS_ACUARS', title: 'REBAR - REINFORCEMENT AROUND VOIDS / ACUARS', no: '05' },
  { key: 'openings', base: 'FRAMING_REBAR_AROUND_OPENINGS', title: 'REBAR - REINFORCEMENT AROUND OPENINGS', no: '06' },
  { key: 'cables', base: 'CABLES_SCHEDULE_EMPTY_TEMPLATE', title: 'PT CABLES LAYOUT AND SCHEDULE - EMPTY TEMPLATE', no: '07' },
];

const SCHEDULE_COLS = [
  { key: 'mark', title: 'MARK', w: 14 },
  { key: 'dia', title: 'Ø', w: 9 },
  { key: 'shape', title: 'SHAPE', w: 13 },
  { key: 'spacing', title: 'SPAC.', w: 13 },
  { key: 'length', title: 'LENGTH\n(mm)', w: 17 },
  { key: 'qty', title: 'QTY', w: 13 },
  { key: 'total_m', title: 'TOTAL\n(m)', w: 17 },
  { key: 'weight_kg', title: 'WT.\n(kg)', w: 17 },
  { key: 'zones', title: 'ZONES / REMARKS', w: 72, align: 'L', max: 44 },
];

const fmtMM = (v) => Math.round(v).toLocaleString('en-US');
const regionBox = (o) => R.regionBbox(o);
const regionLabel = (o) => (o.kind === 'circle' ? `Ø${fmtMM(2 * o.r)}` : o.kind === 'rect' ? `${fmtMM(o.rect.w)} x ${fmtMM(o.rect.h)}` : `POLY ${fmtMM(Math.sqrt(Math.abs(R.polygonOf(o) && 1) || 1))}`);
const sizeOf = (o) => (o.kind === 'circle' ? `Ø${fmtMM(2 * o.r)}` : o.kind === 'rect' ? `${fmtMM(o.rect.w)} x ${fmtMM(o.rect.h)}` : `${fmtMM(regionBox(o).w)} x ${fmtMM(regionBox(o).h)} (POLY)`);
void regionLabel;

/** "B-C / 2-3" style reference for a region. */
export function gridRef(level, b) {
  const near = (arr, key, v) => arr.reduce((best, g) => (Math.abs(g[key] - v) < Math.abs((best ? best[key] : Infinity) - v) ? g : best), null);
  const x1 = near(level.grid.x, 'x', b.minX), x2 = near(level.grid.x, 'x', b.maxX);
  const y1 = near(level.grid.y, 'y', b.minY), y2 = near(level.grid.y, 'y', b.maxY);
  const xs = x1 && x2 ? (x1 === x2 ? x1.label : `${x1.label}-${x2.label}`) : '';
  const ys = y1 && y2 ? (y1 === y2 ? y1.label : `${y1.label}-${y2.label}`) : '';
  return `${xs} / ${ys}`;
}

/** Everything a plan needs under the reinforcement: grid, outline, columns, regions. */
function drawBase(sheet, pl, level, o = {}) {
  const S = sheet.S;
  const ob = level.bbox;
  const bubbleR = 4 * S;
  // grid
  for (const g of level.grid.x) {
    pl.line({ x: g.x, y: ob.minY - 3000 }, { x: g.x, y: ob.maxY + 3000 }, { layer: 'GRID' });
    pl.circle({ x: g.x, y: ob.maxY + 3000 + bubbleR }, bubbleR, { layer: 'GRID-BUBBLE' });
    pl.text({ x: g.x, y: ob.maxY + 3000 + bubbleR }, g.label, { layer: 'TEXT', h: 3.2, align: 'C', valign: 'M', bold: true });
  }
  for (const g of level.grid.y) {
    pl.line({ x: ob.minX - 3000, y: g.y }, { x: ob.maxX + 3000, y: g.y }, { layer: 'GRID' });
    pl.circle({ x: ob.minX - 3000 - bubbleR, y: g.y }, bubbleR, { layer: 'GRID-BUBBLE' });
    pl.text({ x: ob.minX - 3000 - bubbleR, y: g.y }, g.label, { layer: 'TEXT', h: 3.2, align: 'C', valign: 'M', bold: true });
  }
  // grid dimensions
  const gx = level.grid.x, gy = level.grid.y;
  for (let i = 0; i + 1 < gx.length; i++) pl.dim({ x: gx[i].x, y: ob.minY - 2200 }, { x: gx[i + 1].x, y: ob.minY - 2200 }, -6, { h: 2 });
  if (gx.length > 1) pl.dim({ x: gx[0].x, y: ob.minY - 2200 }, { x: gx[gx.length - 1].x, y: ob.minY - 2200 }, -13, { h: 2 });
  for (let i = 0; i + 1 < gy.length; i++) pl.dim({ x: ob.maxX + 2200, y: gy[i].y }, { x: ob.maxX + 2200, y: gy[i + 1].y }, -6, { h: 2 });
  if (gy.length > 1) pl.dim({ x: ob.maxX + 2200, y: gy[0].y }, { x: ob.maxX + 2200, y: gy[gy.length - 1].y }, -13, { h: 2 });
  // slab outline
  pl.pline(level.outline, { layer: 'OUTLINE', closed: true });
  // PT zones
  if (o.pt !== false) for (const z of level.pt.zones) {
    pl.pline(z.polygon, { layer: 'PT-ZONE', closed: true });
    const zb = bbox(z.polygon);
    pl.text({ x: zb.minX + 600, y: zb.maxY - 900 }, `${z.id} - PT SLAB ZONE`, { layer: 'PT-ZONE', h: 2.2 });
  }
  // columns
  for (const c of level.columns) {
    if (c.shape === 'circle') { pl.circle({ x: c.cx, y: c.cy }, c.d / 2, { layer: 'COLUMN' }); pl.hatch([circlePolygon(c.cx, c.cy, c.d / 2, 24)], { layer: 'COLUMN-HATCH', spacing: 1.2 }); }
    else { const r = { x: c.cx - c.w / 2, y: c.cy - c.h / 2, w: c.w, h: c.h }; pl.rect(r, { layer: 'COLUMN' }); pl.hatch([rectPolygon(r)], { layer: 'COLUMN-HATCH', spacing: 1.2 }); }
    if (o.columnIds !== false) pl.text({ x: c.cx + c.w / 2 + 150, y: c.cy + c.h / 2 + 150 }, c.id, { layer: 'TEXT', h: 1.6 });
  }
  // openings
  for (const op of level.openings) {
    const poly = R.polygonOf(op);
    pl.pline(poly, { layer: 'OPENING', closed: true });
    const b = bbox(poly);
    if (op.kind !== 'circle') { pl.line({ x: b.minX, y: b.minY }, { x: b.maxX, y: b.maxY }, { layer: 'OPENING' }); pl.line({ x: b.maxX, y: b.minY }, { x: b.minX, y: b.maxY }, { layer: 'OPENING' }); }
    if (o.regionLabels !== false) pl.text({ x: b.cx, y: b.maxY + 250 }, `${op.id}  OPENING ${sizeOf(op)}`, { layer: 'OPENING', h: 1.8, align: 'C' });
  }
  // voids
  for (const v of level.voids) {
    const poly = R.polygonOf(v);
    pl.pline(poly, { layer: 'VOID', closed: true });
    pl.hatch([poly], { layer: 'VOID-HATCH', pattern: 'ANSI37', spacing: 2.5 });
    const b = bbox(poly);
    if (o.regionLabels !== false) pl.text({ x: b.cx, y: b.maxY + 250 }, `${v.id}  VOID ${sizeOf(v)}`, { layer: 'VOID', h: 1.8, align: 'C' });
  }
  // circular U-bar regions
  if (o.ubarRegions !== false) for (const u of level.ubar.circles) {
    if (!u.fromOpening) pl.circle({ x: u.cx, y: u.cy }, u.r, { layer: 'REBAR-U', ltype: 'DASHDOT' });
    if (o.regionLabels !== false) pl.text({ x: u.cx, y: u.cy - u.r - 700 }, `${u.id}  U-BAR REGION Ø${fmtMM(2 * u.r)}`, { layer: 'REBAR-U', h: 1.8, align: 'C' });
  }
  // north arrow
  const P = sheet.L.plan;
  const nx = P.x + 16, ny = P.y + P.h - 20;
  sheet.pp.circle(nx, ny, 7, { layer: 'TEXT' });
  sheet.pp.solid([{ x: nx, y: ny + 6 }, { x: nx - 3, y: ny - 4 }, { x: nx, y: ny - 1.5 }, { x: nx + 3, y: ny - 4 }], { layer: 'TEXT' });
  sheet.pp.text(nx, ny + 9, 'N', { layer: 'TEXT', h: 3, align: 'C' });
}

const commonNotes = (model, level) => [
  'ALL DIMENSIONS ARE IN MILLIMETRES UNLESS NOTED OTHERWISE. DO NOT SCALE FROM THIS DRAWING.',
  `CONCRETE f'c = ${model.spec.fc} MPa (${model.spec.sources.fc}). REINFORCEMENT: DEFORMED BARS fy = ${model.spec.fy} MPa (${model.spec.sources.fy}). CLEAR COVER ${model.spec.cover} mm TOP AND BOTTOM (${model.spec.sources.cover}).`,
  `SLAB THICKNESS ${level.thickness} mm. THIS SHEET IS TO BE READ WITH THE STRUCTURAL CONSULTANT'S DRAWINGS AND THE PT LAYOUT; ANY DISCREPANCY TO BE REFERRED TO THE ENGINEER BEFORE FABRICATION.`,
  'BAR MARKS REFER TO THE SCHEDULE ON THIS SHEET. LENGTHS ARE CUTTING LENGTHS INCLUDING HOOKS. QUANTITIES ARE FOR THIS LEVEL ONLY.',
  'TENSION LAPS ARE CLASS B (1.3 ld) PER SBC 304-18 §25.5.2; NOT MORE THAN 50 % OF BARS LAPPED AT ONE SECTION, LAPS STAGGERED BY AT LEAST ONE LAP LENGTH.',
  'BARS ENDING AT A FREE EDGE TERMINATE WITH A STANDARD 90° HOOK (12 Ø) UNLESS NOTED.',
];

function lengthNote(model, dias) {
  return R.lengthTable(model.spec, dias).map((r) => `Ø${r.dia}: ld ${r.ld_bottom} (bot) / ${r.ld_top} (top) · LAP ${r.lap_bottom} (bot) / ${r.lap_top} (top) · ldh ${r.ldh}`);
}

const codeText = (model) => (model.spec.sources.code === 'drawing'
  ? `${model.code_reference} AS STATED ON THE STRUCTURAL DRAWINGS. DEVELOPMENT, ANCHORAGE AND LAP LENGTHS PER SBC 304-18 CHAPTER 25 (ACI 318-14 BASIS).`
  : 'SAUDI PRACTICE ASSUMED: SBC 304-18 (SAUDI BUILDING CODE - CONCRETE STRUCTURES, BASED ON ACI 318-14) FOR DEVELOPMENT, ANCHORAGE AND LAP LENGTHS. TO BE ADJUSTED ON RECEIPT OF THE FINAL DESIGN CRITERIA / CONSULTANT REQUIREMENTS.');

const levelAssumptions = (model, level) => model.assumptions.filter((a) => !a.level || a.level === level.id).map((a) => a.text);

/** Build one sheet. `draw` returns { rows, cols, scheduleTitle, totals, general, legend, extra, detailsUsed } */
function buildSheet({ model, level, def, meta, index, total, draw }) {
  const root = new Canvas();
  const blockName = level ? `${def.base}_${level.id}` : def.base;
  const L = layoutFor('A1');
  const pb = level ? expandBbox(level.bbox, 7500) : null;
  const scale = level ? chooseScale(pb, L.plan) : 100;
  const sheet = new Sheet(root, { blockName, scale });
  sheet.frame();
  const pl = level ? sheet.setPlan(pb) : null;
  const r = draw(sheet, pl) || {};
  const drawingNo = level ? `${meta.prefix}-${level.id}-${def.no}` : `${meta.prefix}-000`;

  // schedule
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
  sheet.notes({
    general: r.general || [],
    assumptions: r.assumptions || [],
    codeRef: codeText(model),
    legend: r.legend || [],
    extra: r.extra || [],
  });
  sheet.titleBlock({
    ...meta,
    title: def.title,
    level: level ? `${level.id} - ${level.name}` : 'ALL LEVELS',
    drawingNo,
    sheet: `${index} OF ${total}`,
    scale: level ? `1:${scale} @ A1 (DETAILS AS NOTED)` : 'N.T.S.',
    gridRef: level ? `${level.grid.x[0]?.label}-${level.grid.x[level.grid.x.length - 1]?.label} / ${level.grid.y[0]?.label}-${level.grid.y[level.grid.y.length - 1]?.label}` : 'ALL',
    index: `${meta.prefix}-000`,
    codeRef: model.code_reference ? `${model.code_reference} (ON DRAWINGS)` : 'SBC 304-18 (ASSUMED)',
  });
  if (level) sheet.planTitle(`${level.name} - ${def.title}`, `SCALE 1:${scale}`);
  root.insert(blockName, 0, 0);
  const rows = r.rows || [];
  return { root, sheet, blockName, drawingNo, title: def.title, level: level ? level.id : 'ALL', levelName: level ? level.name : '', scale, key: def.key, rows: rows.concat(leftover.length ? [] : []), csvCols: r.cols || SCHEDULE_COLS, weight: r.weight || 0, leftoverRows: leftover.length, checks: r.checks || [] };
}

// ------------------------------------------------------------------ sheets
function framingSheet(model, level) {
  return (sheet, pl) => {
    drawBase(sheet, pl, level);
    // slab thickness note on plan
    pl.text({ x: level.bbox.minX + 800, y: level.bbox.minY + 700 }, `PT FLAT SLAB THK. ${level.thickness} mm`, { layer: 'TEXT', h: 2.6, bold: true });
    // callouts for regions
    for (const op of level.openings) { const b = regionBox(op); pl.bubble({ x: b.maxX, y: b.maxY }, op.id, { dx: 9, dy: 9, layer: 'CALLOUT' }); }
    for (const v of level.voids) { const b = regionBox(v); pl.bubble({ x: b.minX, y: b.maxY }, v.id, { dx: -9, dy: 9, layer: 'CALLOUT' }); }
    for (const u of level.ubar.circles) pl.bubble({ x: u.cx, y: u.cy }, u.id, { dx: 9, dy: -9, layer: 'CALLOUT' });
    const rows = [
      ...level.columns.map((c) => ({ id: c.id, element: c.shape === 'circle' ? 'COLUMN (ROUND)' : 'COLUMN', size: c.shape === 'circle' ? `Ø${fmtMM(c.d)}` : `${fmtMM(c.w)} x ${fmtMM(c.h)}`, location: `X ${fmtMM(c.cx)}, Y ${fmtMM(c.cy)}` })),
      ...level.openings.map((o) => ({ id: o.id, element: 'OPENING', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...level.voids.map((o) => ({ id: o.id, element: 'VOID / ACUAR', size: sizeOf(o), location: gridRef(level, regionBox(o)) })),
      ...level.ubar.circles.map((o) => ({ id: o.id, element: 'U-BAR REGION', size: `Ø${fmtMM(2 * o.r)}`, location: gridRef(level, { minX: o.cx - o.r, maxX: o.cx + o.r, minY: o.cy - o.r, maxY: o.cy + o.r }) })),
    ];
    const cols = [{ key: 'id', title: 'ID', w: 22 }, { key: 'element', title: 'ELEMENT', w: 38 }, { key: 'size', title: 'SIZE (mm)', w: 45 }, { key: 'location', title: 'LOCATION / GRID', w: 80, align: 'L', max: 46 }];
    // details
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
        'COLUMN POSITIONS, SLAB OUTLINE, OPENINGS AND VOIDS ARE READ FROM THE CONSULTANT\'S COMBINED STRUCTURAL DRAWINGS; VERIFY AGAINST ARCHITECTURAL DRAWINGS BEFORE FORMWORK.',
        'OPENINGS ARE CROSSED; VOID / ACUAR ZONES ARE HATCHED; CIRCULAR U-BAR REGIONS ARE DASH-DOT CIRCLES. SEE SHEETS 02-06 FOR REINFORCEMENT.',
        'FORMWORK LEVELS AND CAMBER PER PT DESIGN. NO PENETRATIONS THROUGH THE SLAB OTHER THAN THOSE SHOWN WITHOUT THE ENGINEER\'S APPROVAL.',
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['OUTLINE', 'SLAB OUTLINE', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'hatch'], ['OPENING', 'OPENING', 'line'], ['VOID', 'VOID / ACUAR', 'line'], ['PT-ZONE', 'PT ZONE', 'line'], ['REBAR-U', 'U-BAR REGION', 'line']],
      detailsUsed: 3,
    };
  };
}

function bottomSheet(model, level) {
  const res = R.bottomMesh(level, model.spec);
  return (sheet, pl) => {
    res.bars.rows(); // assign marks before they are quoted in call-outs
    drawBase(sheet, pl, level, { columnIds: false, regionLabels: false });
    const s = model.spec.bottom;
    for (const z of res.zones) {
      z.groups.forEach((g) => {
        const mid = (g.start + g.end) / 2;
        g.runs.forEach((run, ri) => {
          const a = z.dir === 'X' ? { x: run.a, y: mid } : { x: mid, y: run.a };
          const b = z.dir === 'X' ? { x: run.b, y: mid } : { x: mid, y: run.b };
          pl.line(a, b, { layer: 'REBAR-BOT' });
          pl.barEnds(a, b, { layer: 'REBAR-BOT' });
          // lap positions (non-staggered set)
          let pos = run.a;
          run.piecesA.slice(0, -1).forEach((len) => {
            pos += len;
            const p1 = z.dir === 'X' ? { x: pos - res.lap, y: mid } : { x: mid, y: pos - res.lap };
            const p2 = z.dir === 'X' ? { x: pos, y: mid } : { x: mid, y: pos };
            pl.line(z.dir === 'X' ? { x: p1.x, y: mid + 120 } : { x: mid + 120, y: p1.y }, z.dir === 'X' ? { x: p2.x, y: mid + 120 } : { x: mid + 120, y: p2.y }, { layer: 'REBAR-BOT' });
            pos -= res.lap;
          });
          // extent + callout (first run of the group only)
          if (ri === 0) {
            const off = run.a + 0.12 * run.L + (g.rows % 3) * 900;
            const e1 = z.dir === 'X' ? { x: off, y: g.start } : { x: g.start, y: off };
            const e2 = z.dir === 'X' ? { x: off, y: g.end } : { x: g.end, y: off };
            const marks = run.marks.map((m) => m.mark).join('+');
            pl.extent(e1, e2, `${g.rows}T${s.dia}@${s.spacing} B  L=${run.piecesA.join('+')}  (${marks})`, { h: 1.8 });
          }
        });
      });
    }
    // details
    const d0 = sheet.detailBox(0, 'SECTION - BOTTOM MESH AND LAP', '1:20');
    const det0 = D.sectionMesh({ h: level.thickness, cover: model.spec.cover, dia: s.dia, lap: res.lap, spacing: s.spacing });
    det0.draw(sheet.detailPen(d0, 20, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT OPENING - MESH STOPPED', '1:10');
    const det1 = D.sectionTrimmer({ h: level.thickness, cover: model.spec.cover, count: model.spec.openings.count, dia: model.spec.openings.dia, uLeg: model.spec.openings.uLeg, uDia: model.spec.openings.uDia, withU: true });
    det1.draw(sheet.detailPen(d1, 10, det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    const marksFix = rows; // marks assigned by rows()
    void marksFix;
    return {
      rows, totals: `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`,
      weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `BOTTOM MESH T${s.dia}@${s.spacing} BOTH WAYS IN THE PT ZONE(S) AS BONDED REINFORCEMENT; PLACED ON CHAIRS OVER THE SOFFIT, BELOW THE TENDONS. BARS RUN CONTINUOUSLY THROUGH COLUMNS AND STOP AT OPENINGS (SEE DETAIL 2).`,
        'BAR LENGTHS ARE CUT FROM THE ZONE BOUNDARY LESS COVER; RUNS LONGER THAN ONE STOCK LENGTH ARE SPLIT WITH CLASS B LAPS, ALTERNATE BARS STARTING WITH A HALF STOCK LENGTH (STAGGER).',
        ...lengthNote(model, [s.dia]),
      ],
      assumptions: [...levelAssumptions(model, level), ...res.assumptions],
      legend: [['REBAR-BOT', `T${s.dia} BOTTOM BAR (REPRESENTATIVE)`, 'thick'], ['REBAR-EXTENT', 'BAR RANGE / EXTENT', 'line'], ['OPENING', 'OPENING', 'line']],
      detailsUsed: 2,
    };
  };
}

function topSheet(model, level) {
  const res = R.topAtColumns(level, model.spec);
  return (sheet, pl) => {
    res.bars.rows(); // assign marks before they are quoted in call-outs
    drawBase(sheet, pl, level, { regionLabels: false, ubarRegions: false });
    const s = model.spec.topColumns;
    const seen = new Set();
    for (const { col, type, per } of res.columns) {
      const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
      for (const dir of ['x', 'y']) {
        const p = per[dir];
        const c1 = size[dir];
        const start = (dir === 'x' ? col.cy : col.cx) - ((p.n - 1) * s.spacing) / 2;
        for (let k = 0; k < p.n; k++) {
          const t = start + k * s.spacing;
          const a0 = (dir === 'x' ? col.cx : col.cy) - c1 / 2 - p.ext[-1];
          const b0 = (dir === 'x' ? col.cx : col.cy) + c1 / 2 + p.ext[1];
          const a = dir === 'x' ? { x: a0, y: t } : { x: t, y: a0 };
          const b = dir === 'x' ? { x: b0, y: t } : { x: t, y: b0 };
          pl.line(a, b, { layer: 'REBAR-TOP' });
          if (k === 0 || k === p.n - 1) pl.barEnds(a, b, { layer: 'REBAR-TOP', size: 0.7 });
          if (p.hooks[-1]) pl.line(a, dir === 'x' ? { x: a.x, y: a.y - 150 } : { x: a.x - 150, y: a.y }, { layer: 'REBAR-TOP' });
          if (p.hooks[1]) pl.line(b, dir === 'x' ? { x: b.x, y: b.y - 150 } : { x: b.x - 150, y: b.y }, { layer: 'REBAR-TOP' });
        }
      }
      const at = { x: col.cx + size.x / 2 + per.x.ext[1] * 0.4, y: col.cy + size.y / 2 + per.y.ext[1] * 0.4 };
      pl.bubble(at, type.id, { dx: 7, dy: 7, layer: 'CALLOUT', r: 3.6, h: 1.9 });
      if (!seen.has(type.id)) {
        seen.add(type.id);
        const tx = { x: col.cx + size.x / 2 + per.x.ext[1] + 500, y: col.cy - size.y / 2 - per.y.ext[-1] - 300 };
        pl.text(tx, `${type.id}: ${per.x.n}T${s.dia} X-DIR L=${per.x.length} (${per.x.shape})`, { layer: 'REBAR-TEXT', h: 1.7 });
        pl.text({ x: tx.x, y: tx.y - 2.4 * sheet.S }, `      ${per.y.n}T${s.dia} Y-DIR L=${per.y.length} (${per.y.shape})  @${s.spacing} TOP`, { layer: 'REBAR-TEXT', h: 1.7 });
      }
    }
    // details
    const t0 = res.types[0];
    const d0 = sheet.detailBox(0, 'SECTION AT COLUMN - TOP BARS', '1:25');
    const c0 = res.columns[0]?.col;
    const det0 = D.sectionColumn({ h: level.thickness, c1: c0 ? (c0.shape === 'circle' ? c0.d : c0.w) : 600, ext: t0 ? Math.max(t0.x.ext[-1], t0.x.ext[1]) : 1200, dia: s.dia, spacing: s.spacing, cover: model.spec.cover, hookLeg: R.hookLeg(s.dia), shape: t0 ? t0.x.shape : 'STR' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    // type table in detail box 1
    const d1 = sheet.detailBox(1, 'TOP BAR TYPES OVER COLUMNS', '');
    const typeCols = [{ key: 'id', title: 'TYPE', w: 14 }, { key: 'x', title: 'X-DIR BARS', w: 46, align: 'L' }, { key: 'y', title: 'Y-DIR BARS', w: 46, align: 'L' }, { key: 'as', title: 'As req/prov (mm²)', w: 34 }, { key: 'cols', title: 'COLUMNS', w: (d1.w - 6) - 140, align: 'L', max: 34 }];
    const typeRows = res.types.map((t) => ({ id: t.id, x: `${t.x.n}T${s.dia} L=${t.x.length} ${t.x.shape}`, y: `${t.y.n}T${s.dia} L=${t.y.length} ${t.y.shape}`, as: `${Math.max(t.x.asReq, t.y.asReq)} / ${Math.min(t.x.asProv, t.y.asProv)}`, cols: t.columns.join(', ') }));
    sheet.table(d1.x + 3, d1.y + d1.h - 10, typeCols, typeRows, { maxRows: Math.floor((d1.h - 18) / 4), headH: 5, rowH: 4, h: 1.6 });
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  Ø${s.dia}: ${tot.byDia[0]?.total_m} m`,
      weight: tot.weight_kg, checks: res.checks,
      general: [
        ...commonNotes(model, level),
        `ADDITIONAL TOP BARS T${s.dia}@${s.spacing} BOTH WAYS OVER EVERY COLUMN, PLACED WITHIN A BAND OF c2 + 1.5h EACH SIDE OF THE COLUMN (SBC 304-18 §8.7.5.5.1), EXTENDING NOT LESS THAN ln/6 BEYOND THE FACE OF SUPPORT ON EACH SIDE (§8.7.5.5.2).`,
        'MINIMUM BONDED REINFORCEMENT OVER COLUMNS As = 0.00075·Acf (§8.6.2.3) IS CHECKED PER COLUMN; WHERE IT GOVERNS THE BAR COUNT IS INCREASED (SEE TYPE TABLE, DETAIL 2).',
        'TOP BARS SIT DIRECTLY BELOW THE TOP COVER, ABOVE THE TENDONS, SUPPORTED ON CHAIRS. BAR TYPES (TC) ARE CALLED OUT AT EACH COLUMN.',
        ...lengthNote(model, [s.dia]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR-TOP', `T${s.dia} TOP BAR`, 'thick'], ['CALLOUT', 'TOP BAR TYPE CALL-OUT', 'line'], ['COLUMN-HATCH', 'COLUMN', 'hatch']],
      detailsUsed: 2,
    };
  };
}

function ubarSheet(model, level) {
  const res = R.uBars(level, model.spec);
  return (sheet, pl) => {
    res.bars.rows(); // assign marks before they are quoted in call-outs
    drawBase(sheet, pl, level, { columnIds: false, regionLabels: false, ubarRegions: false, pt: false });
    const su = model.spec.uEdge, se = model.spec.edgeBars, sc = model.spec.uCircle, sr = model.spec.ringBars;
    const cover = model.spec.cover;
    for (const e of res.edgeItems) {
      const ux = (e.b.x - e.a.x) / e.length, uy = (e.b.y - e.a.y) / e.length;
      let nx = -uy, ny = ux; // inward for a CCW outline
      // edge bars T&B (drawn as two offset lines)
      for (const off of [cover + 40, cover + 110]) {
        pl.line({ x: e.a.x + nx * off + ux * cover, y: e.a.y + ny * off + uy * cover }, { x: e.b.x + nx * off - ux * cover, y: e.b.y + ny * off - uy * cover }, { layer: 'REBAR-U' });
      }
      // U-bar symbols every 5th bar
      const step = su.spacing * 5;
      for (let d = cover + su.spacing / 2; d < e.length - cover; d += step) {
        const p = { x: e.a.x + ux * d, y: e.a.y + uy * d };
        pl.line({ x: p.x + nx * cover, y: p.y + ny * cover }, { x: p.x + nx * su.leg, y: p.y + ny * su.leg }, { layer: 'REBAR-U' });
        pl.line({ x: p.x + nx * cover - ux * 80, y: p.y + ny * cover - uy * 80 }, { x: p.x + nx * cover + ux * 80, y: p.y + ny * cover + uy * 80 }, { layer: 'REBAR-U' });
      }
      const mid = { x: (e.a.x + e.b.x) / 2 + nx * (su.leg + 700), y: (e.a.y + e.b.y) / 2 + ny * (su.leg + 700) };
      let rot = (Math.atan2(uy, ux) * 180) / Math.PI; if (rot > 90 || rot <= -90) rot += 180;
      pl.text(mid, `${e.id}: ${e.n}T${su.dia}@${su.spacing} U-BARS LEGS ${su.leg} (${e.uMark.mark}) + ${se.count}T${se.dia} T&B EDGE BARS (${e.marks.map((m) => m.mark).join('+')})`, { layer: 'REBAR-TEXT', h: 1.7, rot, align: 'C' });
      pl.bubble({ x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 }, e.id, { dx: -nx * 6, dy: -ny * 6, layer: 'CALLOUT', r: 3, h: 1.7 });
    }
    for (const c of res.circleItems) {
      pl.circle({ x: c.cx, y: c.cy }, c.r, { layer: c.fromOpening ? 'OPENING' : 'REBAR-U', ltype: c.fromOpening ? undefined : 'DASHDOT' });
      pl.circle({ x: c.cx, y: c.cy }, c.ringR, { layer: 'REBAR-U' });
      pl.circle({ x: c.cx, y: c.cy }, c.ringR + 60, { layer: 'REBAR-U' });
      const nDraw = Math.min(c.n, 24);
      for (let i = 0; i < nDraw; i++) {
        const a = (i / nDraw) * Math.PI * 2;
        pl.line({ x: c.cx + (c.r + cover) * Math.cos(a), y: c.cy + (c.r + cover) * Math.sin(a) }, { x: c.cx + (c.r + cover + sc.leg) * Math.cos(a), y: c.cy + (c.r + cover + sc.leg) * Math.sin(a) }, { layer: 'REBAR-U' });
      }
      pl.bubble({ x: c.cx, y: c.cy }, c.id, { dx: 10, dy: 10, layer: 'CALLOUT' });
      pl.text({ x: c.cx, y: c.cy - c.r - cover - sc.leg - 500 }, `${c.id}: ${c.n}T${sc.dia}@${sc.spacing} RADIAL U-BARS (${c.uMark.mark}) + ${sr.count}T${sr.dia} RINGS T&B (${c.ringMarks.map((m) => m.mark).join('+')})`, { layer: 'REBAR-TEXT', h: 1.7, align: 'C' });
    }
    const d0 = sheet.detailBox(0, 'U-BAR AT SLAB EDGE - SECTION', '1:10');
    const det0 = D.sectionUEdge({ h: level.thickness, cover, leg: su.leg, dia: su.dia, edgeDia: se.dia, spacing: su.spacing });
    det0.draw(sheet.detailPen(d0, 10, det0.bbox));
    const d1 = sheet.detailBox(1, 'U-BARS AROUND CIRCULAR REGION - PLAN', '1:25');
    const c0 = res.circleItems[0] || { r: 1000, ringR: 1000 + cover + sc.dia + sr.dia / 2 };
    const det1 = D.planUCircle({ r: c0.r, cover, leg: sc.leg, spacing: sc.spacing, dia: sc.dia, ringR: c0.ringR, ringDia: sr.dia });
    det1.draw(sheet.detailPen(d1, Math.max(20, Math.ceil(((c0.r + cover + sc.leg + 450) * 2) / (d1.h - 24) / 5) * 5), det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`,
      weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `U-BARS T${su.dia}@${su.spacing} WITH ${su.leg} mm LEGS TOP AND BOTTOM ALONG ALL PT ANCHORAGE EDGES (BURSTING / SPALLING STEEL), WITH ${se.count}T${se.dia} LONGITUDINAL BARS TOP AND BOTTOM INSIDE THE U-BARS. U-BAR DEPTH = SLAB THICKNESS - 2 x COVER = ${res.web} mm.`,
        `AROUND CIRCULAR REGIONS: RADIAL U-BARS T${sc.dia}@${sc.spacing} (LEGS ${sc.leg}) PLUS ${sr.count}T${sr.dia} RING BARS TOP AND BOTTOM, RINGS LAPPED CLASS B.`,
        'U-BARS ARE PLACED BEFORE THE ANCHORAGES ARE FIXED; DO NOT CUT U-BARS TO SUIT ANCHORAGE POCKETS - RELOCATE WITHIN THE SPACING.',
        ...lengthNote(model, [...new Set([su.dia, se.dia, sc.dia])]),
      ],
      assumptions: [...levelAssumptions(model, level), ...res.assumptions],
      legend: [['REBAR-U', 'U-BAR / RING BAR', 'thick'], ['CALLOUT', 'EDGE / REGION ID', 'line'], ['OUTLINE', 'SLAB EDGE', 'thick']],
      detailsUsed: 2,
    };
  };
}

function drawTrimmers(pl, sheet, regions, spec, kind) {
  for (const { region, trimmers, corners, diagMark, uMark, nU, diagL } of regions) {
    for (const t of trimmers) {
      for (const off of t.offsets) {
        const a = { x: t.edge.a.x - t.ux * t.ext[-1] + t.nx * off, y: t.edge.a.y - t.uy * t.ext[-1] + t.ny * off };
        const b = { x: t.edge.b.x + t.ux * t.ext[1] + t.nx * off, y: t.edge.b.y + t.uy * t.ext[1] + t.ny * off };
        pl.line(a, b, { layer: 'REBAR-TRIM' });
        pl.barEnds(a, b, { layer: 'REBAR-TRIM', size: 0.7 });
        if (t.hooks[-1]) pl.line(a, { x: a.x + t.nx * 200, y: a.y + t.ny * 200 }, { layer: 'REBAR-TRIM' });
        if (t.hooks[1]) pl.line(b, { x: b.x + t.nx * 200, y: b.y + t.ny * 200 }, { layer: 'REBAR-TRIM' });
      }
    }
    if (corners) for (const c of corners) {
      for (const off of [-45, 45]) {
        const ox = -c.dy * off, oy = c.dx * off;
        pl.line({ x: c.c.x - c.dx * diagL / 2 + ox, y: c.c.y - c.dy * diagL / 2 + oy }, { x: c.c.x + c.dx * diagL / 2 + ox, y: c.c.y + c.dy * diagL / 2 + oy }, { layer: 'REBAR-TRIM' });
      }
    }
    if (uMark && nU) {
      const poly = R.polygonOf(region);
      for (const e of edges(poly)) {
        const ux = e.dx / e.length, uy = e.dy / e.length;
        let nx = -uy, ny = ux;
        const mid = { x: (e.a.x + e.b.x) / 2, y: (e.a.y + e.b.y) / 2 };
        if (!R.polygonOf(region) || pointInside({ x: mid.x + nx * 10, y: mid.y + ny * 10 }, poly)) { nx = -nx; ny = -ny; }
        for (let d = 150; d < e.length; d += spec.uSpacing * 2) pl.line({ x: e.a.x + ux * d, y: e.a.y + uy * d }, { x: e.a.x + ux * d + nx * spec.uLeg, y: e.a.y + uy * d + ny * spec.uLeg }, { layer: 'REBAR-U' });
      }
    }
    const b = regionBox(region);
    const first = trimmers[0];
    pl.bubble({ x: b.maxX, y: b.maxY }, region.id, { dx: 12, dy: 8, layer: 'CALLOUT' });
    const lines = [`${region.id} ${kind} ${sizeOf(region)}: ${trimmers[0] ? `${spec.count}T${spec.dia} T&B EACH SIDE` : ''} (${[...new Set(trimmers.flatMap((t) => t.marks.map((m) => m.mark)))].join(',')}) ANCHORED ld=${first ? first.ld : ''} BEYOND CORNERS`];
    if (diagMark) lines.push(`${spec.diagCount}T${spec.diagDia} DIAGONALS T&B AT CORNERS L=${diagMark.length} (${diagMark.mark})`);
    if (uMark && nU) lines.push(`${nU}T${spec.uDia}@${spec.uSpacing} U-BARS AT FREE EDGES LEGS ${spec.uLeg} (${uMark.mark})`);
    lines.forEach((ln, i) => pl.text({ x: b.maxX + 16 * sheet.S, y: b.maxY + (8 - i * 2.6) * sheet.S }, ln, { layer: 'REBAR-TEXT', h: 1.7 }));
  }
}

function pointInside(p, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i], b = poly[j];
    if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) inside = !inside;
  }
  return inside;
}

function voidsSheet(model, level) {
  const res = R.aroundVoids(level, model.spec);
  return (sheet, pl) => {
    res.bars.rows(); // assign marks before they are quoted in call-outs
    drawBase(sheet, pl, level, { columnIds: false, regionLabels: false, ubarRegions: false, pt: false });
    drawTrimmers(pl, sheet, res.regions.map((r) => ({ ...r, corners: null, diagMark: null, uMark: null, nU: 0 })), model.spec.voids, 'VOID');
    const sv = model.spec.voids;
    const d0 = sheet.detailBox(0, 'TRIMMER BARS AROUND VOID - PLAN', '1:25');
    const det0 = D.planTrimmers({ w: 1500, h: 1000, ld: res.ld, count: sv.count, dia: sv.dia, diag: false, label: 'VOID / ACUAR' });
    det0.draw(sheet.detailPen(d0, 25, det0.bbox));
    const d1 = sheet.detailBox(1, 'SECTION AT VOID EDGE', '1:10');
    const det1 = D.sectionTrimmer({ h: level.thickness, cover: model.spec.cover, count: sv.count, dia: sv.dia, uLeg: 600, uDia: 12, withU: false });
    det1.draw(sheet.detailPen(d1, 10, det1.bbox));
    const rows = res.bars.rows();
    const tot = res.bars.totals();
    return {
      rows, totals: `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`,
      weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `${sv.count}T${sv.dia} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY VOID / ACUAR ZONE, ANCHORED ld = ${res.ld} mm BEYOND THE CORNERS INTO THE SOLID SLAB. WHERE THE ANCHORAGE WOULD LEAVE THE SLAB THE BAR IS STOPPED AT THE EDGE WITH A 90° HOOK.`,
        'VOID FORMERS TO BE TIED DOWN AGAINST FLOTATION; THE MAIN MESH RUNS CONTINUOUSLY THROUGH THE VOIDED ZONE. NO TENDON DEVIATION THROUGH VOIDS WITHOUT THE PT DESIGNER\'S APPROVAL.',
        ...lengthNote(model, [sv.dia]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR-TRIM', `T${sv.dia} TRIMMER BAR`, 'thick'], ['VOID-HATCH', 'VOID / ACUAR ZONE', 'hatch'], ['CALLOUT', 'VOID ID', 'line']],
      detailsUsed: 2,
    };
  };
}

function openingsSheet(model, level) {
  const res = R.aroundOpenings(level, model.spec);
  return (sheet, pl) => {
    res.bars.rows(); // assign marks before they are quoted in call-outs
    drawBase(sheet, pl, level, { columnIds: false, regionLabels: false, ubarRegions: false, pt: false });
    drawTrimmers(pl, sheet, res.regions.map((r) => ({ ...r, diagL: res.diagL })), model.spec.openings, 'OPENING');
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
      rows, totals: `TOTAL ${tot.weight_kg.toLocaleString('en-US')} kg  ·  ${tot.byDia.map((d) => `Ø${d.dia}: ${d.total_m} m`).join('  ')}`,
      weight: tot.weight_kg,
      general: [
        ...commonNotes(model, level),
        `${so.count}T${so.dia} TRIMMER BARS TOP AND BOTTOM ALONG EACH SIDE OF EVERY OPENING, ANCHORED ld = ${res.ld} mm BEYOND THE CORNERS; ${so.diagCount}T${so.diagDia} DIAGONAL BARS TOP AND BOTTOM AT EACH RE-ENTRANT CORNER, L = ${res.diagL} mm; T${so.uDia}@${so.uSpacing} U-BARS WITH ${so.uLeg} mm LEGS ALONG THE FREE EDGES.`,
        'THE MAIN MESH IS STOPPED AT THE OPENING FACE LESS COVER; TRIMMERS REPLACE THE INTERRUPTED BARS. TENDONS ARE DEVIATED AROUND OPENINGS PER THE PT LAYOUT - NO TENDON MAY BE CUT.',
        ...lengthNote(model, [...new Set([so.dia, so.diagDia, so.uDia])]),
      ],
      assumptions: levelAssumptions(model, level),
      legend: [['REBAR-TRIM', `T${so.dia} TRIMMER / T${so.diagDia} DIAGONAL`, 'thick'], ['REBAR-U', `T${so.uDia} U-BAR`, 'line'], ['OPENING', 'OPENING', 'line'], ['CALLOUT', 'OPENING ID', 'line']],
      detailsUsed: 2,
    };
  };
}

function cablesSheet(model, level) {
  return (sheet, pl) => {
    drawBase(sheet, pl, level, { columnIds: true, regionLabels: true, ubarRegions: false });
    sheet.stamp('EMPTY TEMPLATE - NO TENDONS SHOWN', 'TENDON LAYOUT, PROFILES AND QUANTITIES TO BE ADDED ON COMPLETION OF THE PT DESIGN');
    const cols = [
      { key: 'id', title: 'TENDON\nID', w: 16 }, { key: 'type', title: 'TYPE', w: 16 }, { key: 'strands', title: 'No.\nSTR.', w: 12 }, { key: 'profile', title: 'PROFILE\nREF.', w: 18 },
      { key: 'length', title: 'LENGTH\n(m)', w: 17 }, { key: 'live', title: 'LIVE\nEND', w: 16 }, { key: 'jack', title: 'JACK\n(kN)', w: 17 }, { key: 'elong', title: 'ELONG.\n(mm)', w: 17 }, { key: 'qty', title: 'QTY', w: 12 }, { key: 'remarks', title: 'REMARKS', w: 44, align: 'L' },
    ];
    const rows = Array.from({ length: 22 }, (_, i) => ({ id: `T-${String(i + 1).padStart(2, '0')}`, type: '', strands: '', profile: '', length: '', live: '', jack: '', elong: '', qty: '', remarks: '' }));
    const d0 = sheet.detailBox(0, 'TYPICAL TENDON PROFILE (TEMPLATE)', '1:50');
    const span = level.grid.x.length > 1 ? level.grid.x[1].x - level.grid.x[0].x : 7500;
    const det0 = D.tendonProfile({ span, h: level.thickness });
    det0.draw(sheet.detailPen(d0, Math.max(25, Math.ceil(span / (d0.w - 14) / 5) * 5), det0.bbox));
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
        'GRID, COLUMNS, SLAB OUTLINE AND OPENINGS ARE SHOWN FOR REFERENCE ONLY, AS READ FROM THE STRUCTURAL DRAWINGS.',
      ],
      assumptions: ['TENDON LAYOUT NOT YET DESIGNED: SCHEDULE AND PROFILE LEFT BLANK BY INTENT.', ...levelAssumptions(model, level).slice(0, 3)],
      legend: [['CABLE', 'TENDON (TO BE ADDED)', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'hatch'], ['OPENING', 'OPENING', 'line']],
      detailsUsed: 3,
    };
  };
}

function coverSheet(model, sheets, meta) {
  return (sheet) => {
    const P = sheet.L.plan;
    const pp = sheet.pp;
    pp.text(P.x + 10, P.y + P.h - 16, (meta.project || '').toUpperCase(), { layer: 'TEXT-TITLE', h: 7, bold: true });
    pp.text(P.x + 10, P.y + P.h - 26, 'REINFORCEMENT AND PT CABLES SHOP DRAWINGS - DRAWING INDEX', { layer: 'TEXT-TITLE', h: 4 });
    pp.text(P.x + 10, P.y + P.h - 34, `${meta.company}  ·  ${meta.client ? 'CLIENT: ' + meta.client + '  ·  ' : ''}${meta.location || ''}  ·  REV ${meta.revision}  ·  ${meta.date}`, { layer: 'TITLE', h: 2.6 });
    const cols = [{ key: 'no', title: 'DRAWING No.', w: 40 }, { key: 'title', title: 'DRAWING TITLE', w: 205, align: 'L' }, { key: 'level', title: 'LEVEL', w: 110, align: 'L', max: 40 }, { key: 'block', title: 'BLOCK / XREF NAME', w: 150, align: 'L' }, { key: 'scale', title: 'SCALE', w: 36 }, { key: 'wt', title: 'REBAR (kg)', w: 40 }, { key: 'rev', title: 'REV', w: 20 }];
    const rows = sheets.map((s) => ({ no: s.drawingNo, title: s.title, level: s.level === 'ALL' ? 'ALL' : `${s.level} - ${s.levelName}`, block: s.blockName, scale: s.scale ? `1:${s.scale}` : 'NTS', wt: s.weight ? Math.round(s.weight).toLocaleString('en-US') : '-', rev: meta.revision }));
    const totalW = sheets.reduce((s, x) => s + (x.weight || 0), 0);
    sheet.table(P.x + 10, P.y + P.h - 42, cols, rows, { title: 'DRAWING INDEX / LIST OF SHEETS', rowH: 5, h: 2, headH: 6, titleH: 7, totals: `TOTAL SCHEDULED REINFORCEMENT (ALL LEVELS) ${Math.round(totalW).toLocaleString('en-US')} kg` });
    // level summary in the strip
    const d0 = sheet.detailBox(0, 'LEVELS READ FROM THE STRUCTURAL DRAWINGS', '');
    const lcols = [{ key: 'id', title: 'ID', w: 14 }, { key: 'name', title: 'LEVEL', w: 70, align: 'L', max: 34 }, { key: 'thk', title: 'THK', w: 16 }, { key: 'cols', title: 'COLS', w: 16 }, { key: 'op', title: 'OPEN.', w: 16 }, { key: 'vo', title: 'VOIDS', w: 16 }, { key: 'ub', title: 'U-REG.', w: 16 }, { key: 'area', title: 'AREA m²', w: d0.w - 6 - 164 }];
    sheet.table(d0.x + 3, d0.y + d0.h - 10, lcols, model.levels.map((l) => ({ id: l.id, name: l.name, thk: l.thickness, cols: l.columns.length, op: l.openings.length, vo: l.voids.length, ub: l.ubar.circles.length, area: Math.round(Math.abs(R.polygonArea(l.outline)) / 1e6) })), { headH: 5, rowH: 4, h: 1.6, maxRows: 24 });
    const d1 = sheet.detailBox(1, 'DEVELOPMENT / LAP LENGTHS APPLIED (mm)', '');
    const tcols = [{ key: 'dia', title: 'Ø', w: 16 }, { key: 'ld_bottom', title: 'ld BOT', w: 30 }, { key: 'ld_top', title: 'ld TOP', w: 30 }, { key: 'lap_bottom', title: 'LAP BOT', w: 32 }, { key: 'lap_top', title: 'LAP TOP', w: 32 }, { key: 'ldh', title: 'ldh HOOK', w: d1.w - 6 - 140 }];
    sheet.table(d1.x + 3, d1.y + d1.h - 10, tcols, R.lengthTable(model.spec), { headH: 5, rowH: 4, h: 1.6 });
    const d2 = sheet.detailBox(2, 'HOW TO USE THE BLOCKS / XREFS', '');
    const how = ['EACH SHEET IS A BLOCK NAMED AS LISTED; THE SAME NAME IS ALSO A STAND-ALONE DXF FOR XREF ATTACH.', 'INSERT OR XREF AT 0,0 SCALE 1, UNITS mm. PLAN GEOMETRY IS 1:1; THE FRAME IS SCALED BY THE SHEET SCALE.', 'LAYERS: REBAR-BOT / REBAR-TOP / REBAR-U / REBAR-TRIM / CALLOUT / SCHEDULE / NOTES / GRID / OUTLINE / COLUMN / OPENING / VOID / PT-ZONE / CABLE / FRAME / TITLE.', 'EXPLODE THE BLOCK TO EDIT; RE-RUN THE GENERATOR AFTER CHANGES TO THE STRUCTURAL DRAWINGS.'];
    how.forEach((h, i) => pp.mtext(d2.x + 4, d2.y + d2.h - 12 - i * 11, h, { layer: 'NOTES', h: 1.9, width: d2.w - 8 }));
    return {
      general: [
        `PACKAGE GENERATED FROM THE CONSULTANT'S COMBINED STRUCTURAL DRAWINGS: ${model.levels.length} SLAB LEVEL(S) READ.`,
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
    project: 'PROJECT NAME', client: '', location: '', prefix: 'ST-SD', revision: '00',
    date: new Date().toISOString().slice(0, 10), prepared: '', checked: '', approved: '', status: 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
    ...metaIn,
  };
  const jobs = [];
  for (const level of model.levels) {
    jobs.push({ level, def: SHEET_DEFS[0], draw: framingSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[1], draw: bottomSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[2], draw: topSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[3], draw: ubarSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[4], draw: voidsSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[5], draw: openingsSheet(model, level) });
    jobs.push({ level, def: SHEET_DEFS[6], draw: cablesSheet(model, level) });
  }
  const total = jobs.length + 1;
  const sheets = jobs.map((j, i) => buildSheet({ model, level: j.level, def: j.def, meta, index: i + 2, total, draw: j.draw }));
  const cover = buildSheet({ model, level: null, def: { key: 'cover', base: 'SHOP_DRAWINGS_COVER_INDEX', title: 'COVER SHEET / DRAWING INDEX', no: '000' }, meta, index: 1, total, draw: coverSheet(model, sheets, meta) });
  const all = [cover, ...sheets];

  // Package canvas: every sheet block, inserted side by side.
  const pkg = new Canvas();
  const perRow = 4;
  const gapX = 900 * 100, gapY = 650 * 100;
  all.forEach((s, i) => {
    for (const [name, def] of s.root.layers) if (!pkg.layers.has(name)) pkg.layers.set(name, def);
    pkg.blocks.set(s.blockName, s.root.blocks.get(s.blockName));
    const x = (i % perRow) * gapX, y = -Math.floor(i / perRow) * gapY;
    pkg.insert(s.blockName, x, y);
    pkg.text(x, y + 594 * s.scale + 1500, `${s.drawingNo}  ${s.title}${s.level !== 'ALL' ? `  (${s.level})` : ''}`, { layer: 'XREF', h: 1200 });
  });
  return { meta, sheets: all, pkg };
}
