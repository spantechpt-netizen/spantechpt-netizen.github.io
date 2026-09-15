/**
 * End-to-end API tests. Each run boots the real server against a throwaway
 * database, so nothing here touches production data.
 *
 *   npm test
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
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
