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
import { buildSyntheticCpt } from './helpers/synthetic-cpt.mjs';
import { readFileSync, existsSync, mkdtempSync, readdirSync, rmSync } from 'node:fs';
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
  assert.equal(pkg.sheets.length, 13, '7 standard sheets + 2 RAM additional sheets + 2 cable sheets (one per direction) + the crossings plan + cover');
  assert.ok(pkg.sheets.find((s) => s.key === 'bottom').rows.some((r) => r.mark.startsWith('B1-') || r.mark.startsWith('B2-')), 'standard bottom mesh drawn on the RAM slab too');
  assert.ok(pkg.sheets.find((s) => s.key === 'top').rows.some((r) => r.mark.startsWith('T1-') || r.mark.startsWith('T2-')), 'standard top bars over columns drawn on the RAM slab too');
  const addb = pkg.sheets.find((s) => s.key === 'addbottom');
  assert.ok(addb.rows.length && addb.rows.every((r) => /^ADD\.B[12]-\d\d$/.test(r.mark)), addb.rows.map((r) => r.mark).join(','));
  assert.ok(pkg.sheets.find((s) => s.key === 'addtop').rows.every((r) => /^ADD\.T[12]-\d\d$/.test(r.mark)));
  const cables = pkg.sheets.filter((s) => s.key === 'cables_lat' || s.key === 'cables_lon');
  assert.equal(cables.length, 2, 'one cable sheet per tendon direction');
  assert.ok(cables.every((c) => c.rows.length >= 1), 'cables schedules filled from the RAM tendons');
  assert.ok(cables[0].csvCols.some((c) => c.key === 'elong') && cables[0].csvCols.some((c) => c.key === 'jack'), 'the shop cable sheet carries extensions and the jacking force per strand (office schedule)');
  assert.ok(cables[0].rows.every((r) => /^[AB]\.\d\d$/.test(r.mark) && r.qty >= 1 && r.anchors), 'one schedule row per mark, the tendon numbers of the mark listed as anchor numbers');
  assert.ok(cables[0].rows.some((r) => r.chairs > 0), 'chair stations counted along the tendons with a profile');
  assert.ok(!pkg.sheets.some((s) => s.key === 'cables'), 'the empty template gives way to the RAM cable sheets');
  // the crossings plan (office convention): the X tendon (2100 high at x = 6000, sloping to 1250 at its ends) meets
  // the Y tendon (1250 at both ends: 1250 above the soffit throughout) at (3000, 2000); the X tendon is the higher
  // one there, so it passes over and the Y tendon is drawn broken at the crossing
  const { tendonCrossings } = await import('../shopdrawings/lib/sheets.mjs');
  const L = model.levels[0];
  const cr = tendonCrossings(L);
  assert.equal(cr.length, 1, 'one crossing between the two directions');
  assert.ok(Math.abs(cr[0].pt.x - 3000) < 1 && Math.abs(cr[0].pt.y - 2000) < 1);
  const xt = cr[0].a.spanSet === 'latitude' ? 'a' : 'b';
  assert.equal(cr[0].over, xt, 'the X tendon passes over (higher CGS at the crossing)');
  assert.ok(cr[0].gap > 20 && !cr[0].clash && !cr[0].tight, `gap ${cr[0].gap} mm, neither clash nor tight`);
  const cross = pkg.sheets.find((s) => s.key === 'cables_cross');
  assert.ok(cross && cross.drawingNo.endsWith('-07C'), 'the crossings sheet is 07C');
  assert.equal(cross.rows.length, 0, 'no clash or tight crossing to list');
  const dxfCross = toDxf(cross.root);
  assert.ok(dxfCross.includes('\n8\nPT-Cross-A\n') && dxfCross.includes('\n8\nPT-Cross-B\n') && dxfCross.includes('\n8\nPT-Cross-Gap\n'), 'both directions on the office crossing layers with the gap figure');
  assert.ok(/\n1\nA \d+\n/.test(dxfCross), 'the figure at the crossing names the direction on top (A) and the gap');
  const bPieces = (dxfCross.match(/\n8\nPT-Cross-B\n/g) || []).length;
  assert.ok(bPieces >= 2, 'the tendon under is drawn in two pieces, broken at the crossing');
});

/** The architect's plan of the synthetic slab: the same columns shifted by (dx, dy), the grid lettered A-C / 1-3, the slab drawn 1 m larger. */
function buildReferencePlan(dx, dy) {
  const c = new Canvas();
  c.pline([{ x: -1000 + dx, y: -1000 + dy }, { x: 13000 + dx, y: -1000 + dy }, { x: 13000 + dx, y: 9000 + dy }, { x: -1000 + dx, y: 9000 + dy }], { layer: 'S-RC slab', closed: true });
  const col = c.block('COLUMN'); col.rect(-200, -400, 400, 800, { layer: 'STR-COLS', closed: true });
  for (const [x, y] of [[0, 0], [12000, 0], [0, 8000], [12000, 8000], [6000, 4000]]) c.insert('COLUMN', x + dx, y + dy);
  for (const [i, x] of [0, 6000, 12000].entries()) { c.line(x + dx, -3000 + dy, x + dx, 11000 + dy, { layer: 'S-GRID' }); c.circle(x + dx, 11600 + dy, 400, { layer: 'S-GRID-IDEN' }); c.text(x + dx, 11600 + dy, 'ABC'[i], { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  for (const [i, y] of [0, 4000, 8000].entries()) { c.line(-3000 + dx, y + dy, 15000 + dx, y + dy, { layer: 'S-GRID' }); c.circle(-3600 + dx, y + dy, 400, { layer: 'S-GRID-IDEN' }); c.text(-3600 + dx, y + dy, String(i + 1), { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  return c;
}

test('a reference plan (the architect\'s grid, columns and slab edge) is fitted on the RAM columns and used instead of the RAM geometry', async () => {
  const { readReferencePlan, alignByColumns, alignByPoint, applyReference } = await import('../shopdrawings/lib/reference.mjs');
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'spantech-ref-'));
  const ram = readRamConcept(await buildSyntheticCpt(dir));
  const ref = readReferencePlan(toDxf(buildReferencePlan(50000, 30000)));
  assert.equal(ref.columns.length, 5);
  assert.deepEqual(ref.grid.x.map((g) => g.label), ['A', 'B', 'C']);
  assert.deepEqual(ref.grid.y.map((g) => g.label), ['1', '2', '3']);
  assert.ok(ref.gridFromDrawing, 'the grid comes from the bubbles of the drawing');
  const fit = alignByColumns(ref.columns, ram.columns);
  assert.deepEqual([fit.rot, fit.dx, fit.dy, fit.matched, fit.total], [0, -50000, -30000, 5, 5], 'the drawing is shifted onto the model, every column matched');
  // the plan turned by 90° is found too
  const turned = readReferencePlan(toDxf(buildReferencePlan(0, 0)).replace(/^/, ''));
  const fit90 = alignByColumns(turned.columns.map((c) => ({ ...c, cx: -c.cy, cy: c.cx })), ram.columns);
  assert.equal(fit90.matched, 5, `turned drawing fitted: ${JSON.stringify(fit90)}`);
  assert.ok([90, 270].includes(fit90.rot));
  // by a common point: grid A/1 of the drawing is column (0, 0) of the model
  const byPoint = alignByPoint({ dxf: { x: 50000, y: 30000 }, ram: { x: 0, y: 0 } });
  assert.deepEqual([byPoint.dx, byPoint.dy], [-50000, -30000]);

  const model = ramToModel(ram, { levelName: 'BASEMENT', levelId: 'B1' });
  const res = applyReference(model, ref, { ramColumns: ram.columns });
  const L = model.levels[0];
  assert.equal(L.grid.source, 'reference plan');
  assert.deepEqual(L.grid.x.map((g) => `${g.label}@${Math.round(g.x)}`), ['A@0', 'B@6000', 'C@12000']);
  assert.deepEqual(L.grid.y.map((g) => `${g.label}@${Math.round(g.y)}`), ['1@0', '2@4000', '3@8000']);
  assert.equal(L.columns.length, 5);
  assert.ok(L.columns.every((c) => c.fromReference && c.ramId), 'every drawn column stands on a RAM column');
  assert.ok(L.columns.some((c) => c.id === 'B/2'), 'column ids from the drawing grid');
  assert.deepEqual(L.outline.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`), ['-1000,-1000', '13000,-1000', '13000,9000', '-1000,9000'], 'the slab edge of the drawing, in model coordinates');
  assert.ok(L.ramOutline && res.used.outline === 1);
  assert.ok(model.assumptions.some((a) => /taken from the reference plan/.test(a.text)) && !model.assumptions.some((a) => /Grid lines are not modelled/.test(a.text)));
  // through generate(): the package carries the drawing's grid references
  const { generate } = await import('../shopdrawings/cli.mjs');
  const out = join(dir, 'out');
  const { model: m2, pack } = generate({ inputDxf: join(dir, 'synthetic.cpt'), out, meta: { project: 'REF', prefix: 'T', levelId: 'B1' }, spec: { reference: { text: toDxf(buildReferencePlan(50000, 30000)), use: { grid: true, columns: true, outline: false } } }, svg: false, levelNames: ['BASEMENT'], mode: 'design' });
  assert.ok(m2.levels.every((l) => l.grid.source === 'reference plan'));
  assert.ok(m2.findings.some((f) => /Reference plan fitted on the columns: 5 of 5/.test(f)));
  const sheet = pack.sheets.find((s) => s.key === 'dtop');
  assert.ok(sheet, 'top sheet built on the reference grid');
  rmSync(dir, { recursive: true, force: true });
});

test('beam design through RAM: one strip per beam span with a splitter on each edge written into the .cpt, and the designed beams read back into types and a schedule sheet', async () => {
  const { writeBeamStrips, beamSchedule, beamSpans } = await import('../shopdrawings/lib/beam-strips.mjs');
  const { readRamConcept } = await import('../shopdrawings/lib/ram-concept.mjs');
  const { DatabaseSync } = await import('node:sqlite');
  const dir = mkdtempSync(join(tmpdir(), 'spantech-beams-'));
  const src = await buildSyntheticCpt(dir, { beam: true });
  const ram = readRamConcept(src);
  assert.equal(ram.beams.length, 2);
  // the edge beam along y = 150 runs from the column at (0, 0) to the one at (12000, 0): one span, both ends supported
  const edge = beamSpans(ram.beams.find((b) => b.id === 'BM2'), ram.columns, ram.walls);
  assert.equal(edge.spanSet, 'latitude');
  assert.equal(edge.spans.length, 1);
  assert.ok(edge.spans[0].support0?.kind === 'column' && edge.spans[0].support1?.kind === 'column');
  const out = join(dir, 'beam-strips.cpt');
  const sum = writeBeamStrips(src, out, ram);
  assert.deepEqual([sum.beams, sum.spans, sum.splitters], [2, 2, 4]);
  assert.equal(sum.removed.SpanSegment, 2, 'the old slab strips are gone');
  assert.equal(sum.removed.SpanDesign, 1, 'stale strip results are gone');
  const db = new DatabaseSync(out, { readOnly: true });
  const segs = db.prepare('select * from SpanSegment order by SpanSet, ChildIndex').all();
  assert.equal(segs.length, 2);
  assert.ok(segs.every((r) => r.ColumnStripDesignSystem === 'beam' && r.MiddleStripDesignSystem === 'beam' && r.ColumnStripWidthCalc === 'full'), 'designed as beams');
  const lat = segs.find((r) => r.SpanSet === 'latitude');
  assert.deepEqual([lat.Point0, lat.Point1, lat.Name, lat.FrameNumber, lat.SpanNumber, lat.AtSupport0, lat.AtSupport1, lat.SupportWidth0, lat.SupportWidth1], ['[0][1500]', '[120000][1500]', '1-1', 0, 0, 1, 1, 4000, 8000], 'the strip on the beam centre line, in 0.1 mm, with the column sizes at its ends');
  assert.equal(lat.ParentUID, db.prepare("select UID from SpanSegmentCategory where SpanSet = 'latitude'").get().UID, 'in the latitude category');
  assert.ok(lat.UID > 931 && segs.every((r) => r.PreviousSibUID === 0 && r.NextSibUID === 0 && r.ChildIndex === 0), 'fresh UIDs, one child per category chained');
  const bounds = db.prepare("select Boundary, SpanSet from StripBoundary where SpanSet = 'longitude' order by ChildIndex").all();
  assert.deepEqual(bounds.map((b) => b.Boundary), ['[[88500][0]][[88500][80000]]', '[[91500][0]][[91500][80000]]'], 'a splitter on each edge of the 300 wide beam at x = 9 m');
  const chain = db.prepare("select UID, PreviousSibUID, NextSibUID, ChildIndex, Number from StripBoundary where SpanSet = 'longitude' order by ChildIndex").all();
  assert.ok(chain[0].PreviousSibUID === 0 && chain[0].NextSibUID === chain[1].UID && chain[1].PreviousSibUID === chain[0].UID && chain[1].NextSibUID === 0 && chain[1].Number === 1, 'sibling chain');
  const strips = db.prepare('select Name, StripType, SpanSegment from SpanSegmentStrip').all();
  assert.equal(strips.length, 2);
  assert.ok(strips.some((r) => r.Name === '1C-1' && r.SpanSegment === lat.UID));
  db.close();
  // the schedule off the (already calculated) synthetic model: the interior beam carries RAM's 4T16 top / 3T16 bottom / T12 @ 125 links
  const sch = beamSchedule(ram);
  assert.equal(sch.types.length, 1);
  const t = sch.types[0];
  assert.deepEqual([t.mark, t.section, t.top.text, t.bottom.text, t.stirrups.text, t.count, t.beams], ['B1', '300x600', '4T16', '3T16', 'T12-2L@125', 1, ['BM1']]);
  assert.deepEqual(sch.undesigned, ['BM2'], 'the edge beam has no RAM bars in it');
  assert.deepEqual(sch.added.map((x) => x.mark), ['B1'], 'without a project schedule the type is new');
  // the project's unified schedule: a type on record that carries the beam is used as it is (the lightest one that does),
  // a heavier or different-section record leaves the beam to a new type numbered after the last mark; records never change
  const { typeCovers } = await import('../shopdrawings/lib/beam-strips.mjs');
  const rec = (mark, top, bottom, spacing = 125, width = 300, depth = 600) => ({ mark, width, depth, top: { n: top, dia: 16 }, bottom: { n: bottom, dia: 16 }, stirrups: { dia: 12, legs: 2, spacing } });
  const withLib = beamSchedule(ram, null, { library: [rec('B1', 6, 4, 100), rec('B2', 4, 3), rec('B3', 4, 3, 125, 400, 700)] });
  assert.deepEqual(withLib.types.map((x) => [x.mark, x.count, !!x.existing]), [['B2', 1, true]], 'the lightest record that carries the beam (B2, not the heavier B1)');
  assert.deepEqual(withLib.added, [], 'no new type');
  assert.equal(withLib.beams.find((b) => b.id === 'BM1').mark, 'B2');
  const tooLight = beamSchedule(ram, null, { library: [rec('B1', 3, 3), rec('B7', 4, 3, 125, 400, 700)] });
  assert.deepEqual(tooLight.types.map((x) => [x.mark, !!x.isNew]), [['B8', true]], 'no record carries 4T16 top: a new type after the last mark, B1 untouched');
  assert.deepEqual(tooLight.added.map((x) => [x.mark, x.top.text]), [['B8', '4T16']]);
  assert.ok(typeCovers(rec('X', 4, 3, 125), { width: 300, depth: 600, top: { n: 4, dia: 16 }, bottom: { n: 3, dia: 16 }, stirrups: { dia: 12, legs: 2, spacing: 150 } }) && !typeCovers(rec('X', 4, 3, 150), { width: 300, depth: 600, top: { n: 4, dia: 16 }, bottom: { n: 3, dia: 16 }, stirrups: { dia: 12, legs: 2, spacing: 125 } }), 'stirrup capacity counts');
  // through both packages: the beams sheet appears with the schedule, the plan labelled
  const { generate } = await import('../shopdrawings/cli.mjs');
  const { pack } = generate({ inputDxf: src, out: join(dir, 'design'), meta: { project: 'BEAMS', prefix: 'T', levelId: 'B1' }, svg: false, levelNames: ['BASEMENT'], mode: 'design' });
  const sheet = pack.sheets.find((s) => s.key === 'dbeams');
  assert.ok(sheet && sheet.drawingNo.endsWith('-07'), 'beam sheet 07 in the design package');
  assert.deepEqual(sheet.rows.map((r) => [r.mark, r.section, r.top, r.bottom, r.count]), [['B1', '300 x 600', '4T16', '3T16', 1]]);
  const dxf = toDxf(sheet.root);
  assert.ok(dxf.includes('\n1\nB1 300x600\n') && dxf.includes('\n1\n?? 300x600\n'), 'every beam labelled with its type and section on the plan');
  const { pack: unified } = generate({ inputDxf: src, out: join(dir, 'unified'), meta: { project: 'BEAMS', prefix: 'T', levelId: 'B1' }, spec: { beamTypes: [rec('B1', 3, 3), rec('B2', 5, 4, 100)] }, svg: false, levelNames: ['BASEMENT'], mode: 'design' });
  const us = unified.sheets.find((s) => s.key === 'dbeams');
  assert.deepEqual(us.rows.map((r) => [r.mark, r.top]), [['B2', '5T16']], 'the beam takes the project type on record, printed with its bars');
  assert.ok(toDxf(us.root).includes('UNIFIED BEAM SCHEDULE'), 'the sheet says so');
  const { pack: shop } = generate({ inputDxf: src, out: join(dir, 'shop'), meta: { project: 'BEAMS', prefix: 'T', levelId: 'B1' }, svg: false, levelNames: ['BASEMENT'], mode: 'shop' });
  assert.ok(shop.sheets.some((s) => s.key === 'beams' && s.drawingNo.endsWith('-09')), 'beam sheet 09 in the shop package');
  const plain = await buildSyntheticCpt(dir);
  const { pack: noBeams } = generate({ inputDxf: plain, out: join(dir, 'plain'), meta: { project: 'X', prefix: 'T', levelId: 'B1' }, svg: false, levelNames: ['BASEMENT'], mode: 'design' });
  assert.ok(!noBeams.sheets.some((s) => s.key === 'dbeams'), 'no beam sheet without beams');
  rmSync(dir, { recursive: true, force: true });
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
  // every L-bar symbol carries its own distribution dimension: the run between the column bars it stands for, 350 mm
  // inside the slab edge, with the symbol in the middle of that run
  assert.ok(by('D1').every((it) => it.dist && !it.ind), 'a distribution dimension per run, no indication line');
  const runs = by('D1').map((it) => [Math.min(it.dist.p.x, it.dist.q.x), Math.max(it.dist.p.x, it.dist.q.x)]).sort((u, v) => u[0] - v[0]);
  assert.ok(runs.every(([x1, x2]) => x1 >= 0 && x2 <= 16000 && x2 - x1 >= 800), 'the runs lie along the 16 m edge beam');
  assert.ok(runs.every(([x1, x2], i) => i === 0 || x1 >= runs[i - 1][1] - 1), 'the runs do not overlap');
  assert.ok(by('D1').every((it) => Math.abs(it.a.x - (it.dist.p.x + it.dist.q.x) / 2) < 1), 'the symbol sits in the middle of its run');
  assert.ok(by('D1').every((it) => Math.abs(it.dist.p.y - 350) < 1 && Math.abs(it.dist.q.y - 350) < 1), 'the dimension sits 350 mm inside the slab edge');
  assert.ok(by('D1').every((it) => it.face === 'T' && it.l1 === 'T12-150 LBAR (T)' && it.l2 === 'L=4000' && Math.round(dist2(it.a, it.b)) === 3600), 'L-bar 4 m total: 400 into the beam + 3600 on top');
  assert.ok(by('D6').length >= 1 && by('D6').every((it) => it.l1 === 'T12-150 U-BAR' && it.l2 === 'L=4000'), 'U-bars of 4 m at the free edges');
  assert.ok(by('D2').some((it) => it.l1 === 'T12-200 U-BAR'), 'U-bars at the core wall faces');
  assert.ok(by('D2').some((it) => it.l1 === '10T12 (T&B)'), 'parallel bars along the wall');
  // the 280 zone holds the column at 2000,2000: a drop panel, so its bottom mesh T12@150 is the two D4 groups through
  // the column, each as long as the drop (5000 along X; 3000 along Y is stretched to 1.5 m past the 700 column face)
  assert.equal(by('D4').length, 2, 'drop mesh both ways in the 280 zone');
  assert.ok(by('D4').every((it) => it.face === 'B' && it.l1 === 'T12-150 (B)' && it.posCands && it.dist));
  // each drop bar: the bottom run stops 50 short of the drop faces (1000..6000 x 1000..4000 → 4900 / 2900), rises with a
  // 90° bend over the 50 step and continues at the slab bottom 500, or further where the office length (5000 / 3700
  // centred on the column at 2000,2000) reaches beyond the drop: X 1500 + 500, Y 850 + 500
  assert.deepEqual(by('D4').map((it) => it.l2).sort(), [`L=${2900 + 100 + 850 + 500}`, `L=${4900 + 100 + 1500 + 500}`]);
  assert.ok(by('D4').every((it) => it.bend && it.bend.rise === 50 && it.bend.beyondB === 500 && it.extra === 2 * 50 + it.bend.beyondA + it.bend.beyondB));
  const d4x = by('D4').find((it) => Math.abs(it.a.y - it.b.y) < 1), d4y = by('D4').find((it) => Math.abs(it.a.x - it.b.x) < 1);
  assert.ok(Math.abs(Math.min(d4x.a.x, d4x.b.x) - 1050) < 1 && Math.abs(Math.max(d4x.a.x, d4x.b.x) - 5950) < 1 && d4x.bend.beyondA === 1500, 'X run inside the drop, 1.5 m continuation on the near side');
  assert.ok(Math.abs(Math.min(d4y.a.y, d4y.b.y) - 1050) < 1 && Math.abs(Math.max(d4y.a.y, d4y.b.y) - 3950) < 1 && d4y.bend.beyondA === 850, 'Y run inside the drop');
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
  assert.equal(pack.sheets.length, 7, 'framing, bottom, top, punching, two cable sheets (one per direction), cover');
  const dc = pack.sheets.filter((s) => s.key === 'dcablat' || s.key === 'dcablon');
  assert.equal(dc.length, 2);
  assert.ok(dc.every((c) => !c.csvCols.some((k) => k.key === 'elong' || k.key === 'jack')), 'design cable sheets carry no elongation or jacking force');
  const dxfCab = toDxf(dc.find((c) => c.key === 'dcablat').root);
  assert.ok(dxfCab.includes('\n1\nH210\n') && !dxfCab.includes('\n1\nL125\n'), 'the high point written at the point (H + CGS height); the anchors at 125 are ends, not low points');
  assert.ok(dxfCab.includes('\n8\nText-Profile-A-HIGH\n') && dxfCab.includes('\n8\nPT-HighLow-A\n') && dxfCab.includes('\n2\nLiveEnd\n'), 'office cable layers and anchor blocks');
  assert.ok(dc.every((c) => c.rows.every((r) => /^[AB]\.\d\d$/.test(r.mark))), 'design cable schedule keyed by mark');
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

test('slab mesh option, punching check and the engineer\'s bypass: the top mesh written when both faces are chosen, a column beyond the stirrup limit blocks, the bypass draws PS at it in the engineer\'s name', async () => {
  const { generate } = await import('../shopdrawings/cli.mjs');
  const { punchingCheck, blockingAfter, overrideColumns } = await import('../shopdrawings/lib/punching.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'punch-'));
  // modest loads: every column passes, the mesh option shows on the top sheet and in the take-off
  const light = await buildSyntheticCpt(dir, { loads: { dead: 2, live: 3 } });
  const r0 = generate({ inputDxf: light, out: join(dir, 'light'), meta: { designer: 'Eng. Sara Test' }, spec: { mesh: 'both' }, svg: false, levelNames: ['FIRST'], mode: 'design' });
  const L0 = r0.model.levels[0];
  assert.equal(L0.topMesh, true); assert.equal(L0.meshFaces, 'both');
  assert.deepEqual(L0.meshLabels[0].lines, ['MESH T12@200', 'TOP & BOTTOM TWO WAY']);
  assert.equal(r0.quantities.levels[0].mesh.faces, 2, 'the mesh joins the take-off with both faces');
  assert.ok(r0.quantities.levels[0].steel.mesh_kg > 1000 && r0.quantities.levels[0].steel.kg >= r0.quantities.levels[0].steel.mesh_kg);
  const top0 = readFileSync(r0.files.find((f) => /TOP_REINFORCEMENT.*\.dxf$/.test(f)), 'utf8');
  assert.ok(top0.includes('\n1\nTOP MESH T12@200\n') && top0.includes('TOP & BOTTOM (BOTH FACES)'), 'top mesh written on the top sheet');
  assert.ok(top0.includes('\n1\nPREPARED / DESIGNED BY\n') && top0.includes('\n1\nENG. SARA TEST\n'), 'the engineer who ran the program signs the title block');
  const pc0 = r0.punching[0];
  assert.ok(pc0.columns.length === 5 && pc0.columns.every((c) => c.status === 'ok'), JSON.stringify(pc0.columns.map((c) => [c.id, c.ratio])));
  assert.equal(pc0.columns.find((c) => c.loc === 'interior').trib_source, 'RAM', 'RAM\'s own tributary area where the punching check carries it');
  assert.deepEqual(pc0.blocking, []);
  // the same slab under a heavy live load: the interior column with stud rails passes RAM, the corner ones fail even with stirrups
  const heavy = await buildSyntheticCpt(dir, { loads: { dead: 4, live: 40 } });
  const r1 = generate({ inputDxf: heavy, out: join(dir, 'heavy'), meta: {}, spec: { mesh: 'bottom' }, svg: false, levelNames: ['FIRST'], mode: 'design' });
  const L1 = r1.model.levels[0];
  assert.equal(L1.topMesh, false);
  const pc1 = r1.punching[0];
  assert.ok(pc1.blocking.length >= 4 && pc1.columns.filter((c) => c.status === 'fail').length >= 4, JSON.stringify(pc1.columns.map((c) => [c.id, c.status, c.ratio])));
  const corner = pc1.columns.find((c) => c.loc === 'corner');
  assert.ok(corner.detail && corner.detail.rows >= 12 && corner.detail.legs >= 4, 'what the office detail would need is estimated for every flagged column');
  assert.ok(!r1.files.some((f) => /PUNCH/.test(f) && readFileSync(f, 'utf8').includes('RESPONSIBILITY')), 'no bypass yet: nothing drawn at the failing columns');
  // the engineer's list of columns failing in RAM is flagged whatever the estimate says
  const ramFailed = punchingCheck(r0.model.levels[0], { ...r0.model.spec, punching: { ramFailed: [pc0.columns[0].id.toLowerCase()] } });
  assert.deepEqual(ramFailed.blocking, [pc0.columns[0].id]);
  // decisions: thicken keeps the block, ram_ok / bypass on the named columns clear it
  assert.deepEqual(blockingAfter(pc1, { mode: 'thicken' }), pc1.blocking);
  assert.deepEqual(blockingAfter(pc1, { mode: 'bypass', columns: 'all' }), []);
  assert.deepEqual(blockingAfter(pc1, { mode: 'ram_ok', columns: [pc1.blocking[0]] }), pc1.blocking.slice(1));
  assert.deepEqual([...overrideColumns(pc1, { columns: 'all' })], pc1.flagged);
  // the bypass: PS strips at the named columns, sized from the estimate, the sheets naming the engineer and the date
  const target = pc1.blocking[0];
  const r2 = generate({ inputDxf: heavy, out: join(dir, 'bypass'), meta: { designer: 'Eng. Sara Test' }, spec: { punching: { override: { columns: [target], by: 'Eng. Sara Test', date: '2026-09-28', note: 'client refused a drop' } } }, svg: false, levelNames: ['FIRST'], mode: 'design' });
  assert.deepEqual(r2.punching[0].overridden, [target]);
  const ps = readFileSync(r2.files.find((f) => /PUNCHING.*\.dxf$/.test(f)), 'utf8');
  assert.ok(ps.includes('\n1\nPS2\n') || ps.includes('\n1\nPS1\n'), 'a PS type at the bypassed column');
  assert.ok(ps.includes("PS AT THE DESIGN ENGINEER'S RESPONSIBILITY") && ps.includes('ENG. SARA TEST') && ps.includes('2026-09-28'), 'the bypass is written on the punching sheet with the engineer\'s name and the date');
  assert.ok(ps.includes('CLIENT REFUSED A DROP'), 'the engineer\'s reason is printed in the assumptions');
  const top2 = readFileSync(r2.files.find((f) => /TOP_REINFORCEMENT.*\.dxf$/.test(f)), 'utf8');
  assert.ok(top2.includes(`${target}: PUNCHING NOT PASSING`), 'the top sheet carries the boxed note at the column');
  assert.ok(existsSync(join(dir, 'bypass', 'punching.json')) && readFileSync(join(dir, 'bypass', 'REPORT.md'), 'utf8').includes('Indicative punching check'));
  rmSync(dir, { recursive: true, force: true });
});

test('office beam design: continuous-beam envelope on the model loads, bars and stirrups, the deflection check that blocks, and the ram / office / max option', async () => {
  const { threeMoment, analyseBeam, flexureAs, shearDesign, deflectionCheck, designBeams, pickBars, beamBlockingAfter } = await import('../shopdrawings/lib/beam-design.mjs');
  // the three-moment equation: two equal spans under w give -wL²/8 at the middle support
  assert.deepEqual(threeMoment([6000, 6000], [10, 10]).map((v) => Math.round(v * 10) / 10), [0, -45, 0]);
  const env = analyseBeam([{ length: 6000 }, { length: 6000 }], 20, 10);
  assert.ok(env.Mneg[1] < -(1.2 * 20 + 1.6 * 10) * 36 / 8 + 1 && env.Mpos[0] > 0 && env.Vend[0][1] > env.Vend[0][0], 'patterned live load: hogging at least the full-load value, sagging positive, more shear at the interior end');
  assert.ok(Math.abs(flexureAs(100, 300, 540, 30, 420).as - 520) < 40, 'As for 100 kN·m on 300 x 600 ≈ 520 mm²');
  assert.equal(flexureAs(2000, 300, 540, 30, 420).ok, false, 'a section that cannot carry the moment singly reinforced is flagged');
  const sh = shearDesign(150, 300, 540, 30, 420);
  assert.ok(sh.ok && sh.legs === 2 && sh.spacing <= 270 && sh.spacing >= 75, JSON.stringify(sh));
  assert.equal(shearDesign(2000, 300, 540, 30, 420).ok, false, 'Vs over 0.66 sqrt(fc) b d: section too small');
  assert.deepEqual(pickBars(1200, 300, 40).text, '4T20');
  assert.equal(deflectionCheck({ L: 6000, b: 300, h: 600, d: 540, as: 800, fc: 30, ends: 2, Ma: 100, live: 40 }).table_ok, true, 'h >= L/21');
  const dc = deflectionCheck({ L: 12000, b: 300, h: 500, d: 440, as: 1500, fc: 30, ends: 0, Ma: 350, MaLeft: 0, MaRight: 0, live: 120 });
  assert.ok(!dc.table_ok && dc.ratio > 1 && !dc.ok, JSON.stringify(dc));
  // a hand-made level: a 300 x 400 beam over two 6 m spans on three columns under a 3 + 5 kN/m² slab
  const outline = [{ x: 0, y: 0 }, { x: 12000, y: 0 }, { x: 12000, y: 8000 }, { x: 0, y: 8000 }];
  const level = { thickness: 250, outline, walls: [], columns: [{ id: 'C1', cx: 0, cy: 4000, w: 400, h: 400 }, { id: 'C2', cx: 6000, cy: 4000, w: 400, h: 400 }, { id: 'C3', cx: 12000, cy: 4000, w: 400, h: 400 }], beams: [{ id: 'BM1', a: { x: 0, y: 4000 }, b: { x: 12000, y: 4000 }, t: 300, depth: 400 }], ram: { areaLoads: [{ type: 'dead', q: 3, polygon: outline }, { type: 'live', q: 5, polygon: outline }] } };
  const r = designBeams(level, { fc: 30, fy: 420 });
  const bm = r.beams[0];
  assert.equal(bm.spans.length, 2); assert.equal(bm.spans[0].support0, 'column');
  assert.ok(Math.abs(bm.Mneg_max - bm.loads.wu * 36 / 8) < 1, 'hogging at the middle support = wu L² / 8');
  assert.ok(bm.reasons.includes('flexure') || bm.reasons.includes('shear'), 'a 400 deep beam cannot carry it');
  level.beams[0].depth = 700;
  const r2 = designBeams(level, { fc: 30, fy: 420 });
  assert.deepEqual(r2.beams[0].reasons, []); assert.ok(r2.beams[0].top.area >= r2.beams[0].as_top_req && r2.beams[0].stirrups.spacing >= 75);
  assert.deepEqual(r2.failing, []);
  // the engineer's list of beams failing in RAM blocks whatever the estimate says; decisions clear it
  const r3 = designBeams(level, { fc: 30, fy: 420, beams: { ramFailed: ['bm1'] } });
  assert.deepEqual([r3.blocking, r3.beams[0].ram_failed], [['BM1'], true]);
  assert.deepEqual(beamBlockingAfter(r3, { mode: 'deepen' }), ['BM1']);
  assert.deepEqual(beamBlockingAfter(r3, { mode: 'bypass', beams: 'all' }), []);
  // through the generator: the option decides the bars drawn, the edge beam without RAM bars gets the office design, a 12 m 300 x 600 edge beam fails deflection
  const { generate } = await import('../shopdrawings/cli.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'bd-'));
  const src = await buildSyntheticCpt(dir, { beam: true, loads: { dead: 3, live: 4 } });
  const by = {};
  for (const mode of ['ram', 'office', 'max']) {
    const out = generate({ inputDxf: src, out: join(dir, mode), meta: {}, spec: { beamDesign: mode }, svg: false, levelNames: ['B1'], mode: 'design' });
    by[mode] = out.model.levels[0].beamSchedule;
    assert.equal(out.beamChecks[0].design, mode);
  }
  const bm1 = (m) => by[m].beams.find((b) => b.id === 'BM1');
  assert.deepEqual([bm1('ram').top.text, bm1('ram').bottom.text, bm1('ram').stirrups.text], ['4T16', '3T16', 'T12-2L@125'], 'RAM bars as before');
  assert.equal(bm1('office').bottom.text, bm1('office').office.bottom.text);
  assert.ok(bm1('office').office.bottom.area > bm1('ram').bottom.area, 'the office design of the 8 m simply supported beam is heavier than the RAM band in the file');
  assert.deepEqual([bm1('max').top.text, bm1('max').bottom.text, bm1('max').stirrups.text], ['4T16', bm1('office').bottom.text, 'T12-2L@125'], 'max: set by set the heavier (RAM top and stirrups, office bottom)');
  assert.deepEqual(by.ram.undesigned, ['BM2']); assert.deepEqual(by.office.undesigned, [], 'the office design covers the beam RAM did not');
  assert.ok(by.office.office.failing.includes('BM2') && by.office.office.beams.find((b) => b.id === 'BM2').reasons.includes('deflection'), 'the 12 m 300 x 600 edge beam fails deflection');
  const sheet = readFileSync(readdirSync(join(dir, 'office', 'dxf')).map((f) => join(dir, 'office', 'dxf', f)).find((f) => /BEAM/.test(f)), 'utf8');
  assert.ok(sheet.includes('OFFICE DESIGN') && sheet.includes('NOT PASSING (DEFLECTION)') && sheet.includes('BEAMS NOT PASSING THE OFFICE CHECK: BM2'), 'the sheet says which beam fails and why');
  const ok = generate({ inputDxf: src, out: join(dir, 'bypass'), meta: {}, spec: { beamDesign: 'office', beams: { override: { beams: 'all', by: 'Eng. Sara Test', date: '2026-09-28', note: 'camber 20 mm' } } }, svg: false, levelNames: ['B1'], mode: 'design' });
  const sheet2 = readFileSync(readdirSync(join(dir, 'bypass', 'dxf')).map((f) => join(dir, 'bypass', 'dxf', f)).find((f) => /BEAM/.test(f)), 'utf8');
  assert.ok(sheet2.includes("ACCEPTED AT THE DESIGN ENGINEER'S RESPONSIBILITY (ENG. SARA TEST, 2026-09-28): CAMBER 20 MM"), 'the bypass is printed with the engineer\'s name');
  assert.ok(readFileSync(join(dir, 'office', 'REPORT.md'), 'utf8').includes('Office beam design') && existsSync(join(dir, 'office', 'beams.json')));
  void ok;
  rmSync(dir, { recursive: true, force: true });
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

test('office rule: an interior beam carries top bars across it (4 m / 1.5 m past each face), nothing along it; an edge beam does not', async () => {
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const { prepareRamDesign, applyColumnRule } = await import('../shopdrawings/lib/design.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'ram-beam-'));
  const ram = readRamConcept(await buildSyntheticCpt(dir, { beam: true }));
  assert.equal(ram.beams.length, 2);
  assert.equal(ram.beams[0].t, 300);
  assert.equal(ram.beams[0].depth, 600);
  const model = prepareRamDesign(ramToModel(ram, { levelName: 'BEAM TEST', spec: { ramBands: 'none' } }), { levelName: 'BEAM TEST' });
  const L = model.levels[0];
  const interior = L.beams.filter((b) => b.interior);
  assert.equal(interior.length, 1, 'the beam along y = 0 is an edge beam, not an interior one');
  assert.equal(interior[0].along, 'y');
  const rule = applyColumnRule(L, model.spec, model.assumptions);
  const beamBars = rule.added.filter((it) => it.beam === interior[0].id);
  assert.equal(beamBars.length, 1, 'one group across the beam, none along it');
  const bar = beamBars[0];
  assert.equal(bar.dir, 'x', 'the bars run across a beam whose axis is along y');
  assert.ok(Math.abs(bar.a.y - bar.b.y) < 1 && Math.abs(bar.b.x - bar.a.x) >= 4000, `at least 4 m long: ${Math.round(Math.abs(bar.b.x - bar.a.x))}`);
  assert.ok(Math.min(bar.a.x, bar.b.x) <= 9000 - 150 - 1500 && Math.max(bar.a.x, bar.b.x) >= 9000 + 150 + 1500, 'at least 1.5 m past each face');
  assert.ok(bar.dist && Math.abs(bar.dist.q.y - bar.dist.p.y) <= 8000 + 1 && Math.abs(bar.dist.q.y - bar.dist.p.y) >= 7000, 'distributed along the beam, not beyond it');
  assert.ok(model.assumptions.some((a) => /beams cross the slab/.test(a.text)));
  assert.ok(L.edges.some((e) => e.beam), 'the beam along y = 0 makes that edge an edge beam');
});

test('office rule: a slab at another top-of-concrete level is a separate slab; the step is a free edge of both', async () => {
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const { prepareRamDesign, designAdditions } = await import('../shopdrawings/lib/design.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'ram-step-'));
  const ram = readRamConcept(await buildSyntheticCpt(dir, { step: true }));
  assert.deepEqual(ram.slab.tocs, [0, -300]);
  assert.equal(ram.slab.bodies.length, 2);
  const model = prepareRamDesign(ramToModel(ram, { levelName: 'STEP TEST', spec: { ramBands: 'none' } }), { levelName: 'STEP TEST' });
  assert.equal(model.levels.length, 2, 'two slabs');
  const [upper, lower] = model.levels;
  assert.equal(Math.round(lower.bbox.minX), 8000);
  assert.equal(Math.round(upper.bbox.maxX), 8000);
  assert.equal(lower.toc, -300);
  assert.ok(/T\.O\.C -300/.test(lower.name), lower.name);
  assert.ok(upper.edges.some((e) => Math.abs(e.a.x - 8000) < 1 && Math.abs(e.b.x - 8000) < 1), 'the step is an edge of the upper slab');
  assert.ok(lower.edges.some((e) => Math.abs(e.a.x - 8000) < 1 && Math.abs(e.b.x - 8000) < 1), 'and of the lower slab');
  assert.ok(!upper.jointEdges?.some((e) => Math.abs(e.a.x - 8000) < 1), 'the step is not a drawing joint');
  const adds = designAdditions(upper, model.spec);
  assert.ok(adds.items.some((it) => it.detail === 'D6' && Math.abs(it.a.x - 8000) < 1), 'perimeter U-bars along the step');
  assert.ok(model.assumptions.some((a) => /top-of-concrete levels/.test(a.text)));
});

test('the app edits (delete / lengthen / re-spec / add) apply to bars by id, plan.json carries the bars, and a custom frame DXF replaces the title block', async () => {
  const { readRamConcept, ramToModel } = await import('../shopdrawings/lib/ram-concept.mjs');
  const { prepareRamDesign, composeDesignPackage } = await import('../shopdrawings/lib/design.mjs');
  const { frameEntities } = await import('../shopdrawings/cli.mjs');
  const dir = mkdtempSync(join(tmpdir(), 'ram-edit-'));
  const cpt = await buildSyntheticCpt(dir);
  const ram = readRamConcept(cpt);
  const model0 = prepareRamDesign(ramToModel(ram, { levelName: 'EDIT TEST', spec: {} }), { levelName: 'EDIT TEST' });
  const pack0 = composeDesignPackage(model0, { prefix: 'T' });
  const plan = pack0.plan[0];
  assert.ok(plan.bars.length > 5 && plan.outline.length >= 4 && plan.columns.length === 5, 'plan.json: bars, outline, columns');
  const office = plan.bars.find((b) => b.kind === 'office' && b.face === 'T');
  const ramBar = plan.bars.find((b) => b.kind === 'ram');
  assert.ok(office && ramBar);
  const edits = [
    { op: 'delete', id: office.id },
    { op: 'length', id: ramBar.id, start: 500, end: 500 },
    { op: 'spec', id: ramBar.id, l1: 'T20-100 (B)' },
    { op: 'add', face: 'T', a: { x: 1000, y: 6000 }, b: { x: 5000, y: 6000 }, l1: 'T16-200 (T)' },
    { op: 'delete', id: 'NOPE:1,1-2,2' },
  ];
  const model1 = prepareRamDesign(ramToModel(ram, { levelName: 'EDIT TEST', spec: { edits } }), { levelName: 'EDIT TEST' });
  const pack1 = composeDesignPackage(model1, { prefix: 'T' });
  const plan1 = pack1.plan[0];
  assert.ok(!plan1.bars.some((b) => b.id === office.id), 'deleted bar gone');
  const rb = plan1.bars.find((b) => b.l1 === 'T20-100 (B)');
  assert.ok(rb && rb.edited, 're-specified bar kept with its new call-out');
  const len0 = Math.hypot(ramBar.b.x - ramBar.a.x, ramBar.b.y - ramBar.a.y), len1 = Math.hypot(rb.b.x - rb.a.x, rb.b.y - rb.a.y);
  assert.ok(Math.abs(len1 - len0 - 1000) < 2, `lengthened by 500 each end: ${len0} -> ${len1}`);
  assert.ok(plan1.bars.some((b) => b.l1 === 'T16-200 (T)' && b.zone === 'EDIT'), 'added bar');
  assert.ok(model1.assumptions.some((a) => /4 reinforcement edits .* 1 edits matched no bar/.test(a.text)), model1.assumptions.map((a) => a.text).join('\n'));
  // a custom frame: a rectangle and a title text with tokens, in paper mm
  const frameDxf = toDxf((() => { const c = new Canvas(); c.rect(0, 0, 841, 594, { layer: 'FRAME' }); c.text(650, 20, 'DRG <DRAWING_NO> REV <REV>', { layer: 'TITLE', h: 4 }); c.text(650, 30, '%PROJECT% - <CLIENT>', { layer: 'TITLE', h: 3 }); return c; })());
  const ents = frameEntities(frameDxf);
  assert.equal(ents.length, 3);
  const pack2 = composeDesignPackage(model0, { prefix: 'T', project: 'My Tower', client: 'ACME', frameEntities: ents, frame: { rightWidth: 200, keyplan: false } });
  const sheet = pack2.sheets[1];
  const texts = [];
  for (const e of sheet.root.blocks.get(sheet.blockName).entities || []) if (e.t === 'text') texts.push(e.str);
  assert.ok(texts.some((t) => t === `DRG ${sheet.drawingNo} REV 00`), `token substitution: ${texts.filter((t) => /DRG/.test(t)).join('|')}`);
  assert.ok(texts.some((t) => t === 'MY TOWER - ACME'));
  assert.ok(!texts.some((t) => t === 'KEY PLAN'), 'key plan switched off');
  assert.ok(!texts.some((t) => t === 'THE CLIENT'), 'the built-in title block gives way to the custom frame');
  assert.equal(sheet.sheet.L.title.w, 200, 'strip width from the frame options');
});
