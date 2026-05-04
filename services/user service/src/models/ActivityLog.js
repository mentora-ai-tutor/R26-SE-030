const mongoose = require('mongoose');

const activityLogSchema = new mongoose.Schema({
  student: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Student',
    required: true,
    index: true,
  },
  activity_type: {
    type: String,
    required: true,
    enum: [
      'LOGIN',
      'LOGOUT',
      'SESSION_EXPIRED',
      'PROFILE_VIEW',
      'PROFILE_UPDATE',
      'PASSWORD_CHANGE',
      'STATS_UPDATE',
      'API_CALL',
      'SUSPICIOUS_ACTIVITY',
    ],
    index: true,
  },
  description: {
    type: String,
  },
  metadata: {
    type: mongoose.Schema.Types.Mixed,
    default: {},
  },
  // Session Info
  session_id: {
    type: String,
    index: true,
  },
  // Device/Location
  ip_address: {
    type: String,
  },
  user_agent: {
    type: String,
  },
  device_type: {
    type: String,
  },
  browser: {
    type: String,
  },
  os: {
    type: String,
  },
}, {
  timestamps: true,
});

// Indexes for efficient querying
activityLogSchema.index({ createdAt: -1 });
activityLogSchema.index({ student: 1, createdAt: -1 });
activityLogSchema.index({ activity_type: 1, createdAt: -1 });

// TTL for automatic cleanup after 90 days
activityLogSchema.index({ createdAt: 1 }, { expireAfterSeconds: 90 * 24 * 60 * 60 });

const ActivityLog = mongoose.model('ActivityLog', activityLogSchema);

module.exports = ActivityLog;
