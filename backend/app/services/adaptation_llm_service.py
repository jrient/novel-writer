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

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.5, max_tokens: int = 64_000):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def complete(self, prompt: str, **kwargs) -> str:
        model = kwargs.get("model") or self.model
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = self.temperature
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        system = kwargs.get("system")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
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
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message", {}) or {}
            content = (msg.get("content") or "").strip()
            finish = choice.get("finish_reason")
            usage = data.get("usage", {}) or {}
            if content:
                return content
            # content 为空通常因为 reasoning 模型被 max_tokens 截断（finish=length，
                # reasoning_tokens ≈ max_tokens）。reasoning_content 是思考过程不是答案，
                # 不能当结果用——直接抛错让调用方决定（提示用户增大 max_tokens 或换非 reasoning 模型）。
            reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
            raise ValueError(
                f"LLM 返回空内容 (model={model}, finish={finish}, "
                f"completion_tokens={usage.get('completion_tokens')}, "
                f"reasoning_tokens={reasoning_tokens})；"
                f"reasoning 模型把预算耗在思考上，请增大 ADAPTATION_MAX_TOKENS "
                f"或将 ADAPTATION_EXTRACT_MODEL 配为非 reasoning 模型"
            )


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

def _strip_code_fence(raw: str) -> str:
    """剥离 ```json ... ``` 或 ``` ... ``` markdown 围栏，reasoning 模型常包这一层。"""
    s = (raw or "").strip()
    if not s.startswith("```"):
        return s
    s = s.strip("`").strip()
    if s.lower().startswith("json"):
        s = s[4:].strip()
    return s


_FORMAT_RULES = """\
【格式规范——必须遵守】
输出必须使用网文短剧格式，与以下范例一致：
- 第一行：场号标题行，按【本场标题】填写（如「1-1 开场快剪，旁白+画面」），其中的实体名按映射表替换
- 第二行：人物列表行，格式「人物：角色A 角色B 角色C」，列出本场出场的所有人物（用新名）
- 角色台词：角色名（情绪/动作）：台词内容
- 镜头指示：△【镜头类型】描述
- 旁白/内心独白：Vo/OS：内容
- 场景切换：切——
禁止使用电影剧本格式（如 **角色** 独立行 + 台白独立行）。"""


_REWRITE_INTENSITY_BODY = {
    1: "你只做精准的实体替换，处理同名消歧、称呼一致性、代词一致性。**严禁改动其他词。**",
    2: (
        "你是有经验的剧本改编师。任务：用编剧手法改写本场——不是逐句 paraphrase。\n"
        "**剧本改编 = 识别网感金句原样保留 + 压缩过场对白 + 按策略替换实体；"
        "不追求字面相似度低（那会毁掉爆点）。**\n"
        "\n"
        "【1. 识别「网感金句」（实体替换后原样保留，不许换说法）】\n"
        "- 内心独白（OS / Vo / 旁白）\n"
        "- 高潮反转的爆点（如「哦。」「成了。」「那不然我喝呀？！」「我以三魂七魄之术…」）\n"
        "- 咒语 / 招式名 / 信物术语 / 设定关键句\n"
        "- character_traits 里标注的「口头禅」\n"
        "- 短句反问与单字回应\n"
        "\n"
        "【2. 压缩非关键内容】\n"
        "- 多余配角的过场对白（嘲讽群、谄媚下属、围观甲乙）：**整行删除**\n"
        "- 反复同义的情绪渲染：合并成一句\n"
        "- 仅烘托氛围的旁白（美貌描写 / 服装细节 / 镜头美学 / 装饰描述）：**整行删除**\n"
        "- 与情节强相关的旁白（关键动作 / 道具特写 / 表情拐点 / 特效）：实体替换后保留\n"
        "\n"
        "【3. 实体替换按策略，不要机械换名】\n"
        "- mapping 表 [LOCKED]：严格按表替换\n"
        "- 主角 / 主反派：按 mapping 表换名\n"
        "- 角色昵称（小川、老婆、姐夫、傻子）：**保持不动**\n"
        "- 配角通称（庞经理、围观名媛、保镖头目等只出场 1-2 次的）：相关台词整行删除，不留通称\n"
        "- 道具：mapping 表指定的按表换；其余保留\n"
        "\n"
        "【示范】\n"
        "  原文 3 行：\n"
        "    老爷子（阴沉）：还有一个小时，必须按照道长的吩咐，让他在离婚协议上签字。\n"
        "    苏月娴（凑近，急切）：你爸说的没错，咱家好不容易搭上叶少这关系，颜颜，你可要好好讨叶少欢心才是！\n"
        "    刻薄女（晃动红酒，嗤笑）：果然是个傻子。就他这智商，他知道怎么签字吗？\n"
        "  改写 1 行（删 2 个配角过场，主线浓缩）：\n"
        "    陆父（阴沉）：还有一个小时，让林尘签字离婚。\n"
        "\n"
        "【输出】\n"
        "- 输出改写后的本场内容，第一行为场号标题行（按【本场标题】填写，实体名按映射表替换），第二行为人物列表行（格式「人物：角色A 角色B 角色C」，用新名）\n"
        "- **总行数应在原文 70%~130% 之间**，自然增减，不为凑长度凑话，也不刻意压缩\n"
        "- 不要解释 / 前后缀 / markdown 围栏\n"
        "\n"
        "【必守】\n"
        "- 本场剧情骨架（开场状态→冲突→拐点→结束状态）必须完整保留\n"
        "- 主角的关键动作 / 决策 / 顿悟 一处不可删\n"
        "- 识别出的「网感金句」必须原样出现（仅替换实体）"
    ),
    3: (
        "你是资深编剧。任务：按 era_target 与 intent 对本场做【时代重塑 + 编剧式改写】。"
        "**剧本改编 = 识别网感金句保留 + 删减冗余过场 + 道具艺术性替换 + 时代重塑；"
        "不追求字面相似度低，那会毁掉爆点。**\n"
        "\n"
        "【1. 时代重塑（era_target driven）】\n"
        "- 物件 / 职业 / 机构 / 生活方式 / 流行语 / 术语 按目标时代重写"
        "（例：当代医院 → 80 年代县医院；当代化验单 → 80 年代化验单；现代套房 → 大杂院；术语全部时代化）\n"
        "- 人物语言风格按时代调整（80 年代北方口语 / 民国白话 / 古风 等）\n"
        "\n"
        "【2. 识别「网感金句」（实体替换后原样保留）】\n"
        "- 内心独白（OS / Vo）、咒语 / 招式 / 信物术语句、口头禅、单字回应、爆点短句\n"
        "- 这些 paraphrase 即毁戏。例：「我以三魂七魄之术…」「成了。」「哦。」一字不许改\n"
        "\n"
        "【3. 删减非关键内容（编剧式裁剪）】\n"
        "- 多余配角（围观甲乙、谄媚下属、保镖头目、刻薄女等）：相关台词与镜头**整行删除**\n"
        "- 多余次要事件（次要冲突铺垫、过场寒暄、反复确认）：删\n"
        "- 仅烘托氛围的旁白（美貌描写 / 服装 / 镜头美学 / 环境装饰）：**整行删除**\n"
        "- 关键旁白（动作 / 关键道具 / 表情拐点 / 特效）：保留\n"
        "- 反复同义的情绪句：合并成一句\n"
        "\n"
        "【4. 实体替换按策略】\n"
        "- mapping 表 [LOCKED]：严格按表替换\n"
        "- 主角 / 主反派：按 mapping 表换名\n"
        "- 角色昵称（小川、老婆、姐夫、傻子）：**保持不动**\n"
        "- 配角通称（庞经理、围观名媛、保镖头目）：整行删除，不留通称\n"
        "- 道具：mapping 表指定的按表换；未指定的可**按情节戏剧需要替换为更带张力的同功能道具**"
        "（如「拖鞋→骨头」把人物当狗的羞辱程度升级），或按时代背景重选\n"
        "\n"
        "【示范：场内删 2 留 1+合并】\n"
        "  原文 4 行：\n"
        "    老爷子（拐杖猛地杵地）：爸这是为了你好！今晚必须当着所有顶级权贵，当着叶少的面，废了这个傻子赘婿！还你一个清白！\n"
        "    苏月娴（凑近，急切）：你爸说的没错，咱家好不容易搭上叶少这关系，颜颜，你可要好好讨叶少欢心才是！\n"
        "    刻薄女（晃动红酒，嗤笑）：果然是个傻子。就他这智商，他知道怎么签字吗？\n"
        "    宋颜（压低声音）：爸，今晚有必要这么大肆宣扬吗？让他直接走不行吗？\n"
        "  改写 2 行（删配角过场、压缩老爷子台词、保留宋颜对剧情的关键反对）：\n"
        "    陆父（阴沉）：还有一个小时，让林尘当众签字离婚。\n"
        "    陆语（压低声音）：爸，有必要这么大肆宣扬吗？\n"
        "\n"
        "【输出】\n"
        "- 输出改写后的本场内容，第一行为场号标题行（按【本场标题】填写，实体名按映射表替换），第二行为人物列表行（格式「人物：角色A 角色B 角色C」，用新名）\n"
        "- **总行数应在原文 70%~130% 之间**，自然增减，不为凑长度凑话，也不刻意大幅压缩\n"
        "- 不要解释 / 前后缀 / markdown 围栏\n"
        "\n"
        "【必守】\n"
        "- 本场剧情骨架（开场→冲突→拐点→结束）必须完整保留\n"
        "- 主角关键动作 / 决策 / 顿悟 一处不可删\n"
        "- 识别出的「网感金句」原样输出（仅替换实体）\n"
        "- character_traits 标注的「口头禅」在对应人物台词中至少出现一次"
    ),
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
        cleaned = _strip_code_fence(raw)
        try:
            data = json.loads(cleaned)
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
        cleaned = _strip_code_fence(raw)
        try:
            arr = json.loads(cleaned)
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
        scene_title: Optional[str] = None,
    ) -> str:
        # intensity=1：纯实体替换，保持单步
        if intensity == 1:
            body = _REWRITE_INTENSITY_BODY[1]
            prompt = self._build_single_pass_prompt(body, scene_text, intent, era_target, mappings, character_traits, prev_scene_summary, extra_prompt, scene_title)
            return _strip_code_fence(await self.provider.complete(prompt, model=self.rewrite_model, temperature=0.3))

        # intensity≥2：两步改写——先抽骨架，再从骨架重写
        return await self._two_pass_rewrite(
            scene_text=scene_text,
            intensity=intensity,
            intent=intent,
            era_target=era_target,
            mappings=mappings,
            prev_scene_summary=prev_scene_summary,
            character_traits=character_traits,
            extra_prompt=extra_prompt,
            scene_title=scene_title,
        )

    def _build_mapping_block(self, mappings: List[Dict[str, Any]]) -> str:
        mapping_lines = []
        for m in mappings:
            tag = "[LOCKED]" if m.get("locked") else ""
            repl = m.get("replacement_text") or "(待定)"
            mapping_lines.append(f"- {tag} [{m['entity_type']}] {m['original_text']} → {repl}")
        return "\n".join(mapping_lines) if mapping_lines else "(无)"

    def _build_traits_block(self, character_traits: List[Dict[str, Any]]) -> str:
        return "\n".join(
            f"- {t['name']}：{'、'.join(t.get('tags', []))}"
            for t in character_traits
        ) or "(无)"

    def _build_single_pass_prompt(
        self, body: str, scene_text: str, intent, era_target, mappings, character_traits, prev_scene_summary, extra_prompt, scene_title=None,
    ) -> str:
        mapping_block = self._build_mapping_block(mappings)
        traits_block = self._build_traits_block(character_traits)
        title_hint = f"\n【本场标题（场号标题行据此填写，实体名按映射表替换）】\n{scene_title}" if scene_title else ""
        return f"""你是剧本改编工程师。任务：在保剧情节奏不变的前提下，改写以下单场。

【强度规则】
{body}

{_FORMAT_RULES}
{title_hint}

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

    async def _two_pass_rewrite(
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
        scene_title: Optional[str] = None,
    ) -> str:
        """两步改写：Pass1 抽骨架+金句 → Pass2 从骨架重写（不看原文）。"""
        body = _REWRITE_INTENSITY_BODY.get(intensity, _REWRITE_INTENSITY_BODY[2])
        mapping_block = self._build_mapping_block(mappings)
        traits_block = self._build_traits_block(character_traits)

        # ── Pass 1：提取剧情骨架与金句 ──
        pass1_prompt = f"""你是剧本结构分析师。阅读下面的剧本原文，提取本场的「剧情骨架」与「必须保留的网感金句」。

输出严格 JSON：
{{
  "skeleton": "<本场剧情骨架，用 3~8 个节奏点描述，每个节奏点写明：人物+动作+情感>",
  "golden_lines": ["<必须原样保留的金句1>", "<金句2>", ...],
  "scene_beats": [
    {{"beat": "<节奏点描述>", "characters": ["<参与人物>"], "emotion": "<情绪>"}}
  ]
}}

提取规则：
- skeleton 涵盖开场状态→冲突→拐点→结束状态
- golden_lines 只收爆点短句、内心独白、口头禅、咒语招式名、单字回应
- 不要收普通对白——那些需要改写

【人物性格标签】
{traits_block}

【原文】
{scene_text}"""

        pass1_raw = await self.provider.complete(
            pass1_prompt,
            model=self.extract_model,
            temperature=0.3,
        )
        cleaned = _strip_code_fence(pass1_raw)
        try:
            skeleton_data = json.loads(cleaned)
        except json.JSONDecodeError:
            # 回退路径：用 intensity=1 的纯实体替换 body，避免在缺少金句兜底时仍执行
            # "删 2 留 1" 这种激进策略导致丢戏。
            logger.warning("Pass1 JSON 解析失败，回退到纯实体替换: %s", cleaned[:200])
            safe_body = _REWRITE_INTENSITY_BODY[1]
            return _strip_code_fence(await self.provider.complete(
                self._build_single_pass_prompt(safe_body, scene_text, intent, era_target, mappings, character_traits, prev_scene_summary, extra_prompt, scene_title),
                model=self.rewrite_model,
                temperature=0.3,
            ))

        skeleton = skeleton_data.get("skeleton", "")
        golden_lines = skeleton_data.get("golden_lines", [])
        scene_beats = skeleton_data.get("scene_beats", [])

        # ── Pass 2：基于骨架重写（不提供原文） ──
        golden_block = "\n".join(f"「{g}」" for g in golden_lines) if golden_lines else "(无)"
        beats_block = "\n".join(
            f"- {b.get('beat', '')}（{', '.join(b.get('characters', []))}，{b.get('emotion', '')}）"
            for b in scene_beats
        ) if scene_beats else "(无)"

        title_hint = f"\n【本场标题（场号标题行据此填写，实体名按映射表替换）】\n{scene_title}" if scene_title else ""
        pass2_prompt = f"""你是资深剧本改编师。根据下面的「剧情骨架」和「金句」，重新创作本场剧本。

**关键：你没有原文可以参照，你必须根据骨架从零创作剧本。**
- 每个节奏点都要写出对应的台词、旁白、镜头指示
- 金句必须原样出现在合适的位置，但其中的人名/地名/道具名必须按映射表替换（如「老张家」→「老陈家」）
- 其他台词和旁白必须是你重新创作的，不要凭空猜测原文

【强度规则】
{body}

{_FORMAT_RULES}
{title_hint}

【本场剧情骨架】
{skeleton}

【节奏点】
{beats_block}

【必须保留的金句（原样使用，但人名/地名按映射表替换）】
{golden_block}

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

直接输出创作好的本场剧本，不要解释或前后缀。"""

        # 温度 0.75：在"金句原样保留"硬约束下，过高温度（>0.85）会让模型改写金句
        # 或扭曲人物名，0.75 给创作空间但保留约束执行力。
        return _strip_code_fence(await self.provider.complete(
            pass2_prompt,
            model=self.rewrite_model,
            temperature=0.75,
        ))


def get_default_service() -> AdaptationLLMService:
    """使用配置中的 provider 构造服务。优先 deepseek，其次 openai。"""
    max_tokens = settings.ADAPTATION_MAX_TOKENS
    if settings.DEEPSEEK_API_KEY:
        provider = _OpenAICompatibleProvider(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            model=settings.ADAPTATION_REWRITE_MODEL or settings.DEEPSEEK_PRO_MODEL,
            max_tokens=max_tokens,
        )
    elif settings.OPENAI_API_KEY:
        provider = _OpenAICompatibleProvider(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_BASE_URL,
            model=settings.ADAPTATION_REWRITE_MODEL or settings.OPENAI_MODEL,
            max_tokens=max_tokens,
        )
    else:
        raise RuntimeError("未配置任何 LLM API Key，无法启动改编服务")
    return AdaptationLLMService(
        provider=provider,
        extract_model=settings.ADAPTATION_EXTRACT_MODEL,
        rewrite_model=settings.ADAPTATION_REWRITE_MODEL,
    )
