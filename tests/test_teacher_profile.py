from __future__ import annotations

from KGTS.education.teacher_profile import (
    clean_transcript_segments,
    format_teacher_profile_guidance,
    get_teacher_profile,
    merge_teacher_guidance,
)


def test_profile_matches_current_polygenic_course_title() -> None:
    profile = get_teacher_profile(title="Evolutionary Theory on Polygenic Trait")

    assert profile is not None
    assert profile["profile_id"] == "bimsa_quant_genetics"


def test_profile_does_not_match_unrelated_course() -> None:
    assert get_teacher_profile(title="Linear Algebra") is None


def test_blackboard_cleaning_keeps_independent_conclusion() -> None:
    segments = [
        {"start": "00:00:01", "text": "这里我们画一个坐标轴，再把曲线画出来。这个结论说明选择会改变均值。"},
        {"start": "00:00:10", "text": "复杂概念先用例子解释。"},
    ]

    cleaned, stats = clean_transcript_segments(segments)

    assert stats["removed_blackboard_segments"] == 1
    assert cleaned[0]["text"] == "这个结论说明选择会改变均值。"
    assert cleaned[1]["text"] == "复杂概念先用例子解释。"


def test_guidance_prioritizes_blackboard_and_graph_rules() -> None:
    guidance, profile = merge_teacher_guidance(
        "本页重点讲公式假设。",
        title="Evolutionary Theory on Polygenic Trait",
    )

    assert profile is not None
    assert "硬性禁止" in guidance
    assert "不要生成‘请看黑板’" in guidance
    assert "课件到讲稿扩展" in guidance
    assert "短标题或项目符号" in guidance
    assert "知识图谱扩展" in guidance
    assert "当前 TeX 页" in guidance
    assert "教师本次补充要求" in guidance
    assert guidance.index("硬性禁止") < guidance.index("教师本次补充要求")


def test_profile_guidance_excludes_audit_evidence() -> None:
    profile = get_teacher_profile(title="定量遗传学")
    guidance = format_teacher_profile_guidance(profile)

    assert "evidence" not in guidance
    assert "source_directories" not in guidance


def test_profile_matches_parent_course_when_lesson_title_is_generic(monkeypatch) -> None:
    from KGTS.education import router
    monkeypatch.setattr(router.course_store, "get", lambda course_id: {
        "id": course_id, "title": "Evolutionary Theory on Polygenic Trait",
    })
    guidance, profile = router._resolve_teacher_guidance(
        "Focus on assumptions", course_id="course_new", title="Lesson 1",
    )
    assert profile["profile_id"] == "bimsa_quant_genetics"
    assert "Focus on assumptions" in guidance
