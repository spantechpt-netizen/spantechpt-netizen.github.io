import { api } from '../api.js';
import { t, pick, formatDateTime, relativeDays } from '../i18n.js';
import {
  el, clear, icon, field, readForm, openModal, confirmDialog,
  toast, toastError, optionsFrom, blankOption,
} from '../ui.js';
import { can, canSeeAll, state, refreshBadges } from '../app.js';

const TYPES = ['call', 'meeting', 'email', 'whatsapp', 'site_visit', 'task', 'note'];
const view = { bucket: '', type: '', owner: '', showDone: false };

export async function render() {
  const page = el('div');
  const host = el('div');

  const summary = await api.activitySummary().catch(() => ({ overdue: 0, today: 0, upcoming: 0, no_date: 0 }));

  // Clicking a tile filters the list below it.
  const tile = (bucket, tone, label, value) => el(`div.kpi${tone ? `.${tone}` : ''}`, {
    style: { cursor: 'pointer', outline: view.bucket === bucket ? '2px solid var(--brand-500)' : '' },
    onclick: () => { view.bucket = view.bucket === bucket ? '' : bucket; render2(); },
  }, [
    el('div.label', { text: label }),
    el('div.value.num', { text: String(value) }),
  ]);

  const tiles = el('div.kpi-grid', {}, [
    tile('overdue', summary.overdue ? 'danger' : 'ok', t('overdue'), summary.overdue),
    tile('today', 'warn', t('due_today'), summary.today),
    tile('upcoming', '', t('upcoming'), summary.upcoming),
    tile('', 'accent', t('no_due_date'), summary.no_date),
  ]);

  page.append(tiles);

  page.append(el('div.toolbar', {}, [
    el('select', {
      onchange: (event) => { view.type = event.target.value; refresh(); },
    }, [blankOption(t('activity_type')), ...optionsFrom(TYPES, 'act_')].map((option) => {
      const node = el('option', { value: option.value, text: option.label });
      if (option.value === view.type) node.selected = true;
      return node;
    })),
    canSeeAll() ? el('select', {
      onchange: (event) => { view.owner = event.target.value; refresh(); },
    }, [blankOption(t('owner')), ...state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') }))]
      .map((option) => {
        const node = el('option', { value: option.value, text: option.label });
        if (String(option.value) === String(view.owner)) node.selected = true;
        return node;
      })) : null,
    el('label.checkbox', {}, [
      (() => {
        const box = el('input', { type: 'checkbox' });
        box.checked = view.showDone;
        box.addEventListener('change', () => { view.showDone = box.checked; refresh(); });
        return box;
      })(),
      el('span', { text: t('done') }),
    ]),
    el('div.spacer'),
    can('activities.create') ? el('button.btn', {
      type: 'button', onclick: () => openActivityForm(null, refresh),
    }, [icon('plus', 16), t('new_activity')]) : null,
  ]));

  page.append(el('div.card', {}, [el('div.card-body.flush', {}, [host])]));

  async function refresh() {
    clear(host).append(el('div.loading-page', { text: t('loading') }));
    try {
      const { activities } = await api.activities({
        bucket: view.bucket || undefined,
        type: view.type || undefined,
        owner_id: view.owner || undefined,
        done: view.showDone ? undefined : 0,
        scope: canSeeAll() ? 'all' : undefined,
      });
      clear(host).append(renderList(activities, refresh));
      refreshBadges();
    } catch (error) {
      clear(host).append(el('div.alert.danger', { text: error.localised || error.message }));
    }
  }

  function render2() {
    // Re-draw the tile outlines, then reload the list.
    for (const node of tiles.children) node.style.outline = '';
    const index = ['overdue', 'today', 'upcoming', ''].indexOf(view.bucket);
    if (index >= 0 && view.bucket) tiles.children[index].style.outline = '2px solid var(--brand-500)';
    refresh();
  }

  await refresh();
  return page;
}

function renderList(activities, refresh) {
  if (!activities.length) {
    return el('div.empty', {}, [icon('check', 40), el('div', { text: t('all_clear') })]);
  }

  const list = el('div');
  for (const item of activities) {
    const { days, label } = relativeDays(item.due_at);
    const tone = item.done ? 'is-done' : days === null ? '' : days < 0 ? 'is-overdue' : days === 0 ? 'is-today' : '';

    const related = [
      pick(item, 'customer_name'),
      item.opportunity_title,
      item.quotation_number,
    ].filter(Boolean).join(' · ');

    list.append(el(`div.followup${tone ? `.${tone}` : ''}`, {}, [
      el('button.tick', {
        type: 'button',
        title: item.done ? t('reopen') : t('mark_done'),
        style: item.done ? { background: 'var(--ok-700)', borderColor: 'var(--ok-700)' } : {},
        onclick: async () => {
          try {
            await api.updateActivity(item.id, { done: !item.done });
            refresh();
          } catch (error) { toastError(error); }
        },
      }),
      el('div.body', {}, [
        el('div.subject', { text: item.subject }),
        el('div.meta', {}, [
          el('span.badge.grey', { text: t(`act_${item.type}`) }),
          related ? el('span', { text: ` ${related}` }) : null,
          item.due_at ? el('span.due', { text: ` · ${label} (${formatDateTime(item.due_at)})` }) : null,
          item.owner_name ? el('span.muted', { text: ` · ${pick(item, 'owner_name')}` }) : null,
        ]),
        item.notes ? el('div.tiny.muted', { text: item.notes }) : null,
        item.outcome ? el('div.tiny', { style: { color: 'var(--ok-700)' }, text: `✓ ${item.outcome}` }) : null,
        item.contact_mobile ? el('div.tiny', {}, [
          el('a', { href: `tel:${item.contact_mobile}`, text: `${item.contact_name || ''} ${item.contact_mobile}`, dir: 'ltr' }),
        ]) : null,
      ]),
      can('activities.edit') ? el('div.row', {}, [
        el('button.btn.btn-sm.btn-secondary', {
          type: 'button', title: t('edit'),
          onclick: () => openActivityForm(item, refresh),
        }, [icon('edit', 13)]),
        el('button.btn.btn-sm.btn-danger', {
          type: 'button', title: t('delete'),
          onclick: async () => {
            if (!await confirmDialog(t('confirm_delete'))) return;
            try {
              await api.deleteActivity(item.id);
              toast(t('deleted'), 'success');
              refresh();
            } catch (error) { toastError(error); }
          },
        }, [icon('trash', 13)]),
      ]) : null,
    ]));
  }
  return list;
}

/** Converts an ISO timestamp to the value a datetime-local input expects. */
function toLocalInput(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function openActivityForm(activity, onSaved, preset = {}) {
  const isEdit = Boolean(activity);
  const form = el('form', { onsubmit: (event) => event.preventDefault() });
  const customerSelect = el('select', { name: 'customer_id' });
  const opportunitySelect = el('select', { name: 'opportunity_id' });

  const defaultDue = (() => {
    const date = new Date();
    date.setDate(date.getDate() + 2);
    date.setHours(9, 0, 0, 0);
    return toLocalInput(date.toISOString());
  })();

  form.append(
    field({ name: 'subject', label: t('subject'), value: activity?.subject || '', required: true }),
    el('div.grid.grid-2', {}, [
      field({ name: 'type', label: t('activity_type'), type: 'select', value: activity?.type || 'call', options: optionsFrom(TYPES, 'act_') }),
      field({
        name: 'due_at', label: t('due_at'), type: 'datetime-local',
        value: activity ? toLocalInput(activity.due_at) : defaultDue,
      }),
      el('div.field', {}, [el('label', { text: t('customer') }), customerSelect]),
      el('div.field', {}, [el('label', { text: t('opportunity') }), opportunitySelect]),
      canSeeAll() ? field({
        name: 'owner_id', label: t('owner'), type: 'select',
        value: activity?.owner_id || state.user.id,
        options: state.users.filter((u) => u.active).map((u) => ({ value: u.id, label: pick(u, 'name') })),
      }) : null,
    ]),
    field({ name: 'notes', label: t('notes'), type: 'textarea', value: activity?.notes || '', rows: 3 }),
    isEdit ? field({ name: 'outcome', label: t('outcome'), type: 'textarea', value: activity?.outcome || '', rows: 2 }) : null,
  );

  openModal({
    title: isEdit ? t('edit') : t('new_activity'),
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
            // datetime-local gives local wall time; send it as a real instant.
            if (data.due_at) data.due_at = new Date(data.due_at).toISOString();
            if (isEdit) await api.updateActivity(activity.id, data);
            else await api.createActivity(data);
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

  // Populate the relationship selects after the modal is on screen.
  const selectedCustomer = activity?.customer_id ?? preset.customer_id ?? '';
  const selectedOpportunity = activity?.opportunity_id ?? preset.opportunity_id ?? '';

  customerSelect.append(el('option', { value: '', text: `— ${t('none')} —` }));
  api.customers({ limit: 500, scope: 'all' }).then(({ customers }) => {
    for (const customer of customers) {
      const node = el('option', { value: customer.id });
      node.textContent = pick(customer, 'name');
      if (String(customer.id) === String(selectedCustomer)) node.selected = true;
      customerSelect.append(node);
    }
  }).catch(() => {});

  opportunitySelect.append(el('option', { value: '', text: `— ${t('none')} —` }));
  api.opportunities({ scope: 'all' }).then(({ opportunities }) => {
    for (const opportunity of opportunities) {
      const node = el('option', { value: opportunity.id });
      node.textContent = pick(opportunity, 'title');
      if (String(opportunity.id) === String(selectedOpportunity)) node.selected = true;
      opportunitySelect.append(node);
    }
  }).catch(() => {});
}
