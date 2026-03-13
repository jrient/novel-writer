"""
事件与剧情线路由
处理 StoryEvent 和 Plotline 的 CRUD 操作
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user
from app.models.event import StoryEvent, Plotline
from app.schemas.event import (
    PlotlineCreate, PlotlineUpdate, PlotlineResponse,
    StoryEventCreate, StoryEventUpdate, StoryEventResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/events",
    tags=["events"],
)


# ============ Plotline CRUD ============

@router.get("/plotlines/", response_model=List[PlotlineResponse])
async def list_plotlines(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """列出项目所有剧情线"""
    stmt = (
        select(Plotline)
        .where(Plotline.project_id == project_id)
        .order_by(Plotline.sort_order)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/plotlines/", response_model=PlotlineResponse, status_code=201)
async def create_plotline(
    project_id: int,
    payload: PlotlineCreate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """创建剧情线"""
    try:
        plotline = Plotline(
            **payload.model_dump(),
            project_id=project_id,
        )
        db.add(plotline)
        await db.commit()
        await db.refresh(plotline)
        return plotline
    except Exception as e:
        await db.rollback()
        logger.error(f"创建剧情线失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建剧情线失败")


@router.put("/plotlines/{plotline_id}", response_model=PlotlineResponse)
async def update_plotline(
    project_id: int,
    plotline_id: int,
    payload: PlotlineUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """更新剧情线"""
    try:
        result = await db.execute(
            select(Plotline).where(Plotline.id == plotline_id, Plotline.project_id == project_id)
        )
        plotline = result.scalar_one_or_none()
        if not plotline:
            raise HTTPException(status_code=404, detail="剧情线不存在")

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(plotline, key, value)

        await db.commit()
        await db.refresh(plotline)
        return plotline
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新剧情线失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新剧情线失败")


@router.delete("/plotlines/{plotline_id}", status_code=204)
async def delete_plotline(
    project_id: int,
    plotline_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """删除剧情线"""
    try:
        result = await db.execute(
            select(Plotline).where(Plotline.id == plotline_id, Plotline.project_id == project_id)
        )
        plotline = result.scalar_one_or_none()
        if not plotline:
            raise HTTPException(status_code=404, detail="剧情线不存在")
        await db.delete(plotline)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除剧情线失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除剧情线失败")


# ============ StoryEvent CRUD ============

@router.get("/", response_model=List[StoryEventResponse])
async def list_events(
    project_id: int,
    plotline_id: Optional[int] = Query(None, description="按剧情线筛选"),
    event_type: Optional[str] = Query(None, description="按事件类型筛选"),
    anchor_type: Optional[str] = Query(None, description="按锚定类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """列出项目事件，支持多种筛选"""
    stmt = (
        select(StoryEvent)
        .where(StoryEvent.project_id == project_id)
    )
    if event_type:
        stmt = stmt.where(StoryEvent.event_type == event_type)
    if anchor_type:
        stmt = stmt.where(StoryEvent.anchor_type == anchor_type)
    if status:
        stmt = stmt.where(StoryEvent.status == status)

    stmt = stmt.order_by(StoryEvent.timeline_order)
    result = await db.execute(stmt)
    events = result.scalars().all()

    # 如果按剧情线筛选，在应用层过滤（JSON 字段）
    if plotline_id is not None:
        events = [e for e in events if e.plotline_ids and plotline_id in e.plotline_ids]

    return events


@router.post("/", response_model=StoryEventResponse, status_code=201)
async def create_event(
    project_id: int,
    payload: StoryEventCreate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """创建事件"""
    try:
        # 若未指定 sort_order，自动追加
        if payload.sort_order is None:
            max_result = await db.execute(
                select(func.max(StoryEvent.sort_order)).where(StoryEvent.project_id == project_id)
            )
            max_order = max_result.scalar() or -1
            sort_order = max_order + 1
        else:
            sort_order = payload.sort_order

        event_data = payload.model_dump(exclude={"sort_order"})
        event = StoryEvent(
            **event_data,
            project_id=project_id,
            sort_order=sort_order,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
        return event
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"创建事件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建事件失败")


@router.get("/{event_id}", response_model=StoryEventResponse)
async def get_event(
    project_id: int,
    event_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取事件详情"""
    result = await db.execute(
        select(StoryEvent).where(StoryEvent.id == event_id, StoryEvent.project_id == project_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")
    return event


@router.put("/{event_id}", response_model=StoryEventResponse)
async def update_event(
    project_id: int,
    event_id: int,
    payload: StoryEventUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """更新事件"""
    try:
        result = await db.execute(
            select(StoryEvent).where(StoryEvent.id == event_id, StoryEvent.project_id == project_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")

        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(event, key, value)

        await db.commit()
        await db.refresh(event)
        return event
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新事件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新事件失败")


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    project_id: int,
    event_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """删除事件"""
    try:
        result = await db.execute(
            select(StoryEvent).where(StoryEvent.id == event_id, StoryEvent.project_id == project_id)
        )
        event = result.scalar_one_or_none()
        if not event:
            raise HTTPException(status_code=404, detail="事件不存在")
        await db.delete(event)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除事件失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除事件失败")


@router.get("/{event_id}/chain", response_model=dict)
async def get_event_chain(
    project_id: int,
    event_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取事件的因果链（递归查询前因后果）"""
    # 先获取当前事件
    result = await db.execute(
        select(StoryEvent).where(StoryEvent.id == event_id, StoryEvent.project_id == project_id)
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 加载项目所有事件用于链式查询
    all_result = await db.execute(
        select(StoryEvent).where(StoryEvent.project_id == project_id)
    )
    all_events = {e.id: e for e in all_result.scalars().all()}

    def collect_causes(eid: int, visited: set) -> list:
        if eid in visited or eid not in all_events:
            return []
        visited.add(eid)
        ev = all_events[eid]
        causes = []
        for cid in (ev.cause_event_ids or []):
            causes.extend(collect_causes(cid, visited))
            if cid in all_events:
                causes.append(cid)
        return causes

    def collect_effects(eid: int, visited: set) -> list:
        if eid in visited or eid not in all_events:
            return []
        visited.add(eid)
        ev = all_events[eid]
        effects = []
        for eid2 in (ev.effect_event_ids or []):
            if eid2 in all_events:
                effects.append(eid2)
            effects.extend(collect_effects(eid2, visited))
        return effects

    cause_ids = collect_causes(event_id, set())
    effect_ids = collect_effects(event_id, set())

    def event_to_dict(e):
        return StoryEventResponse.model_validate(e).model_dump()

    return {
        "current": event_to_dict(event),
        "causes": [event_to_dict(all_events[cid]) for cid in cause_ids if cid in all_events],
        "effects": [event_to_dict(all_events[eid]) for eid in effect_ids if eid in all_events],
    }