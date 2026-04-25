const LearningMaterial = require('../models/LearningMaterial');
const materialService = require('../services/material.service');
const apiResponse = require('../utils/apiResponse');
const logger = require('../utils/logger');

const getMaterialsByStudent = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own materials',
        code: 'FORBIDDEN',
      });
    }

    const limit = parseInt(req.query.limit, 10) || 10;
    const page = parseInt(req.query.page, 10) || 1;
    const skip = (page - 1) * limit;
    const sortField = req.query.sort || 'generated_at';
    const sortOrder = req.query.order === 'asc' ? 1 : -1;

    const filter = materialService.buildMaterialQuery(studentId, {
      topic: req.query.topic,
      gap_type: req.query.gap_type,
      status: req.query.status,
    });

    const [materials, total] = await Promise.all([
      LearningMaterial.find(filter)
        .sort({ [sortField]: sortOrder })
        .skip(skip)
        .limit(limit),
      LearningMaterial.countDocuments(filter),
    ]);

    return apiResponse.paginated(res, materials, {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    });
  } catch (error) {
    next(error);
  }
};

const getMaterialById = async (req, res, next) => {
  try {
    const { materialId } = req.params;
    const tokenStudentId = req.student.id;

    const material = await LearningMaterial.findOne({
      material_id: materialId,
    });

    if (!material) {
      return res.status(404).json({
        success: false,
        error: 'Material not found',
        code: 'NOT_FOUND',
      });
    }

    if (material.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own materials',
        code: 'FORBIDDEN',
      });
    }

    return apiResponse.success(res, material);
  } catch (error) {
    next(error);
  }
};

const getTopics = async (req, res, next) => {
  try {
    const { studentId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own materials',
        code: 'FORBIDDEN',
      });
    }

    const topics = await materialService.getDistinctTopics(studentId);

    return apiResponse.success(res, topics);
  } catch (error) {
    next(error);
  }
};

const getMaterialStats = async (req, res, next) => {
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

    const stats = await materialService.getMaterialStats(studentId);

    return apiResponse.success(res, stats);
  } catch (error) {
    next(error);
  }
};

const getMaterialsByTopic = async (req, res, next) => {
  try {
    const { studentId, topicId } = req.params;
    const tokenStudentId = req.student.id;

    if (studentId !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only access your own materials',
        code: 'FORBIDDEN',
      });
    }

    const materials = await LearningMaterial.find({
      student_id: studentId,
      topic_id: topicId,
      status: { $ne: 'deleted' },
    }).sort({ generated_at: -1 });

    return apiResponse.success(res, materials);
  } catch (error) {
    next(error);
  }
};

const deleteMaterial = async (req, res, next) => {
  try {
    const { materialId } = req.params;
    const tokenStudentId = req.student.id;

    const material = await LearningMaterial.findOne({
      material_id: materialId,
    });

    if (!material) {
      return res.status(404).json({
        success: false,
        error: 'Material not found',
        code: 'NOT_FOUND',
      });
    }

    if (material.student_id !== tokenStudentId) {
      return res.status(403).json({
        success: false,
        error: 'Forbidden: You can only delete your own materials',
        code: 'FORBIDDEN',
      });
    }

    material.status = 'deleted';
    await material.save();

    logger.info('Material soft deleted', {
      material_id: materialId,
      student_id: tokenStudentId,
    });

    return apiResponse.success(res, null, 'Material deleted successfully');
  } catch (error) {
    next(error);
  }
};

module.exports = {
  getMaterialsByStudent,
  getMaterialById,
  getTopics,
  getMaterialStats,
  getMaterialsByTopic,
  deleteMaterial,
};