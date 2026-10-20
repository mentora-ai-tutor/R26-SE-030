'use strict';

const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

require('../support/install');

const materialService = require('../../../services/learning-generator/src/services/material.service');
const LearningMaterial = require('../../../services/learning-generator/src/models/LearningMaterial');

test('buildMaterialQuery scopes to owner and excludes hard-deleted materials', () => {
  const filter = materialService.buildMaterialQuery('STU_42', {});
  assert.equal(filter['structured_material.student_id'], 'STU_42');
  assert.deepEqual(filter['structured_material.quality_flags.deleted'], { $ne: true });
});

test('buildMaterialQuery adds topic, gap_type and status when provided', () => {
  const filter = materialService.buildMaterialQuery('STU_1', {
    topic: 'Variables',
    gap_type: 'PARTIAL_GAP',
    status: 'ready',
  });
  assert.equal(filter['structured_material.topic'], 'Variables');
  assert.equal(filter['structured_material.gap_type'], 'PARTIAL_GAP');
  assert.equal(filter['structured_material.status'], 'ready');
});

test('buildMaterialQuery omits filters that are empty strings', () => {
  const filter = materialService.buildMaterialQuery('STU_1', { topic: '', gap_type: '', status: '' });
  assert.equal(filter['structured_material.topic'], undefined);
  assert.equal(filter['structured_material.gap_type'], undefined);
  assert.equal(filter['structured_material.status'], undefined);
});

test('getMaterialStats returns empty-state shape when no materials exist', async (t) => {
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

const makeMaterial = (opts = {}) => ({
  structured_material: {
    student_id: 'STU_A',
    topic: opts.topic || 'Variables',
    topic_id: 'java.fund.variables',
    gap_type: opts.gap_type || 'FUNDAMENTAL_GAP',
    generated_at: opts.generated_at || new Date('2026-01-01T00:00:00Z'),
    quality_flags: opts.quality_flags || {},
    agentic_metadata: opts.agentic_metadata || {},
  },
});

test('getMaterialStats aggregates gap counts, averages, flags, retries and latest date', async (t) => {
  const materials = [
    makeMaterial({
      gap_type: 'FUNDAMENTAL_GAP',
      quality_flags: { needs_review: true, agent_patched_llm: true },
      agentic_metadata: {
        quality_review_agent: { quality_score: 90, retry_count: 2 },
        content_validation_agent: { validation_score: 95 },
      },
      generated_at: new Date('2026-01-02T00:00:00Z'),
      topic: 'Arrays',
    }),
    makeMaterial({
      gap_type: 'PARTIAL_GAP',
      agentic_metadata: {
        quality_review_agent: { quality_score: 70 },
        content_validation_agent: { validation_score: null },
      },
      generated_at: new Date('2026-01-03T00:00:00Z'),
      topic: 'Methods',
    }),
    makeMaterial({
      gap_type: 'SURFACE_GAP',
      agentic_metadata: {
        quality_review_agent: { quality_score: null },
        content_validation_agent: { validation_score: 80 },
      },
      generated_at: new Date('2026-01-01T00:00:00Z'),
      topic: 'Methods',
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
  assert.equal(stats.avg_quality_score, 80); // (90 + 70) / 2
  assert.equal(stats.avg_validation_score, 87.5); // (95 + 80) / 2
  assert.equal(stats.needs_review_count, 1);
  assert.equal(stats.agent_patched_count, 1);
  assert.equal(stats.total_agent_retries, 2);
  assert.equal(stats.latest_generated_at, new Date('2026-01-03T00:00:00Z').toISOString());

  const methods = stats.by_topic.find((s) => s.topic === 'Methods');
  assert.equal(methods.count, 2);
  assert.equal(methods.avg_score, 70);
});
