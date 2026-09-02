export interface Course {
  id: string
  title: string
  description?: string
  chapter_count?: number
  courseware_count?: number
  created_at?: string
  updated_at?: string
}

export interface CourseInput {
  title: string
  description?: string
  course_id?: string
}
