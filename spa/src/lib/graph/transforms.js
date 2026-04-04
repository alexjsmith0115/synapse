/**
 * Graph data transforms: convert API response shapes into Cytoscape elements.
 * All functions return { nodes: [...], edges: [...] }.
 *
 * Node data shape: { id, label, kind, full_name, file_path, line }
 * Edge data shape: { id, source, target, label }
 */

/**
 * Converts find_callees API response to Cytoscape elements.
 * Accepts either a flat array of callees or a depth-tree { root, callees, depth_limit }.
 */
export function calleesToElements(data, rootFullName) {
  const nodes = new Map();
  const edges = [];

  const addNode = (fullName, name, kind = 'method', filePath = '', line = 0) => {
    if (!nodes.has(fullName)) {
      nodes.set(fullName, {
        data: {
          id: fullName,
          label: name || _shortName(fullName),
          kind,
          full_name: fullName,
          file_path: filePath,
          line,
        },
      });
    }
  };

  // Root node
  addNode(rootFullName, _shortName(rootFullName), 'method', '', 0);

  if (Array.isArray(data)) {
    // Flat array: each item is a direct callee
    for (const item of data) {
      const id = item.full_name || item.name;
      if (!id) continue;
      addNode(id, item.name || _shortName(id), item.kind || 'method', item.file_path || '', item.line || 0);
      edges.push({
        data: {
          id: `${rootFullName}->${id}`,
          source: rootFullName,
          target: id,
          label: 'CALLS',
        },
      });
    }
  } else if (data && Array.isArray(data.callees)) {
    // Depth tree: { root, callees: [{ full_name, depth, ... }], depth_limit }
    const root = data.root || rootFullName;
    if (root !== rootFullName) {
      addNode(root, _shortName(root), 'method', '', 0);
      edges.push({ data: { id: `${rootFullName}->${root}`, source: rootFullName, target: root, label: 'CALLS' } });
    }
    for (const item of data.callees) {
      const id = item.full_name || item.name;
      if (!id) continue;
      addNode(id, item.name || _shortName(id), item.kind || 'method', item.file_path || '', item.line || 0);
      // Connect depth-1 items to root; deeper items to their parent (approximated here)
      const src = item.depth === 1 ? root : root;
      edges.push({
        data: {
          id: `${src}->${id}-${item.depth}`,
          source: src,
          target: id,
          label: 'CALLS',
        },
      });
    }
  }

  return { nodes: Array.from(nodes.values()), edges };
}

/**
 * Converts get_hierarchy API response to Cytoscape elements.
 * Accepts { target, parents: [...], children: [...] }.
 */
export function hierarchyToElements(data) {
  const nodes = [];
  const edges = [];
  const seen = new Set();

  const addNode = (fullName, kind = 'class') => {
    if (seen.has(fullName)) return;
    seen.add(fullName);
    nodes.push({
      data: {
        id: fullName,
        label: _shortName(fullName),
        kind,
        full_name: fullName,
      },
    });
  };

  const target = data.target || '';
  addNode(target, 'class');

  for (const parent of data.parents || []) {
    const id = parent.full_name || parent;
    addNode(id, parent.kind || 'class');
    // Parent inherits: parent -> target
    edges.push({
      data: {
        id: `${id}->INHERITS->${target}`,
        source: id,
        target,
        label: 'INHERITS',
      },
    });
  }

  for (const child of data.children || []) {
    const id = child.full_name || child;
    addNode(id, child.kind || 'class');
    // Child inherits from target: target -> child
    edges.push({
      data: {
        id: `${target}->INHERITS->${id}`,
        source: target,
        target: id,
        label: 'INHERITS',
      },
    });
  }

  return { nodes, edges };
}

/**
 * Converts execute_query API response (array of { row: [...] }) to Cytoscape elements.
 * Only graph-renderable rows (containing objects with full_name) are converted.
 */
export function cypherToElements(data) {
  const nodes = new Map();
  const edges = [];

  if (!Array.isArray(data)) return { nodes: [], edges: [] };

  for (const record of data) {
    const row = record.row || [];
    for (const value of row) {
      if (value && typeof value === 'object' && value.full_name) {
        const id = value.full_name;
        if (!nodes.has(id)) {
          nodes.set(id, {
            data: {
              id,
              label: value.name || _shortName(id),
              kind: (value.kind || 'unknown').toLowerCase(),
              full_name: id,
              file_path: value.file_path || '',
              line: value.line || 0,
            },
          });
        }
      }
    }
  }

  return { nodes: Array.from(nodes.values()), edges };
}

/**
 * Returns true if the execute_query result rows contain graph-renderable objects.
 * Used to decide whether to show graph view or table view for raw Cypher results.
 */
export function isGraphResult(data) {
  if (!Array.isArray(data) || data.length === 0) return false;
  const first = data[0];
  if (!first || !Array.isArray(first.row)) return false;
  return first.row.some(v => v && typeof v === 'object' && v.full_name);
}

/**
 * Derives a short display name from a fully-qualified name (last segment).
 */
function _shortName(fullName) {
  if (!fullName) return '';
  const parts = fullName.split('.');
  return parts[parts.length - 1] || fullName;
}
