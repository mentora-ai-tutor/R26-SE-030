'use strict';

const errorHandler = require('../../../services/assessment-agent/src/middleware/errorHandler');

function makeRes() {
  const res = { statusCode: 200, body: null };
  res.status = jest.fn((code) => {
    res.statusCode = code;
    return res;
  });
  res.json = jest.fn((body) => {
    res.body = body;
  });
  return res;
}

describe('errorHandler', () => {
  test('responds with the provided status code and message', () => {
    const res = makeRes();
    const next = jest.fn();

    errorHandler({ statusCode: 404, message: 'Not found' }, {}, res, next);

    expect(res.statusCode).toBe(404);
    expect(res.body).toEqual({ success: false, message: 'Not found' });
  });

  test('defaults to 500 / Internal server error and does not call next', () => {
    const res = makeRes();
    const next = jest.fn();

    errorHandler(new Error('boom'), {}, res, next);

    expect(res.statusCode).toBe(500);
    expect(res.body.success).toBe(false);
    expect(res.body.message).toBe('boom');
    expect(next).not.toHaveBeenCalled();
  });
});