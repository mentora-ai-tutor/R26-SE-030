const express = require('express');
const router = express.Router();
const agentController = require('../controllers/agent.controller');
const { validateQuery } = require('../middleware/validate.middleware');
const { agentQuerySchema } = require('../utils/validationSchemas');

router.get('/logs/:studentId', validateQuery(agentQuerySchema), agentController.getAgentLogs);

router.get('/jobs/:jobId', agentController.getJobStatus);

router.post('/jobs/:jobId/complete', agentController.completeJob);

router.get('/jobs/student/:studentId', agentController.getJobsByStudent);

router.get('/stats/global', agentController.getGlobalStats);

router.get('/health', agentController.checkHealth);

router.post('/retry/:materialId', agentController.retryMaterialGeneration);

module.exports = router;