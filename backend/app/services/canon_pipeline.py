# backend/app/services/canon_pipeline.py
"""原作设定提取 pipeline：CHUNK → ATOMIC_EXTRACT → MERGE_DISAMBIGUATE → PERSIST。

套用 prose_pipeline 范式：asyncio.gather 并行 + return_exceptions 容错 +
canon_event_bus SSE 进度 + CanonExtractionJob 状态机。
"""
import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.chunk import ChunkService
from app.services.ai_service import AIService
from app.services.canon_event_bus import canon_event_bus
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt
from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.reference import ReferenceNovel

logger = logging.getLogger(__name__)

ENTITY_TYPES = ["character", "location", "ability", "faction", "worldrule", "event"]
ATOMIC_CONCURRENCY = 4   # 并行块数上限
MERGE_BATCH = 40         # 单次归并的最大条目数（树状分批）


def _chunk_reference(content: str, chunk_size: int = 4000) -> List[Dict[str, str]]:
    """复用 ChunkService.split_text，给每块加上「片段N」label。"""
    raw_chunks = ChunkService.split_text(content, chunk_size=chunk_size, overlap=200)
    return [
        {"label": f"片段{i + 1}", "text": text}
        for i, text in enumerate(raw_chunks)
    ]


def _safe_json_array(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中稳健提取 JSON 数组（容错 ```json 围栏、前后噪声）。
    仿 wizard._extract_json_array。失败返回 []。
    """
    if not text:
        return []
    # 去掉 markdown 围栏
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 找第一个 [ 到匹配的 ]
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
    return []


async def _atomic_extract_chunk(chunk: Dict[str, str], model: Optional[str]) -> List[Dict[str, Any]]:
    """单块原子提取：调 LLM → 解析 → 把 source.quote 规整为 source_refs（附 chapter=label）。
    任何异常/坏 JSON 返回 []（由上层计 failed）。
    """
    prompt = build_atomic_prompt(chunk_text=chunk["text"], chunk_label=chunk["label"])
    raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
    entities = _safe_json_array(raw)

    normalized: List[Dict[str, Any]] = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("canonical_name"):
            continue
        src = e.pop("source", None) or {}
        quote = src.get("quote") if isinstance(src, dict) else None
        e["source_refs"] = [{"chapter": chunk["label"], "quote": quote}] if quote else []
        e.setdefault("aliases", [])
        e.setdefault("attributes", {})
        e.setdefault("importance", "major")
        normalized.append(e)
    return normalized


async def _merge_entities_of_type(
    entity_type: str, raw_entities: List[Dict[str, Any]], model: Optional[str]
) -> List[Dict[str, Any]]:
    """对同类型条目做 LLM 归并消歧。条目过多时树状分批（每批 MERGE_BATCH）。"""
    if not raw_entities:
        return []
    if len(raw_entities) <= MERGE_BATCH:
        prompt = build_merge_prompt(entity_type, raw_entities)
        raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
        merged = _safe_json_array(raw)
        # 回退：归并失败则原样返回（不丢数据）
        return merged if merged else raw_entities

    # 分批归并后递归再归并
    batch_results: List[Dict[str, Any]] = []
    for i in range(0, len(raw_entities), MERGE_BATCH):
        batch = raw_entities[i:i + MERGE_BATCH]
        prompt = build_merge_prompt(entity_type, batch)
        raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
        batch_results.extend(_safe_json_array(raw) or batch)
    # 仅在严格递减时递归再归并，避免坏 JSON 反复回退导致死循环
    if len(batch_results) < len(raw_entities) and len(batch_results) > MERGE_BATCH:
        return await _merge_entities_of_type(entity_type, batch_results, model)
    return batch_results


async def run_canon_extraction(
    reference_id: int,
    session_factory: async_sessionmaker,
    model: Optional[str] = None,
) -> int:
    """编排：建 job → CHUNK → ATOMIC(并行) → MERGE(按类型) → PERSIST。返回 job_id。
    幂等：重跑前清空该 reference 既有 ai_extracted 实体（保留 user_* 人工条目）。
    """
    # 1) 建 job + 取原作正文
    async with session_factory() as s:
        ref = (await s.execute(select(ReferenceNovel).where(
            ReferenceNovel.id == reference_id))).scalar_one_or_none()
        if ref is None:
            raise ValueError(f"reference {reference_id} 不存在")
        content = ref.content or ""
        job = CanonExtractionJob(reference_id=reference_id, model=model, status="processing")
        s.add(job)
        await s.commit()
        await s.refresh(job)
        job_id = job.id

    try:
        # 2) CHUNK
        chunks = _chunk_reference(content)
        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.chunk_total = len(chunks)
            await s.commit()
        await canon_event_bus.publish(reference_id,
            {"event": "chunked", "job_id": job_id, "chunk_total": len(chunks)})

        # 3) ATOMIC（并行限流，实时进度）
        sem = asyncio.Semaphore(ATOMIC_CONCURRENCY)
        done = 0
        failed = 0
        all_atomic: List[Dict[str, Any]] = []

        async def _worker(ch):
            nonlocal done, failed
            async with sem:
                try:
                    ents = await _atomic_extract_chunk(ch, model)
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    logger.warning("canon atomic chunk failed: %s", e)
                    ents = []
                else:
                    all_atomic.extend(ents)
                done += 1
                await canon_event_bus.publish(reference_id, {
                    "event": "progress", "job_id": job_id,
                    "chunk_done": done, "failed": failed,
                })
                return ents

        await asyncio.gather(*[_worker(c) for c in chunks])

        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.chunk_done = done
            j.failed_chunks = failed
            await s.commit()

        # 4) MERGE（按类型）
        by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in ENTITY_TYPES}
        for e in all_atomic:
            t = e.get("entity_type")
            if t in by_type:
                by_type[t].append(e)
        merged_all: List[Dict[str, Any]] = []
        for t in ENTITY_TYPES:
            merged_all.extend(await _merge_entities_of_type(t, by_type[t], model))
        await canon_event_bus.publish(reference_id,
            {"event": "merged", "job_id": job_id, "entity_count": len(merged_all)})

        # 5) PERSIST（先清旧 ai_extracted，保留人工条目）
        async with session_factory() as s:
            await s.execute(delete(CanonEntity).where(
                CanonEntity.reference_id == reference_id,
                CanonEntity.review_status == "ai_extracted"))
            for e in merged_all:
                s.add(CanonEntity(
                    reference_id=reference_id,
                    entity_type=e.get("entity_type", "character"),
                    canonical_name=e.get("canonical_name", "")[:200] or "未命名",
                    aliases=e.get("aliases", []),
                    summary=e.get("summary"),
                    attributes=e.get("attributes", {}),
                    source_refs=e.get("source_refs", []),
                    importance=e.get("importance", "major"),
                    confidence=float(e.get("confidence", 1.0)),
                    review_status="ai_extracted",
                ))
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.entity_count = len(merged_all)
            j.status = "done"
            await s.commit()

        await canon_event_bus.publish(reference_id,
            {"event": "done", "job_id": job_id, "entity_count": len(merged_all)})
        return job_id

    except Exception as exc:  # noqa: BLE001
        logger.exception("canon extraction failed")
        try:
            async with session_factory() as s:
                j = (await s.execute(select(CanonExtractionJob).where(
                    CanonExtractionJob.id == job_id))).scalar_one_or_none()
                if j is not None:
                    j.status = "failed"
                    j.error = str(exc)[:2000]
                    await s.commit()
        except Exception:  # noqa: BLE001
            logger.exception("canon extraction: failed to persist failed-status")
        await canon_event_bus.publish(reference_id, {"event": "failed", "job_id": job_id, "error": str(exc)})
        return job_id
