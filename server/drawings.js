/**
 * Reinforcement drawings from RAM Concept — the service behind routes/drawings.js.
 *
 * A project is registered once with the data every title block carries; its
 * levels (or zones) are registered under it; a *run* takes one RAM Concept
 * (.cpt) or plan (.dxf) file for one level and produces the numbered package
 * with the shopdrawings generator. Files live under data/drawings/<project>/<run>/.
 */
import { createWriteStream } from 'node:fs';
import { mkdir, readdir, readFile, rm, stat, unlink, writeFile } from 'node:fs/promises';
import { Worker } from 'node:worker_threads';
import { basename, extname, join, resolve } from 'node:path';
import { ROOT } from './config.js';
import { getSetting, nextCounter } from './db.js';
import { badRequest } from './http.js';
import { zipEntries } from './zip.js';

export const DRAWINGS_ROOT = resolve(ROOT, process.env.DRAWINGS_DIR || './data/drawings');

/** 300 MB: a RAM Concept model of a whole floor is a few MB; a DWG exported as DXF can be far larger. */
export const MAX_SOURCE_BYTES = 300 * 1024 * 1024;

export const SOURCE_EXTENSIONS = ['.cpt', '.dxf'];
export const MODES = ['design', 'shop'];
export const RAM_BANDS = ['all', 'user', 'none'];
export const RUN_STATUS = ['draft', 'issued', 'superseded'];
/** The slab mesh option: a bottom mesh only, or a mesh on both faces. */
export const MESH_FACES = ['bottom', 'both'];
/** The engineer's decision on a run blocked by the punching check. */
export const PUNCHING_DECISIONS = ['thicken', 'bypass', 'ram_ok', 'clear'];
/** Where the beam bars come from: RAM's design strips, the office design (continuous-beam analysis), or the heavier of the two set by set. */
export const BEAM_DESIGN = ['ram', 'office', 'max'];
/** The engineer's decision on a run blocked by the beam check (a beam failing deflection / flexure / shear). */
export const BEAM_DECISIONS = ['deepen', 'bypass', 'ram_ok', 'clear'];
/** Project document sections: the original design files, the RAM models, the PT design drawings, the PT shop drawings. */
export const FILE_CATEGORIES = ['design', 'ram', 'pt_design', 'pt_shop'];
/** Sheet frame defaults (paper mm); see shopdrawings/lib/sheet.mjs DEFAULT_FRAME. */
export const FRAME_DEFAULTS = { size: 'A1', rightWidth: 185, bottomStrip: 125, titleH: 150, refsH: 52, keyH: 46, schedH: 140, keyplan: true, refs: true, schedule: true, details: true };

/** The submittal (transmittal) form: one template for the whole office, filled from the project and the runs. */
export const SUBMITTAL_DEFAULTS = {
  prefix: 'SPAN-SUB',
  title: 'DRAWING SUBMITTAL / TRANSMITTAL',
  title_ar: 'طلب اعتماد مخططات',
  intro: 'We are pleased to submit the following drawings for your review and approval. Kindly return one signed copy of this form with your comments.',
  purposes: ['approval', 'information', 'resubmission', 'as_built'],
  responses: ['APPROVED', 'APPROVED AS NOTED', 'REVISE AND RESUBMIT', 'REJECTED'],
  signatures: ['PREPARED BY', 'CHECKED BY', 'APPROVED BY'],
  footer: 'This submittal is issued under the office quality procedure; drawings are identified by their number and revision as printed in the title block. A revised drawing is re-submitted under a new submittal number that names the superseded revision.',
  contact: '',
};
export const SUBMITTAL_STATUS = ['draft', 'submitted', 'approved', 'approved_as_noted', 'resubmit', 'rejected', 'withdrawn'];
export const SUBMITTAL_PURPOSES = ['approval', 'information', 'resubmission', 'as_built'];
/** Office unit rates for the cost study (one currency). */
export const RATE_DEFAULTS = { currency: 'SAR', steel_per_ton: 3200, rebar_labour_per_ton: 350, concrete_per_m3: 280, formwork_per_m2: 45, strand_per_kg: 9.5, anchor_live: 45, anchor_dead: 25, duct_per_m: 6, pt_labour_per_m2: 18, markup_pct: 15, vat_pct: 15 };

/** Office defaults behind the "Drawings" settings tab. */
export const DRAWING_DEFAULTS = {
  project_prefix: 'P',
  design_prefix: 'SPAN-DD',
  shop_prefix: 'SPAN-SD',
  company: 'SPAN TECH CONTRACTING',
  company_line: 'POST-TENSIONED SLABS · KSA · EGYPT · QATAR',
  prepared: 'SPAN TECH DESIGN OFFICE',
  checked: '',
  approved: '',
  status_design: 'DESIGN DRAWING - FOR REVIEW',
  status_shop: 'SHOP DRAWING - FOR CONSULTANT APPROVAL',
  default_mode: 'design',
  ram_bands: 'all',
  mesh: 'bottom',
  beam_design: 'ram',
  spec: {},
  frame: FRAME_DEFAULTS,
  frame_dxf: null,
  submittal: SUBMITTAL_DEFAULTS,
  rates: RATE_DEFAULTS,
};

export function drawingSettings() {
  const stored = getSetting('drawings', {}) || {};
  return { ...DRAWING_DEFAULTS, ...stored, spec: { ...(DRAWING_DEFAULTS.spec || {}), ...(stored.spec || {}) }, frame: { ...FRAME_DEFAULTS, ...(stored.frame || {}) }, submittal: { ...SUBMITTAL_DEFAULTS, ...(stored.submittal || {}) }, rates: { ...RATE_DEFAULTS, ...(stored.rates || {}) } };
}

/** Where the office's own frame DXF is kept once uploaded. */
export const framePath = () => resolve(join(DRAWINGS_ROOT, 'frame.dxf'));

/** A project document on disk. */
export function projectFile(projectId, stored) {
  const root = resolve(join(projectDir(projectId), 'files'));
  const target = resolve(join(root, basename(String(stored || ''))));
  if (!target.startsWith(root + '/') && !target.startsWith(root + '\\')) throw badRequest('Bad file path', 'مسار ملف غير صالح');
  return target;
}

/** The reference plan (DXF) of a level, kept next to the project's files. */
export function referencePath(projectId, levelId) {
  return resolve(join(projectDir(projectId), 'ref', `${Number(levelId)}.dxf`));
}

/** P26-001, P26-002 … — one sequence per year, so the code says when the project was registered. */
export function nextProjectCode(settings = drawingSettings()) {
  const year = new Date().getFullYear();
  const yy = String(year).slice(-2);
  const n = nextCounter(`drawing_projects:${year}`);
  return `${settings.project_prefix || 'P'}${yy}-${String(n).padStart(3, '0')}`;
}

/** Level codes go into drawing numbers, so they are kept to letters, digits and dashes. */
export function normaliseCode(value, field = 'code') {
  const text = String(value ?? '').trim().toUpperCase().replace(/\s+/g, '-').replace(/[^A-Z0-9-]/g, '');
  if (!text) throw badRequest(`${field}: is required`, `${field}: حقل مطلوب`, { field });
  if (text.length > 12) throw badRequest(`${field}: at most 12 characters`, `${field}: 12 حرف على الأكثر`, { field });
  return text;
}

export function projectDir(projectId) {
  return resolve(join(DRAWINGS_ROOT, String(Number(projectId))));
}

export function runDir(projectId, runId) {
  return resolve(join(projectDir(projectId), String(Number(runId))));
}

/** A path inside a run folder; refuses anything that climbs out of it. */
export function runFile(projectId, runId, ...parts) {
  const root = runDir(projectId, runId);
  const target = resolve(join(root, ...parts.map((p) => basename(String(p || '')))));
  if (target !== root && !target.startsWith(root + '/') && !target.startsWith(root + '\\')) {
    throw badRequest('Bad file path', 'مسار ملف غير صالح');
  }
  return target;
}

/** Streams the uploaded model file to disk, stopping the moment it goes over the limit. */
export async function saveSource(req, dir, originalName) {
  const ext = extname(String(originalName || '')).toLowerCase();
  if (!SOURCE_EXTENSIONS.includes(ext)) {
    throw badRequest(
      `Unsupported file "${originalName || ''}". Upload the RAM Concept model (.cpt) or the plan as DXF.`,
      `الملف "${originalName || ''}" مش مدعوم. ارفع موديل الرام (.cpt) أو المسقط بصيغة DXF.`,
    );
  }
  return saveUpload(req, dir, `source${ext}`, ext);
}

/** Any project document (DWG, PDF, RAM model, spreadsheet ...) streamed to `dir/<fileName>`. */
export async function saveUpload(req, dir, fileName, ext) {
  const declared = Number(req.headers['content-length'] || 0);
  if (declared > MAX_SOURCE_BYTES) {
    throw badRequest(
      `That file is ${(declared / 1024 / 1024).toFixed(1)} MB; the limit is ${MAX_SOURCE_BYTES / 1024 / 1024} MB.`,
      `الملف ${(declared / 1024 / 1024).toFixed(1)} ميجا، والحد الأقصى ${MAX_SOURCE_BYTES / 1024 / 1024} ميجا.`,
    );
  }

  await mkdir(dir, { recursive: true });
  const target = join(dir, fileName);
  const written = await new Promise((resolvePromise, reject) => {
    const out = createWriteStream(target);
    let bytes = 0;
    let failed = false;
    const fail = (error) => {
      if (failed) return;
      failed = true;
      req.unpipe?.(out);
      out.destroy();
      unlink(target).catch(() => {});
      reject(error);
    };
    req.on('data', (chunk) => {
      bytes += chunk.length;
      if (bytes > MAX_SOURCE_BYTES && !failed) {
        fail(badRequest(`That file is over the ${MAX_SOURCE_BYTES / 1024 / 1024} MB limit.`, `الملف أكبر من الحد الأقصى ${MAX_SOURCE_BYTES / 1024 / 1024} ميجا.`));
      }
    });
    req.on('error', fail);
    out.on('error', fail);
    out.on('finish', () => { if (!failed) resolvePromise(bytes); });
    req.pipe(out);
  });
  if (!written) {
    await unlink(target).catch(() => {});
    throw badRequest('The file was empty.', 'الملف فاضي.');
  }
  return { file: fileName, ext, bytes: written };
}

/** The title-block data of one run, assembled from the settings, the project and the level. */
export function runMeta({ settings, project, level, mode, revision, date, user }) {
  const prefixBase = mode === 'shop' ? settings.shop_prefix : settings.design_prefix;
  // the engineer running the program signs the drawings: PREPARED / DESIGNED BY carries the logged-in user's name
  const designer = user && user.name ? String(user.name) : '';
  return {
    designer,
    preparedInitials: designer ? designer.split(/\s+/).filter(Boolean).map((w) => w[0]).join('').toUpperCase().slice(0, 4) : '',
    prefix: `${prefixBase}-${project.code}`,
    project: project.name,
    projectCode: project.code,
    client: project.client || '',
    engineer: project.consultant || '',
    contractor: project.contractor || '',
    location: project.location || '',
    company: settings.company,
    company_line: settings.company_line,
    prepared: designer || project.prepared || settings.prepared || '',
    checked: project.checked || settings.checked || '',
    approved: project.approved || settings.approved || '',
    status: mode === 'shop' ? settings.status_shop : settings.status_design,
    revision,
    date: date || new Date().toISOString().slice(0, 10),
    levelId: level.code,
    // the sheet frame: the office's strip sizes / boxes, and its own frame DXF when one was uploaded
    frame: settings.frame,
    frameDxf: settings.frame_dxf ? framePath() : null,
  };
}

/** The level name printed on the sheets: "BASEMENT CEILING" or "1ST FLOOR - ZONE A". */
export const levelTitle = (level) => [level.name, level.zone].filter(Boolean).join(' - ').toUpperCase();

/** Generates one package in a worker thread and resolves with its summary. */
export function runGeneration({ input, out, meta, spec, levelNames, mode }) {
  return new Promise((resolvePromise, reject) => {
    const worker = new Worker(new URL('./drawings-worker.js', import.meta.url), {
      workerData: { input, out, meta, spec, levelNames, mode },
    });
    let settled = false;
    worker.once('message', (message) => {
      settled = true;
      if (message.ok) resolvePromise(message);
      else reject(new Error(message.error));
    });
    worker.once('error', (error) => { if (!settled) { settled = true; reject(error); } });
    worker.once('exit', (code) => {
      if (!settled) { settled = true; reject(new Error(`generator exited with code ${code}`)); }
    });
  });
}

/** Zips a finished run's output folder: dxf/, preview/, schedules/, the package DXF, model.json and REPORT.md. */
export async function zipRun(outDir, folderName) {
  const entries = [];
  const walk = async (dir, rel) => {
    for (const name of (await readdir(dir)).sort()) {
      const full = join(dir, name);
      const info = await stat(full);
      if (info.isDirectory()) await walk(full, `${rel}/${name}`);
      else entries.push({ name: `${rel}/${name}`, data: await readFile(full) });
    }
  };
  await walk(outDir, folderName);
  return zipEntries(entries);
}

export async function writeRunZip(outDir, zipPath, folderName) {
  const buf = await zipRun(outDir, folderName);
  await writeFile(zipPath, buf);
  return buf.length;
}

export async function removeRunFiles(projectId, runId) {
  await rm(runDir(projectId, runId), { recursive: true, force: true });
}

export async function removeProjectFiles(projectId) {
  await rm(projectDir(projectId), { recursive: true, force: true });
}
