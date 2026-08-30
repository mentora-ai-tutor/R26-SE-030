const express = require('express');
const router = express.Router();
const conceptGraphController = require('../controllers/conceptGraph.controller');
const { validateQuery, validateBody } = require('../middleware/validate.middleware');
const { coverageQuerySchema, seedConceptGraphSchema } = require('../utils/validationSchemas');

router.get(
  '/coverage/:studentId',
  validateQuery(coverageQuerySchema),
  conceptGraphController.getCoverage
);

router.post(
  '/seed',
  validateBody(seedConceptGraphSchema),
  conceptGraphController.seedConceptGraph
);

module.exports = router;
