"""把原作 canon 设定拼成 wizard 的「设定锚定」prompt 块。
与 style_reference（文风参考）语义分离：这里是必须遵守的设定事实约束。
MVP：全量注入（按 importance 排序，限条目数）。后续可加 premise 关键词/向量召回。
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canon import CanonEntity

_TYPE_CN = {
    "character": "人物", "location": "地点", "ability": "能力",
    "faction": "势力", "worldrule": "世界观规则", "event": "关键事件",
}
_IMPORTANCE_RANK = {"critical": 0, "major": 1, "minor": 2}
_MAX_ENTITIES = 60


async def build_canon_context(db: AsyncSession, reference_id: int,
                              max_entities: int = _MAX_ENTITIES) -> str:
    rows = (await db.execute(select(CanonEntity).where(
        CanonEntity.reference_id == reference_id))).scalars().all()
    if not rows:
        return ""
    rows = sorted(rows, key=lambda e: _IMPORTANCE_RANK.get(e.importance, 1))[:max_entities]

    by_type: dict[str, list[CanonEntity]] = {}
    for e in rows:
        by_type.setdefault(e.entity_type, []).append(e)

    lines = [
        "【原作设定锚定——以下是二创必须遵守的原作事实，人物/能力/世界观不得与之冲突】",
    ]
    for etype, ents in by_type.items():
        lines.append(f"\n# {_TYPE_CN.get(etype, etype)}")
        for e in ents:
            alias = f"（别名：{'、'.join(e.aliases)}）" if e.aliases else ""
            summary = f"：{e.summary}" if e.summary else ""
            lines.append(f"- {e.canonical_name}{alias}{summary}")
    return "\n".join(lines)
