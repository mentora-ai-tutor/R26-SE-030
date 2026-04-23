const { Student, AuditLog, ActivityLog } = require('../models');
const { sendSuccess } = require('../utils/apiResponse');

// In-memory metrics store (replace with Redis in production)
const metrics = {
  requests: 0,
  responses: 0,
  errors: 0,
  responseTime: [],
  byRoute: {},
  byStatus: {},
  startTime: Date.now(),
};

/**
 * Metrics collection middleware
 * Tracks request/response metrics
 */
const collectMetrics = (req, res, next) => {
  metrics.requests++;

  const route = `${req.method} ${req.route?.path || req.path}`;
  if (!metrics.byRoute[route]) {
    metrics.byRoute[route] = { count: 0, errors: 0, duration: [] };
  }
  metrics.byRoute[route].count++;

  const startTime = Date.now();

  res.on('finish', () => {
    const duration = Date.now() - startTime;
    metrics.responses++;
    metrics.responseTime.push(duration);

    // Keep only last 1000 response times
    if (metrics.responseTime.length > 1000) {
      metrics.responseTime.shift();
    }

    metrics.byRoute[route].duration.push(duration);
    if (metrics.byRoute[route].duration.length > 100) {
      metrics.byRoute[route].duration.shift();
    }

    const status = res.statusCode.toString();
    metrics.byStatus[status] = (metrics.byStatus[status] || 0) + 1;

    if (res.statusCode >= 400) {
      metrics.errors++;
      metrics.byRoute[route].errors++;
    }
  });

  next();
};

/**
 * Calculate average from array
 */
const calculateAverage = (arr) => {
  if (arr.length === 0) return 0;
  return arr.reduce((a, b) => a + b, 0) / arr.length;
};

/**
 * Calculate percentile
 */
const calculatePercentile = (arr, percentile) => {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const index = Math.ceil((percentile / 100) * sorted.length) - 1;
  return sorted[Math.max(0, index)];
};

/**
 * Get metrics endpoint handler
 */
const getMetrics = async (req, res, next) => {
  try {
    const uptime = Date.now() - metrics.startTime;

    const responseMetrics = {
      avg: Math.round(calculateAverage(metrics.responseTime)),
      p50: calculatePercentile(metrics.responseTime, 50),
      p95: calculatePercentile(metrics.responseTime, 95),
      p99: calculatePercentile(metrics.responseTime, 99),
    };

    const routeMetrics = {};
    for (const [route, data] of Object.entries(metrics.byRoute)) {
      routeMetrics[route] = {
        count: data.count,
        errors: data.errors,
        avg_duration: Math.round(calculateAverage(data.duration)),
        error_rate: ((data.errors / data.count) * 100).toFixed(2) + '%',
      };
    }

    const stats = {
      uptime: Math.floor(uptime / 1000), // seconds
      requests: {
        total: metrics.requests,
        responses: metrics.responses,
        errors: metrics.errors,
        error_rate: metrics.requests > 0 ? ((metrics.errors / metrics.requests) * 100).toFixed(2) + '%' : '0%',
      },
      response_time: responseMetrics,
      by_status: metrics.byStatus,
      by_route: routeMetrics,
    };

    return sendSuccess(res, stats);
  } catch (error) {
    next(error);
  }
};

/**
 * Get health check with detailed status
 */
const getHealth = async (req, res, next) => {
  try {
    const { mongoose } = require('mongoose');

    const health = {
      service: 'user-service',
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      version: process.env.npm_package_version || '1.0.0',
      environment: process.env.NODE_ENV,
      database: {
        status: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected',
        name: mongoose.connection.name,
        host: mongoose.connection.host,
      },
      memory: {
        used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) + 'MB',
        total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024) + 'MB',
      },
    };

    // Check if database is connected
    if (mongoose.connection.readyState !== 1) {
      health.status = 'error';
      health.database.status = 'disconnected';
      return res.status(503).json(health);
    }

    res.json(health);
  } catch (error) {
    next(error);
  }
};

/**
 * Get analytics data
 */
const getAnalytics = async (req, res, next) => {
  try {
    const { days = 7 } = req.query;
    const since = new Date(Date.now() - parseInt(days) * 24 * 60 * 60 * 1000);

    const [
      totalUsers,
      activeUsers,
      newUsers,
      logins,
      registrations,
      activityByDay,
      topActions,
    ] = await Promise.all([
      Student.countDocuments({ is_deleted: false }),
      Student.countDocuments({ is_deleted: false, is_active: true }),
      Student.countDocuments({ is_deleted: false, createdAt: { $gte: since } }),
      AuditLog.countDocuments({ action: 'LOGIN', createdAt: { $gte: since } }),
      AuditLog.countDocuments({ action: 'REGISTER', createdAt: { $gte: since } }),
      ActivityLog.aggregate([
        { $match: { createdAt: { $gte: since } } },
        {
          $group: {
            _id: { $dateToString: { format: '%Y-%m-%d', date: '$createdAt' } },
            count: { $sum: 1 },
          },
        },
        { $sort: { _id: 1 } },
      ]),
      ActivityLog.aggregate([
        { $match: { createdAt: { $gte: since } } },
        { $group: { _id: '$activity_type', count: { $sum: 1 } } },
        { $sort: { count: -1 } },
        { $limit: 10 },
      ]),
    ]);

    return sendSuccess(res, {
      period: `${days} days`,
      users: {
        total: totalUsers,
        active: activeUsers,
        new: newUsers,
      },
      auth: {
        logins,
        registrations,
      },
      activity_by_day: activityByDay,
      top_actions: topActions.map((a) => ({
        action: a._id,
        count: a.count,
      })),
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Get recent activity
 */
const getRecentActivity = async (req, res, next) => {
  try {
    const { limit = 20 } = req.query;

    const [recentLogins, recentRegistrations, recentErrors] = await Promise.all([
      AuditLog.find({ action: 'LOGIN' })
        .sort({ createdAt: -1 })
        .limit(parseInt(limit))
        .populate('student', 'name email student_id')
        .lean(),
      AuditLog.find({ action: 'REGISTER' })
        .sort({ createdAt: -1 })
        .limit(parseInt(limit))
        .populate('student', 'name email student_id')
        .lean(),
      AuditLog.find({ status: 'FAILED' })
        .sort({ createdAt: -1 })
        .limit(parseInt(limit))
        .populate('student', 'name email student_id')
        .lean(),
    ]);

    return sendSuccess(res, {
      recent_logins: recentLogins,
      recent_registrations: recentRegistrations,
      recent_errors: recentErrors,
    });
  } catch (error) {
    next(error);
  }
};

module.exports = {
  collectMetrics,
  getMetrics,
  getHealth,
  getAnalytics,
  getRecentActivity,
};
