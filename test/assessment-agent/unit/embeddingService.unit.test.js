'use strict';

const mockAxiosPost = jest.fn();
jest.mock('axios', () => ({ post: (...args) => mockAxiosPost(...args) }), { virtual: true });

const embeddingService = require('../../../services/assessment-agent/src/services/embeddingService');

beforeEach(() => {
  mockAxiosPost.mockReset();
});

describe('embeddingService', () => {
  test('isEnabled defaults to true', () => {
    expect(embeddingService.isEnabled()).toBe(true);
  });

  test('embedTexts returns [] for empty / blank input without network calls', async () => {
    const result = await embeddingService.embedTexts([]);
    expect(result).toEqual([]);
    expect(mockAxiosPost).not.toHaveBeenCalled();

    const blank = await embeddingService.embedTexts(['   ', '']);
    expect(blank).toEqual([]);
    expect(mockAxiosPost).not.toHaveBeenCalled();
  });

  test('embedTexts hits the batch endpoint once and caches results', async () => {
    mockAxiosPost.mockResolvedValue({
      data: { embeddings: [[0.1, 0.2], [0.3, 0.4]] },
    });

    const first = await embeddingService.embedTexts(['alpha', 'beta']);
    const second = await embeddingService.embedTexts(['alpha', 'beta']);

    expect(first).toEqual([[0.1, 0.2], [0.3, 0.4]]);
    expect(second).toEqual([[0.1, 0.2], [0.3, 0.4]]);
    expect(mockAxiosPost).toHaveBeenCalledTimes(1);
  });

  test('returns cached embeddings for individual texts without network calls', async () => {
    mockAxiosPost.mockResolvedValue({
      data: { embeddings: [[0.5, 0.6]] },
    });

    const first = await embeddingService.embedText('cached-sentence');
    expect(first).toEqual([0.5, 0.6]);
    expect(mockAxiosPost).toHaveBeenCalledTimes(1);

    const second = await embeddingService.embedText('cached-sentence');
    expect(second).toEqual([0.5, 0.6]);
    expect(mockAxiosPost).toHaveBeenCalledTimes(1);
  });

  test('falls back to legacy per-prompt endpoint when the batch endpoint returns 404', async () => {
    const batchError = new Error('not found');
    batchError.response = { status: 404 };

    mockAxiosPost
      .mockRejectedValueOnce(batchError)
      .mockResolvedValue({ data: { embedding: [0.7, 0.8] } });

    const result = await embeddingService.embedTexts(['legacy-check']);
    expect(result).toEqual([[0.7, 0.8]]);

    const urls = mockAxiosPost.mock.calls.map((c) => c[0]);
    expect(urls.some((u) => u.endsWith('/api/embed'))).toBe(true);
    expect(urls.some((u) => u.endsWith('/api/embeddings'))).toBe(true);
  });

  test('trims leading/trailing whitespace and drops blank entries before embedding', async () => {
    mockAxiosPost.mockResolvedValue({ data: { embeddings: [[1, 1], [2, 2]] } });

    const result = await embeddingService.embedTexts(['  unique-token-123  ', 'unique-token-123', '   ']);
    expect(result).toEqual([[1, 1], [2, 2]]);
    expect(mockAxiosPost).toHaveBeenCalledTimes(1);
    expect(mockAxiosPost.mock.calls[0][1].input).toEqual(['unique-token-123', 'unique-token-123']);
  });
});