'use strict';

const { test, mock } = require('node:test');
const assert = require('node:assert/strict');
const { performance } = require('node:perf_hooks');

require('../support/install');

const materialService = require('../../../services/learning-generator/src/services/material.service');
const LearningMaterial = require('../../../services/learning-generator/src/models/LearningMaterial');
const StudentProgress = require('../../../services/learning-generator/src/models/StudentProgress');
const { deleteMaterial } = require('../../../services/learning-generator/src/controllers/material.controller');

const makeRes = () => {
  const res = { statusCode: null, body: null };
  res.status = (c) => { res.statusCode = c; return res; };
  res.json = (b) => { res.body = b; return res; };
  return res;
};

test('buildMaterialQuery runs 10k times in under 1s', () => {
  const params = { topic: 'Variables', gap_type: 'PARTIAL_GAP', status: 'ready' };
  const start = performance.now();
  for (let i = 0; i < 10000; i++) {
    const filter = materialService.buildMaterialQuery('STU_PERF', params);
    assert.equal(filter['structured_material.topic'], 'Variables');
  }
  const elapsed = performance.now() - start;
  console.log(`buildMaterialQuery x10000 took ${elapsed.toFixed(2)}ms`);
  assert.ok(elapsed < 1000, `buildMaterialQuery took ${elapsed.toFixed(2)}ms, expected < 1000ms`);
});

test('mocked controller delete flow completes in under 500ms', async (t) => {
  const materialId = '507f1f77bcf86cd799439011';
  const material = {
    _id: materialId,
    structured_material: { material_id: 'MAT_1', student_id: 'STU_OWNER' },
  };
  mock.method(LearningMaterial, 'findById', async () => material);
  mock.method(LearningMaterial, 'findOne', async () => null);
  mock.method(LearningMaterial, 'deleteOne', async () => ({ deletedCount: 1 }));
  mock.method(StudentProgress, 'deleteMany', async () => ({ deletedCount: 1 }));
  t.after(() => mock.restoreAll());

  const start = performance.now();
  for (let i = 0; i < 50; i++) {
    const req = { student: { id: 'STU_OWNER' }, params: { materialId } };
    const res = makeRes();
    await deleteMaterial(req, res, () => {});
    assert.equal(res.statusCode, 200);
  }
  const elapsed = performance.now() - start;
  console.log(`controller delete flow x50 took ${elapsed.toFixed(2)}ms`);
  assert.ok(elapsed < 500, `delete flow took ${elapsed.toFixed(2)}ms, expected < 500ms`);
});
