const AuditLog = require('../models/AuditLog');
const { parseDeviceInfo } = require('./deviceParser');
const logger = require('./logger');

/**
 * Log an audit event
 * @param {Object} options - Audit log options
 * @param {string} options.studentId - Student ID (optional)
 * @param {string} options.action - Action type
 * @param {string} options.status - SUCCESS, FAILED, or PENDING
 * @param {string} options.description - Description of the action
 * @param {Object} options.metadata - Additional metadata
 * @param {Object} options.req - Express request object
 * @param {string} options.requestId - Request ID
 */
const logAudit = async (options) => {
  try {
    const {
      studentId,
      action,
      status = 'SUCCESS',
      description,
      metadata = {},
      req,
      requestId,
    } = options;

    const auditData = {
      student: studentId,
      action,
      status,
      description,
      metadata,
      request_id: requestId,
    };

    if (req) {
      auditData.ip_address = req.ip || req.connection?.remoteAddress;
      auditData.user_agent = req.headers['user-agent'];

      const deviceInfo = parseDeviceInfo(req.headers['user-agent']);
      auditData.device_info = deviceInfo;
    }

    await AuditLog.create(auditData);
  } catch (error) {
    logger.error('Failed to create audit log:', error.message);
  }
};

/**
 * Log authentication events
 */
const logAuth = {
  register: (studentId, req, requestId, status = 'SUCCESS', description) =>
    logAudit({ studentId, action: 'REGISTER', status, description, req, requestId }),

  login: (studentId, req, requestId, status = 'SUCCESS', description) =>
    logAudit({ studentId, action: 'LOGIN', status, description, req, requestId }),

  loginFailed: (email, req, requestId, description) =>
    logAudit({ action: 'LOGIN_FAILED', status: 'FAILED', description: `${email}: ${description}`, req, requestId }),

  logout: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'LOGOUT', req, requestId }),

  passwordChange: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'PASSWORD_CHANGE', req, requestId }),

  passwordResetRequest: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'PASSWORD_RESET_REQUEST', req, requestId }),

  passwordResetComplete: (studentId, req, requestId, status = 'SUCCESS') =>
    logAudit({ studentId, action: 'PASSWORD_RESET_COMPLETE', status, req, requestId }),

  emailVerificationSent: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'EMAIL_VERIFICATION_SENT', req, requestId }),

  emailVerified: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'EMAIL_VERIFIED', req, requestId }),

  accountLocked: (studentId, req, requestId, reason) =>
    logAudit({ studentId, action: 'ACCOUNT_LOCKED', description: reason, req, requestId }),

  accountUnlocked: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'ACCOUNT_UNLOCKED', req, requestId }),

  refreshToken: (studentId, req, requestId, status = 'SUCCESS') =>
    logAudit({ studentId, action: 'REFRESH_TOKEN', status, req, requestId }),

  tokenVerified: (studentId, req, requestId) =>
    logAudit({ studentId, action: 'TOKEN_VERIFIED', req, requestId }),

  sessionRevoked: (studentId, req, requestId, metadata) =>
    logAudit({ studentId, action: 'SESSION_REVOKED', req, requestId, metadata }),

  adminAction: (studentId, req, requestId, description, metadata) =>
    logAudit({ studentId, action: 'ADMIN_ACTION', description, metadata, req, requestId }),
};

/**
 * Get recent audit logs for a student
 * @param {string} studentId - Student ID
 * @param {number} limit - Number of logs to return
 * @returns {Promise<Array>} Audit logs
 */
const getStudentAuditHistory = async (studentId, limit = 50) => {
  return AuditLog.find({ student: studentId })
    .sort({ createdAt: -1 })
    .limit(limit)
    .lean();
};

/**
 * Get suspicious activity (e.g., multiple failed logins)
 * @param {string} ip - IP address
 * @param {number} minutes - Time window in minutes
 * @returns {Promise<number>} Count of failed attempts
 */
const getFailedAttemptsFromIP = async (ip, minutes = 15) => {
  const since = new Date(Date.now() - minutes * 60 * 1000);

  return AuditLog.countDocuments({
    action: 'LOGIN_FAILED',
    ip_address: ip,
    createdAt: { $gte: since },
  });
};

module.exports = {
  logAudit,
  logAuth,
  getStudentAuditHistory,
  getFailedAttemptsFromIP,
};
