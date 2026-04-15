const crypto = require('crypto');

const requestId = (req, res, next) => {
  req.requestId = req.headers['x-request-id'] || crypto.randomUUID();
  res.setHeader('x-request-id', req.requestId);
  next();
};

/**
 * Request timing middleware
 * Adds request start time and duration tracking
 */
const requestTiming = (req, res, next) => {
  req.startTime = Date.now();

  // Override res.end to capture timing
  const originalEnd = res.end;
  res.end = function (...args) {
    res.duration = Date.now() - req.startTime;
    originalEnd.apply(res, args);
  };

  next();
};

/**
 * Session ID middleware
 * Extracts or generates session ID for activity tracking
 */
const sessionId = (req, res, next) => {
  req.sessionId = req.headers['x-session-id'] || null;
  next();
};

module.exports = {
  requestId,
  requestTiming,
  sessionId,
};
