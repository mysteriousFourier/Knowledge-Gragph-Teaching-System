import { Link, Outlet } from "@tanstack/react-router"
import { useLocation } from "@tanstack/react-router"
import { useEffect, useRef, useState } from "react"
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
  const [paperWidth, setPaperWidth] = useState(() => getStoredPaperWidth(isAuthenticated))
  const dragState = useRef<{ startX: number; startWidth: number } | null>(null)
  useTheme()
  const meta = getRouteMeta(location.pathname)
  const gate = getRouteGate(location.pathname)
  const canUseRoute =
    !gate ||
    (isAuthenticated && (!gate.role || user?.role === gate.role))

  useEffect(() => {
    const stored = getStoredPaperWidth(isAuthenticated)
    setPaperWidth((current) => {
      const hasStored = window.localStorage.getItem("kgts_paper_width")
      if (hasStored) {
        return clampPaperWidth(current)
      }
      return stored
    })
  }, [isAuthenticated])

  useEffect(() => {
    window.localStorage.setItem("kgts_paper_width", String(paperWidth))
  }, [paperWidth])

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      const state = dragState.current
      if (!state) return
      const nextWidth = clampPaperWidth(state.startWidth - (event.clientX - state.startX))
      setPaperWidth(nextWidth)
    }

    const handlePointerUp = () => {
      dragState.current = null
      document.body.classList.remove("is-resizing-workspace")
    }

    window.addEventListener("pointermove", handlePointerMove)
    window.addEventListener("pointerup", handlePointerUp)
    return () => {
      window.removeEventListener("pointermove", handlePointerMove)
      window.removeEventListener("pointerup", handlePointerUp)
    }
  }, [])

  const startResize = (event: React.PointerEvent<HTMLButtonElement>) => {
    dragState.current = { startX: event.clientX, startWidth: paperWidth }
    document.body.classList.add("is-resizing-workspace")
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  return (
    <div
      className={cn("studio-shell", isAuthenticated && "is-authenticated")}
      data-route={meta.key}
      style={{ "--paper-width": `${paperWidth}px` } as React.CSSProperties}
    >
      <section className="map-plane" aria-label="课程图谱上下文">
        <Header />
        <div className="axis x-axis">chapter layer / concept relation / response path</div>
        <div className="axis y-axis">evidence density</div>
        <KnowledgeField activeKey={meta.key} />
        <aside className="lens">
          <span className="mono">{meta.kicker}</span>
          <h1>{meta.lensTitle}</h1>
          <p>{meta.description}</p>
          <div className="lens-actions" aria-label="当前状态">
            <span>{isAuthenticated ? `${user?.role === "teacher" ? "Teacher" : "Student"} / ${user?.username}` : "Guest Session"}</span>
            <span>{meta.path}</span>
          </div>
        </aside>
      </section>

      <button
        type="button"
        className="workspace-resizer"
        aria-label="拖动调整工作区宽度"
        title="拖动调整工作区宽度"
        onPointerDown={startResize}
      >
        <span />
      </button>

      <section className="paper-stack" aria-label="当前功能纸面工作区">
        <header className="paper-top">
          <div>
            <span className="mono">active document</span>
            <h2>{meta.paperTitle}</h2>
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

function getStoredPaperWidth(isAuthenticated: boolean) {
  if (typeof window === "undefined") return isAuthenticated ? 820 : 560
  const stored = Number(window.localStorage.getItem("kgts_paper_width"))
  if (Number.isFinite(stored) && stored > 0) return clampPaperWidth(stored)
  return clampPaperWidth(isAuthenticated ? Math.round(window.innerWidth * 0.58) : 560)
}

function clampPaperWidth(width: number) {
  if (typeof window === "undefined") return Math.max(width, 360)
  const resizerWidth = 10
  const minMapWidth = window.innerWidth >= 1280 ? 72 : 48
  const max = Math.max(360, window.innerWidth - minMapWidth - resizerWidth)
  const min = Math.min(420, Math.max(320, window.innerWidth - 520))
  return Math.min(Math.max(width, min), max)
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
    path: "/",
    kicker: "system surface / all routes",
    lensTitle: "KGTS",
    paperTitle: "System Index",
    description: "知识图谱教学系统把登录、教师备课、PPT 文稿、授课、题库反馈、学生学习、练习、复习和图谱管理放回同一套工作台骨架里。",
  },
  {
    match: (path: string) => path.startsWith("/login"),
    key: "login",
    path: "/login",
    kicker: "auth / role gate",
    lensTitle: "Login",
    paperTitle: "Role Gate",
    description: "学生和教师从同一个入口进入，身份决定后续默认工作台。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/ppt"),
    key: "ppt",
    path: "/teacher/ppt",
    kicker: "teacher / ppt",
    lensTitle: "PPT",
    paperTitle: "Slide Manuscript",
    description: "解析幻灯片标题、正文、备注与表格，再生成逐页讲解文稿。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/lecture"),
    key: "lecture",
    path: "/teacher/lecture",
    kicker: "teacher / lecture",
    lensTitle: "Lecture",
    paperTitle: "Lecture Mode",
    description: "播放讲稿，也支持原文编辑和 Markdown / LaTeX 预览。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/exercises"),
    key: "exercises",
    path: "/teacher/exercises",
    kicker: "teacher / exercises",
    lensTitle: "Exercises",
    paperTitle: "Exercise Feedback",
    description: "生成练习题，查看选项和答案，并收集点赞或点踩反馈。",
  },
  {
    match: (path: string) => path.startsWith("/teacher/prepare"),
    key: "prepare",
    path: "/teacher/prepare",
    kicker: "teacher / prepare",
    lensTitle: "Prepare",
    paperTitle: "Prepare Mode",
    description: "导入图谱文件与章节内容，生成可检查、可保存的授课文稿。",
  },
  {
    match: (path: string) => path.startsWith("/teacher"),
    key: "teacher",
    path: "/teacher",
    kicker: "teacher / console",
    lensTitle: "Teacher",
    paperTitle: "Teacher Console",
    description: "教师端聚合备课、PPT 逐页文稿、授课、题库反馈与图谱管理。",
  },
  {
    match: (path: string) => path.startsWith("/student/learn"),
    key: "learn",
    path: "/student/learn",
    kicker: "student / learn",
    lensTitle: "Learn",
    paperTitle: "Learning Sheet",
    description: "围绕章节内容、公式和图谱证据组织学习材料。",
  },
  {
    match: (path: string) => path.startsWith("/student/practice"),
    key: "practice",
    path: "/student/practice",
    kicker: "student / practice",
    lensTitle: "Practice",
    paperTitle: "Practice Sheet",
    description: "学生完成题目并获得面向知识点的反馈。",
  },
  {
    match: (path: string) => path.startsWith("/student/review"),
    key: "review",
    path: "/student/review",
    kicker: "student / review",
    lensTitle: "Review",
    paperTitle: "Review Path",
    description: "沿图谱关系回顾薄弱概念和前置知识。",
  },
  {
    match: (path: string) => path.startsWith("/student"),
    key: "student",
    path: "/student",
    kicker: "student / console",
    lensTitle: "Student",
    paperTitle: "Student Console",
    description: "学生端聚合学习、练习与复习路径。",
  },
  {
    match: (path: string) => path.startsWith("/graph/admin"),
    key: "admin",
    path: "/graph/admin",
    kicker: "graph / admin",
    lensTitle: "Admin",
    paperTitle: "Graph Admin",
    description: "维护知识图谱节点内容，支持新增、编辑与删除。",
  },
  {
    match: (path: string) => path.startsWith("/graph"),
    key: "graph",
    path: "/graph",
    kicker: "graph / browser",
    lensTitle: "Graph",
    paperTitle: "Graph Browser",
    description: "浏览知识节点、筛选关系、聚焦邻居并查看节点详情。",
  },
]

function getRouteMeta(pathname: string) {
  return routeMeta.find((item) => item.match(pathname)) || routeMeta[0]
}

function KnowledgeField({ activeKey }: { activeKey: string }) {
  const selectedIndex = nodeMarks.findIndex((node) => node.key === activeKey)
  const selected = selectedIndex >= 0 ? selectedIndex : 0

  return (
    <svg className="knowledge-field" viewBox="0 0 1200 820" preserveAspectRatio="xMidYMid slice" role="img" aria-label="知识节点关系">
      <path className="thread primary" d="M173 393 C303 242 459 218 620 318 C741 391 843 358 1017 210" />
      <path className="thread" d="M197 451 C356 532 486 532 630 449 C742 384 842 461 1002 568" />
      <path className="thread" d="M334 204 C448 288 535 420 610 652" />
      <path className="thread faint" d="M740 126 C707 271 746 412 854 544" />
      <path className="thread faint" d="M243 640 C410 650 551 701 719 670" />
      {nodeMarks.map((node, index) => (
        <g
          key={node.key}
          className={cn("node", node.size, index === selected && "selected")}
          style={{ "--x": node.x, "--y": node.y } as React.CSSProperties}
        >
          <circle r={node.radius} />
          <text y={node.lines.length > 1 ? -6 : 5}>{node.lines[0]}</text>
          {node.lines[1] && <text y={14}>{node.lines[1]}</text>}
        </g>
      ))}
    </svg>
  )
}

const nodeMarks = [
  { key: "home", x: "124px", y: "348px", radius: 42, size: "large", lines: ["KGTS", "surface"] },
  { key: "teacher", x: "567px", y: "292px", radius: 38, size: "large", lines: ["Teacher", "flow"] },
  { key: "student", x: "975px", y: "186px", radius: 30, size: "medium", lines: ["student"] },
  { key: "graph", x: "972px", y: "546px", radius: 30, size: "medium", lines: ["graph"] },
  { key: "prepare", x: "300px", y: "180px", radius: 22, size: "small", lines: ["prepare"] },
  { key: "ppt", x: "592px", y: "635px", radius: 22, size: "small", lines: ["ppt"] },
  { key: "lecture", x: "212px", y: "618px", radius: 22, size: "small", lines: ["lecture"] },
  { key: "admin", x: "718px", y: "104px", radius: 22, size: "small", lines: ["admin"] },
]
