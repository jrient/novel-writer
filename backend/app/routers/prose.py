"""散文生成模块路由：CRUD + SSE 5 个端点"""
import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import async_session, get_db
from app.core.security import create_sse_ticket, verify_sse_ticket
from app.models.prose_project import ProseProject, ProseScene
from app.models.script_project import ScriptProject
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.prose import ProseProjectCreate, ProseProjectDetail, ProseProjectOut
from app.services import prose_pipeline
from app.services.prose_event_bus import prose_event_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/prose", tags=["prose"])


async def _get_owned_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProseProject:
    p = (await db.execute(
        select(ProseProject).where(
            ProseProject.id == project_id,
            ProseProject.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "散文项目不存在或无权访问")
    return p


@router.post("", response_model=ProseProjectOut)
async def create_prose_project(
    payload: ProseProjectCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sp = (await db.execute(
        select(ScriptProject).where(
            ScriptProject.id == payload.script_project_id,
            ScriptProject.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not sp:
        raise HTTPException(400, "剧本不存在或无权访问")

    title = payload.title or f"《{sp.title}》散文改写"
    genre = payload.genre or getattr(sp, "genre", None)

    project = ProseProject(
        user_id=current_user.id,
        title=title,
        script_project_id=sp.id,
        script_project_title=sp.title,
        premise=payload.premise,
        genre=genre,
        status="pending",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    background.add_task(prose_pipeline.run, async_session, project.id)
    return project


@router.get("", response_model=list[ProseProjectOut])
async def list_prose_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(ProseProject)
        .where(ProseProject.user_id == current_user.id)
        .order_by(ProseProject.created_at.desc())
    )).scalars().all()
    return rows


@router.get("/{project_id}", response_model=ProseProjectDetail)
async def get_prose_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = (await db.execute(
        select(ProseProject)
        .where(ProseProject.id == project_id, ProseProject.user_id == current_user.id)
        .options(selectinload(ProseProject.scenes))
    )).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "散文项目不存在或无权访问")
    return project


@router.delete("/{project_id}", status_code=204)
async def delete_prose_project(
    project: ProseProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await prose_event_bus.publish(project.id, {"event": "project_failed", "status": "deleted"})
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@router.post("/{project_id}/stream/ticket")
async def create_stream_ticket(
    project: ProseProject = Depends(_get_owned_project),
    current_user: User = Depends(get_current_user),
):
    """颁发 30s 短票据，供 EventSource 拉 SSE 流"""
    return {"ticket": create_sse_ticket(current_user.id, project.id)}


@router.get("/{project_id}/stream")
async def stream_prose_project(project_id: int, ticket: str = Query(...)):
    if verify_sse_ticket(ticket, project_id) is None:
        raise HTTPException(401, "ticket 无效或已过期")
    sub = prose_event_bus.subscribe(project_id)

    async def gen():
        try:
            yield "data: " + json.dumps({"event": "subscribed", "project_id": project_id}) + "\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield "data: " + json.dumps(payload, default=str) + "\n\n"
                    if payload.get("event") in ("project_done", "project_failed"):
                        return
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            prose_event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")
