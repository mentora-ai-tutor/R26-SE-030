const axios = require('axios');
const config = require('../config/env');
const ServiceError = require('../utils/ServiceError');
const logger = require('../utils/logger');

class UserServiceClient {
  constructor() {
    this.baseUrl = config.userService.url;
    this.internalKey = config.userService.internalKey;
    this.headers = {
      'X-Internal-Key': this.internalKey,
      'Content-Type': 'application/json',
    };
  }

  async verifyToken(token) {
    logger.debug('Verifying token via User Service', { url: `${this.baseUrl}/internal/auth/verify` });

    try {
      const response = await axios.post(
        `${this.baseUrl}/internal/auth/verify`,
        { token },
        {
          timeout: 10000,
          headers: this.headers,
        }
      );

      if (response.data.valid) {
        logger.debug('Token verified successfully', { student_id: response.data.student?.id });
        return {
          valid: true,
          student: response.data.student,
        };
      }

      logger.warn('Token verification failed', { valid: false });
      return {
        valid: false,
        error: response.data.error || 'Invalid token',
      };
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
        logger.error('User Service is offline - cannot verify token', {
          error: error.message,
          url: this.baseUrl,
        });
        throw new ServiceError(
          'USER_SERVICE_OFFLINE',
          503,
          'User Service is unavailable. Start mentora-user-service.',
          'User Service is offline. Start mentora-user-service.'
        );
      }

      if (error.code === 'ECONNABORTED' || error.message?.includes('timeout')) {
        logger.error('User Service timeout', { error: error.message });
        throw new ServiceError(
          'USER_SERVICE_TIMEOUT',
          503,
          'User Service request timed out.',
          'User Service may be overloaded. Try again in a moment.'
        );
      }

      if (error.response) {
        const status = error.response.status;
        const data = error.response.data;

        if (status === 401 || status === 403) {
          logger.warn('Token rejected by User Service', { status });
          throw new ServiceError(
            'AUTH_FAILED',
            status,
            data.error || 'Authentication failed',
            null
          );
        }

        logger.error('User Service error response', { status, data });
        throw new ServiceError(
          'USER_SERVICE_ERROR',
          status,
          data.error || 'User Service error',
          'Check User Service logs for details.'
        );
      }

      logger.error('User Service unexpected error', { error: error.message });
      throw new ServiceError(
        'USER_SERVICE_ERROR',
        500,
        `User Service error: ${error.message}`,
        null
      );
    }
  }

  async getStudent(studentId) {
    logger.debug('Fetching student from User Service', { student_id: studentId });

    try {
      const response = await axios.get(
        `${this.baseUrl}/internal/students/${studentId}`,
        {
          timeout: 10000,
          headers: this.headers,
        }
      );

      return response.data;
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
        logger.error('User Service offline - cannot fetch student', {
          error: error.message,
          student_id: studentId,
        });
        throw new ServiceError(
          'USER_SERVICE_OFFLINE',
          503,
          'User Service is unavailable. Start mentora-user-service.',
          'User Service is offline. Start mentora-user-service.'
        );
      }

      if (error.response) {
        logger.error('User Service student fetch error', {
          status: error.response.status,
          student_id: studentId,
        });
        throw new ServiceError(
          'USER_SERVICE_ERROR',
          error.response.status,
          'Failed to fetch student from User Service',
          null
        );
      }

      throw error;
    }
  }

  async updateStudentStats(studentId, stats) {
    logger.debug('Updating student stats via User Service', {
      student_id: studentId,
      stats,
    });

    try {
      const response = await axios.patch(
        `${this.baseUrl}/internal/students/${studentId}/stats`,
        stats,
        {
          timeout: 10000,
          headers: this.headers,
        }
      );

      logger.info('Student stats updated', {
        student_id: studentId,
        stats,
        status: response.status,
      });

      return response.data;
    } catch (error) {
      if (error.code === 'ECONNREFUSED' || error.code === 'ENOTFOUND') {
        logger.error('User Service offline - cannot update stats (fire and forget)', {
          error: error.message,
          student_id: studentId,
        });
        return null;
      }

      logger.warn('Failed to update student stats', {
        error: error.message,
        student_id: studentId,
      });
      return null;
    }
  }

  updateStudentStatsAsync(studentId, stats) {
    this.updateStudentStats(studentId, stats).catch((error) => {
      logger.error('Fire-and-forget stats update failed', {
        error: error.message,
        student_id: studentId,
      });
    });
  }

  async checkHealth() {
    try {
      const response = await axios.get(`${this.baseUrl}/health`, {
        timeout: 5000,
      });
      return {
        reachable: response.status >= 200 && response.status < 300,
        status: response.status,
      };
    } catch (error) {
      logger.warn('User Service health check failed', { error: error.message });
      return { reachable: false };
    }
  }
}

module.exports = new UserServiceClient();