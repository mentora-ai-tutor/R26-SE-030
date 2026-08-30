const config = require('../config/env');
const { Student, GithubCredential } = require('../models');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const ghCrypto = require('../utils/ghCrypto');
const ghState = require('../utils/ghOAuthState');
const ghClient = require('../utils/ghClient');

const AUTHORIZE_URL = 'https://github.com/login/oauth/authorize';

const githubConfigReady = () =>
  Boolean(config.github.clientId && config.github.clientSecret && config.github.callbackUrl);

const noStore = (res) => {
  res.set('Cache-Control', 'no-store, no-cache, must-revalidate, private');
  res.set('Pragma', 'no-cache');
  res.set('Expires', '0');
  return res;
};

const escapeForJsString = (s) =>
  String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/</g, '\\u003c');

const renderCallbackHtml = ({ payload }) => {
  const targetOrigin = escapeForJsString(config.frontendOrigin);
  const json = JSON.stringify(payload);
  const safeJson = json.replace(/</g, '\\u003c');
  return `<!doctype html><html><head><meta charset="utf-8"><title>GitHub linked</title>
<style>body{font:14px system-ui;color:#cbd5e1;background:#0f172a;margin:0;padding:32px;text-align:center}</style>
</head><body>
<p>You can close this window.</p>
<script>
(function(){
  try {
    if (window.opener) {
      window.opener.postMessage(${safeJson}, '${targetOrigin}');
    }
  } catch (e) { /* no-op */ }
  setTimeout(function(){ window.close(); }, 100);
})();
</script>
</body></html>`;
};

const start = async (req, res, _next) => {
  try {
    noStore(res);

    if (!githubConfigReady()) {
      return sendError(res, 'GitHub OAuth is not configured', 503, 'GITHUB_OAUTH_NOT_CONFIGURED');
    }

    const studentId = req.student._id.toString();
    const state = ghState.sign(studentId);
    const params = new URLSearchParams({
      client_id: config.github.clientId,
      redirect_uri: config.github.callbackUrl,
      scope: config.github.scope,
      state,
      allow_signup: 'false',
    });
    const url = `${AUTHORIZE_URL}?${params.toString()}`;
    return sendSuccess(res, { url, state }, 'GitHub authorization URL generated');
  } catch (error) {
    logger.error('github oauth start failed:', error.message);
    return sendError(res, 'Failed to start GitHub authorization', 500, 'OAUTH_START_FAILED');
  }
};

const callback = async (req, res, _next) => {
  const { code, state, error: ghError, error_description: ghErrorDesc } = req.query;
  const respondHtml = (payload, statusCode = 200) =>
    noStore(res).status(statusCode).type('html').send(renderCallbackHtml({ payload }));

  if (ghError) {
    logger.warn('github oauth callback returned error:', ghError, ghErrorDesc);
    return respondHtml({
      type: 'gh-link-failed',
      code: 'USER_DENIED',
      message: ghErrorDesc || 'GitHub authorization was denied',
    }, 400);
  }
  if (!code || !state) {
    return respondHtml({
      type: 'gh-link-failed',
      code: 'INVALID_STATE',
      message: 'Missing code or state parameter',
    }, 400);
  }

  let studentId;
  try {
    ({ studentId } = ghState.verify(state));
  } catch (e) {
    return respondHtml({
      type: 'gh-link-failed',
      code: e.message === 'STATE_EXPIRED' ? 'STATE_EXPIRED' : 'INVALID_STATE',
      message: e.message === 'STATE_EXPIRED'
        ? 'Authorization request expired — please try again'
        : 'Invalid authorization state',
    }, 400);
  }

  let exchanged;
  try {
    exchanged = await ghClient.exchangeCode(code);
  } catch (e) {
    logger.error('github token exchange failed:', e.message);
    return respondHtml({
      type: 'gh-link-failed',
      code: 'TOKEN_EXCHANGE_FAILED',
      message: 'Could not exchange code with GitHub',
    }, 502);
  }

  let viewer;
  try {
    viewer = await ghClient.getViewer(exchanged.accessToken);
  } catch (e) {
    logger.error('github user fetch failed:', e.message);
    return respondHtml({
      type: 'gh-link-failed',
      code: 'GITHUB_USER_FETCH_FAILED',
      message: 'Could not load GitHub profile',
    }, 502);
  }

  try {
    const { ciphertext, iv, tag } = ghCrypto.encrypt(exchanged.accessToken, studentId);
    const cred = await GithubCredential.findOneAndUpdate(
      { student_id: studentId },
      {
        student_id: studentId,
        gh_user_id: viewer.id,
        gh_login: viewer.login,
        scopes: exchanged.scope,
        ciphertext, iv, tag,
        linked_at: new Date(),
      },
      { upsert: true, new: true, setDefaultsOnInsert: true },
    );

    await Student.findByIdAndUpdate(studentId, {
      github: {
        linked: true,
        gh_login: viewer.login,
        linked_at: cred.linked_at,
        credential_ref: cred._id,
      },
    });

    logger.info(`github linked for student ${studentId} as @${viewer.login}`);
    return respondHtml({ type: 'gh-linked', login: viewer.login });
  } catch (e) {
    logger.error('github credential persist failed:', e.message);
    return respondHtml({
      type: 'gh-link-failed',
      code: 'PERSIST_FAILED',
      message: 'Could not save GitHub credential',
    }, 500);
  }
};

const status = async (req, res, _next) => {
  noStore(res);

  const studentId = req.student._id.toString();
  const gh = req.student.github || {};
  let cred = gh.credential_ref
    ? await GithubCredential.findById(gh.credential_ref).select('scopes gh_login linked_at')
    : null;

  if (!cred) {
    cred = await GithubCredential.findOne({ student_id: studentId }).select('scopes gh_login linked_at');
  }

  if (!cred) {
    return sendSuccess(res, { linked: false }, 'GitHub link status retrieved');
  }

  if (!gh.linked || String(gh.credential_ref || '') !== String(cred._id)) {
    Student.findByIdAndUpdate(studentId, {
      github: {
        linked: true,
        gh_login: cred.gh_login,
        linked_at: cred.linked_at,
        credential_ref: cred._id,
      },
    }).catch((err) => logger.warn('Failed to repair github link status:', err.message));
  }

  return sendSuccess(res, {
    linked: true,
    gh_login: gh.gh_login || cred.gh_login,
    linked_at: gh.linked_at || cred.linked_at,
    scopes: cred.scopes,
  }, 'GitHub link status retrieved');
};

const unlink = async (req, res, _next) => {
  try {
    noStore(res);

    const studentId = req.student._id.toString();
    const cred = await GithubCredential.findOne({ student_id: studentId });
    if (!cred) {
      await Student.findByIdAndUpdate(studentId, {
        github: { linked: false },
      });
      return sendError(res, 'GitHub is not linked to this account', 404, 'NOT_LINKED');
    }

    try {
      const accessToken = ghCrypto.decrypt(
        { ciphertext: cred.ciphertext, iv: cred.iv, tag: cred.tag },
        studentId.toString(),
      );
      await ghClient.revokeGrant(accessToken);
    } catch (e) {
      logger.warn('github revokeGrant best-effort failed:', e.message);
    }

    await GithubCredential.deleteOne({ _id: cred._id });
    await Student.findByIdAndUpdate(studentId, {
      github: { linked: false },
    });

    logger.info(`github unlinked for student ${studentId}`);
    return sendSuccess(res, { linked: false }, 'GitHub unlinked successfully');
  } catch (error) {
    logger.error('github unlink failed:', error.message);
    return sendError(res, 'Could not unlink GitHub', 500, 'UNLINK_FAILED');
  }
};

module.exports = { start, callback, status, unlink };
