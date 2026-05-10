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
    expiresIn: process.env.JWT_EXPIRES_IN || '1h',
    refreshSecret: process.env.JWT_REFRESH_SECRET,
    refreshExpiresIn: process.env.JWT_REFRESH_EXPIRES_IN || '7d',
  },
  internalServiceKey: process.env.INTERNAL_SERVICE_KEY,
  corsOrigin: process.env.CORS_ORIGIN.split(',').map((origin) => origin.trim()),
  bcryptSaltRounds: parseInt(process.env.BCRYPT_SALT_ROUNDS, 10) || 12,
  // Optional features
  features: {
    emailVerification: process.env.ENABLE_EMAIL_VERIFICATION === 'true',
    accountLockout: process.env.ENABLE_ACCOUNT_LOCKOUT !== 'false', // enabled by default
    auditLogging: process.env.ENABLE_AUDIT_LOGGING !== 'false', // enabled by default
  },
  // Redis config (optional)
  redis: {
    url: process.env.REDIS_URL,
    enabled: !!process.env.REDIS_URL,
  },
};

if (config.nodeEnv === 'development' && config.jwt.secret.length < 32) {
  console.warn('Warning: JWT_SECRET should be at least 32 characters for security');
}

module.exports = config;
