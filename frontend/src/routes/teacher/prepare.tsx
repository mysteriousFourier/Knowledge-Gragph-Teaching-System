import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { BookOpen, FileUp, Network, Save, Wand2 } from "lucide-react"
import { useGenerateLecture, useUploadGraph } from "@/api/education"
import { useSaveChapter, useSaveLecture, useTeacherChapters } from "@/api/teacher"
import { LectureReviewPanel } from "@/components/common/LectureReviewPanel"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
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
  const [chapterTitle, setChapterTitle] = useState("")
  const [chapterContent, setChapterContent] = useState("")
  const [titleEdited, setTitleEdited] = useState(false)
  const [graphContentFallback, setGraphContentFallback] = useState("")
  const [generatedContent, setGeneratedContent] = useState("")
  const [learningPlan, setLearningPlan] = useState<unknown>(null)
  const [consistencyReport, setConsistencyReport] = useState<ConsistencyReport | null>(null)
  const [uploadResult, setUploadResult] = useState<UploadGraphResponse | null>(null)
  const [uploadError, setUploadError] = useState("")
  const [generateError, setGenerateError] = useState("")
  const [style, setStyle] = useState("引导式教学")
  const [length, setLength] = useState("中等")

  const generateLecture = useGenerateLecture()
  const uploadGraph = useUploadGraph()
  const saveChapter = useSaveChapter()
  const saveLecture = useSaveLecture()
  const { data: chaptersData } = useTeacherChapters()

  const effectiveChapterContent = chapterContent.trim() || graphContentFallback
  const previewContent = generatedContent || chapterContent
  const lectureStatusText = generateLecture.isPending ? "正在生成" : generatedContent ? "已生成" : chapterContent ? "已导入 Markdown" : "未生成"

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
  }, [chapterId, chaptersData?.chapters])

  const handleGenerate = async () => {
    if (!effectiveChapterContent.trim()) return
    setGenerateError("")
    try {
      const result = await generateLecture.mutateAsync({
        chapter_id: activeChapterId || chapterId || `chapter_${Date.now()}`,
        chapter_title: chapterTitle.trim(),
        chapter_content: effectiveChapterContent,
        style,
        length,
      })
      if (result.success && (result.lecture_content || result.content)) {
        if (result.chapter_id) setActiveChapterId(result.chapter_id)
        if (result.chapter_title && !titleEdited) setChapterTitle(result.chapter_title)
        setGeneratedContent(result.lecture_content || result.content || "")
        setLearningPlan(result.learning_plan || null)
        setConsistencyReport(result.consistency_report || null)
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
        const markdownContent = result.markdown_content || result.chapter_hint?.content || ""
        if (markdownContent.trim()) {
          setChapterContent(markdownContent)
          if (!titleEdited) setChapterTitle(result.chapter_hint?.title || inferChapterTitle(markdownContent))
        }
        setGeneratedContent("")
        setGraphContentFallback(markdownContent || `请基于已导入的知识图谱生成授课文案。图谱文件：${result.file_name || file.name}`)
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["graph-data"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-nodes"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-relationships"] }),
        queryClient.invalidateQueries({ queryKey: ["graph-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["education-graph"] }),
      ])
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Markdown 知识图谱文件导入失败")
    }
  }

  const persistCurrentLecture = async () => {
    const titleForSave = chapterTitle.trim() || "授课文案"
    const chapterIdForSave = activeChapterId || chapterId || `chapter_${Date.now()}`
    const chapterResult = await saveChapter.mutateAsync({
      chapter_id: chapterIdForSave,
      title: titleForSave,
      content: chapterContent,
    })
    const savedChapterId = chapterResult.chapter?.id || chapterResult.chapter_id || chapterIdForSave
    setActiveChapterId(savedChapterId)
    if (!chapterTitle.trim()) setChapterTitle(titleForSave)
    if (generatedContent.trim()) {
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

  const handleSave = async () => {
    if (!chapterTitle.trim()) return
    await persistCurrentLecture()
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">备课模式</h1>
        <p className="text-muted-foreground">通过 Markdown 知识图谱文件导入内容，生成可检查的授课文案</p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <GraphUploadPanel isPending={uploadGraph.isPending} result={uploadResult} error={uploadError} onUpload={handleGraphUpload} />

          <div className="rounded-lg border bg-card p-4">
            <label className="mb-2 block text-sm font-medium">章节标题</label>
            <input
              value={chapterTitle}
              onChange={(event) => {
                setTitleEdited(true)
                setChapterTitle(event.target.value)
              }}
              placeholder="可选；留空时会从 Markdown 标题中推断"
              className="w-full rounded-lg border bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="rounded-lg border bg-card p-4">
            <label className="mb-2 block text-sm font-medium">Markdown 知识图谱内容</label>
            <textarea
              value={chapterContent}
              onChange={(event) => {
                const nextContent = event.target.value
                setChapterContent(nextContent)
                setGeneratedContent("")
                if (!titleEdited) setChapterTitle(inferChapterTitle(nextContent))
              }}
              placeholder="导入 .md/.markdown 知识图谱文件后，内容会显示在这里。"
              className="min-h-[220px] w-full resize-y rounded-lg border bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>

          <div className="rounded-lg border bg-card p-4">
            <h3 className="mb-3 flex items-center gap-2 font-medium">
              <Wand2 size={18} />
              生成选项
            </h3>
            <div className="space-y-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="text-xs font-medium">
                  教学风格
                  <select value={style} onChange={(event) => setStyle(event.target.value)} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm">
                    <option value="引导式教学">引导式教学</option>
                    <option value="讲授式教学">讲授式教学</option>
                    <option value="探究式教学">探究式教学</option>
                  </select>
                </label>
                <label className="text-xs font-medium">
                  文案长度
                  <select value={length} onChange={(event) => setLength(event.target.value)} className="mt-1 w-full rounded-lg border bg-background px-3 py-2 text-sm">
                    <option value="简短">简短</option>
                    <option value="中等">中等</option>
                    <option value="详细">详细</option>
                  </select>
                </label>
              </div>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={!effectiveChapterContent.trim() || generateLecture.isPending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {generateLecture.isPending ? <LoadingSpinner size={16} /> : <Wand2 size={16} />}
                {generateLecture.isPending ? "生成中..." : "生成授课文案"}
              </button>
              {generateError && <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{generateError}</div>}
            </div>
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
          <section className="relative rounded-lg border bg-card">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
              <h2 className="flex items-center gap-2 font-semibold">
                <BookOpen size={18} />
                内容预览
              </h2>
              <span className="text-xs text-muted-foreground">状态：{lectureStatusText}</span>
            </div>
            <div className="p-4">
              {generateLecture.isPending ? (
                <div className="py-12">
                  <LoadingSpinner text="正在生成授课文案，请稍候..." />
                </div>
              ) : previewContent ? (
                <RichTextContent content={previewContent} />
              ) : (
                <div className="py-12 text-center text-muted-foreground">
                  <FileUp size={48} className="mx-auto mb-4 opacity-50" />
                  <p>导入 Markdown 知识图谱文件后，会在这里展示可阅读内容</p>
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
        导入知识图谱文件
      </div>
      <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-background px-4 py-5 text-center text-sm text-muted-foreground hover:border-primary hover:text-foreground sm:flex-row sm:text-left">
        {isPending ? <LoadingSpinner size={16} /> : <FileUp size={16} />}
        <span>{isPending ? "导入中..." : "选择 .md / .markdown 知识图谱文件"}</span>
        <input
          type="file"
          accept=".md,.markdown,text/markdown,text/x-markdown"
          className="hidden"
          disabled={isPending}
          onChange={(event) => {
            onUpload(event.target.files?.[0])
            event.target.value = ""
          }}
        />
      </label>
      {result?.success && (
        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          已导入 {result.file_name}，解析节点 {result.parsed?.nodes ?? 0} 个、关系 {result.parsed?.relations ?? 0} 条。
        </div>
      )}
      {error && <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}
    </section>
  )
}
