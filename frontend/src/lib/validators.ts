import { z } from "zod"

export const loginSchema = z.object({
  username: z.string().min(1, "用户名不能为空"),
  password: z.string().min(1, "密码不能为空"),
  role: z.enum(["student", "teacher"]),
})

export type LoginFormData = z.infer<typeof loginSchema>

export const askQuestionSchema = z.object({
  question: z.string().min(1, "问题不能为空"),
  chapter_id: z.string().optional(),
  context: z.string().optional(),
})

export type AskQuestionFormData = z.infer<typeof askQuestionSchema>

export const generateLectureSchema = z.object({
  chapter_content: z.string().optional(),
  chapter_title: z.string().optional(),
  style: z.string().optional(),
  length: z.string().optional(),
  teacher_guidance: z.string().max(2000, "教师建议不能超过 2000 字").optional(),
})

export type GenerateLectureFormData = z.infer<typeof generateLectureSchema>
