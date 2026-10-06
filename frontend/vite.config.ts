import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.REPO_EXPLORER_API_URL ?? 'http://127.0.0.1:8018'

export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.REPO_EXPLORER_WEB_PORT ?? 5178),
    strictPort: true,
    proxy: { '/api': apiTarget, '/docs': apiTarget, '/openapi.json': apiTarget },
  },
})
