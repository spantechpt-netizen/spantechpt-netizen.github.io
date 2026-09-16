/**
 * Default content for the Span Tech quotation document.
 *
 * Everything here is a *default*: it is copied into each quotation when the
 * quotation is created, and can then be edited per quotation without affecting
 * other offers. Company-wide defaults are editable from Settings → Templates.
 */

// ------------------------------------------------------------ company profile
export const COMPANY = {
  // --- brand, shared across every country -----------------------------------
  name_en: 'SPAN TECH Contracting & Post Tensioning',
  name_ar: 'شركة سبان تك للمقاولات',
  legal_form_ar: 'شركة ذات مسؤولية محدودة',
  legal_form_en: 'Limited Liability Company',
  tagline_en: 'General Contracting & Post-Tensioned Slabs',
  tagline_ar: 'للمقاولات العامة والأسقف سابقة الإجهاد',

  /**
   * Per-country details. A quotation prints the branch matching its own
   * country, so a Saudi offer carries the Saudi CR and address while an
   * Egyptian one carries the Cairo office — from a single set of settings.
   * A country with nothing filled in falls back to `default_branch`.
   */
  default_branch: 'SA',
  branches: {
    SA: {
      name_en: 'SPAN TECH Contracting & Post Tensioning',
      name_ar: 'شركة سبان تك للمقاولات',
      logo: '/assets/img/logo@2x.png',
      registration_label_ar: 'سجل تجاري',
      registration_label_en: 'CR',
      cr_number: '7038269549',
      vat_number: '',
      phone: '0504291572',
      email: 'Info@spantechksa.com',
      email_alt: '',
      website: 'www.spantechksa.com',
      address_en: 'Riyadh, Kingdom of Saudi Arabia',
      address_ar: 'الرياض، المملكة العربية السعودية',
    },
    EG: {
      name_en: 'SPAN TECH Contracting & Post Tensioning',
      name_ar: 'شركة سبان تك للمقاولات',
      logo: '/assets/img/logo@2x.png',
      registration_label_ar: 'سجل تجاري',
      registration_label_en: 'CR',
      cr_number: '',
      vat_number: '',
      phone: '+20 100 9896731',
      email: 'Info@spantechpt.com',
      email_alt: '',
      website: 'www.spantechpt.com',
      address_en: 'Villa 119, Al Banafseg, M. Naguib St., New Cairo',
      address_ar: 'فيلا 119، البنفسج، شارع محمد نجيب، القاهرة الجديدة',
    },
    // Qatar trades under its own name and its own mark, so the letterhead
    // there is not the Saudi one with a different phone number on it.
    QA: {
      name_en: 'SPAN TEC Trading & Contracting',
      name_ar: 'سبان تك للتجارة والمقاولات العامة',
      logo: '/assets/img/logo-qa@2x.png',
      registration_label_ar: 'السجل التجاري',
      registration_label_en: 'C.R.',
      cr_number: '175473',
      vat_number: '',
      phone: '+974 60008582',
      email: 'sales@spantec-qa.com',
      email_alt: 'finance@spantec-qa.com',
      website: 'www.spantechpt.com',
      address_en: 'Doha, Qatar',
      address_ar: 'الدوحة – قطر',
    },
  },

  vision_en: 'Leadership in the contracting sector through quality and commitment.',
  vision_ar: 'الريادة في قطاع المقاولات من خلال الجودة والالتزام.',
  mission_en: 'To deliver projects that satisfy our clients and add real value to the community.',
  mission_ar: 'تنفيذ مشاريع تحقق رضا عملائنا وتضيف قيمة حقيقية للمجتمع.',
  profile_en: [
    'Execution of structural works and post-tensioned slabs (Post-Tension).',
    'Full compliance with quality and safety systems per the Saudi Building Code (SBC) and international codes (ACI / ASTM).',
    'Proven record across residential towers, schools, commercial malls and administrative buildings throughout the region.',
    'Qualified engineering and technical staff with certified stressing and grouting equipment.',
  ],
  profile_ar: [
    'تنفيذ الأعمال الإنشائية والأسقف اللاحقة للشد (Post-Tension).',
    'التزام كامل بأنظمة الجودة والسلامة طبقاً للكود السعودي (SBC) والأكواد العالمية (ACI / ASTM).',
    'سجل حافل في الأبراج السكنية والمدارس والمولات التجارية والمباني الإدارية في مختلف المناطق.',
    'كوادر هندسية وفنية مؤهلة ومعدات شد وحقن معتمدة.',
  ],
};

/** The branch to print on a document for `country`, with sensible fallbacks. */
export function branchFor(company, country) {
  const branches = company?.branches || COMPANY.branches;
  const fallbackKey = company?.default_branch || COMPANY.default_branch || 'SA';
  const branch = branches?.[country];
  const fallback = branches?.[fallbackKey] || COMPANY.branches.SA;
  // Legal identifiers are country-specific: a Saudi commercial registration
  // must never appear on an Egyptian document, so these never inherit.
  const NEVER_INHERIT = ['cr_number', 'vat_number'];
  if (!branch) {
    const blank = { ...fallback };
    for (const key of NEVER_INHERIT) blank[key] = '';
    return blank;
  }
  // Everything else falls back, so a branch with no phone yet still prints a
  // usable letterhead instead of a blank.
  const merged = { ...fallback };
  for (const key of NEVER_INHERIT) merged[key] = '';
  for (const [key, value] of Object.entries(branch)) {
    if (value !== null && value !== undefined && value !== '') merged[key] = value;
  }
  return merged;
}

// ------------------------------------------------------------- scope of work
export const SCOPE = {
  design: {
    title_en: 'Design',
    title_ar: 'التصميم',
    items: [
      {
        en: 'Modelling and design of post-tensioned slabs and beams in accordance with ACI 318-14 / IBC and the consultant’s recommendations.',
        ar: 'إعداد نمذجة وتصميم بلاطات وكمرات لاحقة الشد طبقاً لـ (ACI 318-14 / IBC) وتوصيات الاستشاري.',
      },
      { en: 'Design loads as shown on the drawings issued to us.', ar: 'الأحمال التصميمية كما هو موضح في اللوحات المرسلة إلينا.' },
      { en: 'The design is based on a post-tensioned concrete system compliant with all applicable international codes and standards.', ar: 'يعتمد التصميم على نظام الخرسانة اللاحقة للشد المتوافق مع جميع الأكواد والمعايير الدولية.' },
      { en: 'Minimum permissible concrete compressive strength: 35 MPa.', ar: 'إجهاد الخرسانة الأدنى المسموح به 35 ميجا باسكال (MPa).' },
      { en: 'Approximate conventional reinforcement ratio: 50–55 kg per m³ of concrete.', ar: 'نسبة التسليح التقليدي التقريبية 50–55 كجم/م³ من الخرسانة.' },
      { en: 'The design is submitted to the consultant for review and approval prior to execution.', ar: 'يتم مراجعة التصميم من الاستشاري واعتماده قبل التنفيذ.' },
    ],
  },
  supply: {
    title_en: 'Supply',
    title_ar: 'التوريد',
    items: [
      { en: 'Strands: 12.70 mm diameter, 1860 MPa ultimate tensile strength, conforming to ASTM A416.', ar: 'الكابلات (Strands): قطر 12.70 مم، مقاومة شد 1860 ميجا باسكال، مطابقة لمعيار ASTM A416.' },
      { en: 'Anchorages and wedges: European SARI system.', ar: 'الأنكورات والرؤوس (Anchorages): نظام SARI الأوروبي.' },
      { en: 'Ducts: high quality corrugated galvanized sheet.', ar: 'الجرابات (Ducts): صاج مشرشر عالي الجودة.' },
      { en: 'Grouting materials: conforming to ASTM C1107 requirements.', ar: 'مستلزمات الحقن (Grouting Materials): مطابقة لمتطلبات ASTM C1107.' },
      { en: 'Stressing and grouting equipment: certified hydraulic equipment, complete with calibrated gauges and recording devices.', ar: 'معدات الشد والحقن: هيدروليكية معتمدة، كاملة بأجهزة القياس والتسجيل المعايرة.' },
    ],
  },
  installation: {
    title_en: 'Installation & Testing',
    title_ar: 'التركيب والاختبارات',
    items: [
      { en: 'Setting out of tendon positions and marking of profiles after completion of slab formwork.', ar: 'تحديد مواقع الكابلات ووضع علامات المسارات بعد الانتهاء من أعمال نجارة السقف.' },
      { en: 'Laying and installation of tendons per the approved shop drawings, after completion of the bottom reinforcement layer.', ar: 'فرد وتركيب الكابلات حسب المخططات التنفيذية المعتمدة بعد الانتهاء من طبقة الحديد السفلية.' },
      { en: 'Stressing of tendons to the required forces with accurate recording of elongations, once the concrete reaches 75% of the specified strength.', ar: 'شد الكابلات بالقوى المطلوبة وتسجيل قراءات الاستطالة بدقة بعد وصول الخرسانة إلى 75% من الإجهاد التصميمي.' },
      { en: 'Submission of stressing reports for the consultant’s approval.', ar: 'تقديم تقارير الشد (Tensioning) لاعتمادها من الاستشاري.' },
      { en: 'Issue of a No-Objection letter for striking of formwork and props after completion of stressing.', ar: 'إصدار خطاب عدم ممانعة لفك الشدات والدعامات بعد الانتهاء من عملية الشد.' },
      { en: 'Cutting of surplus strand after approval of the stressing report.', ar: 'تقطيع الكابلات الزائدة بعد اعتماد تقرير الشد.' },
      { en: 'Grouting of ducts with approved grout per the standards, with confirmed sealing of grout vents, within a maximum of 10 days after casting.', ar: 'حقن الكابلات بمونة معتمدة طبقاً للمعايير والتأكد من إحكام غلق خراطيم الحقن، في مدة أقصاها 10 أيام بعد الصب.' },
    ],
  },
  deliverables: {
    title_en: 'Deliverables',
    title_ar: 'الوثائق المقدمة',
    items: [
      { en: 'Shop drawings and design calculations.', ar: 'المخططات التنفيذية (Shop Drawings) وحسابات التصميم.' },
      { en: 'Inspection and Test Plans (ITPs) and Method Statement.', ar: 'خطط الفحص والاختبار (ITPs) وطريقة العمل (Method Statement).' },
      { en: 'Stressing and grouting reports, plus as-built drawings.', ar: 'تقارير الشد والحقن، بالإضافة إلى مخططات ما تم تنفيذه (As-Built).' },
      { en: 'Material certificates and mill test certificates for strands and anchorages.', ar: 'شهادات المواد وشهادات المصنع للكابلات والأنكورات.' },
      { en: 'Workmanship warranty certificate.', ar: 'شهادة ضمان تنفيذ الأعمال.' },
    ],
  },
  requirements: {
    title_en: 'By Main Contractor / Consultant (Prior to Commencement)',
    title_ar: 'متطلبات من المقاول الرئيسي / الاستشاري قبل البدء',
    items: [
      { en: 'Latest revision of all drawings (architectural + structural + MEP).', ar: 'تزويدنا بآخر الإصدارات من المخططات (معمارية + إنشائية + MEP).' },
      { en: 'Final load schedule, openings and expansion joint locations.', ar: 'تزويدنا بجدول الأحمال والفتحات وفواصل التمدد النهائية.' },
      { en: 'Air-conditioned office for the supervision team.', ar: 'توفير مكتب مكيف لطاقم الإشراف.' },
      { en: 'Power supply (415/380V – 3 Phase, 240V – 2 Phase) and water at site.', ar: 'توفير مصدر كهرباء (415/380 فولت – 3 فاز، 240 فولت – 2 فاز) ومياه في الموقع.' },
      { en: 'Supply of grouting cement, grout admixture and water used in grouting works.', ar: 'توفير أسمنت الحقن ومادة الحقن والمياه المستخدمة في أعمال الحقن.' },
      { en: 'Secure material storage area and adequate working space.', ar: 'توفير مكان تخزين آمن للمواد ومساحات عمل كافية.' },
      { en: 'Scaffolding during stressing, or plywood decking extended 1 m beyond the slab edge in the stressing direction.', ar: 'توفير السقالات اللازمة أثناء عملية الشد، أو تطريح البليوود بمقدار 1 متر خارج حدود السقف في اتجاه الشد.' },
      { en: 'Supply and casting of ready-mix concrete and follow-up of cube tests until the specified f’c is achieved.', ar: 'توريد وصب الخرسانة الجاهزة ومتابعة اختبارات المكعبات حتى تحقيق f’c المطلوب.' },
      { en: 'Supply of conventional reinforcement steel, formwork and steel props.', ar: 'توريد حديد التسليح التقليدي والقوالب والشدات المعدنية.' },
      { en: 'Supply and installation of tendon support chairs, with legs painted with zinc-rich primer for corrosion protection.', ar: 'توريد وتركيب كراسي تثبيت الكابلات، مع دهان الأرجل بمادة الزنكريتش للحماية من التآكل.' },
      { en: 'Supply of anchorage back-up reinforcement (helices / spirals).', ar: 'توريد حديد دعم الأنكورات (السوست).' },
      { en: 'Fabrication of timber pocket formers by the carpenter, and patching of anchorage pockets after stressing is complete.', ar: 'تصنيع الصناديق الخشبية بواسطة النجار، بالإضافة إلى تنفيذ أعمال التلبيش للفتحات بعد إتمام عملية الشد.' },
      { en: 'Vertical and horizontal transportation within the site.', ar: 'النقل الرأسي والأفقي داخل الموقع.' },
    ],
  },
  exclusions: {
    title_en: 'Exclusions',
    title_ar: 'الأعمال غير المشمولة',
    items: [
      { en: 'Concrete supply, casting, curing and cube testing.', ar: 'توريد وصب الخرسانة ومعالجتها واختبارات المكعبات.' },
      { en: 'Conventional reinforcement supply, cutting, bending and fixing.', ar: 'توريد وقص وثني وتركيب حديد التسليح التقليدي.' },
      { en: 'Formwork, falsework, props and scaffolding.', ar: 'الشدات والقوالب والدعامات والسقالات.' },
      { en: 'Taxes, government fees, permits and municipality charges.', ar: 'الضرائب والرسوم الحكومية والتصاريح ورسوم البلدية.' },
      { en: 'Any works not explicitly listed in the scope of work above.', ar: 'أي أعمال غير مذكورة صراحة في نطاق العمل أعلاه.' },
    ],
  },
  warranty: {
    title_en: 'Warranty & Quality Assurance',
    title_ar: 'الضمانات وجودة التنفيذ',
    items: [
      { en: 'Commitment to deliver the works in full compliance with the consultant’s and owner’s requirements.', ar: 'الالتزام بتسليم الأعمال مطابقة لمتطلبات الاستشاري والمالك.' },
      { en: 'Ten (10) year warranty on the post-tensioning works against any defect in materials or workmanship, from the date of final handover.', ar: 'تقديم ضمان كامل لأعمال البوست تنشن ضد أي عيوب في المواد أو التنفيذ لمدة عشر (10) سنوات من تاريخ التسليم النهائي.' },
      { en: 'All materials used (strands, anchorages, ducts, grout) are warranted against approved conformity certificates and test reports.', ar: 'ضمان المواد المستخدمة (الكابلات، الأنكورات، الجرابات، مادة الحقن) وفق شهادات المطابقة والاختبارات المعتمدة.' },
    ],
  },
  schedule: {
    title_en: 'Programme',
    title_ar: 'الجدول الزمني',
    items: [
      { en: 'A detailed programme covering design, supply and execution stages will be issued in coordination with the master project schedule.', ar: 'تقديم برنامج زمني تفصيلي يشمل مراحل التصميم والتوريد والتنفيذ بالتنسيق مع جدول المشروع العام.' },
      { en: 'The execution duration per slab depends on the slab area and the concrete pouring schedule.', ar: 'مدة التنفيذ لكل سقف تعتمد على مساحة البلاطة وجدولة صب الخرسانة.' },
      { en: 'Our objective: to complete our works without delaying any other structural activity on site.', ar: 'هدفنا: إنجاز الأعمال دون تأخير أي بند إنشائي آخر في الموقع.' },
    ],
  },
  team: {
    title_en: 'Project Team',
    title_ar: 'فريق العمل',
    items: [
      { en: 'Project Engineer — responsible for full coordination and liaison with the consultant and main contractor.', ar: 'مهندس المشروع — مسؤول عن التنسيق الكامل والاتصال بالاستشاري والمقاول الرئيسي.' },
      { en: 'Foreman — direct supervision of the technical crews to ensure accurate and efficient execution.', ar: 'فورمان — إشراف مباشر على فرق العمالة الفنية لضمان تنفيذ الأعمال بدقة وكفاءة.' },
      { en: 'Certified stressing technicians and a QA/QC engineer for testing and documentation.', ar: 'فنيو شد معتمدون ومهندس جودة لأعمال الاختبارات والتوثيق.' },
    ],
  },
};

// --------------------------------------------------------------- commercials
export const PAYMENT_TERMS = [
  { pct: 30, en: 'Advance payment upon signing of the contract.', ar: 'دفعة مقدمة عند توقيع العقد.' },
  { pct: 40, en: 'On delivery of materials to site (released in instalments against delivered quantities).', ar: 'عند توريد المواد للموقع (تصرف على دفعات حسب الكميات الموردة).' },
  { pct: 30, en: 'Against monthly invoices based on progress, after completion of stressing works.', ar: 'تصرف بمستخلصات شهرية حسب نسب الإنجاز بعد الانتهاء من أعمال الشد.' },
];

export const CONDITIONS = [
  { en: 'Prices exclude VAT and any government fees.', ar: 'الأسعار لا تشمل ضريبة القيمة المضافة أو أي رسوم حكومية.' },
  { en: 'Payments shall be settled within seven (7) days from the date of submitting the works invoice.', ar: 'يجب سداد الدفعات خلال سبعة (7) أيام من تاريخ تقديم مستخلص الأعمال.' },
  { en: 'Delay of payment beyond ten (10) days may lead to suspension of works without any time or cost liability on Span Tech.', ar: 'قد يؤدي تأخير الدفعات لأكثر من عشرة (10) أيام إلى تعليق الأعمال دون تحمل أي تبعات زمنية أو مالية على سبان تك.' },
  { en: 'No retention shall be applied to this contract.', ar: 'لا يوجد أي مبالغ محتجزة (Retention) على هذا العقد.' },
  { en: 'This offer is based on the drawings issued to us; any change in layout, loads or slab thickness requires re-pricing.', ar: 'هذا العرض مبني على المخططات المرسلة إلينا؛ وأي تغيير في التوزيع أو الأحمال أو سماكة البلاطة يستوجب إعادة التسعير.' },
  { en: 'Should cube test results fail to achieve the specified design strength, stressing works will be suspended until the required results are achieved; the main contractor bears any resulting delay or recasting.', ar: 'في حال فشل مكعبات الخرسانة في تحقيق مقاومة التصميم المطلوبة، يتم تعليق أعمال الشد حتى تحقيق النتائج المطلوبة، ويتحمل المقاول الرئيسي أي تأخير أو إعادة صب ناتج عن ذلك.' },
];

/** Placeholders `{variance}`, `{price}`, `{currency}` are substituted at render time. */
export const PRICE_ADJUSTMENT_CLAUSE = {
  en: 'Prices are based on the current strand price of {price} {currency} per ton. Should the strand price vary by more than ±{variance}% from this figure, both parties are entitled to renegotiate the total price.',
  ar: 'الأسعار مبنية على سعر الكابلات الحالي {price} {currency} للطن. وفي حال تغير سعر الكابلات بنسبة تتجاوز ±{variance}% عن هذا السعر، يحق للطرفين إعادة التفاوض على السعر الإجمالي.',
};

export const INTRO = {
  en: 'Span Tech Contracting Co. is pleased to submit this offer for the design, supply and execution of the post-tensioned slab works for {project}, in accordance with the highest quality standards and approved technical specifications, and in compliance with the Saudi and international codes (SBC / ACI / ASTM).',
  ar: 'تتشرف شركة سبان تك للمقاولات والأسقف اللاحقة للشد (Post-Tension) بتقديم هذا العرض لتنفيذ أعمال الأسقف اللاحقة للشد الخاصة بمشروع {project}، وذلك وفق أعلى معايير الجودة والمواصفات الفنية المعتمدة، وبما يتوافق مع الأكواد السعودية والعالمية (SBC / ACI / ASTM).',
};

// ------------------------------------------------------------ country pricing
/**
 * Per-country commercial defaults. Review these in Settings → Price book
 * before issuing offers — material prices move.
 */
export const COUNTRY_DEFAULTS = {
  SA: {
    name_en: 'Saudi Arabia', name_ar: 'المملكة العربية السعودية',
    currency: 'SAR', currency_en: 'SAR', currency_ar: 'ريال', currency_word_ar: 'ريال سعودي',
    vat_rate: 15, valid_days: 10,
    strand_price_ton: 4000, strand_kg_sqm: 3.5, anchors_per_ton: 25,
    default_price_sqm: 70, floor_price_sqm: 58,
  },
  EG: {
    name_en: 'Egypt', name_ar: 'جمهورية مصر العربية',
    currency: 'EGP', currency_en: 'EGP', currency_ar: 'جنيه', currency_word_ar: 'جنيه مصري',
    vat_rate: 14, valid_days: 10,
    strand_price_ton: 75000, strand_kg_sqm: 3.5, anchors_per_ton: 25,
    default_price_sqm: 900, floor_price_sqm: 750,
  },
  QA: {
    name_en: 'Qatar', name_ar: 'دولة قطر',
    currency: 'QAR', currency_en: 'QAR', currency_ar: 'ريال', currency_word_ar: 'ريال قطري',
    vat_rate: 0, valid_days: 15,
    strand_price_ton: 4200, strand_kg_sqm: 3.5, anchors_per_ton: 25,
    default_price_sqm: 75, floor_price_sqm: 62,
  },
};

export const CURRENCY_WORDS = {
  SAR: { en: ['Saudi Riyal', 'Halalas'], ar: ['ريال سعودي', 'هللة'] },
  EGP: { en: ['Egyptian Pound', 'Piastres'], ar: ['جنيه مصري', 'قرش'] },
  QAR: { en: ['Qatari Riyal', 'Dirhams'], ar: ['ريال قطري', 'درهم'] },
  USD: { en: ['US Dollar', 'Cents'], ar: ['دولار أمريكي', 'سنت'] },
};

export const DEFAULT_ITEM = {
  desc_en: 'Design, supply and execution of post-tensioned slab works',
  desc_ar: 'تصميم وتوريد وتنفيذ أعمال الأسقف اللاحقة للشد',
  unit_en: 'm²',
  unit_ar: 'م²',
};

/** Deep copy so callers can freely mutate the defaults they receive. */
export const cloneDefaults = () => ({
  scope: JSON.parse(JSON.stringify(SCOPE)),
  payment_terms: JSON.parse(JSON.stringify(PAYMENT_TERMS)),
  conditions: JSON.parse(JSON.stringify(CONDITIONS)),
});
