const MasteryProfile = require('../models/MasteryProfile');
const ConceptGraphNode = require('../models/ConceptGraphNode');
const conceptGraphService = require('../services/conceptGraph.service');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');

const buildNodeNameMap = async (conceptIds) => {
  const ids = [...new Set(conceptIds.filter(Boolean))];
  if (ids.length === 0) return new Map();
  const nodes = await ConceptGraphNode.find({ concept_id: { $in: ids } }).select('concept_id name');
  return new Map(nodes.map((n) => [n.concept_id, n.name]));
};

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
    const implicitGaps = augmented?.implicit_gaps || [];
    const unresolved = augmented?.unverified_prerequisites || [];

    const nameMap = await buildNodeNameMap([
      ...implicitGaps.map((g) => g.concept_id),
      ...unresolved.map((u) => u.concept_id),
    ]);

    const implicitGapDetails = implicitGaps
      .map((g) => ({
        concept_id: g.concept_id,
        name: nameMap.get(g.concept_id) || g.concept_id,
        reason: g.reason,
      }));

    const unresolvedDetails = unresolved
      .map((u) => ({
        concept_id: u.concept_id,
        name: nameMap.get(u.concept_id) || u.concept_id,
        blocks: u.blocks,
      }));

    logger.debug('Concept-graph coverage fetched', {
      student_id: studentId,
      category: unitCategory,
      coverage,
      implicitGapsCount: implicitGaps.length,
      unverifiedCount: unresolved.length,
    });

    return apiResponse.success(res, {
      ...coverage,
      implicitGapsCount: implicitGaps.length,
      unverifiedCount: unresolved.length,
      implicitGaps: implicitGapDetails,
      unresolved: unresolvedDetails,
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
