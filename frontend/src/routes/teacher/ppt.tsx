import { createFileRoute } from "@tanstack/react-router"
import { useMemo, useState } from "react"
import { CheckCircle2, Clipboard, FileText, FileUp, Save, Wand2 } from "lucide-react"
import { useGeneratePptLectures, usePreviewPpt } from "@/api/education"
import { useSaveChapter, useSaveLecture } from "@/api/teacher"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import type { PptPreviewResponse, PptSlideDetail, PptSlideLecture } from "@/types/education"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/teacher/ppt")({
  component: TeacherPptPage,
})

function TeacherPptPage() {
  const [file, setFile] = useState<File | null>(null)
  const [style, setStyle] = useState("引导式教学")
  const [preview, setPreview] = useState<PptPreviewResponse | null>(null)
  const [slideLectures, setSlideLectures] = useState<PptSlideLecture[]>([])
  const [selectedIndex, setSelectedIndex] = useState(1)
  const [status, setStatus] = useState("")

  const previewPpt = usePreviewPpt()
  const generatePptLectures = useGeneratePptLectures()
  const saveChapter = useSaveChapter()
  const saveLecture = useSaveLecture()

  const selectedSlide = preview?.slides.find((slide) => slide.index === selectedIndex)
  const selectedLecture = slideLectures.find((lecture) => lecture.index === selectedIndex)
  const lectureStatusText = generatePptLectures.isPending ? "正在生成" : selectedLecture?.lecture ? "已生成" : "未生成"

  const mergedLecture = useMemo(
    () =>
      slideLectures
        .map((item) => {
          const title = item.title || `第 ${item.index} 页`
          const body = item.lecture?.trim() || "_本页未生成文案_"
          return `## 第 ${item.index} 页：${title}\n\n${body}`
        })
        .join("\n\n---\n\n"),
    [slideLectures]
  )

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return
    setFile(selectedFile)
    setSlideLectures([])
    setStatus("")
    const result = await previewPpt.mutateAsync(selectedFile)
    setPreview(result)
    setSelectedIndex(result.slides[0]?.index || 1)
  }

  const handleGenerate = async () => {
    if (!file) return
    setStatus("")
    const result = await generatePptLectures.mutateAsync({ file, style })
    setPreview({
      success: result.success,
      chapter_title: result.chapter_title,
      slide_count: result.slide_count,
      slides: result.slides,
      full_text: result.full_text,
      warning: result.warning,
      error: result.error,
    })
    setSlideLectures(result.slide_lectures || [])
    setSelectedIndex(result.slides[0]?.index || 1)
    if (!result.success && (result.message || result.error)) {
      setStatus(result.message || result.error || "")
    } else if (result.warning) {
      setStatus(result.warning)
    }
  }

  const handleSave = async () => {
    if (!preview || !mergedLecture.trim()) return
    const title = preview.chapter_title || file?.name.replace(/\.[^.]+$/, "") || "未命名PPT"
    const chapterId = `ppt_${Date.now()}`
    const chapterResult = await saveChapter.mutateAsync({
      chapter_id: chapterId,
      title,
      content: preview.full_text,
      source_type: "ppt",
      ppt_slides: preview.slides,
      slide_lectures: slideLectures,
    })
    const savedChapterId = chapterResult.chapter?.id || chapterResult.chapter_id || chapterId
    await saveLecture.mutateAsync({
      chapter_id: savedChapterId,
      lecture_content: mergedLecture,
      source_type: "ppt",
      ppt_slides: preview.slides,
      slide_lectures: slideLectures,
    })
    setStatus("已保存为章节授课文案")
  }

  const handleCopy = async () => {
    if (!selectedLecture?.lecture) return
    await navigator.clipboard.writeText(selectedLecture.lecture)
    setStatus("已复制当前页文案")
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold">PPT逐页文案</h1>
          <p className="text-muted-foreground">上传 PPT，按幻灯片生成可直接授课的讲解文案</p>
        </div>
        <div className="grid grid-cols-1 gap-2 sm:flex sm:flex-wrap">
          <label
            className="inline-flex cursor-pointer items-center gap-2 rounded-lg border bg-card px-3 py-2 text-sm font-medium hover:bg-accent"
          >
            <FileUp size={16} />
            选择PPT
            <input type="file" accept=".ppt,.pptx" onChange={handleFileChange} className="hidden" />
          </label>
          <select
            value={style}
            onChange={(event) => setStyle(event.target.value)}
            className="rounded-lg border bg-background px-3 py-2 text-sm"
          >
            <option value="引导式教学">引导式教学</option>
            <option value="讲授式教学">讲授式教学</option>
            <option value="探究式教学">探究式教学</option>
          </select>
          <button
            onClick={handleGenerate}
            disabled={!file || generatePptLectures.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {generatePptLectures.isPending ? (
              <>
                <LoadingSpinner size={16} />
                生成中...
              </>
            ) : (
              <>
                <Wand2 size={16} />
                生成逐页文案
              </>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={!preview || !mergedLecture.trim() || saveChapter.isPending || saveLecture.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-secondary px-3 py-2 text-sm font-medium text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50"
          >
            <Save size={16} />
            保存为章节
          </button>
        </div>
      </div>

      {status && (
        <div className="flex items-center gap-2 rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground">
          <CheckCircle2 size={16} className="text-primary" />
          {status}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_minmax(0,1fr)_minmax(320px,0.9fr)]">
        <aside className="rounded-xl border bg-card p-3">
          <div className="mb-3 flex items-center gap-2 px-1 text-sm font-semibold">
            <FileText size={16} />
            幻灯片
          </div>
          {previewPpt.isPending ? (
            <LoadingSpinner text="解析PPT中..." />
          ) : preview?.slides.length ? (
            <div className="space-y-2">
              {preview.slides.map((slide) => (
                <button
                  key={slide.index}
                  onClick={() => setSelectedIndex(slide.index)}
                  className={cn(
                    "w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                    selectedIndex === slide.index ? "border-primary bg-primary/10 text-primary" : "hover:bg-accent"
                  )}
                >
                  <div className="font-medium">第 {slide.index} 页</div>
                  <div className="truncate text-xs text-muted-foreground">{slide.title || "无标题"}</div>
                </button>
              ))}
            </div>
          ) : (
            <div className="py-10 text-center text-sm text-muted-foreground">请选择 PPT 文件</div>
          )}
        </aside>

        <section className="rounded-xl border bg-card">
          <div className="border-b p-4">
            <h2 className="font-semibold">页面内容预览</h2>
          </div>
          <div className="space-y-4 p-4">
            {selectedSlide ? <SlidePreview slide={selectedSlide} /> : <EmptyPanel text="暂无页面内容" />}
          </div>
        </section>

        <section className="rounded-xl border bg-card">
          <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-semibold">对应文案</h2>
              <span className="text-xs text-muted-foreground">状态：{lectureStatusText}</span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {preview?.slides.length ? (
                <span className="text-xs text-muted-foreground">
                  第 {selectedIndex} / {preview.slides.length} 页
                </span>
              ) : null}
              <button
                onClick={handleCopy}
                disabled={!selectedLecture?.lecture}
                className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-sm text-muted-foreground hover:bg-accent disabled:opacity-50"
              >
                <Clipboard size={15} />
                复制
              </button>
            </div>
          </div>
          <div className="p-4">
            {generatePptLectures.isPending ? (
              <LoadingSpinner text="生成逐页文案中..." />
            ) : selectedLecture?.lecture ? (
              <RichTextContent content={selectedLecture.lecture} />
            ) : (
              <EmptyPanel text="生成后将在这里显示当前页文案" />
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

function SlidePreview({ slide }: { slide: PptSlideDetail }) {
  return (
    <>
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground">标题</div>
        <div className="mt-1 font-semibold">{slide.title || "无标题"}</div>
      </div>
      <div>
        <div className="text-xs font-medium uppercase text-muted-foreground">正文</div>
        <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm">{slide.content || "无正文文本"}</pre>
      </div>
      {slide.notes && (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground">备注</div>
          <pre className="mt-1 whitespace-pre-wrap rounded-lg bg-muted p-3 text-sm">{slide.notes}</pre>
        </div>
      )}
      {slide.tables?.length ? (
        <div>
          <div className="text-xs font-medium uppercase text-muted-foreground">表格</div>
          <div className="mt-2 space-y-2">
            {slide.tables.map((table, index) => (
              <div key={index} className="overflow-hidden rounded-lg border">
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
      ) : null}
      <div className="text-sm text-muted-foreground">
        图片数量：{slide.image_count || 0}
      </div>
    </>
  )
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="py-16 text-center text-sm text-muted-foreground">{text}</div>
}
