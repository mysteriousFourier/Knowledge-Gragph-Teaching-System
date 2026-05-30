from __future__ import annotations

import io
import os
import sys
import unittest
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.education.claude_api import _extract_deepseek_response_text, _format_deepseek_http_error
from KGTS.education.courseware_style import build_style_reference_guidance, build_style_reference_profile
from KGTS.education.kg_constraints import clean_generated_lecture_output
from KGTS.education.router import (
    _apply_model_slide_lecture_allocations,
    _build_slide_lecture_pacing,
    _merge_existing_slide_lectures,
    _nonempty_slide_lecture_count,
    _normalize_target_slide_indices,
    _slide_lecture_read_timeout,
    _slide_lecture_concurrency,
    _slide_lecture_error_summary,
)
from KGTS.models.education import GenerateSlideLecturesRequest


class CoursewareStyleTest(unittest.TestCase):
    def test_beamer_zip_style_profile_extracts_compact_reference(self):
        tex = r"""
\documentclass[10pt, aspectratio=169]{ctexbeamer}
\usetheme{Madrid}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{tikz}
\definecolor{myline}{RGB}{0,116,112}
\setbeamertemplate{frametitle}{%
  \begin{tikzpicture}[remember picture, overlay]
    \draw[myline, line width=1.5pt] ([yshift=-1.3cm] current page.north west) -- ([yshift=-1.3cm] current page.north east);
  \end{tikzpicture}
}
\setbeamertemplate{title page}{%
  \node[fill=white, text=black] {\inserttitle};
  \includegraphics[height=39pt]{fig/logo.png}
}
\begin{document}
\begin{frame}{Review}
  \begin{itemize}
    \setlength{\itemsep}{0.3\baselineskip}
    \item \textcolor{black}{Selection and drift}
  \end{itemize}
\end{frame}
\begin{frame}{Figure}
  \includegraphics[width=0.6\textwidth]{fig/chart}
\end{frame}
\end{document}
"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("main.tex", tex)
            archive.writestr("fig/logo.png", b"png")
            archive.writestr("fig/chart.png", b"png")

        result = build_style_reference_profile(payload.getvalue(), "reference.zip")
        profile = result["profile"]

        self.assertTrue(result["success"])
        self.assertEqual(profile["document_class"], "ctexbeamer")
        self.assertIn("aspectratio=169", profile["document_options"])
        self.assertIn("usetheme:Madrid", profile["themes"])
        self.assertIn("frametitle", profile["beamertemplates"])
        self.assertIn("thin top rule under frame titles", profile["style_signals"])
        self.assertIn("custom title page with institutional logos", profile["style_signals"])
        self.assertEqual(profile["archive_image_count"], 2)
        self.assertLessEqual(len(result["guidance"]), 2000)

    def test_style_guidance_can_be_built_from_profile_only(self):
        guidance = build_style_reference_guidance(
            {
                "profile": {
                    "document_class": "ctexbeamer",
                    "document_options": ["10pt", "aspectratio=169"],
                    "themes": ["usetheme:Madrid"],
                    "style_signals": ["thin top rule under frame titles"],
                }
            }
        )

        self.assertIn("ctexbeamer", guidance)
        self.assertIn("Madrid", guidance)
        self.assertIn("thin top rule", guidance)

    def test_selected_slide_regeneration_merges_existing_lectures(self):
        slides = [
            {"index": 1, "title": "One"},
            {"index": 2, "title": "Two"},
            {"index": 3, "title": "Three"},
        ]
        existing = [
            {"index": 1, "title": "One", "lecture": "old one", "skipped": False},
            {"index": 2, "title": "Two", "lecture": "old two", "skipped": False},
            {"index": 3, "title": "Three", "lecture": "old three", "skipped": False},
        ]
        generated = [{"index": 2, "title": "Two", "lecture": "new two", "skipped": False}]

        merged = _merge_existing_slide_lectures(existing, generated, slides)

        self.assertEqual([item["lecture"] for item in merged], ["old one", "new two", "old three"])

    def test_slide_lecture_request_accepts_duration_budget(self):
        request = GenerateSlideLecturesRequest(
            slides=[{"index": 1, "title": "One"}],
            target_duration_minutes=15,
            speech_rate_cpm=250,
        )

        self.assertEqual(request.target_duration_minutes, 15)
        self.assertEqual(request.speech_rate_cpm, 250)

    def test_slide_lecture_concurrency_is_bounded(self):
        old_value = os.environ.get("KGTS_SLIDE_LECTURE_CONCURRENCY")
        try:
            os.environ["KGTS_SLIDE_LECTURE_CONCURRENCY"] = "12"
            self.assertEqual(_slide_lecture_concurrency(), 6)
            os.environ["KGTS_SLIDE_LECTURE_CONCURRENCY"] = "0"
            self.assertEqual(_slide_lecture_concurrency(), 1)
            os.environ["KGTS_SLIDE_LECTURE_CONCURRENCY"] = "bad"
            self.assertEqual(_slide_lecture_concurrency(), 3)
        finally:
            if old_value is None:
                os.environ.pop("KGTS_SLIDE_LECTURE_CONCURRENCY", None)
            else:
                os.environ["KGTS_SLIDE_LECTURE_CONCURRENCY"] = old_value

    def test_slide_lecture_timeout_can_be_disabled_for_experiments(self):
        old_value = os.environ.get("KGTS_SLIDE_LECTURE_READ_TIMEOUT_SECONDS")
        try:
            os.environ["KGTS_SLIDE_LECTURE_READ_TIMEOUT_SECONDS"] = "0"
            self.assertIsNone(_slide_lecture_read_timeout("initial"))
            os.environ["KGTS_SLIDE_LECTURE_READ_TIMEOUT_SECONDS"] = "120"
            self.assertEqual(_slide_lecture_read_timeout("initial"), 120)
        finally:
            if old_value is None:
                os.environ.pop("KGTS_SLIDE_LECTURE_READ_TIMEOUT_SECONDS", None)
            else:
                os.environ["KGTS_SLIDE_LECTURE_READ_TIMEOUT_SECONDS"] = old_value

    def test_slide_lecture_pacing_allocates_total_character_budget(self):
        slides = [
            {"index": 1, "title": "Title"},
            {"index": 2, "title": "Dense", "content": "这是一个包含较多课堂内容的页面，用于验证权重分配。" * 8},
            {"index": 3, "title": "Empty", "content": ""},
        ]

        pacing = _build_slide_lecture_pacing(
            slides,
            target_duration_minutes=10,
            speech_rate_cpm=250,
        )

        self.assertEqual(pacing["total_target_chars"], 2500)
        self.assertEqual(sum(item["target_chars"] for item in pacing["slides"].values()), 2500)
        self.assertLess(pacing["slides"][3]["target_chars"], pacing["slides"][2]["target_chars"])
        self.assertIn("target_duration_seconds", pacing["slides"][2])

    def test_model_slide_lecture_allocations_keep_total_budget(self):
        base = _build_slide_lecture_pacing(
            [
                {"index": 1, "title": "Intro", "content": "短页"},
                {"index": 2, "title": "Dense", "content": "内容较多" * 80},
            ],
            target_duration_minutes=2,
            speech_rate_cpm=250,
        )

        planned = _apply_model_slide_lecture_allocations(
            base,
            {"slides": [{"index": 1, "target_chars": 80}, {"index": 2, "target_chars": 800}]},
        )

        self.assertEqual(planned["total_target_chars"], base["total_target_chars"])
        self.assertEqual(sum(item["target_chars"] for item in planned["slides"].values()), 500)
        self.assertEqual(planned["slides"][1]["budget_source"], "deepseek-v4-pro")

    def test_selected_slide_regeneration_preserves_other_metadata(self):
        slides = [{"index": 1, "title": "One"}, {"index": 2, "title": "Two"}]
        existing = [
            {"index": 1, "title": "One", "lecture": "old one", "target_chars": 100, "estimated_chars": 80},
            {"index": 2, "title": "Two", "lecture": "old two", "target_chars": 120, "estimated_chars": 90},
        ]
        generated = [
            {"index": 2, "title": "Two", "lecture": "new two", "target_chars": 250, "estimated_chars": 230},
        ]

        merged = _merge_existing_slide_lectures(existing, generated, slides)

        self.assertEqual(merged[0]["target_chars"], 100)
        self.assertEqual(merged[1]["target_chars"], 250)

    def test_target_slide_indices_rejects_missing_slide(self):
        with self.assertRaises(Exception):
            _normalize_target_slide_indices([4], [{"index": 1}, {"index": 2}])

    def test_empty_slide_lecture_helpers_surface_failures(self):
        lectures = [
            {"index": 1, "lecture": "", "error": "timeout"},
            {"index": 2, "lecture": "有效讲稿", "error": ""},
        ]

        self.assertEqual(_nonempty_slide_lecture_count(lectures), 1)
        self.assertIn("第 1 页：timeout", _slide_lecture_error_summary(lectures))

    def test_deepseek_auth_error_is_actionable_and_redacted(self):
        response = httpx.Response(
            401,
            json={
                "error": {
                    "message": "Authentication Fails, Your api key: ****d3ec is invalid",
                    "code": "invalid_request_error",
                }
            },
            request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
        )

        message = _format_deepseek_http_error(response)

        self.assertIn("DeepSeek API 鉴权失败", message)
        self.assertIn("设置", message)
        self.assertNotIn("d3ec", message)

    def test_deepseek_non_auth_error_is_redacted(self):
        response = httpx.Response(
            400,
            json={"error": {"message": "bad request with api key: sk-testsecret123456"}},
            request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"),
        )

        message = _format_deepseek_http_error(response)

        self.assertIn("HTTP 400", message)
        self.assertNotIn("sk-testsecret123456", message)

    def test_deepseek_empty_content_reports_finish_reason(self):
        with self.assertRaisesRegex(Exception, "finish_reason=stop"):
            _extract_deepseek_response_text({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]})

    def test_deepseek_content_list_is_extracted(self):
        text = _extract_deepseek_response_text(
            {"choices": [{"message": {"content": [{"type": "text", "text": "有效讲稿"}]}}]}
        )

        self.assertEqual(text, "有效讲稿")

    def test_clean_lecture_output_does_not_delete_everything(self):
        raw = "AI补充\n这是一段有效讲解。"

        self.assertEqual(clean_generated_lecture_output(raw), raw)


if __name__ == "__main__":
    unittest.main()
