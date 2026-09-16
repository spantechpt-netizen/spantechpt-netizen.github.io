/**
 * Calendar integration.
 *
 * Every engineer gets a private, unguessable feed URL:
 *   http://<server>/calendar/<token>.ics
 *
 * Pasting that into Outlook, Google Calendar or Apple Calendar as a
 * "subscribed calendar" makes their follow-ups appear there and stay in step —
 * no OAuth, no third-party account, and it keeps working on an intranet server
 * as long as the calendar client can reach the URL.
 */
import { randomBytes } from 'node:crypto';
import { all, get, run } from './db.js';

/** Returns the user's feed token, generating one on first use. */
export function calendarToken(userId) {
  const row = get('SELECT calendar_token FROM users WHERE id = ?', userId);
  if (!row) return null;
  if (row.calendar_token) return row.calendar_token;
  const token = randomBytes(24).toString('base64url');
  run('UPDATE users SET calendar_token = ? WHERE id = ?', token, userId);
  return token;
}

/** Issues a fresh token, which immediately invalidates the previous URL. */
export function rotateCalendarToken(userId) {
  const token = randomBytes(24).toString('base64url');
  run('UPDATE users SET calendar_token = ? WHERE id = ?', token, userId);
  return token;
}

export const userByCalendarToken = (token) =>
  get('SELECT id, name, name_ar, lang FROM users WHERE calendar_token = ? AND active = 1', token);

// ------------------------------------------------------------- ICS building
const pad = (n) => String(n).padStart(2, '0');

/** Formats a date as an ICS UTC timestamp: 20260916T090000Z */
function icsStamp(value) {
  const d = value instanceof Date ? value : new Date(value);
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}`
    + `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
}

/** Escapes the characters that are special inside an ICS value. */
const icsEscape = (text) => String(text ?? '')
  .replace(/\\/g, '\\\\')
  .replace(/;/g, '\\;')
  .replace(/,/g, '\\,')
  .replace(/\r?\n/g, '\\n');

/**
 * ICS lines must not exceed 75 octets; longer ones continue on the next line
 * prefixed by a single space. Folding counts bytes, not characters, so Arabic
 * text stays valid.
 */
function foldLine(line) {
  const bytes = Buffer.from(line, 'utf8');
  if (bytes.length <= 73) return line;

  const parts = [];
  let start = 0;
  let limit = 73;
  while (start < bytes.length) {
    let end = Math.min(start + limit, bytes.length);
    // Never split a multi-byte character: back off to a boundary.
    while (end > start && end < bytes.length && (bytes[end] & 0xc0) === 0x80) end -= 1;
    parts.push(bytes.subarray(start, end).toString('utf8'));
    start = end;
    limit = 72; // continuation lines lose one octet to the leading space
  }
  return parts.join('\r\n ');
}

const ACTIVITY_LABEL = {
  call: ['مكالمة', 'Call'],
  meeting: ['اجتماع', 'Meeting'],
  email: ['إيميل', 'Email'],
  whatsapp: ['واتساب', 'WhatsApp'],
  site_visit: ['زيارة موقع', 'Site visit'],
  task: ['مهمة', 'Task'],
  note: ['ملاحظة', 'Note'],
};

/** Default event length per activity type, in minutes. */
const DURATION = { call: 30, whatsapp: 15, email: 15, note: 15, task: 30, meeting: 60, site_visit: 120 };

function buildEvent(activity, lang, host) {
  const isAr = lang === 'ar';
  const [labelAr, labelEn] = ACTIVITY_LABEL[activity.type] || ['متابعة', 'Follow-up'];
  const label = isAr ? labelAr : labelEn;

  const start = new Date(activity.due_at);
  const end = new Date(start.getTime() + (DURATION[activity.type] || 30) * 60_000);

  const customer = isAr
    ? (activity.customer_name_ar || activity.customer_name)
    : (activity.customer_name || activity.customer_name_ar);

  const summary = `${label}: ${activity.subject}${customer ? ` — ${customer}` : ''}`;

  const descriptionParts = [];
  if (activity.notes) descriptionParts.push(activity.notes);
  if (activity.opportunity_title) {
    descriptionParts.push(`${isAr ? 'الفرصة' : 'Opportunity'}: ${activity.opportunity_title}`);
  }
  if (activity.contact_name) {
    const phone = activity.contact_mobile || activity.contact_phone;
    descriptionParts.push(`${isAr ? 'جهة الاتصال' : 'Contact'}: ${activity.contact_name}${phone ? ` — ${phone}` : ''}`);
  }
  if (host) descriptionParts.push(`${isAr ? 'افتح في النظام' : 'Open in the CRM'}: ${host}/#/activities`);

  const lines = [
    'BEGIN:VEVENT',
    `UID:activity-${activity.id}@spantech-crm`,
    `DTSTAMP:${icsStamp(new Date())}`,
    `DTSTART:${icsStamp(start)}`,
    `DTEND:${icsStamp(end)}`,
    `SUMMARY:${icsEscape(summary)}`,
    descriptionParts.length ? `DESCRIPTION:${icsEscape(descriptionParts.join('\n'))}` : null,
    activity.customer_name ? `LOCATION:${icsEscape(customer || '')}` : null,
    `STATUS:${activity.done ? 'COMPLETED' : 'CONFIRMED'}`,
    `CATEGORIES:${icsEscape(label)}`,
    // A 30-minute alarm mirrors the in-app reminder.
    'BEGIN:VALARM',
    'TRIGGER:-PT30M',
    'ACTION:DISPLAY',
    `DESCRIPTION:${icsEscape(summary)}`,
    'END:VALARM',
    'END:VEVENT',
  ].filter(Boolean);

  return lines.map(foldLine).join('\r\n');
}

/**
 * Builds the full calendar for a user: open follow-ups plus the last 90 days
 * of completed ones, so history stays visible without the feed growing forever.
 */
export function buildUserCalendar(userId, lang = 'ar', host = '') {
  const activities = all(
    `SELECT a.*, c.name_en AS customer_name, c.name_ar AS customer_name_ar,
            o.title AS opportunity_title,
            ct.name AS contact_name, ct.mobile AS contact_mobile, ct.phone AS contact_phone
       FROM activities a
       LEFT JOIN customers c ON c.id = a.customer_id
       LEFT JOIN opportunities o ON o.id = a.opportunity_id
       LEFT JOIN contacts ct ON ct.id = a.contact_id
      WHERE a.owner_id = ?
        AND a.due_at IS NOT NULL
        AND (a.done = 0 OR datetime(a.due_at) >= datetime('now', '-90 days'))
      ORDER BY a.due_at`,
    userId,
  );

  const header = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Span Tech CRM//Follow-ups//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${icsEscape(lang === 'ar' ? 'متابعات سبان تك' : 'Span Tech follow-ups')}`,
    'X-WR-TIMEZONE:UTC',
    // Tells Outlook/Google how often to re-poll the feed.
    'REFRESH-INTERVAL;VALUE=DURATION:PT1H',
    'X-PUBLISHED-TTL:PT1H',
  ].map(foldLine);

  const events = activities
    .filter((a) => !Number.isNaN(new Date(a.due_at).getTime()))
    .map((a) => buildEvent(a, lang, host));

  return [...header, ...events, 'END:VCALENDAR'].join('\r\n') + '\r\n';
}

/** A single-event .ics file, for "add this one to my calendar". */
export function buildSingleEvent(activity, lang = 'ar', host = '') {
  const header = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Span Tech CRM//Follow-ups//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ].map(foldLine);
  return [...header, buildEvent(activity, lang, host), 'END:VCALENDAR'].join('\r\n') + '\r\n';
}
