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

ANALYZE_PROMPT = """你是一位专业的文本分析师。请分析以下原文，完成两项任务：

1. **摘要与文风画像**：概括核心内容，分析叙事风格特点
2. **识别自然断点**：找出文本中所有适合分段的"自然断点"位置

自然断点是指：章节边界、段落结束、对话完成、情节转折、场景切换、时间跳跃等位置。

原文：
{original_text}

请以 JSON 格式输出，结构如下：
{{
  "summary": "用2-3句话概括原文的核心内容和主题",
  "style_profile": {{
    "narrative_pov": "叙事视角（第一人称/第三人称等）",
    "tone": "基调氛围",
    "sentence_style": "句式风格特点",
    "vocabulary": "词汇特点",
    "rhythm": "节奏特点",
    "notable_features": "其他显著特征"
  }},
  "breakpoints": [
    {{
      "anchor_text": "断点位置前后的10-20个字符（从原文精确复制，用于定位）",
      "type": "章节结束|段落结束|对话结束|情节转折|场景切换|时间跳跃|其他",
      "strength": 3,
      "label": "简短描述，如：第一章结束、回忆结束回到现实"
    }}
  ]
}}

重要提示：
1. **断点数量**：尽可能多地识别自然断点，不要遗漏。宁多勿少，后续算法会自动选择最优分段
2. **anchor_text**：必须从原文中精确复制，是断点附近的文本片段，用于精确定位
3. **strength 强度**：1=弱断点（句末、段落内自然停顿），2=中断点（段落结束、对话结束），3=强断点（章节边界、重大情节转折、场景切换）
4. **断点按原文顺序排列**
5. 只输出 JSON，不要有其他内容"""

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

    # 分析任务使用更高的 max_tokens（长文本 JSON 输出可能需要 32000+ tokens）
    ANALYSIS_MAX_TOKENS = 64000

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

    def _get_openai_endpoints(self) -> List[Dict[str, str]]:
        """返回主 + 备用 OpenAI 兼容端点列表"""
        endpoints = [{
            "api_key": settings.OPENAI_API_KEY or "demo",
            "base_url": settings.OPENAI_BASE_URL.rstrip("/"),
            "model": self.model,
        }]
        if settings.OPENAI_FALLBACK_API_KEY and settings.OPENAI_FALLBACK_BASE_URL:
            endpoints.append({
                "api_key": settings.OPENAI_FALLBACK_API_KEY,
                "base_url": settings.OPENAI_FALLBACK_BASE_URL.rstrip("/"),
                "model": settings.OPENAI_FALLBACK_MODEL or self.model,
            })
        return endpoints

    async def _stream_openai(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        endpoints = self._get_openai_endpoints()
        last_error = None

        for i, ep in enumerate(endpoints):
            try:
                async for chunk in self._do_stream_openai(messages, ep):
                    yield chunk
                return  # 成功则直接返回
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"OpenAI endpoint {i} ({ep['base_url']}) failed: {e.response.status_code} - trying next")
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"OpenAI endpoint {i} ({ep['base_url']}) error: {e} - trying next")
                continue

        raise last_error or RuntimeError("All OpenAI endpoints failed")

    async def _do_stream_openai(
        self, messages: List[Dict[str, str]], endpoint: Dict[str, str]
    ) -> AsyncGenerator[str, None]:
        headers = {
            "Authorization": f"Bearer {endpoint['api_key']}",
            "Content-Type": "application/json",
        }
        # OpenRouter 需要额外的 headers
        if "openrouter.ai" in endpoint["base_url"]:
            headers["HTTP-Referer"] = "https://novel.al.jrient.cn"
            headers["X-Title"] = "Novel Writer"
        payload = {
            "model": endpoint["model"],
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        # 代理逻辑：检查是否需要跳过代理
        import os
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        no_proxy = os.environ.get("NO_PROXY", "").split(",")
        base_url = endpoint["base_url"]
        # 如果 URL 在 NO_PROXY 列表中，不使用代理；否则使用代理
        should_skip_proxy = any(np in base_url for np in no_proxy if np)
        use_proxy = None if should_skip_proxy else proxy

        async with httpx.AsyncClient(timeout=None, proxy=use_proxy) as client:
            async with client.stream(
                "POST",
                f"{endpoint['base_url']}/chat/completions",
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
                        choice = chunk.get("choices", [{}])[0]
                        finish_reason = choice.get("finish_reason")
                        if finish_reason:
                            logger.info(f"Chunk finish_reason: {finish_reason}")
                        if finish_reason == "length":
                            logger.warning("AI response was truncated due to max_tokens limit")
                        elif finish_reason == "stop":
                            logger.info("AI completed response normally")
                        delta = choice.get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError) as e:
                        logger.debug(f"Error parsing chunk: {e}")
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

        async with httpx.AsyncClient(timeout=None) as client:
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


    async def analyze_text_non_stream(
        self,
        original_text: str,
    ) -> str:
        """分析全文，非流式模式，返回完整响应"""
        prompt = ANALYZE_PROMPT.format(original_text=original_text)
        messages = self._build_messages(prompt)
        
        endpoints = self._get_openai_endpoints()
        last_error = None

        for i, ep in enumerate(endpoints):
            headers = {
                "Authorization": f"Bearer {ep['api_key']}",
                "Content-Type": "application/json",
            }
            # OpenRouter 需要额外的 headers
            if "openrouter.ai" in ep["base_url"]:
                headers["HTTP-Referer"] = "https://novel.al.jrient.cn"
                headers["X-Title"] = "Novel Writer"
            payload = {
                "model": ep["model"],
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
            }
            # 代理逻辑：检查是否需要跳过代理
            import os
            proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
            no_proxy = os.environ.get("NO_PROXY", "").split(",")
            base_url = ep["base_url"]
            should_skip_proxy = any(np in base_url for np in no_proxy if np)
            use_proxy = None if should_skip_proxy else proxy

            try:
                async with httpx.AsyncClient(timeout=None, proxy=use_proxy) as client:
                    resp = await client.post(
                        f"{ep['base_url']}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    logger.info(f"Non-stream response finish_reason: {result.get('choices', [{}])[0].get('finish_reason')}")
                    logger.info(f"Non-stream response usage: {result.get('usage')}")
                    return result["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"OpenAI endpoint {i} ({ep['base_url']}) non-stream failed: {e.response.status_code} - trying next")
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"OpenAI endpoint {i} ({ep['base_url']}) non-stream error: {e} - trying next")
                continue

        raise last_error or RuntimeError("All OpenAI endpoints failed")

    async def analyze_text(
        self,
        original_text: str,
    ) -> AsyncGenerator[str, None]:
        """分析全文，SSE流式返回摘要+文风+分段建议"""
        prompt = ANALYZE_PROMPT.format(original_text=original_text)
        messages = self._build_messages(prompt)

        # 临时提升 max_tokens 到 64000，确保长文本分析的 JSON 输出完整
        original_max_tokens = self.max_tokens
        self.max_tokens = self.ANALYSIS_MAX_TOKENS
        try:
            async for chunk in self._stream(messages):
                yield chunk
        finally:
            self.max_tokens = original_max_tokens

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

    # ─── Breakpoint-based Segmentation ──────────────────────────────────────

    @staticmethod
    def locate_breakpoint(text: str, anchor_text: str) -> int:
        """
        在原文中定位断点的精确位置。
        返回断点字符索引（anchor_text 结束后最近的句子边界），找不到返回 -1。
        """
        if not anchor_text:
            return -1

        pos = text.find(anchor_text)
        if pos == -1:
            # 模糊匹配：去空白
            stripped = anchor_text.strip()
            pos = text.find(stripped)
            if pos == -1:
                return -1
            anchor_len = len(stripped)
        else:
            anchor_len = len(anchor_text)

        # 从 anchor 结束位置向后找最近的句子边界
        end_pos = pos + anchor_len
        return ExpansionAIService._find_nearest_sentence_boundary(text, end_pos)

    @staticmethod
    def _find_nearest_sentence_boundary(text: str, pos: int, search_range: int = 100) -> int:
        """
        从 pos 附近找最近的句子边界（句号、感叹号、问号、换行符等）。
        优先向后找，再向前找。
        """
        sentence_endings = {'。', '！', '？', '.', '!', '?', '"', '"', '」', '』'}
        text_len = len(text)

        # 向后搜索
        for i in range(pos, min(pos + search_range, text_len)):
            if text[i] in sentence_endings:
                return i + 1
            if text[i] == '\n' and i > pos:
                return i + 1

        # 向前搜索
        for i in range(pos - 1, max(pos - search_range, -1), -1):
            if text[i] in sentence_endings:
                return i + 1
            if text[i] == '\n':
                return i + 1

        # 找不到句子边界，返回原始位置
        return pos

    @staticmethod
    def compute_segments_from_breakpoints(
        original_text: str,
        breakpoints: List[Dict[str, Any]],
        min_segment_chars: int = 300,
        max_segment_chars: int = 2000,
    ) -> List[Dict[str, Any]]:
        """
        两阶段分段 - 阶段2：根据 AI 识别的断点列表，用本地算法计算最优分段。

        算法：
        1. 将所有断点定位到原文中的精确字符位置
        2. 用贪心策略选择断点：从上一个分段结束位置开始，寻找在 [min, max] 字数范围内
           强度最高的断点作为分段结束位置
        3. 如果没有断点落在范围内，在 max 位置附近找句子边界强制切分

        Returns:
            [{"start": int, "end": int, "title": str, "breakpoint_type": str}, ...]
        """
        text_len = len(original_text)
        if text_len == 0:
            return []

        # 如果文本很短，不需要分段
        if text_len <= max_segment_chars:
            return [{
                "start": 0,
                "end": text_len,
                "title": None,
                "breakpoint_type": None,
            }]

        # Step 1: 定位所有断点的精确位置
        located_breakpoints = []
        for bp in breakpoints:
            anchor = bp.get("anchor_text", "")
            pos = ExpansionAIService.locate_breakpoint(original_text, anchor)
            if pos > 0 and pos < text_len:
                located_breakpoints.append({
                    "position": pos,
                    "strength": bp.get("strength", 1),
                    "type": bp.get("type", "其他"),
                    "label": bp.get("label", ""),
                })

        # 去重并排序
        seen_positions = set()
        unique_breakpoints = []
        for bp in located_breakpoints:
            # 合并相近的断点（50字符内）
            merged = False
            for ubp in unique_breakpoints:
                if abs(ubp["position"] - bp["position"]) < 50:
                    # 保留强度更高的
                    if bp["strength"] > ubp["strength"]:
                        ubp.update(bp)
                    merged = True
                    break
            if not merged:
                unique_breakpoints.append(bp)

        unique_breakpoints.sort(key=lambda x: x["position"])

        # Step 2: 贪心算法选择最优分段点
        segments = []
        current_start = 0

        while current_start < text_len:
            remaining = text_len - current_start

            # 剩余文本不超过 max，直接作为最后一段
            if remaining <= max_segment_chars:
                segments.append({
                    "start": current_start,
                    "end": text_len,
                    "title": None,
                    "breakpoint_type": None,
                })
                break

            # 剩余文本如果分成两段会导致下一段太短，适当放宽
            if remaining < min_segment_chars + max_segment_chars:
                # 尽量在中间找断点平均分
                mid = current_start + remaining // 2
                best_bp = None
                best_dist = float('inf')
                for bp in unique_breakpoints:
                    if current_start + min_segment_chars * 0.7 <= bp["position"] <= current_start + remaining - min_segment_chars * 0.7:
                        dist = abs(bp["position"] - mid)
                        # 强断点加权：距离 / 强度
                        weighted_dist = dist / bp["strength"]
                        if weighted_dist < best_dist:
                            best_dist = weighted_dist
                            best_bp = bp

                if best_bp:
                    segments.append({
                        "start": current_start,
                        "end": best_bp["position"],
                        "title": best_bp.get("label"),
                        "breakpoint_type": best_bp.get("type"),
                    })
                    current_start = best_bp["position"]
                else:
                    # 没有合适断点，在中间找句子边界
                    cut_pos = ExpansionAIService._find_nearest_sentence_boundary(
                        original_text, mid
                    )
                    segments.append({
                        "start": current_start,
                        "end": cut_pos,
                        "title": None,
                        "breakpoint_type": None,
                    })
                    current_start = cut_pos
                continue

            # 在 [min, max] 范围内寻找最佳断点
            range_start = current_start + min_segment_chars
            range_end = current_start + max_segment_chars

            # 收集范围内的断点
            candidates = [
                bp for bp in unique_breakpoints
                if range_start <= bp["position"] <= range_end
            ]

            if candidates:
                # 选择强度最高的断点；强度相同时选更靠后的（段落更完整）
                best = max(candidates, key=lambda bp: (bp["strength"], bp["position"]))
                segments.append({
                    "start": current_start,
                    "end": best["position"],
                    "title": best.get("label"),
                    "breakpoint_type": best.get("type"),
                })
                current_start = best["position"]
            else:
                # 没有断点在范围内，扩大搜索到 [min*0.8, max*1.2]
                extended_candidates = [
                    bp for bp in unique_breakpoints
                    if current_start + min_segment_chars * 0.8 <= bp["position"] <= current_start + max_segment_chars * 1.2
                ]

                if extended_candidates:
                    # 选最接近理想长度（min_segment_chars + max_segment_chars）/ 2 的断点
                    ideal = current_start + (min_segment_chars + max_segment_chars) // 2
                    best = min(extended_candidates, key=lambda bp: abs(bp["position"] - ideal) / bp["strength"])
                    segments.append({
                        "start": current_start,
                        "end": best["position"],
                        "title": best.get("label"),
                        "breakpoint_type": best.get("type"),
                    })
                    current_start = best["position"]
                else:
                    # 完全没有断点，在 max 附近找句子边界强制切分
                    cut_pos = ExpansionAIService._find_nearest_sentence_boundary(
                        original_text, current_start + max_segment_chars
                    )
                    # 确保不会切到太后面
                    if cut_pos > current_start + max_segment_chars * 1.3:
                        cut_pos = current_start + max_segment_chars
                    segments.append({
                        "start": current_start,
                        "end": cut_pos,
                        "title": None,
                        "breakpoint_type": None,
                    })
                    current_start = cut_pos

        return segments

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