/**
 * Passive reinforcement for a post-tensioned flat slab, at design (tender)
 * stage.
 *
 * A post-tensioned slab still carries ordinary bars, and the tender drawings
 * have to show them: the bottom mesh, the additional top steel over the
 * columns, the U-bars that close every free edge — the slab perimeter, the
 * cores and the larger openings — and the trimmer and diagonal bars that make
 * up for what an opening cuts. This works all of it out from the geometry the
 * engineer enters, and lays it out so the drawings can be drawn from it.
 *
 * The rules are the code minimums (ACI 318-19 for two-way post-tensioned
 * slabs) and the details the trade uses at tender stage. They are a starting
 * point that the final analysis confirms — the drawings say so, because a
 * sheet that looks final gets built from.
 *
 * Geometry is entered in metres, from the bottom-left corner of the slab.
 * Everything computed is in millimetres, the unit the drawings are in.
 */
import { round2 } from './pricing.js';

/** Bar sizes the trade stocks, in mm. */
export const BAR_SIZES = [8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32];

/** Bars are delivered in 12 m lengths; anything longer is lapped. */
const STOCK_LENGTH_MM = 12_000;

/** kg per metre of a bar of diameter d mm: d² / 162. */
export const kgPerMetre = (d) => (d * d) / 162;

const area = (d) => (Math.PI * d * d) / 4;
const up50 = (mm) => Math.ceil(mm / 50) * 50;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

/** Tension development length at tender stage: 40 bar diameters. */
const devLength = (d) => 40 * d;
/** Lap splice: 50 bar diameters, the figure most specifications ask for. */
const lapLength = (d) => 50 * d;
/** A standard 90° hook adds twelve diameters of straight tail. */
const hookLength = (d) => 12 * d;

/** Grid line names: 1, 2, 3 … along X and A, B, C … along Y. */
export const gridNameX = (i) => String(i + 1);
export const gridNameY = (j) => {
  let n = j;
  let name = '';
  do {
    name = String.fromCharCode(65 + (n % 26)) + name;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return name;
};

/**
 * A slab to start from: three bays by two of 7.5 m, the size of a typical
 * residential floor. The engineer replaces it with the project's own grid.
 */
export function defaultRebar(study = {}) {
  return {
    spans_x: [7.5, 7.5, 7.5],
    spans_y: [7.5, 7.5],
    edge_left: 0.4,
    edge_right: 0.4,
    edge_bottom: 0.4,
    edge_top: 0.4,
    column_x_mm: 600,
    column_y_mm: 600,
    omit_columns: '',
    thickness_mm: Number(study.pt_thickness_mm) || 220,
    cover_mm: 25,

    // Bottom mesh. Zero diameter or spacing means "choose it for me".
    bottom_ratio: 0.0015,
    bottom_dia: 0,
    bottom_spacing: 0,

    // Additional top steel over the columns.
    top_dia: 16,

    // U-bars and the continuous bars they hold, on every free edge.
    ubar_dia: 12,
    ubar_spacing: 200,
    ubar_leg_mm: 0,
    edge_bar_dia: 12,
    edge_bars: 2,

    // Openings.
    trimmer_dia: 16,
    diagonal_dia: 12,
    opening_ubar_min_m: 1.0,

    cores: [],
    openings: [],
  };
}

/**
 * Chooses the lightest bottom mesh that gives the area asked for, and at equal
 * weight the wider spacing, which is quicker to fix.
 */
export function chooseMesh(requiredPerMetre, maxSpacing, dia = 0, spacing = 0) {
  const diameters = dia ? [dia] : [10, 12, 14, 16];
  const spacings = spacing ? [spacing] : [300, 250, 200, 175, 150, 125, 100];
  let best = null;
  for (const d of diameters) {
    for (const s of spacings) {
      if (!spacing && s > maxSpacing) continue;
      const provided = (area(d) * 1000) / s;
      if (provided + 1e-9 < requiredPerMetre && !(dia && spacing)) continue;
      const weight = kgPerMetre(d) * (1000 / s);
      if (!best || weight < best.weight - 1e-9 || (Math.abs(weight - best.weight) < 1e-9 && s > best.spacing)) {
        best = { dia: d, spacing: s, provided, weight };
      }
    }
  }
  // Nothing in the table is heavy enough: fall back to the heaviest, and the
  // warning that follows says it falls short.
  if (!best) {
    const d = diameters[diameters.length - 1];
    const s = spacing || 100;
    best = { dia: d, spacing: s, provided: (area(d) * 1000) / s, weight: kgPerMetre(d) * (1000 / s) };
  }
  return best;
}

/** The part of rectangle r that lies inside the slab, or null if none does. */
function clip(r, W, H) {
  const x0 = clamp(r.x, 0, W);
  const y0 = clamp(r.y, 0, H);
  const x1 = clamp(r.x + r.w, 0, W);
  const y1 = clamp(r.y + r.h, 0, H);
  if (x1 - x0 <= 0 || y1 - y0 <= 0) return null;
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

const inside = (px, py, r) => px >= r.x && px <= r.x + r.w && py >= r.y && py <= r.y + r.h;

/** Distance between two rectangles, zero where they touch or overlap. */
function gap(a, b) {
  const dx = Math.max(0, a.x - (b.x + b.w), b.x - (a.x + a.w));
  const dy = Math.max(0, a.y - (b.y + b.h), b.y - (a.y + a.h));
  return Math.hypot(dx, dy);
}

/**
 * Works out every bar on the slab.
 *
 * Returns the geometry to draw, each family of bars with where it goes, the
 * bar schedule with weights, and the warnings an engineer would want to see
 * before the sheets leave the office.
 */
export function computeRebar(raw) {
  const s = { ...defaultRebar(), ...(raw || {}) };
  const warnings = [];
  const warn = (en, ar) => warnings.push({ en, ar });

  const h = s.thickness_mm;
  const cover = s.cover_mm;

  // ------------------------------------------------------------- geometry
  const spansX = s.spans_x.map((m) => m * 1000);
  const spansY = s.spans_y.map((m) => m * 1000);
  const gridX = [s.edge_left * 1000];
  for (const span of spansX) gridX.push(gridX[gridX.length - 1] + span);
  const gridY = [s.edge_bottom * 1000];
  for (const span of spansY) gridY.push(gridY[gridY.length - 1] + span);
  const W = gridX[gridX.length - 1] + s.edge_right * 1000;
  const H = gridY[gridY.length - 1] + s.edge_top * 1000;

  const toMm = (r, i, prefix) => ({
    label: r.label || `${prefix}${i + 1}`,
    x: r.x * 1000, y: r.y * 1000, w: r.w * 1000, h: r.h * 1000,
  });
  const clipAll = (list, prefix, en, ar) => list.map((r, i) => toMm(r, i, prefix)).map((r) => {
    const c = clip(r, W, H);
    if (!c) {
      warn(`${en} ${r.label} lies outside the slab and is left off the drawings.`,
        `${ar} ${r.label} برّه حدود البلاطة ومش هيترسم.`);
      return null;
    }
    if (c.w !== r.w || c.h !== r.h) {
      warn(`${en} ${r.label} runs past the slab edge and is cut back to it.`,
        `${ar} ${r.label} خارج عن حرف البلاطة واتقصّ عنده.`);
    }
    return { ...r, ...c };
  }).filter(Boolean);

  const cores = clipAll(s.cores, 'C', 'Core', 'الكور');
  const openings = clipAll(s.openings, 'OP', 'Opening', 'الفتحة');
  const voids = [...cores, ...openings];

  const omitted = new Set(String(s.omit_columns || '')
    .toUpperCase().split(/[\s,;،]+/).map((x) => x.replace(/-/g, '')).filter(Boolean));

  const cx = s.column_x_mm;
  const cy = s.column_y_mm;
  const columns = [];
  for (let j = 0; j < gridY.length; j += 1) {
    for (let i = 0; i < gridX.length; i += 1) {
      const name = `${gridNameY(j)}${gridNameX(i)}`;
      if (omitted.has(name)) continue;
      // A column inside a core is the core's wall; inside an opening it is
      // not there at all.
      if (voids.some((v) => inside(gridX[i], gridY[j], v))) continue;
      columns.push({ name, i, j, x: gridX[i], y: gridY[j], w: cx, h: cy });
    }
  }

  const grossArea = (W * H) / 1e6;
  const voidArea = voids.reduce((sum, v) => sum + (v.w * v.h) / 1e6, 0);
  const netArea = Math.max(0, grossArea - voidArea);

  // ---------------------------------------------------------- bottom mesh
  // A uniform mesh in both directions. Below it sit the tendon chairs; above
  // it the tendons themselves.
  const meshRequired = s.bottom_ratio * 1000 * h;
  const meshMaxSpacing = Math.min(300, 2 * h);
  const mesh = chooseMesh(meshRequired, meshMaxSpacing, s.bottom_dia, s.bottom_spacing);
  if (mesh.provided + 1e-9 < meshRequired) {
    warn(`The bottom mesh T${mesh.dia}@${mesh.spacing} gives ${Math.round(mesh.provided)} mm²/m, less than the ${Math.round(meshRequired)} mm²/m asked for.`,
      `الشبكة السفلية T${mesh.dia}@${mesh.spacing} بتدّي ${Math.round(mesh.provided)} مم²/م وده أقل من المطلوب ${Math.round(meshRequired)} مم²/م.`);
  }
  if (mesh.spacing > meshMaxSpacing) {
    warn(`Bottom mesh spacing ${mesh.spacing} mm is wider than ${meshMaxSpacing} mm (the smaller of 2h and 300 mm).`,
      `تباعد الشبكة السفلية ${mesh.spacing} مم أكبر من ${meshMaxSpacing} مم (الأقل من 2h و300 مم).`);
  }

  // ------------------------------------------------ top steel at columns
  // ACI 318-19 §8.6.2.3: at every column, As ≥ 0.00075·Acf in each direction,
  // where Acf is the larger gross section of the two slab strips crossing the
  // column. §8.7.5.3: the bars sit within 1.5h of the column faces, at least
  // four of them, no more than 300 mm apart, and run a sixth of the clear
  // span past the face of the support.
  const topDia = s.top_dia;
  const topAreaBar = area(topDia);
  const tribX = (i) => ((i > 0 ? gridX[i] - gridX[i - 1] : gridX[0]) / (i > 0 ? 2 : 1))
    + ((i < gridX.length - 1 ? gridX[i + 1] - gridX[i] : W - gridX[i]) / (i < gridX.length - 1 ? 2 : 1));
  const tribY = (j) => ((j > 0 ? gridY[j] - gridY[j - 1] : gridY[0]) / (j > 0 ? 2 : 1))
    + ((j < gridY.length - 1 ? gridY[j + 1] - gridY[j] : H - gridY[j]) / (j < gridY.length - 1 ? 2 : 1));

  const topBars = [];
  for (const col of columns) {
    const acf = h * Math.max(tribX(col.i), tribY(col.j));
    const asMin = 0.00075 * acf;

    const place = (dir) => {
      const alongX = dir === 'x';
      const grid = alongX ? gridX : gridY;
      const k = alongX ? col.i : col.j;
      const c = alongX ? cx : cy;          // column size along the bars
      const cAcross = alongX ? cy : cx;    // column size across them
      const centre = alongX ? col.x : col.y;
      const across = alongX ? col.y : col.x;
      const extent = alongX ? W : H;
      const extentAcross = alongX ? H : W;

      // Past the face by ln/6 into each span; to the edge, with a hook, where
      // there is no span on that side.
      let start;
      let end;
      let hooks = 0;
      if (k > 0) start = centre - c / 2 - (grid[k] - grid[k - 1] - c) / 6;
      else { start = cover; hooks += 1; }
      if (k < grid.length - 1) end = centre + c / 2 + (grid[k + 1] - grid[k] - c) / 6;
      else { end = extent - cover; hooks += 1; }
      start = Math.max(cover, start);
      end = Math.min(extent - cover, end);
      const straight = up50(end - start);
      const length = straight + hooks * hookLength(topDia);

      // The band: the column plus 1.5h each side, kept inside the slab.
      const bandLo = Math.max(cover, across - cAcross / 2 - 1.5 * h);
      const bandHi = Math.min(extentAcross - cover, across + cAcross / 2 + 1.5 * h);
      const band = bandHi - bandLo;
      const count = Math.max(4, Math.ceil(asMin / topAreaBar), Math.ceil(band / 300) + 1);

      return {
        column: col.name, dir, dia: topDia, count, length, straight, hooks,
        start, end: start + straight, band_lo: bandLo, band_hi: bandHi,
        spacing: count > 1 ? Math.floor(band / (count - 1)) : 0,
        as_required: Math.round(asMin), as_provided: Math.round(count * topAreaBar),
      };
    };
    topBars.push(place('x'), place('y'));
  }

  // Bars identical in size, number and length share a mark.
  const topMarks = new Map();
  for (const bar of topBars) {
    const key = `${bar.dia}|${bar.count}|${bar.length}|${bar.hooks}`;
    if (!topMarks.has(key)) {
      topMarks.set(key, {
        mark: `T${topMarks.size + 1}`, dia: bar.dia, count: bar.count,
        length: bar.length, hooks: bar.hooks, sets: 0,
      });
    }
    const group = topMarks.get(key);
    group.sets += 1;
    bar.mark = group.mark;
  }

  // ------------------------------------------------------------- U-bars
  // Every free edge is closed by U-bars at regular centres, holding continuous
  // bars top and bottom: the slab perimeter, each core, and each opening big
  // enough for tendons to stop at it.
  const uDia = s.ubar_dia;
  const uLeg = s.ubar_leg_mm || up50(Math.max(500, devLength(uDia), 2 * h));
  const uWidth = h - 2 * cover - uDia;
  const uLength = 2 * uLeg + uWidth;
  const minOpeningForU = s.opening_ubar_min_m * 1000;

  const edgeRuns = [];
  const addRun = (owner, kind, side, x1, y1, x2, y2) => {
    const length = Math.hypot(x2 - x1, y2 - y1);
    if (length <= 0) return;
    const count = Math.floor((length - 2 * cover) / s.ubar_spacing) + 1;
    edgeRuns.push({ owner, kind, side, x1, y1, x2, y2, length, count });
  };
  // Legs point into the slab: on the perimeter inward, around a void outward.
  addRun('slab', 'perimeter', 'bottom', 0, 0, W, 0);
  addRun('slab', 'perimeter', 'right', W, 0, W, H);
  addRun('slab', 'perimeter', 'top', W, H, 0, H);
  addRun('slab', 'perimeter', 'left', 0, H, 0, 0);
  const aroundVoid = (v, kind) => {
    addRun(v.label, kind, 'bottom', v.x, v.y, v.x + v.w, v.y);
    addRun(v.label, kind, 'right', v.x + v.w, v.y, v.x + v.w, v.y + v.h);
    addRun(v.label, kind, 'top', v.x + v.w, v.y + v.h, v.x, v.y + v.h);
    addRun(v.label, kind, 'left', v.x, v.y + v.h, v.x, v.y);
  };
  for (const core of cores) aroundVoid(core, 'core');
  for (const op of openings) {
    if (Math.min(op.w, op.h) >= minOpeningForU) aroundVoid(op, 'opening');
  }

  // --------------------------------------------------- openings, trimmers
  // An opening interrupts the bottom mesh. The bars it cuts are replaced
  // alongside it, half on each side, running a development length past each
  // corner; every corner also gets a diagonal bar top and bottom against the
  // crack that starts there. Small openings are left to push the bars aside.
  const trimDia = s.trimmer_dia;
  const diagDia = s.diagonal_dia;
  const diagLength = up50(Math.max(1000, 2 * devLength(diagDia)));
  const openingDetails = openings.map((op) => {
    if (Math.max(op.w, op.h) < 300) {
      return { label: op.label, small: true, x: op.x, y: op.y, w: op.w, h: op.h };
    }
    const cutAlongX = Math.ceil(op.h / mesh.spacing);   // X-bars the opening cuts
    const cutAlongY = Math.ceil(op.w / mesh.spacing);
    const perSide = (cut) => Math.max(2, Math.ceil((cut * area(mesh.dia)) / 2 / area(trimDia)));
    const ext = up50(devLength(trimDia));
    const x = {
      dir: 'x', count: perSide(cutAlongX), dia: trimDia,
      length: up50(op.w + 2 * ext), ext,
    };
    const y = {
      dir: 'y', count: perSide(cutAlongY), dia: trimDia,
      length: up50(op.h + 2 * ext), ext,
    };
    const near = columns.filter((c) => gap(op, {
      x: c.x - c.w / 2, y: c.y - c.h / 2, w: c.w, h: c.h,
    }) < 4 * h);
    if (near.length) {
      warn(`Opening ${op.label} is within 4h of column ${near.map((c) => c.name).join(', ')}: reduce the punching perimeter per ACI 318-19 §22.6.4.3 and check punching shear.`,
        `الفتحة ${op.label} في حدود 4h من العمود ${near.map((c) => c.name).join('، ')}: لازم تتخصم من محيط الاختراق (ACI 318-19 §22.6.4.3) ويتراجع الاختراق.`);
    }
    return {
      label: op.label, small: false, x: op.x, y: op.y, w: op.w, h: op.h,
      trimmers: [x, y], diagonal: { dia: diagDia, length: diagLength, count: 8 },
      ubars: Math.min(op.w, op.h) >= minOpeningForU,
    };
  });

  // Cores carry diagonal bars at their four corners as well: the slab has a
  // re-entrant corner at each of them.
  const coreDiagonals = cores.length * 8;

  // --------------------------------------------------------- the schedule
  const schedule = [];
  const row = (entry) => {
    const totalM = (entry.count * entry.length) / 1000;
    schedule.push({
      ...entry,
      total_m: round2(totalM),
      weight_kg: round2(totalM * kgPerMetre(entry.dia)),
    });
  };

  // Mesh: bars across the net area at their spacing, with a lap wherever a
  // run is longer than a stock bar.
  const meshRow = (mark, dir) => {
    const run = dir === 'x' ? W - 2 * cover : H - 2 * cover;
    const acrossRun = dir === 'x' ? H - 2 * cover : W - 2 * cover;
    const laps = Math.max(0, Math.ceil(run / STOCK_LENGTH_MM) - 1);
    const barLength = run + laps * lapLength(mesh.dia);
    const count = Math.floor(acrossRun / mesh.spacing) + 1;
    // The voids take their share of the bars out.
    const fullLength = count * barLength;
    const lost = voids.reduce((sum, v) => sum + (v.w * v.h) / mesh.spacing, 0);
    const effectiveCount = Math.max(0, (fullLength - lost) / barLength);
    row({
      mark, family: 'mesh', dir, dia: mesh.dia, shape: 'straight',
      count: Math.ceil(effectiveCount), length: Math.round(barLength),
      spacing: mesh.spacing, laps,
    });
  };
  meshRow('B1', 'x');
  meshRow('B2', 'y');

  for (const group of topMarks.values()) {
    row({
      mark: group.mark, family: 'top', dia: group.dia,
      shape: group.hooks ? 'hooked' : 'straight',
      count: group.count * group.sets, length: group.length,
      sets: group.sets, per_set: group.count,
    });
  }

  const runsOf = (kinds) => edgeRuns.filter((r) => kinds.includes(r.kind));
  const uCount = (kinds) => runsOf(kinds).reduce((sum, r) => sum + r.count, 0);
  const edgeMetres = (kinds) => runsOf(kinds).reduce((sum, r) => sum + r.length, 0);
  const edgeBarRow = (mark, kinds) => {
    const run = edgeMetres(kinds);
    if (!run) return;
    // Two faces, `edge_bars` on each, lapped every stock length, plus a lap
    // at each corner.
    const corners = runsOf(kinds).length;
    const pieces = Math.ceil(run / STOCK_LENGTH_MM) + corners;
    const total = run + pieces * lapLength(s.edge_bar_dia);
    row({
      mark, family: 'edge', dia: s.edge_bar_dia, shape: 'straight',
      count: 2 * s.edge_bars, length: Math.round(total),
    });
  };

  row({ mark: 'U1', family: 'ubar', dia: uDia, shape: 'u', count: uCount(['perimeter']), length: uLength, leg: uLeg, width: uWidth, spacing: s.ubar_spacing });
  edgeBarRow('E1', ['perimeter']);
  if (cores.length) {
    row({ mark: 'U2', family: 'ubar', dia: uDia, shape: 'u', count: uCount(['core']), length: uLength, leg: uLeg, width: uWidth, spacing: s.ubar_spacing });
    edgeBarRow('E2', ['core']);
    row({ mark: 'D1', family: 'diagonal', dia: diagDia, shape: 'straight', count: coreDiagonals, length: diagLength });
  }
  if (runsOf(['opening']).length) {
    row({ mark: 'U3', family: 'ubar', dia: uDia, shape: 'u', count: uCount(['opening']), length: uLength, leg: uLeg, width: uWidth, spacing: s.ubar_spacing });
    edgeBarRow('E3', ['opening']);
  }

  // Trimmers: each opening two sides per direction, top of the mesh layer.
  const trimGroups = new Map();
  for (const op of openingDetails) {
    if (op.small) continue;
    for (const t of op.trimmers) {
      const key = `${t.dia}|${t.length}|${t.count}`;
      if (!trimGroups.has(key)) {
        trimGroups.set(key, { mark: `R${trimGroups.size + 1}`, dia: t.dia, length: t.length, per_side: t.count, sides: 0 });
      }
      const g = trimGroups.get(key);
      g.sides += 2;
      t.mark = g.mark;
    }
  }
  for (const g of trimGroups.values()) {
    row({ mark: g.mark, family: 'trimmer', dia: g.dia, shape: 'straight', count: g.per_side * g.sides, length: g.length });
  }
  const openingDiagonals = openingDetails.filter((o) => !o.small).length * 8;
  if (openingDiagonals) {
    row({ mark: 'D2', family: 'diagonal', dia: diagDia, shape: 'straight', count: openingDiagonals, length: diagLength });
  }

  // ---------------------------------------------------------------- totals
  const byFamily = {};
  for (const r of schedule) byFamily[r.family] = round2((byFamily[r.family] || 0) + r.weight_kg);
  const totalKg = round2(schedule.reduce((sum, r) => sum + r.weight_kg, 0));
  const volume = netArea * (h / 1000);

  if (spansX.some((l) => l / h > 45) || spansY.some((l) => l / h > 45)) {
    warn(`A span is more than 45 times the slab thickness (${h} mm): check deflection and the balanced load.`,
      `فيه بحر أكبر من 45 مرة سمك البلاطة (${h} مم): راجع السهم ونسبة الحمل المتوازن.`);
  }

  return {
    input: s,
    slab: {
      width: W, height: H, thickness: h, cover,
      gross_area_sqm: round2(grossArea), net_area_sqm: round2(netArea),
      volume_m3: round2(volume),
    },
    grid: {
      x: gridX.map((pos, i) => ({ name: gridNameX(i), pos })),
      y: gridY.map((pos, j) => ({ name: gridNameY(j), pos })),
    },
    columns,
    cores,
    openings: openingDetails,
    mesh: {
      dia: mesh.dia, spacing: mesh.spacing,
      required: Math.round(meshRequired), provided: Math.round(mesh.provided),
      max_spacing: meshMaxSpacing,
    },
    top: {
      bars: topBars,
      marks: [...topMarks.values()],
    },
    ubar: { dia: uDia, spacing: s.ubar_spacing, leg: uLeg, width: uWidth, length: uLength, runs: edgeRuns },
    edge_bars: { dia: s.edge_bar_dia, per_face: s.edge_bars },
    diagonal: { dia: diagDia, length: diagLength },
    schedule,
    totals: {
      weight_kg: totalKg,
      weight_ton: round2(totalKg / 1000),
      kg_sqm: netArea ? round2(totalKg / netArea) : 0,
      kg_m3: volume ? round2(totalKg / volume) : 0,
      by_family: byFamily,
    },
    warnings,
  };
}
