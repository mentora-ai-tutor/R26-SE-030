const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const StudentProgress = require('../src/models/StudentProgress');
const LearningMaterial = require('../src/models/LearningMaterial');
const materialService = require('../src/services/material.service');
const {
  getProgressByMaterial,
  updateProgress,
  getProgressByStudent,
  getProgressStats,
} = require('../src/controllers/progress.controller');
const {
  getCoverage,
  seedConceptGraph,
} = require('../src/controllers/conceptGraph.controller');
const conceptGraphService = require('../src/services/conceptGraph.service');
const MasteryProfile = require('../src/models/MasteryProfile');
const ConceptGraphNode = require('../src/models/ConceptGraphNode');

const makeRes = () => {
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
  return res;
};

const baseReq = (overrides = {}) => ({
  student: { id: 'STU_1' },
  params: {},
  query: {},
  body: {},
  ...overrides,
});

const makeMaterial = (opts = {}) => ({
  _id: opts._id || '507f1f77bcf86cd799439011',
  structured_material: {
    material_id: opts.material_id || 'MAT_1',
    student_id: opts.student_id || 'STU_1',
    topic: opts.topic || 'Variables',
    topic_id: opts.topic_id || 'java.fund.variables',
  },
});

const makeProgressDoc = (opts = {}) => {
  const p = {
    student_id: 'STU_1',
    material_id: '507f1f77bcf86cd799439011',
    topic_id: 'java.fund.variables',
    total_steps: opts.total_steps || 0,
    completed_steps: opts.completed_steps || [],
    quiz_score: opts.quiz_score !== undefined ? opts.quiz_score : null,
    completed_at: opts.completed_at || null,
    save: async function () { return this; },
    toJSON() {
      return { ...this };
    },
  };
  return p;
};

test('getProgressByMaterial returns 404 when material missing', async (t) => {
  mock.method(LearningMaterial, 'findById', async () => null);
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_X' } });
  const res = makeRes();
  await getProgressByMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});

test('getProgressByMaterial returns 403 when material belongs to another student', async (t) => {
  mock.method(LearningMaterial, 'findById', async () => makeMaterial({ student_id: 'OTHER' }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getProgressByMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getProgressByMaterial returns existing progress', async (t) => {
  const progress = makeProgressDoc({ total_steps: 5, completed_steps: [1, 2] });
  mock.method(LearningMaterial, 'findById', async () => makeMaterial());
  mock.method(StudentProgress, 'findOne', async () => progress);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getProgressByMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.completed_steps.length, 2);
});

test('updateProgress creates a new progress doc and adds completed step', async (t) => {
  mock.method(LearningMaterial, 'findById', async () => makeMaterial());
  mock.method(StudentProgress, 'findOne', async () => null);
  const created = [];
  mock.method(StudentProgress.prototype, 'save', async function () { created.push(this); return this; });
  t.after(() => mock.restoreAll());

  const req = baseReq({
    params: { materialId: '507f1f77bcf86cd799439011' },
    body: { total_steps: 5, completed_step: 3, quiz_score: 80 },
  });
  const res = makeRes();
  await updateProgress(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  const saved = created[0];
  assert.equal(saved.total_steps, 5);
  assert.deepEqual(saved.completed_steps, [3]);
  assert.equal(saved.quiz_score, 80);
});

test('updateProgress prevents duplicate completed steps', async (t) => {
  const progress = makeProgressDoc({ total_steps: 5, completed_steps: [3] });
  const save = mock.method(progress, 'save', async function () { return this; });
  mock.method(LearningMaterial, 'findById', async () => makeMaterial());
  mock.method(StudentProgress, 'findOne', async () => progress);
  t.after(() => mock.restoreAll());

  const req = baseReq({
    params: { materialId: '507f1f77bcf86cd799439011' },
    body: { completed_step: 3 },
  });
  const res = makeRes();
  await updateProgress(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.deepEqual(progress.completed_steps, [3], 'should not be duplicated');
  assert.equal(save.mock.callCount(), 1);
});

test('updateProgress marks completed when all steps done', async (t) => {
  const progress = makeProgressDoc({ total_steps: 2, completed_steps: [1] });
  mock.method(LearningMaterial, 'findById', async () => makeMaterial());
  mock.method(StudentProgress, 'findOne', async () => progress);
  mock.method(progress, 'save', async function () { return this; });
  t.after(() => mock.restoreAll());

  const req = baseReq({
    params: { materialId: '507f1f77bcf86cd799439011' },
    body: { completed_step: 2 },
  });
  const res = makeRes();
  await updateProgress(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.ok(progress.completed_at);
});

test('getProgressByStudent returns enriched progress for the owner', async (t) => {
  const progress = makeProgressDoc({ total_steps: 5, completed_steps: [1] });
  const material = makeMaterial();
  mock.method(StudentProgress, 'find', () => ({ sort: async () => [progress] }));
  mock.method(LearningMaterial, 'find', async () => [material]);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getProgressByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.length, 1);
  assert.equal(res.body.data[0].topic, 'Variables');
});

test('getProgressStats computes progress percentages', async (t) => {
  const progressList = [
    makeProgressDoc({ total_steps: 10, completed_steps: [1, 2, 3, 4], quiz_score: 80 }),
    makeProgressDoc({ total_steps: 5, completed_steps: [], completed_at: new Date(), quiz_score: 100 }),
  ];
  mock.method(StudentProgress, 'find', async () => progressList);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getProgressStats(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.total_materials, 2);
  assert.equal(res.body.data.completed_materials, 1);
  assert.equal(res.body.data.completed_steps, 4);
  assert.equal(res.body.data.total_steps, 15);
  assert.equal(res.body.data.progress_percentage, 27);
  assert.equal(res.body.data.avg_quiz_score, 90);
});

test('getCoverage returns coverage with implicit gap details', async (t) => {
  mock.method(conceptGraphService, 'computeCoverage', async () => ({
    totalNodes: 3,
    coveredNodes: 1,
    coveragePct: 33.33,
    covered: [],
  }));
  mock.method(MasteryProfile, 'findOne', () => ({
    sort: async () => ({
      augmented_profile: {
        implicit_gaps: [{ concept_id: 'java.oop.inheritance', reason: 'prerequisite_of:x' }],
        unverified_prerequisites: [{ concept_id: 'java.oop.classes_objects', blocks: 'y' }],
      },
    }),
  }));
  mock.method(ConceptGraphNode, 'find', (query) => ({
    select: async () => [
      { concept_id: 'java.oop.inheritance', name: 'Inheritance' },
      { concept_id: 'java.oop.classes_objects', name: 'Classes and Objects' },
    ],
  }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' }, query: { category: 'OOP' } });
  const res = makeRes();
  await getCoverage(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.implicitGapsCount, 1);
  assert.equal(res.body.data.unverifiedCount, 1);
  assert.equal(res.body.data.implicitGaps[0].name, 'Inheritance');
  assert.equal(res.body.data.unresolved[0].name, 'Classes and Objects');
});

test('seedConceptGraph returns seed summary', async (t) => {
  mock.method(conceptGraphService, 'seedGraph', async () => ({ nodeCount: 40 }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ body: [{ concept_id: 'a' }] });
  const res = makeRes();
  await seedConceptGraph(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.nodeCount, 40);
});
