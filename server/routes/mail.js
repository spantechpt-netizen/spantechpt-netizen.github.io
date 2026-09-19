import { all, get, insert, update, run, getSetting, setSetting, audit } from '../db.js';
import { requireAuth, requirePermission, can } from '../auth.js';
import { notFound, badRequest } from '../http.js';
import { encryptSecret, maskSecret } from '../secrets.js';
import { notify } from '../notifications.js';
import {
  listAccounts, testAccount, syncAccount, syncDueAccounts,
  listRequests, getRequest, requestCounts, convertRequest, captureMessage,
  listMessages, getMessage, mailboxCounts, queueMessage,
} from '../mailbox.js';
import { str, int, bool, oneOf, email as emailField } from '../validate.js';

const REQUEST_STATUS = ['new', 'assigned', 'converted', 'dismissed'];
const CAPTURE_CHANNELS = ['whatsapp', 'phone', 'other'];

export function register(router) {
  // ============================================================== accounts
  router.get('/api/mail/accounts', ({ user }) => {
    requirePermission(user, 'mail.manage');
    return { accounts: listAccounts() };
  });

  router.post('/api/mail/accounts', ({ body, user }) => {
    requirePermission(user, 'mail.manage');
    const password = str(body.password, 'password', { required: true, max: 500 });
    const id = insert('mail_accounts', {
      label: str(body.label, 'label', { required: true, max: 120 }),
      host: str(body.host, 'host', { required: true, max: 200 }),
      port: int(body.port, 'port', { min: 1, max: 65535, fallback: 993 }),
      secure: bool(body.secure, true) ? 1 : 0,
      username: str(body.username, 'username', { required: true, max: 200 }),
      password_enc: encryptSecret(password),
      folders: JSON.stringify(normaliseFolders(body.folders)),
      sync_minutes: int(body.sync_minutes, 'sync_minutes', { min: 1, max: 1440, fallback: 10 }),
      allow_self_signed: bool(body.allow_self_signed, false) ? 1 : 0,
      active: bool(body.active, true) ? 1 : 0,
      created_by: user.id,
    });
    audit(user.id, 'mail_account', id, 'create', { host: body.host });
    return { account: listAccounts().find((a) => a.id === id) };
  });

  router.patch('/api/mail/accounts/:id', ({ params, body, user }) => {
    requirePermission(user, 'mail.manage');
    const id = Number(params.id);
    if (!get('SELECT id FROM mail_accounts WHERE id = ?', id)) {
      throw notFound('Mail account not found', 'حساب البريد مش موجود');
    }
    update('mail_accounts', id, {
      label: str(body.label, 'label', { max: 120, fallback: undefined }),
      host: str(body.host, 'host', { max: 200, fallback: undefined }),
      port: int(body.port, 'port', { min: 1, max: 65535, fallback: undefined }),
      secure: body.secure === undefined ? undefined : (bool(body.secure, true) ? 1 : 0),
      username: str(body.username, 'username', { max: 200, fallback: undefined }),
      // An empty password field means "leave the stored one alone".
      password_enc: body.password ? encryptSecret(String(body.password)) : undefined,
      folders: body.folders === undefined ? undefined : JSON.stringify(normaliseFolders(body.folders)),
      sync_minutes: int(body.sync_minutes, 'sync_minutes', { min: 1, max: 1440, fallback: undefined }),
      allow_self_signed: body.allow_self_signed === undefined ? undefined : (bool(body.allow_self_signed, false) ? 1 : 0),
      active: body.active === undefined ? undefined : (bool(body.active, true) ? 1 : 0),
    });
    audit(user.id, 'mail_account', id, 'update');
    return { account: listAccounts().find((a) => a.id === id) };
  });

  router.delete('/api/mail/accounts/:id', ({ params, user }) => {
    requirePermission(user, 'mail.manage');
    const id = Number(params.id);
    run('DELETE FROM mail_accounts WHERE id = ?', id);
    audit(user.id, 'mail_account', id, 'delete');
    return { ok: true };
  });

  /** Connects and lists folders, so the settings screen can prove it works. */
  router.post('/api/mail/accounts/:id/test', async ({ params, user }) => {
    requirePermission(user, 'mail.manage');
    const account = get('SELECT * FROM mail_accounts WHERE id = ?', Number(params.id));
    if (!account) throw notFound('Mail account not found', 'حساب البريد مش موجود');
    const result = await testAccount(account);
    update('mail_accounts', account.id, { last_error: result.ok ? null : String(result.error).slice(0, 500) });
    return result;
  });

  router.post('/api/mail/accounts/:id/sync', async ({ params, body, user }) => {
    requirePermission(user, 'mail.manage');
    const id = Number(params.id);
    if (!get('SELECT id FROM mail_accounts WHERE id = ?', id)) {
      throw notFound('Mail account not found', 'حساب البريد مش موجود');
    }
    const summary = await syncAccount(id, {
      sinceDays: int(body.since_days, 'since_days', { min: 1, max: 3650, fallback: 30 }),
      limit: int(body.limit, 'limit', { min: 1, max: 1000, fallback: 200 }),
      backfill: bool(body.backfill, false),
    });
    return { summary };
  });

  /** Syncs every account that is due — the same pass the timer runs. */
  router.post('/api/mail/sync', async ({ user }) => {
    requirePermission(user, 'mail.manage');
    return { results: await syncDueAccounts() };
  });

  // =============================================================== capture
  /**
   * A request that arrived somewhere the CRM cannot read — WhatsApp, a phone
   * call, a conversation on site. Paste it in and it joins the same queue,
   * with the same extraction and the same triage behind it.
   */
  router.post('/api/mail/capture', async ({ body, user }) => {
    requirePermission(user, 'mail.view');
    const text = str(body.text, 'text', { required: true, min: 1, max: 40_000 });
    const { requestId, extraction } = await captureMessage({
      text,
      fromName: str(body.from_name, 'from_name', { max: 200 }) || null,
      fromPhone: str(body.from_phone, 'from_phone', { max: 40 }) || null,
      channel: oneOf(body.channel, 'channel', CAPTURE_CHANNELS, { fallback: 'whatsapp' }),
      userId: user.id,
    });
    return { request: getRequest(requestId), extraction };
  });

  // ============================================================== requests
  router.get('/api/mail/requests', ({ query, user }) => {
    requirePermission(user, 'mail.view');
    const status = oneOf(query.status, 'status', REQUEST_STATUS, { fallback: undefined });
    // Engineers see what was handed to them; triagers see the whole queue.
    const assignedTo = can(user, 'mail.triage') ? int(query.assigned_to, 'assigned_to', { min: 1, fallback: undefined }) : user.id;
    return {
      requests: listRequests({ status, assignedTo, limit: Number(query.limit) || 100 }),
      counts: requestCounts(),
    };
  });

  router.get('/api/mail/requests/:id', ({ params, user }) => {
    requirePermission(user, 'mail.view');
    const request = getRequest(Number(params.id));
    if (!request) throw notFound('Request not found', 'الطلب مش موجود');
    if (!can(user, 'mail.triage') && request.assigned_to !== user.id) {
      throw notFound('Request not found', 'الطلب مش موجود');
    }
    return { request };
  });

  /** The manager hands a request to an engineer. */
  router.post('/api/mail/requests/:id/assign', ({ params, body, user }) => {
    requirePermission(user, 'mail.triage');
    const id = Number(params.id);
    const request = getRequest(id);
    if (!request) throw notFound('Request not found', 'الطلب مش موجود');

    const assignee = int(body.assigned_to, 'assigned_to', { required: true, min: 1 });
    const target = get('SELECT id, name, name_ar FROM users WHERE id = ? AND active = 1', assignee);
    if (!target) throw badRequest('That engineer is not active', 'المهندس ده مش نشط');

    update('mail_requests', id, {
      status: 'assigned',
      assigned_to: assignee,
      assigned_by: user.id,
      assigned_at: new Date().toISOString(),
      notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }),
    });

    notify({
      userId: assignee,
      actorId: user.id,
      type: 'mail_request',
      titleAr: 'اتحوّلك طلب من الإيميل',
      titleEn: 'An email request was assigned to you',
      bodyAr: `${request.subject || ''} — ${request.from_name || request.from_email || ''}`,
      bodyEn: `${request.subject || ''} — ${request.from_name || request.from_email || ''}`,
      entity: 'mail_request',
      entityId: id,
      link: `requests/${id}`,
      severity: 'warning',
    });

    audit(user.id, 'mail_request', id, 'assign', { to: assignee });
    return { request: getRequest(id) };
  });

  /** Creates the customer, contact and opportunity from the extracted draft. */
  router.post('/api/mail/requests/:id/convert', ({ params, body, user }) => {
    requirePermission(user, 'mail.view');
    const id = Number(params.id);
    const request = getRequest(id);
    if (!request) throw notFound('Request not found', 'الطلب مش موجود');
    if (!can(user, 'mail.triage') && request.assigned_to !== user.id) {
      throw notFound('Request not found', 'الطلب مش موجود');
    }
    if (request.status === 'converted') {
      throw badRequest('This request was already converted', 'الطلب ده اتحوّل قبل كده');
    }
    requirePermission(user, 'opportunities.create');

    const ownerId = can(user, 'mail.triage')
      ? int(body.owner_id, 'owner_id', { min: 1, fallback: request.assigned_to || user.id })
      : user.id;

    const { customerId, opportunityId } = convertRequest(id, {
      overrides: body.overrides || {},
      ownerId,
      actorId: user.id,
    });

    audit(user.id, 'mail_request', id, 'convert', { customerId, opportunityId });
    return { request: getRequest(id), customer_id: customerId, opportunity_id: opportunityId };
  });

  router.post('/api/mail/requests/:id/status', ({ params, body, user }) => {
    requirePermission(user, 'mail.view');
    const id = Number(params.id);
    const request = getRequest(id);
    if (!request) throw notFound('Request not found', 'الطلب مش موجود');
    if (!can(user, 'mail.triage') && request.assigned_to !== user.id) {
      throw notFound('Request not found', 'الطلب مش موجود');
    }
    const status = oneOf(body.status, 'status', REQUEST_STATUS, { required: true });
    update('mail_requests', id, {
      status,
      notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }),
      handled_by: user.id,
      handled_at: new Date().toISOString(),
    });
    audit(user.id, 'mail_request', id, 'status', { to: status });
    return { request: getRequest(id) };
  });

  /** Re-runs extraction on an existing request, e.g. after adding an API key. */
  router.post('/api/mail/requests/:id/re-extract', async ({ params, user }) => {
    requirePermission(user, 'mail.triage');
    const id = Number(params.id);
    const request = getRequest(id);
    if (!request) throw notFound('Request not found', 'الطلب مش موجود');

    const { extractFromEmail } = await import('../extract.js');
    const settings = getSetting('ai', {}) || {};
    const extraction = await extractFromEmail({
      fromEmail: request.from_email,
      fromName: request.from_name,
      subject: request.subject,
      body: request.body_text,
      receivedAt: request.received_at,
    }, { useAi: Boolean(settings.api_key) });

    update('mail_requests', id, {
      extraction_json: JSON.stringify(extraction),
      confidence: extraction.confidence || 0,
      summary_ar: extraction.summary_ar || null,
      summary_en: extraction.summary_en || null,
    });
    return { request: getRequest(id) };
  });

  // ================================================================== AI key
  router.get('/api/mail/ai', ({ user }) => {
    requirePermission(user, 'mail.manage');
    const settings = getSetting('ai', {}) || {};
    return {
      ai: {
        enabled: settings.enabled !== false,
        model: settings.model || 'claude-sonnet-5',
        has_key: Boolean(settings.api_key),
        key_hint: settings.api_key ? maskSecret(settings.api_key) : '',
      },
    };
  });

  router.put('/api/mail/ai', ({ body, user }) => {
    requirePermission(user, 'mail.manage');
    const current = getSetting('ai', {}) || {};
    const next = {
      enabled: bool(body.enabled, current.enabled !== false),
      model: str(body.model, 'model', { max: 80, fallback: current.model || 'claude-sonnet-5' }),
      // An empty field leaves the stored key untouched; "clear" removes it.
      api_key: body.clear_key ? null : (body.api_key ? String(body.api_key).trim() : current.api_key || null),
    };
    setSetting('ai', next);
    audit(user.id, 'settings', null, 'update', { key: 'ai' });
    return {
      ai: {
        enabled: next.enabled,
        model: next.model,
        has_key: Boolean(next.api_key),
        key_hint: next.api_key ? maskSecret(next.api_key) : '',
      },
    };
  });

  // ============================================================== mailbox
  // The requests queue is what the filter let through. This is everything the
  // sync stored, so a message the filter passed over can still be found — and
  // put into the queue by hand if it turns out to matter.

  router.get('/api/mail/messages', ({ query, user }) => {
    requirePermission(user, 'mail.view_all');
    const { messages, total } = listMessages({
      accountId: int(query.account_id, 'account_id', { min: 1, fallback: undefined }),
      folder: str(query.folder, 'folder', { max: 200, fallback: undefined }) || undefined,
      search: str(query.q, 'q', { max: 200, fallback: undefined }) || undefined,
      only: oneOf(query.only, 'only', ['all', 'queued', 'other'], { fallback: 'all' }),
      limit: int(query.limit, 'limit', { min: 1, max: 200, fallback: 60 }),
      offset: int(query.offset, 'offset', { min: 0, max: 100000, fallback: 0 }),
    });
    return { messages, total, counts: mailboxCounts() };
  });

  router.get('/api/mail/messages/:id', ({ params, user }) => {
    requirePermission(user, 'mail.view_all');
    const message = getMessage(Number(params.id));
    if (!message) throw notFound('Message not found', 'الرسالة مش موجودة');
    return { message };
  });

  /** "This one is a request after all." */
  router.post('/api/mail/messages/:id/queue', async ({ params, user }) => {
    requirePermission(user, 'mail.view_all');
    requirePermission(user, 'mail.triage');
    const result = await queueMessage(Number(params.id), { userId: user.id });
    if (!result) throw notFound('Message not found', 'الرسالة مش موجودة');
    if (result.alreadyQueued) {
      throw badRequest(
        'That message is already in the requests queue.',
        'الرسالة دي موجودة في الطلبات بالفعل.',
      );
    }
    return { request: getRequest(result.requestId) };
  });

  /** Badge counts for the sidebar. */
  router.get('/api/mail/summary', ({ user }) => {
    requireAuth(user);
    if (!can(user, 'mail.view')) return { new: 0, assigned: 0, mine: 0 };
    const counts = requestCounts();
    return {
      ...counts,
      mine: get(
        "SELECT COUNT(*) AS n FROM mail_requests WHERE assigned_to = ? AND status = 'assigned'",
        user.id,
      ).n,
    };
  });

  void emailField;
  void all;
}

function normaliseFolders(value) {
  const list = Array.isArray(value)
    ? value
    : String(value || 'INBOX').split(',');
  const cleaned = list.map((f) => String(f).trim()).filter(Boolean).slice(0, 10);
  return cleaned.length ? cleaned : ['INBOX'];
}
