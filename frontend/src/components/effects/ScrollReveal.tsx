import { useEffect, type ReactNode } from "react"

interface ScrollRevealProps {
  children: ReactNode
  className?: string
}

export function ScrollReveal({ children, className = "" }: ScrollRevealProps) {
  useEffect(() => {
    const targetSelectors = [
      ".split-section > .section-copy",
      ".split-section > .flow-map",
      ".capability-section > .section-heading",
      ".capability-card",
      ".api-section > .section-copy",
      ".terminal-panel",
      ".entry-section > .section-heading",
      ".entry-card",
    ]

    let elements: HTMLElement[] = []
    let ticking = false

    function clamp(value: number, min: number, max: number) {
      return Math.max(min, Math.min(max, value))
    }

    function easeOutCubic(value: number) {
      return 1 - Math.pow(1 - value, 3)
    }

    function currentRiseY(element: HTMLElement) {
      const value = parseFloat(
        element.style.getPropertyValue("--scroll-rise-y")
      )
      return Number.isFinite(value) ? value : 0
    }

    function updateScrollRise() {
      ticking = false

      const viewportHeight =
        window.innerHeight || document.documentElement.clientHeight || 800
      const scrollY =
        window.scrollY || document.documentElement.scrollTop || 0
      const scrollHeight = Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight
      )
      const atDocumentBottom = scrollHeight - (scrollY + viewportHeight) <= 4
      const startLine = viewportHeight * 0.96
      const settleLine = viewportHeight * 0.48
      const travelSpan = Math.max(180, startLine - settleLine)

      elements.forEach((element, index) => {
        const rect = element.getBoundingClientRect()
        const previousY = currentRiseY(element)
        const naturalTop = rect.top - previousY
        const naturalBottom = rect.bottom - previousY
        const stagger = Math.min(72, (index % 4) * 18)
        let rawProgress =
          (startLine - naturalTop - stagger) / travelSpan

        if (
          atDocumentBottom &&
          naturalBottom > 0 &&
          naturalTop < viewportHeight
        ) {
          rawProgress = 1
        }

        const progress = easeOutCubic(clamp(rawProgress, 0, 1))
        const settledProgress = progress > 0.985 ? 1 : progress
        const baseOffset =
          element.classList.contains("capability-card") ||
          element.classList.contains("entry-card")
            ? 92
            : 118
        const y = (1 - settledProgress) * baseOffset
        const opacity = 0.02 + settledProgress * 0.98
        const blur = settledProgress >= 1 ? 0 : (1 - settledProgress) * 10

        element.style.setProperty("--scroll-rise-y", `${y.toFixed(2)}px`)
        element.style.setProperty(
          "--scroll-rise-opacity",
          opacity.toFixed(3)
        )
        element.style.setProperty("--scroll-rise-blur", `${blur.toFixed(2)}px`)
      })
    }

    function requestUpdate() {
      if (ticking) return
      ticking = true
      requestAnimationFrame(updateScrollRise)
    }

    function initScrollRise() {
      const seen = new Set<HTMLElement>()
      elements = []

      targetSelectors.forEach((selector) => {
        document.querySelectorAll(selector).forEach((element) => {
          if (!seen.has(element as HTMLElement)) {
            seen.add(element as HTMLElement)
            elements.push(element as HTMLElement)
          }
        })
      })

      elements.forEach((element) => {
        element.classList.add("scroll-rise")
      })

      document.documentElement.dataset.homeScrollRise = elements.length
        ? "js"
        : "empty"
      window.addEventListener("scroll", requestUpdate, { passive: true })
      window.addEventListener("resize", requestUpdate, { passive: true })
      window.setTimeout(requestUpdate, 120)
      requestUpdate()
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initScrollRise, {
        once: true,
      })
    } else {
      initScrollRise()
    }

    return () => {
      window.removeEventListener("scroll", requestUpdate)
      window.removeEventListener("resize", requestUpdate)
    }
  }, [])

  return <div className={className}>{children}</div>
}
