import { api } from '../api.js';
import { t, getLang, formatDateTime } from '../i18n.js';
import { el, clear, icon, toast, toastError, confirmDialog } from '../ui.js';
import { canSeeAll } from '../app.js';
import { refresh as refreshBell, askDesktopPermission, desktopState, desktopSupported } from '../notify.js';

const SEVERITY_CLASS = { info: 'blue', warning: 'amber', danger: 'red' };
const view = { unreadOnly: false };

export async function render({ navigate }) {
  const page = el('div');
  const host = el('div');

  page.append(el('div.toolbar', {}, [
    el('div.segmented', {}, [
      el('button', {
        type: 'button', class: view.unreadOnly ? '' : 'active', text: t('all'),
        onclick: (e) => setFilter(false, e.currentTarget),
      }),
      el('button', {
        type: 'button', class: view.unreadOnly ? 'active' : '', text: t('unread'),
        onclick: (e) => setFilter(true, e.currentTarget),
      }),
    ]),
    el('div.spacer'),
    desktopButton(),
    canSeeAll() ? el('button.btn.btn-secondary', {
      type: 'button', text: t('run_check_now'),
      onclick: async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          await api.sweepReminders();
          toast(t('check_done'), 'success');
          await load();
          await refreshBell({ silent: true });
        } catch (error) { toastError(error); }
        button.disabled = false;
      },
    }) : null,
    el('button.btn', {
      type: 'button', text: t('mark_all_read'),
      onclick: async () => {
        try {
          await api.markAllNotificationsRead();
          await load();
          await refreshBell({ silent: true });
        } catch (error) { toastError(error); }
      },
    }),
  ]));

  function setFilter(unreadOnly, button) {
    view.unreadOnly = unreadOnly;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    load();
  }

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [host])]));

  async function load() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { notifications } = await api.notifications({
        limit: 100, unread: view.unreadOnly ? 1 : undefined,
      });
      clear(host);
      if (!notifications.length) {
        host.append(el('div.empty', {}, [icon('bell', 40), el('div', { text: t('no_notifications') })]));
        return;
      }
      for (const item of notifications) host.append(row(item, navigate, load));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await load();
  return page;
}

function desktopButton() {
  const status = desktopState();
  // Plain HTTP: the browser will never grant this, so explain rather than
  // offering a button that cannot work.
  if (status === 'insecure') {
    return el('span.badge.grey', { title: t('desktop_needs_https'), text: t('desktop_needs_https') });
  }
  if (status === 'unsupported') return null;
  if (status === 'granted') {
    return el('span.badge.green', { text: t('desktop_enabled') });
  }
  if (status === 'denied') {
    return el('span.badge.amber', { title: t('desktop_blocked'), text: t('desktop_blocked') });
  }
  return el('button.btn.btn-secondary', {
    type: 'button', text: t('enable_desktop_notifications'),
    onclick: async (event) => {
      const result = await askDesktopPermission();
      if (result === 'granted') {
        event.currentTarget.replaceWith(el('span.badge.green', { text: t('desktop_enabled') }));
        toast(t('desktop_enabled'), 'success');
      } else {
        toast(t('desktop_blocked'), 'error');
      }
    },
  });
}

function row(item, navigate, reload) {
  const title = (getLang() === 'ar' ? item.title_ar : item.title_en) || item.title_en;
  const body = (getLang() === 'ar' ? item.body_ar : item.body_en) || '';

  const node = el(`div.notif-row${item.is_read ? '' : '.is-unread'}`, {}, [
    el('span.notif-dot', { class: SEVERITY_CLASS[item.severity] || 'blue' }),
    el('div.notif-text', { style: { flex: '1', cursor: item.link ? 'pointer' : 'default' },
      onclick: async () => {
        if (!item.is_read) {
          try { await api.markNotificationRead(item.id); } catch { /* still navigate */ }
        }
        if (item.link) navigate(item.link);
        else reload();
        refreshBell({ silent: true });
      },
    }, [
      el('div.row', { style: { gap: '.4rem' } }, [
        el('span.badge.grey', { text: t(`notif_${item.type}`) }),
        el('span.notif-title', { text: title }),
      ]),
      body ? el('div.notif-body', { text: body }) : null,
      el('div.notif-time', {
        text: [formatDateTime(item.created_at), item.actor_name
          ? `· ${getLang() === 'ar' ? (item.actor_name_ar || item.actor_name) : item.actor_name}`
          : ''].filter(Boolean).join(' '),
      }),
    ]),
    el('div.row', {}, [
      item.is_read ? null : el('button.btn.btn-sm.btn-secondary', {
        type: 'button', title: t('mark_read'),
        onclick: async (event) => {
          event.stopPropagation();
          try {
            await api.markNotificationRead(item.id);
            await reload();
            refreshBell({ silent: true });
          } catch (error) { toastError(error); }
        },
      }, [icon('check', 13)]),
      el('button.btn.btn-sm.btn-danger', {
        type: 'button', title: t('delete'),
        onclick: async (event) => {
          event.stopPropagation();
          if (!await confirmDialog(t('confirm_delete'))) return;
          try {
            await api.deleteNotification(item.id);
            await reload();
            refreshBell({ silent: true });
          } catch (error) { toastError(error); }
        },
      }, [icon('trash', 13)]),
    ]),
  ]);
  return node;
}
