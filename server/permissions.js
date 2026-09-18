/**
 * Capability-based permissions.
 *
 * A role sets the defaults; an administrator can then tick or untick any
 * individual capability for one person. The effective set is:
 *
 *     role defaults  +  that user's overrides
 *
 * So you can hand one engineer the right to see everyone's pipeline without
 * promoting them to manager, or take quotation deletion away from another.
 */

export const PERMISSIONS = [
  // --------------------------------------------------------------- customers
  { key: 'customers.view', group: 'customers', ar: 'عرض العملاء', en: 'View customers' },
  { key: 'customers.create', group: 'customers', ar: 'إضافة عميل', en: 'Create customers' },
  { key: 'customers.edit', group: 'customers', ar: 'تعديل العملاء', en: 'Edit customers' },
  { key: 'customers.delete', group: 'customers', ar: 'مسح العملاء', en: 'Delete customers' },
  { key: 'customers.view_all', group: 'customers', ar: 'يشوف عملاء كل المهندسين', en: 'See every engineer’s customers' },
  { key: 'customers.assign', group: 'customers', ar: 'يحوّل العميل لمهندس تاني', en: 'Reassign customers' },

  // ------------------------------------------------------------ opportunities
  { key: 'opportunities.view', group: 'opportunities', ar: 'عرض الفرص', en: 'View opportunities' },
  { key: 'opportunities.create', group: 'opportunities', ar: 'إضافة فرصة', en: 'Create opportunities' },
  { key: 'opportunities.edit', group: 'opportunities', ar: 'تعديل الفرص', en: 'Edit opportunities' },
  { key: 'opportunities.delete', group: 'opportunities', ar: 'مسح الفرص', en: 'Delete opportunities' },

  // --------------------------------------------------------------- quotations
  { key: 'quotations.view', group: 'quotations', ar: 'عرض عروض الأسعار', en: 'View quotations' },
  { key: 'quotations.create', group: 'quotations', ar: 'إنشاء عرض سعر', en: 'Create quotations' },
  { key: 'quotations.edit', group: 'quotations', ar: 'تعديل عروض الأسعار', en: 'Edit quotations' },
  { key: 'quotations.delete', group: 'quotations', ar: 'مسح عروض الأسعار', en: 'Delete quotations' },
  { key: 'quotations.send', group: 'quotations', ar: 'يحدد العرض كمُرسل', en: 'Mark quotations as sent' },
  { key: 'quotations.decide', group: 'quotations', ar: 'اعتماد أو رفض العروض', en: 'Approve or reject quotations' },
  { key: 'quotations.view_cost', group: 'quotations', ar: 'يشوف التكلفة وهامش الربح', en: 'See cost and margin' },
  { key: 'quotations.edit_closed', group: 'quotations', ar: 'يعدّل عرض مقفول', en: 'Edit a closed quotation' },

  // --------------------------------------------------------------- activities
  { key: 'activities.view', group: 'activities', ar: 'عرض المتابعات', en: 'View follow-ups' },
  { key: 'activities.create', group: 'activities', ar: 'إضافة متابعة', en: 'Create follow-ups' },
  { key: 'activities.edit', group: 'activities', ar: 'تعديل المتابعات', en: 'Edit follow-ups' },
  { key: 'activities.delete', group: 'activities', ar: 'مسح المتابعات', en: 'Delete follow-ups' },

  // ---------------------------------------------------------------- analytics
  { key: 'analytics.view', group: 'analytics', ar: 'عرض التحليلات', en: 'View analytics' },
  { key: 'analytics.view_all', group: 'analytics', ar: 'تحليلات الشركة كلها', en: 'Company-wide analytics' },

  // ----------------------------------------------------------------- messages
  { key: 'messages.send', group: 'messages', ar: 'إرسال رسايل للزمايل', en: 'Send messages' },

  // --------------------------------------------------------------------- mail
  { key: 'mail.view', group: 'mail', ar: 'عرض طلبات الإيميل', en: 'View email requests' },
  { key: 'mail.triage', group: 'mail', ar: 'توزيع الطلبات على المهندسين', en: 'Triage and assign email requests' },
  { key: 'mail.view_all', group: 'mail', ar: 'يشوف كل رسايل صندوق الوارد', en: 'Browse the whole mailbox' },
  { key: 'mail.manage', group: 'mail', ar: 'إعداد حسابات البريد والذكاء الاصطناعي', en: 'Configure mailboxes and AI' },

  // ----------------------------------------------------------------- settings
  { key: 'settings.view', group: 'settings', ar: 'عرض الإعدادات', en: 'View settings' },
  { key: 'settings.edit', group: 'settings', ar: 'تعديل إعدادات الشركة والأسعار', en: 'Edit company settings and prices' },
  { key: 'users.manage', group: 'settings', ar: 'إدارة المستخدمين والصلاحيات', en: 'Manage users and permissions' },
];

export const PERMISSION_KEYS = PERMISSIONS.map((p) => p.key);

export const PERMISSION_GROUPS = [
  { key: 'customers', ar: 'العملاء', en: 'Customers' },
  { key: 'opportunities', ar: 'الفرص', en: 'Opportunities' },
  { key: 'quotations', ar: 'عروض الأسعار', en: 'Quotations' },
  { key: 'activities', ar: 'المتابعات', en: 'Follow-ups' },
  { key: 'analytics', ar: 'التحليلات', en: 'Analytics' },
  { key: 'messages', ar: 'الرسايل', en: 'Messages' },
  { key: 'mail', ar: 'طلبات الإيميل', en: 'Email requests' },
  { key: 'settings', ar: 'الإعدادات', en: 'Settings' },
];

/** What each role can do out of the box. */
export const ROLE_DEFAULTS = {
  viewer: [
    'customers.view', 'opportunities.view', 'quotations.view',
    'activities.view', 'analytics.view',
  ],
  engineer: [
    'customers.view', 'customers.create', 'customers.edit',
    'opportunities.view', 'opportunities.create', 'opportunities.edit',
    'quotations.view', 'quotations.create', 'quotations.edit',
    'quotations.send', 'quotations.view_cost',
    'activities.view', 'activities.create', 'activities.edit', 'activities.delete',
    'analytics.view',
    'messages.send',
    'mail.view',
    'settings.view',
  ],
  manager: [
    ...PERMISSION_KEYS.filter((key) => key !== 'users.manage'),
  ],
  admin: [...PERMISSION_KEYS],
};

/**
 * Merges role defaults with a user's stored overrides.
 * Overrides look like { "quotations.delete": false, "customers.view_all": true }.
 */
export function effectivePermissions(user) {
  if (!user) return new Set();
  const base = new Set(ROLE_DEFAULTS[user.role] || ROLE_DEFAULTS.viewer);

  let overrides = user.permissions;
  if (typeof overrides === 'string') {
    try { overrides = JSON.parse(overrides); } catch { overrides = null; }
  }
  if (overrides && typeof overrides === 'object') {
    for (const [key, allowed] of Object.entries(overrides)) {
      if (!PERMISSION_KEYS.includes(key)) continue;
      if (allowed) base.add(key);
      else base.delete(key);
    }
  }

  // An administrator can never lock themselves out of user management;
  // otherwise the last admin could strand the whole installation.
  if (user.role === 'admin') base.add('users.manage');
  return base;
}

export const can = (user, permission) => effectivePermissions(user).has(permission);

/** Strips unknown keys and coerces values, so only valid overrides are stored. */
export function sanitiseOverrides(input) {
  if (!input || typeof input !== 'object') return {};
  const out = {};
  for (const [key, value] of Object.entries(input)) {
    if (!PERMISSION_KEYS.includes(key)) continue;
    out[key] = Boolean(value);
  }
  return out;
}

/** The catalogue the Settings screen renders, with each role's defaults. */
export const permissionCatalogue = () => ({
  permissions: PERMISSIONS,
  groups: PERMISSION_GROUPS,
  role_defaults: ROLE_DEFAULTS,
});
