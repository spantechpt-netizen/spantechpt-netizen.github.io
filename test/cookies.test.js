/**
 * The SECURE_COOKIES / plain-HTTP mismatch.
 *
 * A Secure cookie is never returned over plain HTTP, so this combination used
 * to log a user in and lose the session on the next request — an endless
 * bounce back to the sign-in screen with nothing in the log to explain it.
 * This needs its own server, because the setting is read at start-up.
 *
 *   npm test
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-cookies-'));
const PORT = 8600 + Math.floor(Math.random() * 300);
const BASE = `http://127.0.0.1:${PORT}`;
const ADMIN = { email: 'admin@test.local', password: 'TestPass@2026' };

let child;

before(async () => {
  child = spawn(process.execPath, ['--no-warnings', 'server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOST: '127.0.0.1',
      DB_PATH: join(workDir, 'test.db'),
      SESSION_SECRET: 'test-secret-value-for-automated-tests-only',
      SECURE_COOKIES: 'true',
      ADMIN_EMAIL: ADMIN.email,
      ADMIN_PASSWORD: ADMIN.password,
      ADMIN_NAME: 'Test Admin',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.on('data', (d) => process.stderr.write(`[secure-server] ${d}`));

  const deadline = Date.now() + 15000;
  for (;;) {
    try {
      if ((await fetch(`${BASE}/api/health`)).ok) break;
    } catch { /* not listening yet */ }
    if (Date.now() > deadline) throw new Error('server did not start in time');
    await new Promise((r) => setTimeout(r, 150));
  }
});

after(() => {
  child?.kill('SIGTERM');
  rmSync(workDir, { recursive: true, force: true });
});

const login = (headers = {}) => fetch(`${BASE}/api/auth/login`, {
  method: 'POST',
  headers: { 'content-type': 'application/json', ...headers },
  body: JSON.stringify(ADMIN),
});

test('signing in over plain HTTP says why, instead of looping', async () => {
  const res = await login();
  assert.equal(res.status, 400, 'a silent 201 here is the bug');

  const body = await res.json();
  assert.match(body.error.message, /SECURE_COOKIES/, 'it names the setting to change');
  assert.match(body.error.message, /HTTPS/);
  assert.ok(body.error.message_ar, 'and says so in Arabic too');
  assert.equal(res.headers.get('set-cookie'), null, 'no session cookie is issued');
});

test('the same sign-in behind a TLS proxy works', async () => {
  const res = await login({ 'x-forwarded-proto': 'https' });
  assert.equal(res.status, 201);

  const cookie = res.headers.get('set-cookie');
  assert.ok(cookie, 'the session cookie is issued');
  assert.match(cookie, /Secure/, 'and carries the Secure flag');
  assert.match(cookie, /HttpOnly/);
});

test('a proxy reporting a chain of protocols is read from the first', async () => {
  // nginx behind another proxy appends, so the value can be "https, http".
  const res = await login({ 'x-forwarded-proto': 'https, http' });
  assert.equal(res.status, 201);
});
