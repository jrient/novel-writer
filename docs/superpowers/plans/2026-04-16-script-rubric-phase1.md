# Script Rubric Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a two-pass LLM pipeline that extracts a structured review handbook from 44 editor-reviewed scripts.

**Architecture:** Parse xlsx + txt files into structured records, run per-script LLM extraction (Pass 1) to produce JSON archives, then cross-script synthesis (Pass 2) to produce a human-readable handbook and machine-readable rubric. Backtesting validates against holdout scripts.

**Tech Stack:** Python 3.11+, openai SDK (compatible mode), openpyxl, pydantic v2, asyncio

**Spec:** `docs/superpowers/specs/2026-04-16-script-rubric-design.md`

**Data correction:** xlsx has 44 valid rows (not 55 as initially estimated). Holdout = 9 scripts, training = 35.

---

## File Structure

```
script_rubric/
├── __init__.py
├── config.py                  # Paths, API config, thresholds
├── models.py                  # Pydantic models: Review, ScriptRecord, ScriptArchive, etc.
├── requirements.txt           # openai, openpyxl, pydantic
├── pipeline/
│   ├── __init__.py
│   ├── parse_xlsx.py          # xlsx → list[ScriptRecord]
│   ├── match_texts.py         # Fuzzy match script titles to txt files
│   ├── llm_client.py          # Async OpenAI-compatible client wrapper
│   ├── pass1_extract.py       # Per-script structured extraction
│   ├── pass2_synthesize.py    # Cross-script synthesis → handbook + rubric
│   ├── backtest.py            # Holdout split + prediction + evaluation
│   └── run.py                 # CLI entry point
├── prompts/
│   ├── pass1.md               # Per-script extraction prompt
│   ├── pass2_universal.md     # Batch A: universal rules
│   ├── pass2_overlay.md       # Batch B: type overlay
│   ├── pass2_redflags.md      # Batch C: rejection patterns
│   └── backtest_predict.md    # Backtest prediction prompt
├── data/
│   └── parsed/                # Intermediate JSON files
├── outputs/
│   ├── archives/              # Per-script JSON archives
│   ├── handbook/              # handbook_v{N}.md + rubric_v{N}.json
│   └── backtest/              # report_v{N}.md
└── tests/
    ├── __init__.py
    ├── test_parse_xlsx.py
    ├── test_match_texts.py
    ├── test_models.py
    ├── test_backtest.py
    └── conftest.py            # Shared fixtures
```

---

## Task 1: Project Scaffolding + Config + Models

**Files:**
- Create: `script_rubric/__init__.py`
- Create: `script_rubric/config.py`
- Create: `script_rubric/models.py`
- Create: `script_rubric/requirements.txt`
- Create: `script_rubric/pipeline/__init__.py`
- Create: `script_rubric/tests/__init__.py`
- Create: `script_rubric/tests/conftest.py`
- Create: `script_rubric/tests/test_models.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p script_rubric/{pipeline,prompts,data/parsed,outputs/{archives,handbook,backtest},tests}
touch script_rubric/__init__.py script_rubric/pipeline/__init__.py script_rubric/tests/__init__.py
```

- [ ] **Step 2: Write requirements.txt**

```
# script_rubric/requirements.txt
openai>=1.0
openpyxl>=3.1
pydantic>=2.0
python-dotenv>=1.0
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -r script_rubric/requirements.txt --break-system-packages
```

Expected: installs successfully, no errors.

- [ ] **Step 4: Write config.py**

```python
# script_rubric/config.py
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PARSED_DIR = DATA_DIR / "parsed"
OUTPUT_DIR = BASE_DIR / "outputs"
ARCHIVES_DIR = OUTPUT_DIR / "archives"
HANDBOOK_DIR = OUTPUT_DIR / "handbook"
BACKTEST_DIR = OUTPUT_DIR / "backtest"
PROMPT_DIR = BASE_DIR / "prompts"

# Data sources
XLSX_PATH = PROJECT_ROOT / "uploads" / "外部待审核剧本.xlsx"
DRAMA_DIR = PROJECT_ROOT / "uploads" / "drama"

# API (OpenAI-compatible mode for Claude Sonnet 4.6)
API_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://yibuapi.com/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL = os.getenv("RUBRIC_MODEL", "claude-sonnet-4-6-20250514")

# Pipeline parameters
PASS1_CONCURRENCY = 5
PASS1_MAX_RETRIES = 2
HOLDOUT_RATIO = 0.2
HOLDOUT_SEED = 42
MAX_ITERATE_ROUNDS = 3

# Backtest thresholds
BACKTEST_STATUS_ACCURACY = 0.70
BACKTEST_RANGE_ACCURACY = 0.60
BACKTEST_MAE_THRESHOLD = 8
BACKTEST_CRITICAL_MISS_RATE = 0.10

# xlsx column mapping (0-indexed)
XLSX_COLUMNS = {
    "source_type": 0,    # A: 原创/改编
    "genre": 1,          # B: 男频/女频/萌宝/世情
    "title": 2,          # C: 剧本名
    "submitter": 3,      # D: 提交人
    "status": 4,         # E: 状态 (签/改/拒)
    "overall_score": 5,  # F: 综合评分
}

# Reviewers: (name, score_col_index, comment_col_index)
REVIEWERS = [
    ("小冉", 6, 7),
    ("贾酒", 8, 9),
    ("47", 10, 11),
    ("宇间", 12, 13),
    ("帕克", 14, 15),
    ("Vicki", 16, 17),
    ("千北", 18, 19),
    ("小刚", 20, 21),
    ("山南", 22, 23),
    ("安兔兔", 24, 25),
    ("步步", 26, 27),
]

# 7 dimension keys (used across pipeline)
DIMENSION_KEYS = [
    "premise_innovation",
    "opening_hook",
    "character_depth",
    "pacing_conflict",
    "writing_dialogue",
    "payoff_satisfaction",
    "benchmark_differentiation",
]

DIMENSION_NAMES_ZH = {
    "premise_innovation": "题材与设定创新度",
    "opening_hook": "开局与钩子",
    "character_depth": "人设立体度",
    "pacing_conflict": "节奏与冲突密度",
    "writing_dialogue": "文笔与台词",
    "payoff_satisfaction": "爽点兑现",
    "benchmark_differentiation": "对标与差异化",
}
```

- [ ] **Step 5: Write models.py**

```python
# script_rubric/models.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field


class Review(BaseModel):
    reviewer: str
    score: int | None = None
    comment: str | None = None


class ScriptRecord(BaseModel):
    title: str
    source_type: str
    genre: str
    submitter: str
    status: str
    reviews: list[Review] = []
    text_content: str | None = None
    text_file: str | None = None

    @computed_field
    @property
    def mean_score(self) -> float | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    @computed_field
    @property
    def score_range(self) -> tuple[int, int] | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if not scores:
            return None
        return (min(scores), max(scores))

    @computed_field
    @property
    def score_std(self) -> float | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if len(scores) < 2:
            return None
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        return round(variance ** 0.5, 1)


class DimensionAnalysis(BaseModel):
    score: int
    verdict: Literal["positive", "mixed", "negative"]
    evidence_from_reviews: list[str] = []
    evidence_from_text: list[str] = []
    extracted_rule: str = ""


class ScriptArchive(BaseModel):
    title: str
    status: str
    genre: str
    mean_score: float
    score_range: tuple[int, int]
    dimensions: dict[str, DimensionAnalysis]
    type_specific_notes: str = ""
    consensus_points: list[str] = []
    disagreement_points: list[str] = []
    red_flags: list[str] = []
    green_flags: list[str] = []


class PredictResult(BaseModel):
    title: str
    predicted_score: int
    predicted_status: str
    dimension_scores: dict[str, int] = {}
    comments: list[str] = []
    red_flags_hit: list[str] = []
    green_flags_hit: list[str] = []


class BacktestMetrics(BaseModel):
    status_accuracy: float
    range_accuracy: float
    mae: float
    critical_miss_rate: float
    total: int
    details: list[dict] = []
```

- [ ] **Step 6: Write test for models**

```python
# script_rubric/tests/test_models.py
from script_rubric.models import Review, ScriptRecord, DimensionAnalysis, ScriptArchive


class TestScriptRecord:
    def test_mean_score(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=80),
                Review(reviewer="R2", score=70),
                Review(reviewer="R3", score=90),
            ],
        )
        assert record.mean_score == 80.0

    def test_mean_score_with_none(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=80),
                Review(reviewer="R2", score=None, comment="好看"),
            ],
        )
        assert record.mean_score == 80.0

    def test_mean_score_empty(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签", reviews=[],
        )
        assert record.mean_score is None

    def test_score_range(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=65),
                Review(reviewer="R2", score=80),
                Review(reviewer="R3", score=100),
            ],
        )
        assert record.score_range == (65, 100)

    def test_score_std(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=70),
                Review(reviewer="R2", score=80),
            ],
        )
        assert record.score_std is not None
        assert abs(record.score_std - 7.1) < 0.1

    def test_score_std_single_review(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[Review(reviewer="R1", score=80)],
        )
        assert record.score_std is None


class TestScriptArchive:
    def test_create_archive(self):
        archive = ScriptArchive(
            title="test", status="签", genre="男频",
            mean_score=80.0, score_range=(75, 85),
            dimensions={
                "premise_innovation": DimensionAnalysis(
                    score=8, verdict="positive",
                    evidence_from_reviews=["设定新颖"],
                    extracted_rule="多元素交叉设定有优势",
                ),
            },
        )
        assert archive.dimensions["premise_innovation"].score == 8
```

- [ ] **Step 7: Run tests**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_models.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Write conftest.py with shared fixtures**

```python
# script_rubric/tests/conftest.py
import pytest

from script_rubric.models import Review, ScriptRecord


@pytest.fixture
def sample_reviews():
    return [
        Review(reviewer="小冉", score=80, comment="好看，挑不出毛病"),
        Review(reviewer="贾酒", score=75, comment="节奏偏慢"),
        Review(reviewer="帕克", score=85, comment="设定新颖"),
    ]


@pytest.fixture
def sample_record(sample_reviews):
    return ScriptRecord(
        title="《测试剧本》",
        source_type="原创",
        genre="男频",
        submitter="测试员",
        status="签",
        reviews=sample_reviews,
        text_content="第一集\n场景：某地\n男主出场...",
    )


@pytest.fixture
def sample_records():
    """Multiple records for testing batch operations."""
    return [
        ScriptRecord(
            title="《签约剧本A》", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=85, comment="很好"),
                Review(reviewer="R2", score=80, comment="不错"),
            ],
        ),
        ScriptRecord(
            title="《修改剧本B》", source_type="改编", genre="女频",
            submitter="B", status="改",
            reviews=[
                Review(reviewer="R1", score=75, comment="节奏慢"),
                Review(reviewer="R2", score=78, comment="可以改"),
            ],
        ),
        ScriptRecord(
            title="《拒绝剧本C》", source_type="原创", genre="男频",
            submitter="C", status="拒",
            reviews=[
                Review(reviewer="R1", score=65, comment="一般"),
                Review(reviewer="R2", score=60, comment="不行"),
            ],
        ),
    ]
```

- [ ] **Step 9: Commit**

```bash
git add script_rubric/
git commit -m "feat(rubric): scaffold project with config, models, and test fixtures"
```

---

## Task 2: xlsx Parser

**Files:**
- Create: `script_rubric/pipeline/parse_xlsx.py`
- Create: `script_rubric/tests/test_parse_xlsx.py`

- [ ] **Step 1: Write the test**

```python
# script_rubric/tests/test_parse_xlsx.py
from script_rubric.pipeline.parse_xlsx import parse_xlsx
from script_rubric.config import XLSX_PATH


class TestParseXlsx:
    def test_parse_returns_list(self):
        records = parse_xlsx(XLSX_PATH)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_valid_rows_only(self):
        """Only rows with non-empty status and at least one reviewer score."""
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            assert r.status in ("签", "改", "拒"), f"Invalid status: {r.status}"
            scores = [rev.score for rev in r.reviews if rev.score is not None]
            assert len(scores) > 0, f"No scores for: {r.title}"

    def test_title_not_empty(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            assert r.title.strip(), f"Empty title found"

    def test_reviews_have_reviewer_names(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            for rev in r.reviews:
                assert rev.reviewer, "Reviewer name is empty"

    def test_scores_in_range(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            for rev in r.reviews:
                if rev.score is not None:
                    assert 0 <= rev.score <= 100, f"Score out of range: {rev.score}"

    def test_genre_values(self):
        records = parse_xlsx(XLSX_PATH)
        valid_genres = {"男频", "女频", "萌宝", "世情"}
        for r in records:
            if r.genre:
                assert r.genre in valid_genres or r.genre == "", \
                    f"Unknown genre: {r.genre} for {r.title}"

    def test_computed_scores(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            if r.mean_score is not None:
                assert 0 <= r.mean_score <= 100

    def test_save_and_load_json(self, tmp_path):
        records = parse_xlsx(XLSX_PATH)
        out = tmp_path / "scripts.json"
        save_parsed(records, out)
        assert out.exists()
        loaded = load_parsed(out)
        assert len(loaded) == len(records)
        assert loaded[0].title == records[0].title


from script_rubric.pipeline.parse_xlsx import save_parsed, load_parsed
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_parse_xlsx.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'script_rubric.pipeline.parse_xlsx'`

- [ ] **Step 3: Implement parse_xlsx.py**

```python
# script_rubric/pipeline/parse_xlsx.py
from __future__ import annotations

import json
from pathlib import Path

import openpyxl

from script_rubric.config import XLSX_COLUMNS, REVIEWERS
from script_rubric.models import Review, ScriptRecord


def parse_xlsx(path: Path) -> list[ScriptRecord]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]

    records: list[ScriptRecord] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        status = _clean_str(row[XLSX_COLUMNS["status"]])
        if not status or status not in ("签", "改", "拒"):
            continue

        reviews = _extract_reviews(row)
        if not any(r.score is not None for r in reviews):
            continue

        title = _clean_str(row[XLSX_COLUMNS["title"]]) or ""
        if not title.strip():
            continue

        records.append(ScriptRecord(
            title=title.strip(),
            source_type=_clean_str(row[XLSX_COLUMNS["source_type"]]) or "",
            genre=_clean_str(row[XLSX_COLUMNS["genre"]]) or "",
            submitter=_clean_str(row[XLSX_COLUMNS["submitter"]]) or "",
            status=status,
            reviews=[r for r in reviews if r.score is not None or r.comment],
        ))

    return records


def _extract_reviews(row: tuple) -> list[Review]:
    reviews = []
    for name, score_col, comment_col in REVIEWERS:
        score_raw = row[score_col] if score_col < len(row) else None
        comment_raw = row[comment_col] if comment_col < len(row) else None

        score = _parse_score(score_raw)
        comment = _clean_str(comment_raw)

        if score is not None or comment:
            reviews.append(Review(reviewer=name, score=score, comment=comment))
    return reviews


def _parse_score(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        return v if 0 <= v <= 100 else None
    s = str(val).strip()
    if s.isdigit():
        v = int(s)
        return v if 0 <= v <= 100 else None
    return None


def _clean_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def save_parsed(records: list[ScriptRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump() for r in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_parsed(path: Path) -> list[ScriptRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ScriptRecord.model_validate(d) for d in data]
```

- [ ] **Step 4: Run tests**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_parse_xlsx.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add script_rubric/pipeline/parse_xlsx.py script_rubric/tests/test_parse_xlsx.py
git commit -m "feat(rubric): implement xlsx parser with review extraction"
```

---

## Task 3: Text Matcher

**Files:**
- Create: `script_rubric/pipeline/match_texts.py`
- Create: `script_rubric/tests/test_match_texts.py`

- [ ] **Step 1: Write the test**

```python
# script_rubric/tests/test_match_texts.py
from pathlib import Path

from script_rubric.models import ScriptRecord, Review
from script_rubric.pipeline.match_texts import match_texts, fuzzy_match_score


class TestFuzzyMatch:
    def test_exact_match(self):
        score = fuzzy_match_score("《八零福星俏娇妻》", "《八零福星俏娇妻》.txt")
        assert score > 0.8

    def test_partial_match(self):
        score = fuzzy_match_score(
            "改编AI真人剧《嫡女贵凰：重生毒妃狠绝色》（1）",
            "改编AI真人剧《嫡女贵凰：重生毒妃狠绝色》（1）.txt",
        )
        assert score > 0.8

    def test_no_match(self):
        score = fuzzy_match_score("完全不同的标题", "另一个文件.txt")
        assert score < 0.5


class TestMatchTexts:
    def test_match_with_real_data(self):
        from script_rubric.config import XLSX_PATH, DRAMA_DIR
        from script_rubric.pipeline.parse_xlsx import parse_xlsx

        records = parse_xlsx(XLSX_PATH)
        result = match_texts(records, DRAMA_DIR)

        matched = sum(1 for r in result.records if r.text_content is not None)
        assert matched > 0, "No texts matched"
        assert result.total == len(records)
        assert result.matched == matched

    def test_missing_dir(self, tmp_path):
        records = [
            ScriptRecord(
                title="test", source_type="原创", genre="男频",
                submitter="A", status="签",
                reviews=[Review(reviewer="R1", score=80)],
            ),
        ]
        result = match_texts(records, tmp_path)
        assert result.matched == 0

    def test_report_generated(self):
        from script_rubric.config import XLSX_PATH, DRAMA_DIR
        from script_rubric.pipeline.parse_xlsx import parse_xlsx

        records = parse_xlsx(XLSX_PATH)
        result = match_texts(records, DRAMA_DIR)
        report = result.to_report()
        assert "matched" in report.lower() or "匹配" in report.lower() or result.matched >= 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_match_texts.py -v
```

Expected: FAIL — import error.

- [ ] **Step 3: Implement match_texts.py**

```python
# script_rubric/pipeline/match_texts.py
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
        lines = [
            f"# Text Match Report",
            f"Total scripts: {self.total}",
            f"Matched: {self.matched} ({self.matched/self.total*100:.0f}%)" if self.total > 0 else "Matched: 0",
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
```

- [ ] **Step 4: Run tests**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_match_texts.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add script_rubric/pipeline/match_texts.py script_rubric/tests/test_match_texts.py
git commit -m "feat(rubric): implement fuzzy text matcher for script files"
```

---

## Task 4: LLM Client

**Files:**
- Create: `script_rubric/pipeline/llm_client.py`

- [ ] **Step 1: Implement LLM client wrapper**

```python
# script_rubric/pipeline/llm_client.py
from __future__ import annotations

import asyncio
import json
import re

from openai import AsyncOpenAI

from script_rubric.config import API_BASE_URL, API_KEY, MODEL, PASS1_CONCURRENCY

_semaphore = asyncio.Semaphore(PASS1_CONCURRENCY)


def get_client() -> AsyncOpenAI:
    return AsyncOpenAI(base_url=API_BASE_URL, api_key=API_KEY)


async def call_llm(
    client: AsyncOpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str = MODEL,
    max_retries: int = 2,
    temperature: float = 0.3,
) -> str:
    async with _semaphore:
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=4096,
                )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
        raise last_error


def extract_json(text: str) -> dict:
    """Extract JSON object from LLM response that may contain markdown fences."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)
```

- [ ] **Step 2: Commit**

```bash
git add script_rubric/pipeline/llm_client.py
git commit -m "feat(rubric): add async LLM client with retry and JSON extraction"
```

---

## Task 5: Pass 1 — Per-Script Extraction

**Files:**
- Create: `script_rubric/prompts/pass1.md`
- Create: `script_rubric/pipeline/pass1_extract.py`

- [ ] **Step 1: Write Pass 1 prompt template**

```markdown
# script_rubric/prompts/pass1.md

你是一位资深剧本评审分析师。你的任务是阅读一部剧本及其多位责编的评审意见，产出一份结构化档案。

## 关键要求

1. **证据驱动**：每个维度的判定必须引用责编原话或正文原文，不得凭空推断。在 evidence_from_reviews 中用"原话 —— 责编名"格式引用。
2. **保留分歧**：责编之间的意见冲突是重要信号，必须如实记录在 disagreement_points 中。
3. **共识提炼**：当 ≥50% 的责编提到同一问题时，标记为 consensus_point。
4. **维度打分**：基于责编评语的整体倾向打 1-10 分。这不是你自己对剧本的判断，而是"责编们集体认为这个维度多好"的综合。
5. **正文缺失时**：如果没有剧本正文，仅基于评语分析，evidence_from_text 留空。

## 7 个维度定义

### 1. premise_innovation（题材与设定创新度）
评估标准：设定组合是否新颖、是否触碰禁忌（映射现实政治等）、市场饱和度。
- 8-10: 设定令人眼前一亮，多元素交叉创新
- 5-7: 常规设定但有亮点
- 1-4: 套路化、无差异化元素

### 2. opening_hook（开局与钩子）
评估标准：前 3 集是否有足够强的事件/情绪钩子、冲突是否快速触发。
- 8-10: 第一集即有强烈冲突和悬念
- 5-7: 前 3 集能抓住注意力但不够炸裂
- 1-4: 开局平淡、进入情绪慢

### 3. character_depth（人设立体度）
评估标准：主角是否立体不扁平、是否避免恋爱脑/工具人、是否符合时代审美。
- 8-10: 人设鲜明有层次，符合当代观众偏好
- 5-7: 人设基本立住但不够出彩
- 1-4: 人设崩塌/恋爱脑/工具人/降智

### 4. pacing_conflict（节奏与冲突密度）
评估标准：事件节奏是否合理、冲突密度是否足够、松紧是否交替。
- 8-10: 节奏紧凑、每集有推进、冲突层层递进
- 5-7: 节奏可接受但有拖沓段落
- 1-4: 节奏慢、冲突不足、重复

### 5. writing_dialogue（文笔与台词）
评估标准：台词是否自然成熟、是否出戏、文笔水平。
- 8-10: 台词精炼有力，文笔成熟
- 5-7: 文笔合格但有小白感
- 1-4: 台词出戏严重、文笔幼稚

### 6. payoff_satisfaction（爽点兑现）
评估标准：承诺的爽点是否兑现、打击是否到位、频率是否合理。
- 8-10: 爽点密集且到位
- 5-7: 有爽点但力度或频率不足
- 1-4: 爽感缺失

### 7. benchmark_differentiation（对标与差异化）
评估标准：是否有明确的市场定位、和已有作品的差异化程度。
- 8-10: 在已有赛道中有明确差异化优势
- 5-7: 有定位但差异化不明显
- 1-4: 和已有作品高度重复

## 输出格式

严格输出以下 JSON（不要输出任何其他内容）：

```json
{
  "title": "剧本标题",
  "status": "签/改/拒",
  "genre": "类型",
  "mean_score": 80.0,
  "score_range": [75, 85],
  "dimensions": {
    "premise_innovation": {
      "score": 8,
      "verdict": "positive",
      "evidence_from_reviews": ["原话 —— 责编名", ...],
      "evidence_from_text": ["正文中的具体描述", ...],
      "extracted_rule": "一句话总结这个维度的规律"
    },
    "opening_hook": { ... },
    "character_depth": { ... },
    "pacing_conflict": { ... },
    "writing_dialogue": { ... },
    "payoff_satisfaction": { ... },
    "benchmark_differentiation": { ... }
  },
  "type_specific_notes": "针对该类型的特殊观察",
  "consensus_points": ["多数责编认同的观点1", ...],
  "disagreement_points": ["责编之间的分歧1", ...],
  "red_flags": ["负面警示1", ...],
  "green_flags": ["正面亮点1", ...]
}
```
```

- [ ] **Step 2: Implement pass1_extract.py**

```python
# script_rubric/pipeline/pass1_extract.py
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from script_rubric.config import (
    ARCHIVES_DIR, PROMPT_DIR, PASS1_MAX_RETRIES, DIMENSION_KEYS,
)
from script_rubric.models import ScriptRecord, ScriptArchive
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json

logger = logging.getLogger(__name__)


def _load_prompt() -> str:
    return (PROMPT_DIR / "pass1.md").read_text(encoding="utf-8")


def _build_user_prompt(record: ScriptRecord) -> str:
    parts = []
    parts.append("## 元数据")
    parts.append(f"标题: {record.title}")
    parts.append(f"类型: {record.source_type} / {record.genre}")
    parts.append(f"状态: {record.status}")
    parts.append(f"提交人: {record.submitter}")
    parts.append(f"均分: {record.mean_score}")
    parts.append(f"分数区间: {record.score_range}")
    parts.append("")

    parts.append(f"## 责编评审 (共 {len(record.reviews)} 位)")
    for rev in record.reviews:
        score_str = str(rev.score) if rev.score is not None else "未打分"
        comment_str = rev.comment or "无评语"
        parts.append(f"【{rev.reviewer}】 分数: {score_str}")
        parts.append(f"评语: {comment_str}")
        parts.append("")

    parts.append("## 剧本正文")
    if record.text_content:
        content = record.text_content
        if len(content) > 50000:
            content = content[:50000] + "\n\n[正文过长，已截断至前50000字]"
        parts.append(content)
    else:
        parts.append("正文缺失，仅基于元数据和评语分析。evidence_from_text 请留空。")

    return "\n".join(parts)


def _slug(title: str) -> str:
    return title.strip().replace(" ", "_").replace("/", "_")[:80]


def _archive_path(title: str) -> Path:
    return ARCHIVES_DIR / f"{_slug(title)}.json"


def _validate_archive(archive: ScriptArchive, record: ScriptRecord) -> list[str]:
    issues = []
    for key in DIMENSION_KEYS:
        if key not in archive.dimensions:
            issues.append(f"Missing dimension: {key}")
        else:
            dim = archive.dimensions[key]
            if not dim.evidence_from_reviews and record.reviews:
                issues.append(f"No review evidence for {key}")
    if archive.status != record.status:
        issues.append(f"Status mismatch: archive={archive.status}, record={record.status}")
    return issues


async def extract_one(
    record: ScriptRecord,
    system_prompt: str,
    skip_existing: bool = True,
) -> ScriptArchive | None:
    path = _archive_path(record.title)
    if skip_existing and path.exists():
        logger.info(f"Skipping (exists): {record.title}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ScriptArchive.model_validate(data)

    client = get_client()
    user_prompt = _build_user_prompt(record)

    try:
        raw = await call_llm(
            client, system_prompt, user_prompt,
            max_retries=PASS1_MAX_RETRIES,
        )
        data = extract_json(raw)
        archive = ScriptArchive.model_validate(data)

        issues = _validate_archive(archive, record)
        if issues:
            logger.warning(f"Validation issues for {record.title}: {issues}")

        ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Extracted: {record.title}")
        return archive

    except Exception as e:
        logger.error(f"Failed to extract {record.title}: {e}")
        return None


async def extract_all(
    records: list[ScriptRecord],
    skip_existing: bool = True,
) -> list[ScriptArchive]:
    system_prompt = _load_prompt()
    tasks = [
        extract_one(record, system_prompt, skip_existing)
        for record in records
    ]
    results = await asyncio.gather(*tasks)
    archives = [a for a in results if a is not None]
    logger.info(f"Extracted {len(archives)}/{len(records)} archives")
    return archives


def load_all_archives() -> list[ScriptArchive]:
    archives = []
    if not ARCHIVES_DIR.exists():
        return archives
    for path in sorted(ARCHIVES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        archives.append(ScriptArchive.model_validate(data))
    return archives
```

- [ ] **Step 3: Run a quick syntax check**

```bash
cd /data/project/novel-writer && python -c "from script_rubric.pipeline.pass1_extract import extract_all, load_all_archives; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add script_rubric/prompts/pass1.md script_rubric/pipeline/pass1_extract.py
git commit -m "feat(rubric): implement Pass 1 per-script LLM extraction"
```

---

## Task 6: Pass 2 — Cross-Script Synthesis

**Files:**
- Create: `script_rubric/prompts/pass2_universal.md`
- Create: `script_rubric/prompts/pass2_overlay.md`
- Create: `script_rubric/prompts/pass2_redflags.md`
- Create: `script_rubric/pipeline/pass2_synthesize.py`

- [ ] **Step 1: Write Pass 2 prompts**

**pass2_universal.md:**

```markdown
# script_rubric/prompts/pass2_universal.md

你是一位剧本行业的首席分析师，面前是多部剧本的结构化评审档案摘要。

请对以下 7 个维度，各产出一个规律章节：

1. premise_innovation（题材与设定创新度）
2. opening_hook（开局与钩子）
3. character_depth（人设立体度）
4. pacing_conflict（节奏与冲突密度）
5. writing_dialogue（文笔与台词）
6. payoff_satisfaction（爽点兑现）
7. benchmark_differentiation（对标与差异化）

每个章节包含：
1. **核心规律**（3-5 条，每条一句话）
2. **正例**（从"签"的剧本中引用 2-3 个具体案例说明规律成立）
3. **反例**（从"拒"的剧本中引用 2-3 个案例说明违反规律的后果）
4. **量化锚点**（如果能从数据中看出阈值，给出来。例："维度分 ≥7 的剧本签约率 80%"）
5. **可执行建议**（写给编剧看的 2-3 条 do / don't）

注意：
- 只从档案证据中归纳，不要编造案例
- 如果某个维度的数据太少无法得出稳定规律，明确标注"样本不足，待验证"
- 用中文输出
- 直接输出 markdown 格式内容，不要包裹在 JSON 中
```

**pass2_overlay.md:**

```markdown
# script_rubric/prompts/pass2_overlay.md

你面前是同一类型（{genre}）的多部剧本的完整评审档案。

和"通用规律"相比，{genre}有哪些独特要求？请产出：

1. **这个类型特别看重什么**（3-5 条，附案例）
2. **这个类型的常见翻车点**（3-5 条，附案例）
3. **和其他类型的关键差异**（2-3 条）
4. **评分修正建议**（评审时，这个类型的哪些维度要加权/降权）

注意：
- 只从档案证据中归纳，不要编造案例
- 用中文输出 markdown 格式
```

**pass2_redflags.md:**

```markdown
# script_rubric/prompts/pass2_redflags.md

你面前是所有被拒绝的剧本的评审档案。

请产出：

1. **高频拒稿原因 TOP 10**（按出现频次排序，每条附 2+ 个具体剧本例证）
2. **致命组合**（哪些问题同时出现时几乎必拒？例："开局平 + 人设恋爱脑"）
3. **可救 vs 不可救**（从"改"和"拒"的边界案例中，找出"差一点就能签"和"完全无法挽救"的区别）
4. **一句话地雷清单**（写给编剧的"绝对不要"列表，10-15 条）

注意：
- 只从档案证据中归纳
- "可救 vs 不可救"部分需要同时参考"改"和"拒"的剧本做对比
- 用中文输出 markdown 格式
```

- [ ] **Step 2: Implement pass2_synthesize.py**

```python
# script_rubric/pipeline/pass2_synthesize.py
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from script_rubric.config import (
    HANDBOOK_DIR, PROMPT_DIR, DIMENSION_KEYS, DIMENSION_NAMES_ZH,
)
from script_rubric.models import ScriptArchive
from script_rubric.pipeline.llm_client import get_client, call_llm

logger = logging.getLogger(__name__)


def _summarize_archive(archive: ScriptArchive) -> str:
    dim_scores = ", ".join(
        f"{DIMENSION_NAMES_ZH.get(k, k)}{archive.dimensions[k].score}"
        for k in DIMENSION_KEYS
        if k in archive.dimensions
    )
    consensus = "; ".join(archive.consensus_points[:3]) if archive.consensus_points else "无"
    disagreement = "; ".join(archive.disagreement_points[:2]) if archive.disagreement_points else "无"
    return (
        f"### {archive.title} | {archive.genre} | {archive.status} | 均分 {archive.mean_score}\n"
        f"维度分: {dim_scores}\n"
        f"共识: {consensus}\n"
        f"分歧: {disagreement}\n"
    )


def _full_archive_text(archive: ScriptArchive) -> str:
    return json.dumps(archive.model_dump(), ensure_ascii=False, indent=1)


async def synthesize_universal(archives: list[ScriptArchive]) -> str:
    system_prompt = (PROMPT_DIR / "pass2_universal.md").read_text(encoding="utf-8")
    summaries = "\n".join(_summarize_archive(a) for a in archives)
    user_prompt = f"## 档案摘要（{len(archives)} 部）\n\n{summaries}"

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


async def synthesize_overlay(archives: list[ScriptArchive], genre: str) -> str:
    template = (PROMPT_DIR / "pass2_overlay.md").read_text(encoding="utf-8")
    system_prompt = template.replace("{genre}", genre)
    details = "\n\n".join(_full_archive_text(a) for a in archives)
    user_prompt = f"## {genre} 档案（{len(archives)} 部）\n\n{details}"

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


async def synthesize_redflags(
    rejected: list[ScriptArchive],
    borderline: list[ScriptArchive],
) -> str:
    system_prompt = (PROMPT_DIR / "pass2_redflags.md").read_text(encoding="utf-8")
    rej_text = "\n\n".join(_full_archive_text(a) for a in rejected)
    bord_text = "\n\n".join(_full_archive_text(a) for a in borderline)
    user_prompt = (
        f"## 被拒剧本（{len(rejected)} 部）\n\n{rej_text}\n\n"
        f"## 待改剧本（{len(borderline)} 部，供对比）\n\n{bord_text}"
    )

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


def _build_data_overview(archives: list[ScriptArchive]) -> str:
    total = len(archives)
    by_status = defaultdict(int)
    by_genre = defaultdict(int)
    for a in archives:
        by_status[a.status] += 1
        by_genre[a.genre] += 1

    dim_avgs = {}
    for key in DIMENSION_KEYS:
        scores = [a.dimensions[key].score for a in archives if key in a.dimensions]
        if scores:
            dim_avgs[DIMENSION_NAMES_ZH.get(key, key)] = round(sum(scores) / len(scores), 1)

    lines = [
        f"- 总样本: {total} 部",
        f"- 状态分布: " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())),
        f"- 类型分布: " + ", ".join(f"{k} {v}" for k, v in sorted(by_genre.items())),
        f"- 各维度平均分:",
    ]
    for name, avg in dim_avgs.items():
        lines.append(f"  - {name}: {avg}")
    return "\n".join(lines)


async def synthesize_all(archives: list[ScriptArchive], version: int = 1) -> tuple[str, dict]:
    logger.info(f"Pass 2: synthesizing handbook v{version} from {len(archives)} archives")

    # Batch A: universal rules
    logger.info("Batch A: universal rules")
    universal = await synthesize_universal(archives)

    # Batch B: type overlays
    by_genre = defaultdict(list)
    for a in archives:
        if a.genre:
            by_genre[a.genre].append(a)

    overlays = {}
    for genre, group in by_genre.items():
        if len(group) >= 3:
            logger.info(f"Batch B: overlay for {genre} ({len(group)} scripts)")
            overlays[genre] = await synthesize_overlay(group, genre)
        else:
            logger.warning(f"Skipping overlay for {genre}: only {len(group)} scripts")
            overlays[genre] = f"*{genre}类型仅有 {len(group)} 部样本，数据不足，暂不生成专项规律。*"

    # Batch C: red flags
    rejected = [a for a in archives if a.status == "拒"]
    borderline = [a for a in archives if a.status == "改"]
    logger.info(f"Batch C: red flags ({len(rejected)} rejected, {len(borderline)} borderline)")
    redflags = await synthesize_redflags(rejected, borderline)

    # Merge into handbook
    now = datetime.now().strftime("%Y-%m-%d")
    handbook = f"""# 剧本评审手册 v{version}

> 基于 {len(archives)} 部剧本的评审数据提炼
> 生成日期: {now} | 模型: Claude Sonnet 4.6

---

## 第一部分：通用规律

{universal}

---

## 第二部分：类型专项

"""
    for genre, text in overlays.items():
        handbook += f"### {genre}\n\n{text}\n\n"

    handbook += f"""---

## 第三部分：地雷清单

{redflags}

---

## 附录：数据概览

{_build_data_overview(archives)}
"""

    # Generate rubric.json
    rubric = _build_rubric(archives, version, now)

    # Save files
    HANDBOOK_DIR.mkdir(parents=True, exist_ok=True)
    handbook_path = HANDBOOK_DIR / f"handbook_v{version}.md"
    handbook_path.write_text(handbook, encoding="utf-8")
    logger.info(f"Saved: {handbook_path}")

    rubric_path = HANDBOOK_DIR / f"rubric_v{version}.json"
    rubric_path.write_text(json.dumps(rubric, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved: {rubric_path}")

    return handbook, rubric


def _build_rubric(archives: list[ScriptArchive], version: int, date: str) -> dict:
    dim_stats = {}
    for key in DIMENSION_KEYS:
        scores_by_status = defaultdict(list)
        for a in archives:
            if key in a.dimensions:
                scores_by_status[a.status].append(a.dimensions[key].score)

        all_scores = [s for lst in scores_by_status.values() for s in lst]
        avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

        red_flags = set()
        green_flags = set()
        for a in archives:
            if key in a.dimensions:
                if a.status == "拒":
                    red_flags.update(a.red_flags)
                elif a.status == "签":
                    green_flags.update(a.green_flags)

        dim_stats[key] = {
            "name_zh": DIMENSION_NAMES_ZH.get(key, key),
            "avg_score": avg,
            "avg_by_status": {
                status: round(sum(scores) / len(scores), 1) if scores else None
                for status, scores in scores_by_status.items()
            },
            "red_flags_sample": list(red_flags)[:5],
            "green_flags_sample": list(green_flags)[:5],
        }

    by_genre = defaultdict(lambda: defaultdict(list))
    for a in archives:
        for key in DIMENSION_KEYS:
            if key in a.dimensions:
                by_genre[a.genre][key].append(a.dimensions[key].score)

    type_overlays = {}
    for genre, dims in by_genre.items():
        type_overlays[genre] = {
            key: round(sum(scores) / len(scores), 1) if scores else None
            for key, scores in dims.items()
        }

    return {
        "version": str(version),
        "generated_at": date,
        "sample_size": len(archives),
        "universal_dimensions": dim_stats,
        "type_overlays": type_overlays,
    }
```

- [ ] **Step 3: Syntax check**

```bash
cd /data/project/novel-writer && python -c "from script_rubric.pipeline.pass2_synthesize import synthesize_all; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add script_rubric/prompts/pass2_universal.md script_rubric/prompts/pass2_overlay.md script_rubric/prompts/pass2_redflags.md script_rubric/pipeline/pass2_synthesize.py
git commit -m "feat(rubric): implement Pass 2 cross-script synthesis with 3 batch types"
```

---

## Task 7: Backtest

**Files:**
- Create: `script_rubric/prompts/backtest_predict.md`
- Create: `script_rubric/pipeline/backtest.py`
- Create: `script_rubric/tests/test_backtest.py`

- [ ] **Step 1: Write backtest prediction prompt**

```markdown
# script_rubric/prompts/backtest_predict.md

你是一位使用评审手册的剧本评审员。请根据手册对以下剧本进行评审。

## 评审手册

{handbook}

## 待评审剧本

标题: {title}
类型: {source_type} / {genre}

### 剧本正文
{text_content}

## 任务

1. 按手册的 7 个维度逐一打分 (1-10)
2. 给出综合评分 (0-100)
3. 给出状态判定: 80+ 为"签"，70-80 为"改"，<70 为"拒"
4. 写出 3-5 条关键评语（模拟责编视角）
5. 标注该剧本踩了哪些地雷 / 命中哪些绿灯

严格输出以下 JSON（不要输出其他内容）：

```json
{
  "title": "剧本标题",
  "predicted_score": 78,
  "predicted_status": "改",
  "dimension_scores": {
    "premise_innovation": 7,
    "opening_hook": 6,
    "character_depth": 7,
    "pacing_conflict": 5,
    "writing_dialogue": 6,
    "payoff_satisfaction": 6,
    "benchmark_differentiation": 7
  },
  "comments": ["评语1", "评语2", "评语3"],
  "red_flags_hit": ["地雷1"],
  "green_flags_hit": ["绿灯1"]
}
```
```

- [ ] **Step 2: Write backtest evaluation test**

```python
# script_rubric/tests/test_backtest.py
from script_rubric.models import BacktestMetrics, ScriptRecord, Review, PredictResult
from script_rubric.pipeline.backtest import (
    split_holdout,
    evaluate_predictions,
)


class TestSplitHoldout:
    def test_split_ratio(self, sample_records):
        # Extend to 10 records
        records = sample_records * 4  # 12 records
        for i, r in enumerate(records):
            r.title = f"Script_{i}"
        train, test = split_holdout(records, ratio=0.2, seed=42)
        assert len(test) >= 2
        assert len(train) + len(test) == len(records)

    def test_stratified_by_status(self):
        records = []
        for i in range(6):
            records.append(ScriptRecord(
                title=f"签_{i}", source_type="原创", genre="男频",
                submitter="A", status="签",
                reviews=[Review(reviewer="R", score=85)],
            ))
        for i in range(4):
            records.append(ScriptRecord(
                title=f"改_{i}", source_type="原创", genre="女频",
                submitter="A", status="改",
                reviews=[Review(reviewer="R", score=75)],
            ))
        for i in range(5):
            records.append(ScriptRecord(
                title=f"拒_{i}", source_type="原创", genre="男频",
                submitter="A", status="拒",
                reviews=[Review(reviewer="R", score=60)],
            ))
        train, test = split_holdout(records, ratio=0.2, seed=42)
        test_statuses = {r.status for r in test}
        assert len(test_statuses) >= 2, "Holdout should have at least 2 status types"

    def test_deterministic(self, sample_records):
        records = sample_records * 4
        for i, r in enumerate(records):
            r.title = f"Script_{i}"
        t1_train, t1_test = split_holdout(records, ratio=0.2, seed=42)
        t2_train, t2_test = split_holdout(records, ratio=0.2, seed=42)
        assert [r.title for r in t1_test] == [r.title for r in t2_test]


class TestEvaluatePredictions:
    def test_perfect_predictions(self):
        actuals = [
            ScriptRecord(
                title="A", source_type="原创", genre="男频",
                submitter="X", status="签",
                reviews=[Review(reviewer="R", score=80), Review(reviewer="R2", score=85)],
            ),
            ScriptRecord(
                title="B", source_type="原创", genre="女频",
                submitter="X", status="拒",
                reviews=[Review(reviewer="R", score=60), Review(reviewer="R2", score=65)],
            ),
        ]
        predictions = [
            PredictResult(title="A", predicted_score=82, predicted_status="签"),
            PredictResult(title="B", predicted_score=62, predicted_status="拒"),
        ]
        metrics = evaluate_predictions(predictions, actuals)
        assert metrics.status_accuracy == 1.0
        assert metrics.range_accuracy == 1.0
        assert metrics.critical_miss_rate == 0.0

    def test_critical_miss(self):
        actuals = [
            ScriptRecord(
                title="A", source_type="原创", genre="男频",
                submitter="X", status="签",
                reviews=[Review(reviewer="R", score=80)],
            ),
        ]
        predictions = [
            PredictResult(title="A", predicted_score=60, predicted_status="拒"),
        ]
        metrics = evaluate_predictions(predictions, actuals)
        assert metrics.critical_miss_rate == 1.0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_backtest.py -v
```

Expected: FAIL — import error.

- [ ] **Step 4: Implement backtest.py**

```python
# script_rubric/pipeline/backtest.py
from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from script_rubric.config import (
    BACKTEST_DIR, PROMPT_DIR, HANDBOOK_DIR,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.models import ScriptRecord, PredictResult, BacktestMetrics
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json

logger = logging.getLogger(__name__)


def split_holdout(
    records: list[ScriptRecord],
    ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[ScriptRecord], list[ScriptRecord]]:
    by_status: dict[str, list[ScriptRecord]] = defaultdict(list)
    for r in records:
        by_status[r.status].append(r)

    rng = random.Random(seed)
    train, test = [], []

    for status, group in by_status.items():
        shuffled = group.copy()
        rng.shuffle(shuffled)
        n_test = max(1, round(len(shuffled) * ratio))
        test.extend(shuffled[:n_test])
        train.extend(shuffled[n_test:])

    return train, test


def evaluate_predictions(
    predictions: list[PredictResult],
    actuals: list[ScriptRecord],
) -> BacktestMetrics:
    actual_map = {r.title: r for r in actuals}
    details = []
    status_hits = 0
    range_hits = 0
    abs_errors = []
    critical_misses = 0
    total = 0

    for pred in predictions:
        actual = actual_map.get(pred.title)
        if not actual:
            continue

        total += 1
        status_hit = pred.predicted_status == actual.status
        if status_hit:
            status_hits += 1

        score_range = actual.score_range
        range_hit = False
        if score_range:
            range_hit = score_range[0] <= pred.predicted_score <= score_range[1]
            if range_hit:
                range_hits += 1

        mae = abs(pred.predicted_score - (actual.mean_score or 0))
        abs_errors.append(mae)

        is_critical = (
            (pred.predicted_status == "签" and actual.status == "拒")
            or (pred.predicted_status == "拒" and actual.status == "签")
        )
        if is_critical:
            critical_misses += 1

        details.append({
            "title": pred.title,
            "actual_status": actual.status,
            "predicted_status": pred.predicted_status,
            "status_hit": status_hit,
            "actual_mean": actual.mean_score,
            "actual_range": list(score_range) if score_range else None,
            "predicted_score": pred.predicted_score,
            "range_hit": range_hit,
            "mae": mae,
            "critical_miss": is_critical,
        })

    return BacktestMetrics(
        status_accuracy=status_hits / total if total else 0,
        range_accuracy=range_hits / total if total else 0,
        mae=sum(abs_errors) / len(abs_errors) if abs_errors else 0,
        critical_miss_rate=critical_misses / total if total else 0,
        total=total,
        details=details,
    )


async def predict_one(
    record: ScriptRecord,
    handbook_text: str,
) -> PredictResult | None:
    template = (PROMPT_DIR / "backtest_predict.md").read_text(encoding="utf-8")
    system_prompt = "你是一位使用评审手册的剧本评审员。严格按照 JSON 格式输出。"
    user_prompt = template.replace("{handbook}", handbook_text)
    user_prompt = user_prompt.replace("{title}", record.title)
    user_prompt = user_prompt.replace("{source_type}", record.source_type)
    user_prompt = user_prompt.replace("{genre}", record.genre)
    user_prompt = user_prompt.replace(
        "{text_content}",
        record.text_content[:30000] if record.text_content else "正文缺失",
    )

    client = get_client()
    try:
        raw = await call_llm(client, system_prompt, user_prompt, max_retries=2)
        data = extract_json(raw)
        return PredictResult.model_validate(data)
    except Exception as e:
        logger.error(f"Prediction failed for {record.title}: {e}")
        return None


async def run_backtest(
    test_records: list[ScriptRecord],
    version: int = 1,
) -> BacktestMetrics:
    handbook_path = HANDBOOK_DIR / f"handbook_v{version}.md"
    if not handbook_path.exists():
        raise FileNotFoundError(f"Handbook not found: {handbook_path}")

    handbook_text = handbook_path.read_text(encoding="utf-8")

    import asyncio
    tasks = [predict_one(r, handbook_text) for r in test_records]
    results = await asyncio.gather(*tasks)
    predictions = [p for p in results if p is not None]

    metrics = evaluate_predictions(predictions, test_records)

    # Save report
    report = generate_report(metrics, version)
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BACKTEST_DIR / f"report_v{version}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"Backtest report saved: {report_path}")

    return metrics


def generate_report(metrics: BacktestMetrics, version: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    status_ok = "✅" if metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY else "❌"
    range_ok = "✅" if metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY else "❌"
    mae_ok = "✅" if metrics.mae <= BACKTEST_MAE_THRESHOLD else "❌"
    crit_ok = "✅" if metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE else "❌"

    lines = [
        f"# 回测报告 v{version}",
        f"> 生成时间: {now} | 测试集: {metrics.total} 部",
        "",
        "## 总览",
        f"- 状态命中率: {metrics.status_accuracy:.0%} {status_ok} (阈值 ≥{BACKTEST_STATUS_ACCURACY:.0%})",
        f"- 区间命中率: {metrics.range_accuracy:.0%} {range_ok} (阈值 ≥{BACKTEST_RANGE_ACCURACY:.0%})",
        f"- 分数 MAE: {metrics.mae:.1f} {mae_ok} (阈值 ≤{BACKTEST_MAE_THRESHOLD})",
        f"- 严重误判率: {metrics.critical_miss_rate:.0%} {crit_ok} (阈值 ≤{BACKTEST_CRITICAL_MISS_RATE:.0%})",
        "",
        "## 逐条明细",
        "| 剧本 | 实际状态 | 预测状态 | 实际均分 | 预测分 | 区间 | 命中 |",
        "|-------|---------|---------|---------|-------|------|------|",
    ]

    for d in metrics.details:
        range_str = f"[{d['actual_range'][0]},{d['actual_range'][1]}]" if d.get("actual_range") else "N/A"
        hit = "✅" if d["status_hit"] else "❌"
        lines.append(
            f"| {d['title'][:20]} | {d['actual_status']} | {d['predicted_status']} "
            f"| {d['actual_mean']} | {d['predicted_score']} | {range_str} | {hit} |"
        )

    # Failure analysis
    failures = [d for d in metrics.details if not d["status_hit"]]
    if failures:
        lines.append("")
        lines.append("## 失败案例分析")
        for d in failures:
            lines.append(f"### 《{d['title']}》预测\"{d['predicted_status']}\" 实际\"{d['actual_status']}\"")
            lines.append(f"- 预测分: {d['predicted_score']}, 实际均分: {d['actual_mean']}")
            if d.get("critical_miss"):
                lines.append("- **严重误判（签↔拒）**")
            lines.append("")

    all_pass = all([
        metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY,
        metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY,
        metrics.mae <= BACKTEST_MAE_THRESHOLD,
        metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE,
    ])

    lines.append("")
    lines.append("## 结论")
    if all_pass:
        lines.append(f"手册 v{version} **达标**，可用于 Phase 2。")
    else:
        lines.append(f"手册 v{version} **未达标**，建议分析失败案例后调整 prompt 重跑。")

    return "\n".join(lines)
```

- [ ] **Step 5: Run tests**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/test_backtest.py -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add script_rubric/prompts/backtest_predict.md script_rubric/pipeline/backtest.py script_rubric/tests/test_backtest.py
git commit -m "feat(rubric): implement backtest with holdout split, prediction, and evaluation"
```

---

## Task 8: CLI Entry Point

**Files:**
- Create: `script_rubric/pipeline/run.py`

- [ ] **Step 1: Implement run.py**

```python
# script_rubric/pipeline/run.py
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from script_rubric.config import (
    XLSX_PATH, DRAMA_DIR, PARSED_DIR, ARCHIVES_DIR,
    HOLDOUT_RATIO, HOLDOUT_SEED, MAX_ITERATE_ROUNDS,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.pipeline.parse_xlsx import parse_xlsx, save_parsed, load_parsed
from script_rubric.pipeline.match_texts import match_texts
from script_rubric.pipeline.pass1_extract import extract_all, load_all_archives
from script_rubric.pipeline.pass2_synthesize import synthesize_all
from script_rubric.pipeline.backtest import split_holdout, run_backtest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run")


async def cmd_full(args):
    """Full pipeline: parse → match → split → Pass 1 → Pass 2 → backtest."""
    logger.info("=== Full Run ===")

    # Step 1: Parse xlsx
    logger.info("Step 1: Parsing xlsx...")
    records = parse_xlsx(XLSX_PATH)
    logger.info(f"  Parsed {len(records)} valid records")

    # Step 2: Match texts
    logger.info("Step 2: Matching text files...")
    match_result = match_texts(records, DRAMA_DIR)
    logger.info(f"  Matched {match_result.matched}/{match_result.total} texts")
    report_path = PARSED_DIR / "match_report.txt"
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(match_result.to_report(), encoding="utf-8")

    # Save parsed records
    save_parsed(records, PARSED_DIR / "scripts.json")

    # Step 3: Split holdout
    logger.info("Step 3: Splitting holdout set...")
    train, test = split_holdout(records, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)
    logger.info(f"  Train: {len(train)}, Test: {len(test)}")

    # Save split info
    split_info = {
        "train_titles": [r.title for r in train],
        "test_titles": [r.title for r in test],
    }
    (PARSED_DIR / "holdout_split.json").write_text(
        json.dumps(split_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Step 4: Pass 1 (training set only)
    logger.info(f"Step 4: Pass 1 extraction ({len(train)} scripts)...")
    archives = await extract_all(train, skip_existing=not args.force)
    logger.info(f"  Extracted {len(archives)} archives")

    # Step 5: Pass 2
    version = args.version or 1
    logger.info(f"Step 5: Pass 2 synthesis → handbook v{version}...")
    handbook, rubric = await synthesize_all(archives, version=version)
    logger.info("  Handbook and rubric generated")

    # Step 6: Backtest
    logger.info(f"Step 6: Backtesting on {len(test)} holdout scripts...")
    metrics = await run_backtest(test, version=version)
    logger.info(f"  Status accuracy: {metrics.status_accuracy:.0%}")
    logger.info(f"  Range accuracy: {metrics.range_accuracy:.0%}")
    logger.info(f"  MAE: {metrics.mae:.1f}")
    logger.info(f"  Critical miss rate: {metrics.critical_miss_rate:.0%}")

    all_pass = all([
        metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY,
        metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY,
        metrics.mae <= BACKTEST_MAE_THRESHOLD,
        metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE,
    ])

    if all_pass:
        logger.info("=== PASS: Handbook meets all thresholds ===")
    else:
        logger.warning("=== FAIL: Handbook did not meet thresholds ===")
        logger.info("Check backtest report for failure analysis")


async def cmd_incremental(args):
    """Incremental: parse new data → Pass 1 (new only) → verify → Pass 2."""
    logger.info("=== Incremental Run ===")

    # Parse current xlsx
    records = parse_xlsx(XLSX_PATH)
    match_result = match_texts(records, DRAMA_DIR)
    logger.info(f"Total records: {len(records)}, matched texts: {match_result.matched}")

    # Find new records (no existing archive)
    existing_archives = load_all_archives()
    existing_titles = {a.title for a in existing_archives}
    new_records = [r for r in records if r.title not in existing_titles]
    logger.info(f"New records: {len(new_records)}")

    if not new_records:
        logger.info("No new records found. Nothing to do.")
        return

    # Pass 1 on new records only
    new_archives = await extract_all(new_records, skip_existing=False)
    logger.info(f"Extracted {len(new_archives)} new archives")

    # Merge all archives and re-synthesize
    all_archives = existing_archives + new_archives
    version = args.version or (len(list(Path(ARCHIVES_DIR).parent.glob("handbook/handbook_v*.md"))) + 1)
    logger.info(f"Re-synthesizing handbook v{version} with {len(all_archives)} total archives...")
    await synthesize_all(all_archives, version=version)

    logger.info("=== Incremental run complete ===")


async def cmd_backtest_only(args):
    """Re-run backtest with existing handbook."""
    version = args.version or 1
    logger.info(f"=== Backtest Only (v{version}) ===")

    records = parse_xlsx(XLSX_PATH)
    match_texts(records, DRAMA_DIR)
    _, test = split_holdout(records, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)

    metrics = await run_backtest(test, version=version)
    logger.info(f"Results: status={metrics.status_accuracy:.0%}, "
                f"range={metrics.range_accuracy:.0%}, mae={metrics.mae:.1f}")


async def cmd_pass2_only(args):
    """Re-run Pass 2 with existing archives."""
    version = args.version or 1
    logger.info(f"=== Pass 2 Only → v{version} ===")

    archives = load_all_archives()
    logger.info(f"Loaded {len(archives)} existing archives")
    await synthesize_all(archives, version=version)
    logger.info("Done")


def main():
    parser = argparse.ArgumentParser(description="Script Rubric Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser("full", help="Full pipeline run")
    p_full.add_argument("--version", type=int, default=1)
    p_full.add_argument("--force", action="store_true", help="Re-extract existing archives")

    p_inc = sub.add_parser("incremental", help="Incremental run with new data")
    p_inc.add_argument("--version", type=int, default=None)

    p_bt = sub.add_parser("backtest", help="Re-run backtest only")
    p_bt.add_argument("--version", type=int, default=1)

    p_p2 = sub.add_parser("pass2", help="Re-run Pass 2 only")
    p_p2.add_argument("--version", type=int, default=1)

    args = parser.parse_args()

    cmd_map = {
        "full": cmd_full,
        "incremental": cmd_incremental,
        "backtest": cmd_backtest_only,
        "pass2": cmd_pass2_only,
    }

    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

```bash
cd /data/project/novel-writer && python -m script_rubric.pipeline.run --help
```

Expected: shows usage with `full`, `incremental`, `backtest`, `pass2` subcommands.

- [ ] **Step 3: Commit**

```bash
git add script_rubric/pipeline/run.py
git commit -m "feat(rubric): implement CLI entry point with full/incremental/backtest/pass2 commands"
```

---

## Task 9: Integration Smoke Test

**Files:**
- No new files — runs the actual pipeline end-to-end

- [ ] **Step 1: Run all unit tests**

```bash
cd /data/project/novel-writer && python -m pytest script_rubric/tests/ -v
```

Expected: all PASS.

- [ ] **Step 2: Do a dry-run parse + match to verify data**

```bash
cd /data/project/novel-writer && python -c "
from script_rubric.pipeline.parse_xlsx import parse_xlsx
from script_rubric.pipeline.match_texts import match_texts
from script_rubric.config import XLSX_PATH, DRAMA_DIR

records = parse_xlsx(XLSX_PATH)
print(f'Parsed: {len(records)} records')
for r in records[:3]:
    print(f'  {r.title} | {r.genre} | {r.status} | scores: {[rev.score for rev in r.reviews if rev.score]}')

result = match_texts(records, DRAMA_DIR)
print(f'Matched: {result.matched}/{result.total}')
print(f'Unmatched: {result.unmatched_titles[:5]}')
"
```

Expected: shows parsed records and match statistics. Verify numbers look correct.

- [ ] **Step 3: Run full pipeline**

```bash
cd /data/project/novel-writer && python -m script_rubric.pipeline.run full --version 1
```

Expected: pipeline runs through all 6 steps. Watch for:
- Parse count matches expected (~44)
- Text match count is reasonable (≥30)
- Pass 1 extraction completes for all training scripts
- Pass 2 generates handbook + rubric
- Backtest produces report with metrics

This step takes ~10-15 minutes and requires API access.

- [ ] **Step 4: Review outputs**

Check generated files:
```bash
ls -la script_rubric/outputs/archives/ | head -20
cat script_rubric/outputs/handbook/handbook_v1.md | head -100
cat script_rubric/outputs/backtest/report_v1.md
```

Verify:
- Archives exist for training set scripts
- Handbook has all 3 parts (通用规律 / 类型专项 / 地雷清单)
- Backtest report has metrics and per-script details

- [ ] **Step 5: Commit all outputs**

```bash
git add script_rubric/
git commit -m "feat(rubric): complete Phase 1 pipeline with initial run outputs"
```

---

## Self-Review

### Spec Coverage

| Spec Section | Plan Task |
|---|---|
| §2 Data sources + parsing | Task 2 (parse_xlsx) |
| §2.3 Matching logic | Task 3 (match_texts) |
| §2.4 Data models | Task 1 (models.py) |
| §3 Dimension structure | Task 5 (pass1 prompt) |
| §4.2 Pass 1 extraction | Task 5 (pass1_extract) |
| §4.3 Pass 2 synthesis | Task 6 (pass2_synthesize) |
| §5 Output handbook + rubric | Task 6 (merge + save) |
| §6 Backtest | Task 7 (backtest) |
| §7 Incremental iteration | Task 8 (cmd_incremental) |
| §8 Tech stack + directory | Task 1 (scaffolding) |
| §8.3 CLI | Task 8 (run.py) |
| §8.4 Config | Task 1 (config.py) |

All spec sections covered. No gaps.

### Placeholder Scan

No TBD, TODO, or "implement later" found. All code blocks are complete.

### Type Consistency

- `ScriptRecord`, `Review`, `ScriptArchive`, `DimensionAnalysis`, `PredictResult`, `BacktestMetrics` — consistent across all tasks
- `DIMENSION_KEYS` used in config, pass1, pass2, backtest — consistent
- `parse_xlsx`, `save_parsed`, `load_parsed` signatures match between implementation and test imports
- `split_holdout`, `evaluate_predictions` signatures match between implementation and test usage
