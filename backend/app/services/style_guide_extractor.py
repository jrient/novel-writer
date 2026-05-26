"""风格指南片段抽取服务

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第五节。
"""
import json
import re
from typing import Tuple

from app.core.config import settings
from app.services.ai_service import AIService


class StyleGuideExtractionError(Exception):
    """LLM 返回无法解析为 JSON，或缺关键字段"""


PROMPT_TEMPLATE = """你是一位资深风格分析师，专门分析中文短篇网文的写作风格。
分析下面给定的短篇全文，严格输出 JSON，三段：

1. structured: 客观可枚举的风格维度（pov / tense / sentence_length /
   dialogue_density / pacing / opening_formula / ending_formula /
   signature_devices[]）。每项给一个简短中文标签或 1-2 句话描述。

2. prose_excerpt: 从原文中挑选一段最能体现该作整体调性的连续段落
   （不少于 100 字、不超过 250 字）。原文照抄，不要改写。

3. prompt_fragment: 一段约 300 字的"风格指南"，必须可以直接拼接到
   下游小说生成 prompt 的 system 段里。要描述：人称/时态/句长偏好/
   段落分隔风格/对白节奏/情绪表达手法/开场和结尾的常用套路。
   不要包含原文具体人名、地名、情节。只描述"怎么写"，不描述"写什么"。

严格 JSON 输出，不要 markdown 代码块。

《{title}》全文：
{content}
"""


_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _strip_code_fence(s: str) -> str:
    """剥掉 LLM 偶尔套上的 ```json ... ``` 围栏"""
    return _CODE_FENCE_RE.sub("", s).strip()


def _try_repair_json(s: str) -> dict | None:
    """尝试修复截断的 JSON：补全未闭合的字符串和括号。"""
    # 计算未闭合的括号层级，逐级补全
    open_brackets = 0
    in_string = False
    escape_next = False
    for ch in s:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            open_brackets += 1
        elif ch in ('}', ']'):
            open_brackets = max(0, open_brackets - 1)

    # 尝试多种修复组合：先尝试关闭截断的字符串，再关闭括号
    close_brackets = '}' * open_brackets
    candidates = [
        s + close_brackets,              # 直接关闭括号
        s + '"' + close_brackets,        # 关闭截断字符串 + 关闭括号
        s + '"]' + close_brackets,       # 关闭截断数组元素 + 关闭括号
        s + '"}' + close_brackets,        # 关闭截断对象值 + 关闭括号
        s + '"]}' + close_brackets,       # 关闭截断数组内对象 + 关闭括号
    ]
    for candidate in candidates:
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            continue
    return None


def _resolve_model_name() -> str:
    """记录抽取实际用到的 model（按 settings 默认 provider 选）"""
    if settings.OPENAI_API_KEY:
        return f"openai/{settings.OPENAI_MODEL}"
    if settings.ANTHROPIC_API_KEY:
        return f"anthropic/{settings.ANTHROPIC_MODEL}"
    if settings.OLLAMA_BASE_URL:
        return f"ollama/{settings.OLLAMA_MODEL}"
    return "demo"


async def extract(title: str, content: str) -> Tuple[str, str]:
    """跑 LLM 抽取，返回 (style_guide_json_str, extraction_model)。

    成功 → JSON 字符串可直接写入 StyleSample.style_guide
    失败 → 抛 StyleGuideExtractionError
    """
    prompt = PROMPT_TEMPLATE.format(title=title, content=content)
    raw = await AIService.generate_text(prompt, max_tokens=4000)
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # LLM 输出截断导致 JSON 不完整，尝试补全右括号
        repaired = _try_repair_json(cleaned)
        if repaired is not None:
            parsed = repaired
        else:
            raise StyleGuideExtractionError(
                f"LLM 输出无法解析为 JSON (含修复尝试失败); 头 200 字: {cleaned[:200]}"
            )

    if not isinstance(parsed, dict) or "structured" not in parsed:
        raise StyleGuideExtractionError(
            f"JSON 缺 structured 字段; keys={list(parsed) if isinstance(parsed, dict) else type(parsed).__name__}"
        )

    # 修复截断可能丢失的字段，补默认值
    parsed.setdefault("prose_excerpt", "")
    parsed.setdefault("prompt_fragment", "")

    return json.dumps(parsed, ensure_ascii=False), _resolve_model_name()
