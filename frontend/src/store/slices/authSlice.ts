import { createSlice, type PayloadAction } from "@reduxjs/toolkit"
import type { User } from "@/types/auth"

interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

const getStoredAuth = (): { user: User | null; token: string | null } => {
  try {
    const token = localStorage.getItem("kgts_token")
    const userStr = localStorage.getItem("kgts_user")
    const user = userStr ? (JSON.parse(userStr) as User) : null
    return { token, user }
  } catch {
    return { token: null, user: null }
  }
}

const stored = getStoredAuth()

const initialState: AuthState = {
  user: stored.user,
  token: stored.token,
  isAuthenticated: !!stored.token,
  isLoading: false,
}

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    loginStart: (state) => {
      state.isLoading = true
    },
    loginSuccess: (state, action: PayloadAction<{ user: User; token: string }>) => {
      state.user = action.payload.user
      state.token = action.payload.token
      state.isAuthenticated = true
      state.isLoading = false
      localStorage.setItem("kgts_token", action.payload.token)
      localStorage.setItem("kgts_user", JSON.stringify(action.payload.user))
    },
    loginFailure: (state) => {
      state.isLoading = false
      state.isAuthenticated = false
    },
    logout: (state) => {
      state.user = null
      state.token = null
      state.isAuthenticated = false
      state.isLoading = false
      localStorage.removeItem("kgts_token")
      localStorage.removeItem("kgts_user")
    },
    updateUser: (state, action: PayloadAction<Partial<User>>) => {
      if (state.user) {
        state.user = { ...state.user, ...action.payload }
        localStorage.setItem("kgts_user", JSON.stringify(state.user))
      }
    },
  },
})

export const { loginStart, loginSuccess, loginFailure, logout, updateUser } = authSlice.actions
export default authSlice.reducer
