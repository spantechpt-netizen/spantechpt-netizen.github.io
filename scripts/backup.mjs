/**
 * Takes a consistent snapshot of the database while the server is running.
 *
 *   npm run backup                 -> ./backups/spantech-YYYY-MM-DD.db
 *   npm run backup -- D:\backups   -> that directory instead
 *
 * `VACUUM INTO` is a single SQLite statement that writes a complete, compacted
 * copy of the database at one point in time. It needs no sqlite3 command-line
 * tool, which is the difference between "works on Linux" and "works anywhere
 * Node runs" — copying the file with cp or copy is not safe while the server
 * is writing, because the recent transactions are still in the -wal file.
 *
 * Old snapshots are pruned by KEEP_DAYS so the disk cannot fill up silently.
 */
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, readdirSync, statSync, unlinkSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { config, ROOT } from '../server/config.js';

const KEEP_DAYS = Number(process.env.BACKUP_KEEP_DAYS || 30);
const outDir = resolve(ROOT, process.argv[2] || process.env.BACKUP_DIR || './backups');

if (!existsSync(config.dbPath)) {
  console.error(`No database at ${config.dbPath} — nothing to back up.`);
  process.exit(1);
}

mkdirSync(outDir, { recursive: true });

const stamp = new Date().toISOString().slice(0, 10);
let target = join(outDir, `spantech-${stamp}.db`);
// More than one run in a day should not overwrite the earlier snapshot.
for (let n = 2; existsSync(target); n += 1) {
  target = join(outDir, `spantech-${stamp}-${n}.db`);
}

const db = new DatabaseSync(config.dbPath, { readOnly: true });
try {
  // The path goes into SQL as a string literal, so a quote in it must be doubled.
  db.exec(`VACUUM INTO '${target.replace(/'/g, "''")}'`);
} finally {
  db.close();
}

const size = (statSync(target).size / 1024 / 1024).toFixed(1);
console.log(`Backed up to ${target} (${size} MB)`);

// --------------------------------------------------------------- retention
const cutoff = Date.now() - KEEP_DAYS * 86_400_000;
let removed = 0;
for (const name of readdirSync(outDir)) {
  if (!/^spantech-\d{4}-\d{2}-\d{2}(-\d+)?\.db$/.test(name)) continue;
  const file = join(outDir, name);
  if (statSync(file).mtimeMs >= cutoff) continue;
  unlinkSync(file);
  removed += 1;
}
if (removed) console.log(`Removed ${removed} snapshot(s) older than ${KEEP_DAYS} days.`);
