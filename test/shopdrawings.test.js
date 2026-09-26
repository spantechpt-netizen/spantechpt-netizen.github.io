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
import { developmentLength, lapLength, hookDevelopmentLength, splitRun, BarList, bottomMesh, topAtColumns, aroundOpenings, DEFAULT_SPEC } from '../shopdrawings/lib/rebar.mjs';
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
  const bars = new BarList('B');
  bars.add({ dia: 12, shape: 'STR', length: 12000, qty: 10, zone: 'A' });
  bars.add({ dia: 12, shape: 'STR', length: 12000, qty: 5, zone: 'B' });
  bars.add({ dia: 16, shape: 'L', length: 3000, qty: 4, zone: 'C' });
  const rows = bars.rows();
  assert.equal(rows.length, 2);
  assert.equal(rows[0].mark, 'B01');
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
  const rowsThroughStair = xZone.groups.filter((g) => g.runs.length === 2);
  assert.ok(rowsThroughStair.length > 0, 'rows crossing the stair opening are split in two runs');
  const w = res.bars.totals().weight_kg;
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
  assert.equal(pack.sheets.length, 1 + 2 * 7);
  const names = pack.sheets.map((s) => s.blockName);
  for (const base of ['FRAMING_REBAR_SLAB_PT_BOTTOM', 'FRAMING_REBAR_ADDITIONAL_AT_COLUMNS', 'FRAMING_REBAR_U_BARS_AROUND_REGIONS', 'FRAMING_REBAR_AROUND_VOIDS_ACUARS', 'FRAMING_REBAR_AROUND_OPENINGS', 'CABLES_SCHEDULE_EMPTY_TEMPLATE']) {
    assert.ok(names.includes(`${base}_L01`) && names.includes(`${base}_L02`), base);
  }
  assert.ok(existsSync(join(out, 'SHOP_DRAWINGS_PACKAGE.dxf')));
  assert.ok(existsSync(join(out, 'REPORT.md')));
  assert.equal(readdirSync(join(out, 'dxf')).length, 15);
  assert.equal(readdirSync(join(out, 'preview')).length, 15);
  const cables = pack.sheets.find((s) => s.key === 'cables');
  assert.ok(cables.rows.every((r) => r.strands === '' && r.length === ''), 'cable schedule stays empty');
  assert.ok(!readdirSync(join(out, 'schedules')).some((f) => /CABLES/.test(f)), 'no CSV for the empty cable template');
  for (const f of readdirSync(join(out, 'preview'))) assert.ok(!/NaN/.test(readFileSync(join(out, 'preview', f), 'utf8')), `${f} has NaN`);
  const pkg = readFileSync(join(out, 'SHOP_DRAWINGS_PACKAGE.dxf'), 'utf8');
  for (const n of names) assert.ok(pkg.includes(`\n2\n${n}\n`), `${n} defined in the package`);
  assert.ok(model.assumptions.length >= 4);
});
