import { createFileRoute, Link, useNavigate } from "@tanstack/react-router"
import { BookOpen, FolderOpen, Pencil, Plus, Save, Trash2, X } from "lucide-react"
import { useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { useCourses, useCreateCourse, useDeleteCourse, useUpdateCourse } from "@/api/courses"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import type { Course } from "@/types/course"

export const Route = createFileRoute("/teacher/courses")({
  component: TeacherCoursesPage,
})

function TeacherCoursesPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data, isLoading, isError } = useCourses()
  const createCourse = useCreateCourse()
  const deleteCourse = useDeleteCourse()
  const updateCourse = useUpdateCourse()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [status, setStatus] = useState("")
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState("")
  const [editDescription, setEditDescription] = useState("")
  const courses = data?.courses || []

  const handleCreate = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const cleanTitle = title.trim()
    if (!cleanTitle) {
      setStatus("请填写课程名称")
      return
    }
    setStatus("")
    try {
      const result = await createCourse.mutateAsync({ title: cleanTitle, description: description.trim() })
      await queryClient.invalidateQueries({ queryKey: ["courses"] })
      setTitle("")
      setDescription("")
      navigate({ to: "/teacher/prepare", search: { chapterId: "", nodeId: "", courseId: result.course.id } })
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "课程创建失败，请稍后重试")
    }
  }

  const handleDelete = async (course: Course) => {
    if (!window.confirm(`删除课程“${course.title}”？已保存的课件文件会保留。`)) return
    try {
      await deleteCourse.mutateAsync(course.id)
      await queryClient.invalidateQueries({ queryKey: ["courses"] })
      setStatus("课程已删除，课件文件仍可从备课项目中恢复")
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "课程删除失败，请稍后重试")
    }
  }

  const startEdit = (course: Course) => { setEditingId(course.id); setEditTitle(course.title); setEditDescription(course.description || ""); setStatus("") }
  const cancelEdit = () => setEditingId(null)
  const saveEdit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!editingId || !editTitle.trim()) return
    try {
      await updateCourse.mutateAsync({ courseId: editingId, title: editTitle.trim(), description: editDescription.trim() })
      await queryClient.invalidateQueries({ queryKey: ["courses"] }); setEditingId(null); setStatus("课程信息已更新")
    } catch (error) { setStatus(error instanceof Error ? error.message : "课程更新失败") }
  }

  return (
    <div className="space-y-7">
      <header className="flex flex-col gap-3 border-b pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="sheet-label">Course Registry</span>
          <h1 className="mt-2 text-3xl font-bold">课程</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">先建立课程，再把课件、讲稿和练习归入对应课程。</p>
        </div>
        <div className="mono flex items-center gap-2 text-xs text-muted-foreground">
          <BookOpen size={15} /> {courses.length} 门课程
        </div>
      </header>

      <section className="grid gap-6 xl:grid-cols-[minmax(280px,0.72fr)_minmax(0,1.28fr)]">
        <form onSubmit={handleCreate} className="border bg-card p-5">
          <div className="mb-4 flex items-center gap-2 font-semibold"><Plus size={18} /> 建立新课程</div>
          <label className="mb-3 block text-sm font-medium">
            课程名称
            <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="例如：线性代数基础" className="mt-2" maxLength={160} autoFocus />
          </label>
          <label className="mb-4 block text-sm font-medium">
            课程说明 <span className="font-normal text-muted-foreground">（可选）</span>
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} placeholder="面向对象、教学范围或学期信息" className="mt-2 min-h-28 resize-y" maxLength={1000} />
          </label>
          <button type="submit" disabled={createCourse.isPending} className="inline-flex w-full items-center justify-center gap-2 bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-60">
            {createCourse.isPending ? <LoadingSpinner size={16} /> : <Plus size={16} />} 创建并进入备课
          </button>
          {status ? <p className="mt-3 text-sm text-muted-foreground" role="status">{status}</p> : null}
        </form>

        <section>
          <div className="mb-3 flex items-center justify-between"><h2 className="text-lg font-semibold">已建立的课程</h2><span className="mono text-xs text-muted-foreground">按最近更新</span></div>
          {isLoading ? <div className="flex min-h-40 items-center justify-center border"><LoadingSpinner text="正在加载课程" /></div> : isError ? <div className="border p-5 text-sm text-destructive">课程列表加载失败，请刷新后重试。</div> : courses.length === 0 ? <div className="border border-dashed p-8 text-center text-sm text-muted-foreground">还没有课程。创建第一门课程后，课件会自动按课程分目录保存。</div> : <div className="grid gap-3 sm:grid-cols-2">{courses.map((course) => editingId === course.id ? <form key={course.id} onSubmit={saveEdit} className="border bg-card p-4"><label className="block text-sm font-medium">课程名称<input value={editTitle} onChange={(e) => setEditTitle(e.target.value)} className="mt-2" maxLength={160} autoFocus /></label><label className="mt-3 block text-sm font-medium">课程说明<textarea value={editDescription} onChange={(e) => setEditDescription(e.target.value)} className="mt-2 min-h-20 resize-y" maxLength={1000} /></label><div className="mt-4 flex gap-2"><button type="submit" className="inline-flex items-center gap-1 bg-primary px-3 py-2 text-sm text-primary-foreground"><Save size={14} />保存</button><button type="button" onClick={cancelEdit} className="inline-flex items-center gap-1 border px-3 py-2 text-sm"><X size={14} />取消</button></div></form> : <CourseCard key={course.id} course={course} onDelete={handleDelete} onEdit={startEdit} />)}</div>}
        </section>
      </section>
    </div>
  )
}

function CourseCard({ course, onDelete, onEdit }: { course: Course; onDelete: (course: Course) => void; onEdit: (course: Course) => void }) {
  return (
    <article className="flex min-h-48 flex-col border bg-card p-4">
      <div className="mb-3 flex items-start justify-between gap-3"><div className="min-w-0"><h3 className="truncate text-lg font-semibold">{course.title}</h3><p className="mt-1 line-clamp-2 min-h-10 text-sm text-muted-foreground">{course.description || "未填写课程说明"}</p></div><div className="flex shrink-0 gap-1"><button type="button" onClick={() => onEdit(course)} className="inline-flex h-8 w-8 items-center justify-center border text-muted-foreground hover:bg-secondary" title="编辑课程" aria-label={`编辑课程 ${course.title}`}><Pencil size={14} /></button><button type="button" onClick={() => onDelete(course)} className="inline-flex h-8 w-8 items-center justify-center border text-muted-foreground hover:bg-destructive hover:text-destructive-foreground" title="删除课程" aria-label={`删除课程 ${course.title}`}><Trash2 size={14} /></button></div></div>
      <div className="mt-auto grid grid-cols-2 gap-2 border-t pt-3 text-xs text-muted-foreground"><span><strong className="text-foreground">{course.courseware_count || 0}</strong> 个课件</span><span><strong className="text-foreground">{course.chapter_count || 0}</strong> 个章节</span></div>
      <Link to="/teacher/prepare" search={{ chapterId: "", nodeId: "", courseId: course.id }} className="mt-3 inline-flex items-center justify-center gap-2 border bg-secondary px-3 py-2 text-sm font-medium"><FolderOpen size={15} /> 打开备课</Link>
    </article>
  )
}
