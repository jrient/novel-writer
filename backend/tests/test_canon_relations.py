"""关系抽取纯函数：name→id 回链 + 去重"""
import pytest
from unittest.mock import patch, AsyncMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.canon_pipeline import _build_name_index, _resolve_relations


def test_build_name_index_includes_aliases():
    ents = [
        {"id": 1, "canonical_name": "孙悟空", "aliases": ["猴哥", "齐天大圣"]},
        {"id": 2, "canonical_name": "唐僧", "aliases": []},
    ]
    idx = _build_name_index(ents)
    assert idx["孙悟空"] == 1
    assert idx["猴哥"] == 1
    assert idx["齐天大圣"] == 1
    assert idx["唐僧"] == 2


def test_resolve_relations_links_and_dedups():
    ents = [
        {"id": 1, "canonical_name": "孙悟空", "aliases": ["猴哥"]},
        {"id": 2, "canonical_name": "唐僧", "aliases": []},
    ]
    idx = _build_name_index(ents)
    raw = [
        {"source": "唐僧", "target": "猴哥", "relation_type": "师徒",
         "label": "唐僧是孙悟空的师父", "quote": "拜为师父"},
        # 重复（同 source/target/type）应被合并
        {"source": "唐僧", "target": "孙悟空", "relation_type": "师徒",
         "label": "", "quote": "师徒同行"},
        # 清单外实体应被丢弃
        {"source": "牛魔王", "target": "唐僧", "relation_type": "敌对", "quote": "x"},
        # 自指应被丢弃
        {"source": "唐僧", "target": "唐僧", "relation_type": "custom", "quote": "x"},
    ]
    rels = _resolve_relations(raw, idx, chunk_label="片段1")
    assert len(rels) == 1
    r = rels[0]
    assert r["source_entity_id"] == 2 and r["target_entity_id"] == 1
    assert r["relation_type"] == "师徒"
    # 两条来源 quote 都保留
    assert len(r["source_refs"]) == 2


@pytest.mark.asyncio
async def test_extract_and_persist_relations(db_session):
    from app.models.reference import ReferenceNovel
    from app.models.canon import CanonEntity, CanonRelation
    from app.services import canon_pipeline as cp

    ref = ReferenceNovel(title="原作", content="唐僧收孙悟空为徒。", total_chars=8)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)

    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="唐僧")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="孙悟空", aliases=["猴哥"])
    db_session.add_all([a, b])
    await db_session.commit()

    fake = '[{"source":"唐僧","target":"孙悟空","relation_type":"师徒","label":"师父","quote":"收为徒"}]'
    sf = async_sessionmaker(db_session.bind, expire_on_commit=False)
    with patch.object(cp.AIService, "generate_text", new=AsyncMock(return_value=fake)):
        n = await cp.extract_relations_for_reference(ref.id, sf, model=None)
    assert n == 1

    rows = (await db_session.execute(
        select(CanonRelation).where(CanonRelation.reference_id == ref.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].relation_type == "师徒"
    assert rows[0].review_status == "ai_extracted"
