const config = require('../config/env');
const { Student } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { logAuth } = require('../utils/auditLogger');
const { activity } = require('../utils/activityLogger');
const { parseDeviceInfo } = require('../utils/deviceParser');
const { generateTokens } = require('./auth.controller');
const googleClient = require('../utils/googleClient');
const googleState = require('../utils/googleOAuthState');

const CALLBACK_PATH = '/auth/google/callback';

const googleReady = () => Boolean(config.google.clientId && config.google.clientSecret && config.google.callbackUrl);

const frontendBase = () => (config.frontendOrigins[0] || 'http://localhost:3000').replace(/\/+$/, '');

const noStore = (res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
  res.set('Pragma', 'no-cache');
  res.set('Expires', '0');
  return res;
};

// GET /api/auth/google/start — 302 to Google's consent screen.
const start = (req, res) => {
  noStore(res);
  const base = frontendBase();

  if (!googleReady()) {
    logger.warn('google oauth start called but Google OAuth is not configured');
    return res.redirect(`${base}/login?google_error=not_configured`);
  }

  const state = googleState.signState('login');
  return res.redirect(googleClient.buildAuthUrl(state));
};

// GET /api/auth/google/callback — Google redirects here with ?code&state.
// We never leak tokens through the URL: a one-time ticket is returned instead.
const callback = async (req, res) => {
  noStore(res);
  const base = frontendBase();
  const fail = (reason) => res.redirect(`${base}/login?google_error=${encodeURIComponent(reason)}`);

  const { code, state, error, error_description: errorDesc } = req.query;

  if (error) {
    logger.warn('google oauth callback returned error:', error, errorDesc);
    return fail(errorDesc || error);
  }
  if (!code || !state) {
    return fail('missing_code');
  }

  try {
    googleState.verifyState(state);
  } catch (e) {
    return fail(e.message === 'STATE_EXPIRED' ? 'state_expired' : 'invalid_state');
  }

  let tokens;
  try {
    tokens = await googleClient.exchangeCode(code);
  } catch (e) {
    logger.error('google token exchange failed:', e.message);
    return fail('token_exchange_failed');
  }

  let profile;
  try {
    profile = googleClient.decodeIdToken(tokens.idToken);
  } catch (e) {
    logger.error('google id_token validation failed:', e.message);
    return fail('invalid_id_token');
  }

  const email = String(profile.email || '').toLowerCase().trim();
  if (!email) {
    return fail('email_missing');
  }
  const emailVerified = profile.email_verified === true || profile.email_verified === 'true';
  const name = profile.name || profile.given_name || email.split('@')[0];
  const picture = profile.picture || '';

  try {
    let student = await Student.findOne({ email });

    if (student && student.is_deleted) {
      return fail('account_disabled');
    }

    const googleBlock = {
      linked: true,
      google_id: profile.sub,
      email,
      picture,
      linked_at: new Date(),
    };

    if (!student) {
      student = new Student({
        name,
        email,
        is_verified: emailVerified,
        email_verified_at: emailVerified ? new Date() : undefined,
      });
    }

    student.google = googleBlock;
    if (picture && !student.profile?.avatar_url) {
      student.profile = { ...(student.profile || {}), avatar_url: picture };
    }
    if (emailVerified && !student.is_verified) {
      student.is_verified = true;
      student.email_verified_at = new Date();
    }
    student.last_login = new Date();
    student.last_active = new Date();

    await student.save({ validateBeforeSave: false });

    const ticket = googleState.createTicket(student._id);
    logger.info(`google oauth completed for ${email}`);
    return res.redirect(`${base}${CALLBACK_PATH}?ticket=${ticket}`);
  } catch (e) {
    logger.error('google account upsert failed:', e.message);
    return fail('account_error');
  }
};

// POST /api/auth/google/exchange — swap the one-time ticket for tokens.
const exchange = async (req, res) => {
  try {
    noStore(res);
    const { ticket } = req.body || {};

    let studentId;
    try {
      ({ studentId } = googleState.consumeTicket(ticket));
    } catch (e) {
      return sendError(res, 'Invalid or expired sign-in ticket', 400, e.message || 'INVALID_TICKET');
    }

    const student = await Student.findById(studentId);
    if (!student || student.is_deleted) {
      return sendError(res, 'Student not found', 404, 'STUDENT_NOT_FOUND');
    }
    if (!student.is_active) {
      return sendError(res, 'Account has been deactivated', 403, 'ACCOUNT_DEACTIVATED');
    }

    const deviceInfo = parseDeviceInfo(req.headers['user-agent']);
    const { accessToken, refreshToken } = await generateTokens(student, deviceInfo, req);

    try {
      await logAuth.login(student._id, req, req.requestId);
      await activity.login(student._id, req);
    } catch (logErr) {
      logger.warn('google login audit/activity logging failed:', logErr.message);
    }

    return sendSuccess(res, {
      student: student.toSafeObject(),
      access_token: accessToken,
      refresh_token: refreshToken,
      expires_in: config.jwt.expiresIn,
    });
  } catch (error) {
    logger.error('google token exchange endpoint failed:', error.message);
    return sendError(res, 'Google sign-in failed', 500, 'GOOGLE_EXCHANGE_FAILED');
  }
};

module.exports = { start, callback, exchange };
