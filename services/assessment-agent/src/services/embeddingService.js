const axios = require('axios');

const OLLAMA_BASE_URL = process.env.OLLAMA_BASE_URL || 'http://localhost:11434';
const OLLAMA_EMBEDDING_MODEL = process.env.OLLAMA_EMBEDDING_MODEL || 'nomic-embed-text';
const EMBEDDING_TIMEOUT = Number(process.env.OLLAMA_EMBEDDING_TIMEOUT || 30000);

const isEnabled = () => process.env.RAG_ENABLED !== 'false';

const EMBEDDING_CACHE_MAX = 500;
const embeddingCache = new Map();

const getCachedEmbedding = (text) => {
  const key = String(text).trim().toLowerCase();
  return embeddingCache.get(key) || null;
};

const setCachedEmbedding = (text, embedding) => {
  const key = String(text).trim().toLowerCase();
  if (embeddingCache.size >= EMBEDDING_CACHE_MAX) {
    const firstKey = embeddingCache.keys().next().value;
    embeddingCache.delete(firstKey);
  }
  embeddingCache.set(key, embedding);
};

const embedTexts = async (texts, model = OLLAMA_EMBEDDING_MODEL) => {
  const input = (texts || []).map((t) => String(t).trim()).filter((t) => t.length > 0);
  if (input.length === 0) return [];

  const results = new Array(input.length);
  const uncached = [];

  for (let i = 0; i < input.length; i++) {
    const cached = getCachedEmbedding(input[i]);
    if (cached) {
      results[i] = cached;
    } else {
      uncached.push({ index: i, text: input[i] });
    }
  }

  if (uncached.length === 0) return results;

  try {
    const response = await axios.post(
      `${OLLAMA_BASE_URL}/api/embed`,
      { model, input: uncached.map(u => u.text) },
      {
        timeout: EMBEDDING_TIMEOUT,
        headers: { 'Content-Type': 'application/json' },
      }
    );
    const embeddings = response.data && response.data.embeddings;
    if (!Array.isArray(embeddings) || embeddings.length === 0) {
      throw new Error('Ollama returned no embeddings');
    }
    for (let j = 0; j < uncached.length; j++) {
      const emb = embeddings[j];
      results[uncached[j].index] = emb;
      setCachedEmbedding(uncached[j].text, emb);
    }
    return results;
  } catch (batchError) {
    if (!batchError.response || (batchError.response && batchError.response.status === 404)) {
      const legacyResults = await embedTextsLegacy(uncached.map(u => u.text), model);
      for (let j = 0; j < uncached.length; j++) {
        results[uncached[j].index] = legacyResults[j];
        setCachedEmbedding(uncached[j].text, legacyResults[j]);
      }
      return results;
    }
    throw batchError;
  }
};

const embedTextsLegacy = async (texts, model) => {
  const embeddings = [];
  for (const text of texts) {
    const cached = getCachedEmbedding(text);
    if (cached) {
      embeddings.push(cached);
      continue;
    }
    const response = await axios.post(
      `${OLLAMA_BASE_URL}/api/embeddings`,
      { model, prompt: text },
      {
        timeout: EMBEDDING_TIMEOUT,
        headers: { 'Content-Type': 'application/json' },
      }
    );
    const embedding = response.data && response.data.embedding;
    if (!Array.isArray(embedding)) {
      throw new Error('Ollama returned no embedding for prompt');
    }
    setCachedEmbedding(text, embedding);
    embeddings.push(embedding);
  }
  return embeddings;
};

const embedText = async (text, model) => {
  const cached = getCachedEmbedding(text);
  if (cached) return cached;
  const embeddings = await embedTexts([text], model);
  return embeddings[0] || [];
};

module.exports = { embedText, embedTexts, isEnabled };
