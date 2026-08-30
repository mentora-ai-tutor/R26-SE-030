const crypto = require('crypto');

function buildSalt(rounds) {
  const r = typeof rounds === 'number' ? rounds : 10;
  return `$2a$${r}$${crypto.randomBytes(16).toString('hex')}`;
}

function digest(salt, data) {
  return crypto.createHash('sha256').update(`${String(salt)}|${String(data)}`).digest('hex');
}

async function genSalt(rounds) {
  return buildSalt(rounds);
}

async function hash(data, saltOrRounds) {
  const salt =
    typeof saltOrRounds === 'number' || typeof saltOrRounds !== 'string'
      ? buildSalt(typeof saltOrRounds === 'number' ? saltOrRounds : 10)
      : saltOrRounds;
  return `${salt}$${digest(salt, data)}`;
}

async function compare(plain, encrypted) {
  if (typeof encrypted !== 'string' || !encrypted.includes('$')) {
    return false;
  }
  const idx = encrypted.lastIndexOf('$');
  const salt = encrypted.slice(0, idx);
  const expected = Buffer.from(encrypted.slice(idx + 1));
  const actual = Buffer.from(digest(salt, plain));
  return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
}

module.exports = { genSalt, hash, compare };