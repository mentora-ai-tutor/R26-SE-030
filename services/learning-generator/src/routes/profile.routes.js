const express = require('express');
const router = express.Router();
const masteryController = require('../controllers/profile.controller');
const { validateBody, validateQuery } = require('../middleware/validate.middleware');
const { masterySubmitSchema, paginationQuerySchema } = require('../utils/validationSchemas');

router.post('/submit', validateBody(masterySubmitSchema), masteryController.submitMasteryProfile);

router.get('/:studentId', masteryController.getMasteryProfile);

router.get('/:studentId/history', validateQuery(paginationQuerySchema), masteryController.getMasteryHistory);

module.exports = router;
