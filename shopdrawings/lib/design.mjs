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
 *   D2  slab edge at core / retaining wall   T12@200 U-bar (LB 1200, LC = t - cover, LA as plan) + 10T12 (T&B) parallel within 800
 *   D3  varying slab thickness          500 lap at the step (note)
 *   D4  column drop / thickened zone    T12@250 (B) extra reinforcement both ways inside the zone, 50 dia beyond it
 *   D5  core wall and slab corners      3T16-200 diagonals 2 m long T&B (3T12 at re-entrant slab corners)
 *   D7  MEP voids                       longitudinal T&B each side, transverse U-bars, diagonals, per the void size table
 *   D12 punching                        PS tags "rows-legs-dia" per column with the schedule (preliminary)
 *   Anchorage-dependent details (D6 slab edge at live anchors, bursting spirals, pan-box trimmers) need the
 *   tendon layout and are left out on purpose; site-specific details (D8-D11) apply only where drawn.
 */
import { extractModel, flatten, closedPolys } from './extract.mjs';
import { bbox, dist, polygonArea, pointInPolygon, centroid, rectPolygon, asAxisRect, cleanPolygon, ceilTo, distToPolygon } from './geometry.mjs';
import * as R from './rebar.mjs';
import * as D from './details.mjs';
import { buildSheet, drawBase, commonNotes, levelAssumptions, gridRef, fmtMM, packSheets } from './sheets.mjs';

// ------------------------------------------------------------------ office convention
export const OFFICE_LAYERS = {
  'REO-TOP': { color: 6, ltype: 'HIDDEN' },
  'REO-BOT': { color: 3, ltype: 'CONTINUOUS' },
  'REO-TXT': { color: 7, ltype: 'CONTINUOUS' },
  'S-TEXT': { color: 7, ltype: 'CONTINUOUS' },
  diamension: { color: 1, ltype: 'CONTINUOUS' },
  DOTS: { color: 2, ltype: 'CONTINUOUS' },
  '9_TEXT': { color: 4, ltype: 'CONTINUOUS' },
  'TEXT-4': { color: 7, ltype: 'CONTINUOUS' },
  LV: { color: 1, ltype: 'CONTINUOUS' },
  'DETAIL-REF': { color: 5, ltype: 'CONTINUOUS' },
  'PS-TAG': { color: 1, ltype: 'CONTINUOUS' },
};
export const OFFICE_TEXT_STYLE = { name: 'BW', font: 'isocp.shx', widthFactor: 0.8 };
const CALL_H = 150, LEN_H = 150, DIM_H = 250, DIM_TICK = 150, DIM_EXO = 50, DIM_EXE = 100, DOT_R = 33;

export const DETAILS = {
  D1: 'TYPICAL SLAB EDGE DETAIL WITH EDGE BEAM',
  D2: 'TYPICAL SLAB EDGE DETAIL AT ANY CORE OR RETAINING WALLS',
  D3: 'TYPICAL DETAIL AT VARYING SLAB THICKNESS',
  D4: 'TYPICAL COLUMN DROP DETAIL',
  D5: 'TYPICAL SLAB DETAIL AT CORE WALL AND SLAB CORNERS',
  D7: 'TYPICAL MEP VOID DETAIL',
  D12: 'TYPICAL PUNCHING DETAIL',
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

    // edge beams: a parallel line pair on a beam layer within 400 mm of a slab edge
    const beamLines = raw.filter((e) => e.type === 'LINE' && /BEAM/i.test(e.layer)).map((e) => ({ a: { x: e.x, y: e.y }, b: { x: e.x2, y: e.y2 } }));
    level.edges = [];
    for (let i = 0; i < outline.length; i++) {
      const a = outline[i], b = outline[(i + 1) % outline.length];
      const L = dist(a, b);
      if (L < 300) continue;
      const u = unit(a, b);
      const withBeam = beamLines.some((bl) => {
        const ub = unit(bl.a, bl.b);
        if (Math.abs(ub.x * u.x + ub.y * u.y) < 0.98) return false;
        const d1 = distToSeg(bl.a, a, b), d2 = distToSeg(bl.b, a, b);
        if (Math.min(d1, d2) > 400) return false;
        const t1 = ((bl.a.x - a.x) * u.x + (bl.a.y - a.y) * u.y), t2 = ((bl.b.x - a.x) * u.x + (bl.b.y - a.y) * u.y);
        const lo = Math.max(0, Math.min(t1, t2)), hi = Math.min(L, Math.max(t1, t2));
        return hi - lo > 0.5 * L || hi - lo > 2000;
      });
      level.edges.push({ a, b, beam: withBeam });
    }

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
  const notForDesign = /Top bars over columns not specified|Edge U-bars not specified|Opening trimmers not specified|Void trimmers not specified|Stock bar length|No plan title found near slab/;
  model.assumptions = model.assumptions.filter((a) => !notForDesign.test(a.text) && !(a.text.startsWith('Slab thickness not stated') && model.levels.some((l) => l.id === a.level && l.thicknessSource)));
  model.design = { units: model.source.units };
  return model;
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

  // ---- D1 slab edge with edge beam: T10-200 L-bars (T) 1200 into the slab
  for (const e of level.edges || []) {
    if (!e.beam) continue;
    const { runs, u } = blockedAlong(e.a, e.b);
    const nIn = inward(e.a, e.b, outline);
    for (const [t1, t2] of runs) {
      const len = t2 - t1;
      if (len < 1200) continue;
      const p1 = add(e.a, u, t1), p2 = add(e.a, u, t2);
      const m = add(e.a, u, (t1 + t2) / 2);
      const count = Math.floor(len / 200) + 1;
      items.push({ detail: 'D1', face: 'T', a: m, b: add(m, nIn, 1200), l1: 'T10-200 LBAR (T)', l2: 'L=1600', dist: { p: add(p1, nIn, 700), q: add(p2, nIn, 700) }, side: 1, zone: gridRef(level, bbox([p1, p2])) });
      addBar('T', { dia: 10, shape: 'L 1200+400', length: 1600, qty: count, spacing: 200, zone: 'D1 EDGE BEAM' });
      if (!level.topMesh) { items.push({ detail: 'D1', face: 'T', a: add(p1, nIn, 600), b: add(p2, nIn, 600), l1: 'T10-250 DIST. (T)', l2: `L=${Math.round(len)}`, side: -1, noTag: true }); addBar('T', { dia: 10, shape: 'STR', length: Math.round(len), qty: Math.floor(1200 / 250) + 1, spacing: 250, zone: 'D1 EDGE BEAM' }); }
    }
  }

  // ---- D2 core walls: U-bars T12@200 + 10T12 (T&B) along the wall face
  const lc = ceilTo(h - cover, 10);
  for (const w of level.walls || []) {
    const poly = w.polygon;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      const L = dist(a, b);
      if (L < 1500) continue;
      const u = unit(a, b), n = perp(u);
      // slab side of this face: the side where a point 600 mm away lies in the slab
      const m = mid(a, b);
      const s1 = add(m, n, 600), s2 = add(m, n, -600);
      const dirOut = inSlab(s1) ? 1 : inSlab(s2) ? -1 : 0;
      if (!dirOut) continue;
      const nOut = { x: n.x * dirOut, y: n.y * dirOut };
      // LA follows the designer's wall top bar length next to this face when there is one
      const la0 = (level.wallBarLengths || []).filter((t) => distToSeg(t, a, b) < 2500 && inSlab(add(m, nOut, 300))).sort((p, q) => q.L - p.L)[0];
      const LA = la0 ? la0.L : 1200;
      const count = Math.floor(L / 200) + 1;
      items.push({ detail: 'D2', face: 'TB', a: m, b: add(m, nOut, 1200), l1: 'T12-200 U-BAR', l2: `L=${LA + 1200 + lc}`, dist: { p: add(a, nOut, 700), q: add(b, nOut, 700) }, side: 1, zone: `${w.id} ${gridRef(level, bbox(poly))}` });
      addBar('T', { dia: 12, shape: `U ${LA}/${lc}/1200`, length: LA + 1200 + lc, qty: count, spacing: 200, zone: `D2 ${w.id}` });
      const par = Math.min(12000, Math.round(L + 1200));
      items.push({ detail: 'D2', face: 'TB', a: add(add(a, nOut, 400), u, -600), b: add(add(b, nOut, 400), u, 600), l1: '10T12 (T&B)', l2: `L=${par}`, side: -1, noTag: true });
      addBar('T', { dia: 12, shape: 'STR', length: par, qty: 5, zone: `D2 ${w.id}` });
      addBar('B', { dia: 12, shape: 'STR', length: par, qty: 5, zone: `D2 ${w.id}` });
      if (!la0) assumptions.push(`D2 AT ${w.id}: NO DESIGNER'S WALL BAR LENGTH FOUND NEXT TO THE FACE; LA = 1200 mm USED.`);
    }
  }

  // ---- D3 / D4 thickness zones
  for (const z of level.thickZones || []) {
    const b = bbox(z.polygon);
    notes.push({ x: b.cx, y: b.maxY + 350, text: `LAP 500 TYP. AT ${z.thickness || 'THK.'} / ${h} STEP (DET.3)` });
    const ext = 50 * 12;
    const runX = { a: { x: b.minX - ext, y: b.minY + b.h * 0.42 }, b: { x: b.maxX + ext, y: b.minY + b.h * 0.42 } };
    const runY = { a: { x: b.minX + b.w * 0.62, y: b.minY - ext }, b: { x: b.minX + b.w * 0.62, y: b.maxY + ext } };
    const Lx = Math.round(runX.b.x - runX.a.x), Ly = Math.round(runY.b.y - runY.a.y);
    items.push({ detail: 'D4', face: 'B', a: runX.a, b: runX.b, l1: 'T12-250 (B) EXTRA', l2: `L=${Lx}`, dist: { p: { x: b.minX + b.w * 0.35, y: b.minY }, q: { x: b.minX + b.w * 0.35, y: b.maxY } }, side: 1, zone: `${z.id} ${gridRef(level, b)}` });
    items.push({ detail: 'D4', face: 'B', a: runY.a, b: runY.b, l1: 'T12-250 (B) EXTRA', l2: `L=${Ly}`, dist: { p: { x: b.minX, y: b.minY + b.h * 0.72 }, q: { x: b.maxX, y: b.minY + b.h * 0.72 } }, side: -1, noTag: true });
    addBar('B', { dia: 12, shape: 'STR', length: Lx, qty: Math.floor(b.h / 250) + 1, spacing: 250, zone: `D4 ${z.id}` });
    addBar('B', { dia: 12, shape: 'STR', length: Ly, qty: Math.floor(b.w / 250) + 1, spacing: 250, zone: `D4 ${z.id}` });
  }

  // ---- D5 corners: convex wall corners inside the slab (3T16) and re-entrant slab corners (3T12)
  const corner = (c, bis, dia, zone) => {
    const dir = perp(bis);
    const ctr = add(c, bis, 350);
    items.push({ detail: 'D5', face: 'TB', a: add(ctr, dir, -1000), b: add(ctr, dir, 1000), l1: `3T${dia}-200 (T&B)`, l2: 'L=2000', side: 1, zone, triple: true });
    addBar('T', { dia, shape: 'STR', length: 2000, qty: 3, spacing: 200, zone });
    addBar('B', { dia, shape: 'STR', length: 2000, qty: 3, spacing: 200, zone });
  };
  for (const w of level.walls || []) {
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
    if ((level.walls || []).some((w) => w.polygon.some((p) => distToPolygon(p, poly) < 300))) continue;
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
    sides.forEach((s, i) => {
      const L = Math.max(1500, Math.round(dist(s.a, s.b) + 1200));
      const u = unit(s.a, s.b);
      items.push({ detail: 'D7', face: 'TB', a: add(s.a, u, -600), b: add(s.b, u, 600), l1: `${row.long.n}T${row.long.dia}-${row.long.s} (T&B)`, l2: `L=${L}`, side: 1, zone, noTag: i > 0 });
      addBar('T', { dia: row.long.dia, shape: 'STR', length: L, qty: row.long.n, spacing: row.long.s, zone });
      addBar('B', { dia: row.long.dia, shape: 'STR', length: L, qty: row.long.n, spacing: row.long.s, zone });
      const m = mid(s.a, s.b);
      const count = Math.floor(dist(s.a, s.b) / row.u.s) + 1;
      if (i < 2) items.push({ detail: 'D7', face: 'TB', a: add(m, s.n, -150), b: add(m, s.n, lb), l1: `T${row.u.dia}-${row.u.s} U-BAR`, l2: `LB=${lb}`, side: -1, noTag: true });
      addBar('T', { dia: row.u.dia, shape: `U ${lb}/${lc}/${lb}`, length: 2 * lb + lc, qty: count, spacing: row.u.s, zone });
    });
    const d = 1000 / Math.SQRT2;
    for (const [cx, cy, sx, sy] of [[b.minX, b.minY, -1, -1], [b.maxX, b.minY, 1, -1], [b.maxX, b.maxY, 1, 1], [b.minX, b.maxY, -1, 1]]) {
      const ctr = { x: cx + sx * 250, y: cy + sy * 250 };
      const dir = { x: sx, y: -sy };
      items.push({ detail: 'D7', face: 'TB', a: { x: ctr.x - dir.x * d, y: ctr.y - dir.y * d }, b: { x: ctr.x + dir.x * d, y: ctr.y + dir.y * d }, l1: `T${row.diag} (T&B)`, l2: 'L=2000', side: 1, noTag: true });
    }
    addBar('T', { dia: row.diag, shape: 'STR', length: 2000, qty: 4, zone });
    addBar('B', { dia: row.diag, shape: 'STR', length: 2000, qty: 4, zone });
  }

  // ---- D12 punching tags (preliminary: PS1 everywhere until the punching design is available)
  const punching = [];
  for (const c of level.columns) {
    const edge = distToPolygon({ x: c.cx, y: c.cy }, outline) < Math.max(c.w, c.h) + 200;
    punching.push({ col: c, type: edge ? 'PS2' : 'PS1', tag: edge ? '12R-4-T12' : '10R-4-T12', rows: edge ? 12 : 10, legs: 4, dia: 12, s: 100 });
  }
  const psTypes = [
    { id: 'PS1', short: '10R-4-T12', long: '10R-4-T12', s: 100, where: 'INTERIOR COLUMNS' },
    { id: 'PS2', short: '12R-4-T12', long: '12R-4-T12', s: 100, where: 'EDGE / CORNER COLUMNS' },
  ].filter((t) => punching.some((p) => p.type === t.id));
  const linkLen = Math.round(2 * (h - 2 * cover) + 2 * 100 + 2 * 75);
  for (const p of punching) bars.T.add({ dia: 12, shape: 'LINK', length: linkLen, qty: p.rows * p.legs * 2, spacing: p.s, zone: `D12 ${p.type} ${p.col.id}`, note: 'PUNCHING' });

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
const readableRot = (u) => { let r = (Math.atan2(u.y, u.x) * 180) / Math.PI; let flip = 1; if (r > 90 || r <= -90) { r += 180; flip = -1; } return { rot: r, flip }; };

/** The distribution indicator: a red dimension with arch ticks and a green number (DIM100 look). */
function officeDim(pl, S, p, q, opts = {}) {
  const L = dist(p, q);
  if (L < 1) return;
  const u = unit(p, q), n = perp(u);
  const off = opts.offset || 0; // dimension line offset from p-q along n
  const a = add(p, n, off), b = add(q, n, off);
  const lay = { layer: 'diamension' };
  pl.line(a, b, lay);
  for (const c of [a, b]) {
    pl.line(add(add(c, u, -DIM_TICK * 0.5), n, -DIM_TICK * 0.5), add(add(c, u, DIM_TICK * 0.5), n, DIM_TICK * 0.5), lay);
  }
  if (off) { pl.line(add(p, n, Math.sign(off) * DIM_EXO), add(a, n, Math.sign(off) * DIM_EXE), lay); pl.line(add(q, n, Math.sign(off) * DIM_EXO), add(b, n, Math.sign(off) * DIM_EXE), lay); }
  const { rot } = readableRot(u);
  const tm = opts.textAt || add(mid(a, b), n, DIM_H * 0.5);
  pl.text(tm, opts.text ?? String(Math.round(L)), { layer: 'diamension', color: 3, h: DIM_H / S, rot, align: 'C', valign: 'B', style: 'BW', widthFactor: 0.8 });
}

function officeDot(pl, S, p) {
  pl.circle(p, DOT_R, { layer: 'DOTS' });
  pl.hatch([R.regionPolygon({ kind: 'circle', cx: p.x, cy: p.y, r: DOT_R })], { layer: 'DOTS', pattern: 'SOLID' });
}

/** One added bar in the office convention. */
export function officeBar(pl, S, it) {
  const layer = it.face === 'B' ? 'REO-BOT' : 'REO-TOP';
  const u = unit(it.a, it.b), n = perp(u);
  const { rot, flip } = readableRot(u);
  const side = (it.side || 1) * flip;
  pl.line(it.a, it.b, { layer });
  if (it.triple) { pl.line(add(it.a, n, 200), add(it.b, n, 200), { layer }); pl.line(add(it.a, n, -200), add(it.b, n, -200), { layer }); }
  const m = mid(it.a, it.b);
  const t1 = add(m, n, side * 60), t2 = add(m, n, -side * 60);
  const to = { layer: 'REO-TXT', style: 'BW', widthFactor: 0.8, rot, align: 'C' };
  pl.text(side > 0 ? t1 : t2, it.l1, { ...to, h: CALL_H / S, valign: side > 0 ? 'B' : 'T' });
  pl.text(side > 0 ? t2 : t1, it.l2, { ...to, h: LEN_H / S, valign: side > 0 ? 'T' : 'B' });
  if (it.dist) {
    officeDim(pl, S, it.dist.p, it.dist.q);
    // the dot where the bar axis crosses the distribution line
    const du = unit(it.dist.p, it.dist.q);
    const t = (m.x - it.dist.p.x) * du.x + (m.y - it.dist.p.y) * du.y;
    officeDot(pl, S, add(it.dist.p, du, Math.max(0, Math.min(dist(it.dist.p, it.dist.q), t))));
  }
  if (it.detail && !it.noTag) {
    const c = add(m, n, side * 520);
    pl.circle(c, 150, { layer: 'DETAIL-REF' });
    pl.text(c, it.detail, { layer: 'DETAIL-REF', h: 130 / S, align: 'C', valign: 'M', bold: true });
  }
}

/** The designer's own reinforcement, re-emitted verbatim in the same convention. */
export function drawExisting(pl, S, ex, faces) {
  const keep = (f) => faces.includes(f);
  for (const l of ex.lines.filter((x) => keep(x.face))) pl.line(l.a, l.b, { layer: /BOT/i.test(l.layer) || l.face === 'B' ? 'REO-BOT' : 'REO-TOP' });
  for (const c of ex.callouts.filter((x) => keep(x.face))) pl.text({ x: c.x, y: c.y }, c.text, { layer: 'REO-TXT', style: 'BW', widthFactor: c.widthFactor || 0.8, h: (c.h || CALL_H) / S, rot: c.rot, align: ['L', 'C', 'R'][c.halign] || 'L', valign: 'B' });
  for (const d of ex.dims.filter((x) => keep(x.face))) drawDimension(pl, S, d);
  for (const d of ex.dots.filter((x) => keep(x.face))) officeDot(pl, S, d);
}

/** A DIMENSION entity (rotated or aligned) drawn as the DIM100 geometry: red lines, arch ticks, green number. */
export function drawDimension(pl, S, e) {
  if (e.x3 == null || e.x4 == null) return;
  const p3 = { x: e.x3, y: e.y3 }, p4 = { x: e.x4, y: e.y4 }, dp = { x: e.x, y: e.y };
  let u;
  if (e.dimType === 1) u = unit(p3, p4);
  else { const r = ((e.rotation || 0) * Math.PI) / 180; u = { x: Math.cos(r), y: Math.sin(r) }; }
  if (!Number.isFinite(u.x) || (Math.abs(u.x) < 1e-9 && Math.abs(u.y) < 1e-9)) return;
  const n = perp(u);
  const along = (p) => (p.x - dp.x) * u.x + (p.y - dp.y) * u.y;
  const a = add(dp, u, along(p3)), b = add(dp, u, along(p4));
  const lay = { layer: 'diamension' };
  pl.line(a, b, lay);
  for (const [c, src] of [[a, p3], [b, p4]]) {
    pl.line(add(add(c, u, -DIM_TICK * 0.5), n, -DIM_TICK * 0.5), add(add(c, u, DIM_TICK * 0.5), n, DIM_TICK * 0.5), lay);
    const off = (c.x - src.x) * n.x + (c.y - src.y) * n.y;
    if (Math.abs(off) > DIM_EXO + 1) pl.line(add(src, n, Math.sign(off) * DIM_EXO), add(c, n, Math.sign(off) * DIM_EXE), lay);
  }
  const { rot } = readableRot(u);
  const tm = e.x2 != null && (e.x2 || e.y2) ? { x: e.x2, y: e.y2 } : add(mid(a, b), n, DIM_H * 0.5);
  const text = e.text && e.text !== '<>' && !/^\s*$/.test(e.text) ? e.text.replace('<>', String(Math.round(e.measure || dist(a, b)))) : String(Math.round(e.measure || dist(a, b)));
  pl.text(tm, text, { layer: 'diamension', color: 3, h: DIM_H / S, rot, align: 'C', valign: 'M', style: 'BW', widthFactor: 0.8 });
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
    for (const z of level.thickZones || []) { const b = bbox(z.polygon); pl.text({ x: b.minX + 500, y: b.maxY - 450 }, `THK ${z.thickness || 'DROP'}`, { layer: 'S-TEXT', h: 200 / S, align: 'L', valign: 'M', style: 'BW', widthFactor: 0.8 }); }
    for (const t of level.rcTags || []) pl.text({ x: t.x, y: t.y }, `RC ${t.thickness}`, { layer: 'S-TEXT', h: 170 / S, align: 'C', valign: 'M', style: 'BW', widthFactor: 0.8 });
  }
}

const detailsKeyRows = (keys) => keys.map((k) => ({ d: k, title: DETAILS[k] }));
const DETAIL_KEY_COLS = [{ key: 'd', title: 'REF', w: 16 }, { key: 'title', title: 'GENERAL DETAIL (SEE THE GENERAL DETAILS SHEET)', w: 160, align: 'L', max: 62 }];

// ------------------------------------------------------------------ sheets
export const DESIGN_SHEETS = [
  { key: 'dframing', base: 'DESIGN_FRAMING_PLAN', title: 'FRAMING PLAN - OUTLINE, COLUMNS, WALLS, OPENINGS, THICKNESS', no: '01' },
  { key: 'dbottom', base: 'DESIGN_BOTTOM_REINFORCEMENT', title: 'BOTTOM REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', no: '02' },
  { key: 'dtop', base: 'DESIGN_TOP_REINFORCEMENT', title: 'TOP REINFORCEMENT PLAN - DESIGN + GENERAL DETAILS', no: '03' },
  { key: 'dpunch', base: 'DESIGN_PUNCHING_SHEAR', title: 'PUNCHING SHEAR REINFORCEMENT PLAN (PRELIMINARY)', no: '04' },
];

const designNotes = (model, level) => [
  commonNotes(model, level)[0],
  `SLAB THICKNESS ${level.thickness} mm${level.tos ? `, ${level.levelTags[0].label} ${level.tos}` : ''}${level.thickZones?.length ? `; THICKENED ZONES ${[...new Set(level.thickZones.map((z) => z.thickness))].join(' / ')} mm HATCHED` : ''}. CONCRETE f'c = ${model.spec.fc} MPa, REINFORCEMENT fy = ${model.spec.fy} MPa, COVER ${model.spec.cover} mm (${model.spec.sources.cover}).`,
  'BAR CALL-OUT (OFFICE CONVENTION): "T10-200 (T)" = BAR SIZE - SPACING (LAYER), "L=2400" = BAR LENGTH; THE RED DIMENSION ACROSS THE BARS IS THE WIDTH OVER WHICH THEY ARE DISTRIBUTED; (T) TOP, (B) BOTTOM, T&B BOTH.',
  'THE REINFORCEMENT DESIGNED BY THE OFFICE IS SHOWN AS DRAWN ON THE DESIGN PLAN. BARS MARKED WITH A CIRCLED "D#" ARE ADDED FROM THE GENERAL DETAILS SHEET (DETAIL NUMBER IN THE CIRCLE) AT THE LOCATIONS THE DETAIL REFERS TO; THE DETAIL GOVERNS FOR SHAPE AND ANCHORAGE.',
];

function framingSheet(model, level, meta, adds) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { regionLabels: true, columnIds: true, gridTag: meta.gridTag, pt: false, ubarRegions: false });
    drawDesignerNotes(pl, S, level);
    for (const e of level.edges.filter((x) => x.beam)) { const m = mid(e.a, e.b); const nIn = inward(e.a, e.b, level.outline); pl.text(add(m, nIn, 450), 'EDGE BEAM', { layer: 'BEAM', h: 1.5, align: 'C', valign: 'M', rot: readableRot(unit(e.a, e.b)).rot }); }
    const rows = [
      ...level.columns.map((c) => ({ id: c.id, element: c.shape === 'circle' ? 'COLUMN (ROUND)' : 'COLUMN', size: c.shape === 'circle' ? `Ø${fmtMM(c.d)}` : `${fmtMM(c.w)} x ${fmtMM(c.h)}`, location: `X ${fmtMM(c.cx)}, Y ${fmtMM(c.cy)}` })),
      ...level.walls.map((w) => ({ id: w.id, element: `WALL ${fmtMM(w.t)} THK`, size: `${fmtMM(w.w)} x ${fmtMM(w.h)}`, location: gridRef(level, bbox(w.polygon)) })),
      ...level.openings.map((o) => ({ id: o.id, element: 'OPENING', size: `${fmtMM(bbox(R.regionPolygon(o)).w)} x ${fmtMM(bbox(R.regionPolygon(o)).h)}`, location: gridRef(level, bbox(R.regionPolygon(o))) })),
      ...level.thickZones.map((z) => ({ id: z.id, element: `THICKENED ZONE ${z.thickness || ''} mm`, size: `${fmtMM(bbox(z.polygon).w)} x ${fmtMM(bbox(z.polygon).h)}`, location: gridRef(level, bbox(z.polygon)) })),
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
      legend: [['OUTLINE', 'SLAB EDGE', 'thick'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL-HATCH', 'WALL (HATCHED)', 'hatch'], ['BEAM', 'EDGE BEAM', 'line'], ['OPENING', 'OPENING (CROSSED)', 'line'], ['SLAB-THK-HATCH', 'THICKENED ZONE', 'hatch']],
      detailsUsed: 3,
    };
  };
}

function rebarSheet(model, level, meta, adds, face) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, pt: false, ubarRegions: false, regionLabels: false });
    drawDesignerNotes(pl, S, level, { thickness: true });
    const faces = face === 'B' ? ['B', 'TB'] : ['T', 'TB'];
    drawExisting(pl, S, level.existing, faces);
    if (face === 'B' || level.topMesh) drawMeshLabels(pl, S, level);
    const mine = adds.items.filter((it) => faces.includes(it.face));
    for (const it of mine) officeBar(pl, S, it);
    if (face === 'T') for (const n of adds.notes) pl.text({ x: n.x, y: n.y }, n.text, { layer: 'DETAIL-REF', h: 150 / S, align: 'C', style: 'BW', widthFactor: 0.8 });
    const list = adds.bars[face];
    const rows = list.rows().filter((r) => r.note !== 'PUNCHING');
    const tot = { weight_kg: Math.round(rows.reduce((s, r) => s + r.weight_kg, 0) * 10) / 10 };
    const used = [...new Set(mine.map((it) => it.detail))].sort();
    const d0 = sheet.detailBox(0, 'GENERAL DETAILS ADDED ON THIS SHEET', '');
    sheet.table(d0.x + 3, d0.y + d0.h - 10, DETAIL_KEY_COLS, detailsKeyRows(used.length ? used : ['D1']), { headH: 5, rowH: 4, h: 1.5, maxRows: 12 });
    const d1 = sheet.detailBox(1, 'MEP VOID REINFORCEMENT (DETAIL 7)', '');
    const vcols = [{ key: 'size', title: 'VOID (m)', w: 26 }, { key: 'long', title: 'LONGITUDINAL T&B (EACH SIDE)', w: 60 }, { key: 'u', title: 'U-BAR', w: 34 }, { key: 'diag', title: 'DIAGONALS T&B (2 m)', w: 50 }];
    sheet.table(d1.x + 3, d1.y + d1.h - 10, vcols, VOID_TABLE.map((r, i) => ({ size: `${i ? VOID_TABLE[i - 1].max : 0} - ${r.max}`, long: `${r.long.n}T${r.long.dia}-${r.long.s}`, u: `T${r.u.dia}-${r.u.s}`, diag: `T${r.diag}` })), { headH: 5, rowH: 4, h: 1.5 });
    const d2 = sheet.detailBox(2, face === 'B' ? 'SECTION - MESH AND EXTRA BOTTOM BARS AT A THICKENED ZONE' : 'SECTION - U-BAR AT A CORE WALL (DETAIL 2)', '1:20');
    const det2 = face === 'B'
      ? D.sectionMesh({ h: level.thickness, cover: model.spec.cover, dia: level.meshSpec?.[0] || 10, lap: R.lapLength(model.spec, level.meshSpec?.[0] || 10), spacing: level.meshSpec?.[1] || 150 })
      : D.sectionUEdge({ h: level.thickness, cover: model.spec.cover, leg: 1200, dia: 12, edgeDia: 12, spacing: 200 });
    det2.draw(sheet.detailPen(d2, 20, det2.bbox));
    const meshLine = level.meshSpec ? `MESH T${level.meshSpec[0]}@${level.meshSpec[1]} ${level.topMesh ? 'BOTTOM & TOP' : 'BOTTOM'} TWO WAY AS LABELLED ON THE PLAN (DESIGN).` : 'NO MESH LABEL FOUND ON THE DESIGN PLAN.';
    return {
      rows, totals: `ADDED FROM THE GENERAL DETAILS: ${tot.weight_kg.toLocaleString('en-US')} kg (DESIGNER'S BARS NOT SCHEDULED HERE)`, weight: tot.weight_kg,
      scheduleTitle: `BAR SCHEDULE - GENERAL DETAILS ADDITIONS (${face === 'B' ? 'BOTTOM' : 'TOP'})`,
      planTitles: [face === 'B' ? 'BOTTOM REINFORCEMENT PLAN' : 'TOP REINFORCEMENT PLAN'],
      general: [...designNotes(model, level), meshLine,
        face === 'B' ? 'BOTTOM SHEET: DETAIL 4 EXTRA BOTTOM BARS INSIDE THICKENED ZONES (50 dia BEYOND THE ZONE), DETAIL 7 VOID TRIMMERS (T&B), DETAIL 2 PARALLEL BARS AND DETAIL 5 DIAGONALS (T&B).'
          : 'TOP SHEET: DETAIL 1 L-BARS ALONG EDGE BEAMS, DETAIL 2 U-BARS AND PARALLEL BARS AT CORE WALLS, DETAIL 5 CORNER DIAGONALS, DETAIL 7 VOID TRIMMERS (T&B); LAP 500 AT THICKNESS STEPS (DETAIL 3).'],
      assumptions: [...adds.assumptions, ...levelAssumptions(model, level), 'ANCHORAGE-DEPENDENT DETAILS (SLAB EDGE AT LIVE ANCHORS, BURSTING SPIRALS, PAN-BOX TRIMMERS) ARE NOT SHOWN: TO BE ADDED WITH THE TENDON LAYOUT.'],
      legend: [[face === 'B' ? 'REO-BOT' : 'REO-TOP', face === 'B' ? 'BOTTOM BAR (B)' : 'TOP BAR (T)', 'thick'], ['diamension', 'DISTRIBUTION WIDTH', 'line'], ['DOTS', 'BAR / DISTRIBUTION DOT', 'line'], ['DETAIL-REF', 'D# = GENERAL DETAIL REFERENCE', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid'], ['WALL-HATCH', 'WALL', 'hatch']],
      detailsUsed: 3,
    };
  };
}

function punchingSheet(model, level, meta, adds) {
  return (sheet, [pl]) => {
    const S = sheet.S;
    drawBase(sheet, pl, level, { gridTag: meta.gridTag, dims: false, pt: false, ubarRegions: false, regionLabels: false, columnIds: true });
    for (const p of adds.punching) {
      const c = p.col;
      const w = c.shape === 'circle' ? c.d : c.w, hh = c.shape === 'circle' ? c.d : c.h;
      const nRows = Math.min(p.rows, 4);
      for (let r = 1; r <= nRows; r++) {
        const o = r * p.s;
        pl.line({ x: c.cx - w / 2, y: c.cy + hh / 2 + o }, { x: c.cx + w / 2, y: c.cy + hh / 2 + o }, { layer: 'REBAR-PUNCH' });
        pl.line({ x: c.cx - w / 2, y: c.cy - hh / 2 - o }, { x: c.cx + w / 2, y: c.cy - hh / 2 - o }, { layer: 'REBAR-PUNCH' });
        pl.line({ x: c.cx + w / 2 + o, y: c.cy - hh / 2 }, { x: c.cx + w / 2 + o, y: c.cy + hh / 2 }, { layer: 'REBAR-PUNCH' });
        pl.line({ x: c.cx - w / 2 - o, y: c.cy - hh / 2 }, { x: c.cx - w / 2 - o, y: c.cy + hh / 2 }, { layer: 'REBAR-PUNCH' });
      }
      pl.text({ x: c.cx + w / 2 + 550, y: c.cy + hh / 2 + 300 }, p.type, { layer: 'PS-TAG', h: 250 / S, style: 'BW', widthFactor: 0.8, bold: true });
      pl.text({ x: c.cx + w / 2 + 550, y: c.cy + hh / 2 + 60 }, p.tag, { layer: 'PS-TAG', h: 150 / S, style: 'BW', widthFactor: 0.8 });
    }
    const rows = adds.psTypes.map((t) => ({ id: t.id, short: t.short, long: t.long, s: t.s, where: t.where, n: adds.punching.filter((p) => p.type === t.id).length }));
    const cols = [{ key: 'id', title: 'TYPE', w: 18 }, { key: 'short', title: 'SHORT DIR.', w: 34 }, { key: 'long', title: 'LONG DIR.', w: 34 }, { key: 's', title: 'S', w: 16 }, { key: 'n', title: 'No. COLS', w: 22 }, { key: 'where', title: 'WHERE', w: 61, align: 'L', max: 34 }];
    const d0 = sheet.detailBox(0, 'PUNCHING SHEAR REINFORCEMENT PLAN FOR COLUMNS (DETAIL 12)', 'N.T.S.');
    const det0 = D.punchingLink({ h: level.thickness, cover: model.spec.cover, dia: 12, rowSpacing: 100, legSpacing: 100, rows: 4 });
    det0.draw(sheet.detailPen(d0, 10, det0.bbox));
    const d1 = sheet.detailBox(1, 'TAG KEY', '');
    ['PUNCHING SHEAR RFT BAR TAGS   10R-4-T12', '10R - DENOTES NUMBER OF ROWS', '4   - DENOTES NUMBER OF LEGS OF STIRRUPS', 'T12 - DENOTES BAR GRADE AND DIAMETER', 'S   - SPACING OF ROWS (mm)'].forEach((s, i) => sheet.pp.text(d1.x + 4, d1.y + d1.h - 14 - i * 5, s, { layer: 'NOTES', h: 1.8 }));
    return {
      rows, cols, scheduleTitle: 'SCHEDULE OF PUNCHING SHEAR REINFORCEMENT',
      general: [designNotes(model, level)[0], 'PUNCHING SHEAR REINFORCEMENT IS TAGGED PER COLUMN AS "ROWS - LEGS - BAR" (DETAIL 12). ROWS START AT d/2 FROM THE COLUMN FACE AT THE SPACING S; STIRRUPS ENCLOSE THE TOP AND BOTTOM BARS.', 'PRELIMINARY: PS TYPES ARE PLACEHOLDERS (PS1 INTERIOR, PS2 EDGE / CORNER) UNTIL THE PUNCHING DESIGN OF EACH COLUMN IS AVAILABLE; THE DESIGN GOVERNS THE NUMBER OF ROWS AND LEGS.'],
      assumptions: ['PUNCHING DESIGN NOT AVAILABLE: PS1 = 10R-4-T12 @100 (INTERIOR), PS2 = 12R-4-T12 @100 (EDGE / CORNER) ASSUMED FROM THE GENERAL DETAILS SCHEDULE - TO BE CONFIRMED.', ...levelAssumptions(model, level).slice(0, 3)],
      legend: [['REBAR-PUNCH', 'ROWS OF STIRRUPS (FIRST 4 SHOWN)', 'thick'], ['PS-TAG', 'PS TYPE / TAG', 'line'], ['COLUMN-HATCH', 'COLUMN', 'solid']],
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
    ['EACH SHEET IS A BLOCK NAMED AS LISTED AND ALSO A STAND-ALONE DXF FOR XREF ATTACH. INSERT OR XREF AT 0,0, SCALE 1, UNITS mm; PLAN GEOMETRY IS 1:1.', 'REINFORCEMENT LAYERS FOLLOW THE OFFICE DESIGN CONVENTION (REO-TOP, REO-BOT, REO-TXT, diamension, DOTS); SHEET FURNITURE FOLLOWS THE SPAN TECH ST- STANDARD.', 'BARS ADDED FROM THE GENERAL DETAILS CARRY A CIRCLED D# ON LAYER DETAIL-REF (FREEZE THE LAYER TO HIDE THE REFERENCES).'].forEach((h, i) => pp.mtext(d2.x + 4, d2.y + d2.h - 12 - i * 14, h, { layer: 'NOTES', h: 1.8, width: d2.w - 8 }));
    return { general: [`DESIGN DRAWINGS GENERATED FROM THE OFFICE DESIGN PLAN: ${model.levels.length} PART(S) READ.`, ...model.findings], assumptions: model.assumptions.map((a) => (a.level ? `[${a.level}] ` : '') + a.text), legend: [], detailsUsed: 3 };
  };
}

// ------------------------------------------------------------------ package
export function composeDesignPackage(model, metaIn = {}) {
  const meta = {
    company: 'SPAN TECH CONTRACTING', company_line: 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
    project: 'PROJECT NAME', client: '', engineer: '', contractor: '', location: '', prefix: 'ST-DD', revision: '00',
    date: new Date().toISOString().slice(0, 10), prepared: '', checked: '', approved: '', status: 'DESIGN DRAWING - FOR REVIEW',
    ...metaIn,
  };
  const jobs = [];
  for (const level of model.levels) {
    const adds = designAdditions(level, model.spec);
    level.additions = { items: adds.items.length, weight: { T: adds.bars.T.totals().weight_kg, B: adds.bars.B.totals().weight_kg } };
    const makers = { dframing: framingSheet, dbottom: (m, l, mt, a) => rebarSheet(m, l, mt, a, 'B'), dtop: (m, l, mt, a) => rebarSheet(m, l, mt, a, 'T'), dpunch: punchingSheet };
    for (const def of DESIGN_SHEETS) jobs.push({ level, def, draw: makers[def.key](model, level, meta, adds) });
  }
  const total = jobs.length + 1;
  const sheets = jobs.map((j, i) => buildSheet({ model, level: j.level, def: j.def, meta, index: i + 2, total, draw: j.draw }));
  const cover = buildSheet({ model, level: null, def: { key: 'cover', base: 'DESIGN_DRAWINGS_COVER_INDEX', title: 'COVER SHEET / DRAWING INDEX', no: '000' }, meta, index: 1, total, draw: designCover(model, sheets, meta) });
  const all = [cover, ...sheets];
  for (const s of all) {
    for (const [n, d] of Object.entries(OFFICE_LAYERS)) s.root.layer(n, d);
    s.root.textStyleDef(OFFICE_TEXT_STYLE.name, { font: OFFICE_TEXT_STYLE.font, widthFactor: OFFICE_TEXT_STYLE.widthFactor });
  }
  return packSheets(all, meta, { textStyles: { [OFFICE_TEXT_STYLE.name]: { font: OFFICE_TEXT_STYLE.font, widthFactor: OFFICE_TEXT_STYLE.widthFactor } } });
}
