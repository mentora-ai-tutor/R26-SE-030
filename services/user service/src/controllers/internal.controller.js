const jwt = require('jsonwebtoken');
const config = require('../config/env');
const { Student, GithubCredential } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { logAuth } = require('../utils/auditLogger');
const ghCrypto = require('../utils/ghCrypto');

const verifyToken = async (req, res, _next) => {
  try {
    const { token } = req.body;

    let decoded;
    try {
      decoded = jwt.verify(token, config.jwt.secret);
    } catch (jwtError) {
      if (jwtError.name === 'TokenExpiredError') {
        return res.status(401).json({
          valid: false,
          error: 'Token expired',
        });
      }
      return res.status(401).json({
        valid: false,
        error: 'Token invalid or expired',
      });
    }

    const student = await Student.findById(decoded.id);

    if (!student) {
      return res.status(401).json({
        valid: false,
        error: 'Token invalid or expired',
      });
    }

    if (student.is_deleted) {
      return res.status(401).json({
        valid: false,
        error: 'Account has been deleted',
      });
    }

    if (!student.is_active) {
      return res.status(403).json({
        valid: false,
        error: 'Account deactivated',
      });
    }

    Student.findByIdAndUpdate(
      decoded.id,
      { last_active: new Date() },
      { validateBeforeSave: false }
    ).catch((err) => {
      logger.warn('Failed to update last_active:', err.message);
    });

    await logAuth.tokenVerified(student._id, req, req.requestId);

    logger.info(`Token verified for student: ${student.student_id} by internal service`);

    return res.status(200).json({
      valid: true,
      student: {
        student_id: student.student_id,
        name: student.name,
        email: student.email,
        role: student.role,
        stats: student.stats,
        is_active: student.is_active,
        last_active: student.last_active,
      },
    });
  } catch (error) {
    logger.error('Internal token verification error:', error.message);
    return res.status(401).json({
      valid: false,
      error: 'Token invalid or expired',
    });
  }
};

const getStudentById = async (req, res, next) => {
  try {
    const { studentId } = req.params;

    const student = await Student.findOne({ student_id: studentId, is_deleted: false });

    if (!student) {
      return sendError(res, 'Student not found', 404, 'STUDENT_NOT_FOUND');
    }

    if (!student.is_active) {
      return sendError(res, 'Student account is deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    logger.info(`Internal lookup for student: ${studentId}`);

    return sendSuccess(res, student.toSafeObject());
  } catch (error) {
    next(error);
  }
};

const updateStudentStats = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const {
      overall_mastery_score,
      materials_generated_increment,
    } = req.body;

    const student = await Student.findOne({ student_id: studentId, is_deleted: false });

    if (!student) {
      return sendError(res, 'Student not found', 404, 'STUDENT_NOT_FOUND');
    }

    if (!student.is_active) {
      return sendError(res, 'Student account is deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    const updateFields = {
      last_active: new Date(),
    };

    const incFields = {};

    if (overall_mastery_score !== undefined) {
      updateFields['stats.overall_mastery_score'] = overall_mastery_score;
      updateFields['stats.last_mastery_update'] = new Date();
    }

    if (materials_generated_increment !== undefined && materials_generated_increment > 0) {
      incFields['stats.total_materials_generated'] = materials_generated_increment;
    }

    const updateQuery = { $set: updateFields };
    if (Object.keys(incFields).length > 0) {
      updateQuery.$inc = incFields;
    }

    const updatedStudent = await Student.findOneAndUpdate(
      { student_id: studentId },
      updateQuery,
      { new: true }
    );

    logger.info(`Stats updated for student: ${studentId} by internal service`);

    return sendSuccess(res, {
      student_id: updatedStudent.student_id,
      stats: {
        overall_mastery_score: updatedStudent.stats.overall_mastery_score,
        total_materials_generated: updatedStudent.stats.total_materials_generated,
        total_sessions: updatedStudent.stats.total_sessions,
        last_mastery_update: updatedStudent.stats.last_mastery_update,
      },
    }, 'Stats updated successfully');
  } catch (error) {
    next(error);
  }
};

const getGithubCredential = async (req, res, next) => {
  try {
    const { studentId } = req.params;

    const cred = await GithubCredential.findOne({ student_id: studentId });
    if (!cred) {
      return sendError(res, 'GitHub credential not found', 404, 'CREDENTIAL_NOT_FOUND');
    }

    let accessToken;
    try {
      accessToken = ghCrypto.decrypt(
        { ciphertext: cred.ciphertext, iv: cred.iv, tag: cred.tag },
        studentId,
      );
    } catch (e) {
      logger.error('github credential decrypt failed:', e.message);
      return sendError(res, 'Failed to decrypt credential', 500, 'DECRYPTION_FAILED');
    }

    GithubCredential.findByIdAndUpdate(cred._id, { last_used_at: new Date() })
      .catch((err) => logger.warn('Failed to bump last_used_at:', err.message));

    logger.info(`internal: served github credential for student ${studentId}`);

    return sendSuccess(res, {
      access_token: accessToken,
      scopes: cred.scopes,
      gh_login: cred.gh_login,
      gh_user_id: cred.gh_user_id,
      linked_at: cred.linked_at,
    }, 'Credential retrieved');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  verifyToken,
  getStudentById,
  updateStudentStats,
  getGithubCredential,
};
