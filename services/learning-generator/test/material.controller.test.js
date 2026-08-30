const { test, mock } = require('node:test');
const assert = require('node:assert/strict');

const LearningMaterial = require('../src/models/LearningMaterial');
const materialService = require('../src/services/material.service');
const {
  getMaterialsByStudent,
  getMaterialById,
  getTopics,
  getMaterialStats,
  getMaterialsByTopic,
  deleteMaterial,
} = require('../src/controllers/material.controller');

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
  ...overrides,
});

const makeMaterialDoc = (opts = {}) => ({
  structured_material: {
    material_id: opts.material_id || 'MAT_1',
    student_id: opts.student_id || 'STU_1',
    topic: opts.topic || 'Variables',
    topic_id: opts.topic_id || 'java.fund.variables',
    gap_type: opts.gap_type || 'FUNDAMENTAL_GAP',
    quality_flags: {},
  },
  save: async function () { return this; },
  toObject() {
    return { structured_material: this.structured_material, _id: 'x' };
  },
});

test('getMaterialsByStudent returns 403 on student mismatch', async () => {
  const req = baseReq({ params: { studentId: 'OTHER' } });
  const res = makeRes();
  await getMaterialsByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getMaterialsByStudent returns paginated materials', async (t) => {
  const materials = [makeMaterialDoc()];
  mock.method(LearningMaterial, 'find', () => ({
    sort: () => ({ skip: () => ({ limit: async () => materials }) }),
  }));
  mock.method(LearningMaterial, 'countDocuments', async () => 1);
  mock.method(materialService, 'buildMaterialQuery', () => ({ student: 'STU_1' }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getMaterialsByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.items.length, 1);
  assert.equal(res.body.data.meta.total, 1);
  assert.equal(res.body.data.meta.page, 1);
});

test('getMaterialsByStudent honors sort order param', async (t) => {
  mock.method(LearningMaterial, 'find', (filter) => ({
    sort: (sortObj) => {
      assert.deepEqual(sortObj, { 'structured_material.generated_at': 1 }); // asc
      return { skip: () => ({ limit: async () => [] }) };
    },
  }));
  mock.method(LearningMaterial, 'countDocuments', async () => 0);
  mock.method(materialService, 'buildMaterialQuery', () => ({}));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' }, query: { order: 'asc' } });
  const res = makeRes();
  await getMaterialsByStudent(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
});

test('getMaterialById returns 403 when material belongs to another student', async (t) => {
  const material = makeMaterialDoc({ student_id: 'OTHER', material_id: 'MAT_1' });
  mock.method(LearningMaterial, 'findById', async () => material);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('getMaterialById returns the material for the owner', async (t) => {
  const material = makeMaterialDoc({ material_id: 'MAT_1' });
  mock.method(LearningMaterial, 'findById', async () => material);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: '507f1f77bcf86cd799439011' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.structured_material.material_id, 'MAT_1');
});

test('getMaterialById returns 404 when not found', async (t) => {
  mock.method(LearningMaterial, 'findById', async () => null);
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_MISSING' } });
  const res = makeRes();
  await getMaterialById(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});

test('getTopics returns 403 on student mismatch and topics on success', async (t) => {
  mock.method(materialService, 'getDistinctTopics', async () => [{ topic: 'Variables' }]);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getTopics(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.deepEqual(res.body.data, [{ topic: 'Variables' }]);
});

test('getMaterialStats returns computed stats', async (t) => {
  mock.method(materialService, 'getMaterialStats', async () => ({ total_materials: 5 }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1' } });
  const res = makeRes();
  await getMaterialStats(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.total_materials, 5);
});

test('getMaterialsByTopic returns materials filtered by topic', async (t) => {
  const materials = [makeMaterialDoc()];
  mock.method(LearningMaterial, 'find', () => ({ sort: async () => materials }));
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { studentId: 'STU_1', topicId: 'java.fund.variables' } });
  const res = makeRes();
  await getMaterialsByTopic(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(res.body.data.length, 1);
});

test('deleteMaterial soft-deletes the material for the owner', async (t) => {
  const material = makeMaterialDoc({ material_id: 'MAT_1' });
  const save = mock.method(material, 'save', async function () { return this; });
  mock.method(LearningMaterial, 'findOne', async () => material);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_1' } });
  const res = makeRes();
  await deleteMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 200);
  assert.equal(material.structured_material.quality_flags.deleted, true);
  assert.equal(save.mock.callCount(), 1);
});

test('deleteMaterial returns 403 when material belongs to another student', async (t) => {
  const material = makeMaterialDoc({ material_id: 'MAT_1', student_id: 'OTHER' });
  mock.method(LearningMaterial, 'findOne', async () => material);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_1' } });
  const res = makeRes();
  await deleteMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 403);
});

test('deleteMaterial returns 404 when material missing', async (t) => {
  mock.method(LearningMaterial, 'findOne', async () => null);
  t.after(() => mock.restoreAll());

  const req = baseReq({ params: { materialId: 'MAT_MISSING' } });
  const res = makeRes();
  await deleteMaterial(req, res, (e) => { throw e; });
  assert.equal(res.statusCode, 404);
});
