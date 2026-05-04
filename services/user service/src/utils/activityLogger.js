const mongoose = require('mongoose');
const ActivityLog = require('../models/ActivityLog');
const { parseDeviceInfo } = require('./deviceParser');
const logger = require('./logger');

/**
 * Log user activity
 * @param {Object} options - Activity log options
 * @param {string} options.studentId - Student ID
 * @param {string} options.activityType - Type of activity
 * @param {string} options.description - Description
 * @param {Object} options.metadata - Additional metadata
 * @param {Object} options.req - Express request object
 */
const logActivity = async (options) => {
  try {
    const {
      studentId,
      activityType,
      description,
      metadata = {},
      req,
    } = options;

    const activityData = {
      student: studentId,
      activity_type: activityType,
      description,
      metadata,
    };

    if (req) {
      activityData.ip_address = req.ip || req.connection?.remoteAddress;
      activityData.user_agent = req.headers['user-agent'];
      activityData.session_id = req.sessionId || req.headers['x-session-id'];

      const deviceInfo = parseDeviceInfo(req.headers['user-agent']);
      activityData.device_type = deviceInfo.type;
      activityData.browser = deviceInfo.browser;
      activityData.os = deviceInfo.os;
    }

    await ActivityLog.create(activityData);
  } catch (error) {
    logger.error('Failed to create activity log:', error.message);
  }
};

/**
 * Predefined activity loggers
 */
const activity = {
  login: (studentId, req, description = 'User logged in') =>
    logActivity({ studentId, activityType: 'LOGIN', description, req }),

  logout: (studentId, req, description = 'User logged out') =>
    logActivity({ studentId, activityType: 'LOGOUT', description, req }),

  sessionExpired: (studentId, req, description = 'Session expired') =>
    logActivity({ studentId, activityType: 'SESSION_EXPIRED', description, req }),

  profileView: (studentId, req) =>
    logActivity({ studentId, activityType: 'PROFILE_VIEW', description: 'Viewed profile', req }),

  profileUpdate: (studentId, req, fields) =>
    logActivity({
      studentId,
      activityType: 'PROFILE_UPDATE',
      description: 'Updated profile',
      metadata: { fields },
      req,
    }),

  passwordChange: (studentId, req) =>
    logActivity({
      studentId,
      activityType: 'PASSWORD_CHANGE',
      description: 'Changed password',
      req,
    }),

  statsUpdate: (studentId, req, stats) =>
    logActivity({
      studentId,
      activityType: 'STATS_UPDATE',
      description: 'Updated stats',
      metadata: { stats },
      req,
    }),

  suspicious: (studentId, req, reason) =>
    logActivity({
      studentId,
      activityType: 'SUSPICIOUS_ACTIVITY',
      description: reason,
      req,
    }),

  apiCall: (studentId, req, endpoint) =>
    logActivity({
      studentId,
      activityType: 'API_CALL',
      description: `Called ${endpoint}`,
      metadata: { endpoint, method: req?.method },
      req,
    }),
};

/**
 * Get activity history for a student
 * @param {string} studentId - Student ID
 * @param {Object} options - Query options
 * @returns {Promise<Array>} Activity logs
 */
const getActivityHistory = async (studentId, options = {}) => {
  const { limit = 50, skip = 0, types = null, since = null } = options;

  const query = { student: studentId };

  if (types && types.length > 0) {
    query.activity_type = { $in: types };
  }

  if (since) {
    query.createdAt = { $gte: since };
  }

  return ActivityLog.find(query)
    .sort({ createdAt: -1 })
    .skip(skip)
    .limit(limit)
    .lean();
};

/**
 * Get activity summary for a student
 * @param {string} studentId - Student ID
 * @param {number} days - Number of days to look back
 * @returns {Promise<Object>} Activity summary
 */
const getActivitySummary = async (studentId, days = 7) => {
  const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

  const summary = await ActivityLog.aggregate([
    {
      $match: {
        student: new mongoose.Types.ObjectId(studentId),
        createdAt: { $gte: since },
      },
    },
    {
      $group: {
        _id: '$activity_type',
        count: { $sum: 1 },
      },
    },
  ]);

  return summary.reduce((acc, item) => {
    acc[item._id] = item.count;
    return acc;
  }, {});
};

module.exports = {
  logActivity,
  activity,
  getActivityHistory,
  getActivitySummary,
};
