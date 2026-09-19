/**
 * Notification bell: polls for new alerts, renders the dropdown, and mirrors
 * anything new to the operating system's notification centre when the
 * engineer has granted permission.
 */
import { api } from './api.js';
import { t, getLang, formatDateTime } from './i18n.js';
import { el, clear, icon, toastError } from './ui.js';

// With the live stream open, polling is only a safety net; without it (an
// old browser, a proxy that refuses long connections) it is the mechanism.
const POLL_MS = 60_000;
const FALLBACK_POLL_MS = 5 * 60_000;

const state = {
  unread: 0,
  unreadMail: 0,
  items: [],
  timer: null,
  stream: null,
  live: false,
  lastSeenId: Number(localStorage.getItem('spantech_last_notification') || 0),
};

const SEVERITY_CLASS = { info: 'blue', warning: 'amber', danger: 'red' };

const title = (n) => (getLang() === 'ar' ? n.title_ar : n.title_en) || n.title_en;
const body = (n) => (getLang() === 'ar' ? n.body_ar : n.body_en) || '';

// ------------------------------------------------------------ desktop alerts
/**
 * Browsers only hand out notification permission in a secure context, which
 * means HTTPS (localhost counts). On a plain-HTTP deployment the API may be
 * missing outright, or present and permanently refusing — either way the
 * honest answer to the engineer is "this needs HTTPS", not "blocked".
 */
export const secureContext = () => window.isSecureContext !== false;

export const desktopSupported = () => typeof Notification !== 'undefined' && secureContext();

export const desktopState = () => {
  if (!secureContext()) return 'insecure';
  return typeof Notification !== 'undefined' ? Notification.permission : 'unsupported';
};

export async function askDesktopPermission() {
  if (!desktopSupported()) return 'unsupported';
  if (Notification.permission === 'granted') return 'granted';
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

/** Raises an OS notification, ignoring anything the browser refuses. */
function showDesktop(item) {
  if (!desktopSupported() || Notification.permission !== 'granted') return;
  try {
    const note = new Notification(title(item), {
      body: body(item),
      tag: `spantech-${item.id}`,
      icon: '/assets/img/icon.png',
      lang: getLang(),
      dir: getLang() === 'ar' ? 'rtl' : 'ltr',
    });
    note.onclick = () => {
      window.focus();
      if (item.link) location.hash = `#/${item.link}`;
      note.close();
    };
  } catch { /* some browsers refuse outside a user gesture */ }
}

// ------------------------------------------------------------------ polling
let onBadgeChange = () => {};
export const setBadgeHandler = (fn) => { onBadgeChange = fn; };

export async function refresh({ silent = false } = {}) {
  try {
    const [{ notifications, unread }, summary] = await Promise.all([
      api.notifications({ limit: 30 }),
      api.inboxSummary().catch(() => ({ messages: 0 })),
    ]);
    state.items = notifications;
    state.unread = unread;
    state.unreadMail = summary.messages || 0;

    // Anything newer than the highest id we have already shown is "new".
    const fresh = notifications.filter((n) => !n.is_read && n.id > state.lastSeenId);
    if (fresh.length) {
      const highest = Math.max(...fresh.map((n) => n.id));
      state.lastSeenId = highest;
      localStorage.setItem('spantech_last_notification', String(highest));
      // Don't blast the desktop on the very first load of a session.
      if (!silent) fresh.slice(0, 3).forEach(showDesktop);
    }

    onBadgeChange(state);
    renderDropdown();
  } catch (error) {
    if (!silent) console.warn('notifications', error);
  }
  return state;
}

export function startPolling() {
  stopPolling();
  openStream();
  state.timer = setInterval(() => refresh({ silent: true }), state.stream ? FALLBACK_POLL_MS : POLL_MS);
}

export function stopPolling() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (state.stream) { state.stream.close(); state.stream = null; }
  state.live = false;
}

// -------------------------------------------------------------- live stream
/**
 * One EventSource per tab. The server says what happened and to whom; the
 * page then fetches through the ordinary API, so nothing arrives on the
 * stream that the API would refuse. Other views listen for the same events
 * on `window` and refresh themselves when they are concerned.
 */
const listeners = new Set();
export const onLive = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

function emit(kind, detail) {
  for (const fn of listeners) {
    try { fn(kind, detail); } catch (error) { console.warn('live listener', error); }
  }
  window.dispatchEvent(new CustomEvent('spantech:live', { detail: { kind, ...detail } }));
}

function openStream() {
  if (typeof EventSource === 'undefined' || state.stream) return;
  const source = new EventSource('/api/events');
  state.stream = source;

  source.addEventListener('hello', () => {
    state.live = true;
    onBadgeChange(state);
  });
  source.addEventListener('notification', (event) => {
    // Not silent: this is exactly the moment a desktop pop-up is wanted.
    refresh({ silent: false });
    emit('notification', parse(event.data));
  });
  source.addEventListener('mail', (event) => {
    refresh({ silent: true });
    emit('mail', parse(event.data));
  });
  source.addEventListener('quote_status', (event) => {
    emit('quote_status', parse(event.data));
  });
  source.onerror = () => {
    // EventSource reconnects on its own; until it does, the poll carries on.
    state.live = false;
    onBadgeChange(state);
  };
}

const parse = (text) => { try { return JSON.parse(text || '{}'); } catch { return {}; } };

export const getState = () => state;

// ------------------------------------------------------------------ bell UI
let dropdown;
let bellButton;

export function bell(navigate) {
  bellButton = el('button.btn.btn-secondary.btn-icon.bell', {
    type: 'button', 'aria-label': t('notifications'), title: t('notifications'),
    onclick: (event) => { event.stopPropagation(); toggleDropdown(navigate); },
  }, [icon('bell', 18), el('span.bell-badge.hidden')]);

  updateBadge();
  return bellButton;
}

function updateBadge() {
  const badge = bellButton?.querySelector('.bell-badge');
  if (!badge) return;
  const count = state.unread;
  badge.textContent = count > 99 ? '99+' : String(count);
  badge.classList.toggle('hidden', count === 0);
}

setBadgeHandler(() => {
  updateBadge();
  const dot = document.querySelector('.live-dot');
  if (dot) {
    dot.classList.toggle('on', state.live);
    dot.title = state.live ? t('live_connected') : t('live_reconnecting');
  }
  // Keep the sidebar's message badge in step too.
  for (const node of document.querySelectorAll('[data-badge="inbox"]')) {
    node.textContent = state.unreadMail > 0 ? String(state.unreadMail) : '';
    node.style.display = state.unreadMail > 0 ? '' : 'none';
  }
});

function toggleDropdown(navigate) {
  if (dropdown) return closeDropdown();
  dropdown = el('div.notif-dropdown');
  renderDropdown(navigate);
  bellButton.parentElement.append(dropdown);
  setTimeout(() => document.addEventListener('click', onOutsideClick), 0);
  refresh({ silent: true });
}

function onOutsideClick(event) {
  if (dropdown && !dropdown.contains(event.target) && !bellButton.contains(event.target)) {
    closeDropdown();
  }
}

function closeDropdown() {
  dropdown?.remove();
  dropdown = null;
  document.removeEventListener('click', onOutsideClick);
}

function renderDropdown(navigate) {
  if (!dropdown) return;
  clear(dropdown);

  dropdown.append(el('div.notif-head', {}, [
    el('b', { text: t('notifications') }),
    el('div.spacer'),
    state.unread > 0 ? el('button.btn.btn-sm.btn-ghost', {
      type: 'button', text: t('mark_all_read'),
      onclick: async (event) => {
        event.stopPropagation();
        try {
          await api.markAllNotificationsRead();
          await refresh({ silent: true });
        } catch (error) { toastError(error); }
      },
    }) : null,
  ]));

  const list = el('div.notif-list');
  if (!state.items.length) {
    list.append(el('div.empty', { style: { padding: '1.6rem' } }, [
      icon('bell', 32), el('div', { text: t('no_notifications') }),
    ]));
  }

  for (const item of state.items.slice(0, 20)) {
    list.append(el(`div.notif-item${item.is_read ? '' : '.is-unread'}`, {
      onclick: async () => {
        if (!item.is_read) {
          try { await api.markNotificationRead(item.id); } catch { /* keep navigating */ }
        }
        closeDropdown();
        if (item.link) {
          if (navigate) navigate(item.link);
          else location.hash = `#/${item.link}`;
        }
        refresh({ silent: true });
      },
    }, [
      el('span.notif-dot', { class: SEVERITY_CLASS[item.severity] || 'blue' }),
      el('div.notif-text', {}, [
        el('div.notif-title', { text: title(item) }),
        body(item) ? el('div.notif-body', { text: body(item) }) : null,
        el('div.notif-time', { text: formatDateTime(item.created_at) }),
      ]),
    ]));
  }
  dropdown.append(list);

  dropdown.append(el('div.notif-foot', {}, [
    el('button.btn.btn-sm.btn-ghost.btn-block', {
      type: 'button', text: t('view_all'),
      onclick: () => {
        closeDropdown();
        if (navigate) navigate('notifications');
        else location.hash = '#/notifications';
      },
    }),
  ]));
}
