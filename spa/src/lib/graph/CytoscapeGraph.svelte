<script>
  import { onMount, onDestroy } from 'svelte';
  import cytoscape from 'cytoscape';
  import dagre from 'cytoscape-dagre';
  import coseBilkent from 'cytoscape-cose-bilkent';
  import { buildStyles } from './nodeStyles.js';
  import { getLayout } from './layouts.js';

  // Register layout extensions once
  cytoscape.use(dagre);
  cytoscape.use(coseBilkent);

  const {
    elements = { nodes: [], edges: [] },
    viewType = 'callees',
    onNodeClick,
    onNodeDoubleClick,
  } = $props();

  let container;
  let cy;
  let tooltipContent = $state('');
  let tooltipStyle = $state('display: none;');

  onMount(() => {
    cy = cytoscape({
      container,
      elements: [...(elements.nodes || []), ...(elements.edges || [])],
      style: buildStyles(),
      layout: getLayout(viewType),
      userZoomingEnabled: true,
      userPanningEnabled: true,
      boxSelectionEnabled: false,
      minZoom: 0.2,
      maxZoom: 5,
    });

    // Click node — expand (per D-06: click to show callers/callees)
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      const data = node.data();
      onNodeClick?.(data);
    });

    // Double-click node — open in editor (per UI-SPEC)
    cy.on('dbltap', 'node', (evt) => {
      const data = evt.target.data();
      if (data.file_path && data.line) {
        const url = `vscode://file/${data.file_path}:${data.line}:1`;
        window.open(url, '_blank');
      }
      onNodeDoubleClick?.(data);
    });

    // Hover node — show tooltip (per D-06)
    cy.on('mouseover', 'node', (evt) => {
      const node = evt.target;
      const data = node.data();
      const pos = evt.renderedPosition || node.renderedPosition();
      tooltipContent = [
        data.full_name || data.label,
        data.kind ? `Kind: ${data.kind}` : '',
        data.file_path ? `File: ${data.file_path}` : '',
        data.line ? `Line: ${data.line}` : '',
      ].filter(Boolean).join('\n');
      tooltipStyle = `display: block; left: ${pos.x + 15}px; top: ${pos.y + 15}px;`;
    });

    cy.on('mouseout', 'node', () => {
      tooltipStyle = 'display: none;';
    });

    // Click empty canvas — deselect all
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        cy.elements().unselect();
      }
    });

    // Right-click node — context menu
    cy.on('cxttap', 'node', (evt) => {
      const data = evt.target.data();
      // Simple context menu via onNodeClick for now
      // Full context menu is a stretch goal
      onNodeClick?.(data);
    });
  });

  // React to elements changes — update graph without recreating
  $effect(() => {
    if (cy && elements) {
      const allElements = [...(elements.nodes || []), ...(elements.edges || [])];
      if (allElements.length > 0) {
        cy.elements().remove();
        cy.add(allElements);
        cy.layout(getLayout(viewType)).run();
        cy.fit(undefined, 50); // fit with 50px padding
      }
    }
  });

  onDestroy(() => {
    cy?.destroy();
  });

  // Re-apply styles on theme change (observe data-theme attribute)
  $effect(() => {
    if (cy) {
      const observer = new MutationObserver(() => {
        cy.style().fromJson(buildStyles()).update();
      });
      observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme'],
      });
      return () => observer.disconnect();
    }
  });
</script>

<div class="graph-container">
  <div class="cytoscape-canvas" bind:this={container}></div>
  <div class="graph-tooltip" style={tooltipStyle}>
    {#each tooltipContent.split('\n') as line}
      <div>{line}</div>
    {/each}
  </div>
</div>

<style>
  .graph-container {
    position: relative;
    width: 100%;
    height: calc(100vh - 200px);
    min-height: 400px;
    border: 1px solid var(--color-border);
    border-radius: 4px;
    overflow: hidden;
    background: var(--color-dominant);
  }
  .cytoscape-canvas {
    width: 100%;
    height: 100%;
  }
  .graph-tooltip {
    position: absolute;
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--color-text-primary);
    pointer-events: none;
    z-index: 10;
    max-width: 400px;
    white-space: nowrap;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
</style>
