"""
向导路由
处理创作向导的 SSE 流式请求和项目创建
"""
import asyncio
import json
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.outline import OutlineNode
from app.models.reference import ReferenceNovel
from app.schemas.wizard import (
    WizardGenerateRequest,
    WizardOutlineRequest,
    WizardCharactersRequest,
    WizardCreateRequest,
    WizardCreateResponse,
    ChapterOutlineItem,
    CharacterOutlineItem,
    # 新的数据结构
    MapNode,
    PartNode,
    NoteItem,
    WizardMapsRequest,
    WizardPartsRequest,
    WizardCharactersForPartRequest,
    WizardCreateV2Request,
)
from app.services.ai_service import AIService, PROMPTS

router = APIRouter(
    prefix="/api/v1/wizard",
    tags=["wizard"],
)


def _extract_json_array(text: str, marker: str) -> list:
    """从文本中提取 JSON 数组，支持多种格式"""
    # 尝试找到标记后的内容
    marker_pos = text.find(marker)
    if marker_pos == -1:
        return []

    after_marker = text[marker_pos + len(marker):].strip()

    # 方法1: 找到完整的 JSON 数组（从 [ 到匹配的 ]）
    if after_marker.startswith('['):
        bracket_count = 0
        for i, char in enumerate(after_marker):
            if char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
                if bracket_count == 0:
                    # 找到匹配的结束括号
                    json_str = after_marker[:i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        break

    # 方法2: 正则匹配（后备方案）
    json_match = re.search(r'\[[\s\S]*?\]', after_marker)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return []


@router.post("/generate")
async def wizard_generate(
    payload: WizardGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向导生成：AI 生成大纲和角色（SSE 流式）
    返回类型：
    - type: outline - 大纲 JSON
    - type: characters - 角色 JSON
    - type: done - 完成
    """
    # 获取参考小说风格
    style_reference = ""
    if payload.reference_ids:
        ref_result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id.in_(payload.reference_ids))
        )
        refs = ref_result.scalars().all()
        style_parts = []
        for ref in refs:
            parts = []
            if ref.writing_style:
                parts.append(f"文风特征：{ref.writing_style}")
            if ref.analysis:
                parts.append(f"分析：{ref.analysis[:500]}")
            if parts:
                style_parts.append(f"参考《{ref.title}》：\n" + "\n".join(parts))
        if style_parts:
            style_reference = "风格参考：\n" + "\n\n".join(style_parts)

    async def event_stream():
        try:
            # 判断是生成还是修改
            is_revision = bool(payload.revision_request and payload.current_outline)

            if is_revision:
                # 修改模式：使用修改 prompt
                import json as json_module
                current_outline_str = json_module.dumps(
                    [item.model_dump() for item in payload.current_outline],
                    ensure_ascii=False, indent=2
                )
                current_characters_str = json_module.dumps(
                    [item.model_dump() for item in payload.current_characters] if payload.current_characters else [],
                    ensure_ascii=False, indent=2
                )
                prompt = PROMPTS["wizard_revision"].format(
                    title=payload.title,
                    genre=payload.genre or "未指定",
                    description=payload.description,
                    target_word_count=payload.target_word_count,
                    chapter_count=payload.chapter_count,
                    style_reference=style_reference or "无",
                    current_outline=current_outline_str,
                    current_characters=current_characters_str,
                    revision_request=payload.revision_request,
                )
            else:
                # 生成模式
                prompt = PROMPTS["wizard_outline_characters"].format(
                    title=payload.title,
                    genre=payload.genre or "未指定",
                    description=payload.description,
                    target_word_count=payload.target_word_count,
                    chapter_count=payload.chapter_count,
                    style_reference=style_reference,
                )

            # 发送开始事件
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成大纲和角色设定...'}, ensure_ascii=False)}\n\n"

            # 生成内容（带心跳防止超时）
            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=8000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            # 使用改进的 JSON 提取方法
            outline_data = _extract_json_array(raw_content, "===OUTLINE===")
            characters_data = _extract_json_array(raw_content, "===CHARACTERS===")

            # 如果解析失败，生成默认大纲
            if not outline_data:
                outline_data = [
                    {"chapter": i + 1, "title": f"第{i + 1}章", "summary": f"第{i + 1}章内容"}
                    for i in range(payload.chapter_count)
                ]

            # 截取到请求的章节数
            outline_data = outline_data[:payload.chapter_count]

            # 发送大纲
            yield f"data: {json.dumps({'type': 'outline', 'data': outline_data}, ensure_ascii=False)}\n\n"

            # 如果没有角色，生成默认主角
            if not characters_data:
                characters_data = [
                    {
                        "name": "主角",
                        "role_type": "protagonist",
                        "gender": "男",
                        "age": "青年",
                        "occupation": "未知",
                        "personality_traits": "勇敢、善良",
                        "appearance": "相貌平平",
                        "background": "来历神秘",
                    }
                ]

            # 发送角色
            yield f"data: {json.dumps({'type': 'characters', 'data': characters_data}, ensure_ascii=False)}\n\n"

            # 完成
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ 新的向导接口（地图-部分-章节层级） ============

@router.post("/generate-maps")
async def wizard_generate_maps(
    payload: WizardMapsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤2：生成地图大纲（SSE 流式）
    返回类型：
    - type: maps - 地图 JSON
    - type: done - 完成
    """
    # 获取参考小说风格
    style_reference = ""
    if payload.reference_ids:
        ref_result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id.in_(payload.reference_ids))
        )
        refs = ref_result.scalars().all()
        style_parts = []
        for ref in refs:
            parts = []
            if ref.writing_style:
                parts.append(f"文风特征：{ref.writing_style}")
            if ref.analysis:
                parts.append(f"分析：{ref.analysis[:500]}")
            if parts:
                style_parts.append(f"参考《{ref.title}》：\n" + "\n".join(parts))
        if style_parts:
            style_reference = "风格参考：\n" + "\n\n".join(style_parts)

    async def event_stream():
        try:
            prompt = PROMPTS["wizard_maps"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                style_reference=style_reference or "无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成地图大纲...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            maps_data = _extract_json_array(raw_content, "===MAPS===")

            if not maps_data:
                maps_data = [
                    {"name": "起始之地", "description": "故事开始的地方"},
                    {"name": "未知领域", "description": "等待探索的神秘之地"},
                ]

            # 分配 ID
            for i, m in enumerate(maps_data):
                m["id"] = i + 1

            yield f"data: {json.dumps({'type': 'maps', 'data': maps_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-parts")
async def wizard_generate_parts(
    payload: WizardPartsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤3：为地图生成部分（SSE 流式）
    返回类型：
    - type: parts - 部分 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            prompt = PROMPTS["wizard_parts"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                map_name=payload.map_name,
                map_description="",
                style_reference="无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': f'正在为「{payload.map_name}」生成部分...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            parts_data = _extract_json_array(raw_content, "===PARTS===")

            if not parts_data:
                parts_data = [
                    {"name": "开端", "summary": "故事的开始", "chapter_count": 3},
                    {"name": "发展", "summary": "故事的发展", "chapter_count": 3},
                ]

            # 分配 ID 和空的章节数组
            for i, p in enumerate(parts_data):
                p["id"] = i + 1
                p["chapters"] = []
                p["character_ids"] = []

            yield f"data: {json.dumps({'type': 'parts', 'data': parts_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-characters-for-part")
async def wizard_generate_characters_for_part(
    payload: WizardCharactersForPartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤4：为部分生成角色（SSE 流式）
    返回类型：
    - type: characters - 角色 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            # 构建大纲文本
            outline_parts = []
            for part in payload.parts:
                outline_parts.append(f"{part.name}: {part.summary or ''}")
                for ch in part.chapters:
                    outline_parts.append(f"  - 第{ch.chapter}章 {ch.title}: {ch.summary}")
            outline_str = "\n".join(outline_parts)

            # 构建已有角色文本
            existing_chars_str = "无"
            if payload.existing_characters:
                char_lines = []
                for c in payload.existing_characters:
                    char_lines.append(f"- {c.name} ({c.role_type})")
                existing_chars_str = "\n".join(char_lines)

            prompt = PROMPTS["wizard_characters_for_part"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                outline=outline_str,
                existing_characters=existing_chars_str,
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成角色...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            characters_data = _extract_json_array(raw_content, "===CHARACTERS===")

            if not characters_data:
                characters_data = [
                    {
                        "name": "主角",
                        "role_type": "protagonist",
                        "gender": "未知",
                        "age": "青年",
                        "occupation": "未知",
                        "personality_traits": "勇敢、善良",
                        "appearance": "相貌平平",
                        "background": "来历神秘",
                        "is_new": True,
                    }
                ]

            yield f"data: {json.dumps({'type': 'characters', 'data': characters_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/create-v2", response_model=WizardCreateResponse)
async def wizard_create_v2(
    payload: WizardCreateV2Request,
    db: AsyncSession = Depends(get_db),
):
    """
    向导创建项目（新版本）：根据确认的地图结构和角色创建项目
    """
    try:
        from app.models.note import Note

        # 生成大纲文本
        outline_text = ""
        for map_item in payload.maps:
            outline_text += f"【{map_item.name}】\n"
            if map_item.description:
                outline_text += f"{map_item.description}\n"
            for part in map_item.parts:
                outline_text += f"\n  {part.name}\n"
                if part.summary:
                    outline_text += f"  {part.summary}\n"
                for ch in part.chapters:
                    outline_text += f"    第{ch.chapter}章 {ch.title}: {ch.summary}\n"
            outline_text += "\n"

        # 创建项目
        new_project = Project(
            title=payload.title,
            description=payload.description,
            genre=payload.genre,
            target_word_count=0,
            current_word_count=0,
            status="draft",
            outline=outline_text,
            maps=[m.model_dump() for m in payload.maps],
        )
        db.add(new_project)
        await db.flush()

        # 创建章节
        chapter_counter = 1
        for map_item in payload.maps:
            for part in map_item.parts:
                for ch in part.chapters:
                    new_chapter = Chapter(
                        project_id=new_project.id,
                        title=f"第{ch.chapter}章 {ch.title}",
                        content="",
                        sort_order=chapter_counter,
                        word_count=0,
                        status="draft",
                    )
                    db.add(new_chapter)
                    chapter_counter += 1

        # 创建角色
        for char_item in payload.characters:
            new_char = Character(
                project_id=new_project.id,
                name=char_item.name,
                role_type=char_item.role_type,
                gender=char_item.gender,
                age=char_item.age,
                occupation=char_item.occupation,
                personality_traits=char_item.personality_traits,
                appearance=char_item.appearance,
                background=char_item.background,
            )
            db.add(new_char)

        # 创建笔记（如果有）
        if payload.notes:
            for i, note_item in enumerate(payload.notes):
                new_note = Note(
                    project_id=new_project.id,
                    note_type=note_item.note_type,
                    title=note_item.title,
                    content=note_item.content,
                    related_chapter_ids=note_item.related_chapter_ids or [],
                    status=note_item.status or "active",
                    sort_order=i,
                )
                db.add(new_note)

        await db.commit()
        await db.refresh(new_project)

        return WizardCreateResponse(
            project_id=new_project.id,
            message="项目创建成功",
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.post("/create", response_model=WizardCreateResponse)
async def wizard_create(
    payload: WizardCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向导创建项目：根据确认的大纲和角色创建项目
    """
    try:
        # 生成大纲文本（用于大纲页面显示）
        outline_text = payload.outline_text
        if not outline_text and payload.outline:
            outline_text = "\n".join([
                f"第{item.chapter}章 {item.title}\n{item.summary}"
                for item in payload.outline
            ])

        # 创建项目
        new_project = Project(
            title=payload.title,
            description=payload.description,
            genre=payload.genre,
            target_word_count=payload.target_word_count,
            current_word_count=0,
            status="draft",
            outline=outline_text,  # 保存大纲到大纲页面
        )
        db.add(new_project)
        await db.flush()  # 获取 project_id

        # 创建章节
        for i, chapter_item in enumerate(payload.outline):
            new_chapter = Chapter(
                project_id=new_project.id,
                title=f"第{chapter_item.chapter}章 {chapter_item.title}",
                content="",
                sort_order=i + 1,
                word_count=0,
                status="draft",
            )
            db.add(new_chapter)

        # 创建角色
        for char_item in payload.characters:
            new_char = Character(
                project_id=new_project.id,
                name=char_item.name,
                role_type=char_item.role_type,
                gender=char_item.gender,
                age=char_item.age,
                occupation=char_item.occupation,
                personality_traits=char_item.personality_traits,
                appearance=char_item.appearance,
                background=char_item.background,
            )
            db.add(new_char)

        # 创建大纲节点（保留兼容性）
        for i, chapter_item in enumerate(payload.outline):
            outline_node = OutlineNode(
                project_id=new_project.id,
                title=chapter_item.title,
                content=chapter_item.summary,
                node_type="chapter",
                sort_order=i + 1,
            )
            db.add(outline_node)

        await db.commit()
        await db.refresh(new_project)

        return WizardCreateResponse(
            project_id=new_project.id,
            message="项目创建成功",
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.post("/generate-outline")
async def wizard_generate_outline(
    payload: WizardOutlineRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向导生成大纲（SSE 流式）
    只生成大纲，不生成角色
    返回类型：
    - type: outline - 大纲 JSON
    - type: done - 完成
    """
    # 获取参考小说风格
    style_reference = ""
    if payload.reference_ids:
        ref_result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id.in_(payload.reference_ids))
        )
        refs = ref_result.scalars().all()
        style_parts = []
        for ref in refs:
            parts = []
            if ref.writing_style:
                parts.append(f"文风特征：{ref.writing_style}")
            if ref.analysis:
                parts.append(f"分析：{ref.analysis[:500]}")
            if parts:
                style_parts.append(f"参考《{ref.title}》：\n" + "\n".join(parts))
        if style_parts:
            style_reference = "风格参考：\n" + "\n\n".join(style_parts)

    async def event_stream():
        try:
            # 判断是生成还是修改
            is_revision = bool(payload.revision_request and payload.current_outline)

            if is_revision:
                # 修改模式
                import json as json_module
                current_outline_str = json_module.dumps(
                    [item.model_dump() for item in payload.current_outline],
                    ensure_ascii=False, indent=2
                )
                prompt = PROMPTS["wizard_outline_only"].format(
                    title=payload.title,
                    genre=payload.genre or "未指定",
                    description=payload.description,
                    target_word_count=payload.target_word_count,
                    chapter_count=payload.chapter_count,
                    style_reference=style_reference or "无",
                ) + f"\n\n当前大纲：\n{current_outline_str}\n\n用户修改意见：\n{payload.revision_request}"
            else:
                # 生成模式
                prompt = PROMPTS["wizard_outline_only"].format(
                    title=payload.title,
                    genre=payload.genre or "未指定",
                    description=payload.description,
                    target_word_count=payload.target_word_count,
                    chapter_count=payload.chapter_count,
                    style_reference=style_reference,
                )

            # 发送开始事件
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成大纲...'}, ensure_ascii=False)}\n\n"

            # 生成内容（带心跳防止超时）
            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=6000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            # 提取大纲 JSON
            outline_data = _extract_json_array(raw_content, "===OUTLINE===")

            # 如果解析失败，生成默认大纲
            if not outline_data:
                outline_data = [
                    {"chapter": i + 1, "title": f"第{i + 1}章", "summary": f"第{i + 1}章内容"}
                    for i in range(payload.chapter_count)
                ]

            # 截取到请求的章节数
            outline_data = outline_data[:payload.chapter_count]

            # 发送大纲
            yield f"data: {json.dumps({'type': 'outline', 'data': outline_data}, ensure_ascii=False)}\n\n"

            # 完成
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ 新的向导接口（地图-部分-章节层级） ============

@router.post("/generate-maps")
async def wizard_generate_maps(
    payload: WizardMapsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤2：生成地图大纲（SSE 流式）
    返回类型：
    - type: maps - 地图 JSON
    - type: done - 完成
    """
    # 获取参考小说风格
    style_reference = ""
    if payload.reference_ids:
        ref_result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id.in_(payload.reference_ids))
        )
        refs = ref_result.scalars().all()
        style_parts = []
        for ref in refs:
            parts = []
            if ref.writing_style:
                parts.append(f"文风特征：{ref.writing_style}")
            if ref.analysis:
                parts.append(f"分析：{ref.analysis[:500]}")
            if parts:
                style_parts.append(f"参考《{ref.title}》：\n" + "\n".join(parts))
        if style_parts:
            style_reference = "风格参考：\n" + "\n\n".join(style_parts)

    async def event_stream():
        try:
            prompt = PROMPTS["wizard_maps"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                style_reference=style_reference or "无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成地图大纲...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            maps_data = _extract_json_array(raw_content, "===MAPS===")

            if not maps_data:
                maps_data = [
                    {"name": "起始之地", "description": "故事开始的地方"},
                    {"name": "未知领域", "description": "等待探索的神秘之地"},
                ]

            # 分配 ID
            for i, m in enumerate(maps_data):
                m["id"] = i + 1

            yield f"data: {json.dumps({'type': 'maps', 'data': maps_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-parts")
async def wizard_generate_parts(
    payload: WizardPartsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤3：为地图生成部分（SSE 流式）
    返回类型：
    - type: parts - 部分 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            prompt = PROMPTS["wizard_parts"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                map_name=payload.map_name,
                map_description="",
                style_reference="无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': f'正在为「{payload.map_name}」生成部分...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            parts_data = _extract_json_array(raw_content, "===PARTS===")

            if not parts_data:
                parts_data = [
                    {"name": "开端", "summary": "故事的开始", "chapter_count": 3},
                    {"name": "发展", "summary": "故事的发展", "chapter_count": 3},
                ]

            # 分配 ID 和空的章节数组
            for i, p in enumerate(parts_data):
                p["id"] = i + 1
                p["chapters"] = []
                p["character_ids"] = []

            yield f"data: {json.dumps({'type': 'parts', 'data': parts_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-characters-for-part")
async def wizard_generate_characters_for_part(
    payload: WizardCharactersForPartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤4：为部分生成角色（SSE 流式）
    返回类型：
    - type: characters - 角色 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            # 构建大纲文本
            outline_parts = []
            for part in payload.parts:
                outline_parts.append(f"{part.name}: {part.summary or ''}")
                for ch in part.chapters:
                    outline_parts.append(f"  - 第{ch.chapter}章 {ch.title}: {ch.summary}")
            outline_str = "\n".join(outline_parts)

            # 构建已有角色文本
            existing_chars_str = "无"
            if payload.existing_characters:
                char_lines = []
                for c in payload.existing_characters:
                    char_lines.append(f"- {c.name} ({c.role_type})")
                existing_chars_str = "\n".join(char_lines)

            prompt = PROMPTS["wizard_characters_for_part"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                outline=outline_str,
                existing_characters=existing_chars_str,
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成角色...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            characters_data = _extract_json_array(raw_content, "===CHARACTERS===")

            if not characters_data:
                characters_data = [
                    {
                        "name": "主角",
                        "role_type": "protagonist",
                        "gender": "未知",
                        "age": "青年",
                        "occupation": "未知",
                        "personality_traits": "勇敢、善良",
                        "appearance": "相貌平平",
                        "background": "来历神秘",
                        "is_new": True,
                    }
                ]

            yield f"data: {json.dumps({'type': 'characters', 'data': characters_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/create-v2", response_model=WizardCreateResponse)
async def wizard_create_v2(
    payload: WizardCreateV2Request,
    db: AsyncSession = Depends(get_db),
):
    """
    向导创建项目（新版本）：根据确认的地图结构和角色创建项目
    """
    try:
        from app.models.note import Note

        # 生成大纲文本
        outline_text = ""
        for map_item in payload.maps:
            outline_text += f"【{map_item.name}】\n"
            if map_item.description:
                outline_text += f"{map_item.description}\n"
            for part in map_item.parts:
                outline_text += f"\n  {part.name}\n"
                if part.summary:
                    outline_text += f"  {part.summary}\n"
                for ch in part.chapters:
                    outline_text += f"    第{ch.chapter}章 {ch.title}: {ch.summary}\n"
            outline_text += "\n"

        # 创建项目
        new_project = Project(
            title=payload.title,
            description=payload.description,
            genre=payload.genre,
            target_word_count=0,
            current_word_count=0,
            status="draft",
            outline=outline_text,
            maps=[m.model_dump() for m in payload.maps],
        )
        db.add(new_project)
        await db.flush()

        # 创建章节
        chapter_counter = 1
        for map_item in payload.maps:
            for part in map_item.parts:
                for ch in part.chapters:
                    new_chapter = Chapter(
                        project_id=new_project.id,
                        title=f"第{ch.chapter}章 {ch.title}",
                        content="",
                        sort_order=chapter_counter,
                        word_count=0,
                        status="draft",
                    )
                    db.add(new_chapter)
                    chapter_counter += 1

        # 创建角色
        for char_item in payload.characters:
            new_char = Character(
                project_id=new_project.id,
                name=char_item.name,
                role_type=char_item.role_type,
                gender=char_item.gender,
                age=char_item.age,
                occupation=char_item.occupation,
                personality_traits=char_item.personality_traits,
                appearance=char_item.appearance,
                background=char_item.background,
            )
            db.add(new_char)

        # 创建笔记（如果有）
        if payload.notes:
            for i, note_item in enumerate(payload.notes):
                new_note = Note(
                    project_id=new_project.id,
                    note_type=note_item.note_type,
                    title=note_item.title,
                    content=note_item.content,
                    related_chapter_ids=note_item.related_chapter_ids or [],
                    status=note_item.status or "active",
                    sort_order=i,
                )
                db.add(new_note)

        await db.commit()
        await db.refresh(new_project)

        return WizardCreateResponse(
            project_id=new_project.id,
            message="项目创建成功",
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.post("/generate-characters")
async def wizard_generate_characters(
    payload: WizardCharactersRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向导生成角色（SSE 流式）
    基于已确认的大纲生成角色
    返回类型：
    - type: characters - 角色 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            # 构建大纲文本
            import json as json_module
            outline_str = json_module.dumps(
                [item.model_dump() for item in payload.outline],
                ensure_ascii=False, indent=2
            )

            prompt = PROMPTS["wizard_characters_from_outline"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                outline=outline_str,
            )

            # 发送开始事件
            yield f"data: {json.dumps({'type': 'progress', 'message': '正在根据大纲生成角色...'}, ensure_ascii=False)}\n\n"

            # 生成内容（带心跳防止超时）
            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            # 提取角色 JSON
            characters_data = _extract_json_array(raw_content, "===CHARACTERS===")

            # 如果解析失败，生成默认主角
            if not characters_data:
                characters_data = [
                    {
                        "name": "主角",
                        "role_type": "protagonist",
                        "gender": "男",
                        "age": "青年",
                        "occupation": "未知",
                        "personality_traits": "勇敢、善良",
                        "appearance": "相貌平平",
                        "background": "来历神秘",
                    }
                ]

            # 发送角色
            yield f"data: {json.dumps({'type': 'characters', 'data': characters_data}, ensure_ascii=False)}\n\n"

            # 完成
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ============ 新的向导接口（地图-部分-章节层级） ============

@router.post("/generate-maps")
async def wizard_generate_maps(
    payload: WizardMapsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤2：生成地图大纲（SSE 流式）
    返回类型：
    - type: maps - 地图 JSON
    - type: done - 完成
    """
    # 获取参考小说风格
    style_reference = ""
    if payload.reference_ids:
        ref_result = await db.execute(
            select(ReferenceNovel).where(ReferenceNovel.id.in_(payload.reference_ids))
        )
        refs = ref_result.scalars().all()
        style_parts = []
        for ref in refs:
            parts = []
            if ref.writing_style:
                parts.append(f"文风特征：{ref.writing_style}")
            if ref.analysis:
                parts.append(f"分析：{ref.analysis[:500]}")
            if parts:
                style_parts.append(f"参考《{ref.title}》：\n" + "\n".join(parts))
        if style_parts:
            style_reference = "风格参考：\n" + "\n\n".join(style_parts)

    async def event_stream():
        try:
            prompt = PROMPTS["wizard_maps"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                style_reference=style_reference or "无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成地图大纲...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            maps_data = _extract_json_array(raw_content, "===MAPS===")

            if not maps_data:
                maps_data = [
                    {"name": "起始之地", "description": "故事开始的地方"},
                    {"name": "未知领域", "description": "等待探索的神秘之地"},
                ]

            # 分配 ID
            for i, m in enumerate(maps_data):
                m["id"] = i + 1

            yield f"data: {json.dumps({'type': 'maps', 'data': maps_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-parts")
async def wizard_generate_parts(
    payload: WizardPartsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤3：为地图生成部分（SSE 流式）
    返回类型：
    - type: parts - 部分 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            prompt = PROMPTS["wizard_parts"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                map_name=payload.map_name,
                map_description="",
                style_reference="无",
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': f'正在为「{payload.map_name}」生成部分...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            parts_data = _extract_json_array(raw_content, "===PARTS===")

            if not parts_data:
                parts_data = [
                    {"name": "开端", "summary": "故事的开始", "chapter_count": 3},
                    {"name": "发展", "summary": "故事的发展", "chapter_count": 3},
                ]

            # 分配 ID 和空的章节数组
            for i, p in enumerate(parts_data):
                p["id"] = i + 1
                p["chapters"] = []
                p["character_ids"] = []

            yield f"data: {json.dumps({'type': 'parts', 'data': parts_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/generate-characters-for-part")
async def wizard_generate_characters_for_part(
    payload: WizardCharactersForPartRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    步骤4：为部分生成角色（SSE 流式）
    返回类型：
    - type: characters - 角色 JSON
    - type: done - 完成
    """
    async def event_stream():
        try:
            # 构建大纲文本
            outline_parts = []
            for part in payload.parts:
                outline_parts.append(f"{part.name}: {part.summary or ''}")
                for ch in part.chapters:
                    outline_parts.append(f"  - 第{ch.chapter}章 {ch.title}: {ch.summary}")
            outline_str = "\n".join(outline_parts)

            # 构建已有角色文本
            existing_chars_str = "无"
            if payload.existing_characters:
                char_lines = []
                for c in payload.existing_characters:
                    char_lines.append(f"- {c.name} ({c.role_type})")
                existing_chars_str = "\n".join(char_lines)

            prompt = PROMPTS["wizard_characters_for_part"].format(
                title=payload.title,
                genre=payload.genre or "未指定",
                description=payload.description,
                outline=outline_str,
                existing_characters=existing_chars_str,
            )

            yield f"data: {json.dumps({'type': 'progress', 'message': '正在生成角色...'}, ensure_ascii=False)}\n\n"

            raw_content = None
            gen_task = asyncio.create_task(AIService.generate_text(prompt, max_tokens=4000))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            raw_content = gen_task.result()

            characters_data = _extract_json_array(raw_content, "===CHARACTERS===")

            if not characters_data:
                characters_data = [
                    {
                        "name": "主角",
                        "role_type": "protagonist",
                        "gender": "未知",
                        "age": "青年",
                        "occupation": "未知",
                        "personality_traits": "勇敢、善良",
                        "appearance": "相貌平平",
                        "background": "来历神秘",
                        "is_new": True,
                    }
                ]

            yield f"data: {json.dumps({'type': 'characters', 'data': characters_data}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/create-v2", response_model=WizardCreateResponse)
async def wizard_create_v2(
    payload: WizardCreateV2Request,
    db: AsyncSession = Depends(get_db),
):
    """
    向导创建项目（新版本）：根据确认的地图结构和角色创建项目
    """
    try:
        from app.models.note import Note

        # 生成大纲文本
        outline_text = ""
        for map_item in payload.maps:
            outline_text += f"【{map_item.name}】\n"
            if map_item.description:
                outline_text += f"{map_item.description}\n"
            for part in map_item.parts:
                outline_text += f"\n  {part.name}\n"
                if part.summary:
                    outline_text += f"  {part.summary}\n"
                for ch in part.chapters:
                    outline_text += f"    第{ch.chapter}章 {ch.title}: {ch.summary}\n"
            outline_text += "\n"

        # 创建项目
        new_project = Project(
            title=payload.title,
            description=payload.description,
            genre=payload.genre,
            target_word_count=0,
            current_word_count=0,
            status="draft",
            outline=outline_text,
            maps=[m.model_dump() for m in payload.maps],
        )
        db.add(new_project)
        await db.flush()

        # 创建章节
        chapter_counter = 1
        for map_item in payload.maps:
            for part in map_item.parts:
                for ch in part.chapters:
                    new_chapter = Chapter(
                        project_id=new_project.id,
                        title=f"第{ch.chapter}章 {ch.title}",
                        content="",
                        sort_order=chapter_counter,
                        word_count=0,
                        status="draft",
                    )
                    db.add(new_chapter)
                    chapter_counter += 1

        # 创建角色
        for char_item in payload.characters:
            new_char = Character(
                project_id=new_project.id,
                name=char_item.name,
                role_type=char_item.role_type,
                gender=char_item.gender,
                age=char_item.age,
                occupation=char_item.occupation,
                personality_traits=char_item.personality_traits,
                appearance=char_item.appearance,
                background=char_item.background,
            )
            db.add(new_char)

        # 创建笔记（如果有）
        if payload.notes:
            for i, note_item in enumerate(payload.notes):
                new_note = Note(
                    project_id=new_project.id,
                    note_type=note_item.note_type,
                    title=note_item.title,
                    content=note_item.content,
                    related_chapter_ids=note_item.related_chapter_ids or [],
                    status=note_item.status or "active",
                    sort_order=i,
                )
                db.add(new_note)

        await db.commit()
        await db.refresh(new_project)

        return WizardCreateResponse(
            project_id=new_project.id,
            message="项目创建成功",
        )

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")