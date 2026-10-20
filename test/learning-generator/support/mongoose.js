'use strict';

const STATIC_NOOPS = [
  'find', 'findById', 'findOne', 'countDocuments', 'deleteOne',
  'deleteMany', 'aggregate', 'updateOne', 'updateMany', 'create', 'insertMany',
];

function Schema(definition, options) {
  this.definition = definition;
  this.options = options;
  this._indexes = [];
  this._methods = {};
}

Schema.Types = { Mixed: 'Mixed', ObjectId: 'ObjectId' };

Object.defineProperty(Schema.prototype, 'methods', {
  get() { return this._methods; },
  set(v) { this._methods = Object.assign(this._methods, v); },
});

Schema.prototype.index = function index() { return this; };

function model(name) {
  function MongooseModel(doc) {
    Object.assign(this, doc);
  }
  MongooseModel.modelName = name;
  MongooseModel.schema = null;
  for (const m of STATIC_NOOPS) {
    MongooseModel[m] = () => { throw new Error(`${name}.${m} is not mocked`); };
  }
  return MongooseModel;
}

module.exports = {
  Schema,
  model,
  Types: { Mixed: 'Mixed', ObjectId: 'ObjectId' },
  connection: { readyState: 0, on: () => {}, close: async () => {} },
  set: () => {},
};
