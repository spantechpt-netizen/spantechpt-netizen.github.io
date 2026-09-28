#!/usr/bin/env node
/**
 * Reinforcement + PT cables shop-drawing generator.
 *
 *   node shopdrawings/cli.mjs --input <combined-structural.dxf> --out <dir> [options]
 *   node shopdrawings/cli.mjs --sample --out shopdrawings/samples/output
 *
 * Options
 *   --project "…"  --client "…"  --location "…"  --company "…"
 *   --prefix SPAN-SD  --rev 00  --date YYYY-MM-DD
 *   --prepared "…"  --checked "…"  --approved "…"
 *   --config file.json      project meta and spec overrides ({ meta: {...}, spec: {...}, layers: "path" })
 *   --layers file.json      layer standard (default: shopdrawings/layers.spantech.json)
 *   --level "1ST FLOOR"     level name (default: from the file name)
 *   --mode design           design drawings from the office's own RFT plan, or from a RAM Concept .cpt, + the General Details rules (default: shop)
 *   --no-svg                skip the SVG previews
 *
 * Output
 *   <out>/dxf/<DRAWING_NO>_<BLOCK>.dxf   one DXF per sheet (block + insert, xref-able)
 *   <out>/SHOP_DRAWINGS_PACKAGE.dxf      every sheet block in one file
 *   <out>/preview/*.svg                  browser previews
 *   <out>/schedules/*.csv                bar bending schedules
 *   <out>/model.json, REPORT.md          what was read, what was assumed
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseDxf } from './lib/dxf-reader.mjs';
import { fromLibredwgJson } from './lib/libredwg-json.mjs';
import { readRamConcept, ramToModel } from './lib/ram-concept.mjs';
import { execFileSync } from 'node:child_process';
import { basename, extname } from 'node:path';
import { extractModel, flatten } from './lib/extract.mjs';
import { composePackage } from './lib/sheets.mjs';
import { quantities } from './lib/quantities.mjs';
import { readReferencePlan, applyReference } from './lib/reference.mjs';
import { beamSchedule } from './lib/beam-strips.mjs';
import { punchingCheck } from './lib/punching.mjs';
import { extractDesign, prepareRamDesign, composeDesignPackage } from './lib/design.mjs';
import { toDxf } from './lib/dxf-writer.mjs';
import { toSvg } from './lib/svg-writer.mjs';
import * as R from './lib/rebar.mjs';

const here = dirname(fileURLToPath(import.meta.url));

export function parseArgs(argv) {
  const a = { svg: true };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith('--')) continue;
    const key = k.slice(2);
    if (key === 'no-svg') { a.svg = false; continue; }
    if (key === 'sample') { a.sample = true; continue; }
    a[key] = argv[++i];
  }
  return a;
}

/** Load a DXF, a LibreDWG JSON export, or a DWG (converted with `dwgread` when it is on PATH). */
export function loadDrawing(inputPath, inputText) {
  if (inputText != null) return parseDxf(inputText);
  const ext = extname(inputPath).toLowerCase();
  if (ext === '.json') return fromLibredwgJson(JSON.parse(readFileSync(inputPath, 'utf8')));
  if (ext === '.dwg') {
    const tool = process.env.DWGREAD || 'dwgread';
    const jsonPath = inputPath.replace(/\.dwg$/i, '.libredwg.json');
    try { execFileSync(tool, ['-O', 'json', '-o', jsonPath, inputPath], { stdio: 'ignore', maxBuffer: 1 << 30 }); }
    catch (e) { throw new Error(`Cannot convert DWG: ${tool} (LibreDWG) not found or failed. Export the drawing as DXF (DXFOUT) or JSON (dwgread -O json) first.`); }
    return fromLibredwgJson(JSON.parse(readFileSync(jsonPath, 'utf8')));
  }
  return parseDxf(readFileSync(inputPath, 'utf8'));
}

/** Level name guessed from the file name, e.g. S02D__FIRST_FLOOR_SLAB_G.A → "S02D FIRST FLOOR SLAB". */
export function levelNameFromFile(inputPath) {
  if (!inputPath) return null;
  const base = basename(inputPath).replace(/\.[^.]+$/, '').replace(/\.libredwg$/, '');
  return base.replace(/[_-]+/g, ' ').replace(/\bG\.?A\.?\b/i, '').replace(/\s+/g, ' ').trim().toUpperCase() || null;
}

export const DEFAULT_LAYER_STANDARD = join(here, 'layers.spantech.json');

export function loadLayerStandard(path = DEFAULT_LAYER_STANDARD) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

export function generate({ inputDxf, inputText, out, meta = {}, spec = {}, svg = true, levelNames, layerStandard, mode = 'shop' }) {
  meta = { layerStandard: layerStandard || loadLayerStandard(), ...meta, mode };
  // the office's own sheet frame: a DXF in paper mm whose texts carry <TOKENS> (see Sheet.customFrame)
  if (meta.frameDxf && existsSync(meta.frameDxf)) meta.frameEntities = frameEntities(readFileSync(meta.frameDxf, 'utf8'));
  let model;
  if (mode === 'design' && inputDxf && /\.cpt$/i.test(inputDxf)) {
    // design drawings straight from the RAM Concept model: its designed bands + the General Details rules
    const ram = readRamConcept(inputDxf);
    const levelName = (levelNames && levelNames[0]) || levelNameFromFile(inputDxf) || '1ST FLOOR';
    const raw = ramToModel(ram, { levelName, levelId: meta.levelId, spec });
    useReferencePlan(raw, ram, spec);
    for (const l of raw.levels) { l.beamSchedule = beamSchedule(ram, l); l.punchingCheck = punchingCheck(l, { ...raw.spec, ...spec, punching: { ...(raw.spec?.punching || {}), ...(spec.punching || {}) } }); }
    model = prepareRamDesign(raw, { levelName, spec, wallThickness: spec.wallThickness });
    const h = ram.project;
    meta = { project: [h.name, h.part].filter(Boolean).join(' - ') || meta.project, company: h.company || meta.company, revision: (h.revision || '').replace(/^rev\.?\s*/i, '') || meta.revision, ...meta };
  } else if (mode === 'design') {
    // design drawings: the office's own design plan + the General Details rules
    const dxf = loadDrawing(inputDxf, inputText);
    model = extractDesign(dxf, { spec, levelNames: levelNames || (inputDxf ? [levelNameFromFile(inputDxf)] : []) });
  } else if (inputDxf && /\.cpt$/i.test(inputDxf)) {
    const ram = readRamConcept(inputDxf);
    model = ramToModel(ram, { levelName: (levelNames && levelNames[0]) || levelNameFromFile(inputDxf) || '1ST FLOOR', levelId: meta.levelId, spec });
    useReferencePlan(model, ram, spec);
    for (const l of model.levels) { l.beamSchedule = beamSchedule(ram, l); l.punchingCheck = punchingCheck(l, { ...model.spec, ...spec, punching: { ...(model.spec?.punching || {}), ...(spec.punching || {}) } }); }
    const h = ram.project;
    meta = { project: [h.name, h.part].filter(Boolean).join(' - ') || meta.project, company: h.company || meta.company, revision: (h.revision || '').replace(/^rev\.?\s*/i, '') || meta.revision, ...meta };
  } else {
    const dxf = loadDrawing(inputDxf, inputText);
    model = extractModel(dxf, { spec, levelNames: levelNames || (inputDxf ? [levelNameFromFile(inputDxf)] : []) });
  }
  const pack = mode === 'design' ? composeDesignPackage(model, meta) : composePackage(model, meta);
  mkdirSync(join(out, 'dxf'), { recursive: true });
  mkdirSync(join(out, 'schedules'), { recursive: true });
  if (svg) mkdirSync(join(out, 'preview'), { recursive: true });
  const files = [];
  for (const s of pack.sheets) {
    const base = `${s.drawingNo}_${s.blockName}`;
    const dxfPath = join(out, 'dxf', `${base}.dxf`);
    writeFileSync(dxfPath, toDxf(s.root, { ltscale: s.scale / 4 }));
    files.push(dxfPath);
    if (svg) writeFileSync(join(out, 'preview', `${base}.svg`), toSvg(s.root, { width: 2400 }));
    if (s.rows && s.rows.length && s.key !== 'cables') {
      const cols = s.csvCols;
      const csv = [cols.map((c) => c.title.replace(/\n/g, ' ')).join(','), ...s.rows.map((r) => cols.map((c) => `"${String(r[c.key] ?? '').replace(/"/g, '""')}"`).join(','))].join('\n');
      writeFileSync(join(out, 'schedules', `${base}.csv`), csv + '\n');
    }
  }
  const maxScale = Math.max(...pack.sheets.map((s) => s.scale || 100));
  writeFileSync(join(out, mode === 'design' ? 'DESIGN_DRAWINGS_PACKAGE.dxf' : 'SHOP_DRAWINGS_PACKAGE.dxf'), toDxf(pack.pkg, { ltscale: maxScale / 4 }));
  writeFileSync(join(out, 'model.json'), JSON.stringify(serializable(model), null, 2));
  if (pack.plan) writeFileSync(join(out, 'plan.json'), JSON.stringify(pack.plan));
  const qty = quantities(model, pack);
  writeFileSync(join(out, 'quantities.json'), JSON.stringify(qty, null, 2));
  const punching = model.levels.map((l) => (l.punchingCheck ? { level: l.id, name: l.name, ...l.punchingCheck, overridden: l.punchingOverridden || [] } : null)).filter(Boolean);
  if (punching.length) writeFileSync(join(out, 'punching.json'), JSON.stringify(punching, null, 2));
  writeFileSync(join(out, 'REPORT.md'), report(model, pack));
  return { model, pack, files, quantities: qty, punching };
}

/**
 * The reference plan of the level (`spec.reference`: { file | text, use: { grid, columns, outline }, align: { mode:
 * 'auto' | 'point', dxf: {x, y}, ram: {x, y}, rot } }): the architect's grid, columns and slab edges replace the
 * RAM ones, matched on the columns or on the point given.
 */
function useReferencePlan(model, ram, spec) {
  const ref = spec && spec.reference;
  if (!ref || (!ref.file && !ref.text)) return;
  const text = ref.text || (existsSync(ref.file) ? readFileSync(ref.file, 'utf8') : null);
  if (!text) { model.findings.push(`Reference plan ${ref.file} not found; the RAM geometry is used.`); return; }
  const plan = readReferencePlan(text);
  applyReference(model, plan, { use: ref.use || {}, align: ref.align || null, ramColumns: ram.columns });
}

/** The entities of a frame DXF (paper mm, bottom-left origin), blocks exploded, ready for Sheet.customFrame. */
export function frameEntities(text) {
  const dxf = parseDxf(text);
  const ents = flatten(dxf);
  const k = 1; // a frame is drawn in paper millimetres
  return ents.filter((e) => ['LINE', 'LWPOLYLINE', 'CIRCLE', 'ARC', 'TEXT', 'MTEXT', 'ATTRIB', 'ATTDEF', 'SOLID', 'TRACE'].includes(e.type)).map((e) => (k === 1 ? e : { ...e, x: e.x * k, y: e.y * k, x2: e.x2 != null ? e.x2 * k : e.x2, y2: e.y2 != null ? e.y2 * k : e.y2, r: e.r != null ? e.r * k : e.r, height: e.height != null ? e.height * k : e.height, pts: e.pts ? e.pts.map((q) => ({ ...q, x: q.x * k, y: q.y * k })) : e.pts }));
}

function serializable(model) {
  return JSON.parse(JSON.stringify(model, (k, v) => (v instanceof Set ? [...v] : v)));
}

function report(model, pack) {
  const L = [];
  const design = pack.meta.mode === 'design';
  L.push(`# ${design ? 'Design drawing package' : 'Shop drawing package'} - ${pack.meta.project}`);
  L.push('');
  L.push(`Generated ${pack.meta.date} · rev ${pack.meta.revision} · ${pack.sheets.length} sheets`);
  L.push('');
  L.push(design ? '## What was read from the office design plan' : '## What was read from the structural drawings');
  L.push('');
  for (const f of model.findings) L.push(`- ${f}`);
  L.push(`- Code reference: ${model.code_reference || 'not stated'} (${model.spec.sources.code}); f'c ${model.spec.fc} MPa (${model.spec.sources.fc}); fy ${model.spec.fy} MPa (${model.spec.sources.fy}); cover ${model.spec.cover} mm (${model.spec.sources.cover}).`);
  for (const f of model.spec.found) L.push(`- Reinforcement note applied: ${f}`);
  L.push('');
  L.push('## Assumptions printed on the sheets');
  L.push('');
  for (const a of model.assumptions) L.push(`- ${a.level ? `[${a.level}] ` : ''}${a.text}`);
  L.push('');
  L.push('## Development and lap lengths applied (mm)');
  L.push('');
  L.push('| Ø | ld bottom | ld top | lap bottom | lap top | ldh |');
  L.push('|---|---|---|---|---|---|');
  for (const r of R.lengthTable(model.spec)) L.push(`| ${r.dia} | ${r.ld_bottom} | ${r.ld_top} | ${r.lap_bottom} | ${r.lap_top} | ${r.ldh} |`);
  L.push('');
  L.push('## Sheets');
  L.push('');
  L.push('| Drawing No | Title | Level | Block / Xref | Scale | Rebar (kg) |');
  L.push('|---|---|---|---|---|---|');
  for (const s of pack.sheets) L.push(`| ${s.drawingNo} | ${s.title} | ${s.level} | \`${s.blockName}\` | ${s.scale ? `1:${s.scale}` : 'NTS'} | ${s.weight ? Math.round(s.weight) : '-'} |`);
  const total = pack.sheets.reduce((s, x) => s + (x.weight || 0), 0);
  L.push('');
  L.push(design
    ? `Reinforcement added from the General Details: **${Math.round(total).toLocaleString('en-US')} kg** (the designer's own bars are kept as drawn and not scheduled here).`
    : `Total scheduled reinforcement: **${Math.round(total).toLocaleString('en-US')} kg** (cables excluded - template only).`);
  const checked = model.levels.filter((l) => l.punchingCheck && l.punchingCheck.columns.length);
  if (checked.length) {
    L.push('');
    L.push('## Indicative punching check (RAM keeps no punching result in the file - the RAM punching report governs)');
    L.push('');
    L.push('| Level | Column | Location | h | Trib. m² | wu kN/m² | Vu kN | vu MPa | phi.vc MPa | Ratio | Status |');
    L.push('|---|---|---|---|---|---|---|---|---|---|---|');
    for (const l of checked) for (const c of l.punchingCheck.columns) L.push(`| ${l.id} | ${c.id} | ${c.loc} | ${c.h} | ${c.trib_m2} | ${c.wu_kn_m2} | ${c.Vu_kn} | ${c.vu_mpa} | ${c.phi_vc_mpa} | ${c.ratio} | ${c.status}${c.ssr ? ' (SSR in RAM)' : ''}${c.ram_failed ? ' (FAILS IN RAM)' : ''}${(l.punchingOverridden || []).includes(c.id) ? ' (PS AT THE ENGINEER\'S RESPONSIBILITY)' : ''} |`);
    for (const l of checked) if (l.punchingCheck.flagged.length) L.push(`\n**${l.id}: columns to look at in the RAM punching report: ${l.punchingCheck.flagged.join(', ')}** (blocking: ${l.punchingCheck.blocking.join(', ') || 'none'}).`);
  }
  if (!design) {
    const checks = pack.sheets.flatMap((s) => s.checks.map((c) => ({ ...c, level: s.level })));
    const governed = checks.filter((c) => c.asProv < c.asReq);
    L.push('');
    L.push(`## Top bar As,min checks: ${checks.length} column-directions checked, ${governed.length} short`);
  }
  return L.join('\n') + '\n';
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const a = parseArgs(process.argv.slice(2));
  const out = resolve(a.out || 'shopdrawings-output');
  const input = a.sample ? join(here, 'samples', 'sample-structural-input.dxf') : a.input;
  if (!input || !existsSync(input)) {
    console.error('usage: node shopdrawings/cli.mjs --input <combined-structural.dxf> --out <dir> [--project "..."] [--config file.json]');
    process.exit(2);
  }
  let cfg = { meta: {}, spec: {} };
  if (a.config) cfg = { meta: {}, spec: {}, ...JSON.parse(readFileSync(a.config, 'utf8')) };
  const meta = { ...cfg.meta };
  for (const k of ['project', 'client', 'location', 'company', 'prefix', 'prepared', 'checked', 'approved', 'date']) if (a[k]) meta[k] = a[k];
  if (a.rev) meta.revision = a.rev;
  const t0 = Date.now();
  const layerStandard = loadLayerStandard(a.layers || cfg.layers || DEFAULT_LAYER_STANDARD);
  const { model, pack, files } = generate({ inputDxf: input, out, meta, spec: cfg.spec, svg: a.svg, layerStandard, levelNames: a.level ? [a.level] : undefined, mode: a.mode || cfg.mode || 'shop' });
  console.log(model.findings.join('\n'));
  console.log(`\n${pack.sheets.length} sheets → ${out}  (${files.length} DXF, ${Date.now() - t0} ms)`);
  for (const s of pack.sheets) console.log(`  ${s.drawingNo}  ${s.blockName.padEnd(44)} 1:${s.scale}  ${s.weight ? Math.round(s.weight) + ' kg' : ''}`);
  console.log(`\nAssumptions (${model.assumptions.length}) are printed on every sheet; see REPORT.md`);
}
