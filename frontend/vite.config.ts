import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Явный IPv4: на Windows «localhost» у Node резолвится в ::1, и сервер недоступен по 127.0.0.1.
    host: '127.0.0.1',
    port: 5183,
    strictPort: true,
    // Тот же origin, что и у фронтенда: httpOnly-cookie с токеном работает без CORS.
    proxy: { '/api': 'http://127.0.0.1:8100' },
  },
})
