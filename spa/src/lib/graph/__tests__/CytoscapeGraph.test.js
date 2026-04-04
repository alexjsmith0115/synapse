import { describe, it, expect } from 'vitest';
import { computeGraphDiff } from '../graphDiff.js';

describe('computeGraphDiff', () => {
  const elements = [
    { data: { id: 'a' } },
    { data: { id: 'b' } },
  ];

  it('returns reset mode when graphKey differs from lastGraphKey (D-12)', () => {
    const result = computeGraphDiff(elements, new Set(), 2, 1);
    expect(result.mode).toBe('reset');
    expect(result.newElements).toEqual(elements);
  });

  it('returns incremental mode when graphKey matches and new elements exist (D-11)', () => {
    const existing = new Set(['a']);
    const result = computeGraphDiff(elements, existing, 1, 1);
    expect(result.mode).toBe('incremental');
    expect(result.newElements).toEqual([{ data: { id: 'b' } }]);
  });

  it('returns noop when graphKey matches and all elements already exist', () => {
    const existing = new Set(['a', 'b']);
    const result = computeGraphDiff(elements, existing, 1, 1);
    expect(result.mode).toBe('noop');
    expect(result.newElements).toEqual([]);
  });

  it('returns reset with empty elements when graphKey changes and no elements', () => {
    const result = computeGraphDiff([], new Set(), 3, 2);
    expect(result.mode).toBe('reset');
    expect(result.newElements).toEqual([]);
  });

  it('returns incremental with only genuinely new elements', () => {
    const elems = [
      { data: { id: 'x' } },
      { data: { id: 'y' } },
      { data: { id: 'z' } },
    ];
    const existing = new Set(['x', 'z']);
    const result = computeGraphDiff(elems, existing, 5, 5);
    expect(result.mode).toBe('incremental');
    expect(result.newElements).toEqual([{ data: { id: 'y' } }]);
  });
});
