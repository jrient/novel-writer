"""canon 模型测试：建表 + 字段默认值 + JSON 往返"""
import pytest
from sqlalchemy import select

from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.reference import ReferenceNovel


@pytest.fixture
async def ref(db_session):
    r = ReferenceNovel(title="西游记", total_chars=1000)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_create_canon_entity_with_json_fields(db_session, ref):
    e = CanonEntity(
        reference_id=ref.id,
        entity_type="character",
        canonical_name="乌鸡国国王",
        aliases=["陛下", "那妖道假扮的国王"],
        summary="被狮猁怪推入井中三年的乌鸡国君主",
        attributes={"role": "受害君主", "fate": "被青毛狮子精顶替"},
        source_refs=[{"chapter": "第三十七回", "offset": 1200, "quote": "我本是乌鸡国王"}],
        importance="major",
        confidence=0.9,
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)

    assert e.id is not None
    assert e.review_status == "ai_extracted"  # 默认值
    assert e.aliases == ["陛下", "那妖道假扮的国王"]
    assert e.source_refs[0]["chapter"] == "第三十七回"


async def test_create_extraction_job_defaults(db_session, ref):
    job = CanonExtractionJob(reference_id=ref.id, model="demo")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.status == "pending"
    assert job.chunk_total == 0
    assert job.chunk_done == 0
    assert job.failed_chunks == 0
    assert job.entity_count == 0

async def test_canon_relation_persist(db_session):
    from app.models.reference import ReferenceNovel
    from app.models.canon import CanonEntity, CanonRelation
    ref = ReferenceNovel(title="原作", content="正文", total_chars=2)
    db_session.add(ref); await db_session.commit(); await db_session.refresh(ref)
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="乙")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)
    rel = CanonRelation(
        reference_id=ref.id, source_entity_id=a.id, target_entity_id=b.id,
        relation_type="师徒", label="甲是乙的师父",
        source_refs=[{"chapter": "片段1", "quote": "甲收乙为徒"}],
    )
    db_session.add(rel); await db_session.commit(); await db_session.refresh(rel)
    assert rel.id is not None
    assert rel.review_status == "ai_extracted"
    assert rel.confidence == 1.0
