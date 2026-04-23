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
from app.services.style_guard import get_style_guard

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
- 不要提及"槽位"这个词，像正常对话一样提问
- 你必须严格输出 JSON 格式，不输出任何其他内容""",
        "user": """当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

{handbook_context}

请根据已有信息，对下一个未完成的槽位提出关键性问题，并提供 3-5 个供用户选择的选项。
关键性问题是指：能够直接影响剧本质量评估维度的问题，如开局钩子是否强、人设是否有反差、冲突密度是否足够、爽点链路是否清晰等。
选项应当是该问题的常见回答或有启发性的建议，帮助用户快速做出选择。用户也可以不选择选项而自由输入。

严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"question": "你的问题", "options": ["选项1", "选项2", "选项3"]}}""",
    },
    "outline": {
        "system": "你是一位专业的解说漫剧本策划师，擅长将零散信息整合为结构清晰的剧本大纲。你必须严格输出 JSON 格式，不输出任何其他内容。",
        "user": """剧本基本信息：
标题：{title}
创意概念：{concept}
目标段落数：{episode_count}

收集到的信息：
{history}

请生成一份 JSON 格式的大纲，要求：
1. 必须生成恰好 {episode_count} 个完整段落，不能多也不能少，覆盖引言、正文各部分、结语
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
    "episode_content": {
        "system": """你是一位顶级分场剧本撰写师，擅长创作极具张力、情感丰富的短剧分场剧本。你的核心能力：
1. 开局绝不平淡：第一个镜头必须有强情绪冲击（拍桌、摔门、角色崩溃大哭、角色愤怒逼近），避免大空镜或缓慢建立场景
2. 对白层次丰富：每句对白要有情绪推进，从隐忍到爆发、从试探到摊牌，用停顿、断句制造张力，让对白成为情感载体而非信息传递工具
3. △ 动作行即画面：用特写、推镜头、闪回等镜头语言替代冗长的环境描写，动作与对白紧密交织
4. VO/OS 精简克制：每场至多1-2条，仅用于关键信息交代或心理揭示，绝不用旁白堆砌剧情

你直接输出纯文本分场剧本，不输出 JSON，不使用 Markdown。""",
        "user": """剧本信息：
标题：{title}
总体概述：{outline_summary}
主要角色：{main_characters}
核心冲突：{core_conflict}
风格基调：{style_tone}

当前集位置：{episode_position}
当前集编号：第{episode_number}集
前一集收尾：{prev_episode}
当前集概要：{current_episode}
后一集开头：{next_episode}

将当前集扩展为分场剧本，严格遵守以下规则：

【格式规范】
分场号：{episode_number}-1、{episode_number}-2……依次递增（3-5场）
每场结构：场次号行 → 地点行 → 人物行 → 正文（△动作/对白/VO/OS）

【开局爆点（第一场必须）】
第一镜必须是以下类型之一：
- 激烈动作：拍桌、摔东西、拽袖子、推搡、揪领子
- 强情绪特写：角色崩溃大哭、愤怒瞪眼、震惊表情、痛苦捂脸
- 戏剧性事件：门被踹开、文件摔桌上、手机砸地上
禁止使用：大空镜、全景建立场景、缓慢环境描写、无动作的旁白开场

【对白规范——情感层次是关键】
- 每句10-30字，情感丰富，可拆成多句表达
- 必带情绪括号，可叠加多层：角色名（隐忍→崩溃）：对白
- 对白要有起承转合：试探 → 压抑 → 爆发 → 后悔/决绝
- 用停顿、断句制造张力："我以为……（停顿）我以为你会懂。"
- 每人连续对白不超过3句，中间穿插动作或对方反应
- 避免说教、解释剧情、信息性对白

【△动作规范】
- 占全文≥30%，是剧本骨架
- 每行一个具体动作或镜头
- 动作与对白紧密交织：△张总猛拍桌，震得茶杯翻倒。 → 紧接对白
- 用镜头语言：△镜头特写XX颤抖的手、△推镜头至XX眼中泪光……

【VO/OS规范】
- 每场≤2条
- 仅用于关键转折或无法言说的心理
- 禁止用VO交代剧情背景

输出示例（仅示意格式与对白层次）：
{episode_number}-1
地点：日 内 办公室
人物：李明 张总
△张总猛拍桌，文件飞散，茶杯震翻。
张总（暴怒）：三十万！公司账上的三十万！你敢说不知道？！
△李明僵在椅上，嘴唇动了动，没出声。
张总（逼近，压低声音）：从小到大，你哪件事瞒得过我？这次，也一样。
△李明缓缓抬头，眼眶泛红。
李明（隐忍→颤抖）：爸……我以为你会懂。我以为，你至少会问一句我为什么要这么做。
△张总愣住。
李明（决绝）：三十万是给妈的。她在医院等着手术，而您——忙着开这间破公司。
△张总脸色骤变。

直接从 {episode_number}-1 开始输出，无任何前缀解释：""",
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
- 不要提及"槽位"这个词，像正常对话一样提问
- 你必须严格输出 JSON 格式，不输出任何其他内容""",
        "user": """当前会话历史：
{history}

剧本基本信息：
标题：{title}
创意概念：{concept}

{handbook_context}

请根据已有信息，对下一个未完成的槽位提出关键性问题，并提供 3-5 个供用户选择的选项。
关键性问题是指：能够直接影响剧本质量评估维度的问题，如开局钩子是否强、人设是否有反差、冲突密度是否足够、爽点链路是否清晰等。请参考上面提供的质量标准来提问。
选项应当是该问题的常见回答或有启发性的建议，帮助用户快速做出选择。用户也可以不选择选项而自由输入。

严格按以下 JSON 格式输出，不要输出任何其他内容：
{{"question": "你的问题", "options": ["选项1", "选项2", "选项3"]}}""",
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
1. 必须生成恰好 {episode_count} 集，不能多也不能少，覆盖故事的开端、发展、高潮、结局
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
    "episode_content": {
        "system": "你是一位专业的动态漫剧本撰写师，擅长将集概要展开为完整的叙事内容。你直接输出纯文本剧本，不输出 JSON，不使用结构化标签。",
        "user": """剧本信息：
标题：{title}
总体概述：{outline_summary}
主要角色：{main_characters}
核心冲突：{core_conflict}
风格基调：{style_tone}

当前集位置：{episode_position}
前一集：{prev_episode}
当前集概要：{current_episode}
后一集：{next_episode}

请将当前集扩展为一段完整的剧本文本，要求：
1. 800-1500 字
2. 包含自然穿插的对白、动作描写、心理活动和环境描写
3. 从"前一集"的结尾状态自然衔接开始，不要凭空切换
4. 结尾必须与"后一集"的开头衔接，留好过渡
5. 不要使用【场景】【对白】【动作】等结构化标签
6. 不要分场景，一气呵成
7. 对白自然流畅，符合人物性格

直接输出完整的剧本内容，不要有任何前缀或解释：""",
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


def _build_episode_system_prompt(
    base_system: str,
    script_type: str,
) -> str:
    """
    为 episode_content 构建三层 system prompt：
    1. 原始规则（base_system）
    2. 反 AI 味清单（追加到末尾）
    """
    from app.services.style_guard import get_style_guard

    sg = get_style_guard()
    anti_slop = sg.get_anti_slop_rules()
    if anti_slop:
        return f"{base_system}\n\n{anti_slop}"
    return base_system


def _build_episode_user_prompt(
    base_user: str,
    script_type: str,
    genre: Optional[str] = None,
) -> str:
    """
    为 episode_content 构建三层 user prompt：
    1. 原始生成指令（base_user）
    2. <examples> 范本+金句（追加到末尾）

    优先抽取同 genre 范本，不足时回退同 script_type 全池。
    """
    sg = get_style_guard()
    style_ctx = sg.build_style_context(script_type, genre=genre)
    if style_ctx:
        return f"{base_user}\n\n{style_ctx}"
    return base_user


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
        genre: str = "",
        handbook_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """生成下一个 AI 问题（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["question"]

        user_prompt = prompt_entry["user"].format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
            handbook_context=handbook_context or "【暂无专项知识】请基于通用创作质量标准和已提供的创意概念进行提问。",
        )

        system_prompt = self._get_system_prompt("question", script_type)

        # Inject handbook knowledge into system prompt
        if handbook_context:
            system_prompt = (system_prompt or "") + f"\n\n{handbook_context}"

        messages = self._build_messages(user_prompt, system_prompt)
        async for chunk in self._stream(messages):
            yield chunk

    async def generate_outline(
        self,
        script_type: str,
        title: str,
        concept: Optional[str],
        history: List[Dict[str, Any]],
        episode_count: int = 20,
        genre: str = "",
        handbook_context: str = "",
    ) -> AsyncGenerator[str, None]:
        """生成剧本大纲（SSE 流式）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["outline"]

        # 动态漫和解说漫都使用 episode_count 占位符
        prompt = prompt_entry["user"].format(
            title=title,
            concept=concept or "（未提供）",
            history=_build_history_text(history),
            episode_count=episode_count,
        )
        # 注入 handbook 到 system prompt（如果提供）
        extra = ""
        if handbook_context:
            extra = f"\n\n{handbook_context}"
        if genre and genre not in extra:
            extra += f"\n\n【项目题材】{genre}"

        # 动态计算 max_tokens
        dynamic_max_tokens = calc_outline_max_tokens(episode_count)
        original_max_tokens = self.max_tokens
        self.max_tokens = max(self.max_tokens, dynamic_max_tokens)

        system_prompt = self._get_system_prompt("outline", script_type)
        if extra and system_prompt:
            system_prompt = f"{system_prompt}{extra}"
        elif extra:
            system_prompt = extra
        messages = self._build_messages(prompt, system_prompt)
        try:
            async for chunk in self._stream(messages):
                yield chunk
        finally:
            self.max_tokens = original_max_tokens

    async def generate_episode_content(
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
        script_type: str = "dynamic",
        genre: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """生成单集/单段完整内容（SSE 流式，输出纯文本）"""
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["episode_content"]

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

        unit_name = "集" if script_type == "dynamic" else "段落"
        format_kwargs: Dict[str, Any] = {
            "title": title,
            "outline_summary": outline_summary,
            "main_characters": "、".join(main_characters) if main_characters else "（未指定）",
            "core_conflict": core_conflict or "（未指定）",
            "style_tone": style_tone or "（未指定）",
            "episode_position": f"第 {episode_index + 1} {unit_name} / 共 {total_episodes} {unit_name}，处于{stage}",
            "episode_number": episode_index + 1,
            "prev_episode": _ep_str(prev_episode),
            "current_episode": _ep_str(current_episode),
            "next_episode": _ep_str(next_episode),
        }

        prompt = prompt_entry["user"].format(**format_kwargs)
        system_prompt = prompt_entry["system"]

        # 注入反 AI 味清单到 system prompt
        system_prompt = _build_episode_system_prompt(system_prompt, script_type)

        # 注入范本+金句到 user prompt
        prompt = _build_episode_user_prompt(prompt, script_type, genre=genre)

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
  "风格基调": "风格基调（如悬疑、温情、喜剧等）",
  "主角弱点": "主角的致命弱点/恐惧/软肋，让读者产生代入感。如果没有明显弱点，写'暂无'",
  "反派逻辑": "反派为什么觉得自己是对的，不是纯坏。如果没有明确反派，写'暂无'",
  "开局钩子": "第一集的悬念/反转/迫在眉睫的损失，吸引读者继续看。如果没有，写'暂无'"
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
