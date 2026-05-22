import { Link, useLocation } from "@tanstack/react-router"
import { BookOpen, Brain, FileText, FileUp, Network, PencilRuler, ShieldCheck } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"

const commandItems = [
  { to: "/teacher/prepare", label: "Prepare", icon: PencilRuler, role: "teacher" },
  { to: "/teacher/ppt", label: "PPT", icon: FileUp, role: "teacher" },
  { to: "/teacher/lecture", label: "Lecture", icon: FileText, role: "teacher" },
  { to: "/teacher/exercises", label: "Exercises", icon: Brain, role: "teacher" },
  { to: "/student/learn", label: "Learn", icon: BookOpen, role: "student" },
  { to: "/student/practice", label: "Practice", icon: Brain, role: "student" },
  { to: "/graph", label: "Graph", icon: Network },
  { to: "/graph/admin", label: "Admin", icon: ShieldCheck, role: "teacher" },
]

export function Sidebar() {
  const location = useLocation()
  const { user, isAuthenticated } = useAuth()
  const visibleItems = commandItems.filter((item) => {
    if (!item.role) return true
    if (!isAuthenticated) return false
    return user?.role === item.role
  })

  return (
    <nav className="command-strip" aria-label="快速入口">
      {visibleItems.map((item) => {
        const Icon = item.icon
        const isActive = location.pathname === item.to || location.pathname.startsWith(`${item.to}/`)

        return (
          <Link key={item.to} to={item.to} className={cn(isActive && "active")}>
            <Icon size={14} />
            <span>{item.label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
