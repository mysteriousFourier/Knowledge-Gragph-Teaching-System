import { useMutation, useQuery } from "@tanstack/react-query"
import { educationClient } from "./client"
import type { ApiResponse, LoginApiResponse } from "@/types/api"
import type { Chapter, Exercise } from "@/types/chapter"
import type {
  GenerateReviewRequest,
  GenerateReviewResponse,
  StudentQuestionRequest,
  StudentQuestionResponse,
} from "@/types/education"

export type ChapterProgressStatus = "learned" | "reviewing" | "forgotten" | "reset" | "unlearned"

export interface ChapterProgressRecord {
  status?: ChapterProgressStatus
  review_status?: ChapterProgressStatus
  learned_at?: string
  review_requested_at?: string
  forgotten_at?: string
  last_practiced_at?: string
  correct_count?: number
  wrong_count?: number
  updated_at?: string
}

export interface StudentProgress {
  total_chapters: number
  learned_chapters: number
  reviewing_chapters?: number
  forgotten_chapters?: number
  progress_percentage: number
  chapters: Record<string, ChapterProgressRecord>
}

export interface ReviewQueueItem {
  chapter_id: string
  title: string
  status: ChapterProgressStatus
  correct_count: number
  wrong_count: number
  learned_at?: string
  last_practiced_at?: string
  reason: string
  priority: number
}

export interface StudentReviewPayload {
  progress: StudentProgress
  recommendations: Array<{ type: string; content: string; chapter_id?: string }>
  queue: ReviewQueueItem[]
  path?: string[]
  nodes?: string[]
  chapter?: Chapter
}

export interface StudentExercisesPayload extends ApiResponse<Exercise[]> {
  exercise?: Exercise
  exercise_bank?: Exercise[]
  approved_exercise_bank?: Exercise[]
  cached?: boolean
  review_pending?: boolean
}

export interface CheckAnswerPayload extends ApiResponse<{ correct: boolean; is_correct?: boolean; explanation?: string; progress?: ChapterProgressRecord }> {
  correct?: boolean
  is_correct?: boolean
  explanation?: string
  feedback?: string
  progress?: ChapterProgressRecord
}

export const useStudentLogin = () => {
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      educationClient
        .post<LoginApiResponse>("/api/student/login", credentials)
        .then((r) => r.data),
  })
}

export const useStudentChapters = () => {
  return useQuery({
    queryKey: ["student-chapters"],
    queryFn: () => educationClient.get<{ success: boolean; chapters: Chapter[] }>("/api/education/list-chapters").then((r) => r.data),
  })
}

export const useStudentChapter = (chapterId: string) => {
  return useQuery({
    queryKey: ["student-chapter", chapterId],
    queryFn: () =>
      educationClient
        .get<{ success: boolean; chapter?: Chapter; error?: string }>(`/api/education/get-chapter?chapter_id=${encodeURIComponent(chapterId)}`)
        .then((r) => r.data),
    enabled: Boolean(chapterId),
  })
}

export const useStudentExercises = (chapterId: string, session = 0) => {
  return useQuery({
    queryKey: ["student-exercises", chapterId, session],
    queryFn: () =>
      educationClient
        .get<StudentExercisesPayload>(`/api/student/exercises?chapter_id=${chapterId}`)
        .then((r) => r.data),
    enabled: !!chapterId,
  })
}

export const useCheckAnswer = () => {
  return useMutation({
    mutationFn: (data: {
      exercise_id: string
      question: string
      answer: string
      chapter_id: string
      correct_answer?: string
      explanation?: string
    }) =>
      educationClient.post<CheckAnswerPayload>("/api/student/check-answer", data).then((r) => r.data),
  })
}

export const useMarkChapter = () => {
  return useMutation({
    mutationFn: (data: { chapter_id: string; status: ChapterProgressStatus }) =>
      educationClient.post<ApiResponse<{ progress?: ChapterProgressRecord }>>("/api/student/mark-chapter", data).then((r) => r.data),
  })
}

export const useStudentProgress = () => {
  return useQuery({
    queryKey: ["student-progress"],
    queryFn: () => educationClient.get<{ success: boolean; progress: StudentProgress }>("/api/student/progress").then((r) => r.data),
  })
}

export const useResetProgress = () => {
  return useMutation({
    mutationFn: (data: { chapter_id?: string }) =>
      educationClient.post<{ success: boolean; progress: StudentProgress }>("/api/student/reset-progress", data).then((r) => r.data),
  })
}

export const useStudentReview = (chapterId?: string) => {
  return useQuery({
    queryKey: ["student-review", chapterId || "queue"],
    queryFn: () =>
      educationClient
        .get<StudentReviewPayload & { success: boolean }>(
          chapterId ? `/api/student/review?chapter_id=${encodeURIComponent(chapterId)}` : "/api/student/review",
        )
        .then((r) => r.data),
  })
}

export const useStudentAskQuestion = () => {
  return useMutation({
    mutationFn: (data: StudentQuestionRequest) =>
      educationClient
        .post<StudentQuestionResponse>("/api/student/question", data)
        .then((r) => r.data),
  })
}

export const useGenerateReview = () => {
  return useMutation({
    mutationFn: (data: GenerateReviewRequest) =>
      educationClient
        .post<GenerateReviewResponse>("/api/student/generate-review", data)
        .then((r) => r.data),
  })
}
