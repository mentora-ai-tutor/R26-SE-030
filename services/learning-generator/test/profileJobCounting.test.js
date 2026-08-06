const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const MasteryProfile = require('../src/models/MasteryProfile');
const GenerationJob = require('../src/models/GenerationJob');
const n8nService = require('../src/services/n8n.service');
const userServiceClient = require('../src/services/userService.client');
const conceptGraphService = require('../src/services/conceptGraph.service');
const { submitMasteryProfile } = require('../src/controllers/profile.controller');

const makeNode = (concept_id, name, opts = {}) => ({
  concept_id,
  name,
  aliases: opts.aliases || [],
  description_embedding: opts.embedding || [],
  prerequisites: opts.prerequisites || [],
  description: opts.description || `Description for ${name}`,
  bloom_level: opts.bloom_level || 'apply',
});

const fixtureGraph = new Map([
  ['java.control.conditionals', makeNode('java.control.conditionals', 'Conditionals', {
    bloom_level: 'apply',
  })],
  ['java.oop.inheritance', makeNode('java.oop.inheritance', 'Inheritance', {
    bloom_level: 'understand',
  })],
  ['java.oop.polymorphism.method_overriding', makeNode('java.oop.polymorphism.method_overriding', 'Method Overriding', {
    prerequisites: ['java.oop.inheritance'],
    bloom_level: 'apply',
  })],
]);

const makeReqRes = () => {
  const req = {
    body: {
      student_id: 'STU_JOB_1',
      analysis_timestamp: new Date().toISOString(),
      mastery_profile: {
        overall_mastery_score: 50,
        knowledge_gaps: [
          { topic: 'Method Overriding', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' },
          { topic: 'Conditionals', topic_id: 'g2', gap_type: 'FUNDAMENTAL_GAP' },
        ],
        strengths: [],
      },
      recommendations: {},
      data_sources: {},
    },
    student: { id: 'STU_JOB_1' },
    ip: '127.0.0.1',
  };
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
  return { req, res };
};

const stubRuntimeDeps = (t, graph) => {
  mock.method(MasteryProfile.prototype, 'save', async function () { return this; });
  mock.method(GenerationJob.prototype, 'save', async function () { return this; });
  mock.method(conceptGraphService, 'loadGraph', async () => graph);
  mock.method(conceptGraphService, 'computeCoverage', async () => ({
    totalNodes: 3,
    coveredNodes: 1,
    coveragePct: 33.33,
  }));
  mock.method(conceptGraphService.embedder, 'embed', async () => [0, 0, 0]);
  mock.method(conceptGraphService.ollamaClient, 'generate', async () => 'NO_MATCH');
  mock.method(n8nService, 'triggerMaterialGeneration', async () => ({}));
  mock.method(userServiceClient, 'updateStudentStatsAsync', async () => {});
  t.after(() => mock.restoreAll());
};

test('GenerationJob gaps_total/gaps_queued use the augmented list (explicit + implicit), not the raw submitted count', async (t) => {
  stubRuntimeDeps(t, fixtureGraph);

  let createdJob = null;
  mock.method(GenerationJob.prototype, 'save', async function () {
    if (!createdJob) createdJob = this;
    return this;
  });

  let lastProfile = null;
  mock.method(MasteryProfile.prototype, 'save', async function () {
    lastProfile = this;
    return this;
  });

  let sentPayload = null;
  mock.method(n8nService, 'triggerMaterialGeneration', async (payload) => {
    sentPayload = payload;
    return {};
  });

  const { req, res } = makeReqRes();

  await submitMasteryProfile(req, res, (err) => { throw err; });

  // Raw submitted count is 2; Method Overriding's UNKNOWN prerequisite
  // (Inheritance) is injected, so the augmented list is 3.
  assert.equal(res.statusCode, 202);
  assert.ok(createdJob, 'expected a GenerationJob to be created');
  assert.equal(createdJob.gaps_total, 3, 'gaps_total must be explicit resolved gaps + injected implicit gaps');
  assert.equal(createdJob.gaps_queued, 3);
  assert.deepEqual(createdJob.gap_topic_ids, ['g1', 'g2', 'java.oop.inheritance']);

  assert.ok(sentPayload, 'expected n8n to receive a payload');
  assert.equal(sentPayload.mastery_profile.knowledge_gaps.length, 3);

  const implicitGap = sentPayload.mastery_profile.knowledge_gaps.find(
    (g) => g.resolution_method === 'implicit'
  );
  assert.ok(implicitGap, 'payload must include an injected implicit prerequisite gap');
  assert.equal(implicitGap.topic, 'Inheritance');
  assert.equal(implicitGap.resolved_concept_id, 'java.oop.inheritance');
  assert.equal(implicitGap.concept_context.concept_id, 'java.oop.inheritance');
  assert.match(implicitGap.reason, /^prerequisite_of:/);

  assert.ok(lastProfile.augmented_profile, 'augmented_profile must be persisted');
  assert.equal(lastProfile.augmented_profile.implicit_gaps.length, 1);
  assert.equal(lastProfile.augmented_profile.unverified_prerequisites.length, 1);
});

test('GenerationJob counters fail open to the raw count when the graph is empty', async (t) => {
  stubRuntimeDeps(t, new Map());

  let createdJob = null;
  mock.method(GenerationJob.prototype, 'save', async function () {
    if (!createdJob) createdJob = this;
    return this;
  });

  const { req, res } = makeReqRes();

  await submitMasteryProfile(req, res, (err) => { throw err; });

  assert.equal(res.statusCode, 202);
  assert.equal(createdJob.gaps_total, 2);
  assert.equal(createdJob.gaps_queued, 2);
});

test('explicitly resolved gaps in the n8n payload carry a non-null concept_context (same shape as implicit)', async (t) => {
  stubRuntimeDeps(t, fixtureGraph);

  let sentPayload = null;
  mock.method(n8nService, 'triggerMaterialGeneration', async (payload) => {
    sentPayload = payload;
    return {};
  });

  const { req, res } = makeReqRes();

  await submitMasteryProfile(req, res, (err) => { throw err; });

  const gaps = sentPayload.mastery_profile.knowledge_gaps;
  const explicit = gaps.filter((g) => g.resolution_method !== 'implicit');
  assert.equal(explicit.length, 2, 'both submitted gaps resolve via Tier 1 exact');

  for (const gap of explicit) {
    assert.equal(gap.resolution_method, 'exact');
    assert.ok(gap.concept_context, `explicit gap ${gap.topic_id} must carry concept_context`);
    assert.equal(gap.concept_context.concept_id, gap.resolved_concept_id);
    assert.equal(gap.concept_context.id, gap.resolved_concept_id);
    assert.ok(gap.concept_context.name, 'concept_context must include the node name');
    assert.ok(gap.concept_context.description, 'concept_context must include the node description');
    assert.ok(gap.concept_context.bloom_level, 'concept_context must include the bloom level');
    assert.ok(Array.isArray(gap.concept_context.prerequisite_names));
    assert.ok(Array.isArray(gap.concept_context.related_topic_names));
  }

  const methodOverriding = explicit.find((g) => g.topic_id === 'g1');
  assert.ok(
    methodOverriding.concept_context.prerequisite_names.includes('Inheritance'),
    'prerequisite concept_ids must be mapped to node names'
  );

  const implicit = gaps.find((g) => g.resolution_method === 'implicit');
  assert.ok(implicit, 'expected an injected implicit prerequisite gap');
  assert.deepEqual(
    Object.keys(implicit.concept_context).sort(),
    Object.keys(methodOverriding.concept_context).sort(),
    'explicit and implicit gaps must build concept_context identically'
  );
});

test('augmentGaps computes the augmented list in one place (single source of truth)', async () => {
  mock.method(conceptGraphService.embedder, 'embed', async () => [0, 0, 0]);
  mock.method(conceptGraphService.ollamaClient, 'generate', async () => 'NO_MATCH');

  const knowledgeGaps = [
    { topic: 'Method Overriding', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' },
    { topic: 'Conditionals', topic_id: 'g2', gap_type: 'FUNDAMENTAL_GAP' },
  ];

  const result = await conceptGraphService.augmentGaps(
    knowledgeGaps,
    [],
    fixtureGraph,
    conceptGraphService.embedder,
    conceptGraphService.ollamaClient
  );

  assert.equal(result.resolvedGaps.length, 2);
  assert.equal(result.injectedGaps.length, 1);
  assert.equal(result.effectiveGaps.length, 3);
  assert.equal(result.injectedGaps[0].resolution_method, 'implicit');
  assert.equal(result.injectedGaps[0].concept_context.concept_id, 'java.oop.inheritance');
  assert.match(result.injectedGaps[0].reason, /prerequisite_of:java\.oop\.polymorphism\.method_overriding/);

  mock.restoreAll();
});
