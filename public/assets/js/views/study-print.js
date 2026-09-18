/**
 * The cost comparison study as a document for the building owner.
 *
 * This is a sales document that has to survive being handed to the owner's own
 * consultant, so it shows its working: the rates it used, the slab-only
 * comparison as well as the whole-building one, and the assumptions named as
 * assumptions. A study that only showed the flattering number would be taken
 * apart in the first technical meeting.
 *
 * Charts are hand-built SVG strings because this document opens in its own
 * window with no module loader and prints without a network.
 */
import { esc } from '../ui.js';

const money = (value, digits = 0) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const LABELS = {
  ar: {
    doc_title: 'دراسة مقارنة التكلفة',
    doc_sub: 'الأسقف اللاحقة للشد مقابل النظام التقليدي',
    prepared_for: 'مقدمة إلى', project: 'المشروع', location: 'الموقع',
    date: 'التاريخ', ref: 'مرجع العرض',
    intro_h: 'الغرض من هذه الدراسة',
    intro: 'أُعدت هذه الدراسة لمقارنة تكلفة تنفيذ أسقف المشروع بنظام الشد اللاحق (Post-Tension) '
      + 'مقابل تنفيذها بالنظام التقليدي، على أساس نفس المساحات وأسعار السوق الحالية. '
      + 'كل الأرقام الواردة قابلة للمراجعة، وأساس كل بند موضح أمامه.',
    profile_h: 'عن شركة سبان تك',
    basis_h: 'أساس المقارنة',
    basis_system: 'النظام التقليدي محل المقارنة',
    basis_area: 'مساحة السقف للدور', basis_floors: 'عدد الأدوار',
    basis_total_area: 'إجمالي المساحة',
    rates_h: 'الأسعار المستخدمة',
    rate_concrete: 'الخرسانة (للمتر المكعب)',
    rate_rebar: 'حديد التسليح (للطن)',
    rate_formwork: 'الشدات (للمتر المربع)',
    rate_pt: 'أعمال الشد اللاحق (للمتر المربع)',
    compare_h: 'مقارنة تكلفة السقف — للمتر المربع',
    item: 'البند', conventional: 'النظام التقليدي', pt: 'الشد اللاحق', diff: 'الفرق',
    concrete: 'الخرسانة', rebar: 'حديد التسليح', formwork: 'الشدات',
    pt_package: 'أعمال الشد اللاحق', total_sqm: 'الإجمالي للمتر المربع',
    slab_thickness: 'سُمك السقف', rebar_density: 'كثافة الحديد',
    project_total_h: 'إجمالي المشروع',
    slab_only: 'فرق تكلفة الأسقف',
    foundation: 'وفر الأساسات والأعمدة',
    programme: 'وفر مدة التنفيذ',
    net_saving: 'صافي الوفر',
    of_conventional: 'من تكلفة النظام التقليدي',
    slab_negative_h: 'ملاحظة على مقارنة الأسقف',
    slab_negative: 'تكلفة السقف اللاحق الشد لهذا المشروع أعلى من النظام التقليدي محل المقارنة. '
      + 'الوفر الحقيقي يأتي مما يترتب على السقف الأخف والأقل سُمكاً: الأساسات والأعمدة، '
      + 'ومدة التنفيذ، وارتفاع المبنى — وهي موضحة في الجدول أعلاه.',
    benefits_h: 'ما وراء التكلفة المباشرة',
    b_concrete: 'خرسانة موفَّرة', b_rebar: 'حديد موفَّر', b_weight: 'تخفيف وزن المبنى',
    b_thickness: 'تقليل سُمك السقف', b_height: 'ارتفاع موفَّر على كامل المبنى',
    b_days: 'اختصار في مدة التنفيذ',
    unit_m3: 'م³', unit_t: 'طن', unit_mm: 'مم', unit_day: 'يوم',
    chart_h: 'مقارنة التكلفة للمتر المربع',
    chart_saving_h: 'مصادر الوفر',
    drawings_h: 'المخططات',
    drawings_original: 'المخطط الأصلي قبل التحويل',
    drawings_pt: 'مخطط الشد اللاحق المقترح',
    notes_h: 'ملاحظات',
    assumptions_h: 'حدود الدراسة',
    assumptions: 'الأرقام أعلاه مبنية على الأسعار والكميات الموضحة، وعلى تصميم مبدئي للأسقف اللاحقة للشد. '
      + 'وفر الأساسات والأعمدة ومدة التنفيذ تقديرات مبنية على خبرة الشركة في مشاريع مماثلة، '
      + 'وتحتاج مراجعة المصمم الإنشائي للمشروع. لا تشمل الدراسة أعمال الحفر والخوازيق أو أي بنود خارج الهيكل الإنشائي.',
    regards: 'وتفضلوا بقبول فائق الاحترام،',
    page: 'صفحة', of: 'من',
  },
  en: {
    doc_title: 'COST COMPARISON STUDY',
    doc_sub: 'Post-Tensioned Slabs vs. Conventional Construction',
    prepared_for: 'Prepared for', project: 'Project', location: 'Location',
    date: 'Date', ref: 'Quotation ref.',
    intro_h: 'Purpose of this study',
    intro: 'This study compares the cost of building the project’s slabs in post-tensioned concrete '
      + 'against the conventional system, on the same areas and at current market rates. '
      + 'Every figure is open to review and the basis of each line is stated.',
    profile_h: 'About Span Tech',
    basis_h: 'Basis of comparison',
    basis_system: 'Conventional system compared against',
    basis_area: 'Slab area per floor', basis_floors: 'Number of floors',
    basis_total_area: 'Total area',
    rates_h: 'Rates used',
    rate_concrete: 'Concrete (per m³)',
    rate_rebar: 'Reinforcement (per tonne)',
    rate_formwork: 'Formwork (per m²)',
    rate_pt: 'Post-tensioning (per m²)',
    compare_h: 'Slab cost comparison — per square metre',
    item: 'Item', conventional: 'Conventional', pt: 'Post-tensioned', diff: 'Difference',
    concrete: 'Concrete', rebar: 'Reinforcement', formwork: 'Formwork',
    pt_package: 'Post-tensioning package', total_sqm: 'Total per m²',
    slab_thickness: 'Slab thickness', rebar_density: 'Reinforcement density',
    project_total_h: 'Project totals',
    slab_only: 'Slab cost difference',
    foundation: 'Foundations and columns saved',
    programme: 'Programme saving',
    net_saving: 'Net saving',
    of_conventional: 'of the conventional cost',
    slab_negative_h: 'A note on the slab comparison',
    slab_negative: 'On slab cost alone, the post-tensioned option is dearer than the conventional '
      + 'system compared here. The saving comes from what follows a lighter, thinner slab — '
      + 'foundations and columns, programme, and building height — set out in the table above.',
    benefits_h: 'Beyond the direct cost',
    b_concrete: 'Concrete saved', b_rebar: 'Reinforcement saved', b_weight: 'Building weight removed',
    b_thickness: 'Slab depth saved', b_height: 'Height saved over the building',
    b_days: 'Programme shortened by',
    unit_m3: 'm³', unit_t: 't', unit_mm: 'mm', unit_day: 'days',
    chart_h: 'Cost per square metre',
    chart_saving_h: 'Where the saving comes from',
    drawings_h: 'Drawings',
    drawings_original: 'Original design before conversion',
    drawings_pt: 'Proposed post-tensioned design',
    notes_h: 'Notes',
    assumptions_h: 'Scope of this study',
    assumptions: 'These figures rest on the rates and quantities shown and on a preliminary '
      + 'post-tensioned design. The foundation and programme savings are estimates from our '
      + 'experience on comparable projects and should be confirmed by the project’s structural '
      + 'designer. Excavation, piling and anything outside the structural frame are not included.',
    regards: 'With our best regards,',
    page: 'Page', of: 'of',
  },
};

// ---------------------------------------------------------------- charts
/**
 * Two stacked columns, conventional against post-tensioned, so the owner can
 * see not just which is cheaper but which part of the cost moved.
 */
function costChart(study, L, currency, isAr) {
  const parts = [
    { key: 'concrete', label: L.concrete, colour: '#1a56a7' },
    { key: 'rebar', label: L.rebar, colour: '#3d8bdd' },
    { key: 'formwork', label: L.formwork, colour: '#7fb2e8' },
    { key: 'post_tension', label: L.pt_package, colour: '#c2410c' },
  ];
  const columns = [
    { name: isAr ? study.system.label_ar : study.system.label_en, side: study.conventional },
    { name: L.pt, side: study.post_tension },
  ];

  const max = Math.max(columns[0].side.per_sqm, columns[1].side.per_sqm, 1);
  const W = 520;
  const H = 260;
  const pad = { top: 16, bottom: 44, left: 52, right: 12 };
  const plotH = H - pad.top - pad.bottom;
  const barW = 92;
  const gap = 96;
  const startX = pad.left + 48;

  let bars = '';
  columns.forEach((column, index) => {
    const x = startX + index * (barW + gap);
    let y = pad.top + plotH;
    for (const part of parts) {
      const value = Number(column.side[part.key]) || 0;
      if (value <= 0) continue;
      const h = (value / max) * plotH;
      y -= h;
      bars += `<rect x="${x}" y="${y.toFixed(1)}" width="${barW}" height="${h.toFixed(1)}" fill="${part.colour}"/>`;
    }
    bars += `<text x="${x + barW / 2}" y="${pad.top + plotH + 18}" text-anchor="middle" font-size="11" fill="#17202b">${esc(column.name)}</text>`;
    bars += `<text x="${x + barW / 2}" y="${(pad.top + plotH - (column.side.per_sqm / max) * plotH - 6).toFixed(1)}" text-anchor="middle" font-size="12" font-weight="700" fill="#0a2647">${money(column.side.per_sqm)}</text>`;
  });

  // Four gridlines are enough to read the scale without crowding the bars.
  let grid = '';
  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i;
    const y = pad.top + plotH - (i / 4) * plotH;
    grid += `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${W - pad.right}" y2="${y.toFixed(1)}" stroke="#e5eaef" stroke-width="1"/>`;
    grid += `<text x="${pad.left - 6}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="9.5" fill="#5b6775">${money(value)}</text>`;
  }

  const legend = parts.map((part, index) => `
    <g transform="translate(${pad.left + index * 116}, ${H - 14})">
      <rect width="10" height="10" y="-9" fill="${part.colour}"/>
      <text x="14" y="0" font-size="9.5" fill="#5b6775">${esc(part.label)}</text>
    </g>`).join('');

  return `<svg viewBox="0 0 ${W} ${H + 6}" width="100%" role="img" aria-label="${esc(L.chart_h)}">
    ${grid}${bars}${legend}
    <text x="${pad.left - 6}" y="${pad.top - 4}" text-anchor="end" font-size="9" fill="#8a94a1">${esc(currency)}</text>
  </svg>`;
}

/** Where the saving comes from, including a bar below the line when it does. */
function savingChart(study, L, currency) {
  const rows = [
    { label: L.slab_only, value: study.saving.slab_total },
    { label: L.foundation, value: study.saving.foundation_total },
    { label: L.programme, value: study.saving.programme_total },
    { label: L.net_saving, value: study.saving.total, strong: true },
  ].filter((row) => row.strong || row.value !== 0);

  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  const W = 520;
  const rowH = 34;
  const H = rows.length * rowH + 14;
  const labelW = 180;
  const zeroX = labelW + ((W - labelW - 20) / 2);
  const halfW = (W - labelW - 20) / 2;

  const bars = rows.map((row, index) => {
    const y = index * rowH + 8;
    const w = (Math.abs(row.value) / max) * halfW;
    const x = row.value >= 0 ? zeroX : zeroX - w;
    const colour = row.strong
      ? (row.value >= 0 ? '#0f7350' : '#a32020')
      : (row.value >= 0 ? '#2670c9' : '#c2410c');
    return `
      <text x="${labelW - 8}" y="${y + 16}" text-anchor="end" font-size="10.5" fill="#17202b"${row.strong ? ' font-weight="700"' : ''}>${esc(row.label)}</text>
      <rect x="${x.toFixed(1)}" y="${y + 4}" width="${Math.max(w, 1).toFixed(1)}" height="16" fill="${colour}" rx="1"/>
      <text x="${(row.value >= 0 ? x + w + 6 : x - 6).toFixed(1)}" y="${y + 16}" text-anchor="${row.value >= 0 ? 'start' : 'end'}" font-size="10" fill="#5b6775">${money(row.value)}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(L.chart_saving_h)}">
    <line x1="${zeroX}" y1="4" x2="${zeroX}" y2="${H - 6}" stroke="#c8d3e0" stroke-width="1"/>
    ${bars}
    <text x="${W - 4}" y="${H - 2}" text-anchor="end" font-size="9" fill="#8a94a1">${esc(currency)}</text>
  </svg>`;
}

// -------------------------------------------------------------- document
export function printStudy(data, lang = 'ar') {
  const html = buildStudyDocument(data, lang);
  const win = window.open('', '_blank');
  if (!win) {
    alert(lang === 'ar'
      ? 'الرجاء السماح بالنوافذ المنبثقة لطباعة الدراسة.'
      : 'Please allow pop-ups to print the study.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
  win.addEventListener('load', () => setTimeout(() => win.print(), 400));
}

function buildStudyDocument(data, lang) {
  const isAr = lang === 'ar';
  const L = LABELS[lang];
  const study = data.study;
  const q = data.quotation || {};
  const company = data.company || {};
  const branch = data.branch || company;
  const currency = q.currency || '';
  const dir = isAr ? 'rtl' : 'ltr';

  const s = study.input;
  const systemName = isAr ? study.system.label_ar : study.system.label_en;
  const projectName = (isAr ? q.project_name_ar : q.project_name) || q.project_name || '';
  const customerName = (isAr ? q.customer_name_ar : q.customer_name) || q.customer_name || '';
  const location = (isAr ? q.location_ar : q.location) || q.location || '';
  const notes = (isAr ? s.notes_ar : s.notes_en) || '';
  const profile = (isAr ? company.profile_ar : company.profile_en) || [];

  const cash = (value) => `${money(value)} ${currency}`;
  const cash2 = (value) => `${money(value, 2)} ${currency}`;

  const compareRow = (label, conv, pt, formatter = cash2) => `
    <tr>
      <td>${esc(label)}</td>
      <td class="n">${formatter(conv)}</td>
      <td class="n">${formatter(pt)}</td>
      <td class="n ${conv - pt >= 0 ? 'good' : 'bad'}">${formatter(conv - pt)}</td>
    </tr>`;

  const drawings = (kind) => (data.drawings || []).filter((d) => d.kind === kind);
  const drawingBlock = (kind, heading) => {
    const list = drawings(kind);
    if (!list.length) return '';
    return `
      <div class="draw-col">
        <h3>${esc(heading)}</h3>
        ${list.map((d) => `
          <figure>
            <img src="${esc(d.url)}" alt="${esc((isAr ? d.caption_ar : d.caption_en) || heading)}">
            ${(isAr ? d.caption_ar : d.caption_en)
              ? `<figcaption>${esc(isAr ? d.caption_ar : d.caption_en)}</figcaption>` : ''}
          </figure>`).join('')}
      </div>`;
  };
  const hasDrawings = drawings('original').length || drawings('post_tension').length;

  const footContact = [
    (isAr ? branch.address_ar : branch.address_en) || '',
    [branch.phone, branch.email, branch.website].filter(Boolean).join('  ·  '),
  ].filter(Boolean).join('\\A ');

  return `<!doctype html>
<html lang="${lang}" dir="${dir}">
<head>
<meta charset="utf-8">
<title>${esc(L.doc_title)} — ${esc(projectName)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap">
<style>
  @page {
    size: A4;
    margin: 20mm 13mm 19mm;
    font-family: ${isAr ? "'Cairo',Tahoma,sans-serif" : "'Inter',Arial,sans-serif"};
    font-size: 7.4pt; color: #5b6775;

    @bottom-${isAr ? 'right' : 'left'} {
      content: "${esc(L.doc_title)}";
      vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0;
    }
    @bottom-center {
      content: "${footContact}";
      white-space: pre-line; text-align: center;
      vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0;
    }
    @bottom-${isAr ? 'left' : 'right'} {
      content: "${esc(L.page)} " counter(page) " ${esc(L.of)} " counter(pages);
      vertical-align: top; padding-top: 2.6mm; border-top: .6pt solid #c8d3e0;
      font-weight: 700; color: #0a2647;
    }
  }

  :root { --brand:#0a2647; --mid:#1a56a7; --wash:#e8f0fa; --line:#c8d3e0; --grey:#5b6775; --ink:#17202b; }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #f1f3f6; color: var(--ink);
    font-family: ${isAr ? "'Cairo','Tajawal',Tahoma,sans-serif" : "'Inter','Segoe UI',Arial,sans-serif"};
    font-size: 10.2pt; line-height: 1.62;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .sheet { width: 210mm; min-height: 297mm; margin: 0 auto; padding: 14mm 13mm 19mm; background: #fff; }
  @media print { body { background: #fff; } .sheet { width: auto; min-height: 0; margin: 0; padding: 0; } .no-print { display: none !important; } }

  .toolbar { position: sticky; top: 0; z-index: 10; display: flex; gap: .5rem; justify-content: center; padding: 10px; background: var(--brand); }
  .toolbar button { padding: 7px 18px; border: 0; border-radius: 5px; background: #fff; color: var(--brand); font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
  .toolbar button.ghost { background: transparent; color: #fff; box-shadow: inset 0 0 0 1px rgba(255,255,255,.5); }

  .letterhead { display: flex; align-items: center; gap: 14px; padding-bottom: 9px; margin-bottom: 12px; border-bottom: 2.5px solid var(--brand); }
  .letterhead img { max-height: 62px; max-width: 58mm; }
  .letterhead .who { flex: 1; }
  .letterhead .n { font-size: 14pt; font-weight: 800; color: var(--brand); line-height: 1.25; }
  .letterhead .t { font-size: 8.6pt; color: var(--grey); }

  .doc-title { padding: 8px 12px; margin-bottom: 12px; background: var(--brand); color: #fff; border-radius: 3px; text-align: center; }
  .doc-title h1 { margin: 0; font-size: 13pt; font-weight: 800; letter-spacing: .02em; }
  .doc-title .sub { font-size: 8.6pt; opacity: .88; }

  .ref-grid { display: grid; grid-template-columns: 1fr 1fr; margin-bottom: 13px; border: 1px solid var(--line); }
  .ref-grid > div { padding: 7px 10px; }
  .ref-grid .bg { background: var(--wash); }
  .ref-line { display: flex; gap: 6px; font-size: 9.4pt; }
  .ref-line + .ref-line { margin-top: 2px; }
  .ref-line .k { min-width: 84px; font-weight: 700; color: var(--brand); }
  .ref-line .v.mono { direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }

  h2 { margin: 16px 0 6px; padding: 4px 9px; background: var(--wash); border-${isAr ? 'right' : 'left'}: 3px solid var(--mid); font-size: 10.6pt; font-weight: 800; color: var(--brand); break-after: avoid; }
  h3 { margin: 10px 0 4px; font-size: 9.8pt; font-weight: 700; color: var(--mid); }
  p { margin: 0 0 7px; text-align: justify; }
  ul { margin: 0 0 7px; padding-${isAr ? 'right' : 'left'}: 16px; }
  li { margin-bottom: 2px; }

  table { width: 100%; border-collapse: collapse; font-size: 9.2pt; margin-bottom: 8px; }
  th, td { padding: 5px 8px; border: 1px solid var(--line); text-align: ${isAr ? 'right' : 'left'}; }
  thead th { background: var(--brand); color: #fff; font-weight: 700; font-size: 8.8pt; }
  td.n, th.n { text-align: ${isAr ? 'left' : 'right'}; direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }
  tr.total td { background: var(--wash); font-weight: 800; color: var(--brand); }
  td.good { color: #0f7350; font-weight: 700; }
  td.bad  { color: #a32020; font-weight: 700; }

  .headline { display: flex; gap: 10px; margin: 10px 0 4px; }
  .headline .box { flex: 1; padding: 10px 12px; border: 1px solid var(--line); border-radius: 3px; text-align: center; }
  .headline .box.main { background: var(--wash); border-color: var(--mid); }
  .headline .box .lbl { font-size: 8.4pt; color: var(--grey); }
  .headline .box .val { font-size: 14pt; font-weight: 800; color: var(--brand); direction: ltr; unicode-bidi: plaintext; }
  .headline .box .val.neg { color: #a32020; }

  .chart { break-inside: avoid; margin-bottom: 10px; }
  .note { padding: 9px 11px; background: #fdf7ee; border: 1px solid #e8c9a0; border-radius: 3px; font-size: 9.2pt; break-inside: avoid; }
  .block { break-inside: avoid; }

  .draws { display: flex; gap: 10px; align-items: flex-start; }
  .draw-col { flex: 1; min-width: 0; }
  figure { margin: 0 0 8px; break-inside: avoid; }
  figure img { width: 100%; border: 1px solid var(--line); border-radius: 2px; }
  figcaption { font-size: 8.4pt; color: var(--grey); margin-top: 3px; text-align: center; }

  .sig { margin-top: 14px; break-inside: avoid; }
  .sig .l { display: flex; gap: 6px; margin-bottom: 11px; font-size: 9pt; }
  .sig .l .k { min-width: 52px; color: var(--grey); }
  .sig .l .line { flex: 1; border-bottom: 1px dotted var(--line); }
</style>
</head>
<body>

<div class="toolbar no-print">
  <button onclick="window.print()">${isAr ? 'طباعة / حفظ PDF' : 'Print / Save as PDF'}</button>
  <button class="ghost" onclick="window.close()">${isAr ? 'إغلاق' : 'Close'}</button>
</div>

<div class="sheet">

  <div class="letterhead">
    <img src="${esc(branch.logo || '/assets/img/logo@2x.png')}" alt="">
    <div class="who">
      <div class="n">${esc(isAr ? (branch.name_ar || company.name_ar) : (branch.name_en || company.name_en))}</div>
      <div class="t">${esc(isAr ? company.tagline_ar : company.tagline_en)}</div>
    </div>
  </div>

  <div class="doc-title">
    <h1>${esc(L.doc_title)}</h1>
    <div class="sub">${esc(L.doc_sub)}</div>
  </div>

  <div class="ref-grid">
    <div>
      <div class="ref-line"><span class="k">${esc(L.prepared_for)}</span><span class="v">${esc(customerName)}</span></div>
      <div class="ref-line"><span class="k">${esc(L.project)}</span><span class="v">${esc(projectName)}</span></div>
      ${location ? `<div class="ref-line"><span class="k">${esc(L.location)}</span><span class="v">${esc(location)}</span></div>` : ''}
    </div>
    <div class="bg">
      <div class="ref-line"><span class="k">${esc(L.ref)}</span><span class="v mono">${esc(q.number || '—')}</span></div>
      <div class="ref-line"><span class="k">${esc(L.date)}</span><span class="v mono">${esc(data.generated_at || '')}</span></div>
      <div class="ref-line"><span class="k">${esc(L.basis_total_area)}</span><span class="v mono">${money(study.total_area_sqm)} m²</span></div>
    </div>
  </div>

  <h2>${esc(L.intro_h)}</h2>
  <p>${esc(L.intro)}</p>

  ${profile.length ? `
  <div class="block">
    <h2>${esc(L.profile_h)}</h2>
    <ul>${profile.map((line) => `<li>${esc(line)}</li>`).join('')}</ul>
  </div>` : ''}

  <h2>${esc(L.basis_h)}</h2>
  <table>
    <tbody>
      <tr><td>${esc(L.basis_system)}</td><td class="n">${esc(systemName)}</td></tr>
      <tr><td>${esc(L.basis_area)}</td><td class="n">${money(study.area_sqm)} m²</td></tr>
      <tr><td>${esc(L.basis_floors)}</td><td class="n">${money(study.floors)}</td></tr>
      <tr class="total"><td>${esc(L.basis_total_area)}</td><td class="n">${money(study.total_area_sqm)} m²</td></tr>
    </tbody>
  </table>

  <h3>${esc(L.rates_h)}</h3>
  <table>
    <tbody>
      <tr><td>${esc(L.rate_concrete)}</td><td class="n">${cash(s.concrete_rate_m3)}</td></tr>
      <tr><td>${esc(L.rate_rebar)}</td><td class="n">${cash(s.rebar_rate_ton)}</td></tr>
      <tr><td>${esc(L.rate_formwork)}</td><td class="n">${cash(s.formwork_rate_sqm)}</td></tr>
      <tr><td>${esc(L.rate_pt)}</td><td class="n">${cash(s.pt_rate_sqm)}</td></tr>
    </tbody>
  </table>

  <h2>${esc(L.compare_h)}</h2>
  <table>
    <thead>
      <tr>
        <th>${esc(L.item)}</th>
        <th class="n">${esc(systemName)}</th>
        <th class="n">${esc(L.pt)}</th>
        <th class="n">${esc(L.diff)}</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>${esc(L.slab_thickness)}</td>
        <td class="n">${money(s.conv_thickness_mm)} mm</td>
        <td class="n">${money(s.pt_thickness_mm)} mm</td>
        <td class="n good">${money(study.benefits.thickness_saved_mm)} mm</td>
      </tr>
      <tr>
        <td>${esc(L.rebar_density)}</td>
        <td class="n">${money(s.conv_rebar_kg_sqm, 1)} kg/m²</td>
        <td class="n">${money(s.pt_rebar_kg_sqm, 1)} kg/m²</td>
        <td class="n good">${money(s.conv_rebar_kg_sqm - s.pt_rebar_kg_sqm, 1)} kg/m²</td>
      </tr>
      ${compareRow(L.concrete, study.conventional.concrete, study.post_tension.concrete)}
      ${compareRow(L.rebar, study.conventional.rebar, study.post_tension.rebar)}
      ${compareRow(L.formwork, study.conventional.formwork, study.post_tension.formwork)}
      ${compareRow(L.pt_package, study.conventional.post_tension, study.post_tension.post_tension)}
      <tr class="total">
        <td>${esc(L.total_sqm)}</td>
        <td class="n">${cash2(study.conventional.per_sqm)}</td>
        <td class="n">${cash2(study.post_tension.per_sqm)}</td>
        <td class="n ${study.saving.slab_per_sqm >= 0 ? 'good' : 'bad'}">${cash2(study.saving.slab_per_sqm)}</td>
      </tr>
    </tbody>
  </table>

  <div class="chart">${costChart(study, L, currency, isAr)}</div>

  <h2>${esc(L.project_total_h)}</h2>
  <table>
    <tbody>
      <tr><td>${esc(L.slab_only)}</td><td class="n ${study.saving.slab_total >= 0 ? 'good' : 'bad'}">${cash(study.saving.slab_total)}</td></tr>
      <tr><td>${esc(L.foundation)}</td><td class="n good">${cash(study.saving.foundation_total)}</td></tr>
      <tr><td>${esc(L.programme)}</td><td class="n good">${cash(study.saving.programme_total)}</td></tr>
      <tr class="total"><td>${esc(L.net_saving)}</td><td class="n">${cash(study.saving.total)}</td></tr>
    </tbody>
  </table>

  <div class="headline">
    <div class="box main">
      <div class="lbl">${esc(L.net_saving)}</div>
      <div class="val ${study.saving.total >= 0 ? '' : 'neg'}">${cash(study.saving.total)}</div>
    </div>
    <div class="box">
      <div class="lbl">${esc(L.of_conventional)}</div>
      <div class="val ${study.saving.pct >= 0 ? '' : 'neg'}">${money(study.saving.pct, 1)}%</div>
    </div>
    <div class="box">
      <div class="lbl">${esc(L.b_days)}</div>
      <div class="val">${money(study.benefits.days_saved)} ${esc(L.unit_day)}</div>
    </div>
  </div>

  <div class="chart">${savingChart(study, L, currency)}</div>

  ${!study.saving.favours_pt_on_slab_alone ? `
  <div class="note">
    <b>${esc(L.slab_negative_h)}</b><br>${esc(L.slab_negative)}
  </div>` : ''}

  <h2>${esc(L.benefits_h)}</h2>
  <table>
    <tbody>
      <tr><td>${esc(L.b_concrete)}</td><td class="n">${money(study.benefits.concrete_saved_m3)} ${esc(L.unit_m3)}</td></tr>
      <tr><td>${esc(L.b_rebar)}</td><td class="n">${money(study.benefits.rebar_saved_ton, 1)} ${esc(L.unit_t)}</td></tr>
      <tr><td>${esc(L.b_weight)}</td><td class="n">${money(study.benefits.weight_saved_ton)} ${esc(L.unit_t)}</td></tr>
      <tr><td>${esc(L.b_thickness)}</td><td class="n">${money(study.benefits.thickness_saved_mm)} ${esc(L.unit_mm)}</td></tr>
      <tr><td>${esc(L.b_height)}</td><td class="n">${money(study.benefits.height_saved_mm)} ${esc(L.unit_mm)}</td></tr>
      <tr><td>${esc(L.b_days)}</td><td class="n">${money(study.benefits.days_saved)} ${esc(L.unit_day)}</td></tr>
    </tbody>
  </table>

  ${hasDrawings ? `
  <h2>${esc(L.drawings_h)}</h2>
  <div class="draws">
    ${drawingBlock('original', L.drawings_original)}
    ${drawingBlock('post_tension', L.drawings_pt)}
  </div>` : ''}

  ${notes ? `<h2>${esc(L.notes_h)}</h2><p>${esc(notes)}</p>` : ''}

  <div class="block">
    <h2>${esc(L.assumptions_h)}</h2>
    <p>${esc(L.assumptions)}</p>
  </div>

  <div class="sig">
    <p style="font-weight:700;color:var(--brand)">${esc(L.regards)}</p>
    <div class="l"><span class="k">${isAr ? 'الاسم' : 'Name'}</span><span class="line"></span></div>
    <div class="l"><span class="k">${isAr ? 'التوقيع' : 'Signature'}</span><span class="line"></span></div>
  </div>

</div>
</body>
</html>`;
}
