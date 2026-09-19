import { api } from '../api.js';
import { t, pick, getLang, isRTL, formatDate, formatDateTime } from '../i18n.js';
import {
  el, clear, icon, openModal, toast, toastError, confirmDialog, field, readForm,
} from '../ui.js';
import { canSeeAll, state } from '../app.js';
import { openActivityForm } from './activities.js';

const TYPE_COLOUR = {
  call: '#1a56a7', meeting: '#14683f', email: '#6b7280',
  whatsapp: '#178553', site_visit: '#c9761a', task: '#3d8bdd', note: '#9ca3af',
};

const view = {
  mode: 'month',
  cursor: new Date(),   // any date inside the month being shown
  scope: 'mine',
};

export async function render({ navigate }) {
  const page = el('div');
  const host = el('div');

  const label = el('b', { style: { minWidth: '150px', textAlign: 'center' } });

  page.append(el('div.toolbar', {}, [
    el('button.btn.btn-secondary.btn-icon', {
      type: 'button', title: t('prev'), onclick: () => step(-1),
    }, [icon(isRTL() ? 'chevron' : 'back', 15)]),
    el('button.btn.btn-secondary', {
      type: 'button', text: t('today'), onclick: () => { view.cursor = new Date(); load(); },
    }),
    el('button.btn.btn-secondary.btn-icon', {
      type: 'button', title: t('next'), onclick: () => step(1),
    }, [icon(isRTL() ? 'back' : 'chevron', 15)]),
    label,
    el('div.segmented', {}, [
      el('button', {
        type: 'button', class: view.mode === 'month' ? 'active' : '', text: t('month'),
        onclick: (e) => setMode('month', e.currentTarget),
      }),
      el('button', {
        type: 'button', class: view.mode === 'agenda' ? 'active' : '', text: t('agenda'),
        onclick: (e) => setMode('agenda', e.currentTarget),
      }),
    ]),
    canSeeAll() ? el('div.segmented', {}, [
      el('button', {
        type: 'button', class: view.scope === 'mine' ? 'active' : '', text: t('my_activities'),
        onclick: (e) => setScope('mine', e.currentTarget),
      }),
      el('button', {
        type: 'button', class: view.scope === 'all' ? 'active' : '', text: t('all_activities'),
        onclick: (e) => setScope('all', e.currentTarget),
      }),
    ]) : null,
    el('div.spacer'),
    el('button.btn.btn-secondary', {
      type: 'button', onclick: openFeedDialog,
    }, [icon('calendar', 15), t('calendar_feed')]),
    el('button.btn', {
      type: 'button', onclick: () => openActivityForm(null, load),
    }, [icon('plus', 16), t('new_activity')]),
  ]));

  function step(direction) {
    const next = new Date(view.cursor);
    if (view.mode === 'month') next.setMonth(next.getMonth() + direction);
    else next.setDate(next.getDate() + direction * 14);
    view.cursor = next;
    load();
  }
  function setMode(mode, button) {
    view.mode = mode;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    load();
  }
  function setScope(scope, button) {
    view.scope = scope;
    for (const sibling of button.parentElement.children) sibling.classList.remove('active');
    button.classList.add('active');
    load();
  }

  page.append(el('div.card', {}, [el('div.card-body', {}, [host])]));

  async function load() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { activities } = await api.activities({
        limit: 500,
        scope: view.scope === 'all' && canSeeAll() ? 'all' : undefined,
      });
      const dated = activities.filter((a) => a.due_at);
      label.textContent = monthLabel(view.cursor);
      clear(host).append(view.mode === 'month' ? monthGrid(dated, load) : agenda(dated, load));
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  await load();
  void navigate;
  return page;
}

function monthLabel(date) {
  return date.toLocaleDateString(isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', {
    month: 'long', year: 'numeric',
  });
}

const dayKey = (date) => {
  const d = date instanceof Date ? date : new Date(date);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

function monthGrid(activities, reload) {
  const cursor = view.cursor;
  const year = cursor.getFullYear();
  const month = cursor.getMonth();

  const first = new Date(year, month, 1);
  // Weeks start on Saturday across the Gulf and Egypt.
  const offset = (first.getDay() + 1) % 7;
  const start = new Date(year, month, 1 - offset);

  const byDay = new Map();
  for (const activity of activities) {
    const key = dayKey(activity.due_at);
    if (!byDay.has(key)) byDay.set(key, []);
    byDay.get(key).push(activity);
  }

  const grid = el('div.cal-grid');
  const headings = ['sat', 'sun', 'mon', 'tue', 'wed', 'thu', 'fri'];
  for (const day of headings) {
    grid.append(el('div.cal-head', { text: t(`weekday_${day}`) }));
  }

  const todayKey = dayKey(new Date());
  for (let i = 0; i < 42; i += 1) {
    const date = new Date(start);
    date.setDate(start.getDate() + i);
    const key = dayKey(date);
    const items = (byDay.get(key) || []).sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

    const cell = el('div.cal-cell', {
      class: [
        date.getMonth() === month ? '' : 'is-outside',
        key === todayKey ? 'is-today' : '',
      ].filter(Boolean).join(' '),
      ondblclick: () => openActivityForm(null, reload),
    }, [
      el('div.cal-daynum', { text: String(date.getDate()) }),
    ]);

    for (const item of items.slice(0, 4)) {
      const overdue = !item.done && new Date(item.due_at) < new Date();
      cell.append(el('div.cal-event', {
        class: item.done ? 'is-done' : overdue ? 'is-overdue' : '',
        style: { borderInlineStartColor: TYPE_COLOUR[item.type] || '#1a56a7' },
        title: `${t(`act_${item.type}`)} — ${item.subject}`,
        onclick: (event) => { event.stopPropagation(); openDay(items, date, reload); },
      }, [
        el('span.cal-time', { text: new Date(item.due_at).toLocaleTimeString(
          isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', { hour: '2-digit', minute: '2-digit' },
        ) }),
        el('span.truncate', { text: item.subject }),
      ]));
    }
    if (items.length > 4) {
      cell.append(el('button.cal-more', {
        type: 'button',
        text: `+${items.length - 4}`,
        onclick: (event) => { event.stopPropagation(); openDay(items, date, reload); },
      }));
    }
    grid.append(cell);
  }
  return grid;
}

function agenda(activities, reload) {
  const now = new Date();
  const horizon = new Date(view.cursor);
  const from = new Date(horizon.getFullYear(), horizon.getMonth(), horizon.getDate() - 7);
  const to = new Date(horizon.getFullYear(), horizon.getMonth(), horizon.getDate() + 45);

  const inRange = activities
    .filter((a) => {
      const due = new Date(a.due_at);
      return due >= from && due <= to;
    })
    .sort((a, b) => new Date(a.due_at) - new Date(b.due_at));

  if (!inRange.length) {
    return el('div.empty', {}, [icon('calendar', 40), el('div', { text: t('nothing_here') })]);
  }

  const wrap = el('div');
  let lastKey = null;
  for (const item of inRange) {
    const key = dayKey(item.due_at);
    if (key !== lastKey) {
      lastKey = key;
      wrap.append(el('div.agenda-day', { text: formatDate(key) }));
    }
    const overdue = !item.done && new Date(item.due_at) < now;
    wrap.append(el('div.agenda-row', {
      class: item.done ? 'is-done' : overdue ? 'is-overdue' : '',
      onclick: () => openDay([item], new Date(item.due_at), reload),
    }, [
      el('span.cal-dot', { style: { background: TYPE_COLOUR[item.type] || '#1a56a7' } }),
      el('span.agenda-time', { text: new Date(item.due_at).toLocaleTimeString(
        isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', { hour: '2-digit', minute: '2-digit' },
      ) }),
      el('div', { style: { flex: '1', minWidth: '0' } }, [
        el('div.bold.small', { text: item.subject }),
        el('div.tiny.muted', {
          text: [t(`act_${item.type}`), pick(item, 'customer_name'), item.opportunity_title]
            .filter(Boolean).join(' · '),
        }),
      ]),
      item.owner_name ? el('span.badge.grey', { text: pick(item, 'owner_name') }) : null,
    ]));
  }
  return wrap;
}

function openDay(items, date, reload) {
  const body = el('div');
  for (const item of items) {
    const overdue = !item.done && new Date(item.due_at) < new Date();
    body.append(el('div.followup', { class: item.done ? 'is-done' : overdue ? 'is-overdue' : '' }, [
      el('button.tick', {
        type: 'button',
        title: item.done ? t('reopen') : t('mark_done'),
        style: item.done ? { background: 'var(--ok-700)', borderColor: 'var(--ok-700)' } : {},
        onclick: async () => {
          try {
            await api.updateActivity(item.id, { done: !item.done });
            close();
            reload();
          } catch (error) { toastError(error); }
        },
      }),
      el('div.body', {}, [
        el('div.subject', { text: item.subject }),
        el('div.meta', {}, [
          el('span.badge.grey', { text: t(`act_${item.type}`) }),
          el('span', { text: ` ${formatDateTime(item.due_at)}` }),
          pick(item, 'customer_name') ? el('span', { text: ` · ${pick(item, 'customer_name')}` }) : null,
        ]),
        item.notes ? el('div.tiny.muted', { text: item.notes }) : null,
      ]),
      el('div.row', {}, [
        el('a.btn.btn-sm.btn-secondary', {
          href: `/api/activities/${item.id}/ics?lang=${getLang()}`,
          title: t('download_ics'),
        }, [icon('calendar', 13)]),
        el('button.btn.btn-sm.btn-secondary', {
          type: 'button', title: t('edit'),
          onclick: () => { close(); openActivityForm(item, reload); },
        }, [icon('edit', 13)]),
      ]),
    ]));
  }

  const { close } = openModal({
    title: formatDate(dayKey(date)),
    body,
    footer: (dismiss) => el('div.row', {}, [
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: dismiss }),
      el('button.btn', {
        type: 'button', text: t('new_activity'),
        onclick: () => { dismiss(); openActivityForm(null, reload); },
      }),
    ]),
  });
}

// ------------------------------------------------------------- feed dialog
export async function openFeedDialog() {
  let feed;
  try { feed = await api.calendarFeed(); } catch (error) { return toastError(error); }

  const urlBox = el('input', { type: 'text', readonly: true, dir: 'ltr' });
  urlBox.value = feed.url;

  const body = el('div', {}, [
    el('p.small', { text: t('calendar_feed_hint') }),
    el('div.row', { style: { gap: '.4rem' } }, [
      urlBox,
      el('button.btn.btn-secondary', {
        type: 'button', text: t('copy_link'),
        onclick: async () => {
          try {
            await navigator.clipboard.writeText(urlBox.value);
            toast(t('copied'), 'success');
          } catch {
            urlBox.select();
            toast(t('copied'), 'success');
          }
        },
      }),
    ]),
    el('div.row.mt-1', { style: { gap: '.4rem' } }, [
      el('a.btn.btn-secondary', { href: feed.webcal_url, text: t('subscribe_outlook') }),
      el('a.btn.btn-secondary', { href: feed.url, download: 'spantech-follow-ups.ics', text: t('download_ics') }),
    ]),
    el('div.alert.info.mt-2', {
      text: getLang() === 'ar'
        ? 'اللينك ده خاص بيك انت بس — متبعتهوش لحد. لو حسّيت إنه اتسرّب، اعمل لينك جديد.'
        : 'This link is private to you — do not share it. If it leaks, generate a new one.',
    }),
    el('h4.mt-2', { text: t('reminder_settings') }),
  ]);

  const settingsForm = el('form', { onsubmit: (e) => e.preventDefault() }, [
    el('div.grid.grid-2', {}, [
      field({
        name: 'reminder_lead_hours', label: t('reminder_lead_hours'), type: 'number',
        value: state.user.reminder_lead_hours ?? 24, min: 1, max: 168,
      }),
      field({
        name: 'stale_after_days', label: t('stale_after_days'), type: 'number',
        value: state.user.stale_after_days ?? 30, min: 1, max: 365,
      }),
    ]),
  ]);
  body.append(settingsForm);

  openModal({
    title: t('calendar_feed'),
    body,
    footer: (close) => el('div.row', { style: { width: '100%' } }, [
      el('button.btn.btn-sm.btn-danger', {
        type: 'button', text: t('new_link'),
        onclick: async () => {
          if (!await confirmDialog(t('rotate_warning'))) return;
          try {
            const fresh = await api.rotateCalendarFeed();
            urlBox.value = fresh.url;
            toast(t('saved'), 'success');
          } catch (error) { toastError(error); }
        },
      }),
      el('div.spacer'),
      el('button.btn.btn-secondary', { type: 'button', text: t('close'), onclick: close }),
      el('button.btn', {
        type: 'button', text: t('save'),
        onclick: async () => {
          try {
            const data = readForm(settingsForm);
            const { user } = await api.updateProfile(data);
            state.user = { ...state.user, ...user };
            toast(t('saved'), 'success');
            close();
          } catch (error) { toastError(error); }
        },
      }),
    ]),
  });
}
