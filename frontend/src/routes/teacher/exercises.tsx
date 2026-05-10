import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useState } from "react"
import { Plus, RefreshCw, ThumbsDown, ThumbsUp } from "lucide-react"
import { useFeedbackExercise, useGenerateExercises, useRegenerateExerciseOption, useTeacherChapters } from "@/api/teacher"
import { EmptyState } from "@/components/common/EmptyState"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { optionLabel, stripOptionPrefix } from "@/lib/exerciseOptions"
import { cn } from "@/lib/utils"
import type { Exercise } from "@/types/chapter"

type FeedbackType = "like" | "dislike"

export const Route = createFileRoute("/teacher/exercises")({
  component: ExercisesPage,
})

function ExercisesPage() {
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [feedbackStates, setFeedbackStates] = useState<Record<string, FeedbackType>>({})
  const [generatedBanks, setGeneratedBanks] = useState<Record<string, Exercise[]>>({})
  const [regeneratingOption, setRegeneratingOption] = useState("")
  const [generateStatus, setGenerateStatus] = useState("")
  const queryClient = useQueryClient()

  const { data: chaptersData } = useTeacherChapters()
  const generateExercises = useGenerateExercises()
  const feedbackExercise = useFeedbackExercise()
  const regenerateOption = useRegenerateExerciseOption()

  const chapters = chaptersData?.chapters || []
  const selectedChapter = chapters.find((chapter) => chapter.id === selectedChapterId)
  const exercises = generatedBanks[selectedChapterId] || selectedChapter?.exercise_bank || []

  const handleGenerate = async () => {
    if (!selectedChapterId) return
    const chapterBody = (selectedChapter?.content || selectedChapter?.lecture_content || "").trim()
    if (!chapterBody) {
      setGenerateStatus("当前章节没有可用内容，无法生成题目。请先导入章节内容、保存授课文案或补充图谱证据。")
      return
    }
    setGenerateStatus("正在生成 5 道新题，DeepSeek 响应可能较慢，请等待。")
    try {
      const result = await generateExercises.mutateAsync({
        chapter_id: selectedChapterId,
        chapter_title: selectedChapter?.title || selectedChapterId,
        chapter_content: chapterBody,
        count: 5,
        force_regenerate: true,
        types: ["选择题", "填空题", "简答题"],
      })
      const nextBank = result.exercise_bank || result.chapter?.exercise_bank || (result.exercise ? [result.exercise] : [])
      if (nextBank.length > 0) {
        setGeneratedBanks((prev) => ({ ...prev, [selectedChapterId]: nextBank }))
        queryClient.setQueryData<{ success: boolean; chapters: typeof chapters }>(["teacher-chapters"], (current) => {
          if (!current?.chapters) return current
          return {
            ...current,
            chapters: current.chapters.map((chapter) =>
              chapter.id === selectedChapterId || chapter.id === result.chapter?.id
                ? { ...chapter, ...(result.chapter || {}), exercise_bank: nextBank }
                : chapter,
            ),
          }
        })
        setGenerateStatus(result.warning ? `已生成 ${nextBank.length} 道题。${result.warning}` : `已生成 ${nextBank.length} 道题。`)
      } else {
        setGenerateStatus(result.warning || result.error || "生成完成，但没有返回可用题目。")
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
        queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
      ])
    } catch (error) {
      const responseData = isAxiosError(error) ? error.response?.data : undefined
      const message =
        (typeof responseData?.detail === "string" && responseData.detail) ||
        (typeof responseData?.error === "string" && responseData.error) ||
        (error instanceof Error ? error.message : "") ||
        "题库生成失败，请检查章节内容和后端日志。"
      setGenerateStatus(message)
    }
  }

  const handleFeedback = async (exercise: Exercise, feedback: FeedbackType) => {
    if (!selectedChapterId) return
    const result = await feedbackExercise.mutateAsync({
      exercise_id: exercise.id,
      chapter_id: selectedChapterId,
      rating: feedback === "like" ? "up" : "down",
      question: exercise.question,
      options: exercise.options || [],
      correct_answer: exercise.correct_answer || exercise.answer,
    })
    if (result.exercise_bank) {
      updateExerciseBank(result.exercise_bank, result.chapter_id || selectedChapterId)
    }
    setFeedbackStates((prev) => ({ ...prev, [exercise.id]: feedback }))
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] }),
      queryClient.invalidateQueries({ queryKey: ["student-exercises"] }),
      queryClient.invalidateQueries({ queryKey: ["student-chapters"] }),
    ])
  }

  const updateExerciseBank = (nextBank: Exercise[], chapterId = selectedChapterId) => {
    setGeneratedBanks((prev) => ({ ...prev, [selectedChapterId]: nextBank, [chapterId]: nextBank }))
    queryClient.setQueryData<{ success: boolean; chapters: typeof chapters }>(["teacher-chapters"], (current) => {
      if (!current?.chapters) return current
      return {
        ...current,
        chapters: current.chapters.map((chapter) =>
          chapter.id === chapterId || chapter.id === selectedChapterId
            ? { ...chapter, exercise_bank: nextBank }
            : chapter,
        ),
      }
    })
  }

  const handleRegenerateOption = async (exercise: Exercise, optionIndex: number) => {
    if (!selectedChapterId) return
    const optionKey = String.fromCharCode(65 + optionIndex)
    setRegeneratingOption(`${exercise.id}:${optionKey}`)
    try {
      const result = await regenerateOption.mutateAsync({
        chapter_id: selectedChapterId,
        exercise_id: exercise.id,
        rating: "down",
        question: exercise.question,
        option_key: optionKey,
        option_text: exercise.options?.[optionIndex],
        options: exercise.options || [],
        correct_answer: exercise.correct_answer || exercise.answer,
        note: "option_downvote_regenerate",
      })
      const nextBank = result.exercise_bank || []
      updateExerciseBank(nextBank, result.chapter_id || selectedChapterId)
      await queryClient.invalidateQueries({ queryKey: ["teacher-chapters"] })
    } finally {
      setRegeneratingOption("")
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">题库反馈</h1>
        <p className="text-muted-foreground">查看、评价和生成练习题</p>
      </div>

      {generateStatus ? <p className="text-sm text-muted-foreground">{generateStatus}</p> : null}

      <div className="bg-card border rounded-xl p-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <label className="block text-sm font-medium mb-2">选择章节</label>
            <select
              value={selectedChapterId}
              onChange={(event) => setSelectedChapterId(event.target.value)}
              className="w-full px-3 py-2.5 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary"
            >
              <option value="">-- 请选择章节 --</option>
              {chapters.map((chapter) => (
                <option key={chapter.id} value={chapter.id}>
                  {chapter.title}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleGenerate}
            disabled={!selectedChapterId || generateExercises.isPending}
            className="inline-flex w-full items-center justify-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50 sm:w-auto"
          >
            <Plus size={16} />
            {generateExercises.isPending ? "生成中..." : "生成新题"}
          </button>
        </div>
      </div>

      {selectedChapterId && (
        <div className="space-y-4">
          {exercises.length === 0 ? (
            <EmptyState
              title="暂无题目"
              description="该章节暂无练习题，点击上方按钮生成新题。"
              action={
                <button
                  onClick={handleGenerate}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
                >
                  <RefreshCw size={16} />
                  生成练习题
                </button>
              }
            />
          ) : (
            <>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                <h2 className="text-lg font-semibold">练习题列表 ({exercises.length})</h2>
              </div>
              <div className="space-y-3">
                {exercises.map((exercise, index) => (
                  <ExerciseCard
                    key={exercise.id || index}
                    index={index + 1}
                    exercise={exercise}
                    feedback={feedbackStates[exercise.id]}
                    onFeedback={(type) => handleFeedback(exercise, type)}
                    onRegenerateOption={(optionIndex) => handleRegenerateOption(exercise, optionIndex)}
                    isPending={feedbackExercise.isPending || regenerateOption.isPending}
                    pendingOption={regeneratingOption.startsWith(`${exercise.id}:`) ? regeneratingOption.split(":")[1] : ""}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function ExerciseCard({
  index,
  exercise,
  feedback,
  onFeedback,
  onRegenerateOption,
  isPending,
  pendingOption,
}: {
  index: number
  exercise: Exercise
  feedback?: FeedbackType
  onFeedback: (type: FeedbackType) => void
  onRegenerateOption: (optionIndex: number) => void
  isPending: boolean
  pendingOption?: string
}) {
  return (
    <div className="bg-card border rounded-xl p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-medium text-muted-foreground">#{index}</span>
            <span
              className={cn(
                "px-2 py-0.5 rounded text-xs font-medium",
                exercise.type === "选择题" && "bg-blue-100 text-blue-700",
                exercise.type === "填空题" && "bg-amber-100 text-amber-700",
                exercise.type === "简答题" && "bg-purple-100 text-purple-700"
              )}
            >
              {exercise.type || "练习题"}
            </span>
          </div>
          <div className="mb-3">
            <RichTextContent content={exercise.question} />
          </div>
          {exercise.options && exercise.options.length > 0 && (
            <div className="space-y-1 mb-3">
              {exercise.options.map((option, optionIndex) => (
                <div key={optionIndex} className="flex items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/60">
                  <div className="flex min-w-0 flex-1 items-start gap-2 text-sm text-muted-foreground">
                    <span className="shrink-0 font-medium">{optionLabel(optionIndex)}</span>
                    <RichTextContent
                      content={stripOptionPrefix(option, optionIndex)}
                      inline
                      className="min-w-0 flex-1"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => onRegenerateOption(optionIndex)}
                    disabled={isPending}
                    className="shrink-0 p-1.5 rounded-md text-muted-foreground hover:bg-red-100 hover:text-red-700 disabled:opacity-50"
                    title="差评该选项并局部重生成"
                  >
                    {pendingOption === String.fromCharCode(65 + optionIndex) ? (
                      <RefreshCw size={14} className="animate-spin" />
                    ) : (
                      <ThumbsDown size={14} />
                    )}
                  </button>
                </div>
              ))}
            </div>
          )}
          {(exercise.answer || exercise.correct_answer) && (
            <div className="text-sm">
              <span className="font-medium">答案:</span>{" "}
              <span className="text-muted-foreground">{exercise.answer || exercise.correct_answer}</span>
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1 self-end sm:self-start">
          <button
            onClick={() => onFeedback("like")}
            disabled={isPending}
            className={cn(
              "p-2 rounded-lg transition-colors",
              feedback === "like" ? "bg-green-100 text-green-700" : "hover:bg-muted text-muted-foreground"
            )}
            title="点赞"
          >
            <ThumbsUp size={16} />
          </button>
          <button
            onClick={() => onFeedback("dislike")}
            disabled={isPending}
            className={cn(
              "p-2 rounded-lg transition-colors",
              feedback === "dislike" ? "bg-red-100 text-red-700" : "hover:bg-muted text-muted-foreground"
            )}
            title="点踩"
          >
            <ThumbsDown size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
