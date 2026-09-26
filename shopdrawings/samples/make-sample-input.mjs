/**
 * Builds a sample "combined structural drawing" DXF, the kind of file the
 * consultant hands over: two slab plans side by side with grid, columns,
 * slab outlines, PT zone, openings, voids, U-bar regions and general notes.
 *
 *   node shopdrawings/samples/make-sample-input.mjs
 *
 * The geometry is invented for the demo; the point is that it uses ordinary
 * layer names, blocks and notes the extractor has to cope with.
 */
import { writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { Canvas } from '../lib/canvas.mjs';
import { toDxf } from '../lib/dxf-writer.mjs';

const here = dirname(fileURLToPath(import.meta.url));

export function buildSampleInput() {
  const c = new Canvas();
  c.layer('S-GRID', { color: 8, ltype: 'CENTER' });
  c.layer('S-COLS', { color: 5 });
  c.layer('S-COLS-HATCH', { color: 8 });
  c.layer('S-SLAB-EDGE', { color: 4, lw: 35 });
  c.layer('S-PT-ZONE', { color: 4, ltype: 'DASHDOT' });
  c.layer('S-OPENINGS', { color: 6 });
  c.layer('S-VOIDS', { color: 30, ltype: 'DASHED' });
  c.layer('S-UBAR', { color: 6 });
  c.layer('S-TEXT', { color: 7 });
  c.layer('S-NOTES', { color: 7 });

  // A column block, the way most offices draw it.
  const col = c.block('COL600');
  col.rect(-300, -300, 600, 600, { layer: 'S-COLS' });
  col.hatch([[{ x: -300, y: -300 }, { x: 300, y: -300 }, { x: 300, y: 300 }, { x: -300, y: 300 }]], { layer: 'S-COLS-HATCH', pattern: 'ANSI31', scale: 25 });

  const gx = [0, 7500, 15000, 22500, 30000];
  const gy = [0, 8000, 16000, 24000];
  const xl = ['A', 'B', 'C', 'D', 'E'];
  const yl = ['1', '2', '3', '4'];

  const drawPlan = (ox, oy, title, cfg) => {
    // grid
    gx.forEach((x, i) => {
      c.line(ox + x, oy - 2500, ox + x, oy + 24000 + 2500, { layer: 'S-GRID' });
      c.circle(ox + x, oy + 24000 + 3500, 700, { layer: 'S-GRID' });
      c.text(ox + x, oy + 24000 + 3500, xl[i], { layer: 'S-TEXT', h: 600, align: 'C', valign: 'M' });
    });
    gy.forEach((y, i) => {
      c.line(ox - 2500, oy + y, ox + 30000 + 2500, oy + y, { layer: 'S-GRID' });
      c.circle(ox - 3500, oy + y, 700, { layer: 'S-GRID' });
      c.text(ox - 3500, oy + y, yl[i], { layer: 'S-TEXT', h: 600, align: 'C', valign: 'M' });
    });
    // slab outline with a notch at the top-right corner and a cantilever on the left
    const outline = cfg.outline.map((p) => ({ x: ox + p.x, y: oy + p.y }));
    c.pline(outline, { layer: 'S-SLAB-EDGE', closed: true });
    // columns
    for (const x of gx) for (const y of gy) {
      if (cfg.skip.some(([sx, sy]) => sx === x && sy === y)) continue;
      c.insert('COL600', ox + x, oy + y);
    }
    // a circular column at the cantilever
    if (cfg.roundCol) c.circle(ox + cfg.roundCol.x, oy + cfg.roundCol.y, 350, { layer: 'S-COLS' });
    // PT zone
    c.pline(cfg.pt.map((p) => ({ x: ox + p.x, y: oy + p.y })), { layer: 'S-PT-ZONE', closed: true });
    // openings
    for (const o of cfg.openings) {
      c.rect(ox + o.x, oy + o.y, o.w, o.h, { layer: 'S-OPENINGS' });
      c.line(ox + o.x, oy + o.y, ox + o.x + o.w, oy + o.y + o.h, { layer: 'S-OPENINGS' });
      c.line(ox + o.x + o.w, oy + o.y, ox + o.x, oy + o.y + o.h, { layer: 'S-OPENINGS' });
      c.text(ox + o.x + o.w / 2, oy + o.y + o.h / 2 + 400, o.label, { layer: 'S-TEXT', h: 300, align: 'C' });
    }
    // voids
    for (const v of cfg.voids) {
      c.rect(ox + v.x, oy + v.y, v.w, v.h, { layer: 'S-VOIDS' });
      c.text(ox + v.x + v.w / 2, oy + v.y + v.h / 2, 'VOID', { layer: 'S-TEXT', h: 300, align: 'C', valign: 'M' });
    }
    // U-bar circular regions
    for (const u of cfg.ubars) {
      c.circle(ox + u.x, oy + u.y, u.r, { layer: 'S-UBAR' });
      c.text(ox + u.x, oy + u.y + u.r + 300, 'U-BARS', { layer: 'S-TEXT', h: 250, align: 'C' });
    }
    // title
    c.text(ox + 15000, oy - 6000, title, { layer: 'S-TEXT', h: 900, align: 'C' });
    c.text(ox + 15000, oy - 7500, `SCALE 1:100 - SLAB THK ${cfg.thk} mm`, { layer: 'S-TEXT', h: 450, align: 'C' });
  };

  const outlineA = [
    { x: -1500, y: -1000 }, { x: 31000, y: -1000 }, { x: 31000, y: 20000 },
    { x: 26000, y: 20000 }, { x: 26000, y: 25000 }, { x: -1500, y: 25000 },
  ];
  drawPlan(0, 0, 'FIRST FLOOR SLAB PLAN', {
    thk: 250,
    outline: outlineA,
    skip: [[30000, 24000]],
    roundCol: null,
    pt: [{ x: -1500, y: -1000 }, { x: 31000, y: -1000 }, { x: 31000, y: 20000 }, { x: 26000, y: 20000 }, { x: 26000, y: 25000 }, { x: -1500, y: 25000 }],
    openings: [
      { x: 9500, y: 9500, w: 3000, h: 5000, label: 'STAIR OPENING' },
      { x: 17500, y: 3000, w: 1800, h: 1500, label: 'SHAFT' },
    ],
    voids: [
      { x: 2000, y: 2000, w: 4000, h: 3000 },
      { x: 17000, y: 18000, w: 5000, h: 3500 },
    ],
    ubars: [{ x: 3750, y: 20000, r: 1000 }],
  });

  const outlineB = [
    { x: -1500, y: -1000 }, { x: 31000, y: -1000 }, { x: 31000, y: 25000 }, { x: -1500, y: 25000 },
  ];
  drawPlan(45000, 0, 'ROOF SLAB PLAN', {
    thk: 220,
    outline: outlineB,
    skip: [],
    roundCol: null,
    pt: [{ x: -1500, y: -1000 }, { x: 31000, y: -1000 }, { x: 31000, y: 25000 }, { x: -1500, y: 25000 }],
    openings: [
      { x: 9500, y: 9500, w: 3000, h: 5000, label: 'STAIR OPENING' },
      { x: 24000, y: 10000, w: 2500, h: 2500, label: 'MECH. OPENING' },
    ],
    voids: [
      { x: 2000, y: 17000, w: 4000, h: 3000 },
    ],
    ubars: [{ x: 26000, y: 4000, r: 1200 }, { x: 4000, y: 4000, r: 900 }],
  });

  // General notes block
  const notes = [
    'GENERAL NOTES',
    '1. DESIGN CODE: SBC 304-18 (SAUDI BUILDING CODE).',
    "2. CONCRETE: f'c = 35 MPa FOR ALL SLABS.",
    '3. REINFORCEMENT: DEFORMED BARS fy = 420 MPa.',
    '4. CLEAR COVER TO SLAB REINFORCEMENT = 25 mm.',
    '5. TOP BARS OVER COLUMNS: T16@150 B.W. UNLESS NOTED.',
    '6. PT SLABS: BONDED SYSTEM, TENDON LAYOUT BY PT CONTRACTOR.',
    '7. ALL DIMENSIONS IN MILLIMETRES.',
  ];
  notes.forEach((n, i) => c.text(0, -12000 - i * 800, n, { layer: 'S-NOTES', h: i ? 400 : 600 }));
  return c;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const out = join(here, 'sample-structural-input.dxf');
  writeFileSync(out, toDxf(buildSampleInput(), { ltscale: 100 }));
  console.log('wrote', out);
}
