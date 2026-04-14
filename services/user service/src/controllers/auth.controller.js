const jwt = require('jsonwebtoken');
const config = require('../config/env');
const Student = require('../models/Student');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');

const generateTokens = async (student) => {
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

  const hashedRefreshToken = await Student.hashRefreshToken(refreshToken);
  student.refresh_token = hashedRefreshToken;
  await student.save({ validateBeforeSave: false });

  return { accessToken, refreshToken };
};

const register = async (req, res, next) => {
  try {
    const { name, email, password, student_id, profile } = req.body;

    const existingStudent = await Student.findOne({ email: email.toLowerCase() });
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
      const existingStudentId = await Student.findOne({ student_id });
      if (existingStudentId) {
        return sendError(res, 'Student ID already exists', 409, 'STUDENT_ID_EXISTS');
      }
      studentData.student_id = student_id;
    }

    const student = new Student(studentData);
    await student.save();

    const { accessToken, refreshToken } = await generateTokens(student);

    logger.info(`New student registered: ${student.email}`);

    return sendSuccess(
      res,
      {
        student: student.toSafeObject(),
        access_token: accessToken,
        refresh_token: refreshToken,
        expires_in: config.jwt.expiresIn,
      },
      'Registration successful',
      201
    );
  } catch (error) {
    next(error);
  }
};

const login = async (req, res, next) => {
  try {
    const { email, password } = req.body;

    const student = await Student.findOne({ email: email.toLowerCase() }).select('+password');

    if (!student) {
      return sendError(res, 'Invalid email or password', 401, 'INVALID_CREDENTIALS');
    }

    if (!student.is_active) {
      return sendError(res, 'Account has been deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    const isPasswordValid = await student.comparePassword(password);

    if (!isPasswordValid) {
      return sendError(res, 'Invalid email or password', 401, 'INVALID_CREDENTIALS');
    }

    student.last_login = new Date();
    student.last_active = new Date();

    const { accessToken, refreshToken } = await generateTokens(student);

    logger.info(`Student logged in: ${student.email}`);

    return sendSuccess(res, {
      student: student.toSafeObject(),
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_in: config.jwt.expiresIn,
    });
  } catch (error) {
    next(error);
  }
};

const refresh = async (req, res, next) => {
  try {
    const { refresh_token } = req.body;

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

    const accessToken = jwt.sign(
      { id: student._id, student_id: student.student_id, role: student.role },
      config.jwt.secret,
      { expiresIn: config.jwt.expiresIn }
    );

    logger.info(`Token refreshed for student: ${student.email}`);

    return sendSuccess(res, {
      access_token: accessToken,
      expires_in: config.jwt.expiresIn,
    });
  } catch (error) {
    next(error);
  }
};

const logout = async (req, res, next) => {
  try {
    const studentId = req.student._id;

    await Student.findByIdAndUpdate(studentId, { refresh_token: null });

    logger.info(`Student logged out: ${req.student.email}`);

    return sendSuccess(res, null, 'Logged out successfully');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  register,
  login,
  refresh,
  logout,
};
