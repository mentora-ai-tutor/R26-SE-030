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
const n8nService = require('../../../services/assessment-agent/src/services/n8nService');
const ragService = require('../../../services/assessment-agent/src/services/ragService');
const app = require('../../../services/assessment-agent/src/app');

const collectionStubs = {};

function setCollection(name, stub) {
  collectionStubs[name] = stub;
  mockDb.collection.mockImplementation((n) => collectionStubs[n] || {});
}

const AUTH = { Authorization: 'Bearer fake-jwt-token' };

beforeEach(() => {
  jest.clearAllMocks();
  Object.keys(collectionStubs).forEach((k) => delete collectionStubs[k]);
  mockDb.collection.mockImplementation((n) => collectionStubs[n] || {});
  jwt.verify.mockReturnValue({ student_id: 'STU-42', role: 'student' });
  ragService.isEnabled.mockReturnValue(false);
});

describe('GET /health', () => {
  test('reports service health', async () => {
    const res = await request(app).get('/health');
    expect(res.status).toBe(200);
    expect(res.body.status).toBe('ok');
    expect(res.body.service).toBe('AME Backend');
  });
});

describe('POST /api/ame/start-session', () => {
  test('returns 401 when no bearer token is provided', async () => {
    const res = await request(app)
      .post('/api/ame/start-session')
      .send({ mastery_profile: { knowledge_gaps: [{ topic: 'Algebra' }] } });

    expect(res.status).toBe(401);
    expect(res.body.message).toBe('No token provided');
    expect(jwt.verify).not.toHaveBeenCalled();
  });

  test('returns 401 when the token is invalid', async () => {
    jwt.verify.mockImplementation(() => {
      throw new Error('bad token');
    });

    const res = await request(app)
      .post('/api/ame/start-session')
      .set(AUTH)
      .send({ mastery_profile: { knowledge_gaps: [{ topic: 'Algebra' }] } });

    expect(res.status).toBe(401);
    expect(res.body.message).toBe('Invalid token');
  });

  test('forwards the authenticated learners payload to the n8n service', async () => {
    n8nService.startSession.mockResolvedValue({ success: true, session_id: 'S1' });

    const res = await request(app)
      .post('/api/ame/start-session')
      .set(AUTH)
      .send({
        mastery_profile: {
          overall_skill_level: 'intermediate',
          knowledge_gaps: [{ topic: 'Algebra' }, { topic: 'Calculus' }],
        },
      });

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true, session_id: 'S1' });

    const payload = n8nService.startSession.mock.calls[0][0];
    expect(payload.learner_id).toBe('STU-42');
    expect(payload.mastery_profile.knowledge_gaps).toHaveLength(2);
  });

  test('returns 400 when mastery_profile validation fails', async () => {
    const res = await request(app)
      .post('/api/ame/start-session')
      .set(AUTH)
      .send({ mastery_profile: { knowledge_gaps: [] } });

    expect(res.status).toBe(400);
    expect(res.body.success).toBe(false);
    expect(res.body.message).toBe('knowledge_gaps must be a non-empty array');
    expect(n8nService.startSession).not.toHaveBeenCalled();
  });
});

describe('GET /api/ame/session/:sessionId', () => {
  test('returns 404 when the session does not exist in either collection', async () => {
    setCollection('ame_session_updates', { findOne: jest.fn().mockResolvedValue(null) });
    setCollection('ame_sessions', { findOne: jest.fn().mockResolvedValue(null) });

    const res = await request(app).get('/api/ame/session/S-NOPE').set(AUTH);

    expect(res.status).toBe(404);
    expect(res.body.message).toBe('Session not found');
  });

  test('returns the session state from the sessions collection', async () => {
    const doc = { session_id: 'S1', session_status: 'active' };
    setCollection('ame_session_updates', { findOne: jest.fn().mockResolvedValue(null) });
    setCollection('ame_sessions', { findOne: jest.fn().mockResolvedValue(doc) });

    const res = await request(app).get('/api/ame/session/S1').set(AUTH);

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ success: true, data: doc });
  });
});

describe('misc routes', () => {
  test('404 handler reports unknown routes', async () => {
    const res = await request(app).get('/api/ame/does-not-exist').set(AUTH);
    expect(res.status).toBe(404);
    expect(res.body.success).toBe(false);
  });
});