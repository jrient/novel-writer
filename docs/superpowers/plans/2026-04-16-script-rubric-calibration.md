# Script Rubric Calibration (Handbook v4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate handbook v4 with a deterministic calibration section (status-score table, advisory thresholds, one anchor script per status) and rewrite the predict prompt to reference it. Improve MAE 14.7 → ≤8 and range hit 14% → ≥60% while preserving status hit ≥70% and 0% critical miss.

**Architecture:** Add a Python-only function `_build_calibration_section(archives)` to `pass2_synthesize.py`. It computes per-status statistics (mean / P25 / P75 / per-dimension averages), advisory thresholds (midpoints of adjacent means), and selects one anchor script per status (closest mean_score to status mean). Output is markdown appended to handbook as Part 4. `cmd_pass2_only` is updated to filter archives to the training split before synthesis. Predict prompt drops hard thresholds and instructs LLM to reference Part 4.

**Tech Stack:** Python 3.11, pydantic v2, pytest, stdlib `statistics`. No new dependencies.

---

## File Structure

| Path | Action | Responsibility |
|------|--------|----------------|
| `script_rubric/pipeline/pass2_synthesize.py` | Modify | Add calibration section generator + integrate into handbook layout |
| `script_rubric/pipeline/run.py` | Modify | Filter archives to training set in `cmd_pass2_only` |
| `script_rubric/prompts/backtest_predict.md` | Rewrite | Drop hard thresholds, reference Part 4, update reasoning instructions |
| `script_rubric/tests/test_pass2_calibration.py` | Create | 3 unit tests for calibration section + 1 for cmd_pass2_only filter |
| `script_rubric/outputs/handbook/handbook_v4.md` | Generate | Output of Pass 2 v4 run |
| `script_rubric/outputs/handbook/rubric_v4.json` | Generate | Output of Pass 2 v4 run |
| `script_rubric/outputs/backtest/report_v4.md` | Generate | Output of backtest v4 run |

---

## Task 1: Calibration section — statistics table (TDD)

**Files:**
- Modify: `script_rubric/pipeline/pass2_synthesize.py` (add new function)
- Create: `script_rubric/tests/test_pass2_calibration.py`

- [ ] **Step 1: Add fixture builder helper at top of new test file**

Create `script_rubric/tests/test_pass2_calibration.py`:

```python
from __future__ import annotations

from script_rubric.models import ScriptArchive, DimensionAnalysis
from script_rubric.config import DIMENSION_KEYS


def _make_archive(
    title: str,
    status: str,
    mean_score: float,
    genre: str = "都市言情",
    dim_score: int = 7,
) -> ScriptArchive:
    dims = {
        key: DimensionAnalysis(score=dim_score, verdict="mixed")
        for key in DIMENSION_KEYS
    }
    return ScriptArchive(
        title=title,
        status=status,
        genre=genre,
        mean_score=mean_score,
        score_range=(int(mean_score) - 2, int(mean_score) + 2),
        dimensions=dims,
        consensus_points=[f"{title} 共识1", f"{title} 共识2", f"{title} 共识3"],
        red_flags=[f"{title} 红旗A"],
        green_flags=[f"{title} 绿旗A"],
    )


def _sample_archives() -> list[ScriptArchive]:
    return [
        _make_archive("S1", "签", 79.0),
        _make_archive("S2", "签", 78.0),
        _make_archive("S3", "签", 77.0),
        _make_archive("R1", "改", 78.0),
        _make_archive("R2", "改", 75.0),
        _make_archive("R3", "改", 80.0),
        _make_archive("J1", "拒", 70.0),
        _make_archive("J2", "拒", 73.0),
        _make_archive("J3", "拒", 76.0),
    ]
```

- [ ] **Step 2: Write the failing test for statistics table content**

Append to `test_pass2_calibration.py`:

```python
class TestCalibrationStats:
    def test_section_has_all_statuses(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "签" in text
        assert "改" in text
        assert "拒" in text

    def test_section_has_correct_status_means(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        # 签: (79+78+77)/3 = 78.0; 改: (78+75+80)/3 = 77.7; 拒: (70+73+76)/3 = 73.0
        assert "78.0" in text
        assert "77.7" in text
        assert "73.0" in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest script_rubric/tests/test_pass2_calibration.py -v`
Expected: FAIL with `ImportError: cannot import name '_build_calibration_section'`

- [ ] **Step 4: Implement statistics-only version of `_build_calibration_section`**

In `script_rubric/pipeline/pass2_synthesize.py`, add `import statistics` near other imports if not present, then append this function before `_build_data_overview`:

```python
def _build_calibration_section(archives: list[ScriptArchive]) -> str:
    by_status: dict[str, list[ScriptArchive]] = defaultdict(list)
    for a in archives:
        by_status[a.status].append(a)

    status_order = ["签", "改", "拒"]
    rows = []
    status_stats: dict[str, dict] = {}

    for status in status_order:
        group = by_status.get(status, [])
        if not group:
            continue
        scores = [a.mean_score for a in group]
        mean = round(sum(scores) / len(scores), 1)
        if len(scores) >= 4:
            quartiles = statistics.quantiles(scores, n=4)
            p25, p75 = round(quartiles[0], 1), round(quartiles[2], 1)
        else:
            p25, p75 = round(min(scores), 1), round(max(scores), 1)

        dim_avgs = []
        for key in DIMENSION_KEYS:
            ds = [a.dimensions[key].score for a in group if key in a.dimensions]
            if ds:
                dim_avgs.append(f"{DIMENSION_NAMES_ZH.get(key, key)} {round(sum(ds)/len(ds), 1)}")
        dim_str = " / ".join(dim_avgs)

        rows.append(f"| {status} | {len(group)} | {mean} | {p25} | {p75} | {dim_str} |")
        status_stats[status] = {"mean": mean, "p25": p25, "p75": p75}

    table = (
        "### A. 状态-分数分布表\n\n"
        "| 状态 | 样本数 | 均分 | P25 | P75 | 维度典型分布 |\n"
        "|------|--------|------|-----|-----|--------------|\n"
        + "\n".join(rows)
    )

    return table
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest script_rubric/tests/test_pass2_calibration.py -v`
Expected: PASS for both `test_section_has_all_statuses` and `test_section_has_correct_status_means`.

- [ ] **Step 6: Commit**

```bash
git add script_rubric/pipeline/pass2_synthesize.py script_rubric/tests/test_pass2_calibration.py
git commit -m "feat(rubric): add calibration stats table builder"
```

---

## Task 2: Calibration section — advisory thresholds (TDD)

**Files:**
- Modify: `script_rubric/pipeline/pass2_synthesize.py:_build_calibration_section`
- Modify: `script_rubric/tests/test_pass2_calibration.py`

- [ ] **Step 1: Write failing test for thresholds**

Append to `TestCalibrationStats` class in `test_pass2_calibration.py`:

```python
    def test_section_has_advisory_thresholds(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        # midpoints: (78.0+77.7)/2 = 77.85 -> 77.9; (77.7+73.0)/2 = 75.35 -> 75.4
        assert "77.9" in text
        assert "75.4" in text
        assert "advisory" in text.lower() or "参考" in text or "刻度仅为参考" in text

    def test_section_has_overlap_warning(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "重叠" in text
        assert "质性" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestCalibrationStats -v`
Expected: 2 PASS, 2 FAIL (new threshold/overlap tests).

- [ ] **Step 3: Extend `_build_calibration_section` to add threshold block**

In `pass2_synthesize.py`, replace the function's `return table` line with the following code (inserted before the return):

```python
    threshold_lines = ["", "### B. 推荐阈值（advisory）", ""]
    if "签" in status_stats and "改" in status_stats:
        cut1 = round((status_stats["签"]["mean"] + status_stats["改"]["mean"]) / 2, 1)
        overlap_lo = min(status_stats["签"]["p25"], status_stats["改"]["p75"])
        overlap_hi = max(status_stats["签"]["p25"], status_stats["改"]["p75"])
        threshold_lines.append(
            f"- 签 / 改 边界 ≈ {cut1}（重叠区 {overlap_lo}-{overlap_hi} 需结合质性判断）"
        )
    if "改" in status_stats and "拒" in status_stats:
        cut2 = round((status_stats["改"]["mean"] + status_stats["拒"]["mean"]) / 2, 1)
        overlap_lo = min(status_stats["改"]["p25"], status_stats["拒"]["p75"])
        overlap_hi = max(status_stats["改"]["p25"], status_stats["拒"]["p75"])
        threshold_lines.append(
            f"- 改 / 拒 边界 ≈ {cut2}（重叠区 {overlap_lo}-{overlap_hi} 需结合质性判断）"
        )
    threshold_lines.append("")
    threshold_lines.append("> 分数与状态高度重叠，刻度仅为参考；最终 status 取决于质性维度（红旗/绿旗）。")

    return table + "\n" + "\n".join(threshold_lines)
```

- [ ] **Step 4: Run tests to verify all 4 pass**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestCalibrationStats -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add script_rubric/pipeline/pass2_synthesize.py script_rubric/tests/test_pass2_calibration.py
git commit -m "feat(rubric): add advisory threshold block to calibration section"
```

---

## Task 3: Calibration section — anchor scripts (TDD)

**Files:**
- Modify: `script_rubric/pipeline/pass2_synthesize.py:_build_calibration_section`
- Modify: `script_rubric/tests/test_pass2_calibration.py`

- [ ] **Step 1: Write failing tests for anchor selection**

Append a new test class to `test_pass2_calibration.py`:

```python
class TestAnchorSelection:
    def test_anchor_per_status_present(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "锚点" in text
        # 签 mean=78.0 -> S2 (78.0); 改 mean=77.7 -> R1 (78.0, |.3| smallest);
        # 拒 mean=73.0 -> J2 (73.0)
        assert "S2" in text
        assert "R1" in text
        assert "J2" in text

    def test_anchor_closest_to_mean_wins(self):
        from script_rubric.pipeline.pass2_synthesize import _select_anchor

        archives = [
            _make_archive("A", "改", 70.0),
            _make_archive("B", "改", 78.0),
            _make_archive("C", "改", 79.0),
        ]
        # mean = 75.67, closest = B (|78-75.67| = 2.33 < |79-75.67| = 3.33 < |70-75.67| = 5.67)
        anchor = _select_anchor(archives, target_mean=75.67)
        assert anchor.title == "B"

    def test_anchor_tiebreak_by_title(self):
        from script_rubric.pipeline.pass2_synthesize import _select_anchor

        archives = [
            _make_archive("Z", "改", 76.0),
            _make_archive("A", "改", 76.0),
        ]
        # both equidistant from 76 -> A wins by title sort
        anchor = _select_anchor(archives, target_mean=76.0)
        assert anchor.title == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestAnchorSelection -v`
Expected: 3 FAIL (one with `ImportError` on `_select_anchor`, two with anchor content missing).

- [ ] **Step 3: Add `_select_anchor` helper and extend `_build_calibration_section`**

In `pass2_synthesize.py`, add this helper before `_build_calibration_section`:

```python
def _select_anchor(group: list[ScriptArchive], target_mean: float) -> ScriptArchive:
    return min(group, key=lambda a: (abs(a.mean_score - target_mean), a.title))
```

Then in `_build_calibration_section`, append anchor-rendering logic before the final return. Replace the current `return table + "\n" + "\n".join(threshold_lines)` with:

```python
    anchor_lines = ["", "### C. 锚点剧本（每状态 1 部，按 mean_score 离均值最近选）", ""]
    for status in status_order:
        group = by_status.get(status, [])
        if not group:
            continue
        target = status_stats[status]["mean"]
        anchor = _select_anchor(group, target)
        dim_parts = [
            f"{DIMENSION_NAMES_ZH.get(k, k)} {anchor.dimensions[k].score}"
            for k in DIMENSION_KEYS
            if k in anchor.dimensions
        ]
        consensus = "；".join(anchor.consensus_points[:2]) if anchor.consensus_points else "无"
        if status == "签":
            flag_label, flag_items = "绿旗", anchor.green_flags[:1]
        else:
            flag_label, flag_items = "红旗", anchor.red_flags[:1]
        flag_text = "；".join(flag_items) if flag_items else "无"

        anchor_lines.append(f"#### 锚点 · {status} · 《{anchor.title}》")
        anchor_lines.append(f"- 类型：{anchor.genre} / 实际均分：{anchor.mean_score}")
        anchor_lines.append(f"- 维度：{' / '.join(dim_parts)}")
        anchor_lines.append(f"- 共识：{consensus}")
        anchor_lines.append(f"- {flag_label}：{flag_text}")
        anchor_lines.append("")

    return table + "\n" + "\n".join(threshold_lines) + "\n" + "\n".join(anchor_lines)
```

- [ ] **Step 4: Run tests to verify all 7 calibration tests pass**

Run: `pytest script_rubric/tests/test_pass2_calibration.py -v`
Expected: 7 PASS (4 stats/threshold + 3 anchor).

- [ ] **Step 5: Commit**

```bash
git add script_rubric/pipeline/pass2_synthesize.py script_rubric/tests/test_pass2_calibration.py
git commit -m "feat(rubric): add anchor script selection to calibration section"
```

---

## Task 4: Wire calibration section into handbook layout

**Files:**
- Modify: `script_rubric/pipeline/pass2_synthesize.py:synthesize_all` (around lines 122-153)

- [ ] **Step 1: Write failing test that handbook contains Part 4 calibration heading**

Append to `test_pass2_calibration.py`:

```python
class TestHandbookIntegration:
    def test_calibration_appears_as_part_four(self, tmp_path, monkeypatch):
        import script_rubric.pipeline.pass2_synthesize as p2

        monkeypatch.setattr(p2, "HANDBOOK_DIR", tmp_path)

        # Stub out the three LLM calls
        async def fake_universal(archives):
            return "通用规律占位"

        async def fake_overlay(archives, genre):
            return f"{genre} 占位"

        async def fake_redflags(rejected, borderline):
            return "地雷占位"

        monkeypatch.setattr(p2, "synthesize_universal", fake_universal)
        monkeypatch.setattr(p2, "synthesize_overlay", fake_overlay)
        monkeypatch.setattr(p2, "synthesize_redflags", fake_redflags)

        import asyncio
        handbook, _ = asyncio.run(p2.synthesize_all(_sample_archives(), version=99))

        assert "## 第四部分：评分校准刻度" in handbook
        # Part 4 must come before appendix
        assert handbook.index("## 第四部分：评分校准刻度") < handbook.index("## 附录")
        # Calibration content must be present
        assert "状态-分数分布表" in handbook
        assert "锚点" in handbook
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestHandbookIntegration -v`
Expected: FAIL with `AssertionError: '## 第四部分：评分校准刻度' not in handbook`.

- [ ] **Step 3: Modify `synthesize_all` to insert Part 4**

In `script_rubric/pipeline/pass2_synthesize.py`, locate the `handbook += f"""---` block that adds the redflags section (around line 142). Replace the entire trailing block (from `handbook += f"""---` through the data overview append) with:

```python
    handbook += f"""---

## 第三部分：地雷清单

{redflags}

---

## 第四部分：评分校准刻度

> 本节由训练集统计确定性生成，为预测时的刻度参考。

{_build_calibration_section(archives)}

---

## 附录：数据概览

{_build_data_overview(archives)}
"""
```

- [ ] **Step 4: Run all calibration tests to verify integration passes**

Run: `pytest script_rubric/tests/test_pass2_calibration.py -v`
Expected: 8 PASS (7 prior + integration).

- [ ] **Step 5: Run full test suite to verify no regressions**

Run: `pytest script_rubric/tests/ -v`
Expected: All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add script_rubric/pipeline/pass2_synthesize.py script_rubric/tests/test_pass2_calibration.py
git commit -m "feat(rubric): integrate calibration section as handbook Part 4"
```

---

## Task 5: Filter `cmd_pass2_only` to training set

**Files:**
- Modify: `script_rubric/pipeline/run.py:cmd_pass2_only` (around lines 132-139)

- [ ] **Step 1: Write failing test that pass2 uses training-only archives**

Append to `test_pass2_calibration.py`:

```python
class TestCmdPass2Filter:
    def test_pass2_filters_to_training_set(self, tmp_path, monkeypatch):
        import script_rubric.pipeline.run as run
        import script_rubric.pipeline.pass2_synthesize as p2

        # Build a parsed records list with 5 records, 1 in test split
        from script_rubric.models import ScriptRecord, Review
        records = [
            ScriptRecord(title=f"T{i}", source_type="x", genre="y",
                         submitter="z", status="改",
                         reviews=[Review(reviewer="a", score=75)])
            for i in range(5)
        ]

        # Build matching archives (all 5)
        archives = [_make_archive(f"T{i}", "改", 75.0) for i in range(5)]

        captured = {}

        async def fake_synth(passed_archives, version):
            captured["titles"] = [a.title for a in passed_archives]
            return "handbook", {}

        monkeypatch.setattr(run, "parse_xlsx", lambda _: records)
        monkeypatch.setattr(run, "match_texts", lambda *a, **kw: None)
        monkeypatch.setattr(run, "load_all_archives", lambda: archives)
        monkeypatch.setattr(run, "synthesize_all", fake_synth)

        import asyncio
        from argparse import Namespace
        asyncio.run(run.cmd_pass2_only(Namespace(version=4)))

        # split_holdout(seed=42, ratio=0.2) on 5 改-records: n_test=max(1, round(1.0))=1
        assert len(captured["titles"]) == 4
        assert len(set(captured["titles"])) == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestCmdPass2Filter -v`
Expected: FAIL with `assert 5 == 4` (current cmd_pass2_only passes all archives unfiltered).

- [ ] **Step 3: Modify `cmd_pass2_only` to filter by training titles**

In `script_rubric/pipeline/run.py`, replace the `cmd_pass2_only` function (around lines 132-139) with:

```python
async def cmd_pass2_only(args):
    version = args.version or 1
    logger.info(f"=== Pass 2 Only -> v{version} ===")

    records = parse_xlsx(XLSX_PATH)
    match_texts(records, DRAMA_DIR)
    train, test = split_holdout(records, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)
    train_titles = {r.title for r in train}
    logger.info(f"Holdout split: train={len(train)}, test={len(test)}")

    all_archives = load_all_archives()
    archives = [a for a in all_archives if a.title in train_titles]
    skipped = len(all_archives) - len(archives)
    logger.info(f"Loaded {len(all_archives)} archives, using {len(archives)} (training only); skipped {skipped} (test or unknown)")

    await synthesize_all(archives, version=version)
    logger.info("Done")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest script_rubric/tests/test_pass2_calibration.py::TestCmdPass2Filter -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest script_rubric/tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add script_rubric/pipeline/run.py script_rubric/tests/test_pass2_calibration.py
git commit -m "fix(rubric): filter pass2 archives to training set to prevent test leakage"
```

---

## Task 6: Rewrite predict prompt to reference calibration section

**Files:**
- Modify: `script_rubric/prompts/backtest_predict.md` (full rewrite)

- [ ] **Step 1: Replace prompt content**

Overwrite `script_rubric/prompts/backtest_predict.md` with:

````markdown
你是一位使用评审手册的剧本评审员。请根据手册对以下剧本进行评审。

## 评审手册

{handbook}

## 待评审剧本

标题: {title}
类型: {source_type} / {genre}

### 剧本正文
{text_content}

## 任务

**第一步：刻度对齐（强制）**
对照手册"第四部分：评分校准刻度"：
1. 阅读 3 部锚点剧本的维度分模式与共识/旗标，找到与本剧最相似的锚点。
2. 参考"状态-分数分布表"中各状态的均分与 P25/P75 区间，估算本剧的合理总分。
3. **注意**：分数与状态高度重叠（详见手册阈值表的重叠区），分数仅为刻度参考，**status 判定要综合质性维度（红旗/绿旗）**，不可仅凭分数硬切。

**第二步：维度评分**
按手册的 7 个维度逐一打分（1-10）。

**第三步：综合评分与状态**
- 综合评分（0-100）：基于第一步的锚点对齐结果。
- 状态判定（"签" / "改" / "拒"）：综合质性维度判断，参考手册阈值但不机械套用。

**第四步：评语与旗标**
- 写出 3-5 条关键评语（模拟责编视角）。
- 标注本剧踩了哪些地雷 / 命中哪些绿灯。

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
  "green_flags_hit": ["绿灯1"],
  "reasoning": "参考的锚点剧本是《xxx》，本剧维度分接近/高于/低于该锚点，因此分数定为 78。"
}
```

注意：`reasoning` 必填，必须显式提到"参考的锚点剧本是哪部"以及"分数偏高/偏低/相当的依据"。
````

Note: `PredictResult` model has extra fields that this prompt may not produce — that's OK, pydantic ignores unknown fields. The new `reasoning` field is also extra; we are not adding it to the model since it's only for LLM self-discipline.

- [ ] **Step 2: Verify prompt is valid markdown / template**

Run:
```bash
python -c "
from pathlib import Path
text = Path('script_rubric/prompts/backtest_predict.md').read_text(encoding='utf-8')
required = ['{handbook}', '{title}', '{source_type}', '{genre}', '{text_content}']
missing = [k for k in required if k not in text]
print('OK' if not missing else f'MISSING: {missing}')
"
```
Expected: `OK`

- [ ] **Step 3: Verify hard threshold is removed**

Run:
```bash
python -c "
from pathlib import Path
text = Path('script_rubric/prompts/backtest_predict.md').read_text(encoding='utf-8')
banned = ['80+ 为', '70-80 为', '<70 为', '80+签']
hits = [b for b in banned if b in text]
print('OK' if not hits else f'STILL PRESENT: {hits}')
"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add script_rubric/prompts/backtest_predict.md
git commit -m "feat(rubric): rewrite predict prompt to use calibration section"
```

---

## Task 7: Generate handbook v4 (live LLM run)

**Files:**
- Generate: `script_rubric/outputs/handbook/handbook_v4.md`
- Generate: `script_rubric/outputs/handbook/rubric_v4.json`

- [ ] **Step 1: Verify environment is set up (proxy cleared, API key present)**

Run:
```bash
cd /data/project/novel-writer && \
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && \
  python -c "from script_rubric.config import API_KEY, MODEL; print('MODEL:', MODEL); print('KEY set:', bool(API_KEY))"
```
Expected: `MODEL: gemini-3.1-pro-preview` (or whatever is in .env), `KEY set: True`

- [ ] **Step 2: Run Pass 2 to generate handbook v4**

Run:
```bash
cd /data/project/novel-writer && \
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && \
  python -m script_rubric.pipeline.run pass2 --version 4 2>&1 | tee /tmp/pass2_v4.log
```
Expected: log shows "Holdout split: train=37, test=7" (or similar — the exact numbers depend on actual dataset), then "Loaded 44 archives, using 37 (training only); skipped 7", then 3 LLM calls (universal, overlays per genre, redflags), then "Done".

- [ ] **Step 3: Inspect handbook v4 output**

Run:
```bash
ls -la script_rubric/outputs/handbook/handbook_v4.md script_rubric/outputs/handbook/rubric_v4.json && \
  grep -c "## 第四部分" script_rubric/outputs/handbook/handbook_v4.md && \
  grep -A 2 "状态-分数分布表" script_rubric/outputs/handbook/handbook_v4.md | head -20
```
Expected: both files exist; "## 第四部分" appears once; the calibration table is visible.

- [ ] **Step 4: Sanity-check anchor titles are not in test set**

Run:
```bash
cd /data/project/novel-writer && \
  python -c "
import json, re
with open('script_rubric/data/parsed/holdout_split.json', encoding='utf-8') as f:
    split = json.load(f)
test_titles = set(split['test_titles'])
hb = open('script_rubric/outputs/handbook/handbook_v4.md', encoding='utf-8').read()
anchors = re.findall(r'锚点 · \S+ · 《(.+?)》', hb)
print('Anchors:', anchors)
leaked = [a for a in anchors if a in test_titles]
print('Leaked:', leaked)
assert not leaked, f'TEST LEAK: {leaked}'
print('OK — no leakage')
"
```
Expected: `Leaked: []` and `OK — no leakage`.

- [ ] **Step 5: Commit handbook v4 outputs**

```bash
git add script_rubric/outputs/handbook/handbook_v4.md script_rubric/outputs/handbook/rubric_v4.json
git commit -m "chore(rubric): generate handbook v4 with calibration section"
```

---

## Task 8: Run backtest v4 and verify acceptance criteria

**Files:**
- Generate: `script_rubric/outputs/backtest/report_v4.md`

- [ ] **Step 1: Run backtest against handbook v4**

Run:
```bash
cd /data/project/novel-writer && \
  unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY && \
  python -m script_rubric.pipeline.run backtest --version 4 2>&1 | tee /tmp/backtest_v4.log
```
Expected: 7 prediction calls complete; "Backtest report saved" log line; final "Results: status=..%, range=..%, mae=..".

- [ ] **Step 2: Read report v4**

Run:
```bash
cat script_rubric/outputs/backtest/report_v4.md
```
Expected: Markdown report with overview metrics, per-row table, failure analysis if any, and conclusion.

- [ ] **Step 3: Verify acceptance criteria**

Check the four metrics from the report:

| Metric | v3 | v4 target | Pass condition |
|--------|-----|-----------|----------------|
| 状态命中率 | 71% | ≥70% | must hold |
| 区间命中率 | 14% | ≥60% | must improve |
| 分数 MAE | 14.7 | ≤8 | must improve |
| 严重误判率 | 0% | ≤10% | must hold |

If all 4 pass: proceed to Step 4.

If any fail: do **not** commit failure as success. Report which metrics missed and consult the diagnostic branches in the design doc:
- MAE still high → consider multi-anchor (P25/P50/P75) or score-derivation examples
- status dropped below 70% → strengthen "DO NOT" prefix in advisory threshold block
- range hit still low → add hard "interval width ≥ 8" constraint to predict prompt

Stop here and report to user before iterating.

- [ ] **Step 4: Commit backtest report**

```bash
git add script_rubric/outputs/backtest/report_v4.md
git commit -m "chore(rubric): backtest handbook v4"
```

- [ ] **Step 5: Final summary message**

Report to user:
- handbook v4 generated, calibration section verified
- backtest v4 metrics: status=X%, range=Y%, MAE=Z, critical=W%
- All 4 acceptance criteria pass / which failed
- Files committed: 3 source/test commits + 2 output commits

---

## Done Definition

- [ ] All 7 calibration tests + 1 cmd_pass2 filter test pass.
- [ ] Full test suite passes (no regressions).
- [ ] `handbook_v4.md` contains Part 4 calibration section with stats table, advisory thresholds, and 3 anchor scripts.
- [ ] No anchor script title appears in `holdout_split.json` test_titles.
- [ ] `report_v4.md` shows status ≥70%, range ≥60%, MAE ≤8, critical ≤10%.
- [ ] All commits land on `main`.
