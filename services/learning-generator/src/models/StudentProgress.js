const mongoose = require('mongoose');

const studentProgressSchema = new mongoose.Schema({
  student_id: {
    type: String,
    index: true,
    required: true,
  },
  material_id: {
    type: String,
    required: true,
  },
  topic_id: {
    type: String,
    required: true,
  },
  total_steps: {
    type: Number,
    default: 0,
  },
  completed_steps: [Number],
  quiz_score: {
    type: Number,
    default: null,
  },
  started_at: {
    type: Date,
    default: Date.now,
  },
  completed_at: {
    type: Date,
    default: null,
  },
  last_active_step: {
    type: Number,
    default: 0,
  },
}, {
  timestamps: true,
  collection: 'student_progress',
});

studentProgressSchema.index({ student_id: 1, material_id: 1 }, { unique: true });
studentProgressSchema.index({ student_id: 1, topic_id: 1 });

studentProgressSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const StudentProgress = mongoose.model('StudentProgress', studentProgressSchema);

module.exports = StudentProgress;
