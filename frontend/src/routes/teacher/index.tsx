import { createFileRoute, Link } from "@tanstack/react-router"
import { BookOpen, FileText, FolderOpen, Plus } from "lucide-react"
import { useCourses } from "@/api/courses"
import { useTeacherChapters } from "@/api/teacher"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import type { Chapter } from "@/types/chapter"
import type { Course } from "@/types/course"

export const Route = createFileRoute("/teacher/")({
  component: TeacherPage,
})

function TeacherPage() {
  const { data, isLoading, isError } = useCourses()
  const courses = data?.courses || []

  return (
    <div className="space-y-7">
      <header className="flex flex-col gap-4 border-b pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="sheet-label">Teacher Console</span>
          <h1 className="mt-2 text-3xl font-bold">课程选择</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            先进入一门课程，再选择具体课节进行备课或授课。
          </p>
        </div>
        <Link
          to="/teacher/courses"
          className="inline-flex min-h-10 items-center justify-center gap-2 border bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Plus size={16} />
          新建课程
        </Link>
      </header>

      {isLoading ? (
        <div className="flex min-h-48 items-center justify-center border bg-card">
          <LoadingSpinner text="正在加载课程..." />
        </div>
      ) : isError ? (
        <div className="border border-destructive/40 bg-card p-6 text-sm text-destructive">
          课程列表加载失败，请刷新后重试。
        </div>
      ) : courses.length === 0 ? (
        <EmptyState
          title="还没有课程"
          description="先新建一门课程，之后保存的课件和课节会归档到这里。"
        />
      ) : (
        <section className="space-y-4" aria-label="课程列表">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">我的课程</h2>
            <span className="mono text-xs text-muted-foreground">{courses.length} 门课程</span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {courses.map((course) => (
              <CourseCard key={course.id} course={course} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

function CourseCard({ course }: { course: Course }) {
  const { data, isLoading } = useTeacherChapters(course.id)
  const chapters = data?.chapters || []

  return (
    <article className="flex min-h-64 flex-col border bg-card p-5 transition-colors hover:border-primary/50">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <span className="mono text-[11px] uppercase tracking-[0.12em] text-muted-foreground">Course</span>
          <h3 className="mt-1 truncate text-xl font-semibold">{course.title}</h3>
          <p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">
            {course.description || "暂无课程说明"}
          </p>
        </div>
        <Link
          to="/teacher/prepare"
          search={{ chapterId: "", nodeId: "", courseId: course.id }}
          className="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 border bg-secondary px-3 text-sm font-medium transition-colors hover:bg-accent"
          title={`进入课程 ${course.title}`}
        >
          <FolderOpen size={15} />
          进入课程
        </Link>
      </div>

      <div className="mt-5 border-t pt-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold">课节</h4>
          <span className="mono text-xs text-muted-foreground">
            {isLoading ? "读取中" : `${chapters.length} 节`}
          </span>
        </div>
        {isLoading ? (
          <div className="flex min-h-16 items-center text-sm text-muted-foreground">
            <LoadingSpinner size={16} text="正在读取课节..." />
          </div>
        ) : chapters.length === 0 ? (
          <p className="border border-dashed px-3 py-4 text-sm text-muted-foreground">
            课程内还没有课节，进入备课后保存第一节课件。
          </p>
        ) : (
          <div className="space-y-2">
            {chapters.map((chapter, index) => (
              <LessonRow key={chapter.id} chapter={chapter} index={index} courseId={course.id} />
            ))}
          </div>
        )}
      </div>
    </article>
  )
}

function LessonRow({ chapter, index, courseId }: { chapter: Chapter; index: number; courseId: string }) {
  const hasLecture = Boolean(chapter.has_lecture_content || chapter.lecture_content)

  return (
    <div className="flex items-center gap-3 border bg-background/40 px-3 py-2.5">
      <span className="mono w-6 shrink-0 text-xs text-muted-foreground">{String(index + 1).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{chapter.title}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {hasLecture ? "已有授课文案" : "尚未生成授课文案"}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Link
          to="/teacher/prepare"
          search={{ chapterId: chapter.id, nodeId: "", courseId }}
          className="inline-flex h-8 items-center justify-center gap-1 border px-2.5 text-xs font-medium transition-colors hover:bg-accent"
          title={`备课：${chapter.title}`}
        >
          <BookOpen size={14} />
          备课
        </Link>
        <Link
          to="/teacher/lecture"
          search={{ chapterId: chapter.id, courseId }}
          className="inline-flex h-8 items-center justify-center gap-1 border bg-primary/10 px-2.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20"
          title={`授课：${chapter.title}`}
        >
          <FileText size={14} />
          授课
        </Link>
      </div>
    </div>
  )
}
