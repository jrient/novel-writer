"""canon_pipeline 纯函数单测（不触发 LLM）"""
import pytest
from unittest.mock import patch, AsyncMock

from app.services.ai_service import AIService
from app.services.canon_pipeline import _chunk_reference, _safe_json_array


def test_chunk_reference_splits_long_text():
    content = "\n".join([f"第{i}段内容，约二十个汉字凑数填充。" for i in range(50)])
    chunks = _chunk_reference(content, chunk_size=200)
    assert len(chunks) > 1
    # 每块带 label
    assert all("label" in c and "text" in c for c in chunks)
    assert chunks[0]["label"].startswith("片段")


def test_safe_json_array_parses_fenced():
    raw = '```json\n[{"canonical_name":"孙悟空","entity_type":"character"}]\n```'
    arr = _safe_json_array(raw)
    assert len(arr) == 1
    assert arr[0]["canonical_name"] == "孙悟空"


def test_safe_json_array_returns_empty_on_garbage():
    assert _safe_json_array("这不是JSON，纯文本。") == []


async def test_atomic_extract_one_chunk_parses_entities():
    from app.services.canon_pipeline import _atomic_extract_chunk

    fake_llm = AsyncMock(return_value=(
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source":{"quote":"我本是乌鸡国王"},"importance":"major"}]'
    ))
    with patch.object(AIService, "generate_text", fake_llm):
        ents = await _atomic_extract_chunk(
            {"label": "第三十七回", "text": "我本是乌鸡国王..."}, model=None
        )
    assert len(ents) == 1
    assert ents[0]["canonical_name"] == "乌鸡国国王"
    # source 被规整进 source_refs
    assert ents[0]["source_refs"][0]["quote"] == "我本是乌鸡国王"
    assert ents[0]["source_refs"][0]["chapter"] == "第三十七回"


async def test_atomic_extract_chunk_handles_bad_json():
    from app.services.canon_pipeline import _atomic_extract_chunk
    with patch.object(AIService, "generate_text", AsyncMock(return_value="抱歉我无法解析")):
        ents = await _atomic_extract_chunk({"label": "片段1", "text": "x"}, model=None)
    assert ents == []


async def test_merge_entities_by_type_disambiguates():
    from app.services.canon_pipeline import _merge_entities_of_type

    raw = [
        {"entity_type": "character", "canonical_name": "乌鸡国王",
         "aliases": ["陛下"], "source_refs": [{"chapter": "片段1", "quote": "a"}]},
        {"entity_type": "character", "canonical_name": "乌鸡国国王",
         "aliases": [], "source_refs": [{"chapter": "片段2", "quote": "b"}]},
    ]
    merged_json = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下","乌鸡国王"],"summary":"被害君主",'
        '"source_refs":[{"chapter":"片段1","quote":"a"},{"chapter":"片段2","quote":"b"}],'
        '"importance":"major"}]'
    )
    with patch.object(AIService, "generate_text", AsyncMock(return_value=merged_json)):
        merged = await _merge_entities_of_type("character", raw, model=None)
    assert len(merged) == 1
    assert merged[0]["canonical_name"] == "乌鸡国国王"
    assert len(merged[0]["source_refs"]) == 2


async def test_merge_entities_empty_returns_empty():
    from app.services.canon_pipeline import _merge_entities_of_type
    assert await _merge_entities_of_type("ability", [], model=None) == []


async def test_merge_no_progress_terminates_without_hang():
    """所有批次都返回坏 JSON → 回退原样 → 不应死循环，返回原集合。"""
    from app.services.canon_pipeline import _merge_entities_of_type, MERGE_BATCH
    raw = [{"entity_type": "character", "canonical_name": f"角色{i}", "aliases": [],
            "source_refs": []} for i in range(MERGE_BATCH + 5)]
    with patch.object(AIService, "generate_text", AsyncMock(return_value="非JSON输出")):
        merged = await _merge_entities_of_type("character", raw, model=None)
    # 坏 JSON 全部回退，无法归并，但必须终止并返回全部条目
    assert len(merged) == MERGE_BATCH + 5


# ---------------------------------------------------------------------------
# Task 8: end-to-end integration test for run_canon_extraction
# ---------------------------------------------------------------------------
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity, CanonExtractionJob
from sqlalchemy import select


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def test_run_canon_extraction_end_to_end(db_session, session_factory):
    ref = ReferenceNovel(title="测试原作",
                         content="乌鸡国国王被狮猁怪推入御花园八角琉璃井中。" * 30,
                         total_chars=600)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)

    atomic_out = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source":{"quote":"乌鸡国国王被推入井中"},"importance":"major"}]'
    )
    merge_out = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source_refs":[{"chapter":"片段1","quote":"乌鸡国国王被推入井中"}],'
        '"importance":"major"}]'
    )

    async def fake_generate(prompt, provider=None, max_tokens=None):
        return merge_out if "归并" in prompt or "待归并" in prompt else atomic_out

    from app.services.canon_pipeline import run_canon_extraction
    with patch.object(AIService, "generate_text", side_effect=fake_generate):
        job_id = await run_canon_extraction(ref.id, session_factory, model="demo")

    async with session_factory() as s:
        job = (await s.execute(select(CanonExtractionJob).where(
            CanonExtractionJob.id == job_id))).scalar_one()
        assert job.status == "done"
        assert job.entity_count >= 1
        ents = (await s.execute(select(CanonEntity).where(
            CanonEntity.reference_id == ref.id))).scalars().all()
        assert any(e.canonical_name == "乌鸡国国王" for e in ents)
        assert ents[0].source_refs  # 溯源非空（准确度回归基线）
        assert ents[0].review_status == "ai_extracted"


async def test_empty_extraction_preserves_existing_entities(db_session, session_factory):
    """全数失败导致 merged_all 为空时，不得抹除上次成功提取的 ai_extracted，
    更不得动用户的人工条目。回归保护：一次失败的提取不应清空历史。"""
    ref = ReferenceNovel(title="测试原作B", content="正文。" * 50, total_chars=150)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    # 预置历史：1 条 AI 提取 + 1 条人工新增
    db_session.add_all([
        CanonEntity(reference_id=ref.id, entity_type="character",
                    canonical_name="旧AI实体", importance="major",
                    confidence=1.0, review_status="ai_extracted"),
        CanonEntity(reference_id=ref.id, entity_type="character",
                    canonical_name="用户实体", importance="major",
                    confidence=1.0, review_status="user_added"),
    ])
    await db_session.commit()

    # LLM 全程返回非 JSON → atomic 全空 → merged_all 为空
    from app.services.canon_pipeline import run_canon_extraction
    with patch.object(AIService, "generate_text",
                      AsyncMock(return_value="服务繁忙，无法解析")):
        job_id = await run_canon_extraction(ref.id, session_factory, model="demo")

    async with session_factory() as s:
        job = (await s.execute(select(CanonExtractionJob).where(
            CanonExtractionJob.id == job_id))).scalar_one()
        assert job.status == "done"
        names = {e.canonical_name for e in (await s.execute(select(CanonEntity).where(
            CanonEntity.reference_id == ref.id))).scalars().all()}
        # 历史 ai_extracted 与人工条目都应保留
        assert "旧AI实体" in names
        assert "用户实体" in names
        assert job.entity_count == 1  # 报告现存 ai_extracted 数量
