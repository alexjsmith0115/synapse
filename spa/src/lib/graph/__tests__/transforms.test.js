import { describe, it, expect } from 'vitest';
import { calleesToElements, hierarchyToElements, usagesToElements, cypherToElements, isGraphResult, neighborhoodToElements } from '../transforms.js';

describe('calleesToElements', () => {
  it('transforms flat array to {nodes, links}', () => {
    const data = [
      { full_name: 'A.B.Foo', name: 'Foo', file_path: '/src/a.cs', line: 10 },
      { full_name: 'A.B.Bar', name: 'Bar', file_path: '/src/b.cs', line: 20 },
    ];
    const result = calleesToElements(data, 'A.B.Root');
    expect(result).toHaveProperty('nodes');
    expect(result).toHaveProperty('links');
    expect(Array.isArray(result.nodes)).toBe(true);
    expect(Array.isArray(result.links)).toBe(true);
    // Root + 2 callees = 3 nodes
    expect(result.nodes).toHaveLength(3);
    expect(result.links).toHaveLength(2);
  });

  it('transforms depth tree to {nodes, links}', () => {
    const data = {
      root: 'A.B.Root',
      callees: [
        { full_name: 'A.B.Foo', depth: 1, file_path: '/src/a.cs', line: 10 },
      ],
      depth_limit: 3,
    };
    const result = calleesToElements(data, 'A.B.Root');
    expect(result.nodes.length).toBeGreaterThanOrEqual(2);
    expect(result.links.length).toBeGreaterThanOrEqual(1);
  });

  it('returns root node with empty callees', () => {
    const result = calleesToElements([], 'A.B.Root');
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('A.B.Root');
    expect(result.links).toHaveLength(0);
  });

  it('node has expected fields (no data wrapper)', () => {
    const data = [{ full_name: 'X.Y', name: 'Y', file_path: '/f.cs', line: 5 }];
    const result = calleesToElements(data, 'Root');
    const callee = result.nodes.find(n => n.id === 'X.Y');
    expect(callee).toHaveProperty('id');
    expect(callee).toHaveProperty('label');
    expect(callee).toHaveProperty('kind');
    expect(callee).toHaveProperty('full_name');
    expect(callee).toHaveProperty('file_path');
    expect(callee).toHaveProperty('line');
    // Must NOT have a data wrapper
    expect(callee.data).toBeUndefined();
  });

  it('links have source and target at top level (no data wrapper)', () => {
    const data = [{ full_name: 'X.Y', name: 'Y' }];
    const result = calleesToElements(data, 'Root');
    expect(result.links[0].source).toBe('Root');
    expect(result.links[0].target).toBe('X.Y');
    expect(result.links[0].data).toBeUndefined();
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
    expect(result.links).toHaveLength(2);
  });

  it('returns single node when no parents or children', () => {
    const data = { target: 'A.MyClass', parents: [], children: [] };
    const result = hierarchyToElements(data);
    expect(result.nodes).toHaveLength(1);
    expect(result.links).toHaveLength(0);
  });

  it('links have INHERITS label at top level', () => {
    const data = {
      target: 'A.MyClass',
      parents: [{ full_name: 'A.Base' }],
      children: [],
    };
    const result = hierarchyToElements(data);
    expect(result.links[0].label).toBe('INHERITS');
    expect(result.links[0].data).toBeUndefined();
  });
});

describe('usagesToElements', () => {
  it('creates center node and caller nodes with inward links', () => {
    const data = [
      { full_name: 'A.Caller1', kind: 'Method', file_path: '/a.cs', line: 10 },
      { full_name: 'B.Caller2', kind: 'Method', file_path: '/b.cs', line: 20 },
    ];
    const result = usagesToElements(data, 'X.Target');
    expect(result.nodes).toHaveLength(3);
    expect(result.links).toHaveLength(2);
    expect(result.links[0].source).toBe('A.Caller1');
    expect(result.links[0].target).toBe('X.Target');
    expect(result.links[1].source).toBe('B.Caller2');
    expect(result.links[1].target).toBe('X.Target');
  });

  it('returns center node only when data is empty', () => {
    const result = usagesToElements([], 'X.Target');
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('X.Target');
    expect(result.links).toHaveLength(0);
  });

  it('handles null/undefined data gracefully', () => {
    const result = usagesToElements(null, 'X.Target');
    expect(result.nodes).toHaveLength(1);
    expect(result.links).toHaveLength(0);
  });

  it('truncates long caller labels', () => {
    const data = [
      { full_name: 'Some.Very.Long.ClassName.MethodName', kind: 'Method' },
    ];
    const result = usagesToElements(data, 'X.T');
    const callerNode = result.nodes.find(n => n.id === 'Some.Very.Long.ClassName.MethodName');
    expect(callerNode.label.length).toBeLessThanOrEqual(16);
  });

  it('links have CALLS label at top level', () => {
    const data = [{ full_name: 'A.Caller', kind: 'Method' }];
    const result = usagesToElements(data, 'X.Target');
    expect(result.links[0].label).toBe('CALLS');
    expect(result.links[0].data).toBeUndefined();
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
    expect(result.links).toHaveLength(0);
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

describe('neighborhoodToElements - center node kind', () => {
  it('center node defaults to kind=Method when data has no kind field', () => {
    const data = { full_name: 'A.Root', neighbors: [] };
    const result = neighborhoodToElements(data);
    expect(result.nodes[0].kind).toBe('Method');
  });

  it('center node uses kind from data when present', () => {
    const data = { full_name: 'A.MyClass', kind: 'Class', neighbors: [] };
    const result = neighborhoodToElements(data);
    expect(result.nodes[0].kind).toBe('Class');
  });

  it('center node uses Interface kind from data', () => {
    const data = { full_name: 'A.IRepo', kind: 'Interface', neighbors: [] };
    const result = neighborhoodToElements(data);
    expect(result.nodes[0].kind).toBe('Interface');
  });
});

describe('neighborhoodToElements', () => {
  it('includes center node and neighbor nodes', () => {
    const data = {
      full_name: 'A.Root',
      neighbors: [
        { full_name: 'A.Callee', kind: 'Method', rel_type: 'CALLS', direction: 'out', name: 'Callee', file_path: '/a.cs', line: 5, signature: '' },
        { full_name: 'A.Caller', kind: 'Method', rel_type: 'CALLS', direction: 'in', name: 'Caller', file_path: '/b.cs', line: 10, signature: '' },
      ],
    };
    const result = neighborhoodToElements(data);
    expect(result.nodes).toHaveLength(3);
    const ids = result.nodes.map(n => n.id);
    expect(ids).toContain('A.Root');
    expect(ids).toContain('A.Callee');
    expect(ids).toContain('A.Caller');
  });

  it('direction=out produces link from center to neighbor', () => {
    const data = {
      full_name: 'A.Root',
      neighbors: [
        { full_name: 'A.Callee', kind: 'Method', rel_type: 'CALLS', direction: 'out', name: 'Callee' },
      ],
    };
    const result = neighborhoodToElements(data);
    expect(result.links).toHaveLength(1);
    expect(result.links[0].source).toBe('A.Root');
    expect(result.links[0].target).toBe('A.Callee');
  });

  it('direction=in produces link from neighbor to center', () => {
    const data = {
      full_name: 'A.Root',
      neighbors: [
        { full_name: 'A.Caller', kind: 'Method', rel_type: 'CALLS', direction: 'in', name: 'Caller' },
      ],
    };
    const result = neighborhoodToElements(data);
    expect(result.links).toHaveLength(1);
    expect(result.links[0].source).toBe('A.Caller');
    expect(result.links[0].target).toBe('A.Root');
  });

  it('deduplicates neighbor nodes by full_name', () => {
    const data = {
      full_name: 'A.Root',
      neighbors: [
        { full_name: 'A.Dup', kind: 'Method', rel_type: 'CALLS', direction: 'out', name: 'Dup' },
        { full_name: 'A.Dup', kind: 'Method', rel_type: 'CALLS', direction: 'out', name: 'Dup' },
      ],
    };
    const result = neighborhoodToElements(data);
    expect(result.nodes.filter(n => n.id === 'A.Dup')).toHaveLength(1);
  });

  it('returns only center node for empty neighbors', () => {
    const data = { full_name: 'A.Root', neighbors: [] };
    const result = neighborhoodToElements(data);
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe('A.Root');
    expect(result.links).toHaveLength(0);
  });

  it('nodes have no data wrapper', () => {
    const data = {
      full_name: 'A.Root',
      neighbors: [
        { full_name: 'A.N', kind: 'Method', rel_type: 'CALLS', direction: 'out', name: 'N' },
      ],
    };
    const result = neighborhoodToElements(data);
    result.nodes.forEach(n => expect(n.data).toBeUndefined());
  });
});
