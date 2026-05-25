from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FORMULA_POLICY_VERSION = "kgts-formula-speech-v2"


@dataclass(frozen=True)
class NormalizedTtsText:
    original_text: str
    normalized_text: str
    text_lang: str
    formula_policy_version: str = FORMULA_POLICY_VERSION


_GREEK_SPEECH = {
    "alpha": "alpha",
    "beta": "beta",
    "gamma": "gamma",
    "delta": "delta",
    "Delta": "变化量",
    "epsilon": "epsilon",
    "lambda": "lambda",
    "mu": "mu",
    "pi": "pi",
    "sigma": "sigma",
    "theta": "theta",
    "varphi": "phi",
    "phi": "phi",
    "omega": "omega",
}

_LATEX_COMMANDS = {
    "times": "乘以",
    "cdot": "乘以",
    "pm": "正负",
    "le": "小于等于",
    "leq": "小于等于",
    "ge": "大于等于",
    "geq": "大于等于",
    "neq": "不等于",
    "ne": "不等于",
    "approx": "约等于",
    "simeq": "约等于",
    "infty": "无穷大",
    "ldots": "省略",
    "cdots": "省略",
    "ln": "自然对数",
    "log": "对数",
    "exp": "指数函数",
    "Pr": "概率",
    "to": "趋近于",
    "rightarrow": "到",
    "leftarrow": "来自",
    "mid": "条件为",
    "mathbf": "",
    "mathrm": "",
    "text": "",
    "left": "",
    "right": "",
}

_LATIN_LETTER_SPEECH = {
    "a": "诶",
    "b": "比",
    "c": "西",
    "d": "迪",
    "e": "伊",
    "f": "艾弗",
    "g": "吉",
    "h": "艾尺",
    "i": "艾",
    "j": "杰",
    "k": "凯",
    "l": "艾勒",
    "m": "艾姆",
    "n": "恩",
    "o": "欧",
    "p": "批",
    "q": "丘",
    "r": "阿尔",
    "s": "艾斯",
    "t": "提",
    "u": "优",
    "v": "维",
    "w": "达不溜",
    "x": "艾克斯",
    "y": "歪",
    "z": "兹",
}

_LATIN_SYMBOL_SPEECH = {
    "+": "加",
    "#": "井号",
    ".": "点",
    "_": "下划线",
    "-": "杠",
}

_GPT_SOVITS_UNSAFE_CJK_SPEECH = {
    "兙": "克",
    "兡": "百克",
    "呣": "母",
    "嗯": "恩",
    "嗧": "加仑",
    "噷": "亨",
    "桛": "线轴",
    "烪": "火",
    "瓧": "十瓦",
    "瓰": "分瓦",
    "瓱": "毫瓦",
    "瓼": "厘瓦",
    "甅": "厘米",
}

_SYMBOL_SPEECH_REPLACEMENTS = {
    "≤": "小于等于",
    "≥": "大于等于",
    "≈": "约等于",
    "≠": "不等于",
    "∞": "无穷大",
    "√": "根号",
    "∑": "求和",
    "∂": "偏导",
    "→": "到",
    "←": "来自",
    "×": "乘以",
    "÷": "除以",
    "±": "正负",
    "％": "百分之",
    "%": "百分之",
    "℃": "摄氏度",
}

_CJK_PAUSE_SENTINELS = {
    "，": "\ue000",
    "。": "\ue001",
    "；": "\ue002",
    "：": "\ue003",
    "？": "\ue004",
    "！": "\ue005",
    "、": "\ue006",
}
_ASCII_TO_CJK_PAUSES = str.maketrans(
    {
        ",": "，",
        ";": "；",
        ":": "：",
        "?": "？",
        "!": "！",
    }
)
_PAUSE_END_RE = re.compile(r"[，。！？；：、,.!?;:]$")

_PUNCTUATION_NORMALIZATION = str.maketrans(
    {
        "“": "\"",
        "”": "\"",
        "„": "\"",
        "‟": "\"",
        "‘": "'",
        "’": "'",
        "‚": "'",
        "‛": "'",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "「": "\"",
        "」": "\"",
        "『": "\"",
        "』": "\"",
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
    }
)

_BARE_MATH_TOKEN = r"(?:\\[A-Za-z]+|[A-Za-zΑ-Ωα-ω0-9]+(?:_\{[^{}]+\}|_[A-Za-z0-9]+|\^\{[^{}]+\}|\^[A-Za-z0-9+-]+)?|\([^()，。！？；：\s]+\)|\{[^{}]+\})"
_BARE_MATH_EXPR_RE = re.compile(
    rf"(?<![A-Za-z0-9])({_BARE_MATH_TOKEN}(?:\s*(?:<=|>=|≤|≥|=|<|>|\+|-|\*|/)\s*{_BARE_MATH_TOKEN})+)(?![A-Za-z0-9])"
)
_LATEX_SUBSUP_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"([A-Za-z](?:"
    r"_\{\\(?:text|mathrm)\{[^{}]+\}\}|"
    r"\^\{\\(?:text|mathrm)\{[^{}]+\}\}|"
    r"_\{[^{}]+\}|_[A-Za-z0-9]+|"
    r"\^\{[^{}]+\}|\^[A-Za-z0-9+-]+"
    r")+)"
    r"(?![A-Za-z0-9])"
)


def _normalize_unicode_preserving_cjk_pauses(text: str) -> str:
    for punctuation, sentinel in _CJK_PAUSE_SENTINELS.items():
        text = text.replace(punctuation, sentinel)
    text = unicodedata.normalize("NFKC", text)
    for punctuation, sentinel in _CJK_PAUSE_SENTINELS.items():
        text = text.replace(sentinel, punctuation)
    return text


def _restore_cjk_pause_punctuation(text: str) -> str:
    if re.search(r"[\u3400-\u9fff]", text):
        text = text.translate(_ASCII_TO_CJK_PAUSES)
        text = re.sub(r"(?<!\d)\.(?!\d)", "。", text)
    text = re.sub(r"\s*([，。！？；：、])\s*", r"\1", text)
    text = re.sub(r"([，。！？；：、]){2,}", lambda match: match.group(0)[-1], text)
    return text


def _line_with_pause(line: str, *, pause: str = "。") -> str:
    line = line.strip()
    if not line:
        return ""
    if _PAUSE_END_RE.search(line):
        return line
    return f"{line}{pause}"


def _markdown_heading_replacement(match: re.Match[str]) -> str:
    return _line_with_pause(match.group(1), pause="。") + " "


def _markdown_list_replacement(match: re.Match[str]) -> str:
    return _line_with_pause(match.group(1), pause="。") + " "


def _line_breaks_to_pauses(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return text
    return " ".join(_line_with_pause(line, pause="。") for line in lines)


def _speech_with_pause(text: str, *, pause: str = "，") -> str:
    spoken = text.strip()
    if not spoken:
        return spoken
    if _PAUSE_END_RE.search(spoken):
        return spoken
    return f"{spoken}{pause}"


def _replace_prose_dashes(text: str) -> str:
    text = re.sub(r"[\u2014\u2013]{2,}", "。", text)
    text = re.sub(r"(?<=[\u3400-\u9fffA-Za-z])[\u2014\u2013](?=[\u3400-\u9fffA-Za-z])", "，", text)
    text = re.sub(r"(?<=[\u3400-\u9fff])[ \t]+-[ \t]+(?=[\u3400-\u9fff])", "，", text)
    return text


@lru_cache(maxsize=1)
def _formula_library_by_id() -> dict[str, dict[str, object]]:
    library_path = ROOT_DIR / "structured" / "formula_library.json"
    if not library_path.exists():
        return {}
    try:
        data = json.loads(library_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    formulas = data.get("formulas", []) if isinstance(data, dict) else []
    by_id: dict[str, dict[str, object]] = {}
    for item in formulas:
        if isinstance(item, dict) and item.get("id") is not None:
            by_id[str(item["id"])] = item
    return by_id


def _strip_latex_wrappers(expr: str) -> str:
    expr = expr.strip()
    expr = re.sub(r"\\begin\{[^}]+\}", " ", expr)
    expr = re.sub(r"\\end\{[^}]+\}", " ", expr)
    expr = expr.replace("\\\\", " ")
    expr = expr.replace("\\left", "").replace("\\right", "")
    expr = expr.replace("\\,", " ").replace("\\;", " ")
    return expr


def _replace_balanced_command(expr: str, command: str, replacement: str) -> str:
    pattern = re.compile(rf"\\{command}\s*\{{([^{{}}]+)\}}\s*\{{([^{{}}]+)\}}")
    previous = None
    while previous != expr:
        previous = expr
        expr = pattern.sub(lambda match: replacement.format(match.group(1), match.group(2)), expr)
    return expr


def _replace_single_argument_command(expr: str, command: str, replacement: str = "{}") -> str:
    pattern = re.compile(rf"\\{command}\s*\{{([^{{}}]+)\}}")
    previous = None
    while previous != expr:
        previous = expr
        expr = pattern.sub(lambda match: replacement.format(match.group(1)), expr)
    return expr


def latex_to_speech(expr: str) -> str:
    raw_expr = expr.strip()
    expr = _strip_latex_wrappers(raw_expr)
    complex_expr = bool(re.search(r"\\(sum|prod|int|begin|matrix|cases)|\\\\|&", raw_expr))

    expr = _replace_balanced_command(expr, "frac", "{} 除以 {}")
    expr = _replace_balanced_command(expr, "binom", "{} 中取 {} 的组合数")
    for command in ("mathbf", "mathrm", "text", "operatorname", "overline", "bar", "hat", "tilde"):
        expr = _replace_single_argument_command(expr, command)
    expr = re.sub(r"\{([^{}]+)\\over\s+([^{}]+)\}", r"\1 除以 \2", expr)
    expr = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"\1 的平方根", expr)
    expr = re.sub(r"\\sum_\{?([^{}^]+)\}?\^\{?([^{}]+)\}?", r"从 \1 到 \2 的求和", expr)
    expr = re.sub(r"\\prod_\{?([^{}^]+)\}?\^\{?([^{}]+)\}?", r"从 \1 到 \2 的连乘", expr)

    for command, spoken in _GREEK_SPEECH.items():
        if command == "Delta":
            expr = re.sub(r"\\Delta\s*([A-Za-z])", r"\1 的变化量", expr)
        expr = expr.replace(f"\\{command}", spoken)

    for command, spoken in _LATEX_COMMANDS.items():
        expr = expr.replace(f"\\{command}", spoken)

    expr = re.sub(r"([A-Za-z0-9})])_\{([^{}]+)\}", r"\1 下标 \2", expr)
    expr = re.sub(r"([A-Za-z0-9})])_([A-Za-z0-9])", r"\1 下标 \2", expr)
    expr = re.sub(r"([A-Za-z0-9})])\^\{([^{}]+)\}", r"\1 的 \2 次方", expr)
    expr = re.sub(r"([A-Za-z0-9})])\^([A-Za-z0-9+-]+)", r"\1 的 \2 次方", expr)

    replacements = {
        "=": " 等于 ",
        "+": " 加 ",
        "-": " 减 ",
        "*": " 乘以 ",
        "/": " 除以 ",
        "(": " 左括号 ",
        ")": " 右括号 ",
        "[": " 左中括号 ",
        "]": " 右中括号 ",
        "{": " ",
        "}": " ",
        ",": " 逗号 ",
        "|": " 条件为 ",
        "<": " 小于 ",
        ">": " 大于 ",
    }
    for old, new in replacements.items():
        expr = expr.replace(old, new)

    expr = re.sub(r"\\[A-Za-z]+", " ", expr)
    expr = expr.replace("−", " 减 ")
    expr = re.sub(r"[_^&]", " ", expr)
    expr = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", expr)
    expr = re.sub(r"(?<=[A-Za-z])(?=\d)", " ", expr)
    expr = re.sub(r"\s+", " ", expr).strip()
    if not expr:
        return "这里有一个公式。"
    if complex_expr:
        return f"这里有一个公式，表达式为 {expr}。"
    return _speech_with_pause(expr)


def _formula_id_to_speech(formula_id: str) -> str:
    item = _formula_library_by_id().get(formula_id)
    if not item:
        return f"公式 {formula_id}。"
    label = str(item.get("label_format") or formula_id)
    description = item.get("description")
    if isinstance(description, str) and description.strip():
        return f"公式 {label}，{description.strip()}。"
    latex = str(item.get("latex") or "")
    if latex:
        return f"公式 {label}，{latex_to_speech(latex)}"
    return f"公式 {label}。"


def replace_formulas_for_speech(text: str) -> str:
    text = _replace_prose_dashes(text)
    text = re.sub(r"\[\[FORMULA:([^\]]+)\]\]", lambda match: _formula_id_to_speech(match.group(1).strip()), text)
    text = re.sub(r"\$\$(.+?)\$\$", lambda match: latex_to_speech(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"\\\[(.+?)\\\]", lambda match: latex_to_speech(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"\\\((.+?)\\\)", lambda match: latex_to_speech(match.group(1)), text, flags=re.DOTALL)
    text = re.sub(r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)", lambda match: latex_to_speech(match.group(1)), text)
    text = re.sub(r"\\frac\s*\{[^{}]+\}\s*\{[^{}]+\}", lambda match: latex_to_speech(match.group(0)), text)
    text = _BARE_MATH_EXPR_RE.sub(lambda match: latex_to_speech(match.group(1)), text)
    text = _LATEX_SUBSUP_TOKEN_RE.sub(lambda match: latex_to_speech(match.group(1)), text)
    return text


def clean_markdown_for_speech(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)

    processed_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            processed_lines.append("")
            continue
        heading_match = re.match(r"#{1,6}\s*(.+)$", line)
        list_match = re.match(r"(?:[-*+]|\d+\.)\s+(.+)$", line)
        if heading_match:
            processed_lines.append(_line_with_pause(heading_match.group(1), pause="。"))
        elif list_match:
            processed_lines.append(_line_with_pause(list_match.group(1), pause="。"))
        else:
            processed_lines.append(line)
    text = "\n".join(processed_lines)

    text = re.sub(r"[>*_~`|]", " ", text)
    text = text.replace("&nbsp;", " ")
    text = _line_breaks_to_pauses(text)
    return text


def sanitize_gpt_sovits_text(text: str) -> str:
    text = _normalize_unicode_preserving_cjk_pauses(text)
    text = text.translate(_PUNCTUATION_NORMALIZATION)
    for symbol, speech in _SYMBOL_SPEECH_REPLACEMENTS.items():
        text = text.replace(symbol, f"，{speech}，")
    for char, speech in _GPT_SOVITS_UNSAFE_CJK_SPEECH.items():
        text = text.replace(char, speech)
    text = "".join(" " if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn"} else char for char in text)
    text = _restore_cjk_pause_punctuation(text)
    return re.sub(r"[ \t\f\v]+", " ", text).strip()


def detect_tts_language(text: str, default_language: str = "zh") -> str:
    stripped = text.strip()
    if not stripped:
        return default_language
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", stripped))
    ascii_letters = len(re.findall(r"[A-Za-z]", stripped))
    meaningful = len(re.findall(r"[\w\u3400-\u9fff]", stripped))
    if cjk_count == 0 and meaningful >= 40 and ascii_letters / max(meaningful, 1) > 0.75:
        return "en"
    return default_language or "zh"


def spell_latin_terms_for_chinese(text: str) -> str:
    def replace_token(match: re.Match[str]) -> str:
        token = match.group(0)
        parts: list[str] = []
        for char in token:
            lower = char.lower()
            if lower in _LATIN_LETTER_SPEECH:
                parts.append(_LATIN_LETTER_SPEECH[lower])
            elif char in _LATIN_SYMBOL_SPEECH:
                parts.append(_LATIN_SYMBOL_SPEECH[char])
            elif char.isdigit():
                parts.append(char)
            else:
                parts.append(" ")
        return " " + "".join(parts).strip() + " "

    return re.sub(r"(?<![A-Za-z0-9])(?:[A-Za-z][A-Za-z0-9+#._-]*)(?![A-Za-z0-9])", replace_token, text)


def normalize_tts_text(text: str, default_language: str = "zh", language_override: str | None = None) -> NormalizedTtsText:
    normalized = replace_formulas_for_speech(text)
    normalized = clean_markdown_for_speech(normalized)
    normalized = sanitize_gpt_sovits_text(normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    text_lang = (language_override or "").strip().lower() or detect_tts_language(normalized, default_language)
    if text_lang in {"all_zh", "all_yue"}:
        normalized = spell_latin_terms_for_chinese(normalized)
        normalized = sanitize_gpt_sovits_text(normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
    return NormalizedTtsText(
        original_text=text,
        normalized_text=normalized,
        text_lang=text_lang,
    )
