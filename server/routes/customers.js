import { all, get, insert, update, run, nextCounter, audit } from '../db.js';
import { requireAuth, requirePermission, canSeeAll, assertCanEdit, can } from '../auth.js';
import { notFound, conflict } from '../http.js';
import { notifyAssignment } from '../notifications.js';
import {
  str, int, oneOf, email as emailField,
  COUNTRIES, CUSTOMER_TYPES, CUSTOMER_STATUS,
} from '../validate.js';

const SORTABLE = {
  name: 'c.name_en',
  created: 'c.created_at',
  updated: 'c.updated_at',
  rating: 'c.rating',
  country: 'c.country',
};

function loadCustomer(id) {
  const row = get(
    `SELECT c.*, u.name AS owner_name, u.name_ar AS owner_name_ar
       FROM customers c LEFT JOIN users u ON u.id = c.owner_id
      WHERE c.id = ?`,
    id,
  );
  if (!row) throw notFound('Customer not found', 'العميل غير موجود');
  return row;
}

function customerFields(body, { partial = false } = {}) {
  const req = (v) => (partial ? undefined : v);
  return {
    name_en: str(body.name_en, 'name_en', { required: !partial, max: 200, fallback: undefined }),
    name_ar: str(body.name_ar, 'name_ar', { max: 200, fallback: undefined }),
    type: oneOf(body.type, 'type', CUSTOMER_TYPES, { fallback: partial ? undefined : 'main_contractor' }),
    country: oneOf(body.country, 'country', COUNTRIES, { fallback: partial ? undefined : 'SA' }),
    city: str(body.city, 'city', { max: 80, fallback: undefined }),
    sector: str(body.sector, 'sector', { max: 60, fallback: undefined }),
    website: str(body.website, 'website', { max: 200, fallback: undefined }),
    phone: str(body.phone, 'phone', { max: 60, fallback: undefined }),
    email: body.email === undefined || body.email === '' ? undefined : emailField(body.email, 'email'),
    address: str(body.address, 'address', { max: 400, fallback: undefined }),
    tax_number: str(body.tax_number, 'tax_number', { max: 60, fallback: undefined }),
    cr_number: str(body.cr_number, 'cr_number', { max: 60, fallback: undefined }),
    status: oneOf(body.status, 'status', CUSTOMER_STATUS, { fallback: partial ? undefined : 'target' }),
    source: str(body.source, 'source', { max: 40, fallback: undefined }),
    rating: int(body.rating, 'rating', { min: 1, max: 5, fallback: partial ? undefined : 3 }),
    owner_id: body.owner_id === undefined ? undefined : int(body.owner_id, 'owner_id', { min: 1, fallback: null }),
    notes: str(body.notes, 'notes', { max: 4000, fallback: undefined }),
    req: req(undefined),
  };
}

export function register(router) {
  router.get('/api/customers', ({ query, user }) => {
    requirePermission(user, 'customers.view');
    const where = [];
    const params = [];

    if (query.q) {
      where.push('(c.name_en LIKE ? OR c.name_ar LIKE ? OR c.city LIKE ? OR c.code LIKE ?)');
      const like = `%${query.q}%`;
      params.push(like, like, like, like);
    }
    if (query.country) { where.push('c.country = ?'); params.push(query.country); }
    if (query.status) { where.push('c.status = ?'); params.push(query.status); }
    if (query.type) { where.push('c.type = ?'); params.push(query.type); }
    if (query.owner_id) { where.push('c.owner_id = ?'); params.push(Number(query.owner_id)); }
    // Engineers only see their own book of customers unless they ask for all.
    if (!canSeeAll(user) && query.scope !== 'all') {
      where.push('(c.owner_id = ? OR c.owner_id IS NULL)');
      params.push(user.id);
    }

    const sort = SORTABLE[query.sort] || 'c.updated_at';
    const dir = String(query.dir).toLowerCase() === 'asc' ? 'ASC' : 'DESC';
    const limit = Math.min(Number(query.limit) || 200, 500);
    const offset = Math.max(Number(query.offset) || 0, 0);
    const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const rows = all(
      `SELECT c.*, u.name AS owner_name, u.name_ar AS owner_name_ar,
              (SELECT COUNT(*) FROM opportunities o WHERE o.customer_id = c.id) AS opportunity_count,
              (SELECT COUNT(*) FROM quotations q WHERE q.customer_id = c.id) AS quotation_count,
              (SELECT MAX(a.due_at) FROM activities a WHERE a.customer_id = c.id AND a.done = 0) AS next_activity
         FROM customers c LEFT JOIN users u ON u.id = c.owner_id
         ${clause}
        ORDER BY ${sort} ${dir}
        LIMIT ? OFFSET ?`,
      ...params, limit, offset,
    );
    const total = get(`SELECT COUNT(*) AS n FROM customers c ${clause}`, ...params).n;
    return { customers: rows, total, limit, offset };
  });

  router.get('/api/customers/:id', ({ params, user }) => {
    requirePermission(user, 'customers.view');
    const id = Number(params.id);
    const customer = loadCustomer(id);
    return {
      customer,
      contacts: all('SELECT * FROM contacts WHERE customer_id = ? ORDER BY is_primary DESC, name', id),
      opportunities: all(
        `SELECT o.*, u.name AS owner_name FROM opportunities o
         LEFT JOIN users u ON u.id = o.owner_id
         WHERE o.customer_id = ? ORDER BY o.updated_at DESC`, id,
      ),
      quotations: all(
        `SELECT id, number, revision, project_name, issue_date, status, currency, total
           FROM quotations WHERE customer_id = ? ORDER BY issue_date DESC, id DESC`, id,
      ),
      activities: all(
        `SELECT a.*, u.name AS owner_name FROM activities a
         LEFT JOIN users u ON u.id = a.owner_id
         WHERE a.customer_id = ? ORDER BY a.done, a.due_at DESC LIMIT 50`, id,
      ),
    };
  });

  router.post('/api/customers', ({ body, user }) => {
    requirePermission(user, 'customers.create');
    const fields = customerFields(body);
    delete fields.req;
    const name = fields.name_en;
    const duplicate = get('SELECT id FROM customers WHERE name_en = ? COLLATE NOCASE', name);
    if (duplicate) {
      throw conflict(
        `A customer named "${name}" already exists`,
        `يوجد عميل مسجل بنفس الاسم "${name}"`,
      );
    }
    const id = insert('customers', {
      ...fields,
      code: `C-${String(nextCounter('customer')).padStart(4, '0')}`,
      owner_id: fields.owner_id ?? user.id,
      created_by: user.id,
    });
    audit(user.id, 'customer', id, 'create', { name });
    const created = loadCustomer(id);
    notifyAssignment({
      actorId: user.id, userId: created.owner_id,
      entity: 'customer', entityId: id, name, link: 'customers',
    });
    return { customer: created };
  });

  router.patch('/api/customers/:id', ({ params, body, user }) => {
    requirePermission(user, 'customers.edit');
    const id = Number(params.id);
    const existing = loadCustomer(id);
    assertCanEdit(user, existing.owner_id);
    const fields = customerFields(body, { partial: true });
    delete fields.req;
    // Only managers may reassign a customer to another engineer.
    if (fields.owner_id !== undefined && !can(user, 'customers.assign')) delete fields.owner_id;
    update('customers', id, fields);
    audit(user.id, 'customer', id, 'update');
    const saved = loadCustomer(id);
    if (fields.owner_id !== undefined && Number(fields.owner_id) !== Number(existing.owner_id)) {
      notifyAssignment({
        actorId: user.id, userId: saved.owner_id,
        entity: 'customer', entityId: id, name: saved.name_en, link: 'customers',
      });
    }
    return { customer: saved };
  });

  router.delete('/api/customers/:id', ({ params, user }) => {
    requirePermission(user, 'customers.delete');
    const id = Number(params.id);
    loadCustomer(id);
    run('DELETE FROM customers WHERE id = ?', id);
    audit(user.id, 'customer', id, 'delete');
    return { ok: true };
  });

  // ---------------------------------------------------------------- contacts
  router.post('/api/customers/:id/contacts', ({ params, body, user }) => {
    requirePermission(user, 'customers.edit');
    const customerId = Number(params.id);
    const customer = loadCustomer(customerId);
    assertCanEdit(user, customer.owner_id);
    const isPrimary = body.is_primary ? 1 : 0;
    if (isPrimary) run('UPDATE contacts SET is_primary = 0 WHERE customer_id = ?', customerId);
    const id = insert('contacts', {
      customer_id: customerId,
      name: str(body.name, 'name', { required: true, max: 120 }),
      name_ar: str(body.name_ar, 'name_ar', { max: 120 }),
      title: str(body.title, 'title', { max: 120 }),
      phone: str(body.phone, 'phone', { max: 60 }),
      mobile: str(body.mobile, 'mobile', { max: 60 }),
      email: body.email ? emailField(body.email, 'email') : null,
      is_primary: isPrimary,
      notes: str(body.notes, 'notes', { max: 2000 }),
    });
    return { contact: get('SELECT * FROM contacts WHERE id = ?', id) };
  });

  router.patch('/api/contacts/:id', ({ params, body, user }) => {
    requirePermission(user, 'customers.edit');
    const id = Number(params.id);
    const contact = get('SELECT * FROM contacts WHERE id = ?', id);
    if (!contact) throw notFound('Contact not found', 'جهة الاتصال غير موجودة');
    const customer = loadCustomer(contact.customer_id);
    assertCanEdit(user, customer.owner_id);
    if (body.is_primary) run('UPDATE contacts SET is_primary = 0 WHERE customer_id = ?', contact.customer_id);
    update('contacts', id, {
      name: str(body.name, 'name', { max: 120, fallback: undefined }),
      name_ar: str(body.name_ar, 'name_ar', { max: 120, fallback: undefined }),
      title: str(body.title, 'title', { max: 120, fallback: undefined }),
      phone: str(body.phone, 'phone', { max: 60, fallback: undefined }),
      mobile: str(body.mobile, 'mobile', { max: 60, fallback: undefined }),
      email: body.email === undefined ? undefined : (body.email ? emailField(body.email, 'email') : null),
      is_primary: body.is_primary === undefined ? undefined : (body.is_primary ? 1 : 0),
      notes: str(body.notes, 'notes', { max: 2000, fallback: undefined }),
    });
    return { contact: get('SELECT * FROM contacts WHERE id = ?', id) };
  });

  router.delete('/api/contacts/:id', ({ params, user }) => {
    requirePermission(user, 'customers.edit');
    const id = Number(params.id);
    const contact = get('SELECT * FROM contacts WHERE id = ?', id);
    if (!contact) throw notFound('Contact not found', 'جهة الاتصال غير موجودة');
    const customer = loadCustomer(contact.customer_id);
    assertCanEdit(user, customer.owner_id);
    run('DELETE FROM contacts WHERE id = ?', id);
    return { ok: true };
  });
}
