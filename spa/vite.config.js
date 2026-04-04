import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig({
  plugins: [svelte()],
  base: '/',
  build: {
    outDir: '../src/synapps/web/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:7433',
    },
  },
});
