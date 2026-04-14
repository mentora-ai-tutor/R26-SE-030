const jwt = require('jsonwebtoken');
const config = require('../config/env');
const Student = require('../models/Student');
const { sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');

const protect = async (req, res, next) => {
  try {
    let token;

    if (
      req.headers.authorization &&
      req.headers.authorization.startsWith('Bearer')
    ) {
      token = req.headers.authorization.split(' ')[1];
    }

    if (!token) {
      return sendError(res, 'Access denied. No token provided.', 401, 'NO_TOKEN');
    }

    try {
      const decoded = jwt.verify(token, config.jwt.secret);

      const student = await Student.findById(decoded.id).select('-password -refresh_token');

      if (!student) {
        return sendError(res, 'Student not found.', 401, 'STUDENT_NOT_FOUND');
      }

      if (!student.is_active) {
        return sendError(res, 'Account has been deactivated.', 403, 'ACCOUNT_DEACTIVATED');
      }

      req.student = student;

      Student.findByIdAndUpdate(
        decoded.id,
        { last_active: new Date() },
        { validateBeforeSave: false }
      ).catch((err) => {
        logger.warn('Failed to update last_active:', err.message);
      });

      next();
    } catch (jwtError) {
      if (jwtError.name === 'TokenExpiredError') {
        return sendError(res, 'Token expired.', 401, 'TOKEN_EXPIRED');
      }
      if (jwtError.name === 'JsonWebTokenError') {
        return sendError(res, 'Invalid token.', 401, 'INVALID_TOKEN');
      }
      throw jwtError;
    }
  } catch (error) {
    logger.error('Auth middleware error:', error.message);
    return sendError(res, 'Authentication failed.', 401, 'AUTH_FAILED');
  }
};

const optionalAuth = async (req, res, next) => {
  try {
    let token;

    if (
      req.headers.authorization &&
      req.headers.authorization.startsWith('Bearer')
    ) {
      token = req.headers.authorization.split(' ')[1];
    }

    if (token) {
      try {
        const decoded = jwt.verify(token, config.jwt.secret);
        const student = await Student.findById(decoded.id).select('-password -refresh_token');
        
        if (student && student.is_active) {
          req.student = student;
        }
      } catch (jwtError) {
        logger.debug('Optional auth token invalid:', jwtError.message);
      }
    }

    next();
  } catch (error) {
    next();
  }
};

module.exports = { protect, optionalAuth };
