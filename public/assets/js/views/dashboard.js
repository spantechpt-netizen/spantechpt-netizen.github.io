/**
 * The dashboard, as widgets the person arranges.
 *
 * Each block on the page is a widget with a key. The order and which are
 * shown are the person's own, saved on their profile, so a sales engineer
 * can put the follow-ups first and drop the country table, while a manager
 * leads with the pipeline. "Customise" turns on drag handles and hide
 * buttons; dragging moves a widget, the change saves as it happens, and
 * hidden widgets wait as chips under the page to be brought back.
 */
import { api } from '../api.js';
import { t, pick, money, moneyShort, formatDate, relativeDays, isRTL } from '../i18n.js';
import { el, clear, icon, dataTable, quoteStatusBadge, stageBadge, toast, toastError } from '../ui.js';

const CURRENCY_BY_COUNTRY = { SA: 'SAR', EG: 'EGP', QA: 'QAR' };

/** Every widget the dashboard knows, in its default order. */
const WIDGETS = ['kpis', 'followups', 'deals', 'quotes', 'country'];

/** The stored layout, or the default when nothing has been saved. */
function layoutOf(user) {
  let saved = null;
  try { saved = user.dashboard_json ? JSON.parse(user.dashboard_json) : null; } catch { saved = null; }
  const seen = new Set();
  const out = [];
  for (const item of Array.isArray(saved) ? saved : []) {
    if (!WIDGETS.includes(item?.key) || seen.has(item.key)) continue;
    seen.add(item.key);
    out.push({ key: item.key, hidden: Boolean(item.hidden) });
  }
  for (const key of WIDGETS) if (!seen.has(key)) out.push({ key, hidden: false });
  return out;
}

export async function render({ navigate, state }) {
  const [overview, followUps, recentQuotes, topDeals] = await Promise.all([
    api.overview(),
    api.activities({ done: 0, limit: 12 }),
    api.quotations({ limit: 8 }),
    api.opportunities({ open: 1 }),
  ]);
  const byCountry = (overview.pipeline || []).length
    ? await api.breakdown().then((r) => r.by_country).catch(() => [])
    : [];

  const data = { overview, followUps, recentQuotes, topDeals, byCountry, state, navigate };
  let layout = layoutOf(state.user);
  let editing = false;

  const page = el('div.dashboard');

  // ------------------------------------------------------------- greeting
  const hour = new Date().getHours();
  const greeting = isRTL()
    ? (hour < 12 ? 'صباح الخير' : 'مساء الخير')
    : (hour < 12 ? 'Good morning' : 'Good afternoon');
  const customiseButton = el('button.btn.btn-sm.btn-secondary', {
    type: 'button', onclick: () => { editing = !editing; draw(); },
  });
  page.append(el('div.row', { style: { marginBottom: '1rem' } }, [
    el('p.muted', { style: { margin: 0 } }, [
      `${greeting}، ${pick(state.user, 'name')} · ${formatDate(new Date().toISOString().slice(0, 10))}`,
    ]),
    el('div.spacer'),
    customiseButton,
  ]));

  const grid = el('div.dash-grid');
  const hiddenBar = el('div.dash-hidden');
  page.append(grid, hiddenBar);

  // ------------------------------------------------------------ persistence
  async function save() {
    try {
      const { user } = await api.updateProfile({ dashboard: layout });
      state.user.dashboard_json = user.dashboard_json;
    } catch (error) { toastError(error); }
  }

  // ------------------------------------------------------------------ draw
  function draw() {
    clear(customiseButton).append(icon(editing ? 'check' : 'settings2', 14), editing ? t('dash_done') : t('dash_customise'));
    page.classList.toggle('is-editing', editing);
    clear(grid);
    for (const item of layout) {
      if (item.hidden) continue;
      grid.append(widgetShell(item.key));
    }
    clear(hiddenBar);
    const hidden = layout.filter((item) => item.hidden);
    if (editing && hidden.length) {
      hiddenBar.append(el('span.tiny.muted', { text: t('dash_hidden') }));
      for (const item of hidden) {
        hiddenBar.append(el('button.btn.btn-sm.btn-secondary', {
          type: 'button', onclick: () => { item.hidden = false; save(); draw(); },
        }, [icon('eye', 13), t(`widget_${item.key}`)]));
      }
    }
    if (editing) hiddenBar.append(el('p.hint', { text: t('dash_hint') }));
  }

  /** The card frame around a widget: a title bar in edit mode, drag and drop. */
  function widgetShell(key) {
    const shell = el('section.dash-widget', { dataset: { key }, class: WIDE.has(key) ? 'wide' : '' });
    if (editing) {
      shell.draggable = true;
      shell.append(el('div.dash-handle', {}, [
        icon('grip', 14),
        el('span', { text: t(`widget_${key}`) }),
        el('div.spacer'),
        el('button.btn.btn-sm.btn-ghost', {
          type: 'button', title: t('dash_hide'), 'aria-label': t('dash_hide'),
          onclick: () => {
            const item = layout.find((w) => w.key === key);
            if (item) { item.hidden = true; save(); draw(); }
          },
        }, [icon('eyeOff', 14)]),
      ]));
      shell.addEventListener('dragstart', (event) => {
        event.dataTransfer.setData('text/plain', key);
        event.dataTransfer.effectAllowed = 'move';
        shell.classList.add('is-dragging');
      });
      shell.addEventListener('dragend', () => shell.classList.remove('is-dragging'));
      shell.addEventListener('dragover', (event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        shell.classList.add('is-over');
      });
      shell.addEventListener('dragleave', () => shell.classList.remove('is-over'));
      shell.addEventListener('drop', (event) => {
        event.preventDefault();
        shell.classList.remove('is-over');
        const from = event.dataTransfer.getData('text/plain');
        if (!from || from === key) return;
        move(from, key);
      });
    }
    shell.append(BUILDERS[key](data));
    return shell;
  }

  /** Puts widget `from` where widget `to` is, shifting the rest along. */
  function move(from, to) {
    const order = layout.map((w) => w.key);
    const fromIndex = order.indexOf(from);
    const toIndex = order.indexOf(to);
    if (fromIndex < 0 || toIndex < 0) return;
    const [moved] = layout.splice(fromIndex, 1);
    layout.splice(toIndex, 0, moved);
    save();
    draw();
    toast(t('saved'), 'success', 1200);
  }

  draw();
  return page;
}

/** Widgets that take the full width of the grid. */
const WIDE = new Set(['kpis', 'quotes', 'country']);

// ------------------------------------------------------------------ widgets
const BUILDERS = {
  kpis({ overview, state }) {
    const open = overview.open || {};
    const closed = overview.closed || {};
    return el('div.kpi-grid', { style: { marginBottom: 0 } }, [
      kpi('accent', t('kpi_open_pipeline'), moneyShort(open.total), `${open.count || 0} ${t('pipeline')}`),
      kpi('', t('kpi_weighted'), moneyShort(open.weighted), t('probability')),
      kpi(closed.win_rate >= 50 ? 'ok' : 'warn', t('kpi_win_rate'), `${closed.win_rate || 0}%`,
        `${closed.won_count || 0} ${t('won')} · ${closed.lost_count || 0} ${t('lost')}`),
      kpi('ok', t('kpi_won_value'), moneyShort(closed.won_value), `${money(closed.won_area || 0, 0)} m²`),
      kpi('', t('kpi_quotes_sent'), overview.quotations?.count || 0, moneyShort(overview.quotations?.value)),
      kpi(state.activitySummary.overdue > 0 ? 'danger' : 'ok', t('overdue'),
        state.activitySummary.overdue, `${state.activitySummary.today} ${t('due_today')}`),
    ]);
  },

  followups({ followUps, navigate }) {
    return card(t('follow_ups'), () => navigate('activities'), followUpList(followUps.activities, navigate));
  },

  deals({ topDeals, navigate }) {
    const deals = (topDeals.opportunities || [])
      .sort((a, b) => (b.expected_value * b.probability) - (a.expected_value * a.probability))
      .slice(0, 8);
    return card(t('top_opportunities'), () => navigate('pipeline'), dataTable({
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
    }));
  },

  quotes({ recentQuotes, navigate }) {
    return card(t('recent_quotes'), () => navigate('quotations'), dataTable({
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
    }));
  },

  country({ byCountry }) {
    return card(t('by_country'), null, dataTable({
      rows: byCountry,
      empty: t('no_data'),
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
    }));
  },
};

function card(title, onOpen, body) {
  return el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: title }),
      el('div.spacer'),
      onOpen ? el('button.btn.btn-sm.btn-ghost', { type: 'button', text: t('open'), onclick: onOpen }) : null,
    ]),
    el('div.card-body.flush', {}, [body]),
  ]);
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
