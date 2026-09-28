/**
 * Reinforcement drawings module: projects, levels, and generation runs.
 *
 *   GET    /api/drawings/projects                 list (q)
 *   POST   /api/drawings/projects                 register a project (code auto-numbered)
 *   GET    /api/drawings/projects/:id             project + levels + runs
 *   PATCH  /api/drawings/projects/:id
 *   DELETE /api/drawings/projects/:id             removes its files too
 *   POST   /api/drawings/projects/:id/levels
 *   PATCH  /api/drawings/levels/:id
 *   DELETE /api/drawings/levels/:id
 *   POST   /api/drawings/levels/:id/runs?name=&mode=&ram_bands=&revision=   file as raw body → generates
 *   GET    /api/drawings/runs/:id                 sheets, assumptions, findings, report
 *   GET    /api/drawings/runs/:id/zip             the whole package as one zip
 *   GET    /api/drawings/runs/:id/files/:kind/:name   kind = dxf | preview | schedules
*   DELETE /api/drawings/runs/:id
 *   PATCH  /api/drawings/runs/:id                 notes / status (issued supersedes the earlier issued run of the level)
 *   GET    /api/drawings/runs/:id/plan            the bars of the run for the editor (plan.json)
 *   POST   /api/drawings/runs/:id/regenerate      a new run from the same model with the level's edits
 *   PUT    /api/drawings/levels/:id/edits         the level's reinforcement edits
 *   POST   /api/drawings/projects/:id/files?category=&name=&level_id=   a project document (raw body)
 *   GET    /api/drawings/files/:id  PATCH  DELETE
 *   GET/POST/DELETE /api/drawings/frame           the office's own sheet frame (DXF)
 *   POST   /api/drawings/runs/:id/beam-strips     rewrites the run's model with one design strip per beam span (+ splitters) for RAM
 *   GET    /api/drawings/runs/:id/beam-strips     downloads that model (.cpt) to calculate in RAM and upload as the next run
 *   GET    /api/drawings/runs/:id/quantities      the take-off of one run (steel, concrete, cables)
 *   GET    /api/drawings/projects/:id/quantities  the take-off of the project: the current run of every level
 *   GET    /api/drawings/projects/:id/cost        the cost study: the take-off priced with the office rates
 *   POST/PATCH/DELETE /api/drawings/levels/:id/reference   the level's reference plan (the architect's DXF) and how it is aligned
 *   GET/POST /api/drawings/projects/:id/submittals   submittal request forms from the runs picked
 *   GET/PATCH/DELETE /api/drawings/submittals/:id  ;  GET /api/drawings/submittals/:id/form (printable HTML)
 */
import { createReadStream } from 'node:fs';
import { stat, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { copyFile, mkdir, unlink } from 'node:fs/promises';
import { extname, basename, dirname } from 'node:path';
import { all, get, insert, update, run as runSql, nextCounter, audit, transaction, getSetting, setSetting } from '../db.js';
import { requirePermission } from '../auth.js';
import { badRequest, notFound, conflict } from '../http.js';
import { str, int, oneOf, jsonField, COUNTRIES } from '../validate.js';
import {
  drawingSettings, nextProjectCode, normaliseCode, runDir, runFile, saveSource, saveUpload, runMeta, levelTitle,
  runGeneration, writeRunZip, removeRunFiles, removeProjectFiles, MODES, RAM_BANDS, RUN_STATUS, MESH_FACES, PUNCHING_DECISIONS, FILE_CATEGORIES,
  framePath, projectFile, projectDir, referencePath, SUBMITTAL_STATUS, SUBMITTAL_PURPOSES,
} from '../drawings.js';
import { submittalCode, submittalItems, submittalHtml } from '../submittals.js';
import { costStudy } from '../../shopdrawings/lib/quantities.mjs';
import { blockingAfter } from '../../shopdrawings/lib/punching.mjs';

const PROJECT_COLUMNS = `p.*, u.name AS owner_name, u.name_ar AS owner_name_ar,
  (SELECT COUNT(*) FROM drawing_levels l WHERE l.project_id = p.id) AS level_count,
  (SELECT COUNT(*) FROM drawing_runs r WHERE r.project_id = p.id AND r.status NOT IN ('failed', 'running')) AS run_count,
  (SELECT MAX(r.created_at) FROM drawing_runs r WHERE r.project_id = p.id AND r.status NOT IN ('failed', 'running')) AS last_run_at`;

function loadProject(id) {
  const row = get(`SELECT ${PROJECT_COLUMNS} FROM drawing_projects p LEFT JOIN users u ON u.id = p.owner_id WHERE p.id = ?`, id);
  if (!row) throw notFound('Project not found', 'المشروع مش موجود');
  return row;
}

function loadLevel(id) {
  const row = get('SELECT * FROM drawing_levels WHERE id = ?', id);
  if (!row) throw notFound('Level not found', 'الدور مش موجود');
  return row;
}

const RUN_COLUMNS = `r.*, l.code AS level_code, l.name AS level_name, l.zone AS level_zone,
  u.name AS created_by_name, u.name_ar AS created_by_name_ar`;

function loadRun(id) {
  const row = get(`SELECT ${RUN_COLUMNS} FROM drawing_runs r JOIN drawing_levels l ON l.id = r.level_id LEFT JOIN users u ON u.id = r.created_by WHERE r.id = ?`, id);
  if (!row) throw notFound('Run not found', 'الإصدار مش موجود');
  return row;
}

const parseJson = (text, fallback) => { try { return text ? JSON.parse(text) : fallback; } catch { return fallback; } };

function publicRun(row, { withReport = false } = {}) {
  const out = {
    ...row,
    sheets: parseJson(row.sheets_json, []),
    assumptions: parseJson(row.assumptions_json, []),
    findings: parseJson(row.findings_json, []),
  };
  out.edits = parseJson(row.edits_json, []);
  out.quantities = parseJson(row.quantities_json, null);
  out.beams = parseJson(row.beams_json, []);
  out.beam_strips = parseJson(row.beam_strips_json, null);
  out.punching = parseJson(row.punching_json, null);
  delete out.sheets_json; delete out.assumptions_json; delete out.findings_json; delete out.edits_json; delete out.quantities_json; delete out.beams_json; delete out.beam_strips_json; delete out.punching_json;
  if (!withReport) delete out.report_md;
  return out;
}

function loadFile(id) {
  const row = get('SELECT f.*, u.name AS uploaded_by_name, u.name_ar AS uploaded_by_name_ar, l.code AS level_code FROM drawing_files f LEFT JOIN users u ON u.id = f.uploaded_by LEFT JOIN drawing_levels l ON l.id = f.level_id WHERE f.id = ?', id);
  if (!row) throw notFound('File not found', 'الملف مش موجود');
  return row;
}

const EDIT_OPS = ['delete', 'length', 'spec', 'add'];
/** Keeps only well-formed edits: an op the generator knows, an id (or two points for an add). */
function cleanEdits(input) {
  if (!Array.isArray(input)) throw badRequest('edits must be a list', 'التعديلات لازم تكون قائمة');
  const out = [];
  for (const e of input.slice(0, 5000)) {
    if (!e || !EDIT_OPS.includes(e.op)) continue;
    const item = { op: e.op };
    if (e.level) item.level = String(e.level).slice(0, 20);
    if (e.op === 'add') {
      const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);
      const a = e.a && { x: num(e.a.x), y: num(e.a.y) }, b = e.b && { x: num(e.b.x), y: num(e.b.y) };
      if (!a || !b || a.x == null || a.y == null || b.x == null || b.y == null) continue;
      item.a = a; item.b = b; item.face = ['T', 'B', 'TB'].includes(e.face) ? e.face : 'T'; item.l1 = String(e.l1 || 'T12-150 (T)').slice(0, 40);
    } else {
      if (!e.id || typeof e.id !== 'string') continue;
      item.id = e.id.slice(0, 80);
      if (e.op === 'length') { item.start = Math.round(Number(e.start) || 0); item.end = Math.round(Number(e.end) || 0); }
      if (e.op === 'spec') { if (!e.l1) continue; item.l1 = String(e.l1).slice(0, 40); }
    }
    out.push(item);
  }
  return out;
}

function publicProject(row) {
  const out = { ...row, spec: parseJson(row.spec_json, {}) };
  delete out.spec_json;
  return out;
}

function projectFields(body, { partial = false } = {}) {
  return {
    name: str(body.name, 'name', { required: !partial, max: 200, fallback: undefined }),
    name_ar: str(body.name_ar, 'name_ar', { max: 200, fallback: undefined }),
    client: str(body.client, 'client', { max: 200, fallback: undefined }),
    consultant: str(body.consultant, 'consultant', { max: 200, fallback: undefined }),
    contractor: str(body.contractor, 'contractor', { max: 200, fallback: undefined }),
    location: str(body.location, 'location', { max: 200, fallback: undefined }),
    country: body.country === undefined ? undefined : (body.country ? oneOf(body.country, 'country', COUNTRIES) : null),
    customer_id: body.customer_id === undefined ? undefined : int(body.customer_id, 'customer_id', { min: 1, fallback: null }),
    prepared: str(body.prepared, 'prepared', { max: 120, fallback: undefined }),
    checked: str(body.checked, 'checked', { max: 120, fallback: undefined }),
    approved: str(body.approved, 'approved', { max: 120, fallback: undefined }),
    default_mode: oneOf(body.default_mode, 'default_mode', MODES, { fallback: partial ? undefined : 'design' }),
    ram_bands: oneOf(body.ram_bands, 'ram_bands', RAM_BANDS, { fallback: partial ? undefined : 'all' }),
    mesh: oneOf(body.mesh, 'mesh', MESH_FACES, { fallback: partial ? undefined : 'bottom' }),
    spec_json: body.spec === undefined ? undefined : JSON.stringify(jsonField(body.spec, 'spec', {}) || {}),
    notes: str(body.notes, 'notes', { max: 4000, fallback: undefined }),
  };
}

function levelFields(body, { partial = false } = {}) {
  return {
    code: body.code === undefined && partial ? undefined : normaliseCode(body.code),
    name: str(body.name, 'name', { required: !partial, max: 120, fallback: undefined }),
    zone: str(body.zone, 'zone', { max: 80, fallback: undefined }),
    sort_order: int(body.sort_order, 'sort_order', { min: 0, max: 999, fallback: partial ? undefined : 0 }),
    wall_thickness: body.wall_thickness === undefined ? undefined : int(body.wall_thickness, 'wall_thickness', { min: 100, max: 2000, fallback: null }),
    notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }),
  };
}

/** "A/1, B/3 C4" → ['A/1', 'B/3', 'C4'] (the column ids as printed on the framing sheet). */
const columnList = (v) => (Array.isArray(v) ? v : String(v || '').split(/[,;\s]+/)).map((x) => String(x).trim().toUpperCase()).filter(Boolean).slice(0, 500);

/** The level's punching record: the columns the engineer reports failing in RAM, and the decision taken on the last blocked run. */
function levelPunching(level) { return parseJson(level.punching_json, {}) || {}; }

const CONTENT_TYPES = { dxf: 'application/dxf', preview: 'image/svg+xml', schedules: 'text/csv; charset=utf-8', root: 'application/octet-stream' };

async function sendFile(res, path, contentType, downloadName) {
  let info;
  try { info = await stat(path); } catch { throw notFound('File not found', 'الملف مش موجود'); }
  if (!info.isFile()) throw notFound('File not found', 'الملف مش موجود');
  res.writeHead(200, {
    'content-type': contentType,
    'content-length': info.size,
    'cache-control': 'private, max-age=0',
    'x-content-type-options': 'nosniff',
    ...(downloadName ? { 'content-disposition': `attachment; filename="${downloadName.replace(/["\\]/g, '')}"` } : {}),
  });
  await new Promise((resolvePromise, reject) => {
    const stream = createReadStream(path);
    stream.on('error', reject);
    stream.on('end', resolvePromise);
    stream.pipe(res);
  });
}

const SUBMITTAL_COLUMNS = 's.*, u.name AS created_by_name, u.name_ar AS created_by_name_ar';
function loadSubmittal(id) {
  const row = get(`SELECT ${SUBMITTAL_COLUMNS} FROM drawing_submittals s LEFT JOIN users u ON u.id = s.created_by WHERE s.id = ?`, id);
  if (!row) throw notFound('Submittal not found', 'طلب الاعتماد مش موجود');
  return row;
}
function publicSubmittal(row) {
  const out = { ...row, items: parseJson(row.items_json, []) };
  delete out.items_json;
  return out;
}

/**
 * The current run of every level of a project: the issued run of the level (the project's default drawing type
 * first), else its latest draft. The take-off of the project is the take-off of those runs.
 */
function currentRuns(project) {
  const runs = all(`SELECT ${RUN_COLUMNS} FROM drawing_runs r JOIN drawing_levels l ON l.id = r.level_id LEFT JOIN users u ON u.id = r.created_by WHERE r.project_id = ? AND r.status NOT IN ('failed', 'running') ORDER BY r.serial DESC`, project.id).map((r) => publicRun(r));
  const levels = all('SELECT * FROM drawing_levels WHERE project_id = ? ORDER BY sort_order, id', project.id);
  const picked = [];
  for (const level of levels) {
    const mine = runs.filter((r) => r.level_id === level.id && r.quantities);
    const rank = (r) => (r.status === 'issued' ? 2 : r.status === 'draft' ? 1 : 0) * 10 + (r.mode === project.default_mode ? 1 : 0);
    const best = mine.sort((a, b) => rank(b) - rank(a) || b.serial - a.serial)[0];
    if (best) picked.push({ level, run: best });
  }
  return picked;
}

/** The take-off of a project: the levels of its current runs, summed. */
function projectQuantities(project) {
  const picked = currentRuns(project);
  const levels = [];
  for (const { level, run } of picked) for (const l of run.quantities.levels || []) levels.push({ ...l, level_code: level.code, level_name: level.name, run_id: run.id, run_serial: run.serial, revision: run.revision, mode: run.mode, run_status: run.status });
  const r1 = (v) => Math.round(v * 10) / 10;
  const sum = (get) => r1(levels.reduce((s, l) => s + (get(l) || 0), 0));
  const byDia = {};
  for (const l of levels) for (const d of l.steel.byDia || []) { byDia[d.dia] = byDia[d.dia] || { dia: d.dia, total_m: 0, kg: 0, count: 0 }; byDia[d.dia].total_m += d.total_m; byDia[d.dia].kg += d.kg; byDia[d.dia].count += d.count; }
  const pt = levels.filter((l) => l.cables);
  const totals = {
    steel: { kg: sum((l) => l.steel.kg), top_kg: sum((l) => l.steel.top_kg), bottom_kg: sum((l) => l.steel.bottom_kg), other_kg: sum((l) => l.steel.other_kg), mesh_kg: sum((l) => l.steel.mesh_kg), byDia: Object.values(byDia).sort((a, b) => a.dia - b.dia).map((d) => ({ ...d, total_m: r1(d.total_m), kg: r1(d.kg) })) },
    concrete: { gross_area_m2: sum((l) => l.concrete.gross_area_m2), openings_m2: sum((l) => l.concrete.openings_m2), net_area_m2: sum((l) => l.concrete.net_area_m2), slab_m3: sum((l) => l.concrete.slab_m3), drops_m3: sum((l) => l.concrete.drops_m3), beams_m3: sum((l) => l.concrete.beams_m3), total_m3: sum((l) => l.concrete.total_m3), formwork_m2: sum((l) => l.concrete.formwork_m2), edge_formwork_m2: sum((l) => l.concrete.edge_formwork_m2) },
    cables: pt.length ? { tendons: pt.reduce((s, l) => s + l.cables.tendons, 0), strands: pt.reduce((s, l) => s + l.cables.strands, 0), tendon_m: sum((l) => l.cables?.tendon_m), strand_m: sum((l) => l.cables?.strand_m), cutting_m: sum((l) => l.cables?.cutting_m), kg: sum((l) => l.cables?.kg), live_ends: pt.reduce((s, l) => s + l.cables.live_ends, 0), dead_ends: pt.reduce((s, l) => s + l.cables.dead_ends, 0), duct_small_m: sum((l) => l.cables?.duct_small_m), duct_large_m: sum((l) => l.cables?.duct_large_m) } : null,
  };
  const net = totals.concrete.net_area_m2;
  totals.steel.kg_per_m2 = net ? Math.round((totals.steel.kg / net) * 100) / 100 : null;
  if (totals.cables) { totals.cables.kg_per_m2 = net ? Math.round((totals.cables.kg / net) * 100) / 100 : null; totals.cables.strand_m_per_m2 = net ? Math.round((totals.cables.strand_m / net) * 100) / 100 : null; }
  return { levels, totals, runs: picked.map(({ level, run }) => ({ level_id: level.id, level_code: level.code, run_id: run.id, serial: run.serial, revision: run.revision, mode: run.mode, status: run.status })) };
}

export function register(router) {
  // ------------------------------------------------------------- projects
  router.get('/api/drawings/projects', ({ query, user }) => {
    requirePermission(user, 'drawings.view');
    const where = [];
    const params = [];
    if (query.q) {
      where.push('(p.name LIKE ? OR p.name_ar LIKE ? OR p.code LIKE ? OR p.client LIKE ? OR p.consultant LIKE ? OR p.location LIKE ?)');
      for (let i = 0; i < 6; i++) params.push(`%${query.q}%`);
    }
    const rows = all(
      `SELECT ${PROJECT_COLUMNS} FROM drawing_projects p LEFT JOIN users u ON u.id = p.owner_id
       ${where.length ? 'WHERE ' + where.join(' AND ') : ''} ORDER BY p.created_at DESC LIMIT 500`,
      ...params,
    );
    return { projects: rows.map(publicProject), total: rows.length, settings: drawingSettings() };
  });

  router.post('/api/drawings/projects', ({ body, user }) => {
    requirePermission(user, 'drawings.create');
    const fields = projectFields(body);
    const settings = drawingSettings();
    const id = transaction(() => {
      const code = body.code ? normaliseCode(body.code) : nextProjectCode(settings);
      if (get('SELECT id FROM drawing_projects WHERE code = ?', code)) {
        throw conflict(`A project with code ${code} already exists`, `فيه مشروع بنفس الكود ${code}`);
      }
      return insert('drawing_projects', { ...fields, code, owner_id: user.id });
    });
    // levels can be registered with the project in one go
    if (Array.isArray(body.levels)) {
      body.levels.forEach((level, i) => {
        if (!level || !level.code || !level.name) return;
        insert('drawing_levels', { ...levelFields({ ...level, sort_order: level.sort_order ?? i }), project_id: id });
      });
    }
    audit(user.id, 'drawing_project', id, 'create', { code: loadProject(id).code });
    return { project: publicProject(loadProject(id)), levels: all('SELECT * FROM drawing_levels WHERE project_id = ? ORDER BY sort_order, id', id) };
  });

  router.get('/api/drawings/projects/:id', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const project = loadProject(params.id);
    const levels = all(
      `SELECT l.*,
         (SELECT COUNT(*) FROM drawing_runs r WHERE r.level_id = l.id AND r.status NOT IN ('failed', 'running')) AS run_count,
         (SELECT MAX(r.revision) FROM drawing_runs r WHERE r.level_id = l.id AND r.status NOT IN ('failed', 'running')) AS last_revision,
         (SELECT MAX(r.created_at) FROM drawing_runs r WHERE r.level_id = l.id AND r.status NOT IN ('failed', 'running')) AS last_run_at
       FROM drawing_levels l WHERE l.project_id = ? ORDER BY l.sort_order, l.id`,
      project.id,
    );
    const runs = all(
      `SELECT ${RUN_COLUMNS} FROM drawing_runs r JOIN drawing_levels l ON l.id = r.level_id LEFT JOIN users u ON u.id = r.created_by
       WHERE r.project_id = ? ORDER BY r.serial DESC`,
      project.id,
    ).map((r) => publicRun(r));
    const files = all(
      `SELECT f.*, u.name AS uploaded_by_name, u.name_ar AS uploaded_by_name_ar, l.code AS level_code
       FROM drawing_files f LEFT JOIN users u ON u.id = f.uploaded_by LEFT JOIN drawing_levels l ON l.id = f.level_id
       WHERE f.project_id = ? ORDER BY f.category, f.created_at DESC`,
      project.id,
    );
    for (const l of levels) { l.edits = parseJson(l.edits_json, []); l.reference = l.ref_file ? { name: l.ref_name, ...parseJson(l.ref_json, {}) } : null; l.punching = levelPunching(l); delete l.ref_json; delete l.punching_json; }
    const submittals = all(`SELECT ${SUBMITTAL_COLUMNS} FROM drawing_submittals s LEFT JOIN users u ON u.id = s.created_by WHERE s.project_id = ? ORDER BY s.serial DESC`, project.id).map(publicSubmittal);
    return { project: publicProject(project), levels, runs, files, submittals, settings: drawingSettings() };
  });

  router.patch('/api/drawings/projects/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const project = loadProject(params.id);
    const fields = projectFields(body, { partial: true });
    if (body.code !== undefined) {
      const code = normaliseCode(body.code);
      const clash = get('SELECT id FROM drawing_projects WHERE code = ? AND id <> ?', code, project.id);
      if (clash) throw conflict(`A project with code ${code} already exists`, `فيه مشروع بنفس الكود ${code}`);
      fields.code = code;
    }
    update('drawing_projects', project.id, fields);
    audit(user.id, 'drawing_project', project.id, 'update');
    return { project: publicProject(loadProject(project.id)) };
  });

  router.delete('/api/drawings/projects/:id', async ({ params, user }) => {
    requirePermission(user, 'drawings.delete');
    const project = loadProject(params.id);
    runSql('DELETE FROM drawing_projects WHERE id = ?', project.id);
    await removeProjectFiles(project.id);
    audit(user.id, 'drawing_project', project.id, 'delete', { code: project.code });
    return { ok: true };
  });

  // --------------------------------------------------------------- levels
  router.post('/api/drawings/projects/:id/levels', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const project = loadProject(params.id);
    const fields = levelFields(body);
    if (get('SELECT id FROM drawing_levels WHERE project_id = ? AND code = ?', project.id, fields.code)) {
      throw conflict(`Level ${fields.code} is already registered`, `الدور ${fields.code} متسجل قبل كده`);
    }
    if (fields.sort_order === 0) {
      const last = get('SELECT MAX(sort_order) AS m FROM drawing_levels WHERE project_id = ?', project.id);
      fields.sort_order = (last?.m ?? -1) + 1;
    }
    const id = insert('drawing_levels', { ...fields, project_id: project.id });
    audit(user.id, 'drawing_level', id, 'create', { code: fields.code });
    return { level: loadLevel(id) };
  });

  router.patch('/api/drawings/levels/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    const fields = levelFields(body, { partial: true });
    if (fields.code && get('SELECT id FROM drawing_levels WHERE project_id = ? AND code = ? AND id <> ?', level.project_id, fields.code, level.id)) {
      throw conflict(`Level ${fields.code} is already registered`, `الدور ${fields.code} متسجل قبل كده`);
    }
    if (body.ram_failed_columns !== undefined) {
      // the columns RAM reports as failing punching (the program cannot read RAM's verdict from the file)
      const rec = levelPunching(level);
      rec.ram_failed = columnList(body.ram_failed_columns);
      fields.punching_json = JSON.stringify(rec);
    }
    update('drawing_levels', level.id, fields);
    const out = loadLevel(level.id);
    out.punching = levelPunching(out); delete out.punching_json;
    return { level: out };
  });

  router.delete('/api/drawings/levels/:id', async ({ params, user }) => {
    requirePermission(user, 'drawings.delete');
    const level = loadLevel(params.id);
    const runs = all('SELECT id FROM drawing_runs WHERE level_id = ?', level.id);
    runSql('DELETE FROM drawing_levels WHERE id = ?', level.id);
    for (const r of runs) await removeRunFiles(level.project_id, r.id);
    audit(user.id, 'drawing_level', level.id, 'delete', { code: level.code });
    return { ok: true };
  });

  // ----------------------------------------------------------------- runs
  /**
   * One generation: the model file comes from the request body (`req`) or is copied from an earlier run
   * (`sourceRun`); the level's reinforcement edits are applied; the package is zipped when done.
   */
  async function startRun({ req, sourceRun, level, project, user, query = {}, body = {} }) {
    const settings = drawingSettings();
    const mode = oneOf(query.mode ?? body.mode, 'mode', MODES, { fallback: sourceRun?.mode || project.default_mode || settings.default_mode || 'design' });
    const ramBands = oneOf(query.ram_bands ?? body.ram_bands, 'ram_bands', RAM_BANDS, { fallback: sourceRun?.ram_bands || project.ram_bands || settings.ram_bands || 'all' });
    const mesh = oneOf(query.mesh ?? body.mesh, 'mesh', MESH_FACES, { fallback: sourceRun?.mesh || project.mesh || settings.mesh || 'bottom' });
    let revision = str(query.revision ?? body.revision, 'revision', { max: 6, fallback: null });
    if (revision === null) {
      const previous = get("SELECT COUNT(*) AS n FROM drawing_runs WHERE level_id = ? AND mode = ? AND status <> 'failed' AND status <> 'running'", level.id, mode).n;
      revision = String(previous).padStart(2, '0');
    } else {
      revision = /^\d{1,2}$/.test(revision) ? revision.padStart(2, '0') : revision.toUpperCase();
    }
    const notes = str(query.notes ?? body.notes, 'notes', { max: 2000, fallback: null });
    const edits = parseJson(level.edits_json, []);

    const meta = runMeta({ settings, project, level, mode, revision, user });
    const serial = nextCounter(`drawing_runs:${project.id}`);
    const runId = insert('drawing_runs', {
      project_id: project.id, level_id: level.id, serial, mode, revision, ram_bands: ramBands, mesh, notes,
      prefix: meta.prefix, source_name: str(query.name ?? body.name, 'name', { max: 200, fallback: sourceRun?.source_name || null }), status: 'running', created_by: user.id,
      edits_json: edits.length ? JSON.stringify(edits) : null,
    });

    const dir = runDir(project.id, runId);
    const out = join(dir, 'out');
    try {
      let source;
      if (req) source = await saveSource(req, dir, query.name || 'model.cpt');
      else {
        if (!sourceRun?.source_file) throw badRequest('The earlier run kept no model file', 'الإصدار القديم مفيهوش ملف الموديل');
        await mkdir(dir, { recursive: true });
        await copyFile(runFile(sourceRun.project_id, sourceRun.id, sourceRun.source_file), join(dir, sourceRun.source_file));
        source = { file: sourceRun.source_file, bytes: sourceRun.source_bytes };
      }
      update('drawing_runs', runId, { source_file: source.file, source_bytes: source.bytes });

      const reference = level.ref_file ? { file: referencePath(project.id, level.id), ...parseJson(level.ref_json, {}) } : null;
      // the punching record of the level: the columns failing in RAM, and the engineer's decision on the earlier blocked run
      const punchRec = levelPunching(level);
      const decision = punchRec.decision && punchRec.decision.mode !== 'clear' ? punchRec.decision : null;
      const projectSpec = parseJson(project.spec_json, {});
      const punchingSpec = {
        ...((settings.spec || {}).punching || {}), ...(projectSpec.punching || {}),
        ramFailed: punchRec.ram_failed || [],
        ...(decision?.mode === 'ram_ok' ? { ramOk: decision.columns === 'all' ? (decision.flagged || []) : decision.columns } : {}),
        ...(decision?.mode === 'bypass' ? { override: { columns: decision.columns, by: decision.by, date: decision.date, note: decision.note } } : {}),
      };
      const spec = {
        ...(settings.spec || {}),
        ...projectSpec,
        ramBands,
        mesh,
        punching: punchingSpec,
        ...(level.wall_thickness ? { wallThickness: level.wall_thickness } : {}),
        ...(edits.length ? { edits } : {}),
        ...(reference ? { reference } : {}),
      };
      const result = await runGeneration({ input: join(dir, source.file), out, meta, spec, levelNames: [levelTitle(level)], mode });
      if (!result.levels.length) {
        throw badRequest(
          'No slab was found in this file: it is not a RAM Concept model with a meshed slab (or not the plan DXF the generator reads).',
          'الملف ده مفيهوش بلاطة: مش موديل رام فيه بلاطة متعملة لها مش (أو مش المسقط DXF اللي البرنامج بيقراه).',
        );
      }
      const folder = `${meta.prefix}-${level.code}_REV${revision}`;
      await writeRunZip(out, join(dir, 'package.zip'), folder);
      let report = null;
      try { report = await readFile(join(out, 'REPORT.md'), 'utf8'); } catch { /* optional */ }
      // the punching check: a column failing in RAM (as reported) or beyond what stirrups can carry (as estimated) blocks the
      // run until the engineer decides (thicken / bypass at own responsibility / passing in RAM)
      const punching = (result.punching || []).map((pc) => ({ ...pc, blocking_after: blockingAfter(pc, decision) }));
      const blocking = punching.flatMap((pc) => pc.blocking_after);
      const punchingRec = punching.length ? { levels: punching, blocking, warnings: punching.flatMap((pc) => pc.warnings || []), decision, ram_failed: punchRec.ram_failed || [] } : null;
      update('drawing_runs', runId, {
        status: blocking.length ? 'blocked' : 'draft',
        punching_json: punchingRec ? JSON.stringify(punchingRec) : null,
        sheet_count: result.sheets.length,
        sheets_json: JSON.stringify(result.sheets),
        assumptions_json: JSON.stringify(result.assumptions),
        findings_json: JSON.stringify(result.findings),
        report_md: report,
        duration_ms: result.duration_ms,
        quantities_json: result.quantities ? JSON.stringify(result.quantities) : null,
        beams_json: result.beams && result.beams.length ? JSON.stringify(result.beams) : null,
      });
      audit(user.id, 'drawing_run', runId, 'generate', { serial, mode, revision, sheets: result.sheets.length, edits: edits.length });
      return publicRun(loadRun(runId));
    } catch (error) {
      const message = String(error?.message || error).split('\n')[0].slice(0, 500);
      update('drawing_runs', runId, { status: 'failed', error: message });
      if (error?.status) throw error;
      throw badRequest(`The generator could not read this model: ${message}`, `الجينيريتور معرفش يقرا الموديل ده: ${message}`);
    }
  }

  router.post('/api/drawings/levels/:id/runs', async ({ req, params, query, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    const project = loadProject(level.project_id);
    return { run: await startRun({ req, level, project, user, query }) };
  }, { rawBody: true });

  router.post('/api/drawings/runs/:id/regenerate', async ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const sourceRun = loadRun(params.id);
    const level = loadLevel(sourceRun.level_id);
    const project = loadProject(level.project_id);
    return { run: await startRun({ sourceRun, level, project, user, body }) };
  });

  /**
   * The engineer's decision on a run blocked by the punching check. `thicken` keeps the run blocked (a thickened model
   * is uploaded as a new run); `ram_ok` declares the columns passing in RAM (the estimate was conservative) and
   * regenerates without punching reinforcement at them; `bypass` records the acknowledgement (name, date, note) and
   * regenerates with the office punching detail at those columns, printed as the design engineer's responsibility;
   * `clear` forgets the decision. The decision is kept on the level so the next runs of the level carry it.
   */
  router.post('/api/drawings/runs/:id/punching-decision', async ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const run = loadRun(params.id);
    const level = loadLevel(run.level_id);
    const project = loadProject(level.project_id);
    const mode = oneOf(body.mode, 'mode', PUNCHING_DECISIONS);
    const rec = levelPunching(level);
    const current = publicRun(run).punching;
    if (mode === 'clear') {
      delete rec.decision;
      update('drawing_levels', level.id, { punching_json: JSON.stringify(rec) });
      audit(user.id, 'drawing_level', level.id, 'punching_decision', { mode });
      return { run: publicRun(run), decision: null };
    }
    if (!current || !(current.blocking || []).length && !(current.warnings || []).length && mode !== 'thicken') throw badRequest('This run is not blocked by the punching check', 'الإصدار ده مش متوقف بسبب البانشنج');
    if ((mode === 'bypass' || mode === 'ram_ok') && body.acknowledge !== true) throw badRequest('The decision needs the engineer\'s acknowledgement', 'القرار محتاج إقرار المهندس');
    const flagged = [...new Set((current?.levels || []).flatMap((pc) => pc.flagged || []))];
    const columns = body.columns === 'all' || body.columns === undefined ? 'all' : columnList(body.columns);
    if (columns !== 'all' && !columns.length) throw badRequest('Pick the columns the decision covers', 'اختار الأعمدة اللي القرار بيغطيها');
    const decision = {
      mode, columns, flagged, by: user.name, by_id: user.id, date: new Date().toISOString().slice(0, 10), run_id: run.id, revision: run.revision,
      note: str(body.note, 'note', { max: 1000, fallback: null }),
    };
    rec.decision = decision;
    update('drawing_levels', level.id, { punching_json: JSON.stringify(rec) });
    audit(user.id, 'drawing_run', run.id, 'punching_decision', { mode, columns, note: decision.note });
    if (mode === 'thicken') return { run: publicRun(loadRun(run.id)), decision };
    // regenerate from the same model under the decision (the level reloaded so the run reads it): the new run replaces the blocked one at its revision
    const next = await startRun({ sourceRun: run, level: loadLevel(level.id), project, user, body: { revision: run.revision, notes: run.notes } });
    if (next.status !== 'blocked') update('drawing_runs', run.id, { status: 'superseded' });
    return { run: next, decision, previous: run.id };
  });

  router.patch('/api/drawings/runs/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const run = loadRun(params.id);
    const fields = { notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }) };
    if (body.status !== undefined) {
      const status = oneOf(body.status, 'status', RUN_STATUS);
      if (run.status === 'failed' || run.status === 'running') throw badRequest('This run produced no drawings', 'الإصدار ده مطلعش لوحات');
      if (run.status === 'blocked' && status === 'issued') throw badRequest('This run is blocked by the punching check: take a decision on it first', 'الإصدار ده متوقف بسبب البانشنج: لازم قرار المهندس الأول');
      fields.status = status;
      // one issued revision per level and type: issuing this one supersedes the earlier issued ones
      if (status === 'issued') runSql("UPDATE drawing_runs SET status = 'superseded', updated_at = datetime('now') WHERE level_id = ? AND mode = ? AND status = 'issued' AND id <> ?", run.level_id, run.mode, run.id);
    }
    update('drawing_runs', run.id, fields);
    audit(user.id, 'drawing_run', run.id, 'update', fields);
    return { run: publicRun(loadRun(run.id)) };
  });

  router.get('/api/drawings/runs/:id/plan', async ({ params, user, res }) => {
    requirePermission(user, 'drawings.view');
    const run = loadRun(params.id);
    await sendFile(res, runFile(run.project_id, run.id, 'out', 'plan.json'), 'application/json; charset=utf-8');
  });

  router.put('/api/drawings/levels/:id/edits', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    const edits = cleanEdits(body.edits);
    update('drawing_levels', level.id, { edits_json: edits.length ? JSON.stringify(edits) : null });
    audit(user.id, 'drawing_level', level.id, 'edits', { count: edits.length });
    return { level: { ...loadLevel(level.id), edits } };
  });

  // ---------------------------------------------------------------- reference plan
  /**
   * The architect's (or structural) plan of the level as DXF: its grid, columns and slab edges replace the RAM
   * geometry on the sheets. The file is read once here to report what it holds; the alignment options live in
   * `ref_json`: { use: { grid, columns, outline }, align: { mode: 'auto' | 'point', dxf: {x,y}, ram: {x,y}, rot } }.
   */
  router.post('/api/drawings/levels/:id/reference', async ({ req, params, query, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    const name = str(query.name, 'name', { max: 200, fallback: 'reference.dxf' });
    if (extname(name).toLowerCase() !== '.dxf') throw badRequest('The reference plan must be a DXF file (export the DWG with DXFOUT)', 'المخطط المرجعي لازم يكون DXF (اطلع الـ DWG بـ DXFOUT)');
    const path = referencePath(level.project_id, level.id);
    const saved = await saveUpload(req, dirname(path), basename(path), '.dxf');
    let summary;
    try {
      const { readReferencePlan } = await import('../../shopdrawings/lib/reference.mjs');
      const plan = readReferencePlan(await readFile(path, 'utf8'));
      summary = { columns: plan.columns.length, outlines: plan.outlines.length, grid_x: plan.grid.x.map((g) => g.label), grid_y: plan.grid.y.map((g) => g.label), grid_from_drawing: plan.gridFromDrawing, units: plan.units, entities: plan.entities, bbox: plan.levels[0]?.bbox ? { minX: Math.round(plan.levels[0].bbox.minX), minY: Math.round(plan.levels[0].bbox.minY), maxX: Math.round(plan.levels[0].bbox.maxX), maxY: Math.round(plan.levels[0].bbox.maxY) } : null };
    } catch (error) {
      await unlink(path).catch(() => {});
      throw badRequest(`The reference plan could not be read: ${String(error?.message || error).slice(0, 200)}`, `المخطط المرجعي مش مقروء: ${String(error?.message || error).slice(0, 200)}`);
    }
    if (!summary.columns && !summary.outlines) { await unlink(path).catch(() => {}); throw badRequest('No columns or slab outline found in that DXF', 'مفيش أعمدة ولا حدود بلاطة في الملف ده'); }
    const current = parseJson(level.ref_json, {});
    const refJson = { ...current, use: current.use || { grid: true, columns: true, outline: true }, align: current.align || { mode: 'auto' }, summary, bytes: saved.bytes };
    update('drawing_levels', level.id, { ref_file: basename(path), ref_name: name, ref_json: JSON.stringify(refJson) });
    audit(user.id, 'drawing_level', level.id, 'reference', { name, ...summary });
    return { level: { ...loadLevel(level.id), reference: { name, ...refJson } } };
  }, { rawBody: true });

  router.patch('/api/drawings/levels/:id/reference', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    if (!level.ref_file) throw notFound('No reference plan on this level', 'الدور ده مفيهوش مخطط مرجعي');
    const current = parseJson(level.ref_json, {});
    const use = body.use ? { grid: body.use.grid !== false, columns: body.use.columns !== false, outline: body.use.outline !== false } : current.use;
    let align = current.align || { mode: 'auto' };
    if (body.align) {
      const mode = oneOf(body.align.mode, 'align.mode', ['auto', 'point']);
      const num = (v, f) => { const n = Number(v); if (!Number.isFinite(n)) throw badRequest(`${f}: a number is required`, `${f}: لازم رقم`); return n; };
      align = mode === 'point'
        ? { mode, dxf: { x: num(body.align.dxf?.x, 'dxf.x'), y: num(body.align.dxf?.y, 'dxf.y') }, ram: { x: num(body.align.ram?.x, 'ram.x'), y: num(body.align.ram?.y, 'ram.y') }, rot: [0, 90, 180, 270].includes(Number(body.align.rot)) ? Number(body.align.rot) : 0 }
        : { mode };
    }
    const refJson = { ...current, use, align };
    update('drawing_levels', level.id, { ref_json: JSON.stringify(refJson) });
    return { level: { ...loadLevel(level.id), reference: { name: level.ref_name, ...refJson } } };
  });

  router.delete('/api/drawings/levels/:id/reference', async ({ params, user }) => {
    requirePermission(user, 'drawings.create');
    const level = loadLevel(params.id);
    update('drawing_levels', level.id, { ref_file: null, ref_name: null, ref_json: null });
    try { await unlink(referencePath(level.project_id, level.id)); } catch { /* already gone */ }
    return { ok: true };
  });

  // ---------------------------------------------------------------- documents
  router.post('/api/drawings/projects/:id/files', async ({ req, params, query, user }) => {
    requirePermission(user, 'drawings.create');
    const project = loadProject(params.id);
    const category = oneOf(query.category, 'category', FILE_CATEGORIES, { fallback: 'design' });
    const name = str(query.name, 'name', { required: true, max: 200 });
    const ext = extname(name).toLowerCase().slice(0, 12);
    const levelId = query.level_id ? int(query.level_id, 'level_id', { min: 1 }) : null;
    if (levelId && !get('SELECT id FROM drawing_levels WHERE id = ? AND project_id = ?', levelId, project.id)) throw notFound('Level not found', 'الدور مش موجود');
    const id = insert('drawing_files', { project_id: project.id, level_id: levelId, category, name, ext, stored: 'pending', uploaded_by: user.id, note: str(query.note, 'note', { max: 500, fallback: null }), revision: str(query.revision, 'revision', { max: 20, fallback: null }) });
    const stored = `${id}${ext}`;
    try {
      const saved = await saveUpload(req, join(projectDir(project.id), 'files'), stored, ext);
      update('drawing_files', id, { stored, bytes: saved.bytes });
    } catch (error) {
      runSql('DELETE FROM drawing_files WHERE id = ?', id);
      throw error;
    }
    audit(user.id, 'drawing_file', id, 'upload', { category, name });
    return { file: loadFile(id) };
  }, { rawBody: true });

  router.get('/api/drawings/files/:id', async ({ params, user, res }) => {
    requirePermission(user, 'drawings.view');
    const file = loadFile(params.id);
    await sendFile(res, projectFile(file.project_id, file.stored), 'application/octet-stream', file.name);
  });

  router.patch('/api/drawings/files/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const file = loadFile(params.id);
    const fields = {
      note: str(body.note, 'note', { max: 500, fallback: undefined }),
      revision: str(body.revision, 'revision', { max: 20, fallback: undefined }),
      category: body.category === undefined ? undefined : oneOf(body.category, 'category', FILE_CATEGORIES),
      level_id: body.level_id === undefined ? undefined : (body.level_id ? int(body.level_id, 'level_id', { min: 1 }) : null),
    };
    update('drawing_files', file.id, fields);
    return { file: loadFile(file.id) };
  });

  router.delete('/api/drawings/files/:id', async ({ params, user }) => {
    requirePermission(user, 'drawings.delete');
    const file = loadFile(params.id);
    runSql('DELETE FROM drawing_files WHERE id = ?', file.id);
    try { await unlink(projectFile(file.project_id, file.stored)); } catch { /* already gone */ }
    audit(user.id, 'drawing_file', file.id, 'delete', { name: file.name });
    return { ok: true };
  });

  // -------------------------------------------------------------- sheet frame
  router.get('/api/drawings/frame', async ({ user, res }) => {
    requirePermission(user, 'drawings.view');
    const settings = drawingSettings();
    if (!settings.frame_dxf) throw notFound('No frame uploaded', 'مفيش فريم مرفوع');
    await sendFile(res, framePath(), 'application/dxf', 'frame.dxf');
  });

  router.post('/api/drawings/frame', async ({ req, query, user }) => {
    requirePermission(user, 'settings.edit');
    const name = str(query.name, 'name', { max: 200, fallback: 'frame.dxf' });
    if (extname(name).toLowerCase() !== '.dxf') throw badRequest('The frame must be a DXF file (paper mm, A1 origin bottom-left)', 'الفريم لازم يكون ملف DXF (بالملليمتر على الورق، أصل A1 في الركن الأسفل الأيسر)');
    const dir = framePath().replace(/[\\/]frame\.dxf$/, '');
    const saved = await saveUpload(req, dir, 'frame.dxf', '.dxf');
    // sanity: the generator must be able to read it
    const { frameEntities } = await import('../../shopdrawings/cli.mjs');
    const ents = frameEntities(await readFile(framePath(), 'utf8'));
    if (!ents.length) { await unlink(framePath()).catch(() => {}); throw badRequest('No drawable entities found in that DXF', 'مفيش عناصر مرسومة في الملف ده'); }
    const current = getSetting('drawings', {}) || {};
    setSetting('drawings', { ...current, frame_dxf: 'frame.dxf', frame_dxf_name: name, frame_dxf_entities: ents.length, frame_dxf_bytes: saved.bytes });
    audit(user.id, 'settings', null, 'frame', { name, entities: ents.length });
    return { frame_dxf: 'frame.dxf', name, entities: ents.length, bytes: saved.bytes };
  }, { rawBody: true });

  router.delete('/api/drawings/frame', async ({ user }) => {
    requirePermission(user, 'settings.edit');
    const current = getSetting('drawings', {}) || {};
    setSetting('drawings', { ...current, frame_dxf: null, frame_dxf_name: null, frame_dxf_entities: null, frame_dxf_bytes: null });
    try { await unlink(framePath()); } catch { /* already gone */ }
    return { ok: true };
  });

  router.get('/api/drawings/runs/:id', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const run = loadRun(params.id);
    return { run: publicRun(run, { withReport: true }), project: publicProject(loadProject(run.project_id)) };
  });

  // ------------------------------------------------------------ beam design through RAM
  /**
   * The beam design, the office way: the run's model is copied with every design strip replaced by one strip on the
   * centre line of every beam span and a splitter on each edge of the beam, designed as a beam. The engineer opens
   * the copy in RAM Concept, runs Calc All, saves, and uploads it as the next run: the beams then come back typed,
   * marked and scheduled on sheet 07 / 09.
   */
  router.post('/api/drawings/runs/:id/beam-strips', async ({ params, user }) => {
    requirePermission(user, 'drawings.create');
    const run = loadRun(params.id);
    if (!run.source_file || !/\.cpt$/i.test(run.source_file)) throw badRequest('This run was not made from a RAM Concept model', 'الإصدار ده مش من موديل رام');
    const src = runFile(run.project_id, run.id, run.source_file);
    const out = runFile(run.project_id, run.id, 'beam-strips.cpt');
    const { readRamConcept } = await import('../../shopdrawings/lib/ram-concept.mjs');
    const { writeBeamStrips } = await import('../../shopdrawings/lib/beam-strips.mjs');
    let summary;
    try {
      const ram = readRamConcept(src);
      if (!ram.beams.length) throw badRequest('The model has no beams', 'الموديل مفيهوش كمرات');
      summary = writeBeamStrips(src, out, ram);
    } catch (error) {
      if (error?.status) throw error;
      throw badRequest(`The beam strips could not be written: ${String(error?.message || error).slice(0, 200)}`, `الشرائح ما اتكتبتش: ${String(error?.message || error).slice(0, 200)}`);
    }
    const info = { ...summary, file: 'beam-strips.cpt', name: `${run.prefix}-${run.level_code}_REV${run.revision}_BEAM-STRIPS.cpt`, created_at: new Date().toISOString(), by: user.name };
    update('drawing_runs', run.id, { beam_strips_json: JSON.stringify(info) });
    audit(user.id, 'drawing_run', run.id, 'beam_strips', { beams: summary.beams, spans: summary.spans });
    return { beam_strips: info };
  });

  router.get('/api/drawings/runs/:id/beam-strips', async ({ params, user, res }) => {
    requirePermission(user, 'drawings.view');
    const run = loadRun(params.id);
    const info = parseJson(run.beam_strips_json, null);
    if (!info) throw notFound('No beam strips model on this run', 'الإصدار ده ملوش موديل شرائح كمرات');
    await sendFile(res, runFile(run.project_id, run.id, 'beam-strips.cpt'), 'application/octet-stream', info.name);
  });

  // ------------------------------------------------------------ quantities and cost
  router.get('/api/drawings/runs/:id/quantities', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const run = publicRun(loadRun(params.id));
    if (!run.quantities) throw notFound('This run carries no take-off', 'الإصدار ده مفيهوش حصر');
    return { quantities: run.quantities, run: { id: run.id, serial: run.serial, revision: run.revision, mode: run.mode, status: run.status, level_code: run.level_code } };
  });

  router.get('/api/drawings/projects/:id/quantities', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const project = loadProject(params.id);
    return { project: { id: project.id, code: project.code, name: project.name }, ...projectQuantities(project) };
  });

  router.get('/api/drawings/projects/:id/cost', ({ params, query, user }) => {
    requirePermission(user, 'drawings.view');
    const project = loadProject(params.id);
    const settings = drawingSettings();
    // the office rates, overridable per call (a what-if from the screen) with numbers only
    const rates = { ...settings.rates };
    for (const [k, v] of Object.entries(query)) if (k in rates && k !== 'currency' && Number.isFinite(Number(v))) rates[k] = Number(v);
    const q = projectQuantities(project);
    return { project: { id: project.id, code: project.code, name: project.name }, quantities: q, cost: costStudy(q, rates) };
  });

  // ------------------------------------------------------------ submittal forms
  router.get('/api/drawings/projects/:id/submittals', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const project = loadProject(params.id);
    const rows = all(`SELECT ${SUBMITTAL_COLUMNS} FROM drawing_submittals s LEFT JOIN users u ON u.id = s.created_by WHERE s.project_id = ? ORDER BY s.serial DESC`, project.id);
    return { submittals: rows.map(publicSubmittal) };
  });

  router.post('/api/drawings/projects/:id/submittals', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const project = loadProject(params.id);
    const settings = drawingSettings();
    const runIds = (Array.isArray(body.run_ids) ? body.run_ids : []).map((v) => int(v, 'run_ids', { min: 1 })).filter(Boolean);
    if (!runIds.length) throw badRequest('Pick at least one drawing run', 'اختار إصدار لوحات واحد على الأقل');
    const runs = runIds.map((id) => publicRun(loadRun(id)));
    if (runs.some((r) => r.project_id !== project.id)) throw badRequest('A run of another project was picked', 'فيه إصدار من مشروع تاني');
    if (runs.some((r) => r.status === 'failed' || r.status === 'running')) throw badRequest('A run without drawings was picked', 'فيه إصدار مطلعش لوحات');
    if (runs.some((r) => r.status === 'blocked')) throw badRequest('A run blocked by the punching check cannot be submitted', 'فيه إصدار متوقف بسبب البانشنج: مينفعش يتقدم قبل قرار المهندس');
    const only = Array.isArray(body.sheets) && body.sheets.length ? body.sheets.map((v) => String(v)) : null;
    const previous = all('SELECT * FROM drawing_submittals WHERE project_id = ? AND status <> ? ORDER BY serial', project.id, 'withdrawn').map(publicSubmittal);
    const items = submittalItems(runs, { only, previous });
    if (!items.length) throw badRequest('No drawings to submit', 'مفيش لوحات تتقدم');
    const modes = new Set(runs.map((r) => r.mode));
    const kind = modes.size > 1 ? 'mixed' : runs[0].mode;
    const resub = items.some((it) => it.prev_rev != null);
    const id = transaction(() => {
      const serial = nextCounter(`drawing_submittals:${project.id}`);
      return insert('drawing_submittals', {
        project_id: project.id, serial, code: submittalCode(settings.submittal.prefix || 'SPAN-SUB', project.code, serial), revision: 0, kind,
        subject: str(body.subject, 'subject', { max: 300, fallback: `${kind === 'design' ? 'DESIGN' : kind === 'shop' ? 'SHOP' : 'DESIGN AND SHOP'} DRAWINGS - ${[...new Set(items.map((it) => it.level))].join(', ')}${resub ? ' (RE-SUBMISSION)' : ''}` }),
        to_name: str(body.to_name, 'to_name', { max: 200, fallback: project.consultant || null }),
        attention: str(body.attention, 'attention', { max: 200, fallback: null }),
        purpose: oneOf(body.purpose, 'purpose', SUBMITTAL_PURPOSES, { fallback: resub ? 'resubmission' : 'approval' }),
        date: str(body.date, 'date', { max: 10, fallback: new Date().toISOString().slice(0, 10) }),
        items_json: JSON.stringify(items), notes: str(body.notes, 'notes', { max: 4000, fallback: null }),
        status: 'draft', created_by: user.id,
      });
    });
    audit(user.id, 'drawing_submittal', id, 'create', { code: loadSubmittal(id).code, items: items.length });
    return { submittal: publicSubmittal(loadSubmittal(id)) };
  });

  router.get('/api/drawings/submittals/:id', ({ params, user }) => {
    requirePermission(user, 'drawings.view');
    const s = publicSubmittal(loadSubmittal(params.id));
    return { submittal: s, project: publicProject(loadProject(s.project_id)) };
  });

  router.get('/api/drawings/submittals/:id/form', ({ params, user, res }) => {
    requirePermission(user, 'drawings.view');
    const s = publicSubmittal(loadSubmittal(params.id));
    const html = submittalHtml({ submittal: s, project: publicProject(loadProject(s.project_id)), settings: drawingSettings(), items: s.items, user });
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'private, max-age=0', 'x-content-type-options': 'nosniff' });
    res.end(html);
  });

  router.patch('/api/drawings/submittals/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const s = loadSubmittal(params.id);
    const settings = drawingSettings();
    const project = loadProject(s.project_id);
    const fields = {
      subject: str(body.subject, 'subject', { max: 300, fallback: undefined }),
      to_name: str(body.to_name, 'to_name', { max: 200, fallback: undefined }),
      attention: str(body.attention, 'attention', { max: 200, fallback: undefined }),
      notes: str(body.notes, 'notes', { max: 4000, fallback: undefined }),
      date: str(body.date, 'date', { max: 10, fallback: undefined }),
      response_date: str(body.response_date, 'response_date', { max: 10, fallback: undefined }),
      response_notes: str(body.response_notes, 'response_notes', { max: 4000, fallback: undefined }),
      response_by: str(body.response_by, 'response_by', { max: 200, fallback: undefined }),
      purpose: body.purpose === undefined ? undefined : oneOf(body.purpose, 'purpose', SUBMITTAL_PURPOSES),
      status: body.status === undefined ? undefined : oneOf(body.status, 'status', SUBMITTAL_STATUS),
    };
    // re-issuing the same submittal (a correction before the consultant answers) bumps its own revision: -R1, -R2 ...
    if (body.reissue) { fields.revision = (s.revision || 0) + 1; fields.code = submittalCode(settings.submittal.prefix || 'SPAN-SUB', project.code, s.serial, fields.revision); fields.status = 'draft'; }
    update('drawing_submittals', s.id, fields);
    audit(user.id, 'drawing_submittal', s.id, 'update', fields);
    return { submittal: publicSubmittal(loadSubmittal(s.id)) };
  });

  router.delete('/api/drawings/submittals/:id', ({ params, user }) => {
    requirePermission(user, 'drawings.delete');
    const s = loadSubmittal(params.id);
    runSql('DELETE FROM drawing_submittals WHERE id = ?', s.id);
    audit(user.id, 'drawing_submittal', s.id, 'delete', { code: s.code });
    return { ok: true };
  });

  router.get('/api/drawings/runs/:id/zip', async ({ params, user, res }) => {
    requirePermission(user, 'drawings.view');
    const run = loadRun(params.id);
    if (run.status === 'failed' || run.status === 'running') throw notFound('This run produced no package', 'الإصدار ده مطلعش لوحات');
    const name = `${run.prefix}-${run.level_code}_REV${run.revision}.zip`;
    await sendFile(res, runFile(run.project_id, run.id, 'package.zip'), 'application/zip', name);
  });

  router.get('/api/drawings/runs/:id/files/:kind/:name', async ({ params, user, res, query }) => {
    requirePermission(user, 'drawings.view');
    const run = loadRun(params.id);
    const kind = oneOf(params.kind, 'kind', ['dxf', 'preview', 'schedules', 'root']);
    const path = kind === 'root'
      ? runFile(run.project_id, run.id, 'out', params.name)
      : runFile(run.project_id, run.id, 'out', kind, params.name);
    const download = query.download !== undefined ? params.name : null;
    await sendFile(res, path, CONTENT_TYPES[kind], download);
  });

  router.delete('/api/drawings/runs/:id', async ({ params, user }) => {
    requirePermission(user, 'drawings.delete');
    const run = loadRun(params.id);
    runSql('DELETE FROM drawing_runs WHERE id = ?', run.id);
    await removeRunFiles(run.project_id, run.id);
    audit(user.id, 'drawing_run', run.id, 'delete', { serial: run.serial });
    return { ok: true };
  });
}
