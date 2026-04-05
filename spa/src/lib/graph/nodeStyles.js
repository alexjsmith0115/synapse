/**
 * Cytoscape.js stylesheet array.
 * Uses CSS custom properties via getComputedStyle for theme-aware colors.
 * Since Cytoscape styles are not CSS but JS objects, we read the CSS vars
 * and build the style array dynamically.
 */

export function getCSSVar(name) {
  if (typeof document === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Get fill color for a node kind, reading CSS custom properties at call time.
 * Returns hex fallback if CSS var is not available (e.g. in tests).
 */
export function getNodeColor(kind) {
  const map = {
    'Class':     { cssVar: '--node-class',     fallback: '#2D6A4F' },
    'Interface': { cssVar: '--node-interface',  fallback: '#52A67A' },
    'Method':    { cssVar: '--node-method',     fallback: '#74C69D' },
    'Field':     { cssVar: '--node-field',      fallback: '#A8D8BE' },
    'Package':   { cssVar: '--node-package',    fallback: '#C3DDD0' },
    'File':      { cssVar: '--node-file',       fallback: '#E8F4ED' },
    'External':  { cssVar: '--node-external',   fallback: '#F0F0F0' },
    'Property':  { cssVar: '--node-field',      fallback: '#A8D8BE' },
    'Namespace': { cssVar: '--node-package',    fallback: '#C3DDD0' },
    'Endpoint':  { cssVar: '--node-method',     fallback: '#74C69D' },
  };
  const entry = map[kind] || map['Method'];
  return getCSSVar(entry.cssVar) || entry.fallback;
}

/**
 * Get text color for a node kind (light text on dark backgrounds, dark on light).
 */
export function getNodeTextColor(kind) {
  const darkBg = ['Class', 'Interface'];
  return darkBg.includes(kind) ? '#FFFFFF' : (getCSSVar('--color-text-primary') || '#1A2E23');
}

/**
 * Append the correct SVG shape for a node kind to a D3 selection.
 * Per D-03: Class=rounded-rect, Method=ellipse, Field=diamond, Interface=rounded-rect,
 * Package=rounded-rect, File=rounded-rect.
 */
export function appendNodeShape(selection, kind) {
  switch (kind) {
    case 'Method':
    case 'Endpoint':
      return selection.append('ellipse').attr('rx', 24).attr('ry', 18);
    case 'Field':
    case 'Property':
      return selection.append('polygon')
        .attr('points', '-20,0 0,-16 20,0 0,16');
    default:
      // Class, Interface, Package, File, External, Namespace — rounded rect
      return selection.append('rect')
        .attr('x', -32).attr('y', -18)
        .attr('width', 64).attr('height', 36)
        .attr('rx', 6);
  }
}

export function buildStyles() {
  return [
    // Node base style
    {
      selector: 'node',
      style: {
        'label': 'data(label)',
        'text-valign': 'center',
        'text-halign': 'center',
        'font-size': '12px',
        'font-weight': 600,
        'font-family': 'system-ui, -apple-system, sans-serif',
        'color': getCSSVar('--color-text-primary') || '#1A2E23',
        'text-max-width': '100px',
        'text-wrap': 'ellipsis',
        'width': 50,
        'height': 50,
        'border-width': 2,
        'shape': 'round-rectangle',
      },
    },
    // Kind-specific colors using node-class CSS var
    {
      selector: 'node[kind = "Class"]',
      style: {
        'background-color': getCSSVar('--node-class') || '#2D6A4F',
        'border-color': getCSSVar('--node-class') || '#2D6A4F',
        'color': '#FFFFFF',
      },
    },
    {
      selector: 'node[kind = "Interface"]',
      style: {
        'background-color': getCSSVar('--node-interface') || '#52A67A',
        'border-color': getCSSVar('--node-interface') || '#52A67A',
        'color': '#FFFFFF',
      },
    },
    {
      selector: 'node[kind = "Method"]',
      style: {
        'background-color': getCSSVar('--node-method') || '#74C69D',
        'border-color': getCSSVar('--node-method') || '#74C69D',
        'color': '#1A2E23',
        'shape': 'ellipse',
      },
    },
    {
      selector: 'node[kind = "Field"]',
      style: {
        'background-color': getCSSVar('--node-field') || '#A8D8BE',
        'border-color': getCSSVar('--node-field') || '#A8D8BE',
        'color': '#1A2E23',
        'shape': 'diamond',
      },
    },
    {
      selector: 'node[kind = "Package"]',
      style: {
        'background-color': getCSSVar('--node-package') || '#C3DDD0',
        'border-color': getCSSVar('--node-package') || '#C3DDD0',
        'color': '#1A2E23',
      },
    },
    {
      selector: 'node[kind = "File"]',
      style: {
        'background-color': getCSSVar('--node-file') || '#E8F4ED',
        'border-color': getCSSVar('--node-external-stroke') || '#74C69D',
        'color': '#1A2E23',
      },
    },
    // External stub nodes (dashed border)
    {
      selector: 'node[kind = "External"]',
      style: {
        'background-color': getCSSVar('--node-external') || '#F0F0F0',
        'border-color': getCSSVar('--node-external-stroke') || '#74C69D',
        'border-style': 'dashed',
        'color': '#666666',
      },
    },
    // Selected node
    {
      selector: 'node:selected',
      style: {
        'border-width': 4,
        'border-color': getCSSVar('--color-accent') || '#2D6A4F',
      },
    },
    // Edge base style
    {
      selector: 'edge',
      style: {
        'width': 2,
        'line-color': getCSSVar('--color-border') || '#C3DDD0',
        'target-arrow-color': getCSSVar('--color-border') || '#C3DDD0',
        'target-arrow-shape': 'triangle',
        'curve-style': 'bezier',
        'arrow-scale': 1.2,
      },
    },
    // Edge with label
    {
      selector: 'edge[label]',
      style: {
        'label': 'data(label)',
        'font-size': '10px',
        'color': getCSSVar('--color-text-secondary') || '#4A6D5A',
        'text-background-color': getCSSVar('--color-dominant') || '#F7FAF8',
        'text-background-opacity': 0.8,
        'text-background-padding': '2px',
      },
    },
    // Selected edge
    {
      selector: 'edge:selected',
      style: {
        'width': 3,
        'line-color': getCSSVar('--color-accent') || '#2D6A4F',
        'target-arrow-color': getCSSVar('--color-accent') || '#2D6A4F',
      },
    },
  ];
}
