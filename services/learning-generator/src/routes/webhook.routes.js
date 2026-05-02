const express = require('express');
const router = express.Router();
const webhookController = require('../controllers/webhook.controller');
const { validateWebhookSecret } = require('../middleware/webhook.middleware');
const { validateBody } = require('../middleware/validate.middleware');
const { n8nWebhookSchema } = require('../utils/validationSchemas');

router.post('/material', validateWebhookSecret, validateBody(n8nWebhookSchema), webhookController.receiveMaterialCallback);

router.post('/material/batch', validateWebhookSecret, webhookController.receiveBatchCallback);

router.post('/job/status', validateWebhookSecret, webhookController.receiveJobStatusUpdate);

router.post('/profile', validateWebhookSecret, webhookController.handleProfileCallback);

module.exports = router;
