function createBuilder() {
  const builder = new Proxy(function joiBuilder() {}, {
    get(target, prop) {
      if (prop === 'then') return undefined;
      if (prop === 'validate') {
        return (value, _opts) => ({ error: null, value });
      }
      return builder;
    },
    apply() {
      return builder;
    },
  });
  return builder;
}

module.exports = createBuilder();