require('./config/env');
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');
const config = require('./config/env');
const logger = require('./utils/logger');
const { errorHandler, notFoundHandler } = require('./middleware/error.middleware');
const { protect } = require('./middleware/auth.middleware');
const { internalOnly } = require('./middleware/internal.middleware');
const { requestId, requestTiming } = require('./middleware/request.middleware');
const { collectMetrics, getMetrics, getHealth, getAnalytics, getRecentActivity } = require('./middleware/metrics.middleware');

// Import routes
const authRoutes = require('./routes/auth.routes');
const studentRoutes = require('./routes/student.routes');
const internalRoutes = require('./routes/internal.routes');
const adminRoutes = require('./routes/admin.routes');
const githubRoutes = require('./routes/githubOAuth.routes');

const app = express();

// Request ID and timing middleware (first)
app.use(requestId);
app.use(requestTiming);

// Security middleware
app.use(helmet());

// CORS configuration
app.use(
  cors({
    origin: config.corsOrigin,
    credentials: true,
    methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization', 'X-Internal-Key', 'X-Request-ID'],
  })
);

// Body parsing
app.use(express.json({ limit: '1mb' }));
app.use(express.urlencoded({ extended: true, limit: '1mb' }));

// Request logging
app.use(
  morgan('combined', {
    stream: {
      write: (message) => logger.info(message.trim()),
    },
    skip: (req) => req.url === '/health' || req.url === '/metrics',
  })
);

// Metrics collection
app.use(collectMetrics);

// Rate limiting
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 20,
  message: {
    success: false,
    error: 'Too many requests. Please try again later.',
    code: 'RATE_LIMIT_EXCEEDED',
  },
  standardHeaders: true,
  legacyHeaders: false,
});

const apiLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: {
    success: false,
    error: 'Too many requests. Please try again later.',
    code: 'RATE_LIMIT_EXCEEDED',
  },
  standardHeaders: true,
  legacyHeaders: false,
});

// Health check (no auth required)
app.get('/health', getHealth);

// Metrics endpoint (internal only)
app.get('/metrics', getMetrics);

// Analytics endpoints (protected, admin only concept)
app.get('/analytics', protect, getAnalytics);
app.get('/analytics/recent', protect, getRecentActivity);

// Auth routes with rate limiting
app.use('/api/auth', authLimiter);
app.use('/api/auth', authRoutes);

// Protected routes
app.use('/api/students', protect, apiLimiter, studentRoutes);

// GitHub OAuth — protect is applied per-route so /oauth/callback stays public.
app.use('/api/github', apiLimiter, githubRoutes);

// Admin routes
app.use('/api/admin', protect, apiLimiter, adminRoutes);

// Internal service routes
app.use('/internal', internalOnly, internalRoutes);

// API v1 prefix (for versioning)
app.use('/v1/auth', authLimiter, authRoutes);
app.use('/v1/students', protect, apiLimiter, studentRoutes);
app.use('/v1/github', apiLimiter, githubRoutes);
app.use('/v1/admin', protect, apiLimiter, adminRoutes);

// 404 handler
app.use(notFoundHandler);

// Error handler
app.use(errorHandler);

module.exports = app;
