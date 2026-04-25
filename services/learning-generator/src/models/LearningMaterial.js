const mongoose = require('mongoose');

const learningMaterialSchema = new mongoose.Schema({
  material_id: {
    type: String,
    unique: true,
    required: true,
  },
  student_id: {
    type: String,
    index: true,
    required: true,
  },
  topic: {
    type: String,
  },
  topic_id: {
    type: String,
  },
  gap_type: {
    type: String,
  },
  difficulty_level: {
    type: String,
  },
  generated_at: {
    type: Date,
    index: true,
  },
  generation_models: {
    llm: String,
    slm: String,
  },
  lesson: {
    page_title: String,
    introduction: mongoose.Schema.Types.Mixed,
    concept_explained: mongoose.Schema.Types.Mixed,
    syntax_reference: mongoose.Schema.Types.Mixed,
    examples: mongoose.Schema.Types.Mixed,
    step_by_step_guide: mongoose.Schema.Types.Mixed,
    common_mistakes: [mongoose.Schema.Types.Mixed],
    debugging_exercise: mongoose.Schema.Types.Mixed,
    quick_reference: mongoose.Schema.Types.Mixed,
    connections: mongoose.Schema.Types.Mixed,
  },
  assessment: {
    quiz: [mongoose.Schema.Types.Mixed],
    concept_summary: String,
    practice_challenge: mongoose.Schema.Types.Mixed,
    self_check: mongoose.Schema.Types.Mixed,
  },
  personalisation: mongoose.Schema.Types.Mixed,
  study_plan: mongoose.Schema.Types.Mixed,
  agentic_metadata: mongoose.Schema.Types.Mixed,
  quality_flags: mongoose.Schema.Types.Mixed,
  status: {
    type: String,
    enum: ['generating', 'ready', 'failed', 'deleted'],
    default: 'ready',
  },
}, {
  timestamps: true,
  collection: 'learning_materials',
  strict: false,
});

learningMaterialSchema.index({ student_id: 1, generated_at: -1 });
learningMaterialSchema.index({ student_id: 1, topic_id: 1 });

learningMaterialSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const LearningMaterial = mongoose.model('LearningMaterial', learningMaterialSchema);

module.exports = LearningMaterial;