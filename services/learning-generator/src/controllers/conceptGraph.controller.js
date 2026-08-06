const MasteryProfile = require('../models/MasteryProfile');
const conceptGraphService = require('../services/conceptGraph.service');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');

const getCoverage = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own concept coverage',
        code: 'FORBIDDEN',
      });
    }

    const unitCategory = req.query.category || 'OOP';

    const coverage = await conceptGraphService.computeCoverage(studentId, unitCategory);

    const latestProfile = await MasteryProfile.findOne({
      student_id: studentId,
    }).sort({ submitted_at: -1 });

    const augmented = latestProfile?.augmented_profile;
    const implicitGapsCount = augmented?.implicit_gaps?.length || 0;
    const unverifiedCount = augmented?.unverified_prerequisites?.length || 0;

    logger.debug('Concept-graph coverage fetched', {
      student_id: studentId,
      category: unitCategory,
      coverage,
      implicitGapsCount,
      unverifiedCount,
    });

    return apiResponse.success(res, {
      ...coverage,
      implicitGapsCount,
      unverifiedCount,
    });
  } catch (error) {
    next(error);
  }
};

const seedConceptGraph = async (req, res, next) => {
  try {
    const summary = await conceptGraphService.seedGraph(req.body);

    logger.info('Concept graph seeded via API', summary);

    return apiResponse.success(res, summary, 'Concept graph seeded successfully');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getCoverage,
  seedConceptGraph,
};
