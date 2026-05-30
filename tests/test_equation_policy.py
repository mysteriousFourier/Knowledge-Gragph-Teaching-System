import tempfile
import unittest
import base64
from pathlib import Path

from education import beamer_full_router as router
from education.beamer_generator_full.latex_parser import parse_latex_to_slides


class EquationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_index = router.EQUATION_INDEX_PATH
        self.old_saved = router.SAVED_PROJECT_DIR
        router.EQUATION_INDEX_PATH = Path(self.tmp.name) / "equation_index.json"
        router.SAVED_PROJECT_DIR = Path(self.tmp.name) / "saved_projects"
        router.SAVED_PROJECT_DIR.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        router.EQUATION_INDEX_PATH = self.old_index
        router.SAVED_PROJECT_DIR = self.old_saved
        self.tmp.cleanup()

    def test_missing_numbered_equation_is_marked(self):
        latex = (
            "\\documentclass{beamer}\n"
            "\\begin{document}\n"
            "\\begin{frame}{A}\n"
            "Equation 27.1 explains the response.\n"
            "\\end{frame}\n"
            "\\end{document}\n"
        )
        marked, missing, resolved = router._apply_equation_reference_policy(latex)
        self.assertFalse(resolved)
        self.assertEqual([item["key"] for item in missing], ["num:27.1"])
        self.assertIn("\\kgmissingequation{num:27.1}{Equation 27.1}", marked)

        parsed = parse_latex_to_slides(marked)
        self.assertEqual(parsed["slides"][0]["missing_equations"][0]["key"], "num:27.1")

    def test_supplement_source_resolves_missing_equation(self):
        latex = (
            "\\documentclass{beamer}\n"
            "\\begin{document}\n"
            "\\begin{frame}{A}\n"
            "Equation 27.1 explains the response.\n"
            "\\end{frame}\n"
            "\\end{document}\n"
        )
        source = "Equation 27.1\n\\[\nR = h^2 S\n\\]\n"
        resolved_latex, missing, resolved = router._apply_equation_reference_policy(
            latex,
            source=source,
            source_id="chapter27",
            source_title="chapter27",
        )
        self.assertFalse(missing)
        self.assertEqual(resolved, ["Equation 27.1"])
        self.assertIn("R = h^2 S", resolved_latex)
        self.assertNotIn("\\begin{alertblock}{缺失公式}", resolved_latex)

    def test_image_frame_layout_uses_orientation(self):
        def png_data_url(width, height):
            data = (
                b"\x89PNG\r\n\x1a\n"
                + b"\x00\x00\x00\rIHDR"
                + int(width).to_bytes(4, "big")
                + int(height).to_bytes(4, "big")
                + b"\x08\x02\x00\x00\x00"
            )
            return "data:image/png;base64," + base64.b64encode(data).decode("ascii")

        horizontal = (
            "\\begin{frame}{A}\n"
            "\\includegraphics[width=200px]{fig/图25_1.png}\n"
            "Figure 25.1 横向图说明。\n"
            "\\end{frame}"
        )
        vertical = (
            "\\begin{frame}{B}\n"
            "\\includegraphics[width=200px]{fig/图25_2.png}\n"
            "Figure 25.2 竖向图说明。\n"
            "\\end{frame}"
        )
        out_h = router._enforce_top_image_bottom_text_layout(
            horizontal,
            {"Figure 25.1": png_data_url(800, 300)},
        )
        out_v = router._enforce_top_image_bottom_text_layout(
            vertical,
            {"Figure 25.2": png_data_url(300, 800)},
        )
        self.assertIn("\\begin{frame}{上图下文}", out_h)
        self.assertIn("\\includegraphics[width=0.7\\textwidth]{fig/图25_1.png}", out_h)
        self.assertIn("\\begin{frame}{左图右文}", out_v)
        self.assertIn("\\includegraphics[width=\\textwidth]{fig/图25_2.png}", out_v)


if __name__ == "__main__":
    unittest.main()
