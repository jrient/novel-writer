"""canon_context：把 reference 的 canon 实体拼成「设定锚定」prompt 块"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def test_build_canon_context_groups_and_labels(db_session, session_factory):
    ref = ReferenceNovel(title="西游记", total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    db_session.add_all([
        CanonEntity(reference_id=ref.id, entity_type="character",
                    canonical_name="乌鸡国国王", summary="被害君主", aliases=["陛下"]),
        CanonEntity(reference_id=ref.id, entity_type="worldrule",
                    canonical_name="三界体系", summary="天庭-人间-地府"),
    ])
    await db_session.commit()

    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        ctx = await build_canon_context(s, ref.id)
    assert "设定锚定" in ctx
    assert "乌鸡国国王" in ctx
    assert "陛下" in ctx
    assert "三界体系" in ctx
    assert "必须遵守" in ctx


async def test_build_canon_context_empty_returns_empty(db_session, session_factory):
    ref = ReferenceNovel(title="空原作", total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        ctx = await build_canon_context(s, ref.id)
    assert ctx == ""


def test_wizard_schema_accepts_canon_reference_id():
    from app.schemas.wizard import WizardMapsRequest
    req = WizardMapsRequest(title="测试", description="穿越乌鸡国", canon_reference_id=5)
    assert req.canon_reference_id == 5
