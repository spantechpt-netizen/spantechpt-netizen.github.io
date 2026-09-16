/**
 * Application shell: session handling, hash routing, sidebar, language switch.
 */
import { api, setUnauthorizedHandler, ApiError } from './api.js';
import { t, getLang, setLang, applyDirection, pick } from './i18n.js';
import { el, clear, icon, toast, toastError, initials, field, readForm, openModal, setTitle } from './ui.js';

import * as dashboard from './views/dashboard.js';
import * as customers from './views/customers.js';
import * as pipeline from './views/pipeline.js';
import * as activities from './views/activities.js';
import * as quotations from './views/quotations.js';
import * as quoteEditor from './views/quote-editor.js';
import * as analytics from './views/analytics.js';
import * as settings from './views/settings.js';
import * as notificationsView from './views/notifications.js';
import * as inbox from './views/inbox.js';
import * as calendarView from './views/calendar.js';
import * as bellModule from './notify.js';

export const state = {
  user: null,
  users: [],
  settings: null,
  activitySummary: { overdue: 0, today: 0, upcoming: 0, no_date: 0 },
};

const ROUTES = [
  { path: 'dashboard', icon: 'dashboard', label: 'nav_dashboard', view: dashboard },
  { path: 'customers', icon: 'customers', label: 'nav_customers', view: customers, need: 'customers.view' },
  { path: 'pipeline', icon: 'pipeline', label: 'nav_pipeline', view: pipeline, need: 'opportunities.view' },
  { path: 'activities', icon: 'activities', label: 'nav_activities', view: activities, badge: 'activities', need: 'activities.view' },
  { path: 'calendar', icon: 'calendar', label: 'nav_calendar', view: calendarView, need: 'activities.view' },
  { path: 'inbox', icon: 'mail', label: 'nav_inbox', view: inbox, badge: 'inbox', need: 'messages.send' },
  { path: 'quotations', icon: 'quotations', label: 'nav_quotations', view: quotations, need: 'quotations.view' },
  { path: 'analytics', icon: 'analytics', label: 'nav_analytics', view: analytics, need: 'analytics.view' },
  { path: 'settings', icon: 'settings', label: 'nav_settings', view: settings, need: 'settings.view' },
];

// Views not shown in the sidebar, reached from inside other screens.
const SUB_ROUTES = { quote: quoteEditor, notifications: notificationsView };

const RANK = { viewer: 0, engineer: 1, manager: 2, admin: 3 };
export const hasRole = (minimum) => (RANK[state.user?.role] ?? -1) >= (RANK[minimum] ?? 99);

/** True when the signed-in user holds this capability. */
export const can = (permission) =>
  Array.isArray(state.user?.permissions) && state.user.permissions.includes(permission);

/** Kept for the views that only ask "may this person change anything?". */
export const canEdit = () => can('customers.edit') || can('opportunities.edit')
  || can('quotations.edit') || can('activities.edit');

/** Whether this person sees every engineer's records or only their own. */
export const canSeeAll = () => can('customers.view_all');

const root = document.getElementById('root');

// ---------------------------------------------------------------- routing
export function navigate(hash) {
  if (location.hash === `#/${hash}`) render();
  else location.hash = `#/${hash}`;
}

function currentRoute() {
  const raw = (location.hash || '#/dashboard').replace(/^#\/?/, '');
  const [path, ...rest] = raw.split('/');
  return { path: path || 'dashboard', params: rest };
}

async function render() {
  if (!state.user) return renderLogin();

  const { path, params } = currentRoute();
  const route = ROUTES.find((r) => r.path === path);
  const sub = SUB_ROUTES[path];
  const view = route?.view || sub;

  if (!view) return navigate('dashboard');
  if (route?.need && !can(route.need)) return navigate('dashboard');

  renderShell();
  const outlet = document.getElementById('outlet');
  const title = route ? t(route.label) : t('quotation');
  document.getElementById('page-title').textContent = title;
  setTitle(title);
  markActiveNav(path);

  clear(outlet).append(el('div.loading-page', { text: t('loading') }));
  try {
    const node = await view.render({ params, navigate, state });
    clear(outlet).append(node);
  } catch (error) {
    clear(outlet).append(el('div.alert.danger', {
      text: error instanceof ApiError ? error.localised : String(error?.message || error),
    }));
    console.error(error);
  }
  refreshBadges();
}

function markActiveNav(path) {
  for (const item of document.querySelectorAll('.nav-item')) {
    item.classList.toggle('active', item.dataset.path === path);
  }
}

// ------------------------------------------------------------------- shell
let shellBuilt = false;

function renderShell() {
  if (shellBuilt && document.getElementById('outlet')) return;
  clear(root);

  const sidebar = el('aside.sidebar#sidebar', {}, [
    el('div.sidebar-brand', {}, [
      el('img', { src: 'assets/img/logo.png', alt: 'Span Tech' }),
      el('div', {}, [
        el('div.name', { text: t('app_name') }),
        el('div.sub', { text: t('app_subtitle') }),
      ]),
    ]),
    el('nav.sidebar-nav', {}, ROUTES
      .filter((route) => !route.need || can(route.need))
      .map((route) => el('a.nav-item', {
        href: `#/${route.path}`,
        dataset: { path: route.path },
        onclick: () => closeSidebar(),
      }, [
        icon(route.icon),
        el('span', { text: t(route.label) }),
        route.badge ? el('span.nav-badge', { dataset: { badge: route.path }, text: '' }) : null,
      ]))),
    el('div.sidebar-footer', {}, [
      el('div.sidebar-user', {}, [
        el('div.avatar', { text: initials(pick(state.user, 'name')) }),
        el('div.who.truncate', {}, [
          el('b', { class: 'truncate', text: pick(state.user, 'name') }),
          el('span', { text: t(`role_${state.user.role}`) }),
        ]),
      ]),
      el('div.row', { style: { marginTop: '.4rem' } }, [
        el('button.btn.btn-sm.btn-secondary', {
          type: 'button', style: { flex: '1' },
          text: t('my_profile'), onclick: openProfile,
        }),
        el('button.btn.btn-sm.btn-secondary', {
          type: 'button', title: t('sign_out'), 'aria-label': t('sign_out'),
          onclick: signOut,
        }, [icon('logout', 15)]),
      ]),
    ]),
  ]);

  const topbar = el('header.topbar', {}, [
    el('button.btn.btn-secondary.btn-icon.menu-toggle', {
      type: 'button', 'aria-label': 'Menu', onclick: toggleSidebar,
    }, [icon('menu', 18)]),
    el('h1#page-title', { text: '' }),
    el('div.topbar-actions', {}, [
      el('div.bell-wrap', {}, [bellModule.bell(navigate)]),
      languageSwitch(),
    ]),
  ]);

  root.append(el('div.app', {}, [
    sidebar,
    el('div.main', {}, [topbar, el('main.content#outlet')]),
  ]));
  shellBuilt = true;
}

function languageSwitch() {
  const make = (code, label) => el('button', {
    type: 'button',
    class: getLang() === code ? 'active' : '',
    text: label,
    onclick: () => {
      if (getLang() === code) return;
      setLang(code);
      shellBuilt = false;
      render();
    },
  });
  return el('div.lang-switch', {}, [make('ar', 'عربي'), make('en', 'EN')]);
}

const toggleSidebar = () => {
  const sidebar = document.getElementById('sidebar');
  sidebar.classList.toggle('open');
  if (sidebar.classList.contains('open')) {
    const scrim = el('div.scrim#scrim', { onclick: closeSidebar });
    document.body.append(scrim);
  } else closeSidebar();
};

const closeSidebar = () => {
  document.getElementById('sidebar')?.classList.remove('open');
  document.getElementById('scrim')?.remove();
};

export async function refreshBadges() {
  try {
    state.activitySummary = await api.activitySummary();
  } catch { return; }
  const counts = {
    activities: state.activitySummary.overdue,
    inbox: bellModule.getState().unreadMail,
  };
  for (const node of document.querySelectorAll('[data-badge]')) {
    const count = counts[node.dataset.badge] || 0;
    node.textContent = count > 0 ? String(count) : '';
    node.style.display = count > 0 ? '' : 'none';
  }
}

// ------------------------------------------------------------------ profile
function openProfile() {
  closeSidebar();
  const form = el('form#profile-form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({ name: 'name', label: t('customer_name_en'), value: state.user.name, required: true }),
      field({ name: 'name_ar', label: t('customer_name_ar'), value: state.user.name_ar || '', dir: 'rtl' }),
      field({ name: 'title', label: t('contact_title'), value: state.user.title || '' }),
      field({ name: 'title_ar', label: `${t('contact_title')} (AR)`, value: state.user.title_ar || '', dir: 'rtl' }),
      field({ name: 'phone', label: t('phone'), value: state.user.phone || '', type: 'tel' }),
      field({
        name: 'lang', label: t('language'), type: 'select', value: state.user.lang,
        options: [{ value: 'ar', label: 'العربية' }, { value: 'en', label: 'English' }],
      }),
    ]),
    el('hr', { style: { border: 0, borderTop: '1px solid var(--ink-200)', margin: '1rem 0' } }),
    el('h4', { text: t('change_password') }),
    el('div.grid.grid-2', {}, [
      field({ name: 'current_password', label: t('current_password'), type: 'password' }),
      field({ name: 'new_password', label: t('new_password'), type: 'password', hint: t('password_min') }),
    ]),
  ]);

  openModal({
    title: t('my_profile'),
    body: form,
    footer: (close) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async (event) => {
          const button = event.currentTarget;
          button.disabled = true;
          const data = readForm(form);
          try {
            if (data.current_password && data.new_password) {
              await api.changePassword(data.current_password, data.new_password);
              toast(t('password_changed'), 'success');
            }
            const { user } = await api.updateProfile({
              name: data.name, name_ar: data.name_ar, title: data.title,
              title_ar: data.title_ar, phone: data.phone, lang: data.lang,
            });
            state.user = user;
            toast(t('saved'), 'success');
            close();
            shellBuilt = false;
            render();
          } catch (error) {
            toastError(error);
            button.disabled = false;
          }
        },
      }),
    ]),
  });
}

async function signOut() {
  bellModule.stopPolling();
  try { await api.logout(); } catch { /* the cookie is cleared regardless */ }
  state.user = null;
  shellBuilt = false;
  renderLogin();
}

// -------------------------------------------------------------- login page
function renderLogin(message) {
  clear(root);
  const form = el('form', {}, [
    field({ name: 'email', label: t('email'), type: 'email', required: true, placeholder: 'name@spantech-pt.com' }),
    field({ name: 'password', label: t('password'), type: 'password', required: true }),
  ]);
  const error = el('div.alert.danger', { class: message ? '' : 'hidden', text: message || '' });
  const button = el('button.btn.btn-lg.btn-block', { type: 'submit', text: t('login') });
  // The button must live inside the form, otherwise clicking it never submits.
  form.append(button);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = readForm(form);
    button.disabled = true;
    button.textContent = '';
    button.append(el('span.spinner'));
    try {
      const { user } = await api.login(data.email, data.password);
      state.user = user;
      if (user.lang && user.lang !== getLang()) setLang(user.lang);
      await bootstrap();
      shellBuilt = false;
      if (!location.hash || location.hash === '#/') location.hash = '#/dashboard';
      else render();
    } catch (err) {
      error.textContent = err instanceof ApiError ? err.localised : t('error');
      error.classList.remove('hidden');
      button.disabled = false;
      button.textContent = t('login');
    }
  });

  root.append(el('div.login-page', {}, [
    el('div.login-card', {}, [
      el('img.logo', { src: 'assets/img/logo.png', alt: 'Span Tech' }),
      el('h1', { text: t('login_title') }),
      el('div.sub', { text: t('login_welcome') }),
      languageSwitch(),
      error,
      form,
    ]),
  ]));
  setTitle(t('login_title'));
  // The switch above rebuilds the page so the new language takes effect.
  root.querySelector('.lang-switch')?.addEventListener('click', () => setTimeout(() => renderLogin(message), 0));
}

// ------------------------------------------------------------------ startup
async function bootstrap() {
  const [usersResult, settingsResult] = await Promise.allSettled([api.users(), api.settings()]);
  if (usersResult.status === 'fulfilled') state.users = usersResult.value.users;
  if (settingsResult.status === 'fulfilled') state.settings = settingsResult.value.settings;
  // `silent` on the first pass: don't fire desktop pop-ups for a backlog.
  await bellModule.refresh({ silent: true });
  bellModule.startPolling();
  await refreshBadges();
}

setUnauthorizedHandler(() => {
  if (!state.user) return;
  bellModule.stopPolling();
  state.user = null;
  shellBuilt = false;
  renderLogin(t('login_title'));
});

window.addEventListener('hashchange', render);

(async function start() {
  applyDirection();
  try {
    const { user } = await api.me();
    if (user) {
      state.user = user;
      if (user.lang && user.lang !== localStorage.getItem('spantech_lang')) setLang(user.lang);
      await bootstrap();
      await render();
      return;
    }
  } catch (error) {
    console.error('startup', error);
  }
  renderLogin();
}());
