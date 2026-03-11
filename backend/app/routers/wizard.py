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
    WizardCreateRequest,
    WizardCreateResponse,
    ChapterOutlineItem,
    CharacterOutlineItem,
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
            # 构建生成 prompt
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


@router.post("/create", response_model=WizardCreateResponse)
async def wizard_create(
    payload: WizardCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    向导创建项目：根据确认的大纲和角色创建项目
    """
    try:
        # 创建项目
        new_project = Project(
            title=payload.title,
            description=payload.description,
            genre=payload.genre,
            target_word_count=payload.target_word_count,
            current_word_count=0,
            status="draft",
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

        # 创建大纲节点
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