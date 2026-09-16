import { createServer } from 'node:http';
import { config, isDefaultSecret } from './config.js';
import { db } from './db.js';
import { userFromRequest, purgeExpiredSessions } from './auth.js';
import { seedSettings, seedAdmin } from './seed.js';
import {
  Router, readJsonBody, sendJson, sendError, serveStatic, notFound, HttpError,
} from './http.js';

import * as authRoutes from './routes/auth.js';
import * as userRoutes from './routes/users.js';
import * as customerRoutes from './routes/customers.js';
import * as opportunityRoutes from './routes/opportunities.js';
import * as activityRoutes from './routes/activities.js';
import * as quotationRoutes from './routes/quotations.js';
import * as analyticsRoutes from './routes/analytics.js';
import * as settingsRoutes from './routes/settings.js';
import * as notificationRoutes from './routes/notifications.js';
import * as calendarRoutes from './routes/calendar.js';
import * as mailRoutes from './routes/mail.js';

import { runReminderSweep, purgeOldNotifications } from './notifications.js';
import { userByCalendarToken, buildUserCalendar } from './calendar.js';
import { syncDueAccounts } from './mailbox.js';

const router = new Router();
for (const module of [
  authRoutes, userRoutes, customerRoutes, opportunityRoutes,
  activityRoutes, quotationRoutes, analyticsRoutes, settingsRoutes,
  notificationRoutes, calendarRoutes, mailRoutes,
]) {
  module.register(router);
}

router.get('/api/health', () => ({
  ok: true,
  version: '1.0.0',
  time: new Date().toISOString(),
}), { public: true });

const server = createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = decodeURIComponent(url.pathname);

  try {
    // Calendar feed. The token in the URL *is* the credential, because
    // Outlook and Google fetch this without any session cookie.
    if (pathname.startsWith('/calendar/') && pathname.endsWith('.ics')) {
      const token = pathname.slice('/calendar/'.length, -'.ics'.length);
      const owner = token ? userByCalendarToken(token) : null;
      if (!owner) throw notFound('Calendar not found', 'التقويم مش موجود');

      const lang = url.searchParams.get('lang') === 'en' ? 'en' : (owner.lang || 'ar');
      const proto = (req.headers['x-forwarded-proto'] || 'http').split(',')[0].trim();
      const body = buildUserCalendar(owner.id, lang, `${proto}://${req.headers.host || ''}`);
      res.writeHead(200, {
        'content-type': 'text/calendar; charset=utf-8',
        'content-length': Buffer.byteLength(body),
        'cache-control': 'no-cache',
        'content-disposition': 'inline; filename="spantech-follow-ups.ics"',
      });
      res.end(req.method === 'HEAD' ? undefined : body);
      return;
    }

    if (pathname.startsWith('/api/')) {
      const matched = router.match(req.method, pathname);
      if (!matched) throw notFound('Unknown endpoint', 'المسار غير موجود');
      if (matched.methodMismatch) {
        throw new HttpError(405, 'Method not allowed', 'طريقة الطلب غير مسموحة');
      }

      const user = userFromRequest(req);
      if (!matched.route.options.public && !user) {
        throw new HttpError(401, 'Not signed in', 'لم يتم تسجيل الدخول');
      }

      const body = await readJsonBody(req);
      const query = Object.fromEntries(url.searchParams);
      const result = await matched.route.handler({
        req, res, body, query, user, params: matched.params,
      });
      if (!res.headersSent) sendJson(res, req.method === 'POST' ? 201 : 200, result);
      return;
    }

    // Static assets, then the SPA shell for any unknown client-side route.
    if (serveStatic(req, res, config.publicDir, pathname)) return;
    if (serveStatic(req, res, config.publicDir, '/index.html')) return;
    throw notFound();
  } catch (error) {
    if (!res.headersSent) sendError(res, error);
    else res.end();
  }
});

// Housekeeping: drop expired sessions and stale notifications hourly.
const cleanup = setInterval(() => {
  try {
    purgeExpiredSessions();
    purgeOldNotifications();
  } catch (error) { console.error('[cleanup]', error); }
}, 3600_000);
cleanup.unref();

// Mailbox polling. Each account has its own interval; this pass just asks
// which are due, so a tight timer here costs nothing.
const MAIL_POLL_MINUTES = Number(process.env.MAIL_POLL_MINUTES || 5);
const mailTimer = setInterval(() => {
  syncDueAccounts().catch((error) => console.error('[mail]', error));
}, Math.max(MAIL_POLL_MINUTES, 1) * 60_000);
mailTimer.unref();

// Reminder engine: raises due / overdue / missed-contact / expiry alerts.
// Dedupe keys make repeat passes harmless, so a short interval is cheap.
const SWEEP_MINUTES = Number(process.env.SWEEP_MINUTES || 15);
const sweep = setInterval(() => {
  try { runReminderSweep(); } catch (error) { console.error('[reminders]', error); }
}, Math.max(SWEEP_MINUTES, 1) * 60_000);
sweep.unref();

function shutdown(signal) {
  console.log(`\n${signal} received — shutting down.`);
  server.close(() => {
    try { db.close(); } catch { /* already closed */ }
    process.exit(0);
  });
  // Don't hang forever on a stuck connection.
  setTimeout(() => process.exit(0), 5000).unref();
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

seedSettings();
const admin = seedAdmin();

// Run one sweep at boot so reminders are current even after downtime.
try { runReminderSweep(); } catch (error) { console.error('[reminders]', error); }

server.listen(config.port, config.host, () => {
  console.log('');
  console.log('  Span Tech CRM  |  نظام سبان تك لإدارة العملاء وعروض الأسعار');
  console.log('  ' + '─'.repeat(60));
  console.log(`  URL       http://${config.host === '0.0.0.0' ? 'localhost' : config.host}:${config.port}`);
  console.log(`  Database  ${config.dbPath}`);
  if (admin) {
    console.log('');
    console.log(`  First administrator created:`);
    console.log(`    email     ${admin.email}`);
    console.log(`    password  ${admin.password}`);
    console.log('    Sign in and change this password immediately.');
  }
  if (isDefaultSecret()) {
    console.log('');
    console.log('  WARNING: SESSION_SECRET is still the default value.');
    console.log('  Set it in .env before exposing this server to the network.');
  }
  console.log('');
});
