/**
 * The spreadsheet writers.
 *
 * An .xlsx is a zip of XML parts; if the zip is off by a byte Excel refuses
 * the whole file, so the archive is checked against the format's own
 * numbers and the XML against a parser.
 *
 *   npm test
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { inflateRawSync } from 'node:zlib';
import { toCsv, toXlsx, zip, crc32 } from '../server/export.js';

const columns = [
  { key: 'number', label: 'رقم العرض' },
  { key: 'total', label: 'Total', type: 'number' },
  { key: 'date', label: 'Date', type: 'date' },
];
const rows = [
  { number: 'SPAN TECH P.T - 26 - 001', total: 38318, date: '2026-09-11' },
  { number: 'a "quoted", name', total: 0, date: null },
];

test('CSV opens in Excel with Arabic intact and quotes escaped', () => {
  const csv = toCsv(columns, rows);
  assert.ok(csv.startsWith('\uFEFF'), 'a byte-order mark tells Excel this is UTF-8');
  // Not trim(): it would strip the byte-order mark along with the whitespace.
  const lines = csv.slice(1).split('\r\n');
  assert.equal(lines[0], 'رقم العرض,Total,Date');
  assert.equal(lines[1], 'SPAN TECH P.T - 26 - 001,38318,2026-09-11');
  assert.equal(lines[2], '"a ""quoted"", name",0,', 'a comma or quote wraps the cell; null is empty');
});

test('the CRC matches the reference value', () => {
  assert.equal(crc32(Buffer.from('123456789')).toString(16), 'cbf43926');
  assert.equal(crc32(Buffer.alloc(0)), 0);
});

/** Reads the archive back with nothing but the zip specification. */
function readZip(buffer) {
  const entries = {};
  let offset = 0;
  while (buffer.readUInt32LE(offset) === 0x04034b50) {
    const compressed = buffer.readUInt32LE(offset + 18);
    const size = buffer.readUInt32LE(offset + 22);
    const nameLength = buffer.readUInt16LE(offset + 26);
    const extraLength = buffer.readUInt16LE(offset + 28);
    const name = buffer.slice(offset + 30, offset + 30 + nameLength).toString('utf8');
    const start = offset + 30 + nameLength + extraLength;
    const data = inflateRawSync(buffer.slice(start, start + compressed));
    assert.equal(data.length, size, `${name}: the stored size matches the data`);
    assert.equal(crc32(data), buffer.readUInt32LE(offset + 14), `${name}: the CRC matches`);
    entries[name] = data.toString('utf8');
    offset = start + compressed;
  }
  assert.equal(buffer.readUInt32LE(offset), 0x02014b50, 'the central directory follows the last entry');
  return entries;
}

test('the workbook is a valid zip of the parts Excel expects', () => {
  const buffer = toXlsx([
    { name: 'Quotations / عروض', columns, rows },
    { name: 'Empty', columns, rows: [] },
  ], { rtl: true });

  assert.equal(buffer.slice(0, 2).toString(), 'PK');
  const parts = readZip(buffer);
  assert.deepEqual(Object.keys(parts).sort(), [
    '[Content_Types].xml', '_rels/.rels', 'xl/_rels/workbook.xml.rels', 'xl/styles.xml',
    'xl/workbook.xml', 'xl/worksheets/sheet1.xml', 'xl/worksheets/sheet2.xml',
  ]);

  const sheet = parts['xl/worksheets/sheet1.xml'];
  assert.match(parts['xl/workbook.xml'], /name="Quotations {3}عروض"/, 'a slash is not allowed in a sheet name');
  assert.match(sheet, /rightToLeft="1"/, 'an Arabic workbook opens right to left');
  assert.match(sheet, /<c r="A1" s="1" t="inlineStr"><is><t>رقم العرض<\/t><\/is><\/c>/, 'headers are styled and inline');
  assert.match(sheet, /<c r="B2" s="2"><v>38318<\/v><\/c>/, 'a number cell is numeric, not text');
  assert.match(sheet, /<c r="C2" s="3"><v>46276<\/v><\/c>/, '2026-09-11 is Excel serial 46276');
  assert.match(sheet, /&quot;quoted&quot;/, 'quotes are escaped in XML');
  assert.ok(!/<c r="C3"/.test(sheet), 'a null cell is left out rather than written empty');
  assert.match(parts['xl/worksheets/sheet2.xml'], /<sheetData><row r="1">/, 'an empty sheet still has its header row');
});

test('the zip writer handles an empty file and a UTF-8 name', () => {
  const parts = readZip(zip([['مجلد/ملف.txt', Buffer.alloc(0)], ['b.txt', Buffer.from('hello')]]));
  assert.deepEqual(parts, { 'مجلد/ملف.txt': '', 'b.txt': 'hello' });
});
