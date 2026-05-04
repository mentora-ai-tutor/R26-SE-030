const { Student } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { activity } = require('../utils/activityLogger');

const getMe = async (req, res) => {
  await activity.profileView(req.student._id, req);
  return sendSuccess(res, req.student.toSafeObject());
};

const updateProfile = async (req, res, next) => {
  try {
    const { name, profile } = req.body;
    const studentId = req.student._id;

    const updateFields = {};
    const updatedFields = [];

    if (name) {
      updateFields.name = name;
      updatedFields.push('name');
    }
    if (profile) {
      if (profile.avatar_url !== undefined) {
        updateFields['profile.avatar_url'] = profile.avatar_url;
        updatedFields.push('profile.avatar_url');
      }
      if (profile.bio !== undefined) {
        updateFields['profile.bio'] = profile.bio;
        updatedFields.push('profile.bio');
      }
      if (profile.java_level !== undefined) {
        updateFields['profile.java_level'] = profile.java_level;
        updatedFields.push('profile.java_level');
      }
      if (profile.institution !== undefined) {
        updateFields['profile.institution'] = profile.institution;
        updatedFields.push('profile.institution');
      }
      if (profile.country !== undefined) {
        updateFields['profile.country'] = profile.country;
        updatedFields.push('profile.country');
      }
    }

    const updatedStudent = await Student.findByIdAndUpdate(
      studentId,
      { $set: updateFields },
      { new: true, runValidators: true }
    );

    await activity.profileUpdate(studentId, req, updatedFields);

    logger.info(`Profile updated for student: ${updatedStudent.email}`);

    return sendSuccess(res, updatedStudent.toSafeObject(), 'Profile updated successfully');
  } catch (error) {
    next(error);
  }
};

const updatePassword = async (req, res, next) => {
  try {
    const { current_password, new_password } = req.body;
    const studentId = req.student._id;

    const student = await Student.findById(studentId).select('+password');

    const isPasswordValid = await student.comparePassword(current_password);

    if (!isPasswordValid) {
      return sendError(res, 'Current password is incorrect', 400, 'INVALID_PASSWORD');
    }

    student.password = new_password;
    student.refresh_token = null;
    await student.save();

    await activity.passwordChange(studentId, req);

    logger.info(`Password updated for student: ${student.email}`);

    return sendSuccess(
      res,
      null,
      'Password updated. Please log in again.'
    );
  } catch (error) {
    next(error);
  }
};

const updateStats = async (req, res, next) => {
  try {
    const { overall_mastery_score, total_materials_generated_increment, total_sessions_increment } = req.body;
    const studentId = req.student._id;

    const updateFields = {
      last_active: new Date(),
    };

    const incFields = {};

    if (overall_mastery_score !== undefined) {
      updateFields['stats.overall_mastery_score'] = overall_mastery_score;
      updateFields['stats.last_mastery_update'] = new Date();
    }

    if (total_materials_generated_increment !== undefined && total_materials_generated_increment > 0) {
      incFields['stats.total_materials_generated'] = total_materials_generated_increment;
    }

    if (total_sessions_increment !== undefined && total_sessions_increment > 0) {
      incFields['stats.total_sessions'] = total_sessions_increment;
    }

    const updateQuery = { $set: updateFields };
    if (Object.keys(incFields).length > 0) {
      updateQuery.$inc = incFields;
    }

    const updatedStudent = await Student.findByIdAndUpdate(
      studentId,
      updateQuery,
      { new: true }
    );

    await activity.statsUpdate(studentId, req, {
      overall_mastery_score,
      total_materials_generated_increment,
      total_sessions_increment,
    });

    return sendSuccess(res, {
      overall_mastery_score: updatedStudent.stats.overall_mastery_score,
      total_materials_generated: updatedStudent.stats.total_materials_generated,
      total_sessions: updatedStudent.stats.total_sessions,
      last_mastery_update: updatedStudent.stats.last_mastery_update,
    }, 'Stats updated successfully');
  } catch (error) {
    next(error);
  }
};

const getSummary = async (req, res) => {
  const student = req.student;

  return sendSuccess(res, {
    student_id: student.student_id,
    name: student.name,
    email: student.email,
    role: student.role,
    profile: {
      java_level: student.profile.java_level,
      avatar_url: student.profile.avatar_url,
    },
    stats: student.stats,
    enrolled_at: student.enrolled_at,
    last_active: student.last_active,
  });
};

// Get User Preferences
const getPreferences = async (req, res) => {
  return sendSuccess(res, req.student.preferences);
};

// Update User Preferences
const updatePreferences = async (req, res, next) => {
  try {
    const { notifications, theme, language, timezone } = req.body;
    const studentId = req.student._id;

    const updateFields = {};

    if (notifications) {
      if (notifications.email !== undefined) updateFields['preferences.notifications.email'] = notifications.email;
      if (notifications.push !== undefined) updateFields['preferences.notifications.push'] = notifications.push;
      if (notifications.marketing !== undefined) updateFields['preferences.notifications.marketing'] = notifications.marketing;
    }
    if (theme) updateFields['preferences.theme'] = theme;
    if (language) updateFields['preferences.language'] = language;
    if (timezone) updateFields['preferences.timezone'] = timezone;

    const updatedStudent = await Student.findByIdAndUpdate(
      studentId,
      { $set: updateFields },
      { new: true, runValidators: true }
    );

    await activity.apiCall(studentId, req, '/api/students/me/preferences');

    logger.info(`Preferences updated for student: ${updatedStudent.email}`);

    return sendSuccess(res, updatedStudent.preferences, 'Preferences updated successfully');
  } catch (error) {
    next(error);
  }
};

// Delete Account (Self)
const deleteAccount = async (req, res, next) => {
  try {
    const { password } = req.body;
    const studentId = req.student._id;

    const student = await Student.findById(studentId).select('+password');

    // Verify password
    const isPasswordValid = await student.comparePassword(password);
    if (!isPasswordValid) {
      return sendError(res, 'Password is incorrect', 400, 'INVALID_PASSWORD');
    }

    // Soft delete
    await student.softDelete();

    // Revoke all sessions
    const { UserSession } = require('../models');
    await UserSession.updateMany(
      { student: studentId, is_active: true },
      { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'account_self_deleted' } }
    );

    logger.info(`Student self-deleted account: ${student.email}`);

    return sendSuccess(res, null, 'Account deleted successfully');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getMe,
  updateProfile,
  updatePassword,
  updateStats,
  getSummary,
  getPreferences,
  updatePreferences,
  deleteAccount,
};
