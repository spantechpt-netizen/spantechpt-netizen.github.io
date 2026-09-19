/**
 * Settings seeding and in-place corrections, exercised directly against a
 * throwaway database rather than through the HTTP API.
 *
 *   npm test
 */
import { test, after } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const workDir = mkdtempSync(join(tmpdir(), 'spantech-seed-'));
process.env.DB_PATH = join(workDir, 'seed.db');
process.env.SESSION_SECRET = 'test-secret-value-for-automated-tests-only';

const { getSetting, setSetting, insert, run, nextCounter } = await import('../server/db.js');
const { seedSettings, reconcileCounters } = await import('../server/seed.js');
const { COMPANY, branchFor } = await import('../server/templates.js');

const CORRECT = COMPANY.branches.SA.cr_number;
const WRONG = '1010981534';

after(() => rmSync(workDir, { recursive: true, force: true }));

test('a fresh install seeds the Saudi registration', () => {
  seedSettings();
  assert.equal(getSetting('company').branches.SA.cr_number, CORRECT);
  assert.notEqual(CORRECT, WRONG);
});

test('an install seeded with the wrong registration is corrected', () => {
  const company = getSetting('company');
  company.branches.SA.cr_number = WRONG;
  setSetting('company', company);

  seedSettings();
  assert.equal(getSetting('company').branches.SA.cr_number, CORRECT);
});

test('a registration the company edited itself is never overwritten', () => {
  const company = getSetting('company');
  company.branches.SA.cr_number = '4030123456';
  setSetting('company', company);

  seedSettings();
  assert.equal(getSetting('company').branches.SA.cr_number, '4030123456');
});

test('a country with no branch of its own borrows contact details, never a registration', () => {
  const branch = branchFor(COMPANY, 'AE');
  assert.equal(branch.phone, COMPANY.branches.SA.phone, 'contact details fall back');
  assert.equal(branch.cr_number, '', 'a Saudi registration never travels');
  assert.equal(branch.vat_number, '', 'nor a Saudi VAT number');
});

test('each branch prints its own identity', () => {
  const qa = branchFor(COMPANY, 'QA');
  assert.match(qa.name_en, /SPAN TEC Trading/);
  assert.equal(qa.cr_number, '175473');
  assert.match(qa.logo, /logo-qa/, 'Qatar carries its own mark');

  const eg = branchFor(COMPANY, 'EG');
  assert.equal(eg.cr_number, '', 'Egypt has no registration on file yet');
  assert.match(eg.email, /spantechpt\.com$/i);
  assert.doesNotMatch(eg.logo, /logo-qa/, 'and not the Qatar mark');
});

test('a half-filled branch fills the gaps from the default branch', () => {
  const company = JSON.parse(JSON.stringify(COMPANY));
  company.branches.QA.phone = '';
  const qa = branchFor(company, 'QA');
  assert.equal(qa.phone, COMPANY.branches.SA.phone, 'the missing phone falls back');
  assert.equal(qa.cr_number, '175473', 'without disturbing what is filled in');
});

// --------------------------------------------------------------- sequences
// The demo data writes codes numbered from one without touching the counters,
// which used to make the first customer added afterwards collide on the unique
// index and fail with a 500.
test('a counter is raised past codes that were written around it', () => {
  insert('customers', { name_en: 'Seeded One', code: 'C-0001', country: 'SA' });
  insert('customers', { name_en: 'Seeded Seven', code: 'C-0007', country: 'SA' });

  reconcileCounters();
  assert.equal(nextCounter('customer'), 8, 'the next code must clear C-0007');
});

test('a counter already ahead is never pulled back', () => {
  run("INSERT INTO counters (key, value) VALUES ('customer', 99) ON CONFLICT(key) DO UPDATE SET value = 99");
  reconcileCounters();
  assert.equal(nextCounter('customer'), 100);
});

test('quotation numbers reconcile per calendar year', () => {
  const customer = insert('customers', { name_en: 'Numbering Test', code: 'C-0100', country: 'SA' });
  const quote = (number, issue) => insert('quotations', {
    customer_id: customer, number, revision: 0, issue_date: issue,
    project_name: 'Numbering', country: 'SA', currency: 'SAR',
  });
  quote('SPAN TECH P.T - 25 - 014', '2025-06-01');
  quote('SPAN TECH P.T - 26 - 003', '2026-02-01');

  reconcileCounters();
  assert.equal(nextCounter('quote_2025'), 15, '2025 continues from its own last number');
  assert.equal(nextCounter('quote_2026'), 4, 'and 2026 from its own');
});
