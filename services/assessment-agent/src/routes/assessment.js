const express = require('express');
const router = express.Router();
const { auth } = require('../middleware/auth');
const assessmentController = require('../controllers/assessmentController');

router.post('/start-session', auth, assessmentController.startSession);
router.post('/submit-answer', auth, assessmentController.submitAnswer);
router.get('/session/:sessionId', auth, assessmentController.getSession);
router.get('/sessions', auth, assessmentController.getSessions);
router.get('/questions', auth, assessmentController.getQuestionsByTopic);
router.get('/feedback-report/:sessionId', auth, assessmentController.getFeedbackReportBySession);

module.exports = router;
