import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { BookOpen, FileUp, Network, Save, Wand2 } from "lucide-react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { useGenerateLecture, useUploadGraph } from "@/api/education"
import { useSaveChapter, useSaveLecture, useTeacherChapters } from "@/api/teacher"
import { LectureReviewPanel } from "@/components/common/LectureReviewPanel"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { generateLectureSchema, type GenerateLectureFormData } from "@/lib/validators"
import type { ConsistencyReport, UploadGraphResponse } from "@/types/education"

export const Route = createFileRoute("/teacher/prepare")({
  component: PreparePage,
  validateSearch: (search: Record<string, unknown>) => ({
    chapterId: typeof search.chapterId === "string" ? search.chapterId : "",
  }),
})

function PreparePage() {
  const { chapterId } = Route.useSearch()
  const queryClient = useQueryClient()
  const [activeChapterId, setActiveChapterId] = useState("")
  const [generatedContent, setGeneratedContent] = useState("")
  const [chapterContent, setChapterContent] = useState("")
  const [chapterTitle, setChapterTitle] = useState("")
  const [titleEdited, setTitleEdited] = useState(false)
  const [graphContentFallback, setGraphContentFallback] = useState("")
  const [consistencyReport, setConsistencyReport] = useState<ConsistencyReport | null>(null)
  const [learningPlan, setLearningPlan] = useState<unknown>(null)
  const [uploadResult, setUploadResult] = useState<UploadGraphResponse | null>(null)
  const [uploadError, setUploadError] = useState("")
  const [generateError, setGenerateError] = useState("")

  const generateLecture = useGenerateLecture()
  const uploadGraph = useUploadGraph()
  const { data: chaptersData } = useTeacherChapters()
  const saveChapter = useSaveChapter()
  const saveLecture = useSaveLecture()
  const lectureStatusText = generateLecture.isPending ? "正在生成" : generatedContent ? "已生成" : "未生成"
  const effectiveChapterContent = chapterContent.trim() || graphContentFallback
  const canGenerateLecture = !!effectiveChapterContent.trim()

  const { register, handleSubmit, setValue } = useForm<GenerateLectureFormData>({
    resolver: zodResolver(generateLectureSchema),
    defaultValues: {
      style: "引导式教学",
      length: "中等",
    },
  })

  useEffect(() => {
    if (!chapterId || !chaptersData?.chapters?.length) return
    const chapter = chaptersData.chapters.find((item) => item.id === chapterId)
    if (!chapter) return

    setActiveChapterId(chapter.id)
    setChapterTitle(chapter.title || "")
    setChapterContent(chapter.content || "")
    setGeneratedContent(chapter.lecture_content || "")
    setLearningPlan(chapter.lecture_learning_plan || null)
    setConsistencyReport(chapter.lecture_consistency_report || null)
    setTitleEdited(Boolean(chapter.title))
    setGraphContentFallback("")
    setGenerateError("")
    setValue("chapter_title", chapter.title || "", { shouldValidate: true })
    setValue("chapter_content", chapter.content || "", { shouldValidate: true })
  }, [chapterId, chaptersData?.chapters, setValue])

  const onGenerate = async (data: GenerateLectureFormData) => {
    const contentForGeneration = chapterContent.trim() || graphContentFallback
    setValue("chapter_content", contentForGeneration, { shouldValidate: true })
    setValue("chapter_title", chapterTitle, { shouldValidate: true })
    setGenerateError("")
    try {
      const result = await generateLecture.mutateAsync({
        ...data,
        chapter_id: activeChapterId || chapterId || `chapter_${Date.now()}`,
        chapter_content: contentForGeneration,
        chapter_title: chapterTitle.trim(),
      })
      if (result.success && (result.lecture_content || result.content)) {
        if (result.chapter_id) {
          setActiveChapterId(result.chapter_id)
        }
        if (result.chapter_title && !titleEdited) {
          setChapterTitle(result.chapter_title)
          setValue("chapter_title", result.chapter_title, { shouldValidate: true })
        }
        setGeneratedContent(result.lecture_content || result.content || "")
        setConsistencyReport(result.consistency_report || null)
        setLearningPlan(result.learning_plan || null)
      } else {
        setGenerateError(result.error || "生成接口未返回授课文案")
      }
    } catch (error) {
      setGenerateError(error instanceof Error ? error.message : "授课文案生成失败")
    }
  }

  const handleGraphUpload = async (file: File | undefined) => {
    if (!file) return
    setUploadError("")
    setUploadResult(null)
    try {
      const result = await uploadGraph.mutateAsync(file)
      setUploadResult(result)
      if (result.success) {
        const hintContent =
          result.chapter_hint?.content ||
          `请基于已导入的知识图谱生成授课文案。图谱文件：${result.file_name || file.name}`
        setGraphContentFallback(hintContent)
        setValue("chapter_content", chapterContent.trim() || hintContent, { shouldValidate: true })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["graph-data"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-nodes"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-relationships"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["education-graph"] }),
      ])
    } catch (error) {
      const message = error instanceof Error ? error.message : "图谱文件导入失败"
      setUploadError(message)
    }
  }

  const handleSave = async () => {
    if (!chapterTitle) return
    const chapterIdForSave = activeChapterId || chapterId || `chapter_${Date.now()}`
    const chapterResult = await saveChapter.mutateAsync({
      chapter_id: chapterIdForSave,
      title: chapterTitle,
      content: chapterContent,
    })
    const savedChapterId = chapterResult.chapter?.id || chapterResult.chapter_id || chapterIdForSave
    setActiveChapterId(savedChapterId)
    if (generatedContent) {
      await saveLecture.mutateAsync({
        chapter_id: savedChapterId,
        lecture_content: generatedContent,
        learning_plan: learningPlan,
        consistency_report: consistencyReport || undefined,
      })
    }
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
    ])
    window.alert("保存成功")
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">备课模式</h1>
        <p className="text-muted-foreground">导入章节内容和图谱文件，生成可检查的授课文案</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <GraphUploadPanel
            isPending={uploadGraph.isPending}
            result={uploadResult}
            error={uploadError}
            onUpload={handleGraphUpload}
          />

          <div className="rounded-lg border bg-card p-4">
            <label className="mb-2 block text-sm font-medium">章节标题</label>
            <input
              value={chapterTitle}
              onChange={(e) => {
                setTitleEdited(true)
                setChapterTitle(e.target.value)
                setValue("chapter_title", e.target.value, { shouldValidate: true })
              }}
              placeholder={graphContentFallback ? "可选；留空时 AI 会基于图谱生成标题" : "输入章节名称，或留空由 AI 生成"}
              className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="rounded-lg border bg-card p-4">
            <label className="mb-2 block text-sm font-medium">章节内容</label>
            <textarea
              value={chapterContent}
              onChange={(e) => {
                const nextContent = e.target.value
                setChapterContent(nextContent)
                setValue("chapter_content", nextContent.trim() || graphContentFallback, { shouldValidate: true })
                if (!titleEdited) {
                  const inferredTitle = inferChapterTitle(nextContent)
                  setChapterTitle(inferredTitle)
                  setValue("chapter_title", inferredTitle, { shouldValidate: true })
                }
              }}
              placeholder={graphContentFallback ? "可选：补充章节内容；留空也会基于已导入图谱生成" : "输入或粘贴章节内容..."}
              className="min-h-[220px] w-full resize-y rounded-lg border bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="rounded-lg border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 font-medium">
              <Wand2 size={18} />
              生成选项
            </h3>
            <form onSubmit={handleSubmit(onGenerate)} className="space-y-3">
              <input type="hidden" {...register("chapter_content")} value={effectiveChapterContent} />
              <input type="hidden" {...register("chapter_title")} value={chapterTitle} />

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-medium">教学风格</label>
                  <select {...register("style")} className="w-full rounded-lg border bg-background px-3 py-2 text-sm">
                    <option value="引导式教学">引导式教学</option>
                    <option value="讲授式教学">讲授式教学</option>
                    <option value="探究式教学">探究式教学</option>
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium">文案长度</label>
                  <select {...register("length")} className="w-full rounded-lg border bg-background px-3 py-2 text-sm">
                    <option value="简短">简短</option>
                    <option value="中等">中等</option>
                    <option value="详细">详细</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                disabled={!canGenerateLecture || generateLecture.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {generateLecture.isPending ? (
                  <>
                    <LoadingSpinner size={16} />
                    生成中...
                  </>
                ) : (
                  <>
                    <Wand2 size={16} />
                    生成授课文案
                  </>
                )}
              </button>
              {generateError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
                  {generateError}
                </div>
              )}
            </form>
          </div>

          <button
            onClick={handleSave}
            disabled={!chapterTitle.trim() || saveChapter.isPending}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-secondary py-2.5 text-sm font-medium text-secondary-foreground hover:bg-secondary/90 disabled:opacity-50"
          >
            <Save size={16} />
            {saveChapter.isPending ? "保存中..." : "保存章节"}
          </button>
        </div>

        <div className="space-y-4">
          <section className="rounded-lg border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
              <h2 className="flex items-center gap-2 font-semibold">
                <BookOpen size={18} />
                授课文案预览
              </h2>
              <span className="text-xs text-muted-foreground">状态：{lectureStatusText}</span>
            </div>
            <div className="p-4">
              {generateLecture.isPending ? (
                <div className="py-12">
                  <LoadingSpinner text="正在生成授课文案，请稍候..." />
                </div>
              ) : generatedContent ? (
                <RichTextContent content={generatedContent} />
              ) : (
                <div className="py-12 text-center text-muted-foreground">
                  <FileUp size={48} className="mx-auto mb-4 opacity-50" />
                  <p>当前没有生成授课文案</p>
                </div>
              )}
            </div>
          </section>

          <LectureReviewPanel learningPlan={learningPlan} consistencyReport={consistencyReport || undefined} />
        </div>
      </div>
    </div>
  )
}

function inferChapterTitle(content: string) {
  const firstLine = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean)

  if (!firstLine) return ""
  return firstLine.replace(/^#+\s*/, "").slice(0, 60)
}

function GraphUploadPanel({
  isPending,
  result,
  error,
  onUpload,
}: {
  isPending: boolean
  result: UploadGraphResponse | null
  error: string
  onUpload: (file: File | undefined) => void
}) {
  return (
    <section className="rounded-lg border bg-card p-4">
      <div className="mb-3 flex items-center gap-2 font-medium">
        <Network size={18} />
        导入图谱文件
      </div>
      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-background px-4 py-5 text-center text-sm text-muted-foreground hover:border-primary hover:text-foreground sm:flex-row sm:text-left">
        {isPending ? <LoadingSpinner size={16} /> : <FileUp size={16} />}
        <span>{isPending ? "导入中..." : "选择 JSON / GraphML / SQLite 图谱文件"}</span>
        <input
          type="file"
          accept=".json,.graphml,.xml,.db,.sqlite,.sqlite3,application/json,text/xml,application/xml,application/vnd.sqlite3,application/x-sqlite3"
          className="hidden"
          disabled={isPending}
          onChange={(event) => onUpload(event.target.files?.[0])}
        />
      </label>
      {result?.success && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          已导入 {result.file_name}，解析节点 {result.parsed?.nodes ?? 0} 个、关系 {result.parsed?.relations ?? 0} 条。
        </div>
      )}
      {error && (
        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}
    </section>
  )
}
