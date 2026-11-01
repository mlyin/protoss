import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Every API path the dashboard reads, proxied to the backend in dev. brand/ sits outside web/, so the
// dev server is allowed to read one level up (the hero art is inlined from brand/hero.svg).
const api = 'http://localhost:8000'
const paths = ['/leaderboard', '/fills', '/stats', '/agents', '/health', '/orgs', '/feed', '/u', '/social', '/lab', '/builder', '/v1', '/onboard', '/docs', '/openapi.json']

export default defineConfig({
  plugins: [react()],
  server: {
    fs: { allow: ['..'] },
    proxy: Object.fromEntries(paths.map((p) => [p, api])),
  },
})
