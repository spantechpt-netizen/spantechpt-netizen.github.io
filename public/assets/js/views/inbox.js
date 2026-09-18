import { api } from '../api.js';
import { t, pick, getLang, formatDateTime } from '../i18n.js';
import {
  el, clear, icon, field, readForm, openModal, confirmDialog,
  toast, toastError, initials,
} from '../ui.js';
import { can, state } from '../app.js';
import { refresh as refreshBell } from '../notify.js';

const view = { box: 'inbox' };

export async function render({ params, navigate }) {
  const page = el('div');
  const listHost = el('div');
  const openThreadId = params[0] ? Number(params[0]) : null;

  page.append(el('div.toolbar', {}, [
    el('div.segmented', {}, [
      el('button', {
        type: 'button', class: view.box === 'inbox' ? 'active' : '', text: t('inbox_tab'),
        onclick: (e) => switchBox('inbox', e.currentTarget),
      }),
      el('button', {
        type: 'button', class: view.box === 'sent' ? 'active' : '', text: t('sent_tab'),
        onclick: (e) => switchBox('sent', e.currentTarget),
      }),
    ]),
    el('div.spacer'),
    can('messages.send') ? el('button.btn', {
      type: 'button', onclick: () => openCompose(null, load),
    }, [icon('plus', 16), t('new_message')]) : null,
  ]));

  function switchBox(box, button) {
    view.box = box;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    load();
  }

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [listHost])]));

  async function load() {
    clear(listHost).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { messages } = await api.messages(view.box);
      clear(listHost);
      if (!messages.length) {
        listHost.append(el('div.empty', {}, [icon('mail', 40), el('div', { text: t('no_messages') })]));
        return;
      }
      for (const message of messages) listHost.append(messageRow(message, load));
    } catch (error) {
      clear(listHost).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await load();
  if (openThreadId) setTimeout(() => openThread(openThreadId, load, navigate), 0);
  return page;
}

function messageRow(message, reload) {
  const who = view.box === 'sent'
    ? `${t('sent_to')}: ${message.recipient_names || '—'}`
    : `${t('from')}: ${getLang() === 'ar' ? (message.sender_name_ar || message.sender_name) : message.sender_name}`;

  return el(`div.msg-row${message.is_read ? '' : '.is-unread'}`, {
    onclick: () => openThread(message.id, reload),
  }, [
    el('div.avatar', { text: initials(message.sender_name) }),
    el('div', { style: { flex: '1', minWidth: '0' } }, [
      el('div.row', { style: { gap: '.4rem' } }, [
        el('span.msg-subject', { text: message.subject || '—' }),
        message.reply_count > 0
          ? el('span.badge.grey', { text: `${message.reply_count} ${t('replies')}` })
          : null,
      ]),
      el('div.msg-preview.truncate', { text: message.body }),
      el('div.tiny.muted', { text: `${who} · ${formatDateTime(message.created_at)}` }),
    ]),
  ]);
}

async function openThread(id, reload, navigate) {
  let data;
  try { data = await api.messageThread(id); } catch (error) { return toastError(error); }
  const { message, replies, recipients } = data;

  const body = el('div');

  const bubble = (entry, isRoot) => el('div.msg-bubble', {}, [
    el('div.row', { style: { gap: '.4rem', marginBottom: '.2rem' } }, [
      el('div.avatar', { style: { width: '26px', height: '26px', fontSize: '.7rem' },
        text: initials(entry.sender_name) }),
      el('b.small', { text: getLang() === 'ar' ? (entry.sender_name_ar || entry.sender_name) : entry.sender_name }),
      el('span.spacer'),
      el('span.tiny.muted', { text: formatDateTime(entry.created_at) }),
    ]),
    el('div.msg-text', { text: entry.body }),
    isRoot && entry.entity ? el('button.btn.btn-sm.btn-ghost', {
      type: 'button',
      text: `${t('attach_record')}: ${entry.entity}`,
      onclick: () => {
        const routes = {
          quotation: `quote/${entry.entity_id}`, customer: 'customers',
          opportunity: 'pipeline', activity: 'activities',
        };
        close();
        (navigate || ((h) => { location.hash = `#/${h}`; }))(routes[entry.entity] || 'dashboard');
      },
    }) : null,
  ]);

  body.append(bubble(message, true));
  for (const reply of replies) body.append(bubble(reply, false));

  body.append(el('div.tiny.muted.mt-1', {
    text: `${t('sent_to')}: ${recipients.map((r) => pick(r, 'name')).join('، ')}`,
  }));

  const replyBox = el('textarea', { rows: 3, placeholder: t('reply_placeholder') });
  body.append(el('div.mt-2', {}, [
    el('h4', { text: t('reply') }),
    replyBox,
  ]));

  const { close } = openModal({
    title: message.subject || t('messages'),
    size: 'wide',
    body,
    footer: (dismiss) => el('div.row', { style: { width: '100%' } }, [
      message.sender_id === state.user.id ? el('button.btn.btn-sm.btn-danger', {
        type: 'button', text: t('delete'),
        onclick: async () => {
          if (!await confirmDialog(t('confirm_delete'))) return;
          try {
            await api.deleteMessage(message.id);
            toast(t('deleted'), 'success');
            dismiss();
            reload?.();
          } catch (error) { toastError(error); }
        },
      }) : null,
      el('div.spacer'),
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: dismiss }),
      can('messages.send') ? el('button.btn', {
        type: 'button', text: t('send'),
        onclick: async (event) => {
          const text = replyBox.value.trim();
          if (!text) return;
          const button = event.currentTarget;
          button.disabled = true;
          try {
            await api.sendMessage({ parent_id: message.id, body: text });
            toast(t('message_sent'), 'success');
            dismiss();
            reload?.();
            refreshBell({ silent: true });
          } catch (error) {
            toastError(error);
            button.disabled = false;
          }
        },
      }) : null,
    ]),
  });

  // Reading the thread clears its unread badge.
  refreshBell({ silent: true });
  reload?.();
}

export function openCompose(preset, onSent) {
  const colleagues = state.users.filter((u) => u.active && u.id !== state.user.id);
  const picker = el('div.recipient-picker');
  const chosen = new Set(preset?.recipient_ids || []);

  for (const colleague of colleagues) {
    const box = el('input', { type: 'checkbox' });
    box.checked = chosen.has(colleague.id);
    box.addEventListener('change', () => {
      if (box.checked) chosen.add(colleague.id);
      else chosen.delete(colleague.id);
    });
    picker.append(el('label.checkbox.recipient-chip', {}, [
      box,
      el('span', { text: `${pick(colleague, 'name')} — ${t(`role_${colleague.role}`)}` }),
    ]));
  }

  const form = el('form', { onsubmit: (event) => event.preventDefault() }, [
    el('div.field', {}, [
      el('label', { text: `${t('message_to')} *` }),
      colleagues.length
        ? picker
        : el('div.muted.small', { text: t('nothing_here') }),
    ]),
    field({ name: 'subject', label: t('message_subject'), required: true, value: preset?.subject || '' }),
    field({
      name: 'body', label: t('message_body'), type: 'textarea', rows: 5,
      required: true, placeholder: t('message_placeholder'), value: preset?.body || '',
    }),
  ]);

  openModal({
    title: t('new_message'),
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('send'),
        onclick: async (event) => {
          const button = event.currentTarget;
          const data = readForm(form);
          if (!chosen.size) return toast(t('pick_colleagues'), 'error');
          if (!data.subject || !data.body) return toast(t('required_field'), 'error');
          button.disabled = true;
          try {
            await api.sendMessage({
              recipient_ids: [...chosen],
              subject: data.subject,
              body: data.body,
              entity: preset?.entity,
              entity_id: preset?.entity_id,
            });
            toast(t('message_sent'), 'success');
            close();
            onSent?.();
            refreshBell({ silent: true });
          } catch (error) {
            toastError(error);
            button.disabled = false;
          }
        },
      }),
    ]),
  });
}
