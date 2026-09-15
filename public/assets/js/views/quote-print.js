/**
 * Renders a quotation as a print-ready A4 document in Arabic or English and
 * opens it in a new window for printing / saving as PDF.
 *
 * The layout is deliberately fixed — only the variable data changes between
 * offers — so every quotation that leaves the company looks identical.
 */
import { esc } from '../ui.js';

const money = (value, digits = 2) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const formatDate = (value) => {
  if (!value) return '—';
  const [year, month, day] = value.slice(0, 10).split('-');
  return `${day}/${month}/${year}`;
};

const SCOPE_ORDER = ['design', 'supply', 'installation', 'deliverables'];

const LABELS = {
  ar: {
    doc_title: 'عرض سعر — أعمال الأسقف اللاحقة للشد',
    doc_subtitle: 'Post-Tension Slabs',
    ref: 'رقم العرض', revision: 'المراجعة', date: 'التاريخ', valid_until: 'ساري حتى',
    to: 'السادة', attention: 'عناية', project: 'المشروع', location: 'الموقع',
    subject: 'الموضوع', greeting: 'تحية طيبة وبعد،',
    profile: 'نبذة عن الشركة', vision: 'رؤيتنا', mission: 'رسالتنا',
    scope: 'نطاق العمل — التزامات شركة سبان تك',
    requirements: 'متطلبات من المقاول الرئيسي / الاستشاري قبل البدء',
    exclusions: 'الأعمال غير المشمولة بالعرض',
    schedule: 'الجدول الزمني', team: 'فريق العمل', warranty: 'الضمانات وجودة التنفيذ',
    commercial: 'العرض المالي',
    boq_item: 'البند', boq_unit: 'الوحدة', boq_qty: 'الكمية',
    boq_rate: 'سعر الوحدة', boq_amount: 'الإجمالي',
    subtotal: 'الإجمالي قبل الضريبة', discount: 'الخصم', net: 'الصافي',
    vat: 'ضريبة القيمة المضافة', total: 'الإجمالي شامل الضريبة',
    in_words: 'المبلغ كتابةً', optional_items: 'بنود اختيارية (غير محتسبة في الإجمالي)',
    payment: 'شروط الدفع', payment_pct: 'النسبة', payment_desc: 'البيان', payment_amount: 'القيمة',
    conditions: 'الشروط والأحكام', notes: 'ملاحظات',
    price_note: 'ملاحظة السعر',
    closing: 'نؤكد التزامنا بأعلى معايير الجودة والسلامة، ونأمل أن ينال عرضنا قبولكم.',
    regards: 'مع خالص التحية والتقدير،',
    for_company: 'عن شركة سبان تك للمقاولات', for_client: 'الموافقة والاعتماد — العميل',
    name: 'الاسم', signature: 'التوقيع', stamp: 'الختم',
    page: 'صفحة', of: 'من', cr: 'سجل تجاري', vat_no: 'الرقم الضريبي',
    unit_price_line: 'سعر المتر المربع',
    currency_note: 'جميع القيم بعملة',
  },
  en: {
    doc_title: 'QUOTATION — POST-TENSIONED SLAB WORKS',
    doc_subtitle: 'Post-Tension Slabs',
    ref: 'Quotation No.', revision: 'Revision', date: 'Date', valid_until: 'Valid until',
    to: 'To', attention: 'Attention', project: 'Project', location: 'Location',
    subject: 'Subject', greeting: 'Dear Sir / Madam,',
    profile: 'Company Profile', vision: 'Our vision', mission: 'Our mission',
    scope: 'Scope of Work — Span Tech Obligations',
    requirements: 'By Main Contractor / Consultant (Prior to Commencement)',
    exclusions: 'Exclusions',
    schedule: 'Programme', team: 'Project Team', warranty: 'Warranty & Quality Assurance',
    commercial: 'Commercial Offer',
    boq_item: 'Description', boq_unit: 'Unit', boq_qty: 'Quantity',
    boq_rate: 'Unit Rate', boq_amount: 'Amount',
    subtotal: 'Subtotal', discount: 'Discount', net: 'Net amount',
    vat: 'VAT', total: 'Total including VAT',
    in_words: 'Amount in words', optional_items: 'Optional items (not included in the total)',
    payment: 'Payment Terms', payment_pct: '%', payment_desc: 'Milestone', payment_amount: 'Value',
    conditions: 'Terms & Conditions', notes: 'Notes',
    price_note: 'Price basis',
    closing: 'We confirm our commitment to the highest standards of quality and safety, and trust that our offer meets your approval.',
    regards: 'With our best regards,',
    for_company: 'For Span Tech Contracting Co.', for_client: 'Client Acceptance & Approval',
    name: 'Name', signature: 'Signature', stamp: 'Stamp',
    page: 'Page', of: 'of', cr: 'CR', vat_no: 'VAT No.',
    unit_price_line: 'Rate per square metre',
    currency_note: 'All values in',
  },
};

export function printQuotation(document_, lang = 'ar') {
  const html = buildDocument(document_, lang);
  const win = window.open('', '_blank');
  if (!win) {
    alert(lang === 'ar'
      ? 'الرجاء السماح بالنوافذ المنبثقة لطباعة العرض.'
      : 'Please allow pop-ups to print the quotation.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
  // Give the fonts and the logo a moment before the print dialog appears.
  win.addEventListener('load', () => setTimeout(() => win.print(), 350));
}

function buildDocument(data, lang) {
  const isAr = lang === 'ar';
  const L = LABELS[lang];
  const q = data.quotation;
  const company = data.company || {};
  const dir = isAr ? 'rtl' : 'ltr';

  const pickText = (entry) => (isAr ? entry.ar : entry.en) || entry.en || entry.ar || '';
  const enabled = (items) => (items || []).filter((item) => item.enabled !== false);

  const projectName = (isAr ? q.project_name_ar : q.project_name) || q.project_name;
  const customerName = (isAr ? q.customer_name_ar : q.customer_name) || q.customer_name;
  const attention = (isAr ? q.attention_ar : q.attention) || q.attention || q.contact_name || '';
  const location = (isAr ? q.location_ar : q.location) || q.location || '';
  const subject = (isAr ? q.subject_ar : q.subject_en) || '';
  const notes = (isAr ? q.notes_ar : q.notes_en) || '';
  const words = isAr ? q.total_words_ar : q.total_words_en;

  const billable = (q.items || []).filter((item) => !item.is_optional);
  const optional = (q.items || []).filter((item) => item.is_optional);

  // The headline rate, taken from the largest m² line so it always agrees
  // with the table below it — the mismatch we saw in the old offer.
  const mainItem = [...billable].sort((a, b) => Number(b.qty) - Number(a.qty))[0];

  const itemRow = (item) => `
    <tr>
      <td class="desc">${esc(isAr ? (item.desc_ar || item.desc_en) : (item.desc_en || item.desc_ar))}</td>
      <td class="c">${esc(isAr ? (item.unit_ar || item.unit_en) : (item.unit_en || item.unit_ar))}</td>
      <td class="n">${money(item.qty, 0)}</td>
      <td class="n">${money(item.unit_price)}</td>
      <td class="n b">${money(item.amount)}</td>
    </tr>`;

  const scopeSections = SCOPE_ORDER
    .map((key, index) => {
      const section = q.scope?.[key];
      const items = enabled(section?.items);
      if (!section || !items.length) return '';
      return `
        <div class="scope-block">
          <h3><span class="idx">${index + 1}</span>${esc(isAr ? section.title_ar : section.title_en)}</h3>
          <ul>${items.map((item) => `<li>${esc(pickText(item))}</li>`).join('')}</ul>
        </div>`;
    })
    .join('');

  const bulletList = (key, title) => {
    const section = q.scope?.[key];
    const items = enabled(section?.items);
    if (!items.length) return '';
    return `
      <section class="block">
        <h2>${esc(title)}</h2>
        <ul class="two-col">${items.map((item) => `<li>${esc(pickText(item))}</li>`).join('')}</ul>
      </section>`;
  };

  const paymentRows = (q.payment_terms || []).map((term, index) => `
    <tr>
      <td class="c">${index + 1}</td>
      <td class="c b">${Number(term.pct || 0)}%</td>
      <td>${esc(pickText(term))}</td>
      <td class="n">${money((Number(term.pct || 0) / 100) * Number(q.total || 0))}</td>
    </tr>`).join('');

  const conditionItems = (q.conditions || [])
    .map((condition) => `<li>${esc(pickText(condition))}</li>`)
    .join('');

  const priceClause = isAr ? data.price_clause?.ar : data.price_clause?.en;
  const intro = (isAr ? data.intro?.ar : data.intro?.en) || '';
  const profile = isAr ? company.profile_ar : company.profile_en;

  return `<!doctype html>
<html lang="${lang}" dir="${dir}">
<head>
<meta charset="utf-8">
<title>${esc(q.number)}${q.revision ? ` R${q.revision}` : ''} — ${esc(projectName)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap">
<style>
  @page { size: A4; margin: 14mm 13mm 16mm; }

  :root {
    --brand: #0a2647;
    --brand-mid: #1a56a7;
    --brand-light: #e8f0fa;
    --line: #c8d3e0;
    --grey: #5b6775;
    --ink: #17202b;
  }

  * { box-sizing: border-box; }

  body {
    margin: 0;
    font-family: ${isAr
      ? "'Cairo','Tajawal','Segoe UI','Noto Naskh Arabic',Tahoma,sans-serif"
      : "'Inter','Segoe UI',system-ui,Arial,sans-serif"};
    font-size: 10.2pt;
    line-height: 1.62;
    color: var(--ink);
    background: #f1f3f6;
  }

  .sheet {
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto;
    padding: 14mm 13mm 16mm;
    background: #fff;
  }
  @media print {
    body { background: #fff; }
    .sheet { width: auto; min-height: 0; margin: 0; padding: 0; }
    .no-print { display: none !important; }
  }

  /* ------------------------------------------------------------- toolbar */
  .toolbar {
    position: sticky; top: 0; z-index: 10;
    display: flex; gap: .5rem; justify-content: center;
    padding: 10px; background: var(--brand);
  }
  .toolbar button {
    padding: 7px 18px; border: 0; border-radius: 5px;
    background: #fff; color: var(--brand);
    font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .toolbar button.ghost { background: transparent; color: #fff; box-shadow: inset 0 0 0 1px rgba(255,255,255,.5); }

  /* -------------------------------------------------------------- header */
  .letterhead {
    display: flex; align-items: center; gap: 14px;
    padding-bottom: 9px; margin-bottom: 12px;
    border-bottom: 2.5px solid var(--brand);
  }
  .letterhead img { height: 46px; width: auto; }
  .letterhead .who { flex: 1; }
  .letterhead .who .n { font-size: 14pt; font-weight: 800; color: var(--brand); line-height: 1.25; }
  .letterhead .who .t { font-size: 8.6pt; color: var(--grey); letter-spacing: .02em; }
  .letterhead .meta { text-align: ${isAr ? 'left' : 'right'}; font-size: 8.2pt; color: var(--grey); line-height: 1.5; direction: ltr; }

  .doc-title {
    padding: 7px 12px; margin-bottom: 12px;
    background: var(--brand); color: #fff; border-radius: 3px;
    text-align: center;
  }
  .doc-title h1 { margin: 0; font-size: 12.5pt; font-weight: 800; letter-spacing: .02em; }
  .doc-title .sub { font-size: 8.4pt; opacity: .85; letter-spacing: .12em; text-transform: uppercase; direction: ltr; }

  /* ------------------------------------------------------- reference grid */
  .ref-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 0;
    margin-bottom: 13px; border: 1px solid var(--line);
  }
  .ref-grid > div { padding: 7px 10px; }
  .ref-grid .left { border-${isAr ? 'left' : 'right'}: 1px solid var(--line); }
  .ref-grid .bg { background: var(--brand-light); }
  .ref-line { display: flex; gap: 6px; font-size: 9.4pt; }
  .ref-line + .ref-line { margin-top: 2px; }
  .ref-line .k { min-width: 74px; font-weight: 700; color: var(--brand); }
  .ref-line .v { flex: 1; }
  .ref-line .v.mono { font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: plaintext; }

  /* -------------------------------------------------------------- blocks */
  .block { margin-bottom: 13px; }
  h2 {
    margin: 0 0 6px; padding: 4px 9px;
    background: var(--brand-light);
    border-${isAr ? 'right' : 'left'}: 3px solid var(--brand-mid);
    font-size: 10.6pt; font-weight: 800; color: var(--brand);
  }
  h3 { margin: 0 0 3px; font-size: 9.8pt; font-weight: 700; color: var(--brand-mid); }
  p { margin: 0 0 6px; text-align: justify; }

  ul { margin: 0 0 6px; padding-${isAr ? 'right' : 'left'}: 16px; }
  li { margin-bottom: 2px; }
  ul.two-col { column-count: 2; column-gap: 16px; }
  ul.two-col li { break-inside: avoid; }

  .scope-block { margin-bottom: 8px; break-inside: avoid; }
  .scope-block h3 { display: flex; align-items: center; gap: 6px; }
  .scope-block .idx {
    display: inline-grid; place-items: center;
    width: 17px; height: 17px; border-radius: 50%;
    background: var(--brand-mid); color: #fff;
    font-size: 8pt; font-weight: 700;
  }

  .intro { padding: 8px 10px; background: #fafbfd; border: 1px solid var(--line); border-radius: 3px; }

  .pill-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 7px; }
  .pill {
    padding: 2px 8px; border-radius: 10px;
    background: var(--brand-light); color: var(--brand);
    font-size: 8.3pt; font-weight: 700;
  }

  /* -------------------------------------------------------------- tables */
  table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
  table.boq th {
    padding: 6px 8px; background: var(--brand); color: #fff;
    font-size: 8.8pt; font-weight: 700; text-align: ${isAr ? 'right' : 'left'};
    border: 1px solid var(--brand);
  }
  table.boq td { padding: 6px 8px; border: 1px solid var(--line); vertical-align: top; }
  table.boq tbody tr:nth-child(even) { background: #fafbfd; }
  table.boq .c { text-align: center; }
  table.boq .n { text-align: ${isAr ? 'left' : 'right'}; font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: plaintext; }
  table.boq .b { font-weight: 700; }
  table.boq .desc { width: 46%; }

  .totals { width: 58%; margin-${isAr ? 'right' : 'left'}: auto; margin-top: 8px; }
  .totals td { padding: 4px 9px; border: 1px solid var(--line); font-size: 9.6pt; }
  .totals td:first-child { font-weight: 600; background: #fafbfd; }
  .totals td:last-child { text-align: ${isAr ? 'left' : 'right'}; font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: plaintext; }
  .totals tr.grand td { background: var(--brand); color: #fff; font-size: 11pt; font-weight: 800; border-color: var(--brand); }

  .words {
    margin-top: 7px; padding: 7px 10px;
    background: var(--brand-light); border-radius: 3px;
    font-size: 9.6pt; font-weight: 700; color: var(--brand);
  }
  .words .k { font-weight: 800; }

  .headline {
    display: flex; align-items: baseline; gap: 8px;
    padding: 8px 12px; margin-bottom: 9px;
    background: var(--brand-light);
    border-${isAr ? 'right' : 'left'}: 3px solid var(--brand-mid); border-radius: 3px;
  }
  .headline .k { font-size: 9.6pt; font-weight: 700; color: var(--brand); }
  .headline .v { font-size: 15pt; font-weight: 800; color: var(--brand); font-variant-numeric: tabular-nums; direction: ltr; unicode-bidi: plaintext; }

  .note {
    padding: 6px 10px; margin-top: 8px;
    background: #fff8e8; border: 1px solid #e8d5a8; border-radius: 3px;
    font-size: 9pt;
  }
  .note .k { font-weight: 800; color: #8a5a00; }

  /* ------------------------------------------------------------ signature */
  .signatures {
    display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
    margin-top: 16px; break-inside: avoid;
  }
  .sig { padding: 9px 11px; border: 1px solid var(--line); border-radius: 3px; }
  .sig .h { margin-bottom: 20px; font-size: 9.6pt; font-weight: 800; color: var(--brand); }
  .sig .l { display: flex; gap: 6px; margin-bottom: 11px; font-size: 9pt; }
  .sig .l .k { min-width: 52px; color: var(--grey); }
  .sig .l .line { flex: 1; border-bottom: 1px dotted var(--line); }

  .closing { margin-top: 12px; break-inside: avoid; }
  .regards { margin-top: 10px; font-weight: 700; color: var(--brand); }

  .footer {
    margin-top: 14px; padding-top: 6px;
    border-top: 1px solid var(--line);
    font-size: 7.8pt; color: var(--grey); text-align: center;
  }

  .avoid-break { break-inside: avoid; }
  .money-group { break-inside: avoid; }
  table.boq thead { display: table-header-group; }  /* repeat headers across pages */
  table.boq tr { break-inside: avoid; }
</style>
</head>
<body>

<div class="toolbar no-print">
  <button onclick="window.print()">${isAr ? 'طباعة / حفظ PDF' : 'Print / Save as PDF'}</button>
  <button class="ghost" onclick="window.close()">${isAr ? 'إغلاق' : 'Close'}</button>
</div>

<div class="sheet">

  <div class="letterhead">
    <img src="/assets/img/logo.png" alt="Span Tech">
    <div class="who">
      <div class="n">${esc(isAr ? company.name_ar : company.name_en)}</div>
      <div class="t">${esc(isAr ? company.tagline_ar : company.tagline_en)}</div>
    </div>
    <div class="meta">
      ${company.cr_number ? `${esc(L.cr)}: ${esc(company.cr_number)}<br>` : ''}
      ${company.vat_number ? `${esc(L.vat_no)}: ${esc(company.vat_number)}<br>` : ''}
      ${company.phone ? `${esc(company.phone)}<br>` : ''}
      ${company.email ? `${esc(company.email)}` : ''}
    </div>
  </div>

  <div class="doc-title">
    <h1>${esc(L.doc_title)}</h1>
    <div class="sub">${esc(L.doc_subtitle)}</div>
  </div>

  <div class="ref-grid">
    <div class="left">
      <div class="ref-line"><span class="k">${esc(L.to)}</span><span class="v">${esc(customerName)}</span></div>
      ${attention ? `<div class="ref-line"><span class="k">${esc(L.attention)}</span><span class="v">${esc(attention)}</span></div>` : ''}
      <div class="ref-line"><span class="k">${esc(L.project)}</span><span class="v">${esc(projectName)}</span></div>
      ${location ? `<div class="ref-line"><span class="k">${esc(L.location)}</span><span class="v">${esc(location)}</span></div>` : ''}
    </div>
    <div class="bg">
      <div class="ref-line"><span class="k">${esc(L.ref)}</span><span class="v mono">${esc(q.number)}${q.revision ? ` / R${q.revision}` : ''}</span></div>
      <div class="ref-line"><span class="k">${esc(L.date)}</span><span class="v mono">${formatDate(q.issue_date)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.valid_until)}</span><span class="v mono">${formatDate(q.valid_until)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.currency_note)}</span><span class="v mono">${esc(q.currency)}</span></div>
    </div>
  </div>

  ${subject ? `<div class="ref-line" style="margin-bottom:10px"><span class="k">${esc(L.subject)}</span><span class="v">${esc(subject)}</span></div>` : ''}

  <p style="font-weight:700">${esc(L.greeting)}</p>
  <div class="intro block"><p style="margin:0">${esc(intro)}</p></div>

  ${profile && profile.length ? `
  <section class="block avoid-break">
    <h2>${esc(L.profile)}</h2>
    <ul>${profile.map((line) => `<li>${esc(line)}</li>`).join('')}</ul>
    <div class="pill-row">
      ${company.vision_en || company.vision_ar ? `<span class="pill">${esc(L.vision)}: ${esc(isAr ? company.vision_ar : company.vision_en)}</span>` : ''}
      ${company.mission_en || company.mission_ar ? `<span class="pill">${esc(L.mission)}: ${esc(isAr ? company.mission_ar : company.mission_en)}</span>` : ''}
    </div>
  </section>` : ''}

  ${scopeSections ? `
  <section class="block">
    <h2>${esc(L.scope)}</h2>
    ${scopeSections}
  </section>` : ''}

  ${bulletList('requirements', L.requirements)}
  ${bulletList('exclusions', L.exclusions)}
  ${bulletList('schedule', L.schedule)}
  ${bulletList('team', L.team)}
  ${bulletList('warranty', L.warranty)}

  <section class="block">
    <h2>${esc(L.commercial)}</h2>

    ${mainItem ? `
    <div class="headline">
      <span class="k">${esc(L.unit_price_line)}</span>
      <span class="v">${money(mainItem.unit_price)} ${esc(q.currency)} / ${esc(isAr ? (mainItem.unit_ar || 'م²') : (mainItem.unit_en || 'm²'))}</span>
    </div>` : ''}

    <table class="boq">
      <thead>
        <tr>
          <th class="desc">${esc(L.boq_item)}</th>
          <th class="c">${esc(L.boq_unit)}</th>
          <th class="c">${esc(L.boq_qty)}</th>
          <th class="c">${esc(L.boq_rate)}</th>
          <th class="c">${esc(L.boq_amount)}</th>
        </tr>
      </thead>
      <tbody>${billable.map(itemRow).join('')}</tbody>
    </table>

    <div class="money-group">
    <table class="totals">
      <tbody>
        <tr><td>${esc(L.subtotal)}</td><td>${money(q.subtotal)} ${esc(q.currency)}</td></tr>
        ${Number(q.discount_amount) > 0 ? `<tr><td>${esc(L.discount)}</td><td>− ${money(q.discount_amount)} ${esc(q.currency)}</td></tr>
        <tr><td>${esc(L.net)}</td><td>${money(q.net_amount)} ${esc(q.currency)}</td></tr>` : ''}
        <tr><td>${esc(L.vat)} (${Number(q.vat_rate)}%)</td><td>${money(q.vat_amount)} ${esc(q.currency)}</td></tr>
        <tr class="grand"><td>${esc(L.total)}</td><td>${money(q.total)} ${esc(q.currency)}</td></tr>
      </tbody>
    </table>

    <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(words)}</div>
    </div>

    ${optional.length ? `
    <h3 style="margin-top:10px">${esc(L.optional_items)}</h3>
    <table class="boq">
      <tbody>${optional.map(itemRow).join('')}</tbody>
    </table>` : ''}

    ${priceClause ? `<div class="note"><span class="k">${esc(L.price_note)}:</span> ${esc(priceClause)}</div>` : ''}
  </section>

  ${paymentRows ? `
  <section class="block avoid-break">
    <h2>${esc(L.payment)}</h2>
    <table class="boq">
      <thead>
        <tr>
          <th class="c" style="width:7%">#</th>
          <th class="c" style="width:12%">${esc(L.payment_pct)}</th>
          <th>${esc(L.payment_desc)}</th>
          <th class="c" style="width:22%">${esc(L.payment_amount)} (${esc(q.currency)})</th>
        </tr>
      </thead>
      <tbody>${paymentRows}</tbody>
    </table>
  </section>` : ''}

  ${conditionItems ? `
  <section class="block avoid-break">
    <h2>${esc(L.conditions)}</h2>
    <ul>${conditionItems}</ul>
  </section>` : ''}

  ${notes ? `
  <section class="block avoid-break">
    <h2>${esc(L.notes)}</h2>
    <p>${esc(notes).replace(/\n/g, '<br>')}</p>
  </section>` : ''}

  <div class="closing">
    <p>${esc(L.closing)}</p>
    <div class="regards">${esc(L.regards)}</div>
  </div>

  <div class="signatures">
    <div class="sig">
      <div class="h">${esc(L.for_company)}</div>
      <div class="l"><span class="k">${esc(L.name)}</span><span class="line">${esc(isAr ? (q.owner_name_ar || q.owner_name || '') : (q.owner_name || ''))}</span></div>
      <div class="l"><span class="k">${esc(L.signature)}</span><span class="line"></span></div>
      <div class="l"><span class="k">${esc(L.stamp)}</span><span class="line"></span></div>
    </div>
    <div class="sig">
      <div class="h">${esc(L.for_client)}</div>
      <div class="l"><span class="k">${esc(L.name)}</span><span class="line"></span></div>
      <div class="l"><span class="k">${esc(L.signature)}</span><span class="line"></span></div>
      <div class="l"><span class="k">${esc(L.date)}</span><span class="line"></span></div>
    </div>
  </div>

  <div class="footer">
    ${esc(isAr ? company.name_ar : company.name_en)}
    ${company.address_en || company.address_ar ? ` · ${esc(isAr ? company.address_ar : company.address_en)}` : ''}
    ${company.phone ? ` · ${esc(company.phone)}` : ''}
    ${company.email ? ` · ${esc(company.email)}` : ''}
    <br>${esc(q.number)}${q.revision ? ` / R${q.revision}` : ''} · ${formatDate(q.issue_date)}
  </div>

</div>
</body>
</html>`;
}
