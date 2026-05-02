const config = require('../config/env');
const logger = require('../utils/logger');

const validateWebhookSecret = (req, res, next) => {
  const secret = req.headers['x-webhook-secret'] || req.query.secret;

  if (!secret) {
    logger.warn('Webhook request missing secret', {
      path: req.path,
      ip: req.ip,
    });
    return res.status(401).json({
      success: false,
      error: 'Webhook secret is required',
      code: 'WEBHOOK_SECRET_MISSING',
    });
  }

  if (secret !== config.n8n.webhookSecret) {
    logger.warn('Invalid webhook secret', {
      path: req.path,
      ip: req.ip,
    });
    return res.status(403).json({
      success: false,
      error: 'Invalid webhook secret',
      code: 'WEBHOOK_SECRET_INVALID',
    });
  }

  logger.debug('Webhook secret validated', { path: req.path });
  next();
};

module.exports = { validateWebhookSecret };
