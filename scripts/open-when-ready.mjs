/**
 * Opens the browser once the server is actually answering.
 *
 *   node scripts/open-when-ready.mjs
 *
 * A fixed sleep before opening the browser is a race: on a cold Windows
 * machine with antivirus inspecting every file, the first start can take well
 * over the couple of seconds a script is willing to guess at, and the person
 * gets a browser error page for a server that is about to come up fine.
 * This polls the health endpoint instead and opens the moment it answers.
 */
import { spawn } from 'node:child_process';
import { config } from '../server/config.js';

const URL_ = `http://localhost:${config.port}`;
const DEADLINE = Date.now() + 90_000;

const open = () => {
  const [command, args] = process.platform === 'win32'
    ? ['cmd', ['/c', 'start', '', URL_]]
    : process.platform === 'darwin'
      ? ['open', [URL_]]
      : ['xdg-open', [URL_]];
  try {
    spawn(command, args, { detached: true, stdio: 'ignore' }).unref();
  } catch {
    console.log(`\n  افتح المتصفح على: ${URL_}\n`);
  }
};

while (Date.now() < DEADLINE) {
  try {
    const res = await fetch(`${URL_}/api/health`);
    if (res.ok) {
      open();
      process.exit(0);
    }
  } catch { /* not listening yet */ }
  await new Promise((r) => setTimeout(r, 300));
}

console.log(`\n  السيرفر أخد وقت أطول من المتوقع. افتح المتصفح يدوياً على: ${URL_}\n`);
