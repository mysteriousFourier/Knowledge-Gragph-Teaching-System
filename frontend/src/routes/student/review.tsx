import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ArrowRight, BookOpen, ListChecks, RotateCcw, Sparkles } from "lucide-react"
import { useGenerateReview, useResetProgress, useStudentChapters, useStudentReview, type ReviewQueueItem } from "@/api/student"
import { ConsistencyPanel } from "@/components/common/ConsistencyPanel"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { optionLabel, stripOptionPrefix } from "@/lib/exerciseOptions"
import type { GenerateReviewResponse } from "@/types/education"

interface ReviewPlan {
  nodes?: string[]
  path?: string[]
}

export const Route = createFileRoute("/student/review")({
  component: ReviewPage,
})

function ReviewPage() {
  const queryClient = useQueryClient()
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [generatedReview, setGeneratedReview] = useState<GenerateReviewResponse | null>(null)

  const { data: chaptersData } = useStudentChapters()
  const { data: reviewQueueData, isLoading: queueLoading } = useStudentReview()
  const { data: reviewData, isLoading } = useStudentReview(selectedChapterId || undefined)
  const generateReview = useGenerateReview()
  const resetProgress = useResetProgress()

  const chapters = chaptersData?.chapters || []
  const selectedChapter = chapters.find((chapter) => chapter.id === selectedChapterId)
  const review = reviewData as ReviewPlan | undefined
  const queue = reviewQueueData?.queue || []

  const handleGenerateReview = async () => {
    if (!selectedChapterId) return
    const result = await generateReview.mutateAsync({ chapter_id: selectedChapterId, count: 5 })
    setGeneratedReview(result)
  }

  const handleResetChapter = async () => {
    if (!selectedChapterId) return
    const confirmed = window.confirm("确认重置本章进度？这会清除本章已学、复习和答题统计。")
    if (!confirmed) return
    await resetProgress.mutateAsync({ chapter_id: selectedChapterId })
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["student-progress"] }),
      queryClient.invalidateQueries({ queryKey: ["student-review"] }),
    ])
  }

  const handleResetAll = async () => {
    const confirmed = window.confirm("确认重置全部学习进度？这会清除所有章节的学习和答题统计。")
    if (!confirmed) return
    await resetProgress.mutateAsync({})
    setSelectedChapterId("")
    setGeneratedReview(null)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["student-progress"] }),
      queryClient.invalidateQueries({ queryKey: ["student-review"] }),
    ])
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">复习模式</h1>
        <p className="text-muted-foreground">优先处理已忘记、错题多和久未练习的章节</p>
      </div>

      <section className="rounded-xl border bg-card">
        <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold">复习队列</h2>
            <p className="text-sm text-muted-foreground">系统按遗忘、错题和间隔时间排序。</p>
          </div>
          <button
            onClick={handleResetAll}
            disabled={resetProgress.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
          >
            <RotateCcw size={15} />
            重置全部学习进度
          </button>
        </div>
        <div className="p-4">
          {queueLoading ? (
            <LoadingSpinner text="加载复习队列..." />
          ) : queue.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {queue.map((item) => (
                <ReviewQueueCard
                  key={item.chapter_id}
                  item={item}
                  active={selectedChapterId === item.chapter_id}
                  onSelect={() => {
                    setSelectedChapterId(item.chapter_id)
                    setGeneratedReview(null)
                  }}
                />
              ))}
            </div>
          ) : (
            <EmptyState title="暂无复习队列" description="学习或练习后，这里会按优先级推荐复习章节。" />
          )}
        </div>
      </section>

      <div className="bg-card border rounded-xl p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="block flex-1 text-sm font-medium">
            <span className="mb-2 block">选择章节</span>
            <select
              value={selectedChapterId}
              onChange={(event) => {
                setSelectedChapterId(event.target.value)
                setGeneratedReview(null)
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
          </label>
          <button
            onClick={handleResetChapter}
            disabled={!selectedChapterId || resetProgress.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-lg border px-3 py-2.5 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <RotateCcw size={15} />
            重置本章进度
          </button>
        </div>
      </div>

      {selectedChapterId && (
        <div className="space-y-4">
          <div className="flex flex-col gap-3 rounded-lg border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-semibold">{selectedChapter?.title || "当前章节"}</h2>
              <p className="text-sm text-muted-foreground">生成复习讲义和 5 道复习题，内容会优先使用章节与图谱证据。</p>
            </div>
            <button
              onClick={handleGenerateReview}
              disabled={generateReview.isPending}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {generateReview.isPending ? <LoadingSpinner size={16} /> : <Sparkles size={16} />}
              {generateReview.isPending ? "生成中..." : "AI 生成复习内容"}
            </button>
          </div>

          {generatedReview?.warning && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              {generatedReview.warning}
            </div>
          )}

          {generatedReview?.review_content && (
            <section className="rounded-lg border bg-card">
              <div className="border-b p-4">
                <h2 className="flex items-center gap-2 font-semibold">
                  <BookOpen size={18} />
                  复习讲义
                </h2>
              </div>
              <div className="p-4">
                <RichTextContent content={generatedReview.review_content} />
              </div>
            </section>
          )}

          {!!generatedReview?.exercise_bank?.length && (
            <section className="rounded-lg border bg-card">
              <div className="border-b p-4">
                <h2 className="flex items-center gap-2 font-semibold">
                  <ListChecks size={18} />
                  复习题单
                </h2>
              </div>
              <div className="divide-y">
                {generatedReview.exercise_bank.map((exercise, index) => (
                  <ExerciseCard key={getExerciseKey(exercise, index)} exercise={exercise} index={index} />
                ))}
              </div>
            </section>
          )}

          {generatedReview?.consistency_report && (
            <ConsistencyPanel report={generatedReview.consistency_report} title="复习内容实体指标" />
          )}

          <div className="bg-card border rounded-xl">
            {isLoading ? (
              <div className="p-8">
                <LoadingSpinner text="加载复习内容..." />
              </div>
            ) : !review ? (
              <div className="p-8">
                <EmptyState title="暂无复习内容" description="该章节暂无复习路径数据" icon={<RotateCcw size={48} />} />
              </div>
            ) : (
              <div className="p-6">
                <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                  <BookOpen size={20} />
                  学习路径
                </h2>
                <div className="space-y-3">
                  {review.path?.length ? (
                    review.path.map((node, index) => (
                      <div key={`${node}-${index}`} className="flex items-center gap-3">
                        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 text-primary flex items-center justify-center text-sm font-medium">
                          {index + 1}
                        </div>
                        <div className="flex-1 p-3 bg-muted/50 rounded-lg">
                          <p className="text-sm">{node}</p>
                        </div>
                        {index < (review.path?.length || 0) - 1 && (
                          <ArrowRight size={16} className="text-muted-foreground flex-shrink-0" />
                        )}
                      </div>
                    ))
                  ) : (
                    <EmptyState title="暂无路径数据" description="该章节没有可用的学习路径" />
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ReviewQueueCard({ item, active, onSelect }: { item: ReviewQueueItem; active: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`rounded-lg border p-4 text-left transition-colors hover:bg-muted/60 ${
        active ? "border-primary bg-primary/10" : "bg-background"
      }`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="font-medium">{item.title}</div>
          <div className="mt-1 text-sm text-muted-foreground">{item.reason}</div>
        </div>
        <span className="rounded-full border bg-card px-2 py-1 text-xs text-muted-foreground">{statusLabel(item.status)}</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>正确 {item.correct_count}</span>
        <span>错误 {item.wrong_count}</span>
        <span>优先级 {item.priority}</span>
      </div>
    </button>
  )
}

function statusLabel(status?: string) {
  const labels: Record<string, string> = {
    learned: "已学完",
    reviewing: "需要复习",
    forgotten: "已忘记",
    unlearned: "未学习",
  }
  return labels[status || "unlearned"] || "未学习"
}

function ExerciseCard({ exercise, index }: { exercise: unknown; index: number }) {
  const item = isRecord(exercise) ? exercise : {}
  const question = String(item.question || `复习题 ${index + 1}`)
  const options = Array.isArray(item.options) ? item.options.map((option) => String(option)) : []
  const answer = String(item.correct_answer || item.answer || "")
  const explanation = String(item.explanation || "")

  return (
    <div className="space-y-3 p-4">
      <div className="font-medium">
        {index + 1}. {question}
      </div>
      {!!options.length && (
        <div className="grid gap-2 sm:grid-cols-2">
          {options.map((option, optionIndex) => (
            <div key={`${optionIndex}-${option}`} className="flex items-start gap-2 rounded-lg border bg-background px-3 py-2 text-sm">
              <span className="shrink-0 font-medium text-muted-foreground">{optionLabel(optionIndex)}</span>
              <RichTextContent
                content={stripOptionPrefix(option, optionIndex)}
                inline
                className="min-w-0 flex-1"
              />
            </div>
          ))}
        </div>
      )}
      {answer && <div className="text-sm text-primary">答案：{answer}</div>}
      {explanation && <RichTextContent content={explanation} className="text-sm" />}
    </div>
  )
}

function getExerciseKey(exercise: unknown, index: number) {
  if (isRecord(exercise) && exercise.id) return String(exercise.id)
  return `review-exercise-${index}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}
