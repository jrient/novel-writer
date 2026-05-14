"""改编流水线编排：parse → extract → split → run_full / rerun_scene。"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.adaptation_version import AdaptationVersion
from app.services.adaptation_event_bus import event_bus
from app.services.adaptation_llm_service import AdaptationLLMService
from app.services.adaptation_splitter import SceneBoundary, split_by_regex

logger = logging.getLogger(__name__)


def _line_count(s: str) -> int:
    return sum(1 for ln in s.splitlines() if ln.strip())


def _delta_pct(orig: str, new: str) -> float:
    o = _line_count(orig) or 1
    return (_line_count(new) - _line_count(orig)) / o


@dataclass
class AdaptationPipeline:
    db: AsyncSession
    llm: AdaptationLLMService
    concurrency: int = 0  # 0 = 用配置默认

    def _sem(self) -> asyncio.Semaphore:
        n = self.concurrency or settings.ADAPTATION_REWRITE_CONCURRENCY
        return asyncio.Semaphore(max(1, n))

    async def extract(self, project: AdaptationProject) -> None:
        """LLM 抽实体 + 性格标签；保留 locked 行不覆盖。"""
        try:
            data = await self.llm.extract_entities(project.source_text)
        except Exception as e:
            project.status = "extract_failed"
            await self.db.commit()
            raise

        existing_rows = (await self.db.execute(
            select(AdaptationMappingEntry).where(
                AdaptationMappingEntry.project_id == project.id
            )
        )).scalars().all()
        seen = {r.original_text for r in existing_rows}

        order = max((r.order_index for r in existing_rows), default=-1) + 1
        for ent in data.get("entities", []):
            text = ent.get("text", "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            self.db.add(AdaptationMappingEntry(
                project_id=project.id,
                entity_type=ent.get("type", "other"),
                original_text=text,
                replacement_text=None,
                locked=False,
                order_index=order,
            ))
            order += 1

        meta = dict(project.metadata_ or {})
        meta["character_traits"] = data.get("character_traits", [])
        project.metadata_ = meta
        project.status = "ready"
        await self.db.commit()

    async def split(self, project: AdaptationProject) -> None:
        """切场：先正则；不命中走 LLM；最后兜底为单场。"""
        text = project.source_text
        boundaries = split_by_regex(text)
        method = "regex"
        if not boundaries:
            try:
                boundaries = await self.llm.split_by_llm(text)
                method = "llm"
            except Exception as e:
                logger.warning("LLM 切场失败，降级单场：%s", e)
                boundaries = [SceneBoundary(index=0, start=0, end=len(text), title="全文")]
                method = "fallback_single"

        meta = dict(project.metadata_ or {})
        meta["scene_boundaries"] = [
            {"index": b.index, "start": b.start, "end": b.end, "title": b.title}
            for b in boundaries
        ]
        meta["scene_summaries"] = meta.get("scene_summaries") or [""] * len(boundaries)
        if len(meta["scene_summaries"]) != len(boundaries):
            meta["scene_summaries"] = [""] * len(boundaries)
        meta["split_method"] = method
        project.metadata_ = meta
        project.status = "ready"
        await self.db.commit()

    async def create_full_run(
        self, project: AdaptationProject, *, extra_prompt: Optional[str] = None
    ) -> AdaptationVersion:
        max_no = (await self.db.execute(
            select(func.coalesce(func.max(AdaptationVersion.version_no), 0))
            .where(AdaptationVersion.project_id == project.id)
        )).scalar_one()

        mappings = (await self.db.execute(
            select(AdaptationMappingEntry)
            .where(AdaptationMappingEntry.project_id == project.id)
            .order_by(AdaptationMappingEntry.order_index)
        )).scalars().all()
        snapshot = [{
            "original_text": m.original_text,
            "replacement_text": m.replacement_text,
            "entity_type": m.entity_type,
            "locked": m.locked,
            "notes": m.notes,
        } for m in mappings]

        version = AdaptationVersion(
            project_id=project.id,
            version_no=int(max_no) + 1,
            triggered_by="full_run",
            status="running",
            mapping_snapshot=snapshot,
            prompt_overrides={"extra_prompt": extra_prompt} if extra_prompt else None,
        )
        self.db.add(version); await self.db.flush()

        boundaries = (project.metadata_ or {}).get("scene_boundaries", [])
        for b in boundaries:
            self.db.add(AdaptationSceneResult(
                version_id=version.id,
                scene_index=b["index"],
                scene_title=b["title"],
                original_scene_text=project.source_text[b["start"]:b["end"]],
                status="pending",
            ))
        project.status = "generating"
        await self.db.commit()
        return version

    async def execute_full_run(
        self, project: AdaptationProject, version: AdaptationVersion
    ) -> None:
        sem = self._sem()
        meta = project.metadata_ or {}
        summaries = meta.get("scene_summaries", [])
        traits = meta.get("character_traits", [])
        extra_prompt = (version.prompt_overrides or {}).get("extra_prompt")

        scenes = (await self.db.execute(
            select(AdaptationSceneResult)
            .where(AdaptationSceneResult.version_id == version.id)
            .order_by(AdaptationSceneResult.scene_index)
        )).scalars().all()

        async def _one(scene: AdaptationSceneResult):
            async with sem:
                await self._rewrite_one(
                    project=project, version=version, scene=scene,
                    prev_summary=summaries[scene.scene_index - 1] if scene.scene_index > 0 and scene.scene_index - 1 < len(summaries) else None,
                    traits=traits, mappings=version.mapping_snapshot or [],
                    extra_prompt=extra_prompt,
                )

        await asyncio.gather(*[_one(s) for s in scenes], return_exceptions=False)

        succeeded = sum(1 for s in scenes if s.status == "done")
        failed = sum(1 for s in scenes if s.status == "failed")
        if failed == 0:
            version.status = "done"
        elif succeeded == 0:
            version.status = "failed"
        else:
            version.status = "partial"
        version.completed_at = datetime.utcnow()
        version.stats = {
            "total_scenes": len(scenes),
            "succeeded": succeeded,
            "failed": failed,
            "total_tokens": sum((s.token_used or 0) for s in scenes),
        }
        project.status = "done"
        await self.db.commit()
        await event_bus.publish(version.id, {
            "event": "version_done", "version_id": version.id, "status": version.status,
        })

    async def _rewrite_one(
        self, *, project: AdaptationProject, version: AdaptationVersion,
        scene: AdaptationSceneResult, prev_summary: Optional[str],
        traits: List[Dict[str, Any]], mappings: List[Dict[str, Any]],
        extra_prompt: Optional[str],
    ) -> None:
        scene.status = "running"
        await event_bus.publish(version.id, {
            "event": "scene_running", "scene_index": scene.scene_index,
        })
        try:
            text = await asyncio.wait_for(
                self.llm.rewrite_scene(
                    scene_text=scene.original_scene_text,
                    intensity=project.intensity,
                    intent=project.intent,
                    era_target=project.era_target,
                    mappings=mappings,
                    prev_scene_summary=prev_summary,
                    character_traits=traits,
                    extra_prompt=extra_prompt,
                    scene_title=scene.scene_title,
                ),
                timeout=settings.ADAPTATION_PER_SCENE_TIMEOUT_SEC,
            )
            scene.rewritten_scene_text = text
            scene.status = "done"
            scene.line_count_delta_pct = _delta_pct(scene.original_scene_text, text)
        except Exception as e:
            scene.status = "failed"
            scene.error = str(e)[:500]
            logger.exception("场 %s 改写失败", scene.scene_index)
        await event_bus.publish(version.id, {
            "event": "scene_done",
            "scene_index": scene.scene_index,
            "status": scene.status,
            "rewritten": scene.rewritten_scene_text,
            "error": scene.error,
            "line_count_delta_pct": scene.line_count_delta_pct,
        })

    async def rerun_scene(
        self, project: AdaptationProject, version: AdaptationVersion,
        scene: AdaptationSceneResult, extra_prompt: Optional[str],
    ) -> None:
        if scene.status == "running":
            raise ValueError("该场正在跑，无法重跑")
        meta = project.metadata_ or {}
        summaries = meta.get("scene_summaries", [])
        traits = meta.get("character_traits", [])
        before = scene.rewritten_scene_text
        await self._rewrite_one(
            project=project, version=version, scene=scene,
            prev_summary=summaries[scene.scene_index - 1] if scene.scene_index > 0 and scene.scene_index - 1 < len(summaries) else None,
            traits=traits, mappings=version.mapping_snapshot or [],
            extra_prompt=extra_prompt,
        )
        edits = list(scene.manual_edits or [])
        edits.append({
            "type": "rerun", "at": datetime.utcnow().isoformat(),
            "prompt": extra_prompt, "before": before, "after": scene.rewritten_scene_text,
        })
        scene.manual_edits = edits
        await self.db.commit()
        # commit 后 SQLAlchemy 会把 server-side onupdate 列（updated_at）标记 expired，
        # 路由层随后访问该属性会触发同步 lazy load 进而 MissingGreenlet。显式 refresh
        # 一次把全部列重新水合回 instance。
        await self.db.refresh(scene)
