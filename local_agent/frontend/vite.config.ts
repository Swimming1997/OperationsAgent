import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

declare const process: { env: Record<string, string | undefined> };

// The built bundle is served by the local agent bridge as static files under
// its own origin, so assets must be referenced relatively.
const bridgeProxyTarget = process.env.VITE_BRIDGE_PROXY_TARGET || 'http://127.0.0.1:18765';

export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: '../local_agent_runtime/web/dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': bridgeProxyTarget,
      '/bridge': bridgeProxyTarget,
    },
  },
});
