const embeddingService = require('./embeddingService');

const RAG_ENABLED = process.env.RAG_ENABLED !== 'false';
const DEFAULT_CHUNK_SIZE = Number(process.env.RAG_CHUNK_SIZE || 800);
const DEFAULT_CHUNK_OVERLAP = Number(process.env.RAG_CHUNK_OVERLAP || 120);
const DEFAULT_TOP_K = Number(process.env.RAG_TOP_K || 5);
const DEFAULT_MIN_SCORE = Number(process.env.RAG_MIN_SCORE || 0.25);

const isEnabled = () => RAG_ENABLED;

const chunkText = (text, chunkSize = DEFAULT_CHUNK_SIZE, chunkOverlap = DEFAULT_CHUNK_OVERLAP) => {
  const normalized = String(text || '').replace(/\r\n/g, '\n').trim();
  if (!normalized) return [];

  const size = Math.max(Number(chunkSize) || DEFAULT_CHUNK_SIZE, 50);
  const overlap = Math.min(Math.max(Number(chunkOverlap) || DEFAULT_CHUNK_OVERLAP, 0), Math.floor(size / 2));

  const chunks = [];
  let start = 0;

  while (start < normalized.length) {
    let end = Math.min(start + size, normalized.length);

    if (end < normalized.length) {
      const newlineAt = normalized.lastIndexOf('\n', end);
      const spaceAt = normalized.lastIndexOf(' ', end);
      const preferredBreak = Math.max(newlineAt, spaceAt);
      if (preferredBreak > start + Math.floor(size * 0.5)) {
        end = preferredBreak + 1;
      }
    }

    const chunk = normalized.slice(start, end).trim();
    if (chunk) chunks.push(chunk);

    if (end >= normalized.length) break;
    start = end - overlap;
  }

  return chunks;
};

const cosineSimilarity = (a, b) => {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length || a.length === 0) return 0;
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  if (normA === 0 || normB === 0) return 0;
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
};

const ingestDocument = async (db, input) => {
  const { document_id, title, topic, source, content, metadata, chunk_size, chunk_overlap } = input || {};

  if (!content || typeof content !== 'string' || !content.trim()) {
    throw new Error('content is required and must be a non-empty string');
  }

  const docId = document_id || `DOC_${Date.now()}`;
  const chunks = chunkText(content, chunk_size, chunk_overlap);

  if (chunks.length === 0) {
    throw new Error('Document produced no chunks');
  }

  await db.collection('ame_knowledge_chunks').deleteMany({ document_id: docId });

  const embeddings = await embeddingService.embedTexts(chunks);

  if (embeddings.length !== chunks.length) {
    throw new Error('Embedding count does not match chunk count');
  }

  const chunkDocs = chunks.map((text, index) => ({
    chunk_id: `${docId}_CHUNK_${index + 1}`,
    document_id: docId,
    title: title || null,
    topic: topic || null,
    source: source || null,
    chunk_index: index + 1,
    content: text,
    metadata: metadata || {},
    embedding: embeddings[index] || [],
    ingested_at: new Date(),
  }));

  await db.collection('ame_knowledge_chunks').insertMany(chunkDocs);

  const docMeta = {
    document_id: docId,
    title: title || null,
    topic: topic || null,
    source: source || null,
    chunk_count: chunkDocs.length,
    total_chars: content.trim().length,
    metadata: metadata || {},
    updated_at: new Date(),
  };

  await db.collection('ame_knowledge_documents').updateOne(
    { document_id: docId },
    { $set: docMeta, $setOnInsert: { created_at: new Date() } },
    { upsert: true }
  );

  return {
    document_id: docId,
    title: title || null,
    topic: topic || null,
    source: source || null,
    chunk_count: chunkDocs.length,
  };
};

const retrieve = async (db, query, options = {}) => {
  const queryText = String(query || '').trim();
  const topK = Number(options.top_k || DEFAULT_TOP_K);
  const threshold = options.threshold != null ? Number(options.threshold) : DEFAULT_MIN_SCORE;

  if (!queryText) {
    return { query: queryText, top_k: 0, retrieval: 'empty-query', chunks: [] };
  }

  const buildFilter = () => {
    const filter = {};
    if (options.topic) filter.topic = options.topic;
    if (options.document_id) filter.document_id = options.document_id;
    return filter;
  };

  try {
    const [queryEmbedding] = await embeddingService.embedTexts([queryText]);

    const candidates = await db.collection('ame_knowledge_chunks')
      .find(buildFilter(), {
        projection: {
          chunk_id: 1,
          document_id: 1,
          title: 1,
          topic: 1,
          source: 1,
          content: 1,
          metadata: 1,
          embedding: 1,
          _id: 0,
        },
      })
      .toArray();

    const scored = [];
    for (const candidate of candidates) {
      const score = cosineSimilarity(queryEmbedding, candidate.embedding);
      if (score >= threshold) {
        scored.push({ score, candidate });
      }
    }

    scored.sort((a, b) => b.score - a.score);

    const chunks = scored.slice(0, topK).map(({ score, candidate }) => ({
      score: Math.round(score * 10000) / 10000,
      chunk_id: candidate.chunk_id,
      document_id: candidate.document_id,
      title: candidate.title,
      topic: candidate.topic,
      source: candidate.source,
      content: candidate.content,
      metadata: candidate.metadata || null,
    }));

    if (chunks.length === 0) {
      return keywordSearch(db, queryText, options, topK);
    }

    return { query: queryText, top_k: chunks.length, retrieval: 'embedding', chunks };
  } catch (error) {
    console.warn('[RAG] Embedding retrieval failed, falling back to keyword search:', error.message);
    return keywordSearch(db, queryText, options, topK);
  }
};

const escapeRegex = (str) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const keywordSearch = async (db, queryText, options, topK) => {
  const keywords = queryText
    .split(/\s+/)
    .map((w) => w.replace(/[^a-zA-Z0-9_#.-]/g, ''))
    .filter((w) => w.length > 2);

  const filter = options.topic ? { topic: options.topic } : {};
  if (options.document_id) filter.document_id = options.document_id;

  if (keywords.length > 0) {
    filter.content = { $regex: keywords.map(escapeRegex).join('|'), $options: 'i' };
  }

  const results = await db.collection('ame_knowledge_chunks')
    .find(filter, {
      projection: {
        chunk_id: 1,
        document_id: 1,
        title: 1,
        topic: 1,
        source: 1,
        content: 1,
        metadata: 1,
        _id: 0,
      },
    })
    .limit(topK)
    .toArray();

  const chunks = results.map((c) => ({
    score: 1,
    chunk_id: c.chunk_id,
    document_id: c.document_id,
    title: c.title,
    topic: c.topic,
    source: c.source,
    content: c.content,
    metadata: c.metadata || null,
  }));

  return { query: queryText, top_k: chunks.length, retrieval: 'keyword', chunks };
};

const listDocuments = async (db, page = 1, limit = 20) => {
  const total = await db.collection('ame_knowledge_documents').countDocuments();
  const documents = await db.collection('ame_knowledge_documents')
    .find({}, { projection: { _id: 0 } })
    .sort({ updated_at: -1 })
    .skip((page - 1) * limit)
    .limit(limit)
    .toArray();

  return {
    documents,
    pagination: {
      page,
      limit,
      total,
      pages: Math.ceil(total / limit),
    },
  };
};

const getDocument = async (db, documentId) => {
  const document = await db.collection('ame_knowledge_documents').findOne(
    { document_id: documentId },
    { projection: { _id: 0 } }
  );
  if (!document) return null;

  const chunks = await db.collection('ame_knowledge_chunks')
    .find({ document_id: documentId }, { projection: { embedding: 0, _id: 0 } })
    .sort({ chunk_index: 1 })
    .toArray();

  return { ...document, chunks };
};

const deleteDocument = async (db, documentId) => {
  const doc = await db.collection('ame_knowledge_documents').findOne({ document_id: documentId });
  if (!doc) return { deleted: false };

  await db.collection('ame_knowledge_documents').deleteOne({ document_id: documentId });
  const result = await db.collection('ame_knowledge_chunks').deleteMany({ document_id: documentId });

  return { deleted: true, removed_chunks: result.deletedCount };
};

const getStats = async (db) => {
  const documentCount = await db.collection('ame_knowledge_documents').countDocuments();
  const chunkCount = await db.collection('ame_knowledge_chunks').countDocuments();

  const topicsResult = await db.collection('ame_knowledge_documents').distinct('topic');
  const documentsResult = await db.collection('ame_knowledge_documents').distinct('document_id');

  const embeddingSample = await db.collection('ame_knowledge_chunks').findOne(
    { embedding: { $exists: true, $ne: [] } },
    { projection: { embedding: 1, _id: 0 } }
  );

  return {
    enabled: isEnabled(),
    documents: documentCount,
    chunks: chunkCount,
    topics: topicsResult.filter(Boolean),
    embedding_dimensions: Array.isArray(embeddingSample && embeddingSample.embedding) ? embeddingSample.embedding.length : 0,
    average_chunks_per_document: documentCount > 0 ? Math.round((chunkCount / documentCount) * 100) / 100 : 0,
    documents_ids: documentsResult,
  };
};

module.exports = {
  isEnabled,
  chunkText,
  cosineSimilarity,
  ingestDocument,
  retrieve,
  keywordSearch,
  listDocuments,
  getDocument,
  deleteDocument,
  getStats,
};
