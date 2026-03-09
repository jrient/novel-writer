"""
AI 路由
处理 AI 写作辅助的 SSE 流式请求
"""
import asyncio

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.reference import ReferenceNovel
from app.schemas.ai import AIGenerateRequest, AIConfigResponse, BatchGenerateRequest
from app.services.ai_service import AIService, PROMPTS

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/ai",
    tags=["ai"],
)


@router.post("/generate")
async def ai_generate(
    project_id: int,
    payload: AIGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 流式生成内容
    返回 SSE (Server-Sent Events) 流
    """
    # 验证项目存在
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 获取上下文：角色和世界观
    chars_result = await db.execute(
        select(Character).where(Character.project_id == project_id).limit(10)
    )
    characters = [
        {"name": c.name, "role_type": c.role_type, "personality": c.personality_traits or ""}
        for c in chars_result.scalars().all()
    ]

    world_result = await db.execute(
        select(WorldbuildingEntry).where(WorldbuildingEntry.project_id == project_id).limit(10)
    )
    worldbuilding = [
        {"name": w.title, "description": w.content or "", "category": w.category}
        for w in world_result.scalars().all()
    ]

    # 如果指定了章节，获取章节内容作为补充
    content = payload.content
    if payload.chapter_id and not content:
        chapter_result = await db.execute(
            select(Chapter).where(
                Chapter.id == payload.chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        if chapter:
            content = chapter.content or ""

    return StreamingResponse(
        AIService.generate_stream(
            action=payload.action,
            content=content,
            provider=payload.provider,
            title=project.title,
            genre=project.genre or "",
            description=project.description or "",
            question=payload.question or "",
            characters=characters,
            worldbuilding=worldbuilding,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/batch-generate")
async def batch_generate(
    project_id: int,
    payload: BatchGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 批量生成前 X 章
    SSE 流式返回：outline -> chapter(逐章) -> done
    """
    import json as _json

    # 验证项目存在
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 获取角色和世界观
    chars_result = await db.execute(
        select(Character).where(Character.project_id == project_id).limit(10)
    )
    characters = [
        {"name": c.name, "role_type": c.role_type, "personality": c.personality_traits or ""}
        for c in chars_result.scalars().all()
    ]

    world_result = await db.execute(
        select(WorldbuildingEntry).where(WorldbuildingEntry.project_id == project_id).limit(10)
    )
    worldbuilding = [
        {"name": w.title, "description": w.content or "", "category": w.category}
        for w in world_result.scalars().all()
    ]

    context = AIService._get_context_text(characters, worldbuilding)

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

    # 获取知识库
    knowledge_reference = ""
    if payload.use_knowledge:
        query_text = f"{project.title} {project.genre or ''} {project.description or ''}"
        knowledge_reference = await _retrieve_knowledge(db, query_text, limit=5)

    title = project.title or ""
    genre = project.genre or ""
    description = project.description or ""

    async def event_stream():
        try:
            # 步骤一：生成大纲
            outline_prompt = PROMPTS["batch_outline"].format(
                chapter_count=payload.chapter_count,
                title=title,
                genre=genre,
                description=description,
                context=context,
                style_reference=style_reference,
                knowledge_reference=knowledge_reference,
            )

            yield f"data: {_json.dumps({'type': 'progress', 'message': '正在生成大纲...'}, ensure_ascii=False)}\n\n"

            # 带心跳的大纲生成，防止长时间无输出导致 Nginx 超时
            outline_raw = None
            gen_task = asyncio.create_task(AIService.generate_text(outline_prompt))
            while not gen_task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
                except asyncio.TimeoutError:
                    yield f": heartbeat\n\n"
            outline_raw = gen_task.result()

            # 发送大纲文本
            yield f"data: {_json.dumps({'type': 'outline', 'text': outline_raw}, ensure_ascii=False)}\n\n"

            # 解析大纲 JSON
            # 尝试从响应中提取 JSON 数组
            outline_data = None
            try:
                outline_data = _json.loads(outline_raw)
            except _json.JSONDecodeError:
                # 尝试从文本中提取 JSON
                import re
                json_match = re.search(r'\[.*\]', outline_raw, re.DOTALL)
                if json_match:
                    try:
                        outline_data = _json.loads(json_match.group())
                    except _json.JSONDecodeError:
                        pass

            if not outline_data or not isinstance(outline_data, list):
                # 降级：生成默认大纲
                outline_data = [
                    {"chapter": i + 1, "title": f"第{i + 1}章", "summary": f"第{i + 1}章内容"}
                    for i in range(payload.chapter_count)
                ]

            # 截取到请求的章节数
            outline_data = outline_data[:payload.chapter_count]

            # 构建完整大纲文本（供后续章节生成参考）
            outline_text = "\n".join(
                f"第{item.get('chapter', i+1)}章「{item.get('title', '')}」：{item.get('summary', '')}"
                for i, item in enumerate(outline_data)
            )

            # 获取已有章节数以确定 sort_order
            existing_count_result = await db.execute(
                select(Chapter).where(Chapter.project_id == project_id)
            )
            existing_chapters = existing_count_result.scalars().all()
            max_sort_order = max((ch.sort_order for ch in existing_chapters), default=0)

            # 步骤二：逐章生成
            previous_summary = ""
            previous_ending = ""
            for i, chapter_info in enumerate(outline_data):
                chapter_index = i + 1
                chapter_title = chapter_info.get("title", f"第{chapter_index}章")
                chapter_summary = chapter_info.get("summary", "")

                yield f"data: {_json.dumps({'type': 'progress', 'message': f'正在生成第 {chapter_index}/{len(outline_data)} 章：{chapter_title}'}, ensure_ascii=False)}\n\n"

                prev_text = f"前一章摘要：{previous_summary}" if previous_summary else "这是小说的第一章。"
                prev_ending_text = f"上一章结尾内容：\n{previous_ending}" if previous_ending else ""

                chapter_prompt = PROMPTS["batch_chapter"].format(
                    chapter_index=chapter_index,
                    words_per_chapter=payload.words_per_chapter,
                    title=title,
                    genre=genre,
                    description=description,
                    context=context,
                    style_reference=style_reference,
                    knowledge_reference=knowledge_reference,
                    outline_text=outline_text,
                    chapter_title=chapter_title,
                    chapter_summary=chapter_summary,
                    previous_summary=prev_text,
                    previous_ending=prev_ending_text,
                )

                # 流式生成章节内容
                chapter_content = ""
                provider = AIService._get_available_provider()

                if provider == "demo":
                    # 演示模式
                    demo_text = f"　　这是第{chapter_index}章「{chapter_title}」的内容。\n\n　　{chapter_summary}\n\n　　故事在这里展开，角色们面临新的挑战和机遇。随着情节的推进，一切都在向着不可预知的方向发展。每一个选择都将影响未来的走路，而命运的齿轮已经开始转动。\n\n　　这一章的故事就此告一段落，但更精彩的内容还在后面等待着读者。"
                    import asyncio
                    # 模拟逐块输出
                    chunk_size = 20
                    for ci in range(0, len(demo_text), chunk_size):
                        chunk = demo_text[ci:ci + chunk_size]
                        chapter_content += chunk
                        yield f"data: {_json.dumps({'type': 'chapter_stream', 'chapter_index': chapter_index, 'title': chapter_title, 'text': chunk}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.05)
                else:
                    # 真实 AI 流式生成
                    if provider == "openai":
                        stream_gen = AIService._stream_openai(chapter_prompt)
                    elif provider == "anthropic":
                        stream_gen = AIService._stream_anthropic(chapter_prompt)
                    else:
                        stream_gen = AIService._stream_ollama(chapter_prompt)

                    async for sse_line in stream_gen:
                        if sse_line.startswith("data: "):
                            try:
                                payload_data = _json.loads(sse_line[6:].strip())
                                if payload_data.get("text"):
                                    chapter_content += payload_data["text"]
                                    yield f"data: {_json.dumps({'type': 'chapter_stream', 'chapter_index': chapter_index, 'title': chapter_title, 'text': payload_data['text']}, ensure_ascii=False)}\n\n"
                                if payload_data.get("error"):
                                    yield f"data: {_json.dumps({'type': 'error', 'message': payload_data['error']}, ensure_ascii=False)}\n\n"
                                    return
                            except _json.JSONDecodeError:
                                pass

                # 保存章节到数据库
                new_chapter = Chapter(
                    project_id=project_id,
                    title=f"第{chapter_index}章 {chapter_title}",
                    content=chapter_content,
                    sort_order=max_sort_order + chapter_index,
                    word_count=len(chapter_content),
                    status="draft",
                )
                db.add(new_chapter)
                await db.commit()
                await db.refresh(new_chapter)

                # 发送章节完成事件
                yield f"data: {_json.dumps({'type': 'chapter_done', 'chapter_index': chapter_index, 'title': chapter_title, 'chapter_id': new_chapter.id, 'word_count': len(chapter_content)}, ensure_ascii=False)}\n\n"

                # 记录摘要和结尾供下一章参考
                previous_summary = chapter_summary or chapter_content[:200]
                previous_ending = chapter_content[-800:] if chapter_content else ""

            # 更新项目总字数
            all_chapters_result = await db.execute(
                select(Chapter).where(Chapter.project_id == project_id)
            )
            total_words = sum(ch.word_count for ch in all_chapters_result.scalars().all())
            project.current_word_count = total_words
            await db.commit()

            # 完成
            yield f"data: {_json.dumps({'type': 'done', 'total_chapters': len(outline_data), 'total_words': total_words}, ensure_ascii=False)}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 独立路由（不依赖项目）
config_router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@config_router.get("/config", response_model=AIConfigResponse)
async def get_ai_config():
    """获取 AI 配置信息"""
    available = []
    models = {}

    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("sk-xxx", "", None):
        available.append("openai")
        models["openai"] = settings.OPENAI_MODEL

    if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None):
        available.append("anthropic")
        models["anthropic"] = settings.ANTHROPIC_MODEL

    available.append("ollama")
    models["ollama"] = settings.OLLAMA_MODEL

    # 演示模式始终可用
    available.append("demo")
    models["demo"] = "built-in"

    # 如果没有真实 provider 可用，默认使用 demo
    from app.services.ai_service import AIService
    actual_default = AIService._get_available_provider(settings.DEFAULT_AI_PROVIDER)

    return AIConfigResponse(
        default_provider=actual_default,
        available_providers=available,
        models=models,
    )


async def _retrieve_knowledge(db: AsyncSession, content: str, limit: int = 3) -> str:
    """检索相关知识"""
    from app.services.embedding import embedding_service
    from sqlalchemy import text
    
    if not content or len(content) < 10:
        return ""
    
    try:
        # 生成查询向量
        query_embedding = await embedding_service.generate_embedding(content[:500])
        
        # 搜索相关知识（reference_id < 0 表示知识条目）
        sql = """
            SELECT content, chapter_title
            FROM novel_chunks
            WHERE reference_id < 0 AND embedding IS NOT NULL
            ORDER BY embedding <=> :query_embedding
            LIMIT :limit
        """
        result = await db.execute(
            text(sql),
            {"query_embedding": str(query_embedding), "limit": limit}
        )
        rows = result.fetchall()
        
        if not rows:
            return ""
        
        knowledge_text = "\n\n相关知识参考：\n"
        for i, row in enumerate(rows, 1):
            knowledge_text += f"{i}. {row[1]}: {row[0][:200]}...\n"
        
        return knowledge_text
    except Exception:
        return ""
