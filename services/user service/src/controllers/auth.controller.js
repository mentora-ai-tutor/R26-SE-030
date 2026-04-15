const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const config = require('../config/env');
const { Student, PasswordResetToken, EmailVerificationToken, UserSession } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { logAuth } = require('../utils/auditLogger');
const { activity } = require('../utils/activityLogger');
const { parseDeviceInfo, generateDeviceId, getDeviceName } = require('../utils/deviceParser');

// Generate tokens
const generateTokens = async (student, deviceInfo, req) => {
  const accessToken = jwt.sign(
    { id: student._id, student_id: student.student_id, role: student.role },
    config.jwt.secret,
    { expiresIn: config.jwt.expiresIn }
  );

  const refreshToken = jwt.sign(
    { id: student._id, student_id: student.student_id, type: 'refresh' },
    config.jwt.refreshSecret,
    { expiresIn: config.jwt.refreshExpiresIn }
  );

  // Hash and save refresh token to student
  const hashedRefreshToken = await Student.hashRefreshToken(refreshToken);
  student.refresh_token = hashedRefreshToken;
  await student.save({ validateBeforeSave: false });

  // Create session record
  const sessionToken = crypto.randomBytes(32).toString('hex');
  const deviceId = generateDeviceId(req.headers['user-agent'], req.ip);

  await UserSession.create({
    student: student._id,
    session_token: sessionToken,
    refresh_token: refreshToken,
    device_id: deviceId,
    device_name: getDeviceName(deviceInfo),
    device_type: deviceInfo.type,
    os: deviceInfo.os,
    browser: deviceInfo.browser,
    browser_version: deviceInfo.browser_version,
    ip_address: req.ip,
    expires_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000), // 7 days
  });

  return { accessToken, refreshToken, sessionToken };
};

// Register
const register = async (req, res, next) => {
  try {
    const { name, email, password, student_id, profile } = req.body;
    const requestId = req.requestId;

    const existingStudent = await Student.findOne({ email: email.toLowerCase(), is_deleted: false });
    if (existingStudent) {
      return sendError(res, 'Email already registered', 409, 'EMAIL_EXISTS');
    }

    const studentData = {
      name,
      email,
      password,
      profile: profile || {},
    };

    if (student_id) {
      const existingStudentId = await Student.findOne({ student_id, is_deleted: false });
      if (existingStudentId) {
        return sendError(res, 'Student ID already exists', 409, 'STUDENT_ID_EXISTS');
      }
    }

    const student = new Student(studentData);
    await student.save();

    // Generate verification token
    const verificationToken = await EmailVerificationToken.create({
      student: student._id,
      email: student.email,
      expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000), // 24 hours
    });

    // Log audit
    await logAuth.register(student._id, req, requestId, 'SUCCESS', 'User registered successfully');

    // TODO: Send verification email here
    logger.info(`Verification token created for ${student.email}: ${verificationToken.token}`);

    // Generate tokens (user can log in immediately but will be prompted to verify)
    const deviceInfo = parseDeviceInfo(req.headers['user-agent']);
    const { accessToken, refreshToken } = await generateTokens(student, deviceInfo, req);

    logger.info(`New student registered: ${student.email}`);

    return sendSuccess(
      res,
      {
        student: student.toSafeObject(),
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_in: config.jwt.expiresIn,
        requires_verification: true,
      },
      'Registration successful. Please verify your email.',
      201
    );
  } catch (error) {
    next(error);
  }
};

// Login
const login = async (req, res, next) => {
  try {
    const { email, password } = req.body;
    const requestId = req.requestId;

    const student = await Student.findOne({ email: email.toLowerCase(), is_deleted: false })
      .select('+password +login_attempts +lock_until');

    if (!student) {
      await logAuth.loginFailed(email, req, requestId, 'User not found');
      return sendError(res, 'Invalid email or password', 401, 'INVALID_CREDENTIALS');
    }

    // Check if account is locked
    if (student.isLocked) {
      const lockTimeRemaining = Math.ceil((student.lock_until - Date.now()) / 1000 / 60);
      await logAuth.loginFailed(email, req, requestId, `Account locked for ${lockTimeRemaining} minutes`);
      return sendError(
        res,
        `Account is locked. Please try again in ${lockTimeRemaining} minutes.`,
        423,
        'ACCOUNT_LOCKED'
      );
    }

    if (!student.is_active) {
      await logAuth.loginFailed(email, req, requestId, 'Account deactivated');
      return sendError(res, 'Account has been deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    const isPasswordValid = await student.comparePassword(password);

    if (!isPasswordValid) {
      await student.incrementLoginAttempts();
      const attemptsLeft = 5 - (student.login_attempts + 1);

      await logAuth.loginFailed(
        email,
        req,
        requestId,
        `Invalid password. ${attemptsLeft > 0 ? `${attemptsLeft} attempts remaining` : 'Account locked'}`
      );

      if (student.login_attempts + 1 >= 5) {
        await logAuth.accountLocked(student._id, req, requestId, 'Too many failed login attempts');
      }

      return sendError(res, 'Invalid email or password', 401, 'INVALID_CREDENTIALS');
    }

    // Reset login attempts on successful login
    if (student.login_attempts > 0) {
      await student.resetLoginAttempts();
    }

    // Update timestamps
    student.last_login = new Date();
    student.last_active = new Date();
    await student.save({ validateBeforeSave: false });

    // Generate tokens
    const deviceInfo = parseDeviceInfo(req.headers['user-agent']);
    const { accessToken, refreshToken, sessionToken } = await generateTokens(student, deviceInfo, req);

    // Log activities
    await logAuth.login(student._id, req, requestId);
    await activity.login(student._id, req);

    logger.info(`Student logged in: ${student.email}`);

    return sendSuccess(res, {
      student: student.toSafeObject(),
      access_token: accessToken,
      refresh_token: refreshToken,
      session_token: sessionToken,
      expires_in: config.jwt.expiresIn,
    });
  } catch (error) {
    next(error);
  }
};

// Refresh Token
const refresh = async (req, res, next) => {
  try {
    const { refresh_token } = req.body;
    const requestId = req.requestId;

    let decoded;
    try {
      decoded = jwt.verify(refresh_token, config.jwt.refreshSecret);
    } catch (jwtError) {
      if (jwtError.name === 'TokenExpiredError') {
        return sendError(res, 'Refresh token expired', 401, 'REFRESH_TOKEN_EXPIRED');
      }
      return sendError(res, 'Invalid refresh token', 401, 'INVALID_REFRESH_TOKEN');
    }

    if (decoded.type !== 'refresh') {
      return sendError(res, 'Invalid token type', 401, 'INVALID_TOKEN_TYPE');
    }

    const student = await Student.findById(decoded.id).select('+refresh_token');

    if (!student) {
      return sendError(res, 'Student not found', 401, 'STUDENT_NOT_FOUND');
    }

    if (!student.is_active) {
      return sendError(res, 'Account has been deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    const isTokenValid = await student.compareRefreshToken(refresh_token);

    if (!isTokenValid) {
      return sendError(res, 'Invalid refresh token', 401, 'INVALID_REFRESH_TOKEN');
    }

    // Generate new access token only (refresh token rotation optional)
    const accessToken = jwt.sign(
      { id: student._id, student_id: student.student_id, role: student.role },
      config.jwt.secret,
      { expiresIn: config.jwt.expiresIn }
    );

    await logAuth.refreshToken(student._id, req, requestId);

    logger.info(`Token refreshed for student: ${student.email}`);

    return sendSuccess(res, {
      access_token: accessToken,
      expires_in: config.jwt.expiresIn,
    });
  } catch (error) {
    next(error);
  }
};

// Logout
const logout = async (req, res, next) => {
  try {
    const studentId = req.student._id;
    const requestId = req.requestId;
    const { all_devices } = req.body;

    if (all_devices) {
      // Revoke all sessions
      await UserSession.revokeAllExcept(studentId, req.headers.authorization?.split(' ')[1]);
      await Student.findByIdAndUpdate(studentId, { refresh_token: null });
      await logAuth.sessionRevoked(studentId, req, requestId, { all_devices: true });
    } else {
      // Just clear current session
      await Student.findByIdAndUpdate(studentId, { refresh_token: null });
    }

    await logAuth.logout(studentId, req, requestId);
    await activity.logout(studentId, req);

    logger.info(`Student logged out: ${req.student.email}`);

    return sendSuccess(res, null, 'Logged out successfully');
  } catch (error) {
    next(error);
  }
};

// Forgot Password
const forgotPassword = async (req, res, next) => {
  try {
    const { email } = req.body;

    const student = await Student.findOne({ email: email.toLowerCase(), is_deleted: false });

    if (!student) {
      // Still return success to prevent email enumeration
      return sendSuccess(res, null, 'If an account exists, a password reset email has been sent');
    }

    // Invalidate any existing tokens
    await PasswordResetToken.updateMany(
      { student: student._id, used: false },
      { $set: { used: true } }
    );

    // Create new reset token
    const resetToken = await PasswordResetToken.create({
      student: student._id,
      expires_at: new Date(Date.now() + 60 * 60 * 1000), // 1 hour
    });

    await logAuth.passwordResetRequest(student._id, req, req.requestId);

    // TODO: Send email with reset link
    logger.info(`Password reset token created for ${student.email}: ${resetToken.token}`);

    return sendSuccess(
      res,
      null,
      'If an account exists, a password reset email has been sent'
    );
  } catch (error) {
    next(error);
  }
};

// Reset Password
const resetPassword = async (req, res, next) => {
  try {
    const { token, new_password } = req.body;

    const resetToken = await PasswordResetToken.findOne({
      token,
      used: false,
      expires_at: { $gt: Date.now() },
    }).populate('student');

    if (!resetToken) {
      return sendError(res, 'Invalid or expired reset token', 400, 'INVALID_TOKEN');
    }

    const student = resetToken.student;

    // Update password
    student.password = new_password;
    student.refresh_token = null;
    student.login_attempts = 0;
    student.lock_until = undefined;
    await student.save();

    // Mark token as used
    await resetToken.markAsUsed(req.ip, req.headers['user-agent']);

    // Revoke all sessions
    await UserSession.updateMany(
      { student: student._id, is_active: true },
      { $set: { is_active: false, is_revoked: true, revoked_at: new Date(), revoked_reason: 'password_reset' } }
    );

    await logAuth.passwordResetComplete(student._id, req, req.requestId, 'SUCCESS');
    await activity.passwordChange(student._id, req);

    logger.info(`Password reset completed for: ${student.email}`);

    return sendSuccess(res, null, 'Password reset successful. Please log in with your new password.');
  } catch (error) {
    next(error);
  }
};

// Verify Email
const verifyEmail = async (req, res, next) => {
  try {
    const { token } = req.body;

    const verificationToken = await EmailVerificationToken.findOne({
      token,
      used: false,
      expires_at: { $gt: Date.now() },
    }).populate('student');

    if (!verificationToken) {
      return sendError(res, 'Invalid or expired verification token', 400, 'INVALID_TOKEN');
    }

    const student = verificationToken.student;

    if (student.is_verified) {
      return sendSuccess(res, null, 'Email is already verified');
    }

    // Mark as verified
    student.is_verified = true;
    student.email_verified_at = new Date();
    await student.save();

    // Mark token as used
    verificationToken.used = true;
    verificationToken.used_at = new Date();
    await verificationToken.save();

    await logAuth.emailVerified(student._id, req, req.requestId);

    logger.info(`Email verified for: ${student.email}`);

    return sendSuccess(res, null, 'Email verified successfully');
  } catch (error) {
    next(error);
  }
};

// Resend Verification Email
const resendVerification = async (req, res, next) => {
  try {
    const { email } = req.body;

    const student = await Student.findOne({ email: email.toLowerCase(), is_deleted: false });

    if (!student) {
      return sendSuccess(res, null, 'If an account exists, a verification email has been sent');
    }

    if (student.is_verified) {
      return sendSuccess(res, null, 'Email is already verified');
    }

    // Invalidate old tokens
    await EmailVerificationToken.updateMany(
      { student: student._id, used: false },
      { $set: { used: true } }
    );

    // Create new token
    const verificationToken = await EmailVerificationToken.create({
      student: student._id,
      email: student.email,
      expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000),
    });

    await logAuth.emailVerificationSent(student._id, req, req.requestId);

    // TODO: Send email
    logger.info(`Verification email resent to ${student.email}: ${verificationToken.token}`);

    return sendSuccess(res, null, 'If an account exists, a verification email has been sent');
  } catch (error) {
    next(error);
  }
};

// Get Sessions
const getSessions = async (req, res, next) => {
  try {
    const studentId = req.student._id;

    const sessions = await UserSession.find({
      student: studentId,
      expires_at: { $gt: Date.now() },
    })
      .sort({ last_active_at: -1 })
      .select('-refresh_token -session_token');

    return sendSuccess(res, { sessions });
  } catch (error) {
    next(error);
  }
};

// Revoke Session
const revokeSession = async (req, res, next) => {
  try {
    const { sessionId } = req.params;
    const studentId = req.student._id;

    const session = await UserSession.findOne({
      _id: sessionId,
      student: studentId,
    });

    if (!session) {
      return sendError(res, 'Session not found', 404, 'SESSION_NOT_FOUND');
    }

    await session.revoke('manual_revoke');
    await logAuth.sessionRevoked(studentId, req, req.requestId, { session_id: sessionId });

    return sendSuccess(res, null, 'Session revoked successfully');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  register,
  login,
  refresh,
  logout,
  forgotPassword,
  resetPassword,
  verifyEmail,
  resendVerification,
  getSessions,
  revokeSession,
};
