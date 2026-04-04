/**
 * Determine whether to do a full reset or incremental add.
 * Returns { mode: 'reset' | 'incremental' | 'noop', newElements: [] }
 */
export function computeGraphDiff(allElements, existingIds, graphKey, lastGraphKey) {
  if (graphKey !== lastGraphKey) {
    return { mode: 'reset', newElements: allElements };
  }
  const newElements = allElements.filter(el => !existingIds.has(el.data.id));
  if (newElements.length === 0) {
    return { mode: 'noop', newElements: [] };
  }
  return { mode: 'incremental', newElements };
}
