/**
 * Design drawings in the office's own convention.
 *
 * Input: the office's reinforcement design plan (RFT drawing) as drawn by the
 * design team, plus the rules of the office's "General Details" sheet for PT /
 * flat slabs. Output: a coordinated sheet set (framing, bottom, top, punching)
 * in the same frame as the shop drawings, where
 *   - everything the designer drew is kept exactly (bars, call-outs, distribution
 *     dimensions, dots, mesh labels, camber notes, level tags), and
 *   - the reinforcement the General Details ask for is added on the plan at the
 *     places the details refer to, drawn with the SAME bar convention:
 *       one line on REO-TOP / REO-BOT (magenta hidden / green), the call-out
 *       "T10-200 (T)" over "L=2400" in style BW (isocp) h=150 parallel to the bar,
 *       the distribution width as a red dimension with arch ticks and a green
 *       number across the bars, and a yellow dot where the bar meets it.
 *   Every added bar carries a small "D#" reference to the detail it comes from.
 *
 * Details applied (numbers as on the General Details sheet):
 *   D1  slab edge with edge beam        T10-200 L-bar (T) 1200 into the slab (+ distribution T10-250 unless a top mesh exists)
 *   D2  slab edge at core / retaining wall   T12@200 U-bar (LB 1200, LC = t - cover, LA as plan); 10T12 (T&B) parallel only with spec.walls.parallelBars
 *   D3  varying slab thickness          500 lap at the step (note)
 *   D4  column drop / thickened zone    T12@250 (B) extra reinforcement both ways inside the zone, 50 dia beyond it
 *   D5  core wall and slab corners      3T16-200 diagonals 2 m long T&B (3T12 at re-entrant slab corners)
 *   D7  MEP voids                       longitudinal T&B each side, transverse U-bars, diagonals, per the void size table
 *   D12 punching                        PS tags "rows-legs-dia" per column with the schedule (preliminary)
 *   Anchorage-dependent details (D6 slab edge at live anchors, bursting spirals, pan-box trimmers) need the
 *   tendon layout and are left out on purpose; site-specific details (D8-D11) apply only where drawn.
 */
import { extractModel, flatten, closedPolys } from './extract.mjs';
import { bbox, dist, polygonArea, pointInPolygon, centroid, rectPolygon, asAxisRect, cleanPolygon, ceilTo, distToPolygon, clipSegmentToPolygon } from './geometry.mjs';
import * as R from './rebar.mjs';
import * as D from './details.mjs';
import { buildSheet, drawBase, commonNotes, levelAssumptions, gridRef, fmtMM, packSheets, ramCablesSheet, beamsSheet } from './sheets.mjs';
import { overrideColumns } from './punching.mjs';
import * as RC from './ram-concept.mjs';
/** The office's DIM100: 250 text, 150 oblique ticks, green number, text above the line, and no extension lines at all (dimse1/dimse2 on, dimexe 0). */
export const DIM100 = { txt: 250, asz: 150, tsz: 150, exo: 0, exe: 0, gap: 70, tad: 1, clrt: 3, clrd: 256, clre: 256, dec: 0, txsty: 'BW', se1: true, se2: true };

// ------------------------------------------------------------------ office convention
export const OFFICE_LAYERS = {
  'REO-TOP': { color: 6, ltype: 'HIDDEN', lw: 20 }, // reinforcement always 0.20 mm: it stands out among the plan lines
  'REO-BOT': { color: 3, ltype: 'CONTINUOUS', lw: 20 },
  'REO-TXT': { color: 7, ltype: 'CONTINUOUS' },
  'S-TEXT': { color: 7, ltype: 'CONTINUOUS' },
  diamension: { color: 1, ltype: 'CONTINUOUS' },
  DOTS: { color: 2, ltype: 'CONTINUOUS' },
  '9_TEXT': { color: 4, ltype: 'CONTINUOUS' },
  'TEXT-4': { color: 7, ltype: 'CONTINUOUS' },
  LV: { color: 1, ltype: 'CONTINUOUS' },
  'DETAIL-REF': { color: 5, ltype: 'CONTINUOUS' },
  'PS-TAG': { color: 1, ltype: 'CONTINUOUS' },
  'PS-ROW': { color: 8, ltype: 'CONTINUOUS' },
  'REBAR-PUNCH': { color: 6, ltype: 'CONTINUOUS', lw: 20 },
  's-hatch': { color: 8, ltype: 'CONTINUOUS' }, // the office's column fill: solid grey
};
export const OFFICE_TEXT_STYLE = { name: 'BW', font: 'isocp.shx', widthFactor: 0.8 };
const PERIM_DIM_IN = 350; // the perimeter distribution dimension sits this far inside the slab edge (nothing is drawn outside the slab)
const CALL_H = 150, LEN_H = 150, DIM_H = 250, DIM_TICK = 150, DIM_EXO = 50, DIM_EXE = 100, DOT_R = 33;
const BAR_W = 20; // every reinforcement bar is a polyline of constant width 20 (model mm)
/** A bar on the plan: a polyline of width BAR_W. */
const barLine = (pl, pts, layer) => pl.pline(pts, { layer, width: BAR_W });
/**
 * The side a bar's legs / hooks are drawn on, by the engineering convention: a bottom bar's legs point up (a
 * horizontal bar) / right (a vertical bar), a top bar's legs point down / left. Returns the unit normal.
 */
function legSide(u, face) {
  let n = { x: -u.y, y: u.x };
  if (n.y < -1e-9 || (Math.abs(n.y) <= 1e-9 && n.x < 0)) n = { x: -n.x, y: -n.y }; // "up / right"
  return face === 'B' ? n : { x: -n.x, y: -n.y };
}

export const DETAILS = {
  D1: 'TYPICAL SLAB EDGE DETAIL WITH EDGE BEAM',
  D2: 'TYPICAL SLAB EDGE DETAIL AT ANY CORE OR RETAINING WALLS',
  D3: 'TYPICAL DETAIL AT VARYING SLAB THICKNESS',
  D4: 'TYPICAL COLUMN DROP DETAIL',
  D5: 'TYPICAL SLAB DETAIL AT CORE WALL AND SLAB CORNERS',
  D6: 'TYPICAL SLAB EDGE REINFORCEMENT DETAIL (U.N.O.) - FREE EDGE U-BARS',
  D7: 'TYPICAL MEP VOID DETAIL',
  D8: 'TYPICAL POUR STRIP DETAIL (PT DETAILS 3)',
  D9: 'TYPICAL BLOCKWORK SUPPORT BEAM DETAIL THROUGH VOID',
  D12: 'TYPICAL PUNCHING DETAIL (PS TYPES: ROWS - LEGS - BAR)',
};

/** Void reinforcement table of detail 7 (size of void in metres). */
export const VOID_TABLE = [
  { max: 0.5, long: { n: 1, dia: 12, s: 150 }, u: { dia: 10, s: 150 }, diag: 12 },
  { max: 1.0, long: { n: 2, dia: 12, s: 150 }, u: { dia: 12, s: 150 }, diag: 12 },
  { max: 2.5, long: { n: 3, dia: 16, s: 150 }, u: { dia: 12, s: 150 }, diag: 16 },
  { max: 4.0, long: { n: 4, dia: 20, s: 150 }, u: { dia: 16, s: 150 }, diag: 16 },
  { max: 5.5, long: { n: 4, dia: 20, s: 150 }, u: { dia: 16, s: 100 }, diag: 16 },
];

const textOf = (e) => (e.text || '').trim();
const mid = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
const unit = (a, b) => { const L = dist(a, b) || 1; return { x: (b.x - a.x) / L, y: (b.y - a.y) / L }; };
const perp = (u) => ({ x: -u.y, y: u.x });
const add = (p, u, k) => ({ x: p.x + u.x * k, y: p.y + u.y * k });
const segMid = (s) => mid(s.a, s.b);
const near = (p, q, r) => dist(p, q) < r;

/** Distance from a point to a segment. */
function distToSeg(p, a, b) {
  const L2 = (b.x - a.x) ** 2 + (b.y - a.y) ** 2;
  if (L2 < 1e-9) return dist(p, a);
  const t = Math.max(0, Math.min(1, ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / L2));
  return dist(p, { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) });
}

// ------------------------------------------------------------------ extraction
/**
 * Read the office design plan. Every slab outline becomes a PART (the office
 * splits its plans the same way). Returns the extractModel result with, per
 * level, the office-specific data: walls, thickness zones, the designer's own
 * reinforcement (kept verbatim), mesh labels, camber notes and level tags.
 */
export function extractDesign(dxf, options = {}) {
  const model = extractModel(dxf, options);
  if (options.spec?.edgeBeams === false) for (const l of model.levels) l.noEdgeBeams = true;
  const spec0 = model.spec;
  const k = { mm: 1, m: 1000, cm: 10 }[model.source.units] || 1;
  const raw = flatten(dxf).map((e) => (k === 1 ? e : scaleEnt(e, k)));
  const texts = raw.filter((e) => (e.type === 'TEXT' || e.type === 'MTEXT') && textOf(e));
  const A = (level, text) => model.assumptions.push({ level: level.id, text });

  // slab thickness from RC tags ("RC230") if the notes did not say
  const rcTags = texts.filter((t) => /^RC\s*\d{3}$/i.test(textOf(t))).map((t) => ({ x: t.x, y: t.y, thickness: parseInt(textOf(t).replace(/\D/g, ''), 10) }));

  model.levels.forEach((level, li) => {
    const outline = level.outline;
    const inPart = (p) => pointInPolygon(p, outline) || distToPolygon(p, outline) < 1500;
    const baseName = (options.levelNames && options.levelNames[0]) || model.levels[0].name.replace(/\s*-\s*PART.*$/i, '');
    const oldName = level.name;
    level.name = `${baseName} - PART ${String(li + 1).padStart(2, '0')}`;
    model.findings = model.findings.map((f) => f.replace(`${level.id} ${oldName}:`, `${level.id} ${level.name}:`));
    for (const a of model.assumptions) if (a.level === level.id) a.text = a.text.replace(oldName, level.name);
    // grid labels: a bubble text can be picked twice when two lines are close; give the second the next unused label
    for (const axis of ['x', 'y']) {
      const seen = new Set();
      for (const g of level.grid[axis]) { if (g.label && seen.has(g.label)) g.label = nextLabel(g.label, seen); seen.add(g.label); }
    }
    level.partIndex = li;

    // thickness: RC tag inside the part wins over the vote / assumption
    const tag = rcTags.find((t) => pointInPolygon(t, outline));
    if (tag) { level.thickness = tag.thickness; level.thicknessSource = 'RC tag on the plan'; }

    // walls: long or non-rectangular closed shapes on the column layer, and blade-shaped "columns"
    const walls = [];
    for (const e of raw.filter((x) => /COL/i.test(x.layer + ' ' + (x.fromBlock || '')) && (x.type === 'LWPOLYLINE' || x.type === 'HATCH'))) {
      for (const p0 of closedPolys(e)) {
        const p = cleanPolygon(p0);
        if (p.length < 4) continue;
        const b = bbox(p);
        const rect = asAxisRect(p, 5);
        const long = Math.max(b.w, b.h) >= 1500 && Math.min(b.w, b.h) <= 600;
        const big = Math.max(b.w, b.h) > 3000 && Math.abs(polygonArea(p)) < 0.5 * b.w * b.h + 1;
        if (!(long || big || (!rect && Math.abs(polygonArea(p)) > 0.3e6))) continue;
        if (!inPart({ x: b.cx, y: b.cy })) continue;
        if (walls.some((w) => near(centroid(w.polygon), centroid(p), 100))) continue;
        const along = b.w >= b.h ? 'x' : 'y';
        walls.push({ polygon: polygonArea(p) < 0 ? [...p].reverse() : p, cx: b.cx, cy: b.cy, w: b.w, h: b.h, t: Math.min(b.w, b.h), length: Math.max(b.w, b.h), a: along === 'x' ? { x: b.minX, y: b.cy } : { x: b.cx, y: b.minY }, b: along === 'x' ? { x: b.maxX, y: b.cy } : { x: b.cx, y: b.maxY } });
      }
    }
    level.columns = level.columns.filter((c) => {
      const blade = c.shape !== 'circle' && Math.max(c.w, c.h) >= 1500 && Math.max(c.w, c.h) / Math.min(c.w, c.h) >= 4;
      if (blade && !walls.some((w) => near({ x: w.cx, y: w.cy }, { x: c.cx, y: c.cy }, 100))) walls.push({ polygon: rectPolygon({ x: c.cx - c.w / 2, y: c.cy - c.h / 2, w: c.w, h: c.h }), cx: c.cx, cy: c.cy, w: c.w, h: c.h, t: Math.min(c.w, c.h), length: Math.max(c.w, c.h), a: c.w >= c.h ? { x: c.cx - c.w / 2, y: c.cy } : { x: c.cx, y: c.cy - c.h / 2 }, b: c.w >= c.h ? { x: c.cx + c.w / 2, y: c.cy } : { x: c.cx, y: c.cy + c.h / 2 } });
      return !blade;
    });
    walls.forEach((w, i) => { w.id = `W${i + 1}`; });
    level.walls = walls;
    // a wall outline small enough to pass as a column is not a column
    level.columns = level.columns.filter((c) => !walls.some((w) => {
      const wb = bbox(w.polygon);
      const ox = Math.max(0, Math.min(c.cx + c.w / 2, wb.maxX) - Math.max(c.cx - c.w / 2, wb.minX)), oy = Math.max(0, Math.min(c.cy + c.h / 2, wb.maxY) - Math.max(c.cy - c.h / 2, wb.minY));
      return near({ x: w.cx, y: w.cy }, { x: c.cx, y: c.cy }, 200) || (ox * oy > 0.5 * c.w * c.h && Math.max(c.w, c.h) >= 1000);
    }));
    level.columns.forEach((c, i) => { if (!c.id || /^C\d+$/.test(c.id)) return; });

    // thickness zones: a nested outline with a 3-digit thickness written inside it (e.g. "280")
    const thickZones = [...(level.thickZones || [])];
    level.sunken = (level.sunken || []).filter((z) => {
      if (!z.fromOutline) return true;
      const inside = texts.filter((t) => /^\d{3}$/.test(textOf(t)) && pointInPolygon(t, z.polygon));
      if (!inside.length) return true;
      thickZones.push({ polygon: z.polygon, thickness: parseInt(textOf(inside[0]), 10), kind: 'thick' });
      return false;
    });
    thickZones.forEach((z, i) => { z.id = `D${i + 1}`; });
    level.thickZones = thickZones;
    model.assumptions = model.assumptions.filter((a) => !(a.level === level.id && /stepped \(sunken \/ raised\) zone/.test(a.text) && !level.sunken.length));

    // local RC thickness markers ("RC" + "200" at stairs)
    level.rcTags = texts.filter((t) => /^\d{3}$/.test(textOf(t)) && pointInPolygon(t, outline) && !thickZones.some((z) => pointInPolygon(t, z.polygon)))
      .filter((t) => texts.some((u) => /^RC$/i.test(textOf(u)) && near(u, t, 700)))
      .map((t) => ({ x: t.x, y: t.y, thickness: parseInt(textOf(t), 10) }));

    // level tags "T.O.C" + "+12.35"
    level.levelTags = level.levelTags || [];
    for (const t of texts.filter((x) => /^T\.?O\.?[SC]\.?$/i.test(textOf(x)) && inPart(x))) {
      const v = texts.filter((u) => /^[+-]?\d+(\.\d+)?$/.test(textOf(u)) && near(u, t, 1200)).sort((p, q) => dist(p, t) - dist(q, t))[0];
      if (v) level.levelTags.push({ x: v.x, y: v.y, label: textOf(t).toUpperCase(), value: textOf(v) });
    }
    if (level.levelTags.length && !level.tos) level.tos = level.levelTags[0].value;

    // designer's notes: camber, mesh labels
    const seen = new Set();
    level.camber = texts.filter((t) => /CAMBER/i.test(textOf(t)) && inPart(t)).filter((t) => { const key = `${Math.round(t.x)}|${Math.round(t.y)}`; if (seen.has(key)) return false; seen.add(key); return true; }).map((t) => ({ x: t.x, y: t.y, text: textOf(t).toUpperCase() }));
    const meshTexts = texts.filter((t) => /MESH|TWO WAY|BOTTOM\s*&\s*TOP/i.test(textOf(t)) && inPart(t));
    const groups = [];
    for (const t of meshTexts) {
      const g = groups.find((x) => near(x, t, 1500));
      if (g) g.lines.push(t); else groups.push({ x: t.x, y: t.y, lines: [t] });
    }
    level.meshLabels = groups.map((g) => ({ x: g.x, y: g.y, lines: g.lines.sort((p, q) => q.y - p.y).map(textOf) }));
    const meshSpec = level.meshLabels.map((m) => m.lines.join(' ')).find((s) => /T\d+@\d+/i.test(s));
    level.meshSpec = meshSpec ? meshSpec.match(/T(\d+)@(\d+)/i).slice(1, 3).map(Number) : null;
    level.topMesh = !!(meshSpec && /TOP/i.test(meshSpec));
    if (options.spec?.mesh === 'both' || options.spec?.mesh === 'bottom') level.topMesh = options.spec.mesh === 'both'; // the run option decides over the plan label

    // edge beams: a line on a beam layer running along the slab edge
    level.beams = raw.filter((e) => e.type === 'LINE' && /BEAM/i.test(e.layer) && (inPart({ x: e.x, y: e.y }) || inPart({ x: e.x2, y: e.y2 }))).map((e) => ({ a: { x: e.x, y: e.y }, b: { x: e.x2, y: e.y2 } }));
    markBeams(level, spec0, A); // band beams (long thickened strips) take the beam rule
    level.edges = slabEdges(level);

    // the designer's own reinforcement, kept verbatim
    const inWin = (p) => inPart(p);
    const barLayer = (l) => /^REO-(TOP|BOT)$|S-TOP REINF|^REO-|REINF/i.test(l);
    const segs = [];
    for (const e of raw) {
      if (!barLayer(e.layer)) continue;
      if (e.type === 'LINE') segs.push({ a: { x: e.x, y: e.y }, b: { x: e.x2, y: e.y2 }, layer: e.layer });
      else if (e.type === 'LWPOLYLINE') for (let i = 0; i + 1 < e.pts.length; i++) segs.push({ a: e.pts[i], b: e.pts[i + 1], layer: e.layer });
    }
    const lines = segs.filter((s) => dist(s.a, s.b) > 200 && inWin(segMid(s)));
    for (const l of lines) if (dist(l.a, l.b) <= 350) l.tick = true; // the designer's short leg symbols at bar ends, not bars
    const callouts = texts.filter((t) => /REO|S-TEXT|TXT/i.test(t.layer) && /T\d+|L\s*=|\(T\)|\(B\)|T&B/i.test(textOf(t)) && inWin(t))
      .map((t) => ({ x: t.x, y: t.y, text: textOf(t), h: t.height || CALL_H, rot: t.rotation || 0, halign: t.halign || 0, widthFactor: t.sx && t.sx < 2 ? t.sx : undefined, style: t.style }));
    const faceOfText = (s) => (/\(B\)|BOT/i.test(s) ? 'B' : /T\s*&\s*B|T&B/i.test(s) ? 'TB' : /\(T\)|TOP/i.test(s) ? 'T' : null);
    for (const c of callouts) c.face = faceOfText(c.text);
    for (const c of callouts.filter((x) => !x.face)) {
      const host = callouts.filter((x) => x.face && near(x, c, 700)).sort((p, q) => dist(p, c) - dist(q, c))[0];
      c.face = host ? host.face : 'T';
    }
    for (const l of lines) {
      const m = segMid(l);
      const host = callouts.filter((c) => c.face && (distToSeg(c, l.a, l.b) < 500 || near(c, m, 900))).sort((p, q) => distToSeg(p, l.a, l.b) - distToSeg(q, l.a, l.b))[0];
      l.face = host ? host.face : /BOT/i.test(l.layer) ? 'B' : 'T';
    }
    // office rule: a top bar ending at the outer slab edge or at an opening ends in a U (500 bottom leg)
    // office rule: a top bar ending at the outer slab edge ends in a U (500 bottom leg), or in an L where the edge carries a beam; at an opening always a U
    const atBoundary = (p) => ((level.openings || []).some((o) => distToPolygon(p, R.regionPolygon(o)) < 300) ? 'U' : distToPolygon(p, outline) < spec0.cover + 300 ? R.edgeEndAt(level, spec0, p).type : false);
    for (const l of lines) if (l.face !== 'B' && !l.tick) l.uEnd = { start: atBoundary(l.a), end: atBoundary(l.b) };
    const dims = raw.filter((e) => e.type === 'DIMENSION' && inWin(e)).map((e) => ({ ...e }));
    const dots = raw.filter((e) => e.type === 'INSERT' && /^DOT/i.test(e.name || '') && inWin(e)).map((e) => ({ x: e.x, y: e.y }));
    const faceNearLine = (p, r) => { const l = lines.filter((s) => distToSeg(p, s.a, s.b) < r).sort((s1, s2) => distToSeg(p, s1.a, s1.b) - distToSeg(p, s2.a, s2.b))[0]; return l ? l.face : 'T'; };
    for (const d of dims) d.face = faceNearLine({ x: d.x, y: d.y }, 1500);
    for (const d of dots) d.face = faceNearLine(d, 300);
    level.existing = { lines, callouts, dims, dots };
    // the designer's wall top bars: "T10-150 (T)" + "L=3000" near a wall face; LA of the U-bars follows them
    level.wallBarLengths = callouts.filter((c) => /^L\s*=\s*\d+/i.test(c.text)).map((c) => ({ x: c.x, y: c.y, L: parseInt(c.text.replace(/\D/g, ''), 10) }));

    model.findings.push(`${level.id} ${level.name}: ${walls.length} walls, ${thickZones.length} thickness zones${thickZones.length ? ` (${[...new Set(thickZones.map((z) => z.thickness))].join('/')} mm)` : ''}, ${level.edges.filter((e) => e.beam).length} of ${level.edges.length} slab edges with an edge beam, designer's reinforcement: ${lines.length} bars, ${callouts.length} call-outs, ${dims.length} distribution dimensions, ${dots.length} dots; mesh ${meshSpec || 'not labelled'}.`);
    if (!tag) A(level, `Slab thickness of ${level.name} not tagged on the plan: ${level.thickness} mm used.`);
    if (!walls.length) A(level, `No walls read in ${level.name}: details 2 and 5 (core walls) not applied.`);
  });
  markJoints(model, spec0.cover);
  const notForDesign = /Top bars over columns not specified|Edge U-bars not specified|Opening trimmers not specified|Void trimmers not specified|Stock bar length|No plan title found near slab/;
  model.assumptions = model.assumptions.filter((a) => !notForDesign.test(a.text) && !(a.text.startsWith('Slab thickness not stated') && model.levels.some((l) => l.id === a.level && l.thicknessSource)));
  model.design = { units: model.source.units };
  return model;
}

/**
 * A RAM Concept model (from ramToModel) prepared for the design package: the bands designed in
 * RAM become the designer's reinforcement, drawn in the office convention (bar line, call-out
 * "T16-150 (T)" + "L=...", distribution DIMENSION, dot); walls become polygons; slab thicknesses
 * are tagged on the plan; then the General Details rules are added on top exactly as for an RFT plan.
 */
/** Polygon clipped to the band lo <= axis <= hi (Sutherland-Hodgman against the two half-planes). */
function clipPolyBand(poly, axis, lo, hi) {
  const clip = (pts, keep, at) => {
    const out = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i], b = pts[(i + 1) % pts.length];
      const ia = keep(a), ib = keep(b);
      if (ia) out.push(a);
      if (ia !== ib) { const t = (at - a[axis]) / (b[axis] - a[axis]); out.push({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t }); }
    }
    return out;
  };
  let pts = clip(poly, (q) => q[axis] >= lo, lo);
  if (pts.length) pts = clip(pts, (q) => q[axis] <= hi, hi);
  return pts.length >= 3 ? pts : null;
}

/**
 * A slab body too big for one sheet is split into PARTS along its longer side, as the office splits its plans
 * (`spec.partMax`, 60 m, with `spec.partOverlap` 600 mm of overlap so that the cut reads as a drawing joint):
 * columns, bands, stud rails and punching checks go to the part that holds their centre, walls / openings / zones /
 * tendons are clipped to each part.
 */
function splitLevels(model, spec) {
  const partMax = spec.partMax || 60000, ov = spec.partOverlap ?? 600;
  const out = [];
  for (const level of model.levels) {
    const b = bbox(level.outline);
    const axis = b.w >= b.h ? 'x' : 'y';
    const size = axis === 'x' ? b.w : b.h;
    const n = Math.ceil(size / partMax);
    if (n < 2) { out.push(level); continue; }
    const lo0 = axis === 'x' ? b.minX : b.minY;
    const step = size / n;
    for (let k = 0; k < n; k++) {
      const lo = lo0 + k * step, hi = lo0 + (k + 1) * step;
      const band = (q) => q[axis] >= lo - (k ? 0 : 1) && q[axis] < hi + (k === n - 1 ? 1 : 0);
      const outline = clipPolyBand(level.outline, axis, lo - (k ? ov : 0), hi + (k < n - 1 ? ov : 0));
      if (!outline) continue;
      const inPart = (q) => pointInPolygon(q, outline);
      const clipPolys = (list) => list.map((o) => ({ ...o, polygon: clipPolyBand(o.polygon, axis, lo - (k ? ov : 0), hi + (k < n - 1 ? ov : 0)) })).filter((o) => o.polygon);
      const ram = level.ram || {};
      out.push({
        ...level,
        id: level.customId ? `${level.id}${'ABCDEFGHIJ'[k] || k + 1}` : `L${String(out.length + 1).padStart(2, '0')}`, name: `${level.name} - PART ${k + 1}`, partOf: level.id, partCut: { axis, lo, hi },
        outline, bbox: bbox(outline),
        // the grid keeps the body's labels; only the lines that cross this part are drawn, trimmed to the part
        grid: level.grid ? {
          ...level.grid,
          x: (level.grid.x || []).filter((g) => axis === 'y' || (g.x >= lo - ov - 1500 && g.x <= hi + ov + 1500)).map((g) => (axis === 'y' ? { ...g, y1: Math.max(g.y1, lo - ov), y2: Math.min(g.y2, hi + ov) } : g)),
          y: (level.grid.y || []).filter((g) => axis === 'x' || (g.y >= lo - ov - 1500 && g.y <= hi + ov + 1500)).map((g) => (axis === 'x' ? { ...g, x1: Math.max(g.x1, lo - ov), x2: Math.min(g.x2, hi + ov) } : g)),
        } : level.grid,
        columns: (level.columns || []).filter((c) => band({ x: c.cx, y: c.cy })),
        walls: (level.walls || []).flatMap((w) => (w.polygon ? [w].filter(() => band(centroid(w.polygon))) : clipSegmentToPolygon(w.a, w.b, outline).filter(([a, bb]) => dist(a, bb) > 50).map(([a, bb]) => ({ ...w, a, b: bb })))),
        // beams are clipped to the part along their axis (new objects: each part decides for itself whether a beam is interior)
        beams: (level.beams || []).flatMap((bm) => clipSegmentToPolygon(bm.a, bm.b, outline).filter(([a, bb]) => dist(a, bb) > 500).map(([a, bb]) => { const u = unit(a, bb), n = perp(u), t = bm.t || 300; return { ...bm, a, b: bb, interior: undefined, polygon: bm.polygon ? [add(a, n, t / 2), add(bb, n, t / 2), add(bb, n, -t / 2), add(a, n, -t / 2)] : undefined }; })),
        openings: clipPolys((level.openings || []).map((o) => ({ ...o, kind: 'polygon', polygon: R.regionPolygon(o) }))),
        thickZones: clipPolys(level.thickZones || []),
        pourStrips: clipPolys(level.pourStrips || []).map((ps) => { const b = bbox(ps.polygon); return { ...ps, width: Math.min(b.w, b.h), length: Math.max(b.w, b.h) }; }),
        ram: {
          ...ram,
          bands: (ram.bands || []).filter((bd) => band(mid(bd.p0, bd.p1))),
          // a tendon running through the cut is drawn up to it on each part (cut end: no anchor, 'CONT.' on the sheet)
          tendons: (ram.tendons || []).filter((t) => (t.pts || []).some(inPart)).map((t) => RC.clipTendon(t, outline, 300)).filter(Boolean),
          shear: (ram.shear || []).filter((sr) => band(mid(sr.a, sr.b))),
          punching: (ram.punching || []).filter((pc) => band(pc.p)),
          ssr: (ram.ssr || []).filter((st) => band(st.loc)),
        },
      });
    }
    model.assumptions.push({ level: level.id, text: `${level.name} (${Math.round(b.w / 1000)} x ${Math.round(b.h / 1000)} m) is drawn in ${n} parts along its ${axis === 'x' ? 'length' : 'height'} (the office splits its plans the same way); the cut between the parts is a drawing joint, not a slab edge.` });
  }
  model.levels = out;
}

/**
 * Parts of one plan overlap where the office split it: an edge of one part that runs inside another part is a drawing
 * joint, not a slab edge (no perimeter bars, no U ends there). Marks `e.joint`, sets `level.jointEdges`.
 */
function markJoints(model, cover) {
  for (const level of model.levels) {
    // (a slab at another top-of-concrete level is a separate slab: its shared boundary is a step, a free edge, not a joint)
    const others = model.levels.filter((o) => o !== level && (o.toc ?? 0) === (level.toc ?? 0));
    let joints = 0;
    for (const e of level.edges || []) {
      const m = mid(e.a, e.b);
      const q1 = add(m, unit(e.a, e.b), Math.min(300, dist(e.a, e.b) / 3)), q2 = add(m, unit(e.b, e.a), Math.min(300, dist(e.a, e.b) / 3));
      e.joint = others.some((o) => [m, q1, q2].every((q) => pointInPolygon(q, o.outline) || distToPolygon(q, o.outline) < 60));
      if (e.joint) { e.beam = false; joints++; }
    }
    if (!joints) continue;
    level.jointEdges = level.edges.filter((e) => e.joint);
    const jl = level.jointEdges.reduce((t, e) => t + dist(e.a, e.b), 0);
    model.findings.push(`${level.id} ${level.name}: ${joints} edges (${Math.round(jl / 1000)} m) are drawing joints with the neighbouring part, not slab edges: no perimeter bars or U ends there.`);
    const atJoint = (p) => level.jointEdges.some((e) => distToSeg(p, e.a, e.b) < cover + 300);
    for (const l of [...(level.existing?.lines || []), ...(level.existing?.items || [])]) if (l.uEnd) for (const k of ['start', 'end']) { const p = k === 'start' ? l.a : l.b; if (l.uEnd[k] && atJoint(p)) l.uEnd[k] = false; }
  }
}

export function prepareRamDesign(model, options = {}) {
  const wallT = options.wallThickness || 250;
  const spec = model.spec;
  splitLevels(model, { ...spec, ...(options.spec || {}) });
  // the office rules need their full parameter sets (perimeter U / L bars, column bars, mesh at thickness changes)
  // (the office rules, not the RAM file's G.A. assumptions; the user's config overrides them)
  for (const key of ['uEdge', 'topColumns', 'thicknessMesh', 'openings', 'punching', 'drops']) spec[key] = { ...R.DEFAULT_SPEC[key], ...(options.spec?.[key] || {}) };
  // the office reinforcement defaults from the settings: bottom mesh, top mesh (both-faces option), column bars, drop bars
  if (options.spec?.bottom) spec.bottom = { ...(spec.bottom || R.DEFAULT_SPEC.bottom), ...options.spec.bottom };
  if (options.spec?.topMesh) spec.topMesh = { ...(spec.bottom || R.DEFAULT_SPEC.bottom), ...options.spec.topMesh };
  const A = (level, text) => model.assumptions.push({ level: level.id, text });
  model.assumptions = model.assumptions.filter((a) => !/office standard reinforcement .* ADDITIONAL reinforcement/i.test(a.text));
  const baseName = options.levelName || (model.levels[0]?.name || 'SLAB').replace(/\s*-\s*PART.*$/i, '');
  const tocs = [...new Set(model.levels.map((l) => l.toc ?? 0))];
  if (tocs.length > 1) model.assumptions.push({ level: model.levels[0].id, text: `${baseName} has ${tocs.length} top-of-concrete levels (${tocs.map((t) => (t >= 0 ? '+' : '') + Math.round(t)).join(' / ')} mm): each is drawn as a separate slab (office rule); the step between them is a free edge of both slabs (perimeter U-bars, bars stopped with a U, no bar runs across the step).` });
  model.levels.forEach((level, li) => {
    const outline = level.outline;
    level.partIndex = li;
    if (model.levels.length > 1) level.name = `${baseName} - PART ${String(li + 1).padStart(2, '0')}${tocs.length > 1 && level.toc ? ` (T.O.C ${level.toc > 0 ? '+' : ''}${Math.round(level.toc)})` : ''}`;
    level.thicknessSource = 'RAM model';
    // walls: RAM line supports are axes; give them a body so the wall details (D2 / D5) and the lined-opening rule can see them
    level.walls = mergeWallSegments((level.walls || []).filter((w) => !w.polygon)).concat((level.walls || []).filter((w) => w.polygon)).map((w) => {
      if (w.polygon) return w;
      const u = unit(w.a, w.b), n = perp(u), t = w.t || wallT;
      return { ...w, t, assumedT: !w.t, length: dist(w.a, w.b), polygon: [add(w.a, n, t / 2), add(w.b, n, t / 2), add(w.b, n, -t / 2), add(w.a, n, -t / 2)] };
    });
    // blade "columns" (a core wall modelled as a long rectangular column) are walls for the drawing
    // (a 500 x 1500 or 500 x 2200 is still a column with its top bars; only a real blade, 2.5 m or longer and 4 x its width, is a wall)
    const bladeMin = options.bladeLength || 2500;
    const blades = (level.columns || []).filter((c) => c.shape !== 'circle' && Math.max(c.w, c.h) >= bladeMin && Math.max(c.w, c.h) / Math.min(c.w, c.h) >= 4 && !(c.angle % 90));
    if (blades.length) {
      level.columns = level.columns.filter((c) => !blades.includes(c));
      for (const c of blades) level.walls.push({ id: c.id, polygon: rectPolygon({ x: c.cx - c.w / 2, y: c.cy - c.h / 2, w: c.w, h: c.h }), t: Math.min(c.w, c.h), length: Math.max(c.w, c.h), a: c.w >= c.h ? { x: c.cx - c.w / 2, y: c.cy } : { x: c.cx, y: c.cy - c.h / 2 }, b: c.w >= c.h ? { x: c.cx + c.w / 2, y: c.cy } : { x: c.cx, y: c.cy + c.h / 2 }, blade: true });
      A(level, `${blades.length} long rectangular columns of ${level.name} (${blades.map((c) => `${c.id} ${Math.round(c.w)}x${Math.round(c.h)}`).slice(0, 6).join(', ')}${blades.length > 6 ? ', ...' : ''}) are drawn as walls: wall U-bars along their faces, no column top bars or punching tags.`);
    }
    for (const w of level.walls) { const b = bbox(w.polygon); w.cx = w.cx ?? b.cx; w.cy = w.cy ?? b.cy; w.w = w.w ?? b.w; w.h = w.h ?? b.h; }
    level.walls.forEach((w, i) => { if (!w.id) w.id = `W${i + 1}`; });
    level.beams = level.beams || [];
    markBeams(level, spec, A);
    level.edges = slabEdges(level);
    // thickness tags: the slab thickness once, each thickened zone inside it
    const c0 = centroid(outline);
    const inside = pointInPolygon(c0, outline) ? c0 : (() => { const b = bbox(outline); return { x: b.minX + 1500, y: b.maxY - 1500 }; })();
    // the slab thickness once, away from any column; the thickened zones carry their own THK labels
    const tagAt = (() => { const cols = level.columns || []; for (const cand of [inside, { x: inside.x + 1500, y: inside.y + 1500 }, { x: inside.x - 1500, y: inside.y - 1500 }, { x: inside.x + 1500, y: inside.y - 1500 }]) if (!cols.some((c) => Math.abs(c.cx - cand.x) < 900 && Math.abs(c.cy - cand.y) < 900) && !(level.thickZones || []).some((z) => pointInPolygon(cand, z.polygon))) return cand; return inside; })();
    level.rcTags = [{ x: tagAt.x, y: tagAt.y, thickness: level.thickness }];
    level.levelTags = level.tos != null ? [{ x: inside.x, y: inside.y - 400, label: 'T.O.C', value: String(level.tos) }] : [];
    level.camber = level.camber || [];
    level.wallBarLengths = [];
    // mesh: RAM designs the bands, not the mesh; the mesh of the specification is written in the office box
    const mesh = spec.bottom || R.DEFAULT_SPEC.bottom;
    level.meshSpec = [mesh.dia, mesh.spacing];
    // the slab mesh option: a bottom mesh only (default) or a mesh on both faces (spec.mesh = 'both'); the top mesh
    // takes its own diameter / spacing from the settings (spec.topMesh) or the bottom mesh's
    level.meshFaces = (options.spec?.mesh || spec.mesh) === 'both' ? 'both' : 'bottom';
    level.topMesh = level.meshFaces === 'both';
    const tmesh = spec.topMesh || mesh;
    level.topMeshSpec = [tmesh.dia, tmesh.spacing];
    const sameMesh = tmesh.dia === mesh.dia && tmesh.spacing === mesh.spacing;
    const b0 = bbox(outline);
    level.meshLabels = [{ x: b0.minX + 600, y: b0.maxY - 700, lines: level.topMesh && !sameMesh ? [`BOTTOM MESH T${mesh.dia}@${mesh.spacing}`, `TOP MESH T${tmesh.dia}@${tmesh.spacing}`, 'TWO WAY'] : [`MESH T${mesh.dia}@${mesh.spacing}`, level.topMesh ? 'TOP & BOTTOM TWO WAY' : 'BOTTOM TWO WAY'] }];
    // designed bands → office items
    const atBoundary = (p) => ((level.openings || []).some((o) => distToPolygon(p, R.regionPolygon(o)) < 300) ? 'U' : distToPolygon(p, outline) < (spec.cover || 25) + 300 ? R.edgeEndAt(level, spec, p).type : false);
    const items = [];
    let tiny = 0;
    // which RAM bands are drawn: 'all' (default), 'user' (only the engineer's own bars) or 'none' (office rules only)
    const take = options.spec?.ramBands || spec.ramBands || 'all';
    const bandsIn = (level.ram?.bands || []).filter((b) => take === 'all' || (take === 'user' && b.designedBy !== 'program'));
    const skipped = (level.ram?.bands || []).length - bandsIn.length;
    if (skipped) A(level, `${skipped} RAM ${take === 'user' ? 'program-generated' : ''} bands of ${level.name} not drawn (spec.ramBands = "${take}").`);
    for (const band of bandsIn) {
      const n = band.count || band.bars.length || 1;
      const centre = band.bars.length ? band.bars[Math.floor(band.bars.length / 2)] : { a: band.p0, b: band.p1 };
      const a = centre.a, b = centre.b;
      if (dist(a, b) < 1200) { tiny++; continue; } // a "band" shorter than 1.2 m is an artefact of the individual-bar export, not a design
      const u = unit(a, b), nn = perp(u);
      const spacing = band.spacing > 0 ? band.spacing : n > 1 ? Math.round(band.width / (n - 1)) : 0;
      const L = Math.round(dist(a, b) / 10) * 10;
      const st = add(a, u, dist(a, b) * 0.35);
      const half = Math.max(band.width, 0) / 2;
      // a close band reads as a spacing ("T16-150"), a few bars spread over a wide band as a count ("6T16")
      const it = { detail: null, ram: band.id, face: band.face, a, b, l1: n > 1 && spacing && spacing <= 500 ? `T${band.dia}-${spacing} (${band.face})` : `${n}T${band.dia} (${band.face})`, l2: `L=${L}`, side: 1, noTag: true };
      if (half > 50) it.dist = { p: add(st, nn, -half), q: add(st, nn, half) };
      if (band.face === 'T') it.uEnd = { start: atBoundary(a), end: atBoundary(b) };
      items.push(it);
    }
    // office rule at the columns: one group each way, as long as the drop panel (or 4 m) and distributed over the
    // crossing group, is added by applyColumnRule; the RAM top bands over the columns are replaced by it
    const inColumnZone = (it) => (level.columns || []).some((c) => {
      const cc = { x: c.cx, y: c.cy };
      const drop = (level.thickZones || []).find((z) => pointInPolygon(cc, z.polygon));
      const m = mid(it.a, it.b);
      if (drop && (pointInPolygon(m, drop.polygon) || distToPolygon(m, drop.polygon) < 300)) return true;
      const reach = Math.max(c.shape === 'circle' ? c.d : Math.max(c.w, c.h), 600) / 2 + 1200;
      return distToSeg(cc, it.a, it.b) < reach && dist(m, cc) < 2500;
    });
    const inDrop = (it) => (level.thickZones || []).some((z) => { const b = bbox(z.polygon); return Math.max(b.w, b.h) <= (spec.topColumns?.dropMax || 6000) && pointInPolygon(mid(it.a, it.b), z.polygon) && dist(it.a, it.b) <= 1.2 * Math.max(b.w, b.h); });
    const replacedB = items.filter((it) => it.face === 'B' && inDrop(it));
    for (const it of replacedB) items.splice(items.indexOf(it), 1);
    if (replacedB.length) A(level, `${replacedB.length} RAM bottom bands local to the drop panels of ${level.name} replaced by the detail 4 extra bottom bars.`);
    const replaced = items.filter((it) => it.face === 'T' && inColumnZone(it));
    for (const it of replaced) items.splice(items.indexOf(it), 1);
    if (tiny) A(level, `${tiny} RAM bands shorter than 1.2 m in ${level.name} ignored as export artefacts.`);
    if (replaced.length) A(level, `${replaced.length} RAM top bands over the columns of ${level.name} replaced by the office column bars (one group each way, the drop panel length / 4 m, distributed over the crossing group).`);
    level.existing = { lines: [], callouts: [], dims: [], dots: [], items };
    model.findings.push(`${level.id} ${level.name}: ${level.walls.length} walls, ${(level.thickZones || []).length} thickness zones, ${level.edges.filter((e) => e.beam).length} of ${level.edges.length} slab edges with an edge beam, RAM designed reinforcement: ${items.length} bands (${items.filter((i) => i.face === 'T').length} top, ${items.filter((i) => i.face === 'B').length} bottom).`);
    const nProg = items.filter((i) => (level.ram?.bands || []).find((b) => b.id === i.ram)?.designedBy === 'program').length;
    A(level, `Reinforcement of ${level.name} is the RAM Concept design (${items.length} bar bands drawn as designed, ${nProg} of them generated by the program for its design strips, ${items.length - nProg} drawn by the engineer); the General Details additions are placed on top of it. Bottom mesh T${mesh.dia}@${mesh.spacing}${level.topMesh ? ` and top mesh T${level.topMeshSpec[0]}@${level.topMeshSpec[1]}` : ''} ${spec.sources?.bottom === 'assumed' || !spec.bottom ? 'assumed' : 'from the settings'}${level.topMesh ? ' (slab mesh option: both faces)' : ' (slab mesh option: bottom only)'}.`);
    if (!level.walls.length) A(level, `No walls in the RAM model of ${level.name}: details 2 and 5 (core walls) not applied.`);
    else if (level.walls.some((w) => w.assumedT)) A(level, `${level.walls.filter((w) => w.assumedT).length} walls of ${level.name} are line supports in RAM without a thickness: ${wallT} mm assumed for the plan (set spec.wallThickness).`);
  });
  markJoints(model, spec.cover || 25);
  model.design = { units: 'mm', source: 'RAM Concept' };
  return model;
}

/**
 * Office rule for beams: any beam crossing the slab with slab on both sides (a normal beam, a wide band beam, a
 * reinforced beam) carries a group of top bars across it, as long as 4 m or 1.5 m past each face, whichever is
 * larger, distributed along the beam; the bars stop at an adjacent beam, an opening or the slab edge. A beam
 * lying along the slab edge is an edge beam (the L-bars of detail 1 instead). A long thickened strip of the slab
 * (longer than `topColumns.dropMax`, up to `beams.bandMaxWidth` wide) is a band beam and takes the same rule.
 */
export function markBeams(level, spec, A = () => {}) {
  const outline = level.outline;
  const openings = (level.openings || []).map((o) => R.regionPolygon(o));
  const walls = level.walls || [];
  const inSlab = (p) => pointInPolygon(p, outline) && !openings.some((poly) => pointInPolygon(p, poly)) && !walls.some((w) => w.polygon && pointInPolygon(p, w.polygon));
  const bandMax = spec.beams?.bandMaxWidth || 3000;
  const dropMax = spec.topColumns?.dropMax || 6000;
  // long thickened strips are band beams
  for (const z of level.thickZones || []) {
    const b = bbox(z.polygon);
    const long = Math.max(b.w, b.h), short = Math.min(b.w, b.h);
    if (long <= dropMax || short > bandMax || long < 3 * short) continue;
    if (level.beams.some((bm) => bm.polygon && pointInPolygon({ x: b.cx, y: b.cy }, bm.polygon))) continue;
    const along = b.w >= b.h ? { x: 1, y: 0 } : { x: 0, y: 1 };
    level.beams.push({ id: `BB${z.id}`, a: add({ x: b.cx, y: b.cy }, along, -long / 2), b: add({ x: b.cx, y: b.cy }, along, long / 2), t: short, depth: z.thickness, polygon: z.polygon, band: true });
  }
  let interior = 0;
  for (const bm of level.beams) {
    if (!bm.polygon) continue;
    const u = unit(bm.a, bm.b), n = perp(u), m = mid(bm.a, bm.b);
    const off = bm.t / 2 + 400;
    bm.interior = inSlab(add(m, n, off)) && inSlab(add(m, n, -off));
    const b = bbox(bm.polygon);
    bm.cx = b.cx; bm.cy = b.cy; bm.w = b.w; bm.h = b.h;
    bm.along = Math.abs(u.x) >= Math.abs(u.y) ? 'x' : 'y';
    if (bm.interior) interior++;
  }
  level.beams.forEach((bm, i) => { if (!bm.id) bm.id = `BM${i + 1}`; });
  if (interior) A(level, `${interior} beams cross the slab of ${level.name} with slab on both sides (${level.beams.filter((b) => b.interior).map((b) => `${b.id} ${Math.round(b.t)}${b.depth ? 'x' + Math.round(b.depth) : ''}${b.band ? ' BAND' : ''}`).slice(0, 8).join(', ')}${interior > 8 ? ', ...' : ''}): each carries top bars across it, ${(spec.topColumns?.length || 4000) / 1000} m or ${(spec.topColumns?.minBeyond ?? 1500) / 1000} m past each face whichever is larger, distributed along the beam, stopped at an adjacent beam, an opening or the slab edge.`);
  return interior;
}

/**
 * The slab edges for the perimeter rule: consecutive short facets of a curved edge (turning less
 * than `tol` degrees) are merged into one run so a curve gets one call-out, not one per facet.
 */
export function slabEdges(level, tol = 20) {
  const outline = level.outline;
  const segs = [];
  for (let i = 0; i < outline.length; i++) {
    const a = outline[i], b = outline[(i + 1) % outline.length];
    if (dist(a, b) < 300) continue;
    segs.push({ a, b, pts: [a, b] });
  }
  if (!segs.length) return [];
  const turn = (s1, s2) => { const u = unit(s1.a, s1.b), v = unit(s2.a, s2.b); return (Math.acos(Math.max(-1, Math.min(1, u.x * v.x + u.y * v.y))) * 180) / Math.PI; };
  const merged = [];
  for (const sg of segs) {
    const last = merged[merged.length - 1];
    if (last && dist(last.b, sg.a) < 1 && turn({ a: last.pts[last.pts.length - 2], b: last.b }, sg) < tol && (dist(sg.a, sg.b) < 2500 || dist(last.pts[last.pts.length - 2], last.b) < 2500)) { last.b = sg.b; last.pts.push(sg.b); continue; }
    merged.push({ a: sg.a, b: sg.b, pts: [...sg.pts] });
  }
  // the last run may continue into the first one
  if (merged.length > 1) {
    const f = merged[0], l = merged[merged.length - 1];
    if (dist(l.b, f.a) < 1 && turn({ a: l.pts[l.pts.length - 2], b: l.b }, f) < tol && (dist(f.a, f.b) < 2500 || dist(l.pts[l.pts.length - 2], l.b) < 2500)) { l.b = f.b; l.pts.push(...f.pts.slice(1)); merged.shift(); }
  }
  return merged.map((e) => ({ a: e.a, b: e.b, pts: e.pts, curved: e.pts.length > 2, beam: R.edgeHasBeam(level, e.a, e.b) }));
}

/**
 * Office rule for the top bars over columns, applied to the design plan itself: at every column the
 * designer's top bars crossing it take the office length (4 m both ways, or the drop panel + margins;
 * at an edge column the U at the edge and 70 % on top), their "L=" call-outs are rewritten, and the
 * bars of each direction are distributed over the length of the crossing bars: the designer's
 * dimension across them is set to that length, or one is added where none was drawn. A column with
 * no designer's bar in a direction gets the office bar added (`topColumns.addMissing: false` to skip).
 */
export function applyColumnRule(level, spec, assumptions = []) {
  const ex = level.existing;
  if (!ex || !level.columns?.length) return { changed: 0, added: [] };
  const s = spec.topColumns;
  if ((s.rule || 'office') !== 'office') return { changed: 0, added: [] };
  const res = R.topAtColumns(level, spec);
  const isTop = (f) => f === 'T' || f === 'TB';
  const dimDir = (d) => { const ang = d.dimType === 1 ? Math.atan2(d.y4 - d.y3, d.x4 - d.x3) : ((d.rotation || 0) * Math.PI) / 180; return { x: Math.cos(ang), y: Math.sin(ang) }; };
  const dot = (u, v) => u.x * v.x + u.y * v.y;
  const added = [];
  let changed = 0, addedDims = 0, missing = 0, rotated = 0;
  for (const { col, per } of res.columns) {
    if (col.isWall && col.core) continue; // a core wall keeps its U-bars; an isolated wall gets the column groups
    const cc = { x: col.cx, y: col.cy };
    // the two groups are perpendicular, along the column's own axes (a rotated column) or the tendon direction
    const theta = columnAxis(level, col);
    if (theta) rotated++;
    const U = { x: { x: Math.cos(theta), y: Math.sin(theta) } };
    U.y = perp(U.x);
    const loc = (p) => ({ x: dot({ x: p.x - cc.x, y: p.y - cc.y }, U.x), y: dot({ x: p.x - cc.x, y: p.y - cc.y }, U.y) });
    const glob = (lx, ly) => ({ x: cc.x + U.x.x * lx + U.y.x * ly, y: cc.y + U.x.y * lx + U.y.y * ly });
    const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
    const span = (dir) => ({ lo: -size[dir] / 2 - per[dir].ext[-1], hi: size[dir] / 2 + per[dir].ext[1] });
    const groups = {};
    for (const dir of ['x', 'y']) {
      const across = dir === 'x' ? 'y' : 'x';
      // a beam gets its own group across it (the office beam rule) and leaves the designer's bars alone
      if (col.isBeam) { groups[dir] = []; continue; }
      // the bars of this direction are spread over the crossing group's length: every parallel top bar within that
      // half-width of the column centre (and crossing the column along its length) belongs to the group
      const halfBand = Math.max(size[across] / 2 + 400, 800, per[across].straight / 2);
      groups[dir] = ex.lines.filter((l) => {
        if (!isTop(l.face) || l.tick || Math.abs(dot(unit(l.a, l.b), U[dir])) < 0.98) return false;
        const A = loc(l.a), B = loc(l.b);
        return Math.abs(A[across]) <= halfBand && Math.min(A[dir], B[dir]) < size[dir] / 2 + 100 && Math.max(A[dir], B[dir]) > -size[dir] / 2 - 100;
      });
    }
    for (const dir of ['x', 'y']) {
      const across = dir === 'x' ? 'y' : 'x';
      const p = per[dir], { lo, hi } = span(dir);
      const pt = (along, t) => (dir === 'x' ? glob(along, t) : glob(t, along));
      if (groups[dir].length) {
        const olds = groups[dir].map((l) => ({ a: { ...l.a }, b: { ...l.b } }));
        for (const l of groups[dir]) {
          const old = { a: { ...l.a }, b: { ...l.b } };
          const t = loc(l.a)[across];
          const fwd = dot(unit(old.a, old.b), U[dir]) > 0; // keep the bar's own direction so its call-out stays on the same side
          l.a = pt(fwd ? lo : hi, t); l.b = pt(fwd ? hi : lo, t);
          l.uEnd = fwd ? { start: p.hookTypes[-1] || false, end: p.hookTypes[1] || false } : { start: p.hookTypes[1] || false, end: p.hookTypes[-1] || false };
          l.office = true;
          changed++;
        }
        // every length call-out next to any bar of the group (parallel bars share one call-out) now reads the office length
        for (const c of ex.callouts) {
          if (!/^L\s*=\s*\d+/i.test(c.text) || (c.rot != null && Math.abs(dot({ x: Math.cos((c.rot * Math.PI) / 180), y: Math.sin((c.rot * Math.PI) / 180) }, U[dir])) < 0.9)) continue;
          if (olds.some((o) => distToSeg(c, o.a, o.b) < 600)) { c.text = `L=${p.straight}`; c.office = true; }
        }
      } else if (s.addMissing !== false && !(col.isWall && col.skipAlong === dir) && p.straight >= 1000) {
        // (a long isolated wall gets the group across it only: its own reinforcement runs along it; a beam likewise;
        // a bar clipped to a stub, as at a column buried in an edge wall, is not drawn: the wall bars cover it)
        const cAcross = span(across);
        // the symbol beside the column stays within the group it stands for (the crossing bars' extent, which is
        // one-sided at an edge column), so the dot on its distribution dimension always lands on the dimension
        const sgn = dir === 'x' ? 1 : -1; // the bar's left normal points +across for an x bar and -across for a y bar
        const clampK = (k) => sgn * Math.max(cAcross.lo + 150, Math.min(cAcross.hi - 150, sgn * k));
        const cands = [...new Set(barOffsets(spec, size[across], cAcross.hi - cAcross.lo).map(clampK))];
        const item = { detail: null, face: 'T', a: pt(lo, 0), b: pt(hi, 0), l1: `T${s.dia}-${s.spacing} (T)`, l2: `L=${p.straight}`, side: 1, noTag: true, uEnd: { start: p.hookTypes[-1] || false, end: p.hookTypes[1] || false }, column: col.id, dir, n: p.n, length: p.length, shape: p.shape, posCands: cands, keep: cc, beam: col.isBeam ? col.id : undefined };
        added.push(item);
        groups[dir] = [{ a: pt(lo, 0), b: pt(hi, 0), added: true, item }];
        missing++;
      }
    }
    // the distribution of each direction = the crossing bars' extent
    for (const dir of ['x', 'y']) {
      if (!groups[dir].length) continue;
      const across = dir === 'x' ? 'y' : 'x';
      const c = col.isBeam ? { lo: -size[across] / 2, hi: size[across] / 2 } : span(across); // the beam group is distributed along the beam itself
      const { lo, hi } = span(dir);
      const dims = ex.dims.filter((d) => {
        if (d.x3 == null || Math.abs(dot(dimDir(d), U[across])) < 0.9) return false;
        const A = loc({ x: d.x3, y: d.y3 }), B = loc({ x: d.x4, y: d.y4 });
        return near({ x: (d.x3 + d.x4) / 2, y: (d.y3 + d.y4) / 2 }, cc, 3000) && Math.min(A[across], B[across]) < 300 && Math.max(A[across], B[across]) > -300;
      });
      if (dims.length) {
        for (const d of dims) {
          const A = loc({ x: d.x3, y: d.y3 }), B = loc({ x: d.x4, y: d.y4 });
          const swap = A[across] > B[across];
          const P3 = dir === 'x' ? glob(A.x, swap ? c.hi : c.lo) : glob(swap ? c.hi : c.lo, A.y);
          const P4 = dir === 'x' ? glob(B.x, swap ? c.lo : c.hi) : glob(swap ? c.lo : c.hi, B.y);
          d.x3 = P3.x; d.y3 = P3.y; d.x4 = P4.x; d.y4 = P4.y;
          if (theta) { d.dimType = 1; d.x = P3.x; d.y = P3.y; }
          d.x2 = d.y2 = undefined; d.text = undefined; d.office = true;
        }
      } else if (groups[dir][0].added) {
        // an added group carries its own distribution (drawn with the bar, the dot where the bar finally sits)
        // clear of the crossing bar beside the column; a beam's dimension goes on its other side, away from the
        // dimensions of the columns that sit on the beam axis
        // (at an edge column the dimension goes on the side where the bar runs into the slab, never off the edge)
        const off = (spec.barOffset ?? 500) + 700;
        const minus = Math.max(lo + 200, -(size[dir] / 2 + off)), plus = Math.min(hi - 200, size[dir] / 2 + off);
        const st = col.isBeam || per[dir].ext[-1] < per[dir].ext[1] ? plus : minus;
        const pA = dir === 'x' ? glob(st, c.lo) : glob(c.lo, st), pB = dir === 'x' ? glob(st, c.hi) : glob(c.hi, st);
        groups[dir][0].item.dist = { p: pA, q: pB };
        addedDims++;
      } else {
        const st = lo + (hi - lo) * 0.35;
        const pA = dir === 'x' ? glob(st, c.lo) : glob(c.lo, st), pB = dir === 'x' ? glob(st, c.hi) : glob(c.hi, st);
        ex.dims.push({ x3: pA.x, y3: pA.y, x4: pB.x, y4: pB.y, x: pA.x, y: pA.y, dimType: theta ? 1 : 0, rotation: across === 'x' ? 0 : 90, face: 'T', office: true });
        for (const l of groups[dir]) { const t = loc(l.a)[across]; ex.dots.push({ ...(dir === 'x' ? glob(st, t) : glob(t, st)), face: 'T' }); }
        addedDims++;
      }
    }
  }
  const beamAdds = added.filter((it) => it.beam).length;
  if (beamAdds) assumptions.push({ level: level.id, text: `Top bars across ${beamAdds} interior beams of ${level.name}: T${s.dia}-${s.spacing}, ${Math.max(s.length || 4000, 0) / 1000} m or the beam width + 2 x ${(s.minBeyond ?? 1500) / 1000} m whichever is larger, distributed along the beam, shortened where the bar reaches an adjacent beam (to its far face), an opening or the slab edge (U).` });
  if (changed || added.length) assumptions.push({ level: level.id, text: `Top bars over columns set to the office rule in ${level.name}: ${s.length || 4000} mm both ways (exactly the drop panel${s.dropMargin ? ` + ${s.dropMargin} mm` : ''} where there is one), ${Math.round((s.edgeFactor ?? 0.7) * 100)} % on top with the U at an edge, the two groups perpendicular along the column axis / tendon direction (${rotated} rotated columns); ${changed} designer's bars re-lengthed, ${missing} bars added where none was drawn, each direction distributed over the crossing bars' length (${addedDims} dimensions added).` });
  return { changed, added, addedDims, missing };
}

/** The axis (radians, 0 for an orthogonal column) the column's top bars follow: the column's own angle, else the nearest tendon within 2.5 m. */
function columnAxis(level, col) {
  const norm = (deg) => { let d = ((deg % 90) + 90) % 90; if (d > 45) d -= 90; return Math.abs(d) < 2 ? 0 : (d * Math.PI) / 180; };
  if (col.angle != null && norm(col.angle)) return norm(col.angle);
  const tendons = [...(level.pt?.tendons || []), ...(level.ram?.tendons || [])];
  let best = null;
  for (const t of tendons) {
    const pts = t.pts || t.points || [];
    for (let i = 0; i + 1 < pts.length; i++) {
      const d = distToSeg({ x: col.cx, y: col.cy }, pts[i], pts[i + 1]);
      if (d < 2500 && (!best || d < best.d)) best = { d, ang: (Math.atan2(pts[i + 1].y - pts[i].y, pts[i + 1].x - pts[i].x) * 180) / Math.PI };
    }
  }
  return best ? norm(best.ang) : 0;
}

/** The column of a drop panel: a thickened zone around one column, no larger than `topColumns.dropMax` (6 m); null for a strip / band. */
export function dropColumn(level, spec, z) {
  const b = bbox(z.polygon);
  if (Math.max(b.w, b.h) > (spec.topColumns?.dropMax || 6000)) return null;
  return (level.columns || []).find((c) => pointInPolygon({ x: c.cx, y: c.cy }, z.polygon)) || null;
}

/**
 * Office rule: the bar symbol of a column group is drawn beside the column, not through its centre (a vertical bar
 * half a metre to the left, a horizontal bar half a metre above), unless that place is taken by other bars or writing:
 * the candidate offsets (along the bar's normal, +n = left of a vertical bar / above a horizontal one) in order.
 */
function barOffsets(spec, colAcross, bandLen) {
  const off = spec.barOffset ?? 500;
  const k = Math.min(colAcross / 2 + off, Math.max(0, bandLen / 2 - 300));
  return k > 0 ? [k, -k, Math.round(k * 0.6), -Math.round(k * 0.6), 0] : [0];
}

/** The part of the segment p->q that lies outside every opening and contains (or is nearest to) the point `keep`. */
function outsideOpenings(level, p, q, keep) {
  const polys = (level.openings || []).map((o) => R.regionPolygon(o));
  if (!polys.length) return [p, q];
  const L = dist(p, q) || 1, u = unit(p, q);
  const ts = [0, 1];
  for (const poly of polys) for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    const dx = q.x - p.x, dy = q.y - p.y, ex = b.x - a.x, ey = b.y - a.y;
    const den = dx * ey - dy * ex; if (Math.abs(den) < 1e-9) continue;
    const t = ((a.x - p.x) * ey - (a.y - p.y) * ex) / den, v = ((a.x - p.x) * dy - (a.y - p.y) * dx) / den;
    if (t > 0 && t < 1 && v >= 0 && v <= 1) ts.push(t);
  }
  ts.sort((x, y) => x - y);
  const tk = Math.max(0, Math.min(1, ((keep.x - p.x) * u.x + (keep.y - p.y) * u.y) / L));
  let best = null;
  for (let i = 0; i + 1 < ts.length; i++) {
    const t0 = ts[i], t1 = ts[i + 1]; if (t1 - t0 < 1e-6) continue;
    const m = add(p, u, L * (t0 + t1) / 2);
    if (polys.some((poly) => pointInPolygon(m, poly))) continue;
    const d = tk < t0 ? t0 - tk : tk > t1 ? tk - t1 : 0;
    if (!best || d < best.d) best = { d, t0, t1 };
  }
  return best ? [add(p, u, L * best.t0), add(p, u, L * best.t1)] : null;
}

/**
 * A bar never runs into an opening: it stops at the opening edge and ends there in a U (the piece at the column / the
 * bar's own reference `keep` is kept); its written length and cutting length follow. Returns null when nothing is left.
 */
export function clipAtOpenings(level, it, uAllow) {
  if (it.hairpin || it.ind) return it;
  const os = outsideOpenings(level, it.a, it.b, it.keep || mid(it.a, it.b));
  if (!os || dist(os[0], os[1]) < 100) return null;
  const oA = dist(os[0], it.a) > 1, oB = dist(os[1], it.b) > 1;
  if (!oA && !oB) return it;
  const oldL = dist(it.a, it.b), newL = dist(os[0], os[1]);
  it.a = os[0]; it.b = os[1];
  it.uEnd = { ...(it.uEnd || {}) };
  if (oA) it.uEnd.start = 'U';
  if (oB) it.uEnd.end = 'U';
  if (/^L=\d+/.test(it.l2 || '')) it.l2 = `L=${Math.round(newL + (it.extra || 0))}`;
  if (it.length) it.length = Math.round(it.length - (oldL - newL) + ((oA ? 1 : 0) + (oB ? 1 : 0)) * uAllow);
  it.clippedOpening = true;
  return it;
}

/** Nothing is drawn outside the slab: bars and distribution lines are clipped to the outline (an item fully outside is dropped). */
function clipToSlab(level, items, spec = {}) {
  const outline = level.outline;
  const uAllow = R.U_BOTTOM_LEG + (level.thickness - 2 * (spec.cover || 25)); // what a U end adds to the cutting length
  const longest = (a, b) => { const parts = clipSegmentToPolygon(a, b, outline).filter(([p, q]) => dist(p, q) > 50); return parts.sort((p, q) => dist(q[0], q[1]) - dist(p[0], p[1]))[0] || null; };
  const out = [];
  // a cut that falls on a drawing joint with the neighbouring part is no cut: the slab (and the bar) continue there
  const joints = level.jointEdges || [];
  const atJoint = (p) => joints.some((e) => distToSeg(p, e.a, e.b) < 100);
  for (const it of items) {
    // a column symbol that may still slide beside the column is judged where it will finally sit: when the slab
    // outline would cut it to a stub at the column axis (a column standing proud of an edge wall), it moves now to
    // the first candidate place where the bar lies in the slab, so the office length survives the clip
    if (it.posCands && it.posCands.length > 1) {
      const u0 = unit(it.a, it.b), n0 = perp(u0), L0 = dist(it.a, it.b);
      const keptAt = (k) => { const sg = longest(add(it.a, n0, k), add(it.b, n0, k)); return sg ? dist(sg[0], sg[1]) : 0; };
      if (keptAt(0) < Math.min(L0, 1000)) {
        const k0 = it.posCands.find((k) => keptAt(k) >= Math.min(L0, 1000) - 1);
        if (k0 != null) { it.a = add(it.a, n0, k0); it.b = add(it.b, n0, k0); it.posCands = it.posCands.filter((k) => keptAt(k) >= Math.min(L0, 1000) - 1).map((k) => k - k0); }
      }
    }
    const seg = longest(it.a, it.b);
    if (!seg) continue;
    const cutA = dist(seg[0], it.a) > 1, cutB = dist(seg[1], it.b) > 1;
    if ((cutA && !atJoint(seg[0])) || (cutB && !atJoint(seg[1]))) {
      const oldL = dist(it.a, it.b);
      it.a = cutA && !atJoint(seg[0]) ? seg[0] : it.a; it.b = cutB && !atJoint(seg[1]) ? seg[1] : it.b; it.clipped = true;
      // the written length follows the drawn bar (an edge drop's bar stops at the slab edge with its leg)
      const newL = dist(it.a, it.b);
      if (/^L=\d+/.test(it.l2 || '')) it.l2 = `L=${Math.round(newL + (it.extra || 0))}`;
      if (it.length) it.length = Math.round(it.length - (oldL - newL));
    }
    if (clipAtOpenings(level, it, uAllow) === null) continue;
    if (it.column && dist(it.a, it.b) < 1000) continue; // a column bar cut to a stub between an opening and the edge is not worth drawing
    if (it.dist) { const ds = longest(it.dist.p, it.dist.q); if (!ds || dist(ds[0], ds[1]) < 200) delete it.dist; else { it.dist.p = ds[0]; it.dist.q = ds[1]; if (it.dist.textAt && !pointInPolygon(it.dist.textAt, outline)) delete it.dist.textAt; } }
    // the distribution never runs into an opening: it stops before it (the piece at the bar is kept)
    if (it.dist) { const os = outsideOpenings(level, it.dist.p, it.dist.q, mid(it.a, it.b)); if (!os || dist(os[0], os[1]) < 200) delete it.dist; else if (dist(os[0], it.dist.p) > 1 || dist(os[1], it.dist.q) > 1) { it.dist.p = os[0]; it.dist.q = os[1]; delete it.dist.textAt; } }
    if (it.ind) { const kept = []; for (let i = 0; i + 1 < it.ind.length; i++) for (const [p, q] of clipSegmentToPolygon(it.ind[i], it.ind[i + 1], outline)) { if (dist(p, q) < 20) continue; if (kept.length && dist(kept[kept.length - 1], p) < 1) kept.push(q); else kept.push(p, q); } it.ind = kept.length >= 2 ? kept : undefined; }
    out.push(it);
  }
  return out;
}

/** Convex hull (monotone chain) of a polygon's points. */
function convexHull(pts) {
  const P = [...pts].sort((a, b) => a.x - b.x || a.y - b.y);
  if (P.length < 3) return P;
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower = []; for (const p of P) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop(); lower.push(p); }
  const upper = []; for (const p of [...P].reverse()) { while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop(); upper.push(p); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/**
 * Office rule: a concrete wall is treated like a column for the top bars over it, unless it belongs to a
 * core: three or more wall faces (of one or several walls) around an opening. Marks `w.core`.
 */
export function markCoreWalls(level) {
  const walls = (level.walls || []).filter((w) => w.polygon);
  for (const w of walls) w.core = false;
  for (const o of level.openings || []) {
    const poly = R.regionPolygon(o);
    const facesAt = [];
    for (const w of walls) for (let i = 0; i < w.polygon.length; i++) {
      const a = w.polygon[i], b = w.polygon[(i + 1) % w.polygon.length];
      if (dist(a, b) < 800) continue;
      if (distToPolygon(mid(a, b), poly) < 400) facesAt.push(w);
    }
    if (new Set(facesAt).size + facesAt.length >= 4 && facesAt.length >= 3) for (const w of facesAt) w.core = true;
  }
  // a single U / L shaped wall polygon wrapping a void (a stair or lift core drawn as one outline) is a core as well
  for (const w of walls) {
    if (w.core) continue;
    const hull = convexHull(w.polygon);
    const enclosed = Math.abs(polygonArea(hull)) - Math.abs(polygonArea(w.polygon));
    if (w.polygon.length >= 6 && enclosed > 1e6 && enclosed > 0.5 * Math.abs(polygonArea(w.polygon))) w.core = true;
  }
  // a wall running along the slab edge is a retaining wall: detail 2 (slab edge at any core or retaining wall) applies,
  // the wall U-bars along its inner face, not the column groups
  for (const w of walls) {
    if (w.core || !w.a || !w.b || !level.outline) continue;
    const L = dist(w.a, w.b);
    if (L < 1000) continue;
    let onEdge = 0;
    for (let k = 0; k <= 8; k++) if (distToPolygon(add(w.a, unit(w.a, w.b), (L * k) / 8), level.outline) < (w.t || 250) / 2 + 300) onEdge++;
    if (onEdge >= 5) { w.core = true; w.retaining = true; }
  }
  const n = walls.filter((w) => w.core).length;
  return { core: n, isolated: walls.length - n, retaining: walls.filter((w) => w.retaining).length };
}

/** Chained wall segments (RAM line supports drawn as short pieces) joined into straight walls. */
function mergeWallSegments(walls, tol = 5) {
  const out = [];
  const rest = walls.map((w) => ({ ...w }));
  while (rest.length) {
    const w = rest.shift();
    let grew = true;
    while (grew) {
      grew = false;
      for (let i = 0; i < rest.length; i++) {
        const o = rest[i];
        const u = unit(w.a, w.b), v = unit(o.a, o.b);
        const ang = (Math.acos(Math.max(-1, Math.min(1, Math.abs(u.x * v.x + u.y * v.y)))) * 180) / Math.PI;
        if (ang > tol) continue;
        const ends = [[w.b, o.a, () => { w.b = o.b; }], [w.b, o.b, () => { w.b = o.a; }], [w.a, o.a, () => { w.a = o.b; }], [w.a, o.b, () => { w.a = o.a; }]];
        const hit = ends.find(([p, q]) => dist(p, q) < 50);
        if (!hit) continue;
        hit[2](); rest.splice(i, 1); grew = true; break;
      }
    }
    out.push(w);
  }
  return out;
}

function nextLabel(label, used) {
  const letters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  if (/^\d+$/.test(label)) { let n = parseInt(label, 10); while (used.has(String(n))) n++; return String(n); }
  let i = letters.indexOf(label.toUpperCase());
  if (i < 0) return label + "'";
  while (used.has(letters[i])) i = (i + 1) % 26;
  return letters[i];
}

function scaleEnt(e, k) {
  const c = { ...e, x: e.x * k, y: e.y * k };
  if (e.x2 != null) { c.x2 = e.x2 * k; c.y2 = e.y2 * k; }
  if (e.x3 != null) { c.x3 = e.x3 * k; c.y3 = e.y3 * k; }
  if (e.x4 != null) { c.x4 = e.x4 * k; c.y4 = e.y4 * k; }
  if (e.pts) c.pts = e.pts.map((p) => ({ ...p, x: p.x * k, y: p.y * k }));
  if (e.paths) c.paths = e.paths.map((path) => path.map((p) => ({ x: p.x * k, y: p.y * k })));
  if (e.r != null) c.r = e.r * k;
  if (e.height != null) c.height = e.height * k;
  if (e.measure != null) c.measure = e.measure * k;
  return c;
}

// ------------------------------------------------------------------ the General Details rules
/**
 * Reinforcement the General Details add to the designer's plan, as drawable
 * items in the office convention plus a bar list per face.
 */
export function designAdditions(level, spec, opts = {}) {
  if ((level.walls || []).some((w) => w.polygon && w.core === undefined)) markCoreWalls(level);
  const items = [];
  const bars = { T: new R.BarList('DT'), B: new R.BarList('DB') };
  const notes = [];
  const assumptions = [];
  const cover = spec.cover || 25;
  const h = level.thickness;
  const outline = level.outline;
  const inSlab = (p) => pointInPolygon(p, outline) && !(level.walls || []).some((w) => pointInPolygon(p, w.polygon)) && !(level.openings || []).some((o) => pointInPolygon(p, R.regionPolygon(o)));
  const addBar = (face, e) => { const f = face === 'B' ? 'B' : 'T'; bars[f].add(e); if (face === 'TB') bars.B.add(e); };
  const blockedAlong = (a, b) => {
    // parts of the edge a->b covered by columns or walls (as intervals of t along the edge)
    const u = unit(a, b), L = dist(a, b);
    const cuts = [];
    for (const c of level.columns) { const poly = c.shape === 'circle' ? R.regionPolygon({ kind: 'circle', cx: c.cx, cy: c.cy, r: c.d / 2 }) : rectPolygon({ x: c.cx - c.w / 2, y: c.cy - c.h / 2, w: c.w, h: c.h }); if (poly.some((p) => distToSeg(p, a, b) < 300) || distToSeg({ x: c.cx, y: c.cy }, a, b) < Math.max(c.w, c.h)) { const ts = poly.map((p) => (p.x - a.x) * u.x + (p.y - a.y) * u.y); cuts.push([Math.min(...ts) - 100, Math.max(...ts) + 100]); } }
    for (const w of level.walls || []) if (w.polygon.some((p) => distToSeg(p, a, b) < 300)) { const ts = w.polygon.map((p) => (p.x - a.x) * u.x + (p.y - a.y) * u.y); cuts.push([Math.min(...ts) - 100, Math.max(...ts) + 100]); }
    return { runs: subtract([[0, L]], cuts), u, L };
  };

  // ---- perimeter rule (office): T12@150 between the column top bars along every edge; a symmetric U of 4 m at
  // a free edge, an L of the same 4 m (400 down into the beam + 3600 on top) where the edge carries a beam (detail 1 / detail 6)
  const su = spec.uEdge;
  const web = h - 2 * cover;
  const uLegTop = ceilTo((su.total - web) / 2, 10);
  // the column / wall bar groups along the edge decide where the perimeter bars stop (the U-bars run before and after them)
  const tcRes = R.topAtColumns(level, spec);
  const bandOf = (c, dir) => { const r = tcRes.columns.find((x) => x.col.id === c.id); if (!r) return 0; const g = dir === 'across' ? Math.max(r.per.x.straight, r.per.y.straight) : r.per[dir].straight; return g; };
  // where a bar symbol goes along an opening side: the middle of the longest run free of the column / beam groups that
  // reach the side (so it never sits on the group of top bars across a beam alongside the opening)
  const sideSymbolAt = (a, bb) => {
    const u = unit(a, bb), Ls = dist(a, bb);
    const runs = R.edgeRunsBetweenColumns(level, a, bb, h, bandOf);
    if (runs.length) { const [t1, t2] = runs.reduce((best, r) => (!best || r[1] - r[0] > best[1] - best[0] ? r : best), null); return add(a, u, (t1 + t2) / 2); }
    // the whole side lies within a group's band: the point farthest from the group's own bar symbols (the support centres)
    const centres = [...level.columns.map((c) => ({ x: c.cx, y: c.cy })), ...(level.beams || []).filter((bm) => bm.interior).map((bm) => ({ x: bm.cx, y: bm.cy }))].map((c) => (c.x - a.x) * u.x + (c.y - a.y) * u.y);
    const best = [0.25, 0.5, 0.75].map((f) => ({ t: f * Ls, d: Math.min(...centres.map((t) => Math.abs(t - f * Ls)), 1e9) })).sort((p, q) => q.d - p.d)[0];
    return add(a, u, best.t);
  };
  // consecutive slab edges of one kind (free / beam) form one chain: one long indication line and one bar symbol
  // every `perimSpan` along the whole chain, instead of a symbol per facet
  // (an edge with a retaining wall along it carries the wall U-bars of detail 2 instead)
  for (const e of level.edges || []) if (e.wall == null) e.wall = (level.walls || []).some((w) => w.retaining) && R.sideLining(level, e.a, e.b) === 'wall';
  const edgesIn = (level.edges || []).filter((x) => !x.joint && !x.wall);
  const chains = [];
  for (const e of edgesIn) {
    const last = chains[chains.length - 1];
    if (last && last.beam === !!e.beam && dist(last.pts[last.pts.length - 1], e.a) < 1) { last.pts.push(...(e.pts || [e.a, e.b]).slice(1)); continue; }
    chains.push({ beam: !!e.beam, pts: [...(e.pts || [e.a, e.b])] });
  }
  if (chains.length > 1) { const f = chains[0], l = chains[chains.length - 1]; if (f.beam === l.beam && dist(l.pts[l.pts.length - 1], f.pts[0]) < 1) { l.pts.push(...f.pts.slice(1)); chains.shift(); } }
  for (const e of chains) {
    const pts = e.pts;
    const facets = [];
    let s0 = 0;
    for (let i = 0; i + 1 < pts.length; i++) { const L = dist(pts[i], pts[i + 1]); if (L < 1) continue; facets.push({ a: pts[i], b: pts[i + 1], s0, L }); s0 += L; }
    if (!facets.length) continue;
    const at = (sv) => { const f = facets.find((x) => sv <= x.s0 + x.L) || facets[facets.length - 1]; const u = unit(f.a, f.b); return { p: add(f.a, u, sv - f.s0), u, f }; };
    const runs = [];
    for (const f of facets) for (const [t1, t2] of R.edgeRunsBetweenColumns(level, f.a, f.b, h, bandOf)) {
      const last = runs[runs.length - 1];
      if (last && Math.abs(last[1] - (f.s0 + t1)) < 1) last[1] = f.s0 + t2; else runs.push([f.s0 + t1, f.s0 + t2]);
    }
    // the bar schedule counts every run between the column bars ...
    const zoneOf = (t1, t2) => gridRef(level, bbox([at(t1).p, at(t2).p]));
    for (const [t1, t2] of runs) {
      const len = t2 - t1;
      if (len < 2 * su.spacing) continue;
      const count = Math.floor(len / su.spacing) + 1;
      if (e.beam) addBar('T', { dia: su.dia, shape: `L ${su.beamLeg}+${su.beamTop}`, length: su.beamLeg + su.beamTop, qty: count, spacing: su.spacing, zone: `D1 EDGE BEAM ${zoneOf(t1, t2)}` });
      else addBar('T', { dia: su.dia, shape: `U ${uLegTop}/${web}/${uLegTop}`, length: su.total, qty: count, spacing: su.spacing, zone: `D6 FREE EDGE ${zoneOf(t1, t2)}` });
    }
    // ... and the plan shows one bar symbol per run between supports, on each facet the run crosses: every symbol
    // carries its own distribution dimension (the run on that facet, 350 inside the edge) with the dot where the
    // bar crosses it - the office rule that no bar is drawn without its distribution dimension
    if (!runs.length) continue;
    let k = 0;
    for (const run of runs) {
      for (const f of facets) {
        const s1 = Math.max(run[0], f.s0), s2 = Math.min(run[1], f.s0 + f.L);
        if (s2 - s1 < Math.max(800, 2 * su.spacing)) continue;
        const sv = (s1 + s2) / 2;
        const mm = at(sv);
        const nIn = inward(f.a, f.b, outline);
        const zone = zoneOf(s1, s2);
        const dd = { p: add(at(s1).p, nIn, PERIM_DIM_IN), q: add(at(s2).p, nIn, PERIM_DIM_IN) };
        if (e.beam) items.push({ detail: 'D1', face: 'T', a: mm.p, b: add(mm.p, nIn, su.beamTop), l1: `T${su.dia}-${su.spacing} LBAR (T)`, l2: `L=${su.beamLeg + su.beamTop}`, dist: dd, side: 1, zone, legEnd: 'start', noTag: k > 0 });
        else items.push({ detail: 'D6', face: 'TB', a: mm.p, b: add(mm.p, nIn, uLegTop), l1: `T${su.dia}-${su.spacing} U-BAR`, l2: `L=${su.total}`, dist: dd, side: 1, zone, hairpin: true, noTag: k > 0 });
        k++;
      }
    }
  }

  // ---- D2 core walls: U-bars T12@200 + 10T12 (T&B) along the wall face
  const lc = ceilTo(h - cover, 10);
  const noLA = new Set();
  for (const w of (level.walls || []).filter((x) => x.core)) { // core walls only: an isolated wall is reinforced like a column
    const poly = w.polygon;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      const L = dist(a, b);
      if (L < 1500) continue;
      const u = unit(a, b), n = perp(u);
      // slab side of this face: the side where a point 600 mm away lies in the slab
      const m = mid(a, b);
      // (a point inside the hull of a U / L shaped wall is the core it encloses, not the slab)
      const hull = convexHull(poly);
      // the face must open directly onto the slab: just off the face (150) is neither wall nor core, and 600 away is slab
      const slabSide = (sg) => { const q = add(m, n, sg * 150); return !pointInPolygon(q, poly) && !pointInPolygon(q, hull) && inSlab(add(m, n, sg * 600)); };
      const dirOut = slabSide(1) ? 1 : slabSide(-1) ? -1 : 0;
      if (!dirOut) continue;
      const nOut = { x: n.x * dirOut, y: n.y * dirOut };
      // LA follows the designer's wall top bar length next to this face when there is one
      const la0 = (level.wallBarLengths || []).filter((t) => distToSeg(t, a, b) < 2500 && inSlab(add(m, nOut, 300))).sort((p, q) => q.L - p.L)[0];
      const LA = la0 ? la0.L : 1200;
      const count = Math.floor(L / 200) + 1;
      // the distribution along the wall face: 700 into the slab, else further in, else over the wall itself, whichever is free of writing
      // the U-bar starts inside the wall at the opening (core) face, passes through the wall and runs LA into the slab
      const tw = Math.round((w.t || 250) / 10) * 10;
      items.push({ detail: 'D2', face: 'TB', a: add(m, nOut, -tw), b: add(m, nOut, LA), l1: 'T12-200 U-BAR', l2: `L=${LA + tw + 1200 + lc}`, ind: [add(a, nOut, PERIM_DIM_IN), add(b, nOut, PERIM_DIM_IN)], hairpin: true, side: 1, zone: `${w.id} ${gridRef(level, bbox(poly))}` });
      addBar('T', { dia: 12, shape: `U ${LA + tw}/${lc}/1200`, length: LA + tw + 1200 + lc, qty: count, spacing: 200, zone: `D2 ${w.id}` });
      // the 10T12 (T&B) parallel bars of detail 2 only when asked for (office practice: the wall face gets the U-bars only)
      if (spec.walls?.parallelBars) {
        const par = Math.min(12000, Math.round(L + 1200));
        items.push({ detail: 'D2', face: 'TB', a: add(add(a, nOut, 400), u, -600), b: add(add(b, nOut, 400), u, 600), l1: '10T12 (T&B)', l2: `L=${par}`, side: -1, noTag: true });
        addBar('T', { dia: 12, shape: 'STR', length: par, qty: 5, zone: `D2 ${w.id}` });
        addBar('B', { dia: 12, shape: 'STR', length: par, qty: 5, zone: `D2 ${w.id}` });
      }
      if (!la0) noLA.add(w.id);
    }
  }

  if (noLA.size) assumptions.push(noLA.size <= 3 ? `D2 AT ${[...noLA].join(', ')}: NO DESIGNER'S WALL BAR LENGTH FOUND NEXT TO THE FACE; LA = 1200 mm USED.` : `D2 WALL U-BARS: LA = 1200 mm USED AT ${noLA.size} WALL FACES (NO DESIGNER'S WALL BAR LENGTH NEXT TO THEM).`);

  // ---- D3 / D4 thickness zones: the bottom mesh inside a column drop is T12@150 (`spec.drops`), drawn as the two D4
  // groups through the column: each group as long as the drop (4 m without one), at least `minBeyond` past the column
  // face, distributed over the crossing group's length; the bar symbol sits beside the column (a vertical bar to its
  // left, a horizontal one above it) unless that place is taken
  const sd = spec.drops || R.DEFAULT_SPEC.drops;
  const sc = spec.topColumns || R.DEFAULT_SPEC.topColumns;
  for (const z of level.thickZones || []) {
    const b = bbox(z.polygon);
    notes.push({ x: b.cx, y: b.maxY + 350, text: `LAP 500 TYP. AT ${z.thickness || 'THK.'} / ${h} STEP (DET.3)` });
    const col = dropColumn(level, spec, z);
    if (col) {
      const cc = { x: col.cx, y: col.cy };
      const size = { x: col.shape === 'circle' ? col.d : col.w, y: col.shape === 'circle' ? col.d : col.h };
      const len = {};
      for (const dir of ['x', 'y']) len[dir] = Math.max(ceilTo(dir === 'x' ? b.w : b.h, 10), ceilTo(size[dir] + 2 * (sc.minBeyond ?? 1500), 10));
      const zone = `D4 ${z.id} ${gridRef(level, b)}`;
      for (const dir of ['x', 'y']) {
        const across = dir === 'x' ? 'y' : 'x';
        const L = len[dir], W = len[across];
        const a = dir === 'x' ? { x: cc.x - L / 2, y: cc.y } : { x: cc.x, y: cc.y - L / 2 };
        const bb = dir === 'x' ? { x: cc.x + L / 2, y: cc.y } : { x: cc.x, y: cc.y + L / 2 };
        // the distribution line crosses the bar beside the column, over the crossing group's length
        const s0 = Math.max(-L / 2 + 200, -(size[dir] / 2 + (spec.barOffset ?? 500) + 700)); // clear of the crossing bar beside the column
        const dp = dir === 'x' ? { x: cc.x + s0, y: cc.y - W / 2 } : { x: cc.x - W / 2, y: cc.y + s0 };
        const dq = dir === 'x' ? { x: cc.x + s0, y: cc.y + W / 2 } : { x: cc.x + W / 2, y: cc.y + s0 };
        // the drop bar (office rule): the bottom run stops `bendCover` (50) short of each drop face, rises with a
        // 90° bend over the step and continues `leg` (500) at the slab bottom to lap with the slab bottom bars (or
        // further when the office length reaches beyond the drop); its length counts the two rises and continuations
        const step = Math.max(50, (z.thickness || h) - h), cov = sd.bendCover ?? 50;
        const zLo = dir === 'x' ? b.minX : b.minY, zHi = dir === 'x' ? b.maxX : b.maxY, c0 = dir === 'x' ? cc.x : cc.y;
        const runA = Math.min(zLo + cov, c0 - 200), runB = Math.max(zHi - cov, c0 + 200);
        const contA = Math.max(sd.leg || 500, ceilTo(Math.max(0, zLo - (c0 - L / 2)), 10)), contB = Math.max(sd.leg || 500, ceilTo(Math.max(0, c0 + L / 2 - zHi), 10));
        const pa = dir === 'x' ? { x: runA, y: cc.y } : { x: cc.x, y: runA }, pb = dir === 'x' ? { x: runB, y: cc.y } : { x: cc.x, y: runB };
        const run = Math.round(runB - runA), extra = 2 * step + contA + contB, total = run + extra;
        items.push({ detail: 'D4', face: 'B', a: pa, b: pb, l1: `T${sd.dia}-${sd.spacing} (B)`, l2: `L=${total}`, dist: { p: dp, q: dq }, posCands: barOffsets(spec, size[across], W), side: 1, zone, noTag: dir === 'y', keep: cc, bend: { rise: step, beyondA: contA, beyondB: contB }, extra });
        addBar('B', { dia: sd.dia, shape: `BEND90 ${step}+${Math.max(contA, contB)}`, length: total, qty: Math.floor(W / sd.spacing) + 1, spacing: sd.spacing, zone: `${zone} ${dir.toUpperCase()}` });
      }
      continue;
    }
    // a thickened zone without a column (a strip, a band): extra bottom bars over the zone, 50 dia beyond it (detail 4)
    // (the bottom run stops `bendCover` short of the zone faces, rises with a 90° bend and continues 50 dia at the slab bottom)
    const ext = 50 * sd.dia, covZ = sd.bendCover ?? 50;
    const runX = { a: { x: b.minX + covZ, y: b.minY + b.h * 0.42 }, b: { x: b.maxX - covZ, y: b.minY + b.h * 0.42 } };
    const runY = { a: { x: b.minX + b.w * 0.62, y: b.minY + covZ }, b: { x: b.minX + b.w * 0.62, y: b.maxY - covZ } };
    const Lx = Math.round(runX.b.x - runX.a.x), Ly = Math.round(runY.b.y - runY.a.y);
    const stepZ = Math.max(50, (z.thickness || h) - h), extraZ = 2 * (stepZ + ext);
    items.push({ detail: 'D4', face: 'B', a: runX.a, b: runX.b, l1: `T${sd.dia}-${sd.spacing} (B) EXTRA`, l2: `L=${Lx + extraZ}`, dist: { p: { x: b.minX + b.w * 0.35, y: b.minY }, q: { x: b.minX + b.w * 0.35, y: b.maxY } }, side: 1, zone: `${z.id} ${gridRef(level, b)}`, bend: { rise: stepZ, beyondA: ext, beyondB: ext }, extra: extraZ });
    items.push({ detail: 'D4', face: 'B', a: runY.a, b: runY.b, l1: `T${sd.dia}-${sd.spacing} (B) EXTRA`, l2: `L=${Ly + extraZ}`, dist: { p: { x: b.minX, y: b.minY + b.h * 0.72 }, q: { x: b.maxX, y: b.minY + b.h * 0.72 } }, side: -1, noTag: true, bend: { rise: stepZ, beyondA: ext, beyondB: ext }, extra: extraZ });
    addBar('B', { dia: sd.dia, shape: `BEND90 ${stepZ}+${ext}`, length: Lx + extraZ, qty: Math.floor(b.h / sd.spacing) + 1, spacing: sd.spacing, zone: `D4 ${z.id}` });
    addBar('B', { dia: sd.dia, shape: `BEND90 ${stepZ}+${ext}`, length: Ly + extraZ, qty: Math.floor(b.w / sd.spacing) + 1, spacing: sd.spacing, zone: `D4 ${z.id}` });
  }

  // ---- D5 corners: convex wall corners inside the slab (3T16) and re-entrant slab corners (3T12)
  const corner = (c, bis, dia, zone) => {
    const dir = perp(bis);
    const ctr = add(c, bis, 350);
    const dn = perp(dir), st = add(ctr, dir, -450);
    items.push({ detail: 'D5', face: 'TB', a: add(ctr, dir, -1000), b: add(ctr, dir, 1000), l1: `3T${dia}-200 (T&B)`, l2: 'L=2000', dist: { p: add(st, dn, -200), q: add(st, dn, 200) }, side: 1, zone, triple: true });
    addBar('T', { dia, shape: 'STR', length: 2000, qty: 3, spacing: 200, zone });
    addBar('B', { dia, shape: 'STR', length: 2000, qty: 3, spacing: 200, zone });
  };
  for (const w of spec.walls?.cornerDiagonals ? level.walls || [] : []) { // wall-corner diagonals (detail 5) only when asked for
    const poly = w.polygon; // CCW
    for (let i = 0; i < poly.length; i++) {
      const p0 = poly[(i + poly.length - 1) % poly.length], p1 = poly[i], p2 = poly[(i + 1) % poly.length];
      const u1 = unit(p0, p1), u2 = unit(p1, p2);
      const cross = u1.x * u2.y - u1.y * u2.x;
      if (cross <= 0.2) continue; // only convex corners of the wall
      const bis = unit({ x: 0, y: 0 }, { x: u1.x - u2.x, y: u1.y - u2.y }); // outward bisector
      if (!inSlab(add(p1, bis, 400))) continue;
      corner(p1, bis, 16, `D5 ${w.id} CORNER`);
    }
  }
  for (let i = 0; i < outline.length; i++) {
    const p0 = outline[(i + outline.length - 1) % outline.length], p1 = outline[i], p2 = outline[(i + 1) % outline.length];
    if (dist(p0, p1) < 300 || dist(p1, p2) < 300) continue;
    const u1 = unit(p0, p1), u2 = unit(p1, p2);
    const cross = u1.x * u2.y - u1.y * u2.x;
    if (cross >= -0.2) continue; // re-entrant corner of a CCW outline turns right
    if ((level.walls || []).some((w) => w.polygon.some((p) => near(p, p1, 400)))) continue; // wall corners handled above
    const bis = unit({ x: 0, y: 0 }, { x: u1.x - u2.x, y: u1.y - u2.y }); // at a re-entrant corner this bisector points into the slab
    if (!inSlab(add(p1, bis, 400))) continue;
    corner(p1, bis, 12, `D5 SLAB CORNER ${gridRef(level, bbox([p1]))}`);
  }

  // ---- D7 MEP voids (openings not lined by walls)
  for (const o of level.openings || []) {
    const poly = R.regionPolygon(o);
    const b = bbox(poly);
    // a RAM model without wall supports: an opening of shaft size (both sides >= `shaftMin`, 1.5 m) is a lift / stair
    // shaft whose walls are not modelled: no trimmers, the perimeter U-bars (T12@150, 4 m) along its sides instead
    // (a lift / stair shaft is walled in reality even when the RAM model has no wall there)
    const shaft = Math.min(b.w, b.h) >= (spec.openings?.shaftMin || 1500) && level.ram && !R.openingLined(level, o);
    if (shaft) {
      const su = spec.uEdge;
      const uLeg = ceilTo((su.total - (h - 2 * cover)) / 2, 10);
      const sidesP = R.regionPolygon(o);
      let k = 0;
      for (let i = 0; i < sidesP.length; i++) {
        const a = sidesP[i], bb = sidesP[(i + 1) % sidesP.length];
        if (dist(a, bb) < 600) continue;
        const lining = R.sideLining(level, a, bb);
        if (lining === 'wall' || lining === 'column') continue; // the wall U-bars of detail 2 cover this side
        const u = unit(a, bb), n = perp(u), m = sideSymbolAt(a, bb);
        const nOut = inSlab(add(m, n, 700)) ? n : inSlab(add(m, n, -700)) ? { x: -n.x, y: -n.y } : null;
        if (!nOut) continue;
        if (lining === 'beam') {
          items.push({ detail: 'D1', face: 'T', a: m, b: add(m, nOut, su.beamTop), l1: `T${su.dia}-${su.spacing} LBAR (T)`, l2: `L=${su.beamLeg + su.beamTop}`, ind: [add(a, nOut, PERIM_DIM_IN), add(bb, nOut, PERIM_DIM_IN)], side: 1, zone: `D1 ${o.id}`, legEnd: 'start', noTag: k > 0 });
          addBar('T', { dia: su.dia, shape: `L ${su.beamLeg}+${su.beamTop}`, length: su.beamLeg + su.beamTop, qty: Math.floor(dist(a, bb) / su.spacing) + 1, spacing: su.spacing, zone: `D1 SHAFT ${o.id} ${gridRef(level, b)}` });
          k++; continue;
        }
        items.push({ detail: 'D6', face: 'TB', a: m, b: add(m, nOut, uLeg), l1: `T${su.dia}-${su.spacing} U-BAR`, l2: `L=${su.total}`, ind: [add(a, nOut, PERIM_DIM_IN), add(bb, nOut, PERIM_DIM_IN)], side: 1, zone: `D6 ${o.id}`, hairpin: true, noTag: k > 0 });
        addBar('T', { dia: su.dia, shape: `U ${uLeg}/${h - 2 * cover}/${uLeg}`, length: su.total, qty: Math.floor(dist(a, bb) / su.spacing) + 1, spacing: su.spacing, zone: `D6 SHAFT ${o.id} ${gridRef(level, b)}` });
        k++;
      }
      assumptions.push(`${o.id} (${gridRef(level, b)}, ${(b.w / 1000).toFixed(1)} x ${(b.h / 1000).toFixed(1)} m) TAKEN AS A LIFT / STAIR SHAFT: NO TRIMMERS, U-BARS T${su.dia}@${su.spacing} (L-BARS AT A BEAM, THE WALL U-BARS AT A WALL) ALONG ITS SIDES; IF IT IS AN OPEN MEP VOID, SWITCH TO DETAIL 7.`);
      continue;
    }
    if (R.openingLined(level, o)) {
      // enclosed opening: no trimmers; an L-bar (400 into the beam + `beamTop` on top) along every side that runs
      // along a beam, like the slab edge (the wall U-bars of detail 2 cover the sides along walls)
      let nL = 0;
      const outerSides = R.regionPolygon(o); // CCW: the slab is on the right-hand side of each edge... checked with inSlab below
      for (let i = 0; i < outerSides.length; i++) {
        const a = outerSides[i], bb = outerSides[(i + 1) % outerSides.length];
        if (dist(a, bb) < 600 || R.sideLining(level, a, bb) !== 'beam') continue;
        const u = unit(a, bb), n = perp(u);
        const m = sideSymbolAt(a, bb);
        const nOut = inSlab(add(m, n, 700)) ? n : inSlab(add(m, n, -700)) ? { x: -n.x, y: -n.y } : null;
        if (!nOut) continue;
        const su = spec.uEdge;
        const count = Math.floor(dist(a, bb) / su.spacing) + 1;
        items.push({ detail: 'D1', face: 'T', a: m, b: add(m, nOut, su.beamTop), l1: `T${su.dia}-${su.spacing} LBAR (T)`, l2: `L=${su.beamLeg + su.beamTop}`, ind: [add(a, nOut, PERIM_DIM_IN), add(bb, nOut, PERIM_DIM_IN)], side: 1, zone: `D1 ${o.id}`, legEnd: 'start', noTag: nL > 0 });
        addBar('T', { dia: su.dia, shape: `L ${su.beamLeg}+${su.beamTop}`, length: su.beamLeg + su.beamTop, qty: count, spacing: su.spacing, zone: `D1 OPENING ${o.id} ${gridRef(level, b)}` });
        nL++;
      }
      assumptions.push(`D7 NOT ADDED AT ${o.id} (${gridRef(level, b)}): OPENING ENCLOSED BY CONCRETE WALLS / BEAMS - NO ADDITIONAL TRIMMERS (OFFICE RULE); ${nL ? `L-BARS ALONG ITS ${nL} BEAM SIDES` : 'WALL U-BARS PER DETAIL 2'}.`);
      continue;
    }
    // the designer already trimmed this opening (T&B call-outs next to it): keep the design, do not add detail 7
    if ((level.existing?.callouts || []).some((c) => c.face === 'TB' && distToPolygon(c, poly) < 800)) { assumptions.push(`D7 NOT ADDED AT ${o.id} (${gridRef(level, b)}): THE DESIGN PLAN ALREADY TRIMS THIS OPENING (T&B BARS).`); continue; }
    const size = Math.max(b.w, b.h) / 1000;
    const row = VOID_TABLE.find((r) => size <= r.max) || VOID_TABLE[VOID_TABLE.length - 1];
    if (size > 2.5) assumptions.push(`D7 APPLIED AT ${o.id} (${gridRef(level, b)}, ${(b.w / 1000).toFixed(1)} x ${(b.h / 1000).toFixed(1)} m) AS AN MEP VOID; IF THIS IS A LIFT / STAIR SHAFT WITH ITS OWN DETAIL, DELETE THE ADDED BARS.`);
    const zone = `D7 ${o.id} ${gridRef(level, b)}`;
    const rect = { x: b.minX, y: b.minY, w: b.w, h: b.h };
    const sides = [
      { a: { x: rect.x, y: rect.y - 150 }, b: { x: rect.x + rect.w, y: rect.y - 150 }, n: { x: 0, y: -1 } },
      { a: { x: rect.x + rect.w + 150, y: rect.y }, b: { x: rect.x + rect.w + 150, y: rect.y + rect.h }, n: { x: 1, y: 0 } },
      { a: { x: rect.x, y: rect.y + rect.h + 150 }, b: { x: rect.x + rect.w, y: rect.y + rect.h + 150 }, n: { x: 0, y: 1 } },
      { a: { x: rect.x - 150, y: rect.y }, b: { x: rect.x - 150, y: rect.y + rect.h }, n: { x: -1, y: 0 } },
    ];
    const lb = row.u.dia >= 16 ? 800 : 600;
    // three groups: G1 parallel to the lettered grids (the sides along X), G2 parallel to the numbered grids, G3 the 45° diagonals crossing both
    sides.forEach((s, i) => {
      const L = Math.max(1500, Math.round(dist(s.a, s.b) + 1200));
      const u = unit(s.a, s.b);
      const grp = Math.abs(u.y) < 0.5 ? 'G1 (X)' : 'G2 (Y)';
      const st = add(s.a, u, dist(s.a, s.b) * 0.35);
      items.push({ detail: 'D7', face: 'TB', a: add(s.a, u, -600), b: add(s.b, u, 600), l1: `${row.long.n}T${row.long.dia}-${row.long.s} (T&B)`, l2: `L=${L}`, dist: { p: st, q: add(st, s.n, (row.long.n - 1) * row.long.s) }, side: 1, zone, noTag: i > 0 });
      addBar('T', { dia: row.long.dia, shape: 'STR', length: L, qty: row.long.n, spacing: row.long.s, zone: `${zone} ${grp}` });
      addBar('B', { dia: row.long.dia, shape: 'STR', length: L, qty: row.long.n, spacing: row.long.s, zone: `${zone} ${grp}` });
      const m = mid(s.a, s.b);
      const count = Math.floor(dist(s.a, s.b) / row.u.s) + 1;
      if (i < 2) items.push({ detail: 'D7', face: 'TB', a: add(m, s.n, -150), b: add(m, s.n, lb), l1: `T${row.u.dia}-${row.u.s} U-BAR`, l2: `LB=${lb}`, dist: { p: add(s.a, s.n, lb * 0.75), q: add(s.b, s.n, lb * 0.75) }, side: -1, noTag: true });
      addBar('T', { dia: row.u.dia, shape: `U ${lb}/${lc}/${lb}`, length: 2 * lb + lc, qty: count, spacing: row.u.s, zone });
    });
    const d = 1000 / Math.SQRT2;
    for (const [cx, cy, sx, sy] of [[b.minX, b.minY, -1, -1], [b.maxX, b.minY, 1, -1], [b.maxX, b.maxY, 1, 1], [b.minX, b.maxY, -1, 1]]) {
      const ctr = { x: cx + sx * 250, y: cy + sy * 250 };
      const dir = { x: sx, y: -sy };
      items.push({ detail: 'D7', face: 'TB', a: { x: ctr.x - dir.x * d, y: ctr.y - dir.y * d }, b: { x: ctr.x + dir.x * d, y: ctr.y + dir.y * d }, l1: `T${row.diag} 45° (T&B)`, l2: 'L=2000', side: 1, noTag: true });
    }
    addBar('T', { dia: row.diag, shape: 'DIAG 45', length: 2000, qty: 4, zone: `${zone} G3 (45°)` });
    addBar('B', { dia: row.diag, shape: 'DIAG 45', length: 2000, qty: 4, zone: `${zone} G3 (45°)` });
  }

  // ---- D8 pour (infill) strips: the office's pour strip detail (PT details 3): ADD T16@200 straight bars 3 m long top
  // and bottom across the strip, U-bars T12@200 (2400 total) from each face into the strip, T12@150 along the strip
  // top and bottom (fixed before the infill pour)
  const sp8 = spec.pourStrip || R.DEFAULT_SPEC.pourStrip;
  for (const ps of level.pourStrips || []) {
    const b = bbox(ps.polygon);
    const along = b.w >= b.h ? { x: 1, y: 0 } : { x: 0, y: 1 }, acr = perp(along);
    const Ls = Math.max(b.w, b.h), Ws = Math.min(b.w, b.h);
    const c = { x: b.cx, y: b.cy };
    const ref = gridRef(level, b);
    const zone = `D8 ${ps.id} ${ref}`;
    const nAcross = Math.floor(Ls / sp8.spacing) + 1;
    // a strip cast against a retaining wall (a wall along one of its long faces) takes the office's wall variant
    // ("reinforcement details of pour strip with retaining wall"): U-bars T12@200 from the wall face, U-bars 2 m from
    // the slab side, T16@200 across, 7T16 top and bottom along the strip, bonding agent at the joint faces
    const faceOf = (sg) => [add(add(c, along, -Ls / 2), acr, sg * Ws / 2), add(add(c, along, Ls / 2), acr, sg * Ws / 2)];
    const wallSg = [-1, 1].find((sg) => R.sideLining(level, ...faceOf(sg)) === 'wall') ?? 0;
    const sw = sp8.wall || {};
    // straight bars across the strip, top and bottom, one symbol at 35 % along (slid along the strip where a column
    // bar already sits there), distributed over the strip length
    const at = add(c, along, -Ls * 0.15);
    const slide = Math.max(0, Ls / 2 - 600);
    const posCands = [0, -Ls * 0.15, Ls * 0.15, -Ls * 0.3, Ls * 0.3, -Ls * 0.4, Ls * 0.4].map((k) => Math.max(-slide, Math.min(slide, k)));
    const distP = add(c, along, -Ls / 2), distQ = add(c, along, Ls / 2);
    const dOff = (Ws / 2 + 400) * (wallSg ? -wallSg : 1); // the distribution on the slab side, never over the wall
    const nAcrossW = wallSg ? Math.floor(Ls / (sw.spacing || sp8.spacing)) + 1 : nAcross;
    if (wallSg) {
      // against a retaining wall (office detail): T12 @ 200 top and bottom, L = 2000, from the wall face into the slab
      const wd = sw.dia || 12, wsp = sw.spacing || 200, wl = sw.length || 2000;
      const face = add(at, acr, wallSg * Ws / 2);
      const inward = { x: -wallSg * acr.x, y: -wallSg * acr.y };
      items.push({ detail: 'D8', face: 'TB', a: face, b: add(face, inward, wl), l1: `T${wd}-${wsp} TOP&BOTTOM`, l2: `L=${wl}`, dist: { p: add(distP, acr, dOff), q: add(distQ, acr, dOff) }, side: 1, zone, keep: at, posCands });
      addBar('T', { dia: wd, shape: 'STR', length: wl, qty: nAcrossW, spacing: wsp, zone });
      addBar('B', { dia: wd, shape: 'STR', length: wl, qty: nAcrossW, spacing: wsp, zone });
    } else {
      const half = sp8.length / 2;
      items.push({ detail: 'D8', face: 'T', a: add(at, acr, -half), b: add(at, acr, half), l1: `T${sp8.dia}-${sp8.spacing} (T)`, l2: `L=${sp8.length}`, dist: { p: add(distP, acr, dOff), q: add(distQ, acr, dOff) }, side: 1, zone, keep: at, posCands });
      items.push({ detail: 'D8', face: 'B', a: add(at, acr, -half), b: add(at, acr, half), l1: `T${sp8.dia}-${sp8.spacing} (B)`, l2: `L=${sp8.length}`, dist: { p: add(distP, acr, dOff), q: add(distQ, acr, dOff) }, side: 1, zone, keep: at, posCands: posCands.slice().reverse() });
      addBar('T', { dia: sp8.dia, shape: 'STR', length: sp8.length, qty: nAcross, spacing: sp8.spacing, zone });
      addBar('B', { dia: sp8.dia, shape: 'STR', length: sp8.length, qty: nAcross, spacing: sp8.spacing, zone });
    }
    // U-bars from each face of the strip, one symbol per face at 65 % along (from the wall face: `wall.uTotal`,
    // 2400; from the slab side of a wall strip: `wall.uSlab`, 2 m; a plain strip: `uTotal` both sides)
    const atU = add(c, along, Ls * 0.15);
    for (const sg of [-1, 1]) {
      const total = wallSg ? (sg === wallSg ? sw.uTotal || sp8.uTotal : sw.uSlab || 2000) : sp8.uTotal;
      const uLegS = ceilTo((total - (h - 2 * cover)) / 2, 10);
      let face = add(atU, acr, sg * Ws / 2);
      const inward = { x: -sg * acr.x, y: -sg * acr.y };
      if (wallSg && sg === wallSg) {
        // the U-bar at the wall sits inside the wall (anchored in it) and comes out into the strip; its closed end
        // one wall thickness behind the face (as deep as the leg allows)
        const wall = (level.walls || []).find((w) => w.polygon && w.polygon.some((pp) => distToSeg(pp, ...faceOf(sg)) < 300));
        const into = Math.min(wall?.t || 250, Math.max(0, uLegS - 400));
        face = add(face, inward, -into);
      } else if (wallSg) {
        // the U-bar from the slab side straddles the joint: half its leg in the slab, half in the strip
        face = add(face, inward, -uLegS / 2);
      }
      items.push({ detail: 'D8', face: 'TB', a: face, b: add(face, inward, uLegS), l1: `T${sp8.uDia}-${sp8.uSpacing} U-BAR${wallSg && sg === wallSg ? ' (WALL)' : ''}`, l2: `L=${total}`, hairpin: true, side: 1, zone, noTag: true });
      addBar('T', { dia: sp8.uDia, shape: `U ${uLegS}/${h - 2 * cover}/${uLegS}`, length: total, qty: Math.floor(Ls / sp8.uSpacing) + 1, spacing: sp8.uSpacing, zone: `${zone} U${wallSg && sg === wallSg ? ' WALL' : ''}` });
    }
    // longitudinal bars along the strip, top and bottom, fixed before the infill pour (7T16 each layer at a wall)
    const longDia = wallSg ? sw.longDia || sp8.longDia : sp8.longDia;
    const longSpacing = wallSg ? sw.longSpacing || (sw.longCount ? null : sp8.longSpacing) : sp8.longSpacing;
    const nLong = longSpacing ? Math.floor(Ws / longSpacing) + 1 : sw.longCount || 7;
    const longLabel = longSpacing ? `T${longDia}-${longSpacing} (T&B) ALONG STRIP` : `${nLong}T${longDia} (T&B) ALONG STRIP`;
    // the bars along the strip come in stock lengths lapped (never one 27 m bar): the plan writes the strip length and the pieces
    const lapL = R.lapLength(spec, longDia);
    const pieces = R.splitRun(Ls, { stock: spec.stock || R.DEFAULT_SPEC.stock || 12000, lap: lapL });
    const Lw = ceilTo(Ls, 10);
    items.push({ detail: 'D8', face: 'TB', a: add(c, along, -Ls / 2), b: add(c, along, Ls / 2), l1: longLabel, l2: pieces.length > 1 ? `L=${Lw} (${pieces.length} PCS, LAP ${lapL})` : `L=${Lw}`, dist: { p: add(add(c, along, Ls * 0.4), acr, -Ws / 2), q: add(add(c, along, Ls * 0.4), acr, Ws / 2) }, side: -1, zone, noTag: true });
    for (const [len, qty] of [...pieces.reduce((m, len) => m.set(len, (m.get(len) || 0) + 1), new Map())]) addBar('TB', { dia: longDia, shape: 'STR', length: len, qty: nLong * qty, spacing: longSpacing || undefined, zone: `${zone} ALONG${pieces.length > 1 ? ` (LAP ${lapL})` : ''}` });
    if (wallSg) assumptions.push(`D8 AT ${ps.id} (${ref}): ${Math.round(Ws)} WIDE POUR STRIP, ${(Ls / 1000).toFixed(1)} m LONG, CAST AGAINST A RETAINING WALL - OFFICE DETAIL: U-BARS T${sp8.uDia}@${sp8.uSpacing} L=${sw.uTotal || sp8.uTotal} ANCHORED IN THE WALL AND OUT INTO THE STRIP, U-BARS T${sp8.uDia}@${sp8.uSpacing} L=${sw.uSlab || 2000} FROM THE SLAB SIDE, T${sw.dia || 12}@${sw.spacing || 200} L=${sw.length || 2000} TOP & BOTTOM FROM THE WALL FACE INTO THE SLAB, ${longLabel} (T&B); BONDING AGENT ON THE JOINT FACES; PROPS AND THE POUR SEQUENCE PER THE PT DESIGNER.`);
    else assumptions.push(`D8 AT ${ps.id} (${ref}): ${Math.round(Ws)} WIDE POUR STRIP, ${(Ls / 1000).toFixed(1)} m LONG - ADD T${sp8.dia}@${sp8.spacing} L=${sp8.length} TOP & BOTTOM ACROSS IT, U-BARS T${sp8.uDia}@${sp8.uSpacing} (${sp8.uTotal} TOTAL) FROM EACH FACE, T${sp8.longDia}@${sp8.longSpacing} T&B ALONG IT FIXED BEFORE THE INFILL POUR; PROPS AND THE POUR SEQUENCE PER THE PT DESIGNER.`);
  }

  // ---- D9 blockwork support beam through the void between two openings: a strip of the slab between two openings
  // (150 min, up to `blockBeam.maxGap`) with no beam and no concrete wall in it carries the blockwork above as a beam:
  // 2T20 top and bottom along the strip, TA (tension anchorage) beyond each void end, T12@200 links along the strip
  const bb9 = spec.blockBeam || R.DEFAULT_SPEC.blockBeam;
  const TA = R.developmentLength(spec, bb9.dia, { top: true });
  const ops = (level.openings || []).map((o) => ({ o, b: bbox(R.regionPolygon(o)) }));
  for (let i = 0; i < ops.length; i++) for (let j = i + 1; j < ops.length; j++) {
    const A = ops[i].b, B = ops[j].b;
    for (const axis of ['x', 'y']) {
      const [lo, hi, olo, ohi] = axis === 'x' ? ['minX', 'maxX', 'minY', 'maxY'] : ['minY', 'maxY', 'minX', 'maxX'];
      const gap = Math.max(A[lo] - B[hi], B[lo] - A[hi]);
      if (gap < bb9.minWidth || gap > bb9.maxGap) continue;
      const s0 = Math.max(A[olo], B[olo]), s1 = Math.min(A[ohi], B[ohi]);
      if (s1 - s0 < 300) continue; // the openings do not face each other
      const g0 = A[lo] - B[hi] > 0 ? B[hi] : A[hi], gm = g0 + gap / 2;
      const pA = axis === 'x' ? { x: gm, y: s0 } : { x: s0, y: gm }, pB = axis === 'x' ? { x: gm, y: s1 } : { x: s1, y: gm };
      const u = unit(pA, pB);
      if (R.sideLining(level, pA, pB)) continue; // a beam or a concrete wall between the openings carries the blockwork
      if (![0.15, 0.5, 0.85].every((t) => inSlab(add(pA, u, dist(pA, pB) * t)))) continue;
      const a = add(pA, u, -TA), bEnd = add(pB, u, TA);
      const L = Math.round(dist(a, bEnd)), Ls = Math.round(dist(pA, pB));
      const ref = gridRef(level, bbox([pA, pB]));
      const zone = `D9 ${ops[i].o.id}/${ops[j].o.id} ${ref}`;
      const nLinks = Math.floor(Ls / bb9.linkSpacing) + 1;
      const lw = Math.round(gap - 2 * cover), ld = h - 2 * cover;
      items.push({ detail: 'D9', face: 'TB', a, b: bEnd, l1: `${bb9.count}T${bb9.dia} (T&B) + T${bb9.linkDia}-${bb9.linkSpacing} LINKS`, l2: `L=${L}`, dist: { p: pA, q: pB }, pairOff: Math.min(120, gap / 2 - cover), side: 1, zone, blockBeam: { gap, ta: TA } });
      addBar('TB', { dia: bb9.dia, shape: 'STR', length: L, qty: bb9.count, zone });
      addBar('T', { dia: bb9.linkDia, shape: `LINK ${lw}x${ld}`, length: ceilTo(2 * (lw + ld) + 20 * bb9.linkDia, 10), qty: nLinks, spacing: bb9.linkSpacing, zone, note: 'LINKS' });
      assumptions.push(`D9 AT ${ops[i].o.id} / ${ops[j].o.id} (${ref}): ${Math.round(gap)} mm STRIP BETWEEN THE TWO OPENINGS WITH NO BEAM / WALL - BLOCKWORK SUPPORT BEAM ${bb9.count}T${bb9.dia} T&B (TA = ${TA} BEYOND EACH VOID) WITH T${bb9.linkDia}@${bb9.linkSpacing} LINKS; DELETE IF NO BLOCKWORK STANDS ON THIS STRIP.`);
    }
  }

  // ---- D12 punching: the office PS detail (stirrup strips "rows - legs - T12" leaving every column face, rows at S)
  // with a RAM model only at the columns RAM designed stud rails for (the rails' length and stud area converted:
  // rows cover the longest rail, the legs match the rail area per face); without a punching design PS1 / PS2 placeholders
  const punching = [];
  const sp = spec.punching || R.DEFAULT_SPEC.punching;
  const psDia = sp.psDia || 12, psS = sp.rowSpacing || 100, legArea = (Math.PI * psDia * psDia) / 4;
  const ssrSets = level.ram?.ssr || [];
  // the engineer's bypass: columns flagged by the punching check (not passing in RAM / by the indicative estimate) get the
  // office detail anyway, sized from the estimate, at the design engineer's responsibility (spec.punching.override)
  const override = sp.override && (sp.override.by || sp.override.columns) ? sp.override : null;
  const overrideIds = override ? overrideColumns(level.punchingCheck, override) : new Set();
  const overridden = [];
  for (const c of level.columns) {
    const w = c.shape === 'circle' ? c.d : c.w, hh = c.shape === 'circle' ? c.d : c.h;
    const set = ssrSets.find((st) => Math.abs(st.loc.x - c.cx) < Math.max(w, hh) && Math.abs(st.loc.y - c.cy) < Math.max(w, hh));
    const ov = !set && overrideIds.has(String(c.id).toUpperCase()) ? (level.punchingCheck?.columns || []).find((k) => String(k.id).toUpperCase() === String(c.id).toUpperCase()) : null;
    if (level.ram && !set && !ov) continue; // RAM: no stud rails at this column = no punching reinforcement required
    const dirs = {};
    if (ov) {
      const det = ov.detail || { rows: ov.loc === 'interior' ? 10 : 12, legs: 4 };
      const edge = distToPolygon({ x: c.cx, y: c.cy }, outline) < Math.max(w, hh) + 200;
      dirs.x = dirs.y = { rows: det.rows, legs: det.legs, sides: [-1, 1] };
      overridden.push({ col: c, check: ov, edge });
    } else if (set) {
      const per = { x: { len: 0 }, y: { len: 0 } }, bySide = {};
      for (const r of set.rails) {
        const dx = r.b.x - r.a.x, dy = r.b.y - r.a.y, dir = Math.abs(dx) >= Math.abs(dy) ? 'x' : 'y';
        per[dir].len = Math.max(per[dir].len, Math.hypot(dx, dy));
        const side = dir + Math.sign(dir === 'x' ? dx : dy); bySide[side] = (bySide[side] || 0) + 1;
      }
      for (const dir of ['x', 'y']) {
        const rails = Math.max(bySide[`${dir}1`] || 0, bySide[`${dir}-1`] || 0);
        const rows = Math.max(2, Math.ceil(per[dir].len / psS));
        const legs = Math.max(4, 2 * Math.ceil((rails * set.studArea) / legArea / 2));
        dirs[dir] = { rows, legs, sides: [-1, 1].filter((sg) => bySide[`${dir}${sg}`]) }; // an edge column has no rails towards the edge
      }
    } else {
      const edge = distToPolygon({ x: c.cx, y: c.cy }, outline) < Math.max(w, hh) + 200;
      dirs.x = dirs.y = { rows: edge ? 12 : 10, legs: 4, sides: [-1, 1] };
    }
    const short = w <= hh ? 'x' : 'y', long = short === 'x' ? 'y' : 'x';
    const tagOf = (d) => `${dirs[d].rows}R-${dirs[d].legs}-T${psDia}`;
    punching.push({ col: c, dirs, s: psS, dia: psDia, short: tagOf(short), long: tagOf(long), shortDir: short, source: set ? set.designedBy : ov ? 'override' : 'assumed', check: ov || null });
  }
  // one PS type per distinct (short dir, long dir, S), the lighter first
  const keyOf = (p) => `${p.short}|${p.long}|${p.s}`;
  const keys = [...new Set(punching.map(keyOf))].sort((a, b) => parseInt(a, 10) - parseInt(b, 10));
  const psTypes = keys.map((k, i) => {
    const [short, long, sv] = k.split('|');
    const cols = punching.filter((p) => keyOf(p) === k);
    for (const p of cols) { p.type = `PS${i + 1}`; p.tag = short === long ? short : `${short} / ${long}`; }
    return { id: `PS${i + 1}`, short, long, s: Number(sv), where: cols.map((p) => p.col.id).join(', ') };
  });
  for (const p of punching) {
    const c = p.col, w = c.shape === 'circle' ? c.d : c.w, hh = c.shape === 'circle' ? c.d : c.h;
    for (const dir of ['x', 'y']) {
      const F = dir === 'x' ? hh : w, ns = p.dirs[dir].legs / 2, sw = Math.max(80, F / ns - 60);
      const linkLen = ceilTo(2 * (sw + h - 2 * cover) + 20 * psDia, 10);
      bars.T.add({ dia: psDia, shape: `LINK ${Math.round(sw)}x${h - 2 * cover}`, length: linkLen, qty: p.dirs[dir].rows * ns * 2, spacing: p.s, zone: `D12 ${p.type} ${c.id} ${dir.toUpperCase()}`, note: 'PUNCHING' });
    }
  }
  const railed = punching.filter((p) => p.source !== 'override');
  if (level.ram) assumptions.push(railed.length ? `D12 PUNCHING: ${railed.length} COLUMNS CARRY STUD RAILS IN THE RAM MODEL (${railed.map((p) => p.col.id).join(', ')}) - DRAWN AS THE OFFICE STIRRUP DETAIL (PS TYPES), ROWS COVERING THE RAILS' LENGTH AT S=${psS}, LEGS MATCHING THE STUD AREA; THE OTHER COLUMNS NEED NO PUNCHING REINFORCEMENT PER RAM.` : 'D12 PUNCHING: NO STUD RAILS IN THE RAM MODEL - NO COLUMN NEEDS PUNCHING REINFORCEMENT PER RAM.');
  if (overridden.length) {
    const who = [override.by, override.date].filter(Boolean).join(', ');
    const ids = overridden.map((o) => o.col.id).join(', ');
    assumptions.push(`D12 PUNCHING - ENGINEER'S BYPASS: COLUMNS ${ids} DO NOT PASS THE PUNCHING CHECK (${overridden.map((o) => `${o.col.id} vu/phi.vc = ${o.check.ratio}`).join('; ')}). NO THICKENING ADOPTED; PUNCHING REINFORCEMENT (PS) IS PROVIDED AT THESE COLUMNS FROM THE OFFICE ESTIMATE AT THE DESIGN ENGINEER'S RESPONSIBILITY${who ? ` (${who})` : ''}${override.note ? `: ${String(override.note).toUpperCase()}` : ''}.`);
    for (const o of overridden) {
      const w = o.col.shape === 'circle' ? o.col.d : o.col.w, hh = o.col.shape === 'circle' ? o.col.d : o.col.h;
      notes.push({ x: o.col.cx, y: o.col.cy + hh / 2 + 700, text: `${o.col.id}: PUNCHING NOT PASSING - PS AT THE DESIGN ENGINEER'S RESPONSIBILITY${override.by ? ` (${String(override.by).toUpperCase()})` : ''}`, box: true, layer: 'PS-TAG' });
      void w;
    }
  }
  level.punchingOverridden = overridden.map((o) => o.col.id);

  return { items, bars, notes, assumptions, punching, psTypes };
}

/** Intervals minus cuts (sorted output). */
function subtract(intervals, cuts) {
  let out = intervals.map((x) => [...x]);
  for (const [c1, c2] of cuts) {
    const next = [];
    for (const [a, b] of out) {
      if (c2 <= a || c1 >= b) { next.push([a, b]); continue; }
      if (c1 > a) next.push([a, c1]);
      if (c2 < b) next.push([c2, b]);
    }
    out = next;
  }
  return out.filter(([a, b]) => b - a > 1);
}

/** Inward unit normal of the outline edge a->b (outline CCW). */
function inward(a, b, outline) {
  const u = unit(a, b), n = perp(u);
  const m = mid(a, b);
  return pointInPolygon(add(m, n, 200), outline) ? n : { x: -n.x, y: -n.y };
}

// ------------------------------------------------------------------ office-convention drafting
// (a bar within half a degree of vertical reads bottom to top, never top to bottom)
// the reading direction of a text along a bar: left to right, or top to bottom when the bar is vertical (the office reads
// vertical writing standing at the left edge of the sheet); `flip` is -1 when the reading direction is opposite to u
const readableRot = (u) => { let r = (Math.atan2(u.y, u.x) * 180) / Math.PI; let flip = 1; if (r >= 89.5) { r -= 180; flip = -1; } else if (r < -90.5) { r += 180; flip = -1; } return { rot: r, flip }; };

// ---------------------------------------------------------------- label placement
const TEXT_W = 0.85; // advance per character in text heights (isocp), before the width factor

/** Axis-aligned box of a text: anchor p, height h (model mm), rotation, alignment. */
function textBox(p, str, h, rot = 0, align = 'L', valign = 'B', wf = 1) {
  const w = String(str).length * h * TEXT_W * wf, hh = h;
  const x0 = align === 'C' ? -w / 2 : align === 'R' ? -w : 0;
  const y0 = valign === 'M' ? -hh / 2 : valign === 'T' ? -hh : 0;
  const r = (rot * Math.PI) / 180, c = Math.cos(r), sn = Math.sin(r);
  return bbox([[x0, y0], [x0 + w, y0], [x0 + w, y0 + hh], [x0, y0 + hh]].map(([x, y]) => ({ x: p.x + x * c - y * sn, y: p.y + x * sn + y * c })));
}

/**
 * Keeps the boxes of everything written on the plan (the designer's call-outs and dimensions,
 * notes, columns, walls) so that every added label can move along its bar, or to the other side,
 * to the first place where it overlaps nothing; when every place is taken, the least overlapping wins.
 */
class LabelPlacer {
  constructor() { this.boxes = []; this.uTags = []; }
  add(b) { if (b && Number.isFinite(b.minX)) this.boxes.push(b); }
  overlap(b) {
    let a = 0;
    for (const o of this.boxes) { const w = Math.min(b.maxX, o.maxX) - Math.max(b.minX, o.minX), h = Math.min(b.maxY, o.maxY) - Math.max(b.minY, o.minY); if (w > 0 && h > 0) a += w * h; }
    return a;
  }
  pick(cands, boxesOf) {
    let best = null;
    for (const c of cands) { const a = boxesOf(c).reduce((sum, b) => sum + this.overlap(b), 0); if (a === 0) return c; if (!best || a < best.a) best = { c, a }; }
    return best ? best.c : cands[0];
  }
}
let placer = null;

/** Start a placer for a plan pen: every text drawn through the pen registers its box. */
function attachPlacer(pl, S, level, spec = {}) {
  placer = new LabelPlacer();
  placer.level = level;
  placer.uAllow = R.U_BOTTOM_LEG + (level.thickness - 2 * (spec.cover || 25));
  const text0 = pl.text.bind(pl);
  pl.text = (p, str, o = {}) => { placer.add(textBox(p, str, (o.h || 2.5) * S, o.rot || 0, o.align || 'L', o.valign || 'B', o.widthFactor || 1)); return text0(p, str, o); };
  for (const c of level.columns || []) placer.add(c.shape === 'circle' ? { minX: c.cx - c.d / 2, minY: c.cy - c.d / 2, maxX: c.cx + c.d / 2, maxY: c.cy + c.d / 2 } : { minX: c.cx - c.w / 2, minY: c.cy - c.h / 2, maxX: c.cx + c.w / 2, maxY: c.cy + c.h / 2 });
  for (const w of level.walls || []) if (w.polygon) placer.add(bbox(w.polygon));
  for (const o of level.openings || []) placer.add(bbox(R.regionPolygon(o))); // a bar symbol never sits in an opening
  return placer;
}

/** A text placed at the first of the candidate anchors that overlaps nothing (candidates = offsets of p). */
function placeText(pl, p, str, o, offsets, S) {
  if (!placer) { pl.text(p, str, o); return p; }
  const h = (o.h || 2.5) * S;
  const q = placer.pick(offsets.map((d) => ({ x: p.x + d.x, y: p.y + d.y })), (c) => [textBox(c, str, h, o.rot || 0, o.align || 'L', o.valign || 'B', o.widthFactor || 1)]);
  pl.text(q, str, o);
  return q;
}

/** The width a bar's own distribution dimension spans: (count - 1) x spacing for a counted group, the spacing of a single bar. */
function distWidthOf(it) {
  const l1 = String(it.l1 || '');
  const count = /^(\d+)\s*T\d+/i.exec(l1);
  const sp = /-(\d{2,4})\b/.exec(l1);
  const spacing = sp ? Number(sp[1]) : 200;
  if (count && Number(count[1]) > 1) return Math.max(spacing, 100) * (Number(count[1]) - 1);
  if (it.n > 1) return Math.max(spacing, 100) * (it.n - 1); // a group whose count is known (column bars)
  // a spacing-only bar stands for a run of bars: never a dimension of one spacing (unreadable, and not what it means)
  return Math.max(spacing * 4, 1000);
}

/** The distribution indicator: a real DIMENSION in style DIM100 (red lines, oblique ticks, green number). */
function officeDim(pl, S, p, q, opts = {}) {
  const L = dist(p, q);
  if (L < 1) return;
  const u = unit(p, q), n = perp(u);
  let textAt = opts.textAt;
  // a dimension shorter than its own text (a 400 group of three bars) carries the text past its end, where it reads
  if (!textAt && L < DIM100.txt * (String(opts.text || Math.round(L)).length * 0.8 + 1.5)) textAt = add(add(q, u, DIM100.txt * 0.6 + (String(opts.text || Math.round(L)).length * DIM100.txt * 0.8) / 2), n, DIM100.gap + DIM100.txt / 2);
  if (placer) { const tm = textAt || add(mid(p, q), n, DIM100.gap + DIM100.txt / 2); placer.add(textBox(tm, opts.text || String(Math.round(L)), DIM100.txt, readableRot(u).rot, 'C', 'M', 0.8)); }
  pl.dimension(p, q, opts.dl || p, { style: 'DIM100', styleDef: DIM100, layer: 'diamension', textMid: textAt, text: opts.text });
}

function officeDot(pl, S, p) {
  pl.circle(p, DOT_R, { layer: 'DOTS' });
  pl.hatch([R.regionPolygon({ kind: 'circle', cx: p.x, cy: p.y, r: DOT_R })], { layer: 'DOTS', pattern: 'SOLID' });
}

/** One added bar in the office convention. */
export function officeBar(pl, S, it, phase) {
  const layer = it.face === 'B' ? 'REO-BOT' : 'REO-TOP';
  if (phase !== 'labels' && it.posCands) {
    // the bar symbol beside the column: the first offset whose line crosses nothing (the column itself, walls, writing)
    const u0 = unit(it.a, it.b), n0 = perp(u0);
    const boxOf = (k) => { const A = add(it.a, n0, k), B = add(it.b, n0, k); return [bbox([add(A, n0, -80), add(A, n0, 80), add(B, n0, -80), add(B, n0, 80)])]; };
    const k = placer ? placer.pick(it.posCands, boxOf) : it.posCands[0];
    it.a = add(it.a, n0, k); it.b = add(it.b, n0, k);
    delete it.posCands;
    if (placer?.level) clipAtOpenings(placer.level, it, placer.uAllow || 800); // in its final place the bar still stops at an opening
    if (placer) placer.add(bbox([add(it.a, n0, -40), add(it.a, n0, 40), add(it.b, n0, -40), add(it.b, n0, 40)])); // later writing keeps off the bar
  }
  const u = unit(it.a, it.b), n = perp(u);
  const { rot, flip } = readableRot(u);
  const side = (it.side || 1) * flip;
  const m0 = mid(it.a, it.b);
  if (phase !== 'labels') {
    // the bar itself, its legs and its distribution dimension (drawn for every bar before any label is placed)
    const ls = legSide(u, it.face); // the legs of this bar: up / right for a bottom bar, down / left for a top bar
    if (it.bend) {
      // the drop bar: the bottom run, a 90° rise over the step at each end (drawn as a leg across the bar, on the
      // leg side) and the continuation at the slab bottom lapping with the slab bottom bars
      const r = Math.max(it.bend.rise || 50, 150);
      const qa1 = add(it.a, ls, r), qa2 = add(qa1, u, -(it.bend.beyondA ?? it.bend.beyond ?? 500));
      const qb1 = add(it.b, ls, r), qb2 = add(qb1, u, it.bend.beyondB ?? it.bend.beyond ?? 500);
      barLine(pl, [qa2, qa1, it.a, it.b, qb1, qb2], layer);
    } else barLine(pl, [it.pairOff ? add(it.a, n, it.pairOff) : it.a, it.pairOff ? add(it.b, n, it.pairOff) : it.b], layer);
    if (it.legEnd) { const e = it.legEnd === 'start' ? it.a : it.b; barLine(pl, [e, add(e, ls, 250)], layer); } // leg of an L at the edge
    if (it.hairpin) { barLine(pl, [add(it.a, ls, 150), add(it.b, ls, 150)], layer); barLine(pl, [it.a, add(it.a, ls, 150)], layer); } // the U on the plan: two legs closed at the edge
    if (it.uEnd) drawUEnds(pl, S, it.a, it.b, it.uEnd, layer);
    if (it.triple) { barLine(pl, [add(it.a, n, 200), add(it.b, n, 200)], layer); barLine(pl, [add(it.a, n, -200), add(it.b, n, -200)], layer); }
    if (it.pairOff) barLine(pl, [add(it.a, n, -it.pairOff), add(it.b, n, -it.pairOff)], layer); // the second bar of a pair (blockwork beam)
    if (it.distCands && !it.dist) {
      const boxOf = (d) => { const du = unit(d.p, d.q), dn = perp(du); return [textBox(d.textAt || add(mid(d.p, d.q), dn, DIM100.gap + DIM100.txt / 2), d.text || String(Math.round(dist(d.p, d.q))), DIM100.txt, readableRot(du).rot, 'C', 'M', 0.8)]; };
      it.dist = placer ? placer.pick(it.distCands, boxOf) : it.distCands[0];
    }
    // office rule: every drawn bar carries a distribution dimension with the dot that ties them together.
    // A bar with an indication line takes the segment of it that it crosses as its dimension; any other bar
    // gets one across it at its symbol, as wide as its group (count x spacing, or the spacing of a single bar).
    if (!it.dist && it.ind && it.ind.length >= 2) {
      let best = null;
      for (let i = 0; i + 1 < it.ind.length; i++) { const d = distToSeg(m0, it.ind[i], it.ind[i + 1]); if (!best || d < best.d) best = { d, p: it.ind[i], q: it.ind[i + 1] }; }
      it.dist = { p: best.p, q: best.q };
      it.ind = null;
    }
    if (!it.dist) {
      const w = distWidthOf(it);
      it.dist = { p: add(m0, n, -w / 2), q: add(m0, n, w / 2) };
      it.distAuto = true;
    }
    if (it.ind) pl.pline(it.ind, { layer: 'diamension' }); // long indication line offset inside the edge: "this bar all along here"
    if (it.dist) {
      // the dot where the bar axis crosses the distribution line; a bar whose axis misses its line by more than a
      // little (the symbol slid away from a clipped group dimension) takes the dimension across itself instead,
      // so that no bar is ever drawn without the dimension and the dot that tie the two together
      let dotAt = null;
      const du = unit(it.dist.p, it.dist.q), Ld = dist(it.dist.p, it.dist.q);
      const den = u.x * du.y - u.y * du.x;
      if (Math.abs(den) > 1e-6) {
        const t = ((m0.x - it.dist.p.x) * u.y - (m0.y - it.dist.p.y) * u.x) / -den;
        if (t >= -300 && t <= Ld + 300) dotAt = add(it.dist.p, du, Math.max(0, Math.min(Ld, t)));
        else if (Math.abs(den) > 0.3 && t > -4000 && t < Ld + 4000 && !it.distAuto) {
          // the symbol slid past the end of its group dimension (clipped group, moved symbol): the dimension is
          // stretched to the bar, so it still measures the run the bar stands for and the dot sits on the bar
          const c = add(it.dist.p, du, t);
          if (t < 0) it.dist = { ...it.dist, p: c }; else it.dist = { ...it.dist, q: c };
          dotAt = c;
        }
      }
      if (!dotAt) {
        const w = distWidthOf(it);
        it.dist = { p: add(m0, n, -w / 2), q: add(m0, n, w / 2) };
        it.distAuto = true;
        dotAt = m0;
      }
      officeDim(pl, S, it.dist.p, it.dist.q, { text: it.dist.text, textAt: it.dist.textAt });
      officeDot(pl, S, dotAt);
    }
    if (phase === 'bars') return;
  }
  // the call-out pair slides along the bar (and may swap sides) to the first place free of other writing
  const to = { layer: 'REO-TXT', style: 'BW', widthFactor: 0.8, rot, align: 'C' };
  const L = dist(it.a, it.b);
  const wTxt = Math.max(String(it.l1).length, String(it.l2).length) * CALL_H * TEXT_W * 0.8;
  let shifts = [0, 400, -400, 800, -800, 1200, -1200, 1600, -1600, 2000, -2000, 2500, -2500, 3000, -3000].filter((k) => Math.abs(k) + wTxt / 2 <= L / 2 + 250);
  // a short bar (a U-bar leg at a wall face or an edge) lets its call-out slide past its ends (into the slab)
  if (L < 2500) shifts = [0, 300, -300, 600, -600, 900, -900, 1200, -1200];
  if (!shifts.length) shifts.push(0);
  // a short bar (a U-bar symbol on an edge or a wall face) can also carry its call-out beside it, along the edge
  const sideways = L < 2500 ? [0, 600, -600, 1200, -1200, 1800, -1800, 2400, -2400] : [0];
  const cands = []; for (const j of sideways) for (const k of shifts) cands.push({ k, sd: flip, j });
  const gap = it.hairpin ? 150 : 60; // a hairpin's second leg sits 150 beside the axis: the call-out on that side clears it
  // office convention: the bar call-out ("T12-150 (B)") above the bar and the length ("L=5340") under it in the
  // reading direction, the bar between them, both texts starting at the same point (left-aligned). The text's "up"
  // on the page is +n when the reading direction follows the bar, -n when it is flipped.
  const wMax = Math.max(String(it.l1).length, String(it.l2).length) * CALL_H * TEXT_W * 0.8;
  const pair = ({ k, j = 0 }) => {
    const mm = add(add(add(m0, u, k), n, j), u, -flip * wMax / 2); // the common start (reading-left) of both lines
    const base = (sg) => (sg < 0 ? gap + 60 : 60);
    const above = add(mm, n, flip * base(flip)), below = add(mm, n, -flip * base(-flip));
    return [[above, it.l1, CALL_H, 'B', 'L'], [below, it.l2, LEN_H, 'T', 'L']];
  };
  const best = placer ? placer.pick(cands, (c) => pair(c).map(([p, str, h, va, al]) => textBox(p, str, h, rot, al, va, 0.8))) : { k: 0, sd: side, j: 0 };
  for (const [p, str, h, va, al] of pair(best)) pl.text(p, str, { ...to, h: h / S, valign: va, align: al });
  const m = add(add(m0, u, best.k), n, best.j || 0);
  if (it.detail && !it.noTag) {
    const tagAt = (k, sg) => add(add(add(m0, u, k), n, best.j || 0), n, sg * 520);
    const tagCands = []; for (const k of [0, 600, -600, 1200, -1200, 1800, -1800]) for (const sg of [best.sd, -best.sd]) tagCands.push(tagAt(best.k + k, sg));
    const c = placer ? placer.pick(tagCands, (q) => [{ minX: q.x - 150, minY: q.y - 150, maxX: q.x + 150, maxY: q.y + 150 }]) : tagAt(best.k, best.sd);
    pl.circle(c, 150, { layer: 'DETAIL-REF' });
    pl.text(c, it.detail, { layer: 'DETAIL-REF', h: 130 / S, align: 'C', valign: 'M', bold: true });
    if (placer) placer.add({ minX: c.x - 150, minY: c.y - 150, maxX: c.x + 150, maxY: c.y + 150 });
  }
}

/** The end of a top bar at the slab boundary: a U (500 bottom leg, "U500") at a free edge or an opening, an L ("L400", the leg down into the beam) at an edge beam: a short leg on the plan and the tag. */
function drawUEnds(pl, S, a, b, uEnd, layer) {
  const u = unit(a, b), n = perp(u);
  const { rot } = readableRot(u);
  const ls = legSide(u, /BOT/.test(layer) ? 'B' : 'T'); // top bar: legs down / left; bottom bar: up / right
  for (const [on, p] of [[uEnd.start, a], [uEnd.end, b]]) {
    if (!on) continue;
    const tick = add(p, ls, 250);
    // a U is drawn as a U: the leg and the 500 bottom leg coming back along the bar from the edge (an L keeps its single leg into the beam)
    if (on === 'U') barLine(pl, [p, tick, add(tick, p === a ? u : { x: -u.x, y: -u.y }, R.U_BOTTOM_LEG)], layer);
    else barLine(pl, [p, tick], layer);
    if (placer) { if (placer.uTags.some((q) => dist(q, p) < 400)) continue; placer.uTags.push(p); } // one tag where two bars end together
    const offs = [0, 300, -300, 600, -600].flatMap((k) => [add(add({ x: 0, y: 0 }, u, k), ls, 300 + 110), add(add({ x: 0, y: 0 }, u, k), ls, -300)]);
    const tag = on === 'L' ? `L${DEFAULT_U.beamLeg}` : `U${R.U_BOTTOM_LEG}`;
    placeText(pl, add(p, n, 0), tag, { layer: 'REO-TXT', style: 'BW', widthFactor: 0.8, h: 110 / S, rot, align: 'C', valign: 'B' }, offs, S);
  }
}

/** The designer's own reinforcement, re-emitted verbatim in the same convention (top bars get the U end at the edge / openings). */
export function drawExisting(pl, S, ex, faces) {
  const keep = (f) => faces.includes(f);
  for (const l of ex.lines.filter((x) => keep(x.face))) {
    const layer = /BOT/i.test(l.layer) || l.face === 'B' ? 'REO-BOT' : 'REO-TOP';
    barLine(pl, [l.a, l.b], layer);
    if (l.uEnd && faces.includes('T')) drawUEnds(pl, S, l.a, l.b, l.uEnd, layer);
  }
  for (const it of (ex.items || []).filter((x) => keep(x.face))) officeBar(pl, S, it);
  for (const c of ex.callouts.filter((x) => keep(x.face))) pl.text({ x: c.x, y: c.y }, c.text, { layer: 'REO-TXT', style: 'BW', widthFactor: c.widthFactor || 0.8, h: (c.h || CALL_H) / S, rot: c.rot, align: ['L', 'C', 'R'][c.halign] || 'L', valign: 'B' });
  for (const d of ex.dims.filter((x) => keep(x.face))) drawDimension(pl, S, d);
  for (const d of ex.dots.filter((x) => keep(x.face))) officeDot(pl, S, d);
}

/** A DIMENSION entity read from the design plan, re-emitted as a real DIMENSION in style DIM100. */
export function drawDimension(pl, S, e) {
  if (e.x3 == null || e.x4 == null) return;
  const p3 = { x: e.x3, y: e.y3 }, p4 = { x: e.x4, y: e.y4 }, dp = { x: e.x, y: e.y };
  const angle = e.dimType === 1 ? (Math.atan2(p4.y - p3.y, p4.x - p3.x) * 180) / Math.PI : (e.rotation || 0);
  const textMid = e.x2 != null && (e.x2 || e.y2) ? { x: e.x2, y: e.y2 } : undefined;
  const text = e.text && e.text !== '<>' && !/^\s*$/.test(e.text) ? e.text : undefined;
  if (placer) { const r = (angle * Math.PI) / 180, u = { x: Math.cos(r), y: Math.sin(r) }, n = perp(u); const along = (p) => (p.x - dp.x) * u.x + (p.y - dp.y) * u.y; const tm = textMid || add(add(dp, u, (along(p3) + along(p4)) / 2), n, DIM100.gap + DIM100.txt / 2); placer.add(textBox(tm, text || String(Math.round(Math.abs(along(p4) - along(p3)))), DIM100.txt, angle, 'C', 'M', 0.8)); }
  pl.dimension(p3, p4, dp, { style: 'DIM100', styleDef: DIM100, layer: 'diamension', angle, textMid, text });
}

/** Mesh label in the designer's style: two lines of cyan text in a box. */
function drawMeshLabels(pl, S, level) {
  for (const m of level.meshLabels || []) {
    const n = m.lines.length;
    const w = Math.max(...m.lines.map((l) => l.length)) * 200 * 0.8 + 400, hh = n * 330 + 200;
    pl.rect({ x: m.x - 200, y: m.y - (n - 1) * 330 - 100, w, h: hh }, { layer: '9_TEXT' });
    m.lines.forEach((ln, i) => pl.text({ x: m.x, y: m.y - i * 330 }, ln, { layer: '9_TEXT', h: 200 / S, style: 'BW', widthFactor: 0.8 }));
  }
}

function drawDesignerNotes(pl, S, level, o = {}) {
  for (const c of level.camber || []) pl.text({ x: c.x, y: c.y }, c.text, { layer: 'TEXT-4', h: 200 / S, style: 'BW', widthFactor: 0.8 });
  for (const t of level.levelTags || []) { pl.text({ x: t.x, y: t.y }, `${t.label} ${t.value}`, { layer: 'TEXT-4', h: 190 / S, style: 'BW', widthFactor: 0.8 }); }
  if (o.thickness !== false) {
    if (o.zones !== false) for (const z of level.thickZones || []) { const b = bbox(z.polygon); pl.text({ x: b.minX + 500, y: b.maxY - 450 }, `THK ${z.thickness || 'DROP'}`, { layer: 'S-TEXT', h: 200 / S, align: 'L', valign: 'M', style: 'BW', widthFactor: 0.8 }); }
    for (const t of level.rcTags || []) pl.text({ x: t.x, y: t.y }, `RC ${t.thickness}`, { layer: 'S-TEXT', h: 170 / S, align: 'C', valign: 'M', style: 'BW', widthFactor: 0.8 });
  }
}

/**
 * The thickness tag of every thickened zone (and, on the bottom sheet, the mesh written in it: the base mesh, or the
 * drop mesh of detail 4 in a column drop) as one block of lines placed after the bars, at the first corner of the zone
 * that is free of bars and writing (top-left, top-right, bottom-left, bottom-right, then just above the zone).
 */
function zoneLabels(pl, S, level, spec, face) {
  const tm = spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh, sd = spec.drops || R.DEFAULT_SPEC.drops;
  for (const z of level.thickZones || []) {
    const b = bbox(z.polygon);
    const lines = [[`THK ${z.thickness || 'DROP'}`, 'S-TEXT', 200]];
    if (face === 'B') lines.push(dropColumn(level, spec, z) ? [`BOTTOM MESH T${sd.dia}@${sd.spacing} (D4)`, '9_TEXT', 170] : [`BOTTOM MESH T${tm.dia}@${tm.spacing}`, '9_TEXT', 170]);
    const wMax = Math.max(...lines.map(([t, , h]) => t.length * h * TEXT_W * 0.8));
    const hAll = lines.reduce((a, [, , h]) => a + h + 100, 0);
    const corners = [[b.minX + 150, b.maxY - 150], [b.maxX - 150 - wMax, b.maxY - 150], [b.minX + 150, b.minY + 150 + hAll], [b.maxX - 150 - wMax, b.minY + 150 + hAll], [b.minX + 150, b.maxY + 150 + hAll], [b.minX + 150, b.minY - 150]];
    const boxesAt = (c) => { let y = c[1]; return lines.map(([t, , h]) => { const bx = textBox({ x: c[0], y: y - h }, t, h, 0, 'L', 'B', 0.8); y -= h + 100; return bx; }); };
    const c = placer ? placer.pick(corners, boxesAt) : corners[0];
    let y = c[1];
    for (const [t, layer, h] of lines) { pl.text({ x: c[0], y: y - h }, t, { layer, h: h / S, style: 'BW', widthFactor: 0.8 }); y -= h + 100; }
  }
}

const DEFAULT_U = R.DEFAULT_SPEC.uEdge;
const detailsKeyRows = (keys) => keys.map((k) => ({ d: k, title: DETAILS[k] }));
const DETAIL_KEY_COLS = [{ key: 'd', title: 'REF', w: 16 }, { key: 'title', title: 'GENERAL DETAIL (SEE THE GENERAL DETAILS SHEET)', w: 160, align: 'L', max: 62 }];

// ------------------------------------------------------------------ sheets
export const DESIGN_SHEETS = [
  { key: 'dframing', base: 'DESIGN_FRAMING_PLAN', title: 'FRAMING PLAN - OUTLINE, COLUMNS, WALLS, OPENINGS, THICKNESS', no: '01' },
  { key: 'dbottom', base: 'DESIGN_BOTTOM_REINFORCEMENT', title: 'BOTTOM REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', no: '02' },
  { key: 'dtop', base: 'DESIGN_TOP_REINFORCEMENT', title: 'TOP REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', no: '03' },
  { key: 'dpunch', base: 'DESIGN_PUNCHING_SHEAR', title: 'PUNCHING SHEAR REINFORCEMENT PLAN', no: '04' },
  // from a RAM model: the tendons, one direction per sheet, with the high / low points of the profile only
  { key: 'dcablat', base: 'DESIGN_PT_CABLES_LATITUDE', title: 'PT CABLES - LATITUDE (DIRECTION 1) - DESIGN LAYOUT AND PROFILE POINTS', no: '05', ramOnly: true, set: 'latitude' },
  { key: 'dcablon', base: 'DESIGN_PT_CABLES_LONGITUDE', title: 'PT CABLES - LONGITUDE (DIRECTION 2) - DESIGN LAYOUT AND PROFILE POINTS', no: '06', ramOnly: true, set: 'longitude' },
  { key: 'dbeams', base: 'DESIGN_BEAM_MARKS_SECTIONS_SCHEDULE', title: 'BEAM MARKS, SECTIONS AND REINFORCEMENT SCHEDULE - RAM DESIGN', no: '07', ramOnly: true, needsBeams: true },
];

const designNotes = (model, level) => [
  commonNotes(model, level)[0],
  `SLAB THICKNESS ${level.thickness} mm${level.tos ? `, ${level.levelTags[0].label} ${level.tos}` : ''}${level.thickZones?.length ? `; THICKENED ZONES ${[...new Set(level.thickZones.map((z) => z.thickness))].join(' / ')} mm HATCHED` : ''}. CONCRETE f'c = ${model.spec.fc} MPa, REINFORCEMENT fy = ${model.spec.fy} MPa, COVER ${model.spec.cover} mm (${model.spec.sources.cover}).`,
  'BAR CALL-OUT (OFFICE CONVENTION): "T10-200 (T)" = BAR SIZE - SPACING (LAYER), "L=2400" = BAR LENGTH; THE RED DIMENSION ACROSS THE BARS IS THE WIDTH OVER WHICH THEY ARE DISTRIBUTED; (T) TOP, (B) BOTTOM, T&B BOTH.',
  'THE REINFORCEMENT DESIGNED BY THE OFFICE IS SHOWN AS DRAWN ON THE DESIGN PLAN. BARS MARKED WITH A CIRCLED "D#" ARE ADDED FROM THE GENERAL DETAILS SHEET (DETAIL NUMBER IN THE CIRCLE) AT THE LOCATIONS THE DETAIL REFERS TO; THE DETAIL GOVERNS FOR SHAPE AND ANCHORAGE.',
  `BAR ENDS AT THE BOUNDARY: U (${R.U_BOTTOM_LEG} BACK AT THE BOTTOM, "U${R.U_BOTTOM_LEG}") AT A FREE EDGE OR AN OPENING, L (${DEFAULT_U.beamLeg} DOWN INTO THE BEAM, "L${DEFAULT_U.beamLeg}") AT AN EDGE BEAM; LEGS ADDED TO THE CUTTING LENGTH. TOP BARS OVER COLUMNS AND ISOLATED WALLS: TWO PERPENDICULAR GROUPS, EACH THE DROP PANEL OR 4 m LONG AND AT LEAST 1.5 m PAST THE FACE, DISTRIBUTED OVER THE CROSSING GROUP; 70 % ON TOP AT AN EDGE. CORE WALLS (3 OR MORE AROUND AN OPENING): WALL U-BARS. PERIMETER T${DEFAULT_U.dia}@${DEFAULT_U.spacing} BETWEEN THE COLUMN BARS: ${DEFAULT_U.total} mm U AT A FREE EDGE, L (${DEFAULT_U.beamLeg} INTO THE BEAM + ${DEFAULT_U.beamTop} ON TOP) AT AN EDGE BEAM; ONE SYMBOL PER RUN, THE LINE INSIDE THE EDGE IS ITS EXTENT. ENCLOSED OPENINGS: NO TRIMMERS; OTHERS: G1 / G2 PARALLEL TO THE SIDES, G3 AT 45°. NOTHING IS DRAWN OUTSIDE THE SLAB.`,
];

function framingSheet(model, level, meta, adds) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { columnHatchLayer: 's-hatch', regionLabels: true, columnIds: true, gridTag: meta.gridTag, pt: false, ubarRegions: false });
    drawDesignerNotes(pl, S, level);
    for (const e of level.edges.filter((x) => x.beam)) { const m = mid(e.a, e.b); const nIn = inward(e.a, e.b, level.outline); pl.text(add(m, nIn, 450), 'EDGE BEAM', { layer: 'BEAM', h: 1.5, align: 'C', valign: 'M', rot: readableRot(unit(e.a, e.b)).rot }); }
    const rows = [
      ...level.columns.map((c) => ({ id: c.id, element: c.shape === 'circle' ? 'COLUMN (ROUND)' : 'COLUMN', size: c.shape === 'circle' ? `Ø${fmtMM(c.d)}` : `${fmtMM(c.w)} x ${fmtMM(c.h)}`, location: `X ${fmtMM(c.cx)}, Y ${fmtMM(c.cy)}` })),
      ...level.walls.map((w) => ({ id: w.id, element: `WALL ${fmtMM(w.t)} THK`, size: `${fmtMM(w.w)} x ${fmtMM(w.h)}`, location: gridRef(level, bbox(w.polygon)) })),
      ...level.openings.map((o) => ({ id: o.id, element: 'OPENING', size: `${fmtMM(bbox(R.regionPolygon(o)).w)} x ${fmtMM(bbox(R.regionPolygon(o)).h)}`, location: gridRef(level, bbox(R.regionPolygon(o))) })),
      ...level.thickZones.map((z) => ({ id: z.id, element: `THICKENED ZONE ${z.thickness || ''} mm`, size: `${fmtMM(bbox(z.polygon).w)} x ${fmtMM(bbox(z.polygon).h)}`, location: gridRef(level, bbox(z.polygon)) })),
      ...(level.pourStrips || []).map((z) => ({ id: z.id, element: 'POUR STRIP', size: `${fmtMM(z.width)} x ${fmtMM(z.length)}`, location: gridRef(level, bbox(z.polygon)) })),
      ...(level.beams || []).filter((bm) => bm.polygon).map((bm) => ({ id: bm.id, element: bm.band ? 'BAND BEAM (THICKENED STRIP)' : bm.interior ? 'INTERIOR BEAM' : 'EDGE BEAM', size: `${fmtMM(bm.t)}${bm.depth ? ' x ' + fmtMM(bm.depth) : ''} L=${fmtMM(dist(bm.a, bm.b))}`, location: gridRef(level, bbox(bm.polygon)) })),
    ];
    const cols = [{ key: 'id', title: 'ID', w: 20 }, { key: 'element', title: 'ELEMENT', w: 42 }, { key: 'size', title: 'SIZE (mm)', w: 45 }, { key: 'location', title: 'LOCATION / GRID', w: 78, align: 'L', max: 44 }];
    const d0 = sheet.detailBox(0, 'GENERAL DETAILS APPLIED ON THIS LEVEL', '');
    sheet.table(d0.x + 3, d0.y + d0.h - 10, DETAIL_KEY_COLS, detailsKeyRows(Object.keys(DETAILS)), { headH: 5, rowH: 4, h: 1.5, maxRows: 12 });
    const d1 = sheet.detailBox(1, 'NOTATION AND MATERIALS', 'N.T.S.');
    const det1 = D.notationLegend({ thickness: level.thickness, fc: model.spec.fc, fy: model.spec.fy, cover: model.spec.cover });
    det1.draw(sheet.detailPen(d1, 12, det1.bbox));
    const d2 = sheet.detailBox(2, 'TYPICAL SLAB SECTION AT COLUMN', '1:25');
    const det2 = D.sectionColumn({ h: level.thickness, c1: level.columns[0]?.w || 600, ext: 1200, dia: 10, spacing: 150, cover: model.spec.cover, hookLeg: R.hookLeg(10), shape: 'STR' });
    det2.draw(sheet.detailPen(d2, 25, det2.bbox));
    return {
      rows, cols, scheduleTitle: 'ELEMENT SCHEDULE',
      general: [...designNotes(model, level).slice(0, 2), 'SLAB OUTLINE, COLUMNS, WALLS, OPENINGS, STAIRS, THICKNESS ZONES, LEVELS AND CAMBER NOTES ARE READ FROM THE OFFICE DESIGN PLAN. EDGE BEAMS ARE LABELLED WHERE THE PLAN DRAWS THEM; DETAIL 1 APPLIES ALONG THEM.', 'SEE SHEETS 02 (BOTTOM), 03 (TOP) AND 04 (PUNCHING) FOR REINFORCEMENT; THE GENERAL DETAILS SHEET IS PART OF THIS SET.'],
      assumptions: levelAssumptions(model, level),
      legend: [['OUTLINE', 'SLAB EDGE', 'thick'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid'], ['WALL-HATCH', 'WALL (HATCHED)', 'hatch'], ['BEAM', 'EDGE BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch'], ['POUR-STRIP-HATCH', 'POUR STRIP', 'hatch']],
      detailsUsed: 3,
    };
  };
}

function rebarSheet(model, level, meta, adds, face) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { columnHatchLayer: 's-hatch', gridTag: meta.gridTag, dims: false, pt: false, ubarRegions: false, regionLabels: false });
    attachPlacer(pl, S, level, model.spec); // everything written from here on is kept clear of what is already there
    drawDesignerNotes(pl, S, level, { thickness: true, zones: false }); // the zone tags are placed after the bars (zoneLabels)
    // office rule: the top sheet carries the top bars and every T&B bar (trimmers, U-bars, diagonals); the bottom sheet the bottom bars only
    const faces = face === 'B' ? ['B'] : ['T', 'TB'];
    drawExisting(pl, S, level.existing, faces);
    if (face === 'B' || level.topMesh) drawMeshLabels(pl, S, level);
    if (face === 'B') {
      // office rule: the bottom mesh is written at every change of slab thickness (thickened zones, local RC thicknesses)
      const tm = model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh;
      const label = `BOTTOM MESH T${tm.dia}@${tm.spacing}`;
      // (inside a thickened zone the mesh is written with the zone tag after the bars, see zoneLabels: the drop mesh of detail 4 in a column drop)
      for (const t of (level.rcTags || []).filter((t) => !(level.thickZones || []).some((z) => pointInPolygon(t, z.polygon)))) pl.text({ x: t.x, y: t.y - 350 }, label, { layer: '9_TEXT', h: 170 / S, align: 'C', valign: 'M', style: 'BW', widthFactor: 0.8 });
    }
    const mine = adds.items.filter((it) => faces.includes(it.face));
    for (const it of mine) officeBar(pl, S, it, 'bars');   // bars and dimensions first ...
    zoneLabels(pl, S, level, model.spec, face);            // ... the zone tags at a free corner of their zone ...
    for (const it of mine) officeBar(pl, S, it, 'labels'); // ... then every call-out finds a free place
    if (face === 'T') for (const n of adds.notes) {
      const at = placeText(pl, { x: n.x, y: n.y }, n.text, { layer: n.layer || 'DETAIL-REF', h: 150 / S, align: 'C', style: 'BW', widthFactor: 0.8 }, [0, 400, -400, 800, -800, 1200, -1200].map((dy) => ({ x: 0, y: dy })), S);
      if (n.box && at) { const tw = n.text.length * 150 * 0.8 * 0.85 + 200; pl.rect({ x: at.x - tw / 2, y: at.y - 100, w: tw, h: 150 + 200 }, { layer: n.layer || 'DETAIL-REF' }); }
    }
    if (face === 'T' && level.topMesh && level.meshSpec) {
      // the top mesh is written at the thickness tag like the bottom one (slab mesh option: both faces)
      for (const t of (level.rcTags || []).filter((t) => !(level.thickZones || []).some((z) => pointInPolygon(t, z.polygon)))) pl.text({ x: t.x, y: t.y - 350 }, `TOP MESH T${(level.topMeshSpec || level.meshSpec)[0]}@${(level.topMeshSpec || level.meshSpec)[1]}`, { layer: '9_TEXT', h: 170 / S, align: 'C', valign: 'M', style: 'BW', widthFactor: 0.8 });
    }
    placer = null;
    const list = adds.bars[face];
    const rows = list.rows().filter((r) => r.note !== 'PUNCHING');
    const tot = { weight_kg: Math.round(rows.reduce((s, r) => s + r.weight_kg, 0) * 10) / 10 };
    const used = [...new Set(mine.map((it) => it.detail))].sort();
    const d0 = sheet.detailBox(0, 'GENERAL DETAILS ADDED ON THIS SHEET', '');
    sheet.table(d0.x + 3, d0.y + d0.h - 10, DETAIL_KEY_COLS, detailsKeyRows(used.length ? used : ['D1']), { headH: 5, rowH: 4, h: 1.5, maxRows: 12 });
    const d1 = sheet.detailBox(1, 'MEP VOID REINFORCEMENT (DETAIL 7)', '');
    const vcols = [{ key: 'size', title: 'VOID (m)', w: 26 }, { key: 'long', title: 'LONGITUDINAL T&B (EACH SIDE)', w: 60 }, { key: 'u', title: 'U-BAR', w: 34 }, { key: 'diag', title: 'DIAGONALS T&B (2 m)', w: 50 }];
    sheet.table(d1.x + 3, d1.y + d1.h - 10, vcols, VOID_TABLE.map((r, i) => ({ size: `${i ? VOID_TABLE[i - 1].max : 0} - ${r.max}`, long: `${r.long.n}T${r.long.dia}-${r.long.s}`, u: `T${r.u.dia}-${r.u.s}`, diag: `T${r.diag}` })), { headH: 5, rowH: 4, h: 1.5 });
    const d9 = face === 'T' ? adds.items.find((it) => it.detail === 'D9') : null;
    const d2 = sheet.detailBox(2, face === 'B' ? 'SECTION - MESH AND EXTRA BOTTOM BARS AT A THICKENED ZONE' : d9 ? 'SECTION - BLOCKWORK SUPPORT BEAM THROUGH VOID (DETAIL 9)' : 'SECTION - U-BAR AT A CORE WALL (DETAIL 2)', '1:20');
    const bb9 = model.spec.blockBeam || R.DEFAULT_SPEC.blockBeam;
    const det2 = d9 ? D.blockBeamSection({ h: level.thickness, cover: model.spec.cover, width: d9.blockBeam.gap, dia: bb9.dia, count: bb9.count, linkDia: bb9.linkDia, linkSpacing: bb9.linkSpacing, ta: d9.blockBeam.ta }) : face === 'B'
      ? D.sectionMesh({ h: level.thickness, cover: model.spec.cover, dia: level.meshSpec?.[0] || 10, lap: R.lapLength(model.spec, level.meshSpec?.[0] || 10), spacing: level.meshSpec?.[1] || 150 })
      : D.sectionUEdge({ h: level.thickness, cover: model.spec.cover, leg: 1200, dia: 12, edgeDia: 12, spacing: 200 });
    det2.draw(sheet.detailPen(d2, 20, det2.bbox));
    const tms = level.topMeshSpec || level.meshSpec;
    const meshLine = level.meshSpec ? `${level.topMesh && tms && (tms[0] !== level.meshSpec[0] || tms[1] !== level.meshSpec[1]) ? `BOTTOM MESH T${level.meshSpec[0]}@${level.meshSpec[1]} AND TOP MESH T${tms[0]}@${tms[1]}` : `MESH T${level.meshSpec[0]}@${level.meshSpec[1]} ${level.topMesh ? 'TOP & BOTTOM (BOTH FACES)' : 'BOTTOM ONLY'}`} TWO WAY AS LABELLED ON THE PLAN (DESIGN)${level.topMesh && face === 'T' ? '; THE TOP MESH RUNS UNDER THE TOP BARS SHOWN, LAPPED AS THE BOTTOM MESH' : ''}.` : 'NO MESH LABEL FOUND ON THE DESIGN PLAN.';
    return {
      rows, totals: `ADDED FROM THE GENERAL DETAILS: ${tot.weight_kg.toLocaleString('en-US')} kg (DESIGNER'S BARS NOT SCHEDULED HERE)`, weight: tot.weight_kg,
      scheduleTitle: `BAR SCHEDULE - GENERAL DETAILS ADDITIONS (${face === 'B' ? 'BOTTOM' : 'TOP'})`,
      planTitles: [face === 'B' ? 'BOTTOM REINFORCEMENT PLAN' : 'TOP REINFORCEMENT PLAN'],
      general: [...designNotes(model, level), meshLine,
        face === 'B' ? `BOTTOM SHEET: BOTTOM BARS ONLY. DETAIL 4 INSIDE A COLUMN DROP = THE DROP MESH T${(model.spec.drops || R.DEFAULT_SPEC.drops).dia}@${(model.spec.drops || R.DEFAULT_SPEC.drops).spacing} AS TWO GROUPS THROUGH THE COLUMN (AS LONG AS THE DROP, AT LEAST 1.5 m PAST THE COLUMN FACE); EXTRA BARS 50 dia BEYOND A THICKENED STRIP. THE BOTTOM MESH T${(model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh).dia}@${(model.spec.thicknessMesh || R.DEFAULT_SPEC.thicknessMesh).spacing} IS WRITTEN AT EVERY CHANGE OF SLAB THICKNESS. T&B BARS (TRIMMERS, U-BARS, DIAGONALS) ARE DRAWN ON THE TOP SHEET; THEIR BOTTOM LAYER IS SCHEDULED HERE.`
          : 'TOP SHEET: DETAIL 1 L-BARS ALONG EDGE BEAMS, DETAIL 2 U-BARS AND PARALLEL BARS AT CORE WALLS, DETAIL 5 CORNER DIAGONALS, DETAIL 7 VOID TRIMMERS (T&B); LAP 500 AT THICKNESS STEPS (DETAIL 3).'],
      assumptions: [...adds.assumptions, ...levelAssumptions(model, level), 'ANCHORAGE-DEPENDENT DETAILS (SLAB EDGE AT LIVE ANCHORS, BURSTING SPIRALS, PAN-BOX TRIMMERS) ARE NOT SHOWN: TO BE ADDED WITH THE TENDON LAYOUT.'],
      legend: [[face === 'B' ? 'REO-BOT' : 'REO-TOP', face === 'B' ? 'BOTTOM BAR (B)' : 'TOP BAR (T)', 'thick'], ['diamension', 'DISTRIBUTION WIDTH', 'line'], ['DOTS', 'BAR / DISTRIBUTION DOT', 'line'], ['DETAIL-REF', 'D# = GENERAL DETAIL REFERENCE', 'line'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid'], ['WALL-HATCH', 'WALL', 'hatch']],
      detailsUsed: 3,
    };
  };
}

function punchingSheet(model, level, meta, adds) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { columnHatchLayer: 's-hatch', gridTag: meta.gridTag, dims: false, pt: false, ubarRegions: false, regionLabels: false, columnIds: true });
    attachPlacer(pl, S, level);
    for (const p of adds.punching) {
      const c = p.col;
      const w = c.shape === 'circle' ? c.d : c.w, hh = c.shape === 'circle' ? c.d : c.h;
      // the stirrup strips: legs / 2 closed stirrups side by side leaving every face, `rows` rows at S (grey row lines)
      for (const dir of ['x', 'y']) {
        const { rows, legs } = p.dirs[dir];
        const ns = Math.max(1, legs / 2), len = rows * p.s;
        const F = dir === 'x' ? hh : w, pitch = F / ns, sw = Math.max(80, pitch - 60);
        const t00 = (dir === 'x' ? c.cy : c.cx) - F / 2;
        for (const sg of p.dirs[dir].sides || [-1, 1]) {
          const face = dir === 'x' ? c.cx + sg * w / 2 : c.cy + sg * hh / 2;
          // nothing outside the slab: the strips stop at the slab edge / an opening
          const endAt = (d) => (dir === 'x' ? { x: face + sg * d, y: c.cy } : { x: c.cx, y: face + sg * d });
          let len = rows * p.s;
          while (len > p.s && !pointInPolygon(endAt(len), level.outline)) len -= p.s;
          const rowsIn = Math.round(len / p.s);
          for (let i = 0; i < ns; i++) {
            const t0 = t00 + pitch * i + (pitch - sw) / 2;
            pl.rect(dir === 'x' ? { x: Math.min(face, face + sg * len), y: t0, w: len, h: sw } : { x: t0, y: Math.min(face, face + sg * len), w: sw, h: len }, { layer: 'REBAR-PUNCH', width: BAR_W });
            for (let r = 1; r <= rowsIn; r++) { const o = face + sg * r * p.s; if (dir === 'x') pl.line({ x: o, y: t0 }, { x: o, y: t0 + sw }, { layer: 'PS-ROW' }); else pl.line({ x: t0, y: o }, { x: t0 + sw, y: o }, { layer: 'PS-ROW' }); }
          }
          // "S" at the first row of the outer strip, with its dot
          const sAt = dir === 'x' ? { x: face + sg * p.s, y: t00 + F + 90 } : { x: t00 + F + 90, y: face + sg * p.s };
          pl.circle(sAt, 25, { layer: 'DOTS' });
          pl.text(add(sAt, dir === 'x' ? { x: 0, y: 1 } : { x: 1, y: 0 }, 60), 'S', { layer: 'PS-TAG', h: 100 / S, style: 'BW', widthFactor: 0.8, align: 'C', valign: 'B', rot: dir === 'x' ? 0 : 90 });
        }
      }
      // the tag beside the column: PS type over "rows - legs - bar"
      const ext = { x: p.dirs.x.rows * p.s, y: p.dirs.y.rows * p.s };
      const base = { x: c.cx + w / 2 + ext.x + 200, y: c.cy + hh / 2 + 150 };
      const offs = [[0, 0], [0, -hh - 300], [-w - ext.x * 2 - 400 - 1400, 0], [-w - ext.x * 2 - 400 - 1400, -hh - 300], [0, ext.y + 600], [0, -hh - ext.y - 900]].map(([x, y]) => ({ x, y }));
      const q = placer.pick(offs.map((d) => ({ x: base.x + d.x, y: base.y + d.y })), (o) => [textBox(o, p.tag, 150, 0, 'L', 'B', 0.8), textBox({ x: o.x, y: o.y + 240 }, p.type, 250, 0, 'L', 'B', 0.8)]);
      pl.text({ x: q.x, y: q.y + 240 }, p.type, { layer: 'PS-TAG', h: 250 / S, style: 'BW', widthFactor: 0.8, bold: true });
      pl.text(q, p.tag, { layer: 'PS-TAG', h: 150 / S, style: 'BW', widthFactor: 0.8 });
      if (p.source === 'override') {
        // the engineer's bypass is written at the column, boxed, so nobody reads the PS as a RAM design
        const txt = `NOT PASSING (vu/phi.vc ${p.check?.ratio ?? '?'}) - PS AT THE DESIGN ENGINEER'S RESPONSIBILITY`;
        const at = placeText(pl, { x: c.cx, y: c.cy - hh / 2 - ext.y - 500 }, txt, { layer: 'PS-TAG', h: 150 / S, align: 'C', style: 'BW', widthFactor: 0.8 }, [0, -400, -800, 400].map((dy) => ({ x: 0, y: dy })), S);
        const tw = txt.length * 150 * 0.8 * 0.85 + 200;
        pl.rect({ x: at.x - tw / 2, y: at.y - 100, w: tw, h: 150 + 200 }, { layer: 'PS-TAG' });
      }
    }
    placer = null;
    const rows = adds.psTypes.map((t) => ({ id: t.id, short: t.short, long: t.long, s: t.s, where: t.where, n: adds.punching.filter((p) => p.type === t.id).length }));
    const cols = [{ key: 'id', title: 'TYPE', w: 18 }, { key: 'short', title: 'SHORT DIR.', w: 36 }, { key: 'long', title: 'LONG DIR.', w: 36 }, { key: 's', title: 'S', w: 14 }, { key: 'n', title: 'No.', w: 14 }, { key: 'where', title: 'COLUMNS', w: 67, align: 'L', max: 38 }];
    const d0 = sheet.detailBox(0, 'PUNCHING SHEAR REINFORCEMENT DETAIL (DETAIL 12 - PS TYPES)', 'N.T.S.');
    const p0 = adds.punching[0];
    const det0 = D.punchingStrips({ h: level.thickness, cover: model.spec.cover, dia: p0 ? p0.dia : 12, s: p0 ? p0.s : 100, rows: p0 ? Math.min(p0.dirs.x.rows, 6) : 4, legs: p0 ? p0.dirs.x.legs : 4 });
    det0.draw(sheet.detailPen(d0, 8, det0.bbox));
    const d1 = sheet.detailBox(1, 'TAG KEY', '');
    ['PUNCHING SHEAR RFT BAR TAGS   10R-4-T12', '10R - DENOTES NUMBER OF ROWS (FROM THE COLUMN FACE, AT S)', '4   - DENOTES NUMBER OF LEGS OF STIRRUPS (PER STRIP)', 'T12 - DENOTES BAR GRADE AND DIAMETER', 'S   - SPACING OF ROWS (mm)', 'SHORT DIR. = STRIPS RUNNING PARALLEL TO THE SHORT SIDE OF THE COLUMN', 'LONG DIR.  = STRIPS RUNNING PARALLEL TO THE LONG SIDE OF THE COLUMN'].forEach((t, i) => sheet.pp.text(d1.x + 4, d1.y + d1.h - 14 - i * 5, t, { layer: 'NOTES', h: 1.8 }));
    const ramPS = !!level.ram;
    const ovs = adds.punching.filter((p) => p.source === 'override');
    const ov = model.spec.punching?.override;
    const check = level.punchingCheck;
    return {
      rows, cols, scheduleTitle: 'SCHEDULE OF PUNCHING SHEAR REINFORCEMENT',
      general: [designNotes(model, level)[0], 'PUNCHING SHEAR REINFORCEMENT IS TAGGED PER COLUMN AS "ROWS - LEGS - BAR" (DETAIL 12): CLOSED STIRRUP STRIPS LEAVE EVERY COLUMN FACE, THE FIRST ROW AT S FROM THE FACE; STIRRUPS ENCLOSE THE TOP AND BOTTOM BARS.', ramPS ? 'PS TYPES ARE DERIVED FROM THE STUD RAILS DESIGNED IN RAM CONCEPT (ROWS COVER THE RAIL LENGTH AT S, LEGS MATCH THE STUD AREA PER FACE); COLUMNS WITHOUT RAILS IN RAM CARRY NO PUNCHING REINFORCEMENT.' : 'PRELIMINARY: PS TYPES ARE PLACEHOLDERS (PS1 INTERIOR, PS2 EDGE / CORNER) UNTIL THE PUNCHING DESIGN OF EACH COLUMN IS AVAILABLE; THE DESIGN GOVERNS THE NUMBER OF ROWS AND LEGS.',
        ovs.length ? `ENGINEER'S BYPASS: COLUMNS ${ovs.map((p) => p.col.id).join(', ')} DO NOT PASS THE PUNCHING CHECK AND NO THICKENING WAS ADOPTED; THEIR PS TYPES ARE SIZED FROM THE OFFICE ESTIMATE AND PROVIDED AT THE DESIGN ENGINEER'S RESPONSIBILITY${ov?.by ? ` - ${String(ov.by).toUpperCase()}` : ''}${ov?.date ? `, ${ov.date}` : ''}.` : null,
        check && check.columns.length ? `INDICATIVE PUNCHING CHECK (SBC 304 / ACI 318 TWO-WAY SHEAR ON RAM'S TRIBUTARY AREAS AND LOADS, f'c ${check.fc} MPa${check.fpc_mpa != null ? `, fpc ${check.fpc_mpa} MPa` : ''}): ${check.columns.filter((k) => k.status !== 'ok').length} OF ${check.columns.length} COLUMNS OVER phi.vc (${check.columns.filter((k) => k.status !== 'ok').map((k) => `${k.id} ${k.ratio}`).join(', ') || 'NONE'}); THE RAM PUNCHING REPORT GOVERNS.` : null].filter(Boolean),
      assumptions: [ramPS ? adds.assumptions.find((t) => /^D12 PUNCHING:/.test(t)) : 'PUNCHING DESIGN NOT AVAILABLE: PS1 = 10R-4-T12 @100 (INTERIOR), PS2 = 12R-4-T12 @100 (EDGE / CORNER) ASSUMED FROM THE GENERAL DETAILS SCHEDULE - TO BE CONFIRMED.', adds.assumptions.find((t) => /^D12 PUNCHING - ENGINEER/.test(t)), ...levelAssumptions(model, level).slice(0, 3)].filter(Boolean),
      legend: [['REBAR-PUNCH', 'STIRRUP STRIPS (LEGS / 2 PER FACE)', 'thick'], ['PS-ROW', 'ROWS OF STIRRUPS AT S', 'line'], ['PS-TAG', 'PS TYPE / TAG', 'line'], ['s-hatch', 'COLUMN (SOLID GREY)', 'solid']],
      detailsUsed: 2,
    };
  };
}

function designCover(model, sheets, meta) {
  return (sheet) => {
    const P = sheet.L.plan;
    const pp = sheet.pp;
    pp.text(P.x + 10, P.y + P.h - 16, (meta.project || '').toUpperCase(), { layer: 'TEXT-TITLE', h: 6, bold: true });
    pp.text(P.x + 10, P.y + P.h - 26, 'REINFORCEMENT DESIGN DRAWINGS - DRAWING INDEX', { layer: 'TEXT-TITLE', h: 4 });
    pp.text(P.x + 10, P.y + P.h - 34, `${meta.company}  ·  ${meta.client ? 'CLIENT: ' + meta.client + '  ·  ' : ''}${meta.location || ''}  ·  REV ${meta.revision}  ·  ${meta.date}`, { layer: 'TITLE', h: 2.6 });
    const cols = [{ key: 'no', title: 'DRAWING No.', w: 40 }, { key: 'title', title: 'DRAWING TITLE', w: 205 }, { key: 'level', title: 'LEVEL / PART', w: 110, align: 'L', max: 40 }, { key: 'block', title: 'BLOCK / XREF NAME', w: 150, align: 'L' }, { key: 'scale', title: 'SCALE', w: 36 }, { key: 'wt', title: 'ADDED (kg)', w: 40 }, { key: 'rev', title: 'REV', w: 20 }];
    const rows = sheets.map((s) => ({ no: s.drawingNo, title: s.title, level: s.level === 'ALL' ? 'ALL' : `${s.level} - ${s.levelName}`, block: s.blockName, scale: s.scale ? `1:${s.scale}` : 'NTS', wt: s.weight ? Math.round(s.weight).toLocaleString('en-US') : '-', rev: meta.revision }));
    sheet.table(P.x + 10, P.y + P.h - 42, cols.map((c) => ({ ...c, align: c.align || (c.key === 'title' ? 'L' : 'C') })), rows, { title: 'DRAWING INDEX / LIST OF SHEETS', rowH: 5, h: 2, headH: 6, titleH: 7 });
    const d0 = sheet.detailBox(0, 'PARTS READ FROM THE DESIGN PLAN', '');
    const lcols = [{ key: 'id', title: 'ID', w: 14 }, { key: 'name', title: 'PART', w: 70, align: 'L', max: 34 }, { key: 'thk', title: 'THK', w: 16 }, { key: 'cols', title: 'COLS', w: 16 }, { key: 'walls', title: 'WALLS', w: 16 }, { key: 'op', title: 'OPEN.', w: 16 }, { key: 'bars', title: 'DESIGN BARS', w: 24 }, { key: 'area', title: 'AREA m²', w: d0.w - 6 - 172 }];
    sheet.table(d0.x + 3, d0.y + d0.h - 10, lcols, model.levels.map((l) => ({ id: l.id, name: l.name, thk: l.thickness, cols: l.columns.length, walls: l.walls.length, op: l.openings.length, bars: l.existing.lines.length, area: Math.round(Math.abs(polygonArea(l.outline)) / 1e6) })), { headH: 5, rowH: 4, h: 1.6, maxRows: 24 });
    const d1 = sheet.detailBox(1, 'GENERAL DETAILS APPLIED', '');
    sheet.table(d1.x + 3, d1.y + d1.h - 10, DETAIL_KEY_COLS, detailsKeyRows(Object.keys(DETAILS)), { headH: 5, rowH: 4, h: 1.5, maxRows: 12 });
    const d2 = sheet.detailBox(2, 'HOW TO USE THE BLOCKS / XREFS', '');
    ['EACH SHEET IS A BLOCK NAMED AS LISTED AND ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1.', 'REINFORCEMENT LAYERS FOLLOW THE OFFICE DESIGN CONVENTION (REO-TOP, REO-BOT, REO-TXT, diamension, DOTS); SHEET FURNITURE FOLLOWS THE SPAN TECH SPAN- STANDARD.', 'BARS ADDED FROM THE GENERAL DETAILS CARRY A CIRCLED D# ON LAYER DETAIL-REF (FREEZE THE LAYER TO HIDE THE REFERENCES).'].forEach((h, i) => pp.mtext(d2.x + 4, d2.y + d2.h - 12 - i * 14, h, { layer: 'NOTES', h: 1.8, width: d2.w - 8 }));
    return { general: [`DESIGN DRAWINGS GENERATED FROM THE OFFICE DESIGN PLAN: ${model.levels.length} PART(S) READ.`, ...model.findings], assumptions: model.assumptions.map((a) => (a.level ? `[${a.level}] ` : '') + a.text), legend: [], detailsUsed: 3 };
  };
}

// ------------------------------------------------------------------ edits from the app
/** A stable id for a bar: its detail / face and its geometry (rounded to 10 mm), so an edit finds the same bar on the next run. */
export function barId(it, prefix = '') {
  const r = (v) => Math.round(v / 10);
  return `${prefix}${it.detail || (it.ram ? 'RB' : it.face || 'X')}:${r(it.a.x)},${r(it.a.y)}-${r(it.b.x)},${r(it.b.y)}`;
}

/**
 * Applies the reinforcement edits made in the app to this level: `spec.edits` is a list of
 *   { op: 'delete', id }                       remove the bar
 *   { op: 'length', id, start, end }           move the start / end along the bar (mm, + = longer), the length re-written
 *   { op: 'spec', id, l1 }                     new call-out ("T16-150 (T)")
 *   { op: 'add', face, a, b, l1, level? }      a new bar between two points
 * Ids are those of `planData` (barId). Edits that match no bar are reported on the sheet.
 */
export function applyEdits(level, adds, edits, assumptions = []) {
  const list = (edits || []).filter((e) => e && (!e.level || e.level === level.id));
  const pools = [
    { name: 'items', arr: adds.items },
    { name: 'ram', arr: level.existing?.items || [] },
    { name: 'lines', arr: level.existing?.lines || [] },
  ];
  for (const pool of pools) for (const it of pool.arr) if (!it.id) it.id = barId(it, pool.name === 'lines' ? 'X' : '');
  let applied = 0;
  const unmatched = [];
  const relabel = (it) => { const L = Math.round((dist(it.a, it.b) + (it.extra || 0)) / 10) * 10; if (it.l2 != null) it.l2 = `L=${L}`; if (it.length != null) it.length = L; };
  for (const e of list) {
    if (e.op === 'add') {
      if (!e.a || !e.b) continue;
      const a = { x: Number(e.a.x), y: Number(e.a.y) }, b = { x: Number(e.b.x), y: Number(e.b.y) };
      if (dist(a, b) < 100) continue;
      const it = { detail: null, face: e.face === 'B' ? 'B' : e.face === 'TB' ? 'TB' : 'T', a, b, l1: e.l1 || 'T12-150 (T)', l2: `L=${Math.round(dist(a, b) / 10) * 10}`, side: 1, noTag: true, edited: true, zone: 'EDIT' };
      if (it.face !== 'B') it.uEnd = { start: false, end: false };
      adds.items.push(it); it.id = barId(it); applied++;
      continue;
    }
    let found = null;
    for (const pool of pools) { const it = pool.arr.find((x) => x.id === e.id); if (it) { found = { pool, it }; break; } }
    if (!found) { unmatched.push(e.id); continue; }
    const { pool, it } = found;
    if (e.op === 'delete') { pool.arr.splice(pool.arr.indexOf(it), 1); applied++; }
    else if (e.op === 'length') {
      const u = unit(it.a, it.b);
      const ds = Number(e.start) || 0, de = Number(e.end) || 0;
      if (dist(it.a, it.b) - ds - de < 200) { unmatched.push(e.id); continue; }
      it.a = add(it.a, u, -ds); it.b = add(it.b, u, de);
      relabel(it); it.edited = true; applied++;
    } else if (e.op === 'spec') { if (e.l1) { it.l1 = String(e.l1); it.edited = true; applied++; } }
  }
  if (applied || unmatched.length) {
    level.edits = { applied, unmatched };
    assumptions.push({ level: level.id, text: `${applied} reinforcement edits made by the engineer in the app applied to ${level.name} (bars deleted, re-lengthed, re-specified or added; the bar schedules count the generated bars only)${unmatched.length ? `; ${unmatched.length} edits matched no bar on this run and were skipped` : ''}.` });
  }
  return { applied, unmatched };
}

/** What the app's editor needs: the slab, its supports and every bar with its id. */
export function planData(level, adds) {
  const pools = [
    { name: 'items', arr: adds.items, kind: 'office' },
    { name: 'ram', arr: level.existing?.items || [], kind: 'ram' },
    { name: 'lines', arr: (level.existing?.lines || []).filter((l) => !l.tick), kind: 'design' },
  ];
  const bars = [];
  for (const pool of pools) for (const it of pool.arr) {
    if (!it.id) it.id = barId(it, pool.name === 'lines' ? 'X' : '');
    bars.push({ id: it.id, kind: pool.kind, detail: it.detail || null, face: it.face || 'T', a: { x: Math.round(it.a.x), y: Math.round(it.a.y) }, b: { x: Math.round(it.b.x), y: Math.round(it.b.y) }, l1: it.l1 || '', l2: it.l2 || '', zone: it.zone || '', edited: !!it.edited });
  }
  const poly = (o) => (o.polygon ? o.polygon : R.regionPolygon(o)).map((p) => ({ x: Math.round(p.x), y: Math.round(p.y) }));
  return {
    id: level.id, name: level.name, thickness: level.thickness, bbox: level.bbox,
    outline: level.outline.map((p) => ({ x: Math.round(p.x), y: Math.round(p.y) })),
    openings: (level.openings || []).map((o) => ({ id: o.id, polygon: poly(o) })),
    columns: (level.columns || []).map((c) => ({ id: c.id, cx: Math.round(c.cx), cy: Math.round(c.cy), w: Math.round(c.shape === 'circle' ? c.d : c.w), h: Math.round(c.shape === 'circle' ? c.d : c.h), shape: c.shape })),
    walls: (level.walls || []).filter((w) => w.polygon).map((w) => ({ id: w.id, polygon: poly(w) })),
    beams: (level.beams || []).filter((b) => b.polygon).map((b) => ({ id: b.id, polygon: poly(b), interior: !!b.interior })),
    thickZones: (level.thickZones || []).map((z) => ({ id: z.id, thickness: z.thickness, polygon: poly(z) })),
    grid: level.grid ? { x: (level.grid.x || []).map((g) => ({ label: g.label, x: Math.round(g.x) })), y: (level.grid.y || []).map((g) => ({ label: g.label, y: Math.round(g.y) })) } : null,
    bars,
  };
}

// ------------------------------------------------------------------ package
export function composeDesignPackage(model, metaIn = {}) {
  const meta = {
    company: 'SPAN TECH CONTRACTING', company_line: 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
    project: 'PROJECT NAME', client: '', engineer: '', contractor: '', location: '', prefix: 'SPAN-DD', revision: '00',
    date: new Date().toISOString().slice(0, 10), prepared: '', checked: '', approved: '', status: 'DESIGN DRAWING - FOR REVIEW',
    ...metaIn,
  };
  const jobs = [];
  for (const level of model.levels) {
    const cores = markCoreWalls(level);
    if (cores.isolated || cores.core) model.assumptions.push({ level: level.id, text: `${cores.isolated} isolated walls in ${level.name} carry the column top bars (the group across the wall, 4 m / the drop panel and at least 1.5 m past the wall face each way; the group along it only on a wall up to ${(model.spec.topColumns?.wallAlongMax || 6000) / 1000} m); ${cores.core} core / retaining walls (${cores.retaining || 0} along the slab edge) carry the wall U-bars of detail 2.` });
    const rule = applyColumnRule(level, model.spec, model.assumptions);
    const adds = designAdditions(level, model.spec);
    for (const it of rule.added) adds.items.push(it);
    adds.items = clipToSlab(level, adds.items, model.spec);
    // the column groups are scheduled after the clipping (a bar stopped at an opening is shorter and ends in a U)
    for (const it of rule.added) if (adds.items.includes(it)) adds.bars.T.add({ dia: model.spec.topColumns.dia, shape: it.clippedOpening ? `${it.shape} (U AT OPENING)` : it.shape, length: it.length, qty: it.n, spacing: model.spec.topColumns.spacing, zone: `${it.beam ? 'BEAM' : 'COLUMN'} ${it.column} ${it.dir.toUpperCase()}` });
    if (level.existing) {
      level.existing.lines = clipToSlab(level, level.existing.lines, model.spec);
      if (level.existing.items) level.existing.items = clipToSlab(level, level.existing.items, model.spec);
      // the designer's / the column rule's distribution DIMENSIONs stop before an opening as well
      for (const d of level.existing.dims || []) {
        if (d.x3 == null) continue;
        const p = { x: d.x3, y: d.y3 }, q = { x: d.x4, y: d.y4 };
        const os = outsideOpenings(level, p, q, mid(p, q));
        if (!os) { d.dropped = true; continue; }
        if (dist(os[0], p) > 1 || dist(os[1], q) > 1) { d.x3 = os[0].x; d.y3 = os[0].y; d.x4 = os[1].x; d.y4 = os[1].y; d.x2 = d.y2 = undefined; d.text = undefined; }
      }
      level.existing.dims = level.existing.dims.filter((d) => !d.dropped);
    }
    // the engineer's edits from the app (delete / lengthen / re-spec / add bars), by stable bar id
    applyEdits(level, adds, model.spec.edits, model.assumptions);
    level.planData = planData(level, adds);
    level.additions = { items: adds.items.length, weight: { T: adds.bars.T.totals().weight_kg, B: adds.bars.B.totals().weight_kg } };
    const makers = { dframing: framingSheet, dbottom: (m, l, mt, a) => rebarSheet(m, l, mt, a, 'B'), dtop: (m, l, mt, a) => rebarSheet(m, l, mt, a, 'T'), dpunch: punchingSheet, dcablat: (m, l, mt) => ramCablesSheet(m, l, mt, { set: 'latitude', variant: 'design' }), dcablon: (m, l, mt) => ramCablesSheet(m, l, mt, { set: 'longitude', variant: 'design' }), dbeams: (m, l, mt) => beamsSheet(m, l, mt) };
    for (const def of DESIGN_SHEETS) {
      if (def.ramOnly && !level.ram) continue;
      if (def.set && !(level.ram?.tendons || []).some((t) => t.spanSet === def.set)) continue;
      if (def.needsBeams && !(level.beamSchedule?.types || []).length) continue;
      jobs.push({ level, def, draw: makers[def.key](model, level, meta, adds) });
    }
  }
  const total = jobs.length + 1;
  const sheets = jobs.map((j, i) => buildSheet({ model, level: j.level, def: j.def, meta, index: i + 2, total, draw: j.draw }));
  const cover = buildSheet({ model, level: null, def: { key: 'cover', base: 'DESIGN_DRAWINGS_COVER_INDEX', title: 'COVER SHEET / DRAWING INDEX', no: '000' }, meta, index: 1, total, draw: designCover(model, sheets, meta) });
  const all = [cover, ...sheets];
  const plan = model.levels.map((l) => l.planData).filter(Boolean);
  for (const s of all) {
    for (const [n, d] of Object.entries(OFFICE_LAYERS)) s.root.layer(n, d);
    s.root.textStyleDef(OFFICE_TEXT_STYLE.name, { font: OFFICE_TEXT_STYLE.font, widthFactor: OFFICE_TEXT_STYLE.widthFactor });
    s.root.dimStyleDef('DIM100', DIM100);
  }
  const pack = packSheets(all, meta, { textStyles: { [OFFICE_TEXT_STYLE.name]: { font: OFFICE_TEXT_STYLE.font, widthFactor: OFFICE_TEXT_STYLE.widthFactor } } });
  pack.plan = plan;
  return pack;
}
