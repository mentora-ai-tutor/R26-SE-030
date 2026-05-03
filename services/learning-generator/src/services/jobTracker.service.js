const mongoose = require('mongoose');
const LearningMaterial = require('../models/LearningMaterial');
const GenerationJob = require('../models/GenerationJob');
const logger = require('../utils/logger');

class JobTrackerService {
  constructor() {
    this.changeStream = null;
    this.pollInterval = null;
    this.isRunning = false;
  }

  start() {
    if (this.isRunning) {
      logger.warn('JobTrackerService is already running');
      return;
    }

    this.isRunning = true;

    try {
      const materialsCollection = mongoose.connection.collection('learning_materials');

      this.changeStream = materialsCollection.watch(
        [{ $match: { operationType: 'insert' } }],
        { fullDocument: 'updateLookup' }
      );

      this.changeStream.on('change', async (change) => {
        try {
          const doc = change.fullDocument;
          const studentId = doc.structured_material?.student_id;

          if (!studentId) return;

          await this.updateJobCounters(studentId);
        } catch (err) {
          logger.error('Error processing material insert event', { error: err.message });
        }
      });

      this.changeStream.on('error', (err) => {
        logger.error('Change stream error (falling back to polling)', { error: err.message });
        this.changeStream = null;
      });

      logger.info('JobTrackerService: change stream started');
    } catch (err) {
      logger.error('JobTrackerService: change stream not supported, using polling only', { error: err.message });
    }

    this.pollInterval = setInterval(async () => {
      try {
        await this.resyncActiveJobs();
      } catch (err) {
        logger.error('JobTrackerService: polling error', { error: err.message });
      }
    }, 10000);

    this.resyncActiveJobs();

    logger.info('JobTrackerService started — polling every 10s + change stream');
  }

  async updateJobCounters(studentId) {
    const collection = mongoose.connection.collection('generation_jobs');
    const activeJobRaw = await collection.findOne({
      $or: [
        { status: { $in: ['processing', 'queued'] } },
        { status: 'failed', error: { $regex: 'timed out|did not respond', $options: 'i' } },
      ],
      student_id: studentId,
    }, { sort: { created_at: -1 } });

    if (!activeJobRaw) return;

    await this.syncJobCounters(new GenerationJob(activeJobRaw));
  }

  async syncJobCounters(activeJob) {
    const jobCreatedAt = new Date(activeJob.created_at).getTime();

    const allMaterials = await LearningMaterial.find({
      'structured_material.student_id': activeJob.student_id,
    }).select('structured_material.topic_id structured_material.generated_at').lean();

    const filteredMaterials = allMaterials.filter(m => {
      const genAt = m.structured_material?.generated_at;
      if (!genAt) return false;
      return new Date(genAt).getTime() >= jobCreatedAt;
    });

    const actualMaterialCount = filteredMaterials.length;
    const actualTopics = [...new Set(
      filteredMaterials.map(m => m.structured_material?.topic_id).filter(Boolean)
    )];

    const wasCompleted = activeJob.status === 'completed' || activeJob.status === 'partial';
    const wasFailed = activeJob.status === 'failed';

    const update = {
      gaps_completed: actualTopics.length,
      materials_generated: actualMaterialCount,
      gap_topic_ids: actualTopics.filter(Boolean),
    };

    if (wasFailed) {
      update.error = undefined;
    }

    if (!wasCompleted && actualTopics.length >= activeJob.gaps_total) {
      update.status = 'completed';
      update.completed_at = new Date();
    } else if (!wasCompleted && activeJob.gaps_completed < activeJob.gaps_total) {
      update.status = 'processing';
      if (activeJob.error && activeJob.error.includes('timed out')) {
        update.error = undefined;
      }
    }

    await GenerationJob.updateOne({ _id: activeJob._id }, { $set: update });

    logger.info('Job counters updated', {
      job_id: activeJob.job_id,
      status: update.status || activeJob.status,
      gaps_completed: actualTopics.length,
      gaps_total: activeJob.gaps_total,
      materials_generated: actualMaterialCount,
    });

    return {
      job_id: activeJob.job_id,
      gaps_completed: actualTopics.length,
      materials_generated: actualMaterialCount,
      status: update.status || activeJob.status,
    };
  }

  async resyncActiveJobs() {
    const collection = mongoose.connection.collection('generation_jobs');
    const activeJobsRaw = await collection.find({
      $or: [
        { status: { $in: ['processing', 'queued'] } },
        { status: 'failed', error: { $regex: 'timed out|did not respond', $options: 'i' } },
      ],
    }).toArray();

    logger.info('JobTrackerService: resyncActiveJobs found jobs', { count: activeJobsRaw.length });

    if (activeJobsRaw.length === 0) return;

    for (const jobRaw of activeJobsRaw) {
      try {
        const jobDoc = new GenerationJob(jobRaw);
        await this.syncJobCounters(jobDoc);
      } catch (err) {
        logger.error('Failed to resync job', { job_id: jobRaw.job_id, error: err.message });
      }
    }
  }

  stop() {
    if (this.changeStream) {
      this.changeStream.close();
      this.changeStream = null;
    }
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.isRunning = false;
    logger.info('JobTrackerService stopped');
  }
}

module.exports = new JobTrackerService();
