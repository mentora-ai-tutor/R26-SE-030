const Joi = require('joi');

const subskillSchema = Joi.object({
  subskill: Joi.string().required(),
  subskill_id: Joi.string().required(),
  status: Joi.string().valid('weak', 'mastered').required(),
  evidence: Joi.string().allow('', null).optional(),
  recommended_content_focus: Joi.string().allow('', null).optional(),
});

const knowledgeGapSchema = Joi.object({
  topic: Joi.string().required(),
  topic_id: Joi.string().required(),
  gap_type: Joi.string()
    .valid('FUNDAMENTAL_GAP', 'PARTIAL_GAP', 'SURFACE_GAP')
    .required(),
  confidence: Joi.number().min(0).max(1).optional(),
  mastery_score: Joi.number().min(0).max(100).optional(),
  weak_subskills: Joi.array().items(subskillSchema).optional(),
  known_subskills: Joi.array().items(subskillSchema).optional(),
  misconceptions: Joi.array().items(Joi.string()).optional(),
  observed_error_patterns: Joi.object().optional(),
  evidence_summary: Joi.string().optional(),
  prerequisite_topics: Joi.array().items(Joi.string()).optional(),
  related_topics: Joi.array().items(Joi.string()).optional(),
  suggested_intervention: Joi.object().optional(),
});

const strengthItemSchema = Joi.alternatives().try(
  Joi.string(),
  Joi.object({
    topic: Joi.string().required(),
    topic_id: Joi.string().required(),
    confidence: Joi.number().min(0).max(1).optional(),
    mastery_score: Joi.number().min(0).max(100).optional(),
    mastery_level: Joi.string().optional(),
    evidence_summary: Joi.string().optional(),
    known_subskills: Joi.array().items(subskillSchema).optional(),
    can_teach_others: Joi.boolean().optional(),
  })
);

const masterySubmitSchema = Joi.object({
  schema_version: Joi.string().optional(),
  student_id: Joi.string().required(),
  analysis_timestamp: Joi.string().isoDate().optional(),
  mastery_profile: Joi.object({
    overall_mastery_score: Joi.number().min(0).max(100).required(),
    knowledge_gaps: Joi.array().min(1).items(knowledgeGapSchema).required(),
    strengths: Joi.array().items(strengthItemSchema).optional(),
  }).required(),
  gap_topic_ids: Joi.array().items(Joi.string()).optional(),
  raw_analysis_payload: Joi.object().optional(),
  recommendations: Joi.object().optional(),
  data_sources: Joi.object().optional(),
});

const paginationQuerySchema = Joi.object({
  limit: Joi.number().integer().min(1).max(100).optional(),
  page: Joi.number().integer().min(1).optional(),
});

const materialQuerySchema = Joi.object({
  topic: Joi.string().optional(),
  gap_type: Joi.string()
    .valid('FUNDAMENTAL_GAP', 'PARTIAL_GAP', 'SURFACE_GAP')
    .optional(),
  status: Joi.string().valid('generating', 'ready', 'failed', 'deleted').optional(),
  limit: Joi.number().integer().min(1).max(100).optional(),
  page: Joi.number().integer().min(1).optional(),
  sort: Joi.string().valid('generated_at', 'created_at', 'topic').optional(),
  order: Joi.string().valid('asc', 'desc').optional(),
});

const agentQuerySchema = Joi.object({
  limit: Joi.number().integer().min(1).max(100).optional(),
  page: Joi.number().integer().min(1).optional(),
});

const n8nWebhookSchema = Joi.object({
  student_id: Joi.string().required(),
  job_id: Joi.string().optional(),
  material_id: Joi.string().required(),
  topic: Joi.string().required(),
  topic_id: Joi.string().required(),
  gap_type: Joi.string()
    .valid('FUNDAMENTAL_GAP', 'PARTIAL_GAP', 'SURFACE_GAP')
    .required(),
  difficulty_level: Joi.string().optional(),
  generated_at: Joi.string().isoDate().optional(),
  generation_models: Joi.object({
    llm: Joi.string().optional(),
    slm: Joi.string().optional(),
  }).optional(),
  lesson: Joi.object({
    page_title: Joi.string().optional(),
    introduction: Joi.object().optional(),
    concept_explained: Joi.object().optional(),
    syntax_reference: Joi.object().optional(),
    examples: Joi.object().optional(),
    step_by_step_guide: Joi.object().optional(),
    common_mistakes: Joi.array().optional(),
    debugging_exercise: Joi.object().optional(),
    quick_reference: Joi.object().optional(),
    connections: Joi.object().optional(),
  }).optional(),
  assessment: Joi.object({
    quiz: Joi.array().optional(),
    concept_summary: Joi.string().optional(),
    practice_challenge: Joi.object().optional(),
    self_check: Joi.object().optional(),
  }).optional(),
  personalisation: Joi.object().optional(),
  study_plan: Joi.object().optional(),
  agentic_metadata: Joi.object().optional(),
  quality_flags: Joi.object().optional(),
  status: Joi.string().valid('generating', 'ready', 'failed', 'deleted').optional(),
}).unknown(true);

module.exports = {
  masterySubmitSchema,
  paginationQuerySchema,
  materialQuerySchema,
  agentQuerySchema,
  n8nWebhookSchema,
};
