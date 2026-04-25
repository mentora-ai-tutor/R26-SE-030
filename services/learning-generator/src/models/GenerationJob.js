const mongoose = require('mongoose');

const generationJobSchema = new mongoose.Schema({
  job_id: {
    type: String,
    unique: true,
    required: true,
  },
  student_id: {
    type: String,
    index: true,
    required: true,
  },
  mastery_profile_id: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'MasteryProfile',
  },
  status: {
    type: String,
    enum: ['queued', 'processing', 'completed', 'failed'],
    default: 'queued',
  },
  gaps_total: {
    type: Number,
  },
  gaps_queued: {
    type: Number,
  },
  n8n_triggered_at: {
    type: Date,
  },
  completed_at: {
    type: Date,
  },
  error: {
    type: String,
  },
  created_at: {
    type: Date,
    default: Date.now,
  },
}, {
  timestamps: true,
  collection: 'generation_jobs',
});

generationJobSchema.index({ student_id: 1, created_at: -1 });
generationJobSchema.index({ status: 1 });

generationJobSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const GenerationJob = mongoose.model('GenerationJob', generationJobSchema);

module.exports = GenerationJob;