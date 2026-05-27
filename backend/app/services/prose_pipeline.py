# backend/app/services/prose_pipeline.py
"""散文生成三步 pipeline：FETCH_SCRIPT → SEARCH_STYLE → REWRITE。"""
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

PROSE_SYSTEM_HEADER = """你是一位专业的中文短篇小说作者，擅长知乎严选风格。
你的任务是将输入的剧本场景改写为连贯流畅的散文小说段落。
要求：保留原场景的核心情节与情感走向；风格完全遵照下方风格指南；
不要保留剧本格式（场景头、对白标记等）；直接输出散文正文，不加任何说明。"""

PROSE_REWRITE_CONCURRENCY = 3


_HEADING_RE = re.compile(
    r"^(?:"
    r"第[零一二三四五六七八九十百千0-9]+[场幕章节回]"  # 第X场/幕/章
    r"|[【\[【].*?[】\]】]"                             # 【标题】
    r"|场次?\s*[零一二三四五六七八九十0-9]+"            # 场次X
    r"|[-=*]{3,}"                                       # 分隔线
    r")"
)

_MIN_SCENE_CHARS = 300   # 无标题时每个场景的最少字数
_TARGET_MAX_SCENES = 20  # 无标题时的目标最大场景数


def _split_content_to_scenes(text: str) -> list[tuple[str, str]]:
    """将纯文本拆分为 (title, content) 场景列表。

    策略 1（优先）：检测场景标题行（第X场/幕/章、【...】、分隔线），
                    有标题则按标题分组，每个标题块 = 一个场景。
    策略 2（回退）：无标题时把段落按字数累积，每攒满 _MIN_SCENE_CHARS
                    个字才切一刀，避免对白行被切成无数微场景。
                    超过 _TARGET_MAX_SCENES 个场景时再次合并。
    """
    lines = text.splitlines()
    heading_indices = [
        i for i, line in enumerate(lines) if _HEADING_RE.match(line.strip())
    ]

    if heading_indices:
        scenes: list[tuple[str, str]] = []
        boundaries = heading_indices + [len(lines)]
        for start, end in zip(boundaries, boundaries[1:]):
            title = lines[start].strip()
            body = "\n".join(lines[start + 1 : end]).strip()
            content = f"{title}\n{body}".strip() if body else title
            if content:
                scenes.append((title[:50], content))
        return scenes

    # 无标题：按字数累积段落
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    scenes = []
    bucket: list[str] = []
    bucket_chars = 0

    for para in paragraphs:
        bucket.append(para)
        bucket_chars += len(para)
        if bucket_chars >= _MIN_SCENE_CHARS:
            content = "\n\n".join(bucket)
            title = bucket[0].split("\n", 1)[0][:50] or f"场景{len(scenes) + 1}"
            scenes.append((title, content))
            bucket = []
            bucket_chars = 0

    # 剩余不足一场的内容合并到最后一场，避免末尾碎片
    if bucket:
        content = "\n\n".join(bucket)
        if scenes:
            last_title, last_content = scenes[-1]
            scenes[-1] = (last_title, last_content + "\n\n" + content)
        else:
            title = bucket[0].split("\n", 1)[0][:50] or "场景1"
            scenes.append((title, content))

    # 场景数超出上限时再次合并
    if len(scenes) > _TARGET_MAX_SCENES:
        chunk = max(2, (len(scenes) + _TARGET_MAX_SCENES - 1) // _TARGET_MAX_SCENES)
        merged: list[tuple[str, str]] = []
        for i in range(0, len(scenes), chunk):
            group = scenes[i : i + chunk]
            title = group[0][0]
            content = "\n\n".join(c for _, c in group)
            merged.append((title, content))
        scenes = merged

    return scenes


class _LLMProvider:
    async def complete(self, prompt: str, **kwargs) -> str: ...


def _get_default_provider() -> _LLMProvider:
    from app.services.adaptation_llm_service import get_default_service
    return get_default_service().provider


async def _search_style_samples(
    session: AsyncSession, query_vec: list, top_k: int, genre: Optional[str]
) -> list[dict]:
    """薄包装，供测试 patch。"""
    return await search_style_samples(session, query_vec, top_k=top_k, genre=genre)


def _build_system_prompt(snapshot: list[dict]) -> str:
    parts = [PROSE_SYSTEM_HEADER]
    fragments = [s["prompt_fragment"] for s in snapshot if s.get("prompt_fragment")]
    if fragments:
        parts.append("\n\n".join(fragments))
    if snapshot and snapshot[0].get("prose_excerpt"):
        parts.append("# 参考段落\n" + snapshot[0]["prose_excerpt"])
    return "\n\n".join(parts)


async def run(
    session_factory: async_sessionmaker,
    project_id: int,
    provider: Optional[_LLMProvider] = None,
) -> None:
    """三步 pipeline 全流程。provider=None 时使用生产 LLM。"""
    if provider is None:
        provider = _get_default_provider()

    # ── Step 1: FETCH_SCRIPT ────────────────────────────────────────────────
    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one_or_none()
        if not project:
            logger.error("prose project %s not found", project_id)
            return

        if project.script_project_id is not None:
            # 从数据库剧本节点获取场景
            nodes = (await session.execute(
                select(ScriptNode)
                .where(ScriptNode.project_id == project.script_project_id)
                .order_by(ScriptNode.sort_order)
            )).scalars().all()
            leaf_nodes = [n for n in nodes if n.content and n.content.strip()]
            scenes_data = [
                (node.title or f"场{idx + 1}", node.content)
                for idx, node in enumerate(leaf_nodes)
            ]
        else:
            # 从上传文件内容拆分场景（按双换行分段）
            raw = project.script_content or ""
            scenes_data = _split_content_to_scenes(raw)

        if not scenes_data:
            project.status = "failed"
            project.style_snapshot = "[]"
            await session.commit()
            await prose_event_bus.publish(project_id, {"event": "project_failed", "status": "failed"})
            return

        project.total_scenes = len(scenes_data)
        project.status = "generating"

        for idx, (scene_title, scene_text) in enumerate(scenes_data):
            session.add(ProseScene(
                project_id=project_id,
                scene_index=idx,
                scene_title=scene_title,
                original_scene_text=scene_text,
            ))
        await session.commit()
        premise = project.premise
        genre = project.genre

    # ── Step 2: SEARCH_STYLE ────────────────────────────────────────────────
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

    system_prompt = _build_system_prompt(snapshot)

    # ── Step 3: REWRITE (concurrent) ─────────────────────────────────────────
    async with session_factory() as session:
        scenes = (await session.execute(
            select(ProseScene).where(ProseScene.project_id == project_id)
            .order_by(ProseScene.scene_index)
        )).scalars().all()
        scene_data = [
            (s.id, s.scene_index, s.scene_title, s.original_scene_text)
            for s in scenes
        ]

    sem = asyncio.Semaphore(PROSE_REWRITE_CONCURRENCY)

    async def _rewrite_one(scene_id: int, scene_index: int, title: str, original: str):
        async with sem:
            async with session_factory() as session:
                sc = (await session.execute(
                    select(ProseScene).where(ProseScene.id == scene_id)
                )).scalar_one()
                sc.status = "running"
                await session.commit()

            try:
                user_msg = f"将以下剧本场景改写为知乎严选风格短篇散文：\n{original}"
                prose = await provider.complete(user_msg, system=system_prompt)
                async with session_factory() as session:
                    sc = (await session.execute(
                        select(ProseScene).where(ProseScene.id == scene_id)
                    )).scalar_one()
                    sc.prose_text = prose
                    sc.status = "done"
                    await session.commit()
                await prose_event_bus.publish(project_id, {
                    "event": "scene_done",
                    "scene_index": scene_index,
                    "scene_title": title,
                    "status": "done",
                    "prose_text": prose,
                })
                return True
            except Exception as e:
                logger.exception("prose scene %s rewrite failed", scene_id)
                async with session_factory() as session:
                    sc = (await session.execute(
                        select(ProseScene).where(ProseScene.id == scene_id)
                    )).scalar_one()
                    sc.status = "failed"
                    sc.error = str(e)[:1000]
                    await session.commit()
                await prose_event_bus.publish(project_id, {
                    "event": "scene_done",
                    "scene_index": scene_index,
                    "scene_title": title,
                    "status": "failed",
                })
                return False

    results = await asyncio.gather(*[
        _rewrite_one(sid, sidx, stitle, sorig)
        for (sid, sidx, stitle, sorig) in scene_data
    ], return_exceptions=True)

    done = sum(1 for r in results if r is True)
    failed = sum(1 for r in results if r is not True)

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
