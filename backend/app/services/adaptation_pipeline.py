"""改编流水线编排：parse → extract → split → run_full / rerun_scene。"""
import asyncio
import logging
from dataclasses import dataclass
from app.core.datetime_utils import utcnow_naive
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
        """并发改写全部场。

        每个场用独立 db session 自行 commit，避免共享 session 并发 commit
        引发 race / 一次性堆积 N 行 dirty 数据导致中途异常时整体回滚的问题。
        gather 用 return_exceptions=True，单场异常不再 cancel 其它兄弟任务。
        """
        # 用 self.db 绑定的 engine 派生 session factory，测试 fixture（独立 engine）也能复用
        _session_factory = async_sessionmaker(
            self.db.bind, class_=AsyncSession, expire_on_commit=False,
        )

        sem = self._sem()
        meta = project.metadata_ or {}
        summaries = meta.get("scene_summaries", [])
        traits = meta.get("character_traits", [])
        extra_prompt = (version.prompt_overrides or {}).get("extra_prompt")
        mappings = version.mapping_snapshot or []
        intensity = project.intensity
        intent = project.intent
        era_target = project.era_target

        scenes = (await self.db.execute(
            select(AdaptationSceneResult)
            .where(AdaptationSceneResult.version_id == version.id)
            .order_by(AdaptationSceneResult.scene_index)
        )).scalars().all()
        # 快照只读字段，后续不再回查 ORM
        scene_specs = [
            {
                "id": s.id,
                "scene_index": s.scene_index,
                "scene_title": s.scene_title,
                "original_text": s.original_scene_text,
            }
            for s in scenes
        ]

        async def _one(spec: Dict[str, Any]):
            async with sem:
                await self._rewrite_one_isolated(
                    session_factory=_session_factory,
                    version_id=version.id,
                    scene_id=spec["id"],
                    scene_index=spec["scene_index"],
                    scene_title=spec["scene_title"],
                    original_text=spec["original_text"],
                    intensity=intensity, intent=intent, era_target=era_target,
                    prev_summary=summaries[spec["scene_index"] - 1] if spec["scene_index"] > 0 and spec["scene_index"] - 1 < len(summaries) else None,
                    traits=traits, mappings=mappings,
                    extra_prompt=extra_prompt,
                )

        results = await asyncio.gather(*[_one(s) for s in scene_specs], return_exceptions=True)
        # 兜底：捕获 _rewrite_one_isolated 本身的异常（按理 isolated 内部已全部 catch；
        # 这里防御性记录一笔）。
        for spec, r in zip(scene_specs, results):
            if isinstance(r, BaseException):
                logger.error("场 %s isolated task 异常未被内部处理: %r", spec["scene_index"], r)

        # 收尾：用独立 session 重新统计真实状态，避免 self.db 缓存的 ORM 与
        # 各场 isolated session 写入产生不一致。
        async with _session_factory() as s:
            counts = (await s.execute(
                select(AdaptationSceneResult.status, func.count())
                .where(AdaptationSceneResult.version_id == version.id)
                .group_by(AdaptationSceneResult.status)
            )).all()
            total = sum(c for _, c in counts)
            succeeded = next((c for st, c in counts if st == "done"), 0)
            failed = next((c for st, c in counts if st == "failed"), 0)
            if failed == 0:
                final_status = "done"
            elif succeeded == 0:
                final_status = "failed"
            else:
                final_status = "partial"
            await s.execute(
                update(AdaptationVersion)
                .where(AdaptationVersion.id == version.id)
                .values(
                    status=final_status,
                    completed_at=utcnow_naive(),
                    stats={
                        "total_scenes": total,
                        "succeeded": succeeded,
                        "failed": failed,
                    },
                )
            )
            await s.execute(
                update(AdaptationProject)
                .where(AdaptationProject.id == project.id)
                .values(status="done")
            )
            await s.commit()
        await event_bus.publish(version.id, {
            "event": "version_done", "version_id": version.id, "status": final_status,
        })

    async def _rewrite_one_isolated(
        self, *, session_factory, version_id: int, scene_id: int,
        scene_index: int, scene_title: Optional[str], original_text: str,
        intensity: int, intent: Optional[str], era_target: Optional[str],
        prev_summary: Optional[str], traits: List[Dict[str, Any]],
        mappings: List[Dict[str, Any]], extra_prompt: Optional[str],
    ) -> None:
        """单场独立 session 版本：标 running → LLM → 写结果，三次独立 commit。

        与 _rewrite_one 行为等价，但不共享 self.db；供 execute_full_run 并发使用。
        """
        # ① 标 running + SSE
        try:
            async with session_factory() as s:
                await s.execute(
                    update(AdaptationSceneResult)
                    .where(AdaptationSceneResult.id == scene_id)
                    .values(status="running", updated_at=utcnow_naive())
                )
                await s.commit()
        except Exception:
            logger.exception("场 %s 标 running 失败", scene_index)
        await event_bus.publish(version_id, {
            "event": "scene_running", "scene_index": scene_index,
        })

        # ② 跑 LLM
        rewritten_text: Optional[str] = None
        delta_pct: Optional[float] = None
        err: Optional[str] = None
        try:
            rewritten_text = await asyncio.wait_for(
                self.llm.rewrite_scene(
                    scene_text=original_text,
                    intensity=intensity,
                    intent=intent,
                    era_target=era_target,
                    mappings=mappings,
                    prev_scene_summary=prev_summary,
                    character_traits=traits,
                    extra_prompt=extra_prompt,
                    scene_title=scene_title,
                ),
                timeout=settings.ADAPTATION_PER_SCENE_TIMEOUT_SEC,
            )
            delta_pct = _delta_pct(original_text, rewritten_text)
            new_status = "done"
        except Exception as e:
            err = str(e)[:500]
            new_status = "failed"
            logger.exception("场 %s 改写失败", scene_index)

        # ③ 写结果（即使 LLM 失败也要落库为 failed，否则 UI 永远看到 running）
        try:
            async with session_factory() as s:
                # Core update 不触发 ORM onupdate=utcnow_naive，显式带 updated_at
                values: Dict[str, Any] = {"status": new_status, "updated_at": utcnow_naive()}
                if rewritten_text is not None:
                    values["rewritten_scene_text"] = rewritten_text
                    values["line_count_delta_pct"] = delta_pct
                if err is not None:
                    values["error"] = err
                await s.execute(
                    update(AdaptationSceneResult)
                    .where(AdaptationSceneResult.id == scene_id)
                    .values(**values)
                )
                await s.commit()
        except Exception:
            logger.exception("场 %s 写结果失败", scene_index)

        await event_bus.publish(version_id, {
            "event": "scene_done",
            "scene_index": scene_index,
            "status": new_status,
            "rewritten": rewritten_text,
            "error": err,
            "line_count_delta_pct": delta_pct,
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
            "type": "rerun", "at": utcnow_naive().isoformat(),
            "prompt": extra_prompt, "before": before, "after": scene.rewritten_scene_text,
        })
        scene.manual_edits = edits
        await self.db.commit()
        # commit 后 SQLAlchemy 会把 server-side onupdate 列（updated_at）标记 expired，
        # 路由层随后访问该属性会触发同步 lazy load 进而 MissingGreenlet。显式 refresh
        # 一次把全部列重新水合回 instance。
        await self.db.refresh(scene)
