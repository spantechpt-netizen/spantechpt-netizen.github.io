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

/**
 * Works out why a request could not be sent, so the message names something
 * the reader can act on.
 */
async function networkFailure() {
  const where = location.origin;

  // The page itself came from somewhere, so if health answers now, the server
  // is up and it was this one request that failed — a browser extension, a
  // proxy, or a blip.
  let serverUp = false;
  try {
    const probe = await fetch('/api/health', { cache: 'no-store' });
    serverUp = probe.ok;
  } catch { /* server really is gone */ }

  if (serverUp) {
    return { error: {
      message: `The server at ${where} is running, but that request did not get through. `
        + 'Something between the browser and it — an extension, antivirus or a proxy — '
        + 'is blocking it. Try again, or try a different browser.',
      message_ar: `السيرفر على ${where} شغال، بس الطلب ده مش بيعدّي. `
        + 'في حاجة بين المتصفح والسيرفر بتمنعه — إضافة في المتصفح أو مضاد فيروسات '
        + 'أو بروكسي. جرّب تاني، أو جرّب متصفح تاني.',
    } };
  }

  return { error: {
    message: `The server at ${where} has stopped answering. Look at the window that is `
      + 'running it: if it closed, or shows an error, start it again with start.bat '
      + '(or ./start.sh) and keep that window open.',
    message_ar: `السيرفر على ${where} وقف. بصّ على النافذة السودا اللي شغّالاه: `
      + 'لو اتقفلت أو فيها رسالة خطأ، شغّل start.bat تاني وسيبها مفتوحة — '
      + 'قفل النافذة دي بيوقّف النظام.',
  } };
}

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
    // "Check your connection" sends people hunting the network for a problem
    // that is usually the server having stopped. Ask it directly and say which
    // of the two it is, and where to look.
    throw new ApiError(0, await networkFailure());
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
  // The customer's correspondence, filed from the mailbox by address.
  customerMail: (id) => request('GET', `/api/customers/${id}/mail`),
  customerMailMessage: (id, messageId) => request('GET', `/api/customers/${id}/mail/${messageId}`),
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
  study: (id) => request('GET', `/api/quotations/${id}/study`),
  saveStudy: (id, study) => request('PUT', `/api/quotations/${id}/study`, { study }),
  updateDrawing: (id, drawingId, payload) =>
    request('PATCH', `/api/quotations/${id}/study/drawings/${drawingId}`, payload),
  deleteDrawing: (id, drawingId) =>
    request('DELETE', `/api/quotations/${id}/study/drawings/${drawingId}`),
  /** The file is the request body; see server/uploads.js for why not multipart. */
  uploadDrawing: async (id, kind, file) => {
    const url = `/api/quotations/${id}/study/drawings${qs({ kind, name: file.name })}`;
    const res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'content-type': file.type || 'application/octet-stream' },
      body: file,
    });
    const payload = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, payload);
    return payload;
  },
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

  // ------------------------------------------------------------ email intake
  mailAccounts: () => request('GET', '/api/mail/accounts'),
  createMailAccount: (data) => request('POST', '/api/mail/accounts', data),
  updateMailAccount: (id, data) => request('PATCH', `/api/mail/accounts/${id}`, data),
  deleteMailAccount: (id) => request('DELETE', `/api/mail/accounts/${id}`),
  testMailAccount: (id) => request('POST', `/api/mail/accounts/${id}/test`, {}),
  syncMailAccount: (id, data) => request('POST', `/api/mail/accounts/${id}/sync`, data ?? {}),
  syncAllMail: () => request('POST', '/api/mail/sync', {}),

  captureRequest: (payload) => request('POST', '/api/mail/capture', payload),
  mailRequests: (params) => request('GET', `/api/mail/requests${qs(params)}`),
  // The whole mailbox, not only what the filter queued.
  mailMessages: (params) => request('GET', `/api/mail/messages${qs(params)}`),
  mailMessage: (id) => request('GET', `/api/mail/messages/${id}`),
  queueMailMessage: (id) => request('POST', `/api/mail/messages/${id}/queue`, {}),
  mailRequest: (id) => request('GET', `/api/mail/requests/${id}`),
  assignMailRequest: (id, data) => request('POST', `/api/mail/requests/${id}/assign`, data),
  convertMailRequest: (id, data) => request('POST', `/api/mail/requests/${id}/convert`, data ?? {}),
  setMailRequestStatus: (id, status, notes) => request('POST', `/api/mail/requests/${id}/status`, { status, notes }),
  reExtractMailRequest: (id) => request('POST', `/api/mail/requests/${id}/re-extract`, {}),
  mailSummary: () => request('GET', '/api/mail/summary'),

  aiSettings: () => request('GET', '/api/mail/ai'),
  saveAiSettings: (data) => request('PUT', '/api/mail/ai', data),

  // ------------------------------------------------------- users & settings
  users: () => request('GET', '/api/users'),
  permissionCatalogue: () => request('GET', '/api/permissions'),
  createUser: (data) => request('POST', '/api/users', data),
  updateUser: (id, data) => request('PATCH', `/api/users/${id}`, data),
  deleteUser: (id) => request('DELETE', `/api/users/${id}`),
  settings: () => request('GET', '/api/settings'),
  saveSetting: (key, value) => request('PUT', `/api/settings/${key}`, { value }),
  resetSetting: (key) => request('POST', `/api/settings/${key}/reset`, {}),
};
