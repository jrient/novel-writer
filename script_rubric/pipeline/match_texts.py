from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from script_rubric.models import ScriptRecord
from script_rubric.pipeline.fetch_docx import fetch_many


MATCH_THRESHOLD = 0.5

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    records: list[ScriptRecord]
    total: int
    matched: int
    unmatched_titles: list[str] = field(default_factory=list)
    match_details: list[dict] = field(default_factory=list)
    docx_success: int = 0
    docx_failed: dict[str, str] = field(default_factory=dict)  # title -> error
    drama_matched: int = 0

    def to_report(self) -> str:
        pct = f"{self.matched/self.total*100:.0f}%" if self.total > 0 else "N/A"
        lines = [
            "# Text Match Report",
            f"Total scripts: {self.total}",
            f"Matched: {self.matched} ({pct})",
            f"  - via Docx (feishu):  {self.docx_success}",
            f"  - via drama dir:      {self.drama_matched}",
            f"Unmatched: {self.total - self.matched}",
            "",
        ]
        if self.docx_failed:
            lines.append("## Docx fetch failures:")
            for title, err in self.docx_failed.items():
                lines.append(f"  - {title[:50]} → {err[:100]}")
            lines.append("")
        if self.unmatched_titles:
            lines.append("## Missing text (no docx + no drama match):")
            for t in self.unmatched_titles:
                lines.append(f"  - {t}")
            lines.append("")
        if self.match_details:
            lines.append("## Match details:")
            for d in self.match_details:
                src = d.get("source", "?")
                if src == "docx":
                    lines.append(f"  - [docx] {d['title'][:40]} → token {d.get('docx_token','')[:20]}")
                else:
                    lines.append(
                        f"  - [drama] {d['title'][:40]} → {d.get('file','')[:40]} (score: {d.get('score',0):.2f})"
                    )
        return "\n".join(lines)


def fuzzy_match_score(title: str, filename: str) -> float:
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    title_clean = title.strip().strip("《》 ")
    name_clean = name.strip().strip("《》 ")
    return SequenceMatcher(None, title_clean, name_clean).ratio()


def match_texts(
    records: list[ScriptRecord],
    drama_dir: Path,
    force_refresh_docx: bool = False,
) -> MatchResult:
    """为每条 ScriptRecord 附上 text_content。

    优先级：
      1. record.docx_token → 飞书拉正文（命中本地 cache 则跳过 API）
      2. 否则在 drama_dir 下 fuzzy match .txt
      3. 都失败 → 记入 unmatched_titles
    """
    # === Stage 1: 批量拉 docx ===
    docx_tokens = [r.docx_token for r in records if r.docx_token]
    docx_content_map: dict[str, str] = {}
    docx_failed_tokens: dict[str, str] = {}
    if docx_tokens:
        docx_content_map, docx_failed_tokens = fetch_many(
            docx_tokens, force=force_refresh_docx
        )

    # === Stage 2: drama_dir fallback 准备 ===
    txt_files: dict[str, Path] = {}
    if drama_dir.exists():
        txt_files = {f.name: f for f in drama_dir.glob("*.txt")}

    matched_count = 0
    docx_success = 0
    drama_matched = 0
    unmatched: list[str] = []
    docx_failed_by_title: dict[str, str] = {}
    details: list[dict] = []

    for record in records:
        # Priority 1: docx
        if record.docx_token:
            content = docx_content_map.get(record.docx_token)
            if content:
                record.text_content = content
                record.text_file = f"docx:{record.docx_token}"
                matched_count += 1
                docx_success += 1
                details.append({
                    "title": record.title,
                    "source": "docx",
                    "docx_token": record.docx_token,
                })
                continue
            # docx 拉取失败，落到 fallback
            err = docx_failed_tokens.get(record.docx_token, "unknown")
            docx_failed_by_title[record.title] = err

        # Priority 2: drama_dir fuzzy match
        best_file = None
        best_score = 0.0
        for fname, fpath in txt_files.items():
            score = fuzzy_match_score(record.title, fname)
            if score > best_score:
                best_score = score
                best_file = fpath

        if best_file and best_score >= MATCH_THRESHOLD:
            record.text_content = best_file.read_text(encoding="utf-8")
            record.text_file = best_file.name
            matched_count += 1
            drama_matched += 1
            details.append({
                "title": record.title,
                "source": "drama",
                "file": best_file.name,
                "score": best_score,
            })
        else:
            unmatched.append(record.title)

    return MatchResult(
        records=records,
        total=len(records),
        matched=matched_count,
        unmatched_titles=unmatched,
        match_details=details,
        docx_success=docx_success,
        docx_failed=docx_failed_by_title,
        drama_matched=drama_matched,
    )
