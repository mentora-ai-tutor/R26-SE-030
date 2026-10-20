const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const assessmentRoutes = require('./routes/assessment');
const ragRoutes = require('./routes/rag');
//const adminRoutes = require('./routes/admin');
const errorHandler = require('./middleware/errorHandler');

const app = express();

// FRONTEND_URL may be a comma-separated list of allowed origins (local + deployed).
const allowedOrigins = (process.env.FRONTEND_URL || 'http://localhost:3000')
  .split(',')
  .map((origin) => origin.trim());

app.use(cors({
  origin: allowedOrigins,
  credentials: true,
}));

app.use(helmet());
app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'ok',
    service: 'AME Backend',
    timestamp: new Date(),
  });
});

app.use('/api/ame', assessmentRoutes);
app.use('/api/ame', ragRoutes);
//app.use('/api/admin', adminRoutes);

app.use((req, res) => {
  res.status(404).json({
    success: false,
    message: `Route ${req.method} ${req.path} not found`,
  });
});

app.use(errorHandler);

module.exports = app;
