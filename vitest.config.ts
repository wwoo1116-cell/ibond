import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['guards/**/*.test.{ts,tsx}'],
    globals: true,
    setupFiles: ['./guards/setup.ts'],
    /* CDS ships ESM with extensionless relative imports (`./Table`), which
     * node's resolver rejects. Inlining routes the package through Vite's
     * resolver, which handles them — the same path the Next build takes. */
    server: { deps: { inline: [/@coinbase[\\/]cds-/] } },
  },
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, 'src') },
  },
});
