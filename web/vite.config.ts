// Dev server and build settings; /api calls are forwarded to the backend.

/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const API = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // Same-origin in dev too: /api/* is forwarded to FastAPI with the prefix stripped.
      "/api": {
        target: API,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      // The Swagger page at /api/docs loads its schema from the absolute path /openapi.json.
      "/openapi.json": { target: API },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router"],
          charts: ["recharts"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
