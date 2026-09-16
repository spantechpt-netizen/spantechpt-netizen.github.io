import { get, insert, update, run, audit } from '../db.js';
import {
  requireAuth, requirePermission, hashPassword, listUsers, destroyUserSessions,
} from '../auth.js';
import { conflict, notFound, badRequest } from '../http.js';
import { sanitiseOverrides, permissionCatalogue } from '../permissions.js';
import { str, email as emailField, oneOf, bool, ROLES, COUNTRIES } from '../validate.js';

export function register(router) {
  router.get('/api/users', ({ user }) => {
    requireAuth(user);
    return { users: listUsers() };
  });

  router.post('/api/users', ({ body, user }) => {
    requirePermission(user, 'users.manage');
    const email = emailField(body.email, 'email', { required: true });
    if (get('SELECT id FROM users WHERE email = ? COLLATE NOCASE', email)) {
      throw conflict('A user with this email already exists', 'يوجد مستخدم بنفس البريد الإلكتروني');
    }
    const password = str(body.password, 'password', { required: true, min: 8, max: 200 });
    const id = insert('users', {
      name: str(body.name, 'name', { required: true, max: 120 }),
      name_ar: str(body.name_ar, 'name_ar', { max: 120 }),
      email,
      password_hash: hashPassword(password),
      role: oneOf(body.role, 'role', ROLES, { fallback: 'engineer' }),
      title: str(body.title, 'title', { max: 120 }),
      title_ar: str(body.title_ar, 'title_ar', { max: 120 }),
      phone: str(body.phone, 'phone', { max: 40 }),
      country: oneOf(body.country, 'country', COUNTRIES, { fallback: 'SA' }),
      lang: oneOf(body.lang, 'lang', ['ar', 'en'], { fallback: 'ar' }),
      active: bool(body.active, true) ? 1 : 0,
      permissions: JSON.stringify(sanitiseOverrides(body.permission_overrides)),
    });
    audit(user.id, 'user', id, 'create', { email });
    return { user: listUsers().find((u) => u.id === id) };
  });

  router.patch('/api/users/:id', ({ params, body, user }) => {
    requirePermission(user, 'users.manage');
    const id = Number(params.id);
    const target = get('SELECT * FROM users WHERE id = ?', id);
    if (!target) throw notFound('User not found', 'المستخدم غير موجود');

    // Never let the last active administrator lock everyone out.
    const demoting = body.role !== undefined && body.role !== 'admin';
    const deactivating = body.active !== undefined && !bool(body.active, true);
    if (target.role === 'admin' && (demoting || deactivating)) {
      const otherAdmins = get(
        'SELECT COUNT(*) AS n FROM users WHERE role = ? AND active = 1 AND id <> ?', 'admin', id,
      ).n;
      if (otherAdmins === 0) {
        throw badRequest(
          'The last active administrator cannot be demoted or disabled',
          'لا يمكن تعطيل أو تخفيض صلاحية آخر مدير نظام نشط',
        );
      }
    }

    if (body.email !== undefined) {
      const email = emailField(body.email, 'email', { required: true });
      const clash = get('SELECT id FROM users WHERE email = ? COLLATE NOCASE AND id <> ?', email, id);
      if (clash) throw conflict('A user with this email already exists', 'يوجد مستخدم بنفس البريد الإلكتروني');
    }

    const active = body.active === undefined ? undefined : (bool(body.active, true) ? 1 : 0);
    update('users', id, {
      name: str(body.name, 'name', { max: 120, fallback: undefined }),
      name_ar: str(body.name_ar, 'name_ar', { max: 120, fallback: undefined }),
      email: body.email === undefined ? undefined : emailField(body.email, 'email'),
      role: oneOf(body.role, 'role', ROLES, { fallback: undefined }),
      title: str(body.title, 'title', { max: 120, fallback: undefined }),
      title_ar: str(body.title_ar, 'title_ar', { max: 120, fallback: undefined }),
      phone: str(body.phone, 'phone', { max: 40, fallback: undefined }),
      country: oneOf(body.country, 'country', COUNTRIES, { fallback: undefined }),
      lang: oneOf(body.lang, 'lang', ['ar', 'en'], { fallback: undefined }),
      active,
      permissions: body.permission_overrides === undefined
        ? undefined
        : JSON.stringify(sanitiseOverrides(body.permission_overrides)),
    });

    if (body.password) {
      const password = str(body.password, 'password', { required: true, min: 8, max: 200 });
      update('users', id, { password_hash: hashPassword(password) });
      destroyUserSessions(id); // force re-login everywhere with the new password
    }
    if (active === 0) destroyUserSessions(id);

    // No need to end sessions for a permission or role change: the capability
    // set is recomputed from this row on every request, so it applies at once
    // without throwing the person out of what they were doing.
    audit(user.id, 'user', id, 'update');
    return { user: listUsers().find((u) => u.id === id) };
  });

  /** Every capability, grouped, with each role's defaults. */
  router.get('/api/permissions', ({ user }) => {
    requireAuth(user);
    return { ...permissionCatalogue(), mine: user.permissions };
  });

  router.delete('/api/users/:id', ({ params, user }) => {
    requirePermission(user, 'users.manage');
    const id = Number(params.id);
    if (id === user.id) throw badRequest('You cannot delete your own account', 'مش هتقدر تمسح حسابك انت');
    const target = get('SELECT role FROM users WHERE id = ?', id);
    if (!target) throw notFound('User not found', 'المستخدم غير موجود');
    // Deactivate rather than delete so historical quotes keep their owner.
    update('users', id, { active: 0 });
    destroyUserSessions(id);
    audit(user.id, 'user', id, 'deactivate');
    return { ok: true };
  });
}
