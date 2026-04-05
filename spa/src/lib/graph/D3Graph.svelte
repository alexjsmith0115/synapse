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
  let controlsExpanded = $state(false);

  // Physics parameter controls — defaults match initial forceSimulation config
  let linkDistance = $state(100);
  let chargeStrength = $state(-400);
  let collisionRadius = $state(45);

  let selectedNodeId = null;
  let selectedLinkId = null;
  // Disambiguate single-click vs double-click
  let clickTimeout;

  function tick() {
    linkGroup.selectAll('line')
      .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    linkGroup.selectAll('text.edge-label')
      .attr('x', d => (d.source.x + d.target.x) / 2)
      .attr('y', d => (d.source.y + d.target.y) / 2);
    nodeGroup.selectAll('g.node')
      .attr('transform', d => `translate(${d.x},${d.y})`);
  }

  function updateLinkOpacity() {
    linkGroup.selectAll('line').attr('opacity', 1);
  }

  function getRootStroke(d) {
    if (d.isRoot) return { color: '#F0E68C', width: 3 };
    return { color: getNodeColor(d.kind), width: 2 };
  }

  function highlightSelected() {
    nodeGroup.selectAll('g.node').classed('selected', d => d.id === selectedNodeId);
    nodeGroup.selectAll('g.node.selected').select('circle')
      .attr('stroke-width', 4)
      .attr('stroke', getCSSVar('--color-accent') || '#2D6A4F');
    nodeGroup.selectAll('g.node:not(.selected)').select('circle').each(function(d) {
      const s = getRootStroke(d);
      d3.select(this).attr('stroke-width', s.width).attr('stroke', s.color);
    });

    if (selectedNodeId) {
      // Compute direct neighbor IDs from simulation link data
      const currentLinks = simulation.force('link').links();
      const neighborIds = new Set();
      for (const l of currentLinks) {
        const srcId = typeof l.source === 'object' ? l.source.id : l.source;
        const tgtId = typeof l.target === 'object' ? l.target.id : l.target;
        if (srcId === selectedNodeId) neighborIds.add(tgtId);
        if (tgtId === selectedNodeId) neighborIds.add(srcId);
      }

      // Dim non-neighbor, non-selected nodes
      nodeGroup.selectAll('g.node').each(function(d) {
        const isRelevant = d.id === selectedNodeId || neighborIds.has(d.id);
        d3.select(this).select('circle').attr('opacity', isRelevant ? 1 : 0.2);
        d3.select(this).select('text').attr('opacity', isRelevant ? 1 : 0.2);
      });

      // Dim non-connected links
      linkGroup.selectAll('line').attr('opacity', d => {
        const srcId = typeof d.source === 'object' ? d.source.id : d.source;
        const tgtId = typeof d.target === 'object' ? d.target.id : d.target;
        const isConnected = srcId === selectedNodeId || tgtId === selectedNodeId;
        return isConnected ? 1 : 0.1;
      });
    } else {
      // Restore full opacity for all nodes
      nodeGroup.selectAll('g.node').each(function() {
        d3.select(this).select('circle').attr('opacity', 1);
        d3.select(this).select('text').attr('opacity', 1);
      });
      updateLinkOpacity();
    }
  }

  function updateGraph(nodes, links) {
    // Links — enter/exit/update
    linkGroup.selectAll('line')
      .data(links, d => d.id)
      .join(
        enter => enter.append('line')
          .attr('stroke', getCSSVar('--color-border') || '#C3DDD0')
          .attr('stroke-width', 2)
          .attr('marker-end', 'url(#arrowhead)')
          .style('cursor', 'pointer')
          .on('click', (event, d) => {
            event.stopPropagation();
            // Deselect node when clicking edge
            selectedNodeId = null;
            highlightSelected();
            if (selectedLinkId === d.id) {
              // Toggle off
              selectedLinkId = null;
              linkGroup.selectAll('line').attr('stroke', getCSSVar('--color-border') || '#C3DDD0').attr('stroke-width', 2);
              linkGroup.selectAll('text.edge-label').remove();
            } else {
              selectedLinkId = d.id;
              linkGroup.selectAll('line')
                .attr('stroke', ld => ld.id === selectedLinkId
                  ? (getCSSVar('--color-accent') || '#2D6A4F')
                  : (getCSSVar('--color-border') || '#C3DDD0'))
                .attr('stroke-width', ld => ld.id === selectedLinkId ? 4 : 2);
              // Show edge label at midpoint — remove previous first
              linkGroup.selectAll('text.edge-label').remove();
              if (d.label && typeof d.source === 'object') {
                linkGroup.append('text')
                  .datum(d)
                  .attr('class', 'edge-label')
                  .attr('x', (d.source.x + d.target.x) / 2)
                  .attr('y', (d.source.y + d.target.y) / 2)
                  .attr('text-anchor', 'middle')
                  .attr('dy', '-6')
                  .attr('font-size', '11px')
                  .attr('fill', getCSSVar('--color-accent') || '#2D6A4F')
                  .style('pointer-events', 'none')
                  .style('user-select', 'none')
                  .text(d.label);
              }
            }
          })
          .on('mouseover', (event, d) => {
            if (d.id !== selectedLinkId) {
              d3.select(event.currentTarget).attr('stroke-width', 3);
            }
            tooltipContent = d.label || '';
            tooltipStyle = `display: block; left: ${event.offsetX + 15}px; top: ${event.offsetY + 15}px;`;
          })
          .on('mouseout', (event, d) => {
            if (d.id !== selectedLinkId) {
              d3.select(event.currentTarget).attr('stroke-width', 2);
            }
            tooltipStyle = 'display: none;';
          }),
        update => update
          .attr('stroke', d => d.id === selectedLinkId ? (getCSSVar('--color-accent') || '#2D6A4F') : (getCSSVar('--color-border') || '#C3DDD0'))
          .attr('stroke-width', d => d.id === selectedLinkId ? 4 : 2),
        exit => exit.remove()
      )
      .attr('opacity', 1);

    // Nodes — enter/exit/update
    nodeGroup.selectAll('g.node')
      .data(nodes, d => d.id)
      .join(
        enter => {
          const g = enter.append('g').attr('class', 'node');

          // Per-node shape and color
          g.each(function(d) {
            const sel = d3.select(this);
            const s = getRootStroke(d);
            appendNodeShape(sel, d.kind)
              .attr('fill', getNodeColor(d.kind))
              .attr('stroke', s.color)
              .attr('stroke-width', s.width)
              .attr('opacity', 1);

            sel.append('text')
              .text(d.label)
              .attr('font-size', '11px')
              .attr('text-anchor', 'middle')
              .attr('dy', '32')
              .attr('fill', getCSSVar('--color-text-primary') || '#1A2E23')
              .attr('opacity', 1)
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
                  // Sync d.x/d.y directly — simulation isn't running to do it
                  d.x = event.x;
                  d.y = event.y;
                  tick();
                }
              })
              .on('end', (event, d) => {
                if (physicsEnabled) {
                  if (!event.active) simulation.alphaTarget(0);
                  d.fx = null;
                  d.fy = null;
                } else {
                  // Commit position and keep pinned to prevent re-layout drift
                  d.x = d.fx;
                  d.y = d.fy;
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
              // Clear edge selection when node is selected
              selectedLinkId = null;
              linkGroup.selectAll('line')
                .attr('stroke', getCSSVar('--color-border') || '#C3DDD0')
                .attr('stroke-width', 2);
              linkGroup.selectAll('text.edge-label').remove();
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
          update.select('circle')
            .attr('opacity', 1)
            .each(function(d) {
              const s = getRootStroke(d);
              d3.select(this).attr('stroke', s.color).attr('stroke-width', s.width);
            });
          update.select('text').attr('opacity', 1);
          return update;
        },
        exit => exit.remove()
      );
  }

  function togglePhysics() {
    physicsEnabled = !physicsEnabled;
    if (physicsEnabled) {
      // Unpin all nodes so simulation can move them
      simulation.nodes().forEach(n => { n.fx = null; n.fy = null; });
      simulation.alpha(0.3).restart();
    } else {
      simulation.stop();
      // Pin all nodes at their current positions to prevent re-layout drift
      simulation.nodes().forEach(n => { n.fx = n.x; n.fy = n.y; });
    }
  }

  onMount(() => {
    const width = svgEl.clientWidth || 800;
    const height = svgEl.clientHeight || 600;

    const svg = d3.select(svgEl);

    // Arrow marker for directed edges.
    // markerUnits="userSpaceOnUse" fixes size in absolute pixels so the arrowhead
    // does not scale when a selected edge has a larger stroke-width.
    svg.append('defs').append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 32)
      .attr('refY', 0)
      .attr('markerWidth', 10)
      .attr('markerHeight', 10)
      .attr('markerUnits', 'userSpaceOnUse')
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

    // Click on empty canvas deselects node and edge
    svg.on('click', () => {
      selectedNodeId = null;
      selectedLinkId = null;
      highlightSelected();
      linkGroup.selectAll('line')
        .attr('stroke', getCSSVar('--color-border') || '#C3DDD0')
        .attr('stroke-width', 2);
      linkGroup.selectAll('text.edge-label').remove();
      onNodeSelect?.(null);
    });

    // Initial render — run synchronously for static layout, then freeze
    const nodes = elements.nodes.map(n => ({ ...n }));
    const links = elements.links.map(l => ({ ...l }));
    updateGraph(nodes, links);
    simulation.nodes(nodes);
    simulation.force('link').links(links);
    simulation.alpha(1.0).restart();
    simulation.tick(300);
    simulation.stop();
    // Remove center force after initial layout — prevents drift on re-layout
    simulation.force('center', null);
    // Pin all nodes at their computed positions
    nodes.forEach(n => { n.fx = n.x; n.fy = n.y; });
    tick();
    updateLinkOpacity();
  });

  // React to elements prop changes
  $effect(() => {
    if (!simulation || !elements) return;
    const oldNodes = simulation.nodes();
    // Preserve existing node positions — reuse data objects so fx/fy survive
    const nodes = elements.nodes.map(n => {
      const existing = oldNodes.find(e => e.id === n.id);
      return existing || { ...n };
    });
    const links = elements.links.map(l => ({ ...l }));
    const hasNewNodes = nodes.some(n => n.x == null);
    updateGraph(nodes, links);
    simulation.nodes(nodes);
    simulation.force('link').links(links);
    if (physicsEnabled) {
      simulation.alpha(hasNewNodes ? 0.5 : 0.1).restart();
    } else if (hasNewNodes) {
      // Only run simulation to position NEW nodes; existing stay pinned via fx/fy
      simulation.alpha(0.5);
      simulation.tick(300);
      simulation.stop();
      // Pin new nodes at their computed positions
      nodes.forEach(n => { if (n.fx == null) { n.fx = n.x; n.fy = n.y; } });
      tick();
      updateLinkOpacity();
    } else {
      // No new nodes — just update DOM without re-layout
      tick();
      updateLinkOpacity();
    }
  });

  // React to physics parameter slider changes
  $effect(() => {
    if (!simulation) return;
    // Access reactive values so Svelte tracks them
    const ld = linkDistance;
    const cs = chargeStrength;
    const cr = collisionRadius;
    simulation.force('link').distance(ld);
    simulation.force('charge').strength(cs);
    simulation.force('collision').radius(cr);
    if (physicsEnabled) {
      simulation.alpha(0.3).restart();
    } else {
      // Unpin, re-layout with new params, then re-pin
      simulation.nodes().forEach(n => { n.fx = null; n.fy = null; });
      simulation.alpha(0.3);
      simulation.tick(300);
      simulation.stop();
      simulation.nodes().forEach(n => { n.fx = n.x; n.fy = n.y; });
      tick();
      updateLinkOpacity();
    }
  });

  // Re-apply colors when theme changes
  $effect(() => {
    if (!svgEl) return;
    const observer = new MutationObserver(() => {
      nodeGroup.selectAll('g.node').each(function(d) {
        const s = getRootStroke(d);
        d3.select(this).select('circle')
          .attr('fill', getNodeColor(d.kind))
          .attr('stroke', d.id === selectedNodeId
            ? (getCSSVar('--color-accent') || '#2D6A4F')
            : s.color)
          .attr('stroke-width', d.id === selectedNodeId ? 4 : s.width);
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
  <div class="graph-toolbar">
    <button
      class="physics-toggle"
      class:physics-on={physicsEnabled}
      onclick={togglePhysics}
      title={physicsEnabled ? 'Disable physics' : 'Enable physics'}
    >
      {physicsEnabled ? 'Physics: ON' : 'Physics: OFF'}
    </button>
    <button
      class="controls-toggle"
      class:active={controlsExpanded}
      onclick={() => controlsExpanded = !controlsExpanded}
      title="Graph settings"
    >
      Settings
    </button>
    {#if controlsExpanded}
      <div class="controls-panel">
        <label class="control-label">
          Link Distance: {linkDistance}
          <input type="range" min="30" max="300" step="10" bind:value={linkDistance} />
        </label>
        <label class="control-label">
          Repel Force: {chargeStrength}
          <input type="range" min="-1000" max="-50" step="10" bind:value={chargeStrength} />
        </label>
        <label class="control-label">
          Collision Radius: {collisionRadius}
          <input type="range" min="10" max="100" step="5" bind:value={collisionRadius} />
        </label>
      </div>
    {/if}
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
  .graph-toolbar {
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 5;
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }
  .graph-toolbar > :global(button) {
    background: var(--color-secondary);
    color: var(--color-text-primary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 12px;
    cursor: pointer;
  }
  .graph-toolbar > :global(button:hover) {
    filter: brightness(1.1);
  }
  .physics-toggle.physics-on {
    background: var(--color-accent);
    color: #ffffff;
    border-color: var(--color-accent);
  }
  .controls-toggle.active {
    background: var(--color-secondary);
    border-color: var(--color-accent);
    color: var(--color-accent);
  }
  .controls-panel {
    background: var(--color-secondary);
    border: 1px solid var(--color-border);
    border-radius: 4px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  .control-label {
    display: flex;
    flex-direction: column;
    font-size: 11px;
    color: var(--color-text-primary);
    gap: 2px;
  }
  .control-label input[type="range"] {
    width: 120px;
    cursor: pointer;
  }
</style>
