/**
 * The API description is built from the router, so it cannot drift: every
 * registered route is in it, with its parameters and whether it needs a
 * session.
 *
 *   npm test
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Router } from '../server/http.js';
import { buildOpenApi, docsPage } from '../server/openapi.js';

test('every route becomes a path, with parameters and security', () => {
  const router = new Router();
  router.get('/api/customers', () => {});
  router.post('/api/customers', () => {});
  router.get('/api/customers/:id/mail/:messageId', () => {});
  router.get('/api/health', () => {}, { public: true });
  router.get('/api/events', () => {}, { stream: true });
  router.post('/api/quotations/:id/study/drawings', () => {}, { rawBody: true });
  router.get('/api/quotations/export', () => {});

  const doc = buildOpenApi(router, { serverUrl: 'http://crm.local' });
  assert.equal(doc.openapi, '3.0.3');
  assert.deepEqual(doc.servers, [{ url: 'http://crm.local' }]);

  const list = doc.paths['/api/customers'];
  assert.equal(list.get.summary, 'List customers, filtered by q, country, status, type and scope.');
  assert.match(list.get.description, /Requires: customers.view/);
  assert.deepEqual(list.get.security, [{ cookieAuth: [] }]);
  assert.ok(list.post.requestBody, 'a POST takes a JSON body');
  assert.ok(list.post.responses[201], 'and answers 201');

  const mail = doc.paths['/api/customers/{id}/mail/{messageId}'].get;
  assert.deepEqual(mail.parameters.map((p) => p.name), ['id', 'messageId']);
  assert.equal(mail.parameters[0].in, 'path');
  assert.equal(mail.tags[0], 'Customers');

  assert.deepEqual(doc.paths['/api/health'].get.security, [], 'a public route needs no session');
  assert.ok(doc.paths['/api/events'].get.responses[200].content['text/event-stream'], 'the stream is described as one');
  assert.ok(doc.paths['/api/quotations/{id}/study/drawings'].post.requestBody.content['image/*'], 'an upload takes the file as the body');

  const exp = doc.paths['/api/quotations/export'].get;
  assert.deepEqual(exp.parameters.map((p) => p.name), ['format', 'lang']);
  assert.deepEqual(doc.tags.map((t) => t.name), ['Customers', 'Notifications', 'Quotations', 'System']);
});

test('the docs page is self-contained', () => {
  const html = docsPage();
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /fetch\('\/api\/openapi\.json'/, 'it reads the document from this server');
  assert.ok(!/https?:\/\/(cdn|unpkg|jsdelivr)/i.test(html), 'and loads nothing from the internet');
});
