import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { config, ROOT } from './config.js';

mkdirSync(dirname(config.dbPath), { recursive: true });

export const db = new DatabaseSync(config.dbPath);

db.exec('PRAGMA journal_mode = WAL;');
db.exec('PRAGMA foreign_keys = ON;');
db.exec('PRAGMA busy_timeout = 5000;');
db.exec(readFileSync(resolve(ROOT, 'server/schema.sql'), 'utf8'));

/**
 * `CREATE TABLE IF NOT EXISTS` never alters an existing table, so columns
 * added after a deployment went live are applied here instead. Adding a
 * column that is already present is skipped, making this safe to re-run.
 */
function addColumn(table, column, definition) {
  const columns = db.prepare(`PRAGMA table_info(${table})`).all();
  if (columns.some((c) => c.name === column)) return;
  db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${definition}`);
}

// Private calendar feed token, and how far ahead a follow-up reminder fires.
addColumn('users', 'calendar_token', 'TEXT');
addColumn('users', 'reminder_lead_hours', 'INTEGER NOT NULL DEFAULT 24');
// Days of silence after which a customer counts as "missed contact".
addColumn('users', 'stale_after_days', 'INTEGER NOT NULL DEFAULT 30');
// Per-user permission overrides on top of the role defaults, as JSON.
addColumn('users', 'permissions', 'TEXT');
// Accept a self-signed certificate on an internal mail server.
addColumn('mail_accounts', 'allow_self_signed', 'INTEGER NOT NULL DEFAULT 0');
// Requests do not all arrive by email. A capture account holds the ones a
// person pasted in — from WhatsApp, a phone call, a meeting — so they land in
// the same triage queue as the mail, with the same extraction behind them.
addColumn('mail_accounts', 'channel', "TEXT NOT NULL DEFAULT 'imap'");
addColumn('mail_messages', 'channel', "TEXT NOT NULL DEFAULT 'email'");
addColumn('mail_messages', 'from_phone', 'TEXT');
// Ducts are galvanized steel in most markets and corrugated plastic in Egypt.
addColumn('quotations', 'duct_type', "TEXT NOT NULL DEFAULT 'steel'");
// Drawings were created without the column update() writes on every row.
addColumn('study_drawings', 'updated_at', 'TEXT');
// Labour is ours on some projects and the main contractor's on others.
addColumn('quotations', 'labour_scope', "TEXT NOT NULL DEFAULT 'spantech'");
// The cost comparison study sent to the owner, and the drawings attached to it.
addColumn('quotations', 'study_json', 'TEXT');
// Every message is filed under the customer it came from or went to, by the
// address, so a customer's record carries its own correspondence.
addColumn('mail_messages', 'customer_id', 'INTEGER REFERENCES customers(id) ON DELETE SET NULL');
db.exec('CREATE INDEX IF NOT EXISTS idx_mail_msg_customer ON mail_messages(customer_id, received_at)');
// How each person arranged the dashboard, as JSON.
addColumn('users', 'dashboard_json', 'TEXT');
// Which layout a quotation prints in, and the wording edited on that print.
addColumn('quotations', 'print_json', 'TEXT');

/** Runs a SELECT and returns every row. */
export const all = (sql, ...params) => db.prepare(sql).all(...params);

/** Runs a SELECT and returns the first row (or undefined). */
export const get = (sql, ...params) => db.prepare(sql).get(...params);

/** Runs an INSERT/UPDATE/DELETE and returns { changes, lastInsertRowid }. */
export const run = (sql, ...params) => db.prepare(sql).run(...params);

let txDepth = 0;

/**
 * Wraps `fn` in a transaction, rolling back if it throws.
 * Re-entrant: nested calls use SAVEPOINTs, so a helper that opens its own
 * transaction (nextCounter, for example) still works inside a larger one.
 */
export function transaction(fn) {
  const nested = txDepth > 0;
  const savepoint = `sp_${txDepth}`;
  db.exec(nested ? `SAVEPOINT ${savepoint}` : 'BEGIN');
  txDepth += 1;
  try {
    const result = fn();
    db.exec(nested ? `RELEASE ${savepoint}` : 'COMMIT');
    txDepth -= 1;
    return result;
  } catch (error) {
    txDepth -= 1;
    try {
      db.exec(nested ? `ROLLBACK TO ${savepoint}; RELEASE ${savepoint}` : 'ROLLBACK');
    } catch { /* connection already unwound */ }
    throw error;
  }
}

/**
 * Builds `INSERT INTO table (...) VALUES (...)` from a plain object,
 * skipping undefined values so partial payloads are safe.
 */
export function insert(table, data) {
  const entries = Object.entries(data).filter(([, v]) => v !== undefined);
  const cols = entries.map(([k]) => k);
  const placeholders = cols.map(() => '?').join(', ');
  const sql = `INSERT INTO ${table} (${cols.join(', ')}) VALUES (${placeholders})`;
  const result = run(sql, ...entries.map(([, v]) => normalise(v)));
  return Number(result.lastInsertRowid);
}

/** Builds `UPDATE table SET ... WHERE id = ?`. Returns the number of rows changed. */
export function update(table, id, data) {
  const entries = Object.entries(data).filter(([, v]) => v !== undefined);
  if (!entries.length) return 0;
  const sets = entries.map(([k]) => `${k} = ?`).join(', ');
  const sql = `UPDATE ${table} SET ${sets}, updated_at = datetime('now') WHERE id = ?`;
  return run(sql, ...entries.map(([, v]) => normalise(v)), id).changes;
}

// SQLite only binds null/number/bigint/string/Uint8Array — map JS values onto those.
function normalise(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'object') return JSON.stringify(value);
  return value;
}

// ------------------------------------------------------------------ settings
export function getSetting(key, fallback = null) {
  const row = get('SELECT value_json FROM settings WHERE key = ?', key);
  if (!row) return fallback;
  try { return JSON.parse(row.value_json); } catch { return fallback; }
}

export function setSetting(key, value) {
  run(
    `INSERT INTO settings (key, value_json, updated_at) VALUES (?, ?, datetime('now'))
     ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = datetime('now')`,
    key,
    JSON.stringify(value),
  );
  return value;
}

export function allSettings() {
  const out = {};
  for (const row of all('SELECT key, value_json FROM settings')) {
    try { out[row.key] = JSON.parse(row.value_json); } catch { /* skip corrupt row */ }
  }
  return out;
}

// ------------------------------------------------------------------ counters
/** Atomically increments a named counter and returns the new value. */
export function nextCounter(key) {
  return transaction(() => {
    run('INSERT INTO counters (key, value) VALUES (?, 0) ON CONFLICT(key) DO NOTHING', key);
    run('UPDATE counters SET value = value + 1 WHERE key = ?', key);
    return get('SELECT value FROM counters WHERE key = ?', key).value;
  });
}

// ----------------------------------------------------------------- audit log
export function audit(userId, entity, entityId, action, detail = null) {
  insert('audit_log', {
    user_id: userId ?? null,
    entity,
    entity_id: entityId ?? null,
    action,
    detail_json: detail ? JSON.stringify(detail) : null,
  });
}
