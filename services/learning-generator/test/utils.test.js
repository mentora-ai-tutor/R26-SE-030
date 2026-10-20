const { test } = require('node:test');
const assert = require('node:assert/strict');

const apiResponse = require('../src/utils/apiResponse');
const ServiceError = require('../src/utils/ServiceError');
const {
  masterySubmitSchema,
  materialQuerySchema,
  paginationQuerySchema,
  seedConceptGraphSchema,
  n8nWebhookSchema,
} = require('../src/utils/validationSchemas');

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

test('ServiceError stores code, statusCode, message and fix', () => {
  const err = new ServiceError('FOO', 503, 'message', 'fix string');
  assert.equal(err.code, 'FOO');
  assert.equal(err.statusCode, 503);
  assert.equal(err.message, 'message');
  assert.equal(err.fix, 'fix string');
  assert.equal(err.name, 'ServiceError');
  assert.ok(err instanceof Error);
});

test('ServiceError defaults fix to null', () => {
  const err = new ServiceError('BAR', 400, 'm');
  assert.equal(err.fix, null);
});

test('apiResponse.success returns success envelope with provided status', () => {
  const res = makeRes();
  apiResponse.success(res, { a: 1 }, 'Done', 200);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.success, true);
  assert.equal(res.body.message, 'Done');
  assert.deepEqual(res.body.data, { a: 1 });
});

test('apiResponse.created uses 201 and default message', () => {
  const res = makeRes();
  apiResponse.created(res, { id: 1 });
  assert.equal(res.statusCode, 201);
  assert.equal(res.body.success, true);
});

test('apiResponse.accepted uses 202', () => {
  const res = makeRes();
  apiResponse.accepted(res, { job_id: 'JOB_1' });
  assert.equal(res.statusCode, 202);
  assert.equal(res.body.data.job_id, 'JOB_1');
});

test('apiResponse.error builds failure envelope with optional fix', () => {
  const res = makeRes();
  apiResponse.error(res, 'bad', 'BAD', 400, 'do something');
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.success, false);
  assert.equal(res.body.code, 'BAD');
  assert.equal(res.body.fix, 'do something');
});

test('apiResponse.paginated wraps items and meta', () => {
  const res = makeRes();
  apiResponse.paginated(res, [1, 2], { page: 1, limit: 2, total: 2, pages: 1 });
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body.data.items, [1, 2]);
  assert.equal(res.body.data.meta.total, 2);
});

test('masterySubmitSchema accepts a valid payload', () => {
  const value = {
    student_id: 'STU_1',
    analysis_timestamp: '2026-01-01T00:00:00.000Z',
    mastery_profile: {
      overall_mastery_score: 50,
      knowledge_gaps: [
        { topic: 'Overriding', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' },
      ],
      strengths: [],
    },
    recommendations: {},
    data_sources: {},
  };
  const { error } = masterySubmitSchema.validate(value);
  assert.equal(error, undefined);
});

test('masterySubmitSchema rejects a payload with no knowledge gaps', () => {
  const value = {
    student_id: 'STU_1',
    mastery_profile: {
      overall_mastery_score: 50,
      knowledge_gaps: [],
    },
  };
  const { error } = masterySubmitSchema.validate(value);
  assert.ok(error);
});

test('masterySubmitSchema rejects an overall score out of range', () => {
  const value = {
    student_id: 'STU_1',
    mastery_profile: {
      overall_mastery_score: 150,
      knowledge_gaps: [{ topic: 'x', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' }],
    },
  };
  const { error } = masterySubmitSchema.validate(value);
  assert.ok(error);
});

test('materialQuerySchema rejects an invalid gap_type', () => {
  const { error } = materialQuerySchema.validate({ gap_type: 'NOPE' });
  assert.ok(error);
});

test('materialQuerySchema accepts valid query params', () => {
  const { error } = materialQuerySchema.validate({ gap_type: 'SURFACE_GAP', limit: 25, order: 'asc' });
  assert.equal(error, undefined);
});

test('paginationQuerySchema rejects limit above 100', () => {
  assert.ok(paginationQuerySchema.validate({ limit: 101 }).error);
  assert.equal(paginationQuerySchema.validate({ limit: 20, page: 2 }).error, undefined);
});

test('seedConceptGraphSchema validates an array of nodes', () => {
  const nodes = [
    { concept_id: 'a', name: 'A', category: 'OOP', bloom_level: 'apply', description: 'desc' },
  ];
  const { error } = seedConceptGraphSchema.validate(nodes);
  assert.equal(error, undefined);
});

test('seedConceptGraphSchema rejects an empty array', () => {
  const { error } = seedConceptGraphSchema.validate([]);
  assert.ok(error);
});

test('n8nWebhookSchema accepts a valid material payload', () => {
  const payload = {
    student_id: 'STU_1',
    material_id: 'MAT_1',
    topic: 'Inheritance',
    topic_id: 'java.oop.inheritance',
    gap_type: 'FUNDAMENTAL_GAP',
  };
  const { error } = n8nWebhookSchema.validate(payload);
  assert.equal(error, undefined);
});

test('n8nWebhookSchema rejects missing material_id', () => {
  const payload = {
    student_id: 'STU_1',
    topic: 'Inheritance',
    topic_id: 'java.oop.inheritance',
    gap_type: 'FUNDAMENTAL_GAP',
  };
  const { error } = n8nWebhookSchema.validate(payload);
  assert.ok(error);
});
