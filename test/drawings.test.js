/**
 * The reinforcement-drawings module, end to end: a project registered once,
 * a level under it, a RAM Concept model uploaded, the numbered package back.
 *
 *   npm test
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { buildSyntheticCpt } from './helpers/synthetic-cpt.mjs';
import { zipEntries, listZip, readZipEntry, crc32 } from '../server/zip.js';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-drawings-'));
const PORT = 8500 + Math.floor(Math.random() * 400);
const BASE = `http://127.0.0.1:${PORT}`;
const ADMIN = { email: 'admin@test.local', password: 'TestPass@2026' };

let child;
let cookie = '';

async function api(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { 'content-type': 'application/json', ...(cookie ? { cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const setCookie = res.headers.get('set-cookie');
  if (setCookie) cookie = setCookie.split(';')[0];
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  return { status: res.status, body: json, text, headers: res.headers };
}

async function upload(path, bytes) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/octet-stream', ...(cookie ? { cookie } : {}) },
    body: bytes,
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  return { status: res.status, body: json };
}

async function download(path) {
  const res = await fetch(`${BASE}${path}`, { headers: cookie ? { cookie } : {} });
  return { status: res.status, headers: res.headers, bytes: Buffer.from(await res.arrayBuffer()) };
}

before(async () => {
  child = spawn(process.execPath, ['--no-warnings', 'server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOST: '127.0.0.1',
      DB_PATH: join(workDir, 'test.db'),
      DRAWINGS_DIR: join(workDir, 'drawings'),
      UPLOAD_DIR: join(workDir, 'uploads'),
      SESSION_SECRET: 'test-secret-value-for-automated-tests-only',
      ADMIN_EMAIL: ADMIN.email,
      ADMIN_PASSWORD: ADMIN.password,
      ADMIN_NAME: 'Test Admin',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.on('data', (d) => process.stderr.write(`[server] ${d}`));
  const deadline = Date.now() + 15000;
  for (;;) {
    try { if ((await fetch(`${BASE}/api/health`)).ok) break; } catch { /* not yet */ }
    if (Date.now() > deadline) throw new Error('server did not start in time');
    await new Promise((r) => setTimeout(r, 150));
  }
  const login = await api('POST', '/api/auth/login', ADMIN);
  assert.equal(login.status, 201);
});

after(() => {
  child?.kill('SIGTERM');
  rmSync(workDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
test('the zip writer produces a stored archive that reads back entry by entry', () => {
  const buf = zipEntries([
    { name: 'pkg/dxf/SPAN-DD-P26-001-B1-01_X.dxf', data: '0\nSECTION\n' },
    { name: 'pkg/REPORT.md', data: Buffer.from('# report\nعربي\n', 'utf8') },
  ]);
  assert.equal(buf.readUInt32LE(0), 0x04034b50, 'local file header signature');
  const entries = listZip(buf);
  assert.deepEqual(entries.map((e) => e.name), ['pkg/dxf/SPAN-DD-P26-001-B1-01_X.dxf', 'pkg/REPORT.md']);
  assert.equal(readZipEntry(buf, 'pkg/REPORT.md').toString('utf8'), '# report\nعربي\n');
  assert.equal(entries[1].crc, crc32(Buffer.from('# report\nعربي\n', 'utf8')));
  assert.equal(crc32(Buffer.from('123456789')), 0xcbf43926, 'CRC-32 check value');
});

let project;
let level;
let firstRun;

test('a project is registered once with an automatic yearly code', async () => {
  const yy = String(new Date().getFullYear()).slice(-2);
  const created = await api('POST', '/api/drawings/projects', {
    name: 'ROAYA SCHOOL 2', name_ar: 'مدرسة رؤية 2', client: 'ROAYA EDUCATION', consultant: 'ABC CONSULTANTS',
    contractor: 'XYZ CONTRACTING', location: 'RIYADH, KSA', country: 'SA',
    levels: [{ code: 'b1', name: 'Basement ceiling' }],
  });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  project = created.body.project;
  assert.equal(project.code, `P${yy}-001`);
  assert.equal(created.body.levels.length, 1);
  assert.equal(created.body.levels[0].code, 'B1', 'level codes are upper-cased');

  const second = await api('POST', '/api/drawings/projects', { name: 'ANOTHER TOWER' });
  assert.equal(second.body.project.code, `P${yy}-002`);

  const clash = await api('POST', '/api/drawings/projects', { name: 'CLASH', code: project.code });
  assert.equal(clash.status, 409);

  const listed = await api('GET', '/api/drawings/projects?q=ROAYA');
  assert.equal(listed.body.projects.length, 1);
  assert.equal(listed.body.projects[0].level_count, 1);
});

test('levels are registered under the project with unique codes', async () => {
  const added = await api('POST', `/api/drawings/projects/${project.id}/levels`, { code: 'GF', name: 'GROUND FLOOR', zone: 'ZONE A', wall_thickness: 250 });
  assert.equal(added.status, 201, JSON.stringify(added.body));
  assert.equal(added.body.level.sort_order, 1, 'appended after the level registered with the project');
  const dup = await api('POST', `/api/drawings/projects/${project.id}/levels`, { code: 'gf', name: 'AGAIN' });
  assert.equal(dup.status, 409);

  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(detail.body.levels.length, 2);
  level = detail.body.levels.find((l) => l.code === 'B1');
  assert.ok(level);
});

test('uploading a RAM model generates the numbered package for the level', async () => {
  const cpt = readFileSync(await buildSyntheticCpt(workDir));
  const result = await upload(`/api/drawings/levels/${level.id}/runs?name=basement.cpt&mode=design&ram_bands=all`, cpt);
  assert.equal(result.status, 201, JSON.stringify(result.body));
  firstRun = result.body.run;
  assert.equal(firstRun.status, 'draft');
  assert.equal(firstRun.serial, 1);
  assert.equal(firstRun.revision, '00');
  assert.equal(firstRun.prefix, `SPAN-DD-${project.code}`);
  assert.ok(firstRun.sheet_count > 3, `sheets: ${firstRun.sheet_count}`);
  assert.equal(firstRun.sheets[0].no, `SPAN-DD-${project.code}-000`, 'the index sheet');
  const plan = firstRun.sheets.find((s) => s.level !== 'ALL');
  assert.ok(plan.no.startsWith(`SPAN-DD-${project.code}-B1-`), `level code in the drawing number: ${plan.no}`);
  assert.equal(plan.level, 'B1');
  assert.equal(plan.level_name, 'BASEMENT CEILING');
  assert.ok(Array.isArray(firstRun.assumptions) && firstRun.assumptions.length > 0);
  assert.ok(firstRun.quantities && firstRun.quantities.levels.length === 1 && firstRun.quantities.totals.concrete.total_m3 > 0, 'the take-off comes back with the run');
}, { timeout: 120000 });

test('the run exposes its sheets, previews, DXFs and one zip of the package', async () => {
  const detail = await api('GET', `/api/drawings/runs/${firstRun.id}`);
  assert.equal(detail.status, 200);
  assert.ok(detail.body.run.report_md.includes('Design drawing package'));
  assert.equal(detail.body.project.code, project.code);

  const sheet = detail.body.run.sheets[1];
  const svg = await download(`/api/drawings/runs/${firstRun.id}/files/preview/${encodeURIComponent(sheet.file)}.svg`);
  assert.equal(svg.status, 200);
  assert.equal(svg.headers.get('content-type'), 'image/svg+xml');
  assert.ok(svg.bytes.toString('utf8').includes('<svg'));

  const dxf = await download(`/api/drawings/runs/${firstRun.id}/files/dxf/${encodeURIComponent(sheet.file)}.dxf?download=1`);
  assert.equal(dxf.status, 200);
  assert.ok(dxf.headers.get('content-disposition').includes('.dxf'));
  assert.ok(dxf.bytes.toString('utf8').startsWith('0\r\nSECTION') || dxf.bytes.toString('utf8').startsWith('0\nSECTION') || dxf.bytes.toString('utf8').includes('SECTION'));

  const climb = await download(`/api/drawings/runs/${firstRun.id}/files/dxf/..%2F..%2Fsource.cpt`);
  assert.equal(climb.status, 404, 'no path climbing out of the run folder');

  const zip = await download(`/api/drawings/runs/${firstRun.id}/zip`);
  assert.equal(zip.status, 200);
  assert.equal(zip.headers.get('content-type'), 'application/zip');
  assert.ok(zip.headers.get('content-disposition').includes(`SPAN-DD-${project.code}-B1_REV00.zip`));
  const names = listZip(zip.bytes).map((e) => e.name);
  assert.ok(names.some((n) => n.endsWith('/REPORT.md')));
  assert.ok(names.some((n) => n.endsWith('/DESIGN_DRAWINGS_PACKAGE.dxf')));
  assert.ok(names.some((n) => n.includes('/dxf/') && n.endsWith('.dxf')));
  assert.ok(names.every((n) => n.startsWith(`SPAN-DD-${project.code}-B1_REV00/`)), 'everything inside one folder');
});

test('the next run of the same level and type takes the next revision and serial', async () => {
  const cpt = readFileSync(join(workDir, 'synthetic.cpt'));
  const result = await upload(`/api/drawings/levels/${level.id}/runs?name=basement-r1.cpt&mode=design`, cpt);
  assert.equal(result.status, 201, JSON.stringify(result.body));
  assert.equal(result.body.run.serial, 2);
  assert.equal(result.body.run.revision, '01');

  const forced = await upload(`/api/drawings/levels/${level.id}/runs?name=basement.cpt&mode=design&revision=A`, cpt);
  assert.equal(forced.body.run.revision, 'A');
  assert.equal(forced.body.run.serial, 3);

  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(detail.body.runs.length, 3);
  assert.equal(detail.body.levels.find((l) => l.code === 'B1').run_count, 3);
}, { timeout: 180000 });

test('revision management: notes, issuing supersedes the earlier issued run, history in the project', async () => {
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  const done = detail.body.runs.filter((r) => r.status === 'draft');
  assert.equal(done.length, 3, 'runs are drafts until issued');
  const [latest, earlier] = done;
  const noted = await api('PATCH', `/api/drawings/runs/${earlier.id}`, { notes: 'first issue', status: 'issued' });
  assert.equal(noted.status, 200, JSON.stringify(noted.body));
  assert.equal(noted.body.run.status, 'issued');
  assert.equal(noted.body.run.notes, 'first issue');
  const reissued = await api('PATCH', `/api/drawings/runs/${latest.id}`, { status: 'issued' });
  assert.equal(reissued.body.run.status, 'issued');
  const after = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(after.body.runs.find((r) => r.id === earlier.id).status, 'superseded', 'the earlier issued run is superseded');
  assert.equal(after.body.runs.filter((r) => r.status === 'issued').length, 1);
  const zip = await download(`/api/drawings/runs/${earlier.id}/zip`);
  assert.equal(zip.status, 200, 'a superseded run keeps its package');
});

test('the reinforcement editor: plan.json, edits saved on the level, regeneration applies them', async () => {
  const plan = await api('GET', `/api/drawings/runs/${firstRun.id}/plan`);
  assert.equal(plan.status, 200);
  const part = plan.body[0];
  assert.ok(part.bars.length > 5 && part.outline.length >= 4, 'plan with bars and outline');
  const office = part.bars.find((b) => b.kind === 'office' && b.face === 'T');
  const edits = [{ op: 'delete', id: office.id }, { op: 'add', face: 'B', a: { x: 1000, y: 7000 }, b: { x: 5000, y: 7000 }, l1: 'T16-200 (B)' }, { op: 'bogus', id: 'x' }, { op: 'spec', id: 'missing' }];
  const saved = await api('PUT', `/api/drawings/levels/${level.id}/edits`, { edits });
  assert.equal(saved.status, 200, JSON.stringify(saved.body));
  assert.equal(saved.body.level.edits.length, 2, 'malformed edits dropped');
  const regen = await api('POST', `/api/drawings/runs/${firstRun.id}/regenerate`, { notes: 'with edits' });
  assert.equal(regen.status, 201, JSON.stringify(regen.body));
  const fresh = regen.body.run;
  assert.equal(fresh.status, 'draft');
  assert.equal(fresh.edits.length, 2, 'the run records the edits it applied');
  assert.equal(fresh.notes, 'with edits');
  assert.ok(fresh.assumptions.some((a) => /reinforcement edits/.test(a)), 'the sheets say the edits were applied');
  const plan2 = await api('GET', `/api/drawings/runs/${fresh.id}/plan`);
  assert.ok(!plan2.body[0].bars.some((b) => b.id === office.id), 'deleted bar gone on the new run');
  assert.ok(plan2.body[0].bars.some((b) => b.l1 === 'T16-200 (B)'), 'added bar drawn on the new run');
}, { timeout: 120000 });

test('project documents: upload into a section, list, edit, download, delete', async () => {
  const up = await upload(`/api/drawings/projects/${project.id}/files?category=design&name=ARCH-PLAN.dwg&note=arch%20set&revision=B`, Buffer.from('AC1027 fake dwg bytes'));
  assert.equal(up.status, 201, JSON.stringify(up.body));
  assert.equal(up.body.file.category, 'design');
  assert.equal(up.body.file.ext, '.dwg');
  assert.equal(up.body.file.bytes, 21);
  const bad = await upload(`/api/drawings/projects/${project.id}/files?category=nope&name=x.pdf`, Buffer.from('x'));
  assert.equal(bad.status, 400);
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(detail.body.files.length, 1);
  const edited = await api('PATCH', `/api/drawings/files/${up.body.file.id}`, { category: 'ram', level_id: level.id, note: 'moved' });
  assert.equal(edited.body.file.category, 'ram');
  assert.equal(edited.body.file.level_code, 'B1');
  const dl = await download(`/api/drawings/files/${up.body.file.id}`);
  assert.equal(dl.status, 200);
  assert.equal(dl.bytes.toString('utf8'), 'AC1027 fake dwg bytes');
  assert.ok(dl.headers.get('content-disposition').includes('ARCH-PLAN.dwg'));
  const gone = await api('DELETE', `/api/drawings/files/${up.body.file.id}`);
  assert.equal(gone.status, 200);
  assert.equal((await download(`/api/drawings/files/${up.body.file.id}`)).status, 404);
});

test('the office frame DXF is uploaded once and used on every sheet', async () => {
  const { Canvas } = await import('../shopdrawings/lib/canvas.mjs');
  const { toDxf } = await import('../shopdrawings/lib/dxf-writer.mjs');
  const c = new Canvas();
  c.rect(0, 0, 841, 594, { layer: 'FRAME' });
  c.text(650, 20, 'OFFICE FRAME <DRAWING_NO> REV <REV>', { layer: 'TITLE', h: 4 });
  const badUp = await upload('/api/drawings/frame?name=frame.pdf', Buffer.from('%PDF'));
  assert.equal(badUp.status, 400);
  const up = await upload('/api/drawings/frame?name=office-frame.dxf', Buffer.from(toDxf(c)));
  assert.equal(up.status, 201, JSON.stringify(up.body));
  assert.equal(up.body.entities, 2);
  const settings = await api('GET', '/api/settings');
  assert.equal(settings.body.settings.drawings.frame_dxf, 'frame.dxf');
  const dl = await download('/api/drawings/frame');
  assert.equal(dl.status, 200);
  const cpt = readFileSync(join(workDir, 'synthetic.cpt'));
  const result = await upload(`/api/drawings/levels/${level.id}/runs?name=framed.cpt&mode=design`, cpt);
  assert.equal(result.status, 201, JSON.stringify(result.body));
  const sheet = result.body.run.sheets[1];
  const dxf = await download(`/api/drawings/runs/${result.body.run.id}/files/dxf/${encodeURIComponent(sheet.file)}.dxf`);
  const text = dxf.bytes.toString('utf8');
  assert.ok(text.includes(`OFFICE FRAME ${sheet.no} REV `), 'the frame tokens are filled on the sheet');
  assert.ok(!text.includes('THE ENGINEER (CONSULTANT)'), 'the built-in title block is replaced');
  const removed = await api('DELETE', '/api/drawings/frame');
  assert.equal(removed.status, 200);
  assert.equal((await download('/api/drawings/frame')).status, 404);
}, { timeout: 120000 });

test('the take-off: steel, concrete and cables of a run, summed over the current runs of the project, and the cost study', async () => {
  const q = await api('GET', `/api/drawings/runs/${firstRun.id}/quantities`);
  assert.equal(q.status, 200, JSON.stringify(q.body));
  const lv = q.body.quantities.levels[0];
  assert.ok(lv.steel.kg > 0 && lv.steel.byDia.length >= 1, `steel ${JSON.stringify(lv.steel)}`);
  assert.ok(lv.concrete.net_area_m2 > 0 && lv.concrete.total_m3 > 0 && lv.concrete.formwork_m2 > 0, `concrete ${JSON.stringify(lv.concrete)}`);
  assert.equal(lv.concrete.thickness, 250);
  assert.ok(lv.cables && lv.cables.tendons === 2 && lv.cables.strands === 7 && lv.cables.kg > 0 && lv.cables.live_ends === 1 && lv.cables.dead_ends === 3, `cables ${JSON.stringify(lv.cables)}`);
  assert.ok(q.body.quantities.totals.steel.kg === lv.steel.kg, 'one level: totals equal the level');

  const pq = await api('GET', `/api/drawings/projects/${project.id}/quantities`);
  assert.equal(pq.status, 200);
  assert.equal(pq.body.runs.length, 1, 'one current run per level with drawings');
  assert.equal(pq.body.runs[0].status, 'issued', 'the issued run of the level is the current one');
  assert.ok(pq.body.totals.concrete.total_m3 > 0 && pq.body.totals.steel.kg > 0);

  const cost = await api('GET', `/api/drawings/projects/${project.id}/cost?steel_per_ton=4000`);
  assert.equal(cost.status, 200, JSON.stringify(cost.body));
  assert.equal(cost.body.cost.currency, 'SAR');
  assert.equal(cost.body.cost.rates.steel_per_ton, 4000, 'a rate overridden for the what-if');
  const steel = cost.body.cost.totals.lines.find((l) => l.key === 'steel');
  assert.equal(steel.amount, Math.round(steel.qty * 4000));
  assert.ok(cost.body.cost.totals.lines.some((l) => l.key === 'strand') && cost.body.cost.totals.total > cost.body.cost.totals.direct, 'PT lines priced, markup and VAT on top');
});

let submittal;
test('submittal request forms: the drawings of the runs picked, numbered per project, the form filled from the title blocks', async () => {
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  const issued = detail.body.runs.find((r) => r.status === 'issued');
  const created = await api('POST', `/api/drawings/projects/${project.id}/submittals`, { run_ids: [issued.id], attention: 'ENG. AHMED', notes: 'first submission' });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  submittal = created.body.submittal;
  assert.equal(submittal.code, `SPAN-SUB-${project.code}-001`);
  assert.equal(submittal.status, 'draft');
  assert.equal(submittal.to_name, 'ABC CONSULTANTS', 'addressed to the consultant of the project');
  assert.equal(submittal.purpose, 'approval');
  assert.ok(submittal.items.length >= 3 && submittal.items.every((it) => it.no.startsWith(`SPAN-DD-${project.code}-B1-`) && it.rev === issued.revision), JSON.stringify(submittal.items.map((it) => it.no)));
  assert.ok(!submittal.items.some((it) => /COVER/i.test(it.title)), 'the cover / index sheet is not submitted');
  assert.ok(submittal.subject.includes('B1'));

  const form = await download(`/api/drawings/submittals/${submittal.id}/form`);
  assert.equal(form.status, 200);
  assert.ok(form.headers.get('content-type').startsWith('text/html'));
  const html = form.bytes.toString('utf8');
  assert.ok(html.includes(submittal.code) && html.includes('ROAYA SCHOOL 2') && html.includes('ABC CONSULTANTS') && html.includes('ENG. AHMED'), 'project and addressee on the form');
  assert.ok(submittal.items.every((it) => html.includes(it.no) && html.includes(it.title)), 'every drawing number and title on the form');
  assert.ok(html.includes('APPROVED AS NOTED') && html.includes('DRAWING SUBMITTAL'), 'the office template');

  const sent = await api('PATCH', `/api/drawings/submittals/${submittal.id}`, { status: 'submitted' });
  assert.equal(sent.body.submittal.status, 'submitted');
  const answered = await api('PATCH', `/api/drawings/submittals/${submittal.id}`, { status: 'resubmit', response_date: '2026-10-01', response_notes: 'revise the top bars', response_by: 'ENG. AHMED' });
  assert.equal(answered.body.submittal.status, 'resubmit');

  // the next run of the level goes out under a new submittal that names the revision it supersedes
  const other = detail.body.runs.find((r) => r.id !== issued.id && r.status !== 'failed');
  const again = await api('POST', `/api/drawings/projects/${project.id}/submittals`, { run_ids: [other.id], sheets: [other.sheets[1].no] });
  assert.equal(again.status, 201, JSON.stringify(again.body));
  assert.equal(again.body.submittal.code, `SPAN-SUB-${project.code}-002`);
  assert.equal(again.body.submittal.items.length, 1, 'only the sheet picked');
  const item = again.body.submittal.items[0];
  assert.equal(item.no, other.sheets[1].no);
  assert.equal(item.prev_submittal, submittal.code, 'names the earlier submittal of the same drawing number');
  assert.equal(item.prev_rev, issued.revision);
  assert.equal(again.body.submittal.purpose, 'resubmission');
  assert.ok(again.body.submittal.subject.includes('RE-SUBMISSION'));

  const reissued = await api('PATCH', `/api/drawings/submittals/${again.body.submittal.id}`, { reissue: true });
  assert.equal(reissued.body.submittal.code, `SPAN-SUB-${project.code}-002-R1`, 'a corrected form keeps its number with its own revision');
  const listed = await api('GET', `/api/drawings/projects/${project.id}/submittals`);
  assert.equal(listed.body.submittals.length, 2);
  const wrong = await api('POST', `/api/drawings/projects/${project.id}/submittals`, { run_ids: [] });
  assert.equal(wrong.status, 400);
});

test('a reference plan (the architect\'s DXF) on the level: uploaded, aligned on the columns, used on the next run', async () => {
  const { Canvas } = await import('../shopdrawings/lib/canvas.mjs');
  const { toDxf } = await import('../shopdrawings/lib/dxf-writer.mjs');
  const dx = 40000, dy = 25000;
  const c = new Canvas();
  c.pline([{ x: -1000 + dx, y: -1000 + dy }, { x: 13000 + dx, y: -1000 + dy }, { x: 13000 + dx, y: 9000 + dy }, { x: -1000 + dx, y: 9000 + dy }], { layer: 'S-RC slab', closed: true });
  const col = c.block('COLUMN'); col.rect(-200, -400, 400, 800, { layer: 'STR-COLS', closed: true });
  for (const [x, y] of [[0, 0], [12000, 0], [0, 8000], [12000, 8000], [6000, 4000]]) c.insert('COLUMN', x + dx, y + dy);
  for (const [i, x] of [0, 6000, 12000].entries()) { c.line(x + dx, -3000 + dy, x + dx, 11000 + dy, { layer: 'S-GRID' }); c.circle(x + dx, 11600 + dy, 400, { layer: 'S-GRID-IDEN' }); c.text(x + dx, 11600 + dy, 'XYZ'[i], { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  for (const [i, y] of [0, 4000, 8000].entries()) { c.line(-3000 + dx, y + dy, 15000 + dx, y + dy, { layer: 'S-GRID' }); c.circle(-3600 + dx, y + dy, 400, { layer: 'S-GRID-IDEN' }); c.text(-3600 + dx, y + dy, String(i + 5), { layer: 'S-GRID-IDEN', h: 300, align: 'C', valign: 'M' }); }
  const bad = await upload(`/api/drawings/levels/${level.id}/reference?name=plan.dwg`, Buffer.from('x'));
  assert.equal(bad.status, 400, 'only DXF');
  const up = await upload(`/api/drawings/levels/${level.id}/reference?name=ARCH-B1.dxf`, Buffer.from(toDxf(c), 'utf8'));
  assert.equal(up.status, 201, JSON.stringify(up.body));
  const ref = up.body.level.reference;
  assert.equal(ref.summary.columns, 5);
  assert.deepEqual(ref.summary.grid_x, ['X', 'Y', 'Z']);
  assert.deepEqual(ref.summary.grid_y, ['5', '6', '7']);
  assert.equal(ref.align.mode, 'auto');
  const opts = await api('PATCH', `/api/drawings/levels/${level.id}/reference`, { use: { grid: true, columns: true, outline: false }, align: { mode: 'point', dxf: { x: dx, y: dy }, ram: { x: 0, y: 0 }, rot: 0 } });
  assert.equal(opts.status, 200, JSON.stringify(opts.body));
  assert.equal(opts.body.level.reference.align.mode, 'point');
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(detail.body.levels.find((l) => l.id === level.id).reference.name, 'ARCH-B1.dxf');

  const cpt = readFileSync(join(workDir, 'synthetic.cpt'));
  const result = await upload(`/api/drawings/levels/${level.id}/runs?name=basement-ref.cpt&mode=design`, cpt);
  assert.equal(result.status, 201, JSON.stringify(result.body));
  const run = result.body.run;
  assert.ok(run.findings.some((f) => /Reference plan matched on the given point/.test(f)), JSON.stringify(run.findings));
  assert.ok(run.assumptions.some((a) => /taken from the reference plan/.test(a)));
  const back = await api('PATCH', `/api/drawings/levels/${level.id}/reference`, { align: { mode: 'auto' } });
  assert.equal(back.body.level.reference.align.mode, 'auto');
  const removed = await api('DELETE', `/api/drawings/levels/${level.id}/reference`);
  assert.equal(removed.status, 200);
  const after2 = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.equal(after2.body.levels.find((l) => l.id === level.id).reference, null);
}, { timeout: 180000 });

test('a bad file is refused and the run is recorded as failed', async () => {
  const wrong = await upload(`/api/drawings/levels/${level.id}/runs?name=plan.pdf`, Buffer.from('%PDF-1.4'));
  assert.equal(wrong.status, 400);
  const broken = await upload(`/api/drawings/levels/${level.id}/runs?name=broken.cpt`, Buffer.from('not a sqlite file'));
  assert.equal(broken.status, 400, JSON.stringify(broken.body));
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.ok(detail.body.runs.some((r) => r.status === 'failed'));
  assert.equal(detail.body.runs.filter((r) => r.status !== 'failed').length, 6, 'three uploads, one regeneration, one framed run, one on the reference plan');
});

test('deleting the project removes its levels, runs and files', async () => {
  const runDir = join(workDir, 'drawings', String(project.id), String(firstRun.id));
  assert.ok(existsSync(join(runDir, 'package.zip')));
  const removed = await api('DELETE', `/api/drawings/projects/${project.id}`);
  assert.equal(removed.status, 200);
  assert.ok(!existsSync(join(workDir, 'drawings', String(project.id))));
  const gone = await api('GET', `/api/drawings/runs/${firstRun.id}`);
  assert.equal(gone.status, 404);
});

test('viewers can read but not generate', async () => {
  const created = await api('POST', '/api/users', { name: 'Viewer', email: 'viewer@test.local', password: 'Viewer@2026', role: 'viewer' });
  assert.equal(created.status, 201, JSON.stringify(created.body));
  const adminCookie = cookie;
  cookie = '';
  const login = await api('POST', '/api/auth/login', { email: 'viewer@test.local', password: 'Viewer@2026' });
  assert.equal(login.status, 201);
  const list = await api('GET', '/api/drawings/projects');
  assert.equal(list.status, 200);
  const denied = await api('POST', '/api/drawings/projects', { name: 'NOPE' });
  assert.equal(denied.status, 403);
  cookie = adminCookie;
});
