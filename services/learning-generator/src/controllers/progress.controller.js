const StudentProgress = require('../models/StudentProgress');
const LearningMaterial = require('../models/LearningMaterial');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');

async function findMaterial(materialId) {
  let material = null;
  if (materialId.match(/^[0-9a-fA-F]{24}$/)) {
    material = await LearningMaterial.findById(materialId);
  }
  if (!material) {
    material = await LearningMaterial.findOne({ 'structured_material.material_id': materialId });
  }
  return material;
}

const getProgressByMaterial = async (req, res, next) => {
  try {
    const { materialId } = req.params;
    const tokenStudentId = req.student.id;

    const material = await findMaterial(materialId);

    if (!material) {
      return res.status(404).json({
        success: false,
        error: 'Material not found',
        code: 'NOT_FOUND',
      });
    }

    if (material.structured_material.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own progress',
        code: 'FORBIDDEN',
      });
    }

    const progress = await StudentProgress.findOne({
      student_id: tokenStudentId,
      material_id: String(material._id),
    });

    return apiResponse.success(res, progress || null);
  } catch (error) {
    next(error);
  }
};

const updateProgress = async (req, res, next) => {
  try {
    const { materialId } = req.params;
    const tokenStudentId = req.student.id;
    const { total_steps, completed_step, active_step, quiz_score, completed_all } = req.body;

    const material = await findMaterial(materialId);

    if (!material) {
      return res.status(404).json({
        success: false,
        error: 'Material not found',
        code: 'NOT_FOUND',
      });
    }

    if (material.structured_material.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only update your own progress',
        code: 'FORBIDDEN',
      });
    }

    const progressDocId = String(material._id);

    let progress = await StudentProgress.findOne({
      student_id: tokenStudentId,
      material_id: progressDocId,
    });

    if (!progress) {
      progress = new StudentProgress({
        student_id: tokenStudentId,
        material_id: progressDocId,
        topic_id: material.structured_material.topic_id,
      });
    }

    if (total_steps) progress.total_steps = total_steps;
    if (completed_step !== undefined && !progress.completed_steps.includes(completed_step)) {
      progress.completed_steps.push(completed_step);
    }
    if (active_step !== undefined) progress.last_active_step = active_step;
    if (quiz_score !== null && quiz_score !== undefined) progress.quiz_score = quiz_score;

    if (completed_all || (progress.total_steps > 0 && progress.completed_steps.length >= progress.total_steps)) {
      progress.completed_at = new Date();
    }

    await progress.save();

    logger.info('Student progress updated', {
      student_id: tokenStudentId,
      material_id: progressDocId,
      completed_steps: progress.completed_steps.length,
      total_steps: progress.total_steps,
    });

    return apiResponse.success(res, progress);
  } catch (error) {
    next(error);
  }
};

const getProgressByStudent = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own progress',
        code: 'FORBIDDEN',
      });
    }

    const progressList = await StudentProgress.find({ student_id: studentId })
      .sort({ updatedAt: -1 });

    const materialIds = progressList.map(p => p.material_id);
    const materials = await LearningMaterial.find({ _id: { $in: materialIds } });

    const materialMap = {};
    materials.forEach(m => {
      materialMap[String(m._id)] = m.structured_material;
    });

    const enriched = progressList.map(p => ({
      ...p.toJSON(),
      topic: materialMap[p.material_id]?.topic || 'Unknown',
      topic_id: materialMap[p.material_id]?.topic_id || p.topic_id,
    }));

    return apiResponse.success(res, enriched);
  } catch (error) {
    next(error);
  }
};

const getProgressStats = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own stats',
        code: 'FORBIDDEN',
      });
    }

    const progressList = await StudentProgress.find({ student_id: studentId });

    const totalMaterials = progressList.length;
    const completedMaterials = progressList.filter(p => p.completed_at).length;
    const inProgressMaterials = progressList.filter(p => p.completed_steps.length > 0 && !p.completed_at).length;
    const notStartedMaterials = progressList.filter(p => p.completed_steps.length === 0).length;

    const totalSteps = progressList.reduce((sum, p) => sum + p.total_steps, 0);
    const completedSteps = progressList.reduce((sum, p) => sum + p.completed_steps.length, 0);

    const avgQuizScore = (() => {
      const scores = progressList.filter(p => p.quiz_score !== null).map(p => p.quiz_score);
      if (scores.length === 0) return null;
      return Math.round(scores.reduce((sum, s) => sum + s, 0) / scores.length);
    })();

    const progressPercentage = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

    return apiResponse.success(res, {
      total_materials: totalMaterials,
      completed_materials: completedMaterials,
      in_progress_materials: inProgressMaterials,
      not_started_materials: notStartedMaterials,
      total_steps: totalSteps,
      completed_steps: completedSteps,
      progress_percentage: progressPercentage,
      avg_quiz_score: avgQuizScore,
    });
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getProgressByMaterial,
  updateProgress,
  getProgressByStudent,
  getProgressStats,
};
