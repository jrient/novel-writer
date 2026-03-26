"""
扩写 AI 服务
独立服务，遵循 ScriptAIService 模式
支持 OpenAI / Anthropic / Ollama 三种 Provider
"""
import json
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── 提示词模板 ─────────────────────────────────────────────────────────────

ANALYZE_PROMPT = """你是一位专业的文本分析师。请分析以下原文，生成：

1. **摘要**：用2-3句话概括原文的核心内容和主题
2. **文风画像**：分析原文的叙事风格特点
3. **分段建议**：根据内容逻辑，建议如何将文本分成若干段落进行扩写

原文：
{original_text}

请以 JSON 格式输出，结构如下：
{{
  "summary": "原文摘要...",
  "style_profile": {{
    "narrative_pov": "叙事视角（第一人称/第三人称等）",
    "tone": "基调氛围",
    "sentence_style": "句式风格特点",
    "vocabulary": "词汇特点",
    "rhythm": "节奏特点",
    "notable_features": "其他显著特征"
  }},
  "segment_suggestions": [
    {{
      "title": "段落标题",
      "start": 0,
      "end": 100,
      "reason": "分段理由"
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。"""

EXPAND_SYSTEM_PROMPT = """你是一位专业的文学扩写专家。你的任务是在保持原文风格和精髓的基础上，对文本进行扩写。

扩写原则：
1. 保持原文的叙事视角和基调
2. 丰富细节描写，但不改变原意
3. 扩展人物心理和情感描写
4. 增强场景感和画面感
5. 保持行文节奏与原文一致
6. 使用与原文相似的词汇风格

{style_instructions}"""

EXPAND_USER_PROMPT = """请扩写以下文本段落。

## 原文摘要
{summary}

## 文风要求
{style_requirements}

## 前文参考
{prev_context}

## 当前段落（需要扩写）
{current_segment}

## 后文参考
{next_context}

## 扩写要求
- 扩写级别：{expansion_level}（light=轻度扩写1.5倍，medium=中度扩写2倍，deep=深度扩写3倍）
- 目标字数：约 {target_word_count} 字
- 特殊指令：{custom_instructions}

请直接输出扩写后的文本，不要添加任何解释或标记："""


# ─── 扩写级别映射 ─────────────────────────────────────────────────────────

EXPANSION_MULTIPLIERS = {
    "light": 1.5,
    "medium": 2.0,
    "deep": 3.0,
}

EXPANSION_LEVEL_NAMES = {
    "light": "轻度扩写",
    "medium": "中度扩写",
    "deep": "深度扩写",
}


class ExpansionAIService:
    """
    扩写 AI 服务
    根据项目的 ai_config 选择合适的 provider 和模型
    API keys 来自全局 settings，不存储在 ai_config 中
    """

    def __init__(self, ai_config: Optional[Dict[str, Any]] = None):
        self.ai_config = ai_config or {}
        self.provider = self.ai_config.get("provider") or settings.DEFAULT_AI_PROVIDER
        self.model = self._resolve_model()
        self.temperature = self._resolve_temperature()
        self.max_tokens = self._resolve_max_tokens()
        self.custom_prompts: Dict[str, Any] = self.ai_config.get("prompt_config") or {}

    def _resolve_model(self) -> str:
        model = self.ai_config.get("model")
        if model:
            return model
        if self.provider == "anthropic":
            return settings.ANTHROPIC_MODEL
        if self.provider == "ollama":
            return settings.OLLAMA_MODEL
        return settings.OPENAI_MODEL

    def _resolve_temperature(self) -> float:
        prompt_config = self.ai_config.get("prompt_config") or {}
        if isinstance(prompt_config, dict):
            t = prompt_config.get("temperature")
            if t is not None:
                return float(t)
        return 0.7

    def _resolve_max_tokens(self) -> int:
        prompt_config = self.ai_config.get("prompt_config") or {}
        if isinstance(prompt_config, dict):
            m = prompt_config.get("max_tokens")
            if m is not None:
                return int(m)
        return settings.AI_MAX_TOKENS_STREAM

    def _get_system_prompt(self, default_prompt: str) -> str:
        """获取系统提示词：优先使用用户自定义，否则用默认"""
        if isinstance(self.custom_prompts, dict):
            custom = self.custom_prompts.get("system_prompt")
            if custom:
                return custom
        return default_prompt

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    # ─── OpenAI / Compatible ────────────────────────────────────────────────

    async def _stream_openai(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        api_key = settings.OPENAI_API_KEY or "demo"
        base_url = settings.OPENAI_BASE_URL.rstrip("/")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0]["delta"]
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    # ─── Anthropic ──────────────────────────────────────────────────────────

    async def _stream_anthropic(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        api_key = settings.ANTHROPIC_API_KEY or ""
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Extract system message if present
        system = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append(msg)

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": user_messages,
            "stream": True,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    try:
                        event = json.loads(data)
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

    # ─── Ollama ─────────────────────────────────────────────────────────────

    async def _stream_ollama(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.temperature},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{base_url}/api/chat",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError):
                        continue

    async def _stream(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        """根据 provider 路由到对应的流式方法"""
        if self.provider == "anthropic":
            async for chunk in self._stream_anthropic(messages):
                yield chunk
        elif self.provider == "ollama":
            async for chunk in self._stream_ollama(messages):
                yield chunk
        else:
            async for chunk in self._stream_openai(messages):
                yield chunk

    # ─── Public Generation Methods ──────────────────────────────────────────

    async def analyze_text(
        self,
        original_text: str,
    ) -> AsyncGenerator[str, None]:
        """分析全文，SSE流式返回摘要+文风+分段建议"""
        prompt = ANALYZE_PROMPT.format(original_text=original_text)
        messages = self._build_messages(prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def expand_segment(
        self,
        summary: str,
        style_profile: Dict[str, Any],
        current_segment: str,
        prev_context: Optional[str] = None,
        next_context: Optional[str] = None,
        expansion_level: str = "medium",
        target_word_count: Optional[int] = None,
        custom_instructions: Optional[str] = None,
        style_instructions: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """扩写单段，携带上下文"""
        # 计算目标字数
        if target_word_count is None:
            multiplier = EXPANSION_MULTIPLIERS.get(expansion_level, 2.0)
            current_len = len(current_segment)
            target_word_count = int(current_len * multiplier)

        # 格式化文风要求
        style_requirements = self._format_style_requirements(style_profile)

        # 系统提示词
        system_prompt = self._get_system_prompt(EXPAND_SYSTEM_PROMPT)
        if style_instructions:
            system_prompt = system_prompt.format(style_instructions=style_instructions)
        else:
            system_prompt = system_prompt.format(style_instructions="")

        # 用户提示词
        prompt = EXPAND_USER_PROMPT.format(
            summary=summary,
            style_requirements=style_requirements,
            prev_context=prev_context or "（无前文参考）",
            current_segment=current_segment,
            next_context=next_context or "（无后文参考）",
            expansion_level=EXPANSION_LEVEL_NAMES.get(expansion_level, expansion_level),
            target_word_count=target_word_count,
            custom_instructions=custom_instructions or "无特殊指令",
        )

        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    def _format_style_requirements(self, style_profile: Dict[str, Any]) -> str:
        """格式化文风要求为文本"""
        if not style_profile:
            return "保持原文风格"

        parts = []
        if style_profile.get("narrative_pov"):
            parts.append(f"叙事视角：{style_profile['narrative_pov']}")
        if style_profile.get("tone"):
            parts.append(f"基调氛围：{style_profile['tone']}")
        if style_profile.get("sentence_style"):
            parts.append(f"句式风格：{style_profile['sentence_style']}")
        if style_profile.get("vocabulary"):
            parts.append(f"词汇特点：{style_profile['vocabulary']}")
        if style_profile.get("rhythm"):
            parts.append(f"节奏特点：{style_profile['rhythm']}")
        if style_profile.get("notable_features"):
            parts.append(f"其他特征：{style_profile['notable_features']}")

        return "；".join(parts) if parts else "保持原文风格"

    # ─── Static Utility Methods ──────────────────────────────────────────────

    @staticmethod
    def detect_script_markers(text: str) -> bool:
        """
        检测文本是否包含剧本格式标记

        剧本格式标记包括：
        - OS (旁白/画外音)
        - △ (动作/表情标记)
        - 【】(场景/角色名)

        Returns:
            bool: 如果检测到剧本标记返回 True，否则返回 False
        """
        if not text:
            return False

        # 检测 OS 标记（旁白/画外音）
        if re.search(r'\bOS\b', text):
            return True

        # 检测 △ 标记（动作/表情）
        if '△' in text:
            return True

        # 检测【】标记（场景/角色名）
        if re.search(r'【[^】]+】', text):
            return True

        return False

    @staticmethod
    def _is_truncated(text: str, finish_reason: Optional[str] = None) -> bool:
        """
        判断 AI 输出是否被截断

        Args:
            text: 生成的文本
            finish_reason: API 返回的结束原因

        Returns:
            bool: 如果判断为被截断返回 True，否则返回 False
        """
        # 如果 finish_reason 是 'length'，明确被截断
        if finish_reason == "length":
            return True

        # 如果 finish_reason 是 'stop'，正常结束
        if finish_reason == "stop":
            return False

        # 如果没有 finish_reason，检查文本特征
        if not text:
            return False

        text = text.strip()

        # 检查是否以标点结尾
        ending_punctuation = {'。', '！', '？', '."', '!"', '?"', '." ', '!" ', '?" '}
        if any(text.endswith(p) for p in ending_punctuation):
            return False

        # 检查是否以逗号结尾（通常是截断）
        if text.endswith('，') or text.endswith(','):
            return True

        # 检查是否以省略号结尾（可能是截断）
        if text.endswith('……') or text.endswith('...'):
            return True

        # 检查是否以不完整的句子结尾（没有标点）
        if text and text[-1] not in {'。', '！', '？', '.', '!', '?', '"', "'", '）', ')', '」', '』'}:
            return True

        return False

    @staticmethod
    def get_expansion_multiplier(level: str) -> float:
        """获取扩写倍数"""
        return EXPANSION_MULTIPLIERS.get(level, 2.0)

    @staticmethod
    def get_expansion_level_name(level: str) -> str:
        """获取扩写级别名称"""
        return EXPANSION_LEVEL_NAMES.get(level, level)