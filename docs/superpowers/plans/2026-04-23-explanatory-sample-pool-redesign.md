# 解说漫样本池重建与 genre 感知抽样 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复剧本 8 第一集"干巴"问题——重建解说漫/动态漫样本池（合并 67 外部评分 + 20 内部签约 = 84 条），按题材质感分池，StyleGuard 支持 genre 感知抽样，并提供 CLI 验证工具重新生成剧本 8 第一集对照老师评价。

**Architecture:** 数据层面：`extract_fewshots.py` 合并 `scripts.json` + `internal_signed_meta.json`，按 `theme_tag` 分 dynamic/explanatory 两池；服务层面：`StyleGuard.get_style_samples/build_style_context` 加 `genre` 参数，优先同 genre 回退同 script_type；链路层面：`ScriptAIService.generate_episode_content` 接收 genre 并透传；工具层面：`scripts/regen_episode.py` 直接复用 drama.py 的 async 流程做离线验证。

**Tech Stack:** Python 3.11 + FastAPI + SQLAlchemy（现有）+ pytest + PyYAML（theme 分类白名单）

---

## 前置数据（已完成，无需再做）

- `script_rubric/data/parsed/internal_signed_meta.json` 已拉取到位（20 份已签约剧本 + 全文，约 73 万字）。gitignore 覆盖了 `script_rubric/data/`，所以此文件仅本地存在。若需在其他机器复现，可重跑 `data/get_feishu_doc.py` + 解析（不在本 plan 范围内）。

## 文件结构

### 新增
- `script_rubric/config/theme_classification.yaml` — 人工主题白名单（兜底）
- `script_rubric/pipeline/theme_classifier.py` — 主题自动分类器
- `script_rubric/tests/test_theme_classifier.py` — 分类器单元测试
- `scripts/regen_episode.py` — CLI 工具：对指定 project_id + episode_index 重新生成 episode_content

### 修改
- `script_rubric/pipeline/extract_fewshots.py` — 合并两个数据源、按 theme 分池、输出带 genre/theme_tag 字段
- `script_rubric/outputs/style_samples_dynamic.json` — 重生成
- `script_rubric/outputs/style_samples_explanatory.json` — 重生成
- `backend/app/services/style_guard.py` — `get_style_samples` 加 `genre`，`build_style_context` 同步；返回结构统一为 `list[dict]`
- `backend/app/services/script_ai_service.py` — `_build_episode_user_prompt` 接收 `genre`，透传 StyleGuard；`generate_episode_content` 加 `genre` 参数
- `backend/app/routers/drama.py:session_expand_episode` — 从 project.concept 解析 genre 并传入 AIService
- `backend/tests/test_style_guard.py` — 更新断言以匹配新返回结构
- `backend/tests/test_drama_ai_service.py` — 加 episode_content genre 透传断言

### 不变
- `script_rubric/data/parsed/scripts.json`
- `HandbookProvider` 及 handbook 注入链路
- 前端 / 大纲生成 / DB schema

---

## Task 1: theme_classifier 与白名单

**Files:**
- Create: `script_rubric/config/theme_classification.yaml`
- Create: `script_rubric/pipeline/theme_classifier.py`
- Test: `script_rubric/tests/test_theme_classifier.py`

- [ ] **Step 1: 写 yaml 白名单（人工硬指定）**

Create `script_rubric/config/theme_classification.yaml`:

```yaml
# 人工白名单：标题精确匹配优先于关键字规则
# theme_tag 取值: urban | rebirth_modern | ai_realperson | xianxia | historical | family | cute_baby
# script_type 映射:
#   dynamic:      xianxia, historical, cute_baby(玄幻向)
#   explanatory:  urban, rebirth_modern, ai_realperson, family, cute_baby(都市向)

overrides:
  # --- 明确解说漫方向 ---
  "改编Ai真人剧《谋妃千岁》大纲小传前三集": {theme_tag: ai_realperson, script_type: explanatory}
  "改编AI真人剧《嫡女贵凰：重生毒妃狠绝色》（1）": {theme_tag: ai_realperson, script_type: explanatory}
  "改编AI真人剧《一世容安》一卡": {theme_tag: ai_realperson, script_type: explanatory}
  "改编AI真人剧《日久成瘾：撩妻总裁轻点宠》 人设大纲一卡": {theme_tag: ai_realperson, script_type: explanatory}
  "改编ai真人剧《帝国老公狠狠爱》人设+大纲+一卡": {theme_tag: ai_realperson, script_type: explanatory}
  "《八零福星俏娇妻》": {theme_tag: rebirth_modern, script_type: explanatory}
  "改编ai真人剧《重生之小三疯了我笑了》人设大纲+前三集": {theme_tag: rebirth_modern, script_type: explanatory}
  "ai仿真人 我走后，他们的橙子喂了猪1-10": {theme_tag: family, script_type: explanatory}
  "ai仿真人 出租狂飙1-10": {theme_tag: urban, script_type: explanatory}
  "ai仿真人 撕碎闺蜜后，我成了靳总心尖宠1-10": {theme_tag: urban, script_type: explanatory}
  "副本《我的蚀骨之恨你来解》1-60集完本4.7修改": {theme_tag: rebirth_modern, script_type: explanatory}
  "【原创全本】男友全家占我房，我反手找大哥上门清理门户": {theme_tag: family, script_type: explanatory}
  "《穿成大佬黑月光，在种田文里稳定发疯》": {theme_tag: rebirth_modern, script_type: explanatory}
  "修改《吃了饺子后，我和婆婆同时怀孕》1-42集完本": {theme_tag: family, script_type: explanatory}
  "定版：霜雪伴晚筝（女频虐恋）": {theme_tag: rebirth_modern, script_type: explanatory}
  "苍苍白发对红妆（修）": {theme_tag: rebirth_modern, script_type: explanatory}

  # --- 明确动态漫方向 ---
  "动态漫：皇子": {theme_tag: xianxia, script_type: dynamic}
  "《天降魔丸，纨绔爹爹被逼成栋梁！》": {theme_tag: xianxia, script_type: dynamic}
  "《天降魔丸，纨绔爹爹被逼成栋梁！》1-35集(2)": {theme_tag: xianxia, script_type: dynamic}
  "《棺边低语》前三集": {theme_tag: xianxia, script_type: dynamic}
  "《棺边低语》一卡": {theme_tag: xianxia, script_type: dynamic}
  "大明大纲+小传+全60集": {theme_tag: historical, script_type: dynamic}
  "封神：只想跑路的我，被人皇偷听了1-30": {theme_tag: xianxia, script_type: dynamic}
  "鉴宝大玩家2": {theme_tag: urban, script_type: dynamic}  # 都市但偏爽文
  "文道1-30": {theme_tag: xianxia, script_type: dynamic}
  "《心术》一卡2.1": {theme_tag: urban, script_type: dynamic}
  "《重生归来，权势滔天》1-65，完本（修改2_ 0）": {theme_tag: urban, script_type: dynamic}
  "姐，咱家南瓜成精了！4.19 修": {theme_tag: xianxia, script_type: dynamic}

  # --- 买榴莲：解说漫第一人称叙事体，单独样本 ---
  "解说漫：买榴莲": {theme_tag: urban, script_type: explanatory}

# 关键字规则（仅用于不在 overrides 中的剧本）
keyword_rules:
  - keywords: ["AI真人", "ai真人", "AI仿真", "ai仿真", "Ai真人", "Ai仿真"]
    theme_tag: ai_realperson
    script_type: explanatory
  - keywords: ["修真", "玄幻", "仙", "神", "道", "法宝", "大帝", "炼"]
    theme_tag: xianxia
    script_type: dynamic
    content_check: true  # 需 excerpt 命中才算
  - keywords: ["皇", "朝", "太子", "将军", "宫"]
    theme_tag: historical
    script_type: dynamic
    content_check: true
  - keywords: ["萌宝", "爹爹", "小祖宗"]
    theme_tag: cute_baby
    script_type: dynamic  # 萌宝默认玄幻向；如需都市向须进 overrides
```

- [ ] **Step 2: 写失败测试**

Create `script_rubric/tests/__init__.py` (empty file).

Create `script_rubric/tests/test_theme_classifier.py`:

```python
"""theme_classifier 单元测试"""
from pathlib import Path
import pytest

from script_rubric.pipeline.theme_classifier import classify, load_config


CONFIG_PATH = Path(__file__).parent.parent / "config" / "theme_classification.yaml"


def test_override_exact_match():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("改编Ai真人剧《谋妃千岁》大纲小传前三集", text_content="", config=cfg)
    assert theme == "ai_realperson"
    assert st == "explanatory"


def test_keyword_ai_realperson_not_in_override():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("原创AI仿真人短剧《未知新稿》", text_content="", config=cfg)
    assert theme == "ai_realperson"
    assert st == "explanatory"


def test_keyword_xianxia_requires_content_check():
    cfg = load_config(CONFIG_PATH)
    # Title alone with "神" but no xianxia content → should NOT trigger xianxia
    theme, st = classify("《神秘的邻居》", text_content="这是一个都市故事，主角开公司。", config=cfg)
    assert theme != "xianxia" or st != "dynamic"

    # Title + xianxia content → trigger xianxia
    theme2, st2 = classify("《无名之辈》", text_content="他突破到了金仙境界，法宝光芒大作。炼丹炉火焰翻涌。", config=cfg)
    assert theme2 == "xianxia"
    assert st2 == "dynamic"


def test_unknown_defaults_to_none():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("完全不认识的标题", text_content="完全不相关内容", config=cfg)
    assert theme is None
    assert st is None
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest script_rubric/tests/test_theme_classifier.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'script_rubric.pipeline.theme_classifier'`

- [ ] **Step 4: 写最小实现**

Create `script_rubric/pipeline/theme_classifier.py`:

```python
"""主题分类器：把剧本标题 + 正文映射到 (theme_tag, script_type)

优先级：
1. overrides 里精确匹配的标题 → 直接使用
2. keyword_rules 按顺序检查；规则命中关键字后，若 content_check=true 还需 text_content 也命中才生效
3. 都未命中 → (None, None)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


def load_config(path: Path) -> dict:
    """从 yaml 读取配置"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify(title: str, text_content: str, config: dict) -> tuple[Optional[str], Optional[str]]:
    """返回 (theme_tag, script_type)；都为 None 表示无法分类"""
    overrides = config.get("overrides") or {}
    if title in overrides:
        o = overrides[title]
        return o.get("theme_tag"), o.get("script_type")

    title_lower = title
    content_lower = text_content or ""
    for rule in config.get("keyword_rules") or []:
        keywords = rule.get("keywords") or []
        hit_title = any(k in title_lower for k in keywords)
        if not hit_title:
            continue
        if rule.get("content_check"):
            hit_content = any(k in content_lower for k in keywords)
            if not hit_content:
                continue
        return rule.get("theme_tag"), rule.get("script_type")

    return None, None
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest script_rubric/tests/test_theme_classifier.py -v`

Expected: 4 passed

- [ ] **Step 6: 确认 pyyaml 在容器中可用**

Run: `docker exec novel-writer-backend python -c "import yaml; print(yaml.__version__)"`

Expected: prints version (already installed — pyyaml is a FastAPI transitive dep). If fails, add `pyyaml` to `backend/requirements.txt`.

- [ ] **Step 7: Commit**

```bash
cd /data/project/novel-writer
git add script_rubric/config/theme_classification.yaml \
        script_rubric/pipeline/theme_classifier.py \
        script_rubric/tests/__init__.py \
        script_rubric/tests/test_theme_classifier.py
git commit -m "feat(rubric): add theme classifier + override/keyword config

Classifies scripts into (theme_tag, script_type) via title overrides first,
keyword rules second. content_check flag prevents false positives on
generic titles that share words with xianxia/historical vocab.

Constraint: No automatic classification without explicit override for ambiguous titles
Confidence: high
Scope-risk: narrow"
```

---

## Task 2: 重写 extract_fewshots.py 合并数据源

**Files:**
- Modify: `script_rubric/pipeline/extract_fewshots.py`

- [ ] **Step 1: 备份现有脚本（观感用，不阻塞）**

Run: `cp script_rubric/pipeline/extract_fewshots.py /tmp/extract_fewshots_old.py`

- [ ] **Step 2: 写新脚本完整实现（替换现有文件）**

Overwrite `script_rubric/pipeline/extract_fewshots.py`:

```python
#!/usr/bin/env python3
"""Extract style samples from both scripts.json (外部评审) and
internal_signed_meta.json (内部签约), classify by theme, split into
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
    """Find first '1-1' / '01-1' scene block; return cleaned truncated excerpt.
    Returns None if no scene marker found or excerpt too short.
    """
    m = re.search(r"^\s*(\d{1,2}-\d+)\s", text_content, re.MULTILINE)
    if not m:
        return None
    start = m.start()
    next_m = re.search(r"^\s*(\d{1,2}-\d+)\s", text_content[m.end():], re.MULTILINE)
    end = m.end() + next_m.start() if next_m else start + 800
    raw = text_content[start:end].strip()
    cleaned = clean_scene_text(raw)
    excerpt = truncate_at_line(cleaned, SAMPLE_TARGET_CHARS)
    if len(excerpt) < SAMPLE_MIN_CHARS:
        return None
    return excerpt


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


def load_drama_huangzi() -> dict | None:
    """Manual sample: drama/动态漫：皇子.txt"""
    path = DRAMA_DIR / "动态漫：皇子.txt"
    if not path.exists():
        return None
    return {
        "title": "动态漫：皇子",
        "text_content": path.read_text(encoding="utf-8"),
        "genre": "男频",
        "mean_score": 80.0,
        "source": "drama_manual",
    }


def load_drama_maiyoulian() -> dict | None:
    """Manual sample: drama/解说漫：买榴莲.txt (narration prose, not scene format)"""
    path = DRAMA_DIR / "解说漫：买榴莲.txt"
    if not path.exists():
        return None
    return {
        "title": "解说漫：买榴莲",
        "text_content": path.read_text(encoding="utf-8"),
        "genre": "世情",
        "mean_score": None,
        "source": "drama_manual",
    }


# ─── Excerpt extraction for 买榴莲 (prose, no scene markers) ─────────────────

def extract_maiyoulian_excerpt(text: str) -> str | None:
    """Extract ~500-char prose opening after '\n1\n' section marker"""
    pos = text.find("\n1\n")
    if pos < 0:
        return None
    raw = text[pos + 3:]
    return truncate_at_line(raw, 450)


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

    all_raw = (
        load_external_reviewed()
        + load_internal_signed()
        + [s for s in (load_drama_huangzi(), load_drama_maiyoulian()) if s]
    )
    print(f"Loaded {len(all_raw)} raw records")

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

    # Add archive quotes (existing 金句 source) to dynamic pool
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
```

- [ ] **Step 3: 运行脚本并检查输出**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m script_rubric.pipeline.extract_fewshots`

Expected output (approximate):
```
Loaded 70+ raw records
Dynamic pool:     10-15 samples, 30 quotes
Explanatory pool: 12-18 samples, 20+ quotes
Unclassified (N) — ...
```

If "Unclassified" list includes titles you care about, add them to `theme_classification.yaml` overrides and re-run.

- [ ] **Step 4: 抽查两个输出 JSON 确认质量**

Run:
```bash
docker exec novel-writer-backend python -c "
import json
for f in ['style_samples_dynamic.json', 'style_samples_explanatory.json']:
    d = json.load(open(f'script_rubric/outputs/{f}'))
    print(f'=== {f} ===')
    print(f'  samples: {len(d[\"samples\"])}')
    for s in d['samples']:
        print(f\"    [{s.get(\\\"genre\\\")}/{s.get(\\\"theme_tag\\\")}] {s['title'][:40]} (mean={s.get(\\\"mean_score\\\")})\")
    print(f'  quotes: {len(d[\"golden_quotes\"])}')
    print()
"
```

Expected: 解说漫池里出现 AI 仿真人剧 + 男友全家占我房 + 蚀骨之恨 等；动态漫池里没有 AI 仿真人剧。

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer
git add script_rubric/pipeline/extract_fewshots.py \
        script_rubric/outputs/style_samples_dynamic.json \
        script_rubric/outputs/style_samples_explanatory.json
git commit -m "refactor(rubric): rebuild sample pools by theme, not by source_type

Merges scripts.json (external, reviewed) + internal_signed_meta.json
(internal, 已签约) into one stream, classifies via theme_classifier, then
splits into dynamic (玄幻/修真/历史) vs explanatory (都市/重生/AI真人剧).
Each sample now carries genre + theme_tag for downstream genre-aware
retrieval.

Constraint: AI仿真人剧 belong in explanatory pool despite having 分场剧本 format
Rejected: Keep writing_dialogue>=7 filter | internal_signed samples have no score, would exclude them all
Confidence: high
Scope-risk: narrow
Directive: Any new sample with ambiguous theme must be added to theme_classification.yaml overrides, not left to keyword rules alone"
```

---

## Task 3: StyleGuard 支持 genre 感知抽样

**Files:**
- Modify: `backend/app/services/style_guard.py`
- Modify: `backend/tests/test_style_guard.py`

- [ ] **Step 1: 更新现有测试以匹配新返回结构**

Replace `backend/tests/test_style_guard.py` with:

```python
"""StyleGuard 服务单元测试"""
import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_dir(tmp_path):
    dynamic_samples = {
        "script_type": "dynamic",
        "samples": [
            {"title": "剧A", "excerpt": "△张总猛拍桌。", "genre": "男频", "theme_tag": "xianxia"},
            {"title": "剧B", "excerpt": "△李秘书推门。", "genre": "男频", "theme_tag": "xianxia"},
            {"title": "剧C", "excerpt": "△王老板摔门。", "genre": "女频", "theme_tag": "urban"},
        ],
        "golden_quotes": ["张总（暴怒）：三十万！你敢说不知道？！"],
    }
    explanatory_samples = {
        "script_type": "explanatory",
        "samples": [
            {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。", "genre": "世情", "theme_tag": "urban"},
            {"title": "蚀骨之恨", "excerpt": "△丈夫和妹妹在灵堂上苟合。", "genre": "女频", "theme_tag": "rebirth_modern"},
            {"title": "男友全家", "excerpt": "△许妍关门。", "genre": "女频", "theme_tag": "family"},
        ],
        "golden_quotes": ["门刚拉开一条缝。"],
    }
    (tmp_path / "style_samples_dynamic.json").write_text(
        json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "style_samples_explanatory.json").write_text(
        json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_style_guard_loads_dynamic_samples(sample_dir):
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic")
    assert len(samples) == 1
    assert isinstance(samples[0], dict)
    assert "excerpt" in samples[0]
    assert "genre" in samples[0]


def test_style_guard_genre_preference(sample_dir):
    """Same-genre samples should be preferred when genre specified"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    # 女频 in explanatory pool has 2 entries (蚀骨之恨, 男友全家)
    seen_titles = set()
    for _ in range(30):
        got = sg.get_style_samples("explanatory", count=1, genre="女频")
        seen_titles.add(got[0]["title"])
    assert seen_titles.issubset({"蚀骨之恨", "男友全家"})


def test_style_guard_fallback_when_no_genre_match(sample_dir):
    """Unknown genre falls back to full pool of same script_type"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    got = sg.get_style_samples("explanatory", count=3, genre="完全不存在的类")
    assert len(got) == 3


def test_style_guard_backward_compat_no_genre(sample_dir):
    """Calls without genre keyword must still work"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    got = sg.get_style_samples("dynamic", count=2)
    assert len(got) == 2
    assert all(isinstance(s, dict) for s in got)


def test_build_style_context_includes_genre_match(sample_dir):
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    ctx = sg.build_style_context("explanatory", genre="女频")
    # Should prefer 女频 samples
    assert ("蚀骨之恨" in ctx) or ("男友全家" in ctx)


def test_anti_slop_rules_unchanged(sample_dir):
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    rules = sg.get_anti_slop_rules()
    assert "过度抽象形容词" in rules
    assert "套路化比喻" in rules
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest tests/test_style_guard.py -v`

Expected: Multiple FAIL (genre kwarg not supported, return type mismatch, etc.)

- [ ] **Step 3: 修改 StyleGuard 实现**

Replace `backend/app/services/style_guard.py` content from line 47 (`def get_style_samples`) to end of class with:

```python
    def get_style_samples(
        self,
        script_type: str,
        count: int = 1,
        genre: Optional[str] = None,
    ) -> list[dict]:
        """按 script_type 抽样，同 genre 优先，不足则回退同 script_type 全池。

        返回 list[dict]，每条含 title/excerpt/genre/theme_tag。
        """
        data = self._get_data(script_type)
        if not data:
            return []
        all_samples = data.get("samples", []) or []
        if not all_samples:
            return []

        # Prefer same-genre subset
        pool = all_samples
        if genre:
            same_genre = [s for s in all_samples if isinstance(s, dict) and s.get("genre") == genre]
            if same_genre:
                pool = same_genre

        n = min(count, len(pool))
        picked = random.sample(pool, n)

        # Top up from full pool if genre subset too small to meet count
        if len(picked) < count:
            remaining = [s for s in all_samples if s not in picked]
            extra = random.sample(remaining, min(count - len(picked), len(remaining)))
            picked.extend(extra)

        # Normalize old string-only entries to dict format (defensive)
        normalized = []
        for p in picked:
            if isinstance(p, dict):
                normalized.append(p)
            else:
                normalized.append({"title": "", "excerpt": str(p), "genre": "", "theme_tag": ""})
        return normalized

    def get_golden_quotes(self, script_type: str) -> list[str]:
        data = self._get_data(script_type)
        if not data:
            return []
        return data.get("golden_quotes", [])

    def get_anti_slop_rules(self) -> str:
        return ANTI_SLOP_RULES

    def build_style_context(
        self,
        script_type: str,
        genre: Optional[str] = None,
    ) -> str:
        """组合：范本 + 金句 → <examples> 标签块。同 genre 优先。"""
        samples = self.get_style_samples(script_type, count=2, genre=genre)
        quotes = self.get_golden_quotes(script_type)
        if not samples and not quotes:
            return ""

        parts = [
            "【风格参考范本】",
            "以下是编辑认可的高分剧本片段，请模仿其节奏、句式结构和对白口吻。",
            "严禁直接使用范本中的具体辞藻、人名、地名。",
            "",
            "<examples>",
        ]

        for s in samples:
            title = s.get("title", "")
            excerpt = s.get("excerpt", "")
            if title:
                parts.append(f"── {title} ──")
            parts.append(excerpt)
            parts.append("")

        if quotes:
            parts.append("--- 金句/句式参考 ---")
            for q in quotes:
                parts.append(q)

        parts.append("</examples>")
        return "\n".join(parts)

    def reload(self):
        self._load()

    # ── Private ──

    def _load(self):
        self._dynamic_data = self._load_file("style_samples_dynamic.json")
        self._explanatory_data = self._load_file("style_samples_explanatory.json")

    def _load_file(self, filename: str) -> Optional[dict]:
        filepath = self.samples_dir / filename
        if not filepath.exists():
            logger.warning("Style samples file not found: %s", filepath)
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            logger.info("Loaded style samples: %s", filename)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load style samples %s: %s", filename, e)
            return None

    def _get_data(self, script_type: str) -> Optional[dict]:
        if script_type == "explanatory":
            return self._explanatory_data
        return self._dynamic_data


# Module-level singleton
_instance: Optional[StyleGuard] = None


def get_style_guard() -> StyleGuard:
    global _instance
    if _instance is None:
        _instance = StyleGuard()
    return _instance
```

Note: This replaces everything from `def get_style_samples` down to the end of the file. The file header (imports, `ANTI_SLOP_RULES`, `class StyleGuard:` declaration, `__init__`) stays unchanged.

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest tests/test_style_guard.py -v`

Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer
git add backend/app/services/style_guard.py backend/tests/test_style_guard.py
git commit -m "feat(style-guard): genre-aware sample retrieval

get_style_samples and build_style_context now accept an optional genre
kwarg; same-genre samples are preferred, with automatic fallback to the
full script_type pool when the genre subset is empty or too small.

Return type standardized to list[dict] (title/excerpt/genre/theme_tag)
for downstream clarity. Old string-only entries are auto-normalized.

Constraint: Must remain backward-compatible with callers that pass no genre
Confidence: high
Scope-risk: narrow
Directive: build_style_context always requests count=2 samples now (was 1) — if token budget becomes tight revisit here first"
```

---

## Task 4: script_ai_service 透传 genre

**Files:**
- Modify: `backend/app/services/script_ai_service.py:345-378` (helpers) and `:699-758` (generate_episode_content)
- Modify: `backend/tests/test_drama_ai_service.py`

- [ ] **Step 1: 写失败测试（断言 genre 会被透传）**

Append to `backend/tests/test_drama_ai_service.py`:

```python
def test_generate_episode_content_accepts_genre():
    """generate_episode_content signature includes genre"""
    import inspect
    sig = inspect.signature(ScriptAIService.generate_episode_content)
    assert "genre" in sig.parameters


def test_build_episode_user_prompt_passes_genre(monkeypatch):
    """_build_episode_user_prompt forwards genre to StyleGuard.build_style_context"""
    from app.services import script_ai_service
    captured = {}

    class FakeGuard:
        def build_style_context(self, script_type, genre=None):
            captured["script_type"] = script_type
            captured["genre"] = genre
            return "<examples>FAKE</examples>"

    monkeypatch.setattr(script_ai_service, "get_style_guard", lambda: FakeGuard())
    result = script_ai_service._build_episode_user_prompt("BASE", "explanatory", genre="女频")
    assert "FAKE" in result
    assert captured["script_type"] == "explanatory"
    assert captured["genre"] == "女频"
```

Note: The current `_build_episode_user_prompt` imports `get_style_guard` inside the function body — the monkeypatch of `script_ai_service.get_style_guard` won't bind unless we change to module-level import OR patch the location properly. Fix in Step 3 below.

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest tests/test_drama_ai_service.py -v -k "genre"`

Expected: FAIL (genre param missing from signature; module-level `get_style_guard` not exposed)

- [ ] **Step 3: 修改 script_ai_service.py**

Two changes:

**Change 3a**: At top of `backend/app/services/script_ai_service.py`, right after `import httpx`, add module-level import (so monkeypatch can bind):

```python
from app.services.style_guard import get_style_guard
```

**Change 3b**: Replace `_build_episode_system_prompt` and `_build_episode_user_prompt` (currently lines 345-378) with:

```python
def _build_episode_system_prompt(
    base_system: str,
    script_type: str,
) -> str:
    """为 episode_content 构建 system prompt：原始规则 + 反 AI 清单"""
    sg = get_style_guard()
    anti_slop = sg.get_anti_slop_rules()
    if anti_slop:
        return f"{base_system}\n\n{anti_slop}"
    return base_system


def _build_episode_user_prompt(
    base_user: str,
    script_type: str,
    genre: Optional[str] = None,
) -> str:
    """为 episode_content 构建 user prompt：生成指令 + <examples> 范本+金句

    优先抽取同 genre 范本，不足时回退同 script_type 全池。
    """
    sg = get_style_guard()
    style_ctx = sg.build_style_context(script_type, genre=genre)
    if style_ctx:
        return f"{base_user}\n\n{style_ctx}"
    return base_user
```

**Change 3c**: Modify `generate_episode_content` signature and call. Find the method (around line 699) and change:

```python
    async def generate_episode_content(
        self,
        title: str,
        outline_summary: str,
        main_characters: List[str],
        core_conflict: str,
        style_tone: str,
        episode_index: int,
        total_episodes: int,
        current_episode: Dict[str, Any],
        prev_episode: Optional[Dict[str, Any]],
        next_episode: Optional[Dict[str, Any]],
        script_type: str = "dynamic",
        genre: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
```

And change the line that calls `_build_episode_user_prompt` (inside the method) from:
```python
        prompt = _build_episode_user_prompt(prompt, script_type)
```
to:
```python
        prompt = _build_episode_user_prompt(prompt, script_type, genre=genre)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /data/project/novel-writer && docker exec novel-writer-backend python -m pytest tests/test_drama_ai_service.py -v`

Expected: All pass (including new genre tests)

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer
git add backend/app/services/script_ai_service.py backend/tests/test_drama_ai_service.py
git commit -m "feat(script-ai): pipe genre into episode_content style injection

generate_episode_content now accepts an optional genre parameter and
passes it through _build_episode_user_prompt -> StyleGuard.build_style_context,
so the episode prompt gets samples matched to the project's genre.

Constraint: module-level get_style_guard import needed so tests can monkeypatch
Confidence: high
Scope-risk: narrow"
```

---

## Task 5: drama.py 读取 genre 传入 AIService

**Files:**
- Modify: `backend/app/routers/drama.py:826-912` (session_expand_episode)

- [ ] **Step 1: 快速搜 _guess_genre_from_concept 的可复用性**

Run: `grep -n "_guess_genre_from_concept\|def _guess_genre" backend/app/routers/drama.py | head -5`

Expected: one function definition around line 474; two callers for question/summary. We will add a third caller inside `session_expand_episode`.

- [ ] **Step 2: 修改 session_expand_episode**

In `backend/app/routers/drama.py`, find `session_expand_episode` (starts around line 826). Locate the line:

```python
    ai_service = ScriptAIService(project.ai_config, project_settings=_proj_settings)
```

Immediately BEFORE that line, add:

```python
    genre = _guess_genre_from_concept(project.concept) if project.concept else ""
```

Then, inside `async def stream():`, find:

```python
            async for chunk in ai_service.generate_episode_content(
                title=project.title,
                ...
                script_type=project.script_type,
            ):
```

Change it to include `genre=genre`:

```python
            async for chunk in ai_service.generate_episode_content(
                title=project.title,
                outline_summary=outline_summary,
                main_characters=main_characters,
                core_conflict=core_conflict,
                style_tone=style_tone,
                episode_index=idx,
                total_episodes=total,
                current_episode=current_ep,
                prev_episode=prev_ep,
                next_episode=next_ep,
                script_type=project.script_type,
                genre=genre,
            ):
```

- [ ] **Step 3: 快速健康检查（backend 重启）**

Run: `docker compose restart backend && sleep 5 && docker logs --tail 30 novel-writer-backend 2>&1 | grep -iE "error|started|listening" | head -10`

Expected: backend starts without import/syntax error.

- [ ] **Step 4: Commit**

```bash
cd /data/project/novel-writer
git add backend/app/routers/drama.py
git commit -m "feat(drama): pass genre to episode_content generation

session_expand_episode now derives genre from project.concept (reusing
_guess_genre_from_concept) and passes it to ScriptAIService so style
samples are filtered by genre at retrieval time.

Confidence: high
Scope-risk: narrow"
```

---

## Task 6: regen_episode.py CLI 验证工具

**Files:**
- Create: `scripts/regen_episode.py`

- [ ] **Step 1: 写 CLI 脚本**

Create `scripts/regen_episode.py`:

```python
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
sys.path.insert(0, str(BACKEND))

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
```

- [ ] **Step 2: 做可执行**

Run: `chmod +x scripts/regen_episode.py`

- [ ] **Step 3: 冒烟测试（--help）**

Run: `docker exec novel-writer-backend python /app/scripts/regen_episode.py --help 2>&1 | head`

Wait — the `scripts/` dir is outside the docker mount path. Check mount first:

Run: `docker exec novel-writer-backend ls /app 2>&1 | head`

If `/app` contains `backend` only (no `scripts`), update docker-compose.yml OR run the script via host Python. Simplest: run via host Python with DATABASE_URL pointing at dockerized postgres.

Host-run variant — set env var and go:

```bash
cd /data/project/novel-writer
DATABASE_URL='postgresql+asyncpg://novel_writer:<password>@localhost:5432/novel_writer' \
    python scripts/regen_episode.py --help
```

Fetch the actual DB password:

```bash
grep POSTGRES_PASSWORD .env 2>/dev/null || docker exec novel-writer-db-1 env | grep POSTGRES_PASSWORD
```

Then prefix the actual password and retest `--help`.

Expected: usage message prints.

- [ ] **Step 4: Commit**

```bash
cd /data/project/novel-writer
git add scripts/regen_episode.py
git commit -m "feat(scripts): add regen_episode.py CLI for offline verification

Reruns generate_episode_content against an existing drama project without
mutating the database. Used to A/B compare output before and after sample
pool changes.

Directive: --out writes to file; stdout is stream-only. DB is read-only.
Confidence: high
Scope-risk: narrow"
```

---

## Task 7: 跑剧本 8 第 1 集对照验证

**Files:** (none modified; verification only)

- [ ] **Step 1: 备份当前剧本 8 第 1 集内容**

Run:
```bash
docker exec novel-writer-db-1 psql -U novel_writer -d novel_writer -t -c \
    "SELECT outline_draft->'sections'->0->>'content' FROM script_sessions WHERE project_id=8;" \
    > /tmp/script8_ep1_BEFORE.txt
wc -c /tmp/script8_ep1_BEFORE.txt
```

Expected: file ~2-3 KB of existing generated 分场剧本.

- [ ] **Step 2: 用 regen 工具重新生成（保存到文件，不覆盖 DB）**

Run (replace <PW> with the password from .env):
```bash
cd /data/project/novel-writer
DATABASE_URL='postgresql+asyncpg://novel_writer:<PW>@localhost:5432/novel_writer' \
    python scripts/regen_episode.py --project-id 8 --episode-index 0 \
    --out /tmp/script8_ep1_AFTER.txt
wc -c /tmp/script8_ep1_AFTER.txt
```

Expected: file written, ~2-4 KB; stderr shows `genre='职场'` or similar non-empty string.

- [ ] **Step 3: 人工对照（diff 主观特征）**

Run:
```bash
echo "=== BEFORE ===" && cat /tmp/script8_ep1_BEFORE.txt | head -40
echo; echo "=== AFTER ===" && cat /tmp/script8_ep1_AFTER.txt | head -40
```

Inspection checklist (at least 2 of 4 should improve):
- [ ] 开场钩子是否带悬念/反差（不只是直接对抗）
- [ ] 主角是否有弱点/代入点（不是开场就站在顶点）
- [ ] 反派是否有自洽逻辑（不是纯纸片人）
- [ ] 对白是否减少"情绪括号→情绪"的标签化

- [ ] **Step 4: 二次验证——对比 prompt 抽到的样本**

Run:
```bash
docker exec novel-writer-backend python -c "
from app.services.style_guard import get_style_guard
sg = get_style_guard()
# Script 8: explanatory, genre='职场' (likely unknown) → fallback to full explanatory pool
for _ in range(3):
    ctx = sg.build_style_context('explanatory', genre='职场')
    print('---')
    for line in ctx.splitlines():
        if line.startswith('── ') and line.endswith(' ──'):
            print(line)
"
```

Expected: outputs include titles from explanatory pool (蚀骨之恨 / 男友全家 / AI 仿真人剧 类）— NOT《皇子》《天降魔丸》。

- [ ] **Step 5: 把验证产出记录为 archival 注释**

Run:
```bash
cd /data/project/novel-writer
mkdir -p .omc/verification
cp /tmp/script8_ep1_BEFORE.txt .omc/verification/2026-04-23_script8_ep1_BEFORE.txt
cp /tmp/script8_ep1_AFTER.txt .omc/verification/2026-04-23_script8_ep1_AFTER.txt
# (git-ignored; local only)
```

No commit needed (verification artifacts).

- [ ] **Step 6: 用户确认**

Ask user: "新生成的剧本 8 第 1 集在 [悬念/弱点/反派/对白] 中满足 2+ 项改善吗？如果是，任务结束；如果不是，进入 Path B（handbook 注入 outline）。"

---

## Self-Review

**1. Spec coverage:**
- 数据源合并与统一 schema ✓ Task 2
- theme_tag 分类规则 ✓ Task 1
- extract_fewshots.py 改造 ✓ Task 2
- StyleGuard API 变更 ✓ Task 3
- script_ai_service 集成 ✓ Task 4
- drama.py router ✓ Task 5
- 剧本 8 验证通路 ✓ Task 6, Task 7
- internal_signed_meta.json ✓ 前置（已完成）

**2. Placeholder scan:** No TBDs / TODOs / "implement later" / vague "add error handling". All code blocks complete.

**3. Type consistency:**
- `get_style_samples` returns `list[dict]` consistently across Task 3 (impl), Task 4 (caller via `build_style_context`)
- `genre` is `Optional[str]` throughout
- `classify()` returns `tuple[Optional[str], Optional[str]]` in Task 1, matching usage in Task 2

**4. Ambiguity:** Resolved
- Password fetching in Task 6 Step 3 has explicit fallback (.env or docker exec)
- `scripts/` mount concern is flagged with a host-run fallback

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-23-explanatory-sample-pool-redesign.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
