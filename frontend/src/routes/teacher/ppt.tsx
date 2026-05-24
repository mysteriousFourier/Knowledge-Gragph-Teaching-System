import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"
import { FileText, Images, Library, Upload } from "lucide-react"
import { usePreviewPpt } from "@/api/education"
import { useTeacherChapters } from "@/api/teacher"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import type { PptSlideDetail } from "@/types/education"

export const Route = createFileRoute("/teacher/ppt")({
  component: TeacherPptPage,
})

function TeacherPptPage() {
  const { data: chaptersData, isLoading } = useTeacherChapters()
  const previewPpt = usePreviewPpt()
  const chapters = chaptersData?.chapters || []
  const pptChapters = useMemo(
    () => chapters.filter((chapter) => chapter.ppt_slides?.length || chapter.lecture_content?.trim()),
    [chapters],
  )
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [selectedSlideIndex, setSelectedSlideIndex] = useState(0)
  const [importedPptTitle, setImportedPptTitle] = useState("")
  const [importedSlides, setImportedSlides] = useState<PptSlideDetail[]>([])

  const selectedChapter =
    pptChapters.find((chapter) => chapter.id === selectedChapterId) || pptChapters[0]
  const slides = importedSlides.length ? importedSlides : selectedChapter?.ppt_slides || []
  const selectedSlide = slides[selectedSlideIndex] || slides[0]
  const selectedLecture = selectedSlide
    ? selectedChapter?.slide_lectures?.find((item) => item.index === selectedSlide.index)
    : undefined
  const lectureContent = selectedLecture?.lecture || selectedChapter?.lecture_content || ""

  const handleSelectChapter = (chapterId: string) => {
    setSelectedChapterId(chapterId)
    setSelectedSlideIndex(0)
    setImportedPptTitle("")
    setImportedSlides([])
  }

  const handleImportPpt = async (file: File | undefined) => {
    if (!file) return
    const result = await previewPpt.mutateAsync(file)
    setImportedSlides(result.slides || [])
    setImportedPptTitle(result.chapter_title || file.name)
    setSelectedSlideIndex(0)
  }

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })
  }

  return (
    <div className="relative space-y-8">
      <PptIndex onJump={scrollToSection} />

      <section id="ppt-generate" className="scroll-mt-6 rounded-xl border bg-card">
        <div className="border-b p-4">
          <h1 className="text-2xl font-bold">PPT 生成</h1>
        </div>
        <div className="overflow-hidden">
          <iframe
            title="LaTeX Beamer 生成器"
            src="/beamer-generator/index.html?v=20260524-callout-math-fix-v31"
            className="h-[calc(100vh-120px)] min-h-[900px] w-full border-0"
          />
        </div>
      </section>

      <section id="ppt-display" className="scroll-mt-6 rounded-xl border bg-card">
        <div className="flex flex-col gap-3 border-b p-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-2xl font-bold">PPT 展示</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Library size={16} className="text-muted-foreground" />
            <select
              value={selectedChapter?.id || ""}
              onChange={(event) => handleSelectChapter(event.target.value)}
              className="min-w-[260px] rounded-lg border bg-background px-3 py-2 text-sm"
            >
              {pptChapters.length ? (
                pptChapters.map((chapter) => (
                  <option key={chapter.id} value={chapter.id}>
                    {chapter.title || chapter.id}
                  </option>
                ))
              ) : (
                <option value="">暂无已保存的 PPT 或授课文案</option>
              )}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-5 p-4 xl:grid-cols-[minmax(320px,0.85fr)_minmax(0,1.15fr)]">
          <section className="rounded-lg border bg-background">
            <div className="flex items-center gap-2 border-b px-4 py-3 font-semibold">
              <FileText size={17} />
              对应文案展示栏
            </div>
            <div className="max-h-[620px] overflow-y-auto p-4">
              {isLoading ? (
                <LoadingSpinner text="正在读取已保存内容..." />
              ) : lectureContent.trim() ? (
                <RichTextContent content={lectureContent} />
              ) : (
                <EmptyPanel text="该章节暂无授课文案" />
              )}
            </div>
          </section>

          <section className="rounded-lg border bg-background">
            <div className="flex flex-col gap-3 border-b px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-2 font-semibold">
                <Images size={17} />
                PPT 预览栏
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex min-h-10 cursor-pointer items-center gap-2 border bg-card px-3 py-2 text-sm font-medium hover:bg-secondary">
                  {previewPpt.isPending ? <LoadingSpinner size={15} /> : <Upload size={15} />}
                  <span>{previewPpt.isPending ? "导入中..." : "导入本地 PPT"}</span>
                  <input
                    type="file"
                    accept=".ppt,.pptx,application/vnd.ms-powerpoint,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                    className="hidden"
                    disabled={previewPpt.isPending}
                    onChange={(event) => {
                      const file = event.target.files?.[0]
                      event.target.value = ""
                      void handleImportPpt(file)
                    }}
                  />
                </label>
                {slides.length ? (
                  <select
                    value={selectedSlide?.index || slides[0]?.index || 1}
                    onChange={(event) => {
                      const next = slides.findIndex((slide) => slide.index === Number(event.target.value))
                      setSelectedSlideIndex(next >= 0 ? next : 0)
                    }}
                    className="rounded-lg border bg-card px-3 py-2 text-sm"
                  >
                    {slides.map((slide, index) => (
                      <option key={slide.index} value={slide.index}>
                        第 {index + 1} 页：{slide.title || "无标题"}
                      </option>
                    ))}
                  </select>
                ) : null}
              </div>
            </div>
            <div className="p-4">
              {importedPptTitle ? (
                <div className="mb-3 border bg-card px-3 py-2 text-xs text-muted-foreground">
                  当前预览：{importedPptTitle}
                </div>
              ) : null}
              {previewPpt.error ? (
                <div className="mb-3 border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                  导入失败：{previewPpt.error instanceof Error ? previewPpt.error.message : "请检查 PPT 文件"}
                </div>
              ) : null}
              {isLoading ? (
                <LoadingSpinner text="正在读取 PPT 预览..." />
              ) : selectedSlide ? (
                <PptSlidePreview slide={selectedSlide} />
              ) : (
                <EmptyPanel text="该章节暂无已保存 PPT 预览" />
              )}
            </div>
          </section>
        </div>
      </section>
    </div>
  )
}

function PptIndex({ onJump }: { onJump: (id: string) => void }) {
  return (
    <div className="ppt-section-index">
      <button type="button" className="ppt-section-index-trigger" aria-label="PPT 索引">
        &lt;&lt;
      </button>
      <div className="ppt-section-index-menu">
        <button type="button" onClick={() => onJump("ppt-generate")} className="ppt-section-index-item">
          PPT 生成
        </button>
        <button type="button" onClick={() => onJump("ppt-display")} className="ppt-section-index-item">
          PPT 展示
        </button>
      </div>
    </div>
  )
}

function PptSlidePreview({ slide }: { slide: PptSlideDetail }) {
  const bodyTexts = [
    slide.content,
    ...(slide.body_texts || []),
    slide.raw_text,
  ].filter(Boolean)

  return (
    <div className="space-y-4">
      <div className="aspect-video overflow-hidden rounded-lg border bg-white p-5 shadow-sm">
        <div className="mb-4 border-b pb-3 text-lg font-semibold">{slide.title || "无标题"}</div>
        {bodyTexts.length ? (
          <div className="space-y-2 text-sm leading-6 text-slate-700">
            {bodyTexts.slice(0, 5).map((text, index) => (
              <p key={index} className="whitespace-pre-wrap">
                {text}
              </p>
            ))}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            本页暂无文本内容
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground sm:grid-cols-4">
        <InfoPill label="页码" value={String(slide.index)} />
        <InfoPill label="图片" value={String(slide.image_count || slide.images?.length || 0)} />
        <InfoPill label="表格" value={String(slide.tables?.length || 0)} />
        <InfoPill label="备注" value={slide.notes ? "有" : "无"} />
      </div>
      {slide.notes ? (
        <pre className="max-h-36 overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm">
          {slide.notes}
        </pre>
      ) : null}
    </div>
  )
}

function InfoPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-card px-3 py-2">
      <div>{label}</div>
      <div className="mt-1 font-semibold text-foreground">{value}</div>
    </div>
  )
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="py-12 text-center text-sm text-muted-foreground">{text}</div>
}
