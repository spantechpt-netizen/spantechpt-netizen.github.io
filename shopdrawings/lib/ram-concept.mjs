/**
 * Reads a RAM Concept model (.cpt, SQLite from version 8 on) straight from
 * the file: slab areas and mesh, columns, wall line supports, tendons with
 * jacks, the designed reinforcement bands with every individual bar, shear
 * regions, punching checks and materials. Internal RAM units: length 0.1 mm,
 * stress 100 MPa (0.1 kN/mm²), area 0.01 mm².
 */
import { DatabaseSync } from 'node:sqlite';
import { bbox, polygonArea, dist, cleanPolygon, simplifyPolygon, centroid, pointInPolygon, clipSegmentToPolygon, distToPolygon, clipPolylineToPolygon } from './geometry.mjs';
import { chainSegments } from './extract.mjs';

const L = (v) => v / 10; // 0.1 mm → mm
const MPa = (v) => v * 100;
const mm2 = (v) => v / 100;
const nums = (s) => (String(s || '').match(/-?\d+(?:\.\d+)?/g) || []).map(Number);
const point = (s) => { const v = nums(s); return { x: L(v[0]), y: L(v[1]) }; };
const points = (s) => { const v = nums(s); const out = []; for (let i = 0; i + 1 < v.length; i += 2) out.push({ x: L(v[i]), y: L(v[i + 1]) }); return out; };
const bools = (s) => (String(s || '').match(/true|false/g) || []).map((b) => b === 'true');

export function readRamConcept(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  const rows = (t) => { try { return db.prepare(`select * from "${t}"`).all(); } catch { return []; } };
  const byUid = (list) => new Map(list.map((r) => [r.UID, r]));

  // ---------------------------------------------------------------- materials / project
  const cover = rows('Cover')[0] || {};
  const headings = [cover.Heading1, cover.Heading2, cover.Heading3, cover.Heading4].filter(Boolean);
  const concrete = rows('Concrete')[0] || {};
  const rebarTypes = byUid(rows('Rebar').map((r) => ({ ...r, dia: parseInt(String(r.Name).replace(/\D/g, ''), 10) || Math.round(Math.sqrt((4 * mm2(r.As)) / Math.PI)), fy: MPa(r.Fy), area: mm2(r.As) })));
  const ptSystem = rows('PTSystem')[0] || {};
  const strand = rows('StrandMaterial')[0] || {};
  const duct = rows('DuctSystem')[0] || {};
  const anchor = rows('AnchorSystem')[0] || {};
  const spanSeg = rows('SpanSegment');
  const punchChecks = rows('PunchCheck');
  const coverTop = spanSeg.length ? L(Math.max(...spanSeg.map((s) => s.ColumnStripTopCover || 0))) : (punchChecks[0] ? L(punchChecks[0].TopCover) : 25);
  const coverBot = spanSeg.length ? L(Math.max(...spanSeg.map((s) => s.ColumnStripBottomCover || 0))) : (punchChecks[0] ? L(punchChecks[0].BottomCover) : 25);
  const fc = concrete.FcFinal ? Math.round(MPa(concrete.FcFinal)) : null;
  const fy = rebarTypes.size ? Math.round([...rebarTypes.values()][0].fy) : null;

  // ---------------------------------------------------------------- slab areas and mesh
  const slabAreas = rows('SlabArea').map((r) => ({ polygon: cleanPolygon(points(r.MultiPoint)), thickness: L(r.SlabThickness), priority: r.Priority, behaviour: r.SlabBehavior, toc: L(r.TOC) }));
  const nodes = new Map(rows('ElementCornerNode').map((r) => [r.Point0, point(r.Point0)]));
  const edgeCount = new Map();
  const elemThk = [];
  const addEdge = (a, b) => { const k = a < b ? `${a}|${b}` : `${b}|${a}`; edgeCount.set(k, (edgeCount.get(k) || 0) + 1); };
  for (const q of rows('QuadSlabElement')) { const n = [q.CornerNode0, q.CornerNode1, q.CornerNode2, q.CornerNode3]; for (let i = 0; i < 4; i++) addEdge(n[i], n[(i + 1) % 4]); elemThk.push({ thk: L(q.SlabThickness), toc: L(q.TOC || 0), n }); }
  for (const q of rows('TriSlabElement')) { const n = [q.CornerNode0, q.CornerNode1, q.CornerNode2]; for (let i = 0; i < 3; i++) addEdge(n[i], n[(i + 1) % 3]); elemThk.push({ thk: L(q.SlabThickness), toc: L(q.TOC || 0), n }); }
  const elements = elemThk.map((e) => { const poly = e.n.map((k) => nodes.get(k) || point(k)); return { thickness: e.thk, toc: e.toc, area: Math.abs(polygonArea(poly)), centroid: centroid(poly) }; });
  const loopsOf = (counts) => {
    const segsOf = [];
    for (const [k, c] of counts) if (c === 1) { const [a, b] = k.split('|'); const pa = nodes.get(a) || point(a), pb = nodes.get(b) || point(b); segsOf.push([pa, pb]); }
    return chainSegments(segsOf, 2).map((p) => simplifyPolygon(p, 1)).filter((p) => p.length >= 3).map((p) => ({ polygon: p, area: Math.abs(polygonArea(p)) })).sort((a, b) => b.area - a.area);
  };
  let loops = loopsOf(edgeCount);
  // office rule: a slab at another level (a step in the top of concrete) is a separate slab entirely; the mesh is
  // taken apart by TOC and every level gets its own outline, so the step reads as a free edge of both slabs
  const tocs = [...new Set(elemThk.map((e) => Math.round(e.toc)))].sort((a, b) => b - a);
  const bodies = [];
  for (const toc of tocs) {
    const counts = new Map();
    for (const e of elemThk) { if (Math.round(e.toc) !== toc) continue; for (let i = 0; i < e.n.length; i++) { const a = e.n[i], b = e.n[(i + 1) % e.n.length]; const k = a < b ? `${a}|${b}` : `${b}|${a}`; counts.set(k, (counts.get(k) || 0) + 1); } }
    const lp = loopsOf(counts).map((l) => (polygonArea(l.polygon) < 0 ? [...l.polygon].reverse() : l.polygon));
    for (const poly of lp) {
      if (lp.some((q) => q !== poly && Math.abs(polygonArea(q)) > Math.abs(polygonArea(poly)) && pointInPolygon(poly[0], q))) continue; // a hole of a body of the same level
      bodies.push({ polygon: poly, holes: lp.filter((q) => q !== poly && pointInPolygon(q[0], poly) && Math.abs(polygonArea(q)) < Math.abs(polygonArea(poly))), toc });
    }
  }
  let outline, holes = [];
  const allLoops = loops.map((l) => (polygonArea(l.polygon) < 0 ? [...l.polygon].reverse() : l.polygon));
  if (loops.length) {
    outline = loops[0].polygon;
    holes = loops.slice(1).filter((l) => pointInPolygon(l.polygon[0], outline)).map((l) => l.polygon);
  } else if (slabAreas.length) {
    outline = slabAreas.sort((a, b) => Math.abs(polygonArea(b.polygon)) - Math.abs(polygonArea(a.polygon)))[0].polygon;
  }
  if (outline && polygonArea(outline) < 0) outline = [...outline].reverse();
  // dominant thickness: by element area (approximate by counting elements)
  const thkCount = new Map();
  for (const e of elemThk) thkCount.set(e.thk, (thkCount.get(e.thk) || 0) + 1);
  const thicknesses = [...thkCount.entries()].sort((a, b) => b[1] - a[1]);
  const baseThickness = thicknesses.length ? thicknesses[0][0] : (slabAreas[0]?.thickness || 250);
  const thickZones = slabAreas.filter((a) => a.thickness > baseThickness + 1).map((a, i) => ({ id: `Z${i + 1}`, polygon: a.polygon, thickness: a.thickness }));
  // beams: RAM beam objects (an axis, a width, a depth); an edge beam lies along the slab edge, an interior one has slab both sides
  const beams = rows('Beam').filter((r) => r.Point0 && r.Point1).map((r, i) => {
    const a = point(r.Point0), b = point(r.Point1);
    const w = L(r.Width || 0) || 300, d = L(r.SlabThickness || 0);
    const len = Math.hypot(b.x - a.x, b.y - a.y) || 1;
    const n = { x: -(b.y - a.y) / len, y: (b.x - a.x) / len };
    return { id: `BM${i + 1}`, a, b, t: w, depth: d, toc: L(r.TOC || 0), meshedAsSlab: !!r.BeamIsMeshedAsSlab, polygon: [{ x: a.x + n.x * w / 2, y: a.y + n.y * w / 2 }, { x: b.x + n.x * w / 2, y: b.y + n.y * w / 2 }, { x: b.x - n.x * w / 2, y: b.y - n.y * w / 2 }, { x: a.x - n.x * w / 2, y: a.y - n.y * w / 2 }] };
  }).filter((bm) => Math.hypot(bm.b.x - bm.a.x, bm.b.y - bm.a.y) > 500);

  // ---------------------------------------------------------------- supports
  const columns = rows('Column').map((r, i) => {
    const p = point(r.Point0);
    let w = L(r.B), h = L(r.D), angle = ((((r.Angle || 0) * 180) / Math.PI) % 180 + 180) % 180;
    if (w < 1) return { id: `C${i + 1}`, shape: 'circle', cx: p.x, cy: p.y, d: h, w: h, h, angle: 0, below: r.SupportSet === 'below' };
    // an orthogonal column is stored with its plan sizes along X / Y (a column turned 90° swaps B and D):
    // every rule (top bars, punching, U-bars) then reads w along X and h along Y
    if (Math.abs(angle - 90) < 2) { [w, h] = [h, w]; angle = 0; } else if (angle < 2 || angle > 178) angle = 0;
    return { id: `C${i + 1}`, shape: 'rect', cx: p.x, cy: p.y, w, h, angle, below: r.SupportSet === 'below' };
  });
  // a column above and a column below at the same point are one column on the plan (the one below drawn)
  for (let i = columns.length - 1; i >= 0; i--) {
    const c = columns[i];
    const twin = columns.findIndex((o, j) => j !== i && Math.abs(o.cx - c.cx) < 50 && Math.abs(o.cy - c.cy) < 50);
    if (twin >= 0 && twin < i && (!c.below || columns[twin].below)) columns.splice(i, 1);
    else if (twin >= 0 && twin < i) { columns.splice(twin, 1); i--; }
  }
  // walls: RAM's own Wall objects (with their thickness; the set below the slab, or above when that is all there is)
  // plus plain line supports; a wall above and one below on the same line are one wall on the plan
  const wallRows = rows('Wall');
  const below = wallRows.filter((r) => r.SupportSet === 'below');
  const chosen = below.length ? below : wallRows;
  const walls = chosen.map((r) => ({ a: point(r.Point0), b: point(r.Point1), t: r.WallThickness ? L(r.WallThickness) : undefined }));
  for (const r of rows('LineSupport')) {
    const a = point(r.Point0), b = point(r.Point1);
    if (!walls.some((w) => (Math.hypot(w.a.x - a.x, w.a.y - a.y) < 50 && Math.hypot(w.b.x - b.x, w.b.y - b.y) < 50) || (Math.hypot(w.a.x - b.x, w.a.y - b.y) < 50 && Math.hypot(w.b.x - a.x, w.b.y - a.y) < 50))) walls.push({ a, b });
  }

  // ---------------------------------------------------------------- tendons
  const tendonSegs = rows('Tendon');
  const jacks = rows('Jack');
  const layersById = new Map(rows('TendonLayer').map((r) => [r.UID, r]));
  const levelsById = new Map(rows('TendonLevel').map((r) => [r.UID, r]));
  const catParent = new Map(rows('TendonCategory').map((r) => [r.UID, r.ParentUID]));
  const jackByNode = new Map(jacks.map((j) => [j.TendonNode0, j]));
  const spanSetOf = (parentUid) => {
    const lvl = levelsById.get(catParent.get(parentUid));
    const layer = lvl && (layersById.get(lvl.ParentUID) || [...layersById.values()].find((l) => l.UID === lvl.ParentUID));
    if (layer) return layer.SpanSet;
    // fall back: order of categories = order of layers
    const idx = [...catParent.keys()].indexOf(parentUid);
    const layersList = [...layersById.values()];
    return layersList[idx] ? layersList[idx].SpanSet : 'latitude';
  };
  // profile points: every tendon node carries its CGS elevation (reference 4 = above the soffit, 5 = below the
  // surface, 6 = from mid-depth) with the local slab surface / soffit, so heights above the soffit follow
  const nodeElev = new Map(rows('TendonNode').map((r) => {
    const thk = L((r.Surface || 0) - (r.Soffit || 0)) || null;
    const v = L(r.ElevationValue || 0);
    const ref = r.ElevationReference;
    const h = ref === 5 && thk ? thk - v : ref === 6 && thk ? thk / 2 + v : v;
    return [r.Point0, { h: Math.round(h), ref, thickness: thk }];
  }));
  // chain segments node to node
  const adj = new Map();
  for (const s of tendonSegs) { for (const n of [s.TendonNode0, s.TendonNode1]) { if (!adj.has(n)) adj.set(n, []); adj.get(n).push(s); } }
  const used = new Set();
  const tendons = [];
  for (const start of adj.keys()) {
    if (adj.get(start).length !== 1) continue;
    const first = adj.get(start)[0];
    if (used.has(first.UID)) continue;
    let node = start; let seg = first;
    const pts = [point(node)];
    const heights = [nodeElev.get(node)?.h ?? null];
    const thks = [nodeElev.get(node)?.thickness ?? null];
    const segsOfTendon = [];
    while (seg && !used.has(seg.UID)) {
      used.add(seg.UID); segsOfTendon.push(seg);
      node = seg.TendonNode0 === node ? seg.TendonNode1 : seg.TendonNode0;
      pts.push(point(node));
      heights.push(nodeElev.get(node)?.h ?? null);
      thks.push(nodeElev.get(node)?.thickness ?? null);
      seg = (adj.get(node) || []).find((s) => !used.has(s.UID));
    }
    const strands = Math.max(...segsOfTendon.map((s) => s.NumStrands));
    const length = pts.reduce((s, p, i) => (i ? s + dist(pts[i - 1], p) : 0), 0);
    const ends = [segsOfTendon[0].TendonNode0 === start ? start : start, node];
    const jackEnds = [start, node].map((n) => jackByNode.get(n)).filter(Boolean);
    const spanSet = spanSetOf(segsOfTendon[0].ParentUID);
    tendons.push({
      id: '', spanSet, strands, pts, length: Math.round(length), segments: segsOfTendon.length,
      live: [!!jackByNode.get(start), !!jackByNode.get(node)],
      jackStress: jackEnds.length ? MPa(jackEnds[0].JackStress) : null,
      elongation: jackEnds.length ? Math.round(jackEnds.reduce((s, j) => s + L(j.Elongation), 0)) : null,
      elongations: [start, node].map((n) => (jackByNode.get(n) ? Math.round(L(jackByNode.get(n).Elongation)) : null)), // per end (null at a dead end)
      harped: !!segsOfTendon[0].Harped,
      // the CGS profile: height above the soffit at every node (null when the model carries none), reverse-curve ratio
      heights: heights.every((h) => h == null) ? null : heights,
      thks: thks.every((h) => h == null) ? null : thks,
      inflection: segsOfTendon[0].InflectionRatio || 0.2,
      thickness: nodeElev.get(start)?.thickness || null,
    });
  }
  // closed loops (no degree-1 node) are ignored; number tendons per span set
  const strandArea = strand.Aps ? mm2(strand.Aps) : 98.7;
  for (const set of ['latitude', 'longitude']) {
    tendons.filter((t) => t.spanSet === set).sort((a, b) => (set === 'latitude' ? a.pts[0].y - b.pts[0].y : a.pts[0].x - b.pts[0].x)).forEach((t, i) => { t.id = `${set === 'latitude' ? 'TA' : 'TB'}-${String(i + 1).padStart(2, '0')}`; });
  }
  for (const t of tendons) t.jackForce = t.jackStress ? Math.round((t.jackStress * strandArea * t.strands) / 1000) : null;

  // ---------------------------------------------------------------- designed reinforcement
  const bandsRaw = rows('ConcentratedRebar');
  const indiv = rows('IndividualBars');
  const bandKey = (r, n) => `${r.ParentUID % 2}|${r.BarFace}|${r.SpanDirection}|${n}|${Math.round(r.AbsoluteElevation)}`;
  const indivByKey = new Map();
  for (const b of indiv) { const k = `${b.BarFace}|${b.SpanDirection}|${points(b.Point0).length}|${Math.round(b.AbsoluteElevation)}`; if (!indivByKey.has(k)) indivByKey.set(k, []); indivByKey.get(k).push(b); }
  const bands = bandsRaw.map((r, i) => {
    const type = rebarTypes.get(r.BarType) || { dia: 12, name: 'T12' };
    const p0 = point(r.Point0), p1 = point(r.Point1);
    const left = point(r.LeftPoint), right = point(r.RightPoint);
    const k = `${r.BarFace}|${r.SpanDirection}|${r.BarCount}|${Math.round(r.AbsoluteElevation)}`;
    // pick the individual-bar set whose bars lie on this band (closest first-bar midpoint to the band line)
    const cands = indivByKey.get(k) || [];
    let best = null, bestD = Infinity;
    const mid = { x: (p0.x + p1.x) / 2, y: (p0.y + p1.y) / 2 };
    for (const c of cands) {
      const a = points(c.Point0), b = points(c.Point1);
      const cm = a.reduce((s, p, j) => ({ x: s.x + (p.x + b[j].x) / 2 / a.length, y: s.y + (p.y + b[j].y) / 2 / a.length }), { x: 0, y: 0 });
      const d = dist(cm, mid);
      if (d < bestD) { bestD = d; best = c; }
    }
    let bars = [];
    if (best) { const a = points(best.Point0), b = points(best.Point1); bars = a.map((p, j) => ({ a: p, b: b[j] })); }
    else { const n = r.BarCount; for (let j = 0; j < n; j++) { const f = n > 1 ? j / (n - 1) : 0.5; const off = { x: left.x + (right.x - left.x) * f - mid.x, y: left.y + (right.y - left.y) * f - mid.y }; bars.push({ a: { x: p0.x + off.x, y: p0.y + off.y }, b: { x: p1.x + off.x, y: p1.y + off.y } }); } }
    const length = bars.length ? Math.round(bars.reduce((s, b) => s + dist(b.a, b.b), 0) / bars.length) : Math.round(dist(p0, p1));
    return {
      id: `RB${i + 1}`, face: r.BarFace === 1 ? 'T' : 'B', dir: r.SpanDirection, dia: type.dia, typeName: type.Name || `T${type.dia}`,
      designedBy: r.DesignedBy === 2 ? 'program' : 'user', // RAM: 1 = drawn by the engineer, 2 = generated by the program for a design strip
      count: r.BarCount, spacing: Math.round(L(r.BarSpacing)), width: Math.round(dist(left, right)), length, elevation: L(r.AbsoluteElevation),
      ends: [r.BarEnd0, r.BarEnd1], bars, p0, p1, matched: !!best,
    };
  });

  // shear regions (stirrups)
  const shear = rows('TransverseRebarRegion').map((r, i) => {
    const type = rebarTypes.get(r.BarType) || { dia: 10 };
    return { id: `SR${i + 1}`, a: point(r.Point0), b: point(r.Point1), dia: type.dia, legs: r.StirrupLegs, spacing: Math.round(L(r.StirrupSpacing)), length: Math.round(dist(point(r.Point0), point(r.Point1))) };
  });
  // the punching checks carry their settings only (RAM keeps no pass / fail result in the file): the tributary area RAM
  // computed (0.01 mm² → m²) and the cover to the bar centroid feed the office's indicative check (lib/punching.mjs)
  const punching = punchChecks.map((r) => ({ name: r.Name, p: point(r.Point0), ssr: r.SsrSystem, coverToCgs: L(r.CoverToCGS), tribArea: r.AutoTribArea > 0 ? r.AutoTribArea / 1e8 : null, ssrDesired: !!r.SsrDesignDesired }));
  // area loads by loading type (RAM units: N per 0.01 mm² → kN/m² is x 1e5; negative = downwards). The loading layer
  // (self_dead / other_dead / live_*) is reached through the category → loading level → loading layer chain.
  const loadingTypes = new Map(rows('LoadingLayer').map((r) => [r.UID, r.LoadingType || String(r.Name || '').toLowerCase()]));
  const loadingLevels = new Map(rows('LoadingLevel').map((r) => [r.UID, r.ParentUID]));
  const loadCats = new Map(rows('AreaLoadCategory').map((r) => [r.UID, loadingTypes.get(loadingLevels.get(r.ParentUID)) || loadingTypes.get(r.ParentUID) || 'unknown']));
  const areaLoads = rows('AreaLoad').filter((r) => r.MultiPoint).map((r) => {
    const type = loadCats.get(r.ParentUID) || 'unknown';
    const q = -Math.min(r.ALFz0 ?? 0, r.ALFz1 ?? 0, r.ALFz2 ?? 0) * 1e5; // kN/m², downwards positive
    return { type: /live/.test(type) ? 'live' : /other_dead|dead/.test(type) && !/self/.test(type) ? 'dead' : type, q: Math.round(q * 100) / 100, polygon: cleanPolygon(points(r.MultiPoint)) };
  }).filter((l) => l.polygon.length >= 3);
  // stud rail sets (SSR) designed by RAM (or drawn by the user) at the columns that need punching reinforcement:
  // the rails (start / end per rail), the studs per rail and the stud spacing; the office draws its stirrup detail instead
  const ssrSystems = byUid(rows('SsrSystem'));
  const ssr = rows('SsrSet').filter((r) => r.Point0 && r.Point1 && r.LocationPoint).map((r, i) => {
    const p0 = points(r.Point0), p1 = points(r.Point1);
    const counts = String(r.StudCount || '').match(/-?\d+/g)?.map(Number) || [];
    const sys = ssrSystems.get(r.SsrSystem) || {};
    return {
      id: `SSR${i + 1}`, loc: point(r.LocationPoint), designedBy: r.DesignedBy === 2 ? 'program' : 'user',
      first: L(r.StudSpacingFirst || 0), typ: L(r.StudSpacingTypical || 0), studArea: sys.StudArea ? mm2(sys.StudArea) : 78.5, studDia: Math.round(Math.sqrt((4 * (sys.StudArea ? mm2(sys.StudArea) : 78.5)) / Math.PI)),
      rails: p0.map((a, k) => ({ a, b: p1[k] || a, count: counts[k] || Math.max(0, ...counts) })),
    };
  });

  // background DXF geometry imported into RAM (for reference only)
  const background = [];
  for (const r of rows('DXFLine')) background.push({ type: 'LINE', layer: r.CadLayerName, pts: [point(r.Point0 || r.MultiPoint), point(r.Point1)] });
  for (const r of rows('DXFPolyline')) background.push({ type: 'PLINE', layer: r.CadLayerName, pts: points(r.MultiPoint) });

  db.close();
  return {
    project: { headings, company: headings[0] || '', name: headings[1] || '', part: headings[2] || '', revision: headings[3] || '' },
    materials: { fc, fcu: concrete.FcuFinal ? Math.round(MPa(concrete.FcuFinal)) : null, fy, coverTop, coverBot, concreteName: concrete.Name, rebarTypes: [...rebarTypes.values()].map((t) => ({ name: t.Name, dia: t.dia, area: t.area })) },
    pt: { system: ptSystem.Name, strandArea, fpu: strand.Fpu ? MPa(strand.Fpu) : null, jackStress: anchor.JackStress ? MPa(anchor.JackStress) : null, strandsPerDuct: duct.StrandsPerDuct, ductType: duct.PTSystemType, ductWidth: duct.DuctWidth ? L(duct.DuctWidth) : null, ductHeight: duct.DuctHeight ? L(duct.DuctHeight) : null, fse: ptSystem.Fse ? MPa(ptSystem.Fse) : null },
    slab: { outline, holes, allLoops, bodies, tocs, baseThickness, thicknesses: thicknesses.map(([thk, n]) => ({ thickness: thk, elements: n })), thickZones, areas: slabAreas, elements },
    columns, walls, beams, tendons, bands, shear, punching, ssr, areaLoads, background,
  };
}

/**
 * The tendon CGS height above the soffit at a distance `s` along the tendon: between two nodes the profile is the
 * usual reverse curve, a parabola over `inflection` x the span next to the high point tangent to the sagging
 * parabola over the rest (straight when both nodes sit at one height).
 */
export function tendonHeightAt(t, s) {
  if (!t.heights) return null;
  let acc = 0;
  for (let i = 0; i + 1 < t.pts.length; i++) {
    const span = dist(t.pts[i], t.pts[i + 1]);
    if (s > acc + span + 1e-6 && i + 2 < t.pts.length) { acc += span; continue; }
    const x = Math.max(0, Math.min(span, s - acc));
    const e0 = t.heights[i], e1 = t.heights[i + 1];
    if (e0 == null || e1 == null) return e0 ?? e1 ?? null;
    if (Math.abs(e1 - e0) < 1 || span < 1) return e0;
    const ir = t.inflection || 0.2;
    // measure from the high end
    const fromHigh = e0 >= e1 ? x : span - x;
    const eh = Math.max(e0, e1), el = Math.min(e0, e1), D = eh - el;
    const L1 = ir * span, L2 = span - L1;
    const y = fromHigh <= L1 ? eh - (D * fromHigh * fromHigh) / (L1 * span) : el + (D * (span - fromHigh) * (span - fromHigh)) / (L2 * span);
    return Math.round(y);
  }
  return t.heights[t.heights.length - 1];
}

/** High / low points of a tendon: every node that is a local maximum / minimum of the profile (ends included). */
export function tendonExtremes(t) {
  if (!t.heights) return [];
  const out = [];
  const n = t.pts.length;
  for (let i = 0; i < n; i++) {
    const h = t.heights[i];
    if (h == null) continue;
    const prev = i > 0 ? t.heights[i - 1] : null, next = i + 1 < n ? t.heights[i + 1] : null;
    const hi = (prev == null || h >= prev) && (next == null || h >= next);
    const lo = (prev == null || h <= prev) && (next == null || h <= next);
    if (hi && lo) continue; // flat: a straight tendon
    out.push({ i, p: t.pts[i], h, kind: hi ? 'H' : 'L', end: i === 0 || i === n - 1 });
  }
  return out;
}

// ---------------------------------------------------------------- to the generator's model
const rot = (p, c, a) => { const s = Math.sin(a), k = Math.cos(a); const x = p.x - c.x, y = p.y - c.y; return { x: c.x + x * k - y * s, y: c.y + x * s + y * k }; };
const modeAngle = (angles) => {
  const bins = new Map();
  for (const a of angles) { const k = Math.round(a / 2.5) * 2.5; bins.set(k, (bins.get(k) || 0) + 1); }
  return [...bins.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 0;
};

/**
 * Split the RAM model into slab bodies (one level per disconnected slab
 * outline), rotate each body into its own orthogonal frame and hand back a
 * model the sheet composers understand, with the RAM design attached.
 */
/**
 * A tendon cut to a polygon (a slab body, or a drawing part): the piece inside it with its profile arrays kept in
 * step (heights and thicknesses interpolated at the cut), the cut ends marked (`cut`) and no longer live; null when
 * the tendon has no piece inside. `tol` lets the anchors sit a little outside the slab edge.
 */
export function clipTendon(t, poly, tol = 400) {
  const c = clipPolylineToPolygon(t.pts, poly, tol);
  if (!c || c.pts.length < 2) return null;
  if (!c.cutStart && !c.cutEnd) return t;
  // a cut point was added at an end when the clipped polyline starts / ends away from the original points kept
  const addStart = c.cutStart && dist(c.pts[0], t.pts[c.from]) > 1;
  const addEnd = c.cutEnd && dist(c.pts[c.pts.length - 1], t.pts[c.to]) > 1;
  const along = (arr) => {
    if (!arr) return arr;
    const kept = arr.slice(c.from, c.to + 1);
    const lerp = (i, j, q) => { const a = arr[i], b = arr[j]; if (a == null || b == null) return a ?? b ?? null; const L = dist(t.pts[i], t.pts[j]) || 1; const f = Math.min(1, dist(t.pts[i], q) / L); return a + (b - a) * f; };
    if (addStart) kept.unshift(lerp(c.from, c.from - 1, c.pts[0]));
    if (addEnd) kept.push(lerp(c.to, c.to + 1, c.pts[c.pts.length - 1]));
    return kept;
  };
  const length = c.pts.reduce((sum, p, i) => (i ? sum + dist(c.pts[i - 1], p) : 0), 0);
  return {
    ...t, pts: c.pts, heights: along(t.heights), thks: along(t.thks), length: Math.round(length),
    live: [c.cutStart ? false : t.live[0], c.cutEnd ? false : t.live[1]],
    elongations: t.elongations ? [c.cutStart ? null : t.elongations[0], c.cutEnd ? null : t.elongations[1]] : t.elongations,
    cut: [c.cutStart, c.cutEnd], fullLength: t.fullLength || t.length,
  };
}

export function ramToModel(ram, { levelName = '1ST FLOOR', levelId = null, spec: specOverrides = {} } = {}) {
  const assumptions = [], findings = [];
  // bodies: the outline plus every other outer loop
  const loops = [ram.slab.outline, ...ram.slab.holes].filter(Boolean);
  const outer = ram.slab.allLoops || loops;
  // one body per outer loop of each top-of-concrete level (a slab at another level is a separate slab: office rule)
  const tocBodies = (ram.slab.bodies || []).length ? ram.slab.bodies : null;
  const bodies = tocBodies ? tocBodies.map((b) => b.polygon) : outer.filter((p) => !outer.some((q) => q !== p && Math.abs(polygonArea(q)) > Math.abs(polygonArea(p)) && pointInPolygon(p[0], q)));
  const tocOf = (body) => (tocBodies ? tocBodies.find((b) => b.polygon === body)?.toc ?? 0 : 0);
  const holesOf = (body) => (tocBodies ? tocBodies.find((b) => b.polygon === body)?.holes || [] : outer.filter((q) => q !== body && pointInPolygon(q[0], body) && Math.abs(polygonArea(q)) < Math.abs(polygonArea(body))));
  const stepped = tocBodies && new Set(tocBodies.map((b) => b.toc)).size > 1;
  const inside = (p, poly) => pointInPolygon(p, poly);
  const spec = {
    fc: ram.materials.fc || 30, fy: ram.materials.fy || 420, cover: Math.max(ram.materials.coverTop || 25, ram.materials.coverBot || 25), stock: 12000, lambda: 1,
    ...specOverrides,
  };
  const levels = bodies.map((body, i) => {
    const holes = holesOf(body);
    // a column whose centre sits on the slab edge (corner / edge columns) belongs to the body too
    const near = (p, poly, tol) => inside(p, poly) || distToPolygon(p, poly) <= tol;
    const cols = ram.columns.filter((c) => near({ x: c.cx, y: c.cy }, body, Math.max(c.w, c.h) / 2) && !holesOf(body).some((h) => inside({ x: c.cx, y: c.cy }, h)));
    const angleDeg = cols.length ? modeAngle(cols.map((c) => ((c.angle % 180) + 180) % 180)) : 0;
    const theta = -(angleDeg * Math.PI) / 180;
    const c0 = centroid(body);
    const R = (p) => rot(p, c0, theta);
    const outline = body.map(R);
    const areasIn = ram.slab.areas.filter((a) => inside(centroid(a.polygon), body)).map((a) => ({ ...a, area: Math.abs(polygonArea(a.polygon)) })).sort((a, b) => b.area - a.area);
    const byThk = new Map();
    for (const e of ram.slab.elements || []) if (inside(e.centroid, body)) byThk.set(e.thickness, (byThk.get(e.thickness) || 0) + e.area);
    const dominant = [...byThk.entries()].sort((a, b) => b[1] - a[1])[0];
    const bodyThickness = dominant ? dominant[0] : (areasIn.length ? areasIn[0].thickness : ram.slab.baseThickness);
    const level = {
      // the level code registered for the project (B1, GF, L03 ...) goes into the drawing numbers when given
      id: levelId ? (bodies.length > 1 ? `${levelId}-${i + 1}` : String(levelId)) : `L${String(i + 1).padStart(2, '0')}`, customId: Boolean(levelId),
      name: bodies.length > 1 ? `${levelName} - BODY ${i + 1}` : levelName, rotation: angleDeg, frame: { cx: c0.x, cy: c0.y, angle: angleDeg },
      thickness: bodyThickness, outline, bbox: bbox(outline),
      columns: cols.map((c, j) => { const p = R({ x: c.cx, y: c.cy }); return { ...c, id: `C${j + 1}`, cx: p.x, cy: p.y, angle: Math.round(((c.angle - angleDeg) % 180 + 180) % 180 * 10) / 10 }; }),
      // (a hole in the RAM mesh has a vertex at every element node: the collinear ones are dropped so that a long
      // void side is one side, with one U-bar symbol and one call-out)
      openings: holes.map((h, j) => ({ id: `O${j + 1}`, kind: 'polygon', polygon: simplifyPolygon(h.map(R), 30) })),
      voids: [], sunken: [], stairs: [],
      // beams whose axis lies in this body (an edge beam along the slab edge, or an interior beam with slab both sides)
      // beams: the part of each beam axis inside this body (an axis crossing into another body is cut there)
      beams: (ram.beams || []).filter((bm) => inside(centroid(bm.polygon), body) || near(centroid(bm.polygon), body, bm.t)).flatMap((bm) => {
        const pieces = clipSegmentToPolygon(bm.a, bm.b, body).filter(([a, b]) => dist(a, b) > 300);
        if (!pieces.length) return [{ ...bm, a: R(bm.a), b: R(bm.b), polygon: bm.polygon.map(R) }];
        return pieces.map(([a, b]) => { const L = dist(a, b) || 1, u = { x: (b.x - a.x) / L, y: (b.y - a.y) / L }, n = { x: -u.y, y: u.x }, w = bm.t / 2; return { ...bm, a: R(a), b: R(b), polygon: [{ x: a.x + n.x * w, y: a.y + n.y * w }, { x: b.x + n.x * w, y: b.y + n.y * w }, { x: b.x - n.x * w, y: b.y - n.y * w }, { x: a.x - n.x * w, y: a.y - n.y * w }].map(R) }; });
      }),
      tos: stepped ? tocOf(body) : undefined, toc: tocOf(body),
      walls: ram.walls.flatMap((w) => clipSegmentToPolygon(w.a, w.b, body).map((seg) => [...seg, w.t])).filter(([a, b]) => Math.hypot(b.x - a.x, b.y - a.y) > 50).map(([a, b, t]) => ({ a: R(a), b: R(b), t })),
      thickZones: areasIn.filter((a) => a.thickness > bodyThickness + 1 && a.behaviour !== 'custom').map((a, j) => ({ id: `Z${j + 1}`, thickness: a.thickness, polygon: a.polygon.map(R) })),
      // a slab area of "custom" behaviour no wider than 1.5 m is a pour (infill) strip: the office's pour strip detail applies
      pourStrips: areasIn.filter((a) => a.behaviour === 'custom' && Math.min(bbox(a.polygon).w, bbox(a.polygon).h) <= 1500).map((a, j) => { const b = bbox(a.polygon); return { id: `PS${j + 1}`, polygon: a.polygon.map(R), width: Math.min(b.w, b.h), length: Math.max(b.w, b.h) }; }),
      customZones: areasIn.filter((a) => a.behaviour === 'custom' && Math.min(bbox(a.polygon).w, bbox(a.polygon).h) > 1500).map((a) => ({ polygon: a.polygon.map(R), thickness: a.thickness })),
      ubar: { edges: 'all', circles: [] },
      pt: { zones: [{ id: 'PT1', polygon: outline }], tendons: [] }, // the whole body is post-tensioned
      ram: {
        bands: ram.bands.filter((b) => inside({ x: (b.p0.x + b.p1.x) / 2, y: (b.p0.y + b.p1.y) / 2 }, body) || b.bars.some((bar) => inside(bar.a, body))).map((b) => ({ ...b, p0: R(b.p0), p1: R(b.p1), bars: b.bars.map((bar) => ({ a: R(bar.a), b: R(bar.b) })) })),
        // a tendon is drawn on the body it lies in; one crossing into another body is cut at the edge (nothing drawn outside the slab)
        tendons: ram.tendons.filter((t) => t.pts.some((p) => inside(p, body))).map((t) => clipTendon(t, body, 400)).filter(Boolean).map((t) => ({ ...t, pts: t.pts.map(R) })),
        shear: ram.shear.filter((s) => inside({ x: (s.a.x + s.b.x) / 2, y: (s.a.y + s.b.y) / 2 }, body)).map((s) => ({ ...s, a: R(s.a), b: R(s.b) })),
        punching: ram.punching.filter((p) => near(p.p, body, 500)).map((p) => ({ ...p, p: R(p.p) })),
        ssr: (ram.ssr || []).filter((st) => near(st.loc, body, 500)).map((st) => ({ ...st, loc: R(st.loc), rails: st.rails.map((r) => ({ ...r, a: R(r.a), b: R(r.b) })) })),
        areaLoads: (ram.areaLoads || []).filter((l) => l.polygon.some((p) => inside(p, body)) || inside(centroid(l.polygon), body)).map((l) => ({ ...l, polygon: l.polygon.map(R) })),
        pt: ram.pt,
      },
    };
    // grid from column positions in the local frame
    const cluster = (vals) => { const out = []; for (const v of [...vals].sort((a, b) => a - b)) { const l = out[out.length - 1]; if (l && Math.abs(l.v - v) < 400) { l.n++; l.v = (l.v * (l.n - 1) + v) / l.n; } else out.push({ v, n: 1 }); } return out.map((c) => c.v); };
    const letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
    const ob = level.bbox;
    level.grid = {
      x: cluster(level.columns.map((c) => c.cx)).map((x, k) => ({ label: letters[k % letters.length], x, y1: ob.minY, y2: ob.maxY })),
      y: cluster(level.columns.map((c) => c.cy)).map((y, k) => ({ label: String(k + 1), y, x1: ob.minX, x2: ob.maxX })),
      source: 'derived from column positions',
    };
    level.columns.forEach((c) => {
      const gx = level.grid.x.find((g) => Math.abs(g.x - c.cx) < 400), gy = level.grid.y.find((g) => Math.abs(g.y - c.cy) < 400);
      if (gx && gy) c.id = `${gx.label}/${gy.label}`;
    });
    findings.push(`${level.id} ${level.name}: ${Math.round(Math.abs(polygonArea(outline)) / 1e6)} m², ${level.columns.length} columns, ${level.walls.length} wall segments, ${level.thickZones.length} thickened zones, ${level.pourStrips.length} pour strips, ${level.ram.bands.length} designed bar bands, ${level.ram.tendons.length} tendons, ${level.openings.length} openings${angleDeg ? `, rotated ${angleDeg}° to its local frame` : ''}.`);
    if (level.customZones.length) assumptions.push({ level: level.id, text: `${level.customZones.length} slab area(s) of "custom" behaviour wider than 1.5 m in ${level.name} (${level.customZones.map((z) => `${Math.round(bbox(z.polygon).w / 1000)} x ${Math.round(bbox(z.polygon).h / 1000)} m`).join(', ')}) are drawn as slab; if one is a pour strip or a ramp, set it on the plan.` });
    if (angleDeg) assumptions.push({ level: level.id, text: `Body ${i + 1} is rotated ${angleDeg}° on the site; the plan is drawn in its local frame (north arrow rotated accordingly).` });
    assumptions.push({ level: level.id, text: 'Grid lines are not modelled in RAM Concept: the grid is derived from the column positions and lettered / numbered consecutively; to be replaced by the architectural grid references.' });
    return level;
  });
  assumptions.push({ text: `Reinforcement, tendons and materials are taken from the RAM Concept model (f'c ${spec.fc} MPa from ${ram.materials.concreteName || 'the model'}, fy ${spec.fy} MPa, cover ${spec.cover} mm). Bar cutting lengths add SBC 304-18 hooks (12 Ø) where a bar ends at a free edge and split runs longer than 12 m with Class B laps.` });
  assumptions.push({ text: (ram.ssr || []).length ? `Punching: RAM designed stud rails at ${ram.ssr.length} columns (SSR sets); the design drawings convert them to the office stirrup detail (PS types) at those columns, the shop sheets show the minimum link arrangement to be confirmed against the RAM punching report.` : 'Punching shear results are not stored in the RAM file (no stud rails designed): links are shown as the minimum detailing arrangement and are to be confirmed against the RAM punching report.' });
  assumptions.push({ text: 'The office standard reinforcement (bottom mesh, top bars over columns, edge U-bars, trimmers, punching links) is applied to the RAM slab exactly as for a G.A. drawing; the bands designed in RAM Concept are drawn on top of it as ADDITIONAL reinforcement (sheets 02A / 03A, marks ADD.B / ADD.T).' });
  const ptSpec = { ...spec, code_reference: null, sources: { code: 'assumed', fc: 'RAM model', fy: 'RAM model', cover: 'RAM model' }, found: ram.materials.rebarTypes.map((t) => `RAM bar type ${t.name} (${t.area} mm²)`) };
  const base = { bottom: { dia: 12, spacing: 200 }, topColumns: { dia: 16, spacing: 150 }, uEdge: { dia: 12, spacing: 200, leg: 1200 }, uCircle: { dia: 12, spacing: 150, leg: 1200 }, edgeBars: { dia: 12, count: 2 }, ringBars: { dia: 12, count: 2 }, voids: { dia: 12, count: 2 }, openings: { dia: 16, count: 2, diagDia: 12, diagCount: 2, uDia: 12, uSpacing: 200, uLeg: 600 }, sunken: { dia: 12, count: 2, uDia: 10, uSpacing: 200, uLeg: 600 }, punching: { dia: 10, legSpacing: 100, extentFactor: 2.0 } };
  return {
    source: { units: 'mm (RAM internal 0.1 mm)', entities: ram.bands.length + ram.tendons.length + ram.columns.length, layers: [], ram: true },
    code_reference: null, spec: { ...base, ...ptSpec }, levels, assumptions, findings, ram,
  };
}
