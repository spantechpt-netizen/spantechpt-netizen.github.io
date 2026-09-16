import { get } from '../db.js';
import { requireAuth } from '../auth.js';
import { notFound } from '../http.js';
import {
  calendarToken, rotateCalendarToken, buildSingleEvent,
} from '../calendar.js';
import { oneOf } from '../validate.js';

export function register(router) {
  /** The engineer's private subscription URL, created on first request. */
  router.get('/api/calendar/feed', ({ req, user }) => {
    requireAuth(user);
    const token = calendarToken(user.id);
    const host = req.headers.host || 'localhost';
    const proto = (req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim();
    const url = `${proto}://${host}/calendar/${token}.ics`;
    return {
      token,
      url,
      // webcal:// makes Outlook and Apple Calendar subscribe rather than download.
      webcal_url: url.replace(/^https?:/, 'webcal:'),
    };
  });

  router.post('/api/calendar/rotate', ({ req, user }) => {
    requireAuth(user);
    const token = rotateCalendarToken(user.id);
    const host = req.headers.host || 'localhost';
    const proto = (req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim();
    const url = `${proto}://${host}/calendar/${token}.ics`;
    return { token, url, webcal_url: url.replace(/^https?:/, 'webcal:') };
  });

  /** Downloads one follow-up as an .ics the engineer can open in Outlook. */
  router.get('/api/activities/:id/ics', ({ req, res, params, query, user }) => {
    requireAuth(user);
    const activity = get(
      `SELECT a.*, c.name_en AS customer_name, c.name_ar AS customer_name_ar,
              o.title AS opportunity_title,
              ct.name AS contact_name, ct.mobile AS contact_mobile, ct.phone AS contact_phone
         FROM activities a
         LEFT JOIN customers c ON c.id = a.customer_id
         LEFT JOIN opportunities o ON o.id = a.opportunity_id
         LEFT JOIN contacts ct ON ct.id = a.contact_id
        WHERE a.id = ?`,
      Number(params.id),
    );
    if (!activity) throw notFound('Follow-up not found', 'المتابعة مش موجودة');
    if (!activity.due_at) throw notFound('This follow-up has no date', 'المتابعة دي مالهاش معاد');

    const lang = oneOf(query.lang, 'lang', ['ar', 'en'], { fallback: user.lang || 'ar' });
    const host = `${(req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim()}://${req.headers.host || ''}`;
    const body = buildSingleEvent(activity, lang, host);

    res.writeHead(200, {
      'content-type': 'text/calendar; charset=utf-8',
      'content-disposition': `attachment; filename="follow-up-${activity.id}.ics"`,
      'content-length': Buffer.byteLength(body),
      'cache-control': 'no-store',
    });
    res.end(body);
  });
}
