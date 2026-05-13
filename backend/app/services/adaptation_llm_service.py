"""改编模块的 LLM 调用层，集中三个能力：抽实体 / LLM 切场 / 改写单场。

为便于测试，构造时可注入 provider；生产由 get_default_service() 用 script_ai_service 路由。
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

import httpx

from app.core.config import settings
from app.services.adaptation_splitter import SceneBoundary

logger = logging.getLogger(__name__)


class _LLMProvider(Protocol):
    async def complete(self, prompt: str, **kwargs) -> str: ...


class _OpenAICompatibleProvider:
    """通用 OpenAI-compatible 非流式调用。"""

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.5, max_tokens: int = 8000):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def complete(self, prompt: str, **kwargs) -> str:
        model = kwargs.get("model") or self.model
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]


_EXTRACT_PROMPT = """你是剧本改编实体抽取器。读下面的剧本原文，列出所有【人物 / 地点 / 关键道具 / 时代关键词】。

输出严格 JSON，禁止任何其他文字：
{{
  "entities": [
    {{"type": "person|place|prop|era_term", "text": "<原文出现形式>", "count": <出现次数>, "sample_context": "<≤30字示例>"}}
  ],
  "character_traits": [
    {{"name": "<人物名>", "tags": ["<≤8字标签>", "口头禅:<具体台词>"]}}
  ]
}}

要求：去重；同一实体不同写法合并；character_traits 仅产出主要人物（出场≥3次）。

原文：
{text}
"""

_SPLIT_PROMPT = """你是剧本场切分器。下面是缺少明显场标记的剧本原文。请按内在场景切分，输出严格 JSON，禁止任何其他文字：
[{{"start": <整数字符偏移>, "end": <整数字符偏移>, "title": "<≤30字场标题>"}}]

约束：start/end 为字符偏移，必须连续覆盖全文；标题为简短的"场N 地点/事件"。

原文（共 {length} 字符）：
{text}
"""

_REWRITE_INTENSITY_BODY = {
    1: "你只做精准的实体替换，处理同名消歧、称呼一致性、代词一致性。**严禁改动其他词。**",
    2: (
        "你做实体替换，并按「保节奏 paraphrase」模式重写全文。目标：在节奏与剧情完全不变的前提下，"
        "尽量降低改写后文本与原文的字面相似度。\n"
        "【必改 — 不改即视为失败】\n"
        "1) 每条人物台词都要换说法：同义词替换、语序调整、句式变换、主被动互换、口语/书面化微调，"
        "使单条台词与原句的字面重合度 ≤60%。**禁止整句逐字照搬**。\n"
        "2) 旁白与动作描写也要用不同措辞重写一遍，禁止整段照搬原文。\n"
        "【守恒 — 违反即不合格】\n"
        "a) 对白行数必须等于原文，每条台词改写后的字数与原台词差异 ≤30%。\n"
        "b) 人物身份/关系/剧情顺序/冲突点/情感拐点 完全保持，不增不减剧情节点。\n"
        "c) character_traits 标注的「口头禅:xxx」必须出现在对应人物的台词中（位置可调，但内容不变）。\n"
        "d) 关键道具仅做映射表规定的替换，其余信息原样保留。"
    ),
    3: "你按 era_target 重写场景中的物件、职业、动作、语言风格。必须保留：出场人物功能、冲突点、情感拐点、场内台词数量在原文 ±20% 以内、场次顺序与定位。",
}


@dataclass
class AdaptationLLMService:
    provider: _LLMProvider
    extract_model: Optional[str] = None
    rewrite_model: Optional[str] = None

    async def extract_entities(self, text: str) -> Dict[str, Any]:
        raw = await self.provider.complete(
            _EXTRACT_PROMPT.format(text=text[: settings.ADAPTATION_MAX_CHARS]),
            model=self.extract_model,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("extract_entities JSON 解析失败: %s; 原始: %s", e, raw[:200])
            raise ValueError(f"实体抽取返回非 JSON：{e}") from e
        data.setdefault("entities", [])
        data.setdefault("character_traits", [])
        return data

    async def split_by_llm(self, text: str) -> List[SceneBoundary]:
        raw = await self.provider.complete(
            _SPLIT_PROMPT.format(text=text, length=len(text)),
            model=self.extract_model,
        )
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 切场返回非 JSON：{e}") from e
        out: list[SceneBoundary] = []
        for i, item in enumerate(arr):
            out.append(SceneBoundary(
                index=i,
                start=int(item["start"]),
                end=int(item["end"]),
                title=str(item.get("title", f"场{i + 1}"))[:80],
            ))
        return out

    async def rewrite_scene(
        self,
        *,
        scene_text: str,
        intensity: int,
        intent: Optional[str],
        era_target: Optional[str],
        mappings: List[Dict[str, Any]],
        prev_scene_summary: Optional[str],
        character_traits: List[Dict[str, Any]],
        extra_prompt: Optional[str],
    ) -> str:
        body = _REWRITE_INTENSITY_BODY.get(intensity, _REWRITE_INTENSITY_BODY[2])

        mapping_lines = []
        for m in mappings:
            tag = "[LOCKED]" if m.get("locked") else ""
            repl = m.get("replacement_text") or "(待定)"
            mapping_lines.append(f"- {tag} [{m['entity_type']}] {m['original_text']} → {repl}")
        mapping_block = "\n".join(mapping_lines) if mapping_lines else "(无)"

        traits_block = "\n".join(
            f"- {t['name']}：{'、'.join(t.get('tags', []))}"
            for t in character_traits
        ) or "(无)"

        prompt = f"""你是剧本改编工程师。任务：在保剧情节奏不变的前提下，改写以下单场。

【强度规则】
{body}

【全局映射表（[LOCKED] 必须严格替换）】
{mapping_block}

【新时代/世界设定】
{era_target or "(未指定)"}

【改编意图】
{intent or "(未指定)"}

【人物性格标签】
{traits_block}

【上一场摘要】
{prev_scene_summary or "(本场为首场)"}

【额外要求】
{extra_prompt or "(无)"}

【原文场内容】
{scene_text}

请直接输出改写后的本场内容，不要任何解释或前后缀。"""

        return await self.provider.complete(prompt, model=self.rewrite_model)


def get_default_service() -> AdaptationLLMService:
    """使用配置中的 provider 构造服务。优先 deepseek，其次 openai。"""
    if settings.DEEPSEEK_API_KEY:
        provider = _OpenAICompatibleProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.ADAPTATION_REWRITE_MODEL or settings.DEEPSEEK_PRO_MODEL,
        )
    elif settings.OPENAI_API_KEY:
        provider = _OpenAICompatibleProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.ADAPTATION_REWRITE_MODEL or settings.OPENAI_MODEL,
        )
    else:
        raise RuntimeError("未配置任何 LLM API Key，无法启动改编服务")
    return AdaptationLLMService(
        provider=provider,
        extract_model=settings.ADAPTATION_EXTRACT_MODEL,
        rewrite_model=settings.ADAPTATION_REWRITE_MODEL,
    )
