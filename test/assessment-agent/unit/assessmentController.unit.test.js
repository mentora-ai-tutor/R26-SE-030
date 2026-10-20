'use strict';

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
}));
jest.mock('../../../services/assessment-agent/src/services/mongoService', () => ({
  getFeedbackReport: jest.fn(),
}));

const n8nService = require('../../../services/assessment-agent/src/services/n8nService');
const ragService = require('../../../services/assessment-agent/src/services/ragService');
const mongoService = require('../../../services/assessment-agent/src/services/mongoService');
const controller = require('../../../services/assessment-agent/src/controllers/assessmentController');

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

const collectionStubs = {};

function setCollection(name, stub) {
  collectionStubs[name] = stub;
  mockDb.collection.mockImplementation((n) => collectionStubs[n] || {});
}

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(collectionStubs).forEach((k) => delete collectionStubs[k]);
  mockDb.collection.mockImplementation((n) => collectionStubs[n] || {});
});

describe('assessmentController response shaping', () => {
  describe('startSession', () => {
    const baseReq = () => ({
      user: { student_id: 'STU-42' },
      body: {
        mastery_profile: {
          overall_skill_level: 'intermediate',
          knowledge_gaps: [{ topic: 'Algebra' }],
        },
      },
    });

    test('returns 400 when mastery_profile is missing', async () => {
      const req = baseReq();
      req.body = {};
      const res = makeRes();
      const next = jest.fn();

      await controller.startSession(req, res, next);

      expect(res.statusCode).toBe(400);
      expect(res.body).toEqual({ success: false, message: 'mastery_profile is required' });
      expect(n8nService.startSession).not.toHaveBeenCalled();
    });

    test('returns 400 when knowledge_gaps is not a non-empty array', async () => {
      const req = baseReq();
      req.body = { mastery_profile: { knowledge_gaps: [] } };
      const res = makeRes();
      const next = jest.fn();

      await controller.startSession(req, res, next);

      expect(res.statusCode).toBe(400);
      expect(res.body.message).toBe('knowledge_gaps must be a non-empty array');
    });

    test('forwards the enriched payload to n8n when RAG is disabled', async () => {
      ragService.isEnabled.mockReturnValue(false);
      n8nService.startSession.mockResolvedValue({ success: true, session_id: 'S1' });

      const res = makeRes();
      const next = jest.fn();

      await controller.startSession(baseReq(), res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({ success: true, session_id: 'S1' });
      const payload = n8nService.startSession.mock.calls[0][0];
      expect(payload.student_id).toBe('STU-42');
      expect(payload.learner_id).toBe('STU-42');
      expect(payload.mastery_profile.knowledge_gaps).toEqual([{ topic: 'Algebra' }]);
      expect(payload.rag_context).toBeUndefined();
    });

    test('deduplicates RAG chunks and attaches rag_context when enabled', async () => {
      ragService.isEnabled.mockReturnValue(true);
      ragService.retrieve.mockResolvedValue({
        query: 'Algebra',
        chunks: [
          { chunk_id: 'c1', content: 'first' },
          { chunk_id: 'c1', content: 'first' },
          { chunk_id: 'c2', content: 'second' },
        ],
      });
      n8nService.startSession.mockResolvedValue({ success: true });

      const req = baseReq();
      req.body.mastery_profile.knowledge_gaps = [{ topic: 'Algebra' }, { topic: 'Calculus' }];

      const res = makeRes();
      const next = jest.fn();

      await controller.startSession(req, res, next);

      const payload = n8nService.startSession.mock.calls[0][0];
      expect(payload.rag_context.chunks).toEqual([
        { chunk_id: 'c1', content: 'first' },
        { chunk_id: 'c2', content: 'second' },
      ]);
      expect(payload.rag_context.topics).toEqual(['Algebra', 'Calculus']);
      expect(res.statusCode).toBe(200);
    });

    test('delegates n8n failures to the error middleware with 500', async () => {
      ragService.isEnabled.mockReturnValue(false);
      n8nService.startSession.mockRejectedValue(new Error('workflow exploded'));

      const res = makeRes();
      const next = jest.fn();

      await controller.startSession(baseReq(), res, next);

      expect(res.sent).toBe(false);
      expect(next).toHaveBeenCalledWith({
        statusCode: 500,
        message: 'Failed to start assessment session',
        error: 'workflow exploded',
      });
    });
  });

  describe('submitAnswer', () => {
    test('returns 400 when session_id is missing', async () => {
      const req = {
        user: { student_id: 'STU-42' },
        body: { question_id: 'q1', answer: 'A' },
      };
      const res = makeRes();
      const next = jest.fn();

      await controller.submitAnswer(req, res, next);

      expect(res.statusCode).toBe(400);
      expect(res.body.message).toBe('session_id is required');
    });

    test('builds rag_context from the current question when RAG is enabled', async () => {
      ragService.isEnabled.mockReturnValue(true);
      ragService.retrieve.mockResolvedValue({
        query: 'Algebra - What is X?',
        chunks: [{ chunk_id: 'c9', content: 'context' }],
      });
      setCollection('ame_questions', {
        findOne: jest.fn().mockResolvedValue({
          current_question: {
            question_id: 'q1',
            topic: 'Algebra',
            question_text: 'What is X?',
          },
        }),
      });
      n8nService.submitAnswer.mockResolvedValue({ success: true, graded: true });

      const req = {
        user: { student_id: 'STU-42' },
        body: { session_id: 'S1', question_id: 'q1', answer: 'A' },
      };
      const res = makeRes();
      const next = jest.fn();

      await controller.submitAnswer(req, res, next);

      const payload = n8nService.submitAnswer.mock.calls[0][0];
      expect(payload.learner_id).toBe('STU-42');
      expect(payload.rag_context.query).toContain('Algebra');
      expect(payload.rag_context.chunks).toHaveLength(1);
      expect(res.statusCode).toBe(200);
    });
  });

  describe('getSession', () => {
    test('returns 404 when no session document exists', async () => {
      setCollection('ame_session_updates', { findOne: jest.fn().mockResolvedValue(null) });
      setCollection('ame_sessions', { findOne: jest.fn().mockResolvedValue(null) });

      const req = { params: { sessionId: 'S-NOPE' }, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getSession(req, res, next);

      expect(res.statusCode).toBe(404);
      expect(res.body.message).toBe('Session not found');
    });

    test('returns the session document with success true', async () => {
      const doc = { session_id: 'S1', session_status: 'active' };
      setCollection('ame_session_updates', { findOne: jest.fn().mockResolvedValue(null) });
      setCollection('ame_sessions', { findOne: jest.fn().mockResolvedValue(doc) });

      const req = { params: { sessionId: 'S1' }, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getSession(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({ success: true, data: doc });
    });
  });

  describe('getQuestionsByTopic', () => {
    const sessionUpdates = [
      {
        learner_id: 'STU-42',
        updated_session: {
          session_history: [
            {
              question_id: 'q1',
              submitted_answer: 'Beta',
              correct_answer: 'Beta',
              is_correct: true,
              time_spent: 118,
            },
          ],
        },
      },
    ];

    const questions = [
      {
        question_generated_at: new Date('2024-01-01T00:00:00Z').toISOString(),
        current_question: {
          question_id: 'q1',
          question_text: 'Pick the best option',
          question_type: 'mcq',
          code_snippet: null,
          options: { A: 'Alpha', B: 'Beta', C: 'Gamma' },
          correct_answer: 'Beta',
          difficulty: 'hard',
          blooms_level: 3,
          evaluation_criteria: 'Reasoning',
          topic: 'Algebra',
        },
      },
    ];

    function setUp(findResults) {
      setCollection('ame_session_updates', {
        find: jest.fn(() => ({ sort: jest.fn(() => ({ toArray: jest.fn().mockResolvedValue(findResults.updates) })) })),
      });
      setCollection('ame_questions', {
        find: jest.fn(() => ({ sort: jest.fn(() => ({ toArray: jest.fn().mockResolvedValue(findResults.questions) })) })),
      });
    }

    test('returns an empty list when the learner has no answered questions', async () => {
      setUp({ updates: [], questions: [] });
      const req = { query: {}, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getQuestionsByTopic(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({ success: true, data: [] });
    });

    test('shapes answered questions into the learner-facing format', async () => {
      setUp({ updates: sessionUpdates, questions });
      const req = { query: {}, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getQuestionsByTopic(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body.success).toBe(true);
      const formatted = res.body.data;
      expect(formatted).toHaveLength(1);
      expect(formatted[0]).toMatchObject({
        id: 'q1',
        number: 1,
        question: 'Pick the best option',
        type: 'mcq',
        options: ['Alpha', 'Beta', 'Gamma'],
        learner_answer: 'Beta',
        correct_answer: 'Beta',
        is_correct: true,
        topic: 'Algebra',
        difficulty: 'Hard',
        bloom_level: 3,
        time_spent: 118,
      });
    });

    test('filters questions by topic when a query param is supplied', async () => {
      setUp({ updates: sessionUpdates, questions });
      const req = { query: { topic: 'Trigonometry' }, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getQuestionsByTopic(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body.data).toEqual([]);
    });
  });

  describe('getFeedbackReportBySession', () => {
    test('rejects a report belonging to another learner with 403', async () => {
      mongoService.getFeedbackReport.mockResolvedValue({
        learner_id: 'STU-OTHER',
        feedback_report: {},
      });

      const req = { params: { sessionId: 'S1' }, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getFeedbackReportBySession(req, res, next);

      expect(res.statusCode).toBe(403);
      expect(res.body.message).toBe('Unauthorized to view this report');
    });

    test('returns the report when it belongs to the requesting learner', async () => {
      const report = { learner_id: 'STU-42', feedback_report: { overall_grade: 'Good' } };
      mongoService.getFeedbackReport.mockResolvedValue(report);

      const req = { params: { sessionId: 'S1' }, user: { student_id: 'STU-42' } };
      const res = makeRes();
      const next = jest.fn();

      await controller.getFeedbackReportBySession(req, res, next);

      expect(res.statusCode).toBe(200);
      expect(res.body).toEqual({ success: true, data: report });
    });
  });
});