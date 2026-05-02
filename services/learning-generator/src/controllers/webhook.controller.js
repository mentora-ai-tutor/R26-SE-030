const LearningMaterial = require('../models/LearningMaterial');
const GenerationJob = require('../models/GenerationJob');
const MasteryProfile = require('../models/MasteryProfile');
const AgentLog = require('../models/AgentLog');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');
const userServiceClient = require('../services/userService.client');

const receiveMaterialCallback = async (req, res, next) => {
  try {
    const materialData = req.body;
    const { student_id, job_id, material_id, topic, topic_id, gap_type } = materialData;

    logger.info('Received n8n material callback', {
      student_id,
      job_id,
      material_id,
      topic,
    });

    const existingMaterial = await LearningMaterial.findOne({
      'structured_material.material_id': material_id,
    });

    if (existingMaterial) {
      logger.warn('Material already exists, updating', { material_id });
      existingMaterial.structured_material = {
        ...existingMaterial.structured_material,
        ...materialData,
        material_id,
        student_id,
        topic,
        topic_id,
        gap_type,
        generated_at: materialData.generated_at || new Date(),
      };
      await existingMaterial.save();
      return apiResponse.success(res, {
        material_id,
        action: 'updated',
      }, 'Material updated successfully');
    }

    const learningMaterial = new LearningMaterial({
      structured_material: {
        material_id,
        student_id,
        topic,
        topic_id,
        gap_type,
        difficulty_level: materialData.difficulty_level,
        generated_at: materialData.generated_at || new Date(),
        generation_models: materialData.generation_models || {},
        lesson: materialData.lesson || {},
        assessment: materialData.assessment || {},
        personalisation: materialData.personalisation || {},
        study_plan: materialData.study_plan || {},
        agentic_metadata: materialData.agentic_metadata || {},
        quality_flags: materialData.quality_flags || {},
      },
    });

    await learningMaterial.save();

    logger.info('Learning material saved', {
      material_id,
      student_id,
      topic,
    });

    if (materialData.agentic_metadata) {
      const agentLog = new AgentLog({
        log_id: `LOG_${material_id}_${Date.now()}`,
        student_id,
        topic,
        llm_model: materialData.generation_models?.llm,
        slm_model: materialData.generation_models?.slm,
        agent_quality_score: materialData.agentic_metadata.quality_review_agent?.quality_score,
        content_validation_score: materialData.agentic_metadata.content_validation_agent?.validation_score,
        agent_retry_count: materialData.agentic_metadata.quality_review_agent?.retry_count || 0,
        timestamp: new Date(),
      });
      await agentLog.save();
    }

    if (job_id) {
      const job = await GenerationJob.findOne({ job_id });
      if (job) {
        job.gaps_completed = (job.gaps_completed || 0) + 1;
        job.materials_generated = (job.materials_generated || 0) + 1;

        if (job.gaps_completed >= job.gaps_total) {
          job.status = 'completed';
          job.completed_at = new Date();
        }

        await job.save();
        logger.info('Generation job updated', {
          job_id,
          gaps_completed: job.gaps_completed,
          status: job.status,
        });
      }
    }

    userServiceClient.updateStudentStatsAsync(student_id, {
      materials_generated_increment: 1,
    });

    return apiResponse.created(res, {
      material_id,
      student_id,
      topic,
      job_id,
    }, 'Material received and saved successfully');
  } catch (error) {
    next(error);
  }
};

const receiveBatchCallback = async (req, res, next) => {
  try {
    const { student_id, job_id, materials, workflow_id, execution_id } = req.body;

    logger.info('Received n8n batch callback', {
      student_id,
      job_id,
      materials_count: materials?.length || 0,
    });

    if (job_id) {
      const job = await GenerationJob.findOne({ job_id });
      if (job) {
        job.n8n_workflow_id = workflow_id || job.n8n_workflow_id;
        job.n8n_execution_id = execution_id || job.n8n_execution_id;
        await job.save();
      }
    }

    const results = {
      success: 0,
      failed: 0,
      errors: [],
    };

    for (const materialData of materials || []) {
      try {
        const { material_id, topic, topic_id, gap_type } = materialData;

        const existingMaterial = await LearningMaterial.findOne({
          'structured_material.material_id': material_id,
        });

        if (existingMaterial) {
          existingMaterial.structured_material = {
            ...existingMaterial.structured_material,
            ...materialData,
            material_id,
            student_id,
            topic,
            topic_id,
            gap_type,
            generated_at: materialData.generated_at || new Date(),
          };
          await existingMaterial.save();
          results.success++;
          continue;
        }

        const learningMaterial = new LearningMaterial({
          structured_material: {
            material_id,
            student_id,
            topic,
            topic_id,
            gap_type,
            difficulty_level: materialData.difficulty_level,
            generated_at: materialData.generated_at || new Date(),
            generation_models: materialData.generation_models || {},
            lesson: materialData.lesson || {},
            assessment: materialData.assessment || {},
            personalisation: materialData.personalisation || {},
            study_plan: materialData.study_plan || {},
            agentic_metadata: materialData.agentic_metadata || {},
            quality_flags: materialData.quality_flags || {},
          },
        });

        await learningMaterial.save();
        results.success++;

        if (materialData.agentic_metadata) {
          const agentLog = new AgentLog({
            log_id: `LOG_${material_id}_${Date.now()}`,
            student_id,
            topic,
            llm_model: materialData.generation_models?.llm,
            slm_model: materialData.generation_models?.slm,
            agent_quality_score: materialData.agentic_metadata.quality_review_agent?.quality_score,
            content_validation_score: materialData.agentic_metadata.content_validation_agent?.validation_score,
            agent_retry_count: materialData.agentic_metadata.quality_review_agent?.retry_count || 0,
            timestamp: new Date(),
          });
          await agentLog.save();
        }
      } catch (materialError) {
        results.failed++;
        results.errors.push({
          material_id: materialData.material_id || 'unknown',
          error: materialError.message,
        });
        logger.error('Failed to save material from batch', {
          material_id: materialData.material_id,
          error: materialError.message,
        });
      }
    }

    if (job_id) {
      const job = await GenerationJob.findOne({ job_id });
      if (job) {
        job.gaps_completed = (job.gaps_completed || 0) + results.success;
        job.gaps_failed = (job.gaps_failed || 0) + results.failed;
        job.materials_generated = (job.materials_generated || 0) + results.success;
        job.materials_failed = (job.materials_failed || 0) + results.failed;

        if (job.gaps_completed >= job.gaps_total) {
          job.status = results.failed > 0 ? 'partial' : 'completed';
          job.completed_at = new Date();
        }

        await job.save();
      }
    }

    userServiceClient.updateStudentStatsAsync(student_id, {
      materials_generated_increment: results.success,
    });

    return apiResponse.created(res, {
      student_id,
      job_id,
      results,
    }, 'Batch materials processed');
  } catch (error) {
    next(error);
  }
};

const receiveJobStatusUpdate = async (req, res, next) => {
  try {
    const { job_id, status, workflow_id, execution_id, error, progress } = req.body;

    logger.info('Received n8n job status update', {
      job_id,
      status,
    });

    const job = await GenerationJob.findOne({ job_id });

    if (!job) {
      return res.status(404).json({
        success: false,
        error: 'Job not found',
        code: 'JOB_NOT_FOUND',
      });
    }

    job.status = status || job.status;
    job.n8n_workflow_id = workflow_id || job.n8n_workflow_id;
    job.n8n_execution_id = execution_id || job.n8n_execution_id;

    if (status === 'completed') {
      job.completed_at = new Date();
    }

    if (status === 'failed' || error) {
      job.error = error || job.error;
    }

    if (progress) {
      job.gaps_completed = progress.completed || job.gaps_completed;
      job.gaps_failed = progress.failed || job.gaps_failed;
    }

    await job.save();

    return apiResponse.success(res, {
      job_id,
      status: job.status,
      updated_at: job.updated_at,
    }, 'Job status updated');
  } catch (error) {
    next(error);
  }
};

const handleProfileCallback = async (req, res, next) => {
  try {
    const { student_id, job_id, mastery_profile_id, status, n8n_response } = req.body;

    logger.info('Received mastery profile n8n callback', {
      student_id,
      job_id,
      mastery_profile_id,
    });

    if (mastery_profile_id) {
      const profile = await MasteryProfile.findById(mastery_profile_id);
      if (profile) {
        profile.n8n_triggered = true;
        profile.n8n_triggered_at = new Date();
        profile.n8n_response = n8n_response || profile.n8n_response;
        await profile.save();
      }
    }

    if (job_id) {
      const job = await GenerationJob.findOne({ job_id });
      if (job) {
        job.status = status || 'processing';
        job.n8n_triggered_at = new Date();
        await job.save();
      }
    }

    return apiResponse.success(res, {
      student_id,
      job_id,
      mastery_profile_id,
    }, 'Mastery profile callback processed');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  receiveMaterialCallback,
  receiveBatchCallback,
  receiveJobStatusUpdate,
  handleProfileCallback,
};
