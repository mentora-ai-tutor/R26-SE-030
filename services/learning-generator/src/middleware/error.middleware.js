const ServiceError = require('../utils/ServiceError');
const logger = require('../utils/logger');

const errorMiddleware = (err, req, res, next) => {
  logger.error('Error caught by middleware', {
    error: err.message,
    stack: err.stack,
    path: req.path,
    method: req.method,
    code: err.code,
  });

  if (err instanceof ServiceError) {
    const response = {
      success: false,
      error: err.message,
      code: err.code,
    };

    if (err.fix) {
      response.fix = err.fix;
    }

    return res.status(err.statusCode).json(response);
  }

  if (err.name === 'ValidationError' && err.errors) {
    const details = Object.keys(err.errors).map((key) => ({
      field: key,
      message: err.errors[key].message,
    }));

    return res.status(400).json({
      success: false,
      error: 'Validation failed',
      code: 'MONGOOSE_VALIDATION_ERROR',
      details,
    });
  }

  if (err.name === 'ValidationError') {
    return res.status(400).json({
      success: false,
      error: err.message,
      code: 'VALIDATION_ERROR',
    });
  }

  if (err.name === 'CastError') {
    return res.status(400).json({
      success: false,
      error: `Invalid ${err.path}: ${err.value}`,
      code: 'CAST_ERROR',
    });
  }

  if (err.code === 11000) {
    const field = Object.keys(err.keyValue || {})[0] || 'field';
    return res.status(409).json({
      success: false,
      error: `Duplicate value for ${field}`,
      code: 'DUPLICATE_ERROR',
    });
  }

  if (err.type === 'entity.parse.failed') {
    return res.status(400).json({
      success: false,
      error: 'Invalid JSON in request body',
      code: 'JSON_PARSE_ERROR',
    });
  }

  if (err.statusCode) {
    return res.status(err.statusCode).json({
      success: false,
      error: err.message,
      code: err.code || 'HTTP_ERROR',
    });
  }

  return res.status(500).json({
    success: false,
    error: 'Internal server error',
    code: 'INTERNAL_ERROR',
  });
};

const notFoundMiddleware = (req, res) => {
  logger.warn('Route not found', {
    path: req.path,
    method: req.method,
  });

  return res.status(404).json({
    success: false,
    error: `Route ${req.method} ${req.path} not found`,
    code: 'NOT_FOUND',
  });
};

module.exports = {
  errorMiddleware,
  notFoundMiddleware,
};