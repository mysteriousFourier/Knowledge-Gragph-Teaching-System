import { createSlice, type PayloadAction } from "@reduxjs/toolkit"

interface UIState {
  sidebarOpen: boolean
  theme: "light" | "dark" | "system"
  qaPanelOpen: boolean
  settingsOpen: boolean
  toast: { message: string; type: "success" | "error" | "info" } | null
}

const getStoredTheme = (): UIState["theme"] => {
  return (localStorage.getItem("kgts_theme") as UIState["theme"]) || "system"
}

const initialState: UIState = {
  sidebarOpen: true,
  theme: getStoredTheme(),
  qaPanelOpen: false,
  settingsOpen: false,
  toast: null,
}

const uiSlice = createSlice({
  name: "ui",
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarOpen = !state.sidebarOpen
    },
    setSidebarOpen: (state, action: PayloadAction<boolean>) => {
      state.sidebarOpen = action.payload
    },
    setTheme: (state, action: PayloadAction<UIState["theme"]>) => {
      state.theme = action.payload
      localStorage.setItem("kgts_theme", action.payload)
    },
    toggleQAPanel: (state) => {
      state.qaPanelOpen = !state.qaPanelOpen
    },
    setQAPanelOpen: (state, action: PayloadAction<boolean>) => {
      state.qaPanelOpen = action.payload
    },
    toggleSettings: (state) => {
      state.settingsOpen = !state.settingsOpen
    },
    setSettingsOpen: (state, action: PayloadAction<boolean>) => {
      state.settingsOpen = action.payload
    },
    showToast: (state, action: PayloadAction<{ message: string; type: "success" | "error" | "info" }>) => {
      state.toast = action.payload
    },
    clearToast: (state) => {
      state.toast = null
    },
  },
})

export const {
  toggleSidebar,
  setSidebarOpen,
  setTheme,
  toggleQAPanel,
  setQAPanelOpen,
  toggleSettings,
  setSettingsOpen,
  showToast,
  clearToast,
} = uiSlice.actions
export default uiSlice.reducer
