const express = require('express');
const router = express.Router();
const internalController = require('../controllers/internal.controller');
const { validate, verifyTokenSchema, updateStatsSchema } = require('../middleware/validate.middleware');

router.post('/auth/verify', validate(verifyTokenSchema), internalController.verifyToken);

router.get('/students/:studentId', internalController.getStudentById);

router.patch('/students/:studentId/stats', validate(updateStatsSchema), internalController.updateStudentStats);

module.exports = router;
