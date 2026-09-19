import { api } from '../api.js';
import { t, pick, money, formatDate } from '../i18n.js';
import {
  el, clear, icon, dataTable, openModal, field, readForm,
  toast, toastError, quoteStatusBadge, blankOption, optionsFrom,
} from '../ui.js';
import { can, canSeeAll, canSeeCost, state } from '../app.js';

const STATUSES = ['draft', 'sent', 'under_review', 'approved', 'rejected', 'expired', 'cancelled'];
const COUNTRIES = ['SA', 'EG', 'QA'];
const filters = { q: '', status: '', country: '', from: '', to: '' };

export async function render({ navigate }) {
  const page = el('div');
  const host = el('div');

  const select = (key, options, label) => el('select', {
    onchange: (event) => { filters[key] = event.target.value; refresh(); },
  }, [blankOption(label), ...options].map((option) => {
    const node = el('option', { value: option.value, text: option.label });
    if (option.value === filters[key]) node.selected = true;
    return node;
  }));

  page.append(el('div.toolbar', {}, [
    el('div.search-box', {}, [icon('search', 15), el('input', {
      type: 'search', placeholder: t('search'), value: filters.q,
      oninput: debounce((event) => { filters.q = event.target.value; refresh(); }, 280),
    })]),
    select('status', optionsFrom(STATUSES, 'qstatus_'), t('status')),
    select('country', COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })), t('country')),
    el('input', {
      type: 'date', title: t('from'), value: filters.from, style: { width: 'auto' },
      onchange: (event) => { filters.from = event.target.value; refresh(); },
    }),
    el('input', {
      type: 'date', title: t('to'), value: filters.to, style: { width: 'auto' },
      onchange: (event) => { filters.to = event.target.value; refresh(); },
    }),
    el('div.spacer'),
    canSeeAll() ? el('button.btn.btn-secondary.btn-sm', {
      type: 'button', text: t('qstatus_expired'),
      title: 'Mark past-validity quotations as expired',
      onclick: async () => {
        try {
          const { expired } = await api.post('/api/quotations/expire-stale');
          toast(`${expired}`, 'success');
          refresh();
        } catch (error) { toastError(error); }
      },
    }) : null,
    can('quotations.create') ? el('button.btn', {
      type: 'button', onclick: () => openNewQuotation(navigate),
    }, [icon('plus', 16), t('new_quotation')]) : null,
  ]));

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [host])]));

  async function refresh() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { quotations } = await api.quotations({ ...filters, scope: canSeeAll() ? 'all' : undefined });
      const totalsByCurrency = quotations.reduce((acc, row) => {
        acc[row.currency] = (acc[row.currency] || 0) + Number(row.total || 0);
        return acc;
      }, {});

      clear(host).append(dataTable({
        rows: quotations,
        onRowClick: (row) => navigate(`quote/${row.id}`),
        columns: [
          {
            label: t('quote_number'),
            render: (row) => el('div', {}, [
              el('div.bold.num', { text: row.number }),
              row.revision > 0
                ? el('span.badge.grey', { text: `${t('revision')} ${row.revision}` })
                : null,
            ]),
          },
          {
            label: t('project_name'),
            render: (row) => el('div', {}, [
              el('div', { text: pick(row, 'project_name') }),
              el('div.tiny.muted', { text: pick(row, 'customer_name') }),
            ]),
          },
          { label: t('country'), render: (row) => t(`country_${row.country}`) },
          { label: t('issue_date'), render: (row) => formatDate(row.issue_date) },
          { label: t('status'), render: (row) => quoteStatusBadge(row.status) },
          {
            label: t('net_amount'), className: 'num',
            render: (row) => `${money(row.net_amount)} ${row.currency}`,
          },
          {
            label: t('grand_total'), className: 'num',
            render: (row) => el('span.bold', { text: `${money(row.total)} ${row.currency}` }),
          },
          canSeeCost() ? {
            label: t('margin'), className: 'num',
            render: (row) => {
              const value = Number(row.margin_pct || 0);
              if (!value) return el('span.muted', { text: '—' });
              return el('span.badge', {
                class: value < 0 ? 'red' : value < 10 ? 'amber' : 'green',
                text: `${value.toFixed(1)}%`,
              });
            },
          } : null,
          { label: t('owner'), render: (row) => pick(row, 'owner_name') || '—' },
        ].filter(Boolean),
        footer: quotations.length ? el('tr', {}, [
          el('td', { colspan: 5, text: `${quotations.length}` }),
          el('td', { colspan: 4, class: 'num', text: Object.entries(totalsByCurrency).map(([currency, sum]) => `${money(sum, 0)} ${currency}`).join('  ·  ') }),
        ]) : null,
      }));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await refresh();
  return page;
}

/** Step 1 of creating an offer: pick the customer / opportunity and the basics. */
export function openNewQuotation(navigate, presetOpportunityId) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() });
  const customerSelect = el('select', { name: 'customer_id', required: true });
  const opportunitySelect = el('select', { name: 'opportunity_id' });
  let opportunities = [];

  form.append(
    el('div.field', {}, [el('label', { text: `${t('customer')} *` }), customerSelect]),
    el('div.field', {}, [el('label', { text: t('opportunity') }), opportunitySelect]),
    el('div.grid.grid-2', {}, [
      field({ name: 'project_name', label: t('project_name'), required: true, dir: 'ltr' }),
      field({ name: 'project_name_ar', label: t('project_name_ar'), dir: 'rtl' }),
      field({ name: 'country', label: t('country'), type: 'select', value: 'SA', options: COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })) }),
      field({ name: 'location', label: t('location') }),
      field({ name: 'attention', label: t('attention'), dir: 'ltr' }),
      field({ name: 'attention_ar', label: t('attention_ar'), dir: 'rtl' }),
      field({ name: 'area_sqm', label: t('area_sqm'), type: 'number', min: 0, step: 1, required: true }),
      field({ name: 'unit_price', label: t('unit_price'), type: 'number', min: 0, step: 0.01, hint: t('default_price') }),
    ]),
  );

  // Choosing an opportunity fills in the project name, area and country.
  opportunitySelect.addEventListener('change', () => {
    const chosen = opportunities.find((o) => String(o.id) === opportunitySelect.value);
    if (!chosen) return;
    form.querySelector('[name="project_name"]').value = chosen.title || '';
    form.querySelector('[name="project_name_ar"]').value = chosen.title_ar || '';
    form.querySelector('[name="country"]').value = chosen.country || 'SA';
    form.querySelector('[name="location"]').value = chosen.city || '';
    if (chosen.area_sqm) form.querySelector('[name="area_sqm"]').value = chosen.area_sqm;
    customerSelect.value = String(chosen.customer_id);
    applyCountryPrice();
  });

  const countryInput = form.querySelector('[name="country"]');
  countryInput.addEventListener('change', applyCountryPrice);

  function applyCountryPrice() {
    const book = state.settings?.countries?.[countryInput.value];
    const priceInput = form.querySelector('[name="unit_price"]');
    if (book && !priceInput.dataset.touched) priceInput.value = book.default_price_sqm ?? '';
  }
  form.querySelector('[name="unit_price"]').addEventListener('input', (event) => {
    event.target.dataset.touched = '1';
  });

  openModal({
    title: t('new_quotation'),
    size: 'wide',
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('create'),
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          try {
            const data = readForm(form);
            const { quotation } = await api.createQuotation(data);
            toast(t('saved'), 'success');
            close();
            navigate(`quote/${quotation.id}`);
          } catch (error) {
            toastError(error);
            button.disabled = false;
          }
        },
      }),
    ]),
  });

  customerSelect.append(el('option', { value: '', text: '—' }));
  api.customers({ limit: 500, scope: 'all' }).then(({ customers }) => {
    for (const customer of customers) {
      const node = el('option', { value: customer.id });
      node.textContent = pick(customer, 'name');
      customerSelect.append(node);
    }
  }).catch(() => {});

  opportunitySelect.append(el('option', { value: '', text: `— ${t('none')} —` }));
  api.opportunities({ open: 1, scope: 'all' }).then((result) => {
    opportunities = result.opportunities;
    for (const opportunity of opportunities) {
      const node = el('option', { value: opportunity.id });
      node.textContent = `${pick(opportunity, 'title')} — ${pick(opportunity, 'customer_name')}`;
      if (String(opportunity.id) === String(presetOpportunityId)) node.selected = true;
      opportunitySelect.append(node);
    }
    if (presetOpportunityId) opportunitySelect.dispatchEvent(new Event('change'));
    else applyCountryPrice();
  }).catch(() => {});
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
