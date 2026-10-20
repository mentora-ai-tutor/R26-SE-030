const express = require('express');
const { protect } = require('../middleware/auth.middleware');
const controller = require('../controllers/githubOAuth.controller');

const router = express.Router();

router.get('/oauth/start', protect, controller.start);
router.get('/oauth/callback', controller.callback);
router.get('/status', protect, controller.status);
router.post('/unlink', protect, controller.unlink);

module.exports = router;
