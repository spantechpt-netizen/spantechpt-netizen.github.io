/**
 * Indicative punching check of every column of a RAM level, and the office's decision rule around it.
 *
 * RAM Concept keeps no punching result in the .cpt (the PunchCheck rows are settings; the SsrSet rows exist only
 * where RAM designed stud rails), so the program cannot read "this column fails" from the file. It estimates the
 * check itself from what the file does hold - the tributary area RAM computed for each punching check, the area
 * loads by loading type, the slab thickness at the column, the concrete grade and the average precompression of
 * the tendons - with the SBC 304 / ACI 318 two-way shear rules (PT provisions where they apply). The estimate is
 * indicative: it flags the columns the engineer must look at in the RAM punching report; the engineer's own list
 * of columns failing in RAM (`spec.punching.ramFailed`) is flagged whatever the estimate says.
 *
 * A flagged column blocks the run until the engineer decides: thicken the slab / drop and re-run, declare the column
 * passing in RAM (the estimate was conservative), or bypass at the design engineer's responsibility - then the
 * office punching detail (PS strips) is provided at that column, sized from the estimate, with the engineer's name
 * and the date printed on the sheets (`spec.punching.override`).
 */
import { bbox, dist, polygonArea, pointInPolygon, distToPolygon } from './geometry.mjs';
import { columnOnBeam, columnInBand } from './rebar.mjs';

const PHI = 0.75;
const GAMMA = { interior: 1.15, edge: 1.3, corner: 1.4 }; // unbalanced moment allowance on the direct shear
const ALPHA_S = { interior: 40, edge: 30, corner: 20 };
const CONCRETE = 25; // kN/m³
const r2 = (v) => Math.round(v * 100) / 100;

/** The columns of a level checked one by one. `spec.punching`: { ramFailed: [ids], override, ramOk, psDia, rowSpacing }. */
export function punchingCheck(level, spec = {}) {
  const out = { method: 'indicative', columns: [], flagged: [], blocking: [], warnings: [] };
  if (!level.ram) return out;
  const sp = spec.punching || {};
  const fc = spec.fc || 30, fy = spec.fy || 420;
  const sqrtFc = Math.sqrt(fc);
  const outline = level.outline || [];
  const loads = level.ram.areaLoads || [];
  const ssrSets = level.ram.ssr || [];
  const checks = level.ram.punching || [];
  const ramFailed = new Set((sp.ramFailed || []).map((v) => String(v).trim().toUpperCase()).filter(Boolean));
  const ramOk = new Set((sp.ramOk || []).map((v) => String(v).trim().toUpperCase()));
  const fpc = precompression(level);
  const tribEstimate = tributaryAreas(level); // m² per column id, nearest-column share of the slab (used where RAM has no punching check)
  const psDia = sp.psDia || 12, psS = sp.rowSpacing || 100, legArea = (Math.PI * psDia * psDia) / 4;
  for (const c of level.columns || []) {
    const w = c.shape === 'circle' ? c.d : c.w, hh = c.shape === 'circle' ? c.d : c.h;
    const cc = { x: c.cx, y: c.cy };
    const zone = (level.thickZones || []).find((z) => pointInPolygon(cc, z.polygon));
    const h = zone ? zone.thickness : level.thickness;
    // a column standing on a beam is carried by the beam: no punching of the slab, no check, nothing flagged
    // (unless the engineer reports it failing in RAM: their report wins and the column is checked and flagged)
    const beam = columnOnBeam(level, c);
    if (beam && !ramFailed.has(String(c.id).toUpperCase())) {
      out.columns.push({ id: c.id, loc: 'beam', h, d: null, trib_m2: null, wu_kn_m2: null, Vu_kn: null, bo_mm: null, vu_mpa: null, phi_vc_mpa: null, phi_vmax_mpa: null, ratio: null, fpc_mpa: null, rule: 'BEAM', ssr: false, trib_source: '-', ram_failed: false, ram_ok: false, status: 'on beam', beam: beam.id });
      continue;
    }
    // the office's scope limited to the PT band beams (`spec.scope: 'bands'`): a column outside every band stands in the
    // consultant's slab - its punching is the consultant's design, not checked here (the engineer's RAM report still wins)
    if (spec.scope === 'bands' && !columnInBand(level, c, spec) && !ramFailed.has(String(c.id).toUpperCase())) {
      out.columns.push({ id: c.id, loc: 'slab', h, d: null, trib_m2: null, wu_kn_m2: null, Vu_kn: null, bo_mm: null, vu_mpa: null, phi_vc_mpa: null, phi_vmax_mpa: null, ratio: null, fpc_mpa: null, rule: 'OTHERS', ssr: false, trib_source: '-', ram_failed: false, ram_ok: false, status: 'out of scope' });
      continue;
    }
    const pc = checks.find((p) => dist(p.p, cc) < Math.max(w, hh, 400));
    const d = Math.max(h - (pc?.coverToCgs || (spec.cover || 25) + 16), 0.6 * h);
    const set = ssrSets.find((st) => dist(st.loc, cc) < Math.max(w, hh, 400));
    // location: edges of the slab outline within the shear perimeter reach
    const reach = Math.max(w, hh) / 2 + 2 * d + 100;
    const edges = outline.length ? edgesNear(outline, cc, reach) : 0;
    const loc = edges >= 2 ? 'corner' : edges === 1 ? 'edge' : 'interior';
    // loads on the tributary area (RAM's own tributary area when the punching check carries it)
    const trib = pc?.tribArea || tribEstimate.get(c.id) || 0;
    const q = { dead: 0, live: 0 };
    for (const kind of ['dead', 'live']) {
      const here = loads.filter((l) => l.type === kind && pointInPolygon(cc, l.polygon));
      const any = loads.filter((l) => l.type === kind);
      q[kind] = here.length ? Math.max(...here.map((l) => l.q)) : any.length ? Math.max(...any.map((l) => l.q)) : 0;
    }
    const sw = CONCRETE * (h / 1000);
    const wu = 1.2 * (sw + q.dead) + 1.6 * q.live; // kN/m²
    const Vu = wu * trib * GAMMA[loc]; // kN
    // critical perimeter at d/2 from the faces
    const c1 = w, c2 = hh;
    const per = perimeterAt(loc, c1, c2, d / 2, c.shape === 'circle');
    const vu = (Vu * 1000) / (per.bo * d); // MPa
    const beta = Math.max(c1, c2) / Math.max(1, Math.min(c1, c2));
    const aS = ALPHA_S[loc];
    // ACI 318-19 22.6.5: PT provisions for interior columns with a known precompression, else the non-prestressed vc
    const ptRule = loc === 'interior' && fpc != null && fc <= 70;
    const vc = ptRule
      ? Math.min(0.29, 0.083 * aS * d / per.bo + 0.125) * sqrtFc + 0.3 * Math.min(3.5, Math.max(0.9, fpc))
      : Math.min(0.33, 0.17 * (1 + 2 / beta), 0.083 * (aS * d / per.bo + 2)) * sqrtFc;
    const vMax = 0.5 * sqrtFc; // the most the office stirrup detail can carry (stud rails 0.66)
    const ratio = vu / (PHI * vc), ratioMax = vu / (PHI * vMax);
    let status = ratio <= 1 ? 'ok' : ratioMax <= 1 ? 'reinforce' : 'fail';
    const id = String(c.id).toUpperCase();
    const col = {
      id: c.id, loc, h, d: Math.round(d), trib_m2: r2(trib), wu_kn_m2: r2(wu), Vu_kn: Math.round(Vu), bo_mm: Math.round(per.bo), vu_mpa: r2(vu), phi_vc_mpa: r2(PHI * vc), phi_vmax_mpa: r2(PHI * vMax), ratio: r2(ratio),
      fpc_mpa: ptRule ? r2(Math.min(3.5, Math.max(0.9, fpc))) : null, rule: ptRule ? 'PT' : 'RC', ssr: !!set, trib_source: pc?.tribArea ? 'RAM' : 'estimated',
      ram_failed: ramFailed.has(id), ram_ok: ramOk.has(id), status,
    };
    // what the office detail would need at this column if it is reinforced here (rows at S covering the outer perimeter
    // where the concrete alone carries 0.17 sqrt(f'c); legs from Av/s = (vu - phi 0.17 sqrt(f'c)) bo / (phi fy))
    if (status !== 'ok' || col.ram_failed) {
      const vcs = 0.17 * sqrtFc;
      const boOut = (Vu * 1000) / (PHI * vcs * d);
      const x = Math.max(0, (boOut - per.b00) / per.k - d / 2);
      const rows = Math.min(30, Math.max(loc === 'interior' ? 10 : 12, Math.ceil(x / psS) + 1)); // capped at 3 m of strips: past that the slab needs thickening, not stirrups
      const avS = Math.max(0, (vu - PHI * vcs) * per.bo / (PHI * fy)); // mm²/mm
      const strips = loc === 'interior' ? 4 : loc === 'edge' ? 3 : 2;
      const legs = Math.min(12, Math.max(4, 2 * Math.ceil((avS * psS) / legArea / strips / 2)));
      col.detail = { rows, legs, s: psS, dia: psDia, avS: r2(avS) };
    }
    out.columns.push(col);
    const flagged = col.ram_failed || (status === 'fail' && !col.ram_ok) || (status === 'reinforce' && !set && !col.ram_ok);
    if (flagged) {
      out.flagged.push(col.id);
      if (col.ram_failed || status === 'fail') out.blocking.push(col.id); else out.warnings.push(col.id);
    }
  }
  out.fpc_mpa = fpc != null ? r2(fpc) : null;
  out.fc = fc;
  return out;
}

/** The slab area nearest to each column (m²): the outline sampled on a grid, every sample given to its nearest column. */
export function tributaryAreas(level) {
  const out = new Map();
  const cols = level.columns || [];
  const outline = level.outline || [];
  if (!cols.length || outline.length < 3) return out;
  const b = bbox(outline);
  const A = Math.abs(polygonArea(outline));
  const step = Math.max(200, Math.sqrt(A / 4000));
  const holes = (level.openings || []).map((o) => o.polygon).filter((p) => p && p.length >= 3);
  const walls = (level.walls || []).filter((w) => w.polygon && w.polygon.length >= 3);
  const counts = new Map();
  for (let y = b.minY + step / 2; y < b.maxY; y += step) for (let x = b.minX + step / 2; x < b.maxX; x += step) {
    const p = { x, y };
    if (!pointInPolygon(p, outline) || holes.some((h) => pointInPolygon(p, h))) continue;
    let best = null, bd = Infinity;
    for (const c of cols) { const dd = Math.hypot(c.cx - x, c.cy - y); if (dd < bd) { bd = dd; best = c; } }
    // a wall nearer than the nearest column carries this sample
    if (walls.some((w) => distToPolygon(p, w.polygon) < bd)) continue;
    counts.set(best.id, (counts.get(best.id) || 0) + 1);
  }
  for (const [id, n] of counts) out.set(id, (n * step * step) / 1e6);
  return out;
}

/** Slab edges of the outline within `reach` of the column centre (each straight side counted once). */
function edgesNear(outline, p, reach) {
  let n = 0;
  for (let i = 0; i < outline.length; i++) {
    const a = outline[i], b = outline[(i + 1) % outline.length];
    if (dist(a, b) < 50) continue;
    if (distToSegment(p, a, b) < reach) n++;
  }
  return Math.min(n, 2);
}

function distToSegment(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
  const t = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

/** The critical perimeter at offset r from the column faces: b0(r) = b00 + k r (k = 8 / 4 / 2 interior / edge / corner). */
function perimeterAt(loc, c1, c2, r, circle) {
  if (circle) { const D = c1; return loc === 'interior' ? { bo: Math.PI * (D + 2 * r), b00: Math.PI * D, k: 2 * Math.PI } : loc === 'edge' ? { bo: (Math.PI * (D + 2 * r)) / 2 + D + 2 * r, b00: (Math.PI * D) / 2 + D, k: Math.PI + 2 } : { bo: (Math.PI * (D + 2 * r)) / 4 + D + 2 * r, b00: (Math.PI * D) / 4 + D, k: Math.PI / 2 + 2 }; }
  if (loc === 'interior') return { bo: 2 * (c1 + c2) + 8 * r, b00: 2 * (c1 + c2), k: 8 };
  if (loc === 'edge') return { bo: c1 + 2 * c2 + 4 * r, b00: c1 + 2 * c2, k: 4 };
  return { bo: c1 + c2 + 2 * r, b00: c1 + c2, k: 2 };
}

/** Average precompression of the level (MPa): the effective force of each tendon set over the slab section across it. */
export function precompression(level) {
  const tendons = level.ram?.tendons || [];
  const pt = level.ram?.pt || {};
  if (!tendons.length || !pt.strandArea || !pt.fse || !level.outline?.length) return null;
  const b = bbox(level.outline);
  const h = level.thickness || 0;
  const vals = [];
  for (const set of ['latitude', 'longitude']) {
    const ts = tendons.filter((t) => t.spanSet === set);
    if (!ts.length) continue;
    // the tendons of a set run one way: the section across them is the slab extent perpendicular to their direction
    const dir = ts.map((t) => { const a = t.pts[0], z = t.pts[t.pts.length - 1]; return Math.abs(z.x - a.x) >= Math.abs(z.y - a.y) ? 'x' : 'y'; });
    const alongX = dir.filter((v) => v === 'x').length >= dir.length / 2;
    const width = alongX ? b.h : b.w; // mm
    const F = ts.reduce((s, t) => s + (t.strands || 1) * pt.strandArea * pt.fse, 0); // N
    if (width > 0 && h > 0) vals.push(F / (width * h));
  }
  if (!vals.length) return null;
  return vals.reduce((s, v) => s + v, 0) / vals.length;
}

/** The columns to draw punching reinforcement at under an engineer's bypass (`override.columns` = 'all' → every flagged column). */
export function overrideColumns(check, override) {
  if (!override || !check) return new Set();
  if (override.columns === 'all' || !override.columns) return new Set(check.flagged);
  return new Set(override.columns.map((v) => String(v).trim().toUpperCase()));
}

/** Which flagged columns still block the run after the engineer's decision. */
export function blockingAfter(check, decision) {
  if (!check) return [];
  const blocking = new Set(check.blocking);
  if (!decision || decision.mode === 'thicken') return [...blocking];
  const covered = decision.columns === 'all' || !decision.columns ? new Set(check.flagged.map((v) => String(v).toUpperCase())) : new Set(decision.columns.map((v) => String(v).trim().toUpperCase()));
  return [...blocking].filter((id) => !covered.has(String(id).toUpperCase()));
}
