"""
笔记路由
处理妙记和其他笔记类型的 CRUD 操作
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.note import Note
from app.models.project import Project
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.outline import OutlineNode
from app.models.event import StoryEvent
from app.schemas.note import (
    NoteCreate, NoteUpdate, NoteResponse,
    MiaojiParseRequest, MiaojiParseResult
)
from app.services.ai_service import AIService

router = APIRouter(prefix="/notes", tags=["notes"])
logger = logging.getLogger(__name__)


async def _get_project_or_404(project_id: int, db: AsyncSession) -> Project:
    """获取项目或返回404"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/", response_model=List[NoteResponse])
async def list_notes(
    project_id: int,
    note_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    """获取笔记列表"""
    await _get_project_or_404(project_id, db)

    query = select(Note).where(Note.project_id == project_id)
    if note_type:
        query = query.where(Note.note_type == note_type)
    query = query.order_by(Note.created_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=NoteResponse)
async def create_note(
    project_id: int,
    payload: NoteCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建笔记"""
    await _get_project_or_404(project_id, db)

    note = Note(
        project_id=project_id,
        title=payload.title,
        content=payload.content,
        note_type=payload.note_type,
        status=payload.status,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    project_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取单个笔记"""
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    project_id: int,
    note_id: int,
    payload: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新笔记"""
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(note, key, value)

    await db.commit()
    await db.refresh(note)
    return note


@router.delete("/{note_id}")
async def delete_note(
    project_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除笔记"""
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")

    await db.delete(note)
    await db.commit()
    return {"message": "删除成功"}


@router.post("/miaoji/quick", response_model=NoteResponse)
async def quick_miaoji(
    project_id: int,
    content: str,
    db: AsyncSession = Depends(get_db),
):
    """快速创建妙记（自动生成标题）"""
    await _get_project_or_404(project_id, db)

    # 从内容生成标题（取前20个字符）
    title = content[:20] + "..." if len(content) > 20 else content

    note = Note(
        project_id=project_id,
        title=title,
        content=content,
        note_type="miaoji",
        status="active",
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


@router.post("/{note_id}/parse", response_model=MiaojiParseResult)
async def parse_miaoji(
    project_id: int,
    note_id: int,
    db: AsyncSession = Depends(get_db),
):
    """解析妙记内容，AI自动分类并创建对应记录"""
    result = await db.execute(
        select(Note).where(Note.id == note_id, Note.project_id == project_id)
    )
    note = result.scalar_one_or_none()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")

    if note.note_type != "miaoji":
        raise HTTPException(status_code=400, detail="只能解析妙记类型的笔记")

    # 调用 AI 解析
    parse_result = await _parse_miaoji_content(note.content or "", project_id, db)

    return parse_result


async def _parse_miaoji_content(content: str, project_id: int, db: AsyncSession) -> MiaojiParseResult:
    """AI 解析妙记内容"""
    prompt = f"""你是一位专业的小说策划和编辑。请分析以下创作笔记内容，将其分类整理为角色、设定、大纲和事件。

笔记内容：
{content}

请严格按以下 JSON 格式输出（不要输出其他任何内容）：
{{
  "characters": [
    {{"name": "角色名", "role_type": "protagonist/antagonist/supporting/minor", "gender": "性别", "age": "年龄", "occupation": "职业", "personality_traits": "性格特点", "appearance": "外貌描写", "background": "背景故事"}}
  ],
  "worldbuilding": [
    {{"name": "设定名称", "category": "geography/culture/magic/technology/history/other", "description": "详细描述"}}
  ],
  "outline": [
    {{"title": "章节标题", "summary": "章节概要", "sort_order": 章节序号}}
  ],
  "events": [
    {{"title": "事件标题", "description": "事件描述", "event_type": "main/subplot/foreshadowing", "importance": 1-5}}
  ],
  "summary": "本次解析的简要总结"
}}

要求：
1. 只提取笔记中明确提到的内容，不要虚构
2. 角色类型：protagonist(主角)、antagonist(反派)、supporting(配角)、minor(次要)
3. 设定类型：geography(地理)、culture(文化)、magic(魔法)、technology(科技)、history(历史)、other(其他)
4. 事件类型：main(主线)、subplot(支线)、foreshadowing(伏笔)
5. 如果某类内容为空，返回空数组
"""

    try:
        ai_response = await AIService.generate_text(prompt, max_tokens=4000)

        # 解析 JSON
        import json
        # 提取 JSON 部分
        json_start = ai_response.find('{')
        json_end = ai_response.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            json_str = ai_response[json_start:json_end]
            data = json.loads(json_str)

            result = MiaojiParseResult(
                characters=data.get("characters", []),
                worldbuilding=data.get("worldbuilding", []),
                outline=data.get("outline", []),
                events=data.get("events", []),
                summary=data.get("summary", ""),
            )

            # 创建对应的记录
            await _create_parsed_records(result, project_id, db)

            return result
        else:
            raise ValueError("AI 响应格式错误")

    except Exception as e:
        logger.error(f"解析妙记失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")


async def _create_parsed_records(result: MiaojiParseResult, project_id: int, db: AsyncSession):
    """根据解析结果创建对应记录"""
    # 创建角色
    for char_data in result.characters:
        char = Character(
            project_id=project_id,
            name=char_data.get("name", "未命名"),
            role_type=char_data.get("role_type", "supporting"),
            gender=char_data.get("gender"),
            age=char_data.get("age"),
            occupation=char_data.get("occupation"),
            personality_traits=char_data.get("personality_traits"),
            appearance=char_data.get("appearance"),
            background=char_data.get("background"),
        )
        db.add(char)

    # 创建设定
    for world_data in result.worldbuilding:
        world = WorldbuildingEntry(
            project_id=project_id,
            name=world_data.get("name", "未命名"),
            category=world_data.get("category", "other"),
            description=world_data.get("description"),
        )
        db.add(world)

    # 创建大纲
    for outline_data in result.outline:
        outline = OutlineNode(
            project_id=project_id,
            title=outline_data.get("title", "未命名"),
            content=outline_data.get("summary"),
            node_type="chapter",
            sort_order=outline_data.get("sort_order", 0),
        )
        db.add(outline)

    # 创建事件
    for event_data in result.events:
        event = StoryEvent(
            project_id=project_id,
            title=event_data.get("title", "未命名"),
            description=event_data.get("description"),
            event_type=event_data.get("event_type", "main"),
            importance=event_data.get("importance", 3),
        )
        db.add(event)

    await db.commit()