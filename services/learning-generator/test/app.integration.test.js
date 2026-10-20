const { test, before, after, mock } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

const app = require('../src/app');
const userServiceClient = require('../src/services/userService.client');

const server = http.createServer(app);
let baseUrl;

before(async () => {
  await new Promise((resolve) => server.listen(0, resolve));
  const address = server.address();
  baseUrl = `http://127.0.0.1:${address.port}`;
});

after(async () => {
  mock.restoreAll();
  await new Promise((resolve) => server.close(resolve));
});

const get = (path, headers = {}) => fetch(baseUrl + path, {
  method: 'GET',
  headers: { 'Content-Type': 'application/json', ...headers },
});

const post = (path, headers = {}, body) => fetch(baseUrl + path, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', ...headers },
  body: body ? JSON.stringify(body) : undefined,
});

test('GET /health returns running service info', async () => {
  const res = await get('/health');
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.success, true);
  assert.equal(body.data.service, 'lmg-service');
  assert.equal(body.data.status, 'running');
});

test('GET /api/materials without token returns 401 AUTH_MISSING', async () => {
  const res = await get('/api/materials');
  assert.equal(res.status, 401);
  const body = await res.json();
  assert.equal(body.success, false);
  assert.equal(body.code, 'AUTH_MISSING');
});

test('GET protected route returns 401 AUTH_INVALID when token verification fails', async (t) => {
  mock.method(userServiceClient, 'verifyToken', async () => ({ valid: false, error: 'Bad token' }));
  t.after(() => mock.restoreAll());
  const res = await get('/api/materials', { Authorization: 'Bearer bad-token' });
  assert.equal(res.status, 401);
  const body = await res.json();
  assert.equal(body.code, 'AUTH_INVALID');
});

test('GET protected route returns 503 when user service is offline', async (t) => {
  const ServiceError = require('../src/utils/ServiceError');
  const err = new ServiceError('USER_SERVICE_OFFLINE', 503, 'User Service offline');
  mock.method(userServiceClient, 'verifyToken', async () => { throw err; });
  t.after(() => mock.restoreAll());
  const res = await get('/api/materials', { Authorization: 'Bearer token' });
  assert.equal(res.status, 503);
  const body = await res.json();
  assert.equal(body.code, 'USER_SERVICE_OFFLINE');
});

test('POST /api/webhooks/n8n/material without secret returns 401', async () => {
  const res = await post('/api/webhooks/n8n/material');
  assert.equal(res.status, 401);
  const body = await res.json();
  assert.equal(body.code, 'WEBHOOK_SECRET_MISSING');
});

test('POST /api/webhooks/n8n/material with invalid secret returns 403', async () => {
  const res = await post('/api/webhooks/n8n/material', { 'x-webhook-secret': 'wrong' });
  assert.equal(res.status, 403);
  const body = await res.json();
  assert.equal(body.code, 'WEBHOOK_SECRET_INVALID');
});
