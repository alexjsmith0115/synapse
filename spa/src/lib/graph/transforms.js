/**
 * Transform API response data into Cytoscape.js elements format.
 * Cytoscape expects: { nodes: [{data: {id, label, ...}}], edges: [{data: {source, target, ...}}] }
 */

/**
 * Transform find_callees response (flat list or depth tree) to graph elements.
 * rootName: the queried method's full_name.
 */
export function calleesToElements(data, rootName) {
  const nodes = new Map();
  const edges = [];

  // Add root node
  if (rootName) {
    const shortName = rootName.split('.').pop();
    nodes.set(rootName, {
      data: { id: rootName, label: shortName, kind: 'Method', full_name: rootName },
    });
  }

  // data may be array (flat) or {root, callees} (depth tree)
  const callees = Array.isArray(data) ? data : (data?.callees || []);
  const root = Array.isArray(data) ? rootName : (data?.root || rootName);

  for (const item of callees) {
    const fn = item.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    const kind = item.kind || 'Method';

    if (!nodes.has(fn)) {
      nodes.set(fn, {
        data: {
          id: fn,
          label: shortName.length > 16 ? shortName.slice(0, 14) + '..' : shortName,
          kind,
          full_name: fn,
          file_path: item.file_path || '',
          line: item.line || 0,
        },
      });
    }

    // Edge from root (or parent at previous depth) to this callee
    const source = item.depth === 1 || !item.depth ? root : (item._parent || root);
    edges.push({
      data: {
        id: `e-${source}-${fn}`,
        source,
        target: fn,
        label: 'CALLS',
      },
    });
  }

  return { nodes: [...nodes.values()], edges };
}

/**
 * Transform find_usages structured response to graph elements.
 * Star layout: queried symbol at center, callers radiating outward with inward CALLS edges.
 */
export function usagesToElements(data, queriedName) {
  const nodes = new Map();
  const edges = [];

  // Center node — the queried symbol
  if (queriedName) {
    const shortName = queriedName.split('.').pop();
    nodes.set(queriedName, {
      data: { id: queriedName, label: shortName, kind: 'Method', full_name: queriedName },
    });
  }

  for (const item of (Array.isArray(data) ? data : [])) {
    const fn = item.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        data: {
          id: fn,
          label: shortName.length > 16 ? shortName.slice(0, 14) + '..' : shortName,
          kind: item.kind || 'Method',
          full_name: fn,
          file_path: item.file_path || '',
          line: item.line || 0,
        },
      });
    }
    // Edge: caller -> center (inward -- callers CALL the queried symbol)
    edges.push({
      data: {
        id: `e-${fn}-${queriedName}`,
        source: fn,
        target: queriedName,
        label: 'CALLS',
      },
    });
  }

  return { nodes: [...nodes.values()], edges };
}

/**
 * Transform get_hierarchy response to graph elements.
 */
export function hierarchyToElements(data) {
  const nodes = new Map();
  const edges = [];
  const target = data.target || '';

  // Target node (the queried class)
  if (target) {
    const shortName = target.split('.').pop();
    nodes.set(target, {
      data: { id: target, label: shortName, kind: 'Class', full_name: target },
    });
  }

  // Parents (classes/interfaces this inherits from)
  for (const parent of data.parents || []) {
    const fn = parent.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        data: {
          id: fn,
          label: shortName,
          kind: parent.kind || 'Class',
          full_name: fn,
          file_path: parent.file_path || '',
          line: parent.line || 0,
        },
      });
    }
    edges.push({ data: { id: `e-${target}-${fn}`, source: target, target: fn, label: 'INHERITS' } });
  }

  // Children (classes that extend this)
  for (const child of data.children || []) {
    const fn = child.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        data: {
          id: fn,
          label: shortName,
          kind: child.kind || 'Class',
          full_name: fn,
          file_path: child.file_path || '',
          line: child.line || 0,
        },
      });
    }
    edges.push({ data: { id: `e-${fn}-${target}`, source: fn, target, label: 'INHERITS' } });
  }

  return { nodes: [...nodes.values()], edges };
}

/**
 * Transform execute_query (Cypher) results to graph elements.
 * Heuristic: if rows contain objects with full_name, render as nodes.
 * Edges are inferred from consecutive node pairs in each row.
 */
export function cypherToElements(data) {
  const nodes = new Map();
  const edges = [];

  for (const item of data || []) {
    const row = item.row || [];
    let prevNodeId = null;

    for (const cell of row) {
      if (cell && typeof cell === 'object' && cell.full_name) {
        const fn = cell.full_name;
        const shortName = (cell.name || fn.split('.').pop());
        if (!nodes.has(fn)) {
          nodes.set(fn, {
            data: {
              id: fn,
              label: shortName.length > 16 ? shortName.slice(0, 14) + '..' : shortName,
              kind: cell.kind || 'Class',
              full_name: fn,
              file_path: cell.file_path || '',
              line: cell.line || 0,
            },
          });
        }
        if (prevNodeId && prevNodeId !== fn) {
          edges.push({
            data: { id: `e-${prevNodeId}-${fn}`, source: prevNodeId, target: fn },
          });
        }
        prevNodeId = fn;
      }
    }
  }

  return { nodes: [...nodes.values()], edges };
}

/**
 * Check if Cypher result rows contain graph-renderable objects.
 */
export function isGraphResult(data) {
  if (!Array.isArray(data) || data.length === 0) return false;
  const row = data[0]?.row;
  if (!Array.isArray(row)) return false;
  return row.some(cell => cell && typeof cell === 'object' && cell.full_name);
}
