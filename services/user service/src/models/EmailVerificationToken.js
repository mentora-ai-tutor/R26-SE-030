const mongoose = require('mongoose');
const crypto = require('crypto');

const emailVerificationTokenSchema = new mongoose.Schema({
  student: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'Student',
    required: true,
  },
  email: {
    type: String,
    required: true,
    lowercase: true,
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
}, {
  timestamps: true,
});

// Index for cleanup
emailVerificationTokenSchema.index({ expires_at: 1 }, { expireAfterSeconds: 0 });
emailVerificationTokenSchema.index({ student: 1, createdAt: -1 });
emailVerificationTokenSchema.index({ token: 1 }, { unique: true });

// Generate secure random token
emailVerificationTokenSchema.pre('save', function (next) {
  if (!this.token) {
    this.token = crypto.randomBytes(32).toString('hex');
  }
  next();
});

// Instance methods
emailVerificationTokenSchema.methods.isValid = function () {
  return !this.used && this.expires_at > Date.now();
};

const EmailVerificationToken = mongoose.model('EmailVerificationToken', emailVerificationTokenSchema);

module.exports = EmailVerificationToken;
