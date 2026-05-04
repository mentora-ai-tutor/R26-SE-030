const n8nService = require('../services/n8nService');
const mongoose = require('mongoose');

const startSession = async (req, res, next) => {
  try {
    const { mastery_profile } = req.body;

    if (!mastery_profile) {
      return res.status(400).json({
        success: false,
        message: 'mastery_profile is required',
      });
    }

    if (!mastery_profile.knowledge_gaps || !Array.isArray(mastery_profile.knowledge_gaps) || mastery_profile.knowledge_gaps.length === 0) {
      return res.status(400).json({
        success: false,
        message: 'knowledge_gaps must be a non-empty array',
      });
    }

    const payload = {
      student_id: req.user.student_id,
      learner_id: req.user.student_id,
      mastery_profile,
    };

    const result = await n8nService.startSession(payload);

    res.status(200).json(result);
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to start assessment session',
      error: error.message,
    });
  }
};

const submitAnswer = async (req, res, next) => {
  try {
    const { session_id, question_id, answer } = req.body;

    if (!session_id) {
      return res.status(400).json({
        success: false,
        message: 'session_id is required',
      });
    }

    if (!question_id) {
      return res.status(400).json({
        success: false,
        message: 'question_id is required',
      });
    }

    if (!answer) {
      return res.status(400).json({
        success: false,
        message: 'answer is required',
      });
    }

    const payload = {
      session_id,
      learner_id: req.user.student_id,
      question_id,
      answer,
    };

    const result = await n8nService.submitAnswer(payload);

    res.status(200).json(result);
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to submit answer',
      error: error.message,
    });
  }
};

const getSession = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const { sessionId } = req.params;
    const learnerId = req.user.student_id;

    let sessionState = await db.collection('ame_session_updates').findOne(
      { session_id: sessionId, learner_id: learnerId },
      { sort: { update_timestamp: -1 } }
    );

    if (!sessionState) {
      sessionState = await db.collection('ame_sessions').findOne({
        session_id: sessionId,
        learner_id: learnerId,
      });
    }

    if (!sessionState) {
      return res.status(404).json({
        success: false,
        message: 'Session not found',
      });
    }

    res.status(200).json({
      success: true,
      data: sessionState,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve session',
      error: error.message,
    });
  }
};

const getSessions = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const learnerId = req.user.student_id;

    const sessions = await db.collection('ame_sessions')
      .find({ learner_id: learnerId })
      .sort({ session_started_at: -1 })
      .toArray();

    res.status(200).json({
      success: true,
      data: sessions,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve sessions',
      error: error.message,
    });
  }
};

module.exports = {
  startSession,
  submitAnswer,
  getSession,
  getSessions,
};
