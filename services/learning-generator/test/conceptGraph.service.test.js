const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  resolveExact,
  classify,
  closePrerequisites,
  parseConceptIdResponse,
  cosineSimilarity,
  resolveEmbedding,
} = require('../src/services/conceptGraph.service');

const makeNode = (concept_id, name, opts = {}) => ({
  concept_id,
  name,
  aliases: opts.aliases || [],
  description_embedding: opts.embedding || [],
  prerequisites: opts.prerequisites || [],
  description: opts.description || `Description for ${name}`,
  bloom_level: opts.bloom_level || 'apply',
});

const fixtureNodes = [
  makeNode('java.fund.variables', 'Variables', { bloom_level: 'remember' }),
  makeNode('java.fund.data_types.primitive', 'Primitive Data Types', {
    prerequisites: ['java.fund.variables'],
    bloom_level: 'remember',
  }),
  makeNode('java.fund.data_types.reference', 'Reference Data Types', {
    prerequisites: ['java.fund.data_types.primitive'],
    bloom_level: 'remember',
  }),
  makeNode('java.fund.operators', 'Operators', {
    prerequisites: ['java.fund.data_types.primitive'],
    bloom_level: 'understand',
  }),
  makeNode('java.control.conditionals', 'Conditionals', {
    prerequisites: ['java.fund.operators'],
    aliases: ['if statement', 'if else'],
    bloom_level: 'apply',
  }),
  makeNode('java.control.loops.for', 'For Loop', {
    prerequisites: ['java.control.conditionals'],
    bloom_level: 'apply',
  }),
  makeNode('java.methods.declaration', 'Method Declaration', {
    prerequisites: ['java.fund.data_types.primitive'],
    bloom_level: 'understand',
  }),
  makeNode('java.methods.parameters_return', 'Parameters and Return Values', {
    prerequisites: ['java.methods.declaration'],
    bloom_level: 'apply',
  }),
  makeNode('java.methods.overloading', 'Method Overloading', {
    prerequisites: ['java.methods.parameters_return'],
    aliases: ['overloading'],
    bloom_level: 'apply',
  }),
  makeNode('java.oop.classes_objects', 'Classes and Objects', {
    prerequisites: ['java.methods.declaration', 'java.fund.data_types.reference'],
    bloom_level: 'understand',
  }),
  makeNode('java.oop.encapsulation', 'Encapsulation', {
    prerequisites: ['java.oop.classes_objects'],
    bloom_level: 'apply',
  }),
  makeNode('java.oop.access_modifiers', 'Access Modifiers', {
    prerequisites: ['java.oop.encapsulation'],
    bloom_level: 'understand',
  }),
  makeNode('java.oop.inheritance', 'Inheritance', {
    prerequisites: ['java.oop.classes_objects', 'java.oop.access_modifiers'],
    bloom_level: 'apply',
  }),
  makeNode('java.oop.polymorphism.method_overriding', 'Method Overriding', {
    prerequisites: ['java.oop.inheritance'],
    aliases: ['overriding', '@Override'],
    bloom_level: 'apply',
  }),
];

const fixtureGraph = new Map(fixtureNodes.map((n) => [n.concept_id, n]));

test('resolveExact matches node name exactly, case-insensitively', () => {
  const result = resolveExact('  CONDITIONALS ', fixtureGraph);
  assert.equal(result.concept_id, 'java.control.conditionals');
  assert.equal(result.method, 'exact');
  assert.equal(result.confidence, 1.0);
});

test('resolveExact matches aliases', () => {
  const result = resolveExact('if statement', fixtureGraph);
  assert.equal(result.concept_id, 'java.control.conditionals');
  assert.equal(result.method, 'alias');
  assert.equal(result.confidence, 1.0);
});

test('resolveExact returns null when nothing matches', () => {
  assert.equal(resolveExact('quantum computing', fixtureGraph), null);
});

test('resolveExact returns null for empty topic', () => {
  assert.equal(resolveExact('', fixtureGraph), null);
  assert.equal(resolveExact(null, fixtureGraph), null);
});

test('classify returns MASTERED for strengths', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
    ],
    strengths: [
      { topic: 'Conditionals', resolved_concept_id: 'java.control.conditionals' },
    ],
  };
  assert.equal(classify('java.control.conditionals', profile), 'MASTERED');
});

test('classify returns GAP for resolved gaps', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
    ],
    strengths: [],
  };
  assert.equal(classify('java.oop.polymorphism.method_overriding', profile), 'GAP');
});

test('classify returns UNKNOWN when never assessed', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
    ],
    strengths: [],
  };
  assert.equal(classify('java.fund.variables', profile), 'UNKNOWN');
});

test('closePrerequisites flags blocking UNKNOWN prerequisites without injecting them', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
    ],
    strengths: [],
  };
  const result = closePrerequisites(['java.oop.polymorphism.method_overriding'], profile, fixtureGraph);

  assert.deepEqual(result.explicitGaps, ['java.oop.polymorphism.method_overriding']);
  assert.deepEqual(result.implicitGaps, []);
  assert.deepEqual(result.unverified, [
    { concept_id: 'java.oop.inheritance', blocks: 'java.oop.polymorphism.method_overriding' },
  ]);
});

test('closePrerequisites stops walking when a prerequisite is MASTERED', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
    ],
    strengths: [
      { topic: 'Inheritance', resolved_concept_id: 'java.oop.inheritance' },
    ],
  };
  const result = closePrerequisites(['java.oop.polymorphism.method_overriding'], profile, fixtureGraph);
  assert.deepEqual(result.unverified, []);
  assert.deepEqual(result.implicitGaps, []);
});

test('closePrerequisites walks past explicit GAP prerequisites', () => {
  const profile = {
    knowledge_gaps: [
      { topic: 'Method Overriding', resolved_concept_id: 'java.oop.polymorphism.method_overriding' },
      { topic: 'Inheritance', resolved_concept_id: 'java.oop.inheritance' },
      { topic: 'Classes and Objects', resolved_concept_id: 'java.oop.classes_objects' },
    ],
    strengths: [],
  };
  const result = closePrerequisites(
    [
      'java.oop.polymorphism.method_overriding',
      'java.oop.inheritance',
      'java.oop.classes_objects',
    ],
    profile,
    fixtureGraph
  );

  assert.deepEqual(result.implicitGaps, []);
  const unverifiedIds = result.unverified.map((u) => u.concept_id);
  assert.ok(unverifiedIds.includes('java.oop.access_modifiers'));
  assert.ok(unverifiedIds.includes('java.methods.declaration'));
  assert.ok(unverifiedIds.includes('java.fund.data_types.reference'));
});

test('parseConceptIdResponse handles fenced plain identifiers', () => {
  assert.equal(
    parseConceptIdResponse('```\njava.oop.inheritance\n```', fixtureGraph),
    'java.oop.inheritance'
  );
});

test('parseConceptIdResponse handles JSON objects', () => {
  assert.equal(
    parseConceptIdResponse('{"concept_id": "java.oop.inheritance"}', fixtureGraph),
    'java.oop.inheritance'
  );
});

test('parseConceptIdResponse extracts identifiers from surrounding text', () => {
  assert.equal(
    parseConceptIdResponse('The matched concept is java.oop.inheritance.', fixtureGraph),
    'java.oop.inheritance'
  );
});

test('parseConceptIdResponse returns null for NO_MATCH', () => {
  assert.equal(parseConceptIdResponse('NO_MATCH', fixtureGraph), null);
  assert.equal(parseConceptIdResponse('no match found', fixtureGraph), null);
});

test('cosineSimilarity computes correct values', () => {
  assert.equal(cosineSimilarity([1, 0, 0], [1, 0, 0]), 1);
  assert.equal(cosineSimilarity([1, 0, 0], [0, 1, 0]), 0);
  const half = Math.SQRT1_2;
  assert.ok(Math.abs(cosineSimilarity([1, 0], [half, half]) - half) < 1e-9);
  assert.equal(cosineSimilarity([1, 0], [1, 0, 0]), 0);
  assert.equal(cosineSimilarity([], []), 0);
});

test('resolveEmbedding returns null below threshold', async () => {
  const graph = new Map([
    ['java.fund.variables', makeNode('java.fund.variables', 'Variables', { embedding: [1, 0, 0] })],
    ['java.fund.operators', makeNode('java.fund.operators', 'Operators', { embedding: [0, 1, 0] })],
  ]);
  const embedder = { embed: async () => [1, 1, 1] };
  const result = await resolveEmbedding({ topic: 'gibberish topic' }, graph, embedder);
  assert.equal(result, null);
});

test('resolveEmbedding escalates on ambiguity (top-2 within 0.05)', async () => {
  const graph = new Map([
    ['a', makeNode('a', 'Node A', { embedding: [1, 0] })],
    ['b', makeNode('b', 'Node B', { embedding: [0.99, Math.sqrt(1 - 0.99 * 0.99)] })],
  ]);
  const embedder = { embed: async () => [1, 0] };
  const result = await resolveEmbedding({ topic: 'ambiguous' }, graph, embedder);
  assert.equal(result, null);
});

test('resolveEmbedding returns best node above threshold with clear margin', async () => {
  const graph = new Map([
    ['a', makeNode('a', 'Node A', { embedding: [1, 0] })],
    ['b', makeNode('b', 'Node B', { embedding: [0, 1] })],
  ]);
  const embedder = { embed: async () => [1, 0] };
  const result = await resolveEmbedding({ topic: 'clear match' }, graph, embedder);
  assert.equal(result.concept_id, 'a');
  assert.equal(result.method, 'embedding');
  assert.equal(result.confidence, 1);
});
