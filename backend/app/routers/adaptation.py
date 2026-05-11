"""剧本改编模块路由。"""
import asyncio
import json
import logging
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.routers.auth import get_current_user
from app.schemas.adaptation import (
    AdaptationProjectCreate, AdaptationProjectUpdate, AdaptationProjectOut,
    AdaptationVersionOut, MappingsBulkPut, MappingEntryOut, SceneBoundary,
    MappingSuggestRequest, RunCreate, SceneRerunRequest, SceneManualPatch,
    VersionDetailOut, SceneResultOut,
)
from app.services.adaptation_pipeline import AdaptationPipeline
from app.services.adaptation_llm_service import get_default_service
from app.services.adaptation_event_bus import event_bus
from app.services.file_parser import FileParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/adaptation", tags=["adaptation"])


def _word_count(text: str) -> int:
    import re
    return len(re.findall(r"[一-鿿]", text)) + len(re.findall(r"[a-zA-Z]+", text))


def _parse_file(content: bytes, filename: str) -> str:
    """按文件扩展名分发解析。"""
    fname = filename.lower()
    if fname.endswith(".docx"):
        return FileParser.parse_docx(content).text
    elif fname.endswith(".md") or fname.endswith(".markdown"):
        return FileParser.parse_markdown(content).text
    else:
        return FileParser.parse_txt(content).text


async def _get_owned_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdaptationProject:
    from sqlalchemy.orm import selectinload
    p = (await db.execute(
        select(AdaptationProject)
        .where(AdaptationProject.id == project_id)
        .options(selectinload(AdaptationProject.versions), selectinload(AdaptationProject.mappings))
    )).scalar_one_or_none()
    if not p or (p.user_id != current_user.id and not getattr(current_user, "is_superuser", False)):
        raise HTTPException(status_code=404, detail="改编项目不存在或无权访问")
    return p


def _project_to_out(p: AdaptationProject) -> dict:
    meta = p.metadata_ or {}
    return {
        "id": p.id, "title": p.title, "source_filename": p.source_filename,
        "intent": p.intent, "intensity": p.intensity, "era_target": p.era_target,
        "status": p.status, "created_at": p.created_at, "updated_at": p.updated_at,
        "word_count": _word_count(p.source_text),
        "scene_boundaries": meta.get("scene_boundaries", []),
        "versions": [
            {
                "id": v.id, "version_no": v.version_no, "triggered_by": v.triggered_by,
                "status": v.status, "stats": v.stats, "error": v.error,
                "created_at": v.created_at, "completed_at": v.completed_at,
            } for v in p.versions
        ],
        "mappings": [
            {
                "id": m.id, "entity_type": m.entity_type,
                "original_text": m.original_text, "replacement_text": m.replacement_text,
                "locked": m.locked, "notes": m.notes, "order_index": m.order_index,
            } for m in p.mappings
        ],
    }


def _version_to_out(v) -> dict:
    return {
        "id": v.id, "version_no": v.version_no, "triggered_by": v.triggered_by,
        "status": v.status, "stats": v.stats, "error": v.error,
        "created_at": v.created_at, "completed_at": v.completed_at,
    }


def _scene_to_out(s) -> dict:
    return {
        "id": s.id, "scene_index": s.scene_index, "scene_title": s.scene_title,
        "status": s.status, "error": s.error, "token_used": s.token_used,
        "line_count_delta_pct": s.line_count_delta_pct,
        "original_scene_text": s.original_scene_text,
        "rewritten_scene_text": s.rewritten_scene_text,
        "manual_edits": s.manual_edits or [],
        "updated_at": s.updated_at,
    }


# ─── Project CRUD ────────────────────────────────────────────────────────

@router.post("/projects", status_code=201, response_model=AdaptationProjectOut)
async def create_project(
    payload: AdaptationProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.raw_text:
        raise HTTPException(400, "raw_text 不能为空（上传文件请用 /projects/upload 端点）")
    if len(payload.raw_text) > settings.ADAPTATION_MAX_CHARS:
        raise HTTPException(400, f"原文超过 {settings.ADAPTATION_MAX_CHARS} 字上限")
    p = AdaptationProject(
        user_id=current_user.id, title=payload.title,
        source_text=payload.raw_text, intent=payload.intent,
        intensity=payload.intensity, era_target=payload.era_target,
        status="ready", metadata_={},
    )
    db.add(p); await db.commit(); await db.refresh(p)
    # Eager load relationships to avoid lazy-load in async context
    from sqlalchemy.orm import selectinload
    await db.refresh(p, attribute_names=["versions", "mappings"])
    return _project_to_out(p)


@router.post("/projects/upload", status_code=201, response_model=AdaptationProjectOut)
async def create_project_upload(
    title: str = Form(...),
    intensity: int = Form(2),
    intent: Optional[str] = Form(None),
    era_target: Optional[str] = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    try:
        text = _parse_file(content, file.filename or "upload.txt")
    except Exception as e:
        raise HTTPException(400, f"文件解析失败：{e}")
    if len(text) > settings.ADAPTATION_MAX_CHARS:
        raise HTTPException(400, f"原文超过 {settings.ADAPTATION_MAX_CHARS} 字上限")
    p = AdaptationProject(
        user_id=current_user.id, title=title, source_filename=file.filename,
        source_text=text, intent=intent, intensity=intensity,
        era_target=era_target, status="ready", metadata_={},
    )
    db.add(p); await db.commit(); await db.refresh(p, attribute_names=["versions", "mappings"])
    return _project_to_out(p)


@router.get("/projects", response_model=List[AdaptationProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy.orm import selectinload
    rows = (await db.execute(
        select(AdaptationProject)
        .where(AdaptationProject.user_id == current_user.id)
        .options(selectinload(AdaptationProject.versions), selectinload(AdaptationProject.mappings))
        .order_by(AdaptationProject.created_at.desc())
    )).scalars().all()
    return [_project_to_out(p) for p in rows]


@router.get("/projects/{project_id}", response_model=AdaptationProjectOut)
async def get_project(p: AdaptationProject = Depends(_get_owned_project)):
    return _project_to_out(p)


@router.patch("/projects/{project_id}", response_model=AdaptationProjectOut)
async def update_project(
    payload: AdaptationProjectUpdate,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit(); await db.refresh(p)
    return _project_to_out(p)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(p); await db.commit()


# ─── Extract / Split / Mappings ──────────────────────────────────────────

@router.post("/projects/{project_id}/extract", response_model=AdaptationProjectOut)
async def extract(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    try:
        await pipe.extract(p)
    except Exception as e:
        raise HTTPException(502, f"实体抽取失败：{e}")
    await db.refresh(p)
    return _project_to_out(p)


@router.post("/projects/{project_id}/split", response_model=AdaptationProjectOut)
async def split(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    await pipe.split(p)
    await db.refresh(p)
    return _project_to_out(p)


@router.put("/projects/{project_id}/mappings", response_model=List[MappingEntryOut])
async def put_mappings(
    payload: MappingsBulkPut,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
    )
    for entry in payload.entries:
        db.add(AdaptationMappingEntry(project_id=p.id, **entry.model_dump()))
    await db.commit()
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()
    return [
        {"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
         "replacement_text": m.replacement_text, "locked": m.locked,
         "notes": m.notes, "order_index": m.order_index}
        for m in rows
    ]


@router.post("/projects/{project_id}/mappings/suggest", response_model=List[MappingEntryOut])
async def suggest_mappings(
    payload: MappingSuggestRequest,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()

    targets = [r for r in rows if (not payload.only_empty) or not r.replacement_text]
    if not targets:
        return [{"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
                 "replacement_text": m.replacement_text, "locked": m.locked,
                 "notes": m.notes, "order_index": m.order_index} for m in rows]

    svc = get_default_service()
    prompt = (
        f"你是剧本改编助手。新时代/世界设定：{p.era_target or '未指定'}；"
        f"改编意图：{p.intent or '未指定'}。\n"
        "为下列原词建议一个合适的新名称，输出严格 JSON：[{\"original\": \"...\", \"replacement\": \"...\"}]\n"
        + json.dumps([{"original": t.original_text, "type": t.entity_type} for t in targets], ensure_ascii=False)
    )
    raw = await svc.provider.complete(prompt, model=svc.extract_model)
    try:
        sugg = {item["original"]: item["replacement"] for item in json.loads(raw)}
    except Exception:
        sugg = {}
    for t in targets:
        if t.original_text in sugg and not t.locked:
            t.replacement_text = sugg[t.original_text]
    await db.commit()
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()
    return [{"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
             "replacement_text": m.replacement_text, "locked": m.locked,
             "notes": m.notes, "order_index": m.order_index} for m in rows]


# ─── Runs / SSE / Rerun / Patch / Export ─────────────────────────────────

async def _get_owned_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdaptationVersion:
    v = (await db.execute(
        select(AdaptationVersion).where(AdaptationVersion.id == version_id)
    )).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "version 不存在")
    p = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.id == v.project_id)
    )).scalar_one()
    if p.user_id != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(404, "无权访问")
    return v


@router.post("/projects/{project_id}/runs", response_model=AdaptationVersionOut)
async def create_run(
    payload: RunCreate,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    if not (p.metadata_ or {}).get("scene_boundaries"):
        raise HTTPException(400, "尚未切场，请先调用 /split")
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    version = await pipe.create_full_run(p, extra_prompt=payload.extra_prompt)
    asyncio.create_task(_background_run(p.id, version.id))
    return _version_to_out(version)


async def _background_run(project_id: int, version_id: int) -> None:
    """后台 task：用一个新的 db session 执行实际改写。"""
    from app.core.database import async_session
    async with async_session() as session:
        p = (await session.execute(
            select(AdaptationProject).where(AdaptationProject.id == project_id)
        )).scalar_one_or_none()
        v = (await session.execute(
            select(AdaptationVersion).where(AdaptationVersion.id == version_id)
        )).scalar_one_or_none()
        if not p or not v:
            return
        pipe = AdaptationPipeline(db=session, llm=get_default_service())
        try:
            await pipe.execute_full_run(p, v)
        except Exception as e:
            logger.exception("背景跑改编失败")
            v.status = "failed"
            v.error = str(e)[:500]
            await session.commit()
            await event_bus.publish(version_id, {"event": "version_failed", "error": str(e)[:200]})


@router.get("/projects/{project_id}/runs", response_model=List[AdaptationVersionOut])
async def list_runs(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AdaptationVersion).where(AdaptationVersion.project_id == p.id)
        .order_by(AdaptationVersion.version_no.desc())
    )).scalars().all()
    return [_version_to_out(v) for v in rows]


@router.get("/runs/{version_id}", response_model=VersionDetailOut)
async def get_version(
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy.orm import selectinload
    # Re-query with eager loaded scene_results to avoid lazy load
    v_full = (await db.execute(
        select(AdaptationVersion)
        .where(AdaptationVersion.id == v.id)
        .options(selectinload(AdaptationVersion.scene_results))
    )).scalar_one()
    return {**_version_to_out(v_full), "scene_results": [_scene_to_out(s) for s in v_full.scene_results]}


@router.get("/runs/{version_id}/stream")
async def stream_run(v: AdaptationVersion = Depends(_get_owned_version)):
    sub = event_bus.subscribe(v.id)

    async def gen():
        try:
            yield "data: " + json.dumps({"event": "subscribed", "version_id": v.id}) + "\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield "data: " + json.dumps(payload, default=str) + "\n\n"
                    if payload.get("event") in ("version_done", "version_failed"):
                        return
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/runs/{version_id}/scenes/{scene_index}/rerun", response_model=SceneResultOut)
async def rerun_scene(
    scene_index: int,
    payload: SceneRerunRequest,
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    scene = (await db.execute(
        select(AdaptationSceneResult).where(
            AdaptationSceneResult.version_id == v.id,
            AdaptationSceneResult.scene_index == scene_index,
        )
    )).scalar_one_or_none()
    if not scene:
        raise HTTPException(404, "scene 不存在")
    if scene.status == "running":
        raise HTTPException(409, "该场正在跑，无法重跑")
    p = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.id == v.project_id)
    )).scalar_one()
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    try:
        await pipe.rerun_scene(p, v, scene, payload.extra_prompt)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _scene_to_out(scene)


@router.patch("/runs/{version_id}/scenes/{scene_index}", response_model=SceneResultOut)
async def patch_scene(
    scene_index: int,
    payload: SceneManualPatch,
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    scene = (await db.execute(
        select(AdaptationSceneResult).where(
            AdaptationSceneResult.version_id == v.id,
            AdaptationSceneResult.scene_index == scene_index,
        )
    )).scalar_one_or_none()
    if not scene:
        raise HTTPException(404, "scene 不存在")
    edits = list(scene.manual_edits or [])
    edits.append({
        "type": "manual", "at": datetime.utcnow().isoformat(),
        "before": scene.rewritten_scene_text, "after": payload.rewritten_scene_text,
    })
    scene.manual_edits = edits
    scene.rewritten_scene_text = payload.rewritten_scene_text
    scene.status = "manual_edited"
    await db.commit()
    return _scene_to_out(scene)


@router.get("/runs/{version_id}/export")
async def export_run(
    format: str = "txt",
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    if format not in ("txt", "docx"):
        raise HTTPException(400, "format 仅支持 txt/docx")
    scenes = (await db.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == v.id)
        .order_by(AdaptationSceneResult.scene_index)
    )).scalars().all()
    parts = [s.rewritten_scene_text or s.original_scene_text for s in scenes]

    if format == "txt":
        text = "\n\n".join(parts)
        return StreamingResponse(
            BytesIO(text.encode("utf-8")), media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=adaptation_v{v.version_no}.txt"},
        )

    # docx
    from docx import Document
    doc = Document()
    for s in scenes:
        if s.scene_title:
            doc.add_heading(s.scene_title, level=2)
        doc.add_paragraph(s.rewritten_scene_text or s.original_scene_text)
    buf = BytesIO()
    doc.save(buf); buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=adaptation_v{v.version_no}.docx"},
    )
