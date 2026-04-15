const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');
const { generateStudentId } = require('../utils/generateStudentId');
const config = require('../config/env');

const studentSchema = new mongoose.Schema(
  {
    student_id: {
      type: String,
      unique: true,
      required: true,
      default: function() {
        return `STU_${Date.now()}_${Math.floor(1000 + Math.random() * 9000)}`;
      },
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
    is_active: {
      type: Boolean,
      default: true,
    },
    is_verified: {
      type: Boolean,
      default: false,
    },
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
    refresh_token: {
      type: String,
      select: false,
    },
  },
  {
    timestamps: true,
  }
);

studentSchema.index({ student_id: 1 }, { unique: true });
studentSchema.index({ email: 1 }, { unique: true });
studentSchema.index({ is_active: 1 });
studentSchema.index({ enrolled_at: -1 });

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

studentSchema.statics.hashRefreshToken = async function (token) {
  return bcrypt.hash(token, config.bcryptSaltRounds);
};

const Student = mongoose.model('Student', studentSchema);

module.exports = Student;
