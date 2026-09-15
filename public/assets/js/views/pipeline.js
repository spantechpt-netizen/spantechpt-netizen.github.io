import { api } from '../api.js';
import { t, pick, money, moneyShort, formatDate } from '../i18n.js';
import {
  el, clear, icon, dataTable, field, readForm, openModal, confirmDialog,
  toast, toastError, stageBadge, optionsFrom, blankOption,
} from '../ui.js';
import { canEdit, canSeeAll, state } from '../app.js';

const STAGES = ['new', 'qualified', 'quoted', 'negotiation', 'won', 'lost'];
const PROJECT_TYPES = ['tower', 'school', 'mall', 'villa', 'rest_house', 'admin', 'hospital', 'parking', 'industrial', 'other'];
const LOST_REASONS = ['price', 'timing', 'competitor', 'scope', 'no_budget', 'no_response', 'other'];
const SOURCES = ['referral', 'website', 'exhibition', 'cold_call', 'existing', 'tender', 'social'];
const COUNTRIES = ['SA', 'EG', 'QA'];
const CURRENCY_BY_COUNTRY = { SA: 'SAR', EG: 'EGP', QA: 'QAR' };

const view = { mode: 'board', country: '', owner: '', q: '' };

export async function render({ navigate }) {
  const page = el('div');
  const host = el('div');

  page.append(el('div.toolbar', {}, [
    el('div.search-box', {}, [icon('search', 15), el('input', {
      type: 'search', placeholder: t('search'), value: view.q,
      oninput: debounce((event) => { view.q = event.target.value; refresh(); }, 280),
    })]),
    el('select', {
      onchange: (event) => { view.country = event.target.value; refresh(); },
    }, [blankOption(t('country')), ...COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) }))]
      .map((option) => {
        const node = el('option', { value: option.value, text: option.label });
        if (option.value === view.country) node.selected = true;
        return node;
      })),
    canSeeAll() ? el('select', {
      onchange: (event) => { view.owner = event.target.value; refresh(); },
    }, [blankOption(t('owner')), ...state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') }))]
      .map((option) => {
        const node = el('option', { value: option.value, text: option.label });
        if (String(option.value) === String(view.owner)) node.selected = true;
        return node;
      })) : null,
    el('div.segmented', {}, [
      el('button', {
        type: 'button', class: view.mode === 'board' ? 'active' : '', text: t('board_view'),
        onclick: (e) => setMode('board', e.currentTarget),
      }),
      el('button', {
        type: 'button', class: view.mode === 'list' ? 'active' : '', text: t('list_view'),
        onclick: (e) => setMode('list', e.currentTarget),
      }),
    ]),
    el('div.spacer'),
    canEdit() ? el('button.btn', {
      type: 'button', onclick: () => openOpportunityForm(null, refresh),
    }, [icon('plus', 16), t('new_opportunity')]) : null,
  ]));

  function setMode(mode, button) {
    view.mode = mode;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    refresh();
  }

  page.append(host);

  async function refresh() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { opportunities } = await api.opportunities({
        q: view.q, country: view.country, owner_id: view.owner,
        scope: canSeeAll() ? 'all' : undefined,
      });
      clear(host).append(view.mode === 'board'
        ? board(opportunities, refresh, navigate)
        : el('div.card', {}, [el('div.card-body.flush', {}, [list(opportunities, refresh, navigate)])]));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await refresh();
  return page;
}

// ------------------------------------------------------------- kanban board
function board(opportunities, refresh, navigate) {
  const wrap = el('div.board');

  for (const stage of STAGES) {
    const items = opportunities.filter((o) => o.stage === stage);
    const sum = items.reduce((total, o) => total + Number(o.expected_value || 0), 0);

    const bodyHost = el('div.board-col-body');
    const column = el('div.board-col', { dataset: { stage } }, [
      el('div.board-col-head', {}, [
        el('span.title', { text: t(`stage_${stage}`) }),
        el('span.count', { text: String(items.length) }),
        el('span.sum', { text: sum ? moneyShort(sum) : '' }),
      ]),
      bodyHost,
    ]);

    for (const item of items) bodyHost.append(card(item, refresh, navigate));

    // Drag and drop between stages.
    column.addEventListener('dragover', (event) => {
      if (!canEdit()) return;
      event.preventDefault();
      column.classList.add('drag-over');
    });
    column.addEventListener('dragleave', () => column.classList.remove('drag-over'));
    column.addEventListener('drop', async (event) => {
      event.preventDefault();
      column.classList.remove('drag-over');
      if (!canEdit()) return;
      const id = Number(event.dataTransfer.getData('text/plain'));
      const moved = opportunities.find((o) => o.id === id);
      if (!moved || moved.stage === stage) return;

      // Losing a deal needs a reason, so ask before moving.
      if (stage === 'lost') return askLossReason(moved, refresh);
      try {
        await api.updateOpportunity(id, { stage });
        toast(t('saved'), 'success');
        refresh();
      } catch (error) { toastError(error); }
    });

    wrap.append(column);
  }
  return wrap;
}

function card(item, refresh, navigate) {
  const node = el('div.deal', { draggable: canEdit() ? 'true' : 'false' }, [
    el('div.title', { text: pick(item, 'title') }),
    el('div.customer', { text: pick(item, 'customer_name') }),
    el('div.row', {}, [
      el('span.value.num', { text: `${moneyShort(item.expected_value)} ${item.currency}` }),
      el('span.spacer'),
      item.area_sqm ? el('span', { text: `${money(item.area_sqm, 0)} m²` }) : null,
    ]),
    el('div.row', { style: { marginTop: '.25rem' } }, [
      el('span.badge.grey', { text: t(`country_${item.country}`) }),
      item.quotation_count > 0 ? el('span.badge.blue', { text: `${item.quotation_count} ${t('quotations')}` }) : null,
      el('span.spacer'),
      el('span.tiny', { text: `${item.probability}%` }),
    ]),
  ]);

  node.addEventListener('dragstart', (event) => {
    event.dataTransfer.setData('text/plain', String(item.id));
    node.classList.add('dragging');
  });
  node.addEventListener('dragend', () => node.classList.remove('dragging'));
  node.addEventListener('click', () => openOpportunityDetail(item.id, refresh, navigate));
  return node;
}

function list(opportunities, refresh, navigate) {
  return dataTable({
    rows: opportunities,
    onRowClick: (row) => openOpportunityDetail(row.id, refresh, navigate),
    columns: [
      {
        label: t('opportunity_title'),
        render: (row) => el('div', {}, [
          el('div.bold', { text: pick(row, 'title') }),
          el('div.tiny.muted', { text: `${row.code || ''} · ${pick(row, 'customer_name')}` }),
        ]),
      },
      { label: t('stage'), render: (row) => stageBadge(row.stage) },
      { label: t('country'), render: (row) => t(`country_${row.country}`) },
      { label: t('area_sqm'), className: 'num', render: (row) => money(row.area_sqm, 0) },
      {
        label: t('expected_value'), className: 'num',
        render: (row) => `${money(row.expected_value, 0)} ${row.currency}`,
      },
      { label: t('probability'), className: 'num', render: (row) => `${row.probability}%` },
      { label: t('expected_close'), render: (row) => formatDate(row.expected_close) },
      { label: t('owner'), render: (row) => pick(row, 'owner_name') || '—' },
    ],
  });
}

// ------------------------------------------------------------------ detail
async function openOpportunityDetail(id, onChange, navigate) {
  let data;
  try { data = await api.opportunity(id); } catch (error) { return toastError(error); }
  const { opportunity, quotations, activities } = data;

  const item = (key, value) => el('div.detail-item', {}, [
    el('div.k', { text: key }), el('div.v', { text: value ?? '—' }),
  ]);

  const body = el('div', {}, [
    el('div.row.wrap.mb-2', {}, [
      stageBadge(opportunity.stage),
      el('span.badge.grey', { text: t(`country_${opportunity.country}`) }),
      opportunity.project_type ? el('span.badge.blue', { text: t(`ptype_${opportunity.project_type}`) }) : null,
      el('span.badge.grey', { text: `${opportunity.probability}%` }),
    ]),
    el('div.detail-grid', {}, [
      item(t('customer'), pick(opportunity, 'customer_name')),
      item(t('city'), opportunity.city),
      item(t('area_sqm'), money(opportunity.area_sqm, 0)),
      item(t('expected_value'), `${money(opportunity.expected_value, 0)} ${opportunity.currency}`),
      item(t('expected_close'), formatDate(opportunity.expected_close)),
      item(t('owner'), pick(opportunity, 'owner_name')),
      item(t('source'), opportunity.source ? t(`source_${opportunity.source}`) : null),
      opportunity.stage === 'lost' ? item(t('lost_reason'), opportunity.lost_reason ? t(`reason_${opportunity.lost_reason}`) : null) : null,
      opportunity.stage === 'lost' ? item(t('lost_to'), opportunity.lost_to) : null,
    ]),
    opportunity.notes ? el('div.mt-2', {}, [
      el('div.k.tiny.bold.muted', { text: t('notes') }),
      el('p', { text: opportunity.notes }),
    ]) : null,

    el('h4.mt-2', { text: `${t('quotations')} (${quotations.length})` }),
    dataTable({
      rows: quotations,
      onRowClick: (row) => { close(); navigate(`quote/${row.id}`); },
      columns: [
        { label: t('quote_number'), className: 'num', render: (row) => `${row.number}${row.revision ? ` R${row.revision}` : ''}` },
        { label: t('issue_date'), render: (row) => formatDate(row.issue_date) },
        { label: t('status'), render: (row) => t(`qstatus_${row.status}`) },
        { label: t('grand_total'), className: 'num', render: (row) => `${money(row.total)} ${row.currency}` },
      ],
    }),

    el('h4.mt-2', { text: `${t('activities')} (${activities.length})` }),
    dataTable({
      rows: activities,
      columns: [
        { label: t('activity_type'), render: (row) => t(`act_${row.type}`) },
        { label: t('subject'), render: (row) => row.subject },
        { label: t('due_at'), render: (row) => formatDate(row.due_at) },
        { label: t('status'), render: (row) => row.done ? t('done') : t('upcoming') },
      ],
    }),
  ]);

  const { close } = openModal({
    title: pick(opportunity, 'title'),
    size: 'wide',
    body,
    footer: (dismiss) => el('div.row', { style: { width: '100%' } }, [
      canSeeAll() ? el('button.btn.btn-danger.btn-sm', {
        type: 'button', text: t('delete'),
        onclick: async () => {
          if (!await confirmDialog(t('confirm_delete'))) return;
          try {
            await api.deleteOpportunity(opportunity.id);
            toast(t('deleted'), 'success');
            dismiss();
            onChange?.();
          } catch (error) { toastError(error); }
        },
      }) : null,
      el('div.spacer'),
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: dismiss }),
      canEdit() ? el('button.btn.btn-secondary', {
        type: 'button', text: t('new_quotation'),
        onclick: () => {
          dismiss();
          navigate(`quote/new?opportunity=${opportunity.id}`);
        },
      }) : null,
      canEdit() ? el('button.btn', {
        type: 'button', text: t('edit'),
        onclick: () => { dismiss(); openOpportunityForm(opportunity, onChange); },
      }) : null,
    ]),
  });
}

// -------------------------------------------------------------------- forms
export function openOpportunityForm(opportunity, onSaved, presetCustomerId) {
  const isEdit = Boolean(opportunity);
  const form = el('form', { onsubmit: (event) => event.preventDefault() });
  const customerSelect = el('select', { name: 'customer_id', required: true });

  const build = (customers) => {
    for (const customer of customers) {
      const node = el('option', { value: customer.id, label: pick(customer, 'name') });
      node.textContent = pick(customer, 'name');
      if (String(customer.id) === String(opportunity?.customer_id ?? presetCustomerId ?? '')) node.selected = true;
      customerSelect.append(node);
    }
  };

  const countrySelect = field({
    name: 'country', label: t('country'), type: 'select',
    value: opportunity?.country || 'SA',
    options: COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })),
  });

  form.append(
    el('div.field', {}, [el('label', { text: `${t('customer')} *` }), customerSelect]),
    el('div.grid.grid-2', {}, [
      field({ name: 'title', label: t('opportunity_title'), value: opportunity?.title || '', required: true }),
      field({ name: 'title_ar', label: `${t('opportunity_title')} (AR)`, value: opportunity?.title_ar || '', dir: 'rtl' }),
      countrySelect,
      field({ name: 'city', label: t('city'), value: opportunity?.city || '' }),
      field({ name: 'project_type', label: t('project_type'), type: 'select', value: opportunity?.project_type || '', options: [blankOption(t('none')), ...optionsFrom(PROJECT_TYPES, 'ptype_')] }),
      field({ name: 'stage', label: t('stage'), type: 'select', value: opportunity?.stage || 'new', options: optionsFrom(STAGES, 'stage_') }),
      field({ name: 'area_sqm', label: t('area_sqm'), type: 'number', value: opportunity?.area_sqm ?? '', min: 0, step: 1 }),
      field({ name: 'expected_value', label: t('expected_value'), type: 'number', value: opportunity?.expected_value ?? '', min: 0, step: 1 }),
      field({ name: 'currency', label: t('currency'), type: 'select', value: opportunity?.currency || 'SAR', options: ['SAR', 'EGP', 'QAR', 'USD'].map((c) => ({ value: c, label: c })) }),
      field({ name: 'probability', label: t('probability'), type: 'number', value: opportunity?.probability ?? 10, min: 0, max: 100, step: 5 }),
      field({ name: 'expected_close', label: t('expected_close'), type: 'date', value: opportunity?.expected_close || '' }),
      field({ name: 'source', label: t('source'), type: 'select', value: opportunity?.source || '', options: [blankOption(t('none')), ...optionsFrom(SOURCES, 'source_')] }),
      canSeeAll() ? field({
        name: 'owner_id', label: t('owner'), type: 'select',
        value: opportunity?.owner_id || state.user.id,
        options: state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') })),
      }) : null,
    ]),
    field({ name: 'notes', label: t('notes'), type: 'textarea', value: opportunity?.notes || '', rows: 3 }),
  );

  // Selecting a country pre-fills the matching currency.
  countrySelect.querySelector('select').addEventListener('change', (event) => {
    const currency = form.querySelector('[name="currency"]');
    if (currency) currency.value = CURRENCY_BY_COUNTRY[event.target.value] || 'SAR';
  });

  openModal({
    title: isEdit ? `${t('edit')} — ${pick(opportunity, 'title')}` : t('new_opportunity'),
    size: 'wide',
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            const data = readForm(form);
            if (isEdit) await api.updateOpportunity(opportunity.id, data);
            else await api.createOpportunity(data);
            toast(t('saved'), 'success');
            close();
            onSaved?.();
          } catch (error) {
            toastError(error);
            button.disabled = false;
          }
        },
      }),
    ]),
  });

  api.customers({ limit: 500, scope: 'all' })
    .then(({ customers }) => build(customers))
    .catch(toastError);
}

function askLossReason(opportunity, refresh) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    field({
      name: 'lost_reason', label: t('lost_reason'), type: 'select',
      options: optionsFrom(LOST_REASONS, 'reason_'), required: true,
    }),
    field({ name: 'lost_to', label: t('lost_to') }),
  ]);

  openModal({
    title: `${t('stage_lost')} — ${pick(opportunity, 'title')}`,
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn.btn-danger', {
        type: 'button', text: t('save'),
        onclick: async () => {
          try {
            await api.updateOpportunity(opportunity.id, { stage: 'lost', ...readForm(form) });
            toast(t('saved'), 'success');
            close();
            refresh();
          } catch (error) { toastError(error); }
        },
      }),
    ]),
  });
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
