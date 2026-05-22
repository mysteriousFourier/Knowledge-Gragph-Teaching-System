import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { BookOpen, ChevronLeft, ChevronRight, Edit3, Eye, Pause, Play, Save, Trash2, X } from "lucide-react"
import { useDeleteChapter, useSaveLecture, useTeacherChapters } from "@/api/teacher"
import { EvidenceSummary } from "@/components/common/EvidenceSummary"
import { LectureReviewPanel } from "@/components/common/LectureReviewPanel"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { useLecturePlayback } from "@/hooks/useLecturePlayback"
import { cn } from "@/lib/utils"
import type { PptSlideDetail } from "@/types/education"

export const Route = createFileRoute("/teacher/lecture")({
  component: LecturePage,
  validateSearch: (search: Record<string, unknown>) => ({
    chapterId: typeof search.chapterId === "string" ? search.chapterId : "",
  }),
})

function LecturePage() {
  const { chapterId } = Route.useSearch()
  const queryClient = useQueryClient()
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [isEditing, setIsEditing] = useState(false)
  const [editorMode, setEditorMode] = useState<"edit" | "preview">("edit")
  const [draftContent, setDraftContent] = useState("")
  const [saveMessage, setSaveMessage] = useState("")

  const { data: chaptersData, isLoading } = useTeacherChapters()
  const saveLecture = useSaveLecture()
  const deleteChapter = useDeleteChapter()
  const chapters = chaptersData?.chapters || []
  const selectedChapter = chapters.find((chapter) => chapter.id === selectedChapterId)
  const lectureContent = isEditing ? draftContent : selectedChapter?.lecture_content || ""
  const markdownSlides = lectureContent.trim() ? [lectureContent] : []
  const isPptChapter = !isEditing && selectedChapter?.source_type === "ppt" && !!selectedChapter.ppt_slides?.length
  const segmentCount = isPptChapter ? selectedChapter?.ppt_slides?.length || 0 : markdownSlides.length
  const playback = useLecturePlayback({ segmentCount })
  const currentSlide = playback.currentSegment

  useEffect(() => {
    playback.reset(0)
  }, [selectedChapterId, isEditing, editorMode])

  useEffect(() => {
    if (!chapters.length || selectedChapterId) return
    const fromSearch = chapterId ? chapters.find((chapter) => chapter.id === chapterId) : undefined
    const withLecture = chapters.find((chapter) => !!chapter.lecture_content)
    setSelectedChapterId((fromSearch || withLecture || chapters[0]).id)
  }, [chapterId, chapters, selectedChapterId])

  const currentPptSlide = selectedChapter?.ppt_slides?.[currentSlide]
  const currentPptLecture = useMemo(() => {
    if (!selectedChapter?.slide_lectures?.length || !currentPptSlide) return undefined
    return selectedChapter.slide_lectures.find((item) => item.index === currentPptSlide.index)
  }, [currentPptSlide, selectedChapter?.slide_lectures])

  const handleStartEdit = () => {
    setDraftContent(selectedChapter?.lecture_content || "")
    setIsEditing(true)
    setEditorMode("edit")
    playback.pause()
    setSaveMessage("")
  }

  const handleCancelEdit = () => {
    setDraftContent("")
    setIsEditing(false)
    setEditorMode("edit")
    setSaveMessage("")
    playback.reset(0)
  }

  const handleSave = async () => {
    if (!selectedChapter) return
    const result = await saveLecture.mutateAsync({
      chapter_id: selectedChapter.id,
      lecture_content: draftContent,
      learning_plan: selectedChapter.lecture_learning_plan,
    })
    if (result.success) {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
        queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
      ])
      setIsEditing(false)
      setEditorMode("edit")
      playback.reset(0)
      setSaveMessage("授课文案已保存")
    }
  }

  const handleDelete = async () => {
    if (!selectedChapter || !window.confirm(`Delete chapter "${selectedChapter.title}"?`)) return
    const result = await deleteChapter.mutateAsync(selectedChapter.id)
    if (!result.success) {
      window.alert(result.error || "Delete failed")
      return
    }
    setSelectedChapterId("")
    setDraftContent("")
    setIsEditing(false)
    setEditorMode("edit")
    setSaveMessage("")
    playback.reset(0)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-progress"] }),
    ])
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">授课模式</h1>
        <p className="text-muted-foreground">播放讲解内容</p>
      </div>

      <div className="bg-card border rounded-xl p-4">
        <label className="block text-sm font-medium mb-2">选择章节</label>
        {isLoading ? (
          <LoadingSpinner size={20} text="加载中..." />
        ) : (
          <select
            value={selectedChapterId}
            onChange={(event) => {
              setSelectedChapterId(event.target.value)
              playback.reset(0)
              setIsEditing(false)
              setEditorMode("edit")
              setDraftContent("")
              setSaveMessage("")
            }}
            className="w-full px-3 py-2.5 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
          >
            <option value="">-- 请选择章节 --</option>
            {chapters.map((chapter) => (
              <option key={chapter.id} value={chapter.id}>
                {chapter.title}
              </option>
            ))}
          </select>
        )}
      </div>

      {selectedChapter && (
        <div className="bg-card border rounded-xl">
          <div className="p-4 border-b flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="font-semibold">{selectedChapter.title}</h2>
              {saveMessage && <p className="mt-1 text-sm text-emerald-600">{saveMessage}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {isEditing ? (
                <>
                  <button
                    onClick={() => {
                      setEditorMode((mode) => (mode === "edit" ? "preview" : "edit"))
                      playback.reset(0)
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                  >
                    {editorMode === "edit" ? <Eye size={14} /> : <Edit3 size={14} />}
                    {editorMode === "edit" ? "预览" : "编辑"}
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saveLecture.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-green-100 text-green-700 hover:bg-green-200 disabled:opacity-50 transition-colors"
                  >
                    <Save size={14} />
                    {saveLecture.isPending ? "保存中..." : "保存"}
                  </button>
                  <button
                    onClick={handleCancelEdit}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-muted text-muted-foreground hover:bg-muted/80 transition-colors"
                  >
                    <X size={14} />
                    取消
                  </button>
                  <button
                    onClick={handleDelete}
                    disabled={deleteChapter.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                </>
              ) : (
                <>
                  <button
                    onClick={handleDelete}
                    disabled={deleteChapter.isPending}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border text-destructive hover:bg-destructive/10 disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                  <button
                    onClick={handleStartEdit}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-primary/10 text-primary hover:bg-primary/20 transition-colors"
                  >
                    <Edit3 size={14} />
                    编辑
                  </button>
                  <button
                    onClick={playback.toggle}
                    disabled={!playback.hasSegments}
                    className={cn(
                      "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50",
                      playback.isPlaying ? "bg-amber-100 text-amber-700 hover:bg-amber-200" : "bg-primary/10 text-primary hover:bg-primary/20"
                    )}
                    title={playback.providerLabel}
                  >
                    {playback.isPlaying ? <Pause size={14} /> : <Play size={14} />}
                    {playback.isPlaying ? "暂停" : "播放"}
                  </button>
                </>
              )}
            </div>
          </div>

          {isEditing && editorMode === "edit" ? (
            <div className="p-4 sm:p-6">
              <label className="mb-2 block text-sm font-medium">Markdown / LaTeX 原文</label>
              <textarea
                value={draftContent}
                onChange={(event) => {
                  setDraftContent(event.target.value)
                  playback.reset(0)
                }}
                placeholder="输入授课文案，支持 Markdown、$...$ 和 $$...$$ 公式"
                className="min-h-[300px] w-full resize-y rounded-lg border bg-background px-3 py-2.5 font-mono text-sm leading-relaxed focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 sm:min-h-[420px]"
              />
            </div>
          ) : isEditing && editorMode === "preview" ? (
            <div className="min-h-[240px] p-4 sm:min-h-[300px] sm:p-6">
              {draftContent.trim() ? (
                <RichTextContent content={draftContent} />
              ) : (
                <EmptyState title="暂无预览内容" description="请先在编辑模式输入授课文案。" icon={<BookOpen size={48} />} />
              )}
            </div>
          ) : isPptChapter && selectedChapter?.ppt_slides?.length ? (
            <>
              <div className="border-b px-4 py-2 text-sm text-muted-foreground">{playback.statusText}</div>
              <div className="grid grid-cols-1 gap-0 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
                <div className="border-b p-5 lg:border-b-0 lg:border-r">
                  {currentPptSlide ? <PptSlidePreview slide={currentPptSlide} /> : <EmptyState title="暂无幻灯片" description="该 PPT 章节缺少页面预览数据。" />}
                </div>
                <div className="p-5">
                  {currentPptLecture?.lecture ? (
                    <div className="prose prose-sm max-w-none dark:prose-invert">
                      <RichTextContent content={currentPptLecture.lecture} />
                    </div>
                  ) : (
                    <EmptyState title="暂无本页讲稿" description="该页没有保存逐页讲稿。" />
                  )}
                  {(currentPptLecture?.learning_plan || currentPptLecture?.sources?.length) && (
                    <div className="mt-4">
                      <EvidenceSummary
                        learningPlan={currentPptLecture.learning_plan}
                        sources={currentPptLecture.sources}
                      />
                    </div>
                  )}
                  <LectureReviewPanel
                    className="mt-4"
                    learningPlan={currentPptLecture?.learning_plan}
                    sources={currentPptLecture?.sources}
                    consistencyReport={currentPptLecture?.consistency_report}
                  />
                </div>
              </div>

              <Pager
                current={currentSlide}
                total={selectedChapter.ppt_slides.length}
                onPrev={() => playback.setCurrentSegment((prev) => prev - 1)}
                onNext={() => playback.setCurrentSegment((prev) => prev + 1)}
              />
            </>
          ) : markdownSlides.length > 0 ? (
            <>
              <div className="border-b px-4 py-2 text-sm text-muted-foreground">{playback.statusText}</div>
              <div className="min-h-[240px] p-4 sm:min-h-[300px] sm:p-6">
                <div className="prose prose-sm max-w-none dark:prose-invert">
                  <RichTextContent content={markdownSlides[currentSlide]} />
                </div>
                <LectureReviewPanel
                  className="mt-6"
                  learningPlan={selectedChapter.lecture_learning_plan}
                  consistencyReport={selectedChapter.lecture_consistency_report}
                />
              </div>

              <Pager
                current={currentSlide}
                total={markdownSlides.length}
                onPrev={() => playback.setCurrentSegment((prev) => prev - 1)}
                onNext={() => playback.setCurrentSegment((prev) => prev + 1)}
              />
            </>
          ) : (
            <div className="p-8">
              <EmptyState
                title="暂无授课文案"
                description="该章节尚未生成授课文稿，请在备课模式或PPT文案页面生成。"
                icon={<BookOpen size={48} />}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Pager({ current, total, onPrev, onNext }: { current: number; total: number; onPrev: () => void; onNext: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 border-t p-4">
      <button
        onClick={onPrev}
        disabled={current === 0}
        className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-sm hover:bg-muted disabled:opacity-50"
      >
        <ChevronLeft size={16} />
        上一页
      </button>
      <span className="text-sm text-muted-foreground">
        {current + 1} / {total}
      </span>
      <button
        onClick={onNext}
        disabled={current === total - 1}
        className="inline-flex items-center justify-center gap-1 px-3 py-1.5 rounded-lg text-sm hover:bg-muted disabled:opacity-50"
      >
        下一页
        <ChevronRight size={16} />
      </button>
    </div>
  )
}

function PptSlidePreview({ slide }: { slide: PptSlideDetail }) {
  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground">幻灯片 {slide.index}</div>
        <h3 className="mt-1 text-lg font-semibold">{slide.title || "无标题"}</h3>
      </div>
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground">页面文本</div>
        <pre className="mt-2 min-h-40 overflow-x-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm leading-relaxed">{slide.content || slide.raw_text || "无正文文本"}</pre>
      </div>
      {slide.notes && (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground">备注</div>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm">{slide.notes}</pre>
        </div>
      )}
      {!!slide.tables?.length && (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground">表格</div>
          <div className="mt-2 space-y-2">
            {slide.tables.map((table, index) => (
              <div key={index} className="overflow-x-auto rounded-lg border">
                {table.rows.map((row, rowIndex) => (
                  <div key={rowIndex} className="grid grid-flow-col auto-cols-fr border-b last:border-b-0">
                    {row.map((cell, cellIndex) => (
                      <div key={cellIndex} className="border-r px-2 py-1 text-sm last:border-r-0">
                        {cell}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
      <div className="text-sm text-muted-foreground">图片数量：{slide.image_count || 0}</div>
    </div>
  )
}
