module.exports = {
  sign: jest.fn(() => 'signed-test-token'),
  verify: jest.fn(() => ({ id: 'stu_0001', student_id: 'STD-00001', role: 'student', type: 'refresh' })),
};