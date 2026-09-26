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
  assert.deepEqual(spec.topColumns, { dia: 20, spacing: 100 });
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
  assert.deepEqual(model.spec.topColumns, { dia: 16, spacing: 150 });
});

test('top bars over an interior column extend ln/6 each side and satisfy As,min', () => {
  const model = extractModel(parseDxf(toDxf(buildSampleInput())));
  const level = model.levels[1]; // roof: full rectangle, 20 columns
  const res = topAtColumns(level, model.spec);
  const interior = res.columns.find((c) => c.col.id === 'C/2');
  // clear span 7500 − 600 = 6900 → /6 = 1150; length = 1150 + 600 + 1150 = 2900
  assert.equal(interior.per.x.length, 2900);
  assert.equal(interior.per.x.shape, 'STR');
  // 8000 − 600 = 7400 → 1233 → 1250; 1250·2 + 600 = 3100
  assert.equal(interior.per.y.length, 3100);
  assert.ok(interior.per.x.asProv >= interior.per.x.asReq);
  const edge = res.columns.find((c) => c.col.id === 'A/2');
  assert.equal(edge.per.x.shape, 'L', 'edge column bar hooks at the slab edge');
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
  assert.ok(layerNames.includes('ST-RB-T1') && layerNames.includes('ST-RB-B2') && layerNames.includes('ST-SLAB-EDGE') && layerNames.includes('ST-SHEET-TITLE'), layerNames.join(','));
  assert.ok(!layerNames.some((n) => /^REBAR|^COLUMN|BBR/.test(n)), 'no internal or BBR layer names remain');
  assert.ok(/\n2\nST-REBAR\n70\n0\n/.test(pkg) && pkg.includes('romans.shx'), 'rebar text style present');
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
    { UID: 31, Point0: P(0, 0), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' }, { UID: 32, Point0: P(12000, 0), B: 4000, D: 8000, Angle: 0, SupportSet: 'below' },
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
  assert.equal(pkg.sheets.length, 9, '8 sheets for the level + cover');
  const cables = pkg.sheets.find((s) => s.key === 'cables');
  assert.ok(cables.rows.length >= 2, 'cables schedule filled from the RAM tendons');
});
