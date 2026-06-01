import { useMutation, useQuery } from "@tanstack/react-query"
import { educationClient } from "./client"
import type {
  CoursewareAsset,
  CoursewareProject,
  CoursewareStyleReferenceResponse,
  EditableSlideModel,
  GenerateLectureRequest,
  GenerateLectureResponse,
  GenerateSlideLecturesRequest,
  GraphNodeContextResponse,
  AskQuestionRequest,
  AskQuestionResponse,
  LearningPlanRequest,
  LearningPlanResponse,
  NaturalSupplementRequest,
  NaturalSupplementResponse,
  PptArtifact,
  PptPreviewResponse,
  PptTexGenerateRequest,
  PptTexGenerateResponse,
  PptUploadResponse,
  TtsStatusResponse,
  TtsSegmentRequest,
  TtsSegmentsResponse,
  TtsSynthesizeRequest,
  TtsSynthesizeResponse,
  UploadGraphResponse,
} from "@/types/education"
import type { ApiResponse, DeepSeekConfigTestResponse, HealthCheckResponse, ConfigStatusResponse, SaveConfigResponse } from "@/types/api"

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

export const useSaveConfig = () => {
  return useMutation({
    mutationFn: (data: {
      deepseek_api_key?: string
      deepseek_api_base?: string
      deepseek_flash_model?: string
      deepseek_pro_model?: string
    }) => educationClient.post<SaveConfigResponse>("/api/save-config", data).then((r) => r.data),
  })
}

export const useTestDeepSeekConfig = () => {
  return useMutation({
    mutationFn: () =>
      educationClient
        .post<DeepSeekConfigTestResponse>("/api/test-deepseek-config", {}, { timeout: 30000 })
        .then((r) => r.data),
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

export const useGraphNodeContext = (nodeIds: string | string[]) => {
  const selectedIds = Array.isArray(nodeIds) ? nodeIds.filter(Boolean) : nodeIds ? [nodeIds] : []
  const selectedKey = selectedIds.join("|")
  return useQuery({
    queryKey: ["education-graph-node-context", selectedKey],
    queryFn: () =>
      educationClient
        .get<GraphNodeContextResponse>(
          `/api/education/graph/node-context?${selectedIds
            .map((nodeId) => `node_id=${encodeURIComponent(nodeId)}`)
            .join("&")}`,
        )
        .then((r) => r.data),
    enabled: selectedIds.length > 0,
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

export const useGeneratePptTex = () => {
  return useMutation({
    mutationFn: (data: PptTexGenerateRequest) =>
      educationClient
        .post<PptTexGenerateResponse>(
          "/api/education/generate-ppt-tex",
          {
            graph_scope: data.graph_scope || "subtree",
            ...data,
          },
          {
            timeout: 0,
          },
        )
        .then((r) => r.data),
  })
}

export const usePreviewTex = () => {
  return useMutation({
    mutationFn: (data: { tex_content: string; filename?: string }) =>
      educationClient
        .post<PptPreviewResponse>("/api/education/preview-tex", {
          filename: data.filename || "edited.tex",
          tex_content: data.tex_content,
        }, {
          timeout: 60000,
        })
        .then((r) => r.data),
  })
}

export const useUploadCoursewareAssets = () => {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      return educationClient
        .post<{ success: boolean; asset_map: Record<string, CoursewareAsset>; assets: CoursewareAsset[]; asset_count: number }>(
          "/api/education/courseware/assets",
          formData,
          {
            headers: { "Content-Type": "multipart/form-data" },
            timeout: 60000,
          },
        )
        .then((r) => r.data)
    },
  })
}

export const useUploadCoursewareStyleReference = () => {
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData()
      formData.append("file", file)
      return educationClient
        .post<CoursewareStyleReferenceResponse>("/api/education/courseware/style-reference", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 60000,
        })
        .then((r) => r.data)
    },
  })
}

export const useSaveCoursewareProject = () => {
  return useMutation({
    mutationFn: (data: {
      project_id?: string
      title: string
      editable_model: EditableSlideModel
      asset_map?: Record<string, CoursewareAsset>
      slides?: unknown[]
      tex_content?: string
      ppt_artifact?: unknown
      source_node_ids?: string[]
      lecture_target_duration_minutes?: number
      lecture_speech_rate_cpm?: number
      lecture_pacing?: unknown
    }) =>
      educationClient
        .post<{ success: boolean; project_id: string; project: CoursewareProject; message?: string }>(
          "/api/education/courseware/projects",
          data,
          { timeout: 60000 },
        )
        .then((r) => r.data),
  })
}

export const useCoursewareProjects = () => {
  return useQuery({
    queryKey: ["courseware-projects"],
    queryFn: () =>
      educationClient
        .get<{ success: boolean; projects: CoursewareProject[] }>("/api/education/courseware/projects")
        .then((r) => r.data),
  })
}

export const useCoursewareProject = (projectId: string) => {
  return useQuery({
    queryKey: ["courseware-project", projectId],
    queryFn: () =>
      educationClient
        .get<{ success: boolean; project: CoursewareProject }>(`/api/education/courseware/projects/${encodeURIComponent(projectId)}`)
        .then((r) => r.data),
    enabled: Boolean(projectId),
  })
}

export const useDeleteCoursewareProject = () => {
  return useMutation({
    mutationFn: (projectId: string) =>
      educationClient
        .delete<{ success: boolean; project_id: string; message?: string }>(
          `/api/education/courseware/projects/${encodeURIComponent(projectId)}`,
        )
        .then((r) => r.data),
  })
}

export const useExportCoursewarePptx = () => {
  return useMutation({
    mutationFn: (data: { title: string; editable_model: EditableSlideModel; source_node_ids?: string[] }) =>
      educationClient
        .post<{ success: boolean; ppt_artifact: PptArtifact; artifact: PptArtifact }>(
          "/api/education/courseware/export-pptx",
          data,
          { timeout: 120000 },
        )
        .then((r) => r.data),
  })
}

export const useGenerateSlideLectures = () => {
  return useMutation({
    mutationFn: async (data: GenerateSlideLecturesRequest & {
      onProgress?: (job: {
        status: string
        stage?: string
        message?: string
        elapsed_seconds?: number
      }) => void
    }) => {
      const { onProgress, ...requestData } = data
      const payload = {
        graph_scope: requestData.graph_scope || "subtree",
        ...requestData,
      }
      const started = await educationClient
        .post<{ success: boolean; job_id: string; status: string; error?: string }>(
          "/api/education/generate-slide-lectures/jobs",
          payload,
          { timeout: 30000 },
        )
        .then((r) => r.data)
      if (!started.success || !started.job_id) {
        throw new Error(started.error || "逐页讲解任务启动失败")
      }

      const startedAt = Date.now()
      const maxWaitMs = 30 * 60 * 1000
      while (Date.now() - startedAt < maxWaitMs) {
        await new Promise((resolve) => window.setTimeout(resolve, 3000))
        const job = await educationClient
          .get<{
            success: boolean
            status: string
            result?: PptUploadResponse
            error?: string
            stage?: string
            message?: string
            elapsed_seconds?: number
          }>(
            `/api/education/generate-slide-lectures/jobs/${encodeURIComponent(started.job_id)}`,
            { timeout: 120000 },
          )
          .then((r) => r.data)
        onProgress?.(job)
        if (job.status === "completed" && job.result) return job.result
        if (job.status === "failed") throw new Error(job.error || "逐页讲解任务失败")
      }
      throw new Error("逐页讲解任务仍在运行，请稍后刷新项目查看结果")
    },
  })
}

export const useGeneratePptLectures = () => {
  return useMutation({
    mutationFn: ({
      file,
      style,
      targetDurationMinutes,
      speechRateCpm,
      sourceNodeIds,
      teacherGuidance,
    }: {
      file: File
      style: string
      targetDurationMinutes?: number
      speechRateCpm?: number
      sourceNodeIds?: string[]
      teacherGuidance?: string
    }) => {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("style", style)
      if (typeof targetDurationMinutes === "number") formData.append("target_duration_minutes", String(targetDurationMinutes))
      if (typeof speechRateCpm === "number") formData.append("speech_rate_cpm", String(speechRateCpm))
      if (sourceNodeIds?.length) {
        if (sourceNodeIds.length === 1) formData.append("source_node_id", sourceNodeIds[0])
        sourceNodeIds.forEach((nodeId) => formData.append("source_node_ids", nodeId))
        formData.append("graph_scope", "subtree")
      }
      if (teacherGuidance?.trim()) formData.append("teacher_guidance", teacherGuidance.trim())
      return educationClient
        .post<PptUploadResponse>("/api/education/upload-ppt", formData, {
          headers: { "Content-Type": "multipart/form-data" },
          timeout: 180000,
        })
        .then((r) => r.data)
    },
  })
}

export const getTtsStatus = () =>
  educationClient.get<TtsStatusResponse>("/api/tts/status").then((r) => r.data)

export const synthesizeTts = (data: TtsSynthesizeRequest) =>
  educationClient
    .post<TtsSynthesizeResponse>("/api/tts/synthesize", data, {
      timeout: 0,
    })
    .then((r) => r.data)

export const splitTtsSegments = (data: TtsSegmentRequest) =>
  educationClient
    .post<TtsSegmentsResponse>("/api/tts/segments", data, {
      timeout: 60000,
    })
    .then((r) => r.data)
