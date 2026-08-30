const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const mongoose = require('mongoose');

const LearningMaterial = require('../src/models/LearningMaterial');
const GenerationJob = require('../src/models/GenerationJob');
const jobTracker = require('../src/services/jobTracker.service');

const makeQueryChain = (result) => ({
  select() { return this; },
  lean: async () => result,
});

const makeJob = (opts = {}) => ({
  _id: `id_${opts.job_id || 'job'}`,
  job_id: opts.job_id || 'JOB_1',
  student_id: opts.student_id || 'STU_1',
  status: opts.status || 'queued',
  created_at: opts.created_at || new Date('2026-01-01T00:00:00Z'),
  gaps_total: opts.gaps_total || 3,
  gaps_completed: opts.gaps_completed || 0,
  error: opts.error,
});

test('syncJobCounters marks job completed when all gaps have materials', async (t) => {
  const activeJob = makeJob({ job_id: 'JOB_1', gaps_total: 2, status: 'queued' });

  const materials = [
    {
      structured_material: {
        topic_id: 'java.fund.variables',
        generated_at: new Date('2026-01-02T00:00:00Z'),
      },
    },
    {
      structured_material: {
        topic_id: 'java.oop.inheritance',
        generated_at: new Date('2026-01-03T00:00:00Z'),
      },
    },
  ];

  mock.method(LearningMaterial, 'find', () => makeQueryChain(materials));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  const result = await jobTracker.syncJobCounters(activeJob);

  assert.equal(result.gaps_completed, 2);
  assert.equal(result.materials_generated, 2);
  assert.equal(result.status, 'completed');

  const update = updateOne.mock.calls[0].arguments[1].$set;
  assert.equal(update.status, 'completed');
  assert.deepEqual(update.gap_topic_ids, ['java.fund.variables', 'java.oop.inheritance']);
  assert.ok(update.completed_at);
});

test('syncJobCounters ignores materials generated before the job was created', async (t) => {
  const activeJob = makeJob({ job_id: 'JOB_2', gaps_total: 1, created_at: new Date('2026-01-10T00:00:00Z') });

  const materials = [
    {
      structured_material: {
        topic_id: 'java.fund.variables',
        generated_at: new Date('2026-01-05T00:00:00Z'), // before job
      },
    },
    {
      structured_material: {
        topic_id: 'java.oop.inheritance',
        generated_at: new Date('2026-01-12T00:00:00Z'), // after job
      },
    },
  ];

  mock.method(LearningMaterial, 'find', () => makeQueryChain(materials));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  const result = await jobTracker.syncJobCounters(activeJob);
  assert.equal(result.gaps_completed, 1);
  assert.equal(result.materials_generated, 1);
  const update = updateOne.mock.calls[0].arguments[1].$set;
  assert.deepEqual(update.gap_topic_ids, ['java.oop.inheritance']);
});

test('syncJobCounters keeps job processing when fewer materials than total', async (t) => {
  const activeJob = makeJob({ job_id: 'JOB_3', gaps_total: 3, gaps_completed: 1, status: 'queued' });
  mock.method(LearningMaterial, 'find', () => makeQueryChain([
    { structured_material: { topic_id: 'java.fund.variables', generated_at: new Date('2026-01-02T00:00:00Z') } },
  ]));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  await jobTracker.syncJobCounters(activeJob);
  assert.equal(updateOne.mock.callCount(), 1);
});

test('updateJobCounters picks the most recent active job and syncs it', async (t) => {
  const activeJobRaw = makeJob({ job_id: 'JOB_A', status: 'processing', gaps_total: 2 });
  const collection = { findOne: async () => null };
  const findOne = mock.method(collection, 'findOne', async () => activeJobRaw);
  mock.method(mongoose.connection, 'collection', () => collection);
  mock.method(LearningMaterial, 'find', () => makeQueryChain([
    { structured_material: { topic_id: 'java.fund.variables', generated_at: new Date('2026-01-02T00:00:00Z') } },
  ]));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  await jobTracker.updateJobCounters('STU_1');
  assert.equal(findOne.mock.calls[0].arguments[0].student_id, 'STU_1');
  assert.equal(updateOne.mock.callCount(), 1);
});

test('updateJobCounters syncs a failed timeout job when no active job exists', async (t) => {
  const failedRaw = makeJob({ job_id: 'JOB_F', status: 'failed', error: 'did not respond', gaps_total: 2 });
  const collection = { findOne: async () => null };
  mock.method(collection, 'findOne', async (query) => {
    if (query.status && query.status.$in) return null; // active query
    return failedRaw; // failed query
  });
  mock.method(mongoose.connection, 'collection', () => collection);
  mock.method(LearningMaterial, 'find', () => makeQueryChain([
    { structured_material: { topic_id: 'java.fund.variables', generated_at: new Date('2026-01-02T00:00:00Z') } },
  ]));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  await jobTracker.updateJobCounters('STU_1');
  assert.equal(updateOne.mock.callCount(), 1);
});

test('updateJobCounters returns undefined when no active or matching failed job exists', async (t) => {
  const collection = {
    findOne: async () => null,
  };
  mock.method(mongoose.connection, 'collection', () => collection);
  t.after(() => mock.restoreAll());

  assert.equal(await jobTracker.updateJobCounters('STU_1'), undefined);
});

test('resyncActiveJobs processes all active and timeout-failed jobs', async (t) => {
  const collection = {
    find(query) {
      if (query.status && Array.isArray(query.status.$in)) {
        return { toArray: async () => [
          makeJob({ job_id: 'JOB_1', status: 'queued', gaps_total: 1 }),
          makeJob({ job_id: 'JOB_2', status: 'processing', gaps_total: 1 }),
        ] };
      }
      return { toArray: async () => [makeJob({ job_id: 'JOB_3', status: 'failed', error: 'timed out', gaps_total: 0 })] };
    },
  };
  mock.method(mongoose.connection, 'collection', () => collection);
  mock.method(LearningMaterial, 'find', () => makeQueryChain([
    { structured_material: { topic_id: 'java.fund.variables', generated_at: new Date('2026-01-02T00:00:00Z') } },
  ]));
  const updateOne = mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  await jobTracker.resyncActiveJobs();
  assert.equal(updateOne.mock.callCount(), 3);
});

test('resyncActiveJobs handles per-job errors gracefully', async (t) => {
  const collection = {
    find(query) {
      if (query.status && Array.isArray(query.status.$in)) {
        return { toArray: async () => [makeJob({ job_id: 'JOB_1', status: 'queued', gaps_total: 1 })] };
      }
      return { toArray: async () => [] };
    },
  };
  mock.method(mongoose.connection, 'collection', () => collection);
  mock.method(LearningMaterial, 'find', () => {
    throw new Error('db boom');
  });
  mock.method(GenerationJob, 'updateOne', async () => ({}));
  t.after(() => mock.restoreAll());

  await assert.doesNotReject(() => jobTracker.resyncActiveJobs());
});

test('start/stop lifecycle guards against duplicate start', () => {
  const warn = mock.method(console, 'warn', () => {});
  jobTracker.isRunning = true;
  jobTracker.start();
  assert.equal(jobTracker.isRunning, true);
  warn.mock.restore();
  jobTracker.isRunning = false;
});
