const userServiceClient = require('../services/userService.client');
const ServiceError = require('../utils/ServiceError');
const logger = require('../utils/logger');

const protect = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      logger.warn('Missing or invalid authorization header', {
        path: req.path,
        ip: req.ip,
      });
      return res.status(401).json({
        success: false,
        error: 'Authorization token missing or invalid',
        code: 'AUTH_MISSING',
      });
    }

    const token = authHeader.substring(7);

    if (!token || token.trim() === '') {
      logger.warn('Empty token provided', { path: req.path });
      return res.status(401).json({
        success: false,
        error: 'Authorization token is empty',
        code: 'AUTH_EMPTY',
      });
    }

    const verificationResult = await userServiceClient.verifyToken(token);

    if (!verificationResult.valid) {
      logger.warn('Token verification failed', {
        path: req.path,
        error: verificationResult.error,
      });
      return res.status(401).json({
        success: false,
        error: verificationResult.error || 'Invalid token',
        code: 'AUTH_INVALID',
      });
    }

    req.student = verificationResult.student;

    logger.debug('Request authenticated', {
      student_id: req.student.id,
      path: req.path,
      method: req.method,
    });

    next();
  } catch (error) {
    if (error instanceof ServiceError) {
      if (error.code === 'USER_SERVICE_OFFLINE') {
        logger.error('User Service unavailable during authentication', {
          error: error.message,
          path: req.path,
        });
        return res.status(503).json({
          success: false,
          error: 'Authentication service unavailable',
          code: error.code,
          fix: 'User Service is offline. Start mentora-user-service.',
        });
      }

      return res.status(error.statusCode).json({
        success: false,
        error: error.message,
        code: error.code,
      });
    }

    logger.error('Unexpected authentication error', {
      error: error.message,
      path: req.path,
    });
    return res.status(500).json({
      success: false,
      error: 'Internal server error during authentication',
      code: 'AUTH_ERROR',
    });
  }
};

module.exports = { protect };