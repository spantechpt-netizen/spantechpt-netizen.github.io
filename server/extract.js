/**
 * Pulls customer and project details out of an incoming email.
 *
 * Two layers:
 *   1. Heuristics — always run, work offline, and cost nothing. They match the
 *      sender against customers you already have, read the subject, and pick
 *      out areas, money, locations and phone numbers.
 *   2. Claude — optional. When an API key is configured in Settings, the email
 *      is also sent to Claude for a proper structured read, which handles free
 *      Arabic prose far better than any regex. Its answer is merged over the
 *      heuristics, and every field records where it came from.
 *
 * Nothing is created automatically: extraction fills a draft that a human
 * reviews before it becomes a customer or an opportunity.
 */
import { all, get, getSetting } from './db.js';

// Free mail providers never identify a company, so never match on them.
const PUBLIC_DOMAINS = new Set([
  'gmail.com', 'googlemail.com', 'hotmail.com', 'outlook.com', 'live.com',
  'yahoo.com', 'yahoo.co.uk', 'icloud.com', 'me.com', 'aol.com',
  'protonmail.com', 'proton.me', 'yandex.com', 'mail.com', 'gmx.com',
]);

const COUNTRY_HINTS = [
  { code: 'SA', patterns: [/\bksa\b/i, /saudi/i, /\.sa\b/i, /riyadh/i, /jeddah/i, /dammam/i, /khobar/i, /makkah|mecca/i, /medina|madinah/i,
    /السعودية/, /الرياض/, /جدة/, /الدمام/, /الخبر/, /مكة/, /المدينة/, /\+?966/] },
  { code: 'EG', patterns: [/egypt/i, /\.eg\b/i, /cairo/i, /giza/i, /alexandria/i, /new capital/i, /\bsheikh zayed\b/i,
    /مصر/, /القاهرة/, /الجيزة/, /الإسكندرية|الاسكندرية/, /العاصمة الإدارية/, /الشيخ زايد/, /\+?20\b/] },
  { code: 'QA', patterns: [/qatar/i, /\.qa\b/i, /doha/i, /lusail/i, /\bal wakrah\b/i,
    /قطر/, /الدوحة/, /لوسيل/, /\+?974/] },
];

const PROJECT_TYPE_HINTS = [
  { type: 'tower', patterns: [/tower/i, /high[- ]?rise/i, /برج/] },
  { type: 'school', patterns: [/school/i, /مدرسة/, /مدارس/] },
  { type: 'mall', patterns: [/\bmall\b/i, /shopping/i, /مول/, /تجاري/] },
  { type: 'villa', patterns: [/villa/i, /compound/i, /فيلا/, /فلل/, /مجمع سكني/] },
  { type: 'rest_house', patterns: [/rest house/i, /استراحة/] },
  { type: 'hospital', patterns: [/hospital/i, /clinic/i, /مستشفى/, /مستوصف/] },
  { type: 'parking', patterns: [/car park/i, /parking/i, /مواقف/, /جراج/] },
  { type: 'industrial', patterns: [/warehouse/i, /factory/i, /industrial/i, /logistics/i, /مستودع/, /مصنع/, /صناعي/] },
  { type: 'admin', patterns: [/office building/i, /administrative/i, /\bhq\b/i, /مبنى إداري/, /مقر/] },
];

/** Subjects that look like a request for a price. */
const RFQ_PATTERNS = [
  /\brfq\b/i, /request for quot/i, /\bquotation\b/i, /\bquote\b/i, /\btender\b/i,
  /\bbid\b/i, /pricing/i, /price offer/i, /budget(?:ary)? (?:price|offer)/i,
  /عرض سعر/, /طلب سعر/, /تسعير/, /تسعيرة/, /مناقصة/, /عطاء/, /دراسة سعر/,
];

const POST_TENSION_PATTERNS = [
  /post[- ]?tension/i, /\bpt slab/i, /prestress/i, /unbonded/i, /bonded tendon/i,
  /لاحقة الشد/, /لاحق الشد/, /اللاحقة للشد/, /بوست تنشن/, /سابقة الإجهاد/,
];

// ============================================================== heuristics

/** Everything after the last "@". */
export const domainOf = (email) => String(email || '').split('@')[1]?.toLowerCase() || null;

export const isPublicDomain = (domain) => !domain || PUBLIC_DOMAINS.has(domain);

/**
 * Finds an existing customer for this sender: first by an exact contact email,
 * then by the company's own email domain, then by a name appearing in the text.
 */
export function matchCustomer({ fromEmail, fromName, subject = '', body = '' }) {
  const domain = domainOf(fromEmail);

  if (fromEmail) {
    const byContact = get(
      `SELECT c.*, ct.id AS contact_id, ct.name AS contact_name
         FROM contacts ct JOIN customers c ON c.id = ct.customer_id
        WHERE lower(ct.email) = ?`,
      String(fromEmail).toLowerCase(),
    );
    if (byContact) return { customer: byContact, contactId: byContact.contact_id, how: 'contact_email' };

    const byCustomerEmail = get('SELECT * FROM customers WHERE lower(email) = ?', String(fromEmail).toLowerCase());
    if (byCustomerEmail) return { customer: byCustomerEmail, contactId: null, how: 'customer_email' };
  }

  if (domain && !isPublicDomain(domain)) {
    const byDomain = get(
      `SELECT * FROM customers
        WHERE lower(email) LIKE ? OR lower(website) LIKE ?
        LIMIT 1`,
      `%@${domain}`, `%${domain}%`,
    );
    if (byDomain) return { customer: byDomain, contactId: null, how: 'domain' };

    const byContactDomain = get(
      `SELECT c.*, ct.id AS contact_id
         FROM contacts ct JOIN customers c ON c.id = ct.customer_id
        WHERE lower(ct.email) LIKE ?
        LIMIT 1`,
      `%@${domain}`,
    );
    if (byContactDomain) {
      return { customer: byContactDomain, contactId: null, how: 'contact_domain' };
    }
  }

  // Last resort: a known customer's name written in the subject or body.
  const haystack = `${subject}\n${body}`.toLowerCase();
  for (const customer of all('SELECT * FROM customers')) {
    for (const name of [customer.name_en, customer.name_ar]) {
      if (!name || name.length < 5) continue;
      if (haystack.includes(name.toLowerCase())) {
        return { customer, contactId: null, how: 'name_in_text' };
      }
    }
  }

  void fromName;
  return { customer: null, contactId: null, how: null };
}

/** Area in m², handling 9,800 / 9800 / ٩٨٠٠ and m2 / m² / متر / م٢. */
export function extractArea(text) {
  if (!text) return null;
  const normalised = normaliseDigits(text);
  const patterns = [
    /([\d][\d,.\s]{0,12}\d|\d)\s*(?:m2|m²|sqm|sq\.?\s?m|square\s*met(?:er|re)s?)/gi,
    /([\d][\d,.\s]{0,12}\d|\d)\s*(?:م2|م²|متر\s*مربع|م\.?م)/g,
    /(?:area|المساحة|مساحة)\s*[:=\-]?\s*([\d][\d,.\s]{0,12}\d|\d)/gi,
  ];

  const found = [];
  for (const pattern of patterns) {
    for (const match of normalised.matchAll(pattern)) {
      const value = Number(String(match[1]).replace(/[,\s]/g, ''));
      // Below 50 m² is almost certainly a thickness or a typo, not a slab.
      if (Number.isFinite(value) && value >= 50 && value <= 5_000_000) found.push(value);
    }
  }
  if (!found.length) return null;
  // The largest figure is usually the total slab area rather than one floor.
  return Math.max(...found);
}

/** Converts Arabic-Indic digits so the numeric regexes above can see them. */
export function normaliseDigits(text) {
  return String(text)
    .replace(/[٠-٩]/g, (d) => String(d.charCodeAt(0) - 0x0660))
    .replace(/[۰-۹]/g, (d) => String(d.charCodeAt(0) - 0x06F0));
}

export function detectCountry(text) {
  for (const { code, patterns } of COUNTRY_HINTS) {
    if (patterns.some((p) => p.test(text))) return code;
  }
  return null;
}

export function detectProjectType(text) {
  for (const { type, patterns } of PROJECT_TYPE_HINTS) {
    if (patterns.some((p) => p.test(text))) return type;
  }
  return null;
}

export const looksLikeRfq = (text) => RFQ_PATTERNS.some((p) => p.test(text));
export const mentionsPostTension = (text) => POST_TENSION_PATTERNS.some((p) => p.test(text));

/** Phone numbers in Gulf/Egypt shapes, de-duplicated. */
export function extractPhones(text) {
  const normalised = normaliseDigits(text);
  const matches = normalised.match(/(?:\+|00)?\d[\d\s\-()]{7,17}\d/g) || [];
  const cleaned = matches
    .map((m) => m.replace(/[\s\-()]/g, ''))
    .filter((m) => m.replace(/\D/g, '').length >= 9 && m.replace(/\D/g, '').length <= 15)
    // Drop anything that is obviously a quantity, a date or a price.
    .filter((m) => !/^\d{4}$/.test(m));
  return [...new Set(cleaned)].slice(0, 4);
}

/**
 * Guesses the project name: a labelled line wins, otherwise the subject with
 * its RFQ boilerplate and Re:/Fwd: prefixes stripped.
 */
export function extractProjectName(subject, body) {
  const labelled = /(?:project|مشروع|المشروع)\s*[:\-–]\s*(.{3,90})/i.exec(`${subject}\n${body}`);
  if (labelled) return tidy(labelled[1]);

  let name = String(subject || '')
    .replace(/^((re|fw|fwd|rv)\s*:\s*)+/i, '')
    .replace(/^((رد|إعادة توجيه|اعادة توجيه)\s*:\s*)+/, '')
    .replace(/\b(rfq|request for quotation|quotation|quote|tender|enquiry|inquiry)\b/gi, '')
    .replace(/(طلب\s*)?عرض\s*سعر|طلب\s*سعر|تسعير(ة)?|مناقصة/g, '')
    .replace(/^[\s\-–—:،,|]+|[\s\-–—:،,|]+$/g, '');

  name = tidy(name);
  return name.length >= 3 ? name : null;
}

/** A company name from the sender's display name or signature. */
export function extractCompanyName(fromName, body, domain) {
  const suffixes = /(contracting|construction|engineering|consultants?|group|holding|company|co\.?|llc|w\.l\.l|est\.?|trading|للمقاولات|للإنشاءات|للاستشارات|هندسية|القابضة|مجموعة)/i;

  for (const line of String(body || '').split('\n').slice(0, 40)) {
    const trimmed = tidy(line);
    if (trimmed.length > 4 && trimmed.length < 70 && suffixes.test(trimmed) && !trimmed.includes('@')) {
      return trimmed;
    }
  }
  if (fromName && suffixes.test(fromName)) return tidy(fromName);
  if (domain && !isPublicDomain(domain)) {
    // acme-contracting.com.sa → "Acme Contracting"
    const base = domain.split('.')[0].replace(/[-_]+/g, ' ');
    return base.replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return null;
}

const tidy = (text) => String(text || '').replace(/\s+/g, ' ').trim();

/**
 * The offline pass. Returns a draft plus a confidence score, where every
 * field notes its source so the reviewer can see what was guessed.
 */
export function heuristicExtract({ fromEmail, fromName, subject, body, receivedAt }) {
  const text = `${subject || ''}\n${body || ''}`;
  const domain = domainOf(fromEmail);
  const match = matchCustomer({ fromEmail, fromName, subject, body });

  const area = extractArea(text);
  const country = detectCountry(text) || match.customer?.country || null;
  const projectType = detectProjectType(text);
  const projectName = extractProjectName(subject, body);
  const isRfq = looksLikeRfq(text);
  const isPt = mentionsPostTension(text);

  // Confidence is about how much we could pin down, not whether it is an RFQ.
  let confidence = 0;
  if (match.customer) confidence += 30;
  else if (domain && !isPublicDomain(domain)) confidence += 10;
  if (projectName) confidence += 20;
  if (area) confidence += 25;
  if (country) confidence += 10;
  if (projectType) confidence += 10;
  if (isPt) confidence += 5;

  return {
    source: 'heuristic',
    is_rfq: isRfq,
    mentions_post_tension: isPt,
    confidence: Math.min(confidence, 100),
    customer: {
      matched_id: match.customer?.id || null,
      matched_by: match.how,
      name: match.customer
        ? (match.customer.name_en || match.customer.name_ar)
        : extractCompanyName(fromName, body, domain),
      country,
      city: null,
      email: fromEmail || null,
      domain,
    },
    contact: {
      matched_id: match.contactId,
      name: fromName || null,
      email: fromEmail || null,
      phones: extractPhones(body || ''),
    },
    project: {
      name: projectName,
      type: projectType,
      area_sqm: area,
      country,
      city: null,
      expected_close: null,
    },
    received_at: receivedAt || null,
    notes: null,
  };
}

// ================================================================== Claude

/**
 * Sends the email to Claude for a structured read. Returns null when no key
 * is configured or the call fails — the heuristics still stand on their own,
 * so extraction never depends on the network.
 */
export async function claudeExtract({ subject, body, fromEmail, fromName }) {
  const settings = getSetting('ai', {}) || {};
  const apiKey = settings.api_key;
  if (!apiKey) return null;

  const model = settings.model || 'claude-sonnet-5';
  const endpoint = settings.endpoint || 'https://api.anthropic.com/v1/messages';

  const schema = {
    is_rfq: 'boolean — true if this email asks for a price, quotation or tender submission',
    mentions_post_tension: 'boolean — true if post-tensioned / prestressed slabs are mentioned',
    customer_name: 'string|null — the client company name, not the sender’s personal name',
    contact_name: 'string|null — the person writing',
    contact_phone: 'string|null',
    country: 'string|null — one of SA, EG, QA',
    city: 'string|null',
    project_name: 'string|null — the project, without RFQ boilerplate',
    project_type: 'string|null — one of tower, school, mall, villa, rest_house, hospital, parking, industrial, admin, other',
    area_sqm: 'number|null — total slab area in square metres',
    deadline: 'string|null — ISO date (YYYY-MM-DD) if a submission deadline is stated',
    summary_ar: 'string — one or two sentences in Arabic saying what the client wants',
    summary_en: 'string — the same in English',
  };

  const prompt = [
    'You are reading an email that arrived at a post-tensioning subcontractor in the Gulf and Egypt.',
    'Extract the facts below and reply with JSON only — no prose, no code fence.',
    'Use null for anything the email does not state. Never invent a value.',
    '',
    'Fields:',
    JSON.stringify(schema, null, 2),
    '',
    '--- EMAIL ---',
    `From: ${fromName || ''} <${fromEmail || ''}>`,
    `Subject: ${subject || ''}`,
    '',
    String(body || '').slice(0, 12_000),
  ].join('\n');

  let response;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30_000);
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model,
        max_tokens: 1200,
        messages: [{ role: 'user', content: prompt }],
      }),
      signal: controller.signal,
    });
    clearTimeout(timer);
  } catch (error) {
    console.warn('[ai] extraction call failed:', error.message);
    return null;
  }

  if (!response.ok) {
    console.warn('[ai] extraction rejected:', response.status, (await response.text()).slice(0, 300));
    return null;
  }

  let parsed;
  try {
    const payload = await response.json();
    const text = (payload.content || []).map((block) => block.text || '').join('').trim();
    // Be forgiving if the model wraps the JSON in a fence anyway.
    const json = text.replace(/^```(?:json)?\s*|\s*```$/g, '');
    parsed = JSON.parse(json.slice(json.indexOf('{'), json.lastIndexOf('}') + 1));
  } catch (error) {
    console.warn('[ai] could not read the extraction reply:', error.message);
    return null;
  }

  return { source: 'claude', model, ...parsed };
}

/** Heuristics first, then Claude's answer merged over the top where present. */
export async function extractFromEmail(email, { useAi = true } = {}) {
  const base = heuristicExtract(email);
  if (!useAi) return base;

  const ai = await claudeExtract(email);
  if (!ai) return base;

  const prefer = (aiValue, fallback) =>
    (aiValue === undefined || aiValue === null || aiValue === '' ? fallback : aiValue);

  const merged = {
    ...base,
    source: 'heuristic+claude',
    ai_model: ai.model,
    is_rfq: typeof ai.is_rfq === 'boolean' ? ai.is_rfq : base.is_rfq,
    mentions_post_tension: typeof ai.mentions_post_tension === 'boolean'
      ? ai.mentions_post_tension : base.mentions_post_tension,
    summary_ar: ai.summary_ar || null,
    summary_en: ai.summary_en || null,
    customer: {
      ...base.customer,
      name: prefer(ai.customer_name, base.customer.name),
      country: prefer(normaliseCountry(ai.country), base.customer.country),
      city: prefer(ai.city, base.customer.city),
    },
    contact: {
      ...base.contact,
      name: prefer(ai.contact_name, base.contact.name),
      phones: ai.contact_phone
        ? [...new Set([ai.contact_phone, ...base.contact.phones])]
        : base.contact.phones,
    },
    project: {
      ...base.project,
      name: prefer(ai.project_name, base.project.name),
      type: prefer(normaliseProjectType(ai.project_type), base.project.type),
      area_sqm: Number.isFinite(Number(ai.area_sqm)) && Number(ai.area_sqm) > 0
        ? Number(ai.area_sqm) : base.project.area_sqm,
      country: prefer(normaliseCountry(ai.country), base.project.country),
      city: prefer(ai.city, base.project.city),
      expected_close: /^\d{4}-\d{2}-\d{2}$/.test(String(ai.deadline || ''))
        ? ai.deadline : base.project.expected_close,
    },
  };

  // Claude filling gaps is worth real confidence.
  let bonus = 0;
  if (ai.project_name && !base.project.name) bonus += 15;
  if (ai.area_sqm && !base.project.area_sqm) bonus += 15;
  if (ai.customer_name && !base.customer.name) bonus += 10;
  merged.confidence = Math.min(base.confidence + bonus, 100);

  return merged;
}

const normaliseCountry = (value) => {
  const text = String(value || '').trim().toUpperCase();
  if (['SA', 'EG', 'QA'].includes(text)) return text;
  return detectCountry(String(value || ''));
};

const normaliseProjectType = (value) => {
  const allowed = ['tower', 'school', 'mall', 'villa', 'rest_house', 'hospital', 'parking', 'industrial', 'admin', 'other'];
  const text = String(value || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  return allowed.includes(text) ? text : null;
};
