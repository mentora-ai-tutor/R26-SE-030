const express = require('express');
const router = express.Router();
const materialController = require('../controllers/material.controller');
const { validateQuery } = require('../middleware/validate.middleware');
const { materialQuerySchema, paginationQuerySchema } = require('../utils/validationSchemas');

router.get('/:studentId', validateQuery(materialQuerySchema), materialController.getMaterialsByStudent);

router.get('/:studentId/topics', materialController.getTopics);

router.get('/:studentId/stats', materialController.getMaterialStats);

router.get('/:studentId/topic/:topicId', validateQuery(paginationQuerySchema), materialController.getMaterialsByTopic);

router.get('/item/:materialId', materialController.getMaterialById);

router.delete('/item/:materialId', materialController.deleteMaterial);

module.exports = router;