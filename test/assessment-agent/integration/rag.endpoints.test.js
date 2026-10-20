'use strict';

const request = require('supertest');

jest.mock('express', () => require('./helpers/expressMock'), { virtual: true });
jest.mock('cors', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('helmet', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('morgan', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('jsonwebtoken', () => ({ verify: jest.fn() }), { virtual: true });
jest.mock('axios', () => ({ post: jest.fn() }), { virtual: true });

const mockDb = { collection: jest.fn() };
jest.mock('mongoose', () => ({ connection: { db: mockDb } }), { virtual: true });
jest.mock('../../../services/assessment-agent/src/services/n8nService', () => ({
  startSession: jest.fn(),
  submitAnswer: jest.fn(),
  runCode: jest.fn(),
}));
jest.mock('../../../services/assessment-agent/src/services/ragService', () => ({
  isEnabled: jest.fn(),
  retrieve: jest.fn(),
  ingestDocument: jest.fn(),
  listDocuments: jest.fn(),
  getDocument: jest.fn(),
  deleteDocument: jest.fn(),
  getStats: jest.fn(),
}));
jest.mock('../../../services/assessment-agent/src/services/mongoService', () => ({
  getFeedbackReport: jest.fn(),
}));

const jwt = require('jsonwebtoken');
const ragService = require('../../../services/assessment-agent/src/services/ragService');
const app = require('../../../services/assessment-agent/src/app');

const AUTH = { Authorization: 'Bearer fake-jwt-token' };

beforeEach(() => {
  jest.clearAllMocks();
  mockDb.collection.mockImplementation(() => ({}));
  jwt.verify.mockReturnValue({ student_id: 'STU-42', role: 'student' });
});

describe('POST /api/ame/rag/retrieve', () => {
  test('returns 400 when the query is missing', async () => {
    const res = await request(app).post('/api/ame/rag/retrieve').set(AUTH).send({});

    expect(res.status).toBe(400);
    expect(res.body.message).toBe('query is required');
  });

  test('returns the retrieval result with success:true', async () => {
    ragService.retrieve.mockResolvedValue({
      query: 'vector algebra',
      top_k: 2,
      retrieval: 'embedding',
      chunks: [
        { chunk_id: 'DOC_1_CHUNK_1', score: 0.92, content: 'Vector basics' },
        { chunk_id: 'DOC_1_CHUNK_2', score: 0.87, content: 'Cross products' },
      ],
    });

    const res = await request(app)
      .post('/api/ame/rag/retrieve')
      .set(AUTH)
      .send({ query: 'vector algebra', top_k: 2, threshold: 0.3 });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.chunks).toHaveLength(2);
    expect(ragService.retrieve).toHaveBeenCalledWith(
      mockDb,
      'vector algebra',
      expect.objectContaining({ top_k: 2 })
    );
  });
});

describe('GET /api/ame/rag/documents', () => {
  test('lists documents with pagination and query parsing', async () => {
    ragService.listDocuments.mockResolvedValue({
      documents: [{ document_id: 'DOC_1', title: 'Cheat sheet', chunk_count: 3 }],
      pagination: { page: 2, limit: 5, total: 7, pages: 2 },
    });

    const res = await request(app).get('/api/ame/rag/documents').set(AUTH).query({ page: '2', limit: '5' });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.documents).toHaveLength(1);
    expect(ragService.listDocuments).toHaveBeenCalledWith(mockDb, 2, 5);
  });
});

describe('POST /api/ame/rag/ingest', () => {
  test('ingests a document and returns a 200 summary', async () => {
    ragService.ingestDocument.mockResolvedValue({
      document_id: 'DOC_NEW',
      chunk_count: 4,
    });

    const res = await request(app)
      .post('/api/ame/rag/ingest')
      .set(AUTH)
      .send({ title: 'Linear Algebra', content: 'Some content about matrices.' });

    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      success: true,
      message: 'Document ingested into the knowledge base',
      data: { document_id: 'DOC_NEW', chunk_count: 4 },
    });
  });
});

describe('GET /api/ame/rag/stats', () => {
  test('returns knowledge base statistics', async () => {
    ragService.getStats.mockResolvedValue({
      enabled: true,
      documents: 2,
      chunks: 18,
      topics: ['Algebra', 'Calculus'],
    });

    const res = await request(app).get('/api/ame/rag/stats').set(AUTH);

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data.documents).toBe(2);
    expect(res.body.data.topics).toEqual(['Algebra', 'Calculus']);
  });
});