"""
AI 服务层
支持 OpenAI / Anthropic / Ollama 三种 Provider + 内置演示模式
提供续写、改写、扩写、大纲生成、角色分析等功能
"""
import asyncio
import json
import logging
import random
from typing import AsyncGenerator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Prompt 模板
PROMPTS = {
    "continue": """你是一位经验丰富的小说作家。请根据以下已有内容，自然流畅地续写故事。
要求：
- 保持与原文一致的文风、语气和叙事节奏
- 续写内容应紧密衔接上文，情节合理推进
- 注意人物性格的一致性
- 续写约300-500字

{context}

已有内容：
{content}

请续写：""",

    "rewrite": """你是一位经验丰富的文学编辑。请对以下段落进行改写润色。
要求：
- 提升文字质量，使表达更生动优美
- 保留原文核心意思和情节走向
- 可以调整句式结构，增加修辞手法
- 保持原文的叙事视角和语气

{context}

需要改写的内容：
{content}

改写后：""",

    "expand": """你是一位经验丰富的小说作家。请对以下内容进行扩写，丰富细节和描写。
要求：
- 增加环境描写、心理描写或动作细节
- 扩写后的内容约为原文的2-3倍
- 保持原文的核心情节不变
- 使场景更加生动立体

{context}

需要扩写的内容：
{content}

扩写后：""",

    "outline": """你是一位经验丰富的小说策划。请根据以下信息，为小说生成一个详细的章节大纲。
要求：
- 包含主要情节线和转折点
- 每个章节有简短的内容概要（2-3句话）
- 注意故事节奏的起伏安排
- 生成10-15个章节的大纲

项目信息：
标题：{title}
类型：{genre}
简介：{description}

{context}

已有内容摘要：
{content}

请生成章节大纲：""",

    "character_analysis": """你是一位经验丰富的文学评论家。请根据以下内容分析角色。
要求：
- 分析角色的性格特征和行为动机
- 指出角色发展的可能方向
- 提供角色互动关系的建议
- 评估角色塑造的完整性

{context}

角色相关内容：
{content}

请分析：""",

    "analyze_expand": """你是一位经验丰富的文学评论家兼小说作家。请先对以下开头内容进行深度分析，然后基于分析结果进行扩写续写。

要求：
1. 先输出【开篇分析】部分，包含：
   - 文风与叙事视角：分析语言风格、叙事人称和叙事节奏
   - 人物线索：识别出场或暗示的人物及其初步特征
   - 场景氛围：分析环境描写营造的氛围和基调
   - 潜在主题：推断故事可能探讨的核心主题和方向

2. 再输出【扩写续写】部分：
   - 基于以上分析，自然衔接原文进行扩写续写
   - 保持与原文一致的文风和叙事视角
   - 丰富场景细节、人物刻画和情节推进
   - 扩写续写约800-1200字

{context}

开头内容：
{content}

请分析并扩写：""",

    "free_chat": """你是一位经验丰富的小说创作顾问。请根据用户的问题提供专业的创作建议。

{context}

当前章节内容：
{content}

用户问题：{question}

请回答：""",

    "revise": """你是一位经验丰富的文学编辑。请根据用户的修改意见，对以下章节内容进行修改。

要求：
- 仔细理解用户的修改意见，针对性地调整内容
- 保持原文的整体风格和叙事节奏
- 只修改需要修改的部分，保留其他内容的完整性
- 修改后的内容要自然流畅，与上下文衔接紧密
- 保持原文的叙事视角和人物性格

{context}

原始内容：
{content}

用户修改意见：{question}

请输出修改后的完整内容：""",

    "polish_character": """你是一位经验丰富的小说角色设计师。请对以下角色设定进行润色和格式整理。

要求：
- 保持原文的核心设定不变，只优化表达方式
- 使描述更加生动具体，避免空洞的形容词
- 整理内容格式，使其结构清晰、易于阅读
- 可以适当补充细节，但不要改变角色的核心特征
- 保持专业小说创作的风格

角色基本信息：
- 姓名：{title}
- 类型：{question}

角色设定内容：
{content}

请输出润色后的角色设定（保持原有的字段结构，直接输出内容即可）：""",

    "batch_outline": """你是一位经验丰富的小说策划。请根据以下信息，为小说生成一个包含 {chapter_count} 章的详细大纲。

要求：
- 严格生成 {chapter_count} 章的大纲
- 每个章节有明确的标题和内容概要（3-5句话）
- 注意故事节奏的起伏安排，包含起承转合
- 章节之间有清晰的情节递进关系

项目信息：
标题：{title}
类型：{genre}
简介：{description}

{context}

{style_reference}

{knowledge_reference}

请严格按以下 JSON 格式输出（不要输出其他内容）：
[
  {{"chapter": 1, "title": "章节标题", "summary": "章节内容概要"}},
  {{"chapter": 2, "title": "章节标题", "summary": "章节内容概要"}}
]""",

    "batch_chapter": """你是一位经验丰富的小说作家。请根据以下信息撰写小说的第 {chapter_index} 章。

要求：
- 【重要】字数必须达到约 {words_per_chapter} 字，不得少于 {min_words} 字，请充分展开情节、对话和描写
- 保持文风一致，情节紧凑
- 必须自然衔接上一章结尾的内容，保持情节连贯性
- 注意人物性格的一致性
- 直接输出章节正文，不要输出标题
- 每个章节都要有完整的起承转合，不要草草收尾

项目信息：
标题：{title}
类型：{genre}
简介：{description}

{context}

{style_reference}

{knowledge_reference}

完整大纲：
{outline_text}

当前章节大纲：
第 {chapter_index} 章「{chapter_title}」：{chapter_summary}

{previous_summary}

{previous_ending}

请撰写第 {chapter_index} 章的正文内容（注意紧密衔接上一章的结尾）：""",

    "wizard_outline_characters": """你是一位经验丰富的小说策划和角色设计师。请根据用户提供的故事构思，生成详细的章节大纲和主要角色设定。

项目信息：
标题：{title}
类型：{genre}
简介：{description}
目标字数：{target_word_count} 字
章节数量：{chapter_count} 章

{style_reference}

请严格按以下 JSON 格式输出（不要输出其他任何内容）：

第一步输出大纲（用 "===OUTLINE===" 标记开始）：
===OUTLINE===
[
  {{"chapter": 1, "title": "章节标题", "summary": "章节内容概要（3-5句话，包含主要情节和转折点）"}},
  {{"chapter": 2, "title": "章节标题", "summary": "章节内容概要"}}
]

第二步输出角色（用 "===CHARACTERS===" 标记开始）：
===CHARACTERS===
[
  {{"name": "角色名", "role_type": "protagonist/antagonist/supporting/minor", "gender": "性别", "age": "年龄", "occupation": "职业/身份", "personality_traits": "性格特征", "appearance": "外貌描写", "background": "背景故事"}}
]

要求：
1. 大纲要完整覆盖故事起承转合，注意节奏起伏
2. 每章概要要有具体的情节，不要笼统描述
3. 角色要有个性，避免脸谱化
4. 主角必须有完整的背景故事和成长动机
5. 配角也要有基本的性格和作用说明
""",

    "wizard_outline_only": """你是一位经验丰富的小说策划。请根据用户提供的故事构思，生成详细的章节大纲。

项目信息：
标题：{title}
类型：{genre}
简介：{description}
目标字数：{target_word_count} 字
章节数量：{chapter_count} 章

{style_reference}

请严格按以下 JSON 格式输出大纲（不要输出其他任何内容）：

===OUTLINE===
[
  {{"chapter": 1, "title": "章节标题", "summary": "章节内容概要（3-5句话，包含主要情节和转折点）"}},
  {{"chapter": 2, "title": "章节标题", "summary": "章节内容概要"}}
]

要求：
1. 大纲要完整覆盖故事起承转合，注意节奏起伏
2. 每章概要要有具体的情节，不要笼统描述
3. 第一章要有吸引人的开头，设置悬念或冲突
4. 最后一章要收束所有线索，给出完整结局
5. 注意故事节奏，高潮章节要有张力
""",

    "wizard_characters_from_outline": """你是一位经验丰富的角色设计师。请根据已确认的章节大纲，为主要角色创建详细的设定。

项目信息：
标题：{title}
类型：{genre}
简介：{description}

已确认的章节大纲：
{outline}

请严格按以下 JSON 格式输出角色（不要输出其他任何内容）：

===CHARACTERS===
[
  {{"name": "角色名", "role_type": "protagonist/antagonist/supporting/minor", "gender": "性别", "age": "年龄", "occupation": "职业/身份", "personality_traits": "性格特征", "appearance": "外貌描写", "background": "背景故事"}}
]

要求：
1. 根据大纲中的情节，推断并创建需要的角色
2. 角色要有个性，避免脸谱化
3. 主角必须有完整的背景故事和成长动机
4. 配角也要有基本的性格和作用说明
5. 角色数量适中，一般3-6个主要角色即可
""",

    "wizard_maps": """你是一位经验丰富的小说策划。请根据用户提供的故事构思，生成故事的主要场景地图。

项目信息：
标题：{title}
类型：{genre}
简介：{description}

{style_reference}

请根据故事需要，设计主要的故事发生地点（地图）。

请严格按以下 JSON 格式输出（不要输出其他任何内容）：

===MAPS===
[
  {{"name": "地图名称（如：青云宗、北境荒漠）", "description": "地图的简要描述，包括环境特点、氛围等"}}
]

要求：
1. 地图数量适中，一般2-5个主要场景
2. 每个地图要有独特的氛围和特点
3. 地图之间要有自然的联系，便于故事推进
4. 考虑故事类型，设计合适的场景
5. 地图名称要贴合故事背景
""",

    "wizard_parts": """你是一位经验丰富的小说策划。请根据故事构思和选定的地图，为该地图生成故事的部分划分。

项目信息：
标题：{title}
类型：{genre}
简介：{description}

当前地图：
地图名称：{map_name}
地图描述：{map_description}

{style_reference}

请为这个地图生成故事的部分划分，每个部分包含若干章节。

请严格按以下 JSON 格式输出（不要输出其他任何内容）：

===PARTS===
[
  {{"name": "部分名称（如：初入青云、宗门大比）", "summary": "这部分的故事概要（2-3句话）", "chapter_count": 章节数量}}
]

要求：
1. 部分数量适中，一般2-4个部分
2. 每个部分有独立的故事弧线
3. 部分之间要有情节递进
4. 考虑地图的特点来设计情节
""",

    "wizard_chapters_for_part": """你是一位经验丰富的小说策划。请根据故事构思，为指定的部分生成详细的章节大纲。

项目信息：
标题：{title}
类型：{genre}
简介：{description}

当前地图：{map_name}
当前部分：{part_name}
部分概要：{part_summary}

{style_reference}

请为这个部分生成详细的章节大纲。

请严格按以下 JSON 格式输出（不要输出其他任何内容）：

===CHAPTERS===
[
  {{"chapter": 章节序号, "title": "章节标题", "summary": "章节内容概要（3-5句话）"}}
]

要求：
1. 章节数量要符合部分的设定
2. 每章有明确的情节推进
3. 章节之间有自然的过渡
4. 注意故事节奏，有起有伏
""",

    "wizard_characters_for_part": """你是一位经验丰富的角色设计师。请根据已确认的部分大纲，为这部分创建出场角色设定。

项目信息：
标题：{title}
类型：{genre}
简介：{description}

当前部分章节大纲：
{outline}

已有角色库（可以复用）：
{existing_characters}

请为这部分创建出场角色，如果已有角色库中有合适的角色，可以复用。

请严格按以下 JSON 格式输出（不要输出其他任何内容）：

===CHARACTERS===
[
  {{"name": "角色名", "role_type": "protagonist/antagonist/supporting/minor", "gender": "性别", "age": "年龄", "occupation": "职业/身份", "personality_traits": "性格特征", "appearance": "外貌描写", "background": "背景故事", "is_new": true/false（是否是新角色）}}
]

要求：
1. 根据大纲中的情节，推断需要哪些角色
2. 如果已有角色库中有合适的，标记 is_new: false
3. 新角色要有个性，避免脸谱化
4. 角色数量适中
""",

    "wizard_revision": """你是一位经验丰富的小说策划和角色设计师。用户对之前生成的大纲和角色设定提出了修改意见，请根据意见进行调整优化。

项目信息：
标题：{title}
类型：{genre}
简介：{description}
目标字数：{target_word_count} 字
章节数量：{chapter_count} 章

{style_reference}

当前大纲：
{current_outline}

当前角色：
{current_characters}

用户修改意见：
{revision_request}

请根据用户的修改意见，调整大纲和角色设定，然后严格按以下 JSON 格式输出（不要输出其他任何内容）：

第一步输出修改后的大纲（用 "===OUTLINE===" 标记开始）：
===OUTLINE===
[
  {{"chapter": 1, "title": "章节标题", "summary": "章节内容概要（3-5句话，包含主要情节和转折点）"}},
  {{"chapter": 2, "title": "章节标题", "summary": "章节内容概要"}}
]

第二步输出修改后的角色（用 "===CHARACTERS===" 标记开始）：
===CHARACTERS===
[
  {{"name": "角色名", "role_type": "protagonist/antagonist/supporting/minor", "gender": "性别", "age": "年龄", "occupation": "职业/身份", "personality_traits": "性格特征", "appearance": "外貌描写", "background": "背景故事"}}
]

要求：
1. 认真理解用户的修改意见，做出针对性调整
2. 保持大纲和角色设定的整体一致性
3. 保留未被修改部分的优点
4. 调整后的内容要更加符合用户期望
""",

    "remove_ai_traces": """你是一位专业的文学编辑，擅长修改润色小说文本，消除 AI 生成的痕迹，使其更加自然、人性化。

请对以下章节内容进行润色修改：

要求：
1. 【字数控制】目标字数约 {target_words} 字，当前 {current_words} 字
   - 如果字数偏少（少于目标 80%），需要适当扩充细节、描写和对话
   - 如果字数偏多（超过目标 120%），需要精简冗余内容
   - 字数偏差在 ±10% 以内可保持不变

2. 【消除 AI 痕迹】注意以下常见问题：
   - 避免过于工整、对称的句式结构
   - 减少重复性的过渡词（如"然而""于是""这时"等）
   - 避免过于刻板的"起承转合"结构
   - 减少空洞的描写，增加具体细节
   - 对话要更自然，减少书面化表达

3. 【保持原有风格】
   - 保留原文的核心情节和人物性格
   - 维持原文的叙事风格和语气
   - 不要改变故事走向

4. 【润色提升】
   - 增加生动的比喻和细节描写
   - 让人物对话更贴近真实口语
   - 增强场景的画面感和代入感

章节标题：{chapter_title}

原文内容：
{content}

请输出润色后的章节内容（只输出正文，不要标题）：""",
}

# 内置演示内容模板
DEMO_RESPONSES = {
    "continue": [
        """他深吸一口气，咸湿的海风灌满胸腔。远处的星际港口在晨光中闪烁着金属般的光泽，那是人类文明延伸向宇宙深处的桥梁。

"陆远！"身后传来母亲略带焦急的呼唤，"回来吃早饭了！"

他回过头，看见母亲站在渔屋门口，围裙上还沾着面粉。那张曾经年轻美丽的面庞，因为岁月和忧愁刻上了深深的纹路。他知道，每当他望向那片星空时，母亲的心都在隐隐作痛。

"来了。"他应了一声，却没有立刻迈步。

就在这时，一艘银色的小型穿梭机划破天际，低空掠过渔村上方。引擎发出低沉的嗡鸣，在平静的海面上激起层层涟漪。陆远的目光追随着那道银色的轨迹，直到它消失在星际港口的方向。

他的手不自觉地握紧了衣兜里那枚父亲留下的星际通行证——那是他唯一的遗物，也是唯一的线索。通行证的全息表面在阳光下微微闪烁，仿佛在诉说着一个未完的故事。

"总有一天，"他在心中默默许下承诺，"我会找到你，父亲。"

远处，渔船的汽笛声悠扬地响起，新的一天开始了。但对陆远来说，这一天注定会与以往不同——因为命运的齿轮，已经悄然转动。""",
    ],
    "rewrite": [
        """晨曦初绽，第一缕金光穿透低垂的薄雾，在浩渺的海面上铺展开一片碎金般的光影。海风裹挟着咸腥的气息，轻柔地拂过码头斑驳的木桩。

陆远伫立在栈桥的尽头，修长的身影在雾气中显得孤寂而坚定。他微微眯起那双如鹰隼般锐利的眼睛，凝望着天际线上那若隐若现的巨大轮廓——星际港口的银色穹顶在晨光中忽明忽暗，宛如一颗沉睡的巨兽的眼睛。

一种说不清道不明的悸动在他胸腔中翻涌。那不仅仅是向往，更像是一种来自血脉深处的召唤，热烈而执拗，如同潮汐般不可阻挡。父亲的身影在记忆中已经模糊，但那个关于星辰大海的梦想，却随着岁月的流逝愈发清晰。""",
    ],
    "expand": [
        """清晨的阳光透过薄雾洒在海面上，波光粼粼如同碎金。那层薄雾是夜间海水蒸发凝结而成的，在晨光的照耀下呈现出一种梦幻般的淡紫色，仿佛给整个渔村披上了一层轻纱。空气中弥漫着海水特有的咸腥味，混合着远处渔船上飘来的柴油气息，以及码头边干鱼铺子里传出的淡淡鱼干香气。

陆远站在码头的尽头，脚下是被海水侵蚀多年的灰色石板，缝隙中生长着顽强的苔藓。他穿着一件洗得发白的蓝色短衫，赤着的双脚感受着石板上残留的夜间凉意。海风吹动他略长的黑发，露出那张被日光晒成小麦色的少年面庞，以及一双与年龄不相称的深邃眼眸。

他望着远方天际线上若隐若现的星际港口，心中涌起一股难以名状的向往。那座港口像一座悬浮在云端的银色城堡，巨大的环形结构在阳光下折射出七彩的光芒。每隔几分钟，就有一艘星际飞船从港口的发射通道中腾空而起，拖着一道璀璨的等离子尾焰，划破天际，消失在那无垠的深蓝之中。

"那里就是通往星辰大海的门户啊……"他喃喃自语，眼中映着那些远去的光点，如同映着一整片星河。""",
    ],
    "outline": [
        """# 《星辰大海》章节大纲

## 第一卷：渔村少年

### 第一章：码头的眺望
陆远是海滨渔村的普通少年，父亲在一次星际远航中失踪。每天清晨，他都会站在码头尽头眺望星际港口，心中充满对未知宇宙的向往。

### 第二章：父亲的遗物
陆远在家中阁楼发现父亲留下的星际通行证和一本加密日志。通行证上有一个神秘的坐标标记，指向银河系边缘的未知星域。

### 第三章：星际港口
陆远偷偷前往星际港口，结识了一位退役的星际导航员——老船长赵铭。赵铭认出了通行证上的标记，告诉他那是传说中的"零号航线"。

### 第四章：离别之夜
母亲发现了陆远的计划，痛哭流涕地阻止他。经过一番深谈，母亲终于松口，将父亲留下的一块神秘水晶交给他，嘱咐他一定要平安归来。

## 第二卷：星际学院

### 第五章：入学考试
陆远凭借过人的空间感知能力通过了星际学院的选拔，进入导航系学习。他遇到了将成为一生挚友的林夕和竞争对手萧逸。

### 第六章：天赋觉醒
在一次实训中，陆远展现出罕见的"星感"天赋——能够直觉感应星际航线中的引力异常。这个能力与父亲的水晶产生了微妙的共鸣。

### 第七章：暗流涌动
学院中出现了针对陆远的神秘势力，有人试图夺取他的星际通行证。他逐渐发现，父亲的失踪并非意外，而是牵涉到一个巨大的阴谋。

## 第三卷：星际远航

### 第八章：首航启程
陆远以见习导航员的身份登上星际探索舰"破晓号"，开始了他的第一次星际远航。目标：追溯父亲最后已知的航行轨迹。

### 第九章：虫洞迷航
穿越虫洞时遭遇引力风暴，陆远凭借"星感"天赋引导飞船脱险，却偏离了预定航线，来到了一片未被探索的星域。

### 第十章：古老文明
在一颗荒芜的行星上，发现了远古外星文明的遗迹。遗迹中的壁画描绘了一条连接银河系各臂的超级航线——"零号航线"的完整路径。

## 第四卷：真相与抉择

### 第十一章：父亲的踪迹
根据遗迹中的线索，陆远找到了父亲最后出现的星球。他发现父亲并没有死去，而是为了保护一个关于"零号航线"的秘密，选择了隐匿。

### 第十二章：星际阴谋
真相大白：星际联邦中的某个派系企图独占"零号航线"，控制银河系的交通命脉。父亲正是因为发现了这个阴谋才被追杀。

### 第十三章：最终抉择
陆远面临艰难的选择：公开"零号航线"的秘密，让全人类共享这条超级航线，但这意味着要与强大的势力为敌。

### 第十四章：星辰大海
陆远选择了勇气和正义，与伙伴们一起将"零号航线"的数据广播至全银河系。在父子重逢的那一刻，他终于理解了父亲当年的选择。

*尾声：陆远站在"破晓号"的舰桥上，望着面前那条通往银河深处的璀璨航线。星辰大海，从此不再是梦想，而是每一个勇敢者的征途。*""",
    ],
    "character_analysis": [
        """## 角色分析报告

### 陆远 - 主角深度分析

**性格特征：**
陆远是一个典型的"被命运选中"的少年角色，但他的独特之处在于内在的矛盾性：
- **勇敢与犹豫并存**：他渴望追随父亲的足迹探索星际，却又顾虑母亲的感受，这种拉扯使他更加真实可信
- **好奇心驱动型人格**：对未知有着天然的亲近感，这既是他最大的优势，也是潜在的弱点
- **善良但倔强**：一旦认定目标，便很难被说服放弃，这种执拗源于对父亲的思念和对真相的渴求

**行为动机：**
- 表层动机：寻找失踪的父亲
- 深层动机：证明自己的价值，不再是"被保护"的角色
- 核心驱动：对自由与未知的向往（血脉中的冒险因子）

**角色发展建议：**
1. **成长弧线**：建议从"为父亲而出发"逐渐转变为"为自己的信念而战"，完成内在动机的升华
2. **弱点设计**：可以增加一些具体的性格弱点，如过度自信导致的判断失误，增强角色的立体感
3. **关系网络**：需要设计一个与陆远形成对照的角色（亦敌亦友），通过冲突推动角色成长

**完整性评估：**
- 基础设定完善度：★★★★☆（背景故事清晰，但日常生活细节可以更丰富）
- 动机合理性：★★★★★（多层动机设计合理）
- 成长空间：★★★★★（有充足的发展余地）
- 独特性：★★★☆☆（建议增加更独特的个人特质或习惯来增强辨识度）""",
    ],
    "analyze_expand": [
        """【开篇分析】

**文风与叙事视角：**
本文采用第三人称有限视角，以主角陆远的感知为中心展开叙事。语言风格兼具文学性与画面感，善于运用视觉意象（"波光粼粼如同碎金"、"金属般的光泽"）营造氛围。叙事节奏舒缓而克制，以静态描写为主，暗含内在的情感张力。整体文风偏向青春科幻文学，兼有抒情散文的质感。

**人物线索：**
- 陆远（主角）：渔村少年，内心渴望星辰大海，与父亲有未了的羁绊。性格中有倔强与温柔并存的特质——他应了母亲的呼唤"却没有立刻迈步"，暗示内心的挣扎与坚定。
- 母亲：围裙沾面粉的传统形象，焦急中透着无奈，暗示她了解儿子的向往却无力阻止。
- 父亲（缺席人物）：通过遗物"星际通行证"存在于叙事中，是推动主角行动的核心动力。

**场景氛围：**
渔村与星际港口的对照构成空间张力——一边是传统、宁静、烟火气息的渔村生活，一边是现代、宏大、充满未知的星际文明。晨光、海风、薄雾共同营造出一种"黎明将至"的氛围，暗示主角即将踏上旅程。

**潜在主题：**
成长与离别、寻找与回归、个人命运与星际文明的碰撞。父子关系将是核心情感线，"星际通行证"既是物理线索也是情感纽带。

---

【扩写续写】

陆远终于转过身，向渔屋走去。晨光在他身后拉出一道瘦长的影子，像一条无形的线，将他与远方的星际港口连接在一起。

推开那扇被海风侵蚀得有些发涩的木门，屋内弥漫着温暖的面香。母亲已经在粗木桌上摆好了早餐——一碗热气腾腾的海鲜粥，几个刚出锅的葱油饼，还有一碟用本地海盐腌制的小鱼干。这些平凡的食物，是这个渔村千百年来不曾改变的味道，即便外面的世界已经进入了星际纪元。

"又在看那边了？"母亲背对着他，声音刻意放得很轻，像是怕惊碎什么易碎的东西。她的手在围裙上擦了擦，没有回头。

陆远在桌前坐下，用勺子搅动着粥碗里的虾仁，没有立刻回答。粥的热气升腾起来，模糊了他的视线，恍惚间，他似乎又看到了父亲坐在对面的样子——那个男人总是吃得很快，然后用粗糙的大手揉乱他的头发，笑着说"小远，今晚爸爸给你讲织女星的故事"。

那是多少年前的事了？五年？还是六年？记忆像被海水浸泡过的旧照片，边缘模糊，中心的影像却愈发清晰。

"妈，"他终于开口，声音有些沙哑，"港口下个月有一批见习导航员的选拔，我……"

话还没说完，母亲手中的陶碗"啪"地磕在了灶台上。屋内突然安静下来，只剩下墙角老式全息收音机里传出的天气播报——"渔政提醒：本周银河系第三旋臂方向有中等规模的离子风暴，请各星际航线注意避让……"

母亲的背影微微颤抖了一下，然后她深吸一口气，继续擦拭着那个并不需要擦拭的碗。

"吃完早饭再说。"她只说了这五个字。

陆远低下头，将手伸进衣兜，指尖触到了那枚通行证冰凉的金属边缘。全息芯片在他的体温下微微发热，仿佛某种古老的感应正在苏醒。他不知道的是，就在三千光年之外，一艘漂泊已久的飞船正在向着银河系的方向缓缓转向，而飞船驾驶舱里，一个同样磨损的通行证正闪烁着与他手中完全相同的频率。

命运的两端，即将交汇。""",
    ],
    "free_chat": [
        """这是一个很好的开篇设置！关于您的创作，我有以下建议：

**关于故事节奏：**
开篇以陆远在码头眺望的静态场景切入，很好地建立了故事的基调——宁静中蕴含着对远方的渴望。建议在前三章中逐步加快节奏，通过一个突发事件（如发现父亲的遗物、一艘神秘飞船降落在渔村附近等）来打破这份宁静，推动故事进入主线。

**关于世界观构建：**
科幻小说的世界观需要在前期巧妙地铺陈。建议通过陆远的日常生活自然地展示这个世界的科技水平和社会结构，而不是大段的说明文字。比如通过他观察星际港口的飞船起降、村里的全息广播新闻等细节来传达信息。

**关于情感线索：**
父子关系是故事的核心情感线。建议在叙事中穿插一些关于父亲的具体回忆片段——不是笼统的叙述，而是具体的场景（如父亲教他识别星座、给他讲述星际航行的故事等），让读者与角色一起建立对这位缺席父亲的情感认同。

**写作技巧建议：**
您的文笔流畅优美，善于运用视觉意象。可以进一步丰富感官描写，加入声音（海浪、汽笛、引擎轰鸣）、气味（海风的咸腥）和触觉（脚下的石板、风中的温度），让场景更加沉浸。""",
    ],
}


class AIService:
    """AI 写作助手服务"""

    @staticmethod
    def _get_available_provider(requested: str = None) -> str:
        """获取可用的 AI provider，无可用时返回 demo"""
        provider = requested or settings.DEFAULT_AI_PROVIDER

        if provider == "openai" and settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("sk-xxx", "", None):
            return "openai"
        if provider == "anthropic" and settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None):
            return "anthropic"
        if provider == "ollama":
            return "ollama"

        # 自动降级：检查其他可用 provider
        if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("sk-xxx", "", None):
            return "openai"
        if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None):
            return "anthropic"

        # 无可用 provider，使用演示模式
        return "demo"

    @staticmethod
    def _get_context_text(
        characters: list = None,
        worldbuilding: list = None,
    ) -> str:
        """构建上下文信息文本"""
        parts = []
        if characters:
            char_lines = []
            for c in characters[:10]:
                line = f"- {c.get('name', '未命名')}({c.get('role_type', '配角')})"
                if c.get('personality'):
                    line += f"，性格：{c['personality']}"
                if c.get('background'):
                    line += f"，背景：{c['background'][:200]}"
                if c.get('appearance'):
                    line += f"，外貌：{c['appearance'][:100]}"
                char_lines.append(line)
            parts.append(f"角色设定：\n" + "\n".join(char_lines))
        if worldbuilding:
            world_info = "\n".join(
                f"- {w.get('name', '未命名')}: {w.get('description', '')[:200]}"
                for w in worldbuilding[:10]
            )
            parts.append(f"世界观设定：\n{world_info}")
        return "\n\n".join(parts) if parts else ""

    @staticmethod
    async def generate_stream(
        action: str,
        content: str,
        provider: str = None,
        title: str = "",
        genre: str = "",
        description: str = "",
        question: str = "",
        characters: list = None,
        worldbuilding: list = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式生成 AI 内容
        返回 SSE 格式的文本流
        """
        actual_provider = AIService._get_available_provider(provider)
        context = AIService._get_context_text(characters, worldbuilding)

        # 构建 prompt
        prompt_template = PROMPTS.get(action, PROMPTS["continue"])
        prompt = prompt_template.format(
            content=content[:3000],
            context=context,
            title=title,
            genre=genre,
            description=description,
            question=question,
        )

        if actual_provider == "demo":
            async for chunk in AIService._stream_demo(action):
                yield chunk
        elif actual_provider == "openai":
            async for chunk in AIService._stream_openai(prompt):
                yield chunk
        elif actual_provider == "anthropic":
            async for chunk in AIService._stream_anthropic(prompt):
                yield chunk
        elif actual_provider == "ollama":
            async for chunk in AIService._stream_ollama(prompt):
                yield chunk

    @staticmethod
    async def generate_text(prompt: str, provider: str = None, max_tokens: int = None) -> str:
        """非流式生成，收集完整响应文本"""
        actual_provider = AIService._get_available_provider(provider)
        max_tokens = max_tokens or settings.AI_MAX_TOKENS_DEFAULT

        if actual_provider == "demo":
            return AIService._demo_outline_text()

        if actual_provider == "openai":
            try:
                from openai import AsyncOpenAI, RateLimitError, APIConnectionError, APITimeoutError
                client = AsyncOpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_BASE_URL,
                    timeout=600.0,
                )
                resp = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一位专业的中文小说创作助手，擅长各类文学创作。请严格按要求的格式输出。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.8,
                    max_tokens=max_tokens,
                )
                return resp.choices[0].message.content or ""
            except RateLimitError as e:
                logger.error(f"OpenAI 速率限制: {e}")
                raise RuntimeError("AI 服务繁忙，请稍后重试")
            except APIConnectionError as e:
                logger.error(f"OpenAI 连接错误: {e}")
                raise RuntimeError("无法连接到 AI 服务")
            except APITimeoutError as e:
                logger.error(f"OpenAI 超时: {e}")
                raise RuntimeError("AI 服务响应超时")
            except Exception as e:
                logger.error(f"OpenAI 未知错误: {e}", exc_info=True)
                raise RuntimeError(f"OpenAI 调用失败: {e}")

        if actual_provider == "anthropic":
            try:
                from anthropic import AsyncAnthropic, RateLimitError, APIConnectionError, APITimeoutError
                client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=600.0)
                resp = await client.messages.create(
                    model=settings.ANTHROPIC_MODEL,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    system="你是一位专业的中文小说创作助手，擅长各类文学创作。请严格按要求的格式输出。",
                    temperature=0.8,
                )
                return resp.content[0].text if resp.content else ""
            except RateLimitError as e:
                logger.error(f"Anthropic 速率限制: {e}")
                raise RuntimeError("AI 服务繁忙，请稍后重试")
            except APIConnectionError as e:
                logger.error(f"Anthropic 连接错误: {e}")
                raise RuntimeError("无法连接到 AI 服务")
            except APITimeoutError as e:
                logger.error(f"Anthropic 超时: {e}")
                raise RuntimeError("AI 服务响应超时")
            except Exception as e:
                logger.error(f"Anthropic 未知错误: {e}", exc_info=True)
                raise RuntimeError(f"Anthropic 调用失败: {e}")

        if actual_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": settings.OLLAMA_MODEL,
                            "prompt": prompt,
                            "system": "你是一位专业的中文小说创作助手，擅长各类文学创作。请严格按要求的格式输出。",
                            "stream": False,
                            "options": {
                                "num_predict": max_tokens,
                                "temperature": 0.8,
                            },
                        },
                        timeout=300.0,
                    )
                    data = response.json()
                    return data.get("response", "")
            except httpx.TimeoutException as e:
                logger.error(f"Ollama 超时: {e}")
                raise RuntimeError("AI 服务响应超时")
            except httpx.ConnectError as e:
                logger.error(f"Ollama 连接错误: {e}")
                raise RuntimeError("无法连接到 Ollama 服务")
            except Exception as e:
                logger.error(f"Ollama 未知错误: {e}", exc_info=True)
                raise RuntimeError(f"Ollama 调用失败: {e}")

        return ""

    @staticmethod
    def _demo_outline_text() -> str:
        """演示模式生成大纲 JSON"""
        return json.dumps([
            {"chapter": 1, "title": "命运的起点", "summary": "主角在平凡的生活中遭遇了一件改变命运的事件，被卷入一个未知的世界。"},
            {"chapter": 2, "title": "初入新世界", "summary": "主角开始适应新的环境，结识了第一位伙伴，同时发现了自己身上隐藏的特殊能力。"},
            {"chapter": 3, "title": "第一次考验", "summary": "主角面临第一个重大挑战，在伙伴的帮助下勉强度过危机，但也暴露了自身的不足。"},
            {"chapter": 4, "title": "暗流涌动", "summary": "表面平静之下，一股神秘势力开始关注主角。主角在探索过程中发现了更大的阴谋。"},
            {"chapter": 5, "title": "抉择时刻", "summary": "主角面对艰难的选择，最终做出了决定，踏上了新的征程。故事在充满希望的氛围中展开新篇章。"},
        ], ensure_ascii=False)

    @staticmethod
    async def _stream_demo(action: str) -> AsyncGenerator[str, None]:
        """内置演示模式：模拟流式输出预设内容"""
        responses = DEMO_RESPONSES.get(action, DEMO_RESPONSES["continue"])
        text = random.choice(responses)

        # 模拟打字效果：逐字符输出
        chunk_size = random.randint(2, 5)
        i = 0
        while i < len(text):
            end = min(i + chunk_size, len(text))
            chunk = text[i:end]
            yield f"data: {json.dumps({'text': chunk, 'demo': True}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.03)  # 模拟延迟
            i = end
            chunk_size = random.randint(2, 6)

        yield f"data: {json.dumps({'done': True, 'demo': True})}\n\n"

    @staticmethod
    async def _stream_openai(prompt: str) -> AsyncGenerator[str, None]:
        """OpenAI 流式生成（带重试）"""
        logger.info(f"开始 OpenAI 流式生成, model={settings.OPENAI_MODEL}, base_url={settings.OPENAI_BASE_URL}")
        from openai import AsyncOpenAI, RateLimitError, APIConnectionError, APITimeoutError

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                client = AsyncOpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_BASE_URL,
                    timeout=httpx.Timeout(connect=30.0, read=600.0, write=30.0, pool=30.0),
                )

                logger.info(f"正在调用 OpenAI API...（第 {attempt} 次尝试）")
                stream = await client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": "你是一位专业的中文小说创作助手，擅长各类文学创作。"},
                        {"role": "user", "content": prompt},
                    ],
                    stream=True,
                    stream_options={"include_usage": True},
                    temperature=0.8,
                    max_tokens=settings.AI_MAX_TOKENS_STREAM,
                )
                logger.info("OpenAI API 返回流，开始读取...")

                chunk_count = 0
                usage_info = None
                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        chunk_count += 1
                        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
                    # 捕获最后一个 chunk 中的 usage 信息
                    if hasattr(chunk, 'usage') and chunk.usage:
                        usage_info = {
                            'input_tokens': chunk.usage.prompt_tokens,
                            'output_tokens': chunk.usage.completion_tokens,
                            'total_tokens': chunk.usage.total_tokens,
                        }

                logger.info(f"OpenAI 流式生成完成，共 {chunk_count} 个 chunk")
                done_data = {'done': True}
                if usage_info:
                    done_data['usage'] = usage_info
                yield f"data: {json.dumps(done_data)}\n\n"
                return  # 成功完成，退出重试循环

            except RateLimitError as e:
                logger.error(f"OpenAI 流式生成速率限制: {e}")
                yield f"data: {json.dumps({'error': 'AI 服务繁忙，请稍后重试'}, ensure_ascii=False)}\n\n"
                return
            except APIConnectionError as e:
                logger.error(f"OpenAI 流式生成连接错误（第 {attempt} 次）: {e}")
                if attempt < max_retries:
                    wait = attempt * 2
                    logger.info(f"等待 {wait}s 后重试...")
                    retry_msg = f"\n[连接中断，正在重试（{attempt}/{max_retries}）...]\n"
                    yield f"data: {json.dumps({'text': retry_msg}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(wait)
                else:
                    yield f"data: {json.dumps({'error': '无法连接到 AI 服务，请稍后重试'}, ensure_ascii=False)}\n\n"
            except APITimeoutError as e:
                logger.error(f"OpenAI 流式生成超时（第 {attempt} 次）: {e}")
                if attempt < max_retries:
                    wait = attempt * 2
                    logger.info(f"等待 {wait}s 后重试...")
                    retry_msg = f"\n[请求超时，正在重试（{attempt}/{max_retries}）...]\n"
                    yield f"data: {json.dumps({'text': retry_msg}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(wait)
                else:
                    yield f"data: {json.dumps({'error': 'AI 服务响应超时，请稍后重试'}, ensure_ascii=False)}\n\n"
            except (httpx.RemoteProtocolError, httpx.ReadError) as e:
                logger.error(f"OpenAI 流式传输中断（第 {attempt} 次）: {e}")
                if attempt < max_retries:
                    wait = attempt * 2
                    logger.info(f"等待 {wait}s 后重试...")
                    retry_msg = f"\n[传输中断，正在重试（{attempt}/{max_retries}）...]\n"
                    yield f"data: {json.dumps({'text': retry_msg}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(wait)
                else:
                    yield f"data: {json.dumps({'error': 'AI 服务连接不稳定，请稍后重试'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"OpenAI 流式生成未知错误: {e}", exc_info=True)
                yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                return

    @staticmethod
    async def _stream_anthropic(prompt: str) -> AsyncGenerator[str, None]:
        """Anthropic Claude 流式生成"""
        try:
            from anthropic import AsyncAnthropic, RateLimitError, APIConnectionError, APITimeoutError

            client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=600.0)

            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=settings.AI_MAX_TOKENS_STREAM,
                messages=[{"role": "user", "content": prompt}],
                system="你是一位专业的中文小说创作助手，擅长各类文学创作。",
                temperature=0.8,
            ) as stream:
                async for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

            # 获取最终消息的 usage 信息
            final_message = await stream.get_final_message()
            done_data = {'done': True}
            if final_message and final_message.usage:
                done_data['usage'] = {
                    'input_tokens': final_message.usage.input_tokens,
                    'output_tokens': final_message.usage.output_tokens,
                    'total_tokens': final_message.usage.input_tokens + final_message.usage.output_tokens,
                }
            yield f"data: {json.dumps(done_data)}\n\n"

        except RateLimitError as e:
            logger.error(f"Anthropic 流式生成速率限制: {e}")
            yield f"data: {json.dumps({'error': 'AI 服务繁忙，请稍后重试'}, ensure_ascii=False)}\n\n"
        except APIConnectionError as e:
            logger.error(f"Anthropic 流式生成连接错误: {e}")
            yield f"data: {json.dumps({'error': '无法连接到 AI 服务'}, ensure_ascii=False)}\n\n"
        except APITimeoutError as e:
            logger.error(f"Anthropic 流式生成超时: {e}")
            yield f"data: {json.dumps({'error': 'AI 服务响应超时'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Anthropic 流式生成未知错误: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    @staticmethod
    async def _stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
        """Ollama 本地模型流式生成"""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "prompt": prompt,
                        "system": "你是一位专业的中文小说创作助手，擅长各类文学创作。",
                        "stream": True,
                        "options": {
                            "num_predict": 8000,
                            "temperature": 0.8,
                        },
                    },
                    timeout=300.0,
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if data.get("response"):
                                yield f"data: {json.dumps({'text': data['response']}, ensure_ascii=False)}\n\n"
                            if data.get("done"):
                                yield f"data: {json.dumps({'done': True})}\n\n"

        except httpx.TimeoutException as e:
            logger.error(f"Ollama 流式生成超时: {e}")
            yield f"data: {json.dumps({'error': 'AI 服务响应超时'}, ensure_ascii=False)}\n\n"
        except httpx.ConnectError as e:
            logger.error(f"Ollama 流式生成连接错误: {e}")
            yield f"data: {json.dumps({'error': '无法连接到 Ollama 服务'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Ollama 流式生成未知错误: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
