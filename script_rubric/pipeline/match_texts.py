from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from script_rubric.models import ScriptRecord


MATCH_THRESHOLD = 0.5


@dataclass
class MatchResult:
    records: list[ScriptRecord]
    total: int
    matched: int
    unmatched_titles: list[str] = field(default_factory=list)
    match_details: list[dict] = field(default_factory=list)

    def to_report(self) -> str:
        pct = f"{self.matched/self.total*100:.0f}%" if self.total > 0 else "N/A"
        lines = [
            "# Text Match Report",
            f"Total scripts: {self.total}",
            f"Matched: {self.matched} ({pct})",
            f"Unmatched: {self.total - self.matched}",
            "",
        ]
        if self.unmatched_titles:
            lines.append("## Unmatched titles:")
            for t in self.unmatched_titles:
                lines.append(f"  - {t}")
        if self.match_details:
            lines.append("")
            lines.append("## Match details:")
            for d in self.match_details:
                lines.append(f"  - {d['title'][:40]} → {d['file'][:40]} (score: {d['score']:.2f})")
        return "\n".join(lines)


def fuzzy_match_score(title: str, filename: str) -> float:
    name = filename.rsplit(".", 1)[0] if "." in filename else filename
    title_clean = title.strip().strip("《》 ")
    name_clean = name.strip().strip("《》 ")
    return SequenceMatcher(None, title_clean, name_clean).ratio()


def match_texts(
    records: list[ScriptRecord],
    drama_dir: Path,
) -> MatchResult:
    if not drama_dir.exists():
        return MatchResult(
            records=records, total=len(records), matched=0,
            unmatched_titles=[r.title for r in records],
        )

    txt_files = {f.name: f for f in drama_dir.glob("*.txt")}

    matched_count = 0
    unmatched: list[str] = []
    details: list[dict] = []

    for record in records:
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
            details.append({
                "title": record.title,
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
    )
