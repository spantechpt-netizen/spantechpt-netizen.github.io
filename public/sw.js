/**
 * A deliberately empty service worker.
 *
 * It exists only so the browser treats the CRM as installable, which is what
 * puts it in the phone's share sheet — share a WhatsApp message to Span Tech
 * and it lands in the incoming requests queue.
 *
 * It caches nothing on purpose. The app is served from the company's own
 * server and updates by deploying; a caching worker would go on serving
 * yesterday's JavaScript after an update, which is a far worse problem than
 * the one offline support would solve here.
 */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', (event) => event.respondWith(fetch(event.request)));
