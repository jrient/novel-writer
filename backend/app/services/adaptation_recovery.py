"""服务启动时清理悬挂的 running 状态。"""
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.adaptation_version import AdaptationVersion


async def cleanup_stale_runs(db: AsyncSession, max_age_sec: int) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_sec)
    stale_versions = (await db.execute(
        select(AdaptationVersion).where(
            AdaptationVersion.status == "running",
            AdaptationVersion.created_at < cutoff,
        )
    )).scalars().all()
    for v in stale_versions:
        v.status = "failed"
        v.error = "服务重启时改编中断"
        await db.execute(
            update(AdaptationSceneResult)
            .where(
                AdaptationSceneResult.version_id == v.id,
                AdaptationSceneResult.status == "running",
            )
            .values(status="failed", error="服务重启时改编中断")
        )
    await db.commit()
    return len(stale_versions)
