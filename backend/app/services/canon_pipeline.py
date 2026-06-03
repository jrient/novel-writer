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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
