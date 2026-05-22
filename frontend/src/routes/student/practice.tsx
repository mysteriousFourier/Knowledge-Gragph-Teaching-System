import { createFileRoute } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { ArrowRight, CheckCircle, RotateCcw, XCircle } from "lucide-react"
import { useCheckAnswer, useStudentChapters, useStudentExercises } from "@/api/student"
import { EmptyState } from "@/components/common/EmptyState"
import { LoadingSpinner } from "@/components/common/LoadingSpinner"
import { RichTextContent } from "@/components/renderers/RichTextContent"
import { optionKey, optionLabel, stripOptionPrefix } from "@/lib/exerciseOptions"
import { cn } from "@/lib/utils"

export const Route = createFileRoute("/student/practice")({
  component: PracticePage,
})

function PracticePage() {
  const queryClient = useQueryClient()
  const [selectedChapterId, setSelectedChapterId] = useState("")
  const [currentExerciseIndex, setCurrentExerciseIndex] = useState(0)
  const [selectedAnswer, setSelectedAnswer] = useState("")
  const [showResult, setShowResult] = useState(false)
  const [results, setResults] = useState<Record<string, boolean>>({})
  const [practiceSession, setPracticeSession] = useState(0)

  const { data: chaptersData } = useStudentChapters()
  const { data: exercisesData, isLoading } = useStudentExercises(selectedChapterId, practiceSession)
  const checkAnswer = useCheckAnswer()

  const chapters = chaptersData?.chapters || []
  const exercises = exercisesData?.data || exercisesData?.exercise_bank || (exercisesData?.exercise ? [exercisesData.exercise] : [])
  const currentExercise = exercises[currentExerciseIndex]

  const handleCheckAnswer = async () => {
    if (!currentExercise || !selectedAnswer) return
    const expectedAnswer = resolveExpectedAnswer(currentExercise)
    const optimisticCorrect = expectedAnswer ? normalizeAnswer(selectedAnswer) === normalizeAnswer(expectedAnswer) : false
    try {
      const result = await checkAnswer.mutateAsync({
        exercise_id: currentExercise.id,
        question: currentExercise.question,
        answer: selectedAnswer,
        chapter_id: selectedChapterId,
        correct_answer: expectedAnswer,
        explanation: currentExercise.explanation,
      })
      setResults((prev) => ({
        ...prev,
        [currentExercise.id]: Boolean(result.data?.correct ?? result.data?.is_correct ?? result.correct ?? result.is_correct ?? optimisticCorrect),
      }))
      void queryClient.invalidateQueries({ queryKey: ["student-progress"] })
      void queryClient.invalidateQueries({ queryKey: ["student-review"] })
    } catch {
      setResults((prev) => ({ ...prev, [currentExercise.id]: optimisticCorrect }))
    }
    setShowResult(true)
  }

  const handleNext = () => {
    setCurrentExerciseIndex((prev) => Math.min(prev + 1, exercises.length - 1))
    setSelectedAnswer("")
    setShowResult(false)
  }

  const handleReset = () => {
    setPracticeSession((prev) => prev + 1)
    setCurrentExerciseIndex(0)
    setSelectedAnswer("")
    setShowResult(false)
    setResults({})
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">练习模式</h1>
        <p className="text-muted-foreground">选择章节，完成练习题</p>
      </div>

      <div className="bg-card border rounded-xl p-4">
        <label className="block text-sm font-medium mb-2">选择章节</label>
        <select
          value={selectedChapterId}
          onChange={(event) => {
            setSelectedChapterId(event.target.value)
            handleReset()
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
      </div>

      {selectedChapterId && (
        <div className="bg-card border rounded-xl">
          {isLoading ? (
            <div className="p-8">
              <LoadingSpinner text="加载题目中..." />
            </div>
          ) : exercises.length === 0 ? (
            <div className="p-8">
              <EmptyState title="暂无题目" description="该章节暂无练习题" />
            </div>
          ) : (
            <>
              <div className="p-4 border-b">
                <div className="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-sm text-muted-foreground">
                    题目 {currentExerciseIndex + 1} / {exercises.length}
                  </span>
                  <button
                    onClick={handleReset}
                    className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                  >
                    <RotateCcw size={14} />
                    重新开始
                  </button>
                </div>
                <div className="w-full bg-muted rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all"
                    style={{ width: `${((currentExerciseIndex + 1) / exercises.length) * 100}%` }}
                  />
                </div>
              </div>

              <div className="p-4 sm:p-6">
                <div className="mb-2">
                  <span
                    className={cn(
                      "inline-block px-2 py-0.5 rounded text-xs font-medium",
                      currentExercise.type === "选择题" && "bg-blue-100 text-blue-700",
                      currentExercise.type === "填空题" && "bg-amber-100 text-amber-700",
                      currentExercise.type === "简答题" && "bg-purple-100 text-purple-700"
                    )}
                  >
                    {currentExercise.type}
                  </span>
                </div>
                <div className="mb-6">
                  <RichTextContent content={currentExercise.question} />
                </div>

                {currentExercise.options && currentExercise.options.length > 0 ? (
                  <div className="space-y-2 mb-6">
                    {currentExercise.options.map((option, index) => {
                      const key = optionKey(index)
                      return (
                      <button
                        key={index}
                        onClick={() => !showResult && setSelectedAnswer(key)}
                        disabled={showResult}
                        className={cn(
                          "w-full text-left px-3 py-3 rounded-lg border text-sm transition-colors sm:px-4",
                          selectedAnswer === key
                            ? showResult
                              ? results[currentExercise.id]
                                ? "bg-green-100 border-green-300 text-green-800"
                                : "bg-red-100 border-red-300 text-red-800"
                              : "bg-primary/10 border-primary text-primary"
                            : "hover:bg-muted border-transparent bg-muted/50"
                        )}
                      >
                        <span className="flex items-start gap-2">
                          <span className="shrink-0 font-medium">{optionLabel(index)}</span>
                          <RichTextContent
                            content={stripOptionPrefix(option, index)}
                            inline
                            className="min-w-0 flex-1"
                          />
                        </span>
                      </button>
                      )
                    })}
                  </div>
                ) : (
                  <div className="mb-6">
                    <textarea
                      value={selectedAnswer}
                      onChange={(event) => !showResult && setSelectedAnswer(event.target.value)}
                      disabled={showResult}
                      placeholder="请输入你的答案..."
                      className="w-full px-3 py-2.5 bg-background border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary min-h-[100px] resize-y"
                    />
                  </div>
                )}

                <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
                  {!showResult ? (
                    <button
                      onClick={handleCheckAnswer}
                      disabled={!selectedAnswer || checkAnswer.isPending}
                      className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90 disabled:opacity-50"
                    >
                      <CheckCircle size={16} />
                      {checkAnswer.isPending ? "检查中..." : "提交答案"}
                    </button>
                  ) : (
                    <>
                      <div
                        className={cn(
                          "inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium",
                          results[currentExercise.id] ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"
                        )}
                      >
                        {results[currentExercise.id] ? (
                          <>
                            <CheckCircle size={16} />
                            回答正确
                          </>
                        ) : (
                          <>
                            <XCircle size={16} />
                            回答错误
                          </>
                        )}
                      </div>
                      {currentExerciseIndex < exercises.length - 1 && (
                        <button
                          onClick={handleNext}
                          className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary/90"
                        >
                          下一题
                          <ArrowRight size={16} />
                        </button>
                      )}
                    </>
                  )}
                </div>

                {showResult && currentExercise.explanation && (
                  <div className="mt-4 p-4 bg-muted/50 rounded-lg">
                    <h4 className="text-sm font-medium mb-2">解析</h4>
                    <RichTextContent content={currentExercise.explanation} />
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function normalizeAnswer(value: string) {
  const text = value.trim()
  const optionMatch = text.match(/^([A-Z])(?:\s*[.)、。:：）-]|\s*$)/i)
  return optionMatch ? optionMatch[1].toUpperCase() : text.toUpperCase()
}

function resolveExpectedAnswer(exercise: {
  correct_answer?: string
  answer?: string
  options?: string[]
}) {
  const rawAnswer = String(exercise.correct_answer || exercise.answer || "").trim()
  const normalized = normalizeAnswer(rawAnswer)
  if (!exercise.options?.length) return rawAnswer
  if (/^[A-Z]$/.test(normalized)) return normalized

  const expectedText = normalizeOptionText(rawAnswer)
  const matchedIndex = exercise.options.findIndex(
    (option, index) => normalizeOptionText(option, index) === expectedText,
  )
  return matchedIndex >= 0 ? optionKey(matchedIndex) : rawAnswer
}

function normalizeOptionText(value: string, index?: number) {
  return stripOptionPrefix(value, index).replace(/\s+/g, " ").trim().toUpperCase()
}
