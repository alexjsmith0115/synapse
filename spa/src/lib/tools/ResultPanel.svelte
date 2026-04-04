<script>
  import DataTable from '../ui/DataTable.svelte';

  const { result = null, resultType = 'table', error = null, loading = false, onSymbolClick } = $props();

  // Derive table columns from first row of result data
  function deriveColumns(data) {
    if (!data || !Array.isArray(data) || data.length === 0) return [];
    const row = data[0];
    if (typeof row !== 'object' || row === null) return [];
    return Object.keys(row).map(key => ({ key, label: key.replace(/_/g, ' ') }));
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
    <DataTable columns={tableColumns} rows={tableRows} {onSymbolClick} />
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
      />
    {/if}
    {#if result.packages}
      <h3 class="heading" style="margin-top: 24px;">Packages</h3>
      <DataTable
        columns={deriveColumns(result.packages)}
        rows={result.packages}
        {onSymbolClick}
      />
    {/if}
    {#if result.http_service_map}
      <h3 class="heading" style="margin-top: 24px;">HTTP Service Map</h3>
      <DataTable
        columns={deriveColumns(result.http_service_map)}
        rows={result.http_service_map}
        {onSymbolClick}
      />
    {/if}
  {:else if resultType === 'graph'}
    <!-- Graph rendering handled by Plan 05; show raw data as fallback -->
    <div class="graph-placeholder">
      <p class="text-secondary">Graph visualization loading...</p>
      <pre class="text-result">{JSON.stringify(result, null, 2)}</pre>
    </div>
  {:else if resultType === 'raw'}
    <pre class="text-result">{JSON.stringify(result, null, 2)}</pre>
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
  .graph-placeholder {
    padding: 16px;
  }
</style>
