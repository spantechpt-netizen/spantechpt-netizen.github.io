import { config } from '../config.js';
import { get, update, audit } from '../db.js';
import {
  SESSION_COOKIE, createSession, destroySession, hashPassword, verifyPassword,
  requireAuth,
} from '../auth.js';
import { effectivePermissions } from '../permissions.js';
import { setCookie, clearCookie, badRequest, unauthorized } from '../http.js';
import { str, int, email as emailField, oneOf } from '../validate.js';

// Simple in-memory throttle: 8 failures per email+IP in 15 minutes.
const attempts = new Map();
const WINDOW_MS = 15 * 60_000;
const MAX_ATTEMPTS = 8;

function throttleKey(email, ip) {
  return `${(email || '').toLowerCase()}|${ip || ''}`;
}

function checkThrottle(key) {
  const entry = attempts.get(key);
  if (!entry) return;
  if (Date.now() - entry.first > WINDOW_MS) {
    attempts.delete(key);
    return;
  }
  if (entry.count >= MAX_ATTEMPTS) {
    const minutes = Math.ceil((WINDOW_MS - (Date.now() - entry.first)) / 60_000);
    throw badRequest(
      `Too many failed sign-in attempts. Try again in ${minutes} minute(s).`,
      `عدد محاولات الدخول تجاوز الحد المسموح. حاول مرة أخرى بعد ${minutes} دقيقة.`,
    );
  }
}

function recordFailure(key) {
  const entry = attempts.get(key);
  if (!entry || Date.now() - entry.first > WINDOW_MS) attempts.set(key, { first: Date.now(), count: 1 });
  else entry.count += 1;
}

export function register(router) {
  router.post('/api/auth/login', ({ req, res, body }) => {
    const email = emailField(body.email, 'email', { required: true });
    const password = str(body.password, 'password', { required: true, max: 200 });
    const ip = req.socket.remoteAddress;
    const key = throttleKey(email, ip);
    checkThrottle(key);

    const user = get('SELECT * FROM users WHERE email = ? COLLATE NOCASE', email);
    if (!user || !verifyPassword(password, user.password_hash)) {
      recordFailure(key);
      throw unauthorized('Incorrect email or password', 'البريد الإلكتروني أو كلمة المرور غير صحيحة');
    }
    if (!user.active) {
      throw unauthorized('This account has been disabled', 'تم تعطيل هذا الحساب');
    }
    attempts.delete(key);

    // A Secure cookie is never sent back over plain HTTP, so this combination
    // logs the user in and then loses the session on the very next request —
    // an endless bounce back to the sign-in screen with nothing in the log to
    // explain it. Say what is wrong instead of letting them hunt for it.
    const proto = (req.headers['x-forwarded-proto'] || '').split(',')[0].trim();
    if (config.secureCookies && proto !== 'https') {
      throw badRequest(
        'The server is set to HTTPS-only cookies (SECURE_COOKIES) but this '
        + 'request arrived over plain HTTP, so the session could not be kept. '
        + 'Either reach the site over HTTPS, or set SECURE_COOKIES=false.',
        'السيرفر مضبوط على كوكيز HTTPS فقط (SECURE_COOKIES) لكن الطلب وصل عبر '
        + 'HTTP عادي، فلن تثبت الجلسة. إما تفتح الموقع بـ HTTPS، أو تضبط '
        + 'SECURE_COOKIES=false.',
      );
    }

    const { token } = createSession(user.id, { ip, userAgent: req.headers['user-agent'] });
    setCookie(res, SESSION_COOKIE, token, {
      maxAge: config.sessionHours * 3600,
      secure: config.secureCookies,
    });
    audit(user.id, 'user', user.id, 'login');

    const { password_hash, ...safe } = user;
    safe.permissions = [...effectivePermissions(user)];
    return { user: safe };
  }, { public: true });

  router.post('/api/auth/logout', ({ req, res, user }) => {
    const cookie = (req.headers.cookie || '').match(new RegExp(`${SESSION_COOKIE}=([^;]+)`));
    if (cookie) destroySession(decodeURIComponent(cookie[1]));
    clearCookie(res, SESSION_COOKIE, { secure: config.secureCookies });
    if (user) audit(user.id, 'user', user.id, 'logout');
    return { ok: true };
  }, { public: true });

  router.get('/api/auth/me', ({ user }) => ({ user: user || null }), { public: true });

  router.patch('/api/auth/profile', ({ body, user }) => {
    requireAuth(user);
    update('users', user.id, {
      name: str(body.name, 'name', { max: 120, fallback: undefined }),
      name_ar: str(body.name_ar, 'name_ar', { max: 120, fallback: undefined }),
      title: str(body.title, 'title', { max: 120, fallback: undefined }),
      title_ar: str(body.title_ar, 'title_ar', { max: 120, fallback: undefined }),
      phone: str(body.phone, 'phone', { max: 40, fallback: undefined }),
      lang: oneOf(body.lang, 'lang', ['ar', 'en'], { fallback: undefined }),
      reminder_lead_hours: int(body.reminder_lead_hours, 'reminder_lead_hours', { min: 1, max: 168, fallback: undefined }),
      stale_after_days: int(body.stale_after_days, 'stale_after_days', { min: 1, max: 365, fallback: undefined }),
    });
    const row = get('SELECT * FROM users WHERE id = ?', user.id);
    const { password_hash, ...safe } = row;
    safe.permissions = [...effectivePermissions(row)];
    return { user: safe };
  });

  router.post('/api/auth/password', ({ body, user }) => {
    requireAuth(user);
    const current = str(body.current_password, 'current_password', { required: true, max: 200 });
    const next = str(body.new_password, 'new_password', { required: true, min: 8, max: 200 });
    const row = get('SELECT password_hash FROM users WHERE id = ?', user.id);
    if (!verifyPassword(current, row.password_hash)) {
      throw badRequest('Current password is incorrect', 'كلمة المرور الحالية غير صحيحة');
    }
    update('users', user.id, { password_hash: hashPassword(next) });
    audit(user.id, 'user', user.id, 'password_change');
    return { ok: true };
  });
}
