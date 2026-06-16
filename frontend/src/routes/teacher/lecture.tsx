import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useEffect, useMemo, useState } from "react"
import { BookOpen, ChevronLeft, ChevronRight, Edit3, Eye, Pause, Play, RotateCcw, Save, Trash2, X } from "lucide-react"
import { useDeleteChapter, useSaveLecture, useTeacherChapters } from "@/api/teacher"
import { EvidenceSummary } from "@/components/common/EvidenceSummary"
import { LectureReviewPanel } from "@/components/common/LectureReviewPanel"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { PlaybackProgress } from "@/components/common/PlaybackProgress"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { useLecturePlayback } from "@/hooks/useLecturePlayback"
import { cn } from "@/lib/utils"
import type { Chapter } from "@/types/chapter"
import type { CoursewareAsset, EditableSlideObject, PptSlideDetail } from "@/types/education"

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
  const slideLectures = selectedChapter?.slide_lectures || []
  const lectureContent = isEditing ? draftContent : selectedChapter?.lecture_content || ""
  const coursewareSlides = useMemo(() => buildLectureSlides(selectedChapter), [selectedChapter])
  const markdownSlides = lectureContent.trim() ? [lectureContent] : []
  const isCoursewareChapter = !isEditing && coursewareSlides.length > 0
  const segmentCount = isCoursewareChapter ? coursewareSlides.length : markdownSlides.length
  const playback = useLecturePlayback({
    segmentCount,
    chapterId: selectedChapter?.id,
    getSegmentId: (segment) => {
      if (isCoursewareChapter) {
        const slide = coursewareSlides[segment]
        return slide ? `slide-${slide.index}` : `slide-${segment + 1}`
      }
      return "lecture"
    },
    getSegmentText: (segment) => {
      if (isCoursewareChapter) {
        const slide = coursewareSlides[segment]
        const lecture = slideLectures.find((item) => item.index === slide?.index && item.lecture?.trim())
        return lecture?.lecture || slide?.notes || slide?.content || slide?.raw_text || ""
      }
      return markdownSlides[segment] || ""
    },
    getSegmentSpeechCues: (segment) => {
      if (!isCoursewareChapter) return undefined
      const slide = coursewareSlides[segment]
      return slideLectures.find((item) => item.index === slide?.index && item.lecture?.trim())?.speech_cues
    },
  })
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

  const currentCoursewareSlide = coursewareSlides[currentSlide]
  const currentSlideLecture = useMemo(() => {
    if (!slideLectures.length || !currentCoursewareSlide) return undefined
    return slideLectures.find((item) => item.index === currentCoursewareSlide.index && item.lecture?.trim())
  }, [currentCoursewareSlide, slideLectures])

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
    if (!selectedChapter || !window.confirm(`删除课程「${selectedChapter.title}」？`)) return
    const result = await deleteChapter.mutateAsync(selectedChapter.id)
    if (!result.success) {
      window.alert(result.error || "删除失败")
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
        <label className="block text-sm font-medium mb-2">选择课程</label>
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
            <option value="">-- 请选择课程 --</option>
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
                    删除
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
                    删除
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
                    {playback.isPlaying || playback.isLoadingAudio ? <Pause size={14} /> : <Play size={14} />}
                    {playback.isPlaying || playback.isLoadingAudio ? "暂停" : "播放"}
                  </button>
                  <button
                    onClick={() => playback.replay(currentSlide)}
                    disabled={!playback.hasSegments}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border hover:bg-accent disabled:opacity-50 transition-colors"
                    title={playback.providerLabel}
                  >
                    <RotateCcw size={14} />
                    重播当前页
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
          ) : isCoursewareChapter && coursewareSlides.length ? (
            <>
              <PlaybackProgress progress={playback.progress} statusText={playback.statusText} />
              <div className="grid gap-0 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
                <div className="border-b p-4 xl:border-b-0 xl:border-r xl:p-5">
                  {currentCoursewareSlide ? (
                    <PptSlidePreview slide={currentCoursewareSlide} assetMap={selectedChapter.asset_map || selectedChapter.editable_model?.assets || {}} />
                  ) : (
                    <EmptyState title="暂无页面" description="该课件缺少页面预览数据。" />
                  )}
                </div>
                <div className="p-4 xl:p-5">
                  {currentSlideLecture?.lecture ? (
                    <RichTextContent content={currentSlideLecture.lecture} />
                  ) : lectureContent.trim() ? (
                    <RichTextContent content={lectureContent} />
                  ) : (
                    <EmptyState title="暂无本页讲稿" description="左侧可先浏览课件展示页；逐页讲稿可在备课工作台生成。" />
                  )}
                  {(currentSlideLecture?.learning_plan || currentSlideLecture?.sources?.length) && (
                    <div className="mt-4">
                      <EvidenceSummary
                        learningPlan={currentSlideLecture.learning_plan}
                        sources={currentSlideLecture.sources}
                      />
                    </div>
                  )}
                  <LectureReviewPanel
                    className="mt-4"
                    learningPlan={currentSlideLecture?.learning_plan}
                    sources={currentSlideLecture?.sources}
                    consistencyReport={currentSlideLecture?.consistency_report}
                  />
                </div>
              </div>

              <Pager
                current={currentSlide}
                total={coursewareSlides.length}
                onPrev={() => playback.setCurrentSegment((prev) => prev - 1)}
                onNext={() => playback.setCurrentSegment((prev) => prev + 1)}
              />
            </>
          ) : markdownSlides.length > 0 ? (
            <>
              <PlaybackProgress progress={playback.progress} statusText={playback.statusText} />
              <div className="min-h-[240px] p-4 sm:min-h-[300px] sm:p-6">
                <RichTextContent content={markdownSlides[currentSlide]} />
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
                description="该课程尚未生成授课文稿，请在备课工作台生成。"
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

function PptSlidePreview({ slide, assetMap = {} }: { slide: PptSlideDetail; assetMap?: Record<string, CoursewareAsset> }) {
  const images = hydrateSlideImages(slide, assetMap)
  const hasVisualContent = Boolean(slide.title || slide.content || slide.raw_text || images.length || slide.tables?.length)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">页面 {slide.index}</div>
        <div className="text-xs text-muted-foreground">{formatSlideKind(slide)}</div>
      </div>

      <div className="mx-auto w-full max-w-5xl">
        <div className="relative aspect-video overflow-hidden rounded-lg border bg-white text-slate-950 shadow-sm">
          <div className="absolute inset-x-0 top-0 h-1 bg-primary" />
          {hasVisualContent ? (
            <div className="flex h-full flex-col p-[4.8%]">
              <div className="min-h-[13%] border-b border-slate-200 pb-3">
                <h3 className="text-balance text-[clamp(1.15rem,2.2vw,2.45rem)] font-semibold leading-tight tracking-normal text-slate-950">
                  {slide.title || `第 ${slide.index} 页`}
                </h3>
              </div>
              <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 pt-4 lg:grid-cols-[minmax(0,1fr)_minmax(210px,0.42fr)]">
                <div className="min-h-0 overflow-hidden text-[clamp(0.82rem,1.12vw,1.08rem)] leading-relaxed text-slate-800">
                  <RichTextContent content={slide.content || slide.raw_text || "无正文文本"} className="lecture-slide-prose" />
                </div>
                {(images.length > 0 || !!slide.tables?.length) && (
                  <div className="min-h-0 space-y-3 overflow-hidden">
                    <SlideImageStrip images={images} />
                    <SlideTableStrip slide={slide} />
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center text-sm text-slate-500">该页暂无可展示内容</div>
          )}
        </div>
      </div>

      {slide.notes && (
        <section className="rounded-lg border bg-muted/35 p-3">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">备注</div>
          <div className="mt-2 text-sm">
            <RichTextContent content={slide.notes} />
          </div>
        </section>
      )}
    </div>
  )
}

function SlideImageStrip({ images }: { images: PptSlideDetail["images"] }) {
  if (!images?.length) return null
  return (
    <div className="grid h-full max-h-[250px] gap-2">
      {images.slice(0, 2).map((image, index) => (
        <figure key={`${image.source_path || image.tex_ref || index}-${index}`} className="min-h-0 overflow-hidden rounded border border-slate-200 bg-slate-50 p-1.5">
          {image.data_uri ? (
            <img src={image.data_uri} alt={image.source_path || `课件图片 ${index + 1}`} className="h-full max-h-48 w-full object-contain" />
          ) : (
            <div className="flex h-24 items-center justify-center px-2 text-center text-xs text-slate-500">
              {image.oversized ? "图片过大，未内嵌预览" : "图片无法预览"}
            </div>
          )}
        </figure>
      ))}
    </div>
  )
}

function SlideTableStrip({ slide }: { slide: PptSlideDetail }) {
  if (!slide.tables?.length) return null
  return (
    <div className="max-h-44 overflow-hidden rounded border border-slate-200 bg-white text-[0.62rem] text-slate-700">
      {slide.tables[0].rows.slice(0, 5).map((row, rowIndex) => (
        <div key={rowIndex} className="grid grid-flow-col auto-cols-fr border-b border-slate-200 last:border-b-0">
          {row.slice(0, 4).map((cell, cellIndex) => (
            <div key={cellIndex} className="min-w-0 border-r border-slate-200 px-1.5 py-1 last:border-r-0">
              <RichTextContent content={cell} inline />
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function PptSlideImages({ slide }: { slide: PptSlideDetail }) {
  const images = slide.images || []
  if (!images.length) {
    return <div className="text-sm text-muted-foreground">图片数量：{slide.image_count || 0}</div>
  }

  return (
    <div>
      <div className="text-xs font-medium uppercase text-muted-foreground">图片</div>
      <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
        {images.map((image, index) => (
          <figure key={`${image.source_path || index}-${index}`} className="rounded-lg border bg-background p-2">
            {image.data_uri ? (
              <img
                src={image.data_uri}
                alt={image.source_path || `课件图片 ${index + 1}`}
                className="max-h-80 w-full rounded object-contain"
              />
            ) : (
              <div className="flex min-h-32 items-center justify-center rounded bg-muted px-3 text-center text-xs text-muted-foreground">
                {image.oversized ? "图片过大，未内嵌预览" : "图片无法预览"}
              </div>
            )}
            {image.source_path ? <figcaption className="mt-2 truncate text-xs text-muted-foreground">{image.source_path}</figcaption> : null}
          </figure>
        ))}
      </div>
    </div>
  )
}

function buildLectureSlides(chapter?: Chapter): PptSlideDetail[] {
  if (!chapter) return []
  if (chapter.ppt_slides?.length) return chapter.ppt_slides
  const editableSlides = chapter.editable_model?.slides || []
  if (editableSlides.length) {
    const assetMap = { ...(chapter.asset_map || {}), ...(chapter.editable_model?.assets || {}) }
    return editableSlides.map((slide, index) => slideFromEditableSlide(slide, index + 1, assetMap))
  }
  if (chapter.tex_content?.trim()) return parseTexSlides(chapter.tex_content)
  return []
}

function slideFromEditableSlide(
  slide: NonNullable<Chapter["editable_model"]>["slides"][number],
  fallbackIndex: number,
  assetMap: Record<string, CoursewareAsset>,
): PptSlideDetail {
  const objects = dedupeEditableObjects([...(slide.objects || []), ...(slide.items || [])])
  const titleObject = objects.find((item) => item.type === "title" || item.role === "title")
  const contentBlocks = objects
    .filter((item) => item !== titleObject && item.type !== "image" && item.type !== "placeholder")
    .map(formatEditableObject)
    .filter(Boolean)
  const imageObjects = objects.filter((item) => item.type === "image" || item.type === "placeholder")
  const images = imageObjects.map((object) => imageFromEditableObject(object, assetMap))
  const tables = objects.filter((item) => item.rows?.length).map((item) => ({ rows: item.rows || [] }))

  return {
    index: slide.index || fallbackIndex,
    title: slide.title || titleObject?.text || titleObject?.title || `第 ${slide.index || fallbackIndex} 页`,
    content: contentBlocks.join("\n\n"),
    notes: slide.notes,
    images,
    image_count: images.length,
    has_images: images.length > 0,
    tables,
    raw_text: contentBlocks.join("\n"),
    source_tex: slide.source_tex,
    source_body_tex: slide.source_body_tex,
    layout: slide.layout,
  }
}

function dedupeEditableObjects(objects: EditableSlideObject[]) {
  const seen = new Set<string>()
  return objects.filter((object, index) => {
    const key = object.id || `${object.type}-${index}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function formatEditableObject(object: EditableSlideObject) {
  if (object.type === "equation" || object.latex) return object.latex ? `$$\n${object.latex}\n$$` : ""
  if (object.rows?.length) return object.rows.map((row) => row.join(" | ")).join("\n")
  return String(object.text || object.rich_html || object.label || "").trim()
}

function imageFromEditableObject(object: EditableSlideObject, assetMap: Record<string, CoursewareAsset>): NonNullable<PptSlideDetail["images"]>[number] {
  const asset = object.asset_id ? assetMap[object.asset_id] : undefined
  return {
    data_uri: asset?.data_uri || null,
    width_emu: 0,
    height_emu: 0,
    left_emu: 0,
    top_emu: 0,
    source_path: object.source_path || asset?.source_path || asset?.name,
    tex_ref: object.tex_ref || asset?.tex_ref,
    width_ratio: object.width_ratio,
    oversized: asset?.oversized,
  }
}

function hydrateSlideImages(slide: PptSlideDetail, assetMap: Record<string, CoursewareAsset>) {
  const assets = Object.values(assetMap)
  return (slide.images || []).map((image) => {
    if (image.data_uri) return image
    const key = normalizeAssetKey(image.source_path || image.tex_ref || "")
    const asset = assets.find((candidate) => {
      const candidates = [candidate.id, candidate.source_path, candidate.tex_ref, candidate.name, ...(candidate.aliases || [])]
      return candidates.some((item) => normalizeAssetKey(item || "") === key)
    })
    return asset?.data_uri ? { ...image, data_uri: asset.data_uri, oversized: asset.oversized } : image
  })
}

function normalizeAssetKey(value: string) {
  return (
    String(value || "")
      .replace(/\\/g, "/")
      .split("/")
      .pop()
      ?.replace(/\.(png|jpe?g|gif|webp|bmp|svg)$/i, "")
      .toLowerCase()
      .trim() || ""
  )
}

function parseTexSlides(texContent: string): PptSlideDetail[] {
  const source = texContent.replace(/\r\n/g, "\n").replace(/\r/g, "\n")
  const frames = Array.from(source.matchAll(/\\begin\{frame\}([\s\S]*?)\\end\{frame\}/g))
  if (!frames.length) {
    const readable = texToReadableMarkdown(source)
    return readable ? [{ index: 1, title: "TeX 课件", content: readable, raw_text: readable, source_tex: source }] : []
  }
  return frames.map((match, index) => {
    const frameSource = match[0]
    const body = match[1] || ""
    const title = extractFrameTitle(frameSource) || `第 ${index + 1} 页`
    const content = texToReadableMarkdown(removeFrameTitle(body))
    return {
      index: index + 1,
      title,
      content,
      raw_text: content,
      source_tex: frameSource,
      source_body_tex: body,
    }
  })
}

function extractFrameTitle(frameSource: string) {
  const beginTitle = /\\begin\{frame\}(?:\s*(?:<[^>]*>|\[[^\]]*\]))*\s*\{([^{}]*)\}/.exec(frameSource)
  if (beginTitle?.[1]) return cleanTexInline(beginTitle[1])
  const frameTitle = /\\frametitle(?:\s*(?:<[^>]*>|\[[^\]]*\]))*\s*\{([^{}]*)\}/.exec(frameSource)
  if (frameTitle?.[1]) return cleanTexInline(frameTitle[1])
  return ""
}

function removeFrameTitle(value: string) {
  return value
    .replace(/^\s*(?:<[^>]*>|\[[^\]]*\])*\s*\{[^{}]*\}/, "")
    .replace(/\\frametitle(?:\s*(?:<[^>]*>|\[[^\]]*\]))*\s*\{[^{}]*\}/g, "")
}

function texToReadableMarkdown(value: string) {
  return value
    .replace(/%.*$/gm, "")
    .replace(/\\begin\{(?:itemize|enumerate)\}/g, "\n")
    .replace(/\\end\{(?:itemize|enumerate)\}/g, "\n")
    .replace(/\\item(?:<[^>]*>)?(?:\[[^\]]*\])?/g, "\n- ")
    .replace(/\\begin\{(?:equation|align|aligned|gather|split)\*?\}([\s\S]*?)\\end\{(?:equation|align|aligned|gather|split)\*?\}/g, (_match, formula) => `\n\n$$\n${formula.trim()}\n$$\n\n`)
    .replace(/\\\[((?:.|\n)*?)\\\]/g, (_match, formula) => `\n\n$$\n${formula.trim()}\n$$\n\n`)
    .replace(/\\\(((?:.|\n)*?)\\\)/g, (_match, formula) => `$${formula.trim()}$`)
    .replace(/\$\$([\s\S]*?)\$\$/g, (_match, formula) => `\n\n$$\n${formula.trim()}\n$$\n\n`)
    .replace(/\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}/g, "\n\n[图：$1]\n\n")
    .replace(/\\(textbf|textit|emph|alert)\{([^{}]*)\}/g, "$2")
    .replace(/\\(small|footnotesize|scriptsize|large|Large|centering|pause)\b/g, "")
    .replace(/\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{([^{}]*)\})?/g, (_match, inner) => inner || "")
    .replace(/[{}]/g, "")
    .split("\n")
    .map((line) => cleanTexInline(line).trim())
    .filter(Boolean)
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim()
}

function cleanTexInline(value: string) {
  return String(value || "")
    .replace(/\\&/g, "&")
    .replace(/\\%/g, "%")
    .replace(/\\_/g, "_")
    .replace(/\\#/g, "#")
    .replace(/~/g, " ")
    .trim()
}

function formatSlideKind(slide: PptSlideDetail) {
  const parts = []
  if (slide.images?.length || slide.image_count) parts.push(`${slide.images?.length || slide.image_count} 图`)
  if (slide.tables?.length) parts.push(`${slide.tables.length} 表`)
  if (slide.source_tex) parts.push("TeX")
  return parts.length ? parts.join(" · ") : "讲授展示"
}
