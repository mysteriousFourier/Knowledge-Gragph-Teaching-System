import { defineConfig, loadEnv } from "vite"
import react from "@vitejs/plugin-react"
import { TanStackRouterVite } from "@tanstack/router-plugin/vite"

const qaxBrowserTarget = "chrome102"

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "")
  const backendTarget = env.VITE_DEV_API_TARGET || env.EDUCATION_API_BASE_URL || "http://127.0.0.1:8000"
  const enableSourceMap = env.VITE_BUILD_SOURCEMAP === "1" || env.VITE_BUILD_SOURCEMAP === "true"

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
      sourcemap: enableSourceMap,
      target: qaxBrowserTarget,
      cssTarget: qaxBrowserTarget,
      reportCompressedSize: false,
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return
            if (id.includes("react-markdown") || id.includes("react-katex") || id.includes("remark-") || id.includes("rehype-") || id.includes("katex")) {
              return "vendor-markdown"
            }
            if (id.includes("@xyflow") || id.includes("@dagrejs") || id.includes("elkjs")) {
              return "vendor-graph"
            }
            if (id.includes("lucide-react")) {
              return "vendor-icons"
            }
          },
        },
      },
    },
  }
})
