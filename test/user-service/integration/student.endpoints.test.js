const { setupEnv } = require('../helpers/envSetup');
setupEnv();

jest.mock('dotenv', () => ({ config: jest.fn(() => ({})) }), { virtual: true });
jest.mock('winston', () => require('../helpers/winstonMock'), { virtual: true });
jest.mock('mongoose', () => require('../helpers/miniMongoose'), { virtual: true });
jest.mock('bcryptjs', () => require('../helpers/bcryptMock'), { virtual: true });
jest.mock('express', () => require('../helpers/miniExpress'), { virtual: true });
jest.mock('helmet', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('cors', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('morgan', () => () => (req, res, next) => next(), { virtual: true });
jest.mock('express-rate-limit', () => jest.fn(() => (req, res, next) => next()), { virtual: true });
jest.mock('jsonwebtoken', () => require('../helpers/jwtMock'), { virtual: true });
jest.mock('joi', () => require('../helpers/joiMock'), { virtual: true });
jest.mock('useragent', () => ({
  parse: jest.fn(() => ({ family: 'MockBrowser', os: { family: 'MockOS' }, toVersion: () => '1.0' })),
}), { virtual: true });
jest.mock('axios', () => ({ post: jest.fn(), get: jest.fn(), delete: jest.fn() }), { virtual: true });
jest.mock('../../../services/user service/src/models/Student', () => require('../helpers/fakeStudent'));

const request = require('supertest');
const app = require('../../../services/user service/src/app');
const { Student } = require('../../../services/user service/src/models');
const FakeStudent = require('../helpers/fakeStudent');

const makeDoc = (overrides = {}) =>
  new FakeStudent({
    name: 'Jane Doe',
    email: 'jane@example.com',
    password: 'hashed-password',
    _plainPassword: 'secret123',
    ...overrides,
  });

describe('student endpoints (integration)', () => {
  beforeEach(() => {
    Student.findById = jest.fn(() => ({ select: jest.fn().mockResolvedValue(makeDoc()) }));
    Student.findByIdAndUpdate = jest.fn().mockResolvedValue({});
  });

  test('GET /api/students/me returns the authenticated student without secrets', async () => {
    const res = await request(app).get('/api/students/me').set('Authorization', 'Bearer test-token');

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.message).toBe('Success');
    expect(res.body.data.email).toBe('jane@example.com');
    expect(res.body.data.password).toBeUndefined();
    expect(res.body.data.student_id).toBe('STD-00001');
  });

  test('PUT /api/students/me updates name and profile fields', async () => {
    const updated = makeDoc({
      name: 'New Name',
      email: 'jane@example.com',
      profile: { avatar_url: '', bio: 'Hello world', java_level: 'advanced', institution: '', country: '' },
    });
    Student.findByIdAndUpdate = jest.fn().mockResolvedValue(updated);

    const res = await request(app)
      .put('/api/students/me')
      .set('Authorization', 'Bearer test-token')
      .send({ name: 'New Name', profile: { bio: 'Hello world', java_level: 'advanced' } });

    expect(res.status).toBe(200);
    expect(res.body.message).toBe('Profile updated successfully');
    expect(res.body.data.name).toBe('New Name');
    expect(Student.findByIdAndUpdate).toHaveBeenCalledWith(
      'stu_0001',
      expect.objectContaining({
        $set: expect.objectContaining({
          name: 'New Name',
          'profile.bio': 'Hello world',
          'profile.java_level': 'advanced',
        }),
      }),
      { new: true, runValidators: true }
    );
  });

  test('PUT /api/students/me/password changes the password when the current one matches', async () => {
    const student = makeDoc();
    student.comparePassword = jest.fn().mockResolvedValue(true);
    student.save = jest.fn(async function () {
      return this;
    });
    Student.findById = jest.fn(() => ({ select: jest.fn().mockResolvedValue(student) }));

    const res = await request(app)
      .put('/api/students/me/password')
      .set('Authorization', 'Bearer test-token')
      .send({ current_password: 'secret123', new_password: 'brandnew456' });

    expect(res.status).toBe(200);
    expect(res.body.success).toBe(true);
    expect(res.body.data).toBeNull();
    expect(res.body.message).toBe('Password updated. Please log in again.');
    expect(student.password).toBe('brandnew456');
    expect(student.refresh_token).toBeNull();
  });

  test('GET /api/students/me/preferences returns the stored preferences', async () => {
    const student = makeDoc({
      preferences: { notifications: { email: true, push: false, marketing: true }, theme: 'dark', language: 'fr', timezone: 'UTC' },
    });
    Student.findById = jest.fn(() => ({ select: jest.fn().mockResolvedValue(student) }));

    const res = await request(app).get('/api/students/me/preferences').set('Authorization', 'Bearer test-token');

    expect(res.status).toBe(200);
    expect(res.body.data.theme).toBe('dark');
    expect(res.body.data.language).toBe('fr');
    expect(res.body.data.notifications.push).toBe(false);
  });

  test('PUT /api/students/me/preferences persists new preference values', async () => {
    const updated = makeDoc({
      preferences: { notifications: { email: false, push: true, marketing: false }, theme: 'dark', language: 'en', timezone: 'UTC' },
    });
    Student.findByIdAndUpdate = jest.fn().mockResolvedValue(updated);

    const res = await request(app)
      .put('/api/students/me/preferences')
      .set('Authorization', 'Bearer test-token')
      .send({ theme: 'dark', notifications: { email: false } });

    expect(res.status).toBe(200);
    expect(res.body.message).toBe('Preferences updated successfully');
    expect(res.body.data.theme).toBe('dark');
    expect(res.body.data.notifications.email).toBe(false);
    expect(Student.findByIdAndUpdate).toHaveBeenCalledWith(
      'stu_0001',
      expect.objectContaining({
        $set: expect.objectContaining({
          'preferences.theme': 'dark',
          'preferences.notifications.email': false,
        }),
      }),
      { new: true, runValidators: true }
    );
  });

  test('protected routes reject requests without an access token', async () => {
    const res = await request(app).get('/api/students/me');

    expect(res.status).toBe(401);
    expect(res.body.success).toBe(false);
    expect(res.body.code).toBe('NO_TOKEN');
    expect(Student.findById).not.toHaveBeenCalled();
  });
});