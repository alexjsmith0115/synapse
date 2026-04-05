/**
 * Remove a node and cascade-remove orphaned children.
 * Handles D3 post-simulation link objects where source/target are node references.
 */
export function removeNodeWithOrphans(nodeId, nodes, links) {
  const remainingLinks = links.filter(l => {
    const srcId = l.source?.id ?? l.source;
    const tgtId = l.target?.id ?? l.target;
    return srcId !== nodeId && tgtId !== nodeId;
  });

  const connected = new Set();
  remainingLinks.forEach(l => {
    connected.add(l.source?.id ?? l.source);
    connected.add(l.target?.id ?? l.target);
  });

  // Keep nodes that are still connected
  const remainingNodes = nodes.filter(n => n.id !== nodeId && connected.has(n.id));

  // If removing leaves no connected nodes but there were multiple, keep disconnected survivors
  if (remainingNodes.length === 0 && nodes.length > 1) {
    return { nodes: nodes.filter(n => n.id !== nodeId), links: remainingLinks };
  }

  return { nodes: remainingNodes, links: remainingLinks };
}
