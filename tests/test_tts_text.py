from KGTS.core.tts_text import normalize_tts_text


def test_normalize_tts_text_replaces_gpt_sovits_unsafe_cjk() -> None:
    unsafe_text = "兙兡呣嗯嗧噷桛烪瓧瓰瓱瓼甅"

    normalized = normalize_tts_text(unsafe_text, "all_zh").normalized_text

    assert normalized == "克百克母恩加仑亨线轴火十瓦分瓦毫瓦厘瓦厘米。"
    assert not any(char in normalized for char in unsafe_text)


def test_normalize_tts_text_speaks_common_math_symbols() -> None:
    normalized = normalize_tts_text("固定概率≤86%，p₀→1；QTL 等位基因。", "all_zh").normalized_text

    assert "小于等于" in normalized
    assert "百分之" in normalized
    assert "到" in normalized
    assert "丘提艾勒" in normalized


def test_normalize_tts_text_preserves_chinese_pause_punctuation() -> None:
    normalized = normalize_tts_text("同学们,今天看选择:它会持续吗?", "zh").normalized_text

    assert normalized == "同学们，今天看选择：它会持续吗？"


def test_normalize_tts_text_adds_pauses_for_markdown_structure() -> None:
    normalized = normalize_tts_text(
        "## 标题\n\n- 第一点：选择会改变频率\n- 第二点：漂移会带来随机性",
        "zh",
    ).normalized_text

    assert normalized == "标题。第一点：选择会改变频率。第二点：漂移会带来随机性。"


def test_normalize_tts_text_adds_pause_around_symbol_speech() -> None:
    normalized = normalize_tts_text("固定概率≤86%，p₀→1；QTL 等位基因。", "zh").normalized_text

    assert "固定概率，小于等于，86，百分之，" in normalized
    assert "p0，到，1" in normalized


def test_normalize_tts_text_turns_prose_dashes_into_pauses() -> None:
    normalized = normalize_tts_text("选择——漂移；选择—迁移。", "zh").normalized_text

    assert normalized == "选择。漂移；选择，迁移。"
    assert "-" not in normalized


def test_normalize_tts_text_speaks_unwrapped_formulas() -> None:
    normalized = normalize_tts_text(r"条件是 p_0 > 1/(2Ns)，所以 P_{\text{fix}} 增加。", "all_zh").normalized_text

    assert "批 下标 0 大于 1 除以 左括号 2 恩艾斯 右括号" in normalized
    assert "批 下标 艾弗艾艾克斯" in normalized
    assert r"\text" not in normalized
