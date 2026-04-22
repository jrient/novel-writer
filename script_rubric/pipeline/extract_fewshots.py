#!/usr/bin/env python3
"""Extract style samples and golden quotes from rubric archives and drama files.

Generates:
- style_samples_dynamic.json (dynamic comic script style)
- style_samples_explanatory.json (explanatory/narration comic script style)
"""

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
ARCHIVES_DIR = PROJECT_ROOT / "script_rubric" / "outputs" / "archives"
SCRIPTS_JSON = PROJECT_ROOT / "script_rubric" / "data" / "parsed" / "scripts.json"
OUTPUT_DIR = PROJECT_ROOT / "script_rubric" / "outputs"
DRAMA_DIR = PROJECT_ROOT / "drama"


def extract_from_huangzi():
    """Extract samples and quotes from drama/动态漫：皇子.txt."""
    path = DRAMA_DIR / "动态漫：皇子.txt"
    content = path.read_text(encoding="utf-8")

    # Find actual scene headers (XX-YY pattern with space after)
    markers = [(m.start(), m.group().strip()) for m in re.finditer(
        r"^(\d{2}-\d+)\s+", content, re.MULTILINE)]

    samples = []

    # Sample 1: first scene (01-1), ~400 chars at line boundary
    if markers:
        start = markers[0][0]
        # Find the end of the 01-1 scene (next scene header)
        if len(markers) > 1:
            end = markers[1][0]
        else:
            end = start + 500
        excerpt = _clean_scene_text(content[start:end].strip())
        # Truncate to ~400 chars at line boundary
        excerpt = _truncate_at_line(excerpt, 400)
        samples.append({
            "title": "动态漫：皇子",
            "writing_dialogue_score": 8,
            "mean_score": 80.0,
            "excerpt": excerpt,
        })

    # Sample 2: second scene (01-2), ~300 chars at line boundary
    if len(markers) > 1:
        start = markers[1][0]
        if len(markers) > 2:
            end = markers[2][0]
        else:
            end = start + 400
        excerpt = _clean_scene_text(content[start:end].strip())
        excerpt = _truncate_at_line(excerpt, 300)
        samples.append({
            "title": "动态漫：皇子",
            "writing_dialogue_score": 8,
            "mean_score": 80.0,
            "excerpt": excerpt,
        })

    # Golden quotes from 皇子
    golden_quotes = _extract_quotes_from_huangzi(content)

    return samples, golden_quotes


def _clean_scene_text(text):
    """Remove character description and stage direction lines embedded in scene text."""
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip lines with character descriptions containing + separator
        if re.search(r"[（(].*：.*\+.*[）)]", stripped):
            continue
        # Skip lines like "出场人物：..." or "人物：..." (standalone)
        if re.match(r"^\s*(出场)?人物[：:]", stripped):
            continue
        # Skip lines that are scene headers with character list
        # e.g. "场景：天界  日/内  出场人物：昭昭、天君..."
        if "出场人物" in stripped:
            continue
        # Remove embedded parenthetical notes like "（注：...）" from action lines
        # e.g. "△ 豪华宽敞的餐厅里...（注：桑柔柔不出声，不露脸。）"
        line = re.sub(r"[（(]注[：:].*?[）)]", "", line)
        cleaned.append(line)
    return "\n".join(cleaned)


def _truncate_at_line(text, max_chars):
    """Truncate text at a line boundary near max_chars."""
    if len(text) <= max_chars:
        return text
    # Find last newline within range
    cut = text[:max_chars].rfind("\n")
    if cut > max_chars * 0.5:
        return text[:cut].rstrip()
    return text[:max_chars].rstrip()


def _extract_quotes_from_huangzi(content):
    """Extract golden quotes from 皇子: action lines and emotional dialogue."""
    quotes = set()

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        # Skip lines containing character descriptions (with + separator, common in stage directions)
        if "+" in line and "：" in line:
            continue
        # Skip lines with role description patterns like "(角色：外貌/服装/身份)"
        if re.search(r"[（(].*：.*[+/）)]", line):
            continue

        # △ action lines: start with △, 10-60 chars
        if line.startswith("△") and 10 <= len(line) <= 60:
            quotes.add(line)

        # Dialogue lines with emotion tags (parentheses), 15-80 chars
        if ("（" in line or "(" in line) and 15 <= len(line) <= 80:
            # Must be a dialogue line (contains colon or is character speech)
            if ":" in line or "：" in line:
                quotes.add(line)

    # Deduplicate and limit
    result = sorted(quotes, key=len, reverse=True)[:20]
    return result


def extract_from_archives():
    """Extract golden quotes from rubric archives writing_dialogue evidence."""
    golden_quotes = set()

    for archive_file in sorted(ARCHIVES_DIR.glob("*.json")):
        try:
            with open(archive_file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

        wd = data.get("dimensions", {}).get("writing_dialogue", {})
        evidence = wd.get("evidence_from_text", [])
        for ev in evidence:
            if ev and len(ev) < 100:
                golden_quotes.add(ev)

    return sorted(golden_quotes, key=lambda x: len(x), reverse=True)[:10]


def extract_from_scripts_json():
    """Extract supplementary samples from qualified scripts in scripts.json."""
    with open(SCRIPTS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    samples = []
    # Find scripts with writing_dialogue >= 7 AND status=签
    # Cross-reference with archives
    archive_wd = {}
    for archive_file in sorted(ARCHIVES_DIR.glob("*.json")):
        try:
            with open(archive_file, encoding="utf-8") as f:
                adata = json.load(f)
            wd_score = adata.get("dimensions", {}).get("writing_dialogue", {}).get("score", 0)
            archive_wd[adata["title"]] = (wd_score, adata.get("mean_score", 0))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue

    for item in data:
        if item.get("status") != "签":
            continue
        if not item.get("text_content"):
            continue

        title = item["title"]
        # Check if this script has writing_dialogue >= 7
        wd_info = archive_wd.get(title)
        if wd_info is None:
            continue
        wd_score, mean_score = wd_info
        if wd_score < 7:
            continue

        # Try to extract scene body
        content = item["text_content"]
        match = re.search(r"^(\d{1,2}-\d+)\s+", content, re.MULTILINE)
        if match:
            start = match.start()
            # Find next scene marker
            next_match = re.search(
                r"^(\d{1,2}-\d+)\s+", content[match.end():], re.MULTILINE)
            if next_match:
                end = match.end() + next_match.start()
            else:
                end = start + 600

            excerpt = _clean_scene_text(content[start:end].strip())
            excerpt = _truncate_at_line(excerpt, 500)

            if len(excerpt) > 200:
                samples.append({
                    "title": title,
                    "writing_dialogue_score": wd_score,
                    "mean_score": mean_score,
                    "excerpt": excerpt,
                })

    return samples


def extract_explanatory():
    """Extract explanatory (narration) comic sample and golden quotes."""
    path = DRAMA_DIR / "解说漫：买榴莲.txt"
    content = path.read_text(encoding="utf-8")

    # Find section 1 start: '\n1\n'
    pos = content.find("\n1\n")
    if pos < 0:
        raise ValueError("Cannot find section 1 marker in 买榴莲")

    start = pos + 3  # Skip '\n1\n'
    # Take 450 chars at line boundary
    raw = content[start:]
    excerpt = _truncate_at_line(raw, 450)

    sample = {
        "title": "解说漫：买榴莲",
        "excerpt": excerpt,
    }

    # Handcrafted golden quotes
    golden_quotes = [
        "快递员敲门的时候，我正烧得浑身骨头缝都在疼。",
        "艰难地裹着羽绒服，扶着墙挪到玄关。",
        "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
        "我胃里一阵翻江倒海，猛地捂住嘴。",
        "我扶着门框的手指骨节泛白，指甲死死抠进木头里。",
        "字字句句，像淬了毒的针，扎进我高烧脆弱的神经里。",
        "我冷冷地看着这对父子。",
        "高烧让我浑身发冷，心却比这温度更冷。",
        "哀莫大于心死。原来就是这种感觉。",
        "没有愤怒的咆哮，没有歇斯底里的哭喊。只有一种极其清晰的、冷彻骨髓的平静。",
        "嘴角勾起一抹极其温柔的笑。",
        "动作单调，重复。",
        "深夜。万籁俱寂。只有冰柜压缩机运转的嗡嗡声。",
        "我的手指已经被坚硬的榴莲壳磨出了血泡。",
        "他咒骂了一句，转身缩回了主卧。",
        "周大海浑身一哆嗦。",
    ]

    return sample, golden_quotes


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Dynamic comic style samples ----
    huangzi_samples, huangzi_quotes = extract_from_huangzi()
    archive_quotes = extract_from_archives()
    supplementary_samples = extract_from_scripts_json()

    # Combine golden quotes (huangzi + archives), deduplicate, limit
    all_dynamic_quotes = list(set(huangzi_quotes + archive_quotes))
    all_dynamic_quotes.sort(key=len, reverse=True)
    all_dynamic_quotes = all_dynamic_quotes[:30]

    dynamic_output = {
        "script_type": "dynamic",
        "samples": huangzi_samples + supplementary_samples,
        "golden_quotes": all_dynamic_quotes,
    }

    dynamic_path = OUTPUT_DIR / "style_samples_dynamic.json"
    with open(dynamic_path, "w", encoding="utf-8") as f:
        json.dump(dynamic_output, f, ensure_ascii=False, indent=2)
    print(f"Wrote {dynamic_path}")
    print(f"  samples: {len(dynamic_output['samples'])}")
    print(f"  golden_quotes: {len(dynamic_output['golden_quotes'])}")

    # ---- Explanatory comic style samples ----
    explanatory_sample, explanatory_quotes = extract_explanatory()

    explanatory_output = {
        "script_type": "explanatory",
        "samples": [explanatory_sample],
        "golden_quotes": explanatory_quotes,
    }

    explanatory_path = OUTPUT_DIR / "style_samples_explanatory.json"
    with open(explanatory_path, "w", encoding="utf-8") as f:
        json.dump(explanatory_output, f, ensure_ascii=False, indent=2)
    print(f"Wrote {explanatory_path}")
    print(f"  samples: {len(explanatory_output['samples'])}")
    print(f"  golden_quotes: {len(explanatory_output['golden_quotes'])}")


if __name__ == "__main__":
    main()
