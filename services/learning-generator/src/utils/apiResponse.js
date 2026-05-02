const success = (res, data, message = 'Success', statusCode = 200) => {
  return res.status(statusCode).json({
    success: true,
    message,
    data,
  });
};

const created = (res, data, message = 'Created successfully') => {
  return success(res, data, message, 201);
};

const accepted = (res, data, message = 'Request accepted') => {
  return success(res, data, message, 202);
};

const error = (res, errorMessage, code, statusCode = 500, fix = null) => {
  const response = {
    success: false,
    error: errorMessage,
    code,
  };
  if (fix) {
    response.fix = fix;
  }
  return res.status(statusCode).json(response);
};

const paginated = (res, data, meta) => {
  return res.status(200).json({
    success: true,
    data: {
      items: data,
      meta,
    },
  });
};

module.exports = {
  success,
  created,
  accepted,
  error,
  paginated,
};