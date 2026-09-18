/**
 * End-to-end API tests. Each run boots the real server against a throwaway
 * database, so nothing here touches production data.
 *
 *   npm test
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { connect } from 'node:net';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-test-'));
const PORT = 8099 + Math.floor(Math.random() * 400);
const BASE = `http://127.0.0.1:${PORT}`;
const ADMIN = { email: 'admin@test.local', password: 'TestPass@2026' };

let child;
let cookie = '';

async function api(method, path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      'content-type': 'application/json',
      ...(cookie ? { cookie } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const setCookie = res.headers.get('set-cookie');
  if (setCookie) cookie = setCookie.split(';')[0];
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  return { status: res.status, body: json, text };
}

/** Posts a file as the raw request body, the way the drawing upload does. */
async function upload(path, contentType, bytes) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': contentType, ...(cookie ? { cookie } : {}) },
    body: bytes,
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  return { status: res.status, body: json };
}

/** Sends bytes a fetch client refuses to send, and returns the status code. */
function rawRequest(raw) {
  return new Promise((resolve, reject) => {
    const socket = connect(PORT, '127.0.0.1', () => socket.write(raw));
    let response = '';
    socket.setTimeout(5000, () => { socket.destroy(); reject(new Error('timed out')); });
    socket.on('data', (chunk) => { response += chunk; });
    socket.on('error', reject);
    socket.on('close', () => {
      const match = /^HTTP\/1\.[01] (\d{3})/.exec(response);
      resolve(match ? Number(match[1]) : 0);
    });
  });
}

before(async () => {
  child = spawn(process.execPath, ['--no-warnings', 'server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOST: '127.0.0.1',
      DB_PATH: join(workDir, 'test.db'),
      SESSION_SECRET: 'test-secret-value-for-automated-tests-only',
      ADMIN_EMAIL: ADMIN.email,
      ADMIN_PASSWORD: ADMIN.password,
      ADMIN_NAME: 'Test Admin',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.on('data', (d) => process.stderr.write(`[server] ${d}`));

  // Wait for the health endpoint rather than sleeping a fixed amount.
  const deadline = Date.now() + 15000;
  for (;;) {
    try {
      const res = await fetch(`${BASE}/api/health`);
      if (res.ok) break;
    } catch { /* not listening yet */ }
    if (Date.now() > deadline) throw new Error('server did not start in time');
    await new Promise((r) => setTimeout(r, 150));
  }
});

after(() => {
  child?.kill('SIGTERM');
  rmSync(workDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
test('rejects a bad password and accepts the right one', async () => {
  const bad = await api('POST', '/api/auth/login', { email: ADMIN.email, password: 'wrong-password' });
  assert.equal(bad.status, 401);

  const good = await api('POST', '/api/auth/login', ADMIN);
  assert.equal(good.status, 201);
  assert.equal(good.body.user.role, 'admin');
  assert.equal(good.body.user.password_hash, undefined, 'password hash must never leave the server');
});

test('refuses unauthenticated access to protected endpoints', async () => {
  const saved = cookie;
  cookie = '';
  const res = await api('GET', '/api/customers');
  assert.equal(res.status, 401);
  cookie = saved;
});

test('creates a customer and rejects a duplicate name', async () => {
  const created = await api('POST', '/api/customers', {
    name_en: 'Shaker Al-Sharif', name_ar: 'شاكر الشريف',
    type: 'owner', country: 'SA', city: 'Riyadh', status: 'prospect', rating: 4,
  });
  assert.equal(created.status, 201);
  assert.equal(created.body.customer.code, 'C-0001');

  const duplicate = await api('POST', '/api/customers', { name_en: 'Shaker Al-Sharif', country: 'SA' });
  assert.equal(duplicate.status, 409);
});

test('validates input and returns a bilingual error', async () => {
  const res = await api('POST', '/api/customers', { name_en: '', country: 'XX' });
  assert.equal(res.status, 400);
  assert.ok(res.body.error.message_ar, 'errors must carry an Arabic message');
});

// ---------------------------------------------------------------------------
let opportunityId;
let quotationId;

test('creates an opportunity linked to the customer', async () => {
  const res = await api('POST', '/api/opportunities', {
    title: 'Rest House — Riyadh', title_ar: 'استراحة — بمدينة الرياض',
    customer_id: 1, country: 'SA', city: 'Riyadh',
    project_type: 'rest_house', area_sqm: 476, stage: 'qualified',
  });
  assert.equal(res.status, 201);
  assert.equal(res.body.opportunity.probability, 30, 'stage "qualified" should default to 30%');
  opportunityId = res.body.opportunity.id;
});

test('prices a quotation of 476 m² at 70 SAR with 15% VAT', async () => {
  const res = await api('POST', '/api/quotations', {
    customer_id: 1,
    opportunity_id: opportunityId,
    project_name: 'Rest House — Riyadh',
    project_name_ar: 'استراحة — بمدينة الرياض',
    attention: 'Shaker Al-Sharif',
    country: 'SA',
    area_sqm: 476,
    unit_price: 70,
    labour_cost_sqm: 18, duct_cost_sqm: 4, grout_cost_sqm: 2, design_cost_sqm: 3,
    anchor_cost: 22, overhead_pct: 8, target_margin: 20,
  });
  assert.equal(res.status, 201);
  const q = res.body.quotation;
  quotationId = q.id;

  assert.match(q.number, /^SPAN TECH P\.T - \d{2} - \d{3}$/);
  assert.equal(q.currency, 'SAR');
  assert.equal(q.vat_rate, 15);
  assert.equal(q.subtotal, 33320, '476 × 70');
  assert.equal(q.net_amount, 33320);
  assert.equal(q.vat_amount, 4998, '15% of 33,320');
  assert.equal(q.total, 38318);
  assert.ok(q.total_words_ar.includes('ريال سعودي'));
  assert.ok(q.total_words_en.includes('Saudi Riyals Only'));
});

test('moves the linked opportunity to the quoted stage', async () => {
  const res = await api('GET', `/api/opportunities/${opportunityId}`);
  assert.equal(res.body.opportunity.stage, 'quoted');
});

test('exposes the internal cost breakdown without printing it', async () => {
  const res = await api('GET', `/api/quotations/${quotationId}`);
  const b = res.body.breakdown;
  assert.equal(b.area_sqm, 476);
  assert.equal(b.strand_kg, 1666, '476 m² × 3.5 kg/m²');
  assert.equal(b.strand_tons, 1.67);
  assert.equal(b.anchor_count, 42, 'ceil(1.666 t × 25 anchors/t)');
  assert.ok(b.cost_per_sqm > 0 && b.cost_per_sqm < 70);
  assert.ok(b.suggested_price_sqm > b.cost_per_sqm, 'target margin must raise the suggested price');
});

test('recomputes totals when a discount is applied', async () => {
  const res = await api('PATCH', `/api/quotations/${quotationId}`, {
    discount_type: 'percent', discount_value: 10,
  });
  const q = res.body.quotation;
  assert.equal(q.subtotal, 33320);
  assert.equal(q.discount_amount, 3332);
  assert.equal(q.net_amount, 29988);
  assert.equal(q.vat_amount, 4498.2);
  assert.equal(q.total, 34486.2);

  // restore for the remaining tests
  await api('PATCH', `/api/quotations/${quotationId}`, { discount_type: 'none', discount_value: 0 });
});

test('ignores client-supplied totals', async () => {
  const res = await api('PATCH', `/api/quotations/${quotationId}`, {
    total: 999999, net_amount: 999999, vat_amount: 1,
  });
  assert.equal(res.body.quotation.total, 38318, 'totals are always derived server side');
});

test('builds a revision that keeps the number and bumps the revision', async () => {
  const res = await api('POST', `/api/quotations/${quotationId}/revise`);
  assert.equal(res.status, 201);
  assert.equal(res.body.quotation.revision, 1);
  assert.equal(res.body.quotation.status, 'draft');
  assert.equal(res.body.quotation.total, 38318, 'revision copies the priced items');
});

test('approving a quotation wins its opportunity', async () => {
  await api('POST', `/api/quotations/${quotationId}/status`, { status: 'sent' });
  const res = await api('POST', `/api/quotations/${quotationId}/status`, { status: 'approved' });
  assert.equal(res.body.quotation.status, 'approved');

  const opp = await api('GET', `/api/opportunities/${opportunityId}`);
  assert.equal(opp.body.opportunity.stage, 'won');
  assert.equal(opp.body.opportunity.probability, 100);
  assert.equal(opp.body.opportunity.expected_value, 33320, 'the won value is the net amount');
});

test('serves a complete bilingual print document', async () => {
  const res = await api('GET', `/api/quotations/${quotationId}/document`);
  assert.equal(res.status, 200);
  const d = res.body;
  assert.ok(d.company.name_ar.includes('سبان تك'));
  assert.ok(d.intro.ar.includes('استراحة'), 'the Arabic intro interpolates the project name');
  assert.ok(d.intro.en.includes('Rest House'));
  assert.ok(d.price_clause.ar.includes('4,000'), 'the strand price is substituted into the clause');
  assert.ok(d.price_clause.en.includes('±5%') || d.price_clause.en.includes('5%'));
  assert.ok(d.quotation.scope.design.items.length > 0);
  assert.equal(d.country.vat_rate, 15);
});

test('applies the right VAT and currency for Egypt and Qatar', async () => {
  const eg = await api('POST', '/api/customers', { name_en: 'Hassan Allam', country: 'EG', city: 'Cairo' });
  const egQuote = await api('POST', '/api/quotations', {
    customer_id: eg.body.customer.id, project_name: 'New Capital Mall',
    country: 'EG', area_sqm: 1000, unit_price: 900,
  });
  assert.equal(egQuote.body.quotation.currency, 'EGP');
  assert.equal(egQuote.body.quotation.vat_rate, 14);
  assert.equal(egQuote.body.quotation.vat_amount, 126000, '14% of 900,000');
  assert.ok(egQuote.body.quotation.total_words_ar.includes('جنيه مصري'));

  const qa = await api('POST', '/api/customers', { name_en: 'UrbaCon', country: 'QA', city: 'Doha' });
  const qaQuote = await api('POST', '/api/quotations', {
    customer_id: qa.body.customer.id, project_name: 'Lusail Office Block',
    country: 'QA', area_sqm: 1000, unit_price: 75,
  });
  assert.equal(qaQuote.body.quotation.currency, 'QAR');
  assert.equal(qaQuote.body.quotation.vat_rate, 0, 'Qatar has no VAT');
  assert.equal(qaQuote.body.quotation.total, 75000);
});

// ---------------------------------------------------------------------------
test('tracks follow-ups in overdue / today / upcoming buckets', async () => {
  const yesterday = new Date(Date.now() - 86400_000).toISOString();
  const tomorrow = new Date(Date.now() + 86400_000).toISOString();

  await api('POST', '/api/activities', { type: 'call', subject: 'Overdue call', customer_id: 1, due_at: yesterday });
  await api('POST', '/api/activities', { type: 'email', subject: 'Future email', customer_id: 1, due_at: tomorrow });

  const summary = await api('GET', '/api/activities/summary');
  assert.equal(summary.body.overdue, 1);
  assert.equal(summary.body.upcoming, 1);

  const overdue = await api('GET', '/api/activities?bucket=overdue');
  assert.equal(overdue.body.activities.length, 1);
  assert.equal(overdue.body.activities[0].subject, 'Overdue call');
});

test('completing a follow-up clears it from the buckets', async () => {
  const list = await api('GET', '/api/activities?bucket=overdue');
  const id = list.body.activities[0].id;
  await api('PATCH', `/api/activities/${id}`, { done: true, outcome: 'Client asked for a revised offer' });
  const summary = await api('GET', '/api/activities/summary');
  assert.equal(summary.body.overdue, 0);
});

// ---------------------------------------------------------------------------
test('reports analytics with a win rate and country breakdown', async () => {
  const overview = await api('GET', '/api/analytics/overview');
  assert.equal(overview.status, 200);
  assert.equal(overview.body.closed.won_count, 1);
  assert.equal(overview.body.closed.win_rate, 100);
  assert.ok(overview.body.quotations.count >= 3);

  const breakdown = await api('GET', '/api/analytics/breakdown');
  const countries = breakdown.body.by_country.map((r) => r.country);
  assert.ok(countries.includes('SA'));
  assert.ok(breakdown.body.price_per_sqm.length > 0, 'price-per-m² benchmark must be reported');

  const funnel = await api('GET', '/api/analytics/funnel');
  assert.ok(funnel.body.funnel.created >= 1);
});

// ---------------------------------------------------------------------------
test('an engineer cannot edit another engineer’s customer', async () => {
  const created = await api('POST', '/api/users', {
    name: 'Mahmoud Saleh', email: 'mahmoud@test.local',
    password: 'Engineer@2026', role: 'engineer', country: 'EG',
  });
  assert.equal(created.status, 201);

  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@test.local', password: 'Engineer@2026' });

  const blocked = await api('PATCH', '/api/customers/1', { city: 'Dammam' });
  assert.equal(blocked.status, 403);

  const deleteBlocked = await api('DELETE', '/api/customers/1');
  assert.equal(deleteBlocked.status, 403, 'engineers may not delete customers');

  cookie = adminCookie;
});

test('refuses to disable the last administrator', async () => {
  const res = await api('PATCH', '/api/users/1', { active: false });
  assert.equal(res.status, 400);
});

test('only managers may change company settings', async () => {
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@test.local', password: 'Engineer@2026' });
  const blocked = await api('PUT', '/api/settings/company', { value: { name_en: 'Hacked' } });
  assert.equal(blocked.status, 403);

  cookie = adminCookie;
  const allowed = await api('PUT', '/api/settings/quote_prefix', { value: 'SPAN TECH P.T' });
  assert.equal(allowed.status, 200);
});

test('signing out invalidates the session', async () => {
  await api('POST', '/api/auth/logout');
  const res = await api('GET', '/api/customers');
  assert.equal(res.status, 401);
});

// ===================================================== notifications & inbox
test('raises reminders for overdue follow-ups and missed contact', async () => {
  // Admin is signed in again at this point in the file order, so re-establish.
  await api('POST', '/api/auth/login', ADMIN);

  const yesterday = new Date(Date.now() - 2 * 86400_000).toISOString();
  await api('POST', '/api/activities', {
    type: 'call', subject: 'Chase the tower BOQ', customer_id: 1, due_at: yesterday,
  });

  const swept = await api('POST', '/api/notifications/sweep');
  assert.equal(swept.status, 201);
  assert.ok(swept.body.swept.overdue >= 1, 'an overdue follow-up must raise an alert');

  const list = await api('GET', '/api/notifications');
  const overdue = list.body.notifications.find((n) => n.type === 'activity_overdue');
  assert.ok(overdue, 'the overdue alert should be in the inbox');
  assert.equal(overdue.severity, 'danger');
  assert.ok(overdue.title_ar && overdue.title_en, 'alerts carry both languages');
});

test('does not raise the same reminder twice', async () => {
  const first = await api('POST', '/api/notifications/sweep');
  assert.equal(first.body.swept.overdue, 0, 'a second sweep must be a no-op');
});

test('marks notifications read and clears the badge', async () => {
  const before = await api('GET', '/api/notifications/count');
  assert.ok(before.body.unread > 0);

  await api('POST', '/api/notifications/read-all');
  const after = await api('GET', '/api/notifications/count');
  assert.equal(after.body.unread, 0);
});

test('sends a message to a colleague and notifies them', async () => {
  const engineer = await api('POST', '/api/users', {
    name: 'Khaled Al-Harbi', email: 'khaled@test.local',
    password: 'Engineer@2026', role: 'engineer', country: 'QA',
  });
  const khaledId = engineer.body.user.id;

  const sent = await api('POST', '/api/messages', {
    recipient_ids: [khaledId],
    subject: 'Lusail pricing',
    body: 'Please review the strand rate before we issue this one.',
  });
  assert.equal(sent.status, 201);
  const threadId = sent.body.thread_id;

  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'khaled@test.local', password: 'Engineer@2026' });

  const inbox = await api('GET', '/api/messages?box=inbox');
  assert.equal(inbox.body.messages.length, 1);
  assert.equal(inbox.body.unread, 1);

  const notifications = await api('GET', '/api/notifications');
  const mail = notifications.body.notifications.find((n) => n.type === 'message');
  assert.ok(mail, 'a message must raise a notification');
  assert.equal(mail.link, `inbox/${threadId}`);

  // Opening the thread clears the unread flag.
  await api('GET', `/api/messages/${threadId}`);
  const after = await api('GET', '/api/messages?box=inbox');
  assert.equal(after.body.unread, 0);

  // And a reply goes back to the original sender.
  const reply = await api('POST', '/api/messages', {
    parent_id: threadId, body: 'Checked — the rate is fine.',
  });
  assert.equal(reply.status, 201);

  cookie = adminCookie;
  const senderNotifications = await api('GET', '/api/notifications?unread=1');
  assert.ok(
    senderNotifications.body.notifications.some((n) => n.type === 'message'),
    'the reply must notify the thread starter',
  );
});

test('refuses a message with no recipients', async () => {
  const res = await api('POST', '/api/messages', { recipient_ids: [], subject: 'x', body: 'y' });
  assert.equal(res.status, 400);
});

test('never notifies someone about their own action', async () => {
  await api('POST', '/api/notifications/read-all');
  // The admin owns customer 1; editing it themselves must stay silent.
  await api('PATCH', '/api/customers/1', { city: 'Riyadh' });
  const after = await api('GET', '/api/notifications/count');
  assert.equal(after.body.unread, 0);
});

// ================================================================== calendar
test('issues a private calendar feed that serves valid iCalendar', async () => {
  const feed = await api('GET', '/api/calendar/feed');
  assert.equal(feed.status, 200);
  assert.match(feed.body.url, /\/calendar\/[A-Za-z0-9_-]+\.ics$/);
  assert.ok(feed.body.webcal_url.startsWith('webcal://'));

  // The feed is fetched by Outlook/Google with no session cookie at all.
  const res = await fetch(feed.body.url.replace(/^http:\/\/[^/]+/, BASE));
  assert.equal(res.status, 200);
  assert.match(res.headers.get('content-type'), /text\/calendar/);

  const ics = await res.text();
  assert.ok(ics.startsWith('BEGIN:VCALENDAR'));
  assert.ok(ics.trimEnd().endsWith('END:VCALENDAR'));
  assert.equal(
    (ics.match(/BEGIN:VEVENT/g) || []).length,
    (ics.match(/END:VEVENT/g) || []).length,
    'every VEVENT must be closed',
  );
  // RFC 5545 caps a content line at 75 octets.
  for (const line of ics.split('\r\n')) {
    assert.ok(Buffer.byteLength(line, 'utf8') <= 75, `line too long: ${line.slice(0, 40)}`);
  }
});

test('rejects an unknown calendar token', async () => {
  const res = await fetch(`${BASE}/calendar/not-a-real-token.ics`);
  assert.equal(res.status, 404);
});

test('rotating the feed invalidates the previous link', async () => {
  const before = await api('GET', '/api/calendar/feed');
  const rotated = await api('POST', '/api/calendar/rotate');
  assert.notEqual(rotated.body.token, before.body.token);

  const old = await fetch(before.body.url.replace(/^http:\/\/[^/]+/, BASE));
  assert.equal(old.status, 404, 'the old URL must stop working');

  const fresh = await fetch(rotated.body.url.replace(/^http:\/\/[^/]+/, BASE));
  assert.equal(fresh.status, 200);
});

test('downloads a single follow-up as an .ics file', async () => {
  const list = await api('GET', '/api/activities');
  const withDate = list.body.activities.find((a) => a.due_at);
  assert.ok(withDate, 'need a dated follow-up for this test');

  const res = await fetch(`${BASE}/api/activities/${withDate.id}/ics`, { headers: { cookie } });
  assert.equal(res.status, 200);
  assert.match(res.headers.get('content-disposition'), /attachment/);
  const ics = await res.text();
  assert.ok(ics.includes('BEGIN:VEVENT'));
  assert.ok(ics.includes('BEGIN:VALARM'), 'events carry a reminder alarm');
});

test('stores per-user reminder preferences', async () => {
  const res = await api('PATCH', '/api/auth/profile', {
    reminder_lead_hours: 48, stale_after_days: 14,
  });
  assert.equal(res.status, 200);
  assert.equal(res.body.user.reminder_lead_hours, 48);
  assert.equal(res.body.user.stale_after_days, 14);
});

// =============================================================== permissions
test('serves the permission catalogue with role defaults', async () => {
  await api('POST', '/api/auth/login', ADMIN);
  const res = await api('GET', '/api/permissions');
  assert.equal(res.status, 200);
  assert.ok(res.body.permissions.length > 20);
  assert.ok(res.body.groups.length >= 6);
  assert.ok(res.body.role_defaults.viewer.length < res.body.role_defaults.engineer.length);
  assert.ok(res.body.role_defaults.engineer.length < res.body.role_defaults.admin.length);
  assert.ok(res.body.mine.includes('users.manage'), 'an admin manages users');
  // Every permission carries both languages for the settings screen.
  for (const permission of res.body.permissions) {
    assert.ok(permission.ar && permission.en, `${permission.key} needs both languages`);
  }
});

test('a viewer can read but not write', async () => {
  await api('POST', '/api/users', {
    name: 'Read Only', email: 'viewer@test.local',
    password: 'Viewer@2026', role: 'viewer',
  });
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'viewer@test.local', password: 'Viewer@2026' });

  assert.equal((await api('GET', '/api/customers')).status, 200);
  assert.equal((await api('POST', '/api/customers', { name_en: 'Nope', country: 'SA' })).status, 403);
  assert.equal((await api('POST', '/api/activities', { subject: 'Nope' })).status, 403);
  assert.equal((await api('POST', '/api/messages', { recipient_ids: [1], subject: 'a', body: 'b' })).status, 403);
  assert.equal((await api('PUT', '/api/settings/quote_prefix', { value: 'X' })).status, 403);

  cookie = adminCookie;
});

test('an engineer cannot delete customers by default', async () => {
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@test.local', password: 'Engineer@2026' });
  const res = await api('DELETE', '/api/customers/2');
  assert.equal(res.status, 403);
  assert.match(res.body.error.message, /customers\.delete/);
  cookie = adminCookie;
});

test('granting one capability to one engineer takes effect', async () => {
  const users = await api('GET', '/api/users');
  const engineer = users.body.users.find((u) => u.email === 'mahmoud@test.local');
  assert.ok(engineer);
  assert.ok(!engineer.effective_permissions.includes('customers.delete'));

  const updated = await api('PATCH', `/api/users/${engineer.id}`, {
    permission_overrides: { 'customers.delete': true },
  });
  assert.equal(updated.status, 200);
  assert.ok(updated.body.user.effective_permissions.includes('customers.delete'));
  assert.equal(updated.body.user.permission_overrides['customers.delete'], true);

  // It applies to the engineer's existing session immediately — no re-login.
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@test.local', password: 'Engineer@2026' });
  const customer = await api('POST', '/api/customers', { name_en: 'Scratch Co', country: 'SA' });
  assert.equal((await api('DELETE', `/api/customers/${customer.body.customer.id}`)).status, 200);
  cookie = adminCookie;
});

test('revoking a role default also takes effect', async () => {
  const users = await api('GET', '/api/users');
  const engineer = users.body.users.find((u) => u.email === 'mahmoud@test.local');

  await api('PATCH', `/api/users/${engineer.id}`, {
    permission_overrides: { 'quotations.create': false },
  });

  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@test.local', password: 'Engineer@2026' });
  const blocked = await api('POST', '/api/quotations', {
    customer_id: 1, project_name: 'Should not happen', country: 'SA', area_sqm: 10, unit_price: 70,
  });
  assert.equal(blocked.status, 403);
  cookie = adminCookie;
});

test('approving a quotation is a separate right from sending one', async () => {
  const users = await api('GET', '/api/users');
  const engineer = users.body.users.find((u) => u.email === 'mahmoud@test.local');
  // Engineers may send, but not decide.
  assert.ok(engineer.effective_permissions.includes('quotations.send'));
  assert.ok(!engineer.effective_permissions.includes('quotations.decide'));
});

test('an administrator cannot lose user management', async () => {
  const res = await api('PATCH', '/api/users/1', {
    permission_overrides: { 'users.manage': false },
  });
  assert.equal(res.status, 200);
  assert.ok(
    res.body.user.effective_permissions.includes('users.manage'),
    'the last admin must never be locked out',
  );
});

test('ignores unknown permission keys', async () => {
  const users = await api('GET', '/api/users');
  const engineer = users.body.users.find((u) => u.email === 'mahmoud@test.local');
  const res = await api('PATCH', `/api/users/${engineer.id}`, {
    permission_overrides: { 'not.a.real.permission': true, 'customers.view': true },
  });
  assert.equal(res.status, 200);
  assert.equal(res.body.user.permission_overrides['not.a.real.permission'], undefined);
});

// ========================================================= company branches
test('a quotation prints the branch matching its own country', async () => {
  await api('POST', '/api/auth/login', ADMIN);

  const saQuote = await api('GET', `/api/quotations/${quotationId}/document`);
  assert.equal(saQuote.status, 200);
  assert.ok(saQuote.body.branch, 'the document must carry a branch');
  assert.equal(saQuote.body.quotation.country, 'SA');
  assert.ok(saQuote.body.branch.phone, 'the Saudi office needs a phone');
  assert.ok(saQuote.body.branch.cr_number, 'the Saudi office has a commercial registration');

  // Egypt was quoted earlier in this file; find it and check it differs.
  const list = await api('GET', '/api/quotations?country=EG');
  const egyptian = list.body.quotations[0];
  assert.ok(egyptian, 'need an Egyptian quotation for this test');

  const egDoc = await api('GET', `/api/quotations/${egyptian.id}/document`);
  assert.equal(egDoc.body.quotation.country, 'EG');
  assert.notEqual(
    egDoc.body.branch.phone, saQuote.body.branch.phone,
    'the Cairo office must not print the Saudi phone number',
  );
  assert.equal(
    egDoc.body.branch.cr_number, '',
    'a Saudi commercial registration must never appear on an Egyptian document',
  );
});

test('a branch with nothing filled in still prints a usable letterhead', async () => {
  const qa = await api('POST', '/api/customers', { name_en: 'Qatar Branch Test', country: 'QA' });
  const quote = await api('POST', '/api/quotations', {
    customer_id: qa.body.customer.id, project_name: 'Branch fallback check',
    country: 'QA', area_sqm: 100, unit_price: 75,
  });

  const doc = await api('GET', `/api/quotations/${quote.body.quotation.id}/document`);
  const branch = doc.body.branch;
  assert.match(branch.name_en, /SPAN TEC Trading/, 'Qatar trades under its own name');
  assert.equal(branch.cr_number, '175473', 'and its own registration');
  assert.match(branch.phone, /^\+974/, 'and its own phone');
  assert.match(branch.email, /spantec-qa\.com$/i);
  assert.match(branch.address_en, /Qatar/);
  assert.match(branch.logo, /logo-qa/, 'and its own mark');
});

test('company settings carry per-country branches', async () => {
  const res = await api('GET', '/api/settings');
  const company = res.body.settings.company;
  assert.ok(company.branches, 'branches must be present');
  for (const code of ['SA', 'EG', 'QA']) {
    assert.ok(company.branches[code], `${code} branch missing`);
  }
  assert.equal(company.branches.SA.cr_number, '7038269549');
  assert.equal(company.branches.QA.cr_number, '175473');
  assert.match(company.branches.EG.email, /spantechpt\.com$/i);
  assert.match(company.branches.SA.email, /spantechksa\.com$/i);
  assert.match(company.branches.QA.email_alt, /finance@spantec-qa\.com/i);
});

// ---------------------------------------------------------------- capture
// Requests that arrive on WhatsApp are pasted in and join the same queue as
// the mail, so the triage and conversion paths stay single.
test('a pasted WhatsApp message joins the requests queue', async () => {
  const res = await api('POST', '/api/mail/capture', {
    channel: 'whatsapp',
    from_name: 'م. طارق',
    from_phone: '+966 55 123 4477',
    text: 'السلام عليكم، محتاجين عرض سعر لأعمال البلاطات اللاحقة للشد لمشروع برج سكني بالرياض، المساحة 9,800 م2',
  });
  assert.equal(res.status, 201);

  const request = res.body.request;
  assert.equal(request.channel, 'whatsapp');
  assert.equal(request.status, 'new');
  assert.equal(request.from_phone, '+966 55 123 4477');
  assert.match(request.subject, /عرض سعر/, 'the first line stands in for a subject');

  const extraction = request.extraction;
  assert.equal(extraction.project.area_sqm, 9800, 'the area is read out of the message');
  assert.equal(extraction.customer.country, 'SA');
  assert.ok(extraction.is_rfq, 'asking for a price is an RFQ whatever the channel');
  assert.ok(
    extraction.contact.phones.includes('+966 55 123 4477'),
    'the sender number is kept even though the body never repeats it',
  );

  const queue = await api('GET', '/api/mail/requests?status=new');
  assert.ok(queue.body.requests.some((r) => r.id === request.id), 'it shows in the new queue');
});

test('a capture from a known number is matched to that customer', async () => {
  const customer = await api('POST', '/api/customers', {
    name_en: 'Rawabi Contracting', country: 'SA', city: 'Riyadh',
  });
  const customerId = customer.body.customer.id;
  await api('POST', `/api/customers/${customerId}/contacts`, {
    name: 'Faisal Otaibi', mobile: '0551234477', is_primary: true,
  });

  // The same number, written the way WhatsApp reports it.
  const res = await api('POST', '/api/mail/capture', {
    channel: 'whatsapp',
    from_phone: '+966551234477',
    text: 'تمام، ابعتلي العرض للمشروع الجديد',
  });
  assert.equal(res.status, 201);
  assert.equal(res.body.request.extraction.customer.matched_id, customerId);
  assert.equal(res.body.request.extraction.customer.matched_by, 'contact_phone');
  assert.equal(res.body.request.customer_id, customerId);
});

test('an empty capture is refused', async () => {
  const res = await api('POST', '/api/mail/capture', { text: '   ' });
  assert.equal(res.status, 400);
});

test('the capture account never shows up as a mailbox', async () => {
  const res = await api('GET', '/api/mail/accounts');
  assert.equal(res.status, 200);
  assert.ok(
    !res.body.accounts.some((a) => a.label === 'Captured requests'),
    'it is an implementation detail, not a mailbox anyone configures',
  );
});

// ------------------------------------------------------------- robustness
// A malformed path or Host header used to throw outside the request handler's
// try block, which takes a Node server down with it: one request from any
// scanner and the CRM was gone for everybody until someone restarted it.
test('a malformed URL is refused, and the server survives it', async () => {
  for (const path of ['/%zz', '/%E0%A4%A', '/api/%zz']) {
    const res = await fetch(`${BASE}${path}`, { headers: { cookie } });
    assert.equal(res.status, 400, `${path} should be a bad request, not a crash`);
  }

  // A stray % in the query string is not malformed — URLSearchParams takes it
  // literally — so it must still be served normally.
  const query = await fetch(`${BASE}/api/customers?x=%`, { headers: { cookie } });
  assert.equal(query.status, 200);

  // fetch() silently drops a Host header, so this one needs a raw socket.
  const status = await rawRequest('GET /api/health HTTP/1.1\r\nHost: [\r\nConnection: close\r\n\r\n');
  assert.equal(status, 400, 'an unparseable Host header is the client’s problem');

  // The point of the test: everything above left the process running.
  const health = await api('GET', '/api/health');
  assert.equal(health.status, 200);
  assert.equal(health.body.ok, true);
});

test('a path cannot escape the public directory', async () => {
  const attempts = [
    '/assets/../../server/config.js',
    '/%2e%2e%2f%2e%2e%2fserver%2fconfig.js',
    '/..%5c..%5cserver%5cconfig.js',           // backslashes, which separate on Windows
  ];
  for (const path of attempts) {
    const res = await fetch(`${BASE}${path}`, { headers: { cookie } });
    const text = await res.text();
    assert.ok(!text.includes('sessionSecret'), `${path} must not reach server source`);
    assert.match(text, /<!doctype html>/i, 'it falls through to the app shell');
  }
});

// ------------------------------------------------------------ duct material
// Egypt works in plastic duct and the other markets in galvanized steel, and
// the printed scope of work has to say which — quoting one and supplying the
// other is a dispute on site.
test('duct material follows the country and rewrites the scope line', async () => {
  const customer = await api('POST', '/api/customers', { name_en: 'Duct Test Co', country: 'EG' });
  const eg = await api('POST', '/api/quotations', {
    customer_id: customer.body.customer.id,
    project_name: 'Cairo duct check', country: 'EG', area_sqm: 500, unit_price: 900,
  });
  assert.equal(eg.status, 201);
  assert.equal(eg.body.quotation.duct_type, 'plastic', 'Egypt defaults to plastic');

  const ductLine = (quote) => quote.scope.supply.items.find((i) => i.key === 'ducts');
  assert.match(ductLine(eg.body.quotation).ar, /بلاستيك/);
  assert.match(ductLine(eg.body.quotation).en, /polyethylene/i);

  const sa = await api('POST', '/api/quotations', {
    customer_id: customer.body.customer.id,
    project_name: 'Riyadh duct check', country: 'SA', area_sqm: 500, unit_price: 70,
  });
  assert.equal(sa.body.quotation.duct_type, 'steel', 'everywhere else defaults to steel');
  assert.match(ductLine(sa.body.quotation).ar, /صاج/);

  // Switching the material rewrites that one line and leaves the rest alone.
  const edited = [...sa.body.quotation.scope.supply.items];
  const strand = edited.find((i) => /Strands/.test(i.en));
  strand.ar = 'الكابلات: مواصفة خاصة بالمشروع';

  const patched = await api('PATCH', `/api/quotations/${sa.body.quotation.id}`, {
    duct_type: 'plastic',
    scope: { ...sa.body.quotation.scope, supply: { ...sa.body.quotation.scope.supply, items: edited } },
  });
  assert.equal(patched.status, 200);
  assert.equal(patched.body.quotation.duct_type, 'plastic');
  assert.match(ductLine(patched.body.quotation).ar, /بلاستيك/, 'the duct line followed the change');

  const keptEdit = patched.body.quotation.scope.supply.items.find((i) => /Strands/.test(i.en));
  assert.equal(keptEdit.ar, 'الكابلات: مواصفة خاصة بالمشروع', 'an edited line is not overwritten');
});

// -------------------------------------------------------------- labour scope
// On some projects we bring the crew, on others the main contractor does and we
// only supervise. The same bullet has to move between our scope of work and
// what we require from the contractor — and never appear in both.
test('who supplies the labour moves the bullet between sections', async () => {
  const customer = await api('POST', '/api/customers', { name_en: 'Labour Test Co', country: 'SA' });
  const created = await api('POST', '/api/quotations', {
    customer_id: customer.body.customer.id,
    project_name: 'Labour scope check', country: 'SA', area_sqm: 900, unit_price: 72,
  });
  assert.equal(created.status, 201);
  assert.equal(created.body.quotation.labour_scope, 'spantech', 'the labour is ours unless said otherwise');

  const labourLines = (quote) => Object.entries(quote.scope)
    .flatMap(([key, section]) => (section.items || [])
      .filter((item) => item.key === 'labour')
      .map((item) => [key, item]));

  const first = labourLines(created.body.quotation);
  assert.equal(first.length, 1, 'the labour line appears exactly once');
  assert.equal(first[0][0], 'installation', 'and under our own scope of work');
  assert.match(first[0][1].ar, /توريد العمالة/);

  // Hand the labour to the client: the line leaves our scope for the list of
  // what the main contractor has to provide.
  const patched = await api('PATCH', `/api/quotations/${created.body.quotation.id}`, {
    labour_scope: 'client',
  });
  assert.equal(patched.status, 200);
  assert.equal(patched.body.quotation.labour_scope, 'client');

  const moved = labourLines(patched.body.quotation);
  assert.equal(moved.length, 1, 'still exactly once, never in both sections');
  assert.equal(moved[0][0], 'requirements');
  assert.match(moved[0][1].ar, /تحت إشراف/, 'we still supervise the crew');

  // And back again, without disturbing the rest of the installation scope.
  const back = await api('PATCH', `/api/quotations/${created.body.quotation.id}`, {
    labour_scope: 'spantech',
  });
  const returned = labourLines(back.body.quotation);
  assert.equal(returned.length, 1);
  assert.equal(returned[0][0], 'installation');
  assert.equal(
    back.body.quotation.scope.installation.items.length,
    created.body.quotation.scope.installation.items.length,
    'the installation scope is the length it started at',
  );

  const rejected = await api('PATCH', `/api/quotations/${created.body.quotation.id}`, {
    labour_scope: 'somebody_else',
  });
  assert.equal(rejected.status, 400, 'an unknown option is refused rather than guessed');
});

// ------------------------------------------------------- study and drawings
// The study is what goes to the owner, and the drawings are the engineer's own
// — attaching one and captioning it has to work end to end.
test('a study takes figures, drawings and captions', async () => {
  const customer = await api('POST', '/api/customers', { name_en: 'Study Test Co', country: 'SA' });
  const created = await api('POST', '/api/quotations', {
    customer_id: customer.body.customer.id,
    project_name: 'Study drawings check', country: 'SA', area_sqm: 5000, unit_price: 72,
  });
  const id = created.body.quotation.id;

  const saved = await api('PUT', `/api/quotations/${id}/study`, {
    study: {
      system: 'solid', floors: 7, area_sqm: 5000,
      conv_thickness_mm: 270, conv_rebar_kg_m3: 125,
      pt_thickness_mm: 220, pt_rebar_kg_m3: 50, pt_rate_sqm: 72,
      concrete_rate_m3: 260, rebar_rate_ton: 3100, formwork_rate_sqm: 45,
    },
  });
  assert.equal(saved.status, 200);
  assert.equal(saved.body.study.complete, true, 'every rate is filled in');
  assert.equal(saved.body.study.conventional.concrete_m3, 9450);

  // A 1×1 PNG is a real PNG as far as the upload is concerned.
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  );
  const uploaded = await upload(`/api/quotations/${id}/study/drawings?kind=original`, 'image/png', png);
  assert.equal(uploaded.status, 201);
  assert.equal(uploaded.body.drawings.length, 1);
  const drawing = uploaded.body.drawings[0];
  assert.equal(drawing.kind, 'original');

  // A PDF cannot be shown inside the printed study, so it is refused with a
  // reason rather than stored and silently dropped from the document.
  const pdf = await upload(`/api/quotations/${id}/study/drawings?kind=original`, 'application/pdf', png);
  assert.equal(pdf.status, 400);
  assert.match(pdf.body.error.message_ar, /PDF/);

  // Captioning writes through the generic update helper, which sets
  // updated_at on every row it touches.
  const captioned = await api('PATCH', `/api/quotations/${id}/study/drawings/${drawing.id}`, {
    caption_ar: 'المخطط الأصلي قبل التحويل',
    caption_en: 'Original layout before conversion',
  });
  assert.equal(captioned.status, 200, captioned.text);
  assert.equal(captioned.body.drawings[0].caption_ar, 'المخطط الأصلي قبل التحويل');

  const file = await fetch(`${BASE}/api/quotations/${id}/study/drawings/${drawing.id}/file`, {
    headers: { cookie },
  });
  assert.equal(file.status, 200);
  assert.equal(file.headers.get('content-type'), 'image/png');

  const removed = await api('DELETE', `/api/quotations/${id}/study/drawings/${drawing.id}`);
  assert.equal(removed.status, 200);
  assert.equal(removed.body.drawings.length, 0);
});

// The deck is edited on the deck itself — the engineer rewrites a sentence in
// front of the owner's name and it has to still be there next time.
test('wording edited on the deck is kept, and kept clean', async () => {
  const customer = await api('POST', '/api/customers', { name_en: 'Deck Test Co', country: 'SA' });
  const created = await api('POST', '/api/quotations', {
    customer_id: customer.body.customer.id,
    project_name: 'Deck edits check', country: 'SA', area_sqm: 3000, unit_price: 70,
  });
  const id = created.body.quotation.id;

  const saved = await api('PUT', `/api/quotations/${id}/study/deck`, {
    text: {
      'cover.title': '  دراسة   تكلفة مشروع النخيل  ',
      'adv.1.h': 'بحور أكبر ومواقف أكتر',
      'bad key!': 'dropped',
      'adv.2.h': 42,
      'long.one': 'x'.repeat(4000),
    },
    hidden: { company: true, basis: false },
  });
  assert.equal(saved.status, 200);
  assert.equal(saved.body.deck.text['cover.title'], 'دراسة تكلفة مشروع النخيل', 'whitespace is tidied');
  assert.equal(saved.body.deck.text['bad key!'], undefined, 'a key that is not a key is dropped');
  assert.equal(saved.body.deck.text['adv.2.h'], undefined, 'a number is not wording');
  assert.equal(saved.body.deck.text['long.one'].length, 1500, 'and text is capped');
  assert.deepEqual(saved.body.deck.hidden, { company: true }, 'only the slides actually dropped');

  const reopened = await api('GET', `/api/quotations/${id}/study`);
  assert.equal(reopened.body.study.input.deck.text['adv.1.h'], 'بحور أكبر ومواقف أكتر');

  // Saving the figures from the study form must not wipe the wording.
  const figures = await api('PUT', `/api/quotations/${id}/study`, {
    study: { system: 'solid', floors: 3, area_sqm: 3000, concrete_rate_m3: 250 },
  });
  assert.equal(figures.status, 200);
  assert.equal(
    figures.body.study.input.deck.text['cover.title'],
    'دراسة تكلفة مشروع النخيل',
    'the deck survives a save from the study form',
  );
  assert.deepEqual(figures.body.study.input.deck.hidden, { company: true });
});
