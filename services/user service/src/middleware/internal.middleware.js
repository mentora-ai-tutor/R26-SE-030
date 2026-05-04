const config = require('../config/env');
const { sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');

const internalOnly = (req, res, next) => {
  const internalKey = req.headers['x-internal-key'];

  if (!internalKey) {
    logger.warn('Internal endpoint accessed without X-Internal-Key header');
    return sendError(res, 'Forbidden: internal endpoint', 403, 'FORBIDDEN');
  }

  if (internalKey !== config.internalServiceKey) {
    logger.warn('Internal endpoint accessed with invalid X-Internal-Key');
    return sendError(res, 'Forbidden: internal endpoint', 403, 'FORBIDDEN');
  }

  next();
};

module.exports = { internalOnly };
