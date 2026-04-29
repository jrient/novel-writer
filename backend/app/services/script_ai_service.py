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

# 按操作类型的默认温度映射
# 用户通过 ai_config.prompt_config.temperature 设置时仍全局覆盖（保留既有行为）
_DEFAULT_TEMPERATURE_BY_KEY: Dict[str, float] = {
    "question": 0.6,          # 引导式提问：需要逻辑推进，避免问跑题
    "outline": 0.75,          # 大纲：结构稳，兼顾反转创造力
    "episode_content": 0.9,   # 单集完整正文：台词/场景需要灵动
    "expand": 0.85,           # 节点展开：偏创作但有上下文约束
    "rewrite": 0.5,           # 改写润色：贴近原意
    "global_directive": 0.4,  # 全局指令：强确定性
    "summary": 0.3,           # 结构化 JSON 摘要：最低幻觉
}
_FALLBACK_TEMPERATURE = 0.7

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
        "system": """你是一位专业的分场剧本编剧，擅长用画面和对白讲故事，作品风格紧凑、情绪真实。

写作原则：
1. 用动作和画面推动剧情，不要写心理活动或旁白来交代信息
2. 开局直接切入冲突，不要空镜、不要缓慢铺垫
3. 台词像真人说话：口语化、有潜台词、短句为主
4. 主角靠自身智商和能力破局，不靠运气

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

将当前集（第{episode_number}集）扩展为完整分场剧本。严格限定在本集范围内，禁止写到下一集的事件中。

【停写边界规则】
后一集信息中给出了下一集要写什么事件。你的本集必须在该事件之前停笔——绝不提前写下一集的内容。

【格式】
每场起手：
  {episode_number}-1 场景名 时间 内/外
  人物：角色列表
  △ 动作/场景描写（短句，2-5行）
  角色（情绪）：台词

△ = 动作行，像分镜指令一样干脆
OS = 内心独白，仅在关键时刻，尽量少用
VO = 画外音，全剧最多1-2条

每集 3-5 场，场次号连续递增。

【核心要求】
- 第一行必须有强动作或强情绪（拍桌、摔门、角色逼近、推搡等），禁止环境描写开场
- 每集至少一个爽点当场兑现，不要拖到下一集
- 最后一行制造悬念（危机/反转/新人物出现）
- 台词口语化、短句为主，禁止书面语和解释性对白
- 不要用"渐渐地""仿佛""宛如""那一刻"等文学性修饰语
- 角色情绪通过行为和台词体现，不要写"他心里想着"

输出示例（仅示意格式，禁止照抄内容）：
{episode_number}-1 公司会议室 日 内
人物：李明、张总
△张总猛拍桌，文件飞散，茶杯震翻。
张总（暴怒）：三十万！你敢说不知道？！
△李明僵在椅上，嘴唇动了动，没出声。
张总（逼近，压低声音）：这次，也一样。
△李明缓缓抬头，眼眶泛红。
李明（隐忍→颤抖）：爸……我以为你会懂。
△张总愣住。
李明（决绝）：三十万是给妈的。她在等手术。
△张总脸色骤变。

直接从 {episode_number}-1 开始输出，不加任何前缀或解释：""",
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

你必须按照以下6个槽位依次收集信息，每次只问一个问题：
【槽位1】故事背景与世界观 — 故事发生在什么时代/世界？有什么特殊设定？
【槽位2】主要角色与关系 — 主角是谁？有哪些重要角色？主角有什么致命弱点/恐惧？反派为什么觉得自己是对的？
【槽位3】核心冲突与情节 — 故事的核心矛盾是什么？开局第一镜的强情绪冲击是什么（拍桌、摔门、崩溃）？
【槽位4】风格与爽点 — 希望什么风格基调？每集的爽点如何当场兑现（打脸/复仇/逆袭）？
【槽位5】差异化定位 — 对标作品是什么？本剧的独特卖点是什么？（如：你的主角与对标作品主角的核心区别）
【槽位6】集数与节奏 — 大约多少集？每集至少多少个冲突事件？

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
关键性问题是指：能够直接影响剧本质量评估维度的问题，如：
- 开局钩子是否强（第一镜必须有强情绪冲击）
- 人设是否有反差（主角弱点+反派逻辑）
- 冲突密度是否足够（每集至少3个冲突事件）
- 爽点链路是否清晰（每集爽点当场兑现）
- 差异化卖点是否明确（与对标作品的核心区别）

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
2. 每集的 content 必须为 80 字以内的一句话概要，包含：①承接上集 ②本集核心剧情 ③结尾状态（悬念或转折点）
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
      "content": "本集一句话概要（≤80字）",
      "sort_order": 0,
      "children": []
    }}
  ]
}}

注意：只输出 JSON，不要有其他内容。每集 content 严格控制在 80 字以内，不要展开详细剧情。""",
    },
    "episode_content": {
        "system": """你是一位专业的动态漫/短剧编剧，作品以冲突密集、台词接地气、节奏紧凑著称。

写作原则：
1. 主角靠自身智商和能力破局，不靠运气或天降救兵
2. 开局直接切入冲突，不要空镜、不要环境铺垫、不要缓慢建立场景
3. 台词像真人说话：口语化、有潜台词、短句为主，绝不用书面语或解释性对白
4. 用动作和行为推动剧情，不要用心理活动或旁白来交代信息
5. 每集至少一个爽点当场兑现，不要拖到下一集

格式：分场剧本格式，场景标题格式为"{N}-1 场景名 时间 内/外"。

你直接输出纯文本剧本，不输出 JSON，不使用任何标签或注释。""",
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

将第{episode_number}集扩展为完整分场剧本。严格限定在本集范围内，禁止写到下一集的事件中。

【停写边界规则】
后一集信息中给出了下一集要写什么事件。你的本集必须在该事件之前停笔——绝不提前写下一集的内容。

【格式规范】
每场起手：
  {episode_number}-1 场景名 时间 内/外
  人物：角色列表
  △ 动作/场景描写（短句，2-5行）
  角色（情绪）：台词

△ = 动作行（短句，像分镜指令一样干脆）
OS = 内心独白，少量使用，仅在关键时刻
VO = 画外音，极少使用，全剧最多1-2条

每集 3-5 场，场次号连续递增。

【核心要求】
- 第一个镜头必须有强动作或强情绪（拍桌、摔门、角色逼近、推搡等），禁止环境描写开场
- 每集至少一个爽点当场兑现（打脸/复仇/真相大白/逆袭），不要拖延
- 最后一行必须制造悬念（危机/反转/新人物出现）
- 台词口语化，短句为主，角色要有自己的说话风格
- 不要写"他心里想着"之类的心理描写，用行为和台词体现
- 禁止使用"渐渐地""仿佛""宛如""那一刻"等文学性修饰语

直接从 {episode_number}-1 开始输出，不加任何前缀、标题或解释：""",
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

# ─── 评审手册精华（v10 校准集 = 57 部编辑确认剧本） ─────────────────────────────
# 注入到 episode_content 的 system prompt，让模型显式对齐"签约线"。
# 同步源：script_rubric/outputs/handbook/ai_writer_prompt.compact.md
# 修改本常量后，必须同步更新 ai_writer_prompt.compact.md 与 ai_writer_prompt.md。
_HANDBOOK_DIGEST = """【精品剧本签约标准——必须对齐】

你正在写"精品短剧"，目标分数 ≥ 78（签约线）。
- 78+ = 签约 / 75-78 = 改稿 / <75 = 拒稿
- 最关键三维（签 vs 拒差距最大）：爽点兑现、人设立体度、对标差异化。先押这三维。

【单集硬指标（不可违反）】
- 每集字数 400-1000，行数 15-40，单场景 ≤ 20 行
- 对话 20-40 句，OS 占 20-30%
- 绝大多数台词 < 15 字
- 每集冲突 ≥ 2 次，打脸 ≥ 1 次
- 30 秒内必有冲突；> 5 行纯描述 = 拖沓
- 钩子结尾不能与前一集同类型

【爽点兑现铁律——签 vs 拒最大差】
- 当场兑现，禁止"下一集再报复"、"忍辱负重等时机"
- 欲扬先抑三步法（每 10 集 ≥ 3 次）：羞辱 → 旁观补刀 → 反击打脸
- 打脸 4 法轮换：物理 / 能力碾压 / 身份反转 / 证据信息差
- 禁止高潮处妥协（嬷嬷代受、突然气晕、转移惩罚）

【人设硬约束——签 vs 拒第二大差】
- 主角：表面标签 × 隐藏身份 × 标志性行为；不能 5 集以上只挨打不还手
- 反派：可脸谱化但不能降智；必须有可识别的标志动作或台词；不能第 7 集就被抓
- 每个女性角色必须有独立功能（靠山/智囊/武力/情感冲突/搞笑），禁止"漂亮+爱主角"工具人

【对标差异化——签 vs 拒第三大差】
- 必须能一句话说清"跟对标作品的核心区别"
- 区别必须是结构性（反向 / 跨频 / 设定颠覆），不是装饰性（颜值更高、服化更精）
- 集齐"马甲+双强+萌宝+带球跑"已不再是优势

【一票否决红线】
1. 古装语境塞现代网络词："大逼兜/视觉污染/现场直播/金主爸爸/老铁/我靠/天啦噜/祖国大大/一分钟啊大哥/老娘"
2. 单一场景拉扯 > 2 集
3. 反派降智 + 重复物理攻击水字数
4. 系统逼迫主角作恶 + OS 立牌坊（精神分裂式）
5. "精神病人的幻想"式终极反转（欺诈观众）
6. 触碰伦理底线 / 价值观扭曲（放弃赡养 / 反派因前世福报作恶）
7. 男频 / 女频爽点性转混用导致两头不讨好"""


# ─── 类型专项浮层（按 genre 注入） ─────────────────────────────────────────────
# 同步源：ai_writer_prompt.compact.md 的"类型专项浮层"小节。
# 关键字匹配：genre 包含某 key（或反之）即注入对应 overlay。
_GENRE_OVERLAY_RULES: Dict[str, str] = {
    "萌宝": """【类型专项·萌宝】
- 萌宝必须有反差感（反向带娃 / 好赌海量 / 反萌套路），常规乖巧奶团子无市场
- 男主前 3 集必须出场，延迟出场严重扣分
- 女主必须有独立高光，不能因萌宝抢戏而隐形
- 加权维度：premise_innovation、opening_hook；降权：常规元素堆砌""",

    "女频": """【类型专项·女频】
- CP 化学反应必须强，男女主前 10 集必有强宿命互动（反差人设："阳光金毛 × 阴湿大猫"）
- 女主必须现代独立感（搞钱 / 高智 / 武力），拒绝古早小白花、依赖男主
- 高潮禁止妥协：禁止嬷嬷代受、突然气晕、转移惩罚
- 古装语境绝对禁止现代网络词（一票否决）
- 加权：payoff_satisfaction、character_depth；降权：premise_innovation""",

    "男频": """【类型专项·男频】
- 极致直白爽点（物理碾压 / 数值碾压 / 一击秒杀）
- 微创新反差优先（植物成精 / 战力=银行卡余额 / 主动猎诡）
- 禁止古早开局："测天赋废柴 + 众人嘲笑 + 拜金女友当众分手"
- 设定与基调必须匹配：荒诞金手指 → 轻喜，禁止强写苦大仇深
- 反派禁止低级作恶（剪刹车线 / 口吐芬芳）
- 主角必须主动使用金手指，禁止"被动触发保护"
- 加权：payoff_satisfaction、premise_innovation；降权：character_depth""",

    "世情": """【类型专项·世情】
- 必须有冲击力社会议题或奇观设定（婆婆生三胎 / 72 套房 / 巨款被骗）
- 前 3 集完成"受气-爆发-反转"闭环，禁止 8 集才爆发
- 反派要有段位、有逻辑，禁止全员恶人 / 极端脸谱化
- 价值观红线一票否决：禁止放弃赡养 / 反人类 / 道德沦丧
- 直接竞品是抖音剧情号，反转力度必须超越短视频
- 加权：pacing_conflict、payoff_satisfaction、benchmark_differentiation""",
}


def _resolve_genre_overlay(genre: Optional[str]) -> Optional[str]:
    """根据 genre 字符串模糊匹配类型专项浮层。
    支持 "原创 / 萌宝"、"改编 / 女频" 等组合形式。
    """
    if not genre:
        return None
    for key, overlay in _GENRE_OVERLAY_RULES.items():
        if key in genre:
            return overlay
    return None


# ─── 前5集特别规则（来自 script_rubric handbook 经验总结） ─────────────────────
# 仅对 episode_index < 5 的正文生成生效，追加到 user prompt 末尾。
_EARLY_EPISODE_RULES = """

【第{ep}集·前5集强制规则——来自精品剧本评审经验，必须遵守】

第{ep}集处于开局阶段，必须执行以下规则：

1. **第一镜禁止平淡**：第一个镜头必须有强情绪冲击（拍桌/摔门/角色崩溃大哭/愤怒逼近/戏剧性事件），禁止大空镜、全景建立场景、缓慢环境描写、无动作的旁白开场
2. **核心角色必须露面**：主角（主角弱点+反派逻辑中涉及的角色）必须在第3集前全部出场，延迟出场会严重拖沓
3. **冲突速闭环**：第1-3集必须完成至少一次完整冲突闭环（挑衅/打压→反击/打脸→情绪释放），禁止"下一集再报复"的拖延
4. **禁止单一场景水字数**：同一场景/同一纠纷不能连续拉扯超过2集，必须引入新危机或升级冲突
5. **核心卖点必须落地**：大纲/标题承诺的奇观（金手指/异能/身份反转等）必须在前3集出现，不能只做铺垫
6. **单集至少3个冲突事件**：本集内必须有≥3个具体的冲突/对峙/反转事件，不能只写日常或背景交代
7. **集末必须有卡点**：本集结尾必须有悬念/反转/迫在眉睫的损失，驱动观众看下一集

【第 1 集额外铁律（仅 ep=1 必须同时满足 5 件套）】
若 {ep} = 1，必须**同时**完成：
① 5 秒内身份反差（极度弱势 + 隐藏金手指）
② 金手指实际效果展示（演出来，不能只口头说）
③ 反派压脸场景 ≥ 1 次
④ 钩子结尾（10 类钩子之一：悬念/打断/危机/反转/新人物/能力/情感/反派/预告/动作）
⑤ 通过具体行为展示主角性格（不是台词描述）"""


def _get_prompts(script_type: str) -> Dict[str, Dict[str, str]]:
    """根据剧本类型获取提示词模板"""
    if script_type == "explanatory":
        return EXPLANATORY_PROMPTS
    return DYNAMIC_PROMPTS


def _build_episode_system_prompt(
    base_system: str,
    script_type: str,
    genre: Optional[str] = None,
) -> str:
    """
    为 episode_content 构建多层 system prompt（顺序固定，下层覆盖上层语义）：
    1. 原始规则（base_system）
    2. handbook digest（v10 校准集精华：评分目标 + 7 维硬指标 + 红线）
    3. 类型专项浮层（按 genre 注入：萌宝 / 女频 / 男频 / 世情）
    4. 反 AI 味清单（最末，作为最强约束）
    """
    from app.services.style_guard import get_style_guard

    parts: List[str] = [base_system, _HANDBOOK_DIGEST]

    overlay = _resolve_genre_overlay(genre)
    if overlay:
        parts.append(overlay)

    sg = get_style_guard()
    anti_slop = sg.get_anti_slop_rules()
    if anti_slop:
        parts.append(anti_slop)

    return "\n\n".join(p for p in parts if p)


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
    """根据集数动态计算 outline 生成所需 max_tokens，上限 64000。
    每集大纲约 200 token（≤80 字概要 + JSON 开销），加 1500 token 结构开销。"""
    return min(64000, max(8000, episode_count * 200 + 1500))


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
        if self.provider == "deepseek":
            return settings.DEEPSEEK_PRO_MODEL
        return settings.OPENAI_MODEL

    def _resolve_temperature(self, key: Optional[str] = None) -> float:
        prompt_config = self.ai_config.get("prompt_config") or {}
        if isinstance(prompt_config, dict):
            t = prompt_config.get("temperature")
            if t is not None:
                return float(t)
        if key and key in _DEFAULT_TEMPERATURE_BY_KEY:
            return _DEFAULT_TEMPERATURE_BY_KEY[key]
        return _FALLBACK_TEMPERATURE

    def _apply_temperature(self, key: str) -> None:
        """根据操作类型切换 self.temperature（尊重用户 prompt_config 覆盖）"""
        self.temperature = self._resolve_temperature(key)
        logger.debug(
            "script_ai temperature[%s] = %.2f (provider=%s, model=%s)",
            key, self.temperature, self.provider, self.model,
        )

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

    # ─── DeepSeek ───────────────────────────────────────────────────────────

    async def _stream_deepseek(
        self, messages: List[Dict[str, str]]
    ) -> AsyncGenerator[str, None]:
        api_key = settings.DEEPSEEK_API_KEY or settings.SCRIPT_CONTENT_API_KEY or ""
        base_url = settings.DEEPSEEK_BASE_URL.rstrip("/")
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
        async with httpx.AsyncClient(timeout=180) as client:
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
        elif self.provider == "deepseek":
            async for chunk in self._stream_deepseek(messages):
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
        self._apply_temperature("question")
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
        self._apply_temperature("outline")
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
        self._apply_temperature("episode_content")
        prompts = _get_prompts(script_type)
        prompt_entry = prompts["episode_content"]

        def _ep_str(ep: Optional[Dict[str, Any]], role: str = "context") -> str:
            """role='prev'：传场景列表+结尾片段，防止任意场景被重复；role='next'：传下一集概要作为停写边界"""
            import re as _re
            if not ep:
                return "（无）"
            title = ep.get("title", "")
            content = ep.get("content", "")
            is_generated = ep.get("generated", False)
            if role == "next":
                # 下一集传概要（不含正文），作为本集的停写边界
                # 注意：content 可能是 outline 原文（一句话概要），不是已生成的正文
                summary = ep.get("content", "")
                if summary:
                    return f"{title}（下一集概要：{summary[:150]}）\n【停写边界：本集写到上述内容之前即可，绝不要覆盖下一集的内容】"
                return f"{title}（概要保密，写到标题相关场景即可，不要展开）"
            if role == "prev" and is_generated and len(content) > 200:
                # 提取所有场景标题行，如 "2-1 粮油店门口 日 外（闪回）"
                scene_headers = _re.findall(r'(?m)^\s*(\d+-\d+\s+[^\n]{2,40})', content)
                tail = content[-250:].lstrip()
                if scene_headers:
                    scene_list = "\n".join(f"  · {h.strip()}" for h in scene_headers[:12])
                    return (
                        f"{title}\n"
                        f"【上集已覆盖场景——本集禁止重复以下任何场景或事件】：\n{scene_list}\n"
                        f"【上集结尾（衔接线索）】：…{tail}"
                    )
                # 旧格式无场景标题：降级为开头+结尾片段
                head = content[:350].rstrip()
                return (
                    f"{title}\n"
                    f"【上集已交代内容（本集禁止重复）】：{head}…\n"
                    f"【上集结尾（衔接线索）】：…{tail}"
                )
            return f"{title}：{content}"

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
            "episode_number_next": episode_index + 2,
            "prev_episode": _ep_str(prev_episode, role="prev"),
            "current_episode": _ep_str(current_episode, role="context"),
            "next_episode": _ep_str(next_episode, role="next"),
        }

        prompt = prompt_entry["user"].format(**format_kwargs)
        system_prompt = prompt_entry["system"]

        # 注入 handbook digest + 类型专项浮层 + 反 AI 味清单到 system prompt
        system_prompt = _build_episode_system_prompt(system_prompt, script_type, genre=genre)

        # 注入范本+金句到 user prompt
        prompt = _build_episode_user_prompt(prompt, script_type, genre=genre)

        # 前5集特别规则：冲突密度/角色速出/爽点速兑（来自 script_rubric 经验）
        if episode_index < 5:
            prompt += _EARLY_EPISODE_RULES.format(ep=episode_index + 1)

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
        self._apply_temperature("expand")
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
        self._apply_temperature("rewrite")
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
        self._apply_temperature("global_directive")
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
        self._apply_temperature("summary")

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
  "故事概要": "一句话描述核心剧情（面向 AI 的凝练版本，1-2 句即可）",
  "主要角色": ["角色1名称及简介", "角色2名称及简介"],
  "核心冲突": "核心冲突描述",
  "场景设定": "主要场景设定",
  "风格基调": "风格基调（如悬疑、温情、喜剧等）",
  "主角弱点": "主角的致命弱点/恐惧/软肋，让读者产生代入感。如果没有明显弱点，写'暂无'",
  "反派逻辑": "反派为什么觉得自己是对的，不是纯坏。如果没有明确反派，写'暂无'",
  "开局钩子": "第一集的悬念/反转/迫在眉睫的损失，吸引读者继续看。如果没有，写'暂无'",
  "故事简介": "面向读者的剧情简介，3-5 段、500-800 字，类似豆瓣/小说网站简介风格，要有钩子和情感铺陈，不剧透关键反转",
  "人物小传": [
    {{
      "姓名": "角色姓名（必须与主要角色列表的姓名一致）",
      "身份": "年龄/职业/社会角色，50字内",
      "目标": "表面目标 + 内心渴望，50字内",
      "弱点": "致命弱点/恐惧/盲点，50字内",
      "关键关系": "与其他主要角色的关系，50字内",
      "典型台词": "一句能体现性格的台词，30字内"
    }}
  ]
}}

约束：
- 人物小传 与 主要角色 列表的人物必须一致；如对话信息不足以填充某字段，写"暂无"，不要编造。
- 故事简介 与 故事概要 不同：故事概要是给 AI 看的凝练版（1-2 句），故事简介是给读者看的展开版（3-5 段）。"""

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

        result = json.loads(json_str)

        # 强制：主要角色 由 人物小传 派生（人物小传 是 source of truth）
        bios = result.get("人物小传")
        if isinstance(bios, list) and bios:
            result["主要角色"] = [
                f"{b.get('姓名', '').strip()}：{b.get('身份', '').strip()}".rstrip("：")
                for b in bios
                if isinstance(b, dict) and b.get("姓名")
            ]

        return result
