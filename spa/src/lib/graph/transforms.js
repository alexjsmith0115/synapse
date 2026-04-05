/**
 * Transform API response data into D3-native graph format.
 * D3 expects: { nodes: [{id, label, ...}], links: [{source, target, ...}] }
 * Flat objects — no {data:{...}} wrappers.
 */

/**
 * Transform find_callees response (flat list or depth tree) to graph elements.
 * rootName: the queried method's full_name.
 */
export function calleesToElements(data, rootName, queriedKind) {
  const nodes = new Map();
  const links = [];

  // Add root node — queriedKind from API takes precedence, then data.kind for depth-tree responses
  if (rootName) {
    const shortName = rootName.split('.').pop();
    nodes.set(rootName, {
      id: rootName, label: shortName, kind: queriedKind || data?.kind || 'Method', full_name: rootName,
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
        id: fn,
        label: shortName,
        kind,
        full_name: fn,
        file_path: item.file_path || '',
        line: item.line || 0,
      });
    }

    // Link from root (or parent at previous depth) to this callee
    const source = item.depth === 1 || !item.depth ? root : (item._parent || root);
    links.push({
      id: `e-${source}-${fn}`,
      source,
      target: fn,
      label: 'CALLS',
    });
  }

  return { nodes: [...nodes.values()], links };
}

/**
 * Transform find_usages structured response to graph elements.
 * Star layout: queried symbol at center, callers radiating outward with inward CALLS links.
 */
export function usagesToElements(data, queriedName, queriedKind) {
  const nodes = new Map();
  const links = [];

  // Center node — the queried symbol; kind comes from caller or defaults to Method
  if (queriedName) {
    const shortName = queriedName.split('.').pop();
    nodes.set(queriedName, {
      id: queriedName, label: shortName, kind: queriedKind || 'Method', full_name: queriedName,
    });
  }

  for (const item of (Array.isArray(data) ? data : [])) {
    const fn = item.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        id: fn,
        label: shortName,
        kind: item.kind || 'Method',
        full_name: fn,
        file_path: item.file_path || '',
        line: item.line || 0,
      });
    }
    // Link: caller -> center (inward — callers CALL the queried symbol)
    links.push({
      id: `e-${fn}-${queriedName}`,
      source: fn,
      target: queriedName,
      label: 'CALLS',
    });
  }

  return { nodes: [...nodes.values()], links };
}

/**
 * Transform get_hierarchy response to graph elements.
 */
export function hierarchyToElements(data) {
  const nodes = new Map();
  const links = [];
  const target = data.target || '';

  // Target node (the queried class)
  if (target) {
    const shortName = target.split('.').pop();
    nodes.set(target, { id: target, label: shortName, kind: 'Class', full_name: target });
  }

  // Parents (classes/interfaces this inherits from)
  for (const parent of data.parents || []) {
    const fn = parent.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        id: fn,
        label: shortName,
        kind: parent.kind || 'Class',
        full_name: fn,
        file_path: parent.file_path || '',
        line: parent.line || 0,
      });
    }
    links.push({ id: `e-${target}-${fn}`, source: target, target: fn, label: 'INHERITS' });
  }

  // Children (classes that extend this)
  for (const child of data.children || []) {
    const fn = child.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        id: fn,
        label: shortName,
        kind: child.kind || 'Class',
        full_name: fn,
        file_path: child.file_path || '',
        line: child.line || 0,
      });
    }
    links.push({ id: `e-${fn}-${target}`, source: fn, target, label: 'INHERITS' });
  }

  return { nodes: [...nodes.values()], links };
}

/**
 * Transform execute_query (Cypher) results to graph elements.
 * Heuristic: if rows contain objects with full_name, render as nodes.
 * Links are inferred from consecutive node pairs in each row.
 */
export function cypherToElements(data) {
  const nodes = new Map();
  const links = [];

  for (const item of data || []) {
    const row = item.row || [];
    let prevNodeId = null;

    for (const cell of row) {
      if (cell && typeof cell === 'object' && cell.full_name) {
        const fn = cell.full_name;
        const shortName = (cell.name || fn.split('.').pop());
        if (!nodes.has(fn)) {
          nodes.set(fn, {
            id: fn,
            label: shortName,
            kind: cell.kind || 'Class',
            full_name: fn,
            file_path: cell.file_path || '',
            line: cell.line || 0,
          });
        }
        if (prevNodeId && prevNodeId !== fn) {
          links.push({ id: `e-${prevNodeId}-${fn}`, source: prevNodeId, target: fn });
        }
        prevNodeId = fn;
      }
    }
  }

  return { nodes: [...nodes.values()], links };
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

/**
 * Transform /api/expand_node response to D3 graph format.
 * data: { full_name, neighbors: [{full_name, kind, rel_type, direction, ...}] }
 * depth: optional depth level for the neighbor nodes (default 0); used for opacity fading.
 *   The center node is NOT assigned a depth here — it already exists in the graph.
 */
export function neighborhoodToElements(data, depth = 0) {
  const nodes = new Map();
  const links = [];
  const center = data.full_name;

  // Add center node (no depth override — it already exists in the accumulated graph).
  // Use data.kind when available so caller's actual kind is reflected (not hardcoded Method).
  if (center) {
    nodes.set(center, {
      id: center,
      label: center.split('.').pop(),
      kind: data.kind || 'Method',
      full_name: center,
    });
  }

  for (const neighbor of data.neighbors || []) {
    const fn = neighbor.full_name;
    if (!fn) continue;
    const shortName = fn.split('.').pop();
    if (!nodes.has(fn)) {
      nodes.set(fn, {
        id: fn,
        label: shortName,
        kind: neighbor.kind || 'Method',
        full_name: fn,
        file_path: neighbor.file_path || '',
        line: neighbor.line || 0,
        name: neighbor.name || shortName,
        signature: neighbor.signature || '',
        depth,
      });
    }
    const [src, tgt] = neighbor.direction === 'out' ? [center, fn] : [fn, center];
    links.push({ id: `e-${src}-${tgt}-${neighbor.rel_type}`, source: src, target: tgt, label: neighbor.rel_type });
  }

  return { nodes: [...nodes.values()], links };
}
