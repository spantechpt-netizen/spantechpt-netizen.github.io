/**
 * Spreadsheet export without a dependency.
 *
 * The CRM has no npm packages, so a CSV and an Excel workbook are written
 * here by hand. An .xlsx file is a zip of a handful of XML parts; the zip
 * writer below uses zlib for the compression and computes the CRC itself.
 * Strings are written inline (`t="inlineStr"`) so there is no shared string
 * table to build, and the first row of every sheet is bold with a frozen pane.
 *
 * A sheet is `{ name, columns: [{ key, label, type }], rows: [...] }`. A
 * column's `type` is 'number', 'date' or 'text' (the default) and decides
 * how the cell is typed, so Excel sums figures and sorts dates properly.
 */
import { deflateRawSync } from 'node:zlib';

// ---------------------------------------------------------------------- CSV
/**
 * UTF-8 with a byte-order mark, which is what makes Excel open Arabic text
 * correctly on a double-click instead of showing question marks.
 */
export function toCsv(columns, rows) {
  const cell = (value) => {
    if (value === null || value === undefined) return '';
    const text = String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [columns.map((c) => cell(c.label)).join(',')];
  for (const row of rows) lines.push(columns.map((c) => cell(row[c.key])).join(','));
  return `\uFEFF${lines.join('\r\n')}\r\n`;
}

// --------------------------------------------------------------------- XLSX
const xml = (value) => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  // Control characters are not allowed in XML 1.0 at all.
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');

/** A1-style column letters: 0 → A, 25 → Z, 26 → AA. */
function columnName(index) {
  let n = index;
  let name = '';
  do {
    name = String.fromCharCode(65 + (n % 26)) + name;
    n = Math.floor(n / 26) - 1;
  } while (n >= 0);
  return name;
}

/** Days since 1899-12-30, which is how Excel stores a date. */
function excelDate(value) {
  const date = value instanceof Date ? value : new Date(String(value).length === 10 ? `${value}T00:00:00Z` : value);
  if (Number.isNaN(date.getTime())) return null;
  return (date.getTime() - Date.UTC(1899, 11, 30)) / 86400_000;
}

/** Sheet names are capped at 31 characters and may not carry these. */
const sheetName = (name, index) => (String(name || `Sheet${index + 1}`)
  .replace(/[\\/?*[\]:]/g, ' ').trim().slice(0, 31)) || `Sheet${index + 1}`;

function sheetXml(sheet) {
  const { columns, rows } = sheet;
  const cellsOf = (values, rowIndex, header) => values.map((value, i) => {
    const ref = `${columnName(i)}${rowIndex}`;
    if (header) return `<c r="${ref}" s="1" t="inlineStr"><is><t>${xml(value)}</t></is></c>`;
    if (value === null || value === undefined || value === '') return '';
    const type = columns[i].type;
    if (type === 'number' && Number.isFinite(Number(value))) return `<c r="${ref}" s="2"><v>${Number(value)}</v></c>`;
    if (type === 'date') {
      const serial = excelDate(value);
      if (serial !== null) return `<c r="${ref}" s="3"><v>${serial}</v></c>`;
    }
    return `<c r="${ref}" t="inlineStr"><is><t>${xml(value)}</t></is></c>`;
  }).join('');

  const lines = [`<row r="1">${cellsOf(columns.map((c) => c.label), 1, true)}</row>`];
  rows.forEach((row, index) => {
    lines.push(`<row r="${index + 2}">${cellsOf(columns.map((c) => row[c.key]), index + 2, false)}</row>`);
  });

  // Column widths from the longest value, within reason.
  const widths = columns.map((c, i) => {
    const longest = Math.max(String(c.label).length, ...rows.slice(0, 200).map((r) => String(r[c.key] ?? '').length));
    return `<col min="${i + 1}" max="${i + 1}" width="${Math.min(60, Math.max(10, longest + 2))}" customWidth="1"/>`;
  }).join('');

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheetViews><sheetView workbookViewId="0"${sheet.rtl ? ' rightToLeft="1"' : ''}><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${widths}</cols>
<sheetData>${lines.join('')}</sheetData>
</worksheet>`;
}

const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1A56A7"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

/** An .xlsx workbook, as a Buffer, from one or more sheets. */
export function toXlsx(sheets, { rtl = false } = {}) {
  const list = sheets.length ? sheets : [{ name: 'Sheet1', columns: [], rows: [] }];
  const files = [];

  files.push(['[Content_Types].xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
${list.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`).join('\n')}
</Types>`]);

  files.push(['_rels/.rels', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`]);

  files.push(['xl/workbook.xml', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>${list.map((s, i) => `<sheet name="${xml(sheetName(s.name, i))}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')}</sheets>
</workbook>`]);

  files.push(['xl/_rels/workbook.xml.rels', `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
${list.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('\n')}
<Relationship Id="rId${list.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`]);

  files.push(['xl/styles.xml', STYLES]);
  list.forEach((sheet, i) => files.push([`xl/worksheets/sheet${i + 1}.xml`, sheetXml({ ...sheet, rtl })]));

  return zip(files.map(([name, text]) => [name, Buffer.from(text, 'utf8')]));
}

// ---------------------------------------------------------------------- ZIP
const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

export function crc32(buffer) {
  let crc = 0xFFFFFFFF;
  for (const byte of buffer) crc = CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

/** MS-DOS date and time fields, as the zip format wants them. */
function dosDateTime(date = new Date()) {
  const time = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
  const day = ((date.getFullYear() - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { time, day };
}

/** A zip archive of [name, Buffer] entries, deflated. */
export function zip(entries) {
  const { time, day } = dosDateTime();
  const locals = [];
  const centrals = [];
  let offset = 0;

  for (const [name, data] of entries) {
    const nameBytes = Buffer.from(name, 'utf8');
    const deflated = deflateRawSync(data, { level: 6 });
    const crc = crc32(data);

    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);            // version needed
    local.writeUInt16LE(0x0800, 6);        // UTF-8 names
    local.writeUInt16LE(8, 8);             // deflate
    local.writeUInt16LE(time, 10);
    local.writeUInt16LE(day, 12);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(deflated.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    local.writeUInt16LE(0, 28);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);          // made by
    central.writeUInt16LE(20, 6);          // needed
    central.writeUInt16LE(0x0800, 8);
    central.writeUInt16LE(8, 10);
    central.writeUInt16LE(time, 12);
    central.writeUInt16LE(day, 14);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(deflated.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBytes.length, 28);
    central.writeUInt16LE(0, 30);          // extra
    central.writeUInt16LE(0, 32);          // comment
    central.writeUInt16LE(0, 34);          // disk
    central.writeUInt16LE(0, 36);          // internal attrs
    central.writeUInt32LE(0, 38);          // external attrs
    central.writeUInt32LE(offset, 42);

    locals.push(local, nameBytes, deflated);
    centrals.push(central, nameBytes);
    offset += local.length + nameBytes.length + deflated.length;
  }

  const centralSize = centrals.reduce((n, b) => n + b.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(0, 4);
  end.writeUInt16LE(0, 6);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  end.writeUInt16LE(0, 20);

  return Buffer.concat([...locals, ...centrals, end]);
}

// ------------------------------------------------------------------ response
export const FORMATS = ['csv', 'xlsx'];

/**
 * Writes a download. The filename is sent twice: an ASCII fallback and the
 * RFC 5987 form, so an Arabic project name survives as the file's name.
 */
export function sendDownload(res, { filename, fallback = 'export', format, sheets, rtl = false }) {
  // Browsers that ignore the encoded name get a plain one, not underscores.
  const ascii = filename.replace(/[^\x20-\x7E]+/g, '').replace(/["\\]/g, '');
  const safeAscii = /[a-z0-9]/i.test(ascii.replace(/\d{4}-\d{2}-\d{2}/g, '')) ? ascii : fallback;
  const encoded = encodeURIComponent(filename).replace(/['()*]/g, (c) => `%${c.charCodeAt(0).toString(16).toUpperCase()}`);

  let body;
  let contentType;
  if (format === 'csv') {
    const sheet = sheets[0];
    body = Buffer.from(toCsv(sheet.columns, sheet.rows), 'utf8');
    contentType = 'text/csv; charset=utf-8';
  } else {
    body = toXlsx(sheets, { rtl });
    contentType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  }

  res.writeHead(200, {
    'content-type': contentType,
    'content-length': body.length,
    'content-disposition': `attachment; filename="${safeAscii}.${format}"; filename*=UTF-8''${encoded}.${format}`,
    'cache-control': 'no-store',
    'x-content-type-options': 'nosniff',
  });
  res.end(body);
}
