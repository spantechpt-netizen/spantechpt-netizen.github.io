import { all, get, insert, update, run, audit } from '../db.js';
import { requireAuth, requireRole, canSeeAll, assertCanEdit } from '../auth.js';
import { notFound } from '../http.js';
import { notifyAssignment } from '../notifications.js';
import { str, int, oneOf, datetime, bool, ACTIVITY_TYPES } from '../validate.js';

const SELECT_ACTIVITY = `
  SELECT a.*,
         c.name_en AS customer_name, c.name_ar AS customer_name_ar,
         o.title   AS opportunity_title,
         q.number  AS quotation_number,
         ct.name   AS contact_name, ct.mobile AS contact_mobile, ct.email AS contact_email,
         u.name    AS owner_name,  u.name_ar AS owner_name_ar
    FROM activities a
    LEFT JOIN customers     c  ON c.id  = a.customer_id
    LEFT JOIN opportunities o  ON o.id  = a.opportunity_id
    LEFT JOIN quotations    q  ON q.id  = a.quotation_id
    LEFT JOIN contacts      ct ON ct.id = a.contact_id
    LEFT JOIN users         u  ON u.id  = a.owner_id`;

function loadActivity(id) {
  const row = get(`${SELECT_ACTIVITY} WHERE a.id = ?`, id);
  if (!row) throw notFound('Activity not found', 'النشاط غير موجود');
  return row;
}

export function register(router) {
  router.get('/api/activities', ({ query, user }) => {
    requireAuth(user);
    const where = [];
    const params = [];

    if (query.customer_id) { where.push('a.customer_id = ?'); params.push(Number(query.customer_id)); }
    if (query.opportunity_id) { where.push('a.opportunity_id = ?'); params.push(Number(query.opportunity_id)); }
    if (query.type) { where.push('a.type = ?'); params.push(query.type); }
    if (query.done === '0' || query.done === '1') { where.push('a.done = ?'); params.push(Number(query.done)); }
    if (query.owner_id) { where.push('a.owner_id = ?'); params.push(Number(query.owner_id)); }
    if (!canSeeAll(user) && query.scope !== 'all') {
      where.push('(a.owner_id = ? OR a.owner_id IS NULL)');
      params.push(user.id);
    }

    // `bucket` powers the follow-up centre: overdue / today / upcoming.
    if (query.bucket === 'overdue') {
      where.push("a.done = 0 AND a.due_at IS NOT NULL AND datetime(a.due_at) < datetime('now')");
    } else if (query.bucket === 'today') {
      where.push("a.done = 0 AND date(a.due_at) = date('now')");
    } else if (query.bucket === 'upcoming') {
      where.push("a.done = 0 AND date(a.due_at) > date('now')");
    }

    const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';
    const limit = Math.min(Number(query.limit) || 300, 500);
    const rows = all(
      `${SELECT_ACTIVITY} ${clause}
       ORDER BY a.done ASC, (a.due_at IS NULL) ASC, a.due_at ASC
       LIMIT ?`,
      ...params, limit,
    );
    return { activities: rows };
  });

  /** Counts for the dashboard badges, always scoped to what the user may see. */
  router.get('/api/activities/summary', ({ user }) => {
    requireAuth(user);
    const scope = canSeeAll(user) ? '' : 'AND (owner_id = ? OR owner_id IS NULL)';
    const params = canSeeAll(user) ? [] : [user.id];
    const count = (condition) =>
      get(`SELECT COUNT(*) AS n FROM activities WHERE ${condition} ${scope}`, ...params).n;
    return {
      overdue: count("done = 0 AND due_at IS NOT NULL AND datetime(due_at) < datetime('now')"),
      today: count("done = 0 AND date(due_at) = date('now')"),
      upcoming: count("done = 0 AND date(due_at) > date('now')"),
      no_date: count('done = 0 AND due_at IS NULL'),
    };
  });

  router.post('/api/activities', ({ body, user }) => {
    requireRole(user, 'engineer');
    const id = insert('activities', {
      type: oneOf(body.type, 'type', ACTIVITY_TYPES, { fallback: 'call' }),
      subject: str(body.subject, 'subject', { required: true, max: 250 }),
      notes: str(body.notes, 'notes', { max: 4000 }),
      customer_id: int(body.customer_id, 'customer_id', { min: 1, fallback: null }),
      opportunity_id: int(body.opportunity_id, 'opportunity_id', { min: 1, fallback: null }),
      quotation_id: int(body.quotation_id, 'quotation_id', { min: 1, fallback: null }),
      contact_id: int(body.contact_id, 'contact_id', { min: 1, fallback: null }),
      owner_id: int(body.owner_id, 'owner_id', { min: 1, fallback: user.id }),
      due_at: datetime(body.due_at, 'due_at'),
      done: bool(body.done) ? 1 : 0,
      done_at: bool(body.done) ? new Date().toISOString() : null,
      outcome: str(body.outcome, 'outcome', { max: 1000 }),
      created_by: user.id,
    });
    const created = loadActivity(id);
    notifyAssignment({
      actorId: user.id, userId: created.owner_id,
      entity: 'activity', entityId: id, name: created.subject, link: 'activities',
    });
    return { activity: created };
  });

  router.patch('/api/activities/:id', ({ params, body, user }) => {
    requireRole(user, 'engineer');
    const id = Number(params.id);
    const existing = loadActivity(id);
    assertCanEdit(user, existing.owner_id);

    const fields = {
      type: oneOf(body.type, 'type', ACTIVITY_TYPES, { fallback: undefined }),
      subject: str(body.subject, 'subject', { max: 250, fallback: undefined }),
      notes: str(body.notes, 'notes', { max: 4000, fallback: undefined }),
      due_at: body.due_at === undefined ? undefined : datetime(body.due_at, 'due_at'),
      outcome: str(body.outcome, 'outcome', { max: 1000, fallback: undefined }),
      contact_id: body.contact_id === undefined ? undefined : int(body.contact_id, 'contact_id', { min: 1, fallback: null }),
    };
    if (canSeeAll(user) && body.owner_id !== undefined) {
      fields.owner_id = int(body.owner_id, 'owner_id', { min: 1, fallback: null });
    }
    if (body.done !== undefined) {
      const done = bool(body.done);
      fields.done = done ? 1 : 0;
      fields.done_at = done ? new Date().toISOString() : null;
    }
    update('activities', id, fields);
    return { activity: loadActivity(id) };
  });

  router.delete('/api/activities/:id', ({ params, user }) => {
    requireRole(user, 'engineer');
    const id = Number(params.id);
    const existing = loadActivity(id);
    assertCanEdit(user, existing.owner_id);
    run('DELETE FROM activities WHERE id = ?', id);
    audit(user.id, 'activity', id, 'delete');
    return { ok: true };
  });
}
