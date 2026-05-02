require('dotenv').config();

module.exports = {
  port: process.env.PORT || 3002,
  nodeEnv: process.env.NODE_ENV || 'development',
  serviceName: process.env.SERVICE_NAME || 'lmg-service',

  mongodb: {
    uri: process.env.MONGODB_URI || 'mongodb://localhost:27017/mentora_lmg',
  },

  userService: {
    url: process.env.USER_SERVICE_URL || 'http://localhost:3001',
    internalKey: process.env.INTERNAL_SERVICE_KEY || 'your_internal_service_secret_key',
  },

  n8n: {
    baseUrl: process.env.N8N_BASE_URL || 'http://localhost:5678',
    webhookLearnerProfile: process.env.N8N_WEBHOOK_LEARNER_PROFILE || 'http://localhost:5678/webhook/learner-profile',
    webhookGetMaterials: process.env.N8N_WEBHOOK_GET_MATERIALS || 'http://localhost:5678/webhook/materials',
    webhookSecret: process.env.N8N_WEBHOOK_SECRET || 'your_n8n_webhook_secret_key',
    timeoutMs: parseInt(process.env.N8N_TIMEOUT_MS, 10) || 600000,
  },

  ollama: {
    baseUrl: process.env.OLLAMA_BASE_URL || 'http://192.168.1.102:11434',
  },

  cors: {
    origin: process.env.CORS_ORIGIN || 'http://localhost:3000',
  },
};