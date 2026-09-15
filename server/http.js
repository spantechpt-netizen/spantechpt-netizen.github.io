import { createReadStream, statSync } from 'node:fs';
import { extname, join, normalize, sep } from 'node:path';

/** Error type that carries an HTTP status code and a bilingual message. */
export class HttpError extends Error {
  constructor(status, message, messageAr = null, details = null) {
    super(message);
    this.status = status;
    this.messageAr = messageAr || message;
    this.details = details;
  }
}

export const badRequest = (en, ar, details) => new HttpError(400, en, ar, details);
export const unauthorized = (en = 'Not signed in', ar = 'لم يتم تسجيل الدخول') =>
  new HttpError(401, en, ar);
export const forbidden = (en = 'Not allowed', ar = 'غير مصرح لك بهذا الإجراء') =>
  new HttpError(403, en, ar);
export const notFound = (en = 'Not found', ar = 'غير موجود') => new HttpError(404, en, ar);
export const conflict = (en, ar) => new HttpError(409, en, ar);

const MAX_BODY_BYTES = 2 * 1024 * 1024; // 2 MB is far above anything this app posts.

export async function readJsonBody(req) {
  if (req.method === 'GET' || req.method === 'HEAD') return {};
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw badRequest('Request body too large', 'حجم الطلب كبير جداً');
    chunks.push(chunk);
  }
  if (!size) return {};
  const raw = Buffer.concat(chunks).toString('utf8');
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    throw badRequest('Invalid JSON body', 'صيغة البيانات المرسلة غير صحيحة');
  }
}

export function sendJson(res, status, payload) {
  const body = JSON.stringify(payload ?? null);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
  });
  res.end(body);
}

export function sendError(res, error) {
  const status = error instanceof HttpError ? error.status : 500;
  if (status >= 500) console.error('[error]', error);
  sendJson(res, status, {
    error: {
      message: status >= 500 ? 'Internal server error' : error.message,
      message_ar: status >= 500 ? 'خطأ داخلي في الخادم' : error.messageAr || error.message,
      details: error.details || null,
    },
  });
}

export function parseCookies(req) {
  const header = req.headers.cookie;
  if (!header) return {};
  const out = {};
  for (const part of header.split(';')) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    out[part.slice(0, eq).trim()] = decodeURIComponent(part.slice(eq + 1).trim());
  }
  return out;
}

export function setCookie(res, name, value, { maxAge, secure = false, httpOnly = true } = {}) {
  const parts = [`${name}=${encodeURIComponent(value)}`, 'Path=/', 'SameSite=Lax'];
  if (httpOnly) parts.push('HttpOnly');
  if (secure) parts.push('Secure');
  if (maxAge !== undefined) parts.push(`Max-Age=${Math.floor(maxAge)}`);
  const existing = res.getHeader('set-cookie');
  const list = existing ? (Array.isArray(existing) ? existing : [existing]) : [];
  list.push(parts.join('; '));
  res.setHeader('set-cookie', list);
}

export function clearCookie(res, name, { secure = false } = {}) {
  setCookie(res, name, '', { maxAge: 0, secure });
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
  '.webmanifest': 'application/manifest+json',
};

/**
 * Serves a file from `rootDir`, refusing any path that escapes it.
 * Returns true when the response was handled.
 */
export function serveStatic(req, res, rootDir, urlPath) {
  let relative = decodeURIComponent(urlPath.split('?')[0]);
  if (relative.endsWith('/')) relative += 'index.html';
  // normalize() collapses ".." before we test containment.
  const target = normalize(join(rootDir, relative));
  if (target !== rootDir && !target.startsWith(rootDir + sep)) return false;

  let stat;
  try {
    stat = statSync(target);
  } catch {
    return false;
  }
  if (!stat.isFile()) return false;

  const ext = extname(target).toLowerCase();
  const etag = `W/"${stat.size}-${Math.floor(stat.mtimeMs)}"`;
  if (req.headers['if-none-match'] === etag) {
    res.writeHead(304, { etag });
    res.end();
    return true;
  }

  // index.html must never be cached or users get a stale app after an update.
  const immutable = ext !== '.html';
  res.writeHead(200, {
    'content-type': MIME[ext] || 'application/octet-stream',
    'content-length': stat.size,
    'cache-control': immutable ? 'public, max-age=300, must-revalidate' : 'no-cache',
    etag,
    'x-content-type-options': 'nosniff',
  });
  if (req.method === 'HEAD') {
    res.end();
    return true;
  }
  createReadStream(target).pipe(res);
  return true;
}

/**
 * Tiny pattern router. Patterns look like "GET /api/customers/:id".
 * Handlers receive ({ req, res, params, query, body, user }).
 */
export class Router {
  constructor() {
    this.routes = [];
  }

  add(method, pattern, handler, options = {}) {
    const segments = pattern.split('/').filter(Boolean);
    this.routes.push({ method, segments, handler, options });
    return this;
  }

  get(p, h, o) { return this.add('GET', p, h, o); }
  post(p, h, o) { return this.add('POST', p, h, o); }
  put(p, h, o) { return this.add('PUT', p, h, o); }
  patch(p, h, o) { return this.add('PATCH', p, h, o); }
  delete(p, h, o) { return this.add('DELETE', p, h, o); }

  match(method, pathname) {
    const parts = pathname.split('/').filter(Boolean);
    let pathMatched = false;
    for (const route of this.routes) {
      if (route.segments.length !== parts.length) continue;
      const params = {};
      let ok = true;
      for (let i = 0; i < parts.length; i += 1) {
        const seg = route.segments[i];
        if (seg.startsWith(':')) params[seg.slice(1)] = decodeURIComponent(parts[i]);
        else if (seg !== parts[i]) { ok = false; break; }
      }
      if (!ok) continue;
      pathMatched = true;
      if (route.method === method) return { route, params };
    }
    return pathMatched ? { methodMismatch: true } : null;
  }
}
