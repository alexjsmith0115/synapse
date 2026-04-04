<script>
  import Header from './lib/ui/Header.svelte';
  import ToolSidebar from './lib/tools/ToolSidebar.svelte';
  import { initTheme } from './lib/stores/theme.js';
  import { onMount } from 'svelte';

  let activeTool = $state('');

  onMount(() => {
    initTheme();
  });

  function handleSelectTool(toolId) {
    activeTool = toolId;
  }
</script>

<div class="unsupported-banner">
  Synapps web UI is designed for desktop use (1024px+).
</div>

<div class="app-shell">
  <Header />
  <div class="body">
    <ToolSidebar {activeTool} onSelectTool={handleSelectTool} />
    <main class="content">
      {#if !activeTool}
        <div class="welcome">
          <h1 class="heading">Synapps Code Intelligence</h1>
          <p class="text-secondary">Select a tool from the sidebar to explore your codebase.</p>
        </div>
      {:else}
        <div class="tool-content">
          <!-- Plan 04 will add ToolForm + ResultPanel here -->
          <p>Tool: {activeTool}</p>
        </div>
      {/if}
    </main>
  </div>
</div>

<style>
  .app-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  .body {
    display: flex;
    flex: 1;
    overflow: hidden;
  }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 32px;
  }
  .welcome {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    gap: 16px;
  }
  .tool-content {
    max-width: 1200px;
  }

  @media (min-width: 768px) and (max-width: 1023px) {
    .app-shell :global(.sidebar) {
      width: 48px;
      min-width: 48px;
    }
    .app-shell :global(.sidebar .category-label),
    .app-shell :global(.sidebar .tool-item) {
      font-size: 0;
      padding: 8px 12px;
    }
  }
</style>
