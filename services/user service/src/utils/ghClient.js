const axios = require('axios');
const config = require('../config/env');

const TOKEN_URL = 'https://github.com/login/oauth/access_token';
const USER_URL = 'https://api.github.com/user';
const GRANT_URL = (clientId) => `https://api.github.com/applications/${clientId}/grant`;

const exchangeCode = async (code) => {
  const resp = await axios.post(
    TOKEN_URL,
    {
      client_id: config.github.clientId,
      client_secret: config.github.clientSecret,
      code,
      redirect_uri: config.github.callbackUrl,
    },
    { headers: { Accept: 'application/json' }, timeout: 10000 },
  );

  if (resp.data && resp.data.error) {
    const err = new Error(resp.data.error_description || resp.data.error);
    err.code = 'TOKEN_EXCHANGE_FAILED';
    throw err;
  }
  if (!resp.data || !resp.data.access_token) {
    const err = new Error('GitHub did not return an access_token');
    err.code = 'TOKEN_EXCHANGE_FAILED';
    throw err;
  }

  return {
    accessToken: resp.data.access_token,
    scope: (resp.data.scope || '').split(',').filter(Boolean),
    tokenType: resp.data.token_type,
  };
};

const getViewer = async (accessToken) => {
  const resp = await axios.get(USER_URL, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    timeout: 10000,
  });
  return { id: resp.data.id, login: resp.data.login };
};

const revokeGrant = async (accessToken) => {
  try {
    await axios.delete(GRANT_URL(config.github.clientId), {
      auth: {
        username: config.github.clientId,
        password: config.github.clientSecret,
      },
      data: { access_token: accessToken },
      headers: { Accept: 'application/vnd.github+json' },
      timeout: 10000,
    });
    return true;
  } catch (err) {
    if (err.response && err.response.status === 404) return true;
    throw err;
  }
};

module.exports = { exchangeCode, getViewer, revokeGrant };
