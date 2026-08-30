const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const LearningMaterial = require('../src/models/LearningMaterial');
const AgentLog = require('../src/models/AgentLog');
const materialService = require('../src/services/material.service');

test('buildMaterialQuery always scopes to student and excludes deleted materials', () => {
  const filter = materialService.buildMaterialQuery('STU_1', {});
  assert.equal(filter['structured_material.student_id'], 'STU_1');
  assert.deepEqual(filter['structured_material.quality_flags'], { $ne: 'deleted' });
});

test('buildMaterialQuery adds topic filter when provided', () => {
  const filter = materialService.buildMaterialQuery('STU_1', { topic: 'Variables' });
  assert.equal(filter['structured_material.topic'], 'Variables');
  assert.equal(filter['structured_material.gap_type'], undefined);
  assert.equal(filter['structured_material.status'], undefined);
});

test('buildMaterialQuery adds gap_type filter when provided', () => {
  const filter = materialService.buildMaterialQuery('STU_1', { gap_type: 'FUNDAMENTAL_GAP' });
  assert.equal(filter['structured_material.gap_type'], 'FUNDAMENTAL_GAP');
});

test('buildMaterialQuery adds status filter when provided', () => {
  const filter = materialService.buildMaterialQuery('STU_1', { status: 'ready' });
  assert.equal(filter['structured_material.status'], 'ready');
});

test('getMaterialStats returns the empty-state shape when there are no materials', async (t) => {
  mock.method(LearningMaterial, 'find', async () => []);
  t.after(() => mock.restoreAll());

  const stats = await materialService.getMaterialStats('STU_EMPTY');
  assert.deepEqual(stats, {
    total_materials: 0,
    by_gap_type: { FUNDAMENTAL_GAP: 0, PARTIAL_GAP: 0, SURFACE_GAP: 0 },
    avg_quality_score: null,
    avg_validation_score: null,
    needs_review_count: 0,
    agent_patched_count: 0,
    total_agent_retries: 0,
    by_topic: [],
    latest_generated_at: null,
  });
});

const makeMaterial = (opts = {}) => {
  const sm = {
    student_id: 'STU_A',
    topic: opts.topic || 'Variables',
    topic_id: 'java.fund.variables',
    gap_type: opts.gap_type || 'FUNDAMENTAL_GAP',
    generated_at: opts.generated_at || new Date('2026-01-01T00:00:00Z'),
    quality_flags: opts.quality_flags || {},
    agentic_metadata: opts.agentic_metadata || {},
  };
  return {
    structured_material: sm,
    toObject() {
      return { _id: 'x', structured_material: sm, __v: 0 };
    },
  };
};

test('getMaterialStats computes gap-type counts, averages, reviews, retries and latest date', async (t) => {
  const materials = [
    makeMaterial({
      gap_type: 'FUNDAMENTAL_GAP',
      quality_flags: { needs_review: true, agent_patched_llm: true },
      agentic_metadata: {
        quality_review_agent: { quality_score: 80, retry_count: 2 },
        content_validation_agent: { validation_score: 90 },
      },
      generated_at: new Date('2026-01-02T00:00:00Z'),
    }),
    makeMaterial({
      gap_type: 'PARTIAL_GAP',
      agentic_metadata: {
        quality_review_agent: { quality_score: 60 },
        content_validation_agent: { validation_score: null },
      },
      generated_at: new Date('2026-01-03T00:00:00Z'),
      topic: 'Inheritance',
    }),
    makeMaterial({
      gap_type: 'SURFACE_GAP',
      agentic_metadata: {
        quality_review_agent: { quality_score: null },
        content_validation_agent: { validation_score: 70 },
      },
      generated_at: new Date('2026-01-01T00:00:00Z'),
      topic: 'Inheritance',
    }),
  ];

  mock.method(LearningMaterial, 'find', async () => materials);
  t.after(() => mock.restoreAll());

  const stats = await materialService.getMaterialStats('STU_A');

  assert.equal(stats.total_materials, 3);
  assert.deepEqual(stats.by_gap_type, {
    FUNDAMENTAL_GAP: 1,
    PARTIAL_GAP: 1,
    SURFACE_GAP: 1,
  });
  assert.equal(stats.avg_quality_score, 70); // (80 + 60) / 2
  assert.equal(stats.avg_validation_score, 80); // (90 + 70) / 2
  assert.equal(stats.needs_review_count, 1);
  assert.equal(stats.agent_patched_count, 1);
  assert.equal(stats.total_agent_retries, 2);
  assert.equal(stats.latest_generated_at, new Date('2026-01-03T00:00:00Z').toISOString());

  const byTopic = stats.by_topic.find((t) => t.topic === 'Inheritance');
  assert.equal(byTopic.count, 2);
  assert.equal(byTopic.avg_score, 60);
});

test('getGlobalAgentStats returns the empty-state shape when there are no logs', async (t) => {
  mock.method(AgentLog, 'find', () => ({ limit: async () => [] }));
  t.after(() => mock.restoreAll());

  const stats = await materialService.getGlobalAgentStats();
  assert.equal(stats.total_generations, 0);
  assert.equal(stats.avg_quality_score, null);
  assert.equal(stats.retry_rate_percent, null);
  assert.equal(stats.accept_rate_percent, null);
  assert.equal(stats.patch_rate_percent, null);
  assert.deepEqual(stats.model_usage, { llm: 'qwen2.5-coder:7b', slm: 'qwen2.5-coder:7b' });
});

test('getGlobalAgentStats computes rates across logs', async (t) => {
  const logs = [
    { agent_quality_score: 90, content_validation_score: 95, agent_retry_count: 1 },
    { agent_quality_score: 40, content_validation_score: 50, agent_retry_count: 2 },
    { agent_quality_score: 60, content_validation_score: 70, agent_retry_count: 0 },
  ];
  mock.method(AgentLog, 'find', () => ({ limit: async () => logs }));
  t.after(() => mock.restoreAll());

  const stats = await materialService.getGlobalAgentStats();
  assert.equal(stats.total_generations, 3);
  assert.equal(stats.avg_quality_score, (90 + 40 + 60) / 3);
  assert.equal(stats.avg_validation_score, (95 + 50 + 70) / 3);
  assert.equal(stats.total_retries, 3);
  assert.equal(stats.retry_rate_percent, 100); // 3 / 3
  assert.equal(stats.accept_rate_percent, 33.33333333333333); // 1/3 accepted (>=70)
  assert.equal(stats.patch_rate_percent, 33.33333333333333); // 1/3 patched (<50)
});

test('formatMaterialForResponse strips __v and returns null for missing material', () => {
  const material = makeMaterial();
  const resp = materialService.formatMaterialForResponse(material);
  assert.equal(resp.__v, undefined);
  assert.equal(resp.structured_material.topic, 'Variables');
  assert.equal(materialService.formatMaterialForResponse(null), null);
});

test('getDistinctTopics aggregates topics in descending latest_generated_at order', async (t) => {
  const aggregateResult = [
    { topic: 'Inheritance', topic_id: 'java.oop.inheritance', count: 2, latest_generated_at: new Date('2026-01-03T00:00:00Z'), avg_quality_score: 60 },
    { topic: 'Variables', topic_id: 'java.fund.variables', count: 1, latest_generated_at: new Date('2026-01-02T00:00:00Z'), avg_quality_score: 80 },
  ];
  const chain = {
    match() { return this; },
    group() { return this; },
    project() { return this; },
    sort() { return this; },
  };
  mock.method(LearningMaterial, 'aggregate', async () => aggregateResult);
  t.after(() => mock.restoreAll());

  const topics = await materialService.getDistinctTopics('STU_A');
  assert.equal(topics.length, 2);
  assert.equal(topics[0].topic, 'Inheritance');
  assert.equal(topics[0].avg_quality_score, 60);
  assert.equal(topics[1].topic, 'Variables');
});
