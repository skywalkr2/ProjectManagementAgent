/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Relative asset paths: the server adds a <base> for its configured base path, so one build serves any base path.
// In development, API calls go to the server named by COCKPIT_DEV_SERVER.
const devServer = process.env.COCKPIT_DEV_SERVER ?? "http://127.0.0.1:8765";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  server: {
    // The app answers only to its own address and refuses another site's Origin, so the proxy presents the app's own
    // address as both: the Host header (changeOrigin) and the Origin of requests that carry one.
    proxy: {
      "/api": {
        target: devServer,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq) => {
            if (proxyReq.getHeader("origin") !== undefined) proxyReq.setHeader("origin", new URL(devServer).origin);
          });
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
