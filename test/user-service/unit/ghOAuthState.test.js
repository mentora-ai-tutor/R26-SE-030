const { setupEnv } = require('../helpers/envSetup');
setupEnv();

jest.mock('dotenv', () => ({ config: jest.fn(() => ({})) }), { virtual: true });

const { sign, verify } = require('../../../services/user service/src/utils/ghOAuthState');

describe('ghOAuthState (unit)', () => {
  test('sign/verify round-trips the student id, and rejects tampering, replay, and expired states', () => {
    const state = sign('stu_99');

    expect(typeof state).toBe('string');
    expect(state.includes('.')).toBe(true);
    expect(verify(state)).toEqual({ studentId: 'stu_99' });

    const tampered = `${state.slice(0, -2)}${state.slice(-2) === 'aa' ? 'bb' : 'aa'}`;
    expect(() => verify(tampered)).toThrow('INVALID_STATE');

    expect(() => verify(state)).toThrow('INVALID_STATE');

    const freshState = sign('stu_1');
    const originalNow = Date.now;
    Date.now = () => originalNow() + 11 * 60 * 1000;

    try {
      expect(() => verify(freshState)).toThrow('STATE_EXPIRED');
    } finally {
      Date.now = originalNow;
    }
  });
});