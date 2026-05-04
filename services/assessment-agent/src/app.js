const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const assessmentRoutes = require('./routes/assessment');
//const adminRoutes = require('./routes/admin');
const errorHandler = require('./middleware/errorHandler');

const app = express();

app.use(cors({
  origin: process.env.FRONTEND_URL,
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
//app.use('/api/admin', adminRoutes);

app.use((req, res) => {
  res.status(404).json({
    success: false,
    message: `Route ${req.method} ${req.path} not found`,
  });
});

app.use(errorHandler);

module.exports = app;
