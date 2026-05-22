import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useState } from "react"
import { GraduationCap, BookOpen, Eye, EyeOff } from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { loginSchema, type LoginFormData } from "@/lib/validators"
import { useStudentLogin } from "@/api/student"
import { useTeacherLogin } from "@/api/teacher"
import { useAppDispatch } from "@/store/hooks"
import { loginStart, loginSuccess, loginFailure } from "@/store/slices/authSlice"
import { cn } from "@/lib/utils"
import type { LoginApiResponse } from "@/types/api"

export const Route = createFileRoute("/login")({
  component: LoginPage,
})

function LoginPage() {
  const [role, setRole] = useState<"student" | "teacher">("student")
  const [showPassword, setShowPassword] = useState(false)
  const navigate = useNavigate()
  const dispatch = useAppDispatch()

  const studentLogin = useStudentLogin()
  const teacherLogin = useTeacherLogin()

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: { role: "student" },
  })

  const onSubmit = async (data: LoginFormData) => {
    dispatch(loginStart())
    try {
      const selectedRole = role
      const mutation = selectedRole === "student" ? studentLogin : teacherLogin
      const result = await mutation.mutateAsync({
        username: data.username,
        password: data.password,
      })

      const session = normalizeLoginResponse(result, selectedRole)

      if (result.success && session) {
        dispatch(
          loginSuccess({
            user: session.user,
            token: session.token,
          })
        )
        navigate({ to: selectedRole === "student" ? "/student" : "/teacher" })
      } else {
        dispatch(loginFailure())
        alert(result.error || "登录失败")
      }
    } catch {
      dispatch(loginFailure())
      alert("登录请求失败，请检查网络连接")
    }
  }

  return (
    <div>
      <span className="sheet-label">Login</span>
      <h1 className="mt-3 text-4xl font-bold">角色进入</h1>
      <p className="mt-5 leading-8 text-muted-foreground">请选择学生或教师身份，登录后进入对应工作台。</p>

      <div className="mt-7">
        <div className="w-full">
          <div className="mb-6">
            <h2 className="text-xl font-semibold">知识图谱教学系统</h2>
            <p className="text-muted-foreground">身份决定默认工作流入口</p>
          </div>

          <div className="border bg-card p-5">
            <div className="mb-6 grid gap-2 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => setRole("student")}
                className={cn(
                  "flex min-h-16 items-center justify-center gap-2 border px-3 py-3 text-sm font-medium transition-colors",
                  role === "student"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                <GraduationCap size={18} />
                学生登录
              </button>
              <button
                type="button"
                onClick={() => setRole("teacher")}
                className={cn(
                  "flex min-h-16 items-center justify-center gap-2 border px-3 py-3 text-sm font-medium transition-colors",
                  role === "teacher"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                <BookOpen size={18} />
                教师登录
              </button>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
              <input type="hidden" {...register("role")} value={role} />

              <div>
                <label className="mb-1.5 block text-sm font-medium">
                  {role === "student" ? "学号/用户名" : "用户名"}
                </label>
                <input
                  {...register("username")}
                  type="text"
                  placeholder={role === "student" ? "请输入学号" : "请输入用户名"}
                />
                {errors.username && (
                  <p className="mt-1 text-xs text-destructive">{errors.username.message}</p>
                )}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium">密码</label>
                <div className="relative">
                  <input
                    {...register("password")}
                    type={showPassword ? "text" : "password"}
                    className="pr-10"
                    placeholder="请输入密码"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
                {errors.password && (
                  <p className="mt-1 text-xs text-destructive">{errors.password.message}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={studentLogin.isPending || teacherLogin.isPending}
                className="w-full bg-primary py-2.5 text-sm font-medium text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50"
              >
                {studentLogin.isPending || teacherLogin.isPending ? "登录中..." : "登录并进入工作台"}
              </button>
            </form>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              {role === "student" ? "学生账号由后端环境配置管理" : "教师账号由后端环境配置管理"}
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

function normalizeLoginResponse(result: LoginApiResponse, role: "student" | "teacher") {
  const user = result.data?.user || result.user
  const username = user?.username || result.username
  const userId = user?.user_id || result.user_id
  const responseRole = (user?.role || result.role || role) as "student" | "teacher"

  if (!username || !userId || responseRole !== role) {
    return null
  }

  return {
    user: {
      username,
      user_id: userId,
      role,
    },
    token: result.data?.token || result.token || `local-${role}-${userId}`,
  }
}
