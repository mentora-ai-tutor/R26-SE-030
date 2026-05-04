const express = require('express');
const router = express.Router();
const progressController = require('../controllers/progress.controller');

router.get('/student/:studentId', progressController.getProgressByStudent);

router.get('/student/:studentId/stats', progressController.getProgressStats);

router.get('/material/:materialId', progressController.getProgressByMaterial);

router.put('/material/:materialId', progressController.updateProgress);

module.exports = router;
