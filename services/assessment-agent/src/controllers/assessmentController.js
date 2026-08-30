const n8nService = require('../services/n8nService');
const mongoose = require('mongoose');
const ragService = require('../services/ragService');
const { getFeedbackReport } = require('../services/mongoService');

const attachRagContext = async (db, query, options = {}) => {
  if (!ragService.isEnabled()) return null;
  try {
    const result = await ragService.retrieve(db, query, options);
    if (!result.chunks || result.chunks.length === 0) return null;
    return result;
  } catch (error) {
    console.warn('[RAG] Context enrichment skipped:', error.message);
    return null;
  }
};

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

    let rag_context = null;
    try {
      if (ragService.isEnabled() && Array.isArray(mastery_profile.knowledge_gaps) && mastery_profile.knowledge_gaps.length > 0) {
        const db = mongoose.connection.db;
        const topics = mastery_profile.knowledge_gaps.map((gap) => gap.topic).filter(Boolean);

        const results = await Promise.all(
          topics.map((topic) => attachRagContext(db, topic, { top_k: 3 }))
        );

        const seen = new Set();
        const chunks = [];
        for (const result of results) {
          if (result && Array.isArray(result.chunks)) {
            for (const chunk of result.chunks) {
              if (!seen.has(chunk.chunk_id)) {
                seen.add(chunk.chunk_id);
                chunks.push(chunk);
              }
            }
          }
        }

        if (chunks.length > 0) {
          rag_context = { query: topics.join(', '), topics, chunks };
        }
      }
    } catch (error) {
      console.warn('[RAG] Failed to build rag_context for session start:', error.message);
    }

    if (rag_context) payload.rag_context = rag_context;

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

    let rag_context = null;
    try {
      if (ragService.isEnabled()) {
        const db = mongoose.connection.db;
        const questionDoc = await db.collection('ame_questions').findOne(
          { 'current_question.question_id': question_id },
          { projection: { current_question: 1, _id: 0 } }
        );
        const currentQuestion = questionDoc ? questionDoc.current_question : null;
        const topic = currentQuestion ? currentQuestion.topic : null;
        const questionText = currentQuestion ? currentQuestion.question_text : null;
        const query = [topic, questionText].filter(Boolean).join(' - ') || question_id;

        const result = await attachRagContext(db, query, { top_k: 3 });
        if (result && Array.isArray(result.chunks) && result.chunks.length > 0) {
          rag_context = { query, topic, chunks: result.chunks };
        }
      }
    } catch (error) {
      console.warn('[RAG] Failed to build rag_context for answer submission:', error.message);
    }

    if (rag_context) payload.rag_context = rag_context;

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

const runCode = async (req, res, next) => {
  try {
    const { session_id, question_id, code, stdin } = req.body;

    if (!code || !String(code).trim()) {
      return res.status(400).json({
        success: false,
        message: 'code is required',
      });
    }

    const payload = {
      session_id: session_id || null,
      question_id: question_id || null,
      learner_id: req.user.student_id,
      code,
      stdin: stdin || '',
    };

    const result = await n8nService.runCode(payload);

    res.status(200).json(result);
  } catch (error) {
    next({
      statusCode: 502,
      message: error.message || 'Code execution failed',
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
      { session_id: sessionId },
      { sort: { update_timestamp: -1 } }
    );

    if (!sessionState) {
      sessionState = await db.collection('ame_sessions').findOne({
        session_id: sessionId,
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

const getQuestionsByTopic = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const learnerId = req.user.student_id;
    const { topic } = req.query;

    // Build map of answered questions from this learner's session history
    const sessionUpdates = await db.collection('ame_session_updates')
      .find({ learner_id: learnerId })
      .sort({ update_timestamp: -1 })
      .toArray();

    const sessionHistoryMap = {};
    for (const update of sessionUpdates) {
      if (update.updated_session && update.updated_session.session_history) {
        for (const entry of update.updated_session.session_history) {
          sessionHistoryMap[entry.question_id] = entry;
        }
      }
    }

    const answeredIds = Object.keys(sessionHistoryMap);
    if (answeredIds.length === 0) {
      return res.status(200).json({ success: true, data: [] });
    }

    // Fetch only questions matching the learner's answered question IDs
    const questions = await db.collection('ame_questions')
      .find({ 'current_question.question_id': { $in: answeredIds } })
      .sort({ question_generated_at: 1 })
      .toArray();

    const formattedQuestions = [];
    let number = 1;
    for (const q of questions) {
      const currentQ = q.current_question;
      if (!currentQ) continue;

      if (topic && currentQ.topic !== topic) continue;

      const historyEntry = sessionHistoryMap[currentQ.question_id];
      if (!historyEntry) continue;

      const options = currentQ.options ? Object.entries(currentQ.options).map(([key, value]) => value) : [];
      const difficultyMap = { easy: 'Easy', medium: 'Medium', hard: 'Hard' };

      formattedQuestions.push({
        id: currentQ.question_id || `q-${number}`,
        number: number,
        question: currentQ.question_text,
        type: currentQ.question_type || 'mcq',
        code_snippet: currentQ.code_snippet,
        options: options,
        learner_answer: historyEntry.submitted_answer || 'Not answered',
        correct_answer: historyEntry.correct_answer || currentQ.correct_answer || '',
        is_correct: historyEntry.is_correct || false,
        explanation: currentQ.evaluation_criteria || '',
        topic: currentQ.topic,
        difficulty: difficultyMap[currentQ.difficulty] || 'Medium',
        bloom_level: currentQ.blooms_level || 1,
        time_spent: historyEntry.time_spent || 0,
        timestamp: new Date(q.question_generated_at || Date.now()).getTime(),
      });
      number++;
    }

    res.status(200).json({
      success: true,
      data: formattedQuestions,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve questions by topic',
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

const getFeedbackReportBySession = async (req, res, next) => {
  try {
    const db = mongoose.connection.db;
    const { sessionId } = req.params;
    const learnerId = req.user.student_id;

    const report = await getFeedbackReport(db, sessionId);

    if (!report) {
      return res.status(404).json({
        success: false,
        message: 'Feedback report not found for this session',
      });
    }

    if (report.learner_id !== learnerId) {
      return res.status(403).json({
        success: false,
        message: 'Unauthorized to view this report',
      });
    }

    res.status(200).json({
      success: true,
      data: report,
    });
  } catch (error) {
    next({
      statusCode: 500,
      message: 'Failed to retrieve feedback report',
      error: error.message,
    });
  }
};

module.exports = {
  startSession,
  submitAnswer,
  runCode,
  getSession,
  getSessions,
  getQuestionsByTopic,
  getFeedbackReportBySession,
};
