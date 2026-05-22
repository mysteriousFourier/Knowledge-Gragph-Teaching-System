from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GenerateLectureRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    chapter_title: str = Field("", description="Chapter title")
    chapter_content: str = Field("", description="Chapter content")
    style: str = Field("guided", description="Teaching style")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")


class AskQuestionRequest(BaseModel):
    question: str = Field(..., description="Question")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")


class LearningPlanRequest(BaseModel):
    query: str = Field(..., description="Learner question or teacher task")
    chapter_id: Optional[str] = Field(None, description="Chapter ID")
    task: str = Field("qa", description="Task type: qa, lecture, exercise, feedback")
    learning_level: str = Field("beginner", description="Learner level")


class NaturalSupplementRequest(BaseModel):
    original_text: str = Field(..., description="Original text")
    supplement: str = Field(..., description="Supplemental text")
    insert_position: Optional[str] = Field(None, description="Insert position")
    save_draft_if_fail: bool = Field(False, description="Save draft if merge fails")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")


class BeamerGenerateRequest(BaseModel):
    content: str = Field(..., description="Lecture script to convert into Beamer LaTeX")
    style: str = Field("academic", description="Slide style")
    slide_count: int = Field(0, ge=0, le=80, description="Target slide count; 0 means auto")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")


class BeamerParseRequest(BaseModel):
    latex: str = Field(..., description="LaTeX Beamer source")


class BeamerExportRequest(BaseModel):
    slides_data: Dict[str, Any] = Field(..., description="Structured slide data")


class AppConfigUpdateRequest(BaseModel):
    deepseek_api_key: Optional[str] = Field(None, description="DeepSeek API key")
    deepseek_api_base: Optional[str] = Field(None, description="DeepSeek API base URL")
    deepseek_flash_model: Optional[str] = Field(None, description="Flash model")
    deepseek_pro_model: Optional[str] = Field(None, description="Pro model")


class ChapterRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")


class MarkChapterRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    student_id: Optional[str] = Field(None, description="Student ID")
    status: Optional[str] = Field("learned", description="learned, reviewing, forgotten, or reset")


class ResetProgressRequest(BaseModel):
    chapter_id: Optional[str] = Field(None, description="Chapter ID")
    student_id: Optional[str] = Field(None, description="Student ID")


class ExerciseRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")


class CheckAnswerRequest(BaseModel):
    exercise_id: str = Field(..., description="Exercise ID")
    question: str = Field(..., description="Question")
    answer: str = Field(..., description="User answer")
    chapter_id: str = Field(..., description="Chapter ID")
    correct_answer: Optional[str] = Field(None, description="Correct answer")
    explanation: Optional[str] = Field(None, description="Explanation")


class QuestionRequest(BaseModel):
    question: str = Field(..., description="Question")
    student_id: Optional[str] = Field(None, description="Student ID")
    chapter_id: Optional[str] = Field(None, description="Chapter ID")
    context: Optional[str] = Field(None, description="Chapter context")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")


class GenerateReviewRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    count: int = Field(5, description="Review exercise count")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")


class SaveChapterRequest(BaseModel):
    chapter_id: Optional[str] = Field(None, description="Chapter ID")
    title: str = Field(..., description="Chapter title")
    content: Optional[str] = Field(None, description="Chapter content")
    graph_data: Optional[Dict[str, Any]] = Field(None, description="Knowledge graph data")
    source_type: Optional[str] = Field(None, description="Chapter source type")
    ppt_slides: Optional[List[Dict[str, Any]]] = Field(None, description="PPT slide parse result")
    slide_lectures: Optional[List[Dict[str, Any]]] = Field(None, description="PPT slide lectures")


class SaveLectureRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    lecture_content: str = Field(..., description="Lecture content")
    graph_data: Optional[Dict[str, Any]] = Field(None, description="Knowledge graph data")
    source_type: Optional[str] = Field(None, description="Chapter source type")
    ppt_slides: Optional[List[Dict[str, Any]]] = Field(None, description="PPT slide parse result")
    slide_lectures: Optional[List[Dict[str, Any]]] = Field(None, description="PPT slide lectures")
    learning_plan: Optional[Dict[str, Any]] = Field(None, description="Lecture grounding plan")
    consistency_report: Optional[Dict[str, Any]] = Field(None, description="Lecture consistency report")


class GenerateExercisesRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    chapter_title: str = Field("", description="Chapter title")
    chapter_content: str = Field("", description="Chapter content")
    count: int = Field(5, description="Exercise count")
    types: Optional[List[str]] = Field(None, description="Requested exercise types")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")
    force_regenerate: bool = Field(False, description="Force exercise regeneration")


class TeacherExerciseFeedbackRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    exercise_id: str = Field(..., description="Exercise ID")
    rating: str = Field("", description="up, down, or clear")
    feedback: Optional[str] = Field(None, description="Legacy frontend feedback value: like or dislike")
    question: Optional[str] = Field(None, description="Question text snapshot")
    note: Optional[str] = Field(None, description="Optional teacher note")
    scope: Optional[str] = Field("exercise", description="exercise or option")
    feedback_key: Optional[str] = Field(None, description="Stable exercise feedback key")
    option_key: Optional[str] = Field(None, description="Option letter for option feedback")
    option_text: Optional[str] = Field(None, description="Option text snapshot")
    option_feedback_key: Optional[str] = Field(None, description="Stable option feedback key")
    options: Optional[List[Any]] = Field(None, description="Exercise options snapshot")
    correct_answer: Optional[str] = Field(None, description="Correct answer snapshot")


class TeacherRegenerateExercisesRequest(BaseModel):
    chapter_id: str = Field(..., description="Chapter ID")
    chapter_title: Optional[str] = Field(None, description="Chapter title snapshot")
    chapter_content: Optional[str] = Field(None, description="Chapter content snapshot")
    count: int = Field(5, description="Question count")
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")
    force_regenerate: bool = Field(True, description="Force rebuild")


class TeacherRegenerateOptionRequest(TeacherExerciseFeedbackRequest):
    api_key: Optional[str] = Field(None, description="DeepSeek API key")
    model: Optional[str] = Field(None, description="DeepSeek model name")
