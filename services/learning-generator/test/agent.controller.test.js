const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const AgentLog = require('../src/models/AgentLog');
const GenerationJob = require('../src/models/GenerationJob');
const LearningMaterial = require('../src/models/LearningMaterial');
const MasteryProfile = require('../src/models/MasteryProfile');
const materialService = require('../src/services/material.service');
const n8nService = require('../src/services/n8n.service');
const ServiceError = require('../src/utils/ServiceError');
const {
  getAgentLogs,
  getJobStatus,
  getJobsByStudent,
  getGlobalStats,
  retryMaterialGeneration,
  completeJob,
  updateJobStatus,
} = require('../src/controllers/agent.controller');

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

const baseReq = (overrides = {}) => ({
  student: { id: 'STU_1' },
  params: {},
  query: {},
  body: {},
  ...overrides,
});

const makeJobDoc = (opts = {}) => ({
  job_id: opts.job_id || 'JOB_1',
  student_id: opts.student_id || 'STU_1',
  status: opts.status || 'queued',
  gaps_total: opts.gaps_total || 2,
  gaps_completed: opts.gaps_completed || 0,
  profile_id: opts.profile_id,
  save: async function () { return this; },
  ...opts,
});

test('getAgentLogs returns 403 on student mismatch', async () => {
  const req = baseReq({ params: { studentId: 'OTHER' } });
  const res = makeRes();
  await getAgentLogs(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getAgentLogs returns paginated logs', async (t) => {
  const logs = [{ log_id: 'L1' }];
  mock.method(AgentLog, 'find', () => ({ sort: () => ({ skip: () => ({ limit: async () => logs }) }) }));
  mock.method(AgentLog, 'countDocuments', async () => 1);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getAgentLogs(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.items.length, 1);
});

test('getJobStatus returns 404 when job not found', async (t) => {
  mock.method(GenerationJob, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'NOPE' } });
  const res = makeRes();
  await getJobStatus(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});

test('getJobStatus returns 403 when job belongs to another student', async (t) => {
  mock.method(GenerationJob, 'findOne', async () => makeJobDoc({ student_id: 'OTHER' }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'JOB_1' } });
  const res = makeRes();
  await getJobStatus(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getJobStatus returns the job for its owner', async (t) => {
  mock.method(GenerationJob, 'findOne', async () => makeJobDoc({ job_id: 'JOB_1' }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'JOB_1' } });
  const res = makeRes();
  await getJobStatus(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.job_id, 'JOB_1');
});

test('getJobsByStudent returns the student jobs', async (t) => {
  const jobs = [makeJobDoc()];
  mock.method(GenerationJob, 'find', () => ({ sort: () => ({ limit: async () => jobs }) }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getJobsByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.length, 1);
});

test('getGlobalStats returns global agent stats', async (t) => {
  mock.method(materialService, 'getGlobalAgentStats', async () => ({ total_generations: 10 }));
  t.after(() => mock.restoreAll());

  const res = makeRes();
  await getGlobalStats(baseReq(), res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.total_generations, 10);
});

test('updateJobStatus returns 400 for an invalid status', async (t) => {
  const req = baseReq({ params: { jobId: 'JOB_1' }, body: { status: 'nope' } });
  const res = makeRes();
  await updateJobStatus(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 400);
  assert.equal(res.body.code, 'BAD_REQUEST');
});

test('updateJobStatus updates a valid status', async (t) => {
  const job = makeJobDoc({ status: 'queued' });
  const save = mock.method(job, 'save', async function () { return this; });
  mock.method(GenerationJob, 'findOne', async () => job);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'JOB_1' }, body: { status: 'completed' } });
  const res = makeRes();
  await updateJobStatus(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(job.status, 'completed');
  assert.equal(save.mock.callCount(), 1);
});

test('completeJob marks the job completed when all materials exist', async (t) => {
  const job = makeJobDoc({ status: 'queued', gaps_total: 2, gap_topic_ids: ['a', 'b'] });
  const save = mock.method(job, 'save', async function () { return this; });
  mock.method(GenerationJob, 'findOne', async () => job);
  mock.method(MasteryProfile, 'findById', async () => null);
  mock.method(LearningMaterial, 'find', () => ({ select: async () => [
    { structured_material: { topic_id: 'a' } },
    { structured_material: { topic_id: 'b' } },
  ] }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'JOB_1' } });
  const res = makeRes();
  await completeJob(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(job.status, 'completed');
  assert.equal(job.gaps_completed, 2);
  assert.equal(save.mock.callCount(), 1);
});

test('completeJob keeps the job processing when fewer materials exist', async (t) => {
  const job = makeJobDoc({ status: 'queued', gaps_total: 5 });
  mock.method(GenerationJob, 'findOne', async () => job);
  mock.method(MasteryProfile, 'findById', async () => null);
  mock.method(LearningMaterial, 'find', () => ({ select: async () => [
    { structured_material: { topic_id: 'a' } },
  ] }));
  mock.method(job, 'save', async function () { return this; });
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { jobId: 'JOB_1' } });
  const res = makeRes();
  await completeJob(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(job.status, 'processing');
  assert.equal(job.gaps_completed, 1);
});

test('retryMaterialGeneration returns 404 when material missing', async (t) => {
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_X' } });
  const res = makeRes();
  await retryMaterialGeneration(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});

test('retryMaterialGeneration returns 202 and queues a retry', async (t) => {
  const material = {
    structured_material: {
      material_id: 'MAT_1',
      student_id: 'STU_1',
      topic: 'Variables',
      topic_id: 'java.fund.variables',
      gap_type: 'FUNDAMENTAL_GAP',
    },
  };
  const latestProfile = {
    _id: '507f1f77bcf86cd799439011',
    analysis_timestamp: new Date(),
    overall_mastery_score: 50,
    strengths: [],
    recommendations: {},
    data_sources: {},
  };

  mock.method(LearningMaterial, 'findOne', async () => material);
  mock.method(MasteryProfile, 'findOne', () => ({ sort: async () => latestProfile }));
  const jobSave = mock.method(GenerationJob.prototype, 'save', async function () { return this; });
  const trigger = mock.method(n8nService, 'triggerMaterialGeneration', async () => ({}));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_1' } });
  const res = makeRes();
  await retryMaterialGeneration(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 202);
  assert.ok(res.body.data.job_id);
  assert.equal(jobSave.mock.callCount(), 1);
  assert.equal(trigger.mock.callCount(), 1);
});

test('retryMaterialGeneration returns 503 when n8n offline', async (t) => {
  const material = {
    structured_material: {
      material_id: 'MAT_1',
      student_id: 'STU_1',
      topic: 'Variables',
      topic_id: 'java.fund.variables',
      gap_type: 'FUNDAMENTAL_GAP',
    },
  };
  const latestProfile = { _id: 'x', analysis_timestamp: new Date(), overall_mastery_score: 50, strengths: [] };

  const savedJobs = [];
  mock.method(LearningMaterial, 'findOne', async () => material);
  mock.method(MasteryProfile, 'findOne', () => ({ sort: async () => latestProfile }));
  mock.method(GenerationJob.prototype, 'save', async function () { savedJobs.push(this); return this; });
  mock.method(n8nService, 'triggerMaterialGeneration', async () => {
    throw new ServiceError('N8N_OFFLINE', 503, 'offline', 'start');
  });
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_1' } });
  const res = makeRes();
  await retryMaterialGeneration(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 503);
  assert.equal(res.body.code, 'N8N_OFFLINE');
  assert.equal(savedJobs[savedJobs.length - 1].status, 'failed');
});
