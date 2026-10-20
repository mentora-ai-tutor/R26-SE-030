const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const MasteryProfile = require('../src/models/MasteryProfile');
const GenerationJob = require('../src/models/GenerationJob');
const n8nService = require('../src/services/n8n.service');
const userServiceClient = require('../src/services/userService.client');
const conceptGraphService = require('../src/services/conceptGraph.service');
const ServiceError = require('../src/utils/ServiceError');
const {
  submitMasteryProfile,
  getMasteryProfile,
  getMasteryProfileById,
  getMasteryHistory,
} = require('../src/controllers/profile.controller');

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

const makeReq = (overrides = {}) => ({
  body: {
    student_id: 'STU_1',
    analysis_timestamp: new Date().toISOString(),
    mastery_profile: {
      overall_mastery_score: 50,
      knowledge_gaps: [{ topic: 'Variables', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' }],
      strengths: [],
    },
    recommendations: {},
    data_sources: {},
  },
  student: { id: 'STU_1' },
  ip: '127.0.0.1',
  params: {},
  query: {},
  ...overrides,
});

const stubDeps = (t, graph = new Map()) => {
  mock.method(MasteryProfile.prototype, 'save', async function () { return this; });
  mock.method(GenerationJob.prototype, 'save', async function () { return this; });
  mock.method(conceptGraphService, 'loadGraph', async () => graph);
  mock.method(conceptGraphService, 'computeCoverage', async () => ({
    totalNodes: 0,
    coveredNodes: 0,
    coveragePct: 0,
  }));
  mock.method(conceptGraphService.embedder, 'embed', async () => [0, 0, 0]);
  mock.method(conceptGraphService.ollamaClient, 'generate', async () => 'NO_MATCH');
  mock.method(n8nService, 'triggerMaterialGeneration', async () => ({}));
  mock.method(userServiceClient, 'updateStudentStatsAsync', async () => {});
  t.after(() => mock.restoreAll());
};

test('submitMasteryProfile returns 403 when student_id mismatch', async () => {
  const req = makeReq({ body: { ...makeReq().body, student_id: 'OTHER' } });
  const res = makeRes();
  await submitMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('submitMasteryProfile returns 202 with job info on success', async (t) => {
  const graph = new Map([
    ['java.fund.variables', {
      concept_id: 'java.fund.variables',
      name: 'Variables',
      prerequisites: [],
      bloom_level: 'remember',
    }],
  ]);
  stubDeps(t, graph);

  const req = makeReq();
  const res = makeRes();
  await submitMasteryProfile(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 202);
  assert.equal(res.body.success, true);
  assert.equal(res.body.data.student_id, 'STU_1');
  assert.ok(res.body.data.job_id);
  assert.ok(res.body.data.check_status_at);
});

test('submitMasteryProfile returns 503 with N8N_OFFLINE code when n8n is offline', async (t) => {
  stubDeps(t, new Map());
  mock.method(n8nService, 'triggerMaterialGeneration', async () => {
    throw new ServiceError('N8N_OFFLINE', 503, 'offline', 'start n8n');
  });

  const req = makeReq();
  const res = makeRes();
  await submitMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 503);
  assert.equal(res.body.code, 'N8N_OFFLINE');
});

test('submitMasteryProfile returns 202 with timeout message on N8N_TIMEOUT', async (t) => {
  stubDeps(t, new Map());
  mock.method(n8nService, 'triggerMaterialGeneration', async () => {
    throw new ServiceError('N8N_TIMEOUT', 504, 'timed out', 'wait');
  });

  const req = makeReq();
  const res = makeRes();
  await submitMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 202);
  const detailMsg = res.body.message;
  assert.match(detailMsg, /continues in background/);
});

test('submitMasteryProfile continues (fail-open) when the concept graph gate throws', async (t) => {
  stubDeps(t, new Map());
  // Force loadGraph to throw
  mock.method(conceptGraphService, 'loadGraph', async () => {
    throw new Error('db boom');
  });

  let capturedJob = null;
  mock.method(GenerationJob.prototype, 'save', async function () {
    if (!capturedJob) capturedJob = this;
    return this;
  });

  const req = makeReq();
  const res = makeRes();
  await submitMasteryProfile(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 202);
  assert.ok(capturedJob);
  assert.equal(capturedJob.gaps_total, 1, 'must fall back to raw gap count');
});

test('getMasteryProfile returns 403 on student mismatch', async () => {
  const req = makeReq({ params: { studentId: 'OTHER' } });
  const res = makeRes();
  await getMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getMasteryProfile returns 404 when no profile exists', async (t) => {
  mock.method(MasteryProfile, 'findOne', () => ({ sort: async () => null }));
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
  assert.equal(res.body.code, 'NOT_FOUND');
});

test('getMasteryProfile returns the profile on success', async (t) => {
  const profile = { student_id: 'STU_1', overall_mastery_score: 50 };
  mock.method(MasteryProfile, 'findOne', () => ({ sort: async () => profile }));
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getMasteryProfile(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.overall_mastery_score, 50);
});

test('getMasteryProfileById returns 404 for an invalid ObjectId', async (t) => {
  const req = makeReq({ params: { profileId: 'not-an-id' } });
  const res = makeRes();
  await getMasteryProfileById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});

test('getMasteryProfileById returns 403 when profile belongs to another student', async (t) => {
  const profile = { student_id: 'OTHER', _id: '507f1f77bcf86cd799439011' };
  mock.method(MasteryProfile, 'findById', async () => profile);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { profileId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getMasteryProfileById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getMasteryHistory returns paginated history', async (t) => {
  const items = [
    { _id: 'x', overall_mastery_score: 50, knowledge_gaps: [{}, {}], submitted_at: new Date() },
  ];
  mock.method(MasteryProfile, 'find', () => ({
    sort: () => ({ skip: () => ({ limit: () => ({ select: async () => items }) }) }),
  }));
  mock.method(MasteryProfile, 'countDocuments', async () => 1);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_1' }, query: { limit: '10', page: '1' } });
  const res = makeRes();
  await getMasteryHistory(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.items.length, 1);
  assert.equal(res.body.data.items[0].gaps_count, 2);
  assert.equal(res.body.data.meta.total, 1);
});
