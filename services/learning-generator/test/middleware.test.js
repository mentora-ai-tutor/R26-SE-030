const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const Joi = require('joi');

const ServiceError = require('../src/utils/ServiceError');
const { validate } = require('../src/middleware/validate.middleware');
const { errorMiddleware, notFoundMiddleware } = require('../src/middleware/error.middleware');
const { validateWebhookSecret } = require('../src/middleware/webhook.middleware');
const { protect } = require('../src/middleware/auth.middleware');
const userServiceClient = require('../src/services/userService.client');

const makeRes = () => {
  const res = {
    statusCode: null,
    body: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(body) {
      this.body = body;
      return this;
    },
  };
  return res;
};

test('validate passes a valid body through to next()', () => {
  const schema = Joi.object({ name: Joi.string().required() });
  const req = { body: { name: 'Ada' } };
  let nextCalled = false;
  const res = makeRes();
  validate(schema)(req, res, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
  assert.equal(req.body.name, 'Ada');
});

test('validate returns 400 with details on validation failure', () => {
  const schema = Joi.object({ name: Joi.string().required() });
  const req = { body: { name: '' } };
  const res = makeRes();
  validate(schema)(req, res, () => { throw new Error('next should not be called'); });
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.code, 'VALIDATION_ERROR');
  assert.ok(Array.isArray(res.body.details));
  assert.ok(res.body.details.length > 0);
  assert.ok(res.body.details[0].field);
});

test('errorMiddleware returns ServiceError shape with statusCode and fix', () => {
  const res = makeRes();
  const err = new ServiceError('N8N_OFFLINE', 503, 'offline', 'start n8n');
  errorMiddleware(err, { path: '/x', method: 'GET' }, res, () => {});
  assert.equal(res.statusCode, 503);
  assert.equal(res.body.code, 'N8N_OFFLINE');
  assert.equal(res.body.fix, 'start n8n');
  assert.equal(res.body.success, false);
});

test('errorMiddleware handles mongoose ValidationError (with errors object)', () => {
  const res = makeRes();
  const err = new Error('validation failed');
  err.name = 'ValidationError';
  err.errors = { name: { message: 'Name is required' } };
  errorMiddleware(err, { path: '/x', method: 'GET' }, res, () => {});
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.code, 'MONGOOSE_VALIDATION_ERROR');
  assert.deepEqual(res.body.details, [{ field: 'name', message: 'Name is required' }]);
});

test('errorMiddleware handles CastError', () => {
  const res = makeRes();
  const err = new Error('bad cast');
  err.name = 'CastError';
  err.path = 'profileId';
  err.value = 'abc';
  errorMiddleware(err, { path: '/x', method: 'GET' }, res, () => {});
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.code, 'CAST_ERROR');
});

test('errorMiddleware handles duplicate key (code 11000)', () => {
  const res = makeRes();
  const err = new Error('dup');
  err.code = 11000;
  err.keyValue = { email: 'a@b.c' };
  errorMiddleware(err, { path: '/x', method: 'GET' }, res, () => {});
  assert.equal(res.statusCode, 409);
  assert.equal(res.body.code, 'DUPLICATE_ERROR');
});

test('errorMiddleware handles JSON body parse errors', () => {
  const res = makeRes();
  const err = new Error('parse failed');
  err.type = 'entity.parse.failed';
  errorMiddleware(err, { path: '/x', method: 'POST' }, res, () => {});
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.code, 'JSON_PARSE_ERROR');
});

test('errorMiddleware falls back to 500 internal server error', () => {
  const res = makeRes();
  errorMiddleware(new Error('boom'), { path: '/x', method: 'GET' }, res, () => {});
  assert.equal(res.statusCode, 500);
  assert.equal(res.body.code, 'INTERNAL_ERROR');
});

test('notFoundMiddleware returns a 404 route message', () => {
  const res = makeRes();
  notFoundMiddleware({ path: '/nope', method: 'POST' }, res);
  assert.equal(res.statusCode, 404);
  assert.equal(res.body.code, 'NOT_FOUND');
  assert.match(res.body.error, /POST \/nope not found/);
});

test('validateWebhookSecret returns 401 when secret missing', () => {
  const req = { headers: {}, query: {}, path: '/webhooks/n8n', ip: '1.2.3.4' };
  const res = makeRes();
  validateWebhookSecret(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.code, 'WEBHOOK_SECRET_MISSING');
});

test('validateWebhookSecret returns 403 when secret wrong', () => {
  const config = require('../src/config/env');
  const req = {
    headers: { 'x-webhook-secret': 'wrong' },
    query: {},
    path: '/webhooks/n8n',
    ip: '1.2.3.4',
  };
  assert.notEqual('wrong', config.n8n.webhookSecret, 'test secret must differ from configured secret');
  const res = makeRes();
  validateWebhookSecret(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'WEBHOOK_SECRET_INVALID');
});

test('validateWebhookSecret calls next() on correct secret', () => {
  const config = require('../src/config/env');
  const req = {
    headers: { 'x-webhook-secret': config.n8n.webhookSecret },
    query: {},
    path: '/webhooks/n8n',
  };
  let nextCalled = false;
  validateWebhookSecret(req, makeRes(), () => { nextCalled = true; });
  assert.equal(nextCalled, true);
});

test('protect returns 401 when Authorization header missing', async () => {
  const req = { headers: {}, path: '/api/mastery/x', ip: '1.1.1.1' };
  const res = makeRes();
  await protect(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.code, 'AUTH_MISSING');
});

test('protect returns 401 when token empty', async () => {
  const req = { headers: { authorization: 'Bearer   ' }, path: '/api/mastery/x', ip: '1.1.1.1' };
  const res = makeRes();
  await protect(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.code, 'AUTH_EMPTY');
});

test('protect populates req.student on valid token', async (t) => {
  mock.method(userServiceClient, 'verifyToken', async () => ({
    valid: true,
    student: { id: 'STU_1', name: 'Ada', role: 'student', is_active: true },
  }));
  t.after(() => mock.restoreAll());

  const req = { headers: { authorization: 'Bearer abc' }, path: '/api/mastery/x', ip: '1.1.1.1' };
  const res = makeRes();
  let nextCalled = false;
  await protect(req, res, () => { nextCalled = true; });
  assert.equal(nextCalled, true);
  assert.equal(req.student.id, 'STU_1');
  assert.equal(req.student.name, 'Ada');
});

test('protect returns 401 when token invalid', async (t) => {
  mock.method(userServiceClient, 'verifyToken', async () => ({
    valid: false,
    error: 'Invalid token',
  }));
  t.after(() => mock.restoreAll());

  const req = { headers: { authorization: 'Bearer bad' }, path: '/api/mastery/x', ip: '1.1.1.1' };
  const res = makeRes();
  await protect(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 401);
  assert.equal(res.body.code, 'AUTH_INVALID');
});

test('protect returns 503 when user service is offline', async (t) => {
  mock.method(userServiceClient, 'verifyToken', async () => {
    throw new ServiceError('USER_SERVICE_OFFLINE', 503, 'offline', 'start user service');
  });
  t.after(() => mock.restoreAll());

  const req = { headers: { authorization: 'Bearer abc' }, path: '/api/mastery/x', ip: '1.1.1.1' };
  const res = makeRes();
  await protect(req, res, () => { throw new Error('next'); });
  assert.equal(res.statusCode, 503);
  assert.equal(res.body.code, 'USER_SERVICE_OFFLINE');
});
