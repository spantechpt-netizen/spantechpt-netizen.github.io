/**
 * The office beam design: the beams of a RAM level analysed and designed here, beside (or instead of) the bars RAM
 * designed for them.
 *
 * RAM Concept keeps no strip forces in the .cpt, so the moments and shears come from the program's own analysis:
 * every beam is a continuous beam over the columns and walls it rests on (the same spans the beam strips use), the
 * load on it is the slab it carries (a tributary width to the next parallel beam / wall / column line or the slab
 * edge on each side) with the slab self-weight, the beam web below the slab and the area loads by loading type
 * read from the file, factored 1.2 D + 1.6 L. The elastic envelope comes from the three-moment equation with the
 * live load patterned (all spans, alternate spans, adjacent pairs); an end span framing into a column takes at
 * least wu L² / 16 hogging (SBC 304 / ACI 318 6.5). Flexure is designed as a singly reinforced rectangular section
 * (tension-controlled, As,min), shear with two-legged stirrups (Vc = 0.17 sqrt(f'c) b d, Vs limits, spacing
 * limits, minimum stirrups), and the deflection is checked by the span / depth table first and by calculation
 * (Branson's Ie, immediate + long-term with lambda = 2, L / 240 in all and L / 360 live) where the table is not met.
 *
 * The result is indicative: the RAM design report governs. A beam failing deflection (or a section that cannot
 * carry its moment / shear) blocks the run in the app until the engineer decides, exactly like the punching alert.
 */
import { dist, pointInPolygon, distToPolygon } from './geometry.mjs';
import { beamSpans } from './beam-strips.mjs';
import { beamsByOthers } from './rebar.mjs';

const PHI_F = 0.9, PHI_V = 0.75;
const CONCRETE = 25; // kN/m³
const BAR_AREA = (d) => (Math.PI * d * d) / 4;
const barsText = (n, dia) => (n && dia ? `${n}T${dia}` : '-');
const r1 = (v) => Math.round(v * 10) / 10;
const r2 = (v) => Math.round(v * 100) / 100;
const ASSUMED = { dead: 2.5, live: 2.0 }; // kN/m² when the file carries no area loads
const MAIN_DIAS = [12, 16, 20, 25, 32];

/** Bars of the smallest area not under `asReq` (mm²) that fit the width (at least two, clear spacing >= max(25, dia)). */
export function pickBars(asReq, width, cover = 40) {
  let best = null;
  for (const dia of MAIN_DIAS) {
    const s = Math.max(25, dia);
    const nMax = Math.max(2, Math.floor((width - 2 * cover - 2 * 10 + s) / (dia + s)));
    for (let n = 2; n <= nMax; n++) {
      const area = n * BAR_AREA(dia);
      if (area < asReq) continue;
      if (!best || area < best.area - 1 || (Math.abs(area - best.area) <= 1 && n < best.n)) best = { n, dia, area: Math.round(area), text: barsText(n, dia) };
      break;
    }
  }
  if (!best) { const dia = 32, n = Math.ceil(asReq / BAR_AREA(dia)); best = { n, dia, area: Math.round(n * BAR_AREA(dia)), text: barsText(n, dia), overflow: true }; }
  return best;
}

/**
 * Support moments of a continuous beam (three-moment equation, pinned ends with known end moments): `L` in mm,
 * `w` per span in kN/m, `mEnd` = [left, right] hogging moments in kN·m (negative) applied at the ends (cantilevers).
 */
export function threeMoment(L, w, mEnd = [0, 0]) {
  const n = L.length;
  const M = new Array(n + 1).fill(0);
  M[0] = mEnd[0] || 0; M[n] = mEnd[1] || 0;
  if (n < 2) return M;
  // unknowns M[1..n-1]; tridiagonal system in kN·m and m
  const Lm = L.map((v) => v / 1000);
  const a = [], b = [], c = [], d = [];
  for (let i = 1; i < n; i++) {
    a.push(Lm[i - 1]); b.push(2 * (Lm[i - 1] + Lm[i])); c.push(Lm[i]);
    let rhs = -(w[i - 1] * Lm[i - 1] ** 3 + w[i] * Lm[i] ** 3) / 4;
    if (i === 1) rhs -= M[0] * Lm[0];
    if (i === n - 1) rhs -= M[n] * Lm[n - 1];
    d.push(rhs);
  }
  // Thomas algorithm
  const m = d.length;
  for (let i = 1; i < m; i++) { const f = a[i] / b[i - 1]; b[i] -= f * c[i - 1]; d[i] -= f * d[i - 1]; }
  const x = new Array(m).fill(0);
  x[m - 1] = d[m - 1] / b[m - 1];
  for (let i = m - 2; i >= 0; i--) x[i] = (d[i] - c[i] * x[i + 1]) / b[i];
  for (let i = 1; i < n; i++) M[i] = x[i - 1];
  return M;
}

/** Span results from the end moments: max positive moment, the end shears (kN, kN·m; L in mm, w kN/m). */
function spanForces(L, w, Ma, Mb) {
  const Lm = L / 1000;
  const Va = (w * Lm) / 2 + (Mb - Ma) / Lm; // reaction at a (upwards) for hogging moments negative
  const Vb = w * Lm - Va;
  const x = w > 0 ? Math.max(0, Math.min(Lm, Va / w)) : Lm / 2;
  const Mmax = Ma + Va * x - (w * x * x) / 2;
  return { Va, Vb, Mpos: Math.max(0, Mmax), x: x * 1000 };
}

/**
 * The envelope of a beam over its spans under dead + patterned live load: hogging at every support (min), sagging
 * per span (max), shears at each span end (max), and the service (unfactored, all spans) moments for deflection.
 */
export function analyseBeam(spans, wD, wL, cantilevers = { left: null, right: null }) {
  const L = spans.map((s) => s.length);
  const n = L.length;
  const cases = [];
  const all = spans.map(() => 1);
  cases.push(all);
  if (n > 1) {
    cases.push(spans.map((_, i) => (i % 2 === 0 ? 1 : 0)));
    cases.push(spans.map((_, i) => (i % 2 === 1 ? 1 : 0)));
    for (let i = 1; i < n; i++) cases.push(spans.map((_, k) => (k === i - 1 || k === i ? 1 : 0)));
  }
  const factored = (live) => spans.map((_, i) => 1.2 * wD + 1.6 * wL * live[i]);
  const endM = (wLc) => [cantilevers.left ? -(wLc * (cantilevers.left / 1000) ** 2) / 2 : 0, cantilevers.right ? -(wLc * (cantilevers.right / 1000) ** 2) / 2 : 0];
  const Mneg = new Array(n + 1).fill(0), Mpos = new Array(n).fill(0), Vend = spans.map(() => [0, 0]);
  for (const live of cases) {
    const w = factored(live);
    const M = threeMoment(L, w, endM(1.2 * wD + 1.6 * wL));
    for (let i = 0; i <= n; i++) Mneg[i] = Math.min(Mneg[i], M[i]);
    for (let i = 0; i < n; i++) {
      const f = spanForces(L[i], w[i], M[i], M[i + 1]);
      Mpos[i] = Math.max(Mpos[i], f.Mpos);
      Vend[i][0] = Math.max(Vend[i][0], Math.abs(f.Va)); Vend[i][1] = Math.max(Vend[i][1], Math.abs(f.Vb));
    }
  }
  // service, all spans loaded, dead and live apart (for the deflection)
  const svc = (w) => { const M = threeMoment(L, spans.map(() => w), endM(w)); return { M, pos: spans.map((_, i) => spanForces(L[i], w, M[i], M[i + 1]).Mpos) }; };
  return { Mneg, Mpos, Vend, service: { dead: svc(wD), live: svc(wL) } };
}

/** Required tension steel (mm²) of a rectangular section for Mu (kN·m); null when the section cannot carry it singly reinforced. */
export function flexureAs(Mu, b, d, fc, fy) {
  if (Mu <= 0) return { as: 0, ok: true };
  const M = (Mu * 1e6) / PHI_F; // N·mm
  const k = (fy * fy) / (1.7 * fc * b);
  const disc = (fy * d) ** 2 - 4 * k * M;
  if (disc < 0) return { as: null, ok: false };
  const as = (fy * d - Math.sqrt(disc)) / (2 * k);
  const a = (as * fy) / (0.85 * fc * b);
  const beta1 = fc <= 28 ? 0.85 : Math.max(0.65, 0.85 - 0.05 * ((fc - 28) / 7));
  const c = a / beta1;
  const et = (0.003 * (d - c)) / c;
  return { as, ok: et >= 0.004, et: r2(et) };
}

/** Stirrups for Vu (kN) at d from the face: dia / legs / spacing, or null when the section is too small in shear. */
export function shearDesign(Vu, b, d, fc, fy) {
  const sq = Math.sqrt(fc);
  const Vc = 0.17 * sq * b * d; // N
  const VsMax = 0.66 * sq * b * d;
  const VuN = Vu * 1000;
  if (VuN > PHI_V * (Vc + VsMax)) return { ok: false, Vc: r1(Vc / 1000), Vs: r1((VuN / PHI_V - Vc) / 1000) };
  const Vs = Math.max(0, VuN / PHI_V - Vc);
  const heavy = Vs > 0.33 * sq * b * d;
  for (const dia of [10, 12]) for (const legs of [2, 4]) {
    const Av = legs * BAR_AREA(dia);
    let s = Math.min(heavy ? d / 4 : d / 2, heavy ? 300 : 600, (Av * fy) / (0.062 * sq * b), (Av * fy) / (0.35 * b));
    if (Vs > 0) s = Math.min(s, (Av * fy * d) / Vs);
    if (VuN <= 0.5 * PHI_V * Vc) s = Math.min(d / 2, 600); // no shear reinforcement required: nominal stirrups
    s = Math.max(50, Math.floor(s / 25) * 25);
    if (s >= 75 || (dia === 12 && legs === 4)) return { ok: true, dia, legs, spacing: s, Vc: r1(Vc / 1000), Vs: r1(Vs / 1000), text: `T${dia}-${legs}L@${s}` };
  }
  return { ok: false, Vc: r1(Vc / 1000), Vs: r1(Vs / 1000) };
}

/** Deflection of one span: the span / depth table, else the calculated immediate + long-term deflection against L/240 and L/360 (live). */
export function deflectionCheck({ L, b, h, d, as, fc, ends, Ma, MaLeft, MaRight, live, cantilever = false }) {
  const ratioTable = cantilever ? 8 : ends === 2 ? 21 : ends === 1 ? 18.5 : 16;
  const hMin = L / ratioTable;
  const out = { L, h_min: Math.round(hMin), table_ok: h >= hMin, ratio: 0, ok: true };
  if (out.table_ok) return out;
  const Ec = 4700 * Math.sqrt(fc), n = 200000 / Ec;
  const Ig = (b * h ** 3) / 12;
  const Mcr = (0.62 * Math.sqrt(fc) * Ig) / (h / 2); // N·mm
  const kd = (() => { const A = b / 2, B = n * as, C = -n * as * d; return (-B + Math.sqrt(B * B - 4 * A * C)) / (2 * A); })();
  const Icr = (b * kd ** 3) / 3 + n * as * (d - kd) ** 2;
  const total = Math.max(1, Ma) * 1e6; // N·mm, service all loads
  const rr = Math.min(1, Mcr / total) ** 3;
  const Ie = Math.min(Ig, rr * Ig + (1 - rr) * Icr);
  const liveShare = Ma > 0 ? live / Ma : 0;
  let delta;
  if (cantilever) delta = ((Ma * 1e6) * L * L) / (4 * Ec * Ie); // w L^4 / (8 E I) with M = w L^2 / 2
  else delta = ((5 * L * L) / (48 * Ec * Ie)) * (Ma - 0.1 * (Math.abs(MaLeft || 0) + Math.abs(MaRight || 0))) * 1e6;
  delta = Math.max(0, delta);
  const dLive = delta * liveShare, dDead = delta - dLive;
  const longTerm = 2.0 * dDead + dLive; // lambda = 2 on the sustained (dead) part, immediate live on top
  const Leff = cantilever ? 2 * L : L;
  out.delta_immediate = r1(delta); out.delta_live = r1(dLive); out.delta_long_term = r1(longTerm);
  out.limit_total = r1(Leff / 240); out.limit_live = r1(Leff / 360);
  out.ratio = r2(Math.max(longTerm / (Leff / 240), dLive / (Leff / 360)));
  out.ok = out.ratio <= 1;
  out.Ie_ratio = r2(Ie / Ig);
  return out;
}

/** The slab width each side of the beam that loads it (mm): half way to the next parallel beam / wall / column line, or to the slab edge. */
function tributaryWidth(bm, level, spans) {
  const L = dist(bm.a, bm.b) || 1;
  const u = { x: (bm.b.x - bm.a.x) / L, y: (bm.b.y - bm.a.y) / L }, nrm = { x: -u.y, y: u.x };
  const mid = { x: (bm.a.x + bm.b.x) / 2, y: (bm.a.y + bm.b.y) / 2 };
  const along = (p) => (p.x - bm.a.x) * u.x + (p.y - bm.a.y) * u.y;
  const offset = (p) => (p.x - bm.a.x) * nrm.x + (p.y - bm.a.y) * nrm.y;
  const cap = Math.max(3000, 0.6 * Math.max(...spans.map((s) => s.length), 0));
  const sides = {};
  for (const sg of [1, -1]) {
    let best = cap * 2;
    // parallel beams and walls overlapping this beam's length
    for (const o of [...(level.beams || []).filter((x) => x !== bm && x.id !== bm.id), ...(level.walls || [])]) {
      if (!o.a || !o.b) continue;
      const Lo = dist(o.a, o.b) || 1, v = { x: (o.b.x - o.a.x) / Lo, y: (o.b.y - o.a.y) / Lo };
      if (Math.abs(u.x * v.x + u.y * v.y) < 0.9) continue;
      const t0 = along(o.a), t1 = along(o.b);
      if (Math.max(t0, t1) < 0 || Math.min(t0, t1) > L) continue;
      const off = offset(o.a) * sg;
      if (off > bm.t / 2 + 50) best = Math.min(best, off / 2);
    }
    // a column line beside the beam (columns off its axis, within its length)
    for (const c of level.columns || []) {
      const p = { x: c.cx, y: c.cy };
      const t = along(p), off = offset(p) * sg;
      if (t < -500 || t > L + 500) continue;
      if (off > Math.max(c.w || 0, c.h || 0, c.d || 0) / 2 + bm.t / 2 + 50) best = Math.min(best, off / 2);
    }
    // the slab edge, walked along the normal from the beam middle
    let edge = 0;
    for (let s = 100; s <= cap * 2; s += 100) { const p = { x: mid.x + nrm.x * sg * s, y: mid.y + nrm.y * sg * s }; if (!pointInPolygon(p, level.outline)) { edge = s; break; } edge = s; }
    best = Math.min(best, edge, cap);
    sides[sg] = Math.max(0, best);
  }
  return { left: Math.round(sides[1]), right: Math.round(sides[-1]), total: Math.round(sides[1] + sides[-1]) };
}

/**
 * Designs every beam of the level. `spec`: fc, fy, beamCover (40), beams.ramFailed (ids the engineer reports failing
 * deflection in RAM). Returns per beam the loads, the envelope, the bars designed and the checks, plus the lists of
 * failing / blocking beams.
 */
export function designBeams(level, spec = {}) {
  const out = { method: 'office', beams: [], failing: [], blocking: [], warnings: [], assumed: [] };
  const beams = level.beams || [];
  if (!beams.length) return out;
  const fc = spec.fc || 30, fy = spec.fy || 420, cover = spec.beamCover || 40;
  const loads = level.ram?.areaLoads || [];
  const hSlab = level.thickness || 250;
  const ramFailed = new Set((spec.beams?.ramFailed || []).map((v) => String(v).trim().toUpperCase()));
  // beams assigned a type of the consultant's / project's schedule (spec.beamAssign) keep that design: not designed here
  const assigned = new Set(Object.keys(spec.beamAssign || {}).map((v) => String(v).trim().toUpperCase()));
  const others = beamsByOthers(level, spec); // the consultant's RC beams: not the office's to design
  const noLoads = !loads.length;
  if (noLoads) out.assumed.push(`no area loads in the model: SDL ${ASSUMED.dead} kN/m² and LL ${ASSUMED.live} kN/m² assumed`);
  // a beam end on a drawing joint (a part of a split slab): the slab - and the beam - go on beyond it
  const joints = level.jointEdges || [];
  const pc = level.partCut;
  const distToSeg = (p, a, b) => { const L2 = (b.x - a.x) ** 2 + (b.y - a.y) ** 2; const t = L2 ? Math.max(0, Math.min(1, ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / L2)) : 0; return Math.hypot(p.x - (a.x + t * (b.x - a.x)), p.y - (a.y + t * (b.y - a.y))); };
  const atJoint = (p) => joints.some((e) => distToSeg(p, e.a, e.b) < 400) || Boolean(pc && ((pc.joints?.lo && Math.abs(p[pc.axis] - (pc.lo - (pc.overlap ?? 600))) < 400) || (pc.joints?.hi && Math.abs(p[pc.axis] - (pc.hi + (pc.overlap ?? 600))) < 400)));
  for (const bm of beams) {
    if (assigned.has(String(bm.id).toUpperCase()) || others.has(String(bm.id).toUpperCase())) continue;
    const sp = beamSpans(bm, level.columns || [], level.walls || [], beams); // (a deeper beam crossing it is a support)
    const L = dist(bm.a, bm.b);
    const mid = { x: (bm.a.x + bm.b.x) / 2, y: (bm.a.y + bm.b.y) / 2 };
    const q = {};
    for (const kind of ['dead', 'live']) {
      const here = loads.filter((l) => l.type === kind && pointInPolygon(mid, l.polygon)), any = loads.filter((l) => l.type === kind);
      q[kind] = here.length ? Math.max(...here.map((l) => l.q)) : any.length ? Math.max(...any.map((l) => l.q)) : ASSUMED[kind];
    }
    // spans: the end pieces beyond the first / last support are cantilevers - unless the piece ends at a drawing
    // joint (the slab was split into parts for the sheets): there the beam goes on into the neighbouring part and is
    // continuous, so that end is taken as an interior support (hogging wu L² / 16), never as a free end
    let spans = sp.spans.slice();
    const cant = { left: null, right: null };
    const jointEnds = [];
    if (spans.length && !spans[0].support0 && atJoint(bm.a)) { spans[0] = { ...spans[0], support0: { kind: 'joint' } }; jointEnds.push('start'); }
    if (spans.length && !spans[spans.length - 1].support1 && atJoint(bm.b)) { spans[spans.length - 1] = { ...spans[spans.length - 1], support1: { kind: 'joint' } }; jointEnds.push('end'); }
    if (jointEnds.length) out.warnings.push(`${bm.id}: continues into the neighbouring part at its ${jointEnds.join(' and ')} (drawing joint) - designed as a continuous beam, not a cantilever; the whole beam is designed on the unsplit slab`);
    if (spans.length > 1 && !spans[0].support0) { cant.left = spans[0].length; spans = spans.slice(1); }
    if (spans.length > 1 && !spans[spans.length - 1].support1) { cant.right = spans[spans.length - 1].length; spans = spans.slice(0, -1); }
    const noSupports = !spans.some((s) => s.support0 || s.support1);
    const trib = tributaryWidth(bm, level, spans);
    const depth = bm.depth || hSlab;
    const web = (CONCRETE * (bm.t / 1000) * Math.max(0, depth - hSlab)) / 1000; // kN/m
    const wD = r2((CONCRETE * (hSlab / 1000) + q.dead) * (trib.total / 1000) + web);
    const wL = r2(q.live * (trib.total / 1000));
    const wu = r2(1.2 * wD + 1.6 * wL);
    const env = analyseBeam(spans, wD, wL, cant);
    const d = depth - cover - 10 - 8;
    const b = bm.t;
    const reasons = [];
    // hogging at the supports: at least wu L² / 16 at an end framing into a column, wu L² / 24 into a wall
    const supportKind = (i) => (i === 0 ? spans[0].support0?.kind : i === spans.length ? spans[spans.length - 1].support1?.kind : 'interior');
    const Mneg = env.Mneg.map((m, i) => {
      const kind = supportKind(i);
      const Ls = (i === 0 ? spans[0].length : spans[i - 1].length) / 1000;
      const min = kind === 'column' ? (wu * Ls * Ls) / 16 : kind === 'wall' ? (wu * Ls * Ls) / 24 : 0;
      return -Math.max(Math.abs(m), kind ? min : 0);
    });
    const topAs = Math.max(...Mneg.map((m) => { const f = flexureAs(Math.abs(m), b, d, fc, fy); if (!f.ok) reasons.push('flexure'); return f.as ?? Infinity; }), 0);
    const botAs = Math.max(...env.Mpos.map((m) => { const f = flexureAs(m, b, d, fc, fy); if (!f.ok) reasons.push('flexure'); return f.as ?? Infinity; }), 0);
    const asMin = Math.max((0.25 * Math.sqrt(fc)) / fy, 1.4 / fy) * b * d;
    const top = Number.isFinite(topAs) ? pickBars(Math.max(topAs, asMin), b, cover) : null;
    const bottom = Number.isFinite(botAs) ? pickBars(Math.max(botAs, asMin), b, cover) : null;
    // shear at d from every support face
    let Vu = 0;
    spans.forEach((s, i) => {
      for (const [k, sup] of [[0, s.support0], [1, s.support1]]) {
        const face = ((sup?.along || 0) / 2 + d) / 1000;
        Vu = Math.max(Vu, env.Vend[i][k] - wu * face);
      }
    });
    if (cant.left) Vu = Math.max(Vu, wu * (cant.left / 1000));
    if (cant.right) Vu = Math.max(Vu, wu * (cant.right / 1000));
    const sh = shearDesign(Vu, b, d, fc, fy);
    if (!sh.ok) reasons.push('shear');
    // deflection per span, the worst governs
    const defl = spans.map((s, i) => {
      const ends = (i > 0 || cant.left ? 1 : 0) + (i < spans.length - 1 || cant.right ? 1 : 0);
      const MaD = env.service.dead.pos[i], MaL = env.service.live.pos[i];
      const asHere = Math.max(bottom?.area || 0, asMin);
      return { span: i + 1, ...deflectionCheck({ L: s.length, b, h: depth, d, as: asHere, fc, ends, Ma: MaD + MaL, MaLeft: env.service.dead.M[i] + env.service.live.M[i], MaRight: env.service.dead.M[i + 1] + env.service.live.M[i + 1], live: MaL }) };
    });
    for (const [side, Lc] of [['left', cant.left], ['right', cant.right]]) if (Lc) {
      const MaD = (wD * (Lc / 1000) ** 2) / 2, MaL = (wL * (Lc / 1000) ** 2) / 2;
      defl.push({ span: side, ...deflectionCheck({ L: Lc, b, h: depth, d, as: Math.max(top?.area || 0, asMin), fc, ends: 1, Ma: MaD + MaL, live: MaL, cantilever: true }) });
    }
    const worst = defl.slice().sort((p, q2) => q2.ratio - p.ratio)[0] || { ok: true, ratio: 0 };
    if (!worst.ok) reasons.push('deflection');
    const id = String(bm.id).toUpperCase();
    const uniq = [...new Set(reasons)];
    const row = {
      id: bm.id, width: b, depth, length: Math.round(L), spans: spans.map((s, i) => ({ length: Math.round(s.length), support0: s.support0?.kind || null, support1: s.support1?.kind || null, Mneg: r1(Math.abs(Mneg[i])), Mpos: r1(env.Mpos[i]), Vmax: r1(Math.max(...env.Vend[i])) })),
      cantilevers: cant, no_supports: noSupports, trib_mm: trib, loads: { slab_kn_m2: r2(CONCRETE * hSlab / 1000), dead_kn_m2: q.dead, live_kn_m2: q.live, web_kn_m: r2(web), wD, wL, wu },
      Mneg_max: r1(Math.max(...Mneg.map(Math.abs))), Mpos_max: r1(Math.max(...env.Mpos, 0)), Vu: r1(Vu), d,
      as_top_req: Number.isFinite(topAs) ? Math.round(Math.max(topAs, asMin)) : null, as_bottom_req: Number.isFinite(botAs) ? Math.round(Math.max(botAs, asMin)) : null,
      top, bottom, stirrups: sh.ok ? { dia: sh.dia, legs: sh.legs, spacing: sh.spacing, text: sh.text } : null, shear: sh,
      deflection: { ...worst, spans: defl }, reasons: uniq, ram_failed: ramFailed.has(id),
      status: uniq.length || ramFailed.has(id) ? 'fail' : 'ok',
    };
    out.beams.push(row);
    if (row.status === 'fail') { out.failing.push(bm.id); out.blocking.push(bm.id); }
    if (noSupports) out.warnings.push(bm.id);
  }
  return out;
}

/** Which failing beams still block the run after the engineer's decision. */
export function beamBlockingAfter(check, decision) {
  if (!check) return [];
  const blocking = check.blocking || [];
  if (!decision || decision.mode === 'deepen' || decision.mode === 'thicken') return [...blocking];
  const covered = decision.columns === 'all' || decision.beams === 'all' || !(decision.beams || decision.columns) ? new Set(blocking.map((v) => String(v).toUpperCase())) : new Set((decision.beams || decision.columns).map((v) => String(v).trim().toUpperCase()));
  return blocking.filter((id) => !covered.has(String(id).toUpperCase()));
}
