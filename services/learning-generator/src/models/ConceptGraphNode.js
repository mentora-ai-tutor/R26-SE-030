const mongoose = require('mongoose');

const conceptGraphNodeSchema = new mongoose.Schema({
  concept_id: {
    type: String,
    unique: true,
    required: true,
  },
  name: {
    type: String,
    required: true,
  },
  category: {
    type: String,
    index: true,
    required: true,
  },
  subcategory: {
    type: String,
    default: '',
  },
  bloom_level: {
    type: String,
    enum: ['remember', 'understand', 'apply', 'analyze', 'evaluate', 'create'],
    required: true,
  },
  description: {
    type: String,
    required: true,
  },
  description_embedding: {
    type: [Number],
    default: undefined,
  },
  aliases: {
    type: [String],
    default: [],
  },
  prerequisites: {
    type: [String],
    index: true,
    default: [],
  },
  related_topics: {
    type: [String],
    default: [],
  },
  source: {
    type: String,
    default: 'OCJP_objectives',
  },
  version: {
    type: Number,
    default: 1,
  },
}, {
  timestamps: true,
  collection: 'concept_graph_nodes',
});

conceptGraphNodeSchema.methods.toJSON = function() {
  const obj = this.toObject();
  delete obj.__v;
  return obj;
};

const ConceptGraphNode = mongoose.model('ConceptGraphNode', conceptGraphNodeSchema);

module.exports = ConceptGraphNode;
