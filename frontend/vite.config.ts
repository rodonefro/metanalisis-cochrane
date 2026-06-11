import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_DEV_BACKEND ?? 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      port: 5173,
      // Proxy only used in development. In production the frontend calls
      // VITE_API_BASE_URL (the Render.com backend) directly.
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
      },
    },
  }
})
