const crypto = require('crypto');
const config = require('../config/env');

// Authorization "state" and one-time login ticket TTLs.
const STATE_TTL_MS = 10 * 60 * 1000; // 10 min
const TICKET_TTL_MS = 2 * 60 * 1000; // 2 min

const usedNonces = new Map();
const tickets = new Map();

const sweep = () => {
  const now = Date.now();
  for (const [key, expiresAt] of usedNonces) {
    if (expiresAt < now) usedNonces.delete(key);
  }
  for (const [key, ticket] of tickets) {
    if (ticket.expiresAt < now) tickets.delete(key);
  }
};

const b64url = (buf) =>
  Buffer.from(buf).toString('base64')
    .replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');

const b64urlDecode = (s) => {
  const pad = '='.repeat((4 - (s.length % 4)) % 4);
  return Buffer.from(s.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64');
};

// ── OAuth state (CSRF protection) ─────────────────────────────────────────
const signState = (metadata = '') => {
  const nonce = crypto.randomBytes(16).toString('hex');
  const payload = `${nonce}|${metadata}|${Date.now()}`;
  const mac = crypto.createHmac('sha256', config.jwt.refreshSecret)
    .update(payload).digest();
  return `${b64url(payload)}.${b64url(mac)}`;
};

const verifyState = (state) => {
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

  const [nonce, metadata, tsStr] = payload.split('|');
  const ts = parseInt(tsStr, 10);
  if (!nonce || !Number.isFinite(ts)) {
    throw new Error('INVALID_STATE');
  }
  if (Date.now() - ts > STATE_TTL_MS) {
    throw new Error('STATE_EXPIRED');
  }

  sweep();
  if (usedNonces.has(nonce)) {
    throw new Error('INVALID_STATE');
  }
  usedNonces.set(nonce, ts + STATE_TTL_MS);

  return { metadata };
};

// ── One-time login ticket ─────────────────────────────────────────────────
// The OAuth callback redirects the browser to the frontend with a short-lived
// opaque ticket instead of the tokens, so tokens never appear in the URL. The
// frontend exchanges the ticket (over CORS) for the real tokens.
const createTicket = (studentId) => {
  sweep();
  const ticket = crypto.randomBytes(32).toString('hex');
  tickets.set(ticket, { studentId: String(studentId), expiresAt: Date.now() + TICKET_TTL_MS });
  return ticket;
};

const consumeTicket = (ticket) => {
  sweep();
  if (!ticket || typeof ticket !== 'string') {
    throw new Error('INVALID_TICKET');
  }
  const entry = tickets.get(ticket);
  if (!entry) {
    throw new Error('INVALID_TICKET');
  }
  tickets.delete(ticket); // single use
  if (entry.expiresAt < Date.now()) {
    throw new Error('TICKET_EXPIRED');
  }
  return { studentId: entry.studentId };
};

module.exports = { signState, verifyState, createTicket, consumeTicket };
