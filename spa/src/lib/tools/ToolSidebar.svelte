<script>
  const { activeTool = $bindable(''), onSelectTool } = $props();

  const categories = [
    {
      name: 'Search',
      tools: [
        { id: 'search_symbols', label: 'Search Symbols' },
      ],
    },
    {
      name: 'Navigate',
      tools: [
        { id: 'find_usages', label: 'Find Usages' },
        { id: 'find_callees', label: 'Find Callees' },
        { id: 'get_hierarchy', label: 'Get Hierarchy' },
      ],
    },
    {
      name: 'Analysis',
      tools: [
        { id: 'get_architecture', label: 'Architecture' },
        { id: 'find_dead_code', label: 'Dead Code' },
        { id: 'find_untested', label: 'Untested Methods' },
      ],
    },
    {
      name: 'Query',
      tools: [
        { id: 'execute_query', label: 'Cypher Query' },
        { id: 'find_http_endpoints', label: 'HTTP Endpoints' },
      ],
    },
  ];

  function select(toolId) {
    onSelectTool?.(toolId);
  }
</script>

<nav class="sidebar">
  {#each categories as category}
    <div class="category">
      <h3 class="category-label label">{category.name}</h3>
      {#each category.tools as tool}
        <button
          class="tool-item"
          class:active={activeTool === tool.id}
          onclick={() => select(tool.id)}
        >
          {tool.label}
        </button>
      {/each}
    </div>
  {/each}
</nav>

<style>
  .sidebar {
    width: 240px;
    min-width: 240px;
    background: var(--color-secondary);
    border-right: 1px solid var(--color-border);
    padding: 24px 0;
    overflow-y: auto;
    height: 100%;
  }
  .category {
    margin-bottom: 24px;
  }
  .category-label {
    padding: 0 24px;
    margin-bottom: 8px;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .tool-item {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 24px;
    font-size: 14px;
    font-weight: 400;
    color: var(--color-text-primary);
    cursor: pointer;
  }
  .tool-item:hover {
    background: var(--color-secondary);
    /* On hover, slightly different shade via mixing — fallback to same */
    background: color-mix(in srgb, var(--color-dominant) 50%, var(--color-secondary));
  }
  .tool-item.active {
    border-left-color: var(--color-accent);
    background: var(--color-dominant);
    font-weight: 600;
  }
</style>
