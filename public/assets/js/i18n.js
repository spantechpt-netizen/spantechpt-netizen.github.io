/**
 * Bilingual dictionary. Every visible string lives here so the whole
 * interface can flip between Arabic (RTL) and English (LTR) instantly.
 */
export const DICT = {
  ar: {
    // --- shell -------------------------------------------------------------
    app_name: 'سبان تك', app_subtitle: 'إدارة العملاء وعروض الأسعار',
    nav_dashboard: 'لوحة التحكم', nav_customers: 'العملاء', nav_pipeline: 'الفرص',
    nav_activities: 'المتابعات', nav_quotations: 'عروض الأسعار',
    nav_analytics: 'التحليلات', nav_settings: 'الإعدادات',
    sign_out: 'تسجيل الخروج', my_profile: 'حسابي', language: 'اللغة',
    loading: 'جارٍ التحميل…', no_data: 'لا توجد بيانات',
    search: 'بحث', filter: 'تصفية', all: 'الكل', clear: 'مسح',
    save: 'حفظ', cancel: 'إلغاء', close: 'إغلاق', delete: 'حذف', edit: 'تعديل',
    add: 'إضافة', create: 'إنشاء', open: 'فتح', back: 'رجوع', actions: 'إجراءات',
    confirm_delete: 'هل أنت متأكد من الحذف؟ لا يمكن التراجع عن هذا الإجراء.',
    saved: 'تم الحفظ بنجاح', deleted: 'تم الحذف', error: 'حدث خطأ',
    required_field: 'حقل مطلوب', optional: 'اختياري', none: 'لا يوجد',
    yes: 'نعم', no: 'لا', total: 'الإجمالي', print: 'طباعة', export: 'تصدير',
    copy: 'نسخ', copied: 'تم النسخ',

    // --- auth --------------------------------------------------------------
    login_title: 'تسجيل الدخول', email: 'البريد الإلكتروني',
    password: 'كلمة المرور', login: 'دخول',
    login_welcome: 'نظام إدارة العملاء وعروض الأسعار',
    current_password: 'كلمة المرور الحالية', new_password: 'كلمة المرور الجديدة',
    change_password: 'تغيير كلمة المرور', password_changed: 'تم تغيير كلمة المرور',
    password_min: 'الحد الأدنى 8 أحرف',

    // --- dashboard ---------------------------------------------------------
    dashboard: 'لوحة التحكم', welcome: 'أهلاً', today: 'اليوم',
    kpi_open_pipeline: 'الفرص المفتوحة', kpi_weighted: 'القيمة المرجحة',
    kpi_win_rate: 'نسبة الفوز', kpi_quotes_sent: 'عروض هذا العام',
    kpi_won_value: 'قيمة المشاريع المكتسبة', kpi_customers: 'العملاء',
    overdue: 'متأخرة', due_today: 'مستحقة اليوم', upcoming: 'قادمة',
    no_due_date: 'بدون تاريخ', follow_ups: 'المتابعات المطلوبة',
    recent_quotes: 'أحدث عروض الأسعار', top_opportunities: 'أهم الفرص',
    all_clear: 'لا توجد متابعات متأخرة — عمل ممتاز!',

    // --- customers ---------------------------------------------------------
    customers: 'العملاء', customer: 'العميل', new_customer: 'عميل جديد',
    customer_name_en: 'الاسم بالإنجليزية', customer_name_ar: 'الاسم بالعربية',
    customer_type: 'نوع العميل', country: 'الدولة', city: 'المدينة',
    sector: 'القطاع', website: 'الموقع الإلكتروني', phone: 'الهاتف',
    address: 'العنوان', tax_number: 'الرقم الضريبي', cr_number: 'السجل التجاري',
    status: 'الحالة', source: 'مصدر العميل', rating: 'الأولوية',
    owner: 'المهندس المسؤول', notes: 'ملاحظات', contacts: 'جهات الاتصال',
    contact_name: 'الاسم', contact_title: 'المسمى الوظيفي', mobile: 'الجوال',
    primary_contact: 'جهة الاتصال الرئيسية', new_contact: 'جهة اتصال جديدة',
    my_customers: 'عملائي', all_customers: 'كل العملاء',
    opportunities_count: 'الفرص', quotations_count: 'العروض',

    type_main_contractor: 'مقاول رئيسي', type_consultant: 'استشاري',
    type_developer: 'مطور عقاري', type_owner: 'مالك',
    type_subcontractor: 'مقاول باطن', type_government: 'جهة حكومية', type_other: 'أخرى',

    status_target: 'عميل مستهدف', status_prospect: 'عميل محتمل',
    status_active: 'عميل نشط', status_dormant: 'غير نشط', status_blacklisted: 'محظور',

    source_referral: 'ترشيح', source_website: 'الموقع الإلكتروني',
    source_exhibition: 'معرض', source_cold_call: 'اتصال مباشر',
    source_existing: 'عميل حالي', source_tender: 'مناقصة', source_social: 'تواصل اجتماعي',

    sector_residential: 'سكني', sector_commercial: 'تجاري', sector_education: 'تعليمي',
    sector_healthcare: 'صحي', sector_industrial: 'صناعي',
    sector_infrastructure: 'بنية تحتية', sector_mixed: 'متعدد الاستخدام',

    // --- pipeline ----------------------------------------------------------
    pipeline: 'الفرص', opportunity: 'الفرصة', new_opportunity: 'فرصة جديدة',
    opportunity_title: 'اسم المشروع', project_type: 'نوع المشروع',
    area_sqm: 'المساحة (م²)', stage: 'المرحلة', probability: 'احتمالية الفوز',
    expected_value: 'القيمة المتوقعة', currency: 'العملة',
    expected_close: 'تاريخ الإغلاق المتوقع', lost_reason: 'سبب الخسارة',
    lost_to: 'المنافس الفائز', my_opportunities: 'فرصي', all_opportunities: 'كل الفرص',
    board_view: 'عرض المراحل', list_view: 'عرض القائمة',

    stage_new: 'جديدة', stage_qualified: 'مؤهلة', stage_quoted: 'تم التسعير',
    stage_negotiation: 'تفاوض', stage_won: 'مكتسبة', stage_lost: 'خسارة',

    ptype_tower: 'برج', ptype_school: 'مدرسة', ptype_mall: 'مول تجاري',
    ptype_villa: 'فيلا', ptype_rest_house: 'استراحة', ptype_admin: 'مبنى إداري',
    ptype_hospital: 'مستشفى', ptype_parking: 'مواقف', ptype_industrial: 'صناعي',
    ptype_other: 'أخرى',

    reason_price: 'السعر', reason_timing: 'التوقيت', reason_competitor: 'منافس',
    reason_scope: 'نطاق العمل', reason_no_budget: 'لا توجد ميزانية',
    reason_no_response: 'لا يوجد رد', reason_other: 'أخرى',

    // --- activities --------------------------------------------------------
    activities: 'المتابعات', activity: 'متابعة', new_activity: 'متابعة جديدة',
    activity_type: 'النوع', subject: 'الموضوع', due_at: 'موعد المتابعة',
    mark_done: 'تم الإنجاز', done: 'منجزة', outcome: 'النتيجة',
    related_to: 'مرتبط بـ', my_activities: 'متابعاتي', all_activities: 'كل المتابعات',
    reopen: 'إعادة فتح',

    act_call: 'مكالمة', act_meeting: 'اجتماع', act_email: 'بريد إلكتروني',
    act_whatsapp: 'واتساب', act_site_visit: 'زيارة موقع', act_task: 'مهمة', act_note: 'ملاحظة',

    // --- quotations --------------------------------------------------------
    quotations: 'عروض الأسعار', quotation: 'عرض السعر', new_quotation: 'عرض سعر جديد',
    quote_number: 'رقم العرض', revision: 'المراجعة', issue_date: 'تاريخ الإصدار',
    valid_days: 'مدة السريان (يوم)', valid_until: 'ساري حتى',
    project_name: 'اسم المشروع', project_name_ar: 'اسم المشروع بالعربية',
    location: 'الموقع', attention: 'عناية السيد',
    subtotal: 'الإجمالي قبل الضريبة', discount: 'الخصم', net_amount: 'الصافي',
    vat: 'ضريبة القيمة المضافة', vat_rate: 'نسبة الضريبة %',
    grand_total: 'الإجمالي شامل الضريبة', unit_price: 'سعر الوحدة',
    quantity: 'الكمية', unit: 'الوحدة', description: 'البند', amount: 'القيمة',
    line_items: 'بنود العرض', add_item: 'إضافة بند', optional_item: 'بند اختياري',
    print_ar: 'طباعة النسخة العربية', print_en: 'طباعة النسخة الإنجليزية',
    duplicate: 'نسخ العرض', create_revision: 'إنشاء مراجعة',
    mark_sent: 'تحديد كمُرسل', mark_approved: 'اعتماد', mark_rejected: 'رفض',
    reject_reason: 'سبب الرفض', amount_in_words: 'المبلغ كتابة',

    qstatus_draft: 'مسودة', qstatus_sent: 'مُرسل', qstatus_under_review: 'قيد الدراسة',
    qstatus_approved: 'معتمد', qstatus_rejected: 'مرفوض',
    qstatus_expired: 'منتهي الصلاحية', qstatus_cancelled: 'ملغي',

    // --- pricing calculator -------------------------------------------------
    cost_calculator: 'حاسبة التكلفة', internal_only: 'للاستخدام الداخلي فقط',
    strand_price_ton: 'سعر الكابلات (للطن)', strand_kg_sqm: 'كجم كابلات لكل م²',
    anchors_per_ton: 'عدد الأنكورات لكل طن', anchor_cost: 'تكلفة الأنكور الواحد',
    duct_cost_sqm: 'تكلفة الجرابات /م²', grout_cost_sqm: 'تكلفة الحقن /م²',
    labour_cost_sqm: 'تكلفة العمالة /م²', design_cost_sqm: 'تكلفة التصميم /م²',
    overhead_pct: 'المصاريف العمومية %', target_margin: 'هامش الربح المستهدف %',
    price_variance: 'نسبة تغير سعر الكابلات ±%',
    strand_tons: 'إجمالي الكابلات (طن)', anchor_count: 'عدد الأنكورات',
    direct_cost: 'التكلفة المباشرة', cost_per_sqm: 'التكلفة /م²',
    price_per_sqm: 'السعر /م²', suggested_price: 'السعر المقترح /م²',
    margin: 'هامش الربح', margin_amount: 'قيمة الربح',
    below_cost_warning: 'تحذير: السعر أقل من التكلفة',
    below_target_warning: 'تنبيه: هامش الربح أقل من المستهدف',

    // --- analytics ---------------------------------------------------------
    analytics: 'التحليلات', period: 'الفترة', from: 'من', to: 'إلى',
    last_12_months: 'آخر 12 شهر', this_year: 'هذا العام', this_quarter: 'هذا الربع',
    conversion_funnel: 'مسار التحويل', by_country: 'حسب الدولة',
    by_engineer: 'حسب المهندس', by_source: 'حسب مصدر العميل',
    by_project_type: 'حسب نوع المشروع', loss_analysis: 'تحليل الخسائر',
    monthly_trend: 'الاتجاه الشهري', price_benchmark: 'متوسط سعر المتر',
    created: 'تم إنشاؤها', qualified: 'مؤهلة', quoted: 'مُسعّرة',
    negotiation: 'تفاوض', won: 'مكتسبة', lost: 'خسارة',
    avg_price: 'المتوسط', min_price: 'الأدنى', max_price: 'الأعلى',
    quotes_issued: 'العروض الصادرة', value_won: 'القيمة المكتسبة',
    conversion_rate: 'نسبة التحويل',

    // --- settings ----------------------------------------------------------
    settings: 'الإعدادات', company_profile: 'بيانات الشركة',
    price_book: 'جدول الأسعار', templates: 'قوالب العرض', users: 'المستخدمون',
    new_user: 'مستخدم جديد', role: 'الصلاحية', active: 'نشط', inactive: 'معطل',
    role_admin: 'مدير النظام', role_manager: 'مدير', role_engineer: 'مهندس',
    role_viewer: 'مشاهدة فقط',
    company_name_en: 'اسم الشركة بالإنجليزية', company_name_ar: 'اسم الشركة بالعربية',
    default_price: 'السعر الافتراضي /م²', floor_price: 'الحد الأدنى للسعر /م²',
    reset_defaults: 'استعادة الإعدادات الافتراضية',
    scope_design: 'التصميم', scope_supply: 'التوريد',
    scope_installation: 'التركيب والاختبارات', scope_deliverables: 'الوثائق المقدمة',
    scope_requirements: 'متطلبات المقاول الرئيسي', scope_exclusions: 'الأعمال غير المشمولة',
    scope_warranty: 'الضمانات', scope_schedule: 'الجدول الزمني', scope_team: 'فريق العمل',
    payment_terms: 'شروط الدفع', conditions: 'الشروط والأحكام',
    quote_prefix: 'بادئة رقم العرض', last_login: 'آخر دخول',

    // --- countries ---------------------------------------------------------
    country_SA: 'السعودية', country_EG: 'مصر', country_QA: 'قطر',
  },

  en: {
    app_name: 'Span Tech', app_subtitle: 'CRM & Quotations',
    nav_dashboard: 'Dashboard', nav_customers: 'Customers', nav_pipeline: 'Pipeline',
    nav_activities: 'Follow-ups', nav_quotations: 'Quotations',
    nav_analytics: 'Analytics', nav_settings: 'Settings',
    sign_out: 'Sign out', my_profile: 'My profile', language: 'Language',
    loading: 'Loading…', no_data: 'No records',
    search: 'Search', filter: 'Filter', all: 'All', clear: 'Clear',
    save: 'Save', cancel: 'Cancel', close: 'Close', delete: 'Delete', edit: 'Edit',
    add: 'Add', create: 'Create', open: 'Open', back: 'Back', actions: 'Actions',
    confirm_delete: 'Delete this record? This cannot be undone.',
    saved: 'Saved', deleted: 'Deleted', error: 'Something went wrong',
    required_field: 'Required', optional: 'optional', none: 'None',
    yes: 'Yes', no: 'No', total: 'Total', print: 'Print', export: 'Export',
    copy: 'Copy', copied: 'Copied',

    login_title: 'Sign in', email: 'Email address',
    password: 'Password', login: 'Sign in',
    login_welcome: 'Customer & Quotation Management',
    current_password: 'Current password', new_password: 'New password',
    change_password: 'Change password', password_changed: 'Password changed',
    password_min: 'Minimum 8 characters',

    dashboard: 'Dashboard', welcome: 'Welcome', today: 'Today',
    kpi_open_pipeline: 'Open pipeline', kpi_weighted: 'Weighted value',
    kpi_win_rate: 'Win rate', kpi_quotes_sent: 'Quotes this year',
    kpi_won_value: 'Won value', kpi_customers: 'Customers',
    overdue: 'Overdue', due_today: 'Due today', upcoming: 'Upcoming',
    no_due_date: 'No date', follow_ups: 'Follow-ups',
    recent_quotes: 'Latest quotations', top_opportunities: 'Top opportunities',
    all_clear: 'Nothing overdue — well done!',

    customers: 'Customers', customer: 'Customer', new_customer: 'New customer',
    customer_name_en: 'Name (English)', customer_name_ar: 'Name (Arabic)',
    customer_type: 'Customer type', country: 'Country', city: 'City',
    sector: 'Sector', website: 'Website', phone: 'Phone',
    address: 'Address', tax_number: 'VAT number', cr_number: 'CR number',
    status: 'Status', source: 'Source', rating: 'Priority',
    owner: 'Account engineer', notes: 'Notes', contacts: 'Contacts',
    contact_name: 'Name', contact_title: 'Job title', mobile: 'Mobile',
    primary_contact: 'Primary contact', new_contact: 'New contact',
    my_customers: 'My customers', all_customers: 'All customers',
    opportunities_count: 'Opportunities', quotations_count: 'Quotes',

    type_main_contractor: 'Main contractor', type_consultant: 'Consultant',
    type_developer: 'Developer', type_owner: 'Owner',
    type_subcontractor: 'Subcontractor', type_government: 'Government', type_other: 'Other',

    status_target: 'Target', status_prospect: 'Prospect',
    status_active: 'Active', status_dormant: 'Dormant', status_blacklisted: 'Blacklisted',

    source_referral: 'Referral', source_website: 'Website',
    source_exhibition: 'Exhibition', source_cold_call: 'Cold call',
    source_existing: 'Existing client', source_tender: 'Tender', source_social: 'Social media',

    sector_residential: 'Residential', sector_commercial: 'Commercial',
    sector_education: 'Education', sector_healthcare: 'Healthcare',
    sector_industrial: 'Industrial', sector_infrastructure: 'Infrastructure',
    sector_mixed: 'Mixed use',

    pipeline: 'Pipeline', opportunity: 'Opportunity', new_opportunity: 'New opportunity',
    opportunity_title: 'Project name', project_type: 'Project type',
    area_sqm: 'Area (m²)', stage: 'Stage', probability: 'Probability',
    expected_value: 'Expected value', currency: 'Currency',
    expected_close: 'Expected close', lost_reason: 'Loss reason',
    lost_to: 'Lost to', my_opportunities: 'My pipeline', all_opportunities: 'All opportunities',
    board_view: 'Board', list_view: 'List',

    stage_new: 'New', stage_qualified: 'Qualified', stage_quoted: 'Quoted',
    stage_negotiation: 'Negotiation', stage_won: 'Won', stage_lost: 'Lost',

    ptype_tower: 'Tower', ptype_school: 'School', ptype_mall: 'Mall',
    ptype_villa: 'Villa', ptype_rest_house: 'Rest house', ptype_admin: 'Office building',
    ptype_hospital: 'Hospital', ptype_parking: 'Car park', ptype_industrial: 'Industrial',
    ptype_other: 'Other',

    reason_price: 'Price', reason_timing: 'Timing', reason_competitor: 'Competitor',
    reason_scope: 'Scope', reason_no_budget: 'No budget',
    reason_no_response: 'No response', reason_other: 'Other',

    activities: 'Follow-ups', activity: 'Follow-up', new_activity: 'New follow-up',
    activity_type: 'Type', subject: 'Subject', due_at: 'Due',
    mark_done: 'Mark done', done: 'Done', outcome: 'Outcome',
    related_to: 'Related to', my_activities: 'Mine', all_activities: 'All',
    reopen: 'Reopen',

    act_call: 'Call', act_meeting: 'Meeting', act_email: 'Email',
    act_whatsapp: 'WhatsApp', act_site_visit: 'Site visit', act_task: 'Task', act_note: 'Note',

    quotations: 'Quotations', quotation: 'Quotation', new_quotation: 'New quotation',
    quote_number: 'Quotation no.', revision: 'Revision', issue_date: 'Issue date',
    valid_days: 'Validity (days)', valid_until: 'Valid until',
    project_name: 'Project name', project_name_ar: 'Project name (Arabic)',
    location: 'Location', attention: 'Attention',
    subtotal: 'Subtotal', discount: 'Discount', net_amount: 'Net amount',
    vat: 'VAT', vat_rate: 'VAT rate %',
    grand_total: 'Grand total', unit_price: 'Unit price',
    quantity: 'Quantity', unit: 'Unit', description: 'Description', amount: 'Amount',
    line_items: 'Line items', add_item: 'Add item', optional_item: 'Optional item',
    print_ar: 'Print Arabic version', print_en: 'Print English version',
    duplicate: 'Duplicate', create_revision: 'Create revision',
    mark_sent: 'Mark as sent', mark_approved: 'Approve', mark_rejected: 'Reject',
    reject_reason: 'Rejection reason', amount_in_words: 'Amount in words',

    qstatus_draft: 'Draft', qstatus_sent: 'Sent', qstatus_under_review: 'Under review',
    qstatus_approved: 'Approved', qstatus_rejected: 'Rejected',
    qstatus_expired: 'Expired', qstatus_cancelled: 'Cancelled',

    cost_calculator: 'Cost calculator', internal_only: 'Internal use only',
    strand_price_ton: 'Strand price (per ton)', strand_kg_sqm: 'Strand kg per m²',
    anchors_per_ton: 'Anchors per ton', anchor_cost: 'Cost per anchor',
    duct_cost_sqm: 'Duct cost /m²', grout_cost_sqm: 'Grout cost /m²',
    labour_cost_sqm: 'Labour cost /m²', design_cost_sqm: 'Design cost /m²',
    overhead_pct: 'Overheads %', target_margin: 'Target margin %',
    price_variance: 'Strand price variance ±%',
    strand_tons: 'Total strand (tons)', anchor_count: 'Anchors',
    direct_cost: 'Direct cost', cost_per_sqm: 'Cost /m²',
    price_per_sqm: 'Price /m²', suggested_price: 'Suggested price /m²',
    margin: 'Margin', margin_amount: 'Margin value',
    below_cost_warning: 'Warning: price is below cost',
    below_target_warning: 'Note: margin is below target',

    analytics: 'Analytics', period: 'Period', from: 'From', to: 'To',
    last_12_months: 'Last 12 months', this_year: 'This year', this_quarter: 'This quarter',
    conversion_funnel: 'Conversion funnel', by_country: 'By country',
    by_engineer: 'By engineer', by_source: 'By source',
    by_project_type: 'By project type', loss_analysis: 'Loss analysis',
    monthly_trend: 'Monthly trend', price_benchmark: 'Price per m² benchmark',
    created: 'Created', qualified: 'Qualified', quoted: 'Quoted',
    negotiation: 'Negotiation', won: 'Won', lost: 'Lost',
    avg_price: 'Average', min_price: 'Lowest', max_price: 'Highest',
    quotes_issued: 'Quotes issued', value_won: 'Value won',
    conversion_rate: 'Conversion',

    settings: 'Settings', company_profile: 'Company profile',
    price_book: 'Price book', templates: 'Quotation templates', users: 'Users',
    new_user: 'New user', role: 'Role', active: 'Active', inactive: 'Disabled',
    role_admin: 'Administrator', role_manager: 'Manager', role_engineer: 'Engineer',
    role_viewer: 'Viewer',
    company_name_en: 'Company name (English)', company_name_ar: 'Company name (Arabic)',
    default_price: 'Default price /m²', floor_price: 'Floor price /m²',
    reset_defaults: 'Restore defaults',
    scope_design: 'Design', scope_supply: 'Supply',
    scope_installation: 'Installation & testing', scope_deliverables: 'Deliverables',
    scope_requirements: 'By main contractor', scope_exclusions: 'Exclusions',
    scope_warranty: 'Warranty', scope_schedule: 'Programme', scope_team: 'Project team',
    payment_terms: 'Payment terms', conditions: 'Terms & conditions',
    quote_prefix: 'Quotation number prefix', last_login: 'Last sign-in',

    country_SA: 'Saudi Arabia', country_EG: 'Egypt', country_QA: 'Qatar',
  },
};

let current = localStorage.getItem('spantech_lang') || 'ar';

export const getLang = () => current;
export const isRTL = () => current === 'ar';

export function setLang(lang) {
  current = lang === 'en' ? 'en' : 'ar';
  localStorage.setItem('spantech_lang', current);
  applyDirection();
}

export function applyDirection() {
  const html = document.documentElement;
  html.lang = current;
  html.dir = isRTL() ? 'rtl' : 'ltr';
}

/** Translate a key. Falls back to the key itself so gaps are visible. */
export function t(key, fallback) {
  return DICT[current]?.[key] ?? DICT.ar[key] ?? fallback ?? key;
}

/** Picks the Arabic or English variant of a record field, with a fallback. */
export function pick(record, baseField) {
  if (!record) return '';
  const arabic = record[`${baseField}_ar`];
  const english = record[baseField] ?? record[`${baseField}_en`];
  return (isRTL() ? arabic || english : english || arabic) || '';
}

// ---------------------------------------------------------------- formatting
const LOCALE = () => (isRTL() ? 'ar-EG' : 'en-GB');

/** Money with no currency symbol — the column header carries the currency. */
export function money(value, digits = 2) {
  const n = Number(value || 0);
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function moneyShort(value) {
  const n = Math.abs(Number(value || 0));
  if (n >= 1_000_000) return `${(Number(value) / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(Number(value) / 1_000).toFixed(0)}K`;
  return money(value, 0);
}

export const number = (value, digits = 0) =>
  Number(value || 0).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function formatDate(value) {
  if (!value) return '—';
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString(LOCALE() === 'ar-EG' ? 'ar-EG-u-nu-latn' : 'en-GB',
    { year: 'numeric', month: 'short', day: '2-digit' });
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return `${formatDate(value)} · ${d.toLocaleTimeString(isRTL() ? 'ar-EG-u-nu-latn' : 'en-GB', { hour: '2-digit', minute: '2-digit' })}`;
}

/** "in 3 days" / "2 days overdue" — drives the follow-up colour coding. */
export function relativeDays(value) {
  if (!value) return { days: null, label: t('no_due_date') };
  const due = new Date(value);
  const days = Math.round((due - new Date()) / 86400_000);
  if (days === 0) return { days, label: t('due_today') };
  if (days < 0) {
    return { days, label: isRTL() ? `متأخرة ${Math.abs(days)} يوم` : `${Math.abs(days)} days overdue` };
  }
  return { days, label: isRTL() ? `بعد ${days} يوم` : `in ${days} days` };
}

applyDirection();
