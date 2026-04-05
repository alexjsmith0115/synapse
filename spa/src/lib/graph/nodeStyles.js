
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
      return selection.append('circle').attr('r', 20);
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

