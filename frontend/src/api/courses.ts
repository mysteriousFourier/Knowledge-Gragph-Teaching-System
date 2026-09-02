import { useMutation, useQuery } from "@tanstack/react-query"
import { educationClient } from "./client"
import type { Course, CourseInput } from "@/types/course"

export const useCourses = () =>
  useQuery({
    queryKey: ["courses"],
    queryFn: () => educationClient.get<{ success: boolean; courses: Course[] }>("/api/education/courses").then((response) => response.data),
  })

export const useCreateCourse = () =>
  useMutation({
    mutationFn: (input: CourseInput) =>
      educationClient.post<{ success: boolean; course: Course }>("/api/education/courses", input).then((response) => response.data),
  })

export const useUpdateCourse = () =>
  useMutation({
    mutationFn: ({ courseId, ...input }: CourseInput & { courseId: string }) =>
      educationClient.patch<{ success: boolean; course: Course }>(`/api/education/courses/${encodeURIComponent(courseId)}`, input).then((response) => response.data),
  })

export const useDeleteCourse = () =>
  useMutation({
    mutationFn: (courseId: string) =>
      educationClient.delete<{ success: boolean; course_id: string }>(`/api/education/courses/${encodeURIComponent(courseId)}`).then((response) => response.data),
  })
