const mongoose = require('mongoose');

const auditLogSchema = new mongoose.Schema({
  student: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Student',
    index: true,
  },
  action: {
    type: String,
    required: true,
    enum: [
      'REGISTER',
      'LOGIN',
      'LOGIN_FAILED',
      'LOGOUT',
      'PASSWORD_CHANGE',
      'PASSWORD_RESET_REQUEST',
      'PASSWORD_RESET_COMPLETE',
      'EMAIL_VERIFICATION_SENT',
      'EMAIL_VERIFIED',
      'PROFILE_UPDATE',
      'ACCOUNT_LOCKED',
      'ACCOUNT_UNLOCKED',
      'ACCOUNT_DEACTIVATED',
      'ACCOUNT_REACTIVATED',
      'ACCOUNT_DELETED',
      'REFRESH_TOKEN',
      'TOKEN_VERIFIED',
      'SESSION_REVOKED',
      'ADMIN_ACTION',
    ],
    index: true,
  },
  status: {
    type: String,
    enum: ['SUCCESS', 'FAILED', 'PENDING'],
    default: 'SUCCESS',
  },
  description: {
    type: String,
  },
  metadata: {
    type: mongoose.Schema.Types.Mixed,
    default: {},
  },
  ip_address: {
    type: String,
  },
  user_agent: {
    type: String,
  },
  device_info: {
    type: {
      type: String, // desktop, mobile, tablet
    },
    os: String,
    browser: String,
    browser_version: String,
  },
  location: {
    country: String,
    city: String,
    region: String,
  },
  request_id: {
    type: String,
    index: true,
  },
}, {
  timestamps: true,
});

// Indexes for querying
auditLogSchema.index({ createdAt: -1 });
auditLogSchema.index({ student: 1, createdAt: -1 });
auditLogSchema.index({ action: 1, createdAt: -1 });
auditLogSchema.index({ ip_address: 1 });

// TTL for automatic cleanup after 1 year
auditLogSchema.index({ createdAt: 1 }, { expireAfterSeconds: 365 * 24 * 60 * 60 });

const AuditLog = mongoose.model('AuditLog', auditLogSchema);

module.exports = AuditLog;
