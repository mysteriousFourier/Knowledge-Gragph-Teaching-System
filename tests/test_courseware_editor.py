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


if __name__ == "__main__":
    unittest.main()
