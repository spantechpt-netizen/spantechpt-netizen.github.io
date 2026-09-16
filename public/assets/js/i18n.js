/**
 * Bilingual dictionary. Every visible string lives here so the whole
 * interface can flip between Arabic (RTL) and English (LTR) instantly.
 *
 * The Arabic here is Egyptian business Arabic — how the engineers actually
 * talk. The *printed quotation* deliberately stays in formal MSA, because it
 * goes to clients in Saudi Arabia and Qatar; that wording lives in
 * server/templates.js and public/assets/js/views/quote-print.js, not here.
 */
export const DICT = {
  ar: {
    // --- shell -------------------------------------------------------------
    app_name: 'سبان تك', app_subtitle: 'العملاء وعروض الأسعار',
    nav_dashboard: 'الرئيسية', nav_customers: 'العملاء', nav_pipeline: 'الفرص',
    nav_activities: 'المتابعات', nav_quotations: 'عروض الأسعار',
    nav_analytics: 'التحليلات', nav_settings: 'الإعدادات',
    nav_inbox: 'الرسايل', nav_calendar: 'الأجندة',
    sign_out: 'خروج', my_profile: 'حسابي', language: 'اللغة',
    loading: 'بيحمّل…', no_data: 'مفيش بيانات',
    search: 'دوّر', filter: 'فلتر', all: 'الكل', clear: 'مسح',
    save: 'حفظ', cancel: 'إلغاء', close: 'إقفال', delete: 'مسح', edit: 'تعديل',
    add: 'زوّد', create: 'إنشاء', open: 'افتح', back: 'رجوع', actions: 'إجراءات',
    confirm_delete: 'متأكد إنك عايز تمسحه؟ مش هينفع ترجع فيها.',
    saved: 'اتحفظ ✓', deleted: 'اتمسح', error: 'حصل خطأ',
    required_field: 'مطلوب', optional: 'اختياري', none: 'مفيش',
    yes: 'أيوه', no: 'لأ', total: 'الإجمالي', print: 'طباعة', export: 'تصدير',
    copy: 'نسخ', copied: 'اتنسخ ✓', send: 'ابعت', refresh: 'تحديث',
    view_all: 'شوف الكل', nothing_here: 'مفيش حاجة هنا',

    // --- auth --------------------------------------------------------------
    login_title: 'تسجيل الدخول', email: 'الإيميل',
    password: 'كلمة السر', login: 'دخول',
    login_welcome: 'نظام العملاء وعروض الأسعار',
    current_password: 'كلمة السر الحالية', new_password: 'كلمة السر الجديدة',
    change_password: 'غيّر كلمة السر', password_changed: 'كلمة السر اتغيّرت',
    password_min: '8 حروف على الأقل',

    // --- dashboard ---------------------------------------------------------
    dashboard: 'الرئيسية', welcome: 'أهلاً', today: 'النهاردة',
    kpi_open_pipeline: 'الفرص الشغالة', kpi_weighted: 'القيمة المرجّحة',
    kpi_win_rate: 'نسبة الكسب', kpi_quotes_sent: 'عروض السنة دي',
    kpi_won_value: 'قيمة الشغل المكسوب', kpi_customers: 'العملاء',
    overdue: 'فاتت', due_today: 'النهاردة', upcoming: 'جاية',
    no_due_date: 'من غير معاد', follow_ups: 'المتابعات المطلوبة',
    recent_quotes: 'آخر عروض الأسعار', top_opportunities: 'أهم الفرص',
    all_clear: 'مفيش حاجة فايتة — تمام كده 👌',

    // --- customers ---------------------------------------------------------
    customers: 'العملاء', customer: 'العميل', new_customer: 'عميل جديد',
    customer_name_en: 'الاسم بالإنجليزي', customer_name_ar: 'الاسم بالعربي',
    customer_type: 'نوع العميل', country: 'الدولة', city: 'المدينة',
    sector: 'القطاع', website: 'الموقع', phone: 'التليفون',
    address: 'العنوان', tax_number: 'الرقم الضريبي', cr_number: 'السجل التجاري',
    status: 'الحالة', source: 'جه منين', rating: 'الأولوية',
    owner: 'المهندس المسؤول', notes: 'ملاحظات', contacts: 'جهات الاتصال',
    contact_name: 'الاسم', contact_title: 'الوظيفة', mobile: 'الموبايل',
    primary_contact: 'الشخص الأساسي', new_contact: 'جهة اتصال جديدة',
    my_customers: 'عملائي', all_customers: 'كل العملاء',
    opportunities_count: 'الفرص', quotations_count: 'العروض',
    last_contact: 'آخر تواصل',

    type_main_contractor: 'مقاول رئيسي', type_consultant: 'استشاري',
    type_developer: 'مطوّر عقاري', type_owner: 'مالك',
    type_subcontractor: 'مقاول باطن', type_government: 'جهة حكومية', type_other: 'غير كده',

    status_target: 'عميل مستهدف', status_prospect: 'عميل محتمل',
    status_active: 'عميل شغّال', status_dormant: 'واقف', status_blacklisted: 'محظور',

    source_referral: 'ترشيح', source_website: 'الموقع',
    source_exhibition: 'معرض', source_cold_call: 'اتصال مباشر',
    source_existing: 'عميل قديم', source_tender: 'مناقصة', source_social: 'سوشيال ميديا',

    sector_residential: 'سكني', sector_commercial: 'تجاري', sector_education: 'تعليمي',
    sector_healthcare: 'صحي', sector_industrial: 'صناعي',
    sector_infrastructure: 'بنية تحتية', sector_mixed: 'متعدد الاستخدام',

    // --- pipeline ----------------------------------------------------------
    pipeline: 'الفرص', opportunity: 'الفرصة', new_opportunity: 'فرصة جديدة',
    opportunity_title: 'اسم المشروع', project_type: 'نوع المشروع',
    area_sqm: 'المساحة (م²)', stage: 'المرحلة', probability: 'فرصة الكسب',
    expected_value: 'القيمة المتوقعة', currency: 'العملة',
    expected_close: 'متوقع يقفل في', lost_reason: 'خسرناها ليه',
    lost_to: 'راحت لمين', my_opportunities: 'فرصي', all_opportunities: 'كل الفرص',
    board_view: 'المراحل', list_view: 'قائمة',

    stage_new: 'جديدة', stage_qualified: 'مؤهلة', stage_quoted: 'اتسعّرت',
    stage_negotiation: 'تفاوض', stage_won: 'كسبناها', stage_lost: 'خسرناها',

    ptype_tower: 'برج', ptype_school: 'مدرسة', ptype_mall: 'مول',
    ptype_villa: 'فيلا', ptype_rest_house: 'استراحة', ptype_admin: 'مبنى إداري',
    ptype_hospital: 'مستشفى', ptype_parking: 'جراج', ptype_industrial: 'صناعي',
    ptype_other: 'غير كده',

    reason_price: 'السعر', reason_timing: 'التوقيت', reason_competitor: 'منافس',
    reason_scope: 'نطاق الشغل', reason_no_budget: 'مفيش ميزانية',
    reason_no_response: 'مردّوش', reason_other: 'غير كده',

    // --- activities --------------------------------------------------------
    activities: 'المتابعات', activity: 'متابعة', new_activity: 'متابعة جديدة',
    activity_type: 'النوع', subject: 'الموضوع', due_at: 'معاد المتابعة',
    mark_done: 'خلصت', done: 'خلصت', outcome: 'النتيجة',
    related_to: 'مرتبطة بـ', my_activities: 'بتاعتي', all_activities: 'الكل',
    reopen: 'افتحها تاني', add_to_calendar: 'ضيفها للأجندة',

    act_call: 'مكالمة', act_meeting: 'اجتماع', act_email: 'إيميل',
    act_whatsapp: 'واتساب', act_site_visit: 'زيارة موقع', act_task: 'مهمة', act_note: 'ملاحظة',

    // --- quotations --------------------------------------------------------
    quotations: 'عروض الأسعار', quotation: 'عرض السعر', new_quotation: 'عرض سعر جديد',
    quote_number: 'رقم العرض', revision: 'المراجعة', issue_date: 'تاريخ الإصدار',
    valid_days: 'مدة السريان (يوم)', valid_until: 'ساري لحد',
    project_name: 'اسم المشروع', project_name_ar: 'اسم المشروع بالعربي',
    location: 'الموقع', attention: 'عناية الأستاذ',
    subtotal: 'الإجمالي قبل الضريبة', discount: 'الخصم', net: 'الصافي',
    net_amount: 'الصافي',
    vat: 'ضريبة القيمة المضافة', vat_rate: 'نسبة الضريبة %',
    grand_total: 'الإجمالي بالضريبة', unit_price: 'سعر الوحدة',
    quantity: 'الكمية', unit: 'الوحدة', description: 'البند', amount: 'القيمة',
    line_items: 'بنود العرض', add_item: 'زوّد بند', optional_item: 'بند اختياري',
    print_ar: 'اطبع عربي', print_en: 'اطبع إنجليزي',
    duplicate: 'انسخ العرض', create_revision: 'اعمل مراجعة',
    mark_sent: 'اتبعت', mark_approved: 'اعتماد', mark_rejected: 'رفض',
    reject_reason: 'سبب الرفض', amount_in_words: 'المبلغ كتابةً',

    qstatus_draft: 'مسودة', qstatus_sent: 'اتبعت', qstatus_under_review: 'تحت الدراسة',
    qstatus_approved: 'اتعتمد', qstatus_rejected: 'اترفض',
    qstatus_expired: 'خلصت صلاحيته', qstatus_cancelled: 'اتلغى',

    // --- pricing calculator -------------------------------------------------
    cost_calculator: 'حاسبة التكلفة', internal_only: 'للاستخدام الداخلي بس',
    strand_price_ton: 'سعر الكابلات (للطن)', strand_kg_sqm: 'كجم كابلات لكل م²',
    anchors_per_ton: 'عدد الأنكورات للطن', anchor_cost: 'تكلفة الأنكور',
    duct_cost_sqm: 'تكلفة الجرابات /م²', grout_cost_sqm: 'تكلفة الحقن /م²',
    labour_cost_sqm: 'تكلفة العمالة /م²', design_cost_sqm: 'تكلفة التصميم /م²',
    overhead_pct: 'المصاريف العمومية %', target_margin: 'الربح المستهدف %',
    price_variance: 'تغيّر سعر الكابلات ±%',
    strand_tons: 'إجمالي الكابلات (طن)', anchor_count: 'عدد الأنكورات',
    direct_cost: 'التكلفة المباشرة', cost_per_sqm: 'التكلفة /م²',
    price_per_sqm: 'السعر /م²', suggested_price: 'السعر المقترح /م²',
    margin: 'الربح', margin_amount: 'قيمة الربح',
    below_cost_warning: 'خد بالك: السعر أقل من التكلفة',
    below_target_warning: 'تنبيه: الربح أقل من المستهدف',

    // --- analytics ---------------------------------------------------------
    analytics: 'التحليلات', period: 'الفترة', from: 'من', to: 'لـ',
    last_12_months: 'آخر 12 شهر', this_year: 'السنة دي', this_quarter: 'الربع ده',
    conversion_funnel: 'مسار التحويل', by_country: 'حسب الدولة',
    by_engineer: 'حسب المهندس', by_source: 'العميل جه منين',
    by_project_type: 'حسب نوع المشروع', loss_analysis: 'تحليل الخسائر',
    monthly_trend: 'الاتجاه الشهري', price_benchmark: 'متوسط سعر المتر',
    created: 'اتعملت', qualified: 'مؤهلة', quoted: 'اتسعّرت',
    negotiation: 'تفاوض', won: 'كسبناها', lost: 'خسرناها',
    avg_price: 'المتوسط', min_price: 'الأقل', max_price: 'الأعلى',
    quotes_issued: 'العروض اللي طلعت', value_won: 'القيمة المكسوبة',
    conversion_rate: 'نسبة التحويل',

    // --- settings ----------------------------------------------------------
    settings: 'الإعدادات', company_profile: 'بيانات الشركة',
    price_book: 'جدول الأسعار', templates: 'قوالب العرض', users: 'المستخدمين',
    new_user: 'مستخدم جديد', role: 'الصلاحية', active: 'شغّال', inactive: 'موقوف',
    role_admin: 'مدير النظام', role_manager: 'مدير', role_engineer: 'مهندس',
    role_viewer: 'مشاهدة بس',
    company_name_en: 'اسم الشركة بالإنجليزي', company_name_ar: 'اسم الشركة بالعربي',
    default_price: 'السعر الافتراضي /م²', floor_price: 'أقل سعر /م²',
    reset_defaults: 'رجّع الافتراضي',
    scope_design: 'التصميم', scope_supply: 'التوريد',
    scope_installation: 'التركيب والاختبارات', scope_deliverables: 'الوثائق المقدمة',
    scope_requirements: 'مطلوب من المقاول الرئيسي', scope_exclusions: 'مش داخل في العرض',
    scope_warranty: 'الضمانات', scope_schedule: 'الجدول الزمني', scope_team: 'فريق العمل',
    payment_terms: 'شروط الدفع', conditions: 'الشروط والأحكام',
    quote_prefix: 'بادئة رقم العرض', last_login: 'آخر دخول',
    branches: 'بيانات الفروع', default_branch: 'الفرع الافتراضي',
    branches_hint: 'كل عرض سعر بيطلع ببيانات الفرع بتاع دولة المشروع — السجل التجاري والعنوان والتليفون.',
    permissions: 'الصلاحيات', permission_overrides: 'صلاحيات مخصصة',
    perm_default_on: 'افتراضي', perm_default_off: 'مقفول افتراضي',
    perm_overridden: 'مخصص', perm_custom: 'مخصصة',
    perm_hint: 'الصلاحيات بتبدأ من الدور، وتقدر تخصص أي بند لشخص لوحده.',
    no_permission: 'مالكش صلاحية للإجراء ده',

    // --- notifications & inbox ---------------------------------------------
    notifications: 'الإشعارات', notification: 'إشعار',
    mark_all_read: 'علّم الكل كمقروء', mark_read: 'علّمه كمقروء',
    no_notifications: 'مفيش إشعارات جديدة',
    unread: 'مش مقروء', read: 'مقروء',
    desktop_notifications: 'إشعارات على سطح المكتب',
    enable_desktop_notifications: 'فعّل إشعارات سطح المكتب',
    desktop_enabled: 'الإشعارات مفعّلة ✓',
    desktop_blocked: 'المتصفح مانع الإشعارات — فعّلها من إعدادات الموقع',
    run_check_now: 'افحص دلوقتي',
    check_done: 'تم الفحص',

    inbox: 'الرسايل', messages: 'الرسايل', new_message: 'رسالة جديدة',
    compose: 'اكتب رسالة', reply: 'رد', replies: 'ردود',
    message_to: 'لمين', message_subject: 'الموضوع', message_body: 'الرسالة',
    message_sent: 'اتبعتت ✓', no_messages: 'مفيش رسايل',
    inbox_tab: 'الوارد', sent_tab: 'اللي بعتّه', from: 'من', sent_to: 'لـ',
    attach_record: 'اربطها بسجل', pick_colleagues: 'اختار الزمايل',
    message_placeholder: 'اكتب رسالتك للزمايل…',
    reply_placeholder: 'اكتب ردك…',

    notif_message: 'رسالة', notif_assigned: 'اتحوّلك', notif_activity_due: 'متابعة قرّبت',
    notif_activity_overdue: 'متابعة فاتت', notif_stale_customer: 'تواصل مفقود',
    notif_quote_status: 'حالة عرض سعر', notif_quote_expiring: 'عرض قرّب يخلص',
    notif_quote_expired: 'عرض خلص',

    // --- calendar ----------------------------------------------------------
    calendar: 'الأجندة', month: 'شهر', week: 'أسبوع', agenda: 'قائمة',
    prev: 'السابق', next: 'التالي', this_month: 'الشهر ده',
    calendar_feed: 'ربط بتقويم أوتلوك / جوجل',
    calendar_feed_hint: 'انسخ اللينك ده وضيفه في أوتلوك أو جوجل كاليندر كـ "تقويم مشترك"، ومتابعاتك هتظهر هناك وتتحدّث لوحدها.',
    copy_link: 'انسخ اللينك', new_link: 'اعمل لينك جديد',
    rotate_warning: 'اللينك القديم هيبطل يشتغل. متأكد؟',
    subscribe_outlook: 'اشترك في أوتلوك', download_ics: 'نزّل ملف .ics',
    reminder_settings: 'إعدادات التنبيه',
    reminder_lead_hours: 'نبّهني قبل المتابعة بـ (ساعة)',
    stale_after_days: 'اعتبر العميل تواصل مفقود بعد (يوم)',

    weekday_sun: 'أحد', weekday_mon: 'اتنين', weekday_tue: 'تلات',
    weekday_wed: 'أربع', weekday_thu: 'خميس', weekday_fri: 'جمعة', weekday_sat: 'سبت',

    // --- email intake ------------------------------------------------------
    nav_requests: 'الطلبات الواردة',
    requests: 'الطلبات الواردة', request: 'طلب',
    req_new: 'جديدة', req_assigned: 'موزّعة', req_converted: 'اتحوّلت', req_dismissed: 'مرفوضة',
    capture_add: 'ضيف طلب من واتساب',
    capture_title: 'طلب جات على الواتساب',
    capture_hint: 'الصق الرسالة زي ما هي. النظام هيقرا منها العميل والمشروع والمساحة والدولة، وتراجعها إنت قبل ما تتحوّل.',
    capture_text: 'نص الرسالة',
    capture_text_ph: 'الصق هنا رسالة الواتساب…',
    capture_from_name: 'اسم المُرسِل',
    capture_from_phone: 'رقم المُرسِل',
    capture_from_phone_hint: 'لو حطيت الرقم، النظام هيدوّر بيه على العميل في القاعدة.',
    capture_channel: 'جاية منين',
    capture_ch_whatsapp: 'واتساب', capture_ch_phone: 'مكالمة', capture_ch_other: 'حاجة تانية',
    capture_save: 'ضيفها للطلبات',
    capture_done: 'اتضافت للطلبات الواردة',
    capture_empty: 'الصق نص الرسالة الأول',
    channel_email: 'إيميل', channel_whatsapp: 'واتساب', channel_phone: 'مكالمة', channel_other: 'يدوي',
    req_is_rfq: 'طلب سعر', req_confidence: 'الثقة',
    req_detail: 'تفاصيل الطلب', req_draft: 'البيانات المستخرجة — راجعها قبل ما تعتمد',
    req_assign: 'وزّعه على مهندس', req_assign_to: 'المهندس',
    req_convert: 'اعتمد وأنشئ العميل والفرصة', req_converted_ok: 'اتعمل العميل والفرصة ✓',
    req_dismiss: 'ارفض الطلب', req_dismiss_confirm: 'هيتشال من الطابور. متأكد؟',
    req_open_opportunity: 'افتح الفرصة', req_re_extract: 'استخرج البيانات تاني',
    req_source: 'مصدر الاستخراج',
    no_requests: 'مفيش طلبات هنا',
    fetch_mail_now: 'اسحب الإيميلات دلوقتي',

    mailboxes: 'حسابات البريد', add_mailbox: 'أضف حساب بريد',
    mailbox_label: 'اسم الحساب', mailbox_user: 'اسم المستخدم / الإيميل',
    mailbox_password: 'كلمة المرور', password_unchanged: 'سيبها فاضية عشان متتغيرش',
    use_app_password: 'استخدم "كلمة مرور تطبيق" مش كلمة سر الإيميل',
    imap_host: 'سيرفر IMAP', imap_port: 'البورت',
    imap_tls: 'اتصال مشفّر (TLS)', imap_tls_hint: 'شغّالة = بورت 993 · مقفولة = 143 مع STARTTLS',
    allow_self_signed: 'اقبل شهادة self-signed',
    allow_self_signed_hint: 'للسيرفرات الداخلية اللي شهادتها مش موثّقة',
    mail_folders: 'المجلدات', sync_every: 'يسحب كل', minutes: 'دقيقة',
    last_sync: 'آخر سحب', test_connection: 'اختبر الاتصال', connection_ok: 'الاتصال تمام ✓',
    mail_stored: 'رسالة اتخزنت', no_mailboxes: 'مفيش حسابات بريد لسه',

    ai_extraction: 'استخراج البيانات بالذكاء الاصطناعي',
    ai_explain: 'من غير مفتاح، النظام بيستخرج البيانات بقواعد جاهزة (المساحة، الدولة، نوع المشروع). لو ضفت مفتاح Claude، هيقرا الإيميل بالكامل ويطلّع بيانات أدق وملخص بالعربي والإنجليزي.',
    ai_key: 'مفتاح Claude API', ai_key_set: 'المفتاح متسجّل ✓',
    ai_key_hint: 'من console.anthropic.com', ai_model: 'الموديل',
    ai_enabled: 'فعّل الاستخراج بالذكاء الاصطناعي', ai_off: 'مقفول',
    ai_clear_key: 'امسح المفتاح',

    notif_mail_request: 'طلب من الإيميل',

    backfill: 'استدعاء من الإيميلات القديمة',
    backfill_hint: 'يفحص البريد القديم ويطلّع منه عملاء ومشاريع',
    backfill_explain: 'هيفحص الإيميلات القديمة ويطلّع منها طلبات الأسعار والعملاء اللي اتكلمتوا معاهم قبل كده. الطلبات هتيجي في الطابور وانت تراجعها — مفيش حاجة هتتضاف لوحدها.',
    backfill_period: 'يرجع لـ', backfill_limit: 'أقصى عدد رسايل',
    backfill_3m: 'آخر 3 شهور', backfill_6m: 'آخر 6 شهور', backfill_1y: 'آخر سنة',
    backfill_3y: 'آخر 3 سنين', backfill_all: 'كل اللي موجود',
    backfill_folders_hint: 'تقدر تزوّد مجلدات تانية زي Archive أو Sent',
    backfill_start: 'ابدأ الفحص', backfill_running: 'بيفحص… ممكن ياخد شوية',
    mail_read: 'رسالة اتقرت',

    // --- countries ---------------------------------------------------------
    country_SA: 'السعودية', country_EG: 'مصر', country_QA: 'قطر',
  },

  en: {
    app_name: 'Span Tech', app_subtitle: 'CRM & Quotations',
    nav_dashboard: 'Dashboard', nav_customers: 'Customers', nav_pipeline: 'Pipeline',
    nav_activities: 'Follow-ups', nav_quotations: 'Quotations',
    nav_analytics: 'Analytics', nav_settings: 'Settings',
    nav_inbox: 'Messages', nav_calendar: 'Calendar',
    sign_out: 'Sign out', my_profile: 'My profile', language: 'Language',
    loading: 'Loading…', no_data: 'No records',
    search: 'Search', filter: 'Filter', all: 'All', clear: 'Clear',
    save: 'Save', cancel: 'Cancel', close: 'Close', delete: 'Delete', edit: 'Edit',
    add: 'Add', create: 'Create', open: 'Open', back: 'Back', actions: 'Actions',
    confirm_delete: 'Delete this record? This cannot be undone.',
    saved: 'Saved', deleted: 'Deleted', error: 'Something went wrong',
    required_field: 'Required', optional: 'optional', none: 'None',
    yes: 'Yes', no: 'No', total: 'Total', print: 'Print', export: 'Export',
    copy: 'Copy', copied: 'Copied', send: 'Send', refresh: 'Refresh',
    view_all: 'View all', nothing_here: 'Nothing here',

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
    last_contact: 'Last contact',

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
    reopen: 'Reopen', add_to_calendar: 'Add to calendar',

    act_call: 'Call', act_meeting: 'Meeting', act_email: 'Email',
    act_whatsapp: 'WhatsApp', act_site_visit: 'Site visit', act_task: 'Task', act_note: 'Note',

    quotations: 'Quotations', quotation: 'Quotation', new_quotation: 'New quotation',
    quote_number: 'Quotation no.', revision: 'Revision', issue_date: 'Issue date',
    valid_days: 'Validity (days)', valid_until: 'Valid until',
    project_name: 'Project name', project_name_ar: 'Project name (Arabic)',
    location: 'Location', attention: 'Attention',
    subtotal: 'Subtotal', discount: 'Discount', net: 'Net',
    net_amount: 'Net amount',
    vat: 'VAT', vat_rate: 'VAT rate %',
    grand_total: 'Grand total', unit_price: 'Unit price',
    quantity: 'Quantity', unit: 'Unit', description: 'Description', amount: 'Amount',
    line_items: 'Line items', add_item: 'Add item', optional_item: 'Optional item',
    print_ar: 'Print Arabic', print_en: 'Print English',
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
    branches: 'Branch details', default_branch: 'Default branch',
    branches_hint: 'Each quotation prints the branch matching the project’s country — registration, address and phone.',
    permissions: 'Permissions', permission_overrides: 'Custom permissions',
    perm_default_on: 'default', perm_default_off: 'off by default',
    perm_overridden: 'custom', perm_custom: 'custom',
    perm_hint: 'Permissions start from the role; override any line for one person.',
    no_permission: 'You do not have permission to do this',

    notifications: 'Notifications', notification: 'Notification',
    mark_all_read: 'Mark all read', mark_read: 'Mark read',
    no_notifications: 'No new notifications',
    unread: 'Unread', read: 'Read',
    desktop_notifications: 'Desktop notifications',
    enable_desktop_notifications: 'Enable desktop notifications',
    desktop_enabled: 'Desktop notifications on',
    desktop_blocked: 'Your browser is blocking notifications — allow them in site settings',
    run_check_now: 'Check now',
    check_done: 'Check complete',

    inbox: 'Messages', messages: 'Messages', new_message: 'New message',
    compose: 'Compose', reply: 'Reply', replies: 'Replies',
    message_to: 'To', message_subject: 'Subject', message_body: 'Message',
    message_sent: 'Sent', no_messages: 'No messages',
    inbox_tab: 'Inbox', sent_tab: 'Sent', from: 'From', sent_to: 'To',
    attach_record: 'Link to a record', pick_colleagues: 'Pick colleagues',
    message_placeholder: 'Write to your colleagues…',
    reply_placeholder: 'Write a reply…',

    notif_message: 'Message', notif_assigned: 'Assigned', notif_activity_due: 'Due soon',
    notif_activity_overdue: 'Overdue', notif_stale_customer: 'Missed contact',
    notif_quote_status: 'Quotation status', notif_quote_expiring: 'Expiring soon',
    notif_quote_expired: 'Expired',

    calendar: 'Calendar', month: 'Month', week: 'Week', agenda: 'Agenda',
    prev: 'Previous', next: 'Next', this_month: 'This month',
    calendar_feed: 'Link to Outlook / Google Calendar',
    calendar_feed_hint: 'Copy this link and add it to Outlook or Google Calendar as a subscribed calendar. Your follow-ups will appear there and stay up to date automatically.',
    copy_link: 'Copy link', new_link: 'Generate a new link',
    rotate_warning: 'The old link will stop working. Continue?',
    subscribe_outlook: 'Subscribe in Outlook', download_ics: 'Download .ics',
    reminder_settings: 'Reminder settings',
    reminder_lead_hours: 'Remind me this many hours before',
    stale_after_days: 'Flag missed contact after (days)',

    weekday_sun: 'Sun', weekday_mon: 'Mon', weekday_tue: 'Tue',
    weekday_wed: 'Wed', weekday_thu: 'Thu', weekday_fri: 'Fri', weekday_sat: 'Sat',

    nav_requests: 'Requests',
    requests: 'Incoming requests', request: 'Request',
    req_new: 'New', req_assigned: 'Assigned', req_converted: 'Converted', req_dismissed: 'Dismissed',
    capture_add: 'Add a WhatsApp request',
    capture_title: 'Request from WhatsApp',
    capture_hint: 'Paste the message as it came. The customer, project, area and country are read out of it for you to check before converting.',
    capture_text: 'Message',
    capture_text_ph: 'Paste the WhatsApp message here…',
    capture_from_name: 'Sender name',
    capture_from_phone: 'Sender number',
    capture_from_phone_hint: 'With the number, the sender is matched against customers already on file.',
    capture_channel: 'Came in by',
    capture_ch_whatsapp: 'WhatsApp', capture_ch_phone: 'Phone call', capture_ch_other: 'Something else',
    capture_save: 'Add to requests',
    capture_done: 'Added to incoming requests',
    capture_empty: 'Paste the message first',
    channel_email: 'Email', channel_whatsapp: 'WhatsApp', channel_phone: 'Call', channel_other: 'Manual',
    req_is_rfq: 'Quote request', req_confidence: 'Confidence',
    req_detail: 'Request detail', req_draft: 'Extracted data — check it before converting',
    req_assign: 'Assign to an engineer', req_assign_to: 'Engineer',
    req_convert: 'Convert to customer and opportunity', req_converted_ok: 'Customer and opportunity created',
    req_dismiss: 'Dismiss', req_dismiss_confirm: 'This drops it from the queue. Continue?',
    req_open_opportunity: 'Open the opportunity', req_re_extract: 'Extract again',
    req_source: 'Extracted by',
    no_requests: 'Nothing in this queue',
    fetch_mail_now: 'Fetch mail now',

    mailboxes: 'Mailboxes', add_mailbox: 'Add a mailbox',
    mailbox_label: 'Name', mailbox_user: 'Username / email',
    mailbox_password: 'Password', password_unchanged: 'Leave blank to keep the stored one',
    use_app_password: 'Use an app password, not the account password',
    imap_host: 'IMAP server', imap_port: 'Port',
    imap_tls: 'Encrypted connection (TLS)', imap_tls_hint: 'On = port 993 · Off = 143 with STARTTLS',
    allow_self_signed: 'Accept a self-signed certificate',
    allow_self_signed_hint: 'For internal servers with an untrusted certificate',
    mail_folders: 'Folders', sync_every: 'Fetch every', minutes: 'minutes',
    last_sync: 'Last fetch', test_connection: 'Test connection', connection_ok: 'Connected',
    mail_stored: 'messages stored', no_mailboxes: 'No mailboxes configured yet',

    ai_extraction: 'AI extraction',
    ai_explain: 'Without a key the CRM extracts what it can with built-in rules (area, country, project type). Add a Claude API key and it reads the whole email for more accurate data and a summary in both languages.',
    ai_key: 'Claude API key', ai_key_set: 'Key stored',
    ai_key_hint: 'From console.anthropic.com', ai_model: 'Model',
    ai_enabled: 'Enable AI extraction', ai_off: 'Off',
    ai_clear_key: 'Remove the key',

    notif_mail_request: 'Email request',

    backfill: 'Import from past email',
    backfill_hint: 'Scan older mail for customers and projects',
    backfill_explain: 'This scans your older email for quotation requests and clients you have already dealt with. Anything found lands in the queue for you to review — nothing is added on its own.',
    backfill_period: 'Go back', backfill_limit: 'Maximum messages',
    backfill_3m: 'Last 3 months', backfill_6m: 'Last 6 months', backfill_1y: 'Last year',
    backfill_3y: 'Last 3 years', backfill_all: 'Everything',
    backfill_folders_hint: 'Add other folders such as Archive or Sent',
    backfill_start: 'Start the scan', backfill_running: 'Scanning… this can take a moment',
    mail_read: 'messages read',

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
