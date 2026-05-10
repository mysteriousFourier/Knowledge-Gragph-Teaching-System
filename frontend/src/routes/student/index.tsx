import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowRight, BookOpen, Brain, RotateCcw } from "lucide-react"
import { useStudentChapters } from "@/api/student"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import type { Chapter } from "@/types/chapter"

export const Route = createFileRoute("/student/")({
  component: StudentPage,
})

function StudentPage() {
  const { data, isLoading } = useStudentChapters()
  const chapters = data?.chapters || []

  return (
    <div className="space-y-6">
      <div>
        <span className="sheet-label">Student Console</span>
        <h1 className="text-2xl font-bold">学生端</h1>
        <p className="text-muted-foreground">选择章节开始学习</p>
      </div>

      <div className="route-grid">
        <QuickActionCard
          to="/student/learn"
          icon={<BookOpen className="h-5 w-5" />}
          title="学习模式"
          description="阅读课程内容"
        />
        <QuickActionCard
          to="/student/practice"
          icon={<Brain className="h-5 w-5" />}
          title="练习模式"
          description="做题巩固知识"
        />
        <QuickActionCard
          to="/student/review"
          icon={<RotateCcw className="h-5 w-5" />}
          title="复习模式"
          description="回顾学习路径"
        />
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4">章节列表</h2>
        {isLoading ? (
          <LoadingSpinner text="加载章节中..." />
        ) : chapters.length === 0 ? (
          <EmptyState title="暂无章节" description="当前没有可用的学习章节，请联系教师导入内容。" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {chapters.map((chapter) => (
              <ChapterCard key={chapter.id} chapter={chapter} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function QuickActionCard({
  to,
  icon,
  title,
  description,
}: {
  to: string
  icon: React.ReactNode
  title: string
  description: string
}) {
  return (
    <Link
      to={to}
      className="flex min-h-24 items-center gap-4 bg-card p-4 transition-all"
    >
      <div className="p-3 text-primary">{icon}</div>
      <div className="flex-1">
        <h3 className="font-medium">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <ArrowRight size={16} className="text-muted-foreground" />
    </Link>
  )
}

function ChapterCard({ chapter }: { chapter: Chapter }) {
  return (
    <Link
      to="/student/learn"
      search={{ chapterId: chapter.id }}
      className="group flex flex-col border bg-card p-5 transition-all"
    >
      <h3 className="font-semibold text-lg mb-2 group-hover:text-primary transition-colors">{chapter.title}</h3>
      <p className="text-sm text-muted-foreground line-clamp-2 mb-4">
        {chapter.content?.substring(0, 100) || "暂无内容描述"}
      </p>
      <div className="mt-auto flex items-center text-sm text-primary">
        开始学习
        <ArrowRight size={14} className="ml-1 group-hover:translate-x-1 transition-transform" />
      </div>
    </Link>
  )
}
