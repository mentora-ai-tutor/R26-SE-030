require('dotenv').config();
const app = require('./src/app');
const config = require('./src/config/env');
const db = require('./src/config/db');
const logger = require('./src/utils/logger');

const startServer = async () => {
  try {
    await db.connectDB();
    logger.info('Database connected successfully');

    const server = app.listen(config.port, () => {
      logger.info(`
╔═══════════════════════════════════════════════════════════╗
║              MENTORA LMG Service Started                  ║
╠═══════════════════════════════════════════════════════════╣
║  Service:    ${config.serviceName.padEnd(42)}║
║  Port:       ${config.port.toString().padEnd(42)}║
║  Environment:${config.nodeEnv.padEnd(42)}║
║  MongoDB:    ${config.mongodb.uri.replace(/\/\/.*@/, '//***@').padEnd(42)}║
║  User Svc:   ${config.userService.url.padEnd(42)}║
║  n8n:        ${config.n8n.baseUrl.padEnd(42)}║
╚═══════════════════════════════════════════════════════════╝
      `);
    });

    const gracefulShutdown = async (signal) => {
      logger.info(`${signal} received. Starting graceful shutdown...`);

      server.close(async () => {
        logger.info('HTTP server closed');

        try {
          await db.disconnectDB();
          logger.info('Graceful shutdown completed');
          process.exit(0);
        } catch (error) {
          logger.error('Error during shutdown', { error: error.message });
          process.exit(1);
        }
      });

      setTimeout(() => {
        logger.warn('Forced shutdown after timeout');
        process.exit(1);
      }, 10000);
    };

    process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
    process.on('SIGINT', () => gracefulShutdown('SIGINT'));

    process.on('uncaughtException', (error) => {
      logger.error('Uncaught Exception', { error: error.message, stack: error.stack });
      process.exit(1);
    });

    process.on('unhandledRejection', (reason, promise) => {
      logger.error('Unhandled Rejection', { reason: reason?.message || reason });
    });

  } catch (error) {
    logger.error('Failed to start server', { error: error.message, stack: error.stack });
    process.exit(1);
  }
};

startServer();