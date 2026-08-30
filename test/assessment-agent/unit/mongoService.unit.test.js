'use strict';

const mongoService = require('../../../services/assessment-agent/src/services/mongoService');

function findResult(arr) {
  return { toArray: jest.fn().mockResolvedValue(arr) };
}

function makeDb(collections) {
  return {
    collection: jest.fn((name) => {
      if (!collections[name]) collections[name] = {};
      return collections[name];
    }),
  };
}

describe('mongoService aggregation logic (no live DB)', () => {
  describe('getDashboardStats', () => {
    test('aggregates session, learner and mastery counters', async () => {
      const db = makeDb({
        ame_sessions: {
          countDocuments: jest.fn((q) =>
            Promise.resolve(q && q.session_status === 'active' ? 4 : 10)
          ),
          distinct: jest.fn().mockResolvedValue(['L1', 'L2', 'L3']),
        },
        ame_feedback_reports: {
          countDocuments: jest.fn().mockResolvedValue(7),
        },
        ame_questions: {
          countDocuments: jest.fn().mockResolvedValue(25),
        },
        ame_session_updates: {
          find: jest.fn(() =>
            findResult([
              { current_topic_mastery: 45.5 },
              { current_topic_mastery: 80 },
              { current_topic_mastery: null },
            ])
          ),
        },
      });

      const stats = await mongoService.getDashboardStats(db);

      expect(stats.total_sessions).toBe(10);
      expect(stats.active_sessions).toBe(4);
      expect(stats.completed_sessions).toBe(7);
      expect(stats.total_learners).toBe(3);
      expect(stats.total_questions_generated).toBe(25);
      expect(stats.average_mastery).toBe(62.75);
    });
  });

  describe('getMasteryDistribution', () => {
    test('buckets mastery values into the five fixed ranges', async () => {
      const db = makeDb({
        ame_session_updates: {
          find: jest.fn(() =>
            findResult([
              { current_topic_mastery: 10 },
              { current_topic_mastery: 30 },
              { current_topic_mastery: 50 },
              { current_topic_mastery: 70 },
              { current_topic_mastery: 84 },
              { current_topic_mastery: 90 },
            ])
          ),
        },
      });

      const distribution = await mongoService.getMasteryDistribution(db);

      expect(distribution).toEqual({
        '0-20': 1,
        '21-40': 1,
        '41-60': 1,
        '61-84': 2,
        '85-100': 1,
      });
    });
  });

  describe('getGradeDistribution', () => {
    test('counts reports only for known grade labels', async () => {
      const db = makeDb({
        ame_feedback_reports: {
          find: jest.fn(() =>
            findResult([
              { feedback_report: { overall_grade: 'Excellent' } },
              { feedback_report: { overall_grade: 'Excellent' } },
              { feedback_report: { overall_grade: 'Good' } },
              { feedback_report: { overall_grade: 'Unknown-Label' } },
            ])
          ),
        },
      });

      const distribution = await mongoService.getGradeDistribution(db);

      expect(distribution).toEqual({
        Excellent: 2,
        Good: 1,
        Satisfactory: 0,
        'Needs Improvement': 0,
        Poor: 0,
      });
    });
  });

  describe('getCommonMisconceptions', () => {
    test('ranks misconceptions by frequency and honours the limit', async () => {
      const db = makeDb({
        ame_feedback_reports: {
          find: jest.fn(() =>
            findResult([
              {
                feedback_report: {
                  misconceptions_to_address: ['confuses-X', 'mixes-Y'],
                },
              },
              {
                feedback_report: {
                  misconceptions_to_address: ['confuses-X'],
                },
              },
            ])
          ),
        },
      });

      const misconceptions = await mongoService.getCommonMisconceptions(db, 10);

      expect(misconceptions[0]).toEqual({ misconception: 'confuses-X', count: 2 });
      expect(misconceptions[1]).toEqual({ misconception: 'mixes-Y', count: 1 });
    });
  });

  describe('getMasteryAnalytics', () => {
    test('builds cohort heatmap and distribution from session updates', async () => {
      const db = makeDb({
        ame_session_updates: {
          toArray: jest.fn().mockResolvedValue([
            {
              updated_session: {
                topic: 'Algebra',
                current_difficulty: 'medium',
                topic_scores: { Algebra: 70, Calculus: 40 },
              },
            },
            {
              updated_session: {
                topic: 'Algebra',
                current_difficulty: 'hard',
                topic_scores: { Algebra: 90 },
              },
            },
          ]),
        },
        ame_questions: {
          find: jest.fn(() =>
            findResult([
              { current_question: { blooms_level: 3 } },
              { current_question: { blooms_level: 4 } },
            ])
          ),
        },
      });

      const analytics = await mongoService.getMasteryAnalytics(db);

      expect(analytics.cohort_mastery_heatmap).toEqual({ Algebra: 80, Calculus: 40 });
      expect(analytics.topic_distribution).toEqual({ Algebra: 2 });
      expect(analytics.difficulty_progression).toEqual({ medium: 1, hard: 1 });
      expect(analytics.blooms_distribution).toEqual({ 3: 1, 4: 1 });
    });
  });
});