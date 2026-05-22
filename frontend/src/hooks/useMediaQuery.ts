import { useState, useEffect } from "react"

const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  "2xl": 1536,
}

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    const media = window.matchMedia(query)
    if (media.matches !== matches) {
      setMatches(media.matches)
    }
    const listener = () => setMatches(media.matches)
    media.addEventListener("change", listener)
    return () => media.removeEventListener("change", listener)
  }, [matches, query])

  return matches
}

export function useIsMobile() {
  return useMediaQuery(`(max-width: ${breakpoints.md - 1}px)`)
}

export function useIsTablet() {
  return useMediaQuery(`(min-width: ${breakpoints.md}px) and (max-width: ${breakpoints.lg - 1}px)`)
}

export function useIsDesktop() {
  return useMediaQuery(`(min-width: ${breakpoints.lg}px)`)
}
