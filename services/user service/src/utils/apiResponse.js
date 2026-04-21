const sendSuccess = (res, data, message = 'Success', statusCode = 200) => {
  return res.status(statusCode).json({
    success: true,
    message,
    data,
  });
};

const sendError = (res, message = 'An error occurred', statusCode = 400, code = '') => {
  const response = {
    success: false,
    error: message,
  };
  if (code) {
    response.code = code;
  }
  return res.status(statusCode).json(response);
};

const sendPaginated = (res, data, meta) => {
  return res.status(200).json({
    success: true,
    data,
    meta,
  });
};

module.exports = {
  sendSuccess,
  sendError,
  sendPaginated,
};
