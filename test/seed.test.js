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

const { getSetting, setSetting } = await import('../server/db.js');
const { seedSettings } = await import('../server/seed.js');
const { COMPANY } = await import('../server/templates.js');

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
