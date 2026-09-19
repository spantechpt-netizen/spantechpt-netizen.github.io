/**
 * Light and dark.
 *
 * The choice is the browser's, kept in localStorage: 'light', 'dark', or
 * nothing, which follows the operating system. index.html applies it before
 * the stylesheet paints so a dark screen never flashes white; this module
 * owns the toggle and keeps following the system while nothing is chosen.
 */
const KEY = 'spantech_theme';
const media = window.matchMedia?.('(prefers-color-scheme: dark)');

export function currentTheme() {
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
  if (saved === 'dark' || saved === 'light') return saved;
  return media?.matches ? 'dark' : 'light';
}

export function applyTheme(theme = currentTheme()) {
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.content = theme === 'dark' ? '#0f172a' : '#0a2647';
  window.dispatchEvent(new CustomEvent('spantech:theme', { detail: { theme } }));
}

export function setTheme(theme) {
  try { localStorage.setItem(KEY, theme); } catch { /* storage blocked */ }
  applyTheme(theme);
}

export const toggleTheme = () => setTheme(currentTheme() === 'dark' ? 'light' : 'dark');

// Following the system only while no explicit choice is stored.
media?.addEventListener?.('change', () => {
  let saved = null;
  try { saved = localStorage.getItem(KEY); } catch { /* storage blocked */ }
  if (!saved) applyTheme();
});
