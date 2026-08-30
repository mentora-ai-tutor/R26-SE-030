const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const config = require('../config/env');

const studentSchema = new mongoose.Schema(
  {
    student_id: {
      type: String,
      unique: true,
      required: true,
      default: () => `STU_${Date.now()}_${Math.floor(1000 + Math.random() * 9000)}`,
    },
    name: {
      type: String,
      required: [true, 'Name is required'],
      trim: true,
      minlength: [2, 'Name must be at least 2 characters'],
      maxlength: [100, 'Name cannot exceed 100 characters'],
    },
    email: {
      type: String,
      required: [true, 'Email is required'],
      unique: true,
      lowercase: true,
      trim: true,
    },
    password: {
      type: String,
      required: [true, 'Password is required'],
      minlength: [6, 'Password must be at least 6 characters'],
      select: false,
    },
    role: {
      type: String,
      enum: ['student', 'instructor', 'admin'],
      default: 'student',
    },
    profile: {
      avatar_url: {
        type: String,
        default: '',
      },
      bio: {
        type: String,
        default: '',
        maxlength: [500, 'Bio cannot exceed 500 characters'],
      },
      java_level: {
        type: String,
        enum: ['beginner', 'intermediate', 'advanced'],
        default: 'beginner',
      },
      institution: {
        type: String,
        default: '',
      },
      country: {
        type: String,
        default: '',
      },
    },
    github: {
      linked: { type: Boolean, default: false },
      gh_login: { type: String },
      linked_at: { type: Date },
      credential_ref: {
        type: mongoose.Schema.Types.ObjectId,
        ref: 'GithubCredential',
      },
    },
    stats: {
      overall_mastery_score: {
        type: Number,
        default: 0,
        min: 0,
        max: 100,
      },
      total_materials_generated: {
        type: Number,
        default: 0,
        min: 0,
      },
      total_sessions: {
        type: Number,
        default: 0,
        min: 0,
      },
      last_mastery_update: {
        type: Date,
      },
    },
    // Account Security
    is_active: {
      type: Boolean,
      default: true,
    },
    is_verified: {
      type: Boolean,
      default: false,
    },
    // Account Lockout
    login_attempts: {
      type: Number,
      default: 0,
    },
    lock_until: {
      type: Date,
    },
    // Soft Delete
    is_deleted: {
      type: Boolean,
      default: false,
    },
    deleted_at: {
      type: Date,
    },
    deleted_by: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Student',
    },
    // User Preferences
    preferences: {
      notifications: {
        email: {
          type: Boolean,
          default: true,
        },
        push: {
          type: Boolean,
          default: true,
        },
        marketing: {
          type: Boolean,
          default: false,
        },
      },
      theme: {
        type: String,
        enum: ['light', 'dark', 'system'],
        default: 'system',
      },
      language: {
        type: String,
        default: 'en',
      },
      timezone: {
        type: String,
        default: 'UTC',
      },
    },
    // Timestamps
    enrolled_at: {
      type: Date,
      default: Date.now,
    },
    last_active: {
      type: Date,
      default: Date.now,
    },
    last_login: {
      type: Date,
    },
    // Tokens
    refresh_token: {
      type: String,
      select: false,
    },
    email_verified_at: {
      type: Date,
    },
  },
  {
    timestamps: true,
  }
);

// Indexes
studentSchema.index({ is_active: 1 });
studentSchema.index({ is_deleted: 1 });
studentSchema.index({ enrolled_at: -1 });
studentSchema.index({ name: 'text', email: 'text', student_id: 'text' });

// Virtual for account locked status
studentSchema.virtual('isLocked').get(function () {
  return !!(this.lock_until && this.lock_until > Date.now());
});

// Pre-save hooks
studentSchema.pre('save', async function (next) {
  if (!this.isModified('password')) {
    return next();
  }

  try {
    const salt = await bcrypt.genSalt(config.bcryptSaltRounds);
    this.password = await bcrypt.hash(this.password, salt);
    next();
  } catch (error) {
    next(error);
  }
});

// Instance Methods
studentSchema.methods.comparePassword = async function (candidatePassword) {
  return bcrypt.compare(candidatePassword, this.password);
};

studentSchema.methods.compareRefreshToken = async function (candidateToken) {
  if (!this.refresh_token) {
    return false;
  }
  return bcrypt.compare(candidateToken, this.refresh_token);
};

studentSchema.methods.toSafeObject = function () {
  const obj = this.toObject();
  delete obj.password;
  delete obj.refresh_token;
  delete obj.__v;
  return obj;
};

studentSchema.methods.updateLastActive = async function () {
  this.last_active = new Date();
  return this.save({ validateBeforeSave: false });
};

// Account Lockout Methods
studentSchema.methods.incrementLoginAttempts = async function () {
  // If lock has expired, reset attempts
  if (this.lock_until && this.lock_until < Date.now()) {
    return this.updateOne({
      $set: { login_attempts: 1 },
      $unset: { lock_until: 1 },
    });
  }

  const updates = { $inc: { login_attempts: 1 } };

  // Lock account after 5 failed attempts (15 minutes)
  if (this.login_attempts + 1 >= 5 && !this.isLocked) {
    updates.$set = { lock_until: Date.now() + 15 * 60 * 1000 }; // 15 minutes
  }

  return this.updateOne(updates);
};

studentSchema.methods.resetLoginAttempts = async function () {
  return this.updateOne({
    $set: { login_attempts: 0 },
    $unset: { lock_until: 1 },
  });
};

// Soft Delete Methods
studentSchema.methods.softDelete = async function (deletedBy = null) {
  this.is_deleted = true;
  this.is_active = false;
  this.deleted_at = new Date();
  if (deletedBy) {
    this.deleted_by = deletedBy;
  }
  return this.save({ validateBeforeSave: false });
};

studentSchema.methods.restore = async function () {
  this.is_deleted = false;
  this.is_active = true;
  this.deleted_at = undefined;
  this.deleted_by = undefined;
  return this.save({ validateBeforeSave: false });
};

// Static Methods
studentSchema.statics.hashRefreshToken = async function (token) {
  return bcrypt.hash(token, config.bcryptSaltRounds);
};

studentSchema.statics.findByCredentials = async function (email, password) {
  const student = await this.findOne({ email: email.toLowerCase(), is_deleted: false }).select('+password');

  if (!student) {
    return null;
  }

  const isMatch = await student.comparePassword(password);

  if (!isMatch) {
    return null;
  }

  return student;
};

studentSchema.statics.findActive = function () {
  return this.find({ is_deleted: false });
};

const Student = mongoose.model('Student', studentSchema);

module.exports = Student;
