import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    // In development the client runs on Vite and the API on uvicorn, so /api
    // has to be forwarded. In production one FastAPI process serves both, and
    // the client's same-origin `/api` paths work unchanged -- which is what
    // keeps the session cookie working without any CORS configuration.
    proxy: {
      "/api": {
        target: process.env.PF_API_ORIGIN ?? "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setup.js",
    css: false,
  },
});
