import { Link } from "@tanstack/react-router"
import { BookOpen, GraduationCap, Home, LogOut, MessageCircle, Network, Settings, Shield, User } from "lucide-react"
import { useAuth } from "@/hooks/useAuth"
import { useAppDispatch } from "@/store/hooks"
import { toggleQAPanel, toggleSettings } from "@/store/slices/uiSlice"
import { APP_NAME } from "@/lib/constants"
import { cn } from "@/lib/utils"

interface HeaderProps {
  className?: string
}

export function Header({ className }: HeaderProps) {
  const { user, isAuthenticated, logout } = useAuth()
  const dispatch = useAppDispatch()

  return (
    <header className={cn("coordinate-bar", className)}>
      <Link to="/" className="mark brand-mark" title={APP_NAME}>
        <BookOpen size={15} />
        <span>KGTS</span>
      </Link>
      <Link to="/" className="mark">
        <Home size={14} />
        <span>Home</span>
      </Link>
      <Link to="/teacher" className="mark">
        <BookOpen size={14} />
        <span>Teacher</span>
      </Link>
      <Link to="/student" className="mark">
        <GraduationCap size={14} />
        <span>Student</span>
      </Link>
      <Link to="/graph" className="mark">
        <Network size={14} />
        <span>Graph</span>
      </Link>
      <Link to="/graph/admin" className="mark">
        <Shield size={14} />
        <span>Admin</span>
      </Link>

      {isAuthenticated && (
        <>
          <button type="button" onClick={() => dispatch(toggleQAPanel())} className="mark icon-mark" title="问答">
            <MessageCircle size={15} />
          </button>
          <button type="button" onClick={() => dispatch(toggleSettings())} className="mark icon-mark" title="设置">
            <Settings size={15} />
          </button>
          <button type="button" onClick={logout} className="mark user-mark" title="退出登录">
            <User size={14} />
            <span>{user?.username}</span>
            <LogOut size={14} />
          </button>
        </>
      )}
    </header>
  )
}
