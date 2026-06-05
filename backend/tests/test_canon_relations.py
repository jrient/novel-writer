"""关系抽取纯函数：name→id 回链 + 去重"""
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
