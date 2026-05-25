import { createFileRoute, Link } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { ArrowRight, BookOpen, Brain, FileText, MessageSquare, Trash2 } from "lucide-react"
import { useDeleteChapter, useTeacherChapters } from "@/api/teacher"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import type { Chapter } from "@/types/chapter"

export const Route = createFileRoute("/teacher/")({
  component: TeacherPage,
})

function TeacherPage() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useTeacherChapters()
  const deleteChapter = useDeleteChapter()
  const chapters = data?.chapters || []

  const handleDeleteChapter = async (chapter: Chapter) => {
    if (!window.confirm(`删除课程「${chapter.title}」？`)) return
    const result = await deleteChapter.mutateAsync(chapter.id)
    if (!result.success) {
      window.alert(result.error || "删除失败")
      return
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-progress"] }),
    ])
  }

  return (
    <div className="space-y-6">
      <div>
        <span className="sheet-label">Teacher Console</span>
        <h1 className="text-2xl font-bold">教师端</h1>
        <p className="text-muted-foreground">管理课程、生成授课文案和练习题</p>
      </div>

      <div className="route-grid">
        <QuickActionCard
          to="/teacher/prepare"
          icon={<BookOpen className="h-5 w-5" />}
          title="备课工作台"
          description="树选课程内容生成课件与逐页讲解"
        />
        <QuickActionCard
          to="/teacher/lecture"
          icon={<FileText className="h-5 w-5" />}
          title="授课模式"
          description="播放讲解内容"
        />
        <QuickActionCard
          to="/teacher/exercises"
          icon={<Brain className="h-5 w-5" />}
          title="题库反馈"
          description="管理练习题与反馈"
        />
        <QuickActionCard
          to="/graph/admin"
          icon={<MessageSquare className="h-5 w-5" />}
          title="图谱管理"
          description="维护知识图谱"
        />
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4">已保存课程</h2>
        {isLoading ? (
          <LoadingSpinner text="加载课程中..." />
        ) : chapters.length === 0 ? (
          <EmptyState title="暂无课程" description="当前没有已保存的课程，请在备课模式导入内容。" />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {chapters.map((chapter) => (
              <ChapterCard
                key={chapter.id}
                chapter={chapter}
                isDeleting={deleteChapter.isPending}
                onDelete={handleDeleteChapter}
              />
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
      <div className="flex-1 min-w-0">
        <h3 className="font-medium">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <ArrowRight size={16} className="text-muted-foreground shrink-0" />
    </Link>
  )
}

function ChapterCard({
  chapter,
  isDeleting,
  onDelete,
}: {
  chapter: Chapter
  isDeleting: boolean
  onDelete: (chapter: Chapter) => void
}) {
  return (
    <div className="group flex flex-col border bg-card p-5 transition-all">
      <h3 className="font-semibold text-lg mb-2">{chapter.title}</h3>
      <div className="space-y-1 mb-4">
        <p className="text-xs text-muted-foreground">
          创建时间: {formatChapterDate(chapter.created_at)}
        </p>
        <p className="text-xs text-muted-foreground">
          授课文案: {chapter.lecture_content ? "已生成" : "未生成"}
        </p>
      </div>
      <div className="mt-auto flex items-center gap-2">
        <Link
          to="/teacher/prepare"
          search={{ chapterId: chapter.id, nodeId: "" }}
          className="flex-1 text-center py-2 bg-primary/10 text-primary rounded-lg text-sm font-medium hover:bg-primary/20 transition-colors"
        >
          备课
        </Link>
        <Link
          to="/teacher/lecture"
          search={{ chapterId: chapter.id }}
          className="flex-1 text-center py-2 bg-secondary text-secondary-foreground rounded-lg text-sm font-medium hover:bg-secondary/80 transition-colors"
        >
          授课
        </Link>
        <button
          type="button"
          onClick={() => onDelete(chapter)}
          disabled={isDeleting}
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-destructive hover:bg-destructive/10 disabled:opacity-50"
          title="删除课程"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )
}

function formatChapterDate(value?: string | number) {
  if (value === undefined || value === null || value === "") return "未知"
  const raw = typeof value === "number" ? value : Number(value)
  const date = Number.isFinite(raw) ? new Date(raw < 100000000000 ? raw * 1000 : raw) : new Date(value)
  return Number.isNaN(date.getTime()) ? "未知" : date.toLocaleDateString("zh-CN")
}
