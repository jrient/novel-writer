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

OUTLINE_SYSTEM = """你是专业的中文短篇小说策划。
任务：将剧本提炼为知乎严选风格短篇小说的章节大纲。

严格按以下格式输出，不得有其他内容：
第一章：[标题]
[60-120字：本章核心情节、人物状态、情感走向]

第二章：[标题]
[60-120字：...]

（根据故事复杂度决定章数：简单故事2章，中等3章，复杂4章）

要求：
- 去除所有剧本格式标注（场号、镜头说明、角色标签、△等）
- 保留核心人物关系、主要冲突、情感弧线
- 章节间有明确的因果与情感递进"""

CHAPTER_SYSTEM_HEADER = """你是专业的中文短篇小说作者，擅长知乎严选风格。
要求：情感细腻，细节生动，人物立体，语言流畅；
不要保留任何剧本格式痕迹；直接输出散文正文，不加标题或说明。"""

_PREV_CONTEXT_CHARS = 1200  # 携带上章结尾的字数
_SCRIPT_TRUNCATE = 8000     # 发给大纲 LLM 的剧本最大字数

# 目标总字数及单章字数（根据章数动态计算）
_TOTAL_TARGET = 10000

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
    per_chapter = max(2000, _TOTAL_TARGET // total_chapters)
    parts = [
        f"正在写{chapter_title}（共{total_chapters}章），目标约{per_chapter}字。",
        "",
        "【全文大纲参考】",
        outline,
        "",
        "【本章重点】",
        chapter_outline,
    ]
    if prev_prose:
        tail = prev_prose[-_PREV_CONTEXT_CHARS:]
        parts += ["", "【上章结尾，请自然衔接】", tail]
    parts += ["", "直接输出本章散文正文。"]
    return "\n".join(parts)


def _build_style_system(snapshot: list[dict]) -> str:
    parts = [CHAPTER_SYSTEM_HEADER]
    fragments = [s["prompt_fragment"] for s in snapshot if s.get("prompt_fragment")]
    if fragments:
        parts.append("\n\n".join(fragments))
    if snapshot and snapshot[0].get("prose_excerpt"):
        parts.append("# 参考段落\n" + snapshot[0]["prose_excerpt"])
    return "\n\n".join(parts)


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
            "以下是一部短剧剧本，请根据要求生成短篇故事大纲：\n\n"
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
            prose = await provider.complete(user_msg, system=system_prompt)

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
