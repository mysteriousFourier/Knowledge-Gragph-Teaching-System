export interface User {
  username: string
  user_id: string
  role: "student" | "teacher"
}

export interface LoginRequest {
  username: string
  password: string
}

export interface LoginResponse {
  success: boolean
  token?: string
  user?: User
  error?: string
}
