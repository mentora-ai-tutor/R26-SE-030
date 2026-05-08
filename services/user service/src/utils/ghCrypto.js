const crypto = require('crypto');
const config = require('../config/env');

const ALGO = 'aes-256-gcm';
const IV_LEN = 12;
const TAG_LEN = 16;

const encrypt = (plaintext, studentId) => {
  if (typeof plaintext !== 'string' || plaintext.length === 0) {
    throw new Error('encrypt: plaintext must be a non-empty string');
  }
  if (!studentId) {
    throw new Error('encrypt: studentId required for AAD binding');
  }

  const iv = crypto.randomBytes(IV_LEN);
  const cipher = crypto.createCipheriv(ALGO, config.github.tokenKek, iv);
  cipher.setAAD(Buffer.from(String(studentId)));

  const ciphertext = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();

  return { ciphertext, iv, tag };
};

const decrypt = ({ ciphertext, iv, tag }, studentId) => {
  if (!ciphertext || !iv || !tag) {
    throw new Error('decrypt: ciphertext, iv, and tag are required');
  }
  if (tag.length !== TAG_LEN) {
    throw new Error(`decrypt: tag must be ${TAG_LEN} bytes`);
  }

  const decipher = crypto.createDecipheriv(ALGO, config.github.tokenKek, iv);
  decipher.setAAD(Buffer.from(String(studentId)));
  decipher.setAuthTag(tag);

  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return plaintext.toString('utf8');
};

module.exports = { encrypt, decrypt };
