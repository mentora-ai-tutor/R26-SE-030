const mongoose = require('mongoose');

const agentLogSchema = new mongoose.Schema({
  log_id: {
    type: String,
    unique: true,
    required: true,
  },
  student_id: {
    type: String,
    index: true,
  },
  topic: {
    type: String,
  },
  llm_model: {
    type: String,
  },
  slm_model: {
    type: String,
  },
  agent_quality_score: {
    type: Number,
  },
  content_validation_score: {
    type: Number,
  },
  agent_retry_count: {
    type: Number,
    default: 0,
  },
  llm_parse_error: {
    type: String,
  },
  slm_parse_error: {
    type: String,
  },
  timestamp: {
    type: Date,
    index: true,
  },
}, {
  timestamps: true,
  collection: 'model_comparison_logs',
  strict: false,
});

agentLogSchema.index({ student_id: 1, timestamp: -1 });

agentLogSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const AgentLog = mongoose.model('AgentLog', agentLogSchema);

module.exports = AgentLog;