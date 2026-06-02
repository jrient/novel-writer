# backend/app/services/prose_pipeline.py
"""散文生成 pipeline：FETCH → OUTLINE → STYLE_SEARCH → GENERATE。

流程：
  1. FETCH        从数据库剧本节点或上传文本获取剧本原文
  2. OUTLINE      LLM 将剧本提炼为 2-4 章的故事大纲（内部，不对外暴露）
  3. STYLE_SEARCH 检索风格样本库，生成风格指南
  4. GENERATE     按章顺序生成散文，每章携带上章结尾作为衔接上下文
"""
import asyncio
import json
import logging
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.prose_project import ProseProject, ProseScene
from app.models.script_node import ScriptNode
from app.services.prose_event_bus import prose_event_bus
from app.services.style_sample_indexer import search_style_samples

logger = logging.getLogger(__name__)

# ── Prompts ────────────────────────────────────────────────────────────────────

OUTLINE_SYSTEM = """你是知乎盐选（盐言故事）的资深签约编辑，负责将剧本改编为盐选爆款短篇小说的创作大纲。

【盐选叙事内核——大纲必须围绕这些来搭】
- 强冲突驱动：每章都有一个明确的冲突/悬念/反转推动剧情，不靠氛围和心理铺陈撑场
- 钩子前置：第一章开篇就甩出反常事件或尖锐冲突，绝不慢热铺背景
- 章末留扣：每一章结尾都埋一个悬念或反转钩子，把读者拽向下一章
- 情绪爽点：虐/爽/反转的情绪节点清晰，读者要有"想往下翻"的冲动
- 第三人称限知视角：紧贴主角，但叙事节奏快、信息密度高

【重要警告】大纲中严禁出现任何剧本元素：
✗ 场号（如 1-1、第2场）
✗ 角色冒号格式（如"李明："、"旁白："）
✗ 镜头说明（如"特写"、"推镜"、"△"）
✗ 时间地点标注行（如"医院急救室外 夜"）
大纲必须是纯叙事视角，描述故事情节、冲突走向与关键反转。

严格按以下格式输出，不得有多余内容：
第一章：[标题]
[本章叙事：80-150字，用第三人称写清本章的核心冲突、剧情推进、关键反转，并点明章末钩子]

第二章：[标题]
[本章叙事：80-150字]

（章数按故事规模决定：简单故事2章，普通3章，复杂4章，最多5章）

要求：
- 提炼故事核心：保留主要人物关系、核心冲突、情感弧线
- 章节间因果紧密、悬念递进，每章都要"事件有进展、悬念有抬升"
- 大纲内容要能支撑每章写出约3000字的盐选风格小说（情节密度足够，不靠注水）
- 【强制，不可违反】将剧本中所有角色的姓名100%替换为全新的虚构中文姓名，大纲中绝对禁止出现原剧本中的任何一个真实人名（哪怕只是顺手提及也不行）。替换规则：主角用平实常见的中文姓名（如陈浩、林晓雨等），配角依性别年龄取合适的名字，整篇大纲中同一角色从头到尾只用同一新名字，不得混用。"""

# 反 AI 味清单（盐选散文版，源自 style_guard.ANTI_SLOP_RULES，去掉镜头/分屏等剧本专属项）
PROSE_ANTI_SLOP = """【写作禁忌——绝对不要出现以下内容】
1. 过度抽象形容词（如"眼神中透露出坚毅的目光"）
2. 套路化比喻/暗喻（如"仿佛一把利刃刺穿了心"、"月光如水"）
3. 书面腔对白（角色说话要像真人日常对话，不像论文或演讲）
4. 环境描写先行的慢热开场（开篇禁止大段写景/缓慢交代背景，第一段就要进冲突）
5. 情绪解释代替情绪表现（不要写"她感到很伤心"，写"她眼眶红了，没说话"）
6. 总结性陈词与升华（不要写"这一刻他明白了勇气的真谛"，留白处理）
7. 万能动词"感到/觉得/变得/充满"（用具体阻力动词替代，如"指关节捏得咯吱响"）
8. 排比/三段论（禁止连续三个结构相似的句子或对白）
9. 为凑字数堆砌的环境与心理描写（字数靠情节推进和对话来填，不靠描写注水）"""

CHAPTER_SYSTEM_HEADER = """你是知乎盐选（盐言故事）的签约作者，专门创作盐选爆款短篇——节奏快、冲突强、反转密、读者一口气读完。

【盐选风格核心要求】
1. 第三人称限知视角，紧贴主角；语言口语化、干净利落，不要文绉绉的文学腔
2. 情节驱动：靠事件推进、冲突和反转抓人，不靠氛围渲染和大段内心戏拖节奏
3. 短句短段：多用短句，段落短小，留白多，读起来轻快不费力
4. 对白推进剧情：对话要像真人说话，自然带出冲突和信息，不是干燥问答也不是书面演讲
5. 情绪靠"演"不靠"说"：用动作、表情、对白外化情绪，绝不直接解释人物心情
6. 严禁任何剧本格式残留：场号（1-1等）、角色冒号对话（"张明："）、镜头说明、地点标注行、"△"符号
7. 【强制，不可违反】只使用大纲中给出的虚构人名，绝对禁止使用或还原任何原始剧本中的真实人名

直接输出小说正文，不加章节标题、不加任何说明文字。"""

_PREV_CONTEXT_CHARS = 1200  # 携带上章结尾的字数
_SCRIPT_TRUNCATE = 8000     # 发给大纲 LLM 的剧本最大字数

# 章节结尾被模型输出 token 上限截断的判定：正常结尾应落在这些句末标点上
_SENTENCE_END = "。！？…”』」）)】—"
_CONTINUE_TAIL_CHARS = 600  # 续写时回喂的结尾上下文字数

_CHAPTER_RE = re.compile(r"^第[零一二三四五六七八九十0-9]+章[：:]\s*(.*)")


# ── 工具函数 ────────────────────────────────────────────────────────────────────

def _parse_outline_chapters(outline: str) -> list[tuple[str, str]]:
    """将大纲文本解析为 [(章节标题, 章节大纲文本), ...] 列表。"""
    lines = outline.splitlines()
    heading_indices = [
        i for i, line in enumerate(lines) if _CHAPTER_RE.match(line.strip())
    ]
    if not heading_indices:
        return [("第一章", outline.strip())]

    chapters: list[tuple[str, str]] = []
    boundaries = heading_indices + [len(lines)]
    for start, end in zip(boundaries, boundaries[1:]):
        raw_title = lines[start].strip()
        body = "\n".join(lines[start + 1 : end]).strip()
        chapters.append((raw_title, f"{raw_title}\n{body}".strip()))
    return chapters


def _build_chapter_prompt(
    outline: str,
    chapter_title: str,
    chapter_outline: str,
    chapter_idx: int,
    total_chapters: int,
    prev_prose: str,
) -> str:
    is_first = chapter_idx == 0
    is_last = chapter_idx == total_chapters - 1

    parts = [
        f"请创作《{chapter_title}》的小说正文。",
        f"本章是全文第{chapter_idx + 1}章（共{total_chapters}章）。",
        "",
        "【创作要求】",
        "- 篇幅服从剧情：把本章该讲的冲突和反转讲完整、收束到位即可，不必凑字数也不要硬拉长；写到自然结束，绝不在句子或情节中途停笔",
        "- 盐选爆款节奏：情节驱动、冲突前置、反转密集，靠事件和对白推进，不靠氛围和心理戏拖慢",
        "- 第三人称限知视角，语言口语化干净，短句短段、多留白，读起来轻快",
        "- 情绪靠动作/表情/对白外化，绝不直接解释人物心情（不写\"他很愤怒\"，写他做了什么）",
        "- 对白像真人说话，自然带出冲突和信息，不要书面腔、不要干燥问答",
        f"{'- 这是第一章：开篇第一段就甩出反常事件或尖锐冲突抓住读者，禁止慢热铺背景' if is_first else ''}",
        f"{'- 这是中间章：结尾必须埋一个悬念或反转钩子，把读者拽向下一章' if (not is_first and not is_last) else ''}",
        f"{'- 这是第一章：除了开场钩子，章末也要留一个悬念钩子' if (is_first and not is_last) else ''}",
        f"{'- 这是最后一章：把核心悬念和反转收束利落，情绪给到位，结尾干脆不拖沓' if is_last else ''}",
        "",
        "【全文大纲（仅供参考，不要照抄）】",
        outline,
        "",
        "【本章创作重点】",
        chapter_outline,
    ]
    if prev_prose:
        tail = prev_prose[-_PREV_CONTEXT_CHARS:]
        parts += [
            "",
            "【上章结尾（请自然衔接，保持语气和视角一致）】",
            tail,
        ]
    parts += [
        "",
        f"现在请直接开始写《{chapter_title}》的正文，把本章剧情写完整、收束到位，不加标题：",
    ]
    return "\n".join(parts)


_STYLE_REF_HEADER = (
    "# 盐选爆款风格参考\n"
    "以下是检索到的盐选爆款风格指南与范例段落。请学习其句式长短、段落分隔节奏、"
    "对白口吻、情绪外化手法、开场钩子与收束方式。\n"
    "【注意】这些范例多为第一人称写作，但本任务一律采用前述【第三人称限知视角】，"
    "请只借鉴其节奏与语感，不要照搬第一人称（不要出现\"我\"作为主角自称）。"
)


def _build_style_system(snapshot: list[dict]) -> str:
    parts = [CHAPTER_SYSTEM_HEADER, PROSE_ANTI_SLOP]
    fragments = [s["prompt_fragment"] for s in snapshot if s.get("prompt_fragment")]
    excerpt = snapshot[0].get("prose_excerpt") if snapshot else None
    if fragments or excerpt:
        parts.append(_STYLE_REF_HEADER)
    if fragments:
        parts.append("\n\n".join(fragments))
    if excerpt:
        parts.append("# 参考段落（只学节奏语感，人称仍用第三人称）\n" + excerpt)
    return "\n\n".join(parts)


def _looks_truncated(prose: str) -> bool:
    """判定本章是否疑似被模型输出上限截断：非空且结尾不是正常句末标点。"""
    s = (prose or "").rstrip()
    if not s:
        return False
    return s[-1] not in _SENTENCE_END


async def _complete_chapter(
    provider: "_LLMProvider",
    user_msg: str,
    system_prompt: str,
    chapter_title: str,
    max_rounds: int = 2,
) -> str:
    """生成单章，若结尾疑似被截断则自动续写补完（最多 max_rounds 轮续写）。

    截断是 provider 静默保存的（finish_reason=length 仍返回部分内容），
    所以这里靠"结尾是否落在句末标点"来检测并续写。
    """
    prose = await provider.complete(user_msg, system=system_prompt)
    rounds = 0
    while _looks_truncated(prose) and rounds < max_rounds:
        rounds += 1
        tail = prose[-_CONTINUE_TAIL_CHARS:]
        cont_prompt = (
            f"下面是《{chapter_title}》的正文，因长度被中途截断了。"
            "请紧接着最后一个字继续写下去，直到本章剧情自然收束、结尾落在完整的句子上。"
            "只输出续写的部分，不要重复已有内容，不要加任何标题或说明。\n\n"
            "【已有正文结尾】\n" + tail
        )
        # 续写是补全兜底：失败不应丢掉已生成的正文，保留已有内容即可
        try:
            cont = await provider.complete(cont_prompt, system=system_prompt)
        except Exception as e:
            logger.warning("章节《%s》续写失败，保留已生成正文: %s", chapter_title, e)
            break
        if not cont.strip():
            break
        prose = prose + cont
    return prose


def _fetch_script_from_nodes(nodes) -> str:
    """将 ScriptNode 列表拼接为剧本文本。"""
    return "\n\n".join(
        (n.title + "\n" if n.title else "") + n.content
        for n in nodes if n.content and n.content.strip()
    )


# ── Provider ────────────────────────────────────────────────────────────────────

class _LLMProvider:
    async def complete(self, prompt: str, **kwargs) -> str: ...


def _get_default_provider() -> _LLMProvider:
    from app.services.adaptation_llm_service import get_default_service
    return get_default_service().provider


async def _search_style_samples(
    session: AsyncSession, query_vec: list, top_k: int, genre: Optional[str]
) -> list[dict]:
    return await search_style_samples(session, query_vec, top_k=top_k, genre=genre)


# ── Main pipeline ───────────────────────────────────────────────────────────────

async def run(
    session_factory: async_sessionmaker,
    project_id: int,
    provider: Optional[_LLMProvider] = None,
) -> None:
    """四步 pipeline 全流程。provider=None 时使用生产 LLM。"""
    if provider is None:
        provider = _get_default_provider()

    # ── Step 1: FETCH ───────────────────────────────────────────────────────────
    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one_or_none()
        if not project:
            logger.error("prose project %s not found", project_id)
            return

        if project.script_project_id is not None:
            nodes = (await session.execute(
                select(ScriptNode)
                .where(ScriptNode.project_id == project.script_project_id)
                .order_by(ScriptNode.sort_order)
            )).scalars().all()
            script_text = _fetch_script_from_nodes(nodes)
        else:
            script_text = project.script_content or ""

        if not script_text.strip():
            project.status = "failed"
            await session.commit()
            await prose_event_bus.publish(project_id, {"event": "project_failed", "status": "failed"})
            return

        premise = project.premise
        genre = project.genre

    # ── Step 2: OUTLINE ─────────────────────────────────────────────────────────
    await prose_event_bus.publish(project_id, {"event": "outline_start"})
    try:
        outline_prompt = (
            "以下是一部短剧剧本原文。请将其【改编】为知乎严选风格短篇小说的章节大纲。\n"
            "注意：大纲必须是纯文学叙事，完全去除剧本格式，提炼故事精髓后重新组织叙事结构。\n\n"
            "【剧本原文】\n"
            + script_text[:_SCRIPT_TRUNCATE]
        )
        outline = await provider.complete(outline_prompt, system=OUTLINE_SYSTEM)
    except Exception as e:
        logger.warning("outline generation failed, falling back to premise: %s", e)
        outline = f"第一章：{premise}\n{premise}"

    chapters = _parse_outline_chapters(outline)
    total_chapters = len(chapters)

    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one()
        project.outline = outline
        project.total_scenes = total_chapters
        project.status = "generating"
        for idx, (chapter_title, chapter_outline) in enumerate(chapters):
            session.add(ProseScene(
                project_id=project_id,
                scene_index=idx,
                scene_title=chapter_title,
                original_scene_text=chapter_outline,
            ))
        await session.commit()

    await prose_event_bus.publish(project_id, {
        "event": "outline_done",
        "total_chapters": total_chapters,
    })

    # ── Step 3: STYLE_SEARCH ────────────────────────────────────────────────────
    try:
        from app.services.embedding import embedding_service
        query_vec = await embedding_service.generate_embedding(premise)
        async with session_factory() as session:
            snapshot = await _search_style_samples(session, query_vec, top_k=3, genre=genre)
    except Exception as e:
        logger.warning("style sample search failed, degrading: %s", e)
        snapshot = []

    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one()
        project.style_snapshot = json.dumps(snapshot, ensure_ascii=False)
        await session.commit()

    system_prompt = _build_style_system(snapshot)

    # ── Step 4: GENERATE（顺序，每章携带上章结尾） ──────────────────────────────
    async with session_factory() as session:
        scenes = (await session.execute(
            select(ProseScene)
            .where(ProseScene.project_id == project_id)
            .order_by(ProseScene.scene_index)
        )).scalars().all()
        scene_rows = [(s.id, s.scene_index, s.scene_title, s.original_scene_text) for s in scenes]

    done = 0
    failed = 0
    prev_prose = ""

    for scene_id, scene_index, chapter_title, chapter_outline in scene_rows:
        async with session_factory() as session:
            sc = (await session.execute(
                select(ProseScene).where(ProseScene.id == scene_id)
            )).scalar_one()
            sc.status = "running"
            await session.commit()

        try:
            user_msg = _build_chapter_prompt(
                outline, chapter_title, chapter_outline,
                scene_index, total_chapters, prev_prose,
            )
            prose = await _complete_chapter(provider, user_msg, system_prompt, chapter_title)

            async with session_factory() as session:
                sc = (await session.execute(
                    select(ProseScene).where(ProseScene.id == scene_id)
                )).scalar_one()
                sc.prose_text = prose
                sc.status = "done"
                await session.commit()

            prev_prose = prose
            done += 1
            await prose_event_bus.publish(project_id, {
                "event": "scene_done",
                "scene_index": scene_index,
                "scene_title": chapter_title,
                "status": "done",
                "prose_text": prose,
            })

        except Exception as e:
            logger.exception("prose chapter %s generation failed", scene_id)
            async with session_factory() as session:
                sc = (await session.execute(
                    select(ProseScene).where(ProseScene.id == scene_id)
                )).scalar_one()
                sc.status = "failed"
                sc.error = str(e)[:1000]
                await session.commit()
            failed += 1
            await prose_event_bus.publish(project_id, {
                "event": "scene_done",
                "scene_index": scene_index,
                "scene_title": chapter_title,
                "status": "failed",
            })

    # ── 最终状态 ────────────────────────────────────────────────────────────────
    if failed == 0:
        final_status = "done"
    elif done == 0:
        final_status = "failed"
    else:
        final_status = "partial"

    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one()
        project.status = final_status
        project.done_scenes = done
        project.failed_scenes = failed
        await session.commit()

    await prose_event_bus.publish(project_id, {
        "event": "project_done" if final_status == "done" else "project_failed",
        "status": final_status,
    })
