const { test } = require('node:test');
const assert = require('node:assert/strict');
const { validateGraphAcyclic } = require('../scripts/seedConceptGraph');
const seedNodes = require('../seed/java_oop_graph.json');

const baseNode = (concept_id, prerequisites = []) => ({
  concept_id,
  name: concept_id,
  category: 'Test',
  subcategory: 'Test',
  bloom_level: 'apply',
  description: `Description for ${concept_id}`,
  aliases: [],
  prerequisites,
  related_topics: [],
  source: 'test',
  version: 1,
});

test('the real seed graph is acyclic', () => {
  assert.equal(validateGraphAcyclic(seedNodes), true);
  assert.ok(seedNodes.length >= 40);
});

test('validateGraphAcyclic rejects a cyclic graph', () => {
  const nodes = [
    baseNode('java.fund.variables', ['java.control.conditionals']),
    baseNode('java.control.conditionals', ['java.fund.operators']),
    baseNode('java.fund.operators', ['java.fund.variables']),
  ];
  assert.throws(() => validateGraphAcyclic(nodes), /cyclic/i);
});

test('validateGraphAcyclic rejects a self-loop', () => {
  const nodes = [
    baseNode('java.fund.variables'),
    baseNode('java.fund.operators', ['java.fund.operators']),
  ];
  assert.throws(() => validateGraphAcyclic(nodes), /self-loop/i);
});

test('validateGraphAcyclic rejects unknown prerequisite references', () => {
  const nodes = [
    baseNode('java.fund.variables'),
    baseNode('java.fund.operators', ['java.fund.does_not_exist']),
  ];
  assert.throws(() => validateGraphAcyclic(nodes), /unknown prerequisite/i);
});

test('validateGraphAcyclic rejects duplicate concept_ids', () => {
  const nodes = [
    baseNode('java.fund.variables'),
    baseNode('java.fund.variables'),
  ];
  assert.throws(() => validateGraphAcyclic(nodes), /duplicate/i);
});

test('validateGraphAcyclic rejects non-array input', () => {
  assert.throws(() => validateGraphAcyclic(null), /non-empty array/i);
});
