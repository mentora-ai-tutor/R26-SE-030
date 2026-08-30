const mongoose = require('mongoose');

const subskillSchema = new mongoose.Schema({
  subskill: String,
  subskill_id: String,
  status: {
    type: String,
    enum: ['weak', 'mastered'],
  },
  evidence: String,
  recommended_content_focus: String,
}, { _id: false });

const knowledgeGapSchema = new mongoose.Schema({
  topic: {
    type: String,
    required: true,
  },
  topic_id: {
    type: String,
    required: true,
  },
  gap_type: {
    type: String,
    enum: ['FUNDAMENTAL_GAP', 'PARTIAL_GAP', 'SURFACE_GAP'],
    required: true,
  },
  confidence: Number,
  mastery_score: Number,
  weak_subskills: [subskillSchema],
  known_subskills: [subskillSchema],
  misconceptions: [String],
  observed_error_patterns: mongoose.Schema.Types.Mixed,
  evidence_summary: String,
  prerequisite_topics: [String],
  related_topics: [String],
  suggested_intervention: mongoose.Schema.Types.Mixed,
}, { _id: false });

const masteryProfileSchema = new mongoose.Schema({
  schema_version: {
    type: String,
    default: 'kaa-lmg-v1.0',
  },
  student_id: {
    type: String,
    index: true,
    required: true,
  },
  analysis_timestamp: {
    type: Date,
    default: Date.now,
  },
  overall_mastery_score: {
    type: Number,
    min: 0,
    max: 100,
  },
  mastery_profile: {
    overall_mastery_score: {
      type: Number,
      min: 0,
      max: 100,
    },
    knowledge_gaps: [knowledgeGapSchema],
    strengths: mongoose.Schema.Types.Mixed,
  },
  knowledge_gaps: [knowledgeGapSchema],
  strengths: mongoose.Schema.Types.Mixed,
  recommendations: mongoose.Schema.Types.Mixed,
  data_sources: mongoose.Schema.Types.Mixed,
  gap_topic_ids: {
    type: [String],
    default: [],
  },
  raw_analysis_payload: mongoose.Schema.Types.Mixed,
  n8n_triggered: {
    type: Boolean,
    default: false,
  },
  n8n_triggered_at: {
    type: Date,
  },
  n8n_response: mongoose.Schema.Types.Mixed,
  submission_ip: {
    type: String,
  },
  submitted_at: {
    type: Date,
    default: Date.now,
  },
}, {
  timestamps: true,
  collection: 'mastery_profiles',
});

masteryProfileSchema.index({ student_id: 1, submitted_at: -1 });

masteryProfileSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const MasteryProfile = mongoose.model('MasteryProfile', masteryProfileSchema);

module.exports = MasteryProfile;
