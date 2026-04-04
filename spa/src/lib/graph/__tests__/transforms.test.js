import { describe, it, expect } from 'vitest';
import { calleesToElements, hierarchyToElements, usagesToElements, cypherToElements, isGraphResult } from '../transforms.js';

describe('calleesToElements', () => {
  it('transforms flat array to {nodes, edges}', () => {
    const data = [
      { full_name: 'A.B.Foo', name: 'Foo', file_path: '/src/a.cs', line: 10 },
      { full_name: 'A.B.Bar', name: 'Bar', file_path: '/src/b.cs', line: 20 },
    ];
    const result = calleesToElements(data, 'A.B.Root');
    expect(result).toHaveProperty('nodes');
    expect(result).toHaveProperty('edges');
    expect(Array.isArray(result.nodes)).toBe(true);
    expect(Array.isArray(result.edges)).toBe(true);
    // Root + 2 callees = 3 nodes
    expect(result.nodes).toHaveLength(3);
    expect(result.edges).toHaveLength(2);
  });

  it('transforms depth tree to {nodes, edges}', () => {
    const data = {
      root: 'A.B.Root',
      callees: [
        { full_name: 'A.B.Foo', depth: 1, file_path: '/src/a.cs', line: 10 },
      ],
      depth_limit: 3,
    };
    const result = calleesToElements(data, 'A.B.Root');
    expect(result.nodes.length).toBeGreaterThanOrEqual(2);
    expect(result.edges.length).toBeGreaterThanOrEqual(1);
  });

  it('returns root node with empty callees', () => {
    const result = calleesToElements([], 'A.B.Root');
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].data.id).toBe('A.B.Root');
    expect(result.edges).toHaveLength(0);
  });

  it('node data has expected fields', () => {
    const data = [{ full_name: 'X.Y', name: 'Y', file_path: '/f.cs', line: 5 }];
    const result = calleesToElements(data, 'Root');
    const callee = result.nodes.find(n => n.data.id === 'X.Y');
    expect(callee.data).toHaveProperty('id');
    expect(callee.data).toHaveProperty('label');
    expect(callee.data).toHaveProperty('kind');
    expect(callee.data).toHaveProperty('full_name');
    expect(callee.data).toHaveProperty('file_path');
    expect(callee.data).toHaveProperty('line');
  });
});

describe('hierarchyToElements', () => {
  it('returns nodes for target, parents, and children', () => {
    const data = {
      target: 'A.MyClass',
      parents: [{ full_name: 'A.Base', kind: 'Class' }],
      children: [{ full_name: 'A.Child', kind: 'Class' }],
    };
    const result = hierarchyToElements(data);
    expect(result.nodes).toHaveLength(3);
    expect(result.edges).toHaveLength(2);
  });

  it('returns single node when no parents or children', () => {
    const data = { target: 'A.MyClass', parents: [], children: [] };
    const result = hierarchyToElements(data);
    expect(result.nodes).toHaveLength(1);
    expect(result.edges).toHaveLength(0);
  });

  it('edges have INHERITS label', () => {
    const data = {
      target: 'A.MyClass',
      parents: [{ full_name: 'A.Base' }],
      children: [],
    };
    const result = hierarchyToElements(data);
    expect(result.edges[0].data.label).toBe('INHERITS');
  });
});

describe('usagesToElements', () => {
  it('creates center node and caller nodes with inward edges', () => {
    const data = [
      { full_name: 'A.Caller1', kind: 'Method', file_path: '/a.cs', line: 10 },
      { full_name: 'B.Caller2', kind: 'Method', file_path: '/b.cs', line: 20 },
    ];
    const result = usagesToElements(data, 'X.Target');
    expect(result.nodes).toHaveLength(3);
    expect(result.edges).toHaveLength(2);
    expect(result.edges[0].data.source).toBe('A.Caller1');
    expect(result.edges[0].data.target).toBe('X.Target');
    expect(result.edges[1].data.source).toBe('B.Caller2');
    expect(result.edges[1].data.target).toBe('X.Target');
  });

  it('returns center node only when data is empty', () => {
    const result = usagesToElements([], 'X.Target');
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].data.id).toBe('X.Target');
    expect(result.edges).toHaveLength(0);
  });

  it('handles null/undefined data gracefully', () => {
    const result = usagesToElements(null, 'X.Target');
    expect(result.nodes).toHaveLength(1);
    expect(result.edges).toHaveLength(0);
  });

  it('truncates long caller labels', () => {
    const data = [
      { full_name: 'Some.Very.Long.ClassName.MethodName', kind: 'Method' },
    ];
    const result = usagesToElements(data, 'X.T');
    const callerNode = result.nodes.find(n => n.data.id === 'Some.Very.Long.ClassName.MethodName');
    expect(callerNode.data.label.length).toBeLessThanOrEqual(16);
  });

  it('edges have CALLS label', () => {
    const data = [{ full_name: 'A.Caller', kind: 'Method' }];
    const result = usagesToElements(data, 'X.Target');
    expect(result.edges[0].data.label).toBe('CALLS');
  });
});

describe('cypherToElements', () => {
  it('extracts nodes from rows with full_name', () => {
    const data = [
      { row: [{ full_name: 'A.Foo', name: 'Foo', kind: 'Method' }] },
      { row: [{ full_name: 'A.Bar', name: 'Bar', kind: 'Class' }] },
    ];
    const result = cypherToElements(data);
    expect(result.nodes).toHaveLength(2);
  });

  it('returns empty for non-graph data', () => {
    const data = [{ row: ['scalar', 42] }];
    const result = cypherToElements(data);
    expect(result.nodes).toHaveLength(0);
    expect(result.edges).toHaveLength(0);
  });
});

describe('isGraphResult', () => {
  it('returns true for rows with full_name objects', () => {
    const data = [{ row: [{ full_name: 'A.Foo', kind: 'Method' }] }];
    expect(isGraphResult(data)).toBe(true);
  });

  it('returns false for scalar rows', () => {
    const data = [{ row: ['hello', 42] }];
    expect(isGraphResult(data)).toBe(false);
  });

  it('returns false for empty array', () => {
    expect(isGraphResult([])).toBe(false);
  });
});
