export interface GenerateLectureRequest {
  chapter_id?: string
  chapter_content?: string
  chapter_title?: string
  style?: string
  length?: string
}

export interface GenerateLectureResponse {
  success: boolean
  content?: string
  lecture_content?: string
  chapter_id?: string
  chapter_title?: string
  consistency_report?: ConsistencyReport
  learning_plan?: unknown
  error?: string
}

export interface ConsistencyEntity {
  id?: string
  name: string
  type?: string
  source_index?: number
  count?: number
}

export interface ConsistencyReport {
  knowledge_support_ratio?: number
  unsupported_concept_rate?: number
  entity_recall?: number
  entity_hallucination_rate?: number
  expected_entities?: ConsistencyEntity[]
  mentioned_entities?: ConsistencyEntity[]
  missing_entities?: ConsistencyEntity[]
  extracted_entities?: ConsistencyEntity[]
  unsupported_entities?: ConsistencyEntity[]
  learning_goal_alignment?: number
  difficulty_match?: string
  hint_policy_violated?: boolean
  is_safe_to_show?: boolean
  warnings?: string[]
}

export interface UploadGraphResponse {
  success: boolean
  file_name?: string
  graph_type?: string
  markdown_content?: string
  chapter_hint?: {
    title?: string
    content?: string
  }
  parsed?: {
    nodes: number
    relations: number
  }
  result?: unknown
  message?: string
  imported_at?: string
  error?: string
}

export interface AskQuestionRequest {
  question: string
  chapter_id?: string
  context?: string
  student_id?: string
}

export interface AskQuestionResponse {
  success: boolean
  answer?: string
  sources?: unknown[]
  retrieval_context?: string
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
  warning?: string
  error?: string
}

export interface StudentQuestionRequest {
  question: string
  chapter_id?: string
  context?: string
  student_id?: string
}

export interface StudentQuestionResponse {
  success: boolean
  answer?: string
  sources?: unknown[]
  retrieval_context?: string
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
  warning?: string
  error?: string
}

export interface GenerateReviewRequest {
  chapter_id: string
  count?: number
}

export interface GenerateReviewResponse {
  success: boolean
  chapter_id?: string
  review_content?: string
  exercise_bank?: unknown[]
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
  generated_at?: string
  warning?: string
  error?: string
}

export interface LearningPlanRequest {
  query?: string
  chapter_id?: string
  task?: string
  learning_level?: string
  student_id?: string
}

export interface LearningPlanResponse {
  success: boolean
  learning_plan?: {
    nodes?: string[]
    path?: string[]
  }
  plan?: {
    nodes: string[]
    path: string[]
  }
  error?: string
}

export interface PptImageInfo {
  data_uri?: string | null
  width_emu: number
  height_emu: number
  left_emu: number
  top_emu: number
  oversized?: boolean
}

export interface PptTable {
  rows: string[][]
}

export interface PptSlideDetail {
  index: number
  title?: string
  content?: string
  notes?: string
  has_images?: boolean
  image_count?: number
  images?: PptImageInfo[]
  tables?: PptTable[]
  body_texts?: string[]
  raw_text?: string
}

export interface PptSlideLecture {
  index: number
  title?: string
  lecture: string
  skipped: boolean
  sources?: unknown[]
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
}

export interface PptPreviewResponse {
  success: boolean
  chapter_title: string
  slide_count: number
  slides: PptSlideDetail[]
  full_text: string
  warning?: string
  error?: string
}

export interface PptUploadResponse extends PptPreviewResponse {
  lecture_content: string
  slide_lectures: PptSlideLecture[]
  style?: string
  model?: string
  generated_at?: string
  message?: string
}

export interface BeamerSlideData {
  id: number
  type: string
  title: string
  subtitle?: string
  items: string[]
  equations: string[]
  notes?: string
}

export interface BeamerSlidesData {
  title: string
  subtitle?: string
  author?: string
  date?: string
  slides: BeamerSlideData[]
}

export interface BeamerGenerateResponse {
  success: boolean
  latex?: string
  slides_data?: BeamerSlidesData
  model?: string
  generated_at?: string
  warning?: string
  message?: string
  error?: string
}

export interface BeamerParseResponse {
  success: boolean
  slides_data: BeamerSlidesData
  error?: string
}

export interface NaturalSupplementRequest {
  original_text: string
  supplement: string
  insert_position?: string
  save_draft_if_fail?: boolean
}

export interface NaturalSupplementResponse {
  success: boolean
  result?: string
  model?: string
  retrieval_context?: string
  sources?: unknown[]
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
  warning?: string
  error?: string
}
