/**
 * Creates the first administrator and the company-wide default settings.
 * Safe to run repeatedly — it only fills in what is missing.
 *
 *   npm run seed            seed defaults
 *   npm run seed -- --demo  also insert demo customers / quotes for training
 *   npm run reset           wipe business data and reseed (keeps users)
 */
import { config } from './config.js';
import { db, all, get, run, insert, getSetting, setSetting, transaction } from './db.js';
import { hashPassword } from './auth.js';
import { COMPANY, SCOPE, PAYMENT_TERMS, CONDITIONS, COUNTRY_DEFAULTS, INTRO, PRICE_ADJUSTMENT_CLAUSE, DEFAULT_ITEM } from './templates.js';
import { round2, computeTotals } from './pricing.js';

export function seedSettings() {
  const company = getSetting('company');
  if (!company) {
    setSetting('company', COMPANY);
  } else if (!company.branches) {
    // An installation created before per-country branches existed: fold the
    // old single contact block into the default branch and add the rest,
    // without touching anything the company has already edited.
    const legacy = {
      cr_number: company.cr_number || '',
      vat_number: company.vat_number || '',
      phone: company.phone || '',
      email: company.email || '',
      website: company.website || '',
      address_en: company.address_en || '',
      address_ar: company.address_ar || '',
    };
    const branches = JSON.parse(JSON.stringify(COMPANY.branches));
    const fallbackKey = COMPANY.default_branch || 'SA';
    for (const [key, value] of Object.entries(legacy)) {
      if (value) branches[fallbackKey][key] = value;
    }
    setSetting('company', {
      ...COMPANY,
      ...company,
      legal_form_ar: company.legal_form_ar || COMPANY.legal_form_ar,
      legal_form_en: company.legal_form_en || COMPANY.legal_form_en,
      default_branch: company.default_branch || fallbackKey,
      branches,
    });
  }

  // Corrections to branches that already exist in the database. These run on
  // every start, so each one has to recognise its own placeholder and refuse to
  // touch anything the company has edited since.
  const stored = getSetting('company');
  let corrected = false;

  // A short-lived seed carried the wrong Saudi commercial registration.
  if (stored?.branches?.SA?.cr_number === '1010981534') {
    stored.branches.SA.cr_number = COMPANY.branches.SA.cr_number;
    corrected = true;
  }

  // Qatar shipped as a placeholder — the group name and address with no
  // registration, phone or email. The real branch trades under its own name
  // and mark, so fill the whole thing in, but only while it is still that
  // placeholder: any contact detail present means someone has been here.
  const qa = stored?.branches?.QA;
  if (qa && !qa.cr_number && !qa.phone && !qa.email) {
    stored.branches.QA = { ...qa, ...COMPANY.branches.QA };
    corrected = true;
  }

  if (corrected) setSetting('company', stored);

  if (!getSetting('scope')) setSetting('scope', SCOPE);
  if (!getSetting('payment_terms')) setSetting('payment_terms', PAYMENT_TERMS);
  if (!getSetting('conditions')) setSetting('conditions', CONDITIONS);
  if (!getSetting('countries')) setSetting('countries', COUNTRY_DEFAULTS);
  if (!getSetting('intro')) setSetting('intro', INTRO);
  if (!getSetting('price_clause')) setSetting('price_clause', PRICE_ADJUSTMENT_CLAUSE);
  if (!getSetting('quote_prefix')) setSetting('quote_prefix', 'SPAN TECH P.T');
}

/**
 * Brings the code sequences up to the highest code actually in the tables.
 *
 * The demo data is written with codes numbered from one and never touched the
 * counters, so on a seeded database the first customer an engineer added
 * reused a code the seed had already taken and the insert failed against the
 * unique index. Running this on every start also heals a database restored
 * from a backup or edited by hand, and it never lowers a counter.
 */
export function reconcileCounters() {
  const trailing = (value) => {
    const match = /(\d+)\s*$/.exec(String(value ?? ''));
    return match ? Number(match[1]) : 0;
  };

  const raise = (key, highest) => {
    if (!highest) return;
    const current = get('SELECT value FROM counters WHERE key = ?', key);
    if (current && current.value >= highest) return;
    run(
      `INSERT INTO counters (key, value) VALUES (?, ?)
       ON CONFLICT(key) DO UPDATE SET value = excluded.value`,
      key, highest,
    );
  };

  const highestCode = (table) => all(`SELECT code FROM ${table}`)
    .reduce((top, row) => Math.max(top, trailing(row.code)), 0);

  raise('customer', highestCode('customers'));
  raise('opportunity', highestCode('opportunities'));

  // A quotation number restarts its sequence every calendar year, so each year
  // carries its own counter.
  const perYear = new Map();
  for (const row of all('SELECT number, issue_date FROM quotations')) {
    const year = String(row.issue_date || '').slice(0, 4);
    if (year.length !== 4) continue;
    perYear.set(year, Math.max(perYear.get(year) || 0, trailing(row.number)));
  }
  for (const [year, highest] of perYear) raise(`quote_${year}`, highest);
}

export function seedAdmin() {
  const existing = get('SELECT COUNT(*) AS n FROM users').n;
  if (existing > 0) return null;
  const id = insert('users', {
    name: config.admin.name,
    name_ar: 'مدير النظام',
    email: config.admin.email,
    password_hash: hashPassword(config.admin.password),
    role: 'admin',
    title: 'System Administrator',
    title_ar: 'مدير النظام',
    country: 'SA',
    lang: 'ar',
  });
  return { id, email: config.admin.email, password: config.admin.password };
}

function seedDemo() {
  if (get('SELECT COUNT(*) AS n FROM customers').n > 0) {
    console.log('  demo data skipped — customers already exist');
    return;
  }
  const owner = get("SELECT id FROM users ORDER BY id LIMIT 1")?.id ?? null;

  const engineers = [
    { name: 'Ahmed Mostafa', name_ar: 'أحمد مصطفى', email: 'ahmed@spantechksa.com', role: 'manager', title: 'Technical Office Manager', title_ar: 'مدير المكتب الفني', country: 'SA' },
    { name: 'Mahmoud Saleh', name_ar: 'محمود صالح', email: 'mahmoud@spantechksa.com', role: 'engineer', title: 'Project Engineer', title_ar: 'مهندس مشاريع', country: 'EG' },
    { name: 'Khaled Al-Harbi', name_ar: 'خالد الحربي', email: 'khaled@spantechksa.com', role: 'engineer', title: 'Sales Engineer', title_ar: 'مهندس مبيعات', country: 'QA' },
  ];
  const engineerIds = engineers.map((e) =>
    insert('users', { ...e, password_hash: hashPassword('SpanTech@2026'), lang: 'ar' }),
  );

  const customers = [
    { name_en: 'Al Rajhi Development', name_ar: 'الراجحي للتطوير', type: 'developer', country: 'SA', city: 'Riyadh', sector: 'residential', status: 'active', source: 'referral', rating: 5, owner_id: engineerIds[0] },
    { name_en: 'Nesma & Partners', name_ar: 'نسما وشركاه', type: 'main_contractor', country: 'SA', city: 'Jeddah', sector: 'commercial', status: 'prospect', source: 'exhibition', rating: 4, owner_id: engineerIds[0] },
    { name_en: 'Orascom Construction', name_ar: 'أوراسكوم للإنشاءات', type: 'main_contractor', country: 'EG', city: 'Cairo', sector: 'mixed', status: 'target', source: 'cold_call', rating: 4, owner_id: engineerIds[1] },
    { name_en: 'Hassan Allam Holding', name_ar: 'حسن علام القابضة', type: 'main_contractor', country: 'EG', city: 'New Capital', sector: 'infrastructure', status: 'prospect', source: 'tender', rating: 5, owner_id: engineerIds[1] },
    { name_en: 'UrbaCon Trading & Contracting', name_ar: 'أوربكون للتجارة والمقاولات', type: 'main_contractor', country: 'QA', city: 'Doha', sector: 'commercial', status: 'target', source: 'website', rating: 3, owner_id: engineerIds[2] },
    { name_en: 'Dar Al-Handasah', name_ar: 'دار الهندسة', type: 'consultant', country: 'SA', city: 'Riyadh', sector: 'education', status: 'active', source: 'existing', rating: 5, owner_id: engineerIds[0] },
  ];

  const today = new Date();
  const iso = (offsetDays) => {
    const d = new Date(today);
    d.setDate(d.getDate() + offsetDays);
    return d.toISOString().slice(0, 10);
  };

  customers.forEach((customer, index) => {
    const customerId = insert('customers', { ...customer, code: `C-${String(index + 1).padStart(4, '0')}`, created_by: owner });
    insert('contacts', {
      customer_id: customerId,
      name: ['Shaker Al-Sharif', 'Omar Fathy', 'Tarek Zaki', 'Nour El-Din', 'Ali Al-Kuwari', 'Sami Habib'][index],
      title: ['Projects Director', 'Procurement Manager', 'Technical Manager', 'Structural Lead', 'Contracts Manager', 'Design Manager'][index],
      mobile: '+9665' + String(10000000 + index * 137),
      is_primary: 1,
    });
  });

  const opportunities = [
    { title: 'Rest House — Riyadh', title_ar: 'استراحة — الرياض', customer_id: 1, country: 'SA', city: 'Riyadh', project_type: 'rest_house', area_sqm: 476, stage: 'quoted', probability: 60, expected_value: 33320, currency: 'SAR', source: 'referral', owner_id: engineerIds[0], expected_close: iso(20) },
    { title: 'Residential Tower A — Jeddah', title_ar: 'برج سكني أ — جدة', customer_id: 2, country: 'SA', city: 'Jeddah', project_type: 'tower', area_sqm: 9800, stage: 'negotiation', probability: 75, expected_value: 686000, currency: 'SAR', source: 'exhibition', owner_id: engineerIds[0], expected_close: iso(35) },
    { title: 'New Capital Mall', title_ar: 'مول العاصمة الإدارية', customer_id: 4, country: 'EG', city: 'New Capital', project_type: 'mall', area_sqm: 21000, stage: 'qualified', probability: 35, expected_value: 18900000, currency: 'EGP', source: 'tender', owner_id: engineerIds[1], expected_close: iso(60) },
    { title: 'Logistics Warehouse', title_ar: 'مستودع لوجستي', customer_id: 3, country: 'EG', city: 'Cairo', project_type: 'industrial', area_sqm: 6400, stage: 'new', probability: 10, expected_value: 5760000, currency: 'EGP', source: 'cold_call', owner_id: engineerIds[1], expected_close: iso(75) },
    { title: 'Lusail Office Block', title_ar: 'مبنى مكاتب لوسيل', customer_id: 5, country: 'QA', city: 'Lusail', project_type: 'admin', area_sqm: 12500, stage: 'won', probability: 100, expected_value: 937500, currency: 'QAR', source: 'website', owner_id: engineerIds[2], expected_close: iso(-10), closed_at: iso(-10) },
    { title: 'Girls School — Riyadh', title_ar: 'مدرسة بنات — الرياض', customer_id: 6, country: 'SA', city: 'Riyadh', project_type: 'school', area_sqm: 3200, stage: 'won', probability: 100, expected_value: 224000, currency: 'SAR', source: 'existing', owner_id: engineerIds[0], expected_close: iso(-40), closed_at: iso(-40) },
    { title: 'Coastal Villas Compound', title_ar: 'مجمع فلل ساحلي', customer_id: 2, country: 'SA', city: 'Jeddah', project_type: 'villa', area_sqm: 2100, stage: 'lost', probability: 0, expected_value: 147000, currency: 'SAR', source: 'referral', owner_id: engineerIds[0], lost_reason: 'price', lost_to: 'Local competitor', closed_at: iso(-25) },
  ];
  opportunities.forEach((opp, index) =>
    insert('opportunities', { ...opp, code: `OPP-${String(index + 1).padStart(4, '0')}`, created_by: owner }),
  );

  // --- quotations, so the pricing side of the demo is populated too --------
  const quotes = [
    {
      opportunity_id: 1, customer_id: 1, country: 'SA', currency: 'SAR', vat_rate: 15,
      project_name: 'Rest House — Riyadh', project_name_ar: 'استراحة — بمدينة الرياض',
      location: 'Riyadh', attention: 'Shaker Al-Sharif', attention_ar: 'شاكر الشريف',
      area: 476, price: 70, status: 'sent', owner_id: engineerIds[0], issue: iso(-8),
      costs: { labour_cost_sqm: 17, duct_cost_sqm: 4, grout_cost_sqm: 2, design_cost_sqm: 3, anchor_cost: 22, overhead_pct: 8 },
    },
    {
      opportunity_id: 2, customer_id: 2, country: 'SA', currency: 'SAR', vat_rate: 15,
      project_name: 'Residential Tower A — Jeddah', project_name_ar: 'برج سكني أ — جدة',
      location: 'Jeddah', attention: 'Omar Fathy', area: 9800, price: 66,
      status: 'under_review', owner_id: engineerIds[0], issue: iso(-15),
      costs: { labour_cost_sqm: 15, duct_cost_sqm: 3.5, grout_cost_sqm: 1.8, design_cost_sqm: 2, anchor_cost: 20, overhead_pct: 7 },
    },
    {
      opportunity_id: 6, customer_id: 6, country: 'SA', currency: 'SAR', vat_rate: 15,
      project_name: 'Girls School — Riyadh', project_name_ar: 'مدرسة بنات — الرياض',
      location: 'Riyadh', attention: 'Sami Habib', area: 3200, price: 70,
      status: 'approved', owner_id: engineerIds[0], issue: iso(-52),
      costs: { labour_cost_sqm: 16, duct_cost_sqm: 4, grout_cost_sqm: 2, design_cost_sqm: 2.5, anchor_cost: 21, overhead_pct: 8 },
    },
    {
      opportunity_id: 5, customer_id: 5, country: 'QA', currency: 'QAR', vat_rate: 0,
      project_name: 'Lusail Office Block', project_name_ar: 'مبنى مكاتب لوسيل',
      location: 'Lusail', attention: 'Ali Al-Kuwari', area: 12500, price: 75,
      status: 'approved', owner_id: engineerIds[2], issue: iso(-22),
      costs: { labour_cost_sqm: 18, duct_cost_sqm: 4.5, grout_cost_sqm: 2.2, design_cost_sqm: 3, anchor_cost: 24, overhead_pct: 9 },
    },
    {
      opportunity_id: 3, customer_id: 4, country: 'EG', currency: 'EGP', vat_rate: 14,
      project_name: 'New Capital Mall', project_name_ar: 'مول العاصمة الإدارية',
      location: 'New Capital', attention: 'Nour El-Din', area: 21000, price: 900,
      status: 'draft', owner_id: engineerIds[1], issue: iso(-3),
      costs: { labour_cost_sqm: 210, duct_cost_sqm: 55, grout_cost_sqm: 28, design_cost_sqm: 35, anchor_cost: 380, overhead_pct: 8 },
    },
  ];

  const scope = getSetting('scope', SCOPE);
  const terms = getSetting('payment_terms', PAYMENT_TERMS);
  const conditions = getSetting('conditions', CONDITIONS);

  quotes.forEach((quote, index) => {
    const book = COUNTRY_DEFAULTS[quote.country];
    const subtotal = round2(quote.area * quote.price);
    const vat = round2(subtotal * (quote.vat_rate / 100));
    const quotationId = insert('quotations', {
      number: `SPAN TECH P.T - ${quote.issue.slice(2, 4)} - ${String(index + 1).padStart(3, '0')}`,
      revision: 0,
      opportunity_id: quote.opportunity_id,
      customer_id: quote.customer_id,
      project_name: quote.project_name,
      project_name_ar: quote.project_name_ar,
      location: quote.location,
      attention: quote.attention,
      attention_ar: quote.attention_ar || null,
      subject_en: 'Quotation for the design, supply and execution of post-tensioned slab works',
      subject_ar: 'عرض سعر تصميم وتوريد وتنفيذ أعمال الأسقف اللاحقة للشد',
      country: quote.country,
      currency: quote.currency,
      vat_rate: quote.vat_rate,
      issue_date: quote.issue,
      valid_days: book.valid_days,
      status: quote.status,
      strand_price_ton: book.strand_price_ton,
      strand_kg_sqm: book.strand_kg_sqm,
      anchors_per_ton: book.anchors_per_ton,
      target_margin: 20,
      ...quote.costs,
      subtotal,
      net_amount: subtotal,
      vat_amount: vat,
      total: round2(subtotal + vat),
      scope_json: JSON.stringify(scope),
      payment_terms_json: JSON.stringify(terms),
      conditions_json: JSON.stringify(conditions),
      owner_id: quote.owner_id,
      created_by: owner,
      sent_at: quote.status === 'draft' ? null : new Date().toISOString(),
    });
    insert('quotation_items', {
      quotation_id: quotationId,
      sort_order: 0,
      desc_en: DEFAULT_ITEM.desc_en,
      desc_ar: DEFAULT_ITEM.desc_ar,
      unit_en: DEFAULT_ITEM.unit_en,
      unit_ar: DEFAULT_ITEM.unit_ar,
      qty: quote.area,
      unit_price: quote.price,
      amount: subtotal,
    });

    // Run the real pricing engine so the demo carries realistic cost/margin data.
    const row = get('SELECT * FROM quotations WHERE id = ?', quotationId);
    const items = all('SELECT * FROM quotation_items WHERE quotation_id = ?', quotationId);
    const totals = computeTotals(row, items);
    run(
      `UPDATE quotations SET cost_total = ?, margin_amount = ?, margin_pct = ? WHERE id = ?`,
      totals.cost_total, totals.margin_amount, totals.margin_pct, quotationId,
    );
  });

  const activities = [
    { type: 'call', subject: 'متابعة عرض سعر الاستراحة', customer_id: 1, opportunity_id: 1, owner_id: engineerIds[0], due_at: iso(-2) + 'T09:00:00.000Z' },
    { type: 'meeting', subject: 'اجتماع فني مع الاستشاري', customer_id: 6, opportunity_id: 6, owner_id: engineerIds[0], due_at: iso(0) + 'T11:00:00.000Z' },
    { type: 'whatsapp', subject: 'إرسال جدول الكميات المحدّث', customer_id: 2, opportunity_id: 2, owner_id: engineerIds[0], due_at: iso(1) + 'T08:30:00.000Z' },
    { type: 'email', subject: 'إرسال ملف الشركة والتأهيل المسبق', customer_id: 3, opportunity_id: 4, owner_id: engineerIds[1], due_at: iso(3) + 'T07:00:00.000Z' },
    { type: 'site_visit', subject: 'زيارة موقع — مول العاصمة الإدارية', customer_id: 4, opportunity_id: 3, owner_id: engineerIds[1], due_at: iso(6) + 'T06:00:00.000Z' },
    { type: 'call', subject: 'مكالمة تعريفية', customer_id: 5, opportunity_id: 5, owner_id: engineerIds[2], due_at: iso(-12) + 'T10:00:00.000Z', done: 1, done_at: iso(-12), outcome: 'إيجابية — طلبوا عرض سعر رسمي' },
  ];
  activities.forEach((activity) => insert('activities', { ...activity, created_by: owner }));

  // The rows above are numbered by hand, so hand the sequences back in step
  // before anyone adds a customer of their own.
  reconcileCounters();

  console.log(`  demo data: ${customers.length} customers, ${opportunities.length} opportunities, ${activities.length} activities`);
  console.log('  demo engineer logins use password: SpanTech@2026');
}

function resetBusinessData() {
  transaction(() => {
    for (const table of ['activities', 'quotation_items', 'quotations', 'opportunities', 'contacts', 'customers', 'audit_log']) {
      run(`DELETE FROM ${table}`);
    }
    run("DELETE FROM counters WHERE key LIKE 'quote%' OR key LIKE 'customer%' OR key LIKE 'opp%'");
  });
  console.log('  business data cleared');
}

function main() {
  const args = process.argv.slice(2);
  console.log(`Span Tech CRM — seeding ${config.dbPath}`);

  if (args.includes('--reset')) resetBusinessData();

  seedSettings();
  console.log('  settings ready');

  const admin = seedAdmin();
  if (admin) {
    console.log('\n  Administrator created:');
    console.log(`    email:    ${admin.email}`);
    console.log(`    password: ${admin.password}`);
    console.log('    Change this password after your first sign-in.\n');
  } else {
    console.log('  users already present — admin not recreated');
  }

  if (args.includes('--demo')) seedDemo();

  db.close();
  console.log('Done.');
}

if (import.meta.url === `file://${process.argv[1]}`) main();
