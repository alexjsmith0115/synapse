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
      const queriedKind = result?.queried_kind;
      const calleeData = result?.callees || result;
      initial = calleesToElements(calleeData, rootName, queriedKind);
    } else if (activeTool === 'get_hierarchy') {
      initial = hierarchyToElements({ ...result, target: result.target || queryParams?.full_name || '' });
    } else if (activeTool === 'find_usages') {
      const queriedKind = result?.queried_kind;
      const usageData = result?.usages || result;
      initial = usagesToElements(usageData, queryParams?.full_name || '', queriedKind);
    } else {
      initial = { nodes: [], links: [] };
    }
    // Ensure all initial nodes start at depth 0
    accumulatedGraphElements = {
      nodes: initial.nodes.map(n => (n.depth == null ? { ...n, depth: 0 } : n)),
      links: initial.links,
    };
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
      const maxDepth = accumulatedGraphElements.nodes.reduce((m, n) => Math.max(m, n.depth ?? 0), 0);
      const newElements = neighborhoodToElements(data, maxDepth + 1);

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
  {:else if resultType === 'context'}
    <!-- Impact scope: stats grid + DataTable sections -->
    {#if result.total_affected != null}
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value heading">{result.total_affected}</div>
          <div class="stat-label label text-secondary">total affected</div>
        </div>
        <div class="stat-card">
          <div class="stat-value heading">{(result.direct_callers || []).length}</div>
          <div class="stat-label label text-secondary">direct callers</div>
        </div>
        <div class="stat-card">
          <div class="stat-value heading">{(result.transitive_callers || []).length}</div>
          <div class="stat-label label text-secondary">transitive callers</div>
        </div>
        <div class="stat-card">
          <div class="stat-value heading">{(result.test_coverage || []).length}</div>
          <div class="stat-label label text-secondary">test coverage</div>
        </div>
        <div class="stat-card">
          <div class="stat-value heading">{(result.direct_callees || []).length}</div>
          <div class="stat-label label text-secondary">direct callees</div>
        </div>
      </div>
    {/if}

    <!-- Source code -->
    {#if result.source}
      <pre class="text-result">{result.source}</pre>
    {/if}

    <!-- Constructor -->
    {#if result.constructor_source}
      <h3 class="heading" style="margin-top: 24px;">Constructor</h3>
      <pre class="text-result">{result.constructor_source}</pre>
    {/if}

    <!-- Interface contract -->
    {#if result.interface_contract && result.interface_contract.interface}
      <div class="info-card" style="margin-top: 16px;">
        <span class="text-secondary">Interface:</span> <strong>{result.interface_contract.interface}</strong>
        &nbsp;&middot;&nbsp;
        <span class="text-secondary">Contract method:</span> <strong>{result.interface_contract.contract_method}</strong>
        {#if result.interface_contract.sibling_implementations && result.interface_contract.sibling_implementations.length > 0}
          &nbsp;&middot;&nbsp;
          <span class="text-secondary">Other implementations:</span>
          {result.interface_contract.sibling_implementations.map(s => s.class_name || s.full_name).join(', ')}
        {/if}
      </div>
    {/if}

    <!-- HTTP endpoint -->
    {#if result.endpoint}
      <h3 class="heading" style="margin-top: 24px;">HTTP Endpoint</h3>
      <div class="info-card">
        <code>{result.endpoint.http_method} {result.endpoint.route}</code>
      </div>
      {#if result.endpoint.client_callers && result.endpoint.client_callers.length > 0}
        <DataTable columns={deriveColumns(result.endpoint.client_callers)} rows={result.endpoint.client_callers} {onSymbolClick} {projectRoot} />
      {/if}
    {/if}

    <!-- Containing type -->
    {#if result.containing_type}
      <h3 class="heading" style="margin-top: 24px;">{result.containing_type.name}</h3>
      {#if result.containing_type.members && result.containing_type.members.length > 0}
        <DataTable columns={deriveColumns(result.containing_type.members)} rows={result.containing_type.members} {onSymbolClick} {projectRoot} />
      {/if}
    {/if}

    <!-- DataTable sections for each array field -->
    {#if result.members && result.members.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Members</h3>
      <DataTable columns={deriveColumns(result.members)} rows={result.members} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.interfaces && result.interfaces.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Interfaces</h3>
      <DataTable columns={deriveColumns(result.interfaces)} rows={result.interfaces} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.callers && result.callers.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Direct Callers</h3>
      <DataTable columns={deriveColumns(result.callers)} rows={result.callers} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.direct_callers && result.direct_callers.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Direct Callers</h3>
      <DataTable columns={deriveColumns(result.direct_callers)} rows={result.direct_callers} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.transitive_callers && result.transitive_callers.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Transitive Callers</h3>
      <DataTable columns={deriveColumns(result.transitive_callers)} rows={result.transitive_callers} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.test_coverage && result.test_coverage.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Test Coverage</h3>
      <DataTable columns={deriveColumns(result.test_coverage)} rows={result.test_coverage} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.direct_callees && result.direct_callees.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Direct Callees</h3>
      <DataTable columns={deriveColumns(result.direct_callees)} rows={result.direct_callees} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.callees && result.callees.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Called Methods</h3>
      <DataTable columns={deriveColumns(result.callees)} rows={result.callees} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.dependencies && result.dependencies.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Dependencies</h3>
      <DataTable columns={deriveColumns(result.dependencies)} rows={result.dependencies} {onSymbolClick} {projectRoot} />
    {/if}
    {#if result.tests && result.tests.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Test Coverage</h3>
      <DataTable columns={deriveColumns(result.tests)} rows={result.tests} {onSymbolClick} {projectRoot} />
    {/if}

    <!-- Summaries -->
    {#if result.summaries && result.summaries.length > 0}
      <h3 class="heading" style="margin-top: 24px;">Summaries</h3>
      <ul class="summaries-list">
        {#each result.summaries as s}
          <li><strong>{s.full_name}</strong> — {s.summary}</li>
        {/each}
      </ul>
    {/if}
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
  .info-card {
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 10px 14px;
    margin-bottom: 8px;
    font-size: 14px;
  }
  .summaries-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .summaries-list li {
    padding: 6px 0;
    border-bottom: 1px solid var(--color-border);
    font-size: 14px;
  }
  .summaries-list li:last-child {
    border-bottom: none;
  }
</style>
