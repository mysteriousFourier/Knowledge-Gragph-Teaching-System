export interface GenerateLectureRequest {
  chapter_id?: string
  chapter_content?: string
  chapter_title?: string
  style?: string
  length?: string
  source_node_id?: string
  source_node_ids?: string[]
  graph_scope?: "subtree" | string
  teacher_guidance?: string
}

export interface GraphSourceScope {
  mode?: string
  root_count?: number
  selected_count?: number
  referenced_count?: number
  max_nodes?: number
  truncated?: boolean
  [key: string]: unknown
}

export interface GenerateLectureResponse {
  success: boolean
  content?: string
  lecture_content?: string
  chapter_id?: string
  chapter_title?: string
  consistency_report?: ConsistencyReport
  learning_plan?: unknown
  source_node_id?: string
  source_node_ids?: string[]
  source_scope?: GraphSourceScope
  error?: string
}

export interface TtsStatusResponse {
  success: boolean
  enabled: boolean
  provider: "disabled" | "genie" | "genie_server" | "gpt_sovits_local" | "gpt_sovits_server" | string
  available: boolean
  model_loaded?: boolean
  runtime_root?: string
  model_id?: string
  cache_enabled?: boolean
  cache_files?: number
  cache_size_mb?: number
  last_error?: string | null
  character_name?: string
  detail?: string
  output_dir?: string
  max_chars?: number
}

export interface TtsSynthesizeRequest {
  text: string
  character_name?: string
  split_sentence?: boolean
  language?: string
  speed_factor?: number
}

export interface TtsSynthesizeResponse {
  success: boolean
  provider: string
  audio_url?: string
  cache_hit?: boolean
  cache_key?: string | null
  normalized_text_length?: number
  text_lang?: string
  text_length?: number
  error?: string
  detail?: string
}

export interface TtsSegmentRequest {
  text: string
  language?: string
  max_chars?: number
}

export interface TtsSegmentItem {
  index: number
  text: string
  length: number
}

export interface TtsSegmentsResponse {
  success: boolean
  segments: TtsSegmentItem[]
  segment_count: number
  normalized_text_length: number
  text_lang: string
  max_chars: number
  error?: string
  detail?: string
}

export interface GraphContextTreeNode {
  id: string
  label: string
  type: string
  children?: GraphContextTreeNode[]
}

export interface GraphNodeContextResponse {
  success: boolean
  node_id?: string
  node_ids?: string[]
  root?: unknown
  roots?: unknown[]
  tree?: GraphContextTreeNode
  nodes?: unknown[]
  relations?: unknown[]
  chapter_title?: string
  chapter_content?: string
  scope?: GraphSourceScope
  evidence?: unknown[]
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
  source_path?: string
  tex_options?: string
  tex_ref?: string
  width_ratio?: number
  height_ratio?: number
  oversized?: boolean
}

export interface CoursewareAsset {
  id: string
  name?: string
  source_path?: string
  tex_ref?: string
  mime_type?: string
  data_uri?: string | null
  aliases?: string[]
  slide_indices?: number[]
  figure_refs?: string[]
  oversized?: boolean
}

export interface EditableSlideBBox {
  x: number
  y: number
  width: number
  height: number
}

export interface EditableSlideObject {
  id: string
  type: "title" | "richText" | "textbox" | "equation" | "table" | "image" | "placeholder" | "callout" | string
  bbox: EditableSlideBBox
  z?: number
  locked?: boolean
  style?: Record<string, unknown>
  text?: string
  rich_html?: string
  latex?: string
  rows?: string[][]
  asset_id?: string
  source_path?: string
  tex_ref?: string
  width_ratio?: number
  label?: string
  title?: string
  role?: string
}

export interface EditableSlide {
  id: string
  index: number
  title?: string
  items: EditableSlideObject[]
  objects?: EditableSlideObject[]
  layout?: PptSlideDetail["layout"]
  source_tex?: string
  source_body_tex?: string
  source_start?: number | null
  source_end?: number | null
  notes?: string
}

export interface EditableSlideModel {
  version: number
  title?: string
  slide_count?: number
  canvas?: {
    width: number
    height: number
    unit?: string
  }
  layout?: {
    canvas?: {
      width: number
      height: number
    }
    [key: string]: unknown
  }
  source_tex?: string
  source_tex_file?: string
  assets?: Record<string, CoursewareAsset>
  slides: EditableSlide[]
  updated_at?: string
}

export interface CoursewareProject {
  id: string
  title: string
  editable_model?: EditableSlideModel
  asset_map?: Record<string, CoursewareAsset>
  slides?: PptSlideDetail[]
  tex_content?: string
  ppt_artifact?: PptArtifact
  source_node_ids?: string[]
  slide_count?: number
  created_at?: string
  updated_at?: string
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
  source_tex?: string
  source_body_tex?: string
  source_start?: number | null
  source_end?: number | null
  layout?: {
    mode?: "text" | "title" | "columns" | "image_only" | "image_text" | "text_image" | string
    has_columns?: boolean
    column_count?: number
    columns?: Array<{
      width_ratio?: number | null
      content?: string
      images?: PptImageInfo[]
      image_count?: number
      image_first?: boolean
      align?: "left" | "center" | string
      max_image_width?: number | null
      source_tex?: string
      [key: string]: unknown
    }>
    outside_content?: string
    align?: "left" | "center" | string
    image_first?: boolean
    image_count?: number
    max_image_width?: number | null
    canvas?: {
      items?: Array<{
        id?: string
        type?: "title" | "content" | "image" | string
        ref?: string
        x?: number
        y?: number
        width?: number
        height?: number
        [key: string]: unknown
      }>
      [key: string]: unknown
    }
    [key: string]: unknown
  }
}

export interface PptArtifact {
  kind?: string
  pptx_path?: string
  tex_path?: string
  pptx_url?: string
  tex_url?: string
  tex_content_hash?: string
  slide_count?: number
  source_node_ids?: string[]
  generated_at?: string
  [key: string]: unknown
}

export interface PptSlideLecture {
  index: number
  title?: string
  lecture: string
  skipped: boolean
  sources?: unknown[]
  graph_paths?: unknown[]
  formula_context?: unknown[]
  learning_plan?: unknown
  consistency_report?: ConsistencyReport
}

export interface PptTexGenerateRequest {
  chapter_title?: string
  style?: string
  source_node_id?: string
  source_node_ids?: string[]
  graph_scope?: "subtree" | string
  teacher_guidance?: string
  max_slides?: number
}

export interface PptPreviewResponse {
  success: boolean
  chapter_title: string
  slide_count: number
  slides: PptSlideDetail[]
  full_text: string
  tex_content?: string
  tex_source_file?: string
  editable_model?: EditableSlideModel
  asset_map?: Record<string, CoursewareAsset>
  layout?: EditableSlideModel["layout"]
  source_tex?: string
  warning?: string
  error?: string
}

export interface PptTexGenerateResponse extends PptPreviewResponse {
  tex_content?: string
  ppt_artifact?: PptArtifact | null
  learning_plan?: unknown
  graph_paths?: unknown[]
  formula_context?: unknown[]
  source_node_id?: string | null
  source_node_ids?: string[]
  source_scope?: GraphSourceScope | null
  style?: string
  model?: string
  generated_at?: string
  message?: string
}

export interface GenerateSlideLecturesRequest {
  chapter_title?: string
  slides: PptSlideDetail[]
  tex_content?: string
  style?: string
  source_node_id?: string
  source_node_ids?: string[]
  graph_scope?: "subtree" | string
  teacher_guidance?: string
  ppt_source_node_ids?: string[]
  ppt_source_scope?: GraphSourceScope | null
}

export interface SourceDriftReport {
  status?: "aligned" | "changed" | "unknown" | string
  changed?: boolean
  added_node_ids?: string[]
  removed_node_ids?: string[]
  ppt_source_node_ids?: string[]
  lecture_source_node_ids?: string[]
  warning?: string
}

export interface PptUploadResponse extends PptTexGenerateResponse {
  lecture_content: string
  slide_lectures: PptSlideLecture[]
  consistency_report?: ConsistencyReport
  drift_report?: SourceDriftReport
  ppt_source_node_ids?: string[]
  lecture_source_node_ids?: string[]
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
