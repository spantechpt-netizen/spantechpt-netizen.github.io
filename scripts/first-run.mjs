/**
 * Gets a trial copy running with no decisions to make.
 *
 *   npm run demo
 *
 * Writes a .env with a freshly generated session secret if there isn't one,
 * seeds the demo customers, opportunities and quotations if the database is
 * empty, and prints the address and the logins. Safe to run again: it never
 * overwrites an existing .env and never re-seeds a database that has data.
 */
import { randomBytes } from 'node:crypto';
import { existsSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { ROOT } from '../server/config.js';

const envPath = resolve(ROOT, '.env');
const line = '─'.repeat(62);

// ------------------------------------------------------------------- .env
if (existsSync(envPath)) {
  console.log('  .env is already here — leaving it alone.');
} else {
  writeFileSync(envPath, `# Span Tech CRM — trial configuration, generated on first run.
PORT=8090
HOST=0.0.0.0
DB_PATH=./data/spantech.db

# Generated for this machine. Changing it signs everyone out and makes any
# saved mailbox password unreadable, so keep it.
SESSION_SECRET=${randomBytes(48).toString('hex')}
SESSION_HOURS=72

# A trial over plain http:// — set to true once there is a certificate.
SECURE_COOKIES=false

ADMIN_EMAIL=admin@spantechksa.com
ADMIN_PASSWORD=SpanTech@2026
ADMIN_NAME=System Administrator
`);
  console.log('  Wrote .env with a session secret generated for this machine.');
}

// -------------------------------------------------------------------- data
// Imported after .env exists, because config reads it at import time.
const { config } = await import('../server/config.js');
const fresh = !existsSync(config.dbPath);

if (fresh) {
  console.log('  Seeding demo data (customers, quotations, follow-ups)…');
  const seed = spawnSync(process.execPath, ['--no-warnings', 'server/seed.js', '--demo'], {
    cwd: ROOT, stdio: 'inherit',
  });
  if (seed.status !== 0) {
    console.error('\n  Seeding failed. The application will still start, but empty.\n');
  }
} else {
  console.log('  Database already exists — keeping what is in it.');
}

// ------------------------------------------------------------------ report
console.log(`
  ${line}
   Span Tech CRM  |  نسخة تجربة
  ${line}

   افتح المتصفح على:   http://localhost:${config.port}

   مدير النظام        admin@spantechksa.com     SpanTech@2026
   مدير مكتب فني      ahmed@spantechksa.com     SpanTech@2026
   مهندس مشاريع       mahmoud@spantechksa.com   SpanTech@2026
   مهندس مبيعات       khaled@spantechksa.com    SpanTech@2026

   كل حساب بيشوف حاجات مختلفة — جرّب تدخل بأكتر من واحد.
   البيانات كلها في ملف data/spantech.db — امسحه عشان تبدأ من أول وجديد.

  ${line}
`);
