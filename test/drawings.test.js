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
  assert.equal(firstRun.status, 'done');
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

test('a bad file is refused and the run is recorded as failed', async () => {
  const wrong = await upload(`/api/drawings/levels/${level.id}/runs?name=plan.pdf`, Buffer.from('%PDF-1.4'));
  assert.equal(wrong.status, 400);
  const broken = await upload(`/api/drawings/levels/${level.id}/runs?name=broken.cpt`, Buffer.from('not a sqlite file'));
  assert.equal(broken.status, 400, JSON.stringify(broken.body));
  const detail = await api('GET', `/api/drawings/projects/${project.id}`);
  assert.ok(detail.body.runs.some((r) => r.status === 'failed'));
  assert.equal(detail.body.runs.filter((r) => r.status === 'done').length, 3);
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
