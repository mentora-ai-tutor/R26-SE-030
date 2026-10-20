const crypto = require('crypto');
const config = require('../config/env');

const TTL_MS = 10 * 60 * 1000;

const usedNonces = new Map();

const sweep = () => {
  const now = Date.now();
  for (const [nonce, expiresAt] of usedNonces) {
    if (expiresAt < now) usedNonces.delete(nonce);
  }
};

const b64url = (buf) =>
  Buffer.from(buf).toString('base64')
    .replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');

const b64urlDecode = (s) => {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64');
};

const sign = (studentId) => {
  const nonce = crypto.randomBytes(16).toString('hex');
  const payload = `${studentId}|${nonce}|${Date.now()}`;
  const mac = crypto.createHmac('sha256', config.jwt.refreshSecret)
    .update(payload).digest();
  return `${b64url(payload)}.${b64url(mac)}`;
};

const verify = (state) => {
  if (!state || typeof state !== 'string' || !state.includes('.')) {
    throw new Error('INVALID_STATE');
  }
  const [payloadB64, macB64] = state.split('.');
  const payload = b64urlDecode(payloadB64).toString('utf8');
  const expected = crypto.createHmac('sha256', config.jwt.refreshSecret)
    .update(payload).digest();
  const provided = b64urlDecode(macB64);

  if (expected.length !== provided.length ||
      !crypto.timingSafeEqual(expected, provided)) {
    throw new Error('INVALID_STATE');
  }

  const [studentId, nonce, tsStr] = payload.split('|');
  const ts = parseInt(tsStr, 10);
  if (!studentId || !nonce || !Number.isFinite(ts)) {
    throw new Error('INVALID_STATE');
  }
  if (Date.now() - ts > TTL_MS) {
    throw new Error('STATE_EXPIRED');
  }

  sweep();
  if (usedNonces.has(nonce)) {
    throw new Error('INVALID_STATE');
  }
  usedNonces.set(nonce, ts + TTL_MS);

  return { studentId };
};

module.exports = { sign, verify };
