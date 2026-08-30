const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const axios = require('axios');

const ConceptGraphNode = require('../src/models/ConceptGraphNode');
const LearningMaterial = require('../src/models/LearningMaterial');
const {
  buildConceptContext,
  bloomToDifficulty,
  seedGraph,
  computeCoverage,
  augmentGaps,
  resolveLLM,
  stripFences,
  findOutermostObject,
  extractField,
  resolveGap,
  resolveEmbedding,
} = require('../src/services/conceptGraph.service');

const makeNode = (concept_id, name, opts = {}) => ({
  concept_id,
  name,
  aliases: opts.aliases || [],
  description_embedding: opts.embedding || [],
  prerequisites: opts.prerequisites || [],
  related_topics: opts.related_topics || [],
  description: opts.description || `Description for ${name}`,
  bloom_level: opts.bloom_level || 'apply',
  category: opts.category || 'OOP',
});

test('bloomToDifficulty maps remember/understand to beginner', () => {
  assert.equal(bloomToDifficulty('remember'), 'beginner');
  assert.equal(bloomToDifficulty('understand'), 'beginner');
});

test('bloomToDifficulty maps apply/analyze to intermediate', () => {
  assert.equal(bloomToDifficulty('apply'), 'intermediate');
  assert.equal(bloomToDifficulty('analyze'), 'intermediate');
});

test('bloomToDifficulty maps evaluate/create (and unknown) to advanced', () => {
  assert.equal(bloomToDifficulty('evaluate'), 'advanced');
  assert.equal(bloomToDifficulty('create'), 'advanced');
  assert.equal(bloomToDifficulty('whatever'), 'advanced');
});

test('buildConceptContext maps prerequisite/related ids to names', () => {
  const graph = new Map([
    ['a', makeNode('a', 'Node A', { prerequisites: ['b'], related_topics: ['c'] })],
    ['b', makeNode('b', 'Node B')],
    ['c', makeNode('c', 'Node C')],
  ]);
  const ctx = buildConceptContext(graph.get('a'), graph);
  assert.equal(ctx.concept_id, 'a');
  assert.equal(ctx.id, 'a');
  assert.equal(ctx.name, 'Node A');
  assert.deepEqual(ctx.prerequisite_names, ['Node B']);
  assert.deepEqual(ctx.related_topic_names, ['Node C']);
  assert.equal(buildConceptContext(null, graph), null);
});

test('stripFences handles json fences, plain fences and backticks', () => {
  assert.equal(stripFences('```json\nabc\n```'), 'abc');
  assert.equal(stripFences('```\nabc\n```'), 'abc');
  assert.equal(stripFences('`abc`'), 'abc');
  assert.equal(stripFences('  abc  '), 'abc');
});

test('findOutermostObject extracts the first balanced object', () => {
  assert.equal(findOutermostObject('{"a":1}'), '{"a":1}');
  assert.equal(findOutermostObject('prefix {"a":{"b":2}} suffix'), '{"a":{"b":2}}');
  assert.equal(findOutermostObject('no braces'), null);
});

test('extractField parses string, array and object typed JSON fields', () => {
  assert.equal(extractField('{"concept_id":"java.a"}', 'concept_id', 'string'), 'java.a');
  assert.deepEqual(extractField('{"ids":["a","b"]}', 'ids', 'array'), ['a', 'b']);
  assert.deepEqual(extractField('{"o":{"k":1}}', 'o', 'object'), { k: 1 });
  assert.equal(extractField('{"x":1}', 'missing', 'string'), null);
});

test('seedGraph upserts nodes and returns a summary', async (t) => {
  const nodes = [
    makeNode('a', 'Node A', { description: 'A desc' }),
    makeNode('b', 'Node B', { description: 'B desc' }),
  ];
  mock.method(ConceptGraphNode, 'bulkWrite', async () => ({
    upsertedCount: 2,
    modifiedCount: 0,
    matchedCount: 2,
  }));
  mock.method(axios, 'post', async () => ({
    data: { embeddings: [new Array(768).fill(0), new Array(768).fill(0)] },
  }));
  t.after(() => mock.restoreAll());

  const summary = await seedGraph(nodes);
  assert.equal(summary.nodeCount, 2);
  assert.equal(summary.upserted, 2);
  assert.equal(axios.post.mock.callCount(), 1);
});

test('seedGraph throws when embedding count mismatches nodes', async (t) => {
  const nodes = [makeNode('a', 'Node A')];
  mock.method(axios, 'post', async () => ({ data: { embeddings: [] } }));
  t.after(() => mock.restoreAll());

  await assert.rejects(() => seedGraph(nodes), /Expected 1 embeddings but received 0/);
});

test('computeCoverage returns zeroed result when no nodes found', async (t) => {
  mock.method(ConceptGraphNode, 'find', () => ({ select: async () => [] }));
  t.after(() => mock.restoreAll());

  const coverage = await computeCoverage('STU_1', 'OOP');
  assert.deepEqual(coverage, { totalNodes: 0, coveredNodes: 0, coveragePct: 0, covered: [] });
});

test('computeCoverage tallies covered nodes from materials', async (t) => {
  const nodes = [
    { concept_id: 'a', name: 'A', category: 'OOP', bloom_level: 'apply' },
    { concept_id: 'b', name: 'B', category: 'OOP', bloom_level: 'understand' },
    { concept_id: 'c', name: 'C', category: 'OOP', bloom_level: 'remember' },
  ];
  mock.method(ConceptGraphNode, 'find', (query) => ({
    select: async () => (query.category ? nodes : []),
  }));
  mock.method(LearningMaterial, 'find', () => ({
    select: async () => [
      { structured_material: { topic_id: 'a' } },
      { structured_material: { topic_id: 'b' } },
    ],
  }));
  t.after(() => mock.restoreAll());

  const coverage = await computeCoverage('STU_1', 'OOP');
  assert.equal(coverage.totalNodes, 3);
  assert.equal(coverage.coveredNodes, 2);
  assert.equal(coverage.coveragePct, 66.67);
  assert.deepEqual(coverage.covered.map((c) => c.concept_id), ['a', 'b']);
});

test('resolveLLM returns the matched concept_id on a valid LLM response', async (t) => {
  const graph = new Map([
    ['java.oop.inheritance', makeNode('java.oop.inheritance', 'Inheritance')],
  ]);
  const client = { generate: async () => 'java.oop.inheritance' };
  const result = await resolveLLM({ topic: 'is-a relation' }, graph, client);
  assert.equal(result.concept_id, 'java.oop.inheritance');
  assert.equal(result.method, 'llm');
});

test('resolveLLM returns llm_no_match when LLM says NO_MATCH', async (t) => {
  const graph = new Map([
    ['java.oop.inheritance', makeNode('java.oop.inheritance', 'Inheritance')],
  ]);
  const client = { generate: async () => 'NO_MATCH' };
  const result = await resolveLLM({ topic: 'anything' }, graph, client);
  assert.equal(result.concept_id, null);
  assert.equal(result.method, 'llm_no_match');
});

test('resolveLLM fails open when the LLM throws', async (t) => {
  const graph = new Map([
    ['java.oop.inheritance', makeNode('java.oop.inheritance', 'Inheritance')],
  ]);
  const client = { generate: async () => { throw new Error('down'); } };
  const result = await resolveLLM({ topic: 'anything' }, graph, client);
  assert.equal(result.concept_id, null);
  assert.equal(result.method, 'llm_no_match');
});

test('resolveEmbedding returns null when the embedder throws', async (t) => {
  const graph = new Map([
    ['a', makeNode('a', 'A', { embedding: [1, 0, 0] })],
  ]);
  const embedder = { embed: async () => { throw new Error('embed fail'); } };
  const result = await resolveEmbedding({ topic: 'x' }, graph, embedder);
  assert.equal(result, null);
});

test('resolveGap short-circuits to unresolved on an empty graph without calling deps', async (t) => {
  let embedCalls = 0;
  let generateCalls = 0;
  const result = await resolveGap(
    { topic: 'anything' },
    new Map(),
    { embed: async () => { embedCalls++; return [1]; } },
    { generate: async () => { generateCalls++; return 'x'; } }
  );
  assert.equal(result.method, 'unresolved');
  assert.equal(embedCalls, 0);
  assert.equal(generateCalls, 0);
});

test('augmentGaps injects implicit prerequisite gaps and returns effective list', async (t) => {
  const graph = new Map([
    ['java.oop.polymorphism.method_overriding', makeNode('java.oop.polymorphism.method_overriding', 'Method Overriding', {
      prerequisites: ['java.oop.inheritance'],
      bloom_level: 'apply',
    })],
    ['java.oop.inheritance', makeNode('java.oop.inheritance', 'Inheritance', {
      bloom_level: 'understand',
      category: 'OOP',
    })],
  ]);
  const embedder = { embed: async () => [0, 0, 0] };
  const client = { generate: async () => 'NO_MATCH' };

  const knowledgeGaps = [
    { topic: 'Method Overriding', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' },
  ];

  const result = await augmentGaps(knowledgeGaps, [], graph, embedder, client);
  assert.equal(result.resolvedGaps.length, 1);
  assert.equal(result.injectedGaps.length, 1);
  assert.equal(result.effectiveGaps.length, 2);

  const injected = result.injectedGaps[0];
  assert.equal(injected.resolution_method, 'implicit');
  assert.equal(injected.resolved_concept_id, 'java.oop.inheritance');
  assert.equal(injected.difficulty_level, 'beginner');
  assert.match(injected.reason, /prerequisite_of:java\.oop\.polymorphism\.method_overriding/);
});

test('augmentGaps maps resolved gaps to concept_context and resolution method', async (t) => {
  const graph = new Map([
    ['java.control.conditionals', makeNode('java.control.conditionals', 'Conditionals', {
      bloom_level: 'apply',
    })],
  ]);
  const embedder = { embed: async () => [0, 0, 0] };
  const client = { generate: async () => 'NO_MATCH' };

  const result = await augmentGaps(
    [{ topic: 'Conditionals', topic_id: 'g1', gap_type: 'FUNDAMENTAL_GAP' }],
    [],
    graph,
    embedder,
    client
  );

  assert.equal(result.resolvedGaps[0].resolution_method, 'exact');
  assert.equal(result.resolvedGaps[0].resolved_concept_id, 'java.control.conditionals');
  assert.equal(result.resolvedGaps[0].concept_context.concept_id, 'java.control.conditionals');
  assert.equal(result.injectedGaps.length, 0);
  assert.equal(result.effectiveGaps.length, 1);
});
