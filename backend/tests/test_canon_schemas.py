"""canon schema 序列化测试"""
from app.schemas.canon import (
    CanonEntityOut, CanonEntityCreate, CanonEntityUpdate, CanonJobOut,
)


def test_entity_create_requires_type_and_name():
    c = CanonEntityCreate(entity_type="character", canonical_name="孙悟空")
    assert c.entity_type == "character"
    assert c.aliases == []
    assert c.attributes == {}


def test_entity_update_all_optional():
    u = CanonEntityUpdate(summary="改过的设定")
    assert u.summary == "改过的设定"
    assert u.canonical_name is None


def test_job_out_from_attributes():
    class FakeJob:
        id = 1
        reference_id = 2
        status = "done"
        model = "demo"
        chunk_total = 5
        chunk_done = 5
        failed_chunks = 0
        entity_count = 12
        error = None
        created_at = None
        updated_at = None
    out = CanonJobOut.model_validate(FakeJob())
    assert out.entity_count == 12
