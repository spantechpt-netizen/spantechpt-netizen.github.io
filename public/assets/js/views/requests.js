/**
 * Incoming requests — anything that looks like it needs someone. Most arrive
 * at the company mailbox on their own; a WhatsApp message or a phone call is
 * pasted in and joins the same queue. The manager triages here and hands each
 * to an engineer; converting one creates the customer and opportunity from
 * what was read out of the message.
 */
import { api } from '../api.js';
import { t, pick, getLang, money, formatDateTime } from '../i18n.js';
import {
  el, clear, icon, field, readForm, openModal, confirmDialog,
  toast, toastError, optionsFrom, blankOption,
} from '../ui.js';
import { can, state, shared } from '../app.js';
import { refresh as refreshBell } from '../notify.js';

const STATUS_CLASS = { new: 'amber', assigned: 'blue', converted: 'green', dismissed: 'grey' };
const PROJECT_TYPES = ['tower', 'school', 'mall', 'villa', 'rest_house', 'admin', 'hospital', 'parking', 'industrial', 'other'];
const COUNTRIES = ['SA', 'EG', 'QA'];

const view = { status: '' };

export async function render({ params, navigate }) {
  const page = el('div');
  const host = el('div');
  const openId = params[0] ? Number(params[0]) : null;

  const tiles = el('div.kpi-grid');
  page.append(tiles);

  const tab = (status, label) => el('button', {
    type: 'button',
    class: view.status === status ? 'active' : '',
    text: label,
    onclick: (event) => {
      view.status = status;
      for (const sibling of event.currentTarget.parentElement.children) sibling.classList.remove('active');
      event.currentTarget.classList.add('active');
      load();
    },
  });

  page.append(el('div.toolbar', {}, [
    el('div.segmented', {}, [
      tab('new', t('req_new')),
      tab('assigned', t('req_assigned')),
      tab('converted', t('req_converted')),
      tab('', t('all')),
    ]),
    el('div.spacer'),
    el('button.btn.btn-primary', {
      type: 'button',
      onclick: () => openCapture(load, navigate),
    }, [icon('plus', 15), t('capture_add')]),
    can('mail.manage') ? el('button.btn.btn-secondary', {
      type: 'button',
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const { results } = await api.syncAllMail();
          const queued = Object.values(results || {}).reduce((sum, r) => sum + (r.queued || 0), 0);
          toast(queued ? `${queued} ${t('req_new')}` : t('check_done'), 'success');
          await load();
          refreshBell({ silent: true });
        } catch (error) { toastError(error); }
        button.disabled = false;
      },
    }, [icon('refresh', 15), t('fetch_mail_now')]) : null,
  ]));

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [host])]));

  // The default tab depends on the job: triagers start on the new queue.
  if (!view.status) view.status = can('mail.triage') ? 'new' : 'assigned';

  async function load() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { requests, counts } = await api.mailRequests({ status: view.status || undefined });
      drawTiles(counts);
      clear(host);
      if (!requests.length) {
        host.append(el('div.empty', {}, [icon('inbox', 40), el('div', { text: t('no_requests') })]));
        return;
      }
      for (const request of requests) host.append(row(request, load, navigate));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  function drawTiles(counts) {
    clear(tiles).append(
      kpi(counts.new ? 'warn' : 'ok', t('req_new'), counts.new),
      kpi('', t('req_assigned'), counts.assigned),
      kpi('ok', t('req_converted'), counts.converted),
    );
  }

  await load();
  if (openId) setTimeout(() => openRequest(openId, load, navigate), 0);
  // Arrived here from the phone's share sheet: open the capture form on it.
  if (shared.pending) {
    const payload = shared.pending;
    shared.pending = null;
    setTimeout(() => openCapture(load, navigate, payload), 0);
  }
  return page;
}

const kpi = (tone, label, value) => el(`div.kpi${tone ? `.${tone}` : ''}`, {}, [
  el('div.label', { text: label }),
  el('div.value.num', { text: String(value ?? 0) }),
]);

function row(request, reload, navigate) {
  const extraction = request.extraction || {};
  const project = extraction.project || {};
  const summary = getLang() === 'ar' ? request.summary_ar : request.summary_en;

  return el(`div.req-row${request.status === 'new' ? '.is-new' : ''}`, {
    onclick: () => openRequest(request.id, reload, navigate),
  }, [
    el('div', { style: { flex: '1', minWidth: '0' } }, [
      el('div.row', { style: { gap: '.4rem', flexWrap: 'wrap' } }, [
        el('span.badge', { class: STATUS_CLASS[request.status] || 'grey', text: t(`req_${request.status}`) }),
        extraction.is_rfq ? el('span.badge.orange', { text: t('req_is_rfq') }) : null,
        extraction.mentions_post_tension ? el('span.badge.blue', { text: 'Post-Tension' }) : null,
        request.channel && request.channel !== 'email'
          ? el('span.badge.green', { text: t(`channel_${request.channel}`) }) : null,
        el('span.req-subject', { text: request.subject || '—' }),
      ]),
      el('div.tiny.muted', {
        text: `${request.from_name || ''} <${request.from_email || ''}> · ${formatDateTime(request.received_at)}`,
      }),
      summary
        ? el('div.small', { style: { marginTop: '.15rem' }, text: summary })
        : el('div.small.muted.truncate', { text: request.snippet || '' }),
      el('div.row', { style: { gap: '.35rem', marginTop: '.3rem', flexWrap: 'wrap' } }, [
        project.area_sqm ? el('span.badge.grey', { text: `${money(project.area_sqm, 0)} m²` }) : null,
        project.country ? el('span.badge.grey', { text: t(`country_${project.country}`) }) : null,
        project.type ? el('span.badge.grey', { text: t(`ptype_${project.type}`) }) : null,
        request.has_attachments ? el('span.badge.grey', { text: `📎 ${request.attachments.length}` }) : null,
        request.assignee_name ? el('span.badge.blue', { text: pick(request, 'assignee_name') }) : null,
      ]),
    ]),
    el('div', { style: { textAlign: 'center', minWidth: '58px' } }, [
      el('div.conf-ring', {
        class: request.confidence >= 70 ? 'high' : request.confidence >= 40 ? 'mid' : 'low',
        text: `${request.confidence}%`,
      }),
      el('div.tiny.muted', { text: t('req_confidence') }),
    ]),
  ]);
}

// ------------------------------------------------------------------ detail
async function openRequest(id, reload, navigate) {
  let data;
  try { data = await api.mailRequest(id); } catch (error) { return toastError(error); }
  const request = data.request;
  const extraction = request.extraction || {};

  const body = el('div');

  // --- the email itself
  body.append(el('div.card', { style: { marginBottom: '.8rem' } }, [
    el('div.card-header', {}, [
      el('div', {}, [
        el('b', { text: request.subject || '—' }),
        el('div.tiny.muted', {
          text: `${request.from_name || ''} <${request.from_email || ''}> · ${formatDateTime(request.received_at)}`,
        }),
      ]),
    ]),
    el('div.card-body', {}, [
      el('pre.mail-body', { text: request.body_text || request.snippet || '' }),
      request.attachments?.length ? el('div.row.wrap.mt-1', {}, [
        el('span.tiny.muted', { text: '📎' }),
        ...request.attachments.map((a) => el('span.badge.grey', { text: `${a.filename} (${Math.round(a.size / 1024)} KB)` })),
      ]) : null,
    ]),
  ]));

  // --- what was read out of it
  const summary = getLang() === 'ar' ? request.summary_ar : request.summary_en;
  if (summary) {
    body.append(el('div.alert.info', { text: summary }));
  }

  const matched = extraction.customer?.matched_id;
  if (matched) {
    body.append(el('div.alert.ok', {
      text: getLang() === 'ar'
        ? `العميل ده موجود عندنا بالفعل: ${extraction.customer.name || ''}`
        : `Matched an existing customer: ${extraction.customer.name || ''}`,
    }));
  }

  // --- the editable draft
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('h4', { text: t('req_draft') }),
    el('div.grid.grid-2', {}, [
      field({ name: 'customer_name', label: t('customer'), value: extraction.customer?.name || '', disabled: Boolean(matched) }),
      field({ name: 'contact_name', label: t('contact_name'), value: extraction.contact?.name || '' }),
      field({ name: 'contact_email', label: t('email'), value: extraction.contact?.email || request.from_email || '', dir: 'ltr' }),
      field({ name: 'contact_phone', label: t('mobile'), value: extraction.contact?.phones?.[0] || '', dir: 'ltr' }),
      field({ name: 'project_name', label: t('opportunity_title'), value: extraction.project?.name || request.subject || '' }),
      field({
        name: 'project_type', label: t('project_type'), type: 'select',
        value: extraction.project?.type || '',
        options: [blankOption(t('none')), ...optionsFrom(PROJECT_TYPES, 'ptype_')],
      }),
      field({ name: 'area_sqm', label: t('area_sqm'), type: 'number', value: extraction.project?.area_sqm || '', min: 0 }),
      field({
        name: 'country', label: t('country'), type: 'select',
        value: extraction.project?.country || extraction.customer?.country || 'SA',
        options: COUNTRIES.map((c) => ({ value: c, label: t(`country_${c}`) })),
      }),
      field({ name: 'city', label: t('city'), value: extraction.project?.city || '' }),
      can('mail.triage') ? field({
        name: 'owner_id', label: t('owner'), type: 'select',
        value: request.assigned_to || state.user.id,
        options: state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') })),
      }) : null,
    ]),
    el('div.tiny.muted', {
      text: `${t('req_source')}: ${extraction.source || 'heuristic'}${extraction.ai_model ? ` (${extraction.ai_model})` : ''}`
        + ` · ${t('req_confidence')} ${request.confidence}%`,
    }),
  ]);
  body.append(form);

  const { close } = openModal({
    title: `${t('req_detail')} #${request.id}`,
    size: 'wide',
    body,
    footer: (dismiss) => el('div.row', { style: { width: '100%', flexWrap: 'wrap' } }, [
      can('mail.triage') && request.status !== 'converted' ? el('button.btn.btn-sm.btn-secondary', {
        type: 'button', text: t('req_assign'),
        onclick: () => { dismiss(); openAssign(request, reload); },
      }) : null,
      can('mail.triage') ? el('button.btn.btn-sm.btn-secondary', {
        type: 'button', title: t('req_re_extract'),
        onclick: async (event) => {
          event.currentTarget.disabled = true;
          try {
            await api.reExtractMailRequest(request.id);
            dismiss();
            openRequest(request.id, reload, navigate);
          } catch (error) { toastError(error); }
        },
      }, [icon('refresh', 13)]) : null,
      el('button.btn.btn-sm.btn-danger', {
        type: 'button', text: t('req_dismiss'),
        onclick: async () => {
          if (!await confirmDialog(t('req_dismiss_confirm'), { confirmLabel: t('req_dismiss') })) return;
          try {
            await api.setMailRequestStatus(request.id, 'dismissed');
            toast(t('saved'), 'success');
            dismiss();
            reload();
            refreshBell({ silent: true });
          } catch (error) { toastError(error); }
        },
      }),
      el('div.spacer'),
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: dismiss }),
      request.status === 'converted'
        ? el('button.btn.btn-success', {
          type: 'button', text: t('req_open_opportunity'),
          onclick: () => { dismiss(); navigate('pipeline'); },
        })
        : el('button.btn', {
          type: 'button', text: t('req_convert'),
          onclick: async (event) => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
              const overrides = readForm(form);
              const ownerId = overrides.owner_id;
              delete overrides.owner_id;
              const result = await api.convertMailRequest(request.id, { overrides, owner_id: ownerId });
              toast(t('req_converted_ok'), 'success');
              dismiss();
              reload();
              refreshBell({ silent: true });
              void result;
            } catch (error) {
              toastError(error);
              button.disabled = false;
            }
          },
        }),
    ]),
  });
}

function openAssign(request, reload) {
  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    field({
      name: 'assigned_to', label: t('req_assign_to'), type: 'select',
      value: request.assigned_to || '',
      options: state.users
        .filter((u) => u.active && u.role !== 'viewer')
        .map((u) => ({ value: u.id, label: `${pick(u, 'name')} — ${t(`role_${u.role}`)}` })),
    }),
    field({ name: 'notes', label: t('notes'), type: 'textarea', rows: 3, value: request.notes || '' }),
  ]);

  openModal({
    title: t('req_assign'),
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          event.currentTarget.disabled = true;
          try {
            await api.assignMailRequest(request.id, readForm(form));
            toast(t('saved'), 'success');
            close();
            reload();
          } catch (error) {
            toastError(error);
            event.currentTarget.disabled = false;
          }
        },
      }),
    ]),
  });
}


// ---------------------------------------------------------------- capture
/**
 * Paste a request that arrived somewhere the CRM cannot read. Pre-fills from
 * `?text=` so the Android share sheet can hand a WhatsApp message straight in.
 */
export function openCapture(reload, navigate, prefill = {}) {
  const form = el('form.form-grid');
  form.append(
    el('p.hint', { text: t('capture_hint'), style: { gridColumn: '1 / -1', margin: '0 0 .2rem' } }),
    field({
      name: 'text', label: t('capture_text'), type: 'textarea', rows: 8, required: true,
      value: prefill.text || '', placeholder: t('capture_text_ph'),
    }),
    field({
      name: 'channel', label: t('capture_channel'), type: 'select',
      value: prefill.channel || 'whatsapp',
      options: [
        { value: 'whatsapp', label: t('capture_ch_whatsapp') },
        { value: 'phone', label: t('capture_ch_phone') },
        { value: 'other', label: t('capture_ch_other') },
      ],
    }),
    field({ name: 'from_name', label: t('capture_from_name'), value: prefill.from_name || '' }),
    field({
      name: 'from_phone', label: t('capture_from_phone'), dir: 'ltr',
      value: prefill.from_phone || '', hint: t('capture_from_phone_hint'),
    }),
  );
  // The message is the point, so give it the full width of the grid.
  form.firstElementChild.nextElementSibling.style.gridColumn = '1 / -1';

  // The footer sits outside the form element, so the button cannot be a plain
  // submit — it has to call the same handler the form's own submit does.
  let submitting = false;
  const save = el('button.btn.btn-primary', { type: 'button', text: t('capture_save') });

  const { close } = openModal({
    title: t('capture_title'),
    body: form,
    footer: (dismiss) => el('div.row', { style: { gap: '.5rem' } }, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: dismiss }),
      el('div.spacer'),
      save,
    ]),
  });

  async function submit() {
    if (submitting) return;
    const values = readForm(form);
    if (!String(values.text || '').trim()) return toast(t('capture_empty'), 'warning');

    submitting = true;
    save.disabled = true;
    try {
      const { request } = await api.captureRequest(values);
      close();
      toast(t('capture_done'), 'success');
      await reload?.();
      refreshBell({ silent: true });
      if (request?.id) openRequest(request.id, reload, navigate);
    } catch (error) {
      toastError(error);
      submitting = false;
      save.disabled = false;
    }
  }

  save.addEventListener('click', submit);
  // Ctrl/⌘+Enter sends it without reaching for the button — the message is
  // pasted into the textarea and the hands are already there.
  form.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
      event.preventDefault();
      submit();
    }
  });
  form.addEventListener('submit', (event) => { event.preventDefault(); submit(); });
}
