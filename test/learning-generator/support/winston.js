'use strict';

const noop = () => {};
const noopFormat = (..._a) => noop;

module.exports = {
  format: {
    combine: noopFormat,
    timestamp: noopFormat,
    errors: noopFormat,
    printf: noopFormat,
    colorize: noopFormat,
    json: noopFormat,
  },
  createLogger: () => ({
    debug: noop, info: noop, warn: noop, error: noop, http: noop, log: noop,
  }),
  transports: {
    Console: class {},
    File: class {},
  },
  addColors: noop,
};
