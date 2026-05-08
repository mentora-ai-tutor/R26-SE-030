const logger = require('../utils/logger');

const validate = (schema, property = 'body') => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req[property], {
      abortEarly: false,
      stripUnknown: true,
      convert: true,
    });

    if (error) {
      const details = error.details.map((detail) => ({
        field: detail.path.join('.'),
        message: detail.message,
        type: detail.type,
      }));

      logger.warn('Validation failed', {
        path: req.path,
        method: req.method,
        errors: details,
      });

      return res.status(400).json({
        success: false,
        error: 'Validation failed',
        code: 'VALIDATION_ERROR',
        details,
      });
    }

    req[property] = value;
    next();
  };
};

const validateQuery = (schema) => validate(schema, 'query');
const validateBody = (schema) => validate(schema, 'body');
const validateParams = (schema) => validate(schema, 'params');

module.exports = {
  validate,
  validateQuery,
  validateBody,
  validateParams,
};