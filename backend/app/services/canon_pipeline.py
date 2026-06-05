# backend/app/services/canon_pipeline.py
"""原作设定提取 pipeline：CHUNK → ATOMIC_EXTRACT → MERGE_DISAMBIGUATE → PERSIST。

套用 prose_pipeline 范式：asyncio.gather 并行 + return_exceptions 容错 +
canon_event_bus SSE 进度 + CanonExtractionJob 状态机。
"""
import asyncio
import json
import logging
import os
import re
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.chunk import ChunkService
from app.services.ai_service import AIService
from app.services.canon_event_bus import canon_event_bus
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt, build_relation_prompt
from app.models.canon import CanonExtractionJob, CanonRelation
from app.models.canon import CanonEntity as _CanonEntity
from app.models.reference import ReferenceNovel

logger = logging.getLogger(__name__)

ENTITY_TYPES = ["character", "location", "ability", "faction", "worldrule",
                "event", "item", "race", "realm", "concept"]
ATOMIC_CONCURRENCY = 4   # 并行块数上限
MERGE_BATCH = 40         # 单次归并的最大条目数（树状分批）


def _load_reference_text(ref) -> str:
    """取原作正文：DB content 优先，为空时回退读 file_path（>10万字上传只存盘不入库）。"""
    content = ref.content or ""
    if not content and ref.file_path and os.path.exists(ref.file_path):
        try:
            with open(ref.file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError as e:
            logger.warning("canon 读取 file_path 失败: %s", e)
    return content


def _chunk_reference(content: str, chunk_size: int = 4000) -> List[Dict[str, str]]:
    """复用 ChunkService.split_text，给每块加上「片段N」label。"""
    raw_chunks = ChunkService.split_text(content, chunk_size=chunk_size, overlap=200)
    return [
        {"label": f"片段{i + 1}", "text": text}
        for i, text in enumerate(raw_chunks)
    ]


def _safe_json_array(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中稳健提取 JSON 数组（容错 markdown 围栏、截断、嵌套括号）。
    当 max_tokens 截断导致缺少闭合 ] 时，自动恢复已生成的完整对象。
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
                    break  # 匹配到 ] 但解析失败，进入截断恢复

    # 截断恢复：逐个提取完整 {...} 对象，丢弃不完整的尾部
    array_body = text[start + 1:]
    objs: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(array_body):
        brace = array_body.find("{", idx)
        if brace == -1:
            break
        d = 0
        for j in range(brace, len(array_body)):
            if array_body[j] == "{":
                d += 1
            elif array_body[j] == "}":
                d -= 1
                if d == 0:
                    try:
                        obj = json.loads(array_body[brace:j + 1])
                        if isinstance(obj, dict):
                            objs.append(obj)
                    except json.JSONDecodeError:
                        pass
                    idx = j + 1
                    break
        else:
            break  # 未找到闭合 }

    return objs

def _build_name_index(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    """canonical_name 与 aliases → entity_id。后者不覆盖前者已占用的名字。"""
    idx: Dict[str, int] = {}
    for e in entities:
        eid = e.get("id")
        name = (e.get("canonical_name") or "").strip()
        if name and name not in idx:
            idx[name] = eid
        for a in e.get("aliases") or []:
            a = (a or "").strip()
            if a and a not in idx:
                idx[a] = eid
    return idx


def _resolve_relations(
    raw_rels: List[Dict[str, Any]], name_index: Dict[str, int], chunk_label: str
) -> List[Dict[str, Any]]:
    """把 LLM 抽出的 {source,target,...} 回链到 entity_id，丢弃越界/自指，并按
    (src,tgt,type) 去重合并 source_refs。"""
    bucket: Dict[tuple, Dict[str, Any]] = {}
    for r in raw_rels:
        if not isinstance(r, dict):
            continue
        sid = name_index.get((r.get("source") or "").strip())
        tid = name_index.get((r.get("target") or "").strip())
        if sid is None or tid is None or sid == tid:
            continue
        rtype = (r.get("relation_type") or "custom").strip() or "custom"
        key = (sid, tid, rtype)
        quote = (r.get("quote") or "").strip()
        ref = {"chapter": chunk_label, "quote": quote} if quote else None
        if key in bucket:
            if ref:
                bucket[key]["source_refs"].append(ref)
        else:
            bucket[key] = {
                "source_entity_id": sid,
                "target_entity_id": tid,
                "relation_type": rtype,
                "label": (r.get("label") or "").strip() or None,
                "summary": None,
                "source_refs": [ref] if ref else [],
            }
    return list(bucket.values())

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

async def _get_processed_chunks(reference_id: int, session_factory) -> set:
    async with session_factory() as s:
        job = (await s.execute(
            select(CanonExtractionJob)
            .where(CanonExtractionJob.reference_id == reference_id)
            .order_by(CanonExtractionJob.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        if job and job.status == "processing" and job.processed_chunks:
            return set(json.loads(job.processed_chunks))
    return set()


def _entity_to_dict(e) -> dict:
    return {
        "canonical_name": e.canonical_name,
        "entity_type": e.entity_type,
        "aliases": e.aliases or [],
        "summary": e.summary or "",
        "attributes": e.attributes or {},
        "source_refs": e.source_refs or [],
        "importance": e.importance,
        "confidence": e.confidence,
    }



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
        content = _load_reference_text(ref)
        job = CanonExtractionJob(reference_id=reference_id, model=model, status="processing")
        s.add(job)
        await s.commit()
        await s.refresh(job)
        job_id = job.id

    try:
                # 2) CHUNK
        all_chunks = _chunk_reference(content)
        processed_set = await _get_processed_chunks(reference_id, session_factory)
        if processed_set:
            chunks = [c for c in all_chunks if c["label"] not in processed_set]
            logger.info("canon resume: %d/%d chunks already done", len(all_chunks) - len(chunks), len(all_chunks))
        else:
            chunks = all_chunks
        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.chunk_total = len(all_chunks)
            await s.commit()
            logger.info("canon: %d/%d chunks 待提取, 开始原子抽取", len(chunks), len(all_chunks))
            await canon_event_bus.publish(reference_id,
                {"event": "chunked", "job_id": job_id, "chunk_total": len(all_chunks)})

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
                # 每块提取结果立即落库（支持断点续跑）
                async with session_factory() as s:
                    for e in ents:
                        s.add(_CanonEntity(
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
                    job_row = (await s.execute(select(CanonExtractionJob).where(
                        CanonExtractionJob.id == job_id))).scalar_one()
                    proc = json.loads(job_row.processed_chunks) if job_row.processed_chunks else []
                    proc.append(ch["label"])
                    job_row.processed_chunks = json.dumps(proc)
                    job_row.chunk_done = done + 1
                    await s.commit()
                done += 1
                await canon_event_bus.publish(reference_id, {
                    "event": "progress", "job_id": job_id,
                    "chunk_done": done, "failed": failed,
                })
                return ents

        await asyncio.gather(*[_worker(c) for c in chunks])

        # 4）从 DB 读全部已保存实体 → 按类型分组 → 合并消歧
        async with session_factory() as s:
            rows = (await s.execute(
                select(_CanonEntity).where(
                    _CanonEntity.reference_id == reference_id,
                    _CanonEntity.review_status == "ai_extracted")
            )).scalars().all()
        by_type: Dict[str, List[Dict]] = {t: [] for t in ENTITY_TYPES}
        for row in rows:
            d = _entity_to_dict(row)
            if d["entity_type"] in by_type:
                by_type[d["entity_type"]].append(d)
        merged_all: List[Dict] = []
        for t in ENTITY_TYPES:
            merged_all.extend(await _merge_entities_of_type(t, by_type[t], model))
        await canon_event_bus.publish(reference_id,
            {"event": "merged", "job_id": job_id, "entity_count": len(merged_all)})

        # 5）清旧写新（单事务，失败则旧数据还在）
        async with session_factory() as s:
            if merged_all:
                await s.execute(delete(_CanonEntity).where(
                    _CanonEntity.reference_id == reference_id,
                    _CanonEntity.review_status == "ai_extracted"))
                for e in merged_all:
                    s.add(_CanonEntity(
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
                new_count = len(merged_all)
            else:
                new_count = (await s.execute(
                    select(func.count()).select_from(_CanonEntity).where(
                        _CanonEntity.reference_id == reference_id,
                        _CanonEntity.review_status == "ai_extracted"))
                ).scalar() or 0
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.entity_count = new_count
            j.processed_chunks = None  # 合并完成，清跟踪
            j.status = "done"
            await s.commit()

        # 6) RELATION_EXTRACT（实体已落库，按已存实体抽关系）
        relation_count = 0
        try:
            relation_count = await extract_relations_for_reference(
                reference_id, session_factory, model)
        except Exception:  # noqa: BLE001
            logger.exception("canon relation extraction failed (non-fatal)")


        await canon_event_bus.publish(reference_id,
            {"event": "done", "job_id": job_id, "entity_count": new_count,
             "relation_count": relation_count})
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

async def _relation_extract_chunk(
    chunk: Dict[str, str], entities_brief: List[Dict[str, Any]],
    name_index: Dict[str, int], model: Optional[str],
) -> List[Dict[str, Any]]:
    prompt = build_relation_prompt(
        entities=entities_brief, chunk_text=chunk["text"], chunk_label=chunk["label"])
    raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
    return _resolve_relations(_safe_json_array(raw), name_index, chunk["label"])


async def extract_relations_for_reference(
    reference_id: int, session_factory: async_sessionmaker, model: Optional[str] = None,
) -> int:
    """对已存在实体的 reference 抽关系并落库。返回关系数。
    幂等：清空既有 ai_extracted 关系，保留 user_*。会发 relation_* SSE 事件。"""
    # 取实体 + 原文
    async with session_factory() as s:
        ref = (await s.execute(select(ReferenceNovel).where(
            ReferenceNovel.id == reference_id))).scalar_one_or_none()
        if ref is None:
            raise ValueError(f"reference {reference_id} 不存在")
        content = _load_reference_text(ref)
        ents = (await s.execute(select(CanonEntity).where(
            CanonEntity.reference_id == reference_id))).scalars().all()
        entities_brief = [
            {"id": e.id, "canonical_name": e.canonical_name,
             "entity_type": e.entity_type, "aliases": e.aliases or []}
            for e in ents
        ]
    if not entities_brief:
        return 0

    name_index = _build_name_index(entities_brief)
    chunks = _chunk_reference(content)
    await canon_event_bus.publish(reference_id, {
        "event": "relation_chunked", "relation_total": len(chunks)})

    sem = asyncio.Semaphore(ATOMIC_CONCURRENCY)
    done = 0
    all_rels: List[Dict[str, Any]] = []

    async def _worker(ch):
        nonlocal done
        async with sem:
            try:
                rels = await _relation_extract_chunk(ch, entities_brief, name_index, model)
            except Exception as e:  # noqa: BLE001
                logger.warning("canon relation chunk failed: %s", e)
                rels = []
            all_rels.extend(rels)
            done += 1
            await canon_event_bus.publish(reference_id, {
                "event": "relation_progress", "relation_done": done,
                "relation_total": len(chunks)})

    await asyncio.gather(*[_worker(c) for c in chunks])

    # 跨块再去重合并（同 src,tgt,type）
    merged: Dict[tuple, Dict[str, Any]] = {}
    for r in all_rels:
        key = (r["source_entity_id"], r["target_entity_id"], r["relation_type"])
        if key in merged:
            merged[key]["source_refs"].extend(r["source_refs"])
            if not merged[key]["label"] and r["label"]:
                merged[key]["label"] = r["label"]
        else:
            merged[key] = r
    final = list(merged.values())

    async with session_factory() as s:
        if final:
            await s.execute(delete(CanonRelation).where(
                CanonRelation.reference_id == reference_id,
                CanonRelation.review_status == "ai_extracted"))
            for r in final:
                s.add(CanonRelation(
                    reference_id=reference_id,
                    source_entity_id=r["source_entity_id"],
                    target_entity_id=r["target_entity_id"],
                    relation_type=r["relation_type"][:40],
                    label=(r["label"] or None),
                    summary=r.get("summary"),
                    source_refs=r["source_refs"],
                    review_status="ai_extracted",
                ))
            await s.commit()
    return len(final)
