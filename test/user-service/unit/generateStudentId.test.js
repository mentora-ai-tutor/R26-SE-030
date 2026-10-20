jest.mock('mongoose', () => ({ model: jest.fn() }), { virtual: true });

const mongoose = require('mongoose');
const { generateStudentId } = require('../../../services/user service/src/utils/generateStudentId');

const findOneChain = (result) => ({
  sort: jest.fn(() => ({
    lean: jest.fn(async () => result),
  })),
});

describe('generateStudentId (unit)', () => {
  beforeEach(() => {
    mongoose.model.mockReset();
  });

  test('returns STD-00001 when no previous student exists', async () => {
    mongoose.model.mockReturnValue({ findOne: jest.fn(() => findOneChain(null)) });

    const id = await generateStudentId();

    expect(id).toBe('STD-00001');
    expect(mongoose.model).toHaveBeenCalledWith('Student');
  });

  test('increments the numeric suffix from the highest existing student id', async () => {
    mongoose.model.mockReturnValue({
      findOne: jest.fn(() => findOneChain({ student_id: 'STD-00042' })),
    });

    const id = await generateStudentId();

    expect(id).toBe('STD-00043');
  });

  test('fallbacks to a timestamp based id when the model lookup throws', async () => {
    mongoose.model.mockImplementation(() => {
      throw new Error('no model registered');
    });

    const id = await generateStudentId();

    expect(id).toMatch(/^STD-\d{17}$/);
  });
});