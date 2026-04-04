<script>
  import { onMount, onDestroy } from 'svelte';
  import { Info, Search, GitFork, Network, ExternalLink } from 'lucide-svelte';

  const { x = 0, y = 0, symbolData = null, onAction, onClose } = $props();

  function handleWindowClick() {
    onClose?.();
  }

  function handleKeydown(event) {
    if (event.key === 'Escape') onClose?.();
  }

  onMount(() => {
    // Delay to avoid the same click that opened the menu from closing it
    const timer = setTimeout(() => {
      window.addEventListener('click', handleWindowClick);
      window.addEventListener('keydown', handleKeydown);
    }, 0);
    return () => clearTimeout(timer);
  });

  onDestroy(() => {
    window.removeEventListener('click', handleWindowClick);
    window.removeEventListener('keydown', handleKeydown);
  });

  function vscodeUrl() {
    if (!symbolData?.file_path || !symbolData?.line) return null;
    return `vscode://file/${symbolData.file_path}:${symbolData.line}:1`;
  }

  const showHierarchy = $derived(
    symbolData?.kind === 'Class' || symbolData?.kind === 'Interface'
  );
  const editorUrl = $derived(vscodeUrl());

  const clampedX = $derived(Math.min(x, (typeof window !== 'undefined' ? window.innerWidth : 1000) - 200));
  const clampedY = $derived(Math.min(y, (typeof window !== 'undefined' ? window.innerHeight : 800) - 200));
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  class="context-menu"
  style="left: {clampedX}px; top: {clampedY}px;"
  onclick={(e) => e.stopPropagation()}
  role="menu"
>
  <button class="menu-item" onclick={() => onAction?.('get_context_for', symbolData)} role="menuitem">
    <Info size={14} />
    Get Context
  </button>
  <button class="menu-item" onclick={() => onAction?.('find_usages', symbolData)} role="menuitem">
    <Search size={14} />
    Find Usages
  </button>
  <button class="menu-item" onclick={() => onAction?.('find_callees', symbolData)} role="menuitem">
    <GitFork size={14} />
    Find Callees
  </button>
  {#if showHierarchy}
    <button class="menu-item" onclick={() => onAction?.('get_hierarchy', symbolData)} role="menuitem">
      <Network size={14} />
      Get Hierarchy
    </button>
  {/if}
  {#if editorUrl}
    <div class="menu-separator"></div>
    <a href={editorUrl} class="menu-item" role="menuitem" onclick={() => onClose?.()}>
      <ExternalLink size={14} />
      Open in Editor
    </a>
  {/if}
</div>

<style>
  .context-menu {
    position: fixed;
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
    z-index: 1000;
    min-width: 160px;
    padding: 4px 0;
  }
  :global([data-theme="dark"]) .context-menu {
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }
  .menu-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 8px 16px;
    min-height: 36px;
    border: none;
    background: none;
    font-size: 14px;
    font-weight: 400;
    color: var(--color-text-primary);
    cursor: pointer;
    text-decoration: none;
    font-family: inherit;
    text-align: left;
  }
  .menu-item :global(svg) {
    color: var(--color-text-secondary);
    flex-shrink: 0;
  }
  .menu-item:hover {
    background: rgba(45, 106, 79, 0.08);
    color: var(--color-accent);
  }
  :global([data-theme="dark"]) .menu-item:hover {
    background: rgba(116, 198, 157, 0.08);
  }
  .menu-item:hover :global(svg) {
    color: var(--color-accent);
  }
  .menu-separator {
    height: 1px;
    background: var(--color-border);
    margin: 4px 0;
  }
</style>
