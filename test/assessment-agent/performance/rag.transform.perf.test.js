'use strict';

jest.mock('axios', () => ({ post: jest.fn() }), { virtual: true });

const ragService = require('../../../services/assessment-agent/src/services/ragService');
const embeddingService = require('../../../services/assessment-agent/src/services/embeddingService');

describe('performance: rag pure transformations', () => {
  test('chunking and cosine scoring on a sample payload complete under 1s', async () => {
    const sample = Array.from(
      { length: 600 },
      (_, i) => `Sentence ${i}: the AME agent scores vector similarity for knowledge chunks about algebra, calculus, vectors, matrices, and linear transformations over repeated lines.`
    ).join('\n');

    let started = Date.now();
    const chunks = ragService.chunkText(sample, 800, 120);
    const chunkMs = Date.now() - started;

    started = Date.now();
    let score = 0;
    for (let i = 1; i < chunks.length; i++) {
      score += ragService.cosineSimilarity(
        new Array(300).fill(0).map((_, idx) => (idx % 2 ? 1 : -1) * (i + 1)),
        new Array(300).fill(0).map((__, idx) => (idx % 3 ? 1 : -1) * (i + 2))
      );
    }
    const cosineMs = Date.now() - started;

    started = Date.now();
    const enabled = embeddingService.isEnabled();
    const utilMs = Date.now() - started;

    const elapsed = chunkMs + cosineMs + utilMs;
    console.log(
      `[performance] chunkText(${chunks.length} chunks)=${chunkMs}ms cosineSim(${chunks.length - 1} pairs)=${cosineMs}ms utils=${utilMs}ms total=${elapsed}ms`
    );

    expect(chunks.length).toBeGreaterThan(0);
    expect(enabled).toBe(true);
    expect(elapsed).toBeLessThan(1000);
  });
});