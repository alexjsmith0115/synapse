<script>
  import Header from './lib/ui/Header.svelte';
  import ToolSidebar from './lib/tools/ToolSidebar.svelte';
  import ToolForm from './lib/tools/ToolForm.svelte';
  import ResultPanel from './lib/tools/ResultPanel.svelte';
  import { initTheme } from './lib/stores/theme.svelte.js';
  import { tools } from './lib/tools/toolConfig.js';
  import { apiCall } from './lib/api.js';
  import { onMount } from 'svelte';

  let activeTool = $state('');
  let result = $state(null);
  let resultType = $state('table');
  let queryParams = $state({});
  let error = $state(null);
  let loading = $state(false);
  let projectRoot = $state('');

  // Cache for autoRun tool results (e.g. get_architecture)
  let cachedResults = $state({});

  onMount(() => {
    initTheme();
    // Fetch project root for path relativization
    fetch('/api/config')
      .then(r => r.json())
      .then(data => { projectRoot = data.project_root || ''; })
      .catch(() => { /* ignore -- paths will show absolute */ });
  });

  function handleResult(data, type, params = {}) {
    result = data;
    resultType = type;
    queryParams = params;
    error = null;
  }

  function handleError(msg) {
    error = msg;
    result = null;
  }

  function handleLoading(isLoading) {
    loading = isLoading;
    if (isLoading) error = null;
  }

  function handleSymbolClick(symbolName) {
    // Navigate to search_symbols tool; pre-fill is a stretch goal
    activeTool = 'search_symbols';
    result = null;
    error = null;
    loading = false;
  }

  async function handleSelectTool(toolId) {
    activeTool = toolId;
    error = null;

    const config = tools[toolId];
    if (config?.autoRun) {
      // Use cached result if available
      if (cachedResults[toolId]) {
        result = cachedResults[toolId];
        resultType = config.resultType;
        queryParams = {};
        loading = false;
        return;
      }
      // Auto-fire the API call
      loading = true;
      result = null;
      try {
        const data = await apiCall(config.endpoint, {}, config.method);
        cachedResults[toolId] = data;
        result = data;
        resultType = config.resultType;
        queryParams = {};
      } catch (err) {
        error = err.message;
        result = null;
      } finally {
        loading = false;
      }
    } else {
      result = null;
      loading = false;
    }
  }

  function handleRefresh(toolId) {
    // Clear cache and re-fire for autoRun tools
    delete cachedResults[toolId];
    cachedResults = { ...cachedResults };
    handleSelectTool(toolId);
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
          <ToolForm
            toolId={activeTool}
            onResult={handleResult}
            onError={handleError}
            onLoading={handleLoading}
            onRefresh={handleRefresh}
          />
          <ResultPanel
            {result}
            {resultType}
            {queryParams}
            {error}
            {loading}
            onSymbolClick={handleSymbolClick}
            {activeTool}
            {projectRoot}
          />
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
