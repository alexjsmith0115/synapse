
export function getCSSVar(name) {
  if (typeof document === 'undefined') return '';
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

/**
 * Get fill color for a node kind, reading CSS custom properties at call time.
 * Returns hex fallback if CSS var is not available (e.g. in tests).
 * Colors chosen for maximum distinction since all nodes are now uniform circles.
 */
export function getNodeColor(kind) {
  const map = {
    'Class':     { cssVar: '--node-class',     fallback: '#4A90D9' },
    'Interface': { cssVar: '--node-interface',  fallback: '#9B59B6' },
    'Method':    { cssVar: '--node-method',     fallback: '#2ECC71' },
    'Field':     { cssVar: '--node-field',      fallback: '#E67E22' },
    'Property':  { cssVar: '--node-field',      fallback: '#E67E22' },
    'Package':   { cssVar: '--node-package',    fallback: '#1ABC9C' },
    'File':      { cssVar: '--node-file',       fallback: '#95A5A6' },
    'External':  { cssVar: '--node-external',   fallback: '#BDC3C7' },
    'Namespace': { cssVar: '--node-package',    fallback: '#1ABC9C' },
    'Endpoint':  { cssVar: '--node-method',     fallback: '#E74C3C' },
  };
  const entry = map[kind] || map['Method'];
  return getCSSVar(entry.cssVar) || entry.fallback;
}

/**
 * Get text color for a node kind.
 * Dark backgrounds (Class, Interface, Method, Package, Namespace, Endpoint) use white text.
 * Light backgrounds (Field, Property, File, External) use dark text.
 */
export function getNodeTextColor(kind) {
  const lightBg = ['Field', 'Property', 'File', 'External'];
  return lightBg.includes(kind) ? '#333333' : '#FFFFFF';
}

/**
 * Append a circle SVG shape for a node to a D3 selection.
 * All kinds render as uniform circles — color is the primary visual differentiator.
 */
export function appendNodeShape(selection, kind) {
  return selection.append('circle').attr('r', 22);
}
