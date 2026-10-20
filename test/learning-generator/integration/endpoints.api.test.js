'use strict';

const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

require('../support/install');

const LearningMaterial = require('../../../services/learning-generator/src/models/LearningMaterial');
const StudentProgress = require('../../../services/learning-generator/src/models/StudentProgress');
const materialService = require('../../../services/learning-generator/src/services/material.service');
const {
  getMaterialsByStudent,
  getMaterialById,
  deleteMaterial,
} = require('../../../services/learning-generator/src/controllers/material.controller');
const {
  getProgressStats,
} = require('../../../services/learning-generator/src/controllers/progress.controller');

const makeRes = () => {
  const res = { statusCode: null, body: null };
  res.status = (c) => { res.statusCode = c; return res; };
  res.json = (b) => { res.body = b; return res; };
  return res;
};

const makeReq = (overrides = {}) => ({
  student: { id: 'STU_OWNER' },
  params: {},
  query: {},
  ...overrides,
});

test('GET /api/materials/:studentId returns paginated materials for the owner', async (t) => {
  const materials = [{ _id: 'm1', structured_material: { material_id: 'MAT_1', student_id: 'STU_OWNER' } }];
  mock.method(LearningMaterial, 'find', () => ({
    sort: () => ({ skip: () => ({ limit: async () => materials }) }),
  }));
  mock.method(LearningMaterial, 'countDocuments', async () => 1);
  mock.method(materialService, 'buildMaterialQuery', () => ({ student: 'STU_OWNER' }));
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_OWNER' }, query: { limit: '10', page: '1' } });
  const res = makeRes();
  await getMaterialsByStudent(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(res.body.success, true);
  assert.equal(res.body.data.items.length, 1);
  assert.deepEqual(res.body.data.meta, { page: 1, limit: 10, total: 1, pages: 1 });
});

test('GET /api/materials/item/:materialId returns a material by 24-hex id for the owner', async (t) => {
  const material = {
    _id: '507f1f77bcf86cd799439011',
    structured_material: { material_id: 'MAT_1', student_id: 'STU_OWNER' },
  };
  mock.method(LearningMaterial, 'findById', async () => material);
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.structured_material.material_id, 'MAT_1');
  assert.equal(LearningMaterial.findById.mock.callCount(), 1);
});

test('GET /api/materials/item/:materialId falls back to findOne for non-hex material ids', async (t) => {
  const material = {
    _id: 'abc',
    structured_material: { material_id: 'MAT_UUID', student_id: 'STU_OWNER' },
  };
  mock.method(LearningMaterial, 'findById', async () => null);
  mock.method(LearningMaterial, 'findOne', async () => material);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { materialId: 'MAT_UUID' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(LearningMaterial.findOne.mock.callCount(), 1);
});

test('DELETE /api/materials/item/:materialId hard-deletes material and cascades progress', async (t) => {
  const material = {
    _id: '507f1f77bcf86cd799439011',
    structured_material: { material_id: 'MAT_1', student_id: 'STU_OWNER' },
  };
  mock.method(LearningMaterial, 'findById', async () => material);
  mock.method(LearningMaterial, 'findOne', async () => null);
  mock.method(LearningMaterial, 'deleteOne', async () => ({ deletedCount: 1 }));
  mock.method(StudentProgress, 'deleteMany', async () => ({ deletedCount: 2 }));
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await deleteMaterial(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(res.body.success, true);
  assert.equal(res.body.message, 'Material deleted successfully');
  assert.equal(LearningMaterial.deleteOne.mock.callCount(), 1);
  assert.equal(StudentProgress.deleteMany.mock.callCount(), 1);
  assert.deepEqual(StudentProgress.deleteMany.mock.calls[0].arguments[0], {
    material_id: '507f1f77bcf86cd799439011',
  });
});

test('GET /api/progress/student/:studentId/stats aggregates progress for the owner', async (t) => {
  const progressList = [
    { student_id: 'STU_OWNER', total_steps: 4, completed_steps: [1, 2], completed_at: null, quiz_score: 80 },
    { student_id: 'STU_OWNER', total_steps: 2, completed_steps: [1, 2], completed_at: new Date(), quiz_score: 60 },
  ];
  mock.method(StudentProgress, 'find', async () => progressList);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_OWNER' } });
  const res = makeRes();
  await getProgressStats(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.total_materials, 2);
  assert.equal(res.body.data.completed_materials, 1);
  assert.equal(res.body.data.in_progress_materials, 1);
  assert.equal(res.body.data.total_steps, 6);
  assert.equal(res.body.data.completed_steps, 4);
  assert.equal(res.body.data.progress_percentage, 67); // Math.round(4/6*100)
  assert.equal(res.body.data.avg_quiz_score, 70); // (80+60)/2
});
