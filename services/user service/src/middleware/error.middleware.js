const logger = require('../utils/logger');

const errorHandler = (err, req, res, _next) => {
  let statusCode = err.statusCode || 500;
  let message = err.message || 'Internal server error';
  let code = err.code || 'INTERNAL_ERROR';

  if (err.name === 'ValidationError' && err.errors) {
    statusCode = 400;
    const validationMessages = Object.values(err.errors)
      .map((e) => e.message)
      .join(', ');
    message = validationMessages || 'Validation failed';
    code = 'VALIDATION_ERROR';
  }

  if (err.name === 'ValidationError' && err.message) {
    statusCode = 400;
    message = err.message;
    code = 'VALIDATION_ERROR';
  }

  if (err.name === 'CastError' && err.kind === 'ObjectId') {
    statusCode = 400;
    message = 'Invalid ID format';
    code = 'INVALID_ID';
  }

  if (err.code === 11000) {
    statusCode = 409;
    const field = Object.keys(err.keyValue || {})[0] || 'field';
    message = `${field.charAt(0).toUpperCase() + field.slice(1)} already exists`;
    code = 'DUPLICATE_KEY';
  }

  if (err.name === 'JsonWebTokenError') {
    statusCode = 401;
    message = 'Invalid token';
    code = 'INVALID_TOKEN';
  }

  if (err.name === 'TokenExpiredError') {
    statusCode = 401;
    message = 'Token expired';
    code = 'TOKEN_EXPIRED';
  }

  if (err.name === 'MulterError') {
    statusCode = 400;
    message = err.message;
    code = 'UPLOAD_ERROR';
  }

  logger.error(`Error: ${message}`, {
    statusCode,
    code,
    path: req.path,
    method: req.method,
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
  });

  const response = {
    success: false,
    error: message,
    code,
  };

  if (process.env.NODE_ENV === 'development' && err.stack) {
    response.stack = err.stack;
  }

  res.status(statusCode).json(response);
};

const notFoundHandler = (req, res) => {
  res.status(404).json({
    success: false,
    error: 'Route not found',
    code: 'NOT_FOUND',
    path: req.originalUrl,
  });
};

class AppError extends Error {
  constructor(message, statusCode, code = '') {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.isOperational = true;
    Error.captureStackTrace(this, this.constructor);
  }
}

module.exports = { errorHandler, notFoundHandler, AppError };
