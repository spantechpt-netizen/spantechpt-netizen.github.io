import { api } from '../api.js';
import { t, pick, formatDate, getLang } from '../i18n.js';
import {
  el, clear, icon, dataTable, field, readForm, openModal, confirmDialog,
  toast, toastError, optionsFrom,
} from '../ui.js';
import { can, state } from '../app.js';

const ROLES = ['admin', 'manager', 'engineer', 'viewer'];
const COUNTRIES = ['SA', 'EG', 'QA'];
const SCOPE_SECTIONS = [
  ['design', 'scope_design'], ['supply', 'scope_supply'],
  ['installation', 'scope_installation'], ['deliverables', 'scope_deliverables'],
  ['requirements', 'scope_requirements'], ['exclusions', 'scope_exclusions'],
  ['schedule', 'scope_schedule'], ['team', 'scope_team'], ['warranty', 'scope_warranty'],
];

export async function render() {
  const { settings } = await api.settings();
  state.settings = settings;

  const page = el('div');
  const tabs = el('div.tabs');
  const panel = el('div');

  const TABS = [
    { key: 'company', label: t('company_profile'), build: () => companyPanel(settings) },
    { key: 'prices', label: t('price_book'), build: () => pricePanel(settings) },
    { key: 'templates', label: t('templates'), build: () => templatePanel(settings) },
    { key: 'mail', label: t('mailboxes'), build: () => mailPanel(), need: 'mail.manage' },
    { key: 'users', label: t('users'), build: () => usersPanel(), need: 'users.manage' },
  ].filter((tab) => !tab.need || can(tab.need));

  let active = TABS[0].key;
  const draw = () => {
    clear(tabs);
    for (const tab of TABS) {
      tabs.append(el('button', {
        type: 'button', class: tab.key === active ? 'active' : '', text: tab.label,
        onclick: () => { active = tab.key; draw(); clear(panel).append(tab.build()); },
      }));
    }
  };
  draw();
  panel.append(TABS[0].build());
  // The API reference, for whoever integrates or maintains the system.
  if (can('users.manage')) {
    tabs.append(el('a.tab-link', { href: '/api/docs', target: '_blank', rel: 'noopener', text: t('api_docs') }));
  }
  page.append(tabs, panel);

  if (!can('settings.edit')) {
    page.prepend(el('div.alert.info', {
      text: getLang() === 'ar'
        ? 'لديك صلاحية عرض فقط — التعديل متاح للمدير.'
        : 'You have read-only access — editing requires a manager role.',
    }));
  }
  return page;
}

const readOnly = () => !can('settings.edit');

async function save(key, value, after) {
  try {
    await api.saveSetting(key, value);
    state.settings[key] = value;
    toast(t('saved'), 'success');
    after?.();
  } catch (error) { toastError(error); }
}

// ------------------------------------------------------------------ company
function companyPanel(settings) {
  const company = JSON.parse(JSON.stringify(settings.company));
  if (!company.branches) company.branches = {};

  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'name_en', label: t('company_name_en'), value: company.name_en, dir: 'ltr', disabled: readOnly() }),
      field({ name: 'name_ar', label: t('company_name_ar'), value: company.name_ar, dir: 'rtl', disabled: readOnly() }),
      field({ name: 'tagline_en', label: 'Tagline (EN)', value: company.tagline_en, dir: 'ltr', disabled: readOnly() }),
      field({ name: 'tagline_ar', label: 'الوصف (AR)', value: company.tagline_ar, dir: 'rtl', disabled: readOnly() }),
      field({ name: 'legal_form_en', label: 'Legal form (EN)', value: company.legal_form_en || '', dir: 'ltr', disabled: readOnly() }),
      field({ name: 'legal_form_ar', label: 'الكيان القانوني (AR)', value: company.legal_form_ar || '', dir: 'rtl', disabled: readOnly() }),
      field({ name: 'quote_prefix', label: t('quote_prefix'), value: settings.quote_prefix, dir: 'ltr', disabled: readOnly() }),
      field({
        name: 'default_branch', label: t('default_branch'), type: 'select',
        value: company.default_branch || 'SA', disabled: readOnly(),
        options: ['SA', 'EG', 'QA'].map((c) => ({ value: c, label: t(`country_${c}`) })),
      }),
    ]),
    field({ name: 'vision_ar', label: `${t('company_profile')} — رؤيتنا`, value: company.vision_ar, dir: 'rtl', disabled: readOnly() }),
    field({ name: 'vision_en', label: 'Our vision', value: company.vision_en, dir: 'ltr', disabled: readOnly() }),
    field({ name: 'mission_ar', label: 'رسالتنا', value: company.mission_ar, dir: 'rtl', disabled: readOnly() }),
    field({ name: 'mission_en', label: 'Our mission', value: company.mission_en, dir: 'ltr', disabled: readOnly() }),
  ]);

  const bulletsAr = listEditor(company.profile_ar || [], 'rtl');
  const bulletsEn = listEditor(company.profile_en || [], 'ltr');
  const branches = branchEditor(company.branches);

  return el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('company_profile') })]),
    el('div.card-body', {}, [
      form,
      el('h4.mt-2', { text: t('branches') }),
      el('div.small.muted', { text: t('branches_hint') }),
      branches.node,
      el('h4.mt-2', { text: 'نقاط التعريف بالشركة (عربي)' }),
      bulletsAr.node,
      el('h4.mt-2', { text: 'Company profile bullets (English)' }),
      bulletsEn.node,
      readOnly() ? null : el('div.row.mt-2', {}, [
        el('button.btn', {
          type: 'button', text: t('save'),
          onclick: () => {
            const data = readForm(form);
            const { quote_prefix, ...companyFields } = data;
            save('company', {
              ...company, ...companyFields,
              branches: branches.values(),
              profile_ar: bulletsAr.values(), profile_en: bulletsEn.values(),
            });
            if (quote_prefix) save('quote_prefix', quote_prefix);
          },
        }),
      ]),
    ].filter(Boolean)),
  ]);
}

// --------------------------------------------------------------- price book
function pricePanel(settings) {
  const countries = JSON.parse(JSON.stringify(settings.countries));
  const host = el('div');

  for (const code of COUNTRIES) {
    const book = countries[code];
    if (!book) continue;
    const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
      el('div.grid.grid-3', {}, [
        field({ name: 'currency', label: t('currency'), value: book.currency, dir: 'ltr', disabled: readOnly() }),
        field({ name: 'vat_rate', label: t('vat_rate'), type: 'number', value: book.vat_rate, min: 0, max: 100, step: 0.5, disabled: readOnly() }),
        field({ name: 'valid_days', label: t('valid_days'), type: 'number', value: book.valid_days, min: 1, max: 365, disabled: readOnly() }),
        field({ name: 'default_price_sqm', label: t('default_price'), type: 'number', value: book.default_price_sqm, min: 0, step: 0.5, disabled: readOnly() }),
        field({ name: 'floor_price_sqm', label: t('floor_price'), type: 'number', value: book.floor_price_sqm, min: 0, step: 0.5, disabled: readOnly() }),
        field({ name: 'strand_price_ton', label: t('strand_price_ton'), type: 'number', value: book.strand_price_ton, min: 0, step: 1, disabled: readOnly() }),
        field({ name: 'strand_kg_sqm', label: t('strand_kg_sqm'), type: 'number', value: book.strand_kg_sqm, min: 0, step: 0.1, disabled: readOnly() }),
        field({ name: 'anchors_per_ton', label: t('anchors_per_ton'), type: 'number', value: book.anchors_per_ton, min: 0, step: 1, disabled: readOnly() }),
      ]),
    ]);

    host.append(el('div.card', {}, [
      el('div.card-header', {}, [
        el('h3', { text: t(`country_${code}`) }),
        el('div.spacer'),
        el('span.badge.blue', { text: book.currency }),
      ]),
      el('div.card-body', {}, [
        form,
        readOnly() ? null : el('button.btn.btn-sm', {
          type: 'button', text: t('save'),
          onclick: () => {
            const data = readForm(form);
            countries[code] = { ...book, ...data };
            save('countries', countries);
          },
        }),
      ].filter(Boolean)),
    ]));
  }

  host.prepend(el('div.alert.warn', {
    text: getLang() === 'ar'
      ? 'راجع أسعار الكابلات والأسعار الافتراضية دورياً — الأسعار المبدئية هنا تقديرية ويجب تحديثها بأسعار السوق الفعلية.'
      : 'Review strand prices and default rates regularly — the seeded figures are placeholders and must be replaced with your real market prices.',
  }));
  return host;
}

// ---------------------------------------------------------------- templates
function templatePanel(settings) {
  const scope = JSON.parse(JSON.stringify(settings.scope));
  const paymentTerms = JSON.parse(JSON.stringify(settings.payment_terms));
  const conditions = JSON.parse(JSON.stringify(settings.conditions));
  const host = el('div');

  host.append(el('div.alert.info', {
    text: getLang() === 'ar'
      ? 'هذه القوالب تُنسخ إلى كل عرض سعر جديد. تعديلها هنا لا يؤثر على العروض الصادرة سابقاً.'
      : 'These templates are copied into every new quotation. Editing them here does not change offers already issued.',
  }));

  // -- scope sections
  const scopeBody = el('div.card-body');
  for (const [key, labelKey] of SCOPE_SECTIONS) {
    const section = scope[key];
    if (!section) continue;
    const editor = pairListEditor(section.items);
    scopeBody.append(el('details', { style: { marginBottom: '.6rem' } }, [
      el('summary', { style: { cursor: 'pointer', fontWeight: '700', padding: '.35rem 0' }, text: t(labelKey) }),
      editor.node,
    ]));
    section._editor = editor;
  }
  host.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('templates') }),
      el('div.spacer'),
      readOnly() ? null : el('button.btn.btn-sm', {
        type: 'button', text: t('save'),
        onclick: () => {
          for (const [key] of SCOPE_SECTIONS) {
            if (scope[key]?._editor) {
              scope[key].items = scope[key]._editor.values();
              delete scope[key]._editor;
            }
          }
          save('scope', scope);
        },
      }),
    ].filter(Boolean)),
    scopeBody,
  ]));

  // -- payment terms
  const paymentEditor = paymentListEditor(paymentTerms);
  host.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('payment_terms') }),
      el('div.spacer'),
      readOnly() ? null : el('button.btn.btn-sm', {
        type: 'button', text: t('save'),
        onclick: () => save('payment_terms', paymentEditor.values()),
      }),
    ].filter(Boolean)),
    el('div.card-body', {}, [paymentEditor.node]),
  ]));

  // -- conditions
  const conditionEditor = pairListEditor(conditions);
  host.append(el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('conditions') }),
      el('div.spacer'),
      readOnly() ? null : el('button.btn.btn-sm', {
        type: 'button', text: t('save'),
        onclick: () => save('conditions', conditionEditor.values()),
      }),
    ].filter(Boolean)),
    el('div.card-body', {}, [conditionEditor.node]),
  ]));

  return host;
}

/** Editor for a list of plain strings. */
function listEditor(initial, dir) {
  const node = el('div');
  let values = [...initial];

  const draw = () => {
    clear(node);
    values.forEach((value, index) => {
      const input = el('input', { type: 'text', dir, disabled: readOnly() });
      input.value = value;
      input.addEventListener('input', () => { values[index] = input.value; });
      node.append(el('div.row', { style: { marginBottom: '.3rem' } }, [
        input,
        readOnly() ? null : el('button.btn.btn-sm.btn-danger', {
          type: 'button', onclick: () => { values.splice(index, 1); draw(); },
        }, [icon('trash', 12)]),
      ].filter(Boolean)));
    });
    if (!readOnly()) {
      node.append(el('button.btn.btn-sm.btn-secondary', {
        type: 'button', text: t('add'),
        onclick: () => { values.push(''); draw(); },
      }));
    }
  };
  draw();
  return { node, values: () => values.filter((value) => value.trim()) };
}

/** Editor for a list of { en, ar } pairs. */
function pairListEditor(initial) {
  const node = el('div');
  let values = initial.map((item) => ({ ...item }));

  const draw = () => {
    clear(node);
    values.forEach((item, index) => {
      const ar = el('textarea', { rows: 2, dir: 'rtl', disabled: readOnly(), placeholder: 'عربي' });
      ar.value = item.ar || '';
      ar.addEventListener('input', () => { values[index].ar = ar.value; });

      const en = el('textarea', { rows: 2, dir: 'ltr', disabled: readOnly(), placeholder: 'English' });
      en.value = item.en || '';
      en.addEventListener('input', () => { values[index].en = en.value; });

      node.append(el('div.row', {
        style: { marginBottom: '.4rem', alignItems: 'flex-start', gap: '.4rem' },
      }, [
        el('div', { style: { flex: '1' } }, [ar]),
        el('div', { style: { flex: '1' } }, [en]),
        readOnly() ? null : el('button.btn.btn-sm.btn-danger', {
          type: 'button', onclick: () => { values.splice(index, 1); draw(); },
        }, [icon('trash', 12)]),
      ].filter(Boolean)));
    });
    if (!readOnly()) {
      node.append(el('button.btn.btn-sm.btn-secondary', {
        type: 'button', text: t('add'),
        onclick: () => { values.push({ en: '', ar: '' }); draw(); },
      }));
    }
  };
  draw();
  return { node, values: () => values.filter((item) => (item.en || '').trim() || (item.ar || '').trim()) };
}

/** Editor for payment milestones: percentage plus a bilingual label. */
function paymentListEditor(initial) {
  const node = el('div');
  let values = initial.map((item) => ({ ...item }));
  const totalNode = el('div.tiny.bold');

  const drawTotal = () => {
    const sum = values.reduce((acc, item) => acc + Number(item.pct || 0), 0);
    totalNode.textContent = `${t('total')}: ${sum}%`;
    totalNode.style.color = sum === 100 ? 'var(--ok-700)' : 'var(--danger-700)';
  };

  const draw = () => {
    clear(node);
    values.forEach((item, index) => {
      const pct = el('input.num', { type: 'number', min: '0', max: '100', step: '5', style: { width: '78px' }, disabled: readOnly() });
      pct.value = item.pct;
      pct.addEventListener('input', () => { values[index].pct = Number(pct.value || 0); drawTotal(); });

      const ar = el('input', { type: 'text', dir: 'rtl', disabled: readOnly(), placeholder: 'عربي' });
      ar.value = item.ar || '';
      ar.addEventListener('input', () => { values[index].ar = ar.value; });

      const en = el('input', { type: 'text', dir: 'ltr', disabled: readOnly(), placeholder: 'English' });
      en.value = item.en || '';
      en.addEventListener('input', () => { values[index].en = en.value; });

      node.append(el('div.row', { style: { marginBottom: '.35rem', gap: '.4rem' } }, [
        pct, el('span', { text: '%' }), ar, en,
        readOnly() ? null : el('button.btn.btn-sm.btn-danger', {
          type: 'button', onclick: () => { values.splice(index, 1); draw(); },
        }, [icon('trash', 12)]),
      ].filter(Boolean)));
    });
    node.append(totalNode);
    if (!readOnly()) {
      node.append(el('button.btn.btn-sm.btn-secondary.mt-1', {
        type: 'button', text: t('add'),
        onclick: () => { values.push({ pct: 0, en: '', ar: '' }); draw(); },
      }));
    }
    drawTotal();
  };
  draw();
  return { node, values: () => values };
}

// -------------------------------------------------------------------- users
function usersPanel() {
  const host = el('div');

  async function refresh() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { users } = await api.users();
      state.users = users;
      clear(host).append(
        el('div.row.mb-1', {}, [
          el('div.spacer'),
          el('button.btn', { type: 'button', onclick: () => openUserForm(null, refresh) }, [icon('plus', 15), t('new_user')]),
        ]),
        dataTable({
          rows: users,
          columns: [
            {
              label: t('customer_name_en'),
              render: (row) => el('div', {}, [
                el('div.bold', { text: pick(row, 'name') }),
                el('div.tiny.muted', { text: row.email }),
              ]),
            },
            {
              label: t('role'),
              render: (row) => el('span.badge', {
                class: row.role === 'admin' ? 'red' : row.role === 'manager' ? 'orange' : 'blue',
                text: t(`role_${row.role}`),
              }),
            },
            {
              label: t('permissions'), className: 'num',
              render: (row) => {
                const overrides = Object.keys(row.permission_overrides || {}).length;
                return el('span', {}, [
                  el('span.badge.grey', { text: String((row.effective_permissions || []).length) }),
                  overrides
                    ? el('span.badge.orange', { style: { marginInlineStart: '.25rem' }, text: `${overrides} ${t('perm_custom')}` })
                    : null,
                ]);
              },
            },
            { label: t('country'), render: (row) => t(`country_${row.country}`) },
            { label: t('last_login'), render: (row) => formatDate(row.last_login_at) },
            {
              label: t('status'),
              render: (row) => el('span.badge', {
                class: row.active ? 'green' : 'grey',
                text: row.active ? t('active') : t('inactive'),
              }),
            },
            {
              label: '', className: 'end',
              render: (row) => el('div.row', {}, [
                el('button.btn.btn-sm.btn-secondary', {
                  type: 'button', text: t('edit'), onclick: () => openUserForm(row, refresh),
                }),
                row.active ? el('button.btn.btn-sm.btn-danger', {
                  type: 'button', title: t('inactive'),
                  onclick: async () => {
                    if (!await confirmDialog(t('confirm_delete'))) return;
                    try { await api.deleteUser(row.id); toast(t('saved'), 'success'); refresh(); }
                    catch (error) { toastError(error); }
                  },
                }, [icon('x', 13)]) : null,
              ]),
            },
          ],
        }),
      );
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  refresh();
  return host;
}

/**
 * Renders the capability matrix. Each row shows whether the role grants it by
 * default, and lets an administrator force it on or off for this one person.
 */
function permissionMatrix(catalogue, user, roleSelect) {
  const host = el('div');
  const overrides = { ...(user?.permission_overrides || {}) };
  let role = user?.role || 'engineer';

  const draw = () => {
    clear(host);
    const defaults = new Set(catalogue.role_defaults[role] || []);

    host.append(el('div.alert.info', {
      style: { marginBottom: '.6rem' },
      text: getLang() === 'ar'
        ? `الصلاحيات دي مبنية على دور "${t(`role_${role}`)}". شيل أو حط علامة على أي بند عشان تخصصه للشخص ده لوحده.`
        : `These start from the "${t(`role_${role}`)}" role. Tick or untick any line to override it for this person only.`,
    }));

    for (const group of catalogue.groups) {
      const rows = catalogue.permissions.filter((p) => p.group === group.key);
      if (!rows.length) continue;

      const body = el('div.perm-group-body');
      for (const permission of rows) {
        const byDefault = defaults.has(permission.key);
        const override = overrides[permission.key];
        const effective = override === undefined ? byDefault : override;

        const box = el('input', { type: 'checkbox' });
        box.checked = effective;
        box.addEventListener('change', () => {
          // Matching the role default clears the override entirely.
          if (box.checked === byDefault) delete overrides[permission.key];
          else overrides[permission.key] = box.checked;
          row.classList.toggle('is-override', overrides[permission.key] !== undefined);
          tag.textContent = overrides[permission.key] === undefined
            ? (byDefault ? t('perm_default_on') : t('perm_default_off'))
            : t('perm_overridden');
        });

        const tag = el('span.perm-tag', {
          text: override === undefined
            ? (byDefault ? t('perm_default_on') : t('perm_default_off'))
            : t('perm_overridden'),
        });

        const row = el(`div.perm-row${override === undefined ? '' : '.is-override'}`, {}, [
          el('label.checkbox', { style: { flex: '1' } }, [
            box,
            el('span', { text: getLang() === 'ar' ? permission.ar : permission.en }),
          ]),
          tag,
        ]);
        body.append(row);
      }

      host.append(el('details.perm-group', { open: true }, [
        el('summary', { text: getLang() === 'ar' ? group.ar : group.en }),
        body,
      ]));
    }
  };

  // Changing the role re-bases the matrix on that role's defaults.
  roleSelect?.addEventListener('change', (event) => {
    role = event.target.value;
    draw();
  });

  draw();
  return { node: host, values: () => overrides };
}

function openUserForm(user, onSaved) {
  const isEdit = Boolean(user);
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'name', label: t('customer_name_en'), value: user?.name || '', required: true, dir: 'ltr' }),
      field({ name: 'name_ar', label: t('customer_name_ar'), value: user?.name_ar || '', dir: 'rtl' }),
      field({ name: 'email', label: t('email'), type: 'email', value: user?.email || '', required: true, dir: 'ltr' }),
      field({
        name: 'password', label: isEdit ? t('new_password') : t('password'),
        type: 'password', required: !isEdit, hint: t('password_min'),
      }),
      field({ name: 'role', label: t('role'), type: 'select', value: user?.role || 'engineer', options: optionsFrom(ROLES, 'role_') }),
      field({ name: 'country', label: t('country'), type: 'select', value: user?.country || 'SA', options: COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })) }),
      field({ name: 'title', label: t('contact_title'), value: user?.title || '', dir: 'ltr' }),
      field({ name: 'title_ar', label: `${t('contact_title')} (AR)`, value: user?.title_ar || '', dir: 'rtl' }),
      field({ name: 'phone', label: t('phone'), type: 'tel', value: user?.phone || '', dir: 'ltr' }),
      field({ name: 'lang', label: t('language'), type: 'select', value: user?.lang || 'ar', options: [{ value: 'ar', label: 'العربية' }, { value: 'en', label: 'English' }] }),
    ]),
    isEdit ? field({ name: 'active', label: t('active'), type: 'checkbox', value: Boolean(user.active) }) : null,
  ]);

  const permHost = el('div', {}, [
    el('h4.mt-2', { text: t('permissions') }),
    el('div.muted.small', { text: t('loading') }),
  ]);
  form.append(permHost);

  let matrix = null;
  api.permissionCatalogue().then((catalogue) => {
    clear(permHost).append(el('h4.mt-2', { text: t('permissions') }));
    matrix = permissionMatrix(catalogue, user, form.querySelector('[name="role"]'));
    permHost.append(matrix.node);
  }).catch(() => {
    clear(permHost).append(el('div.alert.warn', { text: t('error') }));
  });

  openModal({
    title: isEdit ? `${t('edit')} — ${pick(user, 'name')}` : t('new_user'),
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
            if (isEdit && !data.password) delete data.password;
            if (matrix) data.permission_overrides = matrix.values();
            if (isEdit) await api.updateUser(user.id, data);
            else await api.createUser(data);
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


// ================================================================= mailboxes
/**
 * Company mailboxes the CRM reads, plus the optional Claude key that powers
 * the richer extraction. Passwords go in but never come back out.
 */
function mailPanel() {
  const host = el('div');

  host.append(el('div.alert.info', {
    text: getLang() === 'ar'
      ? 'النظام بيقرا البريد بس — عمره ما بيبعت ولا بيمسح، والرسايل بتتقرا من غير ما تتعلّم كمقروءة. استخدم "كلمة مرور تطبيق" مش كلمة سر الإيميل الأصلية.'
      : 'The CRM only reads mail — it never sends or deletes, and messages are fetched without marking them read. Use an app password, not the account’s main password.',
  }));

  const accountsHost = el('div');
  const aiHost = el('div');
  host.append(accountsHost, aiHost);

  async function loadAccounts() {
    clear(accountsHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { accounts } = await api.mailAccounts();
      clear(accountsHost).append(el('div.card', {}, [
        el('div.card-header', {}, [
          el('h3', { text: t('mailboxes') }),
          el('div.spacer'),
          el('button.btn.btn-sm', {
            type: 'button', onclick: () => openMailAccountForm(null, loadAccounts),
          }, [icon('plus', 14), t('add_mailbox')]),
        ]),
        el('div.card-body.flush', {}, [
          accounts.length
            ? dataTable({
              rows: accounts,
              columns: [
                {
                  label: t('mailbox_label'),
                  render: (row) => el('div', {}, [
                    el('div.bold', { text: row.label }),
                    el('div.tiny.muted', { text: `${row.username} · ${row.host}:${row.port}` }),
                  ]),
                },
                { label: t('mail_folders'), render: (row) => (row.folders || []).join(', ') },
                { label: t('sync_every'), className: 'num', render: (row) => `${row.sync_minutes} ${t('minutes')}` },
                {
                  label: t('last_sync'),
                  render: (row) => el('div', {}, [
                    el('div.tiny', { text: row.last_sync_at ? formatDate(row.last_sync_at) : '—' }),
                    row.last_error
                      ? el('div.tiny', { style: { color: 'var(--danger-700)' }, text: String(row.last_error).slice(0, 60) })
                      : null,
                  ]),
                },
                {
                  label: t('status'),
                  render: (row) => el('span.badge', {
                    class: row.active ? 'green' : 'grey',
                    text: row.active ? t('active') : t('inactive'),
                  }),
                },
                {
                  label: '', className: 'end',
                  render: (row) => el('div.row', {}, [
                    el('button.btn.btn-sm.btn-secondary', {
                      type: 'button', text: t('test_connection'),
                      onclick: async (event) => {
                        const button = event.currentTarget;
                        button.disabled = true;
                        try {
                          const result = await api.testMailAccount(row.id);
                          if (result.ok) toast(`${t('connection_ok')} — ${result.folders.length} ${t('mail_folders')}`, 'success');
                          else toast(result.error, 'error', 7000);
                        } catch (error) { toastError(error); }
                        button.disabled = false;
                        loadAccounts();
                      },
                    }),
                    el('button.btn.btn-sm.btn-secondary', {
                      type: 'button', text: t('fetch_mail_now'),
                      onclick: async (event) => {
                        const button = event.currentTarget;
                        button.disabled = true;
                        try {
                          const { summary } = await api.syncMailAccount(row.id, { since_days: 30 });
                          toast(`${summary.stored} ${t('mail_stored')} · ${summary.queued} ${t('req_new')}`, 'success');
                        } catch (error) { toastError(error); }
                        button.disabled = false;
                        loadAccounts();
                      },
                    }),
                    el('button.btn.btn-sm.btn-secondary', {
                      type: 'button', text: t('backfill'),
                      title: t('backfill_hint'),
                      onclick: () => openBackfill(row, loadAccounts),
                    }),
                    el('button.btn.btn-sm.btn-secondary', {
                      type: 'button', text: t('edit'),
                      onclick: () => openMailAccountForm(row, loadAccounts),
                    }),
                    el('button.btn.btn-sm.btn-danger', {
                      type: 'button', title: t('delete'),
                      onclick: async () => {
                        if (!await confirmDialog(t('confirm_delete'))) return;
                        try { await api.deleteMailAccount(row.id); loadAccounts(); }
                        catch (error) { toastError(error); }
                      },
                    }, [icon('trash', 13)]),
                  ]),
                },
              ],
            })
            : el('div.empty', {}, [icon('mail', 40), el('div', { text: t('no_mailboxes') })]),
        ]),
      ]));
    } catch (error) {
      clear(accountsHost).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  async function loadAi() {
    clear(aiHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { ai } = await api.aiSettings();
      const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
        el('div.grid.grid-2', {}, [
          field({
            name: 'api_key', label: t('ai_key'), type: 'password',
            placeholder: ai.has_key ? ai.key_hint : 'sk-ant-…', dir: 'ltr',
            hint: ai.has_key ? t('ai_key_set') : t('ai_key_hint'),
          }),
          field({
            name: 'model', label: t('ai_model'), type: 'select', value: ai.model,
            options: [
              { value: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
              { value: 'claude-opus-5', label: 'Claude Opus 5' },
              { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
            ],
          }),
        ]),
        field({ name: 'enabled', label: t('ai_enabled'), type: 'checkbox', value: ai.enabled }),
      ]);

      clear(aiHost).append(el('div.card', {}, [
        el('div.card-header', {}, [
          el('h3', { text: t('ai_extraction') }),
          el('div.spacer'),
          ai.has_key ? el('span.badge.green', { text: t('ai_key_set') }) : el('span.badge.grey', { text: t('ai_off') }),
        ]),
        el('div.card-body', {}, [
          el('p.small.muted', { text: t('ai_explain') }),
          form,
          el('div.row', {}, [
            el('button.btn', {
              type: 'button', text: t('save'),
              onclick: async () => {
                try {
                  const data = readForm(form);
                  await api.saveAiSettings(data);
                  toast(t('saved'), 'success');
                  loadAi();
                } catch (error) { toastError(error); }
              },
            }),
            ai.has_key ? el('button.btn.btn-secondary', {
              type: 'button', text: t('ai_clear_key'),
              onclick: async () => {
                if (!await confirmDialog(t('confirm_delete'))) return;
                try { await api.saveAiSettings({ clear_key: true }); loadAi(); }
                catch (error) { toastError(error); }
              },
            }) : null,
          ]),
        ]),
      ]));
    } catch (error) {
      clear(aiHost).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  loadAccounts();
  loadAi();
  return host;
}

function openMailAccountForm(account, onSaved) {
  const isEdit = Boolean(account);
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'label', label: t('mailbox_label'), value: account?.label || '', required: true }),
      field({ name: 'username', label: t('mailbox_user'), value: account?.username || '', required: true, dir: 'ltr' }),
      field({ name: 'host', label: t('imap_host'), value: account?.host || '', required: true, dir: 'ltr', hint: 'imap.gmail.com · outlook.office365.com' }),
      field({ name: 'port', label: t('imap_port'), type: 'number', value: account?.port ?? 993, min: 1, max: 65535 }),
      field({
        name: 'password', label: t('mailbox_password'), type: 'password',
        placeholder: isEdit ? '••••••••' : '', dir: 'ltr',
        hint: isEdit ? t('password_unchanged') : t('use_app_password'),
      }),
      field({ name: 'folders', label: t('mail_folders'), value: (account?.folders || ['INBOX']).join(', '), hint: 'INBOX, Archive' }),
      field({ name: 'sync_minutes', label: t('sync_every'), type: 'number', value: account?.sync_minutes ?? 10, min: 1, max: 1440 }),
    ]),
    field({ name: 'secure', label: t('imap_tls'), type: 'checkbox', value: account ? Boolean(account.secure) : true, hint: t('imap_tls_hint') }),
    field({ name: 'allow_self_signed', label: t('allow_self_signed'), type: 'checkbox', value: Boolean(account?.allow_self_signed), hint: t('allow_self_signed_hint') }),
    isEdit ? field({ name: 'active', label: t('active'), type: 'checkbox', value: Boolean(account.active) }) : null,
  ]);

  openModal({
    title: isEdit ? `${t('edit')} — ${account.label}` : t('add_mailbox'),
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
            data.folders = String(data.folders || 'INBOX').split(',').map((f) => f.trim()).filter(Boolean);
            if (isEdit && !data.password) delete data.password;
            if (isEdit) await api.updateMailAccount(account.id, data);
            else await api.createMailAccount(data);
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


/**
 * Scans older mail to find customers and projects already discussed by email.
 * It is the same sync, told to ignore the stored position and reach further
 * back, so nothing is imported twice.
 */
function openBackfill(account, onDone) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('p.small', { text: t('backfill_explain') }),
    el('div.grid.grid-2', {}, [
      field({
        name: 'since_days', label: t('backfill_period'), type: 'select', value: '365',
        options: [
          { value: '90', label: t('backfill_3m') },
          { value: '180', label: t('backfill_6m') },
          { value: '365', label: t('backfill_1y') },
          { value: '1095', label: t('backfill_3y') },
          { value: '3650', label: t('backfill_all') },
        ],
      }),
      field({ name: 'limit', label: t('backfill_limit'), type: 'number', value: 300, min: 1, max: 1000 }),
    ]),
    field({
      name: 'folders', label: t('mail_folders'),
      value: (account.folders || ['INBOX']).join(', '),
      hint: t('backfill_folders_hint'),
    }),
  ]);

  const progress = el('div');

  openModal({
    title: `${t('backfill')} — ${account.label}`,
    body: el('div', {}, [form, progress]),
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('backfill_start'),
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          const data = readForm(form);
          clear(progress).append(el('div.alert.info', { text: t('backfill_running') }));
          try {
            // Widen the folder list first if the person added any.
            const folders = String(data.folders || 'INBOX').split(',').map((f) => f.trim()).filter(Boolean);
            await api.updateMailAccount(account.id, { folders });

            const { summary } = await api.syncMailAccount(account.id, {
              since_days: Number(data.since_days),
              limit: Number(data.limit),
              backfill: true,
            });
            clear(progress).append(el('div.alert.ok', {
              text: `${summary.fetched} ${t('mail_read')} · ${summary.stored} ${t('mail_stored')} · ${summary.queued} ${t('req_new')}`,
            }));
            // A big mailbox takes more than one run; say so rather than
            // leaving the impression that everything came in.
            if (summary.remaining) {
              progress.append(el('div.alert.info', {
                style: { marginTop: '.5rem' },
                text: `${t('backfill_remaining')} ${summary.remaining} — ${t('backfill_again')}`,
              }));
            }
            onDone?.();
          } catch (error) {
            clear(progress).append(el('div.alert.danger', { text: error.localised || error.message }));
          }
          button.disabled = false;
        },
      }),
    ]),
  });
}


/**
 * Per-country office details. A quotation prints the branch matching its own
 * country, so the Saudi CR and the Cairo address never appear on the same
 * document.
 */
function branchEditor(initial) {
  const COUNTRIES = ['SA', 'EG', 'QA'];
  const values = JSON.parse(JSON.stringify(initial || {}));
  const node = el('div');

  for (const code of COUNTRIES) {
    const branch = values[code] || (values[code] = {});
    const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
      el('div.grid.grid-2', {}, [
        field({ name: 'name_en', label: t('company_name_en'), value: branch.name_en || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'name_ar', label: t('company_name_ar'), value: branch.name_ar || '', dir: 'rtl', disabled: readOnly() }),
        field({ name: 'cr_number', label: t('cr_number'), value: branch.cr_number || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'vat_number', label: t('tax_number'), value: branch.vat_number || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'phone', label: t('phone'), value: branch.phone || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'email', label: t('email'), value: branch.email || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'website', label: t('website'), value: branch.website || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'address_en', label: `${t('address')} (EN)`, value: branch.address_en || '', dir: 'ltr', disabled: readOnly() }),
        field({ name: 'address_ar', label: `${t('address')} (AR)`, value: branch.address_ar || '', dir: 'rtl', disabled: readOnly() }),
      ]),
    ]);

    // Read straight off the inputs on save, so nothing needs re-binding.
    branch._form = form;

    node.append(el('details.perm-group', { open: code === 'SA' }, [
      el('summary', { text: `${t(`country_${code}`)} — ${branch.email || branch.phone || t('none')}` }),
      el('div.perm-group-body', {}, [form]),
    ]));
  }

  return {
    node,
    values: () => {
      const out = {};
      for (const code of COUNTRIES) {
        const branch = values[code];
        const data = readForm(branch._form);
        out[code] = {
          ...branch,
          ...Object.fromEntries(Object.entries(data).map(([k, v]) => [k, v ?? ''])),
        };
        delete out[code]._form;
      }
      return out;
    },
  };
}
