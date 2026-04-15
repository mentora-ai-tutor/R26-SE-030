const app = require('./src/app');
const config = require('./src/config/env');
const logger = require('./src/utils/logger');
const { connectDB, disconnectDB } = require('./src/config/db');

let server;

const startServer = async () => {
  try {
    await connectDB();

    server = app.listen(config.port, () => {
      logger.info(`${config.serviceName} running on port ${config.port}`);
      logger.info(`Environment: ${config.nodeEnv}`);
      logger.info(`Health check: http://localhost:${config.port}/health`);
    });

    server.keepAliveTimeout = 65000;
    server.headersTimeout = 66000;

  } catch (error) {
    logger.error('Failed to start server:', error.message);
    process.exit(1);
  }
};

const gracefulShutdown = async (signal) => {
  logger.info(`${signal} received. Starting graceful shutdown...`);

  if (server) {
    server.close(async () => {
      logger.info('HTTP server closed');

      await disconnectDB();

      logger.info(`${config.serviceName} shut down gracefully`);
      process.exit(0);
    });

    setTimeout(() => {
      logger.error('Forced shutdown due to timeout');
      process.exit(1);
    }, 10000);
  } else {
    await disconnectDB();
    process.exit(0);
  }
};

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

process.on('uncaughtException', (error) => {
  logger.error('Uncaught Exception:', error);
  gracefulShutdown('UNCAUGHT_EXCEPTION');
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

startServer();
