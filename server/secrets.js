/**
 * Encryption for the few secrets the CRM has to keep usable rather than
 * hashed — currently the IMAP password and the Claude API key.
 *
 * AES-256-GCM with a key derived from SESSION_SECRET. That ties the ciphertext
 * to this deployment: a stolen database file alone does not yield the mailbox
 * password. It is not a substitute for a real secrets manager, and rotating
 * SESSION_SECRET invalidates anything stored here — which is why decryption
 * fails softly and the settings screen asks for the password again.
 */
import { createCipheriv, createDecipheriv, randomBytes, scryptSync } from 'node:crypto';
import { config } from './config.js';

const KEY = scryptSync(config.sessionSecret, 'spantech-secret-box', 32);

export function encryptSecret(plain) {
  if (plain === null || plain === undefined || plain === '') return '';
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', KEY, iv);
  const enc = Buffer.concat([cipher.update(String(plain), 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `v1.${iv.toString('base64url')}.${tag.toString('base64url')}.${enc.toString('base64url')}`;
}

/** Returns null rather than throwing, so a rotated secret degrades gracefully. */
export function decryptSecret(stored) {
  if (!stored || typeof stored !== 'string') return null;
  const parts = stored.split('.');
  if (parts.length !== 4 || parts[0] !== 'v1') return null;
  try {
    const decipher = createDecipheriv('aes-256-gcm', KEY, Buffer.from(parts[1], 'base64url'));
    decipher.setAuthTag(Buffer.from(parts[2], 'base64url'));
    return Buffer.concat([
      decipher.update(Buffer.from(parts[3], 'base64url')),
      decipher.final(),
    ]).toString('utf8');
  } catch {
    return null;
  }
}

/** For showing that something is set without revealing it. */
export const maskSecret = (value) => {
  if (!value) return '';
  const text = String(value);
  if (text.length <= 4) return '••••';
  return `${'•'.repeat(Math.min(text.length - 2, 12))}${text.slice(-2)}`;
};
