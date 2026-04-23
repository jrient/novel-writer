#!/usr/bin/env python3
"""Extract style samples from both scripts.json (external reviewed) and
internal_signed_meta.json (internal signed), classify by theme, split into
dynamic/explanatory pools with genre + theme_tag metadata.

Outputs:
- style_samples_dynamic.json
- style_samples_explanatory.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from script_rubric.pipeline.theme_classifier import classify, load_config


PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "script_rubric" / "data" / "parsed"
OUTPUT_DIR = PROJECT_ROOT / "script_rubric" / "outputs"
CONFIG_PATH = PROJECT_ROOT / "script_rubric" / "config" / "theme_classification.yaml"
ARCHIVES_DIR = OUTPUT_DIR / "archives"
DRAMA_DIR = PROJECT_ROOT / "drama"

SAMPLE_MIN_CHARS = 200
SAMPLE_TARGET_CHARS = 500


# ─── Text cleaning ───────────────────────────────────────────────────────────

def clean_scene_text(text: str) -> str:
    """Strip 人物: lines, parenthetical character descriptions"""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.search(r"[（(].*：.*\+.*[）)]", stripped):
            continue
        if re.match(r"^\s*(出场)?人物[：:]", stripped):
            continue
        if "出场人物" in stripped:
            continue
        line = re.sub(r"[（(]注[：:].*?[）)]", "", line)
        out.append(line)
    return "\n".join(out)


def truncate_at_line(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rfind("\n")
    if cut > max_chars * 0.5:
        return text[:cut].rstrip()
    return text[:max_chars].rstrip()


def extract_first_scene(text_content: str) -> str | None:
    """Find first scene block(s); return cleaned truncated excerpt.
    If the first scene alone is too short, accumulates consecutive scene
    blocks until the excerpt reaches SAMPLE_MIN_CHARS.
    """
    markers = list(re.finditer(r"^\s*\d{1,2}-\d{1,2}", text_content, re.MULTILINE))
    if not markers:
        return None

    # Collect consecutive scenes until we have enough content
    scenes_text = []
    for i in range(min(5, len(markers))):
        start = markers[i].start()
        end = markers[i + 1].start() if i + 1 < len(markers) else start + 800
        scenes_text.append(text_content[start:end].strip())
        combined = "\n".join(scenes_text)
        cleaned = clean_scene_text(combined)
        excerpt = truncate_at_line(cleaned, SAMPLE_TARGET_CHARS)
        if len(excerpt) >= SAMPLE_MIN_CHARS:
            return excerpt

    return None


def extract_maiyoulian_excerpt(text: str) -> str | None:
    """Extract ~500-char prose opening after '\n1\n' section marker"""
    pos = text.find("\n1\n")
    if pos < 0:
        return None
    raw = text[pos + 3:]
    return truncate_at_line(raw, 450)


# ─── Loaders ─────────────────────────────────────────────────────────────────

def load_external_reviewed() -> list[dict]:
    """scripts.json → list of {title, text_content, genre, mean_score}"""
    path = DATA_DIR / "scripts.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for x in data:
        if x.get("status") != "签":
            continue
        text = x.get("text_content") or ""
        if len(text) < 1000:
            continue
        out.append({
            "title": x["title"],
            "text_content": text,
            "genre": x.get("genre") or "",
            "mean_score": x.get("mean_score"),
            "source": "external_reviewed",
        })
    return out


def load_internal_signed() -> list[dict]:
    """internal_signed_meta.json → list of {title, text_content, genre, mean_score=None}"""
    path = DATA_DIR / "internal_signed_meta.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for x in data:
        text = x.get("text_content") or ""
        if len(text) < 1000:
            continue
        out.append({
            "title": x["title"],
            "text_content": text,
            "genre": x.get("genre") or "",
            "mean_score": None,
            "source": "internal_signed",
        })
    return out


# ─── Golden quotes mining ────────────────────────────────────────────────────

def mine_dialogue_quotes(text: str, limit_per_script: int = 3) -> list[str]:
    """Pull 15-80 char lines that (a) contain emotion tag + dialogue, OR (b) start with △"""
    quotes = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "+" in line and "：" in line:
            continue
        if re.search(r"[（(].*：.*[+/）)]", line):
            continue
        if line.startswith("△") and 10 <= len(line) <= 60:
            quotes.add(line)
        if ("（" in line or "(" in line) and 15 <= len(line) <= 80:
            if ":" in line or "：" in line:
                quotes.add(line)
    return sorted(quotes, key=len, reverse=True)[:limit_per_script]


def mine_archive_quotes() -> list[str]:
    """From rubric archive JSONs, extract writing_dialogue evidence"""
    quotes = set()
    if not ARCHIVES_DIR.exists():
        return []
    for f in sorted(ARCHIVES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        ev = data.get("dimensions", {}).get("writing_dialogue", {}).get("evidence_from_text", [])
        for e in ev:
            if e and 10 < len(e) < 100:
                quotes.add(e)
    return sorted(quotes, key=len, reverse=True)[:15]


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(CONFIG_PATH)

    all_raw = load_external_reviewed() + load_internal_signed()
    print(f"Loaded {len(all_raw)} raw records from data sources")

    # Manual drama files (not in either JSON source)
    drama_entries = []
    huangzi_path = DRAMA_DIR / "动态漫：皇子.txt"
    if huangzi_path.exists():
        drama_entries.append({
            "title": "动态漫：皇子",
            "text_content": huangzi_path.read_text(encoding="utf-8"),
            "genre": "男频",
            "mean_score": 80.0,
            "source": "drama_manual",
        })
    maiyoulian_path = DRAMA_DIR / "解说漫：买榴莲.txt"
    if maiyoulian_path.exists():
        drama_entries.append({
            "title": "解说漫：买榴莲",
            "text_content": maiyoulian_path.read_text(encoding="utf-8"),
            "genre": "世情",
            "mean_score": None,
            "source": "drama_manual",
        })

    all_raw.extend(drama_entries)
    print(f"Added {len(drama_entries)} manual drama entries")

    # Deduplicate by title — keep the entry with the longest text_content
    seen: dict[str, dict] = {}
    for rec in all_raw:
        t = rec["title"]
        if t not in seen or len(rec["text_content"]) > len(seen[t]["text_content"]):
            seen[t] = rec
    all_raw = list(seen.values())
    print(f"After dedup: {len(all_raw)} unique records")

    dynamic_samples: list[dict] = []
    explanatory_samples: list[dict] = []
    dynamic_quotes: set[str] = set()
    explanatory_quotes: set[str] = set()
    unclassified = []

    for rec in all_raw:
        theme, st = classify(rec["title"], rec["text_content"], config)
        if not st:
            unclassified.append(rec["title"])
            continue

        # Excerpt extraction
        if rec["title"] == "解说漫：买榴莲":
            excerpt = extract_maiyoulian_excerpt(rec["text_content"])
        else:
            excerpt = extract_first_scene(rec["text_content"])
        if not excerpt:
            print(f"  SKIP (no excerpt): {rec['title']}")
            continue

        sample = {
            "title": rec["title"],
            "excerpt": excerpt,
            "genre": rec["genre"],
            "theme_tag": theme,
            "mean_score": rec["mean_score"],
            "source": rec["source"],
        }
        if st == "dynamic":
            dynamic_samples.append(sample)
            dynamic_quotes.update(mine_dialogue_quotes(rec["text_content"]))
        else:
            explanatory_samples.append(sample)
            explanatory_quotes.update(mine_dialogue_quotes(rec["text_content"]))

    # Add archive quotes to dynamic pool
    dynamic_quotes.update(mine_archive_quotes())

    # Handcrafted 买榴莲 quotes for explanatory (narration style — different voice)
    explanatory_quotes.update([
        "快递员敲门的时候，我正烧得浑身骨头缝都在疼。",
        "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
        "我扶着门框的手指骨节泛白，指甲死死抠进木头里。",
        "字字句句，像淬了毒的针，扎进我高烧脆弱的神经里。",
        "高烧让我浑身发冷，心却比这温度更冷。",
        "哀莫大于心死。原来就是这种感觉。",
        "没有愤怒的咆哮，没有歇斯底里的哭喊。只有一种极其清晰的、冷彻骨髓的平静。",
    ])

    # Cap quote lists to 30 each
    dynamic_quotes_list = sorted(dynamic_quotes, key=len, reverse=True)[:30]
    explanatory_quotes_list = sorted(explanatory_quotes, key=len, reverse=True)[:30]

    dynamic_output = {
        "script_type": "dynamic",
        "samples": dynamic_samples,
        "golden_quotes": dynamic_quotes_list,
    }
    explanatory_output = {
        "script_type": "explanatory",
        "samples": explanatory_samples,
        "golden_quotes": explanatory_quotes_list,
    }

    (OUTPUT_DIR / "style_samples_dynamic.json").write_text(
        json.dumps(dynamic_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_DIR / "style_samples_explanatory.json").write_text(
        json.dumps(explanatory_output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nDynamic pool:     {len(dynamic_samples)} samples, {len(dynamic_quotes_list)} quotes")
    print(f"Explanatory pool: {len(explanatory_samples)} samples, {len(explanatory_quotes_list)} quotes")
    if unclassified:
        print(f"\nUnclassified ({len(unclassified)}) — add to overrides if needed:")
        for t in unclassified:
            print(f"  - {t}")


if __name__ == "__main__":
    main()
