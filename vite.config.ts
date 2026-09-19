import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs separately on :8000 and keeps its own throwaway demo page at
// `/`. Only `/api` is proxied, so that page stays reachable there untouched and
// the client code never needs an absolute base URL.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
