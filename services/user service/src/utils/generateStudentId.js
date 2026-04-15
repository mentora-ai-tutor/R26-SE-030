const mongoose = require('mongoose');

const generateStudentId = async () => {
  try {
    // Use mongoose.model() to avoid circular dependency
    const Student = mongoose.model('Student');

    // Find the student with the highest student_id starting with STD-
    const lastStudent = await Student.findOne(
      { student_id: { $regex: '^STD-' } },
      { student_id: 1 }
    )
      .sort({ student_id: -1 })
      .lean();

    let nextNumber = 1;

    if (lastStudent && lastStudent.student_id) {
      // Extract the number from the last ID (e.g., STD-00042 -> 42)
      const match = lastStudent.student_id.match(/STD-(\d+)/);
      if (match) {
        nextNumber = parseInt(match[1], 10) + 1;
      }
    }

    // Format with leading zeros (STD-00001, STD-00002, etc.)
    const formattedNumber = nextNumber.toString().padStart(5, '0');
    return `STD-${formattedNumber}`;
  } catch (error) {
    // Fallback: use timestamp-based ID if there's an error
    const timestamp = Date.now();
    const randomDigits = Math.floor(1000 + Math.random() * 9000);
    return `STD-${timestamp}${randomDigits}`;
  }
};

module.exports = { generateStudentId };
