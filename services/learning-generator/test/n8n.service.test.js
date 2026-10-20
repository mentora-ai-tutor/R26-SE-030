const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const axios = require('axios');

const n8nService = require('../src/services/n8n.service');
const ServiceError = require('../src/utils/ServiceError');

const profile = {
  student_id: 'STU_1',
  analysis_timestamp: '2026-01-01T00:00:00.000Z',
  mastery_profile: {
    overall_mastery_score: 67,
    knowledge_gaps: [
      { topic: 'Method Overriding', topic_id: 'g1' },
    ],
    strengths: [],
  },
  recommendations: {},
  data_sources: {},
};

const makeAxiosError = (overrides = {}) => {
  const err = new Error(overrides.message || 'Request failed');
  Object.assign(err, overrides);
  return err;
};

test('triggerMaterialGeneration posts payload and maps success response', async (t) => {
  mock.method(axios, 'post', async () => ({
    status: 200,
    data: {
      status: 'success',
      material_id: 'MAT_1',
      student_id: 'STU_1',
      topic: 'Method Overriding',
      agentic_summary: 'summary',
      generated_at: '2026-01-01T00:00:00Z',
      needs_review: false,
      message: 'ok',
    },
  }));
  t.after(() => mock.restoreAll());

  const result = await n8nService.triggerMaterialGeneration(profile);
  assert.equal(result.success, true);
  assert.equal(result.material_id, 'MAT_1');
  assert.equal(result.student_id, 'STU_1');
  assert.equal(result.topic, 'Method Overriding');
  assert.equal(result.agentic_summary, 'summary');
  assert.equal(result.needs_review, false);
  assert.equal(result.message, 'ok');

  const post = axios.post.mock.calls[0];
  assert.equal(post.arguments[0], n8nService.webhookLearnerProfile);
  assert.equal(post.arguments[1].mastery_profile.knowledge_gaps.length, 1);
  assert.equal(post.arguments[2].headers['X-Webhook-Secret'], n8nService.webhookSecret);
});

test('triggerMaterialGeneration maps status failure (not success)', async (t) => {
  mock.method(axios, 'post', async () => ({
    status: 200,
    data: { status: 'failed', material_id: 'MAT_2' },
  }));
  t.after(() => mock.restoreAll());

  const result = await n8nService.triggerMaterialGeneration(profile);
  assert.equal(result.success, false);
  assert.equal(result.material_id, 'MAT_2');
});

test('triggerMaterialGeneration throws N8N_OFFLINE on ECONNREFUSED', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED', message: 'connect ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => n8nService.triggerMaterialGeneration(profile),
    (err) => err instanceof ServiceError && err.code === 'N8N_OFFLINE' && err.statusCode === 503
  );
});

test('triggerMaterialGeneration throws N8N_TIMEOUT on timeout', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ code: 'ECONNABORTED', message: 'timeout of 600000ms exceeded' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => n8nService.triggerMaterialGeneration(profile),
    (err) => err instanceof ServiceError && err.code === 'N8N_TIMEOUT' && err.statusCode === 504
  );
});

test('triggerMaterialGeneration throws N8N_GENERATION_FAILED on 500 response', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({
      response: { status: 500, data: { error: 'boom' } },
    });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => n8nService.triggerMaterialGeneration(profile),
    (err) => err instanceof ServiceError && err.code === 'N8N_GENERATION_FAILED' && err.statusCode === 500
  );
});

test('triggerMaterialGeneration throws N8N_ERROR with response status otherwise', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({
      response: { status: 422, data: { error: 'bad' } },
    });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => n8nService.triggerMaterialGeneration(profile),
    (err) => err instanceof ServiceError && err.code === 'N8N_ERROR' && err.statusCode === 422
  );
});

test('triggerMaterialGeneration throws N8N_ERROR on unexpected error', async (t) => {
  mock.method(axios, 'post', async () => {
    throw makeAxiosError({ message: 'something unexpected' });
  });
  t.after(() => mock.restoreAll());

  await assert.rejects(
    () => n8nService.triggerMaterialGeneration(profile),
    (err) => err instanceof ServiceError && err.code === 'N8N_ERROR' && err.statusCode === 500
  );
});

test('getMaterialsByStudent returns data on success', async (t) => {
  mock.method(axios, 'get', async () => ({ data: [{ material_id: 'M1' }] }));
  t.after(() => mock.restoreAll());

  const data = await n8nService.getMaterialsByStudent('STU_1');
  assert.deepEqual(data, [{ material_id: 'M1' }]);
  assert.equal(axios.get.mock.calls[0].arguments[0], n8nService.webhookGetMaterials.replace(':studentId', 'STU_1'));
});

test('getMaterialsByStudent returns [] when n8n is offline', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());

  assert.deepEqual(await n8nService.getMaterialsByStudent('STU_1'), []);
});

test('getMaterialsByStudent returns [] on response error', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ response: { status: 500 } });
  });
  t.after(() => mock.restoreAll());

  assert.deepEqual(await n8nService.getMaterialsByStudent('STU_1'), []);
});

test('checkHealth returns reachable true on 2xx', async (t) => {
  mock.method(axios, 'get', async () => ({ status: 200 }));
  t.after(() => mock.restoreAll());
  assert.deepEqual(await n8nService.checkHealth(), { reachable: true });
});

test('checkHealth returns reachable false on error', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ code: 'ECONNREFUSED' });
  });
  t.after(() => mock.restoreAll());
  assert.deepEqual(await n8nService.checkHealth(), { reachable: false });
});

test('getWorkflowStatus returns workflows on success', async (t) => {
  mock.method(axios, 'get', async () => ({ data: { data: [{ id: 'wf1' }] } }));
  t.after(() => mock.restoreAll());
  const result = await n8nService.getWorkflowStatus();
  assert.equal(result.success, true);
  assert.deepEqual(result.workflows, [{ id: 'wf1' }]);
});

test('getWorkflowStatus fails open on error', async (t) => {
  mock.method(axios, 'get', async () => {
    throw makeAxiosError({ message: 'down' });
  });
  t.after(() => mock.restoreAll());
  const result = await n8nService.getWorkflowStatus();
  assert.equal(result.success, false);
  assert.equal(result.error, 'down');
});
