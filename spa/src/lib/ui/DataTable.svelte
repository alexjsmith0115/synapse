<script>
  const { columns = [], rows = [], onSymbolClick } = $props();
  import SymbolLink from './SymbolLink.svelte';

  function isSymbolColumn(col) {
    return col.key === 'full_name' || col.key === 'name';
  }
</script>

{#if rows.length === 0}
  <div class="empty-state">
    <p class="heading">No results found.</p>
    <p class="text-secondary">Try a different query or check that the project is indexed.</p>
  </div>
{:else}
  <div class="table-wrapper">
    <table>
      <thead>
        <tr>
          {#each columns as col}
            <th class="label">{col.label}</th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as row}
          <tr>
            {#each columns as col}
              <td>
                {#if isSymbolColumn(col)}
                  <SymbolLink
                    name={row[col.key] || ''}
                    fullName={row.full_name || row[col.key] || ''}
                    filePath={row.file_path || ''}
                    line={row.line || 0}
                    onNavigate={onSymbolClick}
                  />
                {:else}
                  {row[col.key] ?? ''}
                {/if}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .table-wrapper {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th {
    text-align: left;
    padding: 8px 16px;
    border-bottom: 2px solid var(--color-border);
    white-space: nowrap;
  }
  td {
    padding: 8px 16px;
    border-bottom: 1px solid var(--color-border);
    vertical-align: top;
  }
  tr:nth-child(even) {
    background: var(--color-secondary);
  }
  .empty-state {
    text-align: center;
    padding: 48px 16px;
  }
  .empty-state .heading {
    margin-bottom: 8px;
  }
</style>
