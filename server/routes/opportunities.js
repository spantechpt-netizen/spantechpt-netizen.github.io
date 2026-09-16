import { all, get, insert, update, run, nextCounter, audit } from '../db.js';
import { requireAuth, requireRole, canSeeAll, assertCanEdit } from '../auth.js';
import { notFound, badRequest } from '../http.js';
import { notifyAssignment } from '../notifications.js';
import { str, num, int, oneOf, date, COUNTRIES, STAGES, CURRENCIES } from '../validate.js';

/** Default win probability per stage, applied when the user does not set one. */
const STAGE_PROBABILITY = { new: 10, qualified: 30, quoted: 50, negotiation: 75, won: 100, lost: 0 };

function loadOpportunity(id) {
  const row = get(
    `SELECT o.*, c.name_en AS customer_name, c.name_ar AS customer_name_ar,
            u.name AS owner_name, u.name_ar AS owner_name_ar,
            ct.name AS contact_name, ct.mobile AS contact_mobile
       FROM opportunities o
       JOIN customers c ON c.id = o.customer_id
       LEFT JOIN users u ON u.id = o.owner_id
       LEFT JOIN contacts ct ON ct.id = o.contact_id
      WHERE o.id = ?`,
    id,
  );
  if (!row) throw notFound('Opportunity not found', 'الفرصة غير موجودة');
  return row;
}

export function register(router) {
  router.get('/api/opportunities', ({ query, user }) => {
    requireAuth(user);
    const where = [];
    const params = [];

    if (query.q) {
      where.push('(o.title LIKE ? OR o.title_ar LIKE ? OR c.name_en LIKE ? OR o.code LIKE ?)');
      const like = `%${query.q}%`;
      params.push(like, like, like, like);
    }
    if (query.stage) { where.push('o.stage = ?'); params.push(query.stage); }
    if (query.country) { where.push('o.country = ?'); params.push(query.country); }
    if (query.customer_id) { where.push('o.customer_id = ?'); params.push(Number(query.customer_id)); }
    if (query.owner_id) { where.push('o.owner_id = ?'); params.push(Number(query.owner_id)); }
    if (query.open === '1') { where.push("o.stage NOT IN ('won','lost')"); }
    if (!canSeeAll(user) && query.scope !== 'all') {
      where.push('(o.owner_id = ? OR o.owner_id IS NULL)');
      params.push(user.id);
    }
    const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const rows = all(
      `SELECT o.*, c.name_en AS customer_name, c.name_ar AS customer_name_ar,
              u.name AS owner_name, u.name_ar AS owner_name_ar,
              (SELECT COUNT(*) FROM quotations q WHERE q.opportunity_id = o.id) AS quotation_count,
              (SELECT MIN(a.due_at) FROM activities a WHERE a.opportunity_id = o.id AND a.done = 0) AS next_activity
         FROM opportunities o
         JOIN customers c ON c.id = o.customer_id
         LEFT JOIN users u ON u.id = o.owner_id
         ${clause}
        ORDER BY o.updated_at DESC
        LIMIT 500`,
      ...params,
    );
    return { opportunities: rows };
  });

  router.get('/api/opportunities/:id', ({ params, user }) => {
    requireAuth(user);
    const id = Number(params.id);
    return {
      opportunity: loadOpportunity(id),
      quotations: all(
        `SELECT id, number, revision, project_name, issue_date, status, currency, total, net_amount
           FROM quotations WHERE opportunity_id = ? ORDER BY revision DESC, id DESC`, id,
      ),
      activities: all(
        `SELECT a.*, u.name AS owner_name FROM activities a
         LEFT JOIN users u ON u.id = a.owner_id
         WHERE a.opportunity_id = ? ORDER BY a.done, a.due_at DESC`, id,
      ),
    };
  });

  router.post('/api/opportunities', ({ body, user }) => {
    requireRole(user, 'engineer');
    const customerId = int(body.customer_id, 'customer_id', { required: true, min: 1 });
    const customer = get('SELECT * FROM customers WHERE id = ?', customerId);
    if (!customer) throw notFound('Customer not found', 'العميل غير موجود');

    const stage = oneOf(body.stage, 'stage', STAGES, { fallback: 'new' });
    const id = insert('opportunities', {
      code: `OPP-${String(nextCounter('opportunity')).padStart(4, '0')}`,
      title: str(body.title, 'title', { required: true, max: 200 }),
      title_ar: str(body.title_ar, 'title_ar', { max: 200 }),
      customer_id: customerId,
      contact_id: int(body.contact_id, 'contact_id', { min: 1, fallback: null }),
      country: oneOf(body.country, 'country', COUNTRIES, { fallback: customer.country }),
      city: str(body.city, 'city', { max: 80, fallback: customer.city }),
      project_type: str(body.project_type, 'project_type', { max: 40 }),
      area_sqm: num(body.area_sqm, 'area_sqm', { min: 0, fallback: 0 }),
      stage,
      probability: int(body.probability, 'probability', { min: 0, max: 100, fallback: STAGE_PROBABILITY[stage] }),
      expected_value: num(body.expected_value, 'expected_value', { min: 0, fallback: 0 }),
      currency: oneOf(body.currency, 'currency', CURRENCIES, { fallback: 'SAR' }),
      expected_close: date(body.expected_close, 'expected_close'),
      source: str(body.source, 'source', { max: 40, fallback: customer.source }),
      owner_id: int(body.owner_id, 'owner_id', { min: 1, fallback: user.id }),
      notes: str(body.notes, 'notes', { max: 4000 }),
      created_by: user.id,
    });
    audit(user.id, 'opportunity', id, 'create');
    const created = loadOpportunity(id);
    notifyAssignment({
      actorId: user.id, userId: created.owner_id,
      entity: 'opportunity', entityId: id, name: created.title, link: 'pipeline',
    });
    return { opportunity: created };
  });

  router.patch('/api/opportunities/:id', ({ params, body, user }) => {
    requireRole(user, 'engineer');
    const id = Number(params.id);
    const existing = loadOpportunity(id);
    assertCanEdit(user, existing.owner_id);

    const stage = oneOf(body.stage, 'stage', STAGES, { fallback: undefined });
    if (stage === 'lost' && !body.lost_reason && !existing.lost_reason) {
      throw badRequest('A reason is required when marking an opportunity as lost', 'يجب تحديد سبب الخسارة عند إغلاق الفرصة كخسارة');
    }

    const fields = {
      title: str(body.title, 'title', { max: 200, fallback: undefined }),
      title_ar: str(body.title_ar, 'title_ar', { max: 200, fallback: undefined }),
      contact_id: body.contact_id === undefined ? undefined : int(body.contact_id, 'contact_id', { min: 1, fallback: null }),
      country: oneOf(body.country, 'country', COUNTRIES, { fallback: undefined }),
      city: str(body.city, 'city', { max: 80, fallback: undefined }),
      project_type: str(body.project_type, 'project_type', { max: 40, fallback: undefined }),
      area_sqm: num(body.area_sqm, 'area_sqm', { min: 0, fallback: undefined }),
      stage,
      expected_value: num(body.expected_value, 'expected_value', { min: 0, fallback: undefined }),
      currency: oneOf(body.currency, 'currency', CURRENCIES, { fallback: undefined }),
      expected_close: body.expected_close === undefined ? undefined : date(body.expected_close, 'expected_close'),
      source: str(body.source, 'source', { max: 40, fallback: undefined }),
      notes: str(body.notes, 'notes', { max: 4000, fallback: undefined }),
      lost_reason: str(body.lost_reason, 'lost_reason', { max: 60, fallback: undefined }),
      lost_to: str(body.lost_to, 'lost_to', { max: 200, fallback: undefined }),
    };
    if (canSeeAll(user) && body.owner_id !== undefined) {
      fields.owner_id = int(body.owner_id, 'owner_id', { min: 1, fallback: null });
    }
    // Moving stage resets probability unless the caller supplies one explicitly.
    if (body.probability !== undefined) {
      fields.probability = int(body.probability, 'probability', { min: 0, max: 100 });
    } else if (stage) {
      fields.probability = STAGE_PROBABILITY[stage];
    }
    if (stage === 'won' || stage === 'lost') {
      fields.closed_at = new Date().toISOString().slice(0, 10);
    } else if (stage) {
      fields.closed_at = null;
    }

    update('opportunities', id, fields);
    if (stage && stage !== existing.stage) {
      audit(user.id, 'opportunity', id, 'stage_change', { from: existing.stage, to: stage });
    }
    const saved = loadOpportunity(id);
    if (fields.owner_id !== undefined && Number(fields.owner_id) !== Number(existing.owner_id)) {
      notifyAssignment({
        actorId: user.id, userId: saved.owner_id,
        entity: 'opportunity', entityId: id, name: saved.title, link: 'pipeline',
      });
    }
    return { opportunity: saved };
  });

  router.delete('/api/opportunities/:id', ({ params, user }) => {
    requireRole(user, 'manager');
    const id = Number(params.id);
    loadOpportunity(id);
    run('DELETE FROM opportunities WHERE id = ?', id);
    audit(user.id, 'opportunity', id, 'delete');
    return { ok: true };
  });
}
