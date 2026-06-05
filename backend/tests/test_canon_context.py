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


async def test_build_canon_context_rejects_non_owner(db_session, session_factory, sample_user):
    """归属校验：传入非属主 owner_user_id 时，即便实体存在也返回空，防越权注入。"""
    ref = ReferenceNovel(title="他人原作", owner_id=sample_user.id, total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    db_session.add(CanonEntity(reference_id=ref.id, entity_type="character",
                               canonical_name="秘密角色"))
    await db_session.commit()

    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        # 其他用户试图读属主的原作 canon → 拒绝
        assert await build_canon_context(s, ref.id, owner_user_id=sample_user.id + 999) == ""
        # 属主本人可读
        assert "秘密角色" in await build_canon_context(s, ref.id, owner_user_id=sample_user.id)


async def test_build_canon_context_allows_public_reference(db_session, session_factory):
    """公共原作（owner_id 为空）任何用户都可作为锚定。"""
    ref = ReferenceNovel(title="公共原作", owner_id=None, total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    db_session.add(CanonEntity(reference_id=ref.id, entity_type="character",
                               canonical_name="公共角色"))
    await db_session.commit()

    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        assert "公共角色" in await build_canon_context(s, ref.id, owner_user_id=99)


def test_wizard_schema_accepts_canon_reference_id():
    from app.schemas.wizard import WizardMapsRequest
    req = WizardMapsRequest(title="测试", description="穿越乌鸡国", canon_reference_id=5)
    assert req.canon_reference_id == 5

def test_type_cn_covers_ten_dimensions():
    from app.services.canon_context import _TYPE_CN
    for key in ("item", "race", "realm", "concept"):
        assert key in _TYPE_CN
