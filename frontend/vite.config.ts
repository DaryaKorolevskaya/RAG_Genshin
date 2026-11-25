import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// В разработке /api проксируется на RAG-сервис, поэтому фронтенду не нужен CORS.
// В продакшене то же самое делает nginx (см. nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.RAG_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
