import { useMutation, useQuery } from "@tanstack/react-query"
import { educationClient } from "./client"
import type {
  GenerateLectureRequest,
  GenerateLectureResponse,
  AskQuestionRequest,
  AskQuestionResponse,
  LearningPlanRequest,
  LearningPlanResponse,
  NaturalSupplementRequest,
  NaturalSupplementResponse,
  PptPreviewResponse,
  PptUploadResponse,
  UploadGraphResponse,
} from "@/types/education"
import type { ApiResponse, HealthCheckResponse, ConfigStatusResponse } from "@/types/api"

export const useHealthCheck = () => {
  return useQuery({
    queryKey: ["health"],
    queryFn: () => educationClient.get<HealthCheckResponse>("/api/health").then((r) => r.data),
    refetchInterval: 30000,
  })
}

export const useConfigStatus = () => {
  return useQuery({
    queryKey: ["config-status"],
    queryFn: () => educationClient.get<ConfigStatusResponse>("/api/config-status").then((r) => r.data),
  })
}

export const useGenerateLecture = () => {
  return useMutation({
    mutationFn: (data: GenerateLectureRequest) =>
      educationClient
        .post<GenerateLectureResponse>("/api/education/generate-lecture", {
          chapter_id: data.chapter_id || `chapter_${Date.now()}`,
          ...data,
        }, {
          timeout: 0,
        })
        .then((r) => r.data),
  })
}

export const useAskQuestion = () => {
  return useMutation({
    mutationFn: (data: AskQuestionRequest) =>
      educationClient
        .post<ApiResponse<AskQuestionResponse>>("/api/education/ask-question", data)
        .then((r) => r.data),
  })
}

export const useGetLearningPlan = () => {
  return useMutation({
    mutationFn: (data: LearningPlanRequest) =>
      educationClient
        .post<ApiResponse<LearningPlanResponse>>("/api/education/learning-plan", data)
        .then((r) => r.data),
  })
}

export const useNaturalSupplement = () => {
  return useMutation({
    mutationFn: (data: NaturalSupplementRequest) =>
      educationClient
        .post<NaturalSupplementResponse>("/api/education/natural-supplement", data)
        .then((r) => r.data),
  })
}

export const useEducationGraph = () => {
  return useQuery({
    queryKey: ["education-graph"],
    queryFn: () => educationClient.get<ApiResponse<unknown>>("/api/education/graph").then((r) => r.data),
  })
}

export const useUploadGraph = () => {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      return educationClient
        .post<UploadGraphResponse>("/api/education/upload-graph", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 120000,
        })
        .then((r) => r.data)
    },
  })
}

export const usePreviewPpt = () => {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      return educationClient
        .post<PptPreviewResponse>("/api/education/upload-ppt-preview", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 60000,
        })
        .then((r) => r.data)
    },
  })
}

export const useGeneratePptLectures = () => {
  return useMutation({
    mutationFn: ({ file, style }: { file: File; style: string }) => {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("style", style)
      return educationClient
        .post<PptUploadResponse>("/api/education/upload-ppt", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 180000,
        })
        .then((r) => r.data)
    },
  })
}
