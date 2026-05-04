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
  profile_id: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'MasteryProfile',
  },
  status: {
    type: String,
    enum: ['queued', 'processing', 'completed', 'failed', 'partial', 'closed'],
    default: 'queued',
  },
  gaps_total: {
    type: Number,
  },
  gaps_queued: {
    type: Number,
  },
  gaps_completed: {
    type: Number,
    default: 0,
  },
  gaps_failed: {
    type: Number,
    default: 0,
  },
  n8n_triggered_at: {
    type: Date,
  },
  n8n_workflow_id: {
    type: String,
  },
  n8n_execution_id: {
    type: String,
  },
  completed_at: {
    type: Date,
  },
  materials_generated: {
    type: Number,
    default: 0,
  },
  materials_failed: {
    type: Number,
    default: 0,
  },
  error: {
    type: String,
  },
  gap_topic_ids: {
    type: [String],
    default: [],
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