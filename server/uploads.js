/**
 * Drawings attached to a cost study.
 *
 * The browser sends the file as the raw request body with its type in the
 * Content-Type header, rather than as multipart/form-data. That avoids writing
 * a multipart parser — which is the sort of code that goes wrong quietly — and
 * `fetch(url, { method: 'POST', body: file })` is all the client needs.
 *
 * Files are written under data/uploads/<quotationId>/ with a name this module
 * generates. A client-supplied filename never reaches the filesystem.
 */
import { createWriteStream } from 'node:fs';
import { mkdir, unlink, stat } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { join, resolve, dirname, basename } from 'node:path';
import { ROOT } from './config.js';
import { badRequest } from './http.js';

export const UPLOAD_ROOT = resolve(ROOT, process.env.UPLOAD_DIR || './data/uploads');

/** 20 MB. A drawing exported as an image sits well inside this. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

/**
 * Only formats that can be shown inside the printed study. A PDF cannot be
 * embedded in an HTML document without a renderer, so accepting one here would
 * produce an attachment the owner never sees in the document they are sent.
 */
export const ALLOWED_TYPES = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
};

export const DRAWING_KINDS = ['original', 'post_tension'];

/** Where a stored file lives, refusing anything that climbs out of the root. */
export function drawingPath(quotationId, filename) {
  const safe = basename(String(filename || ''));
  const target = resolve(join(UPLOAD_ROOT, String(Number(quotationId)), safe));
  if (target !== UPLOAD_ROOT && !target.startsWith(UPLOAD_ROOT + '/') && !target.startsWith(UPLOAD_ROOT + '\\')) {
    throw badRequest('Bad file path', 'مسار ملف غير صالح');
  }
  return target;
}

/**
 * Streams the request body to disk, stopping the moment it goes over the
 * limit so a large upload cannot fill the disk while we watch.
 */
export async function saveDrawing(req, quotationId) {
  const contentType = String(req.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
  const extension = ALLOWED_TYPES[contentType];
  if (!extension) {
    throw badRequest(
      `Unsupported file type "${contentType || 'unknown'}". Attach the drawing as PNG, JPG or WebP — `
      + 'a PDF cannot be shown inside the printed study.',
      `نوع الملف "${contentType || 'غير معروف'}" مش مدعوم. ارفع المخطط كصورة PNG أو JPG أو WebP — `
      + 'ملف PDF مش هيظهر جوه الدراسة المطبوعة.',
    );
  }

  const declared = Number(req.headers['content-length'] || 0);
  if (declared > MAX_UPLOAD_BYTES) {
    throw badRequest(
      `That file is ${(declared / 1024 / 1024).toFixed(1)} MB; the limit is ${MAX_UPLOAD_BYTES / 1024 / 1024} MB.`,
      `الملف ${(declared / 1024 / 1024).toFixed(1)} ميجا، والحد الأقصى ${MAX_UPLOAD_BYTES / 1024 / 1024} ميجا.`,
    );
  }

  const filename = `${randomUUID()}.${extension}`;
  const target = drawingPath(quotationId, filename);
  await mkdir(dirname(target), { recursive: true });

  const written = await new Promise((resolvePromise, reject) => {
    const out = createWriteStream(target);
    let bytes = 0;
    let failed = false;

    const fail = (error) => {
      if (failed) return;
      failed = true;
      req.unpipe?.(out);
      out.destroy();
      unlink(target).catch(() => {});
      reject(error);
    };

    req.on('data', (chunk) => {
      bytes += chunk.length;
      if (bytes > MAX_UPLOAD_BYTES && !failed) {
        fail(badRequest(
          `That file is over the ${MAX_UPLOAD_BYTES / 1024 / 1024} MB limit.`,
          `الملف أكبر من الحد الأقصى ${MAX_UPLOAD_BYTES / 1024 / 1024} ميجا.`,
        ));
      }
    });
    req.on('error', fail);
    out.on('error', fail);
    out.on('finish', () => { if (!failed) resolvePromise(bytes); });

    req.pipe(out);
  });

  if (!written) {
    await unlink(target).catch(() => {});
    throw badRequest('The file was empty.', 'الملف فاضي.');
  }

  return { filename, contentType, bytes: written };
}

/** Removes a stored file; a missing one is not an error worth raising. */
export async function deleteDrawingFile(quotationId, filename) {
  try {
    await unlink(drawingPath(quotationId, filename));
  } catch { /* already gone */ }
}

/** True when the file behind a database row is actually on disk. */
export async function drawingExists(quotationId, filename) {
  try {
    return (await stat(drawingPath(quotationId, filename))).isFile();
  } catch {
    return false;
  }
}

