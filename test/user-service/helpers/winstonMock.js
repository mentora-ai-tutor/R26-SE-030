const noopLogger = () => ({
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
  log: jest.fn(),
});

const winstonMock = {
  format: {
    combine: (...args) => args[args.length - 1],
    timestamp: () => ({}),
    errors: () => ({}),
    printf: (fn) => fn,
    colorize: () => ({}),
  },
  transports: {
    Console: function ConsoleTransport() {},
    File: function FileTransport() {},
  },
  createLogger: jest.fn(() => noopLogger()),
};

module.exports = winstonMock;