/**
 * MIME parsing: turns a raw RFC 5322 message into headers plus readable text.
 *
 * Arabic mail is the reason most of this care is needed — subjects arrive as
 * RFC 2047 encoded words, bodies as quoted-printable or base64, and older
 * Outlook installations still send windows-1256 rather than UTF-8.
 */

/** Unfolds continuation lines and returns a header map (lowercased keys). */
export function parseHeaders(headerText) {
  const headers = {};
  const unfolded = headerText.replace(/\r?\n[ \t]+/g, ' ');
  for (const line of unfolded.split(/\r?\n/)) {
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim().toLowerCase();
    const value = line.slice(colon + 1).trim();
    if (headers[key] === undefined) headers[key] = value;
    else if (Array.isArray(headers[key])) headers[key].push(value);
    else headers[key] = [headers[key], value];
  }
  return headers;
}

/** Decodes bytes with a named charset, falling back to UTF-8. */
export function decodeCharset(bytes, charset = 'utf-8') {
  const normalised = String(charset || 'utf-8').toLowerCase().replace(/['"]/g, '');
  const aliases = {
    'cp1256': 'windows-1256',
    'win-1256': 'windows-1256',
    'arabic': 'iso-8859-6',
    'ascii': 'utf-8',
    'us-ascii': 'utf-8',
    'utf8': 'utf-8',
    'unknown-8bit': 'utf-8',
  };
  const label = aliases[normalised] || normalised;
  try {
    return new TextDecoder(label, { fatal: false }).decode(bytes);
  } catch {
    return new TextDecoder('utf-8', { fatal: false }).decode(bytes);
  }
}

/**
 * Decodes RFC 2047 encoded words, e.g.
 *   =?UTF-8?B?2LnYsdi2INiz2LnYsQ==?=  →  عرض سعر
 * Adjacent encoded words are joined without the separating space, per the RFC.
 */
export function decodeWords(input) {
  if (!input) return '';
  let text = String(input);
  // Whitespace between two encoded words is not part of the text.
  text = text.replace(/\?=[ \t]+=\?/g, '?==?');
  return text.replace(/=\?([^?]+)\?([BbQq])\?([^?]*)\?=/g, (whole, charset, encoding, data) => {
    try {
      if (encoding.toUpperCase() === 'B') {
        return decodeCharset(Buffer.from(data, 'base64'), charset);
      }
      const bytes = decodeQuotedPrintable(data.replace(/_/g, ' '), true);
      return decodeCharset(bytes, charset);
    } catch {
      return whole;
    }
  });
}

/** Quoted-printable → Buffer. `inWord` skips soft line breaks (RFC 2047). */
export function decodeQuotedPrintable(text, inWord = false) {
  const source = inWord ? text : text.replace(/=\r?\n/g, '');
  const out = [];
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === '=' && i + 2 < source.length && /^[0-9A-Fa-f]{2}$/.test(source.slice(i + 1, i + 3))) {
      out.push(parseInt(source.slice(i + 1, i + 3), 16));
      i += 2;
    } else {
      out.push(char.charCodeAt(0) & 0xff);
    }
  }
  return Buffer.from(out);
}

/** Splits `text/plain; charset="utf-8"` into its type and parameters. */
export function parseContentType(value = '') {
  const [typePart, ...paramParts] = String(value).split(';');
  const params = {};
  for (const part of paramParts) {
    const eq = part.indexOf('=');
    if (eq === -1) continue;
    params[part.slice(0, eq).trim().toLowerCase()] = part.slice(eq + 1).trim().replace(/^"|"$/g, '');
  }
  return { type: (typePart || 'text/plain').trim().toLowerCase(), params };
}

/**
 * Parses a whole message (or a single MIME part) into
 * { headers, text, html, attachments }.
 *
 * `raw` is a binary-latin1 string, which is how the IMAP client hands over
 * literals — bytes survive intact and are decoded per-part below.
 */
export function parseMessage(raw) {
  const text = String(raw).replace(/\r\n/g, '\n');
  const split = text.indexOf('\n\n');
  const headerText = split === -1 ? text : text.slice(0, split);
  const bodyText = split === -1 ? '' : text.slice(split + 2);

  const headers = parseHeaders(headerText);
  const result = { headers, text: '', html: '', attachments: [] };
  walkPart(headers, bodyText, result);

  if (!result.text && result.html) result.text = htmlToText(result.html);
  return result;
}

function walkPart(headers, body, result, depth = 0) {
  if (depth > 12) return; // guard against a malformed nesting bomb

  const { type, params } = parseContentType(headers['content-type'] || 'text/plain');
  const encoding = String(headers['content-transfer-encoding'] || '7bit').trim().toLowerCase();
  const disposition = String(headers['content-disposition'] || '').toLowerCase();

  if (type.startsWith('multipart/') && params.boundary) {
    const sections = splitMultipart(body, params.boundary);
    // For alternative parts the last readable one wins, which is the richest.
    for (const section of sections) {
      const cut = section.indexOf('\n\n');
      const partHeaders = parseHeaders(cut === -1 ? section : section.slice(0, cut));
      const partBody = cut === -1 ? '' : section.slice(cut + 2);
      walkPart(partHeaders, partBody, result, depth + 1);
    }
    return;
  }

  const bytes = decodeBody(body, encoding);

  if (disposition.includes('attachment') || (params.name && !type.startsWith('text/'))) {
    result.attachments.push({
      filename: decodeWords(params.name || filenameFromDisposition(headers['content-disposition']) || 'attachment'),
      type,
      size: bytes.length,
    });
    return;
  }

  if (type === 'text/plain') {
    const decoded = decodeCharset(bytes, params.charset);
    result.text = result.text ? `${result.text}\n${decoded}` : decoded;
  } else if (type === 'text/html') {
    const decoded = decodeCharset(bytes, params.charset);
    result.html = result.html ? `${result.html}\n${decoded}` : decoded;
  } else if (!type.startsWith('multipart/')) {
    result.attachments.push({
      filename: decodeWords(params.name || 'part'),
      type,
      size: bytes.length,
    });
  }
}

function decodeBody(body, encoding) {
  if (encoding === 'base64') {
    return Buffer.from(body.replace(/[^A-Za-z0-9+/=]/g, ''), 'base64');
  }
  if (encoding === 'quoted-printable') {
    return decodeQuotedPrintable(body);
  }
  return Buffer.from(body, 'binary');
}

function splitMultipart(body, boundary) {
  const marker = `--${boundary}`;
  const parts = [];
  const lines = body.split('\n');
  let current = null;

  for (const line of lines) {
    const trimmed = line.trimEnd();
    if (trimmed === marker) {
      if (current !== null) parts.push(current.join('\n'));
      current = [];
      continue;
    }
    if (trimmed === `${marker}--`) {
      if (current !== null) parts.push(current.join('\n'));
      current = null;
      break;
    }
    if (current !== null) current.push(line);
  }
  if (current !== null && current.length) parts.push(current.join('\n'));
  return parts;
}

function filenameFromDisposition(value = '') {
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(String(value));
  return match ? decodeURIComponent(match[1]) : null;
}

/** Crude but adequate HTML → text, for mail that has no plain-text part. */
export function htmlToText(html) {
  return String(html)
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ')
    .replace(/<\/(p|div|tr|li|h[1-6])>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<td[^>]*>/gi, '\t')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/** Parses `Name <a@b.com>, other@c.com` into [{ name, email }]. */
export function parseAddresses(value) {
  if (!value) return [];
  const decoded = decodeWords(value);
  const out = [];
  // Split on commas that are not inside quotes or angle brackets.
  for (const chunk of decoded.split(/,(?![^<]*>)/)) {
    const part = chunk.trim();
    if (!part) continue;
    const angled = /^(.*?)<([^>]+)>$/.exec(part);
    if (angled) {
      out.push({
        name: angled[1].trim().replace(/^"|"$/g, '') || null,
        email: angled[2].trim().toLowerCase(),
      });
    } else if (part.includes('@')) {
      out.push({ name: null, email: part.replace(/[<>]/g, '').trim().toLowerCase() });
    }
  }
  return out.filter((a) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(a.email));
}

/**
 * Removes quoted history and signatures so extraction sees only what this
 * person actually wrote.
 */
export function stripQuotedReply(text) {
  if (!text) return '';
  const lines = String(text).split('\n');
  const kept = [];

  const markers = [
    /^-{2,}\s*Original Message\s*-{2,}/i,
    /^_{5,}$/,
    /^On .+ wrote:$/i,
    /^From:\s/i,
    /^في .+ كتب:/,
    /^-{2,}\s*رسالة أصلية\s*-{2,}/,
    /^من:\s/,
    /^Sent from my /i,
    /^تم الإرسال من /,
  ];

  for (const line of lines) {
    const trimmed = line.trim();
    if (markers.some((re) => re.test(trimmed))) break;
    if (trimmed === '--') break;           // signature delimiter
    if (/^>/.test(trimmed)) continue;      // quoted line
    kept.push(line);
  }

  return kept.join('\n').replace(/\n{3,}/g, '\n\n').trim() || String(text).trim();
}
