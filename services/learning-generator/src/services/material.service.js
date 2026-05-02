const LearningMaterial = require('../models/LearningMaterial');
const AgentLog = require('../models/AgentLog');
const logger = require('../utils/logger');

const buildMaterialQuery = (studentId, queryParams) => {
  const filter = {
    'structured_material.student_id': studentId,
    'structured_material.quality_flags': { $ne: 'deleted' },
  };

  if (queryParams.topic) {
    filter['structured_material.topic'] = queryParams.topic;
  }

  if (queryParams.gap_type) {
    filter['structured_material.gap_type'] = queryParams.gap_type;
  }

  if (queryParams.status) {
    filter['structured_material.status'] = queryParams.status;
  }

  return filter;
};

const getMaterialStats = async (studentId) => {
  logger.debug('Computing material stats', { student_id: studentId });

  const materials = await LearningMaterial.find({
    'structured_material.student_id': studentId,
  });

  if (materials.length === 0) {
    return {
      total_materials: 0,
      by_gap_type: {
        FUNDAMENTAL_GAP: 0,
        PARTIAL_GAP: 0,
        SURFACE_GAP: 0,
      },
      avg_quality_score: null,
      avg_validation_score: null,
      needs_review_count: 0,
      agent_patched_count: 0,
      total_agent_retries: 0,
      by_topic: [],
      latest_generated_at: null,
    };
  }

  const gapTypeCounts = {
    FUNDAMENTAL_GAP: 0,
    PARTIAL_GAP: 0,
    SURFACE_GAP: 0,
  };

  const topicStats = {};
  let totalQualityScore = 0;
  let totalValidationScore = 0;
  let qualityScoreCount = 0;
  let validationScoreCount = 0;
  let needsReviewCount = 0;
  let agentPatchedCount = 0;
  let totalRetries = 0;
  let latestGeneratedAt = null;

  for (const material of materials) {
    const sm = material.structured_material || {};

    if (sm.gap_type && gapTypeCounts[sm.gap_type] !== undefined) {
      gapTypeCounts[sm.gap_type]++;
    }

    if (sm.topic) {
      if (!topicStats[sm.topic]) {
        topicStats[sm.topic] = {
          topic: sm.topic,
          count: 0,
          totalScore: 0,
          scoreCount: 0,
        };
      }
      topicStats[sm.topic].count++;
    }

    const agentic = sm.agentic_metadata || {};
    const qualityReview = agentic.quality_review_agent || {};
    const contentValidation = agentic.content_validation_agent || {};
    const qualityFlags = sm.quality_flags || {};

    if (qualityReview.quality_score !== undefined && qualityReview.quality_score !== null) {
      totalQualityScore += qualityReview.quality_score;
      qualityScoreCount++;

      if (sm.topic && topicStats[sm.topic]) {
        topicStats[sm.topic].totalScore += qualityReview.quality_score;
        topicStats[sm.topic].scoreCount++;
      }
    }

    if (contentValidation.validation_score !== undefined && contentValidation.validation_score !== null) {
      totalValidationScore += contentValidation.validation_score;
      validationScoreCount++;
    }

    if (qualityFlags.needs_review) {
      needsReviewCount++;
    }

    if (qualityFlags.agent_patched_llm || qualityFlags.agent_patched_slm) {
      agentPatchedCount++;
    }

    if (qualityReview.retry_count !== undefined && qualityReview.retry_count !== null) {
      totalRetries += qualityReview.retry_count;
    }

    if (sm.generated_at) {
      const generatedAt = new Date(sm.generated_at);
      if (!latestGeneratedAt || generatedAt > latestGeneratedAt) {
        latestGeneratedAt = generatedAt;
      }
    }
  }

  const byTopic = Object.values(topicStats).map((stat) => ({
    topic: stat.topic,
    count: stat.count,
    avg_score: stat.scoreCount > 0 ? stat.totalScore / stat.scoreCount : null,
  }));

  return {
    total_materials: materials.length,
    by_gap_type: gapTypeCounts,
    avg_quality_score: qualityScoreCount > 0 ? totalQualityScore / qualityScoreCount : null,
    avg_validation_score: validationScoreCount > 0 ? totalValidationScore / validationScoreCount : null,
    needs_review_count: needsReviewCount,
    agent_patched_count: agentPatchedCount,
    total_agent_retries: totalRetries,
    by_topic: byTopic,
    latest_generated_at: latestGeneratedAt ? latestGeneratedAt.toISOString() : null,
  };
};

const getGlobalAgentStats = async () => {
  logger.debug('Computing global agent stats');

  const logs = await AgentLog.find({}).limit(10000);

  if (logs.length === 0) {
    return {
      total_generations: 0,
      avg_quality_score: null,
      avg_validation_score: null,
      total_retries: 0,
      retry_rate_percent: null,
      accept_rate_percent: null,
      patch_rate_percent: null,
      model_usage: {
        llm: 'qwen2.5-coder:7b',
        slm: 'qwen2.5-coder:7b',
      },
    };
  }

  let totalQualityScore = 0;
  let totalValidationScore = 0;
  let qualityScoreCount = 0;
  let validationScoreCount = 0;
  let totalRetries = 0;
  let acceptedCount = 0;
  let patchedCount = 0;

  for (const log of logs) {
    if (log.agent_quality_score !== undefined && log.agent_quality_score !== null) {
      totalQualityScore += log.agent_quality_score;
      qualityScoreCount++;
    }

    if (log.content_validation_score !== undefined && log.content_validation_score !== null) {
      totalValidationScore += log.content_validation_score;
      validationScoreCount++;
    }

    if (log.agent_retry_count !== undefined && log.agent_retry_count !== null) {
      totalRetries += log.agent_retry_count;
    }

    if (log.agent_quality_score !== undefined && log.agent_quality_score >= 70) {
      acceptedCount++;
    }

    if (log.agent_quality_score !== undefined && log.agent_quality_score < 50) {
      patchedCount++;
    }
  }

  return {
    total_generations: logs.length,
    avg_quality_score: qualityScoreCount > 0 ? totalQualityScore / qualityScoreCount : null,
    avg_validation_score: validationScoreCount > 0 ? totalValidationScore / validationScoreCount : null,
    total_retries: totalRetries,
    retry_rate_percent: logs.length > 0 ? (totalRetries / logs.length) * 100 : null,
    accept_rate_percent: logs.length > 0 ? (acceptedCount / logs.length) * 100 : null,
    patch_rate_percent: logs.length > 0 ? (patchedCount / logs.length) * 100 : null,
    model_usage: {
      llm: 'qwen2.5-coder:7b',
      slm: 'qwen2.5-coder:7b',
    },
  };
};

const formatMaterialForResponse = (material) => {
  if (!material) return null;

  const obj = material.toObject ? material.toObject() : material;

  delete obj.__v;

  return obj;
};

const getDistinctTopics = async (studentId) => {
  const topics = await LearningMaterial.aggregate([
    {
      $match: {
        'structured_material.student_id': studentId,
      },
    },
    {
      $group: {
        _id: {
          topic: '$structured_material.topic',
          topic_id: '$structured_material.topic_id',
        },
        count: { $sum: 1 },
        latest_generated_at: { $max: '$structured_material.generated_at' },
        avg_quality_score: {
          $avg: '$structured_material.agentic_metadata.quality_review_agent.quality_score',
        },
      },
    },
    {
      $project: {
        _id: 0,
        topic: '$_id.topic',
        topic_id: '$_id.topic_id',
        count: 1,
        latest_generated_at: 1,
        avg_quality_score: 1,
      },
    },
    {
      $sort: { latest_generated_at: -1 },
    },
  ]);

  return topics;
};

module.exports = {
  buildMaterialQuery,
  getMaterialStats,
  getGlobalAgentStats,
  formatMaterialForResponse,
  getDistinctTopics,
};