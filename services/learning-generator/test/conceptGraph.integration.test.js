const { test } = require('node:test');
const assert = require('node:assert/strict');
const {
  resolveGap,
  closePrerequisites,
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
  makeNode('java.oop.polymorphism.method_overriding', 'Method Overriding', {
    prerequisites: ['java.oop.inheritance'],
    aliases: ['overriding'],
    embedding: [1, 0, 0],
  }),
  makeNode('java.oop.inheritance', 'Inheritance', {
    prerequisites: ['java.oop.classes_objects'],
    embedding: [0, 1, 0],
  }),
  makeNode('java.oop.classes_objects', 'Classes and Objects', {
    prerequisites: [],
    embedding: [0, 0, 1],
  }),
];

const fixtureGraph = new Map(fixtureNodes.map((n) => [n.concept_id, n]));

const profile = (knowledge_gaps, strengths = []) => ({
  knowledge_gaps,
  strengths,
});

test('resolveGap runs the full three-tier flow and closePrerequisites flags blocking prerequisites', async () => {
  const mockEmbedder = {
    async embed(text) {
      if (text.includes('inherits from a superclass')) return [0, 1, 0];
      return [0, 0, 0];
    },
  };
  const mockOllama = {
    async generate() {
      return 'NO_MATCH';
    },
  };

  const gaps = [
    { topic: 'Method Overriding', evidence_summary: 'confuses override with overload' },
    { topic: 'inherits from a superclass', evidence_summary: 'subclass reuse' },
    { topic: 'completely unrelated topic', evidence_summary: 'nothing' },
  ];

  const resolved = [];
  for (const gap of gaps) {
    const resolution = await resolveGap(gap, fixtureGraph, mockEmbedder, mockOllama);
    resolved.push({ ...gap, ...resolution });
  }

  assert.equal(resolved[0].method, 'exact');
  assert.equal(resolved[0].concept_id, 'java.oop.polymorphism.method_overriding');

  assert.equal(resolved[1].method, 'embedding');
  assert.equal(resolved[1].concept_id, 'java.oop.inheritance');

  assert.equal(resolved[2].method, 'llm_no_match');
  assert.equal(resolved[2].concept_id, null);

  const resolvedIds = resolved.map((g) => g.concept_id).filter(Boolean);
  const closure = closePrerequisites(resolvedIds, profile(resolved), fixtureGraph);

  assert.deepEqual(closure.explicitGaps, [
    'java.oop.polymorphism.method_overriding',
    'java.oop.inheritance',
  ]);
  assert.deepEqual(closure.implicitGaps, []);
  assert.deepEqual(closure.unverified, [
    { concept_id: 'java.oop.classes_objects', blocks: 'java.oop.inheritance' },
  ]);
});

test('resolveGap escalates to LLM tier when embedding fails', async () => {
  const mockEmbedder = {
    async embed() {
      throw new Error('ollama embed unreachable');
    },
  };
  const mockOllama = {
    async generate() {
      return 'java.oop.inheritance';
    },
  };

  const resolution = await resolveGap(
    { topic: 'runtime dispatch issue' },
    fixtureGraph,
    mockEmbedder,
    mockOllama
  );

  assert.equal(resolution.method, 'llm');
  assert.equal(resolution.concept_id, 'java.oop.inheritance');
});

test('resolveGap returns unresolved and never throws when the LLM is down', async () => {
  const mockEmbedder = {
    async embed() {
      return [0, 0, 0];
    },
  };
  const mockOllama = {
    async generate() {
      throw new Error('ollama generate unreachable');
    },
  };

  const resolution = await resolveGap(
    { topic: 'runtime dispatch issue' },
    fixtureGraph,
    mockEmbedder,
    mockOllama
  );

  assert.equal(resolution.concept_id, null);
  assert.equal(resolution.method, 'llm_no_match');
});

test('resolveGap fails open on an empty graph', async () => {
  const resolution = await resolveGap(
    { topic: 'anything' },
    new Map(),
    { embed: async () => [0] },
    { generate: async () => 'java.oop.inheritance' }
  );

  assert.equal(resolution.concept_id, null);
  assert.equal(resolution.method, 'unresolved');
});

test('resolveGap does not call the LLM when the graph is empty', async () => {
  let generateCalls = 0;
  const resolution = await resolveGap(
    { topic: 'anything' },
    new Map(),
    { embed: async () => [0] },
    { generate: async () => { generateCalls++; return 'java.oop.inheritance'; } }
  );

  assert.equal(resolution.concept_id, null);
  assert.equal(generateCalls, 0);
});
