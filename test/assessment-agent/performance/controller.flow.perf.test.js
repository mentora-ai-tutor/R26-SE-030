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
const controller = require('../../../services/assessment-agent/src/controllers/assessmentController');

function makeRes() {
  const res = { statusCode: 200, body: null };
  res.status = jest.fn((code) => {
    res.statusCode = code;
    return res;
  });
  res.json = jest.fn((body) => {
    res.body = body;
  });
  return res;
}

describe('performance: mocked controller flow', () => {
  test('startSession round-trip completes well under 500ms', async () => {
    ragService.isEnabled.mockReturnValue(false);
    n8nService.startSession.mockResolvedValue({ success: true, session_id: 'S1' });

    const req = {
      user: { student_id: 'STU-42' },
      body: {
        mastery_profile: {
          knowledge_gaps: Array.from({ length: 10 }, (_, i) => ({ topic: `Topic-${i}` })),
        },
      },
    };
    const res = makeRes();
    const next = jest.fn();

    const started = Date.now();
    await controller.startSession(req, res, next);
    const elapsed = Date.now() - started;

    console.log(`[performance] startSession (10 knowledge gaps) completed in ${elapsed}ms`);
    expect(res.statusCode).toBe(200);
    expect(elapsed).toBeLessThan(500);
  });
});