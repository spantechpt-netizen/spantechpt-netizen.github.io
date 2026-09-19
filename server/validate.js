import { badRequest } from './http.js';

const fail = (field, en, ar) => {
  throw badRequest(`${field}: ${en}`, `${field}: ${ar}`, { field });
};

export const str = (value, field, { required = false, max = 500, min = 0, fallback = undefined } = {}) => {
  if (value === undefined || value === null || value === '') {
    if (required) fail(field, 'is required', 'حقل مطلوب');
    return fallback;
  }
  const text = String(value).trim();
  if (text.length < min) fail(field, `must be at least ${min} characters`, `يجب ألا يقل عن ${min} حرف`);
  if (text.length > max) fail(field, `must be at most ${max} characters`, `يجب ألا يزيد عن ${max} حرف`);
  return text;
};

export const num = (value, field, { required = false, min = -1e12, max = 1e12, fallback = undefined } = {}) => {
  if (value === undefined || value === null || value === '') {
    if (required) fail(field, 'is required', 'حقل مطلوب');
    return fallback;
  }
  const n = Number(value);
  if (!Number.isFinite(n)) fail(field, 'must be a number', 'يجب أن يكون رقماً');
  if (n < min) fail(field, `must be ${min} or more`, `يجب ألا يقل عن ${min}`);
  if (n > max) fail(field, `must be ${max} or less`, `يجب ألا يزيد عن ${max}`);
  return n;
};

export const int = (value, field, opts = {}) => {
  const n = num(value, field, opts);
  // Preserve null / undefined exactly — they mean "clear" and "leave alone".
  return typeof n === 'number' ? Math.round(n) : n;
};

export const bool = (value, fallback = false) => {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());
};

export const oneOf = (value, field, allowed, { required = false, fallback = undefined } = {}) => {
  if (value === undefined || value === null || value === '') {
    if (required) fail(field, 'is required', 'حقل مطلوب');
    return fallback;
  }
  const text = String(value).trim();
  if (!allowed.includes(text)) {
    fail(field, `must be one of: ${allowed.join(', ')}`, `يجب أن يكون أحد الخيارات: ${allowed.join('، ')}`);
  }
  return text;
};

export const email = (value, field, { required = false, fallback = undefined } = {}) => {
  const text = str(value, field, { required, max: 200, fallback });
  if (text === null || text === undefined) return text;
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text)) {
    fail(field, 'is not a valid email address', 'صيغة البريد الإلكتروني غير صحيحة');
  }
  return text.toLowerCase();
};

export const date = (value, field, { required = false, fallback = undefined } = {}) => {
  const text = str(value, field, { required, max: 30, fallback });
  if (text === null || text === undefined) return text;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    fail(field, 'must be a date formatted YYYY-MM-DD', 'يجب أن يكون تاريخاً بصيغة YYYY-MM-DD');
  }
  return text;
};

export const datetime = (value, field, { required = false, fallback = undefined } = {}) => {
  const text = str(value, field, { required, max: 40, fallback });
  if (text === null || text === undefined) return text;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) {
    fail(field, 'must be a valid date/time', 'يجب أن يكون تاريخاً ووقتاً صحيحاً');
  }
  return parsed.toISOString();
};

export const jsonField = (value, field, fallback = null) => {
  if (value === undefined || value === null) return fallback;
  if (typeof value === 'string') {
    try { return JSON.parse(value); } catch { fail(field, 'is not valid JSON', 'صيغة البيانات غير صحيحة'); }
  }
  return value;
};

export const COUNTRIES = ['SA', 'EG', 'QA'];
export const CURRENCIES = ['SAR', 'EGP', 'QAR', 'USD'];
export const ROLES = ['admin', 'manager', 'engineer', 'viewer'];
export const CUSTOMER_TYPES = ['main_contractor', 'consultant', 'developer', 'owner', 'subcontractor', 'government', 'other'];
export const CUSTOMER_STATUS = ['target', 'prospect', 'active', 'dormant', 'blacklisted'];
export const STAGES = ['new', 'qualified', 'quoted', 'negotiation', 'won', 'lost'];
export const ACTIVITY_TYPES = ['call', 'meeting', 'email', 'whatsapp', 'site_visit', 'task', 'note'];
export const QUOTE_STATUS = ['draft', 'sent', 'under_review', 'approved', 'rejected', 'expired', 'cancelled'];
