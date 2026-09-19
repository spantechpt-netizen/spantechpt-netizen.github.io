import { api } from '../api.js';
import { t, pick, money, formatDate, formatDateTime, relativeDays } from '../i18n.js';
import {
  el, clear, icon, dataTable, field, readForm, openModal, confirmDialog,
  toast, toastError, customerStatusBadge, stars, optionsFrom, blankOption,
  stageBadge, quoteStatusBadge,
} from '../ui.js';
import { can, canSeeAll, state } from '../app.js';

const TYPES = ['main_contractor', 'consultant', 'developer', 'owner', 'subcontractor', 'government', 'other'];
const STATUSES = ['target', 'prospect', 'active', 'dormant', 'blacklisted'];
const SECTORS = ['residential', 'commercial', 'education', 'healthcare', 'industrial', 'infrastructure', 'mixed'];
const SOURCES = ['referral', 'website', 'exhibition', 'cold_call', 'existing', 'tender', 'social'];
const COUNTRIES = ['SA', 'EG', 'QA'];

const filters = { q: '', country: '', status: '', type: '', scope: 'all' };

export async function render({ navigate }) {
  const page = el('div');
  const listHost = el('div');

  const search = el('input', {
    type: 'search', placeholder: t('search'), value: filters.q,
    oninput: debounce((event) => { filters.q = event.target.value; refresh(); }, 280),
  });

  const select = (key, options, label) => el('select', {
    onchange: (event) => { filters[key] = event.target.value; refresh(); },
  }, [blankOption(label), ...options].map((option) => {
    const node = el('option', { value: option.value, text: option.label });
    if (option.value === filters[key]) node.selected = true;
    return node;
  }));

  page.append(el('div.toolbar', {}, [
    el('div.search-box', {}, [icon('search', 15), search]),
    select('country', COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })), t('country')),
    select('status', optionsFrom(STATUSES, 'status_'), t('status')),
    select('type', optionsFrom(TYPES, 'type_'), t('customer_type')),
    canSeeAll() ? el('div.segmented', {}, [
      el('button', {
        type: 'button', class: filters.scope === 'all' ? 'active' : '', text: t('all_customers'),
        onclick: (e) => setScope('all', e.currentTarget),
      }),
      el('button', {
        type: 'button', class: filters.scope === 'mine' ? 'active' : '', text: t('my_customers'),
        onclick: (e) => setScope('mine', e.currentTarget),
      }),
    ]) : null,
    el('div.spacer'),
    can('customers.create') ? el('button.btn', {
      type: 'button', onclick: () => openCustomerForm(null, refresh),
    }, [icon('plus', 16), t('new_customer')]) : null,
  ]));

  function setScope(scope, button) {
    filters.scope = scope;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    refresh();
  }

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [listHost])]));

  async function refresh() {
    clear(listHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const params = { ...filters };
      if (params.scope === 'mine') { params.owner_id = state.user.id; }
      delete params.scope;
      if (canSeeAll()) params.scope = 'all';
      const { customers, total } = await api.customers(params);

      clear(listHost).append(dataTable({
        rows: customers,
        onRowClick: (row) => openCustomerDetail(row.id, refresh, navigate),
        columns: [
          {
            label: t('customer'),
            render: (row) => el('div', {}, [
              el('div.bold', { text: pick(row, 'name') }),
              el('div.tiny.muted', { text: [row.code, t(`type_${row.type}`)].filter(Boolean).join(' · ') }),
            ]),
          },
          {
            label: t('country'),
            render: (row) => el('div', {}, [
              el('div', { text: t(`country_${row.country}`) }),
              row.city ? el('div.tiny.muted', { text: row.city }) : null,
            ]),
          },
          { label: t('status'), render: (row) => customerStatusBadge(row.status) },
          { label: t('rating'), render: (row) => stars(row.rating) },
          { label: t('owner'), render: (row) => pick(row, 'owner_name') || '—' },
          { label: t('opportunities_count'), className: 'num', render: (row) => row.opportunity_count },
          { label: t('quotations_count'), className: 'num', render: (row) => row.quotation_count },
          {
            label: t('due_at'),
            render: (row) => {
              if (!row.next_activity) return el('span.muted', { text: '—' });
              const { days, label } = relativeDays(row.next_activity);
              return el('span', {
                class: days < 0 ? 'badge red' : days === 0 ? 'badge amber' : 'badge grey',
                text: label,
              });
            },
          },
        ],
      }));

      if (total > customers.length) {
        listHost.append(el('div.center.muted.small', {
          style: { padding: '.6rem' },
          text: `${customers.length} / ${total}`,
        }));
      }
    } catch (error) {
      clear(listHost).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await refresh();
  return page;
}

// ------------------------------------------------------------------ detail
export async function openCustomerDetail(id, onChange, navigate) {
  let data;
  try { data = await api.customer(id); } catch (error) { return toastError(error); }
  const { customer, contacts, opportunities, quotations, activities } = data;

  const body = el('div');
  const tabs = el('div.tabs');
  const panel = el('div');

  const TABS = [
    { key: 'info', label: t('customer'), build: () => infoPanel(customer) },
    { key: 'contacts', label: `${t('contacts')} (${contacts.length})`, build: () => contactsPanel(customer, contacts, reload) },
    { key: 'opportunities', label: `${t('pipeline')} (${opportunities.length})`, build: () => opportunitiesPanel(opportunities) },
    { key: 'quotations', label: `${t('quotations')} (${quotations.length})`, build: () => quotationsPanel(quotations, navigate, close) },
    { key: 'activities', label: `${t('activities')} (${activities.length})`, build: () => activitiesPanel(activities) },
    can('mail.view') ? {
      key: 'mail', label: `${t('customer_mail')} (${data.mail_count || 0})`, build: () => mailPanel(customer),
    } : null,
  ].filter(Boolean);

  let active = 'info';
  const drawTabs = () => {
    clear(tabs);
    for (const tab of TABS) {
      tabs.append(el('button', {
        type: 'button', class: tab.key === active ? 'active' : '', text: tab.label,
        onclick: () => { active = tab.key; drawTabs(); clear(panel).append(tab.build()); },
      }));
    }
  };
  drawTabs();
  panel.append(TABS[0].build());
  body.append(tabs, panel);

  const { close } = openModal({
    title: pick(customer, 'name'),
    size: 'wide',
    body,
    footer: (dismiss) => el('div.row', { style: { width: '100%' } }, [
      canSeeAll() ? el('button.btn.btn-danger.btn-sm', {
        type: 'button', text: t('delete'),
        onclick: async () => {
          if (!await confirmDialog(t('confirm_delete'))) return;
          try {
            await api.deleteCustomer(customer.id);
            toast(t('deleted'), 'success');
            dismiss();
            onChange?.();
          } catch (error) { toastError(error); }
        },
      }) : null,
      el('div.spacer'),
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: dismiss }),
      can('customers.edit') ? el('button.btn', {
        type: 'button', text: t('edit'),
        onclick: () => { dismiss(); openCustomerForm(customer, onChange); },
      }) : null,
    ]),
  });

  function reload() { close(); openCustomerDetail(id, onChange, navigate); }
}

function infoPanel(customer) {
  const item = (key, value) => el('div.detail-item', {}, [
    el('div.k', { text: key }),
    el('div.v', { text: value || '—' }),
  ]);
  return el('div', {}, [
    el('div.row.wrap.mb-2', {}, [
      customerStatusBadge(customer.status),
      el('span.badge.blue', { text: t(`type_${customer.type}`) }),
      el('span.badge.grey', { text: t(`country_${customer.country}`) }),
      stars(customer.rating),
    ]),
    el('div.detail-grid', {}, [
      item(t('customer_name_en'), customer.name_en),
      item(t('customer_name_ar'), customer.name_ar),
      item(t('city'), customer.city),
      item(t('sector'), customer.sector ? t(`sector_${customer.sector}`) : null),
      item(t('source'), customer.source ? t(`source_${customer.source}`) : null),
      item(t('owner'), pick(customer, 'owner_name')),
      item(t('phone'), customer.phone),
      item(t('email'), customer.email),
      item(t('website'), customer.website),
      item(t('cr_number'), customer.cr_number),
      item(t('tax_number'), customer.tax_number),
      item(t('address'), customer.address),
    ]),
    customer.notes ? el('div.mt-2', {}, [
      el('div.k.tiny.bold.muted', { text: t('notes') }),
      el('p', { text: customer.notes }),
    ]) : null,
  ]);
}

function contactsPanel(customer, contacts, reload) {
  const host = el('div');
  host.append(el('div.row.mb-1', {}, [
    el('div.spacer'),
    can('customers.edit') ? el('button.btn.btn-sm', {
      type: 'button', text: t('new_contact'),
      onclick: () => openContactForm(customer.id, null, reload),
    }, [icon('plus', 14)]) : null,
  ]));

  host.append(dataTable({
    rows: contacts,
    empty: t('no_data'),
    columns: [
      {
        label: t('contact_name'),
        render: (row) => el('div', {}, [
          el('div.bold', {}, [
            pick(row, 'name'),
            row.is_primary ? el('span.badge.green', { style: { marginInlineStart: '.35rem' }, text: t('primary_contact') }) : null,
          ]),
          row.title ? el('div.tiny.muted', { text: row.title }) : null,
        ]),
      },
      {
        label: t('mobile'),
        render: (row) => row.mobile
          ? el('a.num', { href: `tel:${row.mobile}`, text: row.mobile, dir: 'ltr' })
          : '—',
      },
      {
        label: t('email'),
        render: (row) => row.email ? el('a', { href: `mailto:${row.email}`, text: row.email }) : '—',
      },
      {
        label: '', className: 'end',
        render: (row) => can('customers.edit') ? el('div.row', {}, [
          el('button.btn.btn-sm.btn-secondary', {
            type: 'button', text: t('edit'),
            onclick: () => openContactForm(customer.id, row, reload),
          }),
          el('button.btn.btn-sm.btn-danger', {
            type: 'button', title: t('delete'),
            onclick: async () => {
              if (!await confirmDialog(t('confirm_delete'))) return;
              try { await api.deleteContact(row.id); reload(); } catch (error) { toastError(error); }
            },
          }, [icon('trash', 13)]),
        ]) : null,
      },
    ],
  }));
  return host;
}

/**
 * The customer's correspondence. Loaded when the tab opens, not with the
 * customer, because most visits never come here and the list can be long.
 */
function mailPanel(customer) {
  const host = el('div');
  host.append(el('p.hint', { text: t('customer_mail_hint') }));
  const list = el('div.loading-page', { text: t('loading') });
  host.append(list);

  api.customerMail(customer.id).then(({ messages }) => {
    clear(list).classList.remove('loading-page');
    if (!messages.length) {
      list.append(el('div.empty', {}, [icon('mail', 36), el('div', { text: t('customer_mail_none') })]));
      return;
    }
    for (const message of messages) list.append(mailRow(customer, message));
  }).catch((error) => {
    clear(list).append(el('div.alert.danger', { text: error.localised || error.message }));
  });
  return host;
}

function mailRow(customer, message) {
  const body = el('pre.mail-body', { style: { display: 'none' } });
  let loaded = false;
  const toggle = el('button.btn.btn-sm.btn-ghost', {
    type: 'button', text: t('mail_show_body'),
    onclick: async () => {
      const open = body.style.display !== 'none';
      if (open) { body.style.display = 'none'; toggle.textContent = t('mail_show_body'); return; }
      if (!loaded) {
        try {
          const { message: full } = await api.customerMailMessage(customer.id, message.id);
          body.textContent = full.body_text || full.snippet || '';
          loaded = true;
        } catch (error) { return toastError(error); }
      }
      body.style.display = '';
      toggle.textContent = t('mail_hide_body');
    },
  });
  const sender = message.from_name || message.from_email || message.from_phone || '—';
  const address = message.from_email && message.from_name ? ` <${message.from_email}>` : '';
  return el('div.mail-row', {}, [
    el('div.row.wrap', {}, [
      el('b', { text: message.subject || '—' }),
      message.request_id ? el('span.badge.blue', { text: t('mail_in_requests') }) : null,
      message.has_attachments ? el('span.badge.grey', { text: t('mail_attachments') }) : null,
      el('div.spacer'),
      el('span.tiny.muted', { text: formatDateTime(message.received_at) }),
    ]),
    el('div.tiny.muted', { text: `${sender}${address} · ${message.account_label || message.channel || ''}` }),
    message.snippet ? el('div.small', { text: message.snippet }) : null,
    toggle,
    body,
  ]);
}

function opportunitiesPanel(opportunities) {
  return dataTable({
    rows: opportunities,
    columns: [
      { label: t('opportunity_title'), render: (row) => pick(row, 'title') },
      { label: t('stage'), render: (row) => stageBadge(row.stage) },
      { label: t('area_sqm'), className: 'num', render: (row) => money(row.area_sqm, 0) },
      { label: t('expected_value'), className: 'num', render: (row) => `${money(row.expected_value, 0)} ${row.currency}` },
      { label: t('expected_close'), render: (row) => formatDate(row.expected_close) },
    ],
  });
}

function quotationsPanel(quotations, navigate, close) {
  return dataTable({
    rows: quotations,
    onRowClick: (row) => { close?.(); navigate?.(`quote/${row.id}`); },
    columns: [
      { label: t('quote_number'), className: 'num', render: (row) => row.number },
      { label: t('revision'), className: 'num', render: (row) => row.revision },
      { label: t('project_name'), render: (row) => row.project_name },
      { label: t('issue_date'), render: (row) => formatDate(row.issue_date) },
      { label: t('status'), render: (row) => quoteStatusBadge(row.status) },
      { label: t('grand_total'), className: 'num', render: (row) => `${money(row.total)} ${row.currency}` },
    ],
  });
}

function activitiesPanel(activities) {
  return dataTable({
    rows: activities,
    columns: [
      { label: t('activity_type'), render: (row) => el('span.badge.grey', { text: t(`act_${row.type}`) }) },
      { label: t('subject'), render: (row) => row.subject },
      { label: t('due_at'), render: (row) => formatDate(row.due_at) },
      {
        label: t('status'),
        render: (row) => row.done
          ? el('span.badge.green', { text: t('done') })
          : el('span.badge.amber', { text: t('upcoming') }),
      },
      { label: t('owner'), render: (row) => row.owner_name || '—' },
    ],
  });
}

// -------------------------------------------------------------------- forms
export function openCustomerForm(customer, onSaved) {
  const isEdit = Boolean(customer);
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'name_en', label: t('customer_name_en'), value: customer?.name_en || '', required: true, dir: 'ltr' }),
      field({ name: 'name_ar', label: t('customer_name_ar'), value: customer?.name_ar || '', dir: 'rtl' }),
      field({ name: 'type', label: t('customer_type'), type: 'select', value: customer?.type || 'main_contractor', options: optionsFrom(TYPES, 'type_') }),
      field({ name: 'status', label: t('status'), type: 'select', value: customer?.status || 'target', options: optionsFrom(STATUSES, 'status_') }),
      field({ name: 'country', label: t('country'), type: 'select', value: customer?.country || 'SA', options: COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })) }),
      field({ name: 'city', label: t('city'), value: customer?.city || '' }),
      field({ name: 'sector', label: t('sector'), type: 'select', value: customer?.sector || '', options: [blankOption(t('none')), ...optionsFrom(SECTORS, 'sector_')] }),
      field({ name: 'source', label: t('source'), type: 'select', value: customer?.source || '', options: [blankOption(t('none')), ...optionsFrom(SOURCES, 'source_')] }),
      field({ name: 'rating', label: t('rating'), type: 'select', value: customer?.rating ?? 3, options: [5, 4, 3, 2, 1].map((n) => ({ value: n, label: '★'.repeat(n) })) }),
      canSeeAll() ? field({
        name: 'owner_id', label: t('owner'), type: 'select',
        value: customer?.owner_id || state.user.id,
        options: state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') })),
      }) : null,
      field({ name: 'phone', label: t('phone'), type: 'tel', value: customer?.phone || '', dir: 'ltr' }),
      field({ name: 'email', label: t('email'), type: 'email', value: customer?.email || '', dir: 'ltr' }),
      field({ name: 'cr_number', label: t('cr_number'), value: customer?.cr_number || '', dir: 'ltr' }),
      field({ name: 'tax_number', label: t('tax_number'), value: customer?.tax_number || '', dir: 'ltr' }),
    ]),
    field({ name: 'website', label: t('website'), type: 'url', value: customer?.website || '', dir: 'ltr' }),
    field({ name: 'address', label: t('address'), type: 'textarea', value: customer?.address || '', rows: 2 }),
    field({ name: 'notes', label: t('notes'), type: 'textarea', value: customer?.notes || '', rows: 3 }),
  ]);

  openModal({
    title: isEdit ? `${t('edit')} — ${pick(customer, 'name')}` : t('new_customer'),
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
            if (isEdit) await api.updateCustomer(customer.id, data);
            else await api.createCustomer(data);
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
}

function openContactForm(customerId, contact, onSaved) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'name', label: t('contact_name'), value: contact?.name || '', required: true }),
      field({ name: 'name_ar', label: `${t('contact_name')} (AR)`, value: contact?.name_ar || '', dir: 'rtl' }),
      field({ name: 'title', label: t('contact_title'), value: contact?.title || '' }),
      field({ name: 'mobile', label: t('mobile'), type: 'tel', value: contact?.mobile || '', dir: 'ltr' }),
      field({ name: 'phone', label: t('phone'), type: 'tel', value: contact?.phone || '', dir: 'ltr' }),
      field({ name: 'email', label: t('email'), type: 'email', value: contact?.email || '', dir: 'ltr' }),
    ]),
    field({ name: 'is_primary', label: t('primary_contact'), type: 'checkbox', value: Boolean(contact?.is_primary) }),
    field({ name: 'notes', label: t('notes'), type: 'textarea', value: contact?.notes || '', rows: 2 }),
  ]);

  openModal({
    title: contact ? t('edit') : t('new_contact'),
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          event.currentTarget.disabled = true;
          try {
            const data = readForm(form);
            if (contact) await api.updateContact(contact.id, data);
            else await api.createContact(customerId, data);
            toast(t('saved'), 'success');
            close();
            onSaved?.();
          } catch (error) {
            toastError(error);
            event.currentTarget.disabled = false;
          }
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
