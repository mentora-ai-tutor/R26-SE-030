require('dotenv').config();
const connectDB = require('./src/config/database');
const app = require('./src/app');

const startServer = async () => {
  try {
    await connectDB();

    const PORT = process.env.PORT || 3001;

    app.listen(PORT, () => {
      console.log(`AME Backend running on port ${PORT}`);
    });

    process.on('uncaughtException', (error) => {
      console.error('Uncaught Exception:', error.message);
      process.exit(1);
    });

    process.on('unhandledRejection', (reason) => {
      console.error('Unhandled Rejection:', reason);
    });
  } catch (error) {
    console.error('Failed to start server:', error.message);
    process.exit(1);
  }
};

startServer();
