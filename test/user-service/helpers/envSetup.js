function setupEnv() {
  process.env.PORT = process.env.PORT || '4001';
  process.env.NODE_ENV = process.env.NODE_ENV || 'test';
  process.env.SERVICE_NAME = process.env.SERVICE_NAME || 'user-service-test';
  process.env.MONGODB_URI = process.env.MONGODB_URI || 'mongodb://localhost:27017/mentora_test';
  process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx';
  process.env.JWT_EXPIRES_IN = process.env.JWT_EXPIRES_IN || '1h';
  process.env.JWT_REFRESH_SECRET = process.env.JWT_REFRESH_SECRET || 'test-jwt-refresh-secret-yyyyyyyyyyyyyyyyyyyyyyyy';
  process.env.JWT_REFRESH_EXPIRES_IN = process.env.JWT_REFRESH_EXPIRES_IN || '7d';
  process.env.INTERNAL_SERVICE_KEY = process.env.INTERNAL_SERVICE_KEY || 'test-internal-key';
  process.env.CORS_ORIGIN = process.env.CORS_ORIGIN || 'http://localhost:3000';
  process.env.GH_CLIENT_ID = process.env.GH_CLIENT_ID || 'test-gh-client-id';
  process.env.GH_CLIENT_SECRET = process.env.GH_CLIENT_SECRET || 'test-gh-client-secret';
  process.env.GH_OAUTH_SCOPE = process.env.GH_OAUTH_SCOPE || 'repo';
  process.env.GH_OAUTH_CALLBACK_URL =
    process.env.GH_OAUTH_CALLBACK_URL || 'http://localhost:4001/api/github/oauth/callback';
}

module.exports = { setupEnv };