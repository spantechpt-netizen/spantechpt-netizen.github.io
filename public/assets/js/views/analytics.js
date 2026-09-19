import { api } from '../api.js';
import { t, pick, money, moneyShort, getLang } from '../i18n.js';
import { el, clear, dataTable, blankOption, exportMenu } from '../ui.js';
import { can, canSeeCost, state } from '../app.js';
import { barChart, funnelChart, columnChart, donutChart, PALETTE } from '../charts.js';
import { printReport } from './report-print.js';

const CURRENCY_BY_COUNTRY = { SA: 'SAR', EG: 'EGP', QA: 'QAR' };
const filters = { from: '', to: '', country: '', owner_id: '' };

export async function render() {
  const page = el('div');
  const host = el('div');

  // Default window: the last 12 months.
  if (!filters.from) {
    const to = new Date();
    const from = new Date();
    from.setFullYear(from.getFullYear() - 1);
    filters.from = from.toISOString().slice(0, 10);
    filters.to = to.toISOString().slice(0, 10);
  }

  const preset = (label, months) => el('button.btn.btn-sm.btn-secondary', {
    type: 'button', text: label,
    onclick: () => {
      const to = new Date();
      const from = new Date();
      if (months === 'ytd') from.setMonth(0, 1);
      else from.setMonth(from.getMonth() - months);
      filters.from = from.toISOString().slice(0, 10);
      filters.to = to.toISOString().slice(0, 10);
      fromInput.value = filters.from;
      toInput.value = filters.to;
      refresh();
    },
  });

  const fromInput = el('input', {
    type: 'date', value: filters.from, style: { width: 'auto' },
    onchange: (event) => { filters.from = event.target.value; refresh(); },
  });
  const toInput = el('input', {
    type: 'date', value: filters.to, style: { width: 'auto' },
    onchange: (event) => { filters.to = event.target.value; refresh(); },
  });

  page.append(el('div.toolbar', {}, [
    el('span.small.bold', { text: t('period') }),
    fromInput, toInput,
    preset(t('last_12_months'), 12),
    preset(t('this_year'), 'ytd'),
    preset(t('this_quarter'), 3),
    el('select', {
      onchange: (event) => { filters.country = event.target.value; refresh(); },
    }, [blankOption(t('country')), ...['SA', 'EG', 'QA'].map((c) => ({ value: c, label: t(`country_${c}`) }))]
      .map((option) => {
        const node = el('option', { value: option.value, text: option.label });
        if (option.value === filters.country) node.selected = true;
        return node;
      })),
    can('analytics.view_all') ? el('select', {
      onchange: (event) => { filters.owner_id = event.target.value; refresh(); },
    }, [blankOption(t('by_engineer')), ...state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') }))]
      .map((option) => {
        const node = el('option', { value: option.value, text: option.label });
        if (String(option.value) === String(filters.owner_id)) node.selected = true;
        return node;
      })) : null,
  ]));

  let latest = null;
  page.querySelector('.toolbar').append(
    el('div.spacer'),
    exportMenu({
      href: (format) => {
        const params = new URLSearchParams({ format, lang: getLang() });
        for (const [key, value] of Object.entries(filters)) if (value) params.set(key, value);
        return `/api/analytics/export?${params}`;
      },
      onPdf: () => { if (latest) printAnalytics(latest); },
    }),
  );

  page.append(host);

  async function refresh() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const [overview, monthly, breakdown, funnel] = await Promise.all([
        api.overview(filters), api.monthly(filters),
        api.breakdown(filters), api.funnel(filters),
      ]);
      latest = { overview, monthly, breakdown, funnel };
      clear(host).append(build(overview, monthly, breakdown, funnel));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await refresh();
  return page;
}

function build(overview, monthly, breakdown, funnel) {
  const wrap = el('div');
  const closed = overview.closed || {};
  const open = overview.open || {};

  // -------------------------------------------------------------- KPI row
  wrap.append(el('div.kpi-grid', {}, [
    kpi('accent', t('kpi_open_pipeline'), moneyShort(open.total), `${open.count || 0}`),
    kpi('', t('kpi_weighted'), moneyShort(open.weighted)),
    kpi(closed.win_rate >= 50 ? 'ok' : 'warn', t('kpi_win_rate'), `${closed.win_rate || 0}%`,
      `${closed.won_count || 0} / ${(closed.won_count || 0) + (closed.lost_count || 0)}`),
    kpi('ok', t('value_won'), moneyShort(closed.won_value), `${money(closed.won_area || 0, 0)} m²`),
    kpi('', t('quotes_issued'), overview.quotations?.count || 0, moneyShort(overview.quotations?.value)),
    canSeeCost() ? kpi('', t('margin'), `${Number(overview.quotations?.avg_margin || 0).toFixed(1)}%`) : null,
  ]));

  // ------------------------------------------------- funnel + monthly trend
  const twoUp = el('div.grid.grid-2', { style: { alignItems: 'start' } });

  const f = funnel.funnel || {};
  twoUp.append(card(t('conversion_funnel'), funnelChart([
    { label: t('created'), value: f.created || 0 },
    { label: t('qualified'), value: f.qualified || 0 },
    { label: t('quoted'), value: f.quoted || 0 },
    { label: t('negotiation'), value: f.negotiation || 0 },
    { label: t('won'), value: f.won || 0 },
  ])));

  twoUp.append(card(t('monthly_trend'), columnChart({
    series: [
      { name: t('quotes_issued'), colour: PALETTE[2], points: (monthly.quoted || []).map((row) => ({ x: row.month, y: row.value })) },
      { name: t('value_won'), colour: PALETTE[5], points: (monthly.won || []).map((row) => ({ x: row.month, y: row.value })) },
    ],
  })));
  wrap.append(twoUp);

  // ------------------------------------------------------- country + owner
  const threeUp = el('div.grid.grid-2', { style: { alignItems: 'start' } });

  threeUp.append(card(t('by_country'), el('div', {}, [
    donutChart({
      data: (breakdown.by_country || []).map((row) => ({
        label: t(`country_${row.country}`), value: Number(row.won_value || 0),
      })),
      format: moneyShort,
    }),
    dataTable({
      rows: breakdown.by_country || [],
      columns: [
        { label: t('country'), render: (row) => t(`country_${row.country}`) },
        { label: t('pipeline'), className: 'num', render: (row) => row.count },
        { label: t('won'), className: 'num', render: (row) => row.won },
        {
          label: t('conversion_rate'), className: 'num',
          render: (row) => `${row.count ? Math.round((row.won / row.count) * 100) : 0}%`,
        },
        {
          label: t('value_won'), className: 'num',
          render: (row) => `${moneyShort(row.won_value)} ${CURRENCY_BY_COUNTRY[row.country] || ''}`,
        },
        { label: 'm²', className: 'num', render: (row) => money(row.area, 0) },
      ],
    }),
  ])));

  threeUp.append(card(t('by_engineer'), dataTable({
    rows: breakdown.by_owner || [],
    columns: [
      { label: t('owner'), render: (row) => pick(row, 'name') },
      { label: t('pipeline'), className: 'num', render: (row) => row.count },
      { label: t('won'), className: 'num', render: (row) => row.won },
      { label: t('lost'), className: 'num', render: (row) => row.lost },
      {
        label: t('kpi_win_rate'), className: 'num',
        render: (row) => {
          const decided = row.won + row.lost;
          const rate = decided ? Math.round((row.won / decided) * 100) : 0;
          return el('span.badge', { class: rate >= 50 ? 'green' : rate >= 25 ? 'amber' : 'red', text: `${rate}%` });
        },
      },
      { label: t('value_won'), className: 'num', render: (row) => moneyShort(row.won_value) },
      { label: t('kpi_open_pipeline'), className: 'num', render: (row) => moneyShort(row.open_value) },
    ],
  })));
  wrap.append(threeUp);

  // ------------------------------------------------- source / type / losses
  const fourUp = el('div.grid.grid-2', { style: { alignItems: 'start' } });

  fourUp.append(card(t('by_source'), barChart({
    data: (breakdown.by_source || []).map((row) => ({
      label: row.source === 'unknown' ? t('none') : t(`source_${row.source}`),
      value: row.count,
    })),
    format: (v) => String(v),
  })));

  fourUp.append(card(t('by_project_type'), barChart({
    data: (breakdown.by_project_type || []).map((row) => ({
      label: t(`ptype_${row.project_type}`),
      value: row.count,
    })),
    format: (v) => String(v),
  })));

  fourUp.append(card(t('loss_analysis'), el('div', {}, [
    barChart({
      data: (breakdown.lost_reasons || []).map((row) => ({
        label: t(`reason_${row.reason}`), value: row.count,
      })),
      format: (v) => String(v),
      colour: '#a32020',
    }),
    dataTable({
      rows: breakdown.lost_reasons || [],
      columns: [
        { label: t('lost_reason'), render: (row) => t(`reason_${row.reason}`) },
        { label: t('opportunities_count'), className: 'num', render: (row) => row.count },
        { label: t('expected_value'), className: 'num', render: (row) => moneyShort(row.value) },
      ],
    }),
  ])));

  fourUp.append(card(t('price_benchmark'), dataTable({
    rows: breakdown.price_per_sqm || [],
    empty: t('no_data'),
    columns: [
      { label: t('country'), render: (row) => t(`country_${row.country}`) },
      { label: t('quotes_issued'), className: 'num', render: (row) => row.quotes },
      { label: t('min_price'), className: 'num', render: (row) => `${money(row.min_price)} ${row.currency}` },
      {
        label: t('avg_price'), className: 'num',
        render: (row) => el('span.bold', { text: `${money(row.avg_price)} ${row.currency}` }),
      },
      { label: t('max_price'), className: 'num', render: (row) => `${money(row.max_price)} ${row.currency}` },
    ],
  })));
  wrap.append(fourUp);

  // ----------------------------------------------------- quotes by status
  wrap.append(card(t('quotations'), dataTable({
    rows: overview.quotations?.by_status || [],
    columns: [
      { label: t('status'), render: (row) => t(`qstatus_${row.status}`) },
      { label: t('quotes_issued'), className: 'num', render: (row) => row.count },
      { label: t('net_amount'), className: 'num', render: (row) => moneyShort(row.value) },
    ],
  })));

  return wrap;
}

/** The screen's figures as an A4 report for the print dialogue. */
function printAnalytics({ overview, monthly, breakdown, funnel }) {
  const closed = overview.closed || {};
  const open = overview.open || {};
  const f = funnel.funnel || {};
  const owner = filters.owner_id ? state.users.find((u) => String(u.id) === String(filters.owner_id)) : null;
  const months = new Map();
  for (const row of monthly.quoted || []) months.set(row.month, { month: row.month, qc: row.count, qv: row.value, wc: 0, wv: 0 });
  for (const row of monthly.won || []) months.set(row.month, { ...(months.get(row.month) || { month: row.month, qc: 0, qv: 0 }), wc: row.count, wv: row.value });

  printReport({
    lang: getLang(),
    title: t('report_analytics'),
    subtitle: `${overview.range.from} → ${overview.range.to}`,
    meta: [
      [t('country'), filters.country ? t(`country_${filters.country}`) : t('report_all')],
      [t('by_engineer'), owner ? pick(owner, 'name') : t('report_all')],
    ],
    sections: [
      { heading: t('report_kpis'), kpis: [
        { label: t('kpi_open_pipeline'), value: moneyShort(open.total), meta: `${open.count || 0}` },
        { label: t('kpi_weighted'), value: moneyShort(open.weighted) },
        { label: t('kpi_win_rate'), value: `${closed.win_rate || 0}%`, meta: `${closed.won_count || 0} / ${(closed.won_count || 0) + (closed.lost_count || 0)}` },
        { label: t('value_won'), value: moneyShort(closed.won_value), meta: `${money(closed.won_area || 0, 0)} m²` },
        { label: t('quotes_issued'), value: overview.quotations?.count || 0, meta: moneyShort(overview.quotations?.value) },
        canSeeCost() ? { label: t('margin'), value: `${Number(overview.quotations?.avg_margin || 0).toFixed(1)}%` } : null,
      ].filter(Boolean) },
      { heading: t('conversion_funnel'), columns: [{ label: t('stage') }, { label: t('opportunities_count'), className: 'num' }],
        rows: [[t('created'), f.created || 0], [t('qualified'), f.qualified || 0], [t('quoted'), f.quoted || 0], [t('negotiation'), f.negotiation || 0], [t('won'), f.won || 0]] },
      { heading: t('report_pipeline_stage'), columns: [{ label: t('stage') }, { label: t('opportunities_count'), className: 'num' }, { label: t('expected_value'), className: 'num' }, { label: 'm²', className: 'num' }],
        rows: (overview.pipeline || []).map((r) => [t(`stage_${r.stage}`), r.count, moneyShort(r.value), money(r.area || 0, 0)]) },
      { heading: t('monthly_trend'), columns: [{ label: t('period') }, { label: t('quotes_issued'), className: 'num' }, { label: t('net_amount'), className: 'num' }, { label: t('won'), className: 'num' }, { label: t('value_won'), className: 'num' }],
        rows: [...months.values()].sort((a, b) => a.month.localeCompare(b.month)).map((r) => [r.month, r.qc, moneyShort(r.qv), r.wc, moneyShort(r.wv)]) },
      { heading: t('by_country'), columns: [{ label: t('country') }, { label: t('pipeline'), className: 'num' }, { label: t('won'), className: 'num' }, { label: t('conversion_rate'), className: 'num' }, { label: t('value_won'), className: 'num' }, { label: 'm²', className: 'num' }],
        rows: (breakdown.by_country || []).map((r) => [t(`country_${r.country}`), r.count, r.won, `${r.count ? Math.round((r.won / r.count) * 100) : 0}%`, `${moneyShort(r.won_value)} ${CURRENCY_BY_COUNTRY[r.country] || ''}`, money(r.area, 0)]) },
      { heading: t('by_engineer'), columns: [{ label: t('owner') }, { label: t('pipeline'), className: 'num' }, { label: t('won'), className: 'num' }, { label: t('lost'), className: 'num' }, { label: t('kpi_win_rate'), className: 'num' }, { label: t('value_won'), className: 'num' }, { label: t('kpi_open_pipeline'), className: 'num' }],
        rows: (breakdown.by_owner || []).map((r) => [pick(r, 'name'), r.count, r.won, r.lost, `${(r.won + r.lost) ? Math.round((r.won / (r.won + r.lost)) * 100) : 0}%`, moneyShort(r.won_value), moneyShort(r.open_value)]) },
      { heading: t('by_source'), columns: [{ label: t('source') }, { label: t('opportunities_count'), className: 'num' }, { label: t('won'), className: 'num' }],
        rows: (breakdown.by_source || []).map((r) => [r.source === 'unknown' ? t('none') : t(`source_${r.source}`), r.count, r.won]) },
      { heading: t('by_project_type'), columns: [{ label: t('project_type') }, { label: t('opportunities_count'), className: 'num' }, { label: 'm²', className: 'num' }, { label: t('value_won'), className: 'num' }],
        rows: (breakdown.by_project_type || []).map((r) => [t(`ptype_${r.project_type}`), r.count, money(r.area, 0), moneyShort(r.won_value)]) },
      { heading: t('loss_analysis'), columns: [{ label: t('lost_reason') }, { label: t('opportunities_count'), className: 'num' }, { label: t('expected_value'), className: 'num' }],
        rows: (breakdown.lost_reasons || []).map((r) => [t(`reason_${r.reason}`), r.count, moneyShort(r.value)]) },
      { heading: t('price_benchmark'), columns: [{ label: t('country') }, { label: t('quotes_issued'), className: 'num' }, { label: t('min_price'), className: 'num' }, { label: t('avg_price'), className: 'num' }, { label: t('max_price'), className: 'num' }],
        rows: (breakdown.price_per_sqm || []).map((r) => [t(`country_${r.country}`), r.quotes, `${money(r.min_price)} ${r.currency}`, `${money(r.avg_price)} ${r.currency}`, `${money(r.max_price)} ${r.currency}`]) },
      { heading: t('quotations'), columns: [{ label: t('status') }, { label: t('quotes_issued'), className: 'num' }, { label: t('net_amount'), className: 'num' }],
        rows: (overview.quotations?.by_status || []).map((r) => [t(`qstatus_${r.status}`), r.count, moneyShort(r.value)]) },
    ],
  });
}

const kpi = (tone, label, value, meta) => el(`div.kpi${tone ? `.${tone}` : ''}`, {}, [
  el('div.label', { text: label }),
  el('div.value.num', { text: String(value ?? 0) }),
  meta ? el('div.meta', { text: meta }) : null,
]);

const card = (title, content) => el('div.card', {}, [
  el('div.card-header', {}, [el('h3', { text: title })]),
  el('div.card-body', {}, [content]),
]);
