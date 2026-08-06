const mongoose = require('mongoose');

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
  misconceptions: [String],
  observed_error_patterns: mongoose.Schema.Types.Mixed,
  evidence_summary: String,
  prerequisite_topics: [String],
  related_topics: [String],
  suggested_intervention: mongoose.Schema.Types.Mixed,
  resolved_concept_id: String,
  resolution_method: {
    type: String,
    enum: ['exact', 'alias', 'embedding', 'llm', 'llm_no_match', 'unresolved'],
  },
  resolution_confidence: Number,
  concept_context: mongoose.Schema.Types.Mixed,
}, { _id: false });

const implicitGapSchema = new mongoose.Schema({
  concept_id: String,
  injected: {
    type: Boolean,
    default: true,
  },
  reason: String,
}, { _id: false });

const unverifiedPrerequisiteSchema = new mongoose.Schema({
  concept_id: String,
  blocks: String,
}, { _id: false });

const augmentedProfileSchema = new mongoose.Schema({
  implicit_gaps: [implicitGapSchema],
  unverified_prerequisites: [unverifiedPrerequisiteSchema],
  coverage_snapshot: {
    totalNodes: Number,
    coveredNodes: Number,
    coveragePct: Number,
  },
}, { _id: false });

const masteryProfileSchema = new mongoose.Schema({
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
  knowledge_gaps: [knowledgeGapSchema],
  augmented_profile: augmentedProfileSchema,
  strengths: mongoose.Schema.Types.Mixed,
  recommendations: mongoose.Schema.Types.Mixed,
  data_sources: mongoose.Schema.Types.Mixed,
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
