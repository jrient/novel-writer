"""原作设定 canon 路由：提取触发 + 任务查询 + 实体 CRUD + SSE。
挂在 /api/v1/references/{reference_id}/canon 下。
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db, engine, async_session
from app.core.security import create_sse_ticket, verify_sse_ticket
from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.canon import (
    CanonEntityOut, CanonEntityCreate, CanonEntityUpdate, CanonJobOut,
)
from app.services.canon_pipeline import run_canon_extraction
from app.services.canon_event_bus import canon_event_bus

router = APIRouter(prefix="/api/v1/references/{reference_id}/canon", tags=["canon"])


async def _get_owned_ref(reference_id: int, db: AsyncSession, user: User) -> ReferenceNovel:
    ref = (await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == reference_id,
        (ReferenceNovel.owner_id == user.id) | (ReferenceNovel.owner_id == None),  # noqa: E711
    ))).scalar_one_or_none()
    if ref is None:
        raise HTTPException(status_code=404, detail="原作不存在")
    return ref


@router.post("/extract", status_code=202)
async def start_extraction(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    # 并发守卫：已有进行中的任务则拒绝，避免两次 PERSIST 互相清空
    existing = (await db.execute(select(CanonExtractionJob).where(
        CanonExtractionJob.reference_id == reference_id,
        CanonExtractionJob.status.in_(["pending", "processing"]),
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该原作已有提取任务进行中")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.create_task(run_canon_extraction(reference_id, session_factory))
    return {"message": "提取已启动", "reference_id": reference_id}


@router.get("/job", response_model=CanonJobOut)
async def latest_job(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    job = (await db.execute(select(CanonExtractionJob).where(
        CanonExtractionJob.reference_id == reference_id
    ).order_by(CanonExtractionJob.id.desc()).limit(1))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="尚无提取任务")
    return job


@router.get("/entities", response_model=list[CanonEntityOut])
async def list_entities(
    reference_id: int,
    entity_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    stmt = select(CanonEntity).where(CanonEntity.reference_id == reference_id)
    if entity_type:
        stmt = stmt.where(CanonEntity.entity_type == entity_type)
    rows = (await db.execute(stmt.order_by(CanonEntity.entity_type, CanonEntity.id))).scalars().all()
    return rows


@router.post("/entities", response_model=CanonEntityOut, status_code=201)
async def create_entity(
    reference_id: int,
    payload: CanonEntityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = CanonEntity(
        reference_id=reference_id,
        entity_type=payload.entity_type,
        canonical_name=payload.canonical_name,
        aliases=payload.aliases,
        summary=payload.summary,
        attributes=payload.attributes,
        source_refs=payload.source_refs,
        importance=payload.importance,
        review_status="user_added",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


@router.put("/entities/{entity_id}", response_model=CanonEntityOut)
async def update_entity(
    reference_id: int,
    entity_id: int,
    payload: CanonEntityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = (await db.execute(select(CanonEntity).where(
        CanonEntity.id == entity_id,
        CanonEntity.reference_id == reference_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="设定条目不存在")
    data = payload.model_dump(exclude_unset=True)
    explicit_status = data.pop("review_status", None)
    for k, v in data.items():
        setattr(e, k, v)
    e.review_status = explicit_status or "user_edited"
    await db.commit()
    await db.refresh(e)
    return e


@router.delete("/entities/{entity_id}", status_code=204)
async def delete_entity(
    reference_id: int,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = (await db.execute(select(CanonEntity).where(
        CanonEntity.id == entity_id,
        CanonEntity.reference_id == reference_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="设定条目不存在")
    await db.delete(e)
    await db.commit()


@router.post("/stream/ticket")
async def create_stream_ticket(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """颁发 30s 短票据，供 EventSource 拉 SSE 流。"""
    await _get_owned_ref(reference_id, db, user)
    return {"ticket": create_sse_ticket(user.id, reference_id)}


@router.get("/stream")
async def stream_extraction(reference_id: int, ticket: str = Query(...)):
    """SSE 进度流。需先经 POST /stream/ticket 取得签名票据。"""
    if verify_sse_ticket(ticket, reference_id) is None:
        raise HTTPException(status_code=401, detail="ticket 无效或已过期")
    # 先订阅再读快照：订阅在 gen() 执行前已注册，期间产生的事件会进队列，
    # 不会因「读快照→订阅」之间的间隙而漏事件。
    sub = canon_event_bus.subscribe(reference_id)

    async def gen():
        try:
            yield "data: " + json.dumps({"event": "subscribed", "reference_id": reference_id}) + "\n\n"

            # 快照首帧：补发当前 job 状态，消除「订阅晚于任务启动」的竞态，
            # 同时兼容断线重连/刷新恢复。若任务已结束则立即下发终止事件。
            async with async_session() as s:
                job = (await s.execute(
                    select(CanonExtractionJob)
                    .where(CanonExtractionJob.reference_id == reference_id)
                    .order_by(CanonExtractionJob.id.desc())
                    .limit(1)
                )).scalar_one_or_none()
            if job is not None:
                yield "data: " + json.dumps({
                    "event": "snapshot", "job_id": job.id, "status": job.status,
                    "chunk_total": job.chunk_total, "chunk_done": job.chunk_done,
                    "failed": job.failed_chunks, "entity_count": job.entity_count,
                }, ensure_ascii=False) + "\n\n"
                if job.status == "done":
                    yield "data: " + json.dumps({
                        "event": "done", "job_id": job.id, "entity_count": job.entity_count,
                    }, ensure_ascii=False) + "\n\n"
                    return
                if job.status == "failed":
                    yield "data: " + json.dumps({
                        "event": "failed", "job_id": job.id, "error": job.error or "提取失败",
                    }, ensure_ascii=False) + "\n\n"
                    return

            while True:
                payload = await sub.queue.get()
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                if payload.get("event") in ("done", "failed"):
                    break
        finally:
            canon_event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")
