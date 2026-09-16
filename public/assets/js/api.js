import { getLang } from './i18n.js';

/** Thrown for any non-2xx API response; carries both language messages. */
export class ApiError extends Error {
  constructor(status, payload) {
    const info = payload?.error || {};
    super(info.message || `Request failed (${status})`);
    this.status = status;
    this.messageEn = info.message || `Request failed (${status})`;
    this.messageAr = info.message_ar || this.messageEn;
    this.field = info.details?.field || null;
  }

  /** The message in whichever language the user is reading. */
  get localised() {
    return getLang() === 'ar' ? this.messageAr : this.messageEn;
  }
}

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      credentials: 'same-origin',
      headers: body === undefined ? {} : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, {
      error: {
        message: 'Cannot reach the server. Check your connection.',
        message_ar: 'تعذر الاتصال بالخادم. تحقق من الاتصال بالشبكة.',
      },
    });
  }

  const text = await res.text();
  let payload = null;
  try { payload = text ? JSON.parse(text) : null; } catch { /* non-JSON error page */ }

  if (!res.ok) {
    // 401 on anything but the session probe means the session lapsed.
    if (res.status === 401 && !path.startsWith('/api/auth/')) onUnauthorized();
    throw new ApiError(res.status, payload);
  }
  return payload;
}

const qs = (params = {}) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  }
  const string = search.toString();
  return string ? `?${string}` : '';
};

export const api = {
  get: (path, params) => request('GET', `${path}${qs(params)}`),
  post: (path, body) => request('POST', path, body ?? {}),
  patch: (path, body) => request('PATCH', path, body),
  put: (path, body) => request('PUT', path, body),
  del: (path) => request('DELETE', path),

  // ------------------------------------------------------------------ auth
  login: (email, password) => request('POST', '/api/auth/login', { email, password }),
  logout: () => request('POST', '/api/auth/logout', {}),
  me: () => request('GET', '/api/auth/me'),
  updateProfile: (data) => request('PATCH', '/api/auth/profile', data),
  changePassword: (current_password, new_password) =>
    request('POST', '/api/auth/password', { current_password, new_password }),

  // ------------------------------------------------------------- customers
  customers: (params) => request('GET', `/api/customers${qs(params)}`),
  customer: (id) => request('GET', `/api/customers/${id}`),
  createCustomer: (data) => request('POST', '/api/customers', data),
  updateCustomer: (id, data) => request('PATCH', `/api/customers/${id}`, data),
  deleteCustomer: (id) => request('DELETE', `/api/customers/${id}`),
  createContact: (customerId, data) => request('POST', `/api/customers/${customerId}/contacts`, data),
  updateContact: (id, data) => request('PATCH', `/api/contacts/${id}`, data),
  deleteContact: (id) => request('DELETE', `/api/contacts/${id}`),

  // ---------------------------------------------------------- opportunities
  opportunities: (params) => request('GET', `/api/opportunities${qs(params)}`),
  opportunity: (id) => request('GET', `/api/opportunities/${id}`),
  createOpportunity: (data) => request('POST', '/api/opportunities', data),
  updateOpportunity: (id, data) => request('PATCH', `/api/opportunities/${id}`, data),
  deleteOpportunity: (id) => request('DELETE', `/api/opportunities/${id}`),

  // ------------------------------------------------------------ activities
  activities: (params) => request('GET', `/api/activities${qs(params)}`),
  activitySummary: () => request('GET', '/api/activities/summary'),
  createActivity: (data) => request('POST', '/api/activities', data),
  updateActivity: (id, data) => request('PATCH', `/api/activities/${id}`, data),
  deleteActivity: (id) => request('DELETE', `/api/activities/${id}`),

  // ------------------------------------------------------------ quotations
  quotations: (params) => request('GET', `/api/quotations${qs(params)}`),
  quotation: (id) => request('GET', `/api/quotations/${id}`),
  quotationDocument: (id) => request('GET', `/api/quotations/${id}/document`),
  createQuotation: (data) => request('POST', '/api/quotations', data),
  updateQuotation: (id, data) => request('PATCH', `/api/quotations/${id}`, data),
  setQuotationStatus: (id, status, reason) => request('POST', `/api/quotations/${id}/status`, { status, reason }),
  reviseQuotation: (id) => request('POST', `/api/quotations/${id}/revise`, {}),
  duplicateQuotation: (id, data) => request('POST', `/api/quotations/${id}/duplicate`, data ?? {}),
  deleteQuotation: (id) => request('DELETE', `/api/quotations/${id}`),

  // -------------------------------------------------------------- analytics
  overview: (params) => request('GET', `/api/analytics/overview${qs(params)}`),
  monthly: (params) => request('GET', `/api/analytics/monthly${qs(params)}`),
  breakdown: (params) => request('GET', `/api/analytics/breakdown${qs(params)}`),
  funnel: (params) => request('GET', `/api/analytics/funnel${qs(params)}`),

  // --------------------------------------------------- notifications & mail
  notifications: (params) => request('GET', `/api/notifications${qs(params)}`),
  notificationCount: () => request('GET', '/api/notifications/count'),
  markNotificationRead: (id) => request('POST', `/api/notifications/${id}/read`, {}),
  markAllNotificationsRead: () => request('POST', '/api/notifications/read-all', {}),
  deleteNotification: (id) => request('DELETE', `/api/notifications/${id}`),
  sweepReminders: () => request('POST', '/api/notifications/sweep', {}),
  inboxSummary: () => request('GET', '/api/inbox/summary'),

  messages: (box) => request('GET', `/api/messages${qs({ box })}`),
  messageThread: (id) => request('GET', `/api/messages/${id}`),
  sendMessage: (data) => request('POST', '/api/messages', data),
  deleteMessage: (id) => request('DELETE', `/api/messages/${id}`),

  // ------------------------------------------------------------------ calendar
  calendarFeed: () => request('GET', '/api/calendar/feed'),
  rotateCalendarFeed: () => request('POST', '/api/calendar/rotate', {}),

  // ------------------------------------------------------- users & settings
  users: () => request('GET', '/api/users'),
  createUser: (data) => request('POST', '/api/users', data),
  updateUser: (id, data) => request('PATCH', `/api/users/${id}`, data),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),
  settings: () => request('GET', '/api/settings'),
  saveSetting: (key, value) => request('PUT', `/api/settings/${key}`, { value }),
  resetSetting: (key) => request('POST', `/api/settings/${key}/reset`, {}),
};
