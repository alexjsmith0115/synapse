<script>
  import DataTable from '../ui/DataTable.svelte';
  import D3Graph from '../graph/D3Graph.svelte';
  import NodeDetailPanel from '../graph/NodeDetailPanel.svelte';
  import { calleesToElements, hierarchyToElements, usagesToElements, cypherToElements, neighborhoodToElements, isGraphResult } from '../graph/transforms.js';
  import { removeNodeWithOrphans } from '../graph/graphUtils.js';
  import { apiCall } from '../api.js';

  const { result = null, resultType = 'table', queryParams = {}, error = null, loading = false, onSymbolClick, activeTool = '', projectRoot = '', onDetailAction } = $props();

  // Accumulated graph elements — persists across node expansions.
  // Reset when a new top-level query result arrives (via $effect on result).
  let accumulatedGraphElements = $state({ nodes: [], links: [] });

  // Currently selected node — drives NodeDetailPanel visibility
  let selectedNode = $state(null);

  // When a new result arrives, compute the initial graph elements and reset accumulator
  $effect(() => {
    if (!result || resultType !== 'graph') {
      accumulatedGraphElements = { nodes: [], links: [] };
      return;
    }
    let initial;
    if (activeTool === 'find_callees') {
      const rootName = result?.root || queryParams?.full_name || '';
      initial = calleesToElements(result, rootName);
    } else if (activeTool === 'get_hierarchy') {
      initial = hierarchyToElements({ ...result, target: result.target || queryParams?.full_name || '' });
    } else if (activeTool === 'find_usages') {
      initial = usagesToElements(result, queryParams?.full_name || '');
    } else {
      initial = { nodes: [], links: [] };
    }
    accumulatedGraphElements = initial;
  });

  // Single-click: select node and open detail panel (per D-14)
  function handleNodeSelect(nodeData) {
    selectedNode = nodeData;  // null when clicking empty canvas (per D-07)
  }

  // Double-click: expand all relationships via /api/expand_node (per D-08, D-09, D-10, D-11)
  async function handleNodeExpand(nodeData) {
    if (!nodeData?.full_name) return;
    try {
      const data = await apiCall('expand_node', { full_name: nodeData.full_name });
      const newElements = neighborhoodToElements(data);

      // Merge: deduplicate by id (per D-11)
      const existingNodeIds = new Set(accumulatedGraphElements.nodes.map(n => n.id));
      const existingLinkIds = new Set(accumulatedGraphElements.links.map(l => l.id));

      const mergedNodes = [
        ...accumulatedGraphElements.nodes,
        ...newElements.nodes.filter(n => !existingNodeIds.has(n.id)),
      ];
      const mergedLinks = [
        ...accumulatedGraphElements.links,
        ...newElements.links.filter(l => !existingLinkIds.has(l.id)),
      ];

      accumulatedGraphElements = { nodes: mergedNodes, links: mergedLinks };
    } catch (err) {
      console.warn('Failed to expand node:', err.message);
    }
  }

  // Right-click: remove node + orphan cascade (per D-12, D-13)
  function handleNodeRemove(nodeId) {
    const removed = removeNodeWithOrphans(
      nodeId,
      accumulatedGraphElements.nodes,
      accumulatedGraphElements.links
    );
    accumulatedGraphElements = removed;
    // Close detail panel if the removed node was selected
    if (selectedNode?.id === nodeId) selectedNode = null;
  }

  // Detail panel action: navigate to tool with symbol prefilled (per D-15)
  function handleDetailAction(actionId, symbolData) {
    selectedNode = null;  // close panel
    onDetailAction?.(actionId, symbolData);
  }

  // Derive table columns from first row of result data
  function deriveColumns(data) {
    if (!data || !Array.isArray(data) || data.length === 0) return [];
    const row = data[0];
    if (typeof row !== 'object' || row === null) return [];
    const keys = Object.keys(row);
    const hasLocation = keys.includes('file_path') && keys.includes('line');
    const filtered = keys
      .filter(key => hasLocation ? (key !== 'file_path' && key !== 'line') : true)
      .map(key => ({ key, label: key.replace(/_/g, ' ') }));
    if (hasLocation) {
      filtered.push({ key: 'location', label: 'Location', synthetic: true });
    }
    return filtered;
  }

  // Extract table rows from various result shapes
  function extractRows(data, type) {
    if (Array.isArray(data)) return data;
    // Dead code/untested: { methods: [...], stats: {...} }
    if (data?.methods) return data.methods;
    // Search results with truncation: { results: [...], _truncated: true }
    if (data?.results) return data.results;
    return [];
  }

  const tableRows = $derived(result ? extractRows(result, resultType) : []);
  const tableColumns = $derived(deriveColumns(tableRows));
</script>

<div class="result-panel">
  {#if loading}
    <div class="loading-state">
      <p>Loading...</p>
    </div>
  {:else if error}
    <div class="error-state">
      <h3 class="heading">Something went wrong.</h3>
      <p class="text-secondary">{error}. Check that <code>synapps serve</code> is running and the project is indexed.</p>
    </div>
  {:else if result === null}
    <div class="empty-state">
      <p class="heading">Nothing to show yet.</p>
      <p class="text-secondary">Run a query to see results.</p>
    </div>
  {:else if resultType === 'table'}
    {#if result?.stats}
      <div class="stats-bar">
        {#each Object.entries(result.stats) as [key, value]}
          <span class="stat-item"><span class="label">{key.replace(/_/g, ' ')}:</span> {value}</span>
        {/each}
      </div>
    {/if}
    <DataTable columns={tableColumns} rows={tableRows} {onSymbolClick} {projectRoot} />
  {:else if resultType === 'text'}
    <pre class="text-result">{typeof result === 'string' ? result : JSON.stringify(result, null, 2)}</pre>
  {:else if resultType === 'mixed'}
    <!-- Architecture overview: stats + sections -->
    {#if result.stats}
      <div class="stats-grid">
        {#each Object.entries(result.stats) as [key, value]}
          <div class="stat-card">
            <div class="stat-value heading">{typeof value === 'object' ? JSON.stringify(value) : value}</div>
            <div class="stat-label label text-secondary">{key.replace(/_/g, ' ')}</div>
          </div>
        {/each}
      </div>
    {/if}
    {#if result.hotspots}
      <h3 class="heading" style="margin-top: 24px;">Hotspots</h3>
      <DataTable
        columns={deriveColumns(result.hotspots)}
        rows={result.hotspots}
        {onSymbolClick}
        {projectRoot}
      />
    {/if}
    {#if result.packages}
      <h3 class="heading" style="margin-top: 24px;">Packages</h3>
      <DataTable
        columns={deriveColumns(result.packages)}
        rows={result.packages}
        {onSymbolClick}
        {projectRoot}
      />
    {/if}
    {#if result.http_service_map}
      <h3 class="heading" style="margin-top: 24px;">HTTP Service Map</h3>
      <DataTable
        columns={deriveColumns(result.http_service_map)}
        rows={result.http_service_map}
        {onSymbolClick}
        {projectRoot}
      />
    {/if}
  {:else if resultType === 'graph'}
    {#if accumulatedGraphElements.nodes.length === 0}
      <div class="empty-state">
        <p class="heading">Nothing to show yet.</p>
        <p class="text-secondary">Run a query to build the graph.</p>
      </div>
    {:else}
      <div class="graph-wrapper">
        <D3Graph
          elements={accumulatedGraphElements}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
          onNodeRemove={handleNodeRemove}
        />
        {#if selectedNode}
          <NodeDetailPanel
            node={selectedNode}
            onClose={() => selectedNode = null}
            onAction={handleDetailAction}
          />
        {/if}
      </div>
    {/if}
  {:else if resultType === 'raw'}
    {#if isGraphResult(result)}
      <div class="graph-wrapper">
        <D3Graph
          elements={cypherToElements(result)}
          onNodeSelect={handleNodeSelect}
          onNodeExpand={handleNodeExpand}
          onNodeRemove={handleNodeRemove}
        />
        {#if selectedNode}
          <NodeDetailPanel
            node={selectedNode}
            onClose={() => selectedNode = null}
            onAction={handleDetailAction}
          />
        {/if}
      </div>
      <details style="margin-top: 16px;">
        <summary class="text-secondary">Raw JSON</summary>
        <pre class="text-result">{JSON.stringify(result, null, 2)}</pre>
      </details>
    {:else}
      <pre class="text-result">{JSON.stringify(result, null, 2)}</pre>
    {/if}
  {/if}
</div>

<style>
  .result-panel {
    margin-top: 16px;
  }
  .loading-state, .empty-state, .error-state {
    text-align: center;
    padding: 48px 16px;
  }
  .error-state {
    color: var(--color-destructive);
  }
  .error-state .text-secondary {
    color: var(--color-text-secondary);
    margin-top: 8px;
  }
  .error-state code {
    background: var(--color-secondary);
    padding: 2px 6px;
    border-radius: 3px;
  }
  .text-result {
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 16px;
    overflow-x: auto;
    font-size: 14px;
    line-height: 1.6;
    font-family: monospace;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .stats-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
    padding: 12px 16px;
    background: var(--color-secondary);
    border-radius: 4px;
    margin-bottom: 16px;
  }
  .stat-item .label {
    color: var(--color-text-secondary);
    margin-right: 4px;
  }
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }
  .stat-card {
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 16px;
    text-align: center;
  }
  .stat-label {
    margin-top: 4px;
  }
  .graph-wrapper {
    position: relative;
  }
</style>
