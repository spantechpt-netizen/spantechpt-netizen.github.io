/**
 * Email pipeline tests: the real IMAP client, MIME parser, extraction and
 * request queue, driven against an in-process fake IMAP server.
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { startFakeImap, buildRawMessage } from './fake-imap.js';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-mail-'));
const PORT = 8600 + Math.floor(Math.random() * 300);
const BASE = `http://127.0.0.1:${PORT}`;
const ADMIN = { email: 'admin@mail.test', password: 'TestPass@2026' };

let child;
let imap;
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
  try { json = text ? JSON.parse(text) : null; } catch { /* non-JSON */ }
  return { status: res.status, body: json };
}

// --------------------------------------------------------------- the mailbox
const MESSAGES = {
  INBOX: [
    {
      uid: 101,
      raw: buildRawMessage({
        from: '=?UTF-8?B?2LnZhdixINmB2KrYrdmK?= <omar@nesma-contracting.com.sa>',
        subject: 'طلب عرض سعر — برج سكني أ بجدة',
        body: 'السلام عليكم،\n\nمطلوب عرض سعر لأعمال الأسقف اللاحقة للشد لمشروع برج سكني أ بجدة.\n'
          + 'المساحة التقريبية 9,800 م2.\n\nبرجاء إرسال العرض خلال أسبوع.\n\nعمر فتحي\nنسما وشركاه للمقاولات\n+966 50 123 4567',
      }),
    },
    {
      uid: 102,
      raw: buildRawMessage({
        from: 'Sami Habib <sami@dar-engineering.com>',
        subject: 'RFQ - Post Tension Slabs - Girls School Riyadh',
        body: 'Dear Sir,\n\nPlease quote for post-tensioned slabs, total area 3,200 sqm, '
          + 'for our girls school project in Riyadh.\n\nRegards,\nSami Habib\nDar Engineering Consultants',
      }),
    },
    {
      uid: 103,
      raw: buildRawMessage({
        from: 'Newsletter <newsletter@constructionweekly.com>',
        subject: 'This week in construction',
        body: 'Top stories from the industry.',
        extraHeaders: { 'List-Unsubscribe': '<https://example.com/unsub>' },
      }),
    },
    {
      uid: 104,
      raw: buildRawMessage({
        from: 'Mailer Daemon <mailer-daemon@spantech-pt.com>',
        subject: 'Undeliverable: your message',
        body: 'Delivery has failed to these recipients.',
      }),
    },
    {
      uid: 105,
      raw: buildRawMessage({
        from: 'Ali Al-Kuwari <ali@urbacon.qa>',
        subject: 'Lusail office block — post tension enquiry',
        body: 'Hello,\n\nWe are pricing an office building in Lusail, Doha. '
          + 'Slab area is about 12,500 m2. Can you send a budgetary quotation?\n\nAli',
      }),
    },
  ],
  Archive: [
    {
      uid: 55,
      raw: buildRawMessage({
        from: 'Nour El-Din <nour@hassanallam.com>',
        subject: 'عرض سعر مول العاصمة الإدارية',
        body: 'مطلوب تسعير 21000 م2 أسقف لاحقة الشد لمول العاصمة الإدارية الجديدة.',
        date: 'Mon, 02 Mar 2026 09:00:00 +0200',
      }),
    },
  ],
};

before(async () => {
  imap = await startFakeImap({ messages: MESSAGES, user: 'crm@spantech-pt.com', password: 'mailbox-secret' });

  child = spawn(process.execPath, ['--no-warnings', 'server/index.js'], {
    cwd: new URL('..', import.meta.url).pathname,
    env: {
      ...process.env,
      PORT: String(PORT),
      HOST: '127.0.0.1',
      DB_PATH: join(workDir, 'mail.db'),
      SESSION_SECRET: 'mail-test-secret-value-not-for-production',
      ADMIN_EMAIL: ADMIN.email,
      ADMIN_PASSWORD: ADMIN.password,
      ADMIN_NAME: 'Mail Test Admin',
      MAIL_POLL_MINUTES: '999',   // never poll on its own during the tests
      SWEEP_MINUTES: '999',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stderr.on('data', (d) => process.stderr.write(`[server] ${d}`));

  const deadline = Date.now() + 15000;
  for (;;) {
    try { if ((await fetch(`${BASE}/api/health`)).ok) break; } catch { /* starting */ }
    if (Date.now() > deadline) throw new Error('server did not start');
    await new Promise((r) => setTimeout(r, 150));
  }
  await api('POST', '/api/auth/login', ADMIN);
});

after(async () => {
  child?.kill('SIGTERM');
  await imap?.close();
  rmSync(workDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
let accountId;

test('stores a mailbox and never returns the password', async () => {
  const res = await api('POST', '/api/mail/accounts', {
    label: 'Company inbox',
    host: '127.0.0.1',
    port: imap.port,
    secure: true,
    allow_self_signed: true,   // the fixture certificate is self-signed
    username: 'crm@spantech-pt.com',
    password: 'mailbox-secret',
    folders: ['INBOX'],
  });
  assert.equal(res.status, 201);
  accountId = res.body.account.id;

  const list = await api('GET', '/api/mail/accounts');
  const account = list.body.accounts.find((a) => a.id === accountId);
  assert.equal(account.username, 'crm@spantech-pt.com');
  assert.equal(account.password_enc, undefined, 'the password must never leave the server');
  assert.equal(account.password, undefined);
});

test('connects to the mailbox and lists its folders', async () => {
  const res = await api('POST', `/api/mail/accounts/${accountId}/test`);
  assert.equal(res.status, 201);
  assert.equal(res.body.ok, true, `connection failed: ${res.body.error}`);
  assert.ok(res.body.folders.includes('INBOX'));
  assert.ok(imap.state.loginCount > 0, 'the client must have authenticated');
});

test('reports a clear error for a wrong password', async () => {
  const bad = await api('POST', '/api/mail/accounts', {
    label: 'Wrong', host: '127.0.0.1', port: imap.port, secure: true, allow_self_signed: true,
    username: 'crm@spantech-pt.com', password: 'not-the-password', folders: ['INBOX'],
  });
  const res = await api('POST', `/api/mail/accounts/${bad.body.account.id}/test`);
  assert.equal(res.body.ok, false);
  assert.ok(res.body.error, 'the failure reason must reach the settings screen');
  await api('DELETE', `/api/mail/accounts/${bad.body.account.id}`);
});

test('syncs the inbox, keeping real enquiries and dropping the noise', async () => {
  const res = await api('POST', `/api/mail/accounts/${accountId}/sync`, { since_days: 3650 });
  assert.equal(res.status, 201);
  const summary = res.body.summary;
  assert.equal(summary.fetched, 5, 'every INBOX message should be fetched');
  assert.equal(summary.stored, 5);
  // 101, 102 and 105 are enquiries; 103 is a newsletter and 104 a bounce.
  assert.equal(summary.queued, 3, 'only genuine enquiries belong in the queue');
});

test('decodes Arabic subjects and bodies through the whole pipeline', async () => {
  const res = await api('GET', '/api/mail/requests');
  const arabic = res.body.requests.find((r) => String(r.subject).includes('برج سكني'));
  assert.ok(arabic, 'the Arabic RFQ must be in the queue');
  assert.equal(arabic.from_email, 'omar@nesma-contracting.com.sa');
  assert.equal(arabic.from_name, 'عمر فتحي', 'the encoded-word sender name must decode');
  assert.ok(arabic.snippet.includes('الأسقف اللاحقة للشد'));
});

test('extracts area, country and project type without any AI', async () => {
  const res = await api('GET', '/api/mail/requests');

  const jeddah = res.body.requests.find((r) => String(r.subject).includes('برج سكني'));
  assert.equal(jeddah.extraction.project.area_sqm, 9800, '9,800 م2 must be read');
  assert.equal(jeddah.extraction.project.country, 'SA');
  assert.equal(jeddah.extraction.project.type, 'tower');
  assert.equal(jeddah.extraction.is_rfq, true);
  assert.equal(jeddah.extraction.mentions_post_tension, true);
  assert.ok(jeddah.extraction.contact.phones.length > 0, 'the signature phone should be picked up');

  const school = res.body.requests.find((r) => String(r.subject).includes('Girls School'));
  assert.equal(school.extraction.project.area_sqm, 3200);
  assert.equal(school.extraction.project.type, 'school');
  assert.equal(school.extraction.project.country, 'SA');

  const lusail = res.body.requests.find((r) => String(r.subject).includes('Lusail'));
  assert.equal(lusail.extraction.project.area_sqm, 12500);
  assert.equal(lusail.extraction.project.country, 'QA');
  assert.equal(lusail.extraction.project.type, 'admin');
});

test('does not re-import messages it already has', async () => {
  const res = await api('POST', `/api/mail/accounts/${accountId}/sync`, { since_days: 3650 });
  assert.equal(res.body.summary.queued, 0, 'a second sync must add nothing');
  const list = await api('GET', '/api/mail/requests');
  assert.equal(list.body.requests.length, 3);
});

test('tells the manager a request arrived', async () => {
  const res = await api('GET', '/api/notifications');
  const alerts = res.body.notifications.filter((n) => n.type === 'mail_request');
  assert.equal(alerts.length, 3);
  assert.ok(alerts[0].title_ar && alerts[0].title_en);
  assert.match(alerts[0].link, /^requests\/\d+$/);
});

// ---------------------------------------------------------------------------
let requestId;
let engineerId;

test('a manager assigns a request to an engineer, who is notified', async () => {
  const engineer = await api('POST', '/api/users', {
    name: 'Mahmoud Saleh', email: 'mahmoud@mail.test',
    password: 'Engineer@2026', role: 'engineer', country: 'EG',
  });
  engineerId = engineer.body.user.id;

  const queue = await api('GET', '/api/mail/requests?status=new');
  requestId = queue.body.requests[0].id;

  const assigned = await api('POST', `/api/mail/requests/${requestId}/assign`, {
    assigned_to: engineerId,
    notes: 'راجع المخططات وابعت العرض',
  });
  assert.equal(assigned.status, 201);
  assert.equal(assigned.body.request.status, 'assigned');
  assert.equal(assigned.body.request.assigned_to, engineerId);

  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@mail.test', password: 'Engineer@2026' });
  const alerts = await api('GET', '/api/notifications?unread=1');
  assert.ok(
    alerts.body.notifications.some((n) => n.type === 'mail_request' && n.link === `requests/${requestId}`),
    'the engineer must be told',
  );
  cookie = adminCookie;
});

test('an engineer only sees requests handed to them', async () => {
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@mail.test', password: 'Engineer@2026' });

  const mine = await api('GET', '/api/mail/requests');
  assert.equal(mine.body.requests.length, 1);
  assert.equal(mine.body.requests[0].id, requestId);

  // Someone else's request is not readable.
  const others = await api('GET', '/api/mail/requests/2');
  assert.ok([403, 404].includes(others.status));

  // And they cannot hand work to themselves.
  const blocked = await api('POST', `/api/mail/requests/${requestId}/assign`, { assigned_to: engineerId });
  assert.equal(blocked.status, 403);

  cookie = adminCookie;
});

test('converting a request creates the customer, contact and opportunity', async () => {
  const before = await api('GET', `/api/mail/requests/${requestId}`);
  const extraction = before.body.request.extraction;

  const res = await api('POST', `/api/mail/requests/${requestId}/convert`, { owner_id: engineerId });
  assert.equal(res.status, 201);
  assert.equal(res.body.request.status, 'converted');

  const customer = await api('GET', `/api/customers/${res.body.customer_id}`);
  assert.equal(customer.status, 200);
  assert.equal(customer.body.customer.email, before.body.request.from_email);
  assert.equal(customer.body.customer.owner_id, engineerId, 'the assigned engineer owns it');
  assert.ok(customer.body.contacts.length > 0, 'the sender becomes a contact');
  assert.equal(customer.body.contacts[0].is_primary, 1);

  const opportunity = await api('GET', `/api/opportunities/${res.body.opportunity_id}`);
  assert.equal(opportunity.body.opportunity.area_sqm, extraction.project.area_sqm);
  assert.equal(opportunity.body.opportunity.country, extraction.project.country);
  assert.equal(opportunity.body.opportunity.stage, 'qualified');
});

test('refuses to convert the same request twice', async () => {
  const res = await api('POST', `/api/mail/requests/${requestId}/convert`, {});
  assert.equal(res.status, 400);
});

test('a second email from the same sender matches the existing customer', async () => {
  // Re-syncing with a wider folder set picks up the archived Egyptian RFQ.
  await api('PATCH', `/api/mail/accounts/${accountId}`, { folders: ['INBOX', 'Archive'] });
  const res = await api('POST', `/api/mail/accounts/${accountId}/sync`, { since_days: 3650, backfill: true });
  assert.ok(res.body.summary.queued >= 1, 'the archived RFQ should be queued');

  const queue = await api('GET', '/api/mail/requests');
  const egypt = queue.body.requests.find((r) => String(r.subject).includes('العاصمة'));
  assert.ok(egypt, 'the Arabic archived RFQ must be found');
  assert.equal(egypt.extraction.project.area_sqm, 21000);
  assert.equal(egypt.extraction.project.country, 'EG');
  assert.equal(egypt.extraction.project.type, 'mall');
});

test('dismissing a request takes it off the queue', async () => {
  const queue = await api('GET', '/api/mail/requests?status=new');
  const target = queue.body.requests[0];
  const res = await api('POST', `/api/mail/requests/${target.id}/status`, {
    status: 'dismissed', notes: 'مش شغلنا',
  });
  assert.equal(res.body.request.status, 'dismissed');

  const remaining = await api('GET', '/api/mail/requests?status=new');
  assert.ok(!remaining.body.requests.some((r) => r.id === target.id));
});

// ---------------------------------------------------------------------------
test('the AI key is stored but never read back', async () => {
  const saved = await api('PUT', '/api/mail/ai', {
    enabled: true, model: 'claude-sonnet-5', api_key: 'sk-ant-secret-value-12345',
  });
  assert.equal(saved.status, 200);
  assert.equal(saved.body.ai.has_key, true);
  assert.ok(!JSON.stringify(saved.body).includes('sk-ant-secret-value-12345'), 'the key must not be echoed');

  const read = await api('GET', '/api/mail/ai');
  assert.equal(read.body.ai.has_key, true);
  assert.equal(read.body.ai.api_key, undefined);
  assert.ok(read.body.ai.key_hint.endsWith('45'), 'only a masked hint is shown');

  const cleared = await api('PUT', '/api/mail/ai', { clear_key: true });
  assert.equal(cleared.body.ai.has_key, false);
});

// The filter decides what reaches the queue, not what is kept: the newsletter
// and the bounce are still in the mailbox, and a person can still find them.
test('the whole mailbox is browsable, not only the queued requests', async () => {
  const all = await api('GET', '/api/mail/messages');
  assert.equal(all.status, 200);
  const counts = all.body.counts;
  assert.equal(counts.total, counts.queued + counts.other, 'every message is one or the other');
  assert.equal(counts.other, 2, 'the newsletter and the bounce are kept, just not queued');
  assert.ok(counts.queued >= 3, 'and the enquiries are in the queue');

  const other = await api('GET', '/api/mail/messages?only=other');
  assert.equal(other.body.messages.length, 2);
  assert.ok(other.body.messages.every((m) => !m.request_id));

  const queued = await api('GET', '/api/mail/messages?only=queued');
  assert.ok(queued.body.messages.every((m) => m.request_id));

  const search = await api('GET', '/api/mail/messages?q=%D8%A8%D8%B1%D8%AC');
  assert.ok(search.body.messages.length >= 1, 'searching in Arabic finds the tower enquiry');
  assert.ok(search.body.messages.some((m) => String(m.subject).includes('برج سكني')));

  const one = await api('GET', `/api/mail/messages/${other.body.messages[0].id}`);
  assert.equal(one.status, 200);
  assert.ok(one.body.message.body_text, 'the reader gets the whole message');
});

test('a message the filter passed over can be put into the queue by hand', async () => {
  const other = await api('GET', '/api/mail/messages?only=other');
  const message = other.body.messages[0];

  const queued = await api('POST', `/api/mail/messages/${message.id}/queue`);
  assert.equal(queued.status, 201, queued.text);
  assert.ok(queued.body.request.id > 0, 'a request row comes back');
  assert.equal(queued.body.request.subject, message.subject, 'for that same message');
  assert.equal(queued.body.request.status, 'new', 'and it lands at the top of the queue');

  const again = await api('POST', `/api/mail/messages/${message.id}/queue`);
  assert.equal(again.status, 400, 'and not twice');

  const after = await api('GET', '/api/mail/messages');
  assert.equal(after.body.counts.other, 1, 'one fewer message outside the queue');
});

// A mailbox with more history than one run can carry has to be reachable in
// several runs, rather than handing back the same newest few every time.
test('a second import run reaches further back instead of repeating itself', async () => {
  // A second account against the same mailbox, so this starts from nothing.
  const created = await api('POST', '/api/mail/accounts', {
    label: 'History import', host: '127.0.0.1', port: imap.port, secure: true,
    allow_self_signed: true, username: 'crm@spantech-pt.com', password: 'mailbox-secret',
    folders: ['INBOX'],
  });
  const historyId = created.body.account.id;

  const first = await api('POST', `/api/mail/accounts/${historyId}/sync`, {
    since_days: 3650, limit: 2, backfill: true,
  });
  assert.equal(first.status, 201);
  assert.equal(first.body.summary.fetched, 2, 'the run carries only what it was asked for');
  assert.equal(first.body.summary.remaining, 3, 'and says how many are still waiting');

  const second = await api('POST', `/api/mail/accounts/${historyId}/sync`, {
    since_days: 3650, limit: 2, backfill: true,
  });
  assert.equal(second.body.summary.fetched, 2, 'the next run fetches the next two');
  assert.equal(second.body.summary.skipped, 0, 'not the same two again');
  assert.equal(second.body.summary.remaining, 1);

  const third = await api('POST', `/api/mail/accounts/${historyId}/sync`, {
    since_days: 3650, limit: 2, backfill: true,
  });
  assert.equal(third.body.summary.fetched, 1, 'and the last one');
  assert.equal(third.body.summary.remaining, 0, 'with nothing left behind');

  const mailbox = await api('GET', `/api/mail/messages?account_id=${historyId}`);
  assert.equal(mailbox.body.messages.length, 5, 'the whole folder arrived, two runs at a time');

  await api('DELETE', `/api/mail/accounts/${historyId}`);
});

test('browsing the whole mailbox is its own permission', async () => {
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@mail.test', password: 'Engineer@2026' });
  assert.equal((await api('GET', '/api/mail/requests')).status, 200, 'the queue is still theirs');
  assert.equal((await api('GET', '/api/mail/messages')).status, 403, 'the mailbox is not');
  cookie = adminCookie;
});

test('mail permissions are enforced', async () => {
  const adminCookie = cookie;
  await api('POST', '/api/auth/login', { email: 'mahmoud@mail.test', password: 'Engineer@2026' });

  // An engineer may see their own requests but not configure mailboxes.
  assert.equal((await api('GET', '/api/mail/requests')).status, 200);
  assert.equal((await api('GET', '/api/mail/accounts')).status, 403);
  assert.equal((await api('PUT', '/api/mail/ai', { enabled: false })).status, 403);
  assert.equal((await api('POST', '/api/mail/sync')).status, 403);

  cookie = adminCookie;
});
