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
    raw = await AIService.generate_text(prompt, max_tokens=2000)
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise StyleGuideExtractionError(
            f"LLM 输出无法解析为 JSON: {e.msg}; 头 200 字: {cleaned[:200]}"
        ) from e

    if not isinstance(parsed, dict) or "structured" not in parsed or "prompt_fragment" not in parsed:
        raise StyleGuideExtractionError(
            f"JSON 缺关键字段; keys={list(parsed) if isinstance(parsed, dict) else type(parsed).__name__}"
        )

    return json.dumps(parsed, ensure_ascii=False), _resolve_model_name()
