<script>
  const { name, fullName = '', kind = '', filePath = '', line = 0, onNavigate } = $props();

  function handleClick(event) {
    onNavigate?.({ full_name: fullName || name, kind, file_path: filePath, line }, event);
  }
</script>

<span class="symbol-link">
  <button class="symbol-name" onclick={handleClick} title={fullName || name}>
    {name}
  </button>
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
    text-align: left;
    text-decoration: none;
  }
  .symbol-name:hover {
    text-decoration: underline;
  }
</style>
