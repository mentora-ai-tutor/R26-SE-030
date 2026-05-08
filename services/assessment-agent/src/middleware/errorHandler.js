const errorHandler = (err, req, res, next) => {
  console.error(`[${new Date().toISOString()}] Error:`, err);

  const statusCode = err.statusCode || 500;
  const message = err.message || 'Internal server error';

  const response = {
    success: false,
    message,
  };

  if (process.env.NODE_ENV === 'development') {
    response.error = err.stack || message;
  }

  res.status(statusCode).json(response);
};

module.exports = errorHandler;
