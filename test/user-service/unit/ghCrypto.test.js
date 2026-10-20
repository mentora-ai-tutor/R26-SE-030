const { setupEnv } = require('../helpers/envSetup');
setupEnv();

jest.mock('dotenv', () => ({ config: jest.fn(() => ({})) }), { virtual: true });

const { encrypt, decrypt } = require('../../../services/user service/src/utils/ghCrypto');

describe('ghCrypto (unit)', () => {
  test('encrypt/decrypt round-trips, binds to a student id (AAD), and validates input', () => {
    const token = 'ghp_xYz12345supersecret';
    const packed = encrypt(token, 'stu_42');

    expect(Buffer.isBuffer(packed.ciphertext)).toBe(true);
    expect(Buffer.isBuffer(packed.iv)).toBe(true);
    expect(Buffer.isBuffer(packed.tag)).toBe(true);

    expect(decrypt(packed, 'stu_42')).toBe(token);
    expect(() => decrypt(packed, 'stu_other')).toThrow();

    expect(() => encrypt('', 'stu_1')).toThrow();
    expect(() => encrypt('token', '')).toThrow();
  });
});