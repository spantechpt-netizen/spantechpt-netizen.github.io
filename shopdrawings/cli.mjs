#!/usr/bin/env node
/**
 * Reinforcement + PT cables shop-drawing generator.
 *
 *   node shopdrawings/cli.mjs --input <combined-structural.dxf> --out <dir> [options]
 *   node shopdrawings/cli.mjs --sample --out shopdrawings/samples/output
 *
 * Options
 *   --project "…"  --client "…"  --location "…"  --company "…"
 *   --prefix ST-SD  --rev 00  --date YYYY-MM-DD
 *   --prepared "…"  --checked "…"  --approved "…"
 *   --config file.json      project meta and spec overrides ({ meta: {...}, spec: {...}, layers: "path" })
 *   --layers file.json      layer standard (default: shopdrawings/layers.spantech.json)
 *   --level "1ST FLOOR"     level name (default: from the file name)
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
import { extractModel } from './lib/extract.mjs';
import { composePackage } from './lib/sheets.mjs';
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

export function generate({ inputDxf, inputText, out, meta = {}, spec = {}, svg = true, levelNames, layerStandard }) {
  meta = { layerStandard: layerStandard || loadLayerStandard(), ...meta };
  let model;
  if (inputDxf && /\.cpt$/i.test(inputDxf)) {
    const ram = readRamConcept(inputDxf);
    model = ramToModel(ram, { levelName: (levelNames && levelNames[0]) || levelNameFromFile(inputDxf) || '1ST FLOOR', spec });
    const h = ram.project;
    meta = { project: [h.name, h.part].filter(Boolean).join(' - ') || meta.project, company: h.company || meta.company, revision: (h.revision || '').replace(/^rev\.?\s*/i, '') || meta.revision, ...meta };
  } else {
    const dxf = loadDrawing(inputDxf, inputText);
    model = extractModel(dxf, { spec, levelNames: levelNames || (inputDxf ? [levelNameFromFile(inputDxf)] : []) });
  }
  const pack = composePackage(model, meta);
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
  writeFileSync(join(out, 'SHOP_DRAWINGS_PACKAGE.dxf'), toDxf(pack.pkg, { ltscale: maxScale / 4 }));
  writeFileSync(join(out, 'model.json'), JSON.stringify(serializable(model), null, 2));
  writeFileSync(join(out, 'REPORT.md'), report(model, pack));
  return { model, pack, files };
}

function serializable(model) {
  return JSON.parse(JSON.stringify(model, (k, v) => (v instanceof Set ? [...v] : v)));
}

function report(model, pack) {
  const L = [];
  L.push(`# Shop drawing package - ${pack.meta.project}`);
  L.push('');
  L.push(`Generated ${pack.meta.date} · rev ${pack.meta.revision} · ${pack.sheets.length} sheets`);
  L.push('');
  L.push('## What was read from the structural drawings');
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
  L.push(`Total scheduled reinforcement: **${Math.round(total).toLocaleString('en-US')} kg** (cables excluded - template only).`);
  const checks = pack.sheets.flatMap((s) => s.checks.map((c) => ({ ...c, level: s.level })));
  const governed = checks.filter((c) => c.asProv < c.asReq);
  L.push('');
  L.push(`## Top bar As,min checks: ${checks.length} column-directions checked, ${governed.length} short`);
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
  const { model, pack, files } = generate({ inputDxf: input, out, meta, spec: cfg.spec, svg: a.svg, layerStandard, levelNames: a.level ? [a.level] : undefined });
  console.log(model.findings.join('\n'));
  console.log(`\n${pack.sheets.length} sheets → ${out}  (${files.length} DXF, ${Date.now() - t0} ms)`);
  for (const s of pack.sheets) console.log(`  ${s.drawingNo}  ${s.blockName.padEnd(44)} 1:${s.scale}  ${s.weight ? Math.round(s.weight) + ' kg' : ''}`);
  console.log(`\nAssumptions (${model.assumptions.length}) are printed on every sheet; see REPORT.md`);
}
