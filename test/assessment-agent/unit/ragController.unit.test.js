'use strict';

const mockDb = { collection: jest.fn() };

jest.mock('mongoose', () => ({ connection: { db: mockDb } }), { virtual: true });
jest.mock('../../../services/assessment-agent/src/services/ragService', () => ({
  isEnabled: jest.fn(),
  retrieve: jest.fn(),
  ingestDocument: jest.fn(),
  listDocuments: jest.fn(),
  getDocument: jest.fn(),
  deleteDocument: jest.fn(),
  getStats: jest.fn(),
}));

const ragService = require('../../../services/assessment-agent/src/services/ragService');
const controller = require('../../../services/assessment-agent/src/controllers/ragController');

function makeRes() {
  const res = { statusCode: 200, sent: false, body: null };
  res.status = jest.fn((code) => {
    res.statusCode = code;
    return res;
  });
  res.json = jest.fn((body) => {
    res.body = body;
    res.sent = true;
  });
  return res;
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe('ragController response shaping', () => {
  describe('retrieve', () => {
    test('returns 400 when the query is missing or blank', async () => {
      for (const body of [{}, { query: '   ' }]) {
        const res = makeRes();
        const next = jest.fn();
        await controller.retrieve({ body }, res, next);
        expect(res.statusCode).toBe(400);
        expect(res.body.message).toBe('query is required');
        expect(ragService.retrieve).not.toHaveBeenCalled();
      }
    });

    test('returns the retrieval result wrapped in success:true', async () => {
      ragService.retrieve.mockResolvedValue({
        query: 'algebra',
        top_k: 2,
        retrieval: 'embedding',
        chunks: [{ chunk_id: 'c1', score: 0.9 }],
      });

      const req = { body: { query: 'algebra', top_k: 2, threshold: 0.3 } };
      const res = makeRes();
      const next = jest.fn();

      await controller.retrieve(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({
        success: true,
        data: {
          query: 'algebra',
          top_k: 2,
          retrieval: 'embedding',
          chunks: [{ chunk_id: 'c1', score: 0.9 }],
        },
      });
      expect(ragService.retrieve).toHaveBeenCalledWith(
        mockDb,
        'algebra',
        { topic: undefined, document_id: undefined, top_k: 2, threshold: 0.3 }
      );
    });

    test('forwards retrieval failures to the error middleware with 500', async () => {
      ragService.retrieve.mockRejectedValue(new Error('retrieval failed'));

      const res = makeRes();
      const next = jest.fn();

      await controller.retrieve({ body: { query: 'algebra' } }, res, next);

      expect(res.sent).toBe(false);
      expect(next).toHaveBeenCalledWith({
        statusCode: 500,
        message: 'Failed to retrieve context',
        error: 'retrieval failed',
      });
    });
  });

  describe('getDocument', () => {
    test('returns 404 when the document does not exist', async () => {
      ragService.getDocument.mockResolvedValue(null);

      const req = { params: { documentId: 'DOC_MISSING' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getDocument(req, res, next);

      expect(res.statusCode).toBe(404);
      expect(res.body.message).toBe('Knowledge base document not found');
    });

    test('returns the document with its chunks', async () => {
      ragService.getDocument.mockResolvedValue({
        document_id: 'DOC_1',
        title: 'Trig cheat sheet',
        chunks: [{ chunk_id: 'DOC_1_CHUNK_1' }],
      });

      const req = { params: { documentId: 'DOC_1' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getDocument(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body.data.document_id).toBe('DOC_1');
      expect(res.body.data.chunks).toHaveLength(1);
    });
  });

  describe('deleteDocument', () => {
    test('returns 404 when nothing was deleted', async () => {
      ragService.deleteDocument.mockResolvedValue({ deleted: false });

      const req = { params: { documentId: 'DOC_NONE' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.deleteDocument(req, res, next);

      expect(res.statusCode).toBe(404);
      expect(res.body.message).toBe('Knowledge base document not found');
    });

    test('returns 200 with a deleted summary', async () => {
      ragService.deleteDocument.mockResolvedValue({ deleted: true, removed_chunks: 12 });

      const req = { params: { documentId: 'DOC_1' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.deleteDocument(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({
        success: true,
        message: 'Knowledge base document deleted',
        data: { deleted: true, removed_chunks: 12 },
      });
    });
  });

  describe('listDocuments', () => {
    test('defaults pagination and wraps the result', async () => {
      ragService.listDocuments.mockResolvedValue({
        documents: [],
        pagination: { page: 1, limit: 20, total: 0, pages: 0 },
      });

      const req = { query: {} };
      const res = makeRes();
      const next = jest.fn();

      await controller.listDocuments(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body.success).toBe(true);
      expect(ragService.listDocuments).toHaveBeenCalledWith(mockDb, 1, 20);
    });
  });

  describe('getStats', () => {
    test('returns knowledge base stats', async () => {
      ragService.getStats.mockResolvedValue({ documents: 3, chunks: 40, topics: ['Algebra'] });

      const req = {};
      const res = makeRes();
      const next = jest.fn();

      await controller.getStats(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({ success: true, data: { documents: 3, chunks: 40, topics: ['Algebra'] } });
    });
  });
});