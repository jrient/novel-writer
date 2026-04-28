"""
剧本生成模块路由
Project CRUD + Node CRUD + Session CRUD + AI SSE 接口
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.script_node import ScriptNode
from app.models.script_node_version import ScriptNodeVersion
from app.models.script_project import ScriptProject
from app.models.script_session import ScriptSession
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.drama import (
    CreateVersionRequest,
    DYNAMIC_NODE_TYPES,
    EXPLANATORY_NODE_TYPES,
    ExpandEpisodeRequest,
    ExpandNodeRequest,
    GlobalDirectiveRequest,
    NodeVersionResponse,
    ReorderRequest,
    RewriteRequest,
    ScriptNodeCreate,
    ScriptNodeResponse,
    ScriptNodeUpdate,
    ScriptProjectCreate,
    ScriptProjectListResponse,
    ScriptProjectResponse,
    ScriptProjectUpdate,
    ScriptSessionResponse,
    SessionAnswerRequest,
    SessionSummaryResponse,
)
from app.services.script_ai_service import ScriptAIService
from app.services.handbook_provider import get_handbook
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/drama", tags=["drama"])

# ─── Helpers ──────────────────────────────────────────────────────────────────


class AIConfigUpdate(BaseModel):
    """AI 配置更新请求（drama router 本地定义）"""
    ai_config: Optional[Dict[str, Any]] = None


class CharacterSettingItem(BaseModel):
    """角色设定项"""
    id: str
    name: str = Field(..., max_length=100)
    description: str = Field("", max_length=2000)


class ProjectSettingsUpdate(BaseModel):
    """剧本设定更新请求"""
    characters: List[CharacterSettingItem] = Field(default_factory=list, max_length=50)
    world_setting: str = Field("", max_length=3000)
    tone: str = Field("", max_length=1000)
    plot_anchors: str = Field("", max_length=3000)
    persistent_directive: str = Field("", max_length=2000)


async def get_drama_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScriptProject:
    result = await db.execute(
        select(ScriptProject).where(
            ScriptProject.id == id,
            or_(
                ScriptProject.user_id == current_user.id,
                current_user.is_superuser == True,
            ),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="剧本不存在或无权访问")
    return project


def _validate_node_type(script_type: str, node_type: str):
    if script_type == "explanatory" and node_type not in EXPLANATORY_NODE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"解说漫剧本不支持 '{node_type}' 类型节点"
        )
    if script_type == "dynamic" and node_type not in DYNAMIC_NODE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"动态漫剧本不支持 '{node_type}' 类型节点"
        )


def _sse_response(stream_gen):
    """包装异步生成器为 SSE StreamingResponse"""
    return StreamingResponse(
        stream_gen,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _sse_stream(generator):
    """将文本生成器转换为 SSE 格式"""
    try:
        async for chunk in generator:
            yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as e:
        logger.error(f"SSE stream error: {e}", exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"


# ─── Project CRUD ─────────────────────────────────────────────────────────────


async def _create_node_version(
    db: AsyncSession, node: ScriptNode, source: str
) -> ScriptNodeVersion:
    """Create a version snapshot for an episode node, enforcing max 20 versions."""
    result = await db.execute(
        select(func.coalesce(func.max(ScriptNodeVersion.version_number), 0))
        .where(ScriptNodeVersion.node_id == node.id)
    )
    next_version = result.scalar() + 1

    version = ScriptNodeVersion(
        node_id=node.id,
        version_number=next_version,
        title=node.title,
        content=node.content,
        source=source,
    )
    db.add(version)
    await db.flush()

    # Enforce max 20 versions: delete oldest if exceeded
    count_result = await db.execute(
        select(func.count()).where(ScriptNodeVersion.node_id == node.id)
    )
    total = count_result.scalar()
    if total > 20:
        oldest_result = await db.execute(
            select(ScriptNodeVersion)
            .where(ScriptNodeVersion.node_id == node.id)
            .order_by(ScriptNodeVersion.version_number.asc())
            .limit(total - 20)
        )
        for old_ver in oldest_result.scalars():
            await db.delete(old_ver)

    return version


@router.post("/", response_model=ScriptProjectResponse, status_code=201)
async def create_project(
    body: ScriptProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建剧本项目"""
    project = ScriptProject(
        user_id=current_user.id,
        title=body.title,
        script_type=body.script_type,
        concept=body.concept,
        ai_config=body.ai_config.model_dump() if body.ai_config else None,
        metadata_=body.metadata_,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/", response_model=ScriptProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    script_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出剧本项目（分页，可按类型/状态过滤）"""
    filters = [
        or_(
            ScriptProject.user_id == current_user.id,
            current_user.is_superuser == True,
        )
    ]
    if script_type:
        filters.append(ScriptProject.script_type == script_type)
    if status:
        filters.append(ScriptProject.status == status)

    count_result = await db.execute(
        select(func.count()).select_from(ScriptProject).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ScriptProject)
        .where(*filters)
        .order_by(ScriptProject.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    return ScriptProjectListResponse(
        items=list(items),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}", response_model=ScriptProjectResponse)
async def get_project(
    project: ScriptProject = Depends(get_drama_project),
):
    """获取剧本项目详情"""
    return project


@router.put("/{id}", response_model=ScriptProjectResponse)
async def update_project(
    body: ScriptProjectUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新剧本项目"""
    update_data = body.model_dump(exclude_unset=True, by_alias=False)
    for field, value in update_data.items():
        if field == "ai_config" and value is not None and hasattr(value, "model_dump"):
            value = value.model_dump()
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{id}", status_code=204)
async def delete_project(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除剧本项目（级联删除节点和会话）"""
    await db.delete(project)
    await db.commit()


@router.put("/{id}/ai-config", response_model=ScriptProjectResponse)
async def update_ai_config(
    body: AIConfigUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新 AI 配置"""
    project.ai_config = body.ai_config
    await db.commit()
    await db.refresh(project)
    return project


@router.put("/{id}/settings", response_model=ScriptProjectResponse)
async def update_project_settings(
    body: ProjectSettingsUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新剧本设定（人物/世界观/风格/剧情/持久化AI指令）"""
    current_meta = dict(project.metadata_ or {})
    current_meta["settings"] = body.model_dump()
    project.metadata_ = current_meta
    await db.commit()
    await db.refresh(project)
    return project


# ─── Node CRUD ────────────────────────────────────────────────────────────────


@router.get("/{id}/nodes", response_model=List[Dict[str, Any]])
async def get_nodes_tree(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """获取所有节点（树形结构）"""
    result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = result.scalars().all()

    node_map = {
        n.id: {**ScriptNodeResponse.model_validate(n).model_dump(by_alias=False), "children": []}
        for n in all_nodes
    }
    roots = []
    for n in all_nodes:
        node_dict = node_map[n.id]
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(node_dict)
        else:
            roots.append(node_dict)
    return roots


@router.post("/{id}/nodes", response_model=ScriptNodeResponse, status_code=201)
async def create_node(
    body: ScriptNodeCreate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """创建剧本节点（验证节点类型与剧本类型匹配）"""
    _validate_node_type(project.script_type, body.node_type)

    # Validate parent belongs to this project
    if body.parent_id:
        parent_result = await db.execute(
            select(ScriptNode).where(
                ScriptNode.id == body.parent_id,
                ScriptNode.project_id == project.id,
            )
        )
        if not parent_result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="父节点不存在或不属于该项目")

    node = ScriptNode(
        project_id=project.id,
        parent_id=body.parent_id,
        node_type=body.node_type,
        title=body.title,
        content=body.content,
        speaker=body.speaker,
        visual_desc=body.visual_desc,
        sort_order=body.sort_order,
        metadata_=body.metadata_,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


# IMPORTANT: reorder route BEFORE /{node_id} to avoid path conflicts
@router.put("/{id}/nodes/reorder", status_code=204)
async def reorder_nodes(
    body: ReorderRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """批量重排序节点"""
    for idx, node_id in enumerate(body.node_ids):
        result = await db.execute(
            select(ScriptNode).where(
                ScriptNode.id == node_id,
                ScriptNode.project_id == project.id,
            )
        )
        node = result.scalar_one_or_none()
        if node:
            node.sort_order = idx
    await db.commit()


@router.put("/{id}/nodes/{node_id}", response_model=ScriptNodeResponse)
async def update_node(
    node_id: int,
    body: ScriptNodeUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新剧本节点"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    update_data = body.model_dump(exclude_unset=True, by_alias=False)
    for field, value in update_data.items():
        setattr(node, field, value)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/{id}/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除剧本节点（级联删除子节点）"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    await db.delete(node)
    await db.commit()


# ─── Session CRUD ─────────────────────────────────────────────────────────────


@router.post("/{id}/session", response_model=ScriptSessionResponse)
async def get_or_create_session(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """获取或创建会话（幂等）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        session = ScriptSession(
            project_id=project.id,
            state="init",
            history=[],
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


@router.delete("/{id}/session", status_code=204)
async def delete_session(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除会话"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()


# ─── AI Session Routes (SSE) ──────────────────────────────────────────────────


def _guess_genre_from_concept(concept: str) -> str:
    """从创意概念粗略推断类型"""
    text = concept.lower()
    if "萌宝" in text or "宝宝" in text or "崽崽" in text or "带球跑" in text:
        return "原创 / 萌宝"
    # 男频关键词：修仙/玄幻/系统 + 不含明显女频特征
    if "男频" in text or "修仙" in text or "玄幻" in text or "系统流" in text:
        return "原创 / 男频"
    # 女频关键词
    if "女频" in text or "古言" in text or "宅斗" in text or "宫斗" in text or "穿书" in text:
        return "原创 / 女频"
    # 世情关键词
    if "世情" in text or "家庭" in text or "婚姻" in text or "婆媳" in text or "伦理" in text:
        return "原创 / 世情"
    return ""


@router.post("/{id}/session/init")
async def session_init(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """初始化会话：让 AI 根据项目创意概念生成第一个问题（SSE 流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        session = ScriptSession(
            project_id=project.id,
            state="init",
            history=[],
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)

    # 如果 history 已有内容，说明已初始化过，直接返回
    if session.history:
        return _sse_response(_already_init_stream(session.history))

    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    # 注入 handbook 知识到问答阶段
    handbook = get_handbook()
    # 从 concept 中粗略推断类型
    genre = _guess_genre_from_concept(project.concept) if project.concept else ""
    handbook_context = handbook.get_question_guidance(genre)

    async def stream():
        full_response = ""
        async for chunk in _sse_stream(
            ai_service.generate_question(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=[],
                genre=genre,
                handbook_context=handbook_context,
            )
        ):
            try:
                data = json.loads(chunk.removeprefix("data: ").strip())
                if data.get("type") == "text":
                    full_response += data.get("text", "")
            except Exception:
                pass
            yield chunk

        # Save AI first question to history
        if full_response:
            update_result = await db.execute(
                select(ScriptSession).where(ScriptSession.project_id == project.id)
            )
            updated_session = update_result.scalar_one_or_none()
            if updated_session:
                updated_session.history = [{"role": "assistant", "content": full_response}]
                updated_session.state = "collecting"
                await db.commit()

    return _sse_response(stream())


async def _already_init_stream(history):
    """已初始化的 session，返回第一条 AI 消息"""
    for msg in history:
        if msg.get("role") == "assistant":
            yield f"data: {json.dumps({'text': msg['content'], 'type': 'text'})}\n\n"
            break
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.post("/{id}/session/answer")
async def session_answer(
    body: SessionAnswerRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """提交回答，获取下一个 AI 问题（SSE 流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")

    # Append user answer to history
    history = list(session.history or [])
    history.append({"role": "user", "content": body.answer})
    session.history = history
    session.state = "collecting"
    await db.commit()

    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    # 注入 handbook 知识到问答阶段
    handbook = get_handbook()
    genre = _guess_genre_from_concept(project.concept) if project.concept else ""
    handbook_context = handbook.get_question_guidance(genre)

    async def stream():
        full_response = ""
        async for chunk in _sse_stream(
            ai_service.generate_question(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=history,
                genre=genre,
                handbook_context=handbook_context,
            )
        ):
            # Extract text from SSE for history recording
            try:
                data = json.loads(chunk.removeprefix("data: ").strip())
                if data.get("type") == "text":
                    full_response += data.get("text", "")
            except Exception:
                pass
            yield chunk

        # Save AI response to history
        if full_response:
            new_history = list(session.history or [])
            new_history.append({"role": "assistant", "content": full_response})
            # Use a new db operation — session object might be stale
            update_result = await db.execute(
                select(ScriptSession).where(ScriptSession.project_id == project.id)
            )
            updated_session = update_result.scalar_one_or_none()
            if updated_session:
                updated_session.history = new_history
                await db.commit()

    return _sse_response(stream())


@router.post("/{id}/session/skip", response_model=ScriptSessionResponse)
async def session_skip(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """跳过问答，直接进入大纲生成阶段"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")
    session.state = "generating"
    await db.commit()
    await db.refresh(session)
    return session


@router.post("/{id}/session/summarize", response_model=SessionSummaryResponse)
async def session_summarize(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """根据问答历史生成结构化摘要"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    history = list(session.history or [])
    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    summary = await ai_service.generate_summary(
        script_type=project.script_type,
        title=project.title,
        concept=project.concept,
        history=history,
    )

    session.summary = summary

    # 自动同步 summary 到 project settings（Wizard → Settings）
    _meta = project.metadata_ or {}
    _existing_settings = _meta.get("settings", {})

    # 从 summary 提取 settings 数据
    _new_settings = {
        "characters": _existing_settings.get("characters", []),
        "world_setting": _existing_settings.get("world_setting", ""),
        "tone": _existing_settings.get("tone", ""),
        "plot_anchors": _existing_settings.get("plot_anchors", ""),
        "persistent_directive": _existing_settings.get("persistent_directive", ""),
    }

    # 同步角色：从 summary.主要角色 提取
    if "主要角色" in summary and summary["主要角色"]:
        _new_settings["characters"] = [
            {
                "id": str(uuid.uuid4()),
                "name": char.split("：")[0] if "：" in char else char.split(":")[0] if ":" in char else char,
                "description": char,
            }
            for char in summary["主要角色"]
            if char
        ]

    # 同步世界设定：从 summary.场景设定 提取
    if "场景设定" in summary and summary["场景设定"]:
        _new_settings["world_setting"] = summary["场景设定"]

    # 同步风格基调：从 summary.风格基调 提取
    if "风格基调" in summary and summary["风格基调"]:
        _new_settings["tone"] = summary["风格基调"]

    # 同步核心冲突/开局钩子到 plot_anchors
    _anchors = []
    if "核心冲突" in summary and summary["核心冲突"]:
        _anchors.append(f"核心冲突：{summary['核心冲突']}")
    if "开局钩子" in summary and summary["开局钩子"]:
        _anchors.append(f"开局钩子：{summary['开局钩子']}")
    if _anchors:
        _new_settings["plot_anchors"] = "\n".join(_anchors)

    # 更新 project.metadata_
    project.metadata_ = {**_meta, "settings": _new_settings}

    await db.commit()

    return summary


@router.put("/{id}/session/summary", response_model=SessionSummaryResponse)
async def update_session_summary(
    body: SessionSummaryResponse,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """保存用户编辑后的摘要"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    session.summary = body.model_dump()
    await db.commit()
    return body


@router.post("/{id}/session/generate-outline")
async def session_generate_outline(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """生成大纲草稿（SSE 流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")

    session.state = "generating"
    await db.commit()

    # 读取目标集数（解说漫与动态漫均有效；解说漫对应段落数）
    episode_count = 20
    if session.summary:
        episode_count = int((session.summary or {}).get("目标集数", 20))
        episode_count = max(1, min(200, episode_count))

    history = list(session.history or [])
    # If user edited summary, append it as extra context for outline generation
    if session.summary:
        import json as _json
        summary_text = _json.dumps(session.summary, ensure_ascii=False)
        history = history + [
            {"role": "assistant", "content": "根据以上对话，我整理的创作信息如下："},
            {"role": "user", "content": f"确认的创作信息：{summary_text}\n请严格基于以上确认信息生成大纲。"},
        ]
    _proj_settings = (project.metadata_ or {}).get("settings", {})
    genre = _guess_genre_from_concept(project.concept) if project.concept else ""
    handbook = get_handbook()
    handbook_context = handbook.get_question_guidance(genre)
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_outline(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=history,
                episode_count=episode_count,
                genre=genre,
                handbook_context=handbook_context,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            # Restore state so user can retry
            try:
                rollback_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                rollback_session = rollback_result.scalar_one_or_none()
                if rollback_session:
                    rollback_session.state = "done"
                    await db.commit()
            except Exception:
                pass
            return

        # Save outline_draft BEFORE sending done event to avoid race condition
        if full_response:
            try:
                json_str = full_response.strip()
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]

                outline_json = json.loads(json_str)
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session:
                    # Preserve previous outline in history before overwriting
                    if updated_session.outline_draft:
                        outline_history = list(updated_session.outline_history or [])
                        outline_history.append(updated_session.outline_draft)
                        updated_session.outline_history = outline_history
                    updated_session.outline_draft = outline_json
                    updated_session.state = "done"
                    await db.commit()
                    logger.info(f"Outline saved for project {project.id}, episodes={episode_count}")
                    # 检查生成的集数是否完整
                    actual_count = len(outline_json.get("sections", []))
                    if actual_count < episode_count:
                        yield f"data: {json.dumps({'type': 'partial_warning', 'actual': actual_count, 'expected': episode_count})}\n\n"
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse outline JSON: {e}")
                # 尝试补全截断的 JSON
                try:
                    fixed = json_str.rstrip()
                    # 补全常见截断：缺少结尾的 ]}}
                    for suffix in [']}', ']}', ']}}']:
                        try:
                            outline_json = json.loads(fixed + suffix)
                            # 解析成功，保存修复后的结果
                            update_result = await db.execute(
                                select(ScriptSession).where(ScriptSession.project_id == project.id)
                            )
                            updated_session = update_result.scalar_one_or_none()
                            if updated_session:
                                updated_session.outline_draft = outline_json
                                updated_session.state = "done"
                                await db.commit()
                                actual_count = len(outline_json.get("sections", []))
                                yield f"data: {json.dumps({'type': 'partial_warning', 'actual': actual_count, 'expected': episode_count})}\n\n"
                            break
                        except json.JSONDecodeError:
                            continue
                    else:
                        # 无法修复
                        yield f"data: {json.dumps({'type': 'error', 'message': f'大纲生成不完整，请减少集数后重试'})}\n\n"
                        return
                except Exception:
                    yield f"data: {json.dumps({'type': 'error', 'message': '大纲解析失败，请重试'})}\n\n"
                    return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/session/expand-episode")
async def session_expand_episode(
    body: ExpandEpisodeRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """生成单集/单段完整内容（SSE 流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if not session.outline_draft:
        raise HTTPException(status_code=400, detail="请先生成大纲")

    sections = session.outline_draft.get("sections", [])
    idx = body.episode_index
    unit = "集" if project.script_type == "dynamic" else "段"
    if idx < 0 or idx >= len(sections):
        raise HTTPException(status_code=400, detail=f"索引 {idx} 超出范围（共 {len(sections)} {unit}）")

    current_ep = sections[idx]
    prev_ep = sections[idx - 1] if idx > 0 else None
    next_ep = sections[idx + 1] if idx < len(sections) - 1 else None
    total = len(sections)

    summary_data = session.summary or {}
    main_characters = summary_data.get("主要角色", [])
    core_conflict = summary_data.get("核心冲突", "")
    style_tone = summary_data.get("风格基调", "")
    outline_summary = session.outline_draft.get("summary", "")

    _proj_settings = (project.metadata_ or {}).get("settings", {})
    genre = _guess_genre_from_concept(project.concept) if project.concept else ""
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_episode_content(
                title=project.title,
                outline_summary=outline_summary,
                main_characters=main_characters,
                core_conflict=core_conflict,
                style_tone=style_tone,
                episode_index=idx,
                total_episodes=total,
                current_episode=current_ep,
                prev_episode=prev_ep,
                next_episode=next_ep,
                script_type=project.script_type,
                genre=genre,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"generate_episode_content stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if full_response:
            try:
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session and updated_session.outline_draft:
                    import copy
                    new_draft = copy.deepcopy(updated_session.outline_draft)
                    new_sections = new_draft.get("sections", [])
                    if idx < len(new_sections):
                        # 纯文本直接写入 content，标记已生成
                        new_sections[idx]["content"] = full_response.strip()
                        new_sections[idx]["generated"] = True
                        # 清除旧的 children（如果有）
                        new_sections[idx].pop("children", None)
                        new_draft["sections"] = new_sections
                        updated_session.outline_draft = new_draft
                        await db.commit()
                        logger.info(f"Episode {idx} content generated for project {project.id}")
            except Exception as e:
                logger.warning(f"Could not save episode content: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': '内容保存失败，请重试'})}\n\n"
                return

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/session/confirm-outline", response_model=ScriptSessionResponse)
async def session_confirm_outline(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """确认大纲，将 outline_draft 写入 ScriptNode"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在，请先创建会话")
    if not session.outline_draft:
        raise HTTPException(status_code=400, detail="没有待确认的大纲草稿")

    # Batch delete existing nodes
    await db.execute(delete(ScriptNode).where(ScriptNode.project_id == project.id))

    # Write outline_draft nodes recursively
    outline = session.outline_draft
    sections = outline.get("sections", [])
    await _write_nodes_async(db, project.id, sections, parent_id=None)

    # Create initial versions for all episode nodes
    ep_result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    for ep_node in ep_result.scalars():
        init_ver = ScriptNodeVersion(
            node_id=ep_node.id,
            version_number=1,
            title=ep_node.title,
            content=ep_node.content,
            source="init",
        )
        db.add(init_ver)

    # Update project status
    project.status = "outlined"

    # Update session state
    session.state = "done"
    await db.commit()
    await db.refresh(session)
    return session


async def _write_nodes_async(
    db: AsyncSession, project_id: int, nodes: list, parent_id: Optional[int]
):
    """递归将大纲节点写入数据库（异步，flush 后获取 ID 再写子节点）"""
    for item in nodes:
        node = ScriptNode(
            project_id=project_id,
            parent_id=parent_id,
            node_type=item.get("node_type", "section"),
            title=item.get("title"),
            content=item.get("content"),
            speaker=item.get("speaker"),
            visual_desc=item.get("visual_desc"),
            sort_order=item.get("sort_order", 0),
        )
        db.add(node)
        await db.flush()  # get node.id
        children = item.get("children", [])
        if children:
            await _write_nodes_async(db, project_id, children, parent_id=node.id)


# ─── AI Content Generation Routes (SSE) ──────────────────────────────────────


async def _build_node_context(
    db: AsyncSession, node: ScriptNode, project_id: int
) -> str:
    """构建节点的上下文信息：父节点概要 + 相邻兄弟节点标题 + 故事摘要"""
    parts = []

    # 1. 父节点信息
    if node.parent_id:
        parent_result = await db.execute(
            select(ScriptNode).where(ScriptNode.id == node.parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if parent:
            parts.append(f"所属{parent.node_type}：{parent.title or '未命名'}")
            if parent.content:
                parts.append(f"概要：{parent.content[:200]}")

            # 2. 兄弟节点（同一父节点下的相邻节点）
            siblings_result = await db.execute(
                select(ScriptNode)
                .where(
                    ScriptNode.parent_id == node.parent_id,
                    ScriptNode.project_id == project_id,
                )
                .order_by(ScriptNode.sort_order)
            )
            siblings = siblings_result.scalars().all()
            if len(siblings) > 1:
                sibling_info = []
                for s in siblings:
                    marker = "→ " if s.id == node.id else "  "
                    label = s.title or (s.content[:30] + "..." if s.content else "未命名")
                    sibling_info.append(f"{marker}[{s.node_type}] {label}")
                parts.append("同级节点：\n" + "\n".join(sibling_info))

    # 3. 故事摘要（从 session 获取）
    session_result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project_id)
    )
    session = session_result.scalar_one_or_none()
    if session and session.summary:
        summary = session.summary
        if summary.get("故事概要"):
            parts.append(f"故事概要：{summary['故事概要']}")
        if summary.get("核心冲突"):
            parts.append(f"核心冲突：{summary['核心冲突']}")
        if summary.get("风格基调"):
            parts.append(f"风格基调：{summary['风格基调']}")

    return "\n".join(parts) if parts else ""


@router.post("/{id}/nodes/{node_id}/expand")
async def expand_node(
    node_id: int,
    body: ExpandNodeRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """展开节点内容（SSE 流式）"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    context = await _build_node_context(db, node, project.id)
    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    async def stream():
        async for chunk in _sse_stream(
            ai_service.expand_node(
                script_type=project.script_type,
                title=project.title,
                node_type=node.node_type,
                node_title=node.title,
                content=node.content,
                instructions=body.instructions,
                context=context,
            )
        ):
            yield chunk

    return _sse_response(stream())


@router.post("/{id}/ai/rewrite")
async def rewrite_content(
    body: RewriteRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """重写内容（SSE 流式）"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == body.node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    context = await _build_node_context(db, node, project.id)
    _proj_settings = (project.metadata_ or {}).get("settings", {})
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)

    async def stream():
        async for chunk in _sse_stream(
            ai_service.rewrite_content(
                script_type=project.script_type,
                title=project.title,
                node_type=node.node_type,
                content=node.content or "",
                instructions=body.instructions,
                context=context,
            )
        ):
            yield chunk

    return _sse_response(stream())


@router.post("/{id}/ai/global-directive")
async def global_directive(
    body: GlobalDirectiveRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """全局指令处理（SSE 流式）"""
    # Collect all node content for context
    nodes_result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = nodes_result.scalars().all()
    content_parts = []
    for n in all_nodes:
        if n.content:
            label = f"[{n.node_type}] {n.title or ''}"
            content_parts.append(f"{label}: {n.content}")
    full_content = "\n\n".join(content_parts) if content_parts else "（暂无内容）"

    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        async for chunk in _sse_stream(
            ai_service.global_directive(
                script_type=project.script_type,
                title=project.title,
                directive=body.directive,
                content=full_content,
            )
        ):
            yield chunk

    return _sse_response(stream())


# ─── Export ───────────────────────────────────────────────────────────────────


@router.get("/{id}/export")
async def export_project(
    format: str = Query("txt", pattern="^(txt|markdown)$"),
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """导出剧本（txt 或 markdown 格式）

    输出顺序参考精品剧本档案：剧本简介 → 人物小传 → 正文。
    简介与人物小传从 session.summary 中读取，缺失时跳过对应段落。
    """
    nodes_result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = nodes_result.scalars().all()

    session_result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = session_result.scalar_one_or_none()
    summary = (session.summary or {}) if session else {}

    if format == "markdown":
        content = _export_markdown(project, all_nodes, summary)
        media_type = "text/markdown"
        filename = f"{project.title}.md"
    else:
        content = _export_txt(project, all_nodes, summary)
        media_type = "text/plain"
        filename = f"{project.title}.txt"

    from fastapi.responses import Response

    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


_TXT_DIVIDER = "=" * 50
_BIO_FIELD_LABELS = [
    ("身份", "身份"),
    ("目标", "目标"),
    ("弱点", "弱点"),
    ("关键关系", "关键关系"),
    ("典型台词", "典型台词"),
]


def _txt_section_header(title: str) -> List[str]:
    """生成 txt 大段标题分隔符（=== 标题 === 居中风格）"""
    return [_TXT_DIVIDER, f"  {title}".center(50), _TXT_DIVIDER, ""]


def _export_txt(project: ScriptProject, nodes: list, summary: Dict[str, Any]) -> str:
    lines = [f"《{project.title}》", f"类型：{project.script_type}", ""]
    if project.concept:
        lines += [f"创意概念：{project.concept}", ""]

    # —— 剧本简介 ——
    intro = (summary.get("故事简介") or "").strip()
    if intro:
        lines += _txt_section_header("剧本简介")
        lines.append(intro)
        lines.append("")

    # —— 人物小传 ——
    bios = summary.get("人物小传") or []
    valid_bios = [b for b in bios if isinstance(b, dict) and (b.get("姓名") or "").strip()]
    if valid_bios:
        lines += _txt_section_header("人物小传")
        for bio in valid_bios:
            lines.append(f"【{bio.get('姓名', '').strip()}】")
            for key, label in _BIO_FIELD_LABELS:
                val = (bio.get(key) or "").strip()
                if val:
                    lines.append(f"  {label}：{val}")
            lines.append("")

    # —— 正文 ——
    lines += _txt_section_header("正文")

    def render(node, depth=0):
        indent = "  " * depth
        if node.title:
            lines.append(f"{indent}【{node.node_type}】{node.title}")
        else:
            lines.append(f"{indent}【{node.node_type}】")
        if node.speaker:
            lines.append(f"{indent}  {node.speaker}：")
        if node.content:
            lines.append(f"{indent}  {node.content}")
        if node.visual_desc:
            lines.append(f"{indent}  [视觉] {node.visual_desc}")
        lines.append("")
        for child in sorted(
            [n for n in nodes if n.parent_id == node.id], key=lambda x: x.sort_order
        ):
            render(child, depth + 1)

    for root in [n for n in nodes if not n.parent_id]:
        render(root)

    return "\n".join(lines)


def _export_markdown(project: ScriptProject, nodes: list, summary: Dict[str, Any]) -> str:
    lines = [f"# 《{project.title}》", f"**类型：**{project.script_type}", ""]
    if project.concept:
        lines += [f"**创意概念：**{project.concept}", ""]
    lines.append("---")
    lines.append("")

    # —— 剧本简介 ——
    intro = (summary.get("故事简介") or "").strip()
    if intro:
        lines += ["## 剧本简介", "", intro, ""]

    # —— 人物小传 ——
    bios = summary.get("人物小传") or []
    valid_bios = [b for b in bios if isinstance(b, dict) and (b.get("姓名") or "").strip()]
    if valid_bios:
        lines += ["## 主要人物小传", ""]
        for bio in valid_bios:
            lines.append(f"### {bio.get('姓名', '').strip()}")
            for key, label in _BIO_FIELD_LABELS:
                val = (bio.get(key) or "").strip()
                if val:
                    lines.append(f"- **{label}**：{val}")
            lines.append("")

    # —— 正文 ——
    lines += ["## 正文", ""]

    heading_map = {
        "episode": "###",
        "scene": "####",
        "section": "###",
        "intro": "###",
    }

    def render(node, depth=0):
        heading = heading_map.get(node.node_type, "#####")
        label = node.title or f"（{node.node_type}）"
        lines.append(f"{heading} {label}")
        if node.speaker:
            lines.append(f"**{node.speaker}：**")
        if node.content:
            lines.append(f"{node.content}")
        if node.visual_desc:
            lines.append(f"> *[视觉描述] {node.visual_desc}*")
        lines.append("")
        for child in sorted(
            [n for n in nodes if n.parent_id == node.id], key=lambda x: x.sort_order
        ):
            render(child, depth + 1)

    for root in [n for n in nodes if not n.parent_id]:
        render(root)

    return "\n".join(lines)


# ── Node Version History ──


@router.get("/{id}/nodes/{node_id}/versions", response_model=List[NodeVersionResponse])
async def list_node_versions(
    node_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """查询节点版本历史列表（含 content，最多 20 条）"""
    result = await db.execute(
        select(ScriptNodeVersion)
        .where(ScriptNodeVersion.node_id == node_id)
        .order_by(ScriptNodeVersion.version_number.desc())
    )
    return result.scalars().all()


@router.post("/{id}/nodes/{node_id}/versions", response_model=NodeVersionResponse)
async def create_node_version(
    node_id: int,
    body: CreateVersionRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """手动创建节点版本快照"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Episode 节点不存在")

    version = await _create_node_version(db, node, body.source)
    await db.commit()
    await db.refresh(version)
    return version


@router.post("/{id}/nodes/{node_id}/versions/{version_id}/restore", response_model=NodeVersionResponse)
async def restore_node_version(
    node_id: int,
    version_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """恢复到指定版本（恢复前自动创建当前内容的快照）"""
    node_result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
            ScriptNode.node_type == "episode",
        )
    )
    node = node_result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="Episode 节点不存在")

    ver_result = await db.execute(
        select(ScriptNodeVersion).where(
            ScriptNodeVersion.id == version_id,
            ScriptNodeVersion.node_id == node_id,
        )
    )
    target = ver_result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="版本不存在")

    pre_restore = await _create_node_version(db, node, "manual")
    node.title = target.title
    node.content = target.content
    await db.commit()
    await db.refresh(pre_restore)
    return pre_restore
