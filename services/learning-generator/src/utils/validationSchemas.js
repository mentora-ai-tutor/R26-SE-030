const Joi = require('joi');

const knowledgeGapSchema = Joi.object({
  topic: Joi.string().required(),
  topic_id: Joi.string().required(),
  gap_type: Joi.string()
    .valid('FUNDAMENTAL_GAP', 'PARTIAL_GAP', 'SURFACE_GAP')
    .required(),
  misconceptions: Joi.array().items(Joi.string()).optional(),
  observed_error_patterns: Joi.object().optional(),
  evidence_summary: Joi.string().optional(),
  prerequisite_topics: Joi.array().items(Joi.string()).optional(),
  related_topics: Joi.array().items(Joi.string()).optional(),
  suggested_intervention: Joi.object().optional(),
});

const masterySubmitSchema = Joi.object({
  student_id: Joi.string().required(),
  analysis_timestamp: Joi.string().isoDate().optional(),
  mastery_profile: Joi.object({
    overall_mastery_score: Joi.number().min(0).max(100).required(),
    knowledge_gaps: Joi.array().min(1).items(knowledgeGapSchema).required(),
    strengths: Joi.array().items(Joi.string()).optional(),
  }).required(),
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

module.exports = {
  masterySubmitSchema,
  paginationQuerySchema,
  materialQuerySchema,
  agentQuerySchema,
};