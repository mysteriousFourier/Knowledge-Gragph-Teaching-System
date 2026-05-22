export interface Chapter {
  id: string
  title: string
  content?: string
  lecture_content?: string
  lecture_learning_plan?: unknown
  lecture_consistency_report?: import("./education").ConsistencyReport
  source_type?: string
  ppt_slides?: import("./education").PptSlideDetail[]
  slide_lectures?: import("./education").PptSlideLecture[]
  created_at?: string | number
  updated_at?: string | number
  source?: string
  exercise_bank?: Exercise[]
  approved_exercise_bank?: Exercise[]
}

export interface Exercise {
  id: string
  type: "填空题" | "选择题" | "简答题" | string
  question: string
  options?: string[]
  answer?: string
  correct_answer?: string
  explanation?: string
  difficulty?: number
}

export interface SaveChapterRequest {
  chapter_id: string
  title: string
  content?: string
  source_type?: string
  ppt_slides?: import("./education").PptSlideDetail[]
  slide_lectures?: import("./education").PptSlideLecture[]
}

export interface SaveLectureRequest {
  chapter_id: string
  lecture_content: string
  learning_plan?: unknown
  consistency_report?: import("./education").ConsistencyReport
  source_type?: string
  ppt_slides?: import("./education").PptSlideDetail[]
  slide_lectures?: import("./education").PptSlideLecture[]
}
