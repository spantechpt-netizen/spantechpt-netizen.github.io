/**
 * The cost comparison study, as the deck that goes to the building owner.
 *
 * This is the document that wins the job, so it is built as a presentation —
 * A4 landscape, one idea per slide — rather than a report: an owner reads a
 * headline and a chart, and hands the arithmetic to a consultant afterwards.
 *
 * Which is why the arithmetic is all still here. The rates used, the slab-only
 * comparison as well as the whole-building one, and the assumptions named as
 * assumptions: a deck that only showed the flattering number would be taken
 * apart in the first technical meeting, and the company would be in the room
 * when it happened.
 *
 * Charts are hand-built SVG strings because this opens in its own window with
 * no module loader and prints without a network.
 */
import { esc } from '../ui.js';

const money = (value, digits = 0) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

const LABELS = {
  ar: {
    doc_title: 'دراسة مقارنة التكلفة',
    doc_sub: 'الأسقف اللاحقة للشد مقابل النظام التقليدي',
    prepared_for: 'مقدمة إلى', prepared_by: 'إعداد', project: 'المشروع', location: 'الموقع',
    date: 'التاريخ', ref: 'مرجع العرض',

    profile_h: 'ليه سبان تك',
    profile_sub: 'خبرة تنفيذ وأكواد معتمدة وكوادر مؤهلة',
    vision: 'رؤيتنا', mission: 'رسالتنا',

    basis_h: 'أساس المقارنة',
    basis_sub: 'نفس المساحات ونفس أسعار السوق للنظامين',
    basis_system: 'النظام التقليدي محل المقارنة',
    basis_area: 'مساحة السقف للدور', basis_floors: 'عدد الأدوار',
    basis_total_area: 'إجمالي المساحة',
    rates_h: 'الأسعار المستخدمة',
    rate_concrete: 'الخرسانة (للمتر المكعب)',
    rate_rebar: 'حديد التسليح (للطن)',
    rate_formwork: 'الشدات (للمتر المربع)',
    rate_pt: 'أعمال الشد اللاحق (للمتر المربع)',
    quantities_h: 'الكميات الناتجة',
    q_concrete: 'الخرسانة', q_rebar: 'حديد التسليح',

    compare_h: 'مقارنة تكلفة السقف للمتر المربع',
    compare_sub: 'بند بند، بنفس الأسعار للطرفين',
    item: 'البند', conventional: 'النظام التقليدي', pt: 'الشد اللاحق', diff: 'الفرق',
    concrete: 'الخرسانة', rebar: 'حديد التسليح', formwork: 'الشدات',
    pt_package: 'أعمال الشد اللاحق', total_sqm: 'الإجمالي للمتر المربع',
    slab_thickness: 'سُمك السقف', rebar_density: 'كثافة الحديد',

    saving_h: 'الوفر على المشروع',
    saving_sub: 'فرق تكلفة الأسقف، وما يترتب عليه في باقي المبنى',
    slab_only: 'فرق تكلفة الأسقف',
    foundation: 'وفر الأساسات والأعمدة',
    programme: 'وفر مدة التنفيذ',
    net_saving: 'صافي الوفر',
    of_conventional: 'من تكلفة النظام التقليدي',
    slab_negative_h: 'ملاحظة على مقارنة الأسقف',
    slab_negative: 'تكلفة السقف اللاحق الشد في هذا المشروع أعلى من النظام التقليدي محل المقارنة على مستوى السقف وحده. '
      + 'الوفر الحقيقي يأتي مما يترتب على سقف أخف وأقل سُمكاً: الأساسات والأعمدة، ومدة التنفيذ، وارتفاع المبنى.',
    incomplete_h: 'الدراسة لسه مش مكتملة',
    incomplete: 'في أسعار لسه مش متعبّية في الدراسة، والأرقام المعروضة مبدئية لحد ما تتراجع.',

    programme_h: 'البرنامج الزمني والوزن',
    programme_sub: 'دورة صب أسرع، ومبنى أخف على الأساسات',
    prog_per_floor: 'مدة الدور الواحد',
    prog_total: 'إجمالي مدة الأسقف',
    b_concrete: 'خرسانة موفَّرة', b_rebar: 'حديد موفَّر', b_weight: 'تخفيف وزن المبنى',
    b_thickness: 'تقليل سُمك السقف', b_height: 'ارتفاع موفَّر على كامل المبنى',
    b_days: 'اختصار في مدة التنفيذ',
    unit_m3: 'م³', unit_t: 'طن', unit_mm: 'مم', unit_day: 'يوم',

    adv_h: 'مزايا النظام اللاحق للشد',
    adv_sub: 'اللي مش بيظهر في جدول التكلفة',
    adv1_h: 'بحور أكبر وأعمدة أقل',
    adv1: 'الشد اللاحق بيسمح ببحور أوسع بأعمدة أقل، يعني مساحات مفتوحة وجراجات بعدد سيارات أكبر ومرونة في التقسيم الداخلي.',
    adv2_h: 'مبنى أخف',
    adv2: 'سقف أنحف معناه حِمل ميت أقل على الأعمدة والأساسات، وقوى زلزالية أقل، والوفر ده بينزل لحد القواعد والخوازيق.',
    adv3_h: 'تنفيذ أسرع',
    adv3: 'دورة الصب بتقل لأن الشدات بتتفك بدري بعد الشد، والدور اللي بيتكسب من كل سقف بيتجمع على طول المشروع.',
    adv4_h: 'أداء أفضل للخرسانة',
    adv4: 'الضغط المسبق بيقفل الشروخ ويقلل الترخيم، فالسقف بيفضل مستوي ومقاوم للنفاذية على مدى عمر المبنى.',

    drawings_h: 'المخططات',
    drawings_sub: 'التصميم الأصلي مقابل التصميم المقترح',
    drawings_original: 'المخطط الأصلي قبل التحويل',
    drawings_pt: 'مخطط الشد اللاحق المقترح',

    notes_h: 'ملاحظات',
    assumptions_h: 'حدود الدراسة',
    assumptions: 'الأرقام مبنية على الأسعار والكميات الموضحة، وعلى تصميم مبدئي للأسقف اللاحقة للشد. '
      + 'وفر الأساسات والأعمدة ومدة التنفيذ تقديرات مبنية على خبرة الشركة في مشاريع مماثلة، '
      + 'وتحتاج مراجعة المصمم الإنشائي للمشروع. الدراسة لا تشمل أعمال الحفر والخوازيق أو أي بنود خارج الهيكل الإنشائي.',

    closing_h: 'شكراً لثقتكم',
    closing_sub: 'يسعدنا مناقشة الدراسة مع فريقكم الفني وتقديم تصميم مبدئي للمشروع.',
  },
  en: {
    doc_title: 'COST COMPARISON STUDY',
    doc_sub: 'Post-Tensioned Slabs vs. Conventional Construction',
    prepared_for: 'Prepared for', prepared_by: 'Prepared by', project: 'Project', location: 'Location',
    date: 'Date', ref: 'Quotation ref.',

    profile_h: 'Why Span Tech',
    profile_sub: 'Execution record, approved codes, qualified teams',
    vision: 'Our vision', mission: 'Our mission',

    basis_h: 'Basis of comparison',
    basis_sub: 'The same areas and the same market rates on both sides',
    basis_system: 'Conventional system compared against',
    basis_area: 'Slab area per floor', basis_floors: 'Number of floors',
    basis_total_area: 'Total area',
    rates_h: 'Rates used',
    rate_concrete: 'Concrete (per m³)',
    rate_rebar: 'Reinforcement (per tonne)',
    rate_formwork: 'Formwork (per m²)',
    rate_pt: 'Post-tensioning (per m²)',
    quantities_h: 'Resulting quantities',
    q_concrete: 'Concrete', q_rebar: 'Reinforcement',

    compare_h: 'Slab cost per square metre',
    compare_sub: 'Line by line, at the same rates for both systems',
    item: 'Item', conventional: 'Conventional', pt: 'Post-tensioned', diff: 'Difference',
    concrete: 'Concrete', rebar: 'Reinforcement', formwork: 'Formwork',
    pt_package: 'Post-tensioning package', total_sqm: 'Total per m²',
    slab_thickness: 'Slab thickness', rebar_density: 'Reinforcement density',

    saving_h: 'The saving on this project',
    saving_sub: 'The slab difference, and what follows from it in the rest of the building',
    slab_only: 'Slab cost difference',
    foundation: 'Foundations and columns saved',
    programme: 'Programme saving',
    net_saving: 'Net saving',
    of_conventional: 'of the conventional cost',
    slab_negative_h: 'A note on the slab comparison',
    slab_negative: 'On slab cost alone, the post-tensioned option is dearer than the conventional system '
      + 'compared here. The saving comes from what follows a lighter, thinner slab — foundations and '
      + 'columns, programme, and building height.',
    incomplete_h: 'This study is not complete yet',
    incomplete: 'Some rates have not been filled in, so the figures shown are provisional until they are reviewed.',

    programme_h: 'Programme and weight',
    programme_sub: 'A faster casting cycle, and a lighter building on the foundations',
    prog_per_floor: 'Cycle per floor',
    prog_total: 'Total slab programme',
    b_concrete: 'Concrete saved', b_rebar: 'Reinforcement saved', b_weight: 'Building weight removed',
    b_thickness: 'Slab depth saved', b_height: 'Height saved over the building',
    b_days: 'Programme shortened by',
    unit_m3: 'm³', unit_t: 't', unit_mm: 'mm', unit_day: 'days',

    adv_h: 'What post-tensioning gives you',
    adv_sub: 'The part that does not show up in a cost table',
    adv1_h: 'Longer spans, fewer columns',
    adv1: 'Wider spans on fewer columns mean open floor plates, more cars per level of parking, and freedom to change the internal layout later.',
    adv2_h: 'A lighter building',
    adv2: 'A thinner slab is less dead load on every column and footing below it, and less seismic mass — a saving that carries all the way down to the piles.',
    adv3_h: 'Faster construction',
    adv3: 'Formwork is struck early once the tendons are stressed, so the casting cycle shortens; the days saved on each floor accumulate across the programme.',
    adv4_h: 'Better concrete performance',
    adv4: 'Precompression closes cracks and reduces deflection, so the slab stays flat and resists water ingress over the life of the building.',

    drawings_h: 'Drawings',
    drawings_sub: 'The original design against the proposed one',
    drawings_original: 'Original design before conversion',
    drawings_pt: 'Proposed post-tensioned design',

    notes_h: 'Notes',
    assumptions_h: 'Scope of this study',
    assumptions: 'These figures rest on the rates and quantities shown and on a preliminary post-tensioned '
      + 'design. The foundation and programme savings are estimates from our experience on comparable '
      + 'projects and should be confirmed by the project’s structural designer. Excavation, piling and '
      + 'anything outside the structural frame are not included.',

    closing_h: 'Thank you',
    closing_sub: 'We would be glad to walk your technical team through this study and issue a preliminary design for the project.',
  },
};

// ---------------------------------------------------------------- charts
/**
 * Two stacked columns, conventional against post-tensioned, so the owner sees
 * not only which is cheaper but which part of the cost moved.
 */
function costChart(study, L, currency, isAr) {
  const parts = [
    { key: 'concrete', label: L.concrete, colour: '#1a56a7' },
    { key: 'rebar', label: L.rebar, colour: '#3d8bdd' },
    { key: 'formwork', label: L.formwork, colour: '#8fbdea' },
    { key: 'post_tension', label: L.pt_package, colour: '#c9a227' },
  ];
  const columns = [
    { name: isAr ? study.system.label_ar : study.system.label_en, side: study.conventional },
    { name: L.pt, side: study.post_tension },
  ];

  const max = Math.max(columns[0].side.per_sqm, columns[1].side.per_sqm, 1);
  const W = 560;
  const H = 300;
  const pad = { top: 22, bottom: 34, left: 58, right: 14 };
  const plotH = H - pad.top - pad.bottom;
  const barW = 104;
  const gap = 110;
  const startX = pad.left + 60;

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
    bars += `<text x="${x + barW / 2}" y="${pad.top + plotH + 20}" text-anchor="middle" font-size="12" fill="#17202b">${esc(column.name)}</text>`;
    bars += `<text x="${x + barW / 2}" y="${(pad.top + plotH - (column.side.per_sqm / max) * plotH - 7).toFixed(1)}" text-anchor="middle" font-size="14" font-weight="700" fill="#0a2647">${money(column.side.per_sqm)}</text>`;
  });

  // Four gridlines are enough to read the scale without crowding the bars.
  let grid = '';
  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i;
    const y = pad.top + plotH - (i / 4) * plotH;
    grid += `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${W - pad.right}" y2="${y.toFixed(1)}" stroke="#e5eaef" stroke-width="1"/>`;
    grid += `<text x="${pad.left - 7}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="10" fill="#5b6775">${money(value)}</text>`;
  }

  // The legend is HTML, not SVG: laying out four labels of unknown width by
  // hand goes wrong the moment the language changes.
  const legend = parts.map((part) => `
    <span class="lg"><i style="background:${part.colour}"></i>${esc(part.label)}</span>`).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.compare_h)}">
    ${grid}${bars}
    <text x="${pad.left - 7}" y="${pad.top - 6}" text-anchor="end" font-size="9.5" fill="#8a94a1">${esc(currency)}</text>
  </svg>
  <div class="legend">${legend}</div>`;
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
  const W = 560;
  const rowH = 40;
  const H = rows.length * rowH + 16;
  const labelW = 190;
  // Half the width is reserved for bars below the line only when there are
  // any; otherwise the positive bars get the whole canvas and stay readable.
  const negative = rows.some((row) => row.value < 0);
  const track = W - labelW - 26;
  const halfW = negative ? track / 2 : track - 60;
  const zeroX = negative ? labelW + halfW : labelW;

  const bars = rows.map((row, index) => {
    const y = index * rowH + 10;
    const w = (Math.abs(row.value) / max) * halfW;
    const x = row.value >= 0 ? zeroX : zeroX - w;
    const colour = row.strong
      ? (row.value >= 0 ? '#0f7350' : '#a32020')
      : (row.value >= 0 ? '#1a56a7' : '#c2410c');
    return `
      <text x="${labelW - 10}" y="${y + 18}" text-anchor="end" font-size="12" fill="#17202b"${row.strong ? ' font-weight="700"' : ''}>${esc(row.label)}</text>
      <rect x="${x.toFixed(1)}" y="${y + 4}" width="${Math.max(w, 1).toFixed(1)}" height="19" fill="${colour}" rx="1"/>
      <text x="${(row.value >= 0 ? x + w + 7 : x - 7).toFixed(1)}" y="${y + 18}" text-anchor="${row.value >= 0 ? 'start' : 'end'}" font-size="11.5" fill="#5b6775">${money(row.value)}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.net_saving)}">
    <line x1="${zeroX}" y1="4" x2="${zeroX}" y2="${H - 8}" stroke="#c8d3e0" stroke-width="1"/>
    ${bars}
    <text x="${W - 4}" y="${H - 2}" text-anchor="end" font-size="9.5" fill="#8a94a1">${esc(currency)}</text>
  </svg>`;
}

/** The two programmes side by side, in days, for the whole structure. */
function programmeChart(study, L) {
  const rows = [
    { label: L.conventional, value: study.benefits.conv_programme_days, colour: '#5b6775' },
    { label: L.pt, value: study.benefits.pt_programme_days, colour: '#0f7350' },
  ];
  const max = Math.max(...rows.map((r) => r.value), 1);
  const W = 560;
  const H = 150;
  const labelW = 170;
  const barMax = W - labelW - 90;

  const bars = rows.map((row, index) => {
    const y = 22 + index * 56;
    const w = (row.value / max) * barMax;
    return `
      <text x="${labelW - 10}" y="${y + 24}" text-anchor="end" font-size="12.5" fill="#17202b">${esc(row.label)}</text>
      <rect x="${labelW}" y="${y}" width="${Math.max(w, 2).toFixed(1)}" height="34" fill="${row.colour}" rx="2"/>
      <text x="${(labelW + w + 10).toFixed(1)}" y="${y + 23}" font-size="14" font-weight="700" fill="#0a2647">${money(row.value)} ${esc(L.unit_day)}</text>`;
  }).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.programme_h)}">${bars}</svg>`;
}

// -------------------------------------------------------------- document
export function printStudy(data, lang = 'ar') {
  const html = buildStudyDeck(data, lang);
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

function buildStudyDeck(data, lang) {
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
  const branchName = (isAr ? (branch.name_ar || company.name_ar) : (branch.name_en || company.name_en)) || '';

  const cash = (value) => `${money(value)} ${currency}`;

  // ------------------------------------------------------------- fragments
  const kv = (label, value) => `
    <tr><td>${esc(label)}</td><td class="n">${value}</td></tr>`;

  // Bare numbers in the comparison table: the currency is stated once in the
  // column head, because "1,234.00 SAR" in every cell wraps the column.
  const plain2 = (value) => money(value, 2);

  const compareRow = (label, conv, pt, formatter = plain2) => `
    <tr>
      <td>${esc(label)}</td>
      <td class="n">${formatter(conv)}</td>
      <td class="n">${formatter(pt)}</td>
      <td class="n ${conv - pt >= 0 ? 'good' : 'bad'}">${formatter(conv - pt)}</td>
    </tr>`;

  const stat = (label, value, unit = '') => `
    <div class="stat">
      <div class="v">${value}${unit ? ` <span class="u">${esc(unit)}</span>` : ''}</div>
      <div class="k">${esc(label)}</div>
    </div>`;

  const card = (heading, text) => `
    <div class="card">
      <div class="card-h">${esc(heading)}</div>
      <p>${esc(text)}</p>
    </div>`;

  const drawings = (kind) => (data.drawings || []).filter((d) => d.kind === kind);
  const drawingColumn = (kind, heading) => {
    const list = drawings(kind);
    return `
      <div class="draw-col">
        <div class="draw-h">${esc(heading)}</div>
        ${list.length ? list.map((d) => `
          <figure>
            <img src="${esc(d.url)}" alt="${esc((isAr ? d.caption_ar : d.caption_en) || heading)}">
            ${(isAr ? d.caption_ar : d.caption_en)
              ? `<figcaption>${esc(isAr ? d.caption_ar : d.caption_en)}</figcaption>` : ''}
          </figure>`).join('') : '<div class="draw-empty"></div>'}
      </div>`;
  };
  const hasDrawings = drawings('original').length || drawings('post_tension').length;

  // ------------------------------------------------------------ the slides
  const slides = [];
  const slide = (title, body, options = {}) => slides.push({ title, body, ...options });

  // 1 — cover
  slide('', `
    <div class="cover-in">
      <div class="cover-logo"><img src="${esc(branch.logo || '/assets/img/logo@2x.png')}" alt=""></div>
      <div class="cover-rule"></div>
      <h1>${esc(L.doc_title)}</h1>
      <div class="cover-sub">${esc(L.doc_sub)}</div>
      <div class="cover-meta">
        ${projectName ? `<div><span>${esc(L.project)}</span>${esc(projectName)}</div>` : ''}
        ${customerName ? `<div><span>${esc(L.prepared_for)}</span>${esc(customerName)}</div>` : ''}
        ${location ? `<div><span>${esc(L.location)}</span>${esc(location)}</div>` : ''}
        <div><span>${esc(L.prepared_by)}</span>${esc(branchName)}</div>
        <div><span>${esc(L.ref)}</span><bdi>${esc(q.number || '—')}</bdi></div>
        <div><span>${esc(L.date)}</span><bdi>${esc(data.generated_at || '')}</bdi></div>
      </div>
    </div>`, { className: 'cover', bare: true });

  // 2 — why us
  slide(L.profile_h, `
    <div class="cards four">
      ${profile.map((line) => `<div class="card plain"><p>${esc(line)}</p></div>`).join('')}
    </div>
    <div class="cols two mt">
      <div class="quote"><div class="card-h">${esc(L.vision)}</div><p>${esc(isAr ? company.vision_ar : company.vision_en)}</p></div>
      <div class="quote"><div class="card-h">${esc(L.mission)}</div><p>${esc(isAr ? company.mission_ar : company.mission_en)}</p></div>
    </div>`, { kicker: L.profile_sub });

  // 3 — basis and rates
  slide(L.basis_h, `
    <div class="cols two">
      <div>
        <table>
          <tbody>
            <tr><td>${esc(L.basis_system)}</td><td class="txt">${esc(systemName)}</td></tr>
            ${kv(L.basis_area, `${money(study.area_sqm)} m²`)}
            ${kv(L.basis_floors, money(study.floors))}
            <tr class="total"><td>${esc(L.basis_total_area)}</td><td class="n">${money(study.total_area_sqm)} m²</td></tr>
          </tbody>
        </table>
        <div class="sec-h">${esc(L.quantities_h)}</div>
        <table>
          <thead><tr><th>${esc(L.item)}</th><th class="n">${esc(systemName)}</th><th class="n">${esc(L.pt)}</th></tr></thead>
          <tbody>
            <tr>
              <td>${esc(L.q_concrete)}</td>
              <td class="n">${money(study.conventional.concrete_m3)} ${esc(L.unit_m3)}</td>
              <td class="n">${money(study.post_tension.concrete_m3)} ${esc(L.unit_m3)}</td>
            </tr>
            <tr>
              <td>${esc(L.q_rebar)}</td>
              <td class="n">${money(study.conventional.rebar_ton, 1)} ${esc(L.unit_t)}</td>
              <td class="n">${money(study.post_tension.rebar_ton, 1)} ${esc(L.unit_t)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div>
        <div class="sec-h">${esc(L.rates_h)}</div>
        <table>
          <tbody>
            ${kv(L.rate_concrete, cash(s.concrete_rate_m3))}
            ${kv(L.rate_rebar, cash(s.rebar_rate_ton))}
            ${kv(L.rate_formwork, cash(s.formwork_rate_sqm))}
            ${kv(L.rate_pt, cash(s.pt_rate_sqm))}
          </tbody>
        </table>
        ${!study.complete ? `
        <div class="note">
          <b>${esc(L.incomplete_h)}</b><br>${esc(L.incomplete)}
        </div>` : ''}
      </div>
    </div>`, { kicker: L.basis_sub });

  // 4 — the comparison itself
  slide(L.compare_h, `
    <div class="cols two">
      <table class="cmp">
        <thead>
          <tr>
            <th>${esc(L.item)}</th>
            <th class="n">${esc(systemName)}<span class="cur">${esc(currency)}</span></th>
            <th class="n">${esc(L.pt)}<span class="cur">${esc(currency)}</span></th>
            <th class="n">${esc(L.diff)}<span class="cur">${esc(currency)}</span></th>
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
            <td class="n">${money(study.conventional.rebar_kg_m3)} kg/m³</td>
            <td class="n">${money(study.post_tension.rebar_kg_m3)} kg/m³</td>
            <td class="n good">${money(study.conventional.rebar_kg_m3 - study.post_tension.rebar_kg_m3)} kg/m³</td>
          </tr>
          ${compareRow(L.concrete, study.conventional.concrete, study.post_tension.concrete)}
          ${compareRow(L.rebar, study.conventional.rebar, study.post_tension.rebar)}
          ${compareRow(L.formwork, study.conventional.formwork, study.post_tension.formwork)}
          ${compareRow(L.pt_package, study.conventional.post_tension, study.post_tension.post_tension)}
          <tr class="total">
            <td>${esc(L.total_sqm)}</td>
            <td class="n">${plain2(study.conventional.per_sqm)}</td>
            <td class="n">${plain2(study.post_tension.per_sqm)}</td>
            <td class="n ${study.saving.slab_per_sqm >= 0 ? 'good' : 'bad'}">${plain2(study.saving.slab_per_sqm)}</td>
          </tr>
        </tbody>
      </table>
      <div class="chart">${costChart(study, L, currency, isAr)}</div>
    </div>`, { kicker: L.compare_sub });

  // 5 — the number the owner is here for
  slide(L.saving_h, `
    <div class="hero">
      <div class="hero-main ${study.saving.total >= 0 ? '' : 'neg'}">
        <div class="k">${esc(L.net_saving)}</div>
        <div class="v">${cash(study.saving.total)}</div>
      </div>
      <div class="hero-side">
        ${stat(L.of_conventional, `${money(study.saving.pct, 1)}%`)}
        ${stat(L.b_days, money(study.benefits.days_saved), L.unit_day)}
      </div>
    </div>
    <div class="cols two mt">
      <table>
        <tbody>
          <tr><td>${esc(L.slab_only)}</td><td class="n ${study.saving.slab_total >= 0 ? 'good' : 'bad'}">${cash(study.saving.slab_total)}</td></tr>
          <tr><td>${esc(L.foundation)}</td><td class="n good">${cash(study.saving.foundation_total)}</td></tr>
          <tr><td>${esc(L.programme)}</td><td class="n good">${cash(study.saving.programme_total)}</td></tr>
          <tr class="total"><td>${esc(L.net_saving)}</td><td class="n">${cash(study.saving.total)}</td></tr>
        </tbody>
      </table>
      <div class="chart">${savingChart(study, L, currency)}</div>
    </div>
    ${!study.saving.favours_pt_on_slab_alone ? `
    <div class="note mt">
      <b>${esc(L.slab_negative_h)}</b> ${esc(L.slab_negative)}
    </div>` : ''}`, { kicker: L.saving_sub });

  // 6 — programme and weight
  slide(L.programme_h, `
    <div class="cols two">
      <div>
        <div class="chart">${programmeChart(study, L)}</div>
        <table class="mt">
          <thead>
            <tr>
              <th>${esc(L.item)}</th>
              <th class="n">${esc(systemName)}</th>
              <th class="n">${esc(L.pt)}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>${esc(L.prog_per_floor)}</td>
              <td class="n">${money(s.conv_cycle_days)} ${esc(L.unit_day)}</td>
              <td class="n">${money(s.pt_cycle_days)} ${esc(L.unit_day)}</td>
            </tr>
            <tr>
              <td>${esc(L.prog_total)}</td>
              <td class="n">${money(study.benefits.conv_programme_days)} ${esc(L.unit_day)}</td>
              <td class="n">${money(study.benefits.pt_programme_days)} ${esc(L.unit_day)}</td>
            </tr>
            <tr class="total">
              <td>${esc(L.b_days)}</td>
              <td class="n" colspan="2">${money(study.benefits.days_saved)} ${esc(L.unit_day)}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="stats">
        ${stat(L.b_weight, money(study.benefits.weight_saved_ton), L.unit_t)}
        ${stat(L.b_concrete, money(study.benefits.concrete_saved_m3), L.unit_m3)}
        ${stat(L.b_rebar, money(study.benefits.rebar_saved_ton, 1), L.unit_t)}
        ${stat(L.b_thickness, money(study.benefits.thickness_saved_mm), L.unit_mm)}
        ${stat(L.b_height, money(study.benefits.height_saved_mm), L.unit_mm)}
      </div>
    </div>`, { kicker: L.programme_sub });

  // 7 — the case that is not about money
  slide(L.adv_h, `
    <div class="cards four tall">
      ${card(L.adv1_h, L.adv1)}
      ${card(L.adv2_h, L.adv2)}
      ${card(L.adv3_h, L.adv3)}
      ${card(L.adv4_h, L.adv4)}
    </div>`, { kicker: L.adv_sub });

  // 8 — the drawings, when the engineer has attached them
  if (hasDrawings) {
    slide(L.drawings_h, `
      <div class="draws">
        ${drawingColumn('original', L.drawings_original)}
        ${drawingColumn('post_tension', L.drawings_pt)}
      </div>`, { kicker: L.drawings_sub });
  }

  // 9 — what this study does and does not claim
  slide(L.assumptions_h, `
    <div class="cols ${notes ? 'two' : 'one'}">
      <div class="prose">${esc(L.assumptions)}</div>
      ${notes ? `<div><div class="sec-h">${esc(L.notes_h)}</div><div class="prose">${esc(notes)}</div></div>` : ''}
    </div>`);

  // 10 — close
  slide('', `
    <div class="cover-in">
      <div class="cover-logo"><img src="${esc(branch.logo || '/assets/img/logo@2x.png')}" alt=""></div>
      <div class="cover-rule"></div>
      <h1>${esc(L.closing_h)}</h1>
      <div class="cover-sub">${esc(L.closing_sub)}</div>
      <div class="cover-meta">
        <div>${esc(branchName)}</div>
        ${(isAr ? branch.address_ar : branch.address_en) ? `<div>${esc(isAr ? branch.address_ar : branch.address_en)}</div>` : ''}
        <div class="mono">${[branch.phone, branch.email, branch.website].filter(Boolean).map((x) => esc(x)).join('&nbsp;&nbsp;·&nbsp;&nbsp;')}</div>
      </div>
    </div>`, { className: 'cover', bare: true });

  // --------------------------------------------------------------- markup
  const total = slides.length;
  const deck = slides.map((item, index) => `
  <section class="slide ${item.className || ''}">
    ${item.bare ? '' : `
    <header class="s-head">
      <div>
        <h2>${esc(item.title)}</h2>
        ${item.kicker ? `<div class="kick">${esc(item.kicker)}</div>` : ''}
      </div>
      <img class="s-logo" src="${esc(branch.logo || '/assets/img/logo@2x.png')}" alt="">
    </header>`}
    <div class="s-body">${item.body}</div>
    ${item.bare ? '' : `
    <footer class="s-foot">
      <span>${esc(projectName || branchName)}</span>
      <span class="pg">${index + 1} / ${total}</span>
    </footer>`}
  </section>`).join('');

  return `<!doctype html>
<html lang="${lang}" dir="${dir}">
<head>
<meta charset="utf-8">
<title>${esc(L.doc_title)} — ${esc(projectName)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&family=Inter:wght@400;500;600;700;800&display=swap">
<style>
  /* One slide per sheet. The page number is drawn inside the slide because a
     zero-margin page has no margin box to put it in. */
  @page { size: A4 landscape; margin: 0; }

  :root {
    --navy:#0a2647; --navy-2:#123a63; --mid:#1a56a7; --gold:#c9a227;
    --wash:#eef3fa; --line:#c8d3e0; --grey:#5b6775; --ink:#17202b;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: #e9edf2; color: var(--ink);
    font-family: ${isAr ? "'Cairo','Tajawal',Tahoma,sans-serif" : "'Inter','Segoe UI',Arial,sans-serif"};
    font-size: 10.5pt; line-height: 1.55;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }

  .slide {
    position: relative; width: 297mm; height: 210mm; margin: 0 auto 8mm;
    padding: 11mm 14mm 9mm; background: #fff; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 2px 14px rgba(10,38,71,.16);
    break-after: page; page-break-after: always;
  }
  .slide:last-child { break-after: auto; page-break-after: auto; margin-bottom: 0; }

  @media print {
    body { background: #fff; }
    .slide { margin: 0; box-shadow: none; }
    .no-print { display: none !important; }
  }

  .toolbar { position: sticky; top: 0; z-index: 10; display: flex; gap: .5rem; justify-content: center; padding: 10px; background: var(--navy); }
  .toolbar button { padding: 7px 18px; border: 0; border-radius: 5px; background: #fff; color: var(--navy); font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer; }
  .toolbar button.ghost { background: transparent; color: #fff; box-shadow: inset 0 0 0 1px rgba(255,255,255,.5); }

  /* ------------------------------------------------------------ slide frame */
  .s-head { display: flex; align-items: flex-start; gap: 10mm; padding-bottom: 4mm; border-bottom: 2.5px solid var(--navy); }
  .s-head h2 { margin: 0; font-size: 20pt; font-weight: 800; color: var(--navy); line-height: 1.2; }
  .s-head .kick { margin-top: 1mm; font-size: 10pt; color: var(--grey); }
  .s-head .s-logo { margin-inline-start: auto; max-height: 15mm; max-width: 45mm; }
  /* Centred, so a slide with three lines on it does not look like a slide
     whose bottom half failed to print. */
  .s-body { flex: 1; min-height: 0; padding-top: 6mm; display: flex; flex-direction: column; justify-content: center; }
  .slide.cover .s-body { padding: 0; }
  .s-foot { display: flex; align-items: center; justify-content: space-between; padding-top: 3mm; border-top: 1px solid var(--line); font-size: 8.5pt; color: var(--grey); }
  .s-foot .pg { direction: ltr; unicode-bidi: plaintext; font-weight: 700; color: var(--navy); }

  /* ------------------------------------------------------------------ cover */
  .slide.cover { background: var(--navy); color: #fff; justify-content: center; padding: 0; }
  .slide.cover::after {
    content: ''; position: absolute; inset-inline-end: -40mm; bottom: -60mm;
    width: 160mm; height: 160mm; border-radius: 50%; background: rgba(255,255,255,.04);
  }
  .cover-in { position: relative; z-index: 1; padding: 0 26mm; }
  .cover-logo { display: inline-block; padding: 5mm 7mm; background: #fff; border-radius: 3mm; }
  .cover-logo img { display: block; max-height: 20mm; max-width: 60mm; }
  .cover-rule { width: 38mm; height: 2.2mm; margin: 8mm 0 6mm; background: var(--gold); border-radius: 2mm; }
  .slide.cover h1 { margin: 0; font-size: 30pt; font-weight: 800; letter-spacing: .01em; line-height: 1.18; }
  .cover-sub { margin-top: 3mm; font-size: 13pt; color: #b9cbe4; max-width: 190mm; }
  .cover-meta { margin-top: 12mm; font-size: 11pt; color: #dce6f3; }
  .cover-meta > div { margin-bottom: 1.6mm; }
  .cover-meta span { display: inline-block; min-width: 30mm; color: var(--gold); font-weight: 700; }
  .cover-meta .mono { direction: ltr; unicode-bidi: plaintext; font-size: 10pt; }

  /* ----------------------------------------------------------- layout bits */
  .cols { display: grid; gap: 9mm; align-items: start; }
  .cols.two { grid-template-columns: 1fr 1fr; }
  .cols.one { grid-template-columns: 1fr; }
  .mt { margin-top: 6mm; }
  .sec-h { margin: 0 0 3mm; font-size: 11.5pt; font-weight: 800; color: var(--mid); }
  .prose { font-size: 11pt; line-height: 1.75; text-align: justify; color: var(--ink); }

  table { width: 100%; border-collapse: collapse; font-size: 10pt; }
  table + .sec-h { margin-top: 6mm; }
  th, td { padding: 2.4mm 3mm; border: 1px solid var(--line); text-align: ${isAr ? 'right' : 'left'}; }
  thead th { background: var(--navy); color: #fff; font-weight: 700; font-size: 9.4pt; }
  /* plaintext, so a figure reads in the direction of its own unit: "50 mm"
     stays Latin and left to right, while "9,450 م³" is laid out as Arabic
     prose with the number first. */
  td.n, th.n { text-align: ${isAr ? 'left' : 'right'}; direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }
  td.txt { text-align: ${isAr ? 'left' : 'right'}; }
  table.cmp td:first-child, table.cmp th:first-child { width: 30%; }
  th .cur { display: block; font-size: 8pt; font-weight: 500; opacity: .75; }
  tr.total td { background: var(--wash); font-weight: 800; color: var(--navy); }
  td.good { color: #0f7350; font-weight: 700; }
  td.bad  { color: #a32020; font-weight: 700; }

  .chart svg { display: block; width: 100%; height: auto; }
  .legend { display: flex; flex-wrap: wrap; gap: 2mm 6mm; margin-top: 3mm; font-size: 9pt; color: var(--grey); }
  .legend .lg { display: inline-flex; align-items: center; gap: 2mm; }
  .legend i { width: 3.2mm; height: 3.2mm; border-radius: .6mm; }

  .cards { display: grid; gap: 6mm; }
  .cards.four { grid-template-columns: repeat(4, 1fr); }
  .card { padding: 6mm; background: var(--wash); border-top: 3px solid var(--gold); border-radius: 0 0 2mm 2mm; }
  .card.plain { border-top-color: var(--mid); }
  .cards.tall .card { height: 100%; }
  .card-h { margin-bottom: 2.5mm; font-size: 12pt; font-weight: 800; color: var(--navy); }
  .card p, .quote p { margin: 0; font-size: 10.2pt; line-height: 1.65; }
  .quote { padding: 6mm; border-${isAr ? 'right' : 'left'}: 3px solid var(--mid); background: #f7f9fc; }

  .hero { display: flex; gap: 8mm; align-items: stretch; }
  .hero-main { flex: 2; padding: 8mm; background: var(--navy); color: #fff; border-radius: 2mm; }
  .hero-main.neg { background: #7a1d1d; }
  .hero-main .k { font-size: 11pt; color: var(--gold); font-weight: 700; }
  .hero-main .v { margin-top: 2mm; font-size: 30pt; font-weight: 800; line-height: 1.1; direction: ltr; unicode-bidi: plaintext; }
  .hero-side { flex: 1; display: grid; gap: 4mm; }

  .stats { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; align-content: start; }
  .stat { padding: 5mm; background: var(--wash); border-radius: 2mm; text-align: center; }
  .hero-side .stat { display: flex; flex-direction: column; justify-content: center; }
  .stat .v { font-size: 19pt; font-weight: 800; color: var(--navy); direction: ltr; unicode-bidi: plaintext; }
  .stat .v .u { font-size: 11pt; font-weight: 700; color: var(--grey); }
  .stat .k { font-size: 9.6pt; color: var(--grey); }

  .note { margin-top: 5mm; padding: 4mm 5mm; background: #fdf7ee; border: 1px solid #e8c9a0; border-radius: 2mm; font-size: 10pt; }
  .note b { color: #8a5a10; }

  .draws { display: grid; grid-template-columns: 1fr 1fr; gap: 9mm; height: 100%; }
  .draw-col { display: flex; flex-direction: column; min-height: 0; }
  .draw-h { margin-bottom: 3mm; font-size: 11.5pt; font-weight: 800; color: var(--navy); text-align: center; }
  figure { margin: 0 0 3mm; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  figure img { width: 100%; flex: 1; min-height: 0; object-fit: contain; border: 1px solid var(--line); border-radius: 1mm; }
  figcaption { margin-top: 2mm; font-size: 9pt; color: var(--grey); text-align: center; }
  .draw-empty { flex: 1; border: 1px dashed var(--line); border-radius: 1mm; }
</style>
</head>
<body>

<div class="toolbar no-print">
  <button onclick="window.print()">${isAr ? 'طباعة / حفظ PDF' : 'Print / Save as PDF'}</button>
  <button class="ghost" onclick="window.close()">${isAr ? 'إغلاق' : 'Close'}</button>
</div>
${deck}
</body>
</html>`;
}
