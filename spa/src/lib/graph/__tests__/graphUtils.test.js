import { describe, it, expect } from 'vitest';
import { removeNodeWithOrphans } from '../graphUtils.js';

describe('removeNodeWithOrphans', () => {
  it('removes the target node and its direct links, keeping other nodes as survivors', () => {
    const nodes = [
      { id: 'A' },
      { id: 'B' },
      { id: 'C' },
    ];
    // A -> B -> C (chain); removing B leaves both A and C disconnected — both survive
    const links = [
      { source: 'A', target: 'B' },
      { source: 'B', target: 'C' },
    ];
    const result = removeNodeWithOrphans('B', nodes, links);
    const ids = result.nodes.map(n => n.id);
    expect(ids).not.toContain('B');
    // Both A and C are disconnected survivors — kept since neither is the removed node
    expect(ids).toContain('A');
    expect(ids).toContain('C');
    expect(result.links).toHaveLength(0);
  });

  it('keeps nodes still connected via other paths', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }, { id: 'C' }];
    // A -> B, A -> C, B -> C; removing B keeps A and C (A->C still exists)
    const links = [
      { source: 'A', target: 'B' },
      { source: 'A', target: 'C' },
      { source: 'B', target: 'C' },
    ];
    const result = removeNodeWithOrphans('B', nodes, links);
    const ids = result.nodes.map(n => n.id);
    expect(ids).not.toContain('B');
    expect(ids).toContain('A');
    expect(ids).toContain('C');
  });

  it('handles D3 object-form source/target after simulation', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }, { id: 'C' }];
    // D3 post-simulation: source/target are node objects, not strings
    const links = [
      { source: { id: 'A', x: 0, y: 0 }, target: { id: 'B', x: 1, y: 1 } },
      { source: { id: 'B', x: 1, y: 1 }, target: { id: 'C', x: 2, y: 2 } },
    ];
    const result = removeNodeWithOrphans('A', nodes, links);
    const ids = result.nodes.map(n => n.id);
    expect(ids).not.toContain('A');
    // B and C remain connected to each other
    expect(ids).toContain('B');
    expect(ids).toContain('C');
  });

  it('returns empty nodes for single-node graph', () => {
    const nodes = [{ id: 'A' }];
    const links = [];
    const result = removeNodeWithOrphans('A', nodes, links);
    expect(result.nodes).toHaveLength(0);
    expect(result.links).toHaveLength(0);
  });

  it('removes only the target when it has no links', () => {
    const nodes = [{ id: 'A' }, { id: 'B' }, { id: 'Isolated' }];
    const links = [{ source: 'A', target: 'B' }];
    const result = removeNodeWithOrphans('Isolated', nodes, links);
    const ids = result.nodes.map(n => n.id);
    expect(ids).not.toContain('Isolated');
    expect(ids).toContain('A');
    expect(ids).toContain('B');
  });
});
