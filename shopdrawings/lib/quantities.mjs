/**
 * Quantity take-off of a package: the reinforcement scheduled on its sheets, the concrete of the slab read from the
 * model (net of openings, drops and beams added, formwork) and the post-tensioning (tendons, strands, strand length
 * at cutting length, weight, anchors, ducts). Every figure comes from the same model and schedules the drawings
 * were made from, so the take-off and the drawings never disagree.
 */
import { polygonArea, dist } from './geometry.mjs';
import * as R from './rebar.mjs';

const STRAND_DENSITY = 7850; // kg/m³
const CUT_ALLOWANCE = 300; // mm of strand per stressed anchor
const SMALL_DUCT_MAX = 3; // strands in a 20x50 duct; over that 20x70

const r1 = (v) => Math.round(v * 10) / 10;
const r2 = (v) => Math.round(v * 100) / 100;
const area = (poly) => (poly && poly.length >= 3 ? Math.abs(polygonArea(poly)) : 0);
const perimeter = (poly) => (poly && poly.length >= 2 ? poly.reduce((s, p, i) => s + dist(p, poly[(i + 1) % poly.length]), 0) : 0);

/** The reinforcement of one level: every scheduled row of its sheets, by diameter and by face. */
export function steelOf(level, sheets) {
  const byDia = {};
  let kg = 0, top = 0, bottom = 0, other = 0;
  for (const s of sheets) {
    if (s.level !== level.id) continue;
    const face = /TOP/i.test(s.title) ? 'T' : /BOTTOM/i.test(s.title) ? 'B' : 'O';
    for (const r of s.rows || []) {
      const w = Number(r.weight_kg);
      if (!Number.isFinite(w) || !w) continue;
      const dia = Number(r.dia) || 0;
      byDia[dia] = byDia[dia] || { dia, total_m: 0, kg: 0, count: 0 };
      byDia[dia].total_m += Number(r.total_m) || 0;
      byDia[dia].kg += w;
      byDia[dia].count += Number(r.qty) || 0;
      kg += w;
      if (face === 'T') top += w; else if (face === 'B') bottom += w; else other += w;
    }
  }
  return {
    kg: r1(kg), top_kg: r1(top), bottom_kg: r1(bottom), other_kg: r1(other),
    byDia: Object.values(byDia).sort((a, b) => a.dia - b.dia).map((d) => ({ dia: d.dia, total_m: r1(d.total_m), kg: r1(d.kg), count: d.count })),
  };
}

/**
 * The slab mesh of a design level made from a RAM model (the office mesh written in the notes, not scheduled on the
 * sheets): both directions on each face, laps and stock allowance included, from the net slab area.
 */
export function meshOf(level) {
  if (!level.ram || !level.meshSpec) return null;
  const [dia, spacing] = level.meshSpec;
  if (!dia || !spacing) return null;
  const faces = level.topMesh ? 2 : 1;
  const [tdia, tspacing] = level.topMesh ? (level.topMeshSpec || level.meshSpec) : [0, 0];
  const gross = area(level.outline) / 1e6;
  const openings = (level.openings || []).map((o) => R.regionPolygon(o)).reduce((s, p) => s + area(p) / 1e6, 0);
  const net = Math.max(0, gross - openings);
  const perFace = (sp) => net * (1000 / sp) * 2 * 1.12; // both directions, 12 % laps and waste
  const mBottom = perFace(spacing), mTop = faces === 2 ? perFace(tspacing) : 0;
  const kg = mBottom * R.barWeightPerM(dia) + mTop * R.barWeightPerM(tdia || dia);
  return { dia, spacing, top_dia: tdia || null, top_spacing: tspacing || null, faces, faces_label: faces === 2 ? 'TOP & BOTTOM' : 'BOTTOM', net_area_m2: r1(net), total_m: r1(mBottom + mTop), bottom_m: r1(mBottom), top_m: r1(mTop), kg: r1(kg), bottom_kg: r1(mBottom * R.barWeightPerM(dia)), top_kg: r1(mTop * R.barWeightPerM(tdia || dia)) };
}

/** The concrete of one level: slab net of openings, the extra of drops / thickened zones, the extra of beams below the slab, formwork. */
export function concreteOf(level) {
  const gross = area(level.outline) / 1e6;
  const openings = (level.openings || []).map((o) => R.regionPolygon(o)).reduce((s, p) => s + area(p) / 1e6, 0);
  const net = Math.max(0, gross - openings);
  const thk = (level.thickness || 0) / 1000;
  const slab = net * thk;
  let drops = 0, dropArea = 0;
  for (const z of level.thickZones || []) {
    if (!z.polygon || !z.thickness || z.thickness <= (level.thickness || 0)) continue;
    const a = area(z.polygon) / 1e6;
    dropArea += a;
    drops += a * ((z.thickness - level.thickness) / 1000);
  }
  let beams = 0, beamLen = 0;
  for (const b of level.beams || []) {
    if (!b.a || !b.b || !b.depth || b.depth <= (level.thickness || 0)) continue;
    const L = dist(b.a, b.b) / 1000;
    beamLen += L;
    beams += L * ((b.t || 0) / 1000) * ((b.depth - level.thickness) / 1000);
  }
  const per = perimeter(level.outline) / 1000 + (level.openings || []).map((o) => R.regionPolygon(o)).reduce((s, p) => s + perimeter(p) / 1000, 0);
  return {
    thickness: level.thickness || 0,
    gross_area_m2: r1(gross), openings_m2: r1(openings), net_area_m2: r1(net),
    slab_m3: r1(slab), drops_m3: r1(drops), drop_area_m2: r1(dropArea), beams_m3: r1(beams), beam_length_m: r1(beamLen),
    total_m3: r1(slab + drops + beams),
    soffit_formwork_m2: r1(net + dropArea * 0), edge_formwork_m2: r1(per * thk), formwork_m2: r1(net + per * thk),
    perimeter_m: r1(per),
  };
}

/** The post-tensioning of one level from the RAM tendons: per direction and in all. */
export function cablesOf(level) {
  const tendons = level.ram?.tendons || [];
  if (!tendons.length) return null;
  const strandArea = level.ram?.pt?.strandArea || 140;
  const kgPerM = (strandArea * STRAND_DENSITY) / 1e6;
  const dirs = {};
  for (const t of tendons) {
    const key = t.spanSet === 'latitude' ? 'A' : 'B';
    const d = dirs[key] = dirs[key] || { direction: key, tendons: 0, strands: 0, tendon_m: 0, strand_m: 0, cutting_m: 0, live_ends: 0, dead_ends: 0, duct_small_m: 0, duct_large_m: 0 };
    const live = t.live.filter(Boolean).length;
    const Lm = t.length / 1000;
    d.tendons++;
    d.strands += t.strands;
    d.tendon_m += Lm;
    d.strand_m += Lm * t.strands;
    d.cutting_m += (Lm + (CUT_ALLOWANCE / 1000) * Math.max(1, live)) * t.strands;
    d.live_ends += live;
    d.dead_ends += 2 - live;
    const duct = Math.max(0, Lm - (live === 1 ? 1 : 0));
    if (t.strands <= SMALL_DUCT_MAX) d.duct_small_m += duct; else d.duct_large_m += duct;
  }
  const list = Object.values(dirs).sort((a, b) => a.direction.localeCompare(b.direction)).map((d) => ({ ...d, tendon_m: r1(d.tendon_m), strand_m: r1(d.strand_m), cutting_m: r1(d.cutting_m), duct_small_m: r1(d.duct_small_m), duct_large_m: r1(d.duct_large_m), kg: r1(d.cutting_m * kgPerM) }));
  const sum = (k) => r1(list.reduce((s, d) => s + d[k], 0));
  const net = concreteOf(level).net_area_m2;
  const kg = sum('kg');
  return {
    strand_area_mm2: strandArea, strand_kg_per_m: r2(kgPerM), duct_small: '20x50', duct_large: '20x70',
    directions: list,
    tendons: list.reduce((s, d) => s + d.tendons, 0), strands: list.reduce((s, d) => s + d.strands, 0),
    tendon_m: sum('tendon_m'), strand_m: sum('strand_m'), cutting_m: sum('cutting_m'), kg,
    live_ends: list.reduce((s, d) => s + d.live_ends, 0), dead_ends: list.reduce((s, d) => s + d.dead_ends, 0),
    duct_small_m: sum('duct_small_m'), duct_large_m: sum('duct_large_m'),
    kg_per_m2: net ? r2(kg / net) : null, strand_m_per_m2: net ? r2(sum('strand_m') / net) : null,
  };
}

/** The take-off of a whole package: one entry per level and the totals. */
export function quantities(model, pack) {
  const sheets = pack?.sheets || [];
  const levels = (model.levels || []).map((level) => {
    const concrete = concreteOf(level);
    const steel = steelOf(level, sheets);
    const cables = cablesOf(level);
    const mesh = meshOf(level);
    if (mesh) {
      // the mesh joins the take-off with the scheduled bars (its own line, and in the diameter totals)
      steel.mesh_kg = mesh.kg;
      steel.kg = r1(steel.kg + mesh.kg);
      steel.top_kg = r1(steel.top_kg + mesh.top_kg);
      steel.bottom_kg = r1(steel.bottom_kg + mesh.bottom_kg);
      for (const [dia, m, kg] of [[mesh.dia, mesh.bottom_m, mesh.bottom_kg], [mesh.top_dia, mesh.top_m, mesh.top_kg]]) {
        if (!dia || !kg) continue;
        const d = steel.byDia.find((x) => x.dia === dia);
        if (d) { d.kg = r1(d.kg + kg); d.total_m = r1(d.total_m + m); } else { steel.byDia.push({ dia, total_m: m, kg, count: 0 }); }
      }
      steel.byDia.sort((a, b) => a.dia - b.dia);
    }
    return {
      id: level.id, name: level.name, thickness: level.thickness,
      steel: { ...steel, kg_per_m2: concrete.net_area_m2 ? r2(steel.kg / concrete.net_area_m2) : null, kg_per_m3: concrete.total_m3 ? r1(steel.kg / concrete.total_m3) : null },
      mesh, concrete, cables,
    };
  });
  const sumBy = (get) => r1(levels.reduce((s, l) => s + (get(l) || 0), 0));
  const byDia = {};
  for (const l of levels) for (const d of l.steel.byDia) { byDia[d.dia] = byDia[d.dia] || { dia: d.dia, total_m: 0, kg: 0, count: 0 }; byDia[d.dia].total_m += d.total_m; byDia[d.dia].kg += d.kg; byDia[d.dia].count += d.count; }
  const ptLevels = levels.filter((l) => l.cables);
  const totals = {
    steel: { kg: sumBy((l) => l.steel.kg), top_kg: sumBy((l) => l.steel.top_kg), bottom_kg: sumBy((l) => l.steel.bottom_kg), other_kg: sumBy((l) => l.steel.other_kg), mesh_kg: sumBy((l) => l.steel.mesh_kg), byDia: Object.values(byDia).sort((a, b) => a.dia - b.dia).map((d) => ({ ...d, total_m: r1(d.total_m), kg: r1(d.kg) })) },
    concrete: { gross_area_m2: sumBy((l) => l.concrete.gross_area_m2), openings_m2: sumBy((l) => l.concrete.openings_m2), net_area_m2: sumBy((l) => l.concrete.net_area_m2), slab_m3: sumBy((l) => l.concrete.slab_m3), drops_m3: sumBy((l) => l.concrete.drops_m3), beams_m3: sumBy((l) => l.concrete.beams_m3), total_m3: sumBy((l) => l.concrete.total_m3), formwork_m2: sumBy((l) => l.concrete.formwork_m2), edge_formwork_m2: sumBy((l) => l.concrete.edge_formwork_m2) },
    cables: ptLevels.length ? {
      tendons: ptLevels.reduce((s, l) => s + l.cables.tendons, 0), strands: ptLevels.reduce((s, l) => s + l.cables.strands, 0),
      tendon_m: sumBy((l) => l.cables?.tendon_m), strand_m: sumBy((l) => l.cables?.strand_m), cutting_m: sumBy((l) => l.cables?.cutting_m), kg: sumBy((l) => l.cables?.kg),
      live_ends: ptLevels.reduce((s, l) => s + l.cables.live_ends, 0), dead_ends: ptLevels.reduce((s, l) => s + l.cables.dead_ends, 0),
      duct_small_m: sumBy((l) => l.cables?.duct_small_m), duct_large_m: sumBy((l) => l.cables?.duct_large_m),
    } : null,
  };
  const net = totals.concrete.net_area_m2;
  totals.steel.kg_per_m2 = net ? r2(totals.steel.kg / net) : null;
  if (totals.cables) { totals.cables.kg_per_m2 = net ? r2(totals.cables.kg / net) : null; totals.cables.strand_m_per_m2 = net ? r2(totals.cables.strand_m / net) : null; }
  return { levels, totals };
}

/**
 * The cost study: the take-off priced with the office rates. `rates` (per unit, one currency): steel_per_ton,
 * rebar_labour_per_ton, concrete_per_m3, formwork_per_m2, strand_per_kg, anchor_live, anchor_dead, duct_per_m,
 * pt_labour_per_m2, markup_pct, vat_pct. Returns the lines per level and in all.
 */
export function costStudy(q, rates = {}) {
  const R0 = { steel_per_ton: 3200, rebar_labour_per_ton: 350, concrete_per_m3: 280, formwork_per_m2: 45, strand_per_kg: 9.5, anchor_live: 45, anchor_dead: 25, duct_per_m: 6, pt_labour_per_m2: 18, markup_pct: 15, vat_pct: 15, currency: 'SAR', ...rates };
  const linesOf = (steel, concrete, cables) => {
    const lines = [
      { key: 'steel', unit: 't', qty: r2(steel.kg / 1000), rate: R0.steel_per_ton },
      { key: 'rebar_labour', unit: 't', qty: r2(steel.kg / 1000), rate: R0.rebar_labour_per_ton },
      { key: 'concrete', unit: 'm3', qty: concrete.total_m3, rate: R0.concrete_per_m3 },
      { key: 'formwork', unit: 'm2', qty: concrete.formwork_m2, rate: R0.formwork_per_m2 },
    ];
    if (cables) lines.push(
      { key: 'strand', unit: 'kg', qty: cables.kg, rate: R0.strand_per_kg },
      { key: 'anchor_live', unit: 'no', qty: cables.live_ends, rate: R0.anchor_live },
      { key: 'anchor_dead', unit: 'no', qty: cables.dead_ends, rate: R0.anchor_dead },
      { key: 'duct', unit: 'm', qty: r1(cables.duct_small_m + cables.duct_large_m), rate: R0.duct_per_m },
      { key: 'pt_labour', unit: 'm2', qty: concrete.net_area_m2, rate: R0.pt_labour_per_m2 },
    );
    for (const l of lines) l.amount = Math.round(l.qty * l.rate);
    const direct = lines.reduce((s, l) => s + l.amount, 0);
    const markup = Math.round((direct * (R0.markup_pct || 0)) / 100);
    const vat = Math.round(((direct + markup) * (R0.vat_pct || 0)) / 100);
    return { lines, direct, markup, vat, total: direct + markup + vat, per_m2: concrete.net_area_m2 ? Math.round((direct + markup) / concrete.net_area_m2) : null };
  };
  return {
    currency: R0.currency, rates: R0,
    levels: q.levels.map((l) => ({ id: l.id, name: l.name, ...linesOf(l.steel, l.concrete, l.cables) })),
    totals: linesOf(q.totals.steel, q.totals.concrete, q.totals.cables),
  };
}
