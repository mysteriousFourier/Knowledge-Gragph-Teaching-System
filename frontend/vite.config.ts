import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import { TanStackRouterVite } from "@tanstack/router-plugin/vite"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "")
  const backendTarget = env.VITE_DEV_API_TARGET || "http://127.0.0.1:8000"

  return {
  plugins: [react(), TanStackRouterVite()],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
      "/env-config.js": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  }
})
