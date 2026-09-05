"""Extract a compact teacher pedagogy profile from TeX and timestamped speech.

Usage (from KGTS):
  python scripts/extract_teacher_pedagogy.py ..\250929-bimsa-01_editable ..\260303-bimsa-01_editable
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from KGTS.education.ppt_parser import parse_text_courseware  # noqa: E402
from KGTS.education.teacher_profile import clean_transcript_segments  # noqa: E402


TIMESTAMP_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)\s*-\s*(\d\d:\d\d:\d\d)\]\s*(.*)$")
FEATURE_PATTERNS = {
    "review_and_positioning": ("上一次", "上学期", "回顾", "我们已经", "前面"),
    "core_questions": ("问题是什么", "为什么", "核心问题", "要回答", "如何解释"),
    "definitions": ("称之为", "叫做", "概念", "定义", "也就是说"),
    "examples_and_analogies": ("比如", "举个例子", "类比", "就像", "不妨", "猫", "姚明"),
    "history_and_debate": ("历史", "达尔文", "Fisher", "争论", "综合", "学者", "理论"),
    "caveats": ("但是", "不过", "并不", "不一定", "仅供参考", "仍然", "未必"),
    "open_issues": ("开放", "未来", "尚未", "难以解释", "需要解决", "研究方向"),
    "student_prompts": ("大家", "同学", "你会", "想一想", "注意", "希望大家"),
    "reading_guidance": ("书", "教材", "阅读", "参考", "推荐"),
}


def _parse_time(value: str) -> int:
    h, m, s = (int(item) for item in value.split(":"))
    return h * 3600 + m * 60 + s


def read_transcript(path: Path) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = TIMESTAMP_RE.match(line.strip())
        if not match:
            continue
        start, end, text = match.groups()
        segments.append({"start": start, "end": end, "start_seconds": _parse_time(start), "text": text.strip()})
    return segments


def _sentences(text: str) -> Iterable[str]:
    for sentence in re.split(r"(?<=[。！？!?；;])\s*", text):
        sentence = sentence.strip()
        if sentence:
            yield sentence


def _evidence(segments: List[Dict[str, Any]], needles: Iterable[str], limit: int = 3) -> List[str]:
    result: List[str] = []
    seen = set()
    for segment in segments:
        for sentence in _sentences(str(segment.get("text") or "")):
            if not any(needle.casefold() in sentence.casefold() for needle in needles):
                continue
            clean = sentence[:180]
            if clean not in seen:
                result.append(clean)
                seen.add(clean)
            if len(result) >= limit:
                return result
    return result


def _extract_courseware(path: Path) -> Dict[str, Any]:
    tex_files = sorted(path.glob("*.tex"))
    if not tex_files:
        return {"directory": str(path), "frame_count": 0, "titles": [], "formula_frames": 0, "image_frames": 0}
    tex_path = tex_files[0]
    parsed = parse_text_courseware(tex_path.read_bytes(), tex_path.name)
    slides = parsed.get("slides") or []
    return {
        "directory": path.name,
        "source_tex": tex_path.name,
        "frame_count": len(slides),
        "titles": [str(slide.get("title") or "").strip() for slide in slides if str(slide.get("title") or "").strip()][:20],
        "formula_frames": sum(1 for slide in slides if slide.get("formula_count") or "\\(" in str(slide.get("raw_text") or "")),
        "image_frames": sum(1 for slide in slides if int(slide.get("image_count") or 0) > 0),
    }


def build_profile(directories: List[Path]) -> Dict[str, Any]:
    all_segments: List[Dict[str, Any]] = []
    courseware: List[Dict[str, Any]] = []
    cleanup_stats: List[Dict[str, Any]] = []
    for directory in directories:
        courseware.append(_extract_courseware(directory))
        transcripts = sorted(directory.glob("transcript_*.txt"))
        for transcript in transcripts:
            raw_segments = read_transcript(transcript)
            cleaned, stats = clean_transcript_segments(raw_segments)
            all_segments.extend(cleaned)
            cleanup_stats.append({"source": transcript.name, **stats, "input_segments": len(raw_segments), "kept_segments": len(cleaned)})

    counts = Counter()
    evidence: Dict[str, List[str]] = {}
    for feature, needles in FEATURE_PATTERNS.items():
        hits = [segment for segment in all_segments if any(needle.casefold() in str(segment.get("text") or "").casefold() for needle in needles)]
        counts[feature] = len(hits)
        evidence[feature] = _evidence(all_segments, needles)

    return {
        "profile_id": "bimsa_quant_genetics",
        "display_name": "BIMSA 定量遗传/进化课程教师授课画像",
        "version": 1,
        "course_ids": ["course_test"],
        "title_keywords": ["BIMSA", "定量遗传", "quantitative genetics", "polygenic trait", "evolutionary theory", "微进化", "宏进化", "多基因性状", "进化遗传"],
        "source_directories": [path.name for path in directories],
        "courseware_statistics": courseware,
        "transcript_statistics": {
            "input_segments": sum(item["input_segments"] for item in cleanup_stats),
            "kept_segments": sum(item["kept_segments"] for item in cleanup_stats),
            "features": dict(counts),
            "blackboard_filter": cleanup_stats,
        },
        "lesson_structure": [
            "先回顾前置内容并说明本节在整门课程中的位置，再给学生一个清晰的目标感。",
            "围绕一个核心问题组织内容，用概念定义、机制解释、例子或推导逐步推进。",
            "需要时插入学科史、代表人物和理论争论，但始终回到当前问题。",
            "结尾明确指出结论、理论边界和仍未解决的开放问题。",
        ],
        "generation_rules": [
            "先讲为什么要问这个问题，再讲术语、机制和公式。",
            "复杂概念先用直观类比或反例建立理解，再给出更严格的学术表述。",
            "保留中英文术语、变量和公式；解释公式中当前范围内的符号。",
            "把事实、教师判断和开放猜想分开表述，明确使用‘现有理论’‘一种可能’等限定语。",
            "页面内容少时由口播补足逻辑，但不要重复堆砌页面文字。",
        ],
        "source_to_speech_expansion": [
            "把 TeX 页上的短标题或项目符号展开为‘为什么重要—术语含义—机制或关系—本页结论’，不要逐字复述。",
            "英文术语保留原词，并紧接自然的中文释义；对容易混淆的近义概念做一次对照。",
            "公式页先说明公式回答什么问题，再解释当前页符号、条件和直接推导关系，最后给出直观含义。",
            "图表页只解读屏幕上真实存在的轴、趋势、组别和图注；缺失的图示不得用板书动作补足。",
            "内容跳跃时从知识图谱补一个必要的前置概念或关系桥梁，解释后立即回到当前 TeX 页。",
        ],
        "knowledge_graph_expansion": [
            "始终以当前 TeX 页的标题、文字、公式、表格和图注为讲解锚点，再查询知识图谱扩展。",
            "优先补充页面术语的定义、直接前置概念、机制链路、公式符号与紧邻推导关系。",
            "按教师风格选择少量相关的历史争论、反例、跨学科类比或开放问题，并在解释后回扣当前页。",
            "仅使用检索证据中能支持的内容；不罗列节点名称，不提及‘知识图谱’或内部检索过程。",
            "图谱内容与课件冲突时以当前课程材料为准，并用限定语指出理论边界，不自行补造事实。",
        ],
        "language_rules": [
            "中文口语化、自然停顿，允许适度自我修正和课堂互动语气。",
            "例子应服务于抽象概念，例子之后立即回扣概念或机制。",
            "可以使用生活经验和跨学科类比，但不要让类比替代正式定义。",
        ],
        "open_question_strategy": [
            "主动指出理论与现实之间的鸿沟、争议点和当前解释不足。",
            "把开放问题转成学生可以继续阅读或研究的方向，不伪装成已证实结论。",
        ],
        "forbidden_patterns": [
            "删除或改写所有‘在黑板上写/画/标公式或图’的授课叙述。",
            "不要生成‘请看黑板’‘这里画一个图’‘把这个公式抄下来’等板书依赖指令。",
            "公式、图示和推导必须改成屏幕可读的 Markdown、LaTeX 或文字说明。",
            "不要把口播中的录制闲聊、纯动作和无法确认的转写错误当成教学规则。",
        ],
        "evidence": evidence,
        "notes": "画像由规则统计和人工可读规则组成；板书片段已在统计前删除。",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "teacher_profiles" / "bimsa_quant_genetics.json")
    args = parser.parse_args()
    directories = [path.resolve() for path in args.directories]
    missing = [str(path) for path in directories if not path.is_dir()]
    if missing:
        parser.error("目录不存在: " + ", ".join(missing))
    payload = build_profile(directories)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"success": True, "output": str(output), "kept_segments": payload["transcript_statistics"]["kept_segments"], "removed_blackboard_segments": sum(item["removed_blackboard_segments"] for item in payload["transcript_statistics"]["blackboard_filter"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
