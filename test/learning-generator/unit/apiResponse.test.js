'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');

require('../support/install');

const apiResponse = require('../../../services/learning-generator/src/utils/apiResponse');

const makeRes = () => {
  return {
    statusCode: null,
    body: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(payload) {
      this.body = payload;
      return this;
    },
  };
};

test('success() responds 200 with success/message/data envelope', () => {
  const res = makeRes();
  apiResponse.success(res, { items: [1] }, 'All good');
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.success, true);
  assert.equal(res.body.message, 'All good');
  assert.deepEqual(res.body.data, { items: [1] });
});

test('created() responds 201 and defaults the message', () => {
  const res = makeRes();
  apiResponse.created(res, { id: 'x' });
  assert.equal(res.statusCode, 201);
  assert.equal(res.body.success, true);
  assert.equal(res.body.message, 'Created successfully');
  assert.deepEqual(res.body.data, { id: 'x' });
});

test('accepted() responds 202', () => {
  const res = makeRes();
  apiResponse.accepted(res, { queued: true });
  assert.equal(res.statusCode, 202);
  assert.equal(res.body.data.queued, true);
});

test('error() responds with success=false and optional fix field', () => {
  const res = makeRes();
  apiResponse.error(res, 'Something broke', 'INTERNAL', 503, 'Restart the service');
  assert.equal(res.statusCode, 503);
  assert.equal(res.body.success, false);
  assert.equal(res.body.error, 'Something broke');
  assert.equal(res.body.code, 'INTERNAL');
  assert.equal(res.body.fix, 'Restart the service');
});

test('error() omits fix when not provided', () => {
  const res = makeRes();
  apiResponse.error(res, 'nope', 'BAD_REQUEST', 400);
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.fix, undefined);
});

test('paginated() wraps items and meta under data', () => {
  const res = makeRes();
  apiResponse.paginated(res, [1, 2], { page: 1, limit: 10, total: 2, pages: 1 });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.success, true);
  assert.deepEqual(res.body.data.items, [1, 2]);
  assert.deepEqual(res.body.data.meta, { page: 1, limit: 10, total: 2, pages: 1 });
});

test('success() memoizes the statusCode setter chain', () => {
  const res = makeRes();
  const ret = apiResponse.success(res, null);
  assert.equal(ret, res);
  assert.equal(res.body.success, true);
});
