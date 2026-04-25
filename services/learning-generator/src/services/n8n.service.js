const axios = require('axios');
const config = require('../config/env');
const ServiceError = require('../utils/ServiceError');
const logger = require('../utils/logger');

class N8nService {
  constructor() {
    this.baseUrl = config.n8n.baseUrl;
    this.webhookLearnerProfile = config.n8n.webhookLearnerProfile;
    this.webhookGetMaterials = config.n8n.webhookGetMaterials;
    this.timeoutMs = config.n8n.timeoutMs;
  }

  async triggerMaterialGeneration(masteryProfile) {
    const payload = {
      student_id: masteryProfile.student_id,
      analysis_timestamp: masteryProfile.analysis_timestamp || new Date().toISOString(),
      mastery_profile: {
        overall_mastery_score: masteryProfile.mastery_profile?.overall_mastery_score,
        knowledge_gaps: masteryProfile.mastery_profile?.knowledge_gaps || [],
        strengths: masteryProfile.mastery_profile?.strengths || [],
      },
      recommendations: masteryProfile.recommendations,
      data_sources: masteryProfile.data_sources,
    };

    logger.info('Triggering n8n material generation', {
      student_id: masteryProfile.student_id,
      gaps_count: payload.mastery_profile.knowledge_gaps.length,
    });

    try {
      const response = await axios.post(this.webhookLearnerProfile, payload, {
        timeout: this.timeoutMs,
        headers: {
          'Content-Type': 'application/json',
        },
      });

      logger.info('n8n webhook triggered successfully', {
        student_id: masteryProfile.student_id,
        status: response.status,
      });

      return response.data;
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
        logger.error('n8n service is offline', { error: error.message });
        throw new ServiceError(
          'N8N_OFFLINE',
          503,
          'n8n workflow is offline. Run: npx n8n start',
          'Start the n8n service to process learning material generation.'
        );
      }

      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        logger.error('n8n request timed out', { error: error.message });
        throw new ServiceError(
          'N8N_TIMEOUT',
          504,
          'n8n did not respond in time. LLM may be overloaded.',
          'Wait a few minutes and check n8n workflow status. LLM processing takes 2-10 minutes.'
        );
      }

      if (error.response) {
        const status = error.response.status;
        const data = error.response.data;
        logger.error('n8n webhook error', {
          status,
          data,
          student_id: masteryProfile.student_id,
        });
        throw new ServiceError(
          'N8N_ERROR',
          status,
          `n8n returned error: ${JSON.stringify(data)}`,
          'Check n8n workflow execution logs for details.'
        );
      }

      logger.error('n8n unexpected error', { error: error.message });
      throw new ServiceError(
        'N8N_ERROR',
        500,
        `n8n unexpected error: ${error.message}`,
        'Check n8n service logs for more information.'
      );
    }
  }

  async getMaterialsByStudent(studentId) {
    logger.debug('Fetching materials from n8n', { student_id: studentId });

    try {
      const response = await axios.get(`${this.webhookGetMaterials}/${studentId}`, {
        timeout: 30000,
        headers: {
          'Content-Type': 'application/json',
        },
      });

      return response.data;
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
        logger.warn('n8n service unavailable for material fetch', { student_id: studentId });
        return [];
      }

      if (error.response) {
        logger.warn('n8n material fetch returned error', {
          status: error.response.status,
          student_id: studentId,
        });
        return [];
      }

      logger.error('n8n material fetch error', { error: error.message });
      return [];
    }
  }

  async checkHealth() {
    try {
      const response = await axios.get(this.baseUrl, {
        timeout: 5000,
      });
      return { reachable: response.status >= 200 && response.status < 300 };
    } catch (error) {
      logger.warn('n8n health check failed', { error: error.message });
      return { reachable: false };
    }
  }
}

module.exports = new N8nService();