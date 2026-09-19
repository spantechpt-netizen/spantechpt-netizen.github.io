/**
 * Extraction helpers that do not touch the database, exercised directly.
 *
 *   npm test
 */
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-extract-'));
process.env.DB_PATH = join(workDir, 'extract.db');
process.env.SESSION_SECRET = 'test-secret-value-for-automated-tests-only';

const { extractCompanyName, phoneKey, extractArea } = await import('../server/extract.js');

after(() => rmSync(workDir, { recursive: true, force: true }));

// A WhatsApp message almost always ends in a sign-off, and the company name is
// buried in it. Reading the farewell as the customer name is worse than
// reading nothing, because the reviewer has to notice and undo it.
test('a company name is read out of a signature line', () => {
  const cases = [
    ['تحياتي — م. أحمد من شركة المستقبل للمقاولات', 'شركة المستقبل للمقاولات'],
    ['مع تحياتي، م. خالد من مجموعة الفيصل', 'مجموعة الفيصل'],
    ['Best regards, Ahmed Fathy of Delta Contracting Co.', 'Delta Contracting Co.'],
    ['شكرا, Eng. Sami of Awtad Construction', 'Awtad Construction'],
  ];
  for (const [line, expected] of cases) {
    assert.equal(extractCompanyName(null, line, null), expected, line);
  }
});

test('a name that only looks like a signature is left whole', () => {
  // "of" here is part of the name, not a connector to the person's employer.
  assert.equal(
    extractCompanyName(null, 'Ministry of Housing — General Contracting Dept.', null),
    'Ministry of Housing — General Contracting Dept.',
  );
  assert.equal(
    extractCompanyName(null, 'شركة الراجحي للمقاولات', null),
    'شركة الراجحي للمقاولات',
  );
});

// WhatsApp reports a number in international form; the CRM holds whatever the
// engineer typed. They have to match anyway.
test('a phone number matches however it was written', () => {
  const key = phoneKey('0551234477');
  assert.equal(phoneKey('+966551234477'), key);
  assert.equal(phoneKey('00966 55 123 4477'), key);
  assert.equal(phoneKey('+966 55-123-4477'), key);
  assert.equal(phoneKey('٠٥٥١٢٣٤٤٧٧'), key, 'Arabic-Indic digits too');

  assert.notEqual(phoneKey('0551234478'), key, 'one digit out is a different number');
  assert.equal(phoneKey('1234'), null, 'too short to identify anybody');
  assert.equal(phoneKey(''), null);
  assert.equal(phoneKey(null), null);
});

test('an area survives the way people actually write it', () => {
  assert.equal(extractArea('المساحة حوالي 12,500 متر مربع'), 12500);
  assert.equal(extractArea('area is 9800 m2'), 9800);
  assert.equal(extractArea('٤٧٦ متر مربع'), 476);
});
