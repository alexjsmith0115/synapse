<script>
  import { Info, Search, GitFork, Network, X } from 'lucide-svelte';

  const { node = null, onClose, onAction } = $props();

  const SKIP_KEYS = new Set(['id', 'label', 'full_name', 'kind', 'file_path', 'line', 'signature', 'x', 'y', 'vx', 'vy', 'fx', 'fy', 'index']);

  const remainingProps = $derived(
    node ? Object.entries(node).filter(([k, v]) => !SKIP_KEYS.has(k) && v !== undefined && v !== null && v !== '').sort(([a], [b]) => a.localeCompare(b)) : []
  );

  const showHierarchy = $derived(
    node?.kind === 'Class' || node?.kind === 'Interface'
  );

  function formatKey(key) {
    return key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  }

  function formatValue(value) {
    if (Array.isArray(value)) return value.join(', ');
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }
</script>

{#if node}
  <div class="detail-panel">
    <div class="panel-header">
      <div class="header-title">
        <h3>{node.label || node.name || node.full_name}</h3>
        {#if node.kind}
          <span class="kind-badge kind-{node.kind?.toLowerCase()}">{node.kind}</span>
        {/if}
      </div>
      <button class="close-btn" onclick={() => onClose?.()} aria-label="Close panel">
        <X size={16} />
      </button>
    </div>

    <dl class="properties">
      {#if node.full_name}
        <dt>Full Name</dt>
        <dd class="monospace">{node.full_name}</dd>
      {/if}

      {#if node.kind}
        <dt>Kind</dt>
        <dd>{node.kind}</dd>
      {/if}

      {#if node.file_path}
        <dt>Location</dt>
        <dd>
          <a href="vscode://file/{node.file_path}:{node.line || 1}:1" class="vscode-link">
            {node.file_path}{node.line ? `:${node.line}` : ''}
          </a>
        </dd>
      {/if}

      {#if node.signature}
        <dt>Signature</dt>
        <dd class="monospace">{node.signature}</dd>
      {/if}

      {#each remainingProps as [key, value]}
        <dt>{formatKey(key)}</dt>
        <dd>{formatValue(value)}</dd>
      {/each}
    </dl>

    <div class="actions">
      <h4 class="actions-heading">Actions</h4>
      <button class="action-btn" onclick={() => onAction?.('get_context_for', node)}>
        <Info size={14} /> Get Context
      </button>
      <button class="action-btn" onclick={() => onAction?.('find_usages', node)}>
        <Search size={14} /> Find Usages
      </button>
      <button class="action-btn" onclick={() => onAction?.('find_callees', node)}>
        <GitFork size={14} /> Find Callees
      </button>
      {#if showHierarchy}
        <button class="action-btn" onclick={() => onAction?.('get_hierarchy', node)}>
          <Network size={14} /> Get Hierarchy
        </button>
      {/if}
    </div>
  </div>
{/if}

<style>
  .detail-panel {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    width: 300px;
    background: var(--color-secondary);
    border-left: 1px solid var(--color-border);
    box-shadow: -4px 0 12px rgba(0, 0, 0, 0.08);
    z-index: 20;
    overflow-y: auto;
    padding: 16px;
    font-size: 13px;
  }

  :global([data-theme="dark"]) .detail-panel {
    box-shadow: -4px 0 12px rgba(0, 0, 0, 0.3);
  }

  .panel-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 16px;
    gap: 8px;
  }

  .header-title {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    flex: 1;
  }

  .panel-header h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    word-break: break-all;
  }

  .kind-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    background: rgba(45, 106, 79, 0.12);
    color: var(--color-accent);
    align-self: flex-start;
  }

  :global([data-theme="dark"]) .kind-badge {
    background: rgba(116, 198, 157, 0.12);
  }

  .close-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--color-text-secondary);
    padding: 4px;
    border-radius: 4px;
    flex-shrink: 0;
  }

  .close-btn:hover {
    background: rgba(45, 106, 79, 0.08);
    color: var(--color-accent);
  }

  :global([data-theme="dark"]) .close-btn:hover {
    background: rgba(116, 198, 157, 0.08);
  }

  .properties {
    margin: 0;
  }

  .properties dt {
    font-size: 11px;
    font-weight: 600;
    color: var(--color-text-secondary);
    margin-top: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .properties dd {
    margin: 2px 0 0 0;
    word-break: break-all;
  }

  .monospace {
    font-family: monospace;
    font-size: 12px;
  }

  .vscode-link {
    color: var(--color-accent);
    text-decoration: none;
    font-family: monospace;
    font-size: 12px;
  }

  .vscode-link:hover {
    text-decoration: underline;
  }

  .actions {
    margin-top: 20px;
    padding-top: 16px;
    border-top: 1px solid var(--color-border);
  }

  .actions-heading {
    font-size: 11px;
    font-weight: 600;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 8px 0;
  }

  .action-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 12px;
    border: none;
    background: none;
    font-size: 13px;
    color: var(--color-text-primary);
    cursor: pointer;
    border-radius: 4px;
    font-family: inherit;
    text-align: left;
  }

  .action-btn:hover {
    background: rgba(45, 106, 79, 0.08);
    color: var(--color-accent);
  }

  :global([data-theme="dark"]) .action-btn:hover {
    background: rgba(116, 198, 157, 0.08);
  }

  .action-btn :global(svg) {
    color: var(--color-text-secondary);
    flex-shrink: 0;
  }

  .action-btn:hover :global(svg) {
    color: var(--color-accent);
  }
</style>
