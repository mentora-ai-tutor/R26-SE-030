const express = require('express');
const router = express.Router();
const studentController = require('../controllers/student.controller');
const { 
  validate, 
  updateProfileSchema, 
  updatePasswordSchema, 
  updateStatsSchema 
} = require('../middleware/validate.middleware');

router.get('/me', studentController.getMe);

router.put('/me', validate(updateProfileSchema), studentController.updateProfile);

router.put('/me/password', validate(updatePasswordSchema), studentController.updatePassword);

router.patch('/me/stats', validate(updateStatsSchema), studentController.updateStats);

router.get('/me/summary', studentController.getSummary);

module.exports = router;
