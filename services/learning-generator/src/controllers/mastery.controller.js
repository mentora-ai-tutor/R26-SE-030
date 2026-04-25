const MasteryProfile = require('../models/MasteryProfile');
const GenerationJob = require('../models/GenerationJob');
const n8nService = require('../services/n8n.service');
const userServiceClient = require('../services/userService.client');
const ServiceError = require('../utils/ServiceError');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');

const submitMasteryProfile = async (req, res, next) => {
  try {
    const { student_id, mastery_profile, analysis_timestamp, recommendations, data_sources } = req.body;
    const tokenStudentId = req.student.id;

    if (student_id !== tokenStudentId) {
      logger.warn('Student ID mismatch in mastery submission', {
        body_student_id: student_id,
        token_student_id: tokenStudentId,
      });
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only submit your own mastery profile',
        code: 'FORBIDDEN',
      });
    }

    const masteryProfile = new MasteryProfile({
      student_id,
      analysis_timestamp: analysis_timestamp ? new Date(analysis_timestamp) : new Date(),
      overall_mastery_score: mastery_profile.overall_mastery_score,
      knowledge_gaps: mastery_profile.knowledge_gaps,
      strengths: mastery_profile.strengths || [],
      recommendations: recommendations,
      data_sources: data_sources,
      submission_ip: req.ip,
      n8n_triggered: false,
    });

    await masteryProfile.save();

    logger.info('Mastery profile saved', {
      profile_id: masteryProfile._id,
      student_id,
      gaps_count: mastery_profile.knowledge_gaps.length,
    });

    const jobId = 'JOB_' + Date.now();

    const generationJob = new GenerationJob({
      job_id: jobId,
      student_id,
      mastery_profile_id: masteryProfile._id,
      status: 'queued',
      gaps_total: mastery_profile.knowledge_gaps.length,
      gaps_queued: mastery_profile.knowledge_gaps.length,
    });

    await generationJob.save();

    logger.info('Generation job created', { job_id: jobId, student_id });

    try {
      const n8nPayload = {
        student_id,
        analysis_timestamp: analysis_timestamp || new Date().toISOString(),
        mastery_profile,
        recommendations,
        data_sources,
      };

      await n8nService.triggerMaterialGeneration(n8nPayload);

      masteryProfile.n8n_triggered = true;
      masteryProfile.n8n_triggered_at = new Date();
      await masteryProfile.save();

      generationJob.status = 'processing';
      generationJob.n8n_triggered_at = new Date();
      await generationJob.save();

      logger.info('n8n triggered successfully', {
        job_id: jobId,
        student_id,
      });
    } catch (n8nError) {
      logger.error('n8n trigger failed', {
        error: n8nError.message,
        job_id: jobId,
        student_id,
      });

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
        error: 'Failed to trigger material generation',
        code: 'N8N_TRIGGER_FAILED',
        fix: 'Check n8n service status and try again.',
      });
    }

    userServiceClient.updateStudentStatsAsync(student_id, {
      materials_generated_increment: mastery_profile.knowledge_gaps.length,
    });

    return apiResponse.accepted(res, {
      job_id: jobId,
      student_id,
      gaps_queued: mastery_profile.knowledge_gaps.length,
      topics: mastery_profile.knowledge_gaps.map((g) => g.topic),
      check_status_at: '/api/agent/jobs/' + jobId,
      materials_available_at: '/api/materials/' + student_id,
    }, 'Material generation queued. LLM processing takes 2-10 minutes.');
  } catch (error) {
    next(error);
  }
};

const getMasteryProfile = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own mastery profile',
        code: 'FORBIDDEN',
      });
    }

    const profile = await MasteryProfile.findOne({
      student_id: studentId,
    }).sort({ submitted_at: -1 });

    if (!profile) {
      return res.status(404).json({
        success: false,
        error: 'No mastery profile found for this student',
        code: 'NOT_FOUND',
      });
    }

    return apiResponse.success(res, profile);
  } catch (error) {
    next(error);
  }
};

const getMasteryHistory = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own mastery history',
        code: 'FORBIDDEN',
      });
    }

    const limit = parseInt(req.query.limit, 10) || 10;
    const page = parseInt(req.query.page, 10) || 1;
    const skip = (page - 1) * limit;

    const [profiles, total] = await Promise.all([
      MasteryProfile.find({ student_id: studentId })
        .sort({ submitted_at: -1 })
        .skip(skip)
        .limit(limit)
        .select('overall_mastery_score submitted_at'),
      MasteryProfile.countDocuments({ student_id: studentId }),
    ]);

    const items = profiles.map((p) => ({
      id: p._id,
      overall_mastery_score: p.overall_mastery_score,
      gaps_count: p.knowledge_gaps?.length || 0,
      submitted_at: p.submitted_at,
    }));

    return apiResponse.paginated(res, items, {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    });
  } catch (error) {
    next(error);
  }
};

module.exports = {
  submitMasteryProfile,
  getMasteryProfile,
  getMasteryHistory,
};