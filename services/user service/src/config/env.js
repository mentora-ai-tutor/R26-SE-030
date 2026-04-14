require('dotenv').config();

const requiredEnvVars = [
  'PORT',
  'NODE_ENV',
  'SERVICE_NAME',
  'MONGODB_URI',
  'JWT_SECRET',
  'JWT_EXPIRES_IN',
  'JWT_REFRESH_SECRET',
  'JWT_REFRESH_EXPIRES_IN',
  'INTERNAL_SERVICE_KEY',
  'CORS_ORIGIN',
];

const missingVars = requiredEnvVars.filter((varName) => !process.env[varName]);

if (missingVars.length > 0) {
  console.error(`Missing required environment variables: ${missingVars.join(', ')}`);
  process.exit(1);
}

const config = {
  port: parseInt(process.env.PORT, 10),
  nodeEnv: process.env.NODE_ENV,
  serviceName: process.env.SERVICE_NAME,
  mongodbUri: process.env.MONGODB_URI,
  jwt: {
    secret: process.env.JWT_SECRET,
    expiresIn: process.env.JWT_EXPIRES_IN,
    refreshSecret: process.env.JWT_REFRESH_SECRET,
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN,
  },
  internalServiceKey: process.env.INTERNAL_SERVICE_KEY,
  corsOrigin: process.env.CORS_ORIGIN.split(',').map((origin) => origin.trim()),
  bcryptSaltRounds: 12,
};

if (config.nodeEnv === 'development' && config.jwt.secret.length < 32) {
  console.warn('Warning: JWT_SECRET should be at least 32 characters for security');
}

module.exports = config;
