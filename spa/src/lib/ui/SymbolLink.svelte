<script>
  import { ExternalLink } from 'lucide-svelte';

  const { name, fullName = '', filePath = '', line = 0, onNavigate } = $props();

  function handleClick() {
    onNavigate?.(fullName || name);
  }

  function vscodeUrl() {
    if (!filePath || !line) return null;
    return `vscode://file/${filePath}:${line}:1`;
  }

  const editorUrl = $derived(vscodeUrl());
</script>

<span class="symbol-link">
  <button class="symbol-name" onclick={handleClick} title={fullName || name}>
    {name}
  </button>
  {#if editorUrl}
    <a href={editorUrl} class="editor-link" title="Open in editor" target="_blank" rel="noopener">
      <ExternalLink size={14} />
    </a>
  {/if}
</span>

<style>
  .symbol-link {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .symbol-name {
    background: none;
    border: none;
    color: var(--color-accent);
    cursor: pointer;
    font-size: inherit;
    font-family: inherit;
    padding: 0;
    text-decoration: none;
  }
  .symbol-name:hover {
    text-decoration: underline;
  }
  .editor-link {
    color: var(--color-text-secondary);
    display: inline-flex;
    align-items: center;
    min-width: 20px;
    min-height: 20px;
    justify-content: center;
  }
  .editor-link:hover {
    color: var(--color-accent);
  }
</style>
