import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En mode réel, /api est redirigé vers FastAPI (voir VITE_USE_MOCK dans .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
