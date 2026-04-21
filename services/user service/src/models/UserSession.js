const mongoose = require('mongoose');

const userSessionSchema = new mongoose.Schema({
  student: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Student',
    required: true,
    index: true,
  },
  session_token: {
    type: String,
    required: true,
    unique: true,
    index: true,
  },
  refresh_token: {
    type: String,
    required: true,
  },
  // Device Info
  device_id: {
    type: String,
  },
  device_name: {
    type: String,
  },
  device_type: {
    type: String,
    enum: ['desktop', 'mobile', 'tablet', 'unknown'],
    default: 'unknown',
  },
  os: {
    type: String,
  },
  os_version: {
    type: String,
  },
  browser: {
    type: String,
  },
  browser_version: {
    type: String,
  },
  // Location
  ip_address: {
    type: String,
  },
  // Session Status
  is_active: {
    type: Boolean,
    default: true,
  },
  is_revoked: {
    type: Boolean,
    default: false,
  },
  revoked_at: {
    type: Date,
  },
  revoked_reason: {
    type: String,
  },
  // Timestamps
  last_active_at: {
    type: Date,
    default: Date.now,
  },
  expires_at: {
    type: Date,
    required: true,
  },
}, {
  timestamps: true,
});

// Indexes
userSessionSchema.index({ student: 1, is_active: 1 });
userSessionSchema.index({ expires_at: 1 });
userSessionSchema.index({ device_id: 1 });

// Instance methods
userSessionSchema.methods.revoke = async function (reason = 'manual_logout') {
  this.is_active = false;
  this.is_revoked = true;
  this.revoked_at = new Date();
  this.revoked_reason = reason;
  return this.save();
};

userSessionSchema.methods.updateActivity = async function () {
  this.last_active_at = new Date();
  return this.save({ validateBeforeSave: false });
};

// Static methods
userSessionSchema.statics.findActiveByStudent = function (studentId) {
  return this.find({
    student: studentId,
    is_active: true,
    expires_at: { $gt: Date.now() },
  });
};

userSessionSchema.statics.revokeAllExcept = async function (studentId, exceptToken) {
  return this.updateMany(
    {
      student: studentId,
      session_token: { $ne: exceptToken },
      is_active: true,
    },
    {
      $set: {
        is_active: false,
        is_revoked: true,
        revoked_at: new Date(),
        revoked_reason: 'logout_all',
      },
    }
  );
};

const UserSession = mongoose.model('UserSession', userSessionSchema);

module.exports = UserSession;
