const mongoose = require('mongoose');
const crypto = require('crypto');

const passwordResetTokenSchema = new mongoose.Schema({
  student: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Student',
    required: true,
  },
  token: {
    type: String,
    required: true,
    default: () => crypto.randomBytes(32).toString('hex'),
  },
  expires_at: {
    type: Date,
    required: true,
  },
  used: {
    type: Boolean,
    default: false,
  },
  used_at: {
    type: Date,
  },
  ip_address: {
    type: String,
  },
  user_agent: {
    type: String,
  },
}, {
  timestamps: true,
});

// Index for cleanup
passwordResetTokenSchema.index({ expires_at: 1 }, { expireAfterSeconds: 0 });
passwordResetTokenSchema.index({ student: 1, createdAt: -1 });

// Generate secure random token
passwordResetTokenSchema.pre('save', function (next) {
  if (!this.token) {
    this.token = crypto.randomBytes(32).toString('hex');
  }
  next();
});

// Instance methods
passwordResetTokenSchema.methods.isValid = function () {
  return !this.used && this.expires_at > Date.now();
};

passwordResetTokenSchema.methods.markAsUsed = async function (ip, userAgent) {
  this.used = true;
  this.used_at = new Date();
  this.ip_address = ip;
  this.user_agent = userAgent;
  return this.save();
};

const PasswordResetToken = mongoose.model('PasswordResetToken', passwordResetTokenSchema);

module.exports = PasswordResetToken;
