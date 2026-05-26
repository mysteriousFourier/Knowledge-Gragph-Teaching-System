from __future__ import annotations

import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from KGTS.education.courseware_style import build_style_reference_guidance, build_style_reference_profile
from KGTS.education.router import _merge_existing_slide_lectures, _normalize_target_slide_indices


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

    def test_target_slide_indices_rejects_missing_slide(self):
        with self.assertRaises(Exception):
            _normalize_target_slide_indices([4], [{"index": 1}, {"index": 2}])


if __name__ == "__main__":
    unittest.main()
