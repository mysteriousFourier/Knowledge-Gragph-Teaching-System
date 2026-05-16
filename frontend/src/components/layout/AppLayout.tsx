import { Link, Outlet } from "@tanstack/react-router"
import { useLocation } from "@tanstack/react-router"
import { Header } from "./Header"
import { Sidebar } from "./Sidebar"
import { Monitor, Moon, Sun } from "lucide-react"
import { useTheme } from "@/hooks/useTheme"
import { useAuth } from "@/hooks/useAuth"
import { useAppDispatch, useAppSelector } from "@/store/hooks"
import { setTheme } from "@/store/slices/uiSlice"
import { cn } from "@/lib/utils"

interface AppLayoutProps {
  children?: React.ReactNode
}

export function AppLayout({ children }: AppLayoutProps) {
  const location = useLocation()
  const dispatch = useAppDispatch()
  const theme = useAppSelector((state) => state.ui.theme)
  const { user, isAuthenticated } = useAuth()
  useTheme()
  const meta = getRouteMeta(location.pathname)
  const gate = getRouteGate(location.pathname)
  const canUseRoute =
    !gate ||
    (isAuthenticated && (!gate.role || user?.role === gate.role))

  return (
    <div
      className={cn("studio-shell", isAuthenticated && "is-authenticated")}
      data-route={meta.key}
    >
      <section className="paper-stack" aria-label="当前功能纸面工作区">
        <Header />
        <header className="paper-top">
          <div>
            <span className="mono">active document</span>
            <h2>{meta.paperTitle}</h2>
            <p className="paper-description">{meta.description}</p>
          </div>
          <div className="theme-switch" aria-label="主题切换">
            {themeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => dispatch(setTheme(option.value))}
                className={cn(theme === option.value && "active")}
                title={option.label}
              >
                {option.icon}
                <span>{option.label}</span>
              </button>
            ))}
          </div>
        </header>

        <main className="sheet active paper-workspace">
          {canUseRoute ? children || <Outlet /> : <AccessGate gate={gate} />}
        </main>

        <Sidebar />
      </section>
    </div>
  )
}

interface RouteGate {
  role?: "student" | "teacher"
  title: string
  description: string
}

function getRouteGate(pathname: string): RouteGate | null {
  if (pathname.startsWith("/teacher")) {
    return {
      role: "teacher",
      title: "需要教师登录",
      description: "备课、PPT 文稿、授课和题库反馈属于教师工作流，请先使用教师账号登录。",
    }
  }
  if (pathname.startsWith("/student")) {
    return {
      role: "student",
      title: "需要学生登录",
      description: "学习问答、练习做题和复习路径属于学生工作流，请先使用学生账号登录。",
    }
  }
  if (pathname.startsWith("/graph/admin")) {
    return {
      role: "teacher",
      title: "需要教师登录",
      description: "图谱管理会新增、编辑或删除节点，请先使用教师账号登录。",
    }
  }
  return null
}

function AccessGate({ gate }: { gate: RouteGate }) {
  return (
    <section>
      <span className="sheet-label">Access Required</span>
      <h1 className="mt-3 text-4xl font-bold">{gate.title}</h1>
      <p className="mt-5 leading-8 text-muted-foreground">{gate.description}</p>
      <div className="mt-7 grid gap-3 sm:grid-cols-2">
        <Link to="/login" className="inline-flex items-center justify-center border bg-primary px-4 py-3 text-sm font-medium text-primary-foreground">
          去登录
        </Link>
        <Link to="/" className="inline-flex items-center justify-center border bg-muted px-4 py-3 text-sm font-medium">
          回到首页
        </Link>
      </div>
    </section>
  )
}

const themeOptions: Array<{ value: "light" | "dark" | "system"; icon: React.ReactNode; label: string }> = [
  { value: "light", icon: <Sun size={15} />, label: "白天" },
  { value: "dark", icon: <Moon size={15} />, label: "夜晚" },
  { value: "system", icon: <Monitor size={15} />, label: "跟随系统" },
]

const routeMeta = [
  {
    match: (path: string) => path === "/",
    key: "home",
    paperTitle: "System Index",
    description: "知识图谱教学系统把登录、教师备课、PPT 文稿、授课、题库反馈、学生学习、练习、复习和图谱管理放回同一套工作台骨架里。",
  },
  {
    match: (path: string) => path.startsWith("/login"),
    key: "login",
    paperTitle: "Role Gate",
    description: "学生和教师从同一个入口进入，身份决定后续默认工作台。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/ppt"),
    key: "ppt",
    paperTitle: "Slide Manuscript",
    description: "解析幻灯片标题、正文、备注与表格，再生成逐页讲解文稿。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/lecture"),
    key: "lecture",
    paperTitle: "Lecture Mode",
    description: "播放讲稿，也支持原文编辑和 Markdown / LaTeX 预览。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/exercises"),
    key: "exercises",
    paperTitle: "Exercise Feedback",
    description: "生成练习题，查看选项和答案，并收集点赞或点踩反馈。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/prepare"),
    key: "prepare",
    paperTitle: "Prepare Mode",
    description: "导入图谱文件与章节内容，生成可检查、可保存的授课文稿。",
  },
  {
    match: (path: string) => path.startsWith("/teacher"),
    key: "teacher",
    paperTitle: "Teacher Console",
    description: "教师端聚合备课、PPT 逐页文稿、授课、题库反馈与图谱管理。",
  },
  {
    match: (path: string) => path.startsWith("/student/learn"),
    key: "learn",
    paperTitle: "Learning Sheet",
    description: "围绕章节内容、公式和图谱证据组织学习材料。",
  },
  {
    match: (path: string) => path.startsWith("/student/practice"),
    key: "practice",
    paperTitle: "Practice Sheet",
    description: "学生完成题目并获得面向知识点的反馈。",
  },
  {
    match: (path: string) => path.startsWith("/student/review"),
    key: "review",
    paperTitle: "Review Path",
    description: "沿图谱关系回顾薄弱概念和前置知识。",
  },
  {
    match: (path: string) => path.startsWith("/student"),
    key: "student",
    paperTitle: "Student Console",
    description: "学生端聚合学习、练习与复习路径。",
  },
  {
    match: (path: string) => path.startsWith("/graph/admin"),
    key: "admin",
    paperTitle: "Graph Admin",
    description: "维护知识图谱节点内容，支持新增、编辑与删除。",
  },
  {
    match: (path: string) => path.startsWith("/graph"),
    key: "graph",
    paperTitle: "Graph Browser",
    description: "浏览知识节点、筛选关系、聚焦邻居并查看节点详情。",
  },
]

function getRouteMeta(pathname: string) {
  return routeMeta.find((item) => item.match(pathname)) || routeMeta[0]
}
