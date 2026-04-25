const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const expressRateLimit = require('express-rate-limit');
const morgan = require('morgan');
const config = require('./config/env');
const logger = require('./utils/logger').stream;
const { protect } = require('./middleware/auth.middleware');
const { errorMiddleware, notFoundMiddleware } = require('./middleware/error.middleware');
const masteryRoutes = require('./routes/mastery.routes');
const materialRoutes = require('./routes/material.routes');
const agentRoutes = require('./routes/agent.routes');
const apiResponse = require('./utils/apiResponse');

const app = express();

app.use(helmet());

app.use(cors({
  origin: config.cors.origin,
  credentials: true,
  methods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'X-Internal-Key'],
}));

app.use(express.json({ limit: '5mb' }));
app.use(express.urlencoded({ extended: true, limit: '5mb' }));

app.use(morgan('combined', { stream: logger }));

const limiter = expressRateLimit({
  windowMs: 15 * 60 * 1000,
  max: 1000,
  message: {
    success: false,
    error: 'Too many requests from this IP, please try again later.',
    code: 'RATE_LIMIT_EXCEEDED',
  },
});

app.use('/api', limiter);

const publicLimiter = expressRateLimit({
  windowMs: 60 * 1000,
  max: 10,
  message: {
    success: false,
    error: 'Too many requests, please try again later.',
    code: 'RATE_LIMIT_EXCEEDED',
  },
});

app.get('/health', publicLimiter, (req, res) => {
  return apiResponse.success(res, {
    service: 'lmg-service',
    status: 'running',
    timestamp: new Date().toISOString(),
  });
});

app.use('/api/mastery', protect, masteryRoutes);
app.use('/api/materials', protect, materialRoutes);
app.use('/api/agent', protect, agentRoutes);

app.use(notFoundMiddleware);

app.use(errorMiddleware);

module.exports = app;