const MasteryProfile = require('../models/MasteryProfile');
const GenerationJob = require('../models/GenerationJob');
const n8nService = require('../services/n8n.service');
const userServiceClient = require('../services/userService.client');
const conceptGraphService = require('../services/conceptGraph.service');
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

    // effectiveGaps is the single source of truth for the gap count actually
    // sent to n8n — reused for the GenerationJob document below so the job
    // counters always match the augmented list (explicit resolved gaps +
    // injected implicit prerequisites).
    let effectiveGaps = mastery_profile.knowledge_gaps;

    try {
      const graph = await conceptGraphService.loadGraph();

      if (graph.size > 0) {
        const augmentation = await conceptGraphService.augmentGaps(
          mastery_profile.knowledge_gaps,
          mastery_profile.strengths || [],
          graph,
          conceptGraphService.embedder,
          conceptGraphService.ollamaClient
        );

        const coverageSnapshot = await conceptGraphService.computeCoverage(student_id, null);

        effectiveGaps = augmentation.effectiveGaps;

        masteryProfile.knowledge_gaps = augmentation.resolvedGaps;
        masteryProfile.augmented_profile = {
          implicit_gaps: augmentation.injectedGaps.map((g) => ({
            concept_id: g.resolved_concept_id,
            injected: true,
            reason: g.reason,
          })),
          unverified_prerequisites: augmentation.closure.unverified,
          coverage_snapshot: {
            totalNodes: coverageSnapshot.totalNodes,
            coveredNodes: coverageSnapshot.coveredNodes,
            coveragePct: coverageSnapshot.coveragePct,
          },
        };
        await masteryProfile.save();

        logger.info('Concept-graph gate applied', {
          student_id,
          gaps_total: effectiveGaps.length,
          implicit_gaps: augmentation.injectedGaps.length,
          unverified: augmentation.closure.unverified.length,
          coverage_pct: coverageSnapshot.coveragePct,
        });
      }
    } catch (gateError) {
      logger.warn('Concept-graph gate failed - continuing with raw gaps (fail-open)', {
        error: gateError.message,
        student_id,
      });
      effectiveGaps = mastery_profile.knowledge_gaps;
    }

    const jobId = 'JOB_' + Date.now();

    const generationJob = new GenerationJob({
      job_id: jobId,
      student_id,
      profile_id: masteryProfile._id,
      status: 'queued',
      gaps_total: effectiveGaps.length,
      gaps_queued: effectiveGaps.length,
      gap_topic_ids: effectiveGaps.map((g) => g.topic_id),
    });

    await generationJob.save();

    logger.info('Generation job created', { job_id: jobId, student_id });

    try {
      const n8nPayload = {
        student_id,
        analysis_timestamp: analysis_timestamp || new Date().toISOString(),
        mastery_profile: {
          ...mastery_profile,
          knowledge_gaps: effectiveGaps,
        },
        recommendations,
        data_sources,
        job_id: jobId,
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

      if (n8nError instanceof ServiceError && n8nError.code === 'N8N_OFFLINE') {
        generationJob.status = 'failed';
        generationJob.error = n8nError.message;
        await generationJob.save();

        return res.status(503).json({
          success: false,
          error: n8nError.message,
          code: n8nError.code,
          fix: n8nError.fix,
        });
      }

      if (n8nError instanceof ServiceError && n8nError.code === 'N8N_TIMEOUT') {
        generationJob.status = 'processing';
        generationJob.error = 'n8n response timed out, but processing continues in background';
        generationJob.n8n_triggered_at = new Date();
        await generationJob.save();

        masteryProfile.n8n_triggered = true;
        masteryProfile.n8n_triggered_at = new Date();
        await masteryProfile.save();

        logger.warn('n8n timed out but job remains active for background processing', {
          job_id: jobId,
          student_id,
        });

        return apiResponse.accepted(res, {
          job_id: jobId,
          student_id,
          gaps_queued: effectiveGaps.length,
          topics: effectiveGaps.map((g) => g.topic),
          check_status_at: '/api/agent/jobs/' + jobId,
          materials_available_at: '/api/materials/' + student_id,
        }, 'n8n response timed out, but LLM processing continues in background. Check status periodically.');
      }

      generationJob.status = 'failed';
      generationJob.error = n8nError.message;
      await generationJob.save();

      return res.status(503).json({
        success: false,
        error: 'Failed to trigger material generation',
        code: 'N8N_TRIGGER_FAILED',
        fix: 'Check n8n service status and try again.',
      });
    }

    userServiceClient.updateStudentStatsAsync(student_id, {
      materials_generated_increment: effectiveGaps.length,
    });

    return apiResponse.accepted(res, {
      job_id: jobId,
      student_id,
      gaps_queued: effectiveGaps.length,
      topics: effectiveGaps.map((g) => g.topic),
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
