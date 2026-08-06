const axios = require('axios');
const config = require('../config/env');
const logger = require('../utils/logger');
const ConceptGraphNode = require('../models/ConceptGraphNode');
const LearningMaterial = require('../models/LearningMaterial');

const EMBEDDING_MODEL = 'nomic-embed-text';
const EMBEDDING_THRESHOLD = 0.75;
const EMBEDDING_AMBIGUITY_DELTA = 0.05;
const LLM_MODEL = 'qwen2.5-coder:7b';

const ollamaBaseUrl = config.ollama.baseUrl;

const embed = async (text) => {
  const response = await axios.post(
    `${ollamaBaseUrl}/api/embed`,
    { model: EMBEDDING_MODEL, input: [text] },
    { timeout: 60000 }
  );
  return response.data?.embeddings?.[0] || null;
};

const embedMany = async (texts) => {
  if (!Array.isArray(texts) || texts.length === 0) {
    return [];
  }
  const response = await axios.post(
    `${ollamaBaseUrl}/api/embed`,
    { model: EMBEDDING_MODEL, input: texts },
    { timeout: 120000 }
  );
  return response.data?.embeddings || [];
};

const generate = async ({ model, prompt, options = {} }) => {
  const response = await axios.post(
    `${ollamaBaseUrl}/api/generate`,
    {
      model,
      prompt,
      stream: false,
      options: {
        temperature: 0,
        num_predict: 64,
        ...options,
      },
    },
    { timeout: 45000 }
  );
  return response.data?.response || '';
};

const embedder = { embed };
const ollamaClient = { generate };

const loadGraph = async () => {
  const nodes = await ConceptGraphNode.find({}).lean();

  if (nodes.length === 0) {
    logger.warn('Concept graph is empty. Run: npm run seed:concept-graph');
  }

  const graph = new Map();
  for (const node of nodes) {
    graph.set(node.concept_id, node);
  }
  return graph;
};

const validateGraphAcyclic = (nodes) => {
  if (!Array.isArray(nodes) || nodes.length === 0) {
    throw new Error('Seed data must be a non-empty array of concept graph nodes');
  }

  const ids = nodes.map((node) => node.concept_id);
  const idSet = new Set(ids);
  if (idSet.size !== ids.length) {
    throw new Error('Duplicate concept_id detected in seed data');
  }

  for (const node of nodes) {
    if (!node.concept_id) {
      throw new Error('Every node must have a concept_id');
    }
    for (const prereq of node.prerequisites || []) {
      if (!idSet.has(prereq)) {
        throw new Error(`Node ${node.concept_id} references unknown prerequisite: ${prereq}`);
      }
      if (prereq === node.concept_id) {
        throw new Error(`Node ${node.concept_id} has a self-loop prerequisite`);
      }
    }
  }

  const adjacency = new Map(ids.map((id) => [id, []]));
  for (const node of nodes) {
    adjacency.set(node.concept_id, node.prerequisites || []);
  }

  const indegree = new Map(ids.map((id) => [id, 0]));
  for (const node of nodes) {
    for (const prereq of node.prerequisites || []) {
      indegree.set(prereq, (indegree.get(prereq) || 0) + 1);
    }
  }

  const queue = nodes
    .filter((node) => indegree.get(node.concept_id) === 0)
    .map((node) => node.concept_id);

  let count = 0;
  while (queue.length) {
    const id = queue.shift();
    count++;
    for (const prereq of adjacency.get(id) || []) {
      indegree.set(prereq, indegree.get(prereq) - 1);
      if (indegree.get(prereq) === 0) {
        queue.push(prereq);
      }
    }
  }

  if (count !== nodes.length) {
    throw new Error('Cyclic prerequisite graph detected: topological sort failed');
  }

  return true;
};

const seedGraph = async (nodes) => {
  validateGraphAcyclic(nodes);

  const descriptions = nodes.map((node) => node.description);
  const embeddings = await embedMany(descriptions);
  if (embeddings.length !== nodes.length) {
    throw new Error(`Expected ${nodes.length} embeddings but received ${embeddings.length}`);
  }

  const dimensions = new Set(embeddings.map((e) => (Array.isArray(e) ? e.length : 0)));
  if (dimensions.size > 1 || !dimensions.has(768)) {
    logger.warn('Unexpected embedding dimensions for nomic-embed-text', {
      dimensions: [...dimensions],
    });
  }

  const operations = nodes.map((node, index) => ({
    updateOne: {
      filter: { concept_id: node.concept_id },
      update: {
        $set: {
          ...node,
          description_embedding: embeddings[index],
          updatedAt: new Date(),
        },
        $setOnInsert: {
          createdAt: new Date(),
        },
      },
      upsert: true,
    },
  }));

  const result = await ConceptGraphNode.bulkWrite(operations, { ordered: false });

  return {
    nodeCount: nodes.length,
    upserted: result.upsertedCount,
    modified: result.modifiedCount,
    matched: result.matchedCount,
  };
};

const stripFences = (s) => {
  return s
    .replace(/^```json\s*/gi, '')
    .replace(/^```\s*/gi, '')
    .replace(/\s*```$/gi, '')
    .replace(/^`+/g, '')
    .replace(/`+$/g, '')
    .trim();
};

const findOutermostObject = (s) => {
  const start = s.indexOf('{');
  if (start === -1) return null;

  let depth = 0;
  for (let i = start; i < s.length; i++) {
    if (s[i] === '{') {
      depth++;
    } else if (s[i] === '}') {
      depth--;
      if (depth === 0) {
        return s.substring(start, i + 1);
      }
    }
  }

  const lastClose = s.lastIndexOf('}');
  if (lastClose > start) {
    return s.substring(start, lastClose + 1);
  }
  return null;
};

const extractField = (s, fieldName, type) => {
  if (type === 'string') {
    const re = new RegExp(`"${fieldName}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)"`, 's');
    const m = s.match(re);
    return m ? m[1].replace(/\\n/g, '\n').replace(/\\"/g, '"') : null;
  }

  const bracket = type === 'array' ? '[' : '{';
  const closeBracket = type === 'array' ? ']' : '}';
  const re = new RegExp(`"${fieldName}"\\s*:\\s*(\\${bracket})`);
  const m = re.exec(s);
  if (!m) return null;

  const start = m.index + m[0].length - 1;
  let depth = 0;
  for (let i = start; i < s.length; i++) {
    if (s[i] === bracket) {
      depth++;
    } else if (s[i] === closeBracket) {
      depth--;
      if (depth === 0) {
        try {
          return JSON.parse(s.substring(start, i + 1));
        } catch (e) {
          return null;
        }
      }
    }
  }
  return null;
};

const parseConceptIdResponse = (raw, graph) => {
  if (typeof raw !== 'string' || raw.trim() === '') {
    return null;
  }

  const cleaned = stripFences(raw);

  const direct = cleaned.toLowerCase().trim();
  if (graph.has(direct)) {
    return direct;
  }

  const candidate = findOutermostObject(cleaned);
  if (candidate) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed.concept_id === 'string' && graph.has(parsed.concept_id)) {
        return parsed.concept_id;
      }
    } catch (e) {
      // fall through to field extraction below
    }
  }

  const field = extractField(cleaned, 'concept_id', 'string');
  if (field && graph.has(field)) {
    return field;
  }

  const idMatch = cleaned.match(/java\.[a-z0-9_.]+/i);
  if (idMatch) {
    const candidate = idMatch[0].replace(/[._]+$/g, '');
    if (graph.has(candidate)) {
      return candidate;
    }
  }

  return null;
};

const buildGapText = (gap) => {
  const parts = [gap.topic];
  if (Array.isArray(gap.evidence)) {
    parts.push(...gap.evidence);
  }
  if (gap.evidence_summary) {
    parts.push(gap.evidence_summary);
  }
  if (Array.isArray(gap.misconceptions)) {
    parts.push(...gap.misconceptions);
  }
  if (gap.observed_error_patterns && typeof gap.observed_error_patterns === 'object') {
    parts.push(JSON.stringify(gap.observed_error_patterns));
  }
  return parts.filter(Boolean).join(' ');
};

const resolveExact = (gapTopic, graph) => {
  const normalized = String(gapTopic || '').toLowerCase().trim();
  if (!normalized) {
    return null;
  }

  for (const node of graph.values()) {
    if (String(node.name).toLowerCase() === normalized) {
      return { concept_id: node.concept_id, method: 'exact', confidence: 1.0 };
    }
    const aliasMatch = (node.aliases || []).some(
      (alias) => String(alias).toLowerCase() === normalized
    );
    if (aliasMatch) {
      return { concept_id: node.concept_id, method: 'alias', confidence: 1.0 };
    }
  }
  return null;
};

const cosineSimilarity = (a, b) => {
  if (
    !Array.isArray(a) ||
    !Array.isArray(b) ||
    a.length === 0 ||
    a.length !== b.length
  ) {
    return 0;
  }

  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }

  if (normA === 0 || normB === 0) {
    return 0;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
};

const resolveEmbedding = async (gap, graph, embedderFn) => {
  const embeddedNodes = [...graph.values()].filter(
    (node) => Array.isArray(node.description_embedding) && node.description_embedding.length > 0
  );
  if (embeddedNodes.length === 0) {
    return null;
  }

  const gapText = buildGapText(gap);
  if (!gapText) {
    return null;
  }

  let gapVec;
  try {
    gapVec = await embedderFn.embed(gapText);
  } catch (error) {
    logger.warn('Gap embedding failed, escalating to LLM tier', {
      error: error.message,
      topic: gap.topic,
    });
    return null;
  }

  if (!Array.isArray(gapVec) || gapVec.length === 0) {
    return null;
  }

  const scored = embeddedNodes
    .map((node) => ({ node, sim: cosineSimilarity(gapVec, node.description_embedding) }))
    .sort((a, b) => b.sim - a.sim);

  const best = scored[0];
  if (!best || best.sim < EMBEDDING_THRESHOLD) {
    return null;
  }

  const second = scored[1];
  if (second && best.sim - second.sim <= EMBEDDING_AMBIGUITY_DELTA) {
    logger.debug('Embedding match ambiguous, escalating to LLM tier', {
      topic: gap.topic,
      best: best.node.concept_id,
      best_sim: best.sim,
      second: second.node.concept_id,
      second_sim: second.sim,
    });
    return null;
  }

  return {
    concept_id: best.node.concept_id,
    method: 'embedding',
    confidence: Number(best.sim.toFixed(4)),
  };
};

const resolveLLM = async (gap, graph, client) => {
  const nodeList = [...graph.values()]
    .map((node) => `${node.concept_id}: ${node.name} - ${node.description}`)
    .join('\n');

  const prompt = `A student's assessed knowledge gap is described as:
"${gap.topic}" — evidence: ${buildGapText(gap)}

Match this gap to exactly ONE concept_id from the list below, or return "NO_MATCH"
if none genuinely applies. Respond with only the concept_id or NO_MATCH.

${nodeList}`;

  let response;
  try {
    response = await client.generate({ model: LLM_MODEL, prompt });
  } catch (error) {
    logger.warn('LLM gap resolution failed, marking as unresolved', {
      error: error.message,
      topic: gap.topic,
    });
    return { concept_id: null, method: 'llm_no_match', confidence: 0 };
  }

  const matched = parseConceptIdResponse(response, graph);
  if (!matched) {
    return { concept_id: null, method: 'llm_no_match', confidence: 0 };
  }

  return { concept_id: matched, method: 'llm', confidence: null };
};

const resolveGap = async (gap, graph, embedderFn, client) => {
  if (!graph || graph.size === 0) {
    return { concept_id: null, method: 'unresolved', confidence: 0 };
  }

  const resolution =
    resolveExact(gap.topic, graph) ||
    (await resolveEmbedding(gap, graph, embedderFn)) ||
    (await resolveLLM(gap, graph, client));

  if (!resolution) {
    return { concept_id: null, method: 'unresolved', confidence: 0 };
  }
  return resolution;
};

const classify = (conceptId, profile) => {
  const gapIds = (profile.knowledge_gaps || [])
    .map((g) => g.resolved_concept_id)
    .filter(Boolean);
  const strengthIds = (profile.strengths || [])
    .map((s) => s.resolved_concept_id)
    .filter(Boolean);

  if (strengthIds.includes(conceptId)) {
    return 'MASTERED';
  }
  if (gapIds.includes(conceptId)) {
    return 'GAP';
  }
  return 'UNKNOWN';
};

const closePrerequisites = (resolvedGapIds, profile, graph) => {
  const result = {
    explicitGaps: [...resolvedGapIds],
    implicitGaps: [],
    unverified: [],
  };

  const visited = new Set(resolvedGapIds);
  const queue = [...resolvedGapIds];

  while (queue.length) {
    const currentId = queue.shift();
    const node = graph.get(currentId);
    if (!node) continue;

    for (const prereqId of node.prerequisites || []) {
      if (visited.has(prereqId)) continue;
      visited.add(prereqId);

      const state = classify(prereqId, profile);
      if (state === 'MASTERED') continue;
      if (state === 'GAP') {
        queue.push(prereqId);
        continue;
      }
      if (state === 'UNKNOWN') {
        result.unverified.push({ concept_id: prereqId, blocks: currentId });
        continue;
      }
    }
  }

  return result;
};

const buildConceptContext = (node, graph) => {
  if (!node) return null;
  const nameFor = (id) => {
    const resolved = graph.get(id);
    return resolved ? resolved.name : id;
  };
  return {
    concept_id: node.concept_id,
    id: node.concept_id,
    name: node.name,
    description: node.description,
    bloom_level: node.bloom_level,
    category: node.category,
    prerequisite_names: (node.prerequisites || []).map(nameFor).filter(Boolean),
    related_topic_names: (node.related_topics || []).map(nameFor).filter(Boolean),
  };
};

const augmentGaps = async (knowledgeGaps, strengths, graph, embedderFn, client) => {
  const resolvedGaps = [];
  for (const gap of knowledgeGaps) {
    const resolution = await resolveGap(gap, graph, embedderFn, client);
    const node = resolution.concept_id ? graph.get(resolution.concept_id) : null;
    resolvedGaps.push({
      ...gap,
      resolved_concept_id: resolution.concept_id,
      resolution_method: resolution.method,
      resolution_confidence: resolution.confidence,
      concept_context: buildConceptContext(node, graph),
    });
    logger.info('Knowledge gap resolved', {
      topic: gap.topic,
      concept_id: resolution.concept_id,
      method: resolution.method,
      confidence: resolution.confidence,
    });
  }

  const closure = closePrerequisites(
    resolvedGaps.map((g) => g.resolved_concept_id).filter(Boolean),
    { knowledge_gaps: resolvedGaps, strengths },
    graph
  );

  const injectedGaps = closure.unverified
    .map(({ concept_id, blocks }) => {
      const node = graph.get(concept_id);
      if (!node) return null;
      return {
        topic: node.name,
        topic_id: node.concept_id,
        gap_type: 'FUNDAMENTAL_GAP',
        difficulty_level: bloomToDifficulty(node.bloom_level),
        resolved_concept_id: node.concept_id,
        resolution_method: 'implicit',
        resolution_confidence: null,
        concept_context: buildConceptContext(node, graph),
        reason: `prerequisite_of:${blocks}`,
      };
    })
    .filter(Boolean);

  return {
    resolvedGaps,
    injectedGaps,
    effectiveGaps: [...resolvedGaps, ...injectedGaps],
    closure,
  };
};

const computeCoverage = async (studentId, unitCategory) => {
  const nodeQuery = unitCategory ? { category: unitCategory } : {};
  const totalNodes = await ConceptGraphNode.countDocuments(nodeQuery);

  if (totalNodes === 0) {
    return { totalNodes: 0, coveredNodes: 0, coveragePct: 0 };
  }

  const conceptIds = await ConceptGraphNode.find(nodeQuery).distinct('concept_id');
  const materials = await LearningMaterial.find({
    'structured_material.student_id': studentId,
    'structured_material.topic_id': { $in: conceptIds },
  }).select('structured_material.topic_id');

  const coveredNodes = new Set(
    materials.map((m) => m.structured_material.topic_id)
  ).size;
  const coveragePct = (coveredNodes / totalNodes) * 100;

  return {
    totalNodes,
    coveredNodes,
    coveragePct: Number(coveragePct.toFixed(2)),
  };
};

const bloomToDifficulty = (bloomLevel) => {
  if (['remember', 'understand'].includes(bloomLevel)) {
    return 'beginner';
  }
  if (['apply', 'analyze'].includes(bloomLevel)) {
    return 'intermediate';
  }
  return 'advanced';
};

module.exports = {
  EMBEDDING_MODEL,
  EMBEDDING_THRESHOLD,
  EMBEDDING_AMBIGUITY_DELTA,
  LLM_MODEL,
  embed,
  embedMany,
  generate,
  embedder,
  ollamaClient,
  loadGraph,
  validateGraphAcyclic,
  seedGraph,
  stripFences,
  findOutermostObject,
  extractField,
  parseConceptIdResponse,
  resolveExact,
  resolveEmbedding,
  resolveLLM,
  resolveGap,
  classify,
  closePrerequisites,
  buildConceptContext,
  augmentGaps,
  computeCoverage,
  cosineSimilarity,
  bloomToDifficulty,
};
