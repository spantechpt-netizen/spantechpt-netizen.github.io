/**
 * Reads the combined structural drawing and pulls out what the rebar sheets
 * need: slab outlines per level, grid, columns, PT zones, openings, voids and
 * U-bar regions, plus any design data written in the notes.
 *
 * Nothing is asked of the user: where the drawing is silent an assumption
 * is recorded and printed on the sheet.
 */
import { bbox, expandBbox, bboxContains, cleanPolygon, polygonArea, asAxisRect, pointInPolygon, centroid, transformPoint, dist, rectPolygon, circlePolygon } from './geometry.mjs';
import { DEFAULT_SPEC } from './rebar.mjs';

const LAYER_RULES = [
  ['grid', /GRID|AXIS|AXES|محور|محاور/i],
  ['ubar', /U[-_ ]?BARS?|HAIRPIN/i],
  ['void', /VOID|ACU|ACOU|AKWAR|أكوار|اكوار|كور|HOLLOW|COBIAX|BUBBLE/i],
  ['opening', /OPEN|SHAFT|DUCT|فتح|HOLE|SLEEVE/i],
  ['pt', /(^|[^A-Z])PT([^A-Z]|$)|P-T|TENDON|POST[-_ ]?TEN|كابل|كوابل/i],
  ['column', /COL(?!OR)|COLUMN|عمود|أعمدة|اعمدة/i],
  ['slab', /SLAB|OUTLINE|EDGE|BOUND|حدود|بلاطة|SOG|DECK/i],
  ['notes', /NOTE|TEXT|ANNO|ملاحظ/i],
];

export function classifyLayer(name) {
  for (const [kind, rx] of LAYER_RULES) if (rx.test(name)) return kind;
  return 'other';
}

/** Explode INSERTs so block geometry becomes plain entities in drawing coordinates. */
function flatten(dxf) {
  const out = [];
  const walk = (ents, t, depth, blockName, sink) => {
    for (const e of ents) {
      if (e.type === 'INSERT') {
        const blk = dxf.blocks.get(e.name);
        if (!blk || depth > 4) continue;
        const tt = { x: e.x, y: e.y, sx: e.sx ?? 1, sy: e.sy ?? e.sx ?? 1, rotation: e.rotation || 0 };
        const shifted = blk.entities.map((be) => shiftEntity(be, blk.base));
        const inner = [];
        walk(shifted, null, depth + 1, e.name, inner);
        const placed = inner.map((ie) => transformEntity(ie, tt));
        const outer = t ? placed.map((ie) => transformEntity(ie, t)) : placed;
        sink.push(...outer);
        // Record the insert itself as a candidate column / symbol with its exploded bbox.
        const pts = outer.flatMap(entityPoints);
        const at = t ? transformPoint({ x: e.x, y: e.y }, t) : { x: e.x, y: e.y };
        sink.push({ type: 'INSERT', layer: e.layer, name: e.name, x: at.x, y: at.y, pts, blockBbox: pts.length ? bbox(pts) : null });
        continue;
      }
      const te = t ? transformEntity(e, t) : { ...e };
      te.fromBlock = blockName || null;
      sink.push(te);
    }
  };
  walk(dxf.entities, null, 0, null, out);
  return out;
}

function shiftEntity(e, base) {
  if (!base || (!base.x && !base.y)) return e;
  return transformEntity(e, { x: -base.x, y: -base.y, sx: 1, sy: 1, rotation: 0 });
}

function transformEntity(e, t) {
  const T = (p) => transformPoint(p, t);
  const scale = Math.abs(t.sx || 1);
  const c = { ...e };
  const p = T({ x: e.x, y: e.y });
  c.x = p.x; c.y = p.y;
  if (e.x2 != null) { const q = T({ x: e.x2, y: e.y2 }); c.x2 = q.x; c.y2 = q.y; }
  if (e.pts) c.pts = e.pts.map((q) => ({ ...q, ...T(q) }));
  if (e.paths) c.paths = e.paths.map((path) => path.map((q) => T(q)));
  if (e.r != null) c.r = e.r * scale;
  if (e.height != null) c.height = e.height * scale;
  if (e.rotation != null && e.type === 'TEXT') c.rotation = (e.rotation || 0) + (t.rotation || 0);
  return c;
}

function entityPoints(e) {
  switch (e.type) {
    case 'LINE': return [{ x: e.x, y: e.y }, { x: e.x2, y: e.y2 }];
    case 'LWPOLYLINE': case 'SOLID': case 'TRACE': return e.pts;
    case 'CIRCLE': case 'ARC': return [{ x: e.x - e.r, y: e.y - e.r }, { x: e.x + e.r, y: e.y + e.r }];
    case 'HATCH': return e.paths.flat();
    case 'TEXT': case 'MTEXT': return [{ x: e.x, y: e.y }];
    default: return [];
  }
}

function closedPolys(e) {
  // Closed polygons carried by an entity (polyline, solid or hatch path).
  if (e.type === 'LWPOLYLINE') {
    const pts = cleanPolygon(e.pts);
    const closed = e.closed || (e.pts.length > 3 && dist(e.pts[0], e.pts[e.pts.length - 1]) < 1);
    return closed && pts.length >= 3 ? [pts] : [];
  }
  if (e.type === 'SOLID' || e.type === 'TRACE') return [cleanPolygon(e.pts)];
  if (e.type === 'HATCH') return e.paths.map(cleanPolygon).filter((p) => p.length >= 3);
  return [];
}

const textOf = (e) => (e.text || '').trim();

export function detectUnits(dxf, ents) {
  const u = dxf.header.$INSUNITS;
  if (u === 4) return { scale: 1, name: 'mm', source: '$INSUNITS' };
  if (u === 6) return { scale: 1000, name: 'm', source: '$INSUNITS' };
  if (u === 5) return { scale: 10, name: 'cm', source: '$INSUNITS' };
  const pts = ents.flatMap(entityPoints);
  if (!pts.length) return { scale: 1, name: 'mm', source: 'assumed' };
  const b = bbox(pts);
  const extent = Math.max(b.w, b.h);
  if (extent < 500) return { scale: 1000, name: 'm', source: 'inferred from extents' };
  if (extent < 5000) return { scale: 10, name: 'cm', source: 'inferred from extents' };
  return { scale: 1, name: 'mm', source: 'inferred from extents' };
}

function scaleEntity(e, k) {
  if (k === 1) return e;
  return transformEntity(e, { x: 0, y: 0, sx: k, sy: k, rotation: 0 });
}

/** Region shape from a closed polygon or circle entity. */
function regionFrom(e, poly) {
  if (e.type === 'CIRCLE') return { kind: 'circle', cx: e.x, cy: e.y, r: e.r };
  const rect = asAxisRect(poly, 5);
  if (rect) return { kind: 'rect', rect };
  // circle drawn as bulged polyline
  const b = bbox(poly);
  if (poly.length >= 8 && Math.abs(b.w - b.h) < 0.05 * b.w) {
    const c = centroid(poly);
    const rs = poly.map((p) => dist(p, c));
    const r = rs.reduce((s, v) => s + v, 0) / rs.length;
    if (rs.every((v) => Math.abs(v - r) < 0.05 * r)) return { kind: 'circle', cx: c.x, cy: c.y, r };
  }
  return { kind: 'polygon', polygon: polygonArea(poly) < 0 ? [...poly].reverse() : poly };
}

const regionCenter = (r) => (r.kind === 'circle' ? { x: r.cx, y: r.cy } : r.kind === 'rect' ? { x: r.rect.x + r.rect.w / 2, y: r.rect.y + r.rect.h / 2 } : centroid(r.polygon));
const regionArea = (r) => (r.kind === 'circle' ? Math.PI * r.r * r.r : r.kind === 'rect' ? r.rect.w * r.rect.h : Math.abs(polygonArea(r.polygon)));

export function extractModel(dxf, options = {}) {
  const assumptions = [];
  const findings = [];
  const raw = flatten(dxf);
  const units = detectUnits(dxf, raw);
  const ents = raw.map((e) => scaleEntity(e, units.scale));
  if (units.source !== '$INSUNITS') assumptions.push({ text: `Drawing units not declared; ${units.name} ${units.source}.` });
  findings.push(`Drawing units: ${units.name} (${units.source}); ${ents.length} entities read.`);

  for (const e of ents) e.kind = classifyLayer(e.layer + ' ' + (e.name || ''));
  const texts = ents.filter((e) => (e.type === 'TEXT' || e.type === 'MTEXT') && textOf(e));

  // ---------------------------------------------------------- slab outlines
  let outlines = [];
  for (const e of ents.filter((x) => x.kind === 'slab')) for (const p of closedPolys(e)) if (Math.abs(polygonArea(p)) > 10e6) outlines.push(p);
  if (!outlines.length) {
    const cands = [];
    for (const e of ents.filter((x) => x.kind !== 'grid' && x.type === 'LWPOLYLINE')) for (const p of closedPolys(e)) if (Math.abs(polygonArea(p)) > 20e6) cands.push(p);
    outlines = cands.filter((p) => !cands.some((q) => q !== p && Math.abs(polygonArea(q)) > Math.abs(polygonArea(p)) && pointInPolygon(p[0], q)));
    if (outlines.length) assumptions.push({ text: 'No slab outline layer found: the largest closed polylines were taken as slab outlines.' });
  }
  if (!outlines.length) {
    const pts = ents.filter((e) => e.kind === 'column').flatMap(entityPoints);
    const b = bbox(pts.length ? pts : ents.flatMap(entityPoints));
    outlines = [rectPolygon({ x: b.minX - 1000, y: b.minY - 1000, w: b.w + 2000, h: b.h + 2000 })];
    assumptions.push({ text: 'No slab outline could be read: a rectangle 1.0 m outside the column extents was assumed as the slab edge.' });
  }
  outlines = outlines.map((p) => (polygonArea(p) < 0 ? [...p].reverse() : p));
  // Plans usually sit side by side left to right, then top to bottom.
  outlines.sort((a, b) => { const A = bbox(a), B = bbox(b); return Math.abs(A.minY - B.minY) > Math.max(A.h, B.h) * 0.5 ? B.minY - A.minY : A.minX - B.minX; });

  // ---------------------------------------------------------- global design data
  const allText = texts.map(textOf).join('\n');
  const spec = readSpecFromText(allText, assumptions, options.spec || {});

  const levels = outlines.map((outline, i) => buildLevel(outline, i, ents, texts, spec, assumptions, findings));
  const codeRef = spec.code_reference;
  return {
    source: { units: units.name, entities: ents.length, layers: [...new Set(ents.map((e) => e.layer))].sort() },
    code_reference: codeRef,
    spec,
    levels,
    assumptions,
    findings,
  };
}

export function readSpecFromText(text, assumptions, overrides = {}) {
  const spec = JSON.parse(JSON.stringify(DEFAULT_SPEC));
  const src = {};
  const T = text.toUpperCase();
  let m;
  const code = T.match(/SBC\s*[- ]?\d{3}(?:[- ]?\d{2,4})?/) || T.match(/ACI\s*[- ]?318(?:[- ]?\d{2})?/) || T.match(/BS\s*[- ]?8110/) || T.match(/EN\s*1992|EUROCODE\s*2|EC\s*2/);
  if (code) { spec.code_reference = code[0].replace(/\s+/g, ' ').trim(); src.code = 'drawing'; }
  else { spec.code_reference = null; src.code = 'assumed'; assumptions.push({ text: 'Design code not stated on the drawings: SBC 304-18 (Saudi Building Code, based on ACI 318-14) applied for development, anchorage and lap lengths. To be adjusted on receipt of the final design criteria.' }); }

  if ((m = T.match(/F['’`]?C\s*[=:]?\s*(\d{2})/)) || (m = T.match(/C\s?(\d{2})\/\d{2}/)) || (m = T.match(/CONCRETE[^0-9\n]{0,40}(\d{2})\s*(?:MPA|N\/MM)/))) { spec.fc = parseInt(m[1], 10); src.fc = 'drawing'; }
  else { src.fc = 'assumed'; assumptions.push({ text: `Concrete grade not stated: f'c = ${spec.fc} MPa assumed (conservative for anchorage lengths).` }); }
  if ((m = T.match(/F\s*Y\s*[=:]?\s*(\d{3})/)) ) { spec.fy = parseInt(m[1], 10); src.fy = 'drawing'; }
  else if ((m = T.match(/GRADE\s*(60|420|500)/))) { spec.fy = m[1] === '60' ? 420 : parseInt(m[1], 10); src.fy = 'drawing'; }
  else { src.fy = 'assumed'; assumptions.push({ text: `Reinforcement grade not stated: fy = ${spec.fy} MPa (Grade 60) assumed.` }); }
  if ((m = T.match(/COVER[^0-9\n]{0,25}(\d{2})/))) { spec.cover = parseInt(m[1], 10); src.cover = 'drawing'; }
  else { src.cover = 'assumed'; assumptions.push({ text: `Concrete cover not stated: ${spec.cover} mm top and bottom assumed for slabs (SBC 304-18 Table 20.6.1.3.1).` }); }

  // Bar specs with a context word on the same line.
  const barRx = /(?:T|Y|H|N|D|#|Ø|Φ|DIA\.?)?\s*(\d{2})\s*@\s*(\d{2,3})/gi;
  const lines = text.split(/\n/);
  const found = [];
  for (const line of lines) {
    const U = line.toUpperCase();
    let mm;
    barRx.lastIndex = 0;
    while ((mm = barRx.exec(line))) {
      const dia = parseInt(mm[1], 10), spacing = parseInt(mm[2], 10);
      if (dia < 8 || dia > 40 || spacing < 50 || spacing > 600) continue;
      let target = null;
      if (/BOT|SOFFIT|BOTTOM|B\.?W\.?|MESH/.test(U) && !/TOP/.test(U)) target = 'bottom';
      else if (/TOP|OVER\s*COL|COLUMN|SUPPORT/.test(U)) target = 'topColumns';
      else if (/U[- ]?BAR|HAIRPIN/.test(U)) target = 'uEdge';
      else if (/OPEN/.test(U)) target = 'openings';
      else if (/VOID/.test(U)) target = 'voids';
      if (!target) continue;
      spec[target] = { ...spec[target], dia, spacing };
      found.push(`${target}: T${dia}@${spacing} from note "${line.trim().slice(0, 60)}"`);
    }
  }
  if (!found.some((f) => f.startsWith('bottom'))) assumptions.push({ text: `Bottom mesh not specified: T${spec.bottom.dia}@${spec.bottom.spacing} both ways assumed as bonded reinforcement in PT zones.` });
  if (!found.some((f) => f.startsWith('topColumns'))) assumptions.push({ text: `Top bars over columns not specified: T${spec.topColumns.dia}@${spec.topColumns.spacing} both ways assumed within c + 3h, checked against As,min = 0.00075·Acf (SBC 304-18 §8.6.2.3).` });
  if (!found.some((f) => f.startsWith('uEdge'))) assumptions.push({ text: `Edge U-bars not specified: T${spec.uEdge.dia}@${spec.uEdge.spacing} with ${spec.uEdge.leg} mm legs assumed at PT anchorage edges.` });
  if (!found.some((f) => f.startsWith('openings'))) assumptions.push({ text: `Opening trimmers not specified: ${spec.openings.count}T${spec.openings.dia} T&B each side + ${spec.openings.diagCount}T${spec.openings.diagDia} diagonals at corners assumed.` });
  if (!found.some((f) => f.startsWith('voids'))) assumptions.push({ text: `Void trimmers not specified: ${spec.voids.count}T${spec.voids.dia} T&B each side assumed.` });
  assumptions.push({ text: `Stock bar length ${spec.stock / 1000} m; laps staggered so that not more than 50 % of bars lap at one section.` });
  Object.assign(spec, overrides);
  spec.sources = src;
  spec.found = found;
  return spec;
}

function buildLevel(outline, index, ents, texts, spec, assumptions, findings) {
  const id = `L${String(index + 1).padStart(2, '0')}`;
  const ob = bbox(outline);
  const region = expandBbox(ob, Math.max(ob.w, ob.h) * 0.25);
  const inRegion = (p) => bboxContains(region, p);
  const near = (p, d = 500) => pointInPolygon(p, outline) || pointInPolygon({ x: p.x + d, y: p.y }, outline) || pointInPolygon({ x: p.x - d, y: p.y }, outline) || pointInPolygon({ x: p.x, y: p.y + d }, outline) || pointInPolygon({ x: p.x, y: p.y - d }, outline);
  const levelTexts = texts.filter((t) => inRegion({ x: t.x, y: t.y }));
  const A = { level: id };

  // ------------------------------------------------------------ name
  const heights = levelTexts.map((t) => t.height || 0).sort((a, b) => a - b);
  const median = heights[Math.floor(heights.length / 2)] || 250;
  const titleRx = /FLOOR|ROOF|LEVEL|SLAB|PLAN|BASEMENT|GROUND|PODIUM|MEZZ|TYPICAL|بلاطة|دور|سقف|أرضي|ارضي|قبو|بدروم/i;
  let name = null;
  const titles = levelTexts.filter((t) => titleRx.test(t.text) && (t.height >= median * 1.5 || t.y < ob.minY)).sort((a, b) => b.height - a.height);
  if (titles.length) name = titles[0].text.replace(/\s+/g, ' ').trim();
  if (!name) { name = `LEVEL ${index + 1}`; assumptions.push({ ...A, text: `No plan title found near slab ${index + 1}: named "${name}".` }); }

  // ------------------------------------------------------------ thickness
  let thickness = null;
  const thkRx = /(?:SLAB\s*)?(?:THK|THICK(?:NESS)?|T\s*=|H\s*=)\s*[:=]?\s*(\d{3})|(\d{3})\s*(?:MM)?\s*(?:THK|THICK)|PT\s*SLAB\s*(\d{3})/i;
  for (const t of [...levelTexts, ...texts]) { const m = t.text.match(thkRx); if (m) { thickness = parseInt(m[1] || m[2] || m[3], 10); break; } }
  if (!thickness) { thickness = 250; assumptions.push({ ...A, text: `Slab thickness not stated for ${name}: ${thickness} mm assumed.` }); }

  // ------------------------------------------------------------ grid
  const gridLines = ents.filter((e) => e.kind === 'grid' && (e.type === 'LINE' || (e.type === 'LWPOLYLINE' && e.pts.length === 2)));
  const gx = [], gy = [];
  const labelFor = (p) => {
    let best = null;
    for (const t of texts) {
      const s = t.text.trim();
      if (s.length > 3 || /\s/.test(s)) continue;
      const d = dist({ x: t.x, y: t.y }, p);
      if (d < 3000 && (!best || d < best.d)) best = { d, s };
    }
    return best ? best.s : null;
  };
  for (const g of gridLines) {
    const a = g.type === 'LINE' ? { x: g.x, y: g.y } : g.pts[0];
    const b = g.type === 'LINE' ? { x: g.x2, y: g.y2 } : g.pts[1];
    const len = dist(a, b);
    if (len < 1000) continue;
    const touches = (a.x >= region.minX && a.x <= region.maxX && ((a.y <= region.maxY && b.y >= region.minY) || (b.y <= region.maxY && a.y >= region.minY))) ||
      (a.y >= region.minY && a.y <= region.maxY && ((a.x <= region.maxX && b.x >= region.minX) || (b.x <= region.maxX && a.x >= region.minX)));
    if (!touches) continue;
    const label = labelFor(a) || labelFor(b);
    if (Math.abs(a.x - b.x) < 0.02 * len) gx.push({ label, x: (a.x + b.x) / 2, y1: Math.min(a.y, b.y), y2: Math.max(a.y, b.y) });
    else if (Math.abs(a.y - b.y) < 0.02 * len) gy.push({ label, y: (a.y + b.y) / 2, x1: Math.min(a.x, b.x), x2: Math.max(a.x, b.x) });
  }
  const dedupe = (arr, key) => {
    const out = [];
    for (const g of arr.sort((p, q) => p[key] - q[key])) {
      const last = out[out.length - 1];
      if (last && Math.abs(last[key] - g[key]) < 100) { if (!last.label && g.label) last.label = g.label; continue; }
      out.push(g);
    }
    return out;
  };
  let grid = { x: dedupe(gx, 'x'), y: dedupe(gy, 'y'), source: 'drawing' };

  // ------------------------------------------------------------ columns
  const columns = [];
  const pushColumn = (c) => {
    if (!near({ x: c.cx, y: c.cy }, 300)) return;
    if (columns.some((o) => dist({ x: o.cx, y: o.cy }, { x: c.cx, y: c.cy }) < 150)) return;
    columns.push(c);
  };
  for (const e of ents.filter((x) => x.kind === 'column')) {
    if (e.type === 'CIRCLE' && e.r > 100 && e.r < 1500) { pushColumn({ shape: 'circle', cx: e.x, cy: e.y, d: 2 * e.r, w: 2 * e.r, h: 2 * e.r }); continue; }
    if (e.type === 'INSERT' && e.blockBbox) { const b = e.blockBbox; if (b.w > 150 && b.w < 3000 && b.h > 150 && b.h < 3000) pushColumn({ shape: 'rect', cx: b.cx, cy: b.cy, w: b.w, h: b.h }); continue; }
    for (const p of closedPolys(e)) {
      const b = bbox(p);
      if (b.w < 150 || b.h < 150 || b.w > 3000 || b.h > 3000) continue;
      pushColumn({ shape: 'rect', cx: b.cx, cy: b.cy, w: b.w, h: b.h });
    }
  }
  if (!columns.length) {
    for (const e of ents.filter((x) => x.type === 'LWPOLYLINE' && x.kind !== 'grid' && x.kind !== 'slab')) {
      for (const p of closedPolys(e)) {
        const b = bbox(p);
        if (b.w < 200 || b.h < 200 || b.w > 1500 || b.h > 1500 || b.w / b.h > 4 || b.h / b.w > 4) continue;
        if (!pointInPolygon({ x: b.cx, y: b.cy }, outline)) continue;
        pushColumn({ shape: 'rect', cx: b.cx, cy: b.cy, w: b.w, h: b.h });
      }
    }
    if (columns.length) assumptions.push({ ...A, text: 'No column layer found: small closed rectangles inside the slab were taken as columns.' });
  }
  if (!grid.x.length || !grid.y.length) {
    // Derive a grid from column lines.
    const cluster = (vals) => { const out = []; for (const v of [...vals].sort((a, b) => a - b)) { const l = out[out.length - 1]; if (l && Math.abs(l.v - v) < 300) { l.n++; l.v = (l.v * (l.n - 1) + v) / l.n; } else out.push({ v, n: 1 }); } return out.map((c) => c.v); };
    if (!grid.x.length) grid.x = cluster(columns.map((c) => c.cx)).map((x) => ({ label: null, x, y1: ob.minY, y2: ob.maxY }));
    if (!grid.y.length) grid.y = cluster(columns.map((c) => c.cy)).map((y) => ({ label: null, y, x1: ob.minX, x2: ob.maxX }));
    grid.source = 'derived from column positions';
    assumptions.push({ ...A, text: `Grid lines not found for ${name}: grid derived from column positions.` });
  }
  const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  grid.x.forEach((g, i) => { if (!g.label) g.label = letters[i % letters.length]; if (g.y1 == null) { g.y1 = ob.minY; g.y2 = ob.maxY; } });
  grid.y.forEach((g, i) => { if (!g.label) g.label = String(i + 1); if (g.x1 == null) { g.x1 = ob.minX; g.x2 = ob.maxX; } });
  columns.forEach((c, i) => {
    const gxn = grid.x.reduce((b, g) => (Math.abs(g.x - c.cx) < Math.abs((b ? b.x : Infinity) - c.cx) ? g : b), null);
    const gyn = grid.y.reduce((b, g) => (Math.abs(g.y - c.cy) < Math.abs((b ? b.y : Infinity) - c.cy) ? g : b), null);
    c.id = gxn && gyn && Math.abs(gxn.x - c.cx) < 600 && Math.abs(gyn.y - c.cy) < 600 ? `${gxn.label}/${gyn.label}` : `C${i + 1}`;
  });
  columns.sort((a, b) => b.cy - a.cy || a.cx - b.cx);

  // ------------------------------------------------------------ openings / voids / u-bar / pt
  const openings = [], voids = [], ubarCircles = [], ptZones = [], tendons = [];
  const ubarEdges = [];
  const textNear = (p, r = 1500) => texts.filter((t) => dist({ x: t.x, y: t.y }, p) < r).map(textOf).join(' ').toUpperCase();
  const isColumnShape = (rg) => columns.some((c) => dist(regionCenter(rg), { x: c.cx, y: c.cy }) < 150);
  for (const e of ents) {
    if (!['void', 'opening', 'ubar', 'pt'].includes(e.kind)) continue;
    if (e.type === 'CIRCLE') {
      const rg = { kind: 'circle', cx: e.x, cy: e.y, r: e.r };
      if (!near({ x: e.x, y: e.y })) continue;
      if (e.kind === 'ubar') ubarCircles.push(rg);
      else if (e.kind === 'opening') { openings.push(rg); ubarCircles.push({ ...rg, fromOpening: true }); }
      else if (e.kind === 'void') voids.push(rg);
      continue;
    }
    if (e.kind === 'pt' && (e.type === 'LINE' || (e.type === 'LWPOLYLINE' && !e.closed))) {
      const pts = e.type === 'LINE' ? [{ x: e.x, y: e.y }, { x: e.x2, y: e.y2 }] : e.pts;
      if (pts.some((p) => pointInPolygon(p, outline))) tendons.push({ pts });
      continue;
    }
    if (e.kind === 'ubar' && (e.type === 'LINE' || (e.type === 'LWPOLYLINE' && !e.closed))) {
      const pts = e.type === 'LINE' ? [{ x: e.x, y: e.y }, { x: e.x2, y: e.y2 }] : e.pts;
      for (let i = 0; i + 1 < pts.length; i++) if (near(pts[i], 300) && near(pts[i + 1], 300)) ubarEdges.push({ a: pts[i], b: pts[i + 1] });
      continue;
    }
    for (const p of closedPolys(e)) {
      const rg = regionFrom(e, p);
      const c = regionCenter(rg);
      if (!near(c)) continue;
      if (isColumnShape(rg)) continue;
      if (e.kind === 'pt') { if (regionArea(rg) > 1e6) ptZones.push(rg); continue; }
      if (e.kind === 'ubar') { if (rg.kind === 'circle') ubarCircles.push(rg); continue; }
      const kind = e.kind === 'void' ? voids : openings;
      if (!kind.some((o) => dist(regionCenter(o), c) < 100)) kind.push(rg);
    }
  }
  if (!openings.length && !voids.length) {
    // Heuristic: closed shapes inside the slab that are not columns.
    for (const e of ents.filter((x) => x.type === 'LWPOLYLINE' && !['grid', 'slab', 'column', 'pt'].includes(x.kind))) {
      for (const p of closedPolys(e)) {
        const rg = regionFrom(e, p);
        const area = regionArea(rg);
        if (area < 0.05e6 || area > 60e6) continue;
        const c = regionCenter(rg);
        if (!pointInPolygon(c, outline) || isColumnShape(rg)) continue;
        const words = textNear(c);
        if (/VOID|ACU|AKWAR|كور|HOLLOW/.test(words)) voids.push(rg);
        else { openings.push(rg); assumptions.push({ ...A, text: `Closed shape at (${Math.round(c.x)}, ${Math.round(c.y)}) inside ${name} has no layer or label: treated as an opening.` }); }
      }
    }
  }
  openings.forEach((o, i) => { o.id = `O${i + 1}`; });
  voids.forEach((v, i) => { v.id = `V${i + 1}`; });
  ubarCircles.forEach((u, i) => { u.id = `R${i + 1}`; });
  ptZones.forEach((z, i) => { z.id = `PT${i + 1}`; z.polygon = z.polygon || (z.kind === 'rect' ? rectPolygon(z.rect) : circlePolygon(z.cx, z.cy, z.r)); });

  findings.push(`${id} ${name}: ${columns.length} columns, grid ${grid.x.map((g) => g.label).join('-')} / ${grid.y.map((g) => g.label).join('-')}, ${openings.length} openings, ${voids.length} voids, ${ubarCircles.length} circular U-bar regions, ${ptZones.length} PT zones, ${tendons.length} tendon lines, slab ${thickness} mm.`);

  return {
    id, name, thickness, outline, bbox: ob, grid, columns, openings, voids,
    ubar: { edges: ubarEdges.length ? ubarEdges : 'all', circles: ubarCircles },
    pt: { zones: ptZones, tendons },
  };
}
