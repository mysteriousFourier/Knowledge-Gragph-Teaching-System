import "./lib/polyfills"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { routeTree } from "./routeTree.gen"
import { applyBrowserCompatibilityClasses } from "./lib/browserCompatibility"
import "./index.css"

applyBrowserCompatibilityClasses()

async function loadRuntimeConfig() {
  if ((window as unknown as { __APP_CONFIG__?: unknown }).__APP_CONFIG__) return
  await new Promise<void>((resolve) => {
    const script = document.createElement("script")
    script.src = "/env-config.js"
    script.onload = () => resolve()
    script.onerror = () => resolve()
    document.head.appendChild(script)
  })
}

const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

void loadRuntimeConfig().then(() => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>
  )
})
