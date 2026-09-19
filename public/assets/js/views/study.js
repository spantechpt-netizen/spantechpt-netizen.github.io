/**
 * The cost comparison study behind a quotation.
 *
 * The engineer fills in what the project would otherwise have been built as,
 * the rates in that market, and what the lighter building saves underneath and
 * on the programme. The figures recompute on the server as they type, so what
 * is on screen is what the owner will read.
 */
import { api } from '../api.js';
import { t, pick, getLang, money, formatDateTime } from '../i18n.js';
import { el, clear, icon, field, readForm, toast, toastError, confirmDialog } from '../ui.js';
import { barChart } from '../charts.js';
import { can } from '../app.js';
import { printStudyDesign, STUDY_DESIGNS } from './study-designs.js';

const KINDS = ['original', 'post_tension'];

/** Debounced so a number being typed does not fire a request per keystroke. */
function debounce(fn, ms = 450) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

export async function render({ params, navigate }) {
  const quotationId = Number(params[0]);
  if (!quotationId) return el('div.empty', { text: t('not_found') });

  const page = el('div');
  // The toolbar is mounted first so it stays at the top of the screen; it is
  // filled in once the study has loaded.
  const toolbarHost = el('div');
  const host = el('div');
  page.append(toolbarHost, host);
  clear(host).append(el('div.loading-page', { text: t('loading') }));

  let quote;
  let data;
  try {
    const [quoteRes, studyRes] = await Promise.all([
      api.quotation(quotationId),
      api.study(quotationId),
    ]);
    quote = quoteRes.quotation;
    data = studyRes;
  } catch (error) {
    clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    return page;
  }

  const readOnly = !can('quotations.edit');
  const currency = quote.currency;
  const fmt = (value) => `${money(value)} ${currency}`;

  // -------------------------------------------------------------- structure
  const summary = el('div');
  const form = el('form', { onsubmit: (event) => event.preventDefault() });
  const drawingsHost = el('div');

  toolbarHost.append(el('div.toolbar', {}, [
    el('button.btn.btn-secondary', {
      type: 'button', onclick: () => navigate(`quote/${quotationId}`),
    }, [icon('back', 15), t('back_to_quote')]),
    el('div.spacer'),
    designSelect(),
    el('button.btn.btn-secondary', {
      type: 'button', onclick: () => printDesign('ar'),
    }, [icon('print', 15), t('print_ar')]),
    el('button.btn.btn-primary', {
      type: 'button', onclick: () => printDesign('en'),
    }, [icon('print', 15), t('print_en')]),
  ]));

  /** Which of the six designs the study prints in; saved at once, on its own. */
  function designSelect() {
    const lang = getLang();
    const current = ((data.study.input && data.study.input.deck) || {}).template || 'deck';
    const select = el('select', {
      title: t('design_hint'),
      style: { width: 'auto', minWidth: '11rem' },
      disabled: readOnly,
      onchange: async () => {
        const template = select.value;
        try {
          // Only the choice travels: the wording saved from the document stays as it is.
          const { deck: saved } = await api.saveDeck(quotationId, { template });
          data.study.input.deck = saved;
          toast(t('saved'));
        } catch (error) {
          select.value = current;
          toastError(error);
        }
      },
    }, STUDY_DESIGNS.map((design) => el('option', {
      value: design.id, text: `${t('design_style')}: ${design[lang] || design.en}`, selected: design.id === current,
    })));
    return select;
  }

  async function printDesign(lang) {
    try {
      const payload = await documentPayload();
      printStudyDesign(payload, lang, (payload.study.input.deck && payload.study.input.deck.template) || 'deck');
    } catch (e) { toastError(e); }
  }

  clear(host).append(
    el('div.grid.grid-2', { style: { alignItems: 'start', gap: '1rem' } }, [
      el('div.card', {}, [
        el('div.card-head', {}, [el('b', { text: t('study_inputs') })]),
        el('div.card-body', {}, [form]),
      ]),
      el('div', {}, [
        el('div.card', {}, [
          el('div.card-head', {}, [el('b', { text: t('study_result') })]),
          el('div.card-body', {}, [summary]),
        ]),
        el('div.card', { style: { marginTop: '1rem' } }, [
          el('div.card-head', {}, [el('b', { text: t('study_drawings') })]),
          el('div.card-body', {}, [drawingsHost]),
        ]),
      ]),
    ]),
  );

  // ------------------------------------------------------------------- form
  const input = () => data.study.input;

  function buildForm() {
    clear(form);
    const s = input();
    const numberField = (name, label, extra = {}) => field({
      name, label, type: 'number', value: s[name], step: extra.step || 'any',
      min: 0, hint: extra.hint, disabled: readOnly,
    });

    form.append(
      el('h3.sec', { text: t('study_project') }),
      el('div.grid.grid-2', {}, [
        field({
          name: 'system', label: t('study_system'), type: 'select', value: s.system,
          options: data.systems.map((x) => ({ value: x.key, label: pick(x, 'label') })),
          hint: t('study_system_hint'), disabled: readOnly,
        }),
        numberField('floors', t('study_floors')),
        numberField('area_sqm', t('study_area'), { hint: t('study_area_hint') }),
      ]),

      el('h3.sec', { text: t('study_slabs') }),
      el('div.grid.grid-2', {}, [
        numberField('conv_thickness_mm', t('study_conv_thickness')),
        numberField('pt_thickness_mm', t('study_pt_thickness')),
        numberField('conv_rebar_kg_m3', t('study_conv_rebar')),
        numberField('pt_rebar_kg_m3', t('study_pt_rebar')),
      ]),

      el('h3.sec', { text: t('study_rates') }),
      el('div.grid.grid-2', {}, [
        numberField('concrete_rate_m3', `${t('study_concrete_rate')} (${currency})`),
        numberField('rebar_rate_ton', `${t('study_rebar_rate')} (${currency})`),
        numberField('formwork_rate_sqm', `${t('study_formwork_rate')} (${currency})`),
        numberField('pt_rate_sqm', `${t('study_pt_rate')} (${currency})`, { hint: t('study_pt_rate_hint') }),
      ]),

      el('h3.sec', { text: t('study_beyond') }),
      el('p.hint', { text: t('study_beyond_hint'), style: { marginTop: '-.4rem' } }),
      el('div.grid.grid-2', {}, [
        numberField('foundation_saving_sqm', `${t('study_foundation_saving')} (${currency})`),
        numberField('day_value', `${t('study_day_value')} (${currency})`),
        numberField('conv_cycle_days', t('study_conv_cycle')),
        numberField('pt_cycle_days', t('study_pt_cycle')),
      ]),

      field({
        name: 'notes_ar', label: t('study_notes_ar'), type: 'textarea', rows: 3,
        value: s.notes_ar || '', disabled: readOnly,
      }),
      field({
        name: 'notes_en', label: t('study_notes_en'), type: 'textarea', rows: 3,
        value: s.notes_en || '', disabled: readOnly,
      }),
    );
  }

  const save = debounce(async () => {
    if (readOnly) return;
    try {
      const values = readForm(form);
      const res = await api.saveStudy(quotationId, { ...input(), ...values });
      data.study = res.study;
      drawSummary();
    } catch (error) { toastError(error); }
  });

  form.addEventListener('input', save);

  // ---------------------------------------------------------------- summary
  function drawSummary() {
    const s = data.study;
    clear(summary);

    if (!s.complete) {
      summary.append(el('div.alert.warn', {
        text: `${t('study_incomplete')} ${s.missing.map((m) => t(`study_${m}`) || m).join('، ')}`,
      }));
    }

    const row = (label, conv, pt, bold = false) => el('tr', {}, [
      el('td', { text: label, style: bold ? { fontWeight: '700' } : {} }),
      el('td.num', { text: fmt(conv), style: bold ? { fontWeight: '700' } : {} }),
      el('td.num', { text: fmt(pt), style: bold ? { fontWeight: '700' } : {} }),
    ]);

    summary.append(el('div.scroll-x', {}, [
      el('table.table', {}, [
        el('thead', {}, [el('tr', {}, [
          el('th', { text: `${t('study_per_sqm')}` }),
          el('th.num', { text: pick(s.system, 'label') }),
          el('th.num', { text: t('study_pt') }),
        ])]),
        el('tbody', {}, [
          row(t('study_concrete'), s.conventional.concrete, s.post_tension.concrete),
          row(t('study_rebar'), s.conventional.rebar, s.post_tension.rebar),
          row(t('study_formwork'), s.conventional.formwork, s.post_tension.formwork),
          row(t('study_pt_package'), s.conventional.post_tension, s.post_tension.post_tension),
          row(t('total'), s.conventional.per_sqm, s.post_tension.per_sqm, true),
        ]),
      ]),
    ]));

    // The slab-only answer and the whole-building answer, never merged.
    const slabTone = s.saving.favours_pt_on_slab_alone ? 'ok' : 'warn';
    const totalTone = s.saving.favours_pt ? 'ok' : 'warn';

    summary.append(el('div.kpi-grid', { style: { marginTop: '1rem' } }, [
      el(`div.kpi.${slabTone}`, {}, [
        el('div.label', { text: t('study_slab_only') }),
        el('div.value.num', { text: fmt(s.saving.slab_total) }),
      ]),
      el(`div.kpi.${totalTone}`, {}, [
        el('div.label', { text: `${t('study_whole_building')} (${s.saving.pct}%)` }),
        el('div.value.num', { text: fmt(s.saving.total) }),
      ]),
    ]));

    if (!s.saving.favours_pt_on_slab_alone && s.complete) {
      summary.append(el('div.alert.warn', { style: { marginTop: '.6rem' } }, [
        el('div', { text: t('study_slab_negative') }),
      ]));
    }

    summary.append(
      el('h3.sec', { text: t('study_breakdown') }),
      barChart({
        data: [
          { label: t('study_slab_only'), value: s.saving.slab_total },
          { label: t('study_foundation_saving'), value: s.saving.foundation_total },
          { label: t('study_programme'), value: s.saving.programme_total },
        ],
        format: (v) => fmt(v),
      }),
    );

    const b = s.benefits;
    summary.append(
      el('h3.sec', { text: t('study_benefits') }),
      el('table.table', {}, [el('tbody', {}, [
        el('tr', {}, [el('td', { text: t('study_concrete_saved') }), el('td.num', { text: `${money(b.concrete_saved_m3, 0)} m³` })]),
        el('tr', {}, [el('td', { text: t('study_rebar_saved') }), el('td.num', { text: `${money(b.rebar_saved_ton, 1)} t` })]),
        el('tr', {}, [el('td', { text: t('study_weight_saved') }), el('td.num', { text: `${money(b.weight_saved_ton, 0)} t` })]),
        el('tr', {}, [el('td', { text: t('study_thickness_saved') }), el('td.num', { text: `${money(b.thickness_saved_mm, 0)} mm` })]),
        el('tr', {}, [el('td', { text: t('study_height_saved') }), el('td.num', { text: `${money(b.height_saved_mm, 0)} mm` })]),
        el('tr', {}, [el('td', { text: t('study_days_saved') }), el('td.num', { text: `${money(b.days_saved, 0)} ${t('days')}` })]),
      ])]),
    );
  }

  // --------------------------------------------------------------- drawings
  function drawDrawings() {
    clear(drawingsHost);
    drawingsHost.append(el('p.hint', { text: t('study_drawings_hint') }));

    for (const kind of KINDS) {
      const mine = data.drawings.filter((d) => d.kind === kind);
      drawingsHost.append(el('h3.sec', { text: t(`study_kind_${kind}`) }));

      const grid = el('div.grid.grid-2', { style: { gap: '.6rem' } });
      for (const drawing of mine) {
        grid.append(el('div.card', { style: { padding: '.4rem' } }, [
          el('img', {
            src: drawing.url, alt: pick(drawing, 'caption') || '',
            style: { width: '100%', height: '110px', objectFit: 'cover', borderRadius: '3px' },
          }),
          el('input.input', {
            type: 'text', value: pick(drawing, 'caption') || '',
            placeholder: t('study_caption'), disabled: readOnly,
            style: { marginTop: '.3rem', fontSize: '12px' },
            onchange: async (event) => {
              const key = getLang() === 'ar' ? 'caption_ar' : 'caption_en';
              try {
                const res = await api.updateDrawing(quotationId, drawing.id, { [key]: event.target.value });
                data.drawings = res.drawings;
              } catch (error) { toastError(error); }
            },
          }),
          readOnly ? null : el('button.btn.btn-sm.btn-ghost', {
            type: 'button', text: t('delete'),
            onclick: async () => {
              if (!await confirmDialog(t('confirm_delete'))) return;
              try {
                const res = await api.deleteDrawing(quotationId, drawing.id);
                data.drawings = res.drawings;
                drawDrawings();
              } catch (error) { toastError(error); }
            },
          }),
        ]));
      }
      if (!mine.length) grid.append(el('div.empty', { text: t('study_no_drawings') }));
      drawingsHost.append(grid);

      if (!readOnly) drawingsHost.append(uploadButton(kind));
    }
  }

  function uploadButton(kind) {
    const picker = el('input', {
      type: 'file', accept: 'image/png,image/jpeg,image/webp',
      style: { display: 'none' },
      onchange: async (event) => {
        const files = [...(event.target.files || [])];
        event.target.value = '';
        for (const file of files) {
          try {
            const res = await api.uploadDrawing(quotationId, kind, file);
            data.drawings = res.drawings;
          } catch (error) { toastError(error); }
        }
        drawDrawings();
        toast(t('saved'), 'success');
      },
    });
    return el('div', { style: { marginTop: '.5rem' } }, [
      picker,
      el('button.btn.btn-sm.btn-secondary', {
        type: 'button', onclick: () => picker.click(),
      }, [icon('plus', 14), t('study_upload')]),
    ]);
  }

  // --------------------------------------------------------- print payload
  async function documentPayload() {
    const doc = await api.quotationDocument(quotationId);
    return {
      study: data.study,
      drawings: data.drawings,
      // The deck saves the wording the engineer edits on it straight back to
      // this quotation, so it needs to know which one it is and where to send.
      quotation_id: quotationId,
      origin: window.location.origin,
      quotation: doc.quotation,
      company: doc.company,
      branch: doc.branch,
      country: doc.country,
      generated_at: formatDateTime(new Date().toISOString()),
    };
  }

  buildForm();
  drawSummary();
  drawDrawings();
  return page;
}
