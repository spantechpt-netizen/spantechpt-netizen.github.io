/**
 * Pre-flight for a server that already runs other things.
 *
 *   npm run check
 *
 * The CRM is going onto a machine with Next.js and .NET already on it, behind
 * an nginx that is already serving other sites. Everything this checks is a
 * thing that fails at the worst moment otherwise: a Node too old for
 * node:sqlite, a port another application already holds, a data directory the
 * service account cannot write to, or a session secret still set to the
 * development default.
 *
 * Exits non-zero if anything is wrong, so it can gate a deployment step.
 */
import { createServer } from 'node:net';
import { mkdirSync, writeFileSync, unlinkSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { config, isDefaultSecret } from '../server/config.js';

const results = [];
const record = (ok, label, detail) => results.push({ ok, label, detail });

// ------------------------------------------------------------ node version
const [major, minor] = process.versions.node.split('.').map(Number);
const nodeOk = major > 22 || (major === 22 && minor >= 5);
record(
  nodeOk,
  `Node ${process.versions.node}`,
  nodeOk
    ? 'has the built-in node:sqlite module'
    : 'too old — node:sqlite needs 22.5 or newer. A Next.js app on this server '
      + 'may be pinned to an older Node; this one needs its own.',
);

// node:sqlite is experimental, so confirm it is actually there rather than
// trusting the version number.
let sqliteOk = false;
try {
  await import('node:sqlite');
  sqliteOk = true;
} catch { /* reported below */ }
record(sqliteOk, 'node:sqlite', sqliteOk ? 'available' : 'not available in this Node build');

// -------------------------------------------------------------------- port
const free = await new Promise((resolve) => {
  const probe = createServer();
  probe.once('error', () => resolve(false));
  probe.once('listening', () => probe.close(() => resolve(true)));
  probe.listen(config.port, config.host);
});
record(
  free,
  `Port ${config.port} on ${config.host}`,
  free
    ? 'free'
    : 'already taken. Another application on this server is using it — set a '
      + 'different PORT in .env and point nginx at that one instead.',
);

// --------------------------------------------------------------- data dir
const dataDir = dirname(config.dbPath);
let writable = false;
let writeError = '';
try {
  mkdirSync(dataDir, { recursive: true });
  const probe = join(dataDir, `.write-check-${process.pid}`);
  writeFileSync(probe, 'ok');
  unlinkSync(probe);
  writable = true;
} catch (error) {
  writeError = error.message;
}
record(
  writable,
  `Database directory ${dataDir}`,
  writable ? 'writable' : `not writable — ${writeError}`,
);

// ------------------------------------------------------------------ secret
const secretOk = !isDefaultSecret();
record(
  secretOk,
  'SESSION_SECRET',
  secretOk
    ? 'set'
    : 'still the development default. Sessions would be forgeable, and mailbox '
      + 'passwords are encrypted with a key derived from it.',
);

// ------------------------------------------------------------------ report
const pad = Math.max(...results.map((r) => r.label.length));
console.log('');
for (const { ok, label, detail } of results) {
  console.log(`  ${ok ? '✓' : '✗'}  ${label.padEnd(pad)}  ${detail}`);
}

const failed = results.filter((r) => !r.ok);
console.log('');
if (failed.length) {
  console.log(`  ${failed.length} problem(s) to fix before starting the service.\n`);
  process.exit(1);
}
console.log('  Ready to start.\n');
