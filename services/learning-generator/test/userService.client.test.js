const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const axios = require('axios');

const userServiceClient = require('../src/services/userService.client');
const ServiceError = require('../src/utils/ServiceError');

const makeAxiosError = (overrides = {}) => {
  const err = new Error(overrides.message || 'Request failed');
  Object.assign(err, overrides);
  return err;
};

test('verifyToken returns valid student when user service says valid', async (t) => {
  mock.method(axios, 'post', async () => ({
    data: { valid: true, student: { id: 'STU_1', name: 'Ada' } },
  }));
  t.after(() => mock.restoreAll());

  const result = await userServiceClient.verifyToken('abc123');
  assert.equal(result.valid, true);
  assert.equal(result.student.id, 'STU_1');
  assert.equal(result.student.name, 'Ada');

  const post = axios.post.mock.calls[0];
  assert.equal(post.arguments[0], `${userServiceClient.baseUrl}/internal/auth/verify`);
  assert.deepEqual(post.arguments[1], { token: 'abc123' });
});

test('verifyToken returns invalid when user service says invalid', async (t) => {
  mock.method(axios, 'post', async () => ({ data: { valid: false, error: 'Expired' } }));
  t.after(() => mock.restoreAll());

  const result = await userServiceClient.verifyToken('abc123');
  assert.equal(result.valid, false);
  assert.equal(result.error, 'Expired');
});

test('verifyToken throws USER_SERVICE_OFFLINE on connection refused', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.verifyToken('abc123'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_OFFLINE' && err.statusCode === 503
  );
});

test('verifyToken throws AUTH_FAILED on 401 response', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ response: { status: 401, data: { error: 'Bad token' } } });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.verifyToken('abc123'),
    (err) => err instanceof ServiceError && err.code === 'AUTH_FAILED' && err.statusCode === 401
  );
});

test('verifyToken throws USER_SERVICE_ERROR on 500 response', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ response: { status: 500, data: { error: 'boom' } } });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.verifyToken('abc123'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_ERROR' && err.statusCode === 500
  );
});

test('verifyToken throws USER_SERVICE_TIMEOUT on timeout', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ code: 'ECONNABORTED', message: 'timeout' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.verifyToken('abc123'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_TIMEOUT'
  );
});

test('verifyToken throws USER_SERVICE_ERROR on unexpected error', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ message: 'weird' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.verifyToken('abc123'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_ERROR' && err.statusCode === 500
  );
});

test('getStudent returns data on success', async (t) => {
  mock.method(axios, 'get', async () => ({ data: { id: 'STU_1' } }));
  t.after(() => mock.restoreAll());

  const data = await userServiceClient.getStudent('STU_1');
  assert.deepEqual(data, { id: 'STU_1' });
  assert.equal(axios.get.mock.calls[0].arguments[0], `${userServiceClient.baseUrl}/internal/students/STU_1`);
});

test('getStudent throws USER_SERVICE_OFFLINE on connection refused', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.getStudent('STU_1'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_OFFLINE'
  );
});

test('getStudent throws USER_SERVICE_ERROR on response error', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ response: { status: 404, data: {} } });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => userServiceClient.getStudent('STU_1'),
    (err) => err instanceof ServiceError && err.code === 'USER_SERVICE_ERROR' && err.statusCode === 404
  );
});

test('getStudent rethrows unexpected errors', async (t) => {
  const boom = makeAxiosError({ message: 'weird' });
  mock.method(axios, 'get', async () => {
    throw boom;
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(() => userServiceClient.getStudent('STU_1'), (err) => err === boom);
});

test('updateStudentStats patches stats and returns data on success', async (t) => {
  mock.method(axios, 'patch', async () => ({
    status: 200,
    data: { ok: true },
  }));
  t.after(() => mock.restoreAll());

  const stats = { materials_generated_increment: 3 };
  const result = await userServiceClient.updateStudentStats('STU_1', stats);
  assert.deepEqual(result, { ok: true });
  const patch = axios.patch.mock.calls[0];
  assert.equal(patch.arguments[0], `${userServiceClient.baseUrl}/internal/students/STU_1/stats`);
  assert.deepEqual(patch.arguments[1], stats);
});

test('updateStudentStats returns null on connection refused (fire and forget)', async (t) => {
  mock.method(axios, 'patch', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  assert.equal(await userServiceClient.updateStudentStats('STU_1', {}), null);
});

test('updateStudentStats returns null on any other error', async (t) => {
  mock.method(axios, 'patch', async () => {
    throw makeAxiosError({ response: { status: 500 } });
  });
  t.after(() => mock.restoreAll());

  assert.equal(await userServiceClient.updateStudentStats('STU_1', {}), null);
});

test('updateStudentStatsAsync swallows errors (fire and forget)', async (t) => {
  mock.method(axios, 'patch', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  userServiceClient.updateStudentStatsAsync('STU_1', {});
  await new Promise((resolve) => setImmediate(resolve));
});

test('checkHealth returns reachable on 2xx', async (t) => {
  mock.method(axios, 'get', async () => ({ status: 200 }));
  t.after(() => mock.restoreAll());
  assert.deepEqual(await userServiceClient.checkHealth(), { reachable: true, status: 200 });
});

test('checkHealth returns unreachable on error', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());
  assert.deepEqual(await userServiceClient.checkHealth(), { reachable: false });
});
