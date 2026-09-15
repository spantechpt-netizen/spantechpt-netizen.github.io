/**
 * Small DOM toolkit: element builder, modals, toasts, form fields and the
 * shared badge / icon vocabulary. No framework, no build step.
 */
import { t, getLang } from './i18n.js';

/** Escapes text destined for innerHTML. */
export const esc = (value) => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');

/**
 * el('div.card', { onclick }, [children])
 * Tag syntax supports #id and .class shorthands.
 */
export function el(spec, props = {}, children = []) {
  // Accepts any order: "main#outlet", "div.card#id", "a.nav-item".
  const text = String(spec);
  const hash = text.indexOf('#');
  let id = '';
  let rest = text;
  if (hash !== -1) {
    const after = text.slice(hash + 1);
    const dot = after.indexOf('.');
    id = dot === -1 ? after : after.slice(0, dot);
    rest = text.slice(0, hash) + (dot === -1 ? '' : after.slice(dot));
  }
  const [tag, ...classes] = rest.split('.');
  const node = document.createElement(tag || 'div');
  if (id) node.id = id;
  if (classes.length) node.className = classes.filter(Boolean).join(' ');

  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') node.className = `${node.className} ${value}`.trim();
    else if (key === 'html') node.innerHTML = value;
    else if (key === 'text') node.textContent = value;
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(node.style, value);
    else if (key.startsWith('on') && typeof value === 'function') {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else node.setAttribute(key, value === true ? '' : value);
  }

  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };

// ------------------------------------------------------------------- icons
const ICONS = {
  dashboard: 'M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z',
  customers: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  pipeline: 'M3 3v18h18M7 16l4-6 4 3 5-8',
  activities: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2',
  quotations: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8',
  analytics: 'M18 20V10M12 20V4M6 20v-6',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.14.33.22.7.22 1.09V11a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM21 21l-4.35-4.35',
  plus: 'M12 5v14M5 12h14',
  menu: 'M3 12h18M3 6h18M3 18h18',
  print: 'M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z',
  trash: 'M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2',
  edit: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z',
  copy: 'M20 9h-9a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-9a2 2 0 0 0-2-2zM5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1',
  check: 'M20 6L9 17l-5-5',
  x: 'M18 6L6 18M6 6l12 12',
  phone: 'M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z',
  mail: 'M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zM22 6l-10 7L2 6',
  calendar: 'M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  building: 'M3 21h18M5 21V7l8-4v18M19 21V11l-6-4M9 9v.01M9 12v.01M9 15v.01M9 18v.01',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9',
  empty: 'M20 13V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7M4 13h4l1.5 3h5L16 13h4v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z',
  chevron: 'M9 18l6-6-6-6',
  back: 'M19 12H5M12 19l-7-7 7-7',
};

export function icon(name, size = 18) {
  const path = ICONS[name] || ICONS.empty;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.innerHTML = `<path d="${path}"/>`;
  return svg;
}

// ------------------------------------------------------------------ toasts
let toastHost;
export function toast(message, kind = 'info', ms = 3600) {
  if (!toastHost) {
    toastHost = el('div.toasts');
    document.body.append(toastHost);
  }
  const node = el('div.toast', { class: kind, text: message });
  toastHost.append(node);
  setTimeout(() => {
    node.style.opacity = '0';
    node.style.transition = 'opacity .25s';
    setTimeout(() => node.remove(), 250);
  }, ms);
}

export const toastError = (error) =>
  toast(error?.localised || error?.message || t('error'), 'error', 5200);

// ------------------------------------------------------------------ modals
/**
 * openModal({ title, body, footer, size, onClose })
 * `body` and `footer` may be nodes or functions receiving the close callback.
 */
export function openModal({ title, body, footer, size = '', onClose }) {
  const backdrop = el('div.modal-backdrop');
  const close = () => {
    backdrop.remove();
    document.removeEventListener('keydown', onKey);
    document.body.style.overflow = '';
    onClose?.();
  };
  const onKey = (event) => { if (event.key === 'Escape') close(); };

  const modal = el(`div.modal${size ? `.${size}` : ''}`, {}, [
    el('div.modal-header', {}, [
      el('h2', { text: title || '' }),
      el('button.close', { type: 'button', 'aria-label': t('close'), onclick: close, html: '&times;' }),
    ]),
    el('div.modal-body', {}, [typeof body === 'function' ? body(close) : body]),
  ]);
  if (footer) {
    modal.append(el('div.modal-footer', {}, [typeof footer === 'function' ? footer(close) : footer]));
  }

  backdrop.append(modal);
  backdrop.addEventListener('mousedown', (event) => { if (event.target === backdrop) close(); });
  document.addEventListener('keydown', onKey);
  document.body.style.overflow = 'hidden';
  document.body.append(backdrop);

  // Focus the first input so keyboard users can start typing immediately.
  setTimeout(() => modal.querySelector('input, select, textarea')?.focus(), 40);
  return { close, modal };
}

export function confirmDialog(message, { danger = true, confirmLabel } = {}) {
  return new Promise((resolve) => {
    const { close } = openModal({
      title: t('confirm_delete').split('.')[0],
      size: 'narrow',
      body: el('p', { text: message || t('confirm_delete') }),
      footer: (dismiss) => el('div.row', {}, [
        el('button.btn.btn-secondary', { type: 'button', text: t('cancel'), onclick: () => { dismiss(); resolve(false); } }),
        el(`button.btn${danger ? '.btn-danger' : ''}`, {
          type: 'button', text: confirmLabel || t('delete'),
          onclick: () => { dismiss(); resolve(true); },
        }),
      ]),
      onClose: () => resolve(false),
    });
    void close;
  });
}

// ------------------------------------------------------------------- forms
/**
 * field({ name, label, type, value, options, required, ... })
 * Returns a .field wrapper whose input carries `name` for form collection.
 */
export function field({
  name, label, type = 'text', value = '', options, required = false,
  placeholder = '', hint = '', min, max, step, rows, disabled = false, dir,
}) {
  let input;
  if (type === 'select') {
    input = el('select', { name, disabled });
    for (const option of options || []) {
      const node = el('option', { value: option.value, text: option.label });
      if (String(option.value) === String(value ?? '')) node.selected = true;
      input.append(node);
    }
  } else if (type === 'textarea') {
    input = el('textarea', { name, placeholder, disabled, rows: rows || 3 });
    input.value = value ?? '';
  } else if (type === 'checkbox') {
    input = el('input', { type: 'checkbox', name, disabled });
    input.checked = Boolean(value);
    return el('div.field', {}, [
      el('label.checkbox', {}, [input, el('span', { text: label })]),
      hint ? el('div.hint', { text: hint }) : null,
    ]);
  } else {
    input = el('input', { type, name, placeholder, disabled, min, max, step });
    input.value = value ?? '';
    if (type === 'number') input.classList.add('num');
  }
  if (required) input.required = true;
  if (dir) input.dir = dir;

  return el('div.field', {}, [
    label ? el('label', { for: name }, [
      label,
      required ? el('span', { style: { color: 'var(--danger-600)' }, text: ' *' }) : null,
    ]) : null,
    input,
    hint ? el('div.hint', { text: hint }) : null,
  ]);
}

/** Reads every named control inside `root` into a plain object. */
export function readForm(root) {
  const data = {};
  for (const input of root.querySelectorAll('[name]')) {
    if (input.type === 'checkbox') data[input.name] = input.checked;
    else if (input.type === 'number') data[input.name] = input.value === '' ? null : Number(input.value);
    else data[input.name] = input.value === '' ? null : input.value;
  }
  return data;
}

/** Builds <option> data from a list of i18n keys, e.g. status_target. */
export const optionsFrom = (values, prefix) =>
  values.map((value) => ({ value, label: t(`${prefix}${value}`) }));

export const blankOption = (label) => ({ value: '', label: label ?? t('all') });

// ------------------------------------------------------------------ badges
const STAGE_COLOURS = {
  new: 'grey', qualified: 'blue', quoted: 'blue',
  negotiation: 'orange', won: 'green', lost: 'red',
};
const QUOTE_COLOURS = {
  draft: 'grey', sent: 'blue', under_review: 'orange',
  approved: 'green', rejected: 'red', expired: 'amber', cancelled: 'grey',
};
const CUSTOMER_COLOURS = {
  target: 'amber', prospect: 'blue', active: 'green',
  dormant: 'grey', blacklisted: 'red',
};

export const stageBadge = (stage) =>
  el('span.badge', { class: STAGE_COLOURS[stage] || 'grey', text: t(`stage_${stage}`) });

export const quoteStatusBadge = (status) =>
  el('span.badge', { class: QUOTE_COLOURS[status] || 'grey', text: t(`qstatus_${status}`) });

export const customerStatusBadge = (status) =>
  el('span.badge', { class: CUSTOMER_COLOURS[status] || 'grey', text: t(`status_${status}`) });

export const countryBadge = (code) =>
  el('span.badge.blue', { text: t(`country_${code}`) });

export const stars = (rating) =>
  el('span.stars', { text: '★'.repeat(Math.max(0, Math.min(5, Number(rating) || 0))).padEnd(5, '☆') });

export const initials = (name) => String(name || '?')
  .trim().split(/\s+/).slice(0, 2).map((part) => part[0] || '').join('').toUpperCase();

// ----------------------------------------------------------------- tables
/**
 * dataTable({ columns, rows, onRowClick, empty })
 * columns: [{ key, label, className, render(row) }]
 */
export function dataTable({ columns, rows, onRowClick, empty, footer }) {
  if (!rows || rows.length === 0) {
    return el('div.empty', {}, [icon('empty', 40), el('div', { text: empty || t('no_data') })]);
  }
  const head = el('tr', {}, columns.map((column) =>
    el('th', { class: column.className || '', text: column.label })));

  const body = el('tbody', {}, rows.map((row) => {
    const tr = el('tr', { class: onRowClick ? 'clickable' : '' }, columns.map((column) => {
      const cell = el('td', { class: column.className || '' });
      const content = column.render ? column.render(row) : row[column.key];
      if (content instanceof Node) cell.append(content);
      else cell.textContent = content ?? '—';
      return cell;
    }));
    if (onRowClick) {
      tr.addEventListener('click', (event) => {
        // Let buttons inside a row do their own thing.
        if (event.target.closest('button, a, input')) return;
        onRowClick(row);
      });
    }
    return tr;
  }));

  const table = el('table.data', {}, [el('thead', {}, [head]), body]);
  if (footer) table.append(el('tfoot', {}, [footer]));
  return el('div.table-wrap', {}, [table]);
}

export const loadingBlock = () => el('div.loading-page', { text: t('loading') });

export const pageHeader = (title, actions = []) =>
  el('div.toolbar', {}, [el('h1', { style: { margin: 0 }, text: title }), el('div.spacer'), ...actions]);

/** Keeps a document title in step with the active language. */
export const setTitle = (text) => {
  document.title = `${text} · ${getLang() === 'ar' ? 'سبان تك' : 'Span Tech'}`;
};
