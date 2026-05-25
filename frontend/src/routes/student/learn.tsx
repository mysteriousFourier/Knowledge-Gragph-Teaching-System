import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { BookOpen, CheckCircle, Pause, Play, RotateCcw, Send, Sparkles, Undo2 } from "lucide-react"
import { useMarkChapter, useStudentAskQuestion, useStudentChapters, useStudentProgress, type ChapterProgressStatus } from "@/api/student"
import { ConsistencyPanel } from "@/components/common/ConsistencyPanel"
import { EvidenceSummary } from "@/components/common/EvidenceSummary"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { PlaybackProgress } from "@/components/common/PlaybackProgress"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { useLecturePlayback } from "@/hooks/useLecturePlayback"
import { cn } from "@/lib/utils"
import type { StudentQuestionResponse } from "@/types/education"

export const Route = createFileRoute("/student/learn")({
  component: LearnPage,
})

function LearnPage() {
  const queryClient = useQueryClient()
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState<StudentQuestionResponse | null>(null)

  const { data, isLoading } = useStudentChapters()
  const { data: progressData } = useStudentProgress()
  const markChapter = useMarkChapter()
  const askQuestion = useStudentAskQuestion()

  const chapters = data?.chapters || []
  const selectedChapter = chapters.find((chapter) => chapter.id === selectedChapterId)
  const selectedContent = selectedChapter?.lecture_content || selectedChapter?.content || ""
  const selectedProgress = selectedChapter ? progressData?.progress?.chapters?.[selectedChapter.id] : undefined
  const playback = useLecturePlayback({
    segmentCount: selectedContent ? 1 : 0,
    getSegmentText: () => selectedContent,
  })

  const handleStatus = async (status: ChapterProgressStatus) => {
    if (!selectedChapter) return
    await markChapter.mutateAsync({ chapter_id: selectedChapter.id, status })
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["student-progress"] }),
      queryClient.invalidateQueries({ queryKey: ["student-review"] }),
    ])
  }

  const handleAsk = async () => {
    if (!selectedChapter || !question.trim()) return
    const result = await askQuestion.mutateAsync({
      chapter_id: selectedChapter.id,
      context: `章节标题：${selectedChapter.title}\n\n章节内容：\n${selectedContent}`,
      question: question.trim(),
    })
    setAnswer(result)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">学习模式</h1>
        <p className="text-muted-foreground">选择章节，阅读课程内容</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-card border rounded-xl p-4">
            <h2 className="font-semibold mb-3 flex items-center gap-2">
              <BookOpen size={18} />
              章节选择
            </h2>
            {isLoading ? (
              <LoadingSpinner size={20} text="加载中..." />
            ) : chapters.length === 0 ? (
              <EmptyState title="暂无章节" description="没有可用的学习章节" />
            ) : (
              <div className="space-y-2">
                {chapters.map((chapter) => (
                  <button
                    key={chapter.id}
                    onClick={() => {
                      setSelectedChapterId(chapter.id)
                      playback.reset(0)
                      setQuestion("")
                      setAnswer(null)
                    }}
                    className={cn(
                      "w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors",
                      selectedChapterId === chapter.id
                        ? "bg-primary/10 text-primary font-medium"
                        : "hover:bg-muted text-muted-foreground"
                    )}
                  >
                    {chapter.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="lg:col-span-2">
          {selectedChapter ? (
            <div className="space-y-4">
              <div className="bg-card border rounded-xl">
              <div className="flex flex-col gap-3 border-b p-4 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="min-w-0 font-semibold">{selectedChapter.title}</h2>
                <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center">
                  <button
                    onClick={playback.toggle}
                    disabled={!playback.hasSegments}
                    className={cn(
                      "inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50",
                      playback.isPlaying ? "bg-amber-100 text-amber-700 hover:bg-amber-200" : "bg-primary/10 text-primary hover:bg-primary/20"
                    )}
                    title={playback.providerLabel}
                  >
                    {playback.isPlaying || playback.isLoadingAudio ? <Pause size={14} /> : <Play size={14} />}
                    {playback.isPlaying || playback.isLoadingAudio ? "暂停" : "播放"}
                  </button>
                  <button
                    onClick={() => handleStatus("learned")}
                    disabled={markChapter.isPending}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-green-100 text-green-700 hover:bg-green-200 transition-colors"
                  >
                    <CheckCircle size={14} />
                    标记已学
                  </button>
                  <button
                    onClick={() => handleStatus("forgotten")}
                    disabled={markChapter.isPending}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
                  >
                    <Undo2 size={14} />
                    我忘了
                  </button>
                  <button
                    onClick={() => handleStatus("reviewing")}
                    disabled={markChapter.isPending}
                    className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-blue-100 text-blue-700 hover:bg-blue-200 transition-colors"
                  >
                    <RotateCcw size={14} />
                    重新学习
                  </button>
                </div>
              </div>
              {selectedProgress && (
                <div className="border-b px-4 py-2 text-sm text-muted-foreground">
                  当前状态：{statusLabel(selectedProgress.status)} · 正确 {selectedProgress.correct_count || 0} · 错误 {selectedProgress.wrong_count || 0}
                </div>
              )}
              <PlaybackProgress progress={playback.progress} statusText={playback.statusText} />
              <div className="p-4">
                {selectedContent ? (
                  <RichTextContent content={selectedContent} />
                ) : (
                  <EmptyState title="暂无内容" description="该章节暂无课程内容" />
                )}
              </div>
            </div>
              <section className="bg-card border rounded-xl">
                <div className="border-b p-4">
                  <h2 className="flex items-center gap-2 font-semibold">
                    <Sparkles size={18} />
                    当前章节问答
                  </h2>
                </div>
                <div className="space-y-4 p-4">
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder={`围绕《${selectedChapter.title}》提问，例如：这个公式中的变量分别是什么意思？`}
                    className="min-h-[92px] w-full resize-y rounded-lg border bg-background px-3 py-2.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
                  />
                  <button
                    onClick={handleAsk}
                    disabled={!question.trim() || askQuestion.isPending}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 sm:w-auto"
                  >
                    {askQuestion.isPending ? <LoadingSpinner size={16} /> : <Send size={16} />}
                    {askQuestion.isPending ? "回答中..." : "提问"}
                  </button>

                  {answer?.warning && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                      {answer.warning}
                    </div>
                  )}
                  {answer?.answer && (
                    <div className="rounded-lg border bg-background p-4">
                      <RichTextContent content={answer.answer} />
                    </div>
                  )}
                  {(answer?.learning_plan || answer?.sources?.length || answer?.retrieval_context) && (
                    <EvidenceSummary
                      learningPlan={answer.learning_plan}
                      sources={answer.sources}
                      retrievalContext={answer.retrieval_context}
                      warning={answer.warning}
                    />
                  )}
                  {answer?.consistency_report && (
                    <ConsistencyPanel report={answer.consistency_report} title="问答实体指标" />
                  )}
                </div>
              </section>
            </div>
          ) : (
            <div className="bg-card border rounded-xl p-8">
              <EmptyState
                title="选择章节"
                description="请从左侧选择一个章节开始学习"
                icon={<BookOpen size={48} className="text-muted-foreground" />}
              />
            </div>
          )}
        </div>
      </div>
    </div>
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
