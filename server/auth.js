import { randomBytes, scryptSync, timingSafeEqual, createHmac } from 'node:crypto';
import { config } from './config.js';
import { all, get, run, insert } from './db.js';
import { forbidden, unauthorized, parseCookies } from './http.js';
import { effectivePermissions, can as hasPermission } from './permissions.js';

const SCRYPT_KEYLEN = 64;
export const SESSION_COOKIE = 'spantech_session';

export function hashPassword(plain) {
  const salt = randomBytes(16).toString('hex');
  const derived = scryptSync(plain, salt, SCRYPT_KEYLEN).toString('hex');
  return `scrypt$${salt}$${derived}`;
}

export function verifyPassword(plain, stored) {
  if (!stored || !stored.startsWith('scrypt$')) return false;
  const [, salt, expected] = stored.split('$');
  if (!salt || !expected) return false;
  const derived = scryptSync(plain, salt, SCRYPT_KEYLEN);
  const expectedBuffer = Buffer.from(expected, 'hex');
  if (expectedBuffer.length !== derived.length) return false;
  return timingSafeEqual(derived, expectedBuffer);
}

/**
 * Session tokens are `id.signature`. The signature binds the token to our
 * secret, so a stolen database row alone cannot be replayed against a
 * different deployment, and forged ids are rejected before touching the DB.
 */
function sign(value) {
  return createHmac('sha256', config.sessionSecret).update(value).digest('base64url');
}

export function createSession(userId, { ip, userAgent } = {}) {
  const id = randomBytes(32).toString('base64url');
  const token = `${id}.${sign(id)}`;
  const expires = new Date(Date.now() + config.sessionHours * 3600_000).toISOString();
  insert('sessions', {
    token: id,
    user_id: userId,
    expires_at: expires,
    ip: ip || null,
    user_agent: (userAgent || '').slice(0, 300) || null,
  });
  run("UPDATE users SET last_login_at = datetime('now') WHERE id = ?", userId);
  return { token, expiresAt: expires };
}

export function destroySession(token) {
  const id = splitToken(token);
  if (id) run('DELETE FROM sessions WHERE token = ?', id);
}

export function destroyUserSessions(userId) {
  run('DELETE FROM sessions WHERE user_id = ?', userId);
}

function splitToken(token) {
  if (!token) return null;
  const dot = token.lastIndexOf('.');
  if (dot < 1) return null;
  const id = token.slice(0, dot);
  const signature = token.slice(dot + 1);
  const expected = sign(id);
  if (signature.length !== expected.length) return null;
  if (!timingSafeEqual(Buffer.from(signature), Buffer.from(expected))) return null;
  return id;
}

export function userFromRequest(req) {
  const token = parseCookies(req)[SESSION_COOKIE];
  const id = splitToken(token);
  if (!id) return null;
  const row = get(
    `SELECT u.id, u.name, u.name_ar, u.email, u.role, u.title, u.title_ar, u.phone,
            u.country, u.lang, u.active, u.reminder_lead_hours, u.stale_after_days,
            u.permissions, u.dashboard_json, s.expires_at
       FROM sessions s JOIN users u ON u.id = s.user_id
      WHERE s.token = ?`,
    id,
  );
  if (!row) return null;
  if (new Date(row.expires_at).getTime() < Date.now()) {
    run('DELETE FROM sessions WHERE token = ?', id);
    return null;
  }
  if (!row.active) return null;
  const { expires_at, active, ...user } = row;
  // Resolve the capability set once per request so handlers can just ask.
  user.permissions = [...effectivePermissions(user)];
  return user;
}

export function purgeExpiredSessions() {
  return run("DELETE FROM sessions WHERE expires_at < datetime('now')").changes;
}

// ------------------------------------------------------------- permissions
/** True when the signed-in user holds this capability. */
export const can = (user, permission) =>
  Array.isArray(user?.permissions)
    ? user.permissions.includes(permission)
    : hasPermission(user, permission);

export function requirePermission(user, permission) {
  requireAuth(user);
  if (!can(user, permission)) {
    throw forbidden(
      `You do not have permission to do this (${permission})`,
      'مالكش صلاحية للإجراء ده',
    );
  }
  return user;
}

const RANK = { viewer: 0, engineer: 1, manager: 2, admin: 3 };

export const hasRole = (user, minimum) => user && (RANK[user.role] ?? -1) >= (RANK[minimum] ?? 99);

export function requireAuth(user) {
  if (!user) throw unauthorized();
  return user;
}

export function requireRole(user, minimum) {
  requireAuth(user);
  if (!hasRole(user, minimum)) throw forbidden();
  return user;
}

/**
 * Whether this user sees every engineer's records or only their own.
 * Driven by the capability, so one engineer can be granted company-wide
 * visibility without being promoted.
 */
export const canSeeAll = (user) => can(user, 'customers.view_all');

/** True when `user` may edit a record owned by `ownerId`. */
export function canEditRecord(user, ownerId) {
  if (!user) return false;
  if (canSeeAll(user)) return true;
  return ownerId === null || ownerId === undefined || Number(ownerId) === Number(user.id);
}

export function assertCanEdit(user, ownerId) {
  if (!canEditRecord(user, ownerId)) {
    throw forbidden('This record belongs to another engineer', 'هذا السجل يخص مهندساً آخر');
  }
}

export function listUsers() {
  return all(
    `SELECT id, name, name_ar, email, role, title, title_ar, phone, country, lang,
            active, last_login_at, created_at, permissions
       FROM users ORDER BY active DESC, name`,
  ).map((user) => ({
    ...user,
    // Send the resolved set so the UI can render exactly what this person can do.
    effective_permissions: [...effectivePermissions(user)],
    permission_overrides: safeJson(user.permissions),
    permissions: undefined,
  }));
}

function safeJson(value) {
  if (!value) return {};
  try { return JSON.parse(value); } catch { return {}; }
}
