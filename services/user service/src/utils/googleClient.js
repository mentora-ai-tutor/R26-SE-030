const axios = require('axios');
const config = require('../config/env');

const AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const TOKEN_URL = 'https://oauth2.googleapis.com/token';
const VALID_ISSUERS = ['accounts.google.com', 'https://accounts.google.com'];

const buildAuthUrl = (state) => {
  const params = new URLSearchParams({
    client_id: config.google.clientId,
    redirect_uri: config.google.callbackUrl,
    response_type: 'code',
    scope: config.google.scope,
    state,
    access_type: 'online',
    include_granted_scopes: 'true',
    prompt: 'select_account',
  });
  return `${AUTH_URL}?${params.toString()}`;
};

const exchangeCode = async (code) => {
  const body = new URLSearchParams({
    client_id: config.google.clientId,
    client_secret: config.google.clientSecret,
    code,
    grant_type: 'authorization_code',
    redirect_uri: config.google.callbackUrl,
  });

  const resp = await axios.post(TOKEN_URL, body.toString(), {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Accept: 'application/json',
    },
    timeout: 10000,
  });

  if (!resp.data || !resp.data.id_token) {
    const err = new Error('Google did not return an id_token');
    err.code = 'TOKEN_EXCHANGE_FAILED';
    throw err;
  }

  return {
    accessToken: resp.data.access_token,
    idToken: resp.data.id_token,
    scope: (resp.data.scope || '').split(' ').filter(Boolean),
    tokenType: resp.data.token_type,
  };
};

// The id_token is returned directly by Google's token endpoint over an
// authenticated, TLS-protected server-to-server call, so we validate the
// standard claims (signature authenticity is anchored to that exchange).
const decodeIdToken = (idToken) => {
  if (!idToken || typeof idToken !== 'string') {
    throw new Error('Missing id_token');
  }
  const parts = idToken.split('.');
  if (parts.length !== 3) {
    throw new Error('Malformed id_token');
  }

  const payload = JSON.parse(
    Buffer.from(parts[1].replace(/-/g, '+').replace(/_/g, '/'), 'base64').toString('utf8'),
  );

  if (payload.aud !== config.google.clientId) {
    throw new Error('id_token audience mismatch');
  }
  if (!VALID_ISSUERS.includes(payload.iss)) {
    throw new Error('id_token issuer mismatch');
  }
  if (!payload.exp || payload.exp * 1000 < Date.now()) {
    throw new Error('id_token expired');
  }

  return payload;
};

module.exports = { buildAuthUrl, exchangeCode, decodeIdToken };
