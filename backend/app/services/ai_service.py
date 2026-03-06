"""
AI 服务层
支持 OpenAI / Anthropic / Ollama 三种 Provider + 内置演示模式
提供续写、改写、扩写、大纲生成、角色分析等功能
"""
import asyncio
import json
import random
from typing import AsyncGenerator

from app.core.config import settings

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

    "free_chat": """你是一位经验丰富的小说创作顾问。请根据用户的问题提供专业的创作建议。

{context}

当前章节内容：
{content}

用户问题：{question}

请回答：""",
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
            char_info = "\n".join(
                f"- {c.get('name', '未命名')}({c.get('role_type', '配角')}): {c.get('personality', '无描述')}"
                for c in characters[:5]
            )
            parts.append(f"角色设定：\n{char_info}")
        if worldbuilding:
            world_info = "\n".join(
                f"- {w.get('name', '未命名')}: {w.get('description', '')[:100]}"
                for w in worldbuilding[:5]
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
        """OpenAI 流式生成"""
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
            )

            stream = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "你是一位专业的中文小说创作助手，擅长各类文学创作。"},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                temperature=0.8,
                max_tokens=2000,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    text = chunk.choices[0].delta.content
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    @staticmethod
    async def _stream_anthropic(prompt: str) -> AsyncGenerator[str, None]:
        """Anthropic Claude 流式生成"""
        try:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
                system="你是一位专业的中文小说创作助手，擅长各类文学创作。",
                temperature=0.8,
            ) as stream:
                async for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    @staticmethod
    async def _stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
        """Ollama 本地模型流式生成"""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{settings.OLLAMA_BASE_URL}/api/generate",
                    json={
                        "model": settings.OLLAMA_MODEL,
                        "prompt": prompt,
                        "system": "你是一位专业的中文小说创作助手，擅长各类文学创作。",
                        "stream": True,
                    },
                    timeout=120.0,
                )

                async for line in response.aiter_lines():
                    if line:
                        data = json.loads(line)
                        if data.get("response"):
                            yield f"data: {json.dumps({'text': data['response']}, ensure_ascii=False)}\n\n"
                        if data.get("done"):
                            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
