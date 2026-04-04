/**
 * Layout configurations per graph view type.
 * Dagre: hierarchical DAG — call graphs, class hierarchy.
 * Cose-bilkent: force-directed — architecture overview, Cypher exploration.
 */
export function getLayout(viewType) {
  switch (viewType) {
    case 'callees':
    case 'hierarchy':
    case 'usages':
      return {
        name: 'dagre',
        rankDir: 'LR',
        nodeSep: 60,
        rankSep: 120,
        animate: false,
      };
    case 'architecture':
    case 'cypher':
    default:
      return {
        name: 'cose-bilkent',
        animate: false,
        nodeRepulsion: 4500,
        idealEdgeLength: 100,
        edgeElasticity: 0.1,
        nestingFactor: 0.1,
        gravity: 0.25,
        tile: true,
      };
  }
}
