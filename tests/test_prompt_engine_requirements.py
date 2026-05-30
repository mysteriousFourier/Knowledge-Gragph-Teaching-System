import tempfile
import unittest
from pathlib import Path

from education.beamer_generator_full.prompt_engine import PromptEngine


class PromptEngineRequirementTests(unittest.TestCase):
    def _engine(self) -> PromptEngine:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        prompt_path = Path(temp_dir.name) / "system_prompt.txt"
        prompt_path.write_text("BASE PROMPT", encoding="utf-8")
        return PromptEngine(str(prompt_path))

    def test_free_requirements_are_converted_to_teaching_strategy(self):
        engine = self._engine()
        requirement = "多生成一些参照事例，且知识点用比较浅显易懂的方式展开。不要生硬罗列要点，要聚焦本章。"

        system_prompt = engine.build_system_prompt(custom_requirements=requirement, slide_count=7)
        user_prompt = engine.build_user_prompt("Chapter content", custom_requirements=requirement, slide_count=7)

        for prompt in (system_prompt, user_prompt):
            self.assertIn("自由要求执行策略", prompt)
            self.assertIn("示例化要求", prompt)
            self.assertIn("多示例要求", prompt)
            self.assertIn("通俗化要求", prompt)
            self.assertIn("知识点展开要求", prompt)
            self.assertIn("反罗列要求", prompt)
            self.assertIn("章节聚焦要求", prompt)
            self.assertIn("每个主要 section 至少安排 1 页", prompt)
            self.assertIn("直观解释、关键关系、简短例子、回到公式/图谱关系", prompt)
            self.assertIn("问题-解释-例子-小结", prompt)

    def test_formula_explanations_require_blue_callout_annotations(self):
        engine = self._engine()

        system_prompt = engine.build_system_prompt(slide_count=7)
        user_prompt = engine.build_user_prompt("Equation (2.3)", slide_count=7)

        for prompt in (system_prompt, user_prompt):
            self.assertIn("蓝色 rectangle callout 箭头框", prompt)
            self.assertIn("\\tikzmark", prompt)
            self.assertIn("不能生成逐项文字清单", prompt)

    def test_unclassified_free_requirements_keep_fallback_strategy(self):
        engine = self._engine()

        prompt = engine.build_user_prompt(
            "Chapter content",
            custom_requirements="整体更适合课堂讲授",
            slide_count=7,
        )

        self.assertIn("对无法归类的自由要求", prompt)
        self.assertIn("讲解深度、示例数量或排版结构", prompt)


if __name__ == "__main__":
    unittest.main()
