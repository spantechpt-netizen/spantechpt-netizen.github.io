/**
 * The cost comparison study, as the deck that goes to the building owner.
 *
 * It has two lives. It is projected in a meeting — so the slides are 16:9,
 * the type is large enough to read from the back of a room, and there is a
 * presenter mode with keyboard navigation — and it is sent as a PDF
 * afterwards, so every slide also prints exactly as it appears.
 *
 * The arithmetic is all here, including the slab-only comparison when that one
 * goes against us: a deck that showed only the flattering number would be
 * taken apart in the first technical meeting, with the company in the room.
 *
 * Charts are hand-built SVG because this document opens in its own window with
 * no module loader and prints without a network.
 */
import { esc } from '../ui.js';

const money = (value, digits = 0) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

/** Slide geometry, in the units the charts and the stylesheet both work in. */
const SLIDE = { w: 338.67, h: 190.5 };   // mm — 13.333in × 7.5in, the widescreen standard

const C = {
  navy: '#0a2647',
  navyDeep: '#061a33',
  mid: '#1a56a7',
  sky: '#4d90dd',
  pale: '#a8c8ec',
  gold: '#c9a227',
  goldLight: '#e3c35c',
  green: '#0f7350',
  red: '#a32020',
  ink: '#152233',
  grey: '#5f6c7d',
  line: '#dbe3ec',
  ice: '#f2f6fb',
};

/**
 * Line icons, drawn rather than imported: the deck has to render on a machine
 * with no internet, and an icon font would be one more thing to install.
 */
const ICONS = {
  span: 'M3 20h18M6 20V9M18 20V9M3 9h18M8.5 9c0 2 1.5 3.5 3.5 3.5S15.5 11 15.5 9',
  weight: 'M12 3.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM6.5 20.5l1.8-9h7.4l1.8 9z',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7.5V12l3 1.8',
  shield: 'M12 3l7.5 3v5.5c0 4.8-3.1 7.9-7.5 9.5-4.4-1.6-7.5-4.7-7.5-9.5V6z',
  ruler: 'M3.5 14.5l7-7 6 6-7 7zM12 6l6 6M9.5 8.5l1.5 1.5M7.5 10.5l1.5 1.5M5.5 12.5L7 14',
  cube: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  steel: 'M4 7h16M4 12h16M4 17h16M8 4v16M16 4v16',
  calendar: 'M4.5 6h15v14h-15zM4.5 10h15M9 3.5v4M15 3.5v4',
  money: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v10M14.8 9.4c0-1.1-1.2-1.7-2.8-1.7s-2.8.6-2.8 1.8c0 2.6 5.6 1.4 5.6 4 0 1.2-1.2 1.8-2.8 1.8s-2.8-.6-2.8-1.8',
  layers: 'M12 3.5L3 8l9 4.5L21 8zM3 12.5L12 17l9-4.5M3 16.5L12 21l9-4.5',
  phone: 'M6.5 3.5h3l1.5 4-2 1.5a12 12 0 0 0 6 6l1.5-2 4 1.5v3a1.5 1.5 0 0 1-1.6 1.5C10.9 19.5 4.5 13.1 4.5 5.1A1.5 1.5 0 0 1 6.5 3.5z',
  mail: 'M3.5 6h17v12h-17zM3.5 7l8.5 6 8.5-6',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3.5 12h17M12 3c3 4.5 3 13.5 0 18M12 3c-3 4.5-3 13.5 0 18',
  pin: 'M12 21s6.5-6.1 6.5-10.5a6.5 6.5 0 1 0-13 0C5.5 14.9 12 21 12 21zM12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z',
};

const icon = (name, size = 22, colour = C.gold) => `
  <svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="${colour}"
       stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="${ICONS[name] || ICONS.layers}"/>
  </svg>`;

/**
 * Gradients and the soft shadow every chart shares — with ids of their own per
 * chart. Repeating one id across the document makes every reference resolve to
 * the first copy, and in presenting mode that copy lives on a hidden slide, so
 * the bars it paints simply do not appear.
 */
let defsSeq = 0;
const nextDefs = () => `d${++defsSeq}-`;

const CHART_DEFS = (p) => `
  <defs>
    <linearGradient id="${p}gConv" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#7f93ab"/><stop offset="100%" stop-color="#5f6c7d"/>
    </linearGradient>
    <linearGradient id="${p}gConcrete" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2e6cc0"/><stop offset="100%" stop-color="#17417a"/>
    </linearGradient>
    <linearGradient id="${p}gRebar" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#5d9ce4"/><stop offset="100%" stop-color="#2e6cc0"/>
    </linearGradient>
    <linearGradient id="${p}gForm" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#a8c8ec"/><stop offset="100%" stop-color="#7fb0e0"/>
    </linearGradient>
    <linearGradient id="${p}gPT" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#e3c35c"/><stop offset="100%" stop-color="#b8901c"/>
    </linearGradient>
    <linearGradient id="${p}gGreen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#1a9a6c"/><stop offset="100%" stop-color="#0c5c3f"/>
    </linearGradient>
    <linearGradient id="${p}gRed" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#c84a4a"/><stop offset="100%" stop-color="#8e1b1b"/>
    </linearGradient>
    <filter id="${p}soft" x="-20%" y="-20%" width="140%" height="160%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0a2647" flood-opacity=".18"/>
    </filter>
  </defs>`;
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
    b_thickness: 'تقليل سُمك السقف', b_height: 'ارتفاع موفَّر في المبنى',
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

    // --- deck furniture
    agenda_h: 'محتويات العرض',
    sec_company: 'سبان تك', sec_basis: 'أساس المقارنة', sec_cost: 'المقارنة',
    sec_saving: 'الوفر', sec_time: 'الزمن والوزن', sec_adv: 'المزايا',
    sec_drawings: 'المخططات', sec_limits: 'الحدود',
    per_sqm_short: 'للمتر المربع',
    diff_label: 'الفرق لصالح الشد اللاحق',
    diff_label_neg: 'فرق ضد الشد اللاحق على السقف وحده',
    composition_h: 'مكوّنات التكلفة',
    qty_concrete_h: 'الخرسانة المطلوبة', qty_rebar_h: 'حديد التسليح المطلوب',
    waterfall_h: 'من فين بييجي الوفر',
    start_point: 'تكلفة النظام التقليدي',
    end_point: 'تكلفة الشد اللاحق بعد الوفر',
    timeline_h: 'مدة تنفيذ الأسقف',
    months: 'شهر تقريباً',
    present: 'وضع العرض', print_btn: 'طباعة / حفظ PDF', close_btn: 'إغلاق',
    hint_keys: 'الأسهم للتنقل · Esc للخروج',
    edit_btn: 'تعديل الشرائح', edit_save: 'حفظ التعديلات', edit_reset: 'رجوع للنص الأصلي',
    edit_done: 'إنهاء التعديل',
    edit_hint: 'دوس على أي نص وغيّره · وتقدر تخفي أي شريحة',
    edit_hide: 'إخفاء الشريحة', edit_show: 'إظهار الشريحة',
    edit_saved: 'التعديلات اتحفظت', edit_failed: 'التعديلات ماتحفظتش',
    edit_unsaved: 'في تعديلات لسه ما اتحفظتش. تقفل برضه؟',
    edit_reset_ask: 'هترجّع كل النصوص لأصلها. تمام؟',
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
    b_thickness: 'Slab depth saved', b_height: 'Height saved',
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

    // --- deck furniture
    agenda_h: 'Contents',
    sec_company: 'Span Tech', sec_basis: 'Basis', sec_cost: 'Comparison',
    sec_saving: 'The saving', sec_time: 'Time and weight', sec_adv: 'Advantages',
    sec_drawings: 'Drawings', sec_limits: 'Limits',
    per_sqm_short: 'per m²',
    diff_label: 'In favour of post-tensioning',
    diff_label_neg: 'Against post-tensioning on the slab alone',
    composition_h: 'What the cost is made of',
    qty_concrete_h: 'Concrete required', qty_rebar_h: 'Reinforcement required',
    waterfall_h: 'Where the saving comes from',
    start_point: 'Conventional cost',
    end_point: 'Post-tensioned cost after the saving',
    timeline_h: 'Slab construction time',
    months: 'months approx.',
    present: 'Present', print_btn: 'Print / Save as PDF', close_btn: 'Close',
    hint_keys: 'Arrow keys to move · Esc to exit',
    edit_btn: 'Edit slides', edit_save: 'Save changes', edit_reset: 'Restore original text',
    edit_done: 'Done',
    edit_hint: 'Click any text to change it · and hide any slide you do not want',
    edit_hide: 'Hide this slide', edit_show: 'Show this slide',
    edit_saved: 'Changes saved', edit_failed: 'Could not save the changes',
    edit_unsaved: 'You have unsaved changes. Close anyway?',
    edit_reset_ask: 'This puts every sentence back as it was generated. Go ahead?',
    closing_h: 'Thank you',
    closing_sub: 'We would be glad to walk your technical team through this study and issue a preliminary design for the project.',
  },
};

// ------------------------------------------------------------------- charts
/** A rounded value tag, so a number never sits loose against a bar. */
const tag = (x, y, text, { fill = C.navy, colour = '#fff', size = 19, weight = 700, pad = 12 } = {}) => {
  const w = String(text).length * size * 0.56 + pad * 2;
  return `
    <g>
      <rect x="${(x - w / 2).toFixed(1)}" y="${(y - size - 8).toFixed(1)}" width="${w.toFixed(1)}" height="${size + 14}"
            rx="${(size + 14) / 2}" fill="${fill}"/>
      <text x="${x}" y="${(y + 1).toFixed(1)}" text-anchor="middle" font-size="${size}" font-weight="${weight}" fill="${colour}">${text}</text>
    </g>`;
};

/**
 * The two systems as stacked columns, with the difference called out between
 * them. An owner reads the callout first and the stack second, which is the
 * order the argument is made in.
 */
function costColumns(study, L, currency, isAr) {
  const p = nextDefs();
  const parts = [
    { key: 'concrete', label: L.concrete, fill: `url(#${p}gConcrete)`, flat: C.mid },
    { key: 'rebar', label: L.rebar, fill: `url(#${p}gRebar)`, flat: C.sky },
    { key: 'formwork', label: L.formwork, fill: `url(#${p}gForm)`, flat: C.pale },
    { key: 'post_tension', label: L.pt_package, fill: `url(#${p}gPT)`, flat: C.gold },
  ];
  const columns = [
    { name: isAr ? study.system.label_ar : study.system.label_en, side: study.conventional },
    { name: L.pt, side: study.post_tension },
  ];

  const W = 1000;
  const H = 470;
  const pad = { top: 84, bottom: 84, left: 92, right: 52 };
  const plotH = H - pad.top - pad.bottom;
  const max = Math.max(columns[0].side.per_sqm, columns[1].side.per_sqm, 1) * 1.02;
  const barW = 168;
  const centres = [pad.left + 150, W - pad.right - 190];
  const yOf = (value) => pad.top + plotH - (value / max) * plotH;

  let grid = '';
  for (let i = 0; i <= 4; i += 1) {
    const value = (max / 4) * i;
    const y = yOf(value);
    grid += `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${W - pad.right}" y2="${y.toFixed(1)}"
                   stroke="${i ? '#e8eef5' : C.line}" stroke-width="${i ? 1.5 : 2}"/>`;
    grid += `<text x="${pad.left - 16}" y="${(y + 7).toFixed(1)}" text-anchor="end" font-size="17" fill="${C.grey}">${money(value)}</text>`;
  }

  let bars = '';
  columns.forEach((column, index) => {
    const cx = centres[index];
    const x = cx - barW / 2;
    const top = yOf(column.side.per_sqm);
    const id = `${p}clip${index}`;
    let segments = '';
    let y = pad.top + plotH;
    for (const part of parts) {
      const value = Number(column.side[part.key]) || 0;
      if (value <= 0) continue;
      const h = (value / max) * plotH;
      y -= h;
      segments += `<rect x="${x}" y="${y.toFixed(1)}" width="${barW}" height="${(h + 0.6).toFixed(1)}" fill="${part.fill}"/>`;
      // Only label a band tall enough to hold the number.
      if (h > 42) {
        segments += `<text x="${cx}" y="${(y + h / 2 + 7).toFixed(1)}" text-anchor="middle" font-size="18"
                           font-weight="600" fill="#fff" opacity=".95">${money(value)}</text>`;
      }
    }
    bars += `
      <clipPath id="${id}"><rect x="${x}" y="${top.toFixed(1)}" width="${barW}"
              height="${(pad.top + plotH - top).toFixed(1)}" rx="10"/></clipPath>
      <g clip-path="url(#${id})" filter="url(#${p}soft)">${segments}</g>
      ${tag(cx, top - 22, `${money(column.side.per_sqm)}`, { fill: index ? C.gold : C.navy, colour: index ? C.navyDeep : '#fff', size: 24 })}
      <text x="${cx}" y="${(pad.top + plotH + 38).toFixed(1)}" text-anchor="middle" font-size="19"
            font-weight="700" fill="${C.ink}">${esc(column.name)}</text>`;
  });

  // The difference, drawn as a bracket between the two column heads.
  const yConv = yOf(columns[0].side.per_sqm);
  const yPt = yOf(columns[1].side.per_sqm);
  const gain = study.saving.slab_per_sqm;
  const midX = (centres[0] + centres[1]) / 2;
  const dropX = centres[1] + barW / 2;
  const bracket = Math.abs(yConv - yPt) > 14 ? `
    <line x1="${centres[0] + barW / 2}" y1="${yConv.toFixed(1)}" x2="${dropX.toFixed(1)}" y2="${yConv.toFixed(1)}"
          stroke="${gain >= 0 ? C.green : C.red}" stroke-width="2" stroke-dasharray="7 6" opacity=".75"/>
    <line x1="${dropX.toFixed(1)}" y1="${yConv.toFixed(1)}" x2="${dropX.toFixed(1)}" y2="${yPt.toFixed(1)}"
          stroke="${gain >= 0 ? C.green : C.red}" stroke-width="2.5"/>
    ${tag(midX, (yConv + yPt) / 2 - 4, `${gain >= 0 ? '−' : '+'}${money(Math.abs(gain), 2)} ${currency}`,
      { fill: gain >= 0 ? C.green : C.red, size: 20 })}` : '';

  const legend = parts.map((part) => `
    <span class="lg"><i style="background:${part.flat}"></i>${esc(part.label)}</span>`).join('');

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.compare_h)}">
    ${CHART_DEFS(p)}
    <text x="${pad.left - 16}" y="${(pad.top - 26).toFixed(1)}" text-anchor="end" font-size="15" fill="#93a0b0">${esc(currency)}</text>
    ${grid}${bars}${bracket}
  </svg>
  <div class="legend">${legend}</div>`;
}

/**
 * The saving as a waterfall: the conventional cost on the left, each saving
 * knocked off it in turn, and what is left on the right. It is the shape a
 * commercial reader already knows how to read.
 */
function waterfall(study, L, currency, isAr) {
  const p = nextDefs();
  const steps = [
    { label: L.slab_only, value: study.saving.slab_total },
    { label: L.foundation, value: study.saving.foundation_total },
    { label: L.programme, value: study.saving.programme_total },
  ].filter((step) => step.value !== 0);

  // Built from zero up to the net saving rather than down from the project
  // total: a 400,000 saving against a 7,700,000 project is a sliver on the
  // project's own scale, and a sliver persuades nobody of anything.
  const net = study.saving.total;

  const W = 1000;
  const H = 330;
  const pad = { top: 58, bottom: 74, left: 80, right: 36 };
  const plotH = H - pad.top - pad.bottom;
  const count = steps.length + 1;
  const slot = (W - pad.left - pad.right) / count;
  const barW = Math.min(slot * 0.5, 132);
  // The tallest thing on the chart is the total, or a running peak above it
  // when one of the components is negative.
  let peak = 0;
  let level = 0;
  for (const step of steps) { level += step.value; peak = Math.max(peak, level, 0); }
  const max = Math.max(peak, net, 1) * 1.14;
  const yOf = (value) => pad.top + plotH - (value / max) * plotH;
  const centre = (index) => pad.left + slot * index + slot / 2;

  const column = (index, from, to, fill, label, value, strong) => {
    const cx = centre(index);
    const top = yOf(Math.max(from, to));
    const height = Math.max(Math.abs(yOf(from) - yOf(to)), 3);
    return `
      <rect x="${(cx - barW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}"
            height="${height.toFixed(1)}" rx="6" fill="${fill}" filter="url(#${p}soft)"/>
      ${tag(cx, top - 14, value, { fill: strong ? C.navy : '#ffffff', colour: strong ? '#fff' : C.ink, size: 18 })}
      <text x="${cx}" y="${(pad.top + plotH + 34).toFixed(1)}" text-anchor="middle" font-size="16.5"
            fill="${C.ink}" font-weight="${strong ? 700 : 500}">${esc(label)}</text>`;
  };

  let running = 0;
  let body = '';
  let connectors = '';
  steps.forEach((step, index) => {
    const from = running;
    running += step.value;
    const positive = step.value > 0;
    body += column(index, from, running, positive ? `url(#${p}gGreen)` : `url(#${p}gRed)`, step.label,
      `${positive ? '+' : '−'}${money(Math.abs(step.value))}`, false);
    const y = yOf(running);
    connectors += `<line x1="${(centre(index) + barW / 2).toFixed(1)}" y1="${y.toFixed(1)}"
                         x2="${(centre(index + 1) - barW / 2).toFixed(1)}" y2="${y.toFixed(1)}"
                         stroke="${C.line}" stroke-width="2" stroke-dasharray="6 5"/>`;
  });
  body += column(steps.length, 0, net, `url(#${p}gPT)`, L.net_saving, money(net), true);

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.waterfall_h)}">
    ${CHART_DEFS(p)}
    <line x1="${pad.left - 10}" y1="${(pad.top + plotH).toFixed(1)}" x2="${W - pad.right}" y2="${(pad.top + plotH).toFixed(1)}"
          stroke="${C.line}" stroke-width="2"/>
    <text x="${pad.left - 10}" y="${(pad.top - 28).toFixed(1)}" font-size="15" fill="#93a0b0">${esc(currency)}</text>
    ${connectors}${body}
  </svg>
  <div class="totals-strip">
    <span>${esc(L.start_point)} <b>${money(study.conventional.total)} ${esc(currency)}</b></span>
    <i>${isAr ? '←' : '→'}</i>
    <span>${esc(L.end_point)} <b>${money(study.conventional.total - net)} ${esc(currency)}</b></span>
  </div>`;
}

/** The two programmes on one time axis, with the months marked. */
function timeline(study, L) {
  const p = nextDefs();
  const rows = [
    { label: L.conventional, days: study.benefits.conv_programme_days, fill: `url(#${p}gConv)` },
    { label: L.pt, days: study.benefits.pt_programme_days, fill: `url(#${p}gGreen)` },
  ];
  const W = 1000;
  const H = 300;
  const left = 210;
  const right = 70;
  const track = W - left - right;
  const max = Math.max(...rows.map((r) => r.days), 1);
  const xOf = (days) => left + (days / max) * track;

  // A tick a month, so a duration reads as time rather than as a number.
  let ticks = '';
  for (let day = 0; day <= max; day += 30) {
    const x = xOf(day);
    ticks += `<line x1="${x.toFixed(1)}" y1="54" x2="${x.toFixed(1)}" y2="214" stroke="#eaeff6" stroke-width="1.5"/>`;
    ticks += `<text x="${x.toFixed(1)}" y="42" text-anchor="middle" font-size="15" fill="#93a0b0">${day / 30}</text>`;
  }
  ticks += `<text x="${left - 14}" y="42" text-anchor="end" font-size="14.5" fill="#93a0b0">${esc(L.months)}</text>`;

  const bars = rows.map((row, index) => {
    const y = 76 + index * 74;
    const w = Math.max(xOf(row.days) - left, 4);
    return `
      <text x="${left - 18}" y="${y + 32}" text-anchor="end" font-size="19" font-weight="600" fill="${C.ink}">${esc(row.label)}</text>
      <rect x="${left}" y="${y}" width="${w.toFixed(1)}" height="46" rx="10" fill="${row.fill}" filter="url(#${p}soft)"/>
      <text x="${(left + w - 16).toFixed(1)}" y="${y + 30}" text-anchor="end" font-size="20" font-weight="700" fill="#fff">${money(row.days)}</text>`;
  }).join('');

  const saved = study.benefits.days_saved;
  const bracket = saved > 0 ? `
    <line x1="${xOf(rows[1].days).toFixed(1)}" y1="230" x2="${xOf(rows[0].days).toFixed(1)}" y2="230"
          stroke="${C.gold}" stroke-width="2.5"/>
    <line x1="${xOf(rows[1].days).toFixed(1)}" y1="222" x2="${xOf(rows[1].days).toFixed(1)}" y2="238" stroke="${C.gold}" stroke-width="2.5"/>
    <line x1="${xOf(rows[0].days).toFixed(1)}" y1="222" x2="${xOf(rows[0].days).toFixed(1)}" y2="238" stroke="${C.gold}" stroke-width="2.5"/>
    ${tag((xOf(rows[1].days) + xOf(rows[0].days)) / 2, 276, `${money(saved)} ${L.unit_day}`, { fill: C.gold, colour: C.navyDeep, size: 19 })}` : '';

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(L.timeline_h)}">
    ${CHART_DEFS(p)}${ticks}${bars}${bracket}
  </svg>`;
}

/** One quantity, both systems, as a pair of bars with the saving spelled out. */
function quantityPair(heading, unit, convLabel, convValue, ptLabel, ptValue) {
  const p = nextDefs();
  const W = 480;
  const H = 188;
  const left = 8;
  const track = W - 150;
  const max = Math.max(convValue, ptValue, 1);
  const bar = (y, label, value, fill, colour) => {
    const w = Math.max((value / max) * track, 6);
    return `
      <text x="${left}" y="${y - 10}" font-size="16" fill="${C.grey}">${esc(label)}</text>
      <rect x="${left}" y="${y}" width="${w.toFixed(1)}" height="34" rx="7" fill="${fill}"/>
      <text x="${(left + w + 12).toFixed(1)}" y="${y + 24}" font-size="19" font-weight="700" fill="${colour}">${money(value, value < 100 ? 1 : 0)} <tspan font-size="14" fill="${C.grey}">${esc(unit)}</tspan></text>`;
  };
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" direction="ltr" role="img" aria-label="${esc(heading)}">
    ${CHART_DEFS(p)}
    <text x="${left}" y="18" font-size="18" font-weight="700" fill="${C.navy}">${esc(heading)}</text>
    ${bar(46, convLabel, convValue, `url(#${p}gConv)`, C.ink)}
    ${bar(130, ptLabel, ptValue, `url(#${p}gGreen)`, C.green)}
  </svg>`;
}

// ----------------------------------------------------------------- document
export function printStudy(data, lang = 'ar') {
  const html = buildStudyDeck(data, lang);
  const win = window.open('', '_blank');
  if (!win) {
    alert(lang === 'ar'
      ? 'الرجاء السماح بالنوافذ المنبثقة لفتح الدراسة.'
      : 'Please allow pop-ups to open the study.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
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
  const logo = esc(branch.logo || '/assets/img/logo@2x.png');

  const cash = (value) => `${money(value)} ${currency}`;
  const plain2 = (value) => money(value, 2);

  // ------------------------------------------------------- edited wording
  // Anything marked editable is rendered through `txt`, which prefers what the
  // engineer last wrote on the deck over what the system generated. The
  // generated wording is kept alongside so "back to the original" can restore
  // it in place rather than reopening the document.
  const edits = (study.input && study.input.deck) || {};
  const overrides = edits.text || {};
  const hidden = edits.hidden || {};
  const generated = {};

  // Saving the edits needs an absolute URL: this document is opened blank and
  // written into, so it has no base of its own to resolve a relative one.
  const apiBase = String(data.origin || '').replace(/\/+$/, '');
  const canSave = Boolean(apiBase && data.quotation_id);
  const apiUrl = canSave ? `${apiBase}/api/quotations/${Number(data.quotation_id)}/study/deck` : '';
  /** JSON for a script block: a closing tag inside a string would end it. */
  const json = (value) => JSON.stringify(value).replace(/</g, '\\u003c');

  const mark = (key) => `data-e="${key}"`;
  const txt = (key, value) => {
    const source = value == null ? '' : String(value);
    generated[key] = source;
    return esc(overrides[key] == null ? source : overrides[key]);
  };
  // Prose keeps the line breaks a person typed into it.
  const prose = (key, value) => txt(key, value).replace(/\n/g, '<br>');

  // ------------------------------------------------------------- fragments
  const spec = (label, value) => `
    <div class="spec-row"><span class="k">${esc(label)}</span><span class="v">${value}</span></div>`;

  const compareRow = (label, conv, pt) => `
    <tr>
      <td>${esc(label)}</td>
      <td class="n">${plain2(conv)}</td>
      <td class="n">${plain2(pt)}</td>
      <td class="n ${conv - pt >= 0 ? 'good' : 'bad'}">${plain2(conv - pt)}</td>
    </tr>`;

  const statTile = (name, label, value, unit = '') => `
    <div class="tile">
      <div class="tile-ico">${icon(name, 24)}</div>
      <div>
        <div class="tile-v">${value}${unit ? ` <span class="u">${esc(unit)}</span>` : ''}</div>
        <div class="tile-k">${esc(label)}</div>
      </div>
    </div>`;

  const advCard = (index, name, heading, body) => `
    <div class="card adv">
      <span class="card-n">${String(index).padStart(2, '0')}</span>
      <div class="card-ico">${icon(name, 26)}</div>
      <div class="card-h" ${mark(`adv.${index}.h`)}>${txt(`adv.${index}.h`, heading)}</div>
      <p ${mark(`adv.${index}.p`)}>${txt(`adv.${index}.p`, body)}</p>
    </div>`;

  const drawings = (kind) => (data.drawings || []).filter((d) => d.kind === kind);
  const drawingColumn = (kind, heading, tone) => {
    const list = drawings(kind);
    return `
      <div class="draw-col">
        <div class="draw-h ${tone}" ${mark(`draw.${kind}`)}>${txt(`draw.${kind}`, heading)}</div>
        ${list.length ? list.map((d) => `
          <figure>
            <img src="${esc(d.url)}" alt="${esc((isAr ? d.caption_ar : d.caption_en) || heading)}">
            ${(isAr ? d.caption_ar : d.caption_en)
              ? `<figcaption>${esc(isAr ? d.caption_ar : d.caption_en)}</figcaption>` : ''}
          </figure>`).join('') : '<div class="draw-empty"></div>'}
      </div>`;
  };
  const hasDrawings = drawings('original').length || drawings('post_tension').length;

  // Tendon parabolas: the company's own product, used as the cover motif.
  // The company's own product as the cover motif: a family of tendon
  // parabolas, kept in the lower band so nothing is drawn through the title.
  const tendons = `
    <svg class="motif" viewBox="0 0 1000 560" preserveAspectRatio="none" aria-hidden="true">
      ${[0, 1, 2, 3].map((i) => `
        <path d="M0 ${372 + i * 58} Q 500 ${512 + i * 58} 1000 ${372 + i * 58}"
              fill="none" stroke="#ffffff" stroke-opacity="${0.14 - i * 0.03}" stroke-width="${2.2 - i * 0.3}"/>`).join('')}
      <path d="M0 400 Q 500 548 1000 400" fill="none" stroke="${C.gold}" stroke-opacity=".5" stroke-width="3"/>
      <circle cx="500" cy="474" r="6" fill="${C.gold}" fill-opacity=".75"/>
    </svg>`;

  // ------------------------------------------------------------ the slides
  const slides = [];
  const slide = (title, body, options = {}) => slides.push({ title, body, ...options });

  // 1 — cover
  slide('', `
    ${tendons}
    <div class="cover-in">
      <div class="cover-plate"><img src="${logo}" alt=""></div>
      <div class="cover-rule"></div>
      <h1 ${mark('cover.title')}>${txt('cover.title', L.doc_title)}</h1>
      <div class="cover-sub" ${mark('cover.sub')}>${txt('cover.sub', L.doc_sub)}</div>
    </div>
    <div class="cover-strip">
      ${projectName ? `<div class="cm"><span>${esc(L.project)}</span><b ${mark('cover.project')}>${txt('cover.project', projectName)}</b></div>` : ''}
      ${customerName ? `<div class="cm"><span>${esc(L.prepared_for)}</span><b ${mark('cover.customer')}>${txt('cover.customer', customerName)}</b></div>` : ''}
      ${location ? `<div class="cm"><span>${esc(L.location)}</span><b ${mark('cover.location')}>${txt('cover.location', location)}</b></div>` : ''}
      <div class="cm"><span>${esc(L.prepared_by)}</span><b ${mark('cover.by')}>${txt('cover.by', branchName)}</b></div>
      <div class="cm"><span>${esc(L.ref)}</span><b><bdi>${esc(q.number || '—')}</bdi></b></div>
      <div class="cm"><span>${esc(L.date)}</span><b><bdi>${esc(data.generated_at || '')}</bdi></b></div>
    </div>`, { key: 'cover', className: 'cover', bare: true });

  // 2 — who is asking to be believed
  slide(L.profile_h, `
    <div class="cards four plain">
      ${profile.map((line, index) => `
        <div class="card">
          <div class="card-ico">${icon(['shield', 'layers', 'span', 'weight'][index % 4], 26)}</div>
          <p ${mark(`company.p${index + 1}`)}>${txt(`company.p${index + 1}`, line)}</p>
        </div>`).join('')}
    </div>
    <div class="band">
      <div class="band-col"><span>${esc(L.vision)}</span><span ${mark('company.vision')}>${txt('company.vision', isAr ? company.vision_ar : company.vision_en)}</span></div>
      <div class="band-col"><span>${esc(L.mission)}</span><span ${mark('company.mission')}>${txt('company.mission', isAr ? company.mission_ar : company.mission_en)}</span></div>
    </div>`, { key: 'company', kicker: L.profile_sub, section: L.sec_company });

  // 3 — the ground rules, then the quantities they produce
  slide(L.basis_h, `
    <div class="cols g6-6">
      <div class="panel">
        <div class="panel-h">${esc(L.basis_h)}</div>
        ${spec(L.basis_system, esc(systemName))}
        ${spec(L.basis_area, `${money(study.area_sqm)} m²`)}
        ${spec(L.basis_floors, money(study.floors))}
        ${spec(L.basis_total_area, `<b>${money(study.total_area_sqm)} m²</b>`)}
        <div class="panel-h mt">${esc(L.rates_h)}</div>
        ${spec(L.rate_concrete, cash(s.concrete_rate_m3))}
        ${spec(L.rate_rebar, cash(s.rebar_rate_ton))}
        ${spec(L.rate_formwork, cash(s.formwork_rate_sqm))}
        ${spec(L.rate_pt, cash(s.pt_rate_sqm))}
      </div>
      <div class="panel">
        <div class="panel-h">${esc(L.quantities_h)}</div>
        <div class="chart tight">${quantityPair(L.qty_concrete_h, L.unit_m3, systemName,
          study.conventional.concrete_m3, L.pt, study.post_tension.concrete_m3)}</div>
        <div class="chart tight">${quantityPair(L.qty_rebar_h, L.unit_t, systemName,
          study.conventional.rebar_ton, L.pt, study.post_tension.rebar_ton)}</div>
        ${!study.complete ? `<div class="note"><b>${esc(L.incomplete_h)}</b> ${esc(L.incomplete)}</div>` : ''}
      </div>
    </div>`, { key: 'basis', kicker: L.basis_sub, section: L.sec_basis });

  // 4 — the comparison, chart first
  slide(L.compare_h, `
    <div class="cols g7-5">
      <div class="chart">${costColumns(study, L, currency, isAr)}</div>
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
    </div>`, { key: 'cost', kicker: L.compare_sub, section: L.sec_cost });

  // 5 — the number the meeting is about
  slide(L.saving_h, `
    <div class="kpi-band">
      <div class="kpi hero ${study.saving.total >= 0 ? '' : 'neg'}">
        <div class="k">${esc(L.net_saving)}</div>
        <div class="v">${cash(study.saving.total)}</div>
      </div>
      <div class="kpi">
        <div class="v">${money(study.saving.pct, 1)}%</div>
        <div class="k">${esc(L.of_conventional)}</div>
      </div>
      <div class="kpi">
        <div class="v">${money(study.benefits.days_saved)} <span class="u">${esc(L.unit_day)}</span></div>
        <div class="k">${esc(L.b_days)}</div>
      </div>
    </div>
    <div class="chart grow">${waterfall(study, L, currency, isAr)}</div>
    ${!study.saving.favours_pt_on_slab_alone ? `
    <div class="note"><b>${esc(L.slab_negative_h)}</b> <span ${mark('saving.note')}>${txt('saving.note', L.slab_negative)}</span></div>` : ''}`,
  { key: 'saving', kicker: L.saving_sub, section: L.sec_saving });

  // 6 — time and weight
  slide(L.programme_h, `
    <div class="panel">
      <div class="panel-h">${esc(L.timeline_h)}</div>
      <div class="chart tight">${timeline(study, L)}</div>
    </div>
    <div class="tiles five">
      ${statTile('calendar', L.b_days, money(study.benefits.days_saved), L.unit_day)}
      ${statTile('weight', L.b_weight, money(study.benefits.weight_saved_ton), L.unit_t)}
      ${statTile('cube', L.b_concrete, money(study.benefits.concrete_saved_m3), L.unit_m3)}
      ${statTile('steel', L.b_rebar, money(study.benefits.rebar_saved_ton, 1), L.unit_t)}
      ${statTile('ruler', L.b_height, money(study.benefits.height_saved_mm), L.unit_mm)}
    </div>`, { key: 'time', kicker: L.programme_sub, section: L.sec_time });

  // 7 — the case that is not about money
  slide(L.adv_h, `
    <div class="cards four">
      ${advCard(1, 'span', L.adv1_h, L.adv1)}
      ${advCard(2, 'weight', L.adv2_h, L.adv2)}
      ${advCard(3, 'clock', L.adv3_h, L.adv3)}
      ${advCard(4, 'shield', L.adv4_h, L.adv4)}
    </div>`, { key: 'adv', kicker: L.adv_sub, section: L.sec_adv });

  // 8 — the engineer's own drawings
  if (hasDrawings) {
    slide(L.drawings_h, `
      <div class="draws">
        ${drawingColumn('original', L.drawings_original, 'grey')}
        ${drawingColumn('post_tension', L.drawings_pt, 'gold')}
      </div>`, { key: 'drawings', kicker: L.drawings_sub, section: L.sec_drawings });
  }

  // 9 — what the study does not claim
  slide(L.assumptions_h, `
    <div class="cols mid ${notes ? 'g6-6' : 'g12'}">
      <div class="panel"><div class="panel-h">${esc(L.assumptions_h)}</div><div class="prose" ${mark('limits.body')}>${prose('limits.body', L.assumptions)}</div></div>
      ${notes ? `<div class="panel"><div class="panel-h">${esc(L.notes_h)}</div><div class="prose" ${mark('limits.notes')}>${prose('limits.notes', notes)}</div></div>` : ''}
    </div>`, { key: 'limits', section: L.sec_limits });

  // 10 — close
  slide('', `
    ${tendons}
    <div class="cover-in close">
      <div class="cover-plate"><img src="${logo}" alt=""></div>
      <div class="cover-rule"></div>
      <h1 ${mark('close.title')}>${txt('close.title', L.closing_h)}</h1>
      <div class="cover-sub" ${mark('close.sub')}>${txt('close.sub', L.closing_sub)}</div>
    </div>
    <div class="cover-strip contact">
        <div class="ct">${icon('layers', 20, C.goldLight)}<span>${esc(branchName)}</span></div>
        ${(isAr ? branch.address_ar : branch.address_en)
          ? `<div class="ct">${icon('pin', 20, C.goldLight)}<span>${esc(isAr ? branch.address_ar : branch.address_en)}</span></div>` : ''}
        ${branch.phone ? `<div class="ct">${icon('phone', 20, C.goldLight)}<span><bdi>${esc(branch.phone)}</bdi></span></div>` : ''}
        ${branch.email ? `<div class="ct">${icon('mail', 20, C.goldLight)}<span><bdi>${esc(branch.email)}</bdi></span></div>` : ''}
      ${branch.website ? `<div class="ct">${icon('globe', 20, C.goldLight)}<span><bdi>${esc(branch.website)}</bdi></span></div>` : ''}
    </div>`, { key: 'close', className: 'cover', bare: true });

  // --------------------------------------------------------------- markup
  // Numbering happens inside the document, not here: hiding a slide has to
  // renumber every slide after it.
  const deck = slides.map((item) => `
  <section class="slide ${item.className || ''} ${hidden[item.key] ? 'is-off' : ''}" data-slide="${item.key}">
    ${item.key === 'cover' ? '' : `
    <button type="button" class="ui slide-toggle" data-toggle="${item.key}"></button>`}
    ${item.bare ? '' : `
    <header class="s-head">
      <div class="s-title">
        <h2 ${mark(`${item.key}.title`)}>${txt(`${item.key}.title`, item.title)}</h2>
        ${item.kicker ? `<div class="kick" ${mark(`${item.key}.kick`)}>${txt(`${item.key}.kick`, item.kicker)}</div>` : ''}
      </div>
      <div class="s-mark">
        ${item.section ? `<span class="chip">${esc(item.section)}</span>` : ''}
        <img src="${logo}" alt="">
      </div>
    </header>
    <div class="s-rule"><i></i></div>`}
    <div class="s-body">${item.body}</div>
    ${item.bare ? '' : `
    <footer class="s-foot">
      <span class="who">${esc(projectName || branchName)}</span>
      <span class="bar"><i></i></span>
      <span class="pg"></span>
    </footer>`}
  </section>`).join('');

  return `<!doctype html>
<html lang="${lang}" dir="${dir}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(L.doc_title)} — ${esc(projectName)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800;900&family=Inter:wght@400;500;600;700;800;900&display=swap">
<style>
  /* Widescreen, because this is shown on a screen before it is filed as a
     PDF. A printer that cannot do this size scales it to fit the paper. */
  @page { size: ${SLIDE.w}mm ${SLIDE.h}mm; margin: 0; }

  :root {
    --navy:${C.navy}; --navy-deep:${C.navyDeep}; --mid:${C.mid}; --gold:${C.gold};
    --gold-l:${C.goldLight}; --ice:${C.ice}; --line:${C.line}; --grey:${C.grey}; --ink:${C.ink};
    --k: 1;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; }
  body {
    background: #dfe5ec; color: var(--ink);
    font-family: ${isAr ? "'Cairo','Tajawal',Tahoma,sans-serif" : "'Inter','Segoe UI',Arial,sans-serif"};
    font-size: 11pt; line-height: 1.55;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }

  .slide {
    position: relative; width: ${SLIDE.w}mm; height: ${SLIDE.h}mm;
    margin: 0 auto 7mm; padding: 11mm 15mm 8mm; background: #fff; overflow: hidden;
    display: flex; flex-direction: column;
    box-shadow: 0 6px 26px rgba(10,38,71,.22);
    break-after: page; page-break-after: always;
  }
  .slide:last-child { break-after: auto; page-break-after: auto; margin-bottom: 0; }
  .slide::before {
    content: ''; position: absolute; inset-block: 0; inset-inline-start: 0; width: 3.6mm;
    background: linear-gradient(180deg, var(--navy) 0%, var(--navy) 62%, var(--gold) 62%, var(--gold) 100%);
  }

  @media print {
    body { background: #fff; }
    .slide { margin: 0; box-shadow: none; }
    .ui { display: none !important; }
  }

  /* ------------------------------------------------------------ slide frame */
  .s-head { display: flex; align-items: flex-start; gap: 10mm; }
  .s-title h2 { margin: 0; font-size: 27pt; font-weight: 800; color: var(--navy); line-height: 1.15; letter-spacing: -.01em; }
  .s-title .kick { margin-top: 1.5mm; font-size: 11.5pt; color: var(--grey); }
  .s-mark { margin-inline-start: auto; display: flex; align-items: center; gap: 5mm; flex-shrink: 0; }
  .s-mark img { max-height: 13mm; max-width: 40mm; }
  .chip { padding: 1.2mm 4mm; border-radius: 6mm; background: var(--ice); color: var(--navy); font-size: 9.5pt; font-weight: 700; }
  .s-rule { position: relative; height: 1.6mm; margin: 4mm 0 0; background: var(--ice); border-radius: 1mm; }
  .s-rule i { position: absolute; inset-block: 0; inset-inline-start: 0; width: 34mm; background: var(--gold); border-radius: 1mm; }
  .s-body { flex: 1; min-height: 0; padding-top: 6mm; display: flex; flex-direction: column; justify-content: center; gap: 5mm; }
  .s-foot { display: flex; align-items: center; gap: 6mm; padding-top: 3.5mm; font-size: 9pt; color: var(--grey); }
  .s-foot .who { flex: 1; }
  .s-foot .bar { width: 44mm; height: 1.2mm; background: var(--ice); border-radius: 1mm; overflow: hidden; }
  .s-foot .bar i { display: block; height: 100%; background: var(--gold); }
  .s-foot .pg { direction: ltr; unicode-bidi: isolate; font-weight: 800; color: var(--navy); font-size: 10pt; }

  /* ------------------------------------------------------------------ cover */
  .slide.cover {
    padding: 0; justify-content: center; color: #fff;
    background: radial-gradient(120% 120% at ${isAr ? '85%' : '15%'} 0%, #14406e 0%, var(--navy) 45%, var(--navy-deep) 100%);
  }
  .slide.cover::before { background: var(--gold); width: 2.4mm; }
  .motif { position: absolute; inset: 0; width: 100%; height: 100%; }
  .cover-in { position: relative; z-index: 1; padding: 0 24mm; }
  .cover-plate { display: inline-block; padding: 4mm 6mm; background: #fff; border-radius: 2.5mm; box-shadow: 0 4px 18px rgba(0,0,0,.25); }
  .cover-plate img { display: block; max-height: 17mm; max-width: 54mm; }
  .cover-rule { width: 32mm; height: 1.8mm; margin: 7mm 0 5mm; background: var(--gold); border-radius: 1mm; }
  .slide.cover h1 { margin: 0; font-size: 40pt; font-weight: 900; line-height: 1.1; letter-spacing: -.015em; }
  .cover-sub { margin-top: 3mm; font-size: 14pt; color: #b7cbe4; max-width: 200mm; }
  /* The particulars sit in a strip along the foot of the slide, so the title
     block keeps the middle of the frame to itself. */
  .cover-strip {
    position: absolute; z-index: 1; inset-inline: 0; bottom: 0;
    display: flex; flex-wrap: wrap; gap: 4mm 11mm;
    padding: 6mm 24mm; background: rgba(4,16,32,.45); border-top: 1px solid rgba(201,162,39,.35);
  }
  .cover-strip .cm span { display: block; font-size: 9pt; font-weight: 700; color: var(--gold); margin-bottom: .4mm; }
  .cover-strip .cm b { font-size: 11pt; font-weight: 600; color: #e7eef7; }
  .cover-in.close h1 { font-size: 34pt; }
  .cover-strip.contact { align-items: center; }
  .ct { display: inline-flex; align-items: center; gap: 2.5mm; font-size: 11pt; color: #dbe6f3; }

  /* --------------------------------------------------------------- content */
  .cols { display: grid; gap: 7mm; align-items: stretch; flex: 1; min-height: 0; }
  .cols.g6-6 { grid-template-columns: 1fr 1fr; }
  .cols.g7-5 { grid-template-columns: 1.25fr 1fr; align-items: center; }
  .cols.g12 { grid-template-columns: 1fr; }
  .cols.mid { align-items: center; }

  .panel { padding: 6mm 7mm; background: var(--ice); border-radius: 2.5mm; display: flex; flex-direction: column; justify-content: center; }
  .panel-h { font-size: 12.5pt; font-weight: 800; color: var(--navy); margin-bottom: 3mm; }
  .panel-h.mt { margin-top: 6mm; }
  .prose { font-size: 11.5pt; line-height: 1.8; text-align: justify; }

  .spec-row { display: flex; align-items: baseline; gap: 4mm; padding: 2.2mm 0; border-bottom: 1px solid #dfe8f2; font-size: 11.5pt; }
  .spec-row:last-child { border-bottom: 0; }
  .spec-row .k { color: var(--grey); }
  .spec-row .v { margin-inline-start: auto; font-weight: 700; color: var(--navy); direction: ltr; unicode-bidi: plaintext; }

  table { width: 100%; border-collapse: collapse; font-size: 11pt; }
  th, td { padding: 2.3mm 3.5mm; border-bottom: 1px solid var(--line); text-align: ${isAr ? 'right' : 'left'}; }
  thead th { background: var(--navy); color: #fff; font-weight: 700; font-size: 10pt; border-bottom: 0; }
  thead th:first-child { border-start-start-radius: 2mm; }
  thead th:last-child { border-start-end-radius: 2mm; }
  td.n, th.n { text-align: ${isAr ? 'left' : 'right'}; direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }
  tbody tr:nth-child(even) td { background: #f8fafd; }
  tr.total td { background: var(--ice); font-weight: 800; color: var(--navy); font-size: 11.5pt; }
  td.good { color: ${C.green}; font-weight: 700; }
  td.bad { color: ${C.red}; font-weight: 700; }
  th .cur { display: block; font-size: 8.5pt; font-weight: 500; opacity: .72; }
  table.cmp td:first-child, table.cmp th:first-child { width: 31%; }

  .chart { display: flex; flex-direction: column; justify-content: center; }
  .chart.grow { flex: 1; min-height: 0; }
  .chart.tight { margin: 1mm 0; }
  .chart svg { display: block; width: 100%; height: auto; }
  .legend { display: flex; flex-wrap: wrap; justify-content: center; gap: 2mm 7mm; margin-top: 2mm; font-size: 10pt; color: var(--grey); }
  .legend .lg { display: inline-flex; align-items: center; gap: 2mm; }
  .legend i { width: 3.4mm; height: 3.4mm; border-radius: .8mm; }

  .cards { display: grid; gap: 5mm; }
  .cards.four { grid-template-columns: repeat(4, 1fr); }
  .cards.plain .card { min-height: 54mm; }
  .card { position: relative; padding: 6mm; background: var(--ice); border-radius: 2.5mm; border-top: 2.5mm solid var(--navy); display: flex; flex-direction: column; gap: 3mm; overflow: hidden; }
  .card.adv { min-height: 78mm; }
  .card-n { position: absolute; inset-block-start: 1mm; inset-inline-end: 4mm; font-size: 32pt; font-weight: 900; color: #cfdaea; line-height: 1; }
  .card-ico { width: 11mm; height: 11mm; border-radius: 50%; background: #fff; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(10,38,71,.12); }
  .card-h { font-size: 13pt; font-weight: 800; color: var(--navy); }
  .card p { margin: 0; font-size: 10.8pt; line-height: 1.65; color: #33445a; }

  .band { display: grid; grid-template-columns: 1fr 1fr; gap: 5mm; }
  .band-col { padding: 5mm 6mm; background: var(--navy); color: #eaf1fa; border-radius: 2.5mm; font-size: 11pt; }
  .band-col span { display: block; color: var(--gold); font-weight: 800; font-size: 10.5pt; margin-bottom: 1mm; }

  .kpi-band { display: grid; grid-template-columns: 1.7fr 1fr 1fr; gap: 5mm; }
  .kpi { padding: 5mm 6mm; background: var(--ice); border-radius: 2.5mm; display: flex; flex-direction: column; justify-content: center; }
  .kpi .v { font-size: 22pt; font-weight: 800; color: var(--navy); direction: ltr; unicode-bidi: plaintext; line-height: 1.15; }
  .kpi .v .u { font-size: 12pt; color: var(--grey); }
  .kpi .k { font-size: 10.5pt; color: var(--grey); }
  .kpi.hero { background: linear-gradient(135deg, var(--navy) 0%, #14406e 100%); color: #fff; }
  .kpi.hero .k { color: var(--gold); font-weight: 800; font-size: 11pt; order: -1; margin-bottom: 1mm; }
  .kpi.hero .v { color: #fff; font-size: 30pt; }
  .kpi.hero.neg { background: linear-gradient(135deg, #6f1a1a 0%, #a32020 100%); }

  .tiles { display: grid; gap: 4mm; }
  .tiles.five { grid-template-columns: repeat(5, 1fr); }
  .tile { display: flex; align-items: center; gap: 3mm; padding: 3.5mm 4mm; min-height: 18mm; background: var(--ice); border-radius: 2.5mm; }
  .tile-ico { width: 10mm; height: 10mm; border-radius: 50%; background: var(--navy); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .tile-v { font-size: 15pt; font-weight: 800; color: var(--navy); direction: ltr; unicode-bidi: plaintext; line-height: 1.2; }
  .tile-v .u { font-size: 10pt; color: var(--grey); font-weight: 600; }
  .tile-k { font-size: 9.2pt; color: var(--grey); line-height: 1.25; }

  .totals-strip { display: flex; align-items: center; justify-content: center; gap: 5mm; margin-top: 3mm; font-size: 10.5pt; color: var(--grey); }
  .totals-strip b { color: var(--navy); font-weight: 800; direction: ltr; unicode-bidi: plaintext; }
  .totals-strip i { color: var(--gold); font-style: normal; font-weight: 800; }

  .note { padding: 3.5mm 5mm; background: #fdf6e9; border-inline-start: 1.4mm solid var(--gold); border-radius: 0 2mm 2mm 0; font-size: 10.5pt; }
  .note b { color: #8a5a10; }

  .draws { display: grid; grid-template-columns: 1fr 1fr; gap: 7mm; flex: 1; min-height: 0; }
  .draw-col { display: flex; flex-direction: column; min-height: 0; }
  .draw-h { margin-bottom: 3mm; padding: 2mm 4mm; border-radius: 1.5mm; font-size: 12pt; font-weight: 800; text-align: center; }
  .draw-h.grey { background: var(--ice); color: var(--navy); }
  .draw-h.gold { background: var(--gold); color: var(--navy-deep); }
  figure { margin: 0; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  figure img { width: 100%; flex: 1; min-height: 0; object-fit: contain; border: 1px solid var(--line); border-radius: 1.5mm; background: #fff; }
  figcaption { margin-top: 2mm; font-size: 9.5pt; color: var(--grey); text-align: center; }
  .draw-empty { flex: 1; border: 1px dashed var(--line); border-radius: 1.5mm; }

  /* ------------------------------------------------------- presenting live */
  .ui { font-family: inherit; }
  .bar-top { position: sticky; top: 0; z-index: 40; display: flex; gap: .5rem; justify-content: center;
             padding: 10px; background: var(--navy); }
  .bar-top button, .hud button {
    padding: 7px 18px; border: 0; border-radius: 6px; background: #fff; color: var(--navy);
    font-family: inherit; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .bar-top button.gold { background: var(--gold); color: var(--navy-deep); }
  .bar-top button.ghost { background: transparent; color: #fff; box-shadow: inset 0 0 0 1px rgba(255,255,255,.45); }
  .bar-top .grp { display: flex; align-items: center; gap: .5rem; }
  .bar-top .hint { color: #b9cbe4; font-size: 12.5px; }
  .bar-top .flash { color: var(--gold-l); font-size: 12.5px; font-weight: 700; }
  .bar-edit { display: none; }
  body.editing .bar-edit { display: flex; }
  body.editing .bar-view { display: none; }

  /* ---------------------------------------------------------- editing text */
  body.editing [data-e] {
    outline: 1px dashed #a9bfd8; outline-offset: 3px; border-radius: 1mm; cursor: text;
  }
  body.editing [data-e]:hover { background: rgba(201,162,39,.12); }
  body.editing [data-e]:focus { outline: 2px solid var(--gold); background: rgba(201,162,39,.10); }
  body.editing .slide.cover [data-e] { outline-color: rgba(255,255,255,.45); }

  .slide-toggle {
    display: none; position: absolute; z-index: 6; top: 4mm; inset-inline-start: 7mm;
    padding: 1.5mm 4mm; border: 0; border-radius: 6mm; background: var(--navy); color: #fff;
    font-family: inherit; font-size: 11px; font-weight: 700; cursor: pointer;
  }
  body.editing .slide-toggle { display: block; }
  /* A dropped slide stays in the document while editing, so it can be brought
     back; everywhere else it simply is not there. */
  .slide.is-off { display: none; }
  body.editing .slide.is-off { display: flex; opacity: .4; filter: grayscale(1); }
  body.editing .slide.is-off .slide-toggle { background: var(--gold); color: var(--navy-deep); }

  /* On a projector the slide is scaled to the screen rather than reflowed, so
     what the room sees is exactly what prints. */
  body.present { background: #05101f; overflow: hidden; }
  body.present .bar-top { display: none; }
  /* Centred by auto margins rather than a translate: in a right-to-left
     document a logical offset and a physical translate pull opposite ways and
     the slide ends up off the screen. */
  /* Hidden with visibility rather than display: a slide that was display:none
     when the browser first resolved its SVG gradients comes back without them,
     and the charts show their labels over empty space. */
  body.present .slide {
    visibility: hidden; position: fixed; inset: 0; margin: auto;
    transform: scale(var(--k)); transform-origin: center;
    box-shadow: 0 16px 70px rgba(0,0,0,.65);
  }
  body.present .slide.on { visibility: visible; }
  .hud { display: none; position: fixed; z-index: 60; bottom: 16px; inset-inline-start: 50%;
         transform: translateX(${isAr ? '50%' : '-50%'}); align-items: center; gap: 10px;
         padding: 7px 12px; border-radius: 30px; background: rgba(8,22,40,.82); color: #cfe0f2;
         font-size: 12.5px; backdrop-filter: blur(6px); }
  body.present .hud { display: flex; }
  .hud .n { direction: ltr; unicode-bidi: isolate; font-weight: 800; color: #fff; }
  .hud .hint { opacity: .7; }
  .hud button { padding: 4px 12px; font-size: 12px; }

  @media print {
    .slide.is-off { display: none !important; }
    body.present { overflow: visible; background: #fff; }
    body.present .slide { visibility: visible !important; position: static !important; transform: none !important; margin: 0 !important; box-shadow: none; }
    .hud { display: none !important; }
  }
</style>
</head>
<body>

<div class="ui bar-top">
  <span class="grp bar-view">
    ${canSave ? `<button type="button" id="btn-edit">${esc(L.edit_btn)}</button>` : ''}
    <button type="button" class="gold" id="btn-present">${esc(L.present)}</button>
    <button type="button" id="btn-print">${esc(L.print_btn)}</button>
    <button type="button" class="ghost" id="btn-close">${esc(L.close_btn)}</button>
  </span>
  <span class="grp bar-edit">
    <button type="button" class="gold" id="btn-save">${esc(L.edit_save)}</button>
    <button type="button" class="ghost" id="btn-reset">${esc(L.edit_reset)}</button>
    <button type="button" class="ghost" id="btn-done">${esc(L.edit_done)}</button>
    <span class="hint">${esc(L.edit_hint)}</span>
    <span class="flash" id="flash"></span>
  </span>
</div>
${deck}
<div class="ui hud" id="hud">
  <button type="button" id="btn-prev">‹</button>
  <span class="n" id="hud-n">1</span>
  <button type="button" id="btn-next">›</button>
  <span class="hint">${esc(L.hint_keys)}</span>
  <button type="button" id="btn-exit">${esc(L.close_btn)}</button>
</div>

<script>
window.SPAN = {
  api: ${json(apiUrl)},
  generated: ${json(generated)},
  hidden: ${json(hidden)},
  words: {
    hide: ${json(L.edit_hide)}, show: ${json(L.edit_show)},
    saved: ${json(L.edit_saved)}, failed: ${json(L.edit_failed)},
    unsaved: ${json(L.edit_unsaved)}, resetAsk: ${json(L.edit_reset_ask)}
  }
};
</script>
<script>
(function () {
  var API = SPAN.api;
  var GENERATED = SPAN.generated;
  var WORDS = SPAN.words;
  var hiddenState = SPAN.hidden || {};

  var all = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var fields = Array.prototype.slice.call(document.querySelectorAll('[data-e]'));
  var counter = document.getElementById('hud-n');
  var flash = document.getElementById('flash');
  var index = 0;
  var live = false;
  var editing = false;
  var dirty = false;

  /** The slides that are actually in the deck right now. */
  function shown() {
    return all.filter(function (slide) { return !slide.classList.contains('is-off'); });
  }

  /** Page numbers and the progress bar, recomputed whenever the deck changes. */
  function renumber() {
    var list = shown();
    list.forEach(function (slide, i) {
      var page = slide.querySelector('.pg');
      var bar = slide.querySelector('.s-foot .bar i');
      var pad = function (n) { return (n < 10 ? '0' : '') + n; };
      if (page) page.textContent = pad(i + 1) + ' / ' + pad(list.length);
      if (bar) bar.style.width = (((i + 1) / list.length) * 100).toFixed(1) + '%';
    });
    all.forEach(function (slide) {
      var button = slide.querySelector('.slide-toggle');
      if (!button) return;
      button.textContent = slide.classList.contains('is-off') ? WORDS.show : WORDS.hide;
    });
  }

  function say(message) {
    if (!flash) return;
    flash.textContent = message;
    setTimeout(function () { if (flash.textContent === message) flash.textContent = ''; }, 3000);
  }

  // ------------------------------------------------------------- presenting
  function fit() {
    var slide = shown()[index];
    if (!slide) return;
    var k = Math.min(window.innerWidth / slide.offsetWidth, window.innerHeight / slide.offsetHeight);
    document.documentElement.style.setProperty('--k', k);
  }

  function show(next) {
    var list = shown();
    if (!list.length) return;
    if (next < 0) next = 0;
    if (next > list.length - 1) next = list.length - 1;
    list.forEach(function (slide) { slide.classList.remove('on'); });
    index = next;
    list[index].classList.add('on');
    counter.textContent = (index + 1) + ' / ' + list.length;
    fit();
  }

  function start() {
    if (editing) setEdit(false);
    live = true;
    document.body.classList.add('present');
    show(index);
    if (document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen().catch(function () {});
    }
  }

  function stop() {
    live = false;
    document.body.classList.remove('present');
    all.forEach(function (slide) { slide.classList.remove('on'); });
    if (document.fullscreenElement && document.exitFullscreen) {
      document.exitFullscreen().catch(function () {});
    }
    var current = shown()[index];
    if (current) current.scrollIntoView({ block: 'center' });
  }

  // ---------------------------------------------------------------- editing
  function setEdit(on) {
    editing = on;
    document.body.classList.toggle('editing', on);
    fields.forEach(function (field) {
      if (on) field.setAttribute('contenteditable', 'true');
      else field.removeAttribute('contenteditable');
    });
    if (on) window.scrollTo({ top: 0 });
  }

  function collect() {
    var text = {};
    fields.forEach(function (field) {
      var key = field.getAttribute('data-e');
      var value = field.innerText.replace(/\u00a0/g, ' ').trim();
      // Only what was actually changed is stored, so improving the generated
      // wording later still reaches the decks nobody has touched.
      if (value && value !== String(GENERATED[key] || '').trim()) text[key] = value;
    });
    return { text: text, hidden: hiddenState };
  }

  function save() {
    var payload = collect();
    fetch(API, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload)
    }).then(function (response) {
      if (!response.ok) throw new Error(response.status);
      dirty = false;
      say(WORDS.saved);
    }).catch(function () { say(WORDS.failed); });
  }

  function reset() {
    if (!window.confirm(WORDS.resetAsk)) return;
    fields.forEach(function (field) {
      var key = field.getAttribute('data-e');
      if (GENERATED[key] != null) field.innerText = GENERATED[key];
    });
    Object.keys(hiddenState).forEach(function (key) { delete hiddenState[key]; });
    all.forEach(function (slide) { slide.classList.remove('is-off'); });
    dirty = true;
    renumber();
  }

  // ---------------------------------------------------------------- wiring
  var editButton = document.getElementById('btn-edit');
  if (editButton) editButton.addEventListener('click', function () { setEdit(true); });
  document.getElementById('btn-save').addEventListener('click', save);
  document.getElementById('btn-reset').addEventListener('click', reset);
  document.getElementById('btn-done').addEventListener('click', function () { setEdit(false); });
  document.getElementById('btn-present').addEventListener('click', start);
  document.getElementById('btn-print').addEventListener('click', function () { window.print(); });
  document.getElementById('btn-close').addEventListener('click', function () {
    if (dirty && !window.confirm(WORDS.unsaved)) return;
    dirty = false;
    window.close();
  });
  document.getElementById('btn-exit').addEventListener('click', stop);
  document.getElementById('btn-next').addEventListener('click', function () { show(index + 1); });
  document.getElementById('btn-prev').addEventListener('click', function () { show(index - 1); });

  document.addEventListener('input', function (event) {
    if (event.target.hasAttribute && event.target.hasAttribute('data-e')) dirty = true;
  });

  document.addEventListener('click', function (event) {
    var toggle = event.target.closest && event.target.closest('.slide-toggle');
    if (toggle) {
      var slide = toggle.closest('.slide');
      var key = toggle.getAttribute('data-toggle');
      var off = slide.classList.toggle('is-off');
      if (off) hiddenState[key] = true; else delete hiddenState[key];
      dirty = true;
      renumber();
      return;
    }
    // A click advances the deck the way a clicker does — except on the
    // controls, and never while a sentence is being edited.
    if (!live || editing) return;
    if (event.target.closest && event.target.closest('.hud')) return;
    show(index + 1);
  });

  document.addEventListener('keydown', function (event) {
    if (editing && !live) return;
    if (!live) {
      if (event.key === 'p' || event.key === 'P') start();
      return;
    }
    var key = event.key;
    if (key === 'ArrowRight' || key === 'ArrowDown' || key === ' ' || key === 'PageDown') { show(index + 1); event.preventDefault(); }
    else if (key === 'ArrowLeft' || key === 'ArrowUp' || key === 'PageUp') { show(index - 1); event.preventDefault(); }
    else if (key === 'Home') { show(0); }
    else if (key === 'End') { show(shown().length - 1); }
    else if (key === 'Escape') { stop(); }
  });

  window.addEventListener('beforeunload', function (event) {
    if (!dirty) return undefined;
    event.preventDefault();
    event.returnValue = '';
    return '';
  });

  window.addEventListener('resize', fit);
  renumber();
})();
</script>
</body>
</html>`;
}
