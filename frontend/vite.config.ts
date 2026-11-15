import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The API has no CORS on purpose: in dev the browser only ever talks to Vite,
// and Vite forwards /api and /health to FastAPI.
const API = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": API, "/health": API },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
