"""
参考小说路由
支持上传、分类、分析参考小说
"""
import json
import os
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.reference import ReferenceNovel
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.reference import (
    ReferenceNovelCreate,
    ReferenceNovelUpdate,
    ReferenceNovelResponse,
    ReferenceNovelDetailResponse,
    ReferenceStatsResponse,
)

router = APIRouter(
    prefix="/api/v1/references",
    tags=["references"],
)

UPLOAD_DIR = "reference_novels"

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _analyze_text(content: str) -> dict:
    """分析文本内容，提取统计信息"""
    # 清理内容
    clean = content.replace(" ", "").replace("\n", "")
    total_chars = len(clean)

    # 尝试识别章节
    chapter_patterns = [
        r'第[一二三四五六七八九十百千\d]+章',
        r'Chapter\s*\d+',
        r'第\d+节',
        r'卷[一二三四五六七八九十\d]+',
    ]

    chapters = []
    for pattern in chapter_patterns:
        splits = re.split(f'({pattern})', content)
        if len(splits) > 2:
            # 重组为章节
            i = 1
            while i < len(splits):
                title = splits[i].strip()
                body = splits[i + 1] if i + 1 < len(splits) else ""
                char_count = len(body.replace(" ", "").replace("\n", ""))
                if char_count > 10:  # 过滤太短的段
                    chapters.append({
                        "title": title,
                        "char_count": char_count,
                        "preview": body.strip()[:200],
                    })
                i += 2
            break

    if not chapters and total_chars > 1000:
        # 按段落分割作为替代
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        # 将段落合并为约2000字的"章节"
        current_chapter = []
        current_count = 0
        ch_num = 1
        for para in paragraphs:
            plen = len(para.replace(" ", ""))
            current_chapter.append(para)
            current_count += plen
            if current_count >= 2000:
                chapters.append({
                    "title": f"段落 {ch_num}",
                    "char_count": current_count,
                    "preview": "\n".join(current_chapter)[:200],
                })
                ch_num += 1
                current_chapter = []
                current_count = 0
        if current_chapter:
            chapters.append({
                "title": f"段落 {ch_num}",
                "char_count": current_count,
                "preview": "\n".join(current_chapter)[:200],
            })

    chapter_count = len(chapters)
    avg_chapter_length = total_chars // chapter_count if chapter_count > 0 else total_chars

    # 提取高频词（简单实现）
    # 去除常见停用词后统计
    stopwords = set("的了是在我他她它们这那就也都不有人一个中大到说被让给用和与于而且但因为所以如果虽然可以会能要将从对于把被让")
    words = {}
    for char in clean:
        if char not in stopwords and '\u4e00' <= char <= '\u9fff':
            words[char] = words.get(char, 0) + 1

    top_chars = sorted(words.items(), key=lambda x: x[1], reverse=True)[:20]

    # 分析文风特征
    style_features = []
    avg_sentence_len = 0
    sentences = re.split(r'[。！？…]', content)
    sentence_lengths = [len(s.strip()) for s in sentences if len(s.strip()) > 2]
    if sentence_lengths:
        avg_sentence_len = sum(sentence_lengths) // len(sentence_lengths)

    if avg_sentence_len > 30:
        style_features.append("长句为主，叙事细腻")
    elif avg_sentence_len < 15:
        style_features.append("短句为主，节奏明快")
    else:
        style_features.append("句式均衡，节奏适中")

    # 对话密度
    dialogue_count = content.count('"') + content.count('"') + content.count('「')
    dialogue_density = dialogue_count / max(total_chars, 1) * 1000
    if dialogue_density > 5:
        style_features.append("对话丰富")
    elif dialogue_density < 1:
        style_features.append("叙述为主，对话较少")

    # 描写类型
    desc_keywords = {
        "环境描写": ["阳光", "月光", "风", "雨", "天空", "大地", "山", "水", "树", "花"],
        "心理描写": ["心想", "觉得", "感到", "内心", "思绪", "心中", "暗想", "心头"],
        "动作描写": ["挥", "劈", "跳", "跑", "踢", "打", "抓", "举", "冲", "闪"],
    }
    for desc_type, keywords in desc_keywords.items():
        count = sum(content.count(k) for k in keywords)
        if count > total_chars / 500:
            style_features.append(f"{desc_type}突出")

    analysis = {
        "total_chars": total_chars,
        "chapter_count": chapter_count,
        "avg_chapter_length": avg_chapter_length,
        "avg_sentence_length": avg_sentence_len,
        "dialogue_density": round(dialogue_density, 2),
        "top_chars": top_chars[:10],
        "style_features": style_features,
        "sentence_count": len(sentence_lengths),
    }

    return {
        "analysis": analysis,
        "chapters": chapters,
        "total_chars": total_chars,
        "chapter_count": chapter_count,
        "avg_chapter_length": avg_chapter_length,
        "writing_style": "；".join(style_features),
    }


def _guess_genre(content: str, title: str = "") -> str:
    """根据内容猜测类型"""
    text = title + content[:5000]
    genre_keywords = {
        "修仙": ["修仙", "仙人", "仙界", "仙门", "道友", "道心", "渡劫", "飞升成仙", "仙途", "修真"],
        "玄幻": ["修炼", "灵气", "丹药", "阵法", "境界", "功法", "元婴", "筑基", "金丹", "宗门"],
        "科幻": ["星际", "飞船", "机器人", "AI", "太空", "量子", "基因", "克隆", "外星"],
        "武侠": ["江湖", "武功", "侠", "剑法", "门派", "武林", "内力", "轻功"],
        "言情": ["爱情", "恋爱", "心动", "约会", "甜蜜", "相恋", "告白"],
        "悬疑": ["线索", "案件", "嫌疑", "凶手", "推理", "密室", "侦探", "证据"],
        "历史": ["朝廷", "皇帝", "丞相", "将军", "朝代", "太子", "后宫"],
        "都市": ["公司", "总裁", "职场", "都市", "商业", "白领"],
        "恐怖": ["鬼", "恐惧", "诡异", "阴森", "灵异", "噩梦"],
    }

    scores = {}
    for genre, keywords in genre_keywords.items():
        score = sum(text.count(k) for k in keywords)
        if score > 0:
            scores[genre] = score

    if scores:
        return max(scores, key=scores.get)
    return "其他"


@router.post("/upload", response_model=ReferenceNovelResponse, status_code=201)
async def upload_reference(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    author: Optional[str] = Form(default=None),
    genre: Optional[str] = Form(default=None),
    reference_type: Optional[str] = Form(default="all"),
    tags: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    rating: Optional[int] = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传参考小说文件（支持 .txt .md 格式）"""
    # 验证文件类型
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".txt", ".md", ".text"):
        raise HTTPException(status_code=400, detail="仅支持 .txt 和 .md 格式")

    # 限制文件大小（最大 20MB）
    MAX_FILE_SIZE = 20 * 1024 * 1024
    raw = await file.read()
    if len(raw) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件大小不能超过 20MB")
    # 尝试多种编码
    content = None
    for encoding in ["utf-8", "gbk", "gb2312", "gb18030", "big5", "latin-1"]:
        try:
            content = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        raise HTTPException(status_code=400, detail="无法识别文件编码")

    # 保存文件
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = re.sub(r'[^\w\u4e00-\u9fff.-]', '_', file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 分析内容
    result = _analyze_text(content)

    # 自动猜测标题和类型
    auto_title = title or os.path.splitext(file.filename)[0]
    auto_genre = genre or _guess_genre(content, auto_title)

    novel = ReferenceNovel(
        owner_id=current_user.id,
        title=auto_title,
        author=author,
        genre=auto_genre,
        source=None,
        tags=tags,
        reference_type=reference_type or "all",
        file_path=file_path,
        file_format=ext.lstrip("."),
        total_chars=result["total_chars"],
        chapter_count=result["chapter_count"],
        avg_chapter_length=result["avg_chapter_length"],
        analysis=json.dumps(result["analysis"], ensure_ascii=False),
        writing_style=result["writing_style"],
        chapters_data=json.dumps(result["chapters"][:50], ensure_ascii=False) if result["chapters"] else None,
        content=content if result["total_chars"] < 100000 else None,  # 10万字以下存库
        notes=notes,
        rating=rating,
    )
    db.add(novel)
    await db.commit()
    await db.refresh(novel)
    return novel


@router.post("/", response_model=ReferenceNovelResponse, status_code=201)
async def create_reference(
    payload: ReferenceNovelCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动创建参考小说记录"""
    novel = ReferenceNovel(**payload.model_dump(), owner_id=current_user.id)
    db.add(novel)
    await db.commit()
    await db.refresh(novel)
    return novel


@router.get("/", response_model=List[ReferenceNovelResponse])
async def list_references(
    genre: Optional[str] = None,
    reference_type: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出参考小说，支持按类型和参考类型筛选"""
    stmt = select(ReferenceNovel).where(
        (ReferenceNovel.owner_id == current_user.id) | (ReferenceNovel.owner_id == None)
    )

    if genre:
        stmt = stmt.where(ReferenceNovel.genre == genre)
    if reference_type:
        stmt = stmt.where(ReferenceNovel.reference_type == reference_type)
    if search:
        stmt = stmt.where(
            ReferenceNovel.title.contains(search) |
            ReferenceNovel.author.contains(search)
        )

    stmt = stmt.order_by(ReferenceNovel.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/stats", response_model=ReferenceStatsResponse)
async def get_reference_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取参考库统计信息"""
    result = await db.execute(select(ReferenceNovel).where(
        (ReferenceNovel.owner_id == current_user.id) | (ReferenceNovel.owner_id == None)
    ))
    novels = result.scalars().all()

    genre_dist = {}
    type_dist = {}
    total_chars = 0

    for n in novels:
        if n.genre:
            genre_dist[n.genre] = genre_dist.get(n.genre, 0) + 1
        if n.reference_type:
            type_dist[n.reference_type] = type_dist.get(n.reference_type, 0) + 1
        total_chars += n.total_chars

    count = len(novels)
    return ReferenceStatsResponse(
        total_count=count,
        genre_distribution=genre_dist,
        avg_length=total_chars // count if count > 0 else 0,
        total_chars=total_chars,
        type_distribution=type_dist,
    )


@router.get("/{novel_id}", response_model=ReferenceNovelDetailResponse)
async def get_reference(
    novel_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取参考小说详情"""
    result = await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == novel_id,
        (ReferenceNovel.owner_id == current_user.id) | (ReferenceNovel.owner_id == None),
    ))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="参考小说不存在")

    # 如果内容在文件中，读取
    if not novel.content and novel.file_path and os.path.exists(novel.file_path):
        with open(novel.file_path, "r", encoding="utf-8") as f:
            novel.content = f.read()

    return novel


@router.put("/{novel_id}", response_model=ReferenceNovelResponse)
async def update_reference(
    novel_id: int,
    payload: ReferenceNovelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新参考小说信息"""
    result = await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == novel_id,
        ReferenceNovel.owner_id == current_user.id,
    ))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="参考小说不存在")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(novel, key, value)

    await db.commit()
    await db.refresh(novel)
    return novel


@router.delete("/{novel_id}", status_code=204)
async def delete_reference(
    novel_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除参考小说"""
    result = await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == novel_id,
        ReferenceNovel.owner_id == current_user.id,
    ))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="参考小说不存在")

    # 删除关联文件
    if novel.file_path and os.path.exists(novel.file_path):
        os.remove(novel.file_path)

    await db.delete(novel)
    await db.commit()


@router.get("/{novel_id}/chapters")
async def get_reference_chapters(
    novel_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取参考小说的章节列表"""
    result = await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == novel_id,
        (ReferenceNovel.owner_id == current_user.id) | (ReferenceNovel.owner_id == None),
    ))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="参考小说不存在")

    if novel.chapters_data:
        return json.loads(novel.chapters_data)
    return []


@router.get("/{novel_id}/analysis")
async def get_reference_analysis(
    novel_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取参考小说的分析结果"""
    result = await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == novel_id,
        (ReferenceNovel.owner_id == current_user.id) | (ReferenceNovel.owner_id == None),
    ))
    novel = result.scalar_one_or_none()
    if not novel:
        raise HTTPException(status_code=404, detail="参考小说不存在")

    if novel.analysis:
        return json.loads(novel.analysis)
    return {"message": "暂无分析数据"}


@router.post("/{novel_id}/vectorize")
async def vectorize_reference(
    novel_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """将参考小说向量化"""
    from app.services.chunk import chunk_service
    
    try:
        chunk_count = await chunk_service.process_reference(db, novel_id)
        return {"message": f"成功生成 {chunk_count} 个向量片段"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-vectorize")
async def batch_vectorize_references(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """批量向量化所有参考小说"""
    from app.services.chunk import chunk_service
    
    result = await db.execute(select(ReferenceNovel))
    novels = result.scalars().all()
    
    results = []
    for novel in novels:
        try:
            chunk_count = await chunk_service.process_reference(db, novel.id)
            results.append({"id": novel.id, "title": novel.title, "chunks": chunk_count})
        except Exception as e:
            results.append({"id": novel.id, "title": novel.title, "error": str(e)})
    
    return {"processed": len(results), "results": results}
