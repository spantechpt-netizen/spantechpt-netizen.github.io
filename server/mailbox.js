/**
 * Mailbox synchronisation.
 *
 * Polls each configured account over IMAP, stores anything new, decides
 * whether it needs a human, and files it in the incoming-requests queue with a
 * draft of the customer and project it describes.
 *
 * Nothing is created in the CRM automatically. A request sits in the queue
 * until someone assigns it and presses convert — an email is a claim, not a
 * fact, and a CRM that invents customers from spam is worse than no CRM.
 */
import { all, get, insert, run, update, getSetting, transaction, audit } from './db.js';
import { withImap, imapDate } from './imap.js';
import { parseMessage, decodeWords, parseAddresses, stripQuotedReply } from './mime.js';
import {
  extractFromEmail, looksLikeRfq, mentionsPostTension, domainOf, isPublicDomain, matchByPhone,
} from './extract.js';
import { decryptSecret } from './secrets.js';
import { notify } from './notifications.js';
import { broadcast } from './events.js';

/** Mail that is never worth a human's attention. */
const NOISE_PATTERNS = [
  /^(mailer-daemon|postmaster|no-?reply|noreply|do-?not-?reply|bounce|notification|newsletter|news|marketing|info-desk)@/i,
  /@(?:mailchimp|sendgrid|mailgun|sparkpost|amazonses|linkedin|facebookmail|twitter|jobalerts)\./i,
];
const NOISE_SUBJECTS = [
  /out of office/i, /automatic reply/i, /auto[- ]reply/i, /delivery status notification/i,
  /undeliverable/i, /mail delivery failed/i, /read receipt/i,
  /رسالة تلقائية/, /خارج المكتب/, /فشل تسليم/,
];

// ----------------------------------------------------------- customer link
/**
 * The customer a message belongs to, by address alone.
 *
 * An exact contact or company address wins; failing that, the company's own
 * domain (never a public one such as gmail.com, which would file half the
 * mailbox under one customer); failing that, a WhatsApp number. Names in the
 * text are not used here — a name is a guess, an address is a fact — so a
 * message is never filed under the wrong customer, only left unfiled.
 */
export function linkCustomer({ fromEmail, toEmails = [], fromPhone = null } = {}) {
  const addresses = [fromEmail, ...[].concat(toEmails || [])]
    .map((a) => String(a || '').trim().toLowerCase()).filter(Boolean);

  for (const address of addresses) {
    const hit = get(
      `SELECT c.id FROM contacts ct JOIN customers c ON c.id = ct.customer_id WHERE lower(ct.email) = ?
       UNION SELECT id FROM customers WHERE lower(email) = ?`,
      address, address,
    );
    if (hit) return hit.id;
  }

  for (const address of addresses) {
    const domain = domainOf(address);
    if (!domain || isPublicDomain(domain)) continue;
    const hit = get(
      `SELECT id FROM customers WHERE lower(email) LIKE ? OR lower(website) LIKE ?
       UNION SELECT c.id FROM contacts ct JOIN customers c ON c.id = ct.customer_id WHERE lower(ct.email) LIKE ?
       LIMIT 1`,
      `%@${domain}`, `%${domain}%`, `%@${domain}`,
    );
    if (hit) return hit.id;
  }

  if (fromPhone) {
    const byPhone = matchByPhone(fromPhone);
    if (byPhone.customer) return byPhone.customer.id;
  }
  return null;
}

/**
 * Files the messages that arrived before their sender was in the CRM. Runs
 * at start-up and whenever a contact gains an address, so adding a contact
 * pulls their past mail onto the customer's record.
 */
export function backfillCustomerLinks({ limit = 5000 } = {}) {
  const rows = all(
    `SELECT id, from_email, to_emails, from_phone FROM mail_messages
      WHERE customer_id IS NULL ORDER BY id DESC LIMIT ?`,
    limit,
  );
  let linked = 0;
  transaction(() => {
    for (const row of rows) {
      const customerId = linkCustomer({
        fromEmail: row.from_email,
        toEmails: String(row.to_emails || '').split(',').map((a) => a.trim()).filter(Boolean),
        fromPhone: row.from_phone,
      });
      if (!customerId) continue;
      run('UPDATE mail_messages SET customer_id = ? WHERE id = ?', customerId, row.id);
      linked += 1;
    }
  });
  return linked;
}

/** A customer's correspondence, newest first, with whether each became a request. */
export function listCustomerMail(customerId, { limit = 100 } = {}) {
  return all(
    `${MESSAGE_SELECT} WHERE m.customer_id = ?
      ORDER BY m.received_at DESC, m.id DESC LIMIT ?`,
    customerId, Math.min(Number(limit) || 100, 500),
  ).map(hydrateMessage);
}

export const customerMailCount = (customerId) =>
  get('SELECT COUNT(*) AS n FROM mail_messages WHERE customer_id = ?', customerId).n;

export const isNoise = (fromEmail, subject, headers = {}) => {
  if (headers['auto-submitted'] && headers['auto-submitted'] !== 'no') return true;
  if (headers['list-unsubscribe'] || headers['list-id']) return true;
  if (NOISE_PATTERNS.some((p) => p.test(String(fromEmail || '')))) return true;
  return NOISE_SUBJECTS.some((p) => p.test(String(subject || '')));
};

// ------------------------------------------------------------------ accounts
export const listAccounts = () => all(
  `SELECT id, label, host, port, secure, username, folders, active, sync_minutes,
          allow_self_signed, last_sync_at, last_error, state_json, created_at
     FROM mail_accounts WHERE channel = 'imap' ORDER BY id`,
).map((row) => ({
  ...row,
  folders: safeJson(row.folders, ['INBOX']),
  state: safeJson(row.state_json, {}),
  state_json: undefined,
}));

export const accountConfig = (account) => ({
  host: account.host,
  port: account.port,
  user: account.username,
  password: decryptSecret(account.password_enc),
  secure: Boolean(account.secure),
  // Internal mail servers often present a self-signed certificate. Turning
  // this on keeps the connection encrypted but stops verifying who is on the
  // other end, so it is off unless someone deliberately enables it.
  rejectUnauthorized: !account.allow_self_signed,
});

function safeJson(value, fallback) {
  if (!value) return fallback;
  try { return JSON.parse(value); } catch { return fallback; }
}

/** Opens a connection and lists folders — the "Test connection" button. */
export async function testAccount(account) {
  const config = accountConfig(account);
  if (!config.password) {
    return { ok: false, error: 'The stored password could not be decrypted. Enter it again.' };
  }
  try {
    const folders = await withImap(config, (client) => client.listFolders());
    return { ok: true, folders: folders.map((f) => f.name) };
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

// ---------------------------------------------------------------- ingestion

/**
 * Pulls new mail for one account.
 *
 * `sinceDays` bounds the very first sync so connecting a ten-year-old mailbox
 * does not drag in everything at once; after that the stored UID takes over.
 */
export async function syncAccount(accountId, { sinceDays = 30, limit = 200, backfill = false } = {}) {
  const account = get('SELECT * FROM mail_accounts WHERE id = ?', accountId);
  if (!account) throw new Error('Mail account not found');

  const folders = safeJson(account.folders, ['INBOX']);
  const state = safeJson(account.state_json, {});
  const config = accountConfig(account);
  if (!config.password) {
    update('mail_accounts', accountId, { last_error: 'Password could not be decrypted — re-enter it.' });
    throw new Error('Password could not be decrypted — re-enter it in Settings.');
  }

  const summary = { fetched: 0, stored: 0, queued: 0, skipped: 0, folders: {} };

  await withImap(config, async (client) => {
    for (const folder of folders) {
      let box;
      try {
        box = await client.select(folder, true);
      } catch {
        summary.folders[folder] = { error: 'not found' };
        continue;
      }

      const saved = state[folder] || {};
      // A changed UIDVALIDITY means the server renumbered; start that folder over.
      const continuing = !backfill && saved.lastUid && saved.uidValidity === box.uidValidity;

      const criteria = continuing
        ? `${saved.lastUid + 1}:*`
        : `SINCE ${imapDate(new Date(Date.now() - sinceDays * 86400_000))}`;

      let uids = await client.search(criteria);
      // "N:*" always returns at least the last UID even when nothing is new.
      if (continuing) uids = uids.filter((uid) => uid > saved.lastUid);

      // Importing history, one run does not reach a mailbox of ten thousand
      // messages. Skipping what is already stored means the next run picks up
      // where this one stopped and walks backwards through the folder,
      // instead of fetching the same newest few hundred every time.
      let remaining = 0;
      if (backfill) {
        const have = new Set(
          all('SELECT uid FROM mail_messages WHERE account_id = ? AND folder = ?', account.id, folder)
            .map((row) => row.uid),
        );
        uids = uids.filter((uid) => !have.has(uid));
      }

      uids.sort((a, b) => a - b);
      if (uids.length > limit) {
        remaining = uids.length - limit;
        uids = uids.slice(-limit);
      }

      if (!uids.length) {
        summary.folders[folder] = { fetched: 0 };
        state[folder] = { uidValidity: box.uidValidity, lastUid: saved.lastUid || box.uidNext - 1 || 0 };
        continue;
      }

      const messages = await client.fetchMessages(uids);
      summary.fetched += messages.length;

      let highest = saved.lastUid || 0;
      for (const message of messages) {
        highest = Math.max(highest, message.uid || 0);
        const stored = await storeMessage(account, folder, message);
        if (stored === 'stored') summary.stored += 1;
        else if (stored === 'queued') { summary.stored += 1; summary.queued += 1; }
        else summary.skipped += 1;
      }

      state[folder] = { uidValidity: box.uidValidity, lastUid: highest };
      summary.folders[folder] = { fetched: messages.length, remaining };
      summary.remaining = (summary.remaining || 0) + remaining;
    }
  });

  update('mail_accounts', accountId, {
    state_json: JSON.stringify(state),
    last_sync_at: new Date().toISOString(),
    last_error: null,
  });

  return summary;
}

/**
 * Stores one fetched message and, when it warrants attention, files a request.
 * Returns 'stored' | 'queued' | 'skipped'.
 */
async function storeMessage(account, folder, fetched) {
  const existing = get(
    'SELECT id FROM mail_messages WHERE account_id = ? AND folder = ? AND uid = ?',
    account.id, folder, fetched.uid,
  );
  if (existing) return 'skipped';

  const parsed = parseMessage(fetched.raw);
  const headers = parsed.headers;

  const subject = decodeWords(headers.subject || '').trim();
  const from = parseAddresses(headers.from)[0] || {};
  const toList = parseAddresses(headers.to).map((a) => a.email);
  const bodyFull = (parsed.text || '').trim();
  const body = stripQuotedReply(bodyFull);

  const receivedAt = parseDate(headers.date) || parseInternalDate(fetched.internalDate) || new Date().toISOString();

  const messageRowId = insert('mail_messages', {
    account_id: account.id,
    folder,
    uid: fetched.uid,
    customer_id: linkCustomer({ fromEmail: from.email, toEmails: toList }),
    message_id: (headers['message-id'] || '').trim() || null,
    in_reply_to: (headers['in-reply-to'] || '').trim() || null,
    from_email: from.email || null,
    from_name: from.name || null,
    to_emails: toList.join(', ') || null,
    subject: subject || null,
    body_text: bodyFull.slice(0, 40_000) || null,
    snippet: body.replace(/\s+/g, ' ').slice(0, 300) || null,
    received_at: receivedAt,
    has_attachments: parsed.attachments.length ? 1 : 0,
    attachments_json: parsed.attachments.length ? JSON.stringify(parsed.attachments) : null,
  });

  broadcast('mail', { id: messageRowId, customer_id: null, queued: false });

  // Filter out automated mail before spending anything on extraction.
  if (isNoise(from.email, subject, headers)) return 'stored';

  const text = `${subject}\n${body}`;
  const isRfq = looksLikeRfq(text);
  const isPt = mentionsPostTension(text);
  const isReply = /^((re|fw|fwd|rv)\s*:)/i.test(subject) || Boolean(headers['in-reply-to']);
  const knownSender = from.email
    ? get(
      `SELECT 1 AS ok FROM contacts WHERE lower(email) = ?
       UNION SELECT 1 FROM customers WHERE lower(email) = ?`,
      from.email, from.email,
    )
    : null;

  // Queue anything that asks for a price, mentions our trade, or is a reply
  // from somebody already in the CRM. Everything else is just archived mail.
  if (!isRfq && !isPt && !(isReply && knownSender)) return 'stored';

  const settings = getSetting('ai', {}) || {};
  const extraction = await extractFromEmail({
    fromEmail: from.email,
    fromName: from.name,
    subject,
    body,
    receivedAt,
  }, { useAi: Boolean(settings.api_key) && settings.enabled !== false });

  const requestId = insert('mail_requests', {
    message_id: messageRowId,
    status: 'new',
    kind: isRfq ? 'rfq' : (isReply ? 'reply' : 'other'),
    confidence: extraction.confidence || 0,
    extraction_json: JSON.stringify(extraction),
    summary_ar: extraction.summary_ar || null,
    summary_en: extraction.summary_en || null,
    customer_id: extraction.customer?.matched_id || null,
  });

  notifyTriagers({ subject, from, extraction, requestId });
  broadcast('mail', { id: messageRowId, request_id: requestId, queued: true });
  return 'queued';
}

// ------------------------------------------------------------------- capture
// Not every request arrives by email. A WhatsApp message, a phone call, a
// conversation on site — someone pastes it in and it joins the same queue,
// with the same extraction and the same triage behind it, rather than living
// in a notebook until it is forgotten.

/** The pseudo-account that owns pasted requests, created on first use. */
function captureAccountId() {
  const existing = get("SELECT id FROM mail_accounts WHERE channel = 'capture' LIMIT 1");
  if (existing) return existing.id;
  // It is never synced and never shown in Settings; it exists so a captured
  // message can hang off the same table as a fetched one.
  return insert('mail_accounts', {
    label: 'Captured requests',
    channel: 'capture',
    host: '-', port: 0, secure: 0,
    username: '-', password_enc: '',
    folders: '[]', active: 0, sync_minutes: 0,
  });
}

/** A WhatsApp message has no subject, so its first line stands in for one. */
function firstLine(text) {
  const line = String(text || '').split(/\r?\n/).find((l) => l.trim());
  return (line || '').trim().slice(0, 140);
}

export async function captureMessage({
  text, fromName = null, fromPhone = null, channel = 'whatsapp', userId = null,
} = {}) {
  const body = String(text || '').trim();
  if (!body) throw new Error('empty capture');

  const accountId = captureAccountId();
  const folder = channel;
  const last = get(
    'SELECT MAX(uid) AS uid FROM mail_messages WHERE account_id = ? AND folder = ?',
    accountId, folder,
  );
  const receivedAt = new Date().toISOString();
  const subject = firstLine(body);

  const messageRowId = insert('mail_messages', {
    account_id: accountId,
    channel,
    folder,
    uid: Number(last?.uid || 0) + 1,
    customer_id: linkCustomer({ fromPhone }),
    from_name: fromName,
    from_phone: fromPhone,
    subject: subject || null,
    body_text: body.slice(0, 40_000),
    snippet: body.replace(/\s+/g, ' ').slice(0, 300),
    received_at: receivedAt,
  });

  const settings = getSetting('ai', {}) || {};
  const extraction = await extractFromEmail({
    fromEmail: null,
    fromName,
    fromPhone,
    subject,
    body,
    receivedAt,
  }, { useAi: Boolean(settings.api_key) && settings.enabled !== false });

  // A person chose to paste this in, so it is queued whatever the wording —
  // unlike mail, where the filter exists to keep newsletters out.
  const requestId = insert('mail_requests', {
    message_id: messageRowId,
    status: 'new',
    kind: extraction.is_rfq ? 'rfq' : 'other',
    confidence: extraction.confidence || 0,
    extraction_json: JSON.stringify(extraction),
    summary_ar: extraction.summary_ar || null,
    summary_en: extraction.summary_en || null,
    customer_id: extraction.customer?.matched_id || null,
  });

  notifyTriagers({
    subject,
    from: { name: fromName, email: fromPhone },
    extraction,
    requestId,
    channel,
  });
  audit(userId, 'mail_request', requestId, 'capture', { channel, from: fromPhone || fromName });
  broadcast('mail', { id: messageRowId, request_id: requestId, queued: true, channel });

  return { requestId, extraction };
}

/** Tells whoever triages the queue that something new landed. */
function notifyTriagers({ subject, from, extraction, requestId, channel = 'email' }) {
  const CHANNEL_AR = { email: 'من الإيميل', whatsapp: 'من الواتساب', phone: 'من مكالمة', other: '' };
  const CHANNEL_EN = { email: 'from email', whatsapp: 'from WhatsApp', phone: 'from a call', other: '' };
  const recipients = all(
    `SELECT id, role, permissions FROM users WHERE active = 1 AND role IN ('admin', 'manager')`,
  );
  const who = extraction.customer?.name || from.name || from.email || 'عميل';
  const area = extraction.project?.area_sqm;

  for (const person of recipients) {
    notify({
      userId: person.id,
      type: 'mail_request',
      titleAr: extraction.is_rfq
        ? `طلب عرض سعر جديد ${CHANNEL_AR[channel] ?? ''}`.trim()
        : 'رسالة جديدة محتاجة متابعة',
      titleEn: extraction.is_rfq
        ? `New quotation request ${CHANNEL_EN[channel] ?? ''}`.trim()
        : 'New message needs attention',
      bodyAr: `${who} — ${subject}${area ? ` (${area} م²)` : ''}`,
      bodyEn: `${who} — ${subject}${area ? ` (${area} m²)` : ''}`,
      entity: 'mail_request',
      entityId: requestId,
      link: `requests/${requestId}`,
      severity: extraction.is_rfq ? 'warning' : 'info',
      dedupeKey: `mail_request_${requestId}`,
    });
  }
}

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(decodeWords(value));
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function parseInternalDate(value) {
  if (!value) return null;
  // IMAP: "15-Sep-2026 10:22:31 +0300"
  const parsed = new Date(String(value).replace(/^(\d{2})-(\w{3})-(\d{4})/, '$2 $1, $3'));
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

// --------------------------------------------------------------- scheduling
let running = false;

/** Syncs every active account whose interval has elapsed. */
export async function syncDueAccounts() {
  if (running) return { skipped: 'already running' };
  running = true;
  const results = {};
  try {
    for (const account of all("SELECT * FROM mail_accounts WHERE active = 1 AND channel = 'imap'")) {
      const last = account.last_sync_at ? new Date(account.last_sync_at).getTime() : 0;
      const due = Date.now() - last >= Math.max(account.sync_minutes, 1) * 60_000;
      if (!due) continue;
      try {
        results[account.label] = await syncAccount(account.id);
      } catch (error) {
        results[account.label] = { error: error.message };
        update('mail_accounts', account.id, {
          last_error: error.message.slice(0, 500),
          last_sync_at: new Date().toISOString(),
        });
      }
    }
  } finally {
    running = false;
  }
  return results;
}

// ----------------------------------------------------------- queue helpers
const REQUEST_SELECT = `
  SELECT r.*,
         m.subject, m.from_email, m.from_name, m.from_phone, m.snippet, m.body_text,
         m.received_at, m.has_attachments, m.attachments_json, m.to_emails,
         m.channel,
         a.label AS account_label,
         c.name_en AS customer_name, c.name_ar AS customer_name_ar,
         o.title  AS opportunity_title,
         q.number AS quotation_number,
         u.name   AS assignee_name, u.name_ar AS assignee_name_ar,
         ab.name  AS assigner_name
    FROM mail_requests r
    JOIN mail_messages m ON m.id = r.message_id
    JOIN mail_accounts a ON a.id = m.account_id
    LEFT JOIN customers c ON c.id = r.customer_id
    LEFT JOIN opportunities o ON o.id = r.opportunity_id
    LEFT JOIN quotations q ON q.id = r.quotation_id
    LEFT JOIN users u ON u.id = r.assigned_to
    LEFT JOIN users ab ON ab.id = r.assigned_by`;

// ---------------------------------------------------------- the whole mailbox
// Every message the sync fetched is stored, whether or not it looked like a
// price request — the filter only decides what reaches the triage queue. This
// is the rest of it: the inbox as it actually arrived, so nothing is lost
// behind a rule about what counts as a request.

const MESSAGE_SELECT = `
  SELECT m.id, m.account_id, m.channel, m.folder, m.subject, m.from_email, m.from_name,
         m.from_phone, m.to_emails, m.snippet, m.received_at, m.has_attachments,
         m.attachments_json,
         a.label AS account_label,
         r.id AS request_id, r.status AS request_status,
         m.customer_id, cu.name_en AS customer_name, cu.name_ar AS customer_name_ar
    FROM mail_messages m
    JOIN mail_accounts a ON a.id = m.account_id
    LEFT JOIN mail_requests r ON r.message_id = m.id
    LEFT JOIN customers cu ON cu.id = m.customer_id`;

/**
 * `only`: 'all' (everything), 'queued' (already a request) or 'other' (the
 * mail the filter passed over, which is what this screen is really for).
 */
export function listMessages({
  accountId, folder, search, only = 'all', limit = 60, offset = 0,
} = {}) {
  const where = [];
  const params = [];
  if (accountId) { where.push('m.account_id = ?'); params.push(accountId); }
  if (folder) { where.push('m.folder = ?'); params.push(folder); }
  if (search) {
    const like = `%${String(search).trim()}%`;
    where.push('(m.subject LIKE ? OR m.from_email LIKE ? OR m.from_name LIKE ? OR m.snippet LIKE ? OR m.body_text LIKE ?)');
    params.push(like, like, like, like, like);
  }
  if (only === 'queued') where.push('r.id IS NOT NULL');
  if (only === 'other') where.push('r.id IS NULL');
  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

  const rows = all(
    `${MESSAGE_SELECT} ${clause}
      ORDER BY m.received_at DESC, m.id DESC
      LIMIT ? OFFSET ?`,
    ...params, Math.min(Number(limit) || 60, 200), Math.max(Number(offset) || 0, 0),
  );

  const total = get(
    `SELECT COUNT(*) AS n
       FROM mail_messages m
       JOIN mail_accounts a ON a.id = m.account_id
       LEFT JOIN mail_requests r ON r.message_id = m.id ${clause}`,
    ...params,
  ).n;

  return { messages: rows.map(hydrateMessage), total };
}

export function getMessage(id) {
  const row = get(`${MESSAGE_SELECT} WHERE m.id = ?`, id);
  if (!row) return null;
  const body = get('SELECT body_text FROM mail_messages WHERE id = ?', id);
  return { ...hydrateMessage(row), body_text: body?.body_text || '' };
}

function hydrateMessage(row) {
  return {
    ...row,
    attachments: safeJson(row.attachments_json, []),
    attachments_json: undefined,
  };
}

/** How much mail is here, and how much of it the filter passed over. */
export const mailboxCounts = () => ({
  total: get('SELECT COUNT(*) AS n FROM mail_messages').n,
  queued: get('SELECT COUNT(*) AS n FROM mail_messages m JOIN mail_requests r ON r.message_id = m.id').n,
  other: get('SELECT COUNT(*) AS n FROM mail_messages m LEFT JOIN mail_requests r ON r.message_id = m.id WHERE r.id IS NULL').n,
});

/**
 * Puts a stored message into the triage queue by hand — for the ones the
 * filter passed over and a person can see are worth answering.
 */
export async function queueMessage(id, { userId = null } = {}) {
  const message = get('SELECT * FROM mail_messages WHERE id = ?', id);
  if (!message) return null;
  const already = get('SELECT id FROM mail_requests WHERE message_id = ?', id);
  if (already) return { requestId: already.id, alreadyQueued: true };

  const body = stripQuotedReply(message.body_text || '');
  const settings = getSetting('ai', {}) || {};
  const extraction = await extractFromEmail({
    fromEmail: message.from_email,
    fromName: message.from_name,
    fromPhone: message.from_phone,
    subject: message.subject || '',
    body,
    receivedAt: message.received_at,
  }, { useAi: Boolean(settings.api_key) && settings.enabled !== false });

  const requestId = insert('mail_requests', {
    message_id: message.id,
    status: 'new',
    kind: extraction.is_rfq ? 'rfq' : 'other',
    confidence: extraction.confidence || 0,
    extraction_json: JSON.stringify(extraction),
    summary_ar: extraction.summary_ar || null,
    summary_en: extraction.summary_en || null,
    customer_id: extraction.customer?.matched_id || null,
  });

  audit(userId, 'mail_request', requestId, 'queue_by_hand', { message_id: message.id });
  return { requestId, alreadyQueued: false };
}

export function listRequests({ status, assignedTo, limit = 100 } = {}) {
  const where = [];
  const params = [];
  if (status) { where.push('r.status = ?'); params.push(status); }
  if (assignedTo) { where.push('r.assigned_to = ?'); params.push(assignedTo); }
  const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

  return all(
    `${REQUEST_SELECT} ${clause}
     ORDER BY CASE r.status WHEN 'new' THEN 0 WHEN 'assigned' THEN 1 ELSE 2 END,
              r.confidence DESC, m.received_at DESC
     LIMIT ?`,
    ...params, Math.min(limit, 300),
  ).map(hydrateRequest);
}

export function getRequest(id) {
  const row = get(`${REQUEST_SELECT} WHERE r.id = ?`, id);
  return row ? hydrateRequest(row) : null;
}

function hydrateRequest(row) {
  return {
    ...row,
    extraction: safeJson(row.extraction_json, {}),
    attachments: safeJson(row.attachments_json, []),
    extraction_json: undefined,
    attachments_json: undefined,
  };
}

export const requestCounts = () => ({
  new: get("SELECT COUNT(*) AS n FROM mail_requests WHERE status = 'new'").n,
  assigned: get("SELECT COUNT(*) AS n FROM mail_requests WHERE status = 'assigned'").n,
  converted: get("SELECT COUNT(*) AS n FROM mail_requests WHERE status = 'converted'").n,
});

/**
 * Turns a triaged request into a real customer, contact and opportunity.
 * Existing records are reused rather than duplicated.
 */
export function convertRequest(requestId, { overrides = {}, ownerId, actorId }) {
  const request = getRequest(requestId);
  if (!request) throw new Error('Request not found');

  const extraction = request.extraction || {};
  const draft = {
    customer_name: overrides.customer_name ?? extraction.customer?.name,
    customer_id: overrides.customer_id ?? extraction.customer?.matched_id ?? null,
    country: overrides.country ?? extraction.project?.country ?? extraction.customer?.country ?? 'SA',
    city: overrides.city ?? extraction.project?.city ?? null,
    contact_name: overrides.contact_name ?? extraction.contact?.name,
    contact_email: overrides.contact_email ?? extraction.contact?.email ?? request.from_email,
    contact_phone: overrides.contact_phone ?? extraction.contact?.phones?.[0] ?? null,
    project_name: overrides.project_name ?? extraction.project?.name ?? request.subject,
    project_type: overrides.project_type ?? extraction.project?.type ?? null,
    area_sqm: overrides.area_sqm ?? extraction.project?.area_sqm ?? 0,
  };

  return transaction(() => {
    // --- customer
    let customerId = draft.customer_id;
    if (!customerId) {
      const name = String(draft.customer_name || request.from_name || request.from_email || 'Unknown').trim();
      const existing = get('SELECT id FROM customers WHERE name_en = ? COLLATE NOCASE', name);
      customerId = existing
        ? existing.id
        : insert('customers', {
          name_en: name,
          country: draft.country,
          city: draft.city,
          email: request.from_email,
          status: 'prospect',
          source: 'website',
          type: 'main_contractor',
          owner_id: ownerId,
          created_by: actorId,
          notes: `أضيف تلقائياً من إيميل: ${request.subject || ''}`.trim(),
        });
    }

    // --- contact
    if (draft.contact_email) {
      const existingContact = get(
        'SELECT id FROM contacts WHERE customer_id = ? AND lower(email) = ?',
        customerId, String(draft.contact_email).toLowerCase(),
      );
      if (!existingContact) {
        insert('contacts', {
          customer_id: customerId,
          name: draft.contact_name || draft.contact_email,
          email: draft.contact_email,
          mobile: draft.contact_phone,
          is_primary: get('SELECT COUNT(*) AS n FROM contacts WHERE customer_id = ?', customerId).n === 0 ? 1 : 0,
        });
      }
    }

    // --- opportunity
    const opportunityId = insert('opportunities', {
      title: String(draft.project_name || 'Untitled').slice(0, 200),
      customer_id: customerId,
      country: draft.country,
      city: draft.city,
      project_type: draft.project_type,
      area_sqm: Number(draft.area_sqm) || 0,
      stage: 'qualified',
      probability: 30,
      currency: { SA: 'SAR', EG: 'EGP', QA: 'QAR' }[draft.country] || 'SAR',
      source: 'website',
      owner_id: ownerId,
      created_by: actorId,
      notes: `من إيميل: ${request.subject || ''}`.trim(),
    });

    update('mail_requests', requestId, {
      status: 'converted',
      customer_id: customerId,
      opportunity_id: opportunityId,
      handled_by: actorId,
      handled_at: new Date().toISOString(),
    });

    return { customerId, opportunityId };
  });
}
