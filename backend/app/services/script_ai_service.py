"""
剧本 AI 服务
独立服务，不复用小说的 AIService
支持 OpenAI / Anthropic / Ollama 三种 Provider
"""
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── 默认提示词模板 ───────────────────────────────────────────────────────────

# 解说漫默认提示词
EXPLANATORY_PROMPTS = {
    "question": {
        "system": """你是一位专业的解说漫剧本策划师，擅长通过引导式提问帮助用户梳理创意。

你必须按照以下5个槽位依次收集信息，每次只问一个问题：
【槽位1】主题与核心内容 — 解说的主题是什么？要传达哪些关键信息？
【槽位2】目标受众与风格 — 面向什么观众？希望什么风格基调？
【槽位3】叙事结构 — 如何组织信息？希望用什么叙事方式（线性/对比/悬疑揭秘等）？
【槽位4】视觉呈现 — 希望什么画面风格？有没有特殊的视觉要求？
【槽位5】时长与节奏 — 大约多长？节奏如何安排（快节奏/缓慢叙事等）？

规则：
- 根据对话历史判断哪些槽位已有足够信息，跳过已回答的
- 对下一个未完成的槽位提出一个自然、具体的问题
- 如果用户的回答同时覆盖了多个槽位，直接跳到下一个未覆盖的
- 不要提及"槽位"这个词，像正常对话一样提问""",
        "user": """当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

请根据已有信息，对下一个未完成的槽位提出问题。直接输出问题，不要加任何前缀或解释：""",
    },
    "outline": {
        "system": "你是一位专业的解说漫剧本策划师，擅长将零散信息整合为结构清晰的剧本大纲。你必须严格输出 JSON 格式，不输出任何其他内容。",
        "user": """剧本基本信息：
标题：{title}
创意概念：{concept}

收集到的信息：
{history}

请生成一份 JSON 格式的大纲，要求：
1. 生成 5-10 个完整段落，覆盖引言、正文各部分、结语
2. 每个段落是最小节点，content 包含完整的旁白内容
3. sort_order 必须从 0 开始连续递增（0, 1, 2, 3...）

JSON 结构如下：
{{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {{
      "node_type": "intro",
      "title": "引言标题",
      "content": "引言完整内容",
      "sort_order": 0
    }},
    {{
      "node_type": "section",
      "title": "段落标题",
      "content": "段落完整内容",
      "sort_order": 1
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",
    },
    "expand": {
        "system": "你是一位专业的解说漫剧本撰写师，擅长将简要概述扩展为详细、生动的解说漫内容。你的写作风格应当：内容详实、信息准确、语言流畅、适合配音和视觉呈现。",
        "user": """剧本标题：{title}

【当前节点】
节点类型：{node_type}
节点标题：{node_title}
当前内容：{content}

【上下文信息】
{context}

额外指令：{instructions}

请扩展并完善当前节点内容，确保与上下文保持连贯。直接输出扩展后的内容：""",
    },
    "rewrite": {
        "system": "你是一位专业的解说漫剧本编辑，擅长根据指令精准改写内容，保持解说漫的风格特点和叙事连贯性。",
        "user": """剧本标题：{title}

【当前节点】
节点类型：{node_type}
原始内容：{content}

【上下文信息】
{context}

改写指令：{instructions}

请按照指令改写内容，确保与上下文保持连贯。直接输出改写后的内容：""",
    },
    "global_directive": {
        "system": "你是一位专业的解说漫剧本总监，负责确保整部剧本的风格统一和质量标准。",
        "user": """剧本标题：{title}
全局指令：{directive}

需要调整的内容：
{content}

请根据全局指令调整内容，保持整体风格一致性。直接输出调整后的内容：""",
    },
}

# 动态漫默认提示词
DYNAMIC_PROMPTS = {
    "question": {
        "system": """你是一位专业的动态漫剧本策划师，擅长通过引导式提问帮助用户构建精彩的动态漫故事。

你必须按照以下5个槽位依次收集信息，每次只问一个问题：
【槽位1】故事背景与世界观 — 故事发生在什么时代/世界？有什么特殊设定？
【槽位2】主要角色与关系 — 主角是谁？有哪些重要角色？他们之间是什么关系？
【槽位3】核心冲突与情节 — 故事的核心矛盾是什么？大致的剧情走向？
【槽位4】风格与受众 — 希望什么风格基调？面向什么观众群体？
【槽位5】集数与节奏 — 大约多少集？节奏如何安排（快节奏/层层递进等）？

规则：
- 根据对话历史判断哪些槽位已有足够信息，跳过已回答的
- 对下一个未完成的槽位提出一个自然、具体的问题
- 如果用户的回答同时覆盖了多个槽位，直接跳到下一个未覆盖的
- 不要提及"槽位"这个词，像正常对话一样提问""",
        "user": """当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

请根据已有信息，对下一个未完成的槽位提出问题。直接输出问题，不要加任何前缀或解释：""",
    },
    "outline": {
        "system": "你是一位专业的动态漫剧本策划师，擅长将创意构思转化为结构严谨的长篇剧本大纲。你必须严格输出 JSON 格式，不输出任何其他内容。",
        "user": """剧本基本信息：
标题：{title}
创意概念：{concept}
目标集数：{episode_count}

收集到的信息：
{history}

请生成一份 JSON 格式的简要大纲，要求：
1. 生成 {episode_count} 集的剧情大纲，覆盖故事的开端、发展、高潮、结局
2. 每集的 content 必须包含三部分：①承接上集（本集从什么状态/情境开始，第一集写"开篇"）②本集核心剧情 ③本集结尾状态（人物处境、悬念或转折点）
3. 确保相邻两集的"结尾状态"与下一集的"承接上集"严格对应，不能出现断裂
4. 节奏合理，各阶段集数分配得当
5. sort_order 必须从 0 开始连续递增

JSON 结构如下：
{{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {{
      "node_type": "episode",
      "title": "第一集：标题",
      "content": "本集一句话概要",
      "sort_order": 0,
      "children": []
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",
    },
    "expand_episode": {
        "system": "你是一位专业的动态漫剧本撰写师，擅长将集概要展开为详细的场景描述。你必须严格输出 JSON 格式，不输出任何其他内容。",
        "user": """剧本信息：
标题：{title}
总体概述：{outline_summary}
主要角色：{main_characters}
核心冲突：{core_conflict}
风格基调：{style_tone}

当前集位置：{episode_position}
前一集：{prev_episode}
当前集：{current_episode}
后一集：{next_episode}

请将当前集展开为 2-4 个详细场景，要求：
1. 第一个场景必须从"前一集"的结尾状态自然衔接开始，不能凭空切换场景
2. 场景的 content 包含完整的场景描述、对白和动作
3. 最后一个场景的结尾必须与"后一集"的开头衔接，留好过渡
4. 场景之间衔接自然，节奏紧凑
5. sort_order 从 0 开始连续递增

JSON 结构如下：
{{
  "children": [
    {{
      "node_type": "scene",
      "title": "场景标题",
      "content": "【场景】场景描述\\n\\n【对白】\\n角色A：对白内容\\n\\n【动作】\\n动作描述",
      "sort_order": 0
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",
    },
    "expand": {
        "system": "你是一位专业的动态漫剧本撰写师，擅长将场景概述扩展为生动的对白和动作描述。你的写作应当：对白自然流畅、符合人物性格；动作描述清晰、画面感强；情节紧凑、节奏感强。",
        "user": """剧本标题：{title}

【当前节点】
节点类型：{node_type}
节点标题：{node_title}
当前内容：{content}

【上下文信息】
{context}

额外指令：{instructions}

请扩展并完善当前节点内容，确保与上下文保持连贯。直接输出扩展后的内容：""",
    },
    "rewrite": {
        "system": "你是一位专业的动态漫剧本编辑，擅长根据指令精准改写内容，保持动态漫的风格特点和叙事连贯性。",
        "user": """剧本标题：{title}

【当前节点】
节点类型：{node_type}
原始内容：{content}

【上下文信息】
{context}

改写指令：{instructions}

请按照指令改写内容，确保与上下文保持连贯。直接输出改写后的内容：""",
    },
    "global_directive": {
        "system": "你是一位专业的动态漫剧本总监，负责确保整部剧本的风格统一、人物性格一致和情节连贯。",
        "user": """剧本标题：{title}
全局指令：{directive}

需要调整的内容：
{content}

请根据全局指令调整内容，保持整体风格一致性。直接输出调整后的内容：""",
    },
}


def _get_prompts(script_type: str) -> Dict[str, Dict[str, str]]:
    """根据剧本类型获取提示词模板"""
    if script_type == "explanatory":
        return EXPLANATORY_PROMPTS
    return DYNAMIC_PROMPTS


def calc_outline_max_tokens(episode_count: int) -> int:
    """根据集数动态计算 outline 生成所需 max_tokens，上限 32000"""
    return min(32000, max(8000, episode_count * 150))


def _build_history_text(history: List[Dict[str, Any]]) -> str:
    """将对话历史格式化为文本"""
    if not history:
        return "（暂无历史记录）"
    lines = []
    for item in history:
        role = "AI" if item.get("role") == "assistant" else "用户"
        lines.append(f"{role}：{item.get('content', '')}")
    return "\n".join(lines)


class ScriptAIService:
    """
    剧本 AI 服务
    根据项目的 ai_config 选择合适的 provider 和模型
    API keys 来自全局 settings，不存储在 ai_config 中
    """

    def __init__(
        self,
        ai_config: Optional[Dict[str, Any]] = None,
        project_settings: Optional[Dict[str, Any]] = None,
    ):
        self.ai_config = ai_config or {}
        self.project_settings = project_settings or {}
        self.provider = self.ai_config.get("provider") or settings.DEFAULT_AI_PROVIDER
        self.model = self._resolve_model()
        self.temperature = self._resolve_temperature()
        self.max_tokens = self._resolve_max_tokens()
        self.custom_prompts: Dict[str, Any] = self.ai_config.get("prompt_config") or {}

    def _build_settings_context(self) -> str:
        """将非空设定字段构建为可注入 system prompt 的字符串"""
        s = self.project_settings
        lines = ["【剧本设定】"]
        chars = s.get("characters", [])
        if chars:
            lines.append("人物：")
            for c in chars:
                name = c.get("name", "未命名角色")
                desc = c.get("description") or ""
                if desc:
                    lines.append(f"  - {name}：{desc}")
                else:
                    lines.append(f"  - {name}")
        if s.get("world_setting"):
            lines.append(f"世界观：{s['world_setting']}")
        if s.get("tone"):
            lines.append(f"风格基调：{s['tone']}")
        if s.get("plot_anchors"):
            lines.append(f"核心要素：{s['plot_anchors']}")
        if s.get("persistent_directive"):
            lines.append(f"持久指令：{s['persistent_directive']}")
        return "\n".join(lines) if len(lines) > 1 else ""

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

    def _get_system_prompt(self, key: str, script_type: str) -> Optional[str]:
        """获取系统提示词：优先使用用户自定义，否则用默认；前置注入 project_settings"""
        if isinstance(self.custom_prompts, dict):
            custom = self.custom_prompts.get("system_prompt")
            if custom:
                base: Optional[str] = custom
            else:
                prompts = _get_prompts(script_type)
                prompt_entry = prompts.get(key, {})
                base = prompt_entry.get("system") if isinstance(prompt_entry, dict) else None
        else:
            prompts = _get_prompts(script_type)
            prompt_entry = prompts.get(key, {})
            base = prompt_entry.get("system") if isinstance(prompt_entry, dict) else None

        settings_ctx = self._build_settings_context()
        if not settings_ctx:
            return base
        if base:
            return f"{settings_ctx}\n\n{base}"
        return settings_ctx

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

    async def generate_question(
        self,
        script_type: str,
        title: str,
        concept: Optional[str],
        history: List[Dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """生成下一个 AI 问题（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["question"]
        prompt = prompt_entry["user"].format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
        )
        system_prompt = self._get_system_prompt("question", script_type)
        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def generate_outline(
        self,
        script_type: str,
        title: str,
        concept: Optional[str],
        history: List[Dict[str, Any]],
        episode_count: int = 20,
    ) -> AsyncGenerator[str, None]:
        """生成剧本大纲（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["outline"]

        # 动态漫使用 episode_count 占位符，解说漫不需要
        if script_type == "dynamic":
            prompt = prompt_entry["user"].format(
                title=title,
                concept=concept or "（未提供）",
                history=_build_history_text(history),
                episode_count=episode_count,
            )
            # 动态计算 max_tokens
            dynamic_max_tokens = calc_outline_max_tokens(episode_count)
            original_max_tokens = self.max_tokens
            self.max_tokens = max(self.max_tokens, dynamic_max_tokens)
        else:
            prompt = prompt_entry["user"].format(
                title=title,
                concept=concept or "（未提供）",
                history=_build_history_text(history),
            )
            original_max_tokens = self.max_tokens

        system_prompt = self._get_system_prompt("outline", script_type)
        messages = self._build_messages(prompt, system_prompt)
        try:
            async for chunk in self._stream(messages):
                yield chunk
        finally:
            self.max_tokens = original_max_tokens

    async def expand_episode(
        self,
        title: str,
        outline_summary: str,
        main_characters: List[str],
        core_conflict: str,
        style_tone: str,
        episode_index: int,
        total_episodes: int,
        current_episode: Dict[str, Any],
        prev_episode: Optional[Dict[str, Any]],
        next_episode: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[str, None]:
        """展开单集为详细场景（SSE 流式）"""
        prompt_entry = DYNAMIC_PROMPTS["expand_episode"]

        def _ep_str(ep: Optional[Dict[str, Any]]) -> str:
            if not ep:
                return "（无）"
            return f"{ep.get('title', '')}：{ep.get('content', '')}"

        # 判断故事阶段
        ratio = (episode_index + 1) / total_episodes
        if ratio <= 0.2:
            stage = "开端阶段"
        elif ratio <= 0.6:
            stage = "发展阶段"
        elif ratio <= 0.85:
            stage = "高潮阶段"
        else:
            stage = "结局阶段"

        prompt = prompt_entry["user"].format(
            title=title,
            outline_summary=outline_summary,
            main_characters="、".join(main_characters) if main_characters else "（未指定）",
            core_conflict=core_conflict or "（未指定）",
            style_tone=style_tone or "（未指定）",
            episode_position=f"第 {episode_index + 1} 集 / 共 {total_episodes} 集，处于{stage}",
            prev_episode=_ep_str(prev_episode),
            current_episode=_ep_str(current_episode),
            next_episode=_ep_str(next_episode),
        )
        system_prompt = prompt_entry["system"]
        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def expand_node(
        self,
        script_type: str,
        title: str,
        node_type: str,
        node_title: Optional[str],
        content: Optional[str],
        instructions: Optional[str],
        context: str = "",
    ) -> AsyncGenerator[str, None]:
        """展开节点内容（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["expand"]
        prompt = prompt_entry["user"].format(
            title=title,
            node_type=node_type,
            node_title=node_title or "（无标题）",
            content=content or "（暂无内容）",
            instructions=instructions or "（无额外指令）",
            context=context or "（无上下文）",
        )
        system_prompt = self._get_system_prompt("expand", script_type)
        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def rewrite_content(
        self,
        script_type: str,
        title: str,
        node_type: str,
        content: str,
        instructions: str,
        context: str = "",
    ) -> AsyncGenerator[str, None]:
        """重写内容（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["rewrite"]
        prompt = prompt_entry["user"].format(
            title=title,
            node_type=node_type,
            content=content,
            instructions=instructions,
            context=context or "（无上下文）",
        )
        system_prompt = self._get_system_prompt("rewrite", script_type)
        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def global_directive(
        self,
        script_type: str,
        title: str,
        directive: str,
        content: str,
    ) -> AsyncGenerator[str, None]:
        """全局指令处理（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["global_directive"]
        prompt = prompt_entry["user"].format(
            title=title,
            directive=directive,
            content=content,
        )
        system_prompt = self._get_system_prompt("global_directive", script_type)
        messages = self._build_messages(prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def generate_summary(
        self,
        script_type: str,
        title: str,
        concept: Optional[str],
        history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """根据问答历史生成结构化摘要"""

        history_text = "\n".join([
            f"{'用户' if m['role']=='user' else 'AI'}: {m.get('content', '')}"
            for m in history
        ])

        system_prompt = "你是一位专业的剧本策划师，擅长从对话中提炼关键创作信息，以结构化 JSON 格式输出。你必须严格输出 JSON 格式，不输出任何其他内容。"

        prompt = f"""根据以下对话历史，提取剧本创作的关键信息，以 JSON 格式输出。

剧本类型: {script_type}
标题: {title}
创意概念: {concept or '（未提供）'}

对话历史:
{history_text}

请输出以下 JSON 结构（不要输出其他内容，键名使用中文）:
{{
  "故事概要": "一句话描述核心剧情",
  "主要角色": ["角色1名称及简介", "角色2名称及简介"],
  "核心冲突": "核心冲突描述",
  "场景设定": "主要场景设定",
  "风格基调": "风格基调（如悬疑、温情、喜剧等）"
}}"""

        messages = self._build_messages(prompt, system_prompt)
        full_response = ""
        async for chunk in self._stream(messages):
            full_response += chunk

        # 解析 JSON
        json_str = full_response.strip()
        start = json_str.find('{')
        end = json_str.rfind('}')
        if start != -1 and end != -1:
            json_str = json_str[start:end+1]

        return json.loads(json_str)
