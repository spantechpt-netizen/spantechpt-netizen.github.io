import { all, get, insert, update, run, transaction, nextCounter, getSetting, audit } from '../db.js';
import { requireAuth, requirePermission, canSeeAll, assertCanEdit, can } from '../auth.js';
import { notFound, badRequest } from '../http.js';
import { notifyAssignment, notifyQuoteStatus } from '../notifications.js';
import { computeTotals, amountInWords, round2 } from '../pricing.js';
import {
  COUNTRY_DEFAULTS, DEFAULT_ITEM, SCOPE, PAYMENT_TERMS, CONDITIONS, INTRO,
  PRICE_ADJUSTMENT_CLAUSE, COMPANY, branchFor,
  DUCT_MATERIALS, DUCT_TYPES, defaultDuctType, applyDuctMaterial,
} from '../templates.js';
import {
  str, num, int, oneOf, date, bool, jsonField,
  COUNTRIES, CURRENCIES, QUOTE_STATUS,
} from '../validate.js';
import { readFileSync } from 'node:fs';
import { computeStudy, defaultStudy, CONVENTIONAL_SYSTEMS, CONVENTIONAL_KEYS } from '../study.js';
import { saveDrawing, deleteDrawingFile, drawingPath, DRAWING_KINDS } from '../uploads.js';

const SELECT_QUOTE = `
  SELECT q.*,
         c.name_en AS customer_name, c.name_ar AS customer_name_ar,
         c.address AS customer_address, c.tax_number AS customer_tax_number,
         o.title   AS opportunity_title, o.area_sqm AS opportunity_area,
         ct.name   AS contact_name, ct.title AS contact_title, ct.mobile AS contact_mobile, ct.email AS contact_email,
         u.name    AS owner_name, u.name_ar AS owner_name_ar,
         u.title   AS owner_title, u.title_ar AS owner_title_ar,
         u.phone   AS owner_phone, u.email AS owner_email
    FROM quotations q
    JOIN customers c ON c.id = q.customer_id
    LEFT JOIN opportunities o ON o.id = q.opportunity_id
    LEFT JOIN contacts ct ON ct.id = q.contact_id
    LEFT JOIN users u ON u.id = q.owner_id`;

const countrySettings = () => ({ ...COUNTRY_DEFAULTS, ...(getSetting('countries') || {}) });

function loadQuote(id) {
  const row = get(`${SELECT_QUOTE} WHERE q.id = ?`, id);
  if (!row) throw notFound('Quotation not found', 'عرض السعر غير موجود');
  return row;
}

function loadItems(quotationId) {
  return all('SELECT * FROM quotation_items WHERE quotation_id = ? ORDER BY sort_order, id', quotationId);
}

/** Parses the JSON document columns back into objects for the client. */
function hydrate(quote, items) {
  return {
    ...quote,
    scope: safeParse(quote.scope_json, SCOPE),
    payment_terms: safeParse(quote.payment_terms_json, PAYMENT_TERMS),
    conditions: safeParse(quote.conditions_json, CONDITIONS),
    items,
    total_words_ar: amountInWords(quote.total, quote.currency, 'ar'),
    total_words_en: amountInWords(quote.total, quote.currency, 'en'),
    valid_until: addDays(quote.issue_date, quote.valid_days),
  };
}

function safeParse(json, fallback) {
  if (!json) return fallback;
  try { return JSON.parse(json); } catch { return fallback; }
}

function addDays(isoDate, days) {
  if (!isoDate) return null;
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + Number(days || 0));
  return d.toISOString().slice(0, 10);
}

/** `SPAN TECH P.T - 26 - 059` — resets its sequence every calendar year. */
function generateNumber(issueDate) {
  const prefix = getSetting('quote_prefix', 'SPAN TECH P.T');
  const year = (issueDate || new Date().toISOString().slice(0, 10)).slice(0, 4);
  const sequence = nextCounter(`quote_${year}`);
  return `${prefix} - ${year.slice(2)} - ${String(sequence).padStart(3, '0')}`;
}

/** Normalises client-sent line items; totals are always recomputed server side. */
function normaliseItems(rawItems) {
  const list = Array.isArray(rawItems) ? rawItems : [];
  if (!list.length) return null;
  return list.map((item, index) => ({
    sort_order: int(item.sort_order, 'sort_order', { fallback: index }),
    desc_en: str(item.desc_en, 'desc_en', { required: true, max: 400 }),
    desc_ar: str(item.desc_ar, 'desc_ar', { max: 400 }),
    unit_en: str(item.unit_en, 'unit_en', { max: 20, fallback: 'm²' }),
    unit_ar: str(item.unit_ar, 'unit_ar', { max: 20, fallback: 'م²' }),
    qty: num(item.qty, 'qty', { min: 0, fallback: 0 }),
    unit_price: num(item.unit_price, 'unit_price', { min: 0, fallback: 0 }),
    is_optional: bool(item.is_optional) ? 1 : 0,
  }));
}

/** Recomputes every total and persists the result. Returns the fresh row. */
function recalculate(quotationId) {
  const quote = get('SELECT * FROM quotations WHERE id = ?', quotationId);
  const items = loadItems(quotationId);
  const totals = computeTotals(quote, items);

  transaction(() => {
    for (const item of totals.items) {
      run('UPDATE quotation_items SET amount = ? WHERE id = ?', item.amount, item.id);
    }
    update('quotations', quotationId, {
      subtotal: totals.subtotal,
      discount_amount: totals.discount_amount,
      net_amount: totals.net_amount,
      vat_amount: totals.vat_amount,
      total: totals.total,
      cost_total: totals.cost_total,
      margin_amount: totals.margin_amount,
      margin_pct: totals.margin_pct,
    });
  });
  return totals;
}

function replaceItems(quotationId, items) {
  run('DELETE FROM quotation_items WHERE quotation_id = ?', quotationId);
  items.forEach((item) => insert('quotation_items', { ...item, quotation_id: quotationId, amount: round2(item.qty * item.unit_price) }));
}

export function register(router) {
  // ------------------------------------------------------------------ list
  router.get('/api/quotations', ({ query, user }) => {
    requirePermission(user, 'quotations.view');
    const where = [];
    const params = [];

    if (query.q) {
      where.push('(q.number LIKE ? OR q.project_name LIKE ? OR q.project_name_ar LIKE ? OR c.name_en LIKE ?)');
      const like = `%${query.q}%`;
      params.push(like, like, like, like);
    }
    if (query.status) { where.push('q.status = ?'); params.push(query.status); }
    if (query.country) { where.push('q.country = ?'); params.push(query.country); }
    if (query.customer_id) { where.push('q.customer_id = ?'); params.push(Number(query.customer_id)); }
    if (query.opportunity_id) { where.push('q.opportunity_id = ?'); params.push(Number(query.opportunity_id)); }
    if (query.from) { where.push('q.issue_date >= ?'); params.push(query.from); }
    if (query.to) { where.push('q.issue_date <= ?'); params.push(query.to); }
    if (!canSeeAll(user) && query.scope !== 'all') {
      where.push('(q.owner_id = ? OR q.owner_id IS NULL)');
      params.push(user.id);
    }
    const clause = where.length ? `WHERE ${where.join(' AND ')}` : '';

    const rows = all(
      `SELECT q.id, q.number, q.revision, q.project_name, q.project_name_ar, q.issue_date,
              q.valid_days, q.status, q.country, q.currency, q.subtotal, q.net_amount,
              q.vat_amount, q.total, q.margin_pct, q.customer_id, q.opportunity_id, q.owner_id,
              c.name_en AS customer_name, c.name_ar AS customer_name_ar,
              u.name AS owner_name, u.name_ar AS owner_name_ar
         FROM quotations q
         JOIN customers c ON c.id = q.customer_id
         LEFT JOIN users u ON u.id = q.owner_id
         ${clause}
        ORDER BY q.issue_date DESC, q.id DESC
        LIMIT 500`,
      ...params,
    );
    return { quotations: rows };
  });

  // ------------------------------------------------------------------- read
  router.get('/api/quotations/:id', ({ params, user }) => {
    requirePermission(user, 'quotations.view');
    const id = Number(params.id);
    const quote = loadQuote(id);
    const items = loadItems(id);
    const totals = computeTotals(quote, items);
    return {
      quotation: hydrate(quote, items),
      breakdown: totals.breakdown,
      revisions: all(
        'SELECT id, number, revision, status, issue_date, total FROM quotations WHERE number = ? ORDER BY revision',
        quote.number,
      ),
    };
  });

  /** Everything the printable AR/EN document needs, in one payload. */
  router.get('/api/quotations/:id/document', ({ params, user }) => {
    requirePermission(user, 'quotations.view');
    const id = Number(params.id);
    const quote = loadQuote(id);
    const items = loadItems(id);
    const country = countrySettings()[quote.country] || COUNTRY_DEFAULTS.SA;
    const clause = getSetting('price_clause', PRICE_ADJUSTMENT_CLAUSE);

    const fill = (template) => (template || '')
      .replace('{price}', Number(quote.strand_price_ton).toLocaleString('en-US'))
      .replace('{currency}', quote.currency)
      .replace('{variance}', quote.price_variance);

    const company = getSetting('company', COMPANY);
    return {
      quotation: hydrate(quote, items),
      company,
      // The letterhead shows the office that issues this offer.
      branch: branchFor(company, quote.country),
      country,
      intro: {
        en: (safeParse(quote.intro_en, null) || quote.intro_en || getSetting('intro', INTRO).en || '')
          .replace('{project}', quote.project_name || ''),
        ar: (safeParse(quote.intro_ar, null) || quote.intro_ar || getSetting('intro', INTRO).ar || '')
          .replace('{project}', quote.project_name_ar || quote.project_name || ''),
      },
      price_clause: { en: fill(clause.en), ar: fill(clause.ar) },
    };
  });

  // ------------------------------------------------------------------ study
  // The cost comparison sent to the owner. It hangs off the quotation because
  // it argues for that quotation's price, and it reuses its area and rate.

  const loadStudy = (quote) => {
    const saved = safeParse(quote.study_json, null);
    return computeStudy(saved || defaultStudy(quote));
  };

  const drawingsFor = (quotationId) => all(
    `SELECT id, kind, caption_ar, caption_en, original_name, content_type, bytes,
            sort_order, created_at
       FROM study_drawings WHERE quotation_id = ?
      ORDER BY kind, sort_order, id`,
    quotationId,
  ).map((row) => ({ ...row, url: `/api/quotations/${quotationId}/study/drawings/${row.id}/file` }));

  router.get('/api/quotations/:id/study', ({ params, user }) => {
    requirePermission(user, 'quotations.view');
    const id = Number(params.id);
    const quote = loadQuote(id);
    return {
      study: loadStudy(quote),
      drawings: drawingsFor(id),
      systems: CONVENTIONAL_KEYS.map((key) => ({
        key,
        label_en: CONVENTIONAL_SYSTEMS[key].label_en,
        label_ar: CONVENTIONAL_SYSTEMS[key].label_ar,
      })),
    };
  });

  router.put('/api/quotations/:id/study', ({ params, body, user }) => {
    requirePermission(user, 'quotations.edit');
    const id = Number(params.id);
    const quote = loadQuote(id);
    assertCanEdit(user, quote.owner_id);

    const incoming = body?.study;
    if (!incoming || typeof incoming !== 'object') {
      throw badRequest('A study is required', 'بيانات الدراسة مطلوبة');
    }
    const system = oneOf(incoming.system, 'system', CONVENTIONAL_KEYS, { fallback: 'solid' });

    // Numbers only, and never negative — a negative thickness would produce a
    // saving that looks impressive and means nothing.
    const numeric = (key, { max = 1e9 } = {}) =>
      num(incoming[key], key, { min: 0, max, fallback: defaultStudy(quote, system)[key] });

    const study = {
      system,
      floors: int(incoming.floors, 'floors', { min: 1, max: 200, fallback: 1 }),
      area_sqm: numeric('area_sqm'),
      conv_thickness_mm: numeric('conv_thickness_mm', { max: 3000 }),
      conv_rebar_kg_sqm: numeric('conv_rebar_kg_sqm', { max: 1000 }),
      pt_thickness_mm: numeric('pt_thickness_mm', { max: 3000 }),
      pt_rebar_kg_sqm: numeric('pt_rebar_kg_sqm', { max: 1000 }),
      pt_rate_sqm: numeric('pt_rate_sqm'),
      concrete_rate_m3: numeric('concrete_rate_m3'),
      rebar_rate_ton: numeric('rebar_rate_ton'),
      formwork_rate_sqm: numeric('formwork_rate_sqm'),
      conv_cycle_days: numeric('conv_cycle_days', { max: 3650 }),
      pt_cycle_days: numeric('pt_cycle_days', { max: 3650 }),
      foundation_saving_sqm: numeric('foundation_saving_sqm'),
      day_value: numeric('day_value'),
      storey_height_saving_mm: numeric('storey_height_saving_mm', { max: 10_000 }),
      notes_ar: str(incoming.notes_ar, 'notes_ar', { max: 4000 }) || '',
      notes_en: str(incoming.notes_en, 'notes_en', { max: 4000 }) || '',
    };

    update('quotations', id, { study_json: JSON.stringify(study) });
    audit(user.id, 'quotation', id, 'study');
    return { study: computeStudy(study), drawings: drawingsFor(id) };
  });

  // --------------------------------------------------------- study drawings
  // The original design the owner already has, and the post-tensioned tender
  // drawings produced from it. Shown side by side, they are the strongest part
  // of the argument.

  router.post('/api/quotations/:id/study/drawings', async ({ req, params, query, user }) => {
    requirePermission(user, 'quotations.edit');
    const id = Number(params.id);
    const quote = loadQuote(id);
    assertCanEdit(user, quote.owner_id);

    const kind = oneOf(query.kind, 'kind', DRAWING_KINDS, { fallback: 'original' });
    const saved = await saveDrawing(req, id);

    const next = get(
      'SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM study_drawings WHERE quotation_id = ? AND kind = ?',
      id, kind,
    ).n;

    const drawingId = insert('study_drawings', {
      quotation_id: id,
      kind,
      filename: saved.filename,
      original_name: str(query.name, 'name', { max: 250 }) || null,
      caption_ar: str(query.caption_ar, 'caption_ar', { max: 250 }) || null,
      caption_en: str(query.caption_en, 'caption_en', { max: 250 }) || null,
      content_type: saved.contentType,
      bytes: saved.bytes,
      sort_order: next,
      uploaded_by: user.id,
    });
    audit(user.id, 'quotation', id, 'drawing_add', { kind, bytes: saved.bytes });
    return { drawings: drawingsFor(id), id: drawingId };
  }, { rawBody: true });

  router.get('/api/quotations/:id/study/drawings/:drawingId/file', ({ params, res, user }) => {
    requirePermission(user, 'quotations.view');
    const id = Number(params.id);
    const row = get(
      'SELECT * FROM study_drawings WHERE id = ? AND quotation_id = ?',
      Number(params.drawingId), id,
    );
    if (!row) throw notFound('Drawing not found', 'المخطط مش موجود');

    let file;
    try {
      file = readFileSync(drawingPath(id, row.filename));
    } catch {
      throw notFound('Drawing file is missing', 'ملف المخطط مش موجود على السيرفر');
    }
    res.writeHead(200, {
      'content-type': row.content_type,
      'content-length': file.length,
      'cache-control': 'private, max-age=3600',
      'x-content-type-options': 'nosniff',
    });
    res.end(file);
  });

  router.patch('/api/quotations/:id/study/drawings/:drawingId', ({ params, body, user }) => {
    requirePermission(user, 'quotations.edit');
    const id = Number(params.id);
    const quote = loadQuote(id);
    assertCanEdit(user, quote.owner_id);

    const row = get('SELECT * FROM study_drawings WHERE id = ? AND quotation_id = ?', Number(params.drawingId), id);
    if (!row) throw notFound('Drawing not found', 'المخطط مش موجود');

    update('study_drawings', row.id, {
      caption_ar: str(body.caption_ar, 'caption_ar', { max: 250, fallback: undefined }),
      caption_en: str(body.caption_en, 'caption_en', { max: 250, fallback: undefined }),
      kind: oneOf(body.kind, 'kind', DRAWING_KINDS, { fallback: undefined }),
      sort_order: int(body.sort_order, 'sort_order', { min: 0, max: 999, fallback: undefined }),
    });
    return { drawings: drawingsFor(id) };
  });

  router.delete('/api/quotations/:id/study/drawings/:drawingId', async ({ params, user }) => {
    requirePermission(user, 'quotations.edit');
    const id = Number(params.id);
    const quote = loadQuote(id);
    assertCanEdit(user, quote.owner_id);

    const row = get('SELECT * FROM study_drawings WHERE id = ? AND quotation_id = ?', Number(params.drawingId), id);
    if (!row) throw notFound('Drawing not found', 'المخطط مش موجود');

    run('DELETE FROM study_drawings WHERE id = ?', row.id);
    await deleteDrawingFile(id, row.filename);
    audit(user.id, 'quotation', id, 'drawing_remove');
    return { drawings: drawingsFor(id) };
  });

  // ----------------------------------------------------------------- create
  router.post('/api/quotations', ({ body, user }) => {
    requirePermission(user, 'quotations.create');
    const customerId = int(body.customer_id, 'customer_id', { required: true, min: 1 });
    const customer = get('SELECT * FROM customers WHERE id = ?', customerId);
    if (!customer) throw notFound('Customer not found', 'العميل غير موجود');

    const opportunityId = int(body.opportunity_id, 'opportunity_id', { min: 1, fallback: null });
    const opportunity = opportunityId ? get('SELECT * FROM opportunities WHERE id = ?', opportunityId) : null;

    const countryCode = oneOf(body.country, 'country', COUNTRIES, {
      fallback: opportunity?.country || customer.country || 'SA',
    });
    const defaults = countrySettings()[countryCode] || COUNTRY_DEFAULTS.SA;
    const issueDate = date(body.issue_date, 'issue_date', { fallback: new Date().toISOString().slice(0, 10) });

    const area = num(body.area_sqm, 'area_sqm', { min: 0, fallback: opportunity?.area_sqm || 0 });
    const unitPrice = num(body.unit_price, 'unit_price', { min: 0, fallback: defaults.default_price_sqm });

    const id = transaction(() => {
      const quotationId = insert('quotations', {
        number: generateNumber(issueDate),
        revision: 0,
        opportunity_id: opportunityId,
        customer_id: customerId,
        contact_id: int(body.contact_id, 'contact_id', { min: 1, fallback: opportunity?.contact_id ?? null }),
        project_name: str(body.project_name, 'project_name', { required: true, max: 250 }),
        project_name_ar: str(body.project_name_ar, 'project_name_ar', { max: 250 }),
        location: str(body.location, 'location', { max: 200, fallback: opportunity?.city || customer.city }),
        location_ar: str(body.location_ar, 'location_ar', { max: 200 }),
        attention: str(body.attention, 'attention', { max: 200 }),
        attention_ar: str(body.attention_ar, 'attention_ar', { max: 200 }),
        subject_en: str(body.subject_en, 'subject_en', { max: 400, fallback: 'Quotation for the design, supply and execution of post-tensioned slab works' }),
        subject_ar: str(body.subject_ar, 'subject_ar', { max: 400, fallback: 'عرض سعر تصميم وتوريد وتنفيذ أعمال الأسقف اللاحقة للشد' }),
        country: countryCode,
        currency: oneOf(body.currency, 'currency', CURRENCIES, { fallback: defaults.currency }),
        vat_rate: num(body.vat_rate, 'vat_rate', { min: 0, max: 100, fallback: defaults.vat_rate }),
        vat_included: bool(body.vat_included) ? 1 : 0,
        duct_type: oneOf(body.duct_type, 'duct_type', DUCT_TYPES, {
          fallback: defaultDuctType(countryCode),
        }),
        issue_date: issueDate,
        valid_days: int(body.valid_days, 'valid_days', { min: 1, max: 365, fallback: defaults.valid_days }),
        status: 'draft',
        strand_price_ton: num(body.strand_price_ton, 'strand_price_ton', { min: 0, fallback: defaults.strand_price_ton }),
        strand_kg_sqm: num(body.strand_kg_sqm, 'strand_kg_sqm', { min: 0, fallback: defaults.strand_kg_sqm }),
        anchors_per_ton: num(body.anchors_per_ton, 'anchors_per_ton', { min: 0, fallback: defaults.anchors_per_ton }),
        anchor_cost: num(body.anchor_cost, 'anchor_cost', { min: 0, fallback: 0 }),
        duct_cost_sqm: num(body.duct_cost_sqm, 'duct_cost_sqm', { min: 0, fallback: 0 }),
        grout_cost_sqm: num(body.grout_cost_sqm, 'grout_cost_sqm', { min: 0, fallback: 0 }),
        labour_cost_sqm: num(body.labour_cost_sqm, 'labour_cost_sqm', { min: 0, fallback: 0 }),
        design_cost_sqm: num(body.design_cost_sqm, 'design_cost_sqm', { min: 0, fallback: 0 }),
        overhead_pct: num(body.overhead_pct, 'overhead_pct', { min: 0, max: 100, fallback: 0 }),
        target_margin: num(body.target_margin, 'target_margin', { min: 0, max: 90, fallback: 20 }),
        price_variance: num(body.price_variance, 'price_variance', { min: 0, max: 100, fallback: 5 }),
        discount_type: oneOf(body.discount_type, 'discount_type', ['none', 'percent', 'amount'], { fallback: 'none' }),
        discount_value: num(body.discount_value, 'discount_value', { min: 0, fallback: 0 }),
        scope_json: JSON.stringify(applyDuctMaterial(
          jsonField(body.scope, 'scope', getSetting('scope', SCOPE)),
          oneOf(body.duct_type, 'duct_type', DUCT_TYPES, { fallback: defaultDuctType(countryCode) }),
        )),
        payment_terms_json: JSON.stringify(jsonField(body.payment_terms, 'payment_terms', getSetting('payment_terms', PAYMENT_TERMS))),
        conditions_json: JSON.stringify(jsonField(body.conditions, 'conditions', getSetting('conditions', CONDITIONS))),
        notes_en: str(body.notes_en, 'notes_en', { max: 4000 }),
        notes_ar: str(body.notes_ar, 'notes_ar', { max: 4000 }),
        owner_id: int(body.owner_id, 'owner_id', { min: 1, fallback: user.id }),
        created_by: user.id,
      });

      const items = normaliseItems(body.items) || [{
        sort_order: 0,
        desc_en: DEFAULT_ITEM.desc_en,
        desc_ar: DEFAULT_ITEM.desc_ar,
        unit_en: DEFAULT_ITEM.unit_en,
        unit_ar: DEFAULT_ITEM.unit_ar,
        qty: area,
        unit_price: unitPrice,
        is_optional: 0,
      }];
      replaceItems(quotationId, items);
      return quotationId;
    });

    recalculate(id);
    // Creating an offer moves the opportunity into the "quoted" stage.
    if (opportunity && ['new', 'qualified'].includes(opportunity.stage)) {
      update('opportunities', opportunity.id, { stage: 'quoted', probability: 50 });
    }
    audit(user.id, 'quotation', id, 'create');
    const quote = loadQuote(id);
    notifyAssignment({
      actorId: user.id, userId: quote.owner_id,
      entity: 'quotation', entityId: id, name: `${quote.number} — ${quote.project_name}`,
      link: `quote/${id}`,
    });
    return { quotation: hydrate(quote, loadItems(id)) };
  });

  // ----------------------------------------------------------------- update
  router.patch('/api/quotations/:id', ({ params, body, user }) => {
    requirePermission(user, 'quotations.edit');
    const id = Number(params.id);
    const existing = loadQuote(id);
    assertCanEdit(user, existing.owner_id);
    if (['approved', 'rejected'].includes(existing.status) && !can(user, 'quotations.edit_closed')) {
      throw badRequest(
        'A closed quotation can only be changed by a manager — create a revision instead',
        'لا يمكن تعديل عرض سعر مغلق إلا بواسطة المدير — أنشئ مراجعة جديدة بدلاً من ذلك',
      );
    }

    const fields = {
      project_name: str(body.project_name, 'project_name', { max: 250, fallback: undefined }),
      project_name_ar: str(body.project_name_ar, 'project_name_ar', { max: 250, fallback: undefined }),
      location: str(body.location, 'location', { max: 200, fallback: undefined }),
      location_ar: str(body.location_ar, 'location_ar', { max: 200, fallback: undefined }),
      attention: str(body.attention, 'attention', { max: 200, fallback: undefined }),
      attention_ar: str(body.attention_ar, 'attention_ar', { max: 200, fallback: undefined }),
      subject_en: str(body.subject_en, 'subject_en', { max: 400, fallback: undefined }),
      subject_ar: str(body.subject_ar, 'subject_ar', { max: 400, fallback: undefined }),
      contact_id: body.contact_id === undefined ? undefined : int(body.contact_id, 'contact_id', { min: 1, fallback: null }),
      opportunity_id: body.opportunity_id === undefined ? undefined : int(body.opportunity_id, 'opportunity_id', { min: 1, fallback: null }),
      country: oneOf(body.country, 'country', COUNTRIES, { fallback: undefined }),
      currency: oneOf(body.currency, 'currency', CURRENCIES, { fallback: undefined }),
      vat_rate: num(body.vat_rate, 'vat_rate', { min: 0, max: 100, fallback: undefined }),
      vat_included: body.vat_included === undefined ? undefined : (bool(body.vat_included) ? 1 : 0),
      duct_type: oneOf(body.duct_type, 'duct_type', DUCT_TYPES, { fallback: undefined }),
      issue_date: body.issue_date === undefined ? undefined : date(body.issue_date, 'issue_date'),
      valid_days: int(body.valid_days, 'valid_days', { min: 1, max: 365, fallback: undefined }),
      strand_price_ton: num(body.strand_price_ton, 'strand_price_ton', { min: 0, fallback: undefined }),
      strand_kg_sqm: num(body.strand_kg_sqm, 'strand_kg_sqm', { min: 0, fallback: undefined }),
      anchors_per_ton: num(body.anchors_per_ton, 'anchors_per_ton', { min: 0, fallback: undefined }),
      anchor_cost: num(body.anchor_cost, 'anchor_cost', { min: 0, fallback: undefined }),
      duct_cost_sqm: num(body.duct_cost_sqm, 'duct_cost_sqm', { min: 0, fallback: undefined }),
      grout_cost_sqm: num(body.grout_cost_sqm, 'grout_cost_sqm', { min: 0, fallback: undefined }),
      labour_cost_sqm: num(body.labour_cost_sqm, 'labour_cost_sqm', { min: 0, fallback: undefined }),
      design_cost_sqm: num(body.design_cost_sqm, 'design_cost_sqm', { min: 0, fallback: undefined }),
      overhead_pct: num(body.overhead_pct, 'overhead_pct', { min: 0, max: 100, fallback: undefined }),
      target_margin: num(body.target_margin, 'target_margin', { min: 0, max: 90, fallback: undefined }),
      price_variance: num(body.price_variance, 'price_variance', { min: 0, max: 100, fallback: undefined }),
      discount_type: oneOf(body.discount_type, 'discount_type', ['none', 'percent', 'amount'], { fallback: undefined }),
      discount_value: num(body.discount_value, 'discount_value', { min: 0, fallback: undefined }),
      notes_en: str(body.notes_en, 'notes_en', { max: 4000, fallback: undefined }),
      notes_ar: str(body.notes_ar, 'notes_ar', { max: 4000, fallback: undefined }),
      scope_json: body.scope === undefined ? undefined : JSON.stringify(body.scope),
      payment_terms_json: body.payment_terms === undefined ? undefined : JSON.stringify(body.payment_terms),
      conditions_json: body.conditions === undefined ? undefined : JSON.stringify(body.conditions),
    };
    if (can(user, 'customers.assign') && body.owner_id !== undefined) {
      fields.owner_id = int(body.owner_id, 'owner_id', { min: 1, fallback: null });
    }

    // Switching the duct material rewrites the duct line in the scope, so the
    // printed offer never promises steel while the price is for plastic. Only
    // that line changes; everything the engineer has edited stays.
    if (fields.duct_type !== undefined && fields.duct_type !== existing.duct_type) {
      const scope = fields.scope_json !== undefined
        ? JSON.parse(fields.scope_json)
        : safeParse(existing.scope_json, getSetting('scope', SCOPE));
      fields.scope_json = JSON.stringify(applyDuctMaterial(scope, fields.duct_type));
    }

    update('quotations', id, fields);
    const items = normaliseItems(body.items);
    if (items) replaceItems(id, items);
    recalculate(id);

    audit(user.id, 'quotation', id, 'update');
    const quote = loadQuote(id);
    const fresh = loadItems(id);
    return { quotation: hydrate(quote, fresh), breakdown: computeTotals(quote, fresh).breakdown };
  });

  // --------------------------------------------------------- status changes
  router.post('/api/quotations/:id/status', ({ params, body, user }) => {
    requirePermission(user, 'quotations.view');
    const id = Number(params.id);
    const quote = loadQuote(id);
    assertCanEdit(user, quote.owner_id);
    const status = oneOf(body.status, 'status', QUOTE_STATUS, { required: true });
    // Approving or rejecting is a separate right from merely sending an offer.
    requirePermission(user, ['approved', 'rejected'].includes(status)
      ? 'quotations.decide' : 'quotations.send');

    const fields = { status };
    if (status === 'sent' && !quote.sent_at) fields.sent_at = new Date().toISOString();
    if (['approved', 'rejected', 'cancelled'].includes(status)) fields.decided_at = new Date().toISOString();
    if (status === 'rejected') fields.reject_reason = str(body.reason, 'reason', { max: 500 });
    update('quotations', id, fields);

    // Keep the linked opportunity in step with the offer's outcome.
    if (quote.opportunity_id) {
      const opportunity = get('SELECT * FROM opportunities WHERE id = ?', quote.opportunity_id);
      if (opportunity && !['won', 'lost'].includes(opportunity.stage)) {
        if (status === 'approved') {
          update('opportunities', opportunity.id, {
            stage: 'won', probability: 100,
            expected_value: quote.net_amount, currency: quote.currency,
            closed_at: new Date().toISOString().slice(0, 10),
          });
        } else if (status === 'rejected') {
          update('opportunities', opportunity.id, {
            stage: 'lost', probability: 0,
            lost_reason: str(body.reason, 'reason', { max: 60, fallback: 'other' }),
            closed_at: new Date().toISOString().slice(0, 10),
          });
        } else if (status === 'sent' && opportunity.stage !== 'negotiation') {
          update('opportunities', opportunity.id, { stage: 'quoted', probability: 50 });
        }
      }
    }
    audit(user.id, 'quotation', id, 'status', { from: quote.status, to: status });

    notifyQuoteStatus({ actorId: user.id, userId: quote.owner_id, quotation: quote, status });
    // A won or lost offer is company news: tell the managers too.
    if (['approved', 'rejected'].includes(status)) {
      for (const manager of all("SELECT id FROM users WHERE active = 1 AND role IN ('admin','manager')")) {
        if (manager.id === quote.owner_id) continue;
        notifyQuoteStatus({ actorId: user.id, userId: manager.id, quotation: quote, status });
      }
    }
    return { quotation: hydrate(loadQuote(id), loadItems(id)) };
  });

  // ------------------------------------------------------------- revisions
  router.post('/api/quotations/:id/revise', ({ params, user }) => {
    requirePermission(user, 'quotations.create');
    const id = Number(params.id);
    const source = loadQuote(id);
    assertCanEdit(user, source.owner_id);
    const latest = get('SELECT MAX(revision) AS r FROM quotations WHERE number = ?', source.number).r ?? 0;

    const newId = transaction(() => {
      const {
        id: _id, revision: _rev, created_at: _c, updated_at: _u,
        sent_at: _s, decided_at: _d, reject_reason: _rr,
        customer_name, customer_name_ar, customer_address, customer_tax_number,
        opportunity_title, opportunity_area, contact_name, contact_title,
        contact_mobile, contact_email, owner_name, owner_name_ar,
        owner_title, owner_title_ar, owner_phone, owner_email,
        ...copy
      } = source;
      const cloneId = insert('quotations', {
        ...copy,
        revision: latest + 1,
        parent_id: id,
        status: 'draft',
        issue_date: new Date().toISOString().slice(0, 10),
        created_by: user.id,
      });
      const items = loadItems(id).map(({ id: _itemId, quotation_id, ...item }) => item);
      items.forEach((item) => insert('quotation_items', { ...item, quotation_id: cloneId }));
      return cloneId;
    });

    recalculate(newId);
    audit(user.id, 'quotation', newId, 'revise', { from: id });
    return { quotation: hydrate(loadQuote(newId), loadItems(newId)) };
  });

  router.post('/api/quotations/:id/duplicate', ({ params, body, user }) => {
    requirePermission(user, 'quotations.create');
    const id = Number(params.id);
    const source = loadQuote(id);
    const issueDate = new Date().toISOString().slice(0, 10);

    const newId = transaction(() => {
      const {
        id: _id, number: _n, revision: _rev, parent_id: _p, created_at: _c, updated_at: _u,
        sent_at: _s, decided_at: _d, reject_reason: _rr,
        customer_name, customer_name_ar, customer_address, customer_tax_number,
        opportunity_title, opportunity_area, contact_name, contact_title,
        contact_mobile, contact_email, owner_name, owner_name_ar,
        owner_title, owner_title_ar, owner_phone, owner_email,
        ...copy
      } = source;
      const cloneId = insert('quotations', {
        ...copy,
        number: generateNumber(issueDate),
        revision: 0,
        parent_id: null,
        status: 'draft',
        issue_date: issueDate,
        project_name: str(body.project_name, 'project_name', { max: 250, fallback: `${source.project_name} (copy)` }),
        customer_id: int(body.customer_id, 'customer_id', { min: 1, fallback: source.customer_id }),
        opportunity_id: body.opportunity_id === undefined ? null : int(body.opportunity_id, 'opportunity_id', { min: 1, fallback: null }),
        owner_id: user.id,
        created_by: user.id,
      });
      loadItems(id)
        .map(({ id: _itemId, quotation_id, ...item }) => item)
        .forEach((item) => insert('quotation_items', { ...item, quotation_id: cloneId }));
      return cloneId;
    });

    recalculate(newId);
    audit(user.id, 'quotation', newId, 'duplicate', { from: id });
    return { quotation: hydrate(loadQuote(newId), loadItems(newId)) };
  });

  router.delete('/api/quotations/:id', ({ params, user }) => {
    requirePermission(user, 'quotations.delete');
    const id = Number(params.id);
    loadQuote(id);
    run('DELETE FROM quotations WHERE id = ?', id);
    audit(user.id, 'quotation', id, 'delete');
    return { ok: true };
  });

  /** Marks every sent offer whose validity window has passed as expired. */
  router.post('/api/quotations/expire-stale', ({ user }) => {
    requirePermission(user, 'quotations.edit');
    const changed = run(
      `UPDATE quotations SET status = 'expired', updated_at = datetime('now')
        WHERE status IN ('sent','under_review')
          AND date(issue_date, '+' || valid_days || ' days') < date('now')`,
    ).changes;
    return { expired: changed };
  });
}
