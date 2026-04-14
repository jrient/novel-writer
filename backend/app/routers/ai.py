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
from app.core.dependencies import get_project_with_auth
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.outline import OutlineNode
from app.models.reference import ReferenceNovel
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.ai import AIGenerateRequest, AIConfigResponse, BatchGenerateRequest, ContextPreviewResponse, ContextEntity
from app.services.ai_service import AIService, PROMPTS
from app.services.smart_context import SmartContextService
from app.services.token_usage_service import log_token_usage, estimate_tokens

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/ai",
    tags=["ai"],
)


@router.post("/generate")
async def ai_generate(
    project_id: int,
    payload: AIGenerateRequest,
    project: Project = Depends(get_project_with_auth),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI 流式生成内容
    返回 SSE (Server-Sent Events) 流
    """
    import json as _json

    # 使用智能上下文服务获取相关角色、世界观、事件等
    smart_context = SmartContextService(db, project_id)

    # 如果指定了章节，获取章节内容
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

    # extract_characters: 从选定章节提取角色，特殊处理
    if payload.action == "extract_characters":
        # 获取指定章节或全部章节
        chapter_query = select(Chapter).where(
            Chapter.project_id == project_id
        ).order_by(Chapter.sort_order)
        if payload.chapter_ids:
            chapter_query = select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.id.in_(payload.chapter_ids),
            ).order_by(Chapter.sort_order)
        all_chapters_result = await db.execute(chapter_query)
        all_chapters = all_chapters_result.scalars().all()
        chapters_text_parts = []
        for ch in all_chapters:
            if ch.content and ch.content.strip():
                chapters_text_parts.append(f"【{ch.title}】\n{ch.content}")
        chapters_text = "\n\n---\n\n".join(chapters_text_parts)

        if not chapters_text.strip():
            async def empty_stream():
                yield f"data: {_json.dumps({'error': '项目中没有章节内容，无法提取角色'}, ensure_ascii=False)}\n\n"
                yield f"data: {_json.dumps({'done': True})}\n\n"
            return StreamingResponse(
                empty_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )

        # 获取已有角色名列表
        existing_chars_result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        existing_chars = existing_chars_result.scalars().all()
        existing_names = [c.name for c in existing_chars]
        existing_characters_str = "、".join(existing_names) if existing_names else "（无）"

        # 截断章节内容以适配上下文窗口
        max_content_len = 15000
        if len(chapters_text) > max_content_len:
            chapters_text = chapters_text[:max_content_len] + "\n\n...（内容过长，已截断）"

        # 直接构建 prompt 并使用流式生成
        from app.services.ai_service import PROMPTS as _PROMPTS
        extract_prompt = _PROMPTS["extract_characters"].format(
            existing_characters=existing_characters_str,
            content=chapters_text,
        )

        actual_provider = AIService._get_available_provider(payload.provider)
        provider_model_map = {
            "openai": settings.OPENAI_MODEL,
            "anthropic": settings.ANTHROPIC_MODEL,
            "ollama": settings.OLLAMA_MODEL,
            "demo": "demo",
        }
        actual_model = provider_model_map.get(actual_provider, "unknown")

        async def extract_stream():
            import logging
            _logger = logging.getLogger(__name__)

            collected_output = []
            real_usage = [None]

            if actual_provider == "demo":
                stream_gen = AIService._stream_demo("extract_characters")
            elif actual_provider == "openai":
                stream_gen = AIService._stream_openai(extract_prompt)
            elif actual_provider == "anthropic":
                stream_gen = AIService._stream_anthropic(extract_prompt)
            elif actual_provider == "ollama":
                stream_gen = AIService._stream_ollama(extract_prompt)
            else:
                yield f"data: {_json.dumps({'error': '无可用的 AI 服务'}, ensure_ascii=False)}\n\n"
                return

            yield ": connected\n\n"

            stream_iter = stream_gen.__aiter__()
            pending_task = None
            heartbeat_interval = 5.0

            while True:
                try:
                    if pending_task is None:
                        pending_task = asyncio.create_task(stream_iter.__anext__())

                    done, _ = await asyncio.wait([pending_task], timeout=heartbeat_interval)

                    if done:
                        sse_line = pending_task.result()
                        pending_task = None
                        if sse_line.startswith("data: "):
                            try:
                                _d = _json.loads(sse_line[6:].strip())
                                if _d.get("text"):
                                    collected_output.append(_d["text"])
                                if _d.get("usage"):
                                    real_usage[0] = _d["usage"]
                            except Exception:
                                pass
                        yield sse_line
                    else:
                        yield ": heartbeat\n\n"

                except StopAsyncIteration:
                    break
                except Exception as e:
                    _logger.error(f"extract_characters 生成异常: {e}", exc_info=True)
                    yield f"data: {_json.dumps({'error': 'AI 服务处理异常，请稍后再试'}, ensure_ascii=False)}\n\n"
                    break

            # 记录 token 使用
            if actual_provider != "demo":
                if real_usage[0]:
                    in_tok = real_usage[0].get("input_tokens", 0)
                    out_tok = real_usage[0].get("output_tokens", 0)
                else:
                    output_text = "".join(collected_output)
                    in_tok = estimate_tokens(extract_prompt)
                    out_tok = estimate_tokens(output_text)
                await log_token_usage(
                    db=db, user_id=current_user.id,
                    provider=actual_provider, model=actual_model,
                    action="extract_characters",
                    input_tokens=in_tok, output_tokens=out_tok,
                    project_id=project_id,
                )

        return StreamingResponse(
            extract_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # 构建智能上下文（基于内容语义匹配最相关的设定）
    context_data = await smart_context.build_smart_context(
        content=content or "",
        action=payload.action,
        chapter_id=payload.chapter_id,
        include_events=True,
        include_notes=True,
        include_outline=True,
        pinned_context=payload.pinned_context.model_dump() if payload.pinned_context else None,
    )

    # 提取格式化后的上下文文本
    context_text = context_data.get("context_text", "")

    # 获取匹配到的实体列表（用于前端反馈）
    context_entities = context_data.get("entities", [])

    # 剧情完善：获取前几章内容和大纲作为额外上下文
    outline_context = ""
    previous_chapters = ""
    if payload.action == "plot_enhance":
        # 获取大纲节点
        outline_result = await db.execute(
            select(OutlineNode).where(
                OutlineNode.project_id == project_id
            ).order_by(OutlineNode.level, OutlineNode.sort_order).limit(30)
        )
        outline_nodes = outline_result.scalars().all()
        if outline_nodes:
            outline_lines = []
            for node in outline_nodes:
                prefix = "  " * node.level
                outline_lines.append(f"{prefix}- [{node.node_type}] {node.title}: {node.content or ''}")
            outline_context = "故事大纲：\n" + "\n".join(outline_lines)

        # 获取当前章节之前的章节内容（最多取前5章的摘要）
        chapters_query = select(Chapter).where(
            Chapter.project_id == project_id
        ).order_by(Chapter.sort_order)
        if payload.chapter_id:
            # 获取当前章节的 sort_order
            cur_ch_result = await db.execute(
                select(Chapter).where(Chapter.id == payload.chapter_id)
            )
            cur_chapter = cur_ch_result.scalar_one_or_none()
            if cur_chapter:
                chapters_query = chapters_query.where(
                    Chapter.sort_order < cur_chapter.sort_order
                )
        chapters_query = chapters_query.limit(5)
        prev_result = await db.execute(chapters_query)
        prev_chapters = prev_result.scalars().all()
        if prev_chapters:
            ch_parts = []
            for ch in prev_chapters:
                ch_content = (ch.content or "")[:800]
                ch_parts.append(f"【{ch.title}】\n{ch_content}")
            previous_chapters = "前文内容摘要：\n\n" + "\n\n---\n\n".join(ch_parts)

    # 确定实际使用的 provider 和 model（用于 token 记录）
    actual_provider = AIService._get_available_provider(payload.provider)
    provider_model_map = {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "ollama": settings.OLLAMA_MODEL,
        "demo": "demo",
    }
    actual_model = provider_model_map.get(actual_provider, "unknown")
    input_text = content or ""

    async def stream_with_heartbeat():
        """带心跳的流式生成，防止长连接超时"""
        import logging
        logger = logging.getLogger(__name__)

        collected_output = []
        real_usage = [None]  # 用列表包装以便在闭包中修改

        stream_gen = AIService.generate_stream(
            action=payload.action,
            content=content,
            provider=payload.provider,
            title=project.title,
            genre=project.genre or "",
            description=project.description or "",
            question=payload.question or "",
            context_text=context_text,
            outline_context=outline_context,
            previous_chapters=previous_chapters,
        )

        heartbeat_count = 0
        max_heartbeats = 120  # 最多 120 次心跳（10分钟）后放弃
        heartbeat_interval = 5.0  # 每 5 秒发一次心跳

        # 立即发送初始心跳，确保连接建立并有数据流过
        yield ": connected\n\n"

        # 发送上下文实体列表（用于前端反馈）
        if context_entities:
            yield f"data: {_json.dumps({'type': 'context_used', 'entities': context_entities}, ensure_ascii=False)}\n\n"

        # 创建一个任务来获取下一个元素
        stream_iter = stream_gen.__aiter__()
        pending_task = None

        while True:
            try:
                # 如果没有待处理的任务，创建一个
                if pending_task is None:
                    pending_task = asyncio.create_task(stream_iter.__anext__())

                # 等待任务完成或超时
                done, _ = await asyncio.wait([pending_task], timeout=heartbeat_interval)

                if done:
                    # 任务完成了
                    sse_line = pending_task.result()
                    pending_task = None
                    heartbeat_count = 0
                    # 收集输出文本和真实 usage
                    if sse_line.startswith("data: "):
                        try:
                            _d = _json.loads(sse_line[6:].strip())
                            if _d.get("text"):
                                collected_output.append(_d["text"])
                            if _d.get("usage"):
                                real_usage[0] = _d["usage"]
                        except Exception:
                            pass
                    yield sse_line
                else:
                    # 超时但任务仍在运行，发送心跳
                    heartbeat_count += 1
                    if heartbeat_count > max_heartbeats:
                        logger.error(f"AI 生成超时，已发送 {max_heartbeats} 次心跳仍无响应")
                        pending_task.cancel()
                        yield f"data: {_json.dumps({'error': 'AI 服务响应超时'}, ensure_ascii=False)}\n\n"
                        break
                    logger.debug(f"AI 生成等待中，发送心跳 #{heartbeat_count}")
                    yield f": heartbeat\n\n"

            except StopAsyncIteration:
                # 流正常结束
                break
            except Exception as e:
                logger.error(f"AI 生成异常: {e}", exc_info=True)
                yield f"data: {_json.dumps({'error': 'AI 服务处理异常，请稍后再试'}, ensure_ascii=False)}\n\n"
                break

        # 记录 token 使用（优先使用 API 返回的真实数据）
        if actual_provider != "demo":
            if real_usage[0]:
                in_tok = real_usage[0].get("input_tokens", 0)
                out_tok = real_usage[0].get("output_tokens", 0)
            else:
                output_text = "".join(collected_output)
                in_tok = estimate_tokens(input_text)
                out_tok = estimate_tokens(output_text)
            await log_token_usage(
                db=db,
                user_id=current_user.id,
                provider=actual_provider,
                model=actual_model,
                action=payload.action,
                input_tokens=in_tok,
                output_tokens=out_tok,
                project_id=project_id,
            )

    return StreamingResponse(
        stream_with_heartbeat(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/context-preview", response_model=ContextPreviewResponse)
async def context_preview(
    project_id: int,
    payload: AIGenerateRequest,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    预览 AI 将使用的上下文
    返回匹配到的实体列表，不实际调用 AI
    """
    smart_context = SmartContextService(db, project_id)

    # 如果指定了章节，获取章节内容
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

    # 构建智能上下文
    context_data = await smart_context.build_smart_context(
        content=content or "",
        action=payload.action,
        chapter_id=payload.chapter_id,
        include_events=True,
        include_notes=True,
        include_outline=True,
        pinned_context=payload.pinned_context.model_dump() if payload.pinned_context else None,
    )

    entities = [
        ContextEntity(**e) for e in context_data.get("entities", [])
    ]

    # 生成建议
    suggestions = _generate_context_suggestions(entities, content or "")

    return ContextPreviewResponse(
        entities=entities,
        suggestions=suggestions,
    )


def _generate_context_suggestions(entities: list, content: str) -> str:
    """生成上下文建议"""
    suggestions = []

    # 检查是否有匹配到的角色
    characters = [e for e in entities if e.type == "character"]
    if not characters:
        suggestions.append("未检测到相关角色，建议手动固定主要角色。")
    elif len(characters) < 3:
        suggestions.append(f"检测到 {len(characters)} 个相关角色，可能需要补充更多角色设定。")

    # 检查世界观设定
    worldbuilding = [e for e in entities if e.type == "worldbuilding"]
    if not worldbuilding:
        suggestions.append("未检测到相关世界观设定，建议添加场景、背景等设定。")

    # 检查伏笔
    notes = [e for e in entities if e.type == "note"]
    foreshadowing = [n for n in notes if "伏笔" in n.summary]
    if foreshadowing:
        suggestions.append(f"有 {len(foreshadowing)} 个活跃伏笔待回收，请留意故事发展。")

    # 检查内容长度
    if content and len(content) < 100:
        suggestions.append("当前内容较短，上下文匹配可能不够精确。")

    if not suggestions:
        suggestions.append("上下文匹配良好，可以开始创作。")

    return "\n".join(suggestions)


@router.post("/batch-generate")
async def batch_generate(
    project_id: int,
    payload: BatchGenerateRequest,
    project: Project = Depends(get_project_with_auth),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    AI 批量生成前 X 章
    SSE 流式返回：outline -> chapter(逐章) -> done
    """
    import json as _json

    # 使用智能上下文服务获取相关设定
    smart_context = SmartContextService(db, project_id)
    context_data = await smart_context.build_smart_context(
        content=f"{project.title} {project.genre or ''} {project.description or ''}",
        action="batch_generate",
        include_events=False,
        include_notes=True,
        include_outline=True,
    )
    context = context_data.get("context_text", "")

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

    batch_provider = AIService._get_available_provider()
    batch_model_map = {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "ollama": settings.OLLAMA_MODEL,
        "demo": "demo",
    }
    batch_model = batch_model_map.get(batch_provider, "unknown")

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

            # 记录大纲生成的 token 使用
            if batch_provider != "demo":
                await log_token_usage(
                    db=db, user_id=current_user.id,
                    provider=batch_provider, model=batch_model,
                    action="batch_outline",
                    input_tokens=estimate_tokens(outline_prompt),
                    output_tokens=estimate_tokens(outline_raw),
                    project_id=project_id,
                )

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
                    min_words=int(payload.words_per_chapter * 0.8),
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
                    # 模拟逐块输出
                    chunk_size = 20
                    for ci in range(0, len(demo_text), chunk_size):
                        chunk = demo_text[ci:ci + chunk_size]
                        chapter_content += chunk
                        yield f"data: {_json.dumps({'type': 'chapter_stream', 'chapter_index': chapter_index, 'title': chapter_title, 'text': chunk}, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0.05)
                else:
                    # 真实 AI 流式生成（带心跳防断连）
                    if provider == "openai":
                        stream_gen = AIService._stream_openai(chapter_prompt)
                    elif provider == "anthropic":
                        stream_gen = AIService._stream_anthropic(chapter_prompt)
                    else:
                        stream_gen = AIService._stream_ollama(chapter_prompt)

                    stream_iter = stream_gen.__aiter__()
                    stream_done = False
                    while not stream_done:
                        try:
                            sse_line = await asyncio.wait_for(stream_iter.__anext__(), timeout=15)
                        except asyncio.TimeoutError:
                            # 超过 15 秒未收到数据，发送心跳保持连接
                            yield f": heartbeat\n\n"
                            continue
                        except StopAsyncIteration:
                            stream_done = True
                            break

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

                # 记录章节生成的 token 使用
                if provider != "demo":
                    await log_token_usage(
                        db=db, user_id=current_user.id,
                        provider=batch_provider, model=batch_model,
                        action="batch_chapter",
                        input_tokens=estimate_tokens(chapter_prompt),
                        output_tokens=estimate_tokens(chapter_content),
                        project_id=project_id,
                    )

                # AI 除痕处理
                if payload.remove_ai_traces and provider != "demo":
                    yield f"data: {_json.dumps({'type': 'progress', 'message': f'正在优化第 {chapter_index} 章...'}, ensure_ascii=False)}\n\n"

                    try:
                        remove_prompt = PROMPTS["remove_ai_traces"].format(
                            target_words=payload.words_per_chapter,
                            current_words=len(chapter_content),
                            chapter_title=chapter_title,
                            content=chapter_content,
                        )
                        refined_content = await AIService.generate_text(remove_prompt, max_tokens=len(chapter_content) + 500)

                        if refined_content and len(refined_content) > 100:
                            # 更新章节内容
                            new_chapter.content = refined_content
                            new_chapter.word_count = len(refined_content)
                            await db.commit()
                            await db.refresh(new_chapter)

                            # 记录除痕的 token 使用
                            await log_token_usage(
                                db=db, user_id=current_user.id,
                                provider=batch_provider, model=batch_model,
                                action="remove_ai_traces",
                                input_tokens=estimate_tokens(remove_prompt),
                                output_tokens=estimate_tokens(refined_content),
                                project_id=project_id,
                            )

                            # 发送除痕完成事件（包含优化后的内容差量）
                            diff_words = len(refined_content) - len(chapter_content)
                            yield f"data: {_json.dumps({'type': 'refine_done', 'chapter_index': chapter_index, 'word_diff': diff_words, 'final_words': len(refined_content)}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        # 除痕失败不影响主流程
                        yield f"data: {_json.dumps({'type': 'warning', 'message': f'除痕处理失败: {str(e)[:50]}'}, ensure_ascii=False)}\n\n"

                # 发送章节完成事件
                yield f"data: {_json.dumps({'type': 'chapter_done', 'chapter_index': chapter_index, 'title': chapter_title, 'chapter_id': new_chapter.id, 'word_count': new_chapter.word_count}, ensure_ascii=False)}\n\n"

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
            logger.error(f"批量扩写异常: {e}", exc_info=True)
            yield f"data: {_json.dumps({'type': 'error', 'message': 'AI 服务处理异常，请稍后再试'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
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
