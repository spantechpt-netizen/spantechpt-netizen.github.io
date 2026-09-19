/**
 * The API described from the router itself.
 *
 * Every route registered on the Router becomes a path in an OpenAPI 3.0
 * document, so the description can never drift from what the server
 * actually answers: add a route and it appears, remove one and it goes.
 * What the generator cannot know — what a route is for, what it needs —
 * comes from the notes below, keyed by "METHOD /path", and a route without
 * a note is still listed with its method, path, tag and parameters.
 *
 * /api/docs renders the same document as a page that works with no internet
 * access, because the company server may well have none.
 */

/** One line per route, in both languages, plus the permission it asks for. */
const NOTES = {
  'POST /api/auth/login': ['Sign in with email and password; sets the session cookie.', 'تسجيل الدخول بالإيميل وكلمة السر؛ يضع كوكي الجلسة.'],
  'POST /api/auth/logout': ['Sign out and clear the session.', 'تسجيل الخروج ومسح الجلسة.'],
  'GET /api/auth/me': ['The signed-in user with their effective permissions, or null.', 'المستخدم الحالي وصلاحياته الفعلية، أو null.'],
  'PATCH /api/auth/profile': ['Update own name, language, reminder settings and dashboard layout.', 'تعديل الاسم واللغة وإعدادات التذكير وترتيب لوحة التحكم.'],
  'POST /api/auth/password': ['Change own password.', 'تغيير كلمة السر.'],

  'GET /api/users': ['List users.', 'قائمة المستخدمين.'],
  'POST /api/users': ['Create a user.', 'إنشاء مستخدم.', 'users.manage'],
  'PATCH /api/users/{id}': ['Update a user, their role and permission overrides.', 'تعديل مستخدم ودوره وصلاحياته.', 'users.manage'],
  'DELETE /api/users/{id}': ['Deactivate a user.', 'إيقاف مستخدم.', 'users.manage'],
  'GET /api/permissions': ['The permission catalogue with role defaults.', 'قائمة الصلاحيات وافتراضيات كل دور.'],

  'GET /api/customers': ['List customers, filtered by q, country, status, type and scope.', 'قائمة العملاء مع الفلاتر.', 'customers.view'],
  'POST /api/customers': ['Create a customer.', 'إنشاء عميل.', 'customers.create'],
  'GET /api/customers/{id}': ['A customer with contacts, opportunities, quotations and activities.', 'عميل بجهات اتصاله وفرصه وعروضه ومتابعاته.', 'customers.view'],
  'PATCH /api/customers/{id}': ['Update a customer.', 'تعديل عميل.', 'customers.edit'],
  'DELETE /api/customers/{id}': ['Delete a customer.', 'مسح عميل.', 'customers.delete'],
  'GET /api/customers/{id}/mail': ['Messages filed under this customer by address.', 'رسائل البريد المؤرشفة تحت العميل.', 'customers.view + mail.view'],
  'GET /api/customers/{id}/mail/{messageId}': ['One filed message with its full text.', 'رسالة واحدة بنصها الكامل.', 'customers.view + mail.view'],
  'POST /api/customers/{id}/contacts': ['Add a contact.', 'إضافة جهة اتصال.', 'customers.edit'],
  'PATCH /api/contacts/{id}': ['Update a contact.', 'تعديل جهة اتصال.', 'customers.edit'],
  'DELETE /api/contacts/{id}': ['Delete a contact.', 'مسح جهة اتصال.', 'customers.edit'],

  'GET /api/opportunities': ['List opportunities; open=1 for the live pipeline.', 'قائمة الفرص.', 'opportunities.view'],
  'POST /api/opportunities': ['Create an opportunity.', 'إنشاء فرصة.', 'opportunities.create'],
  'GET /api/opportunities/{id}': ['One opportunity.', 'فرصة واحدة.', 'opportunities.view'],
  'PATCH /api/opportunities/{id}': ['Update an opportunity, including its stage.', 'تعديل فرصة ومرحلتها.', 'opportunities.edit'],
  'DELETE /api/opportunities/{id}': ['Delete an opportunity.', 'مسح فرصة.', 'opportunities.delete'],

  'GET /api/activities': ['List follow-ups; done=0 for open ones.', 'قائمة المتابعات.', 'activities.view'],
  'GET /api/activities/summary': ['Overdue / today / upcoming counts for the badges.', 'أعداد المتابعات الفائتة واليوم والقادمة.', 'activities.view'],
  'GET /api/activities/{id}/ics': ['One follow-up as an .ics calendar file.', 'متابعة كملف تقويم .ics.', 'activities.view'],
  'POST /api/activities': ['Create a follow-up.', 'إنشاء متابعة.', 'activities.create'],
  'PATCH /api/activities/{id}': ['Update or complete a follow-up.', 'تعديل أو إتمام متابعة.', 'activities.edit'],
  'DELETE /api/activities/{id}': ['Delete a follow-up.', 'مسح متابعة.', 'activities.delete'],

  'GET /api/quotations': ['List quotations, filtered by q, status, country, dates.', 'قائمة عروض الأسعار مع الفلاتر.', 'quotations.view'],
  'GET /api/quotations/export': ['The filtered list as a spreadsheet (format=xlsx|csv, lang=ar|en).', 'القائمة كملف Excel أو CSV.', 'quotations.view'],
  'POST /api/quotations': ['Create a quotation from a customer, area and rate.', 'إنشاء عرض سعر.', 'quotations.create'],
  'POST /api/quotations/expire-stale': ['Mark past-validity quotations expired.', 'تحديد العروض منتهية الصلاحية.', 'quotations.edit'],
  'GET /api/quotations/{id}': ['One quotation with items, totals and revisions.', 'عرض سعر ببنوده وإجمالياته ومراجعاته.', 'quotations.view'],
  'PATCH /api/quotations/{id}': ['Update a quotation; totals are recomputed server-side.', 'تعديل عرض سعر؛ الإجماليات تُحسب على السيرفر.', 'quotations.edit'],
  'DELETE /api/quotations/{id}': ['Delete a quotation.', 'مسح عرض سعر.', 'quotations.delete'],
  'GET /api/quotations/{id}/document': ['The full bilingual print document.', 'وثيقة الطباعة الكاملة بالعربية والإنجليزية.', 'quotations.view'],
  'POST /api/quotations/{id}/status': ['Change status (sent, approved, rejected…).', 'تغيير حالة العرض.', 'quotations.send / quotations.decide'],
  'POST /api/quotations/{id}/revise': ['Create the next revision.', 'إنشاء مراجعة جديدة.', 'quotations.create'],
  'POST /api/quotations/{id}/duplicate': ['Duplicate as a new quotation.', 'نسخ كعرض جديد.', 'quotations.create'],
  'GET /api/quotations/{id}/study': ['The cost comparison study and its drawings.', 'دراسة فرق التكلفة ومخططاتها.', 'quotations.view'],
  'PUT /api/quotations/{id}/study': ['Save the study figures.', 'حفظ أرقام الدراسة.', 'quotations.edit'],
  'PUT /api/quotations/{id}/study/deck': ['Save wording edited on the printed deck.', 'حفظ تعديلات نص الشرائح.', 'quotations.edit'],
  'POST /api/quotations/{id}/study/drawings': ['Attach a drawing image (body is the file; kind=original|post_tension).', 'رفع مخطط كصورة.', 'quotations.edit'],
  'GET /api/quotations/{id}/study/drawings/{drawingId}/file': ['The drawing file.', 'ملف المخطط.', 'quotations.view'],
  'PATCH /api/quotations/{id}/study/drawings/{drawingId}': ['Caption or reclassify a drawing.', 'تعليق على مخطط.', 'quotations.edit'],
  'DELETE /api/quotations/{id}/study/drawings/{drawingId}': ['Remove a drawing.', 'مسح مخطط.', 'quotations.edit'],

  'GET /api/analytics/overview': ['KPIs: pipeline, win rate, quotations, customers.', 'المؤشرات الرئيسية.', 'analytics.view'],
  'GET /api/analytics/monthly': ['Monthly quoted and won values.', 'الاتجاه الشهري.', 'analytics.view'],
  'GET /api/analytics/breakdown': ['By country, engineer, source, type, loss reason, price/m².', 'التفصيل حسب الدولة والمهندس والمصدر…', 'analytics.view'],
  'GET /api/analytics/funnel': ['Conversion funnel.', 'قمع التحويل.', 'analytics.view'],
  'GET /api/analytics/export': ['Every analytics table as one workbook (format=xlsx|csv, lang=ar|en).', 'كل جداول التحليلات كملف Excel.', 'analytics.view'],

  'GET /api/notifications': ['Own notifications with the unread count.', 'إشعاراتي وعدد غير المقروء.'],
  'GET /api/notifications/count': ['Unread count only.', 'عدد غير المقروء فقط.'],
  'POST /api/notifications/{id}/read': ['Mark one read.', 'تحديد كمقروء.'],
  'POST /api/notifications/read-all': ['Mark all read.', 'تحديد الكل كمقروء.'],
  'DELETE /api/notifications/{id}': ['Delete a notification.', 'مسح إشعار.'],
  'POST /api/notifications/sweep': ['Run the reminder sweep now.', 'تشغيل مسح التذكيرات الآن.'],
  'GET /api/events': ['Server-Sent Events stream: notification, mail, quote_status.', 'بث الأحداث اللحظية (SSE).'],
  'GET /api/events/status': ['How many browsers hold the stream open.', 'عدد المتصفحات المتصلة بالبث.'],
  'GET /api/messages': ['Internal message threads.', 'الرسائل الداخلية.', 'messages.send'],
  'GET /api/messages/{id}': ['One thread.', 'محادثة واحدة.', 'messages.send'],
  'POST /api/messages': ['Send a message to colleagues.', 'إرسال رسالة للزملاء.', 'messages.send'],
  'DELETE /api/messages/{id}': ['Delete a message.', 'مسح رسالة.', 'messages.send'],
  'GET /api/inbox/summary': ['Unread internal messages count.', 'عدد الرسائل الداخلية غير المقروءة.'],

  'GET /api/calendar/feed': ['Own private calendar feed URL.', 'رابط تقويم المتابعات الخاص.'],
  'POST /api/calendar/rotate': ['Issue a new feed token, invalidating the old link.', 'تجديد رابط التقويم.'],

  'GET /api/settings': ['Company settings, price book and templates.', 'إعدادات الشركة وقوائم الأسعار والقوالب.', 'settings.view'],
  'PUT /api/settings/{key}': ['Replace one settings key.', 'تعديل مفتاح إعدادات.', 'settings.edit'],
  'POST /api/settings/{key}/reset': ['Reset one key to its default.', 'إرجاع مفتاح لافتراضيه.', 'settings.edit'],

  'GET /api/mail/accounts': ['Mailboxes, without passwords.', 'حسابات البريد بدون كلمات السر.', 'mail.manage'],
  'POST /api/mail/accounts': ['Add a mailbox (IMAP).', 'إضافة حساب بريد.', 'mail.manage'],
  'PATCH /api/mail/accounts/{id}': ['Update a mailbox.', 'تعديل حساب بريد.', 'mail.manage'],
  'DELETE /api/mail/accounts/{id}': ['Remove a mailbox.', 'مسح حساب بريد.', 'mail.manage'],
  'POST /api/mail/accounts/{id}/test': ['Test the connection and list folders.', 'اختبار الاتصال.', 'mail.manage'],
  'POST /api/mail/accounts/{id}/sync': ['Sync one mailbox now (backfill=true to import history).', 'مزامنة حساب الآن.', 'mail.manage'],
  'POST /api/mail/sync': ['Sync every due mailbox.', 'مزامنة كل الحسابات.', 'mail.manage'],
  'POST /api/mail/capture': ['Paste a WhatsApp or phone request into the queue.', 'إضافة طلب من واتساب أو مكالمة.', 'mail.view'],
  'GET /api/mail/requests': ['The incoming requests queue.', 'قائمة الطلبات الواردة.', 'mail.view'],
  'GET /api/mail/requests/{id}': ['One request with its extraction.', 'طلب واحد مع بياناته المستخرجة.', 'mail.view'],
  'POST /api/mail/requests/{id}/assign': ['Hand a request to an engineer.', 'تحويل طلب لمهندس.', 'mail.triage'],
  'POST /api/mail/requests/{id}/convert': ['Create customer, contact and opportunity from a request.', 'تحويل الطلب لعميل وفرصة.', 'mail.view'],
  'POST /api/mail/requests/{id}/status': ['Dismiss or reopen a request.', 'تجاهل أو إعادة فتح طلب.', 'mail.triage'],
  'POST /api/mail/requests/{id}/re-extract': ['Run extraction again.', 'إعادة الاستخراج.', 'mail.view'],
  'GET /api/mail/ai': ['Whether an AI key is configured (never the key).', 'حالة مفتاح الذكاء الاصطناعي.', 'mail.manage'],
  'PUT /api/mail/ai': ['Store or clear the AI key.', 'حفظ أو مسح مفتاح الذكاء الاصطناعي.', 'mail.manage'],
  'GET /api/mail/messages': ['The whole mailbox, not only queued requests.', 'كل رسائل الصندوق.', 'mail.view_all'],
  'GET /api/mail/messages/{id}': ['One stored message.', 'رسالة واحدة.', 'mail.view_all'],
  'POST /api/mail/messages/{id}/queue': ['Put a message into the requests queue by hand.', 'إضافة رسالة للطلبات يدوياً.', 'mail.triage'],
  'GET /api/mail/summary': ['Request counts for the badges.', 'أعداد الطلبات للشارات.'],

  'GET /api/health': ['Liveness check, no session needed.', 'فحص الحالة بدون جلسة.'],
  'GET /api/openapi.json': ['This document.', 'هذه الوثيقة.'],
  'GET /api/docs': ['The API reference as a page.', 'مرجع الـ API كصفحة.'],
};

const TAGS = {
  auth: 'Authentication', users: 'Users', permissions: 'Users', customers: 'Customers', contacts: 'Customers',
  opportunities: 'Opportunities', activities: 'Follow-ups', quotations: 'Quotations', analytics: 'Analytics',
  notifications: 'Notifications', events: 'Notifications', messages: 'Messages', inbox: 'Messages',
  calendar: 'Calendar', settings: 'Settings', mail: 'Mail', health: 'System', 'openapi.json': 'System', docs: 'System',
};

/** The router's segments back into a path, with `{param}` placeholders. */
const pathOf = (segments) => `/${segments.map((s) => (s.startsWith(':') ? `{${s.slice(1)}}` : s)).join('/')}`;

export function buildOpenApi(router, { serverUrl = '/' } = {}) {
  const paths = {};
  for (const route of router.routes) {
    const path = pathOf(route.segments);
    const key = `${route.method} ${path}`;
    const [summary, summaryAr, permission] = NOTES[key] || [];
    const tag = TAGS[route.segments[1]] || 'Other';

    const operation = {
      tags: [tag],
      summary: summary || `${route.method} ${path}`,
      description: [summaryAr, permission ? `Requires: ${permission}` : null].filter(Boolean).join('\n\n') || undefined,
      operationId: `${route.method.toLowerCase()}${path.replace(/[{}]/g, '').split('/').filter(Boolean).slice(1).map((s) => s[0].toUpperCase() + s.slice(1)).join('')}`,
      parameters: route.segments.filter((s) => s.startsWith(':')).map((s) => ({
        name: s.slice(1), in: 'path', required: true, schema: { type: 'string' },
      })),
      security: route.options.public ? [] : [{ cookieAuth: [] }],
      responses: {
        200: { description: 'OK', content: { 'application/json': { schema: { type: 'object' } } } },
        400: { description: 'Validation error' },
        401: { description: 'Not signed in' },
        403: { description: 'Not allowed' },
        404: { description: 'Not found' },
      },
    };
    if (route.method === 'POST') operation.responses[201] = operation.responses[200];
    if (['POST', 'PUT', 'PATCH'].includes(route.method) && !route.options.rawBody) {
      operation.requestBody = { content: { 'application/json': { schema: { type: 'object' } } } };
    }
    if (route.options.rawBody) {
      operation.requestBody = { content: { 'image/*': { schema: { type: 'string', format: 'binary' } } } };
    }
    if (route.options.stream) {
      operation.responses[200] = { description: 'text/event-stream', content: { 'text/event-stream': { schema: { type: 'string' } } } };
    }
    if (key.endsWith('/export')) {
      operation.parameters.push(
        { name: 'format', in: 'query', schema: { type: 'string', enum: ['xlsx', 'csv'] } },
        { name: 'lang', in: 'query', schema: { type: 'string', enum: ['ar', 'en'] } },
      );
      operation.responses[200] = { description: 'A spreadsheet download' };
    }
    if (!paths[path]) paths[path] = {};
    paths[path][route.method.toLowerCase()] = operation;
  }

  const tagNames = [...new Set(Object.values(paths).flatMap((ops) => Object.values(ops).map((op) => op.tags[0])))];

  return {
    openapi: '3.0.3',
    info: {
      title: 'Span Tech CRM API',
      version: '1.0.0',
      description: 'The REST API behind the Span Tech CRM: customers, pipeline, follow-ups, quotations, cost studies, mail intake, notifications and analytics. Generated from the running server\'s routes; sign in with POST /api/auth/login and the session cookie authenticates every other call.',
    },
    servers: [{ url: serverUrl }],
    tags: tagNames.sort().map((name) => ({ name })),
    components: {
      securitySchemes: {
        cookieAuth: { type: 'apiKey', in: 'cookie', name: 'spantech_session', description: 'Set by POST /api/auth/login.' },
      },
    },
    paths,
  };
}

/**
 * A reference page that reads the document above. No framework and no
 * network: the page is one file, so it works on a server with no internet.
 */
export function docsPage() {
  return `<!doctype html>
<html lang="en" dir="ltr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Span Tech CRM · API</title>
<style>
  :root { color-scheme: light dark; --bg: #f6f7f9; --card: #fff; --ink: #111827; --muted: #6b7280; --line: #e5e7eb; --brand: #1a56a7; }
  @media (prefers-color-scheme: dark) { :root { --bg: #0f172a; --card: #182234; --ink: #f3f4f6; --muted: #9ca3af; --line: #2b3546; --brand: #8fb8ee; } }
  * { box-sizing: border-box; }
  body { margin: 0; font: 14px/1.55 Inter, 'Segoe UI', system-ui, sans-serif; background: var(--bg); color: var(--ink); }
  header { position: sticky; top: 0; background: #0a2647; color: #fff; padding: .8rem 1.2rem; display: flex; gap: 1rem; align-items: center; z-index: 2; }
  header h1 { margin: 0; font-size: 1.05rem; }
  header input { margin-inline-start: auto; padding: .4rem .7rem; border-radius: 6px; border: 0; min-width: 260px; font: inherit; }
  header a { color: #cdd9e9; font-size: .82rem; }
  main { max-width: 1040px; margin: 0 auto; padding: 1.2rem; }
  .intro { color: var(--muted); margin: 0 0 1rem; }
  h2.tag { font-size: 1rem; margin: 1.6rem 0 .5rem; color: var(--brand); }
  details { background: var(--card); border: 1px solid var(--line); border-radius: 8px; margin-bottom: .45rem; overflow: hidden; }
  summary { display: flex; gap: .7rem; align-items: center; padding: .55rem .8rem; cursor: pointer; list-style: none; }
  summary::-webkit-details-marker { display: none; }
  .m { font-weight: 800; font-size: .72rem; padding: .15rem .45rem; border-radius: 4px; color: #fff; min-width: 58px; text-align: center; }
  .m.get { background: #178553; } .m.post { background: #1a56a7; } .m.put, .m.patch { background: #c9761a; } .m.delete { background: #c62828; }
  code.p { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: .86rem; }
  .s { color: var(--muted); margin-inline-start: auto; font-size: .82rem; text-align: end; }
  .body { padding: .2rem .9rem .9rem; border-top: 1px solid var(--line); font-size: .86rem; }
  .body p { margin: .5rem 0; white-space: pre-line; }
  .lock { font-size: .72rem; color: var(--muted); }
  table { border-collapse: collapse; margin: .4rem 0; }
  td, th { text-align: start; padding: .2rem .6rem .2rem 0; border-bottom: 1px solid var(--line); font-size: .82rem; }
  .try { margin-top: .5rem; display: flex; gap: .4rem; align-items: center; flex-wrap: wrap; }
  .try button { font: inherit; padding: .3rem .7rem; border-radius: 6px; border: 1px solid var(--line); background: var(--card); color: var(--ink); cursor: pointer; }
  pre { background: rgba(0,0,0,.06); padding: .6rem .8rem; border-radius: 6px; overflow: auto; max-height: 320px; font-size: .78rem; }
  .hidden { display: none; }
</style>
</head>
<body>
<header>
  <h1>Span Tech CRM · API reference</h1>
  <a href="/api/openapi.json">openapi.json</a>
  <input id="q" type="search" placeholder="Filter paths…" autocomplete="off">
</header>
<main>
  <p class="intro" id="intro"></p>
  <div id="list"></div>
</main>
<script>
(async function () {
  var res = await fetch('/api/openapi.json', { credentials: 'same-origin' });
  if (!res.ok) { document.getElementById('intro').textContent = 'Sign in to the CRM first, then reload this page.'; return; }
  var doc = await res.json();
  document.getElementById('intro').textContent = doc.info.description;
  var groups = {};
  Object.keys(doc.paths).forEach(function (path) {
    Object.keys(doc.paths[path]).forEach(function (method) {
      var op = doc.paths[path][method];
      var tag = op.tags[0];
      (groups[tag] = groups[tag] || []).push({ path: path, method: method, op: op });
    });
  });
  var list = document.getElementById('list');
  var esc = function (s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); };
  Object.keys(groups).sort().forEach(function (tag) {
    var h = document.createElement('h2'); h.className = 'tag'; h.textContent = tag; list.appendChild(h);
    groups[tag].sort(function (a, b) { return a.path.localeCompare(b.path) || a.method.localeCompare(b.method); }).forEach(function (row) {
      var d = document.createElement('details');
      d.dataset.key = (row.method + ' ' + row.path + ' ' + (row.op.summary || '')).toLowerCase();
      var params = (row.op.parameters || []).map(function (p) { return '<tr><td><code>' + esc(p.name) + '</code></td><td>' + esc(p.in) + '</td><td>' + esc((p.schema && (p.schema.enum ? p.schema.enum.join(' | ') : p.schema.type)) || '') + '</td></tr>'; }).join('');
      var secured = row.op.security && row.op.security.length;
      d.innerHTML = '<summary><span class="m ' + row.method + '">' + row.method.toUpperCase() + '</span><code class="p">' + esc(row.path) + '</code><span class="s">' + esc(row.op.summary) + (secured ? ' <span class="lock">🔒</span>' : '') + '</span></summary>'
        + '<div class="body"><p>' + esc(row.op.description || '') + '</p>'
        + (params ? '<table><tr><th>Parameter</th><th>In</th><th>Type</th></tr>' + params + '</table>' : '')
        + (row.op.requestBody ? '<p class="lock">Request body: ' + esc(Object.keys(row.op.requestBody.content).join(', ')) + '</p>' : '')
        + (row.method === 'get' && row.path.indexOf('{') < 0 && row.path !== '/api/events' ? '<div class="try"><button type="button" data-try="' + esc(row.path) + '">Try it</button><span class="lock">GET with your session</span></div><pre class="hidden"></pre>' : '')
        + '</div>';
      list.appendChild(d);
    });
  });
  list.addEventListener('click', async function (e) {
    var b = e.target.closest('button[data-try]'); if (!b) return;
    var pre = b.parentElement.nextElementSibling; pre.classList.remove('hidden'); pre.textContent = '…';
    try {
      var r = await fetch(b.dataset.try, { credentials: 'same-origin' });
      var ct = r.headers.get('content-type') || '';
      pre.textContent = r.status + ' ' + r.statusText + '\\n' + (ct.indexOf('json') >= 0 ? JSON.stringify(await r.json(), null, 2).slice(0, 6000) : '[' + ct + ']');
    } catch (err) { pre.textContent = String(err); }
  });
  document.getElementById('q').addEventListener('input', function (e) {
    var q = e.target.value.trim().toLowerCase();
    list.querySelectorAll('details').forEach(function (d) { d.style.display = !q || d.dataset.key.indexOf(q) >= 0 ? '' : 'none'; });
    list.querySelectorAll('h2.tag').forEach(function (h) {
      var any = false, n = h.nextElementSibling;
      while (n && n.tagName === 'DETAILS') { if (n.style.display !== 'none') any = true; n = n.nextElementSibling; }
      h.style.display = any ? '' : 'none';
    });
  });
}());
</script>
</body>
</html>`;
}
