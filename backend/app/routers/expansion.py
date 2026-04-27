"""
扩写模块路由
Project CRUD + Segment CRUD + AI SSE 接口
"""
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.user import User
from app.models.expansion_project import ExpansionProject
from app.models.expansion_segment import ExpansionSegment
from app.models.project import Project as NovelProject
from app.models.script_project import ScriptProject as DramaProject
from app.models.script_node import ScriptNode
from app.routers.auth import get_current_user
from app.schemas.expansion import (
    ConvertRequest,
    ExpandSegmentRequest,
    ExpansionProjectCreate,
    ExpansionProjectListResponse,
    ExpansionProjectResponse,
    ExpansionProjectUpdate,
    ExpansionSegmentResponse,
    ExpansionSegmentUpdate,
    ImportFromDramaRequest,
    ImportFromNovelRequest,
    SegmentMergeRequest,
    SegmentReorderRequest,
    SegmentSplitRequest,
)
from app.schemas.drama import ReorderRequest
from app.services.expansion_ai_service import ExpansionAIService
from app.services.file_parser import FileParser
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/expansion", tags=["expansion"])

# ─── Helpers ──────────────────────────────────────────────────────────────────


class ExpandRequest(BaseModel):
    """批量扩写请求"""
    segment_ids: Optional[List[int]] = None
    instructions: Optional[str] = None


async def get_expansion_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpansionProject:
    """获取扩写项目（带认证）"""
    result = await db.execute(
        select(ExpansionProject).where(
            ExpansionProject.id == id,
            or_(
                ExpansionProject.user_id == current_user.id,
                current_user.is_superuser == True,
            ),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="扩写项目不存在或无权访问")
    return project


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


@router.post("/", response_model=ExpansionProjectResponse, status_code=201)
async def create_project(
    body: ExpansionProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建扩写项目（手动输入文本）"""
    project = ExpansionProject(
        user_id=current_user.id,
        title=body.title,
        source_type=body.source_type,
        original_text=body.original_text,
        word_count=len(body.original_text),
        source_ref=body.source_ref,
        expansion_level=body.expansion_level,
        target_word_count=body.target_word_count,
        style_instructions=body.style_instructions,
        ai_config=body.ai_config.model_dump() if body.ai_config else None,
        execution_mode=body.execution_mode,
        metadata_=body.metadata_,
        status="created",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/upload", response_model=ExpansionProjectResponse, status_code=201)
async def upload_project(
    title: Optional[str] = Query(None, max_length=200),
    expansion_level: str = Query("medium", pattern="^(light|medium|deep)$"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传文件创建扩写项目（支持 txt/markdown/docx）"""
    content = await file.read()
    filename = file.filename.lower()

    # 如果没有提供标题，使用文件名
    if not title:
        title = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename

    try:
        if filename.endswith(".txt"):
            result = FileParser.parse_txt(content)
        elif filename.endswith(".md") or filename.endswith(".markdown"):
            result = FileParser.parse_markdown(content)
        elif filename.endswith(".docx"):
            result = FileParser.parse_docx(content)
        else:
            raise HTTPException(status_code=400, detail="不支持的文件格式，请上传 .txt/.md/.docx 文件")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    project = ExpansionProject(
        user_id=current_user.id,
        title=title,
        source_type="upload",
        original_text=result.text,
        word_count=result.word_count,
        expansion_level=expansion_level,
        source_ref={"filename": file.filename},
        status="created",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/import/novel", response_model=ExpansionProjectResponse, status_code=201)
async def import_from_novel(
    body: ImportFromNovelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从小说项目导入文本"""
    # 验证小说项目存在且属于当前用户
    result = await db.execute(
        select(NovelProject).where(
            NovelProject.id == body.project_id,
            or_(
                NovelProject.owner_id == current_user.id,
                current_user.is_superuser == True,
            ),
        )
    )
    novel_project = result.scalar_one_or_none()
    if not novel_project:
        raise HTTPException(status_code=404, detail="小说项目不存在或无权访问")

    # 获取章节内容
    chapter_query = select(NovelProject).where(NovelProject.id == body.project_id)
    if body.chapter_ids:
        # 如果有指定章节 ID，需要查询 chapters 表
        from app.models.chapter import Chapter
        chapters_result = await db.execute(
            select(Chapter)
            .where(
                Chapter.id.in_(body.chapter_ids),
                Chapter.project_id == body.project_id,
            )
            .order_by(Chapter.sort_order)
        )
        chapters = chapters_result.scalars().all()
        text_parts = [f"第{c.sort_order}章 {c.title}\n\n{c.content}" for c in chapters if c.content]
        combined_text = "\n\n".join(text_parts)
    else:
        # 导入所有章节
        from app.models.chapter import Chapter
        all_chapters = await db.execute(
            select(Chapter)
            .where(Chapter.project_id == body.project_id)
            .order_by(Chapter.sort_order)
        )
        chapters = all_chapters.scalars().all()
        text_parts = [f"第{c.sort_order}章 {c.title}\n\n{c.content}" for c in chapters if c.content]
        combined_text = "\n\n".join(text_parts)

    if not combined_text:
        raise HTTPException(status_code=400, detail="小说项目没有内容可导入")

    project = ExpansionProject(
        user_id=current_user.id,
        title=body.title,
        source_type="novel",
        original_text=combined_text,
        word_count=len(combined_text),
        source_ref={"project_id": body.project_id, "chapter_ids": body.chapter_ids},
        expansion_level=body.expansion_level,
        ai_config=body.ai_config.model_dump() if body.ai_config else None,
        execution_mode=body.execution_mode,
        status="created",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/import/drama", response_model=ExpansionProjectResponse, status_code=201)
async def import_from_drama(
    body: ImportFromDramaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从剧本项目导入文本"""
    # 验证剧本项目存在且属于当前用户
    result = await db.execute(
        select(DramaProject).where(
            DramaProject.id == body.project_id,
            or_(
                DramaProject.user_id == current_user.id,
                current_user.is_superuser == True,
            ),
        )
    )
    drama_project = result.scalar_one_or_none()
    if not drama_project:
        raise HTTPException(status_code=404, detail="剧本项目不存在或无权访问")

    # 获取所有节点内容
    nodes_result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == body.project_id)
        .order_by(ScriptNode.sort_order)
    )
    nodes = nodes_result.scalars().all()

    if not nodes:
        raise HTTPException(status_code=400, detail="剧本项目没有内容可导入")

    text_parts = []
    for node in nodes:
        parts = []
        if node.title:
            parts.append(f"【{node.node_type}】{node.title}")
        if node.speaker:
            parts.append(f"{node.speaker}:")
        if node.content:
            parts.append(node.content)
        if node.visual_desc:
            parts.append(f"[视觉] {node.visual_desc}")
        text_parts.append("\n".join(parts))

    combined_text = "\n\n".join(text_parts)

    project = ExpansionProject(
        user_id=current_user.id,
        title=body.title,
        source_type="drama",
        original_text=combined_text,
        word_count=len(combined_text),
        source_ref={"project_id": body.project_id},
        expansion_level=body.expansion_level,
        ai_config=body.ai_config.model_dump() if body.ai_config else None,
        execution_mode=body.execution_mode,
        status="created",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/", response_model=ExpansionProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出扩写项目（分页，可按来源/状态过滤）"""
    filters = [
        or_(
            ExpansionProject.user_id == current_user.id,
            current_user.is_superuser == True,
        )
    ]
    if source_type:
        filters.append(ExpansionProject.source_type == source_type)
    if status:
        filters.append(ExpansionProject.status == status)

    count_result = await db.execute(
        select(func.count()).select_from(ExpansionProject).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ExpansionProject)
        .where(*filters)
        .order_by(ExpansionProject.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = result.scalars().all()

    return ExpansionProjectListResponse(
        items=list(items),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}", response_model=ExpansionProjectResponse)
async def get_project(
    project: ExpansionProject = Depends(get_expansion_project),
):
    """获取扩写项目详情"""
    return project


@router.put("/{id}", response_model=ExpansionProjectResponse)
async def update_project(
    body: ExpansionProjectUpdate,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """更新扩写项目"""
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
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """删除扩写项目（级联删除分段）"""
    await db.delete(project)
    await db.commit()


# ─── Analysis Helpers ─────────────────────────────────────────────────────────


def _extract_json_from_response(text: str) -> Optional[Dict[str, Any]]:
    """从 AI 响应中提取 JSON 对象"""
    json_text = text.strip()
    # 移除可能的 markdown 代码块标记
    if json_text.startswith("```"):
        first_newline = json_text.find("\n")
        if first_newline != -1:
            json_text = json_text[first_newline + 1:]
        if json_text.endswith("```"):
            json_text = json_text[:-3].strip()

    start_idx = json_text.find("{")
    end_idx = json_text.rfind("}") + 1
    if start_idx != -1 and end_idx > start_idx:
        return json.loads(json_text[start_idx:end_idx])
    return None


async def _create_segments_from_breakpoints(
    db: AsyncSession,
    project: ExpansionProject,
    breakpoints: List[Dict[str, Any]],
) -> int:
    """
    两阶段分段 - 阶段2：用本地算法根据断点创建分段记录。
    返回创建的分段数量。
    """
    # 删除旧分段
    await db.execute(
        delete(ExpansionSegment).where(
            ExpansionSegment.project_id == project.id
        )
    )

    original_text = project.original_text
    computed = ExpansionAIService.compute_segments_from_breakpoints(
        original_text, breakpoints
    )

    for idx, seg_info in enumerate(computed):
        start = seg_info["start"]
        end = seg_info["end"]
        original_content = original_text[start:end]

        segment = ExpansionSegment(
            project_id=project.id,
            sort_order=idx,
            title=seg_info.get("title"),
            original_content=original_content,
            original_word_count=len(original_content),
            status="pending",
        )
        db.add(segment)

    # 重新查询项目对象（SSE 长时间流后原对象可能已脱离 session）
    result = await db.execute(
        select(ExpansionProject).where(ExpansionProject.id == project.id)
    )
    fresh_project = result.scalar_one_or_none()
    if fresh_project:
        fresh_project.status = "segmented"
        logger.info(f"[_create_segments] Setting project {project.id} status to 'segmented'")
    await db.commit()
    logger.info(f"[_create_segments] Committed transaction for project {project.id}")
    return len(computed)


# ─── Analysis (SSE) ───────────────────────────────────────────────────────────



@router.post("/{id}/analyze")
async def analyze_project(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """
    两阶段智能分段（SSE 流式）：
    阶段1 - AI 识别自然断点（流式返回）
    阶段2 - 本地算法根据断点 + 字数约束计算最优分段
    """
    ai_service = ExpansionAIService(project.ai_config)

    MAX_ANALYSIS_CHARS = 10000
    analysis_text = project.original_text
    if len(analysis_text) > MAX_ANALYSIS_CHARS:
        analysis_text = analysis_text[:MAX_ANALYSIS_CHARS]

    async def stream():
        # 阶段1：AI 识别断点
        logger.info(f"[ANALYZE] Starting analysis for project {project.id}, text length: {len(analysis_text)}")
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'identifying_breakpoints', 'message': '正在识别自然断点...'})}\n\n"

        full_response = ""
        try:
            logger.info(f"Calling AI analyze_text for project {project.id}")
            async for chunk in ai_service.analyze_text(analysis_text):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"AI analyze stream error: {e}", exc_info=True)
            logger.info(f"AI analyze_text completed for project {project.id}, response length: {len(full_response)}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 调用失败: {str(e)}'})}\n\n"
            return

        if not full_response:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 未返回有效结果'})}\n\n"
            return

        # 解析 AI 返回的 JSON
        try:
            analysis = _extract_json_from_response(full_response)
            if not analysis:
                yield f"data: {json.dumps({'type': 'error', 'message': '无法解析 AI 返回的 JSON'})}\n\n"
                return

            # 更新项目摘要和文风画像
            summary = analysis.get("summary", "")
            style_profile = analysis.get("style_profile", {})
            breakpoints = analysis.get("breakpoints", [])

            # 兼容旧格式：如果返回的是 segment_suggestions 而不是 breakpoints
            if not breakpoints and analysis.get("segment_suggestions"):
                for seg in analysis["segment_suggestions"]:
                    breakpoints.append({
                        "anchor_text": seg.get("start_text", ""),
                        "type": "段落结束",
                        "strength": 2,
                        "label": seg.get("title", ""),
                    })

            if summary or style_profile:
                update_result = await db.execute(
                    select(ExpansionProject).where(ExpansionProject.id == project.id)
                )
                updated_project = update_result.scalar_one_or_none()
                if updated_project:
                    updated_project.summary = summary
                    updated_project.style_profile = style_profile
                    await db.commit()

            # 阶段2：本地算法计算分段
            yield f"data: {json.dumps({'type': 'phase', 'phase': 'computing_segments', 'message': f'已识别 {len(breakpoints)} 个断点，正在计算最优分段...'})}\n\n"

            segment_count = await _create_segments_from_breakpoints(
                db, project, breakpoints
            )

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'segmentation_done', 'message': f'分段完成，共 {segment_count} 段'})}\n\n"

        except json.JSONDecodeError:
            logger.warning("Could not parse analysis JSON from AI response")
            yield f"data: {json.dumps({'type': 'error', 'message': '解析 AI 返回的 JSON 失败'})}\n\n"
        except Exception as e:
            logger.error(f"Error processing analysis result: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'处理分析结果出错: {str(e)}'})}\n\n"

        # 最后发 done 事件
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/segments/resegment")
async def resegment_segments(
    id: int,
    body: SegmentMergeRequest,  # 复用这个 schema，它有 segment_ids
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """
    对指定分段重新分段（SSE 流式）
    将选中的分段内容合并后重新分析分段
    """
    if not body.segment_ids:
        raise HTTPException(status_code=400, detail="请选择要重新分段的段落")

    # 获取选中的分段
    result = await db.execute(
        select(ExpansionSegment)
        .where(ExpansionSegment.project_id == id)
        .where(ExpansionSegment.id.in_(body.segment_ids))
        .order_by(ExpansionSegment.sort_order)
    )
    selected_segments = result.scalars().all()

    if not selected_segments:
        raise HTTPException(status_code=404, detail="未找到选中的分段")

    # 合并选中分段的内容
    combined_text = "\n\n".join(seg.original_content for seg in selected_segments)
    combined_word_count = sum(seg.original_word_count for seg in selected_segments)
    min_sort_order = min(seg.sort_order for seg in selected_segments)

    ai_service = ExpansionAIService(project.ai_config)

    MAX_ANALYSIS_CHARS = 10000
    analysis_text = combined_text
    if len(analysis_text) > MAX_ANALYSIS_CHARS:
        analysis_text = analysis_text[:MAX_ANALYSIS_CHARS]

    async def stream():
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'identifying_breakpoints', 'message': f'正在对 {len(selected_segments)} 段内容重新分段...'})}\n\n"

        full_response = ""
        try:
            async for chunk in ai_service.analyze_text(analysis_text):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"AI resegment segments stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 调用失败: {str(e)}'})}\n\n"
            return

        if not full_response:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 未返回有效结果'})}\n\n"
            return

        try:
            analysis = _extract_json_from_response(full_response)
            if not analysis:
                yield f"data: {json.dumps({'type': 'error', 'message': '无法解析 AI 返回的 JSON'})}\n\n"
                return

            breakpoints = analysis.get("breakpoints", [])

            # 兼容旧格式
            if not breakpoints and analysis.get("segment_suggestions"):
                for seg in analysis["segment_suggestions"]:
                    breakpoints.append({
                        "anchor_text": seg.get("start_text", ""),
                        "type": "段落结束",
                        "strength": 2,
                        "label": seg.get("title", ""),
                    })

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'computing_segments', 'message': f'已识别 {len(breakpoints)} 个断点，正在计算最优分段...'})}\n\n"

            # 计算新分段
            computed = ExpansionAIService.compute_segments_from_breakpoints(
                combined_text, breakpoints
            )

            # 删除原来的分段
            old_ids = [seg.id for seg in selected_segments]
            await db.execute(
                delete(ExpansionSegment).where(ExpansionSegment.id.in_(old_ids))
            )

            # 创建新分段，保持原来的排序位置
            for idx, seg_info in enumerate(computed):
                start = seg_info["start"]
                end = seg_info["end"]
                original_content = combined_text[start:end]

                segment = ExpansionSegment(
                    project_id=id,
                    sort_order=min_sort_order + idx,
                    title=seg_info.get("title"),
                    original_content=original_content,
                    original_word_count=len(original_content),
                    status="pending",
                )
                db.add(segment)

            # 更新后续分段的排序
            await db.execute(
                update(ExpansionSegment)
                .where(ExpansionSegment.project_id == id)
                .where(ExpansionSegment.sort_order >= min_sort_order + len(computed))
                .values(sort_order=ExpansionSegment.sort_order + len(computed) - len(selected_segments))
            )

            await db.commit()

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'segmentation_done', 'message': f'重新分段完成，原 {len(selected_segments)} 段拆分为 {len(computed)} 段'})}\n\n"

        except json.JSONDecodeError:
            logger.warning("Could not parse analysis JSON from AI response")
            yield f"data: {json.dumps({'type': 'error', 'message': '解析 AI 返回的 JSON 失败'})}\n\n"
        except Exception as e:
            logger.error(f"Error processing resegment segments result: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'处理重新分段结果出错: {str(e)}'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/resegment")
async def resegment_project(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """重新分段（SSE 流式），两阶段智能分段"""
    ai_service = ExpansionAIService(project.ai_config)

    MAX_ANALYSIS_CHARS = 10000
    analysis_text = project.original_text
    if len(analysis_text) > MAX_ANALYSIS_CHARS:
        analysis_text = analysis_text[:MAX_ANALYSIS_CHARS]

    async def stream():
        yield f"data: {json.dumps({'type': 'phase', 'phase': 'identifying_breakpoints', 'message': '正在重新识别自然断点...'})}\n\n"

        full_response = ""
        try:
            async for chunk in ai_service.analyze_text(analysis_text):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
        except Exception as e:
            logger.error(f"AI resegment stream error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'AI 调用失败: {str(e)}'})}\n\n"
            return

        if not full_response:
            yield f"data: {json.dumps({'type': 'error', 'message': 'AI 未返回有效结果'})}\n\n"
            return

        try:
            analysis = _extract_json_from_response(full_response)
            if not analysis:
                yield f"data: {json.dumps({'type': 'error', 'message': '无法解析 AI 返回的 JSON'})}\n\n"
                return

            # 更新摘要和文风
            summary = analysis.get("summary", "")
            style_profile = analysis.get("style_profile", {})
            breakpoints = analysis.get("breakpoints", [])

            # 兼容旧格式
            if not breakpoints and analysis.get("segment_suggestions"):
                for seg in analysis["segment_suggestions"]:
                    breakpoints.append({
                        "anchor_text": seg.get("start_text", ""),
                        "type": "段落结束",
                        "strength": 2,
                        "label": seg.get("title", ""),
                    })

            if summary or style_profile:
                project.summary = summary
                project.style_profile = style_profile

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'computing_segments', 'message': f'已识别 {len(breakpoints)} 个断点，正在计算最优分段...'})}\n\n"

            segment_count = await _create_segments_from_breakpoints(
                db, project, breakpoints
            )

            yield f"data: {json.dumps({'type': 'phase', 'phase': 'segmentation_done', 'message': f'重新分段完成，共 {segment_count} 段'})}\n\n"

        except json.JSONDecodeError:
            logger.warning("Could not parse analysis JSON from AI response")
            yield f"data: {json.dumps({'type': 'error', 'message': '解析 AI 返回的 JSON 失败'})}\n\n"
        except Exception as e:
            logger.error(f"Error processing resegment result: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'处理重新分段结果出错: {str(e)}'})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


# ─── Segment CRUD ─────────────────────────────────────────────────────────────


@router.get("/{id}/segments", response_model=List[ExpansionSegmentResponse])
async def get_segments(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """获取项目的所有分段"""
    result = await db.execute(
        select(ExpansionSegment)
        .where(ExpansionSegment.project_id == project.id)
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()
    return list(segments)


@router.put("/{id}/segments/{seg_id}", response_model=ExpansionSegmentResponse)
async def update_segment(
    seg_id: int,
    body: ExpansionSegmentUpdate,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """更新分段"""
    result = await db.execute(
        select(ExpansionSegment).where(
            ExpansionSegment.id == seg_id,
            ExpansionSegment.project_id == project.id,
        )
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="分段不存在")

    update_data = body.model_dump(exclude_unset=True, by_alias=False)
    for field, value in update_data.items():
        setattr(segment, field, value)
    await db.commit()
    await db.refresh(segment)
    return segment


@router.post("/{id}/segments/split", response_model=List[ExpansionSegmentResponse])
async def split_segment(
    body: SegmentSplitRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """拆分分段"""
    result = await db.execute(
        select(ExpansionSegment).where(
            ExpansionSegment.id == body.segment_id,
            ExpansionSegment.project_id == project.id,
        )
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="分段不存在")

    if body.split_position <= 0 or body.split_position >= len(segment.original_content):
        raise HTTPException(status_code=400, detail="拆分位置无效")

    # 创建两个新分段
    content1 = segment.original_content[:body.split_position]
    content2 = segment.original_content[body.split_position:]

    # 更新第一个分段
    segment.original_content = content1
    segment.original_word_count = len(content1)

    # 创建第二个分段
    segment2 = ExpansionSegment(
        project_id=project.id,
        sort_order=segment.sort_order + 1,
        title=segment.title,
        original_content=content2,
        original_word_count=len(content2),
        status="pending",
    )
    db.add(segment2)

    # 重新排序后续分段
    await db.execute(
        update(ExpansionSegment)
        .where(
            ExpansionSegment.project_id == project.id,
            ExpansionSegment.sort_order > segment.sort_order,
        )
        .values(sort_order=ExpansionSegment.sort_order + 1)
    )

    await db.commit()

    # 返回更新后的分段列表
    result = await db.execute(
        select(ExpansionSegment)
        .where(ExpansionSegment.project_id == project.id)
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()
    return list(segments)


@router.post("/{id}/segments/merge", response_model=ExpansionSegmentResponse)
async def merge_segments(
    body: SegmentMergeRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """合并分段"""
    result = await db.execute(
        select(ExpansionSegment)
        .where(
            ExpansionSegment.id.in_(body.segment_ids),
            ExpansionSegment.project_id == project.id,
        )
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()

    if len(segments) != len(body.segment_ids):
        raise HTTPException(status_code=404, detail="部分分段不存在")

    # 合并内容
    merged_content = "\n\n".join(s.original_content for s in segments)
    first_segment = segments[0]

    # 更新第一个分段
    first_segment.original_content = merged_content
    first_segment.original_word_count = len(merged_content)
    first_segment.title = segments[0].title  # 保留第一个标题

    # 删除其他分段
    for segment in segments[1:]:
        await db.delete(segment)

    await db.commit()
    await db.refresh(first_segment)
    return first_segment


@router.put("/{id}/segments/reorder", status_code=204)
async def reorder_segments(
    body: SegmentReorderRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """重排序分段"""
    for idx, seg_id in enumerate(body.segment_ids):
        result = await db.execute(
            select(ExpansionSegment).where(
                ExpansionSegment.id == seg_id,
                ExpansionSegment.project_id == project.id,
            )
        )
        segment = result.scalar_one_or_none()
        if segment:
            segment.sort_order = idx
    await db.commit()


# ─── Expansion (SSE) ──────────────────────────────────────────────────────────


@router.post("/{id}/expand")
async def expand_batch(
    body: ExpandRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """批量扩写分段（SSE 流式）"""
    # 乐观锁检查
    if project.status not in ["segmented", "expanding", "paused"]:
        raise HTTPException(status_code=400, detail="项目未准备好进行扩写")

    # 获取要扩写的分段
    query = select(ExpansionSegment).where(
        ExpansionSegment.project_id == project.id,
        ExpansionSegment.status.in_(["pending", "error"]),
    )
    if body.segment_ids:
        query = query.where(ExpansionSegment.id.in_(body.segment_ids))
    query = query.order_by(ExpansionSegment.sort_order)

    result = await db.execute(query)
    segments = result.scalars().all()

    if not segments:
        raise HTTPException(status_code=400, detail="没有可扩写的分段")

    # 乐观锁更新项目状态
    update_result = await db.execute(
        update(ExpansionProject)
        .where(
            ExpansionProject.id == project.id,
            ExpansionProject.version == project.version,
        )
        .values(status="expanding", version=ExpansionProject.version + 1)
    )
    if update_result.rowcount == 0:
        raise HTTPException(status_code=409, detail="并发冲突，请刷新后重试")

    ai_service = ExpansionAIService(project.ai_config)

    async def stream():
        for i, segment in enumerate(segments):
            # 获取上下文
            prev_segment = segments[i - 1] if i > 0 else None
            next_segment = segments[i + 1] if i < len(segments) - 1 else None

            prev_context = prev_segment.expanded_content if prev_segment else None
            next_context = next_segment.original_content if next_segment else None

            # 更新分段状态
            segment.status = "expanding"
            await db.commit()

            try:
                expanded_text = ""
                async for chunk in _sse_stream(
                    ai_service.expand_segment(
                        summary=project.summary or "",
                        style_profile=project.style_profile or {},
                        current_segment=segment.original_content,
                        prev_context=prev_context,
                        next_context=next_context,
                        expansion_level=segment.expansion_level or project.expansion_level,
                        target_word_count=project.target_word_count,
                        custom_instructions=segment.custom_instructions or body.instructions,
                        style_instructions=project.style_instructions,
                    )
                ):
                    try:
                        data = json.loads(chunk.removeprefix("data: ").strip())
                        if data.get("type") == "text":
                            expanded_text += data.get("text", "")
                    except Exception:
                        pass
                    yield chunk

                # 保存扩写结果
                segment.expanded_content = expanded_text
                segment.expanded_word_count = len(expanded_text)
                segment.status = "completed"
                segment.error_message = None

            except Exception as e:
                logger.error(f"Error expanding segment {segment.id}: {e}", exc_info=True)
                segment.status = "error"
                segment.error_message = str(e)
                yield f"data: {json.dumps({'type': 'error', 'segment_id': segment.id, 'message': str(e)})}\n\n"

            await db.commit()

        # 更新项目状态
        update_result = await db.execute(
            select(ExpansionProject).where(ExpansionProject.id == project.id)
        )
        updated_project = update_result.scalar_one_or_none()
        if updated_project:
            updated_project.status = "completed"
            await db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/segments/{seg_id}/expand")
async def expand_single_segment(
    seg_id: int,
    body: ExpandSegmentRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """扩写单个分段（SSE 流式）"""
    result = await db.execute(
        select(ExpansionSegment).where(
            ExpansionSegment.id == seg_id,
            ExpansionSegment.project_id == project.id,
        )
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="分段不存在")

    # 更新分段状态
    segment.status = "expanding"
    await db.commit()

    ai_service = ExpansionAIService(project.ai_config)

    async def stream():
        expanded_text = ""
        try:
            async for chunk in _sse_stream(
                ai_service.expand_segment(
                    summary=project.summary or "",
                    style_profile=project.style_profile or {},
                    current_segment=segment.original_content,
                    expansion_level=segment.expansion_level or project.expansion_level,
                    target_word_count=project.target_word_count,
                    custom_instructions=body.instructions,
                    style_instructions=project.style_instructions,
                )
            ):
                try:
                    data = json.loads(chunk.removeprefix("data: ").strip())
                    if data.get("type") == "text":
                        expanded_text += data.get("text", "")
                except Exception:
                    pass
                yield chunk

            # 重新查询分段以确保在当前会话中
            result = await db.execute(
                select(ExpansionSegment).where(ExpansionSegment.id == seg_id)
            )
            seg = result.scalar_one_or_none()
            if seg:
                seg.expanded_content = expanded_text
                seg.expanded_word_count = len(expanded_text)
                seg.status = "completed"
                seg.error_message = None

        except Exception as e:
            logger.error(f"Error expanding segment {segment.id}: {e}", exc_info=True)
            # 重新查询分段以确保在当前会话中
            result = await db.execute(
                select(ExpansionSegment).where(ExpansionSegment.id == seg_id)
            )
            seg = result.scalar_one_or_none()
            if seg:
                seg.status = "error"
                seg.error_message = str(e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        await db.commit()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/pause", response_model=ExpansionProjectResponse)
async def pause_expansion(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """暂停扩写"""
    if project.status != "expanding":
        raise HTTPException(status_code=400, detail="项目未在扩写中")

    project.status = "paused"
    await db.commit()
    await db.refresh(project)
    return project


@router.post("/{id}/resume")
async def resume_expansion(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """恢复扩写（SSE 流式）"""
    if project.status != "paused":
        raise HTTPException(status_code=400, detail="项目未暂停")

    # 乐观锁更新
    update_result = await db.execute(
        update(ExpansionProject)
        .where(
            ExpansionProject.id == project.id,
            ExpansionProject.version == project.version,
        )
        .values(status="expanding", version=ExpansionProject.version + 1)
    )
    if update_result.rowcount == 0:
        raise HTTPException(status_code=409, detail="并发冲突，请刷新后重试")

    # 获取未完成的分段
    result = await db.execute(
        select(ExpansionSegment)
        .where(
            ExpansionSegment.project_id == project.id,
            ExpansionSegment.status.in_(["pending", "error", "expanding"]),
        )
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()

    if not segments:
        raise HTTPException(status_code=400, detail="没有待完成的分段")

    ai_service = ExpansionAIService(project.ai_config)

    async def stream():
        for i, segment in enumerate(segments):
            # 获取上下文
            prev_segment = segments[i - 1] if i > 0 else None
            next_segment = segments[i + 1] if i < len(segments) - 1 else None

            prev_context = prev_segment.expanded_content if prev_segment else None
            next_context = next_segment.original_content if next_segment else None

            segment.status = "expanding"
            await db.commit()

            try:
                expanded_text = ""
                async for chunk in _sse_stream(
                    ai_service.expand_segment(
                        summary=project.summary or "",
                        style_profile=project.style_profile or {},
                        current_segment=segment.original_content,
                        prev_context=prev_context,
                        next_context=next_context,
                        expansion_level=segment.expansion_level or project.expansion_level,
                        target_word_count=project.target_word_count,
                        custom_instructions=segment.custom_instructions,
                        style_instructions=project.style_instructions,
                    )
                ):
                    try:
                        data = json.loads(chunk.removeprefix("data: ").strip())
                        if data.get("type") == "text":
                            expanded_text += data.get("text", "")
                    except Exception:
                        pass
                    yield chunk

                segment.expanded_content = expanded_text
                segment.expanded_word_count = len(expanded_text)
                segment.status = "completed"

            except Exception as e:
                logger.error(f"Error expanding segment {segment.id}: {e}", exc_info=True)
                segment.status = "error"
                segment.error_message = str(e)
                yield f"data: {json.dumps({'type': 'error', 'segment_id': segment.id, 'message': str(e)})}\n\n"

            await db.commit()

        update_result = await db.execute(
            select(ExpansionProject).where(ExpansionProject.id == project.id)
        )
        updated_project = update_result.scalar_one_or_none()
        if updated_project:
            updated_project.status = "completed"
            await db.commit()

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


@router.post("/{id}/segments/{seg_id}/retry")
async def retry_segment(
    seg_id: int,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """重试失败的分段（SSE 流式）"""
    result = await db.execute(
        select(ExpansionSegment).where(
            ExpansionSegment.id == seg_id,
            ExpansionSegment.project_id == project.id,
        )
    )
    segment = result.scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="分段不存在")

    if segment.status != "error":
        raise HTTPException(status_code=400, detail="分段状态不是错误，无需重试")

    segment.status = "expanding"
    segment.error_message = None
    await db.commit()

    ai_service = ExpansionAIService(project.ai_config)

    async def stream():
        expanded_text = ""
        try:
            async for chunk in _sse_stream(
                ai_service.expand_segment(
                    summary=project.summary or "",
                    style_profile=project.style_profile or {},
                    current_segment=segment.original_content,
                    expansion_level=segment.expansion_level or project.expansion_level,
                    target_word_count=project.target_word_count,
                    custom_instructions=segment.custom_instructions,
                    style_instructions=project.style_instructions,
                )
            ):
                try:
                    data = json.loads(chunk.removeprefix("data: ").strip())
                    if data.get("type") == "text":
                        expanded_text += data.get("text", "")
                except Exception:
                    pass
                yield chunk

            segment.expanded_content = expanded_text
            segment.expanded_word_count = len(expanded_text)
            segment.status = "completed"

        except Exception as e:
            logger.error(f"Error retrying segment {segment.id}: {e}", exc_info=True)
            segment.status = "error"
            segment.error_message = str(e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        await db.commit()
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return _sse_response(stream())


# ─── Export & Convert ─────────────────────────────────────────────────────────


@router.get("/{id}/export")
async def export_project(
    format: str = Query("txt", pattern="^(txt|markdown)$"),
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """导出扩写结果（txt 或 markdown 格式）"""
    result = await db.execute(
        select(ExpansionSegment)
        .where(ExpansionSegment.project_id == project.id)
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()

    if format == "markdown":
        content = _export_markdown(project, segments)
        media_type = "text/markdown"
        filename = f"{project.title}.md"
    else:
        content = _export_txt(project, segments)
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


def _export_txt(project: ExpansionProject, segments: List[ExpansionSegment]) -> str:
    """导出为 TXT 格式"""
    lines = [f"《{project.title}》", f"扩写级别：{project.expansion_level}", ""]
    if project.summary:
        lines += [f"摘要：{project.summary}", ""]
    lines.append("=" * 40)
    lines.append("")

    for seg in segments:
        if seg.title:
            lines.append(f"【{seg.title}】")
        if seg.expanded_content:
            lines.append(seg.expanded_content)
        else:
            lines.append(seg.original_content)
        lines.append("")

    return "\n".join(lines)


def _export_markdown(project: ExpansionProject, segments: List[ExpansionSegment]) -> str:
    """导出为 Markdown 格式"""
    lines = [f"# 《{project.title}》", f"**扩写级别：**{project.expansion_level}", ""]
    if project.summary:
        lines += [f"**摘要：**{project.summary}", ""]
    lines.append("---")
    lines.append("")

    for seg in segments:
        if seg.title:
            lines.append(f"## {seg.title}")
        if seg.expanded_content:
            lines.append(seg.expanded_content)
        else:
            lines.append(seg.original_content)
        lines.append("")

    return "\n".join(lines)


@router.post("/{id}/analyze-test")
async def analyze_project_test(
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """测试：非流式分析"""
    ai_service = ExpansionAIService(project.ai_config)
    
    MAX_ANALYSIS_CHARS = 10000
    analysis_text = project.original_text
    if len(analysis_text) > MAX_ANALYSIS_CHARS:
        analysis_text = analysis_text[:MAX_ANALYSIS_CHARS]
    
    try:
        full_response = await ai_service.analyze_text_non_stream(analysis_text)
        logger.info(f"Non-stream test response length: {len(full_response)}")
        
        analysis = _extract_json_from_response(full_response)
        if not analysis:
            return {"error": "无法解析 AI 返回的 JSON", "response_length": len(full_response), "response_preview": full_response[:500]}
        
        summary = analysis.get("summary", "")
        style_profile = analysis.get("style_profile", {})
        breakpoints = analysis.get("breakpoints", [])
        
        return {
            "success": True,
            "summary_length": len(summary),
            "breakpoints_count": len(breakpoints),
            "style_profile_keys": list(style_profile.keys()) if style_profile else [],
            "full_response_length": len(full_response),
        }
    except Exception as e:
        logger.error(f"Non-stream analyze error: {e}", exc_info=True)
        return {"error": str(e)}

@router.post("/{id}/convert", status_code=201)
async def convert_project(
    body: ConvertRequest,
    project: ExpansionProject = Depends(get_expansion_project),
    db: AsyncSession = Depends(get_db),
):
    """转换扩写结果为小说或剧本格式"""
    # 获取所有分段的扩写内容
    result = await db.execute(
        select(ExpansionSegment)
        .where(ExpansionSegment.project_id == project.id)
        .order_by(ExpansionSegment.sort_order)
    )
    segments = result.scalars().all()

    expanded_texts = [seg.expanded_content or seg.original_content for seg in segments]
    combined_text = "\n\n".join(expanded_texts)

    if body.target == "novel":
        # 创建小说项目
        from app.models.project import Project
        novel = Project(
            owner_id=project.user_id,
            title=project.title,
            description=f"由扩写项目转换而来 - {project.source_type}",
        )
        db.add(novel)
        await db.flush()

        # 创建章节
        from app.models.chapter import Chapter
        chapter = Chapter(
            project_id=novel.id,
            title="正文",
            content=combined_text,
            sort_order=1,
            word_count=len(combined_text),
        )
        db.add(chapter)

    elif body.target == "drama":
        # 创建剧本项目
        from app.models.script_project import ScriptProject
        drama = ScriptProject(
            user_id=project.user_id,
            title=project.title,
            script_type="dynamic",
            concept=f"由扩写项目转换而来 - {project.source_type}",
        )
        db.add(drama)
        await db.flush()

        # 创建节点
        from app.models.script_node import ScriptNode
        for idx, seg in enumerate(segments):
            node = ScriptNode(
                project_id=drama.id,
                node_type="scene",
                title=seg.title or f"场景{idx + 1}",
                content=seg.expanded_content or seg.original_content,
                sort_order=idx,
            )
            db.add(node)

    await db.commit()

    return {"status": "success", "target": body.target, "message": f"已转换为{body.target}格式"}
