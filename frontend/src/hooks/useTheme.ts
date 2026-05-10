import { useEffect } from "react"
import { useAppSelector } from "@/store/hooks"

export function useTheme() {
  const theme = useAppSelector((state) => state.ui.theme)

  useEffect(() => {
    const root = window.document.documentElement
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)")

    const applyTheme = () => {
      const isDark =
        theme === "dark" || (theme === "system" && systemDark.matches)

      if (isDark) {
        root.classList.add("dark")
      } else {
        root.classList.remove("dark")
      }
    }

    applyTheme()

    if (theme === "system") {
      systemDark.addEventListener("change", applyTheme)
      return () => systemDark.removeEventListener("change", applyTheme)
    }
  }, [theme])

  return theme
}
