const qaxBrowserPattern = /\bQaxbrowser\b/i
const chromeVersionPattern = /\b(?:Chrome|Chromium)\/(\d+)/i

export type BrowserCompatibilityInfo = {
  isQaxBrowser: boolean
  chromeMajor: number | null
  isQaxChromium102: boolean
}

export function getBrowserCompatibilityInfo(userAgent = navigator.userAgent): BrowserCompatibilityInfo {
  const chromeMajorMatch = userAgent.match(chromeVersionPattern)
  const chromeMajor = chromeMajorMatch ? Number.parseInt(chromeMajorMatch[1], 10) : null
  const isQaxBrowser = qaxBrowserPattern.test(userAgent)

  return {
    isQaxBrowser,
    chromeMajor,
    isQaxChromium102: isQaxBrowser && chromeMajor === 102,
  }
}

export function applyBrowserCompatibilityClasses(root = document.documentElement) {
  const compatibility = getBrowserCompatibilityInfo()

  if (compatibility.isQaxBrowser) {
    root.classList.add("qax-browser")
  }

  if (compatibility.isQaxChromium102) {
    root.classList.add("qax-chromium-102")
  }

  return compatibility
}
