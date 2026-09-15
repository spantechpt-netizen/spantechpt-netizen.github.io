import { api } from '../api.js';
import { t, pick, money, moneyShort, formatDate, relativeDays, isRTL } from '../i18n.js';
import { el, icon, dataTable, quoteStatusBadge, stageBadge, toast, toastError } from '../ui.js';

const CURRENCY_BY_COUNTRY = { SA: 'SAR', EG: 'EGP', QA: 'QAR' };

export async function render({ navigate, state }) {
  const [overview, followUps, recentQuotes, topDeals] = await Promise.all([
    api.overview(),
    api.activities({ done: 0, limit: 12 }),
    api.quotations({ limit: 8 }),
    api.opportunities({ open: 1 }),
  ]);

  const page = el('div');

  // ------------------------------------------------------------- greeting
  const hour = new Date().getHours();
  const greeting = isRTL()
    ? (hour < 12 ? 'صباح الخير' : 'مساء الخير')
    : (hour < 12 ? 'Good morning' : 'Good afternoon');
  page.append(el('p.muted', { style: { marginBottom: '1rem' } }, [
    `${greeting}، ${pick(state.user, 'name')} · ${formatDate(new Date().toISOString().slice(0, 10))}`,
  ]));

  // ----------------------------------------------------------------- KPIs
  const open = overview.open || {};
  const closed = overview.closed || {};
  page.append(el('div.kpi-grid', {}, [
    kpi('accent', t('kpi_open_pipeline'), moneyShort(open.total), `${open.count || 0} ${t('pipeline')}`),
    kpi('', t('kpi_weighted'), moneyShort(open.weighted), t('probability')),
    kpi(closed.win_rate >= 50 ? 'ok' : 'warn', t('kpi_win_rate'), `${closed.win_rate || 0}%`,
      `${closed.won_count || 0} ${t('won')} · ${closed.lost_count || 0} ${t('lost')}`),
    kpi('ok', t('kpi_won_value'), moneyShort(closed.won_value), `${money(closed.won_area || 0, 0)} m²`),
    kpi('', t('kpi_quotes_sent'), overview.quotations?.count || 0, moneyShort(overview.quotations?.value)),
    kpi(state.activitySummary.overdue > 0 ? 'danger' : 'ok', t('overdue'),
      state.activitySummary.overdue, `${state.activitySummary.today} ${t('due_today')}`),
  ]));

  // ---------------------------------------------------- follow-ups + deals
  const twoUp = el('div.grid.grid-2', { style: { alignItems: 'start' } });

  twoUp.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('follow_ups') }),
      el('div.spacer'),
      el('button.btn.btn-sm.btn-ghost', { type: 'button', text: t('open'), onclick: () => navigate('activities') }),
    ]),
    el('div.card-body.flush', {}, [followUpList(followUps.activities, navigate)]),
  ]));

  const deals = (topDeals.opportunities || [])
    .sort((a, b) => (b.expected_value * b.probability) - (a.expected_value * a.probability))
    .slice(0, 8);

  twoUp.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('top_opportunities') }),
      el('div.spacer'),
      el('button.btn.btn-sm.btn-ghost', { type: 'button', text: t('open'), onclick: () => navigate('pipeline') }),
    ]),
    el('div.card-body.flush', {}, [dataTable({
      rows: deals,
      onRowClick: () => navigate('pipeline'),
      columns: [
        {
          label: t('opportunity_title'),
          render: (row) => el('div', {}, [
            el('div.bold', { text: pick(row, 'title') }),
            el('div.tiny.muted', { text: pick(row, 'customer_name') }),
          ]),
        },
        { label: t('stage'), render: (row) => stageBadge(row.stage) },
        {
          label: t('expected_value'), className: 'num',
          render: (row) => el('div', {}, [
            el('div.bold', { text: `${moneyShort(row.expected_value)} ${row.currency}` }),
            el('div.tiny.muted', { text: `${row.probability}%` }),
          ]),
        },
      ],
    })]),
  ]));
  page.append(twoUp);

  // ------------------------------------------------------- recent quotes
  page.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('recent_quotes') }),
      el('div.spacer'),
      el('button.btn.btn-sm.btn-ghost', { type: 'button', text: t('open'), onclick: () => navigate('quotations') }),
    ]),
    el('div.card-body.flush', {}, [dataTable({
      rows: (recentQuotes.quotations || []).slice(0, 8),
      onRowClick: (row) => navigate(`quote/${row.id}`),
      columns: [
        {
          label: t('quote_number'),
          render: (row) => el('div', {}, [
            el('div.bold.num', { text: row.number }),
            row.revision > 0 ? el('span.badge.grey', { text: `${t('revision')} ${row.revision}` }) : null,
          ]),
        },
        {
          label: t('project_name'),
          render: (row) => el('div', {}, [
            el('div', { text: pick(row, 'project_name') }),
            el('div.tiny.muted', { text: pick(row, 'customer_name') }),
          ]),
        },
        { label: t('issue_date'), render: (row) => formatDate(row.issue_date) },
        { label: t('status'), render: (row) => quoteStatusBadge(row.status) },
        {
          label: t('grand_total'), className: 'num',
          render: (row) => `${money(row.total)} ${row.currency}`,
        },
      ],
    })]),
  ]));

  // --------------------------------------------- pipeline by country strip
  const byCountry = (overview.pipeline || []).length
    ? await api.breakdown().then((r) => r.by_country).catch(() => [])
    : [];
  if (byCountry.length) {
    page.append(el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: t('by_country') })]),
      el('div.card-body.flush', {}, [dataTable({
        rows: byCountry,
        columns: [
          { label: t('country'), render: (row) => t(`country_${row.country}`) },
          { label: t('pipeline'), className: 'num', render: (row) => row.count },
          { label: t('won'), className: 'num', render: (row) => row.won },
          {
            label: t('value_won'), className: 'num',
            render: (row) => `${moneyShort(row.won_value)} ${CURRENCY_BY_COUNTRY[row.country] || ''}`,
          },
          {
            label: t('kpi_open_pipeline'), className: 'num',
            render: (row) => `${moneyShort(row.open_value)} ${CURRENCY_BY_COUNTRY[row.country] || ''}`,
          },
          { label: 'm²', className: 'num', render: (row) => money(row.area, 0) },
        ],
      })]),
    ]));
  }

  return page;
}

function kpi(tone, label, value, meta) {
  return el(`div.kpi${tone ? `.${tone}` : ''}`, {}, [
    el('div.label', { text: label }),
    el('div.value.num', { text: String(value ?? 0) }),
    meta ? el('div.meta', { text: meta }) : null,
  ]);
}

function followUpList(items, navigate) {
  if (!items || !items.length) {
    return el('div.empty', {}, [icon('check', 40), el('div', { text: t('all_clear') })]);
  }
  const list = el('div');
  for (const item of items) {
    const { days, label } = relativeDays(item.due_at);
    const tone = days === null ? '' : days < 0 ? 'is-overdue' : days === 0 ? 'is-today' : '';

    const row = el(`div.followup${tone ? `.${tone}` : ''}`, {}, [
      el('button.tick', {
        type: 'button', title: t('mark_done'),
        onclick: async (event) => {
          event.stopPropagation();
          try {
            await api.updateActivity(item.id, { done: true });
            row.remove();
            toast(t('saved'), 'success');
          } catch (error) { toastError(error); }
        },
      }),
      el('div.body', {}, [
        el('div.subject', { text: item.subject }),
        el('div.meta', {}, [
          el('span.badge.grey', { text: t(`act_${item.type}`) }),
          ' ',
          el('span', { text: pick(item, 'customer_name') || '—' }),
          item.due_at ? el('span.due', { text: ` · ${label}` }) : null,
        ]),
      ]),
    ]);
    row.addEventListener('click', () => navigate('activities'));
    row.style.cursor = 'pointer';
    list.append(row);
  }
  return list;
}
