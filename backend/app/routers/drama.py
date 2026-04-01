"""
剧本生成模块路由
Project CRUD + Node CRUD + Session CRUD + AI SSE 接口
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.script_node import ScriptNode
from app.models.script_project import ScriptProject
from app.models.script_session import ScriptSession
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.drama import (
    DYNAMIC_NODE_TYPES,
    EXPLANATORY_NODE_TYPES,
    ExpandEpisodeRequest,
    ExpandNodeRequest,
    GlobalDirectiveRequest,
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
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/drama", tags=["drama"])

# ─── Helpers ──────────────────────────────────────────────────────────────────


class AIConfigUpdate(BaseModel):
    """AI 配置更新请求（drama router 本地定义）"""
    ai_config: Optional[Dict[str, Any]] = None


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

    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        full_response = ""
        async for chunk in _sse_stream(
            ai_service.generate_question(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=history,
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
    ai_service = ScriptAIService(project.ai_config)

    summary = await ai_service.generate_summary(
        script_type=project.script_type,
        title=project.title,
        concept=project.concept,
        history=history,
    )

    session.summary = summary
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

    # 读取目标集数（仅动态漫有效）
    episode_count = 20
    if project.script_type == "dynamic" and session.summary:
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
    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_outline(
                script_type=project.script_type,
                title=project.title,
                concept=project.concept,
                history=history,
                episode_count=episode_count,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
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
    """展开单集为详细场景（SSE 流式）"""
    if project.script_type != "dynamic":
        raise HTTPException(status_code=400, detail="仅动态漫支持逐集展开")

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
    if idx < 0 or idx >= len(sections):
        raise HTTPException(status_code=400, detail=f"集索引 {idx} 超出范围（共 {len(sections)} 集）")

    current_ep = sections[idx]
    prev_ep = sections[idx - 1] if idx > 0 else None
    next_ep = sections[idx + 1] if idx < len(sections) - 1 else None
    total = len(sections)

    summary_data = session.summary or {}
    main_characters = summary_data.get("主要角色", [])
    core_conflict = summary_data.get("核心冲突", "")
    style_tone = summary_data.get("风格基调", "")
    outline_summary = session.outline_draft.get("summary", "")

    ai_service = ScriptAIService(project.ai_config)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.expand_episode(
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
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"expand_episode stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if full_response:
            try:
                json_str = full_response.strip()
                start_idx = json_str.find('{')
                end_idx = json_str.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    json_str = json_str[start_idx:end_idx + 1]
                result_json = json.loads(json_str)
                children = result_json.get("children", [])

                # 写回 outline_draft
                update_result = await db.execute(
                    select(ScriptSession).where(ScriptSession.project_id == project.id)
                )
                updated_session = update_result.scalar_one_or_none()
                if updated_session and updated_session.outline_draft:
                    import copy
                    new_draft = copy.deepcopy(updated_session.outline_draft)
                    new_sections = new_draft.get("sections", [])
                    if idx < len(new_sections):
                        new_sections[idx]["children"] = children
                        new_draft["sections"] = new_sections
                        updated_session.outline_draft = new_draft
                        await db.commit()
                        logger.info(f"Episode {idx} expanded with {len(children)} scenes for project {project.id}")
            except json.JSONDecodeError as e:
                logger.warning(f"Could not parse expand_episode JSON: {e}")
                yield f"data: {json.dumps({'type': 'error', 'message': '场景生成解析失败，请重试'})}\n\n"
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
    ai_service = ScriptAIService(project.ai_config)

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
    ai_service = ScriptAIService(project.ai_config)

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
    """导出剧本（txt 或 markdown 格式）"""
    nodes_result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = nodes_result.scalars().all()

    if format == "markdown":
        content = _export_markdown(project, all_nodes)
        media_type = "text/markdown"
        filename = f"{project.title}.md"
    else:
        content = _export_txt(project, all_nodes)
        media_type = "text/plain"
        filename = f"{project.title}.txt"

    from fastapi.responses import Response

    return Response(
        content=content.encode("utf-8"),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _export_txt(project: ScriptProject, nodes: list) -> str:
    lines = [f"《{project.title}》", f"类型：{project.script_type}", ""]
    if project.concept:
        lines += [f"创意概念：{project.concept}", ""]
    lines.append("=" * 40)
    lines.append("")

    node_map = {n.id: n for n in nodes}
    roots = [n for n in nodes if not n.parent_id]

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

    for root in roots:
        render(root)

    return "\n".join(lines)


def _export_markdown(project: ScriptProject, nodes: list) -> str:
    lines = [f"# 《{project.title}》", f"**类型：**{project.script_type}", ""]
    if project.concept:
        lines += [f"**创意概念：**{project.concept}", ""]
    lines.append("---")
    lines.append("")

    heading_map = {
        "episode": "##",
        "scene": "###",
        "section": "##",
        "intro": "##",
    }

    roots = [n for n in nodes if not n.parent_id]

    def render(node, depth=0):
        heading = heading_map.get(node.node_type, "####")
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

    for root in roots:
        render(root)

    return "\n".join(lines)
