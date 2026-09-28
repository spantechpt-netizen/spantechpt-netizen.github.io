/**
 * The reference plan: the architect's (or the structural) drawing of the level, uploaded next to the RAM model so
 * that the sheets carry the project's own grid, the columns as drawn and the slab edges instead of what RAM
 * holds. The two are matched in one point: automatically by fitting the columns of the drawing onto the columns
 * of the model (any translation, the drawing turned by 0 / 90 / 180 / 270), or by a common point given by hand
 * (a grid intersection or a column corner read in both), with an optional turn.
 */
import { parseDxf } from './dxf-reader.mjs';
import { extractModel } from './extract.mjs';
import { bbox, dist, centroid, polygonArea, pointInPolygon } from './geometry.mjs';

const MATCH_TOL = 300; // mm: a drawing column this close to a model column is the same column
const ROTATIONS = [0, 90, 180, 270];

const rotDeg = (p, deg, c = { x: 0, y: 0 }) => {
  const a = (deg * Math.PI) / 180, s = Math.sin(a), k = Math.cos(a);
  const x = p.x - c.x, y = p.y - c.y;
  return { x: c.x + x * k - y * s, y: c.y + x * s + y * k };
};

/** Reads the drawing: its slab outlines, columns and grid (labels from the bubbles), in mm. */
export function readReferencePlan(text, options = {}) {
  const dxf = parseDxf(text);
  const model = extractModel(dxf, { levelNames: options.levelNames });
  const levels = model.levels.map((l) => ({
    name: l.name,
    outline: l.outline, bbox: l.bbox,
    columns: (l.columns || []).map((c) => ({ shape: c.shape || 'rect', cx: c.cx, cy: c.cy, w: c.w, h: c.h, d: c.d, angle: c.angle || 0 })),
    grid: { x: (l.grid?.x || []).map((g) => ({ label: g.label, x: g.x })), y: (l.grid?.y || []).map((g) => ({ label: g.label, y: g.y })), source: l.grid?.source || 'drawing' },
    openings: l.openings || [],
    walls: l.walls || [],
  }));
  const all = { columns: levels.flatMap((l) => l.columns), outlines: levels.map((l) => l.outline) };
  // one grid for the whole drawing: the labels of the largest plan (they are the same lines for every plan on it)
  const main = levels.slice().sort((a, b) => Math.abs(polygonArea(b.outline)) - Math.abs(polygonArea(a.outline)))[0];
  return {
    units: model.source.units, entities: model.source.entities, levels, columns: all.columns, outlines: all.outlines,
    grid: main ? main.grid : { x: [], y: [], source: 'none' },
    gridFromDrawing: main ? main.grid.source === 'drawing' : false,
    findings: model.findings, assumptions: model.assumptions.map((a) => a.text),
  };
}

/**
 * The transform that puts the drawing onto the model, fitted on the columns: for every turn and every pairing of
 * a drawing column with a model column the translation that makes them coincide is tried, and the one that puts
 * the most drawing columns on model columns wins. Returns { rot, dx, dy, matched, total, score } where a drawing
 * point maps as rot(p, rot) + (dx, dy).
 */
export function alignByColumns(refColumns, ramColumns) {
  const refs = refColumns.map((c) => ({ x: c.cx, y: c.cy }));
  const rams = ramColumns.map((c) => ({ x: c.cx, y: c.cy }));
  if (!refs.length || !rams.length) return null;
  const key = (p) => `${Math.round(p.x / MATCH_TOL)},${Math.round(p.y / MATCH_TOL)}`;
  const cells = new Map();
  for (const p of rams) { const k = key(p); if (!cells.has(k)) cells.set(k, []); cells.get(k).push(p); }
  const hasNear = (p) => {
    const cx = Math.round(p.x / MATCH_TOL), cy = Math.round(p.y / MATCH_TOL);
    for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) for (const q of cells.get(`${cx + i},${cy + j}`) || []) if (dist(p, q) <= MATCH_TOL) return true;
    return false;
  };
  let best = null;
  const sample = refs.length > 60 ? refs.filter((_, i) => i % Math.ceil(refs.length / 60) === 0) : refs;
  for (const rot of ROTATIONS) {
    const turned = refs.map((p) => rotDeg(p, rot));
    const turnedSample = sample.map((p) => rotDeg(p, rot));
    const tried = new Set();
    for (const a of turnedSample) for (const b of rams) {
      const dx = b.x - a.x, dy = b.y - a.y;
      const tk = `${Math.round(dx / 50)},${Math.round(dy / 50)}`;
      if (tried.has(tk)) continue;
      tried.add(tk);
      let matched = 0;
      for (const p of turned) if (hasNear({ x: p.x + dx, y: p.y + dy })) matched++;
      const score = matched - Math.hypot(dx, dy) / 1e9 - (rot ? 1e-3 : 0);
      if (!best || score > best.score) best = { rot, dx, dy, matched, total: refs.length, score };
    }
  }
  if (!best) return null;
  // refine the translation on the matched pairs (the mean offset), so a column drawn a little off does not pull it
  const turned = refs.map((p) => rotDeg(p, best.rot));
  let sx = 0, sy = 0, n = 0;
  for (const p of turned) {
    const q = { x: p.x + best.dx, y: p.y + best.dy };
    const near = rams.filter((r) => dist(r, q) <= MATCH_TOL).sort((r1, r2) => dist(r1, q) - dist(r2, q))[0];
    if (near) { sx += near.x - p.x; sy += near.y - p.y; n++; }
  }
  if (n) { best.dx = sx / n; best.dy = sy / n; }
  best.dx = Math.round(best.dx); best.dy = Math.round(best.dy);
  return best;
}

/** The transform from a common point: the drawing point `dxf` (turned by `rot`) lands on the model point `ram`. */
export function alignByPoint({ dxf, ram, rot = 0 }) {
  const t = rotDeg(dxf, rot);
  return { rot, dx: ram.x - t.x, dy: ram.y - t.y, matched: null, total: null, byPoint: true };
}

/**
 * Applies the reference to the model: the grid (labels and positions), the columns and the slab outline of every
 * level are taken from the drawing where `use` says so. `ramColumns` are the model's columns in its own (world)
 * coordinates, the same frame the transform is fitted in; each level carries `frame` (the turn of its body into
 * the local drawing frame) so the drawing geometry follows it. Returns what was done for the report.
 */
export function applyReference(model, ref, { use = {}, align = null, ramColumns = [] } = {}) {
  const want = { grid: use.grid !== false, columns: use.columns !== false, outline: use.outline !== false };
  const T = align?.mode === 'point' && align.dxf && align.ram ? alignByPoint({ dxf: align.dxf, ram: align.ram, rot: Number(align.rot) || 0 }) : alignByColumns(ref.columns, ramColumns);
  const findings = [], assumptions = [];
  if (!T) {
    findings.push('Reference plan: no columns to fit the drawing on the model; the drawing was not used.');
    return { transform: null, findings, assumptions, used: {} };
  }
  const toWorld = (p) => { const q = rotDeg(p, T.rot); return { x: q.x + T.dx, y: q.y + T.dy }; };
  const used = { grid: 0, columns: 0, outline: 0, unmatchedRam: [], unmatchedRef: [] };
  const refColsWorld = ref.columns.map((c) => ({ ...c, ...toWorld({ x: c.cx, y: c.cy }), angle: ((c.angle || 0) + T.rot) % 180 }));
  for (const level of model.levels) {
    const fr = level.frame || { cx: 0, cy: 0, angle: 0 };
    const toLocal = (p) => rotDeg(p, -fr.angle, { x: fr.cx, y: fr.cy });
    const map = (p) => toLocal(toWorld(p));
    const ob = level.bbox;
    // the outline: the drawing outline whose centre falls in this body (or the nearest), when it is one body
    if (want.outline && ref.outlines.length) {
      const cands = ref.outlines.map((poly) => poly.map(map)).map((poly) => ({ poly, c: centroid(poly) }));
      const mine = cands.filter((o) => pointInPolygon(o.c, level.outline) || pointInPolygon(centroid(level.outline), o.poly));
      if (mine.length === 1) {
        const poly = mine[0].poly;
        const a0 = Math.abs(polygonArea(level.outline)), a1 = Math.abs(polygonArea(poly));
        level.ramOutline = level.outline;
        level.outline = polygonArea(poly) < 0 ? [...poly].reverse() : poly;
        level.bbox = bbox(level.outline);
        if (level.pt?.zones?.length === 1) level.pt.zones[0].polygon = level.outline;
        used.outline++;
        if (Math.abs(a1 - a0) / Math.max(a0, 1) > 0.05) assumptions.push({ level: level.id, text: `The slab edge of ${level.name} is taken from the reference plan (${Math.round(a1 / 1e6)} m²); the RAM slab is ${Math.round(a0 / 1e6)} m² (${Math.round(((a1 - a0) / a0) * 100)} %): check the model against the drawing.` });
      } else if (mine.length > 1) findings.push(`Reference plan: ${mine.length} slab outlines of the drawing fall in ${level.name}; the RAM outline is kept.`);
      else findings.push(`Reference plan: no slab outline of the drawing matches ${level.name}; the RAM outline is kept.`);
    }
    // the columns: those of the drawing inside this body, sized as drawn; RAM columns with no drawn column are reported
    if (want.columns && refColsWorld.length) {
      const inBody = refColsWorld.map((c) => ({ ...c, ...toLocal({ x: c.x, y: c.y }) })).filter((c) => pointInPolygon({ x: c.x, y: c.y }, level.outline) || (level.ramOutline && pointInPolygon({ x: c.x, y: c.y }, level.ramOutline)));
      const ramCols = level.columns || [];
      const cols = inBody.map((c, j) => {
        const twin = ramCols.filter((r) => dist({ x: r.cx, y: r.cy }, { x: c.x, y: c.y }) <= MATCH_TOL).sort((r1, r2) => dist({ x: r1.cx, y: r1.cy }, c) - dist({ x: r2.cx, y: r2.cy }, c))[0];
        return { ...(twin || {}), id: `C${j + 1}`, shape: c.shape, cx: c.x, cy: c.y, w: c.w, h: c.h, d: c.d, angle: c.angle, below: twin ? twin.below : true, fromReference: true, ramId: twin?.id || null };
      });
      const unmatchedRam = ramCols.filter((r) => !cols.some((c) => c.ramId === r.id));
      for (const r of unmatchedRam) used.unmatchedRam.push(`${level.id} ${r.id} (${Math.round(r.cx)}, ${Math.round(r.cy)})`);
      for (const c of cols.filter((c) => !c.ramId)) used.unmatchedRef.push(`${level.id} ${c.id} (${Math.round(c.cx)}, ${Math.round(c.cy)})`);
      level.ramColumns = ramCols;
      level.columns = cols;
      used.columns += cols.length;
    }
    // the grid: the drawing's labels and lines, across the body
    if (want.grid && ref.grid && (ref.grid.x.length || ref.grid.y.length)) {
      const gx = [], gy = [];
      const ob2 = level.bbox || ob;
      const lines = [...ref.grid.x.map((g) => ({ label: g.label, a: { x: g.x, y: ref.levels[0]?.bbox?.minY ?? 0 }, b: { x: g.x, y: (ref.levels[0]?.bbox?.minY ?? 0) + 1000 } })), ...ref.grid.y.map((g) => ({ label: g.label, a: { x: ref.levels[0]?.bbox?.minX ?? 0, y: g.y }, b: { x: (ref.levels[0]?.bbox?.minX ?? 0) + 1000, y: g.y } }))];
      for (const ln of lines) {
        const A = map(ln.a), B = map(ln.b);
        const vertical = Math.abs(B.x - A.x) < Math.abs(B.y - A.y);
        if (vertical) { if (A.x >= ob2.minX - 3000 && A.x <= ob2.maxX + 3000) gx.push({ label: ln.label, x: A.x, y1: ob2.minY, y2: ob2.maxY }); }
        else if (A.y >= ob2.minY - 3000 && A.y <= ob2.maxY + 3000) gy.push({ label: ln.label, y: A.y, x1: ob2.minX, x2: ob2.maxX });
      }
      if (gx.length && gy.length) {
        level.grid = { x: gx.sort((p, q) => p.x - q.x), y: gy.sort((p, q) => p.y - q.y), source: 'reference plan' };
        used.grid++;
        for (const c of level.columns || []) {
          const near = (arr, k, v) => arr.reduce((b, g) => (Math.abs(g[k] - v) < Math.abs((b ? b[k] : Infinity) - v) ? g : b), null);
          const cx = near(level.grid.x, 'x', c.cx), cy = near(level.grid.y, 'y', c.cy);
          if (cx && cy && Math.abs(cx.x - c.cx) < 600 && Math.abs(cy.y - c.cy) < 600) c.id = `${cx.label}/${cy.label}`;
        }
      } else findings.push(`Reference plan: the grid of the drawing does not reach ${level.name} after alignment; the derived grid is kept.`);
    }
  }
  // the assumption about the derived grid no longer holds where the drawing's grid is used
  if (used.grid) model.assumptions = (model.assumptions || []).filter((a) => !/Grid lines are not modelled in RAM Concept/.test(a.text));
  const how = T.byPoint ? `matched on the given point (turned ${T.rot}°)` : `fitted on the columns: ${T.matched} of ${T.total} drawing columns fall on model columns (turned ${T.rot}°, shift ${Math.round(T.dx)}, ${Math.round(T.dy)} mm)`;
  findings.push(`Reference plan ${how}; used: ${[used.grid ? 'grid' : null, used.columns ? `${used.columns} columns` : null, used.outline ? 'slab edge' : null].filter(Boolean).join(', ') || 'nothing'}.`);
  if (!T.byPoint && T.matched != null && T.matched < Math.min(3, T.total)) assumptions.push({ text: `The reference plan could be fitted on only ${T.matched} column(s) of the model: give the common point by hand and check the drawing units.` });
  if (used.unmatchedRam.length) assumptions.push({ text: `${used.unmatchedRam.length} RAM column(s) have no column on the reference plan and are not drawn: ${used.unmatchedRam.slice(0, 8).join('; ')}${used.unmatchedRam.length > 8 ? ' …' : ''}.` });
  if (used.unmatchedRef.length) assumptions.push({ text: `${used.unmatchedRef.length} column(s) of the reference plan have no column in the RAM model (drawn as on the plan, no RAM design at them): ${used.unmatchedRef.slice(0, 8).join('; ')}${used.unmatchedRef.length > 8 ? ' …' : ''}.` });
  assumptions.push({ text: `Grid${used.columns ? ', columns' : ''}${used.outline ? ' and slab edges' : ''} are taken from the reference plan (the architectural / structural drawing), ${T.byPoint ? 'aligned on the point given' : 'aligned on the columns'}; the RAM model provides the design.` });
  model.findings.push(...findings);
  model.assumptions.push(...assumptions);
  return { transform: T, findings, assumptions, used };
}
