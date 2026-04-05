<script>
  const { currentPage, totalPages, totalItems, pageSize, onPageChange } = $props();
</script>

<div class="pagination-bar">
  <button
    class="page-btn"
    disabled={currentPage === 1}
    onclick={() => onPageChange?.((currentPage - 2) * pageSize)}
  >
    Previous
  </button>
  <span class="page-indicator label text-secondary">
    Page {currentPage} of {totalPages} ({totalItems} total)
  </span>
  <button
    class="page-btn"
    disabled={currentPage === totalPages}
    onclick={() => onPageChange?.(currentPage * pageSize)}
  >
    Next
  </button>
</div>

<style>
  .pagination-bar {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 16px;
    margin-top: 16px;
  }
  .page-btn {
    padding: 4px 16px;
    background: var(--color-accent);
    color: white;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .page-btn:hover:not(:disabled) {
    opacity: 0.9;
  }
  .page-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .page-indicator {
    font-size: 14px;
  }
</style>
