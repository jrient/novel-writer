#!/usr/bin/env python3
"""CLI tool to regenerate a single episode's content for a drama project.

Does NOT mutate the database; prints the regenerated text to stdout (or a
file if --out is given). Used to validate new sample pool + genre-aware
retrieval against an existing project.

Usage:
    python scripts/regen_episode.py --project-id 8 --episode-index 0
    python scripts/regen_episode.py --project-id 8 --episode-index 0 --out regen_8_ep1.txt
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend is importable
BACKEND = Path(__file__).parent.parent / "backend"
if BACKEND.exists():
    sys.path.insert(0, str(BACKEND))
else:
    # Inside Docker container, app is already in sys.path via PYTHONPATH
    # or /app is the working directory
    sys.path.insert(0, "/app")

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.script_project import ScriptProject
from app.models.script_session import ScriptSession
from app.routers.drama import _guess_genre_from_concept
from app.services.script_ai_service import ScriptAIService


async def regen(project_id: int, episode_index: int, out_path: str | None):
    engine = create_async_engine(settings.DATABASE_URL)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        project = (await db.execute(
            select(ScriptProject).where(ScriptProject.id == project_id)
        )).scalar_one_or_none()
        if not project:
            print(f"ERROR: project {project_id} not found", file=sys.stderr)
            return 1

        session = (await db.execute(
            select(ScriptSession).where(ScriptSession.project_id == project_id)
        )).scalar_one_or_none()
        if not session or not session.outline_draft:
            print(f"ERROR: project {project_id} has no outline_draft", file=sys.stderr)
            return 1

        sections = session.outline_draft.get("sections", [])
        if episode_index < 0 or episode_index >= len(sections):
            print(f"ERROR: episode_index {episode_index} out of range [0, {len(sections)})", file=sys.stderr)
            return 1

        current_ep = sections[episode_index]
        prev_ep = sections[episode_index - 1] if episode_index > 0 else None
        next_ep = sections[episode_index + 1] if episode_index < len(sections) - 1 else None

        summary_data = session.summary or {}
        main_characters = summary_data.get("主要角色", [])
        core_conflict = summary_data.get("核心冲突", "")
        style_tone = summary_data.get("风格基调", "")
        outline_summary = session.outline_draft.get("summary", "")

        _proj_settings = (project.metadata_ or {}).get("settings", {})
        genre = _guess_genre_from_concept(project.concept) if project.concept else ""
        print(f"[info] project={project_id} title={project.title!r} genre={genre!r} script_type={project.script_type}", file=sys.stderr)
        print(f"[info] episode_index={episode_index} current_title={current_ep.get('title')!r}", file=sys.stderr)
        print("[info] streaming...", file=sys.stderr)

        ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)
        full = ""
        async for chunk in ai_service.generate_episode_content(
            title=project.title,
            outline_summary=outline_summary,
            main_characters=main_characters,
            core_conflict=core_conflict,
            style_tone=style_tone,
            episode_index=episode_index,
            total_episodes=len(sections),
            current_episode=current_ep,
            prev_episode=prev_ep,
            next_episode=next_ep,
            script_type=project.script_type,
            genre=genre,
        ):
            full += chunk
            sys.stderr.write(".")
            sys.stderr.flush()
        sys.stderr.write("\n")

        if out_path:
            Path(out_path).write_text(full, encoding="utf-8")
            print(f"[info] saved to {out_path}", file=sys.stderr)
        else:
            print(full)

    await engine.dispose()
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project-id", type=int, required=True)
    p.add_argument("--episode-index", type=int, required=True)
    p.add_argument("--out", type=str, default=None, help="Optional output file path")
    args = p.parse_args()
    sys.exit(asyncio.run(regen(args.project_id, args.episode_index, args.out)))


if __name__ == "__main__":
    main()
