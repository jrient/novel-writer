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
    "question": """你是一位专业的解说漫剧本策划师。你需要通过提问来了解用户的创意，帮助生成高质量的解说漫剧本。

当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

请根据以上信息，提出下一个最关键的问题（一次只问一个问题），帮助我们了解：
- 解说的主题和核心内容
- 目标受众和风格
- 信息结构和叙事方式
- 视觉呈现要求

直接输出问题，不要加任何前缀或解释：""",

    "outline": """你是一位专业的解说漫剧本策划师。请根据以下收集的信息，生成一份完整的解说漫剧本大纲。

剧本基本信息：
标题：{title}
创意概念：{concept}

收集到的信息：
{history}

请生成一份 JSON 格式的大纲，包含以下结构：
{{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {{
      "node_type": "intro",
      "title": "引言标题",
      "content": "引言内容",
      "sort_order": 0
    }},
    {{
      "node_type": "section",
      "title": "段落标题",
      "content": "段落内容概述",
      "sort_order": 1,
      "children": [
        {{
          "node_type": "narration",
          "title": "旁白标题",
          "content": "旁白内容",
          "sort_order": 0
        }}
      ]
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",

    "expand": """你是一位专业的解说漫剧本撰写师。请根据以下节点信息，扩展并完善剧本内容。

剧本标题：{title}
节点类型：{node_type}
节点标题：{node_title}
当前内容：{content}
额外指令：{instructions}

请提供详细、生动的剧本内容扩展。要求：
- 符合解说漫的叙事风格
- 内容详实、信息准确
- 语言流畅、易于理解
- 适合配音和视觉呈现

直接输出扩展后的内容：""",

    "rewrite": """你是一位专业的解说漫剧本编辑。请根据以下指令对剧本内容进行改写。

剧本标题：{title}
节点类型：{node_type}
原始内容：{content}
改写指令：{instructions}

请按照指令改写内容，保持解说漫的风格特点。直接输出改写后的内容：""",

    "global_directive": """你是一位专业的解说漫剧本总监。请根据全局指令，对以下剧本内容进行调整。

剧本标题：{title}
全局指令：{directive}

需要调整的内容：
{content}

请根据全局指令调整内容，保持整体风格一致性。直接输出调整后的内容：""",
}

# 动态漫默认提示词
DYNAMIC_PROMPTS = {
    "question": """你是一位专业的动态漫剧本策划师。你需要通过提问来了解用户的创意，帮助生成高质量的动态漫剧本。

当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

请根据以上信息，提出下一个最关键的问题（一次只问一个问题），帮助我们了解：
- 故事背景和世界观
- 主要人物和关系
- 核心冲突和情节走向
- 分集结构和节奏

直接输出问题，不要加任何前缀或解释：""",

    "outline": """你是一位专业的动态漫剧本策划师。请根据以下收集的信息，生成一份完整的动态漫剧本大纲。

剧本基本信息：
标题：{title}
创意概念：{concept}

收集到的信息：
{history}

请生成一份 JSON 格式的大纲，包含以下结构：
{{
  "title": "剧本标题",
  "summary": "剧本总体概述",
  "sections": [
    {{
      "node_type": "episode",
      "title": "第一集标题",
      "content": "集概述",
      "sort_order": 0,
      "children": [
        {{
          "node_type": "scene",
          "title": "场景标题",
          "content": "场景描述",
          "sort_order": 0,
          "children": [
            {{
              "node_type": "dialogue",
              "title": null,
              "content": "对白内容",
              "speaker": "角色名",
              "sort_order": 0
            }},
            {{
              "node_type": "action",
              "title": null,
              "content": "动作描述",
              "sort_order": 1
            }}
          ]
        }}
      ]
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。""",

    "expand": """你是一位专业的动态漫剧本撰写师。请根据以下节点信息，扩展并完善剧本内容。

剧本标题：{title}
节点类型：{node_type}
节点标题：{node_title}
当前内容：{content}
额外指令：{instructions}

请提供详细、生动的剧本内容扩展。要求：
- 符合动态漫的叙事风格
- 对白自然流畅、符合人物性格
- 动作描述清晰、画面感强
- 情节紧凑、节奏感强

直接输出扩展后的内容：""",

    "rewrite": """你是一位专业的动态漫剧本编辑。请根据以下指令对剧本内容进行改写。

剧本标题：{title}
节点类型：{node_type}
原始内容：{content}
改写指令：{instructions}

请按照指令改写内容，保持动态漫的风格特点。直接输出改写后的内容：""",

    "global_directive": """你是一位专业的动态漫剧本总监。请根据全局指令，对以下剧本内容进行调整。

剧本标题：{title}
全局指令：{directive}

需要调整的内容：
{content}

请根据全局指令调整内容，保持整体风格一致性。直接输出调整后的内容：""",
}


def _get_prompts(script_type: str) -> Dict[str, str]:
    """根据剧本类型获取提示词模板"""
    if script_type == "explanatory":
        return EXPLANATORY_PROMPTS
    return DYNAMIC_PROMPTS


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

    def _get_system_prompt(self, key: str, script_type: str) -> Optional[str]:
        """获取系统提示词：优先使用用户自定义，否则用默认"""
        if isinstance(self.custom_prompts, dict):
            custom = self.custom_prompts.get("system_prompt")
            if custom:
                return custom
        return None

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
        template = prompts["question"]
        prompt = template.format(
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
    ) -> AsyncGenerator[str, None]:
        """生成剧本大纲（SSE 流式）"""
        prompts = _get_prompts(script_type)
        template = prompts["outline"]
        prompt = template.format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
        )
        system_prompt = self._get_system_prompt("outline", script_type)
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
    ) -> AsyncGenerator[str, None]:
        """展开节点内容（SSE 流式）"""
        prompts = _get_prompts(script_type)
        template = prompts["expand"]
        prompt = template.format(
            title=title,
            node_type=node_type,
            node_title=node_title or "（无标题）",
            content=content or "（暂无内容）",
            instructions=instructions or "（无额外指令）",
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
    ) -> AsyncGenerator[str, None]:
        """重写内容（SSE 流式）"""
        prompts = _get_prompts(script_type)
        template = prompts["rewrite"]
        prompt = template.format(
            title=title,
            node_type=node_type,
            content=content,
            instructions=instructions,
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
        template = prompts["global_directive"]
        prompt = template.format(
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

        messages = self._build_messages(prompt, None)
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
