import { readFileSync, existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

// Minimal .env loader so the app stays dependency free.
function loadEnvFile() {
  const file = resolve(ROOT, '.env');
  if (!existsSync(file)) return;
  for (const rawLine of readFileSync(file, 'utf8').split('\n')) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const eq = line.indexOf('=');
    if (eq === -1) continue;
    const key = line.slice(0, eq).trim();
    let value = line.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] === undefined) process.env[key] = value;
  }
}

loadEnvFile();

const bool = (value, fallback) =>
  value === undefined ? fallback : ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase());

export const config = {
  port: Number(process.env.PORT || 8090),
  host: process.env.HOST || '0.0.0.0',
  dbPath: resolve(ROOT, process.env.DB_PATH || './data/spantech.db'),
  publicDir: resolve(ROOT, 'public'),
  sessionSecret: process.env.SESSION_SECRET || 'spantech-development-secret-change-me',
  sessionHours: Number(process.env.SESSION_HOURS || 72),
  secureCookies: bool(process.env.SECURE_COOKIES, false),
  admin: {
    email: process.env.ADMIN_EMAIL || 'admin@spantechksa.com',
    password: process.env.ADMIN_PASSWORD || 'SpanTech@2026',
    name: process.env.ADMIN_NAME || 'System Administrator',
  },
};

export const isDefaultSecret = () =>
  config.sessionSecret === 'spantech-development-secret-change-me';
