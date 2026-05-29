export interface ApiResponse<T = unknown> {
  success: boolean
  data?: T
  error?: string
  timestamp?: string
}

export interface LoginApiResponse {
  success: boolean
  data?: {
    token?: string
    user?: {
      username: string
      user_id: string
      role: "student" | "teacher" | string
    }
  }
  token?: string
  user?: {
    username: string
    user_id: string
    role: "student" | "teacher" | string
  }
  username?: string
  user_id?: string
  role?: "student" | "teacher" | string
  error?: string
  message?: string
}

export interface HealthCheckResponse {
  status: string
  timestamp?: string
}

export interface ConfigStatusResponse {
  success: boolean
  deepseek_api_key_configured: boolean
  deepseek_api_key_fingerprint?: string
  deepseek_api_key_length?: number
  flash_model: string
  pro_model: string
  deepseek_api_base?: string
}

export interface SaveConfigResponse {
  success: boolean
  deepseek_api_key_configured: boolean
  deepseek_api_key_fingerprint?: string
  deepseek_api_key_length?: number
  flash_model: string
  pro_model: string
  deepseek_api_base?: string
  message?: string
}

export interface DeepSeekConfigTestResponse extends SaveConfigResponse {
  response_preview?: string
  error?: string
}
