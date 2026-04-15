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

      const student = await Student.findById(decoded.id)
        .select('-password -refresh_token');

      if (!student) {
        return sendError(res, 'Student not found.', 401, 'STUDENT_NOT_FOUND');
      }

      if (student.is_deleted) {
        return sendError(res, 'Account has been deleted.', 401, 'ACCOUNT_DELETED');
      }

      if (!student.is_active) {
        return sendError(res, 'Account has been deactivated.', 403, 'ACCOUNT_DEACTIVATED');
      }

      req.student = student;
      req.token = token;

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
        const student = await Student.findById(decoded.id)
          .select('-password -refresh_token');

        if (student && student.is_active && !student.is_deleted) {
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

// Role-based access control
const requireRole = (...roles) => {
  return (req, res, next) => {
    if (!req.student) {
      return sendError(res, 'Authentication required', 401, 'AUTH_REQUIRED');
    }

    if (!roles.includes(req.student.role)) {
      return sendError(
        res,
        `Access denied. Required role: ${roles.join(' or ')}`,
        403,
        'INSUFFICIENT_PERMISSIONS'
      );
    }

    next();
  };
};

// Check if user owns resource or is admin
const requireOwnershipOrAdmin = (paramName = 'userId') => {
  return (req, res, next) => {
    if (!req.student) {
      return sendError(res, 'Authentication required', 401, 'AUTH_REQUIRED');
    }

    const resourceId = req.params[paramName];
    const isOwner = req.student._id.toString() === resourceId;
    const isAdmin = req.student.role === 'admin';

    if (!isOwner && !isAdmin) {
      return sendError(res, 'Access denied', 403, 'ACCESS_DENIED');
    }

    next();
  };
};

module.exports = { protect, optionalAuth, requireRole, requireOwnershipOrAdmin };
