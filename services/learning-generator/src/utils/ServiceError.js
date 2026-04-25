class ServiceError extends Error {
  constructor(code, statusCode, message, fix = null) {
    super(message);
    this.code = code;
    this.statusCode = statusCode;
    this.fix = fix;
    this.name = 'ServiceError';
  }
}

module.exports = ServiceError;