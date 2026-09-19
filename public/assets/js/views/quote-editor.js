import { api } from '../api.js';
import { t, pick, money, formatDate, getLang } from '../i18n.js';
import {
  el, clear, icon, field, readForm, openModal, confirmDialog,
  toast, toastError, quoteStatusBadge, optionsFrom,
} from '../ui.js';
import { can, canSeeAll, canSeeCost, state } from '../app.js';
import { openNewQuotation } from './quotations.js';
import { printQuotation } from './quote-print.js';

const SCOPE_SECTIONS = [
  ['design', 'scope_design'],
  ['supply', 'scope_supply'],
  ['installation', 'scope_installation'],
  ['deliverables', 'scope_deliverables'],
  ['requirements', 'scope_requirements'],
  ['exclusions', 'scope_exclusions'],
  ['schedule', 'scope_schedule'],
  ['team', 'scope_team'],
  ['warranty', 'scope_warranty'],
];

export async function render({ params, navigate }) {
  const raw = params[0] || '';
  const [id, query] = raw.split('?');

  if (id === 'new') {
    const opportunityId = new URLSearchParams(query || '').get('opportunity');
    // Defer so the outlet is mounted before the modal opens over it.
    setTimeout(() => openNewQuotation(navigate, opportunityId), 0);
    return el('div.loading-page', { text: t('loading') });
  }

  const data = await api.quotation(id);
  return editor(data, navigate);
}

function editor(data, navigate) {
  let quote = data.quotation;
  let breakdown = data.breakdown;
  let items = quote.items.map((item) => ({ ...item }));
  let scope = quote.scope;
  let paymentTerms = quote.payment_terms;
  let conditions = quote.conditions;
  let dirty = false;

  const page = el('div');
  const readOnly = !can('quotations.edit');

  // ---------------------------------------------------------------- header
  const statusHost = el('div.row.wrap');
  const header = el('div.toolbar', {}, [
    el('button.btn.btn-secondary.btn-icon', {
      type: 'button', title: t('back'), onclick: () => navigate('quotations'),
    }, [icon('back', 16)]),
    el('div', {}, [
      el('h2', { style: { margin: 0 } }, [
        el('span.num', { text: quote.number }),
        quote.revision > 0 ? el('span.badge.grey', { style: { marginInlineStart: '.4rem' }, text: `R${quote.revision}` }) : null,
      ]),
      el('div.tiny.muted', { text: `${pick(quote, 'customer_name')} · ${formatDate(quote.issue_date)}` }),
    ]),
    el('div.spacer'),
    statusHost,
  ]);
  page.append(header);

  // ------------------------------------------------------------- main grid
  const layout = el('div.editor-layout');
  const left = el('div');
  const right = el('div.sticky-panel');
  layout.append(left, right);
  page.append(layout);

  // ---- details card ------------------------------------------------------
  const detailsForm = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'project_name', label: t('project_name'), value: quote.project_name, required: true, dir: 'ltr', disabled: readOnly }),
      field({ name: 'project_name_ar', label: t('project_name_ar'), value: quote.project_name_ar || '', dir: 'rtl', disabled: readOnly }),
      field({ name: 'attention', label: t('attention'), value: quote.attention || '', dir: 'ltr', disabled: readOnly }),
      field({ name: 'attention_ar', label: t('attention_ar'), value: quote.attention_ar || '', dir: 'rtl', disabled: readOnly }),
      field({ name: 'location', label: t('location'), value: quote.location || '', disabled: readOnly }),
      field({ name: 'location_ar', label: t('location_ar'), value: quote.location_ar || '', dir: 'rtl', disabled: readOnly }),
      field({ name: 'issue_date', label: t('issue_date'), type: 'date', value: quote.issue_date, disabled: readOnly }),
      field({ name: 'valid_days', label: t('valid_days'), type: 'number', value: quote.valid_days, min: 1, max: 365, disabled: readOnly }),
      field({
        name: 'country', label: t('country'), type: 'select', value: quote.country,
        options: ['SA', 'EG', 'QA'].map((c) => ({ value: c, label: t(`country_${c}`) })), disabled: readOnly,
      }),
      field({
        name: 'currency', label: t('currency'), type: 'select', value: quote.currency,
        options: ['SAR', 'EGP', 'QAR', 'USD'].map((c) => ({ value: c, label: c })), disabled: readOnly,
      }),
      field({
        name: 'duct_type', label: t('duct_type'), type: 'select', value: quote.duct_type || 'steel',
        options: ['steel', 'plastic'].map((d) => ({ value: d, label: t(`duct_${d}`) })),
        hint: t('duct_hint'), disabled: readOnly,
      }),
      field({
        name: 'labour_scope', label: t('labour_scope'), type: 'select',
        value: quote.labour_scope || 'spantech',
        options: [
          { value: 'spantech', label: t('labour_spantech') },
          { value: 'client', label: t('labour_client') },
        ],
        hint: t('labour_scope_hint'), disabled: readOnly,
      }),
      field({ name: 'vat_rate', label: t('vat_rate'), type: 'number', value: quote.vat_rate, min: 0, max: 100, step: 0.5, disabled: readOnly }),
      field({ name: 'price_variance', label: t('price_variance'), type: 'number', value: quote.price_variance, min: 0, max: 100, step: 0.5, disabled: readOnly }),
    ]),
  ]);

  // Switching country re-applies that market's VAT and currency.
  detailsForm.querySelector('[name="country"]')?.addEventListener('change', (event) => {
    const book = state.settings?.countries?.[event.target.value];
    if (!book) return;
    detailsForm.querySelector('[name="currency"]').value = book.currency;
    detailsForm.querySelector('[name="vat_rate"]').value = book.vat_rate;
    markDirty();
  });
  detailsForm.addEventListener('input', markDirty);

  left.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('quotation') })]),
    el('div.card-body', {}, [detailsForm]),
  ]));

  // ---- line items --------------------------------------------------------
  const itemsHost = el('tbody');
  const itemsCard = el('div.card', {}, [
    el('div.card-header', {}, [
      el('h3', { text: t('line_items') }),
      el('div.spacer'),
      readOnly ? null : el('button.btn.btn-sm.btn-secondary', {
        type: 'button', onclick: () => { addItem(); }, text: t('add_item'),
      }, [icon('plus', 13)]),
    ]),
    el('div.card-body', {}, [
      el('div.table-wrap', {}, [
        el('table.items-table', {}, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: t('description') }),
            el('th', { text: t('unit') }),
            el('th.col-qty', { text: t('quantity') }),
            el('th.col-price', { text: t('unit_price') }),
            el('th.col-amount', { text: t('amount') }),
            readOnly ? null : el('th.col-del'),
          ].filter(Boolean))]),
          itemsHost,
        ]),
      ]),
    ]),
  ]);
  left.append(itemsCard);

  function drawItems() {
    clear(itemsHost);
    items.forEach((item, index) => {
      const amountCell = el('td.col-amount.num', {
        text: money(Number(item.qty || 0) * Number(item.unit_price || 0)),
      });

      const textInput = (key, dir) => {
        const input = el('input', { type: 'text', dir, disabled: readOnly });
        input.value = item[key] ?? '';
        input.addEventListener('input', () => { item[key] = input.value; markDirty(); });
        return input;
      };
      const numberInput = (key) => {
        const input = el('input.num', { type: 'number', min: '0', step: '0.01', disabled: readOnly });
        input.value = item[key] ?? 0;
        input.addEventListener('input', () => {
          item[key] = input.value === '' ? 0 : Number(input.value);
          amountCell.textContent = money(Number(item.qty || 0) * Number(item.unit_price || 0));
          recalcLocal();
          markDirty();
        });
        return input;
      };

      itemsHost.append(el('tr', {}, [
        el('td', {}, [
          textInput('desc_en', 'ltr'),
          el('div', { style: { marginTop: '.2rem' } }, [textInput('desc_ar', 'rtl')]),
          item.is_optional ? el('span.badge.grey', { text: t('optional_item') }) : null,
        ]),
        el('td', { style: { width: '90px' } }, [textInput('unit_en'), textInput('unit_ar', 'rtl')]),
        el('td.col-qty', {}, [numberInput('qty')]),
        el('td.col-price', {}, [numberInput('unit_price')]),
        amountCell,
        readOnly ? null : el('td.col-del', {}, [
          el('button.btn.btn-sm.btn-danger', {
            type: 'button', title: t('delete'),
            onclick: () => {
              if (items.length === 1) return toast(t('error'), 'error');
              items.splice(index, 1);
              drawItems();
              recalcLocal();
              markDirty();
            },
          }, [icon('trash', 12)]),
        ]),
      ].filter(Boolean)));
    });
  }

  function addItem() {
    items.push({
      sort_order: items.length,
      desc_en: '', desc_ar: '',
      unit_en: 'm²', unit_ar: 'م²',
      qty: 0, unit_price: 0, is_optional: 0,
    });
    drawItems();
  }
  drawItems();

  // ---- scope & terms (accordion) ----------------------------------------
  // Held in a host of its own: changing the duct material or who supplies the
  // labour rewrites the scope on the server, and the list has to show what the
  // offer will actually print rather than what it printed a minute ago.
  const scopeHost = el('div');
  const drawScope = () => { clear(scopeHost); scopeHost.append(scopeCard()); };
  drawScope();
  left.append(scopeHost);
  left.append(termsCard());

  // ---- totals panel ------------------------------------------------------
  const totalsHost = el('div.card-body');
  right.append(el('div.card', {}, [
    el('div.card-header', {}, [el('h3', { text: t('total') })]),
    totalsHost,
  ]));

  // The cost calculator is the cost permission, not a manager's screen: an
  // engineer whose "sees cost and margin" is unticked does not get the card,
  // and the server does not send the numbers behind it either.
  const calcHost = el('div.card-body');
  if (canSeeCost()) {
    right.append(el('div.card', {}, [
      el('div.card-header', {}, [
        el('h3', { text: t('cost_calculator') }),
        el('div.spacer'),
        el('span.badge.amber', { text: t('internal_only') }),
      ]),
      calcHost,
    ]));
  }

  function recalcLocal() {
    const billable = items.filter((item) => !item.is_optional);
    const subtotal = billable.reduce((sum, item) => sum + Number(item.qty || 0) * Number(item.unit_price || 0), 0);
    const vatRate = Number(detailsForm.querySelector('[name="vat_rate"]')?.value ?? quote.vat_rate);
    const discount = quote.discount_type === 'percent'
      ? subtotal * (Number(quote.discount_value) / 100)
      : quote.discount_type === 'amount' ? Number(quote.discount_value) : 0;
    const net = subtotal - discount;
    const vat = net * (vatRate / 100);
    const currency = detailsForm.querySelector('[name="currency"]')?.value ?? quote.currency;

    clear(totalsHost).append(el('table.totals-table', {}, [
      el('tbody', {}, [
        row(t('subtotal'), `${money(subtotal)} ${currency}`),
        discount ? row(t('discount'), `− ${money(discount)} ${currency}`) : null,
        row(t('net_amount'), `${money(net)} ${currency}`),
        row(`${t('vat')} ${vatRate}%`, `${money(vat)} ${currency}`),
        el('tr.grand', {}, [
          el('td', { text: t('grand_total') }),
          el('td.num', { text: `${money(net + vat)} ${currency}` }),
        ]),
      ].filter(Boolean)),
    ]));

    if (dirty) {
      totalsHost.append(el('div.alert.info.mt-1', {
        style: { marginBottom: 0 },
        text: getLang() === 'ar' ? 'يوجد تعديلات غير محفوظة' : 'Unsaved changes',
      }));
    }
    drawCalculator(subtotal, net);
  }

  function drawCalculator(subtotal, net) {
    if (!calcHost.isConnected && !calcHost.parentElement) return;
    const area = items
      .filter((item) => !item.is_optional && String(item.unit_en || '').toLowerCase().startsWith('m'))
      .reduce((sum, item) => sum + Number(item.qty || 0), 0);

    const inputs = [
      ['strand_price_ton', t('strand_price_ton'), 1],
      ['strand_kg_sqm', t('strand_kg_sqm'), 0.1],
      ['anchors_per_ton', t('anchors_per_ton'), 1],
      ['anchor_cost', t('anchor_cost'), 0.5],
      ['duct_cost_sqm', t('duct_cost_sqm'), 0.5],
      ['grout_cost_sqm', t('grout_cost_sqm'), 0.5],
      ['labour_cost_sqm', t('labour_cost_sqm'), 0.5],
      ['design_cost_sqm', t('design_cost_sqm'), 0.5],
      ['overhead_pct', t('overhead_pct'), 0.5],
      ['target_margin', t('target_margin'), 1],
    ];

    // Live cost maths, mirroring the server's model.
    const value = (key) => Number(quote[key] || 0);
    const strandTons = (area * value('strand_kg_sqm')) / 1000;
    const strandCost = strandTons * value('strand_price_ton');
    const anchorCount = strandTons * value('anchors_per_ton');
    const direct = strandCost
      + anchorCount * value('anchor_cost')
      + area * (value('duct_cost_sqm') + value('grout_cost_sqm') + value('labour_cost_sqm') + value('design_cost_sqm'));
    const cost = direct * (1 + value('overhead_pct') / 100);
    const marginAmount = net - cost;
    const marginPct = net > 0 ? (marginAmount / net) * 100 : 0;
    const costPerSqm = area > 0 ? cost / area : 0;
    const suggested = value('target_margin') < 100 ? costPerSqm / (1 - value('target_margin') / 100) : 0;

    clear(calcHost);

    const grid = el('div.grid', { style: { gridTemplateColumns: '1fr 1fr', gap: '.5rem' } });
    for (const [key, label, step] of inputs) {
      const node = field({
        name: key, label, type: 'number', value: quote[key], step, min: 0, disabled: readOnly,
      });
      node.querySelector('input').addEventListener('input', (event) => {
        quote[key] = event.target.value === '' ? 0 : Number(event.target.value);
        markDirty();
        recalcLocal();
      });
      grid.append(node);
    }
    calcHost.append(grid);

    const stat = (label, text, tone = '') => el('tr', {}, [
      el('td', { text: label }),
      el('td.num', { class: tone, text }),
    ]);

    calcHost.append(el('table.totals-table.mt-1', {}, [el('tbody', {}, [
      stat(t('area_sqm'), money(area, 0)),
      stat(t('strand_tons'), strandTons.toFixed(2)),
      stat(t('anchor_count'), String(Math.ceil(anchorCount))),
      stat(t('direct_cost'), money(direct, 0)),
      stat(t('cost_per_sqm'), money(costPerSqm)),
      stat(t('price_per_sqm'), area > 0 ? money(net / area) : '—'),
      stat(t('suggested_price'), suggested ? money(suggested) : '—'),
      stat(t('margin_amount'), money(marginAmount, 0)),
      stat(t('margin'), `${marginPct.toFixed(1)}%`),
    ])]));

    // Labour the client is supplying should not also be in our cost, or the
    // offer quietly carries a price for men we are not paying.
    if (quote.labour_scope === 'client' && value('labour_cost_sqm') > 0) {
      calcHost.append(el('div.alert.warn.mt-1', {
        style: { marginBottom: 0 }, text: t('labour_priced_warning'),
      }));
    }

    if (net > 0 && marginAmount < 0) {
      calcHost.append(el('div.alert.danger.mt-1', { style: { marginBottom: 0 }, text: t('below_cost_warning') }));
    } else if (net > 0 && marginPct < value('target_margin')) {
      calcHost.append(el('div.alert.warn.mt-1', { style: { marginBottom: 0 }, text: t('below_target_warning') }));
    }
    void subtotal;
  }

  const row = (label, value) => el('tr', {}, [el('td', { text: label }), el('td.num', { text: value })]);

  function markDirty() {
    if (dirty) return;
    dirty = true;
    drawStatusBar();
    recalcLocal();
  }

  // ---- status bar & actions ---------------------------------------------
  function drawStatusBar() {
    clear(statusHost).append(
      quoteStatusBadge(quote.status),
      el('span.badge.grey', { text: `${t('valid_until')} ${formatDate(quote.valid_until)}` }),
    );

    if (!readOnly) {
      statusHost.append(el('button.btn', {
        type: 'button',
        class: dirty ? '' : 'btn-secondary',
        text: t('save'),
        disabled: !dirty,
        onclick: save,
      }));
    }

    statusHost.append(
      el('button.btn.btn-secondary', {
        type: 'button', onclick: () => doPrint('ar'),
      }, [icon('print', 15), t('print_ar')]),
      el('button.btn.btn-secondary', {
        type: 'button', onclick: () => doPrint('en'),
      }, [icon('print', 15), t('print_en')]),
      // The cost comparison study that goes to the owner behind this offer.
      el('button.btn.btn-secondary', {
        type: 'button', onclick: () => navigate(`study/${quote.id}`),
      }, [icon('analytics', 15), t('study')]),
    );

    if (!readOnly) statusHost.append(actionsMenu());
  }

  function actionsMenu() {
    const wrap = el('div.row');
    const statusActions = [
      ['sent', t('mark_sent'), 'btn-secondary'],
      ['approved', t('mark_approved'), 'btn-success'],
      ['rejected', t('mark_rejected'), 'btn-danger'],
    ];
    for (const [status, label, cls] of statusActions) {
      if (quote.status === status) continue;
      if (status !== 'sent' && quote.status === 'draft') continue;
      wrap.append(el(`button.btn.btn-sm.${cls}`, {
        type: 'button', text: label,
        onclick: () => changeStatus(status),
      }));
    }
    wrap.append(el('button.btn.btn-sm.btn-secondary', {
      type: 'button', title: t('create_revision'), text: t('create_revision'),
      onclick: async () => {
        try {
          const { quotation } = await api.reviseQuotation(quote.id);
          toast(t('saved'), 'success');
          navigate(`quote/${quotation.id}`);
        } catch (error) { toastError(error); }
      },
    }));
    wrap.append(el('button.btn.btn-sm.btn-secondary', {
      type: 'button', title: t('duplicate'),
      onclick: async () => {
        try {
          const { quotation } = await api.duplicateQuotation(quote.id);
          toast(t('saved'), 'success');
          navigate(`quote/${quotation.id}`);
        } catch (error) { toastError(error); }
      },
    }, [icon('copy', 13)]));
    if (canSeeAll()) {
      wrap.append(el('button.btn.btn-sm.btn-danger', {
        type: 'button', title: t('delete'),
        onclick: async () => {
          if (!await confirmDialog(t('confirm_delete'))) return;
          try {
            await api.deleteQuotation(quote.id);
            toast(t('deleted'), 'success');
            navigate('quotations');
          } catch (error) { toastError(error); }
        },
      }, [icon('trash', 13)]));
    }
    return wrap;
  }

  async function changeStatus(status) {
    let reason = null;
    if (status === 'rejected') {
      reason = await askReason();
      if (reason === null) return;
    }
    try {
      const result = await api.setQuotationStatus(quote.id, status, reason);
      quote = { ...quote, ...result.quotation };
      toast(t('saved'), 'success');
      drawStatusBar();
    } catch (error) { toastError(error); }
  }

  function askReason() {
    return new Promise((resolve) => {
      const form = el('form', { onsubmit: (e) => e.preventDefault() }, [
        field({
          name: 'reason', label: t('reject_reason'), type: 'select',
          options: optionsFrom(['price', 'timing', 'competitor', 'scope', 'no_budget', 'no_response', 'other'], 'reason_'),
        }),
      ]);
      openModal({
        title: t('mark_rejected'),
        body: form,
        footer: (close) => el('div.row', {}, [
          el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: () => { close(); resolve(null); } }),
          el('button.btn.btn-danger', {
            type: 'button', text: t('save'),
            onclick: () => { const { reason } = readForm(form); close(); resolve(reason || 'other'); },
          }),
        ]),
        onClose: () => resolve(null),
      });
    });
  }

  async function save() {
    const details = readForm(detailsForm);
    const payload = {
      ...details,
      items: items.map((item, index) => ({ ...item, sort_order: index })),
      scope, payment_terms: paymentTerms, conditions,
      strand_price_ton: quote.strand_price_ton,
      strand_kg_sqm: quote.strand_kg_sqm,
      anchors_per_ton: quote.anchors_per_ton,
      notes_en: quote.notes_en,
      notes_ar: quote.notes_ar,
      // The cost model is only sent by someone who was shown it; otherwise the
      // rates already on the quotation would be saved back as blanks.
      ...(canSeeCost() ? {
        anchor_cost: quote.anchor_cost,
        duct_cost_sqm: quote.duct_cost_sqm,
        grout_cost_sqm: quote.grout_cost_sqm,
        labour_cost_sqm: quote.labour_cost_sqm,
        design_cost_sqm: quote.design_cost_sqm,
        overhead_pct: quote.overhead_pct,
        target_margin: quote.target_margin,
      } : {}),
    };
    try {
      const result = await api.updateQuotation(quote.id, payload);
      quote = { ...result.quotation, items: result.quotation.items };
      breakdown = result.breakdown;
      items = quote.items.map((item) => ({ ...item }));
      dirty = false;
      toast(t('saved'), 'success');
      // Only when it really changed, so a redraw does not close the sections
      // the engineer had opened.
      if (JSON.stringify(result.quotation.scope) !== JSON.stringify(scope)) {
        scope = result.quotation.scope;
        drawScope();
      }
      drawItems();
      drawStatusBar();
      recalcLocal();
    } catch (error) { toastError(error); }
  }

  async function doPrint(lang) {
    if (dirty && !await confirmDialog(
      getLang() === 'ar'
        ? 'يوجد تعديلات غير محفوظة. هل تريد الحفظ قبل الطباعة؟'
        : 'You have unsaved changes. Save before printing?',
      { danger: false, confirmLabel: t('save') },
    )) {
      // Printing anyway prints the last saved version.
    } else if (dirty) {
      await save();
    }
    try {
      const document = await api.quotationDocument(quote.id);
      printQuotation(document, lang);
    } catch (error) { toastError(error); }
  }

  // ---- scope editor ------------------------------------------------------
  function scopeCard() {
    const body = el('div.card-body');
    const card = el('div.card', {}, [
      el('div.card-header', {}, [
        el('h3', { text: t('templates') }),
        el('div.spacer'),
        el('span.tiny.muted', { text: getLang() === 'ar' ? 'أزل علامة أي بند لاستبعاده من العرض' : 'Untick any clause to drop it from this offer' }),
      ]),
      body,
    ]);

    for (const [key, labelKey] of SCOPE_SECTIONS) {
      const section = scope?.[key];
      if (!section) continue;
      const list = el('div', { style: { paddingInlineStart: '.4rem' } });
      section.items.forEach((entry, index) => {
        const box = el('input', { type: 'checkbox', disabled: readOnly });
        box.checked = entry.enabled !== false;
        box.addEventListener('change', () => {
          scope[key].items[index].enabled = box.checked;
          markDirty();
        });
        list.append(el('label.checkbox', { style: { alignItems: 'flex-start', marginBottom: '.3rem' } }, [
          box,
          el('span.small', { text: getLang() === 'ar' ? entry.ar : entry.en }),
        ]));
      });
      body.append(el('details', { style: { marginBottom: '.5rem' } }, [
        el('summary', { style: { cursor: 'pointer', fontWeight: '700', padding: '.3rem 0' }, text: t(labelKey) }),
        list,
      ]));
    }
    return card;
  }

  // ---- payment terms & conditions ---------------------------------------
  function termsCard() {
    const paymentHost = el('div');
    const conditionHost = el('div');

    const drawPayments = () => {
      clear(paymentHost);
      paymentTerms.forEach((term, index) => {
        const pct = el('input.num', { type: 'number', min: '0', max: '100', step: '5', style: { width: '80px' }, disabled: readOnly });
        pct.value = term.pct;
        pct.addEventListener('input', () => { paymentTerms[index].pct = Number(pct.value || 0); markDirty(); drawTotalPct(); });

        const text = el('input', { type: 'text', disabled: readOnly, dir: getLang() === 'ar' ? 'rtl' : 'ltr' });
        text.value = getLang() === 'ar' ? term.ar : term.en;
        text.addEventListener('input', () => {
          paymentTerms[index][getLang() === 'ar' ? 'ar' : 'en'] = text.value;
          markDirty();
        });

        paymentHost.append(el('div.row', { style: { marginBottom: '.35rem' } }, [
          pct, el('span', { text: '%' }), text,
          readOnly ? null : el('button.btn.btn-sm.btn-danger', {
            type: 'button', onclick: () => { paymentTerms.splice(index, 1); drawPayments(); markDirty(); },
          }, [icon('trash', 12)]),
        ].filter(Boolean)));
      });
      drawTotalPct();
    };

    const totalPct = el('div.tiny');
    const drawTotalPct = () => {
      const sum = paymentTerms.reduce((acc, term) => acc + Number(term.pct || 0), 0);
      totalPct.textContent = `${t('total')}: ${sum}%`;
      totalPct.style.color = sum === 100 ? 'var(--ok-700)' : 'var(--danger-700)';
      totalPct.style.fontWeight = '700';
    };

    const drawConditions = () => {
      clear(conditionHost);
      conditions.forEach((condition, index) => {
        const text = el('textarea', { rows: 2, disabled: readOnly, dir: getLang() === 'ar' ? 'rtl' : 'ltr' });
        text.value = getLang() === 'ar' ? condition.ar : condition.en;
        text.addEventListener('input', () => {
          conditions[index][getLang() === 'ar' ? 'ar' : 'en'] = text.value;
          markDirty();
        });
        conditionHost.append(el('div.row', { style: { marginBottom: '.35rem', alignItems: 'flex-start' } }, [
          text,
          readOnly ? null : el('button.btn.btn-sm.btn-danger', {
            type: 'button', onclick: () => { conditions.splice(index, 1); drawConditions(); markDirty(); },
          }, [icon('trash', 12)]),
        ].filter(Boolean)));
      });
    };

    drawPayments();
    drawConditions();

    return el('div.card', {}, [
      el('div.card-header', {}, [el('h3', { text: `${t('payment_terms')} · ${t('conditions')}` })]),
      el('div.card-body', {}, [
        el('h4', { text: t('payment_terms') }),
        paymentHost,
        totalPct,
        readOnly ? null : el('button.btn.btn-sm.btn-secondary.mt-1', {
          type: 'button', text: t('add'),
          onclick: () => { paymentTerms.push({ pct: 0, en: '', ar: '' }); drawPayments(); markDirty(); },
        }),
        el('h4.mt-2', { text: t('conditions') }),
        conditionHost,
        readOnly ? null : el('button.btn.btn-sm.btn-secondary', {
          type: 'button', text: t('add'),
          onclick: () => { conditions.push({ en: '', ar: '' }); drawConditions(); markDirty(); },
        }),
        el('h4.mt-2', { text: t('notes') }),
        (() => {
          const notes = el('textarea', { rows: 3, disabled: readOnly, dir: getLang() === 'ar' ? 'rtl' : 'ltr' });
          notes.value = (getLang() === 'ar' ? quote.notes_ar : quote.notes_en) || '';
          notes.addEventListener('input', () => {
            quote[getLang() === 'ar' ? 'notes_ar' : 'notes_en'] = notes.value;
            markDirty();
          });
          return notes;
        })(),
      ].filter(Boolean)),
    ]);
  }

  drawStatusBar();
  recalcLocal();
  void breakdown;
  return page;
}
