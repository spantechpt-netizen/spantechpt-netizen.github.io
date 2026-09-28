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
 */
import { createReadStream } from 'node:fs';
import { stat, readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { copyFile, mkdir, unlink } from 'node:fs/promises';
import { extname } from 'node:path';
import { all, get, insert, update, run as runSql, nextCounter, audit, transaction, getSetting, setSetting } from '../db.js';
import { requirePermission } from '../auth.js';
import { badRequest, notFound, conflict } from '../http.js';
import { str, int, oneOf, jsonField, COUNTRIES } from '../validate.js';
import {
  drawingSettings, nextProjectCode, normaliseCode, runDir, runFile, saveSource, saveUpload, runMeta, levelTitle,
  runGeneration, writeRunZip, removeRunFiles, removeProjectFiles, MODES, RAM_BANDS, RUN_STATUS, FILE_CATEGORIES,
  framePath, projectFile, projectDir,
} from '../drawings.js';

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
  delete out.sheets_json; delete out.assumptions_json; delete out.findings_json; delete out.edits_json;
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
    for (const l of levels) l.edits = parseJson(l.edits_json, []);
    return { project: publicProject(project), levels, runs, files, settings: drawingSettings() };
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
    update('drawing_levels', level.id, fields);
    return { level: loadLevel(level.id) };
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
    let revision = str(query.revision ?? body.revision, 'revision', { max: 6, fallback: null });
    if (revision === null) {
      const previous = get("SELECT COUNT(*) AS n FROM drawing_runs WHERE level_id = ? AND mode = ? AND status <> 'failed' AND status <> 'running'", level.id, mode).n;
      revision = String(previous).padStart(2, '0');
    } else {
      revision = /^\d{1,2}$/.test(revision) ? revision.padStart(2, '0') : revision.toUpperCase();
    }
    const notes = str(query.notes ?? body.notes, 'notes', { max: 2000, fallback: null });
    const edits = parseJson(level.edits_json, []);

    const meta = runMeta({ settings, project, level, mode, revision });
    const serial = nextCounter(`drawing_runs:${project.id}`);
    const runId = insert('drawing_runs', {
      project_id: project.id, level_id: level.id, serial, mode, revision, ram_bands: ramBands, notes,
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

      const spec = {
        ...(settings.spec || {}),
        ...parseJson(project.spec_json, {}),
        ramBands,
        ...(level.wall_thickness ? { wallThickness: level.wall_thickness } : {}),
        ...(edits.length ? { edits } : {}),
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
      update('drawing_runs', runId, {
        status: 'draft',
        sheet_count: result.sheets.length,
        sheets_json: JSON.stringify(result.sheets),
        assumptions_json: JSON.stringify(result.assumptions),
        findings_json: JSON.stringify(result.findings),
        report_md: report,
        duration_ms: result.duration_ms,
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

  router.patch('/api/drawings/runs/:id', ({ params, body, user }) => {
    requirePermission(user, 'drawings.create');
    const run = loadRun(params.id);
    const fields = { notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }) };
    if (body.status !== undefined) {
      const status = oneOf(body.status, 'status', RUN_STATUS);
      if (run.status === 'failed' || run.status === 'running') throw badRequest('This run produced no drawings', 'الإصدار ده مطلعش لوحات');
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
