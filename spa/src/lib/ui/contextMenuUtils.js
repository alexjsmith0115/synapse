/**
 * Determine whether the "Get Hierarchy" option should be shown
 * in the context menu. Per D-05, only Class and Interface kinds
 * have meaningful hierarchies.
 */
export function shouldShowHierarchy(kind) {
  return kind === 'Class' || kind === 'Interface';
}
