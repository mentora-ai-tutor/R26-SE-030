'use strict';

const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

require('../support/install');

const LearningMaterial = require('../../../services/learning-generator/src/models/LearningMaterial');
const StudentProgress = require('../../../services/learning-generator/src/models/StudentProgress');
const {
  getMaterialsByStudent,
  getMaterialById,
  deleteMaterial,
  getMaterialStats,
} = require('../../../services/learning-generator/src/controllers/material.controller');
const {
  getProgressByStudent,
  getProgressStats,
} = require('../../../services/learning-generator/src/controllers/progress.controller');

const makeRes = () => {
  return {
    statusCode: null,
    body: null,
    status(code) { this.statusCode = code; return this; },
    json(body) { this.body = body; return this; },
  };
};

const makeReq = (overrides = {}) => ({
  student: { id: 'STU_OWNER' },
  params: {},
  query: {},
  ...overrides,
});

test('getMaterialsByStudent returns 403 FORBIDDEN when studentId differs from token student', async () => {
  const req = makeReq({ params: { studentId: 'STU_OTHER' } });
  const res = makeRes();
  await getMaterialsByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('getMaterialById returns 403 FORBIDDEN for a material owned by another student', async (t) => {
  const material = { structured_material: { material_id: 'MAT_1', student_id: 'STU_OTHER' } };
  mock.method(LearningMaterial, 'findById', async () => material);
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('getMaterialStats returns 403 FORBIDDEN on student mismatch', async () => {
  const req = makeReq({ params: { studentId: 'STU_OTHER' } });
  const res = makeRes();
  await getMaterialStats(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('deleteMaterial returns 403 FORBIDDEN when material belongs to another student', async (t) => {
  const material = { structured_material: { material_id: 'MAT_1', student_id: 'STU_OTHER' } };
  mock.method(LearningMaterial, 'findById', async () => material);
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await deleteMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('getProgressByStudent returns 403 FORBIDDEN on student mismatch', async () => {
  const req = makeReq({ params: { studentId: 'STU_OTHER' } });
  const res = makeRes();
  await getProgressByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('getProgressStats returns 403 FORBIDDEN on student mismatch', async () => {
  const req = makeReq({ params: { studentId: 'STU_OTHER' } });
  const res = makeRes();
  await getProgressStats(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
  assert.equal(res.body.code, 'FORBIDDEN');
});

test('getProgressStats computes aggregation for the owner', async (t) => {
  const progressList = [
    { student_id: 'STU_OWNER', total_steps: 5, completed_steps: [1, 2, 3], completed_at: new Date(), quiz_score: 70 },
    { student_id: 'STU_OWNER', total_steps: 3, completed_steps: [], completed_at: null, quiz_score: null },
  ];
  mock.method(StudentProgress, 'find', async () => progressList);
  t.after(() => mock.restoreAll());

  const req = makeReq({ params: { studentId: 'STU_OWNER' } });
  const res = makeRes();
  await getProgressStats(req, res, (e) => { throw e; });

  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.total_materials, 2);
  assert.equal(res.body.data.completed_materials, 1);
  assert.equal(res.body.data.in_progress_materials, 0);
  assert.equal(res.body.data.not_started_materials, 1);
  assert.equal(res.body.data.progress_percentage, 38); // Math.round(3/8 * 100)
  assert.equal(res.body.data.completed_steps, 3);
  assert.equal(res.body.data.avg_quiz_score, 70);
});
