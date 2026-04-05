<script>
  import { onMount, onDestroy } from 'svelte';
  import * as d3 from 'd3';
  import { getNodeColor, getNodeTextColor, appendNodeShape, getCSSVar } from './nodeStyles.js';

  const {
    elements = { nodes: [], links: [] },
    onNodeSelect,
    onNodeExpand,
    onNodeRemove,
  } = $props();

  let svgEl;
  let simulation;
  let linkGroup;
  let nodeGroup;
  let zoomGroup;

  let tooltipContent = $state('');
  let tooltipStyle = $state('display: none;');
  let physicsEnabled = $state(false);

  let selectedNodeId = null;
  // Disambiguate single-click vs double-click
  let clickTimeout;

  function tick() {
    linkGroup.selectAll('line')
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    nodeGroup.selectAll('g.node')
      .attr('transform', d => `translate(${d.x},${d.y})`);
  }

  function highlightSelected() {
    nodeGroup.selectAll('g.node').classed('selected', d => d.id === selectedNodeId);
    nodeGroup.selectAll('g.node.selected').select('rect,ellipse,polygon')
      .attr('stroke-width', 4)
      .attr('stroke', getCSSVar('--color-accent') || '#2D6A4F');
    nodeGroup.selectAll('g.node:not(.selected)').select('rect,ellipse,polygon')
      .attr('stroke-width', 2)
      .attr('stroke', d => getNodeColor(d.kind));
  }

  function updateGraph(nodes, links) {
    // Links — enter/exit/update
    linkGroup.selectAll('line')
      .data(links, d => d.id)
      .join('line')
      .attr('stroke', getCSSVar('--color-border') || '#C3DDD0')
      .attr('stroke-width', 2)
      .attr('marker-end', 'url(#arrowhead)');

    // Nodes — enter/exit/update
    nodeGroup.selectAll('g.node')
      .data(nodes, d => d.id)
      .join(
        enter => {
          const g = enter.append('g').attr('class', 'node');

          // Per-node shape and color
          g.each(function(d) {
            const sel = d3.select(this);
            const opacity = Math.max(0.35, 1 - (d.depth || 0) * 0.25);
            appendNodeShape(sel, d.kind)
              .attr('fill', getNodeColor(d.kind))
              .attr('stroke', getNodeColor(d.kind))
              .attr('stroke-width', 2)
              .attr('opacity', opacity);

            sel.append('text')
              .text(d.label)
              .attr('font-size', '11px')
              .attr('text-anchor', 'middle')
              .attr('dy', '32')
              .attr('fill', getCSSVar('--color-text-primary') || '#1A2E23')
              .attr('opacity', opacity)
              .style('pointer-events', 'none')
              .style('user-select', 'none');
          });

          // Drag
          g.call(
            d3.drag()
              .on('start', (event, d) => {
                if (physicsEnabled) {
                  if (!event.active) simulation.alphaTarget(0.3).restart();
                }
                d.fx = d.x;
                d.fy = d.y;
              })
              .on('drag', (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
                if (!physicsEnabled) {
                  // Manual repositioning when physics is off
                  tick();
                }
              })
              .on('end', (event, d) => {
                if (physicsEnabled) {
                  if (!event.active) simulation.alphaTarget(0);
                  d.fx = null;
                  d.fy = null;
                } else {
                  // Commit dragged position and unpin
                  d.x = d.fx;
                  d.y = d.fy;
                  d.fx = null;
                  d.fy = null;
                  tick();
                }
              })
          );

          // Click / dblclick disambiguation
          g.on('click', (event, d) => {
            event.stopPropagation();
            clearTimeout(clickTimeout);
            clickTimeout = setTimeout(() => {
              selectedNodeId = d.id;
              highlightSelected();
              onNodeSelect?.(d);
            }, 250);
          });

          g.on('dblclick', (event, d) => {
            event.stopPropagation();
            event.preventDefault();
            clearTimeout(clickTimeout);
            onNodeExpand?.(d);
          });

          // Right-click remove
          g.on('contextmenu', (event, d) => {
            event.preventDefault();
            event.stopPropagation();
            onNodeRemove?.(d.id);
          });

          // Hover tooltip
          g.on('mouseover', (event, d) => {
            tooltipContent = [d.full_name || d.label, d.kind ? `Kind: ${d.kind}` : ''].filter(Boolean).join('\n');
            tooltipStyle = `display: block; left: ${event.offsetX + 15}px; top: ${event.offsetY + 15}px;`;
          });

          g.on('mouseout', () => {
            tooltipStyle = 'display: none;';
          });

          return g;
        },
        update => {
          update.select('rect,ellipse,polygon').attr('opacity', d => Math.max(0.35, 1 - (d.depth || 0) * 0.25));
          update.select('text').attr('opacity', d => Math.max(0.35, 1 - (d.depth || 0) * 0.25));
          return update;
        },
        exit => exit.remove()
      );
  }

  function togglePhysics() {
    physicsEnabled = !physicsEnabled;
    if (physicsEnabled) {
      simulation.alpha(0.3).restart();
    } else {
      simulation.stop();
    }
  }

  onMount(() => {
    const width = svgEl.clientWidth || 800;
    const height = svgEl.clientHeight || 600;

    const svg = d3.select(svgEl);

    // Arrow marker for directed edges
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 28)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', getCSSVar('--color-border') || '#C3DDD0');

    zoomGroup = svg.append('g');
    linkGroup = zoomGroup.append('g').attr('class', 'links');
    nodeGroup = zoomGroup.append('g').attr('class', 'nodes');

    simulation = d3.forceSimulation()
      .force('link', d3.forceLink().id(d => d.id).distance(100))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(45))
      .on('tick', tick);

    // Zoom / pan on canvas
    svg.call(
      d3.zoom()
        .scaleExtent([0.2, 5])
        .on('zoom', e => zoomGroup.attr('transform', e.transform))
    );

    // Click on empty canvas deselects
    svg.on('click', () => onNodeSelect?.(null));

    // Initial render — run synchronously for static layout, then freeze
    const nodes = elements.nodes.map(n => ({ ...n }));
    const links = elements.links.map(l => ({ ...l }));
    updateGraph(nodes, links);
    simulation.nodes(nodes);
    simulation.force('link').links(links);
    simulation.alpha(1.0).restart();
    simulation.tick(300);
    simulation.stop();
    tick();
  });

  // React to elements prop changes
  $effect(() => {
    if (!simulation || !elements) return;
    // Preserve existing node positions (RESEARCH Pitfall 1 — avoid proxy mutation)
    const nodes = elements.nodes.map(n => {
      const existing = simulation.nodes().find(e => e.id === n.id);
      return existing || { ...n };
    });
    const links = elements.links.map(l => ({ ...l }));
    updateGraph(nodes, links);
    simulation.nodes(nodes);
    simulation.force('link').links(links);
    if (physicsEnabled) {
      simulation.alpha(elements.nodes.length <= 10 ? 1.0 : 0.3).restart();
    } else {
      simulation.alpha(elements.nodes.length <= 10 ? 1.0 : 0.3);
      simulation.tick(300);
      simulation.stop();
      tick();
    }
  });

  // Re-apply colors when theme changes
  $effect(() => {
    if (!svgEl) return;
    const observer = new MutationObserver(() => {
      nodeGroup.selectAll('g.node').each(function(d) {
        d3.select(this).select('rect,ellipse,polygon')
          .attr('fill', getNodeColor(d.kind))
          .attr('stroke', d.id === selectedNodeId
            ? (getCSSVar('--color-accent') || '#2D6A4F')
            : getNodeColor(d.kind));
        d3.select(this).select('text').attr('fill', getCSSVar('--color-text-primary') || '#1A2E23');
      });
      linkGroup.selectAll('line').attr('stroke', getCSSVar('--color-border') || '#C3DDD0');
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  });

  onDestroy(() => {
    simulation?.stop();
  });
</script>

<div class="graph-container" style="position: relative;">
  <svg bind:this={svgEl} width="100%" height="100%"></svg>
  <div class="graph-tooltip" style={tooltipStyle}>
    {#each tooltipContent.split('\n') as line}
      <div>{line}</div>
    {/each}
  </div>
  <button
    class="physics-toggle"
    class:physics-on={physicsEnabled}
    onclick={togglePhysics}
    title={physicsEnabled ? 'Disable physics' : 'Enable physics'}
  >
    {physicsEnabled ? 'Physics: ON' : 'Physics: OFF'}
  </button>
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
  svg {
    width: 100%;
    height: 100%;
  }
  .graph-container svg :global(.node) {
    cursor: grab;
  }
  .graph-container svg :global(.node:active) {
    cursor: grabbing;
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
  .physics-toggle {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 5;
    background: var(--color-secondary);
    color: var(--color-text-primary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    cursor: pointer;
  }
  .physics-toggle:hover {
    filter: brightness(1.1);
  }
  .physics-toggle.physics-on {
    background: var(--color-accent);
    color: #ffffff;
    border-color: var(--color-accent);
  }
</style>
