const Joi = require('joi');
const { sendError } = require('../utils/apiResponse');

const registerSchema = Joi.object({
  name: Joi.string()
    .min(2)
    .max(100)
    .required()
    .trim()
    .messages({
      'string.empty': 'Name is required',
      'string.min': 'Name must be at least 2 characters',
      'string.max': 'Name cannot exceed 100 characters',
      'any.required': 'Name is required',
    }),
  email: Joi.string()
    .email()
    .lowercase()
    .trim()
    .required()
    .messages({
      'string.email': 'Please provide a valid email address',
      'any.required': 'Email is required',
    }),
  password: Joi.string()
    .min(6)
    .required()
    .messages({
      'string.min': 'Password must be at least 6 characters',
      'any.required': 'Password is required',
    }),
  student_id: Joi.string()
    .pattern(/^STD-\d{5}$/)
    .optional()
    .messages({
      'string.pattern.base': 'Student ID must be in format STD-XXXXX (e.g., STD-00001)',
    }),
  profile: Joi.object({
    java_level: Joi.string()
      .valid('beginner', 'intermediate', 'advanced')
      .optional(),
    institution: Joi.string().max(200).optional().allow(''),
    country: Joi.string().max(100).optional().allow(''),
  }).optional(),
});

const loginSchema = Joi.object({
  email: Joi.string()
    .email()
    .lowercase()
    .trim()
    .required()
    .messages({
      'string.email': 'Please provide a valid email address',
      'any.required': 'Email is required',
    }),
  password: Joi.string()
    .required()
    .messages({
      'any.required': 'Password is required',
    }),
});

const refreshTokenSchema = Joi.object({
  refresh_token: Joi.string()
    .required()
    .messages({
      'any.required': 'Refresh token is required',
    }),
});

const updateProfileSchema = Joi.object({
  name: Joi.string()
    .min(2)
    .max(100)
    .trim()
    .optional(),
  profile: Joi.object({
    avatar_url: Joi.string().uri().optional().allow(''),
    bio: Joi.string().max(500).optional().allow(''),
    java_level: Joi.string()
      .valid('beginner', 'intermediate', 'advanced')
      .optional(),
    institution: Joi.string().max(200).optional().allow(''),
    country: Joi.string().max(100).optional().allow(''),
  }).optional(),
});

const updatePasswordSchema = Joi.object({
  current_password: Joi.string()
    .required()
    .messages({
      'any.required': 'Current password is required',
    }),
  new_password: Joi.string()
    .min(6)
    .required()
    .messages({
      'string.min': 'New password must be at least 6 characters',
      'any.required': 'New password is required',
    }),
});

const updateStatsSchema = Joi.object({
  overall_mastery_score: Joi.number()
    .min(0)
    .max(100)
    .optional(),
  total_materials_generated_increment: Joi.number()
    .integer()
    .min(0)
    .optional(),
  total_sessions_increment: Joi.number()
    .integer()
    .min(0)
    .optional(),
  materials_generated_increment: Joi.number()
    .integer()
    .min(0)
    .optional(),
});

const verifyTokenSchema = Joi.object({
  token: Joi.string()
    .required()
    .messages({
      'any.required': 'Token is required',
    }),
});

const validate = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.body, {
      abortEarly: false,
      stripUnknown: true,
    });

    if (error) {
      const errorMessage = error.details
        .map((detail) => detail.message)
        .join(', ');
      return sendError(res, errorMessage, 400, 'VALIDATION_ERROR');
    }

    req.body = value;
    next();
  };
};

module.exports = {
  registerSchema,
  loginSchema,
  refreshTokenSchema,
  updateProfileSchema,
  updatePasswordSchema,
  updateStatsSchema,
  verifyTokenSchema,
  validate,
};
