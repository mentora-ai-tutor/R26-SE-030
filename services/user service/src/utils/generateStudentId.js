const generateStudentId = () => {
  const timestamp = Date.now();
  const randomDigits = Math.floor(1000 + Math.random() * 9000);
  return `STU_${timestamp}_${randomDigits}`;
};

module.exports = { generateStudentId };
