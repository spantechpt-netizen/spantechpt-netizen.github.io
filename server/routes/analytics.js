import { all, get } from '../db.js';
import { requirePermission, canSeeAll } from '../auth.js';

/**
 * Engineers see only their own numbers; managers and admins see the company.
 * Returns a SQL fragment plus the parameters it needs.
 */
function scopeFor(user, alias, query) {
  if (canSeeAll(user) && query.owner_id) return { sql: `AND ${alias}.owner_id = ?`, params: [Number(query.owner_id)] };
  if (canSeeAll(user)) return { sql: '', params: [] };
  return { sql: `AND ${alias}.owner_id = ?`, params: [user.id] };
}

function dateRange(query) {
  const to = query.to || new Date().toISOString().slice(0, 10);
  const from = query.from || (() => {
    const d = new Date(`${to}T00:00:00Z`);
    d.setUTCFullYear(d.getUTCFullYear() - 1);
    return d.toISOString().slice(0, 10);
  })();
  return { from, to };
}

export function register(router) {
  router.get('/api/analytics/overview', ({ query, user }) => {
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
      quotations: { ...quotes, by_status: quoteStatus },
      customers: get(
        `SELECT COUNT(*) AS total,
                SUM(CASE WHEN status = 'target'   THEN 1 ELSE 0 END) AS targets,
                SUM(CASE WHEN status = 'active'   THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN status = 'prospect' THEN 1 ELSE 0 END) AS prospects
           FROM customers c WHERE 1=1 ${canSeeAll(user) ? '' : 'AND c.owner_id = ?'}`,
        ...(canSeeAll(user) ? [] : [user.id]),
      ),
    };
  });

  /** Monthly quotation volume and won value, for the trend chart. */
  router.get('/api/analytics/monthly', ({ query, user }) => {
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
  });

  /** Breakdown by country, engineer, source, sector and loss reason. */
  router.get('/api/analytics/breakdown', ({ query, user }) => {
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
  });

  /** Conversion funnel: every opportunity created in the window, by furthest stage reached. */
  router.get('/api/analytics/funnel', ({ query, user }) => {
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
  });
}
