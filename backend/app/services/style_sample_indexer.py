"""StyleSample 索引服务：chunk 切分 + embedding 写入

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第六节。
"""
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.services.embedding import embedding_service
from app.models.style_sample import StyleSample, StyleSampleChunk

CHUNK_MIN = 100
CHUNK_MAX = 500
SENTENCE_END_MARKS = "。！？…"


def _hard_split_long_paragraph(text: str) -> List[str]:
    """超 CHUNK_MAX 的段落硬切：先找 CHUNK_MAX 内最后的句末符，没有就切到 CHUNK_MAX。"""
    out: List[str] = []
    remaining = text
    while len(remaining) > CHUNK_MAX:
        window = remaining[:CHUNK_MAX]
        cut = -1
        for i in range(CHUNK_MAX - 1, CHUNK_MAX - 101, -1):
            if i < 0:
                break
            if window[i] in SENTENCE_END_MARKS:
                cut = i + 1
                break
        if cut == -1:
            cut = CHUNK_MAX
        out.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        out.append(remaining)
    return out


def split_chunks(content: str) -> List[str]:
    """按段落切分，少 100 字段并入下一段，超 500 字按句末符硬切。

    规则详见 spec 第六节。
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    refined: List[str] = []
    for p in paragraphs:
        refined.extend(s.strip() for s in p.split("\n") if s.strip())

    if not refined:
        return []

    merged: List[str] = []
    buffer = ""
    for p in refined:
        if buffer:
            buffer = buffer + p
            if len(buffer) >= CHUNK_MIN:
                merged.append(buffer)
                buffer = ""
        elif len(p) < CHUNK_MIN:
            buffer = p
        else:
            merged.append(p)
    if buffer:
        merged.append(buffer)

    out: List[str] = []
    for p in merged:
        if len(p) > CHUNK_MAX:
            out.extend(_hard_split_long_paragraph(p))
        else:
            out.append(p)
    return out


EMBED_BATCH_SIZE = 50


async def index_sample(session: AsyncSession, sample_id: int) -> int:
    """对指定 sample 切 chunk + 生 embedding + 写表。返回写入 chunk 数。

    失败处理：embedding 抛出 → 上抛给调用方；本函数保证不留半成品 chunk
    （生 embedding 失败前不写任何 chunk 行）。
    """
    sample = (await session.execute(
        select(StyleSample).where(StyleSample.id == sample_id)
    )).scalar_one()

    await session.execute(
        delete(StyleSampleChunk).where(StyleSampleChunk.sample_id == sample_id)
    )

    chunks = split_chunks(sample.content)
    if not chunks:
        await session.commit()
        return 0

    embeddings: List[list] = []
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        vecs = await embedding_service.generate_embeddings(batch)
        embeddings.extend(vecs)

    for idx, (text, vec) in enumerate(zip(chunks, embeddings)):
        session.add(StyleSampleChunk(
            sample_id=sample_id,
            chunk_index=idx,
            content=text,
            char_count=len(text),
            embedding=vec,
        ))
    await session.commit()
    return len(chunks)


async def _delete_chunks_only(session: AsyncSession, sample_id: int) -> None:
    """供 pipeline 在抽取失败回退时清空 chunks（不动 sample 行）"""
    await session.execute(
        delete(StyleSampleChunk).where(StyleSampleChunk.sample_id == sample_id)
    )
    await session.commit()


async def search_style_samples(
    session: AsyncSession,
    query_vec: list,
    top_k: int = 3,
    genre: Optional[str] = None,
) -> list[dict]:
    """内部检索：按 query_vec 找 top_k 样本的风格快照。
    供 prose_pipeline 直接调用（不走 HTTP）。

    返回：[{"sample_id": int, "title": str, "prompt_fragment": str, "prose_excerpt": str}]
    样本库为空或无向量时返回 []。
    """
    from sqlalchemy import text as _sql_text

    def _is_postgres() -> bool:
        from app.core.config import settings
        return not settings.DATABASE_URL.startswith("sqlite")

    if _is_postgres():
        sql = """
            SELECT c.sample_id,
                   1.0 - (c.embedding <=> CAST(:qv AS vector)) AS similarity
            FROM style_sample_chunks c
            JOIN style_samples s ON s.id = c.sample_id
            WHERE (CAST(:genre AS text) IS NULL OR s.genre = CAST(:genre AS text))
              AND s.index_status = 'ready'
            ORDER BY c.embedding <=> CAST(:qv AS vector)
            LIMIT :lim
        """
        rows = (await session.execute(_sql_text(sql), {
            "qv": str(query_vec),
            "genre": genre,
            "lim": top_k * 5,
        })).all()
        sample_ids_ordered = list(dict.fromkeys(r.sample_id for r in rows))[:top_k]
    else:
        stmt = (
            select(StyleSampleChunk.sample_id)
            .join(StyleSample, StyleSample.id == StyleSampleChunk.sample_id)
            .where(StyleSample.index_status == "ready")
        )
        if genre:
            stmt = stmt.where(StyleSample.genre == genre)
        rows = (await session.execute(stmt)).all()
        sample_ids_ordered = list(dict.fromkeys(r.sample_id for r in rows))[:top_k]

    if not sample_ids_ordered:
        return []

    samples = (await session.execute(
        select(StyleSample).where(StyleSample.id.in_(sample_ids_ordered))
    )).scalars().all()
    by_id = {s.id: s for s in samples}

    result = []
    for sid in sample_ids_ordered:
        s = by_id.get(sid)
        if not s or not s.style_guide:
            continue
        import json as _json
        try:
            guide = _json.loads(s.style_guide)
        except (ValueError, TypeError):
            continue
        result.append({
            "sample_id": s.id,
            "title": s.title,
            "prompt_fragment": guide.get("prompt_fragment", ""),
            "prose_excerpt": guide.get("prose_excerpt", ""),
        })
    return result
