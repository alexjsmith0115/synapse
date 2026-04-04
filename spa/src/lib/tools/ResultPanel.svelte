<script>
  import DataTable from '../ui/DataTable.svelte';
  import CytoscapeGraph from '../graph/CytoscapeGraph.svelte';
  import { calleesToElements, hierarchyToElements, usagesToElements, cypherToElements, isGraphResult } from '../graph/transforms.js';
  import { apiCall } from '../api.js';

  const { result = null, resultType = 'table', queryParams = {}, error = null, loading = false, onSymbolClick, activeTool = '', projectRoot = '' } = $props();

  // Accumulated graph elements — persists across node expansions.
  // Reset when a new top-level query result arrives (via $effect on result).
  let accumulatedGraphElements = $state({ nodes: [], edges: [] });

  // When a new result arrives, compute the initial graph elements and reset accumulator
  $effect(() => {
    if (!result || resultType !== 'graph') {
      accumulatedGraphElements = { nodes: [], edges: [] };
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
      initial = { nodes: [], edges: [] };
    }
    accumulatedGraphElements = initial;
  });

  const viewType = $derived(
    activeTool === 'find_callees' ? 'callees' :
    activeTool === 'get_hierarchy' ? 'hierarchy' :
    activeTool === 'find_usages' ? 'usages' :
    'cypher'
  );

  // Handle node click — expand callees and MERGE new elements into accumulated state
  async function handleNodeClick(nodeData) {
    if (activeTool === 'find_callees' && nodeData.full_name) {
      try {
        const callees = await apiCall('find_callees', { full_name: nodeData.full_name, limit: 20 });
        const newElements = calleesToElements(callees, nodeData.full_name);

        // Merge new nodes and edges into accumulated state (deduplicate by id)
        const existingNodeIds = new Set(accumulatedGraphElements.nodes.map(n => n.data.id));
        const existingEdgeIds = new Set(accumulatedGraphElements.edges.map(e => e.data.id));

        const mergedNodes = [
          ...accumulatedGraphElements.nodes,
          ...newElements.nodes.filter(n => !existingNodeIds.has(n.data.id)),
        ];
        const mergedEdges = [
          ...accumulatedGraphElements.edges,
          ...newElements.edges.filter(e => !existingEdgeIds.has(e.data.id)),
        ];

        accumulatedGraphElements = { nodes: mergedNodes, edges: mergedEdges };
      } catch (err) {
        console.warn('Failed to expand node:', err.message);
      }
    } else if (activeTool === 'find_usages' && nodeData.full_name) {
      try {
        const usages = await apiCall('find_usages', { full_name: nodeData.full_name, limit: 20 });
        const newElements = usagesToElements(usages, nodeData.full_name);
        const existingNodeIds = new Set(accumulatedGraphElements.nodes.map(n => n.data.id));
        const existingEdgeIds = new Set(accumulatedGraphElements.edges.map(e => e.data.id));
        const mergedNodes = [
          ...accumulatedGraphElements.nodes,
          ...newElements.nodes.filter(n => !existingNodeIds.has(n.data.id)),
        ];
        const mergedEdges = [
          ...accumulatedGraphElements.edges,
          ...newElements.edges.filter(e => !existingEdgeIds.has(e.data.id)),
        ];
        accumulatedGraphElements = { nodes: mergedNodes, edges: mergedEdges };
      } catch (err) {
        console.warn('Failed to expand usages node:', err.message);
      }
    }
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
      <CytoscapeGraph
        elements={accumulatedGraphElements}
        {viewType}
        onNodeClick={handleNodeClick}
      />
    {/if}
  {:else if resultType === 'raw'}
    {#if isGraphResult(result)}
      <CytoscapeGraph
        elements={cypherToElements(result)}
        viewType="cypher"
        onNodeClick={handleNodeClick}
      />
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
    font-size: 13px;
    line-height: 1.5;
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
</style>
