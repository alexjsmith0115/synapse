<script>
  import { Sun, Moon } from 'lucide-svelte';
  import { getTheme, toggleTheme } from '../stores/theme.js';

  const isDark = $derived(getTheme() === 'dark');
</script>

<header class="header">
  <div class="header-left">
    <img src="/synapps-logo.svg" alt="Synapps logo" class="logo" width="28" height="28" />
    <span class="wordmark display">SYNAPPS</span>
  </div>
  <div class="header-right">
    <button
      class="theme-toggle"
      onclick={toggleTheme}
      title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      {#if isDark}
        <Sun size={20} />
      {:else}
        <Moon size={20} />
      {/if}
    </button>
  </div>
</header>

<style>
  .header {
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 24px;
    background: var(--color-secondary);
    border-bottom: 1px solid var(--color-border);
  }
  .header-left {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .logo {
    display: block;
  }
  .wordmark {
    color: var(--color-accent);
    letter-spacing: 2px;
  }
  .theme-toggle {
    background: none;
    border: none;
    cursor: pointer;
    color: var(--color-text-primary);
    padding: 8px;
    border-radius: 4px;
    display: flex;
    align-items: center;
  }
  .theme-toggle:hover {
    background: var(--color-dominant);
  }
</style>
