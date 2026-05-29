from __future__ import annotations

import base64
import io
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import KGTS.education.courseware_editor as editor
from KGTS.education.ppt_parser import build_ppt_lecture_prompt_data, parse_courseware


TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _overlap_area(left: dict, right: dict) -> float:
    left_x2 = float(left["x"]) + float(left["width"])
    left_y2 = float(left["y"]) + float(left["height"])
    right_x2 = float(right["x"]) + float(right["width"])
    right_y2 = float(right["y"]) + float(right["height"])
    return max(0.0, min(left_x2, right_x2) - max(float(left["x"]), float(right["x"]))) * max(
        0.0,
        min(left_y2, right_y2) - max(float(left["y"]), float(right["y"])),
    )


class CoursewareEditorTest(unittest.TestCase):
    def test_build_editable_model_extracts_objects_and_assets(self):
        tex = r"""
\documentclass{beamer}
\begin{document}
\begin{frame}{Figure 26.2}
  \begin{itemize}
    \item Selection response
  \end{itemize}
  \[
  R = h^2 S
  \]
  \includegraphics[width=0.5\textwidth]{fig/chart}
\end{frame}
\end{document}
"""
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("main.tex", tex)
            archive.writestr("fig/chart.png", TINY_PNG)

        parsed = parse_courseware(payload.getvalue(), "lecture.zip")
        prompt = build_ppt_lecture_prompt_data(parsed)
        model = editor.build_editable_model(parsed, prompt)

        self.assertEqual(model["slide_count"], 1)
        self.assertTrue(model["assets"])
        objects = model["slides"][0]["objects"]
        object_types = {item["type"] for item in objects}
        self.assertIn("title", object_types)
        self.assertIn("richText", object_types)
        self.assertIn("equation", object_types)
        self.assertIn("image", object_types)
        body = next(item for item in objects if item["type"] == "richText")
        equation = next(item for item in objects if item["type"] == "equation")
        image = next(item for item in objects if item["type"] == "image")
        self.assertLess(body["bbox"]["height"], 140)
        self.assertGreater(equation["bbox"]["y"], body["bbox"]["y"] + body["bbox"]["height"])
        self.assertEqual(equation["style"]["fontSize"], 24)
        self.assertEqual(equation["style"]["lineHeight"], 1.25)
        self.assertGreater(image["bbox"]["x"], equation["bbox"]["x"])
        self.assertEqual(image["width_ratio"], 0.5)

    def test_assets_from_zip_keeps_aliases_and_data_uri(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("images/Figure-26.2.PNG", TINY_PNG)

        assets = editor.assets_from_upload(payload.getvalue(), "figures.zip")
        asset = next(iter(assets.values()))

        self.assertEqual(asset["source_path"], "images/Figure-26.2.PNG")
        self.assertIn("Figure-26.2", asset["aliases"])
        self.assertTrue(asset["data_uri"].startswith("data:image/png;base64,"))

    def test_serialize_model_to_tex_round_trips_layout_metadata(self):
        tex = r"""
\documentclass{beamer}
\begin{document}
\begin{frame}{Canvas}
  \begin{itemize}
    \item Old text
  \end{itemize}
\end{frame}
\end{document}
"""
        parsed = parse_courseware(tex.encode("utf-8"), "edited.tex")
        prompt = build_ppt_lecture_prompt_data(parsed)
        model = editor.build_editable_model(parsed, prompt)
        body = next(item for item in model["slides"][0]["objects"] if item["type"] == "richText")
        body["text"] = "- New text"
        body["bbox"]["x"] = 222

        serialized = editor.serialize_editable_model_to_tex(model, title="Deck")
        reparsed = parse_courseware(serialized.encode("utf-8"), "edited.tex")
        slide = build_ppt_lecture_prompt_data(reparsed)["slide_details"][0]

        self.assertIn("New text", serialized)
        self.assertIn("% KGTS_LAYOUT", serialized)
        self.assertEqual(slide["layout"]["canvas"]["items"][1]["x"], 222)

    def test_layout_metadata_keeps_manual_canvas_positions(self):
        tex = r"""
\documentclass{beamer}
\begin{document}
\begin{frame}{Manual}
% KGTS_LAYOUT {"items":[{"id":"title","type":"title","x":48,"y":34,"width":904,"height":58},{"id":"body","type":"content","x":222,"y":130,"width":444,"height":80}]}
\begin{itemize}
\item Manual text
\end{itemize}
\end{frame}
\end{document}
"""
        parsed = parse_courseware(tex.encode("utf-8"), "manual.tex")
        prompt = build_ppt_lecture_prompt_data(parsed)
        model = editor.build_editable_model(parsed, prompt)
        body = next(item for item in model["slides"][0]["objects"] if item["type"] == "richText")

        self.assertEqual(body["bbox"]["x"], 222)
        self.assertEqual(body["bbox"]["width"], 444)

    def test_custom_image_macro_and_callout_do_not_overlap_content(self):
        tex = r"""
\documentclass{beamer}
\usepackage{tikz}
\newcommand{\safecontentimage}[1]{\IfFileExists{#1}{\includegraphics[width=0.7\textwidth]{#1}}{\fbox{\parbox[c][0.34\textheight][c]{0.7\textwidth}{Missing image\\\texttt{\detokenize{#1}}}}}}
\begin{document}
\begin{frame}{Figure 27.1}
  \centering
  \safecontentimage{fig/27.1.png}
  \begin{center}
    \parbox{0.95\textwidth}{\scriptsize Fisher caption with inline math $r$, $x$, and $\theta$.}
  \end{center}
\end{frame}
\begin{frame}{Fisher Scaling Parameter}
  \begin{itemize}
    \item Inline variables $n$, $p_b$, and $x$ stay in the body.
  \end{itemize}
  \[
    x = \frac{r\sqrt{n}}{2d}
  \]
  \[
    p_b = 1 - \Phi(x)
  \]
  \begin{tikzpicture}[remember picture, overlay]
    \node[rectangle callout, draw=blue, fill=white, text width=2.20cm, align=center] at ([xshift=10.41cm,yshift=-3.63cm] current page.north west)
      {$p_b$ 仅依赖于 $x$};
  \end{tikzpicture}
\end{frame}
\end{document}
"""
        parsed = parse_courseware(tex.encode("utf-8"), "edited.tex")
        prompt = build_ppt_lecture_prompt_data(parsed)
        model = editor.build_editable_model(parsed, prompt)

        figure_objects = model["slides"][0]["objects"]
        figure_types = [item["type"] for item in figure_objects]
        self.assertEqual(figure_types.count("image"), 1)
        self.assertEqual(figure_types.count("placeholder"), 0)
        self.assertNotIn("equation", figure_types)
        figure_image = next(item for item in figure_objects if item["type"] == "image")
        self.assertEqual(figure_image["source_path"], "figures/fig_0132.png")
        figure_body = next(item for item in figure_objects if item["type"] == "richText")
        self.assertGreaterEqual(figure_body["bbox"]["y"], figure_image["bbox"]["y"] + figure_image["bbox"]["height"])

        callout_objects = model["slides"][1]["objects"]
        self.assertEqual([item["type"] for item in callout_objects].count("equation"), 2)
        callout = next(item for item in callout_objects if item["type"] == "callout")
        for item in callout_objects:
            if item["id"] == callout["id"] or item["type"] == "title":
                continue
            self.assertEqual(_overlap_area(callout["bbox"], item["bbox"]), 0)

    def test_project_save_and_pptx_export(self):
        old_project_dir = editor.PROJECT_DIR
        old_artifact_dir = editor.ARTIFACT_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            editor.PROJECT_DIR = Path(temp_dir) / "projects"
            editor.ARTIFACT_DIR = Path(temp_dir) / "artifacts"
            try:
                model = editor.build_editable_model_from_slide_details(
                    [
                        {
                            "index": 1,
                            "title": "One",
                            "content": "- A",
                            "body_texts": ["A"],
                            "images": [],
                            "tables": [],
                        }
                    ],
                    title="Deck",
                )
                project = editor.save_courseware_project({"title": "Deck", "editable_model": model})
                loaded = editor.load_courseware_project(project["id"])
                artifact = editor.build_pptx_artifact_from_editable_model("Deck", model)

                self.assertEqual(loaded["title"], "Deck")
                self.assertTrue(Path(artifact["pptx_path"]).exists())
                self.assertTrue(Path(artifact["tex_path"]).exists())
            finally:
                editor.PROJECT_DIR = old_project_dir
                editor.ARTIFACT_DIR = old_artifact_dir

    def test_project_save_preserves_uploaded_source_tex_from_model(self):
        old_project_dir = editor.PROJECT_DIR
        with tempfile.TemporaryDirectory() as temp_dir:
            editor.PROJECT_DIR = Path(temp_dir) / "projects"
            try:
                model = editor.build_editable_model_from_slide_details(
                    [{"index": 1, "title": "One", "content": "A"}],
                    title="Deck",
                    source_tex="\\documentclass{beamer}\n\\begin{document}\n\\end{document}",
                )

                project = editor.save_courseware_project({"title": "Deck", "editable_model": model})
                loaded = editor.load_courseware_project(project["id"])

                self.assertIn("\\documentclass{beamer}", loaded["tex_content"])
                self.assertEqual(loaded["editable_model"]["source_tex"], loaded["tex_content"])
            finally:
                editor.PROJECT_DIR = old_project_dir


if __name__ == "__main__":
    unittest.main()
