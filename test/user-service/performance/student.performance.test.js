const { setupEnv } = require('../helpers/envSetup');
setupEnv();

jest.mock('dotenv', () => ({ config: jest.fn(() => ({})) }), { virtual: true });
jest.mock('bcryptjs', () => require('../helpers/bcryptMock'), { virtual: true });
jest.mock('mongoose', () => require('../helpers/miniMongoose'), { virtual: true });

const mongoose = require('mongoose');
const Student = require('../../../services/user service/src/models/Student');
const { generateStudentId } = require('../../../services/user service/src/utils/generateStudentId');

describe('student-service performance', () => {
  test('generateStudentId produces 1000 ids in under 2 seconds', async () => {
    mongoose.model('Student').findOne = () => ({
      sort: jest.fn(() => ({ lean: jest.fn(async () => ({ student_id: 'STD-00042' })) })),
    });

    const start = performance.now();
    const ids = [];
    for (let i = 0; i < 1000; i += 1) {
      ids.push(await generateStudentId());
    }
    const elapsedMs = performance.now() - start;

    console.log(`generateStudentId x1000 took ${elapsedMs.toFixed(2)}ms`);

    expect(ids).toHaveLength(1000);
    expect(ids.every((id) => /^STD-\d{5}$/.test(id))).toBe(true);
    console.log(`  -> measured ${elapsedMs.toFixed(2)}ms (threshold 2000ms)`);
    expect(elapsedMs).toBeLessThan(2000);
  });

  test('Student hash+compare round-trips for 100 passwords in under 1 second', async () => {
    const start = performance.now();

    for (let i = 0; i < 100; i += 1) {
      const student = new Student({
        name: `Perf User ${i}`,
        email: `perf${i}@example.com`,
        password: `password-${i}`,
      });
      await student.save();
      const ok = await student.comparePassword(`password-${i}`);
      expect(ok).toBe(true);
    }

    const elapsedMs = performance.now() - start;

    console.log(`Student hash+compare x100 took ${elapsedMs.toFixed(2)}ms`);
    console.log(`  -> measured ${elapsedMs.toFixed(2)}ms (threshold 1000ms)`);
    expect(elapsedMs).toBeLessThan(1000);
  });
});