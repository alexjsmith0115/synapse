// Theme store using Svelte 5 module-level state
// Per D-14: light default, toggle, persist to localStorage

const STORAGE_KEY = 'synapps-theme';

function getInitialTheme() {
  if (typeof window === 'undefined') return 'light';
  return localStorage.getItem(STORAGE_KEY) || 'light';
}

let current = $state(getInitialTheme());

export function getTheme() {
  return current;
}

export function toggleTheme() {
  current = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', current);
  localStorage.setItem(STORAGE_KEY, current);
}

export function initTheme() {
  document.documentElement.setAttribute('data-theme', current);
}
