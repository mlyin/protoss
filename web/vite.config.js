import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/leaderboard': 'http://localhost:8000', '/fills': 'http://localhost:8000', '/stats': 'http://localhost:8000', '/agents': 'http://localhost:8000', '/health': 'http://localhost:8000' } },
})
