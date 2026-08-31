'use strict';

jest.mock('axios', () => ({ post: jest.fn() }), { virtual: true });

const ragService = require('../../../services/assessment-agent/src/services/ragService');

describe('ragService pure logic', () => {
  describe('chunkText', () => {
    test('returns [] for empty / whitespace input', () => {
      expect(ragService.chunkText('')).toEqual([]);
      expect(ragService.chunkText('   \n  ')).toEqual([]);
      expect(ragService.chunkText(null)).toEqual([]);
    });

    test('returns the whole text as a single chunk when it fits', () => {
      const chunks = ragService.chunkText('Hello World', 800, 120);
      expect(chunks).toEqual(['Hello World']);
    });

    test('splits long text and applies overlap between consecutive chunks', () => {
      const source = 'abcd1234'.repeat(150);
      const chunks = ragService.chunkText(source, 60, 10);

      expect(chunks.length).toBeGreaterThan(1);
      chunks.forEach((c) => {
        expect(c.length).toBeGreaterThan(0);
        expect(c.length).toBeLessThanOrEqual(60);
      });
      expect(chunks.join('').length).toBeGreaterThanOrEqual(source.length);

      for (let i = 1; i < chunks.length; i++) {
        expect(chunks[i].startsWith(chunks[i - 1].slice(-10))).toBe(true);
      }
    });

    test('clamps overlap so it never exceeds half the chunk size', () => {
      const source = 'abcd1234'.repeat(150);
      const chunks = ragService.chunkText(source, 60, 1000);

      const maxOverlap = Math.floor(60 / 2);
      for (let i = 1; i < chunks.length; i++) {
        expect(chunks[i].startsWith(chunks[i - 1].slice(-maxOverlap))).toBe(true);
        expect(chunks[i].startsWith(chunks[i - 1].slice(-(maxOverlap + 1)))).toBe(false);
      }
    });
  });

  describe('cosineSimilarity', () => {
    test('identical vectors produce a similarity of 1', () => {
      const v = [1, 2, 3, 4];
      expect(ragService.cosineSimilarity(v, v)).toBeCloseTo(1, 5);
    });

    test('orthogonal vectors produce a similarity of 0', () => {
      expect(ragService.cosineSimilarity([1, 0, 0], [0, 1, 0])).toBeCloseTo(0, 5);
    });

    test('length-mismatched or empty inputs produce 0', () => {
      expect(ragService.cosineSimilarity([1, 2], [1, 2, 3])).toBe(0);
      expect(ragService.cosineSimilarity([], [])).toBe(0);
      expect(ragService.cosineSimilarity(null, [1])).toBe(0);
    });

    test('ranks a closer vector higher than a distant one', () => {
      const query = [1, 0, 0];
      const close = [0.9, 0.1, 0];
      const far = [0.1, 0.9, 0];
      expect(ragService.cosineSimilarity(query, close)).toBeGreaterThan(
        ragService.cosineSimilarity(query, far)
      );
    });
  });

  describe('isEnabled', () => {
    test('returns true when RAG is not explicitly disabled', () => {
      expect(ragService.isEnabled()).toBe(true);
    });
  });
});