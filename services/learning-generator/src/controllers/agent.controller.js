const AgentLog = require('../models/AgentLog');
const GenerationJob = require('../models/GenerationJob');
const LearningMaterial = require('../models/LearningMaterial');
const MasteryProfile = require('../models/MasteryProfile');
const materialService = require('../services/material.service');
const n8nService = require('../services/n8n.service');
const ServiceError = require('../utils/ServiceError');
const apiResponse = require('../utils/apiResponse');
const db = require('../config/db');
const logger = require('../utils/logger');
const axios = require('axios');
const config = require('../config/env');

const getAgentLogs = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own agent logs',
        code: 'FORBIDDEN',
      });
    }

    const limit = parseInt(req.query.limit, 10) || 20;
    const page = parseInt(req.query.page, 10) || 1;
    const skip = (page - 1) * limit;

    const [logs, total] = await Promise.all([
      AgentLog.find({ student_id: studentId })
        .sort({ timestamp: -1 })
        .skip(skip)
        .limit(limit),
      AgentLog.countDocuments({ student_id: studentId }),
    ]);

    return apiResponse.paginated(res, logs, {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    });
  } catch (error) {
    next(error);
  }
};

const getJobStatus = async (req, res, next) => {
  try {
    const { jobId } = req.params;

    const job = await GenerationJob.findOne({ job_id: jobId });

    if (!job) {
      return res.status(404).json({
        success: false,
        error: 'Job not found',
        code: 'NOT_FOUND',
      });
    }

    const tokenStudentId = req.student.id;
    if (job.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own jobs',
        code: 'FORBIDDEN',
      });
    }

    return apiResponse.success(res, job);
  } catch (error) {
    next(error);
  }
};

const getJobsByStudent = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own jobs',
        code: 'FORBIDDEN',
      });
    }

    const jobs = await GenerationJob.find({ student_id: studentId })
      .sort({ created_at: -1 })
      .limit(10);

    return apiResponse.success(res, jobs);
  } catch (error) {
    next(error);
  }
};

const getGlobalStats = async (req, res, next) => {
  try {
    const stats = await materialService.getGlobalAgentStats();
    return apiResponse.success(res, stats);
  } catch (error) {
    next(error);
  }
};

const checkHealth = async (req, res, next) => {
  try {
    const mongoStatus = db.isConnected() ? 'connected' : 'disconnected';

    const [userServiceHealth, n8nHealth, ollamaHealth] = await Promise.all([
      require('../services/userService.client').checkHealth(),
      require('../services/n8n.service').checkHealth(),
      checkOllamaHealth(),
    ]);

    const dependencies = {
      mongodb: {
        status: mongoStatus,
      },
      user_service: {
        status: userServiceHealth.reachable ? 'reachable' : 'unreachable',
        url: config.userService.url,
      },
      n8n: {
        status: n8nHealth.reachable ? 'reachable' : 'unreachable',
        url: config.n8n.baseUrl,
      },
      ollama: {
        status: ollamaHealth.reachable ? 'reachable' : 'unreachable',
        url: config.ollama.baseUrl,
      },
    };

    if (ollamaHealth.models) {
      dependencies.ollama.models = ollamaHealth.models;
    }

    const allDependenciesReachable = Object.values(dependencies).every(
      (dep) => dep.status === 'connected' || dep.status === 'reachable'
    );

    return res.status(allDependenciesReachable ? 200 : 503).json({
      service: 'lmg-service',
      status: allDependenciesReachable ? 'ok' : 'degraded',
      dependencies,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    next(error);
  }
};

const checkOllamaHealth = async () => {
  try {
    const response = await axios.get(`${config.ollama.baseUrl}/api/tags`, {
      timeout: 5000,
    });

    if (response.data?.models) {
      const models = response.data.models.map((m) => m.name);
      return {
        reachable: true,
        models,
      };
    }

    return { reachable: true };
  } catch (error) {
    logger.warn('Ollama health check failed', { error: error.message });
    return { reachable: false };
  }
};

const retryMaterialGeneration = async (req, res, next) => {
  try {
    const { materialId } = req.params;
    const tokenStudentId = req.student.id;

    const material = await LearningMaterial.findOne({
      'structured_material.material_id': materialId,
    });

    if (!material) {
      return res.status(404).json({
        success: false,
        error: 'Material not found',
        code: 'NOT_FOUND',
      });
    }

    if (material.structured_material.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only retry your own materials',
        code: 'FORBIDDEN',
      });
    }

    const latestProfile = await MasteryProfile.findOne({
      student_id: material.structured_material.student_id,
    }).sort({ submitted_at: -1 });

    if (!latestProfile) {
      return res.status(404).json({
        success: false,
        error: 'No learning profile found to use for retry',
        code: 'NOT_FOUND',
      });
    }

    const sm = material.structured_material;
    const gapData = {
      topic: sm.topic,
      topic_id: sm.topic_id,
      gap_type: sm.gap_type,
    };

    const newJobId = 'JOB_' + Date.now();

    const retryPayload = {
      student_id: sm.student_id,
      analysis_timestamp: latestProfile.analysis_timestamp?.toISOString() || new Date().toISOString(),
      mastery_profile: {
        overall_mastery_score: latestProfile.overall_mastery_score,
        knowledge_gaps: [gapData],
        strengths: latestProfile.strengths || [],
      },
      recommendations: latestProfile.recommendations,
      data_sources: latestProfile.data_sources,
      job_id: newJobId,
    };

    const generationJob = new GenerationJob({
      job_id: newJobId,
      student_id: sm.student_id,
      profile_id: latestProfile._id,
      status: 'processing',
      gaps_total: 1,
      gaps_queued: 1,
      n8n_triggered_at: new Date(),
      n8n_workflow_id: 'retry_workflow',
    });

    await generationJob.save();

    try {
      await n8nService.triggerMaterialGeneration(retryPayload);

      logger.info('Retry triggered successfully', {
        original_material_id: materialId,
        new_job_id: newJobId,
      });

      return apiResponse.accepted(res, {
        job_id: newJobId,
        original_material_id: materialId,
        topic: sm.topic,
        check_status_at: '/api/agent/jobs/' + newJobId,
      }, 'Material regeneration queued');
    } catch (n8nError) {
      generationJob.status = 'failed';
      generationJob.error = n8nError.message;
      await generationJob.save();

      if (n8nError instanceof ServiceError && n8nError.code === 'N8N_OFFLINE') {
        return res.status(503).json({
          success: false,
          error: n8nError.message,
          code: n8nError.code,
          fix: n8nError.fix,
        });
      }

      return res.status(503).json({
        success: false,
        error: 'Failed to retry material generation',
        code: 'RETRY_FAILED',
        fix: 'Check n8n service status and try again.',
      });
    }
  } catch (error) {
    next(error);
  }
};

const completeJob = async (req, res, next) => {
  try {
    const { jobId } = req.params;
    const tokenStudentId = req.student.id;

    const job = await GenerationJob.findOne({ job_id: jobId });

    if (!job) {
      return res.status(404).json({
        success: false,
        error: 'Job not found',
        code: 'NOT_FOUND',
      });
    }

    if (job.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own jobs',
        code: 'FORBIDDEN',
      });
    }

    if (job.status === 'completed' || job.status === 'failed') {
      return apiResponse.success(res, job);
    }

    const profile = await MasteryProfile.findById(job.profile_id);
    const gapTopicIds = profile?.knowledge_gaps?.map(g => g.topic_id) || [];

    const matchingMaterials = await LearningMaterial.find({
      'structured_material.student_id': job.student_id,
      'structured_material.topic_id': { $in: gapTopicIds },
    }).select('_id structured_material.material_id structured_material.topic_id');

    const materialCount = matchingMaterials.length;

    logger.info('Job completion check', {
      job_id: jobId,
      student_id: job.student_id,
      gap_topic_ids: gapTopicIds,
      materials_found: materialCount,
      material_ids: matchingMaterials.map(m => m.structured_material.material_id),
      status: job.status,
    });

    job.gaps_completed = materialCount;
    job.materials_generated = materialCount;

    if (materialCount >= job.gaps_total) {
      job.status = 'completed';
      job.completed_at = new Date();
    } else if (materialCount > 0) {
      job.status = 'processing';
    }

    await job.save();

    return apiResponse.success(res, job);
  } catch (error) {
    next(error);
  }
};

const updateJobStatus = async (req, res, next) => {
  try {
    const { jobId } = req.params;
    const { status } = req.body;
    const tokenStudentId = req.student.id;

    const validStatuses = ['queued', 'processing', 'completed', 'failed', 'partial', 'closed'];
    if (!validStatuses.includes(status)) {
      return res.status(400).json({
        success: false,
        error: `Invalid status. Must be one of: ${validStatuses.join(', ')}`,
        code: 'BAD_REQUEST',
      });
    }

    const job = await GenerationJob.findOne({ job_id: jobId });

    if (!job) {
      return res.status(404).json({
        success: false,
        error: 'Job not found',
        code: 'NOT_FOUND',
      });
    }

    if (job.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only update your own jobs',
        code: 'FORBIDDEN',
      });
    }

    job.status = status;
    await job.save();

    logger.info('Job status updated', {
      job_id: jobId,
      new_status: status,
      student_id: job.student_id,
    });

    return apiResponse.success(res, job);
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getAgentLogs,
  getJobStatus,
  getJobsByStudent,
  getGlobalStats,
  checkHealth,
  retryMaterialGeneration,
  completeJob,
  updateJobStatus,
};
