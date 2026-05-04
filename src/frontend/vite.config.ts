import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg'],
      devOptions: { enabled: false },
      manifest: {
        name: 'TaskPilot Cockpit',
        short_name: 'TaskPilot',
        description: 'AI-agentic Task Management Cockpit',
        theme_color: '#4F46E5',
        background_color: '#030712',
        display: 'standalone',
        scope: '/',
        id: '/',
        start_url: '/',
        icons: [
          { src: '/pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/pwa-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        runtimeCaching: [
          {
            // Kein Cache für Streams (SSE) — kann sonst Abort / «network error» verursachen
            urlPattern: ({ url }) =>
              /^\/api\//.test(url.pathname) &&
              !/^\/api\/code\//.test(url.pathname) &&
              !/^\/api\/sse\//.test(url.pathname),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-cache',
              expiration: { maxEntries: 50, maxAgeSeconds: 300 },
            },
          },
        ],
      },
    }),
  ],
  server: {
    allowedHosts: ['tp.innosmith.ai'],
    proxy: {
      '/api/code': {
        target: 'http://localhost:8000',
        timeout: 0,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api/sse': {
        target: 'http://localhost:8000',
        timeout: 0,
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            proxyRes.headers['cache-control'] = 'no-cache';
            proxyRes.headers['x-accel-buffering'] = 'no';
          });
        },
      },
      '/api': 'http://localhost:8000',
      '/uploads': 'http://localhost:8000',
    },
  },
})
