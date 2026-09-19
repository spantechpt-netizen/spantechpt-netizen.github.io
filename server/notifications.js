/**
 * Notifications and the reminder engine.
 *
 * Two sources feed the same inbox:
 *   1. Actions by people — a record assigned to you, a colleague's message,
 *      a quotation whose status changed.
 *   2. The sweep below — follow-ups falling due or going overdue, customers
 *      who have gone quiet ("missed contact"), and quotations about to expire.
 *
 * Every swept alert carries a `dedupe_key` so a reminder is raised once, not
 * on every pass.
 */
import { all, get, run, insert } from './db.js';
import { publish } from './events.js';

/** Inserts a notification, silently skipping duplicates of the same dedupe key. */
export function notify({
  userId, actorId = null, type, titleAr, titleEn,
  bodyAr = null, bodyEn = null, entity = null, entityId = null,
  link = null, severity = 'info', dedupeKey = null,
}) {
  if (!userId) return null;
  // Never notify someone about their own action.
  if (actorId && Number(actorId) === Number(userId)) return null;
  try {
    const id = insert('notifications', {
      user_id: userId,
      actor_id: actorId,
      type,
      title_ar: titleAr,
      title_en: titleEn,
      body_ar: bodyAr,
      body_en: bodyEn,
      entity,
      entity_id: entityId,
      link,
      severity,
      dedupe_key: dedupeKey,
    });
    // The bell in that person's open tabs learns of it now, not on the next poll.
    publish(userId, 'notification', { id, type, entity, entity_id: entityId, link, severity });
    return id;
  } catch (error) {
    // The unique index on (user_id, dedupe_key) rejects a repeat reminder.
    if (String(error.message || '').includes('UNIQUE')) return null;
    throw error;
  }
}

/** Notifies every active user except `exceptId`. Used for company-wide notices. */
export function notifyAll(payload, exceptId = null) {
  const users = all('SELECT id FROM users WHERE active = 1');
  for (const user of users) {
    if (exceptId && Number(user.id) === Number(exceptId)) continue;
    notify({ ...payload, userId: user.id });
  }
}

export function unreadCount(userId) {
  return get(
    'SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0',
    userId,
  ).n;
}

export function listNotifications(userId, { limit = 50, unreadOnly = false } = {}) {
  return all(
    `SELECT n.*, u.name AS actor_name, u.name_ar AS actor_name_ar
       FROM notifications n
       LEFT JOIN users u ON u.id = n.actor_id
      WHERE n.user_id = ? ${unreadOnly ? 'AND n.is_read = 0' : ''}
      ORDER BY n.is_read ASC, n.created_at DESC
      LIMIT ?`,
    userId, Math.min(limit, 200),
  );
}

export const markRead = (userId, id) =>
  run("UPDATE notifications SET is_read = 1, read_at = datetime('now') WHERE id = ? AND user_id = ?", id, userId).changes;

export const markAllRead = (userId) =>
  run("UPDATE notifications SET is_read = 1, read_at = datetime('now') WHERE user_id = ? AND is_read = 0", userId).changes;

export const deleteNotification = (userId, id) =>
  run('DELETE FROM notifications WHERE id = ? AND user_id = ?', id, userId).changes;

// ============================================================ event helpers
// Called from the route handlers when a person does something notable.

export function notifyAssignment({ actorId, userId, entity, entityId, name, link }) {
  const labels = {
    customer: ['عميل', 'customer'],
    opportunity: ['فرصة', 'opportunity'],
    quotation: ['عرض سعر', 'quotation'],
    activity: ['متابعة', 'follow-up'],
  };
  const [ar, en] = labels[entity] || ['سجل', 'record'];
  notify({
    userId, actorId, type: 'assigned',
    titleAr: `اتحوّلك ${ar} جديد`,
    titleEn: `A ${en} was assigned to you`,
    bodyAr: name, bodyEn: name,
    entity, entityId, link, severity: 'info',
  });
}

export function notifyQuoteStatus({ actorId, userId, quotation, status }) {
  const labels = {
    sent: ['اتبعت للعميل', 'was sent to the client', 'info'],
    under_review: ['بقى تحت الدراسة', 'is under review', 'info'],
    approved: ['اتعتمد 🎉', 'was approved 🎉', 'info'],
    rejected: ['اترفض', 'was rejected', 'danger'],
    cancelled: ['اتلغى', 'was cancelled', 'warning'],
    expired: ['خلصت صلاحيته', 'has expired', 'warning'],
  };
  const [ar, en, severity] = labels[status] || ['اتغيّرت حالته', 'changed status', 'info'];
  notify({
    userId, actorId, type: 'quote_status',
    titleAr: `عرض السعر ${quotation.number} ${ar}`,
    titleEn: `Quotation ${quotation.number} ${en}`,
    bodyAr: quotation.project_name_ar || quotation.project_name,
    bodyEn: quotation.project_name,
    entity: 'quotation', entityId: quotation.id,
    link: `quote/${quotation.id}`, severity,
  });
}

// ============================================================ reminder sweep

/**
 * Raises every reminder that is now due. Safe to call as often as you like —
 * the dedupe keys make repeat passes no-ops.
 * Returns a count per category, which the tests assert on.
 */
export function runReminderSweep() {
  const counts = { due: 0, overdue: 0, stale: 0, expiring: 0, expired: 0 };

  // ---------------------------------------------------- follow-ups due soon
  // "Soon" is each user's own lead time (default 24h).
  const dueSoon = all(
    `SELECT a.id, a.subject, a.due_at, a.owner_id, a.customer_id,
            u.reminder_lead_hours,
            c.name_en AS customer_name, c.name_ar AS customer_name_ar
       FROM activities a
       JOIN users u ON u.id = a.owner_id
       LEFT JOIN customers c ON c.id = a.customer_id
      WHERE a.done = 0
        AND a.due_at IS NOT NULL
        AND u.active = 1
        AND datetime(a.due_at) >= datetime('now')
        AND datetime(a.due_at) <= datetime('now', '+' || u.reminder_lead_hours || ' hours')`,
  );
  for (const row of dueSoon) {
    const created = notify({
      userId: row.owner_id, type: 'activity_due',
      titleAr: 'عندك متابعة قرّبت',
      titleEn: 'A follow-up is coming up',
      bodyAr: `${row.subject}${row.customer_name_ar || row.customer_name ? ` — ${row.customer_name_ar || row.customer_name}` : ''}`,
      bodyEn: `${row.subject}${row.customer_name ? ` — ${row.customer_name}` : ''}`,
      entity: 'activity', entityId: row.id, link: 'activities',
      severity: 'info', dedupeKey: `activity_due_${row.id}`,
    });
    if (created) counts.due += 1;
  }

  // ------------------------------------------------------- overdue follow-ups
  const overdue = all(
    `SELECT a.id, a.subject, a.due_at, a.owner_id,
            c.name_en AS customer_name, c.name_ar AS customer_name_ar
       FROM activities a
       JOIN users u ON u.id = a.owner_id
       LEFT JOIN customers c ON c.id = a.customer_id
      WHERE a.done = 0
        AND a.due_at IS NOT NULL
        AND u.active = 1
        AND datetime(a.due_at) < datetime('now')`,
  );
  for (const row of overdue) {
    const created = notify({
      userId: row.owner_id, type: 'activity_overdue',
      titleAr: 'متابعة فاتت معادها',
      titleEn: 'A follow-up is overdue',
      bodyAr: `${row.subject}${row.customer_name_ar || row.customer_name ? ` — ${row.customer_name_ar || row.customer_name}` : ''}`,
      bodyEn: `${row.subject}${row.customer_name ? ` — ${row.customer_name}` : ''}`,
      entity: 'activity', entityId: row.id, link: 'activities',
      severity: 'danger', dedupeKey: `activity_overdue_${row.id}`,
    });
    if (created) counts.overdue += 1;
  }

  // ------------------------------------------- missed contact (stale customers)
  // A live customer with no activity at all for N days and nothing scheduled.
  const stale = all(
    `SELECT c.id, c.name_en, c.name_ar, c.owner_id, u.stale_after_days,
            (SELECT MAX(COALESCE(a.done_at, a.due_at, a.created_at))
               FROM activities a WHERE a.customer_id = c.id) AS last_touch
       FROM customers c
       JOIN users u ON u.id = c.owner_id
      WHERE u.active = 1
        AND c.status IN ('target', 'prospect', 'active')
        AND NOT EXISTS (
          SELECT 1 FROM activities a WHERE a.customer_id = c.id AND a.done = 0
        )`,
  );
  const month = new Date().toISOString().slice(0, 7);
  for (const row of stale) {
    const days = Number(row.stale_after_days || 30);
    const last = row.last_touch ? new Date(row.last_touch).getTime() : null;
    const cutoff = Date.now() - days * 86400_000;
    // Never contacted at all also counts as missed contact.
    if (last !== null && last > cutoff) continue;

    const since = last
      ? Math.floor((Date.now() - last) / 86400_000)
      : null;
    const created = notify({
      userId: row.owner_id, type: 'stale_customer',
      titleAr: 'تواصل مفقود مع عميل',
      titleEn: 'Missed contact with a customer',
      bodyAr: since === null
        ? `${row.name_ar || row.name_en} — لسه مفيش أي تواصل متسجّل`
        : `${row.name_ar || row.name_en} — بقى ${since} يوم من غير تواصل`,
      bodyEn: since === null
        ? `${row.name_en} — no contact recorded yet`
        : `${row.name_en} — ${since} days with no contact`,
      entity: 'customer', entityId: row.id, link: 'customers',
      severity: 'warning',
      // At most one nudge per customer per calendar month.
      dedupeKey: `stale_customer_${row.id}_${month}`,
    });
    if (created) counts.stale += 1;
  }

  // -------------------------------------------------- quotations near expiry
  const expiring = all(
    `SELECT q.id, q.number, q.project_name, q.project_name_ar, q.owner_id, q.valid_days, q.issue_date
       FROM quotations q
       JOIN users u ON u.id = q.owner_id
      WHERE u.active = 1
        AND q.status IN ('sent', 'under_review')
        AND date(q.issue_date, '+' || q.valid_days || ' days') >= date('now')
        AND date(q.issue_date, '+' || q.valid_days || ' days') <= date('now', '+3 days')`,
  );
  for (const row of expiring) {
    const created = notify({
      userId: row.owner_id, type: 'quote_expiring',
      titleAr: 'عرض سعر قرّب يخلص صلاحيته',
      titleEn: 'A quotation is about to expire',
      bodyAr: `${row.number} — ${row.project_name_ar || row.project_name}`,
      bodyEn: `${row.number} — ${row.project_name}`,
      entity: 'quotation', entityId: row.id, link: `quote/${row.id}`,
      severity: 'warning', dedupeKey: `quote_expiring_${row.id}`,
    });
    if (created) counts.expiring += 1;
  }

  // ------------------------------------------- quotations past their validity
  const lapsed = all(
    `SELECT q.id, q.number, q.project_name, q.project_name_ar, q.owner_id
       FROM quotations q
      WHERE q.status IN ('sent', 'under_review')
        AND date(q.issue_date, '+' || q.valid_days || ' days') < date('now')`,
  );
  for (const row of lapsed) {
    run("UPDATE quotations SET status = 'expired', updated_at = datetime('now') WHERE id = ?", row.id);
    const created = notify({
      userId: row.owner_id, type: 'quote_expired',
      titleAr: 'عرض سعر خلصت صلاحيته',
      titleEn: 'A quotation has expired',
      bodyAr: `${row.number} — ${row.project_name_ar || row.project_name}`,
      bodyEn: `${row.number} — ${row.project_name}`,
      entity: 'quotation', entityId: row.id, link: `quote/${row.id}`,
      severity: 'warning', dedupeKey: `quote_expired_${row.id}`,
    });
    if (created) counts.expired += 1;
  }

  return counts;
}

/** Drops read notifications older than 60 days so the inbox stays small. */
export const purgeOldNotifications = () =>
  run("DELETE FROM notifications WHERE is_read = 1 AND created_at < datetime('now', '-60 days')").changes;
