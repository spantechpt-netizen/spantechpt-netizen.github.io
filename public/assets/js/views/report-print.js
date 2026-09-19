/**
 * A printable report: the data on screen laid out as an A4 document, opened
 * in a new window where the browser's print dialogue saves it as a PDF.
 *
 * The same mechanism prints the quotation and the cost study, and it is the
 * only way to a PDF that keeps Arabic shaping and the company fonts without
 * a rendering library on the server.
 *
 *   printReport({
 *     lang, title, subtitle, meta: [[label, value], ...],
 *     sections: [
 *       { heading, kpis: [{ label, value, meta }] },
 *       { heading, columns: [{ label, className }], rows: [[cell, ...]] },
 *     ],
 *   })
 */
import { esc } from '../ui.js';

const WORDS = {
  ar: { generated: 'تاريخ الإصدار', print: 'طباعة / حفظ PDF', close: 'إقفال', empty: 'مفيش بيانات', page: 'صفحة' },
  en: { generated: 'Generated', print: 'Print / save as PDF', close: 'Close', empty: 'No data', page: 'Page' },
};

export function printReport({ lang = 'ar', title, subtitle = '', meta = [], sections = [], landscape = false }) {
  const html = buildReport({ lang, title, subtitle, meta, sections, landscape });
  const win = window.open('', '_blank');
  if (!win) {
    alert(lang === 'ar' ? 'الرجاء السماح بالنوافذ المنبثقة لفتح التقرير.' : 'Please allow pop-ups to open the report.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
}

function buildReport({ lang, title, subtitle, meta, sections, landscape }) {
  const W = WORDS[lang] || WORDS.ar;
  const rtl = lang === 'ar';
  const now = new Date();
  const stamp = `${String(now.getDate()).padStart(2, '0')}/${String(now.getMonth() + 1).padStart(2, '0')}/${now.getFullYear()} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;

  const cell = (value) => {
    if (value === null || value === undefined) return '—';
    if (typeof value === 'object' && value.html) return value.html;
    return esc(value);
  };

  const section = (s) => {
    if (s.kpis) {
      return `<section class="sec">
        ${s.heading ? `<h2>${esc(s.heading)}</h2>` : ''}
        <div class="kpis">${s.kpis.map((k) => `
          <div class="kpi"><div class="l">${esc(k.label)}</div><div class="v">${esc(k.value)}</div>${k.meta ? `<div class="m">${esc(k.meta)}</div>` : ''}</div>`).join('')}
        </div></section>`;
    }
    const rows = s.rows || [];
    return `<section class="sec">
      ${s.heading ? `<h2>${esc(s.heading)}</h2>` : ''}
      ${rows.length ? `<table>
        <thead><tr>${s.columns.map((c) => `<th class="${c.className || ''}">${esc(c.label)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map((r) => `<tr>${r.map((v, i) => `<td class="${s.columns[i]?.className || ''}">${cell(v)}</td>`).join('')}</tr>`).join('')}</tbody>
        ${s.footer ? `<tfoot><tr>${s.footer.map((v, i) => `<td class="${s.columns[i]?.className || ''}">${cell(v)}</td>`).join('')}</tr></tfoot>` : ''}
      </table>` : `<p class="empty">${W.empty}</p>`}
    </section>`;
  };

  return `<!doctype html>
<html lang="${lang}" dir="${rtl ? 'rtl' : 'ltr'}">
<head>
<meta charset="utf-8">
<title>${esc(title)}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&family=Inter:wght@400;600;700&display=swap" media="print" onload="this.media='all'">
<style>
  @page { size: A4 ${landscape ? 'landscape' : 'portrait'}; margin: 16mm 14mm 18mm; }
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ${rtl ? "'Cairo', 'Segoe UI', Tahoma, sans-serif" : "'Inter', 'Segoe UI', Arial, sans-serif"}; color: #111827; font-size: 12px; line-height: 1.5; background: #f3f4f6; }
  .toolbar { position: sticky; top: 0; display: flex; gap: .5rem; align-items: center; padding: .6rem 1rem; background: #0a2647; color: #fff; }
  .toolbar button { font: inherit; padding: .4rem .9rem; border: 0; border-radius: 6px; cursor: pointer; background: #fff; color: #0a2647; font-weight: 600; }
  .toolbar button.ghost { background: transparent; color: #fff; border: 1px solid rgba(255,255,255,.4); }
  .toolbar .spacer { flex: 1; }
  .page { max-width: ${landscape ? '1120px' : '820px'}; margin: 1rem auto; background: #fff; padding: 18mm 16mm; box-shadow: 0 2px 12px rgba(0,0,0,.08); }
  header.head { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; border-bottom: 3px solid #1a56a7; padding-bottom: .6rem; margin-bottom: 1rem; }
  header.head h1 { margin: 0; font-size: 20px; color: #0a2647; }
  header.head .sub { color: #374151; font-size: 12px; margin-top: .15rem; }
  header.head .brand { font-weight: 800; color: #1a56a7; font-size: 14px; letter-spacing: .04em; white-space: nowrap; }
  .meta { display: flex; flex-wrap: wrap; gap: .3rem 1.4rem; font-size: 11px; color: #374151; margin-bottom: 1rem; }
  .meta b { color: #111827; }
  h2 { font-size: 13.5px; color: #0a2647; margin: 1.1rem 0 .45rem; padding-bottom: .2rem; border-bottom: 1px solid #e5e7eb; break-after: avoid; }
  .sec { break-inside: avoid; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; }
  .kpi { border: 1px solid #e5e7eb; border-inline-start: 3px solid #1a56a7; border-radius: 6px; padding: .5rem .7rem; }
  .kpi .l { font-size: 10px; color: #6b7280; text-transform: uppercase; letter-spacing: .03em; font-weight: 600; }
  .kpi .v { font-size: 17px; font-weight: 700; direction: ltr; unicode-bidi: plaintext; text-align: start; }
  .kpi .m { font-size: 10.5px; color: #6b7280; }
  table { width: 100%; border-collapse: collapse; font-size: 11.5px; }
  th { text-align: start; background: #f3f4f6; color: #374151; font-weight: 700; padding: .38rem .5rem; border-bottom: 1px solid #d1d5db; }
  td { padding: .36rem .5rem; border-bottom: 1px solid #f3f4f6; vertical-align: top; }
  tfoot td { font-weight: 700; border-top: 2px solid #d1d5db; background: #f9fafb; }
  .num { text-align: end; direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; white-space: nowrap; }
  tr { break-inside: avoid; }
  .empty { color: #9ca3af; font-style: italic; }
  footer.foot { margin-top: 1.4rem; padding-top: .5rem; border-top: 1px solid #e5e7eb; font-size: 10px; color: #6b7280; display: flex; justify-content: space-between; }
  @media print {
    body { background: #fff; }
    .toolbar { display: none; }
    .page { max-width: none; margin: 0; padding: 0; box-shadow: none; }
  }
</style>
</head>
<body>
  <div class="toolbar">
    <button type="button" onclick="window.print()">${W.print}</button>
    <span class="spacer"></span>
    <button type="button" class="ghost" onclick="window.close()">${W.close}</button>
  </div>
  <div class="page">
    <header class="head">
      <div>
        <h1>${esc(title)}</h1>
        ${subtitle ? `<div class="sub">${esc(subtitle)}</div>` : ''}
      </div>
      <div class="brand">SPAN TECH</div>
    </header>
    ${meta.length ? `<div class="meta">${meta.map(([k, v]) => `<span><b>${esc(k)}:</b> ${esc(v)}</span>`).join('')}</div>` : ''}
    ${sections.map(section).join('')}
    <footer class="foot"><span>${esc(title)}</span><span>${W.generated}: ${stamp}</span></footer>
  </div>
</body>
</html>`;
}
