import { defineConfig, loadEnv } from 'vite';

function apiTarget(value: string | undefined): string {
  const url = new URL(value?.trim() || 'http://127.0.0.1:8790');
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('VITE_MEMORY_TARGET must be an HTTP(S) URL without credentials, query or fragment');
  }
  return url.toString().replace(/\/$/, '');
}

function publicPage(value: string | undefined): string | undefined {
  if (!value) return value;
  const url = new URL(value, 'http://vite.local');
  if (['/app', '/app/', '/login'].includes(url.pathname)) return '/portal.html' + url.search;
  if (['/docs', '/docs/'].includes(url.pathname)) return '/docs.html' + url.search;
  return value;
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, import.meta.dirname, 'VITE_');
  const target = apiTarget(env.VITE_MEMORY_TARGET);
  return {
    root: import.meta.dirname,
    plugins: [{
      name: 'kairos-pages',
      configureServer(server) {
        server.middlewares.use((request, _response, next) => { request.url = publicPage(request.url); next(); });
      },
      configurePreviewServer(server) {
        server.middlewares.use((request, _response, next) => { request.url = publicPage(request.url); next(); });
      },
    }],
    server: {
      port: 5173,
      watch: { usePolling: env.VITE_USE_POLLING !== 'false', interval: 1000 },
      proxy: {
        '/memory-api': { target, changeOrigin: false, rewrite: (path: string) => path.replace(/^\/memory-api(?=\/|$)/, '') },
        '/v1': { target, changeOrigin: false },
        '/mcp': { target, changeOrigin: false },
        '/health/ready': { target, changeOrigin: false },
      },
    },
    build: {
      rollupOptions: {
        input: {
          home: `${import.meta.dirname}/index.html`,
          docs: `${import.meta.dirname}/docs.html`,
          portal: `${import.meta.dirname}/portal.html`,
        },
        output: {
          manualChunks(moduleId) {
            const id = moduleId.replaceAll('\\', '/');
            if (!id.includes('/node_modules/')) return undefined;
            if (id.includes('/node_modules/three/examples/')) return 'vendor-three-extras';
            if (id.includes('/node_modules/three/build/three.core')) return 'vendor-three-core';
            if (id.includes('/node_modules/three/')) return 'vendor-three-renderer';
            if (['/node_modules/d3-', '/node_modules/ngraph.', '/node_modules/internmap/', '/node_modules/delaunator/', '/node_modules/robust-predicates/'].some(part => id.includes(part))) return 'vendor-layout';
            return 'vendor-graph';
          },
        },
      },
    },
  };
});
