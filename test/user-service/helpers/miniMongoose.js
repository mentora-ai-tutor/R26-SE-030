class ObjectId {}

const models = {};

function createSchema() {
  const schema = {
    methods: {},
    statics: {},
    preHooks: {},
    virtuals: {},
    index() {
      return schema;
    },
    pre(name, fn) {
      (schema.preHooks[name] = schema.preHooks[name] || []).push(fn);
      return schema;
    },
    virtual(name, opts) {
      schema.virtuals[name] = opts || {};
      return schema;
    },
    get(fn) {
      const names = Object.keys(schema.virtuals);
      if (names.length > 0) schema.virtuals[names[names.length - 1]].get = fn;
      return schema;
    },
  };
  return schema;
}

function Schema() {
  return createSchema();
}

function buildModel(name, schema) {
  function Model(data = {}) {
    this._isNew = true;
    this._initial = { ...data };
    Object.assign(this, data);
  }

  Model.modelName = name;

  Model.prototype.isModified = function (path) {
    if (this._isNew) return true;
    if (!(path in this)) return true;
    return JSON.stringify(this[path]) !== JSON.stringify(this._initial[path]);
  };

  Model.prototype.save = async function () {
    const hooks = schema.preHooks.save || [];
    for (const hook of hooks) {
      await hook.call(this, () => {});
    }
    this._isNew = false;
    return this;
  };

  Model.prototype.updateOne = async function (update) {
    this._lastUpdate = update;
    return { acknowledged: true, modifiedCount: 1 };
  };

  Model.prototype.toObject = function () {
    const out = {};
    for (const key of Object.keys(this)) {
      if (key.startsWith('_') && key !== '_id') continue;
      out[key] = this[key];
    }
    return out;
  };

  for (const [methodName, fn] of Object.entries(schema.methods || {})) {
    Model.prototype[methodName] = fn;
  }
  for (const [staticName, fn] of Object.entries(schema.statics || {})) {
    Model[staticName] = fn;
  }
  for (const [vname, vopts] of Object.entries(schema.virtuals || {})) {
    if (vopts && typeof vopts.get === 'function') {
      Object.defineProperty(Model.prototype, vname, { get: vopts.get, configurable: true });
    }
  }

  return Model;
}

const mongoose = {
  Schema,
  model(name, schema) {
    if (schema) {
      const M = buildModel(name, schema);
      models[name] = M;
      return M;
    }
    return models[name];
  },
  connection: { readyState: 0, name: 'test', host: 'localhost' },
  Types: { ObjectId, Mixed: class Mixed {} },
};

Schema.Types = mongoose.Types;
mongoose.mongoose = mongoose;

module.exports = mongoose;