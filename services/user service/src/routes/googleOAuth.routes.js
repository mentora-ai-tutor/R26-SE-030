const express = require('express');
const controller = require('../controllers/googleOAuth.controller');

const router = express.Router();

// Public — the callback is hit by a top-level Google redirect, so no auth.
router.get('/start', controller.start);
router.get('/callback', controller.callback);
router.post('/exchange', controller.exchange);

module.exports = router;
