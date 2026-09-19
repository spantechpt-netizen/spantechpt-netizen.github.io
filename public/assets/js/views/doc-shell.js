/**
 * The frame every printed design shares.
 *
 * A design renders a body and its CSS; this wraps them in a window with the
 * toolbar and the behaviour the study deck already had: print, an edit mode
 * in which every element marked `data-e` is a text field, hide buttons on
 * every section marked `data-sec`, save back to the quotation, restore the
 * generated wording, and — for slide designs — a presentation mode.
 *
 * Edits are keyed with the design's own prefix, so switching designs keeps
 * what was rewritten on each, and only the sentences a person actually
 * changed are stored: improving the generated wording later still reaches
 * the documents nobody touched.
 */
import { esc } from '../ui.js';

/** Digits and money the way every design prints them: Latin, grouped. */
export const money = (value, digits = 2) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

export const formatDate = (value) => {
  if (!value) return '—';
  const [year, month, day] = String(value).slice(0, 10).split('-');
  return `${day}/${month}/${year}`;
};

/** A Latin run inside an Arabic line keeps its order and its plus sign. */
export const ltr = (value) => (value ? `⁦${value}⁩` : '');

/** A string destined for a CSS `content:` property. */
export const cssString = (value) => String(value ?? '')
  .replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\r?\n/g, '\\A ');

/** JSON for a script block: a closing tag inside a string would end it. */
const json = (value) => JSON.stringify(value).replace(/</g, '\\u003c');

const WORDS = {
  ar: {
    present: 'وضع العرض', print: 'طباعة / حفظ PDF', close: 'إغلاق',
    hint_keys: 'الأسهم للتنقل · Esc للخروج',
    edit: 'تعديل النص', save: 'حفظ التعديلات', reset: 'رجوع للنص الأصلي', done: 'تم',
    edit_hint: 'دوس على أي جملة وغيّرها. زرار الإخفاء بيشيل القسم من المطبوع.',
    hide: 'إخفاء', show: 'إظهار',
    saved: 'التعديلات اتحفظت', failed: 'التعديلات ماتحفظتش',
    unsaved: 'في تعديلات لسه ما اتحفظتش. تقفل برضه؟',
    reset_ask: 'هترجّع كل النصوص لأصلها وتظهر كل الأقسام. تمام؟',
    popup: 'الرجاء السماح بالنوافذ المنبثقة لفتح المستند.',
  },
  en: {
    present: 'Present', print: 'Print / Save as PDF', close: 'Close',
    hint_keys: 'Arrow keys to move · Esc to exit',
    edit: 'Edit text', save: 'Save changes', reset: 'Restore original text', done: 'Done',
    edit_hint: 'Click any sentence and change it. The hide button drops a section from the print.',
    hide: 'Hide', show: 'Show',
    saved: 'Changes saved', failed: 'Could not save the changes',
    unsaved: 'You have unsaved changes. Close anyway?',
    reset_ask: 'This puts every sentence back as generated and shows every section. Go ahead?',
    popup: 'Please allow pop-ups to open the document.',
  },
};

/**
 * The helpers a design writes its content through.
 *
 *   ed.txt('title', 'Cost study')  → escaped text, the edited version if any
 *   ed.mark('title')               → the attribute that makes it editable
 *   ed.sec('cover')                → attributes for a hideable section
 *   ed.toggle('cover')             → the hide/show button for that section
 */
export function createEditor(edits, prefix) {
  const overrides = (edits && edits.text) || {};
  const hidden = (edits && edits.hidden) || {};
  const generated = {};
  const k = (key) => `${prefix}.${key}`;

  const txt = (key, value) => {
    const source = value == null ? '' : String(value);
    generated[k(key)] = source;
    const override = overrides[k(key)];
    return esc(override == null ? source : override);
  };
  return {
    prefix,
    key: k,
    generated,
    hidden,
    mark: (key) => `data-e="${k(key)}"`,
    txt,
    prose: (key, value) => txt(key, value).replace(/\n/g, '<br>'),
    /** Attributes for a section that can be dropped from the document. */
    sec: (key) => `data-sec="${k(key)}"${hidden[k(key)] ? ' class="is-off"' : ''}`,
    isHidden: (key) => Boolean(hidden[k(key)]),
    toggle: (key) => `<button type="button" class="sec-toggle" data-toggle="${k(key)}"></button>`,
  };
}

/**
 * Opens the finished document in a new window.
 *
 *   openDocument({ lang, title, css, body, editor, api, presentable, fonts })
 *
 * `api` is the absolute URL the edits are PUT to; without it the document is
 * read-only. `presentable` adds the slide controls and expects each slide to
 * be a `[data-sec].slide` element.
 */
export function openDocument({
  lang = 'ar', title, css, body, editor, api = '', presentable = false, existingText = {},
  printOnLoad = false, bodyClass = '',
}) {
  const html = buildDocument({ lang, title, css, body, editor, api, presentable, existingText, bodyClass });
  const win = window.open('', '_blank');
  if (!win) {
    alert(WORDS[lang].popup);
    return null;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
  if (printOnLoad) win.addEventListener('load', () => setTimeout(() => win.print(), 400));
  return win;
}

export function buildDocument({ lang, title, css, body, editor, api, presentable, existingText, bodyClass }) {
  const W = WORDS[lang] || WORDS.ar;
  const isAr = lang === 'ar';
  const canSave = Boolean(api);

  return `<!doctype html>
<html lang="${lang}" dir="${isAr ? 'rtl' : 'ltr'}">
<head>
<meta charset="utf-8">
<title>${esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Inter:wght@400;500;600;700;800;900&family=Tajawal:wght@400;500;700;800&display=swap">
<style>
${css}

  /* ------------------------------------------------------------ the frame */
  .shell-bar {
    position: sticky; top: 0; z-index: 40; display: flex; gap: .5rem; justify-content: center; flex-wrap: wrap;
    padding: 10px; background: #0a2647; font-family: ${isAr ? "'Cairo', Tahoma, sans-serif" : "'Inter', 'Segoe UI', sans-serif"};
  }
  .shell-bar button {
    padding: 7px 18px; border: 0; border-radius: 6px; background: #fff; color: #0a2647;
    font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .shell-bar button.gold { background: #d3a95c; color: #0a2647; }
  .shell-bar button.ghost { background: transparent; color: #fff; box-shadow: inset 0 0 0 1px rgba(255,255,255,.45); }
  .shell-bar .grp { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; justify-content: center; }
  .shell-bar .hint { color: #b9cbe4; font-size: 12.5px; }
  .shell-bar .flash { color: #f2c879; font-size: 12.5px; font-weight: 700; }
  .shell-bar .bar-edit { display: none; }
  body.editing .shell-bar .bar-edit { display: flex; }
  body.editing .shell-bar .bar-view { display: none; }

  /* ---------------------------------------------------------- editing text */
  body.editing [data-e] { outline: 1px dashed #a9bfd8; outline-offset: 3px; border-radius: 3px; cursor: text; }
  body.editing [data-e]:hover { background: rgba(201,162,39,.14); }
  body.editing [data-e]:focus { outline: 2px solid #d3a95c; background: rgba(201,162,39,.10); }

  [data-sec] { position: relative; }
  .sec-toggle {
    display: none; position: absolute; z-index: 6; top: 6px; inset-inline-end: 6px;
    padding: 3px 12px; border: 0; border-radius: 14px; background: #0a2647; color: #fff;
    font-family: inherit; font-size: 11px; font-weight: 700; cursor: pointer;
  }
  body.editing .sec-toggle { display: inline-block; }
  /* A dropped section stays while editing so it can come back; otherwise it is gone. */
  body:not(.editing) [data-sec].is-off { display: none !important; }
  body.editing [data-sec].is-off { opacity: .4; filter: grayscale(1); }
  body.editing [data-sec].is-off .sec-toggle { background: #d3a95c; color: #0a2647; }

  /* ------------------------------------------------------------ presenting */
  body.present { background: #05101f; overflow: hidden; }
  body.present .shell-bar { display: none; }
  body.present .slide {
    visibility: hidden; position: fixed; inset: 0; margin: auto;
    transform: scale(var(--k, 1)); transform-origin: center; box-shadow: 0 16px 70px rgba(0,0,0,.65);
  }
  body.present .slide.on { visibility: visible; }
  .hud { display: none; position: fixed; z-index: 60; bottom: 16px; inset-inline-start: 50%;
         transform: translateX(${isAr ? '50%' : '-50%'}); align-items: center; gap: 10px;
         padding: 7px 12px; border-radius: 30px; background: rgba(8,22,40,.82); color: #cfe0f2;
         font-size: 12.5px; backdrop-filter: blur(6px); font-family: inherit; }
  body.present .hud { display: flex; }
  .hud button { padding: 4px 12px; border: 0; border-radius: 6px; background: #fff; color: #0a2647; font-weight: 700; cursor: pointer; font-family: inherit; }
  .hud .n { direction: ltr; unicode-bidi: isolate; font-weight: 800; color: #fff; }

  @media print {
    .shell-bar, .hud, .sec-toggle { display: none !important; }
    [data-sec].is-off { display: none !important; }
    body.present { overflow: visible; background: #fff; }
    body.present .slide { visibility: visible !important; position: static !important; transform: none !important; margin: 0 !important; box-shadow: none; }
  }
</style>
</head>
<body class="${esc(bodyClass)}">
<div class="shell-bar">
  <span class="grp bar-view">
    ${canSave ? `<button type="button" id="btn-edit">${esc(W.edit)}</button>` : ''}
    ${presentable ? `<button type="button" class="gold" id="btn-present">${esc(W.present)}</button>` : ''}
    <button type="button" id="btn-print">${esc(W.print)}</button>
    <button type="button" class="ghost" id="btn-close">${esc(W.close)}</button>
  </span>
  <span class="grp bar-edit">
    <button type="button" class="gold" id="btn-save">${esc(W.save)}</button>
    <button type="button" class="ghost" id="btn-reset">${esc(W.reset)}</button>
    <button type="button" class="ghost" id="btn-done">${esc(W.done)}</button>
    <span class="hint">${esc(W.edit_hint)}</span>
    <span class="flash" id="flash"></span>
  </span>
</div>
${body}
${presentable ? `
<div class="hud" id="hud">
  <button type="button" id="btn-prev">‹</button>
  <span class="n" id="hud-n">1</span>
  <button type="button" id="btn-next">›</button>
  <span class="hint">${esc(W.hint_keys)}</span>
  <button type="button" id="btn-exit">${esc(W.close)}</button>
</div>` : ''}
<script>
window.SHELL = {
  api: ${json(api)},
  prefix: ${json(editor ? editor.prefix : '')},
  generated: ${json(editor ? editor.generated : {})},
  hidden: ${json(editor ? editor.hidden : {})},
  existingText: ${json(existingText || {})},
  presentable: ${presentable ? 'true' : 'false'},
  words: ${json({ hide: W.hide, show: W.show, saved: W.saved, failed: W.failed, unsaved: W.unsaved, resetAsk: W.reset_ask })}
};
</script>
<script>
(function () {
  var S = window.SHELL;
  var WORDS = S.words;
  var hiddenState = S.hidden || {};
  var sections = Array.prototype.slice.call(document.querySelectorAll('[data-sec]'));
  var slides = sections.filter(function (s) { return s.classList.contains('slide'); });
  var fields = Array.prototype.slice.call(document.querySelectorAll('[data-e]'));
  var flash = document.getElementById('flash');
  var editing = false, dirty = false, live = false, index = 0;

  // Every hideable section gets its button, placed by the design or here.
  sections.forEach(function (section) {
    var key = section.getAttribute('data-sec');
    if (!section.querySelector('.sec-toggle[data-toggle="' + key + '"]')) {
      var b = document.createElement('button');
      b.type = 'button'; b.className = 'sec-toggle'; b.setAttribute('data-toggle', key);
      section.appendChild(b);
    }
  });
  function relabel() {
    sections.forEach(function (section) {
      var b = section.querySelector('.sec-toggle');
      if (b) b.textContent = section.classList.contains('is-off') ? WORDS.show : WORDS.hide;
    });
    var shownSlides = shown();
    shownSlides.forEach(function (slide, i) {
      var pg = slide.querySelector('.pg');
      if (pg) pg.textContent = (i + 1 < 10 ? '0' : '') + (i + 1) + ' / ' + (shownSlides.length < 10 ? '0' : '') + shownSlides.length;
    });
  }
  function say(message) {
    if (!flash) return;
    flash.textContent = message;
    setTimeout(function () { if (flash.textContent === message) flash.textContent = ''; }, 3000);
  }

  // ---------------------------------------------------------------- editing
  function setEdit(on) {
    editing = on;
    document.body.classList.toggle('editing', on);
    fields.forEach(function (f) { if (on) f.setAttribute('contenteditable', 'true'); else f.removeAttribute('contenteditable'); });
    if (on) window.scrollTo({ top: 0 });
  }
  function collect() {
    // Other designs' wording travels along untouched; this design's is rebuilt.
    var text = {};
    Object.keys(S.existingText || {}).forEach(function (key) {
      if (key.indexOf(S.prefix + '.') !== 0) text[key] = S.existingText[key];
    });
    fields.forEach(function (field) {
      var key = field.getAttribute('data-e');
      var value = field.innerText.replace(/\\u00a0/g, ' ').trim();
      if (value && value !== String(S.generated[key] || '').trim()) text[key] = value;
    });
    return { template: S.prefix, text: text, hidden: hiddenState };
  }
  function save() {
    fetch(S.api, { method: 'PUT', credentials: 'include', headers: { 'content-type': 'application/json' }, body: JSON.stringify(collect()) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); dirty = false; say(WORDS.saved); })
      .catch(function () { say(WORDS.failed); });
  }
  function reset() {
    if (!window.confirm(WORDS.resetAsk)) return;
    fields.forEach(function (f) { var key = f.getAttribute('data-e'); if (S.generated[key] != null) f.innerText = S.generated[key]; });
    sections.forEach(function (section) { delete hiddenState[section.getAttribute('data-sec')]; section.classList.remove('is-off'); });
    dirty = true;
    relabel();
  }

  // ------------------------------------------------------------- presenting
  function shown() { return slides.filter(function (s) { return !s.classList.contains('is-off'); }); }
  function fit() {
    var slide = shown()[index];
    if (!slide) return;
    var k = Math.min(window.innerWidth / slide.offsetWidth, window.innerHeight / slide.offsetHeight);
    document.documentElement.style.setProperty('--k', k);
  }
  function show(next) {
    var list = shown();
    if (!list.length) return;
    index = Math.max(0, Math.min(list.length - 1, next));
    list.forEach(function (s) { s.classList.remove('on'); });
    list[index].classList.add('on');
    var counter = document.getElementById('hud-n');
    if (counter) counter.textContent = (index + 1) + ' / ' + list.length;
    fit();
  }
  function start() {
    if (editing) setEdit(false);
    live = true;
    document.body.classList.add('present');
    show(index);
    if (document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(function () {});
  }
  function stop() {
    live = false;
    document.body.classList.remove('present');
    slides.forEach(function (s) { s.classList.remove('on'); });
    if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(function () {});
    var current = shown()[index];
    if (current) current.scrollIntoView({ block: 'center' });
  }

  // ---------------------------------------------------------------- wiring
  var on = function (id, fn) { var b = document.getElementById(id); if (b) b.addEventListener('click', fn); };
  on('btn-edit', function () { setEdit(true); });
  on('btn-save', save);
  on('btn-reset', reset);
  on('btn-done', function () { setEdit(false); });
  on('btn-print', function () { window.print(); });
  on('btn-present', start);
  on('btn-exit', stop);
  on('btn-next', function () { show(index + 1); });
  on('btn-prev', function () { show(index - 1); });
  on('btn-close', function () { if (dirty && !window.confirm(WORDS.unsaved)) return; dirty = false; window.close(); });

  document.addEventListener('input', function (e) { if (e.target.hasAttribute && e.target.hasAttribute('data-e')) dirty = true; });
  document.addEventListener('click', function (e) {
    var toggle = e.target.closest && e.target.closest('.sec-toggle');
    if (toggle) {
      var section = toggle.closest('[data-sec]');
      var key = toggle.getAttribute('data-toggle');
      var off = section.classList.toggle('is-off');
      if (off) hiddenState[key] = true; else delete hiddenState[key];
      dirty = true;
      relabel();
      return;
    }
    if (!live || editing) return;
    if (e.target.closest && e.target.closest('.hud')) return;
    show(index + 1);
  });
  document.addEventListener('keydown', function (e) {
    if (editing && !live) return;
    if (!live) { if (S.presentable && (e.key === 'p' || e.key === 'P')) start(); return; }
    var key = e.key;
    if (key === 'ArrowRight' || key === 'ArrowDown' || key === ' ' || key === 'PageDown') { show(index + 1); e.preventDefault(); }
    else if (key === 'ArrowLeft' || key === 'ArrowUp' || key === 'PageUp') { show(index - 1); e.preventDefault(); }
    else if (key === 'Home') show(0);
    else if (key === 'End') show(shown().length - 1);
    else if (key === 'Escape') stop();
  });
  window.addEventListener('beforeunload', function (e) { if (!dirty) return undefined; e.preventDefault(); e.returnValue = ''; return ''; });
  window.addEventListener('resize', fit);
  relabel();
})();
</script>
</body>
</html>`;
}
