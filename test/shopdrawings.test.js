/**
 * The reinforcement shop-drawing generator.
 *
 * Lengths here go to a bar bender, so the lap / development arithmetic is
 * pinned to hand calculations from SBC 304-18, and the sample structural
 * drawing has to come back out as the levels, columns and openings that were
 * put into it.
 *
 *   npm test
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, mkdtempSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { parseDxf } from '../shopdrawings/lib/dxf-reader.mjs';
import { toDxf, encodeText } from '../shopdrawings/lib/dxf-writer.mjs';
import { Canvas } from '../shopdrawings/lib/canvas.mjs';
import { extractModel, classifyLayer, readSpecFromText } from '../shopdrawings/lib/extract.mjs';
import { developmentLength, lapLength, hookDevelopmentLength, splitRun, BarList, bottomMesh, topAtColumns, aroundOpenings, punching, mergeTotals, DEFAULT_SPEC } from '../shopdrawings/lib/rebar.mjs';
import { chordsAtY, subtractIntervals, asAxisRect } from '../shopdrawings/lib/geometry.mjs';
import { buildSampleInput } from '../shopdrawings/samples/make-sample-input.mjs';
import { generate } from '../shopdrawings/cli.mjs';

const spec35 = { ...DEFAULT_SPEC, fc: 35, fy: 420 };

test('development and lap lengths follow SBC 304-18 §25.4.2.3 / §25.5.2', () => {
  // Ø12, f'c 35, fy 420: ld = 420 / (2.1·√35) · 12 = 405.7 → 410 (rounded up to 10)
  assert.equal(developmentLength(spec35, 12), 410);
  // top bars ×1.3 = 527.4 → 530
  assert.equal(developmentLength(spec35, 12, { top: true }), 530);
  // Class B lap 1.3·ld = 533 → 550 (rounded up to 50)
  assert.equal(lapLength(spec35, 12), 550);
  // Ø25 uses the 1.7 denominator: 420 / (1.7·√35) · 25 = 1044 → 1050
  assert.equal(developmentLength(spec35, 25), 1050);
  // hook: 0.24·420/√35 · 12 = 204.5 → 210, not less than 8db = 96 or 150
  assert.equal(hookDevelopmentLength(spec35, 12), 210);
  // nothing shorter than 300 mm
  assert.equal(developmentLength({ ...spec35, fc: 60 }, 8), 300);
});

test('runs longer than a stock bar are split with laps, staggered on alternate bars', () => {
  assert.deepEqual(splitRun(9000, { stock: 12000, lap: 550 }), [9000]);
  const a = splitRun(30000, { stock: 12000, lap: 550 });
  assert.deepEqual(a, [12000, 12000, 7100]);
  // each piece overlaps the previous by the lap: 12000 + 12000 + 7100 − 2×550 = 30000
  assert.equal(a.reduce((s, v) => s + v, 0) - 550 * (a.length - 1), 30000);
  const b = splitRun(30000, { stock: 12000, lap: 550, stagger: true });
  assert.equal(b[0], 6000, 'staggered bars start with a half stock');
  assert.equal(b.reduce((s, v) => s + v, 0) - 550 * (b.length - 1), 30000);
});

test('office rule: interior column bars run 4 m (or cover the drop), edge column bars end in a U and run 70 % on top', () => {
  const model = extractModel(parseDxf(toDxf(buildSampleInput())));
  const level = model.levels[1];
  const res = topAtColumns(level, model.spec); // rule: office (default)
  const interior = res.columns.find((c) => c.col.id === 'C/2');
  assert.equal(interior.per.x.length, 4000);
  assert.equal(interior.per.x.shape, 'STR');
  const edge = res.columns.find((c) => c.per.x.hooks[-1] || c.per.x.hooks[1] || c.per.y.hooks[-1] || c.per.y.hooks[1]);
  assert.ok(edge, 'an edge column exists');
  const dir = edge.per.x.hooks[-1] || edge.per.x.hooks[1] ? 'x' : 'y';
  const p = edge.per[dir];
  assert.ok(/U/.test(p.shape), 'U end at the slab edge');
  assert.equal(p.hookLabel, 'U500');
  const uLeg = level.thickness - 2 * model.spec.cover + 500;
  assert.equal(p.hookLeg, uLeg);
  // top straight length from the edge = 70 % of 4 m, but never less than 1.5 m past the inner face of the column
  const edgeSide = p.hooks[-1] ? -1 : 1;
  const straight = p.ext[-1] + p.c1 + p.ext[1];
  const expected = Math.max(2800, p.ext[edgeSide] + p.c1 + 1500);
  assert.equal(straight, expected);
  assert.ok(p.ext[-edgeSide] >= 1500, 'at least 1.5 m past the inner face');
  assert.equal(p.length, Math.ceil((expected + uLeg) / 10) * 10);
  // a drop panel at the column stretches the interior bar over it
  level.thickZones = [{ id: 'D1', polygon: [{ x: interior.col.cx - 2500, y: interior.col.cy - 2000 }, { x: interior.col.cx + 2500, y: interior.col.cy - 2000 }, { x: interior.col.cx + 2500, y: interior.col.cy + 2000 }, { x: interior.col.cx - 2500, y: interior.col.cy + 2000 }], thickness: 300 }];
  const res2 = topAtColumns(level, model.spec);
  assert.equal(res2.columns.find((c) => c.col.id === 'C/2').per.x.length, 5000, 'exactly the 5000 drop panel');
});

test('the bar list merges identical bars into marks and weighs them', () => {
  const bars = new BarList('T2');
  bars.add({ dia: 12, shape: 'STR', length: 12000, qty: 10, zone: 'A', spacing: 200 });
  bars.add({ dia: 12, shape: 'STR', length: 12000, qty: 5, zone: 'B', spacing: 400 });
  bars.add({ dia: 16, shape: 'L', length: 3000, qty: 4, zone: 'C' });
  const rows = bars.rows();
  assert.equal(rows.length, 2, 'same cutting length at two spacings is one mark');
  assert.equal(rows[0].mark, 'T2-01');
  assert.equal(rows[0].spacing, 'VAR.');
  assert.equal(rows[0].qty, 15);
  assert.equal(rows[0].total_m, 180);
  assert.equal(rows[0].weight_kg, Math.round(180 * 0.006165 * 144 * 10) / 10);
  assert.equal(rows[0].zones, 'A, B');
});

test('geometry helpers: chords, interval subtraction, rectangles', () => {
  const L = [{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 5 }, { x: 5, y: 5 }, { x: 5, y: 10 }, { x: 0, y: 10 }];
  assert.deepEqual(chordsAtY(L, 2), [[0, 10]]);
  assert.deepEqual(chordsAtY(L, 7), [[0, 5]]);
  assert.deepEqual(subtractIntervals([[0, 100]], [[40, 60]]), [[0, 40], [60, 100]]);
  assert.deepEqual(asAxisRect([{ x: 1, y: 1 }, { x: 4, y: 1 }, { x: 4, y: 3 }, { x: 1, y: 3 }]), { x: 1, y: 1, w: 3, h: 2 });
  assert.equal(asAxisRect([{ x: 0, y: 0 }, { x: 4, y: 1 }, { x: 4, y: 3 }, { x: 1, y: 3 }]), null);
});

test('layer names are classified the way offices actually name them', () => {
  assert.equal(classifyLayer('S-COLS'), 'column');
  assert.equal(classifyLayer('S-COLUMN-HATCH'), 'column');
  assert.equal(classifyLayer('S-SLAB-OPENING'), 'opening');
  assert.equal(classifyLayer('S-GRID'), 'grid');
  assert.equal(classifyLayer('S-PT-ZONE'), 'pt');
  assert.equal(classifyLayer('S-VOIDS'), 'void');
  assert.equal(classifyLayer('S-UBAR'), 'ubar');
  assert.equal(classifyLayer('S-SLAB-EDGE'), 'slab');
  assert.equal(classifyLayer('COLOR-FILL'), 'other');
});

test('design data written in the notes overrides the assumptions', () => {
  const assumptions = [];
  const spec = readSpecFromText("DESIGN CODE: SBC 304-18\nCONCRETE f'c = 40 MPa\nfy = 420 MPa\nCOVER 30 mm\nBOTTOM MESH T10@150 B.W.\nTOP BARS OVER COLUMNS T20@100", assumptions);
  assert.equal(spec.code_reference, 'SBC 304-18');
  assert.equal(spec.fc, 40);
  assert.equal(spec.cover, 30);
  assert.deepEqual(spec.bottom, { dia: 10, spacing: 150 });
  assert.equal(spec.topColumns.dia, 20); assert.equal(spec.topColumns.spacing, 100);
  assert.ok(!assumptions.some((a) => /Bottom mesh not specified/.test(a.text)));
  // and with nothing stated, everything is an explicit assumption
  const bare = [];
  const s2 = readSpecFromText('', bare);
  assert.equal(s2.code_reference, null);
  assert.ok(bare.some((a) => /SBC 304-18/.test(a.text)), 'Saudi code assumption recorded');
  assert.ok(bare.some((a) => /Bottom mesh not specified/.test(a.text)));
});

test('the sample structural drawing comes back as two levels with their elements', () => {
  const dxf = parseDxf(toDxf(buildSampleInput()));
  const model = extractModel(dxf);
  assert.equal(model.levels.length, 2);
  const [l1, l2] = model.levels;
  assert.equal(l1.name, 'FIRST FLOOR SLAB PLAN');
  assert.equal(l1.thickness, 250);
  assert.equal(l2.thickness, 220);
  assert.equal(l1.columns.length, 19, 'one column skipped at the notch');
  assert.equal(l2.columns.length, 20);
  assert.deepEqual(l1.grid.x.map((g) => g.label), ['A', 'B', 'C', 'D', 'E']);
  assert.deepEqual(l1.grid.y.map((g) => g.label), ['1', '2', '3', '4']);
  assert.ok(l1.columns.some((c) => c.id === 'C/2' && c.w === 600));
  assert.equal(l1.openings.length, 2);
  assert.equal(l1.voids.length, 2);
  assert.equal(l1.ubar.circles.length, 1);
  assert.equal(l1.pt.zones.length, 1);
  assert.equal(model.code_reference, 'SBC 304-18');
  assert.equal(model.spec.fc, 35);
  assert.equal(model.spec.topColumns.dia, 16); assert.equal(model.spec.topColumns.spacing, 150);
});

test('top bars over an interior column extend ln/6 each side and satisfy As,min', () => {
  const model = extractModel(parseDxf(toDxf(buildSampleInput())));
  const level = model.levels[1]; // roof: full rectangle, 20 columns
  model.spec.topColumns.rule = 'code';
  const res = topAtColumns(level, model.spec);
  const interior = res.columns.find((c) => c.col.id === 'C/2');
  // clear span 7500 − 600 = 6900 → /6 = 1150; length = 1150 + 600 + 1150 = 2900
  assert.equal(interior.per.x.length, 2900);
  assert.equal(interior.per.x.shape, 'STR');
  // 8000 − 600 = 7400 → 1233 → 1250; 1250·2 + 600 = 3100
  assert.equal(interior.per.y.length, 3100);
  assert.ok(interior.per.x.asProv >= interior.per.x.asReq);
  const edge = res.columns.find((c) => c.col.id === 'A/2');
  assert.equal(edge.per.x.shape, 'U', 'edge column bar ends in the U with the 500 bottom leg at the slab edge');
  assert.equal(edge.per.x.uEnd?.leg ?? res.uEnd.leg, res.uEnd.leg);
  assert.ok(res.checks.every((c) => c.asProv >= c.asReq));
});

test('bottom mesh stops at openings and its weight is in the right range', () => {
  const model = extractModel(parseDxf(toDxf(buildSampleInput())));
  const level = model.levels[0];
  const res = bottomMesh(level, model.spec);
  const xZone = res.zones.find((z) => z.dir === 'X');
  assert.equal(xZone.code, 'B2', 'bars parallel to X are layer 2');
  const rowsThroughStair = xZone.groups.filter((g) => g.runs.length === 2);
  assert.ok(rowsThroughStair.length > 0, 'rows crossing the stair opening are split in two runs');
  assert.ok(res.lists.X.rows()[0].mark.startsWith('B2-'), 'marks carry the layer code');
  const w = mergeTotals(res.lists.X, res.lists.Y).weight_kg;
  // ~820 m² at T12@200 both ways ≈ 8.9 kg/m² plus laps
  assert.ok(w > 6500 && w < 9000, `weight ${w}`);
  const o = aroundOpenings(level, model.spec);
  assert.equal(o.regions.length, 2);
  assert.ok(o.bars.rows().some((r) => r.shape === 'DIAG'));
});

test('the DXF writer produces a file the reader and AutoCAD structure agree on', () => {
  const c = new Canvas();
  const b = c.block('SHEET_X');
  b.rect(0, 0, 100, 50, { layer: 'OUTLINE' });
  b.text(1, 1, 'ملاحظات Ø12', { h: 5 });
  b.hatch([[{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }]], { pattern: 'ANSI31' });
  c.insert('SHEET_X', 0, 0);
  const dxf = toDxf(c);
  assert.ok(dxf.startsWith('0\nSECTION\n2\nHEADER'));
  assert.ok(dxf.trim().endsWith('EOF'));
  assert.equal(encodeText('Ø12 عربي'), '\\U+00D812 \\U+0639\\U+0631\\U+0628\\U+064A');
  const back = parseDxf(dxf);
  assert.deepEqual(back.entities.map((e) => e.type), ['INSERT']);
  const blk = back.blocks.get('SHEET_X');
  assert.deepEqual(blk.entities.map((e) => e.type), ['LWPOLYLINE', 'TEXT', 'HATCH']);
  assert.equal(blk.entities[1].text, 'ملاحظات Ø12');
  // every handle is unique and below HANDSEED
  const lines = dxf.split('\n');
  const handles = [];
  for (let i = 0; i + 1 < lines.length; i += 2) if ((lines[i] === '5' && lines[i - 1] !== '$HANDSEED') || lines[i] === '105') handles.push(parseInt(lines[i + 1], 16));
  assert.equal(new Set(handles).size, handles.length);
  const seed = parseInt(dxf.match(/\$HANDSEED\n5\n([0-9A-F]+)/)[1], 16);
  assert.ok(Math.max(...handles) < seed);
});

test('the generator writes a complete package for the sample drawing', () => {
  const out = mkdtempSync(join(tmpdir(), 'sd-'));
  const { pack, model } = generate({ inputText: toDxf(buildSampleInput()), out, meta: { project: 'TEST' }, svg: true });
  assert.equal(pack.sheets.length, 1 + 2 * 8);
  const names = pack.sheets.map((s) => s.blockName);
  for (const base of ['FRAMING_REBAR_SLAB_PT_BOTTOM', 'FRAMING_REBAR_ADDITIONAL_AT_COLUMNS', 'FRAMING_REBAR_U_BARS_AROUND_REGIONS', 'FRAMING_REBAR_AROUND_VOIDS_ACUARS', 'FRAMING_REBAR_AROUND_OPENINGS', 'CABLES_SCHEDULE_EMPTY_TEMPLATE', 'FRAMING_REBAR_PUNCHING_LINKS']) {
    assert.ok(names.includes(`${base}_L01`) && names.includes(`${base}_L02`), base);
  }
  assert.ok(existsSync(join(out, 'SHOP_DRAWINGS_PACKAGE.dxf')));
  assert.ok(existsSync(join(out, 'REPORT.md')));
  assert.equal(readdirSync(join(out, 'dxf')).length, 17);
  assert.equal(readdirSync(join(out, 'preview')).length, 17);
  const cables = pack.sheets.find((s) => s.key === 'cables');
  assert.ok(cables.rows.every((r) => r.strands === '' && r.length === ''), 'cable schedule stays empty');
  assert.ok(!readdirSync(join(out, 'schedules')).some((f) => /CABLES/.test(f)), 'no CSV for the empty cable template');
  for (const f of readdirSync(join(out, 'preview'))) assert.ok(!/NaN/.test(readFileSync(join(out, 'preview', f), 'utf8')), `${f} has NaN`);
  const pkg = readFileSync(join(out, 'SHOP_DRAWINGS_PACKAGE.dxf'), 'utf8');
  for (const n of names) assert.ok(pkg.includes(`\n2\n${n}\n`), `${n} defined in the package`);
  assert.ok(model.assumptions.length >= 4);
  // layers follow the Span Tech standard, not the generator's internal names
  const layerNames = [...pkg.matchAll(/\nLAYER\n5\n[0-9A-F]+\n330\n[0-9A-F]+\n100\nAcDbSymbolTableRecord\n100\nAcDbLayerTableRecord\n2\n([^\n]+)\n/g)].map((m) => m[1]);
  assert.ok(layerNames.includes('SPAN-RB-T1') && layerNames.includes('SPAN-RB-B2') && layerNames.includes('SPAN-SLAB-EDGE') && layerNames.includes('SPAN-SHEET-TITLE'), layerNames.join(','));
  assert.ok(!layerNames.some((n) => /^REBAR|^COLUMN|BBR/.test(n)), 'no internal or BBR layer names remain');
  assert.ok(/\n2\nSPAN-REBAR\n70\n0\n/.test(pkg) && pkg.includes('romans.shx'), 'rebar text style present');
  assert.ok(!/\n8\nREBAR-T1\n/.test(pkg), 'entities were renamed too');
});

test('punching links follow the minimum detailing arrangement of the reference drawings', () => {
  const model = extractModel(parseDxf(toDxf(buildSampleInput())));
  const level = model.levels[0]; // 250 mm slab
  const res = punching(level, model.spec);
  // d = 250 - 25 - 16 = 209 → d/2 = 104.5 → rows at 100; extent 2h = 500 → 5 rows
  assert.equal(res.rowSpacing, 100);
  assert.equal(res.rows, 5);
  const interior = res.columns.find((c) => c.col.id === 'C/2');
  assert.equal(interior.sides.length, 4, 'interior column has links on all four faces');
  // 600 face at 100 leg spacing → 7 links per row
  assert.ok(interior.sides.every((s) => s.links === 7 && s.nRows === 5));
  assert.ok(interior.type.label.includes('5X7-T10-100'));
  assert.ok(res.bars.rows()[0].mark.startsWith('PS-'));
  // a column flush with the slab edge: no links on the faces at the edge
  const edgeLevel = { thickness: 250, outline: [{ x: 0, y: 0 }, { x: 10000, y: 0 }, { x: 10000, y: 10000 }, { x: 0, y: 10000 }], columns: [{ id: 'E1', shape: 'rect', cx: 300, cy: 300, w: 600, h: 600 }] };
  const edge = punching(edgeLevel, model.spec);
  assert.equal(edge.columns[0].sides.length, 2, 'corner column: faces at the slab edge carry no links');
});

// ---------------------------------------------------------------- RAM Concept input

/** A tiny RAM Concept model written with node:sqlite: 12 x 8 m slab meshed 3 x 2, five columns, one wall crossing the edge, two tendons, two bands. */
async function buildSyntheticCpt(dir) {
  const { DatabaseSync } = await import('node:sqlite');
  const path = join(dir, 'synthetic.cpt');
  const db = new DatabaseSync(path);
  const P = (x, y) => `[${x * 10}][${y * 10}]`; // mm → 0.1 mm
  const create = (t, cols) => db.exec(`create table "${t}" (${cols.map((c) => `"${c}"`).join(',')})`);
  const insert = (t, rowsToAdd) => { for (const r of rowsToAdd) db.prepare(`insert into "${t}" (${Object.keys(r).map((k) => `"${k}"`).join(',')}) values (${Object.keys(r).map(() => '?').join(',')})`).run(...Object.values(r)); };
  create('Cover', ['Heading1', 'Heading2', 'Heading3', 'Heading4']); insert('Cover', [{ Heading1: 'SPAN TECH', Heading2: 'SYNTHETIC SLAB', Heading3: 'PART 1', Heading4: 'R0' }]);
  create('Concrete', ['UID', 'Name', 'FcFinal', 'FcuFinal']); insert('Concrete', [{ UID: 1, Name: 'C32/40', FcFinal: 0.32, FcuFinal: 0.4 }]);
  create('Rebar', ['UID', 'Name', 'Fy', 'As']); insert('Rebar', [{ UID: 11, Name: 'T12', Fy: 4.2, As: 11300 }, { UID: 16, Name: 'T16', Fy: 4.2, As: 20100 }]);
  create('SlabArea', ['UID', 'MultiPoint', 'SlabThickness', 'Priority', 'SlabBehavior', 'TOC']);
  insert('SlabArea', [
    { UID: 21, MultiPoint: `${P(0, 0)}${P(12000, 0)}${P(12000, 8000)}${P(0, 8000)}`, SlabThickness: 2500, Priority: 1, SlabBehavior: 0, TOC: 0 },
    { UID: 22, MultiPoint: `${P(4000, 0)}${P(8000, 0)}${P(8000, 4000)}${P(4000, 4000)}`, SlabThickness: 4000, Priority: 2, SlabBehavior: 0, TOC: 0 },
  ]);
  create('ElementCornerNode', ['UID', 'Point0']);
  create('QuadSlabElement', ['UID', 'CornerNode0', 'CornerNode1', 'CornerNode2', 'CornerNode3', 'SlabThickness']);
  const xs = [0, 4000, 8000, 12000], ys = [0, 4000, 8000];
  const nodes = []; for (const y of ys) for (const x of xs) nodes.push(P(x, y));
  insert('ElementCornerNode', nodes.map((p, i) => ({ UID: 100 + i, Point0: p })));
  const quads = [];
  for (let j = 0; j < 2; j++) for (let i = 0; i < 3; i++) quads.push({ UID: 200 + quads.length, CornerNode0: P(xs[i], ys[j]), CornerNode1: P(xs[i + 1], ys[j]), CornerNode2: P(xs[i + 1], ys[j + 1]), CornerNode3: P(xs[i], ys[j + 1]), SlabThickness: i === 1 && j === 0 ? 4000 : 2500 });
  insert('QuadSlabElement', quads);
  create('Column', ['UID', 'Point0', 'B', 'D', 'Angle', 'SupportSet']);
  insert('Column', [
    { UID: 31, Point0: P(0, 0), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' }, { UID: 32, Point0: P(12000, 0), B: 4000, D: 8000, Angle: Math.PI / 2, SupportSet: 'below' }, // the second one turned 90°
    { UID: 33, Point0: P(0, 8000), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' }, { UID: 34, Point0: P(12000, 8000), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' },
    { UID: 35, Point0: P(6000, 4000), B: 0, D: 6000, Angle: 0, SupportSet: 'below' },
  ]);
  create('LineSupport', ['UID', 'Point0', 'Point1']); insert('LineSupport', [{ UID: 41, Point0: P(-3000, 2000), Point1: P(5000, 2000) }]);
  create('TendonLayer', ['UID', 'SpanSet']); insert('TendonLayer', [{ UID: 51, SpanSet: 'latitude' }, { UID: 52, SpanSet: 'longitude' }]);
  create('TendonLevel', ['UID', 'ParentUID']); insert('TendonLevel', [{ UID: 61, ParentUID: 51 }, { UID: 62, ParentUID: 52 }]);
  create('TendonCategory', ['UID', 'ParentUID']); insert('TendonCategory', [{ UID: 71, ParentUID: 61 }, { UID: 72, ParentUID: 62 }]);
  create('Tendon', ['UID', 'ParentUID', 'TendonNode0', 'TendonNode1', 'NumStrands', 'Harped']);
  insert('Tendon', [
    { UID: 81, ParentUID: 71, TendonNode0: P(0, 2000), TendonNode1: P(6000, 2000), NumStrands: 4, Harped: 0 }, { UID: 82, ParentUID: 71, TendonNode0: P(6000, 2000), TendonNode1: P(12000, 2000), NumStrands: 4, Harped: 0 },
    { UID: 83, ParentUID: 72, TendonNode0: P(3000, 0), TendonNode1: P(3000, 8000), NumStrands: 3, Harped: 0 },
  ]);
  create('Jack', ['UID', 'TendonNode0', 'JackStress', 'Elongation']); insert('Jack', [{ UID: 91, TendonNode0: P(0, 2000), JackStress: 14.88, Elongation: 850 }]);
  create('StrandMaterial', ['UID', 'Aps', 'Fpu']); insert('StrandMaterial', [{ UID: 1, Aps: 9870, Fpu: 18.6 }]);
  create('ConcentratedRebar', ['UID', 'ParentUID', 'BarFace', 'SpanDirection', 'BarType', 'BarCount', 'BarSpacing', 'Point0', 'Point1', 'LeftPoint', 'RightPoint', 'BarEnd0', 'BarEnd1', 'AbsoluteElevation']);
  insert('ConcentratedRebar', [
    { UID: 301, ParentUID: 1, BarFace: 2, SpanDirection: 1, BarType: 11, BarCount: 5, BarSpacing: 2000, Point0: P(0, 4000), Point1: P(12000, 4000), LeftPoint: P(6000, 3600), RightPoint: P(6000, 4400), BarEnd0: 0, BarEnd1: 0, AbsoluteElevation: -2000 },
    { UID: 302, ParentUID: 1, BarFace: 1, SpanDirection: 2, BarType: 16, BarCount: 6, BarSpacing: 1500, Point0: P(6000, 1500), Point1: P(6000, 6500), LeftPoint: P(5250, 4000), RightPoint: P(6750, 4000), BarEnd0: 0, BarEnd1: 0, AbsoluteElevation: -400 },
  ]);
  create('IndividualBars', ['UID', 'BarFace', 'SpanDirection', 'Point0', 'Point1', 'AbsoluteElevation']);
  const ys5 = [3600, 3800, 4000, 4200, 4400];
  insert('IndividualBars', [{ UID: 401, BarFace: 2, SpanDirection: 1, Point0: ys5.map((y) => P(0, y)).join(''), Point1: ys5.map((y) => P(12000, y)).join(''), AbsoluteElevation: -2000 }]);
  create('TransverseRebarRegion', ['UID', 'Point0', 'Point1', 'BarType', 'StirrupLegs', 'StirrupSpacing']);
  insert('TransverseRebarRegion', [{ UID: 501, Point0: P(4000, 4000), Point1: P(8000, 4000), BarType: 11, StirrupLegs: 2, StirrupSpacing: 1500 }]);
  // stud rails designed by RAM at the middle column: 4 rails of 10 studs @100 leaving every face
  create('SsrSystem', ['UID', 'Name', 'StudArea']); insert('SsrSystem', [{ UID: 14, Name: '10mm SSR', StudArea: 7850 }]);
  create('SsrSet', ['UID', 'Point0', 'Point1', 'DesignedBy', 'SsrSystem', 'StudSpacingFirst', 'StudSpacingTypical', 'StudCount', 'LocationPoint']);
  const rails0 = [], rails1 = [];
  for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) for (let k = 0; k < 4; k++) { const t = -150 + k * 100; const a = { x: 6000 + dx * 300 + (dx ? 0 : t), y: 4000 + dy * 300 + (dy ? 0 : t) }; rails0.push(P(a.x, a.y)); rails1.push(P(a.x + dx * 1000, a.y + dy * 1000)); }
  insert('SsrSet', [{ UID: 701, Point0: rails0.join(''), Point1: rails1.join(''), DesignedBy: 2, SsrSystem: 14, StudSpacingFirst: 1000, StudSpacingTypical: 1000, StudCount: rails0.map(() => '[10]').join(''), LocationPoint: P(6000, 4000) }]);
  create('PunchCheck', ['UID', 'Name', 'Point0', 'SsrSystem', 'CoverToCGS', 'TopCover', 'BottomCover']);
  insert('PunchCheck', [{ UID: 601, Name: 'PC1', Point0: P(6000, 4000), SsrSystem: 'SSR', CoverToCGS: 350, TopCover: 350, BottomCover: 250 }]);
  db.close();
  return path;
}

test('a RAM Concept file is read into a level with its bands, tendons and walls clipped to the slab', async () => {
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'ram-'));
  const ram = readRamConcept(await buildSyntheticCpt(dir));
  assert.equal(ram.project.name, 'SYNTHETIC SLAB');
  assert.equal(ram.materials.fc, 32);
  assert.equal(ram.materials.fy, 420);
  assert.equal(ram.materials.coverTop, 35);
  assert.equal(ram.slab.baseThickness, 250);
  assert.equal(ram.slab.outline.length, 4, 'mesh boundary chained into the slab outline');
  assert.equal(ram.columns.length, 5);
  assert.equal(ram.columns[4].shape, 'circle');
  assert.equal(ram.columns[4].d, 600);
  assert.equal(ram.tendons.length, 2, 'tendon segments chained node to node');
  const lat = ram.tendons.find((t) => t.spanSet === 'latitude');
  assert.equal(lat.strands, 4);
  assert.equal(lat.length, 12000);
  assert.deepEqual(lat.live, [true, false]);
  assert.equal(lat.jackStress, 1488);
  assert.equal(lat.jackForce, Math.round((1488 * 98.7 * 4) / 1000));
  assert.equal(ram.bands.length, 2);
  const bottom = ram.bands.find((b) => b.face === 'B');
  assert.equal(bottom.dia, 12);
  assert.equal(bottom.count, 5);
  assert.equal(bottom.spacing, 200);
  assert.ok(bottom.matched, 'individual bars were matched to the band');
  assert.equal(bottom.bars.length, 5);
  assert.equal(bottom.length, 12000);
  const top = ram.bands.find((b) => b.face === 'T');
  assert.equal(top.dia, 16);
  assert.equal(top.bars.length, 6, 'bars synthesised from the band width when RAM stores no individual bars');
  assert.equal(ram.shear[0].spacing, 150);

  const model = ramToModel(ram, { levelName: 'TEST' });
  assert.equal(model.levels.length, 1);
  const level = model.levels[0];
  assert.equal(level.thickness, 250, 'dominant thickness by mesh element area');
  assert.equal(level.thickZones.length, 1);
  assert.equal(level.thickZones[0].thickness, 400);
  assert.equal(level.walls.length, 1);
  assert.ok(level.walls[0].a.x >= -1 && level.walls[0].b.x <= 5001, 'wall clipped to the slab outline');
  assert.equal(level.grid.x.length, 3);
  assert.equal(level.grid.y.length, 3);
  assert.equal(level.ram.bands.length, 2);
  assert.equal(level.ram.tendons.length, 2);
  assert.ok(model.assumptions.some((a) => /RAM Concept/.test(a.text)));

  const { composePackage } = await import('../shopdrawings/lib/sheets.mjs');
  const pkg = composePackage(model, { project: 'SYNTHETIC', prefix: 'T', company: 'SPAN TECH' });
  assert.equal(pkg.sheets.length, 11, '8 standard sheets + 2 RAM additional sheets + cover');
  assert.ok(pkg.sheets.find((s) => s.key === 'bottom').rows.some((r) => r.mark.startsWith('B1-') || r.mark.startsWith('B2-')), 'standard bottom mesh drawn on the RAM slab too');
  assert.ok(pkg.sheets.find((s) => s.key === 'top').rows.some((r) => r.mark.startsWith('T1-') || r.mark.startsWith('T2-')), 'standard top bars over columns drawn on the RAM slab too');
  const addb = pkg.sheets.find((s) => s.key === 'addbottom');
  assert.ok(addb.rows.length && addb.rows.every((r) => /^ADD\.B[12]-\d\d$/.test(r.mark)), addb.rows.map((r) => r.mark).join(','));
  assert.ok(pkg.sheets.find((s) => s.key === 'addtop').rows.every((r) => /^ADD\.T[12]-\d\d$/.test(r.mark)));
  const cables = pkg.sheets.find((s) => s.key === 'cables');
  assert.ok(cables.rows.length >= 2, 'cables schedule filled from the RAM tendons');
});

test('walls, drop panels, pour strips and stepped zones are read from their layers', () => {
  // a 30 x 20 m slab: perimeter wall along the top edge, four columns with drop panels, a pour strip,
  // a nested slab zone drawn on the slab layer with its own level tag
  const c = new Canvas();
  const rect = (x, y, w, h, layer) => c.pline([{ x, y }, { x: x + w, y }, { x: x + w, y: y + h }, { x, y: y + h }], { layer, closed: true });
  rect(0, 0, 30000, 20000, '0-slab');
  rect(0, 0, 6000, 20000, '0-slab'); // stepped zone
  rect(0, 19650, 30000, 350, '0-walls');
  for (const [x, y] of [[10000, 5000], [20000, 5000], [10000, 15000], [20000, 15000]]) { rect(x - 300, y - 300, 600, 600, '0-columns'); rect(x - 1250, y - 1500, 2500, 3000, '0-drops'); }
  rect(14500, 0, 1000, 20000, '0-pour strip');
  c.text(15000, 10000, 'T.O.S', { layer: 'A-TEXT', h: 200 }); c.text(15000, 9700, '+0.60', { layer: 'A-TEXT', h: 200 });
  c.text(3000, 10000, 'T.O.S', { layer: 'A-TEXT', h: 200 }); c.text(3000, 9700, '+0.50', { layer: 'A-TEXT', h: 200 });
  const dxf = parseDxf(toDxf(c));
  // texts are plain TEXT here; the level tags come from block attributes in real drawings, so feed them as ATTRIB
  for (const e of dxf.entities) if (e.type === 'TEXT' && e.layer === 'A-TEXT') e.type = 'ATTRIB';
  const model = extractModel(dxf, {});
  const L = model.levels[0];
  assert.equal(model.levels.length, 1, 'the nested zone is not a second level');
  assert.equal(L.walls.length, 1);
  assert.ok(L.walls[0].polygon && Math.round(L.walls[0].t) === 350 && Math.round(L.walls[0].length) === 30000);
  assert.equal(L.thickZones.length, 4);
  assert.equal(L.thickZones[0].kind, 'drop');
  assert.equal(L.thickZones[0].thickness, null);
  assert.equal(L.pourStrips.length, 1);
  assert.equal(Math.round(L.pourStrips[0].width), 1000);
  assert.equal(L.tos, '+0.60');
  assert.equal(L.sunken.length, 1);
  assert.equal(L.sunken[0].step, -100, 'the zone at +0.50 is a 100 mm step down from the main +0.60');
  assert.equal(L.columns.length, 4, 'walls and drops are not columns');
  assert.equal(L.grid.x.length, 2);
  assert.equal(L.grid.y.length, 2);
  // top bars run over the wall too, punching links do not
  const top = topAtColumns(L, model.spec);
  assert.ok(top.columns.some((r) => r.col.isWall), 'wall support in the top-bar set');
  const wallRow = top.columns.find((r) => r.col.isWall);
  assert.ok(wallRow.per.y.n > 100 && wallRow.per.y.length < 4000, `bars across the wall: ${wallRow.per.y.n} x ${wallRow.per.y.length}`);
  assert.ok(wallRow.per.x.n <= 12, `bars along the wall are not inflated by the column As,min rule: ${wallRow.per.x.n}`);
  const pun = punching(L, model.spec);
  assert.equal(pun.columns.length, 4);
});

test('HATCH records carry no pixel-size group, which AutoCAD rejects on non-derived boundaries', () => {
  const c = new Canvas();
  c.hatch([[{ x: 0, y: 0 }, { x: 1000, y: 0 }, { x: 1000, y: 350 }, { x: 0, y: 350 }]], { layer: 'W', pattern: 'ANSI31', spacing: 1.2 });
  c.hatch([[{ x: 0, y: 0 }, { x: 600, y: 0 }, { x: 600, y: 600 }, { x: 0, y: 600 }]], { layer: 'C', pattern: 'SOLID' });
  const txt = toDxf(c);
  // walk the file as (code, value) pairs and collect the codes of each HATCH entity
  const lines = txt.split('\n');
  const hatches = [];
  for (let i = 0; i + 1 < lines.length; i += 2) {
    if (lines[i].trim() === '0' && lines[i + 1].trim() === 'HATCH') {
      const codes = [];
      for (let j = i + 2; j + 1 < lines.length && lines[j].trim() !== '0'; j += 2) codes.push(lines[j].trim());
      hatches.push(codes);
    }
  }
  assert.equal(hatches.length, 2);
  for (const codes of hatches) {
    assert.ok(!codes.includes('47'), 'no group 47');
    // pattern data (78 ...) or the style groups (75, 76) are followed directly by the seed count
    const i98 = codes.lastIndexOf('98');
    assert.ok(i98 > 0 && ['79', '76', '49'].includes(codes[i98 - 1]), `98 follows the pattern lines / style groups, got ${codes[i98 - 1]}`);
  }
});

// ---------------------------------------------------------------- design drawings (office convention)
import { extractDesign, designAdditions, composeDesignPackage, clipAtOpenings, VOID_TABLE } from '../shopdrawings/lib/design.mjs';

/** A small office-style design plan: RC slab outline, columns, a U core wall, an edge beam, a void, a 280 zone and the designer's own top bars. */
function buildOfficePlan() {
  const c = new Canvas();
  c.pline([{ x: 0, y: 0 }, { x: 16000, y: 0 }, { x: 16000, y: 12000 }, { x: 10000, y: 12000 }, { x: 10000, y: 9000 }, { x: 0, y: 9000 }], { layer: 'S-RC slab', closed: true });
  // thickened zone 280 as a nested outline with its thickness written inside
  c.pline([{ x: 1000, y: 1000 }, { x: 6000, y: 1000 }, { x: 6000, y: 4000 }, { x: 1000, y: 4000 }], { layer: 'S-RC slab', closed: true });
  c.text(3500, 2500, '280', { layer: 'S-Slab Thick', h: 200 });
  c.text(8000, 8000, 'RC230', { layer: 'TXT', h: 200 });
  c.text(7000, 6000, 'MESH T10@150', { layer: '9_TEXT', h: 200 }); c.text(7000, 5700, 'BOTTOM&TOP TWO WAY', { layer: '9_TEXT', h: 200 });
  c.mtext(2000, 9600, 'CAMBER 1 CM', { layer: 'TEXT-4', h: 200 });
  c.text(12000, 11000, 'T.O.C', { layer: 'TEXT-4', h: 188 }); c.text(12000, 11300, '+12.35', { layer: 'TEXT-4', h: 188 });
  // columns and a U-shaped core wall on the column layer
  const col = c.block('COLUMN'); col.rect(-150, -350, 300, 700, { layer: 'STR-COLS', closed: true }); col.hatch([[{ x: -150, y: -350 }, { x: 150, y: -350 }, { x: 150, y: 350 }, { x: -150, y: 350 }]], { layer: 's-hatch', pattern: 'SOLID' });
  for (const [x, y] of [[2000, 2000], [8000, 2000], [14000, 2000], [2000, 7000], [8000, 7000], [14000, 7000]]) c.insert('COLUMN', x, y);
  c.pline([{ x: 11000, y: 4000 }, { x: 13500, y: 4000 }, { x: 13500, y: 6500 }, { x: 13200, y: 6500 }, { x: 13200, y: 4300 }, { x: 11300, y: 4300 }, { x: 11300, y: 6500 }, { x: 11000, y: 6500 }], { layer: 'STR-COLS', closed: true });
  // edge beam along the bottom edge (a 250 wide line pair)
  c.line(0, 0, 16000, 0, { layer: 'S-BEAM' }); c.line(0, 250, 16000, 250, { layer: 'S-BEAM' });
  // an MEP void 1.2 x 0.8 m, crossed
  c.pline([{ x: 6500, y: 6500 }, { x: 7700, y: 6500 }, { x: 7700, y: 7300 }, { x: 6500, y: 7300 }], { layer: 'S-OPENING', closed: true });
  c.line(6500, 6500, 7700, 7300, { layer: 'S-OPENING' }); c.line(7700, 6500, 6500, 7300, { layer: 'S-OPENING' });
  // a second void 500 mm above it with nothing between them: the strip carries blockwork (detail 9)
  c.pline([{ x: 6500, y: 7800 }, { x: 7700, y: 7800 }, { x: 7700, y: 8600 }, { x: 6500, y: 8600 }], { layer: 'S-OPENING', closed: true });
  c.line(6500, 7800, 7700, 8600, { layer: 'S-OPENING' }); c.line(7700, 7800, 6500, 8600, { layer: 'S-OPENING' });
  // the designer's own top bars over a column, in a block like the office's "TOP REN" blocks
  const ren = c.block('TOP REN');
  ren.line(6800, 2000, 9200, 2000, { layer: 'REO-TOP' });
  ren.text(7500, 2054, 'T10-300 (T)', { layer: 'REO-TXT', h: 150, style: 'BW' }); ren.text(7700, 1817, 'L=2400', { layer: 'REO-TXT', h: 150, style: 'BW' });
  ren.line(8000, 100, 8000, 3200, { layer: 'REO-TOP' }); // reaches the slab edge → gets the U500 end
  ren.text(7950, 1200, 'T10-150 (T)', { layer: 'REO-TXT', h: 150, rot: 90, style: 'BW' }); ren.text(8150, 1200, 'L=2400', { layer: 'REO-TXT', h: 150, rot: 90, style: 'BW' });
  const dot = c.block('DOT'); dot.circle(0, 0, 33, { layer: 'S-CABLE-SYMBOL' });
  ren.insert('DOT', 8000, 3000);
  c.insert('TOP REN', 0, 0);
  // grid: bubbles with labels and lines
  for (const [i, x] of [2000, 8000, 14000].entries()) { c.line(x, -2000, x, 14000, { layer: 'S-GRID' }); c.circle(x, 14600, 400, { layer: 'S-GRID-IDEN' }); c.text(x, 14600, String(i + 1), { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  for (const [i, y] of [2000, 7000].entries()) { c.line(-2000, y, 18000, y, { layer: 'S-GRID' }); c.circle(-2600, y, 400, { layer: 'S-GRID-IDEN' }); c.text(-2600, y, 'AB'[i], { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  return c;
}

test('a DIMENSION entity is read with its measured points, text midpoint, type and measurement', () => {
  const dxfText = ['0', 'SECTION', '2', 'ENTITIES', '0', 'DIMENSION', '8', 'diamension', '2', '*D1', '10', '100', '20', '900', '30', '0', '11', '350', '21', '950', '31', '0', '70', '33', '1', '', '3', 'DIM100', '13', '100', '23', '500', '33', '0', '14', '600', '24', '500', '34', '0', '42', '500', '50', '0', '0', 'ENDSEC', '0', 'EOF'].join('\n');
  const dxf = parseDxf(dxfText);
  const d = dxf.entities.find((e) => e.type === 'DIMENSION');
  assert.ok(d, 'DIMENSION kept');
  assert.equal(d.dimType, 1);
  assert.equal(d.dimstyle, 'DIM100');
  assert.equal(d.measure, 500);
  assert.deepEqual([d.x, d.y, d.x2, d.y2, d.x3, d.y3, d.x4, d.y4], [100, 900, 350, 950, 100, 500, 600, 500]);
  assert.equal(d.text, '');
});

test('the office design plan is read with its walls, thickness zone, edge beam, mesh and the designer\'s bars kept', () => {
  const dxf = parseDxf(toDxf(buildOfficePlan()));
  const model = extractDesign(dxf, { levelNames: ['TYPICAL FLOOR'] });
  assert.equal(model.levels.length, 1);
  const L = model.levels[0];
  assert.equal(L.name, 'TYPICAL FLOOR - PART 01');
  assert.equal(L.thickness, 230, 'RC230 tag sets the thickness');
  assert.equal(L.columns.length, 6);
  assert.equal(L.walls.length, 1, 'the U core is a wall, not a column');
  assert.equal(L.thickZones.length, 1);
  assert.equal(L.thickZones[0].thickness, 280);
  assert.equal(L.sunken.length, 0, 'the 280 outline is not a sunken zone');
  assert.equal(L.openings.length, 2);
  assert.ok(L.edges.some((e) => e.beam), 'the bottom edge carries an edge beam');
  assert.equal(L.edges.filter((e) => e.beam).length, 1);
  assert.deepEqual(L.meshSpec, [10, 150]);
  assert.equal(L.topMesh, true);
  assert.equal(L.existing.lines.length, 2);
  assert.equal(L.existing.callouts.length, 4);
  assert.ok(L.existing.callouts.every((c) => c.face === 'T'));
  assert.equal(L.existing.dots.length, 1);
  assert.equal(L.camber.length, 1);
  assert.equal(L.levelTags[0].value, '+12.35');
  assert.deepEqual(L.grid.x.map((g) => g.label), ['1', '2', '3']);
  assert.deepEqual(L.grid.y.map((g) => g.label), ['A', 'B']);
});

test('the General Details add bars in the office convention at the places they refer to', () => {
  const dxf = parseDxf(toDxf(buildOfficePlan()));
  const model = extractDesign(dxf, { levelNames: ['TYPICAL FLOOR'] });
  const L = model.levels[0];
  model.spec.walls = { parallelBars: true, cornerDiagonals: true }; // the optional wall extras, on for this check
  const adds = designAdditions(L, model.spec);
  const by = (d) => adds.items.filter((it) => it.detail === d);
  assert.ok(by('D1').length >= 1, 'L-bars along the edge beam, one per run between supports');
  const ind = by('D1').find((it) => it.ind).ind;
  assert.equal(Math.round(Math.abs(ind[ind.length - 1].x - ind[0].x)), 16000, 'one indication line along the whole edge beam');
  assert.ok(ind.every((p) => Math.abs(p.y - 350) < 1), 'the indication line sits 350 mm inside the slab edge');
  assert.ok(by('D1').every((it) => it.face === 'T' && it.l1 === 'T12-150 LBAR (T)' && it.l2 === 'L=4000' && Math.round(dist2(it.a, it.b)) === 3600), 'L-bar 4 m total: 400 into the beam + 3600 on top');
  assert.ok(by('D6').length >= 1 && by('D6').every((it) => it.l1 === 'T12-150 U-BAR' && it.l2 === 'L=4000'), 'U-bars of 4 m at the free edges');
  assert.ok(by('D2').some((it) => it.l1 === 'T12-200 U-BAR'), 'U-bars at the core wall faces');
  assert.ok(by('D2').some((it) => it.l1 === '10T12 (T&B)'), 'parallel bars along the wall');
  // the 280 zone holds the column at 2000,2000: a drop panel, so its bottom mesh T12@150 is the two D4 groups through
  // the column, each as long as the drop (5000 along X; 3000 along Y is stretched to 1.5 m past the 700 column face)
  assert.equal(by('D4').length, 2, 'drop mesh both ways in the 280 zone');
  assert.ok(by('D4').every((it) => it.face === 'B' && it.l1 === 'T12-150 (B)' && it.posCands && it.dist));
  // each drop bar is a U with an angled continuation: 45° crank over the 50 step (80) + 500 beyond the drop, both ends
  const extra = 2 * (80 + 500);
  assert.deepEqual(by('D4').map((it) => it.l2).sort(), [`L=${3700 + extra}`, `L=${5000 + extra}`]);
  assert.ok(by('D4').every((it) => it.crank && it.crank.beyond === 500 && it.extra === extra));
  assert.ok(by('D4').every((it) => Math.abs(it.a.x + it.b.x - 4000) < 1 && Math.abs(it.a.y + it.b.y - 4000) < 1), 'the groups are centred on the column');
  assert.ok(by('D5').some((it) => it.l1 === '3T16-200 (T&B)'), 'diagonals at the core wall corners');
  assert.ok(by('D5').some((it) => it.l1 === '3T12-200 (T&B)'), 'diagonals at the re-entrant slab corner');
  const d7 = by('D7');
  assert.ok(d7.length >= 4, 'void trimmers');
  const row = VOID_TABLE.find((r) => 1.2 <= r.max);
  assert.ok(d7.some((it) => it.l1 === `${row.long.n}T${row.long.dia}-${row.long.s} (T&B)`), 'void bars follow the size table');
  assert.equal(adds.punching.length, 6);
  // detail 9: the 500 strip between the two voids (no beam / wall) is a blockwork support beam 2T20 T&B + T12-200 links, TA beyond each void
  const d9 = by('D9');
  assert.equal(d9.length, 1);
  assert.equal(d9[0].l1, '2T16 (T&B) + T12-200 LINKS');
  assert.ok(Math.abs(d9[0].blockBeam.gap - 500) < 1 && Math.abs(d9[0].a.y - d9[0].b.y) < 1, 'along the strip between the voids');
  assert.equal(Math.round(dist2(d9[0].a, d9[0].b)), 1200 + 2 * d9[0].blockBeam.ta, 'the 1200 overlap + TA each side');
  assert.ok(adds.bars.T.rows().some((r) => /^LINK/.test(r.shape) && r.dia === 12), 'links in the schedule');
  assert.ok(adds.punching.every((p) => /^\d+R-4-T12$/.test(p.tag)));
  assert.ok(adds.bars.T.totals().weight_kg > 0 && adds.bars.B.totals().weight_kg > 0);
  assert.ok(adds.notes.some((n) => /LAP 500/.test(n.text)), 'lap note at the thickness step');
  function dist2(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
});

test('a RAM Concept model goes straight to the design package: its bands in the office convention, the rules on top', async () => {
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const { prepareRamDesign } = await import('../shopdrawings/lib/design.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'ramd-'));
  const ram = readRamConcept(await buildSyntheticCpt(dir));
  const model = prepareRamDesign(ramToModel(ram, { levelName: 'FIRST FLOOR', spec: {} }), { levelName: 'FIRST FLOOR', spec: {} });
  const L = model.levels[0];
  assert.equal(L.existing.items.length, 1, 'the RAM bottom band becomes a designer item; the top band over the column is replaced by the office column bars');
  const bot = L.existing.items[0];
  assert.equal(bot.face, 'B'); assert.equal(bot.l1, 'T12-200 (B)'); assert.equal(bot.l2, 'L=12000');
  assert.ok(bot.dist && Math.round(dist2(bot.dist.p, bot.dist.q)) === 800, 'distribution dimension across the band width');
  assert.ok(L.walls.every((w) => w.polygon && w.id), 'walls get a body and an id');
  assert.equal(model.spec.uEdge.spacing, 150, 'office perimeter rule, not the G.A. assumption');
  assert.equal(L.rcTags.length, 1, 'the slab thickness is tagged once; the thickened zone carries its own THK label');
  const pack = composeDesignPackage(model, { project: 'RAM', prefix: 'SPAN-DD', layerStandard: JSON.parse(readFileSync(join('shopdrawings', 'layers.spantech.json'), 'utf8')) });
  assert.equal(pack.sheets.length, 5);
  const dxfTop = toDxf(pack.sheets.find((s) => s.key === 'dtop').root);
  assert.ok(dxfTop.includes('\n1\nT16-150 (T)\n') && dxfTop.includes('\n1\nT12-150 U-BAR\n'), 'RAM band call-out and the perimeter U-bars on the top sheet');
  assert.ok(/\n0\nDIMENSION\n[\s\S]*?\n3\nDIM100\n/.test(dxfTop), 'distribution DIMENSIONs in DIM100');
  const dxfBot = toDxf(pack.sheets.find((s) => s.key === 'dbottom').root);
  assert.ok(dxfBot.includes('\n1\nT12-200 (B)\n') && dxfBot.includes('BOTTOM MESH T10@200'), 'RAM bottom band and the mesh indication at the thickness change');
  // a column turned 90° in RAM is stored with its plan sizes along X / Y
  const turned = L.columns.find((c) => Math.abs(c.cx - 12000) < 1 && Math.abs(c.cy) < 1);
  assert.equal(turned.w, 800); assert.equal(turned.h, 400); assert.equal(turned.angle, 0);
  // punching: only the column with stud rails in RAM gets the office PS detail - 10 rows @100 covering the 1000 rails, 4 legs
  const dxfPS = toDxf(pack.sheets.find((s) => s.key === 'dpunch').root);
  assert.ok(dxfPS.includes('\n1\nPS1\n') && dxfPS.includes('\n1\n10R-4-T12\n'), 'PS1 = 10R-4-T12 from the RAM stud rails');
  assert.ok(!dxfPS.includes('\n1\nPS2\n'), 'columns without stud rails in RAM carry no punching reinforcement');
  assert.ok(dxfPS.includes('\n8\nPS-ROW\n'), 'the stirrup rows are drawn');
  function dist2(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
});

test('the design package is written in the office layers and text style, on the shop-drawing frame', () => {
  const dxf = parseDxf(toDxf(buildOfficePlan()));
  const model = extractDesign(dxf, { levelNames: ['TYPICAL FLOOR'] });
  const pack = composeDesignPackage(model, { project: 'TEST', prefix: 'SPAN-DD', layerStandard: JSON.parse(readFileSync(join('shopdrawings', 'layers.spantech.json'), 'utf8')) });
  assert.equal(pack.sheets.length, 5);
  assert.deepEqual(pack.sheets.map((s) => s.drawingNo), ['SPAN-DD-000', 'SPAN-DD-L01-01', 'SPAN-DD-L01-02', 'SPAN-DD-L01-03', 'SPAN-DD-L01-04']);
  const top = pack.sheets.find((s) => s.key === 'dtop');
  const dxfOut = toDxf(top.root);
  for (const layer of ['REO-TOP', 'REO-TXT', 'diamension', 'DOTS', 'DETAIL-REF']) assert.ok(dxfOut.includes(`\n8\n${layer}\n`), `${layer} used`);
  assert.ok(/\n2\nBW\n[\s\S]*?\n3\nisocp\.shx\n/.test(dxfOut), 'BW text style with isocp.shx');
  assert.ok(dxfOut.includes('\n1\nT10-300 (T)\n'), "the designer's call-out is kept verbatim");
  assert.ok(dxfOut.includes('\n1\nT12-150 LBAR (T)\n'), 'edge beam L-bar call-out in the office form');
  assert.ok(dxfOut.includes('\n1\nT12-150 U-BAR\n'), 'free edge U-bar call-out');
  assert.ok(dxfOut.includes('\n1\nD1\n') && dxfOut.includes('\n1\nD6\n'), 'detail references');
  assert.ok(dxfOut.includes('\n1\nU500\n'), "the designer's top bar ending at the slab edge gets the U500 end");
  // a bar never runs into an opening: a column bar through the void (x 6500..7700 at y 7000) stops at the void edge
  // with a U, the piece at the column (8000,7000) kept, and its written / cutting lengths follow
  const bar = { a: { x: 6000, y: 7000 }, b: { x: 10000, y: 7000 }, l2: 'L=4000', length: 4000, keep: { x: 8000, y: 7000 }, uEnd: { start: false, end: false } };
  const cut = clipAtOpenings(model.levels[0], bar, 800);
  assert.ok(cut && Math.abs(cut.a.x - 7700) < 1 && Math.abs(cut.b.x - 10000) < 1, 'stopped at the void edge, the column side kept');
  assert.equal(cut.uEnd.start, 'U'); assert.equal(cut.l2, 'L=2300'); assert.equal(cut.length, 2300 + 800);
  // the distribution indicator is a real DIMENSION in style DIM100 with its picture block
  assert.ok(/\n0\nDIMENSION\n[\s\S]*?\n3\nDIM100\n/.test(dxfOut), 'DIMENSION entities in style DIM100');
  assert.ok(/\n0\nDIMSTYLE\n[\s\S]*?\n2\nDIM100\n[\s\S]*?\n44\n0\n[\s\S]*?\n140\n250\n[\s\S]*?\n142\n150\n[\s\S]*?\n75\n1\n76\n1\n[\s\S]*?\n178\n3\n/.test(dxfOut), 'DIM100 record: text 250, oblique tick 150, green text, no extension lines');
  assert.ok(/\n0\nBLOCK\n[\s\S]*?\n2\n\*D\d+\n70\n1\n/.test(dxfOut), 'anonymous picture blocks *Dn (numbered package-wide)');
  assert.ok(/\n0\nLAYER\n[\s\S]*?\n2\nREO-TOP\n[\s\S]*?\n6\nHIDDEN\n/.test(dxfOut), 'REO-TOP is a hidden-line layer');
  assert.ok(dxfOut.includes('\n8\nSPAN-GRID\n'), 'sheet furniture on the SPAN standard');
  const bottom = pack.sheets.find((s) => s.key === 'dbottom');
  const bottomDxf = toDxf(bottom.root);
  assert.ok(bottomDxf.includes('\n1\nT12-150 (B)\n'), 'the drop mesh groups on the bottom sheet');
  assert.ok(bottomDxf.includes('\n1\nBOTTOM MESH T12@150 (D4)\n'), 'the drop mesh written in the drop');
  assert.ok(!bottomDxf.includes('\n1\nT12-150 U-BAR\n'), 'the bottom sheet carries no T&B bars (they are on the top sheet)');
});
