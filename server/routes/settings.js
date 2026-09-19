import { allSettings, getSetting, setSetting, audit } from '../db.js';
import { requirePermission } from '../auth.js';
import { badRequest } from '../http.js';
import { COMPANY, SCOPE, PAYMENT_TERMS, CONDITIONS, COUNTRY_DEFAULTS, INTRO, PRICE_ADJUSTMENT_CLAUSE } from '../templates.js';

const DEFAULTS = {
  company: COMPANY,
  scope: SCOPE,
  payment_terms: PAYMENT_TERMS,
  conditions: CONDITIONS,
  countries: COUNTRY_DEFAULTS,
  intro: INTRO,
  price_clause: PRICE_ADJUSTMENT_CLAUSE,
  quote_prefix: 'SPAN TECH P.T',
};

const EDITABLE = Object.keys(DEFAULTS);

export function register(router) {
  router.get('/api/settings', ({ user }) => {
    requirePermission(user, 'settings.view');
    const stored = allSettings();
    const out = {};
    for (const key of EDITABLE) out[key] = stored[key] ?? DEFAULTS[key];
    return { settings: out };
  });

  router.put('/api/settings/:key', ({ params, body, user }) => {
    requirePermission(user, 'settings.edit');
    const { key } = params;
    if (!EDITABLE.includes(key)) {
      throw badRequest(`Unknown setting "${key}"`, `إعداد غير معروف "${key}"`);
    }
    if (body.value === undefined) {
      throw badRequest('A "value" field is required', 'حقل "value" مطلوب');
    }
    setSetting(key, body.value);
    audit(user.id, 'settings', null, 'update', { key });
    return { key, value: getSetting(key) };
  });

  router.post('/api/settings/:key/reset', ({ params, user }) => {
    requirePermission(user, 'settings.edit');
    const { key } = params;
    if (!EDITABLE.includes(key)) {
      throw badRequest(`Unknown setting "${key}"`, `إعداد غير معروف "${key}"`);
    }
    setSetting(key, DEFAULTS[key]);
    audit(user.id, 'settings', null, 'reset', { key });
    return { key, value: DEFAULTS[key] };
  });
}
