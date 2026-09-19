/**
 * The quotation in six designs.
 *
 * The figures, the scope and the terms are the quotation's own whichever
 * design is chosen; what changes is how they are laid out on the page. Every
 * sentence a design generates can be rewritten on the document and saved,
 * and any section can be dropped from the print — the edits are kept per
 * design, so switching designs loses nothing.
 *
 *   letter     the formal letter: letterhead, introduction, table, terms
 *   compact    a two-column first page with the figures in a navy rail
 *   proposal   a cover and numbered chapters, like a tender submission
 *   boq        the bill of quantities first: codes, units, totals, signatures
 *   summary    one page: the total, includes / excludes, three facts
 *   premium    a dark cover, a company page, then the offer on white
 */
import { esc } from '../ui.js';
import { openDocument, createEditor, money, formatDate, ltr, cssString } from './doc-shell.js';

export const QUOTE_DESIGNS = [
  { id: 'letter', ar: 'الخطاب الرسمي', en: 'Formal letter' },
  { id: 'compact', ar: 'الحديث المضغوط', en: 'Compact' },
  { id: 'proposal', ar: 'العرض التجاري', en: 'Commercial proposal' },
  { id: 'boq', ar: 'جدول الكميات', en: 'Bill of quantities' },
  { id: 'summary', ar: 'البطاقة الموجزة', en: 'One-page summary' },
  { id: 'premium', ar: 'الفاخر', en: 'Premium' },
];

const SCOPE_ORDER = ['design', 'supply', 'installation', 'deliverables'];

const LABELS = {
  ar: {
    doc_title: 'عرض سعر — أعمال الأسقف اللاحقة للشد', doc_subtitle: 'Post-Tension Slabs',
    quotation: 'عرض سعر', works: 'أعمال الأسقف اللاحقة للشد',
    ref: 'رقم العرض', revision: 'المراجعة', date: 'التاريخ', valid_until: 'ساري حتى', validity: 'صلاحية العرض',
    to: 'السادة', attention: 'عناية', project: 'المشروع', location: 'الموقع', subject: 'الموضوع',
    greeting: 'تحية طيبة وبعد،', prepared_for: 'مقدّم إلى', quotation_for: 'عرض سعر لـ',
    profile: 'نبذة عن الشركة', about: 'عن سبان تك', vision: 'رؤيتنا', mission: 'رسالتنا',
    scope: 'نطاق العمل — التزامات شركة سبان تك', scope_short: 'نطاق العمل',
    requirements: 'متطلبات من المقاول الرئيسي / الاستشاري قبل البدء', required_short: 'مطلوب منكم',
    exclusions: 'الأعمال غير المشمولة بالعرض', schedule: 'الجدول الزمني', team: 'فريق العمل',
    warranty: 'الضمانات وجودة التنفيذ', commercial: 'العرض المالي', specs: 'المواصفات',
    we_deliver: 'ماذا نقدّم', includes: 'يشمل', excludes: 'لا يشمل',
    boq_title: 'جدول كميات وأسعار', code: 'م', boq_item: 'البند', boq_desc: 'الوصف', boq_unit: 'الوحدة',
    boq_qty: 'الكمية', boq_rate: 'سعر الوحدة', boq_amount: 'الإجمالي',
    group_main: 'أعمال الشد اللاحق — الأسقف', group_optional: 'بنود اختيارية',
    subtotal: 'الإجمالي قبل الضريبة', discount: 'الخصم', net: 'الصافي', vat: 'ضريبة القيمة المضافة',
    total: 'الإجمالي شامل الضريبة', total_short: 'الإجمالي', incl_vat: 'شامل الضريبة', of_which_vat: 'منها ضريبة',
    before_vat: 'قبل الضريبة', area: 'المساحة', rate: 'سعر المتر', unit_price_line: 'سعر المتر المربع',
    in_words: 'المبلغ كتابةً', optional_items: 'بنود اختيارية (غير محتسبة في الإجمالي)',
    payment: 'شروط الدفع', payment_pct: 'النسبة', payment_desc: 'البيان', payment_amount: 'القيمة', payment_split: 'نسب الدفع %',
    conditions: 'الشروط والأحكام', notes: 'ملاحظات', price_note: 'ملاحظة السعر', strand_limit: 'حد تغيّر سعر الكابل',
    closing: 'نؤكد التزامنا بأعلى معايير الجودة والسلامة، ونأمل أن ينال عرضنا قبولكم.',
    regards: 'مع خالص التحية والتقدير،', for_company: 'عن', for_client: 'الموافقة والاعتماد — العميل',
    prepared_by: 'إعداد', approved_by: 'اعتماد', technical_manager: 'المدير الفني', client_approval: 'موافقة العميل',
    name_sign_stamp: 'الاسم والتوقيع والختم', name: 'الاسم', signature: 'التوقيع', stamp: 'الختم',
    page: 'صفحة', of: 'من', cr: 'سجل تجاري', vat_no: 'الرقم الضريبي', page_note: 'أرقام الصفحات تظهر على النسخة المطبوعة',
    currency_note: 'جميع القيم بعملة', days: 'أيام', day_one: 'يوم',
    ch_summary: 'الملخص', ch_scope: 'النطاق', ch_specs: 'المواصفات', ch_price: 'السعر', ch_terms: 'الشروط',
    proposal_kicker: 'TECHNICAL & COMMERCIAL PROPOSAL', total_incl: 'إجمالي العرض شامل الضريبة',
    system: 'النظام', system_value: 'بوست تنشن مربوط (Bonded)', strands: 'الكابلات', strands_value: '12.7 مم · 1860 MPa', code_value: 'ACI 318 / ASTM A416',
    design_code: 'الكود',
    why_us: 'لماذا سبان تك',
    why_us_text: 'فريق تصميم وتنفيذ واحد، مواد بشهادات مصنع، وتقارير شد وحقن مع كل دور. ننفّذ في السعودية ومصر وقطر بنفس المعيار.',
    summary_foot: 'هذا الملخص جزء من العرض الكامل ويخضع لشروطه. الأسعار بالعملة المذكورة وغير شاملة أي رسوم أخرى.',
    included: 'مشمول', lump: 'مقطوعية', reports_line: 'تقارير الشد والحقن ومخططات ما تم تنفيذه',
    cover_regions: 'KSA · EGYPT · QATAR', total_cover: 'TOTAL · INCL. VAT', valid: 'ساري', continued: 'يتبع',
    contact: 'للتواصل', offer: 'العرض',
  },
  en: {
    doc_title: 'QUOTATION — POST-TENSIONED SLAB WORKS', doc_subtitle: 'Post-Tension Slabs',
    quotation: 'Quotation', works: 'Post-tensioned slab works',
    ref: 'Quotation No.', revision: 'Revision', date: 'Date', valid_until: 'Valid until', validity: 'Validity',
    to: 'To', attention: 'Attention', project: 'Project', location: 'Location', subject: 'Subject',
    greeting: 'Dear Sir / Madam,', prepared_for: 'Prepared for', quotation_for: 'Quotation for',
    profile: 'Company Profile', about: 'About Span Tech', vision: 'Our vision', mission: 'Our mission',
    scope: 'Scope of Work — Span Tech Obligations', scope_short: 'Scope of work',
    requirements: 'By Main Contractor / Consultant (Prior to Commencement)', required_short: 'Required from you',
    exclusions: 'Exclusions', schedule: 'Programme', team: 'Project Team',
    warranty: 'Warranty & Quality Assurance', commercial: 'Commercial Offer', specs: 'Specifications',
    we_deliver: 'What we deliver', includes: 'Includes', excludes: 'Excludes',
    boq_title: 'Bill of Quantities & Prices', code: '#', boq_item: 'Description', boq_desc: 'Description', boq_unit: 'Unit',
    boq_qty: 'Quantity', boq_rate: 'Unit Rate', boq_amount: 'Amount',
    group_main: 'Post-tensioning works — slabs', group_optional: 'Optional items',
    subtotal: 'Subtotal', discount: 'Discount', net: 'Net amount', vat: 'VAT',
    total: 'Total including VAT', total_short: 'Total', incl_vat: 'incl. VAT', of_which_vat: 'of which VAT',
    before_vat: 'Before VAT', area: 'Area', rate: 'Rate / m²', unit_price_line: 'Rate per square metre',
    in_words: 'Amount in words', optional_items: 'Optional items (not included in the total)',
    payment: 'Payment Terms', payment_pct: '%', payment_desc: 'Milestone', payment_amount: 'Value', payment_split: 'Payment split %',
    conditions: 'Terms & Conditions', notes: 'Notes', price_note: 'Price basis', strand_limit: 'Strand price variance',
    closing: 'We confirm our commitment to the highest standards of quality and safety, and trust that our offer meets your approval.',
    regards: 'With our best regards,', for_company: 'For', for_client: 'Client Acceptance & Approval',
    prepared_by: 'Prepared by', approved_by: 'Approved by', technical_manager: 'Technical Manager', client_approval: 'Client approval',
    name_sign_stamp: 'Name, signature and stamp', name: 'Name', signature: 'Signature', stamp: 'Stamp',
    page: 'Page', of: 'of', cr: 'CR', vat_no: 'VAT No.', page_note: 'Page numbers appear on the printed copy',
    currency_note: 'All values in', days: 'days', day_one: 'day',
    ch_summary: 'Summary', ch_scope: 'Scope', ch_specs: 'Specifications', ch_price: 'Price', ch_terms: 'Terms',
    proposal_kicker: 'TECHNICAL & COMMERCIAL PROPOSAL', total_incl: 'Offer total including VAT',
    system: 'System', system_value: 'Bonded post-tensioning', strands: 'Strands', strands_value: '12.7 mm · 1860 MPa', code_value: 'ACI 318 / ASTM A416',
    design_code: 'Code',
    why_us: 'Why Span Tech',
    why_us_text: 'One team from design to stressing, certified materials, and stressing and grouting reports with every floor. The same standard in Saudi Arabia, Egypt and Qatar.',
    summary_foot: 'This summary is part of the full offer and subject to its terms. Prices are in the stated currency and exclude any other fees.',
    included: 'Included', lump: 'LS', reports_line: 'Stressing and grouting reports and as-built drawings',
    cover_regions: 'KSA · EGYPT · QATAR', total_cover: 'TOTAL · INCL. VAT', valid: 'Valid', continued: 'continued',
    contact: 'Contact', offer: 'The offer',
  },
};

/** Everything a design needs, worked out once. */
function context(data, lang, ed) {
  const isAr = lang === 'ar';
  const L = LABELS[lang];
  const q = data.quotation;
  const company = data.company || {};
  const branch = data.branch || company;
  const pick = (ar, en) => (isAr ? ar : en) || en || ar || '';
  const pickText = (entry) => pick(entry.ar, entry.en);
  const enabled = (items) => (items || []).filter((item) => item.enabled !== false);

  const billable = (q.items || []).filter((item) => !item.is_optional);
  const optional = (q.items || []).filter((item) => item.is_optional);
  // The headline rate is the largest m² line, so it always agrees with the table.
  const mainItem = [...billable].sort((a, b) => Number(b.qty) - Number(a.qty))[0] || null;
  const currency = q.currency || '';
  const quoteRef = `${q.number}${q.revision ? ` / R${q.revision}` : ''}`;
  const branchName = pick(branch.name_ar || company.name_ar, branch.name_en || company.name_en);
  const branchAddress = pick(branch.address_ar, branch.address_en);
  const contactLine = [branch.phone, branch.email, branch.email_alt, branch.website].filter(Boolean).map(ltr).join(' · ');

  return {
    isAr, lang, L, q, company, branch, ed, pick, pickText, currency, billable, optional, mainItem, quoteRef, branchName, branchAddress, contactLine,
    dir: isAr ? 'rtl' : 'ltr',
    start: isAr ? 'right' : 'left',
    end: isAr ? 'left' : 'right',
    font: isAr ? "'Cairo','Tajawal','Segoe UI',Tahoma,sans-serif" : "'Inter','Segoe UI',Arial,sans-serif",
    projectName: pick(q.project_name_ar, q.project_name),
    customerName: pick(q.customer_name_ar, q.customer_name),
    attention: pick(q.attention_ar, q.attention) || q.contact_name || '',
    location: pick(q.location_ar, q.location),
    subject: pick(q.subject_ar, q.subject_en),
    notes: pick(q.notes_ar, q.notes_en),
    words: isAr ? q.total_words_ar : q.total_words_en,
    intro: pick(data.intro && data.intro.ar, data.intro && data.intro.en),
    priceClause: pick(data.price_clause && data.price_clause.ar, data.price_clause && data.price_clause.en),
    profile: (isAr ? company.profile_ar : company.profile_en) || [],
    vision: pick(company.vision_ar, company.vision_en),
    mission: pick(company.mission_ar, company.mission_en),
    tagline: pick(company.tagline_ar, company.tagline_en),
    legalForm: pick(company.legal_form_ar, company.legal_form_en),
    ownerName: pick(q.owner_name_ar, q.owner_name),
    ownerTitle: pick(q.owner_title_ar, q.owner_title),
    ownerPhone: q.owner_phone || '',
    logo: esc(branch.logo || '/assets/img/logo@2x.png'),
    scopeTitle: (key) => { const s = q.scope && q.scope[key]; return s ? pick(s.title_ar, s.title_en) : ''; },
    scopeItems: (key) => enabled(q.scope && q.scope[key] && q.scope[key].items).map(pickText),
    payments: (q.payment_terms || []).map((term) => ({ pct: Number(term.pct || 0), text: pickText(term) })),
    conditions: (q.conditions || []).map(pickText),
    cash: (v) => `${money(v)} ${currency}`,
    n0: (v) => money(v, 0),
    n2: (v) => money(v, 2),
    area: mainItem ? Number(mainItem.qty) : 0,
    unit: mainItem ? pick(mainItem.unit_ar, mainItem.unit_en) : (isAr ? 'م²' : 'm²'),
    rate: mainItem ? Number(mainItem.unit_price) : 0,
    itemDesc: (item) => pick(item.desc_ar, item.desc_en),
    itemUnit: (item) => pick(item.unit_ar, item.unit_en),
    paymentSplit: (q.payment_terms || []).map((term) => Number(term.pct || 0)).join(' / '),
    validDays: Number(q.valid_days || 0),
    variance: q.price_variance != null ? Number(q.price_variance) : null,
  };
}

// ------------------------------------------------------------------ pieces
/** The frame every A4 design starts from. */
const BASE_CSS = (c) => `
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ${c.font}; font-size: 10.2pt; line-height: 1.6; color: #17202b; background: #eef1f5;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .n { direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }
  table { width: 100%; border-collapse: collapse; }
  p { margin: 0 0 6px; }
  ul { margin: 0; padding-${c.start}: 16px; }
  li { margin-bottom: 2px; }
  .page { position: relative; width: 210mm; min-height: 297mm; margin: 8mm auto; padding: 14mm 13mm 16mm; background: #fff;
          box-shadow: 0 2px 14px rgba(10,38,71,.10); }
  .page.slide + .page.slide, .page + .page { margin-top: 8mm; }
  .break { break-before: page; }
  .avoid { break-inside: avoid; }
  @media print {
    body { background: #fff; }
    .page { width: auto; min-height: 0; margin: 0; padding: 0; box-shadow: none; break-after: page; }
    .page:last-of-type { break-after: auto; }
    thead { display: table-header-group; }
    tr { break-inside: avoid; }
  }
`;

/** Line items with an editable description; `codes` adds A.1 style numbering. */
function boqRows(c, items, { codes = '', keyPrefix = 'item' } = {}) {
  const { ed, n0, n2 } = c;
  return items.map((item, i) => `
    <tr>
      ${codes ? `<td class="c code n">${codes}.${i + 1}</td>` : ''}
      <td class="desc" ${ed.mark(`${keyPrefix}.${item.id || i}`)}>${ed.txt(`${keyPrefix}.${item.id || i}`, c.itemDesc(item))}</td>
      <td class="c">${esc(c.itemUnit(item))}</td>
      <td class="n">${n0(item.qty)}</td>
      <td class="n">${n2(item.unit_price)}</td>
      <td class="n b">${n2(item.amount)}</td>
    </tr>`).join('');
}

function boqHead(c, codes = false) {
  const { L } = c;
  return `<thead><tr>
    ${codes ? `<th class="c" style="width:7%">${esc(L.code)}</th>` : ''}
    <th class="desc">${esc(codes ? L.boq_desc : L.boq_item)}</th><th class="c">${esc(L.boq_unit)}</th>
    <th class="c">${esc(L.boq_qty)}</th><th class="c">${esc(L.boq_rate)}</th><th class="c">${esc(L.boq_amount)}</th>
  </tr></thead>`;
}

function totalsRows(c) {
  const { L, q, cash } = c;
  return `
    <tr><td>${esc(L.subtotal)}</td><td class="n">${cash(q.subtotal)}</td></tr>
    ${Number(q.discount_amount) > 0 ? `<tr><td>${esc(L.discount)}</td><td class="n">− ${cash(q.discount_amount)}</td></tr>
    <tr><td>${esc(L.net)}</td><td class="n">${cash(q.net_amount)}</td></tr>` : ''}
    <tr><td>${esc(L.vat)} (${Number(q.vat_rate)}%)</td><td class="n">${cash(q.vat_amount)}</td></tr>
    <tr class="grand"><td>${esc(L.total)}</td><td class="n">${cash(q.total)}</td></tr>`;
}

/** A bullet section from one scope list; nothing is drawn when the list is empty. */
function listSection(c, key, title, { cls = 'block', twoCol = true } = {}) {
  const { ed } = c;
  const items = c.scopeItems(key);
  if (!items.length) return '';
  return `
    <section class="${cls}" ${ed.sec(key)}>
      <h2 ${ed.mark(`h.${key}`)}>${ed.txt(`h.${key}`, title)}</h2>
      <ul class="${twoCol ? 'two-col' : ''}">${items.map((item, i) => `<li ${ed.mark(`${key}.${i}`)}>${ed.txt(`${key}.${i}`, item)}</li>`).join('')}</ul>
    </section>`;
}

function scopeBlocks(c) {
  const { ed } = c;
  return SCOPE_ORDER.map((key, index) => {
    const items = c.scopeItems(key);
    if (!items.length) return '';
    return `
      <div class="scope-block" ${ed.sec(`scope.${key}`)}>
        <h3><span class="idx n">${index + 1}</span><span ${ed.mark(`h.scope.${key}`)}>${ed.txt(`h.scope.${key}`, c.scopeTitle(key))}</span></h3>
        <ul>${items.map((item, i) => `<li ${ed.mark(`${key}.${i}`)}>${ed.txt(`${key}.${i}`, item)}</li>`).join('')}</ul>
      </div>`;
  }).join('');
}

function paymentTable(c) {
  const { L, q, ed, cash } = c;
  if (!c.payments.length) return '';
  return `
    <table class="boq">
      <thead><tr>
        <th class="c" style="width:7%">#</th><th class="c" style="width:12%">${esc(L.payment_pct)}</th>
        <th>${esc(L.payment_desc)}</th><th class="c" style="width:24%">${esc(L.payment_amount)} (${esc(c.currency)})</th>
      </tr></thead>
      <tbody>${c.payments.map((term, i) => `
        <tr><td class="c n">${i + 1}</td><td class="c b n">${term.pct}%</td>
        <td ${ed.mark(`pay.${i}`)}>${ed.txt(`pay.${i}`, term.text)}</td>
        <td class="n">${money((term.pct / 100) * Number(q.total || 0))}</td></tr>`).join('')}
      </tbody>
    </table>`;
}

function conditionsList(c, ordered = false) {
  const { ed } = c;
  const tag = ordered ? 'ol' : 'ul';
  return `<${tag}>${c.conditions.map((text, i) => `<li ${ed.mark(`cond.${i}`)}>${ed.txt(`cond.${i}`, text)}</li>`).join('')}</${tag}>`;
}

function signatures(c) {
  const { L, ed } = c;
  return `
    <div class="signatures" ${ed.sec('signatures')}>
      <div class="sig">
        <div class="h" ${ed.mark('sig.company')}>${ed.txt('sig.company', `${L.for_company} ${c.branchName}`)}</div>
        <div class="l"><span class="k">${esc(L.name)}</span><span class="line">${esc(c.ownerName)}</span></div>
        <div class="l"><span class="k">${esc(L.signature)}</span><span class="line"></span></div>
        <div class="l"><span class="k">${esc(L.stamp)}</span><span class="line"></span></div>
      </div>
      <div class="sig">
        <div class="h" ${ed.mark('sig.client')}>${ed.txt('sig.client', L.for_client)}</div>
        <div class="l"><span class="k">${esc(L.name)}</span><span class="line"></span></div>
        <div class="l"><span class="k">${esc(L.signature)}</span><span class="line"></span></div>
        <div class="l"><span class="k">${esc(L.date)}</span><span class="line"></span></div>
      </div>
    </div>`;
}

const closingBlock = (c) => `
    <div class="closing avoid" ${c.ed.sec('closing')}>
      <p ${c.ed.mark('closing')}>${c.ed.txt('closing', c.L.closing)}</p>
      <div class="regards" ${c.ed.mark('regards')}>${c.ed.txt('regards', c.L.regards)}</div>
    </div>`;

const notesBlock = (c) => (c.notes ? `
    <section class="block avoid" ${c.ed.sec('notes')}>
      <h2 ${c.ed.mark('h.notes')}>${c.ed.txt('h.notes', c.L.notes)}</h2>
      <p ${c.ed.mark('notes')}>${c.ed.prose('notes', c.notes)}</p>
    </section>` : '');

const priceNote = (c) => (c.priceClause ? `
    <div class="note" ${c.ed.sec('price_note')}><span class="k">${esc(c.L.price_note)}:</span> <span ${c.ed.mark('price_clause')}>${c.ed.txt('price_clause', c.priceClause)}</span></div>` : '');

/** The shared look of navy tables and section bars, used by letter, compact and proposal. */
const NAVY_CSS = (c) => `
  :root { --brand: #0a2647; --brand-mid: #1a56a7; --brand-light: #e8f0fa; --line: #c8d3e0; --grey: #5b6775; }
  h2 { margin: 0 0 6px; padding: 4px 9px; background: var(--brand-light); border-${c.start}: 3px solid var(--brand-mid);
       font-size: 10.6pt; font-weight: 800; color: var(--brand); }
  h3 { margin: 0 0 3px; font-size: 9.8pt; font-weight: 700; color: var(--brand-mid); }
  .block { margin-bottom: 13px; }
  ul.two-col { column-count: 2; column-gap: 16px; } ul.two-col li { break-inside: avoid; }
  .scope-block { margin-bottom: 8px; break-inside: avoid; }
  .scope-block h3 { display: flex; align-items: center; gap: 6px; }
  .scope-block .idx { display: inline-grid; place-items: center; width: 17px; height: 17px; border-radius: 50%;
                      background: var(--brand-mid); color: #fff; font-size: 8pt; font-weight: 700; }
  table.boq { font-size: 9.5pt; }
  table.boq th { padding: 6px 8px; background: var(--brand); color: #fff; font-size: 8.8pt; font-weight: 700; text-align: ${c.start}; border: 1px solid var(--brand); }
  table.boq td { padding: 6px 8px; border: 1px solid var(--line); vertical-align: top; }
  table.boq tbody tr:nth-child(even) { background: #fafbfd; }
  table.boq .c { text-align: center; } table.boq .n { text-align: ${c.end}; } table.boq .b { font-weight: 700; } table.boq .desc { width: 46%; }
  .totals { width: 58%; margin-${c.start}: auto; margin-top: 8px; }
  .totals td { padding: 4px 9px; border: 1px solid var(--line); font-size: 9.6pt; }
  .totals td:first-child { font-weight: 600; background: #fafbfd; } .totals td:last-child { text-align: ${c.end}; }
  .totals tr.grand td { background: var(--brand); color: #fff; font-size: 11pt; font-weight: 800; border-color: var(--brand); }
  .words { margin-top: 7px; padding: 7px 10px; background: var(--brand-light); border-radius: 3px; font-size: 9.6pt; font-weight: 700; color: var(--brand); }
  .headline { display: flex; align-items: baseline; gap: 8px; padding: 8px 12px; margin-bottom: 9px; background: var(--brand-light);
              border-${c.start}: 3px solid var(--brand-mid); border-radius: 3px; }
  .headline .k { font-size: 9.6pt; font-weight: 700; color: var(--brand); }
  .headline .v { font-size: 15pt; font-weight: 800; color: var(--brand); }
  .note { padding: 6px 10px; margin-top: 8px; background: #fff8e8; border: 1px solid #e8d5a8; border-radius: 3px; font-size: 9pt; }
  .note .k { font-weight: 800; color: #8a5a00; }
  .signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 16px; break-inside: avoid; }
  .sig { padding: 9px 11px; border: 1px solid var(--line); border-radius: 3px; }
  .sig .h { margin-bottom: 20px; font-size: 9.6pt; font-weight: 800; color: var(--brand); }
  .sig .l { display: flex; gap: 6px; margin-bottom: 11px; font-size: 9pt; }
  .sig .l .k { min-width: 52px; color: var(--grey); } .sig .l .line { flex: 1; border-bottom: 1px dotted var(--line); }
  .closing { margin-top: 12px; } .regards { margin-top: 10px; font-weight: 700; color: var(--brand); }
`;

// ------------------------------------------------------------------- letter
function letter(c) {
  const { L, q, ed, isAr, company, branch } = c;
  const footContact = [c.branchAddress, c.contactLine].filter(Boolean).join('\n');
  const runHeadRef = [ltr(c.quoteRef), c.projectName].filter(Boolean).join('  —  ');
  const pageCounter = `"${cssString(L.page)} " counter(page) " ${cssString(L.of)} " counter(pages)`;

  const css = `${BASE_CSS(c)}${NAVY_CSS(c)}
  /* The running header and footer live in @page margin boxes, so the browser
     repeats them on every sheet with a real "3 of 5". Page one carries the
     letterhead, so the :first rule drops the running header there. */
  @page {
    size: A4; margin: 20mm 13mm 19mm; font-family: ${c.font}; font-size: 7.4pt; color: #5b6775;
    @top-${c.start} { content: "${cssString(c.branchName)}"; vertical-align: bottom; padding-bottom: 3mm; border-bottom: .6pt solid #c8d3e0; font-weight: 700; color: #0a2647; }
    @top-center { content: ""; vertical-align: bottom; padding-bottom: 3mm; border-bottom: .6pt solid #c8d3e0; }
    @top-${c.end} { content: "${cssString(runHeadRef)}"; vertical-align: bottom; padding-bottom: 3mm; border-bottom: .6pt solid #c8d3e0; }
    @bottom-${c.start} { content: "${cssString(ltr(c.quoteRef))} · ${cssString(ltr(formatDate(q.issue_date)))}"; white-space: nowrap; vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0; }
    @bottom-center { content: "${cssString(footContact)}"; white-space: pre-line; text-align: center; vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0; }
    @bottom-${c.end} { content: ${pageCounter}; vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0; font-weight: 700; color: #0a2647; }
  }
  @page :first { margin-top: 14mm; @top-left { content: ""; border: 0; } @top-center { content: ""; border: 0; } @top-right { content: ""; border: 0; } }
  body { background: #f1f3f6; }
  .page { z-index: 0; padding: 14mm 13mm 19mm; }
  .watermark { position: fixed; inset: 0; z-index: -1; display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .watermark img { width: 118mm; height: auto; opacity: .042; filter: grayscale(1); }
  .letterhead { display: flex; align-items: center; gap: 14px; padding-bottom: 9px; margin-bottom: 12px; border-bottom: 2.5px solid var(--brand); }
  .letterhead img { max-height: 62px; max-width: 58mm; }
  .letterhead .who { flex: 1; }
  .letterhead .who .nm { font-size: 14pt; font-weight: 800; color: var(--brand); line-height: 1.25; }
  .letterhead .who .t { font-size: 8.6pt; color: var(--grey); } .letterhead .who .f { font-size: 7.8pt; color: var(--grey); }
  .letterhead .meta { text-align: ${c.end}; font-size: 8.2pt; color: var(--grey); line-height: 1.5; direction: ltr; }
  .doc-title { padding: 7px 12px; margin-bottom: 12px; background: var(--brand); color: #fff; border-radius: 3px; text-align: center; }
  .doc-title h1 { margin: 0; font-size: 12.5pt; font-weight: 800; }
  .doc-title .sub { font-size: 8.4pt; opacity: .85; letter-spacing: .12em; text-transform: uppercase; direction: ltr; }
  .ref-grid { display: grid; grid-template-columns: 1fr 1fr; margin-bottom: 13px; border: 1px solid var(--line); }
  .ref-grid > div { padding: 7px 10px; } .ref-grid .left { border-${c.end}: 1px solid var(--line); } .ref-grid .bg { background: var(--brand-light); }
  .ref-line { display: flex; gap: 6px; font-size: 9.4pt; } .ref-line + .ref-line { margin-top: 2px; }
  .ref-line .k { min-width: 74px; font-weight: 700; color: var(--brand); } .ref-line .v { flex: 1; }
  .intro { padding: 8px 10px; background: #fafbfd; border: 1px solid var(--line); border-radius: 3px; }
  .pill-row { display: flex; flex-wrap: wrap; gap: 5px; margin: 6px 0; }
  .pill { padding: 2px 8px; border-radius: 10px; background: var(--brand-light); color: var(--brand); font-size: 8.3pt; font-weight: 700; }
  .footer { display: flex; gap: 10px; margin-top: 16px; padding-top: 6px; border-top: 1px solid var(--line); font-size: 7.4pt; color: var(--grey); }
  .footer > div:nth-child(2) { flex: 1; text-align: center; } .footer .page-note { font-style: italic; opacity: .8; }
  @media print { .screen-only { display: none !important; } .page { padding: 0; } }
  `;

  const body = `
<div class="page">
  <div class="watermark" aria-hidden="true"><img src="${c.logo}" alt=""></div>

  <div class="letterhead" ${ed.sec('letterhead')}>
    <img src="${c.logo}" alt="${esc(c.branchName)}">
    <div class="who">
      <div class="nm" ${ed.mark('brand')}>${ed.txt('brand', c.branchName)}</div>
      <div class="t" ${ed.mark('tagline')}>${ed.txt('tagline', c.tagline)}</div>
      ${c.legalForm ? `<div class="f" ${ed.mark('legal')}>${ed.txt('legal', c.legalForm)}</div>` : ''}
    </div>
    ${branch.cr_number || branch.vat_number ? `<div class="meta">
      ${branch.cr_number ? `<div>${esc(c.pick(branch.registration_label_ar, branch.registration_label_en) || L.cr)}: <b>${esc(branch.cr_number)}</b></div>` : ''}
      ${branch.vat_number ? `<div>${esc(L.vat_no)}: <b>${esc(branch.vat_number)}</b></div>` : ''}
    </div>` : ''}
  </div>

  <div class="doc-title">
    <h1 ${ed.mark('title')}>${ed.txt('title', L.doc_title)}</h1>
    <div class="sub" ${ed.mark('subtitle')}>${ed.txt('subtitle', L.doc_subtitle)}</div>
  </div>

  <div class="ref-grid">
    <div class="left">
      <div class="ref-line"><span class="k">${esc(L.to)}</span><span class="v" ${ed.mark('to')}>${ed.txt('to', c.customerName)}</span></div>
      ${c.attention ? `<div class="ref-line"><span class="k">${esc(L.attention)}</span><span class="v" ${ed.mark('attention')}>${ed.txt('attention', c.attention)}</span></div>` : ''}
      <div class="ref-line"><span class="k">${esc(L.project)}</span><span class="v" ${ed.mark('project')}>${ed.txt('project', c.projectName)}</span></div>
      ${c.location ? `<div class="ref-line"><span class="k">${esc(L.location)}</span><span class="v" ${ed.mark('location')}>${ed.txt('location', c.location)}</span></div>` : ''}
    </div>
    <div class="bg">
      <div class="ref-line"><span class="k">${esc(L.ref)}</span><span class="v n">${esc(c.quoteRef)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.date)}</span><span class="v n">${formatDate(q.issue_date)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.valid_until)}</span><span class="v n">${formatDate(q.valid_until)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.currency_note)}</span><span class="v n">${esc(c.currency)}</span></div>
    </div>
  </div>

  ${c.subject ? `<div class="ref-line" style="margin-bottom:10px"><span class="k">${esc(L.subject)}</span><span class="v" ${ed.mark('subject')}>${ed.txt('subject', c.subject)}</span></div>` : ''}

  <div ${ed.sec('intro')}>
    <p style="font-weight:700" ${ed.mark('greeting')}>${ed.txt('greeting', L.greeting)}</p>
    <div class="intro block"><p style="margin:0" ${ed.mark('intro')}>${ed.txt('intro', c.intro)}</p></div>
  </div>

  ${c.profile.length ? `
  <section class="block avoid" ${ed.sec('profile')}>
    <h2 ${ed.mark('h.profile')}>${ed.txt('h.profile', L.profile)}</h2>
    <ul>${c.profile.map((line, i) => `<li ${ed.mark(`profile.${i}`)}>${ed.txt(`profile.${i}`, line)}</li>`).join('')}</ul>
    <div class="pill-row">
      ${c.vision ? `<span class="pill">${esc(L.vision)}: <span ${ed.mark('vision')}>${ed.txt('vision', c.vision)}</span></span>` : ''}
      ${c.mission ? `<span class="pill">${esc(L.mission)}: <span ${ed.mark('mission')}>${ed.txt('mission', c.mission)}</span></span>` : ''}
    </div>
  </section>` : ''}

  <section class="block" ${ed.sec('scope')}>
    <h2 ${ed.mark('h.scope')}>${ed.txt('h.scope', L.scope)}</h2>
    ${scopeBlocks(c)}
  </section>

  ${listSection(c, 'requirements', L.requirements)}
  ${listSection(c, 'exclusions', L.exclusions)}
  ${listSection(c, 'schedule', L.schedule)}
  ${listSection(c, 'team', L.team)}
  ${listSection(c, 'warranty', L.warranty)}

  <section class="block">
    <h2 ${ed.mark('h.commercial')}>${ed.txt('h.commercial', L.commercial)}</h2>
    ${c.mainItem ? `<div class="headline" ${ed.sec('headline')}><span class="k" ${ed.mark('rate_label')}>${ed.txt('rate_label', L.unit_price_line)}</span>
      <span class="v n">${c.n2(c.rate)} ${esc(c.currency)} / ${esc(c.unit)}</span></div>` : ''}
    <table class="boq">${boqHead(c)}<tbody>${boqRows(c, c.billable)}</tbody></table>
    <div class="avoid">
      <table class="totals"><tbody>${totalsRows(c)}</tbody></table>
      <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(c.words)}</div>
    </div>
    ${c.optional.length ? `<div ${ed.sec('optional')}>
      <h3 style="margin-top:10px" ${ed.mark('h.optional')}>${ed.txt('h.optional', L.optional_items)}</h3>
      <table class="boq"><tbody>${boqRows(c, c.optional, { keyPrefix: 'opt' })}</tbody></table></div>` : ''}
    ${priceNote(c)}
  </section>

  ${c.payments.length ? `<section class="block avoid" ${ed.sec('payment')}>
    <h2 ${ed.mark('h.payment')}>${ed.txt('h.payment', L.payment)}</h2>${paymentTable(c)}</section>` : ''}

  ${c.conditions.length ? `<section class="block avoid" ${ed.sec('conditions')}>
    <h2 ${ed.mark('h.conditions')}>${ed.txt('h.conditions', L.conditions)}</h2>${conditionsList(c)}</section>` : ''}

  ${notesBlock(c)}
  ${closingBlock(c)}
  ${signatures(c)}

  <div class="footer screen-only">
    <div class="n">${esc(c.quoteRef)} · ${formatDate(q.issue_date)}</div>
    <div>${esc(footContact.replace('\n', ' · '))}</div>
    <div class="page-note">${esc(L.page_note)}</div>
  </div>
</div>`;
  return { css, body };
}

// ------------------------------------------------------------------ compact
function compact(c) {
  const { L, q, ed } = c;
  // The first page is a checklist, not the full scope: the long form follows on page two.
  const deliver = SCOPE_ORDER.flatMap((key) => c.scopeItems(key).map((text, i) => ({ key: `${key}.${i}`, text }))).slice(0, 8);
  const required = c.scopeItems('requirements');

  const css = `${BASE_CSS(c)}${NAVY_CSS(c)}
  @page { size: A4; margin: 12mm 12mm 14mm; }
  .page { padding: 12mm 12mm 14mm; }
  .top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 8px; }
  .top .kick { font-size: 8.4pt; letter-spacing: .14em; text-transform: uppercase; color: var(--brand-mid); font-weight: 700; direction: ltr; }
  .top img { max-height: 44px; max-width: 46mm; }
  h1 { margin: 2px 0 2px; font-size: 19pt; line-height: 1.2; font-weight: 800; color: var(--brand); }
  .meta { color: var(--grey); font-size: 9.4pt; margin-bottom: 12px; }
  .cols { display: grid; grid-template-columns: 1fr 62mm; gap: 12px; align-items: start; }
  .main h2 { background: none; border: 0; padding: 0; margin: 12px 0 5px; font-size: 11pt; border-bottom: 2px solid var(--brand); padding-bottom: 3px; }
  .main h2:first-child { margin-top: 0; }
  ul.check { list-style: none; padding: 0; } ul.check li { position: relative; padding-${c.start}: 20px; margin-bottom: 4px; }
  ul.check li::before { content: "✓"; position: absolute; inset-inline-start: 0; top: 0; color: #14683f; font-weight: 800; }
  ul.dots li { margin-bottom: 4px; }
  .pay { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .pay div { padding: 6px 8px; border: 1px solid var(--line); border-radius: 4px; font-size: 9pt; }
  .pay b { display: block; font-size: 13pt; color: var(--brand); }
  .rail { background: var(--brand); color: #fff; border-radius: 6px; padding: 14px 14px 12px; position: sticky; top: 0; }
  .rail .brand { font-size: 8.2pt; letter-spacing: .18em; text-transform: uppercase; opacity: .8; margin-bottom: 8px; direction: ltr; text-align: ${c.start}; }
  .rail .row { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,.16); font-size: 9.2pt; }
  .rail .row .v { font-weight: 700; }
  .rail .total { margin-top: 10px; padding-top: 8px; }
  .rail .total .k { font-size: 8.6pt; opacity: .85; } .rail .total .v { font-size: 20pt; font-weight: 900; line-height: 1.15; color: #f2c879; }
  .rail .total .s { font-size: 8.4pt; opacity: .8; }
  .rail .who { margin-top: 12px; font-size: 8.8pt; opacity: .9; line-height: 1.5; }
  .second h2 { margin-top: 0; }
  `;

  const body = `
<div class="page">
  <div class="top" ${ed.sec('top')}>
    <div>
      <div class="kick n">${esc(L.quotation)} · ${esc(c.quoteRef)}</div>
      <h1 ${ed.mark('title')}>${ed.txt('title', `${L.works} — ${c.projectName}`)}</h1>
      <div class="meta"><span ${ed.mark('to')}>${ed.txt('to', `${L.to} ${c.customerName}`)}</span>${c.attention ? ` · <span ${ed.mark('attention')}>${ed.txt('attention', `${L.attention} ${c.attention}`)}</span>` : ''} · <span class="n">${formatDate(q.issue_date)}</span></div>
    </div>
    <img src="${c.logo}" alt="">
  </div>

  <div class="cols">
    <div class="main">
      <section ${ed.sec('deliver')}>
        <h2 ${ed.mark('h.deliver')}>${ed.txt('h.deliver', L.we_deliver)}</h2>
        <ul class="check">${deliver.map((d) => `<li ${ed.mark(d.key)}>${ed.txt(d.key, d.text)}</li>`).join('')}</ul>
      </section>
      ${required.length ? `<section ${ed.sec('requirements')}>
        <h2 ${ed.mark('h.requirements')}>${ed.txt('h.requirements', L.required_short)}</h2>
        <ul class="dots">${required.map((text, i) => `<li ${ed.mark(`requirements.${i}`)}>${ed.txt(`requirements.${i}`, text)}</li>`).join('')}</ul>
      </section>` : ''}
      ${c.payments.length ? `<section ${ed.sec('payment')}>
        <h2 ${ed.mark('h.payment')}>${ed.txt('h.payment', L.payment)}</h2>
        <div class="pay">${c.payments.map((term, i) => `<div><b class="n">${term.pct}%</b><span ${ed.mark(`pay.${i}`)}>${ed.txt(`pay.${i}`, term.text)}</span></div>`).join('')}</div>
      </section>` : ''}
      ${c.intro ? `<section ${ed.sec('intro')}><h2 ${ed.mark('h.intro')}>${ed.txt('h.intro', L.offer)}</h2><p ${ed.mark('intro')}>${ed.txt('intro', c.intro)}</p></section>` : ''}
    </div>

    <aside class="rail">
      <div class="brand" ${ed.mark('brand')}>${ed.txt('brand', c.branchName)}</div>
      ${c.mainItem ? `<div class="row"><span>${esc(L.area)}</span><span class="v n">${c.n0(c.area)} ${esc(c.unit)}</span></div>
      <div class="row"><span>${esc(L.rate)}</span><span class="v n">${c.n2(c.rate)} ${esc(c.currency)}</span></div>` : ''}
      <div class="row"><span>${esc(L.before_vat)}</span><span class="v n">${c.n2(q.net_amount || q.subtotal)}</span></div>
      <div class="row"><span>${esc(L.vat)} ${Number(q.vat_rate)}%</span><span class="v n">${c.n2(q.vat_amount)}</span></div>
      <div class="total"><div class="k">${esc(L.total_short)}</div><div class="v n">${c.n0(q.total)} ${esc(c.currency)}</div><div class="s">${esc(L.incl_vat)}</div></div>
      <div class="row"><span>${esc(L.valid_until)}</span><span class="v n">${formatDate(q.valid_until)}</span></div>
      <div class="who">${esc(c.ownerName)}${c.ownerTitle ? ` · ${esc(c.ownerTitle)}` : ''}<br><span class="n">${esc(c.ownerPhone)}</span></div>
    </aside>
  </div>
</div>

<div class="page second">
  <section class="block">
    <h2 ${ed.mark('h.commercial')}>${ed.txt('h.commercial', L.commercial)}</h2>
    <table class="boq">${boqHead(c)}<tbody>${boqRows(c, c.billable)}</tbody></table>
    <div class="avoid"><table class="totals"><tbody>${totalsRows(c)}</tbody></table>
    <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(c.words)}</div></div>
    ${c.optional.length ? `<div ${ed.sec('optional')}><h3 style="margin-top:10px" ${ed.mark('h.optional')}>${ed.txt('h.optional', L.optional_items)}</h3>
      <table class="boq"><tbody>${boqRows(c, c.optional, { keyPrefix: 'opt' })}</tbody></table></div>` : ''}
    ${priceNote(c)}
  </section>
  <section class="block" ${ed.sec('scope')}>
    <h2 ${ed.mark('h.scope')}>${ed.txt('h.scope', L.scope)}</h2>
    ${scopeBlocks(c)}
  </section>
  ${listSection(c, 'exclusions', L.exclusions)}
  ${listSection(c, 'schedule', L.schedule)}
  ${listSection(c, 'warranty', L.warranty)}
  ${c.conditions.length ? `<section class="block avoid" ${ed.sec('conditions')}>
    <h2 ${ed.mark('h.conditions')}>${ed.txt('h.conditions', L.conditions)}</h2>${conditionsList(c)}</section>` : ''}
  ${notesBlock(c)}
  ${closingBlock(c)}
  ${signatures(c)}
</div>`;
  return { css, body };
}

// ----------------------------------------------------------------- proposal
function proposal(c) {
  const { L, q, ed } = c;
  const chapters = [L.ch_summary, L.ch_scope, L.ch_specs, L.ch_price, L.ch_terms];
  const nav = (active) => `<div class="chapters">${chapters.map((name, i) => `<span class="${i === active ? 'on' : ''}"><b class="n">${i + 1}</b> · ${esc(name)}</span>`).join('')}</div>`;
  const chapterHead = (i, key, title) => `${nav(i)}<h1 class="ch"><span class="num n">${i + 1}</span><span ${ed.mark(`h.${key}`)}>${ed.txt(`h.${key}`, title)}</span></h1>`;
  const fact = (k, key, v) => `<div class="fact"><div class="k">${esc(k)}</div><div class="v" ${ed.mark(key)}>${ed.txt(key, v)}</div></div>`;

  const css = `${BASE_CSS(c)}${NAVY_CSS(c)}
  @page { size: A4; margin: 12mm 13mm 14mm; }
  .page { padding: 12mm 13mm 14mm; }
  .cover { background: var(--brand); color: #fff; display: flex; flex-direction: column; justify-content: space-between; padding: 18mm 16mm; }
  .cover .brand { display: flex; justify-content: space-between; align-items: center; }
  .cover .brand img { max-height: 46px; max-width: 48mm; background: #fff; padding: 4px 8px; border-radius: 4px; }
  .cover .brand .k { font-size: 8.6pt; letter-spacing: .22em; text-transform: uppercase; opacity: .8; direction: ltr; }
  .cover h1 { font-size: 30pt; line-height: 1.15; margin: 0 0 8px; font-weight: 900; text-wrap: balance; }
  .cover .sub { font-size: 12pt; opacity: .85; }
  .cover .tot { margin-top: 26px; padding: 14px 18px; background: rgba(255,255,255,.08); border-${c.start}: 4px solid #d3a95c; }
  .cover .tot .k { font-size: 9pt; opacity: .85; } .cover .tot .v { font-size: 26pt; font-weight: 900; color: #f2c879; line-height: 1.2; }
  .cover .foot { display: flex; justify-content: space-between; gap: 12px; font-size: 9.4pt; opacity: .9; border-top: 1px solid rgba(255,255,255,.25); padding-top: 10px; }
  .chapters { display: flex; gap: 4px; margin-bottom: 14px; font-size: 8.2pt; }
  .chapters span { flex: 1; padding: 4px 6px; background: #f1f4f8; color: var(--grey); text-align: center; border-bottom: 2px solid var(--line); white-space: nowrap; }
  .chapters span.on { background: var(--brand); color: #fff; border-color: var(--brand); font-weight: 700; }
  h1.ch { display: flex; align-items: center; gap: 12px; margin: 0 0 12px; font-size: 18pt; color: var(--brand); font-weight: 800; }
  h1.ch .num { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 6px; background: var(--brand); color: #fff; font-size: 14pt; }
  .facts { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 12px 0; }
  .fact { padding: 8px 10px; border: 1px solid var(--line); border-radius: 4px; }
  .fact .k { font-size: 8.2pt; color: var(--grey); } .fact .v { font-weight: 800; color: var(--brand); font-size: 10pt; }
  .lead { font-size: 10.8pt; line-height: 1.7; }
  .why { padding: 10px 14px; background: var(--brand-light); border-radius: 4px; margin-top: 10px; }
  .why h3 { margin-bottom: 4px; }
  .pgnum { position: absolute; bottom: 6mm; inset-inline-end: 13mm; font-size: 8pt; color: var(--grey); }
  @media print { .cover { margin: -12mm -13mm -14mm; padding: 18mm 16mm; min-height: 297mm; } .pgnum { position: fixed; } }
  `;

  const body = `
<div class="page cover" ${ed.sec('cover')}>
  <div class="brand"><img src="${c.logo}" alt=""><span class="k" ${ed.mark('kicker')}>${ed.txt('kicker', L.proposal_kicker)}</span></div>
  <div>
    <h1 ${ed.mark('title')}>${ed.txt('title', c.projectName)}</h1>
    <div class="sub" ${ed.mark('subtitle')}>${ed.txt('subtitle', c.mainItem ? `${L.works} · ${c.n0(c.area)} ${c.unit}` : L.works)}</div>
    <div class="tot"><div class="k" ${ed.mark('total_label')}>${ed.txt('total_label', L.total_incl)}</div><div class="v n">${c.n0(q.total)} ${esc(c.currency)}</div></div>
  </div>
  <div class="foot">
    <div><b>${esc(L.prepared_for)}:</b> <span ${ed.mark('to')}>${ed.txt('to', c.customerName)}</span>${c.attention ? `<br><b>${esc(L.attention)}:</b> <span ${ed.mark('attention')}>${ed.txt('attention', c.attention)}</span>` : ''}</div>
    <div class="n" style="text-align:${c.end}">${formatDate(q.issue_date)}<br>${esc(c.quoteRef)}</div>
  </div>
</div>

<div class="page" ${ed.sec('summary')}>
  ${chapterHead(0, 'summary', L.ch_summary)}
  <p class="lead" ${ed.mark('intro')}>${ed.txt('intro', c.intro)}</p>
  <div class="facts">
    ${fact(L.system, 'fact.system', L.system_value)}
    ${fact(L.strands, 'fact.strands', L.strands_value)}
    ${fact(L.design_code, 'fact.code', L.code_value)}
    ${c.mainItem ? `<div class="fact"><div class="k">${esc(L.area)}</div><div class="v n">${c.n0(c.area)} ${esc(c.unit)}</div></div>` : ''}
  </div>
  ${c.profile.length ? `<div ${ed.sec('profile')}><h3 ${ed.mark('h.profile')}>${ed.txt('h.profile', L.profile)}</h3>
    <ul>${c.profile.map((line, i) => `<li ${ed.mark(`profile.${i}`)}>${ed.txt(`profile.${i}`, line)}</li>`).join('')}</ul></div>` : ''}
  <div class="why" ${ed.sec('why')}><h3 ${ed.mark('h.why')}>${ed.txt('h.why', L.why_us)}</h3><p style="margin:0" ${ed.mark('why')}>${ed.txt('why', L.why_us_text)}</p></div>
</div>

<div class="page" ${ed.sec('scope')}>
  ${chapterHead(1, 'scope', L.scope_short)}
  ${scopeBlocks(c)}
  ${listSection(c, 'requirements', L.requirements)}
  ${listSection(c, 'exclusions', L.exclusions)}
</div>

<div class="page" ${ed.sec('specs')}>
  ${chapterHead(2, 'specs', L.ch_specs)}
  ${listSection(c, 'schedule', L.schedule, { twoCol: false })}
  ${listSection(c, 'team', L.team, { twoCol: false })}
  ${listSection(c, 'warranty', L.warranty, { twoCol: false })}
</div>

<div class="page" ${ed.sec('price')}>
  ${chapterHead(3, 'price', L.commercial)}
  ${c.mainItem ? `<div class="headline"><span class="k" ${ed.mark('rate_label')}>${ed.txt('rate_label', L.unit_price_line)}</span><span class="v n">${c.n2(c.rate)} ${esc(c.currency)} / ${esc(c.unit)}</span></div>` : ''}
  <table class="boq">${boqHead(c)}<tbody>${boqRows(c, c.billable)}</tbody></table>
  <div class="avoid"><table class="totals"><tbody>${totalsRows(c)}</tbody></table>
  <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(c.words)}</div></div>
  ${c.optional.length ? `<div ${ed.sec('optional')}><h3 style="margin-top:10px" ${ed.mark('h.optional')}>${ed.txt('h.optional', L.optional_items)}</h3>
    <table class="boq"><tbody>${boqRows(c, c.optional, { keyPrefix: 'opt' })}</tbody></table></div>` : ''}
  ${priceNote(c)}
  ${c.payments.length ? `<section class="block avoid" style="margin-top:14px" ${ed.sec('payment')}>
    <h2 ${ed.mark('h.payment')}>${ed.txt('h.payment', L.payment)}</h2>${paymentTable(c)}</section>` : ''}
</div>

<div class="page" ${ed.sec('terms')}>
  ${chapterHead(4, 'terms', L.conditions)}
  ${c.conditions.length ? conditionsList(c, true) : ''}
  ${notesBlock(c)}
  ${closingBlock(c)}
  ${signatures(c)}
</div>`;
  return { css, body };
}

// ---------------------------------------------------------------------- boq
function boq(c) {
  const { L, q, ed } = c;
  const notes = [c.priceClause, ...c.conditions].filter(Boolean);

  const css = `${BASE_CSS(c)}
  :root { --ink: #111; --line: #9aa4b1; --soft: #f3f5f8; --brand: #0a2647; }
  @page { size: A4; margin: 12mm 12mm 14mm; }
  body { font-size: 9.6pt; }
  .page { padding: 12mm 12mm 14mm; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 12px; border-bottom: 2px solid var(--ink); padding-bottom: 8px; margin-bottom: 8px; }
  .head h1 { margin: 0; font-size: 16pt; font-weight: 800; color: var(--ink); }
  .head .sub { color: #444; font-size: 9.6pt; }
  .head img { max-height: 40px; max-width: 44mm; }
  .refs { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); margin-bottom: 10px; font-size: 9pt; }
  .refs div { padding: 5px 8px; border-${c.end}: 1px solid var(--line); } .refs div:last-child { border: 0; }
  .refs .k { display: block; font-size: 7.8pt; color: #555; } .refs .v { font-weight: 700; }
  table.grid { font-size: 9.2pt; }
  table.grid th { padding: 6px 7px; border: 1px solid var(--ink); background: var(--soft); text-align: ${c.start}; font-weight: 800; font-size: 8.6pt; }
  table.grid td { padding: 5px 7px; border: 1px solid var(--line); vertical-align: top; }
  table.grid .c { text-align: center; } table.grid .n { text-align: ${c.end}; } table.grid .b { font-weight: 700; } table.grid .desc { width: 46%; }
  table.grid tr.group td { background: var(--soft); font-weight: 800; border-color: var(--ink); }
  .sum { display: flex; justify-content: flex-end; margin-top: 10px; }
  .sum table { width: 48%; font-size: 9.6pt; }
  .sum td { padding: 5px 9px; border: 1px solid var(--line); } .sum td:last-child { text-align: ${c.end}; }
  .sum tr.grand td { background: var(--brand); color: #fff; font-weight: 900; font-size: 11pt; border-color: var(--brand); }
  .words { margin-top: 6px; font-size: 9.2pt; } .words .k { font-weight: 800; }
  .notes { margin-top: 12px; font-size: 8.8pt; } .notes h3 { margin: 0 0 4px; font-size: 9.4pt; }
  .notes ol { margin: 0; padding-${c.start}: 18px; } .notes li { margin-bottom: 2px; }
  .signs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 22px; break-inside: avoid; }
  .signs div { padding-top: 6px; border-top: 1px solid var(--ink); font-size: 8.8pt; }
  .signs .k { font-weight: 800; } .signs .who { color: #444; }
  `;

  const body = `
<div class="page">
  <div class="head" ${ed.sec('head')}>
    <div>
      <h1 ${ed.mark('title')}>${ed.txt('title', L.boq_title)}</h1>
      <div class="sub" ${ed.mark('subtitle')}>${ed.txt('subtitle', `${c.projectName} · ${L.works}`)}</div>
      <div class="sub" ${ed.mark('to')}>${ed.txt('to', `${L.to} ${c.customerName}${c.attention ? ` · ${L.attention} ${c.attention}` : ''}`)}</div>
    </div>
    <img src="${c.logo}" alt="">
  </div>
  <div class="refs">
    <div><span class="k">${esc(L.ref)}</span><span class="v n">${esc(q.number)}</span></div>
    <div><span class="k">${esc(L.date)}</span><span class="v n">${formatDate(q.issue_date)}</span></div>
    <div><span class="k">${esc(L.revision)}</span><span class="v n">R${Number(q.revision || 0)}</span></div>
    <div><span class="k">${esc(L.validity)}</span><span class="v n">${c.validDays} ${esc(c.validDays === 1 ? L.day_one : L.days)}</span></div>
  </div>

  <table class="grid">
    ${boqHead(c, true)}
    <tbody>
      <tr class="group"><td class="c n">A</td><td colspan="5" ${ed.mark('group.a')}>${ed.txt('group.a', L.group_main)}</td></tr>
      ${boqRows(c, c.billable, { codes: 'A' })}
      <tr ${ed.sec('reports')}><td class="c code n">A.${c.billable.length + 1}</td><td class="desc" ${ed.mark('reports')}>${ed.txt('reports', L.reports_line)}</td>
        <td class="c">${esc(L.lump)}</td><td class="n">1</td><td class="c">—</td><td class="c b">${esc(L.included)}</td></tr>
      ${c.optional.length ? `<tr class="group"><td class="c n">B</td><td colspan="5" ${ed.mark('group.b')}>${ed.txt('group.b', L.group_optional)}</td></tr>
      ${boqRows(c, c.optional, { codes: 'B', keyPrefix: 'opt' })}` : ''}
    </tbody>
  </table>

  <div class="sum avoid"><table><tbody>${totalsRows(c)}</tbody></table></div>
  <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(c.words)}</div>

  ${c.payments.length ? `<div class="notes" ${ed.sec('payment')}><h3 ${ed.mark('h.payment')}>${ed.txt('h.payment', L.payment)}</h3>
    <ol>${c.payments.map((term, i) => `<li><b class="n">${term.pct}%</b> — <span ${ed.mark(`pay.${i}`)}>${ed.txt(`pay.${i}`, term.text)}</span></li>`).join('')}</ol></div>` : ''}

  ${notes.length ? `<div class="notes" ${ed.sec('notes')}><h3 ${ed.mark('h.notes')}>${ed.txt('h.notes', L.notes)}</h3>
    <ol>${notes.map((text, i) => `<li ${ed.mark(`note.${i}`)}>${ed.txt(`note.${i}`, text)}</li>`).join('')}</ol></div>` : ''}
  ${c.notes ? `<div class="notes" ${ed.sec('free_notes')}><p ${ed.mark('free_notes')}>${ed.prose('free_notes', c.notes)}</p></div>` : ''}

  <div class="signs" ${ed.sec('signatures')}>
    <div><span class="k">${esc(L.prepared_by)}</span><br><span class="who" ${ed.mark('sig.prepared')}>${ed.txt('sig.prepared', [c.ownerName, c.ownerTitle].filter(Boolean).join(' — '))}</span></div>
    <div><span class="k">${esc(L.approved_by)}</span><br><span class="who" ${ed.mark('sig.approved')}>${ed.txt('sig.approved', L.technical_manager)}</span></div>
    <div><span class="k">${esc(L.client_approval)}</span><br><span class="who" ${ed.mark('sig.client')}>${ed.txt('sig.client', L.name_sign_stamp)}</span></div>
  </div>
</div>`;
  return { css, body };
}

// ------------------------------------------------------------------ summary
function summary(c) {
  const { L, q, ed, branch } = c;
  const includes = SCOPE_ORDER.flatMap((key) => c.scopeItems(key).map((text, i) => ({ key: `${key}.${i}`, text }))).slice(0, 6);
  const excludes = c.scopeItems('exclusions').slice(0, 6);
  const footLine = [c.branchName, branch.cr_number ? `${L.cr} ${branch.cr_number}` : '', branch.phone ? ltr(branch.phone) : ''].filter(Boolean).join(' · ');

  const css = `${BASE_CSS(c)}
  :root { --brand: #0a2647; --gold: #d3a95c; --line: #d5dde7; --grey: #5b6775; }
  @page { size: A4; margin: 14mm; }
  .page { padding: 14mm; display: flex; flex-direction: column; }
  .brandline { display: flex; justify-content: space-between; align-items: center; font-size: 8.6pt; color: var(--grey); margin-bottom: 18px; }
  .brandline img { max-height: 40px; max-width: 44mm; }
  .kick { font-size: 9pt; color: var(--grey); letter-spacing: .06em; }
  h1 { margin: 2px 0 4px; font-size: 24pt; line-height: 1.15; font-weight: 900; color: var(--brand); text-wrap: balance; }
  .to { color: var(--grey); font-size: 10.5pt; margin-bottom: 16px; }
  .block { background: var(--brand); color: #fff; border-radius: 8px; padding: 18px 20px; margin-bottom: 16px; }
  .block .line { font-size: 11pt; opacity: .9; }
  .block .tot { font-size: 34pt; font-weight: 900; line-height: 1.1; color: #f2c879; margin: 4px 0; }
  .block .sub { font-size: 9.6pt; opacity: .85; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 16px; }
  .two h3 { margin: 0 0 6px; font-size: 10.5pt; color: var(--brand); border-bottom: 2px solid var(--brand); padding-bottom: 3px; }
  .two ul { list-style: none; padding: 0; } .two li { position: relative; padding-${c.start}: 18px; margin-bottom: 4px; font-size: 9.6pt; }
  .two .yes li::before { content: "✓"; position: absolute; inset-inline-start: 0; color: #14683f; font-weight: 800; }
  .two .no li::before { content: "✕"; position: absolute; inset-inline-start: 0; color: #a32020; font-weight: 800; }
  .facts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 18px; }
  .fact { padding: 10px 12px; border: 1px solid var(--line); border-radius: 6px; text-align: center; }
  .fact .v { font-size: 16pt; font-weight: 900; color: var(--brand); } .fact .k { font-size: 8.8pt; color: var(--grey); }
  .foot { margin-top: auto; padding-top: 10px; border-top: 1px solid var(--line); font-size: 8.4pt; color: var(--grey); line-height: 1.55; }
  `;

  const body = `
<div class="page">
  <div class="brandline"><img src="${c.logo}" alt=""><span class="n">${esc(c.quoteRef)} · ${formatDate(q.issue_date)}</span></div>
  <div class="kick" ${ed.mark('kicker')}>${ed.txt('kicker', L.quotation_for)}</div>
  <h1 ${ed.mark('title')}>${ed.txt('title', c.projectName)}</h1>
  <div class="to" ${ed.mark('to')}>${ed.txt('to', `${c.customerName}${c.attention ? ` · ${L.attention} ${c.attention}` : ''}`)}</div>

  <div class="block" ${ed.sec('total')}>
    <div class="line"><span ${ed.mark('works')}>${ed.txt('works', L.works)}</span>${c.mainItem ? ` <span class="n">${c.n0(c.area)} ${esc(c.unit)} × ${c.n0(c.rate)} ${esc(c.currency)}</span>` : ''}</div>
    <div class="tot n">${c.n0(q.total)} ${esc(c.currency)}</div>
    <div class="sub">${esc(L.total)} · ${esc(L.of_which_vat)} <span class="n">${c.n0(q.vat_amount)}</span></div>
  </div>

  <div class="two">
    <div ${ed.sec('includes')}><h3 ${ed.mark('h.includes')}>${ed.txt('h.includes', L.includes)}</h3>
      <ul class="yes">${includes.map((d) => `<li ${ed.mark(d.key)}>${ed.txt(d.key, d.text)}</li>`).join('')}</ul></div>
    <div ${ed.sec('excludes')}><h3 ${ed.mark('h.excludes')}>${ed.txt('h.excludes', L.excludes)}</h3>
      <ul class="no">${excludes.map((text, i) => `<li ${ed.mark(`exclusions.${i}`)}>${ed.txt(`exclusions.${i}`, text)}</li>`).join('')}</ul></div>
  </div>

  <div class="facts" ${ed.sec('facts')}>
    ${c.payments.length ? `<div class="fact"><div class="v n">${esc(c.paymentSplit)}</div><div class="k" ${ed.mark('fact.pay')}>${ed.txt('fact.pay', L.payment_split)}</div></div>` : ''}
    <div class="fact"><div class="v n">${c.validDays} ${esc(c.validDays === 1 ? L.day_one : L.days)}</div><div class="k" ${ed.mark('fact.valid')}>${ed.txt('fact.valid', L.validity)}</div></div>
    ${c.variance != null ? `<div class="fact"><div class="v n">±${c.variance}%</div><div class="k" ${ed.mark('fact.strand')}>${ed.txt('fact.strand', L.strand_limit)}</div></div>` : ''}
  </div>

  <div class="foot" ${ed.sec('foot')}>
    <div ${ed.mark('foot')}>${ed.txt('foot', L.summary_foot)}</div>
    <div>${esc(footLine)}${c.ownerName ? ` · ${esc(c.ownerName)}${c.ownerPhone ? ` <span class="n">${esc(c.ownerPhone)}</span>` : ''}` : ''}</div>
  </div>
</div>`;
  return { css, body };
}

// ------------------------------------------------------------------ premium
function premium(c) {
  const { L, q, ed } = c;
  const pageNo = (n, total) => `<div class="pgn n">${String(n).padStart(2, '0')} / ${String(total).padStart(2, '0')}</div>`;
  const total = 6;

  const css = `${BASE_CSS(c)}
  :root { --ink: #0b0b0d; --gold: #c9a961; --gold-soft: #e8d6ad; --paper: #fff; --grey: #6b6b70; --rule: #dcd6c8; }
  @page { size: A4; margin: 14mm 15mm 16mm; }
  body { font-size: 10pt; color: #1b1b1f; }
  .page { padding: 14mm 15mm 16mm; }
  .dark { background: var(--ink); color: #f5f1e8; display: flex; flex-direction: column; justify-content: space-between; padding: 20mm 18mm; }
  .dark .brand { display: flex; justify-content: space-between; align-items: center; font-size: 8.4pt; letter-spacing: .28em; text-transform: uppercase; color: var(--gold); direction: ltr; }
  .dark .brand img { max-height: 42px; max-width: 46mm; filter: brightness(0) invert(1); }
  .dark .kick { font-size: 10pt; letter-spacing: .18em; text-transform: uppercase; color: var(--gold); margin-bottom: 12px; }
  .dark h1 { font-size: 34pt; line-height: 1.1; margin: 0 0 14px; font-weight: 900; text-wrap: balance; }
  .dark .sub { font-size: 12pt; color: #d9d3c4; }
  .dark .tot { margin-top: 36px; border-top: 1px solid var(--gold); padding-top: 14px; }
  .dark .tot .k { font-size: 8.6pt; letter-spacing: .22em; color: var(--gold); direction: ltr; }
  .dark .tot .v { font-size: 30pt; font-weight: 900; line-height: 1.2; }
  .dark .row { display: flex; gap: 28px; font-size: 9.4pt; color: #d9d3c4; }
  .dark .row b { color: var(--gold); font-weight: 600; }
  h2 { margin: 0 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--gold); font-size: 13pt; font-weight: 800; color: var(--ink); letter-spacing: .02em; }
  h3 { margin: 12px 0 4px; font-size: 10.4pt; color: var(--ink); }
  .eyebrow { font-size: 8.4pt; letter-spacing: .22em; text-transform: uppercase; color: var(--gold); margin-bottom: 4px; direction: ltr; text-align: ${c.start}; }
  .pgn { position: absolute; bottom: 8mm; inset-inline-end: 15mm; font-size: 8pt; color: var(--grey); letter-spacing: .1em; }
  .dark .pgn { color: var(--gold); }
  .prof li { margin-bottom: 6px; padding-${c.start}: 6px; }
  .vm { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }
  .vm div { padding: 12px 14px; border: 1px solid var(--rule); }
  .vm .k { font-size: 8.4pt; letter-spacing: .18em; text-transform: uppercase; color: var(--gold); margin-bottom: 4px; }
  .big { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 14px 0 6px; }
  .big div { border-top: 2px solid var(--gold); padding-top: 6px; }
  .big .v { font-size: 15pt; font-weight: 800; } .big .k { font-size: 8.4pt; color: var(--grey); }
  ul.two-col { column-count: 2; column-gap: 18px; } ul.two-col li { break-inside: avoid; }
  .scope-block { margin-bottom: 8px; break-inside: avoid; } .scope-block .idx { color: var(--gold); font-weight: 800; margin-inline-end: 6px; }
  table.boq { font-size: 9.4pt; }
  table.boq th { padding: 7px 8px; border-bottom: 2px solid var(--ink); text-align: ${c.start}; font-size: 8.4pt; letter-spacing: .08em; text-transform: uppercase; }
  table.boq td { padding: 7px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }
  table.boq .c { text-align: center; } table.boq .n { text-align: ${c.end}; } table.boq .b { font-weight: 700; } table.boq .desc { width: 46%; }
  .totals { width: 56%; margin-${c.start}: auto; margin-top: 10px; }
  .totals td { padding: 5px 8px; border-bottom: 1px solid var(--rule); } .totals td:last-child { text-align: ${c.end}; }
  .totals tr.grand td { border-top: 2px solid var(--gold); border-bottom: 0; font-size: 12pt; font-weight: 900; }
  .words { margin-top: 8px; font-size: 9.4pt; color: var(--grey); } .words .k { color: var(--ink); font-weight: 700; }
  .note { margin-top: 10px; padding: 8px 12px; border-${c.start}: 3px solid var(--gold); background: #faf7ef; font-size: 9pt; } .note .k { font-weight: 800; }
  .block { margin-bottom: 14px; }
  ol { margin: 0; padding-${c.start}: 18px; } ol li { margin-bottom: 3px; }
  .signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 26px; break-inside: avoid; }
  .sig .h { font-size: 9.6pt; font-weight: 800; margin-bottom: 26px; }
  .sig .l { display: flex; gap: 6px; margin-bottom: 12px; font-size: 9pt; } .sig .l .k { min-width: 52px; color: var(--grey); } .sig .l .line { flex: 1; border-bottom: 1px solid var(--rule); }
  .closing { margin-top: 12px; } .regards { margin-top: 8px; font-weight: 700; }
  @media print { .dark { margin: -14mm -15mm -16mm; padding: 20mm 18mm; min-height: 297mm; } .pgn { position: fixed; } }
  `;

  const body = `
<div class="page dark" ${ed.sec('cover')}>
  <div class="brand"><img src="${c.logo}" alt=""><span ${ed.mark('regions')}>${ed.txt('regions', L.cover_regions)}</span></div>
  <div>
    <div class="kick" ${ed.mark('kicker')}>${ed.txt('kicker', L.quotation)}</div>
    <h1 ${ed.mark('title')}>${ed.txt('title', c.projectName)}</h1>
    <div class="sub"><span ${ed.mark('works')}>${ed.txt('works', L.works)}</span> · <span ${ed.mark('to')}>${ed.txt('to', `${L.prepared_for} ${c.customerName}`)}</span></div>
    <div class="tot"><div class="k">${esc(L.total_cover)}</div><div class="v n">${c.n0(q.total)} ${esc(c.currency)}</div></div>
  </div>
  <div class="row"><span><b>No.</b> <span class="n">${esc(c.quoteRef)}</span></span><span class="n">${formatDate(q.issue_date)}</span><span><b>${esc(L.valid)}</b> <span class="n">${formatDate(q.valid_until)}</span></span></div>
  ${pageNo(1, total)}
</div>

<div class="page" ${ed.sec('profile')}>
  <div class="eyebrow">${esc(L.cover_regions)}</div>
  <h2 ${ed.mark('h.profile')}>${ed.txt('h.profile', L.about)}</h2>
  <ul class="prof">${c.profile.map((line, i) => `<li ${ed.mark(`profile.${i}`)}>${ed.txt(`profile.${i}`, line)}</li>`).join('')}</ul>
  <div class="vm">
    ${c.vision ? `<div><div class="k">${esc(L.vision)}</div><div ${ed.mark('vision')}>${ed.txt('vision', c.vision)}</div></div>` : ''}
    ${c.mission ? `<div><div class="k">${esc(L.mission)}</div><div ${ed.mark('mission')}>${ed.txt('mission', c.mission)}</div></div>` : ''}
  </div>
  <div class="big">
    <div><div class="v" ${ed.mark('fact.system')}>${ed.txt('fact.system', L.system_value)}</div><div class="k">${esc(L.system)}</div></div>
    <div><div class="v" ${ed.mark('fact.strands')}>${ed.txt('fact.strands', L.strands_value)}</div><div class="k">${esc(L.strands)}</div></div>
    <div><div class="v" ${ed.mark('fact.code')}>${ed.txt('fact.code', L.code_value)}</div><div class="k">${esc(L.design_code)}</div></div>
  </div>
  <h3 ${ed.mark('h.why')}>${ed.txt('h.why', L.why_us)}</h3>
  <p ${ed.mark('why')}>${ed.txt('why', L.why_us_text)}</p>
  ${pageNo(2, total)}
</div>

<div class="page" ${ed.sec('intro')}>
  <div class="eyebrow">${esc(L.offer)}</div>
  <h2 ${ed.mark('h.intro')}>${ed.txt('h.intro', `${L.doc_subtitle} — ${c.projectName}`)}</h2>
  <p ${ed.mark('greeting')}>${ed.txt('greeting', L.greeting)}</p>
  <p ${ed.mark('intro')}>${ed.txt('intro', c.intro)}</p>
  <h3 ${ed.mark('h.scope')}>${ed.txt('h.scope', L.scope_short)}</h3>
  ${SCOPE_ORDER.map((key, index) => {
    const items = c.scopeItems(key);
    if (!items.length) return '';
    return `<div class="scope-block" ${ed.sec(`scope.${key}`)}><h3><span class="idx n">${index + 1}.</span><span ${ed.mark(`h.scope.${key}`)}>${ed.txt(`h.scope.${key}`, c.scopeTitle(key))}</span></h3>
      <ul>${items.map((item, i) => `<li ${ed.mark(`${key}.${i}`)}>${ed.txt(`${key}.${i}`, item)}</li>`).join('')}</ul></div>`;
  }).join('')}
  ${pageNo(3, total)}
</div>

<div class="page" ${ed.sec('requirements_page')}>
  <div class="eyebrow">${esc(L.offer)}</div>
  ${listSection(c, 'requirements', L.requirements, { twoCol: false })}
  ${listSection(c, 'exclusions', L.exclusions, { twoCol: false })}
  ${listSection(c, 'schedule', L.schedule, { twoCol: false })}
  ${listSection(c, 'team', L.team, { twoCol: false })}
  ${listSection(c, 'warranty', L.warranty, { twoCol: false })}
  ${pageNo(4, total)}
</div>

<div class="page" ${ed.sec('price')}>
  <div class="eyebrow">${esc(L.offer)}</div>
  <h2 ${ed.mark('h.commercial')}>${ed.txt('h.commercial', L.commercial)}</h2>
  <table class="boq">${boqHead(c)}<tbody>${boqRows(c, c.billable)}</tbody></table>
  <div class="avoid"><table class="totals"><tbody>${totalsRows(c)}</tbody></table>
  <div class="words"><span class="k">${esc(L.in_words)}:</span> ${esc(c.words)}</div></div>
  ${c.optional.length ? `<div ${ed.sec('optional')}><h3 ${ed.mark('h.optional')}>${ed.txt('h.optional', L.optional_items)}</h3>
    <table class="boq"><tbody>${boqRows(c, c.optional, { keyPrefix: 'opt' })}</tbody></table></div>` : ''}
  ${priceNote(c)}
  ${c.payments.length ? `<div class="block" style="margin-top:14px" ${ed.sec('payment')}><h3 ${ed.mark('h.payment')}>${ed.txt('h.payment', L.payment)}</h3>
    <table class="boq"><tbody>${c.payments.map((term, i) => `<tr><td class="c b n" style="width:12%">${term.pct}%</td><td ${ed.mark(`pay.${i}`)}>${ed.txt(`pay.${i}`, term.text)}</td>
      <td class="n" style="width:26%">${c.cash((term.pct / 100) * Number(q.total || 0))}</td></tr>`).join('')}</tbody></table></div>` : ''}
  ${pageNo(5, total)}
</div>

<div class="page" ${ed.sec('terms')}>
  <div class="eyebrow">${esc(L.offer)}</div>
  <h2 ${ed.mark('h.conditions')}>${ed.txt('h.conditions', L.conditions)}</h2>
  ${c.conditions.length ? conditionsList(c, true) : ''}
  ${notesBlock(c)}
  ${closingBlock(c)}
  ${signatures(c)}
  ${pageNo(6, total)}
</div>`;
  return { css, body };
}

const RENDERERS = { letter, compact, proposal, boq, summary, premium };

/**
 * Opens the quotation in the chosen design, editable when the browser can
 * reach the server. `document_` is the payload of GET /api/quotations/:id/document.
 */
export function printQuoteDesign(document_, lang = 'ar', design = 'letter') {
  const render = RENDERERS[design] || RENDERERS.letter;
  const id = RENDERERS[design] ? design : 'letter';
  const q = document_.quotation;
  const edits = (q && q.print) || {};
  const ed = createEditor(edits, id);
  const c = context(document_, lang, ed);
  const { css, body } = render(c);
  const origin = String(document_.origin || window.location.origin || '').replace(/\/+$/, '');
  openDocument({
    lang,
    title: `${c.quoteRef} — ${c.projectName}`,
    css,
    body,
    editor: ed,
    existingText: edits.text || {},
    api: q && q.id ? `${origin}/api/quotations/${Number(q.id)}/print` : '',
    presentable: false,
  });
}
