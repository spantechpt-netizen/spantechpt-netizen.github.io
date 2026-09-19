import { all, get } from '../db.js';
import { requirePermission, can } from '../auth.js';
import { oneOf } from '../validate.js';
import { sendDownload, FORMATS } from '../export.js';

/**
 * Engineers see only their own numbers; whoever holds `analytics.view_all`
 * sees the company, and may narrow it to one engineer. Returns a SQL fragment
 * plus the parameters it needs.
 *
 * This asks the analytics permission rather than the customers one, so that
 * unticking "company-wide analytics" for a person actually does something.
 */
const seesEveryone = (user) => can(user, 'analytics.view_all');

function scopeFor(user, alias, query) {
  if (seesEveryone(user) && query.owner_id) return { sql: `AND ${alias}.owner_id = ?`, params: [Number(query.owner_id)] };
  if (seesEveryone(user)) return { sql: '', params: [] };
  return { sql: `AND ${alias}.owner_id = ?`, params: [user.id] };
}

/** Margin is the cost model in one number, so it follows the same permission. */
const withMargin = (row, user) => {
  if (can(user, 'quotations.view_cost')) return row;
  const { avg_margin: _dropped, ...rest } = row;
  return rest;
};

function dateRange(query) {
  const to = query.to || new Date().toISOString().slice(0, 10);
  const from = query.from || (() => {
    const d = new Date(`${to}T00:00:00Z`);
    d.setUTCFullYear(d.getUTCFullYear() - 1);
    return d.toISOString().slice(0, 10);
  })();
  return { from, to };
}

function overview({ query, user }) {
  requirePermission(user, 'analytics.view');
  const { from, to } = dateRange(query);
  const oScope = scopeFor(user, 'o', query);
  const qScope = scopeFor(user, 'q', query);
  const countryFilter = query.country ? 'AND o.country = ?' : '';
  const countryParam = query.country ? [query.country] : [];
  const qCountryFilter = query.country ? 'AND q.country = ?' : '';

  // ---------------------------------------------------------- pipeline KPIs
  const pipeline = all(
    `SELECT stage,
            COUNT(*)            AS count,
            SUM(expected_value) AS value,
            SUM(area_sqm)       AS area
       FROM opportunities o
      WHERE 1=1 ${oScope.sql} ${countryFilter}
      GROUP BY stage`,
    ...oScope.params, ...countryParam,
  );

  const openValue = get(
    `SELECT COALESCE(SUM(expected_value), 0) AS total,
            COALESCE(SUM(expected_value * probability / 100.0), 0) AS weighted,
            COUNT(*) AS count
       FROM opportunities o
      WHERE stage NOT IN ('won','lost') ${oScope.sql} ${countryFilter}`,
    ...oScope.params, ...countryParam,
  );

  const closed = get(
    `SELECT
       SUM(CASE WHEN stage = 'won'  THEN 1 ELSE 0 END)              AS won_count,
       SUM(CASE WHEN stage = 'lost' THEN 1 ELSE 0 END)              AS lost_count,
       SUM(CASE WHEN stage = 'won'  THEN expected_value ELSE 0 END) AS won_value,
       SUM(CASE WHEN stage = 'lost' THEN expected_value ELSE 0 END) AS lost_value,
       SUM(CASE WHEN stage = 'won'  THEN area_sqm ELSE 0 END)       AS won_area
     FROM opportunities o
    WHERE stage IN ('won','lost')
      AND (closed_at IS NULL OR closed_at BETWEEN ? AND ?)
      ${oScope.sql} ${countryFilter}`,
    from, to, ...oScope.params, ...countryParam,
  );

  const wonCount = closed.won_count || 0;
  const lostCount = closed.lost_count || 0;
  const decided = wonCount + lostCount;

  // -------------------------------------------------------- quotation KPIs
  const quotes = get(
    `SELECT COUNT(*) AS count,
            COALESCE(SUM(net_amount), 0) AS value,
            COALESCE(AVG(margin_pct), 0) AS avg_margin
       FROM quotations q
      WHERE q.issue_date BETWEEN ? AND ? ${qScope.sql} ${qCountryFilter}`,
    from, to, ...qScope.params, ...countryParam,
  );

  const quoteStatus = all(
    `SELECT status, COUNT(*) AS count, COALESCE(SUM(net_amount),0) AS value
       FROM quotations q
      WHERE q.issue_date BETWEEN ? AND ? ${qScope.sql} ${qCountryFilter}
      GROUP BY status`,
    from, to, ...qScope.params, ...countryParam,
  );

  return {
    range: { from, to },
    pipeline,
    open: openValue,
    closed: {
      won_count: wonCount,
      lost_count: lostCount,
      won_value: closed.won_value || 0,
      lost_value: closed.lost_value || 0,
      won_area: closed.won_area || 0,
      win_rate: decided ? Math.round((wonCount / decided) * 100) : 0,
    },
    quotations: { ...withMargin(quotes, user), by_status: quoteStatus },
    customers: get(
      `SELECT COUNT(*) AS total,
              SUM(CASE WHEN status = 'target'   THEN 1 ELSE 0 END) AS targets,
              SUM(CASE WHEN status = 'active'   THEN 1 ELSE 0 END) AS active,
              SUM(CASE WHEN status = 'prospect' THEN 1 ELSE 0 END) AS prospects
         FROM customers c WHERE 1=1 ${seesEveryone(user) ? '' : 'AND c.owner_id = ?'}`,
      ...(seesEveryone(user) ? [] : [user.id]),
    ),
  };
}

/** Monthly quotation volume and won value, for the trend chart. */
function monthly({ query, user }) {
  requirePermission(user, 'analytics.view');
  const { from, to } = dateRange(query);
  const qScope = scopeFor(user, 'q', query);
  const oScope = scopeFor(user, 'o', query);

  const quoted = all(
    `SELECT substr(q.issue_date, 1, 7) AS month,
            COUNT(*) AS count,
            COALESCE(SUM(q.net_amount), 0) AS value
       FROM quotations q
      WHERE q.issue_date BETWEEN ? AND ? ${qScope.sql}
      GROUP BY month ORDER BY month`,
    from, to, ...qScope.params,
  );

  const won = all(
    `SELECT substr(o.closed_at, 1, 7) AS month,
            COUNT(*) AS count,
            COALESCE(SUM(o.expected_value), 0) AS value
       FROM opportunities o
      WHERE o.stage = 'won' AND o.closed_at BETWEEN ? AND ? ${oScope.sql}
      GROUP BY month ORDER BY month`,
    from, to, ...oScope.params,
  );

  return { quoted, won, range: { from, to } };
}

/** Breakdown by country, engineer, source, sector and loss reason. */
function breakdown({ query, user }) {
  requirePermission(user, 'analytics.view');
  const { from, to } = dateRange(query);
  const oScope = scopeFor(user, 'o', query);
  const qScope = scopeFor(user, 'q', query);

  return {
    by_country: all(
      `SELECT o.country,
              COUNT(*) AS count,
              SUM(CASE WHEN o.stage = 'won' THEN 1 ELSE 0 END) AS won,
              COALESCE(SUM(CASE WHEN o.stage = 'won' THEN o.expected_value ELSE 0 END), 0) AS won_value,
              COALESCE(SUM(CASE WHEN o.stage NOT IN ('won','lost') THEN o.expected_value ELSE 0 END), 0) AS open_value,
              COALESCE(SUM(o.area_sqm), 0) AS area
         FROM opportunities o WHERE 1=1 ${oScope.sql}
        GROUP BY o.country ORDER BY won_value DESC`,
      ...oScope.params,
    ),
    by_owner: all(
      `SELECT u.id, u.name, u.name_ar,
              COUNT(o.id) AS count,
              SUM(CASE WHEN o.stage = 'won'  THEN 1 ELSE 0 END) AS won,
              SUM(CASE WHEN o.stage = 'lost' THEN 1 ELSE 0 END) AS lost,
              COALESCE(SUM(CASE WHEN o.stage = 'won' THEN o.expected_value ELSE 0 END), 0) AS won_value,
              COALESCE(SUM(CASE WHEN o.stage NOT IN ('won','lost') THEN o.expected_value ELSE 0 END), 0) AS open_value
         FROM users u LEFT JOIN opportunities o ON o.owner_id = u.id
        WHERE u.active = 1
        GROUP BY u.id HAVING count > 0 ORDER BY won_value DESC`,
    ),
    by_source: all(
      `SELECT COALESCE(NULLIF(o.source, ''), 'unknown') AS source,
              COUNT(*) AS count,
              SUM(CASE WHEN o.stage = 'won' THEN 1 ELSE 0 END) AS won
         FROM opportunities o WHERE 1=1 ${oScope.sql}
        GROUP BY source ORDER BY count DESC`,
      ...oScope.params,
    ),
    by_project_type: all(
      `SELECT COALESCE(NULLIF(o.project_type, ''), 'other') AS project_type,
              COUNT(*) AS count,
              COALESCE(SUM(o.area_sqm), 0) AS area,
              COALESCE(SUM(CASE WHEN o.stage = 'won' THEN o.expected_value ELSE 0 END), 0) AS won_value
         FROM opportunities o WHERE 1=1 ${oScope.sql}
        GROUP BY project_type ORDER BY count DESC`,
      ...oScope.params,
    ),
    lost_reasons: all(
      `SELECT COALESCE(NULLIF(o.lost_reason, ''), 'other') AS reason,
              COUNT(*) AS count,
              COALESCE(SUM(o.expected_value), 0) AS value
         FROM opportunities o
        WHERE o.stage = 'lost' ${oScope.sql}
        GROUP BY reason ORDER BY count DESC`,
      ...oScope.params,
    ),
    // Average price per m² actually quoted, by country — the pricing benchmark.
    price_per_sqm: all(
      `SELECT q.country, q.currency,
              COUNT(*) AS quotes,
              ROUND(AVG(q.net_amount / NULLIF(qty.total_qty, 0)), 2) AS avg_price,
              ROUND(MIN(q.net_amount / NULLIF(qty.total_qty, 0)), 2) AS min_price,
              ROUND(MAX(q.net_amount / NULLIF(qty.total_qty, 0)), 2) AS max_price
         FROM quotations q
         JOIN (SELECT quotation_id, SUM(qty) AS total_qty
                 FROM quotation_items WHERE is_optional = 0 GROUP BY quotation_id) qty
           ON qty.quotation_id = q.id
        WHERE q.issue_date BETWEEN ? AND ? AND qty.total_qty > 0 ${qScope.sql}
        GROUP BY q.country, q.currency`,
      from, to, ...qScope.params,
    ),
  };
}

/** Conversion funnel: every opportunity created in the window, by furthest stage reached. */
function funnel({ query, user }) {
  requirePermission(user, 'analytics.view');
  const { from, to } = dateRange(query);
  const oScope = scopeFor(user, 'o', query);
  const rows = get(
    `SELECT
       COUNT(*) AS created,
       SUM(CASE WHEN stage IN ('qualified','quoted','negotiation','won','lost') THEN 1 ELSE 0 END) AS qualified,
       SUM(CASE WHEN stage IN ('quoted','negotiation','won','lost') THEN 1 ELSE 0 END) AS quoted,
       SUM(CASE WHEN stage IN ('negotiation','won') THEN 1 ELSE 0 END) AS negotiation,
       SUM(CASE WHEN stage = 'won' THEN 1 ELSE 0 END) AS won
     FROM opportunities o
    WHERE date(o.created_at) BETWEEN ? AND ? ${oScope.sql}`,
    from, to, ...oScope.params,
  );
  return { funnel: rows, range: { from, to } };
}

/** Column headings for the exported workbook. */
const L = {
  ar: {
    file: 'التحليلات', kpis: 'المؤشرات', metric: 'المؤشر', value: 'القيمة',
    pipeline: 'الفرص حسب المرحلة', stage: 'المرحلة', count: 'العدد', amount: 'القيمة', area: 'المساحة م²',
    quotes: 'عروض الأسعار حسب الحالة', status: 'الحالة',
    monthly: 'الاتجاه الشهري', month: 'الشهر', quoted_count: 'عروض صادرة', quoted_value: 'قيمة العروض', won_count: 'صفقات مكسوبة', won_value: 'قيمة المكسوب',
    country: 'حسب الدولة', country_h: 'الدولة', won: 'مكسوب', open_value: 'قيمة الفرص المفتوحة', conversion: 'نسبة التحويل %',
    engineer: 'حسب المهندس', engineer_h: 'المهندس', lost: 'مخسور', win_rate: 'نسبة الكسب %',
    source: 'حسب المصدر', source_h: 'المصدر',
    ptype: 'حسب نوع المشروع', ptype_h: 'نوع المشروع',
    losses: 'أسباب الخسارة', reason: 'السبب',
    price: 'سعر المتر المربع', quotes_n: 'عدد العروض', avg: 'متوسط السعر', min: 'أقل سعر', max: 'أعلى سعر', currency: 'العملة',
    funnel: 'قمع التحويل', created: 'فرص جديدة', qualified: 'مؤهلة', quoted: 'اتسعّرت', negotiation: 'تفاوض',
    open_pipeline: 'قيمة الفرص المفتوحة', weighted: 'القيمة المرجّحة', open_count: 'عدد الفرص المفتوحة',
    won_total: 'قيمة الشغل المكسوب', won_area: 'مساحة مكسوبة م²', win_rate_k: 'نسبة الكسب %',
    quotes_count: 'عدد العروض', quotes_value: 'قيمة العروض', avg_margin: 'متوسط هامش الربح %',
    customers: 'إجمالي العملاء', period: 'الفترة',
    countries: { SA: 'السعودية', EG: 'مصر', QA: 'قطر' },
    stages: { new: 'جديدة', qualified: 'مؤهلة', quoted: 'اتسعّرت', negotiation: 'تفاوض', won: 'كسبناها', lost: 'خسرناها' },
    statuses: { draft: 'مسودة', sent: 'مُرسل', under_review: 'تحت الدراسة', approved: 'معتمد', rejected: 'مرفوض', expired: 'منتهي', cancelled: 'ملغي' },
  },
  en: {
    file: 'analytics', kpis: 'KPIs', metric: 'Metric', value: 'Value',
    pipeline: 'Pipeline by stage', stage: 'Stage', count: 'Count', amount: 'Value', area: 'Area m²',
    quotes: 'Quotations by status', status: 'Status',
    monthly: 'Monthly trend', month: 'Month', quoted_count: 'Quotes issued', quoted_value: 'Quoted value', won_count: 'Deals won', won_value: 'Won value',
    country: 'By country', country_h: 'Country', won: 'Won', open_value: 'Open pipeline value', conversion: 'Conversion %',
    engineer: 'By engineer', engineer_h: 'Engineer', lost: 'Lost', win_rate: 'Win rate %',
    source: 'By source', source_h: 'Source',
    ptype: 'By project type', ptype_h: 'Project type',
    losses: 'Loss reasons', reason: 'Reason',
    price: 'Price per m²', quotes_n: 'Quotes', avg: 'Average', min: 'Minimum', max: 'Maximum', currency: 'Currency',
    funnel: 'Conversion funnel', created: 'Created', qualified: 'Qualified', quoted: 'Quoted', negotiation: 'Negotiation',
    open_pipeline: 'Open pipeline value', weighted: 'Weighted value', open_count: 'Open opportunities',
    won_total: 'Won value', won_area: 'Won area m²', win_rate_k: 'Win rate %',
    quotes_count: 'Quotations issued', quotes_value: 'Quoted value', avg_margin: 'Average margin %',
    customers: 'Customers', period: 'Period',
    countries: { SA: 'Saudi Arabia', EG: 'Egypt', QA: 'Qatar' },
    stages: { new: 'New', qualified: 'Qualified', quoted: 'Quoted', negotiation: 'Negotiation', won: 'Won', lost: 'Lost' },
    statuses: { draft: 'Draft', sent: 'Sent', under_review: 'Under review', approved: 'Approved', rejected: 'Rejected', expired: 'Expired', cancelled: 'Cancelled' },
  },
};

/**
 * Everything the analytics screen shows, as one workbook: a sheet per
 * table, the KPIs on the first. The same queries, the same permission
 * scope, so a manager and an engineer each export what they can see.
 */
function exportAnalytics({ query, user, res }) {
  const format = oneOf(query.format, 'format', FORMATS, { fallback: 'xlsx' });
  const lang = query.lang === 'en' ? 'en' : 'ar';
  const T = L[lang];
  const o = overview({ query, user });
  const m = monthly({ query, user });
  const b = breakdown({ query, user });
  const f = funnel({ query, user }).funnel || {};
  const name = (row) => (lang === 'ar' && row.name_ar) || row.name;
  const num = (key, label) => ({ key, label, type: 'number' });

  const kpiRows = [
    [T.period, `${o.range.from} → ${o.range.to}`],
    [T.open_pipeline, o.open.total], [T.weighted, o.open.weighted], [T.open_count, o.open.count],
    [T.won_total, o.closed.won_value], [T.won_area, o.closed.won_area], [T.win_rate_k, o.closed.win_rate],
    [T.won, o.closed.won_count], [T.lost, o.closed.lost_count],
    [T.quotes_count, o.quotations.count], [T.quotes_value, o.quotations.value],
    o.quotations.avg_margin !== undefined ? [T.avg_margin, Math.round(o.quotations.avg_margin * 10) / 10] : null,
    [T.customers, o.customers?.total],
    [T.created, f.created], [T.qualified, f.qualified], [T.quoted, f.quoted], [T.negotiation, f.negotiation],
  ].filter(Boolean).map(([metric, value]) => ({ metric, value }));

  const months = new Map();
  for (const row of m.quoted) months.set(row.month, { month: row.month, quoted_count: row.count, quoted_value: row.value, won_count: 0, won_value: 0 });
  for (const row of m.won) {
    const entry = months.get(row.month) || { month: row.month, quoted_count: 0, quoted_value: 0 };
    months.set(row.month, { ...entry, won_count: row.count, won_value: row.value });
  }

  const sheets = [
    { name: T.kpis, columns: [{ key: 'metric', label: T.metric }, { key: 'value', label: T.value }], rows: kpiRows },
    {
      name: T.pipeline,
      columns: [{ key: 'stage', label: T.stage }, num('count', T.count), num('value', T.amount), num('area', T.area)],
      rows: o.pipeline.map((r) => ({ ...r, stage: T.stages[r.stage] || r.stage })),
    },
    {
      name: T.quotes,
      columns: [{ key: 'status', label: T.status }, num('count', T.count), num('value', T.amount)],
      rows: o.quotations.by_status.map((r) => ({ ...r, status: T.statuses[r.status] || r.status })),
    },
    {
      name: T.monthly,
      columns: [{ key: 'month', label: T.month }, num('quoted_count', T.quoted_count), num('quoted_value', T.quoted_value), num('won_count', T.won_count), num('won_value', T.won_value)],
      rows: [...months.values()].sort((a, c) => a.month.localeCompare(c.month)),
    },
    {
      name: T.country,
      columns: [{ key: 'country', label: T.country_h }, num('count', T.count), num('won', T.won), num('conversion', T.conversion), num('won_value', T.won_value), num('open_value', T.open_value), num('area', T.area)],
      rows: b.by_country.map((r) => ({ ...r, country: T.countries[r.country] || r.country, conversion: r.count ? Math.round((r.won / r.count) * 100) : 0 })),
    },
    {
      name: T.engineer,
      columns: [{ key: 'engineer', label: T.engineer_h }, num('count', T.count), num('won', T.won), num('lost', T.lost), num('win_rate', T.win_rate), num('won_value', T.won_value), num('open_value', T.open_value)],
      rows: b.by_owner.map((r) => ({ ...r, engineer: name(r), win_rate: (r.won + r.lost) ? Math.round((r.won / (r.won + r.lost)) * 100) : 0 })),
    },
    { name: T.source, columns: [{ key: 'source', label: T.source_h }, num('count', T.count), num('won', T.won)], rows: b.by_source },
    { name: T.ptype, columns: [{ key: 'project_type', label: T.ptype_h }, num('count', T.count), num('area', T.area), num('won_value', T.won_value)], rows: b.by_project_type },
    { name: T.losses, columns: [{ key: 'reason', label: T.reason }, num('count', T.count), num('value', T.amount)], rows: b.lost_reasons },
    {
      name: T.price,
      columns: [{ key: 'country', label: T.country_h }, { key: 'currency', label: T.currency }, num('quotes', T.quotes_n), num('min_price', T.min), num('avg_price', T.avg), num('max_price', T.max)],
      rows: b.price_per_sqm.map((r) => ({ ...r, country: T.countries[r.country] || r.country })),
    },
  ];

  sendDownload(res, {
    filename: `${T.file}-${o.range.from}-${o.range.to}`,
    fallback: `analytics-${o.range.from}-${o.range.to}`,
    format,
    rtl: lang === 'ar',
    sheets,
  });
}

export function register(router) {
  router.get('/api/analytics/overview', overview);
  router.get('/api/analytics/monthly', monthly);
  router.get('/api/analytics/breakdown', breakdown);
  router.get('/api/analytics/funnel', funnel);
  router.get('/api/analytics/export', exportAnalytics);
}
