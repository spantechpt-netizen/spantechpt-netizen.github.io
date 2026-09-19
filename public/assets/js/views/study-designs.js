/**
 * The cost comparison study in six designs.
 *
 * The figures are the same whichever design is chosen — they come from the
 * server's study engine — and every sentence a design generates can be
 * rewritten on the document and saved, with the edits kept per design.
 *
 *   deck         the executive slide deck (study-print.js, unchanged)
 *   report       an A4 formal report with numbered sections and full tables
 *   compare      the same slab two ways, side by side, item by item
 *   infographic  one page: six big figures, a cost waterfall, a timeline
 *   dashboard    an owner's dashboard: KPI cards, a donut, bars
 *   story        a narrative deck, one idea per slide, warm palette
 */
import { esc } from '../ui.js';
import { printStudy } from './study-print.js';
import { openDocument, createEditor, money, formatDate } from './doc-shell.js';

export const STUDY_DESIGNS = [
  { id: 'deck', ar: 'الشرائح التنفيذية', en: 'Executive deck' },
  { id: 'report', ar: 'التقرير الرسمي', en: 'Formal report' },
  { id: 'compare', ar: 'المقارنة وجهاً لوجه', en: 'Side by side' },
  { id: 'infographic', ar: 'الإنفوجرافيك', en: 'Infographic' },
  { id: 'dashboard', ar: 'لوحة المالك', en: 'Owner dashboard' },
  { id: 'story', ar: 'القصة', en: 'The story' },
];

const L = {
  ar: {
    title: 'دراسة مقارنة تكلفة الأسقف', sub: 'الأسقف اللاحقة للشد مقابل النظام التقليدي',
    prepared_for: 'مقدمة إلى', prepared_by: 'إعداد', project: 'المشروع', date: 'التاريخ', ref: 'مرجع العرض',
    summary: 'ملخص تنفيذي', basis: 'أساس المقارنة', per_sqm: 'المقارنة للمتر المربع', project_level: 'الوفر على مستوى المشروع',
    benefits: 'مكاسب إضافية', drawings: 'المخططات', notes: 'ملاحظات', closing: 'الخلاصة',
    item: 'البند', conventional: 'تقليدي', pt: 'لاحق الشد', diff: 'الفرق',
    concrete: 'الخرسانة', rebar: 'حديد التسليح', formwork: 'الشدات', pt_package: 'أعمال الشد اللاحق', total_sqm: 'الإجمالي (ريال/م²)',
    floors: 'عدد الأدوار', area: 'مساحة السقف للدور', total_area: 'إجمالي المساحة', system: 'النظام التقليدي محل المقارنة',
    thickness: 'سُمك السقف', density: 'كثافة الحديد', mm: 'مم', kg_m3: 'كجم/م³', sqm: 'م²', floor_word: 'أدوار',
    slab_diff: 'فرق تكلفة الأسقف', foundation: 'وفر الأساسات والأعمدة', programme: 'وفر مدة التنفيذ', net: 'صافي الوفر',
    of_conventional: 'من تكلفة الأسقف التقليدية',
    concrete_saved: 'خرسانة موفَّرة', rebar_saved: 'حديد موفَّر', weight_saved: 'وزن أخف', thinner: 'سُمك السقف', height: 'ارتفاع المبنى', days: 'مدة التنفيذ',
    day: 'يوم', days_word: 'يوماً', instead_of: 'بدل',
    summary_text: (n) => `يعرض هذا التقرير المقارنة بين تنفيذ أسقف المشروع بالنظام التقليدي ونظام الخرسانة لاحقة الشد، على نفس المساحات وبأسعار السوق الحالية للطرفين. وتشير النتائج إلى وفر صافٍ قدره ${n} على مستوى المشروع، مع أسقف أرفع وأخف ومدة تنفيذ أقصر.`,
    negative_slab: 'على مستوى السقف وحده يظل نظام الشد اللاحق أعلى تكلفة في هذه الحالة، ويأتي الوفر من الأساسات والأعمدة ومدة التنفيذ.',
    where: 'من أين يأتي الوفر؟', same_building: 'المبنى نفسه بطريقتين', the_number: 'الرقم الذي يهمّ',
    conv_total: 'التكلفة التقليدية', pt_total: 'تكلفة الشد اللاحق', timeline: 'البرنامج الزمني', per_floor: 'للدور',
    dashboard: 'لوحة الوفر', in_favour: 'في صالح الشد اللاحق', not_in_favour: 'في صالح التقليدي', sources: 'مصادر الوفر', per_sqm_short: 'للمتر المربع',
    updated: 'تحديث', slab_only: 'فرق الأسقف', kpi_net: 'صافي الوفر', kpi_pct: 'نسبة الوفر',
    story_1_k: 'المبنى', story_1_h: (f, t) => `${f} ${f > 10 ? 'دوراً' : 'أدوار'}… أخف بـ ${t} طناً`,
    story_1_p: 'نفس المساحات، نفس البحور. الفرق تحت قدميك: سقف أرفع يحمل نفس الأحمال بكابلات مشدودة بدلاً من كتلة الخرسانة والحديد.',
    story_2_k: 'ماذا يعني ذلك', story_2_days: 'تسليم أبكر لأن دورة الدور أقصر. الأسبوع الذي يُوفَّر في السقف يُوفَّر في كل شيء بعده.',
    story_2_height: 'ارتفاع يُكسب من المبنى كله؛ واجهات أقل، وربما دور إضافي في حدود الارتفاع المسموح.',
    story_3_k: 'الكميات', story_3_h: 'أقل خرسانة، أقل حديد، أقل وزن على الأساسات',
    story_4_k: 'الحساب', story_4_h: 'بند ببند، بنفس الأسعار للطرفين',
    story_5_k: 'وفي النهاية', story_6_k: 'المخططات', story_7_k: 'نتكلم؟', story_7_h: 'فريق واحد للتصميم والتنفيذ',
    story_7_p: 'نصمّم، نورّد، نركّب ونشدّ ونحقن، ونسلّم تقارير الشد ومخططات ما تم تنفيذه مع كل دور.',
    original: 'التصميم الأصلي', proposed: 'تصميم الشد اللاحق المقترح',
    page: 'صفحة', of: 'من',
  },
  en: {
    title: 'Slab Cost Comparison Study', sub: 'Post-tensioned slabs against the conventional system',
    prepared_for: 'Prepared for', prepared_by: 'Prepared by', project: 'Project', date: 'Date', ref: 'Quotation ref.',
    summary: 'Executive summary', basis: 'Basis of comparison', per_sqm: 'Comparison per square metre', project_level: 'Saving at project level',
    benefits: 'Further benefits', drawings: 'Drawings', notes: 'Notes', closing: 'Conclusion',
    item: 'Item', conventional: 'Conventional', pt: 'Post-tensioned', diff: 'Difference',
    concrete: 'Concrete', rebar: 'Reinforcement', formwork: 'Formwork', pt_package: 'Post-tensioning works', total_sqm: 'Total (per m²)',
    floors: 'Floors', area: 'Slab area per floor', total_area: 'Total area', system: 'Conventional system compared',
    thickness: 'Slab thickness', density: 'Steel density', mm: 'mm', kg_m3: 'kg/m³', sqm: 'm²', floor_word: 'floors',
    slab_diff: 'Slab cost difference', foundation: 'Foundations and columns', programme: 'Construction time', net: 'Net saving',
    of_conventional: 'of the conventional slab cost',
    concrete_saved: 'Concrete saved', rebar_saved: 'Steel saved', weight_saved: 'Lighter building', thinner: 'Slab thickness', height: 'Building height', days: 'Programme',
    day: 'day', days_word: 'days', instead_of: 'instead of',
    summary_text: (n) => `This report compares building the project's slabs conventionally against post-tensioned slabs, on the same areas and at today's market rates for both. The result is a net saving of ${n} at project level, with thinner, lighter slabs and a shorter programme.`,
    negative_slab: 'On the slab alone the post-tensioned option costs more in this case; the saving comes from foundations, columns and time.',
    where: 'Where does the saving come from?', same_building: 'The same building, two ways', the_number: 'The number that matters',
    conv_total: 'Conventional cost', pt_total: 'Post-tensioned cost', timeline: 'Programme', per_floor: 'per floor',
    dashboard: 'Saving dashboard', in_favour: 'Favours post-tensioning', not_in_favour: 'Favours conventional', sources: 'Sources of saving', per_sqm_short: 'per m²',
    updated: 'Updated', slab_only: 'Slab difference', kpi_net: 'Net saving', kpi_pct: 'Saving',
    story_1_k: 'THE BUILDING', story_1_h: (f, t) => `${f} floors… ${t} tonnes lighter`,
    story_1_p: 'Same areas, same spans. The difference is under your feet: a thinner slab carrying the same loads with stressed strand instead of mass concrete and steel.',
    story_2_k: 'WHAT IT MEANS', story_2_days: 'Earlier handover because each floor cycle is shorter. A week saved on the slab is a week saved on everything after it.',
    story_2_height: 'Height gained across the whole building: less façade, and perhaps an extra floor within the permitted height.',
    story_3_k: 'QUANTITIES', story_3_h: 'Less concrete, less steel, less weight on the foundations',
    story_4_k: 'THE ARITHMETIC', story_4_h: 'Item by item, at the same rates for both',
    story_5_k: 'AND IN THE END', story_6_k: 'DRAWINGS', story_7_k: 'SHALL WE TALK?', story_7_h: 'One team from design to stressing',
    story_7_p: 'We design, supply, install, stress and grout, and hand over stressing reports and as-built drawings with every floor.',
    original: 'Original design', proposed: 'Proposed post-tensioned design',
    page: 'Page', of: 'of',
  },
};

/** Everything a design needs, worked out once. */
function context(data, lang, ed) {
  const isAr = lang === 'ar';
  const T = L[lang];
  const study = data.study;
  const s = study.input;
  const q = data.quotation || {};
  const company = data.company || {};
  const branch = data.branch || company;
  const currency = q.currency || '';
  const pick = (ar, en) => (isAr ? ar : en) || en || ar || '';
  return {
    isAr, T, study, s, q, company, branch, currency, ed, lang,
    dir: isAr ? 'rtl' : 'ltr',
    font: isAr ? "'Cairo','Tajawal',Tahoma,sans-serif" : "'Inter','Segoe UI',Arial,sans-serif",
    projectName: pick(q.project_name_ar, q.project_name),
    customerName: pick(q.customer_name_ar, q.customer_name),
    systemName: pick(study.system.label_ar, study.system.label_en),
    branchName: pick(branch.name_ar || company.name_ar, branch.name_en || company.name_en),
    notes: pick(s.notes_ar, s.notes_en),
    logo: esc(branch.logo || '/assets/img/logo@2x.png'),
    cash: (v) => `${money(v, 0)} ${currency}`,
    cash2: (v) => `${money(v, 2)} ${currency}`,
    n0: (v) => money(v, 0),
    n2: (v) => money(v, 2),
    drawings: (kind) => (data.drawings || []).filter((d) => d.kind === kind),
    caption: (d) => pick(d.caption_ar, d.caption_en),
    dateText: data.generated_at || formatDate(new Date().toISOString().slice(0, 10)),
    ref: `${q.number || ''}${q.revision ? ` R${q.revision}` : ''}`,
  };
}

const BASE_CSS = (c) => `
  * { box-sizing: border-box; }
  body { margin: 0; font-family: ${c.font}; color: #17202b; background: #eef1f5; line-height: 1.6;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .n { font-family: 'Inter', ${c.font}; direction: ltr; unicode-bidi: plaintext; font-variant-numeric: tabular-nums; }
  .good { color: #14683f; } .bad { color: #a32020; }
  table { width: 100%; border-collapse: collapse; }
  @media print { body { background: #fff; } }
`;

/** A comparison table, the same in every A4 design. */
function compareTable(c, cls = 'cmp') {
  const { T, study, n2 } = c;
  const row = (label, a, b) => `
    <tr><td>${esc(label)}</td><td class="n">${n2(a)}</td><td class="n">${n2(b)}</td>
    <td class="n ${a - b >= 0 ? 'good' : 'bad'}">${a - b >= 0 ? '−' : '+'}${n2(Math.abs(a - b))}</td></tr>`;
  const cv = study.conventional; const pt = study.post_tension;
  return `
    <table class="${cls}">
      <thead><tr><th>${esc(T.item)}</th><th class="n">${esc(T.conventional)}</th><th class="n">${esc(T.pt)}</th><th class="n">${esc(T.diff)}</th></tr></thead>
      <tbody>
        ${row(T.concrete, cv.concrete, pt.concrete)}
        ${row(T.rebar, cv.rebar, pt.rebar)}
        ${row(T.formwork, cv.formwork, pt.formwork)}
        ${row(T.pt_package, cv.post_tension, pt.post_tension)}
      </tbody>
      <tfoot>${row(T.total_sqm, cv.per_sqm, pt.per_sqm)}</tfoot>
    </table>`;
}

function drawingsBlock(c, key) {
  const { T, ed } = c;
  const original = c.drawings('original');
  const proposed = c.drawings('post_tension');
  if (!original.length && !proposed.length) return '';
  const col = (list, heading, k) => `
    <div class="draw-col">
      <div class="draw-h" ${ed.mark(k)}>${ed.txt(k, heading)}</div>
      ${list.map((d) => `<figure><img src="${esc(d.url)}" alt="${esc(c.caption(d) || heading)}">${c.caption(d) ? `<figcaption>${esc(c.caption(d))}</figcaption>` : ''}</figure>`).join('')}
    </div>`;
  return `
    <section class="sec" ${ed.sec(key)}>
      <h2 ${ed.mark(`${key}.h`)}>${ed.txt(`${key}.h`, T.drawings)}</h2>
      <div class="draw-grid">${col(original, T.original, `${key}.orig`)}${col(proposed, T.proposed, `${key}.prop`)}</div>
    </section>`;
}

// ===================================================================== report
function report(c) {
  const { T, ed, study, s } = c;
  const b = study.benefits;
  const sv = study.saving;
  const css = `${BASE_CSS(c)}
    @page { size: A4; margin: 18mm 16mm 20mm; }
    .sheet { width: 210mm; margin: 0 auto; background: #fff; padding: 16mm 16mm 18mm; min-height: 297mm; position: relative; }
    @media print { .sheet { width: auto; min-height: 0; margin: 0; padding: 0; } }
    .head { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 3px solid #0a2647; padding-bottom: 8px; }
    .head h1 { margin: 0; font-size: 19pt; color: #0a2647; font-weight: 800; }
    .head .sub { color: #5b6775; font-size: 9.5pt; }
    .head .brand { text-align: ${c.isAr ? 'left' : 'right'}; font-size: 9pt; color: #5b6775; }
    .head .brand img { max-height: 46px; max-width: 48mm; display: block; margin-inline-start: auto; margin-bottom: 4px; }
    .meta { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin: 10px 0 4px; font-size: 9pt; }
    .meta div { border: 1px solid #d9dfe8; padding: 5px 8px; border-radius: 3px; }
    .meta .k { color: #5b6775; font-size: 8pt; }
    .meta .v { font-weight: 700; }
    h2 { font-size: 11.5pt; color: #0a2647; margin: 16px 0 6px; font-weight: 800; break-after: avoid; }
    h2 .no { display: inline-block; min-width: 20px; color: #1a56a7; }
    p { margin: 0 0 6px; text-align: justify; font-size: 10pt; line-height: 1.75; color: #374151; }
    table.cmp th, table.cmp td, table.grid th, table.grid td { border: 1px solid #c8d3e0; padding: 5px 8px; font-size: 9.5pt; }
    table.cmp th, table.grid th { background: #f3f4f6; text-align: start; font-weight: 700; }
    table.cmp th.n, table.cmp td.n { text-align: center; }
    table.cmp tfoot td { font-weight: 800; background: #f9fafb; }
    table.grid td.n { text-align: ${c.isAr ? 'left' : 'right'}; }
    table.grid tr.total td { font-weight: 800; }
    .callout { margin-top: 8px; padding: 8px 12px; background: #e8f0fa; border-inline-start: 3px solid #1a56a7; font-size: 9.8pt; }
    .warn { background: #fdf3dc; border-color: #c9761a; }
    .ben { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .ben div { border: 1px solid #d9dfe8; border-radius: 3px; padding: 8px 10px; }
    .ben .v { font-size: 14pt; font-weight: 800; color: #0a2647; }
    .ben .k { font-size: 8.5pt; color: #5b6775; }
    .draw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .draw-h { font-weight: 700; font-size: 9.5pt; color: #0a2647; margin-bottom: 4px; }
    figure { margin: 0 0 6px; } figure img { width: 100%; border: 1px solid #d9dfe8; } figcaption { font-size: 8pt; color: #5b6775; }
    .foot { margin-top: 18px; padding-top: 6px; border-top: 1px solid #d9dfe8; font-size: 8pt; color: #5b6775; display: flex; justify-content: space-between; }
    .sec { break-inside: avoid; }
  `;
  const body = `
  <div class="sheet">
    <div class="head" ${ed.sec('head')}>
      <div><h1 ${ed.mark('title')}>${ed.txt('title', T.title)}</h1><div class="sub" ${ed.mark('sub')}>${ed.txt('sub', T.sub)}</div></div>
      <div class="brand"><img src="${c.logo}" alt=""><div>${esc(c.branchName)}</div><div class="n">${esc(c.ref)}</div></div>
    </div>
    <div class="meta">
      <div><div class="k">${esc(T.project)}</div><div class="v">${esc(c.projectName)}</div></div>
      <div><div class="k">${esc(T.prepared_for)}</div><div class="v">${esc(c.customerName)}</div></div>
      <div><div class="k">${esc(T.system)}</div><div class="v">${esc(c.systemName)}</div></div>
      <div><div class="k">${esc(T.date)}</div><div class="v n">${esc(c.dateText)}</div></div>
    </div>

    <section class="sec" ${ed.sec('summary')}>
      <h2><span class="no">1.</span> <span ${ed.mark('summary.h')}>${ed.txt('summary.h', T.summary)}</span></h2>
      <p ${ed.mark('summary.p')}>${ed.prose('summary.p', T.summary_text(c.cash(sv.total)))}</p>
      ${!sv.favours_pt_on_slab_alone ? `<div class="callout warn" ${ed.mark('summary.warn')}>${ed.txt('summary.warn', T.negative_slab)}</div>` : ''}
    </section>

    <section class="sec" ${ed.sec('basis')}>
      <h2><span class="no">2.</span> <span ${ed.mark('basis.h')}>${ed.txt('basis.h', T.basis)}</span></h2>
      <table class="grid"><tbody>
        <tr><td>${esc(T.floors)}</td><td class="n">${s.floors}</td><td>${esc(T.area)}</td><td class="n">${c.n0(s.area_sqm)} ${esc(T.sqm)}</td></tr>
        <tr><td>${esc(T.total_area)}</td><td class="n">${c.n0(study.total_area_sqm)} ${esc(T.sqm)}</td><td>${esc(T.system)}</td><td>${esc(c.systemName)}</td></tr>
        <tr><td>${esc(T.thickness)} (${esc(T.conventional)})</td><td class="n">${c.n0(s.conv_thickness_mm)} ${esc(T.mm)}</td><td>${esc(T.thickness)} (${esc(T.pt)})</td><td class="n">${c.n0(s.pt_thickness_mm)} ${esc(T.mm)}</td></tr>
        <tr><td>${esc(T.density)} (${esc(T.conventional)})</td><td class="n">${c.n0(s.conv_rebar_kg_m3)} ${esc(T.kg_m3)}</td><td>${esc(T.density)} (${esc(T.pt)})</td><td class="n">${c.n0(s.pt_rebar_kg_m3)} ${esc(T.kg_m3)}</td></tr>
      </tbody></table>
    </section>

    <section class="sec" ${ed.sec('compare')}>
      <h2><span class="no">3.</span> <span ${ed.mark('compare.h')}>${ed.txt('compare.h', T.per_sqm)}</span></h2>
      ${compareTable(c)}
    </section>

    <section class="sec" ${ed.sec('project')}>
      <h2><span class="no">4.</span> <span ${ed.mark('project.h')}>${ed.txt('project.h', T.project_level)}</span></h2>
      <table class="grid"><tbody>
        <tr><td>${esc(T.slab_diff)} (${c.n0(study.total_area_sqm)} ${esc(T.sqm)})</td><td class="n">${c.cash(sv.slab_total)}</td></tr>
        <tr><td>${esc(T.foundation)}</td><td class="n">${c.cash(sv.foundation_total)}</td></tr>
        <tr><td>${esc(T.programme)} (${c.n0(study.benefits.days_saved)} ${esc(T.days_word)})</td><td class="n">${c.cash(sv.programme_total)}</td></tr>
        <tr class="total"><td>${esc(T.net)}</td><td class="n ${sv.total >= 0 ? 'good' : 'bad'}">${c.cash(sv.total)} (${c.n2(sv.pct)}%)</td></tr>
      </tbody></table>
    </section>

    <section class="sec" ${ed.sec('benefits')}>
      <h2><span class="no">5.</span> <span ${ed.mark('benefits.h')}>${ed.txt('benefits.h', T.benefits)}</span></h2>
      <div class="ben">
        <div><div class="v n">${c.n0(b.concrete_saved_m3)} m³</div><div class="k">${esc(T.concrete_saved)}</div></div>
        <div><div class="v n">${c.n2(b.rebar_saved_ton)} t</div><div class="k">${esc(T.rebar_saved)}</div></div>
        <div><div class="v n">${c.n0(b.weight_saved_ton)} t</div><div class="k">${esc(T.weight_saved)}</div></div>
        <div><div class="v n">−${c.n0(b.thickness_saved_mm)} ${esc(T.mm)}</div><div class="k">${esc(T.thinner)}</div></div>
        <div><div class="v n">−${c.n0(b.height_saved_mm)} ${esc(T.mm)}</div><div class="k">${esc(T.height)}</div></div>
        <div><div class="v n">−${c.n0(b.days_saved)} ${esc(T.day)}</div><div class="k">${esc(T.days)}</div></div>
      </div>
    </section>

    ${drawingsBlock(c, 'drawings')}

    ${c.notes ? `<section class="sec" ${ed.sec('notes')}><h2><span class="no">6.</span> ${esc(T.notes)}</h2><p ${ed.mark('notes.p')}>${ed.prose('notes.p', c.notes)}</p></section>` : ''}

    <div class="foot"><span>${esc(c.branchName)}</span><span class="n">${esc(c.ref)} · ${esc(c.dateText)}</span></div>
  </div>`;
  return { css, body };
}

// ==================================================================== compare
function compare(c) {
  const { T, ed, study, s } = c;
  const sv = study.saving;
  const css = `${BASE_CSS(c)}
    @page { size: A4; margin: 14mm; }
    .sheet { width: 210mm; margin: 0 auto; background: #f7f8fa; padding: 14mm 14mm 16mm; min-height: 297mm; }
    @media print { .sheet { width: auto; min-height: 0; margin: 0; padding: 0; background: #fff; } }
    h1 { text-align: center; font-size: 20pt; color: #0a2647; margin: 0; font-weight: 900; }
    .sub { text-align: center; color: #5b6775; font-size: 9.5pt; margin-bottom: 14px; }
    .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .col { background: #fff; border: 1px solid #d1d5db; border-radius: 10px; padding: 14px; text-align: center; }
    .col.pt { border: 2px solid #1a56a7; box-shadow: 0 8px 20px rgba(26,86,167,.14); }
    .col .k { font-size: 9pt; letter-spacing: .06em; color: #5b6775; font-weight: 700; }
    .col.pt .k { color: #1a56a7; }
    .slab { margin: 10px auto 0; width: 60mm; position: relative; border-radius: 3px; }
    .slab.conv { height: 13mm; background: #9ca3af; }
    .slab.conv::before, .slab.conv::after { content: ''; position: absolute; left: 0; right: 0; height: 2px; background: #374151; }
    .slab.conv::before { top: 5px; } .slab.conv::after { bottom: 5px; }
    .slab.ptn { height: 10.5mm; background: #c9d9f0; overflow: hidden; }
    .slab.ptn svg { position: absolute; inset: 0; width: 100%; height: 100%; }
    .spec { font-size: 8.5pt; color: #5b6775; margin-top: 4px; }
    .price { font-size: 30pt; font-weight: 800; color: #374151; margin-top: 8px; line-height: 1.1; }
    .col.pt .price { color: #1a56a7; }
    .unit { font-size: 8.5pt; color: #5b6775; }
    .tbl { margin-top: 12px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 14px; }
    table.cmp th, table.cmp td { padding: 6px 4px; font-size: 9.5pt; border-bottom: 1px solid #f3f4f6; }
    table.cmp th { color: #5b6775; font-weight: 700; text-align: start; border-bottom: 1px solid #e5e7eb; }
    table.cmp th.n, table.cmp td.n { text-align: center; }
    table.cmp tfoot td { font-weight: 800; border-bottom: 0; border-top: 2px solid #e5e7eb; }
    .band { margin-top: 12px; display: flex; align-items: center; justify-content: space-between; background: #0a2647; color: #fff; border-radius: 10px; padding: 12px 16px; }
    .band .k { font-size: 11pt; font-weight: 700; }
    .band .v { font-size: 22pt; font-weight: 800; color: #f2c879; }
    .band .s { font-size: 8.5pt; color: #b9cbe4; }
    .srcs { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 12px; }
    .srcs div { background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 10px 12px; }
    .srcs .v { font-size: 14pt; font-weight: 800; color: #0a2647; }
    .srcs .k { font-size: 8.5pt; color: #5b6775; }
    .warn { margin-top: 10px; padding: 8px 12px; background: #fdf3dc; border-inline-start: 3px solid #c9761a; font-size: 9pt; border-radius: 4px; }
    .draw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
    .draw-h { font-weight: 700; font-size: 9.5pt; color: #0a2647; margin-bottom: 4px; }
    figure { margin: 0 0 6px; } figure img { width: 100%; border: 1px solid #d9dfe8; border-radius: 4px; } figcaption { font-size: 8pt; color: #5b6775; }
    h2 { font-size: 11pt; color: #0a2647; margin: 14px 0 4px; }
    .foot { margin-top: 14px; font-size: 8pt; color: #9ca3af; display: flex; justify-content: space-between; }
    .sec { break-inside: avoid; }
  `;
  const body = `
  <div class="sheet">
    <section class="sec" ${ed.sec('head')}>
      <h1 ${ed.mark('title')}>${ed.txt('title', T.same_building)}</h1>
      <div class="sub"><span ${ed.mark('sub')}>${ed.txt('sub', `${c.projectName} · ${T.per_sqm_short}`)}</span></div>
      <div class="cols">
        <div class="col">
          <div class="k" ${ed.mark('conv.k')}>${ed.txt('conv.k', c.systemName)}</div>
          <div class="slab conv"></div>
          <div class="spec n">${c.n0(s.conv_thickness_mm)} ${esc(T.mm)} · ${c.n0(s.conv_rebar_kg_m3)} ${esc(T.kg_m3)}</div>
          <div class="price n">${c.n2(study.conventional.per_sqm)}</div>
          <div class="unit">${esc(c.currency)} / ${esc(T.sqm)}</div>
        </div>
        <div class="col pt">
          <div class="k" ${ed.mark('pt.k')}>${ed.txt('pt.k', T.pt)}</div>
          <div class="slab ptn"><svg viewBox="0 0 150 38" preserveAspectRatio="none"><path d="M0 8 Q 75 34 150 8" stroke="#1a56a7" stroke-width="2.5" fill="none"/></svg></div>
          <div class="spec n">${c.n0(s.pt_thickness_mm)} ${esc(T.mm)} · ${c.n0(s.pt_rebar_kg_m3)} ${esc(T.kg_m3)}</div>
          <div class="price n">${c.n2(study.post_tension.per_sqm)}</div>
          <div class="unit">${esc(c.currency)} / ${esc(T.sqm)}</div>
        </div>
      </div>
    </section>

    <section class="sec" ${ed.sec('table')}>
      <div class="tbl">${compareTable(c)}</div>
      ${!sv.favours_pt_on_slab_alone ? `<div class="warn" ${ed.mark('warn')}>${ed.txt('warn', T.negative_slab)}</div>` : ''}
    </section>

    <section class="sec" ${ed.sec('total')}>
      <div class="band">
        <div><div class="k" ${ed.mark('band.k')}>${ed.txt('band.k', `${T.net} · ${s.floors} ${T.floor_word}`)}</div><div class="s n">${c.n0(study.total_area_sqm)} ${esc(T.sqm)} · ${c.n2(sv.pct)}% ${esc(T.of_conventional)}</div></div>
        <div class="v n">${c.cash(sv.total)}</div>
      </div>
      <div class="srcs">
        <div><div class="v n">${c.cash(sv.slab_total)}</div><div class="k">${esc(T.slab_diff)}</div></div>
        <div><div class="v n">${c.cash(sv.foundation_total)}</div><div class="k">${esc(T.foundation)}</div></div>
        <div><div class="v n">${c.cash(sv.programme_total)}</div><div class="k">${esc(T.programme)} · ${c.n0(study.benefits.days_saved)} ${esc(T.day)}</div></div>
      </div>
    </section>

    ${drawingsBlock(c, 'drawings')}
    <div class="foot"><span>${esc(c.branchName)}</span><span class="n">${esc(c.ref)} · ${esc(c.dateText)}</span></div>
  </div>`;
  return { css, body };
}

// ================================================================ infographic
function infographic(c) {
  const { T, ed, study } = c;
  const b = study.benefits; const sv = study.saving;
  const convTotal = study.conventional.total;
  const ptTotal = convTotal - sv.total;
  // Waterfall geometry: bars scaled to the conventional total.
  const W = 520; const H = 150; const top = 22; const base = 138;
  const scale = (v) => (convTotal > 0 ? (v / convTotal) * (base - top) : 0);
  const steps = [
    { label: T.slab_diff, value: sv.slab_total, colour: '#14683f' },
    { label: T.foundation, value: sv.foundation_total, colour: '#178553' },
    { label: T.programme, value: sv.programme_total, colour: '#4ade80' },
  ];
  let running = convTotal;
  const short = (v) => (Math.abs(v) >= 1e6 ? `${money(v / 1e6, 2)}M` : Math.abs(v) >= 1e3 ? `${money(v / 1e3, 0)}K` : money(v, 0));
  const bars = [`<rect x="20" y="${base - scale(convTotal)}" width="80" height="${scale(convTotal)}" fill="#9ca3af"/><text x="60" y="${base + 14}" text-anchor="middle">${esc(T.conv_total)}</text><text x="60" y="${base - scale(convTotal) - 5}" text-anchor="middle" font-weight="700">${short(convTotal)}</text>`];
  steps.forEach((step, i) => {
    const x = 120 + i * 100;
    const yTop = base - scale(running);
    const h = Math.max(1, scale(Math.abs(step.value)));
    const y = step.value >= 0 ? yTop : yTop - h;
    bars.push(`<rect x="${x}" y="${y}" width="70" height="${h}" fill="${step.value >= 0 ? step.colour : '#a32020'}"/><text x="${x + 35}" y="${base + 14}" text-anchor="middle" font-size="8.5">${esc(step.label)}</text><text x="${x + 35}" y="${y - 5}" text-anchor="middle" font-weight="700" fill="${step.value >= 0 ? '#14683f' : '#a32020'}">${step.value >= 0 ? '−' : '+'}${short(Math.abs(step.value))}</text>`);
    running -= step.value;
  });
  bars.push(`<line x1="20" y1="${base}" x2="${W - 10}" y2="${base}" stroke="#d1d5db"/><rect x="420" y="${base - scale(ptTotal)}" width="80" height="${scale(ptTotal)}" fill="#1a56a7"/><text x="460" y="${base + 14}" text-anchor="middle">${esc(T.pt_total)}</text><text x="460" y="${base - scale(ptTotal) - 5}" text-anchor="middle" font-weight="700" fill="#1a56a7">${short(ptTotal)}</text>`);

  const convDays = b.conv_programme_days; const ptDays = b.pt_programme_days;
  const css = `${BASE_CSS(c)}
    @page { size: A4; margin: 12mm; }
    .sheet { width: 210mm; margin: 0 auto; background: #fff; padding: 12mm 14mm; min-height: 297mm; }
    @media print { .sheet { width: auto; min-height: 0; margin: 0; padding: 0; } }
    .top { display: flex; justify-content: space-between; align-items: center; }
    .top h1 { margin: 0; font-size: 18pt; color: #0a2647; font-weight: 900; }
    .top .s { font-size: 9pt; color: #5b6775; }
    .tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; text-align: center; }
    .tile { border-radius: 10px; padding: 10px 6px; background: #e3eefb; }
    .tile.warm { background: #fdf1e2; }
    .tile .v { font-size: 20pt; font-weight: 800; color: #1a56a7; line-height: 1.1; }
    .tile.warm .v { color: #c9761a; }
    .tile .k { font-size: 8.5pt; color: #374151; margin-top: 2px; }
    h2 { font-size: 11pt; color: #0a2647; margin: 14px 0 4px; font-weight: 800; }
    svg.wf { width: 100%; height: auto; display: block; font-family: 'Inter', ${c.font}; font-size: 11px; fill: #374151; }
    .band { display: flex; align-items: center; gap: 14px; margin-top: 10px; background: #0a2647; color: #fff; border-radius: 10px; padding: 10px 14px; }
    .band .p { font-size: 24pt; font-weight: 800; color: #f2c879; line-height: 1; }
    .band .t { font-size: 10pt; line-height: 1.4; }
    .time { margin-top: 12px; display: grid; grid-template-columns: 90px 1fr 110px; gap: 8px; align-items: center; font-size: 9pt; color: #374151; }
    .bar { height: 12px; background: #e5e7eb; border-radius: 6px; position: relative; overflow: hidden; }
    .bar i { position: absolute; inset: 0; border-radius: 6px; }
    .bar i.conv { background: #9ca3af; } .bar i.pt { background: #1a56a7; }
    .cmp-wrap { margin-top: 12px; border: 1px solid #e5e7eb; border-radius: 10px; padding: 8px 12px; }
    table.cmp th, table.cmp td { padding: 4px 4px; font-size: 9pt; border-bottom: 1px solid #f3f4f6; }
    table.cmp th { color: #5b6775; text-align: start; } table.cmp th.n, table.cmp td.n { text-align: center; }
    table.cmp tfoot td { font-weight: 800; border-top: 2px solid #e5e7eb; border-bottom: 0; }
    .draw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .draw-h { font-weight: 700; font-size: 9pt; color: #0a2647; margin-bottom: 4px; }
    figure { margin: 0 0 6px; } figure img { width: 100%; border: 1px solid #d9dfe8; border-radius: 4px; } figcaption { font-size: 8pt; color: #5b6775; }
    .foot { margin-top: 12px; font-size: 8pt; color: #9ca3af; display: flex; justify-content: space-between; }
    .sec { break-inside: avoid; }
  `;
  const body = `
  <div class="sheet">
    <section class="sec" ${ed.sec('head')}>
      <div class="top"><h1 ${ed.mark('title')}>${ed.txt('title', T.the_number)}</h1><div class="s">${esc(c.projectName)} · ${esc(c.customerName)}</div></div>
      <div class="tiles">
        <div class="tile"><div class="v n">${c.n0(b.concrete_saved_m3)} m³</div><div class="k">${esc(T.concrete_saved)}</div></div>
        <div class="tile"><div class="v n">${c.n2(b.rebar_saved_ton)} t</div><div class="k">${esc(T.rebar_saved)}</div></div>
        <div class="tile"><div class="v n">${c.n0(b.weight_saved_ton)} t</div><div class="k">${esc(T.weight_saved)}</div></div>
        <div class="tile warm"><div class="v n">−${c.n0(b.thickness_saved_mm)} ${esc(T.mm)}</div><div class="k">${esc(T.thinner)}</div></div>
        <div class="tile warm"><div class="v n">−${c.n0(b.height_saved_mm)} ${esc(T.mm)}</div><div class="k">${esc(T.height)}</div></div>
        <div class="tile warm"><div class="v n">−${c.n0(b.days_saved)} ${esc(T.day)}</div><div class="k">${esc(T.days)}</div></div>
      </div>
    </section>

    <section class="sec" ${ed.sec('waterfall')}>
      <h2 ${ed.mark('wf.h')}>${ed.txt('wf.h', T.where)}</h2>
      <svg class="wf" viewBox="0 0 ${W} ${H + 12}">${bars.join('')}</svg>
      <div class="band">
        <div class="p n">${c.n2(sv.pct)}%</div>
        <div class="t"><span ${ed.mark('band.t')}>${ed.txt('band.t', T.net)}</span><br><b class="n">${c.cash(sv.total)}</b> · ${s_floors(c)}</div>
      </div>
    </section>

    <section class="sec" ${ed.sec('time')}>
      <h2 ${ed.mark('time.h')}>${ed.txt('time.h', T.timeline)}</h2>
      <div class="time"><span>${esc(T.conventional)}</span><div class="bar"><i class="conv" style="width:100%"></i></div><span class="n">${c.n0(convDays)} ${esc(T.day)}</span></div>
      <div class="time"><span>${esc(T.pt)}</span><div class="bar"><i class="pt" style="width:${convDays ? Math.round((ptDays / convDays) * 100) : 100}%"></i></div><span class="n">${c.n0(ptDays)} ${esc(T.day)}</span></div>
    </section>

    <section class="sec" ${ed.sec('table')}>
      <h2 ${ed.mark('cmp.h')}>${ed.txt('cmp.h', T.per_sqm)}</h2>
      <div class="cmp-wrap">${compareTable(c)}</div>
    </section>

    ${drawingsBlock(c, 'drawings')}
    <div class="foot"><span>${esc(c.branchName)}</span><span class="n">${esc(c.ref)} · ${esc(c.dateText)}</span></div>
  </div>`;
  return { css, body };
}

const s_floors = (c) => `${c.s.floors} ${c.T.floor_word} × ${c.n0(c.s.area_sqm)} ${c.T.sqm}`;

// ================================================================== dashboard
function dashboard(c) {
  const { T, ed, study } = c;
  const sv = study.saving; const b = study.benefits;
  const parts = [sv.slab_total, sv.foundation_total, sv.programme_total].map((v) => Math.max(0, v));
  const sum = parts.reduce((a, v) => a + v, 0) || 1;
  const r = 44; const circ = 2 * Math.PI * r;
  let offset = 0;
  const arcs = parts.map((v, i) => {
    const len = (v / sum) * circ;
    const colour = ['#1a56a7', '#3d8bdd', '#c9761a'][i];
    const arc = `<circle cx="65" cy="65" r="${r}" fill="none" stroke="${colour}" stroke-width="18" stroke-dasharray="${len.toFixed(1)} ${circ.toFixed(1)}" stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 65 65)"/>`;
    offset += len;
    return arc;
  }).join('');
  const pct = (v) => Math.round((Math.max(0, v) / sum) * 100);
  const convMax = Math.max(study.conventional.per_sqm, study.post_tension.per_sqm) || 1;
  const css = `${BASE_CSS(c)}
    @page { size: A4; margin: 12mm; }
    body { background: #f3f5f9; }
    .sheet { width: 210mm; margin: 0 auto; padding: 12mm 13mm; min-height: 297mm; background: #f3f5f9; }
    @media print { .sheet { width: auto; min-height: 0; margin: 0; padding: 0; } }
    .top { display: flex; justify-content: space-between; align-items: center; }
    .top h1 { margin: 0; font-size: 17pt; color: #0a2647; font-weight: 900; }
    .top .s { font-size: 8.5pt; color: #5b6775; }
    .pill { font-size: 9pt; font-weight: 700; padding: 4px 12px; border-radius: 999px; background: #e3f5ec; color: #14683f; }
    .pill.bad { background: #fdeaea; color: #a32020; }
    .cards { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
    .card { background: #fff; border-radius: 10px; padding: 12px 14px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
    .card.k1 { border-inline-start: 4px solid #14683f; } .card.k2 { border-inline-start: 4px solid #1a56a7; }
    .card .k { font-size: 8.5pt; color: #5b6775; font-weight: 700; }
    .card .v { font-size: 22pt; font-weight: 800; line-height: 1.1; }
    .card .m { font-size: 8.5pt; color: #14683f; }
    .card h3 { font-size: 10pt; color: #0a2647; margin: 0 0 6px; font-weight: 800; }
    .two { display: grid; grid-template-columns: 1.1fr 1fr; gap: 10px; margin-top: 10px; }
    .donut-row { display: flex; align-items: center; gap: 12px; }
    svg.donut { width: 112px; height: 112px; flex: none; }
    .legend { list-style: none; margin: 0; padding: 0; font-size: 8.5pt; min-width: 0; flex: 1; }
    .legend li { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
    .legend i { width: 10px; height: 10px; border-radius: 2px; flex: none; } .legend span { flex: 1; } .legend b { flex: none; }
    .lbl { font-size: 8.5pt; margin-top: 8px; display: flex; justify-content: space-between; }
    .bar { height: 12px; background: #e5e7eb; border-radius: 6px; overflow: hidden; } .bar i { display: block; height: 100%; border-radius: 6px; }
    .four { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 10px; text-align: center; font-size: 8.5pt; }
    .four .card { padding: 8px; } .four .v { font-size: 15pt; font-weight: 800; }
    table.cmp th, table.cmp td { padding: 4px 6px; font-size: 9pt; border-bottom: 1px solid #f3f4f6; }
    table.cmp th { color: #5b6775; text-align: start; } table.cmp th.n, table.cmp td.n { text-align: center; }
    table.cmp tfoot td { font-weight: 800; border-top: 2px solid #e5e7eb; border-bottom: 0; }
    .draw-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .draw-h { font-weight: 700; font-size: 9pt; color: #0a2647; margin-bottom: 4px; }
    figure { margin: 0 0 6px; } figure img { width: 100%; border-radius: 6px; } figcaption { font-size: 8pt; color: #5b6775; }
    h2 { font-size: 10.5pt; color: #0a2647; margin: 12px 0 4px; }
    .foot { margin-top: 12px; font-size: 8pt; color: #9ca3af; display: flex; justify-content: space-between; }
    .sec { break-inside: avoid; }
  `;
  const body = `
  <div class="sheet">
    <section class="sec" ${ed.sec('head')}>
      <div class="top">
        <div><h1 ${ed.mark('title')}>${ed.txt('title', T.dashboard)}</h1><div class="s">${esc(c.projectName)} · ${esc(T.updated)} <span class="n">${esc(c.dateText)}</span></div></div>
        <span class="pill ${sv.favours_pt ? '' : 'bad'}">${esc(sv.favours_pt ? T.in_favour : T.not_in_favour)}</span>
      </div>
      <div class="cards">
        <div class="card k1"><div class="k">${esc(T.kpi_net)}</div><div class="v n">${c.cash(sv.total)}</div><div class="m">▲ ${c.n2(sv.pct)}% ${esc(T.of_conventional)}</div></div>
        <div class="card k2"><div class="k">${esc(T.slab_only)}</div><div class="v n">${c.cash(sv.slab_total)}</div><div class="m" style="color:#5b6775">${c.n2(sv.slab_per_sqm)} ${esc(c.currency)}/${esc(T.sqm)} × ${c.n0(study.total_area_sqm)} ${esc(T.sqm)}</div></div>
      </div>
    </section>

    <section class="sec" ${ed.sec('charts')}>
      <div class="two">
        <div class="card">
          <h3 ${ed.mark('src.h')}>${ed.txt('src.h', T.sources)}</h3>
          <div class="donut-row">
            <svg class="donut" viewBox="0 0 130 130">
              <circle cx="65" cy="65" r="${r}" fill="none" stroke="#e5e7eb" stroke-width="18"/>${arcs}
            </svg>
            <!-- The legend is HTML, not SVG text, so a long Arabic label wraps instead of being cut. -->
            <ul class="legend">
              <li><i style="background:#1a56a7"></i><span>${esc(T.slab_diff)}</span><b class="n">${pct(sv.slab_total)}%</b></li>
              <li><i style="background:#3d8bdd"></i><span>${esc(T.foundation)}</span><b class="n">${pct(sv.foundation_total)}%</b></li>
              <li><i style="background:#c9761a"></i><span>${esc(T.programme)}</span><b class="n">${pct(sv.programme_total)}%</b></li>
            </ul>
          </div>
        </div>
        <div class="card">
          <h3 ${ed.mark('sqm.h')}>${ed.txt('sqm.h', T.per_sqm_short)}</h3>
          <div class="lbl"><span>${esc(T.conventional)}</span><span class="n">${c.n2(study.conventional.per_sqm)}</span></div>
          <div class="bar"><i style="width:${Math.round((study.conventional.per_sqm / convMax) * 100)}%;background:#9ca3af"></i></div>
          <div class="lbl"><span>${esc(T.pt)}</span><span class="n">${c.n2(study.post_tension.per_sqm)}</span></div>
          <div class="bar"><i style="width:${Math.round((study.post_tension.per_sqm / convMax) * 100)}%;background:#1a56a7"></i></div>
          <div class="lbl" style="margin-top:12px;color:#5b6775"><span>${esc(T.timeline)}</span><span class="n">${c.n0(b.pt_programme_days)} ${esc(T.instead_of)} ${c.n0(b.conv_programme_days)} ${esc(T.day)}</span></div>
          <div class="bar"><i style="width:${b.conv_programme_days ? Math.round((b.pt_programme_days / b.conv_programme_days) * 100) : 100}%;background:#c9761a"></i></div>
        </div>
      </div>
      <div class="four">
        <div class="card"><div class="v n">${c.n0(b.concrete_saved_m3)} m³</div>${esc(T.concrete_saved)}</div>
        <div class="card"><div class="v n">${c.n2(b.rebar_saved_ton)} t</div>${esc(T.rebar_saved)}</div>
        <div class="card"><div class="v n">−${c.n0(b.days_saved)}</div>${esc(T.day)}</div>
        <div class="card"><div class="v n">−${c.n0(b.height_saved_mm)}</div>${esc(T.mm)} ${esc(T.height)}</div>
      </div>
    </section>

    <section class="sec" ${ed.sec('table')}>
      <div class="card" style="margin-top:10px"><h3 ${ed.mark('cmp.h')}>${ed.txt('cmp.h', T.per_sqm)}</h3>${compareTable(c)}</div>
    </section>

    ${drawingsBlock(c, 'drawings')}
    <div class="foot"><span>${esc(c.branchName)}</span><span class="n">${esc(c.ref)}</span></div>
  </div>`;
  return { css, body };
}

// ======================================================================= story
function story(c) {
  const { T, ed, study, s } = c;
  const b = study.benefits; const sv = study.saving;
  const skyline = `
    <svg class="sky" viewBox="0 0 600 330" preserveAspectRatio="xMidYMax slice">
      <g fill="#374151"><rect x="60" y="150" width="70" height="180"/><rect x="150" y="110" width="60" height="220"/><rect x="230" y="170" width="80" height="160"/><rect x="330" y="80" width="70" height="250"/><rect x="420" y="140" width="60" height="190"/><rect x="500" y="190" width="50" height="140"/></g>
      <g fill="#f2c879" opacity=".9">${[0, 1, 2, 3, 4, 5].map((i) => `<rect x="330" y="${80 + i * 40}" width="70" height="${i ? 4 : 8}"/>`).join('')}</g>
    </svg>`;
  const slide = (key, kicker, inner, cls = '') => `
    <section class="slide ${cls}" ${ed.sec(key)}>
      <div class="kick" ${ed.mark(`${key}.k`)}>${ed.txt(`${key}.k`, kicker)}</div>
      ${inner}
      <div class="sfoot"><span>${esc(c.branchName)}</span><span class="pg n"></span></div>
    </section>`;
  const cv = study.conventional; const pt = study.post_tension;
  const row = (label, a, bb) => `<div class="r"><span>${esc(label)}</span><span class="n">${c.n2(a)}</span><span class="n">${c.n2(bb)}</span><span class="n ${a - bb >= 0 ? 'good' : 'bad'}">${a - bb >= 0 ? '−' : '+'}${c.n2(Math.abs(a - bb))}</span></div>`;
  const drawings = [...c.drawings('original').slice(0, 1), ...c.drawings('post_tension').slice(0, 1)];

  const css = `${BASE_CSS(c)}
    @page { size: 297mm 167mm; margin: 0; }
    body { background: #2b2f38; }
    .slide { position: relative; width: 297mm; height: 167mm; margin: 8mm auto; background: #faf6ef; color: #1f2937; overflow: hidden; padding: 16mm 18mm 14mm; display: flex; flex-direction: column; break-after: page; }
    .slide.dark { background: #1f2937; color: #fff; }
    .kick { font-family: 'Inter', ${c.font}; font-size: 10pt; letter-spacing: .22em; color: #c9761a; font-weight: 700; }
    .slide.dark .kick { color: #f2c879; }
    h1 { font-size: 30pt; font-weight: 900; line-height: 1.25; margin: 8px 0 0; max-width: 170mm; }
    .lead { font-size: 12.5pt; color: #4b5563; margin-top: 8px; max-width: 150mm; line-height: 1.7; }
    .slide.dark .lead { color: #d1d5db; }
    .sky { position: absolute; right: 0; bottom: 0; width: 150mm; height: 100%; opacity: .95; }
    /* The skyline is decoration: the words and the page number sit above it. */
    .sky { z-index: 0; } .slide > *:not(.sky) { position: relative; z-index: 1; }
    .two { display: grid; grid-template-columns: 1fr 1fr; gap: 18mm; margin-top: 12mm; }
    .big { font-size: 34pt; font-weight: 800; line-height: 1; }
    .two p { font-size: 11.5pt; color: #4b5563; line-height: 1.7; margin: 6px 0 0; max-width: 100mm; }
    .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10mm; margin-top: 12mm; }
    .three .big { color: #1f2937; } .three .k { font-size: 10pt; color: #4b5563; margin-top: 4px; }
    .cmp { margin-top: 10mm; display: grid; gap: 6px; font-size: 12pt; }
    .cmp .r { display: grid; grid-template-columns: 1fr 34mm 34mm 34mm; padding: 6px 0; border-bottom: 1px solid #e2d9c8; }
    .cmp .r.h { color: #6b7280; font-size: 9.5pt; font-weight: 700; }
    .cmp .r.t { font-weight: 800; border-bottom: 0; border-top: 2px solid #c9761a; }
    .cmp .n { text-align: center; }
    .number { margin-top: auto; display: flex; justify-content: space-between; align-items: flex-end; }
    .number .big { font-size: 56pt; color: #f2c879; }
    .number .s { font-size: 12pt; color: #d1d5db; }
    .draws { display: grid; grid-template-columns: 1fr 1fr; gap: 10mm; margin-top: 8mm; flex: 1; min-height: 0; }
    .draws figure { margin: 0; display: flex; flex-direction: column; min-height: 0; }
    .draws img { width: 100%; flex: 1; min-height: 0; object-fit: contain; background: #fff; border: 1px solid #e2d9c8; }
    .draws figcaption { font-size: 10pt; color: #4b5563; margin-top: 4px; }
    .sfoot { margin-top: auto; padding-top: 6mm; display: flex; justify-content: space-between; font-size: 9pt; color: #9ca3af; }
    .contact { margin-top: 10mm; font-size: 12pt; color: #4b5563; line-height: 1.9; }
    @media print { body { background: #fff; } .slide { margin: 0; } }
  `;
  const body = `
    ${slide('s1', T.story_1_k, `${skyline}<h1 ${ed.mark('s1.h')}>${ed.txt('s1.h', T.story_1_h(s.floors, c.n0(b.weight_saved_ton)))}</h1><div class="lead" ${ed.mark('s1.p')}>${ed.txt('s1.p', T.story_1_p)}</div><div class="lead" style="margin-top:auto;font-size:10.5pt;color:#9ca3af">${esc(c.projectName)} · ${esc(c.customerName)}</div>`, 'dark')}
    ${slide('s2', T.story_2_k, `<div class="two">
      <div><div class="big n">${c.n0(b.days_saved)} ${esc(T.days_word)}</div><p ${ed.mark('s2.days')}>${ed.txt('s2.days', T.story_2_days)}</p><p class="n" style="font-size:9.5pt;color:#9ca3af">${c.n0(s.pt_cycle_days)} ${esc(T.instead_of)} ${c.n0(s.conv_cycle_days)} ${esc(T.day)} ${esc(T.per_floor)}</p></div>
      <div><div class="big n">${c.n0(b.height_saved_mm)} ${esc(T.mm)}</div><p ${ed.mark('s2.height')}>${ed.txt('s2.height', T.story_2_height)}</p><p class="n" style="font-size:9.5pt;color:#9ca3af">${c.n0(b.thickness_saved_mm)} ${esc(T.mm)} × ${s.floors} ${esc(T.floor_word)}</p></div>
    </div>`)}
    ${slide('s3', T.story_3_k, `<h1 ${ed.mark('s3.h')}>${ed.txt('s3.h', T.story_3_h)}</h1><div class="three">
      <div><div class="big n">${c.n0(b.concrete_saved_m3)} m³</div><div class="k">${esc(T.concrete_saved)}</div></div>
      <div><div class="big n">${c.n2(b.rebar_saved_ton)} t</div><div class="k">${esc(T.rebar_saved)}</div></div>
      <div><div class="big n">${c.n0(b.weight_saved_ton)} t</div><div class="k">${esc(T.weight_saved)}</div></div>
    </div>`)}
    ${slide('s4', T.story_4_k, `<h1 ${ed.mark('s4.h')}>${ed.txt('s4.h', T.story_4_h)}</h1><div class="cmp">
      <div class="r h"><span>${esc(T.item)}</span><span class="n">${esc(T.conventional)}</span><span class="n">${esc(T.pt)}</span><span class="n">${esc(T.diff)}</span></div>
      ${row(T.concrete, cv.concrete, pt.concrete)}${row(T.rebar, cv.rebar, pt.rebar)}${row(T.formwork, cv.formwork, pt.formwork)}${row(T.pt_package, cv.post_tension, pt.post_tension)}
      <div class="r t"><span>${esc(T.total_sqm)}</span><span class="n">${c.n2(cv.per_sqm)}</span><span class="n">${c.n2(pt.per_sqm)}</span><span class="n ${sv.slab_per_sqm >= 0 ? 'good' : 'bad'}">${sv.slab_per_sqm >= 0 ? '−' : '+'}${c.n2(Math.abs(sv.slab_per_sqm))}</span></div>
    </div>`)}
    ${slide('s5', T.story_5_k, `<h1 ${ed.mark('s5.h')}>${ed.txt('s5.h', T.the_number)}</h1><div class="lead" ${ed.mark('s5.p')}>${ed.txt('s5.p', `${T.slab_diff}: ${c.cash(sv.slab_total)} · ${T.foundation}: ${c.cash(sv.foundation_total)} · ${T.programme}: ${c.cash(sv.programme_total)}`)}</div>
      <div class="number"><div class="s">${esc(T.net)} · ${c.n2(sv.pct)}% ${esc(T.of_conventional)}</div><div class="big n">${c.cash(sv.total)}</div></div>`, 'dark')}
    ${drawings.length ? slide('s6', T.story_6_k, `<h1 ${ed.mark('s6.h')}>${ed.txt('s6.h', T.drawings)}</h1><div class="draws">${drawings.map((d) => `<figure><img src="${esc(d.url)}" alt=""><figcaption>${esc(c.caption(d) || (d.kind === 'original' ? T.original : T.proposed))}</figcaption></figure>`).join('')}</div>`) : ''}
    ${slide('s7', T.story_7_k, `<h1 ${ed.mark('s7.h')}>${ed.txt('s7.h', T.story_7_h)}</h1><div class="lead" ${ed.mark('s7.p')}>${ed.txt('s7.p', T.story_7_p)}</div>
      <div class="contact">${esc(c.branchName)}<br>${esc([c.branch.phone, c.branch.email, c.branch.website].filter(Boolean).join(' · '))}<br><span class="n">${esc(c.ref)}</span></div>`)}
  `;
  return { css, body };
}

const RENDERERS = { report, compare, infographic, dashboard, story };
const PRESENTABLE = new Set(['story']);

/**
 * Opens the study in the chosen design. `data` is what the study screen
 * assembles for printing: the computed study, the drawings, the quotation
 * document, the company and branch, and the origin for saving edits.
 */
export function printStudyDesign(data, lang = 'ar', design = 'deck') {
  if (!RENDERERS[design]) {
    printStudy(data, lang);
    return;
  }
  const edits = (data.study.input && data.study.input.deck) || {};
  const ed = createEditor(edits, design);
  const c = context(data, lang, ed);
  const { css, body } = RENDERERS[design](c);
  const apiBase = String(data.origin || '').replace(/\/+$/, '');
  openDocument({
    lang,
    title: `${c.T.title} — ${c.projectName}`,
    css,
    body,
    editor: ed,
    existingText: edits.text || {},
    api: apiBase && data.quotation_id ? `${apiBase}/api/quotations/${Number(data.quotation_id)}/study/deck` : '',
    presentable: PRESENTABLE.has(design),
  });
}
