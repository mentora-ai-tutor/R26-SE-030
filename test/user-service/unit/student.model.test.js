const { setupEnv } = require('../helpers/envSetup');
setupEnv();

jest.mock('dotenv', () => ({ config: jest.fn(() => ({})) }), { virtual: true });
jest.mock('bcryptjs', () => require('../helpers/bcryptMock'), { virtual: true });
jest.mock('mongoose', () => require('../helpers/miniMongoose'), { virtual: true });

const Student = require('../../../services/user service/src/models/Student');

const buildStudent = (overrides = {}) =>
  new Student({
    name: 'Test User',
    email: 'test@example.com',
    password: 'secret123',
    ...overrides,
  });

describe('Student model (unit)', () => {
  test('save hashes the plaintext password and comparePassword verifies/rejects candidates', async () => {
    const student = buildStudent({ password: 'hunter2secret' });
    expect(student.password).toBe('hunter2secret');

    await student.save();

    expect(student.password).not.toBe('hunter2secret');
    expect(student.password).toMatch(/^\$2a\$/);
    expect(await student.comparePassword('hunter2secret')).toBe(true);
    expect(await student.comparePassword('wrong-password')).toBe(false);
  });

  test('toSafeObject strips password, refresh_token, and __v', async () => {
    const student = buildStudent();
    student.password = 'not-in-output';
    student.refresh_token = 'refresh-token-value';
    student.__v = 0;

    const safe = student.toSafeObject();

    expect(safe.email).toBe('test@example.com');
    expect(safe.name).toBe('Test User');
    expect(safe.password).toBeUndefined();
    expect(safe.refresh_token).toBeUndefined();
    expect(safe.__v).toBeUndefined();
  });

  test('softDelete marks the account deleted/inactive and records who deleted it', async () => {
    const student = buildStudent();
    await student.softDelete('admin_123');

    expect(student.is_deleted).toBe(true);
    expect(student.is_active).toBe(false);
    expect(student.deleted_by).toBe('admin_123');
    expect(student.deleted_at).toBeInstanceOf(Date);
  });

  test('isLocked virtual reflects lock_until and incrementLoginAttempts locks at 5 attempts', async () => {
    const student = buildStudent();
    student.login_attempts = 4;

    await student.incrementLoginAttempts();

    expect(student._lastUpdate.$inc).toEqual({ login_attempts: 1 });
    expect(student._lastUpdate.$set.lock_until).toBeGreaterThan(Date.now());

    const locked = buildStudent();
    locked.lock_until = Date.now() + 60 * 1000;
    expect(locked.isLocked).toBe(true);

    const active = buildStudent();
    expect(active.isLocked).toBe(false);
  });
});